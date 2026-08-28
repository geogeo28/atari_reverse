/*
 * sprite.c - billboard projection, the drop budget and the reference drawer.
 *
 * Projection reuses the wall reciprocal table, so a sprite costs no divide
 * beyond the one that places its centre column.  The vertical extent is the
 * same g_slice_height a wall of one cell would have at that distance, which is
 * what makes a billboard sit correctly among the geometry.
 *
 * At 80 columns each chunky pixel is twice as wide in world terms, so the
 * horizontal half of the projection is shifted down by ColumnSet.width_shift
 * while the vertical half is untouched: the window is 80 rows either way.
 *
 * See render.h for the cycle model.
 */
#include "sprite.h"
#include "render.h"

/* Texel v of the sprite's top row and one past its bottom, in 8.8. */
#define SPRITE_TEXEL_ROWS TEX_DIM

typedef struct {
    int32_t depth;      /* distance along the view direction, map units */
    int32_t lateral;    /* distance to the player's right, map units */
} CameraSpace;

static CameraSpace to_camera_space(const Player *player, fix88_t world_x, fix88_t world_y)
{
    int32_t dx = (int32_t)world_x - player->x;
    int32_t dy = (int32_t)world_y - player->y;
    int16_t cosine = angle_cos(player->angle);
    int16_t sine = angle_sin(player->angle);
    CameraSpace out;

    /* Both deltas are differences of map coordinates, so they are words. */
    out.depth = (mul16((int16_t)dx, cosine) + mul16((int16_t)dy, sine)) >> TRIG_SHIFT;
    out.lateral = (mul16((int16_t)-dx, sine) + mul16((int16_t)dy, cosine)) >> TRIG_SHIFT;
    return out;
}

/*
 * Fill in a RenderSprite from a camera-space position.  Returns 0 when the
 * billboard is culled: behind the eye, past the throttle radius, or entirely
 * off the side of the window.
 */
static int project_sprite(const CameraSpace *camera, const ColumnSet *set,
                          const ThrottleMode *mode, const SpriteAsset *asset,
                          RenderSprite *out)
{
    uint16_t table_index;
    uint16_t size;
    int32_t centre_x;
    int32_t left;
    int32_t cols;
    int32_t max_column;

    if (camera->depth < SPRITE_MIN_DEPTH
        || camera->depth > (int32_t)mode->radius_cells * CELL_UNITS) {
        return 0;
    }
    /* A generous frustum test - wider than the 60 degree FOV - which also
     * bounds lateral * height below WALL_PROJECTION_SCALE so the projection
     * stays inside 16 bits. */
    if (camera->lateral > camera->depth || -camera->lateral > camera->depth) {
        return 0;
    }

    table_index = dist_clamp_index(camera->depth);
    size = g_slice_height[table_index];
    max_column = set->count - 1;

    /* The frustum cull bounds lateral * size by WALL_PROJECTION_SCALE, so this
     * is a word product; the divide is the one per sprite the engine spends. */
    centre_x = (set->count / 2)
             + ((mul16((int16_t)camera->lateral, (int16_t)size) / SPRITE_PROJ_X_DIVISOR)
                >> set->width_shift);
    cols = size >> set->width_shift;
    if (cols == 0) {
        return 0;
    }
    left = centre_x - cols / 2;

    out->texels = asset->texels;
    out->spans = asset->spans;
    out->rows = size;
    out->top = (int16_t)(((int32_t)RENDER_H - size) >> 1);
    out->tex_step_v = g_tex_step[table_index];
    out->tex_step_u = (uint16_t)(out->tex_step_v << set->width_shift);
    out->dist = (uint16_t)camera->depth;
    out->band = (uint8_t)render_band_for_dist(mode, (uint16_t)camera->depth);
    out->pad = 0;

    if (left < 0) {
        out->tex_u = (uint16_t)((-left) * out->tex_step_u);
        cols += left;
        left = 0;
    } else {
        out->tex_u = 0;
    }
    if (left + cols > max_column + 1) {
        cols = max_column + 1 - left;
    }
    if (cols <= 0) {
        return 0;
    }
    out->left = (int16_t)left;
    out->cols = (uint16_t)cols;
    return 1;
}

/* Insertion sort by distance, farthest first: the list is at most
 * SPRITE_MAX_VISIBLE long and almost always nearly sorted already. */
static void sort_far_to_near(SpriteList *list)
{
    uint16_t i;

    for (i = 1; i < list->count; ++i) {
        RenderSprite key = list->entries[i];
        uint16_t j = i;

        while (j > 0 && list->entries[j - 1].dist < key.dist) {
            list->entries[j] = list->entries[j - 1];
            --j;
        }
        list->entries[j] = key;
    }
}

/*
 * DESIGN 8.2: spend the per-frame pixel budget in drop-priority order and cut
 * the list where it runs out.  With no AI states yet the priority is distance
 * alone, so the walk runs from the near end and the farthest sprites are the
 * ones that vanish - and the nearest can never be dropped.
 */
static void apply_pixel_budget(SpriteList *list, uint16_t budget)
{
    int32_t spent = 0;
    uint16_t kept = 0;
    uint16_t i;

    for (i = list->count; i > 0; --i) {
        const RenderSprite *sprite = &list->entries[i - 1];
        int32_t cost = (int32_t)sprite->cols * sprite->rows;

        if (kept > 0 && spent + cost > budget) {
            break;
        }
        spent += cost;
        ++kept;
    }
    if (kept < list->count) {
        uint16_t first_kept = (uint16_t)(list->count - kept);

        for (i = 0; i < kept; ++i) {
            list->entries[i] = list->entries[first_kept + i];
        }
        list->count = kept;
    }
}

void sprite_build_list(const GameState *state, SpriteList *list)
{
    const Level *level = state->level;
    const ThrottleMode *mode = render_mode(state);
    const ColumnSet *set = render_columns(state);
    uint16_t i;

    list->count = 0;
    for (i = 0; i < level->entity_count && list->count < SPRITE_MAX_VISIBLE; ++i) {
        const Entity *entity = &level->entities[i];
        const SpriteAsset *asset;
        CameraSpace camera;

        if (!state->entity_alive[i]) {
            continue;
        }
        asset = g_entity_sprites[entity->type];
        if (!asset) {
            continue;
        }
        camera = to_camera_space(&state->player,
                                 cell_centre(entity->cell_x), cell_centre(entity->cell_y));
        if (project_sprite(&camera, set, mode, asset, &list->entries[list->count])) {
            ++list->count;
        }
    }
    sort_far_to_near(list);
    apply_pixel_budget(list, mode->sprite_budget);
}

/* Screen row a texel row maps to.  size <= SLICE_HEIGHT_MAX and the texel row
 * is under TEX_DIM, so the product stays inside 16 bits. */
static int32_t screen_row_of_texel(const RenderSprite *sprite, uint16_t texel_row)
{
    return sprite->top + (mul16((int16_t)texel_row, (int16_t)sprite->rows) >> 6);
}

static void draw_sprite_column(const RenderSprite *sprite, uint16_t texel_u, uint8_t *column_base)
{
    const SpriteSpan span = sprite->spans[texel_u];
    const uint8_t *texels = sprite->texels + texel_u * TEX_DIM;
    const uint8_t *shade = g_shade_lut[sprite->band];
    int32_t first_row;
    int32_t last_row;
    uint16_t texel_v;
    uint8_t *dst;
    int32_t row;

    if (SPRITE_SPAN_IS_EMPTY(span)) {
        return;
    }
    first_row = screen_row_of_texel(sprite, span.first);
    last_row = screen_row_of_texel(sprite, (uint16_t)(span.last + 1)) - 1;
    if (first_row < 0) {
        first_row = 0;
    }
    if (last_row > RENDER_H - 1) {
        last_row = RENDER_H - 1;
    }
    if (first_row > last_row) {
        return;
    }

    texel_v = (uint16_t)((first_row - sprite->top) * sprite->tex_step_v);
    dst = column_base + first_row;
    for (row = first_row; row <= last_row; ++row) {
        uint8_t texel = texels[texel_v >> CELL_SHIFT];

        if (texel != SPRITE_TRANSPARENT) {
            *dst = shade[texel];
        }
        ++dst;
        texel_v = (uint16_t)(texel_v + sprite->tex_step_v);
    }
}

void sprite_draw(const SpriteList *list, const uint16_t *wall_dist,
                 uint16_t columns, uint8_t *chunky)
{
    uint16_t s;

    for (s = 0; s < list->count; ++s) {
        const RenderSprite *sprite = &list->entries[s];
        uint16_t texel_u = sprite->tex_u;
        uint16_t c;

        for (c = 0; c < sprite->cols; ++c) {
            uint16_t screen_x = (uint16_t)(sprite->left + c);
            uint16_t index = texel_u >> CELL_SHIFT;

            texel_u = (uint16_t)(texel_u + sprite->tex_step_u);
            if (screen_x >= columns || index >= TEX_DIM) {
                continue;
            }
            if (sprite->dist >= wall_dist[screen_x]) {
                continue;                       /* the wall in this column is nearer */
            }
            draw_sprite_column(sprite, index, chunky + RENDER_PIXEL_OFFSET(screen_x, 0));
        }
    }
}
