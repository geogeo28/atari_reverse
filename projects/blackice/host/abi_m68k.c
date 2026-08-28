/*
 * abi_m68k.c - the 68000 record layouts, asserted by the cross compiler itself.
 *
 * render.h and sprite.h publish byte offsets that the hand-written 68000 asm
 * indexes with.  Everything else in the project checks those offsets on the
 * HOST, where a pointer is eight bytes and the numbers are extrapolated; this
 * translation unit is compiled only by `make m68k`, so the compiler that will
 * actually build the target is the one making the claim.
 *
 * Asserts only.  It emits no code and defines no symbol - if it ever needs to,
 * that is a sign the layout moved and the asm has to move with it.
 */
#include <stddef.h>

#include "render.h"
#include "sprite.h"

#define ASSERT_LAYOUT(condition, name) \
    typedef char blackice_abi_##name[(condition) ? 1 : -1]

/* ---- RenderColumn: 12 bytes, every 16-bit field on an even offset -------- */

ASSERT_LAYOUT(sizeof(RenderColumn) == RENDER_COLUMN_BYTES,       column_size);
ASSERT_LAYOUT(offsetof(RenderColumn, tex_id)   ==  0,            column_tex_id);
ASSERT_LAYOUT(offsetof(RenderColumn, tex_col)  ==  1,            column_tex_col);
ASSERT_LAYOUT(offsetof(RenderColumn, top)      ==  2,            column_top);
ASSERT_LAYOUT(offsetof(RenderColumn, rows)     ==  4,            column_rows);
ASSERT_LAYOUT(offsetof(RenderColumn, tex_v)    ==  6,            column_tex_v);
ASSERT_LAYOUT(offsetof(RenderColumn, tex_step) ==  8,            column_tex_step);
ASSERT_LAYOUT(offsetof(RenderColumn, band)     == 10,            column_band);
ASSERT_LAYOUT(offsetof(RenderColumn, side)     == 11,            column_side);

/* ---- RenderSprite: 26 bytes, with 4-byte pointers on the target ---------- */

ASSERT_LAYOUT(sizeof(void *) == 4,                               target_pointer_size);
ASSERT_LAYOUT(sizeof(RenderSprite) == RENDER_SPRITE_BYTES_68K,   sprite_size);
ASSERT_LAYOUT(offsetof(RenderSprite, texels)     ==  0,          sprite_texels);
ASSERT_LAYOUT(offsetof(RenderSprite, spans)      ==  4,          sprite_spans);
ASSERT_LAYOUT(offsetof(RenderSprite, left)       ==  8,          sprite_left);
ASSERT_LAYOUT(offsetof(RenderSprite, cols)       == 10,          sprite_cols);
ASSERT_LAYOUT(offsetof(RenderSprite, top)        == 12,          sprite_top);
ASSERT_LAYOUT(offsetof(RenderSprite, rows)       == 14,          sprite_rows);
ASSERT_LAYOUT(offsetof(RenderSprite, tex_u)      == 16,          sprite_tex_u);
ASSERT_LAYOUT(offsetof(RenderSprite, tex_step_u) == 18,          sprite_tex_step_u);
ASSERT_LAYOUT(offsetof(RenderSprite, tex_step_v) == 20,          sprite_tex_step_v);
ASSERT_LAYOUT(offsetof(RenderSprite, dist)       == 22,          sprite_dist);
ASSERT_LAYOUT(offsetof(RenderSprite, band)       == 24,          sprite_band);
ASSERT_LAYOUT(offsetof(RenderSprite, pad)        == 25,          sprite_pad);
