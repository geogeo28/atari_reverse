/* sprite.c — masked buggy / foreground sprites (draw_fg_sprite .. draw_buggy @ 0x1518a..) plus the
 * checkpoint-banner scroll (draw_checkpoint_anim @ 0x1442c).
 *
 * These blit a 4-plane sprite into the draw buffer using the shared transparency cell
 * (blit_transp_cell), bottom row first and walking one scanline up (OBJ_ROW_UP) per row.
 * draw_buggy_wheels is the shared blit body (A0 dst, A1 src, D4 rows-1); draw_fg_sprite sets
 * those up from the animation tables (behind a spin/curve gate) and falls into it.
 */
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"
#include "draw.h"

#define CELL_BYTES    8        /* one 16-pixel, 4-plane transparency cell */
#define WHEELS_CELLS  4        /* cells per row (64 px wide) */

/* draw_buggy_wheels @ 0x151f6 — A0 dst, A1 src, D4 rows-1. Each row is WHEELS_CELLS transparency
 * cells; dst and src both step one scanline up (OBJ_ROW_UP) after the row. */
void g_draw_buggy_wheels(uint8_t *image, uint32_t dst, uint32_t src, uint32_t rows_m1) {
    int rows = (int16_t)rows_m1 + 1;
    for (int r = 0; r < rows; r++, dst -= OBJ_ROW_UP, src -= OBJ_ROW_UP)
        for (int cell = 0; cell < WHEELS_CELLS; cell++)
            blit_transp_cell(image, dst + cell * CELL_BYTES, src + cell * CELL_BYTES);
}

/* draw_fg_sprite @ 0x1518a — the game entry for the foreground buggy sprite. If the buggy is
 * spinning (spin_state < 0) into a hard curve it arms the spin counter and skips the draw;
 * otherwise, unless suppressed, it looks up the current frame in fg_anim_tbl and falls into
 * the wheels blit (dst = buffer + frame dst, src = buf_c + frame src, D4 = frame rows-1). */
#define SPIN_CURVE_THRESH 0x118    /* |road_curve| at/above which a spin aborts the draw */
#define SPIN_FRAMES_RIGHT 0x1e     /* spin duration for a right curve (spin_state == 0xff) */
#define SPIN_FRAMES_LEFT  0x3c     /* spin duration for a left curve (spin_state 0x80..0xfe) */

void g_draw_fg_sprite(uint8_t *image) {
    wr16(image + A_spin_counter, 0);
    int8_t spin = (int8_t)image[A_spin_state];
    if (spin < 0) {                                    /* spinning: a hard curve aborts the draw */
        int16_t curve = (int16_t)be16(image + A_road_curve);
        if ((uint8_t)(spin + 1) != 0) {                /* spin_state 0x80..0xfe: left-curve gate */
            if ((int16_t)(-curve) >= SPIN_CURVE_THRESH) {
                wr16(image + A_spin_counter, SPIN_FRAMES_LEFT);
                wr32(image + A_spin_reset, 0);
                return;
            }
        } else if (curve >= SPIN_CURVE_THRESH) {       /* spin_state == 0xff: right-curve gate */
            wr16(image + A_spin_counter, SPIN_FRAMES_RIGHT);
            wr32(image + A_spin_reset, 0);
            return;
        }
    }
    if (be16(image + A_sprite_suppress) != 0) return;
    if ((int8_t)image[A_fg_gate] < 0) return;

    uint32_t frame = A_fg_anim_tbl + sign_ext16(be16(image + A_anim_frame));
    uint16_t rows_m1 = be16(image + frame);
    uint32_t dst = draw_buffer(image) + sign_ext16(be16(image + frame + 2));
    uint32_t src = be32(image + frame + 4) + be32(image + A_buf_c);
    g_draw_buggy_wheels(image, dst, src, rows_m1);
}

/* draw_buggy_lo @ 0x153fa — the lower buggy body (drawn behind the wheels/foreground). A6 is
 * the draw buffer (set by draw_buggy). Behind a 5-way gate it draws two sub-sprites from a
 * piece list selected by wheel_pos and shifted by spin_counter: [rows0, rows1, then a
 * (src,dst) word pair per sub-sprite]. Each sub-sprite is LO_CELLS transparency cells wide and
 * walks one scanline up per row; src is buf_c + LO_SRC_OFF + offset, dst is A6 + offset. */
#define LO_SRC_OFF       0x27100   /* buggy-body sprite source: buf_c + this (160000) */
#define LO_PIECE_TBL     0x17746   /* piece lists; entry = piece_idx_tbl[wheel_pos] + spin_counter */
#define LO_PIECE_IDX_TBL 0x1773c   /* per-wheel_pos word offset into LO_PIECE_TBL */
#define LO_CELLS         2         /* transparency cells per sub-sprite row (32 px) */
#define LO_SUBSPRITES    2

void g_draw_buggy_lo(uint8_t *image, uint32_t buffer) {
    if (be16(image + A_buggy_draw_flag) == 0) return;
    if ((image[A_buggy_gate] | image[A_fg_gate]) & 0x80) return;
    if ((be16(image + A_sprite_suppress) | be16(image + A_collision_lock)) != 0) return;
    if (be32(image + A_spin_reset) != 0) return;

    uint32_t src_base = be32(image + A_buf_c) + LO_SRC_OFF;
    uint16_t wheel_pos = be16(image + A_wheel_pos);
    uint32_t piece = LO_PIECE_TBL
                   + sign_ext16(be16(image + LO_PIECE_IDX_TBL + wheel_pos * 2))
                   + sign_ext16(be16(image + A_spin_counter));
    uint8_t rows[LO_SUBSPRITES] = { image[piece], image[piece + 1] };
    uint32_t cur = piece + 2;
    for (int sub = 0; sub < LO_SUBSPRITES; sub++, cur += 4) {
        uint32_t src = src_base + sign_ext16(be16(image + cur));
        uint32_t dst = buffer   + sign_ext16(be16(image + cur + 2));
        int nrows = rows[sub] + 1;
        for (int r = 0; r < nrows; r++, dst -= OBJ_ROW_UP, src -= OBJ_ROW_UP)
            for (int cell = 0; cell < LO_CELLS; cell++)
                blit_transp_cell(image, dst + cell * CELL_BYTES, src + cell * CELL_BYTES);
    }
}

/* draw_buggy_hi @ 0x154c6 — the buggy lean overlay (drawn on top). A2 is the dst base (set by
 * draw_buggy). Skipped while leaning hard (lean_state >= LEAN_MAX). It advances a lean frame
 * by accumulating a speed-derived rate: lean_accum += (speed_raw>>13)<<8 | rate_tbl[speed_raw>>5];
 * at LEAN_ACCUM_STEP it resets and steps lean_frame (wrapping at LEAN_FRAME_WRAP). With a
 * nonzero frame it OR-blits two sub-sprites from a piece list [src_word, dst_byte, rows_byte];
 * unlike the body this is additive (no transparency mask) and each source word fills two dest
 * words. dst = A2 - (dst_byte << 5); src = buf_c + HI_SRC_OFF + src_word; both walk up per row. */
#define HI_SRC_OFF       0x23280   /* lean-overlay sprite source: buf_c + this */
#define HI_TBL           0x17554   /* rate bytes at [speed_raw>>5], then lean piece lists */
#define LEAN_MAX         0x1e      /* lean_state at/above which the overlay is skipped */
#define LEAN_ACCUM_STEP  8         /* accumulator level that advances the lean frame */
#define LEAN_FRAME_STEP  8
#define LEAN_FRAME_WRAP  0x18
#define HI_SUBSPRITES    2
#define HI_DST_SHIFT     5         /* dst_byte << 5 subtracted from A2 */

void g_draw_buggy_hi(uint8_t *image, uint32_t dst_base) {
    if ((int16_t)be16(image + A_lean_state) >= LEAN_MAX) return;

    uint16_t speed_raw = be16(image + A_speed_raw);
    uint8_t rate = image[HI_TBL + (speed_raw >> 5)];
    uint16_t accum = (uint16_t)(be16(image + A_lean_accum) + (((speed_raw >> 13) << 8) | rate));
    uint16_t frame = be16(image + A_lean_frame);
    if ((int16_t)accum >= LEAN_ACCUM_STEP) {
        accum = 0;
        frame = (uint16_t)(frame + LEAN_FRAME_STEP);
        if ((int16_t)frame >= LEAN_FRAME_WRAP) frame = 0;
    }
    wr16(image + A_lean_accum, accum);
    wr16(image + A_lean_frame, frame);
    if (frame == 0) return;

    uint32_t src_base = be32(image + A_buf_c) + HI_SRC_OFF;
    uint32_t piece = HI_TBL + frame + be16(image + A_buggy_variant) * 2;
    for (int sub = 0; sub < HI_SUBSPRITES; sub++, dst_base += 0x10) {
        uint32_t src = src_base + sign_ext16(be16(image + piece));
        uint32_t dst = dst_base - sign_ext16((uint16_t)(image[piece + 2] << HI_DST_SHIFT));
        int nrows = image[piece + 3] + 1;
        piece += 4;
        for (int r = 0; r < nrows; r++, dst -= OBJ_ROW_UP, src -= OBJ_ROW_UP) {
            uint32_t dup0 = dup16(be16(image + src));
            wr32(image + dst,     be32(image + dst)     | dup0);
            wr32(image + dst + 4, be32(image + dst + 4) | dup0);
            uint32_t dup4 = dup16(be16(image + src + 8));
            wr32(image + dst + 8,  be32(image + dst + 8)  | dup4);
            wr32(image + dst + 12, be32(image + dst + 12) | dup4);
        }
    }
}

/* draw_checkpoint_anim @0x1442c — scroll the checkpoint banner within buf_c. Copies columns from an
 * X-shifted source (buf_c + CKPT_BASE_OFF + k*ckpt_scroll) to a fixed dest (buf_c + CKPT_BASE_OFF)
 * in three table-driven blocks of increasing width and shift: 7 groups of 1-longword columns
 * (shift 1x), 4 groups of 2 (shift 2x), then one group of 3 (shift 3x). Each group reads a row
 * count and src/dst offsets from CKPT_ANIM_TBL; every row steps src/dst by CKPT_STRIDE (the copied
 * longwords + a fixed skip). No args. */
#define CKPT_BASE_OFF   0x9c40   /* checkpoint banner region: buf_c + this (40000) */
#define CKPT_ANIM_TBL   0x17324  /* control words per group: {rows-1, src_off, dst_off} */
#define CKPT_STRIDE     0x50     /* per-row src/dst step (copied longs + skip = 80 bytes) */
#define CKPT_B1_GROUPS  7
#define CKPT_B2_GROUPS  4
#define CKPT_B3_ROWS_M1 0x1c     /* block 3's single group has a preset row count-1 */

void g_draw_checkpoint_anim(uint8_t *image) {
    uint32_t dst_base = be32(image + A_buf_c) + CKPT_BASE_OFF;   /* a2 */
    uint16_t scroll = be16(image + A_ckpt_scroll);              /* d3 */
    uint32_t src_base = dst_base;                               /* a3 */
    uint32_t tbl = CKPT_ANIM_TBL;                               /* a4 */

    src_base += sign_ext16(scroll);                            /* block 1: 1-longword columns */
    for (int g = 0; g < CKPT_B1_GROUPS; g++) {
        int rows = (int16_t)be16(image + tbl);
        uint32_t src = src_base + sign_ext16(be16(image + tbl + 2));
        uint32_t dst = dst_base + sign_ext16(be16(image + tbl + 4));
        tbl += 6;
        for (int r = 0; r <= rows; r++, src += CKPT_STRIDE, dst += CKPT_STRIDE)
            wr32(image + dst, be32(image + src));
    }
    src_base += sign_ext16(scroll);                            /* block 2: 2-longword columns */
    for (int g = 0; g < CKPT_B2_GROUPS; g++) {
        int rows = (int16_t)be16(image + tbl);
        uint32_t src = src_base + sign_ext16(be16(image + tbl + 2));
        uint32_t dst = dst_base + sign_ext16(be16(image + tbl + 4));
        tbl += 6;
        for (int r = 0; r <= rows; r++, src += CKPT_STRIDE, dst += CKPT_STRIDE) {
            wr32(image + dst,     be32(image + src));
            wr32(image + dst + 4, be32(image + src + 4));
        }
    }
    src_base += sign_ext16(scroll);                            /* block 3: one 3-longword group */
    uint32_t src = src_base + sign_ext16(be16(image + tbl));
    uint32_t dst = dst_base + sign_ext16(be16(image + tbl + 2));
    for (int r = 0; r <= CKPT_B3_ROWS_M1; r++, src += CKPT_STRIDE, dst += CKPT_STRIDE) {
        wr32(image + dst,     be32(image + src));
        wr32(image + dst + 4, be32(image + src + 4));
        wr32(image + dst + 8, be32(image + src + 8));
    }
}
