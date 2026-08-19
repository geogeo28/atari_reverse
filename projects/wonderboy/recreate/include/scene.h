/* scene.h — the SCENE tier: what runs once a frame while the game is inside a scripted room
 * (src/scene.c). $dbc0 is the driver, $de80 the visit budget it spends.
 *
 * game_main_loop's `$66e == 0` block calls `$dbc0` between panel_refresh_frame and `$882`. It does
 * nothing at all unless one of the two mode flags is negative, and which one selects which half of
 * the routine: WB_STATE_FLAG_A30 reaches the two arms driven by the SCENE DESCRIPTOR the pointer
 * WB_RECORD_PTR_10420 holds (kind 1 = a speech script, kind 2 = the shop counter), and
 * WB_STATE_FLAG_A32 the one arm kind 4 selects (the eight fragments a defeated boss leaves).
 *
 * ONE BOUNDARY IS LEFT, and it is no longer the one this header was written for. `$dfbe` — the exit
 * that four of $dbc0's arms take — is RECONSTRUCTED (batch 27): its dispatch table's eight entries
 * are all ported code, and `stage_load_window` below it has run whole since batch 26. So those four
 * arms now RUN their tail and the routine leaves through the original's own `rts`. `$1ab4`, which
 * $de80 tail-jumps to when the exhausted visit's marker cell matches neither neighbour, is still not
 * reconstructed; a case that expects it runs the original with the kit's `stop_pc` set to that
 * address, which diffs the whole prefix at the instant control arrives there.
 *
 * EITHER WAY THESE FUNCTIONS REPORT WHICH EXIT THEY TOOK, because the report is what a case names
 * its expectation with: WB_SCENE_EXIT_RELOAD now means "it RAN $dfbe" rather than "it declined to",
 * and every such case still requires the oracle's executed-PC coverage to hold the transfer
 * instruction it expects to leave through. ../STATUS.md records what the remaining arm leaves
 * unpinned.
 */
#ifndef WONDERBOY_SCENE_H
#define WONDERBOY_SCENE_H

#include <stdint.h>

/* The exit a scene function reports, in place of the transfer the original makes. C-only — no
 * value here is in the image — but test/layout.py scrapes this header so that a case names the
 * same three exits the C does. */
#define WB_SCENE_EXIT_RETURN       0u  /* the original `rts`d without leaving the scene */
#define WB_SCENE_EXIT_RELOAD       1u  /* it went through $dfbe (scene_exit_and_reload), which runs */
#define WB_SCENE_EXIT_STAGE_RESET  2u  /* ...or to $1ab4, which $de80 tail-jumps to. THE TAIL ITSELF
                                        * IS PORTED (batch 41 phase B: it is the speech arm's last
                                        * twenty-eight instructions, `scene_spawn_speech_tail`).
                                        * What is still open is this CALLER's side of it: $deb0
                                        * arrives having pushed nothing, so the tail's
                                        * `movea.l (a7)+,a0` pops $de80's own return address and
                                        * the `rts` returns one frame further out — a one-level
                                        * unwind, not a boundary in the tail */
#define WB_SCENE_EXIT_WILD_RETURN  4u  /* ...or reached the `rts` at $19e0, which is NOT a return:
                                        * `scene_spawn_from_script` pushes a0 at its first
                                        * instruction and only its THREE ARMS pop it again, so a
                                        * descriptor whose kind is not 1, 2 or 4 returns THROUGH
                                        * THAT SAVED a0 and leaves its real return address on the
                                        * stack. An ORIGINAL DEFECT, found by the oracle running
                                        * away when this battery first drove an unnamed kind */
#define WB_SCENE_EXIT_ILLEGAL      3u  /* ...or reached the `illegal` at $1d8e, which is the
                                        * ORIGINAL's own ending and not a boundary of this port:
                                        * a fourth refusal at one shop counter executes $4afc and
                                        * takes an illegal-instruction exception. See
                                        * `scene_spawn_from_script` below */

/* $dbc0 — the once-a-frame scene driver. Takes no argument (it reads its mode flags and its
 * descriptor pointer out of memory) and, in the original, returns nothing. */
uint32_t scene_run_frame(uint8_t *image);

/* $de80 — `sub.w d0,32(a1)`: spend `amount` off the shop record's visit budget, and on the
 * borrow, close the visit. `record` is the original's a1 and `amount` its d0; only d0's low word
 * is read, which is why the argument is the whole longword and the truncation happens here. */
uint32_t scene_spend_visit_budget(uint8_t *image, uint32_t record, uint32_t amount);

/* $1b46 — CLEAR A MARKER CELL AND ITS TWIN, and the whole routine is six instructions: the byte at
 * `cell` is read and cleared, then compared against the cell to its RIGHT and, failing that, the one
 * to its LEFT; whichever holds the same code is cleared too. `cell` is the original's a6, which both
 * callers load from WB_SCENE_MARKER_CELL_PTR.
 *
 * THE RETURN VALUE IS WHETHER A NEIGHBOUR MATCHED, and it exists because THIS LOGIC IS IN THE IMAGE
 * TWICE. $de94, inside `scene_spend_visit_budget` above, is the same six instructions spelt inline —
 * and the ONLY difference between the two originals is what happens when neither neighbour matches:
 * $1b46 simply `rts`s where $de94 takes `jmp $1ab4.w`, the tail this file does not follow. So one
 * body serves both, and the flag is what lets the caller choose its own ending.
 *
 * RENAMED FROM `speech_script_step`, WHICH WAS WRONG twice over: the routine steps no script (it
 * writes collision-map cells, and the speech cursor is stepped by the `addq.l #1,$1017c.l` two
 * instructions above its call site), and the plate's register was a5 where the opcode word $1016 is
 * `move.b (a6),d0`. WHY IT IS IN THIS FILE and not src/player.c with the rest of the $19ac tree:
 * its twin is here, and a second copy of six instructions is the one divergence nothing catches. */
int scene_clear_marker_pair(uint8_t *image, uint32_t cell);

/* $dfbe — LEAVE THE SCENE AND RELOAD THE STAGE, the tail four of $dbc0's arms take. It runs the
 * descriptor's own exit action out of WB_SCENE_EXIT_ACTION_TABLE, takes the message box down, hands
 * stage_load_window the level map, WB_TILE_BITMAPS and the WB_STAGE_START_TABLE entry the descriptor
 * names, and clears the four state words the scene ran under. Takes no register argument — the
 * descriptor comes from WB_RECORD_PTR_10420 and the other two pointers are `lea` literals. */
void scene_exit_and_reload(uint8_t *image);

/* $101bc and $101be — entries 0 and 1 of WB_SCENE_EXIT_ACTION_TABLE. Entries 2..7 are effects.h's
 * six `set_state_*` stubs, so the whole table is reconstructed and the dispatch above needs no
 * boundary. Exported because test/test_scene.py enters each of them directly. */
void scene_exit_action_none(uint8_t *image);
void scene_exit_action_select_a30_table(uint8_t *image);


/* --- $19ac: THE SCENE-SPAWN TREE ----------------------------------------------------------------
 *
 * What ENTERS a scene, where everything above runs one once a frame. Its one caller in the image is
 * the `bsr.w $19ac` at $c66 inside player_pending_event_gate. It takes no register argument — the
 * descriptor comes from WB_RECORD_PTR_10420 and the collision-map cell from
 * WB_SCENE_MARKER_CELL_PTR — and it reads the descriptor as a byte-coded SCRIPT rather than as a
 * record of named fields, which is why src/scene.c walks a cursor over it.
 *
 * IT RUNS WHOLE, on all three arms: every callee is reconstructed (actor_table_reset,
 * map_stamp_block, scene_clear_marker_pair above, the three gates below and stage_load_window), so
 * a differential enters at $19ac and leaves at the original's own `rts`. The ONE exception is not
 * this port's boundary but the ORIGINAL's ending: WB_SCENE_EXIT_ILLEGAL. */
uint32_t scene_spawn_from_script(uint8_t *image);

/* $e43e, $e456, $e46c — the three live entries of WB_SPAWN_GATE_TABLE, the FOURTH dispatch table in
 * the program and the third this project has closed. Each returns having written nothing when
 * WB_HUD_SLOT_BBC8's high byte is its own number, and otherwise OVERWRITES THE SCRIPT: `cursor` is
 * the original's a1, the descriptor byte the caller reads one instruction later, and the word after
 * it is the descriptor's own WB_SCENE_EXIT_ACTION. Exported because test/test_scene.py enters each
 * of them directly as well as through the dispatch. */
void spawn_gate_unless_bbc8_eq1(uint8_t *image, uint32_t cursor);
void spawn_gate_unless_bbc8_eq3(uint8_t *image, uint32_t cursor);
void spawn_gate_unless_bbc8_eq4(uint8_t *image, uint32_t cursor);

/* $1cc0 — the shop's PRICE PLATES: four digits of the price at `price_field` (d6, a displacement
 * into WB_SHOP_RECORD_PTR's record) drawn into the sprite `resource` (d7) names. */
void shop_render_price_digits(uint8_t *image, uint16_t resource, uint16_t price_field);

/* $1d1e — one 8-pixel glyph column of `glyph` (a1) into the masked sprite bitmap at `at` (a0), and
 * the cursor for the NEXT column, which is the original's own a0: one byte on from an EVEN cursor
 * and nine from an odd one. */
uint32_t glyph_stamp_8_rows(uint8_t *image, uint32_t at, uint32_t glyph);

#endif /* WONDERBOY_SCENE_H */
