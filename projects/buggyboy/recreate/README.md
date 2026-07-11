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
(`python -m venv .venv && .venv/bin/pip install unicorn pytest` — Unicorn is unused by the
oracle but kept for ad-hoc experiments).

## Oracle note

The oracle is **Musashi** (kstenerud/Musashi, MAME's 68000 core) — faithful to real 68000
behavior. Unicorn/QEMU's m68k core was tried first and rejected: its ColdFire-derived core
raises spurious illegal-instruction exceptions on byte memory read-modify-write (`addq.b`,
`subq.b`, … to memory), which pervade this code. `emu.py` is the only file that would change
to swap oracles.