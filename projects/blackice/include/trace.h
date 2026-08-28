/*
 * trace.h - the trace meter, the four thresholds, and the run's carry state.
 *
 * DESIGN 9 states every rate in percent per SECOND, and the level header's
 * `trace_base_rate` uses the same unit.  The sim runs at SIM_HZ, and 180/25 is
 * not an integer, so the meter integrates through a remainder: each tick adds
 * the whole per-second rate to a small accumulator and moves whole
 * milli-percent out of it.  Over a second that is exact, with no drift and no
 * fixed-point rounding to argue about - which is what lets DESIGN 9.1's
 * reference table be pinned as a test rather than approximated.
 *
 * The thresholds are STATE, not behaviour: this file computes the band, the
 * palette variant, the music tempo and the enemy tier and puts them in
 * GameState.  What a palette variant looks like and what 168 BPM sounds like
 * belong to the platform layer, which reads them.
 */
#ifndef BLACKICE_TRACE_H
#define BLACKICE_TRACE_H

#include <stdint.h>
#include "game_rules.h"

struct GameState;   /* game.h owns the definition; declared to break the cycle */

/*
 * What the run carries between sectors.  DESIGN 9 makes `trace_carry_cap` the
 * single authority on the start value, so this is deliberately the whole of
 * the carry: two counters and nothing else.  The platform layer owns one of
 * these across a run and hands it to game_start_level.
 */
typedef struct {
    uint8_t sectors_over_par;       /* sectors finished slower than par */
    uint8_t deaths_this_sector;
    int16_t integrity;              /* DESIGN 4: integrity carries between sectors */
    int16_t cycles;                 /* and so do cycles; tokens do not */
} RunProgress;

void run_progress_reset(RunProgress *progress);

/*
 * Start a sector: game_init, then DESIGN 9's start rule and DESIGN 4's
 * integrity bonus.  `progress` may be null, which means a fresh run.
 */
void game_start_level(struct GameState *state, const Level *level, uint32_t seed,
                      const RunProgress *progress);

void trace_init(struct GameState *state, const RunProgress *progress);

/* One tick of the meter: the base rate, the LOS rate, the idle credit, then
 * the thresholds.  `input` is the word this tick acted on, which is what
 * decides whether the player was standing still. */
void trace_step(struct GameState *state, uint16_t input);

/* Apply a one-shot change in milli-percent, positive or negative, and refresh
 * the threshold state.  Every DESIGN 9 bump and drop goes through here. */
void trace_apply(struct GameState *state, int32_t milli);

/* Whole percent, for the HUD and for a test that wants DESIGN 9's own unit. */
static inline uint8_t trace_percent(int32_t trace_milli)
{
    return (uint8_t)(trace_milli / TRACE_MILLI_PER_PERCENT);
}

#endif /* BLACKICE_TRACE_H */
