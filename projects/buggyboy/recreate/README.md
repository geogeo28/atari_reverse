# recreate/ — verified human-readable reconstruction of BuggyBoy

This turns the raw Ghidra dump (`../decomp.c`: `DAT_*`, `undefined`, `CONCAT`, register
artifacts) into clean, idiomatic C — and **proves each function still matches the original
68000 code**, byte for byte, with a differential test.

## Why differential testing (not byte-matching)

BuggyBoy was hand-written 68000 assembly, so there is no original C source to recompile and
byte-match against. Instead we prove **behavioral equivalence**: run the real machine code and
the reconstruction on identical input state and diff the results. The emulator is ground truth,
so correctness never rests on a human reading being right.

```
          initial memory image + registers
                     │
        ┌────────────┴─────────────┐
        ▼                          ▼
  ORACLE (real 68k)          CANDIDATE (our C)
  Musashi via liboracle.so   libbuggyboy.so via ctypes
        │                          │
        ▼                          ▼
  final memory + write-set   final memory
        └──────────► diff ◄────────┘   green = byte-for-byte identical
```

## How a function is modeled

Both sides operate on the **same flat, big-endian memory image** whose indices are Ghidra
addresses (the game's globals sit at their real addresses). Each function has:

- a **core** in `src/` — the readable reconstruction, using idiomatic C types;
- a **glue** `g_<name>(image, regs…)` — unpacks the core's inputs from the image at their real
  addresses, calls the core, lets it write back. The glue *is* the function's I/O contract.

The harness diffs the whole image (minus the stack-guard region), so any byte the real code
writes that the reconstruction gets wrong — or misses — fails the test. Leaf tests can opt into
an **attribution pass** (`differential(..., poison=True)`): it re-runs both cores on an image
whose oracle-written bytes are pre-poisoned, so a candidate that *coincidentally* matches (an
output landing in a zeroed region it never actually wrote) is caught rather than passing.

A function that **never returns** (e.g. `_start`, whose call to the infinite game loop never
comes back) is verified at a **checkpoint PC** instead of at `rts`: `emu.run(…, stop_pc=)` /
`differential(…, stop_pc=, exclude=)` run the oracle to that address and diff there. `exclude`
drops a relocated-stack band from the diff (the reconstruction is pure C, with no machine
stack). `_start` is verified this way at its `bsr main` (`0x100d4`). Each `exclude` band is
**vetted** (`_vet_exclude_bands`, against the oracle's deepest stack pointer): it must reach into
the region A7 actually used, and must not drop a named global that sits *below* the stack — so a
band can't silently hide a real divergence. (A named global the relocated stack sits *over*, like
`trace_pc` during `_start`, is legitimately reused as scratch and allowed.)

## Layout

```
include/   machine.h (big-endian accessors)  addrs.h (named addresses)  buggyboy.h (protos)
src/       <subsystem>.c — cores + glue (score.c, …)
oracle/    loader.py (load+relocate PRG)  emu.py (Musashi runner)  shim.c (Musashi callbacks)
           musashi/ (vendored MAME 68000 core — gitignored, refetched on build)
test/      harness.py (differential driver)  test_<subsystem>.py
sound/     sound_player.py (steps REFRESH in the oracle -> WAV)  ym2149.py / sid.py (chip renderers)
Makefile   builds both libs + runs pytest;  STATUS.md tracks per-function progress
```

## Use

```bash
make test           # build oracle + candidate, run the full differential suite
make oracle/build/liboracle.so   # (re)build just the Musashi oracle
```

First build clones + compiles Musashi under `oracle/musashi/`. Requires the venv at `.venv/`
— run `make venv` (or `python -m venv .venv && .venv/bin/pip install -r requirements.txt`) to
create it and install the pinned Python deps (numpy, pyresidfp, pytest). `pip install unicorn`
too if you want it for ad-hoc experiments — the oracle itself doesn't use it.

## Sound rendering

The game's 50 Hz sound driver (`REFRESH` @0x1b086) is verified in the differential suite like any
other function; `sound/sound_player.py` then *listens* to it. It seeds a track (`INITTUNE`) or
effect (`INITFX`), steps `REFRESH` in the oracle one frame at a time capturing the per-frame
YM2149 register writes, and renders that stream to WAV under `../out/sound/` (a gitignored artifact
directory):

```bash
python sound/sound_player.py                          # every tune + effect, YM2149 -> *.wav
python sound/sound_player.py --synth sid --tunes 3    # faithful C64 SID transcode -> *_sid.wav
python sound/sound_player.py --c64 --fx 2             # native-C64 SID -> *_c64.wav
python sound/sound_player.py --c64-sustain 10 --tunes 3 --fx ""   # A/B a flavor -> tune_03_c64s10.wav
```

`ym2149.py` reproduces the ST PSG. `sid.py` replays the same register stream on a C64 SID (via
`pyresidfp`) in one of two modes. `--synth sid` is a clinical port — SID oscillators driven by the
exact per-frame YM volume, no filter. `--c64` instead plays it like a native C64 playroutine: the
SID's own ADSR shapes each note (gated on note events recovered from the register stream), through
a resonant low-pass with a swept pulse width, with one constant velocity gain per note rather than
the ST's per-frame volume. `--c64-sustain N` (0-15, default 6, implies `--c64`) sets that ADSR's
sustain — higher holds the note body fuller, lower is more percussive — and tags each flavor
`*_c64s<N>.wav` so they sit side by side. These renders are listening tools, not part of the
differential contract.

## Screen rendering

Same idea for the picture: `render/render_screen.py` *looks at* a reconstructed screen by running
the candidate `.so` end to end. It loads + relocates the PRG (so fonts, label strings and fill
patterns sit at their real addresses), stages the real `GRAPHICS.GRA` in the game's own buffer
layout, calls the verified `g_unpack_graphics` to decode the graphic tables into `buf_c`, points
`physbase_tbl[0]` at a free screen region, calls the screen function under test (default
`g_draw_leg_results`), then de-interleaves the 32000-byte ST low-res framebuffer to a PNG under
`../out/render/` (a gitignored artifact directory):

```bash
python render/render_screen.py --leg 0              # leg-results screen -> out/render/leg_results_0.png
python render/render_screen.py --screen results     # race-end results screen -> out/render/results_screen_0.png
```

Colours are authentic: the game's results-screen palette (16 ST words at `0x17fc2`, the pointer
`update_highscore` passes to `xbios_setpalette`) is read straight from the image. The one
remaining gap is `buf_a`-sourced text (a couple of per-leg labels + leg-time digits), which
renders blank because the functions that fill it (`update_highscore`/`init_leg`) aren't
reconstructed yet. The fills, panels, labels and dashboard are real. Like the sound renders, this
is a listening tool, not part of the differential contract.

`render/atari/` takes this one step further: it **cross-compiles the same cores to 68000** and runs
them as a GEMDOS `.PRG` under Hatari (real TOS ROM), then checks the on-target framebuffer is
byte-identical to this host render — see [`render/atari/README.md`](render/atari/README.md).

## OS trap model

OS-bound code enters TOS via `trap #N`, which the oracle can't route to real TOS. Instead
`oracle/shim.c` points each trap vector at a magic PC, and on a hit reads the 68000 exception
frame + the GEMDOS/BIOS/XBIOS function number and services the call **deterministically** —
the semantics both the oracle and any reconstructed wrapper must share live in
[`include/os.h`](include/os.h). Calls that only touch hardware or files (Setpalette/Setcolor/
Setscreen, sound, console, Ikbdws) have no image effect and return 0; Physbase/Logbase return
`OS_SCREEN_BASE`; Malloc bump-allocates from `OS_HEAP_BASE`; XBIOS `Supexec` runs the passed
routine in place (its `rts` returns to the caller, its D0 is the result). GEM `trap #2` models
the AES/VDI calls used at start-up (`os_gem_trap`), and GEMDOS `Fopen`/`Fread`/`Fclose` are
modeled by `os_fopen`/`os_fread`/`os_fclose` over an in-image *staged-file* table — the harness
writes the real file bytes into a staging region and one table entry per file, so both sides
serve identical bytes (see `harness.stage_files`).

Anything **not faithfully modeled** — GEMDOS `Super`, an unmodeled GEM/VDI opcode, a file that
wasn't staged, or an unknown function number — is counted, and `emu.run` **raises** rather than
diff a fabricated result. So an OS-bound function can only be marked verified once every OS call
it makes is genuinely modeled. The remaining gap is `Malloc`: it bump-allocates small blocks, so
`main`'s large screen-buffer allocation needs it pointed at a real in-image block first.

Two layers of tests guard this model. `test/test_os.py` drives tiny hand-assembled 68k stubs
through the oracle to pin the shim's semantics at the edges — Malloc bump/rounding, the Fread
cursor/EOF, and rejection of a closed/unstaged handle. `test/test_os_vs_tos.py` then anchors those
semantics to **real hardware**: `oracle/tos_probe.py` assembles a GEMDOS program that runs the same
calls, auto-runs it on a headless Hatari (real TOS ROM, SDL dummy video) with a GEMDOS drive, and
reads the results back from a file. Exact-value calls (Getrez, Fread bytes + counts) must match the
shim to the byte; machine-dependent ones (Malloc's address) are checked as the *invariant* the shim
also honors (even-aligned, non-overlapping, odd size rounded up to even). It skips when Hatari or a
TOS ROM isn't installed.

## Oracle note

The oracle is **Musashi** (kstenerud/Musashi, MAME's 68000 core) — faithful to real 68000
behavior. Unicorn/QEMU's m68k core was tried first and rejected: its ColdFire-derived core
raises spurious illegal-instruction exceptions on byte memory read-modify-write (`addq.b`,
`subq.b`, … to memory), which pervade this code. `emu.py` is the only file that would change
to swap oracles.

Musashi is **cross-validated against a second, independent 68000** — Hatari's WinUAE-derived
core — by `oracle/isa_conformance.py` (run in `test/test_isa_vs_tos.py`). It executes 277
self-contained instruction snippets on both cores and compares the result + defined CCR bits,
covering the classes this code leans on (byte/word/long memory RMW, `asr/lsl/rox`, `ext`,
`muls/divs`, `addx`, `cmp.b`+`Scc`). All 277 agree; the only divergence found was N/Z after a
`DIVS/DIVU` overflow, which the 68000 PRM leaves *undefined* (excluded from the comparison). So
"verified against Musashi" is, for BuggyBoy's instruction mix, "verified against a real 68000".