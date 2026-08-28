#!/usr/bin/env python3
"""Generate src/assets_data.c: the engine's wall textures and billboard sprites.

BY DEFAULT THE SHIPPED ART IS EMITTED - the indexed PNGs art/ produces, read out
of art/out/native/ and converted by pipeline/stepix.  `--placeholder` emits the
procedural stand-ins instead; they are kept because they are synthetic art with
known contents, which is what a generator test wants, and because they are the
fallback if the art tree is ever unavailable.

Both modes produce the SAME C layout, only different texels:

  wall textures  64x64 bytes, COLUMN MAJOR (texel (u, v) at u * 64 + v), in the
                 slot include/map.h's TEX_* id names, palette indices only from
                 the wall-legal set (DESIGN 3).
  sprites        64x64 bytes, column major, SPRITE_TRANSPARENT as the colour
                 key, plus a per-column (first, last) opaque-row span table.

The procedural path is deterministic - a fixed LCG, no randomness from the host
- so the golden frames are reproducible either way.

    python3 tools/mkassets.py > src/assets_data.c
    python3 tools/mkassets.py --placeholder > src/assets_data.c
"""
import argparse
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "tools"))
sys.path.insert(0, str(_ROOT / "art"))
sys.path.insert(0, str(_ROOT / "pipeline"))
import numpy                                                    # noqa: E402
from PIL import Image                                           # noqa: E402
from consts import CONST                                        # noqa: E402
import palette as art_palette                                   # noqa: E402
# pipeline/stepix is the reference implementation of both on-disk layouts.  Both
# modes go through it so the shipped art and the placeholders are laid out by the
# same code, not by two lookalikes.
import pixelio as art_pixelio                                   # noqa: E402
from stepix import sprite as stepix_sprite                      # noqa: E402
from stepix import texture as stepix_texture                    # noqa: E402
from stepix.palette import check_index_range                    # noqa: E402

assert stepix_texture.TEXTURE_DIM == CONST["TEX_DIM"]
assert stepix_sprite.SPAN_EMPTY_FIRST == CONST["SPRITE_SPAN_EMPTY_FIRST"]
assert stepix_sprite.SPAN_EMPTY_LAST == CONST["SPRITE_SPAN_EMPTY_LAST"]

# Read, never restated: a generator that disagrees with the engine about the
# texture size or the colour key produces art that is wrong in a way nothing
# reports.
TEX_DIM = CONST["TEX_DIM"]
SPRITE_TRANSPARENT = CONST["SPRITE_TRANSPARENT"]
SPAN_EMPTY_FIRST = CONST["SPRITE_SPAN_EMPTY_FIRST"]
SPAN_EMPTY_LAST = CONST["SPRITE_SPAN_EMPTY_LAST"]
WALL_TEXTURE_SLOTS = CONST["WALL_TEXTURE_MAX"] + 1              # slot 0 is the far-fill sentinel
ENT_TYPE_COUNT = CONST["ENT_TYPE_COUNT"]

#: Where the art scripts write the shipped, native-resolution indexed PNGs.  Read from
#: art/pixelio.py, which is the module that puts them there.
DEFAULT_ART_DIR = pathlib.Path(art_pixelio.NATIVE_DIR)
PNG_INDEXED_MODE = "P"                  # the pixel VALUES are palette indices
PALETTE_SIZE = art_palette.PALETTE_SIZE
PALETTE_RGB_BYTES = PALETTE_SIZE * 3

# The palette's roles, from the art department's own definition.  RIM and ALERT
# are RESERVED: no wall texture may contain them, which is what makes a 1px
# white rim-light readable against every wall at every depth.
VOID = art_palette.VOID
CYAN_1, CYAN_2, CYAN_3, CYAN_4, CYAN_5 = art_palette.CYAN_RAMP
MAG_1, MAG_2, MAG_3, MAG_4, MAG_5 = art_palette.MAGENTA_RAMP
DATA, RIM, ALERT, INTEGRITY, GRID = (art_palette.DATA, art_palette.RIM,
                                     art_palette.ALERT, art_palette.INTEGRITY,
                                     art_palette.GRID)
WALL_FORBIDDEN = frozenset(art_palette.SPRITE_ONLY)

assert SPRITE_TRANSPARENT == art_palette.TRANSPARENT_INDEX, \
    "the engine's colour key and the art's disagree"

LCG_MULTIPLIER = 1103515245
LCG_INCREMENT = 12345
LCG_MODULUS = 1 << 31


class Lcg:
    """The one source of pattern noise, so the art is byte-reproducible."""

    def __init__(self, seed):
        self.state = seed

    def next(self, limit):
        self.state = (self.state * LCG_MULTIPLIER + LCG_INCREMENT) % LCG_MODULUS
        return (self.state >> 16) % limit


def blank(colour):
    return [[colour] * TEX_DIM for _ in range(TEX_DIM)]      # [v][u]


def circuit_lattice():
    """Traces on a dark board, with a node pad where two traces cross."""
    px = blank(CYAN_5)
    trace_pitch = 16
    for v in range(TEX_DIM):
        for u in range(TEX_DIM):
            on_h = v % trace_pitch == 0
            on_v = u % trace_pitch == 0
            if on_h and on_v:
                px[v][u] = CYAN_1
            elif on_h or on_v:
                px[v][u] = CYAN_3
            elif (u % trace_pitch) < 2 and (v % trace_pitch) > 8:
                px[v][u] = CYAN_4
    return px


def hex_mesh():
    """A honeycomb outline: two offset rows of flat-topped cells."""
    px = blank(CYAN_5)
    cell_h, cell_w = 16, 16
    for v in range(TEX_DIM):
        row = v // cell_h
        shift = (cell_w // 2) if (row & 1) else 0
        for u in range(TEX_DIM):
            local_u = (u + shift) % cell_w
            local_v = v % cell_h
            edge = local_v in (0, 1) or local_u in (0, 1)
            slope = abs(local_u - local_v) < 2 and local_v < cell_h // 2
            if edge:
                px[v][u] = CYAN_3
            elif slope:
                px[v][u] = CYAN_4
    return px


def glyph_column():
    """Columns of dead text: fixed-pitch blocks in two brightnesses."""
    px = blank(CYAN_5)
    rng = Lcg(0x51A7)
    glyph_h, glyph_w = 8, 6
    for v in range(0, TEX_DIM, glyph_h):
        for u in range(0, TEX_DIM, glyph_w):
            width = 2 + rng.next(3)
            shade = CYAN_2 if rng.next(4) else CYAN_1
            for dv in range(glyph_h - 3):
                for du in range(width):
                    if u + du < TEX_DIM and v + dv < TEX_DIM:
                        px[v + dv][u + du] = shade
    return px


def bus_trunk():
    """Fat vertical conduits with a lit edge on the left of each."""
    px = blank(CYAN_5)
    pitch = 8
    for v in range(TEX_DIM):
        for u in range(TEX_DIM):
            local = u % pitch
            if local == 0:
                px[v][u] = CYAN_2
            elif local < 5:
                px[v][u] = CYAN_4
            elif local == 5:
                px[v][u] = VOID
    return px


def firewall_chevron():
    """Dark magenta chevrons: this wall is ICE, not infrastructure."""
    px = blank(MAG_5)
    pitch = 12
    for v in range(TEX_DIM):
        for u in range(TEX_DIM):
            fold = abs((u % (pitch * 2)) - pitch)
            band = (v + fold) % pitch
            if band < 3:
                px[v][u] = MAG_3
            elif band < 6:
                px[v][u] = MAG_4
    return px


def corrupt_noise():
    """A sector that was written badly: banded noise over the two dark ramps."""
    px = blank(VOID)
    rng = Lcg(0xBAD0)
    palette = (VOID, CYAN_5, CYAN_4, MAG_4, MAG_5)
    for v in range(TEX_DIM):
        run_colour = palette[rng.next(len(palette))]
        u = 0
        while u < TEX_DIM:
            run = 1 + rng.next(7)
            for du in range(run):
                if u + du < TEX_DIM:
                    px[v][u + du] = run_colour
            u += run
            run_colour = palette[rng.next(len(palette))]
    return px


def anchor_pylon():
    """A lit central pillar, so an anchor reads as a target from any angle."""
    px = blank(VOID)
    for v in range(TEX_DIM):
        for u in range(TEX_DIM):
            offset = abs(u - TEX_DIM // 2)
            if offset < 6:
                px[v][u] = CYAN_1 if (v % 8) < 6 else CYAN_3
            elif offset < 12:
                px[v][u] = CYAN_4
            elif offset < 20:
                px[v][u] = CYAN_5
    return px


def exit_plating():
    """Heavy plates with green trim: the way out is always marked, and green
    is the exit lamp in art/palette.py's role table."""
    px = blank(CYAN_4)
    plate = 16
    for v in range(TEX_DIM):
        for u in range(TEX_DIM):
            if v % plate < 2 or u % plate < 2:
                px[v][u] = CYAN_5
            elif (v % plate) in (2, 3) and (u % plate) > 3:
                px[v][u] = INTEGRITY
            elif (v % plate) < 9:
                px[v][u] = CYAN_3
    return px


def gate_panel(trim_colour):
    """A door leaf: horizontal slats with a bright centre seam."""
    px = blank(CYAN_5)
    slat = 8
    for v in range(TEX_DIM):
        for u in range(TEX_DIM):
            if abs(u - TEX_DIM // 2) < 2:
                px[v][u] = CYAN_1
            elif v % slat < 5:
                px[v][u] = CYAN_4
            elif v % slat == 6:
                px[v][u] = trim_colour
    return px


#: One row per wall texture slot: the include/map.h id NAME - so the slot number
#: is the engine's and is never restated here - the art/out/native file that
#: fills it, and the procedural stand-in `--placeholder` uses instead.  The C
#: symbol is the id name lowered, which is what both modes emit.
WALL_TEXTURE_ART = (
    ("TEX_CIRCUIT_LATTICE",  "tex_circuit_lattice",  circuit_lattice),
    ("TEX_HEX_MESH",         "tex_hex_mesh",         hex_mesh),
    ("TEX_GLYPH_COLUMN",     "tex_glyph_column",     glyph_column),
    ("TEX_BUS_TRUNK",        "tex_bus_trunk",        bus_trunk),
    ("TEX_FIREWALL_CHEVRON", "tex_firewall_chevron", firewall_chevron),
    ("TEX_CORRUPT_NOISE",    "tex_corrupted_sector", corrupt_noise),
    ("TEX_ANCHOR_PYLON",     "tex_anchor_pylon",     anchor_pylon),
    ("TEX_EXIT_PLATING",     "tex_exit_gate",        exit_plating),
    # DESIGN 10 draws every plain and exit door with 9 and every locked, sealed
    # or corrupted one with 10; the art calls those two leaves door and
    # sector_key_panel.
    ("TEX_GATE_PANEL",       "tex_door",             lambda: gate_panel(CYAN_2)),
    ("TEX_LOCKED_PANEL",     "tex_sector_key_panel", lambda: gate_panel(MAG_3)),
)

def billboard(body_colour, core_colour, radius_x, radius_y, centre_v):
    """A rim-lit lozenge.  DESIGN 3 mandates a 1-pixel white rim on every
    silhouette edge; the placeholder honours it so the contrast harness has
    something real to measure.

    A 64x64 sprite frame is exactly one cell tall, so it projects to the same
    height as a wall at the same distance.  An enemy fills the frame; a pickup
    is a 32x32 form sitting in the frame's lower half, which is where a thing
    on the floor belongs.
    """
    px = blank(SPRITE_TRANSPARENT)
    centre_u = TEX_DIM / 2.0
    for v in range(TEX_DIM):
        for u in range(TEX_DIM):
            dx = (u + 0.5 - centre_u) / radius_x
            dy = (v + 0.5 - centre_v) / radius_y
            r = dx * dx + dy * dy
            if r <= 1.0:
                px[v][u] = core_colour if r < 0.35 else body_colour
            elif r <= 1.18:
                px[v][u] = RIM
    return px


ENEMY_RADIUS_U, ENEMY_RADIUS_V, ENEMY_CENTRE_V = 18.0, 26.0, 32.0
PICKUP_RADIUS_U, PICKUP_RADIUS_V, PICKUP_CENTRE_V = 11.0, 11.0, 48.0

#: `--placeholder` sprites: one billboard for anything hostile, one for anything
#: lying on the floor.  Distinguishing them further is the art's job, not this
#: generator's.
PLACEHOLDER_SPRITES = (
    ("spr_enemy", lambda: billboard(MAG_2, MAG_1,
                                    ENEMY_RADIUS_U, ENEMY_RADIUS_V, ENEMY_CENTRE_V),
     ("ENT_WATCHDOG", "ENT_SENTRY", "ENT_TRACER", "ENT_BLACK_ICE")),
    ("spr_pickup", lambda: billboard(DATA, INTEGRITY,
                                     PICKUP_RADIUS_U, PICKUP_RADIUS_V, PICKUP_CENTRE_V),
     ("ENT_TOKEN_ALPHA", "ENT_TOKEN_BETA", "ENT_TOKEN_GAMMA",
      "ENT_CYCLES_SMALL", "ENT_CYCLES_LARGE",
      "ENT_INTEGRITY_SMALL", "ENT_INTEGRITY_LARGE",
      "ENT_SCRUBBER", "ENT_DATA_CACHE")),
)

#: The shipped art: one row per DISTINCT billboard, naming the art/out/native
#: file and every entity type drawn with it.
#:
#: ENT_ANCHOR is deliberately absent from both tables: an anchor pylon IS its
#: wall texture (cell value 7), not a billboard, so its slot stays NULL.  The
#: three tokens share one card and the small/large cycles and integrity pickups
#: share one icon, because DESIGN 10 separates those by value and message, not
#: by silhouette - a distant heal that looks like a different object is a
#: misread, and the engine dedups shared assets by pointer anyway.
ART_SPRITES = (
    ("spr_watchdog",        ("ENT_WATCHDOG",)),
    ("spr_sentry",          ("ENT_SENTRY",)),
    ("spr_tracer",          ("ENT_TRACER",)),
    ("spr_black_ice",       ("ENT_BLACK_ICE",)),
    ("spr_access_token",    ("ENT_TOKEN_ALPHA", "ENT_TOKEN_BETA", "ENT_TOKEN_GAMMA")),
    ("spr_cycles_cell",     ("ENT_CYCLES_SMALL", "ENT_CYCLES_LARGE")),
    ("spr_integrity_patch", ("ENT_INTEGRITY_SMALL", "ENT_INTEGRITY_LARGE")),
    ("spr_trace_scrubber",  ("ENT_SCRUBBER",)),
    ("spr_data_particle",   ("ENT_DATA_CACHE",)),
)


def entity_type_names():
    """The EntityType enumerators in value order - include/level.h's own list.

    Read rather than restated: a type inserted in the middle of that enum has to
    move every row of g_entity_sprites with it, and a hand-kept copy here would
    silently draw every later type as the wrong thing.
    """
    by_value = {value: name for name, value in CONST.items()
                if name.startswith("ENT_") and name != "ENT_TYPE_COUNT"}
    missing = [value for value in range(ENT_TYPE_COUNT) if value not in by_value]
    assert not missing, "include/level.h has no EntityType enumerator for %s" % missing
    return [by_value[value] for value in range(ENT_TYPE_COUNT)]


ENTITY_ORDER = entity_type_names()

BYTES_PER_LINE = 32


# ---- reading the shipped art ---------------------------------------------------


def load_indexed_png(path):
    """A mode-P PNG as [v][u] palette indices, on art/palette.py's exact colours.

    The palette is asserted, never converted.  These pixel values ARE palette
    indices: if the PNG were written against a different sixteen colours the
    bytes would still load, still compile and draw the wrong hues, which is the
    one failure a colour-index pipeline cannot see downstream.
    """
    # Named before it is opened: the Makefile's guard only rebuilds the art tree when the whole
    # directory is missing, so one deleted file otherwise arrives as a bare FileNotFoundError
    # traceback rather than as this tool saying which asset it wanted.
    if not path.is_file():
        raise SystemExit("mkassets: %s is missing; run `make -C art` to rebuild the art tree" % path)
    image = Image.open(path)
    if image.mode != PNG_INDEXED_MODE:
        raise SystemExit("mkassets: %s is mode %r, expected %r (its pixel values must be "
                         "palette indices, not colours)" % (path, image.mode, PNG_INDEXED_MODE))
    png_palette = list(image.getpalette() or [])[:PALETTE_RGB_BYTES]
    if png_palette != art_palette.pil_palette():
        raise SystemExit("mkassets: %s does not carry art/palette.py's sixteen colours" % path)

    # check_index_range, not a comparison of our own: it is the pipeline's one statement of
    # what a legal index is, and it runs BEFORE the uint8 cast that would wrap 256 to 0.
    pixels = numpy.asarray(image)
    check_index_range(pixels, str(path))
    return pixels.astype(numpy.uint8, copy=False)


def load_wall_texture(art_dir, stem):
    """One wall texture, which the art authors at exactly the engine's tile size."""
    pixels = load_indexed_png(art_dir / (stem + ".png"))
    if pixels.shape != (TEX_DIM, TEX_DIM):
        raise SystemExit("mkassets: wall texture %s is %dx%d, expected %dx%d"
                         % (stem, pixels.shape[1], pixels.shape[0], TEX_DIM, TEX_DIM))
    return pixels


def load_sprite_frame(art_dir, stem):
    """One billboard, seated on the floor of a TEX_DIM square frame.

    A 64x64 enemy fills the frame - DESIGN 17.1's ENEMY_HEIGHT_CELLS of 1.0, the
    same height as a wall at the same distance.  Smaller art is a pickup, which
    PICKUP_HEIGHT_CELLS puts in the LOWER HALF of the cell so it reads as an
    object on the floor and never competes with an enemy silhouette for the same
    screen rows.  One rule covers both, because the projection centres the frame
    in the window and so the frame's bottom row IS the floor: centre the art
    horizontally, sit it on that bottom row, key out everything else.
    """
    art = load_indexed_png(art_dir / (stem + ".png"))
    height, width = art.shape
    if height > TEX_DIM or width > TEX_DIM:
        raise SystemExit("mkassets: sprite %s is %dx%d, larger than the %dx%d frame"
                         % (stem, width, height, TEX_DIM, TEX_DIM))
    frame = numpy.full((TEX_DIM, TEX_DIM), SPRITE_TRANSPARENT, dtype=numpy.uint8)
    left = (TEX_DIM - width) // 2
    frame[TEX_DIM - height:, left:left + width] = art
    return frame


# ---- the two asset sets ---------------------------------------------------------


def art_assets(art_dir):
    """The shipped art: (wall rows, sprite rows).

    A wall row carries its own TEX_* id name, so the slot table is built from the row rather
    than from this table's position - the sprite rows carry their entity types the same way.
    """
    walls = [(id_name, id_name.lower(), stem + ".png", load_wall_texture(art_dir, stem))
             for id_name, stem, _ in WALL_TEXTURE_ART]
    sprites = [(stem, stem + ".png", load_sprite_frame(art_dir, stem), entities)
               for stem, entities in ART_SPRITES]
    return walls, sprites


def placeholder_assets():
    """The procedural stand-ins, in the same shape as `art_assets`."""
    walls = [(id_name, id_name.lower(), "procedural", numpy.array(build(), dtype=numpy.uint8))
             for id_name, _, build in WALL_TEXTURE_ART]
    sprites = [(symbol, "procedural", numpy.array(build(), dtype=numpy.uint8), entities)
               for symbol, build, entities in PLACEHOLDER_SPRITES]
    return walls, sprites


# ---- the on-disk layouts, from the pipeline -------------------------------------


def to_column_major(pixels):
    """[v][u] indices -> the engine's column-major bytes, via the pipeline itself."""
    return list(stepix_texture.to_column_major(pixels))


def spans(pixels):
    """First and last opaque texel row of each column, from the pipeline.

    An empty column is the canonical (SPAN_EMPTY_FIRST, SPAN_EMPTY_LAST) pair;
    the drawer's skip test is simply first > last.
    """
    flat = stepix_sprite.column_spans(pixels, SPRITE_TRANSPARENT)
    return [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]


# ---- emission --------------------------------------------------------------------

FILE_BANNER = """/*
 * assets_data.c - GENERATED by tools/mkassets.py.  Do not edit.
 *
%s */
#include "render.h"
#include "sprite.h"

"""
# No "/*" anywhere in a banner body: the C compiler warns about one nested in a
# block comment, so the art directory is named without a glob.
ART_BANNER_BODY = (" * The shipped art: the indexed PNGs in art/out/native, read as palette\n"
                   " * indices and laid out by pipeline/stepix - the same code the .PAK uses.\n")
PLACEHOLDER_BANNER_BODY = (" * Procedural stand-in art (tools/mkassets.py --placeholder): synthetic\n"
                           " * texels with known contents, for tests that need them and as the\n"
                           " * fallback when the art tree is unavailable.\n")


def emit_bytes(out, name, data):
    out.write("static const uint8_t %s[TEX_SIZE] = {\n" % name)
    for start in range(0, len(data), BYTES_PER_LINE):
        out.write("    " + "".join("%d," % v for v in data[start:start + BYTES_PER_LINE]) + "\n")
    out.write("};\n\n")


def emit_wall_textures(out, walls):
    """Every texture, then the slot table indexed by include/map.h's TEX_* id."""
    slots = [None] * WALL_TEXTURE_SLOTS
    for id_name, symbol, _, pixels in walls:
        illegal = set(numpy.unique(pixels).tolist()) & WALL_FORBIDDEN
        if illegal:
            raise SystemExit("mkassets: %s uses sprite-only palette indices %s"
                             % (symbol, sorted(illegal)))
        emit_bytes(out, symbol, to_column_major(pixels))
        slots[CONST[id_name]] = symbol

    out.write("const uint8_t *g_wall_textures[WALL_TEXTURE_MAX + 1] = {\n"
              "    0,   /* slot 0 is the far-fill sentinel, never a texture */\n")
    for symbol in slots[1:]:
        out.write("    %s,\n" % (symbol if symbol else "0"))
    out.write("};\n\n")


SPANS_PER_LINE = 8


def emit_sprites(out, sprites):
    """Every billboard and its span table, then g_entity_sprites."""
    asset_of_entity = {}
    for symbol, _, pixels, entities in sprites:
        emit_bytes(out, symbol, to_column_major(pixels))
        table = spans(pixels)
        out.write("static const SpriteSpan %s_spans[TEX_DIM] = {\n" % symbol)
        for start in range(0, TEX_DIM, SPANS_PER_LINE):
            chunk = table[start:start + SPANS_PER_LINE]
            out.write("    " + " ".join("{0x%02x,0x%02x}," % pair for pair in chunk) + "\n")
        out.write("};\n\n")
        out.write("static const SpriteAsset %s_asset = { %s, %s_spans };\n\n"
                  % (symbol, symbol, symbol))
        for entity in entities:
            asset_of_entity[entity] = symbol

    out.write("const SpriteAsset *g_entity_sprites[ENT_TYPE_COUNT] = {\n")
    for entity in ENTITY_ORDER:
        symbol = asset_of_entity.get(entity)
        out.write("    /* %-20s */ %s,\n"
                  % (entity, ("&%s_asset" % symbol) if symbol else "0"))
    out.write("};\n")


LEDGER_ROW = "  %-8s %-22s %-24s %7d\n"


def print_ledger(walls, sprites, out):
    """What was emitted, where it came from and what it costs, in bytes."""
    texel_bytes = TEX_DIM * TEX_DIM
    span_bytes = TEX_DIM * 2
    total = 0
    out.write("mkassets ledger\n")
    out.write("  %-8s %-22s %-24s %7s\n" % ("kind", "symbol", "source", "bytes"))
    for _, symbol, source, _ in walls:
        out.write(LEDGER_ROW % ("texture", symbol, source, texel_bytes))
        total += texel_bytes
    for symbol, source, _, entities in sprites:
        out.write(LEDGER_ROW % ("sprite", symbol, source, texel_bytes + span_bytes))
        out.write("  %-8s %-22s %s\n" % ("", "", ", ".join(entities)))
        total += texel_bytes + span_bytes
    out.write("  %-8s %-22s %-24s %7d\n"
              % ("total", "%d textures" % len(walls), "%d sprites" % len(sprites), total))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--art", type=pathlib.Path, default=DEFAULT_ART_DIR,
                        help="directory of indexed art PNGs (default: %(default)s)")
    parser.add_argument("--placeholder", action="store_true",
                        help="emit the procedural stand-ins instead of the shipped art")
    args = parser.parse_args()

    walls, sprites = placeholder_assets() if args.placeholder else art_assets(args.art)
    out = sys.stdout
    out.write(FILE_BANNER % (PLACEHOLDER_BANNER_BODY if args.placeholder else ART_BANNER_BODY))
    emit_wall_textures(out, walls)
    emit_sprites(out, sprites)
    print_ledger(walls, sprites, sys.stderr)


if __name__ == "__main__":
    main()
