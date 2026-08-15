/* behavior.h — the per-actor BEHAVIOUR tier's foundation: the walk that runs it ($8d0), the
 * dispatcher that is its whole entry mechanism ($928), the spawn animation twenty-five handlers
 * open by branching into ($698a), the thirteen shared leaves they call, and the two tests forty-two
 * and twenty-five of them run every frame ($5c6e, $23b6).
 *
 * WHY THIS IS A FILE OF ITS OWN. PORTABILITY.md §0k measured it: `actor_dispatch_behavior` reads
 * WB_ACTOR_TYPE out of the record, scales it `lsl.w #2` and tail-jumps through a 62-longword table
 * whose base — WB_ACTOR_BEHAVIOR_TABLE — appears nowhere in the image as an operand, because it is
 * the 8-bit displacement of a PC-relative INDEXED extension word. Ghidra follows a plain `lea
 * abs.l` and not that one, so the table and all 61 of its targets were invisible, and with them
 * 18,068 bytes: a third of the program. This file is the bottom of what was behind it. The 61
 * handlers themselves are not here — 59 of the 62 slots are still unported, and the dispatcher's
 * BOUNDARY below is how that is stated rather than hidden.
 *
 * EVERY ROUTINE HERE TAKES 68000 REGISTERS, the convention actor.h sets: a record address in a0, a
 * step in d7, a frame list in a1, a band record in a2. Two hand a register BACK — $5c6e's overlap
 * mask and $23b6's verdict are its d0 and d7 and are read by every one of their callers — and one
 * hands back an address ($6d5a's tail jump leaves the followed record in a1). Everything else
 * writes only the image.
 *
 * NOTHING HERE TOUCHES HARDWARE DIRECTLY. §0k checked it across all 123 functions the wall hid: the
 * scan's hardware table is byte-identical before and after. The tier's only hardware is what it
 * INHERITS through `rng_next`, and `actor_tick_timer30` below does reach it. The generator's entropy
 * term is `$ff8209 ^ tick`, and `$ff8209` is a MODELED hardware byte since the kit's Phase 7 table
 * grew the shifter's video counter: src/rng.c reads it through `hw_read8`, a case DECLARES what it
 * held, and an undeclared read refuses the differential — so rng.h's T3-DATA false green is retired
 * here too. The relaunch this tier gates on one bit of that word is pinned against a counter byte
 * the case states, not against a fabricated 0 both cores were handed.
 */
#ifndef WONDERBOY_BEHAVIOR_H
#define WONDERBOY_BEHAVIOR_H

#include <stdint.h>

/* --- the walk and the dispatch ($8d0, $928) -----------------------------------------------------
 *
 * THE BOUNDARY, and why it is a returned ADDRESS. TEN of the sixty-two slots are unported (sixty
 * were when this was written, and the mechanism has not moved since), so for those there is nothing
 * for the C to call; what it does instead is FETCH the target out of the image
 * exactly as `movea.l (a1),a1` does and hand it back, and the differential runs the ORACLE on with
 * `stop_pc` at that same address plus a coverage witness that the `jmp (a1)` at $936 really fired.
 * That is batch 19's shape and batch 22's, made table-driven: a later batch adds one row to
 * src/behavior.c's list of reconstructed targets and nothing in the mechanism moves.
 *
 * The three values below are what the C returns when there is no address to report. All three are
 * chosen so no table entry can collide with them — test/test_behavior.py checks that against the
 * image's own 62 longwords rather than assuming it.
 *
 * A HANDLER REPORTS A BOUNDARY TOO, which is why every one of them below returns a `uint32_t`
 * rather than nothing. Batch 29's boundary was the dispatcher's alone: a slot was ported or it was
 * not. Batch 31 ported three handlers that leave their own bodies for code this port does not have
 * — slots 59 and 8 fall into slot 7's body, slot 53 called a player-tier routine whose one arm
 * entered WB_PLAYER_STEP_BODY, and slot 61 ends its sequence with `jmp $e494.l` — so a handler now
 * answers the same question the dispatcher does: WB_ACTOR_DISPATCH_RAN when it ran to its own
 * `rts`, or the address at which the original left code this file can follow. The dispatcher and
 * the walk pass whatever it says straight up, so nothing else in the mechanism moves.
 *
 * THE PLAYER-GATE BOUNDARY IS GONE AS OF BATCH 40, and it was the only one of the four that the
 * ORIGINAL RETURNED FROM. `bsr.w $d78` leaves a return address, so when WB_PLAYER_STEP_BODY
 * finished the original resumed inside slot 53, published its sprite, counted its timer down and
 * let the walk go on to the next record — and this port used to stop there instead, which made a
 * pass with a live type-53 record and WB_TILE_33_MODE clear report a boundary where the original
 * had run every record behind it. src/player.c reconstructs $e06, `player_gate_on_1516` CALLS it,
 * and the five handlers that met that edge (53, and 9/12/22/26 through `gated_hurt_frame`) run
 * their frames whole. What is left is slots 59, 8 and 61, none of which ever comes back. */
#define WB_ACTOR_DISPATCH_RAN     0u   /* a reconstructed handler ran to its own `rts` */
#define WB_ACTOR_DISPATCH_REFUSED 1u   /* the scaled type left the table: the original `jmp`s through
                                        * a longword outside it and no C stands in for that */
#define WB_ACTOR_DISPATCH_UNBOUNDED 2u /* THE WALK's own, and this port's alone: a table with no
                                        * terminator, which the original runs for ever. It is a
                                        * separate code from the refusal above because the two mean
                                        * different things and a case that confused them would pin
                                        * neither */
#define WB_ACTOR_DISPATCH_PICKUP_REFUSED 3u
                                       /* SLOT 38's OWN, and a FOURTH code rather than a reuse of
                                        * the first refusal: `jsr (a1)` at $54a4 goes through a
                                        * SECOND table (WB_PICKUP_EFFECT_TABLE), so a case that
                                        * answered `WB_ACTOR_DISPATCH_REFUSED` could not tell a type
                                        * that left the behaviour table from a kind row whose effect
                                        * index left the pickup one — and the two are reached on
                                        * completely different paths.
                                        *
                                        * IT IS OUT OF BAND BY MEASUREMENT, not by hope. The address
                                        * would have been the natural answer (slot 7's state `jsr`
                                        * reports one), but the span this index reads is ordinary
                                        * data and holds zeros, and 0 is WB_ACTOR_DISPATCH_RAN. So
                                        * the answer is a CODE, and test_behavior.py checks all
                                        * fourteen of the image's own longwords against these four
                                        * values rather than assuming none collides. */

/* $8d0 — run one frame of behaviour for every live record of the table WB_ACTOR_TABLE_SELECTED
 * names. No arguments: the cursor comes out of memory. game_main_loop reaches it through $882.
 *
 * Returns WB_ACTOR_DISPATCH_RAN when the walk ran to the original's own `rts`, the entry address of
 * the first handler it dispatched to that this port does not have (at which point the walk STOPS,
 * because the original is now inside code the reconstruction cannot follow),
 * WB_ACTOR_DISPATCH_REFUSED when a record's scaled type left the table, or
 * WB_ACTOR_DISPATCH_UNBOUNDED when the table has no terminator at all. */
uint32_t actor_behavior_pass(uint8_t *image);

/* $928 — the four instructions the whole tier hangs off. `actor` is the original's a0. Returns what
 * `actor_behavior_pass` returns, for the one record. */
uint32_t actor_dispatch_behavior(uint8_t *image, uint32_t actor);

/* $a36 — slots 0 and 58 of WB_ACTOR_BEHAVIOR_TABLE: a bare `rts`, which is also the two bytes that
 * BOUND the table from above. It is a reconstruction like any other, and it is what makes the walk
 * itself testable: a table of type-0 records runs the pass end to end in both cores. */
uint32_t actor_behavior_null(uint8_t *image, uint32_t actor);

/* --- the animation every spawned record plays ($698a) -------------------------------------------
 *
 * TWENTY-FIVE `bne.w $698a` SITES AND NO CALL. It is a shared TAIL, branched into from the handlers'
 * first instruction pair (`btst #2,9(a0) / bne.w`) and returning to `actor_behavior_pass` through
 * their frame — the $1a5d8/$17c72 class, entered at its own address by a battery of its own. */

/* $698a — step `actor`'s WB_ACTOR_FIELD_18 cursor one word through WB_ACTOR_SPAWN_ANIM_FRAMES,
 * publishing each frame as its WB_ACTOR_SPRITE; on the wrap, lower WB_ACTOR_FLAGS2_SPAWNED_BIT and
 * zero the cursor, which is what releases the record to its real handler. */
void actor_spawn_anim_step(uint8_t *image, uint32_t actor);

/* --- the shared leaves ---------------------------------------------------------------------------
 *
 * `step` is the original's d7 throughout — the pixel count the two map probes take — and the
 * routines that take one are called with it already loaded by the handler.
 */

/* $2f22 — step `actor` the way WB_ACTOR_FLAG_SIDE_BIT faces (set = LEFT, i.e. toward the followed
 * record) and FLIP that bit when the step came back blocked. Two `bsr` callers. */
void actor_step_facing(uint8_t *image, uint32_t actor, uint32_t step);

/* $2f86 — count WB_ACTOR_FIELD_30 down; on the frame it reaches zero, reload it and — if the record
 * is SUPPORTED and `rng_next` says so — relaunch it. Two `bsr` callers. */
void actor_tick_timer30(uint8_t *image, uint32_t actor);

/* $2fce — face the followed record, then step TOWARD it by `step`. Two `bsr` callers. */
void actor_face_and_step_toward(uint8_t *image, uint32_t actor, uint32_t step);

/* $2fe8 — face the followed record, then step AWAY from it by WB_ACTOR_STEP_AWAY_PIXELS. It is NOT
 * $2fce with a different d7: the two arms of the `btst` are the other way round, which is the whole
 * difference between the two bodies. Four `bsr` callers. */
void actor_face_and_step_away4(uint8_t *image, uint32_t actor);

/* $3006 — `list_pair` (the original's a1) is TWO longwords, a frame list per facing;
 * WB_ACTOR_FLAG_SIDE_BIT picks one. Publish the frame the cursor names, then advance the cursor —
 * or zero it when the NEXT word is negative. Fourteen `bsr` callers, the busiest leaf here. */
void actor_anim_step_facing_list(uint8_t *image, uint32_t actor, uint32_t list_pair);

/* $4fea — publish one of three sprite ids by WB_ACTOR_FLAG_SUPPORTED_BIT then
 * WB_ACTOR_FLAG_MOVING_BIT. Two callers. */
void actor_select_sprite_by_flag(uint8_t *image, uint32_t actor);

/* $5a3c — publish the word at `frame` (a1) and advance `cursor` (d0) two bytes with a 16-byte wrap.
 * Eighteen bytes with no reads of its own beyond the record: both its registers are the caller's,
 * and the wrapped cursor comes back in d0 because $5a10 `tst.b`s it. Two `bsr` callers. */
uint32_t actor_advance_anim16(uint8_t *image, uint32_t actor, uint32_t frame, uint32_t cursor);

/* $6840 — move `actor` `step` pixels toward the followed record in BOTH axes, at a ride height of
 * WB_ACTOR_PLATFORM_TOP above its y. It touches no flag byte at all. One `bsr` caller. */
void actor_step_toward_followed(uint8_t *image, uint32_t actor, uint32_t step);

/* $6872 — the WB_ACTOR_ANIM_5160_FRAMES stepper, with a relaunch in front of it: a SUPPORTED record
 * whose WB_ACTOR_FIELD_30 countdown has not reached WB_ACTOR_ANIM_5160_HOLD is ticked, and on the
 * tick that reaches it the countdown becomes the record's WB_ACTOR_SPEED and it is launched. Two
 * callers. */
void actor_relaunch_and_anim_5160(uint8_t *image, uint32_t actor);

/* $6d5a — publish the sprite WB_ACTOR_SPRITE_TABLE_6ED8 holds for `actor`'s WB_ACTOR_HALF_WIDTH,
 * then `bra.w` INTO followed_actor_record, so the followed record comes back in a1 and is this
 * routine's result too. Three callers. */
uint32_t actor_sprite_from_6ed8(uint8_t *image, uint32_t actor);

/* $6d70 / $6dd8 — the moving platform. `followed` is the original's a1 and `band` its a2, a record
 * whose WB_ACTOR_BAND_LEFT and WB_ACTOR_BAND_WIDTH words the caller supplies. The first CATCHES the
 * followed record onto the platform's top and stops it falling; the second lets it go again when it
 * has left the band or started moving under its own power. Three callers each. */
void actor_platform_carry_followed(uint8_t *image, uint32_t actor, uint32_t followed,
                                   uint32_t band);
void actor_platform_release_check(uint8_t *image, uint32_t actor, uint32_t followed, uint32_t band);

/* $701c — set WB_ACTOR_FLAG_SIDE_BIT from the followed record's x with the OPPOSITE polarity to
 * actor_set_side_flag's ($67c2 raises it while the followed record is to the LEFT; this raises it
 * while the followed record is to the RIGHT), then force a nonzero WB_ACTOR_FIELD_22 to
 * WB_ACTOR_FIELD_22_HOLD. Two callers. */
void actor_face_followed_reset_22(uint8_t *image, uint32_t actor);

/* --- the two tests the handlers run every frame ($5c6e, $23b6) ----------------------------------- */

/* $5c6e — how `actor`'s box overlaps the followed record's, as three independent bits in d0:
 * WB_ACTOR_OVERLAP_STRIKE_BIT, _BODY_BIT and _POINT_BIT. Two of the three are live only for a band
 * of followed SPRITE ids, so what the player's current animation frame is decides which tests run
 * at all. FORTY-TWO `bsr` callers — thirty read bit 1 and twelve read bit 0, and nothing in the
 * image reads bit 2 on its own. */
uint32_t actor_followed_overlap_mask(uint8_t *image, uint32_t actor);

/* $23b6 — WB_ACTOR_HIT when something the player threw has landed on `actor` this frame, else
 * WB_ACTOR_NOT_HIT, in d7. Two ways in: WB_FLASH_TIMER running with the followed record within
 * WB_ACTOR_FLASH_REACH, or a record of WB_ACTOR_SHOT_TYPE_LO..HI in the HIGH allocation pool whose
 * footprint overlaps this one — which is CONSUMED on the way past, freed outright unless it is
 * WB_ACTOR_SHOT_TYPE_KEPT. Twenty-five `bsr` callers, all of them `tst.w d7 / bne.w` into their own
 * damage arm. */
uint32_t actor_hit_by_player_shot(uint8_t *image, uint32_t actor);

/* $501a — while WB_ACTOR_FLAG_MOVING_BIT is up, lift `actor` by its own WB_ACTOR_SPEED and then
 * lower that speed by one, ending the rise when it runs out. Thirty-six `bsr` callers, which is more
 * than any other leaf in this file. */
void actor_hop_ascend_step(uint8_t *image, uint32_t actor);

/* --- the two shared routines the handlers below needed ------------------------------------------ */

/* $6786 — SIXTEEN BYTES: `move.w #$9,d0 / clr.w d1 / lea $17adc.l,a1 / jmp 56(a1)`, i.e.
 * actor_stun_followed's own opening with WB_ACTOR_REQUEST9_SFX and a `jmp` where that one has a
 * `jsr` — the stub's `rts` returns to THIS routine's caller. Declared here rather than in sound.h
 * because it lives in the behaviour tier's address range and all FIVE of its callers are dispatch
 * rows ($4e4e, $4ee0, $4fca, $506c, $5214 — slots 28, 30, 31, 32 and 33). */
void sound_request_9(uint8_t *image);

/* $6796 — fire WB_ACTOR_STUN_SFX and stamp WB_ACTOR_STUN_STEPS_BASE minus twice
 * WB_EFFECT_STATE_BD68 into the FOLLOWED record's WB_ACTOR_FIELD_29, clearing its
 * WB_ACTOR_FIELD_22. It takes no register at all — the record it writes is `followed_actor_record`'s
 * — and eleven handlers reach it, in slots 39..45, 51..53 and 57. */
void actor_stun_followed(uint8_t *image);

/* $6e8c — `actor` is the platform (a0) and `followed` the record riding it (a1). If the cell that
 * record stands in or the one beside it is WB_MAP_TILE_BLOCK or WB_MAP_TILE_LEDGE, lift the record
 * WB_ACTOR_PLATFORM_STEP pixels back out, clear WB_ACTOR_PLATFORM_RIDDEN and lower the platform's
 * WB_ACTOR_FIELD_22_RIDING_BIT. Two callers, slots 54 and 56, both on their DOWNWARD frames. */
void actor_platform_release_blocked_rider(uint8_t *image, uint32_t actor, uint32_t followed);

/* --- the first ten handlers of the sixty-one ---------------------------------------------------
 *
 * EVERY ONE OF THESE IS A TABLE SLOT, reached only through `actor_dispatch_behavior`'s `jmp (a1)`
 * and never by a call, so each takes exactly the record in a0 and returns nothing: what a handler
 * does is memory. The names are the SLOT and the structure, not the creature — which sprite each
 * draws still wants a cross-reference (../STATUS.md).
 *
 * THE FIVE IN THE $2462..$2db1 BAND ARE ONE SHAPE. Spawn gate, contact test, per-monster move,
 * frame published from a word table inside the handler's own extent, and a death animation on bit 0
 * of WB_ACTOR_FLAGS2 that ends in actor_defeat_and_score. What differs is the move — and slots 3
 * and 6 differ from each other only in that one throws.
 */
uint32_t actor_behavior_type02(uint8_t *image, uint32_t actor);   /* faces the player, never steps */
uint32_t actor_behavior_type03(uint8_t *image, uint32_t actor);   /* patrols, turning two ways */
uint32_t actor_behavior_type04(uint8_t *image, uint32_t actor);   /* hovers on a 64-word delta table */
uint32_t actor_behavior_type05(uint8_t *image, uint32_t actor);   /* hops when the ground says to */
uint32_t actor_behavior_type06(uint8_t *image, uint32_t actor);   /* charges, then THROWS */

/* $5928 / $5972 / $59d0 — the $5a band's other three, and NONE of them has a spawn gate or a
 * contact test either. Slot 47 is pure animation: sixteen frames over WB_ACTOR_FIELD_18 and the
 * slot handed back when the cursor wraps. Slots 48 and 49 open with the same forty-two bytes —
 * actor_fall_and_settle, actor_hop_ascend_step and actor_step_facing's own body inline — and part
 * only in what they animate: 48 plays four frames and counts WB_ACTOR_FIELD_30 down like slot 50,
 * while 49 plays TWO tables over one cursor with WB_ACTOR_FIELD_31 as the phase. */
uint32_t actor_behavior_type47(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type48(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type49(uint8_t *image, uint32_t actor);

/* $5a6e — no spawn gate and no contact test: it drifts WB_ACTOR_TYPE50_STEP pixels a frame the way
 * WB_ACTOR_FLAG_SIDE_BIT points, plays two frames, and frees its own slot on a countdown. */
uint32_t actor_behavior_type50(uint8_t *image, uint32_t actor);

/* $5ab2 — walks until something stops it. Bit 0 of WB_ACTOR_FLAGS2 is a one-way switch rather than
 * a death animation: a strike, a body overlap or a blocked step all raise it, and from then on the
 * record only falls — freeing its slot the frame it is supported again. */
uint32_t actor_behavior_type51(uint8_t *image, uint32_t actor);

/* $6e1c / $6ef4 / $6f3e — the three MOVING PLATFORMS, and one geometry: a0's WB_ACTOR_HALF_WIDTH
 * picks an eight-byte WB_ACTOR_SPRITE_TABLE_6ED8 row whose first word is the sprite and whose next
 * two are the band $6d70/$6dd8 catch and release against. 54 travels vertically and 55 horizontally
 * between WB_ACTOR_FIELD_24 and WB_ACTOR_SIZE_SECOND; 56 has no limit at all and simply sinks while
 * it is stood on and rises when it is not. */
uint32_t actor_behavior_type54(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type55(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type56(uint8_t *image, uint32_t actor);

/* --- slot 51's two neighbours, and the four rows above the platforms ---------------------------
 *
 * $5b3c / $5be4 — ONE GRAMMAR WITH SLOT 51: bit 0 of WB_ACTOR_FLAGS2 as a one-way switch, then the
 * overlap mask's strike and body bits in that order, then the move. Where slot 51 falls until it is
 * supported, slot 52 walks by its own WB_ACTOR_FIELD_30 and frees itself the frame it IS supported,
 * and slot 53 slides a fixed step, counts a timer down and publishes WB_ACTOR_TYPE53_ALIVE while it
 * lives. Slot 53's frame passes through `player_gate_on_1516`, which through batch 39 could end
 * it at a BOUNDARY and since batch 40 runs the jump machine behind it instead. */
uint32_t actor_behavior_type52(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type53(uint8_t *image, uint32_t actor);

/* $6f7e — no movement at all: it publishes WB_ACTOR_SPRITE_NONE and waits for WB_STATE_WORD_6F9C,
 * then consumes that word and RETYPES itself into slot 54, the vertical moving platform. */
uint32_t actor_behavior_type60(uint8_t *image, uint32_t actor);

/* $6f9e — not a creature: the four-message sequence the copylock failure path also `jsr`s into. It
 * starts a song, posts one message per FIRE edge out of WB_ACTOR_TYPE61_MESSAGES, and when the
 * table's terminator comes up transfers to WB_SHOW_DATA_DISK_PROMPT — a boundary, never a return. */
uint32_t actor_behavior_type61(uint8_t *image, uint32_t actor);

/* --- slot 7 ($7060) and the SWOOP state machine ($72c2..$73cd) ----------------------------------
 *
 * THE ONLY HANDLER IN THE TABLE WITH THREE ENTRANCES. Slot 7's own row enters with neither bit of
 * WB_ACTOR_FIELD_30 raised; the two prologues below raise one each and run into the same body, so
 * WB_ACTOR_TYPE08_MARK_BIT and WB_ACTOR_TYPE59_MARK_BIT are how the body knows which row fired.
 *
 * The body is a monster prologue (spawn gate, the shot/overlap contact pair, the damage and defeat
 * exits), a sprite — either a marked record's constant pair or one of four twelve-word lists — and
 * then a `jsr` through WB_ACTOR_SWOOP_STATE_TABLE on WB_ACTOR_FIELD_22. Above the state it hangs
 * two spawners on the same WB_ACTOR_FIELD_31 cursor: a FIVE-SHOT burst every
 * WB_ACTOR_TYPE07_BURST_MASK frames and a single dropper every WB_ACTOR_TYPE07_DROP_MASK.
 *
 * The four states are one machine over WB_ACTOR_FIELD_22, and each is reached ONLY through that
 * `jsr` — the table is their sole reference in the image. `actor` is a0 throughout; none takes a
 * second argument and none returns a value the caller reads.
 */
void actor_swoop_state0_acquire(uint8_t *image, uint32_t actor);
void actor_swoop_state1_run_path(uint8_t *image, uint32_t actor);
void actor_swoop_state2_home_x(uint8_t *image, uint32_t actor);
void actor_swoop_state3_descend(uint8_t *image, uint32_t actor);

/* $7060 — slot 7's body. Returns WB_ACTOR_DISPATCH_RAN, or the address the `jsr (a1)` at $713a
 * would have entered when WB_ACTOR_FIELD_22 names no reconstructed state: the byte is UNBOUNDED
 * (`move.b 22(a0),d0 / lsl.w #2 / movea.l 0(a1,d0.w),a1`), so a state above 3 reads a longword past
 * the four-entry table and calls it, exactly as actor_dispatch_behavior's refusal does. */
uint32_t actor_behavior_type07(uint8_t *image, uint32_t actor);

/* $7044 / $705a — twenty-two bytes and six: each raises its own bit of WB_ACTOR_FIELD_30 and then
 * runs into WB_ACTOR_BEHAVIOR_TYPE07's body. Batch 32 reconstructed that body, so both now RUN ON
 * into it and report whatever it reports; through batch 31 both stopped there as a boundary. */
uint32_t actor_behavior_type59(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type08(uint8_t *image, uint32_t actor);

/* --- slots 28, 30 and 31, and the payout cluster at $517a..$5207 --------------------------------
 *
 * THREE COLLECTABLES, not creatures. None has a spawn gate; each asks `actor_followed_overlap_mask`
 * for bit 1 alone, fires WB_ACTOR_REQUEST9_SFX when it gets it, and hands its own slot back. What
 * each pays differs, and so does what it does while it waits: slot 28 falls, hops and walks by
 * WB_ACTOR_FIELD_31 pixels, slot 30 drifts along a signed table, slot 31 only falls.
 *
 * ALL THREE FLICKER OUT, and they do NOT all stop the same way. WB_ACTOR_FLAG_FLICKER_BIT goes up
 * as WB_ACTOR_FIELD_12 runs down, so a collectable that is not picked up blinks before it
 * disappears. Slots 30 and 31 count that field as a WORD and `bclr` the bit on the frame they free
 * themselves; slot 28 counts it as a BYTE, expires TWICE — the first expiry `bset`s the bit and
 * reloads WB_ACTOR_TYPE28_FIELD_12_RELOAD, the second frees the slot — and never clears it at all,
 * so a freed type-28 record's flag byte keeps bit 6 set.
 */

/* $4e38 — 144 bytes. Collected: WB_ACTOR_TYPE28_GOLD into WB_BCD_COUNTER and
 * WB_ACTOR_COLLECT_SCORE into WB_BCD_SCORE. Waiting: actor_fall_and_settle, actor_hop_ascend_step,
 * actor_relaunch_and_anim_5160 and a step of WB_ACTOR_FIELD_31 pixels, skipped while that byte is
 * zero. Its turn test is the ONE `tst.w d0` in the tier where every other blocked-step test is a
 * `tst.b` — see src/behavior.c. */
uint32_t actor_behavior_type28(uint8_t *image, uint32_t actor);

/* $4eca — 142 bytes. Collected (and only once WB_ACTOR_FIELD_30 has counted up to
 * WB_ACTOR_TYPE30_COLLECT_MIN): WB_HUD_METER_VALUE topped up to WB_HUD_METER_MAX — but only when
 * adding WB_ACTOR_TYPE30_METER_STEP would REACH the maximum, which is a shipped bug src/behavior.c
 * reproduces. Waiting: WB_ACTOR_TYPE30_DRIFT added to its x one word a frame off a GLOBAL cursor,
 * and a one-pixel rise on the frames WB_FRAME_TOGGLE is nonzero. */
uint32_t actor_behavior_type30(uint8_t *image, uint32_t actor);

/* $4f9c — 78 bytes with TWO exits: its own `rts` at $4fe8, which the collect and free arms reach,
 * and a `bne.w $4fea` into actor_select_sprite_by_flag, which the live-countdown arm takes and
 * whose `rts` returns to the dispatcher. That routine's entry is what bounds the handler.
 * Collected: `hud_award_gold_from_descriptor` below. Waiting: it falls, ascends and picks one of
 * three sprites from two flag bits. */
uint32_t actor_behavior_type31(uint8_t *image, uint32_t actor);

/* $517a — 50 bytes. WHAT A COLLECTED SLOT-31 (or slot-32) RECORD IS WORTH: the packed-BCD
 * WB_SCENE_GOLD_AWARD out of the descriptor WB_RECORD_PTR_10424 names, jittered by
 * `bcd_add_random_1_to_4`, added to WB_BCD_COUNTER, written into message
 * WB_TEXT_MESSAGE_GOLD_GET's own string, and then WB_ACTOR_COLLECT_SCORE added to WB_BCD_SCORE and
 * the message posted. Two `bsr` callers, $4fce and $5070. */
void hud_award_gold_from_descriptor(uint8_t *image);

/* $51ac — 44 bytes, and NOT the mask ../names.txt used to call it: it ends in `abcd d1,d0`, so a
 * draw of one to four is added to the caller's d0 IN PACKED BCD and d0 is the result. The draw is
 * `($ff8209 + $ff8207 + WB_ACTOR_FOLLOWED_DEFAULT's two bytes) & WB_BCD_RANDOM_MASK, plus one`, so
 * its only machine entropy is the shifter's video-address counter — a DECLARED hardware pair since
 * batch 33, read once each, in that order. `entry_d0` is the caller's whole d0 and only its low
 * BYTE is written. Two `bsr` callers, $5184 and $544c.
 *
 * `exit_extend` is the SECOND output and the reason this routine has one: the `abcd` at $51d4 is
 * the last instruction before the `rts`, so the carry it leaves is still in X when $5188's counter
 * add folds it into the gold counter's lowest digit (include/hud.h's chain). The bit this routine
 * folds IN is its own — `addq.b #1,d1` on a byte masked to 0..3 always clears X — which is why
 * there is no entry parameter to match. */
uint32_t bcd_add_random_1_to_4(const uint8_t *image, uint32_t entry_d0, unsigned *exit_extend);

/* $51d8 — 48 bytes. The packed-BCD BYTE in `entry_d0` drawn as the two characters at
 * WB_TEXT_GOLD_DIGITS, tens first: a zero tens digit is blanked to WB_TEXT_DIGIT_BLANK rather than
 * drawn. Only two digits, whatever the rest of d0 holds. ONE `bsr` caller, $518c. */
void text_write_gold_digits_a2ac(uint8_t *image, uint32_t entry_d0);

/* --- slots 32..37 ($5046..$5407): the rest of the band -------------------------------------------
 *
 * TWO COLLECTABLES AND FOUR SCENE ACTORS, and with them the band $4e38..$5407 runs whole. Slots 32
 * and 33 share the three above's shape — the footprint bit, WB_ACTOR_REQUEST9_SFX, the flicker as
 * WB_ACTOR_FIELD_12 runs down and WB_ACTOR_FREE_MARKER at the end — and pay two more currencies.
 * Slots 34..37 have no contact test, no countdown and no free marker at all: 34 is the shop's item
 * cursor and 35..37 are the actors `player_pending_event_gate` ($b1a) spawns and waits on.
 */

/* $5046 — 278 bytes. Collected: `hud_award_gold_from_descriptor`, slot 31's payout. Waiting: it
 * falls, ascends, and runs a HOP MACHINE on WB_ACTOR_FIELD_10 — one hop per landing, each at the
 * countdown's own value, so they shorten — and once it has landed at all it also walks
 * WB_ACTOR_TYPE32_WALK_STEP a frame and turns round on a blocked probe. Its animation is the SECOND
 * of the THREE readers of WB_ACTOR_ANIM_5160_FRAMES, off WB_ACTOR_TYPE32_CURSOR; the third is
 * actor_behavior_type46 ($58f8), which is unported.
 *
 * ALL THREE OF ITS STATE GLOBALS ARE SHARED (WB_ACTOR_TYPE32_WALKING and _HOPS_SPENT are bytes,
 * _CURSOR a word), so two live type-32 records share one hop machine and one animation phase — the
 * tier's second instance of WB_ACTOR_TYPE30_CURSOR's property. Its ending clears the two LATCHES
 * and NOT the cursor, where slot 30's ending does clear its own, so the next type-32 record starts
 * its hop machine over and its animation where the last one left off. */
uint32_t actor_behavior_type32(uint8_t *image, uint32_t actor);

/* $5208 — 82 bytes. Collected: WB_PANEL_FRAME_REWIND and WB_PANEL_FRAME_HOLD raised together plus
 * WB_ACTOR_COLLECT_SCORE, i.e. the panel's own clock wound back — no gold, no meter. It is also the
 * one collectable in the band with NO WB_ACTOR_FLAG_MOVING_BIT gate, so a record mid-hop is taken. */
uint32_t actor_behavior_type33(uint8_t *image, uint32_t actor);

/* $525a — 220 bytes. THE SHOP'S ITEM CURSOR: the record's own WB_ACTOR_X is the selection, the
 * joystick's left/right EDGES walk it between WB_ACTOR_TYPE34_ITEM1_X, _MIDDLE_X and _ITEM2_X
 * posting each item's message, and fire writes WB_SHOP_REQUEST. It runs nothing at all while
 * WB_SCENE_MESSAGE_PENDING or WB_SCENE_ACK_WAIT is up. */
uint32_t actor_behavior_type34(uint8_t *image, uint32_t actor);

/* $5336 / $53bc — 38 bytes each, and ONE animation over ONE global cursor
 * (WB_ACTOR_EVENT_ANIM_CURSOR): sixteen words of WB_ACTOR_EVENT_ANIM_FRAMES, one a frame. On the
 * wrap slot 35 raises WB_EVENT_ANIM_DONE_B12 and slot 36 raises WB_EVENT_ANIM_DONE_B16 and
 * RETYPES ITSELF to slot 0. Neither ever frees its slot. */
uint32_t actor_behavior_type35(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type36(uint8_t *image, uint32_t actor);

/* $53e2 — 38 bytes, slot 36's alternative and the band's last row: no animation, no table. It lifts
 * one pixel a frame until its WB_ACTOR_Y EQUALS the scene descriptor's WB_SCENE_VARIANT word less
 * WB_ACTOR_TYPE37_RISE, and raises WB_EVENT_ANIM_DONE_B16 on the frame it arrives. */
uint32_t actor_behavior_type37(uint8_t *image, uint32_t actor);

/* --- slots 9..13 ($2e12..$35c7): the monster-prologue family opens ------------------------------
 *
 * FIVE MORE BODIES INSIDE SLOTS 2..6's GRAMMAR. Every one of them opens with the spawn gate and the
 * `btst #0,9(a0)` switch and runs the same contact enum, and FOUR of the five end the hurt animation
 * `bclr #0,9(a0) / btst #3,9(a0) / bne.w $6bb8` — the DEFEATED bit only tested, never cleared, where
 * slots 2, 3 and 4 clear it. Slot 13 is the exception and has neither instruction: its hurt arm is a
 * throe that ends `bra.w $6bb8` unconditionally. Where they differ is the middle, and each one
 * differs from every other:
 *
 *   9  walks toward the followed record and then asks actor_random_facing_hop for a new direction
 *  10  never touches the map: a 32-word hover table, a one-pixel drift and a homing turn
 *  11  walks while a countdown runs and DECIDES with one `rng_next` word when it expires
 *  12  faces and chases, hops on actor_tick_timer30, and animates by WB_ACTOR_FLAG_SUPPORTED_BIT
 *  13  hops on every supported frame, and its hurt arm is a throe that ALWAYS ends in the defeat
 *
 * SLOTS 9 AND 12 CALL $d78 ON THEIR HURT ARM and the other three never do. That call REPORTED a
 * boundary through batch 39; since batch 40 it runs WB_PLAYER_STEP_BODY — the player's own jump
 * machine, over the MONSTER's record — and the frame goes on. Slot 53 met the same edge.
 */
uint32_t actor_behavior_type09(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type10(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type11(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type12(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type13(uint8_t *image, uint32_t actor);

/* $2f46 — 64 bytes, ONE `bsr` caller (slot 9). A SUPPORTED record gets a facing off bit 2 of
 * `rng_next`'s word and is then launched at WB_ACTOR_RANDOM_HOP_SPEED unconditionally; an airborne
 * one is left entirely alone. Its `# ctx` plate called it a coin-flip TURN — the launch is the
 * other half of it, and nothing vetoes it. */
void actor_random_facing_hop(uint8_t *image, uint32_t actor);

/* --- slots 14..19 ($35d8..$3ff7): the family's second block -------------------------------------
 *
 * SIX MORE BODIES, and none of them reports a boundary: every callee is reconstructed, so all six
 * run to their own `rts`. What they add to the grammar above is three things.
 *
 *   * THE HURT TAIL COMES IN THREE ORDERS NOW. Slots 14, 17 and 18 lower WB_ACTOR_FLAGS2_BIT_0 and
 *     then TEST the defeated mark; slots 15 and 16 TEST FIRST and lower bit 0 only when the mark is
 *     down, so a record that transfers keeps both; slot 19 transfers unconditionally, as 13 does.
 *   * FIVE OF THE SIX SPAWN a second record from actor_alloc_slot_high, and what a REFUSED
 *     allocation does is each caller's own: four of them end the frame (though slot 14's success
 *     writes one byte more than its refusal) and slot 19 runs ON into its shared publish with a1 at
 *     zero, which is the defect below.
 *   * SLOTS 18 AND 19 SPLIT THE STRUCK ARM: actor_set_side_flag runs on the overlap-POINT arm and
 *     not on the shot's, and their body arm flips the facing before actor_damage_followed — which
 *     is why src/behavior.c's contact enum has a fourth value rather than a flag.
 *
 * What each one is:
 *
 *  14  patrols one pixel a frame, turns on a countdown, and drops a type-$2d record every
 *      WB_ACTOR_TYPE14_SPAWN_GAP walking frames — the drop takes the whole frame
 *  15  steps four pixels toward the followed record and lets actor_turn_and_launch turn AND hop it
 *      whenever the step is blocked or the ground drops away
 *  16  walks, and on a countdown launches itself and lobs a type-$27 record with its own flags
 *  17  never touches the map: two GLOBAL cursors drift it on both axes, and when the y cursor wraps
 *      a one-in-eight draw seeds FIVE type-$34 records numbered 5..1
 *  18  walks, and on a countdown CHARGES: it saves its flag byte into WB_ACTOR_FIELD_29, launches,
 *      spawns a type-$29 record, and restores the byte and turns round when it lands again
 *  19  ALTERNATES: 64 words of x drift under a fixed sprite until that cursor wraps, then an attack
 *      phase that drops a type-$2b record on ONE cursor value until ITS cursor wraps and returns
 *      the record to the glide — neither latch is permanent
 *
 * ONE OF THEM PUBLISHES A GARBAGE FRAME AND IT IS THE ORIGINAL'S. Slot 19's `bsr $1b8e` returns in
 * a1 — the register its frame table was just `lea`d into — and the publish below is reached from
 * both arms, so on the frame the shot fires the sprite comes out of the NEW RECORD (or, on a full
 * pool, out of address $14). Reproduced rather than repaired.
 *
 * AND SLOT 17's BODY IS NOT SLOT 17's ALONE: `bra.w $3ae6` at $48b2 — slot 24's live arm — enters
 * its seeding block, and slot 25's `bne.w $3e2a` at $4aa8 borrows slot 18's `rts`. ../names.txt
 * records both shared spans.
 */
uint32_t actor_behavior_type14(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type15(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type16(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type17(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type18(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type19(uint8_t *image, uint32_t actor);

/* --- dispatch rows 20..27 ($4118..$4dd7): the family CLOSES -------------------------------------
 *
 * The last eight of the same grammar, and five of them are code this port already had:
 *
 *  20  falls, walks two pixels and turns on a blocked step; a SUPPORTED record counts
 *      WB_ACTOR_FIELD_30 down and on the frame the decrement goes negative reloads and, on half the
 *      draws, TAIL-JUMPS into actor_start_motion_at_speed. An airborne one publishes ONE sprite id
 *  21  never falls, hops or steps: it animates until the list wraps, latches
 *      WB_ACTOR_TYPE21_AIMING, and then — in reach and one draw in $20 — fires an AIMED shot whose
 *      velocity pair comes out of $6528's table (actor.h)
 *  22  counts down and LAUNCHES ITSELF with the three bit writes spelt inline; below that it
 *      animates and, while WB_ACTOR_TYPE53_ALIVE is clear and one draw in eight, drops a type-$35
 *  23  the GOLD THIEF: slot 4's flying chase and its death arm exactly, with a footprint arm that
 *      charges WB_ACTOR_TYPE23_STEAL_MAX out of WB_BCD_COUNTER and drops a type-$2e carrying it
 *  24  falls, steps one pixel, animates — and LEAVES for slot 17's seeding block
 *  25  slot 18's charge, one minion type over
 *  26  slot 12's chase with a shot on the arm WB_ACTOR_FLAG_MOVING_BIT picks
 *  27  slot 20's body again, byte for byte, with its own tables
 *
 * FOUR OF THEM SPLIT THE STRUCK ARM (20, 21, 25, 27), which through batch 36 only slots 18 and 19
 * did. Slots 22, 24 and 26 face on BOTH struck arms and slot 23 on neither.
 *
 * TWO OF THEM CARRIED THE FAMILY'S BOUNDARY: slots 22 and 26 share slot 9's `gated_hurt_frame`,
 * whose `bsr $d78` reported WB_PLAYER_STEP_BODY while WB_TILE_33_MODE was clear. Batch 40 retired
 * it — the gate calls the jump machine now and all four of those hurt arms run whole.
 *
 * AND SLOT 23 WRITES OUTSIDE ITS OWN RECORD ON A FULL POOL, as slot 19 does: its
 * WB_ACTOR_TYPE23_STUN_FRAMES store sits below the failed-allocation branch, so the byte lands at
 * offset WB_ACTOR_FIELD_21 of address zero. Reproduced rather than repaired.
 */
uint32_t actor_behavior_type20(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type21(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type22(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type23(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type24(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type25(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type26(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type27(uint8_t *image, uint32_t actor);

/* --- slot 38 ($5408) and the PICKUP TIER (batch 38) ---------------------------------------------
 *
 * A COLLECTABLE WHOSE PAYOUT IS A TABLE LOOKUP, and the first row in this tier whose frame reaches
 * a second dispatch. Its waiting arm is slot 31's — fall, ascend, animate or relaunch, run
 * WB_ACTOR_FIELD_12 down as a BYTE and expire TWICE (slot 28's shape: the first expiry `bset`s
 * WB_ACTOR_FLAG_FLICKER_BIT and reloads, the second finds it already up and leaves for
 * `actor_defeat_and_score`). Its collect arm is what is new:
 *
 *   * WB_ACTOR_KIND below WB_ACTOR_PICKUP_KIND_FIRST — a SIGNED byte compare, so $80..$ff counts as
 *     below — pays GOLD, through the same five calls `hud_award_gold_from_descriptor` makes but
 *     with WB_STAGE_NUMBER as the amount;
 *   * at or above it, the kind's 16-byte row decides: a nonzero WB_ACTOR_KIND_SCORE longword goes
 *     into the score AND into `text_post_bonus_points_a4be`'s five digits, and
 *     WB_ACTOR_KIND_PICKUP_EFFECT then indexes WB_PICKUP_EFFECT_TABLE.
 *
 * Both arms end in `actor_defeat_and_score`, so a collected pickup is retired the way a defeated
 * monster is.
 *
 * IT RETURNS WB_ACTOR_DISPATCH_PICKUP_REFUSED when the effect index leaves the fourteen entries.
 * Nothing bounds that index: the two `add.w`s wrap in sixteen bits and the extension word
 * sign-extends, so 56 of the 65,536 values reach an entry (four aliases each) and the rest read a
 * longword outside the table and `jsr` through it. */
uint32_t actor_behavior_type38_pickup(uint8_t *image, uint32_t actor);

/* $6938 — 82 bytes, and the LONGWORD sibling of `text_write_gold_digits_a2ac`: five packed-BCD
 * digits of `entry_d0` patched into the front of message WB_TEXT_MESSAGE_BONUS_POINTS's own shipped
 * string, leading zeros drawn as spaces, and then that message posted. ONE caller, slot 38's score
 * arm, which is also what keeps it out of a runaway — see src/behavior.c: an addend whose low five
 * nibbles are ALL zero leaves the digit loop counting down from zero, and an addend of zero never
 * leaves the blanking loop at all. The caller's `beq` rules the second out and no shipped kind row
 * reaches the first. */
void text_post_bonus_points_a4be(uint8_t *image, uint32_t entry_d0);

/* --- slots 39..46 and 57 (batch 39): the tier's own AMMUNITION -----------------------------------
 *
 * THE LAST NON-PLAYER ROWS, and what they turn out to be is one fact: each is the record some
 * already-reconstructed handler SPAWNS, one parent each, read off the spawners' own type words
 * rather than guessed — 16->39, 6->40, 18->41, 25->42, 19->43, 21->44, 14->45, 23->46, 7->57 — so
 * the fields each spawner writes are exactly the fields the matching handler reads. It is NOT the
 * whole of what the tier spawns: slots 51, 52 and 53 are spawned rows too, and were reconstructed
 * three batches earlier. wonderboy.h's block carries both halves.
 *
 * ALL NINE ARE CLEAN. Every callee below them was already reconstructed, so no arm here reports a
 * boundary; slot 57's body-contact arm is a `bne.w` INTO `actor_damage_followed` and this port
 * follows it, which is one of the twenty-eight tail jumps that routine's own plate counts.
 *
 * THE GRAMMAR IS THE $5a BAND'S. No spawn gate, no `actor_hit_by_player_shot` — these records
 * cannot be shot down — and the contact test is `actor_followed_overlap_mask`'s bits 0 and 1 with
 * bit 2 unread. What differs per slot is the LATCH: slots 40, 42, 43, 44, 45 and 57 use
 * WB_ACTOR_FLAGS2_BIT_0 as a mode byte, while slots 39 and 41 use WB_ACTOR_FIELD_30 and their own
 * WB_ACTOR_FLAG_SUPPORTED_BIT instead, and slot 46 has no contact test at all.
 *
 * SLOT 41 HAS NO TAIL OF ITS OWN: it `bra.w`s into slot 39's at $5534, which the whole-image branch
 * census confirms is reached from exactly four sites, two in each handler. The two are written here
 * as one body with the sprite id as its parameter.
 */
uint32_t actor_behavior_type39(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type40(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type41(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type42(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type43(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type44(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type45(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type46(uint8_t *image, uint32_t actor);
uint32_t actor_behavior_type57(uint8_t *image, uint32_t actor);

/* $d78 — the twelve bytes slot 53 and `gated_hurt_frame` call, and the only player-tier code in
 * this file. While WB_TILE_33_MODE is set it writes nothing at all; while it is clear it runs
 * `player_jump_step` ($e06, player.h) on `actor`, which is where the original branches. It reports
 * nothing because there is nothing left to report — see the boundary paragraph above. */
void player_gate_on_1516(uint8_t *image, uint32_t actor);

#endif /* WONDERBOY_BEHAVIOR_H */
