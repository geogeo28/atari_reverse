#!/usr/bin/env python3
"""Generate src/assets_placeholder.c: procedural stand-in art for the engine.

The real art arrives from projects/blackice/art/ in exactly this format and
replaces these arrays without any code change:

  wall textures  64x64 bytes, COLUMN MAJOR (texel (u, v) at u * 64 + v),
                 palette indices only from the wall-legal set (DESIGN 3).
  sprites        64x64 bytes, column major, SPRITE_TRANSPARENT as the colour
                 key, plus a per-column (first, last) opaque-row span table.

Everything is deterministic - a fixed LCG, no randomness from the host - so the
golden frames are reproducible.

    python3 tools/mkassets.py > src/assets_placeholder.c
"""
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "tools"))
sys.path.insert(0, str(_ROOT / "art"))
sys.path.insert(0, str(_ROOT / "pipeline"))
import numpy                                                    # noqa: E402
from consts import CONST                                        # noqa: E402
import palette as art_palette                                   # noqa: E402
# pipeline/stepix is the reference implementation of both on-disk layouts.  The
# placeholders go through it so that when the real art replaces them the bytes
# are produced by the same code, not by a lookalike.
from stepix import sprite as stepix_sprite                      # noqa: E402
from stepix import texture as stepix_texture                    # noqa: E402

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


WALL_TEXTURES = [
    ("tex_circuit_lattice", circuit_lattice),
    ("tex_hex_mesh", hex_mesh),
    ("tex_glyph_column", glyph_column),
    ("tex_bus_trunk", bus_trunk),
    ("tex_firewall_chevron", firewall_chevron),
    ("tex_corrupt_noise", corrupt_noise),
    ("tex_anchor_pylon", anchor_pylon),
    ("tex_exit_plating", exit_plating),
    ("tex_gate_panel", lambda: gate_panel(CYAN_2)),
    ("tex_locked_panel", lambda: gate_panel(MAG_3)),
]


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

SPRITES = [
    ("spr_enemy", lambda: billboard(MAG_2, MAG_1,
                                    ENEMY_RADIUS_U, ENEMY_RADIUS_V, ENEMY_CENTRE_V)),
    ("spr_pickup", lambda: billboard(DATA, INTEGRITY,
                                     PICKUP_RADIUS_U, PICKUP_RADIUS_V, PICKUP_CENTRE_V)),
]

# Which placeholder billboard each entity type is drawn with.  Anchors are
# deliberately NULL: an anchor pylon IS its wall texture (cell value 7), not a
# billboard.  Sentries are floor entities standing in alcoves and are drawn.
ENTITY_SPRITE = {
    "ENT_WATCHDOG": "spr_enemy",
    "ENT_SENTRY": "spr_enemy",
    "ENT_TRACER": "spr_enemy",
    "ENT_BLACK_ICE": "spr_enemy",
    "ENT_TOKEN_ALPHA": "spr_pickup",
    "ENT_TOKEN_BETA": "spr_pickup",
    "ENT_TOKEN_GAMMA": "spr_pickup",
    "ENT_CYCLES_SMALL": "spr_pickup",
    "ENT_CYCLES_LARGE": "spr_pickup",
    "ENT_INTEGRITY_SMALL": "spr_pickup",
    "ENT_INTEGRITY_LARGE": "spr_pickup",
    "ENT_SCRUBBER": "spr_pickup",
    "ENT_DATA_CACHE": "spr_pickup",
}
ENTITY_ORDER = [
    "ENT_NONE", "ENT_WATCHDOG", "ENT_SENTRY", "ENT_TRACER", "ENT_BLACK_ICE",
    "ENT_ANCHOR", "ENT_TOKEN_ALPHA", "ENT_TOKEN_BETA", "ENT_TOKEN_GAMMA",
    "ENT_CYCLES_SMALL", "ENT_CYCLES_LARGE", "ENT_INTEGRITY_SMALL",
    "ENT_INTEGRITY_LARGE", "ENT_SCRUBBER", "ENT_DATA_CACHE",
]

BYTES_PER_LINE = 32


def to_column_major(px):
    """The pipeline's own transform, so the placeholders are laid out by the
    same code that will lay out the real art."""
    return list(stepix_texture.to_column_major(numpy.array(px, dtype=numpy.uint8)))


def spans(px):
    """First and last opaque texel row of each column, from the pipeline.

    An empty column is the canonical (SPAN_EMPTY_FIRST, SPAN_EMPTY_LAST) pair;
    the drawer's skip test is simply first > last.
    """
    flat = stepix_sprite.column_spans(numpy.array(px, dtype=numpy.uint8), SPRITE_TRANSPARENT)
    return [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]


def emit_bytes(out, name, data):
    out.write("static const uint8_t %s[TEX_SIZE] = {\n" % name)
    for start in range(0, len(data), BYTES_PER_LINE):
        out.write("    " + "".join("%d," % v for v in data[start:start + BYTES_PER_LINE]) + "\n")
    out.write("};\n\n")


def main():
    out = sys.stdout
    out.write("/*\n"
              " * assets_placeholder.c - GENERATED by tools/mkassets.py.  Do not edit.\n"
              " *\n"
              " * Procedural stand-in art so the engine renders something before the real\n"
              " * art arrives.  The real art uses exactly this format and replaces these\n"
              " * arrays with no code change.\n"
              " */\n"
              "#include \"render.h\"\n"
              "#include \"sprite.h\"\n\n")

    for name, build in WALL_TEXTURES:
        px = build()
        used = {v for row in px for v in row}
        illegal = used & WALL_FORBIDDEN
        assert not illegal, "%s uses sprite-only palette indices %s" % (name, sorted(illegal))
        emit_bytes(out, name, to_column_major(px))

    out.write("const uint8_t *g_wall_textures[WALL_TEXTURE_MAX + 1] = {\n"
              "    0,   /* slot 0 is the far-fill sentinel, never a texture */\n")
    for name, _ in WALL_TEXTURES:
        out.write("    %s,\n" % name)
    for _ in range(len(WALL_TEXTURES) + 1, WALL_TEXTURE_SLOTS):
        out.write("    0,\n")
    out.write("};\n\n")

    for name, build in SPRITES:
        px = build()
        emit_bytes(out, name, to_column_major(px))
        out.write("static const SpriteSpan %s_spans[TEX_DIM] = {\n" % name)
        for start in range(0, TEX_DIM, 8):
            chunk = spans(px)[start:start + 8]
            out.write("    " + " ".join("{0x%02x,0x%02x}," % s for s in chunk) + "\n")
        out.write("};\n\n")
        out.write("static const SpriteAsset %s_asset = { %s, %s_spans };\n\n"
                  % (name, name, name))

    out.write("const SpriteAsset *g_entity_sprites[ENT_TYPE_COUNT] = {\n")
    for entity in ENTITY_ORDER:
        asset = ENTITY_SPRITE.get(entity)
        out.write("    /* %-20s */ %s,\n"
                  % (entity, ("&%s_asset" % asset) if asset else "0"))
    out.write("};\n")


if __name__ == "__main__":
    main()
