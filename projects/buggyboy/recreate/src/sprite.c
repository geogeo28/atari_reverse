/* sprite.c — masked buggy / foreground sprites (draw_fg_sprite .. draw_buggy @ 0x1518a..).
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
