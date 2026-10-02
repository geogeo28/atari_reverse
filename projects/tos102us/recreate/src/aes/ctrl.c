/* ctrl.c — ct_mouse (`aes/ctrl.h`), Alcyon C in the ROM: the mouse taken for the AES or given back, every VDI call
 * through the binding's atoms (`aes/gsx.h`, `aes/gsxif.h`), named by the ROM's own calls — gsx_1code to show the arrow
 * on taking it, gsx_ncode for both calls on giving it back.
 *
 * A MISSING ARGUMENT. Giving the mouse back re-shows it with `clr.w (sp); move.w #122,-(sp)` and a Line-F call to
 * gsx_ncode, which takes THREE words: its third — contrl[3], the count of intin words — is the frame's never-written
 * low word -2(a6), whatever the stack held there. The C hands a named word in its place (CT_MOUSE_STALE_COUNT); the
 * cases on that arm drop contrl[3] by name, and pin the arm with the stack word staged at the C's value.
 */
#include <stdint.h>

#include "machine.h"
#include "aes/ctrl.h"
#include "aes/gsx.h"
#include "aes/gsxif.h"

void aes_ct_mouse(uint8_t *image, int16_t grab)
{
    if (grab) {
        aes_gsx_mfsave(image);
        wr16(image + AES_CT_MOUSE_SHOWN, be16(image + AES_GL_MOUSE_SHOWN));
        wr16(image + AES_CT_MOUSE_NEST, be16(image + AES_GL_MOFF));
        aes_gsx_mfset(image, be32(image + AES_AD_ARMICE));
        if (!be16(image + AES_GL_MOUSE_SHOWN)) {
            aes_gsx_1code(image, VDI_ROM_V_SHOW_C_OPCODE, GSX_SHOW_AT_ONCE);
            wr16(image + AES_GL_MOUSE_SHOWN, GSX_MOUSE_SHOWN);
        }
        wr16(image + AES_GL_MOFF, 0);
        return;
    }
    aes_gsx_ncode(image, VDI_ROM_V_HIDE_C_OPCODE, GSX_NO_POINTS, GSX_NO_WORDS);
    aes_gsx_mfrestore(image);
    wr16(image + AES_GL_MOUSE_SHOWN, GSX_MOUSE_HIDDEN);
    if (be16(image + AES_CT_MOUSE_SHOWN)) {
        aes_gsx_ncode(image, VDI_ROM_V_SHOW_C_OPCODE, GSX_NO_POINTS, CT_MOUSE_STALE_COUNT);
        wr16(image + AES_GL_MOUSE_SHOWN, GSX_MOUSE_SHOWN);
    }
    wr16(image + AES_GL_MOFF, be16(image + AES_CT_MOUSE_NEST));
}
