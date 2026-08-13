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
 * INHERITS through `rng_next`, and `actor_tick_timer30` below does reach it — so that routine
 * carries rng.h's T3-DATA false green with it. The generator's entropy term is `$ff8209 ^ tick` and
 * `$ff8209` is off-image, so both cores are served the frame tick alone; the relaunch this tier
 * gates on one bit of that word is therefore pinned as a FUNCTION OF THE TICK, not as randomness.
 */
#ifndef WONDERBOY_BEHAVIOR_H
#define WONDERBOY_BEHAVIOR_H

#include <stdint.h>

/* --- the walk and the dispatch ($8d0, $928) -----------------------------------------------------
 *
 * THE BOUNDARY, and why it is a returned ADDRESS. Sixty of the sixty-two slots are unported, so
 * there is nothing for the C to call; what it does instead is FETCH the target out of the image
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
 * — slots 59 and 8 fall into slot 7's body, slot 53 calls a player-tier routine whose one arm
 * enters WB_PLAYER_STEP_BODY, and slot 61 ends its sequence with `jmp $e494.l` — so a handler now
 * answers the same question the dispatcher does: WB_ACTOR_DISPATCH_RAN when it ran to its own
 * `rts`, or the address at which the original left code this file can follow. The dispatcher and
 * the walk pass whatever it says straight up, so nothing else in the mechanism moves.
 *
 * ONE OF THE FOUR IS A BOUNDARY THE ORIGINAL RETURNS FROM, and the code cannot say so. Slots 59, 8
 * and 61 never come back — two run into another handler's body and the third throws its stack away.
 * Slot 53's does: `bsr.w $d78` leaves a return address, so when WB_PLAYER_STEP_BODY finishes the
 * original resumes inside slot 53, publishes its sprite, counts its timer down and lets the walk go
 * on to the next record. This port stops there instead, so a pass with a live type-53 record and
 * WB_TILE_33_MODE clear reports a boundary where the original would have run every record behind
 * it. That is the port's limit, not the original's; the batch that reconstructs $e06 removes it by
 * calling it and resuming, and the resume point is $5c32. */
#define WB_ACTOR_DISPATCH_RAN     0u   /* a reconstructed handler ran to its own `rts` */
#define WB_ACTOR_DISPATCH_REFUSED 1u   /* the scaled type left the table: the original `jmp`s through
                                        * a longword outside it and no C stands in for that */
#define WB_ACTOR_DISPATCH_UNBOUNDED 2u /* THE WALK's own, and this port's alone: a table with no
                                        * terminator, which the original runs for ever. It is a
                                        * separate code from the refusal above because the two mean
                                        * different things and a case that confused them would pin
                                        * neither */

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
 * lives. Slot 53's frame passes through `player_gate_on_1516`, so it can end at a BOUNDARY. */
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

/* $d78 — the twelve bytes slot 53 calls, and the only player-tier code in this file. Returns
 * WB_ACTOR_DISPATCH_RAN while WB_TILE_33_MODE is set (the original returns having written nothing)
 * and WB_PLAYER_STEP_BODY while it is clear, which is where the original branches. */
uint32_t player_gate_on_1516(const uint8_t *image);

#endif /* WONDERBOY_BEHAVIOR_H */
