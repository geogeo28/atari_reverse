/*
 * game_rules.h - the game layer's tunables, mirroring DESIGN.md's tables.
 *
 * game_consts.h owns what the ENGINE needs (projection, window, throttle
 * modes, door timings).  This file owns what the GAME needs: enemy statistics,
 * weapon statistics, the trace meter's arithmetic and the pickup values.  Every
 * value below is either printed in DESIGN.md or derived from a printed value by
 * an arithmetic that is written out beside it, and nothing outside this file
 * spells one as a literal.
 *
 * Units, once, so no constant below has to restate them:
 *   distance   map units, 8.8 fixed, CELL_UNITS (256) to a grid cell
 *   time       sim ticks at SIM_HZ (25 Hz), so 25 ticks = one second
 *   angle      angle_t, 65536 to a full turn
 *   trace      thousandths of a percent ("milli-percent"), per SECOND
 */
#ifndef BLACKICE_GAME_RULES_H
#define BLACKICE_GAME_RULES_H

#include "fixed.h"
#include "game_consts.h"

/* ---- distances in whole cells, spelled once ----------------------------- */

#define CELLS(n)                ((n) * CELL_UNITS)
/* Tenths of a cell, for the sub-cell reaches DESIGN states as decimals. */
#define CELL_TENTHS(n)          (((n) * CELL_UNITS) / 10)

/* ---- the player (DESIGN 4) ---------------------------------------------- */

#define PLAYER_INTEGRITY_MAX    100
#define PLAYER_INTEGRITY_START  PLAYER_INTEGRITY_MAX
/* DESIGN 4: +25, capped at the maximum, at each sector start. */
#define PLAYER_INTEGRITY_SECTOR_BONUS 25
#define PLAYER_CYCLES_MAX       200
#define PLAYER_CYCLES_START     60

/* Token inventory, one bit each, so "which tokens" is a byte compare. */
#define TOKEN_ALPHA_BIT         0x01
#define TOKEN_BETA_BIT          0x02
#define TOKEN_GAMMA_BIT         0x04

/* ---- run phases --------------------------------------------------------- */

#define PHASE_PLAYING           0
#define PHASE_DEAD              1
#define PHASE_LEVEL_CLEAR       2

/* DESIGN 14 ships eight sectors; sector_index + 1 past the last means done. */
#define LEVEL_SEQUENCE_COUNT    8

/*
 * DESIGN 18 item 6: the first playable's throttle is a two-state UNDERCLOCK
 * <-> NOMINAL toggle.  OVERCLOCK arrives with 160-column mode, so the mode
 * table still carries three entries and only the toggle is short.
 */
#define THROTTLE_TOGGLE_MODES   2

/* ---- the Buster (DESIGN 7) ---------------------------------------------- */

#define BUSTER_DAMAGE_NEAR      8
#define BUSTER_DAMAGE_FAR       4       /* beyond BUSTER_FALLOFF_UNITS */
#define BUSTER_FALLOFF_UNITS    CELLS(8)
#define BUSTER_RANGE_UNITS      CELLS(12)
#define BUSTER_RATE_TICKS       5       /* 0.20 s */
#define BUSTER_COST_CYCLES      1
/* The brownout floor: at zero cycles it still fires, weaker and slower. */
#define BUSTER_BROWNOUT_DAMAGE  3
#define BUSTER_BROWNOUT_RATE_TICKS 10
/* DESIGN 7's flash is two rendered frames; one sim tick is 2 VBLs, so one
 * tick of flag is the cheapest thing that covers them. */
#define MUZZLE_FLASH_TICKS      1

/* ---- enemies (DESIGN 8) ------------------------------------------------- */

#define WATCHDOG_HP             20
#define ANCHOR_HP               60      /* DESIGN 8: four anchors, 60 HP each */
#define SENTRY_HP               35
#define TRACER_HP               25

/* Speeds in map units per tick: cells/tick * CELL_UNITS, rounded. */
#define WATCHDOG_SPEED          46      /* 0.18 c/tick */
#define TRACER_SPEED            61      /* 0.24 c/tick */

#define WATCHDOG_MELEE_DAMAGE   12
#define WATCHDOG_MELEE_REACH    CELL_TENTHS(6)  /* contact <= 0.6 cells */
#define SENTRY_HITSCAN_DAMAGE   8
#define TRACER_SHOT_DAMAGE      10

#define WATCHDOG_ATTACK_TICKS   25      /* cooldown between bites */
/*
 * The bite's wind-up.  DESIGN 8 prints the cooldown but not a tell, and a
 * melee that lands the instant it touches you is unreadable at 25 Hz; 5 ticks
 * (0.20 s) is the window to back out of reach, matching the Buster's own rate.
 */
#define WATCHDOG_BITE_WINDUP_TICKS 5
#define SENTRY_FIRE_TICKS       12      /* while the iris is open */
#define TRACER_FIRE_TICKS       30

/* DESIGN 5's enemy-sight multipliers per throttle mode, 8.8: 0.5 / 1.0 / 1.5.
 * They live here and not in the ThrottleMode table because only the AI reads
 * them; the renderer's copy of the throttle knows nothing about being seen. */
#define THROTTLE_SIGHT_UNDERCLOCK 128
#define THROTTLE_SIGHT_NOMINAL    256
#define THROTTLE_SIGHT_OVERCLOCK  384

#define WATCHDOG_SIGHT_UNITS    CELLS(8)
#define SENTRY_SIGHT_UNITS      CELLS(14)
#define TRACER_SIGHT_UNITS      CELLS(12)

/*
 * Half-cone tangents in 8.8 fixed, because the cone test is a cross/dot
 * comparison and never an arctangent: |cross| <= dot * tan(half cone).
 *   Watchdog 120 deg -> tan 60 = 1.7320508 -> 443
 *   Sentry    90 deg -> tan 45 = 1.0       -> 256
 *   Tracer   150 deg -> tan 75 = 3.7320508 -> 955
 */
#define WATCHDOG_CONE_TAN_Q8    443
#define SENTRY_CONE_TAN_Q8      256
#define TRACER_CONE_TAN_Q8      955

#define WATCHDOG_NOISE_UNITS    CELLS(5)
#define SENTRY_NOISE_UNITS      CELLS(8)
#define TRACER_NOISE_UNITS      CELLS(10)

/* An ALERT Watchdog wakes its pack inside this radius (DESIGN 8 state table). */
#define WATCHDOG_PACK_WAKE_UNITS CELLS(6)
/* DESIGN 9's 25% threshold: Watchdog alert radius +2 cells. */
#define WATCHDOG_ALERT_BONUS_UNITS CELLS(2)

/* Tells and charges, in ticks (DESIGN 8's state table). */
#define WATCHDOG_ALERT_TICKS    8
#define TRACER_ALERT_TICKS      8
#define SENTRY_CHARGE_TICKS     20
#define SENTRY_IRIS_OPEN_TICKS  30      /* vulnerable, firing every SENTRY_FIRE_TICKS */
#define SENTRY_IRIS_SHUT_TICKS  40      /* invulnerable, then it charges again */

/* DESIGN 8: 2-frame dissolve, 12 ticks, then the body is removed. */
#define ENEMY_DISSOLVE_TICKS    12

/* The Tracer's ring, in field steps: it holds cells whose BFS value is 3..5. */
#define TRACER_RING_MIN_STEPS   3
#define TRACER_RING_MAX_STEPS   5
/* FLEE at HP < 40% of TRACER_HP, i.e. below 10. */
#define TRACER_FLEE_HP          ((TRACER_HP * 40) / 100)
/*
 * DESIGN 8's state table gives an IDLE Tracer "patrols its spawn room".  The
 * level format marks no room boundaries, so the patrol is a bounded random walk
 * instead: the body never claims a cell whose centre is further than this from
 * the cell it spawned in, which keeps it inside the chamber it was authored
 * into without the compiler having to name one.  Two cells is the widest walk
 * that cannot cross a one-cell doorway into the next room.
 */
#define TRACER_PATROL_RADIUS_UNITS CELLS(2)

/* ---- navigation (DESIGN 8.1) -------------------------------------------- */

#define NAV_RADIUS_STEPS        20      /* the flood is radius limited to 20 cells */
#define NAV_UNREACHABLE         255     /* out of range, or no route at all */
#define NAV_REBUILD_TICKS       8       /* recomputed every 8 sim ticks (3.125 Hz) */
/*
 * A 4-neighbour flood limited to NAV_RADIUS_STEPS visits at most the diamond
 * 2r^2 + 2r + 1 = 841 cells, so a 1024-entry queue can never overflow and the
 * BFS needs no wrap test.
 */
#define NAV_QUEUE_MAX           1024

/* Hard stop on a line walk, so no LOS or hitscan probe can run away. */
#define GRID_WALK_MAX_STEPS     64

/*
 * Neighbour counts for the mover's "best of 8" and the flood's 4-neighbourhood.
 * The orthogonals come first in every neighbour table, so a loop bounded by the
 * first is the flood and a loop bounded by the second is the mover.
 */
#define NEIGHBOUR_ORTHO_COUNT   4
#define NEIGHBOUR_COUNT         8

/* ---- the trace meter (DESIGN 9) ----------------------------------------- */

/*
 * Every rate below is milli-percent per SECOND, matching the level header's
 * trace_base_rate unit.  trace.c divides by SIM_HZ through a remainder
 * accumulator, so a rate that is not a multiple of 25 still integrates exactly.
 */
#define TRACE_RATE_ENEMY_LOS    600     /* +0.6 %/s while any enemy has LOS */
#define TRACE_RATE_IDLE_CREDIT  200     /* -0.20 %/s standing still at UNDERCLOCK */

/* One-shot changes, in milli-percent. */
#define TRACE_BUMP_NOISE_SHOT   2000    /* firing inside an unalerted enemy's noise radius */
#define TRACE_BUMP_LOCKED_DOOR  3000    /* once per locked door per sector */
#define TRACE_BUMP_PLAYER_HIT   1000
#define TRACE_BUMP_TRACER_ESCAPE 15000  /* a Tracer reaching a sector edge */
#define TRACE_DROP_SCRUBBER     20000
#define TRACE_DROP_TRACER_KILL  8000    /* killed before it fled */
#define TRACE_DROP_SENTRY_KILL  5000

/* Thresholds, in whole percent (DESIGN 9's table). */
#define TRACE_THRESHOLD_DEGRADED 25
#define TRACE_THRESHOLD_TIER     50
#define TRACE_THRESHOLD_CORRUPT  75
#define TRACE_THRESHOLD_HARDENED 100
#define TRACE_BAND_COUNT         5
/* The bands the thresholds cut the meter into, lowest first. */
#define TRACE_BAND_CLEAN         0
#define TRACE_BAND_DEGRADED      1
#define TRACE_BAND_TIER          2
#define TRACE_BAND_CORRUPT       3
#define TRACE_BAND_HARDENED      4

/* Music tempo per band, in BPM (DESIGN 9 and DESIGN 16). */
#define TRACE_TEMPO_CLEAN       140
#define TRACE_TEMPO_DEGRADED    152
#define TRACE_TEMPO_TIER        168
#define TRACE_TEMPO_CORRUPT     184
#define TRACE_TEMPO_HARDENED    200

/*
 * DESIGN 9's enemy escalation, named.  The behaviour each tier names (Watchdogs
 * respawning, Tracers faster, Sentry bursts) is DESIGN 18 item 5's deferred
 * work; the NUMBER is published to the platform layer today, and naming it here
 * is what stops trace.c spelling a bare 1 and 2.
 */
#define ENEMY_TIER_BASE          0      /* below 50%: the roster as authored */
#define ENEMY_TIER_ELEVATED      1      /* 50%: Watchdogs respawn, Tracers +25% speed */
#define ENEMY_TIER_HOSTILE       2      /* 75%: Sentry bursts, Tracers spawn at the edge */

/* Palette variants the thresholds substitute in (DESIGN 11's palette_variant). */
#define PALETTE_VARIANT_CLEAN    0
#define PALETTE_VARIANT_DEGRADED 1
#define PALETTE_VARIANT_CORRUPT  2
#define PALETTE_VARIANT_KERNEL   3

/* DESIGN 9's start rule: start = min(carry_cap, trace_start + 5*over_par + 10*deaths). */
#define TRACE_START_PER_OVER_PAR 5
#define TRACE_START_PER_DEATH    10

/* ---- pickups (DESIGN 10) ------------------------------------------------ */

#define PICKUP_CYCLES_SMALL     10
#define PICKUP_CYCLES_LARGE     25
#define PICKUP_INTEGRITY_SMALL  15
#define PICKUP_INTEGRITY_LARGE  40
/*
 * A pickup is collected anywhere inside its cell: the sprite occupies the
 * lower half of the cell (DESIGN 17.1) and there is no reason to make the
 * player hunt for its centre.
 */
#define PICKUP_REACH_UNITS      (CELL_UNITS / 2)

#endif /* BLACKICE_GAME_RULES_H */
