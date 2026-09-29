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

#include "machine.h"
#include "m68k_idioms.h"
#include "vdi/vdi.h"

/* ---- the clamps the setters and the workstation's initialisation (init_wk) share --------------------
 * An out-of-range index becomes the attribute's DEFAULT, not the nearest bound, in both. */
#define VDI_MARKER_TYPE_COUNT    6    /* marker type 1..6, stored 0-based          ($fcae6a, $fcd452 cmp.w #6) */
#define VDI_MARKER_INDEX_DEFAULT 2    /* ...anything else type 3, the asterisk     ($fcae6a, $fcd45c moveq #2) */
#define VDI_COLOUR_INDEX_DEFAULT 1    /* a colour index outside 0..DEV_TAB[13]-1   ($fcada4, $fcd43e moveq #1) */
#define VDI_PATTERN_STYLE_COUNT  24   /* fill style 1..24 under the PATTERN interior ($fcaf74, $fcd4d2)        */
#define VDI_OTHER_STYLE_COUNT    12   /* ...1..12 under every other                ($fcaf84, $fcd4e8)          */
#define VDI_FILL_STYLE_FIRST     1    /*                                           ($fcd4d8 cmp.w #1)          */
#define VDI_FILL_STYLE_DEFAULT   1    /* ...anything else style 1                  ($fcd4de moveq #1)          */
#define VDI_UD_PATTERN_ROWS      16   /* one plane of the user pattern             ($fcd712, $fcd5a8 cmp.w #16) */

static inline int16_t vdi_within_or(int16_t value, int16_t low, int16_t high, int16_t fallback)
{
    return value < low || value > high ? fallback : value;
}

/* A 1-based index 0-based: outside 1..count it is `fallback` (0-based). */
static inline int16_t vdi_zero_based_or(int16_t one_based, int16_t count, int16_t fallback)
{
    return vdi_within_or((int16_t)(one_based - 1), 0, (int16_t)(count - 1), fallback);
}

/* A colour index checked against the device's colour count: outside 0..DEV_TAB[13]-1 it is colour 1.
 *
 * THE BOUND IS THE COUNT ITSELF (`cmp.w DEV_TAB[13],d7 / bge`), not the count less one: a count of $8000 has no
 * highest index a word can hold, and every index is then colour 1. DEV_TAB[13] is read at each call. */
static inline int16_t vdi_colour_index_or_default(const uint8_t *image, int16_t index)
{
    int16_t colours = table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_COLOURS_INDEX);

    return index >= colours || index < 0 ? VDI_COLOUR_INDEX_DEFAULT : index;
}

/* ...and the pen it maps to — `movea.w` then `adda.l`, so the index is sign-extended before it is doubled. */
static inline uint16_t vdi_mapped_colour(const uint8_t *image, int16_t index)
{
    return be16(image + VDI_MAP_COL + (sign_ext16((uint16_t)index) << 1));
}

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
