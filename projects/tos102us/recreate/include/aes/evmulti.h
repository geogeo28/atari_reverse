/* aes/evmulti.h — evnt_multi (`src/aes/evmulti.c`, gemevlib's ev_multi): SEVERAL events waited for at once, and the
 * ones that came answered.
 *
 *   $fe6998 ev_multi(flags, mouse 1, mouse 2, timer, button, message, answers)   D0.w: the events that came
 *
 * ALCYON C, entered by a Line-F call over its caller's frame — the flags a WORD, the six others LONGWORDS (`aes/evdoor.h`
 * names the flags' bits, the button parameter and a MOBLK). It is the event door's last entry.
 *
 * WHAT IT DOES, in the ROM's order:
 *   1. THE KEYBOARD POLLED AND THE FORK QUEUE RUN (chkkbd, forker): whatever the interrupts queued since the process
 *      last waited is posted before anything is looked at.
 *   2. IT POLLS FIRST. Each event asked for is tested as the machine stands — a key queued, the buttons as the
 *      parameter wants them, the mouse where a rectangle asks, a timer of no time, a message in the pipe — and one
 *      that has come is taken there and then. If ANY came, nothing is queued and nothing waits.
 *   3. ELSE EVERY EVENT ASKED FOR IS QUEUED (iasync, one wait each, in the flags' bit order but the message before the
 *      timer), the process waits for any of them (mwait: the dispatcher), and the waits that did not come are
 *      cancelled (acancel).
 *   4. THE FOUR COMMON ANSWERS (ev_rets) — BEFORE the waits are answered, so the buttons it hands out are the word the
 *      LAST answered wait of any earlier call left (AES_EV_BUTTON_STATE) — then the buttons as they are over them
 *      unless a button event was asked for.
 *   5. EACH WAIT THAT CAME IS ANSWERED (apret, in the order key, buttons, rectangle 1, rectangle 2, message, timer):
 *      the key and the clicks into their answer words, and — a button event's — the buttons apret left.
 */
#ifndef TOS102US_AES_EVMULTI_H
#define TOS102US_AES_EVMULTI_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#include "aes/evlib.h"

/* ---- the ANSWERS beyond ev_rets' four (`aes/evlib.h`'s EV_RETS_*), through the same pointer ------------------------- */
#define EV_MULTI_KEY          8          /* word: the key that came             ($fe69f2 move.w (sp)+,8(a0))    */
#define EV_MULTI_CLICKS       10         /* word: the clicks of a button event  ($fe6a3c move.w $972e,10(a0))   */

/* ---- the fast path's button test --------------------------------------------------------------------------------- */
/* More than this many button changes posted since the last ev_rets (`aes/aes.h`'s AES_MTRANS): the event is looked for
 * in the click record's buttons BEFORE the last change first, then in the buttons as they are. */
#define EV_MULTI_ONE_CHANGE   1          /* ($fe6a0e cmpi.w #1,$c836 / ble)                                     */

#ifndef __ASSEMBLER__
uint16_t aes_ev_multi(uint8_t *image, int16_t flags, uint32_t mouse1, uint32_t mouse2, uint32_t timer, uint32_t button,
                      uint32_t message, uint32_t answers);                                           /* $fe6998 */
#endif

#endif /* TOS102US_AES_EVMULTI_H */
