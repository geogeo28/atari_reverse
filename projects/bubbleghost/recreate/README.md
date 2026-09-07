# Bubble Ghost reconstruction — how this project binds to the kit

Human-readable C for Bubble Ghost (ERE Informatique, 1987), each function **verified byte-for-byte
against the original 68000 code** by the shared harness in
[`tools/recreate_kit`](../../../tools/recreate_kit): a Musashi oracle runs the real code, the
compiled reconstruction runs on a copy of the same flat memory image, and the two are diffed. Why
differential rather than byte-matching, and what it can and cannot see, is written up once in
[`../../buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md). **Read
[`STATUS.md`](STATUS.md)'s "Model gaps" first**: this game reaches OS calls the earlier games
did not, and the table says which are modeled now and which still refuse — most of the
original list is struck through, so a row that still reads as a blocker is the exception.

## Binding

`project.toml` is the whole binding:

| key | value | why |
|---|---|---|
| `prg` | `../bin/GHOST_RT.PRG` | the RUN-TIME layout (below): text 0x14f1a = code+bss, data 0x2f4, 9 relocs |
| `load_base` | `0x10000` | the workspace default; `../names.txt` addresses are Ghidra addresses at this base |
| `image_size` | `0x100000` | must equal `os.h`'s `OS_IMAGE_SIZE`; the program ends at `0x2520e` |
| `heap_base` | `0x30000` | the default Malloc arena (0x20000) is inside this program's BSS, and this game DOES allocate; see below |
| `heap_limit` | `0x90000` | the first address that arena may not reach — `test/abi.py`'s scratch map starts here |

`../bin/GHOST.PRG` is the shipped file, **encrypted against the disk's copy-protection track**;
`../bin/GHOST_PLAIN.PRG` is `tools/depack_bubbleghost.py`'s decryption of it, proven byte-for-byte
against a real Hatari run ([`../notes/loader.md`](../notes/loader.md)). Nothing here touches it.

## The image model

**This is the one thing that is different here, and everything else follows from it.** Bubble Ghost
is Alcyon/DRI C, small model: its crt0 (`crt0_start` @ 0x10036) Mshrinks, **moves the DATA segment
up above the BSS**, clears the BSS, and points `a4` at the boundary. The running program is
`[TEXT][BSS][DATA]` — not the file's `[TEXT][DATA][BSS]` — with

```
TEXT  0x10000 .. 0x1e8ca      BSS  0x1e8ca .. 0x24f1a      DATA  0x24f1a .. 0x2520e
                                            a4 = 0x24f1a
```

and **every global reached as `n(a4)`**, signed: `-26170(a4)` is `0x1e8e0`, `664(a4)` is `0x251b2`.
The kit's loader runs no crt0, so it is fed `GHOST_RT.PRG` — the same program rebuilt in that layout
by `tools/prg_relayout.py` (text' = tlen + blen, data' = dlen, bss' = 0), which is also the image
the Ghidra project was built from. So **a Ghidra address, a `../names.txt` address and a run-time
address are all the same number**.

Two consequences every case lives with:

* **every run passes `a4`.** `regs={"a4": abi.A4_BASE}` — a run without it reads the game's globals
  from address `n`, which is the 68000 vector page, and diffs clean against an oracle doing the same;
* **every case runs on the POST-INIT image, not on `harness.BASE_IMAGE`.** The loaded image's BSS
  is all zeroes: the crt0's last act is `init_globals` @ 0x16d8e, which writes every non-zero
  initialiser one `move` at a time. `test/conftest.py`'s `post_init_image` fixture is that image,
  and a second, **autouse** session fixture installs it as the base every `differential()` starts
  from (`harness.set_base_image`). A battery therefore cannot forget it — which matters because
  forgetting would not fail, it would run the case against zeroed tables and come back green.

**Neither is a convention this project invented, and `test/test_image_model.py` is the proof.** It
compares GHOST_RT.PRG's TEXT and DATA against GHOST_PLAIN.PRG's byte for byte, derives `a4` from
each header independently, then **runs the program's own crt0** on a file-layout image with a
fabricated basepage, to the instruction before it calls `main`, asserting the memory that produces
equals the fixture over the whole program — one byte differs, and it is named rather than excluded
(the basepage pointer stored at `-4(a4)`). That pin has already paid for itself: it found that
`init_globals` **reads A5**, so the fixture passes `a5 = 0x10000` too. A fixture without it is wrong
in seven longwords of live game state while every test around it stays green.

### The Malloc arena is moved, not waived

How the kit's `heap_base` / `heap_limit` keys work is in
[`tools/recreate_kit/README.md`](../../../tools/recreate_kit/README.md), "The Malloc arena is the one
region a project places". **This game's numbers:** the default arena (0x20000) lands in the middle
of this program's BSS, and unlike Joust and Zynaps this game really does allocate — **eleven**
`c_malloc` calls totalling **0x3d544 bytes (245 KiB)** across the four file loaders, plus 0x7c00
more for the sprite bank, all on one boot path. So `tos_malloc_unused` — the claim that a game never
allocates — is simply false here, and the arena is moved to `[0x30000, 0x90000)` instead. Those are
C-library calls rather than GEMDOS traps (`c_malloc` @ 0x15b54 is a free-list allocator that takes
rounded-up pools and never returns them), so the model's arena sees fewer and larger requests;
`project.toml` has the breakdown and `test/test_image_model.py` sums it, pins both keys, and pins a
served `Malloc` landing at 0x30000 on both sides.

## Layout

```
recreate/
├── project.toml     the binding above
├── Makefile         two lines: KIT + GAME, then `include $(KIT)/kit.mk`
├── include/globals.h       the memory model above, and nothing else
├── include/common.h        the 68000-shaped helpers more than one core needs; its own header
│                        says why they are not in the kit's machine.h
├── include/<subsystem>.h   one per subsystem: prototypes, addresses, record layout
├── include/init_globals_stream.h  GENERATED: `init_globals` @ 0x16d8e's 7,869-instruction
│                        stream as data, decoded from the disassembly. Its own header says
│                        why it is derived from the ASM and not from the image it produces
├── src/<subsystem>.c       each core plus its `g_<name>` glue
├── test/harness.py         16-line shim: binds the kit and star-re-exports it
├── test/abi.py             the scratch map, the C stack-argument builder, the two stub shapes,
│                        and what every battery shares: `run_with_a4` (the one differential
│                        spelling), `merge_pokes`, `stage_world`, `trap_slot_noise`, the
│                        big-endian encoders and decoders, and `shard` (the seeder,
│                        `abi.seed_spans`, is the kit's — re-exported here)
├── test/conftest.py        the post-init image fixture, and the autouse one that installs it
├── test/test_image_model.py  the relayout + crt0 pins and the free-space census
├── test/test_constants.py    the CLAUDE.md §5 pin and the duplicate checks — a collector
├── test/test_status.py       STATUS.md's counts against its rows, and its rows against
│                        `../names.txt`: every `fn` is verified or deferred, never both
├── test/test_<subsystem>.py  one differential battery per subsystem
└── STATUS.md        the per-function ledger, in per-subsystem sections
```

There is no `addrs.h`. The 68000 PRIMITIVES every core shares live in the kit's `machine.h` —
`be16`/`wr32`, `sign_ext16`, `addr_add`, `loop_passes` — and the IDIOMS this program's own compiler
emits live in `include/common.h`: `muls_ext_w` (a `muls.w` followed by an `ext.l`),
`copy_longs_ascending`, `longword_slot` and `LONG_BYTES`. That header's comment argues the split,
which is worth reading before adding to either.

## Adding a function

Worked by **several agents at once**, each owning subsystems; the layout is arranged so that adding
a function touches only files your subsystem owns.

| file | who edits it |
|---|---|
| `src/<yours>.c`, `include/<yours>.h`, `test/test_<yours>.py` | **you alone** |
| `STATUS.md`, your `## Verified — <yours> (N)` section and its count | **you alone** |
| `include/<someone else's>.h` | **nobody but its owner** — include it to READ a global, never edit it |
| `include/globals.h`, `test/test_constants.py`, `test/test_status.py`, `test/test_image_model.py`, `test/conftest.py`, `Makefile`, `project.toml`, `test/harness.py` | **nobody**, in normal work |
| `test/abi.py` | shared, **append-only** — only if you need a new stub shape or a helper every battery would otherwise copy |
| `include/common.h` | shared, **append-only**, and only for an idiom a SECOND core needs — a helper with one caller belongs in that caller's file |

Two conventions carry that:

- **A global lives in the header of the subsystem that owns the data.** Any subsystem may
  `#include` another's header to read it. There is no promotion protocol and no shared address file,
  because both would make a routine edit somebody else's file. `test_constants.py` refuses a
  constant defined in two files, an address under two `A_*` names, and — this program's own trap —
  an `A_*` holding an `n(a4)` **displacement** where an address belongs.
- **Borrowed globals get a row in STATUS.md.** A global you define because the subsystem that owns
  it is unported is a LOAN: the row, the `#define` under a BORROWED note, and `test_constants.py`'s
  duplicate check as the automatic call-in notice. Deleting the row and the `#define` it names is
  the whole of the migration.

The steps:

0. **Name-map changes travel as PROPOSALS, not edits.** An agent never touches `../names.txt`: it
   has no ownership seam, and `ApplyNames` **replaces** a plate comment rather than appending, so a
   second `cmt` for an address silently destroys the first. New `fn`/`var`/`cmt` facts go in
   `../out/names_<slice>.txt`, each tagged ADD or EXTEND, for the orchestrator to merge.
   `grep -E '^(fn|var|cmt|param|proto) 0x' ../names.txt | cut -d' ' -f1,2 | sort | uniq -d` must
   stay empty.
1. Read the routine in `../out/prg_dis.txt` **from a known function start** — a `bsr`/`jsr` target
   from an anchored caller. A linear sweep desyncs on data, so a body read from the middle of the
   listing is not evidence (`docs/m68k-disassembly.md`).
2. Write the core in `src/<subsystem>.c` under the names.txt name, plus its glue `g_<name>`. No raw
   register names; name every non-trivial literal. **The glue must call the core**, never restate it.
3. Put addresses, record fields and the prototype in `include/<subsystem>.h`.
4. Add edge + fuzz cases in `test/test_<subsystem>.py`. Run every case through **`abi.run_with_a4`**
   rather than `harness.differential`: it carries the `a4` this program's globals are reached
   through, so a battery cannot be written without it. (The modeled Malloc arena needs nothing from
   a battery: `src/clib.c` allocates through the kit's own `os_malloc`, and `harness.arm_candidate`
   rewinds that bump pointer before every candidate run.) Arguments go on the stack (`abi.stack_args`), because
   this is compiled C, and **pokes travel in `regs["_pokes"]`** — `harness.differential` has no
   `pokes=` parameter. Build a poke dict with **`abi.merge_pokes`**, which refuses an overlap: two
   pokes covering one byte read as "both regions were staged" when only the later one was, and a
   battery that means the overlap passes `allow_overlap=True` at that site and says which bytes win.
   You do **not** stage the post-init image yourself: `conftest.py`'s session-scoped **autouse**
   fixture installs it as the image every differential starts from (`harness.set_base_image`), so a
   case that forgot cannot silently run against a bss of zeroes. Shard the fuzz by `chunk` — either
   partitioning one fixed list (`abi.shard`) or seeding per chunk; `abi.shard`'s docstring says when
   each is right, and a docstring that claims the wrong one is worse than none. Declare the
   battery's `MIRRORS`, `ENTRY_PROLOGUES` and — if any case uses `stop_pc` — `STOP_PROLOGUES` at the
   bottom of that file. `test_constants.py` fails by name if a battery has no pins at all, if
   `src/<yours>.c` exists with no `test_<yours>.py` beside it, and if any module-level `ENTRY_*` or
   `STOP_*` naming an address inside the program has no row: a dict of pins can only check what is
   in it, so the row you forget is the address nothing looks at.
5. `rm -f build/*.so && make test` — green is the bar, not "looks right". Run `make guarded` too if
   the function indexes the image with an address it computed.
6. Mutate a constant, rebuild, confirm the suite goes red, revert. **Only from a green baseline**: a
   suite with one unrelated failing test reports every mutant as killed.
7. Append your STATUS.md row, update your section's count, and say what the verification covered.
   ONE ✅ ROW PER ADDRESS across the whole ledger, and every `fn` line in `../names.txt` needs
   either a ✅ row or a row in "Not reconstructed" — `test_status.py` fails by name on a second row,
   on an unaccounted `fn`, and on an address that claims both. A slice of a routine that already has
   a row is filed under the address the SLICE starts at, not under the routine's.

## Running it

```bash
cd projects/bubbleghost/recreate
make venv                        # the kit's rule: python -m venv .venv + requirements.txt
rm -f build/*.so && make test    # rebuild both libs and run the suite (-n auto)
make guarded                     # the same suite over a PROT_NONE-bounded image (Darwin/BSD only)
```

## On target

[`atari/`](atari/README.md) compiles these cores — **unmodified, and `atari/build.sh` measures it
rather than claiming it: `git` refuses a core that differs from its committed content or that git
does not track, and five isolation gates refuse one that reaches into the shim** — into
`BUBBLE.PRG`, and runs them on a 68000.

```bash
bash atari/build.sh title && python3 atari/smoke.py title   # the gate: 8 checks vs the original
bash atari/build.sh titlefault && python3 atari/smoke.py titlefault   # one colour pen
bash atari/build.sh titlepoke  && python3 atari/smoke.py titlepoke    # one word of the image
bash atari/build.sh titleisr   && python3 atari/smoke.py titleisr     # no Timer C vector
bash atari/build.sh title floppy && python3 atari/smoke.py floppy     # the bootable volume boots
bash atari/build.sh play && bash atari/smoke.py game         # the G key, and the room behind it
bash atari/build.sh play && bash atari/run.sh               # the whole program, for a person

python3 atari/profile.py ours && python3 atari/profile.py original && python3 atari/profile.py compare
python3 atari/profile.py frames ours                        # ...and the per-frame cost itself
```

`profile.py` is the performance campaign's instrument, not a gate: it measures what a room frame
costs on both binaries over the same 1000-vblank window and ranks the difference by function
(`atari/README.md`, "Performance"). `STATUS.md` carries the headline.

**Both anchors are moments.** Ours is a PC in the shim, the original's is `menu_read_key_and_fold`
@ `0x116c4` — the slice boundary right after `title_menu_open`, found by polling RAM for the
decrypted plaintext and adding its load base. So the framebuffer comparison is two programs at one
place in one program, not two waits.

The seam is the INCLUDE PATH plus one omitted directory (the kit's own `src/`), exactly as in
`projects/zynaps/recreate/atari`: `atari/shim_include/` shadows the kit's `os.h`, `hw.h` and `psg.h`
so that every `os_*`, `psg_*` and `hw_*` door a core calls becomes a real trap or a real store. Three
things about this build are not that one's, and each is argued in `atari/README.md`:

* **it runs in USER mode**, because this is a GEM application and its AES and VDI calls are made
  from the mode TOS expects them from — so `os_super` is the real trap here, and the three
  supervisor-only stores the cores make go through a **`trap #9` gate**, which is the original's own
  mechanism for exactly that problem;
* **the crt0 really runs**: the target stages the FILE layout (`GHOST_PLAIN.PRG`) with a fabricated
  basepage below it, so `crt0_relocate_and_clear` establishes A4 on the machine and the smoke pins
  its answer at `0x24f1a`. That the two layouts agree is `test/test_image_model.py`'s proof, not a
  new claim;
* **one constant changes**, and it is the only change to what a verified core computes.
  `xbios_trap_call` answers XBIOS `Logbase` with the kit's `OS_SCREEN_BASE` from inside a core with
  no door under it, and the model's `0x8000` puts this program's room staging area at a negative
  address — harmless off target only because every battery stages the two screen pointers itself.

**The rest of the XBIOS group now has a seam, and getting it took a change to these cores.**
`Setscreen`, `Setpalette`, `Setcolor` and `Vsync` used to be `return 0` inside `src/frontend.c`'s
`xbios_trap_call`, so the target could only reissue two of them at the composition boundary after
the slice that would have made them — and the cost was visible to a person: the presentation played
its whole voice in the desktop's palette. They now go through the kit's own doors
(`tools/recreate_kit/TRAP_MODEL.md`, Phase 14), which are ordered entries in the OS event ledger and
still touch no image byte, so the target shadows them with the real traps. **The door found three
`Setcolor` calls that were not in the C at all** — two in `frame_blow_or_recover`, one in
`frame_death_sequence`, all three green for the life of the project because the difference was
entirely off-image.

**And it has no seam for `Fopen`'s mode.** The kit's `os_fopen` takes `(mem, name_ptr)` and no mode,
so `c_open` drops the original's `mode & 3` before the door and the target opens read-only — which
is what every live caller in this program asks for, but a value the seam guesses rather than
carries. Same shape of fix, same place: a kit door plus a case.

## Regenerating `include/init_globals_stream.h`

`init_globals` @ 0x16d8e is 7,869 straight-line stores and its reconstruction is that stream as
data. `../tools/gen_init_globals_stream.py` decodes it out of `../out/prg_dis.txt`, refuses any
instruction outside its ten shapes, and checks its own output against an oracle run before writing
a line:

```bash
cd projects/bubbleghost/recreate
.venv/bin/python ../tools/gen_init_globals_stream.py -o include/init_globals_stream.h
```

Re-run it if the disassembly is re-cut or the load base moves. Do not hand-edit the header.

`.venv` was built with `--system-site-packages` over the workspace's `atari_reverse` conda
interpreter, as Zynaps' and Joust's were — a disk-space convenience, not a requirement.
