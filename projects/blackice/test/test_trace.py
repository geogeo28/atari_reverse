"""The trace meter, pinned against DESIGN 9's own printed arithmetic.

DESIGN 9.1 prints a reference run for all eight levels and the net percentage
each one lands on.  That table is the tuning target for the whole game, so the
sim's per-second integration and the one-shot bumps are checked against it here
rather than against numbers restated in a test.
"""
import ctypes

import pytest

import aihelp
from aihelp import glib          # noqa: F401 - the session fixture the tests take
from blackice import CONST

MILLI = CONST["TRACE_MILLI_PER_PERCENT"]
SIM_HZ = CONST["SIM_HZ"]

# An empty room: no enemies, so nothing but the base rate moves the meter.
EMPTY_ROOM = [
    "#######",
    "#.....#",
    "#..@..#",
    "#.....#",
    "#######",
]


def empty_state(glib, base_rate=None, throttle=None):
    header = "# name: TRACE\n# start_facing: 0\n"
    if base_rate is not None:
        header += "# trace_base_rate: %d\n" % base_rate
    level = aihelp.level_from_rows(glib, EMPTY_ROOM, header + "\n")
    state = aihelp.new_state(glib, level)
    if throttle is not None:
        state.engine.throttle = throttle
    return state


# ---------------------------------------------------------------------------
# the per-second integration
# ---------------------------------------------------------------------------

SHIPPED_BASE_RATE = 180         # DESIGN 9.1: 0.18 %/s on every shipped level


def test_the_base_rate_is_per_second_and_integrates_without_drift(glib):
    """180 milli-percent per second over 25 ticks is 7.2 per tick, which is not
    an integer.  After a whole second the meter must be at exactly 180 - the
    remainder carry is the reason DESIGN 9.1's table is reachable at all."""
    state = empty_state(glib, base_rate=SHIPPED_BASE_RATE)
    for _ in range(SIM_HZ):
        aihelp.step(glib, state)
    assert state.engine.trace_milli == SHIPPED_BASE_RATE


def test_a_two_minute_par_run_lands_on_the_design_reference_base(glib):
    """DESIGN 9.1, level 1: par 2:00, base 0.18 x par = 21.6%.  Exactly."""
    state = empty_state(glib, base_rate=SHIPPED_BASE_RATE)
    par_ticks = 120 * SIM_HZ
    for _ in range(par_ticks):
        aihelp.step(glib, state)
    assert state.engine.trace_milli == 21600, "DESIGN 9.1 prints 21.6% for level 1"


@pytest.mark.parametrize("throttle,expected", [
    (CONST["THROTTLE_UNDERCLOCK"], 90),     # 0.18 x 0.5
    (CONST["THROTTLE_NOMINAL"], 180),       # 0.18 x 1.0
    (CONST["THROTTLE_OVERCLOCK"], 288),     # 0.18 x 1.6
])
def test_the_throttle_scales_the_rise(glib, throttle, expected):
    """DESIGN 5's trace multipliers are 0.5 / 1.0 / 1.6, and the rise - not the
    meter - is what they scale."""
    state = empty_state(glib, base_rate=SHIPPED_BASE_RATE, throttle=throttle)
    # Hold a movement input so the UNDERCLOCK idle credit stays out of it.
    for _ in range(SIM_HZ):
        aihelp.step(glib, state, CONST["INPUT_FORWARD"])
    assert state.engine.trace_milli == expected


def test_standing_still_at_underclock_is_the_one_passive_fall(glib):
    """DESIGN 5 states the arithmetic outright: base 0.18 x 0.5 = +0.09 %/s
    against a -0.20 %/s credit is a net -0.11 %/s."""
    state = empty_state(glib, base_rate=SHIPPED_BASE_RATE,
                        throttle=CONST["THROTTLE_UNDERCLOCK"])
    glib.trace_apply(aihelp.ref(state), 50 * MILLI)     # start high enough to fall
    start = state.engine.trace_milli
    for _ in range(SIM_HZ):
        aihelp.step(glib, state)
    assert state.engine.trace_milli - start == -110


def test_standing_still_at_nominal_still_climbs(glib):
    state = empty_state(glib, base_rate=SHIPPED_BASE_RATE)
    for _ in range(SIM_HZ):
        aihelp.step(glib, state)
    assert state.engine.trace_milli == SHIPPED_BASE_RATE


def test_the_meter_clamps_at_both_ends(glib):
    state = empty_state(glib)
    glib.trace_apply(aihelp.ref(state), 500 * MILLI)
    assert state.engine.trace_milli == CONST["TRACE_MAX_MILLI"]
    glib.trace_apply(aihelp.ref(state), -500 * MILLI)
    assert state.engine.trace_milli == 0


# ---------------------------------------------------------------------------
# DESIGN 9.1's reference run, level by level
# ---------------------------------------------------------------------------

# name, par (mm:ss), locked doors opened, Tracers killed before fleeing, net %
REFERENCE_RUN = [
    ("INGRESS",     "2:00", 1, 0, 49.0),
    ("THE LEDGER",  "2:30", 2, 1, 53.0),
    ("NURSERY",     "3:00", 2, 1, 62.0),
    ("BAD BLOCK",   "3:00", 2, 2, 54.0),
    ("THE CHOIR",   "3:15", 3, 1, 69.5),
    ("DEAD LETTER", "3:30", 3, 2, 66.0),
    ("COLD STORE",  "3:30", 3, 2, 66.0),
    ("THE KERNEL",  "4:00", 3, 2, 75.0),
]

# The reference run's other terms, from DESIGN 9.1's prose: under enemy LOS for
# 20% of par, three shots inside an unalerted enemy's noise radius, four hits.
REFERENCE_LOS_FRACTION = 0.20
REFERENCE_NOISE_SHOTS = 3
REFERENCE_HITS = 4


def _seconds(par):
    minutes, seconds = par.split(":")
    return int(minutes) * 60 + int(seconds)


@pytest.mark.parametrize("name,par,doors,tracer_kills,net", REFERENCE_RUN)
def test_the_reference_run_reproduces_the_design_table(name, par, doors, tracer_kills, net):
    """Every term of DESIGN 9.1's table, computed from game_rules.h's constants.

    This pins the CONSTANTS, not the sim: if someone retunes the locked-door
    charge or the Tracer-kill credit, the printed table stops being reachable
    and this test says so by name.
    """
    seconds = _seconds(par)
    total = (
        SHIPPED_BASE_RATE * seconds
        + CONST["TRACE_RATE_ENEMY_LOS"] * seconds * REFERENCE_LOS_FRACTION
        + CONST["TRACE_BUMP_LOCKED_DOOR"] * doors
        + CONST["TRACE_BUMP_NOISE_SHOT"] * REFERENCE_NOISE_SHOTS
        + CONST["TRACE_BUMP_PLAYER_HIT"] * REFERENCE_HITS
        - CONST["TRACE_DROP_TRACER_KILL"] * tracer_kills
    )
    assert round(total / MILLI, 1) == net, \
        "%s: the constants give %.1f%%, DESIGN 9.1 prints %.1f%%" % (name, total / MILLI, net)


def test_the_enemy_los_rate_matches_the_reference_runs_average(glib):
    """DESIGN 9.1 describes the LOS term as "under enemy LOS for 20% of par
    (average +0.12 %/s)", which is only true if the rate itself is 0.6 %/s."""
    assert CONST["TRACE_RATE_ENEMY_LOS"] * REFERENCE_LOS_FRACTION == 120


def test_an_enemy_watching_you_adds_the_los_rate(glib):
    """The +0.6 %/s is charged while any enemy has line of sight, and the sim
    must actually be the thing that decides that."""
    rows = ["##########",
            "#w......@#",
            "##########"]
    level = aihelp.level_from_rows(
        glib, rows, "# name: LOS\n# start_facing: 0\n# trace_base_rate: 180\n\n")
    state = aihelp.new_state(glib, level)

    aihelp.step(glib, state)
    assert state.game.enemy_has_los == 1
    start = state.engine.trace_milli
    for _ in range(SIM_HZ):
        aihelp.step(glib, state, CONST["INPUT_FORWARD"])
    gained = state.engine.trace_milli - start
    assert gained == SHIPPED_BASE_RATE + CONST["TRACE_RATE_ENEMY_LOS"]


def test_a_wall_between_you_and_an_enemy_costs_nothing(glib):
    rows = ["##########",
            "#w##....@#",
            "##########"]
    level = aihelp.level_from_rows(
        glib, rows, "# name: LOS\n# start_facing: 0\n# trace_base_rate: 180\n\n")
    state = aihelp.new_state(glib, level)

    for _ in range(SIM_HZ):
        aihelp.step(glib, state, CONST["INPUT_FORWARD"])
    assert state.game.enemy_has_los == 0
    assert state.engine.trace_milli == SHIPPED_BASE_RATE


# ---------------------------------------------------------------------------
# the thresholds
# ---------------------------------------------------------------------------

BANDS = [
    (0, CONST["TRACE_BAND_CLEAN"], CONST["TRACE_TEMPO_CLEAN"],
     CONST["PALETTE_VARIANT_CLEAN"]),
    (25, CONST["TRACE_BAND_DEGRADED"], CONST["TRACE_TEMPO_DEGRADED"],
     CONST["PALETTE_VARIANT_DEGRADED"]),
    (50, CONST["TRACE_BAND_TIER"], CONST["TRACE_TEMPO_TIER"],
     CONST["PALETTE_VARIANT_DEGRADED"]),
    (75, CONST["TRACE_BAND_CORRUPT"], CONST["TRACE_TEMPO_CORRUPT"],
     CONST["PALETTE_VARIANT_CORRUPT"]),
]


@pytest.mark.parametrize("percent,band,tempo,palette", BANDS)
def test_each_threshold_publishes_its_band_tempo_and_palette(glib, percent, band, tempo,
                                                             palette):
    """DESIGN 9's threshold table is STATE the platform layer reads: the sim
    names the band, the tempo and the palette variant and renders none of it."""
    state = empty_state(glib)
    glib.trace_apply(aihelp.ref(state), percent * MILLI)

    assert state.game.trace_band == band
    assert state.game.music_tempo_bpm == tempo
    assert state.game.palette_variant == palette


def test_the_boundary_belongs_to_the_higher_band(glib):
    state = empty_state(glib)
    glib.trace_apply(aihelp.ref(state), 25 * MILLI - 1)
    assert state.game.trace_band == CONST["TRACE_BAND_CLEAN"]
    glib.trace_apply(aihelp.ref(state), 1)
    assert state.game.trace_band == CONST["TRACE_BAND_DEGRADED"]


def test_crossing_a_threshold_announces_it_once_and_only_upward(glib):
    state = empty_state(glib)
    aihelp.clear_events(state)

    glib.trace_apply(aihelp.ref(state), 25 * MILLI)
    events = aihelp.drain_events(state)
    assert CONST["EV_MSG_TRACE_DEGRADED"] in events
    assert CONST["EV_SFX_TRACE_ALARM"] in events

    # A scrubber taking you back under must not ring anything.
    aihelp.clear_events(state)
    glib.trace_apply(aihelp.ref(state), -CONST["TRACE_DROP_SCRUBBER"])
    assert aihelp.drain_events(state) == []
    assert state.game.trace_band == CONST["TRACE_BAND_CLEAN"]


def test_a_corrupt_level_is_never_cleaned_up_by_a_low_meter(glib):
    """The meter escalates the palette; it never walks it back below what the
    level was authored with."""
    header = "# name: CORRUPT\n# palette_variant: 2\n# start_facing: 0\n\n"
    level = aihelp.level_from_rows(glib, EMPTY_ROOM, header)
    state = aihelp.new_state(glib, level)
    assert state.game.palette_variant == CONST["PALETTE_VARIANT_CORRUPT"]


def test_hardened_runs_the_death_path(glib):
    """DESIGN 18 defers the Hunter, so DESIGN 9's 100% exfil becomes the
    HARDENED palette plus the death path."""
    state = empty_state(glib)
    glib.trace_apply(aihelp.ref(state), CONST["TRACE_MAX_MILLI"])
    assert state.game.trace_band == CONST["TRACE_BAND_HARDENED"]
    assert state.game.music_tempo_bpm == CONST["TRACE_TEMPO_HARDENED"]

    aihelp.step(glib, state)
    assert state.game.phase == CONST["PHASE_DEAD"]
    assert state.game.integrity == 0


# ---------------------------------------------------------------------------
# the start rule and the run's carry
# ---------------------------------------------------------------------------

def test_the_start_rule_adds_the_carry_terms_and_the_cap_wins(glib):
    """DESIGN 9: start = min(carry_cap, trace_start + 5*over_par + 10*deaths),
    and trace_carry_cap ships at 25 so no amount of dying starts you above it."""
    header = "# name: START\n# start_facing: 0\n# trace_start: 5\n# trace_carry_cap: 25\n\n"
    level = aihelp.level_from_rows(glib, EMPTY_ROOM, header)
    state = aihelp.new_state(glib, level)
    progress = aihelp.RunProgress()
    glib.run_progress_reset(ctypes.byref(progress))

    progress.deaths_this_sector = 1
    progress.sectors_over_par = 1
    glib.game_start_level(aihelp.ref(state), ctypes.byref(level),
                          level.rng_seed, ctypes.byref(progress))
    expected = 5 + CONST["TRACE_START_PER_DEATH"] + CONST["TRACE_START_PER_OVER_PAR"]
    assert state.engine.trace_milli == expected * MILLI

    progress.deaths_this_sector = 9
    glib.game_start_level(aihelp.ref(state), ctypes.byref(level),
                          level.rng_seed, ctypes.byref(progress))
    assert state.engine.trace_milli == level.trace_carry_cap * MILLI


def test_integrity_carries_between_sectors_with_the_design_bonus(glib):
    """DESIGN 4: integrity carries, +25 capped at 100 at each sector start."""
    level = aihelp.level_from_rows(glib, EMPTY_ROOM, "# name: CARRY\n# start_facing: 0\n\n")
    state = aihelp.new_state(glib, level)
    progress = aihelp.RunProgress()
    glib.run_progress_reset(ctypes.byref(progress))

    progress.integrity = 40
    progress.cycles = 17
    glib.game_start_level(aihelp.ref(state), ctypes.byref(level),
                          level.rng_seed, ctypes.byref(progress))
    assert state.game.integrity == 40 + CONST["PLAYER_INTEGRITY_SECTOR_BONUS"]
    assert state.game.cycles == 17

    progress.integrity = 90
    glib.game_start_level(aihelp.ref(state), ctypes.byref(level),
                          level.rng_seed, ctypes.byref(progress))
    assert state.game.integrity == CONST["PLAYER_INTEGRITY_MAX"]


def test_a_fresh_run_starts_at_the_design_four_values(glib):
    level = aihelp.level_from_rows(glib, EMPTY_ROOM, "# name: FRESH\n# start_facing: 0\n\n")
    state = aihelp.new_state(glib, level)
    assert state.game.integrity == CONST["PLAYER_INTEGRITY_START"]
    assert state.game.cycles == CONST["PLAYER_CYCLES_START"]
    assert state.game.tokens == 0
    assert state.game.phase == CONST["PHASE_PLAYING"]


# ---------------------------------------------------------------------------
# the shipped levels carry the shipped numbers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,par_ticks", [("level1", 3000), ("level2", 3750)])
def test_the_shipped_levels_carry_the_design_header(glib, name, par_ticks):
    import blackice

    path = blackice.ROOT / "levels" / ("%s.txt" % name)
    level = blackice.parse_level(glib, path.read_text())
    assert level.trace_base_rate == SHIPPED_BASE_RATE
    assert level.trace_carry_cap == 25
    assert level.par_ticks == par_ticks
    assert level.start_facing_brads == 0, "DESIGN 12 and 13 both start facing north"


# ---------------------------------------------------------------------------
# DESIGN 9's falls, driven through a kill in the sim
# ---------------------------------------------------------------------------

KILL_ROOM = [
    "##########",
    "#........#",
    "#..t..@..#",
    "#........#",
    "####s#####",
    "##########",
]


def kill_state(glib):
    """A room holding one Tracer and one Sentry, with the meter parked high
    enough that a fall of 8% has somewhere to fall to."""
    level = aihelp.level_from_rows(glib, KILL_ROOM,
                                   "# name: KILLS\n# start_facing: 0\n\n")
    state = aihelp.new_state(glib, level)
    glib.trace_apply(aihelp.ref(state), 50 * MILLI)
    return level, state


def test_destroying_a_sentry_pays_the_design_nine_credit(glib):
    """DESIGN 9's fall table: "Sentry destroyed -5%".  Asserted on the meter the
    sim actually keeps, not on the arithmetic restated in Python."""
    level, state = kill_state(glib)
    sentry = aihelp.entity_index_at(level, 4, 4)
    # The iris has to be open for a shot to land at all (DESIGN 8).
    body = state.game.entities[sentry]
    body.state = CONST["ENT_STATE_ATTACK"]
    body.state_timer = CONST["SENTRY_IRIS_OPEN_TICKS"]

    before = state.engine.trace_milli
    glib.entity_damage(aihelp.ref(state), sentry, CONST["SENTRY_HP"])
    assert body.state == CONST["ENT_STATE_DESTROYED"]
    assert before - state.engine.trace_milli == CONST["TRACE_DROP_SENTRY_KILL"]


def test_killing_a_tracer_before_it_flees_pays_the_design_nine_credit(glib):
    """"Tracer killed before it flees -8%"."""
    level, state = kill_state(glib)
    tracer = aihelp.entity_index_at(level, 3, 2)
    state.game.entities[tracer].state = CONST["ENT_STATE_CHASE"]

    before = state.engine.trace_milli
    glib.entity_damage(aihelp.ref(state), tracer, CONST["TRACER_HP"])
    assert state.game.entities[tracer].state == CONST["ENT_STATE_DEAD"]
    assert before - state.engine.trace_milli == CONST["TRACE_DROP_TRACER_KILL"]


def test_killing_a_tracer_that_is_already_fleeing_pays_nothing(glib):
    """The credit is for stopping a Tracer reporting you.  One that is already
    running has stopped being a threat to the meter, so shooting it in the back
    is worth no percentage - and paying it anyway would let a player farm the
    meter down by wounding Tracers first."""
    level, state = kill_state(glib)
    tracer = aihelp.entity_index_at(level, 3, 2)
    state.game.entities[tracer].state = CONST["ENT_STATE_FLEE"]

    before = state.engine.trace_milli
    glib.entity_damage(aihelp.ref(state), tracer, CONST["TRACER_HP"])
    assert state.game.entities[tracer].state == CONST["ENT_STATE_DEAD"]
    assert state.engine.trace_milli == before


def test_a_wound_that_does_not_kill_pays_nothing(glib):
    """The credit is on the killing blow only, so a body chipped down over
    several shots cannot pay it twice."""
    level, state = kill_state(glib)
    tracer = aihelp.entity_index_at(level, 3, 2)
    state.game.entities[tracer].state = CONST["ENT_STATE_CHASE"]

    before = state.engine.trace_milli
    glib.entity_damage(aihelp.ref(state), tracer, CONST["TRACER_HP"] - 1)
    assert state.game.entities[tracer].hp == 1
    assert state.engine.trace_milli == before


def test_the_enemy_tier_is_the_design_nine_escalation_ladder(glib):
    """DESIGN 9's threshold table raises the roster twice: "tier +1" at 50% and
    the Sentry bursts / edge spawns at 75%.  The behaviour is DESIGN 18 item 5's
    deferred work but the NUMBER is published to the platform layer today."""
    state = empty_state(glib)
    for percent, tier in ((0, CONST["ENEMY_TIER_BASE"]),
                          (25, CONST["ENEMY_TIER_BASE"]),
                          (50, CONST["ENEMY_TIER_ELEVATED"]),
                          (75, CONST["ENEMY_TIER_HOSTILE"]),
                          (100, CONST["ENEMY_TIER_HOSTILE"])):
        state.engine.trace_milli = 0
        glib.trace_apply(aihelp.ref(state), percent * MILLI)
        assert state.game.enemy_tier == tier, "%d%%" % percent
