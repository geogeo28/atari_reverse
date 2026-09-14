# `atari/` — the rebuilt ROM, and the three instruments that measure a ROM from outside and inside

This directory is the **on-target half** of the TOS 1.02 recreate: the charter's
[Tier 2 (conformance on target)](../../README.md) and the on-target half of Tier 3 (performance).
Tier 1 — the per-function differential against the Musashi oracle — lives in `../test/` and is not
this directory's business.

Four things live here:

| | what it is |
|---|---|
| **the ROM** (`header.S`, `boot_stub.c`, `romdefs.h`, `tos_rom.ld`) | `build/TOS102RC.IMG`, 196,608 bytes, linked at `0xFC0000`, booted with `hatari --tos`. Today it is a **minimal boot stub**: the toolchain→ROM→Hatari→picture loop, proved, so every component the recreate lands afterwards has somewhere to land. |
| **`boot_surface.py`** | what a ROM leaves behind when it has finished booting: the screen, the 256 vectors, the system variables, the low RAM, and how long the boot took on the machine's own clocks. |
| **`tostest.py` + `tostest/`** | `TOSTEST.PRG`, run from a floppy's `AUTO` folder, writes a **conformance ledger** into RAM: the answers TOS gave to a fixed set of calls. Diffed between two ROMs. |
| **`tosbench.py` + `tosbench/`** | `TOSBENCH.PRG`, likewise, writes a **timing ledger**: three workloads on two clocks. Ratio'd between two ROMs, against a measured noise floor. |

Everything is built by one `make`; `build/` and `out/` are gitignored, `golden/` is the tracked
evidence.

---

## The commands

```bash
make                       # the ROM, both .PRGs, and the three 720 KB floppies
make boot                  # build, then boot the stub ROM and capture it -> out/stub-*
make golden                # capture the ORIGINAL ROM's three surfaces -> golden/
make check                 # run all three drivers against the original and report
make test-host             # the host pins: sysvars.py against names.txt and prg/tosapi.h
make clean

# the drivers on their own; --rom defaults to the original ROM. --out is capture's alone:
# golden writes golden/ and compare reads it, and neither has an output prefix to move.
python3 boot_surface.py capture|golden|compare [--rom PATH] [--disk PATH] [--out PREFIX]
python3 tostest.py        capture|golden|compare [--rom PATH] [--out PREFIX]
python3 tosbench.py       capture|golden|compare [--rom PATH] [--runs N] [--out PREFIX]

# the rebuilt ROM against the original's goldens
python3 boot_surface.py compare --rom build/TOS102RC.IMG
```

`make golden` and `make check` run the three drivers **at once** (each boots its own machine into
its own work directory) and report all three in a fixed order, so one red driver does not hide the
other two answers. `ORIGINAL_ROM` overrides where the original is read from; it defaults to
`tools/hatari/TOS102US.img`, is read **in place**, and is never copied into a tracked path (Atari
copyright; the workspace `.gitignore` refuses `**/TOS*.img`).

---

## The machine, and why every flag is in it

One configuration, spelled once, in `hatari_rom.machine_arguments`, whose module docstring is the
flag-by-flag reasoning; this is the summary. Two ROMs are comparable only if the machine either side
of them is the same.

```
-c hatari-machine.cfg
--machine st --memsize 1 --monitor rgb --sound off
--patch-tos off --fast-boot off --timer-d off
--fast-forward on --frameskips 0
--statusbar off --drive-led off --confirm-quit off
--disk-a <image> --protect-floppy off
--run-vbls <N> --parse <script>
```

A 1 MB STF on a colour monitor — the machine TOS 1.02 was sold for, and the size `phystop`,
`_memtop` and every `Malloc` answer move with — with a floppy in drive A on every run (an empty
drive is a different boot, not a cleaner one) and the emulator's own chrome out of the photographed
area. The three that are not obvious:

* **`--patch-tos off --fast-boot off --timer-d off`.** **Hatari modifies TOS images by default and
  is quiet about it.** At `--log-level debug`, the original ROM reports
  `Applying TOS patch 'big VDI resolutions mouse driver'` / `Applied 1 TOS patches, 0 patches
  failed` — and the rebuilt stub reports the *same* patch **failing**:
  `Failed to apply TOS patch 'big VDI resolutions mouse driver' at fd0030 (expected d2c147f9, found
  0)`. A comparison where one side is patched and the other is not is not a comparison at all. With
  the flag off, Hatari logs `Skipped TOS patches.` and both sides run the bytes on disk.
* **`-c hatari-machine.cfg`, first on the line.** **The command line is not the whole machine.**
  Hatari reads a configuration file before it parses any option — `$HOME/.config/hatari/hatari.cfg`
  (on macOS, `~/Library/Application Support/Hatari/hatari.cfg`) or, *with no `HOME` in the
  environment*, `hatari.cfg` **in the current directory** — and everything in it that no flag
  overrides is part of the emulated machine. Measured: a file holding nothing but `[Screen]
  bUseExtVdiResolutions = TRUE` moved the boot metric from **461/1534 to 479/1340**, took the
  desktop from three distinct colours to two and changed the pinned RAM, with nothing on the command
  line to say so. The committed `hatari-machine.cfg` names the settings that have no flag here (the
  extended VDI screen, hard-disk and GEMDOS mounting, drive B auto-insert, and the CPU the machine
  flag re-seeds anyway); `-c` is additive, so it goes first and every flag after it still wins. The
  proof is a run each way: with the file, a hostile `HOME` config changes nothing; with an empty one
  in its place, the same hostile config moves the boot metric.
* **`--fast-forward on`.** Headless Hatari runs in **real time** otherwise: 500 vblanks is ten
  emulated *and* ten wall-clock seconds. With it, measured at **1,450–2,000 VBL/s**, so a boot
  capture costs ~0.3 s of emulation and the whole driver run 1.6 s. It changes no emulated
  behaviour — every cycle of every frame is still executed — only how fast the host feeds it.

**Does Hatari accept an unknown 192 KB image?** *Yes, with no ceremony at all.* It identifies the
ROM entirely from the header — `Loaded TOS version 1.02, starting at $fc0000, country code = 0,
NTSC`, read from `os_version`, `os_base` and `os_conf` — and then applies patches by version plus a
**byte signature at a fixed address**. A signature that does not match is a `DEBUG`-level
`Failed to apply` line and nothing more: no refusal, no warning at the default log level, no
checksum test. So an unknown image boots; a *wrong-sized* one would be identified by its header just
the same and boot into whatever the truncation left, which is why `checkrom.py` asserts the length.

**Other Hatari facts learned the hard way here:**

* **`--machine` RE-SEEDS the CPU.** Measured with TOSBENCH: `--cpuclock 32` *before* `--machine st`
  changes nothing (Bconout = 155 ticks, the 8 MHz reading) and the same flag *after* it quarters the
  workload (38 ticks). Anything meant to override the model's CPU has to come after the model.
* **`--parse`'s commands all run at STARTUP**, so a capture cannot live in one: the breakpoint's own
  `:file` is what defers it. And a **memory** breakpoint cannot be armed at startup at all — at
  power-on Hatari has not sized RAM and refuses a condition on a RAM address — so the ledger watch is
  armed from inside a vblank breakpoint's action file. Three scripts, one per hop.
* **Breakpoint conditions have no arithmetic** (`b VBL > VBL + 50` is refused at the `+`) and exactly
  **one level of indirection** (`(d1).w` is legal, `((d1)).w` is not).
* **A ledger-magic condition must not be quoted.** A quoted expression is evaluated when the script
  is *parsed*, which reads the still-zero longword and arms a breakpoint on the constant 0.
* **Stdin must be `/dev/null`.** When `--run-vbls` expires Hatari enters its debugger and **reads a
  command**; with a terminal on stdin it waits for ever. Three development runs of this directory
  hung exactly that way.
* **`q` in an action file** leaves Hatari in "debug mode" and exits **144**. Nothing here uses it;
  every action file ends in `cont` and the run is bounded by `--run-vbls`.
* **An unknown key or section in a config file is ignored in silence** at every log level, so a typo
  in `hatari-machine.cfg` disables a pin rather than failing. A missing `-c` FILE, by contrast, is a
  hard error.

**What a capture is NOT.** Hatari writes a PNG whether or not the machine did anything, and exits 0
after a bus error it printed to its log. `hatari_rom.boot()` refuses on the log's fault markers, and
`distinct_colours` on the screenshot — checked inside `capture()` itself, so no mode can pin or diff
a black screen — is what tells a painted screen from a blank one.

**And every capture records its INSTRUMENT: the ROM, the floppy in drive A and, for the two ledger
drivers, the `.PRG` on it (name, size, sha256).** `compare` **refuses** — it does not report — when
the floppy or the program is not the one the golden was taken with, because a comparison is a
statement about the ROM and only about the ROM. Rebuilding a disk image changes what the machine
executes as surely as rebuilding the ROM does, and without the check the driver would report that
difference as the ROM's. Demonstrated: a `TOSBENCH.ST` cut without `DATA64K.BIN` refuses with both
shas named, instead of reporting the workload that then fails as a ROM regression.

---

## 1. The ROM

`header.S` emits the OS header — **every field value read out of the user's own `TOS102US.img`**, not
copied from a reference — then the reset entry at `$FC0030`; `boot_stub.c` is the whole of the ROM's
behaviour; `tos_rom.ld` places `.mupb` at `$FEFFF4`, which is *the last twelve bytes of a 192 KB
ROM*, so `objcopy -O binary` produces exactly 196,608 bytes with no padding step.

```
60 2e 01 02 00 fc 00 30 00 fc 00 00 00 00 89 00 00 fc 00 30 00 fe ff f4 04 22 19 87 00 00 0e 96
bra.s  ver   os_start    os_base     os_membot   os_rsv1     os_magic    date(BCD)  conf dosdate
```
plus TOS 1.02's four extra longwords (`p_root $7E9C`, `pkbshift $0E61`, `p_run $87CE`, `p_rsv2 0`)
and, at `$FEFFF4`, the MUPB `87 65 43 21 / 00 00 ca 00 / 00 fd 9e ca`.

**`checkrom.py` is the build's gate** and it runs on every link:

```
ROM header: 13 fields match romdefs.h, 196608 bytes, reset PC $fc0030, MUPB found at $fefff4
            header byte-identical to TOS102US.img
```

It checks the length; every header field against `romdefs.h`; that the opening `bra.s` and
`os_start` agree and that `_reset` is linked there; that **`os_magic` dereferences to the MUPB
magic**; and that the first `OS_HEADER_BYTES` of the image are **byte-identical to the original
ROM's**. The dereference exists because a mutation proved the two-constant version wrong: the MUPB's
address is spelled in `romdefs.h` *and* in `tos_rom.ld` (a linker script cannot include a C header),
and moving the `romdefs.h` one by `0x100` produced a well-formed 196,608-byte ROM with `os_magic`
pointing at twelve bytes of zero — which the old size and reset-PC assertions both passed.

**Mutations, run and caught** (each with a forced relink — `make` relinks nothing after a same-second
edit, and a stale image reports a live mutation as survived):

| mutation | caught by |
|---|---|
| `OS_MUPB` moved to `$FEFEF4` | `os_magic points at 0xfefef4, which holds 0x00000000` + the original cross-check |
| `OS_ENTRY_OFFSET` `0x30` → `0x34` | `os_start … reads 0x00fc0034; the original ROM has 0x00fc0030` |
| `OS_VERSION` `0x0102` → `0x0104` | `os_version … reads 0x0104; the original ROM has 0x0102` |

### The boot stub, and the bug it met on its first build

From the reset vector it sets the supervisor stack (the 68000 takes its initial SSP from the ROM's
first longword, which is the `bra.s` and the version word — garbage), sizes the RAM banks, points the
shifter at `$078000` in low resolution, loads sixteen palette registers and paints sixteen horizontal
colour bands. Then it spins. That is all, and it is deliberately all.

Its **first build reproduced bug class 6** of `docs/on-target-execution.md` — the fourth independent
sighting in this workspace. `palette[pen] = STUB_PALETTE[pen]` over sixteen constant-addressed
registers folded to one instruction, `move.w (%a0)+,(%a0,%d0.l)`; the 68000 computes a `MOVE`'s
*destination* effective address **after** the source's postincrement, so every pen landed one
register high and the sixteenth write went to **`$ffff8260`, the resolution register**, carrying pen
15's `0x555`. The machine then displayed low-resolution data in medium resolution: vertical red and
green stripes, nothing wrong in the C, nothing wrong in the geometry. The fix is the documented one —
launder the pointer through an empty `asm` constraint (`opaque()`); `volatile` is **not** a fix,
because the fold is a choice of addressing mode.

**The stub is 1 MB-specific.** It sizes no memory: `STUB_SCREEN_BASE` and `MEMCTRL_1MB` are both
statements about `--memsize 1`, and booting it on another size is outside its contract.

---

## 2. `boot_surface.py`

Four surfaces, four kinds of evidence: the **screenshot**; the **256 vectors** decoded; the **system
variables** `$400–$5B3` decoded by name; and the **boot metric** — the clocks at the stop point. The
driver's own docstring is the reasoning; below is what it measured and what a reader has to know to
trust a verdict.

### The stop rule — and why the anchor the charter asked for does not exist

The brief named the desktop's first AES `evnt_multi`: a breakpoint on `trap #2` with `d0 = $c8` and
the control array's opcode 25, with a vblank-count fallback. **Measured on TOS 1.02 US: over 900
vblanks of boot, `b (pc).w = $4e42 && d0 = $c8` matches ZERO times.** The boot's first `trap #2` is
at `$fecb6a` with `d0 = $73` — the VDI. TOS's desktop is not an application that traps into the AES:
it is part of the same ROM and calls the AES dispatcher (`$fe65aa`) **directly**. The anchor exists
for a GEM program loaded from disk, not for the ROM's own desktop. (`docs/tos-os-calls.md` carries
this as a transferable entry.)

So the stop rule is **`STOP_VBL = 500` vblanks after power-on**, and it is not taken on trust: every
capture photographs the machine **again at `SETTLE_VBL = 550`** and compares the screen and the
pinned RAM. **The verdict gates** — `capture` exits non-zero on a machine that was still moving, and
`golden` writes nothing — because a golden of a machine in motion pins a moment and the next capture
differs from it for that reason alone. Demonstrated by moving the stop to vblank 200: `screen
MOVING, pinned RAM MOVING at $0917, $0919`, exit 1.

### What is pinned, and what is only reported

**Measured over three boots of the original ROM in this configuration:** RAM `$000–$9FE` is
byte-identical across all three; **645 bytes above it are not** — first at `$9FF`, last at `$C7E9`,
over pages `$0000, $1000, $7000, $8000, $9000, $A000, $C000` (stack scratch and the OS's own working
storage). So:

* **pinned:** `$000` to `RAM_PINNED_END = $9FF`, which contains the whole vector table and the whole
  system-variable block. Carried in `golden/boot-ram.txt` as a **hexdump**, not a hash, so a
  difference is localised to a byte rather than to "something moved". `metrics.json` is pinned too —
  its settle verdict, screen, stop rule, instrument and pinned hash — and compared field by field
  rather than byte for byte, since the same file also carries what only reports.
* **reported, not pinned:** the rest of the 64 KB window, as a sha256 per 4 KB page. Those pages
  differ **between two boots of the same ROM** — seven of them, reproducibly — which is exactly why
  they cannot be a verdict; `golden` and `compare` both print which ones moved.

**Masked** (excluded from every comparison, listed by name in the render): `_vbclock $462`,
`_frclock $466`, `_hz_200 $4BA`. They are masked by **policy** — they count time — and, measured,
all three were *identical* across the three boots, which is what makes the boot metric worth
reporting at all.

### The system-variable table was verified, not recalled — and is pinned to `names.txt`

It lives in **`sysvars.py`**, one table for the renderer, the boot metric and the mask (the three
time-varying variables ARE the boot metric, so neither half spells an address). Two widely published
versions of the `$400` table differ by two bytes around `$44C`; the one here is the one a booted
machine agrees with: `memvalid $752019F3` at `$420`, `memval2 $237698AA` at `$43A`, `memval3
$5555AAAA` at `$51A`, `_vblqueue` at `$456` pointing at `_vbl_list` at `$4CE`, `_v_bas_ad` at `$44E`
equal to `_memtop`, `_drvbits` at `$4C2` reading 3 for the two floppies, `swv_vec` at `$46E` holding
the ROM's own reset entry `$FC0030`, `_sysbase` at `$4F2` holding `$FC0000`.

**The tail is the part a booted machine cannot settle.** `$59E–$5B3` reads all zeroes under TOS 1.02,
so the two published variants — one with a `prt_cnt` word at `$59E` and everything after it two bytes
higher, one with `_longframe` there — are indistinguishable by measurement. The table follows
`projects/tos102us/names.txt`, which is the workspace's source of truth for names and agrees with
EmuTOS's `tosvars.S`.

`make test-host` (`test_atari_pins.py`, 78 assertions, no emulator) pins all of it: every name
against `names.txt`, every `names.txt` variable in the block against the table, the table's
contiguity from `$400` to `$5B4`, and `prg/tosapi.h`'s `SYSVAR_*` addresses against the same
entries. Mutation-tested: renaming an entry, restoring the `prt_cnt` variant and moving `_hz_200` by
one byte are each caught by name.

### The golden numbers

```
boot metric at vblank 500:  _vbclock = 461   _frclock = 461   _hz_200 = 1534
```
461 vblanks at **60 Hz** (this is the US ROM: `palmode $448` reads 0, NTSC) is 7.68 s, and
1534 / 200 = 7.67 s — the two clocks agree, which is the cross-check that says neither is being
misread. The desktop itself is drawn by vblank ~400; the screen holds **3 distinct colours** and
`Getrez` reports **low resolution** (`0`).

### Proved

* **original vs original: identical on every pinned, unmasked byte.** `golden` mode *is* the proof —
  it boots twice and writes nothing unless the two agree and both settled — and `compare` against
  the written golden then reports `EVERY PINNED SURFACE IS IDENTICAL.`
* **the stub ROM vs the golden: the expected report.** Four surfaces differ (screen, vectors,
  sysvars, RAM hexdump) and the boot metric reads `_vbclock=0 _frclock=0 _hz_200=0` — a ROM with no
  OS initialises no system variables. The stub *does* reach the stop point, because the stop is
  Hatari's own vblank counter and does not depend on the ROM doing anything; its screen holds
  **16 distinct colours** and is still at the settle shot.
* **a golden artefact that is not there REFUSES** rather than counting as a difference: a broken
  golden is not a statement about a ROM (demonstrated by deleting `boot-vectors.txt`).

---

## 3. `TOSTEST.PRG` and `tostest.py`

`TOSTEST.PRG` runs from `build/TOSTEST.ST`'s `AUTO` folder, calls a fixed set of TOS entry points and
writes a **ledger** at `0xC0000`: a header plus fixed-width 32-byte records, `magic written last` so
a breakpoint on it cannot catch a half-written table. `prg/ledger.h` is the only definition of the
shape — `ledger_run.py` parses its `#define`s at import, so the C and the Python cannot disagree
about an offset.

Ids are stable and grouped by component (`0x01xx` BIOS, `0x02xx` XBIOS, `0x03xx` GEMDOS, `0x04xx` /
`0x05xx` reserved for the VDI and AES), a record is self-describing (it carries its own name), and a
repeated row keeps one id and counts in `v2` — which is what lets the ledger grow from today's ten
calls to the charter's hundreds without a parser change.

**The nineteen records the seeded ledger produces under the original ROM:**

```
  index  id      name      flags                return        second         third  blob
      0  0x0301  Sversion  -                      4864             0             0
      1  0x0302  Getmpb    -                4294967264             0             0
      2  0x0303  Tgetdat   masked                 3734             0             0
      3  0x0101  Kbshift   -                         0             0             0
      4  0x0102  Drvmap    -                         3             0             0
      5  0x0304  MallocX   -                    952004             0             0
      6  0x0305  Malloc    -                     63804             0             0
      7  0x0305  Malloc    -                     64828             0             1
      8  0x0305  Malloc    -                     65852             0             2
      9  0x0305  Malloc    -                     66876             0             3
     10  0x0306  Fsfirst   -                         0             0             0
     11  0x0307  DirEnt    blob                     16          4641             0  414c5048412e4441
     12  0x0307  DirEnt    blob                    300          4641             1  424554412e444154
     13  0x0307  DirEnt    blob                  65536          4641             2  4441544136344b2e
     14  0x0203  Getrez    -                         0             0             0
     15  0x0201  Physbas   -                   1015808             0             0
     16  0x0202  Logbase   -                   1015808             0             0
     17  0x0103  Bconout   -                        28             0             0
     18  0x0204  ScrnCRC   -                1809140553         32000             0
```

Two answers worth naming, because a reader will otherwise take them for defects:

* **`Getmpb` returns `-32` (`EINVFN`) and fills nothing.** That is TOS's own behaviour, not a broken
  wrapper: `Getmpb` is a boot-time call and GEMDOS refuses it once it is initialised. It is a
  perfectly good conformance answer — a recreate that answered anything else would be wrong.
* **`Sversion` = `0x1300`** — GEMDOS 0.13, which is what TOS 1.02 carries.

Everything else reads as it should: `Drvmap = 3` (two floppies), the four `Malloc(1024)` blocks
1,024 bytes apart with `Mfree` returning 0, the three root files at 16 / 300 / 65,536 bytes stamped
`0x1221` = 1989-01-01 (`st_build.py`'s fixed stamp), `Physbase == Logbase == $F8000`, low resolution.

**The floppies.** Both program disks carry the *same* three root files (`ALPHA.DAT`, `BETA.DAT`,
`DATA64K.BIN`, written deterministically by `mkdata.py` with a byte pattern rather than zeroes), so
the directory walk sees the same entries whichever disk it runs from. Only `\AUTO\` differs — TOS
runs every `\AUTO\*.PRG` on the boot drive, so one program per disk is what makes a run be about that
program. The names are distinct in their first eight characters, which is what a record's blob holds.

**The cursor is turned off (`ESC f`) before anything is drawn.** TOS's VT52 cursor blinks off the
vertical blank, so a CRC of the screen taken with it enabled is a coin flip on the blink phase.

**Neither program terminates.** Both spin after publishing, so the machine the host reads is standing
exactly where the last record was written: no desktop has redrawn the screen the CRC measured and no
later allocation has reused the block. Both also run in **supervisor mode from `_start` to the end
and never leave it** — `_hz_200` and the vector page are supervisor-only reads, and bug class 9
(`Super(0)`/`Super(ssp)` is not a balanced pair) can only bite a program that goes back.

### Proved

* **Two runs under the original ROM give identical ledgers on every unmasked field** — that is what
  `golden` mode requires before it writes anything, and it wrote. It also requires both runs to have
  PASSED (status word zero, no row flagged `FAILED`): a golden is what every later ROM is held to,
  and a failed call's answer pinned as the reference makes the failure the standard.
* `compare` against the golden: `EVERY UNMASKED FIELD AND THE SCREEN ARE IDENTICAL.`
* **The screen-CRC surface was mutation-tested**: changing one letter of the program's banner string
  moved `ScrnCRC` from `1809140553` to `4116099642` *and* changed the screenshot's sha256. A surface
  that cannot fail is not a surface.
* The only masked row is `Tgetdate`, because Hatari seeds the emulated clock from the host.

---

## 4. `TOSBENCH.PRG` and `tosbench.py`

Three workloads, each timed on **two** clocks — `_hz_200` (timer C, 200 a second) and `_frclock`
(vertical blanks). Two clocks and not one because they come from different interrupts: a workload
that moved in one and not the other is a finding about the **timer**, not about the workload, and a
rebuilt ROM that programmed timer C differently would otherwise report every workload off by the same
ratio and look like a uniform performance change.

| workload | what it exercises |
|---|---|
| `Bconout` × 2,000 | the BIOS console and the VT52 driver behind it, including what a scroll costs |
| `Malloc`/`Mfree` × 1,000 | GEMDOS's memory manager, allocate/free round trip |
| `Fread` 64 KB in 8 KB chunks | the whole file-system stack — FAT walk, sector cache, floppy driver, DMA |

### The golden numbers, and the noise floor — PER CLOCK

Five runs under the original ROM, both clocks (the table below is the golden this directory carried
when these numbers were taken; `make golden` re-cuts it and prints the same shape):

```
  workload     clock   median      min      max   spread
  Bconout      ticks      154      154      155   0.65%
  Bconout    vblanks       47       46       48   2.13%
  Malloc       ticks      191      190      191   0.52%
  Malloc     vblanks       57       56       58   1.75%
  Fread        ticks     1400     1399     1421   1.57%
  Fread      vblanks      420      416      423   1.67%
```

**The two clocks do not have the same noise floor, and neither number describes the other.** The
widest tick spread is `Fread`'s 1.57 % and the widest vblank spread is `Bconout`'s 2.13 % — a
workload of 47 vblanks has one-vblank quantisation in it, so the coarser clock is the noisier one on
the short workloads. `compare` ratios **both** and classifies each against its own clock's spread;
`golden` prints a noise floor per clock and says, in those words, when one is wider than the bar
(which would mean the instrument cannot see the bar on that clock).

Ticks are `_hz_200`, so `Bconout` is 0.77 s, `Malloc` 0.96 s and `Fread` **7.0 s** — the floppy read
is floppy-bound, which is why it has the widest tick spread.

**`GOLDEN_RUNS` is 5 and three was measurably too few.** A three-run golden reported `Fread`'s spread
as **0.07 %** and the very next single run came back at ratio **1.002** — outside it. A spread over
N runs is a *lower bound* on the noise, and the bound has to be wide enough that a reading just
outside it is not read as a regression. The five runs **overlap** — each has its own work directory,
prefix and log — which costs **~9 s** of wall clock against **22 s** in a row (measured; a single
capture is 4.6 s).

**...BUT THEY MUST NOT START TOGETHER, AND THAT IS A FACT ABOUT THE INSTRUMENT.** Measured: five runs
launched in the same instant read `Fread` as **1360 ticks five times** (spread **0.00 %**); the same
five started **one second apart** read 1380 / 1299 / 1369 / 1327 / 1283 (spread **7.28 %**). The
emulated floppy's rotational phase comes from the host clock at launch, so simultaneous runs are one
reading taken five times, and a golden cut that way would publish a noise floor of zero and then
read ordinary floppy noise as a regression. Hence `RUN_STAGGER_SECONDS`.

**So `Fread`'s real spread is several per cent, and may be wider than the bar.** Single runs of the
ORIGINAL ROM against its own five-run golden have come back at 1399, 1402 and **1427** (ratio
**1.019**), and the staggered measurement above spans 7.28 % — against a 5 % bar. `Bconout` and
`Malloc` have stayed inside 0.65 % (ticks) over every run so far. **Read a `Fread` tick ratio under
about 1.05 as "no change measured"**, use its vblank clock as the cross-check, and if a component
needs the floppy measured more finely, raise `--runs` and re-golden rather than trusting one table.

**A ratio is only a reading if the run worked.** Before any number is printed, `compare` gates on the
program's own status word, on every row's `FAILED` flag, and on each workload having run the same
number of iterations as the golden's; then it diffs the **screen** the workloads drew. Demonstrated
with a bench floppy cut without `DATA64K.BIN`: `THIS RUN IS NOT A READING` naming all three (status
3, `Fread` FAILED, 0 iterations against the golden's 65,536) and exit 1 — where the earlier driver
would have divided 0 by the median and called it `within the bar`.

### Proved

* Three runs of the original against its own golden: every workload `within the bar`, ratios
  1.000–1.002.
* A capture under the **stub ROM** refuses cleanly and names why:
  `REFUSED: the program under build/TOS102RC.IMG never published its ledger magic within 6000
  vblanks` — a ROM with no GEMDOS runs no `AUTO` folder.
* `golden` refuses to take a reference from a run that failed, for the same reason `compare` refuses
  to report one: a golden is what every later ROM is held to.

---

## Layout

```
atari/
├── Makefile             one build for the ROM, both .PRGs and the three floppies
├── romdefs.h            the ROM's header field values and the stub's machine — ONE definition
├── header.S             the OS header, the reset entry, the MUPB
├── boot_stub.c          the whole of the stub ROM's behaviour
├── tos_rom.ld           links a ROM at 0xFC0000 (no relocation, no .bss)
├── checkrom.py          the build's header gate, incl. the byte-identity cross-check
├── cdefines.py          ONE `#define` parser: every driver reads its constants from the C header
├── sysvars.py           ONE system-variable table: the renderer's, the boot metric's, the mask's
├── test_atari_pins.py   `make test-host`: sysvars.py against names.txt and prg/tosapi.h
├── hatari-machine.cfg   the part of the machine that has no command-line flag (`-c`)
├── tos.ld, mkprg.py     COPIES of projects/wonderboy/recreate/atari/'s, for the two .PRGs.
│                        tos.ld's only edit is the KEEP's object name; mkprg.py is verbatim.
│                        A change to either belongs in both trees.
├── mkdata.py            the deterministic fixture files the two floppies carry
├── prg/                 shared by both programs: os.S (17 trap wrappers), ledger.{c,h}, tosapi.h
├── tostest/tostest.c    the conformance program
├── tosbench/tosbench.c  the timing program
├── hatari_rom.py        THE machine, one way of booting a ROM in it, and what a run was taken WITH
├── ledger_run.py        running a ledger program and parsing what it left
├── boot_surface.py      \
├── tostest.py            > the three drivers: capture / golden / compare
├── tosbench.py          /
├── golden/              tracked evidence: the original ROM's three surfaces (68 KB)
├── build/               gitignored: the ROM, the .PRGs, the floppies, the fixtures
└── out/                 gitignored: captures, comparisons, Hatari logs
```

`prg/os.S` is scanned by `tools/assert_trap_registers.sh` on every build (`--expect 17`): TOS
preserves only `%d3-%d7`/`%a3-%a6` across a trap while GCC's m68k SysV ABI believes `%d2`/`%a2`
survive, so every wrapper saves that pair — a discipline nothing else in the project can see
(`docs/on-target-execution.md`, bug class 3).

---

## What is not done here

* **The ROM does nothing but paint.** Every component the recreate lands has to be linked into
  `tos_rom.ld` and the stub retired; `boot_stub.c` is explicitly a toolchain proof.
* **`TOSTEST` seeds 14 call ids, 19 records.** The format is built to grow to hundreds across BIOS /
  XBIOS / GEMDOS / VDI / AES; the VDI and AES id ranges are reserved and empty.
* **Nothing here has run on real hardware.** Every number is Hatari 2.6.1 on this machine
  configuration. `docs/on-target-execution.md` classes 11 and 12 are the reminder that a headless
  pass is not an iron pass.
* **`golden/` was captured on one host.** The boot metric and the bench medians are emulator
  arithmetic; the RATIO between two ROMs measured the same way is the finding, not the absolute.
* **One unexplained failure of `boot_surface.py compare`, original against its own golden, is on
  record and is NOT reproduced.** It reported two differing surfaces and a slightly different set of
  unpinned RAM pages; **34 consecutive clean runs since** (25 of them back to back) have not
  reproduced it, and the diff itself was filtered out of the terminal before it could be read. One
  latent hazard was removed afterwards — all three drivers used to write `arm.txt` and `screen.png`
  into one shared `out/work/`, and each now has its own — but that is a hazard closed, **not a cause
  proved**. Treat a single red `compare` as worth re-running once before it is believed, and if it
  reproduces, the artefacts under `out/compare-*` are the evidence. (Half of that report is now
  explained: the "slightly different set of unpinned RAM pages" is what two boots of the SAME ROM do
  — seven pages, every time — and no longer counts as a difference anywhere. The two differing
  SURFACES are still unexplained.)
* **ONE PINNED BYTE HAS BEEN SEEN TO MOVE, AND IT IS `savptr`'s LOW BYTE.** In one burst of ten
  boots, **four** reported the settle check as `pinned RAM MOVING at $04a5` and the ten boots
  produced **two** distinct pinned-window hashes; **forty boots since, under an idle host and under
  load, have not reproduced it**. `$4A2 savptr` is the BIOS's save-area pointer, which moves while a
  BIOS call is IN FLIGHT — so a stop that lands during the desktop's idle floppy poll catches it
  moved, and the phase of that poll is exactly the host-clock-derived quantity the bench's `Fread`
  spread measures. This is the most likely cause of the unexplained `compare` above. What happens
  today is the right failure — the settle verdict refuses the capture and `golden` writes nothing,
  so a re-run is the answer — but if it becomes common, the decision to take is whether `savptr`
  joins the masked set (it is the OS's live stack pointer, not part of its steady state) rather than
  whether the check is too strict.
* **The goldens in `golden/` are re-cut by `make golden` whenever the instrument changes**, and a
  golden cut before a driver learned to record its instrument makes `compare` refuse by name rather
  than report. That is the intended behaviour, not a failure: the answer is to re-cut, never to
  loosen the check.
