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

static uint16_t band_of(const ThrottleMode *mode, uint16_t dist_units)
{
    uint8_t band;

    for (band = 0; band + 1 < mode->band_count; ++band) {
        if (dist_units < mode->band_limit[band]) {
            return band;
        }
    }
    return (uint16_t)(mode->band_count - 1);
}

uint8_t render_band_for_dist(const ThrottleMode *mode, uint16_t dist_units)
{
    return (uint8_t)band_of(mode, dist_units);
}

/*
 * Turn a perpendicular distance into the clipped screen extent of the slice
 * and the texture v it starts at.  This is the whole of the projection: two
 * table reads and a shift.
 */
static void project_slice(uint16_t perp_units, RenderColumn *column)
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

static void emit_far_column(const ThrottleMode *mode, int32_t max_trace,
                            uint16_t column_cos, RenderColumn *column, uint16_t *wall_dist)
{
    /* max_trace is at most RENDER_RADIUS_MAX cells and the cosine is 1.14. */
    uint16_t perp = (uint16_t)(mul16((int16_t)max_trace, (int16_t)column_cos) >> TRIG_SHIFT);

    project_slice(perp, column);
    column->tex_id = COLUMN_TEX_FAR;
    column->tex_col = 0;
    column->band = (uint8_t)(mode->band_count - 1);
    column->side = SIDE_NS;
    /* A flat far-fill slab never occludes a sprite: everything the sim will
     * draw is nearer than the cut-off by construction. */
    *wall_dist = 0xffff;
}

void render_cast(const GameState *state, RenderScratch *scratch)
{
    const ThrottleMode *mode = render_mode(state);
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
        int32_t delta_x = g_inv_cos_dist[trig_index];
        int32_t delta_y = g_inv_cos_dist[TRIG_INDEX_ADD(trig_index, -TRIG_QUARTER_ENTRIES)];
        RenderColumn *column = &scratch->columns[c];
        int16_t map_x = (int16_t)(pos_x >> CELL_SHIFT);
        int16_t map_y = (int16_t)(pos_y >> CELL_SHIFT);
        int16_t step_x = (cosine >= 0) ? 1 : -1;
        int16_t step_y = (sine >= 0) ? 1 : -1;
        int32_t index_step_y = (int32_t)step_y * grid.width;
        int32_t index = map_cell_index(&grid, map_x, map_y);
        int32_t side_x;
        int32_t side_y;
        int32_t half_delta = 0;     /* half a step along the axis just crossed */
        int32_t hit_len = 0;
        uint16_t hit_u_units = 0;
        uint8_t side = SIDE_NS;
        uint8_t cell = CELL_EMPTY;
        int hit = 0;
        int step;

        {
            int32_t to_next_x = (cosine >= 0) ? (CELL_UNITS - (pos_x & CELL_FRAC_MASK))
                                              : (pos_x & CELL_FRAC_MASK);
            int32_t to_next_y = (sine >= 0) ? (CELL_UNITS - (pos_y & CELL_FRAC_MASK))
                                            : (pos_y & CELL_FRAC_MASK);

            /* A distance into the cell is under CELL_UNITS and a delta is
             * clamped to DELTA_DIST_MAX, so both are words. */
            side_x = mul16((int16_t)to_next_x, (int16_t)delta_x) >> CELL_SHIFT;
            side_y = mul16((int16_t)to_next_y, (int16_t)delta_y) >> CELL_SHIFT;
        }

        for (step = 0; step < DDA_MAX_STEPS; ++step) {
            if (side_x < side_y) {
                hit_len = side_x;
                half_delta = delta_x >> 1;
                side_x += delta_x;
                map_x = (int16_t)(map_x + step_x);
                index += step_x;
                side = SIDE_EW;
            } else {
                hit_len = side_y;
                half_delta = delta_y >> 1;
                side_y += delta_y;
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
                int32_t plane_len = hit_len + half_delta;
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
                hit_len = plane_len;
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
            emit_far_column(mode, max_trace, set->cosine[c], column, &scratch->wall_dist[c]);
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
            column->tex_id = map_cell_texture(cell);
            column->tex_col = (uint8_t)tex_col;
            column->band = (uint8_t)band_of(mode, perp);
            column->side = side;
            scratch->wall_dist[c] = perp;
        }
    }
}
