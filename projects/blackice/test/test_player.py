"""Movement, collision and the wall slide.

Sliding is the mechanic the whole game's feel rests on: a corridor raycaster
where you stick to walls is unplayable, and the fix - attempt x and y as
separate moves - is one `if` that is easy to lose in a refactor.
"""
import ctypes

import pytest

import blackice
from blackice import CONST
from test_raycast import make_level

CELL = blackice.CELL_UNITS
CENTRE = CELL // 2
SPEED_NOMINAL = CONST["THROTTLE_SPEED_NOMINAL"]


def open_room(lib, width=8, height=8, extra_walls=()):
    cells = [1 if (x in (0, width - 1) or y in (0, height - 1)) else 0
             for y in range(height) for x in range(width)]
    for x, y in extra_walls:
        cells[y * width + x] = 1
    return make_level(lib, width, height, cells, (4, 4))


def place(state, cell_x, cell_y, angle, offset=(CENTRE, CENTRE)):
    state.player.x = cell_x * CELL + offset[0]
    state.player.y = cell_y * CELL + offset[1]
    state.player.angle = angle


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
