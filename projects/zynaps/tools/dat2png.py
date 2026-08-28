#!/usr/bin/env python3
"""Zynaps (Hewson, 1988 - Atari ST) asset decoder: renders every disk asset to PNG.

Usage
-----
    python3 dat2png.py <disk_dir> <out_dir> [--prg <ZYNAPS17.PRG>] [--scale N]
    python3 dat2png.py --scan-palettes --prg <ZYNAPS17.PRG>

`disk_dir` is the directory holding the extracted floppy contents (ALIENA.DAT ...
ZYNPIC.PIC).  `--prg` defaults to `<disk_dir>/../ZYNAPS17.PRG`; the PRG is only
needed for its palettes.  Rendering needs Pillow; `--scan-palettes` does not.

Where the formats come from
---------------------------
Every layout below was read out of ZYNAPS17.PRG and then confirmed by rendering.
The three routines that pin the whole file set down are:

  * `load_file` @ $144E8 - `a0`=filename, `a1`=buffer, `d1`=byte count; Fopen /
    Fread / Fclose.  Walking its call sites yields the exact buffer size of every
    asset (e.g. myship.dat = $AF0 = 2800).
  * `unpack_frames` @ $153C0 / `$153F6` - called with `d2` = bytes per animation
    frame and `d7` = frame count - 1, which is where the frame splits come from.
  * `unpack_level_map` @ $15920 - the LEV*.MAP RLE decoder (see below).

The filename strings live at PRG file offset 0x96A2 and are *lowercase*, which is
why a case-sensitive grep for "ALIENA.DAT" finds nothing.  Only one name of each
family is stored ("alienb.dat", "mother1.dat", "lev5.map", "zyn5.dat"); the game
pokes a digit/letter into the string before loading.

Pixel formats
-------------
The ST's plane, mask and palette model itself lives in `tools/st_pixels.py`; what
is Zynaps-specific is only which shape each file has, which is the FRAMED_ASSETS
table below plus the four composite renderers.

1. MASKED WORD SPRITE (most .DAT files, 10 bytes per 16 pixels)
   Each row is `width/16` groups of five big-endian words:
       mask, plane0, plane1, plane2, plane3
   A mask bit that is SET means transparent (the blitter ANDs the mask, then ORs
   the data).  Plane 0 is the LSB of the colour index.

2. MASKED BYTE FONT (CHARS2.DAT, EXTCHARS.DAT - 5 bytes per 8 pixels)
   The same scheme at byte granularity: mask byte + four plane bytes per row,
   8 rows per glyph = 40 bytes per glyph.  CHARS2 = 40 glyphs, EXTCHARS = 48.

3. PLAIN 4-PLANE (screens, tiles, panels - 8 bytes per 16 pixels)
   Standard ST interleaved low-res: word0=plane0 ... word3=plane3, no mask.
   ZYNPIC.PIC is one raw 320x200 screen; STATUS.PI1 (despite the extension - it
   is NOT a Degas file, it has no header and no palette) is a raw 320-px-wide
   strip, and its 53 rows are simply its length divided by the line stride.

4. PLAIN 4-PLANE, BYTE GRANULAR (SMSHIP.DAT, LIFEGRA.DAT)
   plane0..plane3 as single bytes per 8-pixel row.

5. COLUMN-STRIP IMAGES (ZYNLOGO.DAT, SMLOGOS.DAT)
   A wide picture stored as several full-height vertical strips, laid out one
   after another in the file.  The SMLOGOS blitter @ $1452C proves it: it reads
   longwords at +0/+256/+512/+768/+1024 (256 = 32 rows * 8 bytes = one strip) and
   selects one of two 0x500-byte images with a toggling flag.

6. LEVEL TILE SETS (ZYN1/ZYN3/ZYN8.DAT)
   A flat array of 16x8 pixel, 4-plane tiles, 64 bytes each, indexed from zero -
   there is no header.  Tile 0 (which opens 0x7888 0xFFFF ...) is the background
   texture.  Sizes divide exactly: ZYN1 = 617 tiles, ZYN3 = 557, ZYN8 = 502, and
   the largest tile index each level map uses lands exactly inside its set.

7. LEVEL MAPS (LEV*.MAP) - RLE, decoded by `unpack_level_map` @ $15920
   The map is 18 rows x 400 columns of 16-bit tile words.  Each row is coded
   independently as a stream of control words:
       control & 0x8000 == 0 : literal run - the next `control` words are tiles
       control & 0x8000 != 0 : repeat run  - the next single word is repeated
                               `control & 0x7FFF` times
   A row always expands to exactly 400 entries; the decoder consumes each of the
   twelve .MAP files to the last byte.  In a tile word, bits 0-14 are the tile
   index and bit 15 is an attribute flag (collision/solid - not needed to draw).
   18 rows * 8 px = 144 px of playfield, above the 53-row status panel.
   Both invariants are asserted below, so a wrong file or a mis-read format stops
   instead of drawing plausible rubbish.

Palettes
--------
Standard ST: 16 words of 0x0RGB with 3 bits per channel.  In ZYNAPS17.PRG:
    0x8FE0  status-panel / fade palette (its first longword is written straight
            to $FF8240 by the colour-cycle code @ $106AE)
    0x9000  table of 12 level palettes, 32 bytes each (LEV1 -> +0, LEV2 -> +32,
            ... LEVZ -> +352).  Selected @ $10A86 by `lea $8FE4;  d0 = pal<<5`.
    0x9614  title / logo palette (ZYNPIC.PIC, the two logos)
    0x9634  intro palette
    0x9654  a copy of the LEV1 palette used by the bonus stages
`--scan-palettes` lists every run of 16 consecutive valid ST palette words.

Output
------
One PNG per asset in `out_dir`.  Sprites are written RGBA with the masked-out
pixels fully transparent; colour index 0 is a normal opaque colour everywhere
else (it is the level background, not a transparency key).  Animation frames are
laid out left to right, separated by one transparent column.
"""

import argparse
import os
import struct
import sys
from collections import namedtuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(PROJECT_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from st_pixels import (  # noqa: E402  (needs the path above)
    PALETTE_BYTES, PALETTE_ENTRIES, PIXELS_PER_BYTE, PIXELS_PER_WORD, ST_COLOUR_INVALID,
    TRANSPARENT, decode_planar, image_bytes, is_st_colour_word, read_palette, read_palette_words,
    row_bytes, scaled, split_rows, to_rgba_image)

LOWRES_WIDTH = 320
LOWRES_HEIGHT = 200
FRAME_GAP_PX = 1

# --- palettes, as file offsets inside ZYNAPS17.PRG --------------------------
PAL_PANEL = 0x8FE0
PAL_LEVEL_TABLE = 0x9000
PAL_TITLE = 0x9614

# The three palettes the asset table draws with, by name.
PANEL, TITLE, LEVEL1 = "panel", "title", "level1"

# --- level tile sets and maps ----------------------------------------------
TILE_WIDTH = 16
TILE_HEIGHT = 8
TILE_BYTES = image_bytes(TILE_WIDTH, TILE_HEIGHT)  # 64
TILESET_SHEET_COLUMNS = 32
MAP_ROWS = 18
MAP_COLUMNS = 400
MAP_TILE_INDEX_MASK = 0x7FFF  # bits 0-14 of a map word; bit 15 is the collision attribute
MAP_RUN_FLAG = 0x8000  # in a CONTROL word: this run repeats one tile...
MAP_RUN_LENGTH_MASK = 0x7FFF  # ...this many times.  Same width as the tile index, different thing.

# Which tile set each level map is drawn with, and which entry of the level
# palette table it uses.  Both come from the byte tables the level loader indexes
# at PRG offsets 0x9868 (map letter), 0x9878 (tile-set digit) and 0x9888 (palette).
LEVEL_TILESET = {
    "LEV1": "ZYN1", "LEV2": "ZYN1", "LEV3": "ZYN3", "LEV4": "ZYN1",
    "LEV5": "ZYN1", "LEV6": "ZYN3", "LEV7": "ZYN3", "LEV8": "ZYN8",
    "LEV9": "ZYN8", "LEVX": "ZYN1", "LEVY": "ZYN8", "LEVZ": "ZYN8",
}
LEVEL_ORDER = ["LEV1", "LEV2", "LEV3", "LEV4", "LEV5", "LEV6",
               "LEV7", "LEV8", "LEV9", "LEVX", "LEVY", "LEVZ"]

# --- multi-strip pictures ---------------------------------------------------
ZYNLOGO_STRIP_WIDTH = 64
ZYNLOGO_STRIP_ROWS = 64
ZYNLOGO_STRIPS = 3
SMLOGO_STRIP_WIDTH = 16
SMLOGO_STRIP_ROWS = 32
SMLOGO_STRIPS_PER_IMAGE = 5  # 5 * 16 px = 80 px wide
SMLOGO_IMAGES = 2  # "ZYNAPS" then "HEWSON"


# --- asset catalogue --------------------------------------------------------
# Every file below decodes the same way: one bitmap as tall as the file allows,
# cut into `frame_rows`-tall frames and laid out side by side.  The four columns
# after the geometry are what actually differ between them.
Asset = namedtuple("Asset", "width frame_rows unit_bits masked palette")

# The masked word sprites, all drawn in the level-1 palette: name -> (width, frame rows).
MASKED_SPRITES = {
    "ALIENA": (16, 16), "ALIENB": (16, 16), "ALIENC": (16, 16), "ALIEND": (16, 16),
    "ALIENE": (16, 16), "ALIENF": (16, 16), "ALIENG": (16, 16), "ALIENH": (16, 16),
    "ALSEEK": (16, 11), "ALTEXPL": (16, 16), "BIGAST": (32, 32), "BULLET": (16, 8),
    "EXPLODE": (16, 16), "GEMGRAF": (16, 16), "GNDTARG1": (16, 16), "GUNSIGHT": (16, 9),
    "MISSILE1": (16, 9), "MISSILE2": (16, 9), "MISSILE3": (16, 9),
    "MOTHER1": (64, 40), "MOTHER2": (64, 40), "MOTHER3": (64, 40), "MOTHER4": (64, 40),
    "MOTHER5": (64, 40), "MOTHER6": (32, 16), "MOTHER7": (32, 16),
    "MYSHIP": (32, 20), "NEWBOMB": (16, 8), "NEWBULS2": (16, 3), "ROCKET": (16, 16),
    "ROTBALLS": (16, 9), "SEEKER2": (16, 11), "SMALLEXP": (16, 16), "SPINNERS": (16, 8),
}

FRAMED_ASSETS = dict(
    [(name, Asset(width, frame_rows, PIXELS_PER_WORD, True, LEVEL1))
     for name, (width, frame_rows) in sorted(MASKED_SPRITES.items())] +
    [
        ("SWEAP", Asset(32, 26, PIXELS_PER_WORD, False, PANEL)),
        ("SSWEAP", Asset(16, 18, PIXELS_PER_WORD, False, PANEL)),
        ("POWER", Asset(64, 32, PIXELS_PER_WORD, False, PANEL)),
        ("HEWLOGO", Asset(64, 48, PIXELS_PER_WORD, False, TITLE)),
        ("SMSHIP", Asset(8, 8, PIXELS_PER_BYTE, False, PANEL)),
        ("LIFEGRA", Asset(8, 16, PIXELS_PER_BYTE, False, PANEL)),
        # The two fonts are the same shape as the rest: an 8x8 glyph is a frame.
        ("CHARS2", Asset(8, 8, PIXELS_PER_BYTE, True, PANEL)),
        ("EXTCHARS", Asset(8, 8, PIXELS_PER_BYTE, True, PANEL)),
    ])


def level_palette(prg, level_index):
    return read_palette(prg, PAL_LEVEL_TABLE + level_index * PALETTE_BYTES)


def scan_palettes(prg):
    """Maximal spans of >=16 consecutive valid ST colour words -> [(offset, word count)].

    Reporting maximal spans rather than every 16-word window keeps a palette *table* as one
    hit instead of one per sliding position.
    """
    words = struct.unpack(">%dH" % (len(prg) // 2), prg[:len(prg) // 2 * 2])
    spans = []
    start = None
    # ST_COLOUR_INVALID can never be a colour, so trailing it closes a span that runs to the end.
    for i, word in enumerate(words + (ST_COLOUR_INVALID,)):
        if is_st_colour_word(word):
            start = i if start is None else start
            continue
        if start is not None and i - start >= PALETTE_ENTRIES:
            spans.append((start * 2, i - start))
        start = None
    return spans


def blank(width, rows, fill=TRANSPARENT):
    return [[fill] * width for _ in range(rows)]


def paste(dest, src, x, y):
    for row_index, row in enumerate(src):
        dest[y + row_index][x:x + len(row)] = row


def lay_out_frames(frames):
    """Frames side by side, one transparent column apart."""
    if len(frames) == 1:
        return frames[0]
    height = len(frames[0])
    width = len(frames[0][0])
    sheet = blank(len(frames) * (width + FRAME_GAP_PX) - FRAME_GAP_PX, height)
    for i, frame in enumerate(frames):
        paste(sheet, frame, i * (width + FRAME_GAP_PX), 0)
    return sheet


def to_image(pixels, palette, scale):
    image = to_rgba_image(pixels, palette)
    return scaled(image, scale) if scale > 1 else image


def render_framed_asset(name, data, asset):
    """One FRAMED_ASSETS file: the whole file decoded, cut into frames, laid out in a row."""
    stride = row_bytes(asset.width, asset.unit_bits, asset.masked)
    if len(data) % stride:
        raise SystemExit("%s is %d bytes, not a whole number of %d-byte rows: the width or the "
                         "format is wrong" % (name, len(data), stride))
    pixels = decode_planar(data, asset.width, len(data) // stride,
                           unit_bits=asset.unit_bits, masked=asset.masked)
    return lay_out_frames(split_rows(pixels, asset.frame_rows))


# --- level maps -------------------------------------------------------------

def decode_level_map(data):
    """LEV*.MAP -> MAP_ROWS lists of MAP_COLUMNS tile words (mirrors $15920).

    Both of the format's measured invariants are checked: every row expands to exactly
    MAP_COLUMNS entries (never over-running, so nothing has to be truncated), and the twelve
    real maps consume their file to the last word.  The zero-length literal run the checks
    also rule out would otherwise leave the `while` below spinning forever.
    """
    words = struct.unpack(">%dH" % (len(data) // 2), data)
    grid = []
    cursor = 0
    for row_index in range(MAP_ROWS):
        row = []
        while len(row) < MAP_COLUMNS:
            control = words[cursor]
            cursor += 1
            if control & MAP_RUN_FLAG:
                row += [words[cursor]] * (control & MAP_RUN_LENGTH_MASK)
                cursor += 1
            elif control:
                row += list(words[cursor:cursor + control])
                cursor += control
            else:
                raise SystemExit("map row %d holds a zero-length literal run at word %d: this is "
                                 "not a LEV*.MAP" % (row_index, cursor - 1))
        if len(row) != MAP_COLUMNS:
            raise SystemExit("map row %d expands to %d columns, not %d"
                             % (row_index, len(row), MAP_COLUMNS))
        grid.append(row)
    if cursor != len(words):
        raise SystemExit("%d map rows consumed %d of the file's %d words: the row or column count "
                         "is wrong" % (MAP_ROWS, cursor, len(words)))
    return grid


def decode_tile(tile_data, index):
    return decode_planar(tile_data, TILE_WIDTH, TILE_HEIGHT, index * TILE_BYTES)


def render_level(map_data, tile_data):
    grid = decode_level_map(map_data)
    cache = {}
    pixels = blank(MAP_COLUMNS * TILE_WIDTH, MAP_ROWS * TILE_HEIGHT, fill=0)
    for row_index, row in enumerate(grid):
        for column, word in enumerate(row):
            index = word & MAP_TILE_INDEX_MASK
            if index not in cache:
                cache[index] = decode_tile(tile_data, index)
            paste(pixels, cache[index], column * TILE_WIDTH, row_index * TILE_HEIGHT)
    return pixels


def render_tileset(name, data, columns=TILESET_SHEET_COLUMNS):
    """A tile set as a contact sheet of 16x8 tiles.  The set is a flat array with no header,
    so a size that is not a whole number of tiles means it is not one."""
    if len(data) % TILE_BYTES:
        raise SystemExit("%s is %d bytes, not a whole number of %d-byte tiles"
                         % (name, len(data), TILE_BYTES))
    count = len(data) // TILE_BYTES
    rows = (count + columns - 1) // columns
    sheet = blank(columns * TILE_WIDTH, rows * TILE_HEIGHT)
    for index in range(count):
        paste(sheet, decode_tile(data, index),
              (index % columns) * TILE_WIDTH, (index // columns) * TILE_HEIGHT)
    return sheet


def render_strip_picture(data, strip_width, strip_rows, strips, image_index=0):
    """A wide picture stored as `strips` full-height vertical slices."""
    strip_bytes = image_bytes(strip_width, strip_rows)
    base = image_index * strips * strip_bytes
    picture = blank(strips * strip_width, strip_rows, fill=0)
    for i in range(strips):
        slice_pixels = decode_planar(data, strip_width, strip_rows, base + i * strip_bytes)
        paste(picture, slice_pixels, i * strip_width, 0)
    return picture


def build_assets(disk, prg, scale):
    """Yield (output name, PIL image) for every asset in `disk`."""
    read = lambda name: open(os.path.join(disk, name), "rb").read()  # noqa: E731
    palettes = {PANEL: read_palette(prg, PAL_PANEL),
                TITLE: read_palette(prg, PAL_TITLE),
                LEVEL1: level_palette(prg, 0)}

    for name, asset in FRAMED_ASSETS.items():
        pixels = render_framed_asset(name, read(name + ".DAT"), asset)
        yield name, to_image(pixels, palettes[asset.palette], scale)

    zynlogo = render_strip_picture(read("ZYNLOGO.DAT"), ZYNLOGO_STRIP_WIDTH, ZYNLOGO_STRIP_ROWS,
                                   ZYNLOGO_STRIPS)
    yield "ZYNLOGO", to_image(zynlogo, palettes[TITLE], scale)
    smlogos = read("SMLOGOS.DAT")
    for image_index in range(SMLOGO_IMAGES):
        picture = render_strip_picture(smlogos, SMLOGO_STRIP_WIDTH, SMLOGO_STRIP_ROWS,
                                       SMLOGO_STRIPS_PER_IMAGE, image_index)
        yield "SMLOGOS_%d" % image_index, to_image(picture, palettes[TITLE], scale)

    yield "ZYNPIC", to_image(decode_planar(read("ZYNPIC.PIC"), LOWRES_WIDTH, LOWRES_HEIGHT),
                             palettes[TITLE], 1)
    status = read("STATUS.PI1")
    status_rows = len(status) // row_bytes(LOWRES_WIDTH)
    yield "STATUS", to_image(decode_planar(status, LOWRES_WIDTH, status_rows),
                             palettes[PANEL], 1)

    for tileset in sorted(set(LEVEL_TILESET.values())):
        name = tileset + ".DAT"
        yield tileset + "_tiles", to_image(render_tileset(name, read(name)), palettes[LEVEL1], scale)

    for level_index, level in enumerate(LEVEL_ORDER):
        tiles = read(LEVEL_TILESET[level] + ".DAT")
        pixels = render_level(read(level + ".MAP"), tiles)
        yield level, to_image(pixels, level_palette(prg, level_index), 1)


def main():
    parser = argparse.ArgumentParser(description="Render Zynaps (Atari ST) assets to PNG")
    parser.add_argument("disk", nargs="?", help="directory with the extracted disk files")
    parser.add_argument("out", nargs="?", help="output directory for the PNGs")
    parser.add_argument("--prg", help="path to ZYNAPS17.PRG (default: <disk>/../ZYNAPS17.PRG)")
    parser.add_argument("--scale", type=int, default=1, help="nearest-neighbour zoom for small art (default 1)")
    parser.add_argument("--scan-palettes", action="store_true", help="list ST palettes found in the PRG and exit")
    args = parser.parse_args()

    prg_path = args.prg
    if prg_path is None:
        if args.disk is None:
            parser.error("need --prg or a disk directory")
        prg_path = os.path.join(args.disk, os.pardir, "ZYNAPS17.PRG")
    prg = open(prg_path, "rb").read()

    if args.scan_palettes:
        for offset, word_count in scan_palettes(prg):
            print("0x%05x  %3d words (%.2f palettes)" % (offset, word_count, word_count / PALETTE_ENTRIES))
            for entry in range(word_count // PALETTE_ENTRIES):
                base = offset + entry * PALETTE_BYTES
                # Every word in a span is a valid 0x0RGB colour, so three hex digits print it whole.
                colours = " ".join("%03x" % word for word in read_palette_words(prg, base))
                print("    0x%05x  %s" % (base, colours))
        return

    if not args.disk or not args.out:
        parser.error("need both a disk directory and an output directory")
    os.makedirs(args.out, exist_ok=True)
    for name, image in build_assets(args.disk, prg, args.scale):
        path = os.path.join(args.out, name + ".png")
        image.save(path)
        print("%-16s %s" % (name, image.size))


if __name__ == "__main__":
    main()
