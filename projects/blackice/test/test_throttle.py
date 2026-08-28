"""The clock throttle, driven the way the player drives it: through input.

DESIGN 5 makes changing gear cost a tick and lock the controls for twelve more.
Every part of that is edge-triggered state in game_step, and edge-triggered
state is exactly what a test that pokes `state.throttle` directly cannot see -
which is how "holding the key re-fires when the lock expires" survived.
"""
import ctypes

import blackice
from blackice import CONST

THROTTLE = CONST["INPUT_THROTTLE_NEXT"]
FORWARD = CONST["INPUT_FORWARD"]
LOCK_TICKS = CONST["THROTTLE_SWITCH_TICKS"]
MODES = CONST["THROTTLE_TOGGLE_MODES"]


def room(lib):
    return blackice.sealed_room(lib, 12, 12)


def test_a_press_advances_the_mode_and_locks_the_controls(lib):
    state = blackice.new_state(lib, room(lib))
    before = state.throttle

    lib.game_step(ctypes.byref(state), THROTTLE)

    assert state.throttle == (before + 1) % MODES
    assert state.throttle_lock == LOCK_TICKS


def test_holding_the_key_never_fires_twice(lib):
    """The bug: the lock zeroed the input word AND prev_input, so the tick the
    lock expired saw a fresh rising edge on a key that had never been let go.
    Hold it down for four full lock periods; it may fire exactly once."""
    state = blackice.new_state(lib, room(lib))
    first = state.throttle
    changes = 0

    for _ in range(LOCK_TICKS * 4):
        before = state.throttle
        lib.game_step(ctypes.byref(state), THROTTLE)
        if state.throttle != before:
            changes += 1

    assert changes == 1, "a held key changed gear %d times" % changes
    assert state.throttle == (first + 1) % MODES


def test_releasing_and_pressing_again_fires_again(lib):
    """...and the flip side: a real second press must still work, or the lock
    would have turned into a one-shot."""
    state = blackice.new_state(lib, room(lib))
    first = state.throttle

    lib.game_step(ctypes.byref(state), THROTTLE)
    for _ in range(LOCK_TICKS):
        lib.game_step(ctypes.byref(state), 0)          # released, lock running out
    assert state.throttle_lock == 0

    lib.game_step(ctypes.byref(state), THROTTLE)
    assert state.throttle == (first + 2) % MODES


def test_the_mode_wraps_round(lib):
    state = blackice.new_state(lib, room(lib))
    seen = [state.throttle]

    for _ in range(MODES):
        lib.game_step(ctypes.byref(state), THROTTLE)
        for _ in range(LOCK_TICKS):
            lib.game_step(ctypes.byref(state), 0)
        seen.append(state.throttle)

    assert seen[-1] == seen[0], "the mode did not wrap back to where it started"
    assert sorted(set(seen)) == list(range(MODES))


def test_the_switch_costs_the_tick_and_the_lock(lib):
    """DESIGN 5: changing gear costs input.  Movement pressed on the switching
    tick, and during the lock, must not move the player."""
    state = blackice.new_state(lib, room(lib))
    blackice.place(state, 6, 6, 0)
    before = (state.player.x, state.player.y)

    lib.game_step(ctypes.byref(state), THROTTLE | FORWARD)
    assert (state.player.x, state.player.y) == before, "the switching tick still moved"

    for tick in range(LOCK_TICKS):
        assert state.throttle_lock == LOCK_TICKS - tick
        lib.game_step(ctypes.byref(state), FORWARD)
        assert (state.player.x, state.player.y) == before, "tick %d of the lock moved" % tick

    assert state.throttle_lock == 0
    lib.game_step(ctypes.byref(state), FORWARD)
    assert (state.player.x, state.player.y) != before, "the lock never let go"
