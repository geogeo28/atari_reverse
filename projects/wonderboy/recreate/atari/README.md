# atari/ — run the reconstructed Wonder Boy on a real 68000

This takes the reconstruction past the differential harness: it **cross-compiles the very same
verified C cores to 68000** (`m68k-elf-gcc`) and runs them as a GEMDOS `.PRG` under Hatari with a
real TOS ROM. The seventeen translation units under `../src/` are compiled **unchanged** except for one
flag they themselves anticipate, and this directory supplies only the hardware boundary the harness
models away.

It exists because the spine closed. `game_main_loop` is reconstructed whole, and the four things it
touches that the harness can only model — a seeded hardware read, the direct YM2149 ports, a
scheduled write that releases a busy-wait, and three shifter registers the oracle drops — now have a
target-side implementation.

**It is not the game yet, and the reason is one sentence:** `game_main_loop` is `jmp`ed into with a
stage already loaded, and the chain that loads one is unported. §2 draws that line exactly — and
records how M2 crosses it without pretending to have ported the boot: by taking the ORIGINAL's own
post-boot RAM off a real emulated machine and staging that.

## Status

| milestone | what it proves | state |
|-----------|----------------|-------|
| **M1** the machine drives the reconstruction | `vbl_handler` — the project's one reconstructed interrupt handler — runs on the level-4 autovector fifty times a second, its own `WB_VBL_COUNTER` tracking the shim's independent tick count exactly; `tempo_drop_value` picks the music tempo from **two real hardware reads**; the idle countdown expires and `floppy_deselect_drives` drives the **real YM2149**, read back; `sched_wait8`'s uncapped spin ends on a byte a **real interrupt** wrote; and the screen base the reconstruction publishes is translated onto the shifter, read back, **and its addend pinned against `WB_SCREEN_FRONT`'s own longword in the staged image** | ✅ `smoke.py m1` |
| **M1** negative control | one store suppressed (the vector install) and **every machine-driven check fails** — the counter stays at its seeded 0, the tempo byte stays at its never-written sentinel, the countdown never expires, the chip is never touched. The two checks that do NOT depend on the vblank still pass, so the control is targeted rather than a blanket break. On a ROM whose ENTRY STATE already satisfies one of them the control excludes it **and prints the exclusion** (§7) | ✅ `smoke.py novbl` |
| **M1** hardware control | the **same binary**, booted with a monochrome monitor, takes `tempo_drop_value`'s *other* arm — `WB_SND_TICK_DROP_MONO` where a colour boot gives `WB_SND_TICK_DROP_50HZ`. A code control cannot show that a hardware read is LIVE rather than a constant the compiler folded; changing the machine can | ✅ `smoke.py mono` |
| **M1** machine health | every mode runs Hatari to the **end** of `--run-vbls` and asserts both halves: the exit status, and the log scanned for faults whose PC is not TOS's own memory-sizing probe | ✅ every mode |
| **M2** the original's post-boot RAM | `atari/original.py` boots the shipped 1989 disks under Hatari, drives them past the two fire gates and the data-disk swap, and dumps the game's whole address space `[0x3f8,0x80000)` at **`$f8b4`** — the boot's last instruction. Seven pins from the inside (the relocated resource signature, `stage_load_window`'s two latched pointers, both vectors, the stage number, and game_main_loop's own code against the shipped file); a **mis-anchor measurement** (25.6% of the span differs one call earlier); two **negative controls** (no fire → no anchor, no data disk → no anchor); and a **reproducibility measurement** that finds ~500-650 of 523,272 bytes are one boot's accident (the figure moves between boots; `variance` owns it) and holds every band to a ceiling | ✅ `original.py dump / neighbour / variance / nofire / nodisk2` |
| **M2** a frame | `game_main_loop` runs **fifty-two frames on the machine**, and at four anchored frames its 32000 framebuffer bytes and its sixteen hardware pens are **byte-identical to the shipped binary's** running the same fifty-two frames. Both sides read where the picture really is — ours out of the image at the address `flip_screen` published, theirs off the shipped binary's own screen by `savebin` at a breakpoint on `$4a0` | ✅ `smoke.py m2` |
| **M2** mis-anchor control | our frames read off the NEIGHBOURING shipped frame, verdict inverted. The two rows a one-anchor shift can reach both fail; the other six are **excluded and printed**, because this game's picture toggles on a one-second cadence and half the shifts land on an identical frame (§9) | ✅ `smoke.py m2fault` |
| **M2** the two flip-site mutants | **MEASURED DYING** (§9): the base-byte swap in `flip_screen`'s own two call sites, and the wrong buffer published. Neither touches an image byte — the framebuffer compare cannot see them — and both move the address read back off `$ffff8201/8203` | ✅ both CAUGHT |
| **M3** the exits | `game_key_actions`' three endings are not returns — they pop `game_main_loop`'s return address and `jmp` into the unported boot chain, so the reconstruction REPORTS which one it took (../include/game.h). **ALL THREE ARE NOW MADE TO HAPPEN ON THE MACHINE**, one run each: the round-end reload ($54e, unwind $e5ba), the cheat's level skip ($56c, the same target and a different code) and ESC's quit ($58c, the music fade then $e494). Each arm's condition is a word or a byte in the image, so the drive is a debugger poke at `capture_the_frame`'s SECOND arrival — a known frame, not a wall clock — and the ending fires at the top of the next frame, where `game_key_actions` reads. Measured: 2 frames completed, `loop_ending` = 1, 2 and 3 respectively | ✅ `smoke.py m3` |
| **M3** the exits' negative control | not a separate run: each M3 run's FIRST pass is the undriven boot that measures where GEMDOS put the image, and it must report `loop_ending` = WB_KEY_ACTIONS_RETURNED over all fifty-two frames. The poke is therefore shown to be what ends the loop, and the three pokes produce three DIFFERENT codes, which no single accident does. **Its records are rescued at `Pterm` like every other M3 run's** — `m3fault`'s pass-one machine is left hooked exactly as its driven runs are, so it too can crash, be reset and have `--auto` rewrite the very numbers every poke below is aimed with | ✅ `smoke.py m3` pass 1 |
| **M3** the cheat word's own control | the row that completes "the same target on a **different condition**". `$556` is `tst.w $604` THEN `cmpi.b #$31,$879`, and the level-skip drive sets both — so a port that had dropped the word test would still report `loop_ending` = 2 and stay green. A fourth run pokes **N alone**, with `WB_KEY_SEQUENCE_MATCHED` left clear, and requires the loop NOT to end: measured, `loop_ending` = 0 over all fifty-two frames. The two runs are one differential over one poke, and its inputs are DERIVED from the level-skip arm's own poke set minus the word, so the control cannot drift from the thing it controls | ✅ `smoke.py m3` |
| **M3** the `Pterm` hand-back | Joust's discipline, and it is asserted from OUTSIDE the program: the run carries on thousands of vblanks past the exit for the health scan, and at two moments **chained off the program's own `Pterm`** (+1 vblank, then +20) the debugger reads the machine itself. Both installed vectors have stopped being the shim's (`$70` `0x126b4`→`0xfc06c0`, `$118` `0x126c4`→`0xfc3aec` under TOS 1.04), and **TOS's own frame clock `_frclock` is still advancing** — `0x717` then `0x72a`, +19 over the nineteen vblanks between the two readings, which is the liveness half: a vector handed back to a handler that does not run leaves it frozen. The record's own teardown read-backs say the same thing from the inside, through a different path | ✅ `smoke.py m3` |
| **M3** the hand-back control | `build.sh m3fault` is the frame build whose `teardown` never stores the two vectors back — `novbl`'s shape at the other end of the run, one store each suppressed and nothing else. Every hand-back row must go red and every ending row must still hold, which it MEASURES rather than claims: all three endings still fire and report their own codes, while `$70`/`$118` are still `0x126b4`/`0x126c4` one vblank after `Pterm` and `_frclock` is frozen at `0x717` (+0 against a handed-back machine's +19). **AND AT THAT MOMENT THE MACHINE SHOWS NO FAULT AT ALL** — the failure mode of an incomplete hand-back is a SILENT DEAD TOS, which no exit status and no crash scan could have caught. Later in the same run it stops being silent, and §12 records what that cost the control's first design | ✅ `smoke.py m3fault` |
| **M3** the joystick arms | the shim's ACIA handler files a report on `$fe`/`$ff` and **those arms have still never executed under any headless check**. What changed this round is that the boundary is now MEASURED instead of assumed. Hatari 2.6.1 does have a headless input path — `--control-socket` plus `hatari-event keydown/keyup <ST scancode>` — and it works: injected scancodes `$50`, `$29` and `$4b` arrive in `WB_KEY_LAST_SCANCODE` through the real ACIA interrupt, with the shim's own `ikbd_bytes` counter rising from 3 to 10. **It does not reach the stick**: that path presses a KEY at the emulated IKBD, while `--joy1 keys` maps HOST SDL key events, so `WB_JOY0_STATE`/`WB_JOY1_STATE` stayed `$00` under all four injected scancodes including both arrow keys. **PARTIAL BY CONSTRUCTION** — Joust's own wording — with `bash atari/run.sh` the discharging mechanism and a person at the cursor keys the only thing that runs those two arms | ⚠️ measured, and the arms still unexecuted headless |
| **M3** the runner's exec line | the one command no headless mode executes, and it shipped broken: `--sound on` sat in `atari/run.sh` through thirteen green modes and Hatari rejects it at parse time (`--sound` takes a FREQUENCY). `run.sh parsecheck` now builds the identical argument array and hands it to Hatari with `--help` appended, which parses every option before it and stops without booting; the mode adds the control that makes it a check — the SAME line with the rejected value put back must be refused | ✅ `smoke.py runsh` |
| **M3** a saved-state round trip | Joust's `HIGH.SCO` equivalent. **ABSENT BY CONSTRUCTION, not deferred**: `../project.toml`'s byte scan establishes that Wonder Boy performs no file I/O at all — one GEMDOS trap in the whole image, a `Super` — so there is no file for a round trip to exist over | n/a |
| **M4** frame differential vs the original | ~~blocked on M2~~ — **DELIVERED AS PART OF M2**, above: the two rows are the same comparison, and separating them was an artefact of expecting the dump to be a later milestone than the frame. The row is kept so the renumbering is visible rather than silent | ✅ folded into `smoke.py m2` |
| **M5** the hardware-state vector | at the same four anchors, **twenty registers of the machine itself are identical on both sides** — the sixteen shifter pens, the resolution and sync registers, the refresh rate and the V-overscan — captured by the same debugger commands and read back by the same parser on each side (`original.py`'s `vector_commands` / `hardware_vector`). Our side is anchored on `capture_the_frame`'s own entry, at the address the binary **reports about itself**, so the vector is taken at the very instant `FRAME.BIN` is. The YM-2149's sixteen registers are captured and **printed but not compared**, for two named reasons (§10) | ✅ `smoke.py m5` |
| **M5** the rendered picture | Hatari's own `screenshot` at **every one of the four anchors**, byte-identical PNGs. Both sides stop-then-shoot (break at the anchor, run on to the next vblank, photograph a completed frame) with `--frameskips 0` and `--drive-led off`. **The bound is measured, not assumed**: two runs of each side produce byte-identical pictures at all four (§10) | ✅ `smoke.py m5` |
| **M5** injected-fault control | `build.sh m5fault` corrupts **one pen** (pen 3, `$777`, the HUD's white — certainly on screen) on its way to the shifter. The three surfaces that read COLOUR — the pens, the vector, the picture — must go red and the framebuffer must not; and the vector's divergence must be **that pen and nothing else**, asserted | ✅ `smoke.py m5fault` |
| **M5** mis-anchor control | our anchors read off the NEIGHBOURING shipped frame. The complement of the above: the bitplanes and the picture must fail (over the pairs a shift can reach — the rest excluded and printed), and the pens and the vector must NOT, because the palette is the same at every anchor and a frame shift writes no different register. Between the two controls **every surface fails in at least one and the three isolable ones pass in the other**; the rendered picture fails in both, because it reads colour AND drawn bytes (§10) | ✅ `smoke.py m5skew` |
| **M5** the flash arms | `WB_FLASH_TIMER` armed on **both** sides with the original's own operand (`move.w #$2,$714.w` at `$1328`), at the same instant — our shim before its first `game_main_loop`, the shipped binary by a debugger poke at `$4a0`'s first arrival. A declared fabrication, because the raiser is unreachable in this window twice over (§10). Colour 0 goes white at anchor 1 and black at anchor 2, on both sides, and all four surfaces still agree | ✅ `smoke.py m5flash` |
| **M6** the frame heartbeat | over the same fifty-two frames, `flip_screen`'s **screen-base publications are the shipped binary's, flip for flip** — fifty-two addresses in order, ours equal to theirs plus `image_base`. No snapshot sees this: M2 and M5 read four anchors, and a run that visited the right buffers in the wrong order at the other forty-eight would pass both. The two sides' write COUNTS differ and the difference is pinned rather than tolerated — one transient a frame on our side against none (§3's correction), two idle writes against one, and one leading publication because the shipped boot leaves `WB_SCREEN_BACK` on the shifter where our shim leaves `WB_SCREEN_FRONT` (§5) | ✅ `smoke.py m6` |
| **M6** no redundant palette load | neither side loads a palette while a stage runs, and neither ever re-loads the table already on the chip. This is the sibling project's **773-stomps** shape, where a VBL handler re-armed `_colorptr` every vblank and every snapshot stayed green because all 773 loads wrote the same correct sixteen words | ✅ `smoke.py m6` |
| **M6** the re-arm control | `build.sh m6rearm` re-publishes the staged palette after every frame — the same sixteen words, so not one pen ever holds a different colour. The palette rows must go red **and the snapshots must not**, which the control MEASURES rather than claims: it runs M2's whole frame differential and all four anchors' pictures and pens are still byte-identical to the shipped binary's, with **52 palette loads on the bus, 51 of them redundant** | ✅ `smoke.py m6rearm` |
| **M6** the sound | **this project's first on-target assertion about sound.** The shipped binary's 1,155 PSG writes over the window are an **exact prefix of our 6,424** — register and value, in order. A prefix rather than an equality because the music is driven by the VBLANK and the window is bounded by FRAMES, and the two sides spend a different number of vblanks on a frame (about 2 against 11½); the direction is measured, and the floor is the shipped side's own count. §10 records why a snapshot could not supply this and named this stream as the surface that could | ✅ `smoke.py m6` |
| **M6** the sound's reproducibility gate | `original.py psgnoise` boots the shipped binary a **second** time and differences the two streams, because comparing a register the original writes differently on two of its own boots is not evidence in either direction. `m6` refuses to run without the reading and PRINTS what it excludes. Measured: an unflashed pair differs in **0 of 1,155** writes, so `m6` compares all eleven registers; a **flashed** pair differs in **42 of 1,155**, all of them channel A's tone period (registers 0 and 1) inside the first eleven frames, so `m6flash` excludes those two and compares the other nine. One reading per fabrication, which is `flashnoise`'s rule (§10) | ✅ `original.py psgnoise` / `flashpsgnoise` |
| **M6** the ORDER-ONLY mutant | **MEASURED DYING, and it is the last of the four shifter-sink mutants.** `flip_screen`'s timer store and its colour write are adjacent statements whose argument is the already-decremented local, so swapping them writes the same word to RAM and the same colour to the chip — only later. With it applied, `m5flash` is **entirely green** (framebuffer, pens, hardware vector and rendered picture at all four anchors) and `m6flash`'s order row is **RED**. Both sides are watched, and both must show the store reaching the bus before the colour | ✅ `smoke.py m6flash`, mutant CAUGHT |
| **M6** the play build | the build a person plays, booted headless past 12,000 vblanks: **still flipping buffers when the run was cut off**, machine healthy throughout — 1,004 frames under TOS 1.04 and 1,160 under EmuTOS, i.e. four to five frames a second (the ROM decides how much of the window is left after it boots, so the count belongs to the ROM too). The two buffers are found in the trace rather than computed — a play run writes no record — and pinned by being exactly `WB_SCREEN_FRONT - WB_SCREEN_BACK` apart. What is asserted about its exit is that THIS run reached none, because it injects no input; a person can reach one, and what happens when they do is M3's, driven on the frame build that shares this build's whole exit path | ✅ `smoke.py play` |
| **M7** the title screen, DRAWN | the first picture here the reconstruction PRODUCES rather than inherits. From **M1's image** — the shipped `SWB.PRG` plus `gen_image.py`'s seeds, no measured RAM — the boot's own five-call title slice runs on the machine: `load_resource_by_index` asks GEMDOS for `TITLESCR.RAD` **across the file-load seam**, `rad_depack` inflates its 16,620 shipped bytes to 32,128, and `set_palette` puts sixteen words on the chip. Against the shipped binary at `$e556`: **0 of 32000 framebuffer bytes differ and all sixteen pens agree**. The geometry is pinned from the file's own header rather than described, and the Copylock is left UNARMED with the flag and the load's return both asserted (§13) | ✅ `smoke.py title` |
| **M7** different-picture control | `build.sh titlecredits` aims the same three calls at the game's OTHER shipped picture. Every precondition is asserted normally and only the two picture rows are inverted; the mode refuses to pass if the other picture breaks none of them. Measured: **both** break — 21,581 of 32,000 bytes over 200 scanlines, and fifteen of sixteen pens (pen 0 is black in both) | ✅ `smoke.py titlecredits` |
| **M7** the two named mutants | the control breaks BOTH picture rows, so it says nothing about either alone. Two mutants do: the depack destination moved one word (**CAUGHT** — geometry red, 21,904 bytes differ, pens untouched) and `set_palette` deleted (**CAUGHT** — `pens_readback_failed = 0xfffe`, pens 1-15 differ, **0 of 32000 framebuffer bytes**). The second is the fail/pass partition, and the two rows are therefore separately breakable (§13) | ✅ both CAUGHT |

**Batch 44 phase B drew the first picture of the game's own.** The eighteen on-target modes — the
sixteen below plus **`title`** and **`titlecredits`** (§13) — are green on **both ROMs**. That phase
also landed the **file-load seam** (the kit's `include/disk.h`), which gives the backend its seventh
symbol, and it found the seventh on-target bug: the `Super(0)`/`Super(ssp)` round trip had been
correct by the compiler's stack scheduling and nothing else, under every green mode before it.

**Batch 43 phase F walked the ladder's last rung.** All **sixteen** on-target modes of that batch —
`m1`, `mono`, `novbl`, `m2`, `m2fault`, `m5`, `m5skew`, `m5fault`, `m5flash`, `m6`, `m6rearm`,
`m6flash`, **`m3`**, **`m3fault`**, `play`, **`runsh`** — are green on **both ROMs**. Every milestone from M1 to M6 now has
a control of its own, and the one thing on this page that is still owed is not a rung: it is the boot
chain outside the spine (§2). §12 has the argument, and the phase's own two findings are in "The bugs
found on target": an uncapped wait that hung the exit on every key-driven ending, and a launcher
command line that never parsed.

**Batch 43 phase E added the seven M6 rows, killed the LAST shifter-sink mutant, and shipped
`run.sh`.** §11 has the argument. Three things that phase produced that are worth a summary line:

- **No shifter-sink mutant survives.** The order-only one is dead, measured both ways (§11).
- **The sound has an on-target assertion** for the first time, and a reproducibility gate under it.
- **§3 was wrong and is corrected**: this port ADDS a transient to the screen-base publication that
  the original does not have. Three phases of snapshots could not see it; the first ordered read of
  the bus did.

**Batch 43 phase D added the five M5 rows and killed the flash mutant.** §10 has its argument,
including the two things M5 captures and does *not* compare and why.

**Batch 43 phase C moved no row.** It fixed the host-side worker crash (`../STATUS.md`) by routing
`../src/map.c` and `../src/scene.c` through `../include/bus.h`, which changes the sixteen sources
this directory cross-compiles — so all five modes were rebuilt and re-run on both ROMs, and M2 is
still byte-exact at all four anchors (584 vblanks for 52 frames, against phase B's 583; phase F's
build reads 588). **It also
left an unpinned modelling decision on target, and it is recorded rather than claimed:** `bus.h`
answers an address outside the game's 1 MB with zero and drops a write there, while a real ST has
real RAM or the `$ff8000` I/O page. `build.sh`'s seam tripwire cannot see it — `os_in_image` is
already a declared on-target helper and `bus.h` is a header, not a core — and no framebuffer, pen or
`M2.BIN` field would move. Named in "Known gaps".

Verified on **TOS 1.04 and EmuTOS** (Hatari's bundled `tos.img`). **NOT "identical results on both
ROMs"** — the honest split is that M1 is green on both, and two of its pieces behave differently:

- **The image lands somewhere else, and M1 notices.** The M1 build's `image_base` is `0x2ae00` under
  TOS 1.04 and the frame builds' is `0x4a700`; under EmuTOS the M1 build lands at `0x33900` and the
  frame builds at `0x53100`. The published screen base follows it in every case. **All four are
  readings that move with the `.PRG`'s own length as well as with the ROM** — this batch's exit-path
  fix moved the frame builds by `0x100` — so they are quoted as measurements and nothing asserts
  them. The translation in §3 is therefore demonstrably
  not a constant that happens to be right.
- **AND M6 TURNED THAT INTO A HARDWARE CONTROL FOR §3's CORRECTION.** The added transient exists
  exactly when the image base's middle byte carries into the high one. `0x4a700` carries and
  `0x53100` does not — so the **same binary** publishes 52 transients on TOS 1.04 and **none** on
  EmuTOS, with the idle-write count taking up the slack (104 against 156). `expected_base_shape`
  derives all three counts from the two buffer addresses rather than pinning the TOS 1.04 reading,
  which is what lets one assertion be right on both ROMs. Writing them down instead is exactly what
  this phase did first, and all three went wrong at once the moment the other ROM ran them — the
  tell that they were one fact recorded three times.
- **The YM2149 check is only non-trivial on TOS 1.04, AND THE CONTROL KNOWS IT.** Port A reads
  `0x25` at entry there and `0x27` under EmuTOS — i.e. EmuTOS has *already* deselected the drives,
  so on that ROM the assertion is satisfied by the entry state and witnesses nothing. It is the
  TOS 1.04 run that measures a change (`0x25 → 0x27`), and the `novbl` control there that shows the
  change is the reconstruction's doing (`0x25 → 0x25` with the vblank suppressed).
  **On EmuTOS the control would otherwise report a FALSE RED** — "did not break the check it exists
  to break", against a control that was working perfectly — so `machine_driven()` decides membership
  from the recorded entry byte and PRINTS the exclusion. A check quietly dropped from a control is a
  check nobody is running. Two ROMs, one of which can see this check.

**TOS 1.02 never runs the program at all** under a Hatari GEMDOS drive — the sibling project's
finding, reproduced here: no `STATS.BIN`, nothing `Pexec`'d. That is a Hatari/TOS hard-disk
limitation rather than a property of this build, and it is why `smoke.py` walks `tools/hatari/`
**newest first**: a plain `sorted()` picks `TOS102US.img` over `TOS104US.img`. (Its memory-sizing
probe also sits at `PC=$fc0186` rather than 1.04's `$fc0174`, so the fault allowlist would need a
third entry before that ROM could ever report cleanly. Not added, because adding it would imply the
ROM is supported.)

Run against more than one ROM anyway: two of the three bugs the sibling port found on target were
found by adding a *second* observation, and a second ROM was one of them.

## Play it

```bash
bash atari/run.sh          # builds the play build if needed, then opens Hatari with a joystick
```

Cursor keys move, **Right-Ctrl** fires (Hatari's `--joy1 keys`; F12 → Joysticks shows the mapping),
**Ctrl-Q** quits. The script's header is the honest description of what appears, and three lines of it
matter before you start:

- **You get the first playable stage, mid-game.** `game_main_loop` is entered the way the original
  enters it — `jmp $4a0` with a stage already loaded — and the chain that loads one is unported
  (§2), so there is no title screen, no credits and no attract mode. The stage comes from the
  ORIGINAL's own post-boot RAM, measured off a real emulated machine. (The title screen the
  reconstruction CAN draw is `build.sh title` — §13 — and it is a measurement, not a session: it
  draws the picture, photographs it and hands the machine back.)
- **It runs until you close the window,** and that is measured rather than hoped: `smoke.py play`
  boots the same binary headless for 12,000 vblanks and finds it still flipping buffers at the end.
- **It runs at four to five frames a second** (measured headless: 1,004 frames in 12,000 vblanks
  under TOS 1.04, 1,160 under EmuTOS, on an 8 MHz 68000). The
  reconstruction is C compiled for a chip the original was hand-written for and no work has gone
  into that gap. It is the game running and responding, not the game at speed.

It **takes the machine** — real vectors at `$70` and `$118`, as the original does — and normally
never gives it back, so Ctrl-Q is the way out and the headless run writes no `STATS.BIN`. *Normally*
is exact: `run_frames` lost its frame count and its watchdog in this build but kept its third exit,
so a frame in which `game_key_actions` takes one of its three endings DOES leave the loop, hand the
machine back and write a record. No input means no ending, which is why the headless run never sees
one. **What happens after that hand-back is now asserted** rather than left to a person to discover:
§12 has it, driven on the frame build, which shares this build's whole exit path.

**And the last defect on that path was found by driving it.** A key left in `WB_KEY_LAST_SCANCODE`
when the loop ends — which is exactly what pressing ESC or N to leave does — used to make
`pin_sched_wait8` aim an *uncapped* wait at that scancode and hang the program for ever, so the
machine was never handed back at all. §8 has the fix and the isolation.

## Use

```bash
brew install m68k-elf-gcc hatari              # one-time

bash atari/build.sh m1    && python3 atari/smoke.py m1      # M1
bash atari/build.sh m1    && python3 atari/smoke.py mono    #   ...its HARDWARE control
bash atari/build.sh novbl && python3 atari/smoke.py novbl   #   ...and its negative control

python3 atari/original.py dump                              # M2's image: MEASURED, not computed
python3 atari/original.py frames                            #   ...and the shipped side's frames
bash atari/build.sh m2    && python3 atari/smoke.py m2      # M2, the frame differential
bash atari/build.sh m2    && python3 atari/smoke.py m2fault #   ...and its MIS-ANCHOR control

python3 atari/original.py vecnoise                          # M5: which registers are one boot's luck
bash atari/build.sh m2      && python3 atari/smoke.py m5      # M5, the hardware-state vector
bash atari/build.sh m2      && python3 atari/smoke.py m5skew  #   ...its mis-anchor control
bash atari/build.sh m5fault && python3 atari/smoke.py m5fault #   ...and its INJECTED-FAULT control
python3 atari/original.py flash                             # the flash run's own boot of the original
python3 atari/original.py flashnoise                        #   ...and its own accident measurement
bash atari/build.sh m5flash && python3 atari/smoke.py m5flash #   ...and the flash arms, both sides

python3 atari/original.py timeline                          # M6's shipped STREAM, over 52 frames
python3 atari/original.py psgnoise                          #   ...M6 REFUSES TO RUN WITHOUT THIS
bash atari/build.sh m2      && python3 atari/smoke.py m6      # M6, the ordered write timeline
bash atari/build.sh m6rearm && python3 atari/smoke.py m6rearm #   ...and its RE-ARM control
python3 atari/original.py flashtimeline                     # the flash run's own stream...
python3 atari/original.py flashpsgnoise                     #   ...and its own reproducibility gate
bash atari/build.sh m5flash && python3 atari/smoke.py m6flash # flip_screen's last PAIR, in bus order

bash atari/build.sh m2      && python3 atari/smoke.py m3      # M3, THE THREE EXITS + the hand-back
bash atari/build.sh m3fault && python3 atari/smoke.py m3fault #   ...and its HAND-BACK control

python3 atari/original.py title                             # M7: the SHIPPED title screen at $e556
bash atari/build.sh title        && python3 atari/smoke.py title        # M7, THE TITLE DRAWN HERE
bash atari/build.sh titlecredits && python3 atari/smoke.py titlecredits #   ...its PICTURE control

bash atari/build.sh play    && python3 atari/smoke.py play  # the PLAY build, booted headless
python3 atari/smoke.py runsh                                #   ...and the line run.sh actually execs

python3 atari/original.py variance                          # what in the dump is one boot's luck
python3 atari/original.py neighbour                         #   ...and the anchor's own evidence (§9)
python3 atari/original.py nofire                            #   ...and the two boot controls
python3 atari/original.py nodisk2
```

**M6 is `original.py` first, twice over.** `smoke.py m6` refuses without `build/OTIMELINE.json` (the
shipped binary's own stream, which cannot be computed) and refuses again without
`build/PSGNOISE.json` (which of the shipped binary's PSG registers are one boot's accident) — the
same refusal `m5` makes over `VECNOISE.json` and for the same reason. Both readings are **stamped
with the frame count they cover**, and one taken over a different window is refused rather than
allowed to license this one. `m6flash` needs the `F`-prefixed pair of its own, because a flashed
boot is a different machine (§10).

**M5 is `original.py` first too, and `vecnoise` is not optional.** `smoke.py m5` refuses to run
without `build/VECNOISE.json`, because without it the mode does not know which of the shipped
binary's own registers are reproducible and would be comparing music cursors (§10). The reading is
**stamped with the anchors and the register names it covers**, and a run whose anchor set it does not
cover is refused rather than licensed by a measurement of different moments.

`m5flash` needs **two** boots of its own — `original.py flash` for the artefacts and
`original.py flashnoise` for the reading. They are separate because the flashed boot is a *different
machine*: colour 0 there is driven by a countdown the debugger seeds and `flip_screen` decrements, so
`pen00` is a compared register whose reproducibility the unflashed reading says nothing about. That
is why the flash artefacts carry their own `F` prefix, `VECNOISE.json` included.

**M2 is `original.py` first, always.** The image it needs cannot be computed — see §2 — and
`build.sh m2` refuses rather than building against a missing dump, or against one whose three
artefacts are not all from the same boot (they carry a manifest; the build verifies it). The dump
needs **both shipped `.stx` disks** in `../bin/`. `neighbour` runs after `variance`, because the
floor it has to clear is derived from the noise `variance` measures rather than written down.

`smoke.py` finds a TOS ROM in `$WB_TOS_ROM`, then `tools/hatari/TOS*.img` newest first, then
Hatari's bundled EmuTOS. Hatari needs `--memsize 4`: the 1 MiB image is the program's BSS. `build/`
and `disk/` are gitignored build artifacts; the full Hatari log of the last run is kept in
`out/hatari.log`, always, whether the mode passed or not.

**RUN ONE MODE AT A TIME.** `disk/` is a single staged drive and every mode — and `run.sh` —
restages it for its own build, so two of them at once means one machine's `.PRG` changing under the
other while it boots. Measured, in this directory's own final sweep: `m5flash` came back "no
`M2.BIN` — the frame build never reached its own dump" and passed immediately when re-run alone,
because a `run.sh` staging test had rewritten the drive mid-boot. **A mode that fails for a reason
reading like a crash and then passes in isolation is this, not a red.**

## Pieces

| file | role |
|------|------|
| `wonderboy_backend.c` | **the seven kit symbols, made hardware** — plus the three shifter sinks and the freestanding `memset`/`memcpy`/`bzero` this `-nostdlib` link has no libc for (`bzero` is the compiler's own rewrite of `clear_message_buffer`'s 6400-byte clear in `../src/text.c`, and the only libc symbol the cores reach) |
| `wonderboy_main.c` | the shim: stage the image, take the machine, run, hand it back, write `STATS.BIN` |
| `wonderboy_os.s` | `_start`, the TOS trap wrappers, the two interrupt entries (`movem` pair + `rte`, and the MFP end-of-interrupt), and `wb_leave_supervisor` — the way BACK out of supervisor mode, which is not `Super(ssp)` and bug **7** says why |
| `shim_include/tos.h` | the trap wrappers' prototypes — a short list, because the game issues one trap in its life |
| `shim_include/wonderboy_target.h` | the two seams the cores name (`../src/game.c`, `../src/stage.c`) |
| `shim_include/string.h` | a freestanding `<string.h>` — needed by the **kit's** `os.h`, not by the cores; deleting it on the grounds that nothing under `../src/` calls a string function fails the build in fifteen translation units |
| `original.py` | **the shipped 1989 disks, driven under Hatari to a named anchor** — the post-boot RAM dump M2's image is, the register file and palette that go with it, the mis-anchor and reproducibility measurements, the two boot controls, the shipped side of the frame differential, and (M7) the title screen at `$e556` |
| `gen_image.py` | the staged image — and **the honesty line** about what a staged image is not |
| `tos.ld` / `mkprg.py` | link at base 0, then wrap the ELF into a GEMDOS `.PRG` with a relocation table |
| `build.sh` | compile + link + wrap + stage `disk/`, and assert the seam actually held |
| `smoke.py` | headless Hatari: boot, run to completion, read `STATS.BIN` back, check it |
| `run.sh` | **the one that is not a measurement** — build the play build and open Hatari with a screen, sound and a joystick. Its header is the honest account of what appears |

## The boundary decisions

### 1. The seam is the LINK, not the include path — and that is a fact about this game

Joust needs a `shim_include/os.h` that shadows the kit's with `#include_next`, because the five
helpers it replaces (`os_bconstat`, `os_bconin`, `os_super`, `os_giaccess`, `os_random`) are
`static inline` in the kit header and have no symbol to override. **Wonder Boy calls none of them.**

`../project.toml`'s exhaustive byte scan of `SWB.PRG` establishes why: of the sixteen `trap #N`
encodings, exactly one occurs as a real instruction in the whole image, and it is a GEMDOS `Super`.
The game drives the WD1772, the DMA chip, the MFP, the ACIA and the YM2149 itself. So every kit
dependency the reconstruction has is a **real link-time symbol**, and the seam is simply: leave the
kit's own C sources out of the link and supply your own.

**THE SURFACE IS A SET, AND IT IS SEVEN SYMBOLS.** Taken from the union of the seventeen
translation units' undefined symbols minus the game's own; `nm` on the differential `.so` agrees.

| symbol | call sites | on target |
|---|---|---|
| `hw_read8` | 5 — `../src/rng.c`, `../src/behavior.c` ×2, `../src/sound.c` ×2 | the read itself |
| `psg_port_write` | 10 — `../src/game.c`, `../src/sound.c` ×9 | `$ff8800` select, `$ff8802` data |
| `psg_port_read` | 3 — `../src/game.c`, `../src/sound.c` ×2 | select, then read back through `$ff8800` |
| `sched_wait8` | 1 (two wait SITES reach it: `$60e`, `$64e`) | an uncapped spin; the ACIA interrupt ends it |
| `sched_poll16` | 2 — `flip_screen`'s two waits, `$6aa` and `$6d0` | one uncapped iteration; the caller owns the predicate |
| `disk_read_file` | 1 — `load_resource_by_index` (`$e782`), `../src/boot.c` | GEMDOS `Fopen`/`Fread`/`Fclose`. THE FILE-LOAD SEAM (§13) |
| `os_refused` | 1 — `../src/sound.c:786` | **not defined**: `-DOS_NO_REFUSAL_TALLY` makes the kit's `os.h` serve an inline identity |

And the complement, because a set is only a claim if its complement is one: `sched_poll8` has **0**
direct call sites and is deliberately *not* defined, so a future core that calls it gets a link
error; `g_dosound` has **0** — this game never issues XBIOS `Dosound`; the whole staged-file model
and the whole TOS trap model have **0** each.

**`build.sh` asserts the seam rather than describing it**, in both directions: no `g_hw_reset`,
`g_psg_reset`, `g_sched_reset`, `g_dosound`, `g_os_refusal_reset` or `sched_poll8` may appear in the
`.PRG` (a kit source leaking into the link would reintroduce the model silently, and the build would
"verify" against it), and all six of the symbols the backend owes **must**.

### 2. The staged image, and what it is a fabrication of

`gen_image.py` emits the differential harness's own base image — the relocated `SWB.PRG` over
`[0x3f8, 0x218d0)` — with seven named seed words in it. It uses the kit's own loader, so the bytes
the `.PRG` carries on target are the bytes every green test in `../test/` ran against.

The program's own bytes have to be there although none of them execute: `SWB.PRG` has no data or bss
segment, so all 0x214d8 bytes of text are also every table the cores index — the behaviour dispatch
at `$938`, the sprite descriptors, the strings, the sound module at `$17adc`, the palette table.

**A STAGED IMAGE IS A DECLARED FABRICATION OF THE BOOT'S RESULT, AND THIS ONE FABRICATES ALMOST NONE
OF IT.** What the boot produces and this image does not contain is enumerated in `gen_image.py`'s
header, with an address range each: the tile bitmaps at `$1d43e`, the depacked level overlay at
`$217d8`, the sprite descriptors and cell data at `$24898`/`$25298`, the eight pre-shifted scroll
buffers over `$44000..$70000`, and both screens. Two of the routines that produce those are not
merely unported but **unreconstructed** (the tile installer at `$e67e`, `sprites_cru_install` at
`$e87c`), so their products cannot be computed host-side today at all.

So the M1 image can run the routines that read the PROGRAM, and it cannot run a frame. **M1's claim
is drawn exactly on that line** and reaches nothing beyond it.

**THE OBLIGATION IS DISCHARGED, AND THE SENTENCE MOVES RATHER THAN GOING AWAY.** `atari/original.py`
takes the reference this section named as reachable: the ORIGINAL's own post-boot RAM, dumped under
Hatari at `$f8b4`. Every range above is present in the M2 image, measured. What is still fabricated
is the *boot*, not the *data* — the chain remains unported and this image is its result handed over
rather than recomputed, so a port of `$e67e` and `$e87c` would replace the dump. Until then the dump
is the reference and `gen_image.py`'s PROVENANCE table is the receipt, checked on every build.

Two things the discharge cost, both measured rather than assumed:

- **The dump is not the same twice, and the figure MOVES.** Four boots read 536, 538, 591 and 605 of
  523,272 bytes — the Copylock's 512-byte scratch band every time, 12-22 bytes of the playing sound
  driver's state, 8-72 of the game's stack, and `WB_VBL_COUNTER`. `original.py variance` owns that
  number (it prints it and writes `build/VARIANCE.txt`); this file cites the mode rather than
  restating a reading that is stale on the next boot. The mode RAISES on a byte outside those four
  bands *and* on a band that exceeds its ceiling — the band alone is a weak guard, the sound band
  being 13,604 bytes wide to certify a couple of dozen. That guard found the fourth band itself.
  None of them reaches a framebuffer or a pen, which is the whole of why M2's two surfaces can be
  compared exactly against a *fresh* boot.
- **The palette is the boot's product and does not live in RAM.** `set_palette` runs inside the
  unported chain, so an image that staged only memory paints through whatever owned the shifter
  last — measured on the first M2 run, which came back with TOS 1.04's own desktop palette. The
  sixteen pens are dumped at the same anchor and published through the same sink `set_palette`
  writes them through.

### 3. The screen base is TRANSLATED, and it is this port's one piece of real logic

`flip_screen` publishes an address out of the game's *own* address space: `move.b $74d.l,$ff8201.l`
sends bits 23-16 of `WB_SCREEN_FRONT`, whose value is `$070000` or `$078000` — absolute addresses in
the 512 KB map the original owns outright, because `SWB.PRG` relocates itself to `$400` and takes the
machine. **This build does not own the machine.** The reconstruction runs on a 1 MiB array GEMDOS
placed wherever the TPA fell, so the buffer the game means is at `image + $70000`, and `$070000` is
TOS's own memory. Publishing the game's byte unchanged would point the shifter at the operating
system.

So the two bytes are shadowed and re-emitted as `image_base + what the game asked for`, and the
shadow is what makes it possible at all: the two halves arrive in separate instructions and the sum
can carry out of the low half into the high one, so neither byte can be translated without the other.
Both hardware bytes are rewritten on each of the game's two writes.

**The low byte is not lost, and that is an assertion about the base.** An STF's video base register
has no low byte, so an unaligned base is truncated and the shifter displays from up to 255 bytes
below what the game draws at — every byte in memory still correct, the picture's bitplanes permuted.
A `__attribute__((aligned(256)))` does *not* fix that: it aligns the array inside `.bss`, and GEMDOS
loads the `.PRG` wherever the TPA falls. `wonderboy_main.c` rounds the base up once at run time and
**reads the result back**; measured on the M1 run under TOS 1.04, `image_base = 0x2ae00` and the
published base is `0xa2e00` = image + `$78000`. **That number is a reading, not a constant** — it
moves with the `.PRG`'s own length as well as with the ROM, so every figure quoted for it in this
file is stamped with the build and the ROM it came off, and none of them is a value the code may
assume.

**A TRANSIENT IS ADDED, AND M6 MEASURED IT.** This paragraph used to claim the reverse — that the
mixed address the shifter holds between the two byte writes was something this port took over from
the original rather than introduced, on the grounds that the original also writes two bytes in two
instructions. The ordered write timeline (§11) refutes it, and the correction is worth the space
because the reasoning error is a general one: *both sides write two bytes* does not imply *both
sides pass through a mixed address*.

The original's two buffers are `$070000` and `$078000`, which differ **only in the middle byte**. Its
`move.b $74d.l,$ff8201.l` therefore writes `$07` over `$07` every single frame and the high half
never moves: the shifter goes straight from one real buffer to the other and is never pointed
anywhere else. **Measured: zero transients over fifty-two frames.**

Ours cannot do that. The buffers become `image_base + $70000` and `image_base + $78000`, and when the
image base's middle byte is `>= $80` the sum carries into the high byte — so our high byte really
does change, and for one instruction the shifter points at an address that is neither buffer.
Measured under TOS 1.04, with `image_base = 0x4a700`: the pair is `0xba700`/`0xc2700` and the
transient is `0xb2700` or `0xca700`, **once per frame, fifty-two times**. `smoke.py`'s
`expected_base_shape` derives that count on both sides from their own buffer addresses, rather
than pinning it or tolerating it.

It is **TPA-dependent, and that is measured rather than reasoned**: an image base whose middle byte
is under `$80` produces no carry and no transient. EmuTOS puts the frame builds at `0x53100`, and
there the **same binary** produces **zero** transients and three idle base writes a frame instead of
two. So `smoke.py` does not pin a number at all — `expected_base_shape` derives the whole account
(publications, transients, idle writes) from the two buffer addresses, and the two ROMs are then a
hardware control for this paragraph.

What survives of the old paragraph is the reason it does not matter in practice: `flip_screen`
issues both writes between its two waits, i.e. just after a vblank, so the window in which a display
could start from the wrong address is one instruction long and outside the visible frame.

### 4. Both interrupts, and the one the reconstruction does not have

The boot chain's `hw_init_vectors` (`$f8bc`) installs `$70 := vbl_handler` and
`$118 := ikbd_acia_handler`, and the boot continuation at `$e4e6` installs the first again. This
build does the same, at the same real exception vectors — not at a TOS hook — because for the length
of its run it owns the machine as the original does.

`vbl_handler` **is** the reconstruction (`../src/game.c:334`), called unchanged; `wonderboy_os.s`
supplies only the `movem` pair around it and the `rte`. `../names.txt`'s `cmt 0x716` records that the
reconstruction deliberately drops the original's register save because "a C function's own registers
are its compiler's business" — true off target, where nothing was interrupted; on target the
*interrupted* code's registers are the entry's business.

`ikbd_acia_handler` (`$754`) is **unported**, and it is what writes the byte `sched_wait8` spins on,
so without a stand-in the two key waits are hangs. `wonderboy_main.c` supplies one to `../names.txt`'s
own specification: read `$fffffc02`; `$fe`/`$ff` are the joystick-report headers, after which the
next byte is the report; anything else is a scancode. **The key bitmap is deliberately not
reproduced** — `cmt 0x878` establishes that the watch table is all zeroes with no writer, so no
scancode can ever match and nothing in the image ever reads `$878`.

The MFP end-of-interrupt is `bclr` on ISRB and not a store: the 68901's in-service register is
cleared by writing a **zero** to the bit and ones everywhere else, so a `move.b #~0x40` would clear
every other channel's in-service bit at the same time.

### 5. What is deviated from the boot, and what is inherited from it

Four, each stated because a silent deviation is the same shape as a bug. The fourth was found by M6
and had been invisible for three phases:

- **MFP timers A and B are NOT masked**, although the boot masks them (`$e4e6`: IERA/IMRA := 0). This
  build hands the machine back and does GEMDOS I/O afterwards, both of which want TOS's own clock
  alive. It changes interrupt load, not an image byte.
- **The palette is not cleared**, although the boot clears it (`clear_palette`, `$e7f4`). M1 paints
  nothing, so there is nothing for pens to be wrong about; `set_palette`'s sixteen writes are M2's.
- **The PSG select/data pair is not made atomic**, and that is the original's race reproduced rather
  than a hazard introduced. Two threads write the chip: `snd_music_tick`'s driver from the vblank
  handler, and `snd_psg_silence` / `psg_set_drive_select` from the frame. An interrupt landing
  between a select and its data writes the interrupted register's value into the interrupting one.
  Masking here would be a change to what the machine does that no surface in this project could tell
  from the original, so it is recorded: the surface that would show it is the **PSG write timeline**
  compared against the shipped binary's, which is §11. **It now exists, and it has not shown the race
  firing**: over fifty-two frames the shipped binary's 1,155 (register, value) pairs are an exact
  prefix of our 6,424, decoded through the select/data protocol — so no write in that window landed
  in an interrupting register. That is a window's worth of evidence and not a proof the race cannot
  happen; the decoder files a data write with no select before it under register `None`, which is
  what such a landing would look like.
- **`publish_screen_base` publishes `WB_SCREEN_FRONT`; the original's boot publishes
  `WB_SCREEN_BACK`.** MEASURED by §11, from the writes before each side's window: the boot chain
  writes `$070000` at `$f90c`/`$f914`, which is the staged image's BACK buffer, while our shim
  publishes the FRONT one, `$078000`. Frame 1 then publishes `$070000` on both sides, because both
  run the same image and `flip_screen` swaps the same longwords — so the two agree from frame 1
  onward and the whole consequence is **which buffer is on the shifter for the length of the shim's
  own setup**, before any frame has drawn. It is left as it is rather than "fixed", because
  publishing the front buffer is the defensible thing for a shim to do and changing it to match
  would be choosing the original's arbitrary state over a reasoned one; what M6 does instead is
  **derive it** (`expected_base_shape`, from what each side's entry left on the shifter), so it
  cannot drift unnoticed.

### 6. Every write is read back

Sixteen checks, and **two words rather than one**: `readback_failed` says a write did not take,
`readback_attempted` says which checks *ran*, and `smoke.py` compares the second against an **exact
mask**. A check that quietly stops executing is indistinguishable from a passing one in a bare fault
word — which is how the sibling project's exit detector spent a year scanning an empty string. The
bit names are read out of `wonderboy_main.c` by `smoke.py` rather than restated, and a bit the Python
side has not classified as boot-or-teardown is a hard error.

Unlike Joust, one pair is enough here: neither of this build's two interrupt handlers records a
read-back, so the non-atomic `|=` has no second writer. **The moment one of them gains a check it
needs its own pair.**

Two of the sixteen are weaker than the rest and say so where they are written:

| write | assertion | residual blindness |
|---|---|---|
| the resolution register | read back **masked to two bits** | none — the other six bits are bus noise, and the unmasked compare failed on the first on-target run against a machine that had done exactly what it was told |
| the IKBD reset and mouse-relative bytes (write-only device) | the transmitter is **waited for**, then TDRE asserted | two-deep. TDRE means the last byte reached the *shift* register and is still going out (~1.28 ms), so this witnesses every byte but the final one; and a byte that leaves says nothing about the controller obeying it |

### 7. A control has to be able to fail, and on one ROM one of its checks cannot

`novbl`'s verdict is *inverted*: a run that passes the comparison is the failure. That only works if
every check it requires to break is a check this machine could break. On EmuTOS one is not — the
YM2149 row above — so the control would have reported a false red on a correct build.

`machine_driven(record)` therefore derives the required set from the run's OWN recorded entry byte
rather than from a list written down, drops the entry-state-vacuous check, and **prints why**. Both
halves matter: dropping it silently would be the vacuous-green failure mode wearing the control's
clothes, and the printed note names the ROM that does exercise it (TOS 1.04, entry `0x25`).

### 8. The IKBD acknowledge byte is DISCOVERED, not assumed — and asked for TWICE

`sched_wait8`'s pin is a genuine spin rather than a byte already in place, and it is arranged so that
it cannot hang: the reply is waited for on a bounded loop — which is what establishes that this
machine's IKBD answers at all — and only then is the byte cleared, a further reset sent, and
`sched_wait8` called on the same reply.

The byte itself is **learned**. The IKBD's documented self-test-passed answer to `$80 $01` is `$f0`;
the machine this ran on answered **`$f1`**, and the first draft — which had the constant written down
— failed on a path that was working perfectly. Which byte a controller sends is a property of that
controller's firmware, not of this port. What the pin then establishes is that the answer **repeats**,
which is a stronger claim than the constant was.

**AND THE DISCOVERY HAD TWO WAYS OF LEARNING THE WRONG BYTE, BOTH OF WHICH HANG THE PROGRAM.**
`await_ikbd_reply` returns as soon as `WB_KEY_LAST_SCANCODE` is not `$00`, and it cannot tell the
controller's status byte from a scancode. Aim the uncapped wait at a scancode and the run never
reaches its own dump — no `STATS.BIN`, no `M2.BIN`, nothing to read.

- **A key the FRAME LOOP left behind.** The byte was not cleared before the first reset was sent, so
  whatever the loop had in it was taken for the answer. Found by M3's first key-driven ending, and
  **isolated rather than inferred**: poking the scancode ALONE, with no ending driven at all and the
  loop running its full fifty-two frames, kills the run identically. It is now cleared first.
- **A key that arrives DURING the reply window,** which in a play session is not a corner case but
  the normal path — the player's ESC or N *ends the loop*, and the release of that same key lands
  inside the ~300 ms the reset takes to answer. So the reply is asked for **twice**, and the pin is
  taken only if two resets answer the same byte. A press and a release carry different codes and
  neither repeats, so a stray key cannot survive the agreement. If they disagree the pin is simply
  not taken and `RB_IKBD_REPLIED` and `sched_wait_returned` say so — a measurement the run survives,
  where the alternative is a machine that never comes back.

The cost is a third reset (~300 ms of emulated time) in every run, which `RUN_VBLS`' own paragraph
in `smoke.py` now counts.

### 9. M2, and what an anchored frame is worth

The claim is one sentence: **fifty-two frames of the reconstruction run on a 68000, and at four of
them its screen and its sixteen pens are the shipped 1989 binary's, byte for byte.** Four things make
that more than a coincidence, and one of them is a limit.

**The anchor's margin is measured against the instrument's own noise floor.** Two dumps of the same
moment already differ by ~600 bytes, so "the two moments differ" is true of every pair this tool can
produce — `original.py neighbour` therefore takes `variance`'s reading, requires the mis-anchor to
clear ten times it (measured: ~134,000 against a ~5,900 floor, ~23x), and requires the two
same-anchor boots NOT to. A floor nobody has shown to discriminate is not a floor.

**The anchors are chosen by measurement, and the mis-anchor margin is printed.** This game at the top
of stage 1 draws the *same picture every frame*: with no stick pushed nothing moves. Differencing the
shipped binary's own consecutive frames over its first seventy (`original.py frames 70`) finds
exactly two boundaries — frame 1→2 and frame 51→52 — each moving 988 of 32000 bytes over 24 scanlines
from row 60. So the anchors are `1, 2, 51, 52`, the frames either side of each. **AND IT IS A BLINK,
NOT A COUNTER**: frame 52 is byte-identical to frame 1 and frame 51 to frame 2, so the picture toggles
on a one-second cadence rather than advancing. `smoke.py m2` prints every consecutive margin, saying
which pairs are DETECTABLE and which are IDENTICAL PICTURES.

**The control is the mis-anchor, and it excludes what it cannot break.** `m2fault` reads our frames
off the *neighbouring* shipped frame and inverts its verdict. Because the picture toggles, only two
of the eight rows can be broken by a one-anchor shift; the other six are **printed as excluded**,
with the reason, exactly as M1's `novbl` excludes its entry-state-vacuous check. A row silently
dropped from a control is a row nobody is running.

**The framebuffer cannot see the shifter, so M2 reads it back.** `flip_screen`'s two
`shifter_write_byte`s decide which buffer the machine DISPLAYS; they change no image byte. Both
mutants over them therefore leave every compared pixel correct, and both are caught by one row —
`$ffff8201/8203`, read in supervisor before the teardown:

| mutant | measured under `smoke.py m2` |
|---|---|
| the base bytes swapped **at `flip_screen`'s own two call sites** (the swap in the shared translation was already caught at M1) | **CAUGHT** — the backend wrote `0x84a400` and the 24-bit bus handed back `0x4a400`, against `image + 0x78000` |
| **the wrong buffer published** (`WB_SCREEN_BACK` instead of the front) | **CAUGHT** — `0xb9d00` read back against `0xc1d00` |
| the flash's two arms swapped | **SURVIVES M2, and the reason is measured** — `WB_FLASH_TIMER` is `$0000` in the staged image, so `flip_screen` returns before the write on all fifty-two frames and neither arm executes. Not an M2 weakness to fix but a branch the *anchor's own data* cannot reach. **It dies under `smoke.py m5flash`** (§10), which arms the countdown on both sides |

**`sched_poll16` is discharged, and by the iteration count rather than by the frames.**
`flip_screen`'s two waits are its only callers and they are uncapped spins on `WB_VBL_COUNTER`. A
frame count says they returned; only the count of iterations says they SPUN — i.e. that what ended
them was a level-4 interrupt raising the counter and not a predicate already true. Measured: **~17,100
iterations over 52 frames**, ~330 per frame, against the 2 a wait that never spun would give.

**Both ROMs, and the image lands somewhere else on each.** M2 is green on TOS 1.04 (image at
`0x4a700`) and on EmuTOS (`0x53100`, ~34 KB higher), with the published base following it both
times — so the
translation in §3 is demonstrably not a constant that happens to be right, on the frame path too.

### 10. M5, and what a *machine* differential is worth

M2 compares what the reconstruction DREW and reads one hardware register back. M5 compares **the
machine**: registers captured on both sides by the same debugger commands, and the picture Hatari
actually renders. Six things make that more than a screenshot, and two of them are limits.

**Both sides are measured by one piece of code.** `original.py`'s `vector_commands` writes the
debugger script and `hardware_vector` parses it, and the shipped side and ours both go through them.
The sibling project's writer and reader each grew their own idea of the marker terminator and every
one of its frame modes died at the first anchor; one spelling is the fix.

**Our side is anchored on an address the binary reports about itself.** The shim cannot take this
measurement — the YM-2149's file is not readable through `$ff8800` without a select write, and the
rendered surface is the emulator's — so our build is booted a second time under the debugger. The
breakpoint is `capture_the_frame`'s own entry (`noinline`, address in `M2.BIN`'s `capture_pc`), so
its Nth arrival IS the Nth anchor and the vector is taken at the very instant `FRAME.BIN` and
`PENS.BIN` are. Reading that address out of `build/wonderboy.elf` instead would risk a stale ELF from
a later build; a binary reporting its own address cannot be the wrong binary. **The two boots are
then required to agree** — same `capture_pc`, same image base, same framebuffer, same pens — which is
this mode's determinism control and is what pins GEMDOS having placed the program identically.

**The pens are compared through a second, independent path.** M2's pen row is a CPU read by the
running program; M5's `pen00..pen15` are `savebin` straight out of the register file. The two agree.

**The rendered picture's bound is measured, and it moved twice before it settled.** Both sides
stop-then-shoot — break at the anchor, arm `b VBL > VBL`, photograph at the frame boundary — with
`--frameskips 0`, because under `--fast-forward` Hatari skips *rendering* frames it still emulates.
The first comparison still failed at every anchor, and the cause was not the game: with the statusbar
hidden Hatari draws an activity **LED in the top-right border**, our side touches a GEMDOS drive and
the shipped side does not, and the extra colours pushed Hatari's PNG writer from a palette image to a
truecolour one — so the two encodings could never have matched whatever the pixels did.
`--drive-led off` on both sides. With that, the recipe that owns the number is: run `smoke.py m5`
twice and diff `out/pictures/m5/`, run `original.py frames` twice and diff `build/OPNG*.png`.
**Measured: all four anchors are byte-reproducible on both sides**, so all four are asserted. (The
kept pictures are per mode and the directory is emptied each run — one shared directory would let an
`m5fault` run in between leave a deliberately colour-corrupted picture for that diff to certify
against.) An anchor that is ever measured NOT reproducible goes into `RENDER_NOT_REPRODUCIBLE` with
its reading, and the harness refuses an anchor that is in neither list — an anchor asserted by nobody
has to be an anchor somebody wrote a reason for.

**THE SIBLING PROJECT WAS RE-MEASURED WITH THESE SETTINGS, and the honest split is worth carrying
here because this section's four-out-of-four is the optimistic half of it.** Joust asserts its
rendered compare at one anchor of six and its record attributed that to frame-skip alone. Two boots
of its shipped side, before and after: the drive LED *was* in its pictures — frames 1 and 115 came
back truecolour (IHDR type 2, 5697 / 5839 bytes) and become palette images (3270 / 3407) with
`--drive-led off` — so its rendered assertion had been certifying a picture with emulator chrome in
it, silently, because both sides carried the LED alike. But its deep anchors 150/180/210 still
disagree between two boots afterwards, as at least one did before. **The settings account for the
chrome and not for the drift**, two runs cannot rank two configurations against a nondeterministic
quantity, and Joust's `atari/README.md` carries that residue as a blocker with its trigger and home.
Wonder Boy getting 4/4 is a fact about these four anchors, not evidence that the recipe is
sufficient everywhere. (The sibling project
could only assert one, and the difference is this game — a stage that is motionless between its
one-second ticks.)

**Every surface fails in at least one control, and the three that can be isolated pass in the
other.** The rendered picture is the exception and the table below says so: it reads colour *and* it
reads drawn bytes, so both faults move it and neither control shows it standing still.

**And it reads colour more thoroughly than "which pens are on screen" — it reads ALL of them.** A
palette-mode PNG's `PLTE` chunk *is* the shifter's sixteen colour registers, verified byte for byte
against this game's own pens (`$000` → `(0,0,0)`, `$333` → `(102,102,102)`, `$777` →
`(238,238,238)`). So the picture witnesses a corrupted pen whether or not a single pixel uses it,
and the a-priori reason `m5fault`'s picture arm must fail is the format rather than pen 3 happening
to be the HUD's white. (Pen 3 is still the right choice — a visible pen makes the *pixels* move too,
so the row fails for both reasons rather than only the subtle one. And the corollary bites in the
other direction: a TRUECOLOUR capture carries no such table and would not see it at all, which is
exactly how the sibling project's palette control came to classify its rendered picture as a surface
the fault must not move. §10's Joust note has that measurement.)

`m5fault` corrupts pen 3 on its way
to the shifter: the pens, the vector and the picture must break and the bitplanes must not, and the
vector's divergence must be *that pen and nothing else*. `m5skew` reads our anchors off the
neighbouring shipped frame: the bitplanes and the picture must break — over the pairs a shift can
reach, the rest excluded and printed — and the pens and the vector must not.

| surface | `m5fault` (one pen corrupted) | `m5skew` (one anchor's slip) |
|---|---|---|
| bitplanes | must PASS | must FAIL (2 of 4 pairs; the others are the same picture) |
| pens | must FAIL | must PASS |
| hardware vector | must FAIL, at `pen03` only | must PASS |
| rendered picture | must FAIL | must FAIL (same 2 pairs) |

**THE FIRST LIMIT: the YM-2149's sixteen registers are captured, printed, and NOT compared.** The
vector is 36 entries and the differential looks at 20. Two different reasons, and the first is a
measurement:

* **`ym00..ym13`, the sound chip.** Where the music is at frame N depends on which vblank the boot
  finished on and on how many vblanks each side's frame loop spends per frame, and neither is
  controlled. `original.py vecnoise` boots the shipped binary a *second* time and differences the
  vectors: **`ym00`, `ym02`, `ym04`, `ym08` and `ym10` move between two boots of the shipped binary
  itself** at the same anchors. A snapshot of those is not evidence in either direction, and a
  comparison that happened to pass on them would have passed by accident. Two boots is not a sample
  that could BOUND anything, and the mode says so: what it establishes is one-directional — a
  register that moves is demonstrably one boot's accident; one that does not is not thereby shown to
  be stable. So the exclusion is decided **by kind** (the whole sound-chip file) with that
  measurement as its evidence, and the measurement doubles as a **tripwire**: anything moving that M5
  *does* compare raises, in `vecnoise` and again in `smoke.py`. What is worth reading in the printed
  columns anyway: **at anchor 1 the two sides' whole YM file is identical** apart from the port
  below, and it is only at the deeper anchors that the phase has drifted. **The surface that can
  compare sound is the ordered write timeline, which is M6's and is owed.**
* **`ym14`, `ym15`, the two parallel ports** — not the sound chip at all. Port A carries floppy
  drive select, so whoever owns the machine's disks writes it: measured, the shipped binary (booted
  from its own floppy) leaves `$27`, drives deselected, while our side — loaded off a GEMDOS hard
  drive by a TOS still polling for a floppy — reads `$25`. M1's `RB_PSG_PORT_A_DESELECTED` is where
  that write IS asserted.

Four more entries are captured and **reported rather than compared**: `video_base` (the two sides
legitimately draw from different addresses — ours inside a GEMDOS-placed image, alternating
`0xba600`/`0xc2600`; the shipped binary's own `0x70000`/`0x78000`), and `vbl_counter`, `hbl_line`,
`frame_skips`, which are the emulator's position in its run rather than the machine's state.

**THE SECOND LIMIT: the flash is armed by a declared fabrication, and it is not the game reaching
it.** `flip_screen`'s last four instructions are a white-screen flash gated on `WB_FLASH_TIMER`, and
that word is `$0000` in the staged image, so all four are dead across all fifty-two frames. A census
at full width (`../names.txt` `cmt 0x714`: every operand encoding, cross-checked by scanning the raw
`.PRG` text for the halfword `$0714` at every alignment) finds **exactly one writer that raises it** —
`move.w #$2,$714.w` at `$1328`, `player_weapon_fire`'s LIGHTNING arm — and it is unreachable here
twice over: this run injects no joystick byte, so the `cmp.b #$80` on the newly-pressed byte can
never hold; and the staged image's `WB_EFFECT_RECORD_WRITE_PTR` sits exactly at the list base, i.e.
the player holds no item to fire. So `m5flash` **seeds** the word instead — with `#$2`, that
instruction's own operand — on **both** sides at the **same instant**: our shim writes it
immediately before the first `game_main_loop` (`arm_the_flash`), and `original.py flash` pokes it
from the debugger at `$4a0`'s first arrival, which is the boot's own `jmp` landing before any frame
has run. Two frames of countdown then put a white anchor and a black anchor inside the window, which
is both arms. **What this is not** is the game reaching the flash: it is the two sides given the same
unreachable state and required to agree about what they do with it.

**AND THE FABRICATION IS ASSERTED, NOT PRINTED.** `m5flash` is not a control, so it takes the plain
agree-with-the-shipped-binary path — which means a change that *disarms* it is the worst kind of
green: the seed comes from ONE constant both sides scrape, so zeroing it disarms both, colour 0 never
moves, all four surfaces still agree, and the mode reports success while the mutant it exists to kill
is alive again. **A two-sided differential cannot see a fault that hits both sides at once.** So the
mode carries two rows of its own: our side's `WB_FLASH_TIMER` read back out of the image *after*
seeding must equal the seed (and must be `$0000` in the other three modes), and the shipped binary's
flashed boot must **differ from its own unflashed boot** somewhere in the compared set — measured
against the artefacts on disk rather than against an expectation.

With it armed, the survivor dies:

| mutant | measured under `smoke.py m5flash` |
|---|---|
| **the flash's two arms swapped** (`flash ? 0 : WB_FLASH_COLOUR_WHITE`) | **CAUGHT** — on three surfaces and at both arms: at anchor 1 colour 0 reads `$000` where the shipped binary has `$777`, at anchor 2 `$777` where it has `$000`, the pens row and the vector's `pen00` both red at all four anchors, and the rendered pictures differ |
| the sink write moved above the timer store | **SURVIVES, and the reason is structural** — moving `shifter_write_word` above `wr16(image + WB_FLASH_TIMER, flash)` changes no value at all, only the ORDER, because the argument is the already-decremented local. No snapshot can see it, and adding more snapshots never will. **It is M6's**, and M6 is the ordered write timeline |

That leaves **one** of the four shifter-sink mutants alive, and it is the one whose home has always
been the next milestone rather than this one.

### 11. M6, and what an ORDER is worth

M2 compares what the reconstruction drew at four instants. M5 compares the machine's registers and
the rendered picture at the same four. **Every one of those is a snapshot, and a program that
arrives at the right state by a wrong route passes all of them.** M6 is the surface they are all
blind to: what reached the hardware, in what order, across all fifty-two frames.

**THE MUTANT THAT MADE IT NECESSARY, and it is now dead.** `flip_screen`'s last two statements are
`wr16(image + WB_FLASH_TIMER, flash)` and `shifter_write_word(WB_SHIFTER_PALETTE, ...)`. The
argument is the already-decremented local, so **swapping them changes no value anywhere** — the same
word reaches RAM and the same colour reaches the chip. `../STATUS.md` measures it surviving the whole
differential suite, and it survived every check in this directory too. Applied, and measured:
`m5flash` stays **entirely green** — framebuffer, sixteen pens, twenty hardware registers and the
rendered PNG, at all four anchors — while `m6flash`'s order row goes red with exactly the predicted
shape (the first decrement is followed by the *next* frame's colour write, and the last decrement is
followed by none at all). That pair of runs is the whole argument for this section.

**THE INSTRUMENT IS `--trace io_write`, and not the sibling project's two flags.** Two measured
reasons. First, this game's timeline needs `flip_screen`'s screen-base publication, and
`--trace video_addr` emits **nothing at all** for a write to `$ff8201`/`$ff8203` on Hatari 2.6.1 —
zero lines over a whole run. Second, one stream removes any question of how two trace channels
interleave, and interleaving is the only thing this check measures.

Three things about that instrument are worth carrying, because each of them cost a wrong reading:

- **The same register is named two ways in one log.** Code that sign-extends a short absolute
  reaches `$ffff8800`; code that does not reaches `$00ff8800`. It splits along the two sides — TOS
  and our C write the first, the shipped 1989 binary writes the second — so a parser keyed on the
  printed spelling reads one side's stream as EMPTY and passes. Addresses are masked to 24 bits.
- **Hatari collapses repeated lines** into `N repeats of: …` on a doubling schedule. Measured over
  both sides' whole runs, the only line it ever collapses is the MFP's `$fffffa11 = $00` — none of
  the five registers this reads — but a collapsed run would silently shorten a stream compared
  element for element, so it is **detected and refused** rather than expanded on a guess about
  whether the printed count is cumulative or incremental.
- **A window opens with a base already on the shifter, and the classifier has to be told.** Started
  from zero, the first write of a window — `flip_screen`'s high byte, which changes nothing — reads
  as the window's first publication. Measured: that gave our side 53 publications for 52 frames and
  put the whole sequence one flip out of phase, **while the shipped side's own count came out right
  by accident**, because its stale first byte `$07` happens to name a real buffer on its own. Both
  sides now carry the address their window opened on.

**HATARI HAS NO RAM-WRITE TRACE, so the order mutant needed a second probe.** The RAM half of the
pair is a value-change breakpoint — `b ($addr).w ! ($addr).w :trace`, Hatari's own documented idiom —
whose hits are folded into the SAME ordered stream as the I/O writes, under an out-of-band negative
register number. It is an instruction-boundary probe, one instruction coarser than the bus, which is
enough because the two writes are adjacent statements. Two things had to be arranged:

- **The address is not accepted at `--parse` time.** Hatari answers "invalid address" for a RAM
  address at power-on, while `$ffff9202` from its own documentation parses — the machine has not
  sized its memory yet. So the watch is **chained**: a `b VBL > 100` breakpoint that costs nothing
  installs it once the machine is up, and the address itself comes from `STATS.BIN`'s `image_base`,
  which means our side is booted a second time. The two boots are then **required to agree** about
  where GEMDOS put the program — M5's rule, because a different base means the breakpoint watched
  somebody else's memory.
- **The watch has to predate the frames, and each side proves it differently.** On the shipped side
  it goes into the same action file as the debugger's poke, after it, so its baseline is the seed
  and it never sees that write. On ours it is installed on a vblank count, so it MUST see
  `arm_the_flash` write the seed — and the check requires that, because a watch installed after the
  countdown began would be reading an unknown window.

**THE SOUND, at last, and what bounds it.** §10 records that the YM-2149 file cannot be compared as
a snapshot: two boots of the shipped binary itself write different sound registers at the same
anchor, so the register file is captured, printed and compared by nothing. The STREAM can be
compared, and it is: over the window, the shipped binary's **1,155 PSG writes are an exact prefix of
our 6,424**, register and value, in order. A prefix and not an equality, and the asymmetry is
structural rather than a tolerance — the music is driven by `snd_music_tick` from the VBLANK while
the window is bounded by FRAMES, and the two sides spend a different number of vblanks on a frame
(measured: about 2 against 11½). The floor is the shipped side's own count, because a prefix relation
is satisfied by a stream of length one.

**AND IT IS GATED ON A REPRODUCIBILITY MEASUREMENT, for the same reason `m5` is.** `original.py
psgnoise` boots the shipped binary a second time and differences the two streams; `m6` refuses to run
without the reading and **prints what it excludes**. The readings, and they are the interesting part:

| fabrication | pairs taken | writes differing | registers | where |
|---|---|---|---|---|
| **unflashed** | 2 | **0** of 1,155 in both | none | — |
| **flashed** | 2 | **42** of 1,155 in one, 0 in the other | 0 and 1 — channel A's tone period | inside the first eleven frames |

So `m6` compares all eleven registers with nothing excluded, and `m6flash` compares nine. Three
things about that table are the point:

**One reading per fabrication is `flashnoise`'s rule (§10), and it earned its keep here.** The
divergence was first seen as `m6flash` going red, and the tempting response — exclude registers 0
and 1 everywhere on that evidence — would have thrown away the full-strength assertion the unflashed
pairs support. It is also coherent rather than a coincidence: the flashed boot is a different
machine, `../src/behavior.c` gates on the same countdown word, so it drives different actors, and a
sound effect whose pitch sweeps per vblank cannot land on the same value twice when what varies is
which vblank the floppy boot finished on.

**THE PAIRING IS INTERMITTENT — one flashed pair differed and the next did not** — so the reading
accumulates rather than overwrites: a register once seen to move stays excluded, and the stored
`pairs` count says how much looking is behind that.

**And the accumulation is not enough on its own, because `build/` is gitignored.** A fresh clone
starts with an empty reading, and a clone that drew the quiet flashed pair would compare a register
this project has already watched move — going red for something neither binary did.
`PSG_REGISTERS_KNOWN_UNSTABLE` in `original.py` is therefore a **committed floor** under the reading,
carrying `(0, 1)` for the flashed fabrication with these measurements as its citation. The
per-machine pairs union on top of it and never subtract.

The measurement is one-directional, exactly as `vecnoise` is: a register that moves is demonstrably
one boot's accident; one that does not is **not thereby shown to be stable**, and two boots is not a
sample that could bound anything.

**WHAT M6 DOES NOT HAVE is a standing injected control over the SOUND row.** The re-arm control
reddens the palette rows and the mutant reddens the order rows, and both are shown not to move
anything else. Nothing in this directory perturbs the PSG stream on purpose — the writes come from
the cores, which are compiled unchanged. The row is not unexercised, because it has failed for real
(the flashed divergence above is what produced the reproducibility gate), but a demonstrated failure
is not a control. **Registered**, with its trigger and home: the trigger is any change under
`../src/sound.c`, and the home is a `m6silent`-shaped build that perturbs the stream through the
shim's own PSG sink the way `m5fault` perturbs a pen through the shifter sink.

### 12. M3, and what an EXIT is worth

M2, M5 and M6 all watch the reconstruction WHILE IT RUNS. M3 is the only milestone about the two
moments at the ends of it: the frame loop being LEFT, and the machine being given back.

**THE LOOP HAS NO EXIT INSTRUCTION, so leaving it is `game_key_actions`' doing.** `$4a0` is
`do { ... } while (1)` and three of `game_key_actions`' arms end by popping the loop's return address
off the stack and `jmp`ing into the boot chain — a transfer this reconstruction cannot make, because
the chain is unported, so it REPORTS which arm it reached instead (`../include/game.h`'s
`WB_KEY_ACTIONS_*`, and `M2.BIN`'s `loop_ending`). The three:

| arm | condition | reports | the original's `jmp` |
|-----|-----------|---------|----------------------|
| `$54e` | `WB_ROUND_END_RELOAD_REQUEST` ($e1c6) is up — the round bonus at `$e032` raised it — and this CLEARS it | `WB_KEY_ACTIONS_ROUND_END` (1) | `$e5ba`, the sequence |
| `$56c` | `WB_KEY_SEQUENCE_MATCHED` ($604) is up AND `WB_KEY_LAST_SCANCODE` ($879) is `$31`, i.e. N with the cheat on. The request word is left alone, because there was none | `WB_KEY_ACTIONS_LEVEL_SKIP` (2) | `$e5ba`, the same target |
| `$58c` | `WB_KEY_LAST_SCANCODE` is `$01`, i.e. ESC. Starts the music fade at `$594` first | `WB_KEY_ACTIONS_QUIT` (3) | `$e494`, the data-disk prompt |

The two `$e5ba` arms carry **different codes on purpose**: they are reached on different conditions
and clear different state, and one code for the pair would let a port that took the wrong one report
the right answer.

**EVERY CONDITION IS A WORD OR A BYTE IN THE IMAGE, which is the whole mechanism.** No input device
is needed: a debugger poke at the right instant is the drive. The instant is `capture_the_frame`'s
SECOND arrival — the shim calls it once per anchor frame and nowhere else, which is the anchor M5
already photographs on — so the poke lands at the END of a known frame and the ending fires at the
TOP of the next one, where `game_key_actions` reads. Measured, all three: `frames_run` = 2, and
`loop_ending` 1, 2 and 3.

**WHY THE FRAME BUILD AND NOT THE PLAY BUILD,** which is the build a person reaches an ending on. A
poke needs the image's run-time address, and the only honest source of it is the binary's own report
— `M2.BIN`'s `image_base` — which is written when the run ends. The play build writes no record until
an ending fires, so there is nothing to aim the first poke at; the frame build reports `image_base`
AND `capture_pc` about itself on an undriven boot, and the driven boot re-reports both and must
agree. **The exit path is not the play build's difference:** `run_frames`' third exit, `teardown`,
`Pterm` and both records are the same code in both, and `SMOKE_PLAY` changes the frame count and the
watchdog and nothing else. A first attempt to derive `image_base` from the `.PRG` header instead —
basepage + `$100` + text + data, aligned up — was *measured wrong* and abandoned: it gives `0x2b100`
where the binary reported `0x4a600` on the build that measurement was taken on, because
`image_storage` is not the first object the linker puts
in BSS. Layout-dependent until proven otherwise, and it was not.

**THE NEGATIVE CONTROL IS THE FIRST PASS, not a run bolted on.** The undriven boot that measures
those two numbers is required to report `loop_ending` = `WB_KEY_ACTIONS_RETURNED` over all fifty-two
frames, so the poke is shown to be what ends the loop rather than assumed to be. The three pokes then
produce three DIFFERENT codes, which no single accident produces.

**AND ONE ARM NEEDED A SECOND CONTROL, because its poke sets its condition TWICE OVER.** `$556` is
`tst.w $604` and then `cmpi.b #$31,$879`, so the level-skip drive — which sets both — shows the arm
is reachable without showing that the cheat word is what gates it: a port that had dropped the word
test entirely would report `WB_KEY_ACTIONS_LEVEL_SKIP` just the same. A fourth run therefore pokes
**N alone**, with `WB_KEY_SEQUENCE_MATCHED` left clear, and requires the loop NOT to end. Measured:
`loop_ending` = 0 over all fifty-two frames, against 2 with the word set. The two runs are one
differential over one poke — and the control's inputs are DERIVED from the level-skip arm's own poke
set minus the word (`CHEAT_PREMISE_POKES`), because a control whose inputs are a second copy of the
thing it controls is one that stops controlling it the day the copy drifts.

#### The `Pterm` hand-back, asserted from outside the program

This is Joust's M3 discipline: run past the program's own exit and assert the machine's health there,
because an incomplete hand-back is invisible until TOS is running on with whatever the shim left
hooked. That project's measured version was a handler chaining commands out of memory GEMDOS had
taken back — a double bus error a second after the program had gone.

The record already carries the hand-back **from the inside** (`RB_VBL_VECTOR_RESTORED`,
`RB_ACIA_VECTOR_RESTORED` and the rest of the teardown bits, each a read-back of the store it
follows). M3 adds the outside, at two moments **chained off the program's own `Pterm`** — one vblank
after it and twenty after that:

- **Both vectors have stopped being the shim's.** Photographed at the poke, while the reconstruction
  owns the machine, and read again in the tail. Compared ACROSS THE EXIT rather than against a value
  written down here, because what TOS had before the program ran is TOS's business and differs by
  ROM — which the two ROMs show: `$70` goes `0x126b4`→`0xfc06c0` and `$118` `0x126c4`→`0xfc3aec`
  under TOS 1.04, and `0x1b136`→`0xe0086e` / `0x1b146`→`0xe00e64` under EmuTOS. Four different
  numbers, one assertion.
- **TOS's own frame clock is still advancing.** `_frclock` (`$466`) is incremented by TOS's
  vertical-blank handler and by nothing else, so two readings nineteen vblanks apart that differ by
  nineteen say the vector went back to a handler that RUNS. One reading could not: a vector can point
  at ROM and still be reached by nobody. (`Pterm`+1 and `Pterm`+20 — the gap is one less than the
  second reading's offset, and `M3_TAIL_GAP` derives it so the printed label cannot drift from it.)
- **And the ordering is STRUCTURAL, not a margin.** `wonderboy_os.s` exits with `clr.w -(%sp) /
  trap #1`, so a breakpoint on GEMDOS function 0 IS the exit, and the two readings are armed from
  inside its action file. That matters because Hatari's condition parser takes a bare variable or a
  bare number and nothing else — `VBL+300` is rejected at the `+` — so an absolute count was the
  first design, and **the hand-back control killed it**: with the readings at 8000/8500 of 9000,
  `m3fault` failed intermittently on TOS 1.04 with the ending row red, `loop_ending` = 0 over
  fifty-two frames and every hand-back row GREEN. The control's own point, one step further — the
  still-hooked vector took the machine down, **TOS reset**, which restores the vectors and restarts
  the frame clock, and `--auto` re-ran `WB.PRG` with the `:once` poke breakpoint long spent, so the
  undriven second run overwrote the record. Moving the count nearer the exit did not help, because
  the crash and the reset happen within tens of vblanks of `Pterm`. Anchoring on the exit does.
  `--run-vbls` is unchanged either way, so the machine-health scan still covers the long tail; the
  *readings* are what moved. **And the RECORD had to move with them**: the reboot's second run
  overwrites `M2.BIN` and `STATS.BIN` on the drive, so the same `Pterm` action file renames both
  aside before anything can restart. Within `disk/`, because Hatari's `rename` is `rename(2)` and
  refuses a cross-device move — measured, into a scratch directory on another volume.

**AND THE CONTROL SHOWS THE FAILURE IS SILENT.** `build.sh m3fault` suppresses the two vector stores
in `teardown` and nothing else. Measured: all three endings still fire and report their own codes,
the read-backs still RUN, and every hand-back surface reddens — `$70`/`$118` are still `0x126b4`/
`0x126c4` one vblank after `Pterm`, `_frclock` is frozen at `0x717` (+0 over twenty vblanks where a
handed-back machine gives +19), and `readback_failed` names both restore bits. What it also shows is
*how* this fails: **at the moment it matters, Hatari has exited 0 and its log has no fault in it at
all.** A dead TOS looks exactly like a healthy one to an exit status and a crash scan; the only
things that see it are the two vectors and the clock. (What comes *later* in that run is a second
lesson and it is in the ordering bullet above: the unhooked handler eventually runs on memory GEMDOS
has taken back, and on TOS 1.04 that took the machine down and REBOOTED it, which restores the
vectors and restarts the clock. The control's own evidence has a shelf life of a few dozen vblanks.)

#### The one line no headless mode executes

`atari/run.sh`'s `exec` is not covered by anything above: every mode here boots Hatari through
`run_hatari`, and the runner builds a different command — a screen, sound, a joystick, no
fast-forward. **`--sound on` sat in that line through thirteen green modes**, and Hatari rejects it
at parse time (`--sound` takes a FREQUENCY: `off`, or 6000-50066). The runner died at argument
parsing while every check in this file stayed green.

`run.sh parsecheck` builds the argument array ONCE — the same array `exec` takes, because two
spellings is a check that stops covering the line it is named for — prints it, and hands it to Hatari
with `--help` appended. The ordering is measured rather than assumed: Hatari parses left to right and
`--help` prints the usage and stops WHERE IT IS REACHED, so a bad value *before* it reports the error
and a bad value *after* it is never seen. A clean parse is therefore "the usage banner, and no line
beginning `Error`" — the exit status says nothing, because `--help` itself exits 1. `smoke.py runsh`
runs that and then adds the control that makes it a check: the SAME argument list with `--sound on`
put back must be refused, which is the defect that shipped, shown dying.

### 13. The title screen, and what the reconstruction's OWN picture is worth

Every picture before this one in this directory was **inherited**. M2's frame differential is exact
at four anchors, and every byte the frame loop reads was measured off a real machine — §2 is the
honest account of why (`game_main_loop` is `jmp`ed into with a stage already loaded, and the chain
that loads one is unported). A reader is entitled to ask what the reconstruction PRODUCES.

The title screen is the answer, because its whole chain is five calls and all five are reconstructed:

```
  $e4ea  clear_palette()                                                    ../src/stage.c
  $e4ee  clear_both_screens()                                               ../src/boot.c
  $e526  load_resource_by_index(WB_RESOURCE_TITLESCR, WB_RESOURCE_LOAD_BUFFER)   ../src/boot.c
  $e536  rad_depack(WB_RESOURCE_LOAD_BUFFER -> $6ff80)                      ../src/rad.c
  $e540  set_palette($6ff84)                                                ../src/stage.c
```

So `build.sh title` stages **M1's image** — the shipped `SWB.PRG` relocated, plus `gen_image.py`'s
named seeds, and not one byte of measured RAM — asks the machine for `TITLESCR.RAD`, inflates it and
sets the palette. `smoke.py title` compares the 32000 bytes at `WB_SCREEN_LOW` and the sixteen pens
against the SHIPPED binary's own at `$e556` (`original.py title`), which is the instruction the boot
spins on waiting for the stick, i.e. the first instant after `set_palette` has run.

**Measured: 0 of 32000 bytes differ, and all sixteen pens agree** (`000 777 760 640 532 030 040 167
333 666 203 754 643 444 700 500`), on both ROMs. It is the first row here whose picture the
reconstruction drew from the game's own shipped file rather than from a dump of the original.

**THE GEOMETRY IS PINNED, NOT DESCRIBED.** `$6ff80` is the original's own operand (`lea $6ff80.l,a1`
at `$e530`) and is written as that; what makes it work is asserted from the FILE's own header
instead — `TITLESCR.RAD` is 16,620 bytes on disk (16,608 packed under a 12-byte header) and
**32,128 unpacked**, and 32,128 is 128 bytes of header-and-palette prefix plus **exactly one
screen**, so the inflate ends on `WB_SCREEN_LOW`'s last
byte and the picture lands straight in the visible buffer. The record carries both lengths as read
back out of the load buffer, and the row `depack_dest + unpacked == WB_SCREEN_LOW + 32000` is what
holds the arithmetic. The base is published the way `$f906` publishes it — two immediates, i.e.
`WB_SCREEN_LOW` — and **not** from `WB_SCREEN_FRONT`, which is the frame loop's pointer and which the
shipped file carries as `WB_SCREEN_HIGH`: the buffer the picture is *not* in.

**WHERE THE CUT FALLS, because the kit's `include/disk.h` says a project that uses the seam owes its
reader exactly this.** The boot chain is cut at `$e79c` — `jsr disk_load_file.w`, inside
`load_resource_by_index` and the ONE edge into the driver on the boot chain. Everything below it is
excluded: `[$5e3e, $6528)`, `disk_check_signature` through the driver's state block, a WD1772/DMA
state machine and a FAT12 walk whose effects no memory differential can see. A **second** edge into
that band exists and is not on the boot chain at all — the level-4 handler's `jsr $6268.l` when the
idle timer expires (`floppy_deselect_drives`), which this port DOES run and which reaches the YM2149
rather than the controller. Off target the substitution is the kit's staged-file model; here it is
GEMDOS, and the difference is that the ORIGINAL issues one `trap` in its whole life while this build
issues three per load. What is claimed is only that the bytes at `dest` are the file's.

**THE SEAM IS NOT QUITE FREE, AND THE TABLE SAYS SO.** `../src/boot.c` argues that the file-load
substitution costs no name-building, because the row of `WB_RESOURCE_FILE_TABLE` already holds a
NUL-padded `NNNNNNNN.EEE` and "the same pointer goes to `Fopen`". That is true of **thirty-eight of
the forty rows**. It is false of the two whose stem is shorter than eight characters —
`"CREDITS .RAD"` (row `$01`) and `"SPRITES .CRU"` (row `$26`) — and both are files the boot really
loads. The padding is correct where the ORIGINAL reads it: `fat_find_dir_entry` compares those twelve
bytes against a FAT12 directory entry, whose name field the filesystem space-pads. GEMDOS `Fopen`
takes a PATH, in which a space is an ordinary character. So `wonderboy_backend.c` drops every space
and nothing else — a DOS 8.3 name cannot contain one — and `smoke.py` stages the drive under names it
derives from the same table by the same rule, so **the two spellings are pinned to each other by the
run**: if either were wrong the file staged and the file asked for would differ and the load would
return `WB_LOAD_DISK_ERROR`.

**THREE DEVIATIONS FROM THE BOOT, and each is a row rather than a paragraph:**

- **The Copylock is NOT armed.** `$e51e` writes `#$ffff` to `WB_COPYLOCK_ARM_FLAG` immediately before
  this load, and `load_resource_by_index`'s armed arm would report `WB_LOAD_COPYLOCK_RAN` — the
  port's way of saying "the protection would have run here", since the blob cannot be ported and is
  not stubbed. The flag is left at the `$0000` the shipped file carries. **This is asserted, not
  stated**: the record carries the flag as the load found it and the load's own return beside it, and
  the mode reds if either moves. Nothing on the compared surfaces depends on it — the file is on the
  disk in the clear and `rad_depack` is the only thing that touches it.
- **The load runs in USER mode, before the machine is taken**, where the rest of the slice runs in
  supervisor. That is this directory's standing rule for GEMDOS (handle allocation misbehaves when
  entered from supervisor under Hatari's GEMDOS drive — a bug this workspace has shipped once), and
  it costs nothing here because the load touches only image bytes and the two clears the boot
  performs before it touch a disjoint range.
- **The sound request at `$e546` is not made.** `move.w #$8,d0 / lea $17adc.l,a0 / jsr (a0)` starts
  the title music between `set_palette` and the fire wait. It writes no framebuffer byte and no
  colour register; the surface that could see it is M6's ordered PSG stream, and this build carries
  none.

**THE CONTROL IS THE GAME'S OTHER PICTURE.** `build.sh titlecredits` compiles `WB_RESOURCE_CREDITS`
into the same three calls — `CREDITS.RAD` depacks to the same 32,128 bytes into the same buffer, so
nothing about the run's shape moves and every precondition above is asserted NORMALLY (`m2fault`'s
rule: a control whose own run is unsound proves nothing, and "the picture differs" is satisfied by a
run that drew no picture). Only the two picture rows are inverted, and the mode refuses to pass if
the other picture breaks **none** of them. Measured: **both** break — 21,581 of 32,000 bytes over 200
scanlines, and fifteen of the sixteen pens (pen 0 is black in both). The index is REPORTED BY THE
BINARY, for `fault_pen`'s reason: the per-mode `.PRG`s outlive an edit to `build.sh`, so a scrape
could name a resource the running binary never asked for.

**AND TWO NAMED MUTANTS, because the control breaks BOTH picture rows and so says nothing about
either one on its own.** Each was applied, built, run and restored:

| mutant | must redden | measured |
|---|---|---|
| `TITLE_DEPACK_DEST` + 2 — the inflate lands one word below the visible buffer | the geometry row and the bitplanes; NOT the pens (the palette source is `dest + 4` and moves with it) | **CAUGHT**: geometry red, 21,904 of 32,000 bytes differ, pens still `000 777 760 …` |
| `set_palette` deleted — the picture is drawn and the chip is left as `clear_palette` left it | the pens, twice (the plumbing row and the differential); NOT the bitplanes | **CAUGHT**: `pens_readback_failed = 0xfffe`, pens 1-15 differ, **0 of 32000 framebuffer bytes** |

The second is the fail/pass partition the control cannot supply: it shows the pens row failing while
the framebuffer row stays green, so the two surfaces are separately breakable and neither is passing
because the other is. (Pen 0 survives it because `clear_palette` leaves `$000` and the title's own
pen 0 is `$000` — the same reason M5 chose pen 3.)

**WHAT THIS IS NOT.** It is not the boot. `$e4e6`'s `video_set_lowres_50hz`, the MFP mask, the vector
install and everything after the fire wait — the credits screen, the data-disk prompt, the stage
load, the tile installer, `sprites_cru_install` — are still the shim's or still unported. What it is:
the first proof on a 68000 that this reconstruction can turn a file on the game's own disk into the
game's own picture.

**THE NEXT RUNG IS SCOPED AND NOT TAKEN.** The CREDITS screen (`$e562`..`$e5a2`) needs no new port:
it is this slice again at a different destination — `load_resource_by_index(WB_RESOURCE_CREDITS)`,
`rad_depack` to `$77f80`, `set_palette($77f84)` — plus `copy_screen($78000 -> $70000)` (`$f938`,
`../include/boot.h`), `game_restart_reset` (`$fe4a`, `../src/stage.c`, which falls through into the
life reset and so DRAWS `hud_draw_lives`' three cells over the picture), and one colour write
(`move.w #$77,$ff8254`, pen 10). Its shipped-side anchor is `$e5aa` — the `clr.b $877.w` immediately
before the credits fire wait — which is chosen because it collides with none of `boot_script`'s own
four `:once` breakpoints, and so needs neither `fires=False` nor a hook into their action files. It
is not built here: a rung is a build, a control, a shipped-side anchor and two ROMs, and half of one
is worse than none.

## The bugs found on target

Seven, and every one of them is the shape `docs/on-target-execution.md` warns about: real behaviour
in code the differential harness cannot execute at all. The first four came off the first three runs;
the next two came off M3, from the two pieces nothing had ever executed — the exit path and the
runner's own command line; the seventh came off the title build, and it had been latent under every
green mode before it.

**1. A non-volatile image read in a busy-wait — in the SHIM, one file over from the comment about
it.** `await_ikbd_reply` spun on `game_image[WB_KEY_LAST_SCANCODE]`. `game_image` is a plain array to
the compiler and nothing in the loop body can change the byte, so GCC hoisted the load; the reply
landed and was never seen. `wonderboy_backend.c`'s `sched_wait8` reads through a `volatile` pointer
for exactly this reason and its comment says so — and the bug was written in the file next to it.
*Lesson: the hazard you have documented is the one you stop looking for.*

**2. A hardware register that does not read back what you wrote.** The shifter's resolution register
is two bits wide; the other six return whatever was last on the bus. The unmasked read-back failed
against a machine that had done exactly what it was told. *Lesson: a read-back is only a check if it
reads back the bits that exist.*

**3. A bound that outran the run — twice, and the second time it cost the CONTROL its evidence.**
The IKBD reply wait and the vblank watchdog were both given spin counts five to twenty times longer
than `--run-vbls`, so the program never reached its own dump and the mode reported "no `STATS.BIN`"
for builds that were working. The second occurrence was the `novbl` control, where "no record" says
nothing about *which* checks the control broke — and a control that cannot say that is not a control.
Both bounds are now calibrated from the measured ~24 cycles an iteration. *Lesson: a watchdog longer
than the harness's own limit is not a watchdog.*

**4. `--run-vbls` short enough to precede the desktop.** At 900 the program was never `Pexec`'d at
all — TOS 1.04 had not finished booting — and the failure looked identical to a crash. *Lesson: the
first thing to check when nothing ran is whether anything could have.*

**5. THE EXIT HUNG FOR EVER ON EVERY KEY-DRIVEN ENDING** — i.e. on precisely the two ways a person
leaves the play build. `pin_sched_wait8` did not clear `WB_KEY_LAST_SCANCODE` before sending its
first reset, and `await_ikbd_reply` returns on any non-zero byte, so the scancode the frame loop had
just exited on was taken for the controller's acknowledge. The uncapped `sched_wait8` under it was
then aimed at a byte the IKBD will never send: no hand-back, no `Pterm`, no record, nothing to read.
It was found by M3's first key-driven ending and **isolated rather than inferred** — poking the
scancode alone, with no ending driven and the loop running all fifty-two frames, kills the run
identically. §8 has the fix, which also closes the sibling case (a key arriving *inside* the reply
window, which is the normal interactive path) by requiring two resets to answer the same byte.
*Lesson: a milestone that only reports its surfaces is not driving them. The exit path had been
compiled into thirteen green modes and executed by exactly none of them.*

**6. The runner's `exec` line did not parse.** `--sound on`; Hatari's `--sound` takes a frequency.
Thirteen green headless modes and a launcher that died at argument parsing, because no check ran the
one command that is not `run_hatari`'s. §12 has the probe and its control. *Lesson: a command with no
check is not covered by the checks next to it, however many of those are green.*

**7. THE RETURN FROM SUPERVISOR MODE WAS WORKING BY COINCIDENCE**, and the coincidence was the
compiler's stack scheduling. `Super(0)` / `Super(ssp)` is the standard TOS round trip and this shim
had used it since M1. TOS goes back to user mode by loading `%a7` from the USER stack pointer — and
the USP it uses is the one FROZEN when `Super(0)` was called; **measured on TOS 1.04, it does not
set the USP from the supervisor stack on the way out**. So `Super(ssp)` returns onto the stack
position the FIRST call stood at, and the wrapper's own unwind (`addq #6` / `movem` / `rts`) reads
from there. That is right only while the compiler leaves `%sp` at the same depth at both call sites,
and m68k GCC does not promise it: it DEFERS argument pops and combines them, so an edit anywhere
between the two calls can move one of them.

The title slice is such an edit. With its load ahead of `Super(0)`, `%sp` at the second call sat 12
bytes above the first — `USP 003f7f52` against `ISP 003f7f5e`, read out of the debugger at the trap —
the `rts` popped stale stack and the program died reading `$26520020`. The M1 build's two calls are
at the same depth (`USP 003f7fa2` == `ISP 003f7fa2`) and had been surviving on that.

The fix is `wonderboy_os.s`'s `wb_leave_supervisor`, which sets the USER stack pointer to the
supervisor stack it is standing on **one instruction before the trap**, so the return no longer
depends on where either call was made. *Lesson: the failure looked like a defect in the new code and
was a defect in the oldest code in the file — and its symptom was a machine that had already passed
every read-back, torn the machine down cleanly, and then died on the way out with no record. Sixteen
green modes had been one compiler decision away from it.*

## Known gaps

- **The file load is a DECLARED SUBSTITUTION and on target it is the OPERATING SYSTEM.** §13 has the
  cut and its two edges. What no check here can see: the original reads its resources by driving the
  WD1772 and walking FAT12 itself, and this build asks GEMDOS. Sector order, retries, the disk's own
  protection outside the Copylock, and the interactive retry on a read error (`WB_LOAD_ERROR_WAIT` —
  `../src/boot.c` declines to model the spin) are all outside every surface this directory has. The
  framebuffer compare says the BYTES arrived; it says nothing about how.
- **`bus.h`'s out-of-image answer is an ORACLE'S answer FOR MOST ADDRESSES, compiled into the `.PRG`
  and UNPINNED here.** A read outside the game's 1 MB returns zero and a write there is dropped.
  Off-image that matches the shim on everything **except the seven hardware addresses `../include/
  bus.h` enumerates** — `$fffc00`, `$ff8800`, `$ff8802`, `$fffa01`, `$ff820a`, `$ff8207`, `$ff8209`
  — where the shim serves TDRE, the PSG read-back or the case's declared seed, and latches a PSG
  write. So the claim is narrower than a blanket equivalence, and in *two* directions at once: on the
  host it is exact off the modeled set and a stated hole on it (six of the seven are caught by the
  harness's own ledger comparisons; `$fffc00` is not), and on target it is a model of neither. A real
  ST has real RAM (a 4 MB machine) or a live `$ff8000` I/O page at those addresses. Nothing this
  directory measures would show the difference: the framebuffer, the sixteen pens, the M-records and
  `build.sh`'s seam tripwire are all blind to a store that lands outside the array. Not new —
  `../src/blit.c` and `scene_clear_marker_pair` have done it since batch 15 and batch 40 — but batch
  43 phase C widened it to the whole of `../src/map.c` and `../src/scene.c`, so it is stated here
  rather than inherited quietly. Pinning it needs an on-target case that computes such an address on
  purpose and watches a surface that can see the answer; there is none today.
- ~~**Of the four shifter-sink mutants `../STATUS.md` measures as surviving the whole differential
  suite, ONE IS LEFT.**~~ **NONE IS LEFT.** M1 killed the base-byte swap where it lives in the shared
  translation; M2 killed the same swap at `flip_screen`'s own two call sites and the wrong buffer
  published (§9); M5 killed the flash's two arms swapped, by arming the countdown on both sides
  (§10); **M6 killed the sink write moved above the timer store** (§11), which was the one no
  snapshot could ever see because it changes no value, only an order. Measured both ways: with the
  mutant applied `m5flash` is entirely green and `m6flash`'s order row is red.
- **The whole YM-2149 register FILE is still captured on target and compared by nothing** — §10 has
  the two reasons and the measurement behind the first, and neither has moved. What HAS changed is
  that this is no longer the same thing as the sound being unasserted: §11 compares the ordered PSG
  write STREAM, gated on its own reproducibility measurement, and over the fifty-two-frame window
  the shipped binary's 1,155 writes are an exact prefix of ours. The register file remains a printed
  witness because it is a snapshot of where the song had got to; the stream is the assertion.
- **M6's sound row has no standing injected control.** It has failed for real — the flashed
  divergence that produced the reproducibility gate — but a demonstrated failure is not a control,
  and nothing here perturbs the PSG on purpose because the writes come from cores compiled
  unchanged. Registered in §11 with its trigger (any change under `../src/sound.c`) and its home (a
  `m6silent`-shaped build perturbing the shim's PSG sink the way `m5fault` perturbs a pen).
- **M6 reads five registers and the machine has more.** The timeline covers the screen base, the
  sixteen pens and the two YM ports — the surface this port actually drives. The MFP, the FDC and
  the RS-232 writes in the same trace are dropped, because they belong to TOS and to the floppy and
  differ between a GEMDOS drive and a real one by construction. A reconstruction bug that reached
  one of those would not be seen.
- **Only one frame's worth of the game is reached.** Fifty-two frames of a motionless stage 1 with
  no stick pushed. Nothing that needs input, nothing that scrolls, no monster that has spawned, no
  stage but the first. What M2 shows is that the frame loop and everything under it agree with the
  original on the picture they draw *for this stage's opening second* — which is a much narrower
  claim than "the game renders correctly" and is exactly as much as fifty-two static frames support.
- **The staged image is one boot's, and the shipped side is another's.** ~500-650 of its 523,272
  bytes differ between boots (§2). They are argued and measured not to reach a framebuffer or a pen, which
  is what makes the comparison exact; a *whole-memory* differential against a fresh boot is not
  available on those terms and is not attempted.
- **The scancode path is pinned by a status byte, not by a key.** `sched_wait8` really spins and a
  real interrupt really ends it, but the byte is the IKBD's reset acknowledge, so the *game's* two
  waits (`$60e`, `$64e`, on scancode `$19`) have not been driven. **The reason for that is no longer
  "a headless Hatari has no keyboard" — that is measured false.** Hatari 2.6.1's `--control-socket`
  takes `hatari-event keydown/keyup <ST scancode>`, and the injected code really does arrive in
  `WB_KEY_LAST_SCANCODE` through the real ACIA interrupt: scancodes `$50`, `$29` and `$4b` were read
  back out of the running image, with the shim's `ikbd_bytes` rising from 3 to 10. What is missing is
  the SYNCHRONISATION — the socket is driven on wall-clock time while every anchor in this directory
  is a program instant — and one unexplained detail: `keydown 1` (ESC) delivered `$02` where the
  other three delivered their argument exactly, so the one scancode an ending needs is the one that
  did not arrive. **Registered.** Trigger: any attempt to drive an ending or a key wait through a
  real interrupt rather than a poke. Home: §12, and a handshake that arms the injection from the
  poke breakpoint instead of from a `sleep`.
- **The joystick path is installed and unexercised, and now that is a MEASUREMENT.** The handler's
  `$fe`/`$ff` arms have never run. The injection above presses a KEY at the emulated IKBD, while
  `--joy1 keys` maps HOST SDL key events onto the emulated stick, so the two never meet:
  `WB_JOY0_STATE` and `WB_JOY1_STATE` were read out of the running image as `$00` under all four
  injected scancodes, including both arrow keys (`$4b` left, `$50` down). So the arms stay **partial
  by construction** with `bash atari/run.sh` as the discharging mechanism and a person at the cursor
  keys as the only thing that runs them — but the boundary is where a measurement puts it rather than
  where an assumption did.
- **`../src/sound.c:786`'s refusal has no on-target story.** The original reads a word of the sound
  handlers' own instruction stream and `jmp`s through it — inexpressible in C. Off target it is a
  refusal; on target `-DOS_NO_REFUSAL_TALLY` turns it into "return the sentinel", which is the
  routine bailing out of a malformed pattern rather than doing what the original does.
- **The YM2149 assertion is vacuous on EmuTOS** (above): that ROM leaves port A already deselected,
  so only the TOS 1.04 run measures the write. Two machines, one of which can see the check.
- **The build emits four `-Wimplicit-fallthrough` notes** from `../src/behavior.c`. They are the
  cores' own deliberate reproductions of the original's fallthroughs, they predate this directory,
  and annotating them is a change to verified code that belongs to whoever owns that tier.
