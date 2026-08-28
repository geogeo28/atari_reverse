"""The door state machine.

CLOSED -> OPENING -> OPEN -> CLOSING -> CLOSED, with a body in the cell sending
a closing door back the other way.  Every transition is also a change to the
blocking bitmap, and it is the bitmap - not the state byte - that the collider
and the DDA read, so both are asserted together.
"""
import ctypes

import pytest

import blackice
from blackice import CONST, make_level

CELL = blackice.CELL
CENTRE = blackice.CENTRE


def corridor_with_door(lib, variant=None):
    """A 3x9 north-south corridor with a door in the middle."""
    variant = CONST["DOOR_PLAIN"] if variant is None else variant
    width, height = 3, 9
    cells = [1 if (x in (0, width - 1) or y in (0, height - 1)) else 0
             for y in range(height) for x in range(width)]
    cells[4 * width + 1] = variant
    return make_level(lib, width, height, cells, (1, 6))


def door_cell_index(level):
    return 4 * level.width + 1


def blocks(state, cell):
    return (state.blocking.solid[cell >> 3] >> (cell & 7)) & 1


def test_a_new_door_is_closed_and_blocking(lib):
    level = corridor_with_door(lib)
    state = blackice.new_state(lib, level)

    assert state.door_count == 1
    assert state.doors[0].state == CONST["DOOR_STATE_CLOSED"]
    assert blocks(state, door_cell_index(level))
    assert state.door_of_cell[door_cell_index(level)] == 0


def test_touching_a_door_runs_the_whole_cycle(lib):
    level = corridor_with_door(lib)
    state = blackice.new_state(lib, level)
    cell = door_cell_index(level)

    assert lib.game_touch_door(ctypes.byref(state), cell) == 1
    assert state.doors[0].state == CONST["DOOR_STATE_OPENING"]

    # OPENING still blocks, all the way to the last tick of its travel.
    for _ in range(CONST["DOOR_OPENING_TICKS"] - 1):
        lib.game_step(ctypes.byref(state), 0)
        assert state.doors[0].state == CONST["DOOR_STATE_OPENING"]
        assert blocks(state, cell)

    lib.game_step(ctypes.byref(state), 0)
    assert state.doors[0].state == CONST["DOOR_STATE_OPEN"]
    assert not blocks(state, cell)

    for _ in range(CONST["DOOR_OPEN_TICKS"] - 1):
        lib.game_step(ctypes.byref(state), 0)
        assert state.doors[0].state == CONST["DOOR_STATE_OPEN"]

    lib.game_step(ctypes.byref(state), 0)
    assert state.doors[0].state == CONST["DOOR_STATE_CLOSING"]
    assert blocks(state, cell), "a closing door must stop a body immediately"

    for _ in range(CONST["DOOR_CLOSING_TICKS"] - 1):
        lib.game_step(ctypes.byref(state), 0)
        assert state.doors[0].state == CONST["DOOR_STATE_CLOSING"]
    lib.game_step(ctypes.byref(state), 0)
    assert state.doors[0].state == CONST["DOOR_STATE_CLOSED"]
    assert blocks(state, cell)


def test_a_body_in_the_cell_reopens_a_closing_door(lib):
    level = corridor_with_door(lib)
    state = blackice.new_state(lib, level)
    cell = door_cell_index(level)

    lib.game_touch_door(ctypes.byref(state), cell)
    for _ in range(CONST["DOOR_OPENING_TICKS"] + CONST["DOOR_OPEN_TICKS"]):
        lib.game_step(ctypes.byref(state), 0)
    # Standing in the doorway the tick it starts to close.
    state.player.x = 1 * CELL + CENTRE
    state.player.y = 4 * CELL + CENTRE
    assert state.doors[0].state == CONST["DOOR_STATE_CLOSING"]

    lib.game_step(ctypes.byref(state), 0)
    assert state.doors[0].state == CONST["DOOR_STATE_OPENING"]


def test_an_open_door_held_by_a_body_never_starts_closing(lib):
    level = corridor_with_door(lib)
    state = blackice.new_state(lib, level)
    cell = door_cell_index(level)

    lib.game_touch_door(ctypes.byref(state), cell)
    for _ in range(CONST["DOOR_OPENING_TICKS"]):
        lib.game_step(ctypes.byref(state), 0)
    state.player.x = 1 * CELL + CENTRE
    state.player.y = 4 * CELL + CENTRE

    for _ in range(CONST["DOOR_OPEN_TICKS"] * 2):
        lib.game_step(ctypes.byref(state), 0)
    assert state.doors[0].state == CONST["DOOR_STATE_OPEN"]


@pytest.mark.parametrize("variant", ["DOOR_SEALED", "DOOR_CORRUPTED"])
def test_fixed_variants_never_open(lib, variant):
    level = corridor_with_door(lib, CONST[variant])
    state = blackice.new_state(lib, level)
    cell = door_cell_index(level)

    assert lib.game_touch_door(ctypes.byref(state), cell) == 0
    for _ in range(CONST["DOOR_OPENING_TICKS"] * 4):
        lib.game_step(ctypes.byref(state), 0)
    assert state.doors[0].state == CONST["DOOR_STATE_CLOSED"]
    assert blocks(state, cell)


def test_walking_into_a_door_opens_it(lib):
    """DESIGN 6: there is no use key in the shipping controls, so bumping a
    door has to be a trigger of its own."""
    level = corridor_with_door(lib)
    state = blackice.new_state(lib, level)
    state.player.x = 1 * CELL + CENTRE
    state.player.y = 5 * CELL + CENTRE
    state.player.angle = 3 * CONST["ANGLE_QUARTER_TURN"]        # north, into the door

    for _ in range(12):
        lib.game_step(ctypes.byref(state), CONST["INPUT_FORWARD"])
    assert state.doors[0].state != CONST["DOOR_STATE_CLOSED"]


def test_a_closed_door_is_drawn_and_an_open_one_is_not(lib):
    """The two-state renderer: the DDA must hit a closed leaf and pass an open
    one, which is the only thing that makes an opened door readable."""
    level = corridor_with_door(lib)
    state = blackice.new_state(lib, level)
    state.detail_level = CONST["DETAIL_COLUMNS_160"]     # this test names that width
    scratch = blackice.RenderScratch()
    state.player.x = 1 * CELL + CENTRE
    state.player.y = 6 * CELL + CENTRE
    state.player.angle = 3 * CONST["ANGLE_QUARTER_TURN"]        # looking north at the door
    centre_column = CONST["RENDER_COLUMNS_HIGH"] // 2

    lib.render_cast(ctypes.byref(state), ctypes.byref(scratch))
    closed_distance = scratch.wall_dist[centre_column]
    assert scratch.columns[centre_column].tex_id == CONST["TEX_GATE_PANEL"]

    lib.game_touch_door(ctypes.byref(state), door_cell_index(level))
    for _ in range(CONST["DOOR_OPENING_TICKS"]):
        lib.game_step(ctypes.byref(state), 0)
    lib.render_cast(ctypes.byref(state), ctypes.byref(scratch))

    assert scratch.columns[centre_column].tex_id != CONST["TEX_GATE_PANEL"]
    assert scratch.wall_dist[centre_column] > closed_distance, "the ray did not pass through"


def test_an_open_door_re_arms_when_it_is_touched_again(lib):
    """Walking back into an open door must reset its hold timer.  Without that
    arm, a door you are standing in the doorway of starts closing on schedule
    and the player watches it shut in their face."""
    level = corridor_with_door(lib)
    state = blackice.new_state(lib, level)
    cell = door_cell_index(level)

    lib.game_touch_door(ctypes.byref(state), cell)
    for _ in range(CONST["DOOR_OPENING_TICKS"]):
        lib.game_step(ctypes.byref(state), 0)
    assert state.doors[0].state == CONST["DOOR_STATE_OPEN"]

    half = CONST["DOOR_OPEN_TICKS"] // 2
    for _ in range(half):
        lib.game_step(ctypes.byref(state), 0)
    assert state.doors[0].timer == CONST["DOOR_OPEN_TICKS"] - half

    assert lib.game_touch_door(ctypes.byref(state), cell) == 1
    assert state.doors[0].timer == CONST["DOOR_OPEN_TICKS"], "the hold timer was not re-armed"
    assert state.doors[0].state == CONST["DOOR_STATE_OPEN"], "a re-touch must not restart travel"


@pytest.mark.parametrize("variant", ["DOOR_LOCK_ALPHA", "DOOR_LOCK_BETA", "DOOR_LOCK_GAMMA"])
def test_a_locked_door_does_not_open_just_because_you_walked_into_it(lib, variant):
    """DESIGN 10 gives 17/18/19 to the token ledger.  The engine's default
    answer is no; the game layer replaces door_may_open to say yes."""
    level = corridor_with_door(lib, CONST[variant])
    state = blackice.new_state(lib, level)
    cell = door_cell_index(level)

    assert lib.game_touch_door(ctypes.byref(state), cell) == 0
    for _ in range(CONST["DOOR_OPENING_TICKS"] * 4):
        lib.game_step(ctypes.byref(state), 0)
    assert state.doors[0].state == CONST["DOOR_STATE_CLOSED"]
    assert blocks(state, cell)


def test_the_sector_exit_is_never_a_door_that_opens(lib):
    """A '>' is an arch in the OUTER wall.  Opening it would clear a border
    cell's solid bit, and the DDA - which has no bounds test - would walk
    straight out of the map through the hole."""
    level = corridor_with_door(lib, CONST["DOOR_SECTOR_EXIT"])
    state = blackice.new_state(lib, level)
    cell = door_cell_index(level)

    assert lib.game_touch_door(ctypes.byref(state), cell) == 0
    for _ in range(CONST["DOOR_OPEN_TICKS"] * 2):
        lib.game_step(ctypes.byref(state), 0)
    assert state.doors[0].state == CONST["DOOR_STATE_CLOSED"]
    assert blocks(state, cell), "the sector exit stopped blocking"
