# Reconstruction status — Bubble Ghost

Human-readable C reconstruction of Bubble Ghost (ERE Informatique, 1987), each function **verified
byte-for-byte against the original 68000 code** by the shared differential harness
(`tools/recreate_kit`: a Musashi oracle running the real code vs. the compiled reconstruction, on
the same memory image). `../names.txt` is the source of truth for every name.

**Verified: the sum of the per-section counts below.** That sum is larger than the number of
FUNCTIONS, and deliberately: some rows are SLICES filed under the address the slice starts at rather
than under a function's entry (README.md, "Adding a function", step 7), so the sum counts them too.
How many is arithmetic rather than a number to carry — the ✅ rows minus the `fn` lines
`../names.txt` carries — and `test_status.py` re-derives both sides of it.
Against `../names.txt` — the source of truth — the arithmetic is **all 132 of its `fn` lines
verified and none deferred**, out of the 134 functions Ghidra found in this program
(`../notes/anchors.md`, "Shape of the image": the 31 KB running to the end of TEXT is
`init_globals`' own instruction stream, not undiscovered code).

All seven sections carry rows now — `init`, `frontend`, `gameplay`, `blit`, `sound`, `voice` and
`clib`. EVERY `fn` LINE IN `../names.txt` NOW HAS A ✅ ROW, and nothing is deferred: what is left in
"Not reconstructed" is the SECOND program (`GHOST.LOA`), which has no address in this one, and five
small regions of the two top-level routines that no slice may include — three branch tests, one
`jsr` into the LOA and one `c_free`.
Each `## Verified — <subsystem>` heading carries its own count, so the only number an agent touches
is its own section's; `test/test_status.py` fails if a count and its rows disagree, if a section that
carries rows names a subsystem with no `src/<name>.c`, and if a literal grand total creeps back into
this header.

**The image model is README's, not this file's.** Why the harness loads `../bin/GHOST_RT.PRG`, what
the post-init fixture is, and why every case passes `a4 = 0x24f1a` are decided in
[`README.md`](README.md), "The image model", and pinned by `test/test_image_model.py`. Nothing here
restates it.

**How to add a function:** [`README.md`](README.md), "Adding a function" — the procedure, the file
ownership table, and the conventions all live there rather than being restated here.

## The suite, and what it is proved to catch

**The skeleton's own gates are 33 tests** — `test_image_model.py` 22, `test_constants.py` 6,
`test_status.py` 5 — with each battery's cases on top of them, so the suite total is not a number
to carry here: re-count it with `rm -f build/*.so && make test` and report your own battery's share.
The kit's suite behind it measured **631** (`make -C tools/recreate_kit test`) when this was
written — a number that moves with the kit rather than with this project, so re-run it rather than
quoting it.

**Mutations tried against the skeleton's gates**, each rebuilt from a clean `build/` with
`__pycache__` swept, and each **red**:

| mutation | what stayed honest |
|---|---|
| `test_image_model.py`'s `A4_BASE` off by 2 | the `include/globals.h` mirror, and both .PRG headers' derivation of it |
| `conftest.py`'s `INIT_GLOBALS_A5` set to 0 | the crt0 equivalence — the seven `lea n(a5),a0` pointers land in low memory instead |
| `test/abi.py`'s `STUB` moved to 0x80000 | the arena/scratch-map boundary: it must equal `project.toml`'s `heap_limit` |
| `project.toml`'s `heap_limit` raised to 0xa0000 | the same boundary, from the other side |
| `project.toml`'s `heap_base` moved into the program | the kit refuses at IMPORT — the whole suite errors, by name |
| a `## Verified — <x> (N)` count raised by one | `test_status.py`'s per-section re-derivation |
| `src/<x>.c` with its `test_<x>.py` renamed away | `test_constants.py` now names the missing battery instead of dropping the stem — observed live rather than injected, on a tree that carried `src/sound.c` before its battery landed |
| the autouse base-image fixture removed | `test_every_differential_starts_from_the_post_init_image` |
| `conftest.py`'s stated `INIT_GLOBALS_INSNS` off by one | the fixture's measured cost, re-run |
| the Malloc census's palette counted per picture | `test_the_derived_malloc_census_is_the_one_the_prose_quotes` — the exact error the old `0x3d5e4` constant carried |

Every row above was **run**, from a clean `build/` with `__pycache__` swept, against the green
subset `test_image_model.py + test_status.py`. A mutation the suite does not catch is a coverage
hole, not a licence — record it here.

**WHAT THE PRE-COMMIT REVIEW CAUGHT that the mutation sweep did not, 2026-09-06.** Recorded because
the two are different instruments and the difference is the useful part: a sweep can only flip what
the code says, and three of these were about what the code did not say at all.

| found | what it was |
|---|---|
| `c_open`'s truncating arm was missing the original's `Fcreate` + `Fclose` pair (0x15dd8..0x15df2) | a REAL defect in a region no case ran, and no mutation of the written code could have surfaced it |
| the crt0's DATA move counted its `dbf` in 32 bits | a REAL defect, twelve lines from the same `dbf` transcribed correctly |
| the poll's own cases staged no `A_key_raw`, so the flush ate every staged control key | the whole `^S`/`^R`/`^P` arm set was vacuous; the `^S` toggle could be INVERTED with the suite green |
| `test_frame_poll_input_files_the_mouse`'s anti-vacuity assertion was `assert info["writes"]` | a tautology (the trampoline always writes), over an input block nothing seeded |
| three helpers copied into a third battery, one of them with the `rng` quietly dropped | `abi.trap_slot_noise` is the one home now |
| two names for one GEMDOS basepage field across two batteries, pinned by nothing | `test_the_basepage_offsets_have_one_meaning_across_both_files` |

## On target — what the .PRG proved, and what it could not

`atari/` builds these cores into `BUBBLE.PRG` and runs them on a 68000
(`atari/README.md`; the surfaces are `docs/on-target-execution.md`'s). **It is a different
instrument from the differential and it found things the differential cannot**, so what it settled
is recorded here beside the ledger it settled it against.

| what the on-target run settled | which residual it was |
|---|---|
| `crt0_relocate_and_clear` establishes `A4_BASE` on a real machine, from a real basepage | "Verified — init" residual 2: the Mshrink was unmodeled off target. The .PRG makes the real call and the record carries GEMDOS's answer |
| the whole menu is drawn, and its 32,000 displayed bytes are **byte-identical to the original's** | every "the video and colour calls are modeled as no-ops" residual in this file. The picture is now measured rather than assumed |
| `Getrez` really answers, and the gate really branches on it | "Verified — init" residual 1: the model's constant. The record carries the arm the machine took |
| the flush-then-blocking-read idiom is ONE LOOP again | the `Crawcin`/`Cnecin` row in "Model gaps": on target the read blocks and the machine answers, so the front end needs none of the slice boundaries the model forced |
| `install_sound_vectors`' MFP write and the 200 Hz ISR both run — 350-360 ticks by the time the anchor is reached, and `atari/smoke.py` asserts only that the count is NON-ZERO, because the anchor's hold is a count of vertical blanks over a real floppy timeline. The surface is `STATE.BIN`'s `TIMER_C_TICKS`, and `atari/build.sh titleisr` is the control that reds it | the Timer C row in "Model gaps": the model fires no interrupts |
| `play_voice`'s `jsr` into `GHOST.LOA` is a REAL CALL: the file is opened and read, the sample pointer poked into the loaded image at +0x1e is translated from an image offset to a machine address (`VOI_POINTER_MACHINE` in the record, asserted equal to `IMAGE_BASE + VOI_BUFFER_OFFSET`), and the `jsr` returns. **What the second program then DOES is not observed by anything**: the harness runs with `--sound off`, no surface reads the PSG or the MFP timer the LOA programs, and "the speech plays" is not a claim this build has evidence for | the `GHOST.LOA` row in "Not reconstructed": on target it is real memory and a real MFP |

**AND WHAT IT COULD NOT — CLOSED 2026-09-06.** Four XBIOS calls — `Setscreen`, `Setpalette`,
`Setcolor`, `Vsync` — were answered `return 0` INSIDE `src/frontend.c`'s `xbios_trap_call` with no
`os_*` door under them, so no include-path seam could reach them and the target build reissued two of
them a slice late and the other two not at all. **A person found what that cost**: the presentation
picture played its whole digitised voice in the DESKTOP's palette, because `show_presentation`'s
`Setpalette` could not be reissued until after the slice whose next instruction is the `jsr` into
`GHOST.LOA`.

The kit now has doors for the group (`tools/recreate_kit/TRAP_MODEL.md`, Phase 14): each is an
ordered entry in the off-image OS event ledger and still touches no image byte, so `xbios_trap_call`
routes through them and the target shadows them with the real traps.

**The door found three missing calls the differential had been green over for the life of the
project.** `frame_blow_or_recover` (twice) and `frame_death_sequence` filed the trap trampoline's
three save slots and made no `Setcolor` call at all — so the ghost never changed colour when its
breath ran out. Forty-five cases in `test/test_gameplay.py` went red the moment the group became an
event and were green again once the calls were written. That is the residual this table's second row
used to name, retired by measurement rather than by argument.

What is still unpinned is `Setscreen`'s PHYSICAL base and its resolution: an event carries one
32-bit value and that call has three arguments, so the entry is the logical base alone.
`atari/README.md`'s "Unpinned" carries it.

## Performance — the baseline, and six waves measured on top of it

`atari/profile.py` is the instrument the performance campaign will run on: 1000 vblanks of Hatari's
CPU profiler on BOTH binaries, opened at the first arrival at `game_frame_update` and closed 1000
vblanks later, so a frame is a count rather than an estimate. A second mode, `frames`, times the
frames themselves off a per-arrival breakpoint and agrees with the profiler to 0.1%.

**First measurement, 2026-09-07: ours 809.2K cycles a frame (9.91 fps) against the original's
466.9K (17.18 fps) — x1.73.** `present_room` alone is +273K of that 342K gap, at x2.95: it copies
25,600 bytes a frame through `copy_longs_ascending`, which the shipped binary does in an unrolled
`move.l (a3)+,(a2)+` run at 21.9 cycles a longword and ours does at 57.4. The raster engine is
already at parity — our `trap #2` into the ROM VDI costs 268K a frame against the original's 280K.

**WHERE WAVE 5a LEAVES IT: 482.2K cycles a frame, 16.63 fps, x1.03** of the original's 466.9K /
17.18. Every wave below reports its OWN window against its own baseline, so a figure quoted
mid-section is that wave's and not this one — and this instrument's own spread is 0.3%, so hold a
change against the objdump too. **THIS HEADLINE IS WAVE 5a's WINDOW AND NOTHING ELSE'S**: waves 5b
and 5c were measured in their own worktrees at the same time and are NOT in it, so whoever merges
the three re-measures rather than adding the three savings up.

**WAVE 4 SAID THE CAMPAIGN STOPPED HERE UNLESS SOMETHING CHANGED SHAPE, AND WAVE 5a CHANGED THE
DOOR'S.** Its 18.6K was two rows — the shim's GEM door at 8.4K, which the shipped binary has NO
counterpart for because its parameter block already holds machine addresses, and the 200 Hz tick at
8.0K. Wave 5a took the door to 6.7K by making it one hand-written 68000 routine, and its own section
prices what is left in it line by line: the five-slot restatement (1.7K a frame) and the two MFDBs'
patch and restore (2.1K) are work the original does not do at all, and the mandatory `%d2/%a2` save
is 0.45K nobody may take. Nothing below is unspent work that someone forgot.

**Read the table with its instrument in mind.** A row is only a ratio where Hatari CHARGED both
sides; a routine the two binaries enter differently (an interrupt vector against a `jsr`) carries a
full total on one side and almost none on the other, and `compare` prints those under their own
heading instead of ranking them. The full table, the four things this instrument does not measure —
chief among them that the two windows are equal in vblanks and not in frames, which flatters the
slower side — and the usage lines are in `atari/README.md`, "Performance".

### Wave 1, 2026-09-07 — the copy runs

Every raw blit in this program was one helper, `include/common.h`'s `copy_longs_ascending`, and it
walked two 32-bit image OFFSETS: GCC kept the offsets and recomputed `image + offset` per longword
instead of postincrementing two address registers. It now walks two LOCAL cursors behind
`CURSOR_BARRIER`, in spelt-out blocks of `COPY_RUN_UNROLL` closed by one `COUNT_BARRIER`ed counter —
which is `present_room` @ 0x13286's own 32-fold unroll. The same shape now carries
`copy_longs_descending`, `clear_physical_screen`'s fill, and — spelt as its own four-longword row,
because a run of four is all loop control — the 32x32 tile blit that `objects_animate_and_draw`,
`draw_room_to_stage`, `draw_hud_row_tiles` and `draw_tile_bank_screen` each drive. The why of the
barriers is in `include/common.h` beside them, so that the next reader does not simplify them back.

**What the target objects say**, read off `m68k-elf-objdump -d` of the cores built with
`atari/build.sh`'s own flags. **This is codegen evidence, not a profiler window:**

| | before | after |
|---|---|---|
| the whole-region run | `image + offset` recomputed per longword — 57.5 cyc/longword measured | 32 x `movel %a1@+,%a0@+` to one `subql`/`bnes`: **20.6** cyc/longword |
| ...the same run in the shipped binary | | 32 x `move.l (a3)+,(a2)+` to one `dbf`: 20.3 in theory, **21.9** as Hatari charges it |
| the tile blit's row | 4 longwords through the helper, plus per-row call | 4 x `movel %a1@+,%a0@+` + `lea %a0@(144),%a0` + `subqw`/`bnes` — the original's own row |
| the wipe's descending run | `image + offset` recomputed per longword | the original's own `movel %a3@,%a0@` + two `subql #4`, with its `dbf` amortised over 32 of them |
| the cores' `.text`, all seven | 145,326 B | 146,204 B (**+878**); the size gate reported 74,034 B spare BEFORE this change |

**AND WHAT THE PROFILER SAYS**, taken once the change was committed (`3475866`) and `atari/build.sh`
would build it — the projection this paragraph used to carry was ~583K a frame and ~13.7 fps from the
copy runs alone, and the measured window came in under it:

| | before | after |
|---|---|---|
| `present_room`, inclusive | 412,937 cyc/frame, x2.95 the original's | **149,874, x1.07** |
| ...of which the run itself | 367,856 exclusive, all of it in the copy | 167 exclusive; the run is now its own row, `copy_longs_ascending` at **136,318** |
| `blit_tile_32x32` | inside a branch-entered ancestor, uncharged | its own row at 4,530 exclusive over 328 arrivals |

The projection undershot because it costed only the whole-region run; the tile blit's saving is in
the window too and this instrument could not predict it.

What IS pinned is that the change is behaviour-preserving: `make test` and `make guarded` are green
over the whole suite, and the gate was shown to fail on mutations of exactly this shape — one `step`
dropped from `UNROLLED_RUN_BLOCK` (191 failures) and the descending run walked upward (56 failures).

**AND WHAT THE DIFFERENTIAL CANNOT SEE IS THE WHOLE POINT OF THE CHANGE.** Every mutation above is a
mutation of BEHAVIOUR; what this wave buys is CODEGEN, and the suite is green either way. The first
draft of `copy_longs_descending` proved it: it read correctly, passed all 1,895 cases and
`make guarded`, and compiled to `lea -4(a3),a1 / lea -4(a2),a0 / move.l -4(a3),-4(a2)` — 44 cycles a
longword, WORSE than the 36 the original spends, because its `CURSOR_BARRIER` sat after the store
instead of the step. Nothing in the suite could say so; `m68k-elf-objdump -d` said it in one line.
**Read the objdump for any change to these runs.** The differential is the correctness gate and not
the performance one; `atari/profile.py` is the performance one, and until this is committed the
codegen claims above are **unpinned by any check** — that is the honest state of this row.

**Three facts this wave discovered, recorded because a green suite hides all three:**

* **The singles tail has ONE live caller in the whole program** — the bonus bar's 40-longword
  scanline. Every other count is an exact multiple of COPY_RUN_UNROLL (6400, 1280, 1024, 7680, and
  `room_wipe_in_step`'s present, always 160 x (step + 1)), so a tail that is short by one is green
  in all of them and red only through `test_gameplay.py` / `test_frontend.py`. `test_blit.py`, the
  battery that owns these helpers, does not reach it. The note is in `include/common.h` over
  `UNROLLED_RUN`, where the next editor of that loop reads it.
* **`include/common.h` is declared append-only by [`README.md`](README.md)**, and this wave rewrote
  the BODY of `copy_longs_ascending` rather than only adding beside it. The additions
  (`copy_one_longword`, `COPY_RUN_UNROLL`, `UNROLLED_RUN*`) are append-only and are shared by three
  cores as that rule requires; the body rewrite is recorded here rather than left to look like one.
* **The kit hoist trigger is now met, and is REGISTERED rather than done.** `copy_one_longword` is
  the same helper under the same name as `projects/wonderboy/recreate/include/scroll.h`'s, whose
  header names the trigger ("a user in ANOTHER project") and the home
  (`tools/recreate_kit/include/machine.h`); Zynaps' `src/init.c` registers three more copies of the
  same loop waiting on the same move. `include/common.h`'s header carries the registration. Doing it
  is a kit change plus a Wonder Boy re-verification, and is out of this wave's scope.

### Wave 2, 2026-09-07 — the shim's two costs: the GEM dispatch and the sound tick

`build.sh`'s committed-cores gate reads `src` and `include` and nothing else, so a change confined to
`atari/` builds and profiles while the cores are untouched — which is how these two were measured on
their own, before wave 1 landed: **809.2K cycles a frame -> 776.2K, 9.91 fps -> 10.33, x1.73 ->
x1.66**, with wave 1 not in it. **The two waves together: 809.2K -> 517.4K, 9.91 fps -> 15.50,
x1.73 -> x1.11** against the original's 466.9K and 17.18 — which waves 3a and 3b then carry to
489.1K / 16.40 / x1.05, the figure the top of this section quotes.

**The GEM dispatch, `bg_gem_dispatch` (atari/bubble_backend.c): 23.4K cycles a frame -> 10.2K,
x0.43.** Every `trap #2` marshalled the game's parameter block by patching its five (or six) pointers
in place, trapping, and putting them back; and a raster copy additionally COPIED each 20-byte MFDB
into the shim's own memory so that its `fd_addr` could be translated. That copy was most of the cost:
`g_src_mfdb` was a `uint8_t[]`, GCC knows a byte array's alignment is one, and every `wr32` through it
therefore became four byte stores while the copy itself became a 20-iteration byte loop — about 2,700
cycles a call over 8.6 calls a frame. The trap is now handed a block of the shim's OWN
(`g_machine_pblock`, a `uint32_t[]`, so one aligned `move.l` a slot) and the image's block is never
disturbed; the two MFDBs are patched IN PLACE, which is four longwords patched and put back instead
of forty bytes copied. The three sprite routines came down with it, against the original's own:
`save_sprite_backgrounds` x1.17 -> x1.09, `draw_sprites` x1.16 -> x1.10, `restore_sprite_backgrounds`
x1.16 -> x1.09.

**The 200 Hz sound tick, costed on BOTH sides for the first time — and the instrument is the
finding.** Hatari charges cycles to SUBROUTINE arrivals, and both binaries reach their handler off the
MFP's autovector: 3,330 ticks arrive on the shipped side and 21 of them are charged, so the row was
unmeasurable rather than cheap. `profile.py` now sums the profiler's per-ADDRESS data over each side's
own handler ranges (`SOUND_TICK_SYMBOLS`), which knows nothing about how an address was reached.
**Ours cost 4,011 cycles a tick against the original's 1,696-1,699 over two windows — x2.36, 10.0% of
our frame against 4.2% of theirs.** The tick's ABSOLUTE cost tracks how many voices happen to be
sounding, which the unseeded ambience re-roll varies window to window (3,451 to 3,899 over four later
windows, at 2.5 to 3.0 chip writes a tick), so the per-WRITE figure below is the one that is not a
coin toss. It ends at **3,887 a tick against 1,696, x2.29**, with both sides' ranges reported in bytes
(1,932 of ours against the shipped handler's 914) so that a later run can be held against this one.

Where the excess was: 814 of those 4,011 were the `trap #9` supervisor gate, which **the original's
ISR does not make** — its own `psg_gate` @ 0x14940 carries 0.7 cycles a tick, because the handler
writes $ff8800 itself and only USER-mode callers trap. A 68000 exception handler is already
supervisor, and `bg_timer_c_entry` never lowers the interrupt's own IPL 6, so both of the things the
gate provides are already true inside the tick; `bg_timer_c_tick` raises `bg_in_timer_c` for the
length of the call and `shim_include/psg.h`'s door wrote the ports through `bg_psg_write_super`
(bubble_os.s, the gate's own constants) instead of trapping — a routine **wave 3a then deleted**,
folding the two stores into the header itself. **A chip write went from 324 cycles to 100 exactly**,
over 2.5-3.0 writes a tick, in every window of this wave's.

**What is left is the CORE, and it is the next wave's — wave 3a below took both of the levers this
paragraph names, and the paragraph is left as the prediction it was.** `timer_c_sound_isr` plus the two step
routines GCC did not inline cost 2,770-3,165 cycles a tick over those windows, against the original's
1,696 for its whole handler — x1.7 to x1.9, the ordinary C-against-hand-asm gap, and now ~7% of a
517.4K frame. The other lever the review named and this wave did not take: `bg_psg_write_super` was a
`jsr` with two stack arguments around two `move.b`, so most of its 100 cycles was call plumbing —
`projects/zynaps/recreate/atari/shim_include/psg.h` writes the ports inline instead, which would need
the port addresses spelt in a header plus a build.sh gate pinning them equal to `bubble_os.s`'s, and
was worth about 0.7% of a frame — and wave 3a spent it, spelling the ports in `shim_include/psg.h`
with exactly that gate. The lever named in `src/sound.c` was real and unspent: its accessors were
`field_w(image, record, OFFSET)` — a name wave 3a replaced with `record_w`/`record_l`, so a grep for
it now finds nothing — and each recomputed `image + record + offset` per field where the original
walks one `a0` cursor. It is a CORE change, so `build.sh` refused it until it was committed, which
is why this wave did not take it and wave 3a did.

**Unpinned, and it is this wave's own finding.** Nothing on target watches the PSG. The differential
pins the (register, value) pairs the core computes, and `smoke.py` pins that the handler runs
(`TIMER_C_TICKS`) and does not fault, but no check reads a byte back off the chip — so the six
instructions that carry a pair to the ports are covered by review and by the constants they share
with the gate, not by a surface. One failure mode IS caught: a flag wrongly left set makes the next
user-mode write to $ff8800 a bus error, which the fault scan reds on.

Two smaller gaps in the same place, recorded rather than closed. `build.sh` counts the `hw_write8`
call sites the CORES make but nothing counts the places the SHIM writes $ff8800 — that went from one
to two here and a third would land silently. And `bg_in_timer_c` is the first shim variable whose
value changes which branch a VERIFIED CORE takes (`core_sound.o` now carries `U bg_in_timer_c`); what
it selects is only HOW the same (register, value) pair reaches the same chip, but the containment
gate measures which HEADERS a core reaches and cannot see the class at all.

### Wave 3a, 2026-09-07 — the sound tick's CORE, and the last call on the chip-write path

**What wave 2 left named and unspent, taken: 3,906 cycles a tick -> 2,423, and 517.4K cycles a frame
-> 496.4K (15.50 fps -> 16.16, x1.11 -> x1.07 against the original's 465.3K / 17.24).** The tick was
9.7% of a frame and is 6.0%; against the shipped handler's 1,693 it was x2.31 and is **x1.43**. Both
windows are a back-to-back pair from one session in a throwaway worktree — the only way `build.sh`'s
committed-cores gate will build a modified core at all — and the original's window was re-measured in
the same session rather than quoted from wave 2's. **That re-measurement is why this section's
denominators differ from wave 2's by a fraction of a percent throughout**: 1,693 here against wave
2's 1,696-1,699 for the same shipped handler, and 465.3K against 466.9K for the same frame. Neither
side changed; the window did.

| | before | after |
|---|---|---|
| the whole tick | 3,906 cyc/tick | **2,423** |
| `timer_c_sound_isr` + `step_swept_envelope` + `step_triangle_lfo` | 2,095 + 583 + 476 = 3,154 | **~1,990**, one symbol |
| the ISR's YM2149 write | 100 cyc in `bg_psg_write_super`, ~40 more in plumbing | **~32**, two `move.b`s inline |
| `bg_timer_c_entry` / `bg_timer_c_tick` / `bg_write_byte` | 148 / 224 / 56 | unchanged |
| the tick's share of a frame | 50.4K a frame, 9.7% | **30.0K, 6.0%** |

**The core lever was the one `src/sound.c`'s header used to disclaim.** `field_w(image, record, off)`
recomputed `image + record + off` for every field; the record's base is now resolved ONCE per voice
as a host pointer and each field is `d16(An)` off it, which is exactly what the original's `a0` does
for the whole of a voice's tick. **THE 68000's ADDRESS WRAP DID NOT DISAPPEAR, IT MOVED, and the
review is why the line is where it is.** Three addresses in this file can go somewhere a host pointer
cannot follow, and all three are still built with `addr_add`: the record base (`voice_record`'s
`adda.w` of a sign-extended word product — `sound_voice_priority` range-checks nothing and a voice
index of 372 must reach an address BELOW the array), the handler's own cursor as it walks DOWN one
record a voice (a base under 0x1a4 goes round the bottom), and the volume table's SIGNED word index.
A pointer is formed from each only once it is final, and always as `image + <that wrapped
uint32_t>` — the shape `include/common.h`'s `word_at` has used all along, and the one
`guarded_image.py` sizes `GUARD_ABOVE = 1 << 32` for. The first draft let the
cursor and the table index be plain pointer arithmetic, which is both formally UB and a QUIETER
failure than the old spelling: `image - 140` is a heap scribble `make test` cannot see where
`addr_add`'s `0xffffff74` faulted loudly.

**One thing the accessors DID drop, and it is UNPINNED rather than unpinnable** (a second review
pass, same day): the field displacement of 0..0x8a is now added to the POINTER, so `cursor + 0x8a`
does not wrap where the 68000's `d16(a0)` does. It is reachable — any `SND_ISR_TOP_VOICE` below
0x1a4 walks the descending cursor round the bottom, and 0x10 puts the second voice's base at
0xffffff84 — and **`make guarded` IS the surface, which this section's first draft got backwards.**
Its reserve runs from `image + PROGRAM_BYTES` to `image + PROGRAM_BYTES + (1 << 32)`
(`guarded_image.py`), so the pointer form's `image + 0xffffff84 + 0x8a` lands INSIDE it and faults,
where the address form wraps to `image + 0x0e` and reads the image: the two spellings are tellable
apart by a seeded case, and **no case seeds one**. What is not free is the FIX — giving the
accessors an address back is the whole 1,483 cycles a tick this wave bought — so the class is
recorded here and at `timer_c_sound_isr` rather than closed. `make guarded` is green over all 1,895 cases, and it is
**not** the surface for an offset one FIELD out — 0x8c either side of a record is the neighbouring
record, which is image. Wonder Boy's `include/actor_view.h` has a host-only `REC_WITHIN_RECORD`
assert for exactly that class; this file is the second user of the shape and `src/sound.c` REGISTERS
the hoist rather than making it.

`step_swept_envelope` and `step_triangle_lfo` are `static inline` with it. They are each called
twice with CONSTANT offsets, and out of line those offsets became index registers plus four `jsr`s
with three stack arguments each; inlined, the offsets fold. **The objdump is the evidence and the
suite is not**: 109 `d16(An)` accesses in the ISR's code against 10 that still index a register (the
three ISR-state reads, the volume table's own `(a1,a0.w)` — the original's `move.w (a2,d0.w),d0` —
the cursor, and the two segment selects GCC folds into one body rather than two), no libgcc
arithmetic call anywhere in the object (the volume multiply was already a native `muls.w`), no local
text symbol at all, and the only `jsr`s left inside the handler are the five `bg_super_gate` calls on
the user-mode arm of `psg_port_write`, which the ISR never takes. `core_sound.o`'s `.text` grew
5,004 -> 5,090 B (+86).

**And the shim's half, which wave 2 had named at "worth about 0.7% of a frame":**
`shim_include/psg.h`'s untrapped write was a `jsr` into `bubble_os.s` with two stack arguments
around two `move.b`, and most of its 100 cycles was the plumbing — the two stores that replaced it
profile at 32 a write (the declined-levers list below), so the call was carrying about 68.
`psg_untrapped_write` is those two
stores inline now and `bg_psg_write_super` is DELETED rather than left dead.

**It masks NOTHING, and that is the ORIGINAL'S OWN ASYMMETRY rather than a saving.** The original's
ISR loads `a1` with $ffff8800 once @ 0x145a6 and makes all five of its write pairs bare — @ 0x14682
(volume), 0x14780 and 0x14788 (the tone period's halves), 0x1485c (noise) and 0x1487c (key-off), on
a register number it built as `voice + 8`, `2 * voice` (+1) or a constant and never bounded — while
its `and.b #$f,d1` is in the trap handler alone @ 0x1495c. So our two doors disagree about the mask
exactly where the original's two do. The review asked whether they should be made to agree, and the
answer is MEASURED rather than argued: `reg & 15` in the inline store compiles to the same bytes,
`core_sound.o` byte-identical at 5,090 B, because GCC proves every call site's register number
small. It is still left out — a free mask would smooth an asymmetry the original has, and it would
hide a precondition rather than state it. **The precondition is real, and what holds it is a SURFACE
rather than the chip.** The header's earlier draft argued the mask away with "16 selects register 0
on the machine, on the original and through either door" — a hardware claim nothing in this
workspace has measured, and the review was right that it is at best unproven (the AY-3-8910 compares
the upper nibble against its own chip address and stops responding; the YM2149 replaced those pins
with /CS). It is WITHDRAWN rather than replaced by its opposite, because this build depends on
neither: the kit's `psg.h` REFUSES a register above 15 instead of masking it down, so a caller that
ever grew one is red under `make test` before anything is built for the target, and on our side of
the seam the ISR's own numbers are at most 10 while `trap9_psg_handler` masks with
`PSG_REG_SELECT_MASK` before it calls. Note the kit's header states the REFUSAL but gives the
four-bit-decode rationale, so the two files agree on what to do and not on why.

So the port and its data displacement are the only two numbers BOTH DOORS need, and `atari/build.sh`
pins them exactly as it already pins the supervisor gate's three operation codes. **`PSG_REG_MASK` is
deliberately NOT in that loop**, and `build.sh`'s own comment says why: the untrapped door has no
mask to pin it against, so a third entry there would be pinning the header to a constant it must not
grow. **That is not the same as saying the mask needs no pin** — `bubble_os.s`'s `PSG_REG_MASK = 15`
and `include/sound.h`'s `PSG_REG_SELECT_MASK = 0x0f` ARE one chip fact in two languages, both citing
`and.b #$f,d1` @ 0x1495c and both the TRAPPED door, and CLAUDE.md §5 wants that pair pinned. It is
not, and nothing reds if either drifts; recorded in "Still unpinned" below rather than closed here,
because scraping `include/sound.h` is a new pattern and this wave was already editing `build.sh`.

**A STORE INLINED INTO A VERIFIED CORE IS A STORE NO COUNTED DOOR SEES**, and that is what this
wave's two new gates are for — the `hw_write8` census counts call sites the cores make and cannot see
an absolute `move.b` the compiler put there:

| gate | what it refuses |
|---|---|
| `>> the chip's 2 ports agree between psg.h and bubble_os.s, the ISR's store is those 2 stores and nothing else, and only the trapped door masks` | the two constants disagreeing with `bubble_os.s`'s (shown: a `BG_PSG_DATA_OFFSET` of 1), an empty or partial scrape on either side, a body that is not those two stores in select→data order (shown: the pair swapped), a store whose VALUE is not the bare argument (shown: an added `& 15`), and a `bg_super_gate_entry` that has lost its `andi.l #PSG_REG_MASK` (shown: the line deleted) |
| `>> the sound tick's helpers are inlined` | an out-of-line `step_swept_envelope`, `step_triangle_lfo` or `psg_untrapped_write` in any object. `static inline` is a HINT, and `profile.py` refuses a tick-range name that vanishes but cannot see one that APPEARS — a helper that stopped being inlined would take its cycles out of the sum AND cut `timer_c_sound_isr`'s range short at itself, so the tick would read low twice over with nothing red |

**AND THE INLINING GATE WAS VACUOUS FOR AN HOUR, WHICH IS THE TRANSFERABLE HALF.** Its first draft
was `m68k-elf-nm $OBJECTS | grep -q "[Tt] $NAME$" && { ...refuse... }`, and `build.sh` runs under
`set -euo pipefail`: `grep -q` closes the pipe on its FIRST match, `nm` dies of SIGPIPE, and the
pipeline's status becomes 141 — so **the one case the gate exists to catch is the one case the `&&`
does not fire on.** A `__attribute__((noinline))` on `step_swept_envelope` compiled, left
`t step_swept_envelope` in `core_sound.o`, and the build printed the gate's green line. It reads
`grep -c` over the whole stream now, reds on that same mutation, and carries a control asserting the
scrape names `timer_c_sound_isr` exactly once. `build.sh`'s pre-existing `__ORDER_BIG_ENDIAN__` probe
has the same shape and fails CLOSED (a lucky direction, not a designed one); it is left alone and
named here.

**AND THE PORT GATE WAS VACUOUS FOR THE ONE MUTATION THIS WAVE'S ARGUMENT RESTS ON**, found by the
second review pass. Its body scrape was
`sed -n 's/^ *\*(volatile uint8_t \*)\(.*\) = .*;$/\1/p'` — the `= .*;` swallowed the whole value
expression, so it pinned WHERE each store goes and not WHAT it stores. `(uint8_t)(reg & 15)` in the
select store therefore passed it green, and since the object is byte-identical and `make test` never
compiles this header, the twenty-odd lines arguing the untrapped door must NOT mask had no surface at
all: the mask could have been added back and every check in the tree would have agreed. The scrape
now pins both store lines WHOLE, and a second check pins the trapped door's own
`andi.l #PSG_REG_MASK,%d1` present exactly once in `bubble_os.s` — the other direction, in which
deleting one instruction makes the two doors agree silently. Three mutations were run against the
pair and all three red: the added `& 15`, the store pair swapped, and the `andi.l` deleted.

**Still unpinned, and named rather than closed:** nothing on target reads a byte back off the chip
(wave 2's finding, unchanged), and the kit already owns the two ports as `OS_PSG_PORT_SELECT` /
`OS_PSG_PORT_DATA` in its 24-bit bus form. This build cannot reach them — its `hw_write8` IS the
trap gate, and the widening to $ffff8800 lives only in `bubble_os.s`'s `BUS_HIGH_BYTE` — so the
reuse is REGISTERED in `shim_include/psg.h` beside the two `#define`s, with what closing it needs.

Two more from the second review pass, both recorded rather than closed:

* **The trapped door's mask is one chip fact in two languages and is not pinned across them.**
  `bubble_os.s`'s `PSG_REG_MASK = 15` (on target) and `include/sound.h`'s
  `PSG_REG_SELECT_MASK = 0x0f` (the verified core's `trap9_psg_handler`) both transcribe
  `and.b #$f,d1` @ 0x1495c, and nothing holds them equal: `build.sh` scrapes neither, and off target
  the differential agrees with itself because both sides of the model use the C constant. The shape
  is a third entry in the port loop, scraped from `bubble_os.s` and `include/sound.h` rather than
  from `shim_include/psg.h`. CLAUDE.md §5's case, and this wave did not take it.
* **Nothing seeds a `SND_ISR_TOP_VOICE` that reaches the field-displacement wrap**, which is what
  would turn the residual above from unpinned into pinned — `make guarded` is demonstrably the
  surface, the case is what is missing.

**What the differential can and cannot say about this wave.** Nothing here is a behaviour change, so
`make test` and `make guarded` are green either way and are the CORRECTNESS gate, not the performance
one — `atari/profile.py` is the performance one and the objdump is the codegen one. Two mutations
were run to show the gates are not vacuous: the ISR's record cursor walked UP instead of down
(`cursor += SND_VOICE_BYTES`) reddened 29 cases from a forced relink, and the `BG_PSG_DATA_OFFSET`
of 1 above was refused before a byte was compiled. Restored, both green. The second review pass added
three more against the port gate once its scrape was widened — the `& 15`, the swapped store pair and
the deleted `andi.l` — all refused, all restored.

**What the pre-commit review caught that neither instrument did**, recorded because it is the same
two-instrument point this file already makes about `c_open`: the cursor's lost wrap and the table
index's (both green in every case), the mask that contradicted the original, `psg_write_ports`
sitting one word-order away from `psg_port_write` (a transposition compiles to either infinite
recursion or a user-mode bus error), a port gate that read two missed `sed` patterns as two agreeing
zeroes, three read-only routines taking a writable record, and `load_definition` walking a cursor on
one side and re-adding on the other.

**TWO LEVERS MEASURED AND DECLINED, both with their number**, so the next wave does not re-derive
them:

* **The ISR's $484 mirror** still goes through `bg_write_byte` (56 cyc/tick in the callee, ~105 with
  its plumbing). Spelling it as a direct `*(volatile uint8_t *)TOS_CONTERM = ...` store in
  `bg_timer_c_tick` measured **2,298 cycles a tick against 2,343 — 45 cycles, 0.11% of a frame** (an
  A/B pair taken before the review fixes below, so both sides are 33 cycles under the final figure)
  — and made GCC emit `-Warray-bounds` ("source object is likely at address zero") on every build. A
  permanent warning for an eighth of a percent is a bad trade. If it is ever taken it belongs in
  `bubble_os.s` beside the other machine primitives, where the store is one instruction and no
  warning.
* **The `bg_in_timer_c` test in front of every chip write: 50.8 cyc/tick**, summed off the same
  per-address data (2.1% of the tick, 0.13% of a frame; both shares re-derived from this section's
  own 12.4 ticks a frame, after a review found the first draft printing 0.3% and 0.03% for 45 and
  50.8 cycles of the same tick, which cannot both be right) — the flag is `volatile`, so it is a real
  load and a real branch at each of five write sites, and inside the ISR it is true by construction.
  Nothing behaviour-preserving is available without a SEAM change: the verified core can only see
  the kit's `psg_port_write`, and the door under it is what decides trapped or not. Priced here
  rather than left silent. For scale beside it, the two port stores themselves cost **95.3 cyc/tick**
  over ~3 writes — 32 cycles a write, which is the figure the table above quotes.

**What is left in the tick, honestly — and WAVE 4 TOOK 154 OF IT** (that section's table; the
sentence below is left as the reading it was). 2,423 against 1,693 is still x1.43, and the residue
is structural rather than a lever: `bg_timer_c_entry` + `bg_timer_c_tick` + `bg_write_byte` are 428
cycles the original does not spend at all (it saves its own seven registers and juggles `%sr` inline
for ~200), our `movem` saves ten registers to its seven, and GCC's loop control is ~184 against the
`dbf`'s ~124. The BODIES are already at parity where both sides do the same work — the two `muls.w`
rows measured 53.6/49.6 against 57.5/51.7.

### Wave 3b, 2026-09-07 — the per-frame game logic: the Alcyon fp package

**MEASURED TWICE, in a throwaway worktree off the same committed baseline wave 3a used** —
once for the change and again after the pre-commit review moved two more loops; the numbers below are
the second window, which is the code that ships (`build.sh`'s
committed-cores gate has no override, so a modified `src/clib.c` cannot otherwise be built). This
wave and wave 3a touch DISJOINT tiers — this one is `src/clib.c`'s floating-point package plus
`atari/bubble_backend.c`, and nothing in the sound path — so the two "after" windows are two
independent measurements of the same 517.4K frame and not a sum — the merge is measured below.

| | before | after |
|---|---|---|
| cycles/frame, whole window | 517.4K | **509.5K** |
| fps | 15.50 | **15.74** |
| ...against the original's 466.9K / 17.18 | x1.11 | **x1.09** |
| `game_frame_update`, inclusive | 46,472 cyc/frame, x1.49 | **38,638, x1.24** |
| `frame_scale_mouse_to_ghost`, inclusive | 23,184 cyc/frame | **15,218** |
| `fp_dispatch` | 8,959 cyc/call, x2.26 | **5,368, x1.36** |
| `fp_pack_double` | 974 cyc/call | **786** |
| `fp_acc_load_long` | 1,617 cyc/call, x1.41 | **1,295, x1.13** |
| the whole package, over its two calls a frame | 22,647 cyc/frame | **14,595** (the original's 11,438) |
| `bg_gem_dispatch`, exclusive | 10,552 cyc/frame over 8.65 calls | **10,353** |

**AND THE MERGE IS MEASURED, not left as arithmetic.** Wave 3a landed as code (`5c7a9de`) while this
was in review, so both waves were built together in a third worktree and BOTH sides were profiled in
one session:

| | wave 2 | 3a alone | 3b alone | **both** |
|---|---|---|---|---|
| cycles/frame | 517.4K | 496.4K | 509.5K | **489.1K** |
| fps | 15.50 | 16.16 | 15.74 | **16.40** |
| against the original's 466.9K / 17.18 | x1.11 | x1.06 | x1.09 | **x1.05** |
| the 200 Hz tick | 3,906 cyc/tick | 2,423 | 3,889 | **2,434** |

They compose: 517.4 − 21.0 − 7.9 = 488.5 predicted against 489.1 measured, which is what two disjoint
tiers should do and is worth having rather than assuming. **The original was re-measured in the same
session and came back at 466.9K / 17.18 — wave 2's figure exactly**, so the quoted denominator above
is the live one after all. It is also why the 3a column reads x1.06 here and x1.07 in wave 3a's own
section: the same 496.4K, over that session's own reading of the original (465.3K / 17.24).

**AND THE PREDICTION THIS WAVE MADE CAME TRUE, which is the point of having made it.** The three
sprite rows were x1.09-x1.10 with only wave 3b in, and the claim above was that almost none of that
was the VDI — it was the tick nested in their inclusive totals, so halving the tick would collapse
them with no work on the sprite path at all. With both waves in they read **x1.05, x1.05, x1.05**,
and `present_room` went x1.08 -> x1.03 by the same mechanism. `game_frame_update` is x1.49 -> **x1.18**
over the two waves.

**TWO LOOPS, AND THE OBJDUMP FOUND BOTH.** The differential is green on either side of this change —
it is codegen, exactly as wave 1's was — so `m68k-elf-objdump -d` of the cores built with
`atari/build.sh`'s own flags is the whole evidence:

| loop | before | after | the original |
|---|---|---|---|
| `fp_div`'s divisor halving, once a step, 32 steps a call | `moveq #31,d5 / lsl.l d5,d3` — the register shift at 8 + 2 a bit = **70 cycles** — in a 166-cycle step | `lsr.l #1 / roxr.l #1` (20) in an **80**-cycle step | the same pair @ 0x1523c, in a ~64-cycle `dbf` step |
| ...and its compare + subtract | `cmp.l` + `beq` + `cmp.l` + two `sub`s over four halves | a `sub.l`/`subx.l` pair whose result is thrown away, THEN the real one — GCC does not fold them | `cmp.l`/`bcs`/`bne`/`cmp.l`/`bhi` (~14) then `sub.l`/`subx.l` |
| `fp_pack_double`'s normalise, up to 23 passes a call | 40 cycles a pass (the outgoing bit read BEFORE the shift keeps two values live across the back edge) | **22**: `subq.w #1,d1 / add.l d0,d0 / bpl` | 24: `subq.w #1,d3 / asl.l #1,d2 / bcc.s` @ 0x153a4 |

The C says it as the machine does now: `fp_div`'s remainder and divisor ARE the 68000 register pairs
d2:d6 and d7:d4, so they are one `uint64_t` each rather than two halves, and the normalise loop is
"shift while the top bit is still clear" plus the one last shift that carries a 1 out — with the +1
that shift owes taken BEFORE the loop, which is what stops GCC keeping the pre-decrement exponent
live in an address register and is the last 4 of the 18 cycles. Both bodies carry the measurement
beside them so the next reader does not simplify them back.

**The row the reviewers corrected, and it is the useful kind of correction.** The first draft of
`fp_div`'s note claimed GCC "folds the compare and the subtract into one `sub.l`/`subx.l` pair". It
does not — the objdump shows a whole throwaway compare in front of the real subtract, and the
cheaper spelling (`if (remainder - divisor <= remainder)`) is WORSE, because GCC recomputes it and
adds two `movea.l` shuffles. The ~10 cycles a step that leaves is not reachable from C. In a repo
whose stated performance gate IS `m68k-elf-objdump -d`, a codegen claim the objdump refutes is the
drift that gate exists to stop. **[WAVE 5c: the last sentence was wrong — those ~10 cycles WERE
reachable from C, by asking for the two 32-bit HALVES instead of the pair; the throwaway compare is
gone and the step is at the original's own 64/78. The rest of the paragraph stands, including that
the difference-form spelling is worse. See wave 5c below.]**

**The GEM door's own row moved 302 cycles a frame, which is INSIDE the instrument's ~2% noise**, and
is carried on the objdump instead: `A_vdi_contrl` is 0x236f0, past the 68000's signed word
displacement, so every `contrl` slot cost `move.l #145136,d0` plus an indexed `(0,a2,d0.l)` access
(26-32 cycles) and is now `d16(An)` off one `CURSOR_BARRIER`ed address register (16-20). **Hoisting a
plain local buys nothing** — GCC re-folds the constant into the index — which is the transferable
half and was measured before the barrier was added; deleting the barrier again puts every slot back
on the indexed form, +56 B of code. The cursor and its barrier live INSIDE the `selector == GEM_VDI`
arm, because an AES dispatch never reads a `contrl` slot and the first draft made it materialise the
base anyway. That costs the AES path nothing and the room loop measures nothing either way — the
window's 8.65 GEM calls a frame are all VDI.

**WHAT THE MUTATION SWEEP SAID, including the one that survived**, each from a forced relink
(`rm -f build/*.so`) with `__pycache__` swept:

| mutation | result |
|---|---|
| `FP_DIV_STEPS` 32 -> 31 | **RED**, 98 failures |
| the normalise tail's folded `exponent + 1u` -> `+ 2u` | **RED**, 186 failures |
| `fp_div`'s `divisor <= remainder` -> `divisor < remainder` | **GREEN — and it is an equivalent mutant, not a coverage hole** |
| the peeled `mantissa <<= 1` dropped, `test_fp_pack_float_direct` ALONE | **RED**, and it was not before |

The last row is the test movement this change owes. The FLOAT tail's battery had no
vector that drove the shared normalise loop more than one pass — every deep one lived in
`test_fp_pack_double_direct` — so it covered the loop only while the two tails share one copy of it,
which the file's own note says they are written NOT to. Two vectors (23 passes and 15) close it, and
the row above is the anti-vacuity proof that they did: the same mutation is green against the old
list and red against the new one.

The `<=` row is worth the space. The equality arm IS reached by the suite — `test_fp_arithmetic_edges`
divides 1.0 by 1.0, where remainder equals divisor at step 0 — and the raw quotient really does
differ (0x80000000 against 0x7fffffff). What absorbs it is the shared packing tail: 0x7fffffff
normalises to 0xfffffffe, whose guard and sticky bits are both set, so the round carries it back to
0x80000000 with the exponent restored. A model of `fp_div` + `fp_pack_double` was run over 4,000
`x/x` pairs, 4,000 pairs sharing a mantissa and 60,000 constructed pairs that hit the equality at a
step past the first (4,992 of them did) — **not one packed result differs.** The arm is transcribed
from the original's `beq`/`cmp.l`/`bhi` and pinned by the differential's agreement with the real
68000 code on the inputs that reach it; it has no output of its own for a test to hold.

**NEITHER LOOP NAMES A SURFACE, AND THAT IS RECORDED RATHER THAN CLOSED.** Both changes are codegen:
the differential is green on the fast spelling and on the slow one alike, so nothing in this tree
reddens if a later editor "simplifies" `uint64_t divisor` back to two halves, re-parenthesises a
`contrl` access, or moves to a GCC whose lowering differs. `atari/build.sh` already carries codegen
scans (a postincrement/indexed-EA scan, an endianness scan) and the shape of the fix is a third —
refuse a register-form `lsl.l %dN,%dN` inside `fp_div`, assert the `roxr.l #1` count, refuse a
`move.l #145136` inside `bg_gem_dispatch`. It was NOT added: `build.sh` was being edited by wave 3a
in the same working tree. **Unpinned, and it is this wave's own finding.**

**REGISTERED, NOT DONE — TWO KIT-SHAPED FACTS.** `include/common.h`'s header states the rule (a
measurement about the ISA belongs in `tools/recreate_kit/include/machine.h`; an idiom of this
program belongs here) and its own "REGISTERED, NOT DONE" paragraph is the precedent for naming a
hoist rather than making it. Two of this wave's findings are the kit's, not this game's:

* **A 68000 register pair that is SHIFTED must be one `uint64_t`; a pair that is only added or
  subtracted may stay two halves.** That is how m68k GCC lowers, not how Alcyon compiled — and
  `machine.h`'s own `long_add_extend`/`long_sub_extend` note currently recommends the two-half
  spelling without the caveat, so the next project reads the 70-cycle form as house style.
* **`CURSOR_BARRIER` has a second use: pinning a BASE that never advances**, so GCC cannot re-fold a
  large constant back into an indexed access. `machine.h` documents only the postincrement cursor,
  and the measurement for the second use is in this file's wave 3b (wave 5a deleted the C it was
  written over; the assembly's `movea.l %d1,%a1 / adda.l #A_VDI_CONTRL,%a1` is the same fix by
  hand) where no other project will
  find it. It applies to every project with a data symbol past the signed-word displacement.

Both are a kit change plus a re-verification of Wonder Boy and Zynaps, which is more than this wave.

**WHAT THIS WAVE MEASURED AND DID NOT TAKE**, so the next one does not re-derive it:

* **`fp_float_to_double` keeps the two-half spelling this wave's own note condemns**, deliberately.
  Its `(low >> 1) | (bit << 31)` costs the same 70-cycle register shift, ~390 cycles a call — but
  its high half needs an ARITHMETIC shift (the `asr.l #1 / roxr.l #1` triple STATUS calls "the shape
  a port gets wrong"), it runs three fixed passes, and **it has no caller in the room loop at all**:
  all four `fp_dispatch` sites pass an eight-byte source, so the widening never runs. A cold path,
  a sign-semantics risk, and out of a perf wave's remit. The clause is in `fp_div`'s note so the
  file does not read as two contradictory examples of one construct.

* **The core VDI wrappers are already at parity and there is no lever there.** `vro_cpyfm`,
  `vdi_trap`, `vdi_call`, `vdi_set_mfdb` and the two `sprite_pxy_*` writers cost 6,824 cyc/frame
  across the three sprite routines, against the original's 6,431 for the same work. Writing the
  eight-word `blit_pxy` behind a `CURSOR_BARRIER` was costed off the objdump at ~110 cycles a call
  (252 -> 140) and comes to ~0.7K a frame at the price of churning a verified core. NO-GO.
* **The GEM door still holds ~800 cycles a call above its floor.** At 1,166 cyc/call it spends ~280
  in `build_machine_pblock`'s five- or six-slot loop and ~600 staging and restoring the two MFDBs,
  and GCC spills the six `SavedMfdb` values across the `jsr` rather than holding them in the eight
  callee-saved registers it leaves unused. Returning the struct by value was tried in a scratch
  compile and spills identically. A floor of ~360 would be worth ~7K a frame; it needs the door
  restructured, which is more than this wave's remit.
* **The three sprite rows' x1.09 is NOT the VDI**, and this is the finding of the wave. Their +26K a
  frame is 6,824-vs-6,431 in our wrappers, 7,320 in the shim door, and **~18K of Timer C tick nested
  inside their inclusive totals.** The mechanism shows up unmistakably in one row: `copy_longs_ascending`
  is a leaf and its inclusive exceeds its exclusive by 14,001 cyc/frame — 28% of our 50K tick, in a
  function that calls nothing. Hatari pushes `bg_timer_c_tick` on the callstack because the ISR
  `jsr`s to it, so the interrupt lands in every ancestor's INCLUSIVE; on the shipped side nothing
  `jsr`s and the same cycles land in the interrupted routine's EXCLUSIVE. **Halving the tick collapses
  those three rows as a side effect**, and no work on the sprite path would have — which the merged
  window above then confirmed, at x1.05 each.

### Wave 4, 2026-09-07 — the GEM door and the 200 Hz tick's shim, and where the last 18.6K is

**489.1K cycles a frame -> 485.6K, 16.40 fps -> 16.52, x1.05 -> x1.04** against the original's
466.9K / 17.18, whose window is wave 3b's and was not re-run because nothing on that side moved.
`atari/` only: `git` says `src/` and `include/` are untouched and `build.sh`'s committed-cores gate
agrees, so `make test`'s 1,895 cases are green either side of this and are NOT its evidence.

**THIS WAVE DID NOT REACH PARITY, AND THE REST OF THE SECTION IS WHY.** The two levers it took are
spent; every remaining one is measured and named below with its number, and the two biggest are
structural rather than unspent.

| | before | after |
|---|---|---|
| cycles/frame, whole window | 489.1K | **485.6K** |
| frames in 1000 vblanks / fps | 273 / 16.40 | **275 / 16.52** |
| ...against the original's 466.9K / 17.18 | x1.05 | **x1.04** |
| the GEM door, exclusive | `bg_gem_dispatch` 10,241 a frame, **1,184 a call** | `bg_gem_dispatch` 3,100 + `raster_copy_call` 5,311 = **8,411**, **971 a call** |
| the 200 Hz tick | 2,434 cyc/tick, 29.7K a frame | **2,297, 27.8K** |
| ...of which the shim's own half | 428 (`bg_timer_c_entry` 148 + `bg_timer_c_tick` 224 + `bg_write_byte` 56) | **~296**, one routine |
| `save_sprite_backgrounds` / `draw_sprites` / `restore_sprite_backgrounds` | x1.05 / x1.05 / x1.05 | **x1.04 / x1.05 / x1.04** |
| `game_frame_update`, inclusive | 37.1K, x1.19 | **36.6K, x1.17** |
| `shim_bubble_backend.o`'s `.text` | 576 B | 688 B (**+112**); the size gate reports 72,512 B spare |

**THE INSTRUMENT'S OWN SPREAD IS 0.3% AND THIS WAVE IS 0.7%**, so the figure is worth having but not
by much: four windows of the finished code over one session read 485.6K three times and 487.1K once,
and an intermediate build read 483.9K. Every number above is a single window; the objdump below is
what actually carries the argument.

**THE GEM DOOR: 1,184 cycles a call -> 971, and every one of those 213 came off the objdump.** The
door was a flag-guarded stage/restore pair around ONE trap call, so the six values the restore needs
had to be initialised on the paths that stage nothing — and GCC then kept all six in the stack frame
and reloaded them around the `jsr`, fifteen stack accesses at 16 to 28 cycles each, with the eight
callee-saved registers the door leaves free going unused.

| | before | after |
|---|---|---|
| the raster path, whole | 1,186 cycles hand-counted off the objdump | **~1,100** |
| ...the same source with `raster_copy_call` INLINED | | 1,190 — the spills come straight back |
| ...`build_machine_pblock` or `stage_and_trap` left out of line | | 836 B of object against 688, and the six back in the frame |
| the parameter block's five slots | 230 cycles, closed against an ABSOLUTE end address (`cmpal #imm32,%a0` at 14 where a `dbf` is 10) | **~250 with the sentinel, 202 without it** — spelt out, GCC drops the postincrements for a displacement read and an absolute store |
| `machine_address`'s base | the global `bg_image_base`, re-materialised per slot once a branch split the block | the `mem` the caller already holds, in one data register for the whole body |

**`noinline` ON ONE HELPER AND `always_inline` ON TWO IS THE MEASUREMENT, not decoration.** With a
frame of its own the raster body is straight-line and its six values live in d2-d5/a2-a4 across the
trap; inlined it, or left either staging helper out of line, and they go back to the stack. Three
spellings were tried and recorded in the file so the next reader does not re-derive them: barriering
the staging run's SOURCE cursor moves the read off the postincrement (72 cycles a slot against 46),
barriering its DESTINATION cursor stops the function being inlined at all, and writing the slot as a
function taking its two cursors instead of a macro reaching for two locals by name is
**byte-identical** — which is why it is written the house way (`../include/common.h`'s
`copy_one_longword`) rather than the fast-looking way.

**THE 200 Hz TICK'S SHIM HALF: 428 cycles a tick -> ~296, one routine instead of three.** Wave 3a
priced the $484 mirror at 45 cycles and declined it because the C spelling
(`*(volatile uint8_t *)TOS_CONTERM = ...`) makes GCC warn on every build, and named `bubble_os.s` as
where it belongs if it were ever taken. Taken: `bg_timer_c_entry` is now the WHOLE tick outside the
ISR — the count, the supervisor flag, the ISR call and the mirror — and `bg_timer_c_tick` is deleted
rather than left as a wrapper. **428 was the BEFORE figure and not the saving**; the profiler puts
the whole tick at 2,434 -> 2,297, which is 137 a tick and 1.7K a frame.

| | before | after |
|---|---|---|
| `bg_timer_c_entry` | `movem` + `jsr` + `movem` + chain, 148 | the whole tick, **~296** |
| `bg_timer_c_tick` (bubble_main.c) | 224 — pushing the image base, RELOADING it after the ISR, pushing two arguments at `bg_write_byte` for one `move.b` | **deleted** |
| `bg_write_byte` in the tick's path | 56 | **gone**; the mirror is one `move.b CONTERM(%a0),CONTERM` |
| the tick, whole | 2,434 cyc/tick | **2,297** (the ISR body is 1,996 of it, unchanged) |

**THE IMAGE BASE IS READ TWICE ON PURPOSE, and the 16 cycles that costs are the interesting part.**
The cheap spelling pushes it as the ISR's argument and POPS IT BACK for the mirror — but the m68k
SysV ABI makes a callee's incoming argument area the CALLEE's scratch, and GCC really does spill a
modified parameter into its own incoming slot. `timer_c_sound_isr` does not today (`core_sound.o`
reads `%sp@(48)` and never writes it), and if a later edit to `../src/sound.c` ever made it, this
entry would mirror a byte read from a garbage address into TOS's $484 two hundred times a second —
a MACHINE write, so no differential sees it and no screenshot tells it apart.

**AND THE ADDRESSES `bubble_os.s` SHARES WITH A C HEADER ARE NOW ONE LOOP, not three copies of one.**
$484 is the third entry — scraped from the VERIFIED core header `../include/sound.h` (`TOS_CONTERM`,
the address the sound ISR clears IN THE IMAGE) and from `bubble_os.s` (`CONTERM`, the address the
tick mirrors it TO) — and the two PSG ports are the other two, folded into the same
scrape/refuse-empty/normalise/compare body they always were. A second check pins the mirror
instruction present exactly once **INSIDE `bg_timer_c_entry`**, scraped label-to-label the way
`assert_trap_registers.sh` reads routines: a file-wide grep would have been satisfied by the store
having been moved somewhere the interrupt never reaches, which is exactly the regression the gate
exists for. `mirror_conterm`'s one-shot poke already leaves the machine byte at 0, so `smoke.py`'s
`CONTERM_AT_ANCHOR` check passes whether or not the per-tick mirror runs — this gate is the only
thing in the tree that can see it go.

**AND THE FOUR WIDTHS THE ASSEMBLY NOW HARD-CODES ARE PINNED IN C**, because moving the tick into
assembly moved them out of the compiler's sight: `bubble_main.c` carries a `_Static_assert` on each
of `bg_timer_c_ticks`, `bg_timer_c_chain`, `bg_in_timer_c` and `bg_image_base`. Widening
`bg_in_timer_c` to an `int` is the one that bites with no diagnostic anywhere — `clr.b` would clear
only the big-endian top byte, the flag would read true for ever, and `psg.h`'s door would send every
USER-mode chip write straight at $ff8800.

**WHERE THE LAST 18.6K IS, AND WHY PARITY IS NOT REACHABLE FROM HERE.** Read off the per-function
exclusives, with the shipped side's rows discounted by the 4.25% of its frame its own interrupt
spends inside them (Hatari charges an autovectored ISR to whatever it landed in, so every shipped row
carries a share of its 19.8K tick):

| | ours | the original | over |
|---|---|---|---|
| the GEM door — the shim's translation layer | 8,411 | **nothing at all** | +8.4K |
| the 200 Hz tick | 27,809 | 19,839 | +8.0K |
| the ROM VDI itself (`bg_gem_trap` against `vdi_call`) | 270,285 | ~267,802 | +2.5K |
| the fp package | 13,347 | ~11,056 | +2.3K |
| the sprite routines + the core VDI wrappers | 6,887 | ~6,147 | +0.7K |
| the raw copy runs + the object tier | 143,928 | ~143,711 | +0.2K |
| `get_pixel` + `bubble_collision_probe` | 6,315 | ~7,880 | **-1.6K** |
| everything else (the vq/vsf wrappers, the HUD, the console poll) | | | ~-2.0K |

**TWO ROWS ARE 88% OF THE GAP, and both are structural.**

* **THE DOOR HAS NO COUNTERPART AND CANNOT ACQUIRE ONE.** Every pointer the cores put in a GEM
  parameter block is an IMAGE OFFSET — that is what makes the differential's world and the original
  both right — so a `trap #2` here has to restate the block, and the shipped binary's block already
  holds machine addresses. What is left, priced: the five-slot restatement is ~250 cycles a call
  (2.2K a frame) of work the original never does; the two MFDBs' stage and restore ~250 a raster
  call (1.5K a frame), likewise; `movem` and the call frame ~280 a raster call (1.7K a frame); and
  `bg_gem_trap`'s own `movem.l %d2/%a2` pair is MANDATORY at 52 cycles a call (450 a frame) — the
  workspace's one hardware-only bug class (`docs/on-target-execution.md` taxonomy 3), not a saving
  anyone may take. **Caching the block was re-measured on the new shape and is still NO-GO**:
  `../src/frontend.c`'s `vro_cpyfm` and `vr_recfl` each lend the VDI their own `pxy` as `ptsin` and
  put the library's array back afterwards, so the block really does change between calls, and a
  cache must re-read all five longwords to know it — the read is 16 of the ~50 cycles a slot costs.
* **THE TICK'S REMAINING 8.0K IS 6.0K OF ISR BODY AND ~1.2K OF ENTRY.** Ours is 1,996 cycles a tick
  against the shipped handler's 1,704, and that 1,704 INCLUDES its own `movem.l #$f0e0` and `%sr`
  juggling (~200), so body against body it is ~+490 a tick. Wave 3a took every lever in it and the
  objdump says so: 109 `d16(An)` accesses, all four helpers inlined, no libgcc call anywhere. What
  is left is C against hand-asm, legible in two shapes — the volume table's base is kept in a STACK
  slot and re-formed per voice (`moveal %sp@(40),%a1 / addal %a4,%a1`, 24 cycles) where the original
  holds it in `a2` for the whole handler, and word fields land in ADDRESS registers
  (`moveaw %a2@(34),%a0 / clrw %d6 / cmpw %a0,%d6` at 30 against the original's `tst.w 34(a0)` at
  12). Both are worth **300 to 900 cycles a frame, 0.06% to 0.19%**, and both are a core edit plus a
  re-verification. Named, not taken.

**THE OTHER LEVERS, EACH WITH ITS NUMBER, SO THE NEXT WAVE DOES NOT RE-DERIVE THEM:**

* **`bg_gem_trap`'s argument plumbing: ~64 cycles a call, 550 a frame, 0.11%.** The caller spends
  `pea`/`pea`/`addq #8` and the callee two `move.l 12(%sp)` loads to reach one instruction, where
  the original's `vdi_call` @ 0x168d4 puts both operands in registers as IMMEDIATES. Two
  argument-less entry points would take it, at the price of exporting `g_machine_pblock` to
  assembly and a fourth entry in `build.sh`'s two-language loop. NO-GO on ratio.
* **`machine_address`'s 0 test: ~46 cycles a raster call, ~400 a frame, 0.08% — and it is NOT
  available, which this wave learned by taking it and being caught.** The first draft split the rule
  in two on the argument that only an MFDB's `fd_addr` can be 0. It is false: `init_globals` leaves
  all five of `A_vdi_pblock`'s longwords ZERO and `v_opnvwk` fills `intin`/`intout`/`ptsout` but not
  `ptsin`, so the FIRST VDI call of every run is made with a ptsin of 0 — and the shipped binary
  makes it with a ptsin of 0 too. Translating it hands TOS a non-null pointer where the original
  hands NULL. **Both smokes were green on the unfaithful version**, because that call declares zero
  ptsin PAIRS and TOS never dereferences what it was handed. The reasoning is in the file over
  `machine_address`, not only here.
* **`bg_in_timer_c`: 40 cycles a tick to set and clear, plus 50.8 for the `volatile` test in front
  of each chip write — 1.1K a frame, 0.23%.** Unchanged from wave 3a: nothing behaviour-preserving
  is available without a seam change, because the verified core can only see the kit's
  `psg_port_write` and the door under it is what decides trapped or not.
* **The fp package: +2.3K a frame** after wave 3b took its two loops (`fp_dispatch` alone is 8,946
  exclusive against 8,191). NO-GO on ratio.
* **The copy runs and the object tier are AT PARITY** (143.9K against ~143.7K) and `get_pixel` +
  `bubble_collision_probe` are 1.6K AHEAD. There is nothing to take there, and this row is here so
  that nobody spends a wave looking.

**WHAT THE MUTATION SWEEP SAID, INCLUDING THE TWO THAT SURVIVED — AND THE SURVIVORS WERE THIS WAVE'S
FINDING.** Each from a full `atari/build.sh` and the smoke or compiler it names. The last three
rows are the GEM door's: the first two of them were RE-RUN against the second-arrival anchor below
and carry both verdicts, and the third is new to that re-run.

| mutation | result |
|---|---|
| `CONTERM = 0x486` in `bubble_os.s` | **REFUSED** by the two-language loop, by name, before a byte was compiled |
| the `move.b CONTERM(%a0),CONTERM` line deleted | **REFUSED**: "scraped 0 times INSIDE bg_timer_c_entry" |
| the same store MOVED to `bg_read_long`, a routine the interrupt never reaches | **REFUSED** by the same check — which a file-wide grep would have passed |
| `bg_in_timer_c` widened to `volatile uint32_t` | **REFUSED** at compile time by its `_Static_assert` |
| `VDI_POINTER_LONGS` 5 -> 4 | **REFUSED** by both of `build_machine_pblock`'s asserts |
| `addq.l #1,bg_timer_c_ticks` deleted | **RED**: `smoke.py title`, "memory (the program's own record)" — *the 200 Hz Timer C handler never fired* |
| the DESTINATION MFDB's raster restore deleted | **GREEN in both smokes, before and after the second-arrival anchor — and it is an EQUIVALENT MUTANT, not a coverage hole** (below) |
| the SOURCE raster's translation deleted — the door hands the VDI an image OFFSET as an address | **GREEN in both smokes** before; **RED** after: `smoke.py game`, "memory + hardware-state vector", *414 of 32,000 framebuffer bytes differ after one whole room frame* |
| the DESTINATION raster's translation deleted — the same fault on the other operand | **RED**: the ROM VDI takes a Bus Error writing at `$fffefffe` (PC `$fc9378`) and the CPU halts. Added by the re-run, because the restore above turning out equivalent left the destination operand pinned by nothing else |

**THE GEM DOOR'S MFDB TRANSLATION HAD NO SURFACE IN THIS TREE AT ALL — CLOSED**, by the fix the wave
named. The hole was read out of `smoke.py` rather than guessed: `check_the_room_state` compared the
framebuffer at the FIRST arrival at `game_frame_update` (`arm_the_room_anchor`'s
`b pc = $room_pc :once`), which is BEFORE that frame has drawn anything, so no `vro_cpyfm` had run
into it; and the `title` mode, the one with a byte-for-byte pixel comparison, makes no `vro_cpyfm` at
all — the title screen is drawn with the game's own raw blitters. So the whole `raster_copy_call`
body was pinned by nothing but the objdump and the fact that a human sees the ghost move.

**WHAT CLOSED IT:** `arm_the_room_anchor` now arms a SECOND breakpoint on the same room-frame PC and
dumps the framebuffer there too — `b pc = $room_pc :2 :once`, Hatari's "break only on every `<count>`
hit" (`help b`, 2.6.1; it rejects an explicit `:1`, which is why the first arrival's line carries no
count). Two breakpoints on one PC keep their own hit counts, so the pair fires on CONSECUTIVE
arrivals — measured on 2.6.1 before it was relied on. The second arrival is the END of the first room
frame, after `save_sprite_backgrounds`, `draw_sprites`, `present_room`, `restore_sprite_backgrounds`
and `objects_animate_and_draw`, so the displayed framebuffer carries the ghost and the bubble AS THE
VDI DREW THEM THROUGH THE DOOR. It is a deterministic program point on both sides in exactly the way
the first arrival is, and the "four blanks later" objection does not reach it (that objection is
about a WALL-CLOCK capture landing on either side of the erase/redraw cycle,
`arm_the_room_anchor`'s own note).

**BOTH CAPTURES ARE BYTE-IDENTICAL TO THE ORIGINAL'S** — 0 of 32,000 differing at each — and the two
of them differ from EACH OTHER by exactly 361 bytes on BOTH sides, which is the ghost and the bubble.
(That 361 is entry-against-drawn WITHIN one run; it is not the 556 the anchor's docstring also
quotes, which was ours-against-the-original at a wall-clock settled moment and is the measurement
that argued for dumping memory AT the instruction in the first place.) `check_the_room_state`
asserts the difference as its own control: a second capture equal to the first is not a second
arrival, and without it a miscounted breakpoint would compare the same pre-`vro_cpyfm` moment to
itself and pass. That the second arrival is the ADJACENT one is read off the two runs' logs — ours
stops at VBL 2,039 and 2,042, the original at 2,145 and 2,148: one ~3-VBL room frame apart on each
side.

**AND ONE SURVIVOR SURVIVED THE NEW ANCHOR TOO, because it is an EQUIVALENT MUTANT — and so is the
WHOLE RESTORE HALF of `raster_copy_call`, which is the part of this row that generalises.** Deleting
the destination MFDB's raster RESTORE leaves a machine address in the game's own `A_mfdb_dst` after
the trap, and the program never reads it: every one of its `vro_cpyfm` call sites writes BOTH
`A_mfdb_src + MFDB_ADDR` and `A_mfdb_dst + MFDB_ADDR` immediately before the call
(`src/frontend.c` 549-607: seven call sites, all reaching the VDI through one `sprite_copy`). The
same argument retires the other three restores unread: `vro_cpyfm` itself re-stages `contrl[7..10]`
through `vdi_set_src_mfdb`/`vdi_set_dst_mfdb` on every call (their bodies, which wave 5c re-enters
through a base-taking `_at` pair rather than by address), so both
`set_contrl_long` restores are dead, and so is the source raster's. **What the second arrival closed
is the TRANSLATION half, not the restore half.** The restores stay — they keep the game's image
faithful rather than merely working — but they are recorded here as equivalent BY CONSTRUCTION,
exactly like `fp_div`'s row above, so that a later wave pricing them at the ~250 cycles a raster call
this file quotes knows a green sweep is not evidence they are safe to drop.

**WHAT THE SECOND ARRIVAL STILL CANNOT REACH**, named here rather than left for the next sweep to
rediscover:
* **The sprite-background round trip.** The capture reads `phys`, and VDI output reaches `phys` only
  through `present_room` (`src/blit.c` 117). Frame 1 runs save-backgrounds -> draw-sprites ->
  present_room -> restore-backgrounds, so arrival 2 sees `draw_sprites`' source translation but not
  what `save_sprite_backgrounds` wrote into `A_ghost_bg`/`A_bubble_bg` — that reaches `phys` at
  frame 2's `present_room`, i.e. arrival THREE. So the destination operand is pinned here only in
  its CRASHING form (the Bus Error row above); a mistranslation that still landed in valid RAM would
  need a third arrival, which is one more `savebin` and one more row in `ROOM_CAPTURES`.
* **The aliased-MFDB guard.** `destination_mfdb != source_mfdb`, and the staged-slot flag that hangs
  off it, are unreachable in this program by the door's own admission (wave 5a's
  `bg_gem_raster_copy`, `raster_copy_call` before it) — no call site passes the same MFDB twice — so no capture at any arrival can distinguish them.

**What the pre-commit review caught that neither instrument did**, recorded because it is the same
two-instrument point this file makes about `c_open` and about wave 3a's cursor: the ptsin-of-0 above
(green everywhere, unfaithful on target); the image base parked in the callee's own argument slot;
the mirror gate that proved only that a string occurred somewhere in the file; four operand widths
that left the compiler's sight with the tick; an assert that pinned the difference between two
counts and not either count; a `profile.py` comment still arguing for a name the same diff removed;
and a third hand-written copy of the two-language scrape that had already drifted from the other two.

### Wave 5a, 2026-09-08 — the GEM door as one hand-written 68000 routine

**483.8K cycles a frame -> 482.2K, 16.58 fps -> 16.63, x1.036 -> x1.033** against the original's
466.9K / 17.18. **The whole-window move is INSIDE this instrument's own 0.3% spread and is not this
wave's evidence** — the door's own row is, and it moved by a fifth over 2,396 calls:
**8,493 cycles a frame -> 6,702, 984 a call -> 775.** (The 485.6K **wave 4 below reports** is a
DIFFERENT window of the same wave-4 binary; the 483.8K above is the saved `profile-ours.json` this
wave was measured against, which is the honest before.)

**AND 6,702 IS AN UPPER BOUND ON THE SHIPPED DOOR.** The window above was taken BEFORE the
pre-commit review, which then took ~8 more cycles off each of the three paths (the entry builds the
block cursor in `%a0` so no arm has to move it there; `bne` went short). The shipped hand count is
406 / 412 / 878 against the 414 / 416 / 886 that was profiled — about 70 cycles a frame better, not
re-measured, and the direction is not in doubt.

**MEASURED IN A SCRATCH WORKTREE OF `b8ad1b0`, so the two waves running beside this one are not in
the window**: the cores are HEAD's (`make test`, 1,895 cases, green), and the 200 Hz tick this window
profiles is wave 4's C-calling entry, not 5b's assembly twin. Everything below is `atari/` only.

**THE DOOR IS NOW ONE ROUTINE IN `atari/bubble_os.s`.** `bg_gem_dispatch` with `bg_gem_aes_call` and
`bg_gem_raster_copy` as its two branch-entered arms, and `bg_gem_trap` — four instructions — as the
only routine here that traps. `bubble_backend.c`'s `bg_gem_dispatch`, `raster_copy_call`,
`machine_address`, `build_machine_pblock`, `stage_and_trap`, `stage_one_pointer`, `contrl_long`,
`set_contrl_long` and `g_machine_pblock` are DELETED; what is left in that file is the three counters
and the three libc functions. The counters stay in C so that a `_Static_assert` pins the width the
assembly's `addq.l` assumes — wave 4's rule for `bg_timer_c_entry`'s four globals, applied again.

| | before (C) | after (asm) |
|---|---|---|
| the GEM door, exclusive | `bg_gem_dispatch` 3,055 + `raster_copy_call` 5,438 = **8,493** a frame | one row, **6,702** — **-21%** |
| ...a call, over 8.63 / 8.65 of them a frame | **984** | **775** |
| a non-raster VDI call, hand-counted | 498 + `bg_gem_trap`'s 100 | **406 + 68** (414 as profiled) |
| a `vro_cpyfm`, hand-counted | 264 (the dispatch prologue) + 840 + 100 = 1,204 | **878 + 68** (886 as profiled) |
| an AES call, hand-counted | 518 + 100 | **412 + 68** (416 as profiled) |
| `bg_gem_trap`'s row (the ROM VDI) | 268,918 a frame | 269,543 — unchanged, as it must be |
| `shim_bubble_backend.o` + `bubble_os.o`, `.text` | 688 + 958 = **1,646 B** | 134 + 1,290 = **1,424 B (-222)** |
| ...their `.bss` | 36 B (the staged block + the counters) | 36 B, the staged block now in `bubble_os.s` |

**THE HAND COUNT AGAINST THE PROFILER, which is the check on both.** The window is 5.99 `vro_cpyfm`
calls and 2.66 others a frame (1,658 and 738 arrivals over 277 frames), so the door's hand-counted
frame is `5.99 x 886 + 2.66 x 414 = 6,408` against a measured **6,702: Hatari charges 4.6% over the
68000's own tables.** The same sum for the C door is `5.99 x 1,104 + 2.66 x 498 = 7,938` against a
measured 8,493, **+7.0%**. (Both sums price the whole 2.66 bucket at the non-raster VDI figure; the
AES call inside it is 2 cycles dearer, which is inside the 5% and is said here rather than left for
the next reader to find.) Both deltas are the emulator's bus and prefetch model over a textbook
instruction count, and the two differ because the two bodies have different instruction shapes — so
**a hand count is worth about 5% here, and is the right instrument for a change this size** (0.3% of
a frame is inside the profiler's spread; a fifth of a 2,396-call row is not).

**WHAT IS LEFT IN THE 6,702, PRICED, because none of it is unspent work.** Every figure in the two
number columns is HAND-COUNTED off the objdump — the profiler charged the door 6,702 as ONE row and
never charged any of these six sub-rows, so a later wave cannot verify a change against them
directly. Each per-frame figure is its per-call figure times this window's own call rate (8.65 door
calls a frame, 5.99 of them `vro_cpyfm`).

| | a call | a frame | why it stays |
|---|---|---|---|
| the five-slot restatement | 200 | **1,730** | 40 cycles a longword: load 12, the zero test 8, the add 8, the store 12. `movem.l` in and out of a five-register block counts the SAME 200, and a cache must re-read all five to know the block changed — which wave 4 measured as NO-GO and this shape does not move |
| the raster path's MFDB patch and restore | ~356 | 2,132 | two MFDBs, four longwords, each staged and put back. The work the original never does at all |
| the raster path's 7-register `movem` pair | 132 | 791 | the seven values that must survive the trap (two raster slots + what they held, `contrl`, two MFDB offsets). Pushing them singly is 24 a register against `movem`'s 16 |
| the three counters, `addq.l #1,xxx.L` at 28 | 28-56 | 410 | STATE.BIN publishes all three and `smoke.py title` pins them at 68/3/60 |
| `bg_gem_trap`'s `movem.l %d2/%a2` | 52 | 450 | MANDATORY — `docs/on-target-execution.md` taxonomy 3, the workspace's one hardware-only bug class. It is in `bg_gem_trap`'s row, not the door's |
| the `jsr` to `bg_gem_trap` — its `rts` is the other 16 and is inside `bg_gem_trap`'s own 68, not the door's row | 18 | **156** | **A DELIBERATE 0.06%** (the pair is 34 a call, 294 a frame). Hatari charges an exception's whole ROM execution to the symbol that issued the `trap`, so folding the trap into the door would merge 269.5K of ROM into the door's row and cost the campaign the one row that holds `bg_gem_trap` against the original's `vdi_call`. Bought back only by giving up the measurement |

**THE TARGET WAS ~120 CYCLES A NON-RASTER CALL AND ~350 A `vro_cpyfm`; THE FLOOR IS 414 AND 886, and
the arithmetic above is why.** The restatement alone is 200 of any call and the mandatory `movem` 52;
a 120-cycle call would have to not restate the block, and the block really does change between calls
(`../src/frontend.c`'s `vro_cpyfm` and `vr_recfl` each lend the VDI their own `pxy` as `ptsin`).

**THE ELEVEN CONSTANTS THE DOOR IS BUILT OUT OF ARE PINNED IN TWO LANGUAGES.** Moving the door to
assembly moved `GEM_VDI`, `GEM_AES`, `VDI_VRO_CPYFM`, the four `contrl` indices, `MFDB_ADDR`,
`MFDB_SCREEN_ADDR`, the two block lengths and `A_vdi_contrl` out of the compiler's sight and into
immediates — exactly the drift CLAUDE.md §5 is about, and exactly what wave 4 did for the tick's
four operand widths. `build.sh`'s two-language loop grew from 3 entries to 14, and the eleven are
the two selectors; `VDI_VRO_CPYFM`; the THREE `contrl` word indices the door reads
(`VDI_CONTRL_OPCODE`, `VDI_CONTRL_SRC_MFDB`, `VDI_CONTRL_DST_MFDB`); `MFDB_ADDR` and
`MFDB_SCREEN_ADDR`; and `VDI_PB_PTSOUT` and `AES_PB_ADDROUT`, which are each block's LAST index and
not its length — **ten** from `tools/recreate_kit/include/os.h` — plus `A_vdi_contrl` from
`../include/frontend.h`. Each is scraped back out of the header that owns it and refused on a
disagreement. The loop's `sed` now takes the `u` suffix as
OPTIONAL, because the kit spells `GEM_VDI 0x73u` and `VDI_CONTRL_SRC_MFDB 7`. Two more pins are the
ASSEMBLER's own, which is stronger than a scrape: `.ifne MFDB_SCREEN_ADDR / .error` refuses a
sentinel that is no longer 0 (the door tests for it with `beq`, which can only test zero), and
`.ifgt VDI_POINTER_LONGS-AES_POINTER_LONGS / .error` refuses a VDI block that no longer fits the
staging area sized for the AES's. **Both were shown to fire** before they were relied on.

The two block LENGTHS are derived rather than spelt: `VDI_POINTER_LONGS = VDI_PB_PTSOUT + 1` and
`AES_POINTER_LONGS = AES_PB_ADDROUT + 1`, off the kit's own index for each block's last slot. Wave 4
recorded that an assert on the DIFFERENCE of two counts is green for the wrong pair; deriving both
from the kit removes the pair.

**THE MUTATION SWEEP, RE-RUN AGAINST THE ASSEMBLY.** Wave 4's three surviving-then-closed rows were
re-run against this door, plus one the two-language loop is new for.

| mutation | result |
|---|---|
| the SOURCE raster's translation dropped — the door hands the VDI an image OFFSET as an address | **RED**: `smoke.py game`, *419 of 32,000 framebuffer bytes differ after one whole room frame, first at 10153* (the C door's own mutation reddened 414 at the same check) |
| the DESTINATION raster's translation dropped | **RED**: Bus Error **writing** at `$ffff8800`, PC `$23408`; 0 room frames, 3 of 3 checks red |
| `VDI_CONTRL_DST_MFDB` 9 -> 10 in `bubble_os.s` | **REFUSED** by the two-language loop, by name, before a byte was compiled |
| `CONTRL_DST_MFDB_SLOT` off by ONE WORD — the DERIVED offset, which the pin above cannot see | **RED**: Bus Error **reading** at `$30ef7300`, PC `$12986`; 0 room frames, 3 of 3 checks red |

The first two are wave 4's own mutations and red in the same shape; the last two are the pair that
matters for an assembly door, because a slot index in assembly is an immediate rather than a macro —
one of them is caught by the build and the other by the second-arrival capture, and neither is caught
by both.

**TWO NARROWINGS THIS WAVE MADE ON PURPOSE, recorded because neither has a surface.**

* **Anything that is not the VDI selector is the AES.** The C door passed the CALLER's selector
  through to `d0` while choosing the block length by comparing it to `GEM_VDI`; the assembly traps
  with `GEM_AES` as an immediate. `shim_include/os.h` has exactly two doors into this routine
  (`os_vdi` and `os_aes`), so a third selector cannot arise today — but it would now be serviced as
  an AES call rather than passed on, and **NOTHING WATCHES THAT.** `build.sh`'s `os_*` scan asserts
  that every kit helper a CORE calls is shadowed; it says nothing about how many doors call
  `bg_gem_dispatch` or with what selector. Recorded as unpinned rather than claimed as covered.
* **`bubble_mfdb.h` has one includer instead of two.** It reconciles the kit's `MFDB_ADDR` with
  `../include/blit.h`'s, and `bubble_backend.c` was one of the two translation units that pulled both
  in. `bubble_main.c` still does, so the `_Static_assert` still runs — and it matters MORE now, since
  the door takes the kit's spelling through `build.sh` and the cores take `blit.h`'s. The header says
  so.

### Wave 5b, 2026-09-08 — the 200 Hz tick as the ORIGINAL'S OWN INSTRUCTIONS

**The handler is no longer compiled.** `src/asm/sound_tick.S` is a hand-written m68k routine carrying
`timer_c_sound_isr`'s C signature, and 792 of its 856 bytes are the shipped binary's own
0x145be..0x148d6 **byte for byte**. `atari/bubble_os.s`'s `bg_timer_c_entry` calls it instead of the
C core; the C core stays linked, stays the reference, and is what this file's twin is verified
against.

**WHY IT IS THE FIRST CORE THIS BUILD DOES NOT RUN.** Every other row of `atari/README.md`'s seam
inventory is a verified core running as written. This one is not, and the reason is the instrument:
the room loop has no Vsync, so cycles a frame ARE the game's speed, the tick runs 200 times a second
inside it, and wave 3a had already taken every lever out of the C body (d16(An) field access, every
helper inlined, no libgcc call). What was left was C against hand-asm, priced at ~7K a frame in wave
4's NO-GO ledger and left there as "structural". It was not structural; it was a transcription
nobody had written yet.

**WHAT IT BOUGHT, one window each side in one session (`atari/profile.py`, 1000 vblanks opened at
the first arrival at `game_frame_update`):**

| | before (wave 4) | after | the original |
|---|---|---|---|
| the 200 Hz tick | 2,297 cycles | **1,842** (-20%) | 1,697 in this window, 1,704 in wave 4's |
| ...as a share of a frame | 28.0K cyc/frame | **21.9K** (-6.1K) | 19.8K |
| the frame | 485.6K cyc, 16.52 fps, x1.04 | 476.8K, 16.82 fps, x1.02 | 466.9K, 17.18 fps |

**THE FRAME FIGURE IS NOT THIS WAVE'S ALONE and the tick figure is.** This wave was measured in its
own worktree, cut from the shared tree, so its window carries WAVE 5a's GEM door as well; against
5a's own 482.2K the difference is 5.4K, which is the tick row's 6.1K inside this instrument's 0.3%
spread. The headline above says the same thing from the other side: whoever merges the three waves
re-measures rather than adding the savings up. The TICK row has no such problem — it is summed over
the tick's own symbol ranges, which no other wave touches.

**THE TARGET WAS 1,750 A TICK AND THIS IS 1,842 — 92 CYCLES OVER, and the 92 are structural
rather than unspent.** What is left is not in the handler at all: the transcribed body IS the
original's, instruction for instruction, so the whole difference is the eleven instructions around
it plus `bg_timer_c_entry`, which the shipped binary has no counterpart for — it IS the $114 vector,
where ours is a C-ABI routine called from one. Three levers were priced and none of them is free:

| lever | worth | taken? |
|---|---|---|
| the second pointer load reusing `%d0` with an 8-bit displacement, and `movea.w` for a sign-extending `$ffff8800` | 16 cyc/tick | **TAKEN** — measured on Musashi first (a flat 16 on all four staged cases, image and ledger identical over twelve differential runs) and then in the window: 1,858 -> 1,842 |
| a second entry point taking the image in `%a3`, so the entry stops pushing and popping it and one `movem` pair goes | ~85 cyc/tick | NOT taken. Real, and the largest of the three — but it still lands at ~1,760 and costs another build/smoke/profile round at the end of a wave |
| folding `bg_timer_c_entry` into the `.S` so the vector lands IN the twin: no `jsr`, no argument, one `movem` of eight | ~100 cyc/tick | NOT taken, and it is the only one that crosses 1,750. It moves target-only interrupt glue into `src/asm` behind `RECREATE_HOST_DIFFERENTIAL`, which kit.mk's own note says may carry a link stub and nothing else — a seam decision rather than a tuning one |

**AND IT RETIRES ONE OF WAVE 4's NO-GO ROWS.** Wave 4 priced `bg_in_timer_c` at "40 cycles a tick
to set and clear, plus 50.8 in the tests it arms" and closed it with "nothing behaviour-preserving
is available without a seam change". The seam change is this wave: with no C running inside the
interrupt the flag has nothing to say, so the 40 is banked here and the 50.8 is now spent on a
branch no call site on the interrupt's path reaches.


**THE PIN IS A SECOND DIFFERENTIAL, and it needs no second model of the chip.** The twin writes
`$ffff8800`/`$ffff8802` with the original's own bare `move.b` pairs — the same instruction stream in
both builds, no `#ifdef` anywhere in the file — and the kit's oracle decodes those two ports in its
memory callback (`tools/recreate_kit/oracle/shim.c`, `m68k_write_memory_8`). So a twin run under
Musashi leaves its register writes in the ORACLE's PSG ledger while the C core's `psg_port_write`
leaves them in the CANDIDATE's, and `test/test_sound_asm.py` compares the two streams beside the
whole image:

    original ==(test_sound.py)== timer_c_sound_isr ==(test_sound_asm.py)== timer_c_sound_isr_asm

**Its coverage is the C battery's own coverage**, not a second case list: `test_sound.py::isr_case`
calls `assert_twin_matches_the_c` for every case it stages — thirteen batteries, two of them fuzzes
and one of them all 47 shipped definitions — and `test_the_c_battery_runs_the_twin` fails if that
call goes missing. Four more checks sit on top of it: the 792-byte transcription against the .PRG,
a cost bar (the twin may not cost more than the original's own handler, on Musashi's counter, over
four staged shapes), a positive control that a staged case really drives the chip, and
`test_constants.py::test_asm_twin_equates_match_the_headers`, which reads every `.equ` back out of
the assembled OBJECT and refuses one that has drifted from its C header.

**EACH PIN WAS SHOWN TO BE INDEPENDENTLY LIVE**, by mutation, with the build forced (`rm -rf
build/asm` before every rebuild — a same-second edit is enough for `make` to relink nothing and
report a live mutant as survived, `docs/agent-playbook.md` §10):

| mutation | what caught it |
|---|---|
| `.equ SND_VC_VOL_DECAY_STEP` 0x0e -> 0x12 (one field displacement) | 19 failures: the transcription pin AND the differential |
| the voice counter one short (`moveq #SND_VOICES-2`) — OUTSIDE the transcribed span | 32 failures: the differential alone, the byte pin being blind here by construction |
| `.equ BG_PSG_DATA_OFFSET` 2 -> 3 — the image comes out IDENTICAL | 31 failures: the PSG ledger comparison alone |
| one `cmp #imm,%d0` re-encoded as CMPI — same behaviour, different bytes | 1 failure: the transcription pin alone |
| `.equ SND_VC_PRIORITY` 0x72 -> 0x70 | the equate pin alone, naming the header it disagrees with |

The first sweep of these lied once and is recorded so the next one does not: a `sed` whose pattern
had the wrong column count edited nothing, `make` rebuilt nothing, and the suite reported the mutant
as SURVIVED. What made it visible was printing the line before and after the edit.

**WHAT IS NOT TRANSCRIBED, and why each one is a difference rather than a defect:** the prologue (a
C function saves the callee-saved half of the register set a vector handler must save whole); the
two pointer loads (the original reads `&snd_volume_scale` and `&snd_voice[2]` from its own TEXT and
uses them as absolute addresses, because the program IS the memory — here they are read out of the
image and the base added, `image + address`, which is what `src/sound.c` does); the `$484` write
(the twin writes the image's mirror, which is what a differential can see, and `bg_timer_c_entry`
copies that byte out to the machine — `atari/build.sh`'s conterm-mirror gate is what keeps that
store there); and the `sr` work — the original drops from IPL 6 to IPL 5 so other MFP channels can
nest inside it, which this build has never done and still does not. The first is a residual already
on this file's list; the rest are the seam.

**TWO LINES LEFT `bg_timer_c_entry` WITH THE SUBSTITUTION.** `bg_in_timer_c` is no longer raised —
it exists so that a chip write made from inside this interrupt skips the `trap #9` gate, and nothing
C runs inside the interrupt any more. The flag, its `volatile` declaration and
`psg_untrapped_write` all stay, for the user-mode callers that still take the gate and for the
argument `atari/shim_include/psg.h` spends a page making; what is gone is 40 cycles a tick arming a
branch nothing takes. And the image base is now POPPED rather than re-read: the reason it was read
twice — the m68k SysV ABI makes a callee's incoming argument area the callee's scratch, and GCC
really does spill a modified parameter into its own slot — does not reach a hand-written callee
whose 856 bytes never name `%sp` after its prologue. NOT the transcription pin's doing, and the
first draft of this row said it was: that pin brackets the transcribed body and the prologue is
outside it. `test_sound_asm.py::test_the_twin_never_stores_through_its_own_frame` is the check that
holds it, over the twin's own source, matching `%a7` as well as `%sp` because they are one register.

**WHAT IS UNPINNED, said plainly.** The four instructions outside the transcribed span are covered
by the differential (they run on every case) but not by the byte pin, and `bg_timer_c_entry` itself
is covered by neither — it is interrupt glue, which no differential in this workspace reaches
(`docs/on-target-execution.md` class 3). What watches it is `atari/build.sh`: the conterm-mirror
scrape, the trap-register scan, and two new gates. The first asks the LINKED DISASSEMBLY, inside
`bg_timer_c_entry`'s OWN BLOCK, which of the two handlers the vector reaches — one call to the twin,
none to the C core — because calling the core again would boot, play, sound identical and cost 440
cycles a tick more with nothing else in the tree able to say so. (Scoped to the block, not the file:
`../src/sound.c`'s harness glue is linked in too and reaches the core through a `bra` and an `%a2`,
so a file-wide count would be asserting GCC's tail-call decisions.) The second compares the 792
bytes of the object about to be LINKED against the same image the differential compares the KIT's
blob against — because the `.S` is assembled twice, with two flag sets, and nothing else held the
two outputs together (`atari/asm_twin_ships.py`).

**FOUR THINGS THIS WAVE FOUND AND DID NOT CLOSE**, so the next reader has them rather than
rediscovering them: `atari/shim_include/tos.h`'s block on `bg_in_timer_c` still says the entry
raises it and still names the C's inability to touch `%sr` as what keeps the ISR at IPL 6 — both
are now false, and the second matters, because restoring the IPL drop without restoring the gate
would let an IKBD interrupt land between a PSG select and its data write; `atari/build.sh`'s
`MUST_STAY_INLINED` gate now pins the shape of code the tick no longer runs; `bubble_main.c`'s
`_Static_assert` message says `bg_timer_c_entry` sets and clears the flag, which it no longer does;
and this project's twin machinery is a second copy of `projects/zynaps/recreate/test/asm_twins.py`,
whose own STATUS registers it as belonging in the kit — a second project needing the same four
checks IS the trigger that note was waiting for, and this wave answered it with a fork.

### Wave 5c, 2026-09-08 — the game logic's own two tiers: fp division and the VDI binding

**485.6K cycles a frame -> 482.2K, 16.52 fps -> 16.63, x1.040 -> x1.033** against the original's
466.9K / 17.18, re-measured in the same session and unchanged. **THE WHOLE-WINDOW MOVE IS BARELY
OUTSIDE THIS INSTRUMENT'S 0.3% SPREAD AND IS NOT THIS WAVE'S EVIDENCE** — wave 5a's own re-window of
the SAME wave-4 binary read 483.8K, so the honest range for the move is 1.6K to 3.4K. The ROWS are
the evidence, and they move by a fifth to a third each; the objdump under them is the evidence for
the rows. Measured in a scratch worktree of `b8ad1b0`, so waves 5a and 5b are NOT in the window and
the three do not add up — whoever merges them re-measures. `src/` only: `atari/` is untouched, and
`make test` (1,908 cases) and `make guarded` are green either side of this, because it is codegen.

| row, cycles a frame | before | after | the original |
|---|---|---|---|
| `fp_dispatch` exclusive — dispatch + `fp_div`, both branch-entered on both sides | 8,881 | **7,643** | 8,273 |
| `fp_pack_double` exclusive (ours is a `jsr`; the original falls into it, so its cycles are inside the three rows beside it) | 2,963 | 2,950 | — |
| `fp_acc_load_long` + `fp_acc_to_long` exclusive | 1,436 | 1,424 | 332 + `fp_long_to_double` 2,106 + `fp_double_to_long` 824 |
| **the fp package, summed over its two dispatches and two widenings a frame** | 13,281 | **12,017** | 11,535 |
| `vq_key_s` / `vq_mouse` exclusive | 449 / 565 | **369 / 468** | 164 / 233 |
| `vsf_color` / `vr_recfl` exclusive | 145 / 156 | **112 / 119** | 54 / 71 |
| `save_` + `draw_` + `restore_sprite_backgrounds` exclusive | 6,813 | **5,793** | 6,458 (their own 2,314 + `vro_cpyfm` 2,024 + the two MFDB setters 2,120) |
| `core_frontend.o` `.text` | 31,076 B | **24,848 B** | — |
| `core_clib.o` `.text` | 18,804 B | 18,804 B | — |
| the size gate's spare | 72,512 B | **78,656 B** | — |

**THE FP TIER IS THE ONE ROW THAT WENT FROM BEHIND TO AHEAD.** `fp_dispatch`'s exclusive is now 630
cycles a frame UNDER the original's for the same work, and the package as a whole is +482 where wave
3b left it at +1,733 — the residue is `fp_pack_double` being a real `jsr` with five stack arguments
where the original's `fp_div` ends in `bra.w $15394` and falls into it. That is priced below and NOT
taken. The three sprite rows crossed the same way: 355 behind, now 665 ahead.

**LEVER 1 — THE DIVISION STEP, 80/98 CYCLES -> 64/78 AGAINST THE ORIGINAL'S 64/76**, over 32 steps
and two `fp_div` calls a frame. Wave 3b's note said the remaining ~10 a step was "not reachable from
C"; it was reachable, by asking for the two HALVES rather than the pair. `divisor <= remainder` on
one `uint64_t` makes GCC compute a whole 64-bit difference and throw it away —
`move.l d2,d6 / move.l d3,d7 / sub.l d5,d7 / subx.l d4,d6 / bhi`, 34 cycles — in front of the
subtract's own `sub.l`/`subx.l`. Spelling the same condition as `divisor_high < remainder_high ||
(equal && divisor_low <= remainder_low)` gives `cmp.l d2,d4 / bhi / beq` with `cmp.l d3,d5 / bcs`
only on the equality, which is the original's own `cmp.l`/`bcs`/`bne`/`cmp.l`/`bhi` @ 0x1522c. The
last 4 of the 20 are the loop counter: an `unsigned short` closes with `subq.w #1` where an
`unsigned` spends `subq.l`. **`dbf` (10 against 14) is NOT reachable** — every countdown spelling
tried (`step != 0`, a signed `step >= 0`, a peeled `do`/`while`) normalises back to
`moveq #32 / subq / bne`, and the two-armed loop has nothing for a single `dbf` to close on anyway.
Three compare spellings compile byte-identically (`remainder >= divisor`, `!(remainder < divisor)`,
the current one on one `uint64_t`), and the difference-form `if (remainder - divisor <= remainder)`
is still WORSE, as wave 3b measured.

**LEVER 2 — THE BASE REGISTER THE ORIGINAL KEEPS IN A4.** Every global in this program is `d16(a4)`
(`include/globals.h`), so `vq_key_s` @ 0x16a5e writes its four `contrl` slots as
`move.w #$80,-6186(a4)` at 12-20 cycles. A reconstruction has no such register: `image + A_vdi_contrl`
costs a 32-bit `move.l #145136,Dn` (12) in FRONT of an indexed `(0,An,Dn.l)` access, 14 dearer per
slot than the instruction it stands for, and a VDI call fills ten of them. `src/frontend.c`'s VDI
binding now materialises the base ONCE per entry point behind a `CURSOR_BARRIER` and reaches every
slot as a displacement off it — the barrier is the mechanism, exactly as in wave 3b's GEM door, where
a plain local bought nothing because GCC re-folds the constant back into the index. The displacements
are the original's own numbers: `A_vdi_pblock` 0x1e8ca to `contrl[10]` 0x23704 is -26192 to
-6166 off `A4_BASE`, inside the 68000's signed word. Hand-counted off the objdump, `vq_key_s` went
**426 -> 346** cycles and the raster copy inlined at a sprite site **548 -> 376**.

**AND `always_inline` ON `sprite_copy` REPAIRS A REGRESSION THIS WAVE CAUSED, which is worth more
than the lever it protects.** GCC inlined that helper at all seven sites until `vro_cpyfm`'s body
shrank around the `asm` barrier, and then out-lined it: a `jsr`, four pushed arguments and a `movem`
pair, 82 cycles, in front of a body that had just saved 104 — 526 against 376, most of the lever
given back for a change nothing in the tree would have reported. The objdump is the only surface that
sees it; `m68k-elf-nm` naming `t sprite_copy` in `core_frontend.o` is what a gate would grep for, and
that gate is NOT written (below).

**THE THIRD ITEM ON THIS WAVE'S LIST WAS ALREADY AT PARITY AND IS RECORDED RATHER THAN WORKED.**
`hud_bonus_bar_shrink`'s +536 a frame is INCLUSIVE, not its own: its exclusive is 607 against the
original's 587, and the +533 of the gap lives in `vsf_color`, `vr_recfl` and the shim's door beneath
them. Lever 2 took 460 of it without touching the routine at all (its inclusive is 3,487 against
2,955, from 3,503).

**WHAT WENT RED, AND IT IS THE USEFUL HALF.** `gem_trap_save_registers` changed its first parameter's
MEANING from the image to the base, and both are `uint8_t *`: `gem_aes` kept passing `image`, which
compiled clean and filed both saved registers 150 KB low. `test_frontend.py`'s `graf_mouse`,
`appl_init`, `graf_handle` and `aes_crysif` cases caught it — 11 failures — and the comment over that
routine now says so, because the compiler cannot. Two deliberate mutations followed, each from a
forced relink (`rm -f build/*.so`, `__pycache__` swept):

| mutation | result |
|---|---|
| `fp_div`'s high-half compare reversed (`remainder_high < divisor_high`) | **RED**, 104 failures |
| `globals_at` loses the base (`return globals + (int32_t)address`) | **RED**, 387 failures |
| `always_inline` on `sprite_copy` | **no mutation exists** — it is codegen, and the differential is green with it and without it |

**WHAT THIS WAVE MEASURED AND DID NOT TAKE**, each with its number, so the next one does not re-derive
them:

* **`fp_pack_double`'s call is ~250 cycles a call, ~1.0K a frame**, and the original pays none of it:
  its `fp_div` ends `bra.w $15394` and falls into the packing tail with the operands already in
  registers, where ours pushes five stack arguments, `jsr`s, and pays a `movem` pair inside. Closing
  it means a `static inline` body shared by the extern `fp_pack_double` and its five callers —
  a structural change to a verified core that also takes the symbol out of `profile.py`'s table.
* **`fp_pack_double`'s `>> 28` is 68 cycles where the original gets the same nibble from a `swap`
  (4).** `shifted = mantissa >> 12` then `(uint16_t)(shifted >> 16)` is what the C already says, and
  GCC re-derives the second from `mantissa` as `moveq #28 / lsr.l` rather than from `shifted`. A
  `REGISTER_BARRIER` on `shifted` fixes it — measured 104 cycles -> 56, **194 a frame** — which is
  under this wave's own 200-a-frame floor, and it spends the barrier on something that is not a
  cursor or a count.
* **The two `sprite_pxy_*` writers are the same lever, unspent: ~92 cycles a site, six sites, ~550 a
  frame** — and the review found that number UNDER-REPORTS itself, because the ten `A_mfdb_src` /
  `A_mfdb_dst` longword stores their four callers make are the same window and the same lever and are
  not in it. They are the SPRITE PROTOCOL and not the VDI binding, which is the only reason this wave
  left them; the helper they need is now two lines away. Wave 3b priced the same rectangle at ~110 a
  call and called it NO-GO before that helper existed.
* **The AES binding is left on `image + <address>` on purpose, and it is not the sprite protocol's
  problem.** `aes_crysif`, `aes_bind_parameter_block`, `appl_init`, `graf_handle` and `graf_mouse`
  spell twenty-odd slots the old way, and all six AES arrays (`A_aes_ap_id` 0x1f0bc to
  `A_aes_control` 0x1f140) are -24,154 to -24,026 off `A4_BASE`, well inside the window. Nothing
  technical excludes them; they are BOOT AND MENU and make 0.00 calls in the profiled frame, so the
  conversion would buy nothing measurable and would widen a wave that is already outside its brief.
  `gem_aes` therefore materialises a base for its two saved-register stores and its neighbours keep
  the absolute form — the one place in this file where the two idioms sit side by side.

**WHAT THE PRE-COMMIT REVIEW MOVED, and four of the five angles found the same thing.** The base and
the image were both `uint8_t *`, and because every displacement here is NEGATIVE a mix-up does not
reach a wrong slot — it writes BELOW the image, where the byte differential has nothing to compare
and only `make guarded`'s reserve under the buffer can see it (on target it is under
`bubble_main.c`'s guard bytes, which sit above). The base is its own one-field type now, which makes
the mistake a compile error, and `m68k-elf-objdump -d` says the type costs NOTHING: `core_frontend.o`
is byte-identical with the bare pointer and with the struct. Four more came with it:

* `globals_base`'s body IS an `asm`, which is exactly what tipped GCC into out-lining `sprite_copy`,
  and it has thirteen call sites. It carries `always_inline` for the same reason, and the same
  objdump says the marker changes nothing today — it is a hedge against the compiler bump that would
  invert this whole lever with every check in the tree still green.
* The barrier is `REGISTER_BARRIER(base, REGISTER_BARRIER_ADDRESS_CLASS)` and not `CURSOR_BARRIER`:
  `machine.h` reserves the latter for a pointer walked by postincrement, and this one never moves.
  This section's own declined-lever list objects to spending a barrier "on something that is not a
  cursor or a count", and the first draft then did exactly that.
* **`vro_cpyfm` calls `vdi_set_src_mfdb`/`vdi_set_dst_mfdb` again**, through a base-taking `_at`
  pair. The first draft took the shared body directly, which left two VERIFIED routines with no
  on-target caller at all — only the differential's direct entries — and quietly falsified wave 4's
  equivalent-mutant argument, which names those two calls as what re-stages `contrl[7..10]`.
* **`v_gtext`'s per-character `intin` store is the one slot in this file that must NOT move to the
  base**, and nothing said so. Its index is the only RUN-TIME one here and `sign_ext16` can make it
  negative: the original's `adda.w` wraps that back inside the image, where a displacement off the
  base would carry it ~40 KB below. No case seeds it — `test_v_gtext_fuzz` draws lengths from
  `range(0, 24)` and the wrap needs ~16k characters — so the comment is the whole of the guard.

**One review candidate was REFUTED by the objdump rather than taken**: holding the barriered base
across `v_gtext`'s character loop was flagged as register pressure on the one non-straight-line body
in the file, and the loop's six instructions are byte-identical before and after (`clr.w`/`move.b
(a1)+`/`lea`/`addal`/`move.w`/`addq`/`tst`/`bne`, same registers). It costs one `movem` slot in the
prologue and buys seven slots.

**STILL UNPINNED, and it is this wave's own finding — the same one wave 3b recorded and nobody has
taken.** Nothing in this tree reddens if a later editor re-spells `fp_div`'s compare on the pair,
deletes the `CURSOR_BARRIER` in `globals_base`, or drops `always_inline` from `sprite_copy`: all
three are green under `make test` and `make guarded` in either spelling, and all three give back a
third to a half of this wave. `atari/build.sh` already carries codegen scans (the
postincrement/indexed-EA scan, the endianness probe, wave 3a's inlining gate over `core_sound.o`),
and the shape of the fix is three more: refuse a `move.l #145136` inside `core_frontend.o`, refuse a
64-bit `sub`/`subx` pair inside `fp_div`, and refuse `t sprite_copy` in `core_frontend.o`'s symbol
table. It was NOT added, because `build.sh` was being rewritten by wave 5a in the same working tree.

**WHAT THE PRE-COMMIT REVIEW CAUGHT, and it is the same two-instrument point wave 4 makes.** Five
finder angles over the isolated diff found **no functional defect in the assembly** — the register
lifetimes, the `%sp` offsets, the branch ranges, the macro-label namespace and the semantic
equivalence with the deleted C all held — and twelve robustness and documentation defects that no
gate in this tree could see:

| what | why it mattered |
|---|---|
| **the `u` suffix made OPTIONAL turned the two-language loop from fail-closed to fail-OPEN** | with `u` mandatory, `#define VDI_PB_PTSOUT 4 + 1` matched nothing and the empty-scrape guard reddened; optional, it scraped the leading `4`, agreed with the assembly's 4, and printed the green line over a value that is really 5. **Both sides are now anchored** (value, optional `u`, then end of line or a comment) and both were re-measured on the expression form |
| **the `movem` was justified by the WRONG reason, in the row that prices it** | STATUS said "the seven values that must survive the trap" while the routine's header said the same seven are "in the set TOS preserves" — an invitation to delete a 132-cycle save. It is there because m68k SysV makes them CALLEE-saved and the C caller owns them; that TOS also preserves them is why seven is *all* that is needed. Both the row and a comment on the instruction now say so |
| **"NOTHING RE-ENTERS IT" was deleted with the C and re-established nowhere** | the door still depends on it twice — one shared staging block, and a window where the game's own MFDB holds a machine address — and wave 5b is editing the interrupt entry in the same file. Restored as its own paragraph |
| **the two block lengths lost their `_Static_assert`** | `build.sh` pins the two kit indices they are derived from, but nothing pinned that each is its block's HIGHEST index. Two assembler `.error`s restore it |
| **`bg_gem_trap` kept `.globl` with an incompatible ABI** | no C caller survives, but the build has no `-Werror`, so one re-added later would compile with a warning and trap with a garbage selector. The `.globl` is gone; `m68k-elf-nm` still lists a local label as `t`, which is what `profile.py`'s map reads |
| **the door's three C argument offsets were the one cross-language fact with no pin** | eleven constants got a gate and `ARG_MEM`/`ARG_SELECTOR`/`ARG_PBLOCK` — which ARE `os.h`'s prototype restated — got none. `build.sh` now pins the prototype's text |
| **the counters' width pin only worked in one direction** | `_Static_assert(sizeof … == 4)` catches C narrowing the type, not the assembly narrowing `addq.l` to `addq.w`. `build.sh` now counts the three instructions, as it counts the ISR's two PSG stores |
| **the macros emitted a bare `9:` into the file's own hand-written label namespace** | correct today; a later routine's `9f` would have bound to a label inside a staging run. Both macros use GAS's `\@` counter now |
| **the stage-and-trap tail was three copies of one fact** | the selector and the block length must agree, and the deleted C `stage_and_trap` existed to hold them together. `TRAP_STAGED count, selector` restores it at zero cycles — and buys 8 cycles a call, because the entry can then build the block cursor in `%a0` |
| **the `.balign` claim is overridden by `tos.ld`** | `SUBALIGN(2)` caps per-symbol `.bss` alignment at a word; even is all a `move.l` needs, and the comment now says that rather than claiming four |
| **three prose defects that would mislead the next reader** | a gate named from another project (`REPLACED_OS_HELPERS`); a sum that did not equal its own operands; and an enumeration of the eleven constants that counted nine |
| **`smoke.py`'s second-arrival rationale still named `raster_copy_call`** | that comment is the only explanation of why the second capture exists — the surface that reds two of this wave's four mutations |

**LEFT, and why.** `atari/profile.py` carries two more stale references to `bubble_backend.c`'s door
(lines 49 and 1110); that file is being edited by another wave in the same tree and a concurrent
read-modify-write is how a lost update happens, so it is named here rather than fixed. The review
also proposed folding this file's THREE remaining one-off scrape-and-compare sites (`GATE_*`,
`LOAD_BASE`, `STACK_RESERVE`) into the same loop, and rewriting `bubble_os.s` as a `.S` so the kit's
header could be `#include`d instead of scraped: the first is pre-existing code this wave did not
touch, and the second needs `__ASSEMBLER__` guards in `tools/recreate_kit/include/os.h` and
`../include/frontend.h`, which are the kit's and the cores' and out of an `atari/`-only wave's scope.
Both are real and both are somebody's next change.

## Model gaps — read this before picking a function

The kit's TOS trap model (`tools/recreate_kit/TRAP_MODEL.md`) was built for the games before this
one, and Bubble Ghost reaches OS calls none of them did. **An unmodeled call is not a wrong answer,
it is a refused run** — `emu.run` raises and names it — so nothing here can silently produce a false
green. What it does mean is that the routines below cannot be ported until the gap is closed, and
the gap is a KIT change in every case. Counted from the 92 trampoline call sites (`gemdos_trap` @
0x15e58, `xbios_trap` @ 0x15e3c), by the selector immediate pushed at each.

**One gap has been closed since the bootstrap** and is recorded here rather than dropped, because
the reasoning is still the map's: the kit's Malloc arena used to be a kit-wide `#define` at 0x20000,
inside this program's BSS, and the only knob was `tos_malloc_unused` — a claim ("this game never
allocates") that is false here. The kit now places the arena per project (`heap_base` /
`heap_limit`; the mechanism is in
[`tools/recreate_kit/README.md`](../../../tools/recreate_kit/README.md), "The Malloc arena is the
one region a project places", and this game's numbers are in [`README.md`](README.md)), this
project uses `[0x30000, 0x90000)`, and the waiver is gone.

| gap | where it bites | what closing it needs |
|---|---|---|
| ~~**GEMDOS `Cconis` (0x0b), 6 sites**~~ **CLOSED** | every keyboard poll — the menu's "Press [G]…[P]…[D]…[H]", the pause | TRAP_MODEL.md Phase 13 models it over the poked console state, beside `Bconstat`. Every one of the menu's four flush loops is run by a case now |
| **GEMDOS `Crawcin` (0x07), 7 sites / `Cnecin` (0x08), 4 sites** — modeled, but the FLUSH IN FRONT OF EACH ONE cannot be crossed | every key this program reads | Phase 13 models both over the same one QUEUE every console read takes from, and a blocking read with nothing staged REFUSES rather than fabricating a key. **What that costs here was discovered by the port and is not what the row used to claim.** The idiom at all four sites is `while (Cconis()) Crawcin(); c = Cnecin();` — a FLUSH and then a blocking read — so the flush empties the very queue the read then needs, and no staging of `harness.console_keys` can put a key on the far side of it: on a real machine the key arrives AFTER the flush, which is a MOMENT and not an order. Every region of `title_menu_loop` therefore ends at a `Cnecin` push and the next begins there with its own key staged (`test_frontend.py`'s `test_the_menu_regions_meet_at_every_blocking_read` pins that join). Closing it means a second staged stream the flush does not drain, of `os_console_take_key`'s shape — the same shape `Cauxin`'s row below asks for |
| ~~**GEMDOS `Fseek` (0x42), 5 sites**~~ **CLOSED** | reached only through `c_lseek` @ 0x159dc, which neither hall-of-fame routine calls: both read and write GHOST.SCR sequentially | Phase 13 models it over the staged-file cursor, with a refusal rather than an error code for a seek the model cannot serve |
| ~~**GEMDOS `Fdelete` (0x41) / `Pterm` (0x4c) / `Cauxout` (0x04) / `Cprnout` (0x05)**~~ **CLOSED** | the C library's own wrappers (0x16868, 0x14d16, 0x16bae, 0x16bdc) | TRAP_MODEL.md Phase 13 models all four: `Fdelete` edits the staged-file table and answers TOS's EFILNF for a missing name, `Pterm` ends the run with an `OS_EVENT_PTERM` and LATCHES the ledger, and the two character writers take a ledger kind each. All five wrappers are ported and verified in `## Verified — clib` |
| **GEMDOS `Cauxin` (0x03), 1 site** | `c_conin` @ 0x16518's AUX: handle | nothing, and deliberately: the console has a staged keystroke queue and the serial line has nothing at all, so every answer would be invented and the real call would BLOCK for one that never comes. The model refuses it by name. Closing it means a second staged input stream, of `os_console_take_key`'s shape |
| ~~**BIOS `Bconout` (trap #13), 2 sites**~~ **CLOSED** | `game_top_loop` @ 0x101e6 only: the IKBD commands `$12` (disable the mouse) and `$08` (relative reporting back on) | Phase 13 models device 4 as an OS EVENT LEDGER entry per byte and refuses every other device. Both sites are run by a case now — `game_top_boot` and `game_top_boot_tail` — and residual 16 below says what a ledger entry does and does not pin |
| ~~**`trap #2` (GEM), 2 trampolines**~~ **CLOSED** | the AES one @ 0x149b6 (`d0 = $c8`) and the VDI one @ 0x168d4 (`d0 = $73`) | Closed by TRAP_MODEL.md phases 11-13: the kit now models an ST raster, `vro_cpyfm`'s sixteen logic operations, and every VDI/AES opcode this game uses (VDI 3, 8, 12, 22, 25, 100, 109, 114, 124, 128; AES 10, 77, 78). Both trampolines and all sixteen entry points are verified in `## Verified — frontend` |
| **`trap #9`, 1 site** | every PSG access from ordinary code: `psg_access` @ 0x14940 calls the game's OWN supervisor gate `trap9_psg_handler` @ 0x14950 | not a TOS trap at all, so the shim does not intercept it: the oracle dispatches through the vector at `$a4`, which is **zero unless the run has already executed `install_sound_vectors` @ 0x148ea**. A reconstruction cannot trap; it calls `psg_port_write()`/`psg_port_read()` from the kit's `psg.h` (TRAP_MODEL.md, Phase 6), and the ledger comparison is what holds the two equal |
| **the Timer C ISR @ 0x1459a** | the music/sound player, installed at `$114` by `install_sound_vectors` | the model fires no interrupts, so the handler is entered explicitly by a stub that builds a 68000 exception frame — copy `interrupt_frame_pokes` from `projects/zynaps/recreate/test/abi.py`. It exits by pushing TOS's saved `$114` and `rts`ing, not by `rte`, so the stub's frame is not popped the usual way: read the tail before writing the case |
| **the model's `Logbase` is 0x8000, and this game's back buffer is `Logbase - 0x7d00`** | `init_video_and_heap` @ 0x10118, and any draw routine driven from the pointers it stores | that puts the back buffer at **0x300**, so a 0x7d00-byte frame write covers `OS_KBDVBASE` (0x500) and the whole harness-poked input block (0x600..0x61f). Both sides do it identically, so the diff stays clean — but a case that ALSO stages a console key silently loses it. Stage the two screen pointers as test inputs rather than taking them from `init_video_and_heap`'s output |
| **`GHOST.LOA` is a second program, `jsr`ed inside the BSS** | `play_voice` @ 0x13cea (`jsr a4-5982`) | it is an `ABSFLAG` `.PRG` read into `a4-6010` as data, with its sample pointer poked at +0x1e (`../notes/loader.md`). **THE GAME'S TWO ROUTINES ARE PORTED** — the slice stops short of the wait, exactly as this row said it could — and the LOA's own code is what is left: it programs MFP Timer A, and the byte its wait spins on is written by its own handler rather than by an external agent, so Phase 8's scheduled writes have no site to name |

**What is modeled and needs no work**, so that this list is not read as "the OS is unusable": every
XBIOS call the game makes — `Setscreen` (17 sites), `Setcolor` (5), `Random` (4), `Setpalette` (3),
`Vsync` (3), `Logbase` (2), `Getrez` (2) and `Supexec` (2, which really runs the routine nested) —
plus GEMDOS `Cconout`, `Crawio`, `Super`, `Fcreate`, `Fopen`, `Fclose`, `Fread`, `Fwrite`, `Malloc`
and `Mfree`. The video and colour calls are modeled as **no-ops**, which is the standard limit: they
write hardware, not the image, so the differential cannot see a wrong palette or a wrong screen base
at all (`docs/on-target-execution.md`).

## Verified — init (5)

The boot chain: `crt0_start` @ 0x10036, `init_globals` @ 0x16d8e and `main` @ 0x100dc. Every one of
them but `init_globals` is a slice rather than a function — nothing here returns — so each row's
Verification column opens with the `[start, end)` the differential actually runs.

**`game_top_loop` @ 0x101e6 IS NOT HERE EITHER**, though `main` is what calls it and it is the last
routine of the boot chain. It is the front end's own state machine — the menu, the room loop, the
two end-of-room animations and the hall-of-fame submitter — so its eleven slices are verified in
`## Verified — frontend` beside `title_menu_loop`, which they alternate with. Same reason as
`init_gem_and_screens` above: the section a routine sits in is the subsystem it is made of.

**`crt0_setup_args` @ 0x10116 is not here either, and it IS reconstructed.** The crt0 calls it
(`pea 128(a0) / jsr $10116`) and it is a bare `rts` — the Alcyon runtime's argv hook, stubbed out at
link time. It belongs to the C library rather than to this game's boot chain, so its row is in
`## Verified — clib`.

**`init_gem_and_screens` @ 0x10118 is NOT here**, though the boot chain calls it: it opens the AES
connection and the VDI workstation and takes both screen bases off XBIOS, which is the front end's
binding end to end, so it is verified in `## Verified — frontend` with the routines it is made of.
**`init_globals` @ 0x16d8e IS A ROW HERE, and what makes it one is where its C comes from.**
`test_image_model.py` already ran it under the ORACLE and proved the image it leaves equal to the
real crt0's — but that says nothing about a reconstruction, and `test/conftest.py`'s post-init
fixture IS this routine's output, so a C version read off that fixture would be green about nothing.
`include/init_globals_stream.h` is the routine's 7,869-instruction stream decoded from the
disassembly by a generator (which refuses any instruction outside its ten shapes and checks its own
output against an oracle run before writing it), and `src/init.c`'s `init_globals` is the ten-case
interpreter over it. The case that runs it is the one differential in the project that must NOT
start from the post-init fixture: it winds the base image back to the loaded .PRG, where the BSS is
still zero and all 7,056 bytes it changes are attributable.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x10036` | `crt0_relocate_and_clear` **(slice** `[0x10036, 0x100a6)` **)** | 112 of 166 | ✅ verified | `stop_pc` at the `jsr 48(a5)` into `init_globals`, on a FILE-LAYOUT image with a fabricated basepage — the program as TOS hands it over, before the segment move this slice IS. Six segment layouts including the two the original's `ble` before the `dbf` treats specially (a one-byte data segment moves NOTHING, a two-byte one moves both), everything it writes seeded with noise, and the A4 it establishes compared against the oracle's register file. **One excluded band**, the twelve bytes the Mshrink call pushes on the stack the crt0 has just MOVED — outside the differential's own guard — and the run's deepest A7 is asserted to be inside it |
| `0x16d8e` | `init_globals` | 31,548 | ✅ verified | run to `rts` on `harness.BASE_IMAGE` (the .PRG as loaded, bss still zero — not the post-init fixture, which is this routine's own output), over four values of A5 including 0. Its C is generated from the instruction stream, not from the image it produces |
| `0x100dc` | `main_check_resolution` **(slice** `[0x100dc, 0x1010a)` **)** | 46 of 58 | ✅ verified | `stop_pc` where the low-resolution branch lands; the trampoline's three save slots under noise, and the ANSWER (a flag this reconstruction invented, because the branch is not otherwise visible) compared against the arm the oracle took. **Residual:** `Getrez` is the model's constant — see below |
| `0x100f4` | `main_wrong_resolution` **(slice** `[0x100f4, 0x100fe)` **)** | 10 | ✅ verified | entered at its own PC, because the gate above can never choose it under the model. `stop_pc` at the two-instruction spin that follows the `c_printf`; the console-byte ledger carries the whole message, and a second case reads it back out of the ledger to say the case is not vacuous |
| `0x1010a` | `main_start_game` **(slice** `[0x1010a, 0x1010e)` **)** | 4 | ✅ verified | `stop_pc` at the `jsr game_top_loop` that never returns. It composes the verified `init_gem_and_screens`, so what this pins is the composition; a second case asserts the two screen bases and the parameter block really appear |

**21 cases.**

**Mutations tried against this battery**, each from a deleted `.so` with `__pycache__` swept, and
each **red**:

| mutation | what caught it |
|---|---|
| the DATA move one byte short | 4 cases |
| the DATA move's counter read in 32 bits instead of through the `dbf`'s WORD (2026-09-06) | 1 case — `CRT0_SEGMENTS`' `dlen = 0x10001` row, **which did not exist until a review pass found the defect**: the `ble` above the loop is a LONG test and the `dbf` under it a WORD one, so 0x10001 passes the test and then moves exactly ONE byte. The program's own 0x2f4 can never separate the two readings |
| the BSS clear FIVE bytes short | 6 cases |
| the BSS clear starting one byte high | 6 cases |
| `a4` taken from the BSS base rather than the DATA base | 6 cases, and `test_crt0_establishes_the_projects_a4` by name |
| the seven A5-relative pointers built WITHOUT A5 | 4 cases — `test_init_globals_reads_a5`, whose other three values exist for this |
| the stream's `COPY` reading its own destination | 5 cases |
| the stream's word store advancing by a longword | 5 cases |
| `include/init.h`'s `BASEPAGE_DBASE` and `test_image_model.py`'s `BP_DBASE` set to different values | `test_the_basepage_offsets_have_one_meaning_across_both_files`, added BECAUSE nothing else could see it: `test_constants.py` keys its duplicate check on the NAME and its value check on the `A_*` family, so two names for one GEMDOS field are invisible to both |

**TWO MUTATIONS ARE EQUIVALENT, and both are worth recording so nobody re-tries them.**

* **The BSS clear up to FOUR bytes short.** The very next instruction stores the basepage pointer at
  `-4(a4)`, and `a4` is the END of the clear — so the last four bytes of it are overwritten whatever
  the clear did, for every segment layout, not just this program's. Measured as a survivor first
  (`- 1`), understood second, and then pinned from the other side: `- 5` is red.
* **The stream's `ADVANCE` added in 32 bits instead of through `adda.w`'s sign extension.** The nine
  `adda.w` in the whole routine carry 2 and 1400, both positive small words, so no input the
  routine has can tell the two apart. This is the "the data cannot reach it" case CLAUDE.md names:
  the branch is honestly unexercised rather than untested.

### Residuals — what these rows do NOT pin

1. **`Getrez` is the MODEL's answer, not the program's.** The kit services XBIOS `Getrez` and leaves
   D0 = 0 with no `os_*` entry point of its own (`oracle/shim.c`'s `case 0x04`), so there is nothing
   for a reconstruction to call and nothing a case could stage — `main_check_resolution` states the
   model's answer. On a machine really in medium or high resolution the two sides would take
   different arms and the differential could not see it; the surface is an on-target run, and this
   project has no `.PRG` yet.
2. **The crt0's `Mshrink` is a no-op with no ledger entry**, so the reconstruction reproduces its
   arithmetic and not the call. The stack it makes room for is the harness's own.
3. **The crt0's TAIL is not a slice.** `[0x100a6, 0x100dc)` — up to its own `rts` at 0x100da — is
   four calls, `init_globals`, `crt0_setup_args`, `main` and `c_exit`, and the last two never
   return, so the region is read-verified. The Cconout after `c_exit` is code the real machine
   cannot reach at all.
4. **`main`'s composition is read-verified**, for the same reason as the frame loop's: no case
   enters `main` at 0x100dc and leaves, because the arm it takes calls `game_top_loop`.

## Verified — frontend (59)

**THE PROGRAM'S OWN STATE MACHINE IS HERE TOO, and it is the last thing this project had left.**
`game_top_loop` @ 0x101e6 and `title_menu_loop` @ 0x115d6 are twenty-six of the rows below — twelve
and fourteen, one per straight-line region — and `../notes/frontend.md` §2 draws the machine they
make between them.
Neither is written as a C function of its own: `game_top_loop` is a `do { … } while (true)` and
every pass of `title_menu_loop` ends at a blocking console read the model cannot cross (the gap
table above says why), so both compositions are READ-VERIFIED and `src/frontend.c` writes the order
its slices run in out as prose instead. Where each slice stops is not a matter of taste: it is a
`jsr` into a second program, a `Cnecin` push, or one of the three branch tests that decide whether
the routine goes round again — and `test_the_menu_regions_meet_at_every_blocking_read` refuses a
menu region that ends anywhere but at a `Cnecin`.

**The GEM binding, and everything the rest of this project was cut around.** Bubble Ghost is a GEM
application: it opens a virtual workstation and draws its text, its bonus bar and its 32x32 sprites
through the VDI (`../notes/frontend.md` §1). The twelve VDI entry points and four AES ones below,
plus the two trampolines under them, ARE that binding, and porting them is what closes the three `src/blit.c` slices, the
`vro_cpyfm` residuals and (for whoever ports them) the HUD painters. `include/frontend.h` has the
two parameter blocks and every record; `src/frontend.c` is one file of wrappers plus the boot-time
setup, the sprite protocol and the file loaders.

**What replaces `trap #2`.** The oracle really executes the trap and `shim.c` services it out of the
kit's GEM model; the reconstruction calls that same model — `os_vdi` / `os_aes` — over the same
parameter block at the same address in the same image (TRAP_MODEL.md, phases 11-13). One
implementation, one block: what the VDI draws is image state on both sides, so the byte diff covers
the pixels — and the one call here with no image effect at all, `graf_mouse`, is compared as the
ordered OS event ledger instead.

**Every routine here takes the caller's A1/A2** — both trampolines park them and nothing in the
routine computes them (`docs/agent-playbook.md` §5, "a parameter") — and `init_gem_and_screens`,
`load_hiscores` and `draw_hall_of_fame` also take their own A6, because each hands a callee the
address of a stack local and a C reconstruction has no machine stack. Those locals lie in the band
the differential drops, so the frame is an input both sides are handed.

**The three sprite routines MOVED HERE from `src/blit.c`'s residual list**, and the reason is
ownership rather than reach: `save_sprite_backgrounds`, `draw_sprites` and `restore_sprite_backgrounds`
are three `vro_cpyfm` pairs each, so they belong with the sprite protocol and the binding that
carries it, not with the raw `move.l` blitters. `build_sprite_bank`'s grab loop and
`draw_room_to_stage`'s per-cell `vq_mouse` are the same story: each is the residual `src/blit.c` cut
its slice around, and each is closed here by COMPOSING that file's verified core rather than
restating it. The A2 the tile draw leaves used to be the one exception — this file re-derived it —
and is not any more: `draw_room_tile_to_stage` REPORTS it, and the per-cell slice compares the
answer against the oracle's own A2.

**THE INPUT BLOCK IS THIS SUBSYSTEM'S NOW, and "Borrowed globals" is five rows shorter.**
`A_key_raw`, `A_key_shift_state`, `A_mouse_y`, `A_mouse_x` and `A_mouse_buttons` are the five words
`vq_mouse` @ 0x16a26, `vq_key_s` @ 0x16a5e and the `Crawio(0xff)` poll fill; they were on loan in
`include/gameplay.h` while this binding was unported, and they are defined in `include/frontend.h`
now. `src/gameplay.c` includes that header to read them — the migration the loan table predicted,
made. `A_sound_enabled` was NOT part of it and its row is gone for the opposite reason: the routine
that writes it is `game_frame_update`'s `^S` arm, which is the gameplay subsystem's, so gameplay owns
it and never borrowed it.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x10118` | `init_gem_and_screens` | 206 | ✅ verified | run to `rts` from a machine holding none of its state: `appl_init`, `graf_handle`, `v_opnvwk`, both `Getrez`/`Logbase` calls and the `Super` pair round the conterm write. Plus a second case reading the result off the oracle — the two screens a screen apart, the resolution the model answers, the cleared conterm byte and a non-zero `Super` cookie |
| `0x10dea` | `load_demo` | 90 | ✅ verified | run to `rts` over the real `../bin/GHOST.DEM`, plus a case that reads the two pointers back and pins the cursor parked on the base with the file's first record under it |
| `0x10e44` | `load_presentation` | 116 | ✅ verified | run to `rts` over the real `../bin/GHOST.PRE`, whose 0x7820 bytes are exactly the picture and the palette behind it |
| `0x10eb8` | `show_presentation` | 70 | ✅ verified | run to `rts` over the real GHOST.PRE tiles, with poison. Composes `draw_tile_bank_screen` and `clear_physical_screen` (`src/blit.c`) and files the `Setpalette` trampoline's three save slots |
| `0x11d6e` | `hiscore_submit_players` | 78 | ✅ verified | run to `rts` in both player counts and on both sides of the insert: five cases, the last two of which insert once and twice, so the whole chain down to the file write runs |
| `0x11dbc` | `draw_hall_of_fame` | 456 | ✅ verified | run to `rts` over three tables incl. an all-zero one: room 0 as the backdrop, five fixed labels, and the five rows drawn from slot 4 DOWN so the best entry lands on the "SCORE 1:" row. Every glyph is on the declared screen, so the diff compares the picture. Composes `draw_room_to_stage`, `stage_to_work` and `itoa_padded` |
| `0x11f84` | `hiscore_insert_and_save` | 246 | ✅ verified | run to `rts`, BOTH arms: nine offers over four tables, incl. the `>` boundary (a candidate EQUAL to the worst entry does not insert), an insert that walks slot 0 all the way to slot 4, the pending room staged with its high bit set, and a table staged UNSORTED. Plus a case that reads the sorted table back |
| `0x1207a` | `save_hiscores` **(+ a prologue slice** `[0x1207a, 0x120ce)` **)** | 292 | ✅ verified | run to `rts` over three tables, with a case that reads the forty ASCII bytes back out of the staged file against `../notes/frontend.md` §4. The PROLOGUE is a slice of its own over three entry counters, because the routine's FIRST mouse form is only observable there: `graf_mouse`'s whole image effect is `int_in[0]` and `addr_in`, and the closing call overwrites both before the `rts`. Composes `c_creat`, `c_write`, `c_close` and `itoa_padded` |
| `0x121a0` | `load_hiscores` | 386 | ✅ verified | run to `rts` over three shipped-shape files, a file with a non-digit mid-field (the parser has no length check — the byte test is what bounds it), 8 x 6 chunk-seeded random files, and a case reading the table back against `../notes/frontend.md` §4. Composes `c_open`/`c_read`/`c_close`/`c_lmul` |
| `0x13330` | `build_sprite_bank_grab_cells` **(the residual of `src/blit.c`'s slice,** `[0x13330, 0x1342e)` **)** | 254 | ✅ verified | the WHOLE of `build_sprite_bank` @ 0x132ec run to `rts` over the real `../bin/GHOST.DAT` — `src/blit.c`'s verified `build_sprite_bank_prepare` composed with this loop — so the case pins the composition as well as the sixty `c_malloc` + `vro_cpyfm` grabs and the 47/13 split between the two pointer tables |
| `0x1342e` | `save_sprite_backgrounds` | 200 | ✅ verified | four placements incl. one the VDI has to clip, 8 x 8 chunk-seeded fuzz, and poison. **Moved here from `src/blit.c`'s residual list** |
| `0x134f6` | `draw_sprites` | 220 | ✅ verified | as above; the OR mode is the transparency, and the fuzz draws every ghost tile and bubble frame |
| `0x135d2` | `restore_sprite_backgrounds` | 200 | ✅ verified | as above, plus a case that runs all three in order and asserts the work buffer comes back byte for byte — which is the protocol's whole point |
| `0x13a08` | `draw_room_to_stage` | 278 | ✅ verified | run to `rts` over four shipped rooms and the real GHOST.DAT, PLUS a per-cell slice `[0x13a20, 0x13afa)` run at all fifty cells with a mouse reading of its own at each. The per-cell slice is what makes the forty-nine interior polls observable at all — a poll over a fixed mouse state is idempotent, so a run to `rts` cannot tell fifty from one (measured: guarding the poll to the last cell passed the whole battery) — and it also compares the A2 the tile draw leaves against the oracle's, which is what closes the old residual. `src/blit.c`'s slice row for this address is retired as subsumed |
| `0x1396c` | `load_level_pictures` | 156 | ✅ verified | run to `rts` over the real `../bin/GHOST.DAT`: six 30,720-byte banks and the palette, six separate allocations in file order |
| `0x149b6` | `gem_aes` | 28 | ✅ verified | entered directly with the parameter block on the stack and `appl_exit`'s opcode staged — the one modeled AES call the game never makes, so the case reaches the trap without also being a test of a wrapper |
| `0x14b2e` | `aes_crysif` | 102 | ✅ verified | the four opcodes the model serves, D0 compared as the low word; the table's own bytes pinned against the loaded image; and two staged ROWS with a byte at or above 0x80, which is what shows the counts are widened SIGNED (see below) |
| `0x14b94` | `appl_init` | 84 | ✅ verified | from a ZEROED parameter block, so all seven longwords have to be written; `int_out` seeded with noise |
| `0x14be8` | `graf_handle` | 54 | ✅ verified | four SEPARATE out-pointers, which is not what its one caller does — it passes the same scratch word four times, so the four are told apart here and nowhere else |
| `0x14c1e` | `graf_mouse` | 30 | ✅ verified | M_OFF and M_ON. Its whole effect is OFF-IMAGE, so the ordered OS event ledger is the only thing that can tell a reconstruction which makes the call from one which does not |
| `0x16890` | `vdi_set_src_mfdb` | 34 | ✅ verified | five pointers incl. 0x80000000 and 0xfffefffe — the original splits with `asr.l`, so only a pointer with the top bit set shows that the sign fill is dropped by the `move.w` |
| `0x168b2` | `vdi_set_dst_mfdb` | 34 | ✅ verified | as above, over `contrl[9..10]` |
| `0x168d4` | `vdi_call` | 40 | ✅ verified | entered directly with an opcode staged: it parks A1/A2, re-points `contrl` and dispatches |
| `0x168fc` | `vst_height` | 76 | ✅ verified | five heights incl. 0, -1 and 0x7fff; four separate out-pointers over seeded noise |
| `0x16948` | `vst_color` | 44 | ✅ verified | nine pens incl. both ends of the model's 0..15 clamp and a negative one; D0 compared as the low word |
| `0x16974` | `vsf_color` | 44 | ✅ verified | as above |
| `0x169a0` | `v_opnvwk` | 102 | ✅ verified | from the loaded image's ZEROED parameter block, so all four lent pointers have to appear and be put back; two different `work_in` arrays (the attributes come out of that array, so a swapped slot installs a different pen); `work_out` seeded with noise so the 42 entries the model zeroes are visible; the handle passed IN is the BSS zero its real caller passes. Plus a case reading the workstation the model declares |
| `0x16a06` | `v_clrwk` | 32 | ✅ verified | over a screen full of noise, with poison |
| `0x16a26` | `vq_mouse` | 56 | ✅ verified | four poked states incl. both extremes, three separate out-pointers |
| `0x16a5e` | `vq_key_s` | 40 | ✅ verified | six shift masks |
| `0x16a86` | `v_gtext` | 92 | ✅ verified | seven strings x four positions — the empty string, a high-bit one, and the game's own longest menu line — at the origin, the far corner and a negative x the model clips; 8 x 8 chunk-seeded random strings; poison |
| `0x16ae2` | `vr_recfl` | 48 | ✅ verified | three rectangles (the bonus bar's own row among them) x three (interior, pen) pairs, the hollow one included: the model reads the fill INTERIOR before the fill colour, and a solid-only case could not tell the two reads apart |
| `0x16b12` | `vro_cpyfm` | 76 | ✅ verified | four rectangles x two modes x three raster directions, plus 8 x 12 chunk-seeded fuzz over ALL SIXTEEN logic operations and random extents; poison |
| `0x101e6` | `game_top_boot` **(slice** `[0x101e6, 0x10232)` **)** | 76 | ✅ verified | `stop_pc` at the `jsr play_voice` — a SECOND program the model cannot run. The mouse hidden, the voice player and the title picture read off disk, the workstation cleared, `Bconout(4, $12)` on the OS event ledger, the logical screen moved to the work buffer and the picture shown. Composes `graf_mouse`, `load_voice_player`, `load_presentation`, `v_clrwk` and `show_presentation` |
| `0x10236` | `game_top_boot_tail` **(slice** `[0x10236, 0x1024e)` **)** | 24 | ✅ verified | `stop_pc` at the push that opens `c_free`. `load_level_pictures` over the real GHOST.DAT, `load_hiscores` over a shipped-shape GHOST.SCR, and `Bconout(4, $08)`. **Residual:** the `c_free` after it — see below |
| `0x10258` | `game_top_boot_arm` **(slice** `[0x10258, 0x1027e)` **)** | 38 | ✅ verified | the sixty sprite cells grabbed off the real GHOST.DAT, the sound driver installed and silenced, GHOST.DEM read, and the four globals a fresh boot starts from — two tables, one of which is the displayed high score taken from the hall of fame's BEST entry (its LAST, the table being ascending) |
| `0x1027e` | `game_new_game` **(slice** `[0x1027e, 0x102b0)` **)** | 50 | ✅ verified | `stop_pc` at the `jsr title_menu_loop`. Both players back in, `reset_world_state` composed, five lives, a full bar, and the score offered to the hall of fame — practice x score, four cases, because a practice game scores nothing and offers zero |
| `0x102b4` | `game_turn_init` **(slice** `[0x102b4, 0x1037a)` **)** | 198 | ✅ verified | six cases: an ordinary game (which starts at grid (5, 4), i.e. room 1) and two practice squares, each in one- and two-player mode. Twenty per-player slots seeded from the live state, and the turn handed to player TWO so that the swap at the top of the first room brings player one up |
| `0x1037a` | `game_player_change` **(slice** `[0x1037a, 0x105e0)` **)** | 614 | ✅ verified | twelve cases over six (turn, lives, still-playing) states x both player counts, plus one with no handover pending. The "G A M E   O V E R" card for a player who has run out — both players' own copies of the string, which are two DATA addresses holding the same bytes — the handover, the incoming player's twenty slots and 58-word world put back through the verified `restore_world`, and the "P L A Y E R  x" card. A one-player game writes nothing at all, which is what the `player_count = 1` rows say |
| `0x105e0` | `game_room_setup` **(slice** `[0x105e0, 0x1078a)` **)** | 426 | ✅ verified | five worlds: a fresh room entered from the left, one entered from BELOW (the only way this game awards a spare life), a room already seen, a practice room (whose entry direction comes from the room NUMBER, since there is no previous room), and the two-player re-entry. The room the grid square names, the bubble at the entry point it arrives through, the room composed and slid in through `room_wipe_in`, the HUD drawn and the bar refilled |
| `0x10792` | `game_room_frame_tail` **(slice** `[0x10792, 0x108d2)` **)** | 320 | ✅ verified | eight states: an ordinary frame, each of the four exits, the bar's three-frame tick and its floor, room 35's win at both sides of `TOP_WIN_X`, and a turn already out of lives. The ambient countdown underflowing and re-rolling through the fp package, and the five calls that put the frame on screen. **Entered where `game_frame_update` returns** — that call is the gameplay subsystem's nine slices, composed |
| `0x108ec` | `game_ending_sequence` **(slice** `[0x108ec, 0x10af8)`, `stop_pc` at 0x10ce0 where the two end-of-room paths rejoin **)** | 524 | ✅ verified | four cases: the ghost walked right to room 35's door over ~100 animation frames, the door's two object slots opened and then retired to -1, the fall through it, the bonus bar cashed in at 100 a step with the fx8 glissando, and the winner's turn parked (two players, either one up) or the game ended (one player). The fourth case's bar is ALREADY at the floor, so the tally runs zero times — which is the only thing that leaves the level-clear trigger's own volume observable |
| `0x10af8` | `game_room_exit` **(slice** `[0x10af8, 0x10ce0)` **)** | 488 | ✅ verified | seven cases: the ordinary exit from a fresh room (the room bonus and the tally), one already visited (neither), a practice game (which ends the turn), a turn already out, a pending handover, a room left after three deaths, and one left after 100 — which is STAGED and not reachable, and is what the word-sized bonus arithmetic would need |
| `0x10ce0` | `game_end_of_turn` **(slice** `[0x10ce0, 0x10d34)` **)** | 84 | ✅ verified | six states: who, if anyone, is still in. A two-player game asks each player's own life count and only about the one whose turn it was; a one-player game asks the live count and takes both players out with it. `stop_pc` at the room loop's own `while (either player is in)`, which is the composition's and not this slice's |
| `0x10d44` | `game_over_card` **(slice** `[0x10d44, 0x10de6)`, `stop_pc` at 0x1027e — the branch back to the top of the game loop **)** | 162 | ✅ verified | three cases, and two of them write nothing: the card is one-player, non-practice only. `stop_pc` at the branch back to the top of the game loop, which is what says the `do { … } while (true)` really closes |
| `0x115d6` | `title_menu_open` **(slice** `[0x115d6, 0x116c4)` **)** | 238 | ✅ verified | the last game's scores offered to the hall of fame, the menu painted, and the keyboard flushed. Two cases: one whose table no candidate can beat (the submitter's early return) and one that inserts, re-sorts and writes GHOST.SCR — the second being the only thing in this section that can see a CALLEE FRAME at all, since `save_hiscores`' mouse form is read out of its own frame three `jsr`s down |
| `0x115de` | `menu_draw` **(slice** `[0x115de, 0x116c4)` **)** | 230 | ✅ verified | the same without the submitter, which is where the redraw loop re-enters: `sound_stop_all`, the screen cleared, `Setpalette(dat_palette)`, the logical screen onto the visible page, `vst_height(6)`/`vst_color(1)` and the four "Press [x]…" lines, then the flush — run with 0, 1, 3 and 7 keys queued, so the loop eats none, one and the model's whole queue |
| `0x116c4` | `menu_read_key_and_fold` **(slice** `[0x116c4, 0x11700)` **)** | 60 | ✅ verified | fifteen keys: the four the menu dispatches on, their lower-case forms, the fold's own boundary at '`', and two with bit 7 set — which are NEGATIVE as a sign-extended byte and so are never folded. The ANSWER is compared against the oracle's own D0 at the same PC, because the four compares after it write nothing |
| `0x11708` | `menu_ask_player_count` **(slice** `[0x11708, 0x11774)` **)** | 108 | ✅ verified | `[G]`: the two "Press [1]/[2]" lines onto the visible screen, and the flush the loop's first pass makes before it reads a digit |
| `0x11774` | `menu_read_player_count` **(slice** `[0x11774, 0x117cc)` / `[0x11774, 0x1175a)` **)** | 88 | ✅ verified | five keys x two checks: '1', '2', and the three ways a key is neither — a digit that is not 1 or 2, a non-digit, and '3'. The core ANSWERS which way it went (the next pass would begin with a blocking read, which is where a slice has to end) and a second case reads the count back |
| `0x117de` | `menu_ask_practice_level` **(slice** `[0x117de, 0x1183e)` **)** | 96 | ✅ verified | `[P]`: all three scores zeroed, one player, the "Enter level number" prompt, and the first digit's flush |
| `0x1183e` | `menu_read_level_tens` **(slice** `[0x1183e, 0x1186c)` **)** | 46 | ✅ verified | five keys including a non-digit: the read is filed as a WORD less `'0'` — `move.w d0` keeps the ASCII half of the console answer and throws the scancode away — and the second digit's flush follows it |
| `0x1186c` | `menu_read_level_units` **(slice** `[0x1186c, 0x1191e)` **)** | 178 | ✅ verified | nine levels x two checks: both ends of the 0 < n < 36 gate, the two digits' carry, one square from each of the six grid rows, and three REFUSALS (0, 36 and 99). The 6 x 6 search that turns a level into a square, which reuses the two digit globals as its own loop counters WITH THE ROLES REVERSED and puts them back from the frame |
| `0x11930` | `menu_attract_sequence` **(slice** `[0x11930, 0x11ae6)` **)** | 438 | ✅ verified | `[D]`, phase one, with the left button held: room 1 composed, shown and given its ambience, then ONE record of the replay — one and not none, because the button is polled by the record body rather than before it |
| `0x11ae6` | `menu_attract_slideshow` **(slice** `[0x11ae6, 0x11c34)` **)** | 334 | ✅ verified | phase two's head at both ends of the range: `Random()` is one poked longword, and 0 and the 24-bit maximum are what `../notes/frontend.md` §6 derives 5 and 15 rooms from. Only the LENGTH is observable from here — it is drawn before the loop's first test — and the room is the row below |
| `0x11b30` | `menu_attract_slideshow_room` **(slice** `[0x11b30, 0x11c1c)` **)** | 236 | ✅ verified | ONE room of the slideshow, with the button UP so the whole body runs: the room's own `Random()` scaling, the room composed and given its ambience, and thirty frames of three `Vsync`s and a present. **The loop around it is not affordable in one run** — five rooms is the shortest the range allows and each is thirty 25,600-byte presents, which fills the oracle's write ledger — so the body is a slice and the loop is the composition |
| `0x11c34` | `menu_attract_title` **(slice** `[0x11c34, 0x11ca8)` **)** | 116 | ✅ verified | phase three, button up and button down: `show_presentation` and its louder trigger, which a run arriving with the button already down skips entirely, and then the 37,000-poll idle |
| `0x11992` | `demo_play_record` **(slice** `[0x11992, 0x11acc)`, and the loop `[0x11992, 0x11ae6)` **)** | 314 | ✅ verified | seven fixed records — the origin, two blowing cells, a popped bubble, one with NEGATIVE bytes and both byte extremes — plus 8 x 8 chunk-seeded random ones, each six signed bytes into the six globals the renderer reads. Plus THREE composition cases that chain four records of the REAL GHOST.DEM in one run from three different cursors, which is what pins the loop: the cursor stepped six bytes a record, the counter read before it is decremented, and the mouse poll at the end of each pass |
| `0x11cba` | `menu_hall_of_fame` **(slice** `[0x11cba, 0x11d60)` **)** | 166 | ✅ verified | `[H]` over four values of `max_room_reached`: `draw_hall_of_fame`, the screen cleared, `Setpalette(pre_palette)`, the room the player got furthest into drawn behind the HUD, room 0 as the picture and its ambience, then one pass of the idle loop the button ends |

**430 cases.** The fuzzes are CHUNK-SEEDED rather than chunk-partitioned (`test/abi.py`'s `shard`
docstring tells the two apart), so each is `CHUNKS` x its own per-chunk count: `vro_cpyfm` 8 x 12
copies, `v_gtext` 8 x 8 strings, the sprite protocol 8 x 8 placements through each of three
routines, and `load_hiscores` 8 x 6 files. `make guarded` passes over the whole suite: this
subsystem indexes the image with addresses out of the parameter block and with the conterm pointer
it builds from a word, so that is its surface.

**Mutations tried against this battery.** Thirty-three, each from a deleted `build/` with
`__pycache__` swept and each measured against a **fully green whole-suite baseline** (the README's
step 6: a suite with one unrelated failing test reports every mutant as killed). Thirty are **red**;
the three that survive are proved EQUIVALENT below rather than left as holes.

**The last four rows were re-run on 2026-09-06** against a whole-suite baseline of 1595 passing, and
each is new: three name coverage this battery did not have until that day, and the fourth replaces a
mutation that used to be caught only by the attribution pass's refusal.

| mutation | what caught it |
|---|---|
| `contrl`'s ptsin and intin counts swapped | 140 cases — the sprite fuzz, and every `vro_cpyfm` case behind it |
| `v_gtext` reporting the terminator as a character | 52 cases — a `contrl[3]` one long is a different call |
| an MFDB pointer's two halves swapped in `contrl` | 63 cases |
| `v_opnvwk` never restoring the lent `ptsin` pointer | 3 cases — the next call reads the caller's array as ptsin |
| `vro_cpyfm` never restoring it either | the `vro_cpyfm` fuzz |
| `aes_crysif` widening the count table UNSIGNED | 2 cases — the staged rows below; nothing else in the battery could |
| the bubble sprite table reached with the UNBIASED base | `test_build_sprite_bank` |
| `draw_sprites` filling the pxy in the save direction | 12 cases |
| the A1 `c_read` leaves not tracked | 15 cases — every trap after a read files `c_errno`, not the caller's A1 |
| the A1 `c_write` leaves not tracked | 12 cases — the same fact on the writing side |
| `screen_back` computed ABOVE `Logbase` | `test_init_gem_and_screens` |
| the sprite cell's far corner one pixel short | 24 cases |
| the bank screen 12 cells wide instead of 10 | `test_constants.py`, by name |
| the tile draw's leftover A2 without the staging offset | the four `draw_room_to_stage` cases |
| the per-cell poll filing the CURRENT cell's leftover A2 | the same four |
| the hall-of-fame candidate compare widened to `>=` | the equal-score row |
| `draw_hall_of_fame` not clearing `room_number` to the backdrop room | 3 cases — and only since the case stages a DIFFERENT room on entry |
| the hall of fame drawn from its WORST entry down | 3 cases |
| the hall of fame's row pitch one pixel wide | 3 cases |
| one of the five hall-of-fame label rows moved a pixel | 3 cases — the labels are five separate `sub.w #imm` in the original and are transcribed as five values, so the row-pitch mutation above does not cover them |
| the two players submitted in the other order | 2 cases |
| the pending room widened UNSIGNED | 2 cases — the staged high-bit rows below |
| `save_hiscores` writing the room field six digits wide | 12 cases |
| `save_hiscores` showing the mouse where it hides it | 12 cases — the AES mouse mode is OFF-IMAGE, so the ordered OS event ledger is what sees this |
| `save_hiscores`' ENTRY mouse form taken as a constant | 2 cases — the prologue slice, which exists for this |
| the prologue's `Setscreen` skipped | 3 cases — the trampoline's three save slots |
| the per-cell `vq_mouse` guarded to the LAST cell (2026-09-06) | 49 cases — every `test_draw_room_to_stage_cell` but cell 49. It passed all 225 cases of this battery before the per-cell slice existed: a poll over a fixed mouse state is idempotent, so a run to `rts` sees only the last one |
| the tile draw reporting its A2 WITHOUT the tile band (2026-09-06) | 54 cases — the fifty per-cell slices compare the answer against the oracle's own A2, and the four whole-routine cases see the wrong register filed |
| the sprite trio's `src fd_addr := 0` deleted (2026-09-06) | 14 cases, by BYTE DIFF. With both MFDBs staged `fd_addr = 0` it was caught by ONE case and only as the attribution pass refusing the run; the two MFDBs now enter holding distinctive junk rasters, so a deleted store makes the copy read the wrong raster |
| the grab of sprite cell 50 skipped (2026-09-06) | `test_build_sprite_bank`. It passed all 225 cases before the Malloc arena was seeded: cell 50 (`bubble_sprite[3]`) is 512 ZERO bytes in the real GHOST.DAT, and an untouched `c_malloc` buffer is zero too |
| the menu's case-fold boundary 0x60 -> 0x40 (state machine) | 15 cases — `test_menu_read_key_and_fold`, whose rows include '`' itself |
| a demo record's ghost x scaled by 2 instead of 3 | 71 cases — every record case and the chained-replay compositions |
| the demo's puff arm and its release swapped | 70 cases |
| the demo cursor stepped by five bytes rather than six | `test_demo_replay_chains_records`, and every per-record case behind it |
| the bonus bar's floor 0x23 -> 0x24 | the room-frame and both end-of-room batteries |
| the ending walk stepping AFTER its test rather than before | 4 cases — the walk ends ONE PAST `TOP_ENDING_WALK_TO`, which only a whole run of the animation shows |
| '0' accepted as a player count | 10 cases — the `[G]` read's own answer, both arms |
| the two players' slots swapped at the end of a turn | 6 cases |
| a spare life awarded on every exit, not only from below | 5 cases — the room-setup world that enters from BELOW exists for this |
| the bubble's entry x taken from the y word | 5 cases |
| the practice entry direction defaulting to the RIGHT instead of the left | 5 cases |
| `room_wipe_in`'s own note 0x3c -> 0x3d, now that the routine is whole | 5 cases — the room-setup slice, which is what closed that residual |
| the ambient countdown's scale and offset applied in the other order | 1 case — the room-frame row whose countdown underflows |
| the level-clear trigger's volume 9 -> 8 | 4 cases — and only since `ENDING_STATES`' last row cashes in a bar ALREADY at the floor: every tally step rewrites the same voice record, so on any other row the trigger's own volume is overwritten before the run ends |
| a callee frame costing 4 bytes instead of 8 | `test_title_menu_open_submits_the_last_games_scores` — and only since it stages `SAVE_COUNTER_ON_ENTRY` at the frame the derivation predicts. Every other case here stages a hall of fame no candidate can beat, so nothing reached a callee that reads its own frame, and the whole three-deep derivation was unpinned |
| the shared animation frame drawn BEFORE the backgrounds are saved | 5 cases — the five-call sequence moved to `include/frontend.h` this wave, where `src/gameplay.c`'s death sequence runs it too |
| the shared long countdown testing the DECREMENTED value | 3 cases — the attract loops run one pass fewer, which is what the "read the value it arrived with" comment is about |
| the room-grid column stride taken as a longword | 5 cases |
| the room ambience played on the blow's voice instead of voice 0 | 1 case |
| `SND_FX_ROOM_WIPE` 2 -> 3, now that the fx indices live in `include/sound.h` | 5 cases — the room-setup slice, which is where `room_wipe_in`'s trigger is run |
| the bubble's entry Y read from the X word of the same pair | 5 cases — through `src/gameplay.c`'s `room_entry_coordinate`, which this wave stopped re-deriving |
| the hall of fame installing GHOST.PRE's palette | NOTHING — and it was a REAL DEFECT, written that way and found by a review pass reading `move.l -7672(a4)` @ 0x11cc2 against the C. `Setpalette` is a modeled no-op whose argument push lands in the dropped frame band, so no case here can ever see it; the surface is an on-target run. Recorded as a kill of the REVIEW rather than of the suite |
| the room wipe's volume step 8 -> 1 | 5 cases — and only since every world stages `A_sound_enabled` (below) |
| the menu ambience's volume step 8 -> 1 | 51 cases |
| the front end's loud volume 0xb -> 0xc | 50 cases |
| each of the practice entry direction's THREE ranges moved by one, at each end | 5 cases each — and only since `ROOM_SETUP_STATES` grew a practice row at BOTH ends of every range (rooms 1, 5, 13, 17, 25, 29) and one singleton |
| the slideshow room's `Random()` scale and offset applied in the other order | 1 case — the single-room slice, which is the only thing that runs the room roll at all |
| `DEMO_SLIDESHOW_FRAMES` 30 -> 29 | 1 case — the same |
| the title picture's trigger played at the ambience volume | 1 case — `test_menu_attract_title`'s button-UP row, which is the only thing that runs `show_presentation` here |

**FOUR MORE MUTATIONS SURVIVE AND ARE EQUIVALENT, from the state-machine wave.** Each is recorded
with its proof so nobody re-tries it:

* **The FIRST TWO of the slideshow's three per-frame `Vsync`s' return addresses.** The three calls
  are consecutive with nothing between them, and each overwrites `A_trap_saved_ret`, so only the
  LAST one's slot survives to the diff. `RET_DEMO_VSYNC_A` and `_B` are transcribed from the
  disassembly and unpinned; closing it means a `stop_pc` between two `jsr`s, which nothing else
  wants.
* **The slideshow's length divisor read from the ROOM's copy of it.** They are two DATA addresses
  holding the same eight bytes (16794009.0), and `fp_dispatch` reads the operand's value — so no run
  can tell them apart. Same shape as `save_hiscores`' file name below, and pinned the same way:
  `test_the_two_random_divisors_are_distinct_addresses_holding_one_value` pins the contents of each
  address and asserts the two are distinct.
* **`DEMO_TITLE_POLLS` 37,000 -> 36,999.** The counter lives in the frame band the differential
  drops, and the loop's whole body is one `vq_mouse` over a FIXED mouse state — which is idempotent,
  so one poll fewer writes exactly what one poll more does. The same argument
  `draw_room_to_stage`'s per-cell poll needed a slice for; here there is no per-poll slice to make,
  because the poll is the entire body.
* **And the fourth, which is about the code rather than the model:** `game_room_exit`'s room bonus,
  `5000 - deaths * 500`, computed in an `int32_t` instead of an `int16_t`. The very next line widens it
  The very next line widens it with `sign_ext16`, which truncates to the same low word either way —
  so the `int16_t` is documenting the `sub.w` rather than doing the work, and no value of
  `deaths_in_room` can separate the two. A row staging 100 deaths is in `ROOM_EXIT_STATES` anyway,
  because the arithmetic it exercises is real even where this mutation is not.

**FOUR STAGING DECISIONS THIS WAVE'S OWN SWEEPS FORCED**, all the same defect as the four above — a
case that stages the value the routine is about to write, or does not stage the one it reads:

* **All three voices are FREE on entry** (`VOICES_FREE`). `sound_play` refuses a voice whose current
  priority outranks the offer, and the seed writes NOISE over the three voice records — so over
  random priorities every sound trigger in the state machine was a no-op, and a trigger that never
  runs cannot tell one volume, definition or note from another.
* **The `[S]` TOGGLE IS ON in every world** (`SOUND_ON`). Every trigger here scales its volume by
  `A_sound_enabled`, which the loaded image holds as ZERO — so over the default every volume step
  multiplied to 0 and one volume constant was indistinguishable from another. Measured:
  `WIPE_SFX_VOLUME` could be changed from 8 to 1 with the whole suite green.
* **The two file names `init_globals` builds in the BSS are put back over the seed**
  (`VOICE_NAMES_IN_BSS`). They sit immediately above the three voice records, inside the guard band
  the seed writes either side of every span, and noise over them makes the voice player open a name
  nothing staged — which the model refuses, taking the whole run with it. Restoring them as a later
  layer keeps the guard, which is what would catch a voice record written one word too far; the
  ADJACENCY it depends on is asserted at the top of the battery rather than assumed.
* **`ROOM_SETUP_STATES` stages a practice room at BOTH ENDS of all three entry-direction ranges.**
  With one practice row only the table's fall-through arm ever ran, and a range moved by one at the
  end nobody reached survived.

**Three mutations SURVIVE and are EQUIVALENT, not holes.** Each is recorded with its proof so nobody
re-tries it. A FOURTH used to be listed here and has moved to the residuals below —
`save_hiscores`' exit mouse form, whose equivalence holds only under a model gap, which makes it a
premise rather than a proof:

1. **The bubble sort's FIFTH pass.** Four passes instead of five is byte-identical for every input,
   and provably: the table has five entries and each pass makes four ADJACENT compares, so after
   four passes the largest four elements have each reached their place — a fifth pass can never
   swap. The original makes it anyway (it counts its swaps in a local it never reads, so there is no
   early exit), and the reconstruction transcribes that.
2. **The A1 `save_hiscores` RETURNS with not escaping to its caller.** The transcription is right —
   its `c_write`s leave A1 at `c_errno`, and the two-player arm's second offer traps with no
   intervening call — but the evidence is overwritten: every later trap in the second pass re-files
   `c_errno`, so the final slot agrees whatever the reconstruction threaded. Closing it means a
   `stop_pc` inside the second pass, which is a slice of `hiscore_submit_players` nothing else wants.
3. **`save_hiscores` creating the file through `load_hiscores`' copy of the name.** The two are
   different addresses holding the same eleven bytes, and the model resolves a staged file by NAME,
   so no run can tell them apart. `test_the_loaders_open_the_names_the_reconstruction_points_at`
   pins each address's contents instead, and a case asserts the two addresses differ.

**Three mutations were survivors on the first pass, and each names a branch the GAME'S OWN DATA
CANNOT REACH.** They are why three groups of cases exist, and each stages the value rather than
inventing an answer:

* **`aes_crysif`'s SIGNED count bytes.** Every row the program asks for (opcodes 10, 19, 77, 78)
  holds 0, 1 or 5, and the first byte at or above 0x80 in the whole table belongs to opcode 126 —
  which the model does not serve, so the run would be REFUSED rather than compared. The case stages
  the row instead: the table is ordinary image memory both sides read, so a row with a high byte in
  it is an input to the routine's arithmetic and not a fabricated answer.
* **the pending room's SIGNED widening.** A room is 0..35 and even a corrupt GHOST.SCR parses at
  most 99, so the `ext.l` is unreachable through the game's data. The word is staged with its high
  bit set — it is a plain word global and the case pokes it, like any other input.
* **the per-cell poll's A2 ordering**, which needed the tracking to move with the statement before
  it was a real mutation at all.

**One mutation is EQUIVALENT for a different reason**, and is recorded so nobody re-tries it either:
swapping the `vq_mouse` and the tile draw inside `draw_room_to_stage`'s loop WITHOUT moving the A2
tracking with them. The two write disjoint regions — the input block and the staging area — and the
register the poll files is unchanged, so no image can tell the orders apart. Moving the tracking too
is the real mutation, and it is red. So is `init_gem_and_screens`' `work_in` loop bound: raising it
from 10 to 11 writes a 1 into `work_in[10]` that the very next line overwrites with 2.

### Residuals — what these rows do NOT pin

1. **`save_hiscores`' EXIT mouse form is equivalent UNDER THE MODEL, and the premise is the model
   gap.** The reconstruction files the routine's own loop counter, and after the loop that counter
   IS `HISCORE_SLOTS`; a version that passed the constant is byte-identical for every case. The only
   path on which the two differ skips the loop, and it is the `c_creat` FAILURE arm — which no run
   can reach, because `os_fcreate` REFUSES an unstaged name rather than answering negative
   (residual 7 below is the same premise on the reading side). So this is not a proved equivalence
   about the program: it is an equivalence about the program *as the model can run it*, and it stops
   being one the day the model can answer a failed create. Recorded here, beside the other things
   the rows do not pin, rather than in the mutation table's list of equivalents.
2. **The A1 `save_hiscores` returns with is threaded but not PINNED**, and the mutation table's
   third equivalent says why: every later trap re-files `c_errno`, so the value the two-player arm
   carries into its second offer is overwritten before the `rts`. It is transcribed rather than
   dropped because it is what the machine does; closing it means a `stop_pc` inside that second
   pass, which is a slice of `hiscore_submit_players` nothing else wants.
3. **Every XBIOS call this subsystem makes is a NO-OP in the model.** `Getrez`, `Logbase` and
   `Setpalette` write hardware or answer a machine fact, so what a reconstruction reproduces is the
   trampoline's three save slots and the modeled result — a wrong palette or a wrong screen base is
   byte-identical here. **The surface is the on-target smoke run** (`docs/on-target-execution.md`),
   and this project has no `.PRG` yet.
4. **The VDI's colour indices are the model's, not TOS's.** The model writes the colour index
   straight into the planes; real TOS maps VDI pen numbers through a table, so a reconstruction
   verified here draws the right shapes in the wrong colours on a real machine (TRAP_MODEL.md,
   Phase 12). Same class as 3, and the same surface.
5. **The font is the model's synthetic glyph set, not TOS's.** Every `v_gtext` case compares the
   pixels both sides draw from one parameter block, which is the whole of what a differential can
   pin; whether those pixels read as text is an on-target matter.
6. **`graf_mouse`'s `mform` argument is stack garbage at both call sites**, which push only the mode
   word — so the long it reads is really the caller's own return address. It is an argument here for
   that reason, and the AES ignores it for M_OFF and M_ON; the claim is about the AES, not something
   a case observes.
7. **The failure arm of all four loaders is unreachable under the model.** `os_fopen` REFUSES an
   unstaged name rather than answering negative, so the retry loop runs once and
   `load_hiscores`' "no file: every score 0, every room 1" path is transcribed and read-verified.
8. **The `short` return values are compared as D0's LOW WORD**, which is the Alcyon C ABI's answer
   and what every caller reads. `vst_color`, `vsf_color`, `aes_crysif`, `appl_init` and
   `graf_handle` are the routines here that answer at all.
9. **CLOSED, and recorded so the shape is not re-invented.** Three 68000 idioms used to have a
   second home in `src/frontend.c`: `LONGWORD_BYTES` (a second NAME for `src/blit.c`'s `LONG_BYTES`,
   which `test_constants.py`'s name-keyed duplicate check could never see), `tile_draw_leaves_a2`
   (a second spelling of the `muls.w`+`ext.l` destination arithmetic) and `show_presentation`'s
   30,720-byte copy loop (a second spelling of `copy_longs_ascending`). They now live in
   `include/common.h` — `LONG_BYTES`, `muls_ext_w`, `copy_longs_ascending` and `longword_slot` — and
   the A2 restatement is gone entirely: `draw_room_tile_to_stage` REPORTS the register it leaves.
   `include/common.h`'s own header says why these are not in the kit's `machine.h`: that header is
   the ISA, and these are the Alcyon compiler's idioms.
10. **`vro_cpyfm`'s MFDB record is named twice, once per side of the seam**, and the two sets are
   pinned equal TO EACH OTHER by a single `_Static_assert` in `src/frontend.c` rather than by a
   redefinition warning: only two of the six fields are spelt the same in both headers
   (`include/blit.h`'s `MFDB_WIDTH`/`HEIGHT`/`STANDARD`/`PLANES` against the kit's
   `MFDB_W`/`H`/`STAND`/`NPLANES`), so a drift in the other four could never warn at all. The game's
   six values are captured under private `GAME_MFDB_*` names, all six of the game's spellings are
   `#undef`ed — not just the two that collide, so a line in that file meaning the model's record
   cannot silently be written against the game's — and the assertion compares one header with the
   other. It used to be two assertions against LITERALS, which would both have had to be edited to
   move a field. That file is the only translation unit that includes both.

11. **A NEGATIVE `c_read` is unreachable, so the arm that skips the A1 report is transcribed and not
   run.** `src/frontend.c`'s loaders call `c_read_reporting` / `c_write_reporting`, which record A1
   at `A_c_errno` exactly where `c_getfdmode` leaves it — and `c_read` exits at 0x16710 BEFORE that,
   with A1 untouched, when the first Fread comes back negative. No case can produce one: the model
   refuses an unstaged file rather than answering an error, and a staged file always reads. The
   difference is why this file no longer wraps `c_read`/`c_write` and assigns A1 unconditionally
   afterwards, but the arm itself is read-verified. Its console twin is a premise instead of a
   residual: `test_no_loader_opens_a_console_pseudo_handle` asserts that none of the five names this
   subsystem opens is "CON:", "AUX:" or "PRT:", which is what makes a pseudo-handle unreachable.

12. **BOTH TOP-LEVEL COMPOSITIONS ARE READ-VERIFIED**, and each for a reason of its own.
   `game_top_loop` is a `do { … } while (true)` that never returns, so there is nothing a case could
   run to `rts` and a C function for it would be code no test could reach — `src/gameplay.c` says
   the same of `game_frame_update`. `title_menu_loop` DOES return, and cannot be run whole for a
   different reason: every pass of it ends at a blocking console read the model cannot cross (the
   gap table above). What each composition is, in order, is written out as prose in
   `src/frontend.c`; what is unrun between the slices is the five rows in "Not reconstructed".
13. **THE FOUR TEXT CARDS' HOLDS ARE EMPTY COUNTS, and the model has no clock.** Each is 300,000
   (or 100,000) iterations of `addq.l #1` and a compare, transcribed because the counter is image
   state that outlives the loop — but what a real machine spends on them is TIME, which no
   differential can see. Same class as residual 3 above and the same surface.
14. **THE ATTRACT SEQUENCE'S TWO LOOPS ARE RUN ONE BODY AT A TIME, never to their length.** Each
   phase is a slice and each has a case that runs its body — one GHOST.DEM record, one slideshow
   room, the title picture — but nobody has run 980 records or five rooms in one go: five rooms is
   thirty 25,600-byte presents each, which fills the oracle's write ledger. The replay's loop is
   pinned by `demo_play_record`'s four-record composition; the slideshow's is not, and the count it
   walks is a word in the dropped frame band. Its playback RATE is a second thing no case sees:
   there is no `Vsync` in the replay at all (`../notes/frontend.md` §8), so on a real machine it
   runs at whatever the renderer costs.
15. **THE `[H]` ARM'S `Setpalette` IS READ-VERIFIED, AND THIS IS WHERE THE PORT GOT IT WRONG ONCE.**
   It installs GHOST.DAT's palette — its backdrop is room 0, a GHOST.DAT picture — and the
   reconstruction was written with GHOST.PRE's. `Setpalette` is a modeled no-op whose argument push
   lands in the band the differential drops, so no case can tell the two globals apart; the defect
   was found by a review pass reading `move.l -7672(a4)` @ 0x11cc2 against the C, and the mutation
   that restores it still SURVIVES the whole suite. Every `Setpalette` and `Setcolor` argument in
   this project is in that position (residual 3), and the surface for all of them is an on-target
   run.
16. **`game_top_boot`'S OPENING `graf_mouse` MOUSE FORM IS THE HARNESS'S OWN SENTINEL.** The call
   pushes a zero word and the mode, so the `addr_in` LONG the AES reads spans that zero and the word
   at `frame - 10`; a mid-entry slice's frame must sit exactly `TOP_LOCAL_BYTES` above
   `emu.STACK_TOP` (or its callees' frames land where the oracle's do not), which puts `frame - 10`
   ON `emu.STACK_TOP` — where `emu.run` writes the sentinel return address. Both sides therefore read
   that word's zero high half, and a reconstruction reading a DIFFERENT offset of the same frame
   would match. `save_hiscores`' two calls have the same shape and ARE pinned, by
   `test_title_menu_open_submits_the_last_games_scores`; this one is not, and closing it means a
   harness that lets a case choose where the sentinel goes.
17. **THE TWO IKBD COMMANDS ARE LEDGER ENTRIES AND NOTHING ELSE.** `Bconout(4, $12)` and
   `Bconout(4, $08)` touch no memory, so the ordered OS event stream is the only thing that can tell
   a reconstruction which makes them from one which does not — and whether the 6301 really stops
   reporting the mouse is an on-target matter (`docs/on-target-execution.md`).


## Verified — gameplay (15)

The in-room simulation: the castle's four data tables, the ghost, the blow, the bubble and the
hazard model — plus the HUD, both its number formatter and the three painters that draw through the
front end's VDI binding. `../notes/gameplay.md` is the design doc,
`include/gameplay.h` the frozen record layout, and `src/gameplay.c`'s header comment says why
`game_frame_update` is nine slices rather than one function.

**This subsystem now owns the three globals `include/blit.h` held on loan.** `A_room_number`,
`A_object_table` and `A_room_table` — and the `OBJECT_*` / `ROOM_*` record offsets that moved with
them — are defined in `include/gameplay.h`; `src/blit.c` includes it to read them, and the three
rows that predicted this move are gone from "Borrowed globals" below.

**`game_frame_update` IS NOW WHOLE.** The two regions that used to sit between and inside its
slices — the front-end poll `[0x1233a, 0x12434)` and the death sequence `[0x1273c, 0x1294a)` — have
rows of their own below, filed under the addresses the slices start at. What is left unrun is two
regions and no more, and `test_frame_slices_tile_game_frame_update` re-derives both: the four-byte
`unlk a6 / rts` epilogue, which no mid-entry slice may reach, and the 64-byte `^P` pause inside the
poll, whose residual is below.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x10f20` | `reset_world_state` | 936 | ✅ verified | run to `rts`; 3 seeds of noise over the three room-indexed tables and both players' 58-word blocks, plus poison. 174 straight-line stores, one list |
| `0x114ee` | `itoa_padded` | 232 | ✅ verified | run to `rts`; every digit count the HUD reaches (0..0x7fffffff) x widths 1 and 6, widths 0/2/8, the three NEGATIVE values (`c_ldiv` is signed, so those write characters below `'0'`), and poison. Composes the verified `c_ldiv` and `c_strlen` |
| `0x129b4` | `ghost_blow` **(slice** `[0x129b4, 0x12ff8)` **)** | 1604 of 1616 | ✅ verified | `stop_pc` at the `jsr hud_draw_counters` that ends the candle script — the score award IS inside the slice, only the drawing of it is not. Covers: the puff and its idle-voice gate; the `|dx| < 50` / `|dy| < 50` range gate at both bounds and at -32768 (`neg.w` of the most negative word is itself); all eight facings armed and all eight missed; the four diagonal cones at their `bge`/`ble` boundaries; the candle script over all ten shipped candle rooms, each placed from the room's OWN data; the four window bounds from both sides; the left-facing requirement. **Residual:** the two redraws the slice stops short of — `hud_draw_counters` @ 0x113d2 and `present_score_strip` @ 0x131f0, both of which are now verified in their own right, so what is left is to move the `stop_pc` to the `rts` and stage the VDI world in all 360 cases |
| `0x12322` | `game_frame_update` **(7 slices)** | 902 of 1682 | ✅ verified | Seven mid-entry slices, each entered at its own PC and diffed at the next one's: `[0x12322, 0x1233a)` the bubble's frame counter; `[0x12434, 0x124a4)` the mouse divided down through the software float package; `[0x124a4, 0x1255c)` blowing or recovering (entered with the caller's A1/A2, which the two `Setcolor` trampolines file); `[0x1255c, 0x125e6)` the mouse buttons' facing latches; `[0x125e6, 0x126e2)` the two fan slots; `[0x126e2, 0x1294a)` the bubble's own step, pop included; `[0x1294a, 0x129b0)` the drift pulse. The 186 + 526 bytes the two rows above carry make the routine's covered total 1,614 of 1,682 — the rest is the 4-byte epilogue and the 64-byte `^P` pause. **Residual:** slice 3's ONE precondition below |
| `0x13004` | `bubble_collision_probe` | 492 | ✅ verified | run to `rts`; the phase stepped from 0..5 and from outside it, each of the eight rim probes driven alone with one non-background pixel under it, the word-truncated phase offset at phase 1024, and 8 x 12 chunk-seeded fuzz cases over a noisy screen. Composes `get_pixel` |
| `0x13bea` | `get_pixel` | 130 | ✅ verified | run to `rts`, ANSWER compared (it writes nothing): all sixteen colour indices, all sixteen bit positions, five rows of ladder addressing, six negative-x rows (`divs.w` truncates toward zero and the bit index runs past 15), four row-offset wrap rows, and 8 x 12 chunk-seeded fuzz |
| `0x13d2c` | `restore_world_p1` | 356 | ✅ verified | run to `rts`; 3 noise seeds + poison, and the numbered-block case that pins the block being filled BACKWARDS |
| `0x13e90` | `restore_world_p2` | 356 | ✅ verified | as above |
| `0x13ff4` | `save_world_p1` | 356 | ✅ verified | as above |
| `0x14158` | `save_world_p2` | 356 | ✅ verified | as above |
| `0x112c8` | `hud_bonus_bar_fill` | 126 | ✅ verified | run to `rts`; six bar lengths — below the bar's left end, AT it (the loop runs zero times), one past it (the only length at which every `vr_recfl` still sees the CALLER's A2), two past it, 0x40 and the 318 a room starts at — plus the fuzz. Composes the verified `vsf_color` and `vr_recfl` |
| `0x11346` | `hud_bonus_bar_shrink` | 140 | ✅ verified | run to `rts`; eleven (bar, units) pairs either side of the `end - units + 1 < 35` branch, at it and past it — including a `units` that takes the difference negative and one of 0 — plus 8 x 6 chunk-seeded fuzz |
| `0x1233a` | `frame_poll_input` **(slice** `[0x1233a, 0x12434)` **)** | 186 of 250 | ✅ verified | `stop_pc` at the next slice's entry; the mouse and the shift keys through the verified `vq_mouse`/`vq_key_s`, then one `Crawio(0xff)` and the three control keys. Covers: six keys including two with bit 7 set, the stale-key flush loop taken and skipped, four mouse positions x two, six shift states, the `^S` toggle from zero and from three non-zero values, the `^R` whole-game reset with all seven cleared fields staged non-zero, an idle console, and the `^P` branch. **Residual:** the `^P` pause `[0x1239e, 0x123de)`, 64 bytes, read-verified — see below |
| `0x1273c` | `frame_death_sequence` **(slice** `[0x1273c, 0x1294a)` **)** | 526 | ✅ verified | `stop_pc` at the next slice's entry, on a world staged for the eight verified routines it composes. Covers: the frame-counter gate at both sides of `BUBBLE_DEATH_TRIGGER_FRAME` and at it; four ghost tiles through the walk-back (zero, one, three and seven passes); the five `Random()` answers that give all five distinct per-cell holds (2..6); the four entry directions the game uses and one that overflows the word its offset is added through; both `p1_turn` arms of the two-player handover and the one-player arm that parks nothing |
| `0x113d2` | `hud_draw_counters` | 284 | ✅ verified | run to `rts` with poison; eight (score, hi, room, lives) rows covering every field width, 0x7fffffff, a NEGATIVE room (which pins the `ext.l` that widens it) and both negative-lives arms, plus the fuzz. Composes the verified `vst_height`, `vst_color`, `v_gtext` and `itoa_padded` |

**482 cases.** The fuzzes are CHUNK-SEEDED rather than chunk-partitioned (`test/abi.py`'s `shard`
docstring tells the two apart), so each is `CHUNKS` x its own per-chunk count: `get_pixel` 8 x 12
probes, `bubble_collision_probe` 8 x 12 worlds, the fan test 8 x 10 placements and the bubble step
8 x 8 velocity/screen pairs. `make guarded` passes: `get_pixel` indexes the image with an address
it computed from a signed row offset and a signed cell index, with no bounds test of any kind.

**No poison pass on the collision probe or on the frame slices**, and the reason is
`docs/agent-playbook.md` §8's: `probe_phase`, `bubble_frame`, `breath`, `ghost_anim` and
`drift_pulse` are all read-modify-write counters that also STEER the run, so pre-inverting them
diverts it instead of catching a coincidence. The routines that only write — the world block's
five, `itoa_padded` — are run under poison.

**FOUR staging decisions, each of which a measured survivor forced.** They are the same defect four
times — a case that stages the value the routine is about to write, so writing it and not writing it
look alike — and they are written here because the next case added to this battery will want them:

* **`drift_vel_x` / `drift_vel_y` are seeded NON-ZERO** in every blow case. An orthogonal blow arms
  only the axis it moves along; against a zero that is indistinguishable from a reconstruction that
  wrote `0 * speed` to the other. Measured: the both-axes form passed all 360 cases.
* **`drift_pulse` / `drift_interval` too**, for the same reason one field over: `arm_drift` clears
  both, and a reconstruction that dropped the two clears passed all 374.
* **A "busy" voice stages BOTH `SND_VC_DURATION` and `SND_VC_PRIORITY`, and the priority is BELOW
  the puff's own.** `sound_voice_priority` reads the priority and `sound_release_voice` returns at
  once on a zero duration — and with a priority ABOVE the trigger's, `sound_play` refuses by itself,
  so a reconstruction with no idle-voice gate at all is still byte-identical. Both halves were
  measured as survivors.
* **`ghost_x` / `ghost_y` are seeded non-zero in the mouse-scaling cases**, or the `mouse = (0, 0)`
  rows pass with the whole slice deleted.

**Mutations tried against this battery**, each from a deleted `.so` with `__pycache__` swept, and
each **red**:

| mutation | what caught it |
|---|---|
| `get_pixel` counting bits from the RIGHT of the plane word | 38 cases — the bit-position ladder and every probe case behind it |
| `get_pixel`'s row offset multiplied in 32 bits (no `ext.l`) | 4 cases — `test_get_pixel_row_offset_wraps_in_a_signed_word`, which is the only thing that reaches row 205 |
| the probe using the phase it ARRIVED with instead of the stepped one | 8 cases |
| the probe's phase offset added in 32 bits | 1 case — `test_probe_phase_offset_wraps_in_a_signed_word`, built for it: the game's own phase never leaves 0..5, so the case plants eight probe pairs at the word-truncated address itself |
| `arm_drift` writing BOTH velocities on an orthogonal blow | 11 cases — and only after the staging decision above; it survived on zeroed velocities |
| the candle's two map-patch tiles swapped | 10 cases |
| the world block filled forwards | 21 cases — including `test_world_block_is_filled_backwards`, which numbers all 58 words |
| the drift pulse firing after the decrement rather than on the frame it was already 0 | 25 cases |
| the fan's room offset added in 32 bits (`add.l` instead of `adda.w`) | 2 cases — `test_frame_apply_fans_room_offset_wraps_in_a_signed_word`, which plants a fan where the WORD-truncated offset points; the game's own 0..35 never overflows |
| `ghost_blow`'s object room offset truncated to a word (the fan test's shape) | 2 cases — the mirror-image case, which plants the flame object where the 32-BIT address points |
| `itoa_padded` padding one short | 12 cases |
| the blow range gate widened from `< 50` to `<= 50` | 1 case |
| the blow range gate measured in 32 bits (a total `abs`) | 2 cases — the -32768 rows, each facing the direction that offset would blow in |
| `blow_facing_plus1` computed without the `+ 1` | 87 cases |
| the bubble frame wrapping at 11 instead of past 12 | 1 case |
| the bubble step dropping the fan's `x_impulse` | 10 cases |
| the two `Setcolor` return addresses swapped | 2 cases — the trampoline's three save slots are the whole of what a reconstruction can reproduce about a modeled-as-no-op trap |
| room 35 scaled with the ordinary mouse divisor | 3 cases |
| `DRIFT_SPEED_FLOOR` 100 -> 150 | 5 cases |
| `DRIFT_INTERVAL_MAX` 200 -> 100 | 3 cases |
| the facing wrapping one step early (`>= 7` / `<= 0`) | 2 cases — and only after `test_frame_step_facing_wraps` grew the rows JUST INSIDE each end |
| the left button's latch never re-arming | 18 cases |
| the puff's idle-voice gate deleted (`if (1)`) | 13 cases — and only after a busy voice stopped being staged at field 0 with a priority above the trigger's |
| either `sound_release_voice` in slice 3 replaced by a no-op | 2 and 10 cases — the `voice_busy` rows of the shift-gate and breath batteries |
| the cone test deleted from the up-right arm / from the up-left arm | 2 cases each — and only after `test_ghost_blow_cone_boundaries` grew rows that reach ±40 on all four cones, not just two |
| `arm_drift` dropping `drift_interval := 0` / `drift_pulse := 0` | 31 cases |
| `frame_scale_mouse_to_ghost` emptied | 18 cases — all of them, where 15 of 18 before |
| slice 6 always answering "the death sequence" | 5 cases — the dead-bubble rows, which now check the flag |
| the candle's x window widened at both ends (`>` / `<`) | 2 cases |
| the fan's dy band widened at both ends | 4 cases |
| `extinguish_candle` reading `A_room_number` ONCE instead of re-reading it | 1 case — `test_ghost_blow_candle_patch_can_move_the_room_number`, the only thing that separates the two programs |
| the candle's two DEST slots swapped (2026-09-06) | 13 cases — the extinguish script writes each record's tile into the other's slot |
| `muls_ext_w` multiplying in 32 bits, now that it lives in `include/common.h` (2026-09-06) | 11 cases across TWO batteries — `test_gameplay.py`'s two `get_pixel` row-offset wraps and its fuzz, and `test_blit.py`'s two tile-offset wraps and the wipe's word-sized counter. The helper used to be a private copy in each file, so a mutation had to be made twice to be measured once |
| a frame slice's `stop_pc` moved two bytes (2026-09-06) | 40 cases, and `test_constants.py::test_entry_addresses_still_point_at_their_routines` BY NAME — the `STOP_PROLOGUES` pin, which did not exist before that day |
| the entry-point offset added in 32 bits rather than through `adda.w` (2026-09-06) | 1 case — `test_frame_death_sequence_respawns_at_the_rooms_entry_point`'s `entry_dir = 0x4000` row, **added because a review pass measured the `sign_ext16` surviving**: the game's own `entry_dir` is 0..3 and cannot reach the wrap |
| `HUD_ROOM_X` 0x133 -> 0x134 (2026-09-06) | 17 cases — every `hud_draw_counters` row and the fuzz |
| `HUD_TEXT_PEN` 5 -> 6 (2026-09-06) | 17 cases |
| `hud_bonus_bar_fill` filing the CALLER's A2 on every column (2026-09-06) | 4 cases — the two bar lengths that run more than one column, and `test_hud_bonus_bar_fill_files_the_scanline_copys_a2` by name |
| `hud_draw_counters` leaving an exhausted life count at 0 rather than -1 (2026-09-06) | 8 cases |
| the room number widened WITHOUT the `ext.l` (2026-09-06) | 6 cases — the negative-room row, built for it: a word-sized widening draws room -1 as "35" |
| `hud_bonus_bar_shrink`'s surviving column off by one (2026-09-06) | 3 cases — the rows either side of the floor branch |
| `hud_bonus_bar_fill`'s loop bound widened to `<=` (2026-09-06) | 6 cases |
| the `^S` toggle inverted (2026-09-06) | 4 cases — and only after the poll's world started staging `A_key_raw` (see below) |
| `^R` leaving the life count at 0 rather than -1 (2026-09-06) | 1 case, by its own outcome assertion |
| the mouse `x` and `y` out-parameters swapped (2026-09-06) | 27 cases |
| the stale-key flush loop deleted (2026-09-06) | 6 cases — the `stale` half of the ordinary-key rows |
| the walk-back bound off by one (2026-09-06) | 1 case — `ghost_tile` = 5, the row built for the bound |
| `DEATH_HOLD_INITIAL` 5 -> 6 (2026-09-06) | 18 cases |
| the random scale and offset applied in the other order (2026-09-06) | 18 cases |
| the respawn's entry-point x taken from the y word (2026-09-06) | 16 cases |
| the two players' slot sets swapped (2026-09-06) | 2 cases — `test_frame_death_sequence_parks_the_turn`, both arms |
| `BONUS_BAR_Y` 0xbd -> 0xbe (2026-09-06) | the BUILD, by name: `src/gameplay.c`'s `_Static_assert` that `BONUS_BAR_ROW_OFFSET` is row `BONUS_BAR_Y` of the screen. Recorded as a kill in the shape the pin takes, not as an untried mutation |

**Twelve of those were survivors** — six found by the port agent's own sweep and six more by an
independent reviewer — and each is why a case or a staging decision exists at all: the zeroed drift
velocities and pulse schedule, the two room-offset wraps, the probe's phase-offset wrap, the facing
wrap's inner rows, the range gate's -32768 rows facing the wrong way, the busy voice staged at the
wrong field, the two `sound_release_voice` calls nothing reached, the two untested cones, and the
zeroed ghost position under a zero mouse.

**One of the review's findings was a REAL DEFECT, not a coverage hole**, and it is the reason
`extinguish_candle` reads `A_room_number` twenty-eight times where a reconstruction naturally reads
it once: the first map patch can store into `A_room_number` itself (a tile column of 2923 puts
`room_table[0].map[0][x]` at exactly 0x23120), and everything after that store then works on the
room the store left. The first version of this port cached it, and no case reached the difference
until one was built for it.

**A FOURTH SURVIVOR, measured 2026-09-06 and equivalent by proof:** `set_object_tile_for` caching
`A_room_number` WITHIN one call instead of reading it twice. The original reads the word once to
reach the candle record and again to reach the object table, and the reconstruction transcribes
that — but nothing between the two reads writes memory, so the two are one for every input. What is
NOT equivalent is caching it ACROSS the four calls, which the row above shows is red: a store made
by one call can land on `A_room_number` itself.

**A MEASURED SURVIVOR THAT WAS A STAGING DEFECT, 2026-09-06, and the fifth of its kind here.** The
`^S` toggle could be INVERTED with the whole suite green. The post-init image holds `A_key_raw` = 1,
so every poll case that did not stage that byte ran the routine's flush loop — which ate the very
keystroke the case had staged, and the run then took the "no key" path while looking exactly like a
case that exercised a control key. The `^S`, `^R` and `^P` cases were all vacuous. `_poll_world` now
takes `stale_key` as an explicit input of every case, and the three control-key cases assert their
own OUTCOME off the oracle as well as diffing: the byte diff proves the two programs agree, and it
cannot say which arm ran.

**Two more mutations of the poll are EQUIVALENT BY PROOF, not holes**, and `POLL_KEYS`' two
high-bit rows say so rather than claiming to catch them. Both are about the key byte,
and both are worth recording so nobody re-tries them: the flush gate spelt over the sign-extended
word instead of the byte (`(int8_t)b != 0` iff `b != 0`, for every byte), and the key compared
WITHOUT the `ext.w` (the three control codes are all below 0x80, and a byte at or above it equals
none of them read either way). The transcription keeps the original's own spelling.

**Three mutations were tried and are EQUIVALENT, not holes**, and are recorded so nobody re-tries
them: `itoa_padded` reversing on its own digit count instead of re-measuring with `c_strlen` (the
digits it writes are `'0' + r` for `r` in -9..9, never a NUL, so the two lengths agree for every
reachable input); `speed < DRIFT_SPEED_FLOOR` widened to `<=`; and `breath > BREATH_MAX` widened to
`>=` — the last two write the same value they were about to clamp to. A mutation the suite does not
catch is a coverage hole, not a licence — record it here.

### Residuals — what these rows do NOT pin

1. **The composition of the nine slices.** Each is diffed over its own region, and the ORDER they
   run in is read-verified rather than run: no case enters `game_frame_update` at 0x12322 and leaves
   at 0x129b0. The reason is no longer a gap in the coverage — every region but the epilogue and the
   `^P` pause has a case now — it is the `^P` pause itself, which a whole-routine run would enter on
   a staged `^P` and never leave. A run that stages no key composes cleanly and is the shape a
   future case would take.
2. **The two `Setcolor` calls are no-ops in the model.** XBIOS `Setcolor` writes the shifter, which
   is not image state, so a reconstruction that recoloured the ghost wrongly — or never at all — is
   byte-identical here. Only the trampoline's three save slots are compared. **The surface is the
   on-target smoke run** (`docs/on-target-execution.md`), and this project has no `.PRG` yet.
3. **`frame_blow_or_recover` takes the caller's A1/A2 as an argument** (`docs/agent-playbook.md` §5,
   "a parameter"). The two trampolines file whatever the register file holds and nothing in the
   slice computes it; the case hands the same values to both sides. Nothing between the entry and
   either trap writes an address register (`sound_voice_priority` @ 0x1455e and
   `sound_release_voice` @ 0x14510 touch only D0/A0), so the claim is read-verified from two short
   routines rather than assumed. Closing it means porting `game_top_loop`.
4. **`frame_step_live_bubble` answers a flag this reconstruction invented.** The original falls
   into the death sequence; the core returns non-zero instead, because a silent fall-through in a
   function whose composition matters is a correctness trap. Every case asserts it is 0 — the run
   reached the stop PC, so it did not enter the sequence — which is a self-consistency check and
   not a comparison with the oracle. **`BUBBLE_DEATH_TRIGGER_FRAME` (3) IS pinned on the other
   side now**, and by the routine that used to be the blocker: `test_frame_death_sequence_gate`
   enters at 0x1273c — whose first instruction is the `cmpi.w #$3` itself — with the frame at 0, 3,
   4 and 12, so both sides of the bound and the bound itself are run.
5. **The `short` return values are compared as D0's LOW WORD**, which is the Alcyon C ABI's answer
   and what every caller reads. `get_pixel` is the only routine here that answers at all.
6. **Slice 3 calls `ghost_blow_body`, which is `ghost_blow` MINUS its two redraws** — and the
   original reaches those only when the candle script fires, every other exit branching over them.
   So the slice is equivalent to the original exactly while the current room has no candle left,
   which is what every slice-3 case stages (`candle_table[room][0] = -1`). **`hud_draw_counters`
   is no longer what blocks it** — it is verified above; closing it means extending the `ghost_blow`
   slice to its `rts` and staging the GEM parameter block in every case that reaches the redraws.

7. **The `^P` pause `[0x1239e, 0x123de)` is READ-VERIFIED and no case runs it.** It throws the
   console queue away and then spins on `Crawio` until a SECOND `^P` arrives — so the resuming key
   has to arrive *after* the flush, and `harness.console_keys` stages a queue rather than an
   arrival. The kit's scheduled-write model (TRAP_MODEL.md, Phase 8) does stage an arrival, but it
   is keyed to the byte the original's own compare re-reads, and this wait's compare reads
   `A_key_raw` — which the routine writes itself. The byte that really changes is the model's
   console block, inside the trap, so there is no wait SITE to name. `frame_poll_input` therefore
   ANSWERS "the key was ^P" instead of falling into `frame_poll_pause`, every case asserts that
   answer, and the ^P case is diffed at the instruction the original branches into the loop at.
   Closing it means a console model that can stage an arrival rather than a queue.

8. **`hud_bonus_bar_fill`/`_shrink`'s rectangle is built RIGHT TO LEFT, and which of the two x
   words is x1 is UNPINNED.** Both words are locals of the routine's own frame, inside the band the
   differential drops, and `vr_recfl` lends the VDI the pointer rather than copying the words — so
   the only observable is the span filled, and the VDI normalises it. Swapping the two stores was
   measured green across the whole battery on 2026-09-06 and is **equivalent, not a hole**: no case
   can separate them, and none should be written to try.

## Verified — blit (10)

The RAW blitters: the `move.l (a3)+,(a2)+` copies over the two screens, and the 32x32 tile draw
every background paint shares. `src/blit.c` has the map of which routine is which; the geometry and
the two screen pointers live in `include/blit.h`, which owns them.

Every case stages the world itself rather than taking it from a routine's output, and
`test/test_blit.py`'s module docstring says why: the model answers `Logbase` with 0x8000, so
`init_gem_and_screens`' `Logbase - 0x7d00` work buffer would land at 0x300, on the harness-poked
input block (the "Model gaps" row). So `screen_phys`/`screen_back` are poked at addresses inside
`test/abi.py`'s scratch map that keep the machine's own relationship, the six GHOST.DAT banks are
staged in the Malloc arena both as noise and as the real `../bin/GHOST.DAT`, and the object and
room tables are run BOTH as `init_globals` left them and as fuzz.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x10efe` | `clear_physical_screen` | 34 | ✅ verified | run to `rts`; 3 seeds x noise over both screens, poison, and 4 overlapping-screen layouts |
| `0x131f0` | `present_score_strip` | 52 | ✅ verified | as above — the band, not the row: a start at +0x6400 instead of +0x6540 reddens 7 cases |
| `0x13224` | `present_hud_row` | 52 | ✅ verified | as above |
| `0x13258` | `stage_to_work` | 46 | ✅ verified | as above; the source/destination swap reddens 7 |
| `0x13286` | `present_room` | 102 | ✅ verified | as above; unrolled 32 longs x 200 in the original, one loop here |
| `0x1369a` | `draw_tile_bank_screen` | 120 | ✅ verified | run to `rts`; all 7 banks over noise, banks 0..5 over the real GHOST.DAT, poison |
| `0x13712` | `draw_hud_row_tiles` | 92 | ✅ verified | run to `rts`; noise + poison + the real tiles 350..359, and the arithmetic pin that its `add.l #$6400` is 50 tiles and not the room's byte size |
| `0x1376e` | `objects_animate_and_draw` | 510 | ✅ verified | run to `rts`; all 36 shipped rooms over the real GHOST.DAT, 4 of them over noise, 96 fuzz cases in 4 shards, and the two word-edge branches (`blt` on the tile, `bne` on the countdown) the shipped tables never reach |
| `0x132ec` | `build_sprite_bank` **(slice** `[0x132ec, 0x13330)` **)** | 68 of 322 | ✅ verified | `stop_pc` at the head of the grab loop: `bank_index = 0`, `draw_tile_bank_screen`, and the GEOMETRY fields of both MFDBs — `width`/`height`/`wdwidth`/`standard`/`planes`, offsets 4..12. `MFDB_ADDR` (offset 0) is NOT in the slice: the grab loop writes it once per cell from the `c_malloc` it has just made, so it is part of the residual. **Residual:** the 60 `c_malloc` + `vro_cpyfm` grabs, and the `fd_addr` each of them stores |
| `0x13b1e` | `room_wipe_in` **(the slide,** `[0x13b62, 0x13bda)`**, has this battery's cases; the 84 bytes around it are run by `## Verified — frontend`'s `game_room_setup`)** | 120 of 204 here | ✅ verified | each of the 40 steps entered on its own with `D7 = step`, plus the whole loop twice — over noise, and over a staging area the ORACLE composed with 50 real tile draws first. Plus the two steps the game's own loop never reaches, which are what pin the present's WORD-sized `dbf` counter against the `mulu`'s longword product: step 409 (64 longs presented, not 65,600) and step -1 (the full 65,536, on a low staging of its own). **The residual is CLOSED but not by a case in this file:** the three `sound_release_voice` calls and the `sound_play` around the loop are `src/blit.c`'s `room_wipe_in` now, and the only thing that runs them is `## Verified — frontend`'s `game_room_setup` slice, the routine's only caller — five of whose cases redden when the trigger's note is changed. `room_wipe_in` has no glue and no case of its own here, which is why the Name column says where its other 84 bytes are verified |

**Not here, and it is an OWNERSHIP boundary rather than a model gap.** `save_sprite_backgrounds` @
0x1342e, `draw_sprites` @ 0x134f6 and `restore_sprite_backgrounds` @ 0x135d2 are three `vro_cpyfm`
pairs each — they were a refused oracle run until TRAP_MODEL.md Phase 12 modeled VDI opcode 109 over
Phase 11's raster, and they are now **verified in `## Verified — frontend`**, with the sprite
protocol and the binding that carries it rather than with the raw `move.l` blitters.

**`draw_room_to_stage` @ 0x13a08 HAD A ROW HERE AND NO LONGER DOES.** Its slice `[0x13a38, 0x13afa)`
— one iteration of the 5 x 10 loop — is SUBSUMED by the whole-routine row in `## Verified —
frontend`, which composes this file's `draw_room_tile_to_stage` with the per-cell `vq_mouse` and runs
the routine to `rts`. One address, one ✅ row: `test/test_status.py` refuses a second, because two
rows for one routine make the ledger's counts say more work was done than was. The tile draw's own
cases (`test_blit.py`'s 50 cells, 36 rooms, 80 fuzz, poison and the two `ext.l` wraps) are unchanged
and are what the frontend row rests on.

**`build_sprite_bank`'s slice DOES still have a row**, and the difference is worth reading: its
residual `[0x13330, 0x1342e)` is filed under an address of its own
(`build_sprite_bank_grab_cells`), so the two rows name two disjoint spans rather than one routine
twice. `room_wipe_in`'s residual is CLOSED: the sound engine is ported, so the prologue and
epilogue around its slide are `room_wipe_in` in this file now — three key-offs, one trigger and one
key-off — verified through the front end's room-setup slice, which is the routine's only caller.

**What the differential cannot see here.** Nothing in this subsystem traps, so there is no ledger to
compare — but also nothing off-image: every byte these routines write is memory the diff covers, and
the surface that would catch a regression is the image itself. The one thing outside it is the
*screen base*, which XBIOS answers and the model no-ops; a wrong `Setscreen` would leave every
routine here byte-perfect and the picture invisible (`docs/on-target-execution.md`).

**A staging decision worth reading before adding a case.** The seven banks are staged with GAPS
between them rather than packed, because 60 tiles of 512 bytes is exactly a bank: with the banks end
to end, `dat_bank[n / 60] + (n % 60) * 512` collapses to `dat_bank[0] + n * 512` for every n and the
`divs.w #$3c` split stops being observable. Measured — a reconstruction splitting at 59 tiles per
bank passed all 244 cases before the gap went in.

The gaps are also IRREGULAR (`test/test_blit.py`'s `BANK_ADDRESSES`, seven ordered addresses drawn
from one fixed seed), because a constant stride is still affine: at `BANK_BASE + index * 0x8000` a
candidate that computed a bank's address arithmetically — never loading `dat_bank[index]` out of the
image — matched every case. `test_the_staged_banks_are_separated_and_inside_the_arena` asserts both
properties, so neither can be tidied away.

**Mutations tried against this battery**, each from a deleted `.so` with `__pycache__` swept, and
each **red**:

| mutation | what caught it |
|---|---|
| `room_wipe_in_step`'s presented-longword count computed in 32 bits instead of `loop_passes(…, COUNT_MASK_WORD)` | 2 cases — `test_room_wipe_in_step_counts_the_presented_longs_in_a_word` (step 409) and `…_at_the_word_boundary_presents_the_whole_counter` (step -1). Both were WRITTEN for this: the 40 steps the game itself uses are all far inside a word and every one of them passed the 32-bit version |
| `copy_longs_descending` walking UP instead of down | 44 cases — the wipe's move onto its own overlapping span smears the other way |
| `TILES_PER_BANK` 60 → 59 | 85 cases — the `divs.w #$3c` bank split, which only the irregular gaps above make observable |
| `muls_ext_w` multiplying in 32 bits (no `ext.l`) | 3 cases — the two `test_draw_room_tile_offset_wraps_in_a_signed_word` rows and one fuzz shard |
| the object countdown's `!= 0` widened to `> 0` | 1 case — `test_objects_animate_and_draw_word_edge_branches`, which is the only thing that reaches a negative countdown |

Three earlier survivors, found on this battery's first pass and closed by the port agent, are the
reason three of those cases exist at all: a packed bank layout (closed by the gaps), a 32-bit
`muls_ext_w` (closed by the two wrap cases) and a `bgt` countdown test (closed by the word-edge
case). A mutation the suite does not catch is a coverage hole, not a licence — record it here.

## Verified — voice (2)

The digitised-voice path, which is a subsystem of its own for one reason: **the player is a second
program.** `GHOST.LOA` is an `ABSFLAG` .PRG read into the BSS as data and `jsr`ed; `GHOST.VOI` is
30,100 bytes of PCM. What is ported is the two routines of the GAME — the loader, and the call-up
that pokes the sample pointer into the LOA image at +0x1e. The LOA's own code is not, and the row
for it is in "Not reconstructed" with what closing it needs.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x13c6c` | `load_voice_player` | 126 | ✅ verified | run to `rts` on the REAL `../bin/GHOST.LOA` and `../bin/GHOST.VOI` staged under the names `init_globals` builds in the BSS, with every destination seeded. Composes the verified buffered layer (`c_fopen`/`c_fread`/`c_fclose`) and `c_malloc`; a second case reads both destinations back out of the oracle's image, including the VOI's LAST byte — the read is one byte short of the buffer, which is the program's arithmetic and the easiest thing to "fix" by accident |
| `0x13cea` | `play_voice_arm` **(slice** `[0x13cea, 0x13d26)` **)** | 60 of 66 | ✅ verified | `stop_pc` at the `jsr (a0)` into the LOA image, which is not modeled. Three VOI-buffer addresses including 0 and one that wraps a 32-bit `addi.l`, and the ANSWER — the address it would have called — compared against the oracle's A0 |

**6 cases.**

**Mutations tried against this battery**, each from a deleted `.so` with `__pycache__` swept, and
each **red**:

| mutation | what caught it |
|---|---|
| the VOI read filling the whole buffer (0x7594 rather than 0x7593) | 1 case |
| the LOA read one byte short | 1 case |
| the VOI buffer allocated one GRANULE short | 1 case |
| the poke's destination copy taken BEFORE the `+0x1e` | 3 cases |
| the LOA entered at the pointer slot rather than at its text | 3 cases, and `test_play_voice_arm`'s A0 comparison by name |

**TWO ARE EQUIVALENT, and both are properties of things outside this file:**

* **the VOI buffer allocated one BYTE short** (`c_malloc(0x7593)`). `c_malloc` rounds a request up
  to six-byte granules, and 0x7593 and 0x7594 round to the same 5,030 — so the block, its header
  and the arena's new top are identical. One GRANULE short is red, which is what says the size is
  pinned at all.
* **the two mode strings collapsed to one.** `A_mode_ghost_loa` and `A_mode_ghost_voi` are two
  copies of `"br"` at different addresses that the linker never merged; nothing records which was
  read, so no case can separate them.

### Residuals — what these rows do NOT pin

1. **The LOA player itself is not run, and `play_voice` stops at the `jsr` into it.** See "Not
   reconstructed" for the model gap (no MFP timer, no interrupt, and a busy-wait with no site to
   name).
2. **A failed open is not tested by the original at all** — `load_voice_player` has no retry and
   never looks at what `c_fopen` answered, so a missing file would leave the read working on
   garbage. Under the model an unstaged name is a refused run rather than a negative handle, so no
   case reaches it; transcribed as the straight line it is.

## Verified — sound (12)

The whole engine between 0x142bc and 0x149b4: a five-call trigger API, the 200 Hz Timer C handler
that runs three voice records' worth of envelopes and LFOs, and the `trap #9` gate ordinary code
reaches the chip through. `../notes/sound_engine.md` is the design doc, `include/sound.h` the frozen
record layout. **There is no music and no sequencer** — 11 fixed effects and 36 per-room tones, each
one one-shot voice record.

**The chip is off-image, so most of what this subsystem does is invisible to the byte diff.** Every
row below therefore rests on two more surfaces than an ordinary one: the kit's ordered direct-PSG
ledger, which carries reads as well as writes (TRAP_MODEL.md, Phase 6), and — for the installer —
the hardware WRITE ledger (Phase 10). A reconstruction that made no chip access at all is
byte-for-byte identical to one that makes every access the original makes.

**AND ON TARGET, ONE ROW OF THIS TABLE IS NOT WHAT RUNS.** `timer_c_sound_isr` @ 0x1459a stays the
reference and stays verified here, but `atari/build.sh` links `src/asm/sound_tick.S` beside it and
`bg_timer_c_entry` calls THAT — a hand-written m68k routine with the same C signature, 792 of whose
856 bytes are the original's own 0x145be..0x148d6 byte for byte (wave 5b, "Performance"). It is the
only place in this program where the .PRG runs something other than a verified core, and four
things hold it: `test/test_sound_asm.py` compares it against this C over every case `test_sound.py`
stages, image and PSG ledger both; the same file compares its 792 bytes against the .PRG's;
`test_constants.py::test_asm_twin_equates_match_the_headers` refuses a restated `include/sound.h`
constant that has drifted; and `atari/build.sh` asks the linked binary which of the two handlers
the 200 Hz vector reaches, and the object about to be linked whether its 792 bytes are still the
original's.

**The digitised-voice path is NOT this subsystem's**, and never was: `load_voice_player` @ 0x13c6c
and `play_voice` @ 0x13cea have a section of their own (`## Verified — voice`) because what they
load is a SECOND PROGRAM — `GHOST.LOA`, `jsr`ed inside the BSS — with nothing to do with the PSG
engine here. Both are verified; the LOA's own code is the row left in "Not reconstructed".

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x142bc` | `sound_play` | 520 | ✅ verified | all 47 shipped definitions x 3 voices; notes 0..127 plus the negatives and the fold's two boundaries; the priority refusal; the zero-duration "just stop it"; tone-off/noise-off; the volume argument and the no-envelope path; the DEAD voice allocator driven with synthetic voice args (free-scan over all 8 busy subsets, eviction over all 125 priority triples); 8 x 10 fuzz cases (chunk-SEEDED, so each shard draws its own) over synthetic definitions and random records. Accumulator zeroing pinned under the poison pass |
| `0x144c4` | `sound_stop_voice` | 76 | ✅ verified | the range check at -1/0/1/2/3 and both word extremes, over random records; the `psg_gate(8+v, 0)` write and its read-back compared in the PSG ledger |
| `0x14510` | `sound_release_voice` | 78 | ✅ verified | live and idle voices x the range check; duration := 1 and gate := -1 are the whole effect, and `test_isr_key_off_*` is what shows the handler then keys off on the next tick |
| `0x1455e` | `sound_voice_priority` | 24 | ✅ verified | voices 0..2, and 371/372/400/743 — the indices that make `muls.w`+`adda.w`'s sign-extended low word reach BELOW the record array, which is what separates this routine's arithmetic from a 32-bit add. Return compared against the oracle's D0 low word |
| `0x14576` | `sound_stop_all` | 36 | ✅ verified | four random three-record states; composes the verified `sound_stop_voice` |
| `0x1459a` | `timer_c_sound_isr` | 848 | ✅ verified | entered directly (it never `rte`s — it pushes TOS's saved `$114` and `rts`es, so the case stages that vector) and, for the multi-tick cases, through an 18-byte `dbf` stub that calls it N times in ONE oracle run. Covers: the idle skip and the conterm restore over all 8 busy subsets; the ADSR's five phases x four step signs; the triangle LFO folding at both limits with and without the onset delay; the three-segment pitch sweep both directions per segment; the pitch LFO's carry-driven step reload; the noise machine and its `cmp.b #$1f` on a word; the `muls.w` alias above a full-scale accumulator; the unbounded volume-scale index; the byte-wide phase compare; key-off over 18 phase/step combinations; a non-negative gate never counting down; the pointers being read out of the ISR state block (record base relocated); 8 x 10 chunk-seeded random-record fuzz cases at 1..8 ticks, and all 47 real definitions at 12 ticks (those PARTITIONED eight ways, `abi.shard`) |
| `0x148ea` | `install_sound_vectors` | 50 | ✅ verified | three (saved `$114`, conterm) pairs over a seeded state block. The two vectors and the four saved fields are image bytes; **`$fffffa17 := $40` is not**, and the hardware WRITE ledger is the only surface that sees it |
| `0x1491c` | `remove_sound_vectors` | 22 | ✅ verified | two saved states; the same ledger for `$fffffa17 := $48`. Pins that the `trap #9` vector is deliberately NOT restored |
| `0x14940` | `psg_gate` | 16 | ✅ verified | the user-mode stub, entered with its three argument words on the stack; the oracle takes the real `trap #9` through the `$a4` vector the case stages (which is the longword `install_sound_vectors` itself writes) |
| `0x14950` | `trap9_psg_handler` | 50 | ✅ verified | reached through `psg_gate` above — a direct entry is not runnable, because it ends in `rte` and the harness's frame is a `jsr`'s. All 16 registers written and read back; register 7's read-modify-write over 25 (value, mask) pairs; the negative-value pure read; the four-bit select mask; 8 x 12 chunk-seeded fuzz cases over the whole argument space with a fully declared chip. Return compared as a whole longword |
| `0x14982` | `sound_start` | 26 | ✅ verified | three caller register files. `Supexec` runs the installer nested in the oracle; the `xbios_trap` trampoline's three save slots are part of the diff, which is why a1/a2 are arguments |
| `0x1499c` | `sound_stop` | 26 | ✅ verified | two caller register files; the trap #9 vector has to be staged because `sound_stop_all` runs BEFORE the installer would have written it |

**Mutations tried against this battery**, each from a deleted `.so` with `__pycache__` swept, and
each **red**:

| mutation | what caught it |
|---|---|
| the pitch LFO's carry test inverted (`long_add_extend` → its negation) | 18 cases — `test_isr_pitch_lfo_reloads_its_step_on_a_carry` and the record fuzz. The carry is only reachable with the huge steps that case uses, which is why it exists |
| `PSG_REG_SELECT_MASK` 0x0f → 0x1f | 9 cases — `test_psg_gate_masks_the_register_number_to_four_bits`, through the PSG ledger's ordered select stream |
| the volume phase compared as a WORD instead of a byte | 10 cases — `test_isr_selects_the_phase_with_a_byte_compare`, whose high-byte phases `sound_play` really can copy out of a definition |
| the noise clamp's `cmp.b` widened to the word it tests | 10 cases — `test_isr_noise_machine_and_its_byte_wide_clamp`, at the 0x80/0x90 rows that slip past a byte compare |
| `sound_start` skipping its `trap_save_registers` | 1 case — `test_sound_start`, on the three trampoline save slots |

Two earlier survivors, found on this battery's first pass and closed by the port agent, are why two
of those cases exist: a word-wide phase compare (closed by the byte-compare case) and a widened
noise clamp (closed by the 0x80/0x90 rows). A mutation the suite does not catch is a coverage hole,
not a licence — record it here.

### Residuals — what these rows do NOT pin

Seven. Six are off-image effects the differential has no surface for — none a gap in the C, each a
claim that would need a run on real hardware or a new kit surface to check — and the seventh is a
divergence in the C that a surface CAN see and no case reaches.

1. **The handler's IPL drop.** `ori.w #$500,sr` / `andi.w #$fdff,sr` takes the entry IPL of 6 to
   exactly 5, so other MFP channels — the keyboard ACIA in particular — can nest inside the tick.
   That is a status-register effect with no image consequence, and the reconstruction does not
   express it at all. It is also what the installer's automatic-EOI mode exists for, so the two
   residuals are one fact.
   **THE SURFACE IS THE ON-TARGET SMOKE RUN** (`docs/on-target-execution.md`, "The observable
   surfaces"): an ISR that did not drop its IPL locks out the keyboard, so a .PRG that boots to the
   title and accepts a keypress with sound running is what would catch it. Nothing off target can,
   and this project has no .PRG yet — so the residual stands unpinned until it does.
2. **The chain, rather than an `rte`.** The handler ends by pushing TOS's saved `$114` vector and
   `rts`ing, so TOS's own Timer C work still runs. The cases stage that vector with the harness's
   sentinel (or, for a multi-tick run, a bare `rts`), which proves the handler jumps THROUGH it —
   but TOS's handler is not in the image and is never run. **The surface is the same on-target smoke
   run**: a chain that did not reach TOS stops the system clock and the keyboard repeat, which a
   booted .PRG shows and a byte differential cannot.
3. **`trap9_psg_handler` parks the select latch on register 11** (`move.b #$b,(a0)`) so nothing is
   left pointing at the I/O ports. **The surface is a THIRD PSG event kind in the kit's ledger** — a
   bare *select* with no access — which `psg.h` does not have: its calls select and access together,
   so neither side can record one and the two agree by construction. Adding `psg_port_select(reg)`
   and a `SELECT` entry to the ordered ledger is the whole change, and it is a kit change; until it
   lands the final latch position is unverified on both sides rather than verified on neither.
4. **`psg_gate`'s `mask` argument is stack garbage at four of its six call sites**, which push only
   two argument words. The reconstruction passes a definite 0. It is never read at those sites (the
   handler consults `mask` only for register 7, and none of the four selects register 7), so this is
   sound rather than merely convenient — but it is a claim about the handler, not something a case
   observes.
5. **`sound_start`/`sound_stop` take the caller's a1/a2 as arguments** (`docs/agent-playbook.md` §5,
   "a parameter"). The `xbios_trap` trampoline files whatever the register file holds and nothing in
   these two routines computes it; the cases take the values FROM the oracle's own input registers.
   Closing it means porting the callers.
6. **The `short` return values are compared as D0's LOW WORD.** That is the Alcyon C ABI's answer
   and what every caller reads; D0's high half is whatever the routine's own arithmetic left there.
   `psg_gate` is the exception and is compared whole, because it answers with a zero-extended byte.
7. **A voice record's FIELD DISPLACEMENT no longer wraps in 32 bits**, which the 68000's `d16(a0)`
   does — wave 3a's accessors take the record base as a host pointer and add the field to it (see
   "Performance", wave 3a, for why and what it bought). Every ADDRESS the file computes is still
   `addr_add` in `uint32_t`, so this is visible only for a base within 0x8a of the top of the map,
   and only `timer_c_sound_isr`'s descending cursor can produce one — from a `SND_ISR_TOP_VOICE`
   below 0x1a4, which `install_sound_vectors` never writes. **The surface exists and is `make
   guarded`**: the pointer form's `image + 0xffffff84 + 0x8a` lands inside its reserve and faults
   where the address form wraps back into the image, so a case seeding such a base tells the two
   apart. No case seeds one, so this is UNPINNED rather than unpinnable — unlike 1-6, closing it
   needs a test and not a new surface.

## Verified — clib (58)

The Alcyon/DRI C runtime linked into the program, `src/clib.c` / `include/clib.h` / `test/test_clib.py`.
Ported in dependency order: the string and 32-bit arithmetic leaves, the fd-mode side table, the
free-list allocator, the low-level file layer, the whole software floating-point package, the
buffered `FILE` layer on top of it, the console reader and writer, and the printf engine — and with
them the two OS trap trampolines, which are verified through the wrappers that call them.

**The whole C library is now ported bar five wrappers**, each of which needs one GEMDOS call the kit
does not model; they are the only rows left in "Not ported" below.

**FOUR SHAPES OF EVIDENCE**, because most of this subsystem answers somewhere the byte diff cannot
see. A routine whose answer is D0 is checked against the oracle's D0 as well as by the image diff.
`c_ldiv` and `c_lmul` answer through their CALLER'S argument slots, which lie in the band the
differential drops as stack — those run from a poked stub (`test/abi.py`'s `c_call_pokes`) that
files the answers at `abi.RESULT`. And the trap trampolines' only reproducible effect is the three
save slots, so every case that traps stages noise over them: the `RET_*` value a wrapper leaves says
WHICH trap site ran, which is what tells a binary `c_read` (one Fread) from a text one (several).

**A FOURTH SHAPE OF EVIDENCE ARRIVED WITH THE CONSOLE: the kit's ordered OS-event ledger**
(TRAP_MODEL.md, Phase 13). `c_conout_write`, `c_write`'s CON: arm, `c_conin`'s echoes and everything
`c_printf` puts on the screen move no image memory at all — a reconstruction that printed nothing
would be byte-identical to one that got them right. `harness.differential` compares that ledger on
every run without a case asking for it, which is what makes those five routines verifiable rather
than merely read.

**The floating-point package is byte-compared, never float-compared.** It keeps a 32-bit mantissa
where an IEEE double has 53, so "the same number in Python" and "the same eight bytes" are different
questions and only the second is asked. Half the fuzz's operands are raw 64-bit patterns rather than
doubles Python would name — the package has no special case for an infinity, a NaN or a denormal (a
zero EXPONENT is the only value it tests for), so those are ordinary inputs to it.

**601 cases.** The fuzzes are CHUNK-SEEDED rather than chunk-partitioned (`test/abi.py`'s `shard`
docstring tells the two apart), so each is `CHUNKS` x its own per-chunk count: the ldiv/lmul fuzz is
8 x 24 pairs through each routine, the allocator fuzz 8 x 16 arenas, the arithmetic fuzz 8 x 24
operand pairs, the conversion fuzz 8 x 24 patterns through each of three routines, and the printf
fuzz 8 x 24 random formats. `make guarded` sweeps the same suite clean — the allocator and the
buffered layer both index the image with cursors they compute, so that is their surface.

**FOUR OF THE 567 ARE CANDIDATE-ONLY, and they are the file's out-of-bounds guards.** The original
overruns its own frame in three places — `c_fmt_integer`'s 20-word digit array for a base below 8,
`c_fcvt`'s digit buffer for a count `c_fmt_float` derives from a format string's precision, and the
same buffer for a NEGATIVE count (`c_fmt_getnum` accumulates in 16 bits and wraps, so `%.65534f`
arrives as -2). There is nothing comparable to diff against: the oracle would smash its stack and
the candidate would write outside a C array, which in the harness's own process is an xdist worker
vanishing rather than a red case. So the reconstruction REFUSES each, and those four cases drive the
glue directly and assert the refusal tally (`g_os_refusal_count`) instead of an image.

**WHAT THE PRINTF ENGINE IMPLEMENTS**, read off `c_doprnt`'s own dispatch chain and fuzzed over that
and no more: `%[-][0][width][.precision][l]` then one of **d u o x c s e f g**. There is no `%%` (a
second `%` reaches the "unknown conversion" arm and is emitted as itself, which is the same output by
a different route), no `+`/space flag, no `*` width, no `h`, and no `p`/`n`/`i`; `%g` is `%e`, since
`c_fmt_float` tests for `'f'` and takes the exponent form for everything else. **The game itself uses
none of them**: its one `c_printf` call (`main` @ 0x100dc) passes the "Please reboot in LOW REZ"
message, which carries no conversions at all — so every other format in the battery is synthetic, and
that is a statement about coverage rather than about play.

**`Malloc` IS THE KIT'S MODEL ON BOTH SIDES.** `gemdos_malloc` / `gemdos_malloc_or_fail` forward to
`os_malloc` (`tools/recreate_kit/src/os_heap.c`) — the same bump arena, over the same
`heap_base`/`heap_limit` window, that `oracle/shim.c` services the GEMDOS trap from. So the two bump
pointers are comparable after every run (`harness._vet_heap_pointers_agree`), which is what catches an
allocation the reconstruction never makes: the first block of an untouched arena IS the base, so a
wrapper that answered `OS_HEAP_BASE` without allocating would store the byte-identical longword. The
`Malloc(-1)` query — GEMDOS's "how big is the largest free block?", which answers a SIZE and moves
nothing — is the model's too and is now a case (`test_gemdos_malloc[0xffffffff]`). This battery used
to carry a private copy of the arena's two lines in `src/clib.c`, reset per run from `test/abi.py`;
both are gone, and `harness.arm_candidate` rewinds the kit's pointer instead.

**Mutations tried against this battery**, each from a deleted `.so` with `__pycache__` swept. The
first sweep (granule size, the two rounding increments, the mantissa shift, the binary-mode bit,
fp_add's shift bound, the CR constant, c_free's wrap test, the refill's return address, fp_mul's
sticky bit, fp_div's step count, c_ldiv's sign tally, c_getfdmode's overrun) reported 12/12 killed;
re-running the rounding-increment one under the errno/zero-divisor work below found that it does not
in fact die, so eleven of those twelve stand and the twelfth is recorded as a hole. The second sweep:

| mutation | result |
|---|---|
| `c_ldiv` loses its zero-divisor branch | **red** — `test_c_ldiv_by_zero_stores_zero_over_both_slots` fails on `(0, 0)` and does not terminate on `(0, 5)`, which is the defect the branch closes: without it the C is not merely wrong but non-terminating |
| `c_close` drops its `errno` store | **red** (2 cases) — only since `fd_table_poke` began seeding `A_c_errno` with NOISE; before that the store wrote a 0 over a 0 and the mutation survived the whole suite |
| `c_read` drops its closing `errno := 0` | **red** (3 cases) — the same noise seeding |
| ~~`fp_div`'s `long_sub_extend` borrow made inclusive (`<=`)~~ | **red** (3 cases) — the statement it mutated is gone: wave 3b's `fp_div` subtracts a 64-bit pair, so the borrow is the `subx.l` GCC emits. The equivalent point is `remainder -= divisor` |
| `fp_float_to_double`'s `and.l #$8fffffff` widened to `#$9fffffff` (three sign-fill bits → two) | **red** (11 cases) |
| **`fp_pack_float` rounding with the DOUBLE's increment (0x100 instead of 0x200)** | **SURVIVES — and cannot be caught.** See "a hole with a proof" below |
| `c_read` drops its ENTRY `errno := 0` | **SURVIVES.** See below |
| `fp_div`'s `divisor <= remainder` made exclusive (`<`) | **SURVIVES — an equivalent mutant, not a hole.** The suite REACHES the equality arm (`test_fp_arithmetic_edges` divides 1.0 by 1.0) and the raw quotient really differs (0x80000000 against 0x7fffffff); `fp_pack_double`'s shared normalise-and-round tail maps both to the same eight bytes. "Performance", wave 3b, carries the 68,000-pair model that says so |

**A third sweep, re-run when the allocator moved onto `os_malloc`** — the same three questions the
private arena used to answer, asked of the model:

| mutation | result |
|---|---|
| `MALLOC_GRANULE` 6 → 8 | **red** (27 cases) — the granule is the header's own size, so every c_malloc/c_free/c_morecore case walks a differently-spaced list |
| `c_morecore`'s round-up loses its `- 1` (`+ QUANTUM` instead of `+ QUANTUM - 1`) | **red** (2 cases) — `test_c_morecore[1048]` and `[2096]`, the EXACT multiples of the 0x418-granule quantum, where an off-by-one round-up asks GEMDOS for a whole extra quantum |
| `gemdos_malloc` answers `Malloc(-1)` with the arena base instead of forwarding the query | **red** (1 case) — only since the query became a case; the oracle answers the free window (0x60000) and the wrapper answered an address |

**A fourth sweep, over the buffered layer, the console and the printf engine** — eighteen mutants,
each from a deleted `.so` with `__pycache__` swept, against a green `test_clib.py`:

| mutation | result |
|---|---|
| the FILE record's `bufsiz` offset 18 → 16 | **red** (22 cases) |
| `CRLF_BYTES` 2 → 1 (a newline goes out as one byte) | **red** (6) |
| `FILE_LINEBUF` moved from 0x100 to 0x200 | **red** (7) |
| `FMT_NO_PRECISION` moved from 0x100 to 0x200 | **red** (3) |
| `c_write` charges a newline two bytes instead of one | **red** (5) |
| `c_fcvt` rounds with 4 instead of 5 | **red** (8) |
| `c_filbuf` always asks for a whole buffer, never one byte | **red** (2) |
| `c_doprnt`'s right-justify off by one (`width` for `width - 1`) | **red** (13) |
| `c_fread` stops threading the A1 that `c_getfdmode` left behind | **red** (1) |
| `c_conout_write` stops prefixing a newline with a CR | **red** (4) |
| `c_fmt_float` sends `%g` down the `%f` path | **red** (17) |
| `c_putc` flushes one byte early (`<= 0` for `< 0`) | **red** (3) |
| `FMT_HEX_STEP_MASK` widened by a bit | **red** (6) — *see below* |
| `FMT_OCTAL_STEP_MASK` widened by a bit | **red** (8) |
| `unbuffered_char_slot` drops `divs.w`'s remainder | **red** (1) — *see below* |
| the sign-fill of `shift_right_arithmetic` replaced by zeros | **SURVIVES**, with a proof |
| `CLIB_SCRATCH_EXPONENT_ARGS` overlapped onto `CLIB_SCRATCH_FCVT_DOUBLE` | **SURVIVES**, with a proof |

**Two of them found real holes and closed them, which is the point of the sweep.**

* The **step masks** survived their first run, and the reason was the C rather than the battery: the
  octal and hex digit loops step the value with `asr.l`, and the mask that follows exists to clear
  the sign fill. Written with an unsigned `>>` the fill was never there, so the mask could be widened
  by a bit and nothing changed. `shift_right_arithmetic` spells the fill out — C's `>>` on a negative
  signed value is implementation-defined — and both masks are load-bearing now. What still cannot be
  caught is the PAIR: fill-then-mask and no-fill-then-no-mask compute the same function, so dropping
  the fill alone survives. The form that is there is the one that reads as the `asr.l` it transcribes.
* **`unbuffered_char_slot`'s remainder** survived until a case was written for it. `divs.w` leaves the
  remainder in D0's HIGH word and the `adda.l` that follows adds the whole longword, so a FILE record
  two bytes off the 20-byte stride puts its one-byte buffer 0x20000 further up the image. No caller
  in the program passes such a pointer, so `test_c_filbuf_off_stride_record_lands_the_divs_w_
  remainder_in_the_high_word` fabricates one — a legal argument to the routine, not a fabricated
  record — and the mutant now reddens.
* **The scratch overlap cannot be caught, and the reason is the residual above.** Both spans live in
  the band the differential drops, and in the one path that uses both — `%e` — `c_fcvt` has finished
  with its working double before the exponent argument list is written. So the overlap changes
  nothing a case could see, on either side.

**A fifth sweep, over what the pre-commit review changed** — the same protocol, run against
`test_clib.py` **and** `test_constants.py`, because three of these are header constants a battery
mirrors rather than exercises:

| mutation | result |
|---|---|
| `note_fd_modes_consulted` stops recording the A1 `c_getfdmode` leaves | **red** (31) |
| `c_fmt_integer`'s digit-array bound doubled | **red** (1) — the candidate-only guard case |
| `C_FCVT_DIGITS_OVERHEAD` 3 → 0 (the bytes c_fcvt writes past `ndigits`) | **red** (2) |
| `CLIB_SCRATCH_BASE` dropped below `STACK_TOP - STACK_SCRATCH` | **red** (1) |
| `c_fmt_float` stops refusing a NEGATIVE precision | **red** (1) |
| `c_fcvt` stops refusing a negative digit count | **red** (1) |
| `C_EXPONENT_ARGS_OFF_VALUE` 4 → 2 | **red** (30) |
| `file_take_through_cursor` stops advancing the cursor | **red** (11) |

Two of those started as survivors and named their own case, which is the sweep earning its keep: the
`c_fcvt` negative-count guard had no caller that could reach it (`c_fmt_float` refuses first), and
`c_fmt_integer`'s bound had none either. Both are candidate-only cases now. A third — the header
constants — survived only until the sweep was widened to run `test_constants.py` beside the battery;
a mirror is a real pin and a sweep that omits the file holding it reports a phantom survivor.

**THE SCRATCH MOVED because of the review, and the pin moved with it.** `CLIB_SCRATCH_BASE` was
`STACK_TOP - 0x500`, which is inside the dropped band but BELOW `STACK_TOP - STACK_SCRATCH` — the
address at which the kit stops reading a write as a call frame's own and starts reading it as
program output (`tools/recreate_kit/oracle/emu.py`). The battery's pin asserted the dropped band and
not that, so nothing said so. The base is now exactly `STACK_TOP - STACK_SCRATCH`, the assertion is
there, and the three spans are ordered with the vfprintf BUFFER last: it is the one with no bound on
what is written into it, so it overruns into unused band rather than onto `c_fcvt`'s working double —
which is the direction the original overruns too.

**A hole with a proof.** `fp_pack_float`'s `add.l #$200,d2` is transcribed correctly, but no case can
tell it from the double's `#$100`. The round only runs when the guard bit 0x100 is set, and the tail
then stores `mantissa >> 9`. Write `m = 512q + r`: the guard being set means `r >= 256`, so
`(m + 0x100) >> 9 = q + 1 = (m + 0x200) >> 9` for every such m, and the two increments carry out of
bit 31 on exactly the same inputs (bit 8 set puts m either in the range where both carry or the range
where neither does), so the exponent and the re-round follow identically. The differing bit is shifted
out before it is stored. It is unpinnable through this routine's bytes, not merely unpinned — and
`fp_pack_float` has no caller in the program, so there is no composition that would expose it either.

**And a second one, for the same reason: no surface.** `c_read` opens `wr16(A_c_errno, 0)`, and every
path out of it writes `A_c_errno` again before returning — the count after the first Fread, then 0 at
the exit, on the binary path and the text path alike. The entry store is therefore invisible in the
final image, which is all the differential compares; the write LEDGER would see it, but the harness
compares final memory rather than write sequences. Transcribed and left honestly unpinned.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x10116` | `crt0_setup_args` | 2 | ✅ verified | a bare `rts` — the Alcyon runtime's argv hook, stubbed out at link time. Run to `rts` with the command tail the crt0 pushes staged, and the ORACLE'S WRITE-SET asserted EMPTY: the byte diff alone would be vacuous (two programs that do nothing agree), so what carries the case is that the original writes no memory. Filed here rather than under `init` because it is the C library's hook and not the game's boot chain |
| `0x1683e` | `c_strlen` | 41 | ✅ verified | 5 strings incl. empty and 199 bytes; D0 compared as a longword |
| `0x167fc` | `c_strcmp` | 66 | ✅ verified | 10 pairs incl. three high-bit ones — the bytes are SIGN-extended, so an unsigned port returns the opposite sign |
| `0x158fe` | `c_ldiv` | 114 | ✅ verified | stub-driven; 10 edge pairs with attribution poison + 8 x 24 fuzz pairs. Both answers land in the caller's slots. The ZERO DIVISOR is three more cases, run with the machine's zero-divide vector declared (see the residual), plus one that pins the oracle refusing the run without it |
| `0x15970` | `c_lmul` | 108 | ✅ verified | stub-driven; 11 edge pairs with poison + 8 x 24 fuzz pairs. It eats four of its own eight argument bytes |
| `0x15cae` | `c_setfdmode` | 76 | ✅ verified | 5 tables incl. a FULL one, where the record is silently dropped |
| `0x15cfa` | `c_clearfdmode` | 60 | ✅ verified | 5 handles over a table holding one twice — both copies are cleared |
| `0x15d36` | `c_getfdmode` | 46 | ✅ verified | 4 handles, one of them ABSENT: the miss reads past the table onto `A_c_malloc_freelist`, staged with random bytes so a plausible 0 would fail |
| `0x15e58` | `gemdos_trap` | 28 | ✅ verified | through every wrapper below: the three save slots are staged with noise and diffed, and the `RET_*` says which site ran |
| `0x15e3c` | `xbios_trap` | 28 | ✅ verified | entered directly with XBIOS Physbase (0x02); D0 = `OS_SCREEN_BASE` and the slots hold the harness's own sentinel |
| `0x15c82` | `gemdos_malloc` | 22 | ✅ verified | 6 sizes (D0 = the modeled arena base) plus the `Malloc(-1)` query, which answers the free window and allocates nothing; and the save slots |
| `0x15c98` | `gemdos_mfree` | 22 | ✅ verified | 3 blocks; Mfree always succeeds and frees nothing |
| `0x167c8` | `gemdos_malloc_or_fail` | 52 | ✅ verified | 4 sizes; the 0 -> -1 arm is unreachable under the model (see the residual) |
| `0x15af2` | `c_morecore` | 98 | ✅ verified | 5 granule counts across the quantum boundary; the c_free that links the new block in is part of the diff |
| `0x15b54` | `c_malloc` | 170 | ✅ verified | an EMPTY list (self-init + morecore), 7 sizes over a six-block arena, and roughly half of the 8 x 16 fuzz arenas (the arm is a coin, and the case asserts both arms ran) |
| `0x15bfe` | `c_free` | 130 | ✅ verified | 6 (victim, roving-pointer) combinations + the other half of the 8 x 16 fuzz arenas — both coalescing arms and the list's wrap. Every fuzz arena now carries at least one ALLOCATED block, so the free arm can no longer skip itself |
| `0x15d64` | `c_open` | 214 | ✅ verified | 4 modes on a staged file + the three pseudo-devices, which never reach GEMDOS, + the TRUNCATING arm's only runnable path (its delete failing). Its other three calls are read-verified — see the residual below |
| `0x14c7a` | `c_creat` | 154 | ✅ verified | 2 modes (Fcreate truncates the staged file) + the CON: path, which tail-calls c_open |
| `0x14c3c` | `c_close` | 62 | ✅ verified | 2 real handles and 2 pseudo-handles; the signed word compare against 0x8300 is what separates them |
| `0x1667c` | `c_read` | 332 | ✅ verified | 5 binary lengths + 5 text ones. The text pass drops CRs and TOPS THE BUFFER UP, so its later Freads leave a different `RET_*` and a different A2 |
| `0x15394` | `fp_pack_double` | 106 | ✅ verified | entered DIRECTLY as the tail it is (A6 names the frame it unwinds); 9 (mantissa, exponent) pairs across the normalise, round-to-even and carry-out arms, plus every add/sub/mul/div case, which all end here |
| `0x15132` | `fp_pack_float` | 90 | ✅ verified | 7 pairs, entered at the `link a6,#$0` stub. NOTHING IN THE PROGRAM CALLS IT (see the residual) |
| `0x15552` | `fp_long_to_double` | 50 | ✅ verified | 13 longwords incl. both extremes + 8 x 24 random patterns |
| `0x154d0` | `fp_float_to_double` | 58 | ✅ verified | 8 singles + 8 x 24 random patterns; the 64-bit `asr/roxr` triple is the shape a port gets wrong |
| `0x1550a` | `fp_double_to_long` | 70 | ✅ verified | 20 doubles + 8 x 24 random patterns; the shift count is taken mod 64 as the 68000 takes it |
| `0x154b0` | `fp_acc_load_long` | 16 | ✅ verified | 7 longwords in D0, widened in place at `A_fp_acc` |
| `0x154c0` | `fp_acc_to_long` | 16 | ✅ verified | 20 accumulator values; D0 compared as a longword |
| `0x152fa` | `fp_add` | 154 | ✅ verified | 11 edge pairs + its share of the 8 x 24 chunk-seeded fuzz pairs; shares its body and its exit with fp_sub |
| `0x152e0` | `fp_sub` | 26 | ✅ verified | same battery: it flips the SOURCE's sign word in memory and the shared body flips it back |
| `0x1524e` | `fp_mul` | 144 | ✅ verified | 11 edge pairs + its share of the 8 x 24 chunk-seeded fuzz pairs; three 16x16 partials and a sticky bit for the fourth |
| `0x151d0` | `fp_div` | 126 | ✅ verified | 11 edge pairs + its share of the 8 x 24 chunk-seeded fuzz pairs; 32 restoring-division steps over a 64-bit remainder |
| `0x1518c` | `fp_cmp` **(entered at** `0x15190` **)** | 66 | ✅ verified | 9 pairs; its ONLY output is `A_fp_ccr`, the whole SR — see the residual on its high byte. The routine opens with TWO `link a6,#$0`, and `fp_op_table[4]` points at the SECOND (0x15190) — so that is where the case enters, while the row is filed at the address `../names.txt` names |
| `0x153fe` | `fp_dispatch` | 178 | ✅ verified | 5 double-source opcodes + 6 widening ones, plus the whole `Random() -> 5..15` chain the front end computes, run as five C calls from one stub |
| `0x14d72` | `c_fclose` | 82 | ✅ verified | 4 flag sets incl. a free slot and a GEMDOS-allocated buffer; whether the flush leaves A1 elsewhere is derived from the record BEFORE it runs |
| `0x14dc4` | `c_fflush` | 188 | ✅ verified | a free slot, 5 dirty buffers (binary, text, append, read-write, empty) and 4 read ones — where the GEMDOS cursor seeks BACK over what was never handed out |
| `0x14e80` | `c_filbuf` | 304 | ✅ verified | 5 stream shapes over a staged file, 3 refusals (EOF, ERR, write-only), end of file, and one OFF-STRIDE record — the only way to see `divs.w`'s remainder land in the high word |
| `0x14fb0` | `c_flsbuf` | 318 | ✅ verified | 8 (byte, flags, buffer state) rows: the line-buffered arm that returns WITHOUT flushing, the newline and full-buffer arms that do, unbuffered, fully buffered, and both error arms |
| `0x150ee` | `c_putc` | 68 | ✅ verified | 3 counts incl. 0, where the pre-decrement is what sends it to c_flsbuf with -1 already stored |
| `0x15588` | `c_fcvt` | 346 | ✅ verified | 16 doubles x 3 digit counts, compared as BYTES; the scaling loop, the ×10-by-shift-and-add digit loop, the round-half-up carry and the leading-zero shift |
| `0x156e2` | `c_fopen` | 406 | ✅ verified | 8 mode strings over r/w/a/+/b, 5 it refuses (including `"rb"`, which does not parse — the 'b' is a PREFIX), the slot hint and an out-of-range hint |
| `0x15878` | `c_fread` | 134 | ✅ verified | 6 (size, items, buffered) rows: out of the buffer, through c_filbuf, past end of file where the answer is a division, and a partial record the division drops |
| `0x159dc` | `c_lseek` | 278 | ✅ verified | 6 (offset, whence) rows incl. one past the staged length into the reserved capacity, and 3 pseudo-handles answered -1 without a trap |
| `0x1620c` | `c_doprnt` | 650 | ✅ verified | 45 formats over every conversion and flag the engine has + 8 x 24 fuzzed ones + the two extreme exponents + 4 trailing-`%` cases, which dispatch on the CALLER'S D7 |
| `0x15e74` | `c_fmt_integer` | 364 | ✅ verified | 12 (conversion, long, value) rows across all four bases and both sign rules, plus 5 that reach the arm where the BASE is the caller's D7 — which `c_doprnt` never takes |
| `0x15fe0` | `c_fmt_float` | 472 | ✅ verified | 3 conversions x 8 (precision, value) rows, incl. the 0x100 "no precision" sentinel and both zeroes; `%g` proves it takes the `%e` path |
| `0x161b8` | `c_fmt_getnum` | 84 | ✅ verified | 10 strings incl. an empty one, a 16-bit wrap and a high-bit byte, which the SIGN-extended compare puts below '0' |
| `0x164c2` | `c_printf` | 22 | ✅ verified | 2 formats onto a LINE-BUFFERED CON: `c_stdout`, so the whole chain down to the console ledger runs |
| `0x164d8` | `c_sprintf` | 22 | ✅ verified | one format, entered so that `argp` is its own second argument slot — the list c_doprnt walks |
| `0x16496` | `c_vfprintf` | 44 | ✅ verified | 3 formats, incl. the game's own message; the 256-byte buffer is stack on both sides, so what is compared is what c_fputs pushes out of it |
| `0x164ee` | `c_fputs` | 42 | ✅ verified | 4 strings incl. one that overflows the stream's buffer mid-string and flushes through c_write |
| `0x16518` | `c_conin` | 356 | ✅ verified | 8 typed lines (RETURN, BACKSPACE with and without anything to rub out, the end-of-file character, a typed LINE FEED) + 4 already-gathered lines + 3 refused handles. Every echo is a console-ledger entry with its own RET_* |
| `0x16b5e` | `c_conout_write` | 74 | ✅ verified | 7 spans incl. an empty one, a partial one and every printable byte; the ledger is the whole surface, and the zero-length case asserts an EMPTY ledger so "never ran" cannot pass as "wrote nothing" |
| `0x16c04` | `c_write` | 394 | ✅ verified | 6 binary spans, 7 text ones over every newline position, and 3 to CON:. The three Fwrite sites leave different RET_*, so the run, the CR/LF pair and the tail are told apart by more than the file's bytes |
| `0x16868` | `c_unlink` | 40 | ✅ verified | GEMDOS Fdelete over a name the harness staged and one it did not — the second answers TOS's EFILNF rather than refusing, because the staged-file table IS the model's filesystem — plus the exact code in `A_c_errno` and the table slot really being cleared |
| `0x16ba8` | `c_auxout_write` | 46 | ✅ verified | 5 spans incl. an empty one, a partial one and a NUL/high-bit/newline mix; the ordered AUX: ledger is the whole surface, and the zero-length case asserts an EMPTY ledger so "never ran" cannot pass as "wrote nothing". Reached through `c_write`'s AUX: arm too |
| `0x16bd6` | `c_prtout_write` | 46 | ✅ verified | the same five spans over Cprnout, whose answer the original discards. `test_character_device_write` runs both writers from one list, so a writer that sent to the other device is 15 cases red |
| `0x14d16` | `c_exit_pterm` | 22 | ✅ verified | four exit codes. The oracle ENDS at the trap and the candidate returns from `os_pterm` — the one place the two shores differ by construction — so what is compared is the ledger entry and the trampoline's three save slots |
| `0x14d2c` | `c_exit` | 70 | ✅ verified | the 73-record walk then Pterm: six flag sets either side of the `& 3` in-use test, two open streams at once, and one open in the LAST record — which is the only thing that pins the walk's bound |

**Mutations tried against these five, each from a deleted `.so` with `__pycache__` swept:**

| mutation | what caught it |
|---|---|
| `c_unlink`'s 0/-1 answer inverted | 2 cases — both rows of `test_c_unlink` |
| `c_prtout_write` sending to AUX: instead of the printer | 15 cases — the shared list is what makes one writer's mistake the other's failure too |
| the character writers' count tested AFTER the decrement | 26 cases |
| `c_exit_pterm` never terminating | 11 cases |
| `c_exit`'s walk one record short | 1 case — `test_c_exit_closes_the_LAST_slot`, **which did not exist until this mutant survived**: every other case's stream sits at FILE_SLOT, and a walk that stopped one record early passed the whole suite |
| `c_open`'s truncating arm dropping the delete's `!= 0` test (2026-09-06) | 1 case — `test_c_open_truncating_abandons_the_call_when_the_delete_fails`, which is the arm's only runnable branch |

**And one is EQUIVALENT, not a hole:** `c_exit`'s in-use test widened from `& FILE_IN_USE` to
`!= 0`. `c_fclose` calls `c_fflush` first, and `c_fflush` returns -1 without touching anything on a
record whose flags carry neither FILE_READ nor FILE_WRITE — so closing a record that is merely DIRTY
writes nothing, makes no trap, and is indistinguishable from skipping it. Recorded so nobody
re-tries it.

### What the demo-range chain now rests on

`test_demo_slideshow_length_chain` runs `fp_acc_load_long` → `fp_dispatch(0x803, /16794009)` →
`fp_dispatch(0x802, *11)` → `fp_dispatch(0x800, +5)` → `fp_acc_to_long` as one differential and
asserts the 5..15 the plate at 0x115d6 in `../names.txt` claims, with both boundaries pinned
(`Random()` = 0 gives 5, `Random()` = 0xffffff gives 15 and never 16). That plate's reasoning is now
executed rather than argued.

### Residuals — reconstructed, not covered by a case

* **`c_ldiv` with a zero divisor executes `divu.w #0,d0` deliberately** — the library's way of
  raising the 68000's zero-divide exception — and then answers 0/0 from `clr.l d0 / clr.l d1`. THIS
  IS NOW A VERIFIED BRANCH, not a residual, and it took a measurement off real TOS to make it one:
  a GEMDOS program run headless under Hatari on the TOS ROM reports vector 5 (`$14`) = `$e00d68` and
  comes back from a user-mode `divu.w #0` with D0 untouched — so the handler RETURNS and the
  library's own continuation is what the machine executes. The harness's image has no such vector
  (`$14` is zero, and the oracle takes the exception into the vector page), so the three cases
  DECLARE the machine by poking an `rte` at `$14`, and a fourth pins that the declaration is
  load-bearing: without it the oracle refuses the run. What remains unpinned is only the identity of
  TOS's handler — the cases run an `rte`, TOS runs `$e00d68`, and nothing in the image could tell
  them apart. The probe itself was a one-off (`tos_probe.run_tos_program`); it is not in the suite,
  because a 20-second Hatari boot in a 2-second `make test` would be the wrong trade.
* **`c_ldiv` with a divisor of 0x80000000 HANGS.** Its magnitude cannot be represented, so `neg.l`
  leaves it negative, the alignment loop shifts the 1 out of the top and never reaches
  `divisor >= dividend` again. The original's own behaviour, transcribed; the fuzz keeps both
  magnitudes below 0x40000000 and says so.
* **`gemdos_malloc_or_fail`'s failure arm (Malloc returned 0 → -1) is unreachable IN A GREEN CASE**:
  the modeled `os_malloc` is a bump allocator that succeeds until the arena's ceiling, and the one
  way to get its 0 — a request the `[0x30000, 0x90000)` window cannot hold — comes back through
  `os_refused`, which reddens the run rather than exercising the arm. Read-verified, as is
  `c_morecore`'s and `c_malloc`'s handling of it.
* **`c_open`'s and `c_creat`'s "GEMDOS refused" arms are unreachable** for the same kind of reason:
  `os_fopen` REFUSES an unstaged name rather than returning a negative handle, so a case that asked
  for one would be rejected instead of exercising the arm. Read-verified.
* **`c_open`'s truncating arm (`mode & 1`) is THREE-QUARTERS read-verified**, and the blocker is the
  staged filesystem rather than a missing model. The arm is Fdelete, then Fcreate, then Fclose, then
  the ordinary Fopen; `os_fdelete` CLEARS the staged slot's name and `os_fcreate` refuses a name the
  harness has not declared ("the harness declares the filesystem", `tools/recreate_kit/include/
  os.h`), so the create that follows the delete always refuses. What runs is the DELETE-FAILS path —
  `test_c_open_truncating_abandons_the_call_when_the_delete_fails`, which is the arm's only branch —
  and the three calls after it are transcribed and unrun. Nothing in the game asks for the mode at
  all: `c_creat` requests write access only. Closing it means an `os_fcreate` that can re-declare a
  name `os_fdelete` cleared.
* **`c_read`'s console arm** (a handle at or below `FD_DEVICE_CON`) is still not reconstructed and
  still refuses — but the reason has changed and is now scope rather than a model gap. Its body is a
  loop calling `c_conin` @ 0x16518 once per byte until the count runs out or one answers -1, and
  `c_conin` is verified above. Porting it is ordinary work on an already-verified routine, and it is
  the natural next thing in this subsystem.
* **`fp_cmp`'s `status_high` is a harness fact, not a reconstruction's output.** The routine stores
  the WHOLE status register, whose high byte is the machine's mode and interrupt mask; the battery
  declares it (0x2700) and every fp_cmp case would redden if it were wrong, but no reconstruction
  could derive it.
* **`fp_pack_float` @ 0x15132 has no caller.** It is `fp_op_table[6]` and all four of the program's
  `fp_dispatch` sites carry opcodes 0x0800..0x0804. It is reconstructed and verified anyway, entered
  at its own stub, because it is real code in the shipped binary.
* **`fp_dispatch` selects among the seven operations with a `switch`, not an indirect jump.** The
  table is `init_globals`' output and never written again; `test_fp_op_table_points_where_the_
  reconstruction_assumes` reads all seven slots off the post-init image, follows each `jmp` island
  and pins the routine it lands on. Dispatching opcode 5 or 6 — the two packing TAILS, which pop ten
  saved registers and unlink a frame `fp_dispatch` never pushed — refuses instead of inventing a
  behaviour.
* **`fp_dispatch`'s widening scratch is its own stack local** (-10(a6)), inside the band the diff
  drops. Nothing compares those eight bytes directly; what pins the widening is the destination the
  widened value is then added to.
* **`c_lseek`'s FAILURE PATH is read-verified and cannot be otherwise.** When GEMDOS refuses a seek,
  the original asks for the current position and the file's length, re-bases the offset, EXTENDS the
  file by `Fwrite`ing `offset - length` bytes read off its OWN UNINITIALISED STACK FRAME, and seeks
  again. Two things stop it being a case: the trap model refuses a seek it cannot serve rather than
  answering an error code (TRAP_MODEL.md, Phase 13, "a refusal is not an error return"), so the first
  seek never comes back negative in a green run; and the bytes that would reach the file are frame
  garbage no reconstruction can produce. The four `RET_*` of that path are named in `include/clib.h`
  and the arithmetic is described there; nothing is transcribed against nothing.
* **THE RECONSTRUCTION KEEPS TWO PIECES OF SCRATCH IN THE IMAGE THAT THE ORIGINAL KEEPS ON ITS
  STACK**, and neither is pinned. `c_fcvt` scales its working copy of a double with `fp_mul`/`fp_div`,
  which take IMAGE addresses, and `c_vfprintf` formats into a 256-byte buffer that `c_fputs` then
  walks by address; the originals are `-14(a6)` and `-256(a6)`. A reconstruction has no frame in the
  image, so `include/clib.h` names three spans at `CLIB_SCRATCH_BASE` — inside the band the
  differential DROPS as stack, which is where the original's are too. A candidate that used different
  in-band addresses would still be green. What IS pinned is what each produces: `A_fp_acc` and the
  digits `c_fcvt` hands back, and the bytes `c_fputs` pushes into the FILE.
* **`c_fmt_float`'s digit buffer is a C array, not the original's 30-byte frame.** The original
  writes `precision + 3` digits into `-30(a6)` and would smash its own frame somewhere past a
  precision of about 25; the reconstruction holds them in `C_FCVT_DIGITS_MAX` bytes and the battery
  stays inside the range the original survives. The overflow is read-verified, not reproduced.
  `c_vfprintf`'s 256-byte buffer has the same shape of limit and the same answer.
* **`c_fmt_integer`'s "unknown conversion" arm formats in a base of the CALLER'S making.** The
  four-way chain leaves D7 alone when the conversion is none of d/u/o/x, so the base is whatever the
  caller left there — and from `c_doprnt` that is the conversion character itself. `c_doprnt` only
  ever routes d/u/o/x here, so nothing in the program reaches it; five cases declare the register and
  run it anyway, including bases this library cannot name.
* **`c_doprnt`'s trailing bare `%` dispatches on D7 for the same reason**, and four cases declare it
  ('d', 's', 'f' and 0 — each consuming a different number of argument bytes). Both are §5
  "a parameter" residuals: real branches, reachable only by declaring a register the C ABI has no
  name for.
* **`c_filbuf` @ 0x14eac..0x14eb2 is DEAD CODE.** Nothing branches there; the two stores it holds
  (ptr = base, cnt = 0) are the compiler's leftovers from a path the optimiser removed. Transcribed
  as a comment rather than as code.
* **`c_filbuf`'s stdout flush is unreachable under the model.** It fires only for a stream whose
  handle is `FD_DEVICE_CON`, and `c_read` — called two lines later — refuses that handle, so every
  run that reaches the flush is voided before it ends. Read-verified; closing it means porting
  `c_read`'s console arm, which `c_conin` has now unblocked (see the residual above).
* **THE A1 A CALL LEAVES BEHIND IS CARRIED, NOT PREDICTED.** `c_getfdmode` comes back with A1 one
  entry past the fd-mode table (= `A_c_errno`) and nothing puts it back, so every trap the CALLER
  reaches afterwards files that rather than what it held before. `c_read` and `c_write` are the only
  two routines that ask, so they are the only two that record it — into a register block the whole
  buffered layer carries BY POINTER (`c_read_reporting` / `c_write_reporting`; the by-value spellings
  remain for callers outside this subsystem). Predicting it per caller was the first shape here and
  it was wrong: `c_fputs`'s second flush files a different A1 from its first, which
  `test_c_fputs_across_several_flushes` is the case for.
* **Two of the three out-of-bounds guards refuse input the ORIGINAL does not survive either.** A
  precision above 60 and a negative one are refused by `c_fmt_float`, and a base needing more than
  `FMT_DIGIT_SLOTS` digits by `c_fmt_integer` — all three well outside anything the original's own
  frames hold. Refusing is not the original's behaviour; the original corrupts its frame and carries
  on. That is recorded here rather than reproduced, because reproducing it means writing outside a C
  array in the harness's process.

**`c_conin`'s `^C` arm is run now too**, and it is the one place where the reconstruction's shape
differs from the original's on purpose: the original FALLS THROUGH from the `^C` branch into the
end-of-file test, which is code the real machine never reaches because Pterm does not return. The
reconstruction returns instead, and the model agrees from the other side — `os_pterm` latches the
event ledger and every entry after it is refused. `test_c_conin_ctrl_c_ends_the_program` is what
runs the arm at all; nothing else in the suite types a `^C`.

### The one arm of this subsystem still unrunnable

**`c_conin`'s AUX: handle wants GEMDOS Cauxin (0x03), and the model REFUSES it deliberately.** The
console has a staged keystroke queue behind it and the serial line has nothing at all, so every
answer would be invented and the real call would block waiting for one that never comes
(tools/recreate_kit/include/os.h, `os_cauxin`). The arm is transcribed as the refusal it is; closing
it means a second staged input stream, of exactly `os_console_take_key`'s shape.

## Borrowed globals

A global lives in the header of the subsystem that owns the data (README.md, "Adding a function").
A row here is a LOAN: a global defined in a header that does not own it, because the routine that
does is unported. Each row names the address, the name as spelt, the owner, where it is defined
today, and why — and a finished migration DELETES its row and the `#define` it names, so the
table's length reads as outstanding debt rather than as history.

| Addr | Name | Owner | Defined in | Why on loan |
|---|---|---|---|---|
| `0x25182` / `0x2518a` / `0x25192` | `A_const_mouse_x_scale_room35` / `A_const_mouse_x_scale` / `A_const_mouse_y_scale` | clib (the DATA the fp package divides by) | `include/gameplay.h` | three doubles in the program's DATA segment. `include/clib.h` owns the float package but names none of the program's own constants; if it grows a home for them, these three rows and their defines go |

**ONE ROW IS LEFT, AND THAT IS THE CONTRACT WORKING.** This table has carried nine rows and has
retired eight, each by the edit its own "Why on loan" column named in advance:

* `A_room_number`, `A_object_table` and `A_room_table` were `include/blit.h`'s while the gameplay
  subsystem was unported. `include/gameplay.h` defines all three now, plus the `OBJECT_*` / `ROOM_*`
  record offsets that moved with them, and `src/blit.c` includes it to read them.
* `A_key_raw`, `A_key_shift_state`, `A_mouse_y`, `A_mouse_x` and `A_mouse_buttons` — the input block
  — were `include/gameplay.h`'s while the front end's VDI binding was unported. `include/frontend.h`
  defines all five now (the routines that FILL them are `vq_mouse` @ 0x16a26, `vq_key_s` @ 0x16a5e
  and the `Crawio(0xff)` poll, all that subsystem's), and `src/gameplay.c` includes it to read them.
  `A_key_raw` is written from `game_frame_update` @ 0x1238e — a writer in another subsystem, but one
  word of one block, and a block has one owner.
* `A_sound_enabled` had a row and should not have: the routine that WRITES it is
  `game_frame_update`'s `^S` arm @ 0x123ea, which is the gameplay subsystem's own, so gameplay owns
  it and never borrowed it. `title_menu_loop` @ 0x115d6 reads it too, and a reader in another
  subsystem is not ownership. The row is deleted as a misfiling rather than as a migration.

Rows are DELETED rather than annotated, so the table's length reads as outstanding debt and not as
history. What is left is the three doubles ABOVE, and their row says what would retire them.

**What the two checks do and do not cover, for the record offsets that travel with a table.** An
offset re-defined under the SAME name in two headers IS caught — `test_no_constant_is_defined_in_two_files`
is keyed on the name and takes offsets as readily as addresses. What is NOT caught is the same
offset under a DIFFERENT name: `OBJECT_TILE` in one header and, say, `OBJ_TILE_INDEX` in another,
both 0. `test_no_address_has_two_spellings` is value-keyed but only over the `A_*` family,
deliberately — for geometry and record offsets a shared VALUE carries no information at all
(`OBJECT_TILE` and `MFDB_ADDR` are both 0 and always will be), so a value-keyed check over these
families would fire on coincidences and be turned off. So the differently-named duplicate is the
case that has to be caught by reading, and the provenance tag on every `OBJECT_*` / `ROOM_*` /
`CANDLE_*` / `PROBE_*` line in `include/gameplay.h` — the `lea`/`muls` instruction each offset was
read off, and the case that pins it — is what makes that reading cheap.

## Not reconstructed, and why

Every `fn` line in `../names.txt` with no ✅ row above eventually appears here, with the reason:
unreachable under the model, a model gap named above, or simply not yet started. Each ported section
defers a named set; those sets are gathered here so that "what is left" is one list rather than
several asides.

**Read the "not blocked any more" rows first.** TRAP_MODEL.md phases 11-13 and the front end's GEM
binding between them retired five of this table's reasons in one wave, and a row that still reads
like a gap when it has become ordinary work is the most expensive kind of stale prose here.

| Routine(s) | Subsystem | Why not, and what would close it |
|---|---|---|
| the `GHOST.LOA` player itself — a second program, so it has no address in this one | voice | **THE TWO GAME ROUTINES ARE PORTED** — `## Verified — voice` — and what is left is the second program `play_voice` loads and calls: an `ABSFLAG` .PRG that enters supervisor mode, saves the MFP registers, installs a handler at `$134`, programs Timer A from a rate table and busy-waits on a done flag (`../notes/loader.md`). The kit fires no interrupts, so the handler would be entered directly per sample (the shape `timer_c_sound_isr` uses) and the setup/teardown run as slices around the MFP writes; the WAIT has no site the scheduled-write model can name, because the byte it spins on is written by the handler and not by an external agent. It also arms the cartridge DAC, which nothing models |
| `play_voice`'s call into the LOA, at 0x10232 | frontend | ONE `jsr`, four bytes, and it is the boot chain's join to the row above: `game_top_boot` stops at it and `game_top_boot_tail` starts after it. `src/voice.c`'s `play_voice_arm` answers the address it would call, so the composition is checked rather than falling through silently |
| `game_top_free_voice_buffer` @ 0x1024e | frontend | ONE `c_free`, ten bytes, transcribed as a function of its own and run by no case. The block it returns is the one `load_voice_player` allocated, and a slice entered fresh has none: `A_voi_buffer` holds the loaded image's zero, so both sides would walk a free list built out of whatever lies below address 0. `c_free` itself has nine cases in `test_clib.py` |
| the menu's four dispatch compares, from 0x11700 | frontend | `cmp.w #$47,d0 / bne` and the three like it, which write nothing at all: `menu_read_key_and_fold` ANSWERS the folded key and each arm's own slice is entered at its first instruction, so what is unrun is the branches between them |
| the two `do { … } while` conditions, at 0x10d34 and 0x11d60 | frontend | The room loop's "is either player still in" and the menu's "was anything chosen" — the composition's own tests, which no slice may include because each is what decides whether the routine goes round again or returns. Both are read-verified; the flags they read are written inside slices that are not |
