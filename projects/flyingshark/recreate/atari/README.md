# FLYSHARK.PRG — the reconstruction, on a 68000

The ten verified subsystems in [`../src`](../src) compiled by `m68k-elf-gcc` and run on a real Atari
ST (Hatari, and a real machine when you put the floppy in one). **The cores are compiled unchanged**:
what differs between this build and the differential `.so` is the include path, the four kit source
files it leaves out, one core's optimisation FLAGS, and one routine it calls the asm twin for
instead of the C — the last two being the performance campaign's, both pinned by
[`../test/test_asm_sprite.py`](../test/test_asm_sprite.py) and by this directory's own framebuffer
identity, and both written up in [`../STATUS.md`](../STATUS.md)'s "On-target performance".
`make test` in [`..`](..) is untouched by anything in this directory.

**Two builds, and the order matters.** `build.sh` with no argument makes the PLAYABLE program: it
writes no files anywhere, which is what you want on a floppy and which means the full smoke has
nothing to read. So run the checks first and the deliverable last:

```bash
bash atari/build.sh smoke              # the program with a frame limit and a record
python3 atari/smoke.py --floppy        # boot it, the ORIGINAL and the .ST; judge every surface
bash atari/build.sh                    # NOW the playable build -> disk/AUTO + disk/FLYSHARK.ST
python3 atari/smoke.py --floppy-only   # ...and judge THAT one on the frame it publishes
bash atari/run.sh                      # play it   (run.sh floppy | run.sh original)
```

Any command here may be run from anywhere: every path in every script is derived from the script's
own location. `smoke.py` refuses a play build in its first second rather than waiting out a deadline
for a file that build never writes, and names the command above.

## What it does, measured

Booted headless on TOS 1.04 with `--memsize 1`, from `AUTO\` on a GEMDOS drive, the reconstruction
loads its eight files, draws the title picture, and runs the attract screen — and **the frame it
publishes at attract frame 120 is the ORIGINAL binary's frame, byte for byte, all 32,000 of them**.
`smoke.py` is where that is checked, along with everything else a run can be watched on, and it
leaves its captures in `../../out/smoke/` for a person to look at (that directory is gitignored, so
the pictures are evidence of a run rather than of a commit).

| what | number |
|---|---|
| `FLYSHARK.PRG` | play: text 56,576 + data 0 + bss 559,268, 582 relocations, 57,334 B on disc. The `smoke` build adds the record's two files and the frame limit: the same text, 599 relocations, 57,351 B. Both are byte-reproducible across rebuilds. (Text was 50,432 before the performance campaign; the whole +6,144 is `src/sprite.c` compiled at -O3 with bounded unrolling — the asm twin is 792 B of body and a NET 256 B SMALLER than the C call sites it replaces, because GCC no longer specialises the blitter four ways. `../STATUS.md`'s "On-target performance" has the measurements) |
| `FLYSHARK.IMG` | 48,694 B — the original's relocated TEXT+DATA, staged into the image at boot |
| loaded at | `0xa956` (TPA low), image base `0x18900` (both builds now carry the same text), program ends `0x9327a` |
| headroom on a 1 MB ST | 413,054 B between the program's top and the stack GEMDOS gave it, against a 65,536 B floor |
| the screen ring | `0x60000` + `0x7800`/`0xfa00`/`0x17700`/`0x1f400`, the verified pointers |
| files | 8 opened, 288,551 B read, 0 failures |
| the chip | 13,611 PSG register writes = 27,222 hardware stores, 0 refused; SR $2304 — supervisor at IPL 3, the level the original chooses for itself. (It was 41,028 before the performance campaign, and the drop is the point: the sound module ticks on the VERTICAL BLANK, so 200 frames that now cost 1,047 blanks instead of 3,160 drive the chip for a third of the emulated time — the music-to-frame ratio is now the original's, where before it was three times too fast) |
| pace | **4.55 vertical blanks a frame = 11.0 fps, against the original's own measured 4.00 = 12.5 fps** — 1.14x, and 89 of 126 frames take exactly the four the original takes (`profile.py pace`, on the steady attract screen). A blank is 160,256 cycles, so a lever worth less than one is INVISIBLE here: the frame still ends on the blank it ended on and the saving becomes `Vsync` idle inside it. That is why the vertical-blank path's own 17% (`../STATUS.md`, "What a vertical blank costs") moved this line from 4.559 to 4.548 and nothing else — a per-blank profile is the instrument for a per-blank lever. The smoke's own line says 5.24 over the whole run and the two are the same build: the smoke divides ALL the run's blanks — the boot, the 108-call prescroll, the heavier text pages — by the 200 frames it counted, where `profile.py` clocks frame to frame past the prescroll. The smoke's number is a floor check, this one is the pace |

The pace is the one number that is not the original's, and it is class 13
(`docs/on-target-execution.md`). **The campaign has run** (`../STATUS.md`, "On-target performance"):
the frame went from 13.60 vertical blanks to 4.56 against the original's own measured 4.00, in three
measured levers — the blitter's inner-loop `memcpy` spelt out, `-O3` with bounded unrolling for the
one file the profiler named, and an asm twin for the four unclipped sprite blitters that is the
original's own machine code byte for byte. A fourth cut the vertical-blank path by 23%, which the
pace can barely show for the reason the row above gives. Levers were also tried and refused, and the
size budget and the measurements that refused them are written down beside them.

**`profile.py` is the instrument, and it is in this directory.** `pace` clocks both binaries with a
repeating breakpoint on `render_frame`; `ours` / `original` / `compare` run the Hatari CPU profiler
over a window of the same length on each and ratio them function by function. Every number in the
STATUS section came out of it, and re-running it is one command:

```bash
python3 atari/profile.py pace            # ours: vblanks per frame, and its spread
python3 atari/profile.py original-pace   # ...the 1988 binary's, the same way
python3 atari/profile.py ours            # ...and where the cycles are, per symbol
python3 atari/profile.py ours --phases   # DIAGNOSTIC: inlining off, so each phase is a row — read for SHAPE, not for cost
```

**Every ours-side mode rebuilds and RESTAGES `disk/`** with a smoke build whose frame limit is far
above what a measurement window can hold, and says so as it goes. That is the wrong volume to play
or to run the full smoke against, so the two-build order above applies afterwards as well: run
`bash atari/build.sh` before `atari/run.sh`. `--no-build` measures whatever is already staged.

**The original does not make its own budget either, and that is the number to compare against.**
`render_frame` waits for the third vertical blank of the frame it just published, so 3 blanks is
the BUDGET; measured, the shipped binary takes 4.000 on every one of 129 attract frames. 12.5 fps,
not 16.7.

## The load-address budget

**The original only works from `AUTO\`, and this build does not have that constraint.** Both halves
matter, because the second is a consequence of a decision this build makes and not a property of the
game.

The original asks for `Setscreen(0x70000, 0x78000)` and then builds its 0x1f900-byte scroll ring
*downwards* from whatever `Physbase` answers — so the ring lands at `round_up_256(0x78000 - 0x1f900)`
= `0x58800`, at a fixed machine address. Its own image (text+data+bss) is `0x4aede` bytes, so it
survives only while

```
load address + 0x4aede <= 0x58800      i.e.   load address <= 0xd922
```

From `AUTO\` under TOS 1.04 it loads at `0xaa56` and clears the ring by 11,980 bytes. From the
desktop it loads at `0x12596`, ends at `0x5d474` — 19,572 bytes INSIDE the ring — and dies on an
illegal instruction a second after the last file loads, looking exactly like a missing deprotection
patch (`../../tools/boot_shots.py`, and `docs/packed-executables.md`, "Gamex hard-disk installs").

This build cannot use those numbers at all, and the reason is not its size. The cores address the
game as `image + <Ghidra address>`, and in IMAGE space the program occupies `[0x10000, 0x5aede)` —
so a ring at image `0x58800` would sit **inside the program's own bss**, on top of the sound module
and the entity arena. The original escapes that only because its whole image space is shifted down
by `0xaa56 - 0x10000`, and a reconstruction inside a TPA has no such shift to spend. So:

* the image is a `.bss` array and `fs_image_base` is where it landed (rounded up to 256);
* `shim_include/init.h` answers `fs_physbase()` with **`0x7f800`** — `test/abi.py`'s
  `SCREEN_RING_PHYSBASE`, the same Physbase every differential case in the project ran with, so
  `boot_init` derives the *verified* ring pointers and the ring lands at image `0x60000`, clear of
  the program by 20,770 bytes;
* the shim's own `Setscreen` makes that image address true on the machine before any core runs, and
  `Physbase()` is read back and compared with it — the class-8 assertion.

**What replaces the ceiling is a floor, and it is asserted every boot.** The program needs
609,424 bytes of TPA (text + bss) plus the 256-byte basepage; `_start` latches the basepage and the
entry stack pointer before anything can move them, and `flyshark_main` publishes `p_lowtpa`,
`p_hitpa`, the program's top and the headroom between them. On the 1 MB ST the smoke measures
413,074 bytes spare. A machine with less — an AUTO-folder resident that ate low memory, a 512 KB
ST — reddens there rather than crashing somewhere later.

`AUTO\` is kept anyway, for two reasons that survive the arithmetic: it is the recipe the release
ships and the one the original is comparable under, and it is the only way a floppy starts a game
without a desktop, a mouse and a person.

## The memory map

```
image space          machine                what   — the machine column is one run's: the base is
                                            wherever GEMDOS put the program, rounded up to 256
                                            (0x17200 for the smoke build, 0x17100 for the play
                                            build, and it moves whenever either grows)
0x00070 / 0x00118    -                      the cores' vector cells: ordinary image longwords here,
                                            and the shim DISPATCHES on them (see below)
0x10000 .. 0x1be36   0x27200 .. 0x33036     the original's TEXT+DATA, staged from FLYSHARK.IMG
0x1be36 .. 0x5aede   0x33036 .. 0x720de     its BSS: the sprite bank, the four tile banks, the map,
                                            the sound module, the entity arena — filled by the
                                            eight files the boot loads
0x5aede .. 0x60000   0x720de .. 0x77200     the TAIL band: 20,770 bytes checked for ZERO
0x60000 .. 0x87600   0x77200 .. 0x9e800     the screen ring and the frame above its top base
                                            (test/abi.py's SCREEN_RING_SPAN), with the displayed
                                            screen at image 0x7f800 = 0x96a00
0x87600 .. +0x1000   0x9e800 .. 0x9f800     the GUARD band, filled with 0xa5
```

Two bands rather than one, and the reason is the same as in the sibling project: a census names
addresses the code NAMES, and what it cannot cover is an address the code COMPUTES — a tile blit one
row past the ring's base, a scroll span one word too generous. The tail band is checked for zero
rather than filled with a pattern, because zero is what both shores hold there and a pattern would
make this build differ from the differential over bytes the cores may legally read. A wild store
above the guard band is beyond any band; nothing here claims otherwise.

## Shim, not core — what this directory supplies and why

Everything in this table is a routine `../STATUS.md` files under "Not reconstructed", or something a
differential structurally cannot have. Each is composed from verified cores; none re-implements one.

The title flow used to be four of these rows and is now none of them: `enter_title`,
`title_attract_prescroll`, `title_attract_start_tune`, `title_attract_poll`, `title_frame_step` and
`load_level_assets` are all cores (`../include/frontend.h`), each answering with the branch the
original took. What is left is the row below — the frame counter and the stop test this build needs
between those calls, which is why it restates `src/frontend.c`'s own composition instead of calling
`title_attract_loop`.

| what | why it is not a core | where |
|---|---|---|
| `_start`, the trap wrappers, `Super`/`fs_leave_supervisor` | the oracle services traps in-process; there is nothing to diff | `flyshark_os.s` |
| the `$70` and `$118` entries and their dispatch | an exception frame and an `rte` are not expressible in C | `flyshark_os.s`, `dispatch_image_vector` |
| `main`'s two re-entry labels @ 0x15754 and 0x15758 | both are BRANCH targets rather than calls — `init_new_game` ends `bra.w enter_title`, and the stage loop is re-entered by an unwind — so the calls either side of them are composed here. The slice between them is a core (`main_boot`), and the window that once blocked it is a `project.toml` key now | `run_the_whole_program` |
| the attract loop's frame limit and stop | `title_attract_loop` is verified whole, but its only exit is the fire button; a smoke run stops at a frame count | `run_the_title`, `run_the_attract_loop`, `run_the_attract_spin` |
| `start_level`'s middle @ 0x11494 | five arms on the level number between two verified slices | `start_level` |
| the frame loop's three exits | the original leaves them by unwinding the stack; a C function cannot | `run_the_frame_loop` |

**`A\MODULE.BAK`'s bytes are loaded and never executed.** The file is a GEMDOS `.PRG` — header and
all — that the game reads RAW into its own bss at image `0x58928` and calls through the entries at
`+0x1c`, and this build loads it exactly the same way, with the game's own record and the verified
`load_file`. What runs is the RECONSTRUCTED driver: `../src/sound.c`, thirty verified rows, reading
the module's tables and patterns out of the image and driving the chip through `shim_include/psg.h`.
Executing the module's own 68000 code was the alternative (Bubble Ghost's `GHOST.LOA` build does
that), and it is the wrong trade here: the driver is the part of this game with the most verified
rows behind it, and routing it through the seam is what puts every one of its 41,028 register writes
where a counter and the write ledger's target half can see them.

**The exits are watched, not intercepted** (`docs/on-target-execution.md` class 7). `frame_loop_once`
is verified whole, so the shim cannot reach inside it; instead it reads, at each frame boundary, the
state the verified code has already written — `level_number` moved (the level advance),
`game_over_delay` went negative (`game_over_hiscore_check` ran), the abort key's bit is set. Each
costs the rest of one frame that the original's unwind skips.

## The seam

`shim_include/` is first on the include path. Everything in it either shadows a kit header or
answers a call the kit models, and `build.sh` refuses a build where a core reaches past it.

| header | what it replaces | what the target half does |
|---|---|---|
| `os.h` | the kit's TOS model | real GEMDOS `Fopen`/`Fread`/`Fclose` (with the image bound and four counters), real XBIOS `Setscreen`/`Setpalette`/`Vsync` with every address translated out of image space, `Bconout(4,…)` for the IKBD, `Cconout`, and a `Super` that does not trap because `_start` already did |
| `hw.h` | `src/hw.c`'s ordered ledgers | the real stores, and `bclr`/`bset`/`and.b` as the ONE instruction they are — a read-modify-write spelt as a store would clear every bit it should preserve |
| `psg.h` | `src/psg.c` | `$ff8800`/`$ff8802`, select then data |
| `sched.h` | `src/sched.c`'s capped polls | the same spins with NO cap, because the interrupt really writes the byte here (a bound that exists for the harness must not ship) |
| `init.h` | two `static inline`s in a CORE header | `fs_physbase()` answers the image Physbase this build chooses; `fs_kbdvbase()` answers the REAL `Kbdvbase()` expressed in image space, so the core's `image +` lands back on TOS's own struct |
| `string.h` | nothing — m68k-elf ships no libc | `memcpy`/`memset`/`memmove`, in `flyshark_backend.c` |
| `tos.h` | — | the trap prototypes and `fs_image_base`, the one constant the two address spaces differ by |

Three addresses the translation cannot reach, and each is handled where it happens: the 68000's own
vectors `$70` and `$118` (the cores store Ghidra addresses into the image's vector page and the
shim's two entries dispatch on what they find — which is what makes `acia_ikbd_isr`'s two-state
machine work here with no knowledge of it in the shim), and TOS's KBDVBASE (above).

`build.sh` runs three gates before the compiler and three after it. Before: every `os_*` a core
calls is shadowed (10 of them), no core includes a shim header by name, and every trap wrapper saves
`%d2`/`%a2` (`tools/assert_trap_registers.sh`, 16 wrappers, and it proves on every run that it can
fail). After: **the asm twin is what the game calls** — `blit_sprite_rows_unclipped_asm` defined by
the `.S` object and referenced by the core object, because that substitution otherwise fails
SILENTLY (drop `-DFS_ASM_SPRITE` and the seam resolves to the C, everything still links, the pixels
are still right, and only the frame rate says so; `../src/asm/README.md`); `_start` is at offset 0,
where GEMDOS enters; and `g_record` is still in the linked program, which is not bookkeeping but the one thing that makes a PLAY build locatable. Nothing reads
that array in a play build, so as a file-static it is dead stores and GCC deletes it; the check was
written after `smoke.py --floppy-only` found the magic at zero addresses in a megabyte of RAM, and
making the array static again reddens the build.

## The surfaces

`smoke.py` boots the reconstruction and the original through the same recipe and checks all six
(`docs/on-target-execution.md`, "The observable surfaces"):

* **memory** — the published framebuffer against the original's at `scroll_pos == 0xf0`, byte for
  byte. Its control costs no extra boot: the same comparison against the frame the original
  published one `render_frame` earlier must DIVERGE, and does (12,779 bytes).
* **the trap ledger** — `--trace os_base`: the same eight files opened in the same order.
* **the hardware-state vector** — the sixteen colour registers against the game palette in the
  program's own table, the resolution byte, and TWO class-8 read-backs: `Physbase()` against the
  address handed to `Setscreen` at the boot, and — at the end of the run — the shifter's own two
  bytes against `image base + screen_draw`, which is the only check there is that the game's
  per-frame publish reaches the chip. That one matters most: the game moves the physical base every
  frame and the harness's `Setscreen` event drops that argument entirely.
* **the input path** — a real key through the real `$118` into `acia_ikbd_isr`, asserted twice: an
  UNWATCHED scancode must move none of the eight bits, and a WATCHED one must move its own, caught
  by a breakpoint on the byte while the key is held (the negative check alone is equally true of a
  handler whose ladder never runs).
* **rendered pixels** — the title picture, captured on a BREAKPOINT rather than by polling: the
  program sets `level0_assets_loaded` one statement before the sprite bank overwrites the picture's
  buffer, so that byte is the moment, and the capture is taken at the following vertical blank
  (stop-then-shoot). Every colour of `FLY_SHK.NEO`'s own palette must be on screen at once.
  **Two races live in that one capture, and both are measured rather than assumed.** A breakpoint on
  a state can only be armed once the driver knows the address, and a state that is ALREADY true
  fires at once — on the attract screen, a wrong picture rather than a missed one (with a
  five-second poll for the program, the arming lost that race two runs in three and the check failed
  at 4/15, the attract screen's own score). So the smoke build writes a BEACON as its first act and
  the driver waits on that instead of polling. **The arming's own cost was the rest of that race**,
  found during the performance campaign: the driver then located the program by dumping the whole
  megabyte and scanning it, and the dump spent enough of the window that the capture came back BLACK
  about one run in three. The beacon's four bytes ARE the image base — `flyshark_main.c` had been
  writing it there all along — so the breakpoint is now armed straight off the file with nothing
  between, and the "was it already late" test is a one-byte read taken AFTER the breakpoint stands.
  Three consecutive green runs since, with both scores identical.
  The second race is the other way round: class 8 says photograph at the NEXT vertical blank, but
  the rest of this boot — 117 KB of sprite bank and `enter_title`'s `set_palette_black` — can pass
  in less than one blank, and one run in three came back black. So BOTH captures are taken, at the
  trigger and one blank later, and the better score is the picture; the run prints both.
* **when a check gives up, it says why** — what it was waiting for, how long it waited against
  which deadline, and the tail of Hatari's own log. The deadlines are wall-clock on a machine that
  may be busy (a second emulator on this box stretched a 30 s run to 155 s once), so they are
  generous by about five times over a quiet host, and nothing waits on a fixed sleep for something
  it can poll for: the program is located by the RECORD'S OWN MAGIC in a RAM dump, which works on a
  GEMDOS drive, on a floppy (where Hatari writes no `.ST` back to the host) and in a play build
  (which writes nothing at all).
* **timelines** — vertical blanks per drawn frame, the scroll's two-per-frame step, one `Setscreen`
  per frame plus the boot's two, and the seam counters: `hw_writes == 2 x psg_writes` with
  `psg_writes > 0` says every hardware store was one half of a PSG register write AND that the chip
  was driven at all (the equality alone is green at zero — the seam's own inline makes it true by
  construction).
* **exit status and the log** — Hatari's return code and its bus/address-error and halt lines, for
  both runs, plus the teardown read-backs (`$70`, `$118`, TOS's joyvec and the screen all handed
  back, which is what stops the machine halting a second after `Pterm`).

## Deliberate divergences

Three, all of them named because a reader of the disassembly beside this build would otherwise find
them and wonder.

1. **An easy game gets the hard arm's fire rates.** `init_stage_state` ends
   `tst.b hard_mode / beq.w $12cb6 / bra.w $12cc8` — two entries into `difficulty_apply_fire_rates`
   that differ in four register immediates — and the reconstruction verifies the HARD one (0x12cc8).
   The shim calls the verified core on both arms rather than transcribing the other four constants
   into an unverified copy. It is a real gameplay difference (enemies reload every 10 frames rather
   than every 35) and `../STATUS.md`'s "Unpinned on target" carries it.
2. **The screen is not at `0x78000`.** It is inside this program's own array, at
   `fs_image_base + 0x7f800`. The load-address section is the argument.
3. **The IKBD is put back at the teardown** with two commands (`$1a`, `$08`) the original never
   sends, because the original never ends. Without them the desktop's mouse is dead after `Pterm`,
   which is the mirror of class 12 — a device left in the wrong mode for the OS instead of for the
   game.

## What is unpinned

* **The joystick has never been pressed.** Hatari's `--cmd-fifo` has no joystick event and a key
  bound to its keyboard-as-joystick emulation is swallowed headless, so the stick cannot be pressed
  from outside the emulator at all (`tools/hatari_headless.py`, and `docs/on-target-execution.md`
  class 12, which is a defect found exactly this way). What `smoke.py` DOES exercise is the rest of
  that path: a real key, through the real `$118`, into `acia_ikbd_isr`, with the byte it filed and
  the `bclr` it made both asserted. What stays untested is everything downstream of the IKBD's `$14`
  mode: the `$FE`/`$FF` packet headers, the two continuation vectors, and therefore starting a game,
  flying the plane and dropping a bomb. **A person with a stick is the only check there is.**
* **Nothing has been played past the attract screen** under any automated check. `run_the_frame_loop`,
  its three watched exits and everything in `frame_loop_once` are verified off target and have never
  run here.
* **Real hardware.** Every number in this file is Hatari's. The floppy is written and verified
  (`mkfloppy.py` reads it back with a different parser) and has not been in a drive.
* **One TOS.** Everything is TOS 1.04. `docs/on-target-execution.md` class 6's working rule is to
  run the smoke on more than one ROM — EmuTOS is forgiving where real TOS is not, and the two
  agreeing byte for byte is a much stronger green than either alone. Not done here.
* **The window where TOS still owns the keyboard.** `boot_init` sends the IKBD `$14` command and the
  shim installs the real `$118` immediately after that slice returns rather than inside it, so a
  joystick packet arriving in between is taken by TOS's handler. It is microseconds and it is not
  the original's window.
* **The teardown's own frame.** The shim hands the machine back after the frame limit; a play build
  never reaches it, and a person quits by resetting the machine. There is no quit key — so the play
  build also never publishes its seam counters, and `--floppy-only` judges it on its FRAME instead
  (`../STATUS.md`, "every seam counter in the PLAY build").
* **Two busy-waits whose cap is spelt in a CORE**, not behind the seam — the pause key and the
  fire-release wait give up after 4,096 polls on the machine. `../STATUS.md` has the row; the fix is
  in files this build does not own.

## The floppy

`mkfloppy.py` writes `disk/FLYSHARK.ST` — 720 KB, double-sided, with `AUTO\FLYSHARK.PRG`,
`FLYSHARK.IMG` in the root and all 21 of the game's data files in `A\`. The filesystem is
`tools/st_build.py`'s (which is what makes the boot sector one TOS will mount and not execute); what
this project's file adds is the second subdirectory, because `st_build.build()` writes one.

712,704 B used and 15,360 B free for the PLAY volume — every level's assets fit, with 15 clusters
to spare. It was 21,504 B free before the performance campaign spent 6,144 B on hotter codegen for
one file; `../STATUS.md`'s "On-target performance" is where that budget is argued, including the two
levers it refused for overrunning it. If a build
grew past that, the volume drops LATER LEVELS' tile banks whole rather than in part, and says which;
the boot's own eight files are required, and a volume that cannot hold them is refused rather than
written.

**Do not write-protect it.** `load_file` opens with GEMDOS mode 2, read *and* write, which is the
original's own constant — a write-protected disc fails the open, and `load_file` has no error
handling at all, so the game would draw whatever was in the buffer.
