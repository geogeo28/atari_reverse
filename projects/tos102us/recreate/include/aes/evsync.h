/* aes/evsync.h — the scheduler's SEMAPHORE (`src/aes/evsync.c`): GEM's SPB, a nesting count, the PD holding it and the
 * waits queued on it (`aes/wmupdate.h`: the screen lock `wind_spb` is the one the ROM keeps).
 *
 *   $fe4e5a tak_flag(spb)   the semaphore taken if it is free or the running process's own — D0.w whether it was
 *
 * Alcyon C in the ROM (`link a6`), entered by a Line-F call (`$f800`) from wm_update (`$feca82`) and amutex
 * (`$fe4ea0`) over one pointer.
 */
#ifndef TOS102US_AES_EVSYNC_H
#define TOS102US_AES_EVSYNC_H

#include <stdint.h>

/* tak_flag's ANSWER, the word of D0: `moveq #1,d0` ($fe4e8a) or `clr.w d0` ($fe4e7c). The refusal clears the WORD
 * alone, over the owner it has just loaded (`move.l 2(a5),d0`, $fe4e68): D0's high word is then the owner's — nothing
 * a caller reads (wm_update and amutex test the word, `tst.w d0`). */
#define TAK_FLAG_TAKEN        1
#define TAK_FLAG_REFUSED      0
/* The count a FREE semaphore holds once tak_flag has counted its caller in ($fe4e74 cmpi.w #1,(a5)). */
#define SPB_FIRST_HOLD        1

uint16_t aes_tak_flag(uint8_t *image, uint32_t semaphore);                                                /* $fe4e5a */

#endif /* TOS102US_AES_EVSYNC_H */
