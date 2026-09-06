# Bubble Ghost (ERE Informatique, 1987 / Accolade, 1988) — Atari ST

A ghost blows a fragile bubble through the rooms of a castle, past candles, fans and spikes; the
title picture signs it *by C.Andreani* over *Copyright 1988, ACCOLADE INC. TM*. One 61 KB
`GHOST.PRG` plus six data files on a single-sided floppy, written in **Alcyon/DRI C, small model**.

**Status: bootstrap only.** The shipped executable was decrypted statically, the copy protection is
understood and passes under Hatari, the Ghidra project is up with **38 of its 134 functions named**,
and the graphics and speech are decoded straight out of the data files. There is **no `recreate/`
yet** — nothing here is verified against a 68000 oracle, and no reconstruction exists.

> No game data is in this repository. `bin/` and `out/` are gitignored; bring your own disk.

## The disk

| file | bytes | what it is |
|---|---:|---|
| `GHOST.PRG` | 61,032 | the game, wrapped in a disk-protection **encrypter** (below) |
| `GHOST.LOA` | 2,703 | a standalone MFP Timer A **sample player**, loaded as data and `jsr`ed |
| `GHOST.VOI` | 30,100 | the sample it plays: the "Welcome to Bubble Ghost" speech, 14,985 Hz |
| `GHOST.DAT` | 184,352 | the tile bank — 360 × 512 bytes + a 32-byte palette |
| `GHOST.PRE` | 30,752 | the presentation screen — 60 × 512 bytes + a 32-byte palette |
| `GHOST.DEM` | 6,000 | the attract-mode recording: 1,000 records of 6 bytes |
| `DESKTOP.INF` | — | French desktop settings; **no autostart line, and no AUTO folder** |

`GHOST.SCR` is not on the disk: the game creates it on A: the first time it saves the hall of fame.
Every filename the program opens carries an explicit `A:` prefix except `GHOST.LOA`/`GHOST.VOI`,
which are built byte by byte at run time and load from the current drive.

## The wrapper is a cipher, not a cruncher

`GHOST.PRG` is the *same size* as the program inside it. Its five-word entry stub jumps into the
tail of the DATA segment, where a 262-word `eor` loop decrypts the wrapper's own second half — and
the first word it writes is the loop's own `dbf` displacement, which the 68000 has **already
prefetched**, so pass one branches to the stale target and runs a fixup tail that ones-complements
the key table. The unpacked code then `Floprd`s **track 79** of drive A: (sectors 245, 246 and 247,
which carry fuzzy bits and bad CRCs), CRCs what it read, CRCs the wrapper's own last 632 bytes with
that as the polynomial, and uses the 16-bit result as the key of a stream cipher over the whole
program — `plain[i+1] = cipher[i+1] ^ plain[i] ^ SR ^ k[i]`, with the CPU's **own condition codes**
in the keystream. So the check is not a branch anyone can patch out: get the disk wrong and you get
rubbish, not a failed test. The key (`0x586b`) fell to an exhaustive search over all 65,536 values,
scored on whether the plaintext looks like a program.

Full annotated disassembly, layer by layer, in [`notes/loader.md`](notes/loader.md); the general
lessons are in [`docs/packed-executables.md`](../../docs/packed-executables.md).

## Reproduce it

```bash
# 1. decrypt the shipped executable (statically — no emulator, no disk)
python3 ../../tools/depack_bubbleghost.py bin/GHOST.PRG -o bin/GHOST_PLAIN.PRG
#    61032 packed -> 60391 bytes: text 0xe8ca, data 0x2f4, bss 0x6650, 9 relocations

# 2. Ghidra: one bootstrap, then the naming loop
bash run.sh                  # RE-IMPORTS AND WIPES NAMES — first bootstrap only
#    rewrites GHOST_PLAIN.PRG -> bin/GHOST_RT.PRG (run-time layout), pins a4, seeds 0x16d8e
bash reapply.sh              # the naming loop: names.txt -> DB -> decomp.c (on GHOST_RT.PRG)

# 3. prove the protection, and the static decrypter, on a real CPU
python3 tools/boot_ghost.py  # headless Hatari, TOS 1.04, the Pasti dump in A:

# 4. decode the data files (needs Pillow; output to out/assets/, gitignored)
python3 tools/extract_gfx.py
python3 tools/extract_audio.py
```

**Why the relayout.** The Alcyon/DRI C crt0 moves the DATA segment *above* the BSS before anything
else runs and parks `a4` on the boundary, so the file layout `[TEXT][DATA][BSS]` is not the layout
the program executes in and every global is reached as `n(a4)`: with the Ghidra image in file
layout the decompiler showed **10,031 `a4 + n` expressions and no global had an address** for a
`var` line to name. Feeding Ghidra the rebuilt `[TEXT][BSS][DATA]` image and pinning `a4` leaves
**0 of them, with 8,166 globals resolved to their run-time addresses** — a Ghidra address is the
run-time address everywhere, for code, BSS and DATA alike. The general recipe is in
[`docs/ghidra-pipeline.md`](../../docs/ghidra-pipeline.md), "Small-model C".

`boot_ghost.py`'s gate is **not the picture**: it passes only when the whole TEXT
`depack_bubbleghost.py` produced statically is found byte for byte in the emulated machine's RAM
(the nine relocated longwords excepted), with a clean Hatari log, exit status 0 and a non-blank capture.
That answers "does the protection pass under Hatari" and "is the static decrypter right" at once.
Starting the game from a GEMDOS C: is legitimate here because the protection addresses drive A: **by
device number**, so the `.stx` and its fuzzy bits stay where the check looks.

## The data files

`GHOST.PRE` and `GHOST.DAT` are the **same format**: a run of 32×32-pixel tiles, 512 bytes each
(32 rows of two word-interleaved low-res groups), back to back with no header or index table, and a
16-entry `$0RGB` palette at the end. `GHOST.PRE`'s 60 tiles are the title screen in row-major order,
10 across by 6 down = 320×192 — eight scan lines short of a full ST screen. The layout was found by
a stride sweep and pinned by a seam test; every "obvious" 320×192 reading renders as striped noise.

**`GHOST.DAT` is described two ways in the notes, and they are the same bytes.**
[`notes/anchors.md`](notes/anchors.md) reads it off the loader as *six 320×192 pictures*, because
`0x1396c` `malloc`s six `0x7800` buffers and then a `0x20` palette;
[`notes/assets_survey.md`](notes/assets_survey.md) reads it off the pixels as *360 tiles of 32×32*,
which renders as coherent artwork. 6 × 30,720 = 360 × 512, so both are true of the file — **the code
will settle how the game addresses them**, and that is the same question as where the room maps are.

`GHOST.VOI` is raw unsigned 8-bit PCM, one 2.0 s phrase, played by `GHOST.LOA` through the PSG's
three volume registers at 14,985 Hz. `GHOST.DEM` is 1,000 six-byte records that look like recorded
*object state* — ghost x/y/tile, bubble x/y/frame — rather than an input script; the fields
cross-check against `GHOST.DAT`'s own tile ranges. Formats, evidence and what is still hypothesis:
[`notes/assets_survey.md`](notes/assets_survey.md).

## Gallery

Unlike the solved games in this repository, **neither picture below was drawn by a reconstruction** —
there is no reconstruction yet. The left one is `GHOST.PRE` decoded by `tools/extract_gfx.py`; the
right one is the original binary itself, decrypted by its own wrapper inside Hatari.

| `GHOST.PRE`, decoded from the file | the game's menu, past the protection |
|:---:|:---:|
| ![](../../assets/bubbleghost/title.png) | ![](../../assets/bubbleghost/menu-hatari.png) |

## What is next

- **The naming loop.** 38 of 134 functions carry names; four of those are marked `# ctx` (named
  from the call site, body unread) and must be confirmed. Ghidra decompiles 123 of the 134 — the 11
  failures are all in the Alcyon C runtime. The program's shape is already anchored: `main` at
  `0x100dc`, the top loop at `0x101e6`, `a4` on the BSS/DATA boundary, two trap trampolines carrying
  all 92 OS calls, and exactly one installed vector (Timer C, the sound player).
- **A `recreate/` harness.** Nothing here is proved against the Musashi oracle yet. The game is
  remarkably OS-friendly for 1987 — all video through XBIOS, all keyboard through GEMDOS raw
  console, no Line-A, no VDI, and `$ffff8800` plus `$fffffa17` the only hardware addresses in the
  image — so the port should be dominated by drawing code rather than by hardware banging.
- **Music and effects.** Neither is on the disk: both come out of `GHOST.PRG`'s own PSG synth engine
  (ADSR-style voice records of `0x8c` bytes, driven by the Timer C ISR at `0x1459a`, reached through
  a `trap #9` supervisor gate the game installs itself). Once it is named, capture it the way
  [`projects/zynaps/tools/extract_audio.py`](../zynaps/tools/extract_audio.py) does: run the original
  under the kit's oracle, log the `$ff8800`/`$ff8802` writes per 50 Hz frame, render through
  `projects/buggyboy/recreate/sound/ym2149.py`.
- **The open questions the code must answer** are listed at the end of
  [`notes/assets_survey.md`](notes/assets_survey.md): the room maps, transparency, whether there are
  per-room palettes, and `GHOST.DEM`'s coordinate unit and origin.

`names.txt` is the source of truth for every name, at load base `0x10000` (Ghidra address = image
offset + `0x10000`).
