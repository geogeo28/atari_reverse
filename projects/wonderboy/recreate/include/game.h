/* game.h — THE SPINE: the routines the frame loop itself is made of (src/game.c).
 *
 * Everything else in this reconstruction runs because a differential entered it. Nothing here does:
 * `game_main_loop` ($4a0) is an unconditional `do { ... } while(1)` and these are the routines it
 * calls directly, which is why they were the last part of the program to be ported rather than the
 * first. ../STATUS.md's batch 42 phase A carries the whole inventory of what the loop reaches.
 *
 * TWO OF THEM BUSY-WAIT, and that is the reason this module could not exist before the kit's
 * scheduled-write model (tools/recreate_kit/TRAP_MODEL.md, "Phase 8"). `game_unpause_on_key_release`
 * spins on WB_KEY_LAST_SCANCODE until the IKBD ACIA interrupt stores the pause key's RELEASE code,
 * and `game_key_actions` does the same for Help's. No instruction in either routine writes that
 * byte, so off target the loop is infinite on both sides of the differential — the case declares the
 * store, and the reconstruction reads the byte through `sched_poll8` once per iteration. On target
 * `sched_poll8` is not compiled and the wait is a plain re-read: the interrupt really does store it.
 *
 * THREE OF game_key_actions' ENDINGS ARE NOT RETURNS. They pop game_main_loop's return address off
 * the stack and `jmp` into the boot chain — the loop is left, not returned from — so the function
 * reports WHICH ending it reached in place of the transfer, and a case sets the kit's `stop_pc` to
 * that `jmp` and requires the oracle's executed-PC coverage to hold the arm's own instruction
 * (the same arrangement scene.h describes).
 */
#ifndef WONDERBOY_GAME_H
#define WONDERBOY_GAME_H

#include <stdint.h>

/* Which of game_key_actions' four endings it reached. C-only — no value here is in the image — but
 * test/layout.py scrapes this header, so a case names the same four the C does.
 *
 * The two UNWIND codes are distinct although both arms `jmp $e5ba`: they are reached on different
 * conditions and clear different state, and one code for the pair would let a port that took the
 * wrong one report the right answer. */
#define WB_KEY_ACTIONS_RETURNED    0u  /* the original `rts`d: no action, or one that stays in the frame */
#define WB_KEY_ACTIONS_ROUND_END   1u  /* $54e/$550: WB_ROUND_END_RELOAD_REQUEST was up, so the round
                                        * is over — unwound out of the frame loop into $e5ba */
#define WB_KEY_ACTIONS_LEVEL_SKIP  2u  /* $56c/$56e: the cheat is enabled and N is held — the same
                                        * tail, reached without clearing the request word */
#define WB_KEY_ACTIONS_QUIT        3u  /* $58c..$598: ESC — start the music fade, then unwind into
                                        * the data-disk prompt at $e494 */

/* $53e — game_main_loop's SECOND leading `bsr`, and the game's whole keyboard. It turns the last
 * IKBD scancode into one of five actions (pause, quit, level skip, the cheat sequence's next step,
 * the cheat's Help toggle) and, before any of them, consumes the round-end reload request.
 *
 * Returns one of the WB_KEY_ACTIONS_* above. Takes no argument: every input is a byte or word in
 * the image. */
uint32_t game_key_actions(uint8_t *image);

/* $638 — game_main_loop's FIRST leading `bsr`. Does nothing unless the game is paused AND the pause
 * key is still held; then it waits for the release and lifts the pause.
 *
 * The wait is the routine's whole reason for being a boundary until now: `cmpi.b #$99,$879.l /
 * bne.s` spins on a byte the ACIA handler writes. */
void game_unpause_on_key_release(uint8_t *image);

#endif /* WONDERBOY_GAME_H */
