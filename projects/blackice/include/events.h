/*
 * events.h - the one-way channel from the simulation to the platform layer.
 *
 * The sim must not know what a sound chip or a HUD is: it runs on the host
 * under pytest with neither.  So it never plays or draws anything - it pushes
 * an id into a small ring, and the platform layer drains the ring once per
 * frame and decides what a "token grab" sounds like this build (a YM arpeggio
 * now, a DMA sample later) and what "BETA REQUIRED" looks like.
 *
 * Ids are one flat enum in two blocks, SFX first and HUD messages after, so a
 * drainer can classify with one compare against EV_MSG_ALPHA_REQUIRED.  The
 * SFX block is in DESIGN 16's sample-table order, which is also the order the priority
 * column is written in; the platform layer owns the priority table, because
 * preemption is a property of the one channel, not of the event.
 *
 * The ring drops on overflow rather than blocking or growing, and it drops the
 * NEW cue, not the queued one: DESIGN 16 says a one-shot that cannot play is
 * dropped and never queued.  Two rules keep a HUD line from ever being what is
 * lost, because a message the player never reads is a rule they never learn:
 *
 *   - An SFX id already in the ring is not pushed again.  One tick can wake
 *     four Watchdogs, and four snarls are one snarl on a one-shot channel.
 *   - The last EVENT_QUEUE_MESSAGE_RESERVE slots are reserved for messages, so
 *     a tick that generates a snarl per body still has room for the line that
 *     explains what just happened.
 */
#ifndef BLACKICE_EVENTS_H
#define BLACKICE_EVENTS_H

#include <stdint.h>

typedef enum {
    EV_NONE = 0,

    /* ---- SFX, DESIGN 16's sample table in its printed order ---- */
    EV_SFX_BUSTER_SHOT = 1,
    EV_SFX_SPIKE_SHOT,              /* reserved: Spike is deferred (DESIGN 18) */
    EV_SFX_WATCHDOG_SNARL,
    EV_SFX_SENTRY_CHARGE,
    EV_SFX_GATE_OPEN,
    EV_SFX_GATE_CLOSE,
    EV_SFX_TOKEN_GRAB,
    EV_SFX_DOOR_REFUSAL,
    EV_SFX_THROTTLE_CHANGE,
    EV_SFX_TRACE_ALARM,
    EV_SFX_PLAYER_HIT,
    EV_SFX_ENEMY_DISSOLVE,
    EV_SFX_EXFIL_SIREN,
    /* Not in the sample table: the Tracer's own two cues (DESIGN 8). */
    EV_SFX_TRACER_PING,
    EV_SFX_TRACER_SIREN,

    /* ---- HUD message lines (DESIGN 15.1's 38-character message field) ----
     * The block starts at 64 so a drainer can classify with one compare, and
     * the first message IS the boundary rather than a separate alias: an alias
     * would be an id nothing ever sends. */
    EV_MSG_ALPHA_REQUIRED = 64,
    EV_MSG_BETA_REQUIRED,
    EV_MSG_GAMMA_REQUIRED,
    EV_MSG_GATE_SEALED,             /* the Cold Boot Gate, until the 100% exfil */
    EV_MSG_TOKEN_ALPHA,
    EV_MSG_TOKEN_BETA,
    EV_MSG_TOKEN_GAMMA,
    EV_MSG_CYCLES,
    EV_MSG_INTEGRITY,
    EV_MSG_SCRUBBER,
    EV_MSG_DATA_CACHE,
    EV_MSG_TRACE_DEGRADED,          /* the four threshold crossings, in order */
    EV_MSG_TRACE_TIER,
    EV_MSG_TRACE_CORRUPT,
    EV_MSG_TRACE_HARDENED,
    EV_MSG_SECTOR_CLEAR,
    EV_MSG_CONNECTION_TERMINATED,
    EV_ID_COUNT
} EventId;

#define EVENT_IS_MESSAGE(id) ((id) >= EV_MSG_ALPHA_REQUIRED)

/* A power of two, so the wrap is a mask and not a compare-and-branch. */
#define EVENT_QUEUE_SIZE 16
#define EVENT_QUEUE_MASK (EVENT_QUEUE_SIZE - 1)
/*
 * Ring slots no SFX may take.  Four is the most HUD lines one tick has ever
 * been observed to generate - a token grab (line + cycles), a locked-door latch
 * and a band crossing - so a message is never the thing a snarl displaces.
 */
#define EVENT_QUEUE_MESSAGE_RESERVE 4

typedef struct {
    uint8_t ids[EVENT_QUEUE_SIZE];
    uint8_t head;                   /* next slot to write */
    uint8_t tail;                   /* next slot to read */
    uint8_t dropped;                /* pushes lost to a full ring, for diagnostics */
    uint8_t pad;
} EventQueue;

void event_reset(EventQueue *queue);
void event_push(EventQueue *queue, uint8_t id);

/* Pops the oldest event into *id.  Returns 0 when the ring is empty. */
int event_pop(EventQueue *queue, uint8_t *id);

#endif /* BLACKICE_EVENTS_H */
