/* attributes.c — the VDI's ATTRIBUTE SETTERS, the fill-pattern pointer and the corner sort.
 *
 * Every setter has one shape: read an index out of intin (or ptsin), CLAMP it — an out-of-range value
 * becomes the attribute's DEFAULT rather than the nearest bound, except where the ROM says otherwise —
 * store it into the workstation `LINEA_CUR_WORK` names, answer the value actually set in intout, and
 * say how many words were answered in contrl[4]. The ORDER of those stores is the ROM's, function by
 * function, because it is visible when a caller's arrays overlap.
 *
 * None of them writes a Line-A copy the dispatcher makes of a workstation field (`vdi/attributes.h`).
 *
 * THE INDEXES ARE SIGNED WORDS, and every clamp is a signed compare (`bge`/`bgt`/`blt`): $8000 is a
 * very negative style, not a very large one.
 */
#include <stdint.h>

#include "machine.h"
#include "ipl.h"
#include "m68k_idioms.h"
#include "recreate.h"
#include "bios/bcon.h"
#include "vdi/vdi.h"
#include "vdi/attributes.h"

#define ARRAY_WORD_BYTES      2

/* Line style 1..7 is stored 0-based; anything else is style 1, solid ($fcac94). */
#define LINE_STYLE_COUNT      7
/* Line ends: 0 square, 1 arrow, 2 round; anything else is square ($fcad40). */
#define LINE_END_LAST         2
/* A line's width is odd: an even one is rounded DOWN, by `((w - 1) / 2) * 2 + 1` ($fcace8). */
#define LINE_WIDTH_MIN        1
/* The marker, colour and fill-style clamps are `vdi/attributes.h`'s: init_wk clamps the same way. */
/* Write mode 1..4 is stored 0-based; anything else is mode 1, replace ($fcb34c). */
#define WRITE_MODE_LAST       3
/* Text alignment: horizontal 0..2, vertical 0..5; anything else is 0 ($fce406, $fce41c). */
#define H_ALIGN_LAST          2
#define V_ALIGN_LAST          5
/* Text rotation in tenths of a degree, ROUNDED to the nearest quarter turn ($fce44e). */
#define QUARTER_TURN          900
#define HALF_QUARTER_TURN     450
/* vsin_mode/vqin_mode's intin[0]: the four input devices ($fd3914). */
#define DEVICE_LOCATOR        1
#define DEVICE_VALUATOR       2
#define DEVICE_CHOICE         3
#define DEVICE_STRING         4
/* vsf_udpat: one plane of the user pattern is VDI_UD_PATTERN_ROWS rows, and WS_MULTIFILL says whether
 * the pattern is one plane or one per screen plane ($fcd712 cmp.w #16, $fcd724 asl.w #4). */
#define UD_PATTERN_PLANE_SHIFT 4
#define UD_PATTERN_ROW_MASK   (VDI_UD_PATTERN_ROWS - 1)
#define ONE_PLANE             0
#define EVERY_PLANE           1
/* vsl_ends and vst_alignment answer two words; everything else here that answers, one. */
#define ONE_WORD              1
#define TWO_WORDS             2
#define ONE_POINT             1

/* ---- the workstation and the device tables (the call's arrays are `vdi/vdi.h`'s) ------------- */

/* ---- the clamps ------------------------------------------------------------------------------- */

/* The 1-based index in intin[0], 0-based (`vdi_zero_based_or`). */
static int16_t zero_based_or(const uint8_t *image, int16_t count, int16_t fallback)
{
    return vdi_zero_based_or(intin_word(image, 0), count, fallback);
}

/* The colour index in intin[0], clamped (`vdi/attributes.h`); the pen it maps to is `vdi_mapped_colour`. */
static int16_t colour_index(const uint8_t *image)
{
    return vdi_colour_index_or_default(image, intin_word(image, 0));
}

/* ================================================================================================
 * Lines
 * ============================================================================================= */

/* $fcac76 — vsl_type (15). contrl[4] first; the style stored 0-based, answered 1-based. */
void vdi_vsl_type(uint8_t *image)
{
    int16_t style;

    answer_words(image, ONE_WORD);
    style = zero_based_or(image, LINE_STYLE_COUNT, 0);
    set_current_work_word(image, WS_LINE_INDEX, (uint16_t)style);
    answer_intout(image, 0, (uint16_t)(style + 1));
}

/* $fcacc0 — vsl_width (16). ptsin[0] into 1..SIZ_TAB[6], rounded down to odd; answered as the point
 * (width, 0). The division is `divs.w #2`, which truncates towards zero — the same as C's. */
void vdi_vsl_width(uint8_t *image)
{
    int16_t widest = table_word(image, LINEA_SIZ_TAB, VDI_SIZ_TAB_MAX_LINE_WIDTH_INDEX);
    int16_t width = ptsin_word(image, 0);

    if (width < LINE_WIDTH_MIN)
        width = LINE_WIDTH_MIN;
    else if (width > widest)
        width = widest;
    width = (int16_t)((int16_t)(width - 1) / 2 * 2 + 1);

    answer_points(image, ONE_POINT);
    set_current_work_word(image, WS_LINE_WIDTH, (uint16_t)width);
    answer_ptsout(image, 0, (uint16_t)width);
    answer_ptsout(image, 1, 0);
}

/* $fcad20 — vsl_ends (108). Both end styles read before anything is stored. */
void vdi_vsl_ends(uint8_t *image)
{
    int16_t begin;
    int16_t end;

    answer_words(image, TWO_WORDS);
    begin = vdi_within_or(intin_word(image, 0), 0, LINE_END_LAST, 0);
    end = vdi_within_or(intin_word(image, 1), 0, LINE_END_LAST, 0);
    set_current_work_word(image, WS_LINE_BEG, (uint16_t)begin);
    answer_intout(image, 0, (uint16_t)begin);
    set_current_work_word(image, WS_LINE_END, (uint16_t)end);
    answer_intout(image, 1, (uint16_t)end);
}

/* $fcad7c — vsl_color (17). The INDEX is answered, the mapped PEN stored. */
void vdi_vsl_color(uint8_t *image)
{
    int16_t index;

    answer_words(image, ONE_WORD);
    index = colour_index(image);
    answer_intout(image, 0, (uint16_t)index);
    set_current_work_word(image, WS_LINE_COLOR, vdi_mapped_colour(image, index));
}

/* $fcb4a2 — vsl_udsty (113). The user line style, raw: no clamp and no answer at all. */
void vdi_vsl_udsty(uint8_t *image)
{
    set_current_work_word(image, WS_UD_LS, (uint16_t)intin_word(image, 0));
}

/* ================================================================================================
 * Markers
 * ============================================================================================= */

/* $fcadcc — vsm_height (19). ptsin[1] into SIZ_TAB's marker heights, then a SCALE — the height in
 * units of the smallest marker, rounded to nearest — and the size that scale really gives, answered
 * as a point. It is one of the few functions that sets `VDI_RESULT`. All `divs.w`/`muls.w`: word
 * quotients and word products, and a zero smallest height is the 68000's zero-divide. */
void vdi_vsm_height(uint8_t *image)
{
    int16_t lowest = table_word(image, LINEA_SIZ_TAB, VDI_SIZ_TAB_MIN_MARK_HEIGHT_INDEX);
    int16_t highest = table_word(image, LINEA_SIZ_TAB, VDI_SIZ_TAB_MAX_MARK_HEIGHT_INDEX);
    int16_t narrowest = table_word(image, LINEA_SIZ_TAB, VDI_SIZ_TAB_MIN_MARK_WIDTH_INDEX);
    int16_t height = ptsin_word(image, 1);
    int16_t scale;

    if (height < lowest)
        height = lowest;
    else if (height > highest)
        height = highest;
    set_current_work_word(image, WS_MARK_HEIGHT, (uint16_t)height);
    scale = quotient_word(m68k_divs_w(sign_ext16((uint16_t)(height + lowest / 2)), (uint16_t)lowest));
    set_current_work_word(image, WS_MARK_SCALE, (uint16_t)scale);

    answer_points(image, ONE_POINT);
    answer_ptsout(image, 0, (uint16_t)((int32_t)scale * narrowest));
    answer_ptsout(image, 1, (uint16_t)((int32_t)scale * lowest));
    wr16(image + VDI_RESULT, VDI_RESULT_SET);
}

/* $fcae58 — vsm_type (18). contrl[4] LAST here. */
void vdi_vsm_type(uint8_t *image)
{
    int16_t type = zero_based_or(image, VDI_MARKER_TYPE_COUNT, VDI_MARKER_INDEX_DEFAULT);

    set_current_work_word(image, WS_MARK_INDEX, (uint16_t)type);
    answer_intout(image, 0, (uint16_t)(type + 1));
    answer_words(image, ONE_WORD);
}

/* $fcaea8 — vsm_color (20). vsl_color's body with contrl[4] LAST. */
void vdi_vsm_color(uint8_t *image)
{
    int16_t index = colour_index(image);

    answer_intout(image, 0, (uint16_t)index);
    set_current_work_word(image, WS_MARK_COLOR, vdi_mapped_colour(image, index));
    answer_words(image, ONE_WORD);
}

/* ================================================================================================
 * Fill
 * ============================================================================================= */

/* One of the four pattern tables: its mask word, and the first row of pattern `index` in it. */
static void point_into_table(uint8_t *image, uint32_t work, uint32_t table, int16_t index)
{
    int16_t mask = table_word(image, table, 0);
    uint32_t offset = word_index((uint16_t)(index * (mask + 1)), ARRAY_WORD_BYTES);

    wr32(image + work + WS_PATPTR, table + VDI_PATTERN_TABLE_HEADER_BYTES + offset);
    wr16(image + work + WS_PATMSK, (uint16_t)mask);
}

static void point_at(uint8_t *image, uint32_t work, uint32_t pattern, uint16_t mask)
{
    wr32(image + work + WS_PATPTR, pattern);
    wr16(image + work + WS_PATMSK, mask);
}

/* $fcc9a6 — st_fl_ptr. A 0-based style below a table's count indexes that table; one at or above it
 * is REBASED into the next, and nothing bounds it there — a hatch style of 13..24, which vsf_style
 * allows under the pattern interior and which survives a later switch to hatch, points past the
 * last hatch into whatever follows it in ROM. Reproduced, not corrected.
 *
 * An interior outside 0..4 falls through the ROM's switch to the stores with A5 NEVER LOADED: the
 * pointer would be whatever the caller left in A5. Every caller clamps the interior first (vsf_interior,
 * `$fcd4b4` in the workstation's initialisation), so no path reaches it; it HALTS here rather than
 * invent a register. */
void vdi_st_fl_ptr(uint8_t *image)
{
    uint32_t work = current_work(image);
    int16_t style = (int16_t)be16(image + work + WS_FILL_INDEX);

    switch (be16(image + work + WS_FILL_STYLE)) {
    case VDI_INTERIOR_HOLLOW:
        point_at(image, work, VDI_PATTERN_HOLLOW, 0);
        break;
    case VDI_INTERIOR_SOLID:
        point_at(image, work, VDI_PATTERN_SOLID, 0);
        break;
    case VDI_INTERIOR_PATTERN:
        if (style < VDI_PATTERNS_LOWER_COUNT)
            point_into_table(image, work, VDI_PATTERNS_LOWER, style);
        else
            point_into_table(image, work, VDI_PATTERNS_UPPER, (int16_t)(style - VDI_PATTERNS_LOWER_COUNT));
        break;
    case VDI_INTERIOR_HATCH:
        if (style < VDI_HATCHES_LOWER_COUNT)
            point_into_table(image, work, VDI_HATCHES_LOWER, style);
        else
            point_into_table(image, work, VDI_HATCHES_UPPER, (int16_t)(style - VDI_HATCHES_LOWER_COUNT));
        break;
    case VDI_INTERIOR_USER:
        point_at(image, work, work + WS_UD_PATRN, UD_PATTERN_ROW_MASK);
        break;
    default:
        recreate_not_reconstructed("st_fl_ptr: an interior outside 0..4 stores an unloaded A5");
    }
}

/* $fcaefe — vsf_interior (23). 0..4, anything else hollow; then the pattern pointer follows it. */
void vdi_vsf_interior(uint8_t *image)
{
    int16_t interior;

    answer_words(image, ONE_WORD);
    interior = vdi_within_or(intin_word(image, 0), VDI_INTERIOR_HOLLOW, VDI_INTERIOR_USER, VDI_INTERIOR_HOLLOW);
    set_current_work_word(image, WS_FILL_STYLE, (uint16_t)interior);
    answer_intout(image, 0, (uint16_t)interior);
    vdi_st_fl_ptr(image);
}

/* $fcaf4a — vsf_style (24). The bound is the CURRENT interior's: 24 under the pattern interior, 12
 * under every other, even the three that have no styles. Answered 1-based, stored 0-based. */
void vdi_vsf_style(uint8_t *image)
{
    int16_t style;
    int16_t count;

    answer_words(image, ONE_WORD);
    style = intin_word(image, 0);
    count = current_work_word(image, WS_FILL_STYLE) == VDI_INTERIOR_PATTERN
            ? VDI_PATTERN_STYLE_COUNT : VDI_OTHER_STYLE_COUNT;
    style = vdi_within_or(style, VDI_FILL_STYLE_FIRST, count, VDI_FILL_STYLE_DEFAULT);
    answer_intout(image, 0, (uint16_t)style);
    set_current_work_word(image, WS_FILL_INDEX, (uint16_t)(style - 1));
    vdi_st_fl_ptr(image);
}

/* $fcafb2 — vsf_color (25). vsl_color's body, into the fill pen. */
void vdi_vsf_color(uint8_t *image)
{
    int16_t index;

    answer_words(image, ONE_WORD);
    index = colour_index(image);
    answer_intout(image, 0, (uint16_t)index);
    set_current_work_word(image, WS_FILL_COLOR, vdi_mapped_colour(image, index));
}

/* $fcd6fa — vsf_udpat (112). contrl[3] words: sixteen are ONE plane, sixteen per screen plane
 * (INQ_TAB[4], shifted as a word) are EVERY plane, and any other count is REFUSED — nothing stored,
 * not even WS_MULTIFILL, and no answer. Neither arm re-points WS_PATPTR: it already names this array
 * whenever the user interior is current. */
void vdi_vsf_udpat(uint8_t *image)
{
    uint32_t work = current_work(image);
    int16_t words = (int16_t)be16(image + linea_pointer(image, LINEA_CONTRL) + CONTRL_N_INTIN);
    int16_t per_plane = (int16_t)(table_word(image, LINEA_INQ_TAB, VDI_INQ_TAB_PLANES_INDEX)
                                  << UD_PATTERN_PLANE_SHIFT);
    const uint8_t *source;
    uint8_t *pattern;
    int16_t row;

    if (words == VDI_UD_PATTERN_ROWS)
        wr16(image + work + WS_MULTIFILL, ONE_PLANE);
    else if (words == per_plane)
        wr16(image + work + WS_MULTIFILL, EVERY_PLANE);
    else
        return;
    source = image + linea_pointer(image, LINEA_INTIN);
    pattern = image + work + WS_UD_PATRN;
    for (row = 0; row < words; row++, source += ARRAY_WORD_BYTES, pattern += ARRAY_WORD_BYTES)
        wr16(pattern, be16(source));
}

/* ================================================================================================
 * Text
 * ============================================================================================= */

/* $fce3b2 — vst_effects (106). The requested effects masked by those the device has (INQ_TAB[2]). */
void vdi_vst_effects(uint8_t *image)
{
    uint16_t effects = (uint16_t)intin_word(image, 0)
                       & (uint16_t)table_word(image, LINEA_INQ_TAB, VDI_INQ_TAB_EFFECTS_INDEX);

    set_current_work_word(image, WS_STYLE, effects);
    answer_intout(image, 0, effects);
    answer_words(image, ONE_WORD);
}

/* $fce3e6 — vst_alignment (39). Each half answered BEFORE it is stored, and read after the first
 * half's answer. */
void vdi_vst_alignment(uint8_t *image)
{
    int16_t horizontal = vdi_within_or(intin_word(image, 0), 0, H_ALIGN_LAST, 0);
    int16_t vertical;

    answer_intout(image, 0, (uint16_t)horizontal);
    set_current_work_word(image, WS_H_ALIGN, (uint16_t)horizontal);
    vertical = vdi_within_or(intin_word(image, 1), 0, V_ALIGN_LAST, 0);
    answer_intout(image, 1, (uint16_t)vertical);
    set_current_work_word(image, WS_V_ALIGN, (uint16_t)vertical);
    answer_words(image, TWO_WORDS);
}

/* $fce442 — vst_rotation (13). The angle rounded to a quarter turn: `add.w #450` — which WRAPS past
 * 32,317 — then `divs.w #900`, truncating towards zero, then `muls.w #900`. No range check: -900,
 * 1800 and 3600 are all stored as they come. */
void vdi_vst_rotation(uint8_t *image)
{
    int16_t shifted = (int16_t)(intin_word(image, 0) + HALF_QUARTER_TURN);
    int16_t turns = quotient_word(m68k_divs_w(sign_ext16((uint16_t)shifted), QUARTER_TURN));
    uint16_t rounded = (uint16_t)((int32_t)turns * QUARTER_TURN);

    set_current_work_word(image, WS_CHUP, rounded);
    answer_intout(image, 0, rounded);
    answer_words(image, ONE_WORD);
}

/* $fce560 — vst_color (22). contrl[4] after the clamp, before the answer. */
void vdi_vst_color(uint8_t *image)
{
    int16_t index = colour_index(image);

    answer_words(image, ONE_WORD);
    answer_intout(image, 0, (uint16_t)index);
    set_current_work_word(image, WS_TEXT_COLOR, vdi_mapped_colour(image, index));
}

/* ================================================================================================
 * Write mode, input modes, clipping
 * ============================================================================================= */

/* $fcb32e — vswr_mode (32). Stored 0-based, answered 1-based. */
void vdi_vswr_mode(uint8_t *image)
{
    int16_t mode;

    answer_words(image, ONE_WORD);
    mode = vdi_within_or((int16_t)(intin_word(image, 0) - 1), 0, WRITE_MODE_LAST, 0);
    set_current_work_word(image, WS_WRT_MODE, (uint16_t)mode);
    answer_intout(image, 0, (uint16_t)(mode + 1));
}

/* The Line-A word that keeps a device's input mode, or 0 for a device number the switch has no arm
 * for — 0 and anything above 4 (`cmp.w #4 / bhi`, unsigned). */
static uint32_t input_mode_variable(int16_t device)
{
    switch (device) {
    case DEVICE_LOCATOR:
        return LINEA_LOC_MODE;
    case DEVICE_VALUATOR:
        return LINEA_VAL_MODE;
    case DEVICE_CHOICE:
        return LINEA_CHC_MODE;
    case DEVICE_STRING:
        return LINEA_STR_MODE;
    default:
        return 0;
    }
}

/* $fcb388 — vsin_mode (33). intin[1] (1 request, 2 sample) is echoed RAW into intout[0] — no range
 * check — and stored less one; intin[0], the device, is read only after that echo. */
void vdi_vsin_mode(uint8_t *image)
{
    int16_t mode;
    uint32_t variable;

    answer_words(image, ONE_WORD);
    mode = intin_word(image, 1);
    answer_intout(image, 0, (uint16_t)mode);
    variable = input_mode_variable(intin_word(image, 0));
    if (variable != 0)
        wr16(image + variable, (uint16_t)(mode - 1));
}

/* $fcb3f6 — vqin_mode (115). Answers the STORED word, which is vsin_mode's argument less one: a
 * device set to sample mode (2) reports 1. A device number with no arm leaves intout[0] unwritten,
 * though contrl[4] still says one word. */
void vdi_vqin_mode(uint8_t *image)
{
    uint32_t variable;

    answer_words(image, ONE_WORD);
    variable = input_mode_variable(intin_word(image, 0));
    if (variable != 0)
        answer_intout(image, 0, be16(image + variable));
}

/* $fcb55e — arb_corner. Word compares, signed; the x pair is always sorted ascending. */
static void swap_words(uint8_t *image, uint32_t first, uint32_t second)
{
    uint16_t held = be16(image + first);

    wr16(image + first, be16(image + second));
    wr16(image + second, held);
}

void vdi_arb_corner(uint8_t *image, uint32_t corners, uint16_t order)
{
    uint32_t x0 = corners, y0 = corners + ARRAY_WORD_BYTES;
    uint32_t x1 = corners + 2 * ARRAY_WORD_BYTES, y1 = corners + 3 * ARRAY_WORD_BYTES;
    int16_t top, bottom;

    if ((int16_t)be16(image + x0) > (int16_t)be16(image + x1))
        swap_words(image, x0, x1);
    top = (int16_t)be16(image + y0);
    bottom = (int16_t)be16(image + y1);
    if ((order == VDI_CORNERS_Y_DESCENDING && top < bottom) || (order == VDI_CORNERS_Y_ASCENDING && top > bottom))
        swap_words(image, y0, y1);
}

/* $fcb4ba — vs_clip (129). intin[0] is stored RAW as WS_CLIP (any nonzero word turns clipping on,
 * and is kept as given). On: the caller's ptsin is SORTED IN PLACE (arb_corner, y ascending), then
 * the top-left corner is floored at 0 and the bottom-right capped at DEV_TAB's last column and row —
 * each against ONE bound only, so a rectangle wholly off the screen keeps its off-screen edge — each
 * word READ AND STORED IN TURN, which is visible when ptsin overlaps the record. Off: the whole
 * screen. No answer and no count. */
static int16_t at_least_zero(int16_t value)
{
    return value < 0 ? 0 : value;
}

static int16_t at_most(int16_t value, int16_t bound)
{
    return value > bound ? bound : value;
}

/* The clip-on arm, kept out of line so the clip-off arm — the common call, and a handful of stores —
 * does not pay for the addresses this one precomputes (measured: 1.16 inline, the bar is 1.10). PTSIN is
 * read ONCE, before the sort, and walked (`movea.l $29a6,a5` / `move.w (a5)+,d6`): a ptsin laid over the
 * pointer itself is sorted under the ROM without moving the words it then reads. */
__attribute__((noinline))
static void clip_to_the_corners(uint8_t *image, uint32_t work, int16_t last_x, int16_t last_y)
{
    uint32_t ptsin = linea_pointer(image, LINEA_PTSIN);
    const uint8_t *corner = image + ptsin;

    vdi_arb_corner(image, ptsin, VDI_CORNERS_Y_ASCENDING);
    wr16(image + work + WS_XMN_CLIP, (uint16_t)at_least_zero((int16_t)be16(corner)));
    wr16(image + work + WS_YMN_CLIP, (uint16_t)at_least_zero((int16_t)be16(corner + VDI_WORD_BYTES)));
    wr16(image + work + WS_XMX_CLIP, (uint16_t)at_most((int16_t)be16(corner + 2 * VDI_WORD_BYTES), last_x));
    wr16(image + work + WS_YMX_CLIP, (uint16_t)at_most((int16_t)be16(corner + 3 * VDI_WORD_BYTES), last_y));
}

void vdi_vs_clip(uint8_t *image)
{
    uint32_t work = current_work(image);
    int16_t clip = intin_word(image, 0);
    int16_t last_x = table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_MAX_X_INDEX);
    int16_t last_y = table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_MAX_Y_INDEX);

    wr16(image + work + WS_CLIP, (uint16_t)clip);
    if (clip != 0) {
        clip_to_the_corners(image, work, last_x, last_y);
        return;
    }
    /* The ROM clears WS_CLIP a second time here ($fcb538): the same 0 over the same word. */
    wr16(image + work + WS_XMN_CLIP, 0);
    wr16(image + work + WS_YMN_CLIP, 0);
    wr16(image + work + WS_XMX_CLIP, (uint16_t)last_x);
    wr16(image + work + WS_YMX_CLIP, (uint16_t)last_y);
}

/* ================================================================================================
 * The vector exchanges: contrl[9..10] gets the routine the Line-A longword held, and the longword
 * gets contrl[7..8]. Nothing is called — the routines in the snapshot point into the AES.
 * ============================================================================================= */

static void exchange_vector(uint8_t *image, uint32_t vector)
{
    uint32_t contrl = linea_pointer(image, LINEA_CONTRL);

    wr32(image + contrl + CONTRL_POINTER_B, be32(image + vector));
    wr32(image + vector, be32(image + contrl + CONTRL_POINTER_A));
}

/* $fca6a4 — vex_timv (118). The one exchange made with interrupts MASKED (`ori.w #$700,sr` round
 * the two moves), because the 200 Hz tick calls through USER_TIM. Then BIOS `Tickcal` through the ROM's own
 * `trap #13` on target (the core directly off it), its LOW WORD answered in intout[0] — and contrl[4]
 * is NOT set: the dispatcher's clear stands, so a caller is told no words came back. */
void vdi_vex_timv(uint8_t *image)
{
    os_ipl_t mask = os_ipl_raise();
    uint32_t period;

    exchange_vector(image, LINEA_USER_TIM);
    os_ipl_restore(mask);
#ifdef RECREATE_HOST_DIFFERENTIAL
    period = bios_tickcal(image);
#else
    period = bios_trap_plain(BIOS_TICKCAL_FN);
#endif
    answer_intout(image, 0, (uint16_t)period);
}

/* $fcff68 / $fcff80 / $fcff98 — vex_butv (125), vex_motv (126), vex_curv (127): the same exchange
 * UNMASKED, though the mouse interrupt calls through all three. */
void vdi_vex_butv(uint8_t *image)
{
    exchange_vector(image, LINEA_USER_BUT);
}

void vdi_vex_motv(uint8_t *image)
{
    exchange_vector(image, LINEA_USER_MOT);
}

void vdi_vex_curv(uint8_t *image)
{
    exchange_vector(image, LINEA_USER_CUR);
}
