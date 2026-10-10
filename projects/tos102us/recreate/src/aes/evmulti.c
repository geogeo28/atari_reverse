/* evmulti.c — evnt_multi (`aes/evmulti.h`): gemevlib's ev_multi, Alcyon C in the ROM, ported over its own order.
 *
 * Every read is where the ROM makes it: the running process (AES_RLR) is read again for each word taken through it, a
 * global a callee may have stored is read again after the call (the click record's buttons under downorup, the
 * buttons under ev_rets), and the answers' pointer is put on the 24-bit bus for each store.
 *
 * THE MESSAGE WAIT'S QPB is a local of the ROM's frame (-8(a6): the running process's id, a message's sixteen bytes,
 * the buffer), handed to iasync BY ITS ADDRESS, which the wait's EVB keeps — while the process is parked, until another
 * process's write serves it through it, and after: an EVB is freed as it is. Off target it is a slot of the RUNNING
 * PROCESS's own (`host_slot.h`, A SLOT PER PROCESS), as ap_rdwr's QPB is and beside it: the fast path's ev_mesag has
 * claimed and given back ap_rdwr's before any wait is queued.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "stack_diet.h"
#include "transcribed.h"
#include "aes/aes.h"
#include "aes/apmsg.h"
#include "aes/evasync.h"
#include "aes/evdoor.h"
#include "aes/evfork.h"
#include "aes/evinput.h"
#include "aes/evlib.h"
#include "aes/evmulti.h"
#include "aes/evwait.h"
#include "aes/fmlib.h"
#include "aes/gsx.h"
#include "aes/pdpipe.h"
#include "aes/strings.h"
#include "aes/wmupdate.h"

_Static_assert(HOST_SLOT_AES_EV_MULTI_QPB_BYTES == HOST_PROCESSES * QPB_BYTES,
               "ev_multi's QPB (-8(a6)..-1(a6)) and its host slot: one QPB per process");

/* The event bit of each wait ev_multi queued (0: not asked for), and all of them — the ROM's -22(a6)..-10(a6) — with
 * the image address of the message wait's QPB. */
struct queued_waits {
    uint16_t key, buttons, first_mouse, second_mouse, message, timer, all;
    uint32_t qpb;
};

/* An answer word stored through the answers' pointer. */
static inline void answer(uint8_t *image, uint32_t answers, uint32_t which, uint16_t value)
{
    set_bus_word(image, answers + which, value);
}

/* The fast path's BUTTON test ($fe6a00..$fe6a70), for the process that owns the mouse alone (compared as longs).
 * With more than one button change posted since the last ev_rets, the buttons BEFORE the last change are tried
 * first (the click record's, with its clicks): a press and its release in one pass still answer the press. Then the
 * buttons as they are, with the last change's clicks. The buttons that satisfied the wait are left where ev_rets
 * reads them. Each global is read again after downorup, as the ROM reads it. */
static inline uint16_t buttons_come_already(uint8_t *image, uint32_t wanted, uint32_t answers)
{
    if (be32(image + AES_RLR) != be32(image + AES_GL_MOWNER))
        return 0;
    if (global_word(image, AES_MTRANS) > EV_MULTI_ONE_CHANGE
        && aes_downorup(image, global_word(image, AES_PR_BUTTON), wanted)) {
        wr16(image + AES_EV_BUTTON_STATE, be16(image + AES_PR_BUTTON));
        answer(image, answers, EV_MULTI_CLICKS, be16(image + AES_PR_MCLICK));
        return EV_MU_BUTTON;
    }
    if (aes_downorup(image, global_word(image, AES_BUTTON), wanted)) {
        wr16(image + AES_EV_BUTTON_STATE, be16(image + AES_BUTTON));
        answer(image, answers, EV_MULTI_CLICKS, be16(image + AES_MCLICK));
        return EV_MU_BUTTON;
    }
    return 0;
}

/* IT POLLS FIRST ($fe69cc..$fe6ac6): every event asked for that has come already, each taken where it is found — a
 * queued key off the running process's own queue (its PD's CDA, not AES_GL_CDA), a message read out of its pipe (a
 * pipe that holds anything, its index compared signed). A timer of no time has always come — and is tested BEFORE
 * the message, the one place the ROM leaves the flags' bit order. (The ROM also tests there that no wait is queued
 * yet, `tst.w -10(a6)`: none ever is, the word was cleared at entry.) */
static inline uint16_t come_already(uint8_t *image, int16_t flags, uint32_t mouse1, uint32_t mouse2, uint32_t timer,
                                    uint32_t button, uint32_t message, uint32_t answers)
{
    uint16_t came = 0;

    if (flags & EV_MU_KEYBD) {
        uint32_t keys = bus_long(image, running(image, PD_CDA)) + CDA_KEY_QUEUE;

        if (bus_word(image, keys + CQUEUE_COUNT)) {
            answer(image, answers, EV_MULTI_KEY, (uint16_t)aes_dq(image, keys));
            came |= EV_MU_KEYBD;
        }
    }
    if (flags & EV_MU_BUTTON)
        came |= buttons_come_already(image, button, answers);
    if ((flags & EV_MU_M1) && aes_ev_mchk(image, mouse1))
        came |= EV_MU_M1;
    if ((flags & EV_MU_M2) && aes_ev_mchk(image, mouse2))
        came |= EV_MU_M2;
    if ((flags & EV_MU_TIMER) && !timer)
        came |= EV_MU_TIMER;
    if ((flags & EV_MU_MESAG) && signed_field(image, be32(image + AES_RLR), PD_QUEUE_INDEX) > 0) {
        (void)aes_ev_mesag(image, message);
        came |= EV_MU_MESAG;
    }
    return came;
}

/* One wait queued, its event bit added to all of them. */
static inline uint16_t queued(uint8_t *image, struct queued_waits *waits, int16_t code, uint32_t parameter)
{
    uint16_t event = aes_iasync(image, code, parameter);

    waits->all |= event;
    return event;
}

/* NOTHING HAS COME ($fe6ad0..$fe6b90): a wait queued for every event asked for — the message's over a QPB of this
 * call's own (the running process's id as its PD holds it, one message's bytes, the buffer), the timer's in ticks
 * (the long divided by the tick's milliseconds as a signed long, as ev_timer divides it). `qpb_local` is that QPB on
 * target, where the wait's EVB keeps its address. */
static inline void queue_the_waits(uint8_t *image, struct queued_waits *waits, uint16_t *qpb_local, int16_t flags,
                                   uint32_t mouse1, uint32_t mouse2, uint32_t timer, uint32_t button, uint32_t message)
{
    if (flags & EV_MU_KEYBD)
        waits->key = queued(image, waits, IASYNC_KEYBOARD, 0);
    if (flags & EV_MU_BUTTON)
        waits->buttons = queued(image, waits, IASYNC_BUTTON, button);
    if (flags & EV_MU_M1)
        waits->first_mouse = queued(image, waits, IASYNC_MOUSE, mouse1);
    if (flags & EV_MU_M2)
        waits->second_mouse = queued(image, waits, IASYNC_MOUSE, mouse2);
    if (flags & EV_MU_MESAG) {
        uint16_t process = (uint16_t)running_process_id(image);

        waits->qpb = host_slot_claim_for(AES_EV_MULTI_QPB, qpb_local, process);
        wr16(image + waits->qpb + QPB_PID, process);
        wr16(image + waits->qpb + QPB_COUNT, AP_MSG_BYTES);
        wr32(image + waits->qpb + QPB_BUFFER, message);
        waits->message = queued(image, waits, IASYNC_READ, waits->qpb);
    }
    if (flags & EV_MU_TIMER)
        waits->timer = queued(image, waits, IASYNC_DELAY,
                              (uint32_t)aes_ldiv(image, (int32_t)timer, (int16_t)be16(image + AES_GL_TICK_MS)));
}

/* Did the wait of `event` come? Answered if so — its EVB freed — into `*answered`. */
static inline int came_and_answered(uint8_t *image, uint16_t arrived, uint16_t event, uint16_t *answered)
{
    if (!(arrived & event))
        return 0;
    *answered = (uint16_t)aes_apret(image, (int16_t)event);
    return 1;
}

/* THE WAITS THAT CAME, ANSWERED ($fe6bc2..$fe6c4a) in the ROM's order: the key into its answer word; the clicks into
 * theirs and the buttons apret just left (AES_EV_BUTTON_STATE) over ev_rets' third answer; the others' answers
 * dropped. The events that came. */
static inline uint16_t answer_the_waits(uint8_t *image, const struct queued_waits *waits, uint16_t arrived,
                                        uint32_t answers)
{
    uint16_t came = 0, answered;

    if (came_and_answered(image, arrived, waits->key, &answered)) {
        answer(image, answers, EV_MULTI_KEY, answered);
        came |= EV_MU_KEYBD;
    }
    if (came_and_answered(image, arrived, waits->buttons, &answered)) {
        answer(image, answers, EV_MULTI_CLICKS, answered);
        answer(image, answers, EV_RETS_BUTTONS, be16(image + AES_EV_BUTTON_STATE));
        came |= EV_MU_BUTTON;
    }
    if (came_and_answered(image, arrived, waits->first_mouse, &answered))
        came |= EV_MU_M1;
    if (came_and_answered(image, arrived, waits->second_mouse, &answered))
        came |= EV_MU_M2;
    if (came_and_answered(image, arrived, waits->message, &answered))
        came |= EV_MU_MESAG;
    if (came_and_answered(image, arrived, waits->timer, &answered))
        came |= EV_MU_TIMER;
    return came;
}

/* $fe6998 — ev_multi (`aes/evmulti.h` has the five steps). The events that came, a bit each; a message that came
 * clears the control manager's "sent" mark (on the fast path ev_mesag cleared it already). */
FRAME_DIET("no-defer-pop", "no-caller-saves")
EVDOOR_TWIN
uint16_t aes_ev_multi(uint8_t *image, int16_t flags, uint32_t mouse1, uint32_t mouse2, uint32_t timer, uint32_t button,
                      uint32_t message, uint32_t answers)
{
    uint16_t qpb_local[FRAME_LOCAL_WORDS(QPB_BYTES)];
    struct queued_waits waits = {0};
    uint16_t came, arrived = 0;

    aes_chkkbd(image);
    aes_forker(image);
    came = come_already(image, flags, mouse1, mouse2, timer, button, message, answers);
    if (!came) {
        queue_the_waits(image, &waits, qpb_local, flags, mouse1, mouse2, timer, button, message);
        arrived = aes_ev_mwait(image, (int16_t)waits.all);
        arrived |= (uint16_t)aes_acancel(image, (int16_t)waits.all);
    }
    aes_ev_rets(image, answers);
    if (!(flags & EV_MU_BUTTON))
        answer(image, answers, EV_RETS_BUTTONS, be16(image + AES_BUTTON));
    if (!came) {
        came = answer_the_waits(image, &waits, arrived, answers);
        if (waits.qpb)
            host_slot_release_for(AES_EV_MULTI_QPB, waits.qpb);
    }
    if (came & EV_MU_MESAG)
        wr16(image + AES_CTL_MESSAGE_SENT, 0);
    return came;
}
