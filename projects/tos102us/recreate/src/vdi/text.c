/* text.c — the VDI's TEXT LAYER in C: the font ring's set-up (`text_init`), the scaled header
 * (`make_header`), the size and face setters (vst_height, vst_point, vst_font), the two measuring
 * inquiries (vqt_extent, vqt_width) and the GDOS font loader (vst_load_fonts). All Alcyon C in the ROM.
 *
 * THE RING WALK is shared by every setter: slot by slot until a zero slot, each slot a chain through
 * FONT_NEXT. vst_height and vst_point go on walking the slots AFTER the one their font was found in,
 * so a face split across slots is one run of sizes.
 *
 * A FONT THE RING DOES NOT HOLD is not an error to them. vst_unload_fonts leaves WS_CUR_FONT naming a
 * loaded font the ring no longer reaches; vst_height and vst_point then take the header at ADDRESS 0
 * (the vector table) as their font, and a chain on from there follows vector longwords whose high
 * bytes are not zero — which is why every header here is reached through `bus_dereference`, as the
 * 68000's 24-bit bus reaches it. vst_font falls back to the ROM 6x6 instead.
 *
 * THE ORDER of every store is the ROM's, because the arrays a caller hands in may overlap each other,
 * the workstation, and the VDI's scratch words — vqt_extent adds into VDI_EXTENT_SCRATCH in memory and
 * reads it back for every answer.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "host_slot.h"
#include "vdi/vdi.h"
#include "vdi/font.h"
#include "vdi/helpers.h"
#include "vdi/text.h"
#include "vdi/text_raster.h"

/* FONT_FLAGS' LOW byte, which is what every `btst` on the flags reads (`btst #n,67(a5)`). */
static inline int font_flag(const uint8_t *image, uint32_t font, uint16_t mask)
{
    return (font_word(image, font, FONT_FLAGS) & mask) != 0;
}

/* ---- the ring ------------------------------------------------------------------------------------ */
/* The slot the cursor is at, and the cursor moved past it (`movea.l (a4)+,a5`). */
static uint32_t next_slot(const uint8_t *image, uint32_t *slot)
{
    uint32_t font = be32(image + *slot);

    *slot += VDI_LONG_BYTES;
    return font;
}

/* The first font of face `face` from the slot at `*slot` on, the cursor left past its slot — or 0, with
 * the cursor past the first zero slot, when there is none. */
static uint32_t first_of_face(const uint8_t *image, uint16_t face, uint32_t *slot)
{
    uint32_t font;

    while ((font = next_slot(image, slot)) != 0)
        for (; font != 0; font = font_long(image, font, FONT_NEXT))
            if (font_word(image, font, FONT_ID) == face)
                return font;
    return 0;
}

static void set_current_font(uint8_t *image, uint32_t font)
{
    wr32(image + LINEA_CUR_FONT, font);
    wr32(image + current_work(image) + WS_CUR_FONT, font);
}

/* The four points both size setters answer for the font they settled on (`answer_font_size`), and the
 * result flag after them. Out of line, as GCC placed it before the points became a shared helper — with the
 * attribute the objects are unchanged by the move (compared). */
#define SIZE_ANSWER_POINTS FONT_SIZE_ANSWER_POINTS

static __attribute__((noinline)) void answer_size(uint8_t *image, uint32_t font)
{
    answer_font_size(image, font);
    wr16(image + VDI_RESULT, VDI_RESULT_SET);
}

/* ================================================================================================
 * $fcde9c — text_init: the ring's fixed slots, and what the fonts in it tell the device tables.
 *
 * Slot 0 becomes the ROM 6x6 and slots 2 and 3 are emptied, so the walk covers the 6x6 and whatever
 * chain v_opnwk left in slot 1. Along it: the LAST font flagged default becomes DEF_FONT; each change
 * of id is one more face; each font of the system face widens SIZ_TAB's character sizes (UNSIGNED
 * compares, from a minimum of $7fff) and is one more character height; and a form not flagged in 68000
 * order is byte-swapped — WITHOUT setting the flag, so a second call would swap it back. The face count
 * starts from the 6x6's own id, read out of the ROM, and gains one at the end.
 * ============================================================================================= */
/* Each minimum starts at the largest word a SIGNED compare would keep ($fcdea4 `move.w #32767`), though
 * the compares are unsigned. */
#define SIZ_TAB_MIN_START     0x7fff

/* SIZ_TAB[`index`] replaced by the font's `field` when that is SMALLER (`bls` skips) — or, for a maximum,
 * LARGER (`bcc` skips). The field is read again for the store, as the ROM does. */
static void lower_size(uint8_t *image, unsigned index, uint32_t font, uint32_t field)
{
    if (table_uword(image, LINEA_SIZ_TAB, index) > font_word(image, font, field))
        set_table_word(image, LINEA_SIZ_TAB, index, font_word(image, font, field));
}

static void raise_size(uint8_t *image, unsigned index, uint32_t font, uint32_t field)
{
    if (table_uword(image, LINEA_SIZ_TAB, index) < font_word(image, font, field))
        set_table_word(image, LINEA_SIZ_TAB, index, font_word(image, font, field));
}

static void widen_character_sizes(uint8_t *image, uint32_t font)
{
    lower_size(image, VDI_SIZ_TAB_MIN_CHAR_WIDTH_INDEX, font, FONT_MAX_CHAR_WIDTH);
    lower_size(image, VDI_SIZ_TAB_MIN_CHAR_HEIGHT_INDEX, font, FONT_TOP);
    raise_size(image, VDI_SIZ_TAB_MAX_CHAR_WIDTH_INDEX, font, FONT_MAX_CHAR_WIDTH);
    raise_size(image, VDI_SIZ_TAB_MAX_CHAR_HEIGHT_INDEX, font, FONT_TOP);
}

/* The form of `font` byte-swapped by font_byteswap, which reads it through LINEA_FBASE/FWIDTH/DELY. */
static void swap_form(uint8_t *image, uint32_t font)
{
    wr32(image + LINEA_FBASE, font_long(image, font, FONT_DAT_TABLE));
    wr16(image + LINEA_FWIDTH, font_word(image, font, FONT_FORM_WIDTH));
    wr16(image + LINEA_DELY, font_word(image, font, FONT_FORM_HEIGHT));
    vdi_font_byteswap(image);
}

void vdi_text_init(uint8_t *image)
{
    uint32_t slot = LINEA_FONT_RING;
    uint32_t font;
    uint16_t previous_face = be16(image + FONT_ROM_6X6 + FONT_ID);
    uint16_t heights = 0, faces = 0;

    set_table_word(image, LINEA_SIZ_TAB, VDI_SIZ_TAB_MIN_CHAR_WIDTH_INDEX, SIZ_TAB_MIN_START);
    set_table_word(image, LINEA_SIZ_TAB, VDI_SIZ_TAB_MIN_CHAR_HEIGHT_INDEX, SIZ_TAB_MIN_START);
    set_table_word(image, LINEA_SIZ_TAB, VDI_SIZ_TAB_MAX_CHAR_WIDTH_INDEX, 0);
    set_table_word(image, LINEA_SIZ_TAB, VDI_SIZ_TAB_MAX_CHAR_HEIGHT_INDEX, 0);
    wr32(image + LINEA_FONT_RING + LINEA_FONT_RING_SYSTEM * VDI_LONG_BYTES, FONT_ROM_6X6);
    wr32(image + LINEA_FONT_RING + LINEA_FONT_RING_LOADED * VDI_LONG_BYTES, 0);
    wr32(image + LINEA_FONT_RING + (LINEA_FONT_RING_SLOTS - 1) * VDI_LONG_BYTES, 0);

    while ((font = next_slot(image, &slot)) != 0) {
        for (; font != 0; font = font_long(image, font, FONT_NEXT)) {
            uint16_t face;

            if (font_flag(image, font, FONT_FLAG_DEFAULT_MASK))
                wr32(image + LINEA_DEF_FONT, font);
            face = font_word(image, font, FONT_ID);
            if (face != previous_face) {
                faces++;
                previous_face = face;
            }
            if (font_word(image, font, FONT_ID) == FONT_SYSTEM_FACE) {
                widen_character_sizes(image, font);
                heights++;
            }
            if (!font_flag(image, font, FONT_FLAG_SWAPPED_MASK))
                swap_form(image, font);
        }
    }
    set_table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_CHAR_HEIGHTS_INDEX, heights);
    faces++;
    set_table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_FACES_INDEX, faces);
    wr16(image + LINEA_FONT_COUNT, faces);
    wr32(image + LINEA_CUR_FONT, be32(image + LINEA_DEF_FONT));
}

/* ================================================================================================
 * $fce116 — make_header: WS_CUR_FONT's header copied into the workstation's WS_SCRATCH_HEAD with every
 * size put through the text DDA, which then becomes the current font — WS_SCALED set.
 *
 * THE POINT SIZE IS DOUBLED whatever the DDA says (`asl.w #1`). Under the doubling marker the top,
 * ascent and half are doubled PLUS ONE (`lsl.w` / `addq.w #1`) and every other size is act_siz's
 * doubling. FONT_NEXT is not copied: the scratch header's link is whatever the record held.
 * ============================================================================================= */
static void scale_field(uint8_t *image, const uint8_t *from, uint8_t *to, uint32_t field)
{
    wr16(to + field, (uint16_t)vdi_act_siz(image, (int16_t)be16(from + field)));
}

static void double_field_plus_one(const uint8_t *from, uint8_t *to, uint32_t field)
{
    wr16(to + field, (uint16_t)((be16(from + field) << 1) + 1));
}

static void copy_word_field(const uint8_t *from, uint8_t *to, uint32_t field)
{
    wr16(to + field, be16(from + field));
}

static void copy_long_field(const uint8_t *from, uint8_t *to, uint32_t field)
{
    wr32(to + field, be32(from + field));
}

void vdi_make_header(uint8_t *image)
{
    uint32_t work = current_work(image);
    uint32_t font = be32(image + work + WS_CUR_FONT);
    uint32_t header = work + WS_SCRATCH_HEAD;
    const uint8_t *from = font_header(image, font);
    uint8_t *to = image + header;

    copy_word_field(from, to, FONT_ID);
    wr16(to + FONT_POINT, (uint16_t)(be16(from + FONT_POINT) << 1));
    vdi_copy_name(image, bus_dereference(font) + FONT_NAME, header + FONT_NAME);
    copy_word_field(from, to, FONT_FIRST_ADE);
    copy_word_field(from, to, FONT_LAST_ADE);
    if (be16(image + LINEA_DDA_INC) == VDI_DDA_DOUBLE) {
        double_field_plus_one(from, to, FONT_TOP);
        double_field_plus_one(from, to, FONT_ASCENT);
        double_field_plus_one(from, to, FONT_HALF);
    } else {
        scale_field(image, from, to, FONT_TOP);
        scale_field(image, from, to, FONT_ASCENT);
        scale_field(image, from, to, FONT_HALF);
    }
    scale_field(image, from, to, FONT_DESCENT);
    scale_field(image, from, to, FONT_BOTTOM);
    scale_field(image, from, to, FONT_MAX_CHAR_WIDTH);
    scale_field(image, from, to, FONT_MAX_CELL_WIDTH);
    scale_field(image, from, to, FONT_LEFT_OFFSET);
    scale_field(image, from, to, FONT_RIGHT_OFFSET);
    scale_field(image, from, to, FONT_THICKEN);
    scale_field(image, from, to, FONT_UL_SIZE);
    copy_word_field(from, to, FONT_LIGHTEN);
    copy_word_field(from, to, FONT_SKEW);
    copy_word_field(from, to, FONT_FLAGS);
    copy_long_field(from, to, FONT_HOR_TABLE);
    copy_long_field(from, to, FONT_OFF_TABLE);
    copy_long_field(from, to, FONT_DAT_TABLE);
    copy_word_field(from, to, FONT_FORM_WIDTH);
    copy_word_field(from, to, FONT_FORM_HEIGHT);
    wr16(image + work + WS_SCALED, 1);
    wr32(image + LINEA_CUR_FONT, header);
    wr32(image + work + WS_CUR_FONT, header);
}

/* ================================================================================================
 * $fcdfd0 — vst_height (12): the TALLEST font of the current face whose top is no higher than ptsin[1],
 * and when its top is not exactly that, the header scaled to it.
 *
 * The face's first font is taken whatever its top; from there the walk moves on while the next font of
 * the face still fits (an UNSIGNED compare) — along its chain, and on into the slots after it, where a
 * slot whose first font does not fit or is another face is skipped whole. In normalised coordinates the
 * height is measured from the bottom row: DEV_TAB[1] + 1 - ptsin[1].
 * ============================================================================================= */
void vdi_vst_height(uint8_t *image)
{
    uint16_t face = font_word(image, linea_pointer(image, LINEA_CUR_FONT), FONT_ID);
    uint32_t slot = LINEA_FONT_RING;
    uint32_t font, chosen;
    uint16_t requested;

    set_current_work_word(image, WS_PTS_MODE, VDI_PTS_MODE_HEIGHT);
    font = chosen = first_of_face(image, face, &slot);
    requested = (uint16_t)ptsin_word(image, 1);
    if (current_work_word(image, WS_XFM_MODE) == VDI_XFM_MODE_NDC)
        requested = (uint16_t)(table_uword(image, LINEA_DEV_TAB, VDI_DEV_TAB_MAX_Y_INDEX) + 1 - requested);
    do {
        while (requested >= font_word(image, font, FONT_TOP) && font_word(image, font, FONT_ID) == face) {
            chosen = font;
            font = font_long(image, font, FONT_NEXT);
            if (font == 0)
                break;
        }
        font = next_slot(image, &slot);
    } while (font != 0);

    set_current_font(image, chosen);
    set_current_work_word(image, WS_SCALED, 0);
    if (requested != font_word(image, chosen, FONT_TOP)) {
        uint32_t work = current_work(image);          /* pushed round the call, and stored through after it */
        uint16_t increment = (uint16_t)vdi_clc_dda(image, (int16_t)font_word(image, chosen, FONT_TOP), (int16_t)requested);

        wr16(image + work + WS_DDA_INC, increment);
        wr16(image + LINEA_DDA_INC, increment);
        set_current_work_word(image, WS_T_SCLSTS, be16(image + LINEA_T_SCLSTS));
        vdi_make_header(image);
        chosen = linea_pointer(image, LINEA_CUR_FONT);
    }
    answer_points(image, SIZE_ANSWER_POINTS);
    answer_size(image, chosen);
}

/* ================================================================================================
 * $fce26c — vst_point (107): the LARGEST font of the current face whose point size is no more than
 * intin[0] (SIGNED compares), found by vst_height's walk — and, remembered along the same walk, the last
 * font whose DOUBLED size still fits. When the fit is not exact and that doubled size lies above the
 * chosen font's and within the request, the doubled font is scaled up by two instead (DDA marker, scale
 * up, make_header). The size it settles on is answered in intout[0].
 *
 * WS_T_SCLSTS is set, the Line-A copy is not: act_siz tests the doubling marker before the direction.
 * ============================================================================================= */
#define POINT_ANSWER_WORDS 1

void vdi_vst_point(uint8_t *image)
{
    uint16_t face = font_word(image, linea_pointer(image, LINEA_CUR_FONT), FONT_ID);
    uint32_t slot = LINEA_FONT_RING;
    uint32_t font, chosen, doubled;
    int16_t requested;
    uint8_t *contrl;

    set_current_work_word(image, WS_PTS_MODE, VDI_PTS_MODE_POINT);
    font = chosen = doubled = first_of_face(image, face, &slot);
    requested = intin_word(image, 0);
    do {
        for (;;) {
            int16_t point = (int16_t)font_word(image, font, FONT_POINT);

            if (requested < point || font_word(image, font, FONT_ID) != face)
                break;
            chosen = font;
            if (requested >= (int16_t)(uint16_t)((uint16_t)point << 1))         /* `asl.w`: the word, doubled */
                doubled = font;
            font = font_long(image, font, FONT_NEXT);
            if (font == 0)
                break;
        }
        font = next_slot(image, &slot);
    } while (font != 0);

    wr32(image + current_work(image) + WS_CUR_FONT, chosen);
    wr32(image + LINEA_CUR_FONT, chosen);
    set_current_work_word(image, WS_SCALED, 0);
    if (requested != (int16_t)font_word(image, chosen, FONT_POINT)) {
        int16_t doubled_point = (int16_t)(uint16_t)(font_word(image, doubled, FONT_POINT) << 1);

        if (doubled_point > (int16_t)font_word(image, chosen, FONT_POINT) && doubled_point <= requested) {
            set_current_work_word(image, WS_DDA_INC, VDI_DDA_DOUBLE);
            wr16(image + LINEA_DDA_INC, VDI_DDA_DOUBLE);
            set_current_work_word(image, WS_T_SCLSTS, VDI_SCALE_UP);
            wr32(image + current_work(image) + WS_CUR_FONT, doubled);
            vdi_make_header(image);
            chosen = linea_pointer(image, LINEA_CUR_FONT);
        }
    }
    contrl = image + linea_pointer(image, LINEA_CONTRL);          /* one `movea.l $299e`, as the ROM */
    wr16(contrl + CONTRL_N_INTOUT, POINT_ANSWER_WORDS);
    wr16(contrl + CONTRL_N_PTSOUT, SIZE_ANSWER_POINTS);
    answer_intout(image, 0, font_word(image, chosen, FONT_POINT));
    answer_size(image, chosen);
}

/* ================================================================================================
 * $fce47c — vst_font (21): the first font of face intin[0] — the ROM 6x6 when the ring has none — made
 * current, then the size the workstation last asked for asked again of it: vst_point with the old
 * font's point size when WS_PTS_MODE says vst_point set it, vst_height with its top otherwise.
 *
 * It CALLS THE SETTER OVER ARRAYS OF ITS OWN FRAME: INTIN at the size, PTSIN and PTSOUT both at the
 * points (so the setter's answer lands on the height it was asked), and puts the caller's three pointers
 * back after. The setter's intout[0] and contrl counts still reach the CALLER's arrays; vst_font then
 * answers the face in intout[0], clears contrl[2] and sets contrl[4] to 1.
 * ============================================================================================= */
/* The frame's arrays COMPACTED into the host slot: the ROM's `-18(a6)` points (ptsin[0..1], and ptsout's four
 * words) first, then its `-6(a6)` size (intin[0]) straight after them rather than 12 bytes above. Nothing the
 * nested setter touches sits in the ROM's gap, so the two layouts are the same call. */
#define FONT_CALL_POINTS_AT   0
#define FONT_CALL_SIZE_AT     (SIZE_ANSWER_POINTS * 2 * VDI_WORD_BYTES)
#define FONT_ANSWER_WORDS     1

void vdi_vst_font(uint8_t *image)
{
    uint16_t frame_local[SIZE_ANSWER_POINTS * 2 + 1];                 /* the points' words, then the size */
    _Static_assert(sizeof frame_local == HOST_SLOT_VDI_VST_FONT_CALL_BYTES, "the nested call's arrays");
    uint32_t current = linea_pointer(image, LINEA_CUR_FONT);
    uint32_t slot = LINEA_FONT_RING;
    uint32_t frame = host_slot_claim(VDI_VST_FONT_CALL, frame_local);
    uint32_t font, intin, ptsin, ptsout;
    uint8_t *intout;

    wr16(image + frame + FONT_CALL_SIZE_AT, font_word(image, current, FONT_POINT));
    wr16(image + frame + FONT_CALL_POINTS_AT + VDI_WORD_BYTES, font_word(image, current, FONT_TOP));
    font = first_of_face(image, (uint16_t)intin_word(image, 0), &slot);
    if (font == 0)
        font = FONT_ROM_6X6;
    set_current_font(image, font);

    intin = linea_pointer(image, LINEA_INTIN);
    ptsin = linea_pointer(image, LINEA_PTSIN);
    ptsout = linea_pointer(image, LINEA_PTSOUT);
    wr32(image + LINEA_INTIN, frame + FONT_CALL_SIZE_AT);
    wr32(image + LINEA_PTSOUT, frame + FONT_CALL_POINTS_AT);
    wr32(image + LINEA_PTSIN, frame + FONT_CALL_POINTS_AT);
    if (current_work_word(image, WS_PTS_MODE) != VDI_PTS_MODE_HEIGHT)
        vdi_vst_point(image);
    else
        vdi_vst_height(image);
    wr32(image + LINEA_INTIN, intin);
    wr32(image + LINEA_PTSIN, ptsin);
    wr32(image + LINEA_PTSOUT, ptsout);
    host_slot_release(VDI_VST_FONT_CALL);

    answer_points(image, 0);
    answer_words(image, FONT_ANSWER_WORDS);
    intout = image + linea_pointer(image, LINEA_INTOUT);
    wr16(intout, font_word(image, linea_pointer(image, LINEA_CUR_FONT), FONT_ID));
}

/* ================================================================================================
 * The two measuring inquiries: a character's advance is the difference of two neighbouring entries of
 * FONT_OFF_TABLE. The index is `character - FONT_FIRST_ADE` as a WORD, SIGN-EXTENDED into the address
 * (`movea.w`), with the `+ 1` and the doubling done in 32 bits — so a character $8000 or more past the
 * first reads BELOW the table.
 * ============================================================================================= */
static uint16_t advance_in(const uint8_t *image, uint32_t table, uint16_t index)
{
    uint32_t entry = table + sign_ext16(index) * VDI_WORD_BYTES;

    return (uint16_t)(be16(image + bus_dereference(entry + VDI_WORD_BYTES)) - be16(image + bus_dereference(entry)));
}

static uint16_t advance_of(const uint8_t *image, uint32_t font, uint16_t index)
{
    return advance_in(image, font_long(image, font, FONT_OFF_TABLE), index);
}

/* A scaled width as both inquiries scale it IN MEMORY, when LINEA_SCALE is on: doubled (`asl.w`) under
 * the doubling marker, act_siz's otherwise. The two `__builtin_expect`s tell GCC the act_siz call is the
 * path to lay out straight — scaled text is what a size setter leaves behind — which is worth 12 cycles of
 * vqt_width's spills round the call on its scaled row (measured, Tier 3). */
static void scale_in_place(uint8_t *image, uint8_t *width)
{
    if (__builtin_expect(be16(image + LINEA_SCALE) == 0, 0))
        return;
    if (__builtin_expect(be16(image + LINEA_DDA_INC) == VDI_DDA_DOUBLE, 0))
        wr16(width, (uint16_t)(be16(width) << 1));
    else
        wr16(width, (uint16_t)vdi_act_siz(image, (int16_t)be16(width)));
}

static int style_asks_for(const uint8_t *image, uint16_t effect)
{
    return (be16(image + LINEA_STYLE) & effect) != 0;
}

/* ================================================================================================
 * $fce62a — vqt_extent (116): the box a string of contrl[3] characters (intin) would fill, as four
 * corners in ptsout for the four right-angle rotations of LINEA_CHUP — and for any other rotation NONE,
 * though contrl[2] says 4 (the caller's ptsout is left as it was).
 *
 * The width is summed IN VDI_EXTENT_SCRATCH and the height built in VDI_EXTENT_HEIGHT_SCRATCH, and both
 * are READ BACK for every corner stored. Scaled, then widened for bold (THICKEN x count, `mulu.w`, only
 * for a font not flagged monospace), italic (both offsets) and outline (two per character, and two
 * rows). AT 270 DEGREES THE ROM SWAPS THE WRONG WORDS: it answers (0,h) (0,0) (h,0) (w,h), where the
 * other three rotations answer the box turned.
 * ============================================================================================= */
#define EXTENT_ANSWER_POINTS  4
#define OUTLINE_GROWTH        2          /* a pixel each side ($fce710 asl.w, $fce718 addq.w #2) */
#define ZERO_WORD             0          /* a corner word that is 0, not one of the two scratch words */
#define W                     VDI_EXTENT_SCRATCH
#define H                     VDI_EXTENT_HEIGHT_SCRATCH

/* One corner word, from `scratch` read back as it stands — or 0 — and the cursor past it. */
__attribute__((always_inline))
static inline uint8_t *corner_word(const uint8_t *image, uint8_t *ptsout, uint32_t scratch)
{
    wr16(ptsout, scratch == ZERO_WORD ? 0 : be16(image + scratch));
    return ptsout + VDI_WORD_BYTES;
}

/* The eight words of one rotation's corners, stored in order: always inlined, so each `scratch` is a
 * constant and each word the ROM's one `move.w` or `clr.w`. */
__attribute__((always_inline))
static inline void answer_corners(const uint8_t *image, uint8_t *ptsout, uint32_t x0, uint32_t y0, uint32_t x1,
                                  uint32_t y1, uint32_t x2, uint32_t y2, uint32_t x3, uint32_t y3)
{
    ptsout = corner_word(image, ptsout, x0);
    ptsout = corner_word(image, ptsout, y0);
    ptsout = corner_word(image, ptsout, x1);
    ptsout = corner_word(image, ptsout, y1);
    ptsout = corner_word(image, ptsout, x2);
    ptsout = corner_word(image, ptsout, y2);
    ptsout = corner_word(image, ptsout, x3);
    corner_word(image, ptsout, y3);
}

static void answer_extent_corners(const uint8_t *image, uint8_t *ptsout, uint16_t rotation)
{
    switch (rotation) {
    case 0:                      answer_corners(image, ptsout, ZERO_WORD, ZERO_WORD, W, ZERO_WORD, W, H, ZERO_WORD, H); break;
    case TEXT_ROTATION_90:       answer_corners(image, ptsout, H, ZERO_WORD, H, W, ZERO_WORD, W, ZERO_WORD, ZERO_WORD); break;
    case TEXT_ROTATION_180:      answer_corners(image, ptsout, W, H, ZERO_WORD, H, ZERO_WORD, ZERO_WORD, W, ZERO_WORD); break;
    case TEXT_ROTATION_270:      answer_corners(image, ptsout, ZERO_WORD, H, ZERO_WORD, ZERO_WORD, H, ZERO_WORD, W, H); break;
    default:                     break;
    }
}
#undef W
#undef H

void vdi_vqt_extent(uint8_t *image)
{
    uint32_t font = linea_pointer(image, LINEA_CUR_FONT);
    const uint8_t *intin = image + linea_pointer(image, LINEA_INTIN);
    uint8_t *ptsout;
    uint16_t first;
    int16_t count;

    wr16(image + VDI_EXTENT_SCRATCH, 0);
    first = font_word(image, font, FONT_FIRST_ADE);
    count = contrl_word(image, CONTRL_N_INTIN);
    for (int16_t character = 0; character < count; character++) {
        uint16_t index = (uint16_t)(be16(intin) - first);

        intin += VDI_WORD_BYTES;
        add_ram_word(image, VDI_EXTENT_SCRATCH, advance_of(image, font, index));
    }
    scale_in_place(image, image + VDI_EXTENT_SCRATCH);
    if (style_asks_for(image, VDI_STYLE_THICKEN_MASK) && !font_flag(image, font, FONT_FLAG_MONOSPACE_MASK))
        add_ram_word(image, VDI_EXTENT_SCRATCH,                        /* `mulu.w`: an unsigned product */
                     (uint16_t)((uint32_t)font_word(image, font, FONT_THICKEN) * (uint16_t)count));
    if (style_asks_for(image, VDI_STYLE_SKEW_MASK))
        add_ram_word(image, VDI_EXTENT_SCRATCH,
                     (uint16_t)(font_word(image, font, FONT_LEFT_OFFSET) + font_word(image, font, FONT_RIGHT_OFFSET)));
    set_ram_word(image, VDI_EXTENT_HEIGHT_SCRATCH,
                 (uint16_t)(font_word(image, font, FONT_TOP) + font_word(image, font, FONT_BOTTOM) + 1));
    if (style_asks_for(image, VDI_STYLE_OUTLINE_MASK)) {
        add_ram_word(image, VDI_EXTENT_SCRATCH, (uint16_t)((uint16_t)count << 1));
        add_ram_word(image, VDI_EXTENT_HEIGHT_SCRATCH, OUTLINE_GROWTH);
    }
    answer_points(image, EXTENT_ANSWER_POINTS);
    ptsout = image + linea_pointer(image, LINEA_PTSOUT);
    answer_extent_corners(image, ptsout, be16(image + LINEA_CHUP));
    wr16(image + VDI_RESULT, VDI_RESULT_SET);
}

/* ================================================================================================
 * $fce7f0 — vqt_width (117): character intin[0]'s advance in ptsout[0], and its left and right offsets
 * from FONT_HOR_TABLE in ptsout[2] and [4] — each a SIGNED BYTE — for a font flagged to have one; both
 * CLEARED FIRST, before intin is read. A character outside FIRST_ADE..LAST_ADE (UNSIGNED) answers -1
 * and leaves ptsout[0] alone.
 *
 * THE OFFSET TABLE AND THE HOR TABLE ARE INDEXED DIFFERENTLY: the advance by the 32-bit doubling above,
 * the offsets through `adda.w a1,a1` and a `(a0,a1.w)` index — the doubled index WRAPPED to a word and
 * sign-extended again, so from $4000 characters past the first the two tables part company.
 * ============================================================================================= */
#define WIDTH_ANSWER_POINTS   3
#define WIDTH_ANSWER_WORDS    1
#define NO_SUCH_CHARACTER     0xffff
#define LEFT_OFFSET_WORD      2          /* ptsout[2] and ptsout[4] ($fce804, $fce808) */
#define RIGHT_OFFSET_WORD     4
#define HOR_ENTRY_BYTES       2          /* a left and a right offset, a byte each */

void vdi_vqt_width(uint8_t *image)
{
    const uint8_t *font = font_header(image, linea_pointer(image, LINEA_CUR_FONT));
    uint8_t *ptsout = image + linea_pointer(image, LINEA_PTSOUT);
    uint16_t character;
    uint8_t *contrl;

    wr16(ptsout + LEFT_OFFSET_WORD * VDI_WORD_BYTES, 0);
    wr16(ptsout + RIGHT_OFFSET_WORD * VDI_WORD_BYTES, 0);
    character = (uint16_t)intin_word(image, 0);
    if (character < be16(font + FONT_FIRST_ADE) || character > be16(font + FONT_LAST_ADE)) {
        answer_intout(image, 0, NO_SUCH_CHARACTER);
    } else {
        uint16_t index;

        answer_intout(image, 0, character);
        index = (uint16_t)(character - be16(font + FONT_FIRST_ADE));
        wr16(ptsout, advance_in(image, be32(font + FONT_OFF_TABLE), index));
        scale_in_place(image, ptsout);
        if (be16(font + FONT_FLAGS) & FONT_FLAG_HOR_TABLE_MASK) {
            uint32_t entry = word_index(index, HOR_ENTRY_BYTES);

            wr16(ptsout + LEFT_OFFSET_WORD * VDI_WORD_BYTES, (uint16_t)sign_ext8(image[bus_dereference(be32(font + FONT_HOR_TABLE) + entry)]));
            wr16(ptsout + RIGHT_OFFSET_WORD * VDI_WORD_BYTES,
                 (uint16_t)sign_ext8(image[bus_dereference(be32(font + FONT_HOR_TABLE) + entry + 1)]));
        }
    }
    contrl = image + linea_pointer(image, LINEA_CONTRL);          /* one `movea.l $299e`, as the ROM */
    wr16(contrl + CONTRL_N_PTSOUT, WIDTH_ANSWER_POINTS);
    wr16(contrl + CONTRL_N_INTOUT, WIDTH_ANSWER_WORDS);
    wr16(image + VDI_RESULT, VDI_RESULT_SET);
}

/* ================================================================================================
 * $fced06 — vst_load_fonts (119): GDOS hands the workstation its chain of loaded fonts (contrl[10..11])
 * with a text-effects buffer (contrl[7..8]) and that buffer's split (contrl[9]). Once only: a workstation
 * that already has loaded fonts answers 0 and takes nothing. Otherwise every font of the chain whose form
 * is not yet in 68000 order is byte-swapped and FLAGGED so (`eori.w #4`); the faces are counted (a change
 * of id along the chain) into WS_NUM_FONTS and intout[0]. contrl[4] = 1 is written first, either way.
 *
 * The ring's loaded slot is NOT filled — the dispatcher copies WS_LOADED_FONTS into it on the next call.
 * ============================================================================================= */
#define LOAD_ANSWER_WORDS     1
#define NO_FACE_YET           0xffff     /* `moveq #-1,d7` */

void vdi_vst_load_fonts(uint8_t *image)
{
    uint32_t work = current_work(image);
    uint8_t *contrl = image + linea_pointer(image, LINEA_CONTRL);    /* one `movea.l $299e`, held for five reaches */
    uint16_t faces = 0, previous_face = NO_FACE_YET;
    uint32_t font;

    wr16(contrl + CONTRL_N_INTOUT, LOAD_ANSWER_WORDS);
    if (be32(image + work + WS_LOADED_FONTS) != 0) {
        answer_intout(image, 0, 0);
        return;
    }
    wr16(image + work + WS_SCRPT2, be16(contrl + CONTRL_FONT_SCRPT2));
    wr32(image + work + WS_SCRTCHP, be32(contrl + CONTRL_POINTER_A));
    font = be32(contrl + CONTRL_FONT_CHAIN);
    wr32(image + work + WS_LOADED_FONTS, font);
    do {
        if (font_word(image, font, FONT_ID) != previous_face) {
            previous_face = font_word(image, font, FONT_ID);
            faces++;
        }
        if (!font_flag(image, font, FONT_FLAG_SWAPPED_MASK)) {
            swap_form(image, font);
            wr16(image + bus_dereference(font + FONT_FLAGS), font_word(image, font, FONT_FLAGS) ^ FONT_FLAG_SWAPPED_MASK);
        }
        font = font_long(image, font, FONT_NEXT);
    } while (font != 0);
    add_ram_word(image, work + WS_NUM_FONTS, faces);
    answer_intout(image, 0, faces);
}
