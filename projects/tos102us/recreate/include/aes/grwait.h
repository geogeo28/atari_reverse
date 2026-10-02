/* aes/grwait.h — the box loops that WAIT ON THE MOUSE (`src/aes/grwait.c`): gr_stilldn, the one wait, and gr_watchbox,
 * which loops on it. Hand 68000 in the ROM, ported over its own order; the wait reaches the event layer through the
 * event door (`aes/evdoor.h`).
 */
#ifndef TOS102US_AES_GRWAIT_H
#define TOS102US_AES_GRWAIT_H

#include <stdint.h>

/* gr_stilldn's answer: still down (no rise came) or risen. */
#define GR_STILL_DOWN         1
#define GR_RISEN              0

uint16_t aes_gr_stilldn(uint8_t *image, int16_t leave, int16_t x, int16_t y, int16_t width, int16_t height); /* $fe8508 */
uint16_t aes_gr_watchbox(uint8_t *image, uint32_t tree, int16_t object, int16_t in_state, int16_t out_state);
                                                                                                    /* $fe84ba */

#endif /* TOS102US_AES_GRWAIT_H */
