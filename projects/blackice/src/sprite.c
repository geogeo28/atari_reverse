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

    /*
     * The frustum cull bounds lateral * size by WALL_PROJECTION_SCALE, so the
     * product is a word - and narrowing it before the divide is what makes the
     * 68000 use `divs.w` instead of a __divsi3 call.  This is the one divide
     * per visible sprite the engine spends.
     */
    centre_x = (set->count / 2)
             + (((int16_t)mul16((int16_t)camera->lateral, (int16_t)size)
                 / (int16_t)SPRITE_PROJ_X_DIVISOR)
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

/*
 * Insert into the far-to-near list, keeping at most SPRITE_MAX_VISIBLE.
 *
 * The cap belongs HERE and not in the entity walk.  Capping in file order let
 * the level's 33rd entity be dropped however close it was, which is the one
 * thing DESIGN 8.2 forbids; capping by distance drops the farthest instead,
 * and the farthest is entries[0].
 */
static void insert_by_distance(SpriteList *list, const RenderSprite *sprite)
{
    uint16_t i;

    if (list->count == SPRITE_MAX_VISIBLE) {
        if (sprite->dist >= list->entries[0].dist) {
            return;                     /* no nearer than anything already kept */
        }
        for (i = 0; i + 1 < list->count; ++i) {
            list->entries[i] = list->entries[i + 1];
        }
        --list->count;
    }
    i = list->count;
    while (i > 0 && list->entries[i - 1].dist < sprite->dist) {
        list->entries[i] = list->entries[i - 1];
        --i;
    }
    list->entries[i] = *sprite;
    ++list->count;
}

/*
 * DESIGN 8.2: "a sprite's contribution is the pixels it would actually write:
 * AFTER clipping its projected rectangle to the 160x80 render window".
 *
 * `cols` has already been clipped to the window by project_sprite; `rows` has
 * not, and cannot be - the drawer needs the unclipped height to map a span's
 * texel rows onto screen rows.  So the row clip happens here, and it is not a
 * detail: at FOCAL_ROWS 115 a Watchdog at contact range projects 191 rows into
 * an 80-row window, and charging the budget 191 spends two and a half times
 * what the frame will actually draw.
 *
 * The other half of DESIGN 8.2's rule - "and after the per-column depth test
 * against the wall depth array" - is deliberately NOT applied here.  The wall
 * depths belong to the cast, and the list is built from the simulation snapshot
 * before it; charging a sprite for columns a wall will eat is the conservative
 * direction to be wrong in, and the exact figure is spent in sprite_draw, which
 * has the depths.
 */
int32_t sprite_pixel_cost(const RenderSprite *sprite)
{
    int16_t top = sprite->top;
    int16_t bottom = (int16_t)(top + sprite->rows);     /* exclusive */

    if (top < 0) {
        top = 0;
    }
    if (bottom > RENDER_H) {
        bottom = RENDER_H;
    }
    if (bottom <= top) {
        return 0;
    }
    /* Both factors are clipped to the window - at most RENDER_W_MAX columns by
     * RENDER_H rows - so the product is 12,800 at its largest and this is one
     * `muls.w`.  Spelling it as a 32x32 multiply made it a __mulsi3 call, which
     * is the one thing the Makefile's libgcc gate exists to refuse. */
    return mul16((int16_t)sprite->cols, (int16_t)(bottom - top));
}

/*
 * DESIGN 8.2 step 3: "the nearest attacker is exempt - the closest entity in
 * ATTACK, or if none is attacking, the closest entity - and is always drawn.
 * Every other entity is admitted in ascending-distance order while the
 * accumulator stays under SPR_PX_BUDGET; the rest are dropped farthest-first."
 *
 * The exempt sprite is kept and costs the accumulator nothing, which is exactly
 * what makes DESIGN 8.2's worst case the 12,800 pixels of a window-filling
 * sprite PLUS the budget rather than the budget alone.  The dog eating you is
 * always drawn.
 *
 * The exempt entry is identified by its distance rather than by an index: the
 * list is sorted as it is built, so an index taken during the walk would not
 * survive the insertions after it, and RenderSprite's 26-byte 68000 layout has
 * no room for a back pointer.  Two sprites at exactly the same distance exempt
 * one of them, which is right - the exemption is for one sprite.
 */
static void apply_pixel_budget(SpriteList *list, uint16_t budget,
                               int have_exempt, uint16_t exempt_dist)
{
    uint8_t keep[SPRITE_MAX_VISIBLE];
    int32_t spent = 0;
    int exempt_taken = 0;
    int budget_spent = 0;
    uint16_t write = 0;
    uint16_t i;

    if (list->count == 0) {
        return;
    }
    /* The exempt body can still have been evicted by the SPRITE_MAX_VISIBLE cap
     * - which takes 32 nearer bodies on screen at once.  The nearest survivor
     * then takes the exemption, which is DESIGN 8.2's own "if none is attacking"
     * fallback and keeps the guarantee that SOMETHING is always drawn. */
    if (have_exempt) {
        int found = 0;

        for (i = 0; i < list->count; ++i) {
            found |= list->entries[i].dist == exempt_dist;
        }
        if (!found) {
            exempt_dist = list->entries[list->count - 1].dist;
        }
    }

    /* Near end first: the far sprites are the ones that vanish. */
    for (i = list->count; i > 0; --i) {
        const RenderSprite *sprite = &list->entries[i - 1];
        int32_t cost;

        if (have_exempt && !exempt_taken && sprite->dist == exempt_dist) {
            exempt_taken = 1;
            keep[i - 1] = 1;
            continue;
        }
        cost = sprite_pixel_cost(sprite);
        if (budget_spent || spent + cost > budget) {
            budget_spent = 1;               /* farthest-first, so nothing after it fits */
            keep[i - 1] = 0;
            continue;
        }
        spent += cost;
        keep[i - 1] = 1;
    }
    /* Compacted in place, keeping the far-to-near order the drawer needs. */
    for (i = 0; i < list->count; ++i) {
        if (keep[i]) {
            list->entries[write++] = list->entries[i];
        }
    }
    list->count = write;
}

void sprite_build_list(const GameState *state, SpriteList *list)
{
    const Level *level = state->level;
    const ThrottleMode *mode = render_mode(state);
    const ColumnSet *set = render_columns(state);
    int have_exempt = 0;
    int exempt_attacks = 0;
    uint16_t exempt_dist = 0;
    uint16_t i;

    list->count = 0;
    for (i = 0; i < level->entity_count; ++i) {
        const Entity *entity = &level->entities[i];
        const SpriteAsset *asset;
        CameraSpace camera;
        RenderSprite sprite;
        int attacks;

        if (!entity_is_live(state, i)) {
            continue;
        }
        asset = g_entity_sprites[entity->type];
        if (!asset) {
            continue;
        }
        /* The AUTHORED cell is where the body started; the runtime table is
         * where it is now.  A pickup never leaves its centre, so this is the
         * same point for one and the live position for the other. */
        camera = to_camera_space(&state->player,
                                 entity_world_x(state, i), entity_world_y(state, i));
        if (!project_sprite(&camera, set, mode, asset, &sprite)) {
            continue;
        }
        /* An attacker outranks any distance, and among attackers - or among
         * everything, when nothing is attacking - the nearest wins. */
        attacks = state->entities[i].state == ENT_STATE_ATTACK;
        if (!have_exempt
            || (attacks && !exempt_attacks)
            || (attacks == exempt_attacks && sprite.dist < exempt_dist)) {
            have_exempt = 1;
            exempt_attacks = attacks;
            exempt_dist = sprite.dist;
        }
        insert_by_distance(list, &sprite);
    }
    apply_pixel_budget(list, set->sprite_budget, have_exempt, exempt_dist);
}

/* Screen row a texel row maps to.  Both factors are words - the texel row is
 * under TEX_DIM and the height under SLICE_HEIGHT_MAX - so it is one `muls.w`
 * into a 32-bit product, which is what mul16 is for. */
static int32_t screen_row_of_texel(const RenderSprite *sprite, uint16_t texel_row)
{
    return sprite->top + (mul16((int16_t)texel_row, (int16_t)sprite->rows) >> TEX_DIM_SHIFT);
}

static void draw_sprite_column(const RenderSprite *sprite, uint16_t texel_u, uint8_t *column_base)
{
    const SpriteSpan span = sprite->spans[texel_u];
    const uint8_t *texels = sprite->texels + texel_u * TEX_DIM;
    const uint8_t *shade = g_shade_lut[sprite->band];
    int32_t first_row;
    int32_t last_row;
    uint16_t texel_v;
    uint16_t step_v;
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

    /* Hoisted: the stores below may alias the RenderSprite as far as the
     * compiler knows, so it reloaded the step through the pointer per pixel. */
    step_v = sprite->tex_step_v;
    texel_v = (uint16_t)((first_row - sprite->top) * step_v);
    dst = column_base + first_row;
    for (row = first_row; row <= last_row; ++row) {
        uint8_t texel = texels[fix88_whole(texel_v)];

        if (texel != SPRITE_TRANSPARENT) {
            *dst = shade[texel];
        }
        ++dst;
        texel_v = (uint16_t)(texel_v + step_v);
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
            uint16_t index = fix88_whole(texel_u);

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
