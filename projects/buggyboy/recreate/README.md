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
writes that the reconstruction gets wrong — or misses — fails the test.

A function that **never returns** (e.g. `_start`, whose call to the infinite game loop never
comes back) is verified at a **checkpoint PC** instead of at `rts`: `emu.run(…, stop_pc=)` /
`differential(…, stop_pc=, exclude=)` run the oracle to that address and diff there. `exclude`
drops a relocated-stack band from the diff (the reconstruction is pure C, with no machine
stack). `_start` is verified this way at its `bsr main` (`0x100d4`).

## Layout

```
include/   machine.h (big-endian accessors)  addrs.h (named addresses)  buggyboy.h (protos)
src/       <subsystem>.c — cores + glue (score.c, …)
oracle/    loader.py (load+relocate PRG)  emu.py (Musashi runner)  shim.c (Musashi callbacks)
           musashi/ (vendored MAME 68000 core — gitignored, refetched on build)
test/      harness.py (differential driver)  test_<subsystem>.py
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