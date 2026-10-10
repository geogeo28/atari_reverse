/* gtext.c — GRAPHIC TEXT: v_gtext (opcode 8) and d_justified, the justified-text worker GDP 10 reaches.
 * Both Alcyon C in the ROM.
 *
 * v_gtext PLACES THE STRING, then draws it a glyph at a time:
 *
 *   * the effects' parameters out of the font into the Line-A variables TextBlt reads (bold's weight, the
 *     lighten mask, italic's two offsets and skew mask), and the form;
 *   * an OFFSET from ptsin[0] to the string's reference corner — along it by the horizontal alignment (the
 *     string's width from vqt_extent, halved or whole) and italic's lean, across it by the vertical one
 *     (a font line: top, half, ascent, bottom, descent);
 *   * the first glyph's corner for the rotation, and where the underline starts and which way it grows;
 *   * each character through TextBlt — '?' for one the font does not have — which moves DESTX/DESTY past
 *     it; justified text adds its gaps (`vdi/gtext.h`) and a font with a HOR table its byte of offset;
 *   * the underline, as WS's UL_SIZE lines of $a003, clipped one by one when CLIP is on.
 *
 * A plain string — no effect, left-aligned, not turned, unscaled, in a monospaced font eight pixels a cell
 * — goes to the fast path ($fcf96a) instead, which may refuse it and leave it to the loop.
 *
 * WHAT THE ROM LEAVES UNSET. Past the last alignment the ROM names (H_ALIGN over 2, V_ALIGN over 5) the
 * offset is a frame word never written, and a rotation that is not a right angle leaves DESTX/DESTY as they
 * were and the underline's start and steps unwritten: stack garbage in the ROM, 0 here. vst_alignment clamps
 * both alignments, and the dispatcher re-copies $1702/$1704 from the workstation record before every call, so
 * only a program poking the RECORD's WS_H_ALIGN / WS_V_ALIGN reaches the first; a rotation of 3600
 * (vst_rotation rounds 3150 up to it) reaches the second, and draws where the last text stopped — only its
 * UNDERLINE reads the unwritten words.
 *
 * THE ORDER of every store is the ROM's: the caller's arrays may overlap the Line-A variables and the VDI's
 * scratch words, and the ROM re-reads INTIN, CUR_FONT and the scratch after each glyph.
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "host_slot.h"
#include "m68k_idioms.h"
#include "stack_diet.h"
#include "vdi/vdi.h"
#include "vdi/font.h"
#include "vdi/helpers.h"
#include "vdi/fill.h"
#include "vdi/raster.h"
#include "vdi/text.h"
#include "vdi/text_raster.h"
#include "vdi/gtext.h"

/* The frame word that refuses the fast path when nonzero: the style, alignment and rotation OR-ed, or all
 * ones for justified text ($fcd78c `move.w #-1`). */
#define REFUSE_FAST_PATH      0xffffu
/* The one cell width the fast path draws ($fcdb9a `cmpi.w #8,52(a5)`). */
#define FAST_CELL_WIDTH       (1 << TEXT_FAST_GLYPH_SHIFT)
/* An outlined glyph is a pixel bigger each side, which moves every corner by one ($fcd7fa move.w #1). */
#define OUTLINE_BORDER        1
/* A turn or a half turn places the glyph past its reference pixel, not on it ($fcda7e `addq.w #1`). */
#define PAST_THE_REFERENCE    1
/* Where the underline starts below the cell's top, as the font leaves it ($fcd838 `move.w #1`), for a font
 * of the system face whose underline is as thick as its bottom (0, $fcd832), and that font doubled (-1). */
#define UNDERLINE_BELOW       1
#define UNDERLINE_ON_BOTTOM   0
#define UNDERLINE_DOUBLED     (-1)
/* The underline's rows are drawn in the LN_MASK of a solid line, or the font's lighten mask ($fcdd72). */
#define UNDERLINE_SOLID       0xffffu
/* The rotation whose multiples draw the underline along x ($fcdd24 `divs.w #1800`). */
#define HALF_TURN             TEXT_ROTATION_180
/* The alignments, by the dispatcher's copies' values (vst_alignment's range, $fce406 / $fce41c). */
enum horizontal_alignment { ALIGN_LEFT, ALIGN_CENTRE, ALIGN_RIGHT };
enum vertical_alignment { ALIGN_BASELINE, ALIGN_HALF, ALIGN_ASCENT, ALIGN_BOTTOM, ALIGN_DESCENT, ALIGN_TOP };

/* What the placement leaves for the drawing and the underline — v_gtext's frame words. */
struct placement {
    int16_t outline;          /* -18: OUTLINE_BORDER or 0                                          */
    int16_t underline_drop;   /* -20                                                               */
    int16_t along;            /* -30: the reference corner's offset along the text                 */
    int16_t across;           /* -32: ...and across it, from the cell's top                        */
    int16_t line_x, line_y;   /* -10, -12: the underline's first row                               */
    int16_t step_x, step_y;   /* -14, -16: ...and the step to the next                             */
};

/* ---- the placement ------------------------------------------------------------------------------ */

/* The effects' parameters TextBlt reads, taken from the font for each effect STYLE asks for — italic's
 * offsets cleared when it does not ($fcd79c..$fcd7ea). */
static void take_effects(uint8_t *image, uint32_t font)
{
    if (style_asks_for(image, VDI_STYLE_THICKEN_MASK))
        set_ram_word(image, LINEA_WEIGHT, font_word(image, font, FONT_THICKEN));
    if (style_asks_for(image, VDI_STYLE_LIGHTEN_MASK))
        set_ram_word(image, LINEA_LITEMASK, font_word(image, font, FONT_LIGHTEN));
    if (style_asks_for(image, VDI_STYLE_SKEW_MASK)) {
        set_ram_word(image, LINEA_L_OFF, font_word(image, font, FONT_LEFT_OFFSET));
        set_ram_word(image, LINEA_R_OFF, font_word(image, font, FONT_RIGHT_OFFSET));
        set_ram_word(image, LINEA_SKEWMASK, font_word(image, font, FONT_SKEW));
    } else {
        set_ram_word(image, LINEA_L_OFF, 0);
        set_ram_word(image, LINEA_R_OFF, 0);
    }
}

/* $fcd806: UNSIGNED, the bottom against the underline's thickness; the doubling marker is DDA_INC's -1. */
static int16_t underline_drop(const uint8_t *image, uint32_t font)
{
    if (font_word(image, font, FONT_ID) != FONT_SYSTEM_FACE
        || font_word(image, font, FONT_BOTTOM) > font_word(image, font, FONT_UL_SIZE))
        return UNDERLINE_BELOW;
    if (ram_uword(image, LINEA_SCALE) && ram_uword(image, LINEA_DDA_INC) == VDI_DDA_DOUBLE)
        return UNDERLINE_DOUBLED;
    return UNDERLINE_ON_BOTTOM;
}

/* The string's width into VDI_EXTENT_SCRATCH: vqt_extent answers its corners into a frame of ours, which
 * LINEA_PTSOUT names for the call, and contrl[2] is put back to 0 after it ($fcd870..$fcd894). */
static void measure(uint8_t *image)
{
    int16_t corners_local[VDI_EXTENT_ANSWER_POINTS * VDI_POINT_WORDS];
    uint32_t ptsout = linea_pointer(image, LINEA_PTSOUT);

    _Static_assert(sizeof corners_local == HOST_SLOT_VDI_GTEXT_EXTENT_BYTES, "four points");
    wr32(image + LINEA_PTSOUT, host_slot_claim(VDI_GTEXT_EXTENT, corners_local));
    vdi_vqt_extent(image);
    host_slot_release(VDI_GTEXT_EXTENT);
    wr32(image + LINEA_PTSOUT, ptsout);
    answer_points(image, 0);
}

/* $fcd858: the offset along the text for H_ALIGN. Justified text has its length in the scratch word already
 * (d_justified stored it), so it is not measured again. */
static int16_t horizontal_offset(uint8_t *image, int justified, int16_t outline)
{
    switch (ram_word(image, VDI_TEXT_H_ALIGN)) {
    case ALIGN_LEFT:
        return 0;
    case ALIGN_CENTRE:
        if (!justified)
            measure(image);
        return (int16_t)(ram_word(image, VDI_EXTENT_SCRATCH) / 2 - outline);
    case ALIGN_RIGHT:
        if (!justified)
            measure(image);
        return (int16_t)(ram_word(image, VDI_EXTENT_SCRATCH) - 2 * outline);
    default:
        return 0;
    }
}

/* The LOW WORD of a 16 x 16 product, all that a `mulu.w` / `muls.w` the ROM keeps a word of leaves — the same
 * word signed or not. Spelt unsigned because GCC then emits the one multiply; a signed product it can see only
 * a word of is taken through `__mulsi3` (measured). */
static inline uint16_t product_low_word(uint16_t left, uint16_t right)
{
    return (uint16_t)((uint32_t)left * right);
}

/* An italic's lean at a font line `rows` from the top of a glyph `height` tall: `mulu.w` keeping the product's
 * LOW word, then `divu.w` ($fcd950..$fcd960). */
static int16_t lean(uint16_t rows, uint16_t offset, uint16_t height)
{
    return quotient_word(m68k_divu_w(product_low_word(rows, offset), height));
}

/* $fcd906: the offset across the text for V_ALIGN — from the cell's top to the font line named — and the
 * italic's lean that line moves the offset along by. */
static void vertical_offset(const uint8_t *image, uint32_t font, struct placement *place)
{
    int skewed = style_asks_for(image, VDI_STYLE_SKEW_MASK);
    uint16_t left = skewed ? font_word(image, font, FONT_LEFT_OFFSET) : 0;
    uint16_t right = skewed ? font_word(image, font, FONT_RIGHT_OFFSET) : 0;
    uint16_t top = font_word(image, font, FONT_TOP);

    switch (ram_word(image, VDI_TEXT_V_ALIGN)) {
    case ALIGN_BASELINE:
        place->across = (int16_t)top;
        place->along = (int16_t)(place->along + left);
        break;
    case ALIGN_HALF:
        place->across = (int16_t)(top - font_word(image, font, FONT_HALF));
        place->along = (int16_t)(place->along + lean(font_word(image, font, FONT_HALF), right, top));
        break;
    case ALIGN_ASCENT:
        place->across = (int16_t)(top - font_word(image, font, FONT_ASCENT));
        place->along = (int16_t)(place->along + lean(font_word(image, font, FONT_ASCENT), right, top));
        break;
    case ALIGN_BOTTOM:
        place->across = (int16_t)(top + font_word(image, font, FONT_BOTTOM));
        break;
    case ALIGN_DESCENT:
        place->across = (int16_t)(top + font_word(image, font, FONT_DESCENT));
        place->along = (int16_t)(place->along + lean(font_word(image, font, FONT_DESCENT), left,
                                                     font_word(image, font, FONT_BOTTOM)));
        break;
    case ALIGN_TOP:
        place->across = 0;
        place->along = (int16_t)(place->along + left + right);
        break;
    default:
        break;
    }
}

/* The underline's start and step, for a turned string: the row it starts on and the direction it grows. */
static void underline_from(struct placement *place, int16_t x, int16_t y, int16_t step_x, int16_t step_y)
{
    place->line_x = x;
    place->line_y = y;
    place->step_x = step_x;
    place->step_y = step_y;
}

/* How far the underline's first row lies past the cell's top line or short of its bottom one: the font's
 * UL_SIZE and the drop. */
static int16_t underline_offset(const uint8_t *image, uint32_t font, const struct placement *place)
{
    return (int16_t)(font_word(image, font, FONT_UL_SIZE) + place->underline_drop);
}

/* The cell's height less one, top line to bottom line: what a half or three-quarter turn places by. */
static uint16_t cell_extent(const uint8_t *image, uint32_t font)
{
    return (uint16_t)(font_word(image, font, FONT_TOP) + font_word(image, font, FONT_BOTTOM));
}

/* $fcda0a: the first glyph's corner (DESTX, DESTY) for the rotation, from ptsin[0] less the offsets, and the
 * underline's first row a cell's height and the underline's drop away from it. Every word is read in the
 * ROM's order, after the stores before it: ptsin's y after DESTX, and the font's lines (a header may overlap
 * DESTX/DESTY) where each arm reads them. */
static void place_origin(uint8_t *image, uint32_t font, struct placement *place)
{
    const uint8_t *ptsin = image + linea_pointer(image, LINEA_PTSIN);
    int16_t x, y, line;

    switch (ram_word(image, LINEA_CHUP)) {
    case 0:
        x = (int16_t)(be16(ptsin) - place->along - place->outline);
        set_ram_word(image, LINEA_DESTX, (uint16_t)x);
        y = (int16_t)(be16(ptsin + VDI_POINT_Y) - place->across - place->outline);
        set_ram_word(image, LINEA_DESTY, (uint16_t)y);
        underline_from(place, x, (int16_t)(y + font_word(image, font, FONT_TOP) + underline_offset(image, font, place)),
                       0, 1);
        break;
    case TEXT_ROTATION_90:
        x = (int16_t)(be16(ptsin) - place->across - place->outline);
        set_ram_word(image, LINEA_DESTX, (uint16_t)x);
        line = (int16_t)(x + font_word(image, font, FONT_TOP) + underline_offset(image, font, place));
        y = (int16_t)(be16(ptsin + VDI_POINT_Y) + place->along + place->outline + PAST_THE_REFERENCE);
        set_ram_word(image, LINEA_DESTY, (uint16_t)y);
        underline_from(place, line, y, 1, 0);
        break;
    case TEXT_ROTATION_180:
        x = (int16_t)(be16(ptsin) + place->along + place->outline + PAST_THE_REFERENCE);
        set_ram_word(image, LINEA_DESTX, (uint16_t)x);
        y = (int16_t)(be16(ptsin + VDI_POINT_Y) - (cell_extent(image, font) - place->across) - place->outline);
        set_ram_word(image, LINEA_DESTY, (uint16_t)y);
        underline_from(place, x, (int16_t)(font_word(image, font, FONT_BOTTOM) + y - underline_offset(image, font, place)),
                       0, -1);
        break;
    case TEXT_ROTATION_270:
        x = (int16_t)(be16(ptsin) - (cell_extent(image, font) - place->across) - place->outline);
        set_ram_word(image, LINEA_DESTX, (uint16_t)x);
        line = (int16_t)(font_word(image, font, FONT_BOTTOM) + x - underline_offset(image, font, place));
        y = (int16_t)(be16(ptsin + VDI_POINT_Y) - place->along - place->outline);
        set_ram_word(image, LINEA_DESTY, (uint16_t)y);
        underline_from(place, line, y, -1, 0);
        break;
    default:
        break;
    }
}

/* $fcdb84: the fast path takes an unscaled string nothing refuses, in a monospaced font of 8-pixel cells. */
static int fast_shape(const uint8_t *image, uint32_t font, uint16_t refusal)
{
    return !ram_uword(image, LINEA_SCALE) && !refusal && font_flag(image, font, FONT_FLAG_MONOSPACE_MASK)
           && font_word(image, font, FONT_MAX_CELL_WIDTH) == FAST_CELL_WIDTH;
}

/* ---- the glyphs --------------------------------------------------------------------------------- */

/* One gap of justified text taken: its step, and one pixel more while its count lasts ($fcdc46..$fcdcce). */
static void take_gap(uint8_t *image, uint32_t gap)
{
    add_ram_word(image, LINEA_DESTX, ram_uword(image, gap + VDI_GAP_STEP_X));
    add_ram_word(image, LINEA_DESTY, ram_uword(image, gap + VDI_GAP_STEP_Y));
    if (ram_word(image, gap + VDI_GAP_EXTRA)) {
        add_ram_word(image, LINEA_DESTX, ram_uword(image, gap + VDI_GAP_EXTRA_X));
        add_ram_word(image, LINEA_DESTY, ram_uword(image, gap + VDI_GAP_EXTRA_Y));
        add_ram_word(image, gap + VDI_GAP_EXTRA, (uint16_t)-1);
    }
}

/* intin[`index`], through the pointer as it stands. */
static uint16_t character_at(const uint8_t *image, int16_t index)
{
    return be16(image + call_element(image, LINEA_INTIN, (unsigned)index));
}

/* $fcdbbe: character `index` as a glyph of the font — its column of the form in SOURCEX, its width the next
 * offset less SOURCEX READ BACK — and TextBlt. Answers the glyph's index, from the font's first character:
 * UNSIGNED bounds, and the offset table indexed by it SIGN-EXTENDED (`movea.w`), in 32 bits. */
static uint16_t draw_glyph(uint8_t *image, uint32_t font, int16_t index)
{
    uint16_t glyph = character_at(image, index);
    uint32_t entry;

    if (glyph < font_word(image, font, FONT_FIRST_ADE) || glyph > font_word(image, font, FONT_LAST_ADE))
        glyph = VDI_TEXT_MISSING_CHARACTER;
    glyph = (uint16_t)(glyph - font_word(image, font, FONT_FIRST_ADE));
    entry = font_offset_entry(font_long(image, font, FONT_OFF_TABLE), glyph);
    set_ram_word(image, LINEA_SOURCEX, be16(image + bus_dereference(entry)));
    set_ram_word(image, LINEA_DELX,
                 (uint16_t)(be16(image + bus_dereference(entry + VDI_WORD_BYTES)) - ram_uword(image, LINEA_SOURCEX)));
    set_ram_word(image, LINEA_SOURCEY, 0);
    set_ram_word(image, LINEA_DELY, font_word(image, font, FONT_FORM_HEIGHT));
    linea_textblt(image);
    return glyph;
}

/* $fcdbae: every character, the scaler's accumulator started half full. The FIRST glyph is drawn in `font`,
 * the one v_gtext loaded at its entry (A5, $fcd76e); CUR_FONT is read again only after each TextBlt
 * ($fcdc38), and that is the font the gaps, the HOR table and the next glyph use. Justified text takes its gaps
 * (a space's after the character's); a font with a HOR table moves DESTX by the glyph's SIGNED BYTE of it —
 * one byte a glyph, the index sign-extended ($fcdcdc). */
static void draw_string(uint8_t *image, uint32_t font, int16_t count, int justified)
{
    set_ram_word(image, LINEA_XACC_DDA, VDI_DDA_ACCUMULATOR_START);
    for (int16_t index = 0; index < count; index++) {
        uint16_t glyph = draw_glyph(image, font, index);

        font = linea_pointer(image, LINEA_CUR_FONT);
        if (justified) {
            take_gap(image, VDI_GAP_AFTER_CHARACTER);
            if (character_at(image, index) == VDI_TEXT_SPACE)
                take_gap(image, VDI_GAP_AFTER_SPACE);
        }
        if (font_flag(image, font, FONT_FLAG_HOR_TABLE_MASK))
            add_ram_word(image, LINEA_DESTX, (uint16_t)sign_ext8(
                image[bus_dereference(font_long(image, font, FONT_HOR_TABLE) + sign_ext16(glyph))]));
    }
}

/* ---- the underline ------------------------------------------------------------------------------ */

/* One row of the underline through $a003, clipped first when CLIP is on — with the end points the clip cut
 * put back after it, so the next row steps from the uncut ones ($fcddd6..$fcde1e). */
static void underline_row(uint8_t *image)
{
    int16_t x1, x2, y1, y2;

    if (!ram_uword(image, LINEA_CLIP)) {
        linea_line(image);
        return;
    }
    x1 = ram_word(image, LINEA_X1);
    x2 = ram_word(image, LINEA_X2);
    y1 = ram_word(image, LINEA_Y1);
    y2 = ram_word(image, LINEA_Y2);
    if (vdi_clip_line(image))
        linea_line(image);
    set_ram_word(image, LINEA_X1, (uint16_t)x1);
    set_ram_word(image, LINEA_X2, (uint16_t)x2);
    set_ram_word(image, LINEA_Y1, (uint16_t)y1);
    set_ram_word(image, LINEA_Y2, (uint16_t)y2);
}

/* LN_MASK moved on a row: `asr.w #1`, with bit 15 SET when bit 0 was — so a mask with its top bit set keeps
 * it, which is not a rotation ($fcde56..$fcde7c). */
static void next_row_mask(uint8_t *image)
{
    uint16_t shifted = (uint16_t)((int16_t)ram_uword(image, LINEA_LN_MASK) >> 1);

    set_ram_word(image, LINEA_LN_MASK, ram_uword(image, LINEA_LN_MASK) & 1 ? shifted | SIGN_BIT16 : shifted);
}

/* $fcdd0c: the underline from its first row to where the string ended (DESTX or DESTY), UL_SIZE rows of the
 * text colour, each a step further on — in the lighten mask when the text is lightened. */
static void underline(uint8_t *image, const struct placement *place)
{
    int16_t rows;

    set_ram_word(image, LINEA_X1, (uint16_t)place->line_x);
    set_ram_word(image, LINEA_Y1, (uint16_t)place->line_y);
    if (ram_word(image, LINEA_CHUP) % HALF_TURN == 0) {
        set_ram_word(image, LINEA_X2, ram_uword(image, LINEA_DESTX));
        set_ram_word(image, LINEA_Y2, ram_uword(image, LINEA_Y1));
    } else {
        set_ram_word(image, LINEA_X2, ram_uword(image, LINEA_X1));
        set_ram_word(image, LINEA_Y2, ram_uword(image, LINEA_DESTY));
    }
    set_ram_word(image, LINEA_LN_MASK, style_asks_for(image, VDI_STYLE_LIGHTEN_MASK)
                                           ? font_word(image, linea_pointer(image, LINEA_CUR_FONT), FONT_LIGHTEN)
                                           : UNDERLINE_SOLID);
    set_colour_bits(image, ram_uword(image, LINEA_TEXT_FG));
    rows = (int16_t)font_word(image, linea_pointer(image, LINEA_CUR_FONT), FONT_UL_SIZE);
    for (int16_t row = 0; row < rows; row++) {
        underline_row(image);
        add_ram_word(image, LINEA_X1, (uint16_t)place->step_x);
        add_ram_word(image, LINEA_X2, (uint16_t)place->step_x);
        add_ram_word(image, LINEA_Y1, (uint16_t)place->step_y);
        add_ram_word(image, LINEA_Y2, (uint16_t)place->step_y);
        next_row_mask(image);
    }
}

/* ================================================================================================
 * $fcd756 — v_gtext (8): contrl[3] characters of intin at ptsin[0], in the current font, effects, alignment
 * and rotation. Nothing for a count of 0 or less.
 * ============================================================================================= */

/* Everything past the count test. Out of line so an empty string returns before any of its registers are saved:
 * with it inlined, the prologue alone put the empty string's row at 1.71 (measured, Tier 3).
 * ON A DIET (`stack_diet.h`): this frame stands under the text blit on whichever stack the `trap #2` was taken — the
 * screen manager's 1,196 bytes, where a text drawn for an icon in a menu is the deepest any call goes
 * (`test/aes_stack.py`): 76 bytes held over the blit without the mark, 64 with it. */
FRAME_DIET("no-function-cse", "no-gcse", "no-caller-saves")
static __attribute__((noinline)) void place_and_draw(uint8_t *image, int16_t count)
{
    struct placement place = { 0 };
    uint32_t font = linea_pointer(image, LINEA_CUR_FONT);
    int justified = contrl_word(image, CONTRL_OPCODE) == VDI_ROM_GDP_OPCODE;
    uint16_t refusal = justified ? REFUSE_FAST_PATH : ram_uword(image, LINEA_STYLE);

    take_effects(image, font);
    place.outline = style_asks_for(image, VDI_STYLE_OUTLINE_MASK) ? OUTLINE_BORDER : 0;
    place.underline_drop = underline_drop(image, font);
    wr32(image + LINEA_FBASE, font_long(image, font, FONT_DAT_TABLE));
    set_ram_word(image, LINEA_FWIDTH, font_word(image, font, FONT_FORM_WIDTH));
    refusal |= ram_uword(image, VDI_TEXT_H_ALIGN);
    place.along = horizontal_offset(image, justified, place.outline);
    vertical_offset(image, font, &place);
    refusal |= ram_uword(image, LINEA_CHUP);
    place_origin(image, font, &place);
    set_ram_word(image, LINEA_TEXT_FG, current_work_word(image, WS_TEXT_COLOR));
    set_ram_word(image, LINEA_DELY, font_word(image, font, FONT_FORM_HEIGHT));
    if (fast_shape(image, font, refusal) && (uint16_t)linea_fast_text(image))
        return;
    draw_string(image, font, count, justified);
    if (style_asks_for(image, VDI_STYLE_UNDERLINE_MASK))
        underline(image, &place);
}

void vdi_v_gtext(uint8_t *image)
{
    int16_t count = contrl_word(image, CONTRL_N_INTIN);

    if (count > 0)
        place_and_draw(image, count);
}

/* ================================================================================================
 * $fce9e8 — d_justified: GDP 10's string — intin[0] a flag for spacing the words, intin[1] for spacing the
 * characters, the text from intin[2] — spread over ptsin[2] pixels and drawn by v_gtext.
 *
 * It MEASURES the text (vqt_extent into a frame of its own, contrl[3] less the two flags, INTIN moved past
 * them) and splits the SLACK — the length asked for less the text's width — over the gaps: between the words
 * (after each space) when their flag is set and there is a space, and between the characters when theirs is
 * and there are two. Spacing both, the word gap is held within half the font's widest cell either way, and
 * what it takes is taken off the characters' slack. The gaps go into the two records v_gtext walks, turned
 * for the rotation (a rotation that is not a right angle leaves them as they were), and the width v_gtext
 * aligns by becomes the length asked for.
 *
 * WHAT IT PUTS BACK: INTIN and PTSOUT. contrl[3] is LEFT at the count less two, and the count it came with
 * is written into contrl[2] ($fcece6 `4(a0)`) — the words the GDP's caller reads back as points answered.
 * ============================================================================================= */
#define JUSTIFY_FLAG_WORDS    2          /* intin[0] and [1], ahead of the text ($fcea0c, $fcea10) */
#define LENGTH_WORD           2          /* ptsin[2]: the length asked for     ($fcea62 `4(a0)`) */
#define UNIT_BACKWARD         (-1)       /* ($fceaa8 `moveq #-1`)                                   */
#define UNIT_FORWARD          1          /* ($fceaba `moveq #1`)                                    */

/* `slack` over `gaps`: each gap's step (the quotient, `divs.w`), and the remainder into the record's count of
 * gaps a pixel wider — made positive IN MEMORY, the pixel's direction answered in `unit`. */
static int16_t split_slack(uint8_t *image, uint32_t gap, int16_t slack, int16_t gaps, int16_t *unit)
{
    uint32_t divided = m68k_divs_w((uint32_t)(int32_t)slack, (uint16_t)gaps);

    set_ram_word(image, gap + VDI_GAP_EXTRA, (uint16_t)remainder_word(divided));
    if (ram_word(image, gap + VDI_GAP_EXTRA) < 0) {
        *unit = UNIT_BACKWARD;
        set_ram_word(image, gap + VDI_GAP_EXTRA, (uint16_t)-ram_word(image, gap + VDI_GAP_EXTRA));
    } else {
        *unit = UNIT_FORWARD;
    }
    return quotient_word(divided);
}

/* The record's steps, turned for LINEA_CHUP: x, y, then the extra pixel's x, y ($fceb1c..$fceb94). */
static void turn_gap(uint8_t *image, uint32_t gap, int16_t step, int16_t unit)
{
    int16_t x, y, extra_x, extra_y;

    switch (ram_word(image, LINEA_CHUP)) {
    case 0:                 x = step;  y = 0;     extra_x = unit;  extra_y = 0;     break;
    case TEXT_ROTATION_90:  x = 0;     y = -step; extra_x = 0;     extra_y = -unit; break;
    case TEXT_ROTATION_180: x = -step; y = 0;     extra_x = -unit; extra_y = 0;     break;
    case TEXT_ROTATION_270: x = 0;     y = step;  extra_x = 0;     extra_y = unit;  break;
    default:                return;
    }
    set_ram_word(image, gap + VDI_GAP_STEP_X, (uint16_t)x);
    set_ram_word(image, gap + VDI_GAP_STEP_Y, (uint16_t)y);
    set_ram_word(image, gap + VDI_GAP_EXTRA_X, (uint16_t)extra_x);
    set_ram_word(image, gap + VDI_GAP_EXTRA_Y, (uint16_t)extra_y);
}

/* A gap kind not spread: no step, no extra pixel ($fcebb0). */
static void close_gap(uint8_t *image, uint32_t gap)
{
    set_ram_word(image, gap + VDI_GAP_STEP_X, 0);
    set_ram_word(image, gap + VDI_GAP_STEP_Y, 0);
    set_ram_word(image, gap + VDI_GAP_EXTRA, 0);
}

/* The slack as the ROM takes it each time: the length less the width summed in the scratch, a word. */
static int16_t slack_of(const uint8_t *image, int16_t length)
{
    return (int16_t)(length - ram_word(image, VDI_EXTENT_SCRATCH));
}

/* $fcea78: the word gaps' step, held within half the widest cell when the characters are spread too (their
 * extra pixels dropped with a cut), and what the words take then added to the width the characters' slack is
 * measured from — two `muls.w`, a word kept of each. */
static void spread_words(uint8_t *image, int16_t length, int16_t spaces, int characters_too)
{
    int16_t unit, step = split_slack(image, VDI_GAP_AFTER_SPACE, slack_of(image, length), spaces, &unit);

    if (characters_too) {
        int16_t limit = (int16_t)(font_word(image, linea_pointer(image, LINEA_CUR_FONT), FONT_MAX_CELL_WIDTH) >> 1);

        if (step > limit) {
            step = limit;
            set_ram_word(image, VDI_GAP_AFTER_SPACE + VDI_GAP_EXTRA, 0);
        }
        if (step < -limit) {
            step = (int16_t)-limit;
            set_ram_word(image, VDI_GAP_AFTER_SPACE + VDI_GAP_EXTRA, 0);
        }
        add_ram_word(image, VDI_EXTENT_SCRATCH,
                     (uint16_t)(product_low_word((uint16_t)step, (uint16_t)spaces)
                                + product_low_word((uint16_t)unit, ram_uword(image, VDI_GAP_AFTER_SPACE + VDI_GAP_EXTRA))));
    }
    turn_gap(image, VDI_GAP_AFTER_SPACE, step, unit);
}

/* $fcebd4: the character gaps' step — what is left of the slack over the `count - 1` gaps. */
static void spread_characters(uint8_t *image, int16_t length, int16_t count)
{
    int16_t unit, step = split_slack(image, VDI_GAP_AFTER_CHARACTER, slack_of(image, length), (int16_t)(count - 1), &unit);

    turn_gap(image, VDI_GAP_AFTER_CHARACTER, step, unit);
}

/* The spaces among the `count` characters from `text` ($fcea3c). */
static int16_t spaces_in(const uint8_t *image, uint32_t text, int16_t count)
{
    int16_t spaces = 0;

    for (int16_t index = 0; index < count; index++, text += VDI_WORD_BYTES)
        if (be16(image + text) == VDI_TEXT_SPACE)
            spaces++;
    return spaces;
}

void vdi_d_justified(uint8_t *image)
{
    uint8_t *count_word = image + linea_pointer(image, LINEA_CONTRL) + CONTRL_N_INTIN;    /* one `movea.l` */
    int16_t given = (int16_t)be16(count_word), count = (int16_t)(given - JUSTIFY_FLAG_WORDS);
    uint32_t intin, ptsout, text;
    int16_t space_words, space_characters, spaces, length;
    int16_t corners_local[VDI_EXTENT_ANSWER_POINTS * VDI_POINT_WORDS];

    _Static_assert(sizeof corners_local == HOST_SLOT_VDI_JUSTIFIED_EXTENT_BYTES, "four points");
    wr16(count_word, (uint16_t)count);
    text = linea_pointer(image, LINEA_INTIN);
    space_words = ram_word(image, text);
    space_characters = ram_word(image, text + VDI_WORD_BYTES);
    text += JUSTIFY_FLAG_WORDS * VDI_WORD_BYTES;
    intin = linea_pointer(image, LINEA_INTIN);
    wr32(image + LINEA_INTIN, text);
    ptsout = linea_pointer(image, LINEA_PTSOUT);
    wr32(image + LINEA_PTSOUT, host_slot_claim(VDI_JUSTIFIED_EXTENT, corners_local));
    spaces = spaces_in(image, text, count);
    vdi_vqt_extent(image);
    answer_points(image, 0);
    length = ptsin_word(image, LENGTH_WORD);
    if (space_words && spaces)
        spread_words(image, length, spaces, space_characters);
    else
        close_gap(image, VDI_GAP_AFTER_SPACE);
    if (space_characters && count > 1)
        spread_characters(image, length, count);
    else
        close_gap(image, VDI_GAP_AFTER_CHARACTER);
    set_ram_word(image, VDI_EXTENT_SCRATCH, (uint16_t)length);
    vdi_v_gtext(image);
    host_slot_release(VDI_JUSTIFIED_EXTENT);
    set_contrl_word(image, CONTRL_N_PTSOUT, (uint16_t)given);
    wr32(image + LINEA_PTSOUT, ptsout);
    wr32(image + LINEA_INTIN, intin);
}
