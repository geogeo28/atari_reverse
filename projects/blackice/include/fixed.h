/*
 * fixed.h - fixed-point types, trig and reciprocal tables for BLACK ICE.
 *
 * There is no floating point anywhere in the engine: the target is a stock
 * 68000 with no FPU and no libm.  Two number formats carry everything:
 *
 *   map units (fix88_t)  8.8 fixed point, one grid cell = CELL_UNITS (256).
 *                        A 64x64 map spans 16384 units, so a signed 16-bit
 *                        word holds any map coordinate with room to spare.
 *   angles   (angle_t)   unsigned 16 bit, 0..65535 = one full turn.  Wrapping
 *                        is free: uint16_t arithmetic wraps by definition.
 *
 * Trig values are 1.14 fixed (TRIG_ONE == 1.0) so that a 16x16 `muls` against
 * a map-unit distance lands in a 32-bit product that only needs a >>14 to come
 * back to map units.  The 68000 has `muls`/`mulu` 16x16->32 and `divu` 32/16->16
 * and nothing wider, so every hot-path product is deliberately 16x16.
 */
#ifndef BLACKICE_FIXED_H
#define BLACKICE_FIXED_H

#include <stdint.h>

/* ---- map units -------------------------------------------------------- */

#define CELL_SHIFT      8
#define CELL_UNITS      (1 << CELL_SHIFT)   /* map units per grid cell */
#define CELL_FRAC_MASK  (CELL_UNITS - 1)

typedef int16_t  fix88_t;   /* map coordinate or distance, 8.8 fixed */
typedef uint16_t angle_t;   /* 0..65535 == one full turn */

/* ---- angles ----------------------------------------------------------- */

#define ANGLE_QUARTER_TURN  16384

/*
 * DESIGN.md states angles in "brads", 1024 to a full turn, and the .bil level
 * file stores them that way.  The engine works in 16-bit angle_t so that a
 * turn is a plain uint16 add with free wraparound; brads convert on load.
 */
#define BRADS_PER_TURN          1024
#define ANGLE_UNITS_PER_BRAD    (65536 / BRADS_PER_TURN)   /* 64 */
#define ANGLE_FROM_BRADS(b)     ((angle_t)((uint16_t)(b) * ANGLE_UNITS_PER_BRAD))

/* ---- the 68000's only widening multiply --------------------------------- */

/*
 * `muls.w` is 16x16 -> 32 and costs about 70 cycles; it is the widest multiply
 * the 68000 has.  A product written as 32x32 becomes a call to libgcc's
 * __mulsi3, a subroutine costing several times that, and in a per-column loop
 * the difference is tens of thousands of cycles a frame.  GCC only picks the
 * instruction when it can see BOTH operands are 16 bit, so every hot product in
 * the engine goes through here and each narrowing cast is a deliberate claim
 * about that value's range, documented where it is made.
 */
static inline int32_t mul16(int16_t a, int16_t b)
{
    return (int32_t)a * (int32_t)b;
}

/* ---- 1.14 trig tables -------------------------------------------------- */

#define TRIG_ONE            16384       /* 1.0 in 1.14 fixed */
#define TRIG_SHIFT          14
#define TRIG_TABLE_SIZE     1024
#define TRIG_INDEX_SHIFT    6           /* angle_t >> 6 -> table index */
#define TRIG_INDEX_MASK     (TRIG_TABLE_SIZE - 1)
#define TRIG_QUARTER_ENTRIES (TRIG_TABLE_SIZE / 4)  /* entries per 90 degrees */

extern const int16_t g_sin_1024[TRIG_TABLE_SIZE];

/*
 * Ray length gained per whole grid cell of travel along one axis, in map
 * units: CELL_UNITS / |cos(theta)| for the x axis.  This is the DDA's
 * "delta distance" and replaces the per-ray divide that the textbook
 * algorithm needs.  Near a grid-parallel ray the true value is unbounded, so
 * it saturates at DELTA_DIST_MAX - clamping *high* is the safe direction
 * because it only makes the DDA prefer the other axis, and the ray leaves the
 * map long before the error matters.
 */
#define DELTA_DIST_MAX  32000
extern const uint16_t g_inv_cos_dist[TRIG_TABLE_SIZE];

/* Table index for an angle, and the quarter-turn shift that turns cos into sin. */
#define TRIG_INDEX(angle)       (((uint16_t)(angle) >> TRIG_INDEX_SHIFT) & TRIG_INDEX_MASK)
#define TRIG_INDEX_ADD(i, d)    (((i) + (d)) & TRIG_INDEX_MASK)

static inline int16_t angle_sin(angle_t a)
{
    return g_sin_1024[TRIG_INDEX(a)];
}

static inline int16_t angle_cos(angle_t a)
{
    return g_sin_1024[TRIG_INDEX_ADD(TRIG_INDEX(a), TRIG_QUARTER_ENTRIES)];
}

/* ---- reciprocal tables ------------------------------------------------- */

/*
 * Both tables are indexed directly by a perpendicular distance in map units,
 * which removes every divide from the per-column and per-sprite work.
 *
 *   g_slice_height[d]  projected pixel height of a one-cell-tall wall at
 *                      distance d, == WALL_PROJECTION_SCALE / d.
 *   g_tex_step[d]      texels of a 64-tall texture per screen row for that
 *                      same slice, 8.8 fixed, == (TEX_DIM << 8) / height.
 *
 * Entries below DIST_MIN_UNITS are filled with the DIST_MIN_UNITS value, so a
 * caller only has to clamp the top end.  DIST_TABLE_SIZE is a power of two so
 * the clamp is a compare against a constant and nothing else.
 *
 * The tables are 32 KB of .bss filled by tables_init() rather than 32 KB of
 * const data, to keep them out of the .PRG on the target.
 */
#define DIST_TABLE_SIZE 8192                        /* 32 cells of traced depth */
#define DIST_TABLE_MAX  (DIST_TABLE_SIZE - 1)
#define DIST_MIN_UNITS  48                          /* closer than the player can stand */

extern uint16_t g_slice_height[DIST_TABLE_SIZE];
extern uint16_t g_tex_step[DIST_TABLE_SIZE];

/* Fill the reciprocal tables.  Call once at start-up before any rendering. */
void tables_init(void);

static inline uint16_t dist_clamp_index(int32_t dist_units)
{
    if (dist_units < 0) {
        return 0;
    }
    if (dist_units > DIST_TABLE_MAX) {
        return DIST_TABLE_MAX;
    }
    return (uint16_t)dist_units;
}

#endif /* BLACKICE_FIXED_H */
