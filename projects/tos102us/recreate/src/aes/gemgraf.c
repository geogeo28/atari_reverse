/* gemgraf.c — the AES's graphics library (`aes/gemgraf.h`): hand 68000 in the ROM, ported over its own order.
 *
 * WHAT THE PORT KEEPS. Each routine reads its caller's GRECTs and answer words through the pointers it is handed, and
 * the AES's own arrays (ptsin, intin, contrl) and globals at their absolute addresses, in the ROM's order: a pointer
 * laid over one of those arrays reads what the routine has just stored there (every routine's battery holds one
 * such overlap). Every width is a WORD and wraps. A FRAME the ROM hands on by address — gsx_cline's own two points,
 * gr_gtext's copy of its GRECT, gr_just's character count, gr_box's inner GRECT — is a C local here, standing in
 * through `host_slot.h` off target.
 *
 * The cores marked TRANSCRIBED_CORE ship as the ROM's own instructions (`gemgraf.S`): Line-F-free leaves whose C
 * measures over Tier 3's bar, which Tier 1 proves here. Everything else makes Line-F calls in the ROM and ships as C.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "transcribed.h"
#include "aes/aes.h"
#include "aes/gemgraf.h"
#include "aes/gsx.h"
#include "aes/gsxif.h"
#include "aes/objects.h"
#include "aes/strings.h"
#include "vdi/linea.h"
#include "vdi/vdi.h"

/* The AES's ptsin a point at a time (a word at a time: `aes/gsx.h`'s GSX_INTIN_WORD / GSX_PTSIN_WORD). */
#define PTSIN_POINT(index)    (AES_GSX_PTSIN + (index) * VDI_POINT_BYTES)

/* The calls' point counts: a line's two ends, a closed box's five corners, a corner's three, the dotted box's first
 * three sides (four points) and its last (two), and a text's one (where it starts). */
#define LINE_POINTS           2
#define BOX_POINTS            5
#define CORNER_POINTS         3
#define DOTTED_SIDES_POINTS   4
#define DOTTED_LAST_POINTS    2
#define TEXT_POINTS           1
#define DOTTED_FIRST_SEGMENT  1          /* gsx_xline's counter starts at one: `count` points are `count` - 1 lines */

/* ---- the clip ---------------------------------------------------------------------------------------------------- */

/* $fda7f8 — gsx_sclip: the GRECT into the four clip words, each read once; then vs_clip ON over its corners in ptsin
 * — x and y read again, as one longword twice, then the width and height again, each read AFTER the store before it
 * (a GRECT laid over ptsin reads its corner back) — or OFF when the height just moved, or the width word read back,
 * is 0. Answers 1 either way. */
uint16_t aes_gsx_sclip(uint8_t *image, uint32_t rect)
{
    int16_t flag = 0;
    uint16_t height;

    wr16(image + AES_GL_XCLIP, bus_word(image, rect + GRECT_X));
    wr16(image + AES_GL_YCLIP, bus_word(image, rect + GRECT_Y));
    wr16(image + AES_GL_WCLIP, bus_word(image, rect + GRECT_W));
    height = bus_word(image, rect + GRECT_H);
    wr16(image + AES_GL_HCLIP, height);
    if (height && be16(image + AES_GL_WCLIP)) {
        wr32(image + PTSIN_POINT(0), bus_long(image, rect + GRECT_X));
        wr32(image + PTSIN_POINT(1), bus_long(image, rect + GRECT_X));
        add_ram_word(image, GSX_PTSIN_WORD(2), (uint16_t)(bus_word(image, rect + GRECT_W) - 1));
        add_ram_word(image, GSX_PTSIN_WORD(3), (uint16_t)(bus_word(image, rect + GRECT_H) - 1));
        flag = 1;
    }
    aes_vs_clip(image, flag, AES_GSX_PTSIN);
    return 1;
}

/* $fda846 — gsx_gclip: the four clip words out into a GRECT, x first: a GRECT laid over them reads its own stores. */
TRANSCRIBED_CORE
void aes_gsx_gclip(uint8_t *image, uint32_t rect)
{
    set_bus_word(image, rect + GRECT_X, be16(image + AES_GL_XCLIP));
    set_bus_word(image, rect + GRECT_Y, be16(image + AES_GL_YCLIP));
    set_bus_word(image, rect + GRECT_W, be16(image + AES_GL_WCLIP));
    set_bus_word(image, rect + GRECT_H, be16(image + AES_GL_HCLIP));
}

/* $fda864 — gsx_chkclip: 1 when the GRECT touches the clip, or the clip is empty (its width or height 0). Signed
 * WORD sums and compares: a GRECT whose right edge x + w EQUALS the clip's x still touches it ($fda896 `blt`), as
 * one whose bottom edge equals its y does. */
TRANSCRIBED_CORE
uint16_t aes_gsx_chkclip(uint8_t *image, uint32_t rect)
{
    int16_t clip_width = (int16_t)be16(image + AES_GL_WCLIP), clip_height;
    int16_t x, y;

    if (!clip_width)
        return 1;
    clip_height = (int16_t)be16(image + AES_GL_HCLIP);
    if (!clip_height)
        return 1;
    x = (int16_t)bus_word(image, rect + GRECT_X);
    if (x >= (int16_t)(clip_width + be16(image + AES_GL_XCLIP)))
        return 0;
    y = (int16_t)bus_word(image, rect + GRECT_Y);
    if (y >= (int16_t)(clip_height + be16(image + AES_GL_YCLIP)))
        return 0;
    if ((int16_t)(x + bus_word(image, rect + GRECT_W)) < (int16_t)be16(image + AES_GL_XCLIP))
        return 0;
    if ((int16_t)(y + bus_word(image, rect + GRECT_H)) < (int16_t)be16(image + AES_GL_YCLIP))
        return 0;
    return 1;
}

/* ---- lines and boxes --------------------------------------------------------------------------------------------- */

/* $fda8d2 — gsx_cline: v_pline over the ROM's FRAME (its two points are its arguments, handed on by address), the
 * cursor hidden round it. */
void aes_gsx_cline(uint8_t *image, int16_t x1, int16_t y1, int16_t x2, int16_t y2)
{
    uint16_t points_local[LINE_POINTS * VDI_POINT_WORDS];
    uint32_t points;

    aes_gsx_moff(image);
    points = host_slot_claim(AES_CLINE_POINTS, points_local);
    wr32(image + points, words_long(x1, y1));
    wr32(image + points + VDI_POINT_BYTES, words_long(x2, y2));
    aes_v_pline(image, LINE_POINTS, points);
    host_slot_release(AES_CLINE_POINTS);
    aes_gsx_mon(image);
}

/* The binding's words as one ADDRESS register reaches them: contrl's, held in a register (`REGISTER_BARRIER`), and a
 * 16-bit displacement off it — contrl, intin, the caches and the handle all lie within its reach — as the ROM reaches
 * them through its `lea`'d A3/A4. Through `image` plus each absolute address, every access costs a longword immediate
 * and an indexed mode (Tier 3, gsx_attr's cached arm: 374 cycles against the ROM's 308). */
static inline uint8_t *near_contrl(uint8_t *contrl, uint32_t address)
{
    return contrl + (int32_t)(address - AES_GSX_CONTRL);
}

/* $fda8e6 — gsx_attr: the writing mode, then the text colour (`text`) or the line colour, each set through a call of
 * its own only when its cache differs — contrl[1], [3] and [6] filled for both before either test, contrl[0] and
 * intin[0] per call, the cache stored before the trap. intin[0] is SAVED first and put back last, whether a call
 * was made or not: a caller's string in intin keeps its first character. */
void aes_gsx_attr(uint8_t *image, int16_t text, int16_t mode, int16_t colour)
{
    uint8_t *contrl = image + AES_GSX_CONTRL;
    uint8_t *intin, *cache;
    uint16_t saved, opcode = VDI_ROM_VSL_COLOR_OPCODE;

    REGISTER_BARRIER(contrl, REGISTER_BARRIER_ADDRESS_CLASS);
    intin = near_contrl(contrl, GSX_INTIN_WORD(0));
    saved = be16(intin);
    wr16(contrl + CONTRL_N_PTSIN, GSX_NO_POINTS);
    wr16(contrl + CONTRL_N_INTIN, GSX_ONE_WORD);
    wr16(contrl + CONTRL_HANDLE, be16(near_contrl(contrl, AES_GL_HANDLE)));
    cache = near_contrl(contrl, AES_GL_MODE);
    if (mode != (int16_t)be16(cache)) {
        wr16(contrl + CONTRL_OPCODE, VDI_ROM_VSWR_MODE_OPCODE);
        wr16(intin, (uint16_t)mode);
        wr16(cache, (uint16_t)mode);
        aes_gsx2(image);
    }
    cache = near_contrl(contrl, AES_GL_LCOLOR);
    if (text) {
        cache = near_contrl(contrl, AES_GL_TCOLOR);
        opcode = VDI_ROM_VST_COLOR_OPCODE;
    }
    if (colour != (int16_t)be16(cache)) {
        wr16(contrl + CONTRL_OPCODE, opcode);
        wr16(intin, (uint16_t)colour);
        wr16(cache, (uint16_t)colour);
        aes_gsx2(image);
    }
    wr16(intin, saved);
}

/* $fda956 — gsx_bxpts: a GRECT's corners into ptsin, closed — (x, y), (x + w - 1, y), (x + w - 1, y + h - 1),
 * (x, y + h - 1), (x, y) — the GRECT read whole before the first store. */
TRANSCRIBED_CORE
void aes_gsx_bxpts(uint8_t *image, uint32_t rect)
{
    uint32_t corner = bus_long(image, rect + GRECT_X);
    uint16_t x = (uint16_t)pair_high(corner), y = (uint16_t)pair_low(corner);
    uint16_t right = (uint16_t)(x + bus_word(image, rect + GRECT_W) - 1);
    uint16_t bottom = (uint16_t)(y + bus_word(image, rect + GRECT_H) - 1);

    wr32(image + PTSIN_POINT(0), corner);
    wr16(image + GSX_PTSIN_WORD(2), right);
    wr16(image + GSX_PTSIN_WORD(3), y);
    wr16(image + GSX_PTSIN_WORD(4), right);
    wr16(image + GSX_PTSIN_WORD(5), bottom);
    wr16(image + GSX_PTSIN_WORD(6), x);
    wr16(image + GSX_PTSIN_WORD(7), bottom);
    wr32(image + PTSIN_POINT(4), corner);
}

/* $fda97c — gsx_box: the GRECT's outline as one polyline of its five corners. */
uint16_t aes_gsx_box(uint8_t *image, uint32_t rect)
{
    aes_gsx_bxpts(image, rect);
    return aes_v_pline(image, BOX_POINTS, AES_GSX_PTSIN);
}

/* $fdae38 — gsx_xline: `count` points as dotted lines, one segment a call, each segment's dots in step with the
 * screen's: the style $5555 shifted by the parity of the segment's x ^ y (a vertical one), of its first point's y
 * (drawn rightwards) or of its last point's y (leftwards). Each segment's points are read when it is drawn — after
 * the last call, so points laid over intin read the style word stored there. A solid line style is put back last. */
uint16_t aes_gsx_xline(uint8_t *image, int16_t count, uint32_t points)
{
    int16_t segment;
    uint16_t x0, y0, x1, parity;

    for (segment = DOTTED_FIRST_SEGMENT; segment < count; segment++) {
        x0 = bus_word(image, points);
        y0 = bus_word(image, points + VDI_WORD_BYTES);
        x1 = bus_word(image, points + VDI_POINT_BYTES);
        if (x0 == x1)
            parity = x0 ^ y0;
        else if ((int16_t)x0 < (int16_t)x1)
            parity = y0;
        else
            parity = bus_word(image, points + VDI_POINT_BYTES + VDI_WORD_BYTES);
        aes_gsx_1code(image, VDI_ROM_VSL_UDSTY_OPCODE, (int16_t)(uint16_t)(GSX_STYLE_DOTTED << (parity & GSX_STYLE_PARITY_MASK)));
        aes_v_pline(image, LINE_POINTS, points);
        points += VDI_POINT_BYTES;
    }
    return aes_gsx_1code(image, VDI_ROM_VSL_UDSTY_OPCODE, (int16_t)GSX_STYLE_SOLID);
}

/* $fdada4 — gsx_xbox: a dotted box — gsx_bxpts' corners, three sides as one dotted polyline, then the fourth from
 * (x, y) to the bottom-left corner moved up a row, so no dot is drawn twice. */
uint16_t aes_gsx_xbox(uint8_t *image, uint32_t rect)
{
    aes_gsx_bxpts(image, rect);
    aes_gsx_xline(image, DOTTED_SIDES_POINTS, AES_GSX_PTSIN);
    wr32(image + PTSIN_POINT(1), be32(image + PTSIN_POINT(3)));
    add_ram_word(image, GSX_PTSIN_WORD(3), (uint16_t)-1);
    return aes_gsx_xline(image, DOTTED_LAST_POINTS, AES_GSX_PTSIN);
}

/* $fdadce — gsx_xcbox: a dotted box's four CORNERS, each two strokes of twice the AES's box size (gl_wbox, gl_hbox),
 * drawn as one three-point gsx_xline. The ROM builds each corner from the last one's points IN PTSIN — word adds and
 * longword copies of what is there — and reads the GRECT's x and y three times between its stores (a GRECT laid
 * over ptsin reads them back): ported store by store. */
uint16_t aes_gsx_xcbox(uint8_t *image, uint32_t rect)
{
    uint16_t across = (uint16_t)(be16(image + AES_GL_WBOX) * 2);
    uint16_t down = (uint16_t)(be16(image + AES_GL_HBOX) * 2);
    uint16_t right, bottom;

    /* the top-left corner: (x, y + down), (x, y), (x + across, y) */
    wr32(image + PTSIN_POINT(0), bus_long(image, rect + GRECT_X));
    add_ram_word(image, GSX_PTSIN_WORD(1), down);
    wr32(image + PTSIN_POINT(1), bus_long(image, rect + GRECT_X));
    wr32(image + PTSIN_POINT(2), bus_long(image, rect + GRECT_X));
    add_ram_word(image, GSX_PTSIN_WORD(4), across);
    right = (uint16_t)(bus_word(image, rect + GRECT_W) - 1);
    bottom = (uint16_t)(bus_word(image, rect + GRECT_H) - 1);
    aes_gsx_xline(image, CORNER_POINTS, AES_GSX_PTSIN);
    /* the top-right: (x + w - 1 - across, y), (x + w - 1, y), (x + w - 1, y + down) */
    add_ram_word(image, GSX_PTSIN_WORD(4), (uint16_t)-across);
    add_ram_word(image, GSX_PTSIN_WORD(4), right);
    wr32(image + PTSIN_POINT(1), be32(image + PTSIN_POINT(2)));
    wr32(image + PTSIN_POINT(0), be32(image + PTSIN_POINT(1)));
    add_ram_word(image, GSX_PTSIN_WORD(0), (uint16_t)-across);
    add_ram_word(image, GSX_PTSIN_WORD(5), down);
    aes_gsx_xline(image, CORNER_POINTS, AES_GSX_PTSIN);
    /* the bottom-right: (x + w - 1 - across, y + h - 1), (x + w - 1, y + h - 1), (x + w - 1, y + h - 1 - down) */
    add_ram_word(image, GSX_PTSIN_WORD(1), bottom);
    wr32(image + PTSIN_POINT(1), be32(image + PTSIN_POINT(0)));
    add_ram_word(image, GSX_PTSIN_WORD(2), across);
    wr32(image + PTSIN_POINT(2), be32(image + PTSIN_POINT(1)));
    add_ram_word(image, GSX_PTSIN_WORD(5), (uint16_t)-down);
    aes_gsx_xline(image, CORNER_POINTS, AES_GSX_PTSIN);
    /* the bottom-left: (x + across, y + h - 1), (x, y + h - 1), (x, y + h - 1 - down) */
    add_ram_word(image, GSX_PTSIN_WORD(4), (uint16_t)-right);
    wr32(image + PTSIN_POINT(1), be32(image + PTSIN_POINT(2)));
    add_ram_word(image, GSX_PTSIN_WORD(3), down);
    wr32(image + PTSIN_POINT(0), be32(image + PTSIN_POINT(1)));
    add_ram_word(image, GSX_PTSIN_WORD(0), across);
    return aes_gsx_xline(image, CORNER_POINTS, AES_GSX_PTSIN);
}

/* ---- blits and fills --------------------------------------------------------------------------------------------- */

/* $fda9ce — gsx_blt: gl_src set up for the source (0 the screen, else a form `source_bytes` across), the cursor
 * hidden, gl_dst for the destination; the two rectangles' corners into ptsin; then vrt_cpyfm in the two colours —
 * or vro_cpyfm when the foreground is -1 — and the cursor shown. */
void aes_gsx_blt(uint8_t *image, uint32_t source, int16_t source_x, int16_t source_y, int16_t source_bytes,
                 uint32_t destination, int16_t destination_x, int16_t destination_y, int16_t destination_bytes,
                 int16_t width, int16_t height, int16_t rule, int16_t foreground, int16_t background)
{
    uint16_t right = (uint16_t)(width - 1), bottom = (uint16_t)(height - 1);

    aes_gsx_fix(image, AES_GL_SRC, source, source_bytes, height);
    aes_gsx_moff(image);
    aes_gsx_fix(image, AES_GL_DST, destination, destination_bytes, height);
    wr32(image + PTSIN_POINT(0), words_long(source_x, source_y));
    wr32(image + PTSIN_POINT(1), words_long((int16_t)(source_x + right), (int16_t)(source_y + bottom)));
    wr32(image + PTSIN_POINT(2), words_long(destination_x, destination_y));
    wr32(image + PTSIN_POINT(3), words_long((int16_t)(destination_x + right), (int16_t)(destination_y + bottom)));
    if (foreground != GSX_NO_COLOUR)
        aes_vrt_cpyfm(image, rule, AES_GSX_PTSIN, AES_GL_SRC, AES_GL_DST, foreground, background);
    else
        aes_vro_cpyfm(image, rule, AES_GSX_PTSIN, AES_GL_SRC, AES_GL_DST);
    aes_gsx_mon(image);
}

/* $fdaa48 — bb_screen: gsx_blt from the screen to the screen, no colours (vro_cpyfm). */
void aes_bb_screen(uint8_t *image, int16_t rule, int16_t source_x, int16_t source_y, int16_t destination_x,
                   int16_t destination_y, int16_t width, int16_t height)
{
    aes_gsx_blt(image, 0, source_x, source_y, 0, 0, destination_x, destination_y, 0, width, height, rule,
                GSX_NO_COLOUR, GSX_NO_COLOUR);
}

/* $fdaa6a — gsx_trans: gl_dst set up for the destination FIRST, then gl_src — made a STANDARD-format form of one
 * plane, its two words stored as one longword — and vrn_trnfm from the one to the other. */
uint16_t aes_gsx_trans(uint8_t *image, uint32_t source, int16_t source_bytes, uint32_t destination,
                       int16_t destination_bytes, int16_t height)
{
    aes_gsx_fix(image, AES_GL_DST, destination, destination_bytes, height);
    aes_gsx_fix(image, AES_GL_SRC, source, source_bytes, height);
    wr32(image + AES_GL_SRC + MFDB_STAND, (uint32_t)MFDB_FORMAT_STANDARD << M68K_WORD_BITS | GSX_FORM_PLANES);
    return aes_vrn_trnfm(image, AES_GL_SRC, AES_GL_DST);
}

/* $fdac28 — bb_fill: gsx_attr(text, mode, the text colour's own cache — so only the mode can change), the interior
 * and style each through its cache (stored before the call), the rectangle's corners into ptsin, gl_dst the
 * screen, vr_recfl. */
uint16_t aes_bb_fill(uint8_t *image, int16_t mode, int16_t interior, int16_t pattern, int16_t x, int16_t y,
                     int16_t width, int16_t height)
{
    aes_gsx_attr(image, GSX_TEXT_TEXT, mode, (int16_t)be16(image + AES_GL_TCOLOR));
    if (interior != (int16_t)be16(image + AES_GL_FIS)) {
        wr16(image + AES_GL_FIS, (uint16_t)interior);
        aes_gsx_1code(image, VDI_ROM_VSF_INTERIOR_OPCODE, interior);
    }
    if (pattern != (int16_t)be16(image + AES_GL_PATT)) {
        wr16(image + AES_GL_PATT, (uint16_t)pattern);
        aes_gsx_1code(image, VDI_ROM_VSF_STYLE_OPCODE, pattern);
    }
    wr32(image + PTSIN_POINT(0), words_long(x, y));
    wr32(image + PTSIN_POINT(1), words_long((int16_t)(x + width - 1), (int16_t)(y + height - 1)));
    aes_gsx_fix(image, AES_GL_DST, 0, 0, 0);
    return aes_vr_recfl(image, AES_GSX_PTSIN, AES_GL_DST);
}

/* ---- text -------------------------------------------------------------------------------------------------------- */

/* $fdaca4 — gsx_tcalc: the string into the AES's intin as words (xstrpix through the pointer at $c844), then in the
 * IBM or the small font its width — the characters times the cell, or the caller's width when that is smaller — out
 * through `width`; and, unless the cell is taller than the caller's height, the cell's height through `height` and
 * the characters that fit (`divs.w`) through `characters`, else 0. Any other font: all three 0. Each answer word is
 * read back from where it was just stored, in that order: answer pointers laid over each other chain. D0 is the
 * count stored. */
uint16_t aes_gsx_tcalc(uint8_t *image, int16_t font, uint32_t text, uint32_t width, uint32_t height,
                       uint32_t characters)
{
    int16_t count = aes_xstrpix(image, be32(image + AES_AD_INTIN), text);
    uint16_t cell_width, cell_height, fit = 0;
    uint32_t wide;

    if (font == GSX_FONT_IBM) {
        cell_width = be16(image + AES_GL_WCHAR);
        cell_height = be16(image + AES_GL_HCHAR);
    } else if (font == GSX_FONT_SMALL) {
        cell_width = be16(image + AES_GL_WSCHAR);
        cell_height = be16(image + AES_GL_HSCHAR);
    } else {
        set_bus_word(image, width, 0);
        set_bus_word(image, height, 0);
        set_bus_word(image, characters, 0);
        return 0;
    }
    wide = (uint32_t)m68k_muls_w((uint16_t)count, cell_width);
    if ((int16_t)wide > (int16_t)bus_word(image, width))
        wide = bus_word(image, width);
    set_bus_word(image, width, (uint16_t)wide);
    if ((int16_t)cell_height <= (int16_t)bus_word(image, height)) {
        set_bus_word(image, height, cell_height);
        fit = (uint16_t)quotient_word(m68k_divs_w((uint32_t)(int32_t)(int16_t)wide, cell_width));
    }
    set_bus_word(image, characters, fit);
    return fit;
}

/* gsx_tblt's two fonts: the word its baseline comes from, vst_height's four answer words and the height it is set
 * to — the VALUES of the ROM's table at $fdad74 (six longwords a font: the AES's own RAM addresses), named here in
 * vst_height's argument order; the ROM lays them baseline, cell height, cell width, char height, char width, height
 * (pushed in reverse). */
struct tblt_font {
    uint32_t baseline, char_width, char_height, cell_width, cell_height, height;
};

static const struct tblt_font TBLT_IBM = {
    AES_GL_HPTSCHAR, AES_GL_WPTSCHAR, AES_GL_HPTSCHAR, AES_GL_WCHAR, AES_GL_HCHAR,
    GSX_WS_WORD(GSX_WS_CHMAXH),
};
static const struct tblt_font TBLT_SMALL = {
    AES_GL_HSPTSCHAR, AES_GL_WSPTSCHAR, AES_GL_HSPTSCHAR, AES_GL_WSCHAR, AES_GL_HSCHAR,
    GSX_WS_WORD(GSX_WS_CHMINH),
};

/* $fdad0a — gsx_tblt: `characters` of the AES's intin drawn at (x, y). In the IBM or the small font the font is SET
 * first when its cache differs (vst_height, its answers into the font's words, the cache stored after the call) and
 * y moved down to the baseline by the font's character height, read after it; any other font draws as the VDI
 * stands. contrl[0..1] are stored as one longword, then contrl[3] and [6], and ptsin[0..1]: PTSIN is NOT pointed
 * anywhere, so the call reads the block's PTSIN as the last call left it. */
uint16_t aes_gsx_tblt(uint8_t *image, int16_t font, int16_t x, int16_t y, int16_t characters)
{
    const struct tblt_font *row = font == GSX_FONT_IBM ? &TBLT_IBM : font == GSX_FONT_SMALL ? &TBLT_SMALL : 0;
    uint8_t *contrl = image + AES_GSX_CONTRL;

    if (row) {
        if (font != (int16_t)be16(image + AES_GL_FONT)) {
            aes_vst_height(image, (int16_t)be16(image + row->height), row->char_width, row->char_height,
                           row->cell_width, row->cell_height);
            wr16(image + AES_GL_FONT, (uint16_t)font);
        }
        y = (int16_t)(y + be16(image + row->baseline));
    }
    wr32(contrl + CONTRL_OPCODE, (uint32_t)VDI_ROM_V_GTEXT_OPCODE << M68K_WORD_BITS | TEXT_POINTS);
    wr16(contrl + CONTRL_N_INTIN, (uint16_t)characters);
    wr16(contrl + CONTRL_HANDLE, be16(image + AES_GL_HANDLE));
    wr32(image + PTSIN_POINT(0), words_long(x, y));
    return aes_gsx2(image);
}

/* ---- the gr_ layer: GRECTs, colour words, text in boxes, icons ---------------------------------------------------- */

/* $fda56e — gr_inside: the GRECT shrunk by `thickness` on every side (grown, for a negative one) — each word read,
 * summed and stored back, x and y first, then w and h less twice it (`asl.w`: a word). */
TRANSCRIBED_CORE
void aes_gr_inside(uint8_t *image, uint32_t rect, int16_t thickness)
{
    uint16_t both_sides = (uint16_t)((uint16_t)thickness << 1);

    set_bus_word(image, rect + GRECT_X, (uint16_t)(bus_word(image, rect + GRECT_X) + thickness));
    set_bus_word(image, rect + GRECT_Y, (uint16_t)(bus_word(image, rect + GRECT_Y) + thickness));
    set_bus_word(image, rect + GRECT_W, (uint16_t)(bus_word(image, rect + GRECT_W) - both_sides));
    set_bus_word(image, rect + GRECT_H, (uint16_t)(bus_word(image, rect + GRECT_H) - both_sides));
}

/* $fda582 — gr_rect: the fill colour set (vsf_color), then bb_fill in replace mode — hollow for pattern 0, solid for
 * 7, any other a pattern — over the GRECT, read after the colour's call. */
uint16_t aes_gr_rect(uint8_t *image, int16_t colour, int16_t pattern, uint32_t rect)
{
    int16_t interior = GSX_FIS_PATTERN;

    if (pattern == GSX_PATTERN_HOLLOW)
        interior = GSX_FIS_HOLLOW;
    if (pattern == GSX_PATTERN_SOLID)
        interior = GSX_FIS_SOLID;
    aes_gsx_1code(image, VDI_ROM_VSF_COLOR_OPCODE, colour);
    return aes_bb_fill(image, GSX_MODE_REPLACE, interior, pattern, (int16_t)bus_word(image, rect + GRECT_X),
                       (int16_t)bus_word(image, rect + GRECT_Y), (int16_t)bus_word(image, rect + GRECT_W),
                       (int16_t)bus_word(image, rect + GRECT_H));
}

/* Half of what is left over, rounded up: `addq.w #1; asr.w #1` — a WORD, so a spare of $7fff rounds to -$4000. */
static inline int16_t half_spare(int16_t spare)
{
    return (int16_t)((int16_t)(spare + 1) >> 1);
}

/* $fda5c2 — gr_just: the string's size in `font` (gsx_tcalc), its width and height out into the GRECT's own and its
 * character count into the ROM's FRAME — the word of D0 its `movem` saved, which the `movem` back makes the answer.
 * Then the GRECT's corner moved: down by half the height to spare, and across — by half the width to spare (centred)
 * or all of it (right) — each spare a WORD difference of the GRECT's word read after gsx_tcalc stored it, tested by
 * the true signed compare (`ble` after `sub.w`). */
uint16_t aes_gr_just(uint8_t *image, int16_t just, int16_t font, uint32_t text, int16_t width, int16_t height,
                     uint32_t rect)
{
    uint16_t count_local;
    uint32_t count = host_slot_claim(AES_JUST_COUNT, &count_local);
    int16_t text_height, text_width;
    uint16_t characters;

    aes_gsx_tcalc(image, font, text, rect + GRECT_W, rect + GRECT_H, count);
    text_height = (int16_t)bus_word(image, rect + GRECT_H);
    if (height > text_height)
        set_bus_word(image, rect + GRECT_Y,
                     (uint16_t)(bus_word(image, rect + GRECT_Y) + half_spare((int16_t)(height - text_height))));
    text_width = (int16_t)bus_word(image, rect + GRECT_W);
    if (width > text_width) {
        if (just == GSX_JUST_CENTRE)
            set_bus_word(image, rect + GRECT_X,
                         (uint16_t)(bus_word(image, rect + GRECT_X) + half_spare((int16_t)(width - text_width))));
        else if (just == GSX_JUST_RIGHT)
            set_bus_word(image, rect + GRECT_X, (uint16_t)(bus_word(image, rect + GRECT_X) + width - text_width));
    }
    characters = be16(image + count);
    host_slot_release(AES_JUST_COUNT);
    return characters;
}

/* $fda62c — gr_gtext: a COPY of the GRECT in the ROM's frame (the words of D0 and D1 its `movem` saved), justified
 * by gr_just, and the characters that fit drawn at its corner (gsx_tblt) — none when gr_just answers 0 or less. */
void aes_gr_gtext(uint8_t *image, int16_t just, int16_t font, uint32_t text, uint32_t rect)
{
    uint16_t copy_local[GRECT_WORDS];
    uint32_t copy = host_slot_claim(AES_GTEXT_RECT, copy_local);
    int16_t characters;

    wr32(image + copy + GRECT_X, bus_long(image, rect + GRECT_X));
    wr32(image + copy + GRECT_W, bus_long(image, rect + GRECT_W));
    characters = (int16_t)aes_gr_just(image, just, font, text, (int16_t)be16(image + copy + GRECT_W),
                                      (int16_t)be16(image + copy + GRECT_H), copy);
    if (characters > 0)
        aes_gsx_tblt(image, font, (int16_t)be16(image + copy + GRECT_X), (int16_t)be16(image + copy + GRECT_Y),
                     characters);
    host_slot_release(AES_GTEXT_RECT);
}

/* $fda66a — gr_crack: an object's colour word out through five pointers, in this order — the border colour (bits
 * 12-15), the text colour (8-11), the pattern (4-6, and 7), the writing mode, the interior colour (0-3). The
 * pattern's top bit is read back out of the word just stored: set, the pattern keeps its low three bits (`andi.w`
 * over the word) and the mode is replace; clear, transparent. Pointers laid over each other: the last store wins. */
TRANSCRIBED_CORE
void aes_gr_crack(uint8_t *image, int16_t colour, uint32_t border, uint32_t text, uint32_t pattern, uint32_t interior,
                  uint32_t mode)
{
    uint16_t high = (uint16_t)((uint16_t)colour >> CRACK_TEXT_SHIFT), low = (uint16_t)colour & CRACK_LOW_BYTE_MASK;

    set_bus_word(image, border, (high >> (CRACK_BORDER_SHIFT - CRACK_TEXT_SHIFT)) & CRACK_NIBBLE_MASK);
    set_bus_word(image, text, high & CRACK_NIBBLE_MASK);
    set_bus_word(image, pattern, (low >> CRACK_PATTERN_SHIFT) & CRACK_NIBBLE_MASK);
    if (bus_byte(image, pattern + 1) & 1u << CRACK_REPLACE_BIT) {
        set_bus_word(image, pattern, bus_word(image, pattern) & CRACK_PATTERN_MASK);
        set_bus_word(image, mode, GSX_MODE_REPLACE);
    } else {
        set_bus_word(image, mode, GSX_MODE_TRANSPARENT);
    }
    set_bus_word(image, interior, low & CRACK_NIBBLE_MASK);
}

/* $fda76e, folded: one of an icon's two forms blitted onto the screen at the icon's GRECT — a form as wide in bytes
 * as the icon is in pixels / 8, the screen's row gl_width / 8 (each `divs.w`: toward zero), transparent, in the
 * two colours. The ROM's fragment takes the form in D0, the colours in D1/D2 and the GRECT in its caller's A3. */
static void gicon_blit(uint8_t *image, uint32_t form, uint32_t icon, int16_t foreground, int16_t background)
{
    int16_t width = (int16_t)bus_word(image, icon + GRECT_W);

    aes_gsx_blt(image, form, 0, 0, quotient_word(m68k_divs_w((uint32_t)(int32_t)width, BITS_PER_BYTE)), 0,
                (int16_t)bus_word(image, icon + GRECT_X), (int16_t)bus_word(image, icon + GRECT_Y),
                gsx_screen_row_bytes(image),
                width, (int16_t)bus_word(image, icon + GRECT_H), GSX_MODE_TRANSPARENT, foreground, background);
}

/* $fda6c4 — gr_gicon: an icon. Its character word holds the foreground colour (bits 12-15), the background (8-11)
 * and a character (0-7); SELECTED swaps the colours. Unless the icon is WHITEBAK over a white background, the MASK
 * is blitted in the background colour and the text's GRECT filled solid in it; then the DATA in the foreground, the
 * text colour set (transparent), the character — when there is one — drawn in the small font at the icon's corner
 * plus its offset, and the text centred in its GRECT. */
void aes_gr_gicon(uint8_t *image, int16_t state, uint32_t mask, uint32_t data, uint32_t text, int16_t character,
                  int16_t char_x, int16_t char_y, uint32_t icon, uint32_t text_rect)
{
    int16_t foreground = (int16_t)((character >> ICON_FOREGROUND_SHIFT) & CRACK_NIBBLE_MASK);
    int16_t background = (int16_t)((character >> ICON_BACKGROUND_SHIFT) & CRACK_NIBBLE_MASK), swapped;
    uint16_t glyph = (uint16_t)character & ICON_CHARACTER_MASK;

    if (state & 1 << ICON_STATE_SELECTED_BIT) {
        swapped = foreground;
        foreground = background;
        background = swapped;
    }
    if (!(state & 1 << ICON_STATE_WHITEBAK_BIT) || background != ICON_COLOUR_WHITE) {
        gicon_blit(image, mask, icon, background, foreground);
        aes_gr_rect(image, background, GSX_PATTERN_SOLID, text_rect);
    }
    gicon_blit(image, data, icon, foreground, background);
    aes_gsx_attr(image, GSX_TEXT_TEXT, GSX_MODE_TRANSPARENT, foreground);
    if (glyph) {
        wr16(image + GSX_INTIN_WORD(0), glyph);
        aes_gsx_tblt(image, GSX_FONT_SMALL, (int16_t)(bus_word(image, icon + GRECT_X) + char_x),
                     (int16_t)(bus_word(image, icon + GRECT_Y) + char_y), ICON_CHARACTERS);
    }
    aes_gr_gtext(image, GSX_JUST_CENTRE, GSX_FONT_SMALL, text, text_rect);
}

/* $fda7a4 — gr_box: a box `thickness` lines thick, the cursor hidden round it — each line gr_inside of a copy of the
 * GRECT (a local of the ROM's frame) and gsx_box, from thickness - 1 in to 0; a NEGATIVE thickness draws from
 * thickness out to 0 (one line more: the ROM's `subq.w #1` first). A thickness of 0 draws nothing. */
void aes_gr_box(uint8_t *image, int16_t x, int16_t y, int16_t width, int16_t height, int16_t thickness)
{
    uint16_t inner_local[GRECT_WORDS];
    uint32_t inner;

    if (!thickness)
        return;
    if (thickness < 0)
        thickness = (int16_t)(thickness - 1);
    aes_gsx_moff(image);
    inner = host_slot_claim(AES_BOX_RECT, inner_local);
    do {
        thickness = (int16_t)(thickness > 0 ? thickness - 1 : thickness + 1);
        wr32(image + inner + GRECT_X, words_long(x, y));
        wr32(image + inner + GRECT_W, words_long(width, height));
        aes_gr_inside(image, inner, thickness);
        aes_gsx_box(image, inner);
    } while (thickness);
    host_slot_release(AES_BOX_RECT);
    aes_gsx_mon(image);
}
