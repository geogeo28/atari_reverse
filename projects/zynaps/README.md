# Zynaps (Hewson, 1988 — Atari ST)

Horizontally-scrolling shoot-em-up. Written by Dominic Robinson for the Spectrum/C64 in 1987 and
converted to the ST by **Microwish** — the credits page names *coding: Howie, graphics: Pete Lyon,
music and sound FX: J. Dave Rogers*. One 42 KB `.PRG` plus 62 data files on a single-sided floppy;
nothing is packed and nothing is encrypted, so the whole game is readable with the normal pipeline.

## The disk

**Provenance.** The user's own copy, dumped from the physical floppy with a GreaseWeazle V4.1 on
2026-08-16. The gold master and its two derived images live in
[`gw/dumps/zynaps/`](../../gw/dumps/zynaps) and are **never written to**:

| file | what it is |
|---|---|
| `zynaps.scp` | 39 MB flux, 5 revolutions/track — the only lossless record. Keep it forever. |
| `zynaps.stx` | Pasti image: sectors *plus* address fields, FDC status, fuzzy masks. Keeps the protection. |
| `zynaps.st` | 409,600 B raw sector image: 80 cylinders × 1 side × 10 × 512 B. Loses the protection. |
| `read.log` | the reader's own log, including its per-track sector map. |

Geometry: single-sided, 80 tracks, 10 sectors/track, 512 B/sector, 800 sectors. `read.log` ends
`Found 770 sectors of 800 (96 %)` and marks cylinders 77, 78 and 79 as missing — but the flux read
them perfectly. `stx_extract.py` shows all 30 present and clean in `zynaps.stx`; what could not be
done is *placing* them, because their address fields claim other tracks (see *Protection* below).
They are a 30-sector hole in the derived `.st`, filled with the reader's bad-sector pattern, and no
file lives there.

### The BPB says one FAT and the disk has two

The boot sector's BPB field `nfats` (offset 16) reads **1**; the volume really carries **2** FATs of
3 sectors each, so its root directory starts at sector 7 (`1 reserved + 2 × 3`), not at sector 4.

It is harmless on a real ST because **the Atari BPB has no FAT-count field at all** — `Getbpb`
returns `fatrec`, *the sector of the SECOND FAT*, and TOS derives the data area from it — so TOS
lays the volume out with two FATs whatever the DOS byte says, which is how the disk really is. Only
a host-side tool that believes `nfats` is misled: it reads the second FAT as the root directory and
finds nothing. The general form of this trap, and the diagnosis, are in
[`docs/binary-formats.md`](../../docs/binary-formats.md).

Two ways to read it, both scripted:

```bash
python3 tools/st_extract.py --nfats 2 gw/dumps/zynaps/zynaps.st   # no byte is touched
bash projects/zynaps/tools/make_bin.sh                            # regenerate the whole of bin/
```

`make_bin.sh` is the only record of how the gitignored [`bin/`](bin) was made: it copies the gold
master, patches that one byte (refusing unless it still reads 1), extracts the tree with
`st_extract.py`, and asserts **63 files, 326,382 bytes**. `cmp -l` against the master reports
exactly one difference, at byte 17. Running `st_extract.py` on the *unpatched* master now warns and
exits non-zero with `DIAGNOSTIC sector 7 looks like a directory (16 live entries) ⇒ nfats=2` instead
of printing "0 files" and exiting 0.

### Boot path

The boot sector holds **no code at all** (bytes `$1e`..`$40` are zero) and its 16-bit word checksum
is `$76be`, not `$1234`, so TOS does not execute it. The game starts the ordinary way: TOS boots to
the desktop, the desktop runs `AUTO\ZYNAPS17.PRG`, and the PRG loads its data files out of the
current drive's root with GEMDOS `Fopen`/`Fread`/`Fclose`. `DESKTOP.INF` on the disk is a stock
desktop configuration, not part of the boot.

### Protection — present on the disk, unread by the game

`python3 tools/stx_extract.py gw/dumps/zynaps/zynaps.stx` reports **30 findings**, all of one kind:

| physical cylinder | its 10 sectors' address fields claim |
|---|---|
| 77 | track **76** |
| 78 | track **73** |
| 79 | track **72** |

Every sector on those three tracks was formatted with a *wrong track number in its ID field*, so a
WD1772 seeking to track 77 and asking for track 77 gets record-not-found — a deliberate format, not
media damage, and the reason the `.st` has a 30-sector hole. The class, and what to establish before
concluding anything from it, are in
[`docs/binary-formats.md`](../../docs/binary-formats.md#protection-pattern-the-address-field-claims-another-track).

**And their contents are now known: each cylinder is a byte-exact clone of the track its address
fields name**, so the `.st`'s hole loses nothing —
[The protected tracks hold nothing new](#the-protected-tracks-hold-nothing-new).

**The verdict is that `ZYNAPS17.PRG` does not check it.** Three independent lines of evidence:

1. **Static.** A byte-level scan of the whole 40,774-byte TEXT finds **zero** references to
   `$ff8604`/`$ff8606` (the WD1772 registers) or to any `$ff86xx` DMA register, at any alignment.
   (The one `ff 86` byte pair in the image is the displacement of `dbf d4,$1584c` at `$158c4`.)
   The whole OS-call census is four GEMDOS traps — `Super` at `$10006` and the
   `Fopen`/`Fread`/`Fclose` of the single loader `load_file` at `$144e8` — one Line-A opcode,
   `$a00a` (hide mouse) at `$10010`, and one XBIOS trap, `Xbtimer` at `$16abe`, which is **inside
   dead code**: it sits in `sound_install_timer_a_dead` at `$16aa6`, a function nothing in the image
   calls (it would have run the sound tick off Timer A). There is no `Floprd`, no `Flopver`, no
   `Rwabs`, no BIOS trap at all: the `trap #13`/`#7`/`#15` the linear sweep prints at
   `$199xx`/`$19a6a` are the bytes of the strings `CODING : HOWIE`, `ROLE OF HONOUR` and the
   `ZXCVBNM` key table.
2. **Dynamic.** The game plays to level 1 from the **patched `.st`** (protection tracks absent) and
   from a **GEMDOS folder** (no floppy in the machine at all), identically to the `.stx`. See below.
3. **Filesystem.** The last cluster any file uses is 361 → sector 733 → **cylinder 73**. Cylinders
   74–79, the protected ones included, are entirely free space. Nothing the game loads is there.

So the protection defeats a whole-disk copier and nothing else — the loader would run just as well
from an unprotected copy. Record it anyway: **`bin/zynaps.st` is not a faithful copy of the disk**,
and `zynaps.stx` is.

## Boot results

`projects/zynaps/tools/boot_shots.py` boots each medium headlessly, drives the front end, and
photographs it into [`out/boot/`](out/boot) as `<mode>_tos<version>_<capture>.png`, beside Hatari's
own `<mode>_tos<version>.log`. The TOS version is in the name because it comes off the ROM's own version
word, so a 1.02 run cannot overwrite the 1.04 evidence.

| medium | front end | level 1 | captures |
|---|---|---|---|
| `gw/dumps/zynaps/zynaps.stx` (protection intact) | yes | **yes** | `stx_tos104_{front1,front2,getready,level1,level1_later}.png` |
| `bin/zynaps.st` (patched, protection tracks absent) | yes | **yes** | `st_tos104_*.png` |
| `bin/disk/` as C:, `--auto C:\AUTO\ZYNAPS17.PRG` | yes | **yes** | `gemdos_tos104_*.png` |

All three reach the cycling front end (the `ZYNPIC.PIC` loading picture → ROLE OF HONOUR → the
credits/menu page, over and over), then `PLAYER 1 / PREPARE FOR COMBAT` over the status panel, then
the scrolling first level with the ship, the ground base and enemy waves.
`out/boot/contact_sheet_tos104.png` shows all three side by side.

**No TOS-version sensitivity.** Both floppy media were run on TOS 1.02 as well and reach the same
states (`*_tos102_*.png`, `contact_sheet_tos102.png`); the ROM only changes where GEMDOS loads the
PRG. The GEMDOS-folder mode has no TOS 1.02 row because **Hatari refuses directory emulation below
TOS 1.04** — it logs `Please use at least TOS v1.04 for the HD directory emulation`, does not mount
the drive, and the `--auto` program never runs. That is an emulator limit, not the game's;
`boot_shots.py` refuses that combination up front rather than failing later with a confusing
symptom. Machine throughout: plain ST, 1 MB, RGB monitor.

**What a boot proves, and what it does not.** The surface is *rendered pixels plus the emulator's
log and exit status* ([`docs/on-target-execution.md`](../../docs/on-target-execution.md), "The
observable surfaces"), and a run is only evidence if all of them agree: `boot_shots.py` fails the
run if Hatari logs a bus/address error or a load failure, if the emulator dies before the timeline
ends, if it exits non-zero, if any capture holds a single colour (a photograph of a blank screen), or
if the level-1 capture is the same picture as the first front-end one. A blank frame is retaken up to
five times first — the game blanks the screen for a couple of seconds between front-end pages, and
where that gap falls moves with the ROM (it caught a page on TOS 1.04 and black on 1.02). What it does **not** prove is
the input path: only the fire byte is poked, so the IKBD-to-`$9681` delivery below it and in-game
steering are not exercised *by these runs*. The KEYBOARD half was exercised later, by the pause
demonstration under [Secrets and dead code](#secrets-and-dead-code) — a real Hatari key event
carried through the ACIA handler to `$9685` and back out as a frozen frame. The joystick half is
still unproven either way.

**The GEMDOS folder works because the game opens its files by bare name** — no drive letter, no
path — so the current drive is whatever it was booted from.

## Boot it yourself

```bash
bash projects/zynaps/play.sh                          # the faithful .stx in a window, sound, joystick on keys
bash projects/zynaps/play.sh st                       # the patched raw sector image
bash projects/zynaps/play.sh gemdos                   # bin/disk/ as C:, auto-running the PRG
bash projects/zynaps/play.sh headless stx             # no window: boot, drive it, photograph into out/boot/
bash projects/zynaps/play.sh headless stx --tos 102   # ...on a different ROM; --tos-rom PATH takes any image
ZYN_TOS_ROM=/path/to/tos.img bash projects/zynaps/play.sh
```

`play.sh` is a thin wrapper: `projects/zynaps/tools/boot_shots.py` owns the Hatari command line —
media, ROM, machine, memory — and `play.sh` asks it for the GUI variant with `--print-command` and
execs that. Everything after the mode is forwarded to the driver.

Controls are **joystick port 1**, emulated on the keyboard by Hatari's `--joy1 keys`. The game reads
the keyboard directly in three places: the front end takes `1` for a one-player game and `2` for a
two-player one, the level takes **`SPACE` to pause** (see
[Secrets and dead code](#secrets-and-dead-code)), and high-score name entry takes the whole
keyboard through its own scancode map.

**`SPACE` does *not* step the front-end page**, as this file, `play.sh` and `boot_shots.py` used to
say. `attract_wait_for_start` `$12bb4` tests scancode 2, scancode 3 and joystick fire and nothing
else; the pages turn on their own 750-frame timer (`attract_page_timer` `$19f1e`, `$12c1e`), which is
why pressing SPACE there looked like it worked.

**The PLAYABLE RECONSTRUCTION is a separate thing, and it runs on a real STE.** Everything above
boots the ORIGINAL 1988 binary in Hatari. The C reconstruction in
[`recreate/atari/`](recreate/atari/README.md) cross-compiles to its own bootable `ZYNAPS.ST`, and
the user has booted that floppy on their 4 MB STE and played it — STE-confirmed playable. It adds
three deliberate divergences from the original: the `Z`-`Y`-`N` trainer (arm by typing the three
keys in order at the title, then `F1` invulnerability / `F2` lives / `F3` power-ups, with per-key
sound feedback), `ESC` → menu, and `F10` → TOS. See
[`recreate/atari/README.md`](recreate/atari/README.md) for the detail, the French-keyboard argument,
and which of those features are STE-confirmed versus still emulator-only.

### Driving it headless

`projects/zynaps/tools/boot_shots.py` is the headless driver; the Hatari plumbing it sits on —
opening the command FIFO without being able to hang, awaited screenshots and RAM dumps, the log
scan, finding a loaded `.PRG` in RAM — is shared in
[`tools/hatari_headless.py`](../../tools/hatari_headless.py). Three things it knows the hard way:

- **Hatari's `--cmd-fifo` has no joystick event.** `hatari-event` takes mouse buttons and keys
  only, and a key bound to the keyboard-as-joystick emulation is swallowed headless. The front end
  does not care (it tests scancodes against the "last key" byte its ACIA handler files), but the
  `PREPARE FOR COMBAT` gate does: it re-sends IKBD `$16` (interrogate joystick) and spins on
  `bpl` until bit 7 of `$9681` — fire — is set, and no key will do.
- **So fire is poked into that byte, on a breakpoint at the gate's own `tst.b`.** A *timed* poke
  races the real IKBD replies, which clear the same byte a few thousand cycles later; it opened the
  gate in one run out of three. Stopping the CPU on the instruction that reads the byte removes the
  race. The gate is at TEXT offset `$0f2a` (`$10f2a` in `out/prg_dis.txt`), and it was **found, not
  read off the sweep** — three other `tst.b $9681` loops look identical, and the one actually
  spinning came off the return address on the supervisor stack while the game sat on the gate. The
  load address is found the same way: a RAM dump, searched for the PRG's own first TEXT bytes,
  because GEMDOS puts the program somewhere different on a floppy boot, on drive C:, and on each
  TOS version. Those bytes appear **twice** during a floppy boot — once in the disk buffer being
  read in, once in the loaded program — and the two are told apart by relocation: GEMDOS adds the
  load address to the first fixup's longword in place, so only the loaded copy satisfies
  `longword == the file's longword + base`.
- **The run is anchored on what the machine did, twice — not on a stopwatch.** The first anchor is
  the RAM search above, polled from 6 s until it hits, so a slower host shifts the whole run instead
  of silently photographing a TOS desktop. The front-end offsets were then measured by
  screenshotting a whole floppy boot every 2 s: the PRG is in RAM at ~7 s, but it spends **~20 s
  reading its 62 data files behind a static loading picture** and the interactive front end only
  appears around load + 27 s. The second anchor is the **gate itself**: the same breakpoint that
  pokes fire also `savebin`s that byte to a host file, so the driver waits for the gate to be
  crossed and dates the in-game captures from there. That one is not a refinement — with fixed
  delays the `level1` capture was the level on the `.stx` and still the PREPARE FOR COMBAT screen on
  the `.st`, ten seconds apart, and no check on the picture can tell those two apart: both are the
  same status panel in 32 colours.

## File inventory

| file(s) | bytes | role |
|---|---|---|
| `AUTO/ZYNAPS17.PRG` | 42,360 | the game: text `0x9f46`, no data, bss `0x54a28`, 1506 relocations, entropy 6.07 |
| `ZYNPIC.PIC` | 32,000 | the loading/title picture — one raw 320×200 low-res screen |
| `STATUS.PI1` | 8,480 | the in-game status panel — 320×53, **not** a Degas PI1 despite the extension |
| `ZYN1/ZYN3/ZYN8.DAT` | 39,488 / 35,648 / 32,128 | level tilesets: 617 / 557 / 502 tiles of 16×8 |
| `LEV{1..9,X,Y,Z}.MAP` | 4,118–8,718 | the twelve level maps, RLE'd, 18 rows × 400 columns of tile words |
| `MYSHIP.DAT` | 2,800 | the player ship, 7 frames |
| `ALIEN{A..H}.DAT` | 640 / 160 | eight enemy types |
| `MOTHER{1..7}.DAT` | 1,600 / 320 | the large enemy craft |
| `ALSEEK`, `SEEKER2` | 880 | homing enemies · `BIGAST` 3,840 asteroids · `SPINNERS` 320 |
| `BULLET`, `NEWBOMB`, `NEWBULS2`, `MISSILE{1,2,3}`, `ROTBALLS` | 80–360 | shots |
| `EXPLODE`, `SMALLEXP`, `ALTEXPL` | 1,920 / 960 / 1,280 | explosion cycles |
| `SWEAP`, `SSWEAP`, `POWER`, `GUNSIGHT`, `LIFEGRA`, `SMSHIP` | 32–2,080 | HUD: weapon icons, power bar, sight, life/ship markers |
| `GEMGRAF`, `GNDTARG1`, `ROCKET` | 640 | pick-ups and ground targets |
| `CHARS2.DAT` / `EXTCHARS.DAT` | 1,600 / 1,920 | the game font, 40 and 48 glyphs |
| `ZYNLOGO`, `HEWLOGO`, `SMLOGOS` | 6,144 / 1,536 / 2,560 | the ZYNAPS and HEWSON logos, large and small |
| `DESKTOP.INF` | 478 | stock TOS desktop configuration, not used by the game |

## Asset formats

Decoded by [`projects/zynaps/tools/dat2png.py`](tools/dat2png.py), which renders every asset into
[`out/assets/`](out/assets) (62 PNGs). Each layout was read out of the PRG and then **confirmed by
rendering** — the three routines that pin the whole set down are `load_file` `$144e8` (which gives
every asset's exact byte count from its call sites), `unpack_frames` `$153c0`/`$153f6` (`d2` =
bytes per frame, `d7` = frames − 1, which gives every frame split) and `unpack_level_map` `$15920`.
The filename strings are at PRG file offset `0x96a2` and are **lowercase**, which is why a
case-sensitive grep for `ALIENA.DAT` finds nothing. Rendering needs Pillow — run it with the
workspace's python; `--scan-palettes` does not, so it works with plain stdlib. The plane, mask and
palette decoding itself lives in the shared [`tools/st_pixels.py`](../../tools/st_pixels.py).

```bash
python3 projects/zynaps/tools/dat2png.py projects/zynaps/bin/disk projects/zynaps/out/assets
python3 projects/zynaps/tools/dat2png.py --scan-palettes --prg projects/zynaps/bin/ZYNAPS17.PRG
```

**Masked word sprite** — the format of most `.DAT` files. Each row is `width/16` groups of five
big-endian words: `mask, plane0, plane1, plane2, plane3` (10 bytes per 16 pixels). A **set** mask
bit is transparent — the blitter ANDs the mask, then ORs the data. Colour index 0 is a real palette
colour, not a transparency key.

| file | bytes | format | confirmed? |
|---|---|---|---|
| `ZYNPIC.PIC` | 32,000 | raw 320×200, 4-plane **interleaved** (not contiguous planes) | **rendered** — title art + HEWSON logo |
| `STATUS.PI1` | 8,480 | raw 320×53 interleaved, **no header, no palette** (8480 = 53 × 160) | **rendered** — the status panel |
| `ALIEN[A-G].DAT` | 640 | masked 16×16, 4 frames | **rendered** (`d2=$a0 d7=3`) |
| `ALIENH.DAT` | 160 | masked 16×16, 1 frame | **rendered** |
| `ALSEEK`, `SEEKER2.DAT` | 880 | masked 16×11, 8 frames | **rendered** (`d2=$6e d7=7`) |
| `ALTEXPL.DAT` | 1,280 | masked 16×16, 8 frames | **rendered** |
| `BIGAST.DAT` | 3,840 | masked **32×32**, 6 frames | **rendered** — asteroids |
| `BULLET`, `NEWBOMB.DAT` | 80 | masked 16×8, 1 frame | **rendered** |
| `EXPLODE.DAT` | 1,920 | masked 16×16, 12 frames | **rendered** — a clean explosion cycle |
| `SMALLEXP.DAT` | 960 | masked 16×16, 6 frames | **rendered** |
| `GEMGRAF`, `GNDTARG1`, `ROCKET.DAT` | 640 | masked 16×16, 4 frames | **rendered** |
| `GUNSIGHT.DAT` | 90 | masked 16×9, 1 frame | **rendered** |
| `MISSILE1-3`, `ROTBALLS.DAT` | 360 | masked 16×9, 4 frames | **rendered** |
| `MOTHER1-5.DAT` | 1,600 | masked **64×40**, 1 frame | **rendered** — big alien craft |
| `MOTHER6/7.DAT` | 320 | masked 32×16 | 32 px wide rendered; **1-vs-2 frame split guessed** |
| `MYSHIP.DAT` | 2,800 | masked **32×20, 7 frames** | **rendered** (code: 7 buffers 400 B apart) |
| `NEWBULS2.DAT` | 120 | masked 16×3, 4 frames | **rendered** |
| `SPINNERS.DAT` | 320 | masked 16×8, 4 frames | **rendered** |
| `SWEAP.DAT` | 2,080 | **unmasked** 4-plane 32×26, 5 frames | **rendered** — boxed weapon icons |
| `SSWEAP.DAT` | 864 | **unmasked** 4-plane 16×18, 6 frames | **rendered** — small weapon icons |
| `CHARS2.DAT` | 1,600 | byte-masked font: mask byte + 4 plane bytes per row, 8 rows = 40 B/glyph, **40 glyphs** | **rendered** — reads `0123…XYZ!?:.` |
| `EXTCHARS.DAT` | 1,920 | the same, **48 glyphs** (adds Spc/Del/Clr/Ent key captions) | **rendered** |
| `HEWLOGO.DAT` | 1,536 | unmasked 4-plane 64×48 | **rendered** — HEW/SON stacked |
| `ZYNLOGO.DAT` | 6,144 | 192×64 stored as **three vertical 64×64 strips** | **rendered** — reassembles to ZYNAPS |
| `SMLOGOS.DAT` | 2,560 | **two** 80×32 pictures, each five vertical 16×32 strips | **rendered** + the blitter at `$1452c` |
| `ZYN1/ZYN3/ZYN8.DAT` | 39,488 / 35,648 / 32,128 | flat array of 16×8 4-plane **64-byte tiles, no header** → 617 / 557 / 502 tiles | **rendered** |
| `LEV*.MAP` | 4,118–8,718 | 18 rows × 400 columns of tile words, per-row RLE | **rendered** — the decoder consumes every file to its last byte |
| `SMSHIP.DAT` | 32 | byte-granular 4-plane 8×8 | **guessed** — plausible, too small to be sure |
| `LIFEGRA.DAT` | 64 | byte-granular 4-plane 8×16 (two 8×8 icons) | **guessed** |
| `POWER.DAT` | 1,024 | unmasked 4-plane 64×32 (row stride 32 B) | **guessed** — geometry solid, content unidentified |

**The `0x7888` at the head of `ZYN*.DAT` is not a header.** It is the first tile word. Likewise the
`0x800c`/`0x801a` at the head of `LEV*.MAP` is the first RLE control word, not a width/height.

**`LEV*.MAP` RLE** (from `unpack_level_map` `$15920`): per row, read a control word — if
`ctrl & 0x8000` is clear, the next `ctrl` words are **literal** tiles; if set, the next single word
**repeats** `ctrl & 0x7fff` times. Each row expands to exactly 400 entries and the destination is
column-major (36 B per column). Within a tile word, bits 0–14 are the tile index and **bit 15 is an
attribute flag** (collision/solid; not needed to draw).

**The four `'q'` sections are asteroid fields, not bonus stages.** The map-letter table at file
`0x9868` reads `5 q 2 3 8 4 q 7 6 9 q z x y 1 q` — four `'q'`s among the twelve level letters. At
`$109cc` the section-type test takes that letter, and on `'q'` it **skips the map load entirely**,
loads `BIGAST.DAT` through `asteroids_load_and_build` (`$156ac`), sets `asteroid_section_flag` and
takes the `palette_asteroid` palette. `asteroids_draw`/`_move`/`_animate` (`$159be`/`$159f2`/`$15a6a`)
run 18 columns of asteroid records instead of a tile map — which is why those sections have neither a
`LEV*.MAP` nor a tile set.

**Level → tileset** (PRG byte tables at file offsets `0x9868`/`0x9878`/`0x9888`): LEV1, 2, 4, 5, X →
`ZYN1`; LEV3, 6, 7 → `ZYN3`; LEV8, 9, Y, Z → `ZYN8`. Cross-checked by maximum tile index: LEV1's max
is 616 against ZYN1's 617 tiles, LEV6's 556 against ZYN3's 557, LEVZ's 501 against ZYN8's 502. Only
three tilesets exist because only three are referenced — that is not a gap in the dump.

### Palettes

16 ST words, `0x0RGB`, 3 bits per channel. `dat2png.py --scan-palettes` lists every maximal run of
valid colour words in the PRG (26 of them); four are real, and the rest are data that happens to
satisfy the mask.

A **file** offset here is `names.txt`'s Ghidra address minus `0x10000` plus the 28-byte GEMDOS
header — `0x9614` in the file is `palette_frontend` at `$195f8`. Both are given because the code
sites are spelled in Ghidra addresses and `dat2png.py` reads the file.

| PRG file offset | `names.txt` | what it is | proof |
|---|---|---|---|
| `0x8fe0` | `palette_hw_shadow` `$18fc4` | panel / fade (STATUS, S/SSWEAP, POWER, fonts) | written to `$ff8240` by the Timer-B split at `$106ae` |
| `0x9000` | `palette_per_section_table` `$18fe4` | **12 level palettes**, 32 B each | staged into `palette_next` at `$10a5e`, indexed `$1986c[section] * 32` |
| `0x9614` | `palette_frontend` `$195f8` | title/logo palette — ZYNPIC, ZYNLOGO, HEWLOGO, SMLOGOS | `movem.l $95f8` at five sites |
| `0x9634` | `palette_boot` `$19618` | the boot/title palette (also `palette_title`) | `# ctx` in `names.txt` — inferred from call context, not a body read |
| `0x9654` | `palette_asteroid` `$19638` | the **asteroid-field** palette | taken at `$109cc`, on the branch where the section letter is `'q'` |

## Music and sound effects

Every sound the game has — 45 numbered streams — dumped by
[`projects/zynaps/tools/extract_audio.py`](tools/extract_audio.py) into
[`out/audio/`](out/audio): a `snd_NN.ym` (one YM2149 register file per 50 Hz frame, uncompressed
YM6) for each, a `snd_NN.wav` (44100 Hz mono) for each that is a sound the game can play on its own,
plus a `manifest.tsv`. It needs numpy, so run it with the workspace's python or
`recreate/.venv/bin/python`:

```bash
projects/zynaps/recreate/.venv/bin/python projects/zynaps/tools/extract_audio.py   # ~30 s
```

Beside them, `ref_title.wav` / `ref_level1.wav` and their `.regs` files are a recording of the
**real game** running in Hatari, which is what the dumps are judged against — see
[Judged against the real game](#judged-against-the-real-game) below.

**It plays the original code, it does not re-implement it.** The tool loads `ZYNAPS17.PRG` through
the kit's PRG loader and runs the game's own 68000 replayer under the Musashi oracle
([`tools/recreate_kit`](../../tools/recreate_kit)) inside `emu.audio_capturing()`: `sound_reset_psg`
once, `sound_start` once with `d1` = the number, then `sound_tick` once per emulated VBL, tapping
the `$ff8800`/`$ff8802` write stream after every tick. `recreate/src/sound.c` decodes the whole
format, but nothing here reads it — the frames are what the original wrote.

**The numbers.** `sound_start` `$16ac8` takes `d1` = 0..44, an index into the little-endian offset
table `tune_index` `$17058` over `tune_data` `$171e8`. Three groups come out of the sweep:

| | count | what they are | `.wav`? |
|---|---|---|---|
| music | 5 | the capture proved a loop (or hit the cap): they never end | yes |
| sfx | 22 | they stopped themselves — command `0xe1` ran on every voice they armed | yes |
| part | 18 | **continuation streams**: no sound of their own (below) | no |

Total 47,013 frames = 940 s of audio. A one-shot may still use several voices — `0x14`, the ship
exploding, arms two — so "sfx" means *it ends*, not *it is one voice*; the manifest's `voices`
column is the separate fact.

`0x0b` is the boot tune *and* the title music (`_start` at `$1007a`, `moveq #$b,d1`) — a 262 s
three-voice piece that spawns `0x0c` and `0x0d` on voices 2 and 3 with `fd`/`fe`, 56 s of lead-in
and then a 206 s exact loop. The other music the game starts directly is `0x0e` (24 s),
`0x1e` (12.8 s) and `0x27`. The busiest effect is `0x2c`, fired from six sites.

**A stream with no `fa <chan>` header is a PART, and a part gets no `.wav`.** Numbers 0–10, 12, 13,
31–33 and 40–41 carry no header: the game reaches them only through another stream's `0xe5` jump or
`0xfc`/`0xfd`/`0xfe` spawn, mid-piece, by which point the parent has chosen the voice and its volume
and pitch tables. Started here they run on **voice 3** — the driver's fall-through for a channel
byte that is neither 1 nor 2 — where the parent would have picked the voice (`fd 0c` puts 12 on
voice 2). Numbers 0–9 additionally carry no `0xe8` volume-table command, so `sound_voice_modulate`
steps their volume byte up from 0 against whatever record the voice was already holding — which,
from a freshly loaded image, is nothing, and they come out **silent at the register level**. The
other nine make a noise, but it is one bare voice of a piece at whatever level the modulator walks
to, which is not the sound the game has either.

So the rule is: **a `.wav` is written only for a stream that opens with its own `fa <chan>`.** Both
kinds of part would otherwise be a misleading file to double-click — ten of them silent, eight of
them half a tune — and the `.ym` beside them still carries the register stream, which is the fact.
To hear a part, play its parent: **11 spawns 12 and 13**, **30 spawns 31, 32 and 33**, **39 spawns
40 and 41**. `manifest.tsv`'s opening-bytes column shows most of those spawn commands, but not all —
30's `fe 1f` is 46 bytes into its stream, past the ten the column carries — so the walk below, not
the manifest, is what the claim rests on. Those parents also spawn streams that are *not* parts:
both **14 and 39 spawn 36**, which has its own `fa` header and its own `.wav`. And a part is reached
by another stream's `$e5` **jump** as well, which behaves like a call; the full reachability walk is
under [Secrets and dead code](#secrets-and-dead-code) — it is what shows that **nine** of the 45
streams can be started by nothing at all.

**Where a capture stops.** A sound that ends itself ends the file. One that does not is run to a
15,000-frame cap while a detector watches the driver's whole mutable state (`$16e82`..`$16f40` —
shadow, toggle, noise block, three voice records): a repeat there proves the output loops forever.
Eight numbers close that way. Thirteen cannot, because `sound_noise_modulate` steps the noise
block's counter pair on *every* tick, and against the record the binary ships (cursor 0, so both
limit bytes read 0 out of the zeroed vector page) the first byte only fires when it wraps — 256
ticks — and the second only when *it* wraps, 65,536 ticks. The one thing that rewinds the pair is
`note_on` consuming a pending `0xe4`, which is exactly why the tunes using `0xe4` reach an exact
loop and the rest cannot. For the rest the fallback rule ignores that counter pair only, takes the
repeat it finds, and writes the lead-in plus the loop played through twice.

That fallback's `second period replays N%` column is a *consistency* check, not evidence: a frame
is the register shadow, and the shadow is inside the state the rule hashed, so a musical repeat
implies a frame repeat. It is there to catch the frame/state alignment being off by one, and reads
100% for all thirteen.

**What is checked, every run** — the tool exits non-zero on any of these, and every check that
can be made off the register stream runs *before* a byte is written. `manifest.tsv` is written last
of all, so its presence is what marks `out/audio/` a finished dump:

- the index's length is *derived*, not typed: `tune_index` `$17058` runs up to `mod_table_data`
  `$170b2`, so 45 is arithmetic on two `include/sound.h` addresses — cross-checked against the
  sign-extension boundary `test_sound.py` pins (entry 45's word is the first with bit 15 set);
- **the exact case `test_sound.py::test_music_frames` verifies** — `sound_start` then 32 ticks, no
  reset — captured tick by tick produces a PSG ledger identical to the one that battery gets from a
  single chained oracle run, all 352 accesses in order. That is the tie between this dump and the
  differential-verified player: the capture's own driving does not change what the driver writes.
  (The reset a capture does first is deliberately outside that sequence — the original ends
  `moveq #$d,d0` / `dbf d0`, so chaining it would hand `sound_start` a D0 of `$ffff`. Its 14-access
  flush, the one `test_reset_psg` verifies, is asserted where it happens instead);
- every tick flushes registers **10..0 in that order** — not merely eleven of them; a flush the
  other way round leaves an identical register file and only the ledger can see it;
- register 13 (the envelope shape) is never written, and the shape the reset leaves — read out of
  the shipped register shadow, not typed — is a **one-shot** (`0x00`), so an envelope-mode volume
  really is silence rather than a buzz;
- **not one chip read is served** — so nothing in these dumps rests on the capture mode's
  fabricated answers;
- the register-stream silence verdict and the rendered `.wav`'s peak agree on all 27 rendered;
- the boot tune arms all three voices, loops, and plays a melody rather than a held note — it uses
  571 distinct tone periods against a bar of 32;
- one number is re-captured after the whole sweep and must be byte-identical, which is what would
  catch driver state leaking between numbers.

**The renderer is BuggyBoy's** ([`recreate/sound/ym2149.py`](../buggyboy/recreate/sound/ym2149.py)),
imported rather than copied. Three things about it matter here, and all three were settled by the
recording below rather than by argument:

- **it renders on the chip's scale, not each file's own peak.** 0 dBFS is three channels at volume
  15, so nothing clips by construction and the `.wav` levels are comparable *between* numbers —
  the title tune peaks at −1.6 dBFS and the 2.3 s piece `0x24` at −34.7, which is how far apart
  they really are (one voice at volume 8 against three at 15). `manifest.tsv` carries the column.
- **it is band-limited** (8× oversampled, then each output sample is the mean of its interval, the
  way the machine's analog stage integrates). Zynaps writes tone periods of 0 and 1 often — 2,268
  channel-frames of the title tune's 13,121 — and the chip reads those as a 125 kHz square, which is
  inaudible on the machine and folds back into the audio band at full amplitude in a renderer that
  samples straight at 44100 Hz. Effects `0x25` and `0x26` are period 0 for every one of their 55
  frames.
- **it is AC-coupled** (a moving-mean high-pass, corner ~20 Hz), because the machine's audio output
  is. Subtracting one mean for the whole track is not the same thing: the DC a unipolar square
  carries *moves with the volume register*, so a tremolo left a full-depth sub-audio staircase —
  measured at 20% of the title tune's whole energy below 50 Hz, against 8% in the recording.

Two Zynaps quirks it is handed: the driver never rewrites register 13, so the envelope generator
reads as long completed; and it adds a biased delta to its volume byte **without masking**, so a
volume register really does reach values with bit 4 set — "use the envelope" — which on hardware is
silence, and is counted as such. That second claim now rests on a number rather than on reasoning:
the register shadow the binary ships carries envelope shape `0x00`, a one-shot, and a Hatari trace
of a real boot shows registers 11–13 written by nothing but `sound_reset_psg` and always as 0.

### Judged against the real game

`extract_audio.py` cannot judge itself: it drives the original replayer under our oracle and renders
the result with our synth, so a fault in either half comes out as a plausible `.wav`.
[`tools/ref_capture.py`](tools/ref_capture.py) boots the actual game in Hatari — plain ST, RGB
monitor, so 50 Hz, which is the machine's own PAL VBL since the game never writes `$ffff820a` — and
records two spans, the title screen and a level-1 game with the fire button poked so the ship
shoots. [`tools/compare_audio.py`](tools/compare_audio.py) reads them back:

```bash
projects/zynaps/recreate/.venv/bin/python projects/zynaps/tools/ref_capture.py    # ~2 min
projects/zynaps/recreate/.venv/bin/python projects/zynaps/tools/compare_audio.py
```

Two surfaces, because they fail differently. **`ref_<span>.regs`** is the register file the game's
own tick flushed each frame, read out of Hatari's `psg_write` trace — it can see a *capture* fault
and nothing else. **`ref_<span>.wav`** is Hatari's audio — it can see a *renderer* fault and nothing
else.

- **The capture is exact.** All 1,000 compared frames of the title recording replay `snd_11.ym`
  register for register (from its frame 1818), on every one of the eleven registers the tick
  flushes. The mixer's top two bits are masked on both sides: `note_on` ORs the I/O-port *direction*
  bits into register 7, the chip takes them, and the `.ym` drops them because YM5/YM6 read that
  register's spare bits as special-effect codes. Ten sounds were located the same way in the
  level-1 recording, matched on their own voice's registers — four of them music, two of them parts
  with no `.wav` to listen to.
- **The renderer, before and after.** Judged by an *alignment-free* agreement between the two
  average spectra (0..1), which is the honest metric here — a dominant-pitch track is too unstable
  on three simultaneous square waves to align, and scored against the recording's own registers the
  loudest partial is the sounding fundamental in only 41% of frames, so that is the ceiling of any
  per-frame pitch figure:

  | | before | after |
  |---|---:|---:|
  | title tune (`0x0b`, 20 s of the title screen) | 0.906 | **0.978** |
  | `0x0b` again, under level-1 play | 0.912 | **0.953** |
  | `0x27` (3.6 s, three voices) | 0.182 | **0.594** |
  | `0x14` (3.8 s, two voices) | 0.330 | **0.669** |
  | `0x0e` (24 s, one voice) | 0.535 | **0.563** |
  | `0x12` (2.3 s) | 0.696 | 0.689 |
  | `0x22` (2.3 s) | 0.731 | 0.718 |
  | `0x2c` (0.9 s) | 0.597 | 0.584 |

  Only the title figure is a clean score. The level-1 ones are a **floor**: Zynaps plays music under
  the level, so the recording carries the other two voices while an effect sounds and a one-voice
  dump is being compared against a mix — which is why the three-voice `0x27` moves most and the
  short one-voice effects barely move at all. The per-frame pitch column moved from 17% to 16% on
  the title tune, i.e. not at all, which is the metric's ceiling showing rather than the render's.

**What this does not prove.** Hatari's YM2149 is a model too — better and far more scrutinised than
ours, but a model. An agreement number is "two independent implementations agree", not "this is the
chip". The register surface is the stronger of the two: those bytes are the game's, and Hatari only
carried them.

## Secrets and dead code

A hunt through the finished reconstruction for what the game *has* but does not use: hidden inputs,
dormant flags, code with no caller, data with no consumer. Every positive claim below was either
**demonstrated on the original binary** in Hatari — never on the recreate — or is a static fact with
its address given. Negative results are reported as plainly as positive ones, because a hunt that
only reports what it found is not evidence about what is there.

The driver is [`tools/secrets_demo.py`](tools/secrets_demo.py), which boots the faithful `.stx`
through `boot_shots.py`'s own two anchors (the PRG appearing in RAM, then the PREPARE-FOR-COMBAT
gate being crossed), does **one** thing, and photographs and dumps the consequence into
`out/secrets/` beside a `result_<experiment>.json`.
[`tools/patroller_tracks.py`](tools/patroller_tracks.py) and
[`tools/globals_census.py`](tools/globals_census.py) read those records back.

**Each experiment carries the verdict it had to reach**, and the driver's **exit status** is that
verdict and not merely "Hatari did not crash" — a pause that failed to freeze, a control run whose
ship survived, a patroller run that never saw its actor type, each exits non-zero. That is the
surface a future Hatari or TOS change would trip; without it the whole battery would come back green
with the failure buried in a JSON file nobody re-reads, which is exactly how the wrong SPACE claim
survived.

**`out/` is gitignored**, so the captures and the `result_*.json` are not in the repository; the
commands below regenerate them. **The static sweeps are not so lucky.** Ten one-off scripts wrote the
sound, file, script-opcode and actor-type verdicts — `sound_{scan_callsites,reachability,
orphan_profile}.py`, `files_{load_census,render_unused}.py`, `data_{walk_scripts,script_ops,
actor_types,formations}.py` and their shared `data_zynlib.py` — and they live in `out/secrets/` with
their output. **Those four rows are therefore reproducible only from the addresses and procedures
written out below, not by running anything**, until someone judges a sweep worth promoting to
`tools/`. Every claim in them names the address and the decode it rests on, which is what makes them
checkable by hand; that is a weaker guarantee than the three demonstrations, and it is stated here
rather than glossed.

```bash
projects/zynaps/recreate/.venv/bin/python projects/zynaps/tools/secrets_demo.py pause
projects/zynaps/recreate/.venv/bin/python projects/zynaps/tools/secrets_demo.py all   # ~25 min
```

| lead | verdict |
|---|---|
| input-driven secrets | **NOTHING undocumented** — the only in-game key is the manual's own pause on `SPACE`, verified live; no cheat key exists |
| a dormant invulnerability flag | **CONFIRMED-LIVE** — `$19912`, read three times, written by nothing |
| the unreachable power-up arm `$13ede` | **NOTHING** — a two-instruction stub, not a lost weapon |
| the dead sine patroller `$148ca` | **DEAD-BUT-INTERESTING** — a cut enemy, and the game still clears its state array |
| the actor script VM's dead arms | **DEAD-BUT-INTERESTING** — a complete homing feature no script names |
| sound streams nothing can start | **DEAD-BUT-INTERESTING** — nine finished effects |
| data files nothing opens | **DEAD-BUT-INTERESTING** — three of the game's, one finished sprite art |
| unreachable enemy *types* | **NOTHING** — every type with a handler is spawned |
| unreferenced text, author tags, build dates | **NOTHING** — every message is drawn; there is no hidden text |
| the protected tracks 77–79 | **NOTHING NEW** — byte-exact clones of tracks 76, 73 and 72 |

### The manual's pause — `SPACE`, exercised at last

`$10fda`, inside the **frame-loop head** (`frame_panel_scroll_and_ship_stage` `$10f4e`):

```
010fda  cmpi.b  #$39,key_scancode      ; SPACE?
010fe2  bne.w   $11010                 ; no -> get on with the frame
010fe6  tst.b   key_scancode / bne.s   ; wait for the release
010fee  move.b  #8,palette_swap_countdown
010ff6  move.b  #8,palette_rotate_countdown
010ffe  cmpi.b  #$39,key_scancode / bne.s $10fee    ; ...spin here until SPACE again
011008  tst.b   key_scancode / bne.s   ; and wait for ITS release
```

Press SPACE in the level and the frame loop stops dead; press it again and it carries on. The spin's
*body* rewrites both palette-cycle counters, so the palette animation is held as well as the frame,
and no buffer flip happens inside it, so the screen freezes exactly as it stood.

**Demonstrated.** `secrets_demo.py pause` photographs the level running, presses SPACE through
Hatari's real keyboard event (so the byte arrives the way the game's own ACIA handler files it),
photographs twice 2.5 s apart, presses SPACE again and photographs twice more. It was run **five
times, two cycles each**, and all ten cycles agreed: the pair before is two different pictures, the
pair while paused is **byte-identical** (and not blank — the capture's colour count is recorded
beside the verdict, because two photographs of a blanked screen would be identical too), both
countdowns read **8**, the pause loop's own constant, and the pair after differs again.

Each run **overwrites** `result_pause.json` and the twelve `pause_r*_[1-6]_*.png`, so what is on disk
is the most recent boot, not all five. The repetition is a claim about runs, not about files.

**Nothing here is new to the game — the pause is in the manual.** `names.txt` has described the
mechanism since the naming wave (`cmt 0x10fda`, "PAUSE: scancode $39 (space) pauses…"), and
`frame_pause_if_space` in `recreate/src/frame.c` reconstructs it with the differential driving all
three spins. What the hunt added is workspace-internal only: nobody in this project had exercised
the key, and three prose surfaces — this README, `play.sh` and `boot_shots.py` — said SPACE did
something else (all corrected). Running it is also what closes the key-reader census: with the
documented pause accounted for, no undocumented input remains.

### A dormant invulnerability flag — `ship_invulnerable` `$19912`

**Read by three instructions and written by none.** All three reads are the same shape:

| site | what it guards |
|---|---|
| `$11e66` | the ship's first record flying into the landscape |
| `$11eb2` | the ship's second (shadow) record doing the same |
| `$13d0e` | the ship touching a lethal entity — enemy, ground target or shot |

```
011e66  tst.b   ship_invulnerable
011e6c  bne.w   $11ed4                 ; nonzero -> skip the death entirely
011e70  bset    #0,death_event_flags
011e78  move.w  #1,d2
011e7c  bsr.w   explosion_spawn
```

Those are the only player-death sites: `explosion_spawn` `$15510` has four callers and the fourth
(`$11f74`) is the **boss** exploding, with `d2 = 0`. A life is deducted at `$1277a`, and only when a
player explosion animation reaches its last frame. So a nonzero byte here is **complete
invulnerability**, to terrain and to everything else.

**Nothing writes it.** A read/write census of every absolute-long operand in the sweep
([`tools/globals_census.py`](tools/globals_census.py) → `out/secrets/globals_rw_census.tsv`) finds three reads and zero
writes, and no `lea` takes its address. Nor does anything reach it indirectly. Only two `lea` bases
in the whole image sit below it and near enough to matter, and both are dismissed by their own
index:

- `$198d6` is the **read-only** character-to-glyph map, and its one reader indexes it by
  `char - $20` over a `$21`-byte table.
- `$198bb` is `squadron_kill_counters`, and it *is* written through an index —
  `subi.b #1,idx(a6)` at `$1490c`, `$14962` and `$14a64`, from record byte `+0x21`. But every writer
  of `+0x21` sets it from a **six-iteration** free-slot scan of that same array (`$138b0`, `$1397c`,
  `$13a36`) or from a flag of 0 or 1 (`$13b98`), so the byte holds 0..5 and the decrement lands in
  `$198bb`..`$198c0`. Reaching `$19912` would take an id of `$57`.

Its immediate neighbours `$19911` and `$19913` are written by direct absolute moves, so nothing in
the region is array-addressed either. It lives in bss, so GEMDOS zeroes it at load and it reads 0
for the life of the process — which the `probe` run confirms by sampling it, 0 every time.

**Demonstrated, as a single-variable experiment on the original.** An unattended ship on level 1 is
shot down fast, so the game's own enemies are the test and the flag is the only thing touched:

| run | poke | lives over 70 s | `death_event_flags` |
|---|---|---|---|
| `probe` | none | 3 → 2 → 1 → **0** within ~22 s | set |
| `invuln-off`, three times | none | 3 → 2 → 1 → **0** within ~22 s, every time | set |
| `invuln-on`, three times | `$19912 = 1` at the gate | **3, 3, 3 … 3** for all 14 samples | **never set** |

The final captures say the same thing without a number: `invuln_off_2_end.png` is **GAME OVER
PLAYER 1 / YOU ARE NOT RATED** over the status panel, while `invuln_on_2_end.png` is the ship still
flying, deeper into the level, with thousands of points on the panel that the control never lived
long enough to score. (These, too, are overwritten by each run; the score differs from run to run,
the two outcomes do not.)

`result_invuln-{on,off}.json`, and the recipe is one byte: `w b $<load base + $9912> $1` at the
Hatari debugger, where the load base is where GEMDOS put the PRG. Poking it *later* than the gate is
worth knowing about: a first attempt that waited four seconds lost one life anyway, because a death
was already *in flight* — the life comes off when the explosion animation ends, not when the ship is
hit.

**What it is** is not established. It has the exact shape of a debug switch left in — a byte the
developer poked from a monitor — but nothing in the image, on the disk, or in the strings names it,
and no input path reaches it. What would establish it: a build of the game with a writer, which we
do not have. **It is a poke cheat in the shipped binary either way**, and the recipe is one byte.

### The cut enemy, and the array the game still clears for it

`$148ca` is an actor move handler of the ordinary shape — `a2` = the record, `d6` = the slot index
`enemies_move_all` counts — that **nothing anywhere references**. It reads and writes a per-slot
direction byte at `slot_dir_flags` `$19673 + d6`: with the flag clear it steps x down by 2 until
x ≤ `$c8`, then *sets* the flag; with it set it steps x up by 2 until x ≥ `$190`, where it despawns.
Every frame it also writes `y = base + sin(phase, amplitude $32)`, the phase stepping 6 per frame.
So: **sweep in from the right, turn round at x = 200, fly back out.** Against
`enemy_move_type14_sine` `$1494a`, which is the same routine with amplitude 6, phase step `$14`, x
stepping 4, and no turn.

**What makes it more than a leftover is `$19673`.** That 13-byte array — `$19673`..`$1967f`, ending
exactly at `ikbd_joystick_state` — has **exactly two references in the whole image**:
`section_start_tail` clears all thirteen of it at `$10da6` on every section start, and the dead
handler is the only code that ever reads or writes one. *The shipped game still resets a state array
whose sole consumer was cut.* That dates the cut after the array and its reset were already wired in.

**Demonstrated.** `secrets_demo.py patroller-on` points one entry of `actor_move_table` at `$148ca`
and changes nothing else, then samples every live actor's slot, type and x twice a second. Which
type the handler was *written* for is not recoverable — no table entry survives — so the run borrows
the slot of type `$16`, the wave enemy `spawn_formation` puts on screen continuously in every
section. (Type `$0e`, the opcode-`0b` trio, appeared in none of 120 samples of an earlier run.)
Both runs also poke the invulnerability flag, which is not the variable: without it neither run
stays in one section long enough for a wave to cross.

The unit that means anything is one *actor's* flight — a maximal run of consecutive samples in which
one slot holds a live record of the type — because a whole sample mixes actors that spawned at
different moments. `tools/patroller_tracks.py` cuts the JSON that way and scores each track for
a turn (x falls to a floor, then climbs more than one sample's 50 px of travel back past it):

| | tracks of 4+ samples | of which turn | floor of the turning ones |
|---|---|---|---|
| `patroller-off` (the shipped handler) | 36 | **3** | 179 |
| `patroller-on` (`$148ca`) | 33 | **33** | **200..216** |

```
patroller-off  slot 7:  351 312 282 255 207 153  99
patroller-on   slot 3:  374 336 300 262 226 212 250 286 324 360 398
```

Every track turns under the dead handler and a twelfth of them do under the shipped one — and the two
populations do not overlap. The dead handler's floors are 200..216, never below 200, which is its own
`cmp.w #$c8` seen through the sampling rate: 25 frames pass between samples and x moves 2 px a frame,
so a sample lands on or just after the turn rather than on it. The control's three turns all floor at
**179**, outside that band, and they are not a counter-example: type `$16`'s shipped handler is the
**script VM**, and the script's class-5 heading op can turn an actor round. What no shipped script
does is turn *every* actor, at the handler's own x.

Type `$14`, whose table slot was **not** touched, keeps its ordinary flight in the same run, which
pins the effect to the dispatch rather than to anything global.

There is no matching dead *art*: every `.DAT` sprite file the PRG names is consumed by a type that
is spawned. The unused art is one the PRG does not name at all — see below.

### A whole homing feature in the actor script VM that no script uses

The actor script VM (`actor_script_run` `$14c66`) dispatches an opcode's low three bits through
`script_op_table` `$19438`, and class 7 again through `script_op_ext_table` `$19458`. The shipped
scripts — `$19ac2`..`$19b85`, `0xc3` = 195 bytes, 18 scripts, of which **119 have bit 7 clear**, and a
linear scan is exact because a byte with bit 7 set is a delay and one without *is* the opcode — use
classes {0,1,3,5,7} and ext ops
{0,1,3,4,5,7,9,11,15}. Five arms are **real code no script names**:

| arm | address | what its instructions do |
|---|---|---|
| class 2 | `$14d00` | write `(op & 0x78) >> 3` into **both** `+0x1b` and `+0x1c`, set carry, `rts` |
| class 4 | `$14d88` | `+0x1a = $11`, `+0x1f = (op & 0x78) >> 3`, then `bsr entity_steer_toward_target` |
| ext 2 | `$14de2` | pick a **random heading**, apply it and move |
| ext 6 | `$14e50` | step x left by 2 *unconditionally* — ext 0 is the same step, but frozen while the scroll is |
| ext 8 | `$141d6` | the steering tick itself: turn toward the target by at most `+0x1f` every `+0x1c` frames |

**Class 4 is the one that carries the reading.** `+0x1a` is the entity index a steered shot chases,
`$11` is 17, and entity 17 is **the player's ship record**; `+0x1f` is the maximum turn per tick; and
it then calls the steering routine. Set a target of the player, cap the turn rate, steer — for an
*actor*, which is what the script VM drives. Class 2 fills the countdown/period pair that steering
then consumes, and ext 8 is the tick. Together they are a homing-enemy feature the game has and never
asks for.

**Two caveats, because the repo does not speak with one voice here.** `recreate/STATUS.md` names
`$14d00` `actor_script_op_set_fire_rate` and `$14d88` `actor_script_op_fire`, and `names.txt` records
`+0x1b`/`+0x1c` as *both* a fire countdown and reload (for script class 2) *and* a turn countdown and
period (for a steered shot) — the fields are a union it already flags. So: class 2's pair is **not
decided by its own body**, which writes one value into two bytes and returns. Class 4's is, by the
`bsr` and the target index. Read the table above as the instructions, and the paragraph above it as
the inference.

The code is not orphaned in general — the steering tick `$141d6` has five callers, four of them live
(`$11bd0`, `$11bf2`, `$140ec`, `$1415e`, for the enemy seeker and the player's own homing shots) and
the fifth the dead class-4 arm at `$14d98`. What no shipped script does is *name* it: not one of the
119 bit-7-clear script bytes has `(op & 7)` of 2 or 4, or is `$17`, `$37` or `$47` (ext 2, 6 and
8) — a superset check that holds whatever the parse phase, since only a bit-7-clear byte can be an
opcode at all. So the game can make a *shot* home, and its scripts never ask an *enemy* to.

The reported-unused arms that turn out to be nothing: class 6 and ext 10, 12, 13 and 14 are all
**genuine zero entries** (checked against the relocation table, so they are not unrelocated
pointers). `jsr (a0)` with `a0 = 0` is a crash, not a feature, and no opcode reaches them.

`spawn_formation` `$14a7c` has two decoded features no shipped formation uses, both confirmed by
enumerating all 18 reachable records: a **byte-3 "kind"** field, taken when byte 1 has bit 7 set —
every record's byte 1 is `$00`..`$11` — and a **`0xff` random-y**, which would replace `base_y + dy`
with `(rand16 & 0x7f) + $28` per actor; no y byte in any record is `$ff`.

### Nine sounds nothing can start

Every one of the 23 instructions that reaches `sound_start` `$16ac8` is a `bsr.w`; 22 carry a literal
`moveq #n,d1` immediately before (no table, no global, no inherited `d1`) and the 23rd is the
interpreter's own spawn at `$16c6a`. Closing that seed set under the streams' own `$fc`/`$fd`/`$fe`
spawns and `$e5` jumps — including the single `$ec` at `$17295`, which swaps `tune_index[0]` and
`[1]` and so makes stream 0 reachable — reaches **36 of the 45**.

The nine left over are **19, 23, 25, 29, 35, 37, 38, 42 and 43**, and they are not headerless parts:
each opens with its own `fa <chan>`, each ends itself with `$e1`, and each already has a `.wav` in
[`out/audio/`](out/audio). Two structural signatures say they are a bank only partly wired up:
channel code **3** occurs on exactly three streams (23, 25, 35) and all three are orphans, while 29
is 44 — the game's busiest effect — with one note changed, and 42/43 shadow 37/38 (43 differs from 38
in its pitch and noise tables; 42 has the *same* three tables as 37 and differs only in noise period
and note).
`out/secrets/sound_orphans.txt` has each one's register profile.

This corrects the earlier census, which was a byte-level scan for `moveq #n,d1; bsr sound_start`
and knew nothing about the spawn graph. It also corrects the spawn list above: **30 spawns 31** as
well as 32 and 33, and **36 is spawned by both 14 and 39**.

### Files on the disk that no load site opens

The filename table at `$19686` holds 31 lowercase strings, which six patch sites (the alien, mother
and missile letter/digit tables and the map-letter table) turn into 60 names. **Four** of the disk's
62 files are named by none of them — and one of the four is `DESKTOP.INF`, TOS's own desktop
configuration rather than the game's, which leaves three of the game's:

- **`ROTBALLS.DAT`, 360 B — finished art for something cut.** Four frames of a rotating pair of
  chrome-blue spheres, in exactly the masked 16×9 geometry and byte count of the `MISSILE1-3.DAT`
  the game *does* load: a drop-in fourth sprite set.
- **`CHARS2.DAT`, 1,600 B — the superseded font.** `EXTCHARS.DAT` with four glyphs (I, J, S, T) one
  pixel over and the eight key-caption glyphs missing.
- **`SMSHIP.DAT`, 32 B — unidentified.** It renders as noise under both layouts 32 bytes admit, and
  since nothing loads it, no code pins its format; "unidentified" is the honest answer.

Renders are in `out/secrets/files_unused_*.png` and `data_unref_ROTBALLS.png`. No file has trailing
data the loader does not reach — the reverse is routine: **nineteen** are deliberately over-asked and
`Fread` returns short (all twelve `LEV*.MAP`, the three `ZYN*.DAT`, `ALIENH`, `LIFEGRA`, `MOTHER6`
and `MOTHER7`).

Beside them, a **dead load**: `$1009e` stages `lev1.map` into the map buffer `$478ae` with a 14,400-
byte cap and never calls the loader — `$100b0` overwrites `a0`, `a1` and `d1` with `myship.dat`'s
arguments and only that load reaches the `bsr $144e8` at `$100c2`. Not a branch that is skipped; a
fall-through with no call in it.

### The rest of the dead code, and what it is worth

- **`powerup_slot1_activate` `$13ede` — not a lost weapon.** Two instructions: refill the weapon HUD
  timer and `rts`. It is the shared prologue of the bomb, seeker and missile arms with the weapon
  change taken out. Unreachable because `$13dfe` diverts a cursor of 1 to the upgrade arm first.
- **Both power-up jump tables' entry 0** — also unreachable, and previously unrecorded. `$13da8`
  sends a cursor of 0 to the ship-speed arm before either table is indexed, and the upgrade table's
  index can only equal a cursor that is not 0. Both entry 0s are `$148c8`, the bare `rts`, so
  nothing is lost. (The upgrade table also holds `powerup_upgrade_shield` in three of its five
  slots, so it has three destinations, not five.)
- **`$119ba`..`$119d8`** — eleven instructions past an unconditional `bra`: an **inline enemy-shot
  spawn**, superseded by the `bsr spawn_enemy_shot` two instructions above it. It writes `+0x10`,
  the position pair from A1, the alive byte, and `d2 & 0x7ff` into `+0x1a` — and no type byte.
- **`sound_install_timer_a_dead` `$16aa6`** would `Xbtimer(Timer A, ctrl 7, data $f4, vec
  sound_tick)`. Control 7 is ÷200 of the MFP's 2.4576 MHz and `$f4` is 244, so the tick would run at
  12288/244 = **50.36 Hz** — the PAL VBL rate. It is not a fast mode or a slow one; it is the sound
  tick **decoupled from the display**. It is also the image's only XBIOS trap. *Read, not
  demonstrated*: installing it on top of the four live VBL `bsr sound_tick` sites would double-tick
  the driver, so a demonstration has to replace those, not just add this.
- **`$113b4`** — the ship's right-hand clamp; both branches jump past it.
- **`game_over_screen`'s palette restore** — dead because the not-rated arm pops a return address
  the rated arm pushed. Already in `recreate/STATUS.md`.

### The protected tracks hold nothing new

Cylinders 77, 78 and 79 — the ones whose sectors claim tracks 76, 73 and 72 — had never had their
*contents* looked at. All 30 sectors read clean out of `zynaps.stx`: FDC status `$00`, valid ID and
data CRCs, **zero fuzzy bits**, track flags identical to the 77 unprotected tracks. And each cylinder
is a **byte-exact whole-track clone of the track its address fields name** — 0 differing bytes in all
three cases — carrying the *source* track's sector skew rather than its own, which is what a
whole-track image copy leaves and a sector-by-sector one does not.

A stepping artifact is ruled out, but it takes two arguments, not one. For 78→73 and 79→72 the
distance does it: a mis-step reproduces a *neighbour*, and those are five and seven cylinders lower,
which a monotone 0→79 read (`--seek-retries 0`) never revisits. **77→76 is a neighbour**, so for that
pair the distance argument says nothing and two measurements have to. First, **angular position**:
first-sector `bitpos` falls smoothly with the *physical* cylinder across the whole disk (406 at 0 →
374 at 76 → 358/361/362 at 77/78/79), and each clone continues the physical trend instead of
reproducing its source's value — a re-read of the same track would do the opposite. Second,
**independent flux captures**: 223,012 against 223,024 transitions for 76 and 77, 231,385 against
231,415 for 73 and 78, 228,965 against 228,895 for 72 and 79 — within 0.03%, as identical data must
be, and never equal, as two surfaces must not be. What the
sectors hold is therefore already on the disk, *as a copy of it*: the filesystem still places every
byte of every file on cylinders 0–73, and these three tracks are duplicates of three of those. Read
as images, 12 of the 30 reproduce the live `ZYNLOGO.DAT`, 16 reproduce free-space residue of
`ZYNPIC.PIC`, 2 the tail of an older `ZYNAPS17.PRG` — byte-identical to the shipped one — and zeros.
The Protection section's "cylinders 74–79 are entirely free space, nothing the game loads is there"
therefore still holds: nothing is *addressed* there, and what is *recorded* there is a second copy.
Rendered with the game's own `palette_boot`, cylinder 77 reproduces
scanlines 83–114 of the title screen exactly. **The `.st`'s 30-sector hole loses nothing.**

*Why* the clones exist is not established: a deliberate anti-copy format and a duplicator-buffer
artifact are both consistent with everything measured, and nothing here separates them.

The boot sector accounts for all 512 bytes: 493 zero, and every non-zero byte a BPB field except
`$0fe`..`$0ff` = `ff ff`, which is unexplained (clearing it gives checksum `$76bf`, still not
`$1234`, so it is not a botched boot-checksum fix). There is **no format-tool signature** — the BRA
is `00 00`, the OEM name six spaces, the serial `00 00 00` — where every other ST disk in this
workspace carries one; and FAT entries 0 and 1 are `000`/`000` where a formatter writes the media
byte and `fff`. The two FATs are byte-identical. Plausible but unproven: the filesystem was
synthesised numerically by the mastering tool rather than formatted by TOS.

One deleted directory entry survives, `?YNPIC.PIC` at image offset `$15e0`, stamped three minutes
before the live copy; its data is recoverable from free space and is byte-identical to the shipped
`ZYNPIC.PIC`. Free space also holds an older `ZYNAPS17.PRG`, byte-identical to the shipped build.
**Nothing new is recoverable from the disk.**

### The negative results

These matter as much as the findings, and each is a sweep that came back empty:

- **There is no cheat key and no hidden message.** The only scancode comparisons in the whole image
  are `$39` (the pause, twice), `$02` and `$03` (the menu's 1 and 2 players) and the name-entry
  dispatch at `$13124`. The game's text is plain ASCII — `draw_char` `$13710` maps a character ≥ `$41`
  to glyph `char - $37` and anything below through the byte table at `$198d6` — so a plain `strings`
  does find every message. All **21** text records are drawn, every draw site is a direct
  `lea` or resolves to one (there is no indexed draw anywhere, so reachability is exact), and **none is
  orphaned**. Twenty of the 21 sites are a direct `lea $addr.l,a6`; the twenty-first (`$131a0`, the
name being typed) is `movea.l a5,a6`, and A5 traces to the literal `lea $19d48.l,a5` at `$12ff4` — so
the enumeration is still exact, but by one extra step rather than by inspection. No build date, no
version string, no compiler banner, no dev message. The `ZXCVBNM` run
  at `$19a39` is not a key table in the QWERTY sense: it is a **scancode → ASCII map**, indexed by
  the IKBD make code and read at exactly one site, the name-entry dispatch.
- **No enemy type is implemented and unspawned.** Every one of the six live `actor_move_table` entries
  and all nine live `actor_anim_table` entries is reached by shipped data. Types `$17`..`$31` — the
  band where the move pass falls into the animation table and then into the script-op table — cannot
  be produced by any shipped path at all; the highest type the data writes is `$16`. That is a
  dispatch boundary, not a secret. (Type `$15` sits between `$14` and `$16` in four type bitmaps with
  no handler, no art and no spawner anywhere — a vestige, and no more than that.)
- **The default high-score table** at `$19d5a` reads HOWIE 100000, **METTY** 80000, **MARK** 50000,
  **JOHN** 30000, PETE 10000. HOWIE and PETE are the credited coder and artist; the other three
  appear nowhere else in the image. Plausibly the rest of Microwish — unestablished.

### What the recreate says

Nothing here changes a verified fact, and no reconstructed code was touched. The pause is already
`frame_pause_if_space` in `src/frame.c`; `$13ede` and all five script-VM arms already have verified
rows;
`$148ca`, `$16aa6` and `$119ba` are already recorded as deliberately unported. **No cheat turned out
to live in a kit-modelled path**, so nothing was modelled away.

Two things `recreate/STATUS.md` does not yet say, and could. All five script-VM arms above
(`$14d00`, `$14d88`, `$14de2`, `$14e50`, `$141d6`) already have **verified rows** there — what it has
no entry for is that five of them are **unreachable from the shipped scripts**, which is the kind of
fact its reachability notes elsewhere do record. The same for both power-up jump tables' entry 0,
unreachable for the reason entry 1 is. Neither was written here: this hunt changed no reconstructed
code, and a ledger row is the porting session's to add.

Proposed `names.txt` lines for all of the above are in `out/names_secrets.txt` — gitignored with the
rest of `out/`, so they are a hand-off for the next naming pass rather than a committed artifact.
`names.txt` itself is untouched.

## Layout and next steps

- [`bin/`](bin) — `ZYNAPS17.PRG`, the patched `zynaps.st`, and `disk/` (the extracted tree).
- [`out/`](out) — `prg_dis.txt` (linear sweep), `boot/` (boot screenshots), `assets/` (rendered
  art), `audio/` (every stream as `.ym`, every playable one also as `.wav`, plus the `ref_*`
  recordings of the real game).
- [`tools/`](tools) — `boot_shots.py` (headless Hatari driver), `dat2png.py` (asset decoder),
  `extract_audio.py` (the sound dump above), `ref_capture.py` (record the real game's audio and
  register stream), `compare_audio.py` (judge the dumps against that recording), `make_bin.sh`
  (regenerate `bin/` from the gold master), and the three the secrets hunt added —
  `secrets_demo.py` (demonstrate a secret on the original in Hatari), `patroller_tracks.py` and
  `globals_census.py` (read its records back). The game-agnostic halves live in
  [`tools/hatari_headless.py`](../../tools/hatari_headless.py),
  [`tools/st_pixels.py`](../../tools/st_pixels.py), [`tools/st_extract.py`](../../tools/st_extract.py)
  and [`tools/stx_extract.py`](../../tools/stx_extract.py).
- [`play.sh`](play.sh) — boot the game. `run.sh`/`reapply.sh` are the Ghidra bootstrap and
  re-apply, and `names.txt` is the name map (see the workspace [`CLAUDE.md`](../../CLAUDE.md)).
- [`gen_readme_assets.py`](gen_readme_assets.py) — the eleven pictures in the workspace
  [`README.md`](../../README.md)'s Zynaps gallery, rendered **by the reconstruction** rather than
  screenshotted from the original: it drives the boot chain, the attract loop, the section chain and
  `frame_loop_once` through the same ctypes entry points `recreate/test/` drives, reads the sixteen
  pens back out of the kit's hardware-write ledger, and writes the tracked
  [`assets/zynaps/`](../../assets/zynaps). It renders the set twice and refuses a picture whose two
  renderings differ. Needs `bin/` and a `make test` build (the harness dlopens `liboracle.so` at
  import); nothing here RUNS the oracle, and no Hatari or TOS ROM is involved.
- [`recreate/`](recreate) — the differential reconstruction against the Musashi oracle;
  [`recreate/README.md`](recreate/README.md) is the binding and
  [`recreate/STATUS.md`](recreate/STATUS.md) the per-function ledger.

### Open

- `POWER.DAT`'s meaning (geometry is solid, content is not identifiable), the `MOTHER6/7` frame
  split, and `SMSHIP`/`LIFEGRA` at 8 px wide — all recorded as *guessed* above.
- In-game **steering** was never exercised headless: the joystick byte `$9681` is still only poked,
  and the IKBD-to-`$9681` delivery below it stays unproven either way. The **keyboard** half is no
  longer unproven — the pause demonstration above drives a real Hatari key event all the way through
  the ACIA handler to `$9685` and back out as a frozen frame.
- Why `ship_invulnerable` `$19912` exists, and why `$0fe`..`$0ff` of the boot sector reads `ff ff`.
- Whether cylinders 77–79 are a deliberate anti-copy format or a duplicator artifact — both remain
  consistent with every measurement.
