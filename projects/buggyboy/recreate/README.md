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
addresses (the game's globals sit at their real addresses). Multi-byte access goes through the
`be16`/`be32`/`wr16`/`wr32` accessors in `include/machine.h`, which preserve the 68000's big-endian
order; on the little-endian test host they assemble each word byte-by-byte, and on a big-endian
target (the m68k PRG in `render/atari/`) they compile to native aligned loads — see that
directory's README "Performance" note. Each function has:

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
           road_bands.h (shared render_road pipeline + 68k primitives, used by both road layers)
src/       <subsystem>.c — cores + glue (score.c, …)
src/machine/  byte-exact 1:1 machine-model transcriptions kept as trust anchors (road.c)
oracle/    loader.py (load+relocate PRG)  emu.py (Musashi runner)  shim.c (Musashi callbacks)
           musashi/ (vendored MAME 68000 core — gitignored, refetched on build)
test/      harness.py (differential driver)  test_<subsystem>.py
sound/     sound_player.py (steps REFRESH in the oracle -> WAV)  ym2149.py / sid.py (chip renderers)
Makefile   builds both libs + runs pytest;  STATUS.md tracks per-function progress
```

## Two reconstruction layers

Most functions have a single readable reconstruction in `src/`. A few dense, hand-written 68000
routines (e.g. `render_road`, the pseudo-3D rasterizer) additionally keep a **byte-exact machine
model** — a literal register/`goto` transcription — under `src/machine/`, as a second, independently
verified transcription (the *trust anchor*). The readable idiomatic version in `src/` is the
**default** the game links (`g_render_road`); the anchor is exposed under a `_machine` suffix
(`g_render_road_machine`). Both are diffed against the Musashi oracle by the same fuzz battery, so
they cannot silently drift apart. Shared scaffolding (the band pipeline, the 68k word/blit
primitives) lives in `include/road_bands.h` so there is one source of truth for the parts that are
genuinely common.

## Use

```bash
make test           # build oracle + candidate, run the full differential suite
make oracle/build/liboracle.so   # (re)build just the Musashi oracle
```

First build clones + compiles Musashi under `oracle/musashi/`. Requires the venv at `.venv/`
— run `make venv` (or `python -m venv .venv && .venv/bin/pip install -r requirements.txt`) to
create it and install the pinned Python deps (numpy, pyresidfp, pytest, pytest-xdist). `pip install unicorn`
too if you want it for ad-hoc experiments — the oracle itself doesn't use it.

`make test` runs the suite in parallel across cores with `pytest-xdist` (`-n auto`). Each test
stages its own in-memory image and drives the `.so` via ctypes, so xdist workers (separate
processes) never collide. Override the parallelism with `PYTEST_ARGS`:

```bash
make test PYTEST_ARGS=-n0                 # serial (e.g. to read a traceback cleanly)
make test 'PYTEST_ARGS=-n4 -k objshift'   # 4 workers, one subsystem
```

### Writing a fuzz test so it parallelizes

A single `test_fuzz` that loops thousands of iterations is **one** test item — xdist can't split
it across workers, so it becomes the wall-clock floor. Shard it by splitting *case generation* from
*checking*: a generator yields `(i, params…)` from the one seeded RNG, and a `chunk`-parametrized
test runs only the iterations where `i % FUZZ_CHUNKS == chunk`. Every worker replays the full RNG
stream (microseconds) but runs the expensive differential on its slice only — coverage is **byte-identical**
to the un-sharded loop (the round-robin is an exact partition of the iteration range):

```python
FUZZ_CHUNKS = 8   # module-level, per test file (matches the per-file constant style)

def _fuzz_cases():
    rng = random.Random(0xB117)          # seeded ONCE — the shared stream must not be re-seeded per chunk
    for i in range(4000):
        ... = rng.randrange(...)         # draw all inputs in the original order
        yield i, x, color, rows_m1

@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz(chunk):
    for i, x, color, rows_m1 in _fuzz_cases():
        if i % FUZZ_CHUNKS != chunk:
            continue
        _check(seed=i, x=x, color=color, rows_m1=rows_m1)
```

Re-seeding per chunk (`Random(seed + chunk)`) would be simpler but **changes the inputs tested** —
don't. A deterministic nested-loop test (no RNG) shards even more simply: parametrize over the
outer loop variable (e.g. `@pytest.mark.parametrize("fine_x", FINE_X_ALL)`). Rule of thumb: shard
any test whose serial time approaches the current slowest item so no single item gates the run.


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
python render/render_screen.py --screen highscore   # populated high-score table -> out/render/highscore_screen_0.png
python render/render_screen.py --screen intermission # scrolling between-legs screen -> out/render/intermission_screen.png
python render/render_screen.py --screen buggy       # player car (rear view, at rest) -> out/render/buggy.png
python render/render_screen.py --screen map --leg 2 # per-leg track map + progress arrow -> out/render/legmap_2.png
```

The `buggy` and `map` screens are drawn from real gameplay data with no `game_update` needed: the
car sprite (`g_draw_buggy` + `_hi`/`_lo`/wheels) comes from the unpacked graphics, and the track map
(`g_init_leg_dash` + `g_draw_dashboard`) is built per-leg from **COURSES.DAT** — each leg a distinct
course outline. They use the per-leg scenery palette (`0x17f7e`) with index 0 (the scenery "empty"
fill) forced to black so the sprite/map reads on a clean background. Only the at-rest buggy pose is
rendered (non-game pose values can index the sprite tables outside the staged buffers).

Colours and text are authentic: the game's results-screen palette (16 ST words at `0x17fc2`) is
read straight from the image, and the per-leg labels/digits are the real strings from
**COURSES.DAT** (staged at `mem_base`, where `buf_a = mem_base + 0x1900` points). The results
screen's SCORE/NAME rows come from the *runtime* `highscore_table` (`0x18266`, ships all-zero),
which `update_highscore` fills — so `--screen results` shows them blank, while `--screen highscore`
builds the game's default table with the verified `g_init_scoretable` and ranks a demo player record
into it with `g_update_highscore` before drawing (only the single player record is demo data — the
table is the game's own). Everything else is
drawn from static data or the two data files. Like the sound renders, this is a listening tool, not
part of the differential contract.

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

## Harness gaps (off-image effects)

The differential is a **whole-image** comparison, so any effect that lands *outside* the image is
invisible to it. OS/hardware calls with "no image effect" (Setpalette, Setcolor, the direct
`$ffff82xx` colour-register pokes, Dosound) return 0 and write nothing the diff sees — so the oracle
verifies *that* they were called, never *which palette/value* was loaded. This is a real blind spot:
the leg-0 tunnel bug was `game_update`'s sprite-mode-4 loading the `0x17fb0` scratch instead of the
`0x17fa2` race palette (the original `suba #$18,a0`-rewinds A0 before the trap) — byte-clean under
`make test`, wrong on hardware. It was only found by diffing Hatari **memory snapshots** (recon vs
original: identical game state, but the recon's hardware palette held the +7-shifted scratch). See
the [`buggyboy-off-image-palette-debugging`] memory note and the `game_update` STATUS row.

The durable fix is to give these calls **capture ledgers** like the sound path already has
(`emu.psg_writes()`, the Dosound arg ledger) and assert on them:
- Capture XBIOS Setpalette (fn 6) / Setcolor (fn 7) in `oracle/shim.c` — the source pointer + the
  16 loaded words — into an ordered ledger exposed like `psg_writes()`.
- Mask `m68k_write_memory_16`/`_32` to the 24-bit bus the way `m68k_write_memory_8` already does
  (they currently drop `$ffffxxxx` word/long writes instead of aliasing them to `$ffxxxx`), so the
  mode-6 `$ffff824c` colour poke lands at `$ff824c` and is logged.
- Have the reconstruction's `g_xbios_setpalette` / `g_poke_color_reg` seams record the same, and
  add a ledger-diff test over the real course — companion to `test_game_update_real_course.py`,
  which only guards the *image* side. That closes the bug class whole-image diffing can't see.

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