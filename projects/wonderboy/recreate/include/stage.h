/* stage.h — the stage loader (src/stage.c): what runs ONCE when a stage is entered, as against the
 * background-scroll engine in scroll.h, which runs once a FRAME.
 *
 * The three routines at $fa30/$fb06/$fd46 are the initial fill of the eight pre-shifted buffers the
 * scroll engine then maintains: draw the map into copy 0, publish the scroll state, derive the other
 * seven copies. $f95c calls them back to back and is not reconstructed (it sets the palette through
 * the shifter and calls the sound module). $fed2 resets the state they run on, $fe1e relocates a
 * table loaded past the program, and $e110's pair plots a banner into copy 0 out of a second font.
 *
 * WHAT THE NAMES CLAIM. `bg_build_buffer` says the map's tiles are drawn into WB_BG_BUFFER_BASE at
 * WB_BG_BUFFER_LINE bytes a scanline; that the result is "the visible window" follows from the
 * eleven-by-sixteen geometry matching WB_BG_BUFFER_TILE_ROWS and WB_BG_ROW_CELLS, not from anything
 * this file proves. `stage_reset_state` says WHICH addresses are cleared; what most of them hold is
 * established in ../names.txt or nowhere.
 *
 * Every ADDRESS these touch is a global in wonderboy.h, which both languages read.
 */
#ifndef WONDERBOY_STAGE_H
#define WONDERBOY_STAGE_H

#include <stdint.h>

/* $fa30 — draw the map's visible window into pre-shifted copy 0.
 *
 * The three entry REGISTERS are arguments: `map` (a0) is the level's map, header and all; `start`
 * (a1) points at the two words naming the top-left map cell; `tiles` (a6) is the tile bank each
 * cell's 128-byte bitmap is taken from. The bank is also what WB_STAGE_RAW_TILE_INDEX is about —
 * see the comment on the index lookup in the body. */
void bg_build_buffer(uint8_t *image, uint32_t map, uint32_t start, uint32_t tiles);

/* $fb06 — publish the stage's scroll state: the two limits out of the map header, the map cursor
 * and position words out of the start record, the ring cursors zeroed, and the sixteen buffer row
 * pointers loaded. Takes no register argument: both pointers come from WB_STAGE_MAP_PTR /
 * WB_STAGE_START_PTR, which $f95c latched. */
void stage_publish_scroll_state(uint8_t *image);

/* $fd46 — derive pre-shifted copies 1..7 from copy 0, WB_BG_PRESHIFT_BITS at a time. Each 128-byte
 * scanline closes as a RING: the first cell's shifted-out bits are held in WB_BG_BUILD_CARRY and
 * ORed into the last. Takes no register argument — both buffer addresses are `lea`d. */
void bg_build_preshifted_copies(uint8_t *image);

/* $fe1e — turn each record's leading offset into an absolute pointer, ONCE. Guarded by a signature
 * byte, because the conversion is in place and is not idempotent. */
void resource_table_relocate(uint8_t *image);

/* $fed2 — clear the per-stage state block and re-seed the eight WB_TILE_INDEX_TAIL entries. */
void stage_reset_state(uint8_t *image);

/* $e16a — plot one 8x8 glyph of WB_BG_BANNER_FONT into the background buffer and return the cursor
 * for the NEXT 8-pixel cell, which is one byte on from an even cursor and seven from an odd one.
 * `glyph` is a0 and `cursor` a1; the advanced cursor is the result, exactly as the original's a1. */
uint32_t bg_plot_banner_glyph(uint8_t *image, uint32_t glyph, uint32_t cursor);

/* $e140 — plot the whole banner record `record` (a6) names: a word of buffer offset, then characters
 * until one with WB_BG_BANNER_END's bit set. Returns the original's a6, which points AT the
 * terminator: the loop ends on `tst.b (a6) / bpl`, which reads that byte without consuming it. */
uint32_t bg_plot_banner(uint8_t *image, uint32_t record);

/* $e110 — the round banner, plus the perfect-bonus one and its score when the meter is full. */
void bg_plot_round_banner(uint8_t *image);

/* $fe4a — the NEW-GAME reset: WB_LEVEL_SEQ_INDEX cleared, WB_LIVES set to WB_LIVES_ON_RESTART, the
 * effect record list emptied and the six HUD slots cleared, and then the tail below, which it falls
 * through into. One `bsr` caller ($e59e). */
void game_restart_reset(uint8_t *image);

/* $fe8c — the tail both entrants run: redraw the lives, reseed the meter, clear the score and the
 * small state words, reset WB_STAGE_TUNE_LATCH and point WB_EFFECT_RECORD_WRITE_PTR back at the
 * list's base. Its own caller is the `jsr $fe8c.l` at $c00, on the path that has just decremented
 * WB_LIVES — which is why Ghidra's single 136-byte function at $fe4a is two routines here. */
void game_life_restart_reset(uint8_t *image);

/* $f944 — the WB_PALETTE_COLOURS words at `source` (a0) into the shifter's colour registers, and the
 * cursor past them (the original's a0, which its eight `move.l (a0)+,(a1)+` leave at source + 32).
 *
 * WHAT IT DOES IS NOT PINNED BY ANYTHING. WB_SHIFTER_PALETTE lies outside the memory image, so the
 * oracle DROPS all sixteen writes — the kit models hardware READS and has no ledger for a write
 * (tools/recreate_kit/include/hw.h) — and this routine touches no image byte at all. A case can
 * therefore show that both sides write NOTHING and that the source cursor comes back where the
 * original leaves it, and that is the whole of the surface: which words went to which colour
 * register, and that they went anywhere, is UNTESTED here and stated as such in src/stage.c.
 *
 * Reached from $f95c (the stage's own palette) and from three sites in the boot prompt at $e494. */
uint32_t set_palette(uint8_t *image, uint32_t source);

/* $e7f4 — the same sixteen registers written with zero, and the same untested claim. Two call sites,
 * both in the boot: $e494's prompt and $e4ea's continuation. Returns the cursor the original leaves
 * a0 at, which no caller reads. */
uint32_t clear_palette(uint8_t *image);

/* $f95c — THE STAGE-TRANSITION HINGE: every stage entry in the game goes through it.
 *
 * The three entry REGISTERS are its arguments, and all six call sites load all three: `map` (a0) is
 * the level map, `start` (a1) the WB_START_RECORD_LEN-byte start record, `tiles` (a6) the tile bank.
 * It latches map and start into WB_STAGE_MAP_PTR / WB_STAGE_START_PTR, raises or clears
 * WB_STAGE_RAW_TILE_INDEX according to whether the bank IS WB_TILE_BITMAPS, copies the start
 * record's position into the followed actor's record, runs the three builders above back to back,
 * computes WB_SCROLL_FOLLOW_X/_Y unless the scroll is frozen, sets the palette, and then either
 * starts a song or stops the module.
 *
 * IT RUNS WHOLE. Every callee is reconstructed — the three builders (batch 12), `set_palette` and
 * the sound module's `snd_play_song` / `snd_stop` (batch 26) — so a differential enters at $f95c and
 * leaves at its own `rts` with no boundary. What it inherits is `set_palette`'s untested claim above
 * and nothing else. */
void stage_load_window(uint8_t *image, uint32_t map, uint32_t start, uint32_t tiles);

#endif /* WONDERBOY_STAGE_H */
