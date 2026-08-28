/*
 * abi.c - struct sizes and offsets, exported for the test harness.
 *
 * The pytest suite drives the engine through ctypes, which means it holds its
 * own picture of every struct layout.  These accessors let the tests assert
 * that picture against the compiler's instead of assuming it, so a field added
 * to GameState fails a test rather than silently corrupting one.
 *
 * Host-only: nothing in src/ references it.
 */
#include <stddef.h>

#include "game.h"
#include "render.h"
#include "sprite.h"

size_t bi_sizeof_level(void)         { return sizeof(Level); }
size_t bi_sizeof_gamestate(void)     { return sizeof(GameState); }
size_t bi_sizeof_rendercolumn(void)  { return sizeof(RenderColumn); }
size_t bi_sizeof_renderscratch(void) { return sizeof(RenderScratch); }
size_t bi_sizeof_rendersprite(void)  { return sizeof(RenderSprite); }
size_t bi_sizeof_spritelist(void)    { return sizeof(SpriteList); }
size_t bi_sizeof_door(void)          { return sizeof(Door); }

size_t bi_offset_state_player(void)  { return offsetof(GameState, player); }
size_t bi_offset_state_doors(void)   { return offsetof(GameState, doors); }
size_t bi_offset_state_trace(void)   { return offsetof(GameState, trace_milli); }
/* Where the engine half of GameState ends and the game layer begins.  The
 * ctypes mirror only models the engine half, so this - not sizeof - is what
 * pins it. */
size_t bi_offset_state_gamelayer(void) { return offsetof(GameState, entities); }
/* Three probes into the game layer's own fields, so the suite's mirror of it
 * is pinned in the middle and not only at its start. */
size_t bi_offset_state_nav(void)       { return offsetof(GameState, nav); }
size_t bi_offset_state_events(void)    { return offsetof(GameState, events); }
size_t bi_offset_state_integrity(void) { return offsetof(GameState, integrity); }
size_t bi_offset_scratch_dist(void)  { return offsetof(RenderScratch, wall_dist); }
size_t bi_offset_scratch_sprites(void) { return offsetof(RenderScratch, sprites); }
size_t bi_offset_level_cells(void)   { return offsetof(Level, cells); }
