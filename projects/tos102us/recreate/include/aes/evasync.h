/* aes/evasync.h — THE EVENT BLOCKS' LISTS (`src/aes/evasync.c`, gemasync and geminput's evremove): an event posted to
 * its process (signal), an EVB made complete (azombie), taken from the free list (get_evb), put on a wait list
 * (evinsert), taken off one and freed (takeoff), taken off one with its answer and completed (evremove); and the two
 * ends of a wait for the running process: its completed EVB of one event freed and answered (apret), every EVB of a
 * set of events it no longer waits for cancelled (acancel).
 *
 * ALCYON C, every routine entered by a Line-F call over its caller's frame (an EVB or a list a LONGWORD, an event mask
 * or an answer a WORD). get_evb answers a POINTER (D0 whole), apret and acancel a WORD; the rest leave a callee's D0,
 * which no caller reads.
 *
 * AN EVB IS ON UP TO TWO LISTS AT ONCE, by two different links:
 *   - its PROCESS's (PD_EVLIST) or the free list (AES_EUL), singly linked through EVB_NEXT — the first longword, so
 *     the list's head (a PD field, a global) is walked as the EVB before the first: "the link at";
 *   - a WAIT list or the completed list, doubly linked through EVB_LINK and EVB_PRED. A wait list's head is one
 *     longword — a CDA's keyboard, mouse or button wait, a PD's pipe ends, a semaphore's waiters, the delay list — and
 *     the first EVB's EVB_PRED points at the head AS IF IT WERE AN EVB: the head's address less AES_ELINKOFF, so that
 *     `pred->link = …` stores into the head itself. Taking an EVB off needs no list: `leave_list` in the source.
 * The delay list (iasync's adelay) is a DELTA list: each EVB's EVB_PARM is the ticks after its predecessor's, which is
 * why takeoff hands a cancelled delay's ticks to the one after it.
 */
#ifndef TOS102US_AES_EVASYNC_H
#define TOS102US_AES_EVASYNC_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#include "aes/aes.h"

/* ---- the lists' globals --------------------------------------------------------------------------------------------
 * The list of COMPLETED EVBs is `aes/aes.h`'s AES_ZOMBIE_LIST ($c84a); the delays wait on another. */
/* The DELAY list (adelay's, $fe55a8): the EVBs waiting for a timer, each holding the ticks after the one before it —
 * and the milliseconds a tick is, which ev_multi and ev_timer divide a timer by ($fe6b6c, $fe693a).
 * NO C READS EITHER YET, nor EVB_FLAG_LEAVE below: each is a word a ROM instruction was found reading (cited), named
 * here for the lists' battery, which reads the delay list out of an image by them (`test/aes_evasync.py`); their C
 * readers are adelay and tchange, amouse, ev_multi and ev_timer — band 4's later waves. */
#define AES_DELAY_LIST        0x9c1a     /* long                                ($fe55b4 movea.l $9c1a,a4)     */
#define AES_GL_TICK_MS        0xc91a     /* word: 20                            ($fe6b6c move.w $c91a,d0)      */
/* The offset of EVB_LINK in an EVB, kept in RAM (gem_main stores 4, $fda094) and subtracted from a list head's address
 * to make the head's stand-in predecessor. */
#define AES_ELINKOFF          0x97f6     /* long                                ($fe3fe6 sub.l $97f6,d0)       */
/* The waits pending for MORE than one click (a `ctx` name, GEM's gl_bpend): abutton counts one in ($fe5648), b_click
 * opens the click delay only while it is set ($fe4f72), and evremove counts one out — see its body for which. */
#define AES_GL_BPEND          0xc84e     /* word                                ($fe5150 subq.w #1)            */
/* The high word of the last answer apret took: for a button wait the buttons' state, which ev_rets hands back as the
 * event's ($fe6858) and ev_multi stores beside the clicks ($fe6bfa). */
#define AES_EV_BUTTON_STATE   0xc792     /* word                                ($fe426e move.w d0,$c792)      */

/* ---- EVB_FLAG's bits ----------------------------------------------------------------------------------------------- */
#define EVB_FLAG_NOCANCEL     0x0001     /* being served: acancel keeps it      ($fe42a2 btst #0; set $fe5a14) */
#define EVB_FLAG_COMPLETE     0x0002     /* its event came: azombie's whole word ($fe3ff6 move.w #2)           */
#define EVB_FLAG_DELAY        0x0004     /* on the delay list                   ($fe4088 btst #2; set $fe55a2) */
#define EVB_FLAG_LEAVE        0x0008     /* a mouse wait for its rectangle LEFT ($fe56ac ori.w #8; no C reads it) */

/* ---- apret's answers when the running process has no such EVB ------------------------------------------------------ */
#define APRET_NO_EVB          100        /* none of that event on its list      ($fe41ea moveq #100)           */
#define APRET_NOT_COMPLETE    101        /* ...or one that is not completed     ($fe4208 moveq #101)           */

/* ---- evremove: a button wait's clicks, in its parameter ------------------------------------------------------------- */
#define EVB_PARM_CLICKS_SHIFT 16         /* ($fe512c asr.l d1 of 16)                                           */
#define EVB_PARM_CLICKS_MASK  0xff       /* ($fe5134 andi.l #255)                                              */
#define ONE_CLICK             1          /* more than this is a multi-click wait ($fe513e cmpi.w #1)           */
#define EVB_RETURN_HIGH_SHIFT 16         /* ($fe426c asr.l d1 of 16)                                           */

#ifndef __ASSEMBLER__
#include "m68k_idioms.h"

/* A process at the HEAD of the woken list (AES_DRL), where the dispatcher's next pass finds it: signal's wake of a
 * parked one ($fe3fac) and pstart's of a new one ($fe58b0) — the PD's link stored first, then the list's head.
 * A MACRO, measured: as an inline function GCC swaps the operands of one compare in aes_signal's walk (`cmpa.l d1,a1`
 * for `cmp.l a1,d1`: the same cycles, not the same bytes), and signal's object is held byte-identical.
 * IT EVALUATES BOTH ARGUMENTS TWICE: hand it LOCALS — a call (`aes_getpd(image)`) would be made twice and hand out
 * two PDs, and a field read (`bus_long(image, x)`) would be read again after the first store, which may be over it. */
#define onto_the_woken_list(image, pd) \
    (set_bus_long((image), (pd) + PD_LINK, be32((image) + AES_DRL)), wr32((image) + AES_DRL, (pd)))

void aes_signal(uint8_t *image, uint32_t evb);                                                       /* $fe3f5e */
void aes_azombie(uint8_t *image, uint32_t evb);                                                      /* $fe3fba */
uint32_t aes_get_evb(uint8_t *image);                                                                /* $fe4002 */
void aes_evinsert(uint8_t *image, uint32_t evb, uint32_t list);                                      /* $fe4030 */
void aes_takeoff(uint8_t *image, uint32_t evb);                                                      /* $fe4062 */
int16_t aes_apret(uint8_t *image, int16_t mask);                                                     /* $fe41bc */
int16_t aes_acancel(uint8_t *image, int16_t mask);                                                   /* $fe427a */
void aes_evremove(uint8_t *image, uint32_t evb, int16_t answer);                                     /* $fe511a */
#endif

#endif /* TOS102US_AES_EVASYNC_H */
