/* gsxif.c — the rest of gemgsxif (`aes/gsxif.h`): hand 68000 in the ROM, ported over its own order. Every VDI call
 * goes through `aes/gsx.h`'s binding: a wrapper's call is `gsx_call` (the folded $fe8bb6/$fe8bba, PTSIN put back
 * after it), contrl[7..8] the pointer a call carries and contrl[9..10] the one it answers.
 *
 * The cores marked TRANSCRIBED_CORE ship as the ROM's own instructions (`gsxif.S`): their C measures over Tier 3's bar
 * and Tier 1 proves it here. The rest make Line-F calls in the ROM, so they ship as C.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/gemdosif.h"
#include "aes/gsx.h"
#include "aes/gsxif.h"
#include "aes/objects.h"
#include "aes/strings.h"
#include "transcribed.h"
#include "vdi/escape.h"
#include "vdi/linea.h"
#include "vdi/lines.h"
#include "vdi/mouse.h"
#include "vdi/vdi.h"
#include "vdi/workstation.h"

_Static_assert(GSX_MOUSE_FORM_BYTES == SPRITE_FORM_ROWS + SPRITE_ROWS * SPRITE_FORM_ROW_BYTES,
               "the mouse form gsx_mfsave copies is not the Line-A sprite form");

#define OPEN_WORDS             (GSX_OPEN_WORDS + 1)  /* $fe8bdf: v_opnwk's row, 11 words, no points */
/* gsx_start's line style: user-defined (`vsl_type 7`, `pea $f0007`), one pixel wide (`vdi/lines.h`'s
 * VDI_THIN_LINE_WIDTH), every pixel set (`aes/gsx.h`'s GSX_STYLE_SOLID). */
#define LINE_TYPE_USER         7
#define BOX_HEIGHT_OVER_CELL   3                     /* gl_hbox = gl_hchar + 3 ($fdab9a addq.w #3) */
#define BB_STANDARD_FORM       1                     /* gl_tmp.fd_stand := 1 ($fe8914 move.w #1) */
#define BB_COPY_MODE           3                     /* vro_cpyfm's S_ONLY ($fe8956 move.w #3) */
#define PTSOUT_WORD(index)     (AES_GSX_PTSOUT + (index) * VDI_WORD_BYTES)
/* bb_save's and bb_restore's two corner arrays: the AES's ptsin, the screen's corners then the form's. */
#define CORNERS_BYTES          (4 * VDI_WORD_BYTES)  /* two corners, x and y each */
#define CORNERS_FIRST          AES_GSX_PTSIN
#define CORNERS_SECOND         (CORNERS_FIRST + CORNERS_BYTES)

/* ---- the mouse state, out through the caller's pointers -------------------------------------------------------- */

/* $fe8768 — gr_mkstate: xrat, yrat, the buttons and the shift state, each read as its pointer is reached and stored
 * before the next is read (the ROM walks a table of the four addresses) — a pointer at a later word changes it. */
void aes_gr_mkstate(uint8_t *image, uint32_t mouse_x, uint32_t mouse_y, uint32_t buttons, uint32_t keys)
{
    set_bus_word(image, mouse_x, be16(image + AES_XRAT));
    set_bus_word(image, mouse_y, be16(image + AES_YRAT));
    set_bus_word(image, buttons, be16(image + AES_BUTTON));
    set_bus_word(image, keys, be16(image + AES_KSTATE));
}

/* $fe8a54 — gsx_mxmy: xrat and yrat, the second read after the first is stored. */
TRANSCRIBED_CORE
void aes_gsx_mxmy(uint8_t *image, uint32_t mouse_x, uint32_t mouse_y)
{
    set_bus_word(image, mouse_x, be16(image + AES_XRAT));
    set_bus_word(image, mouse_y, be16(image + AES_YRAT));
}

/* $fe8a6a — gsx_button. */
TRANSCRIBED_CORE
uint16_t aes_gsx_button(uint8_t *image)
{
    return be16(image + AES_BUTTON);
}

/* ---- the save-under buffer ----------------------------------------------------------------------------------- */

/* $fe8790 — gsx_malloc: gl_tmp made the screen's MFDB, then its address the block Malloc'd. */
void aes_gsx_malloc(uint8_t *image)
{
    aes_gsx_fix(image, AES_GL_TMP, 0, 0, 0);
    wr32(image + AES_GL_TMP + MFDB_ADDR, aes_dos_alloc(image, GSX_SAVE_BUFFER_BYTES));
}

/* $fe87b0 — gsx_mfree. */
void aes_gsx_mfree(uint8_t *image)
{
    (void)aes_dos_free(image, AES_GSX_MFREE_RETURN, be32(image + AES_GL_TMP + MFDB_ADDR));
}

/* $fe87bc — gsx_mret: the buffer's address, then gl_mlen — read after the first store. */
TRANSCRIBED_CORE
void aes_gsx_mret(uint8_t *image, uint32_t address, uint32_t length)
{
    set_bus_long(image, address, be32(image + AES_GL_TMP + MFDB_ADDR));
    set_bus_long(image, length, be32(image + AES_GL_MLEN));
}

/* bb_set's body, INLINED into bb_set and its two callers: their own call of it pushed ten longwords where the ROM's
 * frame is seven (Tier 3: bb_save's own cycles 1.13 of the ROM's as a call, the cursor hidden). */
static inline __attribute__((always_inline)) void blit_under(uint8_t *image, int16_t x, int16_t y, int16_t width,
                                                             int16_t height, uint32_t screen_corners,
                                                             uint32_t form_corners, uint32_t screen_mfdb,
                                                             uint32_t source, uint32_t destination)
{
    uint8_t *tmp = image + AES_GL_TMP;               /* `lea $9c4e,a1`: every gl_tmp store through it */
    uint8_t *form, *screen;
    uint16_t first_word = (uint16_t)x >> GSX_PIXELS_PER_WORD_SHIFT;
    uint16_t words = (uint16_t)((uint16_t)((uint16_t)width + (uint16_t)x - 1) >> GSX_PIXELS_PER_WORD_SHIFT);
    uint16_t pixels, left;

    REGISTER_BARRIER(tmp, REGISTER_BARRIER_ADDRESS_CLASS);
    words = (uint16_t)(words - first_word + 1);
    pixels = (uint16_t)(words << GSX_PIXELS_PER_WORD_SHIFT);
    left = (uint16_t)(first_word << GSX_PIXELS_PER_WORD_SHIFT);
    wr16(tmp + MFDB_STAND, BB_STANDARD_FORM);
    wr16(tmp + MFDB_WDWIDTH, words);
    wr16(tmp + MFDB_H, (uint16_t)height);
    wr16(tmp + MFDB_W, pixels);
    form = image + bus_span(form_corners, CORNERS_BYTES);
    wr32(form, 0);
    wr16(form + 2 * VDI_WORD_BYTES, (uint16_t)(pixels - 1));
    wr16(form + 3 * VDI_WORD_BYTES, (uint16_t)(height - 1));
    screen = image + bus_span(screen_corners, CORNERS_BYTES);
    wr16(screen, left);
    wr32(screen + VDI_WORD_BYTES, words_long(y, (uint16_t)(left + pixels - 1)));
    wr16(screen + 3 * VDI_WORD_BYTES, (uint16_t)(height - 1 + y));
    aes_gsx_fix(image, screen_mfdb, 0, 0, 0);
    aes_gsx_moff(image);
    aes_vro_cpyfm(image, BB_COPY_MODE, AES_GSX_PTSIN, source, destination);
    aes_gsx_mon(image);
}

/* $fe88f8 — bb_set: the rectangle widened to whole words; gl_tmp a standard form of that size; the screen's corners
 * at `screen_corners`, the form's at `form_corners`; `screen_mfdb` the screen's; then vro_cpyfm S_ONLY over the AES's
 * ptsin, the cursor hidden round it. Every width is a WORD and the word index is a LOGICAL shift (`lsr.w`), so an x
 * below 0 is a word far to the right. Each array is reached through one pointer, as the ROM's (a1)/(a2) — its four
 * words checked on the bus once — and the screen's y and right edge are stored as ONE longword (`move.l d1`). */
void aes_bb_set(uint8_t *image, int16_t x, int16_t y, int16_t width, int16_t height, uint32_t screen_corners,
                uint32_t form_corners, uint32_t screen_mfdb, uint32_t source, uint32_t destination)
{
    blit_under(image, x, y, width, height, screen_corners, form_corners, screen_mfdb, source, destination);
}

/* $fe8966 — bb_save: the screen under `rect` into gl_tmp (gl_src the screen's MFDB). The rectangle is read as two
 * longwords, its size first. */
void aes_bb_save(uint8_t *image, uint32_t rect)
{
    uint32_t size = bus_long(image, rect + GRECT_W);
    uint32_t origin = bus_long(image, rect);

    blit_under(image, (int16_t)(origin >> M68K_WORD_BITS), (int16_t)origin, (int16_t)(size >> M68K_WORD_BITS),
               (int16_t)size, CORNERS_FIRST, CORNERS_SECOND, AES_GL_SRC, AES_GL_SRC, AES_GL_TMP);
}

/* $fe8996 — bb_restore: gl_tmp back onto the screen under `rect` (gl_dst the screen's MFDB), the corners swapped. */
void aes_bb_restore(uint8_t *image, uint32_t rect)
{
    uint32_t size = bus_long(image, rect + GRECT_W);
    uint32_t origin = bus_long(image, rect);

    blit_under(image, (int16_t)(origin >> M68K_WORD_BITS), (int16_t)origin, (int16_t)(size >> M68K_WORD_BITS),
               (int16_t)size, CORNERS_SECOND, CORNERS_FIRST, AES_GL_DST, AES_GL_TMP, AES_GL_DST);
}

/* ---- the mouse's routines and form --------------------------------------------------------------------------- */

/* $fe89c6 — gsx_setmb: the button routine, then the motion routine, each through its vex call, what each displaced
 * kept. The third argument (GEM's `&drwaddr`, once vex_curv's) is never read. */
void aes_gsx_setmb(uint8_t *image, uint32_t button, uint32_t motion, uint32_t cursor)
{
    (void)cursor;
    wr32(image + AES_GSX_CONTRL_PTR, button);
    gsx_call(image, VDI_ROM_VEX_BUTV_OPCODE, GSX_NO_POINTS, GSX_NO_WORDS);
    wr32(image + AES_OLD_BUTTON, be32(image + AES_GSX_CONTRL_PTR2));
    wr32(image + AES_GSX_CONTRL_PTR, motion);
    gsx_call(image, VDI_ROM_VEX_MOTV_OPCODE, GSX_NO_POINTS, GSX_NO_WORDS);
    wr32(image + AES_OLD_MOTION, be32(image + AES_GSX_CONTRL_PTR2));
}

/* $fe883e — the AES's own: its button and motion interrupt glue (ROM code, handed as values). */
void aes_gsx_setmb_aes(uint8_t *image)
{
    aes_gsx_setmb(image, AES_ROM_BUTTON_GLUE, AES_ROM_MOTION_GLUE, AES_DRWADDR);
}

/* $fe89f8 — gsx_resetmb: the routines gsx_setmb displaced, put back. */
void aes_gsx_resetmb(uint8_t *image)
{
    wr32(image + AES_GSX_CONTRL_PTR, be32(image + AES_OLD_BUTTON));
    gsx_call(image, VDI_ROM_VEX_BUTV_OPCODE, GSX_NO_POINTS, GSX_NO_WORDS);
    wr32(image + AES_GSX_CONTRL_PTR, be32(image + AES_OLD_MOTION));
    gsx_call(image, VDI_ROM_VEX_MOTV_OPCODE, GSX_NO_POINTS, GSX_NO_WORDS);
}

/* $fe8a18 — gsx_tick: vex_timv; the routine it displaced out through `old`; intout[0] (the tick's milliseconds)
 * answered — read AFTER that store, so an `old` laid over intout changes it. */
uint16_t aes_gsx_tick(uint8_t *image, uint32_t routine, uint32_t old)
{
    wr32(image + AES_GSX_CONTRL_PTR, routine);
    gsx_call(image, VDI_ROM_VEX_TIMV_OPCODE, GSX_NO_POINTS, GSX_NO_WORDS);
    set_bus_long(image, old, be32(image + AES_GSX_CONTRL_PTR2));
    return be16(image + AES_GSX_INTOUT);
}

/* One word of gsx_mfset's copy: read, stored, both cursors on — the barriers keep each a postincremented address
 * register, `move.w (a1)+,(a0)+`. */
static inline __attribute__((always_inline)) void copy_word_on(uint8_t **to, const uint8_t **from)
{
    wr16(*to, be16(*from));
    *to += VDI_WORD_BYTES;
    *from += VDI_WORD_BYTES;
    CURSOR_BARRIER(*to);
    CURSOR_BARRIER(*from);
}

_Static_assert(GSX_MOUSE_FORM_WORDS % 2 == 1, "gsx_mfset copies its words in pairs and then the last one");

/* $fe8a38 — gsx_mfset: the cursor hidden; the form's 37 words copied one at a time — each read, then stored — to where
 * AES_AD_INTIN points (the AES's intin since gsx_start); vsc_form by the $fe8bdc table's row 0; the cursor shown.
 * Both ends walk a pointer, the ROM's (a0)+ and (a1)+, each span checked on the bus once. The ROM counts its words
 * with `moveq #36,d0` / `dbf`, which GCC never emits: one word a pass costs 4 cycles a word over the ROM's (Tier 3:
 * 1.10 of its own cycles), so the copy takes TWO words a pass and the 37th after — the order still one word at a
 * time, forward. */
void aes_gsx_mfset(uint8_t *image, uint32_t form)
{
    const uint8_t *from;
    uint8_t *to;
    uint16_t pairs = GSX_MOUSE_FORM_WORDS / 2;

    aes_gsx_moff(image);
    from = image + bus_span(form, GSX_MOUSE_FORM_BYTES);
    to = image + bus_span(be32(image + AES_AD_INTIN), GSX_MOUSE_FORM_BYTES);
    COUNT_BARRIER(pairs);
    do {
        copy_word_on(&to, &from);
        copy_word_on(&to, &from);
    } while (--pairs != 0);
    wr16(to, be16(from));
    gsx_call(image, VDI_ROM_VSC_FORM_OPCODE, GSX_NO_POINTS, GSX_MOUSE_FORM_WORDS);
    aes_gsx_mon(image);
}

/* $fee498 — gsx_mfsave: `$a000`; the mouse form, GSX_MOUSE_FORM_BELOW_LINEA under the block's base, kept where it
 * lives and copied out. */
void aes_gsx_mfsave(uint8_t *image)
{
    uint32_t form = gsx_linea_base(image) - GSX_MOUSE_FORM_BELOW_LINEA;

    wr32(image + AES_MFORM_AT, form);
    aes_lbcopy(image, AES_MFORM_SAVE, form, GSX_MOUSE_FORM_BYTES);
}

/* $fee4c0 — gsx_mfrestore: ...and copied back to where it lives. */
void aes_gsx_mfrestore(uint8_t *image)
{
    aes_lbcopy(image, be32(image + AES_MFORM_AT), AES_MFORM_SAVE, GSX_MOUSE_FORM_BYTES);
}

/* $fe88e4 — ratinit: v_show_c(0), which shows the cursor whatever the VDI's own hide depth; the AES's nest 0. */
TRANSCRIBED_CORE
void aes_ratinit(uint8_t *image)
{
    aes_gsx_1code(image, VDI_ROM_V_SHOW_C_OPCODE, 0);
    wr16(image + AES_GL_MOFF, 0);
}

/* ---- the workstation ------------------------------------------------------------------------------------------ */

/* $fe8866 — gsx_escapes: contrl[5] the escape, then VDI 5. */
void aes_gsx_escapes(uint8_t *image, int16_t escape)
{
    wr16(image + AES_GSX_SUBFUNCTION, (uint16_t)escape);
    gsx_call(image, VDI_ROM_ESCAPE_OPCODE, GSX_NO_POINTS, GSX_NO_WORDS);
}

/* gsx_graphic's change of mode, its own function and never inlined: GCC does not shrink-wrap, and inlined, the escape
 * calls' frame is built on the mode-held path too (Tier 3, that path's own cycles: 204 inlined; the ROM's 98) — the
 * mode held, then out of graphics (the alpha cursor on, the old mouse routines back) or into them (the alpha cursor
 * off, the AES's in). */
static void __attribute__((noinline)) graphic_mode_change(uint8_t *image, uint16_t graphic)
{
    wr16(image + AES_GL_GRAPHIC, graphic);
    if (!graphic) {
        aes_gsx_escapes(image, VDI_ESCAPE_V_ENTER_CUR);
        aes_gsx_resetmb(image);
        return;
    }
    aes_gsx_escapes(image, VDI_ESCAPE_V_EXIT_CUR);
    aes_gsx_setmb_aes(image);
}

/* $fe8828 — gsx_graphic: nothing if the mode is the one held (a WORD compare), else the change. */
void aes_gsx_graphic(uint8_t *image, int16_t graphic)
{
    /* The ROM's `lea $c90c,a1` is one address register; the field's displacement SPLIT between the register and the
     * compare (`lea d16(a0)`, `cmp.w d16(a0)`) is the cheapest the C reaches — an `adda.l` of the whole address costs
     * 4 cycles more, an index register 6 (Tier 3, the mode held: 72 of its own cycles against the ROM's 58). */
    const uint8_t *held = image + AES_GL_GRAPHIC / 2;

    REGISTER_BARRIER(held, REGISTER_BARRIER_ADDRESS_CLASS);
    _Static_assert(AES_GL_GRAPHIC % 2 == 0, "the two halves of the split displacement are the field's address");
    if ((uint16_t)graphic != be16(held + AES_GL_GRAPHIC / 2))
        graphic_mode_change(image, (uint16_t)graphic);
}

/* $fe8aae — v_opnwk: the block's INTIN at `work_in`, INTOUT at `work_out` and PTSOUT 90 bytes in, for the one call
 * (row 3 of $fe8bdc); the handle answered in contrl[6] out through `handle`; the AES's own three arrays back. */
void aes_v_opnwk(uint8_t *image, uint32_t work_in, uint32_t handle, uint32_t work_out)
{
    wr32(image + AES_GSX_PB_INTIN, work_in);
    wr32(image + AES_GSX_PB_INTOUT, work_out);
    wr32(image + AES_GSX_PB_PTSOUT, work_out + GSX_WS_INTOUT_BYTES);
    gsx_call(image, VDI_ROM_V_OPNWK_OPCODE, GSX_NO_POINTS, OPEN_WORDS);
    set_bus_word(image, handle, be16(image + AES_GSX_HANDLE));
    wr32(image + AES_GSX_PB_INTIN, AES_GSX_INTIN);
    wr32(image + AES_GSX_PB_INTOUT, AES_GSX_INTOUT);
    wr32(image + AES_GSX_PB_PTSOUT, AES_GSX_PTSOUT);
}

/* $fe8876 — gsx_wsopen: intin's ten attributes 1 and its coordinates 2, then gl_restype over intin[0]; the physical
 * workstation opened into gl_handle and gl_ws; gl_restype set from the size answered — 3, then 2 for a screen 319
 * wide, else 4 for one 399 high; no resolution change asked; graphics mode. */
void aes_gsx_wsopen(uint8_t *image)
{
    uint16_t restype = GSX_RESTYPE_MEDIUM;
    int index;

    for (index = 0; index < GSX_OPEN_WORDS; index++)
        wr16(image + GSX_INTIN_WORD(index), GSX_OPEN_ATTRIBUTE);
    wr16(image + GSX_INTIN_WORD(GSX_OPEN_WORDS), GSX_OPEN_COORDINATES);
    wr16(image + AES_GSX_INTIN, be16(image + AES_GL_RESTYPE));
    aes_v_opnwk(image, AES_GSX_INTIN, AES_GL_HANDLE, AES_GL_WS);
    if (be16(image + GSX_WS_WORD(GSX_WS_XRES)) == GSX_LOW_XRES)
        restype = GSX_RESTYPE_LOW;
    else if (be16(image + GSX_WS_WORD(GSX_WS_YRES)) == VDI_OPNWK_HIGH_MAX_Y)
        restype = GSX_RESTYPE_HIGH;
    wr16(image + AES_GL_RESTYPE, restype);
    wr16(image + AES_GL_RSCHANGE, 0);
    wr16(image + AES_GL_GRAPHIC, GSX_GRAPHIC);
}

/* $fe88de — gsx_wsclose: v_clswk. */
void aes_gsx_wsclose(uint8_t *image)
{
    gsx_call(image, VDI_ROM_V_CLSWK_OPCODE, GSX_NO_POINTS, GSX_NO_WORDS);
}

/* gsx_start's GRECT, a store a word, the ROM's `clr.l` of x and y one longword. */
static void set_grect(uint8_t *image, uint32_t rect, uint16_t x, uint16_t y, uint16_t width, uint16_t height)
{
    wr32(image + rect, words_long(x, y));
    wr16(image + rect + GRECT_W, width);
    wr16(image + rect + GRECT_H, height);
}

/* gsx_start's screen planes: the colours halved until none are left, counting each halving that left any (`lsr.w`
 * then `beq`): 16 colours are 4 planes, 2 one, and 0 or 1 none. */
static uint16_t planes_of(uint16_t colours)
{
    uint16_t planes = 0;

    while ((colours >>= 1) != 0)
        planes++;
    return planes;
}

/* $fdaab0 — gsx_start: every attribute cache -1 (so each setter's first call reaches the VDI), the clip the whole
 * screen, the screen's size and planes from gl_ws; the large font's sizes from vqt_attributes (its height kept as
 * gl_ws's maximum), the small font's from vst_height on gl_ws's minimum, then the large set back — its answers
 * discarded into a stack word; the cells across and down (`divs.w`), the box (`muls.w`, `divs.w` by the pixel's
 * aspect); the line style; and the five GRECTs. The VDI's answers are read once each, in the ROM's order. */
void aes_gsx_start(uint8_t *image)
{
    uint16_t discard;
    uint32_t discard_at;
    uint16_t width, height, cell_width, cell_height, box_height, box_width;

    wr16(image + AES_GL_LCOLOR, (uint16_t)-1);
    wr16(image + AES_GL_TCOLOR, (uint16_t)-1);
    wr16(image + AES_GL_DEAD_CACHE, (uint16_t)-1);
    wr16(image + AES_GL_MODE, (uint16_t)-1);
    wr16(image + AES_GL_FONT, (uint16_t)-1);
    wr16(image + AES_GL_PATT, (uint16_t)-1);
    wr16(image + AES_GL_FIS, (uint16_t)-1);
    wr16(image + AES_GL_XCLIP, 0);
    wr16(image + AES_GL_YCLIP, 0);
    width = (uint16_t)(be16(image + GSX_WS_WORD(GSX_WS_XRES)) + 1);
    wr16(image + AES_GL_WCLIP, width);
    wr16(image + AES_GL_WIDTH, width);
    height = (uint16_t)(be16(image + GSX_WS_WORD(GSX_WS_YRES)) + 1);
    wr16(image + AES_GL_HCLIP, height);
    wr16(image + AES_GL_HEIGHT, height);
    wr16(image + AES_GL_NPLANES, planes_of(be16(image + GSX_WS_WORD(GSX_WS_NCOLORS))));

    aes_gsx_ncode(image, VDI_ROM_VQT_ATTRIBUTES_OPCODE, GSX_NO_POINTS, GSX_NO_WORDS);
    wr16(image + AES_GL_WPTSCHAR, be16(image + PTSOUT_WORD(0)));
    wr16(image + GSX_WS_WORD(GSX_WS_CHMAXH), be16(image + PTSOUT_WORD(1)));
    wr16(image + AES_GL_HPTSCHAR, be16(image + PTSOUT_WORD(1)));
    cell_width = be16(image + PTSOUT_WORD(2));
    wr16(image + AES_GL_WCHAR, cell_width);
    cell_height = be16(image + PTSOUT_WORD(3));
    wr16(image + AES_GL_HCHAR, cell_height);
    aes_vst_height(image, (int16_t)be16(image + GSX_WS_WORD(GSX_WS_CHMINH)), AES_GL_WSPTSCHAR, AES_GL_HSPTSCHAR,
                   AES_GL_WSCHAR, AES_GL_HSCHAR);
    discard_at = host_slot_claim(AES_GSX_START_DISCARD, &discard);
    aes_vst_height(image, (int16_t)be16(image + GSX_WS_WORD(GSX_WS_CHMAXH)), discard_at, discard_at, discard_at, discard_at);
    host_slot_release(AES_GSX_START_DISCARD);

    wr16(image + AES_GL_NCOLS, (uint16_t)quotient_word(m68k_divs_w((uint32_t)(int32_t)(int16_t)width, cell_width)));
    wr16(image + AES_GL_NROWS, (uint16_t)quotient_word(m68k_divs_w((uint32_t)(int32_t)(int16_t)height, cell_height)));
    box_height = (uint16_t)(cell_height + BOX_HEIGHT_OVER_CELL);
    wr16(image + AES_GL_HBOX, box_height);
    box_width = (uint16_t)m68k_divs_w((uint32_t)m68k_muls_w(be16(image + GSX_WS_WORD(GSX_WS_HPIXEL)), box_height),
                                      be16(image + GSX_WS_WORD(GSX_WS_WPIXEL)));
    wr16(image + AES_GL_WBOX, box_width);

    aes_gsx_1code(image, VDI_ROM_VSL_TYPE_OPCODE, LINE_TYPE_USER);
    aes_vsl_width(image, VDI_THIN_LINE_WIDTH);
    aes_gsx_1code(image, VDI_ROM_VSL_UDSTY_OPCODE, (int16_t)GSX_STYLE_SOLID);

    set_grect(image, AES_GL_RSCREEN, 0, 0, width, height);
    set_grect(image, AES_GL_RFULL, 0, box_height, width, (uint16_t)(height - box_height));
    set_grect(image, AES_GL_RZERO, 0, 0, 0, 0);
    set_grect(image, AES_GL_RMENU, 0, 0, width, box_height);
    set_grect(image, AES_GL_RCENTER, (uint16_t)(width - box_width) >> 1,
              (uint16_t)(height - 2 * box_height) >> 1, box_width, box_height);
    wr32(image + AES_AD_INTIN, AES_GSX_INTIN);
}

/* $fe8808 — gsx_init: the workstation opened and started, the AES's mouse routines in, and the mouse's position. */
void aes_gsx_init(uint8_t *image)
{
    aes_gsx_wsopen(image);
    aes_gsx_start(image);
    aes_gsx_setmb_aes(image);
    gsx_call(image, VDI_ROM_VQ_MOUSE_OPCODE, GSX_NO_POINTS, GSX_NO_WORDS);
    wr16(image + AES_XRAT, be16(image + PTSOUT_WORD(0)));
    wr16(image + AES_YRAT, be16(image + PTSOUT_WORD(1)));
}
