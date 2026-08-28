/*
 * game_consts.h - every tunable of the BLACK ICE sim and renderer.
 *
 * Values come from design/DESIGN.md where that document fixes them; the rest
 * are placeholders chosen to make the engine legible and testable.  Nothing
 * outside this file may spell a tunable as a literal.
 */
#ifndef BLACKICE_GAME_CONSTS_H
#define BLACKICE_GAME_CONSTS_H

#include "fixed.h"

/* ---- simulation ------------------------------------------------------- */

#define SIM_HZ                  25          /* fixed timestep (DESIGN 4), one tick per 2 PAL VBLs */

/* ---- player (DESIGN 4, converted from cells/tick and brads/tick) ------- */

/* 0.150 cells/tick * 256 units/cell = 38.4, rounded. */
#define PLAYER_MOVE_SPEED       38
/* 0.090 cells/tick. */
#define PLAYER_BACK_SPEED       23
/* 0.110 cells/tick. */
#define PLAYER_STRAFE_SPEED     28
/* 24 brads/tick, and one brad is ANGLE_UNITS_PER_BRAD angle units. */
#define PLAYER_TURN_SPEED       (24 * ANGLE_UNITS_PER_BRAD)
/* 0.28 cells. */
#define PLAYER_RADIUS           72

/* ---- doors -------------------------------------------------------------- */

/*
 * CLOSED -> OPENING (blocks) -> OPEN (passable) -> CLOSING (blocks) -> CLOSED.
 * A body standing in a closing door sends it back to OPENING, so a door can
 * never shut on the player.  0.5 s of travel each way at SIM_HZ, 3 s open.
 */
#define DOOR_OPENING_TICKS      (SIM_HZ / 2)    /* 0.5 s */
#define DOOR_OPEN_TICKS         (SIM_HZ * 3)    /* 3 s */
#define DOOR_CLOSING_TICKS      (SIM_HZ / 2)
#define DOOR_MAX_COUNT          64

/* ---- render window (DESIGN 17) ------------------------------------------ */

/*
 * 160x80 logical, pixel-doubled to 320x160.  The bottom SCREEN_HUD_LINES
 * scanlines are a static planar HUD the platform layer owns; the engine never
 * writes them.
 */
#define RENDER_W_MAX            160         /* widest column count == buffer width */
#define RENDER_H                80          /* logical rows, always, in both modes */

#define SCREEN_W                320
#define SCREEN_H                200
#define SCREEN_PLANES           4
#define SCREEN_BYTES_PER_LINE   ((SCREEN_W / 8) * SCREEN_PLANES)   /* 160 */
#define SCREEN_BYTES            (SCREEN_BYTES_PER_LINE * SCREEN_H) /* 32000 */
#define SCREEN_WINDOW_LINES     (RENDER_H * 2)                     /* 160 */
#define SCREEN_HUD_LINES        (SCREEN_H - SCREEN_WINDOW_LINES)   /* 40 */

#define PALETTE_SIZE            16
#define COLOUR_VOID             0           /* floor and ceiling: the void */
/*
 * The colour a beyond-the-radius column is flat-filled with.  DESIGN's colour
 * table lists index 0 for the far fill, but DESIGN 5 also requires "the
 * far-fill boundary visibly moves" as throttle feedback, and a void-coloured
 * fill on a void background is invisible.  Index 5 (#003355, the darkest cyan)
 * is the cheapest thing that satisfies both; set it to 0 to follow the table.
 */
#define COLOUR_FAR_FILL         5

/* ---- field of view ---------------------------------------------------- */

#define FOV_DEGREES             60
#define FOV_ANGLE               10923       /* 60 * 65536 / 360 */
#define FOV_HALF_ANGLE          (FOV_ANGLE / 2)

/* ---- texture geometry --------------------------------------------------- */

#define TEX_DIM                 64
#define TEX_DIM_SHIFT           6           /* log2(TEX_DIM) */
#define TEX_SIZE                (TEX_DIM * TEX_DIM)
#define TEX_INDEX_MASK          (TEX_DIM - 1)

/* ---- wall projection --------------------------------------------------- */

/*
 * Vertical: a wall is one cell tall and projects to
 *     height_rows = FOCAL_ROWS / perpendicular_distance_in_cells
 * so, with distances carried in 8.8 map units,
 *     height_rows = WALL_PROJECTION_SCALE / perpendicular_distance_in_units.
 *
 * Horizontal: the projection plane sits FOCAL_COLS = (RENDER_W_MAX / 2) /
 * tan(FOV / 2) = 80 / tan(30 deg) = 138.56 columns from the eye.  Only the
 * sprite projection needs it, through SPRITE_PROJ_X_DIVISOR.
 *
 * Both are independent of the column count: 80-column mode halves the
 * horizontal resolution but keeps all 80 rows, so the two modes share the
 * height and texture-step tables.
 *
 * WHY 115 AND NOT 64 (DESIGN v2.1 D1).  A cell face is FOCAL_COLS/d = 138.56/d columns wide,
 * each 2 screen pixels; an ST low-resolution pixel is 0.833 as wide as it is
 * tall; so the face measures 231/d screen units across against 2*FOCAL_ROWS/d
 * tall.  Squaring those gives FOCAL_ROWS = 115.  The first draft used TEX_DIM,
 * which projected every cell 1.8 to 1 SQUAT - corridors looked like letterbox
 * slots and the world read as half its height.
 *
 * TEX_DIM used to be a pleasant coincidence here: with FOCAL_ROWS == TEX_DIM
 * the texture step (TEX_DIM << 8) / height came out equal to the distance, so
 * a target build could step by the distance itself and skip a table.  That
 * shortcut is gone, and nothing depended on it: tables_init derives the step
 * from the height it actually computed, which is exact for any FOCAL_ROWS.
 *
 * Override at the compiler to compare (-DFOCAL_ROWS=64).
 */
#ifndef FOCAL_ROWS
#define FOCAL_ROWS              115
#endif
#define WALL_PROJECTION_SCALE   ((int32_t)FOCAL_ROWS * CELL_UNITS)
#define FOCAL_COLS_Q8           35472       /* 138.56 columns, 8.8 fixed */
#define SLICE_HEIGHT_MAX        (WALL_PROJECTION_SCALE / DIST_MIN_UNITS)

/* ---- depth bands (fog) ------------------------------------------------- */

#define BAND_COUNT              5
/* The shade level fed to the remap LUT is `band + side`, so there is one more
 * level than there are bands: the unlit face of the furthest band. */
#define SHADE_LEVEL_COUNT       (BAND_COUNT + 1)

/* ---- the clock throttle (DESIGN 5) -------------------------------------- */

#define THROTTLE_UNDERCLOCK     0
#define THROTTLE_NOMINAL        1
#define THROTTLE_OVERCLOCK      2
#define THROTTLE_MODE_COUNT     3
#define THROTTLE_DEFAULT        THROTTLE_NOMINAL
/* Changing the throttle locks input for this many ticks (DESIGN 5). */
#define THROTTLE_SWITCH_TICKS   12

#define RENDER_RADIUS_UNDERCLOCK 6
#define RENDER_RADIUS_NOMINAL    12
#define RENDER_RADIUS_OVERCLOCK  20
#define RENDER_RADIUS_MAX        RENDER_RADIUS_OVERCLOCK

#define RENDER_COLUMNS_LOW      80          /* 4 screen pixels wide */
#define RENDER_COLUMNS_HIGH     160         /* 2 screen pixels wide */

/* Speed multipliers, 8.8 fixed: 1.25 / 1.00 / 0.80. */
#define THROTTLE_SPEED_UNDERCLOCK 320
#define THROTTLE_SPEED_NOMINAL    256
#define THROTTLE_SPEED_OVERCLOCK  205
/* Trace-rate multipliers, 8.8 fixed: 0.5 / 1.0 / 1.6. */
#define THROTTLE_TRACE_UNDERCLOCK 128
#define THROTTLE_TRACE_NOMINAL    256
#define THROTTLE_TRACE_OVERCLOCK  410

/* Hard stop on DDA work per ray; also bounds the worst-case frame. */
#define DDA_MAX_STEPS           64

/*
 * The longest ray the widest throttle traces, and one past it.  A side
 * distance at or beyond DDA_BEYOND_TRACE is "this axis is not crossed inside
 * the trace", which is the value the DDA's own `hit_len > max_trace` test then
 * breaks on - so the two ways a ray can end share one comparison.
 *
 * A delta distance longer than the whole trace can only ever push a side
 * distance past the end, so the DDA clamps the value it ADDS each step to this
 * and keeps the accumulator inside a 16-bit register.  The unclamped delta is
 * still what the door-plane refinement uses, where the true length matters.
 */
#define DDA_MAX_TRACE_UNITS     (RENDER_RADIUS_MAX * CELL_UNITS)
#define DDA_BEYOND_TRACE        (DDA_MAX_TRACE_UNITS + 1)

/* ---- textures and sprites ---------------------------------------------- */

#define WALL_TEXTURE_MAX        15          /* ids 1..15 */
/* The palette index used as the sprite colour key. */
#define SPRITE_TRANSPARENT 15

#define SPRITE_MAX_VISIBLE      32
/* Nearer than this the billboard is behind the eye or absurdly large: cull. */
#define SPRITE_MIN_DEPTH        64
/*
 * screen_x_offset = lateral * g_slice_height[depth] / SPRITE_PROJ_X_DIVISOR
 * at RENDER_COLUMNS_HIGH.  Derivation: 1/depth == height /
 * WALL_PROJECTION_SCALE, so the divisor is
 * WALL_PROJECTION_SCALE * 256 / FOCAL_COLS_Q8 = 16384 * 256 / 35472 = 118.
 * The frustum cull (|lateral| <= depth) keeps the product at or below
 * WALL_PROJECTION_SCALE, so it stays 16 bit.  At 80 columns the offset and the
 * sprite width are both halved after the divide; the height is not, because
 * the window is 80 rows in both modes.
 */
#define SPRITE_PROJ_X_DIVISOR   (WALL_PROJECTION_SCALE * 256 / FOCAL_COLS_Q8)
/*
 * Chunky pixels of sprite the renderer will spend in one frame (DESIGN 8.2),
 * provisional.  It scales with the render width, so it is a property of the
 * detail level and not of the clock throttle: 6000 at 160 columns, 3000 at 80.
 */
#define SPRITE_PIXEL_BUDGET_HIGH 6000
#define SPRITE_PIXEL_BUDGET_LOW  3000

/* ---- map and level ------------------------------------------------------ */

#define MAP_MAX_DIM             64
#define MAP_MAX_CELLS           (MAP_MAX_DIM * MAP_MAX_DIM)
#define MAP_BITMAP_BYTES        (MAP_MAX_CELLS / 8)

#define LEVEL_NAME_LEN          16
#define LEVEL_MAX_ENTITIES      64          /* DESIGN 11: entity_count <= 64 */

/* ---- trace meter (DESIGN 9) --------------------------------------------- */

/* The meter is carried in thousandths of a percent so the per-tick base rate
 * is an integer. */
#define TRACE_MILLI_PER_PERCENT 1000
#define TRACE_MAX_MILLI         (100 * TRACE_MILLI_PER_PERCENT)

#endif /* BLACKICE_GAME_CONSTS_H */
