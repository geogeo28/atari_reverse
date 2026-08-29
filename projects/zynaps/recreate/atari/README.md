# ZYNAPS.PRG — the reconstruction on a 68000

**M1: the title picture and its music, produced by the verified cores, on an emulated Atari ST.**

`projects/zynaps/recreate/` holds 166 functions verified byte-for-byte against the original 68000
code by the differential harness. Until this directory existed, none of them had ever executed on a
68000. This is the cross-compile: the same C, unmodified, plus a hardware shim, wrapped into a
GEMDOS `.PRG` that boots under Hatari to the title screen with the title tune playing — and a
`smoke.py` that judges it against the shipped binary on six named surfaces.

```bash
bash atari/build.sh title            # -> build/ZYNAPS-title.PRG, disk/ staged for Hatari
python3 atari/smoke.py title         # twelve checks, all green
bash atari/build.sh titlefault       # the negative control
python3 atari/smoke.py titlefault    # the same twelve plus two, the colour pair INVERTED
bash atari/build.sh play && bash atari/run.sh    # ...and the one a person watches
```

Read [`docs/on-target-execution.md`](../../../../docs/on-target-execution.md) first: the seam
pattern, the twelve-entry bug taxonomy, and the six observable surfaces are that file's, and every
design decision here is an application of one of them.

---

## What M1 runs, and where it stops

`zynaps_main.c` composes the boot's **verified slices only**, in the original's own order, and stops
where the reconstruction stops:

| the original | what runs here | from |
|---|---|---|
| `0x10000` `Super(0)`, `movea.l d0,a7` | `boot_enter_supervisor()` | `../src/init.c` ✅ verified |
| `0x10010` `dc.w $a00a` (hide mouse) | `zy_line_a_hide_mouse()` | `zynaps_os.s` — the real opcode |
| `0x10012` `move.l $70.l,$195d0.l` | `boot_save_vbl_vector(image)` | `../src/init.c` ✅ verified |
| `0x1001c` `ikbd_send_cmd($12)` | `zy_ikbd_send_cmd(0x12)` | `zynaps_os.s` — unported, see below |
| `0x10024` `ikbd_send_cmd($15)` | `zy_ikbd_send_cmd(0x15)` | `zynaps_os.s` |
| `0x1002c`–`0x101b9` | `boot_load_title_assets(image)` | `../src/init.c` ✅ verified |

`0x101ba` is where `../STATUS.md`'s "Not reconstructed" table stops the boot — the harness's
staged-file table holds eight files and the ninth would be opened there — so it is where this stops
too. **Nothing in this directory composes an unverified slice.** The frame loop, the front end and
the remaining ~54 file loads are M2's, after the next port wave.

That slice does the whole title screen: the two framebuffers fixed at `0x70300`/`0x78000`, the title
picture read into the back buffer, low resolution selected, the game's own VBL and Timer B vectors
installed, tune `0x0b` started, the picture published, its palette uploaded, and seven more graphics
loaded and reshaped.

## The machine, and one number that is not the original's

`--machine st --memsize 4`, TOS 1.04. **The 4 MB is this build's, not the game's.** The cores index
a flat 1 MiB image (`OS_IMAGE_SIZE`, and `../project.toml`'s `image_size` must equal it), which on
target is a 1 MiB `.bss` array; TOS 1.04's TPA on a 1 MB machine has no room for that plus a stack.
The original ships for a 512 KB machine.

`smoke.py` runs **both sides at 4 MB**, so every comparison it makes is about the two programs
rather than about two different machines. That is sound because the game hard-codes its framebuffers
at absolute RAM and TOS's TPA base does not move with the memory size — and it is *checked* rather
than argued: the original's own capture must hold more than one colour and its sixteen pens must be
the shipped boot palette, or the run says so and stops.

## The seam inventory

Every symbol the differential harness models, and what it becomes here. **The seam is the include
path plus two omitted sets of translation units** — no core is edited, and `build.sh` measures that
(no core includes a shim header; no core reads a target-only `-D`).

| symbol | what the HARNESS modelled | what the TARGET does | how |
|---|---|---|---|
| `os_fopen` / `os_fread` / `os_fclose` | a staged-file table in the image (8 slots at `0xbf000`), pure image copies — **bounds-checked** against the image, and a bad name **refused** | real GEMDOS `trap #1` `$3d`/`$3f`/`$3e` against Hatari's GEMDOS drive, with the model's **image bound and its refusal tally restored** — see below | `shim_include/os.h` shadow → `zynaps_os.s` |
| `os_super` | returns the cookie `$00535550`, no privilege change | **a no-op returning the same cookie.** `_start` takes supervisor once, before any C, and hands it back once through `zy_leave_supervisor` | `shim_include/os.h` shadow |
| `os_refused` | a refusal tally the harness reads back | an inline identity — the kit's own `os.h` anticipates this build | `-DOS_NO_REFUSAL_TALLY` |
| `psg_port_write` | an ordered write ledger + a register file (`kit/src/psg.c`) | `move.b reg,$ffff8800` then `move.b val,$ffff8802`, from inside the vertical-blank interrupt | kit `src/` excluded → `zynaps_backend.c` |
| `hw_read8` | seeded reads of four declared addresses (`kit/src/hw.c`) | **not defined.** No Zynaps core calls it (measured), and a stub would be a fabricated machine byte | kit `src/` excluded |
| `hw_write8/16/32` | **does not exist** — `hw.h` deliberately exports no write | a real `volatile` store, counted | `shim_include/hw.h` → `zynaps_backend.c` |
| `sched_poll8` / `sched_wait8` / `sched_poll16` | polls counted per wait site, with declared stores (`kit/src/sched.c`) | **not defined.** No Zynaps core calls one (measured) | kit `src/` excluded |
| `g_dosound`, `disk_*` | the Dosound ledger, the staged disk | **not defined.** No Zynaps core calls one | kit `src/` excluded |
| `shifter_write_palette` | an empty body (`../src/irq_hw_offtarget.c`) | sixteen (or one) real `move.w` to `$ffff8240`, one store per pen through `hw_write16` | that file excluded → `zynaps_backend.c` |
| `shifter_clear_pen0` | an empty body | `clr.w $ffff8240` | the same |
| `mfp_ack_timer_b` | an empty body | `bclr #0,$fffffa0f` — a read-modify-write, not a store | the same |
| `shifter_palette_write` / `shifter_screen_base_write` | a static record inside `../src/video.c` | **still a static record** — `video.c` is a core and has no target seam. The shim makes the two writes itself; see the caveat below | `zynaps_main.c` |
| `init_shifter_mode_*`, `init_palette_uploads` | counters inside `../src/init.c` | **still counters** — the shim reads them and makes the real `andi.b #$fc,$ff8260` only if the slice asked for it | `zynaps_main.c` |
| `ikbd_send_cmd` @ `0x14444` | **not reconstructed** — the kit models no read for the ACIA status at `$fffc00`, so the oracle spins for ever | a bounded spin on bit 1 of `$fffffc00` then a store to `$fffffc02`, with the bound's verdict as the return value | `zynaps_os.s` |
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
* **The refusal tally.** `-DOS_NO_REFUSAL_TALLY` is right for the cores' own sentinel path but
  leaves nothing counting a FAILED OPEN — and `load_file` (`../src/fileio.c`) has no error handling
  at all, faithfully: it hands Fopen's `-33` straight to Fread as a handle. Under the harness an
  unstaged name was a refusal the harness could not ignore; on target a data file missing from
  `../../bin/disk` would simply leave the buffer zeroed, and **M1 draws none of the four files whose
  absence would show**. So the opens are counted at the seam and the count is asserted.

### The one seam that is not a seam, and what it costs

`../src/video.c`'s `shifter_palette_write` and `shifter_screen_base_write` are defined **inside a
core**, unlike `../src/irq_hw_offtarget.c`'s three, which live in a file a target build simply does
not compile. So there is nothing to override: on target they go on filling a static array, and the
shim performs the two writes. Two different arrangements follow, and the asymmetry is deliberate:

* **The palette IS the core's own output.** The shim calls `g_set_palette_title(image, scratch)` —
  `video.c`'s glue, which clears the sink, runs the verified `set_palette_title`, and writes the
  eight longwords **the core's loop produced** to the image — then pushes those to `$ff8240`. A
  mutation inside the core reaches the screen. The scratch address is `0x80000`, above the program
  (`0x6e96e`) and above the framebuffers (`0x7fd00`), so no surface this smoke compares can see it.
* **The screen base cannot be**, because the core's record is only reachable through
  `g_screen_flip_buffers`, which would flip the buffers a second time to hand it over. So the shim
  reads the swapped pointer out of the image and adds the image base. That pointer is still the
  core's output — the swap is ordinary diffable memory the differential holds, and `smoke.py`
  compares both framebuffer words against the original's — but the two published BYTES are the
  shim's arithmetic, and `Physbase` is what reads them back.

The residual: a change to `screen_flip_buffers`' publish half would not reach the machine. Recorded
under **Unpinned**, below.

## The six surfaces, and what each one measured

`python3 atari/smoke.py title`, TOS 1.04, both sides at 4 MB. Measured 2026-08-29:

```
-- title: image base 0x1a600, the original at 0xaa56, 266 vblanks and 2926 PSG writes at the anchor
   [green] exit status + log (ours)
   [green] exit status + log (the original)
   [green] exit status + log (the program's own record)
   [green] exit status + log (the machine was handed back)
   [green] exit status + log (the fault scan can fail)
   [green] the original was anchored on its own boot
   [green] trap ledger
   [green] memory (the framebuffer)
   [green] memory (the boot slice's own output and ledgers)
   [green] timelines (the PSG tick frames)
   [green] hardware-state vector (the pens, $ff8260, the video base)
   [green] rendered pixels
-- OK
```

| surface | what it compared | result |
|---|---|---|
| **exit status + log** | Hatari's return code and its own `Bus Error`/`Address Error`/`CPU halted` lines, on both sides, read from **stderr**; the emulator kept running three seconds past `Pterm`; and the program's own `STATE.BIN` complete to its `'DONE'` tail | clean. The only fault line either side logs is TOS's own `Bus Error writing at $41fffe, PC=$fc0174` — the ROM sizing memory at the 4 MB boundary — which the scan drops **by its ROM PC**, not by failing to see it. The scan's own control proves that distinction on every run |
| **trap ledger** | `--trace gemdos`: our `Fopen`/`Fread`/`Fclose` sequence, minus the shim's four files and TOS's own `DESKTOP.INF`, against the original's first slice | **24 calls parsed on our side, identical to the original's first 24** — the same eight lowercase names in the same order, on the same handle, with the same byte counts. The buffer address is deliberately not compared: ours is inside a 1 MiB array and the original's is absolute RAM |
| **memory** | the 32000-byte displayed framebuffer, written by the program from `image + screen_front`, against a `savebin` of the original's `0x70300` | **byte-identical** |
| **hardware-state vector** | the sixteen colour registers, `$ff8260` and the two video-base bytes, read at the anchor by the DEBUGGER and independently by the PROGRAM, both sides | pens identical and equal to the shipped boot palette; `$ff8260` = 0 (low res) on both; `Physbase` reads back exactly what was published (`0x8a900` = image base `0x1a600` + `0x70300`), so the address was 256-aligned and nothing was truncated |
| **rendered pixels** | a Hatari screenshot of each side, byte for byte, with `--frameskips 0 --statusbar off --drive-led off` and stop-then-shoot | **byte-identical** |
| **timelines** | `--trace psg_write`, cut into the sound driver's own descending 10..0 tick frames, first 64 compared | identical — the title tune is the same stream, register for register |

Also read back and asserted, from `STATE.BIN`: `boot_enter_supervisor`'s token is the model's
`$00535550`; both IKBD sends report the transmitter went ready; the resolution sink fired exactly
once with mask `$fc`; exactly one title-palette upload; `image[0x195d0]` holds the real TOS vector
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

## What `build.sh` refuses

Four scans, and each names the defect it exists for:

* **The trap-register scan** (`tools/assert_trap_registers.sh --expect 11`). TOS preserves only
  `%d3-%d7`/`%a3-%a6`; GCC believes `%d2`/`%a2` survive too. A wrapper that does not save the pair
  silently corrupts one variable in its C caller, and it is invisible to every differential in this
  project. Eleven wrappers here trap and return; `_start`'s `trap #1` is `Pterm0` and is exempt by
  the scan's own rule.
* **The EA-ordering scan.** A postincrement source and an indexed destination on the SAME address
  register — the instruction GCC folded a sibling project's palette loop into, which put every pen
  one register high and drove the sixteenth write into `$ff8260`, the resolution register.
  `zynaps_backend.c` is written so the shape cannot be emitted; "cannot" is a claim about a
  compiler, so it is measured — and the scan proves it can fail on every run, against two synthetic
  known-bad lines, because a pattern that quietly stopped matching would look exactly like a clean
  binary.
* **The endianness check.** `machine.h` picks native `*(uint32_t *)` accessors on a big-endian
  target; if that guard failed to fire, every field access in every core would be an `lsl #8`
  shuffle chain (a uniform ~4x slowdown and a 40% larger `.PRG`). The count is reported, not gated —
  30 today, where hundreds would be the tell — and `__ORDER_BIG_ENDIAN__` is asserted at the source.
* **The containment checks.** No file under `../src` or `../include` may include a shim header or
  read a target-only `-D`. Asked of includes and macro names rather than of identifiers, because
  those files' own comments discuss `hw_write8` and the target build at length — that is the seam
  documented where it lives, and a grep for identifiers would red on prose.
* **The `os_*` census — the shadow's own central claim, measured.** `shim_include/os.h` replaces
  FOUR kit helpers and pulls the rest in through `#include_next`, so every other `os_*` is still the
  deterministic MODEL, compiled into the `.PRG` and answering out of an in-image register file. The
  header says that is safe because a grep found only those four; this is that grep, run every build.
  A core reaching `os_bconin` would link cleanly and read a real keypress out of a fabricated model,
  with `-DOS_NO_REFUSAL_TALLY` having compiled away the tally that would have counted it: no link
  error, no record field, no surface. M2's own plan ports the routines that would do it.

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
| **6** the EA-ordering shape | designed out of `shifter_write_palette` (one store per pen, through a call, with the address computed as a value) and then scanned for |
| **7** hand-back on every exit path | the whole teardown: both vectors, the chip, `Setscreen`, sixteen pens — each read back into the record, with the emulator left running three seconds past `Pterm` |
| **8** the video base's missing low byte | **the design constraint of this build.** The image's runtime base is rounded up to 256 with reserved slack, and `Physbase` reads the register back: `0x8a900` published, `0x8a900` returned |
| **9** `Super(0)`/`Super(ssp)` is not a pair | `zy_leave_supervisor` plants the USP itself one instruction before the trap. This build is the EXPOSED shape, not the lucky one — `_start` takes supervisor before any C and hands it back a whole boot later, so the two `%sp` depths have no reason to agree |
| **11** a seam's second obligation | the reason the vectors go in AFTER the slice rather than during it: no GEMDOS trap is ever made with TOS's vertical-blank handler displaced |
| **12** a poke's unexecuted input path | the `$12`/`$15` IKBD sends are made, and the record carries the transmitter's verdict — but nothing downstream of the byte is exercised, because M1 has no input path at all. See Unpinned |

## Unpinned, and why

Written down rather than skipped — `docs/on-target-execution.md`'s rule is that a change naming no
surface *is* the finding.

1. **Six of the seven `irq` handlers never execute.** M1 installs `vbl_isr` and `timer_b_isr`;
   `vbl_isr_title`, `timer_b_raster_isr`, `attract_vbl_isr`, `attract_rasterbar_isr` and `vbl_menu`
   belong to the front end, which is unported. So `shifter_write_palette`'s multi-pen path,
   `shifter_clear_pen0` and the palette cycling are compiled and never run. **M2's surface.**
2. **Timer B is installed and never fires** — nothing in M1 programs an MFP timer. So
   `timer_b_isr`'s body and `mfp_ack_timer_b`'s `bclr` are unexecuted. The record carries the count
   (0), so this is a measured claim rather than a belief, but the acknowledge itself is untested.
3. **`screen_flip_buffers`' publish half does not reach the machine.** See "the one seam that is not
   a seam". What holds today is the buffer swap (memory) and the read-back (`Physbase`); a change to
   the two bytes the core computes would be invisible. Closing it needs either a kit-level
   hardware-write ledger — which `../STATUS.md` already names as the surface for the whole off-image
   class — or a seam inside `video.c`, which is a core and not this directory's to edit.
4. **The IKBD's *effect* is unpinned.** The record says the transmitter went ready and the byte was
   stored; that the 6301 disabled the mouse and entered joystick interrogation mode is not
   observable here, because M1 reads no input. This is exactly the shape of taxonomy 12, named in
   advance rather than after.
5. **The Line-A hide-mouse has no surface at all.** There is no mouse pointer in any comparison this
   file makes; the call is here because the boot makes it.
6. **`os_super`'s deviation is not reproduced.** The original follows its `Super(0)` with
   `movea.l d0,a7` and runs on the old supervisor stack for the rest of its life; this build keeps
   the stack GEMDOS gave it. `../STATUS.md`'s `boot_enter_supervisor` row already records that "that
   A7 becomes that token is unpinned" off target, and it is unpinned here for the same reason —
   reproducing it would move the C stack out from under the compiler mid-function.
7. **One TOS ROM.** `docs/on-target-execution.md` class 6's working rule is to run the smoke on more
   than one ROM, and this runs only on TOS 1.04. TOS 1.02 is not an option — Hatari refuses GEMDOS
   directory emulation below 1.04 — so a second ROM means EmuTOS or a floppy build, and both are
   M2-sized. **Recorded, not done.**
8. **Nothing has run on real hardware.** Every number above is Hatari's.
9. **The PSG select/data pair is unmasked inside the handler**, reproducing the original's race on
   purpose. Nothing else in this build writes the chip while the handler runs. The TEARDOWN's
   silence is a different matter and is now masked and made BEFORE the vector restore: handing the
   vertical-blank vector back does not remove the other writer of that latch, it *introduces* it
   (TOS's own vertical blank drives the chip for `Dosound` and the floppy's drive-select lines). An
   earlier draft had the silence after the restore, unmasked, with the argument the wrong way round.
10. **TOS's vertical blank is displaced for the whole title screen** — five seconds under `title`,
    indefinitely under `play`. `_frclock`/`_vbclock` freeze and every `_vblqueue` entry stops,
    including TOS's floppy VBL with its media-change poll and its drive deselect/motor timeout. The
    class-11 argument above is about GEMDOS traps made in that window (there are none), which is a
    different question from what TOS's handler stops DOING. Invisible under `--harddrive`, so this
    smoke can never see it — and it is the idle-fuse shape a floppy build would meet, which is the
    same build item 7 names for the second ROM.
11. **The sixteen pens go up as sixteen stores** where the original's `set_palette_title` ends in
    one uninterruptible `movem.l`. The critical section around the hand-over restores the atomicity;
    what stays unpinned is that nothing MEASURES a half-changed palette, because the anchor is 250
    vblanks later and no surface here samples a single frame during the boot.
12. **The video base is read back as two bytes, and the pens are masked to three bits a gun** — an
    STF's layout. An STE has a third base byte at `$ff820d` and four bits a gun. The pens are saved
    and restored RAW (only the record masks), so the hand-back is correct on both machines; the base
    read-back would simply not see an STE's low byte. Untested either way: nothing has run on one.

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

## What M2 will need from the cores

M1 stops at `0x101ba` because the reconstruction does. To go further:

* **The rest of `_start`** (`0x101ba`..`0x10814`) is blocked at KIT level, not by the program: the
  harness's staged-file table holds eight files and the boot opens about thirty. **On target that
  wall does not exist** — `os_fopen` is a real trap here — so what M2 needs is the SLICE, verified
  off target by a bigger table or by a slice per eight files. `../STATUS.md` names both options.
* **The section flow's tail** (`0x10d96`..`0x10f4e`) and `title_attract_loop` (`0x12ac2`) are both
  blocked on `ikbd_send_cmd`'s ACIA wall. Same shape: `zynaps_os.s` already has the send, and
  `ikbd_acia_isr` (`0x14456`) is the other half — an interrupt handler, so it wants an entry beside
  `zy_vbl_entry`. That is what gives M1's `$15` command something to do and closes Unpinned 4.
* **The frame loop** (`0x10f4e`) needs its three stages (`0x113c0`, `0x11c00`, `0x11d30`), which are
  the wave-3 world-staging work.
* **A kit-level hardware-write ledger** would retire Unpinned 3 and most of the off-image class.
  `zynaps_backend.c` already defines `hw_write8/16/32` under the kit's future names, so that merge
  is deleting `shim_include/hw.h` and nothing else.

## Layout

```
atari/
├── build.sh              title | titlefault | play, plus the four scans
├── smoke.py              the six surfaces and the control
├── run.sh                launches the play build with a screen and sound
├── gen_image.py          stages the relocated program (kit loader) -> disk/ZYNAPS.IMG
├── mkprg.py              base-0 ELF -> GEMDOS .PRG  (a copy; see its header)
├── tos.ld                the link script (a copy; see its header)
├── zynaps_os.s           _start, 11 trap wrappers, the machine primitives, 2 interrupt entries
├── zynaps_main.c         the shim: staging, the boot, the hand-back, the record
├── zynaps_backend.c      the seam's target half + a freestanding libc
├── shim_include/
│   ├── os.h              shadows the kit's: real GEMDOS, no-op Super
│   ├── hw.h              shadows the kit's: adds the write half it does not export yet
│   ├── tos.h             what zynaps_os.s provides
│   ├── zynaps_target.h   what the two C files hand each other
│   └── string.h          the three libc names
├── build/                gitignored
└── disk/                 gitignored — the GEMDOS drive Hatari boots
```

`mkprg.py` and `tos.ld` are **copies**, as they are in `projects/joust/recreate/atari/` and
`projects/wonderboy/recreate/atari/`; each copy's header names the others and says what differs.
Moving them into `tools/recreate_kit/` is the standing kit candidate — registered in Joust's README
("Reviewed and deferred"), in Wonder Boy's `STATUS.md` batch 43 phase A queue, and here.
