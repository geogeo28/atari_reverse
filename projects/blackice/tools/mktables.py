#!/usr/bin/env python3
"""Generate src/tables.c: trig, DDA delta distances, per-column ray geometry,
the throttle table, the palette and the depth-shade remap.

Everything here is derived once, offline, so the engine never computes a
transcendental and never divides in a hot path.  Run it after changing any
geometry constant in include/game_consts.h and keep the two in step: the
constants below are mirrored from that header and the C file asserts nothing,
so a silent divergence would be a real defect.  test/test_tables.py pins them.

    python3 tools/mktables.py > src/tables.c
"""
import math
import pathlib
import sys

# art/palette.py is the SHIPPING palette and the shipping depth-band remaps: it
# carries the reserved-accent rule, the "nothing fogs to void before band 4"
# rule, and the proofs behind both.  Restating any of it here is how the engine
# came to render the reserved white rim-light as green.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "art"))
import palette as art_palette                                   # noqa: E402

# --- mirrored from include/fixed.h / include/game_consts.h -----------------
TRIG_TABLE_SIZE = 1024
TRIG_ONE = 16384
CELL_UNITS = 256
DELTA_DIST_NEVER = 0xFFFF
FOV_DEGREES = 60
RENDER_COLUMNS_HIGH = 160
RENDER_COLUMNS_LOW = 80
BAND_COUNT = 5
SHADE_LEVEL_COUNT = BAND_COUNT + 1
PALETTE_SIZE = 16
THROTTLE_MODE_COUNT = 3

assert art_palette.DEPTH_BANDS == BAND_COUNT, \
    "art defines %d depth bands, game_consts.h says %d" % (art_palette.DEPTH_BANDS, BAND_COUNT)
assert art_palette.PALETTE_SIZE == PALETTE_SIZE

# DESIGN 5.  Radius in cells, band count and the 8.8 multipliers - and nothing
# about the render width, which is the separate detail-level setting.
THROTTLE_MODES = [
    # name          radius bands speed trace
    ("UNDERCLOCK",  6,     3,    320,  128),
    ("NOMINAL",     12,    5,    256,  256),
    ("OVERCLOCK",   20,    5,    205,  410),
]

# Where each band ends, as a fraction of the render radius.  At radius 12 these
# land exactly on 2 / 4 / 7 / 11 cells.
BAND_FRACTIONS_5 = (1 / 6, 1 / 3, 7 / 12, 11 / 12)
BAND_FRACTIONS_3 = (1 / 3, 2 / 3)
BAND_LIMIT_UNUSED = 0xFFFF


def sin_table():
    """1.14 sine over a full turn."""
    return [int(round(TRIG_ONE * math.sin(2 * math.pi * i / TRIG_TABLE_SIZE)))
            for i in range(TRIG_TABLE_SIZE)]


def delta_dist_table(sin_tab):
    """Ray length gained per whole cell of x travel: CELL_UNITS / |cos(theta)|.

    Derived from the QUANTISED cosine the DDA will actually use, not from
    math.cos, so the step distances and the hit point stay self-consistent.

    The value is EXACT wherever it is finite - the smallest non-zero |cos| the
    table holds gives 256 * 16384 / 100 = 41943, which is why the entries are
    unsigned words.  Rounding them down instead would make a near-axis ray
    cross the perpendicular grid line up to 23% early, in the wrong cell.  The
    four exactly-grid-parallel angles are DELTA_DIST_NEVER: no finite crossing.
    """
    out = []
    quarter = TRIG_TABLE_SIZE // 4
    for i in range(TRIG_TABLE_SIZE):
        cos14 = abs(sin_tab[(i + quarter) % TRIG_TABLE_SIZE])
        if cos14 == 0:
            out.append(DELTA_DIST_NEVER)
        else:
            delta = int(round(CELL_UNITS * TRIG_ONE / cos14))
            assert delta < DELTA_DIST_NEVER, "delta %d collides with the sentinel" % delta
            out.append(delta)
    return out


def column_geometry(columns):
    """Per-column ray angle offset and its fisheye-correction cosine.

    The offsets are atan-spaced, not evenly spaced: that is what makes a flat
    wall project to a flat wall.  The cosine then converts the DDA's ray length
    into the perpendicular distance the projection needs.
    """
    half_fov = math.radians(FOV_DEGREES) / 2
    tan_half = math.tan(half_fov)
    angles, cosines = [], []
    for c in range(columns):
        camera_x = (2.0 * (c + 0.5) / columns) - 1.0
        theta = math.atan(camera_x * tan_half)
        angles.append(int(round(theta * 65536 / (2 * math.pi))))
        cosines.append(int(round(TRIG_ONE * math.cos(theta))))
    return angles, cosines


def shade_lut():
    """g_shade_lut[level][index], straight from art/palette.py's band tables.

    The renderer composes the depth band and the face's lighting into ONE index
    with `band + side`, so an unlit face reads exactly one band deeper than a
    lit one at the same distance - which is why there is one more level than
    there are bands.  The deepest band has nowhere deeper to go, so its lit and
    unlit rows are the same table; that band is the far fill, where the cue has
    nothing left to distinguish.
    """
    deepest = art_palette.DEPTH_BANDS - 1
    return [list(art_palette.shade_table(min(level, deepest)))
            for level in range(SHADE_LEVEL_COUNT)]


def band_limits(radius_cells, bands):
    fractions = BAND_FRACTIONS_5 if bands == 5 else BAND_FRACTIONS_3
    radius_units = radius_cells * CELL_UNITS
    limits = [int(round(radius_units * f)) for f in fractions]
    while len(limits) < BAND_COUNT - 1:
        limits.append(BAND_LIMIT_UNUSED)
    return limits


def emit_array(out, ctype, name, values, per_line=12, index_fmt="{}"):
    out.write("const %s %s[%d] = {\n" % (ctype, name, len(values)))
    for start in range(0, len(values), per_line):
        chunk = values[start:start + per_line]
        out.write("    " + " ".join(index_fmt.format(v) + "," for v in chunk) + "\n")
    out.write("};\n\n")


def main():
    out = sys.stdout
    sin_tab = sin_table()
    delta_tab = delta_dist_table(sin_tab)
    angle_hi, cos_hi = column_geometry(RENDER_COLUMNS_HIGH)
    angle_lo, cos_lo = column_geometry(RENDER_COLUMNS_LOW)

    out.write("/*\n"
              " * tables.c - GENERATED by tools/mktables.py.  Do not edit.\n"
              " *\n"
              " * Trig, DDA delta distances, per-column ray geometry, the throttle table,\n"
              " * the palette and the depth-shade remap.  The two reciprocal tables are\n"
              " * .bss filled by tables_init() rather than 32 KB of const data, to keep\n"
              " * them out of the .PRG on the target.\n"
              " */\n"
              "#include \"fixed.h\"\n"
              "#include \"render.h\"\n\n")

    emit_array(out, "int16_t", "g_sin_1024", sin_tab)
    emit_array(out, "uint16_t", "g_inv_cos_dist", delta_tab)
    emit_array(out, "int16_t", "g_col_angle_high", angle_hi)
    emit_array(out, "uint16_t", "g_col_cos_high", cos_hi)
    emit_array(out, "int16_t", "g_col_angle_low", angle_lo)
    emit_array(out, "uint16_t", "g_col_cos_low", cos_lo)

    # The budgets are spelled as their macro names, not their values: the C
    # file includes game_consts.h, so there is no second copy to drift.
    out.write("const ColumnSet g_column_sets[DETAIL_LEVEL_COUNT] = {\n"
              "    /* DETAIL_COLUMNS_160 */ { RENDER_COLUMNS_HIGH, SPRITE_PIXEL_BUDGET_HIGH,"
              " 0, 0, g_col_angle_high, g_col_cos_high },\n"
              "    /* DETAIL_COLUMNS_80  */ { RENDER_COLUMNS_LOW,  SPRITE_PIXEL_BUDGET_LOW,"
              "  1, 0, g_col_angle_low,  g_col_cos_low  },\n"
              "};\n\n")

    out.write("const ThrottleMode g_throttle_modes[THROTTLE_MODE_COUNT] = {\n")
    for name, radius, bands, speed, trace in THROTTLE_MODES:
        limits = band_limits(radius, bands)
        out.write("    /* %s */ { %d, %d, %d, %d, { %s } },\n"
                  % (name, radius, bands, speed, trace,
                     ", ".join(str(v) for v in limits)))
    out.write("};\n\n")

    out.write("/* DESIGN 3's sixteen registers, from art/palette.py. */\n"
              "const uint8_t g_palette_rgb[PALETTE_SIZE][3] = {\n")
    for entry in art_palette.PALETTE:
        r, g, b = entry.rgb
        out.write("    { 0x%02x, 0x%02x, 0x%02x },   /* %-9s #%02X%02X%02X */\n"
                  % (r, g, b, entry.name, r, g, b))
    out.write("};\n\n")

    out.write("/* Depth-band index remaps, from art/palette.py's shade_table(). */\n"
              "const uint8_t g_shade_lut[SHADE_LEVEL_COUNT][PALETTE_SIZE] = {\n")
    for level, row in enumerate(shade_lut()):
        out.write("    /* level %d */ { %s },\n"
                  % (level, ", ".join("%2d" % v for v in row)))
    out.write("};\n\n")

    out.write("""uint16_t g_slice_height[DIST_TABLE_SIZE];
uint16_t g_tex_step[DIST_TABLE_SIZE];
uint8_t g_cell_texture[CELL_VALUE_COUNT];

/*
 * Fill the two reciprocal tables.  The only divides in the engine live here and
 * they run once, at start-up: 8192 iterations of two `divu` is about 2.3 ms on
 * an 8 MHz 68000.
 */
void tables_init(void)
{
    int32_t dist;

    for (dist = DIST_MIN_UNITS; dist < DIST_TABLE_SIZE; ++dist) {
        uint16_t height = (uint16_t)(WALL_PROJECTION_SCALE / dist);

        g_slice_height[dist] = height;
        g_tex_step[dist] = (uint16_t)(((int32_t)TEX_DIM << 8) / height);
    }
    /* Nothing can be closer than DIST_MIN_UNITS, so the head of the table
     * repeats that entry and callers only have to clamp the top end. */
    for (dist = 0; dist < DIST_MIN_UNITS; ++dist) {
        g_slice_height[dist] = g_slice_height[DIST_MIN_UNITS];
        g_tex_step[dist] = g_tex_step[DIST_MIN_UNITS];
    }
    /* Asked once per value here rather than once per column at run time; the
     * rule itself stays in map_cell_texture. */
    for (dist = 0; dist < CELL_VALUE_COUNT; ++dist) {
        g_cell_texture[dist] = map_cell_texture((uint8_t)dist);
    }
}
""")


if __name__ == "__main__":
    main()
