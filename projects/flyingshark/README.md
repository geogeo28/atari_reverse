# Flying Shark (Atari ST, Firebird 1988 — Gamex hard-disk release)

Taito's vertically-scrolling shooter, converted for the ST by **Prime Software & Images Design**
(the payload says so in its first 48 bytes). The copy in `bin/` is not the floppy release: it is
"PP"'s 2012/2018 **Gamex hard-disk install**, in which the game is a Gamex-LZ stream hidden in the
DATA of a stub whose TEXT hooks `trap #1` and serves the game's file opens out of one 600 KB blob.
Step 0 of this project was getting the real program out of that and proving it still runs: it does —
`bin/FLYSHARK.PRG` boots to its title screen under plain TOS 1.04 with the whole Gamex runtime
thrown away. The anatomy, the stub's GEMDOS implementation, and everything the reference run showed
are in [`notes/loader.md`](notes/loader.md).

## Files (`bin/`)

| File | Size | What it is |
|---|---:|---|
| `FILES/FSLA` | 24,790 | **stub + the packed game.** TEXT `0x698` is the wrapper; DATA is a Gamex-LZ stream at `0x6d4` |
| `FILES/FRD` | 600,440 | **the game's data**, 21 files concatenated; the stub's directory holds the offsets |
| `FILES/D15RU.FIC` | 65,943 | Gamex-LZ packed mini-OS the loader installs — wrapper |
| `RUNME.TOS` | 3,566 | Gamex-LZ packed loader — wrapper |
| `FFS273.HST`, `LFS273.HST`, `HAGA`, `FS240R.BMP` | | Gamex runtime, hardware-detect data, cover scan — wrapper |
| `README.TXT`, `LOG.TXT` | | the release's own notes, by "PP" |

`tools/unpack_dist.py` writes, alongside them: **`FLYSHARK.PRG`** — the game, 50,358 B,
`text=0x59f4 data=0x6442 bss=0x3f0a8`, **1563 relocations**, entropy 6.25 — plus `RUNME_PLAIN.PRG`
and `GOS.PRG` (the depacked wrappers, for the record) and `disk/`, a folder TOS boots the game from:
`AUTO/FLYSHARK.PRG` and the container's 21 files in `A/`, which is the relative path the game itself
asks for.

The program is in `AUTO/` because it has to load LOW: it puts its screen at a fixed `$70000/$78000`
and builds its scroll ring down from there to `$58800`, so it survives only if its TEXT lands at or
below `$d922`. TOS's own `AUTO` scan gives it `$aa56`; started from the desktop it gets `$12596` and
its own ring overwrites the music driver it just loaded. See
[`notes/loader.md`](notes/loader.md), "Where the screen lives".

`bin/` and `out/` are gitignored — supply your own copy of the release.

## Analyze, reconstruct, run

```bash
python3 tools/unpack_dist.py                # depack + split the container; prints the manifest
/Users/geogeo/miniconda3/envs/atari_reverse/bin/python -m pytest tools/   # pin the directory + payload digest
bash run.sh                                 # import FLYSHARK.PRG -> analyze -> annotate -> decomp.c
# read decomp.c, grow names.txt, then:
bash reapply.sh

python3 tools/boot_shots.py                 # boot bin/disk under Hatari -> out/boot/title.png
python3 tools/extract_assets.py             # title picture, palette, bank sheets -> out/assets/
```

## Status

**Bootstrap done; naming in progress.** The distribution is unpacked and pinned by a test, and the
extracted game **plays** under Hatari from a plain folder, with no Gamex runtime: title
(`out/boot/title.png`, 15/15 of the title palette on screen), then the attract cycle — credits and
HALL OF FAME over a live scrolling level 1 (`out/boot/attract_1.png`, `attract_2.png`) — with no
fault lines. Input is untested; a joystick cannot be pressed headless. `names.txt` and `notes/` carry
the naming wave's own progress.

Not built yet: a real `.ST` floppy. It needs `tools/st_build.py` to grow arbitrary subdirectories —
this disk wants both `AUTO\` and `A\` — and that is the only thing standing between this and real
hardware.
