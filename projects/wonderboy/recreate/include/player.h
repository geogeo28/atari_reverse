/* player.h — THE PLAYER'S OWN FRAME, below `actor_behavior_type01_player` ($a38).
 *
 * Slot 1 of WB_ACTOR_BEHAVIOR_TABLE is the one dispatch row src/behavior.c does not have, and it is
 * not a handler in that file's sense at all: it is NINE `bsr`s in sequence ($a38..$a73), each into a
 * routine of its own, spread over $a76..$21e4 (one of the nine is `actor_fall_and_settle`, which the
 * whole behaviour tier shares). THE PLATES HERE NAME EACH ROUTINE'S CALL SITE rather than its
 * ordinal in that sequence: an ordinal is a number two documents can disagree about, and they did.
 *
 * THIS FILE IS THE FIRST OF THOSE TIERS — two of those calls ($a76 and $d84), the jump machine the
 * third one reaches through the gate ($e06), the routine the fourth will call when it lands ($107c)
 * and the spawn helper the second one hands a template to ($539e) — chosen because every callee
 * below them is already reconstructed. What is NOT here is named at the bottom of this comment.
 *
 * WHY $539e IS IN THIS FILE and not src/scene.c, which its name would suggest. The rule this
 * workspace uses is the MODULE OF ITS CALLER — `sound_request_9` lives in src/behavior.c because its
 * callers are dispatch rows, not in src/sound.c — and this routine's one caller is
 * `player_pending_event_gate` ($b1a), the player's own second call. It also sits inside the
 * BEHAVIOUR band ($539e, between slot 35's template and slot 36's entry) and fills a record for the
 * three event actors src/behavior.c holds, so scene.c is the one home it has no claim from at all.
 *
 * WHY A FILE OF ITS OWN rather than more of src/behavior.c. The player's subtree is ~4,900 unported
 * bytes across five tiers (input, the jump machine, the walk accelerator, the collision/scene tree
 * at $151a and the stage transition at $1f54); src/behavior.c is the sixty-one OTHER rows and is
 * already 5,000 lines. The two meet at exactly one address, and that address stays where the
 * behaviour tier's battery pins it: $d78 (`player_gate_on_1516`) is defined in src/behavior.c
 * because slot 53 and the four gated hurt arms call it and test_behavior.py holds its entry pin —
 * it is the behaviour tier's one entrance into this file, and behavior.h declares it.
 *
 * THE REGISTER CONVENTION IS actor.h's: the player's record address in a0, which every routine here
 * takes as `actor`. None of them returns a register any caller reads, so all of them are `void`.
 *
 * NO BOUNDARY IS REPORTED FROM THIS FILE, which is what makes it the first tier. These five call
 * exactly THREE things between them — `joy1_newly_pressed` ($682), `snd_call_trigger_effect`
 * (stub +56) and `snd_play_song` (stub +0) — and all three are reconstructed, so each runs to the
 * original's own `rts`. (The map probes, the fall pass and the two allocators are callees of the
 * routines this batch DEFERRED, not of these.)
 *
 * WHAT THE FRAME STILL CALLS AND THIS FILE DOES NOT HAVE, in the order $a38 calls them:
 * `player_pending_event_gate` ($b1a, called at $a3c), `player_step_and_arm` ($ec8 at $a4a — the
 * WALK), `player_weapon_fire` ($1208 at $a4e), `player_collide_and_scroll` ($151a at $a6c) and
 * `player_stage_transition` ($1f54 at $a70, the last). ../STATUS.md's batch-40 partition prices all
 * five and says why each is not here.
 */
#ifndef WONDERBOY_PLAYER_H
#define WONDERBOY_PLAYER_H

#include <stdint.h>

/* $a76 — THE DEATH CHECK, the frame's first call ($a38). It runs only while
 * WB_HUD_METER_VALUE is zero, and the two arms are what happens when the player has just run out.
 *
 * The revival arm (WB_HUD_SLOT_BBC6 holding a charge, or WB_KEY_SEQUENCE_MATCHED set): SFX
 * WB_PLAYER_DEATH_SFX, the slot rearmed, message WB_TEXT_MESSAGE_REVIVAL_USED posted and the meter
 * refilled to WB_PLAYER_METER_REVIVE. The other arm is the death itself: the flicker bit lowered and
 * — while WB_STAGE_RESET_BLOCK's first word is not already negative — WB_STATE_FLAG_A34 raised, song
 * WB_PLAYER_DEATH_SONG started through stub +0, and three words raised that
 * `player_pending_event_gate` and the scroll then read.
 *
 * THE CHEAT WORD IS AN INPUT ON BOTH ARMS and it is not the same input twice: nonzero takes the
 * revival arm whether or not the slot has a charge, and nonzero on that arm SKIPS the rearm — so the
 * medicine is never spent and the meter refills for ever. */
void player_meter_empty_check(uint8_t *image, uint32_t actor);

/* $e06 — THE JUMP MACHINE, the body `player_gate_on_1516` branches into while WB_TILE_33_MODE is
 * clear, and the only way into it: the whole-image census finds ONE instruction naming this address,
 * the `beq.w` at $d7e. (../names.txt's plate said `player_apply_joystick` "also falls into" it; that
 * routine ends in its own `rts` at $e04 — batch 40 corrected it.)
 *
 * Three exclusive arms over WB_ACTOR_FLAGS, tested in this order, and every frame first stamps
 * WB_ACTOR_FIELD_10 with WB_EFFECT_STATE_BD6A's low byte plus WB_PLAYER_JUMP_STRENGTH_BIAS — the
 * jump's height, re-derived on every frame from a state word nothing else in the recovered code
 * reads:
 *   * WB_ACTOR_FLAG_MOVING_BIT set — ASCENDING. The record rises by its own WB_ACTOR_SPEED and the
 *     speed is spent one per frame; the frame it reaches zero ends the climb and reloads the byte
 *     with 1, which is what leaves the record falling at one pixel a frame.
 *   * WB_ACTOR_FLAG_SUPPORTED_BIT set — STANDING. A rising edge of WB_JOY1_UP_BIT launches:
 *     WB_PLAYER_JUMP_SFX, the two motion bits raised, the supported bit lowered and the speed loaded
 *     from the strength byte above.
 *   * neither — AIRBORNE, and this is the WING BOOTS. While WB_HUD_SLOT_BBC2 still has a charge and
 *     UP is HELD (the level, not the edge), the fall speed is forced back to 1 and one charge is
 *     spent per frame; the frame the last one goes the slot is rearmed with WB_HUD_SLOT_REARM and
 *     message WB_TEXT_MESSAGE_WING_BOOTS_LOST is posted. The message is what names the slot. */
void player_jump_step(uint8_t *image, uint32_t actor);

/* $d84 — THE LADDER, called at $a60, after the fall pass. It does nothing at all unless
 * WB_TILE_33_FLAG is up, i.e. unless `actor_fall_and_settle`'s player-only head found tile
 * WB_MAP_TILE_33 under the record this frame.
 *
 * Up and down are one body with three operands changed: the two facing bits are lowered, the x is
 * SNAPPED to WB_PLAYER_LADDER_X_MASK plus WB_PLAYER_LADDER_X_BIAS (a mask that keeps bit 0, so an
 * odd x stays odd), WB_TILE_33_STEP is raised, and the y moves WB_PLAYER_LADDER_STEP pixels and is
 * masked even. What differs is the direction of that move and the value written to WB_TILE_33_MODE:
 * WB_TILE_33_MODE_UP going up and WB_TILE_33_MODE_DOWN going down, two different nonzero words for
 * one flag every reader treats as a boolean. On the frame neither direction is held — and on every
 * frame the flag is down — the routine's whole effect is to clear WB_TILE_33_STEP. */
void player_apply_joystick(uint8_t *image, uint32_t actor);

/* $107c — LEAVING THE LADDER. Two call sites, both inside `player_step_and_arm` ($ec8, phase B)
 * and both guarded by `tst.w WB_TILE_33_MODE`, so this runs on the frame a climbing player pushes
 * left or right. It has NO caller in this port until that routine lands.
 *
 * The mode is cleared, the record is put back into the falling state (supported down, moving and
 * launched up) and WB_ACTOR_SPEED is reloaded with the same
 * WB_EFFECT_STATE_BD6A + WB_PLAYER_JUMP_STRENGTH_BIAS byte the jump machine stamps into
 * WB_ACTOR_FIELD_10 — so stepping off a ladder costs a full jump's worth of upward speed. */
void player_reset_ground_state(uint8_t *image, uint32_t actor);

/* $539e — the spawn helper `player_pending_event_gate` reaches by `bsr` at $c5e, its one caller.
 * `spawn_template` is the original's a1 (the 32 bytes at WB_ACTOR_TYPE35_TEMPLATE) and `destination` its
 * a2 (the record to fill). EIGHT longwords land, not the five ../names.txt's plate claimed: the
 * FIRST is WB_RECORD_PTR_10420's own +20 longword, written over the record's x and y, and only then
 * does `lea 4(a1),a1` skip the template's first longword and copy the SEVEN above it. So the
 * template's first four bytes are never read, and the record is positioned from the scene descriptor
 * rather than from the template. */
void scene_copy_record_fields(uint8_t *image, uint32_t spawn_template,
                              uint32_t destination);

#endif /* WONDERBOY_PLAYER_H */
