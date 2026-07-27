/* dash_const.h — the dashboard graphic's geometry, in ONE place, plus the two entry points its TWO
 * routes share: the C reference (src/hud.c's rm_hud_dashboard over cell_dashboard, include/plane.h) and
 * the STE hardware-blitter route (src/blitter_dash.c). The scroll_const.h / blit_const.h precedent.
 *
 * Before this header these numbers were scattered across four files: DASHBOARD_DST as a src/hud.c
 * literal, DASH_ROWS / DASH_GROUPS in BOTH include/plane.h and src/events.c (events.c does not include
 * plane.h, so they were genuine independent copies), the arena row stride only in src/events.c, and the
 * arena offset in src/events.c and src/results.c. The blitter route depends on all of them AGREEING, so
 * they collapse here — same names, same values.
 *
 * ONE spelling is deliberately left outside: ARENA_DASH_SRC_OFF, which test/adapter.py bakes into
 * game_fixture.h. It cannot be shared across the Python/C boundary, so render/atari/game_main.c pins it
 * equal to RM_DASH_SRC_OFF with a static assert instead (CLAUDE.md §5).
 */
#ifndef RM_DASH_CONST_H
#define RM_DASH_CONST_H

#include <stdint.h>

#include "screen.h"

#define RM_DASH_SRC_OFF    0x11c20   /* the dashboard graphic's home within the gfx arena (buf_c) */
#define DASHBOARD_DST      0x280      /* draw-buffer offset of the HUD's phase-7 dashboard composite */
#define DASH_ROWS          40         /* scanlines of dashboard art */
#define DASH_GROUPS        8          /* groups of four dest words (0x40 bytes) per row */
#define DASH_GROUP_BYTES   8          /* one group = one 16-px 4-plane cell = 4 words */
#define ARENA_ROW_STRIDE   0xa0       /* one scanline in the graphics arena */
/* The bytes of each scanline that ARE dashboard art. The rest of the arena row belongs to neighbouring
 * graphics: nothing here reads it, so nothing here should copy or hash it either. */
#define DASH_ROW_BYTES     (DASH_GROUPS * DASH_GROUP_BYTES)

/* THE fact the blitter route is built on: the arena's row pitch equals the framebuffer's, so the chip
 * can read the live art IN PLACE with src_y_inc == dst_y_inc and no materialised stream. If they ever
 * diverged the route would need two pitches (and this header's users would need to say which one they
 * mean), so pin them equal rather than letting the coincidence go unremarked. */
typedef char rm_dash_arena_stride_is_screen_stride[(ARENA_ROW_STRIDE == SCREEN_ROW_BYTES) ? 1 : -1];

/* One group = one word per plane, which is what makes "plane p's column" a fixed +2p byte offset and
 * lets each blitter pass walk one plane with a DASH_GROUP_BYTES x-step. */
typedef char rm_dash_group_is_one_word_per_plane[(DASH_GROUP_BYTES == SCREEN_PLANES * 2) ? 1 : -1];

/* The blitter route's per-row correction: after DASH_GROUPS-1 x-steps of DASH_GROUP_BYTES the walk has
 * covered all but the last group of a row, so this lands it on the next row's first group. It is the
 * SAME number for the source and the destination — see the stride assert above. */
#define DASH_BLIT_Y_INC   (ARENA_ROW_STRIDE - (DASH_GROUPS - 1) * DASH_GROUP_BYTES)

/* The C reference: composite the dashboard art at `gfx` over the framebuffer `px` at DASHBOARD_DST
 * (src/hud.c — cell_dashboard with this route's fixed geometry). The blitter route falls back to THIS
 * function, so both routes' pixels come from one body. */
void rm_hud_dashboard(uint8_t *px, const uint8_t *gfx);

/* ---- the STE hardware-blitter route (src/blitter_dash.c) -----------------------------------------
 * Declared next to the geometry it consumes (include/blitter.h carries only the bind, which needs
 * none of it). DEFINED only by the m68k blitter build — the host .so links src/hud.c alone and never
 * names them. */
void rm_blit_hud_dashboard_draw(uint8_t *px, const uint8_t *gfx);       /* supervisor half */
void rm_blit_hud_dashboard_dispatch(uint8_t *px, const uint8_t *gfx);   /* + one Supexec */
/* The boot-bound seam src/hud.c calls: the blitter dispatch on a blitter machine, rm_hud_dashboard (the
 * C reference) otherwise. ONE declaration so the pointer type cannot drift from its definition. */
extern void (*rm_blit_hud_dashboard_fn)(uint8_t *, const uint8_t *);

#endif /* RM_DASH_CONST_H */
