"""Pickups and the doors they unlock.

DESIGN 6 gives the game no use key: you collect by standing on it and you open
by walking into it.  So these are two halves of one verb and they are tested
together.
"""
import ctypes

import pytest

import aihelp
from aihelp import CELL, CENTRE
from aihelp import glib          # noqa: F401 - the session fixture the tests take
from blackice import CONST

# brad 256 = east.  The base rate is zeroed so every trace assertion below is
# the one-shot it names and not that plus however long the walk took.
HEADER = "# name: PICKUPS\n# start_facing: 256\n# trace_base_rate: 0\n\n"
FORWARD = CONST["INPUT_FORWARD"]
MILLI = CONST["TRACE_MILLI_PER_PERCENT"]


def corridor(glib, glyphs):
    """A west-east corridor with the player at the west end and `glyphs`
    laid out east of it, one per cell."""
    row = "#@" + glyphs + "." * 2 + "#"
    rows = ["#" * len(row), row, "#" * len(row)]
    return aihelp.level_from_rows(glib, rows, HEADER)


def walk_east(glib, state, ticks):
    for _ in range(ticks):
        aihelp.step(glib, state, FORWARD)


# ---------------------------------------------------------------------------
# collecting
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("glyph,field,gain", [
    ("c", "cycles", CONST["PICKUP_CYCLES_SMALL"]),
    ("C", "cycles", CONST["PICKUP_CYCLES_LARGE"]),
    ("i", "integrity", CONST["PICKUP_INTEGRITY_SMALL"]),
    ("I", "integrity", CONST["PICKUP_INTEGRITY_LARGE"]),
])
def test_walking_over_a_pickup_collects_its_value(glib, glyph, field, gain):
    level = corridor(glib, glyph)
    state = aihelp.new_state(glib, level)
    # Take a hit's worth of damage first, so an integrity pickup has room.
    state.game.integrity = 50
    state.game.cycles = 50
    before = getattr(state.game, field)

    walk_east(glib, state, 20)
    assert state.engine.entity_alive[0] == 0, "the pickup should be gone"
    assert getattr(state.game, field) == before + gain


def test_a_pickup_never_takes_you_past_the_cap(glib):
    level = corridor(glib, "C")
    state = aihelp.new_state(glib, level)
    state.game.cycles = CONST["PLAYER_CYCLES_MAX"] - 1

    walk_east(glib, state, 20)
    assert state.game.cycles == CONST["PLAYER_CYCLES_MAX"]


def test_a_scrubber_takes_twenty_percent_off_the_meter(glib):
    level = corridor(glib, "u")
    state = aihelp.new_state(glib, level)
    glib.trace_apply(aihelp.ref(state), 50 * MILLI)
    before = state.engine.trace_milli

    walk_east(glib, state, 20)
    assert state.engine.entity_alive[0] == 0
    assert state.engine.trace_milli == before - CONST["TRACE_DROP_SCRUBBER"]


def test_a_data_cache_is_counted_for_the_results_screen(glib):
    level = corridor(glib, "d")
    state = aihelp.new_state(glib, level)

    walk_east(glib, state, 20)
    assert state.game.data_caches == 1


@pytest.mark.parametrize("glyph,bit,message", [
    ("p", CONST["TOKEN_ALPHA_BIT"], CONST["EV_MSG_TOKEN_ALPHA"]),
    ("q", CONST["TOKEN_BETA_BIT"], CONST["EV_MSG_TOKEN_BETA"]),
    ("r", CONST["TOKEN_GAMMA_BIT"], CONST["EV_MSG_TOKEN_GAMMA"]),
])
def test_a_token_lands_in_the_ledger_and_announces_itself(glib, glyph, bit, message):
    level = corridor(glib, glyph)
    state = aihelp.new_state(glib, level)
    aihelp.clear_events(state)

    walk_east(glib, state, 20)
    assert state.game.tokens & bit
    events = aihelp.drain_events(state)
    assert message in events
    assert CONST["EV_SFX_TOKEN_GRAB"] in events


def test_a_pickup_out_of_reach_is_not_collected(glib):
    """The reach is the pickup's own cell, so standing in the next one over
    must not sweep it up."""
    level = corridor(glib, "c")
    state = aihelp.new_state(glib, level)
    assert state.engine.entity_alive[0] == 1

    aihelp.step(glib, state)                # a tick with no movement at all
    assert state.engine.entity_alive[0] == 1


def test_every_pickup_type_disappears_from_the_sprite_list(glib):
    """A collected pickup must stop being drawn, which is entity_alive."""
    level = corridor(glib, "cCiIupqrd")
    state = aihelp.new_state(glib, level)
    count = level.entity_count
    assert count == 9

    walk_east(glib, state, 120)
    alive = sum(state.engine.entity_alive[i] for i in range(count))
    assert alive == 0, "the walk crossed every cell; nothing should be left"


# ---------------------------------------------------------------------------
# token doors
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant,bit", [
    (CONST["DOOR_LOCK_ALPHA"], CONST["TOKEN_ALPHA_BIT"]),
    (CONST["DOOR_LOCK_BETA"], CONST["TOKEN_BETA_BIT"]),
    (CONST["DOOR_LOCK_GAMMA"], CONST["TOKEN_GAMMA_BIT"]),
])
def test_each_locked_variant_names_its_own_token(glib, variant, bit):
    assert glib.door_required_token(variant) == bit


def test_a_plain_gate_and_a_sealed_one_demand_nothing(glib):
    assert glib.door_required_token(CONST["DOOR_PLAIN"]) == 0
    assert glib.door_required_token(CONST["DOOR_SEALED"]) == 0


LOCKED_CORRIDOR = ["########",
                   "#@..1..#",
                   "########"]


def locked_state(glib):
    level = aihelp.level_from_rows(glib, LOCKED_CORRIDOR, HEADER)
    return level, aihelp.new_state(glib, level)


def test_a_locked_door_refuses_without_its_token(glib):
    level, state = locked_state(glib)
    door_cell = aihelp.cell(level, 4, 1)
    aihelp.clear_events(state)

    walk_east(glib, state, 40)
    assert state.engine.doors[0].state == CONST["DOOR_STATE_CLOSED"]
    assert state.engine.player.x < door_cell % level.width * CELL, "it should have stopped"

    events = aihelp.drain_events(state)
    assert CONST["EV_MSG_ALPHA_REQUIRED"] in events
    assert CONST["EV_SFX_DOOR_REFUSAL"] in events


def test_leaning_on_a_locked_door_refuses_once_and_not_every_tick(glib):
    """DESIGN 15.1 gives the message line a 2 s timeout; a refusal repeated at
    25 Hz would be a stuck line and a stuck tone."""
    _, state = locked_state(glib)
    walk_east(glib, state, 30)                  # arrive and lean
    aihelp.clear_events(state)
    walk_east(glib, state, 30)                  # keep leaning

    events = aihelp.drain_events(state)
    assert CONST["EV_MSG_ALPHA_REQUIRED"] not in events


def test_a_locked_door_opens_with_its_token_charges_three_percent_and_latches(glib):
    """DESIGN 10: the door PERMANENTLY becomes a plain gate and the +3% fires
    once per door per sector, so a second pass through it is free."""
    level, state = locked_state(glib)
    state.game.tokens = CONST["TOKEN_ALPHA_BIT"]
    before = state.engine.trace_milli

    walk_east(glib, state, 40)
    assert state.engine.doors[0].state != CONST["DOOR_STATE_CLOSED"]
    assert state.engine.doors[0].variant == CONST["DOOR_PLAIN"], "it must latch"

    assert state.engine.trace_milli - before == CONST["TRACE_BUMP_LOCKED_DOOR"]

    # Walk back into it once it has shut again: no second charge.
    for _ in range(CONST["DOOR_OPEN_TICKS"] + CONST["DOOR_CLOSING_TICKS"] + 4):
        aihelp.step(glib, state, CONST["INPUT_BACK"])
    marker = state.engine.trace_milli
    walk_east(glib, state, 40)
    assert state.engine.trace_milli == marker, "a latched door is free to re-open"


def test_taking_the_token_then_the_door_is_the_whole_route(glib):
    """The DESIGN 12 shape in miniature: the token is on the way to the gate it
    opens, and picking it up is the only thing that changes the outcome."""
    rows = ["#########",
            "#@.p.1..#",
            "#########"]
    level = aihelp.level_from_rows(glib, rows, HEADER)
    state = aihelp.new_state(glib, level)

    walk_east(glib, state, 60)
    assert state.game.tokens & CONST["TOKEN_ALPHA_BIT"]
    assert state.engine.doors[0].variant == CONST["DOOR_PLAIN"]


# ---------------------------------------------------------------------------
# the terminal doors
# ---------------------------------------------------------------------------

def test_touching_the_sector_exit_ends_the_level(glib):
    """DESIGN 10: variant 23 is terminal - entering the cell ends the level, and
    the leaf never opens, which is what keeps the map border sealed."""
    rows = ["####>###",
            "#@.....#",
            "########"]
    level = aihelp.level_from_rows(glib, rows, HEADER)
    state = aihelp.new_state(glib, level)
    aihelp.clear_events(state)

    # Walk east under the arch, then north into it.
    for _ in range(60):
        aihelp.step(glib, state, FORWARD)
        if state.game.phase != CONST["PHASE_PLAYING"]:
            break
    state.engine.player.x = 4 * CELL + CENTRE
    state.engine.player.angle = 3 * CONST["ANGLE_QUARTER_TURN"]     # north
    for _ in range(40):
        aihelp.step(glib, state, FORWARD)
        if state.game.phase != CONST["PHASE_PLAYING"]:
            break

    assert state.game.phase == CONST["PHASE_LEVEL_CLEAR"]
    assert state.game.next_sector_index == level.sector_index + 1
    assert CONST["EV_MSG_SECTOR_CLEAR"] in aihelp.drain_events(state)
    assert state.engine.doors[0].state == CONST["DOOR_STATE_CLOSED"], \
        "a terminal door must never travel"


def test_the_sealed_gate_refuses_and_stays_shut(glib):
    rows = ["########",
            "#@.....#",
            "####S###"]
    level = aihelp.level_from_rows(glib, rows, HEADER)
    state = aihelp.new_state(glib, level)
    aihelp.clear_events(state)

    state.engine.player.x = 4 * CELL + CENTRE
    state.engine.player.angle = CONST["ANGLE_QUARTER_TURN"]         # south
    for _ in range(40):
        aihelp.step(glib, state, FORWARD)

    assert state.game.phase == CONST["PHASE_PLAYING"]
    assert state.engine.doors[0].state == CONST["DOOR_STATE_CLOSED"]
    assert CONST["EV_MSG_GATE_SEALED"] in aihelp.drain_events(state)


# ---------------------------------------------------------------------------
# damage and death
# ---------------------------------------------------------------------------

def test_taking_a_hit_costs_integrity_and_one_percent_of_trace(glib):
    level = corridor(glib, ".")
    state = aihelp.new_state(glib, level)
    before_trace = state.engine.trace_milli
    before_hp = state.game.integrity

    glib.sim_damage_player(aihelp.ref(state), 12)  # a Watchdog bite
    assert state.game.integrity == before_hp - 12
    assert state.engine.trace_milli - before_trace == CONST["TRACE_BUMP_PLAYER_HIT"]
    assert CONST["EV_SFX_PLAYER_HIT"] in aihelp.drain_events(state)


def test_running_out_of_integrity_ends_the_run_and_freezes_the_sim(glib):
    level = corridor(glib, ".")
    state = aihelp.new_state(glib, level)

    glib.sim_damage_player(aihelp.ref(state), CONST["PLAYER_INTEGRITY_MAX"])
    assert state.game.phase == CONST["PHASE_DEAD"]
    assert state.game.integrity == 0
    assert state.game.deaths_this_sector == 1
    assert CONST["EV_MSG_CONNECTION_TERMINATED"] in aihelp.drain_events(state)

    # DESIGN 15: the sim is frozen, so nothing moves and the timer stops.
    ticks = state.game.route_ticks
    walk_east(glib, state, 20)
    assert state.game.route_ticks == ticks


def test_a_retry_restarts_the_sector_and_carries_the_death_cost(glib):
    """DESIGN 15: retries are unlimited and restart the current sector; each
    death is +10% starting trace, capped by trace_carry_cap."""
    level = corridor(glib, ".")
    state = aihelp.new_state(glib, level)
    glib.sim_damage_player(aihelp.ref(state), CONST["PLAYER_INTEGRITY_MAX"])

    progress = aihelp.RunProgress()
    glib.run_progress_reset(ctypes.byref(progress))
    progress.deaths_this_sector = state.game.deaths_this_sector
    glib.game_start_level(aihelp.ref(state), ctypes.byref(level),
                          level.rng_seed, ctypes.byref(progress))

    assert state.game.phase == CONST["PHASE_PLAYING"]
    assert state.game.integrity == CONST["PLAYER_INTEGRITY_MAX"]
    assert state.engine.trace_milli == CONST["TRACE_START_PER_DEATH"] * MILLI


# ---------------------------------------------------------------------------
# the reach, to the map unit
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("offset,collected", [
    (CONST["PICKUP_REACH_UNITS"] - 1, True),
    (CONST["PICKUP_REACH_UNITS"], False),
])
def test_the_pickup_reach_is_exactly_the_pickup_cell(glib, offset, collected):
    """DESIGN 10 and DESIGN 17.1: a pickup is collected anywhere inside its own
    cell and nowhere else, so the reach is half a cell from its centre.  A walk
    that only ever ends up standing on the sprite cannot tell a reach of half a
    cell from one of two cells, or from one of an eighth."""
    level = corridor(glib, "c")
    state = aihelp.new_state(glib, level)
    body = state.game.entities[0]
    # Stand the player due east of the pickup by the offset under test and take
    # a tick with no movement, so the collider cannot walk the gap closed.
    state.engine.player.x = body.x + offset
    state.engine.player.y = body.y

    aihelp.step(glib, state)
    assert (state.engine.entity_alive[0] == 0) == collected, \
        "%d map units from the centre of a %d-unit cell" % (offset, CELL)
