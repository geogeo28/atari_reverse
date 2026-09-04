# ZYNAPS.PRG — the reconstruction on a 68000

**M2: the whole game — boot, attract, a playable section, a death and a restart — byte-identical to
the shipped binary for 180 frames. M1: the title picture and its music.**

The M2 section is next; everything after it is M1's, which still builds, still runs and is still
what `smoke.py title` certifies.

`projects/zynaps/recreate/` holds every routine of the program, verified byte-for-byte against the
original 68000 code by the differential harness. Until this directory existed, none of them had ever
executed on a 68000. This is the cross-compile: the same C, unmodified, plus a hardware shim,
wrapped into a GEMDOS `.PRG` that boots under Hatari and PLAYS — and a `smoke.py` that judges it
against the shipped binary on the six named surfaces.

```bash
bash atari/build.sh title            # -> build/ZYNAPS-title.PRG, disk/ staged for Hatari
python3 atari/smoke.py title         # twelve checks, all green
bash atari/build.sh titlefault       # the negative control
python3 atari/smoke.py titlefault    # the same twelve plus two, the colour pair INVERTED
bash atari/build.sh floppy           # -> disk/ZYNAPS.ST, a bootable Atari floppy
python3 atari/smoke.py floppy        # the same twelve, off a real FAT12 volume, both sides
python3 atari/smoke.py floppy --tos-rom ../../../../tools/hatari/TOS102US.img   # ...on another ROM
bash atari/build.sh play && bash atari/run.sh    # ...and the one a person watches
```

Read [`docs/on-target-execution.md`](../../../../docs/on-target-execution.md) first: the seam
pattern, the twelve-entry bug taxonomy, and the six observable surfaces are that file's, and every
design decision here is an application of one of them.

---

# M2 — THE WHOLE GAME

**Boot, attract loop, a section you can play, a death, a restart — composed out of verified slices
in the original's own order, and byte-identical to the shipped 1988 binary for the whole of the
first life.**

```bash
bash atari/build.sh game        && python3 atari/smoke.py game        # seven checks, all green
bash atari/build.sh gamefault   && python3 atari/smoke.py gamefault   # the control, INVERTED
bash atari/build.sh play        && bash atari/run.sh                  # ...and the one you play
bash atari/build.sh play floppy                                       # -> disk/ZYNAPS.ST for the STE
bash atari/build.sh cheats      && python3 atari/smoke.py cheats      # the TRAINER's positive control
```

Every one of those binaries carries the **trainer** — type `Z`, `Y`, `N` in order at the title, then
`F1`/`F2`/`F3` — which is the one thing in this directory that is deliberately not the 1988 program. It is inert
until a player arms it and every mode above asserts it stayed that way; see **THE TRAINER** below.

## What runs, and in what order

`zynaps_main.c` composes every slice of `_start`, of `title_attract_loop` and of the section chain,
and then calls `frame_loop_once` until it leaves. There is no unverified body anywhere in the path;
what the shim adds is the four MFP read-back spins, the interrupt dispatch, and a frame budget.

| the original | what runs here |
|---|---|
| `0x10000`..`0x1002c` | the M1 prologue: `boot_enter_supervisor`, the Line-A opcode, `boot_save_vbl_vector`, the two `ikbd_send_cmd`s |
| `0x1002c` | `boot_load_title_assets` — and the real `$70`/`$120` vectors go in after it |
| `0x101ba` | `boot_load_gameplay_assets` — fourteen more files and the banks built from them |
| `0x104c8` | `boot_install_ikbd_isr` — and the real `$118` vector goes in after it |
| `0x10500` | `boot_front_end_prologue`, the top of the loop of loops |
| `0x10520` | `title_attract_loop`: `attract_program_timer_b`, a spin, `attract_program_rasterbar_timer`, a spin, `attract_build_colour_bars`, `attract_wait_for_start` |
| `0x10524`..`0x1069e` | `boot_stage_frontend_screens`, `boot_program_timer_b`, a spin, `boot_program_raster_timer`, a spin, `boot_enable_interrupts` |
| `0x10792` | `boot_new_game_records` |
| `0x10814`..`0x10f4e` | the section chain: `section_advance` -> `section_reload_needed` -> (`section_reload_intro_screens`, `section_load_assets`) -> `section_restart_prologue` -> `section_start_prefill` -> `section_start_tail` |
| `0x10f4e` | `frame_loop_once`, until one of its five exits; four of them re-enter the chain and the fifth goes back to `0x10500` |

**Game over and the high scores are not a step of this list, and that is the program's shape rather
than an omission**: `frame_resolve_hits_and_game_state` calls `game_over_screen` itself on the last
life and comes back with the TITLE exit. So the ending is reached by playing, not by composing.

## The four things the shim adds, and why each one has to be there

* **The four `$fffa21` read-back spins** (`0x1062e`, `0x1066c`, `0x12b0a`, `0x12b48`). Ten bytes
  each, `cmpi.b #$xx,$fffa21 / bne` back to the store — the one shape the kit's seeded read model
  refuses, because the byte read is one the run itself wrote two instructions earlier
  (`../STATUS.md`'s "Not reconstructed", its last KIT row). The verified slices stop on the store
  and resume after the spin, so this is the ten bytes in between, done on the real Timer B data
  register. **Surface: the hardware-state vector** — `mfp_settle_restores` counts how many times a
  read did not come back with what had just been written, and it is 244 over a run (the register
  is a live counter once the timer is started, so a read catches the loaded value only sometimes,
  which is exactly why the original spins).
* **The interrupt dispatch.** The program re-points its vectors per phase, twelve stores of seven
  distinct handler addresses, and it makes them into the IMAGE's vector page — which here is a
  longword inside the image array, not low memory. So `zynaps_os.s` has three entries (`$70`, `$120`,
  `$118`) and each reads the longword the cores wrote and calls the handler it names.
  **An address the table does not know is a HALT with the value in the record**, never a silent
  skip: a dropped interrupt would leave the frame loop's sync wait spinning for ever and the run
  would look like a hang with nothing in it. `unknown_vector_halts` is 0 in every run, and the
  per-handler entry counts are in the record — a phase whose handler was installed and never
  entered is visible as a zero.
* **The frame budget.** `ZY_GAME_FRAMES` stops the headless build at a declared `frame_loop_once`
  count and hands the machine back exactly as M1 does. `build.sh play` puts it out of reach.
* **The read-modify-writes, which are the cores' own now.** Unpinned 2 above asked this file for
  three definitions and this build supplies them: `hw_bset8`, `hw_bclr8` and `hw_and8`, each a byte
  access, each calling `note_store()`. **It is not cosmetic** — `move.b #$40,$fffa09` does not
  enable MFP channel 6, it disables every other channel of interrupt-enable B, Timer C among them,
  which is TOS's 200 Hz clock and the floppy driver's motor timeout. `rmw_stores` counts what went
  through the three doors (about 25,000 in a 300-frame run, almost all of them the Timer B
  acknowledge), and it is a surface rather than bookkeeping: a build that had somehow linked the
  kit's own off-target `src/hw.c` would show 0.

  **THE ADDRESS-KEYED BRIDGE THAT USED TO BE HERE IS DELETED.** Before kit commit `2db68f6` the
  cores could not express the operation, so this build recognised the five registers by ADDRESS in
  `hw_write8` and made the read-modify-write anyway, under a TEMPORARY marker. The cores spell it
  themselves now, so the bridge would be a second implementation of an operation its callers
  already name.

## The video base moved into the hardware door

M1's Unpinned 3 said a re-publish after the fact "is not a shape M2 can keep", and it is not:
`screen_flip_buffers` publishes an IMAGE OFFSET to `$ff8201`/`$ff8203` every frame, and a shim that
corrected it afterwards would leave the shifter pointed at `$0703xx` for most of every frame.

The translation is now `zynaps_backend.c`'s, at the door the core itself reaches. **The offset is
assembled across the two stores** because a byte of a sum is not the sum of a byte —
`image base + offset` carries out of bits 8-15 into 16-23 — so each call updates its half of the
remembered offset and stores BOTH translated bytes. The record carries the offset the cores last
published, the machine address it became, and how many pairs went up; `smoke.py game` refuses a run
that published fewer than one per sample.

## The frame differential

`python3 atari/smoke.py game`, TOS 1.04, both sides at the same memory size, both off a GEMDOS
drive. Re-measured 2026-09-02 at **1 MB**, after the diet (see **Memory**), and green at 4 MB in the
same sweep:

```
-- game on st / TOS104US.img at 1 MB: image base 0x23200, the original at 0xaa56
   memory: TPA [0x12496, 0xf8000) = 940906 B, image 512 KiB at 0x23200, 343428 B headroom
   to the stack, 0 tail + 0 guard byte(s) dirty
   300 frames over 1 section start(s), 1 attract pass(es), player(s) 1, section 0, 3 lives,
   score 00000000
   dispatched: 19 in-game / 904 menu / 26 attract VBLs, 903 raster + 2560 bar Timer Bs,
   1686 IKBD; 0 unknown-vector halt(s)
   samples [1, 30, 60, 120, 240]; 5152 read-modify-writes made, 1104 Timer B data restore(s)
   pacing: 2.69 vblanks/frame [2x197 4x103] = 18.6 fps (the original's 2 = 25)
   [green] exit status + log (ours)
   [green] exit status + log (the fault scan can fail)
   [green] exit status + log (the machine was handed back)
   [green] exit status + log (the original)
   [green] exit status + log (the program's own record)
   [green] hardware-state vector (TOS's 200 Hz clock survived the boot)
   [green] hardware-state vector (the pens, frame by frame)
   [green] memory (the image fitted the machine, and stayed inside itself)
   [green] timelines (the frame cadence and the interrupt service rates)
   [green] memory (the framebuffer and the entity table, frame by frame)
-- OK
```

**At frames 1, 30, 60, 120 and 240 the 32000-byte framebuffer is byte-identical, the twenty entity
records are byte-identical, and the sixteen colour registers are identical.** Not "close": zero
differing bytes at every sample, on a screen with the ship, the parallax starfield, the scrolling
terrain, the enemies and the whole status panel on it.

### What makes the two comparable

Four pins, and each was needed:

* **The frame number is the loop head's own pass count.** One `frame_loop_once` here is one arrival
  at `0x10f4e` there, so a Hatari breakpoint's hit count and the program's own counter mean the same
  thing. Sample N is the state after N passes, i.e. the original's (N+1)th arrival — `:N+1 :once`.
* **The same input.** Both sides are given the fire button, poked into the byte the ACIA handler
  writes. **The press must never reach a FRAME**, and a first draft that poked on a wall-clock timer
  did: the frame loop interrogates the controller once a frame, so a poke landing between the loop
  head and the stage's own read gave one side a shot the other did not fire — measured as a
  framebuffer differing by 12 bytes at frame 30 in one run and 24 in the next, which is a
  non-deterministic comparison and worth nothing. Each side now presses from somewhere that only
  exists inside a wait: the original from a repeating breakpoint on its own poll at `0x10f2a`, ours
  from a driver that reads the program's phase and presses only when it is not PLAYING. A repeating
  breakpoint on the loop head clears the byte on EVERY frame of both runs, so every frame's stick is
  provably neutral.
* **The same random stream, and the same entity table.** Both are pinned at the first arrival at
  the loop head and then left to EVOLVE — re-applying either per frame would hide the divergence
  this comparison is for. `rand16` runs once a pass in the attract loop and once a pass in the fire
  wait and the two sides make different numbers of both, so they would reach the game with different
  LFSR states. The entity table is the front end's scratch as well as the frame loop's, and MEASURED
  without the pin: record 0 — the one the front end draws its GUNSIGHT through — differed at five
  bytes from frame 30 onward and never moved again, because our attract loop exits after one pass
  where the original's runs on (unpinned 19). Zeroing it is not fabrication: an all-zero table is
  what a machine that had just booted holds, and it is a superset of the clearing the game's own
  `section_restart_prologue` does. It does not fix unpinned 19; it stops a front-end difference
  being reported as a frame-loop one. **It also changed the game**: with the stale gunsight gone the
  ship survives all 300 frames where it used to die at 176.
* **The entity table's sprite pointers are rebased, not skipped.** They are absolute addresses of
  the loaded program and the two programs load at different bases, so each is converted to a Ghidra
  address and compared — which is stricter than excluding them. A field that is a program address on
  neither side is a dead slot's leftover (measured: `$fc0000` here against `$fc55aa` there, both
  inside TOS's ROM) and is reported as unset rather than as a difference.

### The negative control

`build.sh gamefault` is the game build with **ONE STEP of the section chain dropped** — the two
`bsr`s at `0x1085a`, the player intro screen and the whole-panel repaint — and nothing else. A
dropped composition step is the defect this milestone is most exposed to, because the whole of M2 is
calls to verified slices and what can be wrong is the order and the set. Measured:

```
   [red ] memory (the framebuffer and the entity table, frame by frame)   (must FAIL)
           frame 1:   748 of 32000 framebuffer bytes differ
           frame 30:  748 ... frame 60: 748 ... frame 120: 748 ... frame 180: 748
   [green] hardware-state vector (the pens, frame by frame)
   [green] exit status + log  (all five)
-- OK
```

**THE FIRST CONTROL WAS MEASURED NOT TO ISOLATE ANYTHING and is recorded rather than quietly
replaced.** It bound the raster split's vector (`0x106ae`) to the plain in-game Timer B, on the
reasoning that the palette it uploads mid-screen would move the pens. Every surface stayed green:
the pens are sampled at the loop head, and whatever the split did to them has been undone by the
time the frame ends. A control that cannot go red says nothing about the checks it exists for.

## The finding this milestone is really about: the C is too slow for its own interrupt

`docs/on-target-execution.md` has no class for it, and it cost this milestone more than every other
defect together. **Attract mode's Timer B fires every TWO SCANLINES — about 1024 CPU cycles at
8 MHz — and its handler is C.** Measured by dividing the program's own `timer_b_ticks` by its
`vbl_ticks` over a five-second window:

| the handler carried | Timer B interrupts per frame | what the main line did |
|---|---|---|
| a linear-scan hardware ledger, a 15-register `movem` | far under the offered rate | two instructions a frame: twenty seconds inside an eight-iteration palette upload, the title page never drawn |
| a hashed ledger, a 15-register `movem` | the same | the same |
| **no ledger, a 4-register `movem`** | **98 of the 100 offered** | the attract loop runs, a game starts, the section reaches PREPARE FOR COMBAT |

**THE NUMBERS THAT USED TO BE IN THAT COLUMN — "79 of the frame's 156", ON EVERY ROW — ARE
RETRACTED**, and the paragraph below says why. What survives is the shape: the handler was longer
than its own period and the fixes made it shorter. The first two rows have not been re-measured
since, which is why they are described rather than numbered.

Two changes came out of that, and both are correct on their own terms as well as faster:

* **The interrupt entries save four registers, not fifteen.** The m68k SysV ABI makes
  `%d0/%d1/%a0/%a1` scratch and `%d2-%d7/%a2-%a6` callee-saved, so everything reached from the `jsr`
  has already restored the other eleven. The original's handlers save all of them because they are
  hand asm; a C handler cannot need to. 176 cycles there and back, twice.
* **There is no address-keyed hardware ledger.** M1's Unpinned 15 asked for one — a count of stores
  per register, which would subsume the three tallies keyed on arguments about today's call sites —
  and it was written twice and deleted twice. What costs is the extra CALL per hardware store, not
  the search: the hashed second draft was still over the cliff. So the shape a target build can
  afford is a fixed set of named counters, each one compare and one `addq`, and `zynaps_backend.c`
  says so where the table used to be.

**"79 OF 156" WAS WRONG IN BOTH HALVES, and re-measuring it is where the Performance section below
started.** The denominator is not 156: Timer B is in EVENT-COUNT mode, and the event it counts is
the shifter's display-enable pulse — one per DISPLAYED scanline, of which ST low resolution has 200,
not one per HBL of a 313-line PAL frame. At a period of 2 the chip therefore offers **100**
interrupts a vertical blank. And the numerator is not 79: the record now carries the bars' handler
entry count and the attract VBL's beside it, and a `game` run serves **6,263 over 64 attract
vertical blanks — 97.9 of the 100 offered, 98%.** The four-register `movem` and the deleted ledger
closed this; the figure quoted above was taken before them and never redone, and the reading that
"the bars are drawn at half density" followed from the arithmetic rather than from a screen. What
keeps it closed is `smoke.py`'s `check_the_pacing`, whose floor is 95% of the offered rate.

# THE TRAINER — the one thing here that is NOT the original

**Type `Z`, then `Y`, then `N` — one key at a time, in that order — at the title screen and the game
answers with a sound no player of the 1988 disk could ever have heard. After that, `F1` makes the
ship invulnerable, `F2` puts the lives back and `F3` maxes every power-up.**

Everything else in this directory exists to be byte-identical to a 1988 binary. This section is the
exception, asked for deliberately, and it is written so that the exception stays exactly where it
was put:

* **No core is edited.** The trainer is one new shim file, `atari/zynaps_cheats.c`, plus eleven
  lines spread over `zynaps_main.c`, `shim_include/hw.h` and `build.sh`. `make test` is unchanged at
  **4751**, and `build.sh`'s three core-containment gates — no core includes a shim header, no core
  reads a target-only `-D` (`ZY_CHEATS` is now on that list), no shim symbol collides with a core's
  — all stay green.
* **The frame differential is untouched.** `smoke.py game` still compares 32000 framebuffer bytes,
  sixteen pens and twenty entity records against the shipped binary at five frames, and still finds
  them identical.
* **It is inert until a player arms it,** and that is a MEASUREMENT rather than a claim — see "How
  dormancy is proved" below.

## The combo, and the French keyboard

| | | |
|---|---|---|
| **arm** | type `Z`, then `Y`, then `N` in order (one key at a time) | **at the title/attract screen only** |
| `F1` | toggle invulnerability | in game |
| `F2` | lives back to 9 | in game |
| `F3` | every power-up to its ceiling, seeker selected | in game |

**A TYPED SEQUENCE, not a simultaneous hold — and that is a real-hardware fix, not a preference.**
Three keys held down together can GHOST on the IKBD's keyboard matrix: the controller scans a grid,
and certain key triads share rows and columns such that a third press is never reported. On the
user's STE the simultaneous hold armed nothing. A sequence — one key down and up before the next —
touches one matrix cell at a time and cannot ghost, and it does not depend on hold timing. A wrong
or out-of-order key restarts the sequence (a misplaced `Z` restarts on that `Z`, so a fumble
followed by a clean `Z`-`Y`-`N` still arms). The sequence is refused anywhere but the title —
`zynaps_main.c`'s `title_attract_loop` opens the window around `attract_wait_for_start` and closes
it on the way out. Z, Y and N are none of the three keys that wait exits on (`1`, `2`, fire), so
typing them cannot start a game by accident.

**THE SCANCODES ARE RESOLVED AT RUNTIME OUT OF THE GAME'S OWN TABLE.** An ST keyboard sends POSITION
codes, and this build is played on a French AZERTY STE where the key labelled `Z` is not the key a
UK machine calls `Z`. The game ships exactly one table that turns a scancode into a character —
`scancode_to_char_table` @ `0x19a39`, 115 bytes, `0x00`..`0x72`, read by the high-score name entry
at `0x13164` and by nothing else — so the trainer's combo is spelt as the three CHARACTERS `'Z'`,
`'Y'`, `'N'` and `zy_cheats_resolve_scancodes` looks them up in that table once, at boot, straight
after the image is staged. The combo is therefore the letters the game itself would print for those
keys, and a localised build shipping a different table would move it without an edit here.

**...and the shipped table is a pure QWERTY map, so the lookup alone is not enough.** Measured over
all 115 bytes: `0x2c`→`Z`, `0x15`→`Y`, `0x31`→`N`, `0x1e`→`A`, `0x11`→`W` — UK/US positions, with no
layout switch anywhere in the image and no second table. On AZERTY the `Z` key sends `0x11` and
nothing in this program says so. So each combo letter accepts TWO scancodes: **the one the table
resolves, and the one the letter sits at on AZERTY** (`Z`=`0x11`, `Y`=`0x15`, `N`=`0x31`). `Y` and
`N` do not move between the layouts, so for those two the pair collapses to a single code; only `Z`
really has two, and **the cost of the fallback is that `W`+`Y`+`N` also arms the trainer on a QWERTY
keyboard.** That is a cheat combo and not a game control; being armable on both machines is worth
more than being unique on one.

`F1`–`F3` need no layout argument at all: the function-key block sends the same scancodes on every
ST keyboard. Nothing in the game reads them — the table holds `0xff` for all three, and the only
scancode comparisons in the whole program are SPACE (the pause, `0x10fda`/`0x10ffe`) and `1`/`2`
(the menu) — so a press cannot collide with a control.

## Four sounds nobody has heard since 1988

The secrets hunt (`../../README.md`, "Secrets and dead code") proved nine of the forty-five sound
streams unreachable: every one of the 23 instructions that reaches `sound_start` was followed
through the spawn, jump and swap graph, and ids **19, 23, 25, 29, 35, 37, 38, 42, 43** are in no
closure. Each is a complete stream — its own `fa <channel>` header, its own `$e1` terminator — so
each still plays as its author left it. The trainer's feedback is four of them:

| event | orphan | what it is |
|---|---|---|
| **armed** | **35** (`0x23`) | 2.0 s, `fa 03`. Channel code 3 occurs on exactly three streams and all three are orphans, which makes it the fanfare |
| `F1` invulnerability | **19** (`0x13`) | the only orphan armed on **voice 1**, so the toggle is heard over whatever the other two voices are doing |
| `F2` lives | **37** (`0x25`) | one of the pair 42/43 shadow |
| `F3` power-ups | **38** (`0x26`) | ...and the other |

They are started through the game's own verified `sound_start` @ `0x16ac8`, whose whole effect is
the image (no hardware, no trap), from the vertical blank AFTER the program's own handler has run —
so the voice rewrite lands between two ticks of the driver rather than in the middle of one. All
four carry `fa` headers, so `sound_start`'s `channel` argument is overwritten and the `0` this
build passes means "nothing was chosen".

## What each key writes, and why those bytes

Every address below is a core header's and every ceiling is the game's own — `zynaps_cheats.c`
chooses no number except the life count.

**`F1` — invulnerability.** `A_ship_invulnerable` @ `0x19912`, toggled 0/1. It is a **dormant flag
the author left wired up and never set**: three sites read it — the two landscape collisions at
`0x11e66`/`0x11eb2` and the lethal entity touch at `0x13d0e` — and *nothing in the shipped image
writes it* (`names.txt` carries the exhaustive walk). Non-zero suppresses all three.

**`F2` — lives.** `A_lives` @ `0x1991a` = 9, plus `bset #4,$19904` through the game's own
`panel_request_repaint`. Bit 4 is the odd one of the five panel bits: the frame head has no `bclr`
for it because `draw_lives_icons` clears it itself once it has drawn, so asking here is exactly what
the extra-life award at `0x12e36` does. **The icon row is six wide,** so nine lives draw six full
icons and the other three are real but off the panel. Nothing above `0x7f` may ever go in this byte:
`life_icon_for_slot` reads it SIGNED, so `0x80` and up draw six EMPTY icons over a full stock.

**`F3` — power-ups.** The five commit arms of `../src/weapon.c`, at their ceilings, in one go:

| byte | value | where the ceiling comes from |
|---|---|---|
| `A_weapon_power_level` `0x19908` | `WEAPON_POWER_LEVEL_MAX` = 4 | `cmpi.b #$4` + `ble` @ `0x13f1e` |
| `A_shield_level` `0x1990a` | `SHIELD_LEVEL_MAX` = 3 | `cmpi.b #$3` + `ble` @ `0x13f4a` |
| `A_power_gauge_display` `0x198c3` | = the shield level | `powerup_upgrade_shield` writes the pair together @ `0x13f5e` |
| `A_selected_weapon` `0x198b4` | `WEAPON_KIND_SEEKER` = 4 | the fire dispatcher's `cmpi.b #$4` @ `0x113d0` |
| `A_ship_speed_level` `0x19907` | `SHIP_SPEED_LEVEL_MAX` = **1** | see below |
| `A_weapon_decay_timer` `0x19dcc` | `POWERUP_DECAY_TICKS` = `0x3e8` | `move.w #$3e8` @ `0x13ede` |
| `A_shield_decay_timer` `0x19dca` | `0x3e8` | @ `0x13e9e` |
| `A_speed_decay_timer` `0x19dc8` | `0x3e8` | @ `0x13dd0` |

...plus panel bits 0, 1 and 2.

**THE THREE DECAY TIMERS ARE UNPINNED ON TARGET, and that is a measurement rather than an
oversight.** Nothing outside the program can tell their refill from the section start's: they tick
down once a frame AND `section_restart_prologue` has just set them to the same ceiling, so a value
read a few frames after the press is a few short of full either way — measured at 967/966/964
against 1000, from a run in which all three writes had landed. A counter the SHIM kept is no better,
and a draft of this carried one: it read the three words back through the same `A_*_decay_timer`
expressions that had just written them, so it returned 3 for every possible defect *including the
wrong-address one its own failure message named*. It was deleted rather than reworded. What stands
behind these three is the header scrape (the addresses are the ones `../src/weapon.c`'s commit arms
use) and `make test`'s verification of those arms — not an on-target surface.

**THE SPEED LEVEL'S REAL CEILING IS 1, NOT 8, and the "eight levels" in `STATUS.md` is eight
differential TEST CASES rather than eight game levels.** `A_ship_speed_table` @ `0x19370` holds
exactly two eight-byte entries (dx 4 / dx 8) and what follows the second is a relocated pointer, so
a level of 2 indexes out of the table and flies the ship at a garbage delta. The capsule's own arm
cannot be borrowed as a bound either: unlike the other two its clamp is an EQUALITY (`cmpi.b #$2` +
`bne`), so a byte already past 2 walks straight on, unclamped, for ever. `SHIP_SPEED_LEVEL_MAX` is
the value that arm writes back and it is the highest this may ever be.

**THE THREE LAUNCH-STOCK COUNTERS ARE DELIBERATELY NOT POKED.**
`A_missile_launch_counter`/`A_bomb_launch_counter`/`A_seeker_launch_counter` (`0x198b5`/`6`/`8`) are
written by the section restart and decremented by the three launchers, and **nothing in the image
reads one** — no branch anywhere tests them, and `0x198b8` is never even initialised. What actually
bounds firing is the in-flight count, which the two levels above already max. Poking them would look
like an effect and be none.

**The levels decay.** All three step down when their timer reaches zero (`frame_decay_timer`, about
a thousand frames), and a death takes one off each. `F3` again is the answer; the trainer does not
freeze a timer the game means to run.

## Where the code is, and why it is split in two

| | |
|---|---|
| `atari/zynaps_cheats.c` / `.h` | the whole trainer: the watcher, the state machine, the three pokes |
| `shim_include/hw.h` | four lines in `hw_read8` — the ACIA-data tap, UNCONDITIONAL (see below) |
| `zynaps_main.c` | the include, the record fields, `zy_cheats_tick()` in the VBL, the two windows, the boot-time scancode resolve |
| `build.sh` | the new object, `-DZY_CHEATS`, `ZY_CHEATS` on the target-macro list, the `cheats` mode |
| `smoke.py` | the dormancy check in every mode, and the `cheats` mode that arms it |

**THE BYTE CAN ONLY BE SEEN AT THE ACIA.** Reading the 6850's data port POPS it, so the byte the
keyboard sent exists for exactly one read and `ikbd_acia_isr` makes it. A watcher could not read the
port again afterwards, and it could not read the keys out of the image either: the program keeps ONE
byte, `A_key_scancode` @ `0x19685`, holding the key currently down and overwritten by the next press
and cleared by its own release — so a watcher reading it from the VBL would miss presses that came
and went between two frames, and the sequence needs to see every press at the instant it lands.
Hence the tap in `hw_read8`, declared in `hw.h` rather than included, exactly as
`zy_store_video_base_byte` is, so that no shim header reaches a verified core.

**THE TAP IS UNCONDITIONAL, and that is what keeps the divergence out of the cores.** A first
draft wrapped it in `#ifdef ZY_CHEATS`, and `build.sh` passes its `-D`s to the CORE compile — so
`../src/irq.c`'s `ikbd_acia_service_one_byte`, a differential-pinned core, would have compiled to
different machine code in the default build and in the purist one. `make test` never compiles this
header, so it could not have seen the difference; and the gate written for exactly that risk greps
`../src` and `../include` for the macro name, which a *shim header* is not — the gate would have
printed green over the one case its own comment cites. So the call is always emitted, the purist
build links the empty body in `zynaps_cheats.c`'s `#else` arm, and `ZY_CHEATS` reaches no verified
translation unit at all. What that costs the purist build is one `bsr`+`rts` per IKBD byte, about
three bytes a frame, in the build nothing measures.

**It costs nothing anywhere else.** Every caller of `hw_read8` passes a CONSTANT address, so the
comparison folds at compile time: `ikbd_send_cmd`'s status poll, the handler's GPIP test and
`zynaps_main.c`'s four MFP read-backs emit the bare `move.b` they always did, and only the one site
that reads `$fffffc02` keeps the call.

**WHAT IT COSTS, COUNTED OFF THE BINARY** (`build/zynaps-game.elf`, 68000 cycles):

| path | when | cycles |
|---|---|---|
| `zy_cheats_tick`, disarmed | every vertical blank | ~130 — `tst.b g_armed`, `tst.b g_arming_window_open`, clear the pending byte, return |
| `zy_cheat_note_ikbd_byte`, joystick payload | 2 bytes a frame | ~150 each — `tst.b A_ikbd_packet_remaining` and out |
| ...the packet's `0xfd` header | 1 byte a frame | ~165 — two compares and out |

That is about **800 cycles a frame** against the ~400,000 a 2.5-vblank frame has, or **0.2 %**.

**Measured on the pacing surface: 2.52 vblanks/frame before the trainer; 2.53 and 2.54 over three
runs with it, against a ceiling of 2.64.** The whole movement is one or two frames of 300 changing
bucket (`2x222 4x78` → `2x221 4x78 5x1` → `2x220 4x79 5x1`), which is the run-to-run spread the
ceiling was set with — the same binary produced 2.53 and 2.54 on consecutive runs.

**THE WORK IS SPLIT ACROSS TWO INTERRUPTS.** The ACIA door does the least possible — advance the
arming sequence's cursor by one press, and latch one bit per cheat key — because it is entered once
per byte from inside the keyboard interrupt. The state machine (arming on a completed sequence,
jingle, pokes) runs from `zy_cheats_tick`
in the vertical blank, after the program's own handler. MFP channel 6 is level 6 and the vertical
blank is level 4, so the keyboard can interrupt the tick but never the reverse; every store either
one makes into the trainer's OWN state is a single 68000 instruction, and the pending-key byte is a
`bset`/`bclr` pair rather than a read-modify-write so that a key pressed between the tick's read and
its clear is not lost (measured in `build/zynaps.dis`: `or.b #imm,<abs>` and `and.b #imm,<abs>`).

**THAT ARGUMENT IS ABOUT THE TRAINER'S BYTES AND NOT ABOUT THE IMAGE'S, and the difference is a
residual worth stating.** The pokes write bytes the MAIN LINE read-modify-writes over several
instructions — `frame_decay_timer` does `wr16(t, be16(t) - 1)` and then steps a level — and the
vertical blank preempts the main line. `F3` pressed on the one frame the shield timer is being
stepped can be partly undone: the shield lands at 2 rather than 3 until the next press. It cannot be
fixed from the trainer's side (it *is* the interrupt, not the thing being interrupted), and the
window is a few instructions out of the ~400,000 cycles a frame takes, so it is recorded here rather
than papered over. Pressing the key again is the whole of the workaround.

## How dormancy is proved

The frame differential compares two programs PLAYING and finds them identical, which says the
cheats changed nothing over a run in which nobody pressed a key. It cannot say the watcher was
quiet. So the record carries the trainer's own account of itself, and:

* **`smoke.py title`, `titlefault`, `floppy`, `game` and `gamefault` each assert
  `check_the_trainer_stayed_dormant`** — `cheats_armed`, `cheat_arm_jingles` and the three fire
  counts all 0, plus the combo's resolved scancodes against smoke.py's own reading of the same 115
  table bytes. `cheats_built` is CROSS-CHECKED rather than required: the ELF is asked whether the
  watcher's data is in it and the program's own claim must agree, which is what makes `ZY_NOCHEATS=1`
  a build this matrix can judge instead of one that reds by construction.
* **HOW MUCH THAT PROVES DEPENDS ON THE MODE, and it is worth being exact.** In `game` and
  `gamefault` the attract loop really does open the arming window and the ACIA vector really is the
  program's, so the watcher runs and the zeros are a measurement. In `title`, `titlefault` and
  `floppy --floppy-build title` the whole `#if ZY_PHASE == ZY_PHASE_GAME` block is compiled out —
  with it BOTH window setters and the store that installs the game's ACIA vector — so the watcher
  cannot fire whatever the keyboard sends. There the check is a **regression net** (a trainer that
  had started poking from the boot, or from an M1 code path, would show) rather than a dormancy
  proof, and the scancode comparison is the part of it that measures something in every mode.
* **`smoke.py cheats` is the positive control**, and without it those five assertions would be a
  check on code that could not fire at all. It drives the combo and the three keys through
  **Hatari's own keyboard** (`hatari-event keydown`/`keyup`, one make code and one break code each)
  — the real path: 6301 → ACIA → MFP channel 6 → `ikbd_acia_isr` → the tap. Nothing about the
  trainer is poked into place; only the FIRE button still is, because Hatari swallows a key bound to
  its joystick emulation, and fire is not what that mode judges.

What `smoke.py cheats` asserts, in the order the run produces it:

1. **two arming negatives** — a wrong/fumbled sequence (`Z`, `Y`, `Z`, `N`) and an incomplete one
   (`Z`, `Y` and stop), each typed at the title: `g_armed` read live off the machine is still 0
   after both;
2. **the positive** — `Z`, then `Y`, then `N` typed in order: it arms, once, and the fanfare's
   stream pointer read back out of voice 3's record equals what smoke.py's own port of
   `sound_lookup_tune` predicts for orphan 35;
3. **the in-game refusal** — `g_arming_window_open` is 1 at the title and 0 inside the frame loop;
4. **the six bytes the three keys write**, each read back off the running machine at the address
   its header names — plus the panel bits, which nothing outside could sample (the frame loop clears
   each one as it repaints, within a frame) so the shim reads the mask back through the game's own
   `panel_request_repaint` and keeps only the bit it asked for. The three decay timers are **not**
   checked and the paragraph above says why;
5. **invulnerability as a BEHAVIOUR** — a neutral-stick life ends at about frame 176; with `F1` on
   the run passes frame 400 still on its first life, and then `F1` is pressed AGAIN and the same
   ship in the same run dies. The second half is what makes the first half mean anything.

**The gate's own coverage, mutation-tested** (each applied alone, built, and the named mode run):

| mutation | mode | verdict |
|---|---|---|
| the cursor advances on a WRONG letter, not only the expected one | `cheats` | KILLED — "a wrong/fumbled sequence (Z, Y, Z, N) armed the trainer" |
| a wrong letter does NOT reset the cursor (so a fumbled order still arms) | `cheats` | KILLED — "a wrong/fumbled sequence (Z, Y, Z, N) armed the trainer" |
| the arming jingle is counted twice | `cheats` | KILLED — "the record says armed=1, jingles=2 — one arming, once, was asked for" |
| `zy_cheats_arming_window(0)` a no-op, so the window never shuts | `cheats` | KILLED — "the arming window was still open inside the frame loop" |
| `F2` acts but its fire count is not incremented | `cheats` | KILLED — "cheat_lives_fires is 0, and 1 key press(es) reached the machine" |
| the trainer arms on the first attract vblank with no keys pressed | `game` | KILLED — "the trainer fired in a run that pressed none of its keys" |

The last one — the only `game` row — is the one that matters most: it is the DORMANCY check going
red, which is what says the five zeros every other mode prints are a measurement rather than a shape
that cannot fail. (It arms on the first vblank with no input at all, rather than on a typed sequence,
because a `game` run spends only 26 vblanks in the attract loop and never types the letters — a
mutation that still required the sequence would have survived for want of input rather than for want
of a check.)

**THE PSG TRACE IS NOT THE JINGLE'S SURFACE, and it cannot be.** `smoke.py` traces `psg_write` and
cuts it into the sound driver's own tick frames, but the title tune is driving all three voices at
the moment the fanfare starts and no register write in that window is the jingle's alone. What IS
exact is the voice record: `sound_start`'s whole effect is those eight image stores, the shim reads
the restart pointer back immediately (the cursor moves every tick, so nothing outside could sample
it) and the record carries it. That is a stronger surface than a trace scrape, not a weaker one.

## Building it, and the purist path

`-DZY_CHEATS` is **on by default in every mode**, and that is what makes the dormancy checks worth
anything: the binary `smoke.py title`/`game`/`floppy` judges is the same binary a player gets,
watcher and all. A build carrying the cheats only in the mode that exercises them would be proving
dormancy of code that was not there. **One floppy**, and it carries the dormant watcher.

```bash
bash atari/build.sh cheats && python3 atari/smoke.py cheats   # the positive control
ZY_NOCHEATS=1 bash atari/build.sh play                        # the purist binary
```

`ZY_NOCHEATS=1` is an environment variable, not a mode — `build.sh`'s `case` would reject one. It
compiles `zynaps_cheats.c`'s empty arm, so the watcher, the key table and the pokes are **absent**
from the binary rather than disarmed. The tap's *call* in `hw_read8` stays (see above): that is what
keeps the verified cores compiling identically in both builds. `smoke.py` tells this build's zeros
from a dormant trainer's by asking the ELF for the watcher's own data, so the purist binary is
judgeable by the same matrix rather than red by construction. It is a define path and not a second
disk.


# PERFORMANCE — the frame cadence, measured against the shipped binary's own

**The port computes the right bytes and takes about 1.5 times as long to do it — it used to take
three.** The frame differential above is byte-identical; this section is the other question, asked
with the same discipline: both binaries, on one machine, through one instrument, over a window of
the same length.

> **THE VERDICT AT THE FOOT OF THIS SECTION USED TO SAY THE CAMPAIGN WAS CLOSED, AND IT WAS
> WRONG.** It closed on a mean, and the residual it could not account for was hiding in a place a
> mean cannot look: a cost that scales with HOW MANY ENTITIES ARE ON SCREEN. The user's report was
> never "the game is slow" — it was "**it slows down when there are a lot of sprites**", which is a
> claim about the distribution's tail. Wave E built the instrument that can read that tail
> (`atari/census.py` + `atari/bench_tier.py`), found **+41,056 cycles a busy frame** in the one
> frame slice nobody had twinned, and collected ~36,000 of them. See **The heavy frame** below,
> which is now the section's centre of gravity; the mean-based tables that follow it are kept
> because they are still true about means.

**The scroll path is done, and so are the sprite and text paths.** Wave A transcribed the twenty page
blits, the two column emitters and the tile emitter — 28%, 16% and 7% of the pre-twin profiler
window's frame at 2.19x, 5.34x and 4.49x the original's cost — into `../src/asm/` at 1.07x-1.09x,
which took the cadence from a mode of 6 vertical blanks to a mode of 4. **Wave B did the same for
`draw_sprite_masked_collide` (0x15b7c) at 2.45x, `draw_score_panel` (0x136c8) at 2.77x and the
character blitter it ends in**, and the mode moved again, 4 to **2**: most of the judged run is now on
budget. **Wave C twinned the frame loop's LAST SLICE** (0x11d30..0x1296e, `../src/asm/frame.S`, the
first twin in this project that CALLS — sixteen C cores through the kit's callback door), which took
the judged cadence from 2.80 to **2.67**, 18.7 fps against the original's 25.
`../src/asm/README.md` is the recipe all three waves followed and carries what each added to it —
including wave C's warning that the profiler row which commissioned it was ~95% busy-wait, so its
real prize was ~19,500 cycles a frame and not the ~140,000 the row implied.

```bash
python3 atari/profile.py frames             # OUR cadence: vblanks per frame, work, wait
python3 atari/profile.py original-frames    # ...the shipped binary's, the same way
python3 atari/profile.py ours               # OUR per-symbol cycles over 1000 vblanks
python3 atari/profile.py original           # ...the shipped binary's, from names.txt's symbols
python3 atari/profile.py compare            # both profiles read back and ratioed
```

...and the two tools wave E added, which answer the question `profile.py` structurally cannot —
**what does one BUSY frame cost, routine by routine, on both sides?**

```bash
# stage the busiest frame the oracle plays into, and a light one for contrast
python3 atari/census.py 0 300 0 atari/out/heavy.img atari/out/light.img
# ...then price every stage and tier routine on those frames, ours against the original
python3 atari/bench_tier.py atari/out/heavy.img atari/out/light.img
```

`census.py` walks the ORACLE playing a real section frame by frame, reports each frame's entity
load, and saves the busiest image it sees (and the lightest that still draws). `bench_tier.py` runs
both sides over that one image under Musashi — the original's own machine code through `emu.run`,
and ours as the cross-compiled `atari/build/zynaps.elf` through `emu.run_bench`. One image, one
instrument: no window, no mixture, and no average. It prices **what the game calls**, resolving a
shipped twin's `<core>_asm` out of the linked ELF and marking those rows `[twin]`.

**Use these, not a profiler row, to scope a twin** — `src/asm/README.md`'s "What wave E added" is
why, and "THE HEAVY FRAME" below is what they found.

## THE HEAVY FRAME — the measurement the mean could not take

**The instrument.** `atari/census.py` walks the ORACLE playing the real game frame by frame and
saves the busiest image it sees; `atari/bench_tier.py` then prices every frame stage and every
routine of the enemy/actor/projectile tier on THAT one image, both sides, under Musashi. The
original runs its own machine code (`emu.run`); ours is `atari/build/zynaps.elf` — the exact code
inside `ZYNAPS.PRG`, twins and all — loaded at its link addresses and entered through
`emu.run_bench`. One image, one instrument, no window and no mixture. (The precedent is
`projects/buggyboy/recreate/tools/bench_frame.py`; nothing in the method is new but the game.)

The staged busy frame is section 0, frame 141 of the oracle's own play: **14 live entities with all
eleven actor slots full** — eight wave enemies, three enemy shots, three explosion particles.

**The frame's spin-free stages, before and after wave E.** A release slot is 320,000 cycles (two
vblanks at 8 MHz), and that is the budget a frame either fits or misses.

| stage | the original | ours, before | ours, after | after/original |
|---|---|---|---|---|
| `frame_panel_scroll_and_ship_stage` (waves A/B twins inside) | 143,316 | 144,502 | 144,502 | 1.01x |
| `frame_spawn_and_move_stage` | 19,924 | 38,574 | 38,574 | 1.94x |
| **`frame_draw_objects_and_collide`** | **91,038** | **132,094** | **96,436** | **1.06x** |
| **total** | **254,278** | **315,170** | **279,512** | **1.10x** |
| the excess, as a share of a release slot | — | **+60,892 = 19.0%** | **+25,234 = 7.9%** | |

`frame_drone_and_fire_stage` HAS NO ROW ON THIS FRAME, and that is the frame rather than the table:
the head slice's own gate branches straight past it when the ship record is dead, which it is here.
An earlier edition of this table entered the stage anyway and reported 498 cycles against 256 — a
stage that did not happen, folded into both totals. `bench_tier.py` now skips a stage the frame's
gates skip and says so.


**The quiet frame moved too**, and by less, which is the check that the fix is where the diagnosis
said: its stage went 32,720 -> 24,970 (1.42x -> 1.09x) and the whole spin-free frame +13,274 ->
**+5,524** (1.07x -> **1.03x**). A change that had helped both frames equally would have been fixing
something other than the per-entity term.

**AND THAT IS WHY THE HEAVY FRAME MISSED ITS SLOT.** The fifth slice costs the original 9,866 cycles
on this frame (measured on the oracle with the waits released; ours is wave C's shipped twin at
~1.03x), so the whole frame's work is:

| | work on the busy frame | share of the 320,000-cycle slot | vblanks |
|---|---|---|---|
| the original | ~264,100 | 83% | 2 |
| ours, before wave E | ~325,300 | **101.7% — missed** | 4 |
| ours, after | ~289,700 | **90.5% — fits** | 2 |

**We were missing the slot by under 2%, and the untwinned slice held six times that.** Note the
shape of it: the *mean* said we were 1.53x the original and implied a hopeless 138,000-cycle gap;
the busy frame said we were 1.8% over a threshold. Those are the same port.

**Where the busy frame's 41,056 cycles were, measured part by part rather than inferred:**

| part of `frame_draw_objects_and_collide` | ours | the original | excess |
|---|---|---|---|
| `asteroids_draw` x1 | 1,330 | 932 | +398 |
| `draw_sprite_masked_collide` x14 (wave B's twin) | 75,376 | 71,164 | +4,212 |
| `object_pair_overlap_mark` x51 | 15,520 | 11,040 | +4,480 |
| **the stage's own loops and call glue** | **39,868** | **7,902** | **+31,966 (5.05x)** |

The last row is the whole finding. The original's inner pair walk is six instructions and a `bsr`,
keeping its four cursors in address registers; the C re-derives `entity_record()` and
`collision_row()` per iteration and makes a **seven-argument C call fifty-one times a frame**.
`src/asm/frame_draw.S` transcribes the slice with `object_pair_overlap_mark` as an in-blob `bsr`
target — wave B's `draw_char` shape, 18 cycles and no marshalling — and lands the whole stage at
**1.06x**, +5,398 cycles.

**TWO NUMBERS FOR THE TWIN ON THIS FRAME, AND BOTH ARE RIGHT.** The table above says **96,436**; the
cost bar in `../test/test_asm_frame_draw.py` says **95,146**. Same frame, same original, same C —
the 1,290-cycle difference is the CALLBACK DOOR. Off target the twin's `jsr asteroids_draw` stops
the run and the harness calls the host C, which costs the emulated machine nothing; the bench runs
the target ELF, where that `jsr` is a real call into real m68k. The suite's number is therefore the
twin's own instructions and the bench's is what the machine executes. Neither is stale, and moving
either to "reconcile" them would be wrong.


**THE +4,108 THAT IS LEFT IS THE SPRITE SEAM, AND IT IS THE NEXT LEVER RATHER THAN A DEFECT.** It is
~295 cycles a call over fourteen calls (and +2,544 over eight on a quieter frame, which is what says
it is per-call): `draw_sprite_masked_collide_asm` carries a C signature, so the new twin's
trampoline turns two pointers into image offsets and that twin's prologue turns them straight back
into pointers. Closing it needs a second, register-ABI entry point in `sprite.S` — a change to a
shipped and pinned twin, deliberately not made in this wave.

**THE SPRITE PATH ITSELF IS DONE.** `draw_sprite_masked_collide` is **1.06x over fourteen real
calls** on the busy frame. Whatever is left in this game, it is not in blitting.

**TWO CAVEATS, AND BOTH MAKE THE REAL MACHINE WORSE THAN THE TABLE.**

* **These are MUSASHI cycles.** Hatari's model carries the ST's bus contention and reads the same
  twins 1.03x-1.08x where Musashi reads 1.00x-1.01x, so on iron the pre-wave-E heavy frame missed
  its slot by somewhat more than 1.8%, and the post-wave-E margin is thinner than 9%. The
  DIRECTION and the ~36,000-cycle recovery are instrument-independent; the headroom is not.
* **Nothing here has run on the user's STE.** The evidence that the fix reaches a player is the
  game smoke's own histogram, below — emulated, not iron.

## Why the number that matters is VBLANKS PER FRAME and not a frame rate

`frame_end_and_flip` (`../src/frame.c`) ends by waiting on `A_vbl_wait_flag`, and the handler that
clears it is `vbl_menu` (`../src/irq.c` @ 0x13c26), whose raster phase counts up and **wraps at 2**.
So the frame loop is released on every SECOND vertical blank and nothing releases it in between: a
frame that fits its budget takes exactly 2 vblanks, and one that overruns by a single cycle takes 4.
**The cadence is quantised**, a mean is a mixture rather than a rate, and the DISTRIBUTION is the
finding. That is also why `smoke.py` carries a histogram and not an average.

## The measurement, original against ours — THE CAMPAIGN'S CLOSING TABLE

Both sides by `atari/profile.py frames` and `... original-frames`: the same `play` binary pair, the
same session, the same tree, each clocked from the frame loop's head to `screen_flip_buffers` by two
repeating `:quiet` breakpoints that cost the emulated machine nothing. `st` / `TOS104US.img`.
The table's figures were clocked at 4 MB; `profile.py` runs at whatever `smoke.MEMSIZE_MB` says,
which is 1 MB since the diet — **Memory** measures that the cadence does not move with it.

| | the original | ours | ratio |
|---|---|---|---|
| frames clocked | 531 | 524 | |
| vblanks per frame, mean | **2.075** | **3.294** | 1.59x |
| the distribution | `2x510 3x2 4x19` | `2x185 4x339` | |
| the mode, and its frame rate | **2 = 25 fps** | **4 = 12.5 fps** | |
| frames on budget (2 vblanks) | 510 of 531 (**96.0%**) | 185 of 524 (**35.3%**) | |
| work cycles a frame, mean | **261,383** | **400,058** | **1.531x** |
| ...min / max | 205,488 / 480,688 | 235,280 / 485,988 | |

**READ "work" WITH ITS CAVEAT, because it is the same one that mis-scoped two waves.** `work` is
clocked from the loop head to the buffer flip, and the frame's RASTER-PHASE SPIN sits inside that
span — so any frame that missed its release slot has its measured work inflated by the wait for the
next one. The number is an upper bound on real compute, not a compute figure, and the excess over
the original is smaller than 138,675 by however much of that spin our slower frames sit through.
That is why the DISTRIBUTION, not the mean, is what this table is really about.

**THE BUSY STRETCH, RE-TAKEN AFTER WAVE E**, both sides, same instrument, same 600-frame `play`
window. This is the table that answers the user's report, because the `play` build runs on into the
part of the section where the waves arrive:

| | the original | ours, before wave E | ours, after wave E |
|---|---|---|---|
| frames clocked | 532 | 563 | 564 |
| vblanks per frame, mean | **2.079** | **3.306** | **2.926** |
| the distribution | `2x510 3x2 4x20` | `2x196 3x1 4x364 5x2` | `2x304 4x258 5x2` |
| frames on budget (2 vblanks) | 510 (**95.9%**) | 196 (**34.8%**) | **304 (53.9%)** |
| work cycles a frame, mean | 261,459 | 404,988 | 357,967 |

**The share of frames that fit the release slot went from a third to over half** — 196 to 304 of
~564, +55% — which is the same effect the busy-frame table above predicts and is the closest thing
to the user's own experience that this workspace can measure. The mean work fell by 47,021, which is
MORE than the ~36,000 the twin actually saves: a frame that now fits its slot also stops paying the
raster spin the "work" span includes, so that figure flatters the change and the 36,000 is the
honest one.

**The judged figure is the `game` build's own 300-frame record**, a different and kinder window:
**2.51-2.52 vblanks a frame, 19.8-19.9 fps** — from **2.68, `[2x199 4x101]`**. That is TWENTY
completed `game` and `gamefault` runs across three full matrix sweeps and three standalone ones,
spanning 754 to 757 vblanks over 300 frames; the histograms run from `[2x223 4x77]` through
`[2x222 3x1 4x77]` to `[2x222 4x78]`, and the worst frame any run produced was five vblanks. **The
overrunning frames fell from 101 of 300 to 76-78**, and no correctness surface moved — the frame
differential is zero bytes on every sampled frame, as it was. `smoke.py`'s
`PACING_MEAN_CEILING_VBLS` tightens from 2.81 to **2.64** on that sample (the worst run's 757
vblanks plus the file's standing 36, rounded DOWN).

**THE CAMPAIGN, WAVE BY WAVE:**

| wave | what it twinned | judged cadence | fps |
|---|---|---|---|
| before any twin | — | 5.73 | 8.7 |
| A | the scroll path | 3.75 | 13.3 |
| B | the sprite and text paths | 2.80 | 17.9 |
| C | the frame loop's last slice | 2.67 | 18.7 |
| D | the three slices before it — NOT SHIPPED | 2.68 | 18.7 |
| **E** | **the draw/collide slice — the one nobody had** | **2.51-2.52** | **19.8-19.9** |

Wave D's three twins are **verification-only**: measured at **+13 cycles a frame** by an A/B on one
tree (403,947 with them off, 403,960 on), so the game keeps the C and the twins stay as the
measurement. `include/frame.h`'s seam block and `STATUS.md`'s wave-D section carry the decision.

**Wave E's one twin SHIPS**, and the contrast with wave D is the lesson rather than the numbers:
699 instructions bought 13 cycles, 86 instructions bought ~36,000 on a busy frame. Wave D twinned
what an inclusive profiler row pointed at; wave E measured what a busy frame costs and twinned that.
`src/asm/README.md`'s "What wave E added" has the method, and the rule it adds to wave D's:

> An inclusive row is not a prize — **and a MEAN is not a distribution.** Ask which frame the row is
> an average of before concluding a routine is small.

## The per-tier attribution of what is left

`atari/profile.py compare`, ours over a 1000-vblank window against the shipped binary's.

Every row re-taken on the binary that SHIPS (the verification-only build), so the table has one
provenance throughout.

| tier | ours/call | original/call | ratio | standing |
|---|---|---|---|---|
| `scroll_page_to_screen_p*` (wave A) | 118,495 | 111,761 | **1.06x** | twinned |
| `scroll_emit_column_shift2` (wave A) | 32,992 | 31,599 | **1.04x** | twinned |
| `draw_score_panel` (wave B) | 17,088 | 16,495 | **1.04x** | twinned |
| `draw_char` (wave B) | 1,959 | 1,772 | **1.11x** | twinned |
| the frame loop's last slice (wave C) | — | — | 1.02-1.04x | twinned, shipped |
| the other three slices (wave D) | — | — | — | twinned, **not shipped**: +13 cyc |
| `enemies_move_all` | 12,982 | 2,848 | **4.56x** | un-twinned |
| `actor_script_run` | 1,989 | 611 | **3.26x** | un-twinned |
| `enemy_move_scripted` | 2,293 | 823 | **2.79x** | un-twinned |
| `enemies_animate_all` | 3,231 | 1,171 | **2.76x** | un-twinned |
| `screen_flip_buffers` | 1,291 | 196 | **6.59x** | un-twinned, ~1,100 a frame |
| `ikbd_send_cmd` | 7,887 | 84 | 94.2x **in this window** | **1.000 send/frame both sides in-game** |

**`ikbd_send_cmd` is resolved and is not a lever — and its row above is left in to show the trap.**
It reads as 4,981 calls to the original's 105 at 7,887 cycles a call against 84, which is the largest
discrepancy anywhere in the profile and is an ARTEFACT OF THE WINDOW, not a fact about the code. Measured per
PHASE, with a third breakpoint on the send site over the same 300 frames, it is **exactly one send
per frame on both sides** (315/315 and 336/336): the frame loop has one call site each, and the
whole apparent gap was a profiling window that was nearly all attract on our side and nearly all
gameplay on the original's. Window mixing, a third time. What remains is a wait-phase cadence
difference (795 sends a vblank against 83, while the game waits for the player to press fire) with
no instruction-level difference found and no observable consequence; `STATUS.md` records it against
the `attract_wait_for_start` residual that already scopes the per-phase counter.

## The verdict — and the one this section used to carry, which was wrong

**THIS SECTION PREVIOUSLY SAID "the campaign closes here" AND IT SHOULD NOT HAVE.** It is worth
recording exactly how a careful, well-instrumented conclusion came out wrong, because nothing in it
was sloppy:

* it read the gap off a **mean** — 138,675 cycles a frame, 400,058 against 261,383;
* it accounted for that mean honestly, as enemy tier (~14,400) + emulator-model residual + nothing
  from ikbd;
* and it concluded that no remaining candidate cleared the "worth writing asm for" floor.

Every number was right. The conclusion was wrong, because **a mean cannot see a cost that scales
with what is on screen**, and the user's report was precisely about that: *it slows down when there
are a lot of sprites*. `frame_draw_objects_and_collide` averaged small and cost **+41,056 cycles on
a busy frame** — 12.8% of a release slot, in the one frame slice no wave had twinned. The old
verdict's own "~14,400 a frame" for the enemy tier is the same artefact: on a busy frame that tier
is +19,992, and the stage above it was never in the list at all.

> **The lesson, and it is the wave's real product: an average over frames is the wrong instrument
> for a complaint about frames.** Before declaring a performance campaign closed, price the work on
> the busiest state the game itself produces. `atari/census.py` + `atari/bench_tier.py` do that in
> about a minute, and they did not exist when the campaign was closed.

**WHERE IT STANDS NOW.** After wave E the busy frame's spin-free stages are **1.10x** the original's
(279,512 against 254,278, +25,234 = 7.9% of a release slot, from +60,892 = 19.0%), the judged cadence
is **2.51-2.52** against the original's 2.075, and **53.9%** of the busy stretch fits its release slot
against 34.8% before. What is left, measured on the busy frame rather than averaged:

* **The enemy/actor tier: +19,992 cycles**, of which `enemies_move_all` is +13,214 and the script VM
  under it +10,256. It is the largest remaining item and **it CANNOT be twinned** — see below.
* **The sprite seam: +4,108**, the C ABI between `frame_draw.S` and `sprite.S`. A register-ABI entry
  point in the latter closes it; that is a change to a shipped, pinned twin and is scoped, not done.
* **`frame_spawn_and_move_stage`'s own +18,650**, which is mostly the enemy tier inside it.
* **The emulator-model residual**, unchanged and still not a lever: the twins are 1.00x-1.01x on
  Musashi and 1.03x-1.08x under Hatari, and that difference is the emulator's timing model of the
  original's own instruction sequence, not something in the code to remove.

**WHY THE ENEMY TIER CANNOT BE TWINNED, and this is a property of the recipe rather than of effort.**
Both actor passes and the script VM dispatch through a table of code addresses **held in the image**:

```
01489a: lea $19380.l,a0          | the per-type handler table, IN THE IMAGE
0148ac: movea.l 0(a0,d1.l),a0    | ...one of the ORIGINAL's own code addresses
0148b4: jsr (a0)                 | ...jumped to directly
```

Those are the 1988 binary's own addresses; our handlers are at our link addresses. Transcribing
`jsr (a0)` faithfully would jump into the loaded image and execute the original's machine code. So
every such dispatcher needs a lookup the original does not have — which is exactly what the C
already spells (`run_actor_handler`, `run_script_arm`: a linear scan over an address map) — and a
twin would be measured against the lookup's cost, not the original's `jsr`. **The 1.00x-by-
construction warrant does not hold there, and "do not improve on the original" forbids a twin
quietly substituting a cleverer dispatch.**

That makes the tier's excess a **dispatch problem, not a transcription problem**, and it explains
why it reads 2.4x-4.2x while every twinned routine reads 1.0x. The legitimate lever is an O(1)
dispatch **in the C** — a change to a translation that was always ours, since the original has no
such scan — with the same differential and no asm. It needs its own decision; `STATUS.md` carries
it as the named next lever, unstarted.

**THE FLOOR FOR "worth writing asm for" STILL STANDS, with one correction to how you apply it.** A
trampoline costs ~150 cycles a site and wave D's 699 instructions moved 13 cycles, so a candidate
must clear several thousand cycles **as a remainder**, every child subtracted by measurement. What
wave E adds is *which frame you take the remainder on*: measured on a mean, wave E's slice cleared
nothing; measured on a busy frame, it cleared 36,000 — and its 86 instructions are the cheapest twin
in the directory.

## Where the cycles go, routine by routine, on both sides

`atari/profile.py ours` and `... original`, Hatari's own CPU profiler over a 1000-vblank window
opened at the twentieth frame — ours with symbols out of the linked ELF, the shipped binary's out of
`../../names.txt` relocated to where GEMDOS put it. **The frames in a window are counted from the
scroll blit** (`frame_panel_scroll_and_ship_stage` calls exactly one of the twenty
`scroll_page_to_screen_p*` entries per pass, on both sides), because a per-frame breakpoint inside
the window would be a debugger entry and a debugger entry stops the profiler. Ours held 155 frames
and this wave's shipped-binary window 99 — both re-derivable from `atari/out/profile-ours.json` and
`atari/out/profile-original.json` as they stand.

**READ THE PROVENANCE MARKERS BEFORE THE NUMBERS.** The tables below mix two profiling runs of the
same two binaries — the shipped binary did not change, but it was re-profiled — and the marker says
which run a figure is from:

* **unmarked** — this wave's run, and re-derivable cell by cell from the two jsons named above;
* **†** — carried over from the PRE-TWIN `profile.py ours` run, whose json this wave's overwrote. It
  cannot be re-derived from `atari/out/`; it is quoted from the previous edition of this table.
* **‡** — carried over from an EARLIER `profile.py original` run, whose json is likewise overwritten;
  the previous edition of the paragraph above recorded its window as 72 frames. This wave's 99-frame
  window gives `draw_score_panel` **16,540**, `sound_tick` **4,388** and `enemies_move_all` **2,773**
  where the ‡ cells say 16,463, 4,644 and 2,100 — the rows are left as the two runs measured them
  together rather than blended with a third.

A ratio marked **†‡** therefore divides a pre-twin figure of ours by an earlier figure of the
original's: it is the ratio those two runs measured together, not one this wave took.

**The scroll rows are the asm twins now**, so they are given before and after. `profile.py compare`
pairs a `*_asm` symbol with the original's own name, which is why the twins still have rows here.

| | ours/call | orig/call | ratio | ours/call before the twins | ratio before |
|---|---|---|---|---|---|
| `scroll_page_to_screen_p*` | **120,939** | 111,846 | **1.08x** | 244,702† | 2.19x† |
| `scroll_emit_column_shift2` | **33,560** | 31,452 | **1.07x** | 167,345† | 5.34x† |
| `scroll_emit_tile_column` | **35,046** | 32,175 | **1.09x** | 144,074† | 4.49x† |
| `draw_sprite_masked_collide` | **7,959** | 7,734 | **1.029x** | 18,539 | 2.40x |
| `draw_score_panel` | **16,975** | 16,657 | **1.019x** | 45,899 | 2.76x |

The last two rows' "before" columns are this wave's own pre-twin run rather than a carried-over one,
which is why they carry no †.

Those are Hatari's figures, which carry the machine's bus contention. Musashi's own cycle count, over
the differential's staged cases, is tighter still — **1.0024x** for the twenty blits, **1.0083x** and
**1.0136x** for the two emitters, **1.011x** for the tile emitter, **1.0236x/1.0387x** for the collide
blitter's middle and edge bands, **1.0458x** for its sibling and **1.0210x/1.0184x/1.1141x** for the
panel, the digits and a character drawn from C — and every point of it is the C-ABI prologue and
epilogue the original does not have. Each is pinned per case, a few CYCLES above what it measured, so
one extra register in a `movem` reddens it; `test_asm_{scroll,sprite,text}.py` take the readings on
every run.

And the rest of the frame, which the twins did not touch. **The per-frame column below is the
PRE-TWIN measurement and is left that way on purpose**: the profiler's window is a fixed 1,000
vertical blanks, so a faster game puts a different stretch of play inside it (a section start and a
long run of IKBD traffic moved in), and a per-frame share taken from the new window would not be
comparable with the old one routine by routine. The per-CALL figures ARE the comparable ones, but
**only the unmarked ones were re-taken** — three rows of the nine.

**THE FRAME AS A WHOLE IS A DIFFERENT INSTRUMENT AND IS NOT IN THE TABLE.** Ours is **518,237**
cycles to the original's **271,565**, **1.91x** — that is the cadence table above's "loop head to
flip, mean cycles" row verbatim, taken by breakpoints around one frame, not by the profiler. The
profiler's own window puts a frame at 861,899 (ours, pre-twin) and 268,317 (the original, this
wave's run): a different window over a different stretch of play, which is why the two instruments
do not agree and why no row below should be divided into 518,237.

**The percentages are shares of the pre-twin profiler window's per-frame total, 861,899.** That is
the whole of why `draw_sprite_masked_collide` reads 16% here and 27% of the frame in "What the
remaining 1.9x is" below — 140,948 of 861,899 against 140,948 of 518,237, one instrument each, both
right about their own denominator.

| | ours/frame (pre-twin, share of 861,899) | the original/frame | ours/call | orig/call | ratio |
|---|---|---|---|---|---|
| `draw_sprite_masked_collide` | 140,948† (16%) | 30,719 | 18,378 | 7,490 | **2.45x** |
| `zy_vbl_tick` — the whole VBL | 56,860† (7%) | (`sound_tick` 4,644‡) | 8,637 | | |
| `draw_score_panel` | 45,563† (5%) | 16,463‡ | 45,563† | 16,463‡ | 2.77x†‡ |
| `shifter_upload_palette_longs` | 33,153† (4%) | | 2,573† | | |
| `frame_spawn_and_move_stage` | 25,502† (3%) | | 25,502† | | |
| `zy_timer_b_tick` — the raster split | 21,577 (3%) | | 3,344 | | |
| `hw_write32` | 21,181† (2%) | | **205†** | | |
| `enemies_move_all` | 14,179† (2%) | 2,100‡ | 14,179† | 2,100‡ | **6.75x**†‡ |
| `psg_port_write` | 12,774† (1%) | | 180† | | |

**The per-CALL column is the one to read where the two windows saw different game states.** The
shipped side's window was profiled with the fire button held, so it drew fewer sprites a frame than
ours did (3.5‡ against 7.7; this wave's 99-frame original window draws 4.1) and
`draw_sprite_masked_collide`'s per-frame figures are not comparable
where its per-call figures are. `python3 atari/profile.py compare` prints the per-call ratio table
and refuses a row either side called fewer than twenty times.

**The diagnosis that led to the twins, and its outcome.** Three quarters of the frame used to be
four blitters, and every one of them was a C loop over longwords where the original is a `movem.l`
run: `copy_longs` compiles to `move.l (a0)+,(a1)+ / cmp.l / bne`, 36 cycles per 4 bytes, where a
12-register `movem.l` pair moves 48 bytes in 212 — 9 cycles a byte against 4.4, and 2.19x is exactly
what the scroll blit measured. That difference is `docs/on-target-execution.md`'s taxonomy 4 exactly,
and **no compiler flag reached it**: `-O3` generated the byte-identical loop (measured, on
`scroll.c`), and `-funroll-loops` got 9 cycles a byte down to about 7.4 — worth ~5% of the frame and
not a release slot.

What DID reach it was giving up on the compiler and writing the `movem.l` run out by hand — not a
new one, the original's own. See "The asm twins" below. `draw_sprite_masked_collide` at 2.45x was the
same shape and got the same answer in wave B, and is now 1.029x.

The ratios above 4x were a different finding: `scroll_emit_column_shift2` at 5.34x and
`enemies_move_all` at 6.75x are not bulk copies, so a `movem` was not what they were missing — they
are per-entity work where the original keeps its state in registers across a loop the reconstruction
spells as image reads and writes, which is the shape `machine.h`'s accessors force. The emitter is
now 1.07x, because a transcription keeps the state in registers by construction. `enemies_move_all`
is untouched and, re-measured with the whole tree twinned, is NOT the next lever: 3.91x per call now,
but only 2,914 cycles a frame of its own body against the original's 1,121 — the bullet under "What
the remaining 1.6x is" has the arithmetic.

## The asm twins — how the scroll, sprite, text and frame paths were transcribed

A **twin** is a hand-written m68k transcription of the original binary's own instruction sequence for
one routine, carrying the C signature of the verified core it replaces. `../src/asm/README.md` is the
recipe in full; the shape of the argument is short:

* the C cores are already proven byte-for-byte equal to the original (`../test/test_scroll.py`), and
  the original's instructions are in `../../out/prg_dis.txt` — so the fast version is not something
  to invent, it is something to COPY, and **a faithful transcription is 1.00x by construction**;
* the twins live in `../src/asm/*.S`, are assembled by the kit (`tools/recreate_kit/kit.mk`), and are
  substituted for the C at the CALL SITE through a per-subsystem seam — `../include/scroll.h`'s
  `ZY_SCROLL()`, `../include/sprite.h`'s `ZY_SPRITE()`, `../include/text.h`'s `ZY_TEXT()` — which
  `build.sh` switches on through `ASM_SEAM_DEFINES`. **The C stays compiled and stays the reference.**
* `../test/test_asm_{scroll,sprite,text}.py` run each twin and its C core over the same staged image
  under Musashi and compare the WHOLE image, on that subsystem's C battery's own cases — so the chain
  is `original == C == twin`, both links byte-exact. The four checks live in `../test/asm_twins.py`
  and are shared; a suite holds only its cases, its byte-pinned spans and its cost ceilings;
* the twenty page blits go further: their bodies mention no address at all, so they are assembled
  **byte-identical to the original's own machine code**, and that is a test
  (`test_the_twins_transcribe_the_original`) rather than a claim. Wave B's routines are byte-pinned
  over their SEVEN ROW LOOPS rather than whole — their clip prologues are immediate compares, which
  `gas` encodes as ANDI/CMPI/SUBI where the original's assembler used the immediate-EA forms, so the
  prologues cannot be byte-equal however faithfully they are copied. The cost pins stand in there;
* `build.sh`'s **asm-twin gate** is what stops the whole thing failing silently. Drop one of the
  `-D`s and that subsystem's `ZY_*(fn)` resolves back to the C: the twins still assemble, still link,
  still export their names, and the game still draws exactly the right pixels, several times slower,
  with nothing but the frame rate to say so. The gate asks the objects whether each declared twin is
  both DEFINED by an asm object and REFERENCED by a core object with no core object naming the bare C
  core, and it is proven able to fail (dropping `-DZY_ASM_TEXT` names all three text twins and
  exits 1). It globs `../include/*.h` rather than matching a prefix, which is why the sprite and text
  waves were covered by it the moment their headers declared a twin.

## What the remaining 1.6x is, and what it is not

* **It is not the shim, and the shim has now been taken out anyway.** Before the sweep above,
  everything this build added around the verified cores was **42,291 of the 815,488 cycles, 5.2%**:

  | | cycles/frame, before → after |
  |---|---|
  | the three interrupt entries and their dispatch | 4,426 → 3,850 |
  | the four hardware doors and their store counters | 37,865 → ~12,000 |

  What is left of the doors is the counting, and it cannot go lower while it is honest: every
  hardware store bumps `zy_hw_writes` and about two thirds of them bump an address-keyed tally too,
  each a `volatile` read-modify-write of about 24 cycles that must stay ONE instruction to be safe
  against an interrupt counting through the same door. At roughly 260 stores a frame that is ~12,000
  cycles, and it is the surface a target run has instead of the kit's ordered ledger. The CALL that
  used to wrap each of them — 205 cycles for a 24-cycle `move.l` to `$ff8240`, 103 times a frame —
  is gone.
* **It was not one routine, and that is why the whole scroll path went at once.** The scroll blit
  was the largest single item at 28% of the pre-twin profiler frame, but a twin of it alone (245,000
  down to ~112,000) would have
  left 680,000 — still over the 640,000 that four vblanks buys, so on its own it would not have moved
  one frame's bucket. The three routines together took 438,000 down to about 143,000, which is
  295,000 off, and THAT crossed the line: the mode moved from 6 vblanks to 4.
* **IT WAS NEVER "ONE ROUTINE", AND THIS BULLET USED TO SAY IT WAS.** It named
  `frame_resolve_hits_and_game_state`'s 211,784 cycles a frame of `frame_loop_once` "self" as the
  whole remainder. That row was ~95% busy-wait; wave C twinned it and collected ~19,500, not 140,000.
  The bullet was then rewritten to name the loop's other three slices at ~70,300; that figure was an
  inclusive row minus a partial child list, and wave D twinned all three for **+13 cycles a frame**.
  **Twice the remainder was read off a row instead of measured as a remainder, and twice it was an
  order of magnitude out.** What is actually left, measured as a remainder on one tree, is in "The
  per-tier ratio table, and what is left" above; `src/asm/README.md`'s "What wave D added" carries the
  rule that would have caught both.
* **`enemies_move_all` is NOT the next lever, and this is the measurement that says so.** Its
  inclusive cost is 12,976 cycles a frame against the original's 3,387, which reads like a
  9,589-cycle prize — but its own body is 2,914 against the original's 1,121, so a twin of the
  DISPATCHER SHELL wins **1,793 cycles a frame, 0.38%**. The other 7,800 are spread over the ~15
  movement handlers it calls, each needing its own transcription, battery and cost bar. `STATUS.md`
  carries the same arithmetic beside the twin table.

**WHY THE ARITHMETIC SAID TO DO THIS AND NOT THE SMALL LEVERS.** The cadence is quantised, so the
only change a player can see is a frame moving a whole release slot, and that needed **175,000
cycles** off (815,488 down under the 640,000 that four vblanks buys). The shim's entire overhead is
42,291 and the compiler's best offer was about 40,000 (`-funroll-loops` on the copy loops); together
they were less than half of it and would have left every frame in the bucket it was in, for a harder
binary to read. The asm twins were the only lever big enough, and they were worth 295,000.

**THE SHIM'S SHARE WAS TAKEN AND IT DID NOT MOVE THE MODE, WHICH IS WHAT THE ARITHMETIC SAID.**
The cadence is quantised, so the only change a player can see is a frame moving from 6 vblanks to 4,
and that needs the frame under the **640,000 cycles** four vblanks buys. The sweep above took 44,349
off — every one of them real and measured, and the binary is *easier* to read for it, because the
doors are now one header instead of eight cross-unit functions — and 770,571 is still 131,000 over
that line. What it DID move is the mixture: the fast bucket went from **10 frames of 534 to 47 of
564** in `play` and from **41 of 300 to 52 of 300** in `game`, so the mean fell from 7.38 to 5.81
and from 5.73 to 5.65. The MODE is still 6.

**The reachable next step is 4 vblanks, and it is one campaign rather than a lever — a frame moving
from the 6-vblank release slot to the 4, i.e. 8.3 fps to 12.5 at the MODE** (the `play` build's mean
is now 8.57 fps and the `game` build's 8.8; a mode is what a mixture of buckets is compared against,
and this whole paragraph is mode-to-mode). `scroll_page_to_screen_p*` at 2.19x plus
`scroll_emit_column_shift2` at 5.34x are 378,578 cycles a frame between them where the original
spends 139,392; asm twins at the original's own cost take **239,000** off, which is past the 131,000
the bucket now needs and was past the 175,000 it needed before. That is the work this section exists
to scope, and `atari/profile.py` plus `smoke.py`'s pacing check are what would judge it frame by
frame.

## Interrupt service, and input latency

| | the original | ours | how it was measured |
|---|---|---|---|
| attract Timer B served | 100 per vblank offered | **6,263 over 64 vblanks = 97.9 (98%)** | the record's own dispatch counts |
| in-game raster Timer B | once a frame | 1,961 over 1,962 menu vblanks | the same |
| keyboard ACIA served | one 3-byte report a frame | 917 over 2,045 vblanks = 0.45 | the same |
| input to ship movement | **1 frame** | **1 frame** | `frame_loop_once` passes `image[A_joystick_state]` to `frame_drone_and_fire_stage` once a pass and nothing else reads it, on either side |

**Input latency is one frame on both sides by construction, and that is the whole point of the
cadence table**: the FRAME COUNT is identical and the MILLISECONDS are not — 40 ms there against
115 ms here, because a frame is 2 vblanks there and 3.75 here (it was 5.73 before the
asm twins, i.e. 75 ms).

The four `$fffa21` read-back spins cost **281 iterations in a whole run** (about 4,200 cycles across
the four sites), and the number is large only because the register is a live counter: the spin
re-stores until a read comes back with what was written, which is the original's own loop and is why
it exists. It is not a pacing cost.

**THE "BOOT IS 2.8x" ROW WAS NOT MEASURING THE BOOT, AND IS RETRACTED.** It read the vertical
blank at which each side first reached its frame loop — ~2,230 here, ~795 there — and that number
is mostly the ATTRACT WAIT, whose length is set by how often the host-side driver gets round to
pressing fire, not by how fast either program boots.

The boot is now clocked by the program itself, and `smoke.py` prints it on every run. Marks on TOS's
own 200 Hz counter at `$4ba`, ONE PAIR AROUND EACH LOADER so that neither span bills the other's
work — a draft that reused the title loader's exit as the gameplay span's entry charged six record
reads, a masked vector-install window and the control's own fault injection to
`boot_load_gameplay_assets` — because the alternative instrument cannot be armed: a host driver
learns where GEMDOS put the program by reading a file the program writes, and by the time a poll
notices that file both loaders have run (measured — the earliest breakpoint anything outside could
arm landed at vertical blank 1,936, after the whole boot). `zy_vbl_ticks` cannot do it either: the
boot loads its files BEFORE it installs its own vertical-blank handler, so that counter is still 0
when both loaders are done — which is what the first draft of this clock printed.

| | title assets (8 files) | gameplay assets (14 files) |
|---|---|---|
| GEMDOS hard drive (`smoke.py game`) | **15 ms** | **250 ms** |
| floppy image (`smoke.py floppy`) | **12,315 ms** | — |

A FIFTH MARK AT THE HAND-BACK MAKES IT A CHECK AND NOT ONLY A COST. The spans stay reported and
unjudged — a boot time is host-dependent, and `atari/profile.py` is where cost is judged — but the
clock must have ADVANCED between the first mark and the last, and `smoke.py` reddens if it has not.
That is the first surface here for the defect the read-modify-write doors exist to prevent: Timer C
drives `$4ba` from MFP interrupt-enable B, beside the channel `boot_enable_interrupts` turns on, so
the plain `move.b #$40,$fffa09` that `hw_bset8` exists to avoid would take TOS's 200 Hz clock and
the floppy's motor timeout with it — and the kit's `hw.h` says in its own words that the write
ledger holds that the store happened and cannot hold which bits it preserved. The game would run,
the frames would be byte-identical, and the clock would be dead. Proven able to redden by making
`read_hz_200` return a constant.

**So the boot is the MEDIUM and not the port.** The same eight files and the same preshift banks
take 15 ms off Hatari's GEMDOS drive, where host file I/O costs the emulated machine nothing, and
12.3 SECONDS off an emulated floppy. 265 ms of emulated time for the whole hard-drive boot is about
thirteen vertical blanks — there is no 2.8x in it to explain, and the C preshift builders are inside
that 265 ms rather than beside it. What is still unmeasured is the SHIPPED binary's own two spans:
it has no record to write them to, and the same host-poll problem blocks a breakpoint. Closing that
needs the instrument to stop the machine at a PC it can know in advance, which nothing here does
yet.

## The pacing surface, and the control that reddens it

`smoke.py game` gained an eighth check, `check_the_pacing`, on the **timelines** surface. It reads
the program's own histogram out of STATE.BIN and judges five things, each with its tolerance argued
in the source:

* **the run is the one the tolerances were measured on** — the numbers below are absolute, not
  shares, so a run of a different length is REPORTED rather than judged. The `play` build's longer
  run reaches a second life, whose mixture is a different one, and would be read as a regression.
* **no frame costs zero vertical blanks** — 0 tolerance, and it is a real invariant:
  `frame_end_and_flip` arms `A_vbl_wait_flag` and spins until a handler clears it, with no cap, so a
  vblank always elapses inside the wait. **ONE vblank is NOT an error and an earlier draft of this
  arm said it was.** `A_raster_phase` is free-running, so a frame arriving with it already at READY
  skips the first wait and is released a single vblank later — the same parity effect that puts two
  3-vblank frames in the shipped binary's own 542. A zero-tolerance floor at two would have reddened
  a correct run.
* **the mean under 2.81 vblanks** — the derivation is eighteen frames each slipping one release slot,
  and a slot is two vertical blanks: 36 vblanks over 300 frames is 0.12 on the mean. It is applied to
  the WORST of eight runs rather than to their mean, because since wave B the cadence is **no longer
  reproducible to the second decimal**: ~65% of the frames now finish NEAR the release boundary,
  where a handful of cycles moves a frame between 2 slots and 4, whereas while every frame overran
  nothing sat on the boundary and the histogram repeated to the frame. That is a consequence of the
  win, not of anything getting flakier. Wave D's sample, on the binary that ships, is six `game` runs
  at 2.68, 2.68, 2.68, 2.67, 2.67, 2.68 and two `gamefault` at 2.68 and 2.69 — worst 2.69, 807
  vblanks. 807 + 36 = 843, and 843 / 300 = **2.81 exactly**, so like the 2.96 and 2.82 it replaces
  this ceiling carries no rounding slop. Measuring from the worst run is also what pays for the
  jitter: a regression still gets the full 36 vblanks. The 0.12 is
  deliberately NOT re-derived as a share of the new mean, which would shrink the slack with every win
  and make the check tighter than the evidence for it. (An earlier draft of the pre-twin ceiling used
  6.0 and was measured to be forty times looser than its own justification claimed.)
* **no frame reaches the histogram's last slot (seven vblanks or more)** — the allowance is **0**,
  where it used to be 2%: the section's first pass, the one frame that used to overflow, now fits
  with room to spare, and 0 of 300 is what all eight runs measure (their worst frame anywhere reached
  five). What zero does NOT fix, and the gap has grown: the slot is fixed in C at seven while the
  mode is now **two**, so this arm fires only at three and a half times the mode; a regression that
  puts every frame back at four or six vblanks is caught by the mean alone.
* **attract Timer B at or above 95% of the 100 the chip offers**, and **the ACIA at or above 0.25
  interrupts a vertical blank** — a handler running past its own period lands near half service, so
  the two states are far apart and the floors do not have to be precise to separate them.

**IT IS FAULT-BLIND, AND THAT IS MEASURED RATHER THAN ARGUED.** The check sits in `mode_game`'s
fault-blind set, so `gamefault` has to keep it green: measured, the control gives **2.80 twice**,
inside `game`'s own 2.80-2.84 band. The dropped section-chain step is a one-off panel repaint, not
per-frame work, so it moves what is DRAWN and not what a frame costs.

**IT WAS PROVED ABLE TO GO RED** rather than assumed to be. The control is a busy-wait in
`zy_vbl_tick` — 400 iterations of a `volatile` store, about 36,000 cycles, a fifth of a vertical
blank — which is enough to push a frame past the release slot it just fits into and on to the next
one. That is deliberately far past the ceiling: a control that only just crossed it would
be testing the tolerance rather than the surface. Measured 2026-09-01:

```
   pacing: 7.54 vblanks/frame [6x75 7+x225] = 6.6 fps (the original's 2 = 25); attract Timer B 6263/6400 served over 64 vblanks
   [red ] timelines (the frame cadence and the interrupt service rates)   (must PASS)
           the frame loop averaged 7.54 vblanks a frame over 300 frames, past the ceiling
           225 of 300 frames took 7 vblanks or more, past the 2% allowance
   [green] memory (the framebuffer and the entity table, frame by frame)
   [green] hardware-state vector (the pens, frame by frame)
   [green] exit status + log  (all five)
-- FAILED: 1 check(s)
```

The measurement above was taken before the asm twins, against the tolerances of the day — a 5.85
ceiling and a 2% overflow allowance, where the twins have since bought 3.87 and 0: 5.73 to
**7.54**, two of the check's arms red, and **every other surface still green — the
frame differential included**. That last part is the point rather than a footnote: a slower frame
computes the same bytes, because the game is frame-locked and nothing in it reads a clock, so a
pacing regression is invisible to every check this directory had before. The control was then
removed.

**THE CONTROL MUST BE GATED ON THE FRAME LOOP, and the first draft was not.** An ungated busy-wait
in `zy_vbl_tick` also slows the BOOT and the ATTRACT loop — 22 GEMDOS file loads and a wait for the
fire button, all of them running with 20-45% of the CPU taken — and the run then never reached its
first frame inside `smoke.py`'s fire deadline at all. That is a red, but on `check_the_game_ran` and
for the wrong reason: it says the machine got slower, not that the CADENCE check can see it. So the
control arms itself when `play_one_game` enters the frame loop and disarms on the way out, which
leaves every other phase at full speed and isolates the one span the histogram measures.

To re-run it, put this at the top of `zy_vbl_tick` with a `volatile uint32_t` flag set beside
`g_phase = PHASE_PLAYING` and cleared after the `do`/`while`:

```c
if (zy_pacing_control_armed)
    for (volatile uint32_t spin = 0; spin < 400u; spin++)
        zy_pacing_control_sink = spin;
```

## The bootable floppy, and what goes on the STE

`build.sh play floppy` writes `disk/ZYNAPS.ST` with the play build in `AUTO\ZYNAPS17.PRG`.
**Measured 2026-09-01: it boots from drive A on TOS 1.04 through the desktop's own AUTO scan and
reaches PLAYER 1 / PREPARE FOR COMBAT with the ZYNAPS logo and the status panel drawn** — 64 files,
417,792 B used, sha256 `aa44a32f…`. The medium is a FLAG now rather than a mode (M1's Unpinned 14), so any build can be
written onto a volume and `smoke.py --floppy-build <mode>` says which one is on it.

`build.sh` also clears the drive's `.BIN` files before staging, which is not tidiness: a floppy
built after a `game` run had every frame dump on it — 79 files and 588 KB against the 64 and 416 KB
it should be.

## Taxonomy classes M2 met, beyond M1's

| class | how it showed up |
|---|---|
| **11** a seam's second obligation | the whole boot's fourteen file loads now run with TOS's vertical blank displaced, which M1 deliberately never did — because the ORIGINAL does exactly that (its own vector goes in at `0x10062` and it opens fourteen more files afterwards), and the GEMDOS ledger says all twenty-two of ours complete |
| **12** a poke's unexecuted input path | **both** — the checks poke the joystick byte, because Hatari swallows a key bound to its keyboard-as-joystick emulation and the stick cannot be pressed from outside at all. What IS exercised is the whole chain behind it: `ikbd_send_cmd(0x16)` goes to the real 6301, the reply raises MFP channel 6, our `$118` entry dispatches `ikbd_acia_isr`, and it files the packet — 3394 ACIA interrupts in a run. `atari/run.sh` (`--joy1 keys`) is the discharge |
| **the reconstruction's own speed** | not a numbered class and it should be — see the section above |

## Unpinned, and why — M2's own

Numbered on from M1's list.

16. **The frame loop's two register parameters are passed as 0.** `frame_loop_once` takes
    `chance_index_register` and `ground_spawn_y_register`, two 68000 registers the original carries
    across a verified callee's `rts` (`../STATUS.md`'s "## Coverage limits"). Off target the case
    takes them from the oracle; on target there is no oracle, so this build declares 0 for both and
    `build.sh` can override either with a `-D`.

    **THE DERIVATION WAS ATTEMPTED AND IS UNDER-SPECIFIED**, which is why this is still here after
    the core-fidelity pass: D1 at the `bsr` into `enemy_fire_and_update_shots` depends on what the
    scroll blit's own `movem` left behind, and `../STATUS.md` carries the table of what is and is
    not pinned. `ground_spawn_y_register` costs nothing the shipped data can reach —
    `test_no_shipped_ground_script_can_make_the_spawner_read_its_carried_register` walks all
    thirteen shipped scripts and finds no record whose scripted y reaches the guard.
    `chance_index_register` is the live one: its HIGH BYTE indexes the per-section fire-chance
    table, so it decides whether enemies fire this frame, and a wrong value means enemies that shoot
    when the original's do not. **The frame differential is the surface, and it is green for 180
    frames of section 1** — which bounds the cost rather than removing it, since a section whose
    table row differs at the index 0 selects would diverge where this one does not.
17. **The second life is not pinned, and every sample has to stay inside the first.** Past the
    frame loop's first non-NEXT_FRAME exit the ship has died, `section_start_tail` has asked for the
    fire button again, and that wait calls `rand16` once a pass — so the number of passes, which is
    the DRIVER's rather than the program's, decides the random state the next life starts from.
    Measured before the entity pin landed: a sample at frame 240 came out byte-identical once and 42
    framebuffer bytes apart twice, always in entity record 6, the first enemy-shot slot.
    **It is checked rather than avoided**: the program reports the frame the first life ended on and
    `check_the_game_ran` refuses a sample at or past it, which is what caught the death moving from
    184 to 176 when the cores' `abcd` carry threading landed. With the entity table pinned the ship
    now survives the whole 300-frame budget, so all five samples are inside one life with room —
    but the guard is what says so, not the list. Closing it properly means pinning the random state
    at each SECTION START rather than only at the first.
18. **The attract screen has no anchor of its own.** M1 compares two boots at a palette state; M2
    compares two games at a frame count; the ATTRACT loop in between is compared by neither. It is
    also the phase where the reconstruction is slowest (see the interrupt finding), so it is the one
    most likely to differ. What would close it is the same shape as the frame differential — a
    breakpoint count on the attract loop's own body — and it is not done.
19. **Our attract loop exits without being asked.** Measured: the first interrogation's reply lands
    `$fd $fd` in the two joystick bytes rather than `$fd` then two states, so the fire test sees a
    negative byte and starts a one-player game. The cause is the interrupt budget above — the raster
    Timer B is MFP channel 8 and the keyboard ACIA is channel 6, so a handler that runs longer than
    its own period blocks the ACIA long enough for a byte of the three-byte packet to be lost and
    the packet parser to desynchronise. It is invisible to the frame differential (which pins the
    input from the loop head onwards) and it is why `player_count` is 1 in every run.
20. **The sound timeline is not compared for the game.** M1 cuts the PSG trace into the driver's own
    descending 10..0 tick frames and compares the first 64. The same cutter would work here, and the
    in-game tunes are what it would compare; it is not wired up.
21. **The game floppy has no differential.** `smoke.py floppy` runs M1's twelve checks off a volume;
    the GAME on a floppy has been booted and photographed (above) and nothing more. The frame
    differential's driver needs the floppy path's `$70`-derived anchor to be taught to it.
22. **The three read-modify-write doors are not atomic where the original's instructions are.**
    `bset`/`bclr`/`andi.b` on a register are single 68000 instructions; `*port = *port | bit` is a
    read and a write with a window between them, and an interrupt landing in that window would have
    its own change overwritten. Every caller in this reconstruction is already inside an interrupt
    or inside the boot's masked vector window, so nothing in THIS build can take it — but that is a
    fact about today's call sites, not about the doors, and the first caller on the main line with
    interrupts open would be exposed. What would close it is a mask around the pair, at the cost of
    two more instructions in the hottest handler the program has.
23. **Nothing has run on real hardware, and nothing has run on an STE**, exactly as in M1: Hatari
    refuses `--machine ste` on a ROM at or below TOS 1.4, and `tools/hatari/` has no later one.
24. **The game runs at 1.4x the original's cadence and 1.6x its frame cost** — 2.80 vertical blanks
    a frame against 2.08, 417,049 cycles against 262,244. It was a THIRD (5.73 and 815,488) before
    the asm twins, and a HALF (3.75) after wave A. It remains unpinned in the sense that MATTERS
    here: `check_the_pacing` refuses a REGRESSION from today's number and cannot demand the
    original's, so nothing in the suite goes red while the gap stands. **Wave C is scoped in the
    Performance section** — `frame_resolve_hits_and_game_state` is ~211,800 cycles a frame of
    tail-called, unprofiled C, and essentially the whole of the remaining gap — and the recipe is
    `../src/asm/README.md`. (The shim sweep took a further 44,349 cycles off — the doors inlined, the
    palette upload unrolled — so the combined tree is faster than any wave measured alone; the
    header table above carries the re-measured figures.)
25. **The SHIPPED binary's boot is still unclocked, and ours is no longer a mystery.** The old
    form of this row — "the boot takes 2.8x the original's vertical blanks" — was retracted on
    2026-09-01: it measured the vertical blank at which each side first reached its frame loop,
    which is mostly the attract wait and therefore mostly the host driver's own press cadence. Our
    two loaders are clocked by the program now, on TOS's `$4ba`, and `smoke.py` prints the pair:
    15 ms and 250 ms off the GEMDOS drive, 12,315 ms for the first off a floppy. What remains is the
    original's own two spans, which cannot be taken the same way — it has no record to write them
    into, and a breakpoint cannot be armed before its loaders run because the driver only learns
    where GEMDOS put it by polling for a file. See the PERFORMANCE section's boot table.
26. **The pacing surface judges OUR side alone.** `check_the_pacing`'s floors and ceiling are
    numbers this tree measured, checked into `smoke.py`; the original's own cadence is measured by
    `atari/profile.py original-frames` and lives in that file's comments and this README, not in the
    run. A `smoke.py game` therefore cannot notice the ORIGINAL getting slower — which cannot
    happen — but also cannot notice its own reference numbers going stale against a Hatari upgrade
    or another ROM. What would close it is running the shipped side's timeline inside `mode_game`,
    at the cost of a second boot in every run.

---

> **Realigned 2026-08-29** for kit commit `f5a2f71`, which moved the cores' hardware sinks onto a
> real write ledger. The shim's old `hw.h` shadow and its three per-routine overrides are gone, the
> cores' own `hw_write*` stores are what reach the chip, `ikbd_send_cmd` is a verified core rather
> than shim assembly, and `build.sh` grew a gate for the class of breakage that caused. Same twelve
> checks, same control — plus a **floppy** mode and a bootable `disk/ZYNAPS.ST`.
>
> **Swept 2026-09-01** for the shim's own cost on target. `shim_include/hw.h` and `psg.h` are back
> as SHADOWS OF THE KIT'S OWN NAMES — the seven doors as `static inline`, so a constant-address call
> site folds the address ladder and the store classification away — `build.sh` gained one per-file
> `-funroll-loops` for the palette upload, and the boot grew a clock of its own on TOS's `$4ba`.
> 44,349 cycles a frame, the pacing ceiling tightened 5.85 → 5.78, and two new build gates
> plus one new smoke check hold what the inlining put at risk.

## What M1 runs, and where it stops

`zynaps_main.c` composes the boot's **verified slices only**, in the original's own order, and stops
where the reconstruction stops:

| the original | what runs here | from |
|---|---|---|
| `0x10000` `Super(0)`, `movea.l d0,a7` | `boot_enter_supervisor()` | `../src/init.c` ✅ verified |
| `0x10010` `dc.w $a00a` (hide mouse) | `zy_line_a_hide_mouse()` | `zynaps_os.s` — the real opcode |
| `0x10012` `move.l $70.l,$195d0.l` | `boot_save_vbl_vector(image)` | `../src/init.c` ✅ verified |
| `0x1001c` `ikbd_send_cmd($12)` | `ikbd_send_cmd(0x12)` | `../src/input.c` ✅ verified |
| `0x10024` `ikbd_send_cmd($15)` | `ikbd_send_cmd(0x15)` | `../src/input.c` ✅ verified |
| `0x1002c`–`0x101b9` | `boot_load_title_assets(image)` | `../src/init.c` ✅ verified |

`0x101ba` is where `../STATUS.md`'s "Not reconstructed" table stops the boot — the harness's
staged-file table holds eight files and the ninth would be opened there — so it is where this stops
too. **Nothing in this directory composes an unverified slice.** The frame loop, the front end and
the remaining ~54 file loads are M2's, after the next port wave.

That slice does the whole title screen: the two framebuffers fixed at `0x70300`/`0x78000`, the title
picture read into the back buffer, low resolution selected, the game's own VBL and Timer B vectors
installed, tune `0x0b` started, the picture published, its palette uploaded, and seven more graphics
loaded and reshaped.

## Memory — the 1 MB diet

`--machine st --memsize 1`, TOS 1.04. **This build runs on a 1 MB Atari ST**, and every mode of the
smoke matrix is judged there. It used to need 4 MB: the shim hosted the differential harness's full
1 MiB image as `.bss`, which is a megabyte of program for a game that shipped on a 512 KB machine.

### What shrank, and what did not

`OS_IMAGE_SIZE` is **unchanged at 1 MiB** and must stay so: it is *both sides* of the differential —
the Musashi oracle's buffer and the candidate's bound — and `harness._vet_os_memory_map()` pins it
equal to `../project.toml`'s `image_size`. Off target that megabyte is a host `calloc` and costs
nothing.

The TARGET build gets its own length, `ZY_TARGET_IMAGE_BYTES = 0x80000` in
`shim_include/os.h`, and that one definition drives all of it: the `.bss` array, the two
`_Static_assert`s that the staged program and both framebuffers fit inside it, and — the one that
matters — the bound `os_in_image` checks. That last is not cosmetic. `os_fread` hands GEMDOS a
destination *inside this array*; a 512 KiB array bounded against 1 MiB would let one oversized read
write over `zy_saved_ssp` and `g_record`, which is the failure that tears down cleanly with every
read-back green.

**What the upper half held is harness-only.** The kit's fixed map puts the staged-file table at
`0xbf000` and its staging area at `0xc0000`, and the oracle's stack above that. None of the three
exists here: this build's file I/O is real GEMDOS (`shim_include/os.h`), it runs on the stack GEMDOS
gave it, and **no kit `src/*.c` is linked into the .PRG at all** — `build.sh` compiles
`../src/*.c` plus the three shim files and nothing else.

### The budget, measured

`_start` latches the basepage GEMDOS hands it — and the stack pointer it was entered with — before
the `Super(0)` push moves the stack, and `record_memory_budget` publishes them in `STATE.BIN`. So
these are the machine's numbers, not an estimate; `smoke.py` prints them on every run:

| | bytes | where it goes |
|---|---:|---|
| ST RAM at `--memsize 1` | 1,048,576 | |
| − TOS's physical screen | 32,768 | TOS puts it at the **top** of RAM → `p_hitpa` = `0xf8000` |
| − TOS low RAM + GEMDOS | 74,902 | → `p_lowtpa` = `0x12496`, booting a Hatari GEMDOS drive |
| **= TPA** | **940,906** | basepage + text + data + bss + the stack, and nothing else |
| − stack reserve | 32,768 | `STACK_RESERVE_BYTES`, `smoke.py` |
| **= budget** | **908,138** | what `build.sh`'s size gate weighs a build against |
| the `title` build | 595,594 | basepage 256 + text 66,048 + bss 529,290 → **312,544 B spare** |
| the `game` / `play` build | 597,470 | basepage 256 + text 67,840 + bss 529,374 → **310,668 B spare** |

**The 256-byte basepage is on the bill**, because GEMDOS carves it out of the same TPA immediately
below the text — a gate that weighed only `text + data + bss` would pass a binary that overran by
its length.

Three measured facts sit behind the table. **The floppy boot is cheaper, not dearer**: booting
`disk/ZYNAPS.ST` gives `p_lowtpa` = `0xa956` and a TPA of 972,458, about 31 KB more than the GEMDOS
drive, so the number written down is the worse of the two media and covers both. **`p_lowtpa` does
not move with the memory size** — at `--memsize 4` it is the same `0x12496`; only `p_hitpa` follows
the screen up. And the run-time headroom between the top of everything GEMDOS loaded and the
stack's ceiling is **345,304 B** at 1 MB.

Two things that measurement is careful about, both because getting either wrong makes the number
flatter itself:

* **The floor is `p_bbase + p_blen`, not the top of the image.** A `.bss` object linked *after*
  `g_image_store` sits above it — there are a couple of hundred bytes of door counters up there —
  and measuring from the image would leave them outside the check that is supposed to cover them.
* **The ceiling is the LOWER of `p_hitpa` and the SP `_start` was entered with.** TOS starts a
  child's stack at the top of its TPA, but that is a convention, not a guarantee; a launcher that
  pushed an environment would make a `p_hitpa`-only measurement over-report by the difference. The
  floor is copied from `projects/buggyboy/remaster/render/atari/os.s`, which carries the same pair
  for the same reason.

**And the TPA itself is pinned, not trusted.** `TPA_1MB_BYTES` is a measurement, and a measurement
nobody re-takes is a belief: `check_the_memory` compares it against the TPA the machine in front of
it reported on every 1 MB run, so a TOS build or an AUTO-folder resident that ate 200 KB more low
memory reds there instead of leaving `build.sh`'s gate quietly 200 KB too generous. Measured able to
fail: raising the constant to 999,999 gives *"this machine's TPA is 940906 B, under the 999999
build.sh's size gate weighs every build against"*.

### The census: why 0x80000 is enough

The claim is that no address the game can produce lands in `[0x80000, 0x100000)`. The evidence, in
the order it was gathered:

1. **The game shipped for a 512 KB ST.** Its framebuffers are `0x70300` and `0x78000` — hard-coded
   absolutes in the shipped binary, not relocated — and `0x78000 + 32000 = 0x7fd00` is the top of a
   512 KB machine's RAM with 768 bytes to spare. That is not a coincidence; it is the machine the
   addresses were chosen for.
2. **Program text + bss ends at `0x6e96e`.** `../project.toml`'s byte scan: text `0x9f46`, no data,
   bss `0x54a28`, at `load_base` `0x10000`.
3. **No `Malloc` and no `Mshrink` anywhere in the text**, at any alignment — the same byte scan. So
   nothing can be handed out above the program at run time.
4. **Every `A_*` the cores name is below `0x80000`**, the highest being `A_screen_front_buffer` at
   `0x78000`. `A_*` is this project's spelling for a Ghidra address and the only way a core reaches
   absolute memory, so this is the census proper — and `build.sh` re-runs it every build rather than
   leaving it a number somebody checked once. **472 addresses in two spellings**: the 315 `#define`s
   in the headers *and* the 157 `.equ`s the asm twins in `../src/asm` restate, whose objects are
   linked into this .PRG and are a second route to absolute memory the header grep would have
   missed. The gate **fails closed**: it counts what it parsed against a loose count of every `A_*`
   declaration, and refuses a mismatch, so a define written any other legal way (`(0x90000u)`, a
   decimal) is a refusal rather than an address quietly outside the census.
5. **No hex literal in `src/`, `include/` or the shim falls in the gap.** The only values at or
   above `0x80000` are the hardware registers, `0xff8201` upwards, which go through the hardware
   doors and never touch the image.
6. **The two framebuffers are asserted at compile time** against `ZY_TARGET_IMAGE_BYTES`, in
   `zynaps_main.c`, so the load-bearing half of (1) cannot rot silently.

**What the census cannot cover, said plainly**: an address the code *computes* rather than names — a
blit one row past the front buffer, a scroll span one word too generous — and the *extent* of a
named one, since (4) compares bases and only the framebuffers have an extent check. Off target such
a write lands inside the oracle's own megabyte and the differential compares it on both sides,
green. So there are **two watched bands** above everything the census names, and there are two
because **the game's world does not end where the array does**:

| band | span | held at | why it is separate |
|---|---|---|---|
| the **tail** | `[0x7fd00, 0x80000)`, 768 B | **zero** | Inside the image. The front buffer ends at `0x7fd00` and the array at `0x80000`, so *one low-res row* past the front buffer — 160 B, the exact overrun this paragraph names — lands here and a band above the array would never see it. Checked for zero rather than filled with a pattern: TOS zeroes `.bss` and the harness `calloc`s, so zero is what *both shores* hold there, and writing a pattern into a region a core can legally read would make this build differ from the differential. |
| the **guard** | `[0x80000, 0x81000)`, 4 KiB | `0xa5` | Outside the image, where a write reaches `zy_saved_ssp` and `g_record` — the failure that tears down clean with every read-back green. Filled with a pattern rather than checked for zero, because zero is also what a `memset` overrun leaves. |

`check_the_memory` reds on a single dirty byte in either, and **both arms are mutation-tested**: one
deliberate store at `IMAGE_WORLD_BYTES` reddens the tail, one at `ZY_TARGET_IMAGE_BYTES` reddens the
guard. Both bands come back **0 after a 300-frame `game` run**, which is the measurement — not an
assumption — that nothing in the frame loop walks off the top of the front buffer. A wild store
*further* up than the guard band is beyond any band, and nothing here claims otherwise.

The cores' own two `os_in_image` guards — `../src/init.c`'s attract-bar list and section-table walk
— move to the smaller bound with everything else. Neither can produce an address in the gap: both
start from an `A_*` below `0x7fd00` and step by 2 or 4 until they pass a cursor. **That is an
argument and not a surface, and `../STATUS.md`'s "On target" records it as unpinned**: the two
guards now stop at different addresses on the two shores, both fail by *not writing*, and pinning it
would mean a refusal counter in `src/` — a change to verified code that this work deliberately did
not make.

### Why 512 KB is out of reach

The obvious next step is not available. The game's framebuffers span `[0x70300, 0x7fd00)` — the top
of a 512 KB space — but on the real machine so does the *original*, which loads at `0xaa56` and runs
in the space below them. This reconstruction does not: it is a GEMDOS program that must fit its
whole image *inside its own TPA*. On a 512 KB machine that TPA is about **416,618 B (407 KB)** —
derived from two measurements rather than looked up: `p_hitpa` is RAM's top less TOS's 32 KB screen
(`0x80000 - 32768 = 0x78000`), and `p_lowtpa` is the same `0x12496` at every memory size, which is
itself measured (identical at `--memsize 1` and `--memsize 4`). A 512 KiB image plus 66 KB of text
does not fit in 407 KB, and it cannot be made to without moving the framebuffers — which are the
game's own absolute addresses and therefore not ours to move.

It was run rather than only computed: `smoke.py title --memsize 0` never reaches the program at all
(`BASE.BIN never appeared in 180 s`). **1 MB is the floor for this build**, and the original's own
512 KB is a property of a program that *is* the machine's memory rather than a guest inside it.

### Both sides, same machine

`smoke.py` runs **both sides at whatever `--memsize` says**, so every comparison it makes is about
the two programs rather than about two different machines. That is sound because the game hard-codes
its framebuffers at absolute RAM and TOS's TPA base does not move with the memory size — and it is
*checked* rather than argued: the original's own capture must hold more than one colour and its
sixteen pens must be the shipped boot palette, or the run says so and stops.

**The cadence does not depend on the memory size, measured rather than assumed.** The full matrix
runs at 1 MB and at 4 MB, and the four paced runs give:

| | `game` | `gamefault` |
|---|---:|---:|
| `--memsize 1` | 2.69, 2.69 | 2.67, 2.69 |
| `--memsize 4` | 2.68, 2.67 | 2.70, 2.67 |

(Two sweeps of the whole matrix at each size; both runs of each cell are listed.) The two sizes'
ranges overlap completely and neither is systematically higher — the spread is the
release-slot jitter the PERFORMANCE section describes, not the machine. All four are under the 2.81
ceiling, which is why `check_the_pacing` is left judging both sizes against the one number it was
calibrated at. ST RAM has no wait states that vary with how much of it is fitted, and these are the
numbers that say so. (The 2.70 is one hundredth above the worst of the eight runs the ceiling was
derived from; it is a ninth sample, 0.11 under the ceiling, and the derivation is not re-taken for
it — the PERFORMANCE section's own rule is that a wider baseline, never a raised ceiling, is the
response to a run that sits high.)

## The seam inventory

Every symbol the differential harness models, and what it becomes here. **The seam is the include
path plus ONE omitted directory** — the kit's own `src/`. No core is edited, no core is left out,
and `build.sh` measures three separate ways for that to stop being true: no core includes a shim
header, no core reads a target-only `-D`, and **no shim symbol collides with one a core defines**.

The seam moved under this build once already, at kit commit `f5a2f71`, and the last check is what
that cost bought. The kit grew `hw_write8/16/32` and a ledger for them, `../src/irq_hw_offtarget.c`
was deleted, and three names this directory used to own became live core code — so the shim's copies
turned from the target half of a seam into shadows of verified routines overnight. The linker does
object, but as `multiple definition of 'shifter_clear_pen0'` in the middle of a thirty-file link
line, saying nothing about which side is meant to own the name.

| symbol | what the HARNESS modelled | what the TARGET does | how |
|---|---|---|---|
| `os_fopen` / `os_fread` / `os_fclose` | a staged-file table in the image (8 slots at `0xbf000`), pure image copies — **bounds-checked** against the image, and a bad name **refused** | real GEMDOS `trap #1` `$3d`/`$3f`/`$3e` against Hatari's GEMDOS drive, with the model's **image bound and its refusal tally restored** — see below | `shim_include/os.h` shadow → `zynaps_os.s` |
| `os_super` | returns the cookie `$00535550`, no privilege change | **a no-op returning the same cookie.** `_start` takes supervisor once, before any C, and hands it back once through `zy_leave_supervisor` | `shim_include/os.h` shadow |
| `os_refused` | a refusal tally the harness reads back | an inline identity — the kit's own `os.h` anticipates this build | `-DOS_NO_REFUSAL_TALLY` |
| `os_in_image` | `addr <= OS_IMAGE_SIZE && count <= OS_IMAGE_SIZE - addr`, the differential's 1 MiB | the same arithmetic against `ZY_TARGET_IMAGE_BYTES` — the 512 KiB array that actually exists here. See **Memory** | `shim_include/os.h` shadow |
| `psg_port_write` | an ordered write ledger + a register file (`kit/src/psg.c`) | `move.b reg,$ffff8800` then `move.b val,$ffff8802`, from inside the vertical-blank interrupt | kit `src/` excluded; `shim_include/psg.h` shadows the header and defines it `static inline` |
| `hw_read8` | seeded reads of five declared addresses (`kit/src/hw.c`) | a real `volatile` load. One core caller — `ikbd_send_cmd` spinning on the 6850's transmitter-empty bit at `$fffffc00` — and one shim caller, `zynaps_main.c` reading TOS's four MFP registers back at the hand-back | kit `src/` excluded; `shim_include/hw.h` shadows the header and defines it `static inline` |
| `hw_write8/16/32` | an ordered (address, width, value) ledger `harness.differential` compares entry for entry (`kit/src/hw.c`) | a real `volatile` store **of its own width**, counted — and counted again by address for the three core effects the machine cannot be asked about afterwards. `hw_write8` also recognises the shifter's two video-base bytes and hands them to `zynaps_backend.c`, the one door that is a protocol rather than a store | kit `src/` excluded; `shim_include/hw.h`, `static inline`; the counters stay in `zynaps_backend.c` |
| `hw_bset8` / `hw_bclr8` / `hw_and8` | the same ledger, holding the byte the ORACLE's own `bset`/`bclr`/`andi.b` produced from its fabricated read (`kit/src/hw.c`) | a real `volatile` read-modify-write of its own BYTE width on the register, counted like `hw_write8` and again through `zy_rmw_stores`. Six core call sites; see Unpinned 2 for the table | kit `src/` excluded; `shim_include/hw.h`, `static inline` |
| `sched_poll8` / `sched_wait8` | polls counted per wait site, with declared stores (`kit/src/sched.c`) | `shim_include/sched.h` — the same spin with NO cap, and `volatile` so the loop keeps reading. `src/highscore.c`'s game-over chain is what calls them | kit `src/` excluded; this shim REPLACES rather than `#include_next`s |
| `sched_poll16` | the word form of the above | **not defined.** No Zynaps core calls it, and an unexercised word read in the one build with no oracle behind it is worse than absent — `shim_include/sched.h` says what to watch for when the first caller arrives | kit `src/` excluded |
| `g_dosound`, `disk_*` | the Dosound ledger, the staged disk | **not defined.** No Zynaps core calls one | kit `src/` excluded |
| `shifter_upload_palette_longs` / `shifter_write_pen` / `shifter_clear_pen0` | **ordinary core code** in `../src/video.c`, writing the ledger through `hw_write32`/`hw_write16` | the same core code, its `hw_write*` now the real store — eight `move.l` over `$ffff8240`, or one `move.w` | nothing: the seam is `hw_write*` |
| `mfp_ack_timer_b` | core code in `../src/irq.c`: `hw_bclr8($fffa0f, 0)`, ledgered as the `0 & ~bit` the oracle's own `bclr` produced | the same core code, its `hw_bclr8` now the real `bclr` — Timer B's channel alone. See Unpinned 2 | `shim_include/hw.h` must define `hw_bset8`/`hw_bclr8`/`hw_and8` |
| `screen_flip_buffers`' publish half | `hw_write8($ff8203/$ff8201, image offset >> 8/16)`, ledgered and compared | the same store — of an IMAGE OFFSET, which is right where the image is the machine's memory and wrong here. The shim re-publishes the machine address after the slice | `zynaps_main.c`, see below |
| `init_shifter_mode_mask_written` | the one byte the write ledger cannot hold: the MASK the `andi.b` applied | **still a counter** — read into the record. The ACCESS it describes is the core's own, through `hw_and8` | `zynaps_main.c` |
| `ikbd_send_cmd` @ `0x14444` | ✅ verified in `../src/input.c` — `$fffc00` is a seeded READ slot (`OS_HW_ACIA_STATUS`) and `$fffc02` is ledgered | the same core code: an UNBOUNDED spin on bit 1 of `$fffffc00`, then a store to `$fffffc02`, exactly the original's four instructions. `-DOS_NO_REFUSAL_TALLY` compiles the off-target give-up arm away, and `build.sh` measures that it did | nothing: the seam is `hw_read8`/`hw_write8` |
| the Line-A opcode @ `0x10010` | modelled as a no-op (the oracle takes it as an exception) | the real `dc.w $a00a` | `zynaps_os.s` |
| `image[0x70]`, `image[0x120]`, `image[0x195d0]` | ordinary diffable image bytes | **not vectors.** The shim seeds `image[0x70]` from the real `$70` so the slice's copy means something, and installs the REAL vectors itself, masked | `zynaps_main.c` |
| interrupts | the harness runs none at all | `$70` and `$120` are replaced with `movem`/`rte` trampolines calling the verified `vbl_isr` / `timer_b_isr` | `zynaps_os.s` |
| `memcpy` / `memmove` / `memset` | the host's libc | hand-written loops (`-fno-tree-loop-distribute-patterns` stops GCC replacing them with calls to themselves) | `zynaps_backend.c` |

### What a real trap loses, and what is put back

A seam that swaps a modelled call for a real one drops the model's CONTRACT along with its
implementation, and the kit's file helpers have two halves worth keeping. Both are restored in
`shim_include/os.h`, and each keeps a count the record publishes and `smoke.py` asserts — a restored
guard with no surface is a guard nobody can watch fire.

* **The image bound.** `os_fread` copies through `os_in_image(buf, count)`, "written as a
  subtraction, never `addr + count`: that sum wraps for a large count and waves the copy through".
  Off target a destination past the image is a refusal and the harness throws the case away, so a
  mutated address or an off-by-one length is caught by construction. Unguarded on target, GEMDOS
  writes those bytes into whatever follows the image in `.bss` — `zy_saved_ssp` among them, which is
  the shape that dies at `zy_leave_supervisor` *after* a clean teardown with every read-back green.
  A `_Static_assert` covers the staging read the same way, at compile time.
  **`os_in_image` is itself shadowed here since the diet**, so that the bound is
  `ZY_TARGET_IMAGE_BYTES` — the length of the array that actually exists — and not the model's
  1 MiB. That is the fifth replaced helper, and bounding against the wrong one of the two is exactly
  the defect this bullet describes.
* **The refusal tally.** `-DOS_NO_REFUSAL_TALLY` is right for the cores' own sentinel path but
  leaves nothing counting a FAILED OPEN — and `load_file` (`../src/fileio.c`) has no error handling
  at all, faithfully: it hands Fopen's `-33` straight to Fread as a handle. Under the harness an
  unstaged name was a refusal the harness could not ignore; on target a data file missing from
  `../../bin/disk` would simply leave the buffer zeroed, and **M1 draws none of the four files whose
  absence would show**. So the opens are counted at the seam and the count is asserted.

### The one address a relocated image cannot publish for itself

The cores make their own hardware stores now, and `zynaps_main.c` lost two of the three publishes it
used to make on their behalf: `set_palette_title`'s sixteen colour registers and
`shifter_select_low_resolution`'s `$ff8260` byte both land on the real chip from inside the verified
slice. One is left, and it is the only one that is not a fidelity question but an ADDRESS question.

`screen_flip_buffers` publishes two bytes of `0x70300` — an IMAGE OFFSET. That is exactly right in
the differential's world, where the image IS the machine's memory and starts at 0, and exactly right
on the original, which runs at the base its hard-coded framebuffers are absolute against. This build
stages the image in a `.bss` array, so the shifter needs `image + 0x70300`, and the core has
no way to know that: it is handed a `uint8_t *` and writes what the original writes.

So the core's two stores land first with the untranslated value, and `publish_screen_base()`
re-stores the machine address after the slice. `raw_video_base_at_anchor` reads the register back and
`smoke.py` compares it against `published_screen_base`, so a missing re-publish is a red.

**What it costs is a transient**, and it is honest to state it: between the core's store inside the
slice and the shim's after it, the shifter is pointed at `$0703xx` and displays whatever is there
while the remaining seven files load — about a second on a GEMDOS drive and several on a floppy.
Nothing this smoke photographs can see it (every shot is at the anchor, seconds later). It is
harmless here and it is **not** a shape M2 can keep: the frame loop flips every frame, so the
translation has to move somewhere the core itself can reach. Recorded under **Unpinned 3**.

## The six surfaces, and what each one measured

`python3 atari/smoke.py title`, TOS 1.04, both sides at the same memory size. Re-measured
2026-09-02 at **1 MB**, after the diet, and green at 4 MB in the same sweep:

```
-- title on st / TOS104US.img at 1 MB: image base 0x22a00, the original at 0xaa56,
   266 vblanks and 2926 PSG writes at the anchor
   memory: TPA [0x12496, 0xf8000) = 940906 B, image 512 KiB at 0x22a00, 345304 B headroom
   to the stack, 0 tail + 0 guard byte(s) dirty
   pens read off the chip, unmasked: 0033 0021 0202 0044 0055 0066 0665 0777 0550 0303 ...
   [green] exit status + log (ours)
   [green] exit status + log (the fault scan can fail)
   [green] exit status + log (the machine was handed back)
   [green] exit status + log (the original)
   [green] exit status + log (the program's own record)
   [green] hardware-state vector (TOS's 200 Hz clock survived the boot)
   [green] hardware-state vector (Timer B never fired)
   [green] memory (the boot slice's own output and ledgers)
   [green] memory (the framebuffer)
   [green] memory (the game fork was not taken)
   [green] memory (the image fitted the machine, and stayed inside itself)
   [green] the original was anchored on its own boot
   [green] timelines (the PSG tick frames)
   [green] trap ledger
   [green] hardware-state vector (the pens, $ff8260, the video base)
   [green] rendered pixels
-- OK
```

| surface | what it compared | result |
|---|---|---|
| **exit status + log** | Hatari's return code and its own `Bus Error`/`Address Error`/`CPU halted` lines, on both sides, read from **stderr**; the emulator kept running three seconds past `Pterm`; and the program's own `STATE.BIN` complete to its `'DONE'` tail | clean. At 4 MB the only fault line either side logs is TOS's own `Bus Error writing at $41fffe, PC=$fc0174` — the ROM sizing memory at the 4 MB boundary — which the scan drops **by its ROM PC**, not by failing to see it. **At 1 MB that line does not appear at all**: the ROM never probes past the RAM it has, so the drop-by-PC arm has no input there and is exercised only by the matrix's 4 MB half, which is one reason both halves are run. The scan's own control proves it can still go red on every run |
| **trap ledger** | `--trace gemdos`: our `Fopen`/`Fread`/`Fclose` sequence, minus the shim's four files and TOS's own `DESKTOP.INF`, against the original's first slice | **24 calls parsed on our side, identical to the original's first 24** — the same eight lowercase names in the same order, on the same handle, with the same byte counts. The buffer address is deliberately not compared: ours is inside the image array and the original's is absolute RAM |
| **memory** | the 32000-byte displayed framebuffer, written by the program from `image + screen_front`, against a `savebin` of the original's `0x70300` | **byte-identical** |
| **hardware-state vector** | the sixteen colour registers, `$ff8260` and the two video-base bytes, read at the anchor by the DEBUGGER and independently by the PROGRAM, both sides | pens identical and equal to the shipped boot palette; `$ff8260` = 0 (low res) on both; `Physbase` reads back exactly what was published (`0x8cc00` = image base `0x1c900` + `0x70300`), so the address was 256-aligned and nothing was truncated. The report also prints the pens UNMASKED, which is the only place an STE's fourth bit a gun could show — on an ST every high nibble reads back 0 |
| **rendered pixels** | a Hatari screenshot of each side, byte for byte, with `--frameskips 0 --statusbar off --drive-led off` and stop-then-shoot | **byte-identical** |
| **timelines** | `--trace psg_write`, cut into the sound driver's own descending 10..0 tick frames, first 64 compared | identical — the title tune is the same stream, register for register |

Also read back and asserted, from `STATE.BIN`: `boot_enter_supervisor`'s token is the model's
`$00535550`; one then two command bytes had reached `$fffc02` after the two IKBD sends; exactly one
store to `$ff8260`, with mask `$fc`; exactly eight LONGWORDS into the colour block — which is
`set_palette_title`'s `movem.l #$00ff,$ff8240.l` and cannot be inflated by the shim's own word-wide
pen writes; `image[0x195d0]` holds the real TOS vector
the shim seeded at `image[0x70]`; `2926 = 266 x 11` PSG writes, i.e. the driver flushed eleven
registers on every one of the 266 vertical blanks and missed none; no PSG write named a register
outside 0..15; Timer B fired 0 times; and after the hand-back both vectors, the resolution and all
sixteen pens are what TOS had, with `Physbase` back on TOS's own screen.

### The alignment rule for the timeline, and why the anchors differ

The two boots do not agree on when the tune's first frame falls. The original installs its VBL
vector mid-slice (`0x10062`) and ticks through all eight file loads; this build installs it **after**
the slice returns, so that no GEMDOS trap is ever made with TOS's vertical-blank handler displaced
(`docs/on-target-execution.md` class 11). So the timeline is compared as a **shape**: a trace is cut
into frames on the driver's own descending `10..0` flush — the only thing in either program that
writes the chip that way — and frame 0 is each side's first, whatever the boot did before it.

The two runs are also anchored differently, and the reason is a measured failure:

* **Ours is a PC.** The shim writes `BASE.BIN` with the runtime address of `zy_anchor` before it
  loads anything, then spends five seconds on the title screen.
* **The original's is a STATE** — its last colour register holding the boot palette's last pen, a
  value read off the staged program image rather than typed. A PC breakpoint has to be armed before
  the program arrives, and the shipped disk runs the game out of `C:\AUTO` within seconds of
  power-on and reaches `0x101ba` a few milliseconds later; the first draft polled RAM for the
  program and then armed, and anchored the original in its **front end** twenty seconds later —
  22,948 of 32,000 framebuffer bytes apart, with pen 0 blanked by a title-screen handler our boot
  never installs. A state condition fires whether it was armed before or after, which is what makes
  it immune to that race. `check_the_original_was_anchored_on_its_boot` is that diagnosis turned
  into a check.

That anchors the original at `0x10084` rather than `0x101ba`, i.e. before the last seven file loads.
Those read into `0x41eae`..`0x6115e`, all below the framebuffer, and none touches the palette — so
every surface compared is identical at both points, and the ledger and the timeline are read out of
the whole run's trace and do not depend on the shot at all.

Both sides are photographed **stop-then-shoot**: break at the anchor, then four `b VBL > VBL :once`
breakpoints chained (Hatari's expressions have no arithmetic — `b VBL > VBL + 4` is refused at the
`+`), and the last one photographs. `zy_anchor` holds sixteen vblanks, and the smoke asserts that
hold is longer than its own offset — the two numbers are in different languages and the check is the
pin.

## The negative control

`build.sh titlefault` is the title build with **one pen corrupted on its way to the shifter and
nothing else** — the cores draw the same bytes, make the same calls and write the same chip
registers. `smoke.py titlefault` inverts its verdict for the two colour-sensitive surfaces.
Measured:

```
   [red ] hardware-state vector   the pens differ at [3]: ours ['0x733'], the original's ['0x44']
   [red ] rendered pixels         the pictures differ in 172356 of 1377792 colour bytes
   [green] memory (the framebuffer)
   [green] trap ledger
   [green] timelines (the PSG tick frames)
   [green] exit status + log  (all four)
   [green] the control's own soundness
   [green] the control moved exactly one pen
-- OK
```

Two things keep the control honest, and both cost a check:

* **The pen comes from the RECORD, never from a scrape of `build.sh`.** The per-mode `.PRG`s outlive
  an edit to that script, so a scraped number could name a pen the running binary never touched.
* **The pen must be ON SCREEN.** `smoke.py` decodes `ZYNPIC.PIC` and refuses a fault pen the title
  picture does not use — otherwise the rendered-pixels arm would fail for lack of coverage rather
  than because of the fault, which is the trap a sibling project fell into and had to document.

## The bootable floppy

`build.sh floppy` writes `disk/ZYNAPS.ST` and `smoke.py floppy` boots it. **This is the form that
goes onto the real machine**, and it is the first run in which TOS's own loader, a FAT12 volume and
the floppy driver are all under the program rather than emulated away by a GEMDOS drive.

### What is on it, and what is not the original's

**The filesystem is not `mkfloppy.py`'s.** `tools/st_build.py` is this workspace's FAT12 writer —
the write half of `st_extract.py`, stdlib only, game-agnostic — and it does all of it: two FATs, the
`AUTO\` subdirectory, a deterministic image, a sha256, and the one thing that decides whether a real
machine mounts the disk at all. *TOS EXECUTES sector 0 when its 256 big-endian words sum to `$1234`*,
and `st_build` picks a serial that makes the sum come out wrong on purpose and then asserts it. An
`mformat` image satisfies that by luck, 65,535 times in 65,536 — the first draft of this file shelled
out to mtools and would have shipped that lottery, along with a `brew install` step in the runbook.

What `mkfloppy.py` is left holding is what is about ZYNAPS: **which files, under which names.** The
loader is the DESKTOP's `AUTO` scan, so our program must be **`AUTO\ZYNAPS17.PRG`**, the name the
original ships; and the data files must sit in the **root**, because the game opens them by bare name
against whatever drive it was booted from.

```
>> disk/ZYNAPS.ST: 64 files verified against disk/ byte for byte
   AUTO\ZYNAPS17.PRG = ZYNAPS-floppy.PRG (42039 B), 63 files in the root
   399360 B used, 328704 B free; the run writes back 3 files in 34 clusters
   sha256 e21dcbde0e1290dd1ede11926115e6d0d405afe158f53a5188c54817bcac5bd9
```

That sha256 is not decoration: it is the only host-side binding between the image a check booted and
the bytes a person writes to a physical floppy. Print it here, re-read it before the write, compare
it after a boot that was supposed to leave the volume alone.

**The geometry is not the original's: 720 KB DOUBLE-SIDED, 9 sectors a track**, where the original is
80x1x10x512 = 400 KB. `st_build` argues for that format on its own terms — it is what `gw/README.md`
prescribes for an unprotected disk, and the 10- and 11-sector formats hold more but are the ones a
drive that is not the one they were written on can fail to read. 400 KB could not have held this
build in any case: the 62 data files are 307 clusters, our `.PRG` is 42, `ZYNAPS.IMG` — the relocated
game image the shim stages into its own array, which the original does not need because it *is* the
game — is 40, and the three files the run writes back are 34, against a single-sided volume's 393.
The cost is that a single-sided drive cannot read this disk; the machine it is for is an STE.

The BPB says two FATs and the volume has two. The original's says **one** and carries two (a
duplication artifact TOS never notices, because the Atari BPB has no FAT-count field —
`../../README.md`); this image does not reproduce the lie, which is why it needs no `--nfats`
override to be read by a host tool.

**Verified by a different reader from the one that wrote it.** `st_build` writes the volume;
`mkfloppy.py` reads it back with `st_extract.py`'s parser and compares every file's bytes against
the source it came from, refusing on any missing, extra or differing file — and inspects the
parser's warnings AFTER the read, because `st_extract` fills most of them from inside `walk` and
`read_file`. It also asks the finished volume for what the RUN will need and not just for what the
build put on it: 34 free clusters and three free root-directory slots, which are different resources
and run out at different times. `smoke.py` re-checks the one thing that goes stale before every run
— that `AUTO\ZYNAPS17.PRG` on the volume IS `build/ZYNAPS-floppy.PRG` — because a stale image boots
and passes every surface while testing a binary that is no longer on disk.

### What the run measured

`python3 atari/smoke.py floppy` — **ours off `disk/ZYNAPS.ST`, the original off its own
`../../bin/zynaps.st`**, both sides on the same ROM and machine. Sixteen checks, all green
(re-measured 2026-09-02 at 1 MB, and green at 4 MB in the same sweep):

```
-- floppy on st / TOS104US.img at 1 MB: image base 0x1af00, the original at 0xaa56,
   266 vblanks and 2926 PSG writes at the anchor
   memory: TPA [0xa956, 0xf8000) = 972458 B, image 512 KiB at 0x1af00, 376856 B headroom
   to the stack, 0 tail + 0 guard byte(s) dirty
   [green] x16, including memory (the framebuffer), rendered pixels, trap ledger, timelines
-- OK
```

That `TPA [0xa956, ...)` is the second measurement the **Memory** budget rests on: booting the
FAT12 volume leaves `p_lowtpa` about 31 KB *lower* than the GEMDOS drive does, so the GEMDOS
figure is the worse of the two and is the one the size gate is set from.

Re-run on **TOS 1.02** — a second ROM, which Unpinned 7 asked for and the GEMDOS modes cannot have
(Hatari refuses directory emulation below 1.04) — also sixteen green, at a different load address:
`image base 0x1d100`, out of a TPA of 963,836 B (`p_lowtpa` `0xcb04`, a third figure again). Between
the three runs the program has been relocated to three different places and published a correct
256-aligned video base from each — and the 1 MB budget held on all three.

**The class-11 question the floppy makes real, answered.** TOS's vertical-blank handler is displaced
for the whole title screen, and on a floppy that handler owns the drive's motor timeout and media
poll — the "idle fuse" shape that cost the Wonder Boy port a batch. The GEMDOS ledger says it never
arises here: `BASE.BIN`, `ZYNAPS.IMG` and the eight data files are all opened BEFORE the vectors go
in, and `SCREEN.BIN` and `STATE.BIN` are written AFTER the hand-back — and those two writes, 32 KB
through TOS's floppy driver, succeed. There is no GEMDOS call in the window at all.

### Two things about the medium worth writing down

* **`--run-vbls` expiring does NOT write the image back; quitting does.** Hatari keeps a `.ST` in
  memory and flushes it when the emulator is shut down properly. Measured both ways: a run left to
  hit its vblank budget leaves the host file byte-identical, and the same run closed through the
  command FIFO has `STATE.BIN` on it. `run_ours_from_floppy` therefore waits for the record and
  closes, and it waits on the GEMDOS ledger showing `STATE.BIN` created, written **and closed** —
  the close is where GEMDOS flushes the last sectors and the directory entry.
* **The anchor cannot be `BASE.BIN` and cannot be a signature search either.** The first is written
  onto the floppy, which the driver cannot read during the run. The second is what
  `poll_for_original` does for the original, and it does not work for us: `locate_by_signature` cuts
  its needle from the bytes BEFORE a program's first relocation, and this build's first fixup is at
  TEXT offset `0xa`. So the load address comes out of **the vertical-blank vector the program itself
  installs** — `$70` does not move with the TPA, and its contents minus `zy_vbl_entry`'s ELF offset
  is the base — and is then confirmed by the same exact relocation test the search ends with.

## What `build.sh` refuses

Ten scans, and each names the defect it exists for:

* **The duplicate-symbol gate.** The shim may not define a name a core defines. It exists because
  the seam MOVES: three names this directory owned became live core code when the kit's write ledger
  landed, and the shim's copies turned from the target half of a seam into shadows of verified
  routines. It is also the half a linker cannot be relied on for — a build that ever acquired
  `-z muldefs`, or a variable that landed in COMMON, would link clean and run the WRONG BODY, with
  `make test` green on the core the machine never executes. Compared on defined GLOBAL symbols of
  separately compiled objects (which is why `build.sh` compiles and links in two steps), and it
  proves it can fail on every run in the TWO ways it can rot: a synthetic pair of lists with one
  name in common must produce exactly that name, **and** both real lists must be non-empty, because
  `comm` over two empty lists is just as silent as over two clean ones. Both measured — re-introducing
  `shifter_clear_pen0` into `zynaps_backend.c` gives `ERROR: the shim defines 1 symbol(s) that
  ../src now defines too`, naming it; breaking `defined_globals`' field filter gives `ERROR: nm named
  0 shim and 0 core symbols`.
* **The IKBD-cap scan, and its first draft is why it has a MEASURED control.** `../src/input.c`'s
  `ikbd_send_cmd` carries a give-up arm, `IKBD_TX_POLL_MAX`, inside `#ifndef OS_NO_REFUSAL_TALLY` —
  it exists so an off-target case cannot spin for ever on a byte the harness forgot to seed. On the
  machine the 6850 really does empty and the original has no cap, so a build that shipped one would
  drop a command byte instead of waiting a microsecond. `-DOS_NO_REFUSAL_TALLY` removes it, and this
  is the check that it did.
  The draft asked "does the routine contain a comparison", on the reasoning that a counter needs
  one. **It was vacuous, and the review measured it**: with the cap present GCC reverses the loop
  onto a countdown and emits `subq`/`bne` with *no* `cmp` or `tst` at all, so capped and uncapped
  both scored zero. What it counts now is CONDITIONAL BRANCHES — the original's spin has exactly one,
  its own `beq` — and the control is not a synthetic line but `../src/input.c` compiled a second time
  with the macro undefined, which the scan must score higher. Today: **1 against the control's 2.**
* **The `hw_read8` census.** `hw_read8` used to be defined nowhere in this build, so a core that
  acquired a hardware read failed to LINK; `zynaps_backend.c` defines it now, for `ikbd_send_cmd`'s
  ACIA poll, and that link error is gone. Off target the kit REFUSES an address outside its seeded
  set — but the refusal tally is compiled away here, so a core reading `$ff8260` through a bare
  literal would be green there and read the real chip on target, with no link error and no surface.
  So every argument must be one of `os.h`'s `OS_HW_*` names, which is what makes the address
  DECLARED. One site today, and it names one.

* **The trap-register scan** (`tools/assert_trap_registers.sh --expect 11`). TOS preserves only
  `%d3-%d7`/`%a3-%a6`; GCC believes `%d2`/`%a2` survive too. A wrapper that does not save the pair
  silently corrupts one variable in its C caller, and it is invisible to every differential in this
  project. Eleven wrappers here trap and return; `_start`'s `trap #1` is `Pterm0` and is exempt by
  the scan's own rule.
* **The EA-ordering scan.** A postincrement source and an indexed destination on the SAME address
  register — the instruction GCC folded a sibling project's palette loop into, which put every pen
  one register high and drove the sixteenth write into `$ff8260`, the resolution register.
  the hardware stores are emitted inside core loops now; "cannot be emitted" was a claim about a
  compiler, so it is measured — and the scan proves it can fail on every run, against two synthetic
  known-bad lines, because a pattern that quietly stopped matching would look exactly like a clean
  binary.
* **The endianness check.** `machine.h` picks native `*(uint32_t *)` accessors on a big-endian
  target; if that guard failed to fire, every field access in every core would be an `lsl #8`
  shuffle chain (a uniform ~4x slowdown and a 40% larger `.PRG`). The count is reported, not gated —
  30 today, where hundreds would be the tell — and `__ORDER_BIG_ENDIAN__` is asserted at the source.
* **The containment checks.** The cores' whole PREPROCESSED include closure must be exactly the six
  shim headers the seam declares — the four shadows of kit headers the cores already include
  (`os.h`, `hw.h`, `psg.h`, `sched.h`), plus `tos.h` because the `os.h` shadow needs the trap
  primitives and `string.h` because m68k-elf ships no libc — and no core may read a target-only
  `-D`. It used to grep for a DIRECT `#include "zynaps_target.h"`, which was sound while `os.h` was
  the only shadow and went blind the moment `hw.h` became one: a shim header could then reach a core
  THROUGH the shadow, and a first draft of `shim_include/hw.h` did exactly that, putting
  `zy_image_base` and every `zy_*` global into six verified translation units with the gate printing
  green. `gcc -MM` answers what the compiler opened, which is the question the gate was always
  asking. Still asked of includes and macro names rather than of identifiers, because those files'
  own comments discuss `hw_write8` and the target build at length — that is the seam documented
  where it lives, and a grep for identifiers would red on prose.
* **The doors' own two checks**, both added with the inlining. The shim's shadows must define
  EXACTLY the doors the kit declares (`psg_port_read` excepted, and deliberately: a core that
  acquired a PSG read then fails to compile rather than reading a real chip with no surface behind
  it) — the kit is shared by four projects, and a door added or renamed there would otherwise leave
  this build compiling against a stale shadow. And every counter those doors keep must be
  incremented by a SINGLE read-modify-write instruction: the counters are read on the main line and
  bumped inside interrupts, which is safe only while `addq.l #1,<abs>` is one uninterruptible
  instruction. That was a one-off human read of one object while the doors lived in one file; they
  are emitted at every inlined call site now, so it became a scan. 98 increments today, none split.
* **The `os_*` census — the shadow's own central claim, measured.** `shim_include/os.h` replaces
  FIVE kit helpers and pulls the rest in through `#include_next`, so every other `os_*` is still the
  deterministic MODEL, compiled into the `.PRG` and answering out of an in-image register file. The
  header says that is safe because a grep found only those five; this is that grep, run every build.
  A core reaching `os_bconin` would link cleanly and read a real keypress out of a fabricated model,
  with `-DOS_NO_REFUSAL_TALLY` having compiled away the tally that would have counted it: no link
  error, no record field, no surface. M2's own plan ports the routines that would do it.
  **The scan is in two halves since the diet, and the second half is what the diet made necessary.**
  The first covers `../src` and `../include`; the second covers the shim's *own* three C files and
  its headers, which were exempt while a modelled helper here was merely useless. It is worse than
  useless now: the model's fixed map puts its staged-file table at `0xbf000` and its staging area at
  `0xc0000`, both of which were inside the 1 MiB array and are a quarter of a megabyte *past the
  end* of the 512 KiB one. A shim helper calling `os_fwrite` — or `os_in_image_fixed`, whose bound
  is baked into a macro over `OS_IMAGE_SIZE` and cannot be shadowed — would link cleanly, pass every
  other scan, and write into `.bss`. Comments are stripped (`-fpreprocessed -dD -E`) before the
  grep, because these files argue at length about the helpers they deliberately do *not* call and a
  raw grep reports the reasoning as the defect.
* **The memory census** — every `A_<name>` this build can link, against `ZY_TARGET_IMAGE_BYTES`. The
  target image is half the differential's, and the claim that pays for it is that no address the
  game names lands in the missing upper half (**Memory**, above). A new `A_*` above the image would
  otherwise compile, run against the `.bss` beyond the array, and be caught by nothing until a
  crash. Today: **472 addresses, all below `0x80000`** — the headers' 315 `#define`s *and* the 157
  `.equ`s the asm twins restate, because those objects are linked and are a second route to absolute
  memory. It **fails closed**: the parsed count is checked against a loose count of every `A_*`
  declaration, so a shape the grep cannot read is a refusal rather than a silent gap. Both arms
  measured able to fail — a probe `#define A_x 0x90000` gives `ERROR: an address a core names is at
  or above the target image's 0x80000`; a probe `#define A_x (0x90000u)` gives `ERROR: the census
  parsed 472 addresses out of 473 A_* declarations`, printing the one it could not read.
* **The 1 MB size gate.** `basepage + text + data + bss` against the TPA a 1 MB TOS 1.04 machine
  leaves, scraped from `smoke.py`'s measured budget. `_start` takes no `Mshrink`, so a binary that
  eats the whole TPA does not fail to load — it loads and then writes its own stack, in the middle
  of a boot, with no message. Today, for the `play` build a person actually runs: **597,470 B
  loaded against a 908,138 B budget, 310,668 B spare** (the `title` build is 595,594). Measured able
  to fail — dropping the budget to 500,000 gives `ERROR: ZYNAPS.PRG needs 595594 B of TPA`. The run-time half of it is `smoke.py`'s `check_the_memory`, which weighs the
  program against the stack ceiling the machine in front of it actually reported, checks the two
  watched bands, and re-takes the TPA measurement the gate's own budget rests on; every arm of it is
  mutation-tested.

Two things `build.sh` deliberately does NOT do:

* **`-Wno-array-bounds` is not passed.** The flag exists in both sibling projects for the shim's
  absolute-address dereferences — but `CFLAGS` is shared with the VERIFIED CORES, and this is the
  one build where an out-of-bounds index reads live machine memory rather than the harness's guarded
  image. The three sites that need it carry a scoped `#pragma GCC diagnostic` instead
  (`read_vector` / `write_vector` in `zynaps_main.c`), so the cores are still built at
  `-Wall -Wextra` with nothing suppressed. Measured: those two accessors are the only sites that
  warned.
* **It does not gate on the `lsl #8` count**, only report it. The threshold would be a guess, and a
  guessed gate is worse than a printed number.

## Taxonomy classes this build met

Numbered as in `docs/on-target-execution.md`.

| class | how it showed up here |
|---|---|
| **1** endianness tax | avoided by construction — `machine.h`'s big-endian arm; `build.sh` reports the `lsl #8` count so a regression is visible |
| **3** trap/ABI glue | eleven wrappers, every one saving `%d2`/`%a2`, gated by the workspace scan |
| **6** the EA-ordering shape | designed out by construction — every shifter store computes its address as a value and hands it to a `hw_write*` call, which cannot compile to a postincrement-source/indexed-destination pair — and then scanned for anyway, in the linked binary, because "cannot" is a claim about a compiler |
| **7** hand-back on every exit path | the whole teardown: both vectors, the chip, `Setscreen`, sixteen pens — each read back into the record, with the emulator left running three seconds past `Pterm` |
| **8** the video base's missing low byte | **the design constraint of this build.** The image's runtime base is rounded up to 256 with reserved slack, and `Physbase` reads the register back. Measured at THREE different load addresses, which is the point of it: `0x8cc00` on the GEMDOS drive, `0x85100` off the floppy on TOS 1.04, `0x87300` off the floppy on TOS 1.02 — published and returned, every time |
| **9** `Super(0)`/`Super(ssp)` is not a pair | `zy_leave_supervisor` plants the USP itself one instruction before the trap. This build is the EXPOSED shape, not the lucky one — `_start` takes supervisor before any C and hands it back a whole boot later, so the two `%sp` depths have no reason to agree |
| **11** a seam's second obligation | the reason the vectors go in AFTER the slice rather than during it: no GEMDOS trap is ever made with TOS's vertical-blank handler displaced. **Now measured on the medium where it would bite** — the floppy run's whole GEMDOS ledger (`BASE.BIN`, `ZYNAPS.IMG`, the eight data files, then `SCREEN.BIN` and `STATE.BIN`) falls either before the install or after the hand-back, and TOS's floppy driver writes 32 KB back afterwards without complaint |
| **12** a poke's unexecuted input path | the `$12`/`$15` IKBD sends are made by the VERIFIED `ikbd_send_cmd`, and the record carries how many bytes reached `$fffc02` — but nothing downstream of the byte is exercised, because M1 has no input path at all. See Unpinned |
| **the seam's own drift** | not a numbered class and it should be: three shim symbols became core code under this build without a single test moving. The duplicate-symbol gate above is the surface for it |

## Unpinned, and why

Written down rather than skipped — `docs/on-target-execution.md`'s rule is that a change naming no
surface *is* the finding.

1. **Six of the seven `irq` handlers never execute.** M1 installs `vbl_isr` and `timer_b_isr`;
   `vbl_isr_title`, `timer_b_raster_isr`, `attract_vbl_isr`, `attract_rasterbar_isr` and `vbl_menu`
   belong to the front end, which is unported. So `shifter_upload_palette_longs`' handler callers,
   `shifter_write_pen`, `shifter_clear_pen0` and the palette cycling are compiled and never run.
   **M2's surface.**
2. **THE READ-MODIFY-WRITE DEFECT IS CLOSED IN THE CORES, AND `zynaps_backend.c` MUST NOW DEFINE
   THREE NEW NAMES.** The cores used to spell the original's `bset`/`bclr`/`andi.b` on a register as
   a plain `hw_write8` of the byte a fabricated read produced — green off target and wrong on the
   machine, where the store clobbers every bit it should have preserved. They now spell the
   OPERATION, through three kit names added beside `hw_write8/16/32` in
   `tools/recreate_kit/include/hw.h`:

   | name | what a target build must compile it to | the cores' six call sites |
   |---|---|---|
   | `void hw_bset8(uint32_t addr, uint32_t bit)` | `*(volatile uint8_t *)addr \|= (uint8_t)(1u << bit);` | `../src/init.c`'s `boot_enable_interrupts` (`$fffa09` and `$fffa15`, bit 6) and `../src/frame.c`'s `frame_end_and_flip` (`$fffa09`, bit 6) |
   | `void hw_bclr8(uint32_t addr, uint32_t bit)` | `*(volatile uint8_t *)addr &= (uint8_t)~(1u << bit);` | `../src/irq.c`'s `mfp_ack_timer_b` (`$fffa0f`, bit 0) and `mfp_ack_acia` (`$fffa11`, bit 6) |
   | `void hw_and8(uint32_t addr, uint32_t mask)` | `*(volatile uint8_t *)addr &= (uint8_t)mask;` | `../src/init.c`'s `shifter_select_low_resolution` (`$ff8260`, mask `$fc`) |

   **A BYTE ACCESS, exactly as `hw_write8` is a byte store, and for the same reason** — `$fffa10` is
   the MFP's timer-A data register and a widened access would clobber it. Each is ONE store, so
   `andi.b` must stay one call and not two `hw_bclr8`s (the kit's
   `test_splitting_a_mask_into_two_bit_clears_reds` is what says so).

   **AND EACH MUST CALL `note_store()`, like the three stores above them.** That is not tidiness:
   `note_store` is what feeds `zy_hw_writes` and the per-address counters the record exposes, so a
   definition that omits it leaves `zy_shifter_mode_writes` at 0 and `smoke.py`'s
   `record["shifter_mode_writes"]` check fails for a reason that has nothing to do with the
   register — the surface goes dark exactly where this change needs it most.

   **Until the backend defines them the target build does not link**, which is the intended shape:
   the cores can no longer express the defect, so the machine's read half has to be supplied here.
   The off-target ledger is unchanged — `src/hw.c` records the byte the oracle's own instruction
   produced from its fabricated 0 — so every existing case stayed green through the change.

   What is still unpinned is the same as before and no more: off target a `bclr`'s ledgered value is
   0 for every bit and an `andi.b`'s is 0 for every mask, so the ledger holds the address, the width
   and the fact of the access, not the channel or the mask. (A `bset`'s IS pinned — `0 | (1 << bit)`
   is a different byte per bit.) `../include/init.h`'s one-byte sink still holds the resolution mask;
   the four MFP bits are held only by the source spelling and by this table.
3. **`screen_flip_buffers` publishes an IMAGE OFFSET to the shifter, and the shim re-publishes the
   machine address after the slice.** See "the one address a relocated image cannot publish for
   itself". The core's store is now real and ledgered off target — that half is pinned, which it was
   not before the kit's write ledger — but on target it names `$0703xx` rather than
   `image + 0x70300`, so the shifter displays garbage from the core's store until the shim's, about
   a second on a GEMDOS drive and several off a floppy. No surface here samples that window: every
   shot is at the anchor. **It is not a shape M2 can keep** — the frame loop flips every frame, so
   the translation has to move somewhere the core itself can reach.
4. **The IKBD's *effect* is unpinned.** The record says one then two command bytes reached
   `$fffc02`; that the 6301 disabled the mouse and entered joystick interrogation mode is not
   observable here, because M1 reads no input. This is exactly the shape of taxonomy 12, named in
   advance rather than after. And the spin is now **unbounded**, as the original's is: a transmitter
   that never empties hangs the boot instead of publishing a 0, and the finding is then a missing
   `STATE.BIN` — a louder result than the bounded copy's, and the original's own behaviour.
5. **The Line-A hide-mouse has no surface at all.** There is no mouse pointer in any comparison this
   file makes; the call is here because the boot makes it.
6. **`os_super`'s deviation is not reproduced.** The original follows its `Super(0)` with
   `movea.l d0,a7` and runs on the old supervisor stack for the rest of its life; this build keeps
   the stack GEMDOS gave it. `../STATUS.md`'s `boot_enter_supervisor` row already records that "that
   A7 becomes that token is unpinned" off target, and it is unpinned here for the same reason —
   reproducing it would move the C stack out from under the compiler mid-function.
7. ~~**One TOS ROM.**~~ **Closed by the floppy build.** `smoke.py floppy` runs both sides off
   floppies, so Hatari's refusal of GEMDOS directory emulation below TOS 1.04 no longer applies:
   twelve green on TOS 1.04 and twelve green on TOS 1.02, at different load addresses. What is still
   missing is **EmuTOS** — Homebrew's Hatari ships no ROM for it and none is in `tools/hatari/` —
   and the ROM the target STE actually has, **TOS 1.62**, which is neither of these.
8. **Nothing has run on real hardware.** Every number above is Hatari's.
9. **The PSG select/data pair is unmasked inside the handler**, reproducing the original's race on
   purpose. Nothing else in this build writes the chip while the handler runs. The TEARDOWN's
   silence is a different matter and is now masked and made BEFORE the vector restore: handing the
   vertical-blank vector back does not remove the other writer of that latch, it *introduces* it
   (TOS's own vertical blank drives the chip for `Dosound` and the floppy's drive-select lines). An
   earlier draft had the silence after the restore, unmasked, with the argument the wrong way round.
10. **TOS's vertical blank is displaced for the whole title screen** — five seconds under `title`,
    indefinitely under `play`. `_frclock`/`_vbclock` freeze and every `_vblqueue` entry stops,
    including TOS's floppy VBL with its media-change poll and its drive deselect/motor timeout.
    **Now exercised rather than argued about:** the floppy run displaces it for the same five seconds
    with a real FDC underneath, and TOS then writes 32 KB back through its own driver after the
    hand-back. The window still contains no GEMDOS call of ours (the ledger says so), so what remains
    unpinned is the case M2 creates — a load made WHILE the vectors are ours, which is what
    `_start`'s own boot does and this build deliberately does not.
11. **The sixteen pens go up as sixteen stores** where the original's `set_palette_title` ends in
    one uninterruptible `movem.l`. The critical section around the hand-over restores the atomicity;
    what stays unpinned is that nothing MEASURES a half-changed palette, because the anchor is 250
    vblanks later and no surface here samples a single frame during the boot.
12. **Nothing has run on an STE, and on these ROMs nothing can.** An STE has a third video-base
    byte at `$ff820d` and FOUR bits a gun where the ST has three; the pens are saved and restored RAW
    (only the record masks), so the hand-back is correct on both machines, and the base read-back
    would simply not see an STE's low byte. `smoke.py --machine ste` was attempted and **Hatari
    refuses the combination**: "TOS versions <= 1.4 work only in ST mode and with a 68000 CPU", and
    it silently switches back to `st`, which would have reported on a machine nobody asked about.
    `assert_machine_and_rom_agree` now refuses it up front with that reason instead. Unblocking it
    needs a TOS 1.06+ ROM or EmuTOS — the same missing input as item 7. What CAN be said today is
    that the unmasked pens are printed on every run, and on an ST every high nibble reads back 0, so
    the day an STE run happens the fourth bit has a baseline to be compared against.
13. **The floppy is 720 KB DOUBLE-SIDED where the original is 400 KB single-sided**, because
    400 KB cannot hold the build (see "The bootable floppy"). Nothing about the program depends on
    it — but a single-sided drive cannot read the disk, and no single-sided image has been produced
    or tested. The 720 KB choice is `tools/st_build.py`'s, argued there.
14. **The floppy has NO NEGATIVE CONTROL.** `titlefault` is a mode of the `build.sh` enum and the
    floppy is another, so the medium that actually goes on the STE is the one medium whose twelve
    checks have never been shown able to go red. What limits the damage is that they are the SAME
    check functions the GEMDOS control inverts, so what is genuinely unproved is narrower: the
    floppy path's own new machinery — the `$70`-derived anchor, the record lifted out of the image,
    the framebuffer lifted out of the image. Two of those three are self-refusing (a wrong record
    fails its magic, its field count or its tail; a wrong anchor moves the pens and the picture), so
    the gap is real and small. The fix is to make the MEDIUM a flag orthogonal to the mode rather
    than a fourth mode, which also stops `build.sh floppy` producing a second copy of the `title`
    binary under another name. **Named, not done.**
15. **`palette_long_writes` is keyed on a WIDTH, which is an argument about today's call sites.**
    `zynaps_backend.c` counts longword-wide stores into the colour block because
    `set_palette_title`'s `movem` is the only thing that makes one — true now, and the comment says
    so. The first `hw_write32` anyone adds there (M2's palette fades are the obvious candidate)
    inflates the count and reddens the arm whose job is to catch a DELETED `set_palette_title`, for
    a reason unrelated to the boot. The depth-correct replacement is the shape the kit already has
    off target: a small bounded on-target ledger of (address, width, value) carried in `STATE.BIN`,
    which would subsume all three tallies and `SHIM_HW_WRITES`'s hand-maintained arithmetic with it.

## Out of scope, and left for its own commit

Two defects this directory's review found that are NOT in this diff, because fixing them here would
be either wrong or somebody else's change:

* **`tools/hatari_headless.py`'s `LOG_FAULT_MARKERS` spells "Bus error"; Hatari 2.6.1 prints
  "Bus Error".** So `log_faults()` returns `[]` over a log that names a bus error, for every project
  that takes the default — the sibling project's half-blind exit detector, alive again in a
  different spelling. `smoke.py` passes its own correct-cased markers rather than editing the shared
  list, because a case-insensitive matcher there would redden every 4 MB run in the workspace on
  TOS's harmless memory-sizing probe; that fix needs the ROM-PC filter to move with it, which is a
  change to a shared tool and belongs in its own commit with the siblings re-run.
* **`smoke.py`'s `await_file` is a second definition of `HeadlessSession._await_file`.** The two
  differ in timeout and in the size test. Promoting the private one (it is private only by name) is
  a `tools/` change with callers in other projects; noted rather than folded in.
* **The duplicate-symbol gate is per-project for a kit-wide failure class.** Three projects have
  the same `recreate/atari/{build.sh,shim_include,smoke.py}` shape and the class is structural to
  `tools/recreate_kit/` — `projects/joust/recreate/atari/build.sh` still links its shim and cores in
  one `gcc` call with an `os.h` shadow, carrying the exact exposure this gate was written for.
  Lifting `defined_globals` plus the comparison into a `tools/` script the three build scripts call
  is the depth-correct form. It is left out of this commit because it is a change to two other
  projects' builds and wants their smokes re-run with it; per-project gates are also the established
  style here (Wonder Boy keeps its own `nm` gates locally).
* **`../src/input.c:65` warns under this build's `-D`.** `for (unsigned poll = 0; ; poll++)` sets a
  variable nothing reads once `-DOS_NO_REFUSAL_TALLY` has removed the give-up arm, so a target build
  emits one `-Wunused-but-set-variable` from a CORE. It is a true statement about the code — and in
  fact the first evidence that the arm really is compiled out, which is now measured properly by
  `build.sh`'s IKBD-cap scan instead. Silencing it is a change to a verified core, which this
  directory does not make.

## What M2 will need from the cores

M1 stops at `0x101ba` because the reconstruction does. To go further:

* **The rest of `_start`** (`0x101ba`..`0x10814`). The kit's staged-file table holds 32 slots now
  and the boot measured at 22 `load_file` calls, so the wall that stopped the slice here is gone;
  what M2 needs is the SLICE, verified off target. `../STATUS.md` has the row.
* **The section flow's tail** (`0x10d96`..`0x10f4e`) and `title_attract_loop` (`0x12ac2`). The ACIA
  wall is half gone: `ikbd_send_cmd` is verified and this build calls it. The other half is
  `ikbd_acia_isr` (`0x14456`), which needs a READ model for `$fffc02` — a declared byte sequence —
  and, here, an interrupt entry beside `zy_vbl_entry`. That is what gives M1's `$15` command
  something to do and closes Unpinned 4.
* **The frame loop** (`0x10f4e`) needs its three stages (`0x113c0`, `0x11c00`, `0x11d30`), which are
  the wave-3 world-staging work.
* **A place for the video-base translation that is not the shim.** Unpinned 3: `screen_flip_buffers`
  publishes an image offset, M2 flips every frame, and a re-publish after the fact stops being a
  workable arrangement the moment there is more than one flip. This is the one item on this list
  that is a DESIGN question rather than a porting one.
* ~~**A kit-level hardware-write ledger.**~~ Landed at `f5a2f71`, and it is what this revision of
  the shim is realigned to: the OLD `shim_include/hw.h` is deleted, `../src/irq_hw_offtarget.c` is
  deleted, and the target half of the kit's own `hw_*` names is this build's. Since 2026-09-01 that
  target half is a new `shim_include/hw.h` rather than `zynaps_backend.c` — the same names and
  signatures, `static inline` so a call site can fold them; the backend keeps the counters and the
  one door that is a protocol. The Layout section says why the two files are not the same thing.

## Layout

```
atari/
├── build.sh              title | titlefault | game | gamefault | play | playtitle, on either
│                         medium (gemdos | floppy), plus the eight scans
├── smoke.py              the six surfaces, two controls, the floppy mode and M2's frame
│                         differential against the shipped binary
├── mkfloppy.py           which files under which names -> disk/ZYNAPS.ST via tools/st_build.py
├── run.sh                launches the play build with a screen, sound and a joystick — the
│                         one input path no headless check can exercise
├── gen_image.py          stages the relocated program (kit loader) -> disk/ZYNAPS.IMG
├── mkprg.py              base-0 ELF -> GEMDOS .PRG  (a copy; see its header)
├── tos.ld                the link script (a copy; see its header)
├── zynaps_os.s           _start, 11 trap wrappers, the machine primitives, 3 interrupt entries
├── zynaps_main.c         the shim: staging, the boot, the hand-back, the record
├── zynaps_backend.c      the seam's target half + a freestanding libc
├── shim_include/
│   ├── os.h              shadows the kit's: real GEMDOS, no-op Super
│   ├── hw.h              shadows the kit's: the seven doors, as target inlines
│   ├── psg.h             shadows the kit's: the YM2149's two ports, likewise
│   ├── sched.h           shadows the kit's: the busy waits, uncapped
│   ├── tos.h             what zynaps_os.s provides
│   ├── zynaps_target.h   what the two C files hand each other
│   └── string.h          the three libc names
├── build/                gitignored — objects, the ELF and the per-mode .PRG/.elf pairs
└── disk/                 gitignored — the GEMDOS drive Hatari boots, and ZYNAPS.ST
```

`shim_include/hw.h` CAME BACK on 2026-09-01 and it is a different file from the one that was
deleted. The old shadow existed because the kit exported no write half at all and the shadow added
one, with narrow value types the kit later contradicted — that file was redundant and then wrong,
and deleting it was right. This one adds no name the kit does not declare and changes no signature:
it defines the kit's OWN seven names `static inline` so a call site can see them, which is what the
kit's header asks a target build to do, and the whole reason is measured — 205 cycles for a 24-cycle
store, in the PERFORMANCE section's lever table. `psg.h` is the same seam for the same reason. It
cannot `#include_next` the kit's headers: those seven are declared `extern`, and C forbids a
`static inline` definition of a name already declared without `static`.

`mkprg.py` and `tos.ld` are **copies**, as they are in `projects/joust/recreate/atari/` and
`projects/wonderboy/recreate/atari/`; each copy's header names the others and says what differs.
Moving them into `tools/recreate_kit/` is the standing kit candidate — registered in Joust's README
("Reviewed and deferred"), in Wonder Boy's `STATUS.md` batch 43 phase A queue, and here.
