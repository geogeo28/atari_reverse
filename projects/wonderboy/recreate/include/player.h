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
 * WHY A FILE OF ITS OWN rather than more of src/behavior.c. The player's subtree was ~4,900 unported
 * bytes across five tiers (input, the jump machine, the walk accelerator, the collision/scene tree
 * at $151a and the stage transition at $1f54); src/behavior.c is the sixty-one OTHER rows and is
 * already 5,000 lines. The two meet at exactly one address, and that address stays where the
 * behaviour tier's battery pins it: $d78 (`player_gate_on_1516`) is defined in src/behavior.c
 * because slot 53 and the four gated hurt arms call it and test_behavior.py holds its entry pin —
 * it is the behaviour tier's one entrance into this file, and behavior.h declares it.
 *
 * THE REGISTER CONVENTION IS actor.h's: the player's record address in a0, which every routine here
 * takes as `actor`. Only ONE of them hands a register back that a caller reads — the gate's d7, and
 * even that is returned as an exit code rather than as the register (see its plate below) — so the
 * rest are `void`.
 * ONE OF THEM TAKES A THIRD PARAMETER AND IT IS NOT A REGISTER: `player_weapon_fire`'s
 * `entry_extend` is the 68000's X FLAG, which its `sbcd` folds in and no `regs=` dict can carry —
 * `leaf.register_glue` takes its arity from the caller, so a battery binding this one from the
 * convention above rather than from its own prototype would call a 3-argument function with 2.
 *
 * EIGHT OF THE TEN REPORT NO BOUNDARY AT ALL, which is what made this the first tier. Between them
 * they call exactly SIX things — `joy1_newly_pressed` ($682), `snd_call_trigger_effect` (stub +56),
 * `snd_play_song` (stub +0), the two map step probes ($10a2/$1170) and `actor_alloc_slot_high`
 * ($1b8e) — and every one of those is reconstructed, so each runs to the original's own `rts`.
 * (The fall pass and the LOW allocator are callees of the routines still deferred, not of these.)
 *
 * THE OTHER TWO REPORT AN ENDING RATHER THAN A CALLEE. `player_run_map_cell` ($151a, batch 41 phase
 * A) adds `snd_stop` (stub +28) and `actor_knock_back_and_launch` ($6ade) to that list, both
 * reconstructed; what it cannot follow is two ENDINGS, a stack unwind and a spin, and the three
 * WB_PLAYER_COLLIDE_* codes below are what it returns in their place. `player_pending_event_gate`
 * ($b1a, batch 41 phase C) is the heavier of the two, with SIX codes over five endings, and its own
 * plate at the foot of this file is where they are.
 *
 * WHAT THE FRAME STILL CALLS AND THIS FILE DOES NOT HAVE: NOTHING. All nine of `$a38`'s `bsr`s are
 * reconstructed as of batch 41 phase C. What is left of the player is `$a38` ITSELF — 62 bytes of
 * nine calls, the caller-side d7 gate on the pending-event gate's answer, and two conditional guards
 * (`$6ef0` over the fall, `$a32` over the collision map, each skipping exactly one call).
 *
 * IT IS STILL NOT PORTED, and as of batch 41 phase D the reason is no longer only the three costs
 * that phase C priced. The FOURTH is inside this header: `$a4a` and `$a4e` are adjacent `bsr`s, so
 * the frame is the site that must supply `player_weapon_fire`'s `entry_extend`, and the two cases
 * that measure that are beside the weapon's own rows below. ../STATUS.md's batch 41 phase D section
 * prices the row rather than this plate.
 *
 * BATCH 41 PHASE E PAID HALF OF THAT FOURTH COST AND MEASURED THE OTHER HALF. `player_step_and_arm`
 * now REPORTS its exit X and `player_weapon_fire` is fed it, pinned end to end at the `sbcd` — so
 * what the frame has to do with the bit is settled. What it has to be GIVEN is not: the walk's
 * coasting arm passes its caller's X straight through, and on a frame that fires the weapon that
 * arm is the one that runs, so the frame owes an entry bit of its own.
 *
 * THAT BIT COMES FROM `$d78`, AND ON A FIRING FRAME IT IS DERIVABLE FROM MEMORY. `player_jump_step`
 * ($e06), which `$d78` falls into whenever the ladder mode is down, opens with
 * `move.w $bd6a.l,d0 / addi.b #$8,d0` and THREE of its six exits still carry that instruction's X —
 * everything between is `move.b`, `btst`, `tst.b`, the branches, and `joy1_newly_pressed`, none of
 * which writes a flag. The other three leave `subq.b #1,$bbc2.l` ($e48), `subq.b #1,11(a0)` ($eb2),
 * or the sound stub's — and that last one is the LAUNCH arm, which a firing frame cannot take,
 * since the weapon's own gate wants the newly-pressed byte to be exactly $80 and the launch wants
 * bit 0 of it. (An earlier draft of this plate read every arm as overwriting the opening `addi.b`
 * and concluded that the chain ran up to `actor_dispatch_behavior`'s `jmp (a1)`; the bytes refute
 * that and it is RETRACTED.)
 *
 * SO THE FIFTH COST IS A MODEL, NOT A THREADING: `$a76` and `$b1a` cannot reach the `sbcd` with
 * their bit intact on any frame that fires, and the dispatch table's signature is not part of it.
 * The one arm that still passes a caller's bit is `$d78`'s own `tst.w $1516.l / rts` on a ladder,
 * and whether such a frame can fire at all is unmeasured — the weapon's first gate reads `$1514`.
 * ../STATUS.md's batch 41 phase E section prices what is left.
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
/* `extend` IS THE 68000's X, and this routine is the one place in the frame that can DESTROY it
 * with a value the port has never read (batch 41 phase F's gate found it). TWO of its four paths end
 * in a sound call — the revival's `jsr 56(a1)` at $a9e and the death's `jsr (a1)` at $aec — and
 * every instruction below either call, and every instruction of `player_pending_event_gate`'s
 * no-event path after it, is X-silent. So on those two paths the bit that arrives at $a46 is
 * `snd_trigger_effect`'s or `snd_play_song`'s, NOT the dispatcher's.
 *
 * IT IS DERIVABLE IN PRINCIPLE AND NOT MODELLED HERE: both routines end
 * `add.w d0,d0 / lea / movea.w / adda.l a3,a2 / move.l / move.l / move.b / move.b / rts`, and only
 * that `add.w` writes X — so the bit is bit 15 of a sign-extended table byte. Threading it means a
 * new output on a 334-byte routine with loops and on every one of its call sites, which is a phase
 * and not a line. Until then the port REFUSES rather than guesses: this routine writes
 * WB_PLAYER_EXTEND_UNREAD through `extend`, and `actor_behavior_type01_player` reports
 * WB_PLAYER_FRAME_SOUND_EXTEND if that value is still there when the walk would consume it.
 *
 * `extend` may be NULL — no other caller exists in the image, and the value is meaningless to one. */
void player_meter_empty_check(uint8_t *image, uint32_t actor, unsigned *extend);

/* THE SENTINEL, and it is OUT OF BAND by construction: an X flag is 0 or 1 and this is neither, so a
 * refusal cannot be confused with a bit (the standing rule that an in-band refusal collides with a
 * real value). Nothing in the chain produces it but `player_meter_empty_check`, and nothing consumes
 * it but the frame — `player_step_and_arm` and `player_weapon_fire` are never reached with it. */
#define WB_PLAYER_EXTEND_UNREAD 2u

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
 *     message WB_TEXT_MESSAGE_WING_BOOTS_LOST is posted. The message is what names the slot.
 *
 * IT REPORTS AN EXIT X through the same NULL-able `extend` its caller takes (batch 41 phase F). SIX
 * exits, and FIVE of them are a function of three bytes — the opening `addi.b #$8,d0` at $e12 is the
 * default and the ASCENT's `subq.b #1,11(a0)` and the WING BOOTS' `subq.b #1,$bbc2.l` are the only
 * two overwrites. The sixth, the LAUNCH at $ea6, leaves the sound routine's, which this port has
 * never read and no frame that also fires can reach; src/player.c's plates carry both readings. */
void player_jump_step(uint8_t *image, uint32_t actor, unsigned *extend);

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
 * batch 40 phase A's "no caller in this port" is retired by this routine landing.
 *
 * IT RETURNS A CONDITION-CODE BIT, WHICH IS WHAT BATCH 41 PHASE E ADDED. The 68000 X this routine
 * leaves is `player_weapon_fire`'s `entry_extend` — `$a4a` and `$a4e` are adjacent `bsr`s — and it
 * is per-path rather than constant, so it is THREADED: `entry_extend` in, the exit bit back. The
 * per-section model lives on the five plates in src/player.c and the probes' on
 * `map_ground_under_cell`'s in src/map.c; test_player.py's frame-composition battery pins the whole
 * chain at its one consumer, the `sbcd` at $1260.
 *
 * ONE ARM PASSES THE CALLER'S BIT STRAIGHT THROUGH — the coast on a zero speed, with no knock-back,
 * no flicker and no drift — so `entry_extend` is a real input and not a formality. THE FRAME
 * CANNOT SUPPLY IT YET: the instruction before `$a4a` is `bsr.w $d78`, whose own non-jumping arm is
 * a bare `tst.w`/`rts` that passes ITS caller's bit on, and so on up through `$b1a` and `$a76`.
 * ../STATUS.md's batch 41 phase E section prices that chain; every case here enters with the zero
 * `emu.run`'s SR = $2700 gives. */
unsigned player_step_and_arm(uint8_t *image, uint32_t actor, unsigned entry_extend);

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
 * `subq.b`/`addq.b` on one of four record bytes, or the map probe's own arithmetic), and `emu.run`
 * forces the CCR clear, so no case that ENTERS THIS ROUTINE can hand it a set X.
 *
 * THAT IS A LIMIT ON A CASE'S ENTRY, NOT ON THE GAME, and batch 41 phase D drew the line where it
 * actually falls. A run that starts at `$a4a` and lets the WALK execute produces the bit itself, and
 * the two cases beside the rows above measure it: two seeds differing in two record bytes leave the
 * image byte-for-byte identical when the walk returns, and then spend a DIFFERENT shot count. So
 * the bit is drivable after all — from the frame, not from here.
 *
 * WHICH IS WHY THIS SITE IS NOT `overlap_mask_exit_extend`'s CLASS, and that reading is RETRACTED.
 * That helper re-computes its bit from the two words the last arithmetic instruction read; here the
 * two arms leave the SAME words with the SAME values, so no function of the image can tell them
 * apart. The bit has to be THREADED — and as of BATCH 41 PHASE E it is: `player_step_and_arm`
 * reports its exit X (see its plate above and the per-section model in src/player.c), the two map
 * probes report theirs (include/map.h), and test_player.py's sixteen-row frame-composition battery
 * runs the two routines composed as `$a4a`/`$a4e` compose them against the ORIGINAL's own pair, one
 * row per X-writer the walk can leave last. What is still `$a38`'s to supply is the bit the WALK is
 * entered with, on the one arm that passes it through; ../STATUS.md's batch 41 phase E section
 * prices what that costs. */
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
 * end of $17b3a). So the spin is entered on EVERY run whatever the case SEEDS, and the six
 * instructions below it — $1938..$194d, twenty-two bytes, ending in the arm's own `rts` — are NOT
 * PORTED: a branch no case could drive would ship unpinned, and this report is what the
 * reconstruction returns in their place, from the instant the oracle arrives at the `tst.b`.
 *
 * BATCH 42 PHASE A MOVED THE SECOND HALF OF THAT ARGUMENT, so read it with its date on it. The
 * seeding half is unchanged and still decisive. The half that said no core has anything to clear the
 * byte is now FALSE: the kit's SCHEDULED WRITE model (tools/recreate_kit/TRAP_MODEL.md, "Phase 8")
 * stores into memory mid-run at a declared arrival, which is exactly what the sound module's own
 * interrupt does to this byte. So those six instructions are REACHABLE — through a declared store
 * rather than a seed — and porting them is queued in ../STATUS.md rather than done. Until it lands
 * this report is what the arm returns, and what it costs is unchanged.
 *
 * WB_PLAYER_COLLIDE_UNWIND is the port's own, and it is the `lea 12(a7),a7 / jmp $e5ba.l` at $1622:
 * THREE return addresses discarded, so the arm abandons this routine, `actor_behavior_type01_player`
 * and whatever called that. Nothing a C function can do, so it says which arm it took and the case
 * diffs at the instant control arrives at the `lea`. TWO instructions reach it — the `beq.w` at
 * $161c on tile WB_MAP_TILE_39, and `player_pending_event_gate`'s `bra.w` at $d16 — and only the
 * first is this routine's own. */
/* THE THREE FAMILIES SHARE ONE NUMBER SPACE, and batch 41 phase F is what made that mandatory.
 * `actor_behavior_type01_player` propagates its callees' reports VERBATIM (behavior.h's boundary
 * rule) and `actor_dispatch_behavior` passes the row's answer straight up, so the codes below, the
 * gate's at the foot of this file, and behavior.h's four WB_ACTOR_DISPATCH_* all arrive at the same
 * caller through the same `uint32_t`. Before the flip they were three private spaces and three
 * pairs collided; they are now allocated once, and
 * `test_the_dispatch_code_space_has_no_collision` in test/test_behavior.py is what says so rather
 * than this comment.
 *
 * ZERO IS SHARED ON PURPOSE and is the one value that may be: WB_ACTOR_DISPATCH_RAN,
 * WB_PLAYER_COLLIDE_RETURN and WB_PLAYER_GATE_FRAME_RUNS all mean "the original reached its own
 * `rts`", which is the same fact about three routines and not three facts. Every code that stands
 * in for a transfer the port cannot follow has a number of its own. */
#define WB_PLAYER_COLLIDE_RETURN      0u  /* the original `rts`d */
#define WB_PLAYER_COLLIDE_SOUND_WAIT  4u  /* ...or reached the busy-wait at $1932 with the byte up */
#define WB_PLAYER_COLLIDE_UNWIND      5u  /* ...or the triple pop at $1622 */

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

/* $b1a — THE PENDING-EVENT GATE, the frame's SECOND call ($a3c) and the one that decides whether the
 * seven below it run at all. Three words of WB_STAGE_RESET_BLOCK are tested in the order the block
 * holds them, each with an arm of its own:
 *   * the block's OWN first word — the DEATH request `player_meter_empty_check` raises at $aee.
 *     The dying player rises a pixel a frame, swaying along WB_ACTOR_TYPE30_DRIFT through
 *     WB_DEATH_DRIFT_CURSOR, until WB_SCROLL_FOLLOW_Y reaches WB_DEATH_ASCENT_TOP_Y; then the
 *     GAME OVER message goes up and every frame after that is the continue prompt;
 *   * WB_STAGE_ANIM_REQUEST_B0E — the boss defeat's. It spawns WB_ACTOR_TYPE35_TEMPLATE into
 *     WB_SCENE_SPAWN_GATE_SLOT and, once WB_EVENT_ANIM_DONE_B12 says that actor has finished,
 *     runs `scene_spawn_from_script` and takes both flags down;
 *   * WB_SCENE_ALIGN_REQUEST_B14 — the hidden door's. It spawns a PAIR of records straight (no
 *     template), waits on WB_EVENT_ANIM_DONE_B16 and then WB_STAGE_ANIM_DONE_B18, and ends the
 *     event either by advancing the stage or by raising WB_EVENT_FINISHED_E1BE.
 *
 * WHAT THE CALLER READS IS d7, AND THE C RETURNS AN EXIT CODE INSTEAD. `tst.w d7 / bmi.w $a74` at
 * $a40 reads the low word only, so the two returning endings are one bit — but the two are not the
 * same write: $b32 is `clr.l d7`, which takes the HIGH half with it, and $bb4/$d22 are
 * `move.w #$ffff,d7`, which leave it. That is a register claim, so it lives in the differential:
 * test_player.py enters every case with a known d7 and reads the whole 32 bits back out of the
 * oracle, against what the exit code says they should be.
 *
 * SIX CODES OVER FIVE ENDINGS, and the arithmetic is worth stating because it is what an audit
 * counts: the routine has five places control leaves it — two `rts`es and three unwinds — and a
 * SIXTH code for the arm where the leaving is the CALLEE's rather than this routine's. Three of the
 * five are stack unwinds, which is what batch 40 phase B read as a reason the routine could never be
 * ported at all; every callee is reconstructed now, and each ending is reported out of band and
 * diffed at a `stop_pc` checkpoint with a witness above it (README.md, "Reporting an exit the port
 * cannot take"). */
#define WB_PLAYER_GATE_FRAME_RUNS      0u  /* `clr.l d7 / rts` at $b32: none of the three set, so
                                            * the seven calls below the gate all run */
#define WB_PLAYER_GATE_FRAME_SKIPPED   6u  /* `move.w #$ffff,d7 / rts` at $bb4 (after the shared
                                            * `bsr.w $1f54` at $bb0) or at $d22 (WITHOUT it). TWO
                                            * PATHS REACH $d22 AND ONLY ONE IS A BRANCH: the
                                            * `bne.w` at $c86, the align arm's slot refusal — which
                                            * is the asymmetry against the second arm's $c3e, where
                                            * the same refusal goes to the shared tail — and the
                                            * FALL-THROUGH from the $e1be raise at $d1a */
/* ...and the gate's THIRD unwind has no WB_PLAYER_GATE_* name of its own, because it is not a
 * second exit but the SAME instruction: the `bra.w $1622` at $d16 branches into
 * `player_run_map_cell`'s own `lea 12(a7),a7 / jmp $e5ba.l`, with no call and no code of that
 * routine run, so the gate reaches the identical triple pop and reports the identical
 * WB_PLAYER_COLLIDE_UNWIND above. */
#define WB_PLAYER_GATE_DATADISK_UNWIND 7u  /* `lea 4(a7),a7 / jmp $e494.l` at $bd8: ONE return
                                            * address discarded, into show_data_disk_prompt */
#define WB_PLAYER_GATE_RESTART_UNWIND  8u  /* `lea 4(a7),a7 / jmp $e5ba.l` at $c1c: one again, into
                                            * the level-entry band. THREE instructions above that
                                            * pop — not one — is $c06, the image's ONE absolute-LONG
                                            * write of WB_EFFECT_STATE_21E4: losing a life costs the
                                            * armour. The arm's tail runs $c06 (the armour), $c0e
                                            * (WB_LEVEL_SEQ_INDEX back one), $c14
                                            * (WB_LIFE_RESTART_ENTRY_C26 up) and then the pop */
#define WB_PLAYER_FRAME_SOUND_EXTEND  10u  /* `actor_behavior_type01_player`'s own, and the one
                                            * report that is not a transfer: the frame reached $a4a
                                            * carrying an X that `snd_trigger_effect` or
                                            * `snd_play_song` left and this port has not read, so it
                                            * stops rather than hand `player_weapon_fire`'s `sbcd` a
                                            * guessed bit. It fires only when the death check took a
                                            * sound arm AND `player_gate_on_1516` took the LADDER
                                            * arm, which is the one combination that lets the bit
                                            * survive; a jumping frame overwrites it and runs whole */
#define WB_PLAYER_GATE_SCENE_LEFT      9u  /* `bsr.w $19ac` at $c66 did not come back.
                                            * `scene_spawn_from_script` has three endings of its own
                                            * (scene.h) and none of them is this routine's to
                                            * describe, so the gate says only that the call left and
                                            * the case's own `stop_pc` names WHICH — everything
                                            * below the `bsr` on that arm is then unreached */
uint32_t player_pending_event_gate(uint8_t *image, uint32_t actor);

/* $a38 — THE FRAME TOP, slot 1 of WB_ACTOR_BEHAVIOR_TABLE, and the sixty-second row to go live
 * (batch 41 phase F). Nine calls, a register test on the gate's answer and two memory guards; the
 * body's plate in src/player.c is where each is, and why the routine is in that file rather than
 * beside the other sixty-one.
 *
 * `entry_extend` IS `actor_dispatch_behavior`'s OWN X — bit 14 of the type word, which `lsl.w #2,d1`
 * at $92e shifts out THREE instructions above the `jmp (a1)` that is this routine's only entrance
 * (`lea` and `movea.l` are all that sit between them).
 * On the game's own data the player's record holds type 1, so the bit is 0; the SET direction is the
 * dispatcher's documented type ALIASING ($4001 and $c001 scale to the same slot), which is the
 * original's behaviour and not a fabricated input.
 *
 * THE CLAIM IS SCOPED TO THE ARMS WHERE `player_meter_empty_check` IS SILENT. Two of that routine's
 * four paths end in a sound call and leave a bit no reader of this port has, and on those the X at
 * $a46 is the sound routine's rather than the dispatcher's. The frame REFUSES there rather than
 * guess — WB_PLAYER_FRAME_SOUND_EXTEND — and only when the gate's ladder arm would let the bit
 * survive; a jumping frame overwrites it and runs whole.
 *
 * IT RETURNS ITS CALLEE'S REPORT VERBATIM, out of the shared number space at the head of the
 * WB_PLAYER_COLLIDE_* block above, and WB_ACTOR_DISPATCH_RAN for its own `rts`. */
uint32_t actor_behavior_type01_player(uint8_t *image, uint32_t actor, unsigned entry_extend);

#endif /* WONDERBOY_PLAYER_H */
