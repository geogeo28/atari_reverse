# Joust — differential reconstruction

Readable C for Joust (Atari ST, Gamex release), each function **proven byte-for-byte equivalent to
the original 68000 code**. This is the *recreate* track: faithfulness beats correctness every time,
so original bugs are reproduced rather than fixed.

The machinery is shared — [`tools/recreate_kit`](../../../tools/recreate_kit/README.md) loads the
`.PRG` into a flat image, runs the original under a Musashi 68000 oracle and this project's
compiled C on the same image, and diffs the result. Everything game-specific lives here. For *why*
the method is differential rather than byte-matching, read the worked reference project,
[`projects/buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md).

Progress and per-function verification notes: [`STATUS.md`](STATUS.md).

```
project.toml      binds this directory to the kit (paths, load base, image size)
Makefile          three lines: KIT + GAME + include $(KIT)/kit.mk
include/addrs.h   the globals MORE THAN ONE subsystem touches, by Ghidra address (mirrors ../names.txt)
include/joust.h   public prototypes + what several subsystems share: screen geometry, the 68000
                  primitives (loop_passes, lsr32/ror32, divu_w) and the object record
include/<sys>.h   one per subsystem (draw.h, object.h, …): only what that layer alone touches —
                  a constant earns its way into addrs.h/joust.h when a SECOND layer needs it, and
                  is never spelled out in two headers (no translation unit includes both, so a
                  drifted copy would compile silently; the test_*.py mirror pins scrape by header)
src/*.c           one file per subsystem: the readable core plus its `g_<name>` glue
                  (the kit also links its own src/*.c into the candidate — the Dosound ledger)
test/harness.py   the kit-binding shim
test/abi.py       how each of Joust's calling conventions is driven under the oracle
test/test_*.py    the differential batteries
```

## Running

```bash
make venv      # once: .venv + pytest/pytest-xdist (see requirements.txt)
make test      # build the candidate + the shared oracle, run the suite across cores
make oracle    # rebuild only the shared Musashi oracle
make clean     # this project's build/ only — the oracle is shared, see the kit README
```

## Calling conventions, and why `test/abi.py` exists

BuggyBoy is hand-written assembly and passes everything in registers. Joust is compiled C: most of
its routines take arguments on the **caller's stack** (`4(a7)`, `8(a7)`, …) and write their results
back into that same block. The oracle starts a function with A7 at the top of the image, and the
differential deliberately stops comparing there — the C reconstruction has no machine stack to
match — so a frame built at A7 would be invisible to the diff.

`test/abi.py` fixes that by poking a two-instruction 68000 stub into free image space and entering
the oracle there:

```
movea.l #ARG_BLOCK-4, a7      ; the argument block now lives in ordinary, diffed memory
jmp     <routine>             ; its rts pops a sentinel pre-poked into the slot below
```

Pre-poking the return slot instead of using `jsr` means the oracle makes **no stack write at all**,
so every byte it writes is the routine's own output. A second variant handles register-argument
routines whose results land in D1/D2 (which an image diff cannot see): it `jsr`s the routine and
stores D1/D2 through A0 with the same `move.l d1,(a0)+ / move.l d2,(a0)+` pair the game itself
uses. The candidate glue mirrors that store, so both sides are compared on identical bytes.

### A glue may refuse a call the original makes

Glue is normally a bare forwarder, but the oracle's instruction cap has no candidate-side
counterpart: a reconstructed routine that spins for ever hangs a pytest worker with **no output at
all** under `-n auto`, which is the one failure the differential cannot report. So a glue in front
of an unbounded spin may add a guard the original has no trace of, and report the refusal through
its own return code rather than through the routine's result. `g_pause_until_key`
(`src/input.c`) is the worked instance, with `_pause_glue` in `test/test_input.py` putting a
wall-clock deadline on every candidate-side entry into the spin as the second layer. The
reconstructed function itself stays uncapped and faithful — the guard lives in the glue precisely
so that it does.

## `project.toml` — the heap waiver

Joust's data segment runs to `0x2b7ae`, which covers the kit's modeled Malloc heap
(`OS_HEAP_BASE = 0x20000`). That is why `project.toml` sets `tos_malloc_unused = true`. The
evidence is an exhaustive **byte scan** of text+data (there is no bss) — deliberately not a grep of
a disassembly listing, whose linear sweep drops trap sites after desyncing on data:

- 22 `trap #1` (`4e41`) sites exist, and every one is immediately preceded by an in-line
  `3f3c <sel>` selector immediate. No selector is ever loaded through a register.
- Those selectors are `0x19 0x20 0x3c 0x3d 0x3e 0x3f 0x40 0x4c` — **no `Malloc` (0x48), no
  `Mshrink` (0x4a)**. The Gamex loader does the memory setup before the game runs.
- The byte pattern `3f 3c 00 48` / `3f 3c 00 4a` occurs nowhere in the image at any alignment.

So no modeled allocation can ever be handed out on top of the program. Two guards back the
declaration up rather than trusting it: `harness._vet_os_memory_map()` refuses the overlap at
import unless the flag is set, and `emu._vet_no_malloc_over_program()` fails **every run** in which
the oracle actually serves a `Malloc` — because there both sides would scribble the same bytes over
the same program area and the diff would come back clean while proving nothing. The second sits in
`emu.run()` (not in `differential()`) so oracle-only runs are covered too, and counts serviced
`Malloc` traps rather than watching the bump pointer — `Malloc(-1)`, the "largest free block?"
query, is served without moving it. `test/test_heap_guard.py` pins both.

For the general lesson — why a trap census must be a byte scan — see `docs/m68k-disassembly.md`.
Joust's own dropped site is the `Bconstat` at image `0x11c2c`, which the desynced listing renders
as `ori.b #$4e4d,d1`.

## Staged files — an honesty note

Joust reads two files at startup:

- `HIGH.SCO` (26 bytes) — present in `../bin/`, authentic.
- `JOUST.MUR` (0x7d00 bytes, read straight over the program's own data segment at `0x23aae`) —
  **not shipped**. Despite the extension it is the **title picture**, not music: 0x7d00 = 32000
  bytes = one whole low-res framebuffer, and `title_screen` copies exactly that buffer to
  `screen_base`. Better still, **its loader is patched out** — `init_system` has a `bra.s` at
  `0x10224` jumping over it (and another at `0x10204` over a raw-floppy loader), so the Gamex
  release loads no external file but `HIGH.SCO` and runs on the placeholder picture the PRG
  carries. Staging that placeholder is not a compromise — it is what the shipped game does.

No test in the suite stages either file yet. When the startup path is reconstructed, the intended
stand-in for `JOUST.MUR` is the PRG's *own* data segment (`img[0x23aae : 0x23aae + 0x7d00]`) — the
differential only requires that both sides see identical staged bytes, not that the bytes are the
real music. That stand-in must never be described as authentic music data.

## The TOS traps Joust needs

The kit's shim originally covered only what BuggyBoy needed. The seven Joust also traps — `Super`,
`Giaccess`, `Fcreate`, `Fwrite`, `Random`, `Bconstat`, `Bconin` — are now modelled kit-wide;
`tools/recreate_kit/TRAP_MODEL.md` records what each one does and, per trap, what it deliberately
does **not** capture. `test/test_os_traps.py` pins the semantics with hand-assembled 68000 stubs.
Read the "not captured" notes before reconstructing a trap-bound function: two of them bound what
can be verified at all — a run delivers at most one console keystroke, and the whole program
executes in supervisor mode, so Joust's floppy routine never takes its user-mode `Super` path.

**The raw-floppy routine at `0x152dc` is unverifiable, not merely pending — leave it off the
reconstruction list.** The `Super` limitation above is the weaker one. The routine also reads the
PSG select port directly (`move.b $ff8800,d1` at `0x15544`), and the kit rejects **any** direct PSG
read on its own: the ledger records writes only, so there is nothing correct to return. That
rejection does not depend on the mixed-path guard, so *no* `emu.run` reaching that instruction can
go green, whatever else the run does. It is blocked on the oracle gaining a real PSG read model, not
on someone writing the C. Do not "fix" a rejection by narrowing either guard — that restores the
fabricated `0` read they exist to prevent (`tools/recreate_kit/TRAP_MODEL.md`, Phase 3).

The XBIOS `Dosound` ledger the harness compares off-image sound against (Joust has four `Dosound`
sites) is kit-wide — `tools/recreate_kit/src/dosound_log.c`, linked into every candidate.
`Giaccess`, by contrast, needs no ledger: it reads and writes an in-image register file, so the
differential covers it directly.
