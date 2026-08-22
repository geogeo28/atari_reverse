# atari/ — run the reconstructed Wonder Boy on a real 68000

This takes the reconstruction past the differential harness: it **cross-compiles the very same
verified C cores to 68000** (`m68k-elf-gcc`) and runs them as a GEMDOS `.PRG` under Hatari with a
real TOS ROM. The sixteen translation units under `../src/` are compiled **unchanged** except for one
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
| **M3** the exits | `game_key_actions`' three endings `jmp` into the boot chain and `game_main_loop` reports them instead — the same "exits the reconstruction reports and its caller drops" that Joust's M3 completes in its shim. Nothing here completes them yet | ⛔ owed |
| **M3** the joystick arms | the shim's ACIA handler files a report on `$fe`/`$ff` and **those arms have never executed**. Discharged by an interactive Hatari run with `--joy1 keys` and a human at the cursor keys, which is where Joust's M3 leaves steering too; a headless run cannot press a stick. **This row exists because a registered boundary with no discharging milestone is how an unpinned arm ships forever** | ⛔ owed, mechanism named |
| **M3** a saved-state round trip | Joust's `HIGH.SCO` equivalent. **ABSENT BY CONSTRUCTION, not deferred**: `../project.toml`'s byte scan establishes that Wonder Boy performs no file I/O at all — one GEMDOS trap in the whole image, a `Super` — so there is no file for a round trip to exist over | n/a |
| **M4** frame differential vs the original | ~~blocked on M2~~ — **DELIVERED AS PART OF M2**, above: the two rows are the same comparison, and separating them was an artefact of expecting the dump to be a later milestone than the frame. The row is kept so the renumbering is visible rather than silent | ✅ folded into `smoke.py m2` |
| **M5** hardware-state vector + rendered picture | M2 reads back ONE register (`$ffff8201/8203`, the row that kills the two flip-site mutants). The rest of Joust's vector — the YM-2149 file, resolution, refresh rate — and Hatari's own `screenshot` are not taken. Catches when it lands: **the flash's two arms swapped**, which M2 cannot see because its anchors are frames on which `WB_FLASH_TIMER` is zero | ⛔ owed, partly delivered |
| **M6** timelines | the ordered stream of shifter and PSG writes, reduced to a per-phase shape. Catches: the sink write moved above the timer store; and the PSG select/data race in §5 | ⛔ owed |

Verified on **TOS 1.04 and EmuTOS** (Hatari's bundled `tos.img`). **NOT "identical results on both
ROMs"** — the honest split is that M1 is green on both, and two of its pieces behave differently:

- **The image lands somewhere else, and M1 notices.** `image_base` is `0x2a600` under TOS 1.04 and
  `0x33100` under EmuTOS, and the published screen base follows it (`0xa2600` / `0xab100`). The
  translation in §3 is therefore demonstrably not a constant that happens to be right.
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

python3 atari/original.py variance                          # what in the dump is one boot's luck
python3 atari/original.py neighbour                         #   ...and the anchor's own evidence (§9)
python3 atari/original.py nofire                            #   ...and the two boot controls
python3 atari/original.py nodisk2
```

**M2 is `original.py` first, always.** The image it needs cannot be computed — see §2 — and
`build.sh m2` refuses rather than building against a missing dump, or against one whose three
artefacts are not all from the same boot (they carry a manifest; the build verifies it). The dump
needs **both shipped `.stx` disks** in `../bin/`. `neighbour` runs after `variance`, because the
floor it has to clear is derived from the noise `variance` measures rather than written down.

`smoke.py` finds a TOS ROM in `$WB_TOS_ROM`, then `tools/hatari/TOS*.img` newest first, then
Hatari's bundled EmuTOS. Hatari needs `--memsize 4`: the 1 MiB image is the program's BSS. `build/`
and `disk/` are gitignored build artifacts; the full Hatari log of the last run is kept in
`out/hatari.log`, always, whether the mode passed or not.

## Pieces

| file | role |
|------|------|
| `wonderboy_backend.c` | **the six kit symbols, made hardware** — plus the three shifter sinks and the freestanding `memset`/`memcpy`/`bzero` this `-nostdlib` link has no libc for (`bzero` is the compiler's own rewrite of `clear_message_buffer`'s 6400-byte clear in `../src/text.c`, and the only libc symbol the cores reach) |
| `wonderboy_main.c` | the shim: stage the image, take the machine, run, hand it back, write `STATS.BIN` |
| `wonderboy_os.s` | `_start`, the TOS trap wrappers, and the two interrupt entries (`movem` pair + `rte`, and the MFP end-of-interrupt) |
| `shim_include/tos.h` | the trap wrappers' prototypes — a short list, because the game issues one trap in its life |
| `shim_include/wonderboy_target.h` | the two seams the cores name (`../src/game.c`, `../src/stage.c`) |
| `shim_include/string.h` | a freestanding `<string.h>` — needed by the **kit's** `os.h`, not by the cores; deleting it on the grounds that nothing under `../src/` calls a string function fails the build in fifteen translation units |
| `original.py` | **the shipped 1989 disks, driven under Hatari to a named anchor** — the post-boot RAM dump M2's image is, the register file and palette that go with it, the mis-anchor and reproducibility measurements, the two boot controls, and the shipped side of the frame differential |
| `gen_image.py` | the staged image — and **the honesty line** about what a staged image is not |
| `tos.ld` / `mkprg.py` | link at base 0, then wrap the ELF into a GEMDOS `.PRG` with a relocation table |
| `build.sh` | compile + link + wrap + stage `disk/`, and assert the seam actually held |
| `smoke.py` | headless Hatari: boot, run to completion, read `STATS.BIN` back, check it |

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

**THE SURFACE IS A SET, AND IT IS SIX SYMBOLS.** Taken from the union of the sixteen translation
units' undefined symbols minus the game's own; `nm` on the differential `.so` agrees.

| symbol | call sites | on target |
|---|---|---|
| `hw_read8` | 5 — `../src/rng.c`, `../src/behavior.c` ×2, `../src/sound.c` ×2 | the read itself |
| `psg_port_write` | 10 — `../src/game.c`, `../src/sound.c` ×9 | `$ff8800` select, `$ff8802` data |
| `psg_port_read` | 3 — `../src/game.c`, `../src/sound.c` ×2 | select, then read back through `$ff8800` |
| `sched_wait8` | 1 (two wait SITES reach it: `$60e`, `$64e`) | an uncapped spin; the ACIA interrupt ends it |
| `sched_poll16` | 2 — `flip_screen`'s two waits, `$6aa` and `$6d0` | one uncapped iteration; the caller owns the predicate |
| `os_refused` | 1 — `../src/sound.c:786` | **not defined**: `-DOS_NO_REFUSAL_TALLY` makes the kit's `os.h` serve an inline identity |

And the complement, because a set is only a claim if its complement is one: `sched_poll8` has **0**
direct call sites and is deliberately *not* defined, so a future core that calls it gets a link
error; `g_dosound` has **0** — this game never issues XBIOS `Dosound`; the whole staged-file model
and the whole TOS trap model have **0** each.

**`build.sh` asserts the seam rather than describing it**, in both directions: no `g_hw_reset`,
`g_psg_reset`, `g_sched_reset`, `g_dosound`, `g_os_refusal_reset` or `sched_poll8` may appear in the
`.PRG` (a kit source leaking into the link would reintroduce the model silently, and the build would
"verify" against it), and all five of the symbols the backend owes **must**.

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
**reads the result back**; measured on the M1 run, `image_base = 0x2a600` and the published base is
`0xa2600` = image + `$78000`.

**One transient is inherited rather than added:** between the game's first byte and its second the
shifter is pointed at a mixed address, exactly as it is in the original, which also writes two bytes
in two instructions. `flip_screen` issues both between its two waits, i.e. just after a vblank,
which is why the original gets away with it and so does this.

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

Three, each stated because a silent deviation is the same shape as a bug:

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
  (`--trace psg_write`) compared against the shipped binary's, which is M6.

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

### 8. The IKBD acknowledge byte is DISCOVERED, not assumed

`sched_wait8`'s pin is a genuine spin rather than a byte already in place, and it is arranged in two
phases so that it cannot hang: the first reset's reply is waited for on a bounded loop — which is
what establishes that this machine's IKBD answers at all — and only then is the byte cleared, a
second reset sent, and `sched_wait8` called on the same reply.

The byte itself is **learned**. The IKBD's documented self-test-passed answer to `$80 $01` is `$f0`;
the machine this ran on answered **`$f1`**, and the first draft — which had the constant written down
— failed on a path that was working perfectly. Which byte a controller sends is a property of that
controller's firmware, not of this port. What phase two then pins is that the answer **repeats**,
which is a stronger claim than the constant was.

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
| the flash's two arms swapped | **SURVIVES, and the reason is measured** — `WB_FLASH_TIMER` is `$0000` in the staged image, so `flash_step` returns before the write on all fifty-two frames and the arm never executes. Not an M2 weakness to fix but a branch the *anchor's own data* cannot reach; it is M5's, and staging a frame with the flash armed is what would reach it |

**`sched_poll16` is discharged, and by the iteration count rather than by the frames.**
`flip_screen`'s two waits are its only callers and they are uncapped spins on `WB_VBL_COUNTER`. A
frame count says they returned; only the count of iterations says they SPUN — i.e. that what ended
them was a level-4 interrupt raising the counter and not a predicate already true. Measured: **~17,100
iterations over 52 frames**, ~330 per frame, against the 2 a wait that never spun would give.

**Both ROMs, and the image lands somewhere else on each.** M2 is green on TOS 1.04 (image at
`0x49d00`) and on EmuTOS, which lands it ~36 KB higher, with the published base following it both
times — so the
translation in §3 is demonstrably not a constant that happens to be right, on the frame path too.

## The bugs found on target

Four, on the first three runs, and every one of them is the shape `docs/on-target-execution.md`
warns about: real behaviour in code the differential harness cannot execute at all.

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

## Known gaps

- **Of the four shifter-sink mutants `../STATUS.md` measures as surviving the whole differential
  suite, THREE AND A HALF ARE NOW DEAD.** M1 killed the base-byte swap where it lives in the shared
  translation; M2 kills the same swap at `flip_screen`'s own two call sites and the wrong buffer
  published (§9). **Two are left**, and they are different kinds of left: the flash's two arms
  swapped is *measured surviving* because the anchored window's own data never arms the flash (§9) —
  M5's, and reachable only by staging a frame with `WB_FLASH_TIMER` non-zero; the sink write moved
  above the timer store is untried, and is M6's.
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
  real interrupt really ends it, but the byte is the IKBD's reset acknowledge; a headless Hatari has
  no keyboard, so the *game's* two waits (`$60e`, `$64e`, on scancode `$19`) have not been driven.
- **The joystick path is installed and unexercised.** The handler's `$fe`/`$ff` arms have never run:
  the IKBD sends joystick reports only in event-reporting mode with a stick that moves, and there is
  no stick here. The scancode arm is the one M1 drives.
- **`../src/sound.c:786`'s refusal has no on-target story.** The original reads a word of the sound
  handlers' own instruction stream and `jmp`s through it — inexpressible in C. Off target it is a
  refusal; on target `-DOS_NO_REFUSAL_TALLY` turns it into "return the sentinel", which is the
  routine bailing out of a malformed pattern rather than doing what the original does.
- **The YM2149 assertion is vacuous on EmuTOS** (above): that ROM leaves port A already deselected,
  so only the TOS 1.04 run measures the write. Two machines, one of which can see the check.
- **The build emits four `-Wimplicit-fallthrough` notes** from `../src/behavior.c`. They are the
  cores' own deliberate reproductions of the original's fallthroughs, they predate this directory,
  and annotating them is a change to verified code that belongs to whoever owns that tier.
