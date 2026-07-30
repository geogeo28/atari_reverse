/* render.h — the per-object render pass: the physics branch each slot takes, and the sprite it
 * ends up drawing. One routine with three entry points (see src/render.c).
 *
 * Every A_* address is a Ghidra address (image offset + the 0x10000 load base) and mirrors a `var`
 * line in ../../names.txt, which stays the source of truth for the name. Only what this layer alone
 * touches is declared here — the object record and the 68000 primitives are in joust.h, the shared
 * globals in addrs.h, and the routines this pass hands work to in draw.h / object.h / world.h /
 * egg.h / score.h / player.h / sound.h, all of which src/render.c includes rather than restates.
 */
#ifndef JOUST_RENDER_H
#define JOUST_RENDER_H

#include <stdint.h>

#include "addrs.h"
#include "draw.h"     /* select_sprite_base, draw_object_data/_mask, the draw_half_select bits */
#include "egg.h"      /* the platform_edge_table this pass walks, and its EDGE_* record */
#include "joust.h"
#include "object.h"   /* check_platform, platform_present, live_object_count, the box record */
#include "player.h"   /* player_death, and OBJ_FLAGS_FLAPPING — the mask over joust.h's flap pair */
#include "score.h"    /* score_update, draw_lives_p1/p2 */
#include "sound.h"    /* play_sound and snd_priority */
#include "world.h"    /* flash_spawn_pad, the spawn_points table, OBJ_FLAG_PLAYER/GRABBED/REMOVED */

/* --- globals this layer alone touches --------------------------------------------------------- */

/* A_respawn_lock is addrs.h's — the wave director clears it too. */
#define A_snd_owner         0x10d4eu  /* .l — the object whose looping sound is playing; compared
                                       * with the current slot before releasing it */

#define A_spawn_points_END    0x119b4u  /* == egg_bonus_table; the wrap bound of the spawn search */

/* --- the flags word (object + OBJ_FLAGS). Every BIT of it is shared and lives in joust.h or
 *     world.h, with ../../names.txt documenting the whole word; what is left here is the one mask
 *     no other layer takes. --------------------------------------------------------------------- */

/* The respawn branch reads bits 0-1 (the rider's TYPE, joust.h's OBJ_FLAG_TYPE_LO/HI) together with
 * OBJ_FLAG_PLAYER above them as one small number (`and.b #$7`), which is why this mask is a bit
 * wider than joust.h's ENEMY_TYPE_MASK — and why a PLAYER's masked type comes out 4 or 6 and so
 * never passes the `cmp.b #$3` that takes the respawn lock. */
#define OBJ_RIDER_TYPE_MASK   0x7u   /* the type values themselves are joust.h's */

/* --- object-record fields only this layer touches. They belong in joust.h the moment a second
 *     subsystem reads them, the way addrs.h describes for globals. ------------------------------ */
#define OBJ_PREV_Y      0x12u  /* .w — the partner of joust.h's OBJ_PREV_X, committed with it */

/* During a respawn the HIGH BYTE of OBJ_VX doubles as the materialise frame counter (`move.b #$5,
 * 6(a0)` at 0x13468, `subq.b #1,6(a0)` at 0x1353c). A rider that is still growing has no horizontal
 * speed yet, so the word is free — and finish_respawn clears the whole word before releasing it. */
#define OBJ_GROW_TIMER  OBJ_VX
/* Likewise OBJ_VY, as a WORD, carries the byte offset of the spawn_points record the rider is
 * growing on — the same field flash_spawn_pad indexes the table with (see src/world.c). */
#define OBJ_SPAWN_OFFSET  OBJ_VY
/* The `btst #0,15(a0)` / `btst #1,15(a0)` footstep tests read the flap frame's LOW BYTE. */
#define OBJ_FLAP_FRAME_LO  (OBJ_FLAP_FRAME + 1u)

/* --- geometry --------------------------------------------------------------------------------- */

/* The playfield width in pixels (`addi.w #$140` / `subi.w #$140` / `sub.w #$140`). world.h already
 * derives it from the scanline geometry for the lava troll; aliased rather than re-derived so the
 * two cannot drift apart. */
#define RIDER_X_WRAP  TROLL_X_WRAP
#define RIDER_X_MAX   ((int16_t)(RIDER_X_WRAP - 1))  /* `cmp.w #$13f` — the last column a rider sits on */
#define RIDER_Y_MAX   0xb4                 /* `move.l #$b4,d1` — the lowest scanline it may fall to */

/* Past this x a DEAD rider is half off the right edge, and one of draw_object_data's two passes is
 * suppressed so the half that would wrap onto the next scanline is not drawn. */
#define CORPSE_CLIP_X  0x12f

/* The two draw_half_select values that leaves: `bset #0` drops the wrap column, `bset #1` the
 * leading cell. src/draw.c names the same two bits from the READER's side (HALF_SELECT_SKIP_WRAP /
 * HALF_SELECT_SKIP_LEADING) and those are private to that file, so these are the writer's spelling
 * of the same pair — pinned equal to draw.c's in test_render.py rather than left to drift. */
#define CORPSE_KEEP_LEADING_CELL  0x01u
#define CORPSE_KEEP_WRAP_COLUMN   0x02u

/* --- velocities ------------------------------------------------------------------------------- */
#define FLAP_VY_STEP     2     /* `subq.w #2` — how hard one flap kicks upward... */
#define FLAP_VY_MIN    (-4)    /* `cmp.w #$fffc` — ...and the rise speed it saturates at */
#define FALL_VY_MAX      4     /* `cmp.w #$4` — terminal speed, one gravity step at a time */
#define EDGE_ROLL_DX     4     /* `moveq #$4` / `subq.w #$4` — the sideways shove off an edge... */
#define EDGE_ROLL_VX_MAX     4     /* ...and the speed the resulting roll saturates at, */
#define EDGE_ROLL_VX_MIN  (-4)     /*    each direction measured separately */
#define EDGE_PUSH_DOWN_DY  4   /* `addq.w #4` — a box with a positive y push shoves the rider down */
#define EDGE_SNAP_UP_DY    2   /* `subq.w #2` — a negative one snaps it onto the box's top edge */

/* --- timers ----------------------------------------------------------------------------------- */
#define STEP_TIMER_RESET      5u    /* `move.b #$5,11(a0)` — frames between gravity steps */
#define WALK_ANIM_RESET       3u    /* `move.b #$3,10(a0)` — frames between walk-speed steps */
#define EDGE_DWELL_FRAMES     0xbu  /* what a type-3 enemy's OBJ_FLAP_TIMER is reloaded to on a bump */
#define RESPAWN_ANIM_FRAMES   5u    /* the materialise animation's outer counter... */
#define RESPAWN_STEP_FRAMES   0xbu  /* ...and its inner one */
#define RESPAWN_ANIM_LAST     2     /* `cmpi.b #$2` — below this the ordinary sprite select runs */
#define RESPAWN_LIVE_LIMIT    8     /* `cmpi.b #$8` — no enemy respawns while this many are live */
#define RESPAWN_LOCK_SET      1u

/* `move.b #$1` into platform_present: >0 means "repaint me" (object.h documents the byte).
 * SECOND WRITER, DELIBERATELY NOT SHARED YET: src/egg.c spells the same value PLATFORM_NEEDS_REDRAW
 * for the egg's own edge bump. Two layers write it now, so by the rule addrs.h states it has earned
 * a move into object.h next to A_platform_present — but that edits egg.c, which is outside this
 * change. Until then the two are pinned equal by
 * test_render.py::test_the_platform_redraw_mark_is_the_one_egg_c_writes. */
#define PLATFORM_REDRAW_MARK   1u
#define LAVA_DEATH_SCORE       5u   /* `addq.b #5` into OBJ_SCORE_PENDING, i.e. 50 points */

/* --- sprite sets: the rider bitmaps, held as relocated immediates rather than through a table --- */
#define SPRITE_RIDER_P1      0x1a80au
#define SPRITE_RIDER_P2      0x1cd6au
#define SPRITE_RIDER_DEAD    0xf20u     /* added to either player set once the rider is dead */
#define SPRITE_ENEMY_DEAD    0x2202au
#define SPRITE_ENEMY_TYPE1   0x1f2cau
#define SPRITE_ENEMY_TYPE2   0x201eau   /* also what an enemy with no type bits at all draws */
#define SPRITE_ENEMY_TYPE3   0x2110au

/* Offsets into the chosen set. Each pose has its own, and each pose has its own mirrored half — the
 * facing offsets differ per pose because the poses are different widths. */
#define SPRITE_WALK           0x360u   /* the walking poses, one every SPRITE_WALK_STRIDE */
#define SPRITE_WALK_STRIDE    0x260u
#define SPRITE_WALK_FACING    0x130u
#define SPRITE_STRIDE_FACING  0x120u   /* ...for the one walk frame that completes a stride */
#define SPRITE_GLIDE_FACING   0xd0u
#define SPRITE_FLAP           0x1a0u
#define SPRITE_FLAP_FACING    0xe0u
#define SPRITE_MATERIALISE_PLAYER  0x260u  /* a player's materialise frames sit one stride further in */

/* Rows of the sprite each pose is: staged into draw_rows for the blitters. */
#define RIDER_ROWS_FLIGHT     0xdu   /* gliding; flapping adds one */
#define RIDER_ROWS_STANDING   0x13u  /* on a platform, and the height a materialising rider grows to */
#define RIDER_ROWS_STRIDE     0x12u  /* the frame that completes a stride is a row shorter */

#define WALK_FRAME_STRIDE_END  4u  /* `moveq #$4` — the walk frame that ends a stride and wraps to 0 */

/* --- sound: what this pass asks play_sound for ------------------------------------------------ */
#define SND_NONE          0u     /* index 0 releases whatever is looping (see src/sound.c) */
#define SND_SPAWN         4u
#define SND_WALK_A        9u
#define SND_FLAP          0xau
#define SND_WALK_B        0xcu
#define SND_STEP_A        0xdu
#define SND_STEP_B        0xfu
#define SND_PRIORITY_FREE 0x10u  /* a priority worse than any real sound, so the next one wins */

/* --- spawn_points record (0x14 bytes). Its {y0,y1,x0,x1} box uses the same field ORDER as
 *     platform_table's, but two bytes further in — the record opens with the in-use flag and the
 *     pixel shift world.h's SPAWN_SHIFT already names, so the box cannot share object.h's PLAT_*. */
#define SPAWN_IN_USE       0x0u   /* .b — nonzero while a rider is growing here */
#define SPAWN_Y0           0x2u
#define SPAWN_Y1           0x4u
#define SPAWN_X0           0x6u
#define SPAWN_X1           0x8u
#define SPAWN_Y            0xau   /* .w — where the rider itself is placed... */
#define SPAWN_X            0xcu   /* ...which is SPAWN_X0..X1's pad, offset by a few pixels */
#define SPAWN_PRESENT_PTR  0x10u  /* .l — this pad's platform_present byte; 0 = no platform to
                                   * stand on this wave, so the point is unusable */
#define SPAWN_RECORD       0x14u

/* --- render.c ---------------------------------------------------------------------------------- */
void render_objects(uint8_t *image);
void render_objects_next(uint8_t *image, uint32_t object);
void render_object_body(uint8_t *image, uint32_t object);

#endif /* JOUST_RENDER_H */
