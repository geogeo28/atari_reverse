/* vdi/attributes.h — the VDI's ATTRIBUTE SETTERS (`src/vdi/attributes.c`), and two helpers other layers
 * reuse: the fill-pattern pointer and the rectangle corner sort.
 *
 * Every setter is a VDI function, `void vdi_<fn>(uint8_t *image)` (`vdi/vdi.h` says why), and NONE
 * writes a Line-A copy the dispatcher makes of a workstation field (`LINEA_WRT_MODE`, `LINEA_CLIP`,
 * `LINEA_PATPTR`, ...): the copy catches up on the NEXT call, when `$fca9f6` copies the record again, and
 * until then a Line-A primitive still draws with the old value. (A few store outside the record too —
 * vsin_mode into Line-A's input modes, the vex_* exchanges into USER_*, vsm_height into VDI_RESULT — but
 * none of those is a dispatcher copy.)
 */
#ifndef TOS102US_VDI_ATTRIBUTES_H
#define TOS102US_VDI_ATTRIBUTES_H

#include <stdint.h>

/* ---- the line, marker and fill setters ----------------------------------------------------------- */
void vdi_vsl_type(uint8_t *image);          /* $fcac76, opcode 15  */
void vdi_vsl_width(uint8_t *image);         /* $fcacc0, opcode 16  */
void vdi_vsl_ends(uint8_t *image);          /* $fcad20, opcode 108 */
void vdi_vsl_color(uint8_t *image);         /* $fcad7c, opcode 17  */
void vdi_vsl_udsty(uint8_t *image);         /* $fcb4a2, opcode 113 */
void vdi_vsm_height(uint8_t *image);        /* $fcadcc, opcode 19  */
void vdi_vsm_type(uint8_t *image);          /* $fcae58, opcode 18  */
void vdi_vsm_color(uint8_t *image);         /* $fcaea8, opcode 20  */
void vdi_vsf_interior(uint8_t *image);      /* $fcaefe, opcode 23  */
void vdi_vsf_style(uint8_t *image);         /* $fcaf4a, opcode 24  */
void vdi_vsf_color(uint8_t *image);         /* $fcafb2, opcode 25  */
void vdi_vsf_udpat(uint8_t *image);         /* $fcd6fa, opcode 112 */

/* ---- the text setters ---------------------------------------------------------------------------- */
void vdi_vst_effects(uint8_t *image);       /* $fce3b2, opcode 106 */
void vdi_vst_alignment(uint8_t *image);     /* $fce3e6, opcode 39  */
void vdi_vst_rotation(uint8_t *image);      /* $fce442, opcode 13  */
void vdi_vst_color(uint8_t *image);         /* $fce560, opcode 22  */

/* ---- the write mode, the input modes, the clip rectangle ----------------------------------------- */
void vdi_vswr_mode(uint8_t *image);         /* $fcb32e, opcode 32  */
void vdi_vsin_mode(uint8_t *image);         /* $fcb388, opcode 33  */
void vdi_vqin_mode(uint8_t *image);         /* $fcb3f6, opcode 115 */
void vdi_vs_clip(uint8_t *image);           /* $fcb4ba, opcode 129 */

/* ---- the four vector exchanges: the new routine at contrl[7..8], the old one answered at [9..10] --- */
void vdi_vex_timv(uint8_t *image);          /* $fca6a4, opcode 118 */
void vdi_vex_butv(uint8_t *image);          /* $fcff68, opcode 125 */
void vdi_vex_motv(uint8_t *image);          /* $fcff80, opcode 126 */
void vdi_vex_curv(uint8_t *image);          /* $fcff98, opcode 127 */

/* ---- the shared helpers -------------------------------------------------------------------------- */
/* $fcc9a6 — st_fl_ptr: point the CURRENT workstation's WS_PATPTR / WS_PATMSK at the pattern its
 * WS_FILL_STYLE (the interior) and WS_FILL_INDEX (the style, 0-based) select. Called after either
 * changes, and by the workstation's initialisation. */
void vdi_st_fl_ptr(uint8_t *image);

/* $fcb55e — arb_corner: sort the rectangle `corners` points at (x0, y0, x1, y1, four signed words) IN
 * PLACE so that x0 <= x1, and y by `order`: ascending, descending, or — any other value — left alone.
 * vs_clip, the raster copies, vr_recfl and the rounded box all sort their ptsin through it. */
#define VDI_CORNERS_Y_DESCENDING 0       /* y0 >= y1                            ($fcb586 tst.w)     */
#define VDI_CORNERS_Y_ASCENDING  1       /* y0 <= y1                            ($fcb58e cmp.w #1)  */
void vdi_arb_corner(uint8_t *image, uint32_t corners, uint16_t order);

#endif /* TOS102US_VDI_ATTRIBUTES_H */
