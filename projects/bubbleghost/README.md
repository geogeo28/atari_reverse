# Bubble Ghost (ERE Informatique, 1987 / Accolade, 1988) — Atari ST

A ghost blows a fragile bubble through the rooms of a castle, past candles, fans and spikes; the
title picture signs it *by C.Andreani* over *Copyright 1988, ACCOLADE INC. TM*. One 61 KB
`GHOST.PRG` plus six data files on a single-sided floppy, written in **Alcyon/DRI C, small model**.

**Status: fully named, and every named function reconstructed and verified.** The shipped
executable was decrypted statically, the copy protection is understood and passes under Hatari, the
graphics and speech are decoded out of the data files, and the whole program has been read —
**132 of its 134 functions named, 203 globals, 161 plate comments** in `names.txt`. `recreate/`
holds the C reconstruction: **all 132 of those functions are green under the differential harness**,
byte-for-byte against the original 68000 code, across **1,895 tests**.
[`recreate/STATUS.md`](recreate/STATUS.md) is the per-function ledger and says what the harness can
and cannot see; what is left is `GHOST.LOA` — a second program with no address in this one — and
five small regions of the two top-level routines that no slice may include.

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

`GHOST.SCR` is not on the disk: the game creates it on A: the first time it saves the hall of
fame. Every filename carries an explicit `A:` prefix except `GHOST.LOA`/`GHOST.VOI`, which are
built byte by byte at run time and load from the current drive.

## The wrapper is a cipher, not a cruncher

`GHOST.PRG` is the *same size* as the program inside it. Its five-word entry stub jumps into the
tail of the DATA segment, where a 262-word `eor` loop decrypts the wrapper's own second half — and
the first word it writes is the loop's own `dbf` displacement, which the 68000 has **already
prefetched**, so pass one branches to the stale target and runs a fixup tail that ones-complements
the key table. The unpacked code then `Floprd`s **track 79** of drive A: (sectors 245–247, fuzzy
bits and bad CRCs), CRCs what it read, CRCs the wrapper's own last 632 bytes with that as the
polynomial, and uses the 16-bit result as the key of a stream cipher over the whole program —
`plain[i+1] = cipher[i+1] ^ plain[i] ^ SR ^ k[i]`, with the CPU's **own condition codes** in the
keystream. So the check is not a branch anyone can patch out: get the disk wrong and you get
rubbish, not a failed test. The key (`0x586b`) fell to an exhaustive search over all 65,536
values, scored on whether the plaintext looks like a program. Layer-by-layer disassembly in
[`notes/loader.md`](notes/loader.md); general lessons in
[`docs/packed-executables.md`](../../docs/packed-executables.md).

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
python3 tools/extract_gfx.py && python3 tools/extract_audio.py

# 5. the reconstruction harness (image-model + constants tests)
make -C recreate test
```

**Why the relayout.** The Alcyon/DRI C crt0 moves the DATA segment *above* the BSS before
anything else runs and parks `a4` on the boundary, so the file layout `[TEXT][DATA][BSS]` is not
the layout the program executes in and every global is reached as `n(a4)`: in file layout the
decompiler showed **10,031 `a4 + n` expressions and no global had an address** for a `var` line
to name. The rebuilt `[TEXT][BSS][DATA]` image with `a4` pinned leaves **0 of them, and 8,166
globals resolved to their run-time addresses**. Recipe:
[`docs/ghidra-pipeline.md`](../../docs/ghidra-pipeline.md), "Small-model C".

`boot_ghost.py`'s gate is **not the picture**: it passes only when the whole TEXT
`depack_bubbleghost.py` produced statically is found byte for byte in the emulated machine's RAM
(the nine relocated longwords excepted), with a clean Hatari log, exit status 0 and a non-blank
capture — answering "does the protection pass under Hatari" and "is the static decrypter right"
at once. Starting the game from a GEMDOS C: is legitimate here because the protection addresses
drive A: **by device number**, so the `.stx` and its fuzzy bits stay where the check looks.

## The data files

`GHOST.PRE` and `GHOST.DAT` are the **same format**: 32×32-pixel tiles, 512 bytes each (32 rows
of two word-interleaved low-res groups), back to back with no header or index, and a 16-entry
`$0RGB` palette at the end. `GHOST.PRE`'s 60 tiles are the title screen in row-major order, 10
across by 6 down = 320×192 — eight scan lines short of a full ST screen. The layout was found by a
stride sweep and pinned by a seam test; every "obvious" 320×192 reading renders as striped noise.

**`GHOST.DAT` is described two ways in the notes, and they are the same bytes** — six 30,720-byte
buffers off the loader (`load_level_pictures` `malloc`s six `0x7800` blocks and a `0x20` palette)
and 360 tiles of 32×32 off the pixels. 6 × 30,720 = 360 × 512, and **the code settles it**: the
game fetches tile *n* as `dat_bank[n / 60] + (n % 60) * 512`, one 360-tile bank read in six
pieces. The room maps are 5×10 word grids of those indices, in the 36-record `room_table`
(`0x21a4a`).

`GHOST.VOI` is raw unsigned 8-bit PCM, one 2.0 s phrase, played by `GHOST.LOA` through the PSG's
three volume registers at 14,985 Hz. `GHOST.DEM` is 1,000 six-byte records of recorded *object
state* — `(ghost_x/3, ghost_y/2, ghost_tile, bubble_x/3, bubble_y/2, bubble_frame)`, confirmed
against the demo player: one record per drawn frame, 980 of the 1,000 replayed, no `Vsync` in the
loop. Formats and evidence: [`notes/assets_survey.md`](notes/assets_survey.md).

## Gallery

**Neither picture below was drawn by a reconstruction** — there is none yet. The left one is
`GHOST.PRE` decoded by `tools/extract_gfx.py`; the right one is the original binary, decrypted by
its own wrapper inside Hatari.

| `GHOST.PRE`, decoded from the file | the game's menu, past the protection |
|:---:|:---:|
| ![](../../assets/bubbleghost/title.png) | ![](../../assets/bubbleghost/menu-hatari.png) |

## What is next

The naming loop is done — **132 of 134 functions, 203 globals, 161 plate comments** — and so is the
port: every one of those 132 is verified byte-for-byte against the original, in **1,895 tests**.
Ghidra decompiled 123 of the 134; the 11 failures are all Alcyon C runtime, read out of the
disassembly. [`recreate/README.md`](recreate/README.md) has the image model and the procedure;
[`recreate/STATUS.md`](recreate/STATUS.md) has the ledger, the residuals and the kit's remaining
model gaps.

**What is left is three things, and none of them is a function of this program:**

1. **`GHOST.LOA`** — the standalone MFP Timer A sample player, loaded as data and `jsr`ed. It is a
   second program with no address in this one; the two game routines that load and arm it are
   verified, and the LOA's own code is not. It programs a timer, busy-waits on a flag its own
   interrupt handler sets, and arms the cartridge DAC — none of which the kit models.
2. **A staged console stream the keyboard flush does not drain.** Every key this game reads it reads
   as `while (Cconis()) Crawcin(); c = Cnecin();`, and the model's console is one queue the flush
   empties — so no run can cross a flush into the blocking read behind it, and the whole front end
   is verified as regions that each END at one. STATUS.md's "Model gaps" says what closing it needs.
3. **A playable `.PRG`.** Everything the differential cannot see — the palette, the screen base, the
   VDI's colour mapping, the font, `Vsync`, the text cards' timing — is invisible here by
   construction, and the surface for all of it is an on-target run
   ([`docs/on-target-execution.md`](../../docs/on-target-execution.md)). This project has no build
   yet.

The game is remarkably OS-friendly for 1987 — a **GEM application**: text, the bonus bar and every
32×32 sprite blit go through the **VDI** (`trap #2`, `d0 = 0x73`), the input is the **mouse**
(`vq_mouse` for position and facing, `vq_key_s` for the Shift-key blow), XBIOS carries the screen
base and the palette, GEMDOS the files and the menu keys, there is no Line-A, and `$ffff8800` plus
`$fffffa17` are the only hardware addresses in the image. That is what the port turned out to be
dominated by: drawing code rather than hardware banging, and teaching the kit the VDI — sixteen
entry points, an ST raster and `vro_cpyfm`'s sixteen logic operations. Everything the asset survey left
open is answered at the end of [`notes/assets_survey.md`](notes/assets_survey.md), with the bodies
read in [`notes/frontend.md`](notes/frontend.md), [`notes/gameplay.md`](notes/gameplay.md) and
[`notes/sound_engine.md`](notes/sound_engine.md).

`names.txt` is the source of truth for every name; its addresses are Ghidra addresses at load base `0x10000` (= image offset + `0x10000`).
