"""Movement, collision and the wall slide.

Sliding is the mechanic the whole game's feel rests on: a corridor raycaster
where you stick to walls is unplayable, and the fix - attempt x and y as
separate moves - is one `if` that is easy to lose in a refactor.
"""
import ctypes

import pytest

import blackice
from blackice import CONST, make_level

CELL = blackice.CELL
CENTRE = blackice.CENTRE
place = blackice.place
SPEED_NOMINAL = CONST["THROTTLE_SPEED_NOMINAL"]


def open_room(lib, width=8, height=8, extra_walls=()):
    return blackice.sealed_room(lib, width, height, extra_walls, start_cell=(4, 4))


def test_walking_forward_moves_along_the_view_direction(lib):
    level = open_room(lib)
    state = blackice.new_state(lib, level)
    place(state, 4, 4, 0)                           # due east
    before = (state.player.x, state.player.y)

    lib.game_step(ctypes.byref(state), CONST["INPUT_FORWARD"])

    expected = CONST["PLAYER_MOVE_SPEED"] * SPEED_NOMINAL >> 8
    assert state.player.x - before[0] == pytest.approx(expected, abs=1)
    assert state.player.y == before[1]


def test_a_wall_stops_the_axis_it_blocks(lib):
    level = open_room(lib)
    state = blackice.new_state(lib, level)
    place(state, 6, 4, 0, offset=(CELL - CONST["PLAYER_RADIUS"] - 2, CENTRE))
    before = state.player.x

    for _ in range(6):
        lib.game_step(ctypes.byref(state), CONST["INPUT_FORWARD"])

    assert state.player.x >= before
    assert state.player.x + CONST["PLAYER_RADIUS"] <= 7 * CELL


def test_a_diagonal_move_into_a_wall_slides_along_it(lib):
    """Pushing north-east into the north wall must still deliver the east
    component.  This is the whole point of the axis-separated collider."""
    level = open_room(lib)
    state = blackice.new_state(lib, level)
    # Facing north-east, hard against the north wall.
    place(state, 4, 1, CONST["ANGLE_QUARTER_TURN"] * 7 // 2,
          offset=(CENTRE, CONST["PLAYER_RADIUS"] + 1))
    before = (state.player.x, state.player.y)

    for _ in range(4):
        lib.game_step(ctypes.byref(state), CONST["INPUT_FORWARD"])

    assert state.player.x > before[0], "the free axis was lost: no slide"
    assert state.player.y >= CONST["PLAYER_RADIUS"] + CELL - 1, "walked into the wall"


def test_the_body_never_ends_a_tick_inside_a_wall(lib):
    """A soak: whatever the input, the collider's post-condition holds."""
    import random

    level = open_room(lib, extra_walls=[(3, 3), (5, 5), (3, 5)])
    state = blackice.new_state(lib, level)
    place(state, 4, 4, 0)
    rng = random.Random(7)
    moves = [CONST["INPUT_FORWARD"], CONST["INPUT_BACK"],
             CONST["INPUT_STRAFE_LEFT"], CONST["INPUT_STRAFE_RIGHT"],
             CONST["INPUT_TURN_LEFT"], CONST["INPUT_TURN_RIGHT"]]

    for _ in range(600):
        lib.game_step(ctypes.byref(state), rng.choice(moves) | rng.choice(moves))
        radius = CONST["PLAYER_RADIUS"]
        for dx in (-radius, radius):
            for dy in (-radius, radius):
                cell_x = (state.player.x + dx) >> 8
                cell_y = (state.player.y + dy) >> 8
                index = cell_y * level.width + cell_x
                assert state.blocking.solid[index >> 3] & (1 << (index & 7)) == 0


def test_the_throttle_scales_the_speed(lib):
    level = open_room(lib)
    distances = []
    for throttle in range(CONST["THROTTLE_MODE_COUNT"]):
        state = blackice.new_state(lib, level)
        state.throttle = throttle
        place(state, 2, 4, 0)
        before = state.player.x
        for _ in range(5):
            lib.game_step(ctypes.byref(state), CONST["INPUT_FORWARD"])
        distances.append(state.player.x - before)

    # UNDERCLOCK is the fastest and OVERCLOCK the slowest, per DESIGN 5.
    assert distances[CONST["THROTTLE_UNDERCLOCK"]] > distances[CONST["THROTTLE_NOMINAL"]]
    assert distances[CONST["THROTTLE_NOMINAL"]] > distances[CONST["THROTTLE_OVERCLOCK"]]


def test_a_concave_corner_slides_to_an_exact_position(lib):
    """The collider tries x, then y.  Swapping the two axes still slides, still
    keeps the body out of the wall, and still passes every inequality above -
    it just ends somewhere else.  So this pins the landing spot exactly, and
    the cell the move reported bumping.

    The corner is at (5, 5): a wall to the east and a wall to the south, with
    the body pushed south-east into both.
    """
    level = open_room(lib, extra_walls=[(5, 4), (4, 5), (5, 5)])
    state = blackice.new_state(lib, level)
    radius = CONST["PLAYER_RADIUS"]
    speed = CONST["PLAYER_MOVE_SPEED"] * SPEED_NOMINAL >> 8
    place(state, 4, 4, CONST["ANGLE_QUARTER_TURN"] // 2)     # facing south-east

    for _ in range(20):
        lib.game_step(ctypes.byref(state), CONST["INPUT_FORWARD"])

    # Both axes are blocked by the corner, so the body ends flush against both
    # faces and nowhere else.  A speed's worth of tolerance covers the last
    # partial step; without it the test would pin the step phase, not the wall.
    east_face = 5 * CELL
    south_face = 5 * CELL
    assert east_face - radius - speed <= state.player.x <= east_face - radius
    assert south_face - radius - speed <= state.player.y <= south_face - radius


def test_a_wall_on_one_axis_delivers_the_other_axis_exactly(lib):
    """The single-axis case, pinned to a number.  Swapping the axis order makes
    this deliver the WRONG component while still looking like a slide."""
    level = open_room(lib, extra_walls=[(4, 3)])             # a wall due north
    state = blackice.new_state(lib, level)
    speed = CONST["PLAYER_MOVE_SPEED"] * SPEED_NOMINAL >> 8
    # Facing north-east, hard up against the wall's south face.
    place(state, 4, 4, CONST["ANGLE_QUARTER_TURN"] * 7 // 2,
          offset=(CENTRE, CONST["PLAYER_RADIUS"] + 1))
    before = (state.player.x, state.player.y)

    lib.game_step(ctypes.byref(state), CONST["INPUT_FORWARD"])

    # A 45-degree move of `speed` units delivers speed/sqrt(2) on each axis; y
    # is refused by the wall, x is not.
    expected_x = before[0] + round(speed * 0.7071)
    assert abs(state.player.x - expected_x) <= 2, \
        "the free axis delivered %d, expected about %d" % (state.player.x - before[0],
                                                           expected_x - before[0])
    assert state.player.y == before[1], "the blocked axis moved"


def test_the_blocked_axis_is_the_cell_that_gets_reported(lib):
    """`bumped_cell` is how a door learns it was walked into, and it is the
    other half of the axis order: swapping x and y reports the wrong cell.  A
    door in the blocked cell makes that observable without the test having to
    reach into the game layer for the raw value."""
    width = height = 8
    cells = [1 if (x in (0, width - 1) or y in (0, height - 1)) else 0
             for y in range(height) for x in range(width)]
    door_x, door_y = 4, 3
    other_x, other_y = 5, 4             # the free axis: a door here must NOT open
    cells[door_y * width + door_x] = CONST["DOOR_PLAIN"]
    cells[other_y * width + other_x] = CONST["DOOR_PLAIN"]
    level = make_level(lib, width, height, cells, (4, 4))
    state = blackice.new_state(lib, level)

    # Facing north-east against the north door: y is refused, x is delivered.
    place(state, 4, 4, CONST["ANGLE_QUARTER_TURN"] * 7 // 2,
          offset=(CENTRE, CONST["PLAYER_RADIUS"] + 1))
    lib.game_step(ctypes.byref(state), CONST["INPUT_FORWARD"])

    opened = {state.doors[i].cell for i in range(state.door_count)
              if state.doors[i].state != CONST["DOOR_STATE_CLOSED"]}
    assert opened == {door_y * width + door_x}, \
        "the blocked axis reported the wrong cell: %r" % sorted(opened)


def test_the_x_axis_is_attempted_before_the_y_axis(lib):
    """Axis-separated collision is order-dependent, and the order is a choice.

    Where ONE axis is blocked the order cannot be seen: the free component is
    delivered either way.  It shows only at an OUTSIDE corner approached
    diagonally, where the first axis's move is what puts the body beside the
    wall that then refuses the second.  Here x goes first, so x is delivered and
    y is refused; the other order gives the mirror-image position, slides just
    as convincingly, and passes every other test in this file.
    """
    wall_x, wall_y = 5, 5
    level = open_room(lib, extra_walls=[(wall_x, wall_y)])
    state = blackice.new_state(lib, level)
    radius = CONST["PLAYER_RADIUS"]

    # Placed so the body clears the wall on both axes standing still, and a
    # single diagonal step brings exactly one axis into contact with it.
    approach = wall_x * CELL - radius - 8
    place(state, 4, 4, CONST["ANGLE_QUARTER_TURN"] // 2,        # south-east
          offset=(approach - 4 * CELL, approach - 4 * CELL))
    before = (state.player.x, state.player.y)
    assert before[0] + radius < wall_x * CELL, "the body already touches the wall"

    lib.game_step(ctypes.byref(state), CONST["INPUT_FORWARD"])

    assert state.player.x > before[0], "x was not delivered: the axes are the wrong way round"
    assert state.player.y == before[1], "y was delivered: the axes are the wrong way round"
    assert state.player.x + radius > wall_x * CELL, \
        "the step was too short to bring the body against the wall at all"
