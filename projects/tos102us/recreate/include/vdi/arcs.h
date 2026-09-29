/* vdi/arcs.h — ARCS, ELLIPSES and ROUNDED BOXES (`src/vdi/arcs.c`): the workers the GDP's curve arms call —
 * gdp_arc and gdp_ell (the arms' angles and radii into the arc scratch), clc_arc (the curve as a point list,
 * drawn), clc_pts (one point of it), and gdp_rbox (a box with quarter-round corners).
 *
 * THE ARC SCRATCH is VDI RAM the ROM's Alcyon C reads and writes by absolute address (`vdi/linea.h`'s
 * LINEA_GDP_*: DRI's beg_ang, end_ang, del_ang, start, angle, xc, yc, xrad, yrad, n_steps), and the curve is
 * built IN PTSIN — the entry's copy, which the arm's own points were read out of first. Angles are tenths of
 * a degree, counter-clockwise from 3 o'clock; a y offset is SUBTRACTED from the centre (screen y runs down).
 *
 * Every routine here is an Alcyon call entered by `jsr` with nothing in its frame but clc_pts' word index.
 */
#ifndef TOS102US_VDI_ARCS_H
#define TOS102US_VDI_ARCS_H

/* ---- contrl[5]: the GDP numbers these routines tell apart (vdi_gdp's switch, $fd3954) ------------------ */
#define VDI_GDP_ARC           2          /* outlined through v_pline            ($fcc8f0 cmpi.w #2) */
#define VDI_GDP_PIE           3          /* closed at the centre, filled         ($fcc8a8 cmpi.w #3) */
#define VDI_GDP_CIRCLE        4          /* vdi_gdp's own arm stages the scratch ($fcbc70)          */
#define VDI_GDP_ELLIPSE       5          /* ...as for the circle                ($fcbcc8)           */
#define VDI_GDP_ELLIPTICAL_ARC 6         /*                                     ($fcc8f8 cmpi.w #6) */
#define VDI_GDP_ELLIPTICAL_PIE 7         /*                                     ($fcc8b0 cmpi.w #7) */
#define VDI_GDP_ROUNDED_BOX   8          /* outlined                            ($fcc5a4 cmpi.w #8) */
#define VDI_GDP_FILLED_ROUNDED_BOX 9     /* filled: gdp_rbox fills for every number but 8 ($fcc5aa bne) */

/* ---- the rounded box: five points a corner, four corners and the closing point ------------------------- */
#define VDI_RBOX_CORNER_POINTS 5         /*                                     ($fcc444 moveq #10 words) */
#define VDI_RBOX_POINTS       21         /* contrl[1]                           ($fcc59e move.w #21) */
/* The corner radius is the screen's last column over 64 ($fcc2e8 `asr.w #6`), then no more than half the box. */
#define VDI_RBOX_RADIUS_SHIFT 6

#ifndef __ASSEMBLER__
#include <stdint.h>

void vdi_clc_pts(uint8_t *image, int16_t point);                          /* $fcc914 */
void vdi_clc_arc(uint8_t *image);                                          /* $fcc79e */
void vdi_gdp_arc(uint8_t *image);                                          /* $fcc62e */
void vdi_gdp_ell(uint8_t *image);                                          /* $fcc714 */
/* The ROM sorts the box's corners through its CALLER's A5 ($fcc28e `move.l a5,-(sp)`), which the one caller,
 * vdi_gdp, loaded from LINEA_PTSIN at $fcbbe0 and has not touched since: the core reads LINEA_PTSIN. */
void vdi_gdp_rbox(uint8_t *image);                                         /* $fcc284 */
#endif /* __ASSEMBLER__ */

#endif /* TOS102US_VDI_ARCS_H */
