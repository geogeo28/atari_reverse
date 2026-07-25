# BLIT_STE_SPEC — the unified ST/STE hardware-blitter binary (PERF30 C4)

**ONE `BUGGYBOY.PRG` runs on both a plain ST and an STE**, using the Atari STE/Mega-ST **BLiTTER** chip
for the heavy masked object blits when present and the 68000 RMW engine when not. The blitter emits the
**same framebuffer bytes** as the CPU engine, so every byte-compare pin holds — a perf swap, never a pixel
change. (Slices 1-5 built and proved this as a *separate* `GAME_STE` binary; **slice 6 unified it** into
the shipping PRG — that framing supersedes the "separate binary" language below where they conflict; see
§11.)

This document is the driver design + the objshift2 → blitter recipe + the census that bounded the colour
engine. Historical slice tags (1-5) are kept for provenance.

---

## 1. Build (slice 6 — the unified binary)

`render/atari/build_game.sh` builds the shipping `BUGGYBOY.PRG` with the blitter path **always linked**
(`-DRM_BLITTER`; `src/blitter.c` + `src/blitter_objshift2.c` + `src/blitter_objshift.c`), bound at boot:

| invocation | output | notes |
|---|---|---|
| `bash build_game.sh` | `BUGGYBOY.PRG` | **unified** — blitter on an STE, CPU asm on an ST/TT (bound at boot) |
| `GAME_FORCE_NO_BLITTER=1 …` | `BUGGYBOY.PRG` | pins the CPU path even on an STE — a harness A/B baseline knob |
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

1. **Blitter-side clip (LEFT/RIGHT) — GO, now unblocked.** In slice 2 moving clip to the blitter would
   have added materialise cost; the cache removes that objection (clip sprites cache too). Fold the 1008
   currently-declined clip cases in via `endmask1/3` partial columns, extend the sweep to keep them 0-XOR.
   Keep any case the endmask can't reproduce on the CPU hybrid.
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

**The driving win needs the DATA, not the engine: boot pre-shift tables.** Eliminating the per-frame
materialise (precompute the `(mask,data)` phases from the static `arena.gfx` at load) is the ONLY way the
colour engine wins driving — the same conclusion slice 3 reached, now the binding constraint. This is the
deferred sprite-layout work (§3's A2 note): the pre-shift crosses cell boundaries, so it must key on the
sprite/subcell structure (`OBJSH2P_SUBCELL_S`), not a flat arena sweep.

**Combined RAM (both caches, STE build):** objshift2 `128 × ~2.75 KB ≈ 356 KB` + objshift `96 ×
~2.05 KB ≈ 197 KB` = **~553 KB** static BSS. Fits a 1 MB STE (the honest minimum) with headroom; a 512 KB
STE needs both slot counts roughly halved (~277 KB). The colour cache is unused while it stays on the CPU
path, so a shipping build that never opts it in can drop it — but it is kept compiled so the sweep pins it.

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
item, not a landing.

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
