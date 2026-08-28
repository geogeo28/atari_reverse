"""Differential test of the integer DDA against a brute-force float marcher.

The marcher is deliberately dumb: it walks the ray in small steps until it
enters a solid cell, then solves the crossing analytically.  It shares no code
and no algorithm with src/raycast.c beyond the quantised sine table, which both
must use or they would disagree about where the ray points in the first place.
"""
import ctypes
import math
import random

import pytest

import blackice
from blackice import CONST

SIDE_NS = CONST["SIDE_NS"]
SIDE_EW = CONST["SIDE_EW"]
TRIG_ONE = blackice.TRIG_ONE
CELL = blackice.CELL_UNITS

# The marcher steps this far between cell probes.  A cell is 256 units, so it
# can never step over one; it can only get the ORDER of two crossings wrong
# within a corner, which is what CORNER_GUARD_UNITS discards.
MARCH_STEP_UNITS = 4.0
CORNER_GUARD_UNITS = 6.0

# The integer DDA rounds its delta distance once per cell, so error accumulates
# with the step count; twelve cells of travel is worth about six units, and the
# initial side distance truncates one more.
DISTANCE_TOLERANCE_UNITS = 12
TEXEL_TOLERANCE = 3


def make_level(lib, width, height, cells, start_cell):
    level = blackice.Level()
    level.width = width
    level.height = height
    level.entity_count = 0
    level.trace_base_rate = 400
    level.start_cell_x, level.start_cell_y = start_cell
    for i, value in enumerate(cells):
        level.cells[i] = value
    return level


def random_map(seed, width=16, height=16, density=0.22):
    """A sealed room with random pillars, using a distinct texture id per cell
    so that a matching tex_id is strong evidence the same cell was hit."""
    rng = random.Random(seed)
    cells = [0] * (width * height)
    for y in range(height):
        for x in range(width):
            border = x in (0, width - 1) or y in (0, height - 1)
            if border:
                cells[y * width + x] = 1
            elif rng.random() < density:
                cells[y * width + x] = rng.randint(2, 8)
    open_cells = [(x, y) for y in range(height) for x in range(width)
                  if cells[y * width + x] == 0]
    return cells, width, height, rng.choice(open_cells), rng


def march(cells, width, pos_x, pos_y, dir_x, dir_y, radius_units):
    """Return (perp_ray_length, side, hit_x, hit_y, cell_value) or None."""
    travelled = 0.0
    previous = (int(pos_x) >> 8, int(pos_y) >> 8)
    while travelled <= radius_units:
        travelled += MARCH_STEP_UNITS
        x = pos_x + dir_x * travelled
        y = pos_y + dir_y * travelled
        cell = (int(math.floor(x)) >> 8, int(math.floor(y)) >> 8)
        if cell == previous:
            continue
        if cell[0] != previous[0] and cell[1] != previous[1]:
            return None                                 # corner: order is ambiguous
        value = cells[cell[1] * width + cell[0]]
        if value != 0:
            if cell[0] != previous[0]:
                boundary = (cell[0] if cell[0] > previous[0] else previous[0]) * CELL
                length = (boundary - pos_x) / dir_x
                side = SIDE_EW
            else:
                boundary = (cell[1] if cell[1] > previous[1] else previous[1]) * CELL
                length = (boundary - pos_y) / dir_y
                side = SIDE_NS
            return length, side, pos_x + dir_x * length, pos_y + dir_y * length, value
        previous = cell
    return None


def near_a_cell_edge(value):
    edge = value - math.floor(value / CELL) * CELL
    return edge < CORNER_GUARD_UNITS or edge > CELL - CORNER_GUARD_UNITS


@pytest.mark.parametrize("seed", range(6))
def test_dda_matches_a_brute_force_marcher(lib, seed):
    cells, width, height, start, rng = random_map(seed)
    level = make_level(lib, width, height, cells, start)
    state = blackice.new_state(lib, level)
    scratch = blackice.RenderScratch()

    sines = blackice.table(lib, "g_sin_1024", ctypes.c_int16, blackice.TRIG_TABLE_SIZE)
    columns = CONST["RENDER_COLUMNS_HIGH"]
    col_angle = blackice.table(lib, "g_col_angle_high", ctypes.c_int16, columns)
    col_cos = blackice.table(lib, "g_col_cos_high", ctypes.c_uint16, columns)
    radius_units = CONST["RENDER_RADIUS_NOMINAL"] * CELL

    compared = 0
    for _ in range(4):
        state.player.x = start[0] * CELL + rng.randint(80, 176)
        state.player.y = start[1] * CELL + rng.randint(80, 176)
        state.player.angle = rng.randrange(65536)
        lib.render_cast(ctypes.byref(state), ctypes.byref(scratch))

        for column in range(0, columns, 7):
            ray = (state.player.angle + col_angle[column]) & 0xffff
            index = (ray >> 6) & (blackice.TRIG_TABLE_SIZE - 1)
            sine = sines[index] / TRIG_ONE
            cosine = sines[(index + blackice.TRIG_TABLE_SIZE // 4) % blackice.TRIG_TABLE_SIZE] \
                / TRIG_ONE
            if sine == 0 or cosine == 0:
                continue                                # grid-parallel: the guard below is moot
            reference = march(cells, width, state.player.x, state.player.y,
                              cosine, sine, radius_units)
            got = scratch.columns[column]
            if reference is None:
                continue
            length, side, hit_x, hit_y, value = reference
            if near_a_cell_edge(hit_y if side == SIDE_EW else hit_x):
                continue                                # grazing a corner
            if got.tex_id == CONST["COLUMN_TEX_FAR"]:
                continue                                # both agree only past the radius

            assert got.side == side, "column %d took the wrong face" % column
            assert got.tex_id == value, "column %d hit a different cell" % column

            perp = length * col_cos[column] / TRIG_ONE
            assert abs(scratch.wall_dist[column] - perp) <= DISTANCE_TOLERANCE_UNITS

            surface = hit_y if side == SIDE_EW else hit_x
            texel = int(surface) % CELL >> 2
            if (side == SIDE_EW and cosine > 0) or (side == SIDE_NS and sine < 0):
                texel = (blackice.TEX_DIM - 1) - texel
            delta = (got.tex_col - texel) % blackice.TEX_DIM
            assert min(delta, blackice.TEX_DIM - delta) <= TEXEL_TOLERANCE
            compared += 1
    assert compared > 40, "the guards discarded almost every column"


def test_fisheye_correction_makes_a_flat_wall_flat(lib):
    """Standing square to a long wall, every column of it must project to the
    same height.  Without the per-column cosine the edges bulge."""
    width = height = 16
    cells = [1 if (x in (0, width - 1) or y in (0, height - 1)) else 0
             for y in range(height) for x in range(width)]
    level = make_level(lib, width, height, cells, (8, 8))
    state = blackice.new_state(lib, level)
    scratch = blackice.RenderScratch()

    state.player.x = 8 * CELL + CELL // 2
    state.player.y = 8 * CELL + CELL // 2
    state.player.angle = 3 * CONST["ANGLE_QUARTER_TURN"]        # due north
    lib.render_cast(ctypes.byref(state), ctypes.byref(scratch))

    heights = [scratch.columns[c].rows for c in range(CONST["RENDER_COLUMNS_HIGH"])
               if scratch.columns[c].tex_id != CONST["COLUMN_TEX_FAR"]]
    assert len(heights) == CONST["RENDER_COLUMNS_HIGH"]
    assert max(heights) - min(heights) <= 1, "flat wall is not flat: %r" % sorted(set(heights))


def test_every_column_stays_inside_the_window(lib, level1):
    """Whatever the DDA finds, the column list must never ask the drawer to
    write outside the chunky buffer: the drawer has no clipping of its own."""
    state = blackice.new_state(lib, level1)
    scratch = blackice.RenderScratch()

    modes = blackice.table(lib, "g_throttle_modes", blackice.ThrottleMode,
                           CONST["THROTTLE_MODE_COUNT"])
    sets = blackice.table(lib, "g_column_sets", blackice.ColumnSet, CONST["COLUMN_SET_COUNT"])
    for throttle in range(CONST["THROTTLE_MODE_COUNT"]):
        state.throttle = throttle
        columns = sets[modes[throttle].column_set].count
        for angle in range(0, 65536, 4096):
            state.player.angle = angle
            lib.render_cast(ctypes.byref(state), ctypes.byref(scratch))
            for c in range(columns):
                column = scratch.columns[c]
                assert 0 <= column.top <= blackice.RENDER_H
                assert column.top + column.rows <= blackice.RENDER_H
                assert column.tex_col < blackice.TEX_DIM
                assert column.band < CONST["BAND_COUNT"]
                assert column.side in (SIDE_NS, SIDE_EW)
