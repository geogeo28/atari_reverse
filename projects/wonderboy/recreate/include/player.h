/* player.h — THE PLAYER'S OWN FRAME, below `actor_behavior_type01_player` ($a38).
 *
 * Slot 1 of WB_ACTOR_BEHAVIOR_TABLE is the one dispatch row src/behavior.c does not have, and it is
 * not a handler in that file's sense at all: it is NINE `bsr`s in sequence ($a38..$a73), each into a
 * routine of its own, spread over $a76..$21e4 (one of the nine is `actor_fall_and_settle`, which the
 * whole behaviour tier shares). THE PLATES HERE NAME EACH ROUTINE'S CALL SITE rather than its
 * ordinal in that sequence: an ordinal is a number two documents can disagree about, and they did.
 *
 * THIS FILE IS THE FIRST OF THOSE TIERS — batch 40 phase A took four of those calls ($a76, $d84,
 * the jump machine the gate reaches at $e06, and $107c) plus the spawn helper $539e, phase B added
 * the two below them that are also CALLEE-CLEAN (the WALK, $ec8, and the WEAPON, $1208), and phase C
 * the LAST call, `player_stage_transition` ($1f54). "Callee-clean" is the whole criterion — every
 * routine any of these reaches is already reconstructed — and what is NOT here is named at the
 * bottom of this comment.
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
 * ONE OF THE SEVEN TAKES A THIRD PARAMETER AND IT IS NOT A REGISTER: `player_weapon_fire`'s
 * `entry_extend` is the 68000's X FLAG, which its `sbcd` folds in and no `regs=` dict can carry —
 * `leaf.register_glue` takes its arity from the caller, so a battery binding this one from the
 * convention above rather than from its own prototype would call a 3-argument function with 2.
 *
 * THE FIRST EIGHT REPORT NO BOUNDARY AT ALL, which is what made this the first tier. Between them
 * they call exactly SIX things — `joy1_newly_pressed` ($682), `snd_call_trigger_effect` (stub +56),
 * `snd_play_song` (stub +0), the two map step probes ($10a2/$1170) and `actor_alloc_slot_high`
 * ($1b8e) — and every one of those is reconstructed, so each runs to the original's own `rts`.
 * (The fall pass and the LOW allocator are callees of the routines still deferred, not of these.)
 *
 * THE NINTH DOES REPORT ONE — two, in fact. `player_run_map_cell` ($151a, batch 41 phase A) adds
 * `snd_stop` (stub +28) and `actor_knock_back_and_launch` ($6ade) to that list, both reconstructed;
 * what it cannot follow is not a callee but two ENDINGS, a stack unwind and a spin, and the three
 * WB_PLAYER_COLLIDE_* codes below are what it returns in their place.
 *
 * WHAT THE FRAME STILL CALLS AND THIS FILE DOES NOT HAVE, in the order $a38 calls them: exactly
 * ONE, `player_pending_event_gate` ($b1a, called at $a3c). Batch 41 phase A took the other,
 * `player_run_map_cell` ($151a at $a6c). ../STATUS.md's batch-40
 * partition prices $b1a and says why it is not here: it is UNPORTABLE rather than merely unported,
 * because THREE of its exits leave through a stack unwind instead of returning — `lea 4(a7),a7 /
 * jmp` at $bdc and at $c20, and — the one a census of its own instructions does not see —
 * `bra.w $1622` at $d16, which lands in `player_run_map_cell`'s own `lea 12(a7),a7 / jmp $e5ba.l`
 * and so pops THREE return addresses in another routine's body.
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

/* $107c — LEAVING THE LADDER. Two call sites, both inside `player_step_and_arm` ($ec8) and both
 * guarded by `tst.w WB_TILE_33_MODE`, so this runs on the frame a climbing player pushes left or
 * right. Batch 40 phase A had no caller for it at all; phase B's walk is that caller.
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

/* $ec8 — THE WALK, called at $a4a. FIVE SECTIONS in a row, each falling into the next:
 *   * the KNOCK-BACK: while WB_ACTOR_FIELD_29 (the count `actor_stun_followed` seeds) is nonzero,
 *     one map step AWAY from WB_ACTOR_FLAG_SIDE_BIT and one off the count;
 *   * the FIRE EDGE: a rising WB_JOY1_FIRE_BIT raises WB_ACTOR_FLAG_FIRED_BIT, lowers
 *     WB_ACTOR_FLAGS2_BIT_0 and zeroes the walk speed;
 *   * the FLICKER COUNTDOWN, whose one reader this is;
 *   * the HURT DRIFT, gated on WB_ACTOR_FLAGS2_BIT_0: landing lowers the bit, otherwise the record
 *     is pushed WB_ACTOR_FIELD_31 pixels the way WB_ACTOR_FIELD_30 names and two are spent;
 *   * and the WALK ACCELERATOR. WB_ACTOR_FIELD_22 is the speed, WB_ACTOR_FIELD_23 the direction it
 *     is travelling (zero LEFT, WB_ACTOR_ST_BYTE right) and WB_ACTOR_FIELD_24 a counter that lets
 *     the speed rise on one frame in WB_PLAYER_WALK_SUBFRAME_MASK + 1, up to
 *     WB_EFFECT_STATE_BD6A + WB_PLAYER_WALK_SPEED_BIAS. Holding the direction it is NOT travelling
 *     sheds speed instead, and the two rates are NOT equal.
 *
 * ITS TWO CALLS TO `player_reset_ground_state` ARE THAT ROUTINE'S ONLY CALL SITES in the image, so
 * batch 40 phase A's "no caller in this port" is retired by this routine landing. */
void player_step_and_arm(uint8_t *image, uint32_t actor);

/* $1208 — THE WEAPON, called at $a4e. Four gates in series — no ladder tile under the player, the
 * WB_EFFECT_RECORD_LIST write pointer off its base (i.e. something IS held), `joy1_newly_pressed`
 * exactly WB_PLAYER_FIRE_EDGE_EXACT, and WB_JOY1_DOWN_BIT held — and then the newest record's HIGH
 * byte picks one of four arms: the LIGHTNING (which only sets WB_FLASH_TIMER), the WIND SPOUT, the
 * FIREBALL and the BOMB, the last three of which allocate out of the high pool and give up without
 * spending anything when it is full. Every arm that gets that far then spends one packed-BCD unit
 * off WB_RECORD_LOW_BYTE and pops the record when the count reaches zero.
 *
 * `entry_extend` IS THE X THE `sbcd -(a2),-(a6)` AT $1260 FOLDS IN, and this is the first site in
 * this project where a THREADED one is also LOCALLY PRODUCED on one arm. The reading per arm, which
 * is what include/hud.h's site table asks of every such call:
 *   * FIREBALL — PRODUCED HERE. `subq.w #8,2(a1)` at $12e2 is the only arithmetic instruction
 *     between the arm's `bsr $1b8e` and the `sbcd`; `btst`, `bset`/`bclr` and `clr.b` below it leave
 *     X alone. So the bit is a BORROW out of the shot's y and an ordinary differential row drives it
 *     either way — which is why this parameter is a parameter and not a claim.
 *   * WIND SPOUT and BOMB — THE CALLER'S, and the enumeration is COMPLETE rather than indicative,
 *     because a site that claims an inherited X can only be closed from the plate if every
 *     instruction on the path is named. The gates and the dispatch above the arms:
 *     `tst.w`, `cmpi.l`, `bsr`/`rts`, `cmp.b`, `btst`, `movea.l`, `cmpi.b`, `beq`/`bne`/`bra`.
 *     `joy1_newly_pressed` ($682), which runs on EVERY path here including the lightning's, is
 *     `move.b`/`move.b`/`eor.b`/`and.b`/`rts` — and the two LOGICAL ops are the ones an
 *     "arithmetic only" reading would miss: EOR and AND set N and Z, clear V and C, and leave X
 *     ALONE. `actor_alloc_slot_high` ($1b8e) is NINE instructions, `movea.l`/`lea`/`move.w` then a
 *     loop of `cmpi.w`/`beq`/`lea`/`dbf` and a `movea.l #$0`/`rts` — no arithmetic, and `dbf`
 *     writes no condition code at all. Below the allocation: `move.w #imm`, `move.b #imm`,
 *     `clr.w`/`clr.b`, `bclr`/`bset`, `move.l`, and `addq.l` on an ADDRESS register, which is the
 *     one form of an arithmetic opcode that sets NO flags. So the bit is whatever entered $1208.
 *   * LIGHTNING — THE CALLER'S too, and by a shorter argument, though NOT by the shortest one: the
 *     arm itself is one `move.w #$2,$714.w`, but the four gates above it still run and so does
 *     `joy1_newly_pressed`, so the reading rests on the same enumeration.
 * And what "the caller's" means here is `player_step_and_arm`'s exit X, because $a4a and $a4e are
 * adjacent `bsr`s with nothing between them. That routine's last X-writer is data dependent (a
 * `subq.b`/`addq.b` on one of four record bytes, or the map probe's own arithmetic), so the three
 * arms above are the same class as `overlap_mask_exit_extend`'s site — and `emu.run` forces the CCR
 * clear, so no case in this project can enter them with X set. ../STATUS.md carries that. */
void player_weapon_fire(uint8_t *image, uint32_t actor, unsigned entry_extend);

/* $1f54 — THE STAGE TRANSITION, called at $a70 (the frame's LAST call) and again at $bb0, on nearly
 * every arm of `player_pending_event_gate`. Four flag words in one chain, and only the fourth arm
 * runs on an ordinary frame:
 *   * WB_STAGE_ANIM_DONE_B10 set — nothing at all. It is this routine's own latch, so once the
 *     transition has played out the whole routine is an `rts` until something clears the word.
 *   * WB_STAGE_ANIM_REQUEST_B0E set — the TRANSITION, twenty-four frames off one of two tables
 *     WB_EFFECT_STATE_21E4 picks between, and the wrap raises WB_STAGE_ANIM_DONE_B10.
 *   * WB_EVENT_ANIM_DONE_B16 set — sixteen frames off WB_PLAYER_EVENT_ANIM_CURSOR's table; the wrap
 *     raises WB_STAGE_ANIM_DONE_B18 and blanks the sprite.
 *   * WB_STAGE_RESET_BLOCK set (the death handshake `player_meter_empty_check` writes) — sixteen
 *     frames off WB_PLAYER_DEATH_ANIM_CURSOR's, with no completion flag of its own.
 *   * none of them — the POSTURE SELECTOR, which is the player's sprite on every ordinary frame:
 *     the hurt pair, then the ladder, then the swing, then standing / walking / jumping / falling
 *     out of one of the three WB_PLAYER_POSTURE_TABLE_* records.
 *
 * IT IS CALLEE-CLEAN like the seven above it — the only thing it calls is the SFX stub — and it is
 * where BOTH of the walk's flag bits are spent: WB_ACTOR_FLAG_FIRED_BIT gates the swing and is
 * lowered by it, WB_ACTOR_FLAG_MOVED_BIT chooses the walk cycle over standing still. Batch 40's
 * "what those two bits BUY is decided in the one routine of the frame this port lacks" is answered
 * by this routine landing.
 *
 * THE SWING'S FIRST FRAME IS INDEXED BY THE SFX ID, not by the cursor — see WB_PLAYER_ATTACK_SFX and
 * the plate at $20ca. Reproduced, not tidied. */
void player_stage_transition(uint8_t *image, uint32_t actor);

/* The two places `player_run_map_cell` stops being a function, reported in place of what the
 * original does there. C-only — no value here is in the image — but test/layout.py scrapes this
 * header so that a case names the same three outcomes the C does.
 *
 * WB_PLAYER_COLLIDE_SOUND_WAIT IS A BOUNDARY OF THE ORACLE'S, NOT OF THE PORT'S, which is what makes
 * it a report rather than a refusal. `tst.b 378(a5) / bne.s $1932` spins until
 * WB_SND_ENGINE_ENABLED goes zero, and only the sound module's own interrupt clears it — which no
 * differential run has.
 *
 * AND THE BYTE IS NOT AN INPUT THE CASE CAN CHOOSE: `snd_play_song`, three instructions above the
 * spin on the one path that reaches it, raises that very byte as its LAST write (`st 378(a3)` at the
 * end of $17b3a). So the spin is entered on EVERY run, whatever the case seeds, and everything below
 * it is unreachable under either core rather than merely awkward: SIX instructions, $1938..$194d,
 * TWENTY-TWO bytes, ending in the arm's own `rts`. They are therefore NOT PORTED — a branch no case
 * can drive would ship unpinned — and this report is what the reconstruction returns in their place,
 * from the instant the oracle arrives at the `tst.b`. ../STATUS.md records what that leaves
 * honestly unpinned.
 *
 * WB_PLAYER_COLLIDE_UNWIND is the port's own, and it is the `lea 12(a7),a7 / jmp $e5ba.l` at $1622:
 * THREE return addresses discarded, so the arm abandons this routine, `actor_behavior_type01_player`
 * and whatever called that. Nothing a C function can do, so it says which arm it took and the case
 * diffs at the instant control arrives at the `lea`. TWO instructions reach it — the `beq.w` at
 * $161c on tile WB_MAP_TILE_39, and `player_pending_event_gate`'s `bra.w` at $d16 — and only the
 * first is this routine's own. */
#define WB_PLAYER_COLLIDE_RETURN      0u  /* the original `rts`d */
#define WB_PLAYER_COLLIDE_SOUND_WAIT  1u  /* ...or reached the busy-wait at $1932 with the byte up */
#define WB_PLAYER_COLLIDE_UNWIND      2u  /* ...or the triple pop at $1622 */

/* $151a — THE COLLISION MAP, called at $a6c and only while WB_STATE_FLAG_A32 is clear. One cell
 * lookup and then one of three bands (see WB_SCENE_TRIGGER_CODE_FIRST in wonderboy.h):
 *   * below WB_SCENE_TRIGGER_CODE_FIRST — WB_TILE_33_FLAG's BYTE cleared, and nothing else;
 *   * up to WB_SCENE_TRIGGER_CODE_LAST — the cell names a 32-byte SCENE DESCRIPTOR, which is
 *     published to WB_RECORD_PTR_10420 (this is the image's ONE writer of that pointer) and then
 *     dispatched on its own kind word. Eight arms; a ninth value publishes and returns;
 *   * above it — the six special tiles WB_MAP_TILE_34..WB_MAP_TILE_39 beside WB_MAP_TILE_33.
 *
 * ITS ONLY CALLEES ARE RECONSTRUCTED: `actor_alloc_slot_high` ($1b8e) on the WB_MAP_TILE_34 arm, the
 * sound stub's +0/+28/+56 entries, and — through `bra.w $6ade` at $15e8 —
 * `actor_knock_back_and_launch`, which is `actor_damage_followed`'s own tail. */
uint32_t player_run_map_cell(uint8_t *image, uint32_t actor);

#endif /* WONDERBOY_PLAYER_H */
