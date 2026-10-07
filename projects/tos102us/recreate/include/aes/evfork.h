/* aes/evfork.h — THE FORK QUEUE and what runs off it (`src/aes/evfork.c`, gemdisp's forkq, forker and chkkbd, and
 * geminput's four FORK FUNCTIONS): what an interrupt cannot do itself — post an event to a process's waits — it
 * QUEUES (forkq: a fork function and one longword of data), and the dispatcher runs the queue between processes
 * (forker), under `rlr` = -1. The keyboard is not an interrupt of the AES's: chkkbd POLLS it through the VDI.
 *
 *   forkq(code, data)     {code, data} at the queue's tail; the 33rd DROPPED            ($fe4b1a, Line-F and `jsr`)
 *   forker()              every queued entry taken, recorded while appl_trecord runs, and CALLED   ($fe4bc6)
 *   chkkbd()              the shift keys (VDI 128) and, while the keyboard's owner's queue has room, one key (VDI
 *                         33, 31): a key or changed shift keys → forkq(kchange)           ($fe4cd6)
 *   kchange(key, shift)   the shift keys noted; a key posted to the keyboard's owner      ($fe5180)
 *   bchange(new, clicks)  a first press re-decides whose the mouse is; the click record; post_button   ($fe51d8)
 *   mchange(x, y)         where the mouse is (VDI 124); a move ends an open click count; over the bar the mouse goes
 *                         to the screen manager; post_mouse                                ($fe534c)
 *   tchange(elapsed)      the delay list counted down, every delay run out completed; the tick re-armed   ($fe4e02)
 *
 * A FORK FUNCTION'S ONE LONGWORD is its Alcyon frame: forker pushes it and `jsr`s the entry's code
 * (`staged_call.h`, THE FORK HOOK), and each function reads it as its own arguments — two words (kchange, bchange,
 * mchange) or one long (tchange).
 *
 * THE CODE A QUEUE ENTRY HOLDS is a CODE ADDRESS in compared RAM: the fork function's ROM address off target (what
 * the ROM's own interrupts queue: the image equal byte for byte), the function's own entry on target — fork_<fn>()
 * below, the one spelling of both (`staged_call.h`'s ALCYON_ROUTINE). forker's recorder compares against the same.
 */
#ifndef TOS102US_AES_EVFORK_H
#define TOS102US_AES_EVFORK_H

#ifndef __ASSEMBLER__
#include <stdint.h>

#include "staged_call.h"
#endif
#include "addrs.h"

/* ---- appl_trecord's recorder, inside forker ($fe4c1e..$fe4cb2) -------------------------------------------------------
 * The key that ENDS a recording, as kchange's data holds it in its high word: Control-\ (scan code $2b, ASCII $1c). */
#define RECORD_END_KEY        0x2b1c     /* ($fe4c3c cmp.l #$2b1c0000 of the data's high word)                 */
#define RECORD_KEY_MASK       0xffff0000 /* ($fe4c36 and.l #$ffff0000): the data's high word (HIGH_WORD_SHIFT)   */

/* ---- chkkbd's and mchange's VDI calls: the input device and mode vsin_mode (33) is handed -------------------------- */
#define VSIN_STRING_DEVICE    4          /* the keyboard                        ($fe4d0c move.w #4,(a5))        */
#define VSIN_LOCATOR_DEVICE   1          /* the mouse                           ($fe53de move.w #1,$95ba)       */
#define VSIN_SAMPLE_MODE      2          /* answer at once, do not wait         ($fe4d10, $fe53e6 move.w #2)    */
#define VSIN_MODE_WORDS       2          /* its intin words                     ($fe4d16, $fe53ee move.w #2,(sp)) */
#define VSM_STRING_NO_ECHO    (-1)       /* vsm_string's length: one key, no echo ($fe4d24 move.w #-1,(a5))     */
#define VSM_STRING_WORDS      2          /* its intin words                     ($fe4d2c move.w #2,(sp))        */
#define VSM_LOCATOR_POINTS    1          /* vsm_locator's one point             ($fe5412 move.l #$1c0001)       */
/* ...and the distance, in pixels either way, the mouse may move inside an open click count without ending it. */
#define CLICK_SLOP            2          /* ($fe5388 cmp.w #2; $fe5398 cmp.w #-2)                               */
/* While appl_tplay plays a recording back (GEM's gl_play), mchange MOVES the mouse to the recorded point. Set by
 * ap_tplay alone ($fe6646). */
#define AES_GL_PLAY           0x9800     /* word                                ($fe53d6 tst.w $9800)           */
/* bchange's first press: the left button alone, down ($fe51ea cmpi.w #1,8(a6)). */
#define BCHANGE_FIRST_PRESS   1

#ifndef __ASSEMBLER__
void aes_forkq(uint8_t *image, uint32_t code, uint32_t data);                                         /* $fe4b1a */
void aes_forker(uint8_t *image);                                                                      /* $fe4bc6 */
void aes_chkkbd(uint8_t *image);                                                                      /* $fe4cd6 */
void aes_kchange(uint8_t *image, int16_t key, int16_t shift_keys);                                    /* $fe5180 */
void aes_bchange(uint8_t *image, int16_t buttons, int16_t clicks);                                    /* $fe51d8 */
void aes_mchange(uint8_t *image, int16_t x, int16_t y);                                               /* $fe534c */
void aes_tchange(uint8_t *image, uint32_t elapsed);                                                   /* $fe4e02 */
void aes_drawrat(uint8_t *image, int16_t x, int16_t y);                                               /* $fed412 */

#ifndef RECREATE_HOST_DIFFERENTIAL
/* THE FORK FUNCTIONS' ENTRIES on target: what a queue entry's code is, entered by forker's `jsr (a0)` over the one
 * longword it pushed — which is the m68k C call of one `uint32_t`, so each is plain C (`src/aes/evfork.c`). */
void aes_kchange_fork(uint32_t data);
void aes_bchange_fork(uint32_t data);
void aes_mchange_fork(uint32_t data);
void aes_tchange_fork(uint32_t data);
#endif

/* A fork function's CODE, as a queue entry holds it and forker's recorder compares it. */
static inline uint32_t fork_kchange(void)
{
    return ALCYON_ROUTINE(AES_ROM_KCHANGE, aes_kchange_fork);
}

static inline uint32_t fork_bchange(void)
{
    return ALCYON_ROUTINE(AES_ROM_BCHANGE, aes_bchange_fork);
}

static inline uint32_t fork_tchange(void)
{
    return ALCYON_ROUTINE(AES_ROM_TCHANGE, aes_tchange_fork);
}
#endif

#endif /* TOS102US_AES_EVFORK_H */
