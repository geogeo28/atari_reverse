# Flying Shark — the disk asset formats

Every claim below is derived from the routine named beside it in `out/prg_dis.txt` and then
re-checked against the bytes; where a render settled it, the render is described. The disk files
were carved from `bin/FILES/FRD` (a raw dump of disc A's data area) at the offsets in the project
brief; the carve reproduces exactly the eight names in the game's own file table plus the nine
extra tile banks.

The load addresses come from `asset_file_table` at Ghidra `0x162ee` (see `out/names_data.txt`),
and the four buffers are contiguous:

```
0x1be36  SPRITES.cru  0x1caf2      (FLY_SHK.NEO 0x7d80 lands here first, then is overwritten)
0x38928  HSC bank 0   0x8000  \
0x40928  HSC bank 1   0x8000   |  0x1be36 + 0x1caf2 == 0x38928 exactly
0x48928  HSC bank 2   0x8000   |  0x38928 + 4*0x8000 == 0x58928 exactly
0x50928  HSC bank 3   0x8000  /
0x58928  MODULE.BAK   0x1065      (header included; its TEXT is at 0x58944)
```

---

## `FLY_SHK.NEO` — the title screen — **certain**

A stock NEOchrome file: 128-byte header, then 32,000 bytes of low-resolution screen.
`128 + 32000 = 32128 = 0x7d80`, the exact length in the file table.

Header (`+0x00` flag `0000`, `+0x02` resolution `0000` = low), **palette = 16 ST colour words at
`+0x04`**: `000 600 243 016 037 157 267 132 222 751 373 000 431 333 555 777`. The filename field at
`+0x24` is blank; the colour-cycling fields at `+0x30` hold `801e` and the game ignores them.

The proof is `show_title_screen` at `0x11212`: it `Setpalette`s **`0x1be3a` = buffer + 4**, and then
copies `0x1f40` longwords (32,000 bytes) from **the start of the file** to **`physbase - 0x80`** —
so the 128-byte header is deliberately laid just below the screen and the image bytes land on it.
Rendered with `st_pixels.decode_planar(neo, 320, 200, offset=128)` and the `+4` palette it comes out
as the Flying Shark title art, correct colours, no shear.

## `SPRITES.CRU` — the sprite bank — **certain**

117,490 bytes, loaded **raw** — nothing in the image decrunches it, and the file is plainly a
directory plus pixels, so the `.cru` extension is a leftover, not a container.

```
0x00000  directory: 256 records of 20 bytes  (= 5120 = 0x1400)
0x01400  pixel data, one blob per record, in record order, to the last byte of the file
```

Record:

| off | size | field |
|---|---|---|
| +0 | LONG | offset of the pixel data from the start of the file |
| +4 | WORD | width in 16-pixel words, **minus 1** |
| +6 | WORD | height in rows, **minus 1** |
| +8, +10 | WORD | draw offset (x, y): the blitter adds it at 0x144c2/0x144fe before clipping, and `sprite_hitbox_test` @0x116b8 adds it too |
| +12, +14 | WORD | extra hit-box offset (x, y), added on top of the draw offset by `sprite_hitbox_test` only |
| +16, +18 | WORD | hit-box width, height in pixels (`add.w 16(a4)` / `18(a4)` give the far edge) |

Two routines pin it. `0x112c2` walks the directory adding the buffer base `0x1be36` to the `+0`
longword of each of **256** records with `lea 20(a0),a0` — that is the record count and the stride.
`sprite_hit_test` at `0x11698` indexes with `muls.w #$14,d0` and reads `8(a4)`,`12(a4)` and `16(a4)`
as *x offset, x offset, width* and `10/14/18` as the *y* trio — which is what makes `+16/+18` a hit
box rather than the bitmap size (record 50 is a 32×25 bitmap with a 49×39 box).

Pixels are **masked, word-interleaved bitplanes**: five words per 16-pixel group — mask first, then
planes 0..3 — so the row stride is `(width_words) * 10` bytes and a frame is `stride * rows`.
Arithmetic check: leaving out the 12 hit-box-only records (zero bytes, sharing the previous pointer),
all **218 bitmap records** chain exactly — each `stride*rows` equals the gap to the next bitmap's data
offset and the last ends on the final byte of the file (`tools/extract_assets.py` refuses otherwise). Rendering records
0..47 with `decode_planar(..., masked=True)` gives clean biplanes with fully transparent
backgrounds; the same records decoded unmasked show the mask smeared into the artwork, so the
masked reading is the right one.

Counts: **230 used records (0..229)**, 26 zero-filled spares; 218 carry a bitmap. Widths of the
bitmap records are 1 word (68), 2 words (131), 3 (6) or 4 (13); heights run to 64 rows.

**Twelve records carry no bitmap at all** — 38, 39, 40, 42, 43, 44, 45, 46, 48, 49, 141 and 152 have
height-minus-1 = `-1`, share the previous record's data pointer and occupy zero bytes, but do carry
a large hit box (70×71, 73×73, 64×64). They exist purely to give `sprite_hit_test` a box for
something that is drawn out of several other sprites — an extractor must skip them rather than
treat them as corrupt.

## `HSC_n.DAT` — the tile banks — **certain**

Thirteen files, `HSC_0` … `HSC_C`, all exactly 32,768 bytes and all thirteen genuinely different
(distinct MD5s). Four are resident at a time, back to back, so a single byte addresses 256 tiles.

A tile is **512 bytes = 32 rows × 16 bytes = 32×32 pixels, four word-interleaved bitplanes, no
mask, no per-bank palette**. The proof is the map draw: `0x1486e` computes the tile address as
`index * 512` (`asl.l #4` then `asl.l #5`), the inner blit at `0x1489c` copies four longwords
(16 bytes = 16 px × 4 planes… i.e. two 16-pixel groups) and then skips `144` bytes — `16 + 144 =
160`, one whole low-resolution screen row — and the full-refill loop at `0x145ee` sets `d7 = 0x1f`,
32 rows. Rendered as 8×8 sheets against `palette_game` (`0x16294`), banks 0, 3 and C all come out as
coherent 32×32 terrain: runways, hangars, trees, coastline, sea.

Tile 0 is the plain background tile and is the only duplicate in a bank.

Which bank goes where is not in the file — it is in `level_asset_digit_table` (`0x162d4`), the
string `012314567289AB3013B48C375`, five digits per level:

| level | HSC banks | map |
|---|---|---|
| 1 | 0 1 2 3 | LEVEL1 |
| 2 | 4 5 6 7 | LEVEL2 |
| 3 | 8 9 A B | LEVEL3 |
| 4 | 0 1 3 B | LEVEL4 |
| 5 | 8 C 3 7 | LEVEL5 |

`load_level_assets` (`0x10332`) pokes those digits straight into the `A\HSC_0.DAT` /
`A\LEVEL1.MAP` strings in the file table before loading. Levels 2 and up need banks that are not on
disc A, which is where the "PLEASE INSERT DISC B" prompt comes from.

## `LEVELn.MAP` — the scrolling terrain — **certain**

```
+0  WORD  columns   (10 in all five files)
+2  WORD  rows
+4        rows * columns * 2 bytes of cells
```

A cell is **two bytes: base tile index, overlay tile index**, both indexing the 256 resident tiles.
Row stride is therefore 20 bytes.

| file | bytes | cols | rows | `4 + rows*20` |
|---|---|---|---|---|
| LEVEL1.MAP | 3,664 | 10 | 183 | 3,664 |
| LEVEL2.MAP | 4,184 | 10 | 209 | 4,184 |
| LEVEL3.MAP | 4,084 | 10 | 204 | 4,084 |
| LEVEL4.MAP | 4,084 | 10 | 204 | 4,084 |
| LEVEL5.MAP | 4,624 | 10 | 231 | 4,624 |

The code says the same thing twice. At `0x1050e` the game reads the header and computes the initial
cursor as `0x16436 + rows * (columns*2)` — **one past the end of the map** — and stores it in
`map_row_ptr`; `0x147d0` then walks it *backwards* 20 bytes at a time, once per 32 pixels of scroll.
So **the end of the file is the start of the level.** In the per-column loop at `0x1484a` the cursor
advances by `lea 2(a3),a3` (the cell size) for `d7 = 9` iterations (ten columns), reading
`(a3)`/`20(a3)` as the two base tiles of the vertical split and `1(a3)`/`21(a3)` as their overlays;
if both overlays are zero it takes the plain copy at `0x14898`, otherwise the masked merge at
`0x14d0a`.

Rendering LEVEL1 by walking the rows from the last to the first, ten tiles wide, gives a
320×5,856-pixel strip that reads as one continuous landscape: the carrier/airfield with runway and
hangars at the level's start, then trees, a coastline and open sea. The overlay plane rendered on
its own is mostly tile 0 with isolated patches of foliage and a bridge — exactly the "sparse second
layer" the two code paths imply.

Note there is **no spawn data in the map**. Enemy waves come from the per-level script blocks in
DATA that `level_table` (`0x15a4c`) points at (`0x1b350`, `0x1b5aa`, `0x1b7e6`, `0x1b9d2`,
`0x1bbd2`), driven by the scroll-progress counter — that is gameplay-slice territory.

## `MODULE.BAK` — see `notes/sound_engine.md`

A GEMDOS `.PRG` (`601a`, text `0x1048`, `ABSFLAG 0xffff`, no relocs) read whole, header included.
Its TEXT base is `0x58944 = 0x58928 + 28`.

## `HSC_4` … `HSC_C` and the disc-B split

Disc A carries all thirteen tile banks in the `FRD` dump used here, so the extractor does not need
disc B; the prompt exists because the *original* disc A only held banks 0–3.

## Reference: rendering these with `tools/st_pixels.py`

```python
import st_pixels as sp
# title
sp.to_rgb_image(sp.decode_planar(neo, 320, 200, offset=128), sp.read_palette(neo, 4))
# one sprite (rec = the 20-byte record)
sp.decode_planar(cru, (rec.words)*16, rec.rows, offset=rec.data_off, masked=True)
# one tile
sp.decode_planar(bank, 32, 32, offset=index*512)
```

`palette_game` at Ghidra `0x16294` (image `0x6294`) is the in-play palette for the sprites and the
tiles: its Setpalette wrapper (0x111be) runs at every level start (0x11564, 0x1055e, 0x14be6). The
words at `0x16274` (`palette_title`, wrapper 0x111d6) are installed once by `init_load_assets` just
before the NEO title replaces them with its own; under them the tiles come out green-on-green. An
earlier draft of this note had the two swapped.
