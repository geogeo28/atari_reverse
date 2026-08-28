/*
 * events.c - the sim-to-platform ring, and the cue each event asks for.
 *
 * See events.h for the drop policy and event_sfx.h for the map.
 */
#include "event_sfx.h"
#include "events.h"

void event_reset(EventQueue *queue)
{
    queue->head = 0;
    queue->tail = 0;
    queue->dropped = 0;
    queue->pad = 0;
}

/* Slots still writable.  One slot is always left empty, which is what makes
 * head == tail mean "empty" and not "full". */
static uint8_t event_free_slots(const EventQueue *queue)
{
    uint8_t used = (uint8_t)((queue->head - queue->tail) & EVENT_QUEUE_MASK);

    return (uint8_t)(EVENT_QUEUE_MASK - used);
}

/* Is this cue already waiting to be played? */
static int event_already_queued(const EventQueue *queue, uint8_t id)
{
    uint8_t slot = queue->tail;

    while (slot != queue->head) {
        if (queue->ids[slot] == id) {
            return 1;
        }
        slot = (uint8_t)((slot + 1) & EVENT_QUEUE_MASK);
    }
    return 0;
}

static void event_drop(EventQueue *queue)
{
    if (queue->dropped < 0xff) {
        ++queue->dropped;
    }
}

void event_push(EventQueue *queue, uint8_t id)
{
    uint8_t free_slots = event_free_slots(queue);

    if (id == EV_NONE) {
        return;                     /* a row with no cue: trace.c's CLEAN band */
    }
    if (!EVENT_IS_MESSAGE(id)) {
        /* One channel plays one thing, so a second copy of a cue already
         * waiting is not a quieter version of it - it is nothing at all.  Four
         * Watchdogs waking together are one snarl. */
        if (event_already_queued(queue, id)) {
            return;
        }
        /* The reserved tail belongs to the HUD: a dropped line is a rule the
         * player is never told, and a dropped snarl is a sound they can see the
         * cause of. */
        if (free_slots <= EVENT_QUEUE_MESSAGE_RESERVE) {
            event_drop(queue);
            return;
        }
    }
    if (free_slots == 0) {
        event_drop(queue);
        return;
    }
    queue->ids[queue->head] = id;
    queue->head = (uint8_t)((queue->head + 1) & EVENT_QUEUE_MASK);
}

int event_pop(EventQueue *queue, uint8_t *id)
{
    if (queue->tail == queue->head) {
        return 0;
    }
    *id = queue->ids[queue->tail];
    queue->tail = (uint8_t)((queue->tail + 1) & EVENT_QUEUE_MASK);
    return 1;
}

uint8_t event_sfx(uint8_t id)
{
    return event_sfx_of_id(id);
}
