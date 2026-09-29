/* vdi/workstation.h — the WORKSTATIONS (`src/vdi/workstation.c`): the physical one opened and closed, the
 * virtual ones opened and closed on the list behind it, and the record set-up both opens share.
 *
 *   $fcb694 v_opnwk (1)     the device tables, the RAM font headers, the resolution, the physical record,
 *                           the text ring, the input modes, the timer and mouse, the realized palette
 *   $fcb998 v_clswk (2)     every virtual workstation given back to GEMDOS, then the timer and mouse
 *   $fcd612 v_opnvwk (100)  a record Malloc'd, given the lowest handle the list walk finds, linked in
 *   $fcd6a4 v_clsvwk (101)  the current record unlinked and Mfree'd — never the physical one
 *   $fcd402 init_wk         the CURRENT record's attributes from intin[1..10], its defaults, the answer
 *
 * All five are Alcyon C. The four functions are VDI functions (`void f(image)`, `vdi/vdi.h`) and init_wk an
 * Alcyon call with no arguments, the way `text_init` is. What they reach is other layers', by name: setres,
 * init_timer_mouse and restore_timer_mouse (`vdi/screen.h`), text_init (`vdi/text.h`), vq_color
 * (`vdi/inquire.h`), st_fl_ptr (`vdi/attributes.h`) and GEMDOS through the VDI's own door, gemdos_call
 * (`vdi/helpers.h`).
 */
#ifndef TOS102US_VDI_WORKSTATION_H
#define TOS102US_VDI_WORKSTATION_H

/* ---- v_opnwk: the device tables where a mode is not the defaults' low resolution ----------------------
 * setres answers the mode opened plus one (`vdi/screen.h`); v_opnwk compares that WORD with 2 and 3 and
 * patches the tables it has just copied from the ROM. Low resolution (1, and any other answer) keeps them. */
#define VDI_OPNWK_WIDE_MAX_X          639   /* DEV_TAB[0], both 640-pixel modes    ($fcb738, $fcb762)  */
#define VDI_OPNWK_MEDIUM_PIXEL_WIDTH  169   /* DEV_TAB[3], microns                 ($fcb740)           */
#define VDI_OPNWK_MEDIUM_COLOURS      4     /* DEV_TAB[13]                         ($fcb748)           */
#define VDI_OPNWK_MEDIUM_PLANES       2     /* INQ_TAB[4]                          ($fcb750)           */
#define VDI_OPNWK_HIGH_MAX_Y          399   /* DEV_TAB[1]                          ($fcb76a)           */
#define VDI_OPNWK_HIGH_PIXEL_WIDTH    372   /* DEV_TAB[3]                          ($fcb772)           */
#define VDI_OPNWK_HIGH_COLOURS        2     /* DEV_TAB[13]                         ($fcb77a)           */
#define VDI_OPNWK_HIGH_COLOUR_CAPABLE 0     /* DEV_TAB[35]                         ($fcb782 clr.w)     */
#define VDI_OPNWK_HIGH_PALETTE        2     /* DEV_TAB[39]                         ($fcb788)           */
#define VDI_OPNWK_HIGH_BACKGROUNDS    1     /* INQ_TAB[1]                          ($fcb790)           */
#define VDI_OPNWK_HIGH_PLANES         1     /* INQ_TAB[4]                          ($fcb798)           */
#define VDI_OPNWK_HIGH_LUT            0     /* INQ_TAB[5]                          ($fcb7a0 clr.w)     */
/* ...and in mono the two RAM system fonts' sizes and which one is the default: the 8x16 becomes it. The two
 * sizes are what the ROM headers copied a moment before already hold, so those two stores move nothing. */
#define VDI_OPNWK_HIGH_8X8_POINT      9     /* FONT_POINT of FONT_RAM_8X8          ($fcb7a6)           */
#define VDI_OPNWK_HIGH_8X16_POINT     10    /* FONT_POINT of FONT_RAM_8X16         ($fcb7ae)           */

/* ---- init_wk: intin[1..10] of an open call (intin[0] is the device, setres's; intin[5] is skipped) ------ */
#define VDI_OPEN_LINE_TYPE            1     /* 1..7, stored less one — and 0 as -1 ($fcd418)           */
#define VDI_OPEN_LINE_COLOUR          2     /*                                     ($fcd430)           */
#define VDI_OPEN_MARK_TYPE            3     /* 1..6, stored less one, else 2       ($fcd44e)           */
#define VDI_OPEN_MARK_COLOUR          4     /*                                     ($fcd466)           */
#define VDI_OPEN_TEXT_COLOUR          6     /* past intin[5], the text face        ($fcd484 addq.l #2) */
#define VDI_OPEN_FILL_INTERIOR        7     /* 0..4, else 0                        ($fcd4b2)           */
#define VDI_OPEN_FILL_STYLE           8     /* stored AS GIVEN, 1-based            ($fcd4c8)           */
#define VDI_OPEN_FILL_COLOUR          9     /*                                     ($fcd500)           */
#define VDI_OPEN_XFM_MODE             10    /* stored as given                     ($fcd51e)           */

/* ---- the return sites the GEMDOS door parks in LINEA_RETSAV: each caller's instruction after its `jsr` --
 * (`vdi/helpers.h`, gemdos_call). The host build hands them on so RETSAV holds what the ROM's own `jsr`
 * leaves; the shipped build reaches the door's `.S`, which parks its own caller's address instead. */
#define VDI_OPNVWK_MALLOC_RETURN      0xfcd62a
#define VDI_CLSVWK_MFREE_RETURN       0xfcd6ee
#define VDI_CLSWK_MFREE_RETURN        0xfcb9ca

/* ---- v_opnwk's call of vq_color: the arrays it points the Line-A pointers at, as ONE host slot ----------
 * (`host_slot.h`, HOST_SLOT_VDI_OPNWK_COLOUR_CALL). The ROM's are frame locals — intout -38(a6), intin
 * -30(a6), contrl -26(a6) — laid out here compacted, contrl only as far as the count vq_color writes. */
#define VDI_OPNWK_CALL_INTOUT         0     /* index, then the three guns          ($fcb876 lea -38)   */
#define VDI_OPNWK_CALL_INTIN          8     /* index, realized                     ($fcb868 lea -30)   */
#define VDI_OPNWK_CALL_CONTRL         12    /* to contrl[4], vq_color's count      ($fcb85e lea -26)   */
#define VDI_OPNWK_CALL_BYTES          22

#ifndef __ASSEMBLER__
#include <stdint.h>

void vdi_v_opnwk(uint8_t *image);    /* $fcb694, opcode 1 */
void vdi_v_clswk(uint8_t *image);    /* $fcb998, opcode 2 */
void vdi_v_opnvwk(uint8_t *image);   /* $fcd612, opcode 100 */
void vdi_v_clsvwk(uint8_t *image);   /* $fcd6a4, opcode 101 */
void vdi_init_wk(uint8_t *image);    /* $fcd402 */
#endif /* __ASSEMBLER__ */

#endif /* TOS102US_VDI_WORKSTATION_H */
