"""The generated tables are the engine's arithmetic; if they drift, everything
downstream is wrong in a way that looks like a rendering bug."""
import ctypes
import math
import sys

import blackice
from blackice import CONST

sys.path.insert(0, str(blackice.ROOT / "art"))
import palette as art_palette                   # noqa: E402

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
    uses, or the two disagree by a fraction of a cell at long range.

    Every finite entry is EXACT.  Clamping them low was a real defect - it made
    a near-axis ray cross the perpendicular grid line early, in the wrong cell -
    so this asserts no clamp at all below the never-crosses sentinel.
    """
    sines = sin_table(lib)
    deltas = blackice.table(lib, "g_inv_cos_dist", ctypes.c_uint16, TABLE)
    never = CONST["DELTA_DIST_NEVER"]
    finite = []
    for i in range(TABLE):
        cos14 = abs(sines[(i + QUARTER) % TABLE])
        if cos14 == 0:
            assert deltas[i] == never, "a grid-parallel ray must never cross"
            continue
        expected = round(blackice.CELL_UNITS * TRIG_ONE / cos14)
        assert deltas[i] == expected
        finite.append(deltas[i])
    assert max(finite) < never, "a real delta collides with the sentinel"


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


def test_the_shade_lut_is_the_art_departments_band_tables(lib):
    """art/palette.py owns the depth-band remaps - the reserved-accent rule, the
    "nothing fogs to void before the last band" rule and the proofs behind both
    live there.  The engine table is generated from it, so this is the pin that
    says the generated copy is still that table.

    The renderer composes band and face into one index (`band + side`), so an
    unlit face reads one band deeper; the deepest band has nowhere deeper to go
    and its two rows coincide.
    """
    levels = CONST["SHADE_LEVEL_COUNT"]
    size = CONST["PALETTE_SIZE"]
    lut = blackice.table(lib, "g_shade_lut", ctypes.c_uint8 * size, levels)
    deepest = art_palette.DEPTH_BANDS - 1

    assert levels == art_palette.DEPTH_BANDS + 1, "one level per band, plus the unlit deepest"
    for level in range(levels):
        expected = art_palette.shade_table(min(level, deepest))
        assert list(lut[level]) == list(expected), "level %d is not the art's band" % level

    for index in range(size):
        assert lut[0][index] == index, "level 0 must be the identity or the lit face is wrong"
    for level in range(levels):
        assert lut[level][CONST["COLOUR_VOID"]] == CONST["COLOUR_VOID"]


def test_no_wall_legal_colour_fogs_to_void_before_the_last_band(lib):
    """The art review's rule.  Sending a structural colour to void mid-range
    punches black holes shaped exactly like the corruption texture, so distance
    manufactures corruption - which inverts the premise of the world."""
    size = CONST["PALETTE_SIZE"]
    levels = CONST["SHADE_LEVEL_COUNT"]
    lut = blackice.table(lib, "g_shade_lut", ctypes.c_uint8 * size, levels)
    void = CONST["COLOUR_VOID"]
    last_band = art_palette.DEPTH_BANDS - 1

    for index in art_palette.wall_legal_indices():
        if index == void:
            continue
        for level in range(last_band):
            assert lut[level][index] != void, \
                "palette index %d fogs to void at level %d" % (index, level)


def test_the_reserved_accents_never_fade(lib):
    """RIM and ALERT are reserved so a 1px rim-light and an enemy's core stay
    readable at every depth.  Fading either is the same defect as omitting it."""
    size = CONST["PALETTE_SIZE"]
    levels = CONST["SHADE_LEVEL_COUNT"]
    lut = blackice.table(lib, "g_shade_lut", ctypes.c_uint8 * size, levels)

    for index in art_palette.SPRITE_ONLY:
        for level in range(levels):
            assert lut[level][index] == index, \
                "reserved accent %d moved at level %d" % (index, level)


def test_throttle_modes_match_the_design_table(lib):
    modes = blackice.table(lib, "g_throttle_modes", blackice.ThrottleMode,
                           CONST["THROTTLE_MODE_COUNT"])
    expected = [
        (CONST["RENDER_RADIUS_UNDERCLOCK"], 3,
         CONST["THROTTLE_SPEED_UNDERCLOCK"], CONST["THROTTLE_TRACE_UNDERCLOCK"]),
        (CONST["RENDER_RADIUS_NOMINAL"], 5,
         CONST["THROTTLE_SPEED_NOMINAL"], CONST["THROTTLE_TRACE_NOMINAL"]),
        (CONST["RENDER_RADIUS_OVERCLOCK"], 5,
         CONST["THROTTLE_SPEED_OVERCLOCK"], CONST["THROTTLE_TRACE_OVERCLOCK"]),
    ]
    # tools/mktables.py carries its own copy of this table, because the C is
    # generated from it.  These asserts are what keeps the two copies equal.
    for mode, (radius, bands, speed, trace) in zip(modes, expected):
        assert (mode.radius_cells, mode.band_count) == (radius, bands)
        assert (mode.speed_scale, mode.trace_scale) == (speed, trace)
        limits = [mode.band_limit[i] for i in range(bands - 1)]
        assert limits == sorted(limits)
        assert limits[-1] < radius * blackice.CELL_UNITS


def test_the_throttle_table_says_nothing_about_the_render_width(lib):
    """DESIGN 5 makes the throttle a radius / speed / trace trade.  The width
    is the separate detail level, and the sprite budget - which scales with the
    width - hangs off that and not off the throttle."""
    assert not hasattr(blackice.ThrottleMode, "column_set")
    assert not hasattr(blackice.ThrottleMode, "sprite_budget")

    sets = blackice.table(lib, "g_column_sets", blackice.ColumnSet,
                          CONST["DETAIL_LEVEL_COUNT"])
    wide = sets[CONST["DETAIL_COLUMNS_160"]]
    narrow = sets[CONST["DETAIL_COLUMNS_80"]]

    assert (wide.count, wide.width_shift) == (CONST["RENDER_COLUMNS_HIGH"], 0)
    assert (narrow.count, narrow.width_shift) == (CONST["RENDER_COLUMNS_LOW"], 1)
    assert wide.sprite_budget == CONST["SPRITE_PIXEL_BUDGET_HIGH"]
    assert narrow.sprite_budget == CONST["SPRITE_PIXEL_BUDGET_LOW"]


def test_the_palette_is_the_shipping_art_palette(lib):
    """art/palette.py is the single definition of DESIGN 3's sixteen registers.
    The engine table is generated from it; this is what says the two agree.

    It matters more than a normal constant pin: the indices carry ROLES.  An
    engine built against a stale copy rendered every reserved white rim-light
    in whatever colour had drifted into slot 12.
    """
    rgb = blackice.table(lib, "g_palette_rgb", ctypes.c_uint8 * 3, CONST["PALETTE_SIZE"])

    assert len(art_palette.PALETTE) == CONST["PALETTE_SIZE"]
    for entry in art_palette.PALETTE:
        assert list(rgb[entry.index]) == list(entry.rgb), \
            "palette index %d (%s) moved" % (entry.index, entry.name)
        # STE colour words are 4 bits a channel: every value must be a multiple
        # of 0x11 or it silently quantises on the hardware.
        for channel in entry.rgb:
            assert channel % 0x11 == 0

    # The transparency key is a palette role, and the engine spells it itself.
    assert CONST["SPRITE_TRANSPARENT"] == art_palette.TRANSPARENT_INDEX
    assert CONST["COLOUR_VOID"] == art_palette.VOID


def test_the_cell_texture_table_is_the_function_it_replaces(lib):
    """render_cast reads a table instead of calling map_cell_texture per column.
    A table and a function are two answers to one question, so the table is
    filled BY the function - and this is what says it still was."""
    lib.map_cell_texture.argtypes = [ctypes.c_uint8]
    lib.map_cell_texture.restype = ctypes.c_uint8
    table = blackice.table(lib, "g_cell_texture", ctypes.c_uint8, CONST["CELL_VALUE_COUNT"])

    for value in range(CONST["CELL_VALUE_COUNT"]):
        assert table[value] == lib.map_cell_texture(value), "cell value %d" % value

    # Every texture an AUTHORED cell can name must have art, or draw.c
    # dereferences NULL.  Values the legend cannot produce are the loader's
    # problem, and it refuses them - see test_level.py.
    sys.path.insert(0, str(blackice.ROOT / "tools"))
    import mklevel

    slots = blackice.wall_texture_slots(lib)
    for glyph, (value, _entity, _start) in mklevel.LEGEND.items():
        texture = table[value]
        assert texture == 0 or slots[texture], \
            "glyph %r names empty texture slot %d" % (glyph, texture)
