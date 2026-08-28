"""DESIGN's printed gameplay numbers, against the constants and the table.

Everything else in the suite derives its expectations from `CONST`, which is
parsed out of include/*.h.  That is the right way round for behaviour - a test
that restates a tunable goes stale the day the tunable moves - but it leaves one
hole nothing else can cover: change the header and the test changes with it.  A
Watchdog whose noise radius doubles is invisible to a test that computes "five
cells" from the same #define.

So this module is the other direction, and it is the ONLY module allowed to be:
the literals below are transcribed from DESIGN.md's own tables, and each one is
quoted where it came from.  Two things are pinned here and nowhere else:

  * the constants, against the numbers the design document prints;
  * `g_enemy_stats`, the table the sim actually reads, against those constants -
    because a cone widened in the table is a cone the AI uses and the header
    never mentions.
"""
import ctypes

import pytest

import aihelp
import blackice
from aihelp import glib          # noqa: F401 - the session fixture the tests take
from blackice import CONST

CELL = blackice.CELL_UNITS
SIM_HZ = CONST["SIM_HZ"]


class EnemyStats(ctypes.Structure):
    """include/entities.h's EnemyStats: the row ai.c reads for sight and hp."""

    _fields_ = [("hp", ctypes.c_uint8), ("speed", ctypes.c_uint8),
                ("sight_units", ctypes.c_uint16), ("noise_units", ctypes.c_uint16),
                ("cone_tan_q8", ctypes.c_int16)]


def stats_table(glib):
    aihelp.bind(glib)
    return (EnemyStats * CONST["ENT_TYPE_COUNT"]).in_dll(glib, "g_enemy_stats")


# ---------------------------------------------------------------------------
# DESIGN 8's enemy table, transcribed
# ---------------------------------------------------------------------------

# | | Watchdog | Sentry | Tracer |
# | HP | 20 | 35 | 25 |
# | Speed | 0.18 c/tick | static | 0.24 c/tick |
# | Damage | 12 melee, contact <= 0.6 cells | 8 hitscan | 10 ranged |
# | Attack rate | 25 ticks | 12 ticks while iris open | 30 ticks |
# | Base sight | 8 cells, 120 deg | 14 cells, 90 deg | 12 cells, 150 deg |
# | Noise radius | 5 cells | 8 cells | 10 cells |
DESIGN_8 = {
    "WATCHDOG": {"HP": 20, "SIGHT_CELLS": 8, "NOISE_CELLS": 5, "CONE_DEGREES": 120},
    "SENTRY":   {"HP": 35, "SIGHT_CELLS": 14, "NOISE_CELLS": 8, "CONE_DEGREES": 90},
    "TRACER":   {"HP": 25, "SIGHT_CELLS": 12, "NOISE_CELLS": 10, "CONE_DEGREES": 150},
}

#: tan(half cone) in 8.8 fixed, rounded, for each printed cone width.  Written
#: out rather than computed with math.tan so the number in the header and the
#: number here were arrived at independently.
CONE_TAN_Q8_FOR_DEGREES = {120: 443, 90: 256, 150: 955}


@pytest.mark.parametrize("enemy", sorted(DESIGN_8))
def test_the_enemy_constants_are_design_eights_printed_numbers(glib, enemy):
    printed = DESIGN_8[enemy]
    assert CONST["%s_HP" % enemy] == printed["HP"]
    assert CONST["%s_SIGHT_UNITS" % enemy] == printed["SIGHT_CELLS"] * CELL
    assert CONST["%s_NOISE_UNITS" % enemy] == printed["NOISE_CELLS"] * CELL
    assert CONST["%s_CONE_TAN_Q8" % enemy] \
        == CONE_TAN_Q8_FOR_DEGREES[printed["CONE_DEGREES"]]


@pytest.mark.parametrize("enemy", sorted(DESIGN_8))
def test_the_stats_table_the_ai_reads_matches_those_constants(glib, enemy):
    """entities.c's g_enemy_stats is what every sight test in the tick actually
    consults.  A row that disagrees with the rules header is an enemy that plays
    by numbers no document contains - and for a Sentry it is invisible to
    gameplay tests, because DESIGN 11's alcove is itself a 90 degree aperture and
    hides any cone wider than the one it was given."""
    row = stats_table(glib)[CONST["ENT_%s" % enemy]]
    assert row.hp == CONST["%s_HP" % enemy]
    assert row.sight_units == CONST["%s_SIGHT_UNITS" % enemy]
    assert row.noise_units == CONST["%s_NOISE_UNITS" % enemy]
    assert row.cone_tan_q8 == CONST["%s_CONE_TAN_Q8" % enemy]


def test_the_movers_speeds_are_the_printed_cells_per_tick(glib):
    """0.18 and 0.24 cells/tick, rounded to whole map units.  A static Sentry
    has speed 0, which is what makes "never moves" a table entry and not a
    branch."""
    table = stats_table(glib)
    assert table[CONST["ENT_WATCHDOG"]].speed == round(0.18 * CELL)
    assert table[CONST["ENT_TRACER"]].speed == round(0.24 * CELL)
    assert table[CONST["ENT_SENTRY"]].speed == 0
    assert CONST["ANCHOR_HP"] == 60, "DESIGN 8: four anchors, 60 HP each"


def test_the_damage_and_attack_rates_are_design_eights(glib):
    assert CONST["WATCHDOG_MELEE_DAMAGE"] == 12
    # game_rules.h spells sub-cell reaches as CELL_TENTHS(n), which truncates:
    # 0.6 cells is 153 units and not 154, and the reach is an upper bound the
    # design writes as "<= 0.6 cells", so truncating is the safe direction.
    assert CONST["WATCHDOG_MELEE_REACH"] == 6 * CELL // 10, "contact <= 0.6 cells"
    assert CONST["WATCHDOG_ATTACK_TICKS"] == 25
    assert CONST["SENTRY_HITSCAN_DAMAGE"] == 8
    assert CONST["SENTRY_FIRE_TICKS"] == 12
    assert CONST["TRACER_SHOT_DAMAGE"] == 10
    assert CONST["TRACER_FIRE_TICKS"] == 30
    assert CONST["WATCHDOG_PACK_WAKE_UNITS"] == 6 * CELL, "wakes its pack within 6 cells"


def test_the_state_table_timings_are_design_eights(glib):
    """DESIGN 8's state table: an 8-tick tell, a 20-tick charge, 30 ticks of
    open iris and 40 shut, and a 12-tick two-frame dissolve."""
    assert CONST["WATCHDOG_ALERT_TICKS"] == 8
    assert CONST["TRACER_ALERT_TICKS"] == 8
    assert CONST["SENTRY_CHARGE_TICKS"] == 20
    assert CONST["SENTRY_IRIS_OPEN_TICKS"] == 30
    assert CONST["SENTRY_IRIS_SHUT_TICKS"] == 40
    assert CONST["ENEMY_DISSOLVE_TICKS"] == 12
    assert CONST["TRACER_RING_MIN_STEPS"] == 3, "field range 3-5 with LOS"
    assert CONST["TRACER_RING_MAX_STEPS"] == 5
    assert CONST["TRACER_FLEE_HP"] == 10, "FLEE at HP < 40% of 25"


# ---------------------------------------------------------------------------
# DESIGN 7's weapon, DESIGN 8.1's navigation, DESIGN 9's meter
# ---------------------------------------------------------------------------

def test_the_buster_is_design_sevens_weapon(glib):
    assert CONST["BUSTER_DAMAGE_NEAR"] == 8
    assert CONST["BUSTER_DAMAGE_FAR"] == 4
    assert CONST["BUSTER_FALLOFF_UNITS"] == 8 * CELL
    assert CONST["BUSTER_RANGE_UNITS"] == 12 * CELL
    assert CONST["BUSTER_RATE_TICKS"] == SIM_HZ // 5, "0.20 s"
    assert CONST["BUSTER_COST_CYCLES"] == 1


def test_the_navigation_field_is_design_eight_ones(glib):
    """"One byte per cell, radius limited to 20 cells, 255 = out of range",
    "recomputed every 8 sim ticks (3.125 Hz)"."""
    assert CONST["NAV_RADIUS_STEPS"] == 20
    assert CONST["NAV_UNREACHABLE"] == 255
    assert CONST["NAV_REBUILD_TICKS"] == 8
    # A 4-neighbour flood limited to r visits at most the diamond 2r^2+2r+1.
    radius = CONST["NAV_RADIUS_STEPS"]
    assert CONST["NAV_QUEUE_MAX"] >= 2 * radius * radius + 2 * radius + 1


def test_the_trace_meters_rates_and_thresholds_are_design_nines(glib):
    """DESIGN 9's rise and fall tables, in milli-percent per SECOND."""
    assert CONST["TRACE_RATE_ENEMY_LOS"] == 600, "+0.6 %/s while any enemy has LOS"
    assert CONST["TRACE_RATE_IDLE_CREDIT"] == 200, "-0.20 %/s still at UNDERCLOCK"
    assert CONST["TRACE_BUMP_NOISE_SHOT"] == 2000
    assert CONST["TRACE_BUMP_LOCKED_DOOR"] == 3000
    assert CONST["TRACE_BUMP_PLAYER_HIT"] == 1000
    assert CONST["TRACE_BUMP_TRACER_ESCAPE"] == 15000
    assert CONST["TRACE_DROP_SCRUBBER"] == 20000
    assert CONST["TRACE_DROP_TRACER_KILL"] == 8000
    assert CONST["TRACE_DROP_SENTRY_KILL"] == 5000
    for name, percent in (("DEGRADED", 25), ("TIER", 50),
                          ("CORRUPT", 75), ("HARDENED", 100)):
        assert CONST["TRACE_THRESHOLD_%s" % name] == percent
    for name, bpm in (("CLEAN", 140), ("DEGRADED", 152), ("TIER", 168),
                      ("CORRUPT", 184), ("HARDENED", 200)):
        assert CONST["TRACE_TEMPO_%s" % name] == bpm


def test_the_pickups_are_design_tens(glib):
    assert CONST["PICKUP_CYCLES_SMALL"] == 10
    assert CONST["PICKUP_CYCLES_LARGE"] == 25
    assert CONST["PICKUP_INTEGRITY_SMALL"] == 15
    assert CONST["PICKUP_INTEGRITY_LARGE"] == 40
    assert CONST["PICKUP_REACH_UNITS"] == CELL // 2, "collected anywhere in its cell"


def test_the_rng_is_numerical_recipes_lcg(glib):
    """DESIGN 4.3 names the generator's constants, and the whole determinism
    contract is those two numbers.  test_replay checks the RECURRENCE against
    them, which cannot notice them changing; this is where they are the claim."""
    assert CONST["RNG_MULTIPLIER"] == 1664525
    assert CONST["RNG_INCREMENT"] == 1013904223
