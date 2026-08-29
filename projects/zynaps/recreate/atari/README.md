# ZYNAPS.PRG — the reconstruction on a 68000

**M1: the title picture and its music, produced by the verified cores, on an emulated Atari ST.**

`projects/zynaps/recreate/` holds 196 rows — 185 functions and 11 slices — verified byte-for-byte
against the original 68000 code by the differential harness. Until this directory existed, none of them had ever executed on a
68000. This is the cross-compile: the same C, unmodified, plus a hardware shim, wrapped into a
GEMDOS `.PRG` that boots under Hatari to the title screen with the title tune playing — and a
`smoke.py` that judges it against the shipped binary on six named surfaces.

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

> **Realigned 2026-08-29** for kit commit `f5a2f71`, which moved the cores' hardware sinks onto a
> real write ledger. The shim's `hw.h` shadow and its three per-routine overrides are gone, the
> cores' own `hw_write*` stores are what reach the chip, `ikbd_send_cmd` is a verified core rather
> than shim assembly, and `build.sh` grew a gate for the class of breakage that caused. Same twelve
> checks, same control — plus a **floppy** mode and a bootable `disk/ZYNAPS.ST`.

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
| `psg_port_write` | an ordered write ledger + a register file (`kit/src/psg.c`) | `move.b reg,$ffff8800` then `move.b val,$ffff8802`, from inside the vertical-blank interrupt | kit `src/` excluded → `zynaps_backend.c` |
| `hw_read8` | seeded reads of five declared addresses (`kit/src/hw.c`) | a real `volatile` load. ONE core caller: `ikbd_send_cmd` spinning on the 6850's transmitter-empty bit at `$fffffc00` | kit `src/` excluded → `zynaps_backend.c` |
| `hw_write8/16/32` | an ordered (address, width, value) ledger `harness.differential` compares entry for entry (`kit/src/hw.c`) | a real `volatile` store **of its own width**, counted — and counted again by address for the three core effects the machine cannot be asked about afterwards | kit `src/` excluded → `zynaps_backend.c` |
| `sched_poll8` / `sched_wait8` | polls counted per wait site, with declared stores (`kit/src/sched.c`) | `shim_include/sched.h` — the same spin with NO cap, and `volatile` so the loop keeps reading. `src/highscore.c`'s game-over chain is what calls them | kit `src/` excluded; this shim REPLACES rather than `#include_next`s |
| `sched_poll16` | the word form of the above | **not defined.** No Zynaps core calls it, and an unexercised word read in the one build with no oracle behind it is worse than absent — `shim_include/sched.h` says what to watch for when the first caller arrives | kit `src/` excluded |
| `g_dosound`, `disk_*` | the Dosound ledger, the staged disk | **not defined.** No Zynaps core calls one | kit `src/` excluded |
| `shifter_upload_palette_longs` / `shifter_write_pen` / `shifter_clear_pen0` | **ordinary core code** in `../src/video.c`, writing the ledger through `hw_write32`/`hw_write16` | the same core code, its `hw_write*` now the real store — eight `move.l` over `$ffff8240`, or one `move.w` | nothing: the seam is `hw_write*` |
| `mfp_ack_timer_b` | core code in `../src/irq.c`: `hw_write8($fffa0f, 0)` | the same, as a real byte store — and that is **not** the original's `bclr #0`. See Unpinned 2 | nothing: the seam is `hw_write*` |
| `screen_flip_buffers`' publish half | `hw_write8($ff8203/$ff8201, image offset >> 8/16)`, ledgered and compared | the same store — of an IMAGE OFFSET, which is right where the image is the machine's memory and wrong here. The shim re-publishes the machine address after the slice | `zynaps_main.c`, see below |
| `init_shifter_mode_mask_written` | the one byte the write ledger cannot hold: the MASK the `andi.b` applied | **still a counter** — read into the record. The STORE it describes is the core's own, through `hw_write8` | `zynaps_main.c` |
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
stages the image in a 1 MiB `.bss` array, so the shifter needs `image + 0x70300`, and the core has
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

`python3 atari/smoke.py title`, TOS 1.04, both sides at 4 MB. Re-measured 2026-08-29, after the
kit's write ledger moved the seam:

```
-- title on st / TOS104US.img: image base 0x1c900, the original at 0xaa56, 266 vblanks and 2926 PSG
   pens read off the chip, unmasked: 0033 0021 0202 0044 0055 0066 0665 0777 0550 0303 0413 0746 ...
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
The cost is that a single-sided drive cannot read this disk; the machine it is for is a 4 MB STE.

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
`../../bin/zynaps.st`**, both sides on the same ROM and machine. Twelve checks, all green:

```
-- floppy on st / TOS104US.img: image base 0x14e00, the original at 0xaa56, 266 vblanks and 2926 PSG
   [green] x12, including memory (the framebuffer), rendered pixels, trap ledger, timelines
-- OK
```

Re-run on **TOS 1.02** — a second ROM, which Unpinned 7 asked for and the GEMDOS modes cannot have
(Hatari refuses directory emulation below 1.04) — also twelve green, at a different load address:
`image base 0x17000`. Between the three runs the program has been relocated to three different
places and published a correct 256-aligned video base from each.

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

Eight scans, and each names the defect it exists for:

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
2. **`mfp_ack_timer_b` would acknowledge the WRONG THING if it ever ran — an on-target defect, not
   merely an unpinned byte.** `../src/irq.c` spells it `hw_write8($fffa0f, 0)`, because off target
   the read half of the original's `bclr #0,$fffa0f` answers a fabricated 0 and both sides then
   store 0 and agree. On the machine that store clears EVERY in-service bit in the register, not
   Timer B's. `../include/irq.h` and the kit's `hw.h` both say a target build must not ship the
   expression, and this one does — it is harmless today only because **Timer B is installed and
   never fires** (nothing in M1 programs an MFP timer, and `timer_b_ticks_at_anchor` is 0 in every
   run, which is a measured claim rather than a belief). It becomes live the moment M2 starts a
   timer. Fixing it is a change to a CORE and to the kit's read model, not to this directory: the
   address needs a seeded READ slot so the mask is pinned on both sides.

   Its sibling, `andi.b #$fc,$ff8260` in `../src/init.c`, has the same shape and is **measured
   harmless**: `$ff8260` decodes two bits, and both the mask and a plain 0 leave them clear, which
   is ST low resolution either way. `rez_at_anchor` and `rez_after` read the register back.
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
  the shim is realigned to: `shim_include/hw.h` is deleted, `../src/irq_hw_offtarget.c` is deleted,
  and `zynaps_backend.c` is the target half of the kit's own four `hw_*` names.

## Layout

```
atari/
├── build.sh              title | titlefault | floppy | play, plus the eight scans
├── smoke.py              the six surfaces, the control, and the floppy mode
├── mkfloppy.py           which files under which names -> disk/ZYNAPS.ST via tools/st_build.py
├── run.sh                launches the play build with a screen and sound
├── gen_image.py          stages the relocated program (kit loader) -> disk/ZYNAPS.IMG
├── mkprg.py              base-0 ELF -> GEMDOS .PRG  (a copy; see its header)
├── tos.ld                the link script (a copy; see its header)
├── zynaps_os.s           _start, 11 trap wrappers, the machine primitives, 2 interrupt entries
├── zynaps_main.c         the shim: staging, the boot, the hand-back, the record
├── zynaps_backend.c      the seam's target half + a freestanding libc
├── shim_include/
│   ├── os.h              shadows the kit's: real GEMDOS, no-op Super
│   ├── tos.h             what zynaps_os.s provides
│   ├── zynaps_target.h   what the two C files hand each other
│   └── string.h          the three libc names
├── build/                gitignored — objects, the ELF and the per-mode .PRG/.elf pairs
└── disk/                 gitignored — the GEMDOS drive Hatari boots, and ZYNAPS.ST
```

There is no `shim_include/hw.h` any more, and its absence is load-bearing: it shadowed the kit's
header to add a write half the kit did not export. The kit exports `hw_read8` and `hw_write8/16/32`
itself now, with `uint32_t` values where the shadow declared narrow ones, so keeping the file would
have been a silent signature conflict on top of a redundant one.

`mkprg.py` and `tos.ld` are **copies**, as they are in `projects/joust/recreate/atari/` and
`projects/wonderboy/recreate/atari/`; each copy's header names the others and says what differs.
Moving them into `tools/recreate_kit/` is the standing kit candidate — registered in Joust's README
("Reviewed and deferred"), in Wonder Boy's `STATUS.md` batch 43 phase A queue, and here.
