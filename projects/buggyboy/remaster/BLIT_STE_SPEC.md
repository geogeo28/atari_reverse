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

### 3b. Fine-x (skew) mapping — **DESIGN** (slice 2)

For `fine_x != 0` the engine places the 16-px source word at pixel offset `fine_x`, straddling col0 (high
bits) and col1 (low bits). The blitter's **SKEW** shifts the source right by `skew` bits into the dst word
grid, so `skew = fine_x` reproduces the straddle, and the blit spans `straddle + 1` dst columns
(`x_count = straddle + 1`). **FXSR** primes the shifter at line start (the leftmost dst word is formed from
the first source word's high bits); the trailing dst word is formed from the last source word's low bits.
The exact `FXSR`/`NFSR` + `endmask1`/`endmask3` values for the partial straddle edges must be **pinned by
extending the self-test to sweep `fine_x` 1..15** before the engine is switched over — this is the first
slice-2 task. The mask/data bitmaps are materialised per fine-x phase (§3), so the shift is a table read,
not a runtime barrel.

### 3c. Clip / edge families

The base family (on-screen, no clip) needs no edge masking (`endmask = 0xFFFF`; bitmap zeros carry
transparency). The LEFT/RIGHT clip families (`col < 0` / `col ≥ bound`) map to the blitter's `endmask1` /
`endmask3` partial-column masks + an adjusted `dst_addr`/`x_count`, replacing the CPU's ladder. **Fallback:
any clip case the endmask cannot reproduce byte-exactly stays on the CPU path (a pinned hybrid)** rather
than shipping approximate pixels — the dispatch already branches on family, so a per-family CPU/blitter
choice is cheap.

---

## 4. Pins (what proves the STE build)

Musashi cannot emulate the blitter, so the pins are Hatari-based (weaker instruction-level pinning than the
host Musashi differentials, compensated by whole-frame byte equality over a real drive):

| pin | script | slice 1 result |
|---|---|---|
| stock .PRG byte-identical with flag off | `shasum` | **PASS** (unchanged) |
| stock goldens ×5 on `--machine st` | `run_golden.py` | **MATCH ×5** |
| STE build goldens ×5 on `--machine ste` | `run_ste_golden.py` | **MATCH ×5** |
| blitter == `rm_blit_objshift2` (aligned) | `run_ste_selftest.py` | **0/32000** |
| whole-frame A/B (stock-ST vs STE) over the drive | `run_ste_ab.py` | **0-mismatch** |
| host differential suite | `make test` | **708 passed** |
| cadence instrument on `--machine ste` | `run_cadence.py` | works; STE == stock baseline |

The A/B differential (`run_ste_ab.py`) is 0 by construction in slice 1 (objshift2 is still on the CPU in
both builds); it becomes the **load-bearing byte-exactness gate** the moment slice 2 routes objshift2
through the blitter.

---

## 5. Slice 2 — what to convert next

1. **Pin the skew** — extend `blitter_selftest.c` to sweep `fine_x` 1..15 (and each width_idx / clip
   family), calibrating `skew`/`FXSR`/`NFSR`/endmasks against the real engine, all-zero XOR.
2. **Build the A2 mask/data phase tables** once at asset load from the static `arena.gfx` (~49 KB masks).
3. **Route `RM_BLIT_OBJSHIFT2`** (the `objshift2_glue` family in `src/object_list.c`) to a blitter path
   under `GAME_STE`, running the object pass in supervisor; keep any un-pinnable clip case on the CPU
   (hybrid). Gate every frame with `run_ste_ab.py` + `run_ste_golden.py`.
4. **Measure** the cadence delta on `--machine ste` (objlist fixed pass is 27.6% of the gate frame). Then
   slice 3: the colour-indexed `rm_blit_objshift` pass 1 (25.3%), same recipe with the 4-word
   `~(A|B|C)&D` mask + colour fill.
