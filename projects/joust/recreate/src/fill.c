/* fill.c — the flat-fill primitives (make_fill_pattern @ 0x102fe, fill_pattern_n @ 0x10334).
 *
 * A flat fill writes the same two longwords into every 4-plane cell it covers: the first carries
 * planes 0 and 1, the second planes 2 and 3. make_fill_pattern builds that pair from a colour
 * index; fill_pattern_n is the count-driven loop that lays it down.
 */
#include "machine.h"
#include "joust.h"

/* DEGENERATE IN THE SHIPPED BINARY, AND REPRODUCED AS SUCH.
 *
 * The original is four consecutive `btst #0,d0 / beq / or.l #$ffff0000,d1` blocks at 0x10302,
 * 0x1030e, 0x1031a and 0x10326 that are byte-for-byte identical. Presumably each was meant to test
 * a different bit of the colour into a different plane, but all four test bit 0 and all four OR the
 * same constant into the same register, so the last three are no-ops — and D2, cleared on entry, is
 * never written at all. The net effect: only bit 0 of the colour survives, and only into plane 0,
 * making this a two-colour fill.
 *
 * This is the original code, not a depacker artifact, and the three repeats are not mid-entry
 * aliases (nothing anywhere in the image branches to 0x1030e / 0x1031a / 0x10326). All three
 * fill_screen call sites pass colour 0, so the game never exercises the difference. */
#define FILL_COLOUR_BIT  0x1u          /* btst #0,d0 — the only colour bit the routine reads */
#define FILL_PLANE0_SET  0xffff0000u   /* or.l #$ffff0000,d1 — plane 0 of the cell all ones */

void make_fill_pattern(uint32_t colour, uint32_t *planes01, uint32_t *planes23) {
    *planes01 = (colour & FILL_COLOUR_BIT) ? FILL_PLANE0_SET : 0;
    *planes23 = 0;
}

/* fill_pattern_n(count, planes01, planes23, dst) — write `count` cells from dst upward and return
 * the end pointer (A0 on return, the routine's only other output). The count is a `subq.w`
 * counter, so a count of 0 means 65536 cells rather than none.
 *
 * Unreferenced in the shipped image: a count-driven twin of the loop fill_screen carries inline. */
uint32_t fill_pattern_n(uint8_t *image, uint32_t dst, uint16_t count,
                        uint32_t planes01, uint32_t planes23) {
    unsigned passes = loop_passes(count, COUNT_MASK_WORD);
    for (unsigned i = 0; i < passes; i++) {
        wr32(image + dst, planes01);
        wr32(image + dst + 4, planes23);
        dst += CELL_BYTES;
    }
    return dst;
}

/* make_fill_pattern's outputs live in D1/D2, which an image diff cannot see, so the differential
 * test drives it through a 68000 stub that stores them (`move.l d1,(a0)+ / move.l d2,(a0)+`).
 * This glue mirrors that store at the same address — see test/abi.py. */
void g_make_fill_pattern(uint8_t *image, uint32_t colour, uint32_t result) {
    uint32_t planes01, planes23;
    make_fill_pattern(colour, &planes01, &planes23);
    wr32(image + result, planes01);
    wr32(image + result + 4, planes23);
}

/* Register ABI: D0 = count, D1/D2 = the cell pattern, A0 = destination. `count` arrives as a full
 * longword so a test can prove the high half is discarded, exactly as `subq.w` discards it. */
uint32_t g_fill_pattern_n(uint8_t *image, uint32_t dst, uint32_t count,
                          uint32_t planes01, uint32_t planes23) {
    return fill_pattern_n(image, dst, (uint16_t)count, planes01, planes23);
}
