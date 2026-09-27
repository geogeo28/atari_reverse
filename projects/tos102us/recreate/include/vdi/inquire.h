/* vdi/inquire.h — the VDI's INQUIRIES and its PALETTE: the functions that answer what a workstation,
 * the fonts, the mouse, the keyboard and the colour registers hold, and the two that set and read a
 * colour.
 *
 * Every one is a VDI function entered as the dispatcher leaves the machine (`vdi/vdi.h`), so every
 * core is `void f(uint8_t *image)`: arguments through the Line-A pointers, answers into intout /
 * ptsout / contrl's two counts, and — for five of them — VDI_RESULT = 1. The inquiries are
 * `src/vdi/inquire.c`; the palette pair is `src/vdi/palette.c`.
 */
#ifndef TOS102US_VDI_INQUIRE_H
#define TOS102US_VDI_INQUIRE_H

#include <stdint.h>

/* ---- src/vdi/inquire.c --------------------------------------------------------------------------- */
void vdi_nop(uint8_t *image);                 /* $fca652, opcodes 4 / 10 / 27 / 34 */
void vdi_valuator(uint8_t *image);            /* $fcb198, opcode 29 */
void vdi_vql_attributes(uint8_t *image);      /* $fcbd7e, opcode 35 */
void vdi_vqm_attributes(uint8_t *image);      /* $fcbdda, opcode 36 */
void vdi_vqf_attributes(uint8_t *image);      /* $fcbe3a, opcode 37 */
void vdi_vqt_attributes(uint8_t *image);      /* $fce5b0, opcode 38 */
void vdi_vq_extnd(uint8_t *image);            /* $fcb8d0, opcode 102 */
void vdi_vst_unload_fonts(uint8_t *image);    /* $fced9a, opcode 120 */
void vdi_vq_mouse(uint8_t *image);            /* $fcb156, opcode 124 */
void vdi_vq_key_s(uint8_t *image);            /* $fcb30a, opcode 128 */
void vdi_vqt_name(uint8_t *image);            /* $fce8ca, opcode 130 */
void vdi_vqt_fontinfo(uint8_t *image);        /* $fce95a, opcode 131 */

/* ---- src/vdi/palette.c --------------------------------------------------------------------------- */
void vdi_vs_color(uint8_t *image);            /* $fd2dd2, opcode 14 */
void vdi_vq_color(uint8_t *image);            /* $fd2e84, opcode 26 */

#endif /* TOS102US_VDI_INQUIRE_H */
