#!/usr/bin/env python3
"""Decode Wonder Boy in Monsterland's (Atari ST) artwork into PNGs.

Usage:
  python3 projects/wonderboy/tools/extract_gfx.py [OUT_DIR]

OUT_DIR defaults to `projects/wonderboy/out/gfx`. Reads only the game's own files under
`projects/wonderboy/bin/` and the .RAD depacker at `tools/depack_rad.py`; writes:

  sprites/sprite_NNN.png   one RGBA sprite per SPRITES.CRU descriptor (transparent where masked)
  sprites_sheet.png        every sprite on one grid
  sprites_manifest.txt     index, file offset, size and anchor of every descriptor
  tiles_sheet.png          the 661 background tiles of TILEDATA.RAD
  screens/*.png            the full 320x200 screens (TITLESCR / CREDITS / DATADISK)
  palettes.png, .txt       the eight in-PRG palettes, as swatch strips and as $0RGB words
  font_sheet.png           the text font, the message-box frame glyphs and the digit glyphs
  hud_sheet.png            the record bitmaps, meter cells, HUD slot cells and panel frames

EVERY PIXEL FORMAT HERE IS THE ST's LOW-RES ONE: four bitplanes, a pixel's 4-bit colour index
gathered one bit per plane (plane 0 = bit 0), and colours as $0RGB words with 3 bits per channel.
What differs between assets is only how the planes are INTERLEAVED, and there are two shapes:

  word-planar  a row is groups of four big-endian 16-bit plane words, 16 pixels per group. Screens,
               tiles and every HUD bitmap are this.
  byte-planar  a row is four consecutive plane BYTES, so the cell is 8 pixels wide. The font, the
               digit glyphs and the meter cells are this — see text_plot_glyph in recreate/src/text.c
               and plot_column in recreate/src/hud.c, which walk exactly these two layouts.

Sprites add a fifth word per group, a MASK, ahead of the four plane words: a set mask bit keeps the
background, i.e. that pixel is transparent.

Addresses of in-PRG assets are RUNTIME addresses, as used by names.txt and recreate/include/
wonderboy.h — the authority for every table and count below. PRG_RUNTIME_TO_FILE converts.
"""

import os
import sys
from collections import namedtuple

try:
    from PIL import Image
except ImportError:
    raise SystemExit("this tool needs Pillow: run it with the atari_reverse conda env's python "
                     "(the interpreter this workspace supports), or `pip install pillow`")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(PROJECT_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import depack_rad  # noqa: E402  (needs the path above)

BIN_DIR = os.path.join(PROJECT_DIR, "bin")
DEFAULT_OUT_DIR = os.path.join(PROJECT_DIR, "out", "gfx")

# ---- the ST's pixel and colour model ----------------------------------------------------------

PLANES = 4
PIXELS_PER_PLANE_WORD = 16
PIXELS_PER_PLANE_BYTE = 8
BYTES_PER_WORD = 2                        # every plane word and palette entry is one be16
PALETTE_ENTRIES = 16
ST_CHANNEL_BITS = 3                       # $0RGB: three bits per channel...
ST_CHANNEL_MAX = (1 << ST_CHANNEL_BITS) - 1   # ...so 7 is full brightness
EIGHT_BIT_MAX = 255


def word_planar_bytes(width_px, rows=1):
    """The bytes a word-planar bitmap of this shape occupies — the one source for every stride.

    Defined here rather than beside decode_word_planar because the constants below are built
    from it at import time.
    """
    return rows * (width_px // PIXELS_PER_PLANE_WORD) * PLANES * BYTES_PER_WORD

# ---- SPRITES.CRU ------------------------------------------------------------------------------

SPRITES_FILE = os.path.join(BIN_DIR, "disk2", "SPRITES.CRU")
# The stored form of the .RAD container: packed length == unpacked length == filesize - 64, and the
# body is verbatim, so there is nothing to depack (depack_rad refuses it with GUARD_STORED_FORM).
CRU_BODY_BASE = 64
CRU_PACKED_LENGTH_OFFSET = 0              # be32; in the stored form it equals the unpacked length
CRU_PALETTE_OFFSET = 0x20                 # inside the 64-byte header, ahead of the body
SPRITE_DESC_BYTES = 20
SPRITE_DESC_COUNT = 482                   # == first descriptor's data pointer / SPRITE_DESC_BYTES
SPRITE_DESC_DATA_PTR = 0                  # be32, relative to CRU_BODY_BASE
SPRITE_DESC_WIDTH_CLASS = 4               # u8: width = (class + 1) * 16 px
SPRITE_DESC_HEIGHT_MINUS_1 = 5            # u8
SPRITE_DESC_ANCHOR_X = 8                  # be16 pair; recorded in the manifest, never applied
SPRITE_DESC_ANCHOR_Y = 10
SPRITE_WIDTH_UNIT = 16
SPRITE_WORDS_PER_GROUP = 1 + PLANES       # mask, plane0, plane1, plane2, plane3
SPRITE_GROUP_BYTES = SPRITE_WORDS_PER_GROUP * BYTES_PER_WORD
SPRITE_SHEET_COLUMNS = 16
SPRITE_NON_EMPTY_FLOOR = 0.90             # the share of descriptors that must hold visible pixels

# ---- TILEDATA.RAD -----------------------------------------------------------------------------

TILES_FILE = os.path.join(BIN_DIR, "disk2", "TILEDATA.RAD")
TILE_WIDTH = 16
TILE_ROWS = 16
TILE_BYTES = word_planar_bytes(TILE_WIDTH, TILE_ROWS)
TILE_SHEET_COLUMNS = 32

# ---- the full-screen .RAD files ---------------------------------------------------------------

SCREEN_FILES = (
    ("titlescr", os.path.join(BIN_DIR, "disk1", "TITLESCR.RAD")),
    ("credits", os.path.join(BIN_DIR, "disk1", "CREDITS.RAD")),
    ("datadisk", os.path.join(BIN_DIR, "disk2", "DATADISK.RAD")),
)
SCREEN_HEADER_BYTES = 128
SCREEN_PALETTE_OFFSET = 4                 # 16 be16 words inside that header
SCREEN_WIDTH = 320
SCREEN_HEIGHT = 200
SCREEN_LINE_BYTES = word_planar_bytes(SCREEN_WIDTH)   # 160
SCREEN_UNPACKED_BYTES = SCREEN_HEADER_BYTES + SCREEN_LINE_BYTES * SCREEN_HEIGHT

# ---- AUTO/SWB.PRG -----------------------------------------------------------------------------

PRG_FILE = os.path.join(BIN_DIR, "disk1", "AUTO", "SWB.PRG")
# The startup stub relocates itself, so a runtime address is this much above its file offset.
PRG_LOAD_BASE = 0x3F8                     # must match load_base in recreate/project.toml
PRG_HEADER_BYTES = 0x1C                   # the GEMDOS .PRG header, ahead of the image
PRG_RUNTIME_TO_FILE = PRG_LOAD_BASE - PRG_HEADER_BYTES

PRG_PALETTE_TABLE = 0xFC46
PRG_PALETTE_COUNT = 8
PRG_PALETTE_BYTES = PALETTE_ENTRIES * BYTES_PER_WORD
PRG_PALETTE_FOR_BITMAPS = 0               # no in-image evidence picks a palette per bitmap
PALETTE_SWATCH_PX = 24

# Byte-planar cells: 8 rows of four plane bytes, so 32 bytes and 8 px wide (WB_DIGIT_GLYPH_LEN).
GLYPH_ROWS = 8
GLYPH_BYTES = GLYPH_ROWS * PLANES
GLYPH_SHEET_SCALE = 3                     # these cells are 8x8; nearest-neighbour up for eyeballing

GlyphGroup = namedtuple("GlyphGroup", "name runtime count columns")
# Counts are wonderboy.h's: WB_TEXT_GLYPH_TABLE holds ASCII $20..$7f, WB_TEXT_FRAME_GLYPH_COUNT is 8,
# and the "two" digit tables at $1447c/$145bc are ONE 20-glyph block ($145bc is ten glyphs into it).
TEXT_GLYPH_GROUPS = (
    GlyphGroup("text font $12c9c (ASCII $20..$7f)", 0x12C9C, 96, 16),
    GlyphGroup("message-box frame glyphs $12b9c", 0x12B9C, 8, 8),
    GlyphGroup("digit glyphs $1447c (default 0-9, then the $145bc alternates)", 0x1447C, 20, 10),
)
METER_CELL_GROUP = GlyphGroup("meter cells $146fc (full, 3/4, 2/4, 1/4, empty)", 0x146FC, 5, 5)

# The HUD sheet, in the order its groups are stacked. The word-planar ones' entry stride is
# word_planar_bytes(width_px, rows) — which is WB_RECORD_BITMAP_LEN, WB_HUD_CELL_BYTES * ROWS and
# WB_PANEL_FRAME_LEN respectively. Every count comes from names.txt / wonderboy.h. METER_CELL_GROUP
# sits in this list because it belongs on the sheet, not because it shares their layout: it is the
# one byte-planar group here, so the renderer below dispatches on the group's type.
BitmapGroup = namedtuple("BitmapGroup", "name runtime count width_px rows columns")
HUD_GROUPS = (
    # record_bitmap_table: $400 apart and running exactly up to text_frame_glyphs at $12b9c.
    BitmapGroup("record bitmaps $1079c", 0x1079C, 9, 64, 32, 5),
    METER_CELL_GROUP,
    # hud_slot_cells: fourteen consecutive $e0 cells, ending exactly at panel_frame_bitmaps.
    BitmapGroup("HUD slot cells $1479c", 0x1479C, 14, 32, 14, 7),
    # panel_frame_bitmaps: panel_frame_index cycles 0..$c, and 13 * $300 ends at snd_stub_00.
    BitmapGroup("panel frames $153dc", 0x153DC, 13, 48, 32, 7),
)

# ---- sheet composition ------------------------------------------------------------------------

SHEET_GAP = 2
SHEET_BACKGROUND = (32, 32, 40, 255)
GROUP_GAP = 10


def be16(data, offset):
    return (data[offset] << 8) | data[offset + 1]


def be32(data, offset):
    return int.from_bytes(data[offset:offset + 4], "big")


def st_word_to_rgb(word):
    """One $0RGB palette word to 8-bit RGB."""
    channels = ((word >> 8) & ST_CHANNEL_MAX, (word >> 4) & ST_CHANNEL_MAX, word & ST_CHANNEL_MAX)
    return tuple(channel * EIGHT_BIT_MAX // ST_CHANNEL_MAX for channel in channels)


def read_palette(data, offset):
    words = [be16(data, offset + i * BYTES_PER_WORD) for i in range(PALETTE_ENTRIES)]
    return words, [st_word_to_rgb(word) for word in words]


def gather_planes(plane_values, bit_count):
    """Four same-width plane fields to `bit_count` colour indices, leftmost pixel first."""
    pixels = []
    for bit in reversed(range(bit_count)):
        index = 0
        for plane, value in enumerate(plane_values):
            index |= ((value >> bit) & 1) << plane
        pixels.append(index)
    return pixels


def plane_group_offsets(offset, width_px, rows, group_bytes):
    """One list of 16-pixel group offsets per row — the walk screens, tiles and sprites share."""
    groups = width_px // PIXELS_PER_PLANE_WORD
    return [[offset + (row * groups + group) * group_bytes for group in range(groups)]
            for row in range(rows)]


def decode_word_planar(data, offset, width_px, rows,
                       group_bytes=PLANES * BYTES_PER_WORD, plane_word_at=0):
    """Rows of colour indices from the interleaved-plane-word layout (screens, tiles, HUD).

    Sprites walk the same rows through a wider group: `group_bytes` is the stride from one group
    to the next, `plane_word_at` where plane 0 sits inside it (past the mask word).
    """
    out = []
    for row_offsets in plane_group_offsets(offset, width_px, rows, group_bytes):
        pixels = []
        for at in row_offsets:
            planes = [be16(data, at + plane_word_at + plane * BYTES_PER_WORD)
                      for plane in range(PLANES)]
            pixels += gather_planes(planes, PIXELS_PER_PLANE_WORD)
        out.append(pixels)
    return out


def decode_byte_planar(data, offset, rows):
    """Rows of colour indices from the four-consecutive-plane-bytes layout (font, digits, meter)."""
    out = []
    for row in range(rows):
        at = offset + row * PLANES
        plane_bytes = data[at:at + PLANES]
        # A short slice would silently gather zeros, i.e. a blank glyph, from a wrong address or a
        # truncated file — the one failure this decoder cannot show you in the PNG.
        if len(plane_bytes) != PLANES:
            raise SystemExit("byte-planar row at %#x holds %d of the %d plane bytes: the address is "
                             "wrong or the file is truncated" % (at, len(plane_bytes), PLANES))
        out.append(gather_planes(plane_bytes, PIXELS_PER_PLANE_BYTE))
    return out


def decode_sprite(data, offset, width_px, rows):
    """Rows of (index, opaque) pairs. A SET mask bit keeps the background, so it means transparent."""
    index_rows = decode_word_planar(data, offset, width_px, rows,
                                    group_bytes=SPRITE_GROUP_BYTES, plane_word_at=BYTES_PER_WORD)
    mask_offsets = plane_group_offsets(offset, width_px, rows, SPRITE_GROUP_BYTES)
    out = []
    for indices, row_offsets in zip(index_rows, mask_offsets):
        opaque = []
        for at in row_offsets:
            opaque += [not bit for bit in gather_planes([be16(data, at)], PIXELS_PER_PLANE_WORD)]
        out.append(list(zip(indices, opaque)))
    return out


def image_from_indices(rows, palette):
    image = Image.new("RGB", (len(rows[0]), len(rows)))
    image.putdata([palette[index] for row in rows for index in row])
    return image


def image_from_masked_indices(rows, palette):
    image = Image.new("RGBA", (len(rows[0]), len(rows)))
    image.putdata([palette[index] + (EIGHT_BIT_MAX,) if opaque else (0, 0, 0, 0)
                   for row in rows for index, opaque in row])
    return image


def grid_sheet(images, columns):
    """Lay same-or-smaller images on a grid of cells the size of the largest, top-left aligned."""
    cell_width = max(image.width for image in images)
    cell_height = max(image.height for image in images)
    rows = -(-len(images) // columns)
    sheet = Image.new("RGBA", (columns * (cell_width + SHEET_GAP) + SHEET_GAP,
                               rows * (cell_height + SHEET_GAP) + SHEET_GAP), SHEET_BACKGROUND)
    for i, image in enumerate(images):
        x = SHEET_GAP + (i % columns) * (cell_width + SHEET_GAP)
        y = SHEET_GAP + (i // columns) * (cell_height + SHEET_GAP)
        # A masked images's own alpha, or `paste` would punch its transparent pixels through the
        # sheet's background too and the holes would read as white in most viewers.
        sheet.paste(image, (x, y), image if image.mode == "RGBA" else None)
    return sheet


def stack_sheets(sheets):
    width = max(sheet.width for sheet in sheets)
    height = sum(sheet.height for sheet in sheets) + GROUP_GAP * (len(sheets) - 1)
    stacked = Image.new("RGBA", (width, height), SHEET_BACKGROUND)
    y = 0
    for sheet in sheets:
        stacked.paste(sheet, (0, y))
        y += sheet.height + GROUP_GAP
    return stacked


def scaled(image, factor):
    return image.resize((image.width * factor, image.height * factor), Image.NEAREST)


def read_file(path):
    with open(path, "rb") as handle:
        return handle.read()


def depack(path):
    data = read_file(path)
    return depack_rad.depack(data, depack_rad.parse_header(data))


def prg_offset(runtime):
    return runtime - PRG_RUNTIME_TO_FILE


# ---- the extractors -----------------------------------------------------------------------------

SpriteEntry = namedtuple("SpriteEntry", "index data_offset width rows anchor_x anchor_y stride")


def read_sprite_descriptors(cru):
    # The descriptor table ends where the first body begins, which is what fixes SPRITE_DESC_COUNT.
    first_body = be32(cru, CRU_BODY_BASE + SPRITE_DESC_DATA_PTR)
    assert first_body == SPRITE_DESC_COUNT * SPRITE_DESC_BYTES, (
        "first descriptor's data pointer %#x implies %d descriptors of %d bytes, not %d"
        % (first_body, first_body // SPRITE_DESC_BYTES, SPRITE_DESC_BYTES, SPRITE_DESC_COUNT))
    entries = []
    for index in range(SPRITE_DESC_COUNT):
        at = CRU_BODY_BASE + index * SPRITE_DESC_BYTES
        width = (cru[at + SPRITE_DESC_WIDTH_CLASS] + 1) * SPRITE_WIDTH_UNIT
        rows = cru[at + SPRITE_DESC_HEIGHT_MINUS_1] + 1
        stride = width // SPRITE_WIDTH_UNIT * SPRITE_GROUP_BYTES
        entries.append(SpriteEntry(
            index=index,
            data_offset=CRU_BODY_BASE + be32(cru, at + SPRITE_DESC_DATA_PTR),
            width=width,
            rows=rows,
            anchor_x=be16(cru, at + SPRITE_DESC_ANCHOR_X),
            anchor_y=be16(cru, at + SPRITE_DESC_ANCHOR_Y),
            stride=stride,
        ))
    return entries


def check_sprite_layout(entries, file_size):
    """Sprite bodies should tile the rest of the file exactly. Return the mismatches, in order."""
    ordered = sorted(entries, key=lambda entry: entry.data_offset)
    violations = []
    for entry, following in zip(ordered, ordered[1:] + [None]):
        end = entry.data_offset + entry.stride * entry.rows
        expected = following.data_offset if following else file_size
        if end != expected:
            violations.append("sprite %d ends at %#x, next body starts at %#x"
                              % (entry.index, end, expected))
    return violations


def check_cru_stored_form(cru):
    """Refuse anything but the container's STORED form, whose body is the verbatim descriptors.

    docs/binary-formats.md pins the detection: packed == unpacked, which is exactly what
    depack_rad refuses with GUARD_STORED_FORM. A packed or truncated file would otherwise be
    read as descriptors and produce confident nonsense.
    """
    try:
        depack_rad.parse_header(cru)
        guard = None                      # it parsed as a real stream, so it is PACKED
    except depack_rad.DepackError as error:
        guard = error.guard
    body_bytes = be32(cru, CRU_PACKED_LENGTH_OFFSET)
    if guard != depack_rad.GUARD_STORED_FORM or body_bytes != len(cru) - CRU_BODY_BASE:
        raise SystemExit("%s is not the stored form of the .RAD container (packed == unpacked == "
                         "filesize - %d): it is packed or truncated" % (SPRITES_FILE, CRU_BODY_BASE))


def extract_sprites(out_dir, report):
    cru = read_file(SPRITES_FILE)
    check_cru_stored_form(cru)
    _, palette = read_palette(cru, CRU_PALETTE_OFFSET)
    entries = read_sprite_descriptors(cru)

    violations = check_sprite_layout(entries, len(cru))
    if violations:
        # main() never gets to print `report`, so the diagnostics have to go out from here.
        print("\n".join(report + ["  %s" % violation for violation in violations]),
              file=sys.stderr)
        raise SystemExit("sprite descriptor layout is not what the format claims: %d of %d "
                         "descriptors do not tile the body exactly"
                         % (len(violations), len(entries)))
    report.append("sprites: pointer/size self-check PASS (all %d descriptors tile the body exactly)"
                  % len(entries))

    sprite_dir = os.path.join(out_dir, "sprites")
    os.makedirs(sprite_dir, exist_ok=True)
    images, manifest, non_empty, fully_opaque = [], [], 0, 0
    for entry in entries:
        rows = decode_sprite(cru, entry.data_offset, entry.width, entry.rows)
        image = image_from_masked_indices(rows, palette)
        image.save(os.path.join(sprite_dir, "sprite_%03d.png" % entry.index))
        images.append(image)
        opacity = [opaque for row in rows for _, opaque in row]
        non_empty += any(opacity)
        fully_opaque += all(opacity)
        manifest.append("%3d  offset %#08x  %2dx%-3d  anchor %5d,%-5d"
                        % (entry.index, entry.data_offset, entry.width, entry.rows,
                           entry.anchor_x, entry.anchor_y))

    grid_sheet(images, SPRITE_SHEET_COLUMNS).save(os.path.join(out_dir, "sprites_sheet.png"))
    header = "index  file offset  WxH      anchor x,y\n"
    with open(os.path.join(out_dir, "sprites_manifest.txt"), "w") as handle:
        handle.write(header + "\n".join(manifest) + "\n")

    share = non_empty / len(entries)
    report.append("sprites: %d PNGs + sheet + manifest; %d non-empty (%.1f%%), %d with no "
                  "transparent pixel at all" % (len(entries), non_empty, share * 100, fully_opaque))
    if share < SPRITE_NON_EMPTY_FLOOR:
        raise SystemExit("only %.1f%% of sprites hold visible pixels — the decode is wrong" %
                         (share * 100))
    return len(entries)


def extract_tiles(out_dir, palette, report):
    tiles = depack(TILES_FILE)
    if len(tiles) % TILE_BYTES:
        raise SystemExit("TILEDATA.RAD unpacks to %d bytes, not a multiple of the %d-byte tile"
                         % (len(tiles), TILE_BYTES))
    count = len(tiles) // TILE_BYTES
    images = [image_from_indices(decode_word_planar(tiles, index * TILE_BYTES, TILE_WIDTH, TILE_ROWS),
                                 palette)
              for index in range(count)]
    grid_sheet(images, TILE_SHEET_COLUMNS).save(os.path.join(out_dir, "tiles_sheet.png"))
    report.append("tiles: %d tiles of %dx%d from %d unpacked bytes -> tiles_sheet.png"
                  % (count, TILE_WIDTH, TILE_ROWS, len(tiles)))
    return count


def extract_screens(out_dir, report):
    screen_dir = os.path.join(out_dir, "screens")
    os.makedirs(screen_dir, exist_ok=True)
    for name, path in SCREEN_FILES:
        screen = depack(path)
        if len(screen) != SCREEN_UNPACKED_BYTES:
            raise SystemExit("%s unpacks to %d bytes, not the %d of a header plus one ST screen"
                             % (name, len(screen), SCREEN_UNPACKED_BYTES))
        _, palette = read_palette(screen, SCREEN_PALETTE_OFFSET)
        rows = decode_word_planar(screen, SCREEN_HEADER_BYTES, SCREEN_WIDTH, SCREEN_HEIGHT)
        image = image_from_indices(rows, palette)
        image.save(os.path.join(screen_dir, "%s.png" % name))
        report.append("screen: %-9s %dx%d" % (name, image.width, image.height))
    return len(SCREEN_FILES)


def extract_palettes(prg, out_dir, report):
    words, swatches = [], []
    for entry in range(PRG_PALETTE_COUNT):
        entry_words, colours = read_palette(prg, prg_offset(PRG_PALETTE_TABLE) +
                                            entry * PRG_PALETTE_BYTES)
        words.append(entry_words)
        strip = Image.new("RGB", (PALETTE_ENTRIES, 1))
        strip.putdata(colours)
        swatches.append(scaled(strip, PALETTE_SWATCH_PX))
    grid_sheet(swatches, 1).save(os.path.join(out_dir, "palettes.png"))
    with open(os.path.join(out_dir, "palettes.txt"), "w") as handle:
        for entry, entry_words in enumerate(words):
            handle.write("%d  %s\n" % (entry, " ".join("%04x" % word for word in entry_words)))
    report.append("palettes: %d entries of %d colours -> palettes.png + palettes.txt"
                  % (PRG_PALETTE_COUNT, PALETTE_ENTRIES))
    return [st_word_to_rgb(word) for word in words[PRG_PALETTE_FOR_BITMAPS]]


def glyph_group_sheet(prg, group, palette):
    images = [image_from_indices(decode_byte_planar(prg, prg_offset(group.runtime) + i * GLYPH_BYTES,
                                                    GLYPH_ROWS), palette)
              for i in range(group.count)]
    return grid_sheet(images, group.columns)


def bitmap_group_sheet(prg, group, palette):
    stride = word_planar_bytes(group.width_px, group.rows)
    images = [image_from_indices(decode_word_planar(prg, prg_offset(group.runtime) + i * stride,
                                                    group.width_px, group.rows), palette)
              for i in range(group.count)]
    return grid_sheet(images, group.columns)


def extract_fonts(prg, out_dir, palette, report):
    sheets = [glyph_group_sheet(prg, group, palette) for group in TEXT_GLYPH_GROUPS]
    scaled(stack_sheets(sheets), GLYPH_SHEET_SCALE).save(os.path.join(out_dir, "font_sheet.png"))
    for group in TEXT_GLYPH_GROUPS:
        report.append("font:  %-3d glyphs of %dx%d  %s"
                      % (group.count, PIXELS_PER_PLANE_BYTE, GLYPH_ROWS, group.name))
    return sum(group.count for group in TEXT_GLYPH_GROUPS)


def hud_group_sheet(prg, group, palette):
    """A HUD group's sheet and its cell size — byte-planar meter cells, or word-planar bitmaps.

    The byte-planar cells are 8x8, far smaller than the bitmaps, so they go up by the same factor
    the font sheet uses to stay legible next to them.
    """
    if isinstance(group, GlyphGroup):
        return (scaled(glyph_group_sheet(prg, group, palette), GLYPH_SHEET_SCALE),
                PIXELS_PER_PLANE_BYTE, GLYPH_ROWS)
    return bitmap_group_sheet(prg, group, palette), group.width_px, group.rows


def extract_hud(prg, out_dir, palette, report):
    sheets = []
    for group in HUD_GROUPS:
        sheet, width_px, rows = hud_group_sheet(prg, group, palette)
        sheets.append(sheet)
        report.append("hud:   %-3d cells of %dx%d  %s" % (group.count, width_px, rows, group.name))
    stack_sheets(sheets).save(os.path.join(out_dir, "hud_sheet.png"))
    return sum(group.count for group in HUD_GROUPS)


def main(argv):
    out_dir = argv[1] if len(argv) > 1 else DEFAULT_OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    prg = read_file(PRG_FILE)
    report = []

    bitmap_palette = extract_palettes(prg, out_dir, report)
    counts = {
        "sprites": extract_sprites(out_dir, report),
        "tiles": extract_tiles(out_dir, bitmap_palette, report),
        "screens": extract_screens(out_dir, report),
        "glyphs": extract_fonts(prg, out_dir, bitmap_palette, report),
        "hud cells": extract_hud(prg, out_dir, bitmap_palette, report),
    }

    print("\n".join(report))
    print("\nwrote to %s" % out_dir)
    print("  " + ", ".join("%s: %d" % item for item in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
