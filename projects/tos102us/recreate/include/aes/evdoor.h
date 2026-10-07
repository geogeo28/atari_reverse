/* aes/evdoor.h — THE EVENT DOOR: how the AES's C reaches the event layer and the scheduler (ev_multi, ap_rdwr, ...: the
 * dispatcher's layer), entry by entry — the ROM's own routine until the entry has a C twin, then the twin.
 *
 * WHAT A DOOR ENTRY IS. A ROM routine of that layer, keyed BY ITS ROM ADDRESS, entered over the Alcyon frame its ROM
 * callers push (`move.w`/`move.l -(sp)`, then a Line-F call word) and answering in D0. Every C call of one goes through
 * its wrapper below — `evdoor_<routine>`, the routine's arguments as the ROM's callers hand them — and nowhere else, so
 * the wrapper is the ONE place a port changes: when an entry has a C twin its wrapper's body becomes the call of the
 * twin (`aes_tak_flag(image, ...)`), on both builds, and no caller is touched. An entry is then REBOUND. Until it is:
 *
 * ON TARGET the wrapper is the ROM's call itself: the frame pushed as its callers push it, and a `jsr` to the routine —
 * so the shipped C runs the ROM's own event layer, from the same bytes the ROM's callers reach. The Line-F word's handler
 * is skipped (a `jsr` lands where the call table names: `test_aes_event.py` holds each entry to its callers' call word).
 * An Alcyon routine keeps D3-D7/A3-A6 (its Line-F return restores what its own mask names) and may change D0-D2/A0-A2
 * (the Line-F handler itself loads D1, D2 and A0 on every call the routine makes): all six are given up, GCC's D2 and A2
 * among them — the trap-glue lesson (`docs/on-target-execution.md`).
 *
 * OFF TARGET the wrapper packs the same frame into bytes and hands it to `recreate_call_event_door`, a hook the case
 * binds (`test/aes_event.py`), which runs the ROM's routine in a NESTED ORACLE RUN over the candidate's own image, lays
 * its writes back and answers its D0 (EVDOOR_SERVED) — so both shores run the ROM's event layer over the same machine,
 * and the differential is about the C round it. Frame locals whose ADDRESS a caller hands the door (an MOBLK, the answer
 * words) take `host_slot.h` slots, as every escaping local does. Before the hook, the door CHECKS the hop the ROM's call
 * word takes — vector $2c at the Line-F handler's RAM copy, the copy naming the ROM call table — and halts by name if a
 * case moved either: the ROM's caller would then run other code, and the door's would not. A hook that refuses (an entry
 * it does not serve; a nested run that reached the dispatcher — the call would BLOCK, nothing it waits for satisfied, and
 * the machine would switch away until something is, or YIELD — or ran past its cap) halts the core by name too, never
 * answered with a fabricated 0 or the "no event" the dispatcher's guard would let a blocked wait return.
 *
 * A REBOUND ENTRY IS STILL AN ARRIVAL, off target. Its wrapper packs the frame and asks the hook all the same, which
 * answers EVDOOR_ARRIVED — "noted: run the twin": the case has recorded the frame (what each call is handed is compared
 * with the ROM's own call's, which sees a wrong rectangle the image cannot) and laid the interrupt due at that call, as
 * at any door call. The twin then runs, and its answer is handed to `recreate_event_door_returned` — where a case may
 * hold the twin, at its own call, to the ROM routine's nested run over the image it arrived with (the SHADOW,
 * `test/aes_event.py`). Which answer an entry gets is the HOOK's, read off the build (the entries whose wrapper is
 * spelt through EVDOOR_REBOUND, below: each leaves a marker in the library): a wrapper and the hook that disagree
 * halt by name. A hook call made WHILE A TWIN RUNS is refused by name too (the next paragraph's rule, at run time).
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
 * Tier 3 prices a door user on its own cycles: a ROM routine its `jsr` enters runs on both sides and is taken off both;
 * a twin's cycles are ours, against the ROM routine's (`bench/tier3.py`, mechanism (EV)).
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
#include "ram_vector.h"

/* The hook: `routine` reached over `image` with the Alcyon `frame`. Its answer is one of three: */
#define EVDOOR_REFUSED        0          /* the case serves no such call (the core halts by name)              */
#define EVDOOR_SERVED         1          /* the ROM's routine was run over the image, its D0 in `*answer`      */
#define EVDOOR_ARRIVED        2          /* noted, nothing run: the entry is rebound, its twin runs next       */
extern uint32_t (*recreate_call_event_door)(uint8_t *image, uint32_t routine, const uint8_t *frame, uint32_t frame_bytes,
                                            uint32_t *answer);
/* ...and what a rebound entry's twin answered, once it has returned (the word in `answer`; EVDOOR_NO_ANSWER from an
 * entry that answers nothing — which the case knows by the entry, not by this value). */
#define EVDOOR_NO_ANSWER      0
extern void (*recreate_event_door_returned)(uint8_t *image, uint32_t routine, uint32_t answer);

/* The hook asked: the hop the ROM's call word takes checked first; a refusal halts. `*answer` is a served call's. */
static inline uint32_t event_door_asked(uint8_t *image, uint32_t routine, const uint8_t *frame, uint32_t frame_bytes,
                                        uint32_t *answer)
{
    uint32_t verdict;

    require_cpu_routine(image, VECTOR_LINE_F, AES_LINEF_COPY,
                        "the event door: vector $2c no longer the Line-F handler's RAM copy — the ROM's call word would "
                        "run other code");
    require_cpu_routine(image, AES_LINEF_COPY + LINEF_TABLE_OPERAND, AES_LINEF_TABLE,
                        "the event door: the Line-F handler's copy no longer names the ROM call table");
    verdict = recreate_call_event_door(image, routine, frame, frame_bytes, answer);
    if (verdict == EVDOOR_REFUSED)
        recreate_not_reconstructed("the event door: the case's hook refused the call — an entry it does not serve, a "
                                   "call that would block (nothing it waits for satisfied) or yield, or a nested run "
                                   "past its cap");
    return verdict;
}

/* An entry the ROM still serves: its nested run's D0. */
static inline uint32_t event_door(uint8_t *image, uint32_t routine, const uint8_t *frame, uint32_t frame_bytes)
{
    uint32_t answer = 0;

    if (event_door_asked(image, routine, frame, frame_bytes, &answer) != EVDOOR_SERVED)
        recreate_not_reconstructed("the event door: the hook left this entry to a twin, and its wrapper calls none — "
                                   "an entry whose twin the library exports, its wrapper left on the nested run");
    return answer;
}

/* A REBOUND entry's arrival: the frame noted by the case, nothing run. */
static inline void event_door_arrival(uint8_t *image, uint32_t routine, const uint8_t *frame, uint32_t frame_bytes)
{
    uint32_t unanswered = 0;

    if (event_door_asked(image, routine, frame, frame_bytes, &unanswered) != EVDOOR_ARRIVED)
        recreate_not_reconstructed("the event door: the hook served a rebound entry by the ROM's nested run — its "
                                   "wrapper's twin would run over the routine's own writes");
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

/* ---- the wrappers: the ONE call of each entry ---------------------------------------------------------------------
 * First the entry the ROM still serves (ev_multi, the last one), then the rebound ones.
 * On target the values are pushed from REGISTERS or immediates ("ri" — a stack operand would move under the pushes),
 * and the ones that can travel in the scratch the routine destroys anyway — D0, D1, A0, A1 — are put there as in-out
 * operands, so the call holds no callee-saved register but the D2/A2 GCC must keep round it. */
#ifndef RECREATE_HOST_DIFFERENTIAL
/* A call no wrapper below has a priced shape for: an error at compile time, never target code nothing measures. */
extern void evdoor_shape_unbuilt(void) __attribute__((error("the event door: a call shape with no priced Tier 3 row")));
#endif

static inline uint16_t evdoor_ev_multi(uint8_t *image, int16_t flags, uint32_t mouse1, uint32_t mouse2, uint32_t timer,
                                       uint32_t button, uint32_t message, uint32_t answers)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    uint8_t frame[EVDOOR_EV_MULTI_FRAME_BYTES];
    uint32_t at = frame_word(frame, 0, (uint16_t)flags);

    at = frame_long(frame, at, mouse1);
    at = frame_long(frame, at, mouse2);
    at = frame_long(frame, at, timer);
    at = frame_long(frame, at, button);
    at = frame_long(frame, at, message);
    frame_long(frame, at, answers);
    return (uint16_t)event_door(image, AES_ROM_EV_MULTI, frame, sizeof frame);
#else
    register uint32_t answer __asm__("d0") = answers;       /* in: the answers' address; out: the events */
    register uint32_t rise __asm__("d1") = button;
    register uint32_t first __asm__("a0") = mouse1;
    register uint32_t second __asm__("a1") = mouse2;

    (void)image;
    /* THE TWO SHAPES BUILT, both waiting for nothing timed or sent: ONE rectangle (gr_stilldn's) and TWO (mn_do's);
     * fm_do's, with no rectangle, is the first with its zero first rectangle pushed from A0 as the value it is. A
     * caller handing a timer or a message is a new shape: added with its own priced row, refused until. */
    if (!(__builtin_constant_p(timer | message) && !(timer | message)))
        evdoor_shape_unbuilt();
    /* The frame pushed last longword first — answers, message, button, timer, mouse 2, mouse 1, flags — the call, the
     * frame dropped. One rectangle: the zero second rectangle, timer and message pushed from the A1 the absent second
     * rectangle holds (a register push is 12 cycles, an immediate's 20). Two: the zero timer and message by `clr.l`, as
     * mn_do's own call pushes them ($fe8e6c, $fe8e72). */
/* The one call, ZERO_PUSH the instruction that pushes the zero timer and message: an asm template is a string literal,
 * so the two shapes share their operands, clobbers, call and frame drop by this macro and differ by that string. */
#define EVDOOR_EV_MULTI_CALL(ZERO_PUSH)                                                                                 \
    __asm__ volatile ("move.l %0,-(%%sp)\n\t"                                                                           \
                      ZERO_PUSH "\n\t"                                                                                  \
                      "move.l %1,-(%%sp)\n\t"                                                                           \
                      ZERO_PUSH "\n\t"                                                                                  \
                      "move.l %3,-(%%sp)\n\t"                                                                           \
                      "move.l %2,-(%%sp)\n\t"                                                                           \
                      "move.w %4,-(%%sp)\n\t"                                                                           \
                      "jsr %c5\n\t"                                                                                     \
                      "lea %c6(%%sp),%%sp"                                                                              \
                      : "+d"(answer), "+d"(rise), "+a"(first), "+a"(second)                                             \
                      : "ri"(flags), "i"(AES_ROM_EV_MULTI), "i"(EVDOOR_EV_MULTI_FRAME_BYTES)                            \
                      : "d2", "a2", "memory", "cc")
    if (__builtin_constant_p(mouse2) && !mouse2)
        EVDOOR_EV_MULTI_CALL("move.l %3,-(%%sp)");
    else
        EVDOOR_EV_MULTI_CALL("clr.l -(%%sp)");
#undef EVDOOR_EV_MULTI_CALL
    return (uint16_t)answer;
#endif
}

/* ---- A REBOUND ENTRY'S WRAPPER, SPELT ONCE ------------------------------------------------------------------------
 * `EVDOOR_REBOUND(entry, ENTRY, (parameters), packed, arguments...)` IS the flip of an entry: it defines
 * `evdoor_<entry>` as the call of ITS OWN twin — `aes_<entry>(image, arguments...)`, the name built here from the
 * entry's, so a wrapper spelt rebound can call no other twin — on target that call and nothing else; off target the
 * Alcyon frame packed (`packed`: the `frame_word` / `frame_long` chain over `frame` — what it packs is compared,
 * field by field, with the frame the ROM's own call hands the entry), the ARRIVAL at the hook, the twin, and its
 * return reported. And it is what REBOUND is derived from, on both builds: off target the one translation unit that
 * defines the hooks (`src/aes/evdoor.c`) defines a MARKER per entry spelt through it (`evdoor_rebound_<entry>`, the
 * entry's ROM address), which is the set the case's hook answers ARRIVED for (`aes_event.rebound_in`); on target an
 * entry spelt through it has no `jsr` into the ROM left (`bench/tier3.py`). So a twin that merely EXISTS — exported,
 * its wrapper still the ROM's call — is rebound nowhere: it is a C core like any other until its wrapper is re-spelt.
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

#endif /* TOS102US_AES_EVDOOR_H */
