# Zynaps reconstruction — how this project binds to the kit

Human-readable C for Zynaps (Hewson, 1988), each function **verified byte-for-byte against the
original 68000 code**. All the machinery is the shared harness in
[`tools/recreate_kit`](../../../tools/recreate_kit): a Musashi oracle runs the real code and the
compiled reconstruction runs on a copy of the same flat memory image, and the two images are
diffed. Why differential testing rather than byte-matching, and what the harness can and cannot
see, is written up once in [`../../buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md)
— the reference implementation. This file says what is specific to Zynaps, and
[`STATUS.md`](STATUS.md) is the per-function ledger.

## Binding

`project.toml` is the whole binding:

| key | value | why |
|---|---|---|
| `prg` | `../bin/ZYNAPS17.PRG` | plain unpacked 68000: text 0x9f46, no data, bss 0x54a28, 1506 relocs |
| `load_base` | `0x10000` | the workspace default; `../names.txt` addresses are Ghidra addresses at this base |
| `image_size` | `0x100000` | must equal `os.h`'s `OS_IMAGE_SIZE`; the program ends at `0x6e96e` |
| `tos_malloc_unused` | `true` | the bss covers the model's Malloc heap at `0x20000`, and the game issues no `Malloc` |

The **target** build does not use `image_size`: it has its own, smaller `ZY_TARGET_IMAGE_BYTES` —
see `atari/README.md`'s "Memory".

The waiver's evidence lives in `project.toml` and its run-time half is exercised by
`test/test_heap_guard.py`. The two other fixed regions need no waiver: the staged-file table
(`0xbf000`) sits above the program, and the harness-poked input block (`0x600`) below `load_base`.

**Free image space is not simply "above the program".** Zynaps hard-codes its two framebuffers at
absolute RAM — `screen_back` 0x70300 and `screen_front` 0x78000, together `[0x70300, 0x7fd00)` —
rather than allocating them, so there is a 63 KB hole in the middle of the apparently free space
that belongs to the game. `test/abi.py` parks its stub and scratch buffers clear of both, and
`test/test_constants.py` pins that.

## Names

`../names.txt` is the source of truth, and it names all 195 functions. **It is not uniformly
certain**: 19 of the 195 `fn` lines and 86 of the 280 `var` lines carry a trailing `# ctx`, meaning
the name was inferred from call context rather than confirmed from a body read end to end. Never
invent a name here and never rename one there.

**Using a `# ctx` name in C obliges a comment saying so**, next to the declaration, so a reader
knows the name is a proposal that a later body read may overturn — and so that renaming it later is
a search rather than an archaeology. `include/entity.h` does this per record field with an explicit
provenance tag on each.

## Layout

```
recreate/
├── project.toml     the binding above
├── Makefile         two lines: KIT + GAME, then `include $(KIT)/kit.mk`
├── include/<subsystem>.h   one per subsystem: its prototypes, addresses and record layout
├── src/<subsystem>.c       each core plus its `g_<name>` glue
├── src/asm/*.S             ASM TWINS: the original's own instructions for the hottest cores,
│                           linked instead of the C on the target build — src/asm/README.md
├── test/
│   ├── harness.py   16-line shim: binds the kit and star-re-exports it
│   ├── abi.py       the 68000 stub that stores register-only answers into diffed memory
│   ├── test_constants.py   the CLAUDE.md §5 pin and the duplicate checks — a collector
│   ├── test_status.py      STATUS.md's counts against its rows
│   ├── test_heap_guard.py  the run-time half of the `tos_malloc_unused` waiver
│   ├── asm_twins.py        the four checks every twin suite runs, shared
│   ├── test_asm_<path>.py  the asm twins against the C cores they replace, byte-exact
│   └── test_<subsystem>.py one differential battery per subsystem
├── atari/           THE CORES ON A REAL 68000 — see atari/README.md
└── STATUS.md        the per-function ledger, in per-subsystem sections
```

There is no `addrs.h` and no `zynaps.h`. The 68000 primitives every core shares (`loop_passes` and
its count masks, the 16- and 32-bit rotates, `word_sub`, `sign_ext16`, `addr_add`, the big-endian
accessors) all live in the kit's `machine.h`; a project-local copy of any of them is a bug.

`src/sound.c` is the only core whose answers are registers rather than memory (A1 and D1), so its
test enters the oracle at a poked stub — `test/abi.py` — which `jsr`s the routine and stores those
registers where the image diff can see them.

**`src/asm/` is a target-side substitution, not a second reconstruction.** Each `.S` transcribes the
ORIGINAL binary's instruction sequence for one core and carries that core's C signature; the C stays
compiled and stays the reference, and `test/test_asm_<path>.py` proves each twin byte-equal to it
over the whole image. The scroll path, the two sprite blitters and the score panel with its character
blitter are transcribed, and so is the frame loop's LAST SLICE (`frame.S`, the first twin here that
CALLS — it reaches sixteen verified C cores through the kit's callback door off target, and the real
cores on target) — 29 twins over six `.S` files. `make test` builds them first (the kit's
`$(ASM_BIN)` rule) and runs both directions.
[`src/asm/README.md`](src/asm/README.md) is the recipe for adding one.

## Adding a function

This project is worked by **several agents at once**, each owning a set of subsystems. The layout
is arranged so that adding a function touches only files your subsystem owns.

| file | who edits it |
|---|---|
| `src/<yours>.c`, `include/<yours>.h`, `test/test_<yours>.py` | **you alone** |
| `STATUS.md`, your `## Verified — <yours> (N)` section and its count | **you alone** |
| `include/<someone else's>.h` | **nobody but its owner** — include it to READ a global, never edit it |
| `test/test_constants.py`, `test/test_status.py`, `Makefile`, `project.toml`, `test/harness.py` | **nobody**, in normal work |
| `test/abi.py` | shared, append-only — only if you need a new stub shape |

Two conventions carry that:

- **A global lives in the header of the subsystem that owns the data** (`../out/globals.tsv` says
  which that is). Any subsystem may `#include` another's header to read it. There is no promotion
  protocol and no shared address file, because both would make a routine edit somebody else's file.
  `test_constants.py` refuses a constant defined in two files and an address under two `A_*` names,
  which is what a C compiler cannot do here — no translation unit includes every header.
- **`include/entity.h`'s record block is FROZEN, not append-only.** The naming pass already
  recovered the whole 0x2c-byte record, so every field is transcribed with a provenance tag
  (`pinned by <test>` or `names.txt, unpinned`). Nobody adds a field; you upgrade a tag in the
  change that ports a routine using it. "Append-only in offset order" was the earlier rule and it
  was self-contradictory — inserting at an offset is not appending.

The steps:

1. Read the routine in `../out/prg_dis.txt` **from a known function start** — a `bsr`/`jsr` target
   from an anchored caller. A linear sweep desyncs on data, so a body read from the middle of the
   listing is not evidence (`docs/m68k-disassembly.md`).
2. Write the core in `src/<subsystem>.c` with the names.txt name, plus its glue `g_<name>`. The core
   carries no raw register names; the register→role map is a one-line comment in the glue. Name
   every non-trivial literal. **The glue must call the core**, not recompute its answer — a glue
   that duplicates the logic leaves the core untested and the suite green.
3. Put addresses, record fields and the prototype in `include/<subsystem>.h`.
4. Add edge + fuzz cases in `test/test_<subsystem>.py`, sharding the fuzz by `chunk` so `-n auto`
   spreads it. Declare the battery's `MIRRORS` and `ENTRY_PROLOGUES` at the bottom of that file;
   `test_constants.py` fails by name if a battery has neither.
5. `rm -f build/*.so && make test` — green is the bar, not "looks right". Run `make guarded` too if
   the function indexes the image with an address it computed.
6. Mutate a constant, rebuild, confirm the suite goes red, revert. **Only from a green baseline**: a
   suite with one unrelated failing test reports every mutant as killed. A survivor is either a
   missing case or a genuinely unreachable arm — record which in STATUS.md, never both.
7. Append your STATUS.md row, update your section's count, and say what the verification covered.

## Running it

```bash
cd projects/zynaps/recreate
make venv                        # the kit's rule: python -m venv .venv + requirements.txt
rm -f build/*.so && make test    # rebuild both libs, assemble src/asm/*.S, run the suite (-n auto)
make asm                         # (re)assemble just the asm twins -> build/asm/twins.{elf,bin}
make guarded                     # the same suite over a PROT_NONE-bounded image (Darwin/BSD only)
```

`.venv` here was built with `--system-site-packages` over the workspace's `atari_reverse` conda
interpreter, exactly as Joust's was, so pytest and pytest-xdist resolve out of that environment
rather than being installed twice. `make venv` produces a working venv either way — the flag is a
disk-space convenience, not a requirement.

## Running it on a 68000

```bash
bash atari/build.sh title && python3 atari/smoke.py title
```

`atari/` cross-compiles the **verified cores, unmodified** into a GEMDOS `ZYNAPS.PRG` and boots it
under Hatari to the game's title picture with its music playing, then judges it against the shipped
binary on the six surfaces of [`docs/on-target-execution.md`](../../../docs/on-target-execution.md).
The seam is the include path (`atari/shim_include/` shadows the kit's `os.h`, `hw.h`, `psg.h` and
`sched.h`) plus two omitted sets of translation units, so the differential `.so` is untouched and `make test` is
unchanged — which `atari/build.sh` measures rather than asserts. **It runs on a 1 MB ST**: the
target image is 512 KiB where the differential's is 1 MiB, and `atari/README.md`'s "Memory" section
carries the budget, the address census behind it and the gates that keep it true.

[`atari/README.md`](atari/README.md) is canonical: the seam inventory, what each surface measured,
the negative control, and the ledger of what is still unpinned. `STATUS.md`'s "## On target" is the
pointer from the per-function tables.

**How fast it runs is a separate question from whether it is right, and it has its own instrument.**
`atari/profile.py` clocks both binaries on one machine — the frame cadence off two repeating
debugger breakpoints, the per-routine cycles off Hatari's CPU profiler — and `atari/README.md`'s
PERFORMANCE section carries the table. The short version: the frame differential is byte-identical
and the frame takes **just under three times as long**, 5.66 vertical blanks against the original's
2, with the render path being C where the original is `movem.l` accounting for all of it — the
shim's own share was swept out on 2026-09-01 for 44,349 cycles a frame and the mode did not move.
The regression guard is `smoke.py game`'s `check_the_pacing`, on the timelines surface.

```bash
python3 atari/profile.py frames             # our cadence: vblanks per frame, work, wait
python3 atari/profile.py original-frames    # ...the shipped binary's, the same way
python3 atari/profile.py ours               # per-symbol cycles over a fixed window
python3 atari/profile.py original           # ...and the shipped binary's, from names.txt
python3 atari/profile.py compare            # both read back and ratioed, per call
```

`make guarded` matters here: the preshift builders in `src/sprite.c` index the image with a cursor
they compute themselves, so a step-back one slot too far would read host heap rather than fail. It
is a census, not a gate — see the kit README. It only guards inputs a case actually drives, which is
why `test_sprite.py`'s `FUZZ_MAX_FRAME_BYTES` cap is load-bearing; `STATUS.md` records the two
widths above it that leave the image entirely.
