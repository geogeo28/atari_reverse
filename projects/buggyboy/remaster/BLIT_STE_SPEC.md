# BLIT_STE_SPEC — the STE hardware-blitter build target (PERF30 C4)

A **separate, additive** build of the BuggyBoy remaster (`GAME_STE=1`) that runs the heavy masked
object blits on the Atari STE/Mega-ST **BLiTTER** chip instead of the 68000 RMW loop. The blitter emits
the **same framebuffer bytes** as the CPU engine, so every byte-compare pin still holds — this is a perf
swap, never a pixel change. The stock ST binary is **unchanged** (byte-for-byte, verified by hash).

This document is the driver design + the objshift2 → blitter recipe. Slice 1 (this doc + `src/blitter.c`,
`src/blitter_selftest.c`, the `run_ste_*.py` harness) builds and **proves** the driver; slice 2 wires the
recipe into the live engine.

---

## 1. Build target (slice 1 — landed)

`render/atari/build_game.sh` gains an opt-in profile:

| invocation | output | notes |
|---|---|---|
| `bash build_game.sh` | `BUGGYBOY.PRG` | stock ST — **byte-identical** to before C4 (hash-pinned) |
| `GAME_STE=1 bash build_game.sh` | `BUGGYBST.PRG` | STE build: `-DGAME_STE`, links `src/blitter.c` |
| `GAME_STE=1 GAME_STE_SELFTEST=1 …` | `BUGGYBST.PRG` | + `-DGAME_STE_SELFTEST`, links `src/blitter_selftest.c` |

When `GAME_STE` is unset every added shell variable is empty, so the stock `CFLAGS` / source list / link
line are unchanged. `src/blitter*.c` are excluded from the host `.so` and bench builds in the `Makefile`
(`STE_SRC` filter-out) exactly like the `src/asm/*.S` cores — they poke supervisor-only I/O registers and
never compile for the host differential.

**Presence check + bail.** `main()` (under `#ifdef GAME_STE`) calls `blitter_available()` first: a Supexec
excursion walks the cookie jar (`_p_cookies` @ `0x5A0`). It checks the **`_BLT` cookie first** — TOS
creates it iff blitter hardware is present, so it is authoritative — and on a pre-`_BLT` TOS falls back to
`_MCH` with the machine id ∈ {STE/MegaSTE = 1, Falcon = 3}. This is **not** "id ≥ 1": the **TT030 (id 2)
has no blitter** and must bail, as must a plain ST (0) and a pre-cookie TOS (`0x5A0 == 0`). Anything
without a blitter gets a clean `Cconws` message and exits — never a bus error on the first `0xFFFF8Axx`
poke.

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
| cadence `--machine ste` before/after | `run_cadence.py` | baseline | see §6 |

---

## 6. Cadence finding (slice 2) — the win needs the DATA, not just the blitter

Free-running cadence (`-DGAME_PRESENT_FREERUN`, leg 0 autodrive, 399 presents): stock ST **mean 6.61
vbl**, STE routed **mean 6.65 vbl** — essentially flat (a ~0.6 % regression, within noise). The blitter
path is byte-exact and live, but does **not collapse** the objlist fixed pass at these frames. Why: the
per-blit **materialiser** does the same fine-x shift + mask build the CPU engine does, plus a scratch
round-trip, so it only offloads the framebuffer RMW — a per-BASE-blit win of ~15 % that is (a) swamped at
leg 0, which is not objshift2-base-dense, and (b) partly eaten by the double memory traffic. **The
collapse is a DATA change, not a blitter change:** boot-time pre-shift tables (§3, ~49 KB) remove the
per-frame materialise entirely, leaving 2 blitter passes over static tables — then objshift2 drops toward
the blitter's RMW floor. That is slice 3.

## 7. Slice 3 — what to convert next

1. **Boot pre-shift tables** — build the `(mask, data)` interleaved bitmaps for all 16 fine-x phases from
   the static `arena.gfx` at asset load; the dispatch becomes a table lookup + 2 blit passes (no per-frame
   shift). Re-measure `run_cadence.py` st-vs-ste — this is where the objlist pass should collapse.
2. **Blitter-side clip** — move the LEFT/RIGHT families off the CPU hybrid using endmask1/3, extending the
   sweep to keep them at 0 mismatch.
3. **One-excursion supervisor** — if per-blit Supexec shows on the collapsed profile, wrap the object pass
   in a single excursion (mind the supervisor stack).
4. **Then the colour-indexed `rm_blit_objshift` pass 1** (25.3 % of the gate) — same cookie-cut with the
   4-word `~(A|B|C)&D` mask + colour fill.
