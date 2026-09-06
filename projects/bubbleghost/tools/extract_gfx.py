#!/usr/bin/env python3
"""Decode Bubble Ghost's (Atari ST, ERE Informatique / Accolade 1988) artwork into PNGs.

Usage:
  python3 projects/bubbleghost/tools/extract_gfx.py [OUT_DIR]

OUT_DIR defaults to `projects/bubbleghost/out/assets` (gitignored). Reads only the game's own data
files under `projects/bubbleghost/bin/` — never GHOST.PRG — and writes:

  title.png          GHOST.PRE assembled into the 320x192 title screen
  palette_title.txt  GHOST.PRE's 16 colour words, as $0RGB and as 8-bit RGB
  dat_tiles.png      GHOST.DAT's 360 tiles on one sheet, in the file's own palette
  palette_dat.txt    GHOST.DAT's 16 colour words

THE FORMAT, confirmed by reading the result back as a coherent picture. The layout hunt behind it,
and what the sheet turns out to show, are in notes/assets_survey.md rather than here.

Both files are a whole number of 32x32-PIXEL TILES followed by a 32-byte $0RGB palette, back to
back with no header, index table or gap. A tile is 512 bytes: 32 rows of one word-interleaved group
pair — the plain low-res ST layout of `tools/st_pixels.py`, applied to a 32-pixel-wide bitmap
rather than to a 320-pixel screen. GHOST.PRE holds 60 tiles, and they are the title screen in
ROW-MAJOR order, 10 across by 6 down = 320x192 (8 rows short of a full ST screen). GHOST.DAT holds
360, the game's whole tile bank.

Nothing in either file marks transparency — a masked group would be five words wide and the tiles
would not be 512 bytes — so the drawing code in GHOST.PRG treats index 0 as transparent or builds a
mask at run time. Which tile index means what, and how the 35 rooms are built out of them, lives in
that code too: once it gives the room maps, a `render_room()` fed a list of tile indices is all that
is needed to draw them. The sheet's 20-column layout is this tool's choice, not one the game has.
"""

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(PROJECT_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from st_pixels import (  # noqa: E402  (needs the path above)
    PALETTE_BYTES, decode_planar, image_bytes, is_st_colour_word, read_palette_words, palette_rgb,
    split_rows, st_word_to_rgb, tile_sheet, to_rgb_image)

BIN_DIR = os.path.join(PROJECT_DIR, "bin")
DEFAULT_OUT_DIR = os.path.join(PROJECT_DIR, "out", "assets")

# The format both files are in: square tiles, then the palette.
TILE_PIXELS = 32
TILE_BYTES = image_bytes(TILE_PIXELS, TILE_PIXELS)  # 512

# GHOST.PRE's 60 tiles, laid out row-major, are the title screen.
TITLE_TILES_ACROSS = 10
TITLE_TILES_DOWN = 6

# How wide to draw the GHOST.DAT survey sheet. This tool's choice, not the game's.
SHEET_TILES_ACROSS = 20
SHEET_GAP_PIXELS = 1  # a one-pixel rule between tiles, so a tile's own edge is visible


def read_binary(name):
    with open(os.path.join(BIN_DIR, name), "rb") as handle:
        return handle.read()


def split_palette(data, name):
    """`data` -> (tile bytes, the 16 colour words that follow them).

    The palette's position is the format's own invariant, so a file that is not a whole number of
    tiles plus one palette is not this format and must fail here rather than decode as a picture
    with a corner missing.
    """
    tile_bytes = len(data) - PALETTE_BYTES
    if tile_bytes <= 0 or tile_bytes % TILE_BYTES:
        raise SystemExit("%s is %d bytes, which is not N tiles of %d plus a %d-byte palette"
                         % (name, len(data), TILE_BYTES, PALETTE_BYTES))
    words = read_palette_words(data, tile_bytes)
    if not all(is_st_colour_word(word) for word in words):
        raise SystemExit("%s: the 16 words at %#x are not $0RGB colours, so the palette is not "
                         "there and the tile count is wrong" % (name, tile_bytes))
    return data[:tile_bytes], words


def decode_tiles(tile_data):
    """The tile stream -> a list of 32x32 tiles, each a list of 32 rows of colour indices."""
    rows = len(tile_data) // (TILE_BYTES // TILE_PIXELS)
    return split_rows(decode_planar(tile_data, TILE_PIXELS, rows), TILE_PIXELS)


def write_palette_text(path, words, source):
    lines = ["# %s: 16 ST colour words ($0RGB, 3 bits per channel) at the end of the file" % source,
             "# index  word   r,g,b (8-bit)"]
    for index, word in enumerate(words):
        lines.append("%5d  $%04x  %3d,%3d,%3d" % ((index, word) + st_word_to_rgb(word)))
    with open(path, "w") as handle:
        handle.write("\n".join(lines) + "\n")


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)

    pre_tiles, pre_palette = split_palette(read_binary("GHOST.PRE"), "GHOST.PRE")
    title = decode_tiles(pre_tiles)
    if len(title) != TITLE_TILES_ACROSS * TITLE_TILES_DOWN:
        raise SystemExit("GHOST.PRE holds %d tiles, not the %d a %dx%d title screen needs"
                         % (len(title), TITLE_TILES_ACROSS * TITLE_TILES_DOWN,
                            TITLE_TILES_ACROSS, TITLE_TILES_DOWN))
    to_rgb_image(tile_sheet(title, TITLE_TILES_ACROSS), palette_rgb(pre_palette)).save(
        os.path.join(out_dir, "title.png"))
    write_palette_text(os.path.join(out_dir, "palette_title.txt"), pre_palette, "GHOST.PRE")

    dat_tiles, dat_palette = split_palette(read_binary("GHOST.DAT"), "GHOST.DAT")
    sheet = tile_sheet(decode_tiles(dat_tiles), SHEET_TILES_ACROSS, SHEET_GAP_PIXELS)
    to_rgb_image(sheet, palette_rgb(dat_palette)).save(os.path.join(out_dir, "dat_tiles.png"))
    write_palette_text(os.path.join(out_dir, "palette_dat.txt"), dat_palette, "GHOST.DAT")

    print("%d title tiles, %d data tiles -> %s"
          % (len(title), len(dat_tiles) // TILE_BYTES, out_dir))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT_DIR)
