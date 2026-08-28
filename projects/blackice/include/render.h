/*
 * render.h - the raycaster, the column list the 68000 asm consumes, and the
 *            reference column drawer.
 *
 * =========================================================================
 * THE CHUNKY BUFFER IS COLUMN MAJOR.  This is the most consequential layout
 * decision in the engine and it is deliberate.
 * =========================================================================
 * A raycaster emits VERTICAL slices.  In a row-major buffer every pixel of a
 * slice is one stride from the last, so the inner loop can only store one byte
 * at a time and pays an `adda.w` per pixel.  In a column-major buffer a slice
 * is a contiguous run: the 68000 stores through `(a0)+`, and an unrolled
 * version packs four texels into a d-register and retires them with one
 * `move.l`.
 *
 * It is not free.  The c2p pass wants the eight chunky pixels of a 16-pixel
 * planar group to be contiguous, and column major makes them eight strided
 * byte reads instead of two `move.l`: about +72 cycles per group, +115,000 on
 * a worst-case frame.  The wall drawer saves more than that - roughly 14 to 18
 * cycles on each of up to 12,800 textured pixels, 179,000 to 230,000 - so the
 * trade is a clear net win, and the gather cost can be recovered by a c2p that
 * transposes a 16-column strip at a time, reading whole chunky columns with
 * `movem.l`.  Both numbers are estimates until the platform agent measures.
 *
 * Pixel (x, y) lives at chunky[x * RENDER_H + y].  Use RENDER_PIXEL_OFFSET.
 *
 * -------------------------------------------------------------------------
 * WHY 80-COLUMN MODE NARROWS THE BUFFER INSTEAD OF DOUBLING COLUMNS
 * -------------------------------------------------------------------------
 * At 80 columns each chunky pixel is 4 screen pixels wide instead of 2.  Two
 * implementations were possible:
 *   (a) keep a 160-wide chunky buffer and write every ray's slice into two
 *       adjacent columns.  In a column-major buffer those two columns are 80
 *       bytes apart, so this doubles the cost of the single hottest loop in
 *       the program and saves nothing in the c2p.
 *   (b) let the buffer be 80 wide and have the c2p expand each byte to 4
 *       screen pixels.  Wall drawing halves, and the c2p's per-output-word
 *       gather halves too (4 source bytes per planar group instead of 8).
 * (b) is cheaper on both stages, so `columns` is a real width and the chunky
 * buffer's stride in x is RENDER_H regardless: only the number of columns
 * changes.  The buffer is always allocated RENDER_W_MAX * RENDER_H.
 *
 * -------------------------------------------------------------------------
 * 68000 cost model (8 MHz, 160,000 cycles per 50 Hz frame, 480,000 per 3 VBLs)
 * -------------------------------------------------------------------------
 * Per ray (160 rays at NOMINAL/OVERCLOCK, 80 at UNDERCLOCK):
 *   setup   two table reads for the delta distances, two `mulu` for the initial
 *           side distances, one `muls` for the perpendicular distance, one
 *           `muls` for the texture u              ~ 4 x 70 + 60 = 340 cyc
 *   DDA     per step: cmp.l, add.l, add index, btst on the solid bitmap, dbra
 *                                                ~ 60 cyc / step
 *   emit    fill one RenderColumn                ~ 90 cyc
 *   NOMINAL: radius 12, typical ray 5 steps -> 730 cyc, worst 12 -> 1150 cyc.
 *            160 rays: typical 117,000, worst 184,000 cyc.
 *   UNDERCLOCK: radius 6, 80 rays, worst 80 x 790 = 63,000 cyc.
 *   OVERCLOCK: radius 20, worst 160 x 1630 = 261,000 cyc.
 *
 * Per wall pixel, reference drawer (shade LUT in the loop):
 *   move.b (a_tex,d_v.w),d_t          14
 *   move.b (a_shade,d_t.w),(a_dst)+   18
 *   add.w  d_fstep,d_frac              4   texel accumulator, fraction
 *   addx.w d_istep,d_texel             4   texel accumulator, integer
 *   dbra                              10
 *   -> ~50 cyc/px unrolled by one, ~32 cyc/px unrolled x8 with four texels
 *      packed into one `move.l` store.
 *   DESIGN's worst case WC-A is 160 columns x 80 rows = 12,800 pixels, which is
 *   410,000 cyc at 32/px and does NOT fit 480,000 alongside the c2p.  The
 *   mitigations, in the order DESIGN 17 commits to them:
 *      (a) pre-shaded textures - DESIGN 17 bakes 5 depth bands at level load,
 *          which deletes the `move.b (a_shade,..)` and lands at ~22 cyc/px
 *          (282,000 for WC-A);
 *      (b) 80-column mode - halves it again to 141,000;
 *      (c) the render-radius throttle, which shortens slices, not their count.
 *   The reference C keeps the LUT in the loop because it must remain the
 *   byte-for-byte oracle for both variants; a pre-shaded texture is the same
 *   code with an identity LUT and a texture pointer chosen per band.
 *
 * Per far-fill pixel: `move.b d_fill,(a0)+` = 8 cyc, or ~2 cyc/px filling with
 * `move.l`.  A cut-off column is nearly free, which is the point of the
 * throttle.
 *
 * Per sprite pixel:
 *   move.b (a_tex,d_v.w),d_t          14
 *   cmp.b  #SPRITE_TRANSPARENT,d_t     8
 *   beq                             10/8
 *   move.b (a_shade,d_t.w),(a0)+      18
 *   add.w / addx.w                     8
 *   -> ~58 cyc/px.  SPRITE_PIXEL_BUDGET_HIGH x 58 = 348,000 cyc, which is why
 *      the budget is a tunable that DESIGN 17 marks provisional, and why the
 *      per-column opaque spans exist.
 *
 * Per c2p+double pixel: see host/c2p.h.
 *
 * -------------------------------------------------------------------------
 * WHAT IS MEASURED AND WHAT IS NOT
 * -------------------------------------------------------------------------
 * Measured (m68k-elf-gcc 16.1, -O2 -m68000 -ffreestanding, `make m68k`):
 *   raycast.o and draw.o reference NO libgcc arithmetic helper: every widening
 *   product is a `muls.w`, and there is no divide in either.  That is the
 *   property the cost model above depends on, and it only holds because every
 *   hot product goes through fixed.h's mul16 - written as 32x32 they became
 *   eleven __mulsi3 calls in render_cast alone.  Object sizes: raycast 1.5 KB,
 *   draw 0.4 KB, sprite 1.7 KB, tables 5.4 KB text + 32 KB bss.
 *   Two divides remain, both cold: one per visible sprite (the billboard's
 *   centre column) and one per door per tick (the cell's x and y).
 * NOT measured: every cycle count above.  They are read off the 68000 timing
 * tables, not off the Musashi oracle or Hatari, and the platform agent must
 * pin the real numbers before DESIGN 17's budget table can be filled in.
 */
#ifndef BLACKICE_RENDER_H
#define BLACKICE_RENDER_H

#include <stdint.h>
#include "fixed.h"
#include "game_consts.h"
#include "game.h"
#include "sprite.h"

/* ---- chunky frame buffer ----------------------------------------------- */

#define CHUNKY_STRIDE           RENDER_H    /* bytes between two columns */
#define CHUNKY_BYTES            (RENDER_W_MAX * CHUNKY_STRIDE)
#define RENDER_PIXEL_OFFSET(x, y) ((x) * CHUNKY_STRIDE + (y))

/* ---- the column list --------------------------------------------------- */

#define COLUMN_TEX_FAR  0       /* past the throttle radius: flat COLOUR_FAR_FILL */

#define SIDE_NS         0       /* ray crossed a horizontal grid line: lit face */
#define SIDE_EW         1       /* ray crossed a vertical grid line: unlit face */

/*
 * One entry per screen column, in screen order.  Everything is pre-clipped:
 * `top` and `rows` describe exactly the pixels to write, and `tex_v` is the
 * texel already advanced past the rows that fell off the top of the window.
 * The drawer therefore has no clipping work and no divides.
 *
 * 68000 layout, 12 bytes, every 16-bit field on an even offset:
 *    +0  tex_id   u8   COLUMN_TEX_FAR, or the wall texture id 1..15
 *    +1  tex_col  u8   texture column 0..63
 *    +2  top      i16  first row to write, 0..RENDER_H-1
 *    +4  rows     u16  rows to write, 0..RENDER_H
 *    +6  tex_v    u16  texel v at row `top`, 8.8 fixed
 *    +8  tex_step u16  texel v added per row, 8.8 fixed
 *   +10  band     u8   depth band, 0..BAND_COUNT-1
 *   +11  side     u8   SIDE_NS or SIDE_EW
 * The shade LUT row is g_shade_lut[band + side]: composing the lit/unlit remap
 * with the fog remap into one add is what makes shading free per column.
 */
typedef struct {
    uint8_t  tex_id;
    uint8_t  tex_col;
    int16_t  top;
    uint16_t rows;
    uint16_t tex_v;
    uint16_t tex_step;
    uint8_t  band;
    uint8_t  side;
} RenderColumn;

#define RENDER_COLUMN_BYTES 12

/* ---- column sets ------------------------------------------------------- */

#define COLUMN_SET_HIGH     0   /* 160 columns, 2 screen pixels wide */
#define COLUMN_SET_LOW      1   /* 80 columns, 4 screen pixels wide */
#define COLUMN_SET_COUNT    2

typedef struct {
    uint16_t        count;
    uint8_t         width_shift;    /* 0 or 1: how much wider a column is than at 160 */
    uint8_t         pad;
    const int16_t  *angle;          /* per-column ray angle offset from the view angle */
    const uint16_t *cosine;         /* per-column fisheye correction, 1.14 */
} ColumnSet;

extern const ColumnSet g_column_sets[COLUMN_SET_COUNT];
extern const int16_t   g_col_angle_high[RENDER_COLUMNS_HIGH];
extern const uint16_t  g_col_cos_high[RENDER_COLUMNS_HIGH];
extern const int16_t   g_col_angle_low[RENDER_COLUMNS_LOW];
extern const uint16_t  g_col_cos_low[RENDER_COLUMNS_LOW];

/* ---- throttle modes (DESIGN 5) ------------------------------------------ */

typedef struct {
    uint8_t  radius_cells;
    uint8_t  band_count;
    uint8_t  column_set;
    uint8_t  pad;
    uint16_t speed_scale;                   /* 8.8 */
    uint16_t trace_scale;                   /* 8.8 */
    uint16_t sprite_budget;                 /* chunky pixels per frame */
    uint16_t band_limit[BAND_COUNT - 1];    /* map units; unused entries are 0xffff */
} ThrottleMode;

extern const ThrottleMode g_throttle_modes[THROTTLE_MODE_COUNT];

static inline const ThrottleMode *render_mode(const GameState *state)
{
    return &g_throttle_modes[state->throttle];
}

static inline const ColumnSet *render_columns(const GameState *state)
{
    return &g_column_sets[render_mode(state)->column_set];
}

/* ---- per-frame scratch (not simulation state, never hashed) ------------- */

typedef struct {
    RenderColumn columns[RENDER_W_MAX];
    uint16_t     wall_dist[RENDER_W_MAX];   /* perpendicular distance, map units */
    SpriteList   sprites;
} RenderScratch;

/* ---- assets ------------------------------------------------------------ */

/*
 * Wall textures are 64x64 bytes, COLUMN MAJOR: texel (u, v) at u * 64 + v, so
 * a texture column is a contiguous 64-byte run.  Slot 0 is unused (0 is the
 * far-fill sentinel); slots 1..15 are the ids a map cell can name.
 */
extern const uint8_t *g_wall_textures[WALL_TEXTURE_MAX + 1];

/* Palette as 8-bit RGB triples, for the host PNG writer only. */
extern const uint8_t g_palette_rgb[PALETTE_SIZE][3];

/* Shade remap: g_shade_lut[band + side][index].  Level 0 is the identity. */
extern const uint8_t g_shade_lut[SHADE_LEVEL_COUNT][PALETTE_SIZE];

/* ---- stages ------------------------------------------------------------ */

/* Cast the mode's rays and fill scratch->columns and scratch->wall_dist. */
void render_cast(const GameState *state, RenderScratch *scratch);

/* Draw the column list into the chunky buffer.  Does not clear it. */
void render_draw_columns(const RenderScratch *scratch, uint16_t columns, uint8_t *chunky);

/* Fill `columns` columns of the chunky buffer with the void. */
void render_clear(uint8_t *chunky, uint16_t columns);

/* clear + cast + draw columns + build and draw sprites. */
void render_frame(const GameState *state, RenderScratch *scratch, uint8_t *chunky);

/* Depth band for a perpendicular distance in map units. */
uint8_t render_band_for_dist(const ThrottleMode *mode, uint16_t dist_units);

#endif /* BLACKICE_RENDER_H */
