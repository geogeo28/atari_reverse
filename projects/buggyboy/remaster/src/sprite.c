/* sprite.c — remaster of the masked player-car / foreground sprites (recreate's draw_fg_sprite ..
 * draw_buggy @0x1518a..0x152ac).
 *
 * These blit a 4-plane sprite into the draw buffer with the shared transparency cell (cell_transp,
 * plane.h), bottom row first and walking one scanline up (OBJ_ROW_UP) per row. Every sprite's pixels
 * live in the unpacked-graphics arena (recreate's buf_c) at a table-driven byte offset; the two lean
 * sub-sprites add their own sub-arena bias (HI_SRC_OFF / LO_SRC_OFF).
 *
 * Split (as in recreate) into the shared wheels blit body, the foreground sprite (draw_fg_sprite),
 * and the player car (draw_buggy) with its lean overlay (buggy_hi) and lower body (buggy_lo). The
 * checkpoint-banner scroll (recreate's draw_checkpoint_anim) is a separate, off-path effect and is
 * not part of the in-race object draw, so it is omitted here.
 *
 * Byte-for-byte identical output to recreate's cores (see test/test_sprite.py).
 */
#include "game.h"
#include "plane.h"
#include "screen.h"
#include "st.h"

#define OBJ_ROW_UP    0xa0     /* 160 bytes: one scanline up (sprites drawn bottom to top) */
#define CELL_BYTES    8        /* one 16-pixel, 4-plane transparency cell */
#define WHEELS_CELLS  4        /* cells per foreground-sprite row (64 px wide) */

/* Blit `rows` rows of `cells` transparency cells each, from `src` (in the graphics arena) to `dst`
 * (a framebuffer byte offset). Both dst and src step one scanline up (OBJ_ROW_UP) after each row —
 * the shared bottom-up sprite blit (draw_buggy_wheels @0x151f6, and the buggy body/lower loops). */
static void blit_sprite(Framebuffer *fb, const uint8_t *gfx, Offset dst, uint32_t src,
                        int rows, int cells) {
    for (int r = 0; r < rows; r++, dst -= OBJ_ROW_UP, src -= OBJ_ROW_UP)
        for (int cell = 0; cell < cells; cell++)
            cell_transp(fb->px, dst + cell * CELL_BYTES, gfx + src + cell * CELL_BYTES);
}

/* ---- draw_fg_sprite @0x1518a — the foreground buggy sprite. If the buggy is spinning (spin_state
 * < 0) into a hard curve it arms the spin counter and skips the draw; otherwise, unless suppressed,
 * it looks up the current frame in fg_anim_tbl and blits it (WHEELS_CELLS cells per row). */
#define SPIN_CURVE_THRESH 0x118    /* |road_curve| at/above which a spin aborts the draw */
#define SPIN_FRAMES_RIGHT 0x1e     /* spin duration for a right curve (spin_state == 0xff) */
#define SPIN_FRAMES_LEFT  0x3c     /* spin duration for a left curve (spin_state 0x80..0xfe) */

void rm_draw_fg_sprite(SpriteState *s, const SpriteAssets *a, Framebuffer *fb) {
    s->spin_counter = 0;
    if (s->spin_state < 0) {                             /* spinning: a hard curve aborts the draw */
        int16_t curve = s->road_curve;
        if ((uint8_t)(s->spin_state + 1) != 0) {        /* spin_state 0x80..0xfe: left-curve gate */
            if ((int16_t)(-curve) >= SPIN_CURVE_THRESH) {
                s->spin_counter = SPIN_FRAMES_LEFT;
                s->spin_reset = 0;
                return;
            }
        } else if (curve >= SPIN_CURVE_THRESH) {        /* spin_state == 0xff: right-curve gate */
            s->spin_counter = SPIN_FRAMES_RIGHT;
            s->spin_reset = 0;
            return;
        }
    }
    if (s->sprite_suppress != 0) return;
    if (s->fg_gate < 0) return;

    const uint8_t *frame = a->fg_anim_tbl + sx16(s->anim_frame);
    int rows = be16(frame) + 1;
    Offset dst = sx16(be16(frame + 2));
    uint32_t src = be32(frame + 4);
    blit_sprite(fb, a->gfx, dst, src, rows, WHEELS_CELLS);
}

/* ---- draw_buggy_lo @0x153fa — the lower buggy body (behind the wheels/foreground). Behind a 5-way
 * gate it draws two sub-sprites from a piece list selected by wheel_pos and shifted by spin_counter:
 * [rows0, rows1, then a (src,dst) word pair per sub-sprite]. Each sub-sprite is LO_CELLS cells wide
 * and walks up per row; src is gfx + LO_SRC_OFF + offset, dst is the buffer + offset. */
#define LO_SRC_OFF    0x27100   /* lower-body sprite source: gfx + this (160000) */
#define LO_CELLS      2         /* transparency cells per sub-sprite row (32 px) */
#define LO_SUBSPRITES 2

static void draw_buggy_lo(SpriteState *s, const SpriteAssets *a, Framebuffer *fb) {
    if (s->buggy_draw_flag == 0) return;
    if ((s->buggy_gate | (uint8_t)s->fg_gate) & 0x80) return;
    if ((s->sprite_suppress | s->collision_lock) != 0) return;
    if (s->spin_reset != 0) return;

    uint32_t src_base = LO_SRC_OFF;
    const uint8_t *piece = a->lo_piece_tbl
                         + sx16(be16(a->lo_piece_idx + s->wheel_pos * 2))
                         + sx16(s->spin_counter);
    uint8_t rows[LO_SUBSPRITES] = { piece[0], piece[1] };
    const uint8_t *cur = piece + 2;
    for (int sub = 0; sub < LO_SUBSPRITES; sub++, cur += 4) {
        uint32_t src = src_base + sx16(be16(cur));
        Offset   dst = sx16(be16(cur + 2));
        blit_sprite(fb, a->gfx, dst, src, rows[sub] + 1, LO_CELLS);
    }
}

/* ---- draw_buggy_hi @0x154c6 — the lean overlay (on top). Skipped while leaning hard (lean >=
 * LEAN_MAX). It advances a lean frame by accumulating a speed-derived rate; with a nonzero frame it
 * OR-blits two sub-sprites from a piece list [src_word, dst_byte, rows_byte]. Unlike the body this is
 * additive (no transparency mask) and each source word fills two dest words. dst = dst_base -
 * (dst_byte << HI_DST_SHIFT); src = gfx + HI_SRC_OFF + src_word; both walk up per row. */
#define HI_SRC_OFF      0x23280   /* lean-overlay sprite source: gfx + this */
#define LEAN_MAX        0x1e      /* lean at/above which the overlay is skipped */
#define LEAN_ACCUM_STEP 8         /* accumulator level that advances the lean frame */
#define LEAN_FRAME_STEP 8
#define LEAN_FRAME_WRAP 0x18
#define HI_SUBSPRITES   2
#define HI_DST_SHIFT    5         /* dst_byte << 5 subtracted from dst_base */
#define HI_SUB_STRIDE   0x10      /* dst_base advances this per sub-sprite */
#define HI_RATE_SHIFT   5         /* speed_raw >> this indexes the rate byte */
#define HI_ACCUM_SHIFT  13        /* speed_raw >> this is the accumulator's high byte */

static void draw_buggy_hi(SpriteState *s, const SpriteAssets *a, Framebuffer *fb, Offset dst_base) {
    if ((int16_t)s->lean >= LEAN_MAX) return;

    uint16_t speed_raw = s->speed_raw;
    uint8_t rate = a->hi_tbl[speed_raw >> HI_RATE_SHIFT];
    uint16_t accum = (uint16_t)(s->lean_accum + (((speed_raw >> HI_ACCUM_SHIFT) << 8) | rate));
    uint16_t frame = s->lean_frame;
    if ((int16_t)accum >= LEAN_ACCUM_STEP) {
        accum = 0;
        frame = (uint16_t)(frame + LEAN_FRAME_STEP);
        if ((int16_t)frame >= LEAN_FRAME_WRAP) frame = 0;
    }
    s->lean_accum = accum;
    s->lean_frame = frame;
    if (frame == 0) return;

    uint32_t src_base = HI_SRC_OFF;
    const uint8_t *piece = a->hi_tbl + frame + s->variant * 2;
    for (int sub = 0; sub < HI_SUBSPRITES; sub++, dst_base += HI_SUB_STRIDE) {
        uint32_t src = src_base + sx16(be16(piece));
        Offset   dst = dst_base - sx16((uint16_t)(piece[2] << HI_DST_SHIFT));
        int rows = piece[3] + 1;
        piece += 4;
        for (int r = 0; r < rows; r++, dst -= OBJ_ROW_UP, src -= OBJ_ROW_UP) {
            Plane4 dup0 = dup16(be16(a->gfx + src));
            wr32(fb->px + dst,     be32(fb->px + dst)     | dup0);
            wr32(fb->px + dst + 4, be32(fb->px + dst + 4) | dup0);
            Plane4 dup4 = dup16(be16(a->gfx + src + 8));
            wr32(fb->px + dst + 8,  be32(fb->px + dst + 8)  | dup4);
            wr32(fb->px + dst + 12, be32(fb->px + dst + 12) | dup4);
        }
    }
}

/* ---- draw_buggy @0x152ac — draw the player car. Position it from the lean/crash/skid/pitch state,
 * pick the body sprite for the current lean from body_tbl, blit the body (blit_sprite for the upright
 * frames whose flag is 0, else an inline BUGGY_BODY_CELLS-cell transparency blit for the leaning
 * frames), then the lean overlay (draw_buggy_hi, dst_base = the body dst) and the lower body
 * (draw_buggy_lo). */
#define BUGGY_BASE_POS   0x71c0    /* base screen position before the crash/skid/pitch offsets */
#define BUGGY_DST_BIAS   0x40      /* dst = buffer + this + position */
#define BUGGY_BODY_CELLS 5         /* transparency cells per body row */
#define BUGGY_VARIANT_MUL 8        /* lean * this = the hi piece-list variant / body_tbl stride */

void rm_draw_buggy(SpriteState *s, const SpriteAssets *a, Framebuffer *fb) {
    int16_t pos = (int16_t)(BUGGY_BASE_POS - s->crash_disp - s->pitch + s->skid);

    s->variant = (uint16_t)(s->lean * BUGGY_VARIANT_MUL);   /* read back by draw_buggy_hi */

    const uint8_t *piece = a->body_tbl + sx16((uint16_t)(s->lean * BUGGY_VARIANT_MUL));
    uint32_t src = be32(piece);
    uint8_t flag = piece[4];
    int rows = piece[5] + 1;
    pos = (int16_t)(pos + (int16_t)be16(piece + 6));
    Offset dst = BUGGY_DST_BIAS + sx16((uint16_t)pos);

    blit_sprite(fb, a->gfx, dst, src, rows, flag == 0 ? WHEELS_CELLS : BUGGY_BODY_CELLS);

    draw_buggy_hi(s, a, fb, dst);                           /* dst_base = the (original) body dst */
    draw_buggy_lo(s, a, fb);
}
