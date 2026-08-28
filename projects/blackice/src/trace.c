/*
 * trace.c - the trace meter and DESIGN 9's four thresholds.
 *
 * ---------------------------------------------------------------------------
 * Why the meter carries a remainder
 * ---------------------------------------------------------------------------
 * DESIGN 9 states every rate per SECOND and the sim runs at SIM_HZ, so the
 * per-tick rise is rate/25 - and 180/25 = 7.2 is not an integer.  Truncating it
 * would lose 0.5 %/minute and DESIGN 9.1's reference table would stop being
 * reachable; scaling the meter up by 25 would change the unit the HUD and the
 * level header both speak.  So the meter stays in milli-percent and carries the
 * remainder: each tick adds the whole per-second rate into `trace_remainder`
 * and moves out whatever whole milli-percent have accumulated.  Over any whole
 * second that is exact, and the level-1 reference run lands on 21.6% to the
 * milli-percent.
 */
#include "entities.h"
#include "events.h"
#include "game.h"
#include "render.h"
#include "trace.h"

/*
 * DESIGN 9's threshold table, in the order the meter crosses it.  Each row is
 * the percent that opens the band, the palette variant it substitutes in, the
 * music tempo it sets, and the HUD line it announces.
 */
typedef struct {
    uint8_t  percent;
    uint8_t  palette_variant;
    uint8_t  message;
    uint16_t tempo_bpm;
} TraceBand;

static const TraceBand TRACE_BANDS[TRACE_BAND_COUNT] = {
    { 0,                        PALETTE_VARIANT_CLEAN,    EV_NONE,
      TRACE_TEMPO_CLEAN },
    { TRACE_THRESHOLD_DEGRADED, PALETTE_VARIANT_DEGRADED, EV_MSG_TRACE_DEGRADED,
      TRACE_TEMPO_DEGRADED },
    { TRACE_THRESHOLD_TIER,     PALETTE_VARIANT_DEGRADED, EV_MSG_TRACE_TIER,
      TRACE_TEMPO_TIER },
    { TRACE_THRESHOLD_CORRUPT,  PALETTE_VARIANT_CORRUPT,  EV_MSG_TRACE_CORRUPT,
      TRACE_TEMPO_CORRUPT },
    { TRACE_THRESHOLD_HARDENED, PALETTE_VARIANT_CORRUPT,  EV_MSG_TRACE_HARDENED,
      TRACE_TEMPO_HARDENED },
};

/*
 * DESIGN 9's enemy escalation, by band.  DESIGN 18 item 5 ships the palette and
 * the tempo but no tier-up behaviour in the first playable, so this number is
 * published for the platform layer and read by nothing in the sim except the
 * Watchdog's +2-cell alert radius, which is a sight change and not a tier.
 */
static uint8_t enemy_tier_for_band(uint8_t band)
{
    if (band >= TRACE_BAND_CORRUPT) {
        return ENEMY_TIER_HOSTILE;
    }
    return band >= TRACE_BAND_TIER ? ENEMY_TIER_ELEVATED : ENEMY_TIER_BASE;
}

/*
 * The band of a meter reading, compared in MILLI-percent.  Converting to whole
 * percent first would be a 32-bit divide by 1000 - a __divsi3 call - on every
 * tick and on every one-shot; scaling the four thresholds up instead is four
 * compares against constants the compiler folds.
 */
static uint8_t band_for_milli(int32_t milli)
{
    uint8_t band = TRACE_BAND_COUNT - 1;

    while (band > 0
           && milli < (int32_t)TRACE_BANDS[band].percent * TRACE_MILLI_PER_PERCENT) {
        --band;
    }
    return band;
}

/*
 * Recompute everything the thresholds publish, and announce a band the meter
 * has just entered.  Announcing only on a RISE is deliberate: a scrubber that
 * drops you back under 50% should not ring the alarm on the way down.
 */
static void trace_refresh_bands(GameState *state)
{
    uint8_t band = band_for_milli(state->trace_milli);
    const TraceBand *row = &TRACE_BANDS[band];

    if (band > state->trace_band) {
        event_push(&state->events, row->message);
        event_push(&state->events, EV_SFX_TRACE_ALARM);
    }
    state->trace_band = band;
    state->music_tempo_bpm = row->tempo_bpm;
    state->enemy_tier = enemy_tier_for_band(band);
    /* A level authored corrupt stays corrupt: the meter escalates the palette,
     * it never cleans it up. */
    state->palette_variant = row->palette_variant > state->level->palette_variant
                           ? row->palette_variant : state->level->palette_variant;
}

static void trace_clamp(GameState *state)
{
    if (state->trace_milli > TRACE_MAX_MILLI) {
        state->trace_milli = TRACE_MAX_MILLI;
        state->trace_remainder = 0;
    } else if (state->trace_milli < 0) {
        state->trace_milli = 0;
        state->trace_remainder = 0;
    }
}

void trace_apply(GameState *state, int32_t milli)
{
    state->trace_milli += milli;
    trace_clamp(state);
    trace_refresh_bands(state);
}

void run_progress_reset(RunProgress *progress)
{
    progress->sectors_over_par = 0;
    progress->deaths_this_sector = 0;
    progress->integrity = PLAYER_INTEGRITY_START;
    progress->cycles = PLAYER_CYCLES_START;
}

void trace_init(GameState *state, const RunProgress *progress)
{
    const Level *level = state->level;
    uint8_t over_par = progress ? progress->sectors_over_par : 0;
    uint8_t deaths = progress ? progress->deaths_this_sector : 0;
    int32_t start = (int32_t)level->trace_start
                  + TRACE_START_PER_OVER_PAR * over_par
                  + TRACE_START_PER_DEATH * deaths;

    /* DESIGN 9: trace_carry_cap is the single authority on the start value, so
     * no amount of over-par running or dying can start you above it. */
    if (start > level->trace_carry_cap) {
        start = level->trace_carry_cap;
    }
    state->trace_milli = start * TRACE_MILLI_PER_PERCENT;
    state->trace_remainder = 0;
    state->deaths_this_sector = deaths;
    /* Publish the bands without announcing them: a run that starts at 25% has
     * not "crossed" anything the player did. */
    state->trace_band = band_for_milli(state->trace_milli);
    trace_refresh_bands(state);
}

/*
 * The per-second rates of DESIGN 9's rise table, before the throttle scales
 * them.  The idle credit is deliberately outside this: DESIGN 5's arithmetic
 * for standing still at UNDERCLOCK is 0.18 x 0.5 - 0.20 = -0.11 %/s, so the
 * credit is NOT scaled by the throttle and the rise is.
 */
static int32_t trace_rise_per_second(const GameState *state)
{
    int32_t rate = state->level->trace_base_rate;

    if (state->enemy_has_los) {
        rate += TRACE_RATE_ENEMY_LOS;
    }
    /* rate is at most base + LOS = 780 and trace_scale at most 410, so this is
     * a word product and not a __mulsi3 call. */
    return mul16((int16_t)rate, (int16_t)render_mode(state)->trace_scale) >> 8;
}

/*
 * Standing still is the player not ASKING to move, not the collider refusing.
 * It is judged on the input this tick is acting on and not on prev_input, which
 * still holds the previous tick's word while the meter runs.
 */
static int player_is_still(uint16_t input)
{
    const uint16_t MOVE_INPUTS = INPUT_FORWARD | INPUT_BACK
                               | INPUT_STRAFE_LEFT | INPUT_STRAFE_RIGHT;

    return (input & MOVE_INPUTS) == 0;
}

void trace_step(GameState *state, uint16_t input)
{
    int32_t per_second = trace_rise_per_second(state);

    /* DESIGN 5: the only thing in the game that lowers trace passively. */
    if (state->throttle == THROTTLE_UNDERCLOCK && player_is_still(input)) {
        per_second -= TRACE_RATE_IDLE_CREDIT;
    }

    state->trace_remainder = (int16_t)(state->trace_remainder + per_second);
    state->trace_milli += state->trace_remainder / SIM_HZ;
    state->trace_remainder = (int16_t)(state->trace_remainder % SIM_HZ);

    trace_clamp(state);
    trace_refresh_bands(state);
}

void game_start_level(GameState *state, const Level *level, uint32_t seed,
                      const RunProgress *progress)
{
    game_init(state, level, seed);
    trace_init(state, progress);
    if (!progress) {
        return;                         /* game_init already set the fresh-run values */
    }
    /* DESIGN 4: integrity and cycles carry between sectors, and integrity gains
     * +25 capped at 100 at each sector start.  Tokens do not carry: they are
     * discarded at the exit gate. */
    state->integrity = progress->integrity + PLAYER_INTEGRITY_SECTOR_BONUS;
    if (state->integrity > PLAYER_INTEGRITY_MAX) {
        state->integrity = PLAYER_INTEGRITY_MAX;
    }
    state->cycles = progress->cycles;
}
