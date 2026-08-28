/*
 * sprite.h - billboard sprites: projection, drop budget and the list the
 *            68000 asm consumes.
 *
 * A sprite is 64x64 bytes of palette index, COLUMN MAJOR like a wall texture
 * (texel (u, v) at u * 64 + v), with SPRITE_TRANSPARENT as the colour key.
 * Alongside it is a per-column span table giving the first and last opaque
 * texel row of that column, which hoists the leading and trailing transparent
 * runs out of the inner loop entirely - the only reason a per-pixel
 * transparency test is affordable at all.
 */
#ifndef BLACKICE_SPRITE_H
#define BLACKICE_SPRITE_H

#include <stdint.h>
#include "fixed.h"
#include "game_consts.h"
#include "game.h"

/* A column with no opaque texel is encoded first > last; the pipeline writes
 * the canonical empty pair (0xFF, 0x00). */
typedef struct {
    uint8_t first;
    uint8_t last;
} SpriteSpan;

#define SPRITE_SPAN_EMPTY_FIRST 0xFF
#define SPRITE_SPAN_EMPTY_LAST 0x00
#define SPRITE_SPAN_IS_EMPTY(s) ((s).first > (s).last)

typedef struct {
    const uint8_t    *texels;   /* TEX_SIZE bytes, column major */
    const SpriteSpan *spans;    /* TEX_DIM entries */
} SpriteAsset;

/* Sprite asset each entity type is drawn with; NULL means "not drawn". */
extern const SpriteAsset *g_entity_sprites[ENT_TYPE_COUNT];

/*
 * One visible billboard, fully projected and clipped.
 *
 * 68000 layout, RENDER_SPRITE_BYTES_68K = 26 bytes (pointers are 4 bytes there;
 * the host build is wider,
 * which is why the asm must use these documented offsets and not sizeof):
 *    +0  texels      ptr  64x64 column-major texels
 *    +4  spans       ptr  TEX_DIM SpriteSpan pairs
 *    +8  left        i16  first screen column to draw, already clipped to 0
 *   +10  cols        u16  screen columns to draw
 *   +12  top         i16  screen row of the sprite's top edge; MAY BE NEGATIVE
 *   +14  rows        u16  full projected height in rows, before row clipping
 *   +16  tex_u       u16  texel u at column `left`, 8.8 fixed
 *   +18  tex_step_u  u16  texel u added per screen column, 8.8 fixed
 *   +20  tex_step_v  u16  texel v added per screen row, 8.8 fixed
 *   +22  dist        u16  perpendicular distance in map units, for the z test
 *   +24  band        u8   depth band, the shade LUT row is g_shade_lut[band]
 *   +25  pad         u8
 *
 * `top` is deliberately left unclipped: the drawer needs it to map a span's
 * texel rows onto screen rows, and clipping happens per column after that.
 */
typedef struct {
    const uint8_t    *texels;
    const SpriteSpan *spans;
    int16_t  left;
    uint16_t cols;
    int16_t  top;
    uint16_t rows;
    uint16_t tex_u;
    uint16_t tex_step_u;
    uint16_t tex_step_v;
    uint16_t dist;
    uint8_t  band;
    uint8_t  pad;
} RenderSprite;

#define RENDER_SPRITE_BYTES_68K 26

typedef struct {
    RenderSprite entries[SPRITE_MAX_VISIBLE];
    uint16_t     count;         /* sorted far to near: draw in list order */
} SpriteList;

/*
 * Project every live entity into a far-to-near list, then spend the per-frame
 * pixel budget on it.
 *
 * DESIGN 8.2 asks that the nearest ATTACKER never be dropped - "the closest
 * entity in ATTACK, or if none is attacking, the closest entity" - and TWO caps
 * could drop one: SPRITE_MAX_VISIBLE, which is applied by inserting in distance
 * order and evicting the farthest, and the pixel budget, which is spent from
 * the near end.  Both cut from the far end only, and the exempt sprite is
 * additionally kept whatever the budget says and charged nothing for it, which
 * is what makes the worst case a window-filling sprite PLUS the budget.
 */
void sprite_build_list(const GameState *state, SpriteList *list);

/*
 * DESIGN 8.2's cost function: the chunky pixels this billboard would actually
 * write, AFTER its projected rectangle is clipped to the render window.  `cols`
 * arrives already column-clipped; `rows` is the full projected height, because
 * the drawer needs it to map texel rows onto screen rows, so the row clip lives
 * here.  Published rather than static because it is the rule the whole budget
 * rests on: a sprite 191 rows tall in an 80-row window costs 80.
 */
int32_t sprite_pixel_cost(const RenderSprite *sprite);

/*
 * Draw the list into the chunky buffer, column-clipped against `wall_dist`
 * (RENDER_W_MAX entries of perpendicular distance in map units).
 */
void sprite_draw(const SpriteList *list, const uint16_t *wall_dist,
                 uint16_t columns, uint8_t *chunky);

#endif /* BLACKICE_SPRITE_H */
