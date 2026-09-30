/* mouse.c — the MOUSE, CURSOR and INPUT routines (`vdi/mouse.h` lists them).
 *
 * THE SPRITE PAIR. `$a00d` draws a 16x16 form of (mask, data) rows into the screen at (x - hot_x,
 * y - hot_y), SAVING every word it touches in a save block first; `$a00c` puts the saved words back.
 * The ROM spreads each form word over the TWO 16-pixel groups it straddles as one longword and runs
 * three fragments per row through `jsr (a6)` / `jmp (a3)` / `jmp (a4)` / `jmp (a5)` — read and save the
 * screen, shift the form, combine by colour, store — chosen once per call by the clip and per plane by
 * the colours. Here that is `sprite_span` (which groups a row touches), `spread_row` and `sprite_op`.
 * A sprite clipped at the left or right edge touches ONE group and saves one word a row, and the save
 * block's STAT bit 1 says which the restore has to write back.
 *
 * THE HIDE COUNT. M_HID_CT is a depth: hide raises it and removes the sprite on the way to 1, show
 * lowers it and draws the sprite on reaching 0. MOUSE_FLAG is a LOCK the interrupt paths test, raised
 * round every routine that touches the sprite state — invisible to a differential (the oracle takes no
 * interrupt, and every routine gives it back), so only the target build's cycles see it.
 *
 * THE INTERRUPT PATHS. `mouse_isr` is KBDVECS' mousevec: it turns a relative packet into button and
 * position state, calling the three USER vectors a program may replace — in the captured machine two of
 * them point INTO THE AES, so a case repoints them at a stub it stages (`test/vdi_mouse.py`). The ISR
 * never draws: the default USER_CUR queues the position, and the VBL's slot 0 (`vbl_draw_cursor`)
 * redraws at the queued place.
 *
 * THE INPUT FUNCTIONS poll the keyboard through BIOS device 2 — the real `trap #13` on target, the BIOS
 * core directly off it — and in REQUEST mode they SPIN until a poll answers. A case stages the console
 * ring (`test/iorec.py`) or the button bits, which is what an interrupt would have done — up front, or
 * SCHEDULED at the spin's wait site (`request_pass`), which is what takes the loop round again.
 */
#include <stdint.h>

#include "machine.h"
#include "ipl.h"
#include "addrs.h"
#include "m68k_idioms.h"
#include "staged_call.h"
#include "sched.h"
#include "bios/bcon.h"
#include "xbios/xbios.h"
#include "vdi/vdi.h"
#include "vdi/raster.h"
#include "vdi/helpers.h"
#include "vdi/mouse.h"
#include "transcribed.h"

#define WORD_BYTES           2
#define PIXEL_IN_GROUP_MASK  15u     /* concat's D0: the x within its group */
#define GROUP_BITS           16      /* a form word shifted into the high word of a longword */
#define LOW_WORD             0xffffu
#define HIGH_WORD            0xffff0000u
/* The last x (y) at which all sixteen columns (rows) fit: DEV_TAB[0] ([1]) less this. */
#define SPRITE_EDGE          (SPRITE_ROWS - 1)
/* `$fd00c8`'s eight combine fragments: index = the XOR half, then the plane's fg bit, then its bg bit. */
#define SPRITE_OPS_XOR       4
#define SPRITE_OP_FG         2
#define SPRITE_OP_BG         1
#define CLEAR_PIXEL_BIT_MASK 1u
/* `ror.b #2` on the button bits that changed: left (bit 0) to bit 6, right to bit 7 ($fcfe74). */
#define CHANGED_BITS_ROTATE  2
#define BYTE_BITS            8

/* ================================================================================================
 * The sprite pair.
 * ============================================================================================= */

static inline uint16_t peek16(const uint8_t *image, uint32_t address)
{
    return be16(image + bus_address(address));
}

static inline void poke16(uint8_t *image, uint32_t address, uint16_t value)
{
    wr16(image + bus_address(address), value);
}

/* Which of the two groups a row covers: both, or — clipped at an edge — the one left on screen. */
enum sprite_span {
    SPAN_BOTH_GROUPS,   /* the save block's long rows: ($fd00e8) and ($fd00f4)                */
    SPAN_RIGHT_GROUP,   /* clipped at the LEFT edge: the low word, x moved one group on ($fd0104) */
    SPAN_LEFT_GROUP,    /* clipped at the RIGHT edge: the high word ($fd0114)                   */
};

/* A form word spread over the two groups at `shift` pixels in: ($fd0128) `rol.l` and ($fd0136)
 * `swap` + `ror.l` are one function of the shift, `(word << 16) >> shift`. */
static inline uint32_t spread_row(uint16_t word, unsigned shift)
{
    return ((uint32_t)word << GROUP_BITS) >> shift;
}

/* $fd0148..$fd0182 — one plane's row combined with the screen, by `$fd00c8`'s index. The four XOR
 * fragments are not one rule: two apply the data first. */
static uint32_t sprite_op(unsigned op, uint32_t screen, uint32_t mask, uint32_t data)
{
    switch (op) {
    case 0: return screen & ~mask & ~data;
    case 1: return (screen | mask) & ~data;
    case 2: return (screen & ~mask) | data;
    case 3: return screen | mask | data;
    case 4: return (screen ^ data) & ~mask;
    case 5: return (screen | mask) ^ data;
    case 6: return (screen & ~mask) ^ data;
    default: return (screen ^ mask) | data;
    }
}

/* The form row at `form_row` — its mask word, then its data word — spread at `shift` ($fd0128 / $fd0136). */
static void spread_form_row(const uint8_t *image, uint32_t form_row, unsigned shift, uint32_t *mask, uint32_t *data)
{
    *mask = spread_row(peek16(image, form_row), shift);
    *data = spread_row(peek16(image, form_row + WORD_BYTES), shift);
}

/* One row of one plane: the screen word(s) read and SAVED, and only then the form row read (`jmp (a3)` after
 * the save), combined, and stored. Answers where the next save goes. `at` is the row's left group,
 * `group_step` the bytes to the right one (PLANES * 2). */
static uint32_t sprite_row(uint8_t *image, enum sprite_span span, uint32_t at, uint16_t group_step,
                           uint32_t save_at, unsigned op, uint32_t form_row, unsigned shift)
{
    uint32_t right_at = at + sign_ext16(group_step);
    uint32_t screen, mask, data;

    if (span == SPAN_BOTH_GROUPS) {
        screen = (uint32_t)peek16(image, at) << GROUP_BITS | peek16(image, right_at);
        wr32(image + bus_address(save_at), screen);
        spread_form_row(image, form_row, shift, &mask, &data);
        screen = sprite_op(op, screen, mask, data);
        poke16(image, right_at, (uint16_t)screen);
        poke16(image, at, (uint16_t)(screen >> GROUP_BITS));
        return save_at + sizeof(uint32_t);
    }
    screen = peek16(image, at);
    poke16(image, save_at, (uint16_t)screen);
    spread_form_row(image, form_row, shift, &mask, &data);
    if (span == SPAN_RIGHT_GROUP) {
        poke16(image, at, (uint16_t)sprite_op(op, screen, mask, data));
    } else {
        screen = sprite_op(op, screen << GROUP_BITS, mask, data);
        poke16(image, at, (uint16_t)(screen >> GROUP_BITS));
    }
    return save_at + WORD_BYTES;
}

/* $fcffb0 — $a00d draw_sprite. The ROM's order of reads and writes is kept, because a Line-A caller's
 * form and save block are its own memory: the colours and the XOR sign before STAT's long bit is
 * cleared, the hot spot after it; the save block's header after the clip; each row saved before its form
 * words are read.
 *
 * THE CLIP IS UNSIGNED (`bcs` after `sub.w`, `bhi` against DEV_TAB - 15), and a top clip starts the
 * form `(hot_y - y) * 4` bytes in by `suba.w`. Both loops are `dbf` entered AT the `dbf`: a count of 0
 * runs no pass and a negative one 65,535 or so — a hot spot 16 or more below y (only a Line-A caller's
 * own form can have one) saves a length of 0, which the restore then reads as 65,536 rows. */
TRANSCRIBED_CORE
void linea_draw_sprite(uint8_t *image, uint32_t form, uint32_t save_block, uint32_t x_register,
                       uint32_t y_register)
{
    uint16_t bg = peek16(image, form + SPRITE_FORM_BG);
    uint16_t fg = peek16(image, form + SPRITE_FORM_FG);
    unsigned ops = (int16_t)peek16(image, form + SPRITE_FORM_PLANES) < 0 ? SPRITE_OPS_XOR : 0;
    uint8_t *stat = image + bus_address(save_block + SPRITE_SAVE_STAT);
    uint16_t x, y, hot_x, hot_y, rows, planes, group_step, line;
    uint32_t rows_at = form + SPRITE_FORM_ROWS;
    uint32_t screen, save_at;
    enum sprite_span span;
    unsigned shift;

    *stat &= (uint8_t)~(1u << SPRITE_SAVE_LONG_BIT);
    hot_x = peek16(image, form + SPRITE_FORM_HOT_X);
    x = (uint16_t)((uint16_t)x_register - hot_x);
    if ((uint16_t)x_register < hot_x) {
        x = (uint16_t)(x + SPRITE_ROWS);
        span = SPAN_RIGHT_GROUP;
    } else if (x > (uint16_t)(table_uword(image, LINEA_DEV_TAB, VDI_DEV_TAB_MAX_X_INDEX) - SPRITE_EDGE)) {
        span = SPAN_LEFT_GROUP;
    } else {
        *stat |= 1u << SPRITE_SAVE_LONG_BIT;
        span = SPAN_BOTH_GROUPS;
    }

    hot_y = peek16(image, form + SPRITE_FORM_HOT_Y);
    y = (uint16_t)((uint16_t)y_register - hot_y);
    if ((uint16_t)y_register < hot_y) {
        rows = (uint16_t)(y + SPRITE_ROWS);
        rows_at -= word_index(y, SPRITE_FORM_ROW_BYTES);
        y = 0;
    } else if (y > (uint16_t)(table_uword(image, LINEA_DEV_TAB, VDI_DEV_TAB_MAX_Y_INDEX) - SPRITE_EDGE)) {
        rows = (uint16_t)(table_uword(image, LINEA_DEV_TAB, VDI_DEV_TAB_MAX_Y_INDEX) - y + 1);
    } else {
        rows = SPRITE_ROWS;
    }

    screen = be32(image + SYSVAR_V_BAS_AD) + sign_ext16((uint16_t)concat_offset(image, x, y));
    shift = x & PIXEL_IN_GROUP_MASK;
    planes = be16(image + LINEA_PLANES);
    group_step = (uint16_t)(planes * WORD_BYTES);
    line = be16(image + LINEA_WIDTH);
    wr32(image + bus_address(save_block + SPRITE_SAVE_ADDR), screen);
    poke16(image, save_block + SPRITE_SAVE_LEN, rows);
    *stat |= 1u << SPRITE_SAVE_VALID_BIT;
    save_at = save_block + SPRITE_SAVE_AREA;

    for (uint16_t planes_left = planes; planes_left != 0; planes_left--) {
        unsigned op = ops + (fg & 1u) * SPRITE_OP_FG + (bg & 1u) * SPRITE_OP_BG;
        uint32_t at = screen;

        fg >>= 1;
        bg >>= 1;
        for (uint16_t rows_left = rows; rows_left != 0; rows_left--) {
            save_at = sprite_row(image, span, at, group_step, save_at, op, rows_at, shift);
            rows_at += SPRITE_FORM_ROW_BYTES;
            at += sign_ext16(line);
        }
        rows_at -= word_index(rows, SPRITE_FORM_ROW_BYTES);
        screen += WORD_BYTES;
    }
}

/* The restore's three layouts, by PLANES: fewer than two (0 too — `subq.w #2` borrows), two, and
 * "more", which is FOUR — three or five-plus planes are restored as if they were four. */
#define UNDRAW_PLANES_TWO      2
#define UNDRAW_PLANES_MORE     4

/* One plane: a row is one word, or a longword moved WHOLE (`move.l (a1)+,(a0)`), then the line down. */
static void undraw_one_plane(uint8_t *image, uint32_t at, uint32_t saved, uint16_t line, uint16_t passes,
                             unsigned long_rows)
{
    do {
        if (long_rows) {
            uint32_t row = be32(image + bus_address(saved));

            wr32(image + bus_address(at), row);
            saved += sizeof(uint32_t);
        } else {
            poke16(image, at, peek16(image, saved));
            saved += WORD_BYTES;
        }
        at += sign_ext16(line);
    } while (passes-- != 0);
}

/* Two or four planes: each plane's saves start a fixed step after the one before, and a row writes the
 * planes' words interleaved as the screen holds them — both halves of a long row, in turn. The step is
 * `adda.w` of a word: two planes add rows * 2 once or twice, four add rows * 2 or rows * 4. */
static void undraw_interleaved(uint8_t *image, uint32_t at, uint32_t saved, uint16_t line, uint16_t passes,
                               unsigned long_rows, uint16_t rows, int two_planes)
{
    unsigned plane_count = two_planes ? UNDRAW_PLANES_TWO : UNDRAW_PLANES_MORE;
    uint16_t step = (uint16_t)(rows * WORD_BYTES);
    uint32_t plane_saved[UNDRAW_PLANES_MORE];
    uint32_t plane_offset;
    unsigned plane;

    if (two_planes)
        plane_offset = sign_ext16(step) << long_rows;
    else
        plane_offset = sign_ext16((uint16_t)(step << long_rows));
    for (plane = 0; plane < plane_count; plane++)
        plane_saved[plane] = saved + plane * plane_offset;
    do {
        uint32_t word_at = at;
        unsigned half;

        for (half = 0; half <= long_rows; half++) {
            for (plane = 0; plane < plane_count; plane++) {
                poke16(image, word_at, peek16(image, plane_saved[plane]));
                plane_saved[plane] += WORD_BYTES;
                word_at += WORD_BYTES;
            }
        }
        at += sign_ext16(line);
    } while (passes-- != 0);
}

/* $fd0184 — $a00c undraw_sprite: the saved words back, if the block holds a save (clearing the bit
 * either way), in one of the three layouts above. A row count of 0 is 65,536 passes (`subq.w #1`, then
 * a `dbf` at the loop's foot) — what a draw clipped to no rows leaves. */
TRANSCRIBED_CORE
void linea_undraw_sprite(uint8_t *image, uint32_t save_block)
{
    uint8_t *stat = image + bus_address(save_block + SPRITE_SAVE_STAT);
    uint8_t status = *stat;
    uint16_t rows, line, planes, passes;
    uint32_t at, saved;
    unsigned long_rows;

    *stat = status & (uint8_t)~(1u << SPRITE_SAVE_VALID_BIT);
    if (!(status & (1u << SPRITE_SAVE_VALID_BIT)))
        return;
    rows = peek16(image, save_block + SPRITE_SAVE_LEN);
    passes = (uint16_t)(rows - 1);
    line = be16(image + LINEA_WIDTH);
    at = be32(image + bus_address(save_block + SPRITE_SAVE_ADDR));
    saved = save_block + SPRITE_SAVE_AREA;
    planes = be16(image + LINEA_PLANES);
    long_rows = (*stat >> SPRITE_SAVE_LONG_BIT) & 1u;
    if (planes < UNDRAW_PLANES_TWO)
        undraw_one_plane(image, at, saved, line, passes, long_rows);
    else
        undraw_interleaved(image, at, saved, line, passes, long_rows, rows, planes == UNDRAW_PLANES_TWO);
}

/* ================================================================================================
 * The hide count.
 * ============================================================================================= */

/* $fd0254 — $a00a hide_mouse, and v_hide_c's body: one deeper, and on reaching 1 the sprite removed
 * and any position the ISR had queued forgotten. */
TRANSCRIBED_CORE
void linea_hide_mouse(uint8_t *image)
{
    image[LINEA_MOUSE_FLAG]++;
    wr16(image + LINEA_M_HID_CT, (uint16_t)(be16(image + LINEA_M_HID_CT) + 1));
    if (be16(image + LINEA_M_HID_CT) == 1) {
        linea_undraw_sprite(image, LINEA_SAVE_BLOCK);
        image[LINEA_CUR_FLAG] = 0;
    }
    image[LINEA_MOUSE_FLAG]--;
}

/* $fd0286 — one shallower, and on reaching 0 the sprite drawn at GCURX/GCURY. `subq.w` then `bgt` —
 * a signed compare of the depth with 1 — and `bmi` on the result's sign alone, so a depth below 0 is
 * put back to 0 undrawn, and $8000 (whose decrement overflows to $7fff) is DRAWN. */
TRANSCRIBED_CORE
void vdi_show_cursor(uint8_t *image)
{
    int16_t depth;

    image[LINEA_MOUSE_FLAG]++;
    depth = (int16_t)be16(image + LINEA_M_HID_CT);
    wr16(image + LINEA_M_HID_CT, (uint16_t)(depth - 1));
    if (depth <= 1) {
        if (!((uint16_t)(depth - 1) & SIGN_BIT16)) {
            linea_draw_sprite(image, LINEA_M_POS_HX, LINEA_SAVE_BLOCK, be16(image + LINEA_GCURX),
                              be16(image + LINEA_GCURY));
            image[LINEA_CUR_FLAG] = 0;
        }
        wr16(image + LINEA_M_HID_CT, 0);
    }
    image[LINEA_MOUSE_FLAG]--;
}

/* $fcb120 — v_show_c (122), and $a009: intin[0] = 0 means "show whatever the depth" — the depth is
 * forced to 1 first, unless it is already 0. */
void vdi_v_show_c(uint8_t *image)
{
    if (intin_word(image, 0) == 0 && be16(image + LINEA_M_HID_CT) != 0)
        wr16(image + LINEA_M_HID_CT, 1);
    vdi_show_cursor(image);
}

/* $fcb148 — v_hide_c (123). */
void vdi_v_hide_c(uint8_t *image)
{
    linea_hide_mouse(image);
}

/* A colour index as vsc_form maps it: `cmp.w DEV_TAB[13]` then `bmi` — the SIGN of the difference, not a
 * signed compare — so a very negative index reads BELOW MAP_COL (`0(a1,d0.w)`) where it survives. */
static uint16_t mapped_colour(const uint8_t *image, uint16_t index)
{
    if (!word_difference_is_negative(index, table_uword(image, LINEA_DEV_TAB, VDI_DEV_TAB_COLOURS_INDEX)))
        index = 1;
    return peek16(image, VDI_MAP_COL + word_index(index, WORD_BYTES));
}

/* $fd02ca — vsc_form (111), and $a00b: intin's hot spot (four bits each), planes word, the two colours
 * mapped, then the 16 mask words and 16 data words INTERLEAVED into MASK_FORM — each word read and
 * stored in turn, which only an intin laid over MASK_FORM shows. */
TRANSCRIBED_CORE
void vdi_vsc_form(uint8_t *image)
{
    uint32_t intin;
    unsigned row;

    image[LINEA_MOUSE_FLAG]++;
    intin = linea_pointer(image, LINEA_INTIN);
    wr16(image + LINEA_M_POS_HX, peek16(image, intin) & PIXEL_IN_GROUP_MASK);
    wr16(image + LINEA_M_POS_HY, peek16(image, intin + WORD_BYTES) & PIXEL_IN_GROUP_MASK);
    wr16(image + LINEA_M_PLANES, peek16(image, intin + 2 * WORD_BYTES));
    wr16(image + LINEA_M_CDB_BG, mapped_colour(image, peek16(image, intin + 3 * WORD_BYTES)));
    wr16(image + LINEA_M_CDB_FG, mapped_colour(image, peek16(image, intin + 4 * WORD_BYTES)));
    for (row = 0; row < SPRITE_ROWS; row++) {
        uint32_t mask_at = intin + (5 + row) * WORD_BYTES;
        uint32_t stored_at = LINEA_MASK_FORM + row * SPRITE_FORM_ROW_BYTES;

        wr16(image + stored_at, peek16(image, mask_at));
        wr16(image + stored_at + WORD_BYTES, peek16(image, mask_at + SPRITE_ROWS * WORD_BYTES));
    }
    image[LINEA_MOUSE_FLAG]--;
}

/* ================================================================================================
 * The interrupt paths.
 * ============================================================================================= */

/* A USER vector — `movea.l USER_x,a1 / jsr (a1)` — through `staged_call.h`'s register-carrying shape: D0
 * and D1 handed in and answered, A0 whatever the ISR or the previous routine left, the published contract of
 * USER_BUT and USER_MOT (whose routines answer in D0/D1) and of USER_CUR, which the ISR hands the position.
 * What no build hands a routine is the rest of the ISR's register file (D3 holds the sign-extended dy
 * during USER_MOT) — no routine TOS installs reads it, and a staged one that did would diverge, rightly. */
static void call_user_vector(uint8_t *image, uint32_t vector, uint32_t registers[STAGED_REGISTERS])
{
    call_vector_registers(image, be32(image + vector), registers);
}

/* clamp_mouse over the pair, high words kept. */
static void clamp_position(const uint8_t *image, uint32_t registers[STAGED_REGISTERS])
{
    vdi_clamp_mouse(image, registers[STAGED_D0], registers[STAGED_D1], registers);
}

static inline uint32_t low_word_into(uint32_t register_value, uint16_t low)
{
    return (register_value & HIGH_WORD) | low;
}

/* The IKBD numbers the right button bit 0; the VDI numbers the left one bit 0 ($fcfe4a lsr.b / bset). */
static inline uint8_t vdi_buttons(uint8_t header)
{
    uint8_t buttons = header & MOUSE_PACKET_BUTTONS_MASK;

    return (uint8_t)((buttons >> 1) | ((buttons & 1u) << 1));
}

static inline uint8_t rotate_byte_right(uint8_t value, unsigned count)
{
    return (uint8_t)((value >> count) | (value << (BYTE_BITS - count)));
}

/* The button arm: USER_BUT with the new buttons in D0 and the old in D1, its D0 answer the state, and
 * CUR_MS_STAT = that state with bits 6/7 saying which changed. What the ISR then does to D1's LOW word —
 * the pushed word popped back, the changed bits made in its low byte — no later reader sees: the motion
 * arm replaces the whole low word with GCURY. Its HIGH word stays the routine's, which USER_MOT and
 * USER_CUR are handed. */
static void report_buttons(uint8_t *image, uint32_t registers[STAGED_REGISTERS],
                           uint8_t previous)
{
    uint8_t answered, changed;

    call_user_vector(image, LINEA_USER_BUT, registers);
    wr16(image + LINEA_MOUSE_BT, (uint16_t)registers[STAGED_D0]);
    answered = (uint8_t)registers[STAGED_D0];
    changed = rotate_byte_right((uint8_t)(previous ^ answered), CHANGED_BITS_ROTATE);
    image[LINEA_CUR_MS_STAT] = answered | changed;
}

/* The motion arm: GCURX/GCURY moved by the packet's signed bytes, clamped, handed to USER_MOT, clamped
 * AGAIN (the routine may move it off screen), stored, and handed to USER_CUR. */
static void report_motion(uint8_t *image, uint32_t registers[STAGED_REGISTERS])
{
    uint32_t packet = registers[STAGED_A0];
    uint16_t x = be16(image + LINEA_GCURX);
    uint16_t y;

    x = (uint16_t)(x + (int8_t)image[bus_address(packet + MOUSE_PACKET_DX)]);
    registers[STAGED_D0] = low_word_into(registers[STAGED_D0], x);
    y = be16(image + LINEA_GCURY);
    y = (uint16_t)(y + (int8_t)image[bus_address(packet + MOUSE_PACKET_DY)]);
    registers[STAGED_D1] = low_word_into(registers[STAGED_D1], y);
    clamp_position(image, registers);
    call_user_vector(image, LINEA_USER_MOT, registers);
    clamp_position(image, registers);
    wr16(image + LINEA_GCURX, (uint16_t)registers[STAGED_D0]);
    wr16(image + LINEA_GCURY, (uint16_t)registers[STAGED_D1]);
    call_user_vector(image, LINEA_USER_CUR, registers);
}

/* $fcfe28 — the mouse ISR (KBDVECS' mousevec), A0 the IKBD's three-byte relative packet. Nothing while
 * MOUSE_FLAG is held, nothing for a packet whose header is not $f8..$fb; the button arm only when the
 * buttons differ from CUR_MS_STAT's; the motion arm only when dx | dy is not zero, and otherwise the
 * "moved" bit cleared. The packet is READ WHERE THE ROM READS IT — dx twice — and THROUGH THE A0 USER_BUT
 * HANDS BACK ($fcfe7e `move.b 1(a0),d0`), because a user routine may have written it, or moved A0, in
 * between; USER_MOT is handed that A0 and USER_CUR whatever USER_MOT left. */
TRANSCRIBED_CORE
void vdi_mouse_isr(uint8_t *image, uint32_t packet, uint32_t entry_d0, uint32_t entry_d1)
{
    uint32_t registers[STAGED_REGISTERS];
    uint8_t header, buttons, previous, moved;

    if (image[LINEA_MOUSE_FLAG] != 0)
        return;
    header = image[bus_address(packet)];
    if ((header & MOUSE_PACKET_HEADER_MASK) != MOUSE_PACKET_HEADER_MASK)
        return;
    buttons = vdi_buttons(header);
    previous = image[LINEA_CUR_MS_STAT] & MOUSE_STAT_BUTTONS_MASK;
    registers[STAGED_D0] = low_word_into(entry_d0, buttons);
    registers[STAGED_D1] = low_word_into(entry_d1, previous);
    registers[STAGED_A0] = packet;
    if (buttons != previous)
        report_buttons(image, registers, previous);
    moved = image[bus_address(registers[STAGED_A0] + MOUSE_PACKET_DX)];
    moved |= image[bus_address(registers[STAGED_A0] + MOUSE_PACKET_DY)];
    if (moved == 0) {
        image[LINEA_CUR_MS_STAT] &= (uint8_t)~(1u << MOUSE_STAT_MOVED_BIT);
        return;
    }
    image[LINEA_CUR_MS_STAT] |= 1u << MOUSE_STAT_MOVED_BIT;
    report_motion(image, registers);
}

/* $fcff0a — USER_CUR's default: while the cursor is shown, queue (D0, D1) for the VBL, masked. */
TRANSCRIBED_CORE
void vdi_default_user_cur(uint8_t *image, uint32_t x, uint32_t y)
{
    os_ipl_t mask;

    if (be16(image + LINEA_M_HID_CT) != 0)
        return;
    mask = os_ipl_raise();
    wr16(image + LINEA_CUR_X, (uint16_t)x);
    wr16(image + LINEA_CUR_Y, (uint16_t)y);
    image[LINEA_CUR_FLAG] |= 1u << CUR_FLAG_MOVED_BIT;
    os_ipl_restore(mask);
}

/* $fcff2a — _vblqueue[0]: unless MOUSE_FLAG is held, a queued position (the flag's bit taken) redrawn —
 * the old sprite restored, the new one drawn at CUR_X/CUR_Y, both read before the restore. */
TRANSCRIBED_CORE
void vdi_vbl_draw_cursor(uint8_t *image)
{
    uint8_t flag;
    uint32_t position;

    if (image[LINEA_MOUSE_FLAG] != 0)
        return;
    flag = image[LINEA_CUR_FLAG];
    image[LINEA_CUR_FLAG] = flag & (uint8_t)~(1u << CUR_FLAG_MOVED_BIT);
    if (!(flag & (1u << CUR_FLAG_MOVED_BIT)))
        return;
    position = be32(image + LINEA_CUR_X);
    linea_undraw_sprite(image, LINEA_SAVE_BLOCK);
    linea_draw_sprite(image, LINEA_M_POS_HX, LINEA_SAVE_BLOCK, sign_ext16((uint16_t)(position >> GROUP_BITS)),
                      sign_ext16((uint16_t)position));
}

/* XBIOS Initmous(mode, param, vector), as the two workstation calls make it — on target through the machine's
 * own `trap #14` (`xbios/xbios.h`, which pushes Initmous' function number 0 as the ROM does, `clr.w`). */
static void initmous(uint8_t *image, uint16_t mode, uint32_t param, uint32_t vector)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    xbios_initmous(image, mode, param, vector);
#else
    (void)image;
    xbios_trap_word_long_long(XBIOS_INITMOUS_FN, mode, param, vector);
#endif
}

/* $fca7f8 — the mouse's workstation half: the user vectors at their defaults (button and motion a bare
 * `rts`, the cursor `default_user_cur`), the arrow through vsc_form with INTIN lent to it, the state
 * cleared, the VBL's slot 0 taken, and the IKBD put in relative mode with this file's ISR. */
void vdi_mouse_init(uint8_t *image)
{
    uint32_t intin;

    wr32(image + LINEA_USER_BUT, VDI_ROM_USER_VECTOR_DEFAULT);
    wr32(image + LINEA_USER_MOT, VDI_ROM_USER_VECTOR_DEFAULT);
    wr32(image + LINEA_USER_CUR, VDI_ROM_DEFAULT_USER_CUR);
    intin = be32(image + LINEA_INTIN);
    wr32(image + LINEA_INTIN, VDI_DEFAULT_MOUSE_FORM);
    vdi_vsc_form(image);
    wr32(image + LINEA_INTIN, intin);
    wr16(image + LINEA_MOUSE_BT, 0);
    image[LINEA_CUR_MS_STAT] = 0;
    image[LINEA_MOUSE_FLAG] = 0;
    wr16(image + LINEA_CUR_X, 0);
    wr16(image + LINEA_CUR_Y, 0);
    image[LINEA_CUR_FLAG] = 0;
    wr32(image + bus_address(be32(image + SYSVAR_VBLQUEUE)), VDI_ROM_VBL_DRAW_CURSOR);
    initmous(image, INITMOUS_RELATIVE, VDI_INITMOUS_PARAMS, VDI_ROM_MOUSE_ISR);
}

/* $fca872 — the VBL's slot 0 emptied, and the IKBD's mouse off. */
void vdi_mouse_off(uint8_t *image)
{
    wr32(image + bus_address(be32(image + SYSVAR_VBLQUEUE)), 0);
    initmous(image, INITMOUS_DISABLE, MOUSE_INITMOUS_UNUSED, MOUSE_INITMOUS_UNUSED);
}

/* ================================================================================================
 * The polls, and the three input functions.
 * ============================================================================================= */

/* BIOS Bconstat / Bconin on the keyboard: the ROM's own `trap #13` on target, the core off it — handed
 * the D0 the dispatcher leaves, the routine's own address (`bios/bcon.h`). */
static uint32_t keyboard_status(uint8_t *image)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    return bios_bconstat(image, BIOS_BCONSTAT, CONSOLE_DEVICE);
#else
    (void)image;
    return bios_trap_device(BIOS_BCONSTAT_FN, CONSOLE_DEVICE);
#endif
}

static uint32_t keyboard_read(uint8_t *image)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    return bios_bconin(image, BIOS_BCONIN, CONSOLE_DEVICE);
#else
    (void)image;
    return bios_trap_device(BIOS_BCONIN_FN, CONSOLE_DEVICE);
#endif
}

/* A key into TERM_CH: its ASCII word OR its scancode byte shifted up (`swap` / `lsl.w #8` / `or.w`). */
static void read_key(uint8_t *image)
{
    uint32_t key = keyboard_read(image);

    wr16(image + LINEA_TERM_CH, (uint16_t)(key | (key >> GROUP_BITS << BYTE_BITS)));
}

/* $fca7ca — a key waiting? Read into TERM_CH if so. */
uint32_t vdi_poll_key(uint8_t *image)
{
    if ((uint16_t)keyboard_status(image) == 0)
        return POLL_NOTHING;
    read_key(image);
    return POLL_TERMINATED;
}

/* $fca7c0 — the choice "device": TERM_CH = 1, and D0 left as the caller had it. */
TRANSCRIBED_CORE
uint32_t vdi_poll_choice(uint8_t *image, uint32_t entry_d0)
{
    wr16(image + LINEA_TERM_CH, TERM_CH_CHOICE);
    return entry_d0;
}

/* $fca88a — the locator: a button that changed (TERM_CH $20 left, $21 right; CUR_MS_STAT kept to the
 * buttons and the moved bit), else a key, else the ISR's "moved" bit taken with GCURX/GCURY into X1/Y1.
 * The status byte is the one read BEFORE the keyboard poll: the ROM keeps it in D1 across `trap #13`,
 * which the console's status driver and the dispatcher leave alone. */
TRANSCRIBED_CORE
uint32_t vdi_poll_locator(uint8_t *image)
{
    uint8_t status = image[LINEA_CUR_MS_STAT];

    if (status & MOUSE_STAT_CHANGED_MASK) {
        wr16(image + LINEA_TERM_CH, status & (1u << MOUSE_STAT_LEFT_CHANGED_BIT) ? TERM_CH_LEFT_BUTTON
                                                                                  : TERM_CH_RIGHT_BUTTON);
        image[LINEA_CUR_MS_STAT] = status & MOUSE_STAT_KEPT_MASK;
        return POLL_TERMINATED;
    }
    if ((uint16_t)keyboard_status(image) != 0) {
        read_key(image);
        return POLL_TERMINATED;
    }
    if (!(status & (1u << MOUSE_STAT_MOVED_BIT)))
        return POLL_NOTHING;
    image[LINEA_CUR_MS_STAT] = status & (uint8_t)~(1u << MOUSE_STAT_MOVED_BIT);
    wr16(image + LINEA_X1, be16(image + LINEA_GCURX));
    wr16(image + LINEA_Y1, be16(image + LINEA_GCURY));
    return POLL_MOVED;
}

/* One pass of a REQUEST spin, through the kit's scheduled-write door (`sched.h`): what ends the spin is an
 * interrupt — a key into the IKBD ring, a button into CUR_MS_STAT — so each pass ticks the loop's WAIT SITE
 * (`addrs.h`), where a case's schedule lands that store before the poll reads it, and the cap refuses a case
 * whose store never comes rather than hanging the suite. `watched` is what the interrupt writes. On target
 * the tick is a bare read and the loop the ROM's own. 0 once the cap is spent: the case is void, and the
 * caller returns. */
static int request_pass(uint8_t *image, uint32_t site, uint32_t watched)
{
    uint32_t unused;

    return sched_poll32(image, watched, site, &unused);
}

static inline uint16_t term_ch_ascii(const uint8_t *image)
{
    return be16(image + LINEA_TERM_CH) & TERM_CH_ASCII_MASK;
}

/* ptsout[0] = X1, ptsout[1] = Y1, through the pointer read once. */
static void answer_x1_y1(uint8_t *image)
{
    uint32_t ptsout = linea_pointer(image, LINEA_PTSOUT);

    wr16(image + ptsout, be16(image + LINEA_X1));
    wr16(image + ptsout + WORD_BYTES, be16(image + LINEA_Y1));
}

/* $fcb002 — vdi_locator (28). It WRITES intin[0] = 1 in the caller's array, and GCURX/GCURY = ptsin[0].
 * REQUEST: the cursor forced on at depth 1 and drawn, then a spin until the poll answers 1 — a button
 * or a key; motion only moves X1/Y1 — the key's ASCII and X1/Y1 answered, and the cursor hidden again.
 * SAMPLE: one poll, answered by its arm; the fourth arm (3) is unreachable — no poll answers it. */
void vdi_locator(uint8_t *image)
{
    uint32_t ptsin, contrl;
    uint32_t answer;

    wr16(image + linea_pointer(image, LINEA_INTIN), 1);
    ptsin = linea_pointer(image, LINEA_PTSIN);
    wr16(image + LINEA_GCURX, be16(image + ptsin));
    wr16(image + LINEA_GCURY, be16(image + ptsin + WORD_BYTES));
    if (be16(image + LINEA_LOC_MODE) == 0) {
        wr16(image + LINEA_M_HID_CT, 1);
        vdi_show_cursor(image);
        do {
            if (!request_pass(image, VDI_LOCATOR_WAIT_SITE, LINEA_CUR_MS_STAT))
                return;
        } while ((uint16_t)vdi_poll_locator(image) != POLL_TERMINATED);
        contrl = linea_pointer(image, LINEA_CONTRL);
        wr16(image + contrl + CONTRL_N_INTOUT, 1);
        wr16(image + contrl + CONTRL_N_PTSOUT, 1);
        answer_intout(image, 0, term_ch_ascii(image));
        answer_x1_y1(image);
        linea_hide_mouse(image);
        return;
    }
    answer = vdi_poll_locator(image);
    contrl = linea_pointer(image, LINEA_CONTRL);
    wr16(image + contrl + CONTRL_N_PTSOUT, 1);
    wr16(image + contrl + CONTRL_N_INTOUT, 0);
    switch ((uint16_t)answer) {
    case POLL_NOTHING:
        wr16(image + contrl + CONTRL_N_PTSOUT, 0);
        break;
    case POLL_TERMINATED:
        wr16(image + contrl + CONTRL_N_PTSOUT, 0);
        wr16(image + contrl + CONTRL_N_INTOUT, 1);
        answer_intout(image, 0, term_ch_ascii(image));
        break;
    case POLL_MOVED:
        answer_x1_y1(image);
        break;
    case POLL_BOTH:
        wr16(image + contrl + CONTRL_N_INTOUT, 1);
        answer_x1_y1(image);
        break;
    default:
        break;
    }
}

/* $fcb1a0 — vdi_choice (30). Its poll ($fca7c0) never writes D0, so what it "answers" is the D0 the
 * DISPATCHER left — the MONO_STATUS word it stored last ($fcaae6), 0 or 8. So REQUEST mode SPINS FOR
 * EVER (it waits for a 1) and SAMPLE mode answers contrl[4] = 0 or 8 words with none written. The arms
 * for 1 and 2 are the ROM's all the same, and a case entered with D0 = MONO_STATUS = 1 or 2 runs them. */
void vdi_choice(uint8_t *image)
{
    uint32_t dispatcher_d0 = be16(image + LINEA_MONO_STATUS);
    uint16_t answer;

    if (be16(image + LINEA_CHC_MODE) == 0) {
        wr16(image + linea_pointer(image, LINEA_CONTRL) + CONTRL_N_INTOUT, 1);
        do {                                        /* nothing an interrupt writes ends it: D0 is fixed */
            if (!request_pass(image, VDI_CHOICE_WAIT_SITE, LINEA_TERM_CH))
                return;
        } while ((uint16_t)vdi_poll_choice(image, dispatcher_d0) != POLL_TERMINATED);
        answer_intout(image, 0, term_ch_ascii(image));
        return;
    }
    answer = (uint16_t)vdi_poll_choice(image, dispatcher_d0);
    wr16(image + linea_pointer(image, LINEA_CONTRL) + CONTRL_N_INTOUT, answer);
    if (answer == POLL_TERMINATED)
        answer_intout(image, 0, term_ch_ascii(image));
    else if (answer == POLL_MOVED)
        answer_intout(image, 1, term_ch_ascii(image));
}

/* $fcb22a — vdi_string (31): up to intin[0] keys into intout, the ASCII byte of each — or, for a
 * NEGATIVE count, its magnitude of whole scancode words (so $8000, whose `neg.w` stays negative, reads
 * none). REQUEST: waits for each key and stops at a RETURN, which is stored but not counted — and which
 * a whole-word read never sees, so it runs to its count. SAMPLE: stops at the first poll that finds no
 * key, and leaves TERM_CH unmasked. */
void vdi_string(uint8_t *image)
{
    int16_t count = intin_word(image, 0);
    uint16_t mask = TERM_CH_ASCII_MASK;
    int16_t stored = 0;

    if (count < 0) {
        count = (int16_t)-(uint16_t)count;
        mask = LOW_WORD;
    }
    if (be16(image + LINEA_STR_MODE) == 0) {
        wr16(image + LINEA_TERM_CH, 0);
        while (stored < count && be16(image + LINEA_TERM_CH) != TERM_CH_RETURN) {
            uint16_t key;

            do {
                if (!request_pass(image, VDI_STRING_WAIT_SITE, IOREC_IKBD + IOREC_TAIL))
                    return;
            } while ((uint16_t)vdi_poll_key(image) == POLL_NOTHING);
            key = be16(image + LINEA_TERM_CH) & mask;
            wr16(image + LINEA_TERM_CH, key);
            wr16(image + linea_pointer(image, LINEA_INTOUT) + (uint32_t)(int32_t)stored * WORD_BYTES, key);
            stored++;
        }
        if (be16(image + LINEA_TERM_CH) == TERM_CH_RETURN)
            stored--;
    } else {
        while (stored < count && (uint16_t)vdi_poll_key(image) != POLL_NOTHING) {
            wr16(image + linea_pointer(image, LINEA_INTOUT) + (uint32_t)(int32_t)stored * WORD_BYTES,
                 be16(image + LINEA_TERM_CH) & mask);
            stored++;
        }
    }
    wr16(image + linea_pointer(image, LINEA_CONTRL) + CONTRL_N_INTOUT, (uint16_t)stored);
}
