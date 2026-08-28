# HARDWARE.md — running the reconstruction on a real Atari

Everything in [`README.md`](README.md) was measured under Hatari. This file is for the run that is
not: a physical Atari ST/STE, booting a physical floppy, with nobody able to attach a debugger to
it. It is the runbook for that session — what to write, what to expect, what to watch, and what to
bring back.

**Read the last section before you conclude anything from a failure.** Emulation is not a proof of
hardware, and this project's sibling ports have the crash reports to say so.

---

## 1. What you need

| | |
|---|---|
| **machine** | Atari ST, STE or Mega ST with **at least 2 MB of RAM**. Not negotiable and not a guess — see §2. |
| **TOS** | 1.04 is what every check here ran on. 1.62 (the usual STE ROM) and 1.06 are untested; 1.02 is known-broken *under Hatari's GEMDOS drive* and untested on real media. |
| **monitor** | Colour (RGB or TV). The build takes low-res 320×200×16 and programs 50 Hz PAL. A mono monitor changes the music tempo by design (README §"M1 hardware control") and the picture will not be right. |
| **drive** | One double-sided 720 KB drive as A:. Single-sided drives cannot read these disks. |
| **disks** | Two blank DD floppies (see §3). Not HD disks with the hole taped — they hold a coercivity a DD drive writes badly. |
| **joystick** | Port 1. Cursor keys do **not** work on hardware; that mapping is Hatari's `--joy1 keys`, not the game's. |

## 2. Why 2 MB, and how that was measured

The `.PRG` asks GEMDOS for text + data + bss in one allocation. For the play build that is

```
text 106,496 + data 0 + bss 1,209,070 = 1,315,566 bytes
```

because the reconstruction runs on a flat 1 MiB image (`OS_IMAGE_SIZE`) held in `.bss`, plus 256
bytes of alignment slack. Add TOS's own low memory and there is no 1 MB machine that can load it.

`smoke.py floppy` pass 4 is that fact, measured rather than asserted: the same disk in a 1 MB
machine still has TOS find and `Pexec` `\AUTO\WB.PRG`, and the program never opens `WB.IMG` — it was
never loaded. **On real hardware this failure looks like a disk that does nothing**: the drive
spins, the desktop appears, no game. If that is what you see, check the RAM before you suspect the
disk.

**AND IT IS NOT THE ONLY FAILURE WITH THAT SHAPE**: the idle-fuse race (§8) looked identical on a
4 MB STE — desktop, no title, no bombs. **`WBPROBE.ST`'s record tells them apart**: the memory
failure never opens `WB.IMG` at all, the fuse failure opens it, opens `TITLESCR.RAD` too, and stops
with `title_result = WB_LOAD_DISK_ERROR`. That is why §9 asks you to boot the probe disk and keep it.

## 3. Writing the disks

Build them first, which also runs the five emulated passes that say they work:

```bash
bash atari/build.sh ownrun && bash atari/build.sh ownplay
python3 atari/smoke.py floppy
```

That leaves two images in `atari/out/`:

| image | carries | for |
|---|---|---|
| **`WBOOT.ST`** | `\AUTO\WB.PRG` = the uncapped play build, `WB.IMG`, and **all 40 rows** of `WB_RESOURCE_FILE_TABLE` | **playing**. This is the disk. |
| **`WBPROBE.ST`** | `\AUTO\WB.PRG` = the record-writing build, `WB.IMG`, and six resource rows | **evidence** (§7). It writes its record onto itself. |

**The sizes and the free space are not restated here.** `tools/st_build.py` prints the whole layout —
every file, its clusters, the total, the free bytes and the volume's **sha256** — and `smoke.py
floppy` prints that report for each image as it builds it. One copy, and it is the one that was
measured. Read it off the run you just did.

**Check the digest before you write.** The image the five passes proved and the image on your floppy
are only the same file if you say so, and nothing else in this chain binds them:

```bash
shasum -a 256 atari/out/WBOOT.ST      # must equal the sha256 `smoke.py floppy` printed for it
```

Pass 1 asserts the play image is byte-for-byte unchanged **after** its own boot, so the digest in the
report is the digest of a volume that booted. (`original.py`'s dump manifest is the same discipline
one directory over.) If the two disagree, something wrote to the image after the run — rebuild before
you write the disk, not after.

Write each with the `gw` toolkit's **verified sector route**, which is what
[`gw/README.md`](../../../../gw/README.md)'s "Unprotected disk? Write the `.st`, not the `.scp`"
section prescribes. These volumes are plain FAT12 with no protection of any kind, so the flux route
would only cost you the verify:

```bash
cd ../../../../gw
./write_disk.sh ../projects/wonderboy/recreate/atari/out/WBOOT.ST
```

`write_disk.sh` infers `atarist.720` from the image's 737,280 bytes and reads every track back after
writing. **A track that will not verify after gw's retries is a media or drive fault, not a bad
image** — clean the heads, try another disk. The RoboCop precedent in `gw/README.md` is the reason
this is worth insisting on: an *unverified* write booted to the title screen and then died part-way
through loading, because the bad track was well past the boot area.

Label the physical disks. The two images carry different FAT serial numbers on purpose (TOS uses
them for media-change detection), but the labels are for you.

## 4. What to expect on boot

Insert `WBOOT.ST`, power on, hands off.

| when | what | measured |
|---|---|---|
| 0 | memory test, the TOS boot screen | |
| ~32 s | the screen goes **black**, then the **title screen** appears | `smoke.py floppy` pass 1 prints both figures off the run it just did — the vblank of the first shifter pen write and of the last. TOS's own boot is most of the first; the **window** between them is the title's own load and depack, and that is the part the floppy owns. Batch 44 phase G, TOS 1.04, two runs a minute apart: first pen 1,593 and 1,607, window 277 and 192 vblanks (~4–5.5 s). Repeated runs do not agree to better than that. |
| then | it **waits at the title for fire**, for ever | `-DSMOKE_PLAY` removes the gate's spin bound by design |
| fire | the **credits** screen loads | joystick 1, port 1. **This did not work before 2026-08-27** — see §8's row on the mouse, and the fix is `install` sending IKBD command `$12` |
| fire | stage 1's overlay, tiles and sprites load; the frame loop starts | |

Then it plays, at **four to five frames a second** (README's "Play it" has the measurement and the
reason). ESC quits the round, which draws the data-disk prompt and walks the whole chain again.

**It never gives the machine back.** The build takes the real vectors at `$70` and `$118`, as the
original does, and every ending goes back into the boot chain. The only way out is the reset button.
That is a property of the build and not a fault.

Times will differ from the table: it is measured on an emulated 8 MHz ST with `--fast-forward`
disabled for the FDC, and your drive's seek times are your drive's.

**ABOUT THREE SECONDS AFTER EACH LOAD THE DRIVE GOES QUIET AND ITS LIGHT GOES OUT** — that is the
original's own idle protocol, reproduced (§8). **What you must NOT see is the drive going quiet
WHILE it is loading**: that is the failure §8 describes, and it ends at the desktop.

## 5. The trap-wrapper audit — the class that fails ONLY on hardware

TOS preserves only `%d3-%d7`/`%a3-%a6` across a trap. GCC's m68k SysV ABI believes `%d2-%d7` and
`%a2-%a6` are callee-saved and caches live values in `%d2`/`%a2` across a call to any wrapper. So
that pair is exactly what the compiler expects to survive and TOS may destroy, and a wrapper that
does not save it **silently corrupts one variable in its C caller**. It shipped a
three-bombs-on-the-STE crash in BuggyBoy (`projects/buggyboy/recreate/README.md`, "On-target
register rule"; `docs/on-target-execution.md` taxonomy 3), and it is invisible to every differential
this project has — the oracle services traps in-process and clobbers nothing, and a given TOS build
may leave a benign value in the pair.

Every routine in `atari/wonderboy_os.s` was read against that rule in batch 44 phase G and **the
audit found nothing**: ten routines issue a trap and return, and all ten carry both halves of the
pair.

What is durable is the **shape**, and it is what to check against if you ever add a wrapper:

- **The `movem` pair brackets the trap** — `movem.l %d2/%a2,-(%sp)` before, `movem.l (%sp)+,%d2/%a2`
  after. Both halves, or the routine is only half-correct.
- **The first C argument moves to `12(%sp)`**, not `4(%sp)`, because the pair costs eight bytes of
  stack. Getting the save right and the offset wrong reads the wrong argument.
- **Interrupt entries save `%d0-%d7/%a0-%a6` in full** (`wb_vbl_entry`, `wb_acia_entry`) — they
  interrupt arbitrary code, so nothing about them is a calling convention.
- **`_start`'s own `trap #1` is `Pterm0`, which never returns**, and so has no caller left to
  corrupt. It is exempt by that fact, not by an exception list.
- **`wb_irq_disable` / `wb_irq_restore` issue no trap at all** and read their argument at `6(%sp)`.

Nothing outside this file issues a trap: there is no inline assembly in `wonderboy_main.c` or
`wonderboy_backend.c`, and neither interrupt entry calls a TOS routine.

**The roster of which routines those are is not maintained here** — a hand-kept table of ten names
goes stale the first time an eleventh is added, which is the failure it exists to prevent.
`atari/build.sh` runs
[`tools/assert_trap_registers.sh`](../../../../tools/assert_trap_registers.sh) on every build, which
re-derives it from the source: it walks each routine from its label to the NEXT label, and refuses
the build when one that issues a `trap` and returns does not carry both halves of the pair. It also
asserts the **count** the build expects (ten), so a scan that stopped parsing the file reds instead
of passing over routines it can no longer see. That count in `build.sh` is the one number to update
when a wrapper is added.

**And the scan proves it can fail, on every run**, by re-running the same program over the source
with the save halves stripped and again with the restore halves stripped — each must name every
wrapper. Verified by mutation in batch 44 phase G against three shapes: `Fread`'s save half deleted;
the same with a trailing `| comment` on its `rts` (this file's own house style, which an earlier
end-anchored pattern read as "the routine never closes"); and the same with a guard clause's early
`rts` before the trap. The first draft of the gate caught one of the three.

## 6. What to watch on iron — the reads emulation answers differently

The sibling project's other hardware bug class is a **read the harness answers with a constant**.
Off target the differential oracle returns 0 for any hardware address outside its modeled set, so a
branch that depends on one is green all the way to real hardware and then takes the other arm
(`docs/on-target-execution.md`, tier T4). On target every one of these answers for itself. These are
the five `hw_read8` call sites (`wonderboy_backend.c` names them) plus the two STE registers this
port never writes:

| address | read by | what changes on your machine |
|---|---|---|
| `$fffa01` MFP GPIP bit 7 | `tempo_drop_value` (`src/sound.c:1057`) | the monitor-detect line. **Colour monitor → one music tempo, mono → the other.** Live and asserted (README, "M1 hardware control"). |
| `$ff820a` bit 1 | `tempo_drop_value` (`src/sound.c:1059`) | 50/60 Hz sync. **This is BuggyBoy's register** — the read that was green to real hardware because the oracle answered 0. Here the shim writes it (50 Hz PAL) before the read, so a machine forced to 60 Hz would take the other tempo arm. |
| `$ff8207`, `$ff8209` | both PRNGs (`src/rng.c:33`, `src/behavior.c:2520/2522`) | the shifter's video address counter. Under the oracle it is always 0, "so the diff stays clean while the game's randomness silently disappears". **On hardware the game's randomness comes back** — which means two real runs will not agree with each other, and that is correct. |
| `$ff8800` read-back | `psg_port_read` | the YM2149 register file, including the floppy drive-select bits. See §8's first row. |
| `$ff820d` (STE only) | **nothing here writes it** | the STE's video base LOW byte, which an STF does not have. TOS leaves it 0 and the image is 256-byte aligned, so the picture is right — but a program run before this one that left it non-zero would shift the whole display and no surface in this project would see it. If the picture is offset by less than a line, this is the first thing to check. |
| `$ff820f` (STE only) | **nothing here writes it** | the STE's line-offset register. Same story: 0 after TOS's video init, and a non-zero value would skew every line. |

**A reset before you insert the disk clears both STE registers** and costs you nothing. Do it if the
machine has been running something else.

## 7. Bringing evidence home

You cannot attach a debugger to the machine, and the play build writes nothing. `WBPROBE.ST` is the
channel:

1. Insert `WBPROBE.ST`, power on, and **do not touch the joystick**.
2. The title screen appears, and about six seconds later the fire gate gives up on its own
   (`SPINS_LONG`, ~2,000,000 spins ≈ 6 s at 8 MHz). The drive light comes on, the program writes
   five files and terminates to the desktop.
3. Power off and bring the disk back.

**The disk is not readable by plugging it into a modern machine.** Its BPB is TOS's, and macOS's
FAT driver rejects it outright — measured: `fsck_msdos` answers `Invalid BS_jmpBoot`. There is no
mount, no Finder, no `cp`. The disk comes home the same way every other disk in this workspace does,
through Greaseweazle:

```bash
cd ../../../../gw
./backup_disk.sh wb_probe_run1          # spins the disk ONCE: flux SCP gold master, and the .ST
```

That leaves `gw/dumps/wb_probe_run1/wb_probe_run1.st` — the image the run wrote, read back off the
physical medium. **Do not re-run `smoke.py floppy` first**: it rebuilds `atari/out/WBPROBE.ST` from
scratch, so the copy in `out/` is always a pre-run image with no record on it.

Then read the record out host-side, naming the **dumped** image:

```python
import sys; sys.path.insert(0, "atari")
import smoke
record = smoke.read_own_off_the_floppy("../../../gw/dumps/wb_probe_run1/wb_probe_run1.st")
```

`read_own_off_the_floppy` **raises** if that volume has no `OWN.BIN`, and it cannot reach the GEMDOS
drive at all. Both properties matter here, and the second one is why the obvious spelling is not
used: `read_own(blob=...)` reads a `None` blob as "no blob was supplied" and falls back to
`atari/disk/OWN.BIN` — **the last emulated run's record**. That would hand you a green record off
your own host and call it a hardware result.

`OWN.BIN` (140 B) is the ladder's own account of the run: which slices ran, what each returned, how
many fire gates were crossed, where it stopped. `STATS.BIN` (40 B) carries M1's sixteen read-back
bits, the two clocks, the two hardware reads of §6 and **`ikbd_mouse_disable_sent`** — whether the
ACIA's transmitter took `init_ikbd`'s `$12` (§8's row on the mouse). **A `STATS.BIN` written before
that send is REFUSED by name rather than graded**: it is the same 40 bytes and its version word is
the older one, so a reader would otherwise report a failed send about a build that made none. `M2.BIN`, `FRAME.BIN` (128,000 B) and
`PENS.BIN` carry the frame record and four captured screens.

**If you do press fire**, the run goes further and the record says so — and on that disk the stage
load then fails with `WB_LOAD_DISK_ERROR`, because `SPRITES.CRU` is not on it. That is a recorded
stop arm, not a crash: the probe disk leaves the 279 KB out so that `FRAME.BIN` has somewhere to go.

**And this is the only place the joystick has ever been exercised.** No headless check in this
project has ever run the ACIA handler's two joystick arms (README §12); a person at a real stick on
a real machine is what runs them for the first time. If the title screen does not respond to fire,
that is news, and `OWN.BIN`'s `fire_gates_crossed` is where it is written down.

## 8. Known deviations you will see, and that are not faults

| what | why |
|---|---|
| **One disk, no disk swap.** | The original asks you to swap to the data disk between the credits and stage 1. Everything is on one volume here, so the swap never happens. The *prompt* is still drawn by ESC (README §15). |
| **The drive-select read-back does not mean what it means in emulation.** | `RB_PSG_PORT_A_DESELECTED` is the program reading YM2149 port A back at the end of its run. On a GEMDOS drive nothing else touches that register; with a **real disk in the drive TOS polls it for media change all run long**, so the read-back reads whoever wrote last and that is usually the ROM (measured: the read-back saw `$25`, the ROM's poll, where the program had left `$27`). **The assertion is not dropped, it moves**: `smoke.py floppy` excludes the bit and instead asserts, off the ordered write timeline and filtered to the program's own pcs, that `floppy_deselect_drives` wrote exactly the byte the read-back wanted — and that the ROM wrote *after* it, which is why the read-back could not see it. The ROM's write count is printed per run rather than written down: it is TOS **1.04's** polling rate over that pass's window (hundreds), and the STE's own ROM is a different program with a different one. **`RB_PSG_PORT_A_RESTORED` — the teardown's read-back of the SAME register — lost that race once (2026-08-26) and is fixed by ORDER, not by an exclusion**: the restore and its read-back now run before the level-4 vector goes back to TOS, so the ROM's poll is still dead when they run. On iron the poll is your own drive's ROM, so if this bit ever reds, suspect the order of a teardown edit before you suspect the chip. |
| **The drive deselects ~3 s after each load, not during one.** | `WB_FLOPPY_IDLE_TIMER` is the original's own idle countdown, `vbl_handler` runs it down to `floppy_deselect_drives`, and the two instructions that keep it out of a disk operation live below the file-load seam — so **the seam carries that protocol itself**. It did not until 2026-08-26, and until then the fuse could expire mid-sector: on a 4 MB STE that stopped the boot at the title with the desktop coming back and **no bombs, no diagnosis**. Fixed, and pinned by `smoke.py floppy` booting the play disk on **two ROMs** (it reproduces on EmuTOS, not on TOS 1.04) with a row that forbids a write of ours to port A while a disk operation is open. **The measurement, the trace and what stays unpinned: `../STATUS.md` batch 44 phase H.** |
| **Loads are slower and audible.** | The seam is GEMDOS, so every resource is a FAT12 walk and a WD1772 transfer. The original drove the controller itself. §4 has the measured cost. |
| **Four overlays are damaged on the pressed data disk.** | `OVALAY4B.RAD`, `OVALAY5B.RAD`, `OVALAY6A.RAD`, `OVALAY9A.RAD` differ between the authentic dump (`bin/disk2/`) and the repaired tree. **`WBOOT.ST` carries the authentic bytes**, because a play disk built from a hybrid would be evidence about nothing. The stages those overlays serve may not load correctly, and that is 1989 media rather than this port. `smoke.py floppy` names them on every build. |
| **The mouse stops working the moment the game starts, and comes back on reset.** | The original's own behaviour, reproduced: `init_ikbd` (`$e48c`) sends IKBD command `$12`, disable mouse — and it is what makes fire work at all, because on a real ST joystick 1's fire and the mouse's right button are the same line. **`../STATUS.md` batch 44 phase H addendum has the mechanism and the STE's own record.** This build never hands the machine back (§4), so the reset button is what gives you the mouse; the `$08` in `teardown` is for the modes that do return. |
| **No music tempo change on a mono monitor, because there is no picture.** | The build is low-res only. |
| **It runs at 4–5 fps.** | C compiled for a chip the original was hand-written for. No work has gone into that gap. |

README's "Known gaps" has the rest, and three of them matter on hardware specifically: the file
load is a declared substitution (sector order, retries and the interactive read-error wait are
outside every surface here); `bus.h`'s out-of-image answer is compiled into the `.PRG` and pinned by
nothing on target; and M6 reads five registers while the machine has more.

## 9. If it crashes

**A crash on iron with everything green under Hatari is the expected shape of a hardware bug**, not
a surprise. BuggyBoy's first real-hardware run crashed with a fully green emulated suite, and both
causes were in the two classes above. Suspect them in this order:

1. **A trap wrapper's registers** (§5). The audit says all ten are correct and the build now refuses
   a regression — but the symptom is *three bombs*, usually just after a file load, and it is what
   this class looks like. If you have bombs, note **where in the sequence** (before the title? after
   the credits? during a stage load?): that names which wrapper's caller was running.
2. **A hardware read that answered differently** (§6). The symptom is not a crash but a **wrong
   branch**: the wrong music tempo, a picture offset, randomness that never varies. Nothing bombs.
3. **Memory.** Under 2 MB the game never appears at all (§2). A machine with exactly 2 MB and a
   large resident accessory or driver in the AUTO folder can also fall short — boot with nothing
   else in `\AUTO\`, which is what `WBOOT.ST` gives you.
4. **The disk.** Re-run `gw/write_disk.sh` and watch the verify. A partially-bad disk that boots and
   then dies during a load is exactly the RoboCop failure `gw/README.md` documents.

Whatever happens, **boot `WBPROBE.ST` afterwards and keep it** — its record is the only instrument
on the machine, and a record that stops early says where.

## 10. What emulation cannot prove, honestly

- **That a real WD1772 and a real drive read these disks.** Hatari's FDC is a model; the media is a
  file. Timing, seek behaviour, index alignment and marginal media are all outside it.
- **That a real TOS behaves like this one.** Every check ran on TOS 1.04 (and EmuTOS where noted —
  the floppy mode now runs its play disk on BOTH, which it did not before phase H). The STE's own ROM
  is a different program, and the register-clobber class in §5 is precisely a class where "a
  different TOS" is the whole difference. **No longer hypothetical**: §8's race gave three different
  answers on three ROMs.
- **That the picture is right.** The differential compares memory and the sixteen pens; §6's last
  two rows are two STE registers between the memory and the screen that nothing here reads back.
- **That the joystick works.** Nothing headless has ever run those two code paths (§7).
- **That the sound is right.** The ordered PSG write stream is compared against the shipped binary's
  (README §11); what a real YM2149 makes of that stream is not.

The green suite says the reconstruction does the right things to the machine it was shown. Only the
machine can say what the machine does with them.
