/* escape.c — the VDI's ESCAPE, opcode 5 ($fc427a): the alpha-text screen, the tablet and hard-copy queries,
 * and the graphic cursor, picked by contrl[5] (`vdi/escape.h`).
 *
 * HAND 68000 IN THE BIOS's RANGE, and mostly not the VDI's own code at all:
 *
 *      lea     $2994,a4                ; CON_STATE_FLAGS: the console's block, which the arms address off
 *      movea.l 10(a4),a0 / move.w 10(a0),d0            ; contrl[5]
 *      cmp.w   #19,d0 / bhi  .past     ; UNSIGNED: a negative number is past the table too
 *      add.w   d0,d0 / move.w $fc4298(pc,d0.w),d0 / jmp $fc4298(pc,d0.w)
 *  .past:  cmp.w #101,d0 / beq v_offset / cmp.w #102,d0 / beq v_fontinit / rts
 *
 * The table's entries are the VT52 driver's own escape bodies — `ESC A` is v_curup's whole arm, byte for
 * byte, and the two jump tables name the same addresses — so this file enters them BY NAME through
 * `bios/vt52.h` rather than spelling any of them again. What is the escape's alone is the dispatch, the three
 * answering arms, the cursor address, the text loop, the two tail-jumps into the mouse's v_show_c / v_hide_c,
 * the Scrdmp trap and the two arms past the table.
 *
 * WHAT SHIPS is the ROM's own instructions for those (`escape.S`, `transcribed.h`): this C measured
 * 1.20x-3.13x against them — a compare tree for the ROM's table and a frame round every arm, where the ROM's
 * arms are a few instructions off the `lea` — and is what Tier 1 proves the arms by. The console bodies it
 * enters by name are the ones `escape.S`'s thunks reach.
 *
 * A POINTER THE ROM LOADS ONCE IS READ ONCE. The answering arms load intout's pointer into A0 and store both
 * answers through it, so they hold it in a local — which would only show if an answer overlapped the Line-A
 * pointer itself; what the cases DO overlap is intout with contrl, where the order the ROM stores the count
 * and the answers in is the whole difference.
 *
 * WHAT IS NOT RECONSTRUCTED BEHIND IT: v_hardcopy's printer dump. Scrdmp calls whatever `scr_dump` ($502)
 * names — the ROM's own dump in the captured machine — and a case stages a routine there, as the VBL's
 * battery does for the same call (`src/bios/vbl.c`).
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "m68k_idioms.h"
#include "bios/vt52.h"
#include "xbios/xbios.h"
#include "vdi/vdi.h"
#include "vdi/font.h"
#include "vdi/mouse.h"
#include "vdi/escape.h"
#include "transcribed.h"

/* ---- the arms that answer ------------------------------------------------------------------------ */

/* $fc442e — vq_chcells: the count first, then COLUMNS into intout[1] before ROWS into intout[0]. */
static void vq_chcells(uint8_t *image)
{
    uint8_t *intout;

    answer_words(image, VDI_ESCAPE_ANSWER_CELLS_WORDS);
    intout = image + linea_pointer(image, LINEA_INTOUT);
    wr16(intout + VDI_WORD_BYTES, (uint16_t)(be16(image + CON_MAX_COLUMN) + 1));
    wr16(intout, (uint16_t)(be16(image + CON_MAX_ROW) + 1));
}

/* $fc451c — vq_curaddress: the count, then row and column in intout's order. */
static void vq_curaddress(uint8_t *image)
{
    uint8_t *intout;

    answer_words(image, VDI_ESCAPE_ANSWER_CELLS_WORDS);
    intout = image + linea_pointer(image, LINEA_INTOUT);
    wr16(intout, (uint16_t)(be16(image + CON_CURSOR_ROW) + 1));
    wr16(intout + VDI_WORD_BYTES, (uint16_t)(be16(image + CON_CURSOR_COLUMN) + 1));
}

/* $fc453c — vq_tabstatus: one `moveq #1,d0`, stored as the count and as the answer. */
static void vq_tabstatus(uint8_t *image)
{
    answer_words(image, VDI_ESCAPE_ANSWER_TABLET_WORDS);
    answer_intout(image, 0, VDI_ESCAPE_ANSWER_TABLET);
}

/* ---- the arms that move the cursor or write text ------------------------------------------------- */

/* $fc44dc — vs_curaddress: intin's row and column are 1-BASED, and the `subq.w #1` is unchecked, so a 0
 * reaches the cell arithmetic as $ffff (`console_place_cursor`'s clamp is the N flag of a word difference,
 * which $ffff passes). */
static void vs_curaddress(uint8_t *image)
{
    const uint8_t *intin = image + linea_pointer(image, LINEA_INTIN);
    uint16_t row = (uint16_t)(be16(intin) - 1);
    uint16_t column = (uint16_t)(be16(intin + VDI_WORD_BYTES) - 1);

    console_place_cursor(image, column, row);
}

/* $fc44ee — v_curtext: contrl[3] words of intin through the console's own state machine ($fc42f6, Bconout
 * past its argument fetch), so a control code is obeyed and an ESC begins a sequence the NEXT word — or
 * the next call — completes. `bra` to a `dbf`: a count of 0 sends nothing, and the count is a WORD. */
static void v_curtext(uint8_t *image)
{
    uint16_t count = (uint16_t)contrl_word(image, CONTRL_N_INTIN);
    uint32_t intin = linea_pointer(image, LINEA_INTIN);

    for (; count != 0; count--) {
        (void)console_output(image, 0, be16(image + bus_dereference(intin)));
        intin += VDI_WORD_BYTES;
    }
}

/* $fc42d0 — v_offset: the text screen starts intin[0] scan lines down. Under the cursor's lock and taken
 * as `mulu.w`, but the cursor's own ADDRESS is not recomputed: the offset reaches the screen at the next
 * cursor placement. */
static void v_offset(uint8_t *image)
{
    uint16_t lines;

    console_hide_cursor(image);
    lines = (uint16_t)intin_word(image, 0);
    wr16(image + CON_CURSOR_OFFSET, (uint16_t)((uint32_t)lines * be16(image + CON_LINE_BYTES)));
    console_unlock_cursor(image);
}

/* $fc4a42 — v_fontinit: the console's cell geometry and font from the header intin[0..1] points at. The
 * height is read ONCE and both divides are `divu.w` of a zero-extended screen size — a header whose height
 * or cell width is 0 takes the zero-divide exception (`m68k_divu_w`), with the fields before it stored. */
static void v_fontinit(uint8_t *image)
{
    uint32_t font = be32(image + linea_pointer(image, LINEA_INTIN));
    uint16_t height = font_word(image, font, FONT_FORM_HEIGHT);

    wr16(image + CON_CELL_HEIGHT, height);
    wr16(image + CON_ROW_BYTES, (uint16_t)((uint32_t)be16(image + CON_LINE_BYTES) * height));
    wr16(image + CON_MAX_ROW, (uint16_t)(quotient_word(m68k_divu_w(be16(image + LINEA_V_REZ_VT), height)) - 1));
    wr16(image + CON_MAX_COLUMN,
         (uint16_t)(quotient_word(m68k_divu_w(be16(image + LINEA_V_REZ_HZ),
                                              font_word(image, font, FONT_MAX_CELL_WIDTH))) - 1));
    wr16(image + CON_FONT_FORM_BYTES, font_word(image, font, FONT_FORM_WIDTH));
    wr16(image + CON_FONT_FIRST, font_word(image, font, FONT_FIRST_ADE));
    wr16(image + CON_FONT_LAST, font_word(image, font, FONT_LAST_ADE));
    wr32(image + CON_FONT_FORM, font_long(image, font, FONT_DAT_TABLE));
    wr32(image + CON_FONT_OFFSETS, font_long(image, font, FONT_OFF_TABLE));
}

/* $fc4450 — v_hardcopy: `move.w #20,-(sp) / trap #14`, its answer discarded. */
static void v_hardcopy(uint8_t *image)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    xbios_scrdmp(image);
#else
    (void)image;
    (void)xbios_trap_plain(XBIOS_SCRDMP_FN);
#endif
}

/* $fc454e — v_dspcur: the CALLER's intin[0] cleared, then `jmp` v_show_c — which reads it back as "show
 * whatever the depth", so the graphic cursor is forced on screen. The ptsin position GEM documents is
 * never read. */
static void v_dspcur(uint8_t *image)
{
    wr16(image + linea_pointer(image, LINEA_INTIN), 0);
    vdi_v_show_c(image);
}

/* $fc427a — the dispatch. The table arms that are the console's own escape bodies are entered by name. */
TRANSCRIBED_CORE
void vdi_escape(uint8_t *image)
{
    switch ((uint16_t)contrl_word(image, CONTRL_SUBFUNCTION)) {
    case VDI_ESCAPE_VQ_CHCELLS:    vq_chcells(image); return;
    case VDI_ESCAPE_V_EXIT_CUR:    console_hide_cursor(image); console_clear_screen_and_home(image); return;
    case VDI_ESCAPE_V_ENTER_CUR:   console_clear_screen_and_home(image); console_show_cursor(image); return;
    case VDI_ESCAPE_V_CURUP:       console_cursor_up(image); return;
    case VDI_ESCAPE_V_CURDOWN:     console_cursor_down(image); return;
    case VDI_ESCAPE_V_CURRIGHT:    console_cursor_right(image); return;
    case VDI_ESCAPE_V_CURLEFT:     console_cursor_left(image); return;
    case VDI_ESCAPE_V_CURHOME:     console_cursor_home(image); return;
    case VDI_ESCAPE_V_EEOS:        console_clear_to_end_of_screen(image); return;
    case VDI_ESCAPE_V_EEOL:        console_clear_to_end_of_line(image); return;
    case VDI_ESCAPE_VS_CURADDRESS: vs_curaddress(image); return;
    case VDI_ESCAPE_V_CURTEXT:     v_curtext(image); return;
    case VDI_ESCAPE_V_RVON:        console_reverse_video(image, 1); return;
    case VDI_ESCAPE_V_RVOFF:       console_reverse_video(image, 0); return;
    case VDI_ESCAPE_VQ_CURADDRESS: vq_curaddress(image); return;
    case VDI_ESCAPE_VQ_TABSTATUS:  vq_tabstatus(image); return;
    case VDI_ESCAPE_V_HARDCOPY:    v_hardcopy(image); return;
    case VDI_ESCAPE_V_DSPCUR:      v_dspcur(image); return;
    case VDI_ESCAPE_V_RMCUR:       vdi_v_hide_c(image); return;
    case VDI_ESCAPE_V_OFFSET:      v_offset(image); return;
    case VDI_ESCAPE_V_FONTINIT:    v_fontinit(image); return;
    default:                       return;      /* 0, and everything past 19 but 101 and 102 */
    }
}
