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

#include "blit.h"      /* sprite_pass_regs — game_main_loop's one argument */

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

/* ...AND THE LOOP'S OTHER TWO WAYS OUT, WHICH ARE NOT game_key_actions'. `game_main_loop` returns
 * one number for all of them, so these continue the block above rather than starting a space of
 * their own — one iteration has one ending, and a caller that had to consult two fields to learn
 * which could get them out of step.
 *
 * THE CENSUS IS THE IMAGE'S, and it is what says two more codes are needed and not one. The shipped
 * bytes hold THREE `jmp $e494.l` and FOUR `jmp $e5ba.l`, and only three of the seven are
 * game_key_actions':
 *
 *   $e494   $598  game_key_actions' ESC arm         -> WB_KEY_ACTIONS_QUIT
 *           $bdc  player_pending_event_gate's game-over box expiry (player.h,
 *                 WB_PLAYER_GATE_DATADISK_UNWIND)   -> WB_LOOP_EXIT_DATA_DISK
 *           $700e actor_behavior_type61's terminator, which the Copylock failure path also reaches
 *                 (behavior.h, WB_SHOW_DATA_DISK_PROMPT) -> WB_LOOP_EXIT_DATA_DISK
 *   $e5ba   $550  game_key_actions' round end       -> WB_KEY_ACTIONS_ROUND_END
 *           $56e  ...and its level skip             -> WB_KEY_ACTIONS_LEVEL_SKIP
 *           $c20  the gate's spend-a-life restart (WB_PLAYER_GATE_RESTART_UNWIND)
 *                                                   -> WB_LOOP_EXIT_RELOAD
 *           $1626 player_run_map_cell's triple pop (WB_PLAYER_COLLIDE_UNWIND), which the gate's own
 *                 `bra.w $1622` at $d16 shares      -> WB_LOOP_EXIT_RELOAD
 *
 * The four in the second column all reach the loop through `game_latch_input_and_step_actors` — the
 * behaviour pass hands its callee's report up unchanged (behavior.h) — and until batch 44 phase E's
 * gate the loop DISCARDED it, so a player's death kept the frame loop turning on the own-entry
 * build where the original had left it. TWO CODES AND NOT FOUR because the loop is reporting the
 * TRANSFER it cannot make and there are two destinations; WHICH arm produced it is the pass's own
 * report, and the batteries that drive each arm are the ones that name it.
 *
 * EVERY OTHER REPORT THE PASS CAN MAKE LEAVES THE LOOP RUNNING, and that is deliberate: a refusal,
 * a runaway or an unreconstructed handler's entry address is a boundary of THIS PORT, not a place
 * the original went, so there is no transfer to stand in for. ../STATUS.md §6 carries what that
 * costs on target. */
#define WB_LOOP_EXIT_DATA_DISK     4u  /* the pass reported a `jmp $e494.l`: show_data_disk_prompt */
#define WB_LOOP_EXIT_RELOAD        5u  /* ...or a `jmp $e5ba.l`: the level-entry band */

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

/* $882 — `bsr joy1_latch_edge / bsr actor_behavior_pass / rts`, and the last of the four calls
 * game_main_loop's $66e-gated block makes. The order is the point: the latch produces the joystick
 * edge the behaviour pass then reads.
 *
 * RETURNS THE PASS'S REPORT VERBATIM — one of behavior.h's WB_ACTOR_DISPATCH_* codes, one of
 * player.h's WB_PLAYER_* ones, or the entry address of a handler this port does not have. The
 * ORIGINAL drops the d0 the `bsr` leaves and this routine's own `rts` carries nothing; what travels
 * here is the out-of-band boundary report, which is a port artefact and has to reach a caller that
 * can act on it. WB_LOOP_EXIT_* above says which four values `game_main_loop` acts on. */
uint32_t game_latch_input_and_step_actors(uint8_t *image);

/* $50a — snap WB_SCROLL_FOLLOW_X/_Y to even pixels, rounding x UP instead of down while the
 * followed actor's WB_ACTOR_FLAG_SIDE_BIT is set. Between bg_scroll_blit and sprite_draw_pass,
 * which is where the camera has to be quantised for the pass below it to draw on a word boundary. */
void game_snap_follow_cursor(uint8_t *image);

/* $e0a8 — the round bonus's SETUP, and a true routine: `bsr.w $e0a8` at $e048 is its one caller and
 * it ends in its own `rts`. Loads the bonus stage, switches into A30 mode, plots the banner and
 * computes WB_ROUND_BONUS_METER_TARGET. */
void round_bonus_setup(uint8_t *image);

/* $e032 — the round bonus, one frame of it, and the long-queued reader of WB_EVENT_FINISHED_E1BE.
 * Returns at once while that word is clear; otherwise runs setup, then the drain, then the refill,
 * and ends by raising WB_ROUND_END_RELOAD_REQUEST for game_key_actions to consume. */
void round_bonus_run_frame(uint8_t *image);

/* $624c — replace the YM2149 port A's low three bits (the floppy's side and drive selects) with
 * `bits`, the original's d0, keeping WB_PSG_PORT_A_KEEP. A read-modify-write, so the case must
 * declare the register's prior contents with `psg_seed`. */
void psg_set_drive_select(uint8_t *image, uint32_t bits);

/* $6268 — every drive off. vbl_handler's one call, made on the frame WB_FLOPPY_IDLE_TIMER expires. */
void floppy_deselect_drives(uint8_t *image);

/* $716 — THE VERTICAL-BLANK HANDLER, and the program's only periodic tick. Raises WB_VBL_COUNTER,
 * runs the music tick, and counts WB_FLOPPY_IDLE_TIMER down to the drive deselect.
 *
 * ITS DIFFERENTIAL STOPS AT THE `rte`. The CHECKPOINT is not new — it is the kit's documented
 * answer for a run that cannot reach an `rts`, and TRAP_MODEL.md already applies it to a `Pterm`
 * that lands on the sentinel longword. What is new is the REASON an interrupt handler needs one,
 * which is recorded in no kit document; a reader meeting `stop_pc=VBL_RTE` in test_game.py is owed
 * it, and so is the next project to port a handler (../STATUS.md queues moving it to the kit):
 *
 *   * THE RUNNER'S FRAME IS AN `rts` FRAME AND AN `rte` POPS A WIDER ONE. `osh_run` plants the
 *     4-byte sentinel AT a7 and stops when the PC reaches it (tools/recreate_kit/oracle/shim.c);
 *     `rte` takes a 6-byte exception frame — SR from (a7), PC from 2(a7) — so it reads the
 *     sentinel's own high word as a status register and assembles a PC out of the sentinel's low
 *     word and whatever follows it. The two disagree BY CONSTRUCTION, and no poke fixes it: the
 *     runner overwrites the frame's first longword after every poke lands.
 *   * SO THE CASES CHECKPOINT THE `rte` ITSELF, which is the kit's documented answer for a run that
 *     cannot reach an `rts` (TRAP_MODEL.md). Nothing is lost by stopping one instruction early: the
 *     `rte` restores a7 and the SR and writes no image byte, and the `movem` pair around the body
 *     has already put back every register it saved.
 *   * AND THE CHECKPOINT IS SELF-WITNESSING HERE, unlike the scene driver's. `run_reaching` exists
 *     because a `stop_pc` run stops at EITHER the checkpoint or an `rts`, so a case that only set
 *     one would pass whichever fired. This handler HAS no `rts` — test_game.py asserts that from
 *     the bytes — so the checkpoint is the only stop, and `emu.run` raises when a run reaches
 *     neither. A negative control drives the same case without it and requires that raise.
 *
 * The `movem.l #$fffe,-(a7)` / `movem.l (a7)+,#$7fff` pair is NOT reproduced. It saves the machine's
 * registers around a handler that must not disturb the code it interrupted; a C function's
 * registers are its compiler's business, and the bytes the save writes land in the runner's stack
 * band, which the harness excludes from the diff. It is not the only such pair on the path: the
 * tick is reached through the stub at $17aea, itself a `movem`/`bsr`/`movem`/`rts`, so a run pushes
 * 120 bytes of saved registers and not 60. What that costs is in ../STATUS.md's
 * honestly-unpinned list. */
void vbl_handler(uint8_t *image);

/* $694 — THE FLIP, and game_main_loop's last call: swap WB_SCREEN_FRONT with WB_SCREEN_BACK, publish
 * the new front buffer to the shifter, wait out the vertical blank, toggle WB_FRAME_TOGGLE and run
 * the white-flash countdown.
 *
 * IT BUSY-WAITS TWICE ON WB_VBL_COUNTER, at WB_FLIP_READY_WAIT_PC and WB_FLIP_TICK_WAIT_PC, and a
 * case therefore declares BOTH as its `wait_sites` — even the one no schedule entry stores on,
 * because a poll the model does not count is refused rather than served
 * (tools/recreate_kit/include/sched.h). What that keying buys, and what a run TOTAL hid here for two
 * phases, is in ../STATUS.md's batch 42 phase C and in os.h's "WAIT SITES".
 *
 * WHAT IT PUTS ON THE SCREEN IS NOT PINNED. Three shifter registers over four writes — the screen
 * base's two bytes and colour 0 twice — are off the image, dropped by the oracle, and mirrored by
 * nothing on this side. The same standing hole set_palette has carried since batch 12. */
void flip_screen(uint8_t *image);

/* THE SCREEN-BASE SINK IS NOT DECLARED HERE. `shifter_screen_base_write` is ../include/shifter.h's,
 * with the palette write src/stage.c used to export and the word write `flip_screen`'s flash makes:
 * one module states the port's whole shifter boundary and its one `#ifdef WB_ON_TARGET` arm. */

/* $4a0 — THE FRAME LOOP, and the routine every other name in this header is called BY. One call of
 * this function is ONE ITERATION: the original's `bra.s $4a0` at $508 is where a case checkpoints
 * it, since the loop has no exit instruction at all.
 *
 * Returns one of the WB_KEY_ACTIONS_* / WB_LOOP_EXIT_* codes above. WB_KEY_ACTIONS_RETURNED means
 * the iteration ran to the backward branch; anything else means the original unwound out of the
 * loop into the boot chain, which is a transfer this reconstruction reports rather than makes —
 * from `game_key_actions` for the first three and from the behaviour pass for the last two.
 *
 * `sprites` is `sprite_draw_pass`' register file (include/blit.h) — the loop's only argument,
 * because that is the loop's only callee with a register interface. */
uint32_t game_main_loop(uint8_t *image, sprite_pass_regs *sprites);

#endif /* WONDERBOY_GAME_H */
