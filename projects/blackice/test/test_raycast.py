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
from blackice import CONST, make_level

SIDE_NS = CONST["SIDE_NS"]
SIDE_EW = CONST["SIDE_EW"]
TRIG_ONE = blackice.TRIG_ONE
CELL = blackice.CELL
CENTRE = blackice.CENTRE

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
# How far the DDA may sit from the float marcher when the ray is running along
# a wall it nearly touches.  The near-axis clamp bug read hundreds of units short.
SPIKE_TOLERANCE_UNITS = 24


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


def march(cells, width, pos_x, pos_y, dir_x, dir_y, radius_units,
          step_units=MARCH_STEP_UNITS):
    """Return (perp_ray_length, side, hit_x, hit_y, cell_value) or None.

    `step_units` is how finely the crossings are resolved.  A ray that starts a
    few units from a grid line crosses it almost immediately, and the order of
    the two axes' first crossings is only unambiguous if the probe step is
    finer than the gap - so the near-grid-line test below marches at one unit.
    """
    travelled = 0.0
    previous = (int(pos_x) >> 8, int(pos_y) >> 8)
    while travelled <= radius_units:
        travelled += step_units
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



def state_at_full_width(lib, level):
    """A state rendering at 160 columns.

    The shipping default is 80 (DESIGN v2.1 17.3), and the tests below read the
    160-column ray tables by name, so they have to say which width they mean
    rather than inherit whichever one ships this week.
    """
    state = blackice.new_state(lib, level)
    state.detail_level = CONST["DETAIL_COLUMNS_160"]
    return state


THROTTLE_RADIUS = {
    CONST["THROTTLE_UNDERCLOCK"]: CONST["RENDER_RADIUS_UNDERCLOCK"],
    CONST["THROTTLE_NOMINAL"]: CONST["RENDER_RADIUS_NOMINAL"],
    CONST["THROTTLE_OVERCLOCK"]: CONST["RENDER_RADIUS_OVERCLOCK"],
}


@pytest.mark.parametrize("throttle", sorted(THROTTLE_RADIUS))
@pytest.mark.parametrize("seed", range(6))
def test_dda_matches_a_brute_force_marcher(lib, seed, throttle):
    """Run at every throttle, not just NOMINAL.  The radius is what bounds the
    DDA's step count, so OVERCLOCK is the only setting that reaches the far end
    of DDA_MAX_STEPS and UNDERCLOCK the only one that cuts rays short."""
    cells, width, height, start, rng = random_map(seed)
    level = make_level(lib, width, height, cells, start)
    state = state_at_full_width(lib, level)
    state.throttle = throttle
    scratch = blackice.RenderScratch()

    sines = blackice.table(lib, "g_sin_1024", ctypes.c_int16, blackice.TRIG_TABLE_SIZE)
    columns = CONST["RENDER_COLUMNS_HIGH"]
    col_angle = blackice.table(lib, "g_col_angle_high", ctypes.c_int16, columns)
    col_cos = blackice.table(lib, "g_col_cos_high", ctypes.c_uint16, columns)
    radius_units = THROTTLE_RADIUS[throttle] * CELL

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
            # The mirror rule, restated: src/raycast.c owns it and atari/cast.S carries a third
            # copy.  All three were inverted together on 2026-08-28 - see that file's comment.
            if (side == SIDE_EW and cosine <= 0) or (side == SIDE_NS and sine >= 0):
                texel = (blackice.TEX_DIM - 1) - texel
            delta = (got.tex_col - texel) % blackice.TEX_DIM
            assert min(delta, blackice.TEX_DIM - delta) <= TEXEL_TOLERANCE
            compared += 1
    assert compared > 20, "the guards discarded almost every column"


def test_fisheye_correction_makes_a_flat_wall_flat(lib):
    """Standing square to a long wall, every column of it must project to the
    same height.  Without the per-column cosine the edges bulge."""
    width = height = 16
    cells = [1 if (x in (0, width - 1) or y in (0, height - 1)) else 0
             for y in range(height) for x in range(width)]
    level = make_level(lib, width, height, cells, (8, 8))
    state = state_at_full_width(lib, level)
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
    state = state_at_full_width(lib, level1)
    scratch = blackice.RenderScratch()

    sets = blackice.table(lib, "g_column_sets", blackice.ColumnSet, CONST["DETAIL_LEVEL_COUNT"])
    for throttle in range(CONST["THROTTLE_MODE_COUNT"]):
        for detail in range(CONST["DETAIL_LEVEL_COUNT"]):
            state.throttle = throttle
            state.detail_level = detail
            columns = sets[detail].count
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


def test_hugging_a_wall_and_looking_along_it_matches_the_marcher(lib):
    """A near-axis ray's delta distance is huge, and it used to be CLAMPED - to
    a value BELOW the truth - so the ray thought it crossed the perpendicular
    grid line up to 23% early, stepped into the wall it was running beside, and
    drew one wildly-near column in the middle of a flat corridor.

    Every guard in the sweep above discards exactly this case (it is grazing, it
    is near-axis, it is beside a cell edge), so it gets its own test: hug the
    north wall, look along it, and hold the DDA to the float marcher.
    """
    width = height = 24
    cells = [1 if (x in (0, width - 1) or y in (0, height - 1)) else 0
             for y in range(height) for x in range(width)]
    level = make_level(lib, width, height, cells, (12, 12))
    state = state_at_full_width(lib, level)
    state.throttle = CONST["THROTTLE_OVERCLOCK"]        # radius 20: the whole room
    scratch = blackice.RenderScratch()

    sines = blackice.table(lib, "g_sin_1024", ctypes.c_int16, blackice.TRIG_TABLE_SIZE)
    columns = CONST["RENDER_COLUMNS_HIGH"]
    col_angle = blackice.table(lib, "g_col_angle_high", ctypes.c_int16, columns)
    col_cos = blackice.table(lib, "g_col_cos_high", ctypes.c_uint16, columns)
    radius_units = CONST["RENDER_RADIUS_OVERCLOCK"] * CELL
    radius = CONST["PLAYER_RADIUS"]

    compared = 0
    # As near the wall as the body can stand, and looking as nearly due east as
    # the angle quantisation allows - then a hair either side of it.
    for angle_offset in (-2, -1, 0, 1, 2):
        for gap in (radius, radius + 3, 128, 200):
            state.player.x = 6 * CELL + CENTRE
            state.player.y = 1 * CELL + gap
            state.player.angle = angle_offset & 0xffff
            lib.render_cast(ctypes.byref(state), ctypes.byref(scratch))

            for column in range(columns):
                ray = (state.player.angle + col_angle[column]) & 0xffff
                index = (ray >> 6) & (blackice.TRIG_TABLE_SIZE - 1)
                sine = sines[index] / TRIG_ONE
                cosine = sines[(index + blackice.TRIG_TABLE_SIZE // 4)
                               % blackice.TRIG_TABLE_SIZE] / TRIG_ONE
                if sine == 0 or cosine == 0:
                    continue
                reference = march(cells, width, state.player.x, state.player.y,
                                  cosine, sine, radius_units)
                if reference is None or scratch.columns[column].tex_id == CONST["COLUMN_TEX_FAR"]:
                    continue
                length, side, hit_x, hit_y, _value = reference
                if near_a_cell_edge(hit_y if side == SIDE_EW else hit_x):
                    continue
                perp = length * col_cos[column] / TRIG_ONE
                assert abs(scratch.wall_dist[column] - perp) <= SPIKE_TOLERANCE_UNITS, (
                    "column %d reads %d, the marcher says %.1f (gap %d, angle %d)"
                    % (column, scratch.wall_dist[column], perp, gap, angle_offset))
                compared += 1
    assert compared > 200, "only %d columns survived the guards" % compared


def test_a_grid_parallel_ray_never_crosses_the_other_axis(lib):
    """The four exactly-axis-aligned angles have no finite delta distance at
    all.  Storing a large number there instead of the never-crosses sentinel
    would make such a ray step sideways out of its own row."""
    deltas = blackice.table(lib, "g_inv_cos_dist", ctypes.c_uint16, blackice.TRIG_TABLE_SIZE)
    never = CONST["DELTA_DIST_NEVER"]

    parallel = [i for i in range(blackice.TRIG_TABLE_SIZE) if deltas[i] == never]
    # The table is the X-axis delta, CELL / |cos|, so it is infinite exactly
    # where the cosine is zero: due north and due south.
    assert parallel == [blackice.TRIG_TABLE_SIZE // 4, 3 * blackice.TRIG_TABLE_SIZE // 4], \
        "the never-crosses sentinel is not on the two axes with a zero cosine"


def test_the_dda_reaches_the_far_corner_of_the_overclock_radius(lib):
    """DDA_MAX_STEPS bounds the worst-case frame, and a bound set too low is
    invisible: rays just stop early and the wall they should have hit is drawn
    as far fill.  A diagonal ray at radius 20 crosses about 40 grid lines, so
    this fails outright at any cap below that."""
    # Sized so the diagonal to the far corner is just INSIDE the OVERCLOCK
    # radius: the ray must be allowed to run its full length, and at 45 degrees
    # a ray of that length crosses about 35 grid lines.
    width = height = 15
    cells = [1 if (x in (0, width - 1) or y in (0, height - 1)) else 0
             for y in range(height) for x in range(width)]
    level = make_level(lib, width, height, cells, (1, 1))
    state = state_at_full_width(lib, level)
    state.throttle = CONST["THROTTLE_OVERCLOCK"]
    scratch = blackice.RenderScratch()

    # Standing in the corner looking along the diagonal: every ray runs most of
    # the radius through empty floor before the far wall stops it.
    state.player.x = 1 * CELL + CENTRE
    state.player.y = 1 * CELL + CENTRE
    state.player.angle = CONST["ANGLE_QUARTER_TURN"] // 2        # south-east
    lib.render_cast(ctypes.byref(state), ctypes.byref(scratch))

    far = sum(1 for c in range(CONST["RENDER_COLUMNS_HIGH"])
              if scratch.columns[c].tex_id == CONST["COLUMN_TEX_FAR"])
    assert far == 0, "%d rays gave up before reaching the far wall" % far

    # The longest of these rays needs roughly two steps per cell of travel, so
    # a cap anywhere near 16 leaves the far wall unfound.
    reached = max(scratch.wall_dist[c] for c in range(CONST["RENDER_COLUMNS_HIGH"]))
    assert reached > 12 * CELL, "the longest ray only reached %d units" % reached


# Sub-cell offsets that put the eye a few units from a grid line.  This is the
# only place the near-axis delta bug can show: the first crossing of the
# near-parallel axis lands INSIDE the trace only when the distance to that
# axis's next grid line is under about 32 units, and every other test in this
# file deliberately stands in the middle of a cell.
NEAR_GRID_LINE_OFFSETS = (2, 7, 18, 31, 226, 239, 250, 254)
#: Angles within a degree or so of each axis, where a delta distance is huge.
NEAR_AXIS_ANGLES = (0, 3, 40, 16384 - 40, 16384, 16384 + 3, 32768, 49152 + 40)
#: One unit: fine enough to order two crossings that are a few units apart.
FINE_MARCH_STEP_UNITS = 1.0
#: The other axis sits here, well clear of any line.
MID_CELL_OFFSET = 128


@pytest.mark.parametrize("seed", range(4))
def test_dda_matches_the_marcher_from_within_a_hair_of_a_grid_line(lib, seed):
    """The near-axis case, which every guard in the sweep above throws away.

    A ray running almost parallel to one axis gains a huge ray length per cell
    of travel along it - up to 41,943 map units.  Clamping that number DOWN, as
    the first version did, makes the DDA believe it crosses that grid line up
    to 23% early, so it walks into the next row of cells too soon and reports
    whatever is there.  It only bites when the eye starts within a few units of
    the line, which is exactly where this stands.
    """
    cells, width, height, start, rng = random_map(seed, density=0.28)
    level = make_level(lib, width, height, cells, start)
    state = state_at_full_width(lib, level)
    state.throttle = CONST["THROTTLE_OVERCLOCK"]
    scratch = blackice.RenderScratch()

    sines = blackice.table(lib, "g_sin_1024", ctypes.c_int16, blackice.TRIG_TABLE_SIZE)
    columns = CONST["RENDER_COLUMNS_HIGH"]
    col_angle = blackice.table(lib, "g_col_angle_high", ctypes.c_int16, columns)
    col_cos = blackice.table(lib, "g_col_cos_high", ctypes.c_uint16, columns)
    radius_units = CONST["RENDER_RADIUS_OVERCLOCK"] * CELL

    # One axis near its grid line at a time.  With BOTH near one, the eye is a
    # few units from a cell CORNER and which of the two crossings comes first
    # is decided by the last bit of the quantised angle - a genuinely ambiguous
    # case that says nothing about the clamp this test is here for.
    positions = ([(offset, MID_CELL_OFFSET) for offset in NEAR_GRID_LINE_OFFSETS]
                 + [(MID_CELL_OFFSET, offset) for offset in NEAR_GRID_LINE_OFFSETS])

    compared = 0
    mismatches = []
    for offset_x, offset_y in positions:
        for angle in NEAR_AXIS_ANGLES:
            state.player.x = start[0] * CELL + offset_x
            state.player.y = start[1] * CELL + offset_y
            state.player.angle = angle & 0xffff
            lib.render_cast(ctypes.byref(state), ctypes.byref(scratch))

            for column in range(0, columns, 11):
                ray = (state.player.angle + col_angle[column]) & 0xffff
                index = (ray >> 6) & (blackice.TRIG_TABLE_SIZE - 1)
                sine = sines[index] / TRIG_ONE
                cosine = sines[(index + blackice.TRIG_TABLE_SIZE // 4)
                               % blackice.TRIG_TABLE_SIZE] / TRIG_ONE
                if sine == 0 or cosine == 0:
                    continue
                reference = march(cells, width, state.player.x, state.player.y,
                                  cosine, sine, radius_units, FINE_MARCH_STEP_UNITS)
                got = scratch.columns[column]
                if reference is None or got.tex_id == CONST["COLUMN_TEX_FAR"]:
                    continue
                length, side, hit_x, hit_y, value = reference
                if near_a_cell_edge(hit_y if side == SIDE_EW else hit_x):
                    continue
                compared += 1
                perp = length * col_cos[column] / TRIG_ONE
                if got.tex_id != value or \
                        abs(scratch.wall_dist[column] - perp) > DISTANCE_TOLERANCE_UNITS:
                    mismatches.append(
                        "offset (%d,%d) angle %d column %d: cell %d at %d, "
                        "marcher says cell %d at %.0f"
                        % (offset_x, offset_y, angle, column, got.tex_id,
                           scratch.wall_dist[column], value, perp))

    assert compared > 200, "only %d columns survived the guards" % compared
    assert not mismatches, "%d of %d columns disagree:\n  %s" % (
        len(mismatches), compared, "\n  ".join(mismatches[:6]))


def test_a_ray_running_along_a_grid_line_crosses_it_where_the_geometry_says(lib):
    """The exact shape of the near-axis clamp bug, built on purpose.

    Stand a few units below a grid line and look almost due east, drifting
    north.  The ray crosses that line after `gap / |sin|` units - about 1,150
    here, four and a half cells along.  Clamp the delta distance to a value
    BELOW the truth and the crossing moves to 875, three and a half cells
    along, and the DDA spends a whole cell in the wrong ROW.

    A body can never stand within its own radius of a wall, so the wrong row is
    always open ground next to the eye - but a pillar FURTHER ALONG that row is
    hit a cell early, and reported 23% nearer than it is.  That pillar is what
    this map is: everything else on the ray's path is clear.
    """
    width = height = 24
    eye_cell_x, eye_cell_y = 4, 12
    pillar = (eye_cell_x + 3, eye_cell_y - 1)
    cells = [1 if (x in (0, width - 1) or y in (0, height - 1)) else 0
             for y in range(height) for x in range(width)]
    cells[pillar[1] * width + pillar[0]] = 5
    level = make_level(lib, width, height, cells, (eye_cell_x, eye_cell_y))
    state = state_at_full_width(lib, level)
    state.throttle = CONST["THROTTLE_OVERCLOCK"]
    scratch = blackice.RenderScratch()

    sines = blackice.table(lib, "g_sin_1024", ctypes.c_int16, blackice.TRIG_TABLE_SIZE)
    columns = CONST["RENDER_COLUMNS_HIGH"]
    col_angle = blackice.table(lib, "g_col_angle_high", ctypes.c_int16, columns)
    col_cos = blackice.table(lib, "g_col_cos_high", ctypes.c_uint16, columns)
    radius_units = CONST["RENDER_RADIUS_OVERCLOCK"] * CELL

    compared = 0
    mismatches = []
    for gap in (4, 7, 11, 18, 26):
        # A hair below the grid line at the top of the eye's row, looking east
        # with the faintest northward drift the angle table can express.
        state.player.x = eye_cell_x * CELL + CENTRE
        state.player.y = eye_cell_y * CELL + gap
        for angle in range(65535, 65535 - 640, -64):
            state.player.angle = angle
            lib.render_cast(ctypes.byref(state), ctypes.byref(scratch))

            for column in range(columns):
                ray = (state.player.angle + col_angle[column]) & 0xffff
                index = (ray >> 6) & (blackice.TRIG_TABLE_SIZE - 1)
                sine = sines[index] / TRIG_ONE
                cosine = sines[(index + blackice.TRIG_TABLE_SIZE // 4)
                               % blackice.TRIG_TABLE_SIZE] / TRIG_ONE
                if sine >= 0 or cosine <= 0:
                    continue                    # only the north-east quadrant runs the line
                reference = march(cells, width, state.player.x, state.player.y,
                                  cosine, sine, radius_units, FINE_MARCH_STEP_UNITS)
                got = scratch.columns[column]
                if reference is None or got.tex_id == CONST["COLUMN_TEX_FAR"]:
                    continue
                length, side, hit_x, hit_y, value = reference
                if near_a_cell_edge(hit_y if side == SIDE_EW else hit_x):
                    continue
                compared += 1
                perp = length * col_cos[column] / TRIG_ONE
                if got.tex_id != value or \
                        abs(scratch.wall_dist[column] - perp) > DISTANCE_TOLERANCE_UNITS:
                    mismatches.append(
                        "gap %d angle %d column %d: cell %d at %d, marcher says cell %d at %.0f"
                        % (gap, angle, column, got.tex_id, scratch.wall_dist[column],
                           value, perp))

    assert compared > 100, "only %d columns survived the guards" % compared
    assert not mismatches, "%d of %d columns disagree:\n  %s" % (
        len(mismatches), compared, "\n  ".join(mismatches[:6]))
