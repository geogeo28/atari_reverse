#!/usr/bin/env python3
"""Flying Shark (Firebird 1988, Atari ST) — the disk assets, decoded to PNGs.

    python3 projects/flyingshark/tools/extract_assets.py [OUT_DIR]

OUT_DIR defaults to `projects/flyingshark/out/assets` (gitignored); the inputs are the files
`tools/unpack_dist.py` split out of `bin/FILES/FRD` into `bin/disk/A/`, plus `bin/FLYSHARK.PRG`
itself for the palettes and the per-level bank assignment.

Every format below is read out of the game's own code — `notes/assets_survey.md` names the routine
that pins each field, and `out/assets/README.txt` (written by this script) says what each output is.

  title.png            FLY_SHK.NEO: a 128-byte NEOchrome header carrying its own palette, then one
                       whole 320x200 low-res screen.
  palettes/*.png       The three palettes in the .PRG's DATA plus the title picture's own, as
                       swatch strips; palettes.txt has the colour words.
  sprites/*.png        SPRITES.CRU: a 256-record directory of 20 bytes, then one masked, word-
                       interleaved bitmap per record. Masked pixels come out as alpha 0.
  tiles/bank_X.png     HSC_X.DAT: 64 tiles of 32x32, four word-interleaved planes, no mask.
  levels/level_N.png   LEVELn.MAP read from its END (the map scrolls upward), each cell a base tile
                       plus an overlay tile drawn with colour 0 transparent, over the four HSC
                       banks that level loads.
  manifest.txt         The counts, and the record of the consistency checks below.
  survey.txt           MODULE.BAK's PRG header and SPRITES.CRU's first words, as text.

The manifest is not a report of what happened to decode — every structural claim is CHECKED and a
mismatch raises: each sprite bitmap must end exactly where the next one begins (and the last on the
final byte of the file), a bank must be exactly 64 whole tiles, a map header's row count must
account for the whole file, and no map cell may index past the four resident banks.

Needs Pillow for the PNGs; `survey.txt` and the checks do not.
"""
import collections
import os
import struct
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(PROJECT_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
sys.path.insert(0, os.path.join(PROJECT_DIR, "tools"))

from st_pixels import (  # noqa: E402  (needs the paths above)
    PALETTE_ENTRIES, PIXELS_PER_WORD, TRANSPARENT, decode_planar, image_bytes, palette_rgb,
    read_palette_words, st_word_to_rgb, tile_sheet, to_rgb_image, to_rgba_image)
from unpack_dist import (  # noqa: E402
    DEPACKED_GAME, DISK_SUBDIR, GAME_DATA_SUBDIR, MODULE_NAME, NEO_HEADER_BYTES, NEO_NAME,
    PRG_HEADER_BYTES, prg_header)

DEFAULT_OUT_SUBDIR = os.path.join("out", "assets")
SPRITES_SUBDIR = "sprites"
TILES_SUBDIR = "tiles"
LEVELS_SUBDIR = "levels"
PALETTES_SUBDIR = "palettes"
MANIFEST_TXT = "manifest.txt"
README_TXT = "README.txt"

# --- reaching into FLYSHARK.PRG's DATA ----------------------------------------------------------
# The disassembly and names.txt address the image at this base, so a Ghidra address is that many
# bytes into the loaded image and PRG_HEADER_BYTES further into the file.
PRG_LOAD_BASE = 0x10000
# The three palettes DATA holds, by the XBIOS Setpalette wrapper that installs each.
PALETTE_GAME_ADDR = 0x16294        # 0x111be, called at every level start — the in-play palette
PALETTE_FRONTEND_ADDR = 0x16274    # 0x111d6, called once by init_load_assets before the title loads
PALETTE_BLACK_ADDR = 0x162B4       # 0x111a6, sixteen zero words, to blank between phases
# `level_asset_digit_table`: five ASCII digits per level, the four HSC banks then the LEVELn map.
LEVEL_DIGITS_ADDR = 0x162D4
LEVEL_COUNT = 5
BANK_SLOTS = 4
DIGITS_PER_LEVEL = BANK_SLOTS + 1

# --- the NEOchrome title ------------------------------------------------------------------------
# flag word, resolution word, then the palette. The filename and animation fields are unused here.
NEO_PALETTE_OFFSET = 4
SCREEN_WIDTH = 320
SCREEN_ROWS = 200
TITLE_PNG = "title.png"

# --- palettes -----------------------------------------------------------------------------------
PALETTES_TXT = "palettes.txt"
PALETTE_PNG = "%s.png"
SWATCH_PIXELS = 24  # one colour's square in a swatch strip

# --- SPRITES.CRU --------------------------------------------------------------------------------
SPRITES_NAME = "SPRITES.CRU"
# A record is a be32 data offset then eight words: width class, rows-1, the draw offset the blitter
# adds to the entity position (0x144fe/0x144c2), the further offset the hit test adds on top of it
# and then the hit box's size (0x116b8..0x116e8).
SPRITE_RECORD_FORMAT = ">IHH6h"
SPRITE_RECORD_BYTES = struct.calcsize(SPRITE_RECORD_FORMAT)     # 20
SPRITE_RECORDS = 256
SPRITE_DIRECTORY_BYTES = SPRITE_RECORDS * SPRITE_RECORD_BYTES   # 0x1400, also the first pixel byte
# One 16-pixel group of a masked bitmap is five words: the mask then the four planes. The width
# class is the group count minus one, so class n spans (n+1) groups of ten bytes.
SPRITE_GROUP_BYTES = 10
SPRITE_NO_BITMAP = 0xFFFF   # rows-1 of a record that carries a hit box and no pixels at all
SPRITE_SPARE = 0            # data offset of a record the game never uses
SPRITE_PNG = "sprite_%03d.png"
SPRITE_SHEET_PNG = "sprites_sheet.png"
SPRITE_INDEX_TSV = "sprites_index.tsv"
SPRITE_SHEET_ACROSS = 16
SPRITE_SHEET_GAP = 1
SPRITE_INDEX_COLUMNS = ("id", "class", "width", "rows", "draw_dx", "draw_dy", "hit_dx", "hit_dy",
                        "hit_w", "hit_h", "data_off", "bytes", "sheet_cell")

# --- HSC_n.DAT ----------------------------------------------------------------------------------
BANK_NAME = "HSC_%s.DAT"
BANK_DIGITS = "0123456789ABC"
TILE_PIXELS = 32
TILE_BYTES = image_bytes(TILE_PIXELS, TILE_PIXELS)              # 512: 32 rows of 4 plane words
TILES_PER_BANK = 64
BANK_BYTES = TILES_PER_BANK * TILE_BYTES                        # 0x8000, the loader's slot size
RESIDENT_TILES = BANK_SLOTS * TILES_PER_BANK                    # 256: one byte addresses them all
BANK_PNG = "bank_%s.png"
BANK_SHEET_ACROSS = 8
BANK_SHEET_GAP = 1

# --- LEVELn.MAP ---------------------------------------------------------------------------------
MAP_NAME = "LEVEL%s.MAP"
MAP_HEADER_FORMAT = ">2H"                                       # columns, rows
MAP_HEADER_BYTES = struct.calcsize(MAP_HEADER_FORMAT)
MAP_CELL_BYTES = 2                                              # base tile index, overlay index
OVERLAY_NONE = 0
LEVEL_PNG = "level_%d.png"
LEVEL_PREVIEW_PNG = "level_%d_preview.png"
PREVIEW_DIVISOR = 4

# --- survey.txt ---------------------------------------------------------------------------------
SURVEY_TXT = "survey.txt"
SURVEY_WORDS = 64
WORDS_PER_SURVEY_LINE = 16

SpriteRecord = collections.namedtuple(
    "SpriteRecord",
    "index data_off width_class rows width span draw_dx draw_dy hit_dx hit_dy hit_w hit_h")

README_TEXT = """Flying Shark — extracted assets
Written by projects/flyingshark/tools/extract_assets.py; see notes/assets_survey.md for the
byte-level evidence behind every format. Everything here is regenerated from bin/, so it is safe
to delete the whole folder.

title.png              FLY_SHK.NEO, 320x200, in the palette out of its own NEOchrome header.
palettes/              One PNG swatch strip per palette, sixteen colours left to right:
  palette_game_16294     the in-play palette (installed at every level start) — the one the tiles
                         and the sprites below are painted in.
  palette_frontend_16274 installed once before the title picture loads.
  palette_black_162b4    sixteen zero words, used to blank the screen between phases.
  palette_title_neo      the title picture's own, out of the .NEO header.
palettes.txt           The same four as colour words and 8-bit RGB.
sprites/sprite_NNN.png One PNG per SPRITES.CRU record that has pixels; NNN is the record index the
                       game itself uses (sprite_header_tbl entry). Masked pixels are alpha 0.
sprites_sheet.png      All of them on one sheet, row-major, 16 across, in the same order; the
                       `sheet_cell` column of the index below gives each sprite's cell.
sprites_index.tsv      Every used record: id, width class, size, the draw offset the blitter adds
                       to the entity position, the extra offset and size of the collision box, and
                       where the pixels live. Records with rows=0 are hit-box-only: they exist so
                       sprite_hit_test has a box for something drawn out of several other sprites,
                       and their class/width columns are the file's own bytes, addressing nothing.
tiles/bank_X.png       HSC_X.DAT as an 8x8 sheet of 32x32 tiles, tile 0 top left, in the in-play
                       palette. Four banks are resident at once, so a map's tile index is
                       slot*64 + tile — the slots a level uses are in manifest.txt.
levels/level_N.png     The whole of LEVELn.MAP rendered 320 pixels wide, THE LEVEL'S START AT THE
                       TOP: the file is read backwards because the map scrolls upward past the
                       player. Each cell is a base tile with its overlay tile drawn over it,
                       colour 0 transparent.
levels/level_N_preview.png  The same image at 1/%d scale, for looking at a whole level at once.
manifest.txt           Counts, per-level geometry, and the consistency checks the extractor makes.
survey.txt             SPRITES.CRU's first words and MODULE.BAK's PRG header, as text.
""" % PREVIEW_DIVISOR


def read(path):
    with open(path, "rb") as handle:
        return handle.read()


def data_dir(bin_dir):
    return os.path.join(bin_dir, DISK_SUBDIR, GAME_DATA_SUBDIR)


def make_dir(out_dir, *parts):
    path = os.path.join(out_dir, *parts)
    os.makedirs(path, exist_ok=True)
    return path


# --- FLYSHARK.PRG's DATA ------------------------------------------------------------------------

def prg_offset(address):
    """A Ghidra/runtime address to its offset in the .PRG file."""
    return address - PRG_LOAD_BASE + PRG_HEADER_BYTES


def palette_words_at(prg, address):
    return read_palette_words(prg, prg_offset(address))


def level_digits(prg, level):
    """The five ASCII digits `level_asset_digit_table` holds for one level (0-based)."""
    at = prg_offset(LEVEL_DIGITS_ADDR) + level * DIGITS_PER_LEVEL
    return prg[at:at + DIGITS_PER_LEVEL].decode("ascii")


# --- the title ------------------------------------------------------------------------------------

def write_title(picture, out_dir):
    palette = palette_rgb(read_palette_words(picture, NEO_PALETTE_OFFSET))
    rows = decode_planar(picture, SCREEN_WIDTH, SCREEN_ROWS, offset=NEO_HEADER_BYTES)
    to_rgb_image(rows, palette).save(os.path.join(out_dir, TITLE_PNG))
    return [f"{TITLE_PNG}: {SCREEN_WIDTH}x{SCREEN_ROWS} from {NEO_NAME}"]


# --- palettes ---------------------------------------------------------------------------------

def write_palette_swatch(words, path):
    """Sixteen colours as one strip of squares, so a palette can be eyeballed next to the art."""
    row = [index for index in range(PALETTE_ENTRIES) for _ in range(SWATCH_PIXELS)]
    to_rgb_image([row] * SWATCH_PIXELS, palette_rgb(words)).save(path)


def palette_text(name, words):
    lines = [f"{name}\n"]
    lines += [f"  {index:2d}  ${word:04x}  rgb{st_word_to_rgb(word)}\n"
              for index, word in enumerate(words)]
    return lines + ["\n"]


def write_palettes(palettes, out_dir):
    """`palettes` is (name, words) in the order the manifest should list them."""
    swatch_dir = make_dir(out_dir, PALETTES_SUBDIR)
    text = []
    for name, words in palettes:
        write_palette_swatch(words, os.path.join(swatch_dir, PALETTE_PNG % name))
        text += palette_text(name, words)
    with open(os.path.join(out_dir, PALETTES_TXT), "w") as handle:
        handle.writelines(text)
    return [f"{PALETTES_SUBDIR}/: " + ", ".join(name for name, _ in palettes),
            f"{PALETTES_TXT}: the same {len(palettes)} palettes as colour words"]


# --- SPRITES.CRU ----------------------------------------------------------------------------------

def sprite_records(cru):
    """The directory's used records, in index order. A zero data offset is a spare."""
    records = []
    for index in range(SPRITE_RECORDS):
        at = index * SPRITE_RECORD_BYTES
        fields = struct.unpack(SPRITE_RECORD_FORMAT, cru[at:at + SPRITE_RECORD_BYTES])
        data_off, width_class, rows_minus_one = fields[:3]
        if data_off == SPRITE_SPARE:
            continue
        rows = 0 if rows_minus_one == SPRITE_NO_BITMAP else rows_minus_one + 1
        stride = (width_class + 1) * SPRITE_GROUP_BYTES
        records.append(SpriteRecord(index, data_off, width_class, rows,
                                    (width_class + 1) * PIXELS_PER_WORD, rows * stride, *fields[3:]))
    return records


def check_sprite_spans(records, file_bytes):
    """Bitmap n must end exactly on bitmap n+1's first byte, and the last on the file's last byte.

    This is the whole format's load-bearing arithmetic: it pins the row stride the width class
    implies, the +1 on the row count, and the record order all at once.
    """
    bitmaps = [record for record in records if record.rows]
    if bitmaps[0].data_off != SPRITE_DIRECTORY_BYTES:
        raise ValueError(f"{SPRITES_NAME}: the pixels start at {bitmaps[0].data_off:#x}, not on the "
                         f"{SPRITE_DIRECTORY_BYTES:#x} byte the {SPRITE_RECORDS}-record directory ends on")
    for record, following in zip(bitmaps, bitmaps[1:]):
        end = record.data_off + record.span
        if end != following.data_off:
            raise ValueError(f"{SPRITES_NAME}: record {record.index} is {record.width}x{record.rows} at "
                             f"{record.data_off:#x}, so it ends at {end:#x} — but record {following.index} "
                             f"starts at {following.data_off:#x}")
    end = bitmaps[-1].data_off + bitmaps[-1].span
    if end != file_bytes:
        raise ValueError(f"{SPRITES_NAME}: the last bitmap (record {bitmaps[-1].index}) ends at {end:#x}, "
                         f"the file is {file_bytes:#x} bytes")
    return bitmaps


def padded_cell(pixels, width, rows):
    """One sprite in a fixed cell, the slack left transparent, so the sheet can be a plain grid."""
    cell = [row + [TRANSPARENT] * (width - len(row)) for row in pixels]
    return cell + [[TRANSPARENT] * width for _ in range(rows - len(pixels))]


def sprite_index_lines(records, sheet_cells):
    lines = ["\t".join(SPRITE_INDEX_COLUMNS) + "\n"]
    for record in records:
        lines.append("\t".join(str(field) for field in (
            record.index, record.width_class, record.width, record.rows,
            record.draw_dx, record.draw_dy, record.hit_dx, record.hit_dy, record.hit_w, record.hit_h,
            f"{record.data_off:#x}", record.span, sheet_cells.get(record.index, ""))) + "\n")
    return lines


def write_sprites(cru, records, palette, out_dir):
    sprite_dir = make_dir(out_dir, SPRITES_SUBDIR)
    bitmaps = check_sprite_spans(records, len(cru))
    cell_width = max(record.width for record in bitmaps)
    cell_rows = max(record.rows for record in bitmaps)
    cells, sheet_cells = [], {}
    for record in bitmaps:
        pixels = decode_planar(cru, record.width, record.rows, offset=record.data_off, masked=True)
        to_rgba_image(pixels, palette).save(os.path.join(sprite_dir, SPRITE_PNG % record.index))
        sheet_cells[record.index] = len(cells)
        cells.append(padded_cell(pixels, cell_width, cell_rows))

    sheet = tile_sheet(cells, SPRITE_SHEET_ACROSS, SPRITE_SHEET_GAP)
    to_rgba_image(sheet, palette).save(os.path.join(out_dir, SPRITE_SHEET_PNG))
    with open(os.path.join(out_dir, SPRITE_INDEX_TSV), "w") as handle:
        handle.writelines(sprite_index_lines(records, sheet_cells))

    classes = collections.Counter(record.width_class for record in bitmaps)
    hitbox_only = [record.index for record in records if not record.rows]
    return [f"{SPRITES_NAME}: {len(records)} records used of {SPRITE_RECORDS}, "
            f"{len(bitmaps)} rendered, {len(hitbox_only)} hit-box-only",
            "  width classes " + " ".join(f"{key}:{classes[key]}" for key in sorted(classes))
            + f", widest {cell_width} px, tallest {cell_rows} rows",
            "  hit-box-only records " + " ".join(str(index) for index in hitbox_only),
            f"  every bitmap span checked: {SPRITE_DIRECTORY_BYTES:#x}..{len(cru):#x} accounted for",
            f"  {SPRITE_SHEET_PNG} is {SPRITE_SHEET_ACROSS} cells of {cell_width}x{cell_rows} across"]


# --- HSC_n.DAT --------------------------------------------------------------------------------

def decode_bank(bank, name):
    if len(bank) != BANK_BYTES:
        raise ValueError(f"{name}: {len(bank)} bytes, not the {TILES_PER_BANK} whole {TILE_BYTES}-byte "
                         f"tiles ({BANK_BYTES}) the loader's slot holds")
    return [decode_planar(bank, TILE_PIXELS, TILE_PIXELS, offset=index * TILE_BYTES)
            for index in range(TILES_PER_BANK)]


def bank_tiles(source, digit):
    name = BANK_NAME % digit
    return decode_bank(read(os.path.join(source, name)), name)


def write_tile_sheets(source, palette, out_dir):
    tiles_dir = make_dir(out_dir, TILES_SUBDIR)
    for digit in BANK_DIGITS:
        sheet = tile_sheet(bank_tiles(source, digit), BANK_SHEET_ACROSS, BANK_SHEET_GAP)
        to_rgb_image(sheet, palette).save(os.path.join(tiles_dir, BANK_PNG % digit))
    return [f"{TILES_SUBDIR}/: {len(BANK_DIGITS)} banks (HSC_{BANK_DIGITS[0]}..{BANK_DIGITS[-1]}) of "
            f"{TILES_PER_BANK} tiles of {TILE_PIXELS}x{TILE_PIXELS}, {BANK_SHEET_ACROSS} across"]


# --- LEVELn.MAP -------------------------------------------------------------------------------

def read_map(data, name):
    """The header's geometry, checked against the file's length and the resident tile count."""
    columns, rows = struct.unpack(MAP_HEADER_FORMAT, data[:MAP_HEADER_BYTES])
    expected = MAP_HEADER_BYTES + rows * columns * MAP_CELL_BYTES
    if expected != len(data):
        raise ValueError(f"{name}: the header says {columns}x{rows} cells = {expected} bytes, "
                         f"the file is {len(data)}")
    # A cell index is one byte, so this cannot fire on today's files: it pins the OTHER half of the
    # claim — that the four banks a level loads are the whole of a map's tile space.
    highest = max(data[MAP_HEADER_BYTES:])
    if highest >= RESIDENT_TILES:
        raise ValueError(f"{name}: tile index {highest} is past the {RESIDENT_TILES} tiles the "
                         f"{BANK_SLOTS} resident banks hold")
    return columns, rows


def with_overlay(base_tile, overlay_tile):
    """The overlay tile drawn over the base one with colour 0 transparent — the game's masked merge."""
    return [[over if over else under for under, over in zip(under_row, over_row)]
            for under_row, over_row in zip(base_tile, overlay_tile)]


def map_row_pixels(data, columns, map_row, tiles):
    """One row of cells -> TILE_PIXELS rows of pixels, `columns` tiles wide."""
    at = MAP_HEADER_BYTES + map_row * columns * MAP_CELL_BYTES
    pixel_rows = [[] for _ in range(TILE_PIXELS)]
    for column in range(columns):
        base, overlay = data[at + column * MAP_CELL_BYTES:at + (column + 1) * MAP_CELL_BYTES]
        tile = tiles[base] if overlay == OVERLAY_NONE else with_overlay(tiles[base], tiles[overlay])
        for y, row in enumerate(tile):
            pixel_rows[y] += row
    return pixel_rows


def render_map(data, columns, rows, tiles):
    """The whole map, the file's LAST row first: the map is walked backwards as the level scrolls."""
    pixels = []
    for map_row in reversed(range(rows)):
        pixels += map_row_pixels(data, columns, map_row, tiles)
    return pixels


def downscaled(pixel_rows, divisor):
    """Nearest-neighbour shrink in index space, so no new colour is ever invented."""
    return [row[::divisor] for row in pixel_rows[::divisor]]


def write_level(source, prg, level, palette, levels_dir):
    """One level: its four banks' tiles, its map rendered over them, and a preview. -> manifest line."""
    digits = level_digits(prg, level)
    tiles = []
    for digit in digits[:BANK_SLOTS]:
        tiles += bank_tiles(source, digit)
    name = MAP_NAME % digits[BANK_SLOTS]
    data = read(os.path.join(source, name))
    columns, rows = read_map(data, name)

    pixels = render_map(data, columns, rows, tiles)
    number = level + 1
    to_rgb_image(pixels, palette).save(os.path.join(levels_dir, LEVEL_PNG % number))
    preview = downscaled(pixels, PREVIEW_DIVISOR)
    to_rgb_image(preview, palette).save(os.path.join(levels_dir, LEVEL_PREVIEW_PNG % number))
    return (f"  level {number}: banks {' '.join(digits[:BANK_SLOTS])}  {name}  "
            f"{columns}x{rows} cells  {len(pixels[0])}x{len(pixels)} px  "
            f"preview {len(preview[0])}x{len(preview)}")


def write_levels(source, prg, palette, out_dir):
    levels_dir = make_dir(out_dir, LEVELS_SUBDIR)
    return [f"{LEVELS_SUBDIR}/: {LEVEL_COUNT} maps, rendered with the level's own four banks, "
            "the level's start at the top"] + \
           [write_level(source, prg, level, palette, levels_dir) for level in range(LEVEL_COUNT)]


# --- survey.txt -------------------------------------------------------------------------------

def survey_lines(sprites, module):
    """SPRITES.CRU's opening words and MODULE.BAK's PRG header, as text for the notes to quote."""
    words = struct.unpack(f">{SURVEY_WORDS}H", sprites[:SURVEY_WORDS * 2])
    lines = [f"{SPRITES_NAME}: {len(sprites):,} bytes\n",
             f"  first {SURVEY_WORDS} words:\n"]
    for at in range(0, SURVEY_WORDS, WORDS_PER_SURVEY_LINE):
        chunk = words[at:at + WORDS_PER_SURVEY_LINE]
        lines.append(f"    {at * 2:#06x}  " + " ".join(f"{word:04x}" for word in chunk) + "\n")

    magic, text, data, bss, symbols, reserved, flags, absflag = prg_header(module, MODULE_NAME)
    lines += [f"\n{MODULE_NAME}: {len(module):,} bytes\n",
              f"  magic {magic:#06x}  text {text:#x}  data {data:#x}  bss {bss:#x}  sym {symbols:#x}\n",
              f"  reserved {reserved:#x}  flags {flags:#x}  absflag {absflag:#06x}"
              f"{'  (position-independent: no relocation table)' if absflag else ''}\n"]
    return lines


# --- the run ------------------------------------------------------------------------------------

def extract(bin_dir, out_dir, report=print):
    os.makedirs(out_dir, exist_ok=True)
    source = data_dir(bin_dir)
    if not os.path.isdir(source):
        raise SystemExit(f"{source} is not laid out — run tools/unpack_dist.py first")

    prg = read(os.path.join(bin_dir, DEPACKED_GAME))
    picture = read(os.path.join(source, NEO_NAME))
    cru = read(os.path.join(source, SPRITES_NAME))
    game_palette = palette_rgb(palette_words_at(prg, PALETTE_GAME_ADDR))
    palettes = (("palette_game_16294", palette_words_at(prg, PALETTE_GAME_ADDR)),
                ("palette_frontend_16274", palette_words_at(prg, PALETTE_FRONTEND_ADDR)),
                ("palette_black_162b4", palette_words_at(prg, PALETTE_BLACK_ADDR)),
                ("palette_title_neo", read_palette_words(picture, NEO_PALETTE_OFFSET)))

    report(f"{source} -> {out_dir}")
    manifest = [f"Flying Shark — assets decoded from {source} and {DEPACKED_GAME}", ""]
    manifest += write_title(picture, out_dir)
    manifest += write_palettes(palettes, out_dir)
    manifest += write_sprites(cru, sprite_records(cru), game_palette, out_dir)
    manifest += write_tile_sheets(source, game_palette, out_dir)
    manifest += write_levels(source, prg, game_palette, out_dir)

    survey = survey_lines(cru, read(os.path.join(source, MODULE_NAME)))
    with open(os.path.join(out_dir, SURVEY_TXT), "w") as handle:
        handle.writelines(survey)
    manifest.append(f"{SURVEY_TXT}: {SPRITES_NAME}'s first words + {MODULE_NAME}'s PRG header")

    with open(os.path.join(out_dir, MANIFEST_TXT), "w") as handle:
        handle.writelines(line + "\n" for line in manifest)
    with open(os.path.join(out_dir, README_TXT), "w") as handle:
        handle.write(README_TEXT)
    report("\n".join("  " + line for line in manifest))


def main():
    bin_dir = os.path.join(PROJECT_DIR, "bin")
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PROJECT_DIR, DEFAULT_OUT_SUBDIR)
    extract(bin_dir, out_dir)


if __name__ == "__main__":
    main()
