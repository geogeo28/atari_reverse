# Flying Shark reconstruction — how this project binds to the kit

Human-readable C for Flying Shark (Taito 1987; the Atari ST conversion by Prime Software for
Firebird), each function **verified byte-for-byte against the original 68000 code** by the shared
harness in [`tools/recreate_kit`](../../../tools/recreate_kit): a Musashi oracle runs the real code,
the compiled reconstruction runs on a copy of the same flat memory image, and the two are diffed.
Why differential rather than byte-matching, and what it can and cannot see, is written up once in
[`../../buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md).

**All ten subsystems are ported** — sprite, entity, player, weapons, hud and sound in waves 1 and 2,
then init, frontend, scroll and irq in wave 3 — over the skeleton this file describes: the binding,
the image model, and the gates that catch a wave of subsystem agents getting either wrong.
[`STATUS.md`](STATUS.md) is the ledger, and what is left is accounted for in its "Not reconstructed,
and why" table rather than by absence.

The game itself — the boot chain, the front end, the interrupt model, the entity records, the asset
formats and the sound module — is written up in [`../notes/`](../notes), and every name in
[`../names.txt`](../names.txt) is grounded there. Read `../notes/frontend.md` §1–§3 before touching
anything in this directory: the boot chain is what the image model below reproduces.

## Binding

`project.toml` is the whole binding:

| key | value | why |
|---|---|---|
| `prg` | `../bin/FLYSHARK.PRG` | a plain GEMDOS `.PRG`, nothing packed: text 0x59f4, data 0x6442, bss 0x3f0a8, 1563 relocs |
| `load_base` | `0x10000` | the workspace default; `../names.txt` addresses are Ghidra addresses at this base |
| `image_size` | `0x100000` | must equal `os.h`'s `OS_IMAGE_SIZE`; the program ends at `0x5aede` |
| `tos_malloc_unused` | `true` | the game never allocates — the kit's default 0x20000 arena is inside this program's bss, and the waiver is what lets it stay there. `project.toml` carries the byte scan; `test/test_heap_guard.py` drives the run-time half of the guard |

The game reaches TOS through **six** calls and no others: GEMDOS `Super`, `Fopen`, `Fread`,
`Fclose` and `Cconout`, BIOS `Bconout`, and XBIOS `Setscreen`, `Setpalette`, `Physbase`, `Kbdvbase`
and `Vsync`. Everything else is direct hardware — the IKBD ACIA at `$fffffc02`, the MFP at
`$fffffa11`, the shifter at `$ff8256`, and the YM2149 through the sound module's own writes to
`$ff8800`/`$ff8802`. A case that reaches the sound module therefore needs `psg_seed=` and
`hw_seed={0xff820a: …}` (`tools/recreate_kit/TRAP_MODEL.md`, Phases 6 and 7).

## The image model

**This is the one thing that is different here, and every battery lives with it.** Flying Shark
loads eight files off disc A before its frame loop starts — seven of which are still in memory when
`init_load_assets` returns, `A\FLY_SHK.NEO` having been overwritten by the sprite bank — and derives
its screen pointers from a value the harness has to choose. So
`harness.BASE_IMAGE` — the `.PRG` as loaded, with a bss of zeroes — is not the machine any
frame-loop routine runs on, and a case staged on it would run against zeroed tile banks, a zeroed
sprite bank and null screen pointers, come back green, and be green about a machine that never
exists.

`test/conftest.py`'s **`post_load_image`** fixture is that machine, and a second, **autouse**
session fixture installs it as the image every `differential()` starts from
(`harness.set_base_image`). A battery therefore cannot forget it — which matters because forgetting
would not fail, it would run the case against zeroes.

**The fixture is produced by RUNNING THE ORIGINAL under the oracle, not by transcribing it.** Two
slices of the game's own code, each with the files that slice reads staged for the TOS model:

| slice | run | staged |
|---|---|---|
| 1 | `boot_init` 0x14bee → 0x14cd2 (one instruction short of the `Kbdvbase` pair) | `A\MODULE.BAK` |
| 2 | `init_load_assets` 0x11212 → its `rts` (the title picture and its 32,000-byte copy to `Physbase - 0x80`, then level 0's assets, the sprite bank and the directory fix-up) | the other **seven** |

**Slice 2 used to be two, and the staged-file window is why.** The model stages files in ONE window,
and at the kit's default that window is smaller than this boot's eight files, so `init_load_assets`
was replayed as the title picture on its own and then the other seven entered at 0x112ac — and the
seam that left is why `main`'s own boot slice had no ✅ row at all. `project.toml`'s **`fs_base`**
moves the table down onto the top of `test/abi.py`'s scratch map, and the eight then fit in one
slice with room to spare.

**The arithmetic lives in `project.toml`'s `fs_base` comment and nowhere else** — how big the window
is, what the boot costs it and how much is left — because a subtraction restated in five files is a
subtraction that goes stale in four of them. The map:

```
0x5aede   the program's end                 0xb1000   test/abi.py's scratch map ends,
0x87600   the screen ring's end                       and the staged-file table begins  (fs_base)
                                            0xb2000   the raw staged bytes  (fs_base + 0x1000)
                                            0xff000   STACK_GUARD_LO — the top of the window
```

`test_the_staged_file_window_holds_the_whole_boot` **measures** that arithmetic — it reads the two
addresses back out of the harness's own `OS_FS_TABLE`/`OS_FS_STAGING` and asserts the files fit with
a stated minimum of headroom, so a ninth asset reddens there rather than inside `stage_files` — and
`test_the_staged_file_window_is_clear_of_the_scratch_map_and_the_ring` pins the placement against
the two regions THIS project invented — the kit's own `_vet_staged_file_window` knows about the
program, the framebuffer, the poked-input block and the stack guard, and knows nothing about a ring
or a scratch map a project placed.

The **one** part of the chain the replay does not keep is where the screen ring lands: `boot_init`
derives it from a `Physbase` the model answers with 0x8000, which underflows (below). The fixture
re-applies the routine's own arithmetic at the harness's Physbase instead, between slices 1 and 2.

`conftest.install_boot_state` — the hand transcription this replaced — is kept as a **second
opinion**: `test_the_replay_and_the_transcription_agree` diffs the two over the whole image outside
three named bands (the game's own stack, `load_file`'s scratch, and the title picture in the model's
framebuffer). When they disagree the replay is right, and the transcription is what gets fixed; it
already has been, for the `st $176ea` the transcription had missed.

A second session fixture, **`post_new_game_image`**, is `post_load_image` with `init_new_game`
@ 0x112fa run to its closing `bra.w enter_title`. It has the per-game state reset and the entity
arena zeroed by `clear_actor_arrays` @ 0x115e2 — including the nine bytes `A\MODULE.BAK`'s load
leaves over entity slot 0 (`include/globals.h`, "THE SOUND MODULE OVERLAPS THE ARENA"). It is not
the differential's base; a battery whose routine runs on a started game asks for it by name.

### Where the screen ring goes, and why the harness places it

Flying Shark does not double-buffer. `boot_init` @ 0x14bee builds a **0x1f900-byte circular
framebuffer** immediately below whatever XBIOS `Physbase` answers, keeps four bases inside it, and
scrolls by moving a base 0x500 bytes (8 scanlines) per frame — publishing each frame with
`Setscreen(-1, screen_draw, -1)`. That region is a second area of live game memory, as real as the
bss and not in the `.PRG` at all.

**The model's own `Physbase` cannot be used.** `os.h` answers it with `OS_SCREEN_BASE` = 0x8000, and
the routine's first act is `subi.l #$1f900,d0` — which underflows to 0xfffe8700. Every derived base
would then sit outside the image: the oracle drops those writes on the floor, and a candidate
indexing `image + base` walks off its buffer (which is what `make guarded` faults on). So the
fixture applies **boot_init's own arithmetic to a Physbase of the harness's choosing**:

```
abi.SCREEN_RING_PHYSBASE = 0x7f800        (chosen so that...)
abi.SCREEN_RING_BASE     = 0x60000        = round_up_256(0x7f800 - 0x1f900)
ring[0..3]               = 0x67800 / 0x6fa00 / 0x77700 / 0x7f400
the whole surface        = [0x60000, 0x87600)   the ring, plus one 0x7d00 frame from its top base
```

Note the rounding is **strictly** up (`addi.l #$100,d0 / clr.b d0`), which is why the Physbase is
0x7f800 and not 0x7f900. The region sits above the program's 0x5aede end and below `test/abi.py`'s
scratch map at 0x90000.

**Three pins hold it, and they are deliberately separate** (`test/test_image_model.py`):

* `test_the_boot_slice_derives_the_ring_from_its_own_physbase` runs the **real `boot_init`** from
  0x14bee to 0x14cd2 and asserts its nine screen pointers equal `conftest.ring_pointers()` at the
  **model's** Physbase. So the formula is the routine's, not a transcription of it;
* `test_the_ring_placement_is_the_originals_arithmetic` asserts `abi.SCREEN_RING_BASE` is that same
  formula at the **harness's** Physbase — one number, not two maintained values;
* `test_the_screen_ring_is_clear_of_the_program_and_the_staged_files` is the only thing between the
  ring and the program: the kit's `_vet_os_memory_map` knows about the program, the heap and the
  file table, and knows nothing about a region a project invented.

A core must therefore read `A_screen_ring_base` **out of the image** and never compile 0x60000 in.
`include/globals.h` carries no ring address for that reason, and `test_constants.py` refuses an
`A_*` outside the program.

### The rest of the fixture, and its pins

The replay makes the fixture the original's own work, so what is left to pin is that each slice is
entered where it says and that the whole image agrees with an independent reading of the same code
(`test/test_image_model.py`):

| what the fixture holds | pinned by |
|---|---|
| every byte of it | the **exhaustive** replay-vs-transcription difference: outside three named bands the two must agree, and a store one side invented, misplaced or dropped fails by address |
| the four slice entries and the three checkpoints | `check_entry_prologues(conftest)` — the bytes at each address, read off the loaded `.PRG` |
| A\SPRITES.cru, A\LEVEL1.MAP and the four A\HSC_n.DAT tile banks at their record destinations | the real `load_file` @ 0x10bfa, once per record, with that one file staged |
| the 256 relocated sprite-directory pointers and the four restore-list terminators | the real fix-up loop @ 0x112c2, over an image holding the raw file bytes |
| the relocated TEXT + DATA under all of it | the `.PRG`'s own bytes, sliced out of the file and fixed up by the test rather than by the loader |

## Layout

```
recreate/
├── project.toml     the binding above, and the Malloc waiver's byte-scan evidence
├── Makefile         two lines: KIT + GAME, then `include $(KIT)/kit.mk`
├── include/globals.h       the memory model: segment bounds, the ring's nine pointers, the file
│                        destinations, the two big arrays — and nothing else
├── include/<subsystem>.h   one per subsystem: prototypes, addresses, record layout
├── src/<subsystem>.c       each core plus its `g_<name>` glue
├── src/asm/*.S             ASM TWINS: the original's own instruction sequence for a core the
│                        target build wants at the original's speed, carrying that core's C
│                        signature. Off target they are never linked — `test/test_asm_*.py`
│                        runs them under Musashi and compares them against the C. See
│                        `src/asm/README.md`
├── test/harness.py         16-line shim: binds the kit and star-re-exports it
├── test/abi.py             the scratch map, the ring placement, the register-call stub, and the
│                        two helpers every battery would otherwise copy — `run_case` (one
│                        differential case) and `declare_glue` (a `g_*`'s ctypes signature)
├── test/conftest.py        the boot-chain replay, the three image builders (`post_load`,
│                        `post_new_game`, `started_level`) as plain functions plus the fixtures
│                        over them, the autouse one that installs the first as every
│                        differential's base, and the STAGED WORLDS the whole-frame batteries
│                        share (built once per `make test`, cached across the xdist workers by
│                        `built_once_per_run`)
├── test/test_image_model.py  the replay's pins, the second opinion, and the free-space census
├── test/test_constants.py    the CLAUDE.md §5 pin and the duplicate checks — a collector
├── test/test_heap_guard.py   the run-time half of project.toml's `tos_malloc_unused` waiver
├── test/test_status.py       STATUS.md's counts against its rows, and its rows against
│                        `../names.txt`: every `fn` is verified or deferred, never both
├── test/test_<subsystem>.py  one differential battery per subsystem
├── test/asm_twins.py       the machinery every asm-twin differential shares (a copy of Zynaps')
├── test/test_asm_<name>.py  one twin's differential, transcription pin and cost pin
└── STATUS.md        the per-function ledger, in per-subsystem sections
```

There is no `addrs.h`, and the 68000 primitives every core shares live in the kit's `machine.h`.
`include/common.h` is for the idioms this PROGRAM's assembly repeats that more than one core needs,
and the bar for adding one is still two callers in two files, because a helper with one caller
belongs in that caller's file. `test_constants.py::test_no_constant_is_defined_in_two_files` is what
makes the alternative loud: one fact under two names is refused rather than merged silently. One of
its entries is not an idiom but a SEAM — `wait_may_go_round_again`, the harness-only give-up a spin
on an interrupt-written byte is bounded by, which compiles to a constant 1 on target. It clears the
two-caller bar like everything else here: all FOUR busy-waits in the reconstruction go through it,
in three files. Its comment argues why a bound has to exist off target and must not exist on it, and
why exhausting one has to tally a refusal rather than quietly return — and every caller honours the
0 with a `return`, which is the contract `tools/recreate_kit/include/sched.h` states for the kit's
own capped waits.

## Adding a function

Worked by **several agents at once**, each owning subsystems; the layout is arranged so that adding
a function touches only files your subsystem owns.

| file | who edits it |
|---|---|
| `src/<yours>.c`, `include/<yours>.h`, `test/test_<yours>.py` | **you alone** |
| `STATUS.md`, your `## Verified — <yours> (N)` section and its count | **you alone** |
| `include/<someone else's>.h` | **nobody but its owner** — include it to READ a global, never edit it |
| `include/globals.h`, `test/test_constants.py`, `test/test_status.py`, `test/test_image_model.py`, `test/conftest.py`, `Makefile`, `project.toml`, `test/harness.py` | **nobody**, in normal work — `conftest.py`'s staged worlds are the one thing a battery reaches into, and by asking for the fixture rather than by editing it |
| `include/common.h` | shared, **append-only**, and only for an idiom a SECOND core needs |
| `test/abi.py` | shared, **append-only** — only if you need a new stub shape or a helper every battery would otherwise copy |

The ten planned subsystems, which are the `## Verified` sections `STATUS.md` opens with and the
`src/<stem>.c` names they are keyed to: `init`, `frontend`, `scroll`, `sprite`, `entity`, `player`,
`weapons`, `hud`, `irq`, `sound`.

Two conventions carry that:

- **A global lives in the header of the subsystem that owns the data.** Any subsystem may
  `#include` another's header to read it. There is no promotion protocol and no shared address file,
  because both would make a routine edit somebody else's file. `test_constants.py` refuses a
  constant defined in two files, an address under two `A_*` names, and an `A_*` outside the program.
- **Borrowed globals get a row in STATUS.md.** A global you define because the subsystem that owns
  it is unported is a LOAN: the row, the `#define` under a BORROWED note, and `test_constants.py`'s
  duplicate check as the automatic call-in notice. Deleting the row and the `#define` it names is
  the whole of the migration.

**FREEZE a shared record layout in one block, and tag every field.** The 58-byte entity record
(91 of them at `A_entity_arena`) is what several agents will port routines against at once, so it
goes into `include/entity.h` **whole**, in one block nobody adds to, each field tagged either
`pinned by <test>` or `names.txt, unpinned` — and the only permitted edit is upgrading a tag in the
same change that ports the routine which pins it. `projects/zynaps/recreate/include/entity.h` is the
worked example, and `docs/agent-playbook.md` §11 is the argument. "Append-only in offset order" is
the rule that looks right and is not: inserting at an offset is not appending.

The steps:

0. **Name-map changes travel as PROPOSALS, not edits.** An agent never touches `../names.txt`: it
   has no ownership seam, and `ApplyNames` **replaces** a plate comment rather than appending, so a
   second `cmt` for an address silently destroys the first. New `fn`/`var`/`cmt` facts go in
   `../out/names_<slice>.txt`, sectioned CORRECTIONS / NEW NAMES / COMMENT REFINEMENTS, each row
   citing the line it replaces or deletes, and opening with "NOTHING HERE IS IN ../names.txt YET —
   merge deliberately", for the orchestrator to merge.
   `grep -E '^(fn|var|cmt|param|proto) 0x' ../names.txt | cut -d' ' -f1,2 | sort | uniq -d` must
   stay empty. `../out/names_harness.txt` is this skeleton's own proposals file.
1. Read the routine in `../out/prg_dis.txt` **from a known function start** — a `bsr`/`jsr` target
   from an anchored caller. A linear sweep desyncs on data, so a body read from the middle of the
   listing is not evidence (`docs/m68k-disassembly.md`). `decomp.c` is a map only: Ghidra renders
   most of this program's register-argument routines as a bare `return;`.
2. Write the core in `src/<subsystem>.c` under the `../names.txt` name, plus its glue `g_<name>`.
   No raw register names; name every non-trivial literal. **The glue must call the core**, never
   restate it. This game is hand assembly with a REGISTER ABI: the glue takes the registers as
   parameters and a one-line comment maps register → role.
3. Put addresses, record fields and the prototype in `include/<subsystem>.h`.
4. Add edge + fuzz cases in `test/test_<subsystem>.py`. A case is `abi.run_case(entry, glue,
   pokes=…, regs=…, note=…)` — pokes travel in `regs["_pokes"]`, which `run_case` does for you
   because `harness.differential` has no `pokes=` parameter — and every `g_*` a battery calls is
   declared once with `abi.declare_glue`, so ctypes cannot pass a 64-bit image pointer as an `int`.
   You do **not** stage the post-load image yourself: `conftest.py`'s autouse fixture installs it
   (ask for `post_new_game_image` by name if your routine runs on a started game). A routine whose
   whole answer is in registers goes through `abi.register_call_pokes`. Shard fuzz by `chunk` so
   `-n auto` spreads it, and prefer an EXHAUSTIVE sweep over a random one wherever the input is
   narrow enough — a one-byte input is 256 cases, and a 96-draw fuzz over it covered 78 of them.
   Declare the battery's `MIRRORS`, `ENTRY_PROLOGUES` and — if any case uses `stop_pc` —
   `STOP_PROLOGUES` at the bottom of that file; `test_constants.py` fails by name if a battery has
   no pins, if `src/<yours>.c` exists with no `test_<yours>.py` beside it, and if a module-level
   `ENTRY_*`/`STOP_*` inside the program has no row. A `MIRRORS` row is just the constant's NAME,
   read out of `include/globals.h` — set `MIRROR_HEADER = "include/<yours>.h"` at the top of the
   file to mirror your own header instead, and spell the full `(name, path, name)` triple only for
   the odd row that comes from somewhere else.
5. `rm -f build/*.so && make test` — green is the bar, not "looks right". Run `make guarded` too if
   the function indexes the image with an address it computed, which every screen-ring routine does.
6. Mutate a constant, rebuild, confirm the suite goes red, revert. **Only from a green baseline**:
   a suite with one unrelated failing test reports every mutant as killed.
7. Append your STATUS.md row, update your section's count, and say what the verification covered.
   ONE ✅ ROW PER ADDRESS across the whole ledger, and every `fn` line in `../names.txt` needs
   either a ✅ row or a row in "Not reconstructed" — `test_status.py` skips that check only while
   the ledger is completely empty, and arms at the first row anyone files.

## Running it

```bash
cd projects/flyingshark/recreate
rm -f build/*.so && make test    # rebuild both libs and run the suite (-n auto)
make guarded                     # the same suite over a PROT_NONE-bounded image (Darwin/BSD only)
```

`make venv` is the kit's rule (`python -m venv .venv` + `requirements.txt`) and takes whatever
`python` is on PATH, which is why this `.venv` was created explicitly over the workspace's
`atari_reverse` conda interpreter, as Zynaps', Joust's and Bubble Ghost's were:

```bash
/Users/geogeo/miniconda3/envs/atari_reverse/bin/python -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
```

`--system-site-packages` is a disk-space convenience, not a requirement.

The disc-A files the fixture reads live in [`../bin/disk/A/`](../bin/disk/A); `../notes/loader.md`
has the carve from `../bin/FILES/FRD` if that folder is ever lost.

## Running it on a 68000

[`atari/`](atari) compiles the same cores with `m68k-elf-gcc` and boots them on a real Atari ST.
The cores are compiled UNCHANGED — the difference between the two builds is the include path
(`atari/shim_include/` shadows the kit's `os.h`, `hw.h`, `psg.h` and `sched.h` with real-TOS
versions, and this project's `include/init.h` with its two undoored XBIOS answers), the four kit
sources the .PRG leaves out, and the two things the performance campaign added: `src/sprite.c` is
compiled with hotter flags, and three of its routines are called through an asm twin instead of the
C — the unclipped blitter through `src/asm/sprite.S`, the five restore blitters and the ring-seam
copy through `src/asm/restore.S`. Both are *source*-identical and both are pinned — the twins by
`test/test_asm_sprite.py` and `test/test_asm_restore.py`, and the whole build by the framebuffer
identity `atari/smoke.py` checks.

```bash
bash atari/build.sh          # -> atari/disk/AUTO/FLYSHARK.PRG and atari/disk/FLYSHARK.ST
python3 atari/smoke.py       # boot it AND the original, and judge both on every surface
python3 atari/profile.py pace   # ...and what a frame costs, against the original's own
bash atari/run.sh            # play it
```

**The frames it publishes at attract frames 50 and 120 — one per attract text page — are the
original binary's frames, byte for byte.** Both are `screen_prev1`, the buffer the shifter is
fetching, and reading it rather than `screen_draw` is what puts a sprite inside the comparison at
all (`atari/smoke.py`'s `A_SCREEN_DRAW` comment has the measurement).
[`atari/README.md`](atari/README.md) is the whole account: the memory map, why the original's
`AUTO\`-only 0xd922 load ceiling does not apply to a build whose screen ring lives in its own `.bss`,
what the shim supplies and why none of it re-implements a core — it COMPOSES the verified ones, and
what is left over is the handful of things a differential structurally cannot hold (an `rte`, a
branch target that is not a call, a stack unwind, a smoke run's own frame limit) — the six surfaces
`atari/smoke.py` checks, three deliberate divergences and what is still unpinned (chiefly: the
joystick has never been pressed, and nothing has been played past the attract screen).

Two things a core owner may want to know:

* **`fs_physbase()` and `fs_kbdvbase()` are the seam they were written to be.** `include/init.h`
  says an on-target build replaces those two bodies; `atari/shim_include/init.h` is that replacement,
  and it is the only place a shim header shadows a CORE header.
* **`KEY_ABORT_BIT` is private to `src/player.c`, and the target build needs it.** The frame loop's
  abort exit unwinds the stack rather than returning, so the shim watches F10's bit at the frame
  boundary and spells the same bit as `FS_ABORT_KEY_MASK`. When a core header grows that constant —
  `include/irq.h` owns `A_key_bits` — the shim's copy should be deleted in the same change.
