/* draw.h — the drawing/blit layer's public API, its globals, and the 68000 shift semantics it
 * leans on.
 *
 * Addresses are Ghidra addresses (image offset + the 0x10000 load base) and mirror `var` lines in
 * ../../names.txt. The two globals every subsystem shares (A_screen_base, A_rng_ptr) live in
 * addrs.h; everything below is touched only by this layer, so it is declared here.
 */
#ifndef JOUST_DRAW_H
#define JOUST_DRAW_H

#include <stdint.h>

#include "addrs.h"

/* --- globals: the sprite-draw scratch the callers stage and the blitters read ---------------- */
#define A_playfield_bottom  0x10d60u  /* .l — screen address of the lava line; a sprite reaching it dies */

/* The three per-CELL suppressors the pterodactyl blitter tests. update_pterodactyl (0x1502a)
 * copies the record's edge counters into them, so a NONZERO byte means "skip that cell this row" —
 * which is how the sprite is clipped at the left and right screen edges. */
#define A_draw_clip_cell0   0x10d0eu  /* .b — suppresses the leading cell   (dst + 0) */
#define A_draw_clip_cell1   0x10d0fu  /* .b — suppresses the middle cell    (dst + 8) */
#define A_draw_clip_cell2   0x10d10u  /* .b — suppresses the trailing cell  (dst + 16) */

#define A_draw_dst          0x10de8u  /* .l */
#define A_draw_src          0x10df0u  /* .l */
#define A_draw_dst_off      0x10df8u  /* .w — folded in with adda.w, i.e. SIGN-extended */
#define A_draw_half_select  0x10dc2u  /* .b — bit1 skips the leading pass, bit0 the wrap column */

/* WIDTH CLASH, FAITHFULLY REPRODUCED. draw_shift and draw_rows are read as BYTES by the rider
 * blitters (draw_object_data) and as WORDS by the pterodactyl one (blit_sprite_planes) — and a
 * byte read at the word's address takes its HIGH half, so the two readings do not even agree on
 * which half carries the value. The writers split the same way (0x131b4 stores a byte, 0x15006 a
 * word), so each subsystem is self-consistent and the clash only shows if they interleave. Each
 * reconstruction below reads exactly the width its own instruction reads. */
#define A_draw_shift        0x10df4u  /* .b here, .w in blit_sprite_planes */
#define A_draw_rows         0x10df6u  /* .b here, .w in blit_sprite_planes */

/* --- globals: the text engine ---------------------------------------------------------------- */
#define A_text_ptr          0x10e0au  /* .l — screen address of the next character cell */
#define A_text_shift        0x10e0eu  /* .b — pixels into that cell */
#define A_text_color        0x10e0fu  /* .b — one bit per bitplane: set = OR the glyph in */
#define A_text_bg_color     0x10e10u  /* .b — likewise for the background bar */
#define A_text_flags        0x10e11u  /* .b — see TEXT_FLAG_* */
#define A_text_x            0x10e12u  /* .w */
#define A_text_y            0x10e14u  /* .w */

/* --- the two glyph tables draw_string indexes, one byte per row per character from ' ' up ------ */
#define A_font_small        0x18192u  /* 5 rows of 4 px */
#define A_font_large        0x17ebau  /* 8 rows of 6 px */

/* --- the two object identities select_sprite_base compares against; everything else is an enemy - */
#define A_object_table      0x10f36u  /* player 1's object slot, and the table's base */
#define A_player2           0x10f84u  /* player 2's object slot */

/* Bitplane words in one 4-plane cell. joust.h fixes the cell in bytes (CELL_BYTES); every routine
 * here walks it plane by plane instead, two bytes at a time. */
#define CELL_PLANE_WORDS  4u

/* --- 68000 shift/rotate with a register count ------------------------------------------------- */
/* The CPU takes the count from the low 6 bits of the count register, then performs that many
 * single-bit steps. For a shift that means anything >= 32 clears the register; for a rotate, n
 * steps of a longword is n mod 32, so the top bit of the count never matters. */
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

/* --- text engine ------------------------------------------------------------------------------ */
#define TEXT_FLAG_BACKGROUND  0x10u  /* bit4: paint the background bar behind each glyph */
#define TEXT_FLAG_LARGE_FONT  0x80u  /* bit7: the 8-row font rather than the 5-row one */

/* --- object record fields (see the object_table comment in ../../names.txt) -------------------- */
#define OBJ_FLAGS       0x00u  /* .w */
#define OBJ_X           0x02u  /* .w */
#define OBJ_PREV_X      0x10u  /* .w */
#define OBJ_PREV_DST    0x14u  /* .l */
#define OBJ_PREV_SRC    0x18u  /* .l */
#define OBJ_PREV_ROWS   0x1cu  /* .b */
#define OBJ_PREV_SHIFT  0x1du  /* .b */

#define OBJ_FLAG_IN_LAVA  0x0100u  /* bit8: the sprite reached playfield_bottom while being drawn */

/* --- the pterodactyl record blit_mask_wide reads ---------------------------------------------- */
#define PTERO_DST_BASE  0x02u   /* .l — added to screen_base */
#define PTERO_SRC       0x06u   /* .l — the sprite set; the erase mask sits PTERO_MASK_OFF in */
#define PTERO_SHIFT     0x0au   /* .w */
#define PTERO_DST_OFF   0x16u   /* .w — SIGN-extended (adda.w) */
#define PTERO_ROWS      0x18u   /* .w — signed; <= 0 draws nothing */
#define PTERO_MASK_OFF  0x120u
#define PTERO_MASK_ROW_BYTES 8u /* two longwords consumed per row (`move.l (a2)+` twice) */

/* --- the ground-animation record blit_sprite / blit_sprite_mask read (a5) ---------------------- */
#define SPR_SRC         0x00u   /* .l — data rows; the AND mask sits SPR_MASK_OFF in */
#define SPR_DST_OFF     0x04u   /* .l — added to screen_base */
#define SPR_SHIFT       0x08u   /* .w */
#define SPR_CELL_SELECT 0x0au   /* .w — only its LOW byte is tested, as a signed byte. `blt` skips
                                 *      the trailing cell and `bgt` the leading one, so < 0 draws
                                 *      the LEADING cell alone, > 0 the TRAILING one, and 0 both. */
#define SPR_MASK_OFF    0x90u

/* --- draw.c ----------------------------------------------------------------------------------- */
void fill_screen(uint8_t *image, uint16_t colour);
void draw_string(uint8_t *image, uint32_t string);
uint32_t select_sprite_base(uint32_t object, uint32_t flags);
void blit_pattern_rows(uint8_t *image, uint32_t dst, uint32_t plane_select,
                       uint32_t row0, uint32_t row1, uint32_t row2);
void draw_object_data(uint8_t *image, uint32_t object);
void draw_object_mask(uint8_t *image, uint32_t object);
void blit_mask_wide(uint8_t *image, uint32_t record);
void blit_sprite_planes(uint8_t *image);
void paint_floor_row(uint8_t *image, uint32_t row);
void blit_sprite_mask(uint8_t *image, uint32_t record, uint16_t rows);
void blit_sprite(uint8_t *image, uint32_t record, uint16_t rows);

#endif /* JOUST_DRAW_H */
