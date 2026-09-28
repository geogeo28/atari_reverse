/* vdi/lines.h — POLYLINES and MARKERS (`src/vdi/lines.c`): v_pline and v_pmarker, and the Alcyon geometry a
 * WIDE line is drawn with — the quarter circle its round ends and its thickness are taken from (cir_dda,
 * perp_off, do_circ), the wide segments themselves (wline), and the arrowheads (arrow, do_arrow).
 *
 * THE QUARTER CIRCLE. `LINEA_Q_CIRCLE` holds, for each of `LINEA_NUM_QC_LINES` rows from the centre
 * outwards, the half-width of a disc as wide as the line in PIXELS — rows counted in the device's own
 * aspect, which is why DEV_TAB's pixel size is read wherever a length crosses from x to y. cir_dda
 * rebuilds it only when WS_LINE_WIDTH differs from `LINEA_LINE_CW`, the width it was last built for.
 *
 * Every routine here is Alcyon C over the Line-A variables and the current workstation. Four frames hand
 * the ADDRESS of a local on — a wide segment's four corners and its perpendicular offset, perp_off's
 * transformed direction, an arrowhead's triangle, a marker's points — each a host slot off target
 * (`host_slot.h`).
 */
#ifndef TOS102US_VDI_LINES_H
#define TOS102US_VDI_LINES_H

#include "vdi/vdi.h"

/* ---- v_pline's line style: WS_LINE_INDEX below this reads VDI_LINE_STYLES, from it WS_UD_LS ------ */
#define VDI_LINE_STYLE_USER   6          /*                                     ($fcb9f2 cmp.w #6)  */

/* ---- the MARKER SHAPES VDI_MARKER_SHAPES points at, one per WS_MARK_INDEX (0-based) --------------
 * A shape is a count of polylines, then each polyline as a count of points and that many (x, y) word
 * offsets from the marker's centre, scaled by WS_MARK_SCALE ($fd3664..$fd36eb, six shapes). The largest
 * polyline in the ROM's table has five points, which is the room v_pmarker's frame has. */
#define VDI_MARKER_SHAPE_ENTRY_BYTES 4   /* longwords                           ($fcbb12 adda.l a0,a0 x2) */
#define VDI_MARKER_POINTS_MAX 5          /* `link #-60`: five points below its other locals ($fcbb38) */

/* ---- the arrowhead: its length along the line and its half-width across it, from WS_LINE_WIDTH ---- */
#define VDI_ARROW_LENGTH_THIN 8          /* a one-pixel line's                  ($fcd1ae moveq #8)  */
#define VDI_ARROW_LENGTH_PER_WIDTH 3     /* ...else 3 x width - 1               ($fcd1b4 muls.w #3) */
#define VDI_ARROW_SCALE       1000       /* the direction as a fraction of this ($fcd264)           */
/* do_arrow's `step`, in WORDS: from the first point towards the line's end, and back from the last. */
#define VDI_ARROW_STEP_FORWARD 2         /*                                     ($fcd12c move.w #2) */
#define VDI_ARROW_STEP_BACKWARD (-2)     /*                                     ($fcd15a move.w #-2) */

/* ---- a wide segment: its four corners, closed by plygn into a fifth point ------------------------- */
#define VDI_WIDE_CORNER_COUNT 4          /*                                     ($fccce0 move.w #4) */
#define VDI_ARROW_CORNERS     3          /*                                     ($fcd350 move.w #3) */

#ifndef __ASSEMBLER__
#include <stdint.h>

void vdi_v_pline(uint8_t *image);                                          /* $fcb9e0, opcode 6 */
void vdi_v_pmarker(uint8_t *image);                                        /* $fcba7a, opcode 7 */
void vdi_cir_dda(uint8_t *image);                                          /* $fcca86 */
void vdi_wline(uint8_t *image);                                            /* $fccba0 */
/* `x_at` / `y_at` are the image addresses of the offset's two words, read and answered in place. */
void vdi_perp_off(uint8_t *image, uint32_t x_at, uint32_t y_at);           /* $fccd92 */
void vdi_do_circ(uint8_t *image, int16_t x, int16_t y);                    /* $fccf4e */
void vdi_arrow(uint8_t *image);                                            /* $fcd0fa */
/* `point_at` is the image address of the line's end point; `step` WORDS to the next point along it. */
void vdi_do_arrow(uint8_t *image, uint32_t point_at, int16_t step);        /* $fcd196 */
#endif /* __ASSEMBLER__ */

#endif /* TOS102US_VDI_LINES_H */
