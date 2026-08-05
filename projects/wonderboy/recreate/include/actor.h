/* actor.h — the followed actor's record, the two tests the game runs against it, the pass that
 * projects actor records into screen coordinates, and the table's own lifecycle (src/actor.c).
 *
 * `followed_actor_record` is the bottom of the tier: fifteen call sites in the image, three of them
 * the routines below. Everything here takes and returns 68000 REGISTERS — a record address in a0, a
 * reach in d0 — because that is the whole interface the originals have; every address is a global
 * named in wonderboy.h, which both languages read, so this header carries no constant of its own.
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

#endif /* WONDERBOY_ACTOR_H */
