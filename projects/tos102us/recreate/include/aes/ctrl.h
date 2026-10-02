/* aes/ctrl.h — the CONTROL MANAGER's leaves (`src/aes/ctrl.c`): ct_mouse, which takes the mouse for the AES (the form
 * saved, the arrow shown) and gives it back — what fm_alert and mn_do bracket their loops with.
 *
 * Every field below carries one ROM access and the WIDTH TAG (`vdi/linea.h`, "THE WIDTH TAG"); `test/aes.py` parses
 * this header with `aes/aes.h`.
 */
#ifndef TOS102US_AES_CTRL_H
#define TOS102US_AES_CTRL_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

/* The arrow's mouse form: start-up asks rs_gaddr for the AES resource's form 3 and keeps the form it points at. */
#define AES_AD_ARMICE         0xc762     /* long                                ($fda21c move.l (a0),$c762)    */
/* What ct_mouse found when it took the mouse, put back when it gives it up. */
#define AES_CT_MOUSE_SHOWN    0xc908     /* word: AES_GL_MOUSE_SHOWN, then      ($fe4aa4 move.w $9b6e,$c908)   */
#define AES_CT_MOUSE_NEST     0x9bba     /* word: AES_GL_MOFF, then             ($fe4aae move.w $c86a,$9bba)   */

#define CT_MOUSE_GRAB         1          /* ct_mouse's argument, tested for non-zero ($fe4a9c tst.w 8(a6))     */
#define CT_MOUSE_RELEASE      0
/* The third word the release's re-show never pushes (`ctrl.c`'s note): ANY value is as faithful as another. */
#define CT_MOUSE_STALE_COUNT  0

#ifndef __ASSEMBLER__
void aes_ct_mouse(uint8_t *image, int16_t grab);                                                    /* $fe4a98 */
#endif

#endif /* TOS102US_AES_CTRL_H */
