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
#define WB_SCENE_EXIT_STAGE_RESET  2u  /* ...or to $1ab4, which $de80 tail-jumps to — NOT ported */

/* $dbc0 — the once-a-frame scene driver. Takes no argument (it reads its mode flags and its
 * descriptor pointer out of memory) and, in the original, returns nothing. */
uint32_t scene_run_frame(uint8_t *image);

/* $de80 — `sub.w d0,32(a1)`: spend `amount` off the shop record's visit budget, and on the
 * borrow, close the visit. `record` is the original's a1 and `amount` its d0; only d0's low word
 * is read, which is why the argument is the whole longword and the truncation happens here. */
uint32_t scene_spend_visit_budget(uint8_t *image, uint32_t record, uint32_t amount);

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

#endif /* WONDERBOY_SCENE_H */
