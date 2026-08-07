/* actor.h — the followed actor's record, the two tests the game runs against it, the pass that
 * projects actor records into screen coordinates, and the table's own lifecycle (src/actor.c).
 *
 * `followed_actor_record` is the bottom of the tier: fifteen call sites in the image, three of them
 * the routines below. Everything here takes and returns 68000 REGISTERS — a record address in a0, a
 * reach in d0 — because that is the whole interface the originals have; every address is a global
 * named in wonderboy.h, which both languages read. The two `#define`s below are the exception, and
 * they are the same exception scene.h makes: they are not image state at all but the two exits
 * `actor_defeat_and_score` reports for which of its two tails ran, and test/layout.py scrapes this
 * header so that a case names the same two the C does.
 */
#ifndef WONDERBOY_ACTOR_H
#define WONDERBOY_ACTOR_H

#include <stdint.h>

/* $67e0 — the a1 fifteen call sites want: WB_ACTOR_FOLLOWED_A32 while WB_STATE_FLAG_A32 is
 * NONZERO (a `bne`, not the `bpl` $8e66 uses on the same word), else WB_ACTOR_FOLLOWED_DEFAULT. */
uint32_t followed_actor_record(const uint8_t *image);

/* $67c2 — set WB_ACTOR_FLAG_SIDE_BIT in `actor`'s flag byte while the followed actor is to its
 * left, clear it otherwise. `actor` is the original's a0. Thirty-four `bsr` callers. */
void actor_set_side_flag(uint8_t *image, uint32_t actor);

/* $67f8 — 0 while the followed actor is within `reach` of `actor` horizontally, and
 * WB_ACTOR_OUT_OF_REACH beyond it. `reach` is the original's d0 and so is the result: only the low
 * word is written, so the caller's own high half comes back. Five `bsr` callers. */
uint32_t actor_followed_x_within(const uint8_t *image, uint32_t actor, uint32_t reach);

/* $8dfe — refresh screen record WB_ACTOR_FOLLOWED_SLOT (== WB_SCROLL_FOLLOW_X) from the record
 * `followed_actor_record` names, and do nothing at all while WB_STATE_FLAG_A30 is negative.
 * game_main_loop calls it immediately before bg_scroll_run_queue, which reads that record. */
void project_followed_actor(uint8_t *image);

/* $8e66 — publish one of the three actor tables into WB_ACTOR_TABLE_SELECTED and project all
 * WB_ACTOR_SCREEN_RECORD_COUNT of its records. game_main_loop calls it after the scroll has moved
 * and before the sprite pass at $8f02. */
void project_actor_list(uint8_t *image);

/* --- the table's lifecycle ---------------------------------------------------------------------
 *
 * Every address below is the original's a0/a1/a6, so a caller names the table or record it means.
 * None of these returns its walked-out cursor except the two allocators, whose a1 IS the result.
 */

/* $1f36 — mark all WB_ACTOR_SCREEN_RECORD_COUNT records of `table` free and zero everything else in
 * them. Three `bsr` callers and four `jsr $1f36.w` ones. */
void actor_table_reset(uint8_t *image, uint32_t table);

/* $df9e — stamp WB_ACTOR_FREE_MARKER into `count` + 1 records from `first` on, touching no other
 * field. `first` is the original's a6 and `count` its d7, a `dbf` count. Two `bsr` callers. */
void actor_slots_mark_free(uint8_t *image, uint32_t first, uint32_t count);

/* $1b68 / $1b8e — the first free record of each pool of the table WB_ACTOR_TABLE_SELECTED names,
 * or WB_ACTOR_ALLOC_NONE when the pool is full. The original's whole result is a1; of the three
 * `jsr $1b68.w` sites only $101dc tests it against zero, and the two that do not hand it straight
 * to `actor_spawn_from_template`, which writes through it regardless. */
uint32_t actor_alloc_slot_low(const uint8_t *image);
uint32_t actor_alloc_slot_high(const uint8_t *image);

/* $ffe4 — fill `record` (the original's a1, normally an allocator's result) in from the 32-byte
 * `template_record` (its a0). Two `bsr` callers, both inside $ff42. */
void actor_spawn_from_template(uint8_t *image, uint32_t template_record, uint32_t record);

/* $2af2 — clear WB_ACTOR_FLAG_SUPPORTED_BIT, raise the two motion bits and store `speed`'s low byte
 * into WB_ACTOR_SPEED. `speed` is the original's d0. Seven control-flow sites: four `bsr` and three
 * `bra.w` tail jumps. */
void actor_start_motion_at_speed(uint8_t *image, uint32_t actor, uint32_t speed);

/* $14d6 — the fall's per-frame step: unsupported, falling, and one more unit of WB_ACTOR_SPEED
 * until it is exactly WB_ACTOR_FALL_SPEED_MAX. Reached by `bsr` from $13a6 and by `blt.w` from
 * $14c0, inside the routine at $1492. */
void actor_accelerate_fall(uint8_t *image, uint32_t actor);

/* --- the per-frame spawn pass -------------------------------------------------------------------
 *
 * $ff42 is game_main_loop's one call site for all of the above: it counts the template table's
 * countdowns down, and then either spawns the ONE template its cursor names or sweeps the table for
 * every armed one whose countdown has run out. Both arms hand the allocator's result on UNTESTED.
 */

/* $ff42 — no registers: WB_STATE_FLAG_A30, WB_TABLE_PTR_21E8C and the table's own four-word header
 * are all in memory. One caller, game_main_loop's block gated on that flag. */
void actor_spawn_pass(uint8_t *image);

/* $1006a — seed `template_record`'s WB_SPAWN_HITPOINTS from its WB_SPAWN_KILL_COUNT and its type.
 * `template_record` is the original's a0, which is still the template the spawn above just read.
 * Two `bsr` callers, both inside $ff42. */
void actor_template_set_hitpoints(uint8_t *image, uint32_t template_record);

/* --- what an actor does when a map step reports back --------------------------------------------
 *
 * `step_outcome` is the original's d0 and `ground_flags` its d1 — the pair
 * actor_step_left_against_map / actor_step_right_against_map leave behind. Only d0's low BYTE and
 * the three low bits of d1 are read, and all three routines share the `bchg` at $2b7a.
 */

/* $2b5a — blocked with a step up ahead: launch at WB_ACTOR_HOP_SPEED. Blocked without one, or clear
 * with a two-cell drop ahead: flip the side flag. Otherwise nothing. Two `bsr` callers ($2a56,
 * $2a6c), one either side of a `btst #3,8(a0)`; $2b70 is its second arm and not an entry point. */
void actor_hop_or_flip_side(uint8_t *image, uint32_t actor, uint32_t step_outcome,
                            uint32_t ground_flags);

/* $2b82 — flip the side flag when the step was blocked or a ONE-cell drop lies ahead. Ten `bsr`
 * callers. Ghidra records 20 bytes for it; the true extent is 12 plus the shared tail. */
void actor_toggle_side_flag(uint8_t *image, uint32_t actor, uint32_t step_outcome,
                            uint32_t ground_flags);

/* $2b8e — $2b82's test over a longer tail, and only for a SUPPORTED record: flip the side flag and
 * launch at WB_ACTOR_TURN_LAUNCH_SPEED, which is actor_start_motion_at_speed's three writes with
 * the speed spelt inline. Two `bsr` callers ($37c8, $37de); Ghidra has no function here at all. */
void actor_turn_and_launch(uint8_t *image, uint32_t actor, uint32_t step_outcome,
                           uint32_t ground_flags);

/* --- the two damage paths -----------------------------------------------------------------------
 *
 * Both take the original's a0 and nothing else, and both call into src/sound.c — the only routines
 * in this file that leave the actor tier at all. Neither returns anything: what they leave in d0/d1
 * and a1/a2/a5/a6 differs by ARM and is asserted against a model in test/test_actor.py rather than
 * returned, the way the two projections' cursors are.
 */

/* $69fe — pay for a hit ON the followed record: a charge off WB_HUD_SLOT_BBBE (the helmet) if it
 * has one, else WB_ACTOR_DAMAGE_TABLE's word for `attacker`'s type off WB_HUD_METER_VALUE. Then
 * knock the record back, whichever pool paid. A record already carrying
 * WB_ACTOR_FLAGS2_INVULNERABLE_BIT is left completely alone. Thirty-eight control-flow sites: ten
 * `bsr.w` and twenty-eight tail jumps. */
void actor_damage_followed(uint8_t *image, uint32_t attacker);

/* $6b46 — deal one: WB_EFFECT_RECORD_LIST's first byte plus one, DOUBLED while WB_HUD_SLOT_BBC0
 * (the gauntlet) has a charge, off the WB_SPAWN_HITPOINTS pool of `actor`'s own template. On a pool
 * that reaches zero or goes negative, WB_ACTOR_FLAGS2_DEFEATED_BIT goes up on `actor`. Twenty-five
 * control-flow sites: one `bsr.w` ($709a) and twenty-four `bra.w`. */
void actor_damage_template_hitpoints(uint8_t *image, uint32_t actor);

/* --- and what happens when one of them wins ------------------------------------------------------
 *
 * $6bb8 is where a defeated actor is PAID FOR: the score its template's type is worth, the kill
 * counted against that template, the live count lowered, the slot freed and — if the spawn cursor
 * has already been round once — the template re-armed for another one. Above all of that sits one
 * gated block: if the record that died is WB_BOSS_FRAGMENT_ORIGIN while WB_STATE_FLAG_A32 is up,
 * the music stops, WB_BOSS_DEFEAT_FLAG goes up for src/scene.c's fragment arm to find next frame,
 * SFX WB_BOSS_DEFEAT_SFX fires and the meter is raised.
 *
 * IT IS NOT ONLY THE COPYLOCK'S TAIL, AND IT IS NOT RARE. ../names.txt records that the protection's
 * failure path `jmp`s here, which is how Ghidra came to fold the routine into `copylock_key_check`.
 * But the image holds TWENTY-NINE control-flow sites aimed at $6bb8: that one `jmp` ($f572), four
 * unconditional `bra.w` ($35c2, $3ff2, $5472, $54a6) and TWENTY-FOUR conditional `bne.w` — $2556,
 * $272c, $70aa and twenty-one more. Every one of the twenty-four is the same three instructions: a
 * per-monster state routine ends `bclr`/`btst #3,9(a0)` and branches here when the bit was set, and
 * bit 3 of WB_ACTOR_FLAGS2 is the DEFEATED bit `actor_damage_template_hitpoints` raises. So this
 * routine runs on EVERY monster death in the game, not on a protection failure — which is also what
 * makes the respawn continuation at $6cdc (below) hot code rather than a corner.
 *
 * THE BOUNDARY IS GONE. Batch 21b stopped at `ble.w $6cdc` and reported which exit it reached;
 * batch 22 followed the branch, so both exits now run to the original's own `rts` and the two
 * `#define`s below report which of the two the run TOOK rather than where it stopped. They are still
 * C-only — not image state — which is why test/layout.py scrapes this header for them.
 *
 * WHAT $6cdc IS. 126 bytes ($6cdc..$6d59), reached from `$6bb8` and from nowhere else, ending in the
 * `rts` that returns to $6bb8's own caller. It picks a KIND — the template's forced one, or a
 * stage_random_kind draw when that is zero — and rebuilds the dead record out of it: NINE writes
 * over ten offsets, not the six an earlier reading of this plate counted. The `bmi.w $6c38` on a
 * negative kind takes it back into $6bb8's retire tail, which is why that tail is a helper in
 * src/actor.c with three entrances rather than a block with one.
 */
#define WB_ACTOR_DEFEAT_RETIRED  0u  /* the slot was freed and the template possibly re-armed */
#define WB_ACTOR_DEFEAT_RESPAWN  1u  /* the slot came back as a new kind ($6cdc ran to its `rts`) */

/* $6bb8 — `actor` is the original's a0, the record that just died. Returns one of the two exits
 * above. Twenty-nine control-flow sites: 24 `bne.w`, 4 `bra.w` and the Copylock's `jmp`. */
uint32_t actor_defeat_and_score(uint8_t *image, uint32_t actor);

/* $6cdc — rebuild `actor` (a0) as a new kind, drawn for `template_record` (a1) unless that template
 * forces one. `entry_d2` is the caller's d2, handed straight to whichever draw runs because its HIGH
 * half addresses that draw's table read (rng.h); $6bb8 reaches here with the scaled spawn type in
 * the low word and zero above it. Returns WB_ACTOR_DEFEAT_RESPAWN, or WB_ACTOR_DEFEAT_RETIRED when a
 * forced kind is negative and the `bmi.w $6c38` frees the slot instead. */
uint32_t actor_respawn_as_new_kind(uint8_t *image, uint32_t actor, uint32_t template_record,
                                   uint32_t entry_d2);

#endif /* WONDERBOY_ACTOR_H */
