/* screen.c — pixel position <-> screen address (pos_to_screen @ 0x182a2, screen_to_pos @ 0x182d6).
 *
 * Every draw routine addresses the screen as (cell address, shift): the address of the 8-byte
 * 4-plane cell containing the pixel, plus how far into that cell's 16 pixels it sits.
 */
#include "machine.h"
#include "addrs.h"
#include "joust.h"

/* divu_w (joust.h) reproduces DIVU.W's overflow case: a quotient too wide for 16 bits sets V and
 * leaves the destination UNCHANGED. Neither routine here tests V, so such a dividend simply skips
 * the divide and carries forward. Only screen_to_pos's `divu.w #$a0` can reach it (an address more
 * than 0xa00000 past screen_base); pos_to_screen divides a zero-extended word, which never
 * overflows. */

/* pos_to_screen(x, y) -> the containing cell's address, and *shift = x within that cell.
 *
 * Both offsets are folded into the address with `adda.w`, which adds only the low word of the
 * product, SIGN-EXTENDED. So from y = 205 on, the row offset y*0xa0 passes 0x7fff and the address
 * runs backwards instead of down the screen. The game never draws below row 199, but the
 * reconstruction has to bend the same way.
 */
uint32_t pos_to_screen(const uint8_t *image, uint16_t x, uint16_t y, uint16_t *shift) {
    uint32_t addr = be32(image + A_screen_base);
    addr += sign_ext16((uint32_t)y * SCREEN_ROW_BYTES);          /* mulu.w #$a0 ; adda.w d0,a0 */

    uint32_t split = divu_w(x, CELL_PIXELS);                     /* divu.w #$10: cell and shift */
    *shift = (uint16_t)(split >> 16);                            /* swap d0 ; move.w d0,d1 */
    addr += sign_ext16((uint16_t)split * CELL_BYTES);            /* mulu.w #$8 ; adda.w d0,a0 */
    return addr;
}

/* ORIGINAL BUG, REPRODUCED FAITHFULLY. screen_to_pos scales the recovered cell index by
 * `mulu.w #$16` — 22 decimal — where a cell spans CELL_PIXELS = 16 pixels. 0x16 is the hex
 * spelling of 22, so this is almost certainly a decimal/hex slip for the 16 the inverse needs, and
 * it makes screen_to_pos fail to round-trip pos_to_screen for every x >= 16. The routine is
 * unreferenced in the whole image, so nothing in the game ever notices. Do NOT correct it: the
 * differential test compares against the shipped code, wrong scale and all. */
#define SCREEN_TO_POS_X_SCALE 0x16u

/* screen_to_pos(addr, shift) -> *x, *y: the inverse of pos_to_screen (modulo the bug above).
 * The offset from screen_base divides by the row length for y; its remainder divides by the cell
 * size for the cell index, which is scaled back up to pixels and offset by the shift. */
void screen_to_pos(const uint8_t *image, uint32_t addr, uint16_t shift, uint16_t *x, uint16_t *y) {
    uint32_t split = divu_w(addr - be32(image + A_screen_base), SCREEN_ROW_BYTES);
    *y = (uint16_t)split;                                        /* quotient = whole scanlines */

    uint32_t within_row = split >> 16;                           /* clr.w d0 ; swap d0 */
    uint32_t cell = divu_w(within_row, CELL_BYTES);
    *x = (uint16_t)((uint16_t)cell * SCREEN_TO_POS_X_SCALE + shift);   /* mulu.w #$16 ; add.w d1,d0 */
}

/* Stack ABI, shared by both routines: the caller pushes a 10-byte block that the routine reads
 * from 4(a7), and the results are written back into the same block. `args` is its image address. */
#define POS_ARG_ADDR  0u   /*  4(a7) .l — cell address: out of pos_to_screen, in to screen_to_pos */
#define POS_ARG_SHIFT 4u   /*  8(a7) .w — pixel shift within the cell, same direction as ADDR */
#define POS_ARG_X     6u   /* 10(a7) .w — x: in to pos_to_screen, out of screen_to_pos */
#define POS_ARG_Y     8u   /* 12(a7) .w — y: likewise */

void g_pos_to_screen(uint8_t *image, uint32_t args) {
    uint16_t shift;
    uint32_t addr = pos_to_screen(image, be16(image + args + POS_ARG_X),
                                  be16(image + args + POS_ARG_Y), &shift);
    wr32(image + args + POS_ARG_ADDR, addr);
    wr16(image + args + POS_ARG_SHIFT, shift);
}

void g_screen_to_pos(uint8_t *image, uint32_t args) {
    uint16_t x, y;
    screen_to_pos(image, be32(image + args + POS_ARG_ADDR),
                  be16(image + args + POS_ARG_SHIFT), &x, &y);
    wr16(image + args + POS_ARG_X, x);
    wr16(image + args + POS_ARG_Y, y);
}
