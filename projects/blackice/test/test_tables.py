"""The generated tables are the engine's arithmetic; if they drift, everything
downstream is wrong in a way that looks like a rendering bug."""
import ctypes
import math

import blackice
from blackice import CONST

TRIG_ONE = blackice.TRIG_ONE
TABLE = blackice.TRIG_TABLE_SIZE
QUARTER = TABLE // 4


def sin_table(lib):
    return blackice.table(lib, "g_sin_1024", ctypes.c_int16, TABLE)


def test_sine_table_matches_the_ideal_within_one_lsb(lib):
    values = sin_table(lib)
    for i in range(TABLE):
        ideal = TRIG_ONE * math.sin(2 * math.pi * i / TABLE)
        assert abs(values[i] - ideal) <= 1.0


def test_delta_distance_is_the_reciprocal_of_the_quantised_cosine(lib):
    """The DDA's step distances must come from the same cosine the hit point
    uses, or the two disagree by a fraction of a cell at long range."""
    sines = sin_table(lib)
    deltas = blackice.table(lib, "g_inv_cos_dist", ctypes.c_uint16, TABLE)
    clamp = CONST["DELTA_DIST_MAX"]
    for i in range(TABLE):
        cos14 = abs(sines[(i + QUARTER) % TABLE])
        expected = clamp if cos14 == 0 else min(clamp, round(blackice.CELL_UNITS * TRIG_ONE / cos14))
        assert deltas[i] == expected


def test_column_angles_span_the_fov_and_are_atan_spaced(lib):
    columns = CONST["RENDER_COLUMNS_HIGH"]
    angles = blackice.table(lib, "g_col_angle_high", ctypes.c_int16, columns)
    cosines = blackice.table(lib, "g_col_cos_high", ctypes.c_uint16, columns)
    half_fov = math.radians(CONST["FOV_DEGREES"]) / 2

    assert angles[0] == -angles[columns - 1]
    assert abs(angles[0]) < CONST["FOV_HALF_ANGLE"]
    for c in range(columns):
        camera_x = (2.0 * (c + 0.5) / columns) - 1.0
        theta = math.atan(camera_x * math.tan(half_fov))
        assert abs(angles[c] - theta * 65536 / (2 * math.pi)) <= 1.0
        assert abs(cosines[c] - TRIG_ONE * math.cos(theta)) <= 1.0


def test_reciprocal_tables_agree_with_the_projection(lib):
    heights = blackice.table(lib, "g_slice_height", ctypes.c_uint16, blackice.DIST_TABLE_SIZE)
    steps = blackice.table(lib, "g_tex_step", ctypes.c_uint16, blackice.DIST_TABLE_SIZE)
    scale = CONST["WALL_PROJECTION_SCALE"]
    floor = CONST["DIST_MIN_UNITS"]

    for dist in range(floor, blackice.DIST_TABLE_SIZE):
        assert heights[dist] == scale // dist
        assert steps[dist] == (blackice.TEX_DIM << 8) // heights[dist]
    for dist in range(floor):
        assert heights[dist] == heights[floor]
        assert steps[dist] == steps[floor]
    assert heights[floor] == CONST["SLICE_HEIGHT_MAX"]


# Rec.601 luminance: a sum of channels would call the alarm orange brighter
# than the magenta it fades into, which is not what an eye sees.
def _luminance(rgb_triple):
    return 0.299 * rgb_triple[0] + 0.587 * rgb_triple[1] + 0.114 * rgb_triple[2]


def test_shade_lut_walks_every_colour_toward_the_void(lib):
    """Fog must be monotone: no palette entry may get brighter with depth, and
    the identity must be exactly level 0 or the lit face is wrong."""
    levels = CONST["SHADE_LEVEL_COUNT"]
    size = CONST["PALETTE_SIZE"]
    lut = blackice.table(lib, "g_shade_lut", ctypes.c_uint8 * size, levels)
    rgb = blackice.table(lib, "g_palette_rgb", ctypes.c_uint8 * 3, size)

    for index in range(size):
        assert lut[0][index] == index
    for level in range(1, levels):
        for index in range(size):
            before = _luminance(rgb[lut[level - 1][index]])
            after = _luminance(rgb[lut[level][index]])
            assert after <= before, "index %d brightens at level %d" % (index, level)
    # The void has to be a fixed point or the far bands would crawl back up.
    for level in range(levels):
        assert lut[level][CONST["COLOUR_VOID"]] == CONST["COLOUR_VOID"]


def test_throttle_modes_match_the_design_table(lib):
    modes = blackice.table(lib, "g_throttle_modes", blackice.ThrottleMode,
                           CONST["THROTTLE_MODE_COUNT"])
    expected = [
        (CONST["RENDER_RADIUS_UNDERCLOCK"], 3, CONST["COLUMN_SET_LOW"],
         CONST["THROTTLE_SPEED_UNDERCLOCK"], CONST["THROTTLE_TRACE_UNDERCLOCK"],
         CONST["SPRITE_PIXEL_BUDGET_LOW"]),
        (CONST["RENDER_RADIUS_NOMINAL"], 5, CONST["COLUMN_SET_HIGH"],
         CONST["THROTTLE_SPEED_NOMINAL"], CONST["THROTTLE_TRACE_NOMINAL"],
         CONST["SPRITE_PIXEL_BUDGET_HIGH"]),
        (CONST["RENDER_RADIUS_OVERCLOCK"], 5, CONST["COLUMN_SET_HIGH"],
         CONST["THROTTLE_SPEED_OVERCLOCK"], CONST["THROTTLE_TRACE_OVERCLOCK"],
         CONST["SPRITE_PIXEL_BUDGET_HIGH"]),
    ]
    # tools/mktables.py carries its own copy of this table, because the C is
    # generated from it.  These asserts are what keeps the two copies equal.
    for mode, (radius, bands, column_set, speed, trace, budget) in zip(modes, expected):
        assert (mode.radius_cells, mode.band_count, mode.column_set) == (radius, bands, column_set)
        assert (mode.speed_scale, mode.trace_scale) == (speed, trace)
        assert mode.sprite_budget == budget
        limits = [mode.band_limit[i] for i in range(bands - 1)]
        assert limits == sorted(limits)
        assert limits[-1] < radius * blackice.CELL_UNITS


# DESIGN 3 fixes these sixteen registers for the whole game.  They live in
# tools/mktables.py, so this is the second copy that pins the first.
DESIGN_PALETTE = [
    "000000", "CCFFFF", "77EEFF", "33BBEE", "1177BB", "003355",
    "FFCCFF", "FF77DD", "DD33AA", "991177", "440044",
    "FFFF66", "33FF66", "FFFFFF", "FF4400", "333344",
]


def test_the_palette_is_the_design_contract(lib):
    rgb = blackice.table(lib, "g_palette_rgb", ctypes.c_uint8 * 3, CONST["PALETTE_SIZE"])
    for index, hexcode in enumerate(DESIGN_PALETTE):
        expected = [int(hexcode[i:i + 2], 16) for i in (0, 2, 4)]
        assert list(rgb[index]) == expected, "palette index %d moved" % index
        # STE colour words are 4 bits a channel: every value must be a multiple
        # of 0x11 or it silently quantises on the hardware.
        for channel in expected:
            assert channel % 0x11 == 0
