/*
 * raycast.c - one DDA per screen column, producing the RenderColumn list.
 *
 * The algorithm is the textbook grid DDA with two changes that remove every
 * divide from the per-column path:
 *
 *  1. The "delta distance" (ray length per whole cell of travel along one axis)
 *     comes from g_inv_cos_dist, a 1024-entry table indexed by the ray angle,
 *     instead of a reciprocal computed per ray.
 *  2. The slice height and the texture step come from g_slice_height and
 *     g_tex_step, both indexed directly by the perpendicular distance in map
 *     units, instead of DIST_SCALE / dist and (64 << 8) / height.
 *
 * The perpendicular distance itself is the ray length times a per-column
 * cosine (g_col_cos_*), which is the fisheye correction: the ray angles are
 * atan-spaced across the FOV, so multiplying by cos(column angle) yields the
 * distance to the projection plane and a flat wall projects flat.
 *
 * See render.h for the 68000 cycle model.
 */
#include "render.h"

/* Texture coordinates are 64 wide and a cell is 256 map units across. */
#define TEXEL_SHIFT_FROM_UNITS 2

/*
 * The mode's band edges, lifted out of the ThrottleMode once per frame so the
 * per-column band test is a straight-line compare chain over registers rather
 * than a loop with a bounds test and an indexed load.  Unused edges are
 * BAND_LIMIT_UNUSED (0xffff), which is why a three-band mode needs no special
 * case: nothing is ever further away than that.
 */
typedef struct {
    uint16_t limit[BAND_COUNT - 1];
    uint8_t  last;
} BandEdges;

static BandEdges band_edges_of(const ThrottleMode *mode)
{
    BandEdges edges;
    uint8_t i;

    for (i = 0; i < BAND_COUNT - 1; ++i) {
        edges.limit[i] = mode->band_limit[i];
    }
    edges.last = (uint8_t)(mode->band_count - 1);
    return edges;
}

/* band_of's chain is written out for exactly BAND_COUNT - 1 edges. */
typedef char band_of_is_written_for_five_bands[(BAND_COUNT == 5) ? 1 : -1];

static uint8_t band_of(const BandEdges *edges, uint16_t dist_units)
{
    if (dist_units < edges->limit[0]) {
        return 0;
    }
    if (dist_units < edges->limit[1]) {
        return 1;
    }
    if (dist_units < edges->limit[2]) {
        return 2;
    }
    if (dist_units < edges->limit[3]) {
        return 3;
    }
    return edges->last;
}

uint8_t render_band_for_dist(const ThrottleMode *mode, uint16_t dist_units)
{
    const BandEdges edges = band_edges_of(mode);

    return band_of(&edges, dist_units);
}

/*
 * Turn a perpendicular distance into the clipped screen extent of the slice
 * and the texture v it starts at.  This is the whole of the projection: two
 * table reads and a shift.
 */
static inline void project_slice(uint16_t perp_units, RenderColumn *column)
{
    uint16_t table_index = dist_clamp_index(perp_units);
    uint16_t height = g_slice_height[table_index];
    uint16_t step = g_tex_step[table_index];
    int32_t top = ((int32_t)RENDER_H - height) >> 1;    /* floors, so it stays symmetric */

    column->tex_step = step;
    if (top < 0) {
        /* A slice taller than the window is at most SLICE_HEIGHT_MAX rows, so
         * the overhang and the step both fit a word. */
        column->tex_v = (uint16_t)mul16((int16_t)(-top), (int16_t)step);
        column->top = 0;
        column->rows = RENDER_H;
    } else {
        uint16_t rows = height;

        if (top + rows > RENDER_H) {
            rows = (uint16_t)(RENDER_H - top);
        }
        column->tex_v = 0;
        column->top = (int16_t)top;
        column->rows = rows;
    }
}

static void emit_far_column(const BandEdges *edges, int32_t max_trace,
                            uint16_t column_cos, RenderColumn *column, uint16_t *wall_dist)
{
    /* max_trace is at most RENDER_RADIUS_MAX cells and the cosine is 1.14. */
    uint16_t perp = (uint16_t)(mul16((int16_t)max_trace, (int16_t)column_cos) >> TRIG_SHIFT);

    project_slice(perp, column);
    column->tex_id = COLUMN_TEX_FAR;
    column->tex_col = 0;
    column->band = edges->last;
    column->side = SIDE_NS;
    /* A flat far-fill slab never occludes a sprite: everything the sim will
     * draw is nearer than the cut-off by construction. */
    *wall_dist = WALL_DIST_NONE;
}

/*
 * How far along the ray the first crossing of one axis lies, in map units.
 *
 * `to_next_units` is the distance to that axis's next grid line (0..CELL_UNITS)
 * and `delta` the ray length per whole cell along it, so the product is a
 * genuine unsigned 16x16 - a delta can exceed INT16_MAX.  Anything at or past
 * the end of the trace collapses to DDA_BEYOND_TRACE, which is also what a
 * grid-parallel ray's never-crossed axis returns, so the loop needs only one
 * end-of-ray test.
 */
static int16_t first_crossing(uint16_t to_next_units, uint16_t delta, int32_t max_trace)
{
    int32_t side;

    if (delta == DELTA_DIST_NEVER) {
        return DDA_BEYOND_TRACE;
    }
    side = (int32_t)(mulu16(to_next_units, delta) >> CELL_SHIFT);
    return (int16_t)(side > max_trace ? DDA_BEYOND_TRACE : side);
}

/* The value the DDA adds to a side distance each step.  See DDA_BEYOND_TRACE:
 * a step longer than the whole trace is indistinguishable from one exactly
 * that long, and clamping keeps the accumulator in a word. */
static int16_t delta_step(uint16_t delta)
{
    return (int16_t)(delta > DDA_BEYOND_TRACE ? DDA_BEYOND_TRACE : delta);
}

void render_cast(const GameState *state, RenderScratch *scratch)
{
    const ThrottleMode *mode = render_mode(state);
    const BandEdges edges = band_edges_of(mode);
    const ColumnSet *set = render_columns(state);
    const MapGrid grid = level_grid(state->level);
    const int32_t max_trace = (int32_t)mode->radius_cells * CELL_UNITS;
    const fix88_t pos_x = state->player.x;
    const fix88_t pos_y = state->player.y;
    uint16_t c;

    for (c = 0; c < set->count; ++c) {
        angle_t ray_angle = (angle_t)(state->player.angle + set->angle[c]);
        uint16_t trig_index = TRIG_INDEX(ray_angle);
        int16_t sine = g_sin_1024[trig_index];
        int16_t cosine = g_sin_1024[TRIG_INDEX_ADD(trig_index, TRIG_QUARTER_ENTRIES)];
        uint16_t delta_x = g_inv_cos_dist[trig_index];
        uint16_t delta_y = g_inv_cos_dist[TRIG_INDEX_ADD(trig_index, -TRIG_QUARTER_ENTRIES)];
        int16_t delta_step_x = delta_step(delta_x);
        int16_t delta_step_y = delta_step(delta_y);
        RenderColumn *column = &scratch->columns[c];
        int16_t map_x = (int16_t)(pos_x >> CELL_SHIFT);
        int16_t map_y = (int16_t)(pos_y >> CELL_SHIFT);
        int16_t step_x = (cosine >= 0) ? 1 : -1;
        int16_t step_y = (sine >= 0) ? 1 : -1;
        int32_t index_step_y = (int32_t)step_y * grid.width;
        int32_t index = map_cell_index(&grid, map_x, map_y);
        uint16_t to_next_x = (uint16_t)((cosine >= 0) ? (CELL_UNITS - (pos_x & CELL_FRAC_MASK))
                                                      : (pos_x & CELL_FRAC_MASK));
        uint16_t to_next_y = (uint16_t)((sine >= 0) ? (CELL_UNITS - (pos_y & CELL_FRAC_MASK))
                                                    : (pos_y & CELL_FRAC_MASK));
        int16_t side_x = first_crossing(to_next_x, delta_x, max_trace);
        int16_t side_y = first_crossing(to_next_y, delta_y, max_trace);
        int16_t hit_len = 0;
        uint16_t hit_u_units = 0;
        uint8_t side = SIDE_NS;
        uint8_t cell = CELL_EMPTY;
        int hit = 0;
        int step;

        for (step = 0; step < DDA_MAX_STEPS; ++step) {
            if (side_x < side_y) {
                hit_len = side_x;
                side_x = (int16_t)(side_x + delta_step_x);
                map_x = (int16_t)(map_x + step_x);
                index += step_x;
                side = SIDE_EW;
            } else {
                hit_len = side_y;
                side_y = (int16_t)(side_y + delta_step_y);
                map_y = (int16_t)(map_y + step_y);
                index += index_step_y;
                side = SIDE_NS;
            }
            if (hit_len > max_trace) {
                break;
            }
            if (!map_cell_blocks(&state->blocking, (uint16_t)index)) {
                continue;
            }

            cell = grid.cells[index];
            if (CELL_IS_DOOR(cell)) {
                uint8_t door = state->door_of_cell[index];
                /* Half a step along the axis just crossed, from the UNCLAMPED
                 * delta: this is a geometric length, not an accumulator, so a
                 * near-axis ray must see the real one and reject the door. */
                int32_t plane_len = hit_len
                                  + (int32_t)((side == SIDE_EW ? delta_x : delta_y) >> 1);
                int32_t across;

                /* An open door is simply not there: v1 renders two states. */
                if (door != DOOR_NONE && DOOR_IS_PASSABLE(state->doors[door])) {
                    continue;
                }
                /*
                 * The leaf hangs on the cell midline perpendicular to the axis
                 * the ray just crossed, so step half a delta further and take
                 * the hit only if the ray has not left the cell sideways -
                 * the Wolf3D convention, one add and one compare.
                 */
                if (plane_len > max_trace) {
                    break;
                }
                /* plane_len passed the max_trace test above, so it is a word. */
                across = (side == SIDE_EW)
                       ? (pos_y + (mul16(sine, (int16_t)plane_len) >> TRIG_SHIFT))
                       : (pos_x + (mul16(cosine, (int16_t)plane_len) >> TRIG_SHIFT));
                if ((across >> CELL_SHIFT) != ((side == SIDE_EW) ? map_y : map_x)) {
                    continue;
                }
                hit_len = (int16_t)plane_len;
                hit_u_units = (uint16_t)(across & CELL_FRAC_MASK);
                hit = 1;
                break;
            }

            /* Where along the face the ray landed, in map units within the cell. */
            if (side == SIDE_EW) {
                hit_u_units = (uint16_t)((pos_y + (mul16(sine, (int16_t)hit_len) >> TRIG_SHIFT))
                                         & CELL_FRAC_MASK);
            } else {
                hit_u_units = (uint16_t)((pos_x + (mul16(cosine, (int16_t)hit_len) >> TRIG_SHIFT))
                                         & CELL_FRAC_MASK);
            }
            hit = 1;
            break;
        }

        if (!hit) {
            emit_far_column(&edges, max_trace, set->cosine[c], column, &scratch->wall_dist[c]);
            continue;
        }

        {
            uint16_t perp = (uint16_t)(mul16((int16_t)hit_len,
                                             (int16_t)set->cosine[c]) >> TRIG_SHIFT);
            uint16_t tex_col = (uint16_t)(hit_u_units >> TEXEL_SHIFT_FROM_UNITS);

            /* Mirror the u on the two faces whose winding runs the other way,
             * or adjacent walls meet with the texture flipped. */
            if ((side == SIDE_EW && cosine > 0) || (side == SIDE_NS && sine < 0)) {
                tex_col = (uint16_t)(TEX_INDEX_MASK - tex_col);
            }

            project_slice(perp, column);
            column->tex_id = g_cell_texture[cell];
            column->tex_col = (uint8_t)tex_col;
            column->band = band_of(&edges, perp);
            column->side = side;
            scratch->wall_dist[c] = perp;
        }
    }
}
