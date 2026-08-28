/*
 * event_sfx.h - which sound each EventId asks for.
 *
 * events.h is the sim's vocabulary: it names what HAPPENED.  The audio bank in
 * audio/blackice_sfx_ids.h is the platform's vocabulary: it names what can be
 * PLAYED.  The two lists are not the same length, and this file is the one
 * place that says how one maps onto the other - so the drainer in the platform
 * layer is a table lookup and no other file has to hold an opinion about it.
 *
 * ---------------------------------------------------------------------------
 * Why the lists differ
 * ---------------------------------------------------------------------------
 * DESIGN 16's sample table prints thirteen rows.  The shipped bank authored ten
 * (audio/blackice_sfx_ids.h, BLACKICE_SFX_COUNT), and the sim additionally
 * raises the Tracer's own two cues, which DESIGN 8 names in the enemy table and
 * DESIGN 16 never listed.  Five EventIds therefore have no sample of their own:
 *
 *   EV_SFX_GATE_CLOSE      -> the gate sweep, which the driver plays for both
 *                             leaves; the close is the same sound reversed and
 *                             a reversed sample costs no bank space.
 *   EV_SFX_DOOR_REFUSAL    -> the Sentry's charge whine, the only low sustained
 *                             tone in the bank.  DESIGN 16's YM form for the
 *                             refusal ("a low buzz") is the authoritative one
 *                             until the DMA bank authors a refusal of its own.
 *   EV_SFX_THROTTLE_CHANGE -> the token-grab arpeggio, the bank's only short
 *                             two-note click.  DESIGN 16 gives the throttle
 *                             change priority 1 and the grab priority 2, so the
 *                             substitute preempts more than the row asked for;
 *                             that is the cost of not authoring the cue.
 *   EV_SFX_TRACER_PING     -> the Watchdog snarl.  Both are "an enemy has just
 *                             noticed you" on the ALERT transition, which is
 *                             what the cue has to read as.
 *   EV_SFX_TRACER_SIREN    -> the exfil siren.  It is a siren.
 *
 * Every one of the five is a documented substitution and not a silence: a cue
 * the sim raises and the platform cannot play is a rule the player never hears.
 * Authoring the three missing DESIGN 16 samples replaces a row here and nothing
 * else.
 */
#ifndef BLACKICE_EVENT_SFX_H
#define BLACKICE_EVENT_SFX_H

#include <stdint.h>
#include "events.h"

/*
 * The bank's own indices, from audio/blackice_sfx_ids.h - which is GENERATED,
 * lives outside the engine's include path, and cannot be included from here.
 * test_events.py parses that file and asserts these equal, so the duplication
 * is pinned rather than merely hoped for.
 */
#define EVENT_SFX_BUSTER_SHOT     0
#define EVENT_SFX_SPIKE_SHOT      1
#define EVENT_SFX_WATCHDOG_SNARL  2
#define EVENT_SFX_SENTRY_CHARGE   3
#define EVENT_SFX_GATE_OPEN       4
#define EVENT_SFX_TOKEN_GRAB      5
#define EVENT_SFX_TRACE_ALARM     6
#define EVENT_SFX_PLAYER_HIT      7
#define EVENT_SFX_ENEMY_DISSOLVE  8
#define EVENT_SFX_EXFIL_SIREN     9
#define EVENT_SFX_BANK_COUNT      10

/* This id asks for no sound: EV_NONE, and every HUD message line. */
#define EVENT_SFX_NONE            0xff

/*
 * EventId -> bank index, covering EVERY id in events.h.  The designated
 * initialisers mean a new EventId that nobody maps arrives as EVENT_SFX_NONE
 * only if it is spelled below; test_events.py walks the whole enum and fails on
 * an id this table does not name, so "no sound" is always a decision.
 */
static const uint8_t EVENT_SFX_OF_ID[EV_ID_COUNT] = {
    [EV_NONE]                  = EVENT_SFX_NONE,

    [EV_SFX_BUSTER_SHOT]       = EVENT_SFX_BUSTER_SHOT,
    [EV_SFX_SPIKE_SHOT]        = EVENT_SFX_SPIKE_SHOT,
    [EV_SFX_WATCHDOG_SNARL]    = EVENT_SFX_WATCHDOG_SNARL,
    [EV_SFX_SENTRY_CHARGE]     = EVENT_SFX_SENTRY_CHARGE,
    [EV_SFX_GATE_OPEN]         = EVENT_SFX_GATE_OPEN,
    [EV_SFX_GATE_CLOSE]        = EVENT_SFX_GATE_OPEN,       /* substituted; see above */
    [EV_SFX_TOKEN_GRAB]        = EVENT_SFX_TOKEN_GRAB,
    [EV_SFX_DOOR_REFUSAL]      = EVENT_SFX_SENTRY_CHARGE,   /* substituted */
    [EV_SFX_THROTTLE_CHANGE]   = EVENT_SFX_TOKEN_GRAB,      /* substituted */
    [EV_SFX_TRACE_ALARM]       = EVENT_SFX_TRACE_ALARM,
    [EV_SFX_PLAYER_HIT]        = EVENT_SFX_PLAYER_HIT,
    [EV_SFX_ENEMY_DISSOLVE]    = EVENT_SFX_ENEMY_DISSOLVE,
    [EV_SFX_EXFIL_SIREN]       = EVENT_SFX_EXFIL_SIREN,
    [EV_SFX_TRACER_PING]       = EVENT_SFX_WATCHDOG_SNARL,  /* substituted */
    [EV_SFX_TRACER_SIREN]      = EVENT_SFX_EXFIL_SIREN,     /* substituted */

    /* HUD lines: drawn, never sounded. */
    [EV_MSG_ALPHA_REQUIRED]       = EVENT_SFX_NONE,
    [EV_MSG_BETA_REQUIRED]        = EVENT_SFX_NONE,
    [EV_MSG_GAMMA_REQUIRED]       = EVENT_SFX_NONE,
    [EV_MSG_GATE_SEALED]          = EVENT_SFX_NONE,
    [EV_MSG_TOKEN_ALPHA]          = EVENT_SFX_NONE,
    [EV_MSG_TOKEN_BETA]           = EVENT_SFX_NONE,
    [EV_MSG_TOKEN_GAMMA]          = EVENT_SFX_NONE,
    [EV_MSG_CYCLES]               = EVENT_SFX_NONE,
    [EV_MSG_INTEGRITY]            = EVENT_SFX_NONE,
    [EV_MSG_SCRUBBER]             = EVENT_SFX_NONE,
    [EV_MSG_DATA_CACHE]           = EVENT_SFX_NONE,
    [EV_MSG_TRACE_DEGRADED]       = EVENT_SFX_NONE,
    [EV_MSG_TRACE_TIER]           = EVENT_SFX_NONE,
    [EV_MSG_TRACE_CORRUPT]        = EVENT_SFX_NONE,
    [EV_MSG_TRACE_HARDENED]       = EVENT_SFX_NONE,
    [EV_MSG_SECTOR_CLEAR]         = EVENT_SFX_NONE,
    [EV_MSG_CONNECTION_TERMINATED] = EVENT_SFX_NONE,
};

/* The bank cue an event asks for, or EVENT_SFX_NONE. */
static inline uint8_t event_sfx_of_id(uint8_t id)
{
    return id < EV_ID_COUNT ? EVENT_SFX_OF_ID[id] : EVENT_SFX_NONE;
}

/*
 * The same answer as a symbol the platform layer - and the test suite - can
 * link against.  events.c is the one translation unit that includes this
 * header, so the table above has exactly one copy in the image.
 */
uint8_t event_sfx(uint8_t id);

#endif /* BLACKICE_EVENT_SFX_H */
