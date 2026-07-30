/* object.c — Joust's object / physics / collision layer.
 *
 * Everything here works on the 0x4e-byte object record (or the pterodactyl's 0x20-byte one) and on
 * the four static tables that describe the playfield: platform_table (the landable boxes),
 * platform_edge_table (the bump boxes at their ends), platform_sprites (the bitmaps, which double
 * as the pixel-collision surface) and platform_present (which of them exist this wave).
 *
 * Collision is two-stage. test_overlap is the broad phase over two boxes staged in
 * hit_box_a / hit_box_b; when their scanline bands overlap it aligns both sprites onto the same
 * screen column and hands each column to pixel_collision, which ORs the four plane words of a row
 * together and looks for a shared bit.
 */
#include "machine.h"
#include "addrs.h"
#include "joust.h"
#include "object.h"
#include "sound.h"   /* ptero_spot_player calls play_sound */

/* ------------------------------------------------------------------ pixel_collision @ 0x13fe6 */

/* The four plane words of one cell, OR-ed into a single 16-bit occupancy mask. */
static uint16_t or_planes(const uint8_t *image, uint32_t src) {
    uint16_t mask = 0;
    for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++) mask |= be16(image + src + plane * 2u);
    return mask;
}

/* The 32-bit value the original builds in D4/D5 for one sprite row: this cell's mask in the low
 * half and, when `spill` holds, the PREVIOUS cell's mask in the high half — so the shift below
 * pulls in the bits that a shifted sprite spills across the cell boundary. With no shift, or on the
 * sprite's first column, there is no previous cell and the high half stays zero. */
static uint32_t row_mask(const uint8_t *image, uint32_t src, int spill) {
    uint32_t mask = or_planes(image, src);
    if (spill) mask |= (uint32_t)or_planes(image, src - CELL_BYTES) << 16;
    return mask;
}

/* pixel_collision(box_a = A1, box_b = A2) — walk hit_rows rows of the two sprites, already aligned
 * on a shared column by test_overlap, and stop at the first row whose shifted masks share a bit.
 *
 * On a hit it sets collision_hit and parks box_a's column cursor at COLS - 1, so that test_overlap's
 * `addq.w #1` immediately ends its column loop. It never advances the boxes' own HB_SRC fields —
 * that is test_overlap's job.
 */
void pixel_collision(uint8_t *image, uint32_t box_a, uint32_t box_b) {
    uint32_t src_a = be32(image + box_a + HB_SRC);          /* a3 */
    uint32_t src_b = be32(image + box_b + HB_SRC);          /* a4 */
    uint8_t shift_a = image[box_a + HB_SHIFT];              /* d2 */
    uint8_t shift_b = image[box_b + HB_SHIFT];              /* d3 */
    uint16_t cols_a = be16(image + box_a + HB_COLS);
    uint16_t cols_b = be16(image + box_b + HB_COLS);
    /* The original re-tests both cursors every row; nothing in the loop writes them (the hit path
     * returns straight out), so hoisting the two conditions is exact. The `shift != 0` half is
     * faithful but unobservable: at shift 0 the spilled half never reaches the compared low word,
     * so dropping it changes only which bytes are READ, and the differential compares writes. */
    int spill_a = be16(image + box_a + HB_CUR_COL) != 0 && shift_a != 0;
    int spill_b = be16(image + box_b + HB_CUR_COL) != 0 && shift_b != 0;

    unsigned rows = loop_passes(image[A_hit_rows], COUNT_MASK_BYTE);   /* subq.b: 0 means 256 */
    while (rows--) {
        uint16_t pixels_a = (uint16_t)lsr32(row_mask(image, src_a, spill_a), shift_a);
        uint16_t pixels_b = (uint16_t)lsr32(row_mask(image, src_b, spill_b), shift_b);
        if (pixels_a & pixels_b) {
            image[A_collision_hit] = COLLISION_HIT_SET;
            wr16(image + box_a + HB_CUR_COL, (uint16_t)(cols_a - 1u));
            return;
        }
        /* adda.w: only the low word of COLS * CELL_BYTES reaches the pointer, sign-extended. */
        src_a += sign_ext16(cols_a * CELL_BYTES);
        src_b += sign_ext16(cols_b * CELL_BYTES);
    }
}

/* ---------------------------------------------------------------------- test_overlap @ 0x13ef2 */

/* test_overlap() — broad phase for the two boxes staged in hit_box_a / hit_box_b.
 *
 * The boxes are first ordered by screen address, so `upper` is the one higher up the screen. If the
 * upper box's scanline band does not reach the lower box's top, there is nothing to test. Otherwise
 * both sprites are wound forward to the first shared row and the first shared column, and every
 * column from there on is handed to pixel_collision. Both boxes are MUTATED in place: HB_SRC and
 * HB_CUR_COL are the loop's cursors.
 */
void test_overlap(uint8_t *image) {
    image[A_collision_hit] = 0;

    uint32_t upper = A_hit_box_a, lower = A_hit_box_b;      /* a1, a2 — `exg` orders them */
    if ((int32_t)be32(image + A_hit_box_a) > (int32_t)be32(image + A_hit_box_b)) {
        upper = A_hit_box_b;
        lower = A_hit_box_a;
    }

    /* Scanline-band test. `add.b` folds the row count into the LOW BYTE of the y word with no
     * carry, so a box whose y low byte plus its rows passes 0xff wraps inside the byte instead of
     * moving down the screen. Faithful, and the game's y values stay well inside one byte. */
    uint16_t upper_y = be16(image + upper + HB_Y);
    uint16_t upper_bottom = set_low_byte(upper_y, (uint8_t)(upper_y + image[upper + HB_ROWS]));
    if ((int16_t)upper_bottom <= (int16_t)be16(image + lower + HB_Y)) return;

    /* Column offset between the two sprites: the byte gap between their cells, modulo one scanline,
     * divided by the cell size. divu.w's remainder is the within-row part of the gap. */
    uint32_t row_split = divu_w(be32(image + lower + HB_DST) - be32(image + upper + HB_DST),
                                SCREEN_ROW_BYTES);
    uint32_t col_delta = (row_split >> 16) / CELL_BYTES;

    wr16(image + upper + HB_CUR_COL, 0);
    wr16(image + lower + HB_CUR_COL, 0);
    if ((uint16_t)col_delta < be16(image + upper + HB_COLS)) {
        wr16(image + upper + HB_CUR_COL, (uint16_t)col_delta);   /* lower starts inside upper */
    } else {
        /* Too far right to be inside the upper sprite: measure the gap the other way round, back
         * from the end of the scanline (`sub.w #$14` + `neg.w`). */
        uint16_t back = (uint16_t)(CELLS_PER_ROW - (uint16_t)col_delta);
        if (back >= be16(image + lower + HB_COLS)) return;
        wr16(image + lower + HB_CUR_COL, back);
    }

    /* How many of the upper sprite's rows the lower sprite's top reaches into, clamped below to the
     * lower sprite's own height. Byte-wide, so pixel_collision's `subq.b` count sees it as-is. */
    image[A_hit_rows] = (uint8_t)(image[upper + HB_ROWS] + be16(image + upper + HB_Y)
                                  - be16(image + lower + HB_Y));

    /* Wind the upper sprite past the rows above the overlap, then both onto their shared column.
     * The original spends two separate `add.l d1,4(a1)`s on the upper box, one per term; folding
     * them into a single add is exact — the intermediate is never read, and both wrap mod 2^32. */
    uint8_t skipped = (uint8_t)(image[upper + HB_ROWS] - image[A_hit_rows]);
    wr32(image + upper + HB_SRC, be32(image + upper + HB_SRC)
         + (uint32_t)skipped * be16(image + upper + HB_COLS) * CELL_BYTES
         + (uint32_t)be16(image + upper + HB_CUR_COL) * CELL_BYTES);
    wr32(image + lower + HB_SRC, be32(image + lower + HB_SRC)
         + (uint32_t)be16(image + lower + HB_CUR_COL) * CELL_BYTES);

    if ((int8_t)image[A_hit_rows] > (int8_t)image[lower + HB_ROWS])
        image[A_hit_rows] = image[lower + HB_ROWS];

    for (;;) {
        pixel_collision(image, upper, lower);
        wr16(image + upper + HB_CUR_COL, (uint16_t)(be16(image + upper + HB_CUR_COL) + 1u));
        wr16(image + lower + HB_CUR_COL, (uint16_t)(be16(image + lower + HB_CUR_COL) + 1u));
        wr32(image + upper + HB_SRC, be32(image + upper + HB_SRC) + CELL_BYTES);
        wr32(image + lower + HB_SRC, be32(image + lower + HB_SRC) + CELL_BYTES);
        if (be16(image + upper + HB_COLS) == be16(image + upper + HB_CUR_COL)) return;
        if (be16(image + lower + HB_COLS) == be16(image + lower + HB_CUR_COL)) return;
    }
}

/* ---------------------------------------------------------------------- joust_bounce @ 0x140fe */

/* The two thresholds of joust_bounce's wrap-aware "which rider is on the right?" compare. x wraps
 * at the 320-pixel playfield width, so a gap of -19 or less really means A is on the right by
 * gap + 320; the 18-pixel dead band either side is about one rider's width. */
#define BOUNCE_GAP_NEAR_LEFT  0xffeeu   /* cmpi.w #$ffee + bcc: gap in [-18,-1] -> A is on the left */
#define BOUNCE_GAP_FAR_RIGHT  0x12eu    /* cmpi.w #$12e  + bge: gap >= 320-18 wraps to A on the left */

/* `neg.w 6(an)` — point a rider's horizontal velocity the way the bounce sends it, if it is not
 * already going that way. Only written when it actually flips, as the original does; a velocity of
 * exactly 0 is therefore left alone, which the differential cannot pin either way because `neg.w`
 * of 0 would store the same 0 back. */
static void force_velocity_sign(uint8_t *image, uint32_t object, int want_positive) {
    int16_t vx = (int16_t)be16(image + object + OBJ_VX);
    if (want_positive ? vx < 0 : vx > 0)
        wr16(image + object + OBJ_VX, (uint16_t)(0u - (uint32_t)(uint16_t)vx));
}

/* joust_bounce(obj_a = A0, obj_b = A3, flags_a = D0, flags_b = D1) — a drawn joust.
 *
 * Neither rider wins (collision_check decides that; this is only reached when their heights tie),
 * so both are turned away from each other and pushed apart. The facing bit and the sign of the
 * horizontal velocity are set together, and the updated flags words are stored back.
 */
void joust_bounce(uint8_t *image, uint32_t obj_a, uint32_t obj_b, uint16_t flags_a, uint16_t flags_b) {
    int16_t gap = (int16_t)(be16(image + obj_a + OBJ_X) - be16(image + obj_b + OBJ_X));
    int a_on_right = (uint16_t)gap < BOUNCE_GAP_NEAR_LEFT && gap < (int16_t)BOUNCE_GAP_FAR_RIGHT;

    if (a_on_right) {
        flags_a |= OBJ_FLAG_FACING_RIGHT;
        flags_b &= (uint16_t)~OBJ_FLAG_FACING_RIGHT;
    } else {
        flags_a &= (uint16_t)~OBJ_FLAG_FACING_RIGHT;
        flags_b |= OBJ_FLAG_FACING_RIGHT;
    }
    force_velocity_sign(image, obj_a, a_on_right);
    force_velocity_sign(image, obj_b, !a_on_right);

    wr16(image + obj_a + OBJ_FLAGS, flags_a);
    wr16(image + obj_b + OBJ_FLAGS, flags_b);
}

/* --------------------------------------------------------------------- check_platform @ 0x13300 */

#define PLATFORM_FLAP_FRAME_LOW  4u   /* mid-flap the rider's feet sit one pixel lower */
#define PLATFORM_WALK_ANIM_RESET 3u   /* anim/step timers restarted when the rider leaves a platform */
#define PLATFORM_WALK_STEP_RESET 5u

/* check_platform(object = A0, flags = D0) -> flags (D0) — is this object standing on a platform?
 *
 * Scans the platforms present this wave for one whose box contains the object's (x, y). On a hit the
 * object is snapped down onto the platform's top edge and bit 9 is set; otherwise bit 9 is cleared
 * and, if it had been set, the walk animation is restarted and the fall speed zeroed.
 */
uint32_t check_platform(uint8_t *image, uint32_t object, uint32_t flags) {
    uint32_t present = A_platform_present;
    for (uint32_t plat = A_platform_table; plat != A_platform_table_END;
         plat += PLAT_RECORD, present++) {
        if (image[present] == 0) continue;                  /* absent this wave */
        int16_t y = (int16_t)be16(image + object + OBJ_Y);
        if (y < (int16_t)be16(image + plat + PLAT_Y0) || y > (int16_t)be16(image + plat + PLAT_Y1))
            continue;
        int16_t x = (int16_t)be16(image + object + OBJ_X);
        if (x < (int16_t)be16(image + plat + PLAT_X0) || x > (int16_t)be16(image + plat + PLAT_X1))
            continue;

        wr16(image + object + OBJ_Y, be16(image + plat + PLAT_Y0));
        if (be16(image + object + OBJ_FLAP_FRAME) == PLATFORM_FLAP_FRAME_LOW)
            wr16(image + object + OBJ_Y, (uint16_t)(be16(image + object + OBJ_Y) + 1u));
        return flags | OBJ_FLAG_ON_PLATFORM;
    }

    if (!(flags & OBJ_FLAG_ON_PLATFORM)) return flags;      /* was not standing, still is not */
    image[object + OBJ_ANIM_TIMER] = PLATFORM_WALK_ANIM_RESET;
    wr16(image + object + OBJ_FLAP_FRAME, 0);
    image[object + OBJ_STEP_TIMER] = PLATFORM_WALK_STEP_RESET;
    wr16(image + object + OBJ_VY, 0);
    return flags & ~OBJ_FLAG_ON_PLATFORM;
}

/* ------------------------------------------------------------------- the egg sprite blits -----
 * (each carries its own address below: erase_egg_sprite @ 0x129b4, draw_egg_sprite @ 0x12914)
 *
 * The egg is a one-cell sprite drawn at a pixel shift, so each row takes two passes: the main pass
 * writes the bits that stay inside the cell, and the wrap pass writes the bits that spilled out of
 * it into the cell to its right (or, once the egg's x has reached EGG_WRAP_X, into the cell one
 * scanline back — the screen's right edge wraps onto the next row's left edge). Both passes read
 * the SAME four plane words per row; the source row stride is EGG_SRC_ROW_BYTES, of which only the
 * first four words are ever read.
 */
#define EGG_WRAP_X          0x130u   /* cmpi.w #$130: at/after this x the spill lands a row back */
#define EGG_SRC_ROW_BYTES   0x10u    /* 4 plane words consumed + `adda.w #$8` skipped */

enum egg_pass { EGG_PASS_MAIN, EGG_PASS_WRAP };
enum egg_combine { EGG_MASK_OUT, EGG_OR_IN };    /* not.w + and.w (erase) vs or.w (draw) */

static void egg_blit_row(uint8_t *image, uint32_t dst, uint32_t src, uint8_t shift,
                         enum egg_pass pass, enum egg_combine combine) {
    for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++, dst += 2u, src += 2u) {
        uint32_t word = be16(image + src);
        /* The wrap pass swaps the word into the HIGH half first, so the shift leaves exactly the
         * bits that fell off the end of the cell. */
        uint16_t bits = (uint16_t)lsr32(pass == EGG_PASS_WRAP ? word << 16 : word, shift);
        uint16_t screen = be16(image + dst);
        wr16(image + dst, combine == EGG_OR_IN ? (uint16_t)(screen | bits)
                                               : (uint16_t)(screen & (uint16_t)~bits));
    }
}

/* Where the wrap pass starts: one cell right of the sprite, or a scanline back once x has reached
 * the wrap point. `x` is the egg's own x (erase) or draw_x (draw). */
static uint32_t egg_wrap_dst(uint32_t dst, uint16_t x) {
    dst += CELL_BYTES;
    if ((int16_t)x >= (int16_t)EGG_WRAP_X) dst -= SCREEN_ROW_BYTES;
    return dst;
}

/* One row on. The 68000 leaves both pointers 8 bytes along (the four `(a1)+` / `(a2)+` writes) and
 * then completes each stride with `adda.w #$98` / `adda.w #$8`; the totals are one screen scanline
 * and one source row. egg_blit_row takes its pointers by value, so the whole stride lands here. */
static void egg_advance_row(uint32_t *dst, uint32_t *src) {
    *dst += SCREEN_ROW_BYTES;
    *src += EGG_SRC_ROW_BYTES;
}

/* erase_egg_sprite @ 0x129b4 (object = A0) — AND-NOT the egg back out of the screen, from the
 * address, source, height and shift the last draw recorded in the object record. It allocates
 * nothing (the name it carried before the body was read was `alloc_object`). */
void erase_egg_sprite(uint8_t *image, uint32_t object) {
    uint8_t shift = image[object + OBJ_EGG_SHIFT];
    uint32_t dst = be32(image + object + OBJ_EGG_DST);
    uint32_t src = be32(image + object + OBJ_EGG_SRC);

    for (unsigned pass = loop_passes(image[object + OBJ_EGG_ROWS], COUNT_MASK_BYTE); pass--; ) {
        egg_blit_row(image, dst, src, shift, EGG_PASS_MAIN, EGG_MASK_OUT);
        egg_advance_row(&dst, &src);
    }

    /* The second pass re-reads all four fields from the record, as the original does — nothing in
     * the first pass writes them unless the erase runs over the object table itself. */
    dst = egg_wrap_dst(be32(image + object + OBJ_EGG_DST), be16(image + object + OBJ_EGG_X));
    src = be32(image + object + OBJ_EGG_SRC);
    for (unsigned pass = loop_passes(image[object + OBJ_EGG_ROWS], COUNT_MASK_BYTE); pass--; ) {
        egg_blit_row(image, dst, src, shift, EGG_PASS_WRAP, EGG_MASK_OUT);
        egg_advance_row(&dst, &src);
    }
}

/* draw_egg_sprite @ 0x12914 (object = A0) — OR the egg into the screen from the draw_* scratch
 * globals.
 *
 * The main pass stops early if the destination reaches playfield_bottom: the egg has fallen into
 * the lava, so its state becomes EGG_STATE_LAVA and draw_rows is rewritten to the number of rows
 * actually drawn — which the wrap pass then repeats. Note that a hit on the very first row leaves
 * draw_rows = 0, and `subq.b` reads 0 as 256, so the wrap pass then marches 256 scanlines down the
 * image. Faithful: the original does exactly that.
 */
void draw_egg_sprite(uint8_t *image, uint32_t object) {
    if (image[object + OBJ_EGG_STATE] == 0) return;

    uint8_t shift = image[A_draw_shift];
    uint32_t dst = be32(image + A_draw_dst);
    uint32_t src = be32(image + A_draw_src);
    uint8_t rows_left = image[A_draw_rows];                 /* d1: the `subq.b` row counter */

    for (;;) {
        if ((int32_t)dst >= (int32_t)be32(image + A_playfield_bottom)) {
            image[object + OBJ_EGG_STATE] = EGG_STATE_LAVA;
            /* `sub.b $df6.l,d1 ; neg.b d1` — draw_rows is re-read here, not carried in a register,
             * so an egg drawn over the draw_* globals themselves would subtract the new value. */
            image[A_draw_rows] =
                (uint8_t)(0u - (unsigned)(uint8_t)(rows_left - image[A_draw_rows]));
            break;
        }
        egg_blit_row(image, dst, src, shift, EGG_PASS_MAIN, EGG_OR_IN);
        egg_advance_row(&dst, &src);
        if (--rows_left == 0) break;
    }

    dst = egg_wrap_dst(be32(image + A_draw_dst), be16(image + A_draw_x));
    src = be32(image + A_draw_src);
    for (unsigned pass = loop_passes(image[A_draw_rows], COUNT_MASK_BYTE); pass--; ) {
        egg_blit_row(image, dst, src, shift, EGG_PASS_WRAP, EGG_OR_IN);
        egg_advance_row(&dst, &src);
    }
}

/* --------------------------------------------------------------- ptero_avoid_platform @ 0x15226 */

#define PTERO_AVOID_X_MIN     0x3cu   /* outside this x band the pterodactyl is clear of every platform */
#define PTERO_AVOID_X_MAX     0xfau
#define PTERO_PLATFORM_ABOVE  0xdu    /* rows above a platform that still count as blocked */
#define PTERO_VERTICAL_STEP   4u      /* the climb/dive step handed back to the mover */

/* `move.w`/`clr.w` into a data register: the low word is replaced and the HIGH half survives
 * untouched. Every write to D1 below is word-wide, which is the whole reason the caller gets its
 * own high half back on the clear exits. (machine.h models the byte-wide case as set_low_byte.) */
static uint32_t set_low_word(uint32_t reg, uint16_t value) {
    return (reg & 0xffff0000u) | value;
}

/* ptero_avoid_platform(pterodactyl = A0, scratch = D1 on entry) -> D1.
 *
 * Returns a vertical step of PTERO_VERTICAL_STEP while a platform's row band brackets the
 * pterodactyl's y, and 0 when it is clear. Only D1's LOW word is ever written, so its high half
 * comes back holding whatever the routine last left there — the caller's own value on the two
 * "clear" exits, or the divu remainder of the record that matched. Callers read `move.w d1,…`,
 * so none of them can see the difference; the full longword is modelled because the differential
 * pins the register the stub stores, not just the half the game uses.
 */
uint32_t ptero_avoid_platform(uint8_t *image, uint32_t pterodactyl, uint32_t scratch) {
    int16_t x = (int16_t)be16(image + pterodactyl + PT_X);
    if (x < (int16_t)PTERO_AVOID_X_MIN || x > (int16_t)PTERO_AVOID_X_MAX)
        return set_low_word(scratch, 0);                    /* clr.w d1 */

    int16_t y = (int16_t)be16(image + pterodactyl + PT_Y);
    for (uint32_t sprite = A_platform_sprites; sprite < A_platform_sprites_END;
         sprite += PSPR_RECORD) {
        if (image[be32(image + sprite + PSPR_PRESENT)] == 0) continue;

        /* The platform's top scanline, from its screen offset. */
        scratch = divu_w(be32(image + sprite + PSPR_DST_OFF), SCREEN_ROW_BYTES);
        uint16_t band_bottom = (uint16_t)((uint16_t)scratch + be16(image + sprite + PSPR_ROWS));
        if ((int16_t)band_bottom < y) continue;
        scratch = set_low_word(scratch, (uint16_t)((uint16_t)scratch - PTERO_PLATFORM_ABOVE));
        if ((int16_t)(uint16_t)scratch > y) continue;
        return set_low_word(scratch, PTERO_VERTICAL_STEP);
    }
    return set_low_word(scratch, 0);
}

/* ------------------------------------------------------------------ ptero_spot_player @ 0x15276 */

#define SND_PTERO_SWOOP     3u      /* sound_table index played when a player is spotted */

/* The four window thresholds, each spelled with the signedness of the branch that tests it: `bhi`
 * and `bcc` are unsigned (hence the `u`), `ble` and `bge` are signed (hence the int16_t cast).
 * Suffixing a signed one `u` would silently convert the compared value in the same expression. */
#define PTERO_SPOT_ROW_BAND   0xau  /* cmpi.w #$a + bhi: y gap + 4 must land in 0..10 */
#define PTERO_SPOT_ROW_BIAS   4u
#define PTERO_SPOT_X_BIAS     8u    /* addq.w #8 applied BEFORE the direction flip — see below */
#define PTERO_SPOT_X_NEAR  ((int16_t)8)     /* cmpi.w #$8  + ble: closer than this and it is past */
#define PTERO_SPOT_X_FAR   ((int16_t)0x69)  /* cmpi.w #$69 + bge: beyond this it is out of reach */
#define PTERO_SPOT_X_BEHIND   0xff29u  /* cmpi.w #$ff29 + bcc — see the note in the body */
#define PTERO_SWOOP_TIMER_SET 0x14u

/* ptero_spot_player(pterodactyl = A0, player = A3, flags = D0) — arm the swoop if this player is in
 * front of the pterodactyl and roughly level with it.
 *
 * Vertically the player must sit within [-4, +6] rows of the pterodactyl. Horizontally the gap is
 * measured in the direction of travel, biased by PTERO_SPOT_X_BIAS BEFORE the flip — which makes
 * the window asymmetric: flying left the player must be 1..0x60 pixels to the left, flying right
 * 0x11..0x70 pixels to the right.
 */
void ptero_spot_player(uint8_t *image, uint32_t pterodactyl, uint32_t player, uint32_t flags) {
    uint16_t row_gap = (uint16_t)(be16(image + pterodactyl + PT_Y) - be16(image + player + OBJ_Y)
                                  + PTERO_SPOT_ROW_BIAS);
    if (row_gap > PTERO_SPOT_ROW_BAND) return;              /* unsigned: one test covers both signs */

    uint16_t ahead = (uint16_t)(be16(image + pterodactyl + PT_X) + PTERO_SPOT_X_BIAS
                                - be16(image + player + OBJ_X));
    if (flags & PT_FLAG_MOVING_RIGHT) ahead = (uint16_t)(0u - (uint32_t)ahead);

    /* REDUNDANT IN THE SHIPPED CODE, KEPT FOR FIDELITY: this rejects [-215, -1], every value of
     * which the signed `<= PTERO_SPOT_X_NEAR` test below already rejects. It costs nothing and
     * changes nothing; presumably an earlier, looser window that was later tightened. */
    if (ahead >= PTERO_SPOT_X_BEHIND) return;
    if ((int16_t)ahead >= PTERO_SPOT_X_FAR) return;
    if ((int16_t)ahead <= PTERO_SPOT_X_NEAR) return;

    play_sound(image, SND_PTERO_SWOOP);
    image[pterodactyl + PT_SWOOP_TIMER] = PTERO_SWOOP_TIMER_SET;
}

/* -------------------------------------------------------------- count_objects_and_pad @ 0x1033e */

#define MESSAGE_CHAR_CAP  0x23u   /* the character walk stops here, and pads (0x23 - count) times */
#define LIVE_OBJECT_PAD   8u      /* pads (8 - live) times */
#define EGG_PAD           0x0eu   /* pads (0x0e - eggs) times */
#define PLAYER1_EGG_STATE_MIN 4   /* player 1's egg states that still count as a live object */
#define PLAYER1_EGG_STATE_MAX 0x12

/* Between waves (game_phase != 0) the pad is driven by a character count instead of an object
 * count. NOTE THE FIELD: the walk starts at MSG_SCREEN_PTR, the address draw_string PAINTS at, not
 * at the message's string pointer one longword further on — so what it counts is screen bytes up to
 * the first zero, not the message text. Since the count only sizes a delay loop, nothing in the
 * game observes the difference; it is reproduced, not corrected. */
static void count_message_chars(uint8_t *image) {
    image[A_message_char_count] = 0;
    for (uint32_t message = A_message_table; message != A_message_table_END;
         message += MSG_RECORD) {
        if (image[message + MSG_KIND] == 0) continue;       /* free slot */
        uint32_t cursor = be32(image + message + MSG_SCREEN_PTR);
        while (image[cursor++] != 0) {
            image[A_message_char_count]++;
            if (image[A_message_char_count] == MESSAGE_CHAR_CAP) return;
        }
    }
}

/* During play: how many object slots are alive, and how many carry an egg. A slot awaiting respawn
 * counts only once it has been drawn at least once (its previous destination is non-zero). */
static void count_live_objects(uint8_t *image) {
    image[A_live_object_count] = 0;
    image[A_egg_count] = 0;
    for (uint32_t object = A_object_table; object != A_object_table_END; object += OBJ_SIZE) {
        uint16_t flags = be16(image + object + OBJ_FLAGS);
        int pending_first_draw = (flags & OBJ_FLAG_RESPAWN)
                                 && be32(image + object + OBJ_PREV_DST) == 0;
        if (flags != 0 && !pending_first_draw) image[A_live_object_count]++;
        if (image[object + OBJ_EGG_STATE] != 0) image[A_egg_count]++;
    }
}

/* count_objects_and_pad() — the per-frame census, and the frame-time equaliser built on it.
 *
 * The original follows each count with a busy-wait proportional to how much work the frame did NOT
 * have to do — (8 - live), (0x0e - eggs), (0x23 - chars) passes of an inner spin — so a sparse frame
 * costs the same wall time as a busy one. Those loops touch no memory, so there is nothing for the
 * differential to compare and nothing to reproduce here: pacing belongs to the on-target build,
 * where a host-speed C loop would be meaningless anyway.
 */
void count_objects_and_pad(uint8_t *image) {
    if (image[A_game_phase] != 0) {
        count_message_chars(image);
        return;
    }
    count_live_objects(image);
    image[A_ptero_spawn_count] = 0;

    /* Player 1 mid-death still occupies a slot: its egg record is running the dismount animation. */
    int8_t player1_egg = (int8_t)image[A_object_table + OBJ_EGG_STATE];
    if (player1_egg >= PLAYER1_EGG_STATE_MIN && player1_egg <= PLAYER1_EGG_STATE_MAX)
        image[A_live_object_count]++;
}

/* ------------------------------------------------------------------------------------- glue ---
 *
 * Each g_* below unpacks the original's register arguments from the image at their real addresses.
 * Routines whose result lands in a data register write it to `result`, mirroring the 68000 stub the
 * differential test enters the oracle through (see test/abi.py).
 */

void g_pixel_collision(uint8_t *image, uint32_t box_a, uint32_t box_b) {
    pixel_collision(image, box_a, box_b);
}

void g_test_overlap(uint8_t *image) {
    test_overlap(image);
}

void g_joust_bounce(uint8_t *image, uint32_t obj_a, uint32_t obj_b,
                    uint32_t flags_a, uint32_t flags_b) {
    /* D0/D1 arrive as longwords so a test can prove only the low word is stored. */
    joust_bounce(image, obj_a, obj_b, (uint16_t)flags_a, (uint16_t)flags_b);
}

void g_check_platform(uint8_t *image, uint32_t object, uint32_t flags, uint32_t result) {
    wr32(image + result, check_platform(image, object, flags));
}

void g_erase_egg_sprite(uint8_t *image, uint32_t object) {
    erase_egg_sprite(image, object);
}

void g_draw_egg_sprite(uint8_t *image, uint32_t object) {
    draw_egg_sprite(image, object);
}

void g_ptero_avoid_platform(uint8_t *image, uint32_t pterodactyl, uint32_t scratch,
                            uint32_t result) {
    wr32(image + result, ptero_avoid_platform(image, pterodactyl, scratch));
}

void g_ptero_spot_player(uint8_t *image, uint32_t pterodactyl, uint32_t player, uint32_t flags) {
    ptero_spot_player(image, pterodactyl, player, flags);
}

void g_count_objects_and_pad(uint8_t *image) {
    count_objects_and_pad(image);
}
