/* evwait.c — A WAIT QUEUED, AND WAITED FOR (`aes/evwait.h`): gemasync's iasync and mwait, geminput's akbin, adelay,
 * abutton, amouse and amutex, and the semaphore's release, unsync. Alcyon C in the ROM, ported over its own order.
 *
 * Every read is where the ROM makes it: the running process (AES_RLR) and its CDA (AES_GL_CDA) are read again for
 * each word taken through them, an EVB's word the ROM tests in memory is tested in memory, and a pointer is carried
 * as the 32 bits the ROM carries and put on the 24-bit bus only where it is dereferenced.
 *
 * amouse's FRAME is the ROM's where its address escapes: its copy of the MOBLK stands in through `host_slot.h` off
 * target (lbcopy fills it, inside reads its rectangle), laid out as the ROM's `link` lays it.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "transcribed.h"
#include "aes/aes.h"
#include "aes/evasync.h"
#include "aes/evdoor.h"
#include "aes/evinput.h"
#include "aes/evsync.h"
#include "aes/evwait.h"
#include "aes/fmlib.h"
#include "aes/gsx.h"
#include "aes/objects.h"
#include "aes/pdpipe.h"
#include "aes/rect.h"
#include "aes/strings.h"
#include "aes/switch.h"
#include "aes/wmupdate.h"

#define AMOUSE_MOBLK_BYTES    (EV_MOBLK_WORDS * (uint32_t)sizeof(uint16_t))    /* ($fe5672 move.w #10,(sp): lbcopy's count) */
_Static_assert(HOST_SLOT_AES_AMOUSE_MOBLK_BYTES == AMOUSE_MOBLK_BYTES, "amouse's frame and its host slot");
_Static_assert(EV_MOBLK_RECT + GRECT_BYTES == AMOUSE_MOBLK_BYTES, "a MOBLK is its flag and one GRECT");

/* A wait list of the running process's CDA (CDA_*_WAIT) or its key queue: the address, AES_GL_CDA read for it. */
static inline uint32_t in_the_cda(const uint8_t *image, uint32_t field)
{
    return be32(image + AES_GL_CDA) + field;
}

/* $fe40b2 — mwait: the running process waits for any event of `mask`. With none of them come it is marked WAITING
 * and the dispatcher entered: the call comes back when the scheduler runs this process again, an event of the mask
 * posted to it. Answers every event that has come, the mask's or not. */
uint16_t aes_ev_mwait(uint8_t *image, int16_t mask)
{
    set_bus_word(image, running(image, PD_EVWAIT), (uint16_t)mask);
    if (!(bus_word(image, running(image, PD_EVFLG)) & (uint16_t)mask)) {
        set_bus_word(image, running(image, PD_STAT), PD_STAT_WAITING);
        aes_dsptch(image);
    }
    return bus_word(image, running(image, PD_EVFLG));
}

/* PAST THE LAST EVB — a ROM defect, refused by name OFF TARGET ALONE. get_evb answers 0 when no EVB is free and
 * iasync does not test it: the ROM builds the wait in "the EVB at address 0". On a 68000 the first of those stores
 * (EVB_NEXT, at 0..3: ROM) is a BUS ERROR; the oracle's model lets it through and writes on over the exception
 * vectors — a state no machine reaches, which a differential would then hold the C to. (The low-memory twin of
 * `m68k_idioms.h`'s store above RAM.) The target build keeps the ROM's plain stores, and takes the bus error it takes.
 * UNREACHABLE BY COUNTING on the machine as it boots: fifteen EVBs and five more with each accessory ($fe4536), where
 * a blocked call asks six at most (ev_multi) and the screen manager's own asks three. */
#define NO_EVB_FREE  "iasync: no EVB is free (get_evb answers none, which the ROM does not test: it builds the wait " \
                     "at address 0 — a bus error on a 68000, where the oracle writes on over the exception vectors)"

/* $fe40ec — iasync: an EVB taken off the free list (get_evb, whose "none" is not tested: above) and put at the head
 * of the running process's, naming that process, on no wait list; given the first event bit none of the process's
 * EVBs holds — the bit shifted IN THE EVB, so with all sixteen held it leaves the word 0 — and that bit added to the
 * process's. Then the wait of `code` queued over `parameter` (IASYNC_*; any other code queues nothing). Answers the
 * EVB's event bit, read after the wait is queued. */
uint16_t aes_iasync(uint8_t *image, int16_t code, uint32_t parameter)
{
    uint32_t evb = aes_get_evb(image);

#ifdef RECREATE_HOST_DIFFERENTIAL
    if (!evb)
        recreate_not_reconstructed(NO_EVB_FREE);
#endif
    set_bus_long(image, evb + EVB_NEXT, bus_long(image, running(image, PD_EVLIST)));
    set_bus_long(image, running(image, PD_EVLIST), evb);
    set_bus_long(image, evb + EVB_PD, be32(image + AES_RLR));
    set_bus_long(image, evb + EVB_PRED, 0);
    set_bus_word(image, evb + EVB_FLAG, 0);
    set_bus_word(image, evb + EVB_MASK, IASYNC_FIRST_EVENT);
    while (bus_word(image, running(image, PD_EVBITS)) & bus_word(image, evb + EVB_MASK))
        set_bus_word(image, evb + EVB_MASK, (uint16_t)(bus_word(image, evb + EVB_MASK) << 1));
    set_bus_word(image, running(image, PD_EVBITS),
                 bus_word(image, running(image, PD_EVBITS)) | bus_word(image, evb + EVB_MASK));
    switch (code) {
    case IASYNC_READ:     aes_aqueue(image, PIPE_READING, evb, parameter); break;
    case IASYNC_WRITE:    aes_aqueue(image, PIPE_WRITING, evb, parameter); break;
    case IASYNC_DELAY:    aes_adelay(image, evb, (int32_t)parameter); break;
    case IASYNC_MUTEX:    aes_amutex(image, evb, parameter); break;
    case IASYNC_KEYBOARD: aes_akbin(image, evb); break;
    case IASYNC_MOUSE:    aes_amouse(image, evb, parameter); break;
    case IASYNC_BUTTON:   aes_abutton(image, evb, parameter); break;
    default:              break;
    }
    return bus_word(image, evb + EVB_MASK);
}

/* $fe5520 — akbin: a wait for a key. One queued for the running process is taken at once — the key the answer's low
 * word, its high word clear — and the EVB completed; else the EVB waits on the CDA's keyboard list. */
void aes_akbin(uint8_t *image, uint32_t evb)
{
    if (bus_word(image, in_the_cda(image, CDA_KEY_COUNT))) {
        set_bus_long(image, evb + EVB_RETURN, (uint16_t)aes_dq(image, in_the_cda(image, CDA_KEY_QUEUE)));
        aes_azombie(image, evb);
        return;
    }
    aes_evinsert(image, evb, in_the_cda(image, CDA_KEYBOARD_WAIT));
}

/* $fe5566 — adelay: a wait of `ticks` (none: one), under the interrupt mask — the tick glue walks the same list.
 * THE COUNTDOWN the tick glue counts to the next expiry: armed with these ticks when none runs (and the ticks
 * counted so far cleared), else shortened to them when they are no more than it holds — compared SIGNED.
 * THE DELAY LIST is a DELTA list: the EVB goes before the first delay that has at least as many ticks left as it
 * (signed again), its own ticks less those of every delay it passed, and the one it is put before keeps the
 * difference. */
void aes_adelay(uint8_t *image, uint32_t evb, int32_t ticks)
{
    uint32_t before, after;

    if (!ticks)
        ticks = ADELAY_LEAST_TICKS;
    aes_spl7_save(image);
    if (be32(image + AES_TIMER_COUNTDOWN)) {
        if (ticks <= (int32_t)be32(image + AES_TIMER_COUNTDOWN))
            wr32(image + AES_TIMER_COUNTDOWN, (uint32_t)ticks);
    } else {
        arm_the_tick(image, (uint32_t)ticks);
    }
    set_bus_word(image, evb + EVB_FLAG, bus_word(image, evb + EVB_FLAG) | EVB_FLAG_DELAY);
    before = AES_DELAY_LIST - be32(image + AES_ELINKOFF);
    after = be32(image + AES_DELAY_LIST);
    while (after && ticks > (int32_t)bus_long(image, after + EVB_PARM)) {
        ticks -= (int32_t)bus_long(image, after + EVB_PARM);
        before = after;
        after = bus_long(image, before + EVB_LINK);
    }
    set_bus_long(image, evb + EVB_PRED, before);
    set_bus_long(image, before + EVB_LINK, evb);
    set_bus_long(image, evb + EVB_PARM, (uint32_t)ticks);
    set_bus_long(image, evb + EVB_LINK, after);
    if (after) {
        uint32_t left = bus_long(image, after + EVB_PARM) - (uint32_t)ticks;

        set_bus_long(image, after + EVB_PRED, evb);
        set_bus_long(image, after + EVB_PARM, left);
    }
    aes_spl_restore(image);
}

/* $fe55f8 — abutton: a wait for the buttons `wanted` (clicks, mask and state: `aes/evdoor.h`'s EV_BUTTON_PARAMETER).
 * As wanted now (downorup, over the buttons as they are): the buttons the answer's high word, the EVB completed.
 * Else a wait for more than one click is counted among those pending (AES_GL_BPEND — b_click opens the click delay
 * only while one is), the parameter kept in the EVB, and the EVB put on the CDA's button list. */
void aes_abutton(uint8_t *image, uint32_t evb, uint32_t wanted)
{
    if (aes_downorup(image, (int16_t)be16(image + AES_BUTTON), wanted)) {
        set_bus_long(image, evb + EVB_RETURN, (uint32_t)be16(image + AES_BUTTON) << HIGH_WORD_SHIFT);
        aes_azombie(image, evb);
        return;
    }
    if ((int16_t)((wanted >> BUTTON_PARM_CLICKS_SHIFT) & BUTTON_PARM_BYTE) > ONE_CLICK)
        wr16(image + AES_GL_BPEND, (uint16_t)(be16(image + AES_GL_BPEND) + 1));
    set_bus_long(image, evb + EVB_PARM, wanted);
    aes_evinsert(image, evb, in_the_cda(image, CDA_BUTTON_WAIT));
}

/* A rectangle's two words as amouse keeps them in an EVB's longword: the first the high word, the second ADDED to
 * it sign-extended (`ext.l d1; add.l d1,d0`) — a negative y or h borrows one from the x or w above it. */
static inline uint32_t high_and_signed_low(uint16_t high, int16_t low)
{
    return ((uint32_t)high << HIGH_WORD_SHIFT) + (uint32_t)(int32_t)low;
}

/* $fe5666 — amouse: a wait for the mouse to enter or leave the rectangle of the MOBLK at `moblk`, copied into the
 * frame first (every later read is the copy's). The mouse already where the wait asks — inside, as a word, differs
 * from the MOBLK's leave flag — completes the EVB. Else the EVB is flagged LEAVE or not, keeps the rectangle (x and
 * y in its parameter, w and h in its ANSWER: what post_mouse's inorout tests it by) and goes on the CDA's mouse
 * list. */
void aes_amouse(uint8_t *image, uint32_t evb, uint32_t moblk)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(AMOUSE_MOBLK_BYTES)];
    uint32_t frame = host_slot_claim(AES_AMOUSE_MOBLK, frame_local);
    uint32_t rect = frame + EV_MOBLK_RECT;

    aes_lbcopy(image, frame, moblk, (int16_t)AMOUSE_MOBLK_BYTES);
    if (aes_inside(image, global_word(image, AES_XRAT), global_word(image, AES_YRAT), rect)
        != (int16_t)be16(image + frame + EV_MOBLK_LEAVE)) {
        aes_azombie(image, evb);
    } else {
        if (be16(image + frame + EV_MOBLK_LEAVE))
            set_bus_word(image, evb + EVB_FLAG, bus_word(image, evb + EVB_FLAG) | EVB_FLAG_LEAVE);
        else
            set_bus_word(image, evb + EVB_FLAG, bus_word(image, evb + EVB_FLAG) & (uint16_t)~EVB_FLAG_LEAVE);
        set_bus_long(image, evb + EVB_PARM, high_and_signed_low(be16(image + rect + GRECT_X),
                                                                (int16_t)be16(image + rect + GRECT_Y)));
        set_bus_long(image, evb + EVB_RETURN, high_and_signed_low(be16(image + rect + GRECT_W),
                                                                  (int16_t)be16(image + rect + GRECT_H)));
        aes_evinsert(image, evb, in_the_cda(image, CDA_MOUSE_WAIT));
    }
    host_slot_release(AES_AMOUSE_MOBLK);
}

/* $fe4e8e — amutex: a wait for the semaphore at `semaphore`. Taken (tak_flag) completes the EVB; refused, the EVB
 * goes at the head of the semaphore's wait list — the last to wait is the first unsync hands it to. */
void aes_amutex(uint8_t *image, uint32_t evb, uint32_t semaphore)
{
    if (aes_tak_flag(image, semaphore))
        aes_azombie(image, evb);
    else
        aes_evinsert(image, evb, semaphore + SPB_WAIT);
}

/* $fe4eb8 — unsync: the semaphore at `semaphore` given up once. Still held (the count not 0): nothing more. At 0
 * with nobody waiting: no owner. At 0 with a wait queued: the list's first EVB taken off it BY THE HEAD ALONE (the
 * EVB after it keeps the first as its predecessor — azombie then links the first elsewhere), its process the owner
 * with one hold, the EVB completed — which makes that process ready — and the caller YIELDS to the dispatcher. */
EVDOOR_TWIN
uint16_t aes_unsync(uint8_t *image, uint32_t semaphore)
{
    uint32_t waiting;

    set_bus_word(image, semaphore + SPB_COUNT, (uint16_t)(bus_word(image, semaphore + SPB_COUNT) - 1));
    if (bus_word(image, semaphore + SPB_COUNT))
        return UNSYNC_NOBODY_WAITS;     /* not the ROM's D0 (its caller's own, untouched): nothing reads it */
    waiting = bus_long(image, semaphore + SPB_WAIT);
    if (!waiting) {
        set_bus_long(image, semaphore + SPB_OWNER, 0);
        return UNSYNC_NOBODY_WAITS;
    }
    set_bus_long(image, semaphore + SPB_WAIT, bus_long(image, waiting + EVB_LINK));
    set_bus_long(image, semaphore + SPB_OWNER, bus_long(image, waiting + EVB_PD));
    set_bus_word(image, semaphore + SPB_COUNT, SPB_FIRST_HOLD);
    aes_azombie(image, waiting);
    aes_dsptch(image);
    return UNSYNC_NOBODY_WAITS;         /* ...nor this one (what the scheduler brings back) */
}
