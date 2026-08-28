/*
 * draw.c - the reference column drawer and the frame assembly.
 *
 * This is the code the hand-written 68000 inner loop must match byte for byte.
 * It is deliberately plain: one pointer walking a contiguous run of the
 * column-major chunky buffer, a two-register texel accumulator, and no
 * clipping, branching or division inside the loop - render_cast already
 * resolved all of that into the RenderColumn.
 *
 * See render.h for the cycle model.
 */
#include "mem.h"
#include "render.h"
#include "sprite.h"

static void draw_far_column(const RenderColumn *column, uint8_t *dst)
{
    memset(dst, COLOUR_FAR_FILL, column->rows);
}

static void draw_textured_column(const RenderColumn *column, uint8_t *dst)
{
    const uint8_t *texels = g_wall_textures[column->tex_id] + column->tex_col * TEX_DIM;
    const uint8_t *shade = g_shade_lut[column->band + column->side];
    uint16_t texel_v = column->tex_v;
    uint16_t step = column->tex_step;
    /* Counted down in a local: `column->rows` reloaded through the pointer
     * every iteration, because the compiler cannot prove the stores do not
     * alias the RenderColumn. */
    uint16_t rows = column->rows;

    while (rows--) {
        *dst++ = shade[texels[fix88_whole(texel_v)]];
        texel_v = (uint16_t)(texel_v + step);
    }
}

void render_draw_columns(const RenderScratch *scratch, uint16_t columns, uint8_t *chunky)
{
    uint16_t c;

    for (c = 0; c < columns; ++c) {
        const RenderColumn *column = &scratch->columns[c];
        uint8_t *dst = chunky + RENDER_PIXEL_OFFSET(c, column->top);

        if (column->rows == 0) {
            continue;
        }
        if (column->tex_id == COLUMN_TEX_FAR) {
            draw_far_column(column, dst);
        } else {
            draw_textured_column(column, dst);
        }
    }
}

void render_clear(uint8_t *chunky, uint16_t columns)
{
    /* The buffer is column major and the used columns start at 0, so the live
     * region is one contiguous run whatever the column count is. */
    memset(chunky, COLOUR_VOID, (size_t)columns * CHUNKY_STRIDE);
}

void render_frame(const GameState *state, RenderScratch *scratch, uint8_t *chunky)
{
    uint16_t columns = render_columns(state)->count;

    render_clear(chunky, columns);
    render_cast(state, scratch);
    render_draw_columns(scratch, columns, chunky);
    sprite_build_list(state, &scratch->sprites);
    sprite_draw(&scratch->sprites, scratch->wall_dist, columns, chunky);
}
