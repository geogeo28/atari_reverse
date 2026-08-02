/* actor.h — the followed actor's record, the two tests the game runs against it, and the pass that
 * projects actor records into screen coordinates (src/actor.c).
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

#endif /* WONDERBOY_ACTOR_H */
