/* joust.h — the reconstruction's public API, plus what more than one subsystem shares: the screen
 * geometry, the 68000 primitives, and the object record.
 *
 * Joust runs on a 320x200 Atari ST low-resolution screen: 16 colours from four interleaved
 * bitplanes. Pixels are grouped into 16-pixel cells of four bitplane words, and every routine
 * here steps in whole cells, so the four constants below fix the entire memory layout.
 *
 * What belongs here is what two or more layers need; anything one layer owns stays in its own
 * header (draw.h, object.h, ...). The globals shared by address live in addrs.h instead.
 */
#ifndef JOUST_H
#define JOUST_H

#include <stdint.h>

#define SCREEN_ROW_BYTES 0xa0u   /* 160: one low-res scanline (320 px / 16 px per cell * 8 bytes) */
#define CELL_PIXELS      16u     /* pixels spanned by one 4-plane cell */
#define CELL_BYTES       8u      /* bytes in one 4-plane cell (four bitplane words) */
#define CELL_PLANE_WORDS 4u      /* those four words, the unit every plane-by-plane blit counts in
                                  * (`moveq #$4` in the original) */

/* ================================================================================================
 * 68000 semantics the reconstructions lean on.
 * ============================================================================================= */

/* The 68000 counts a loop down with `subq` + `bne`, which tests only the operand size: the loop
 * always runs at least once, and a zero count wraps to the full range of that size. */
#define COUNT_MASK_BYTE  0xffu     /* `subq.b #1,dn`: 0 means 256 passes */
#define COUNT_MASK_WORD  0xffffu   /* `subq.w #1,dn`: 0 means 65536 passes */

static inline unsigned loop_passes(uint32_t count, uint32_t size_mask) {
    return ((count - 1u) & size_mask) + 1u;
}

/* A shift or rotate with a register count takes that count from the low 6 bits of the register,
 * then performs that many single-bit steps. For a shift that means anything >= 32 clears the
 * register; for a rotate, n steps of a longword is n mod 32, so the top bit never matters.
 *
 * The count's WIDTH is the caller's business, not this code's: the drawing layer feeds lsr32 a word
 * read of draw_shift and the object layer a byte read of the same address (see addrs.h), so each
 * call site passes a value of exactly the width its own instruction read. */
#define SHIFT_COUNT_MASK   0x3fu
#define ROTATE_COUNT_MASK  0x1fu

static inline uint32_t lsr32(uint32_t value, uint32_t count) {
    count &= SHIFT_COUNT_MASK;
    return count >= 32u ? 0u : value >> count;
}

static inline uint32_t ror32(uint32_t value, uint32_t count) {
    count &= ROTATE_COUNT_MASK;
    return count ? (value >> count) | (value << (32u - count)) : value;
}

/* DIVU.W leaves the destination as (remainder << 16) | quotient — unless the quotient would not fit
 * in 16 bits, in which case V is set and the destination is left UNCHANGED. No caller tests V, so
 * an out-of-range dividend simply carries forward undivided. */
static inline uint32_t divu_w(uint32_t dividend, uint16_t divisor) {
    uint32_t quotient = dividend / divisor;
    if (quotient > 0xffffu) return dividend;
    return ((dividend % divisor) << 16) | quotient;
}

/* ================================================================================================
 * The object record (0x4e bytes, object_table) — read by the drawing layer and the object layer
 * alike, so the layout is fixed once here. ../../names.txt documents the whole record; a field
 * earns a name here when a routine that uses it is ported.
 * ============================================================================================= */
#define OBJ_FLAGS           0x00u   /* .w */
#define OBJ_X               0x02u   /* .w */
#define OBJ_Y               0x04u   /* .w */
#define OBJ_VX              0x06u   /* .w */
#define OBJ_VY              0x08u   /* .w */
#define OBJ_ANIM_TIMER      0x0au   /* .b */
#define OBJ_STEP_TIMER      0x0bu   /* .b */
#define OBJ_FLAP_FRAME      0x0eu   /* .w */
#define OBJ_PREV_X          0x10u   /* .w */
#define OBJ_PREV_DST        0x14u   /* .l — last drawn screen address */
#define OBJ_PREV_SRC        0x18u   /* .l */
#define OBJ_PREV_ROWS       0x1cu   /* .b */
#define OBJ_PREV_SHIFT      0x1du   /* .b */
#define OBJ_EGG_STATE       0x1eu   /* .b */
#define OBJ_EGG_X           0x20u   /* .w */
#define OBJ_EGG_DST         0x2au   /* .l — screen address the egg sprite was drawn at */
#define OBJ_EGG_SRC         0x2eu   /* .l */
#define OBJ_EGG_ROWS        0x32u   /* .b */
#define OBJ_EGG_SHIFT       0x33u   /* .b */
#define OBJ_SIZE            0x4eu

#define OBJ_FLAG_RESPAWN       (1u << 7)   /* awaiting respawn */
#define OBJ_FLAG_IN_LAVA       0x0100u     /* bit8: the sprite reached playfield_bottom while being drawn */
#define OBJ_FLAG_ON_PLATFORM   (1u << 9)   /* standing on a platform */
#define OBJ_FLAG_FACING_RIGHT  0x8000u     /* bit15 — `btst #15,d0`, a bit test on the whole longword */

/* --- rng.c --- */
void rng_advance(uint8_t *image, uint32_t mix);

/* --- screen.c --- */
uint32_t pos_to_screen(const uint8_t *image, uint16_t x, uint16_t y, uint16_t *shift);
void screen_to_pos(const uint8_t *image, uint32_t addr, uint16_t shift, uint16_t *x, uint16_t *y);

/* --- fill.c --- */
void make_fill_pattern(uint32_t colour, uint32_t *planes01, uint32_t *planes23);
uint32_t fill_pattern_n(uint8_t *image, uint32_t dst, uint16_t count,
                        uint32_t planes01, uint32_t planes23);

/* --- blit.c --- */
void blit_copy(uint8_t *image, uint32_t dst, uint32_t src, uint16_t cols, uint16_t rows);
void blit_or(uint8_t *image, uint32_t dst, uint32_t src, uint16_t cols, uint16_t rows);
void blit_andnot(uint8_t *image, uint32_t dst, uint32_t src, uint16_t cols, uint16_t rows);

#endif /* JOUST_H */
