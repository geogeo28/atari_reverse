/* inquire.c — the VDI's INQUIRIES: what a workstation's attributes, the device, the fonts, the mouse
 * and the keyboard hold, answered into intout / ptsout and contrl's two counts. Plus the two opcodes
 * the ROM serves with nothing at all.
 *
 * Entered as the dispatcher leaves the machine (`vdi/vdi.h`): contrl[2] and contrl[4] already
 * cleared, VDI_RESULT cleared, and the workstation's copies made. So a function that answers no points
 * writes no contrl[2], and what it DOES write is in the ROM's order — which only an overlap of the
 * arrays can show, and the cases lay one.
 *
 * WHICH COPY IS READ is part of each function, because the Line-A copies and the record are two
 * different addresses. The three attribute inquiries of lines, markers and fills read the write
 * mode from LINEA_WRT_MODE, vqt_attributes reads it from WS_WRT_MODE; the text inquiries read the
 * font through LINEA_CUR_FONT, never WS_CUR_FONT. On entry the dispatcher has made each pair equal.
 *
 * SO IS WHEN A POINTER IS READ. The ROM loads intout's pointer once, answers into it, and only then
 * loads ptsout's (`movea.l $29ae,a5` after the intout stores) — so each core here reads LINEA_PTSOUT
 * after its intout answers, and anything else the ROM reads between two stores between them too.
 */
#include <stdint.h>

#include "machine.h"
#include "vdi/font.h"
#include "vdi/helpers.h"
#include "vdi/inquire.h"
#include "vdi/vdi.h"

#define WORD_BYTES 2
#define LONG_BYTES 4

/* A colour the workstation keeps MAPPED (a hardware pen), answered as the VDI index again. `movea.w`
 * sign-extends and `adda.l a0,a0` doubles in 32 bits — not the wrapping word index of `m68k_idioms.h`,
 * so a pen of $4000 reads $8000 bytes ABOVE the table, not below it. */
static uint16_t vdi_index_of_pen(const uint8_t *image, uint16_t pen)
{
    return be16(image + (uint32_t)(VDI_REV_MAP_COL + WORD_BYTES * sign_ext16(pen)));
}


/* $fca652 — opcodes 4, 10, 27 and 34, and USER_TIM's default: the `rts` that ends get_kbshift. */
void vdi_nop(uint8_t *image)
{
    (void)image;
}

/* $fcb198 — opcode 29, valuator input: `link / unlk / rts`. Nothing is answered, not even a count. */
void vdi_valuator(uint8_t *image)
{
    (void)image;
}

/* $fcbd7e — vql_attributes (35): line style (1-based), colour, write mode (1-based); width, 0. */
#define VQL_INTOUT_WORDS  3
#define VQL_PTSOUT_POINTS 1

void vdi_vql_attributes(uint8_t *image)
{
    uint32_t work = linea_pointer(image, LINEA_CUR_WORK);
    uint8_t *intout = image + linea_pointer(image, LINEA_INTOUT);
    uint8_t *ptsout;

    wr16(intout, be16(image + work + WS_LINE_INDEX) + 1);
    wr16(intout + WORD_BYTES, vdi_index_of_pen(image, be16(image + work + WS_LINE_COLOR)));
    wr16(intout + 2 * WORD_BYTES, be16(image + LINEA_WRT_MODE) + 1);
    ptsout = image + linea_pointer(image, LINEA_PTSOUT);
    wr16(ptsout, be16(image + work + WS_LINE_WIDTH));
    wr16(ptsout + WORD_BYTES, 0);
    answer_points(image, VQL_PTSOUT_POINTS);
    answer_words(image, VQL_INTOUT_WORDS);
}

/* $fcbdda — vqm_attributes (36): marker type, colour, write mode (1-based); 0, height.
 *
 * THE MARKER TYPE IS ANSWERED 0-BASED — `move.w 60(a4)` with no `addq`, where vql and vqf add one to
 * their style indexes — so it does not round-trip through vsm_type. And unlike vql, this one sets
 * VDI_RESULT, and writes contrl[4] before contrl[2]. */
#define VQM_INTOUT_WORDS  3
#define VQM_PTSOUT_POINTS 1

void vdi_vqm_attributes(uint8_t *image)
{
    uint32_t work = linea_pointer(image, LINEA_CUR_WORK);
    uint8_t *intout = image + linea_pointer(image, LINEA_INTOUT);
    uint8_t *ptsout;

    wr16(intout, be16(image + work + WS_MARK_INDEX));
    wr16(intout + WORD_BYTES, vdi_index_of_pen(image, be16(image + work + WS_MARK_COLOR)));
    wr16(intout + 2 * WORD_BYTES, be16(image + LINEA_WRT_MODE) + 1);
    ptsout = image + linea_pointer(image, LINEA_PTSOUT);
    wr16(ptsout, 0);
    wr16(ptsout + WORD_BYTES, be16(image + work + WS_MARK_HEIGHT));
    answer_words(image, VQM_INTOUT_WORDS);
    answer_points(image, VQM_PTSOUT_POINTS);
    wr16(image + VDI_RESULT, VDI_RESULT_SET);
}

/* $fcbe3a — vqf_attributes (37): interior, colour, style index (1-based), write mode (1-based),
 * perimeter. No points. */
#define VQF_INTOUT_WORDS 5

void vdi_vqf_attributes(uint8_t *image)
{
    uint32_t work = linea_pointer(image, LINEA_CUR_WORK);
    uint8_t *intout = image + linea_pointer(image, LINEA_INTOUT);

    wr16(intout, be16(image + work + WS_FILL_STYLE));
    wr16(intout + WORD_BYTES, vdi_index_of_pen(image, be16(image + work + WS_FILL_COLOR)));
    wr16(intout + 2 * WORD_BYTES, be16(image + work + WS_FILL_INDEX) + 1);
    wr16(intout + 3 * WORD_BYTES, be16(image + LINEA_WRT_MODE) + 1);
    wr16(intout + 4 * WORD_BYTES, be16(image + work + WS_FILL_PER));
    answer_words(image, VQF_INTOUT_WORDS);
}

/* $fce5b0 — vqt_attributes (38): the font's id, colour, rotation, both alignments and the write mode;
 * then the font's character width, cell height from the top, cell width, and cell height.
 *
 * THE WRITE MODE IS ANSWERED 0-BASED, out of the RECORD (`move.w 296(a3)`), where the other three
 * attribute inquiries answer LINEA_WRT_MODE + 1 — so the four disagree by one about the same field. */
#define VQT_INTOUT_WORDS  6
#define VQT_PTSOUT_POINTS 2

void vdi_vqt_attributes(uint8_t *image)
{
    uint32_t work = linea_pointer(image, LINEA_CUR_WORK);
    uint32_t font = linea_pointer(image, LINEA_CUR_FONT);
    uint8_t *intout = image + linea_pointer(image, LINEA_INTOUT);

    wr16(intout, font_word(image, font, FONT_ID));
    wr16(intout + WORD_BYTES, vdi_index_of_pen(image, be16(image + work + WS_TEXT_COLOR)));
    wr16(intout + 2 * WORD_BYTES, be16(image + work + WS_CHUP));
    wr16(intout + 3 * WORD_BYTES, be16(image + work + WS_H_ALIGN));
    wr16(intout + 4 * WORD_BYTES, be16(image + work + WS_V_ALIGN));
    wr16(intout + 5 * WORD_BYTES, be16(image + work + WS_WRT_MODE));
    answer_font_size(image, font);                 /* the top read after the first store (`$fce5f2`), kept in D7 */
    answer_points(image, VQT_PTSOUT_POINTS);
    answer_words(image, VQT_INTOUT_WORDS);
    wr16(image + VDI_RESULT, VDI_RESULT_SET);
}

/* $fc4e06 — the blit mode the drawing vectors were filled for, which XBIOS Blitmode also reads
 * ($fc0f02): `move.w LINEA_BLIT_MODE,d0 / rts`. */
static uint16_t blit_mode_get(const uint8_t *image)
{
    return be16(image + LINEA_BLIT_MODE);
}

/* $fcb8d0 — vq_extnd (102): intin[0] = 0 answers v_opnwk's tables again (SIZ_TAB, DEV_TAB); anything
 * else answers the extended ones — the clip rectangle and eight zeros, INQ_TAB, and a drawing speed
 * by the blit mode. `tst.w`, so $0100 is "extended". The counts come first and VDI_RESULT is set.
 *
 * intin[0] IS READ TWICE, before the tables and again after intout is written, and the second read
 * alone decides the speed — so with intin laid over intout, the plain arm answers a speed too
 * (DEV_TAB[0] is not 0) and an extended one whose INQ_TAB[0] is 0 does not. */
#define VQ_EXTND_PTSOUT_POINTS (VDI_SIZ_TAB_WORDS / 2)
#define VQ_EXTND_CLIP_WORDS    4      /* xmin, ymin, xmax, ymax */
#define VQ_EXTND_SPEED_BLITTER 5000
#define VQ_EXTND_SPEED_CPU     1000

static int extended_inquiry(const uint8_t *image)
{
    return be16(image + linea_pointer(image, LINEA_INTIN)) != 0;
}

void vdi_vq_extnd(uint8_t *image)
{
    uint8_t *ptsout;
    uint8_t *intout;
    const uint8_t *table;

    answer_points(image, VQ_EXTND_PTSOUT_POINTS);
    answer_words(image, VDI_INQ_TAB_WORDS);
    wr16(image + VDI_RESULT, VDI_RESULT_SET);
    ptsout = image + linea_pointer(image, LINEA_PTSOUT);
    if (!extended_inquiry(image)) {
        copy_words(ptsout, image + LINEA_SIZ_TAB, VDI_SIZ_TAB_WORDS);
        table = image + LINEA_DEV_TAB;
    } else {
        wr16(ptsout, be16(image + LINEA_XMINCL));
        wr16(ptsout + WORD_BYTES, be16(image + LINEA_YMINCL));
        wr16(ptsout + 2 * WORD_BYTES, be16(image + LINEA_XMAXCL));
        wr16(ptsout + 3 * WORD_BYTES, be16(image + LINEA_YMAXCL));
        for (unsigned word = VQ_EXTND_CLIP_WORDS; word < VDI_SIZ_TAB_WORDS; word++)
            wr16(ptsout + word * WORD_BYTES, 0);
        table = image + LINEA_INQ_TAB;
    }
    intout = image + linea_pointer(image, LINEA_INTOUT);
    copy_words(intout, table, VDI_INQ_TAB_WORDS);
    if (extended_inquiry(image))           /* ...and intout's pointer is loaded again for the speed */
        answer_intout(image, VDI_INQ_TAB_SPEED_INDEX,
                      (blit_mode_get(image) & LINEA_BLIT_MODE_BLITTER_MASK) ? VQ_EXTND_SPEED_BLITTER : VQ_EXTND_SPEED_CPU);
}

/* $fced9a — vst_unload_fonts (120): forget the workstation's loaded fonts. It resets the record's own
 * font count, scratch buffer and its split, and answers nothing.
 *
 * WHAT IT LEAVES: LINEA_FONT_RING's loaded slot (the dispatcher's copy, refreshed on the NEXT call) and
 * WS_CUR_FONT — so a workstation whose current font was a loaded one keeps pointing at it. */
void vdi_vst_unload_fonts(uint8_t *image)
{
    uint8_t *work = image + linea_pointer(image, LINEA_CUR_WORK);

    wr32(work + WS_LOADED_FONTS, 0);
    wr16(work + WS_SCRPT2, be16(image + VDI_SCRPT2_DEFAULT));
    wr32(work + WS_SCRTCHP, VDI_TEXT_SCRATCH);
    wr16(work + WS_NUM_FONTS, be16(image + LINEA_FONT_COUNT));
}

/* $fcb156 — vq_mouse (124): the buttons, then the counts, then the position. */
#define VQ_MOUSE_INTOUT_WORDS  1
#define VQ_MOUSE_PTSOUT_POINTS 1

void vdi_vq_mouse(uint8_t *image)
{
    uint8_t *ptsout;

    wr16(image + linea_pointer(image, LINEA_INTOUT), be16(image + LINEA_MOUSE_BT));
    answer_words(image, VQ_MOUSE_INTOUT_WORDS);
    answer_points(image, VQ_MOUSE_PTSOUT_POINTS);
    ptsout = image + linea_pointer(image, LINEA_PTSOUT);
    wr16(ptsout, be16(image + LINEA_GCURX));
    wr16(ptsout + WORD_BYTES, be16(image + LINEA_GCURY));
}

/* $fcb30a — vq_key_s (128): the count, then get_kbshift's low word — the four modifier keys, Caps Lock
 * and the emulated buttons masked off. Only D0.w is stored (`move.w d0,-(sp)`), so the high word
 * handed to the helper is nobody's. */
#define VQ_KEY_S_INTOUT_WORDS 1

void vdi_vq_key_s(uint8_t *image)
{
    answer_words(image, VQ_KEY_S_INTOUT_WORDS);
    wr16(image + linea_pointer(image, LINEA_INTOUT), (uint16_t)vdi_get_kbshift(image, 0));
}

/* vqt_name's face walk: the ring's slots in order, each a chain through FONT_NEXT, until a ZERO SLOT
 * — so an empty loaded slot hides every slot after it. A run of fonts with one id is one face, and the
 * id remembered carries across slots. Face `element` (1-based), or the ROM 6x6 when there is none —
 * element 0 and every negative one included. */
#define NO_FACE_ID 0xffff

static uint32_t face_numbered(const uint8_t *image, uint16_t element)
{
    uint16_t faces = 0;
    uint16_t previous_id = NO_FACE_ID;

    for (uint32_t slot = LINEA_FONT_RING;; slot += LONG_BYTES) {
        uint32_t font = be32(image + slot);
        if (font == 0)
            return FONT_ROM_6X6;
        for (; font != 0; font = be32(image + font + FONT_NEXT)) {
            uint16_t id = be16(image + font + FONT_ID);
            if (id == previous_id)
                continue;
            previous_id = id;
            if (++faces == element)
                return font;
        }
    }
}

/* $fce8ca — vqt_name (130): face intin[0]'s id and its name, one SIGN-EXTENDED character a word, then
 * zeros; contrl[4] = 33.
 *
 * IT WRITES 34 WORDS AND SAYS 33. The terminating NUL is written and not counted, so the zero fill
 * that follows runs one word past intout[32]. And the name is read up to its NUL, not up to
 * FONT_NAME_BYTES: a 32-character name runs on into FONT_FIRST_ADE's high byte. */
#define VQT_NAME_INTOUT_WORDS (1 + FONT_NAME_BYTES)

void vdi_vqt_name(uint8_t *image)
{
    uint32_t font = face_numbered(image, be16(image + linea_pointer(image, LINEA_INTIN)));
    uint8_t *intout = image + linea_pointer(image, LINEA_INTOUT);
    const uint8_t *name = image + font + FONT_NAME;
    uint16_t counted = 1;                         /* the id, then one per character before the NUL */
    uint16_t character;

    wr16(intout, be16(image + font + FONT_ID));
    intout += WORD_BYTES;
    for (;;) {
        character = (uint16_t)sign_ext8(*name++);
        wr16(intout, character);
        intout += WORD_BYTES;
        if (character == 0)
            break;
        counted++;
    }
    for (; (int16_t)counted < VQT_NAME_INTOUT_WORDS; counted++) {
        wr16(intout, 0);
        intout += WORD_BYTES;
    }
    answer_words(image, VQT_NAME_INTOUT_WORDS);
}

/* $fce95a — vqt_fontinfo (131): the current font's first and last character, then five (x, y)
 * pairs: cell width / bottom, the bold widening / descent, the italic left offset / half, the italic
 * right offset / ascent, 0 / top. A widening or an offset is answered only when LINEA_STYLE asks
 * for that effect, 0 otherwise — and LINEA_STYLE is tested TWICE (`btst` on its low byte), each just
 * before the answer it decides, after the stores ahead of it. */
#define VQT_FONTINFO_INTOUT_WORDS  2
#define VQT_FONTINFO_PTSOUT_POINTS 5

void vdi_vqt_fontinfo(uint8_t *image)
{
    const uint8_t *font = image + linea_pointer(image, LINEA_CUR_FONT);
    uint8_t *intout = image + linea_pointer(image, LINEA_INTOUT);
    uint8_t *ptsout;
    int skewed;

    wr16(intout, be16(font + FONT_FIRST_ADE));
    wr16(intout + WORD_BYTES, be16(font + FONT_LAST_ADE));
    ptsout = image + linea_pointer(image, LINEA_PTSOUT);
    wr16(ptsout, be16(font + FONT_MAX_CELL_WIDTH));
    wr16(ptsout + WORD_BYTES, be16(font + FONT_BOTTOM));
    wr16(ptsout + 2 * WORD_BYTES, style_asks_for(image, VDI_STYLE_THICKEN_MASK) ? be16(font + FONT_THICKEN) : 0);
    wr16(ptsout + 3 * WORD_BYTES, be16(font + FONT_DESCENT));
    skewed = style_asks_for(image, VDI_STYLE_SKEW_MASK);
    wr16(ptsout + 4 * WORD_BYTES, skewed ? be16(font + FONT_LEFT_OFFSET) : 0);
    wr16(ptsout + 5 * WORD_BYTES, be16(font + FONT_HALF));
    wr16(ptsout + 6 * WORD_BYTES, skewed ? be16(font + FONT_RIGHT_OFFSET) : 0);
    wr16(ptsout + 7 * WORD_BYTES, be16(font + FONT_ASCENT));
    wr16(ptsout + 8 * WORD_BYTES, 0);
    wr16(ptsout + 9 * WORD_BYTES, be16(font + FONT_TOP));
    answer_points(image, VQT_FONTINFO_PTSOUT_POINTS);
    answer_words(image, VQT_FONTINFO_INTOUT_WORDS);
    wr16(image + VDI_RESULT, VDI_RESULT_SET);
}
