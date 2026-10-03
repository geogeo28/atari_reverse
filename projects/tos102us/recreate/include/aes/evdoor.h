/* aes/evdoor.h — THE EVENT DOOR: how the AES's C reaches the event layer and the scheduler, which no C of this
 * reconstruction holds yet (ev_multi, ap_rdwr, ...: the dispatcher's layer).
 *
 * WHAT A DOOR ENTRY IS. A ROM routine of that layer, keyed BY ITS ROM ADDRESS, entered over the Alcyon frame its ROM
 * callers push (`move.w`/`move.l -(sp)`, then a Line-F call word) and answering in D0. Every C call of one goes through
 * its wrapper below — `evdoor_<routine>`, the routine's arguments as the ROM's callers hand them — and nowhere else, so
 * the wrapper is the ONE place a later port changes: when the event layer has C twins, each wrapper's body becomes the
 * call of its twin (`aes_ev_multi(image, ...)`), on both builds, and no caller is touched. Until then:
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
 * its writes back and answers its D0 — so both shores run the ROM's event layer over the same machine, and the
 * differential is about the C round it. Frame locals whose ADDRESS a caller hands the door (an MOBLK, the answer words)
 * take `host_slot.h` slots, as every escaping local does. Before the hook, the door CHECKS the hop the ROM's call word
 * takes — vector $2c at the Line-F handler's RAM copy, the copy naming the ROM call table — and halts by name if a case
 * moved either: the ROM's caller would then run other code, and the door's would not. A hook that refuses (an entry it
 * does not serve; a nested run that reached the dispatcher — the call would BLOCK, nothing it waits for satisfied, and
 * the machine would switch away until something is, or YIELD — or ran past its cap) halts the core by name too, never
 * answered with a fabricated 0 or the "no event" the dispatcher's guard would let a blocked wait return.
 *
 * Tier 3 prices a door user on its own cycles: the ROM routine its `jsr` enters runs on both sides and is taken off both
 * (`bench/tier3.py`, mechanism (EV)).
 */
#ifndef TOS102US_AES_EVDOOR_H
#define TOS102US_AES_EVDOOR_H

#include <stdint.h>

#include "addrs.h"
#include "machine.h"
#include "aes/aes.h"

/* ---- what the entries are handed --------------------------------------------------------------------------------- */
/* ev_multi's FLAGS, the events it is asked for, a bit each (`btst #n,d7` over the flags word): */
#define EV_MU_BUTTON          0x0002     /* ($fe69fa btst #1,d7)                                               */
#define EV_MU_M1              0x0004     /* ($fe6a72 btst #2,d7): the first mouse rectangle                    */
#define EV_MU_M2              0x0008     /* ($fe6a84 btst #3,d7): the second                                    */
/* ...its BUTTON parameter, one longword: the clicks in the high word, the button mask and the state wanted in the low
 * word's two bytes ($fe6a18 move.l 22(a6) handed whole to the button test $fe5292). */
#define EV_BUTTON_CLICKS_SHIFT 16
#define EV_BUTTON_MASK_SHIFT  8
#define EV_BUTTON_PARAMETER(clicks, mask, state) \
    ((uint32_t)(clicks) << EV_BUTTON_CLICKS_SHIFT | (uint32_t)(mask) << EV_BUTTON_MASK_SHIFT | (uint32_t)(state))
#define EV_BUTTON_LEFT        1          /* the mask of the left button                                         */
#define EV_BUTTON_UP          0          /* the state: none of the mask's buttons down                         */
/* ...a MOUSE RECTANGLE (GEM's MOBLK): whether the event is the mouse leaving it (1) or entering it (0), then the
 * rectangle — five words, which ev_multi's test reads in place ($fe695c, through the pointer handed it). */
#define EV_MOBLK_WORDS        5
#define EV_MOBLK_LEAVE        0          /* word: 1 leaving, 0 entering                                        */
#define EV_MOBLK_RECT         2          /* bytes[GRECT_BYTES]                                                 */
/* ...and the ANSWERS it writes through its last pointer: the mouse, the buttons, the shift keys, the key, the clicks. */
#define EV_MULTI_ANSWER_WORDS 6
/* ap_rdwr's CODE: a message written into the receiver's pipe (ap_sendmsg's `move.w #2`, $febe20). */
#define AP_RDWR_WRITE         2

/* ---- the entries' Alcyon frames: words and longs, in the order the ROM's callers push them ----------------------- */
/* ev_multi(flags, mouse rectangle 1, mouse rectangle 2, timer, button, message buffer, answers) — the flags a word,
 * the rest longwords ($fe69a0 move.w 8(a6); $fe69a4 movea.l 10(a6) .. $fe69ee movea.l 30(a6)). */
#define EVDOOR_EV_MULTI_FRAME_BYTES 26
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

/* The hook: `routine` run over `image` with the Alcyon `frame`; nonzero once served, its D0 in `*answer`. */
extern uint32_t (*recreate_call_event_door)(uint8_t *image, uint32_t routine, const uint8_t *frame, uint32_t frame_bytes,
                                            uint32_t *answer);

static inline uint32_t event_door(uint8_t *image, uint32_t routine, const uint8_t *frame, uint32_t frame_bytes)
{
    uint32_t answer = 0;

    require_cpu_routine(image, VECTOR_LINE_F, AES_LINEF_COPY,
                        "the event door: vector $2c no longer the Line-F handler's RAM copy — the ROM's call word would "
                        "run other code");
    require_cpu_routine(image, AES_LINEF_COPY + LINEF_TABLE_OPERAND, AES_LINEF_TABLE,
                        "the event door: the Line-F handler's copy no longer names the ROM call table");
    if (!recreate_call_event_door(image, routine, frame, frame_bytes, &answer))
        recreate_not_reconstructed("the event door: the case's hook refused the call — an entry it does not serve, a "
                                   "call that would block (nothing it waits for satisfied) or yield, or a nested run "
                                   "past its cap");
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
    /* THE TWO SHAPES BUILT, both waiting for nothing timed or sent: ONE rectangle (gr_stilldn's) and TWO (mn_do's). A
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

static inline uint16_t evdoor_ap_rdwr(uint8_t *image, int16_t code, int16_t process, int16_t length, uint32_t buffer)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    uint8_t frame[EVDOOR_AP_RDWR_FRAME_BYTES];
    uint32_t at = frame_word(frame, 0, (uint16_t)code);

    at = frame_word(frame, at, (uint16_t)process);
    at = frame_word(frame, at, (uint16_t)length);
    frame_long(frame, at, buffer);
    return (uint16_t)event_door(image, AES_ROM_AP_RDWR, frame, sizeof frame);
#else
    register uint32_t answer __asm__("d0") = (uint16_t)process;   /* in: the process id; out: the answer */
    register uint32_t length_word __asm__("d1") = (uint16_t)length;
    register uint32_t address __asm__("a0") = buffer;
    register uint32_t scratch __asm__("a1");

    (void)image;
    __asm__ volatile ("move.l %2,-(%%sp)\n\t"
                      "move.w %1,-(%%sp)\n\t"
                      "move.w %0,-(%%sp)\n\t"
                      "move.w %4,-(%%sp)\n\t"
                      "jsr %c5\n\t"
                      "lea %c6(%%sp),%%sp"
                      : "+d"(answer), "+d"(length_word), "+a"(address), "=a"(scratch)
                      : "ri"(code), "i"(AES_ROM_AP_RDWR), "i"(EVDOOR_AP_RDWR_FRAME_BYTES)
                      : "d2", "a2", "memory", "cc");
    return (uint16_t)answer;
#endif
}

#ifndef RECREATE_HOST_DIFFERENTIAL
/* The call of an entry over ONE longword (ROUTINE an address constant, FRAME_BYTES its frame's): pushed from the A0
 * it is handed in, the frame dropped by `addq`. A macro, as an "i" operand must be a constant where it is spelt. */
#define EVDOOR_CALL_LONG(ROUTINE, FRAME_BYTES, argument) __extension__({                                            \
    register uint32_t answer_ __asm__("d0");                                                                         \
    register uint32_t scratch_ __asm__("d1");                                                                        \
    register uint32_t pointer_ __asm__("a0") = (argument);                                                           \
    register uint32_t other_ __asm__("a1");                                                                          \
    __asm__ volatile ("move.l %2,-(%%sp)\n\t"                                                                        \
                      "jsr %c4\n\t"                                                                                  \
                      "addq.l %5,%%sp"                                                                               \
                      : "=d"(answer_), "=d"(scratch_), "+a"(pointer_), "=a"(other_)                                  \
                      : "i"(ROUTINE), "i"(FRAME_BYTES)                                                               \
                      : "d2", "a2", "memory", "cc");                                                                 \
    (uint16_t)answer_; })
#endif

static inline uint16_t evdoor_tak_flag(uint8_t *image, uint32_t semaphore)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    uint8_t frame[EVDOOR_TAK_FLAG_FRAME_BYTES];

    frame_long(frame, 0, semaphore);
    return (uint16_t)event_door(image, AES_ROM_TAK_FLAG, frame, sizeof frame);
#else
    (void)image;
    return EVDOOR_CALL_LONG(AES_ROM_TAK_FLAG, EVDOOR_TAK_FLAG_FRAME_BYTES, semaphore);
#endif
}

static inline uint16_t evdoor_unsync(uint8_t *image, uint32_t semaphore)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    uint8_t frame[EVDOOR_UNSYNC_FRAME_BYTES];

    frame_long(frame, 0, semaphore);
    return (uint16_t)event_door(image, AES_ROM_UNSYNC, frame, sizeof frame);
#else
    (void)image;
    return EVDOOR_CALL_LONG(AES_ROM_UNSYNC, EVDOOR_UNSYNC_FRAME_BYTES, semaphore);
#endif
}

static inline uint16_t evdoor_ev_block(uint8_t *image, int16_t code, uint32_t parameter)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    uint8_t frame[EVDOOR_EV_BLOCK_FRAME_BYTES];

    frame_long(frame, frame_word(frame, 0, (uint16_t)code), parameter);
    return (uint16_t)event_door(image, AES_ROM_EV_BLOCK, frame, sizeof frame);
#else
    register uint32_t answer __asm__("d0");
    register uint32_t scratch __asm__("d1");
    register uint32_t value __asm__("a0") = parameter;
    register uint32_t other __asm__("a1");

    (void)image;
    __asm__ volatile ("move.l %2,-(%%sp)\n\t"
                      "move.w %4,-(%%sp)\n\t"
                      "jsr %c5\n\t"
                      "addq.l %6,%%sp"
                      : "=d"(answer), "=d"(scratch), "+a"(value), "=a"(other)
                      : "ri"(code), "i"(AES_ROM_EV_BLOCK), "i"(EVDOOR_EV_BLOCK_FRAME_BYTES)
                      : "d2", "a2", "memory", "cc");
    return (uint16_t)answer;
#endif
}

static inline uint16_t evdoor_ct_chgown(uint8_t *image, uint32_t owner, uint32_t rect)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    uint8_t frame[EVDOOR_CT_CHGOWN_FRAME_BYTES];

    frame_long(frame, frame_long(frame, 0, owner), rect);
    return (uint16_t)event_door(image, AES_ROM_CT_CHGOWN, frame, sizeof frame);
#else
    register uint32_t answer __asm__("d0");
    register uint32_t scratch __asm__("d1");
    register uint32_t pd __asm__("a0") = owner;
    register uint32_t area __asm__("a1") = rect;

    (void)image;
    __asm__ volatile ("move.l %3,-(%%sp)\n\t"
                      "move.l %2,-(%%sp)\n\t"
                      "jsr %c4\n\t"
                      "addq.l %5,%%sp"
                      : "=d"(answer), "=d"(scratch), "+a"(pd), "+a"(area)
                      : "i"(AES_ROM_CT_CHGOWN), "i"(EVDOOR_CT_CHGOWN_FRAME_BYTES)
                      : "d2", "a2", "memory", "cc");
    return (uint16_t)answer;
#endif
}

/* post_button leaves D0 its EVB walk's end (`move.l a3,d0`, $fe5346): nothing its caller reads, so nothing answered. */
static inline void evdoor_post_button(uint8_t *image, uint32_t process, int16_t button, int16_t clicks)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    uint8_t frame[EVDOOR_POST_BUTTON_FRAME_BYTES];

    frame_word(frame, frame_word(frame, frame_long(frame, 0, process), (uint16_t)button), (uint16_t)clicks);
    event_door(image, AES_ROM_POST_BUTTON, frame, sizeof frame);
#else
    register uint32_t answer __asm__("d0");
    register uint32_t scratch __asm__("d1");
    register uint32_t pd __asm__("a0") = process;
    register uint32_t other __asm__("a1");

    (void)image;
    __asm__ volatile ("move.w %5,-(%%sp)\n\t"
                      "move.w %4,-(%%sp)\n\t"
                      "move.l %2,-(%%sp)\n\t"
                      "jsr %c6\n\t"
                      "addq.l %7,%%sp"
                      : "=d"(answer), "=d"(scratch), "+a"(pd), "=a"(other)
                      : "ri"(button), "ri"(clicks), "i"(AES_ROM_POST_BUTTON), "i"(EVDOOR_POST_BUTTON_FRAME_BYTES)
                      : "d2", "a2", "memory", "cc");
#endif
}

#endif /* TOS102US_AES_EVDOOR_H */
