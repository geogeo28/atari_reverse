/* scene.h — the SCENE tier: what runs once a frame while the game is inside a scripted room
 * (src/scene.c). $dbc0 is the driver, $de80 the visit budget it spends.
 *
 * game_main_loop's `$66e == 0` block calls `$dbc0` between panel_refresh_frame and `$882`. It does
 * nothing at all unless one of the two mode flags is negative, and which one selects which half of
 * the routine: WB_STATE_FLAG_A30 reaches the two arms driven by the SCENE DESCRIPTOR the pointer
 * WB_RECORD_PTR_10420 holds (kind 1 = a speech script, kind 2 = the shop counter), and
 * WB_STATE_FLAG_A32 the one arm kind 4 selects (the eight fragments a defeated boss leaves).
 *
 * THE RECONSTRUCTION STOPS AT A BOUNDARY, and the boundary is this header's whole reason for
 * existing. Four of $dbc0's exits transfer to `$dfbe` and one of $de80's to `$1ab4`; BOTH of those
 * routines end in `jsr stage_load_window` ($f95c), which this project cannot verify — it sets the
 * palette through a shifter write the oracle silently drops (a write off the mapped image is a
 * no-op there, so a reconstruction that skipped it would come back GREEN) and then calls into the
 * sound module's PSG side. So neither is reconstructed, and instead of calling them these
 * functions RETURN WHICH TAIL THEY REACHED. A case runs the original with the kit's `stop_pc`
 * checkpoint set to that tail's address, which diffs the whole prefix at the instant control
 * arrives there; ../STATUS.md records the arms this leaves unpinned.
 */
#ifndef WONDERBOY_SCENE_H
#define WONDERBOY_SCENE_H

#include <stdint.h>

/* The exit a scene function reports, in place of the transfer the original makes. C-only — no
 * value here is in the image — but test/layout.py scrapes this header so that a case names the
 * same three exits the C does. */
#define WB_SCENE_EXIT_RETURN       0u  /* the original `rts`d */
#define WB_SCENE_EXIT_RELOAD       1u  /* it transferred to $dfbe (scene_exit_and_reload) */
#define WB_SCENE_EXIT_STAGE_RESET  2u  /* ...or to $1ab4, which $de80 tail-jumps to */

/* $dbc0 — the once-a-frame scene driver. Takes no argument (it reads its mode flags and its
 * descriptor pointer out of memory) and, in the original, returns nothing. */
uint32_t scene_run_frame(uint8_t *image);

/* $de80 — `sub.w d0,32(a1)`: spend `amount` off the shop record's visit budget, and on the
 * borrow, close the visit. `record` is the original's a1 and `amount` its d0; only d0's low word
 * is read, which is why the argument is the whole longword and the truncation happens here. */
uint32_t scene_spend_visit_budget(uint8_t *image, uint32_t record, uint32_t amount);

#endif /* WONDERBOY_SCENE_H */
