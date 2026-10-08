/* evasync.c — THE EVENT BLOCKS' LISTS (`aes/evasync.h`): gemasync's signal, azombie, get_evb, evinsert, takeoff, apret
 * and acancel, and geminput's evremove. Alcyon C in the ROM, ported over its own order.
 *
 * Every read is where the ROM makes it: a link or a list's head is read again each time the ROM reads it again (an EVB
 * a caller hands in may lie over the list it is put on), and the running process (AES_RLR) is read again for each of
 * its words apret and acancel clear. A pointer is carried as the 32 bits the ROM carries — stored, and compared, with
 * whatever top byte it came with — and put on the 24-bit bus only where it is dereferenced.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/evasync.h"
#include "aes/strings.h"

_Static_assert(PD_LINK == 0 && EVB_NEXT == 0, "a list's head is walked as the record before its first");

/* A wait list's head, as the EVB before its first: the address whose EVB_LINK is the head. */
static inline uint32_t head_as_evb(const uint8_t *image, uint32_t head)
{
    return head - be32(image + AES_ELINKOFF);
}

/* An EVB off the doubly linked list it is on: its predecessor's link past it, its successor's (if any) back — and
 * whether it had a successor. The ROM spells it three times ($fe406e takeoff, $fe420c apret, $fe5160 evremove), each
 * reading the EVB's two links again for every use. */
static inline int leave_list(uint8_t *image, uint32_t evb)
{
    set_bus_long(image, bus_long(image, evb + EVB_PRED) + EVB_LINK, bus_long(image, evb + EVB_LINK));
    if (!bus_long(image, evb + EVB_LINK))
        return 0;
    set_bus_long(image, bus_long(image, evb + EVB_LINK) + EVB_PRED, bus_long(image, evb + EVB_PRED));
    return 1;
}

/* An EVB back on the free list, at its head. */
static inline void free_evb(uint8_t *image, uint32_t evb)
{
    set_bus_long(image, evb + EVB_NEXT, be32(image + AES_EUL));
    wr32(image + AES_EUL, evb);
}

/* One of the running process's event words less the bits of `mask` (`rlr` read for each, as the ROM reads it). */
static inline void clear_running(uint8_t *image, uint32_t field, uint16_t mask)
{
    uint32_t at = running(image, field);

    set_bus_word(image, at, (uint16_t)(bus_word(image, at) & (uint16_t)~mask));
}

/* $fe3f5e — signal: the EVB's event posted to its process (PD_EVFLG), and that process — if it is not the running
 * one, is parked on the not-ready list and waits for an event that has come — made ready and moved to the head of
 * the woken list. The not-ready list is walked to it, or to its end, before anything is tested. */
void aes_signal(uint8_t *image, uint32_t evb)
{
    uint32_t pd = bus_long(image, evb + EVB_PD);
    uint16_t event = bus_word(image, evb + EVB_MASK);
    uint32_t link_at = AES_NRL;
    uint32_t parked;

    set_bus_word(image, pd + PD_EVFLG, (uint16_t)(bus_word(image, pd + PD_EVFLG) | event));
    for (parked = be32(image + AES_NRL); parked != pd && parked; parked = bus_long(image, link_at + PD_LINK))
        link_at = parked;
    if (pd == be32(image + AES_RLR))
        return;
    if (!(bus_word(image, pd + PD_EVFLG) & bus_word(image, pd + PD_EVWAIT)))
        return;
    if (!parked)
        return;
    set_bus_word(image, parked + PD_STAT, PD_STAT_READY);
    set_bus_long(image, link_at + PD_LINK, bus_long(image, parked + PD_LINK));
    onto_the_woken_list(image, parked);
}

/* $fe3fba — azombie: the EVB at the head of the completed list, its flag COMPLETE alone (a delay's or a served
 * wait's bit gone), its event signalled. */
void aes_azombie(uint8_t *image, uint32_t evb)
{
    set_bus_long(image, evb + EVB_LINK, be32(image + AES_ZOMBIE_LIST));
    if (be32(image + AES_ZOMBIE_LIST))
        set_bus_long(image, be32(image + AES_ZOMBIE_LIST) + EVB_PRED, evb);
    set_bus_long(image, evb + EVB_PRED, head_as_evb(image, AES_ZOMBIE_LIST));
    wr32(image + AES_ZOMBIE_LIST, evb);
    set_bus_word(image, evb + EVB_FLAG, EVB_FLAG_COMPLETE);
    aes_signal(image, evb);
}

/* $fe4002 — get_evb: the first free EVB off the free list and cleared — or 0 when none is free, which its one caller
 * (iasync, $fe40f8) does not test (off target iasync refuses it by name: `evwait.c`). */
uint32_t aes_get_evb(uint8_t *image)
{
    uint32_t evb = be32(image + AES_EUL);

    if (evb) {
        wr32(image + AES_EUL, bus_long(image, be32(image + AES_EUL) + EVB_NEXT));
        aes_bfill(image, EVB_BYTES, 0, evb);
    }
    return evb;
}

/* $fe4030 — evinsert: the EVB at the HEAD of the wait list whose head is at `list` — so the last to wait is the
 * first found. The list's first is read before any store. */
void aes_evinsert(uint8_t *image, uint32_t evb, uint32_t list)
{
    uint32_t before = head_as_evb(image, list);
    uint32_t first = bus_long(image, list);

    set_bus_long(image, evb + EVB_PRED, before);
    set_bus_long(image, before + EVB_LINK, evb);
    set_bus_long(image, evb + EVB_LINK, first);
    if (first)
        set_bus_long(image, first + EVB_PRED, evb);
}

/* $fe4062 — takeoff: an EVB whose event did not come, off its wait list and freed. A DELAY with one after it on the
 * delay list hands that one its ticks (the list holds differences). The caller has taken it off its process's list. */
void aes_takeoff(uint8_t *image, uint32_t evb)
{
    if (leave_list(image, evb) && (bus_word(image, evb + EVB_FLAG) & EVB_FLAG_DELAY)) {
        uint32_t ticks = bus_long(image, bus_long(image, evb + EVB_LINK) + EVB_PARM) + bus_long(image, evb + EVB_PARM);

        set_bus_long(image, bus_long(image, evb + EVB_LINK) + EVB_PARM, ticks);
    }
    free_evb(image, evb);
}

/* $fe41bc — apret: the running process's EVB of the event `mask` — found on its list by the whole mask, and on the
 * completed list by its address — taken off both and freed, the event's bit cleared in its three event words; its
 * answer's low word answered, the high word left in AES_EV_BUTTON_STATE. With no such EVB, or one not completed,
 * nothing is touched (APRET_NO_EVB, APRET_NOT_COMPLETE): answers no caller reaches, each calling only for an event
 * that came. */
int16_t aes_apret(uint8_t *image, int16_t mask)
{
    uint32_t link_at = running(image, PD_EVLIST);
    uint32_t evb = bus_long(image, link_at);
    uint32_t completed;
    int16_t answer;

    while (evb && bus_word(image, evb + EVB_MASK) != (uint16_t)mask) {
        link_at = evb;
        evb = bus_long(image, link_at + EVB_NEXT);
    }
    if (!evb)
        return APRET_NO_EVB;
    for (completed = be32(image + AES_ZOMBIE_LIST); completed != evb && completed;)
        completed = bus_long(image, completed + EVB_LINK);
    if (!completed)
        return APRET_NOT_COMPLETE;
    (void)leave_list(image, evb);
    set_bus_long(image, link_at + EVB_NEXT, bus_long(image, evb + EVB_NEXT));
    clear_running(image, PD_EVBITS, (uint16_t)mask);
    clear_running(image, PD_EVWAIT, (uint16_t)mask);
    clear_running(image, PD_EVFLG, (uint16_t)mask);
    answer = (int16_t)bus_long(image, evb + EVB_RETURN);
    free_evb(image, evb);
    wr16(image + AES_EV_BUTTON_STATE, (uint16_t)(bus_long(image, evb + EVB_RETURN) >> HIGH_WORD_SHIFT));
    return answer;
}

/* $fe427a — acancel: every EVB of the running process whose event is among `mask`: one completed (or being served)
 * is kept and its event answered; any other is taken off the process's list and its wait list, freed (takeoff), and
 * its bit cleared in the process's event bits and its waits — not in the events that came. The walk goes on from the
 * EVB before the one taken off. */
int16_t aes_acancel(uint8_t *image, int16_t mask)
{
    uint32_t link_at = running(image, PD_EVLIST);
    uint32_t evb = bus_long(image, link_at);
    uint16_t kept = 0;

    while (evb) {
        if (bus_word(image, evb + EVB_MASK) & (uint16_t)mask) {
            if (bus_word(image, evb + EVB_FLAG) & (EVB_FLAG_NOCANCEL | EVB_FLAG_COMPLETE)) {
                kept |= bus_word(image, evb + EVB_MASK);
            } else {
                set_bus_long(image, link_at + EVB_NEXT, bus_long(image, evb + EVB_NEXT));
                aes_takeoff(image, evb);
                clear_running(image, PD_EVBITS, bus_word(image, evb + EVB_MASK));
                clear_running(image, PD_EVWAIT, bus_word(image, evb + EVB_MASK));
                evb = link_at;
            }
        }
        link_at = evb;
        evb = bus_long(image, link_at + EVB_NEXT);
    }
    return (int16_t)kept;
}

/* $fe511a — evremove: an EVB whose event came — its answer's low word ORed in, off its wait list, completed
 * (azombie). First, the pending multi-click waits counted one down, never below one, when the high word of the EVB's
 * parameter has a low byte over one: a button wait's clicks — and, since no kind is tested, a mouse wait's
 * rectangle's x. (A delay reaches here from tchange alone, which clears its parameter first: $fe4e28.) */
void aes_evremove(uint8_t *image, uint32_t evb, int16_t answer)
{
    uint16_t clicks = (uint16_t)(bus_long(image, evb + EVB_PARM) >> BUTTON_PARM_CLICKS_SHIFT) & BUTTON_PARM_BYTE;

    if (clicks > ONE_CLICK && (int16_t)be16(image + AES_GL_BPEND) > ONE_CLICK)
        wr16(image + AES_GL_BPEND, (uint16_t)(be16(image + AES_GL_BPEND) - 1));
    set_bus_long(image, evb + EVB_RETURN, bus_long(image, evb + EVB_RETURN) | (uint16_t)answer);
    (void)leave_list(image, evb);
    aes_azombie(image, evb);
}
