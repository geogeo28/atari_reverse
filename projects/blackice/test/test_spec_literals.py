"""DESIGN's numbers, spelled as literals.

Every other test in this suite reads its expectations out of the headers, which
is what keeps them honest about the code - and blind to the code being wrong.
`assert DOOR_OPEN_TICKS == DOOR_OPEN_TICKS` passes whatever the value is.

This file is the other end of that: the design document's figures, typed in by
hand, checked against what the engine compiled.  When one of these fails the
question is not "which is right" - it is "was the design changed on purpose".
"""
import blackice
from blackice import CONST

SIM_HZ = 25                     # DESIGN 4: one tick per two PAL VBLs


def test_the_simulation_runs_at_25_hz():
    assert CONST["SIM_HZ"] == SIM_HZ


def test_the_door_cycle_is_half_a_second_three_seconds_half_a_second():
    """DESIGN 10.  Spelled in ticks here and derived from SIM_HZ in the header,
    so this catches a change to either."""
    assert CONST["DOOR_OPENING_TICKS"] == 12        # 0.5 s at 25 Hz, floored
    assert CONST["DOOR_OPEN_TICKS"] == 75           # 3 s
    assert CONST["DOOR_CLOSING_TICKS"] == 12
    assert CONST["DOOR_MAX_COUNT"] == 64


def test_the_throttle_is_the_design_five_table():
    """DESIGN 5: three clock settings trading render radius against speed and
    trace rate.  The radii are the shape of the whole mechanic."""
    assert CONST["RENDER_RADIUS_UNDERCLOCK"] == 6
    assert CONST["RENDER_RADIUS_NOMINAL"] == 12
    assert CONST["RENDER_RADIUS_OVERCLOCK"] == 20
    assert CONST["THROTTLE_MODE_COUNT"] == 3
    assert CONST["THROTTLE_SWITCH_TICKS"] == 12     # the switch costs half a second

    # The 8.8 multipliers: 1.25 / 1.00 / 0.80 speed, 0.5 / 1.0 / 1.6 trace.
    assert CONST["THROTTLE_SPEED_UNDERCLOCK"] == round(1.25 * 256)
    assert CONST["THROTTLE_SPEED_NOMINAL"] == 256
    assert CONST["THROTTLE_SPEED_OVERCLOCK"] == round(0.80 * 256)
    assert CONST["THROTTLE_TRACE_UNDERCLOCK"] == round(0.5 * 256)
    assert CONST["THROTTLE_TRACE_NOMINAL"] == 256
    assert CONST["THROTTLE_TRACE_OVERCLOCK"] == round(1.6 * 256)


def test_the_sprite_budget_is_the_design_eight_figure():
    assert CONST["SPRITE_PIXEL_BUDGET_HIGH"] == 6000
    assert CONST["SPRITE_PIXEL_BUDGET_LOW"] == 3000
    assert CONST["SPRITE_MAX_VISIBLE"] == 32


def test_the_render_window_is_160_by_80_doubled_to_320_by_200():
    """DESIGN 17.  The window is 160x80 logical pixels, doubled to 320x160 of
    the ST's 320x200 screen, with 40 scanlines of HUD under it."""
    assert CONST["RENDER_W_MAX"] == 160
    assert CONST["RENDER_H"] == 80
    assert CONST["RENDER_COLUMNS_HIGH"] == 160
    assert CONST["RENDER_COLUMNS_LOW"] == 80
    assert CONST["SCREEN_W"] == 320
    assert CONST["SCREEN_H"] == 200
    assert CONST["SCREEN_PLANES"] == 4
    assert CONST["SCREEN_BYTES_PER_LINE"] == 160
    assert CONST["SCREEN_BYTES"] == 32000
    assert CONST["SCREEN_WINDOW_LINES"] == 160
    assert CONST["SCREEN_HUD_LINES"] == 40
    assert CONST["PALETTE_SIZE"] == 16


def test_the_projection_is_a_60_degree_fov_over_64_texel_art():
    assert CONST["FOV_DEGREES"] == 60
    assert CONST["TEX_DIM"] == 64
    assert CONST["BAND_COUNT"] == 5

    # FOCAL_ROWS makes a cell CUBIC: a face spans FOCAL_COLS/d columns of 2
    # screen pixels, an ST pixel is 0.833 as wide as it is tall, and the face
    # is 2 * FOCAL_ROWS/d tall.  Equating the two gives 115, not TEX_DIM's 64,
    # which projected walls squat by 1.8 to 1.
    assert CONST["FOCAL_ROWS"] == 115
    ste_pixel_aspect = 0.833
    focal_cols = CONST["FOCAL_COLS_Q8"] / 256
    assert abs(focal_cols - 80 / __import__("math").tan(__import__("math").radians(30))) < 0.1
    square = focal_cols * 2 * ste_pixel_aspect / 2
    assert abs(CONST["FOCAL_ROWS"] - square) <= 1, \
        "FOCAL_ROWS %d does not square up a cell (%.1f does)" % (CONST["FOCAL_ROWS"], square)


def test_the_level_header_is_42_bytes():
    """DESIGN 11's .bil header, field by field: 4 magic + 16 name + 10 bytes of
    small fields + 2 facing + 4 seed + 2 rate + 2 start/cap + 2 par + 2 count."""
    assert CONST["LEVEL_BLOB_HEADER_BYTES"] == 42
    assert CONST["LEVEL_BLOB_ENTITY_BYTES"] == 5
    assert CONST["LEVEL_NAME_LEN"] == 16
    assert CONST["MAP_MAX_DIM"] == 64
    assert CONST["LEVEL_MAX_ENTITIES"] == 64
    assert CONST["LEVEL_BLOB_OFF_RNG_SEED"] == 30
    assert CONST["LEVEL_BLOB_OFF_ENTITY_COUNT"] == 40


def test_the_trace_meter_is_carried_in_thousandths_of_a_percent():
    """DESIGN 9.  The base rate is per SECOND, not per tick - the engine got
    that wrong once and ran the meter 25 times too fast."""
    assert CONST["TRACE_MILLI_PER_PERCENT"] == 1000
    assert CONST["TRACE_MAX_MILLI"] == 100 * 1000

    import sys
    sys.path.insert(0, str(blackice.ROOT / "tools"))
    import mklevel

    assert mklevel.HEADER_DEFAULTS["trace_base_rate"] == 180, "DESIGN 9.1 ships 0.18 %/s"
    assert 180 / CONST["TRACE_MILLI_PER_PERCENT"] == 0.18


def test_the_map_grid_is_64_by_64_cells_of_256_units():
    assert CONST["MAP_MAX_DIM"] == 64
    assert CONST["MAP_MAX_CELLS"] == 64 * 64
    assert CONST["CELL_UNITS"] == 256
    assert CONST["BRADS_PER_TURN"] == 1024          # DESIGN 11 stores angles as brads
