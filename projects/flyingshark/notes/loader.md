# Flying Shark — what is in the distribution, and how to get the game out of it

`bin/` is not the 1988 floppy release. It is **"PP"'s Gamex hard-disk install** (February 2012,
updated September 2018; see `bin/README.TXT` and `bin/LOG.TXT`), and three layers of wrapper sit
between the shipped files and the program this project is about.

**Decision: the target is the game program, `bin/FLYSHARK.PRG`.** Everything else on this page is
documented so that nobody has to work it out twice, and then set aside.

## The distribution

| File | Size | What it is | Ours? |
|---|---:|---|---|
| `RUNME.TOS` | 3,566 | Gamex loader, Gamex-LZ packed (stream @`0x122` → 16,691 B PRG). Loads `FFS273.HST`/`LFS273.HST`, `C:\GAMEX\HAGA`, `FS240R.BMP`, then `FILES\FSLA`. | wrapper |
| `FFS273.HST`, `LFS273.HST` | 69,888 each | the Gamex runtime ("GOS") and its configuration. Not packed with this cruncher. | wrapper |
| `HAGA` | 13,446 | Gamex hardware-detect data. | wrapper |
| `FS240R.BMP` | 77,878 | the cover scan the loader shows. | wrapper |
| `FILES/D15RU.FIC` | 65,943 | Gamex-LZ packed (stream @`0x20` → 89,632 B). A TOS-like mini OS: strings `PATH=`, `COMMAND.PRG`, `\AUTO\*.PRG`. | wrapper |
| **`FILES/FSLA`** | 24,790 | **stub + packed game.** TEXT `0x698` is the GEMDOS-serving stub; DATA is one Gamex-LZ stream (@`0x6d4`) that inflates to the game. | **the target** |
| **`FILES/FRD`** | 600,440 | **every file the game opens, concatenated.** No per-file headers; the stub's directory holds the offsets. | **the data** |

`tools/unpack_dist.py` produces `bin/FLYSHARK.PRG` (the payload), `bin/RUNME_PLAIN.PRG` and
`bin/GOS.PRG` (the two wrappers, for the record), and `bin/disk/` — the bootable folder below.

**The payload:** 50,358 bytes, `text=0x59f4 data=0x6442 bss=0x3f0a8 sym=0`, **1563 relocations**,
entropy 6.25, sha256 `659c09d5…4325c89`. Strings: `PROGRAMMING BY PRIME SOFTWARE & IMAGES DESIGN`,
`PRIME SOFTWARE LIMITED`, `PLEASE INSERT DISC A AND PRESS FIRE`, `…DISC B…`.

FSLA's DATA opens with a 16-byte record — signature `C3`, three longs of which the last is the
payload's bss size `0x3f0a8` — then a 16-byte name field: **`FLSNDC.TOS`**, which is what the game
was called before it was packed. The Gamex-LZ stream starts immediately after, at file offset
`0x6d4`, with a control byte of `0x11` (a 17-byte literal run) delivering the `601a` header.

## The container's directory

The stub carries it at **TEXT offset `0x538`**, running to the end of TEXT (`0x698`) — 22 entries of
16 bytes: a 12-byte NUL-padded name, then a be32 start offset into `FRD`. **A file ends where the
next entry starts**, and the last entry, `ZZ.TOS`, is a terminator whose start is `FRD`'s own length.
The constant `0x92978` (600,440) is also stored outright at TEXT `0x4b2`.

| # | Name | Offset | Size | What |
|---:|---|---:|---:|---|
| 0 | `FLY_SHK.NEO` | `0x0` | 32,128 | NEOchrome title picture (128-byte header + one 320×200 screen) |
| 1 | `LEVEL5.MAP` | `0x7d80` | 4,624 | level map, first words `000a 00e7` |
| 2 | `LEVEL4.MAP` | `0x8f90` | 4,084 | level map |
| 3 | `LEVEL3.MAP` | `0x9f84` | 4,084 | level map |
| 4 | `LEVEL2.MAP` | `0xaf78` | 4,184 | level map |
| 5 | `LEVEL1.MAP` | `0xbfd0` | 3,664 | level map, first words `000a 00b7` |
| 6–18 | `HSC_C.DAT` … `HSC_0.DAT` | `0xce20` + n·`0x8000` | 32,768 each | thirteen graphics banks, counting **down** from C |
| 19 | `SPRITES.CRU` | `0x74e20` | 117,490 | sprite container (see below) |
| 20 | `MODULE.BAK` | `0x91912` | 4,198 | the PSG music/sfx driver — a GEMDOS PRG, `absflag=$ffff` (position-independent), text `0x1048` |
| 21 | `ZZ.TOS` | `0x92978` | — | terminator: start == `len(FRD)` |

`SPRITES.CRU` opens with a **256-entry directory of 20-byte records**: a be32 data offset followed by
eight words (`0001 0015 0004 0000 0004 0000 001e 0016` for record 0 — the last two look like a
width/height pair). Record 0 points at `0x1400` = 256 × 20, so the directory exactly fills the space
before the first data byte. It is **not** the Wonder Boy `RAD` container — do not run `depack_rad.py`
on it. The `HSC_*.DAT` banks are almost certainly tiles (thirteen of them, each exactly 32 KB, four
loaded at a time), but the layout is unread; `tools/extract_assets.py` renders each as a 320-pixel
wide bitmap and labels that a hypothesis.

## How the stub serves GEMDOS

Read from `python3 tools/prg_dis.py projects/flyingshark/bin/FILES/FSLA`; addresses are TEXT offsets.

**Startup (`0x0`–`0x120`).** Saves the entry `a7` into the operand of the `lea` at `0x112`, and the
basepage pointer into the operand of the `lea` at `0x9e` — the stub patches its own instruction
stream rather than keeping variables. `Super(0)`, stack at `$80000`. It then picks the Gamex GOS's
published parameters out of low memory: `$600`/`$601` (cheat option flags), `$608` → `$4f0` (the GOS
jump-table pointer), `$60c` → `$4a2` (cache buffer), `$610` → `$4a6` (cache size), `$614` → `$49e`,
and the longword four bytes below the current `trap #1` handler → the operand of the `jmp` at
`0x1ea`, which is where unhandled GEMDOS calls go.

**Relocating itself out of the way (`0x64`–`0x96`).** DATA (`0x5a12` bytes — the packed payload) is
copied to `$44000`; then TEXT `0x98`…`0xa28` (2,448 bytes) is copied to `$6600` and jumped to. It has
to move, because what comes next overwrites the stub's own image.

**Unpacking (`0x98`–`0x120`).** The Gamex-LZ depacker at `0x4b6` inflates `$44020` into
**basepage + 228**, so the payload's TEXT lands at basepage + 256 — exactly where the stub's own TEXT
was. The DRI relocator at `0x122` walks the table with the `1` = advance 254 rule, fills in a
basepage (`p_tlen`/`p_dlen`/`p_blen` at 12/20/28, `p_dbase`/`p_bbase` derived), and clears to
`$77d00`. Then `sr = $2700`, the `trap #1` vector at `$84` is pointed at the relocated copy of the
handler at `0x1a0`, `$fffffa07`…`$fffffa13` are masked down to the interrupts Gamex wants, the three
patches below are applied, `a7` is restored, `sr = $0300` (user mode), a basepage pointer is put at
`4(a7)` — the normal GEMDOS entry convention — and it jumps to the game.

**The three patches the stub pokes into the loaded game** (offsets into the game's TEXT; add the
project's `0x10000` load base for a Ghidra address):

| Game TEXT | Ghidra | Patch | When |
|---|---|---|---|
| `0x3c3e` | `0x13c3e` | `clr.w` | only if `$600.b` — "unlimited planes" |
| `0x3cb0` | `0x13cb0` | `move.w #$6002` (a `bra.s`) | only if `$601.b` — "super cheat" |
| `0x426a` | `0x1426a` | `move.l #$4eb86132` = `jsr $6132.w` | **always** |

The unconditional one lands in the middle of the game's **IKBD ACIA interrupt handler** (the routine
at `0x4218` that reads `$fffffc02` and files scan codes), replacing a `bclr #7,d1 / bne`. It is a
Gamex hook — the release advertises exit-to-desktop and state-save hotkeys — not a deprotection, and
the target `$6132` is in the GOS, below the stub's relocated copy at `$6600`. **Nothing needs it to
run the game.**

**The `trap #1` handler (`0x1a0`).** Takes the parameter block from `a7` or `usp` depending on the
saved SR's S bit, then dispatches on the function word:

| Call | at | What it does |
|---|---|---|
| `Fopen` `$3d` | `0x1f4` | **skips the first two characters of the name** (the `A\`), then matches up to 8 characters against the directory, case-folded (`andi.b #$df` for anything above `'9'`), with `.` matching a zero table byte. On a hit it writes the file's start offset and length **into the immediates at `0x29c` and `0x296`** — the Fread routine's own instruction stream — clears the position at `0x49a`, and returns handle **6**. On a miss, `d0 = $df` (EFILNF). |
| `Fcreate` `$3c` | `0x24c` | copies 13 bytes of the name over the string at `0x362` (`2200SAVE.III`), clears the position, returns handle **7** |
| `Fclose` `$3e` | `0x282` | `d0 = 0`, unconditionally |
| `Fread` `$3f` | `0x286` | handle 7 → the GOS path at `0x314`. Otherwise: if the requested span is inside the cached `FRD` window (`0x4aa`/`0x4ae`, valid when `$612f.w` is set), copy straight out of the cache buffer at `[0x4a2]`; else refill the cache through the GOS at `0x370` and re-enter. Advances the position at `0x49a`. |
| `Fwrite` `$40` | `0x2fc` | always the GOS path; passes `'cR'` or `'Wr'` depending on whether the position is zero |
| `Fseek` `$42` | `0x3e4` | requires handle 6. Mode 0 = absolute, 1 = relative, 2 = from the end (`length − offset`, clamped at 0); anything else `d0 = $e0` |
| `Fattrib` `$43` | `0x1f0` | `d0 = $20`, unconditionally |
| `Fsfirst` `$4e` | `0x42e` | matches up to 12 characters (**no** `A\` skip), then `Fgetdta` and fills `d_length` at DTA+26 and 14 bytes of `d_fname` at DTA+30 |
| anything else | `0x1ea` | `jmp` to the saved vector |

The GOS path is a `jsr` through `[0x4f0]` indexed by a word at `8(a1)` — the Gamex runtime's own
jump table — which is why the wrapper cannot be run without the whole Gamex install, and why it is
easier to drop it than to keep it.

## Running the game without any of it

The `Fopen` skipping two characters is the tell: the game asks for its files by the **relative paths
`A\FLY_SHK.NEO`, `A\MODULE.BAK`, `A\SPRITES.cru`, `A\LEVEL1.MAP`, `A\HSC_0.DAT` …** So a folder with
the program and the container's files in a subdirectory `A` is all TOS needs; its own GEMDOS answers
exactly the opens the stub was faking. That is `bin/disk/`, and `tools/boot_shots.py` boots it.

The program goes in **`bin/disk/AUTO/`**, not at the root, and that is load-bearing rather than
tidy — see "Where the screen lives" below.

## Where the screen lives

`boot_init` @ `0x14c04` calls **`Setscreen(log=$70000, phys=$78000, rez=0)` unconditionally**, and
then builds its scrolling ring downwards from what `Physbase` gives back: **ring = [`$58800`,
`$78100`)**, 0x1f900 bytes of it. Nothing about that adapts to where the program was loaded — the
addresses are fixed and the ring is carved out of whatever is there.

The program is `text 0x59f4 + data 0x6442 + bss 0x3f0a8` = **`0x4aede`** bytes, so it survives only
if its TEXT loads at or below `$58800 − 0x4aede` = **`$d922`**. Measured, on TOS 1.04 with 1 MB:

| How it is started | TEXT | BSS ends | vs the ring at `$58800` |
|---|---:|---:|---|
| desktop, `--auto C:\FLYSHARK.PRG` | `$12596` | `$5d474` | **overlaps by 0x4c74 (19,572 B)** — dies |
| TOS's own `AUTO\` scan, no `--auto` | `$aa56` | `$55934` | clears it by 0x2ecc (11,980 B) — plays |

That is the whole explanation of the illegal instruction documented below: at the desktop load
address the module buffer sits at `$5aebe`, its code at `$5aeda`, and the bytes the game's own first
screen writes land on `$5b000`–`$5b01f` — module file offsets `0x142`–`0x161`, exactly the span that
was corrupted, with the crash PC `$5b004` `0x2804` into the ring. Under the Gamex GOS the mini-OS
answers `Physbase` from its own layout; on the original floppy the game loaded low because there was
no desktop above it. **`AUTO\` reproduces that**: TOS runs `\AUTO\*.PRG` on the boot drive before it
loads GEM, so the TPA is as low as the machine gives.

The headroom is only ~12 KB, so this is worth re-checking whenever the machine changes — a different
TOS, more resident software, or a `.PRG` that grows past `0x4aede` puts it back over the line.
`boot_shots.py` asserts `TEXT <= 0x d922` on every run rather than leaving it to be noticed.

**Not built: a real `.ST` floppy.** `tools/st_build.py` writes root files and one hard-coded `AUTO\`
subdirectory, and this disk needs *two* directories — `AUTO\FLYSHARK.PRG` and `A\` with the 21 data
files (650,798 bytes in total, which does fit the 728,064-byte volume). Teaching `st_build.py`
arbitrary subdirectories is the missing piece; it was out of this task's bounds. The GEMDOS-folder
recipe below reaches the same load address by the same mechanism, so nothing about the finding waits
on it — but a disk for real hardware does.

### The reference run

```
python3 projects/flyingshark/tools/boot_shots.py     # TOS 1.04, 1 MB, bin/disk as C:, NO --auto
```

```
hatari --tos tools/hatari/TOS104US.img --machine st --memsize 1 --monitor rgb \
       --confirm-quit off --statusbar off --drive-led off --frameskips 0 --sound off \
       --run-vbls 12000 --slowdown 4 --harddrive projects/flyingshark/bin/disk \
       --trace os_base --trace-file projects/flyingshark/out/boot/os_104.trace \
       --cmd-fifo <the session's>
```

**The game plays.** Payload TEXT at **`$aa56`**; `out/boot/title.png` is the Firebird/Taito title
with **15 of 15** of `FLY_SHK.NEO`'s palette colours on screen, 43 s after power-on; then
`out/boot/attract_1.png` and `attract_2.png` are the **credits** (`PROGRAMMING BY HENRY S CLARK AND
KARL D JEFFERY · GRAPHICS BY JASON G LIHOU · SOUND BY J C BROOKE`) and the **HALL OF FAME**, both
over a live scrolling level-1 backdrop. All three captures differ from each other; no fault lines;
exit 0. So the front end, the level renderer and the vertical scroll all run. Input is untested —
the stick cannot be pressed headless, and the attract cycle does not need it.

`--tos 102` is refused before the emulator starts: Hatari will not emulate a GEMDOS drive below TOS
1.04, so nothing on it would ever run. Testing 1.02 needs the floppy that is not built yet.

Getting that capture took four attempts at an anchor and the lesson generalises, so it is in
`docs/packed-executables.md` too. **The title is on screen for only a few emulated seconds** before
the front end moves on — and in the desktop recipe, for one or two before the crash — so:

- a fixed pre-roll photographed one flat colour three times over, once ten seconds early and once
  after TOS had taken the screen back;
- polling RAM for the payload's TEXT is late (the program is in memory seconds before it draws) and
  slow (a 1 MB `savebin` is a debugger stop);
- waiting on the picture's `Fopen` in a `--trace os_base` file looks exact and is not: **Hatari's
  trace file is buffered**, and by the time that line reaches the host all eight opens are in it.
  Read the trace afterwards for the load order, never as a live signal;
- what works is `--slowdown 4`, which multiplies Hatari's per-VBL wait so the window becomes wide
  enough to photograph, plus a capture check that recognises the picture by its own palette (15/15
  on the title, 5/15 on the TOS desktop, 1/15 on a blank screen, 4/15 on the attract screens). At
  `--slowdown 1` the same capture loop missed the title twice running.

Watch out for **another Hatari on the same host** — a concurrent run in a different project stretched
an unslowed run from ~30 s to ~155 s.

### What the run showed, in load order

`--trace os_base` (kept as `out/boot/os_104.trace`) gives the whole file sequence, and it is **not**
the directory's order:

```
Fopen("A\MODULE.BAK")  Fopen("A\FLY_SHK.NEO")  Fopen("A\HSC_0.DAT")   Fopen("A\LEVEL1.MAP")
Fopen("A\HSC_1.DAT")   Fopen("A\HSC_2.DAT")    Fopen("A\HSC_3.DAT")   Fopen("A\SPRITES.cru")
```

Every open is `Fopen(..., read/write)`, each followed immediately by its `Fclose` — one small
loader routine does all eight. Its `Fopen` trap is at run-time `$b66c` and its `Fclose` at `$b69a`;
against this recipe's base `$aa56` that is **game TEXT `0xc16` and `0xc44` — Ghidra `0x10c16` and
`0x10c44`**, the same two offsets the desktop run gave from base `$12596` ($131ac/$131da), which is
the cross-check that the arithmetic is right. The game also installs its own **VBL handler at TEXT
`0x1636` (Ghidra `0x11636`)**.

### The desktop recipe, and what it cost to understand

Before the `AUTO\` layout, the same folder was booted with `--auto C:\FLYSHARK.PRG` — i.e. from the
desktop. To reproduce it: move `bin/disk/AUTO/FLYSHARK.PRG` back to `bin/disk/`, and add
`--auto C:\FLYSHARK.PRG` to the command line above.

That run loads the payload at **`$12596`** and dies about a second after the eighth file: **illegal
instruction (exception 4) at `$5b004`**, TOS bombs it with `Pterm(-1)`, the desktop comes back and
then hangs in the ROM's floppy wait (`btst #5,$fffffa01` at `$fc1566`) because drive A: is empty.
The title picture is drawn first, so the run looks like a pass until the next capture.

Dumping the music driver out of RAM at a breakpoint on `$5b004` shows it matching `MODULE.BAK` for
its first `0x142` bytes and then diverging: file bytes `0x142`–`0x161` are the driver's PSG-mixer
setup (`btst`/`beq`/`eori.b` × 3 then `lea $ff8800,a0`), replaced in RAM by table-looking data
(`3333 3333 cccc 8888 …`), with the code from `0x162` on intact. The `beq` at file `0x140` branches
into that data and hits `$cccc`. **The overwriting is the game's own screen ring**, per "Where the
screen lives" — not a missing Gamex patch, not a protection check.

## The game's own file table

At game **image offset `0x62ee`** (Ghidra `0x172ee`), in DATA, one record per file:
`be32 buffer address` · `be32 length` · `name, NUL-terminated, padded to even`. The addresses are
image-relative — they are relocated at load — so add the load base (or `0x10000` for a Ghidra
address).

| Name | Buffer (image) | Ghidra | Length |
|---|---|---|---:|
| `A\FLY_SHK.NEO` | `0xbe36` | `0x1be36` | `0x7d80` = 32,128 |
| `A\MODULE.BAK` | `0x48928` | `0x58928` | `0x1065` = 4,197 |
| `A\SPRITES.cru` | `0xbe36` | `0x1be36` | `0x1caf2` = 117,490 |
| `A\LEVEL1.MAP` | `0x6432` | `0x16432` | `0x1388` = 5,000 (buffer; the file is 3,664) |
| `A\HSC_0.DAT` | `0x28928` | `0x38928` | `0x8000` |
| `A\HSC_1.DAT` | `0x30928` | `0x40928` | `0x8000` |
| `A\HSC_2.DAT` | `0x38928` | `0x48928` | `0x8000` |
| `A\HSC_3.DAT` | `0x40928` | `0x50928` | `0x8000` |

`0xbe36` is `text + data` — the start of BSS — and the picture and the sprites share it: the title is
read into the buffer, drawn, and then overwritten by `SPRITES.CRU`. The rest tiles BSS with no gaps:
sprites `0xbe36`→`0x28928`, then the four graphics banks back to back, then the music driver at
`0x48928`. Only four of the thirteen `HSC_*` banks are named here; the others (and levels 2–5) must
be reached by poking a digit into the string, which is the second thing to look for in the code —
along with the `PLEASE INSERT DISC A/B` prompts at image `0x4a40`/`0x4a69`, which are how the
original floppy release swapped them.

The game **relocates `SPRITES.CRU`'s directory in place** after loading it: record 0's offset field
reads `0x1400` in the file and `buffer + 0x1400` in RAM.

A table of TEXT-range longwords follows the filename table at image `0x6396` (`0x53b2`, `0x5408`,
`0x54a4`, `0x5586`, `0x4dda`, `0x4e98`, `0x4fd8`, `0x5188`, `0x4df0`, `0x4ec0`, `0x5012`, `0x51d2`,
`0x4d6a`, `0x4d80`, `0x4d9a`, `0x4db8`, `0x4d58`) — seventeen entries, all inside TEXT, so a handler
or state table.

## Reproducing all of it

```bash
python3 projects/flyingshark/tools/unpack_dist.py          # depack + split; prints the manifest
/Users/geogeo/miniconda3/envs/atari_reverse/bin/python -m pytest projects/flyingshark/tools/
python3 projects/flyingshark/tools/boot_shots.py           # the reference run -> out/boot/
python3 projects/flyingshark/tools/extract_assets.py       # title, palette, bank sheets -> out/assets/
```
