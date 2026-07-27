# BLIT_STE_SPEC — the unified ST/STE hardware-blitter binary (PERF30 C4 + C5)

**ONE `BUGGYBOY.PRG` runs on both a plain ST and an STE**, using the Atari STE/Mega-ST **BLiTTER** chip
for the heavy masked object blits and the road fine-scroll when present and the 68000 RMW engines when
not. The blitter emits the
**same framebuffer bytes** as the CPU engine, so every byte-compare pin holds — a perf swap, never a pixel
change. (Slices 1-5 built and proved this as a *separate* `GAME_STE` binary; **slice 6 unified it** into
the shipping PRG — that framing supersedes the "separate binary" language below where they conflict; see
§11.)

This document is the driver design + the objshift2 → blitter recipe + the census that bounded the colour
engine + (§16) the road-scroll route. Historical slice tags (1-5) are kept for provenance.

---

## 1. Build (slice 6 — the unified binary)

`render/atari/build_game.sh` builds the shipping `BUGGYBOY.PRG` with the blitter path **always linked**
(`-DRM_BLITTER`; `src/blitter.c` + `src/blitter_objshift2.c` + `src/blitter_objshift.c`), bound at boot:

| invocation | output | notes |
|---|---|---|
| `bash build_game.sh` | `BUGGYBOY.PRG` | **unified** — blitter on an STE, CPU asm on an ST/TT (bound at boot) |
| `GAME_FORCE_NO_BLITTER=1 …` | `BUGGYBOY.PRG` | pins the CPU path even on an STE — a harness A/B baseline knob |
| `GAME_SCROLL_HOG=1 …` | `BUGGYBOY.PRG` | road-scroll passes on HOG instead of the shipping shared-bus restart loop — the §16 bus-policy A/B |
| `GAME_STE_SELFTEST=1 …` | (measurement) | + `src/blitter_selftest.c`, boots the driver proof, no game |
| `GAME_STE_SWEEP=1 …` | (measurement) | + `src/blitter_sweep.c`, boots the recipe sweep |
| `GAME_STE_CENSUS=1 …` | (measurement) | + `src/blitter_census.c`, drives + counts distinct tuples |

`src/blitter*.c` are excluded from the host `.so` / bench builds (`Makefile` `STE_SRC` filter-out) — they
poke supervisor-only I/O registers, so `RM_BLITTER` is never set for the host differential and `make test`
keeps pinning the C reference. The old `GAME_STE` two-binary profile / `BUGGYBST.PRG` is **retired**;
`GAME_STE` is accepted-but-ignored for script compatibility. The stock ST binary is no longer a separate
artifact — the unified PRG on an ST is **cadence-identical** to the old stock (§11), which replaces the
byte-identical-stock pin.

**Presence check — bind, never bail.** `main()` calls `blitter_available()` once at boot: a Supexec
excursion walks the cookie jar (`_p_cookies` @ `0x5A0`), checks the **`_BLT` cookie first** (TOS creates it
iff blitter hardware exists — authoritative), and on a pre-`_BLT` TOS falls back to `_MCH` id ∈ {STE/MegaSTE
= 1, Falcon = 3} — **not** "id ≥ 1", so the **TT030 (id 2) is correctly excluded**. A plain ST (0), TT, or
pre-cookie TOS (`0x5A0 == 0`) returns 0 **without touching any `0xFFFF8Axx` register** and simply **binds
the CPU asm engine** — no message, no exit. The result is stored in `g_have_blitter` (gates the F10-reload
cache flush) and passed to `rm_blit_objshift2_bind()`.

---

## 2. The blitter driver (`include/blitter.h` + `src/blitter.c`)

Named register block at `0xFFFF8A00` (no bare `0x8Axx` literals anywhere), typed `BlitPass` struct, and
`blit_run()` which pokes the registers and starts the chip.

**HOG vs shared.** `blit_run()` uses **HOG** (control bit 6): the chip holds the bus and runs the whole
pass to completion, then the CPU resumes with `BUSY` already clear. Justification: the masked object blits
are **small** (a few dst words wide × ≤ 43 rows) — tens of microseconds, far under the 20 ms VBL period —
so hogging the bus never starves the 50 Hz sound pump or the IKBD ISR, which run in the gaps *between*
blits (one per object). Shared mode (HOG = 0, 64-word bursts with a CPU restart loop) only earns its keep
on screen-sized blits where the CPU has overlapping work; here there is none. **The non-HOG restart loop**
(for a future screen-sized road/scroll blit) is:

```
restart:  bset.b  #7,(BLT_CONTROL)   ; set BUSY -> the chip runs one 64-word burst, then clears BUSY
          nop                        ; bus-settle before the next control read
          bne.s   restart            ; the bset's Z reflects the prior BUSY; loop until the blit completes
```
— documented, not shipped in slice 1.

> **CORRECTION (2026-07-26, C5 slice 1 — the loop above is INCOMPLETE as written; see §16).** It has no
> START. The `bset`'s Z flag reports the bit's value BEFORE the write, so on the first pass through the
> loop it reports the pre-start BUSY = 0 and the branch falls straight through — the chip runs one burst
> and the caller returns with the pass unfinished. Measured, not reasoned: shipped that way, the C5
> slice-1 sweep failed **640/640** scroll cases with ~63 of 3,360 words written per fill pass. The
> shipping form (`blit_start_and_wait_shared`, blitter.h) prefixes an explicit
> `move.b #BLT_CTL_BUSY,(BLT_CONTROL)` — which also CLEARS the HOG bit a previous `blit_start_and_wait`
> left set — and only then enters the loop above.

**Supervisor.** The `0xFFFF8Axx` page bus-errors from user mode. Slice 1's self-test runs the whole test in
one `Supexec`. Slice 2's live engine keeps the **entire `draw_object_list` pass in supervisor** (one
Supexec around the object loop), so per-blit Supexec overhead is avoided.

---

## 3. Why objshift2 is a cookie-cut, and the recipe

`rm_blit_objshift2` (`src/blit.c`) is a **self-masking** blit: the transparency mask is derived from the
source pixels at blit time as `mask = ~(w0 | w1)` (two source plane-words), and each drawn 16-px 4-plane
cell is

```
plane0 = (dst & mask) | w0        plane2 = (dst & mask) | (w0|w1)
plane1 = (dst & mask) | w1        plane3 = (dst & mask) | (w0|w1)      mask = ~(w0|w1)
```

The source is a **2-plane** sprite (planes 0,1); planes 2,3 are synthesised as `~mask = (w0|w1)` (the
sprite draws in palette indices 12–15). Per-plane this is exactly `dst = (dst AND mask) OR data`, i.e. a
classic two-pass **cookie-cut**:

- **AND pass** — `LOP = AND`, `HOP = SRC`, source = the `mask` bitmap (same mask for all 4 planes).
- **OR pass** — `LOP = OR`, `HOP = SRC`, source = the per-plane `data` bitmap (`w0`, `w1`, `uni`, `uni`).

The blitter endmask cannot compute a per-pixel data-derived mask, so the mask must be **materialised in
memory**. Crucially it can be built **once at asset-load time**: the sprite pixel source (`arena.gfx`,
`c->buf_c`) is static — read from `GRAPHICS.GRA` at boot, `const` in the dispatcher, never regenerated per
frame (only re-unpacked on the F10 reload). This is the PERF30 A2 "pre-shifted compiled sprites" build:
per fine-x phase, precompute the `(mask, data)` word arrays from the static gfx arena (~49 KB masks-only /
~98 KB full — effectively a 1 MB STE, which the target has).

### 3a. Aligned mapping — **PROVEN** (slice 1)

At `fine_x == 0` (`shl == 16`) the engine degenerates to an aligned cookie-cut into one column set (col1
untouched). `src/blitter_selftest.c` materialises the `mask`/`data` bitmaps from a synthetic sprite, fires
**8 blitter passes** (4 planes × {AND mask, OR data}) over a non-trivial background, and XORs the result
against the **real `rm_blit_objshift2`** output. `run_ste_selftest.py` boots it on `--machine ste
--blitter on` and asserts the diff is all-zero. **Result: 0/32000 — byte-for-byte.** Per plane `p`:

```
dst_addr = fb + y_top*160 + aligned_col + p*2   dst_x_inc = 8   dst_y_inc = 160 - 8*(cells-1)
x_count  = cells   y_count = rows   skew = 0   endmask1/2/3 = 0xFFFF   hop = SRC   lop = AND|OR
src (tightly packed): src_x_inc = 2, src_y_inc = 2
```

This pins the driver end-to-end: register poking, HOP=SRC + LOP AND/OR, the interleaved 4-plane walk,
endmasks, and Hatari's blitter model all agree with the C engine.

### 3b. Fine-x mapping — **PROVEN + ROUTED via pre-shift, not hardware skew** (slice 2)

`src/blitter_objshift2.c` implements the BASE-family fine-x blit. **Decision: pre-shift in the
materialiser + a skew=0 blit, NOT the hardware SKEW register.** Rationale: slice 1 proved the skew=0
AND/OR cookie-cut byte-exact, so doing the fine-x straddle in software (each source word spread across two
dst columns exactly as the CPU engine's `<<shl`, into pre-shifted `straddle+1`-wide bitmaps) keeps the pin
on the proven aligned recipe and sidesteps the blitter's FXSR/NFSR/endmask edge semantics — a
byte-exactness risk that would violate "no approximate pixels." The hardware-skew variant (unshifted
tables + `skew=fine_x` + a calibrated FXSR/NFSR sweep) is deferred as a **RAM optimisation**, not a
correctness path.

Per column `j` (0..straddle), plane data = the fine-x-shifted source, mask = `~(shifted w0|w1)`:
```
sh_w = (left_cell << (16-fine_x)) | (this_cell >> fine_x)          per plane word
data[j] = (sh_w0, sh_w1, sh_u, sh_u)   mask[j] = ~sh_u   (sh_u = sh_w0|sh_w1)   for planes 0..3
```
The 4 plane words of a 16-px cell are contiguous in the ST interleaved framebuffer and the cookie-cut
mask is identical across planes, so the bitmaps are laid out **interleaved** and the blit is **2 passes
per blit** (AND all planes, OR all planes) with a contiguous dst walk (`dst_x_inc=2`,
`dst_y_inc = -(160 + 2*(nwords-1))` to walk UP one scanline, matching the engine's bottom-up row order) —
not 8 per-plane passes.

**Proven:** `src/blitter_sweep.c` / `run_ste_sweep.py` sweeps the full case space (width_idx 0..2 × fine_x
0..15 × 12 columns spanning clip/base/clip × rows {0,3,0x2a} = 1728 cases): **720 BASE cases blitter-drawn,
0 mismatch** vs the CPU engine; 1008 CLIP cases correctly declined. A mutation (shift by fine_x+1) fails
601 cases — the straddle is genuinely exercised, not vacuous.

### 3c. Clip / edge families — **CPU hybrid** (slice 2)

The LEFT/RIGHT clip families (`col < 0` / `col ≥ base_ceiling`) stay on the CPU asm engine (a pinned
hybrid). `rm_blit_objshift2_dispatch` decides the family in USER mode (cheap arithmetic) and only enters
the Supexec/blitter path for BASE — a declined clip case never pays the excursion. Blitter-side clip
(endmask1/3 partial columns) is a future refinement; the hybrid keeps every clip pixel byte-exact today.

### 3d. Runtime routing + supervisor (slice 2)

`object_list.c` (the sole `RM_BLIT_OBJSHIFT2` call site) `#undef`/redefines the macro to
`rm_blit_objshift2_dispatch` under `GAME_STE` — the seam is kept OUT of `include/game.h`. The blitter
touches the supervisor-only I/O page, so a BASE draw runs inside **one Supexec per blit** (materialise +
2 blit passes). Per-blit Supexec measured cheap (< 1 % of frame) since the family filter runs before it;
a single excursion around the whole object pass is possible but carries supervisor-stack-depth risk on the
deep render tree — deferred.

**RAM cost:** the per-blit scratch is `bl_mask + bl_data = 2 × (4 planes × 4 cols × 43 rows) × 2 B ≈
2.7 KB` static. The slice-3 boot pre-shift tables (below) trade this for ~49 KB masks / ~98 KB full — well
inside the STE's ≥ 1 MB (the harness runs `--memsize 4`).

---

## 4. Pins (what proves the STE build)

Musashi cannot emulate the blitter, so the pins are Hatari-based (weaker instruction-level pinning than the
host Musashi differentials, compensated by whole-frame byte equality over a real drive):

| pin | script | slice 1 | slice 2 |
|---|---|---|---|
| stock .PRG byte-identical (flag off) | `shasum` | PASS | PASS (my edits byte-neutral) |
| stock goldens ×5 `--machine st` | `run_golden.py` | MATCH ×5 | MATCH ×5 |
| STE goldens ×5 `--machine ste` (objshift2 on blitter) | `run_ste_golden.py` | MATCH ×5 | **MATCH ×5** |
| blitter == `rm_blit_objshift2`, aligned | `run_ste_selftest.py` | 0/32000 | 0/32000 |
| blitter == `rm_blit_objshift2`, **full sweep** | `run_ste_sweep.py` | — | **1728 cases, 0 mismatch (720 BASE)** |
| whole-frame A/B stock-ST vs STE over the drive | `run_ste_ab.py` | 0 (by construction) | **0-mismatch ×10 frames (load-bearing)** |
| host differential suite | `make test` | 708 | 718 (concurrent work; host untouched by STE files) |
| cadence `--machine ste` before/after | `run_cadence.py` | baseline | **gate 8.22→7.22 vbl (~12%), §6** |

---

## 6. Cadence — the win, and how it was found (slices 2→3)

**Slice 2 measured flat** (leg-0 driving, free-run: stock 6.61 vs STE 6.65 vbl). The blitter is byte-exact
and live but did not collapse the objlist pass, so slice 3 **profiled the objshift2-DENSE gate frame**
(idle the autodrive on the leg-start gate — the frame the objlist pass dominates, PERF30 "gate frame").
Decomposition (free-run mean vbl/present, `GAME_STE_PROF_NOMAT/NOBLIT` timing builds):

| variant | mean | isolates |
|---|---|---|
| stock ST (CPU asm) | 8.28 | baseline |
| STE bare (dispatch + Supexec, no work) | 6.27 | removing the base CPU blits saves ~2.0 vbl |
| STE **nomat** (blit, skip materialise) | **7.27** | the boot-table ceiling — beats stock by ~1 vbl |
| STE noblit (materialise, skip blit) | 9.28 | **materialise alone = +3.0 vbl** |
| STE full (materialise + blit) | 9.28 | blitter passes are ~free (~1 vbl) |

**Finding: the per-frame MATERIALISE (~3 vbl) is the whole cost; the blitter passes are cheap.** The naive
path is a net LOSS because it re-shifts every frame. The blitter works; the *data prep* was the problem.

**Slice-3 fix: a memoisation cache** (`src/blitter_objshift2.c`). The materialised bitmap is a pure
function of `(src, src_off, fine_x, width_idx, rows_m1)` over `arena.gfx`, which is **static for the whole
race** (read once at asset load; the only writer is the F10 reload, off the render path — re-verified in
`src/assets.c` / `load_assets`). So a direct-mapped cache of the interleaved `(mask,data)` bitmaps never
invalidates: a miss materialises into the slot, a hit blits it straight. The gate/tunnel sprites (drawn
identically every frame) hit after warm-up → the profiled `nomat` win, byte-exact.

**Result (free-run):**

| scene | stock ST | STE cached | delta |
|---|---|---|---|
| leg-0 gate (idle, objshift2-dense) | 8.22 | **7.22** | **−12 %** |
| leg-4 gate (idle, second leg — not a leg-0 artifact) | 8.23 | **7.23** | **−12 %** |
| leg-0 driving (throttle) | 7.06 | 7.04 | ~flat (slow-moving sprites hit) |

**RAM:** the cache is `OBJSH2_CACHE_SLOTS (128) × sizeof(Objsh2Cache) ≈ 356 KB` static BSS in the STE
build (each slot holds a full interleaved mask+data bitmap = 2 × 4 planes × 4 cols × 43 rows × 2 B ≈
2.75 KB + key). Well inside the harness's `--memsize 4`; the honest **minimum STE config is 1 MB** (the
base STE ships 512 KB–1 MB — a 1 MB STE fits it with room, a 512 KB STE would need `OBJSH2_CACHE_SLOTS`
cut to ~64 = 178 KB). Collisions never corrupt pixels: a key mismatch is treated as a miss and
re-materialises the slot (verified — the full sweep stays 0-XOR with the cache live).

## 7. Slice 4 — what next (go/no-go)

1. **Blitter-side clip (LEFT/RIGHT) — ~~GO, now unblocked~~ MEASURED NO-GO (C5 census, 2026-07-26).** In
   slice 2 moving clip to the blitter would have added materialise cost; the cache removes that objection
   (clip sprites cache too). The plan was to fold the 1008 currently-declined clip cases in via
   `endmask1/3` partial columns and extend the sweep to keep them 0-XOR. **The census then costed the
   family: 2 CLIP calls / 1,802 cyc = 0.225 ms on the GATE frame, and objshift2 makes ZERO clip calls in
   real play.** A whole extra recipe family plus its sweep cases, for a fifth of a millisecond on the
   worst frame and nothing on the common one. Closed; see PERF30's C5 slice-2 note.
2. **Colour-indexed `rm_blit_objshift` pass 1 (25.3 % of the gate) — GO, same pattern.** Its cookie-cut is
   the 4-word `~(A|B|C)&D` mask + a colour fill; the identical cache-keyed pre-shift + 2-pass recipe
   applies. This is the bigger remaining stage — recommended as the slice-4 headline.
3. **One-excursion supervisor — DEFER.** Per-blit Supexec did not block the win (STE-bare 6.27 already
   beats stock 8.28), so the trap overhead is small; wrapping the object pass in one excursion is a minor
   optimisation with supervisor-stack-depth risk on the deep render tree. Revisit only if it shows on a
   collapsed profile.
4. **Static boot tables (vs the on-demand cache) — OPTIONAL.** The cache already reaches the `nomat`
   ceiling on repeated frames; precomputing all 16 phases at boot would only help the first appearance of
   each sprite (cold-cache frames) at a large RAM cost. Not worth it unless cold frames measure badly.

## 8. Slice 4 — the colour-indexed engine: recipe PROVEN, but NOT routed (the cache's driving wall)

**The recipe (byte-exact, `src/blitter_objshift.c`).** The colour-indexed pass 1 (`rm_blit_objshift`,
~25 % of the gate) is the SAME cache-keyed pre-shift + 2-pass cookie-cut, with three differences from
objshift2: the source is 4-plane (words A,B,C,D per 8-byte cell), the show mask is `~(A|B|C)&D`, and each
plane's pixels are gated by a per-plane **colour fill** from `color_pairs[colour]`. **No third pass** — the
fill is composited into the OR-data at materialise time; plane 3 (D) additionally masks its pixels by `~m`
(the engine's `is_last` special). The per-column values are the exact algebraic reduction of the CPU
engine's sequential AND-then-OR straddle (a column is written by cell j-1's col1 half then cell j's col0
half):
```
net_mask[j]   = m_col1[j-1] & m_col0[j]
net_data_p[j] = (pix_lo_p[j-1] & m_col0[j]) | pix_hi_p[j]      (absent neighbour → 0xFFFF mask seed / 0 px)
```
where a cell's half is `m = (rotl32(0xFFFF0000|mask16, shl))`'s high/low word and `pix = (word_p<<shl) &
fill_p`. **Proven** over the full objshift case space (base_cells 1/2 × fine_x 0..15 × 12 columns × 4
(colour,rows_m1,stride) tuples = 1536 cases): `run_ste_sweep.py` → **704 BASE cases blitter-drawn, 0
mismatch** vs the real `rm_blit_objshift`; a dropped plane-3 `~mask` mutation fails 297 cases.

**Why it is NOT routed — the on-demand cache hits a wall on driving.** Cache hit rates (250-frame
autodrive, counters at the SCREEN.BIN tail):

| scene | objshift2 hit | objshift (colour) hit |
|---|---|---|
| gate (idle) | 1500/1506 = **100 %** | 1500/1506 = **100 %** |
| driving (throttle) | 54/60 = 90 % (but only 0.24 blits/frame) | 128/1420 = **9 %** |

On DRIVING the colour engine issues ~5.7 blits/frame and **misses 91 %** — roadside objects change
fine-x / scale (rows) / colour every frame, so the key never repeats. Each miss pays the expensive 4-word
materialise, and routing it **REGRESSES the race ~15 %** (leg-0 driving 7.06 → 8.13 vbl). No on-demand-cache
policy escapes this: not materialising on a miss leaves the cache empty (0 % hit, no win); materialising on
a miss is pure overhead when the sprite never recurs. objshift2 escaped only because it issues almost no
blits while driving (0.24/frame). **So the colour engine ships byte-exact but on the CPU path**
(`-DRM_STE_OBJSH_ROUTE` opts it back in for experimentation); the shipping STE build routes objshift2 only.
*(Superseded by slice 9, §14: the knob and its glue are DELETED — the colour engine now ships routed
through the hardware-skew table, and the pre-shift path is sweep-only.)*

**The driving win needs the DATA, not the engine: boot pre-shift tables.** Eliminating the per-frame
materialise (precompute the `(mask,data)` phases from the static `arena.gfx` at load) is the ONLY way the
colour engine wins driving — the same conclusion slice 3 reached, now the binding constraint. This is the
deferred sprite-layout work (§3's A2 note): the pre-shift crosses cell boundaries, so it must key on the
sprite/subcell structure (`OBJSH2P_SUBCELL_S`), not a flat arena sweep.

**Combined RAM (both caches, STE build):** objshift2 `128 × ~2.75 KB ≈ 356 KB` + objshift `96 ×
~2.05 KB ≈ 197 KB` = **~553 KB** static BSS. Fits a 1 MB STE (the honest minimum) with headroom; a 512 KB
STE needs both slot counts roughly halved (~277 KB). The colour cache is unused while it stays on the CPU
path, so a shipping build that never opts it in can drop it — but it is kept compiled so the sweep pins it.

> **Stale figures (superseded by slice 6 + measured in §12):** the shipping caches today are
> objshift2 **16 slots / 43 KB** (§11) + colour **219 KB** = **262 KB**, not 553 KB; and the measured
> unified footprint is **1.18 MB** (text 122,624 + BSS 1,114,796), so "fits a 1 MB STE" is wrong — the
> honest minimum machine is **2 MB** (see §12 for the diet option). *(Superseded by §15: the 1 MB diet
> landed — the minimum is **1 MB** on ST and STE alike.)*

## 9. Slice 5 — go/no-go (revised by the slice-4 finding)

1. **Boot pre-shift tables — the gating item, now RESOLVED by census (§10): NO-GO for the colour engine,
   UNNEEDED for objshift2.**
2. **Colour engine routing — stays CPU** (the census shows tables can't rescue it).
3. **Blitter-side clip (both engines)** — still open, but a minor win (clip is the blit minority).
4. **objsprite engine (the third fine-x blitter) — LOWER priority**; same recipe, cold on the gate.

## 10. Slice 5 — the boot-table census: a MEASURED verdict (NO-GO for colour, UNNEEDED for objshift2)

Boot tables only pay off if the reachable materialise-key set is bounded and fits RAM. `src/blitter_census.c`
(`-DGAME_STE_CENSUS`) instruments every objshift/objshift2 call over a real drive and counts the DISTINCT
base-family tuples — the exact set a boot table would enumerate. `run_ste_census.py` drives leg 0 headless
at growing frame counts:

| frames | objshift2 distinct | objshift (colour) distinct | colour distinct/frame |
|---:|---:|---:|---:|
| 30 | **6** | 100 | 3.3 |
| 40 | **6** | 149 | 3.7 |
| 60 | **6** | 349 | 5.8 |

**objshift2 — BOUNDED at 6 distinct tuples** (flat as the drive grows; it is a fixed-sprite pass). The
128-slot cache already covers it 100 % (§6 hit rate) — **boot tables are UNNEEDED**; slice 3's routing is
the whole win there. Confirmed **6 on every leg 0-4** (60-frame census).

**colour engine — effectively UNBOUNDED.** Distinct grows ~5/frame and *accelerating* (more objects enter
view as you drive), with ~70 % of blits carrying a never-before-seen tuple — the roadside pass draws many
objects across a continuum of scale (`rows_m1`) × sub-pixel-x (`fine_x`) × `src_off`. Extrapolated over a
full leg (hundreds–thousands of driving frames) the set is **tens of thousands of entries × ~2 KB ≈ tens
of MB — it does not fit a 1 MB (or 4 MB) STE.** Confirmed on **all legs 0-4** (60-frame census: distinct
131–349, 43–97 % unique). MEASURED **NO-GO for full colour boot tables.** (The
headless autodrive drives off-course and crashes past ~60 clean frames, so the census caps there — but the
monotonic super-linear curve to 60 frames is decisive, and it is **independently corroborated by slice 4's
9 %/91 % cache hit/miss** at 96 slots: a bounded recurring set would have hit far more.)

**The hybrid fallback also fails.** A "big non-evicting cache for the recurring set + CPU for the rest"
needs a recurring set; here ~70 % of tuples are unique (never recur), so a bigger cache just fills with
one-shot entries — each still pays the materialise once. There is no recurring set to cache. So neither
full tables NOR a hybrid escapes the per-frame materialise for the colour pass.

**Verdict (evidence over a forced landing, the B2/A5 precedent):** the colour engine stays on the CPU
(byte-exact recipe preserved, `-DRM_STE_OBJSH_ROUTE` for experimentation); the STE build's honest object
win is **objshift2 (gate −12 %)**. The colour pass's driving cost is irreducible under the pre-shift +
cache/table approach — a real colour win would need a fundamentally different scheme (e.g. hardware
skew from unshifted data, so no per-frame materialise at all — the FXSR/NFSR calibration risk slice 2
deferred), not more tables. That is the only remaining lever for the colour pass, and it is a research
item, not a landing. *(That lever landed: §12 measured the skew key bounded, §13 proved the recipe,
§14 routed it — `-DRM_STE_OBJSH_ROUTE` is deleted; the skew table ships.)*

> **CORRECTION (2026-07-25, slice 7 — see §12).** Two facts above are superseded:
> 1. *"The headless autodrive drives off-course and crashes past ~60 clean frames"* was an
>    instrumentation artifact, not a crash: the census build also passed `-DGOLDEN_BOOT_LEG`, whose
>    boot-time golden dump **races `census_dump` for SCREEN.BIN** (the runner takes the first full
>    file). With the flag dropped (and a `#error` now guarding the pair) the autodrive censuses
>    cleanly to **≥300 frames**. The slice-5 counts themselves were sound — the re-key control
>    reproduces leg-0 full-key 100/149/349 at 30/40/60 exactly — so the UNBOUNDED verdict for the
>    **full pre-shift key** stands.
> 2. That verdict does **not** transfer to reduced keys: §12 measures the set as **BOUNDED** once
>    the pre-shift scheme's key fields (fine_x, colour, rows) are removed by hardware skew.

## 11. Slice 6 — the UNIFIED ST/STE binary

The census (§10) made this cheap: objshift2's reachable set is a **bounded 6 distinct tuples**, so its
cache shrinks to a census-justified static size and lives unconditionally in BSS. One `BUGGYBOY.PRG` now
serves both machines.

**Binding design — a boot-bound function pointer (zero ST overhead).** `object_list.c`'s sole
`RM_BLIT_OBJSHIFT2` call site resolves (under `-DRM_BLITTER`, the m68k target) to `rm_blit_objshift2_fn` —
a function pointer initialised to `rm_blit_objshift2_asm` and bound once at boot by
`rm_blit_objshift2_bind(blitter_available())`: to the blitter dispatch on an STE, or left at the CPU asm
engine on an ST/TT. Measured stock-ST overhead of the one indirection vs the old direct call: **ZERO** —
`--machine st` cadence of the unified PRG is byte-identical to the old committed stock on both scenes
(gate 8.932 = 8.932, drive 8.167 = 8.167 vbl/present). The pointer (not a per-blit `if (have_blitter)`
branch) was chosen precisely so the plain ST pays nothing per blit. The colour engine stays on the CPU on
every machine (§8/§10); only objshift2 is bound. The seam is kept OUT of `include/game.h` (it lives in
`object_list.c`).

**Cache shrink.** `OBJSH2_CACHE_SLOTS` 128 → **16** (nearest power of two > 2× the 6-tuple working set;
zero eviction). Re-verified on the gate: objshift2 hit=360 miss=6 = **100 % after the 6 one-time warmup
misses**. BSS: **356 KB → 44 KB** for the objshift2 cache. The colour cache (197 KB, unused on the CPU
path) is kept compiled so the sweep pins it. **Net unified-PRG BSS over the old stock: +44 KB** (the
objshift2 cache) + the small blitter code — well inside the base game's existing **1 MB** requirement,
which does **not move**: the unified PRG runs in the same memory footprint on both a 1 MB ST and STE.

**Same-PRG verification matrix (the two-binary story, retired):**

| pin | result |
|---|---|
| SAME PRG, goldens ×5 on `--machine st` (CPU path) | **MATCH ×5** |
| SAME PRG, goldens ×5 on `--machine ste --blitter` (blitter path) | **MATCH ×5** |
| SAME PRG, whole-frame A/B st(CPU) vs ste(blitter), 15 frames | **0-mismatch** (`run_ste_ab.py`) |
| recipe sweep (both engines, separate measurement build) | **3264 cases, 0 mismatch** |
| stock-ST cadence UNREGRESSED (unified st vs old stock) | **identical** — gate 8.932=8.932, drive 8.167=8.167 |
| STE gate win retained | **7.949 vbl (−11 %)** |
| `--machine tt` (no blitter) boots + renders on the CPU path | **MATCH, no bail** |
| host differential | `make test` green |

**Retired:** the separate `BUGGYBST.PRG` and the "stock byte-identical" pin (there is no separate stock
artifact any more; the unified-vs-old-stock *cadence identity* on `--machine st` is the replacement).

> **Correction (2026-07-25, §12):** "the base game's existing 1 MB requirement" was asserted, not
> measured. The measured unified footprint is **1.18 MB** (`m68k-elf-nm -S`: text 122,624 + BSS
> 1,114,796 — arena 380 KB, screen pool 319 KB, colour cache 219 KB, scroll prebuild 104 KB, objshift2
> cache 43 KB), so the honest minimum machine is **2 MB** on ST and STE alike. The unused 219 KB colour
> cache is the obvious diet if a 1 MB target ever matters (it only backs the `-DRM_STE_OBJSH_ROUTE`
> experiment and the sweep's measurement build). *(Realized in slice 9: the cache left the shipping
> link entirely — footprint now 1.08 MB, §14. Then §15's diet landed the rest: minimum = **1 MB**.)*

## 12. Slice 7 — the RE-KEY census: BOUNDED under hardware skew (tables are GO)

Slice 5's NO-GO measured the **full pre-shift key** `(src_off, fine_x, color, stride, rows_m1,
base_cells)` — the set a *pre-shifted* table must enumerate. A **hardware-skew** engine (SKEW +
FXSR/NFSR, blitting from **unshifted** bitmaps) shrinks that key structurally:

- `fine_x` — the chip shifts at blit time; the materialised content no longer depends on it.
- `color` — the per-plane fill is a **binary select** (`fill_p ∈ {0, 0xFFFF}`): a plane is either
  OR'd with the source bitmap or skipped. Colour picks *which* passes run, not the bitmap bytes.
- `rows_m1` — materialise each sprite at its max rows and blit fewer via `y_count`.

`src/blitter_census.c` now counts the colour engine under four keys at once (full / noshift /
noshift-nocolor / **sprite** `(src_off, stride, base_cells)`), hashed as one subset chain; the report
carries a magic + set-count header that `run_ste_census.py` validates (the C↔Python wire-format pin,
and the tripwire that would have caught the §10 race).

**Measured (leg 0, distinct per key by drive length; full key = the slice-5 control):**

| frames | full | noshift | noshift-nocolor | **sprite** |
|---:|---:|---:|---:|---:|
| 30 | 100 | 62 | 62 | **18** |
| 60 | 349 | 136 | 124 | **60** |
| 80 | 479 | 199 | 158 | **76** |
| 140 | 617 | 216 | 162 | **78** |
| 300 | 989 | 280 | **162** | **78** |

- **full — UNBOUNDED** (control): reproduces slice 5 exactly (100/149/349), still climbing at 300 f.
- **noshift — still growing** ~14× slower: dropping fine_x alone is not enough.
- **noshift-nocolor — BOUNDED at 162** (flat 140→300 f): roadside scales are quantised per sprite.
- **sprite — BOUNDED at 78** (flat from ~80 f). All legs at 140 f: 78/75/79/98/79. From 140→300 f
  leg 0 issued +700 base calls and **0 new sprite keys — a 100 % table hit rate**; over the whole
  300-frame drive only 4.8 % of blits carried a first-sight key (vs 60 % under the full key). This is
  the recurring set the §8 on-demand cache (9 % hit) could not find — it exists once fine_x/colour/rows
  leave the key.

**RAM.** Entry = (1 mask + 4 data planes) × `base_cells` × 43 rows × 2 B = 430 B (cells=1) / 860 B
(cells=2). Worst leg (98 entries): **41–82 KB**; all-legs sum 409 entries (a loose upper bound — legs
share the catalogue): 172–344 KB. Hard structural ceiling regardless of counts: entries store 1.25× the
disjoint arena bytes they cover, and the whole gfx arena is 234 KB → **≤ ~293 KB total**. Routing
colour to a static table retires the 219 KB on-demand colour cache, so the **net footprint delta is
≈ −40 KB to +75 KB**.

**What this does NOT prove:** the skew recipe itself. The FXSR/NFSR/endmask edge semantics under
`skew = fine_x` are the byte-exactness risk slice 2 deferred — that calibration (pinned by the existing
`run_ste_sweep.py` case space) is the open engineering work; this slice only establishes the data side
is bounded and affordable. Also unmeasured: the `base_cells` split of the 78–98 keys (RAM given as
bounds) and the cross-leg key union (per-leg max vs sum given as bounds) — both cheap to instrument
when the table is built. **→ Resolved by slice 8 (§13): the recipe is proven byte-exact.**

## 13. Slice 8 — the hardware-SKEW colour recipe: PROVEN byte-exact (no FXSR/NFSR needed)

`src/blitter_skew.c` implements the colour engine's BASE family from **unshifted, colour-independent**
bitmaps with the chip doing the fine-x shift. The §8 straddle algebra collapses exactly onto the
blitter's skew semantics (with `k = fine_x`): `net_mask[c] = skew(m_{c-1}, m_c)` and
`net_data_p[c] = skew(P_{c-1}, P_c) & f_p` — the fill commutes with the skew, and the CPU reduction's
`& m_hi` on the low half is a no-op (the `rol.l` seed's high bits are ones).

**Unshifted bitmap set** (5 per sprite region, `base_cells` words/row + pad):
`M = ~(A|B|C)&D`, `P0..P2 = A,B,C`, `P3 = D & ~M` (the engine's `is_last` special, pre-folded).
Public seam (built for slice 2): `ObjshSkewBitmaps` + `rm_objsh_skew_materialise(bm, …)` (materialise
into a caller-owned set — a table entry) + `rm_blit_objshift_skew_from(bm, …)` (blit from a given set);
`rm_blit_objshift_skew` is the scratch-backed wrapper the sweep pins.

**The calibrated register recipe — 4 AND + up to 4 OR passes, per plane, skew=fine_x, FXSR=0, NFSR=0:**

| | AND (mask `M`) | OR (data `P_p`; skipped when `f_p == 0`) |
|---|---|---|
| HOP / LOP | SRC / AND | SRC / OR |
| skew_ctl | `fine_x` (no FXSR, no NFSR) | same |
| endmask1 / 2 / 3 | `0xFFFF>>k` / `0xFFFF` / `~(0xFFFF>>k)` | same, each `& f_p` |
| x_count / y_count | `base_cells+1` / rows | same |
| src_x_inc / src_y_inc | 2 / **0** | same |
| dst_addr / x_inc / y_inc | plane col0, bottom row / 8 / `-(160 + 8*base_cells)` | same |

Three structural findings (why the slice-2 risk dissolved):
1. **FXSR/NFSR are unnecessary — endmasks do the edges.** Writing `base_cells+1` columns from
   `base_cells` source words leaves exactly one polluted read per line (column 0's leftover top `k`
   bits; the last column's wasted next-row read). The CPU engine touches neither, and
   `endmask1 = 0xFFFF>>k` / `endmask3 = ~(0xFFFF>>k)` block exactly those bits. No preload, no
   suppressed fetch, no sentinel columns in the bitmaps.
2. **`src_y_inc = 0`**: with `x_count = base_cells+1` over a packed `base_cells`-word row, the x-walk
   already spans the row; one pad row of words absorbs the final wasted read (padded to cover the
   FXSR *mutation* build's drift too, so even diagnostic builds never read out of bounds).
3. **The colour fill rides in the OR-pass ENDMASKS** (`dst |= src & e`), so the bitmaps stay
   colour-independent for arbitrary fill words — stronger than §12 assumed. On real game data every
   fill word is 0 or 0xFFFF (the `color_pairs` bit-expansion; verified over all legs), so a blit is
   **4 AND + popcount(colour) OR ≈ 6 passes on average** — a zero plane's OR pass is skipped outright.

**Pins (all green, supersedes §11's 3264-case figure):**

| pin | result |
|---|---|
| sweep, three grids (objshift2 / pre-shift / skew) | **4800 cases, 0 mismatch**; handled 720 / 704 / 704 |
| non-vacuity gate (C-emitted expected-BASE counts; self-describing layout tail) | handled == expected enforced; forced-decline build **fails loudly** (verified) |
| mutation coverage, `--mutate all` (others grids skipped) | skew+1 **704**, FXSR-on **704**, endmask1 **643**, endmask3 **660**, plane-3 **297** — all caught |
| host differential | `make test` **730** (incl. the Makefile `STE_SRC` exclusion of the skew file) |
| shipping PRG | **sha256-identical** before/after the whole slice |

**Cost (Hatari 200 Hz timer, swept shape base_cells 2 × 32 rows, 1000 iters):** materialise 13,520 cyc;
blit passes **timed in isolation** 16,680 (synthetic 8-pass) / **12,920 (game fill, 6 passes)**;
combined 26,400; shipping CPU asm 33,960. So the skew path is **0.78×** the CPU engine *with* a
per-call materialise, and **0.38×** blitting from a table (slice 2). Honesty caveats: the earlier
subtract-two-totals estimate (~1,920 cyc for the passes) was an artifact — the isolated timing is the
honest figure; Hatari's blitter timing is a model, not cycle-exact hardware, like every C4 cadence
number (§4); and the 33–48-row band (cap `OBJSH_MAX_ROWS = 0x30`) is above the sweep grid's top —
structurally low risk (rows enters only as `y_count`) but stated.

**Slice 2 (next):** the static table keyed on §12's `sprite` key (materialise into entries at load /
first sight), routing behind the boot binding, per-pass register-poke batching (the setup is now the
dominant per-blit CPU cost), the shipping-path clip-test dedup (`objsh_is_base` is shared by the
census + skew paths; `blitter_objshift.c`'s two internal copies still pending), and the cadence
measurement — the go/no-go is DRIVING must not regress (the §8 failure mode), with gate improvement
expected from 0.38×. **→ Landed as slice 9 (§14): GO.**

## 14. Slice 9 — the colour engine ROUTED through the skew table: GO (driving improves)

The shipping STE build now routes `rm_blit_objshift`'s BASE family through the hardware-skew table.
`-DRM_STE_OBJSH_ROUTE` and its glue are **deleted**; the pre-shift path (`rm_blit_objshift_blitter` +
its 219 KB cache) left the shipping link and lives **sweep-only**, where it still pins the pre-shift
recipe. The shipping route is pinned by the goldens / A-B / the new table sweep section — not by the
pre-shift grid.

**Design.**
- **Table:** `skew_table[128]` (`ObjshSkewEntry` ≈ 984 B; 123 KB BSS), open-addressed, linear probe,
  **no eviction**; key = `(src, src_off, stride, base_cells)`; `rows_done == 0` marks free. Entries
  **grow on demand** (a taller call re-materialises the same key from row 0; rows are prefix-stable, so
  a grown entry is byte-identical and a shorter call just blits fewer via `y_count`) — chosen over
  materialise-at-max so the stride-driven source walk never reads rows no real call asked for.
- **Flush per leg (the union measurement made this mandatory):** the census now dumps the sprite-key
  set contents and the runner unions legs 0–4 — converged (300 f/leg) per-leg 78/75/79/98/79, but
  **union = 128 = exactly the table capacity, zero headroom**. An F10-only flush would fill the table
  mid-race and retire the route. So `start_leg()` (the single leg-init funnel) flushes the table:
  the live set is one leg's ≤ 98 (~30 spare), and each leg pays only the measured warm-up (the leg-0
  driving figure below IS the cold-table case: 68 first-sights + 43 grows inside it). objshift2's
  6-tuple cache is deliberately not flushed. A **saturation latch** guards the impossible-per-census
  overflow: on the first full-table decline the whole route retires to the (pixel-identical) CPU
  hybrid for the race — no perpetual 128-probe scans — re-armed by the flush.
- **Routing:** boot-bound `rm_blit_objshift_fn` (statically defaulted to the CPU asm — no NULL window),
  bound with objshift2's via one `rm_blit_bind_all(have_blitter)`; flushes via `rm_blit_flush_all()`.
  Seam in `object_list.c`, out of game.h. CLIP / over-tall / zero-row decided in user mode; BASE = one
  Supexec per blit (**quantified: ~0.3–0.55 ms/frame at ~4.5 blits — the §7 one-excursion idea stays
  deferred on that number**).
- **Poke batching:** `blit_skew_begin` owns the per-blit invariants (increments, HOP, skew, X_COUNT —
  the chip reloads x_count from an internal latch per line, sweep-verified); passes grouped 4 AND then
  ORs so endmasks/LOP poke once per group. `src_addr` must be re-poked every pass — **the chip walks
  it** to `bitmap + 2*base_cells*rows`. 42 register writes per 6-pass blit vs `blit_run`'s 102; the
  HOG start/wait is one shared `blit_start_and_wait` (single owner for the bus policy). Table hash is
  a shift/xor mix (no `__mulsi3`).

**Pins (all green):**

| pin | result |
|---|---|
| sweep | **4936 cases, 0 mismatch** — grids 720/704/704 + **table section 134/134** (GROW / CLIP / HIT / fill-128 / FULL-decline / latched-decline / flush-rearm; declined cases must leave the fb untouched and complete byte-exactly on the CPU hybrid) |
| `--mutate all` | **6/6 caught** — recipe mutations 704/704/643/660/297 + `NOGROW` **caught only by the table section** (1 case; grow ordering is load-bearing and documented) |
| goldens | same PRG **MATCH ×5 `--machine st`** and **×5 `--machine ste`** (re-run after the flush landed) |
| whole-frame A/B st(CPU) vs ste(blitter) | **0-mismatch** (now load-bearing for the colour engine) |
| host differential | `make test` **730** |
| `--machine tt` | CPU path, 0 bytes different from st |

**Cadence (leg 0, sub-vblank render clock; ST tick-identical throughout):**

| scene | objshift2-only routing | + colour routed | vs stock ST |
|---|---:|---:|---:|
| STE gate (idle 200 f) | 111.05 ms | **105.58 ms** | **−19.2 %** |
| STE drive (250 f) | 99.22 ms | **97.18 ms** | **−2.5 % — GO, no regression** |

Driving route counters: **90 % pure table hits** (1004 hit / 68 first-sight / 43 grow / 0 full) — the
inversion of §8's 9 %-hit failure. Sweep cost bench: table blit **9,400 cyc** vs CPU asm 33,920
(**0.28×**). Shipping footprint: text 122,368 + BSS 1,009,752 = **1.08 MB** (−97 KB vs pre-slice: the
219 KB cache left, the 123 KB table + code came in). Honest minimum machine stays **2 MB**
*(superseded by §15: the diet took it to **1 MB**)*.

**Noted, not folded in:** the probe's `muluw #984` (entry not power-of-two; ~0.4 %/blit — padding to
1024 B costs 5 KB BSS for a shift) — **CLOSED as a NO-GO on SIZE (C5 census, see PERF30's C5 slice-2
note): the measured win is 0.028 ms/frame and the pad costs 5,120 B of a margin now standing at 9,548 B
(§17). Half the 1 MB STE's remaining headroom for 0.03 % of a frame is not a trade this build makes**;
grow-from-`rows_done` (warm-up-only saving, measured and skipped);
the `SYS_HZ200` `-Warray-bounds` build noise (pre-existing pattern). Hatari-model caveat (§13) applies
to every cadence number here; the byte-exactness pins do not depend on it.

## 15. Slice 10 — the 1 MB DIET: the remaster runs on a 1 MB ST and STE, like the original

**User requirement:** the remaster must run on a 1 MB machine like the original. *(Corrected
2026-07-26 by the binary-recovered numbers: the original holds only **437 KB of TPA** — 48.6 KB
program + one 388,616 B Malloc — and START.PRG's hard-coded `0x77000` scratch pins a **512 KB ST
design target** (medium-high confidence). "512 KB was not enough" was wrong; ≈0.5 MB resident incl.
the TOS screen was right. The requirement as set — 1 MB max — stands and is met; a 512 KB target
would be a separate ~270 KB campaign against the perf structures. See README "Measured performance
& memory".)* Post-slice-9 footprint was 1.132 MB against a measured TPA of
**905,448 B** (EmuTOS 1 MB, the binding number; TOS 1.04 desktop 940,906 — measured with a
`Malloc(-1)` probe at `--memsize 1`). The diet closed the gap in two moves, both measurement-first.

**Move 1 — the 256 KB overdraw tails were sized to folklore.** `SCREEN_OVERDRAW` was 0x20000 per
buffer because clipped roadside draws "write up to ~102 KB past the screen" — an unverified estimate
(PERF30 §A2 had flagged it). The reach census (`tools/reach_census.py` + `tools/reach_probe.c`,
now in-repo and reproducible): over **5,240 composed frames + 4,000 forced-branch dispatcher runs +
305 staged frames**, all legs and scene classes, the maximum write past the visible 32,000 bytes is
**8 bytes** (`render_road`, offsets 32,000–32,007, 81 frames; every object engine tops out *below*
32,000; 0 writes before offset 0). The planned fully-off-screen cull is **moot** — nothing is ever
drawn below the screen (both family predicates are purely horizontal). New tail: **0x1000** (512×
the measured reach; `32,000 + 0x1000 = 36,096` keeps the second buffer 256-aligned), saving
**253,952 B**. `SCREEN_TAIL_LIVE (8)` names the legitimate render_road prefix.

**Standing guards on the number** (the ~102 KB lesson: never folklore again):
- **Host**: `test/equiv.py` canaries the whole tail past `SCREEN_TAIL_LIVE` and asserts it untouched
  on every compared composed frame — `make test` is now the reach-regression tripwire (mutation-
  checked: a draw at +0x800 reddens 16 tests). `test/adapter.py` regex-reads `SCREEN_OVERDRAW` and
  `SCREEN_TAIL_LIVE` from game_main.c — one source of truth.
- **Target**: trace builds (`GAME_CADENCE_TRACE`/`GAME_TAIL_CANARY`) canary-fill and scan the whole
  4,088-byte guarded tail per present, latched trip counters in the cadence tail (mutation-checked
  on target: +0x800 draw trips 100 presents). Zero cost in the shipping PRG.
- **Chip path**: a new 32-case below-screen sweep section (destinations flush/straddling/1-row/
  wholly-below the bottom edge, both engines, both paths) with every sweep comparison now spanning
  screen + tail — the blitter writes nothing past the tail the CPU doesn't.

**Move 2 — the STE tables leave BSS.** `skew_table` (125,952 B) + `objsh2_cache` (44,480 B) are now
**placed into the free TPA above BSS at boot**, only when the blitter binds: `os.s` `_start` captures
the basepage and initial SP; `rm_blit_bind_all` computes `base = align(p_bbase + p_blen)`,
`ceiling = min(p_hitpa, initial_sp) − 0x4000` (stack margin), memsets the block (the BSS-zero
markers — `rows_done`, `valid` — are re-established manually), and hands each module its pointer. No
`Mshrink`/`Malloc` — the shell owns the whole TPA, exactly the "ample RAM" the original relied on.
**Total safety for the unplaced state**: the skew route starts latched-full, `objsh2` declines at its
single entry on a null cache, both flushes are null-safe total functions, and a declined placement
binds the CPU engines exactly like a no-blitter machine. The sweep consumes the bind result and
reports a clean DECLINE (verified via `GAME_FORCE_NO_BLITTER`) instead of running unplaced.

**Result (all pins green):**

| | before diet | after |
|---|---:|---:|
| text + data + bss | 1,132,000 | **707,840** |
| screen_pool | 326,400 | 72,448 |
| skew_table / objsh2_cache | 170,432 B BSS | placed at boot (STE only) |
| 1 MB ST | won't load (−227 KB) | **fits, +197 KB spare** |
| 1 MB STE incl. placed tables | won't load | **fits — blitter route LIVE, 14,092 B spare above the 16 KB stack margin** |

Pins: `make test` 730 (host canary live); goldens ×5 st + ×5 ste at default memsize AND at
**`--memsize 1`** (the new standing pin — run_golden/run_ste_golden take `--memsize`, all runners
honor `RM_MEMSIZE`, and the census/sweep pin themselves to 4 MB — CENSUS.PRG alone is 1.4 MB);
sweep **4,968 cases 0-XOR** incl. the below-screen section; A/B 0-mismatch; cadence within noise
(gate 105.47 / drive 97.34 ms) with 0 canary trips.

**Watch item:** the 1 MB STE margin is thin — **10,620 B of future program growth silently drops a
1 MB STE to the CPU engines** (pixel-identical, slower; the cadence tail's `free TPA bytes` counter
is the observable). Check it when BSS grows. The `--memsize 1` goldens are placement-blind by design
(CPU fallback is pixel-identical); the cadence route counters are what prove the blitter bound.
*(Margin corrected 2026-07-26 by the consolidated measurement: the earlier "14,092 B" was the TRACE
build's margin — the shipping PRG's is 10,620 B, pinned empirically: a BSS-pad probe shows the
placement declining at exactly +4 bytes over the 170,432 the tables need. The usable 1 MB TPA is
905,440 B by basepage arithmetic — the earlier 905,448 was the `Malloc(-1)` view, 8 B apart. The
canonical perf + memory tables live in `README.md` "Measured performance & memory".)*

## 16. C5 slice 1 — the ROAD FINE-SCROLL on the blitter (the third route, and the first with no table)

`rm_blit_road_scroll` (`src/scroll.c`) was the last big stage still on the 68000 when the blitter is
bound: **12.06 ms of the 130.5 ms gate frame** on the Musashi bench, 9 % of it, and the second-largest
single stage after the object tree. It is also the most blitter-shaped work in the game — two constant
fills and a rectangular copy — so it is a much cleaner cookie than either object engine, and the whole
campaign fits in one slice.

**It needs NO lookup table.** Both object routes exist to dodge a per-call materialise, and both pay for
that with a placed table (§14/§15). The scroll route blits **straight out of the `shifted` pre-rotated
playfield the CPU reference already reads** — `rm_scroll_prebuild` built it once per leg. So there is
nothing to place, nothing to flush, and nothing the 1 MB TPA can veto.

### Design

`src/blitter_scroll.c` implements the route; `include/scroll_const.h` is the new ONE home for the scroll
geometry (`OBJ_ROAD_START_OFF`, `SRC_ROW_STRIDE`, …, hoisted out of `scroll.c` — the `blit_const.h` /
`road_const.h` precedent) plus the two seams both routes must run identically:

- **`rm_scroll_advance`** — the per-frame scalar head (the `seg_head * scroll_speed` step, the
  `[0, 0x280)` wrap, `hscroll_step2`). It is **state, not pixels**, and must run exactly ONCE per call on
  either route, so it is a shared `static inline` and each route calls it once.
- **`rm_scroll_seam_row`** — the 4-plane masked wrap blend of one row, shared because the blitter route
  keeps the seam on the CPU.

`src/scroll.c` keeps the byte-exact reference and now exposes it as `rm_scroll_draw(geo, shifted, fb)` —
"draw an already-advanced frame" — with `rm_blit_road_scroll` being head + draw. That split is what lets
the blitter route run the head once and still fall back to *these exact pixels*.

### The recipe — 3 or 4 passes, and one CPU seam

| | A. top fill, EVEN plane-words | A. top fill, ODD plane-words | B. main band copy | B. wrapped tail (edge ≥ 1) |
|---|---|---|---|---|
| HOP / LOP | ONE / **ONE** | ONE / **ZERO** | SRC / SRC | SRC / SRC |
| dst_addr | `fb` | `fb + 2` | band start | band + `main_cols`·8 |
| dst_x_inc / dst_y_inc | 4 / `160 − 39·4` = 4 | same | 2 / `160 − 2(w−1)` | same |
| src_x_inc / src_y_inc | 0 / 0 (unread) | same | 2 / `0x140 − 2(w−1)` | same |
| x_count / y_count | 40 / 84 | 40 / 84 | `w = main_cols·4` / 20 | `w = edge·4` / 20 |
| endmask1/2/3 | all `0xFFFF` | all `0xFFFF` | all `0xFFFF` | all `0xFFFF` |
| skew | 0 | 0 | 0 (both ends column-aligned) | 0 |

Three things make this fall out cleanly:

1. **`ROAD_TOP_FILL` is `0xffff0000`**, which in the ST's interleaved framebuffer is exactly "every EVEN
   plane-word all ones, every ODD plane-word zero" — so the 13,440-byte constant fill is TWO source-less
   passes over the same 84×40 pair grid, one word apart, distinguished only by LOP. With `HOP = ONE` and
   all-ones endmasks the chip needs neither a source nor a destination read. (A `typedef char [...]`
   static assert in `blitter_scroll.c` pins the constant to the recipe: a different pattern would need
   different LOPs.)
2. **Both pitches are constant across the 20 rows**, so the band is ONE blit, not one per row.
3. **`x_count` is never 0.** `edge == 0` wraps no columns, so the wrap pass is SKIPPED rather than
   programmed with a zero width (the chip reads 0 as 65,536). `main_cols ∈ [1, 20]` for all 640 reachable
   scroll positions; a `scroll_blit_serves` tripwire declines anything else to the CPU reference and
   counts it. It is a tripwire on the chip contract, **not** a safe harbour — the only state that trips it
   is an out-of-range position, which the C reference (the original's single-wrap arithmetic, unchanged
   here by design) walks just as badly. What it prevents is handing that state to the *chip*.

**The seam stays on the CPU** (20 rows × 4 words): the blitter cannot compute it — the fraction is a
shift of a *different* source word ORed under a mask. **Ordering** is the one real constraint: the seam
READS framebuffer words the main copy WRITES, so it must run AFTER it. The wrap blit writes columns
`main_cols … main_cols+edge−1` and the seam writes column `main_cols−1` — disjoint — so the wrap may run
either side; it runs before, inside the same excursion. Net: **[fill even, fill odd, main, wrap] in ONE
Supexec, then the seam.** And when `shift == 0` the seam is the identity by construction (mask all ones,
fraction `>> 16` = 0), so the blitter route skips the whole pass rather than rewriting bytes.

**Supexec:** all 3–4 passes share ONE excursion — they are consecutive with no user-mode work between
them, so four traps for one stage would be pure overhead. This is *not* the §7 "one excursion for the
whole object pass" idea, which spans user-mode dispatch work and stays deferred.

**Routing:** a boot-bound `rm_blit_road_scroll_fn`, statically defaulted to the C reference (no NULL
window), bound by `rm_blit_bind_all` alongside the object routes. The seam is an UPPERCASE
`RM_BLIT_ROAD_SCROLL` macro at the sole call site (`src/frame.c`), out of `game.h` — the `object_list.c`
shape. **It is bound FIRST, on the probe result alone**, before table placement can veto: with no table
of its own it cannot be retired by a TPA too small for the object routes' 170 KB, so a 1 MB STE that
loses the object tables still keeps the scroll on the chip. (`rm_blit_bind_all`'s RETURN keeps its old
meaning — the *tabled* routes' binding.)

### Bus policy — the shared-bus restart loop SHIPS; HOG measured and declined

These are screen-sized passes (the fill alone is 6,720 words), not the object blits' tens of
microseconds, so §2's non-HOG restart discipline is the default — and this slice is where it first
shipped. §2's snippet turned out to be **incomplete**: it has no start, so its own first `bset` reports
the pre-start `BUSY = 0` and the loop falls through after one burst. Shipped that way the sweep failed
**640/640** cases with ~63 of 3,360 words written per fill pass. `blit_start_and_wait_shared`
(`blitter.h`) prefixes an explicit `move.b #BUSY` — which also clears the HOG bit a previous
`blit_start_and_wait` left set — and then runs §2's loop. §2 now carries that correction.

Both policies are byte-exact (the sweep is 0-mismatch either way). Measured on the cadence, leg 0:

| bus policy | STE gate (200 idle f) | STE drive (250 f) | canary trips | present cadence |
|---|---:|---:|---:|---|
| shared-bus restart (**ships**) | **99.25 ms** (3,970 ticks) | **90.72 ms** (4,536) | 0 | median 8 / 6 vbl |
| HOG (`GAME_SCROLL_HOG=1`) | 98.22 ms (3,929) | 90.20 ms (4,510) | 0 | median 8 / 6 vbl — identical |

**HOG is 1.03 ms (1.0 %) faster on the gate, 0.52 ms (0.6 %) driving, with no anomaly**: no canary trips,
an identical vblank-span distribution, and no possibility of lost 200 Hz ticks (the whole stage costs
≈4.8 ms on the chip, so no single bus hold can approach the 5 ms tick — the instrument cannot be
under-counting). **We still ship the restart loop.** 1 % of a frame does not buy a ~3 ms whole-CPU freeze
every frame: that freeze delays the 50 Hz sound pump and the IKBD ISR by up to 15 % of a VBL period, it
is the one cost none of our pins can see (the goldens are pixels; the cadence quantises to 20 ms), and
Hatari's bus model is exactly the part of the emulation least like real hardware. The knob stays so the
number is reproducible.

### Pins (all green)

| pin | result |
|---|---|
| sweep | **5,608 cases, 0 mismatch** — the five existing sections + a new **road-scroll section, 640/640 routed** |
| `--mutate 7…10` (new) | **4/4 caught** — odd-fill LOP **640**, main `x_count`+1 **640**, wrap blit skipped **304** (= exactly the `edge ≥ 1` cases), seam before the blits **300** (= exactly the `edge ≥ 0 ∧ shift ≠ 0` cases) |
| `--mutate 1…6` (regression) | 6/6 still caught — 704 / 704 / 643 / 660 / 297 / 1 |
| goldens | same PRG **MATCH ×5 `--machine st`** and **×5 `--machine ste`**, and again at **`--memsize 1`** on both (the slice-10 standing pin) |
| whole-frame A/B st(CPU) vs ste(blitter) | **0-mismatch** ×4 frames — now load-bearing for the scroll route (and the only pin on the dispatch's head-once property) |
| host differential | `make test` **730** |
| cadence, ST | gate **130.30** (was 130.45) / drive **99.40** (was 99.88) — the C reference got *faster*, see below |
| route counters | gate `scroll routed=201 declined=0`; drive `routed=251 declined=0` — the route is live, the tripwire never fires |

**The sweep's new section is EXHAUSTIVE, not sampled**: `hscroll_pos` wraps modulo 640, so 640 cases are
the entire reachable case space — every (shift × coarse column × edge) combination, including `edge = −1`
(no wrap), `edge = 0` (a seam with no wrap columns), `shift = 0` with an edge, and the maximum edge (one
main column left). The playfield is a seeded LCG put through the REAL `rm_scroll_prebuild`, so the 16
pre-rotated copies have the shipping shape, copy 0 raw included. The delta's SIGN alternates case by case
so both wrap branches of the head run, and the whole `ScrollState` is compared after every case.

**Stated limitation:** the sweep's scroll section, like every other, is gated on `blitter_sweep`'s
`tables_bound` — which is the *object* routes' binding. On a machine where the object tables do not place
but the scroll route does, the sweep would report a clean decline and pin nothing. That configuration is
unreachable for the sweep (it pins itself to `--memsize 4`, and CENSUS/SWEEP PRGs are far larger than the
shipping one), so it is documented rather than plumbed.

### Cadence and cost

| scene | ST (CPU, before) | ST (CPU, after) | STE (before) | STE (after) | STE delta |
|---|---:|---:|---:|---:|---:|
| gate (200 idle f) | 130.45 | **130.30** | 105.47 | **99.25** | **−6.22 ms (−5.9 %)** |
| drive (250 f) | 99.88 | **99.40** | 97.34 | **90.72** | **−6.62 ms (−6.8 %)** |

STE vs stock ST is now **gate −23.8 %, drive −8.7 %** (was −19.2 % / −2.1 %). The stage itself goes from
12.06 ms to ≈5.8 ms — the chip does the pixels, the CPU keeps the seam and one Supexec.

**The ST path got faster too, by 0.15–0.48 ms, and that was NOT free.** Splitting `rm_blit_road_scroll`
into head + `rm_scroll_draw` first cost **+13,690 cyc/frame** (12.06 → 13.77 ms on `tools/bench.py`):
across the function boundary GCC stopped strength-reducing `copy_run`'s loop and emitted a
double-indexed `move.l (aN,dI.l),(aM,dI.l)` plus index bookkeeping instead of `move.l (aN)+,(aM)+` —
~17 cyc × 800 longs. Rewriting `copy_run` as an explicit post-increment pointer walk (the shape the top
fill right below it already uses, and for the same reason) recovered all of it and 1,254 cyc more:
**bench `blit_road_scroll` 96,514 → 95,260 cyc (12.06 → 11.91 ms)**. Passing the geometry by pointer vs
by value was measured too and is noise (95,260 vs 95,434).

### Memory

| | before | after |
|---|---:|---:|
| shipping PRG text + data + bss | 707,748 | **708,804** (text 122,368 → 123,392; bss 585,380 → 585,412) |
| resident on a 1 MB machine (+ 256 B basepage) | 708,004 | **709,060** |
| 1 MB STE margin after the 170,432 B of placed tables + the 16 KB stack margin | 10,620 | **9,564** |

**+1,056 B of program, so the §15 watch item's margin drops 10,620 → 9,564 B** — still positive, and
measured live: a `--memsize 1 --machine ste` cadence run reports `free TPA = 184,244` with
`objshift2 hit=240` / `colour table hit=242` / `scroll routed=41`, i.e. both object tables placed AND the
scroll route bound on a 1 MB STE. The margin is now under 10 KB; the next slice that adds text must check
it. Note the new asymmetry in the failure mode: if the margin ever goes negative, the object routes retire
to the CPU but **the scroll route stays on the chip** (it has no table to place).

## 17. C5 slice 2 — the HUD DASHBOARD on the blitter (the fourth route, and the second with no table)

`cell_dashboard` (`include/plane.h`), fired once per frame from `draw_hud`'s phase 7, is the biggest
single thing left in `draw_hud` once the object routes and the road scroll are on the chip. It is also
the most cookie-cut-shaped work in the game after the object engines: 40 rows x 8 groups of
`{mask, ink_a, ink_b, ink_c}`, composited per plane as `(dst & mask) | ink`.

### It needs NO lookup table, and no materialise either

The scroll route (§16) already blits straight out of a buffer the CPU reference reads. This one goes one
step further: **the chip reads the LIVE per-leg art IN PLACE, out of the graphics arena**, because
`ARENA_ROW_STRIDE == SCREEN_ROW_BYTES` — the arena's row pitch and the framebuffer's are the same 160
bytes. Source and destination therefore walk with the same x-step and the same per-row correction, and
the recipe needs no stream, no cache, no invalidation and no RAM at all.

That is not just tidiness. This art is the one asset that **changes under the route**: `init_leg_dash`
rebuilds the whole mini-map between legs, `draw_leg_labels` overlays the place names, and
`probe_collision` mutates ONE word of it MID-LEG as the progress marker walks. The last attempt to
precompute this blit is exactly the `dash_pristine` revert in PERF30 (it composited the transparent
mini-map over a background-less buffer and painted the sky black). Reading in place cannot go stale.

`include/dash_const.h` is the new ONE home for the geometry. It existed in three places before —
`DASHBOARD_DST` as a `hud.c` literal, `DASH_ROWS`/`DASH_GROUPS` in BOTH `plane.h` and `events.c` (which
does not include `plane.h`, so they were genuine independent copies), and the arena row stride only in
`events.c` — and the route depends on all four AGREEING. The header carries a static assert pinning
`ARENA_ROW_STRIDE == SCREEN_ROW_BYTES`, which is the fact the whole recipe rests on.

### The recipe — 8 passes, four AND then four OR

Per group the four source words are `{mask, ink_a, ink_b, ink_c}` and the four destination words are

```
plane 0 = (dst & mask) | ink_a      plane 2 = (dst & mask) | ink_b
plane 1 = (dst & mask) | ink_b      plane 3 = (dst & mask) | ink_c
```

so per plane it is the classic two-pass cookie-cut. Everything except `src_addr`, `dst_addr` and the LOP
is constant across all eight passes:

| | AND pass, plane p | OR pass, plane p |
|---|---|---|
| HOP / LOP | SRC / **AND** | SRC / **OR** |
| src_addr | `art + 0` (the mask word) | `art + {2,4,4,6}[p]` |
| dst_addr | `fb + DASHBOARD_DST + 2p` | same |
| src_x_inc / dst_x_inc | 8 / 8 (one group) | same |
| src_y_inc / dst_y_inc | 104 / 104 (`160 - 7x8`) | same |
| x_count / y_count | 8 groups / 40 rows | same |
| endmask1/2/3 | all `0xFFFF` | all `0xFFFF` |
| skew | 0 (every column is word-aligned) | 0 |

Three things fall out:

1. **Plane p owns byte offset 2p of every group**, so the four planes write DISJOINT destination words.
   No plane can observe another's write; only AND-before-OR *within* a plane is ordered. That is what
   lets the passes be regrouped into two LOP groups (the `blitter_skew.c` argument, §14), which is what
   makes the poke batching worth it.
2. **The middle source word feeds TWO planes** — `ink_b` is planes 1 and 2. This is the one part of the
   mapping that is not a straight per-plane index, and it is the trap below.
3. **Poke batching (§14 shape):** `dash_blit_begin` pokes the four increments, HOP, skew, the three
   endmasks and `x_count` ONCE (the chip reloads `x_count` from an internal latch per line); each group
   pokes one LOP; each pass pokes the two addresses and `y_count`. 36 register writes per composite,
   where `blit_run`'s 17 per pass would be 136.

**The tripwire.** Unlike the scroll route there is no runtime geometry at all — destination, rows, groups
and both pitches are compile-time constants, asserted in the file. The only runtime input is the pair of
base addresses, and the only thing the chip cannot express about them is an ODD one: `src_addr`/`dst_addr`
ignore bit 0, so an odd art pointer would blit from `base-1` while the CPU reference reads the words the
caller meant. `dash_blit_serves` declines that to the C reference and counts it. It is a tripwire on the
chip contract, not a family split: the arena and both screen buffers are word-aligned by construction, so
its counter reading 0 is the expected result. It is not a safe harbour either — the C reference would
take an ADDRESS ERROR on the same pointer (`be16`/`wr16` are raw word accesses).

### The "7-pass refinement" is WRONG, and the sweep is what says so

Planes 1 and 2 take the same ink word, so "blit plane 1, then copy its finished framebuffer column to
plane 2" looks like a free pass — 7 instead of 8. **It is not equivalent.** The two results are
`(bg1 & mask) | ink_b` and `(bg2 & mask) | ink_b`, equal only where `mask == 0` or the two planes'
BACKGROUND words agree. The real background under the dashboard rows is the road top fill, and
`ROAD_TOP_FILL = 0xffff0000` is precisely "plane 1 word `0x0000`, plane 2 word `0xFFFF`" — the worst
possible case for the assumption.

Rather than argue it, the variant ships as sweep mutation `RM_SKEW_MUT_DASH_P2COPY` (14) and is
**CAUGHT on 14 of the section's 16 cases**. The two it does NOT break are the all-opaque atlas
(`mask == 0` everywhere, where the algebra really is background-independent) — which is exactly the
baked art the goldens and `make test` stage, and exactly the trap that shipped the `dash_pristine` bug.
A pin built only on the baked atlas would have blessed a wrong recipe.

*(A second vacuity of the same family was found and fixed while building the section: its first
background was the sweep's uniform `SWEEP_BG_BYTE` fill, under which every plane's background word is
equal and mutation 14 was invisible — 0 of 16 caught on that background. The section now uses a seeded
LCG fill and the real `ROAD_TOP_FILL` pattern, both of which have per-plane asymmetry. Uniform test
backgrounds cannot pin per-plane recipes.)*

### Bus policy — the shared-bus restart loop SHIPS again; HOG measured and declined

Eight screen-width passes over 40 rows is the scroll route's trade, not the object blits', so the default
is §2's shared-bus restart loop. `GAME_DASH_HOG=1` rebuilds it on HOG. Measured, leg 0:

| bus policy | STE gate (200 idle f) | STE drive (250 f) | canary trips |
|---|---:|---:|---:|
| shared-bus restart (**ships**) | **97.75 ms** | **89.80 ms** | 0 |
| HOG (`GAME_DASH_HOG=1`) | 97.22 ms (−0.53, −0.54 %) | 88.98 ms (−0.82, −0.91 %) | 0 |

Same verdict as §16 and for the same reason: half a percent of a frame does not buy a whole-CPU freeze
that delays the 50 Hz sound pump and the IKBD ISR and that no pin can see. The knob stays so the number
is reproducible.

### The sweep's new section — the data IS the case space

The recipe has no case space; the DATA does, because the per-group mask decides per destination word
between a read-modify-write and a plain store, and the CPU reference even takes a different BRANCH for a
fully-opaque group. So the section is art x background:

- **art** — all five legs' REAL art, staged by driving the game's own `rm_init_leg_dash` +
  `rm_draw_leg_labels` into the loaded arena; a marker-STEPPED leg-0 variant (extra label passes, each
  folding one `probe_collision` step); and the two algebraic extremes, an all-opaque atlas and an
  all-transparent one (where the composite must be the identity). 8 variants.
- **background** — seeded LCG noise, and `ROAD_TOP_FILL`. 2.

16 cases, whole screen + overdraw tail compared, guard bands armed BEFORE the art is staged (so a
staging overrun is caught too). Staging real art meant the sweep build now runs `load_assets` before its
entry point and is handed a minimal `RmEventCtx` by `game_main.c` — the shell owns the arena, the sweep
owns the comparison.

**The section carries its own non-vacuity gate.** Every other section generates its inputs in
`blitter_sweep.c`; this one's come from the ASSET FILES through the game's leg-init code, so "the real
art was staged" is an assumption a mis-wired context would satisfy silently — eight identical images,
sixteen byte-exact cases, nothing pinned. The report therefore carries how many DISTINCT arts were
staged (a hash per variant) and the runner fails unless it is 8. That is also the only thing that proves
the marker-stepped variant is a different image from plain leg 0.

### Stated limitations (what these pins do NOT cover)

Named rather than left implicit, per CLAUDE.md's mutation-coverage rule:

- **The tripwire's decline branch is unexercised.** `dash_blit_serves` can only fail on an odd base
  address, and the arena and both screen buffers are word-aligned by construction — no build can reach
  it, and the sweep cannot seed it without mis-aligning its own framebuffers (which would decline all 16
  cases and read as a route regression). `rm_dash_blit_declined` is structurally 0. §16's `x_count`
  tripwire has the same shape; this is the second instance and neither is pinned.
- **The tripwire does not cover 24-bit truncation.** The chip's address registers hold 24 bits, so a
  source above 16 MB (a Falcon running from TT-RAM — `blitter_present()` accepts Falcon) is truncated,
  not declined. True of all four routes; predates this slice and is not fixed here.
- **The BOOT BINDING is proven only by the cadence route counters.** The sweep calls
  `rm_blit_hud_dashboard_draw` directly and the goldens/A-B compare pixels, which are identical either
  way — so deleting `rm_blit_hud_dashboard_bind` from `rm_blit_bind_all` would leave every automated pin
  green and silently give the perf win back. `dash routed=201/251` in the cadence tail is what says the
  route was live; `run_cadence.py` prints it but does not assert it. Same gap as §16's scroll route.

### Pins (all green)

| pin | result |
|---|---|
| sweep | **5,624 cases, 0 mismatch** — the six existing sections + a new **HUD-dashboard section, 16/16 routed, 8/8 distinct arts staged** |
| `--mutate 11…14` (new) | **4/4 caught** — LOP swap **16**, `x_count` 8→9 **16**, `y_inc` 104→96 **16**, plane-2 copy **14** (the 2 misses are the all-opaque atlas, by construction — see above) |
| `--mutate 1…10` (regression) | 10/10 still caught, counts unchanged — 704 / 704 / 643 / 660 / 297 / 1 / 640 / 640 / 304 / 300 |
| goldens | same PRG **MATCH ×5 `--machine st`** and **×5 `--machine ste`**, and again at **`--memsize 1`** on both |
| whole-frame A/B st(CPU) vs ste(blitter) | **0-mismatch** ×4 frames — now load-bearing for the dashboard route |
| host differential | `make test` **730** |
| cycle-exact bench | `draw_hud` **130,120 cyc / 16.27 ms** and `draw_frame` **990,618 / 123.83 ms** — both bit-identical to HEAD, i.e. the constant hoist and the seam cost the CPU reference nothing |
| route counters | gate `dash routed=201 declined=0`; drive `routed=251 declined=0` |
| 1 MB STE | `free TPA = 184,188` with `objshift2 hit` / `colour table hit` / `scroll routed=61` / `dash routed=61` — all FOUR routes bound |

### Cadence and cost

| scene | ST (CPU, before) | ST (CPU, after) | STE (before) | STE (after) | STE delta |
|---|---:|---:|---:|---:|---:|
| gate (200 idle f) | 130.30 | **130.30** | 99.25 | **97.75** | **−1.50 ms (−1.5 %)** |
| drive (250 f) | 99.40 | **99.78** | 90.72 | **89.80** | **−0.92 ms (−1.0 %)** |

STE vs stock ST is now **gate −25.0 %, drive −10.0 %** (was −23.8 % / −8.7 %).

**Two honesty notes on these numbers.**

1. **The saving is well under the pre-slice census's projection.** That census measured the two engines
   in isolation on a staged leg-0 gate frame (CPU 9.18 ms vs blitter-shared 5.08 ms) and projected
   ≈3.3 ms/frame; the whole-frame instrument says **1.50**. Both are same-instrument and reproducible;
   what is NOT established is why they disagree, and the cadence figure is the one the README carries
   because it is the one a player experiences. The route is still a clear GO — it is free of RAM, free of
   invalidation risk, and monotone on both scenes — but "≈3.3 ms" should not be repeated.
2. **The ST drive cell moved +0.38 ms and the ST gate cell did not move at all** (bit-identical, 5,212
   ticks both sides). It is not the seam: the cycle-exact Musashi bench reports `draw_hud` and
   `draw_frame` unchanged to the cycle. The render clock counts whole 200 Hz ticks per frame, so a
   sub-tick per-frame change re-phases some frames across a tick boundary and sums to ±N ticks over 250
   frames; +19 ticks is 0.076 ticks/frame of phase. Reported rather than explained away.

**Harness fix that came with the slice:** `run_cadence.py`'s `VBLS_PER_FRAME_HEADROOM` was 12, which is
not enough for the stock-ST gate cell (200 idle frames at ~130 ms, 10 vblanks/present in the taxed trace
build, plus the boot and leg-select vblanks) — that cell died with "did not produce SCREEN.BIN" until the
headroom went to 16. The published 130.30 was reachable before only by luck of rounding.

### Memory

| | before | after |
|---|---:|---:|
| shipping PRG text + data + bss | 708,804 | **708,820** (text 123,392 unchanged; bss 585,412 → 585,428) |
| resident on a 1 MB machine (+ 256 B basepage) | 709,060 | **709,076** |
| 1 MB STE margin after the 170,432 B of placed tables + the 16 KB stack margin | 9,564 | **9,548** |

**+16 B only** — the route's whole state is two counters and one 8-byte dispatch struct, and its code fit
inside the padding the flat image already carries up to the BSS start (`mkprg.py` pads text to
`bss_start`, so the reported `text` is unchanged even though the ELF's `.text` grew). The §15 watch item
therefore barely moves: 9,548 B of headroom left before a 1 MB STE silently drops its OBJECT routes.
