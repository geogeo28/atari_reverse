/* vdi/text.h — the TEXT LAYER's C (`src/vdi/text.c`): the font ring's set-up, the scaled header, the size
 * and face setters, the two measuring inquiries and the GDOS font loader.
 *
 * Six are VDI FUNCTIONS, entered as the dispatcher leaves the machine (`vdi/vdi.h`) and so `void f(image)`.
 * The other two are ALCYON C calls with no arguments: `text_init`, which v_opnwk makes once, and
 * `make_header`, which vst_height and vst_point reach by `bsr` once they have chosen a font to scale.
 *
 * THE RING (`LINEA_FONT_RING`, `vdi/linea.h`) is how every one of them finds a font: slot by slot until
 * a ZERO SLOT, each slot a chain through FONT_NEXT. A face is an id; its sizes are the fonts of that id,
 * which the setters expect to find in ascending order along the chain after the first of them.
 */
#ifndef TOS102US_VDI_TEXT_H
#define TOS102US_VDI_TEXT_H

/* WS_PTS_MODE's two values: which setter chose the size, and so which one vst_font re-runs. */
#define VDI_PTS_MODE_HEIGHT   0          /*                                     ($fcdfe6 clr.w)     */
#define VDI_PTS_MODE_POINT    1          /*                                     ($fce284 move.w #1) */
/* vqt_extent's answer: the string's box, four corners ($fce724 `move.w #4`) — what v_gtext and d_justified
 * give it a frame of their own for. */
#define VDI_EXTENT_ANSWER_POINTS 4

#ifndef __ASSEMBLER__
#include <stdint.h>

/* ---- the Alcyon calls ---------------------------------------------------------------------------- */
void vdi_text_init(uint8_t *image);           /* $fcde9c */
void vdi_make_header(uint8_t *image);         /* $fce116 */

/* ---- the VDI functions ------------------------------------------------------------------------- */
void vdi_vst_height(uint8_t *image);          /* $fcdfd0, opcode 12 */
void vdi_vst_font(uint8_t *image);            /* $fce47c, opcode 21 */
void vdi_vst_point(uint8_t *image);           /* $fce26c, opcode 107 */
void vdi_vqt_extent(uint8_t *image);          /* $fce62a, opcode 116 */
void vdi_vqt_width(uint8_t *image);           /* $fce7f0, opcode 117 */
void vdi_vst_load_fonts(uint8_t *image);      /* $fced06, opcode 119 */
#endif /* __ASSEMBLER__ */

#endif /* TOS102US_VDI_TEXT_H */
