/* aes/evdoor.h — THE EVENT DOOR: how the AES's C reaches the event layer and the scheduler (ev_multi, ap_rdwr, ...: the
 * dispatcher's layer), entry by entry — each by its C twin (every entry is REBOUND: FLIP 3 was the last).
 *
 * WHAT A DOOR ENTRY IS. A ROM routine of that layer, keyed BY ITS ROM ADDRESS, entered over the Alcyon frame its ROM
 * callers push (`move.w`/`move.l -(sp)`, then a Line-F call word) and answering in D0. Every C call of one goes through
 * its wrapper below — `evdoor_<routine>`, the routine's arguments as the ROM's callers hand them — and nowhere else:
 * the wrapper's body is the call of the entry's C twin (`aes_tak_flag(image, ...)`), on both builds. ON TARGET it is
 * that call and nothing else.
 *
 * OFF TARGET A CALL IS AN ARRIVAL FIRST. The wrapper packs the same frame into bytes and hands it to
 * `recreate_call_event_door`, a hook the case binds (`test/aes_event.py`), which answers EVDOOR_ARRIVED — "noted: run
 * the twin": the case has recorded the frame (what each call is handed is compared with the ROM's own call's, which
 * sees a wrong rectangle the image cannot) and laid the interrupt due at that call. Frame locals whose ADDRESS a
 * caller hands the door (an MOBLK, the answer words) take `host_slot.h` slots, as every escaping local does. A hook
 * that refuses (an entry the case does not bind, a call made WHILE A TWIN RUNS — the next paragraph's rule, at run
 * time) or answers any other word halts the core by name, never carried on. (The hop the ROM's call word takes —
 * vector $2c, the Line-F handler's RAM copy, the call table — is NOT checked here: a wrapper is a C call of a C twin,
 * as every other Alcyon call of the AES's C is, and a case that moved the vector is refused where it shows — the
 * ROM's own run never returns. The checks went with the served road they guarded: band 4 wave 3's retirement.)
 *
 * The twin then runs, and its return is reported to `recreate_event_door_returned` with the word it answered —
 * where the case gives the arrival's place up (a return must answer the innermost arrival in flight) and holds the
 * answer, and the image the twin returns over, to the ROM routine's own at the same door call of the ROM's watched
 * run (`test/aes_event.py`; nothing of the ROM is run there — the nested run that once shadowed a twin at its call
 * went with band 4 wave 3's retirement).
 * Which entries a hook answers for is read off the build (each wrapper spelt through EVDOOR_REBOUND, below, leaves a
 * marker in the library).
 *
 * A TWIN CALLS ANOTHER ENTRY'S CORE, NEVER ITS WRAPPER. The wrappers below are for callers OUTSIDE the event layer
 * (band 3's C: wm_update, fm_do, ...). A twin that needs another entry — amutex taking the semaphore, ev_block queueing
 * through iasync — calls `aes_tak_flag(image, ...)` itself, as the ROM's routine calls the ROM's. Through
 * `evdoor_tak_flag` the host's hook would count one more ARRIVAL than either watched run does (the ROM's run and our
 * blob's are watched at the OUTERMOST door call only; on target the wrapper is the core's call and nothing shows): every
 * ordinal after it — the frames compared, the interrupt laid "at door call k", a slice's mark — would be one off on
 * the host alone, and read as a bug of the twin. Held by the build: no function a twin reaches, in any file, refers to
 * the door's hooks (`test/test_aes_event.py`, over the host build's own call graph).
 *
 * Tier 3 prices a door user on its own cycles, a twin's among them, against the ROM's with the ROM routine's — and a
 * second time net of both (`bench/tier3.py`, (V) at the door: ARRIVALS, and TWO COUNTS — the caller's own).
 */
#ifndef TOS102US_AES_EVDOOR_H
#define TOS102US_AES_EVDOOR_H

#include <stdint.h>

#include "addrs.h"
#include "machine.h"
#include "transcribed.h"
#include "aes/aes.h"
#include "aes/evsync.h"
#include "aes/evinput.h"
#include "aes/evwait.h"
#include "aes/evlib.h"
#include "aes/evmulti.h"

/* ---- what the entries are handed --------------------------------------------------------------------------------- */
/* ev_multi's FLAGS, the events it is asked for, a bit each (`btst #n,d7` over the flags word): */
#define EV_MU_KEYBD           0x0001     /* ($fe69cc btst #0,d7): a key                                         */
#define EV_MU_BUTTON          0x0002     /* ($fe69fa btst #1,d7)                                               */
#define EV_MU_M1              0x0004     /* ($fe6a72 btst #2,d7): the first mouse rectangle                    */
#define EV_MU_M2              0x0008     /* ($fe6a84 btst #3,d7): the second                                    */
#define EV_MU_MESAG           0x0010     /* ($fe6aae btst #4,d7): a message in the process's pipe               */
#define EV_MU_TIMER           0x0020     /* ($fe6a98 btst #5,d7): the timer run out                             */
/* ...its BUTTON parameter, one longword (`aes/aes.h`'s BUTTON_PARM_*): the clicks in the high word, the button mask
 * and the state wanted in the low word's two bytes ($fe6a18 move.l 22(a6) handed whole to the button test $fe5292). */
#define EV_BUTTON_PARAMETER(clicks, mask, state) \
    ((uint32_t)(clicks) << BUTTON_PARM_CLICKS_SHIFT | (uint32_t)(mask) << BUTTON_PARM_MASK_SHIFT | (uint32_t)(state))
#define EV_BUTTON_LEFT        1          /* the mask of the left button                                         */
#define EV_BUTTON_UP          0          /* the state: none of the mask's buttons down                         */
/* ...a MOUSE RECTANGLE (GEM's MOBLK): whether the event is the mouse leaving it (1) or entering it (0), then the
 * rectangle — five words, which ev_multi's test reads in place ($fe695c, through the pointer handed it). */
#define EV_MOBLK_WORDS        5
#define EV_MOBLK_LEAVE        0          /* word: 1 leaving, 0 entering                                        */
#define EV_MOBLK_RECT         2          /* bytes[GRECT_BYTES]                                                 */
/* ...and the ANSWERS it writes through its last pointer: the mouse, the buttons, the shift keys, the key, the clicks. */
#define EV_MULTI_ANSWER_WORDS 6
/* ev_button's ANSWERS, through its last pointer: the mouse, the buttons, the shift keys ($fe681a, four stores). */
#define EV_BUTTON_ANSWER_WORDS 4
/* ap_rdwr's CODE: a message written into the receiver's pipe (ap_sendmsg's `move.w #2`, $febe20). */
#define AP_RDWR_WRITE         2

/* ---- the entries' Alcyon frames: words and longs, in the order the ROM's callers push them ----------------------- */
/* ev_multi(flags, mouse rectangle 1, mouse rectangle 2, timer, button, message buffer, answers) — the flags a word,
 * the rest longwords ($fe69a0 move.w 8(a6); $fe69a4 movea.l 10(a6) .. $fe69ee movea.l 30(a6)). */
#define EVDOOR_EV_MULTI_FRAME_BYTES 26
/* ev_button(clicks, mask, state, answers): three words and a pointer ($fe68aa move.w 8(a6) .. $fe68d8 move.l 14(a6)). */
#define EVDOOR_EV_BUTTON_FRAME_BYTES 10
/* ap_rdwr(code, process id, length, buffer): three words and a pointer ($fe65c8: the words from 8(a6), the frame's
 * own address +10 handed on). */
#define EVDOOR_AP_RDWR_FRAME_BYTES  10
/* The scheduler's SEMAPHORE calls, each over one pointer to the semaphore (`aes/wmupdate.h`'s SPB): tak_flag takes
 * it, answering whether it got it ($fe4e62 movea.l 8(a6),a5); unsync gives it up, handing it to the first wait queued
 * on it ($fe4ec0). */
#define EVDOOR_TAK_FLAG_FRAME_BYTES 4
#define EVDOOR_UNSYNC_FRAME_BYTES   4
/* ev_block(code, parameter): a word, then a longword ($fe6878 move.l 10(a6); $fe687c move.w 8(a6)). */
#define EVDOOR_EV_BLOCK_FRAME_BYTES 6
/* ct_chgown(owner, rectangle): the PD the mouse and keyboard go to, and the control rectangle's address
 * ($fe49c4 move.l 8(a6); $fe49be move.l 12(a6)). */
#define EVDOOR_CT_CHGOWN_FRAME_BYTES 8
/* post_button(process, button, clicks): the PD a button event is posted to, the buttons' state and the clicks
 * ($fe52ee movea.l 8(a6); $fe5304 move.w 12(a6); $fe52ea move.w 14(a6)). */
#define EVDOOR_POST_BUTTON_FRAME_BYTES 8

#ifdef RECREATE_HOST_DIFFERENTIAL
/* The hook: `routine` arrived at over `image` with the Alcyon `frame`. Its answer is one of two: */
#define EVDOOR_REFUSED        0          /* the case binds no such call, or a twin is running (the core halts) */
#define EVDOOR_ARRIVED        1          /* noted, nothing run: the entry's twin runs next                     */
extern uint32_t (*recreate_call_event_door)(uint8_t *image, uint32_t routine, const uint8_t *frame,
                                            uint32_t frame_bytes);
/* ...and what the entry's twin answered, once it has returned (the word in `answer`; EVDOOR_NO_ANSWER from an
 * entry that answers nothing — which the case knows by the entry, not by this value). */
#define EVDOOR_NO_ANSWER      0
extern void (*recreate_event_door_returned)(uint8_t *image, uint32_t routine, uint32_t answer);

/* An entry's ARRIVAL: the frame noted by the case — nothing run. A refusal halts, and so does any answer that is not
 * ARRIVED (a callback that raised answers an undefined word). */
static inline void event_door_arrival(uint8_t *image, uint32_t routine, const uint8_t *frame, uint32_t frame_bytes)
{
    uint32_t verdict;

    verdict = recreate_call_event_door(image, routine, frame, frame_bytes);
    if (verdict == EVDOOR_REFUSED)
        recreate_not_reconstructed("the event door: the case's hook refused the call — an entry it does not bind, or "
                                   "a call made through a wrapper while a twin runs");
    if (verdict != EVDOOR_ARRIVED)
        recreate_not_reconstructed("the event door: the hook answered neither ARRIVED nor REFUSED — every entry is "
                                   "rebound, and its wrapper's twin runs only over an arrival the case noted");
}

/* ...and its twin's return: the answer shown to the case, and handed on. */
static inline uint16_t event_door_returned(uint8_t *image, uint32_t routine, uint16_t answer)
{
    recreate_event_door_returned(image, routine, answer);
    return answer;
}

/* A word or a longword of a frame being packed, at `at`: the next field's offset back. */
static inline uint32_t frame_word(uint8_t *frame, uint32_t at, uint16_t value)
{
    wr16(frame + at, value);
    return at + sizeof(uint16_t);
}

static inline uint32_t frame_long(uint8_t *frame, uint32_t at, uint32_t value)
{
    wr32(frame + at, value);
    return at + sizeof(uint32_t);
}
#endif

/* ---- the wrappers: the ONE call of each entry — A REBOUND ENTRY'S WRAPPER, SPELT ONCE -----------------------------
 * `EVDOOR_REBOUND(entry, ENTRY, (parameters), packed, arguments...)` IS the flip of an entry: it defines
 * `evdoor_<entry>` as the call of ITS OWN twin — `aes_<entry>(image, arguments...)`, the name built here from the
 * entry's, so a wrapper spelt rebound can call no other twin — on target that call and nothing else; off target the
 * Alcyon frame packed (`packed`: the `frame_word` / `frame_long` chain over `frame` — what it packs is compared,
 * field by field, with the frame the ROM's own call hands the entry), the ARRIVAL at the hook, the twin, and its
 * return reported. And it is what REBOUND is derived from, on both builds: off target the one translation unit that
 * defines the hooks (`src/aes/evdoor.c`) defines a MARKER per entry spelt through it (`evdoor_rebound_<entry>`, the
 * entry's ROM address), which is the set the case's hook answers ARRIVED for (`aes_event.rebound_in`); on target an
 * entry spelt through it has no `jsr` into the ROM left (`bench/tier3.py`).
 * `EVDOOR_REBOUND_VOID` is the same for an entry that answers nothing (post_button: D0 a callee's leftover no caller
 * reads) — the return is reported with no answer, and nothing is compared with the ROM routine's D0.
 *
 * THE TWIN IS CALLED, NEVER JUMPED TO (`EVDOOR_A_CALL_NOT_A_JUMP`, `transcribed.h`). The ROM's caller reaches the
 * entry by a Line-F call word and gets control back, whatever it does next; a wrapper that were `return aes_x(...)`
 * alone is, in a caller that returns the wrapper's answer (wm_update's `return evdoor_unsync(...)`, ap_sendmsg's
 * `return evdoor_ap_rdwr(...)`), a tail `jmp` into the twin — which then holds its caller's CALLER's return address,
 * for a row entered at that caller the run's sentinel: an arrival no watch can close (`aes_event.DoorStops`). */
#ifdef RECREATE_HOST_DIFFERENTIAL
#ifdef EVDOOR_DEFINES_THE_MARKERS
#define EVDOOR_REBOUND_MARKER(entry, ENTRY) const uint32_t evdoor_rebound_##entry = AES_ROM_##ENTRY;
#else
#define EVDOOR_REBOUND_MARKER(entry, ENTRY)
#endif
/* The frame packed and the arrival made: the statements both kinds of wrapper open with. */
#define EVDOOR_ARRIVING(ENTRY, PACKED)                                                                                \
    uint8_t frame[EVDOOR_##ENTRY##_FRAME_BYTES];                                                                      \
                                                                                                                      \
    (void)(PACKED);                                                                                                   \
    event_door_arrival(image, AES_ROM_##ENTRY, frame, sizeof frame)
#define EVDOOR_REBOUND(entry, ENTRY, PARAMETERS, PACKED, ...)                                                         \
    EVDOOR_REBOUND_MARKER(entry, ENTRY)                                                                               \
    static inline uint16_t evdoor_##entry PARAMETERS                                                                  \
    {                                                                                                                 \
        EVDOOR_ARRIVING(ENTRY, PACKED);                                                                               \
        return event_door_returned(image, AES_ROM_##ENTRY, aes_##entry(image, __VA_ARGS__));                          \
    }
#define EVDOOR_REBOUND_VOID(entry, ENTRY, PARAMETERS, PACKED, ...)                                                    \
    EVDOOR_REBOUND_MARKER(entry, ENTRY)                                                                               \
    static inline void evdoor_##entry PARAMETERS                                                                      \
    {                                                                                                                 \
        EVDOOR_ARRIVING(ENTRY, PACKED);                                                                               \
        aes_##entry(image, __VA_ARGS__);                                                                              \
        recreate_event_door_returned(image, AES_ROM_##ENTRY, EVDOOR_NO_ANSWER);                                       \
    }
#else
#define EVDOOR_REBOUND(entry, ENTRY, PARAMETERS, PACKED, ...)                                                         \
    static inline uint16_t evdoor_##entry PARAMETERS                                                                  \
    {                                                                                                                 \
        uint16_t answer = aes_##entry(image, __VA_ARGS__);                                                            \
                                                                                                                      \
        EVDOOR_A_CALL_NOT_A_JUMP;                                                                                     \
        return answer;                                                                                                \
    }
#define EVDOOR_REBOUND_VOID(entry, ENTRY, PARAMETERS, PACKED, ...)                                                    \
    static inline void evdoor_##entry PARAMETERS                                                                      \
    {                                                                                                                 \
        aes_##entry(image, __VA_ARGS__);                                                                              \
        EVDOOR_A_CALL_NOT_A_JUMP;                                                                                     \
    }
#endif

/* REBOUND: tak_flag is C (`aes/evsync.h`). */
EVDOOR_REBOUND(tak_flag, TAK_FLAG, (uint8_t *image, uint32_t semaphore),
               frame_long(frame, 0, semaphore),
               semaphore)

/* REBOUND: unsync is C (`aes/evwait.h`). The word it answers is nothing the ROM's routine sets and nothing a caller
 * reads; a release that hands the lock over reaches the dispatcher inside the twin. */
EVDOOR_REBOUND(unsync, UNSYNC, (uint8_t *image, uint32_t semaphore),
               frame_long(frame, 0, semaphore),
               semaphore)

/* REBOUND: ev_block is C (`aes/evlib.h`): a wait nothing satisfies reaches the dispatcher inside the twin. */
EVDOOR_REBOUND(ev_block, EV_BLOCK, (uint8_t *image, int16_t code, uint32_t parameter),
               frame_long(frame, frame_word(frame, 0, (uint16_t)code), parameter),
               code, parameter)

/* REBOUND: ap_rdwr is C (`aes/evlib.h`). */
EVDOOR_REBOUND(ap_rdwr, AP_RDWR, (uint8_t *image, int16_t code, int16_t process, int16_t length, uint32_t buffer),
               frame_long(frame, frame_word(frame, frame_word(frame, frame_word(frame, 0, (uint16_t)code),
                                                              (uint16_t)process), (uint16_t)length), buffer),
               code, process, length, buffer)

/* REBOUND: ev_button is C (`aes/evlib.h`). Its answer, the event's count, is nothing fm_button reads; answered all the
 * same, as every entry is. */
EVDOOR_REBOUND(ev_button, EV_BUTTON, (uint8_t *image, int16_t clicks, int16_t mask, int16_t state, uint32_t answers),
               frame_long(frame, frame_word(frame, frame_word(frame, frame_word(frame, 0, (uint16_t)clicks),
                                                              (uint16_t)mask), (uint16_t)state), answers),
               clicks, mask, state, answers)

/* REBOUND: ct_chgown is C (`aes/evinput.h`); the word it answers is always 0. */
EVDOOR_REBOUND(ct_chgown, CT_CHGOWN, (uint8_t *image, uint32_t owner, uint32_t rect),
               frame_long(frame, frame_long(frame, 0, owner), rect),
               owner, rect)

/* REBOUND: post_button is C (`aes/evinput.h`). The ROM's leaves D0 its EVB walk's end (`move.l a3,d0`, $fe5346):
 * nothing its caller reads, so nothing answered. */
EVDOOR_REBOUND_VOID(post_button, POST_BUTTON, (uint8_t *image, uint32_t process, int16_t button, int16_t clicks),
                    frame_word(frame, frame_word(frame, frame_long(frame, 0, process), (uint16_t)button),
                               (uint16_t)clicks),
                    process, button, clicks)

/* REBOUND: ev_multi is C (`aes/evmulti.h`): the keyboard poll and the fork queue run in C under every call. */
EVDOOR_REBOUND(ev_multi, EV_MULTI,
               (uint8_t *image, int16_t flags, uint32_t mouse1, uint32_t mouse2, uint32_t timer, uint32_t button,
                uint32_t message, uint32_t answers),
               frame_long(frame, frame_long(frame, frame_long(frame, frame_long(frame, frame_long(frame, frame_long(
                   frame, frame_word(frame, 0, (uint16_t)flags), mouse1), mouse2), timer), button), message), answers),
               flags, mouse1, mouse2, timer, button, message, answers)

#endif /* TOS102US_AES_EVDOOR_H */
