/* render.c — the per-object render pass @ 0x12caa..0x1358a.
 *
 * One routine with three entry points, which is why all three share this file:
 *
 *   render_objects      @ 0x12caa  points A0 at object_table and falls into the body — the whole
 *                                  table in one call, and the only entry the game itself uses
 *                                  (`jsr $12caa` from the main loop at 0x10042).
 *   render_objects_next @ 0x12cb2  the loop tail: A0 += OBJ_SIZE, `rts` at effect_table, otherwise
 *                                  fall into the body again. Not callable — every path that
 *                                  finishes a slot BRANCHES here, and it owns the routine's single
 *                                  `rts`.
 *   render_object_body  @ 0x12cc2  one slot's work: pick a branch off the flags word, move the
 *                                  object, choose its sprite, erase the old one and draw the new.
 *                                  Entered with A0 mid-table it therefore renders that slot AND
 *                                  every slot above it, because it falls into the tail.
 *
 * The body has two RESTART edges — the platform-edge branch that finds no box (0x1319c) and the
 * respawn that finishes growing (0x135f0). Both store the updated flags word and branch back to
 * 0x12cc2, which re-reads it, so the same slot is re-dispatched down a different branch. They are
 * the `SLOT_RESTART` results below.
 *
 * Register map for the whole routine: A0 = the object, D0 = its flags word (zero-extended from the
 * record's word by `clr.l`/`move.w`, so only bits 0-15 are ever live), D1 = the sprite address on
 * its way to draw_src, A1/A2 = whichever table the current branch is walking.
 */
#include "machine.h"
#include "joust.h"
#include "render.h"

typedef enum { SLOT_DONE, SLOT_RESTART } slot_result;

/* Forward declaration for the one true cycle in the flow graph: the respawn's materialise step can
 * hand back to the ordinary sprite select (`blt.w 0x12dfc` at 0x1359a). */
static void select_sprite_and_draw(uint8_t *image, uint32_t object, uint32_t flags);

/* =================================================================================================
 * The tail of every branch: stage the sprite, then erase and redraw.
 * ============================================================================================= */

/* @ 0x1300e — draw the sprite the draw_* globals now describe, and record it as this object's
 * "previous" so the next frame's erase pass knows what to undo. */
static void redraw_and_commit(uint8_t *image, uint32_t object) {
    draw_object_data(image, object);

    wr32(image + object + OBJ_PREV_DST, be32(image + A_draw_dst));
    wr32(image + object + OBJ_PREV_SRC, be32(image + A_draw_src));
    image[object + OBJ_PREV_ROWS] = image[A_draw_rows];
    image[object + OBJ_PREV_SHIFT] = image[A_draw_shift];
    wr16(image + object + OBJ_PREV_X, be16(image + object + OBJ_X));
    wr16(image + object + OBJ_PREV_Y, be16(image + object + OBJ_Y));
}

/* @ 0x13004 — the same, preceded by the erase. A prev_dst of 0 means nothing has ever been drawn
 * for this slot, so there is nothing to take back off the screen. */
static void erase_then_redraw(uint8_t *image, uint32_t object) {
    if (be32(image + object + OBJ_PREV_DST) != 0) draw_object_mask(image, object);
    redraw_and_commit(image, object);
}

/* A dead rider drifting off the right-hand edge is drawn in halves: one of draw_object_data's two
 * passes is suppressed so the part that would wrap onto the next scanline is dropped instead.
 *
 * WHICH half is kept depends on OBJ_FLAG_REMOVED, and the two mappings are exact opposites (0x12fb0
 * against 0x12fca). A corpse still on the board keeps the leading cell while it drifts left and the
 * wrap column while it drifts right; one already being taken off the board does the reverse.
 * OBJ_FLAG_CORPSE_INSIDE switches the whole thing off while the rider is well on screen.
 *
 * This is one of only two readers of OBJ_FLAG_REMOVED in the whole program (update_objects, in
 * src/objects.c, is the other), and the bit changes nothing else here — both arms write
 * draw_half_select and nothing more, which is what
 * test_render.py's test_bit12_changes_nothing_when_the_corpse_is_not_at_the_edge pins. */
static void clip_departing_corpse(uint8_t *image, uint32_t object, uint32_t flags) {
    if (!(flags & OBJ_FLAG_DEAD)) return;
    if (flags & OBJ_FLAG_CORPSE_INSIDE) return;
    if ((int16_t)be16(image + object + OBJ_X) <= CORPSE_CLIP_X) return;

    int drifting_left = (int16_t)be16(image + object + OBJ_VX) < 0;
    if (flags & OBJ_FLAG_REMOVED) drifting_left = !drifting_left;
    image[A_draw_half_select] = (uint8_t)(drifting_left ? CORPSE_KEEP_LEADING_CELL
                                                        : CORPSE_KEEP_WRAP_COLUMN);
}

/* @ 0x12f4c — the join every branch that draws something reaches. Commits the sprite and the flags
 * word, converts the object's (x, y) into a screen address, and erases the previous sprite only
 * when this frame's is going somewhere else: an identical address, source, height and shift means
 * the AND-NOT and the OR would cancel, so the erase is skipped outright.
 */
static void commit_and_draw(uint8_t *image, uint32_t object, uint32_t flags, uint32_t sprite) {
    wr32(image + A_draw_src, sprite);
    wr16(image + object + OBJ_FLAGS, (uint16_t)flags);

    /* The original parks A0 in draw_dst across the pos_to_screen call and reloads it afterwards
     * (0x12f56 / 0x12f72), that routine saving no address register. Reproduced for write order,
     * though it cannot be observed: draw_dst is overwritten with the result a few instructions
     * later, and object_table (0x10f36..) cannot reach draw_dst (0x10de8). */
    wr32(image + A_draw_dst, object);

    uint16_t shift;
    uint32_t dst = pos_to_screen(image, be16(image + object + OBJ_X),
                                 be16(image + object + OBJ_Y), &shift);
    wr32(image + A_draw_dst, dst);
    image[A_draw_shift] = (uint8_t)shift;   /* `move.b d0` — the LOW byte of the returned word */

    image[A_draw_half_select] = 0;
    clip_departing_corpse(image, object, flags);

    int unchanged = image[object + OBJ_PREV_SHIFT] == image[A_draw_shift]
                 && image[object + OBJ_PREV_ROWS] == image[A_draw_rows]
                 && be32(image + object + OBJ_PREV_SRC) == be32(image + A_draw_src)
                 && be32(image + object + OBJ_PREV_DST) == be32(image + A_draw_dst);

    if (unchanged) redraw_and_commit(image, object);
    else erase_then_redraw(image, object);
}

/* =================================================================================================
 * Choosing the sprite @ 0x12dfc — the join the two physics branches fall into.
 * ============================================================================================= */

/* The set, by identity for a player and by type for an enemy; the pose is added on afterwards. */
static uint32_t rider_sprite_set(uint32_t flags) {
    if (flags & OBJ_FLAG_PLAYER) {
        uint32_t set = (flags & OBJ_FLAG_TYPE_HI) ? SPRITE_RIDER_P2 : SPRITE_RIDER_P1;
        return (flags & OBJ_FLAG_DEAD) ? set + SPRITE_RIDER_DEAD : set;
    }
    if (flags & OBJ_FLAG_DEAD) return SPRITE_ENEMY_DEAD;

    /* `btst #0` then `btst #1`: types 1 (01) and 3 (11) have their own sets, and BOTH type 2 (10)
     * and the type-0 (00) an enemy is never shipped with fall to the middle one. */
    if (!(flags & OBJ_FLAG_TYPE_LO)) return SPRITE_ENEMY_TYPE2;
    return (flags & OBJ_FLAG_TYPE_HI) ? SPRITE_ENEMY_TYPE3 : SPRITE_ENEMY_TYPE1;
}

/* Release the looping walk sound if this object is the one still holding it. */
static void release_walk_sound(uint8_t *image, uint32_t object) {
    if (object != be32(image + A_snd_owner)) return;
    uint16_t playing = be16(image + A_snd_priority);
    if (playing == SND_WALK_A || playing == SND_WALK_B) play_sound(image, SND_NONE);
}

/* The footfall @ 0x12ebc: the walk cycle has come back round to its last frame. Enemies are silent
 * — only a player's footsteps are heard — and the two sounds alternate through snd_priority, which
 * play_sound then owns. */
static void walk_footfall_sound(uint8_t *image, uint32_t object) {
    if (object >= A_enemy_objects) return;

    if (be16(image + A_snd_priority) == SND_WALK_A) {
        wr16(image + A_snd_priority, SND_PRIORITY_FREE);
        play_sound(image, SND_WALK_B);
        wr32(image + A_snd_owner, object);
        return;
    }
    play_sound(image, SND_WALK_A);
    /* Only claimed if play_sound actually took the request — it drops one that a higher-priority
     * sound is already holding, and then the owner must stay whoever that sound belongs to. */
    if (be16(image + A_snd_priority) == SND_WALK_A) wr32(image + A_snd_owner, object);
}

/* The walking poses @ 0x12e5a: one frame every SPRITE_WALK_STRIDE, the last of them being the one
 * that completes a stride (a row shorter, its own mirrored offset, and it wraps the counter). */
static uint32_t walking_sprite(uint8_t *image, uint32_t object, uint32_t flags, uint32_t set) {
    image[A_draw_rows] = RIDER_ROWS_STANDING;
    uint16_t frame = be16(image + object + OBJ_FLAP_FRAME);
    uint32_t sprite = set + SPRITE_WALK + SPRITE_WALK_STRIDE * frame;   /* mulu.w: 16 x 16 -> 32 */

    if (frame != WALK_FRAME_STRIDE_END) {
        release_walk_sound(image, object);
        return (flags & OBJ_FLAG_FACING_RIGHT) ? sprite + SPRITE_WALK_FACING : sprite;
    }

    walk_footfall_sound(image, object);
    image[A_draw_rows] = RIDER_ROWS_STRIDE;
    wr16(image + object + OBJ_FLAP_FRAME, 0);
    return (flags & OBJ_FLAG_FACING_RIGHT) ? sprite + SPRITE_STRIDE_FACING : sprite;
}

/* The airborne poses @ 0x12f20: gliding, or one row taller with the wings up. */
static uint32_t flying_sprite(uint8_t *image, uint32_t flags, uint32_t set) {
    if (!(flags & OBJ_FLAG_WINGS_UP))
        return (flags & OBJ_FLAG_FACING_RIGHT) ? set + SPRITE_GLIDE_FACING : set;

    image[A_draw_rows]++;
    uint32_t sprite = set + SPRITE_FLAP;
    return (flags & OBJ_FLAG_FACING_RIGHT) ? sprite + SPRITE_FLAP_FACING : sprite;
}

static void select_sprite_and_draw(uint8_t *image, uint32_t object, uint32_t flags) {
    image[A_draw_rows] = RIDER_ROWS_FLIGHT;
    uint32_t set = rider_sprite_set(flags);
    uint32_t sprite = (flags & OBJ_FLAG_ON_PLATFORM) ? walking_sprite(image, object, flags, set)
                                                     : flying_sprite(image, flags, set);
    commit_and_draw(image, object, flags, sprite);
}

/* =================================================================================================
 * Moving the object: the two steps every physics branch funnels through.
 * ============================================================================================= */

/* @ 0x12dd4 — x += vx, wrapping round the 320-pixel playfield, then ask whether the object has
 * landed on (or walked off) a platform before its sprite is picked. */
static void step_x_and_draw(uint8_t *image, uint32_t object, uint32_t flags) {
    /* `add.w` + `bge`, which tests N == V — i.e. the sign of the TRUE sum, not of the stored word.
     * The full-precision sum below IS that sign, and the truncation is stored separately. */
    int32_t moved = (int16_t)be16(image + object + OBJ_X) + (int16_t)be16(image + object + OBJ_VX);
    wr16(image + object + OBJ_X, (uint16_t)moved);

    if (moved < 0)
        wr16(image + object + OBJ_X, (uint16_t)(be16(image + object + OBJ_X) + RIDER_X_WRAP));
    else if ((int16_t)be16(image + object + OBJ_X) > RIDER_X_MAX)
        wr16(image + object + OBJ_X, (uint16_t)(be16(image + object + OBJ_X) - RIDER_X_WRAP));

    select_sprite_and_draw(image, object, check_platform(image, object, flags));
}

/* @ 0x12da6 — y += vy, bouncing off the top of the screen and stopping dead at the bottom. */
static void step_y_and_draw(uint8_t *image, uint32_t object, uint32_t flags) {
    int32_t moved = (int16_t)be16(image + object + OBJ_Y) + (int16_t)be16(image + object + OBJ_VY);
    wr16(image + object + OBJ_Y, (uint16_t)moved);

    if (moved < 0) {
        wr16(image + object + OBJ_Y, 0);
        wr16(image + object + OBJ_VY, (uint16_t)-(int16_t)be16(image + object + OBJ_VY));
    } else if ((int16_t)be16(image + object + OBJ_Y) > RIDER_Y_MAX) {
        wr16(image + object + OBJ_Y, RIDER_Y_MAX);
        wr16(image + object + OBJ_VY, 0);
    }
    step_x_and_draw(image, object, flags);
}

/* =================================================================================================
 * Branch: in flight @ 0x12cea — the fall-through case, and the only one that flaps.
 * ============================================================================================= */

/* Ease vx one pixel per frame toward the speed the stick (or the AI) is asking for. */
static void ease_vx_toward_target(uint8_t *image, uint32_t object) {
    int16_t target = (int16_t)be16(image + object + OBJ_TARGET_VX);
    if (target == 0) return;

    int16_t vx = (int16_t)be16(image + object + OBJ_VX);
    if (vx > target) wr16(image + object + OBJ_VX, (uint16_t)(vx - 1));
    else if (vx < target) wr16(image + object + OBJ_VX, (uint16_t)(vx + 1));
}

/* One upward kick @ 0x12d68. The subtraction is a WORD op on the stored velocity, so a vy of 0x8001
 * wraps to +0x7fff and then reads as far above the rise limit — reproduced rather than clamped. */
static void flap_upward(uint8_t *image, uint32_t object) {
    int16_t rising = (int16_t)(be16(image + object + OBJ_VY) - FLAP_VY_STEP);
    if (rising < FLAP_VY_MIN) rising = FLAP_VY_MIN;
    wr16(image + object + OBJ_VY, (uint16_t)rising);
}

/* Gravity @ 0x12d84 — one step every STEP_TIMER_RESET frames, saturating at terminal speed. */
static void fall_a_step(uint8_t *image, uint32_t object) {
    if (--image[object + OBJ_STEP_TIMER] != 0) return;

    image[object + OBJ_STEP_TIMER] = STEP_TIMER_RESET;
    wr16(image + object + OBJ_VY, (uint16_t)(be16(image + object + OBJ_VY) + 1u));
    if ((int16_t)be16(image + object + OBJ_VY) > FALL_VY_MAX)
        wr16(image + object + OBJ_VY, FALL_VY_MAX);
}

static void fly(uint8_t *image, uint32_t object, uint32_t flags) {
    if (flags & OBJ_FLAG_GRABBED) {
        /* Held by the lava troll: it cannot drive itself sideways, and its flap rate is capped. */
        wr16(image + object + OBJ_VX, 0);
        if ((int8_t)image[object + OBJ_STEP_TIMER] > (int8_t)image[A_flap_delay])
            image[object + OBJ_STEP_TIMER] = image[A_flap_delay];
    } else {
        int16_t target = (int16_t)be16(image + object + OBJ_TARGET_VX);
        if (target > 0) flags |= OBJ_FLAG_FACING_RIGHT;
        else if (target < 0) flags &= ~OBJ_FLAG_FACING_RIGHT;
    }

    if ((flags & OBJ_FLAG_FLAP_REQUEST) && !(flags & OBJ_FLAG_FLAP_TAKEN)) {
        flags |= OBJ_FLAG_FLAP_TAKEN;
        if (object < A_enemy_objects) play_sound(image, SND_FLAP);   /* enemies flap silently */
        if (!(flags & OBJ_FLAG_GRABBED)) ease_vx_toward_target(image, object);
        flap_upward(image, object);
        step_y_and_draw(image, object, flags);
        return;
    }

    /* Not asking to flap (drop the latch so the next press counts), or asking but already kicked. */
    if (!(flags & OBJ_FLAG_FLAP_REQUEST)) flags &= ~OBJ_FLAG_FLAP_TAKEN;
    fall_a_step(image, object);
    step_y_and_draw(image, object, flags);
}

/* =================================================================================================
 * Branch: standing on a platform @ 0x13200.
 * ============================================================================================= */

/* The footstep sounds @ 0x132aa, on the walk frames whose low bit is set. Enemies are silent. */
static void walk_step_sound(uint8_t *image, uint32_t object) {
    if (object >= A_enemy_objects) return;

    uint8_t frame = image[object + OBJ_FLAP_FRAME_LO];
    if (!(frame & 1u)) return;
    if (frame & 2u) { play_sound(image, SND_STEP_A); return; }

    /* SIGNED: only a sound at or below SND_STEP_A's own priority may be interrupted. */
    if ((int16_t)be16(image + A_snd_priority) < (int16_t)SND_STEP_A) return;
    wr16(image + A_snd_priority, SND_PRIORITY_FREE);
    play_sound(image, SND_STEP_B);
}

/* The walk cycle @ 0x1326e, once this frame's speed is settled: face the way the feet are going,
 * and step the animation — unless the rider is turning round, which snaps straight to the frame
 * that ends a stride. */
static void step_walk_animation(uint8_t *image, uint32_t object, uint32_t flags) {
    int16_t vx = (int16_t)be16(image + object + OBJ_VX);
    if (vx == 0) {
        wr16(image + object + OBJ_FLAP_FRAME, 0);
        step_x_and_draw(image, object, flags);
        return;
    }
    if (vx < 0) flags &= ~OBJ_FLAG_FACING_RIGHT;
    else flags |= OBJ_FLAG_FACING_RIGHT;

    /* `eor.w` + `btst #15`: the target and the current speed disagree about direction. */
    uint16_t turning = (uint16_t)(be16(image + object + OBJ_TARGET_VX) ^ (uint16_t)vx);
    if (turning & 0x8000u) {
        wr16(image + object + OBJ_FLAP_FRAME, WALK_FRAME_STRIDE_END);
        step_x_and_draw(image, object, flags);
        return;
    }

    wr16(image + object + OBJ_FLAP_FRAME, (uint16_t)(be16(image + object + OBJ_FLAP_FRAME) + 1u));
    walk_step_sound(image, object);
    if (be16(image + object + OBJ_FLAP_FRAME) == WALK_FRAME_STRIDE_END)
        wr16(image + object + OBJ_FLAP_FRAME, 0);
    step_x_and_draw(image, object, flags);
}

static void walk_on_platform(uint8_t *image, uint32_t object, uint32_t flags) {
    if ((flags & OBJ_FLAG_FLAP_REQUEST) && !(flags & OBJ_FLAG_FLAP_TAKEN)) {
        /* Take off. The `cmpa.l #enemy_objects,a0` at 0x1320c that opens this block is DEAD — no
         * branch consumes its condition codes — so players and enemies leave alike. */
        flags &= ~OBJ_FLAG_ON_PLATFORM;
        flags |= OBJ_FLAG_WINGS_UP;
        flags &= ~OBJ_FLAG_FLAP_TAKEN;
        wr16(image + object + OBJ_Y, (uint16_t)(be16(image + object + OBJ_Y) - 1u));
        wr16(image + object + OBJ_VY, 0);
        image[object + OBJ_STEP_TIMER] = STEP_TIMER_RESET;
        wr16(image + object + OBJ_FLAP_FRAME, 0);
        step_y_and_draw(image, object, flags);
        return;
    }
    if (!(flags & OBJ_FLAG_FLAP_REQUEST)) flags &= ~OBJ_FLAG_FLAP_TAKEN;

    /* Walking speed eases toward the target one pixel every WALK_ANIM_RESET frames; already being
     * at the target holds the timer at its reload instead of counting it down. */
    uint16_t target = be16(image + object + OBJ_TARGET_VX);
    if (target == be16(image + object + OBJ_VX)) {
        image[object + OBJ_ANIM_TIMER] = WALK_ANIM_RESET;
    } else if (--image[object + OBJ_ANIM_TIMER] == 0) {
        image[object + OBJ_ANIM_TIMER] = WALK_ANIM_RESET;
        int16_t vx = (int16_t)be16(image + object + OBJ_VX);
        wr16(image + object + OBJ_VX,
             (uint16_t)((int16_t)target < vx ? vx - 1 : vx + 1));
    }
    step_walk_animation(image, object, flags);
}

/* =================================================================================================
 * Branch: sinking into the lava @ 0x131a8.
 * ============================================================================================= */

/* The object keeps its previous sprite and simply slides one scanline further down each frame.
 * Once the destination reaches playfield_bottom it is erased for good and the slot dies. */
static void sink_into_lava(uint8_t *image, uint32_t object) {
    wr16(image + object + OBJ_Y, (uint16_t)(be16(image + object + OBJ_Y) + 1u));
    wr32(image + A_draw_src, be32(image + object + OBJ_PREV_SRC));
    image[A_draw_shift] = image[object + OBJ_PREV_SHIFT];
    image[A_draw_rows] = image[object + OBJ_PREV_ROWS];

    uint32_t dst = be32(image + object + OBJ_PREV_DST) + SCREEN_ROW_BYTES;
    wr32(image + A_draw_dst, dst);
    if ((int32_t)dst < (int32_t)be32(image + A_playfield_bottom)) {
        erase_then_redraw(image, object);
        return;
    }

    draw_object_mask(image, object);
    /* An UNSIGNED whole-pointer bound (`cmpa.l #player2 ; bhi`): both player slots are paid for the
     * fall, every enemy slot above them is not. */
    if (object <= A_player2) {
        image[object + OBJ_SCORE_PENDING] = (uint8_t)(image[object + OBJ_SCORE_PENDING]
                                                      + LAVA_DEATH_SCORE);
        score_update(image, object);
    }
    player_death(image, object);
}

/* =================================================================================================
 * Branch: bumped a platform edge @ 0x13044.
 *
 * platform_edge_table's boxes wrap the ends of each platform. An object inside one is pushed clear
 * — down, up onto the top edge, or sideways off it — and the platform is marked for a redraw.
 * ============================================================================================= */

/* The box header is the same {y0, y1, x0, x1} platform_table opens with (object.h's PLAT_*). */
static int inside_edge_box(const uint8_t *image, uint32_t object, uint32_t edge) {
    int16_t y = (int16_t)be16(image + object + OBJ_Y);
    if (y < (int16_t)be16(image + edge + PLAT_Y0) || y > (int16_t)be16(image + edge + PLAT_Y1))
        return 0;
    int16_t x = (int16_t)be16(image + object + OBJ_X);
    return x >= (int16_t)be16(image + edge + PLAT_X0) && x <= (int16_t)be16(image + edge + PLAT_X1);
}

/* The vertical response @ 0x13072. A positive push shoves the object down into the open; a negative
 * one lifts it onto the box's top edge and, if it was not already moving, starts it walking away. */
static void apply_edge_y_push(uint8_t *image, uint32_t object, uint32_t flags, uint32_t edge) {
    int8_t y_push = (int8_t)image[edge + EDGE_Y_PUSH];
    if (y_push == 0) return;

    if (y_push > 0) {
        wr16(image + object + OBJ_Y,
             (uint16_t)(be16(image + object + OBJ_Y) + EDGE_PUSH_DOWN_DY));
        /* Only a box that does NOT also push sideways parks a type-3 enemy here for a while. */
        if (image[edge + EDGE_X_PUSH] == 0
            && (flags & ENEMY_TYPE_MASK) == ENEMY_TYPE_3)
            image[object + OBJ_FLAP_TIMER] = EDGE_DWELL_FRAMES;
    } else {
        if (be16(image + object + OBJ_VX) == 0)
            wr16(image + object + OBJ_VX, (flags & OBJ_FLAG_FACING_RIGHT) ? 1u : 0xffffu);
        wr16(image + object + OBJ_Y, be16(image + edge + PLAT_Y0));
        wr16(image + object + OBJ_Y,
             (uint16_t)(be16(image + object + OBJ_Y) - EDGE_SNAP_UP_DY));
    }
    wr16(image + object + OBJ_VY, 0);
    image[object + OBJ_STEP_TIMER] = STEP_TIMER_RESET;
}

/* Rolling right @ 0x130ea: x moves a fixed step and the speed is nudged toward the roll limit — a
 * rider already heading the other way is turned round (`addq` then `neg`) rather than eased. */
static void roll_right(uint8_t *image, uint32_t object) {
    uint16_t x = (uint16_t)(EDGE_ROLL_DX + be16(image + object + OBJ_X));
    if ((int16_t)x > RIDER_X_MAX) x = (uint16_t)(x - RIDER_X_WRAP);
    wr16(image + object + OBJ_X, x);

    int16_t vx = (int16_t)be16(image + object + OBJ_VX);
    if (vx == 0) return;
    if (vx < 0) wr16(image + object + OBJ_VX, (uint16_t)-(int16_t)(vx + 1));
    else if (vx != EDGE_ROLL_VX_MAX) wr16(image + object + OBJ_VX, (uint16_t)(vx + 1));
}

/* Rolling left @ 0x1311e — the mirror image, except that the x step is a `subq.w` whose `bge` reads
 * N == V, so an x of 0x8000 or just above wraps the OTHER way from what the stored word suggests. */
static void roll_left(uint8_t *image, uint32_t object) {
    int32_t stepped = (int16_t)be16(image + object + OBJ_X) - EDGE_ROLL_DX;
    uint16_t x = (uint16_t)stepped;
    if (stepped < 0) x = (uint16_t)(x + RIDER_X_WRAP);
    wr16(image + object + OBJ_X, x);

    int16_t vx = (int16_t)be16(image + object + OBJ_VX);
    if (vx == 0) return;
    if (vx > 0) wr16(image + object + OBJ_VX, (uint16_t)-(int16_t)(vx - 1));
    else if (vx != EDGE_ROLL_VX_MIN) wr16(image + object + OBJ_VX, (uint16_t)(vx - 1));
}

/* The horizontal response @ 0x130c4. Any sideways push cancels a rise first: the object is dragged
 * back down by exactly the height it was about to gain. */
static void apply_edge_x_push(uint8_t *image, uint32_t object, uint32_t edge) {
    int8_t x_push = (int8_t)image[edge + EDGE_X_PUSH];
    if (x_push == 0) return;

    image[object + OBJ_TURN_TIMER]++;
    int16_t vy = (int16_t)be16(image + object + OBJ_VY);
    if (vy < 0)
        wr16(image + object + OBJ_Y, (uint16_t)(be16(image + object + OBJ_Y) - (uint16_t)vy));
    wr16(image + object + OBJ_VY, 0);
    image[object + OBJ_STEP_TIMER] = STEP_TIMER_RESET;

    if (x_push > 0) roll_right(image, object);
    else roll_left(image, object);
}

static slot_result platform_edge_bump(uint8_t *image, uint32_t object, uint32_t flags) {
    for (uint32_t edge = A_platform_edge_table; edge != A_platform_edge_table_END;
         edge += EDGE_RECORD) {
        if (!inside_edge_box(image, object, edge)) continue;

        apply_edge_y_push(image, object, flags, edge);
        apply_edge_x_push(image, object, edge);

        /* Redraw the object where it now is, with the sprite it was last drawn from — this branch
         * picks no new pose — and ask draw_platforms to repaint the platform it scraped. */
        flags &= ~OBJ_FLAG_PLATFORM_BUMP;
        image[A_draw_rows] = image[object + OBJ_PREV_ROWS];
        uint32_t sprite = be32(image + object + OBJ_PREV_SRC);
        image[A_platform_present + sign_ext16(be16(image + edge + EDGE_PLATFORM))] =
            PLATFORM_REDRAW_MARK;
        commit_and_draw(image, object, flags, sprite);
        return SLOT_DONE;
    }

    /* No box contains it after all: drop the bit and re-dispatch the same slot. */
    wr16(image + object + OBJ_FLAGS, (uint16_t)(flags & ~OBJ_FLAG_PLATFORM_BUMP));
    return SLOT_RESTART;
}

/* =================================================================================================
 * Branch: awaiting respawn @ 0x13376.
 *
 * Two halves, told apart by prev_dst: a slot that has never been drawn is still looking for a spawn
 * point, and one that has is already standing on it, growing a row at a time.
 * ============================================================================================= */

/* @ 0x135a8 — the rider is fully grown: release its sound and its pad, and clear the three flags
 * that kept it here, so the restart re-dispatches it as an ordinary rider on a platform. */
static slot_result finish_respawn(uint8_t *image, uint32_t object, uint32_t flags) {
    if (object == be32(image + A_snd_owner)) play_sound(image, SND_NONE);
    image[object + OBJ_STEP_TIMER] = 0;
    flash_spawn_pad(image, object, flags);

    uint32_t spawn = A_spawn_points + sign_ext16(be16(image + object + OBJ_SPAWN_OFFSET));
    image[spawn + SPAWN_IN_USE] = 0;
    wr16(image + object + OBJ_VY, 0);
    wr16(image + object + OBJ_VX, 0);   /* also clears OBJ_GROW_TIMER, its high byte */
    image[object + OBJ_STEP_TIMER] = STEP_TIMER_RESET;
    image[object + OBJ_ANIM_TIMER] = WALK_ANIM_RESET;

    flags &= ~(OBJ_FLAG_RESPAWN | OBJ_FLAG_FLAP_REQUEST | OBJ_FLAG_FLAP_TAKEN);
    wr16(image + object + OBJ_FLAGS, (uint16_t)flags);
    return SLOT_RESTART;
}

/* The tail of the materialise animation @ 0x1358e, shared by its two inner counters. Below
 * RESPAWN_ANIM_LAST the rider is grown enough to be drawn as an ordinary one. */
static void grow_frame_done(uint8_t *image, uint32_t object, uint32_t flags, uint32_t sprite) {
    image[object + OBJ_GROW_TIMER] = image[object + OBJ_ANIM_TIMER];
    if ((int8_t)image[object + OBJ_ANIM_TIMER] < RESPAWN_ANIM_LAST)
        select_sprite_and_draw(image, object, flags);
    else
        commit_and_draw(image, object, flags, sprite);
}

/* @ 0x1353c — one frame of the pad flash while the rider grows. Three nested counters: OBJ_GROW_TIMER
 * paces the frames, OBJ_STEP_TIMER the flashes within one animation step, and OBJ_ANIM_TIMER the
 * steps themselves. Running the last of them out ends the respawn. */
static slot_result grow_a_frame(uint8_t *image, uint32_t object, uint32_t flags, uint32_t sprite) {
    if (--image[object + OBJ_GROW_TIMER] != 0) {
        flash_spawn_pad(image, object, flags);
        commit_and_draw(image, object, flags, sprite);
        return SLOT_DONE;
    }

    if (flags & OBJ_FLAG_PLAYER) sprite += SPRITE_MATERIALISE_PLAYER;
    image[object + OBJ_GROW_TIMER] = image[object + OBJ_ANIM_TIMER];

    if (--image[object + OBJ_STEP_TIMER] != 0) {
        flash_spawn_pad(image, object, flags);
        uint8_t step = image[object + OBJ_STEP_TIMER];
        if (step & 1u) {
            commit_and_draw(image, object, flags, sprite);
            return SLOT_DONE;
        }
        if (step & 2u) {
            commit_and_draw(image, object, flags, select_sprite_base(object, flags));
            return SLOT_DONE;
        }
        image[object + OBJ_STEP_TIMER]--;   /* every fourth flash costs two steps, not one */
    } else {
        if (--image[object + OBJ_ANIM_TIMER] == 0) return finish_respawn(image, object, flags);
        flash_spawn_pad(image, object, flags);
        image[object + OBJ_STEP_TIMER] = RESPAWN_STEP_FRAMES;
    }

    grow_frame_done(image, object, flags, sprite);
    return SLOT_DONE;
}

/* @ 0x134d0 — the rider grows one row per frame out of the spawn pad until it is RIDER_ROWS_STANDING
 * tall, rising a scanline each time so its feet stay put. */
static slot_result materialise(uint8_t *image, uint32_t object, uint32_t flags) {
    uint32_t sprite = be32(image + object + OBJ_PREV_SRC);

    if (image[object + OBJ_PREV_ROWS] != RIDER_ROWS_STANDING) {
        image[A_draw_rows] = (uint8_t)(image[object + OBJ_PREV_ROWS] + 1u);
        wr16(image + object + OBJ_Y, (uint16_t)(be16(image + object + OBJ_Y) - 1u));

        /* The frame it reaches full height on announces itself, and an enemy hands the respawn lock
         * back so the next one may start growing. */
        if (image[A_draw_rows] == RIDER_ROWS_STANDING) {
            int announce = 1;
            if (!(flags & OBJ_FLAG_PLAYER)) {
                image[A_respawn_lock] = 0;
                /* `cmp.b #$3 ; blt` — signed, but the mask holds the value to 0..7 either way. */
                announce = (flags & OBJ_RIDER_TYPE_MASK) >= ENEMY_TYPE_3;
            }
            if (announce) {
                wr32(image + A_snd_owner, object);
                play_sound(image, SND_SPAWN);
            }
        }
        return grow_a_frame(image, object, flags, sprite);
    }

    /* Full height: the first flap request or steer ends the respawn outright. */
    image[A_draw_rows] = RIDER_ROWS_STANDING;
    if ((flags & OBJ_FLAG_FLAP_REQUEST) || be16(image + object + OBJ_TARGET_VX) != 0)
        return finish_respawn(image, object, flags);
    return grow_a_frame(image, object, flags, sprite);
}

/* Is any OTHER live object standing over this spawn point's box? @ 0x133d4 */
static int spawn_point_is_clear(const uint8_t *image, uint32_t object, uint32_t spawn) {
    for (uint32_t other = A_object_table; other != A_object_table_END; other += OBJ_SIZE) {
        if (other == object || be16(image + other + OBJ_FLAGS) == 0) continue;

        int16_t y = (int16_t)be16(image + other + OBJ_Y);
        if (y < (int16_t)be16(image + spawn + SPAWN_Y0)) continue;
        if (y > (int16_t)be16(image + spawn + SPAWN_Y1)) continue;
        int16_t x = (int16_t)be16(image + other + OBJ_X);
        if (x < (int16_t)be16(image + spawn + SPAWN_X0)) continue;
        if (x <= (int16_t)be16(image + spawn + SPAWN_X1)) return 0;
    }
    return 1;
}

/* @ 0x13416 — put the rider on the pad and start it growing. */
static void place_rider(uint8_t *image, uint32_t object, uint32_t flags, uint32_t spawn) {
    /* `and.b #$7` then a SIGNED `cmp.b #$3`, over a value the mask holds to 0..7: types 0-3 take
     * the lock, and every type but 3 announces itself. */
    uint32_t type = flags & OBJ_RIDER_TYPE_MASK;
    if (type <= ENEMY_TYPE_3) {
        image[A_respawn_lock] = RESPAWN_LOCK_SET;
        if (type != ENEMY_TYPE_3) {
            wr32(image + A_snd_owner, object);
            play_sound(image, SND_SPAWN);
        }
    }

    image[A_live_object_count]++;
    image[spawn + SPAWN_IN_USE] = 1;
    wr16(image + object + OBJ_FLAP_FRAME, 0);
    wr16(image + object + OBJ_Y, be16(image + spawn + SPAWN_Y));
    wr16(image + object + OBJ_X, be16(image + spawn + SPAWN_X));
    image[object + OBJ_ANIM_TIMER] = RESPAWN_ANIM_FRAMES;
    image[object + OBJ_STEP_TIMER] = RESPAWN_STEP_FRAMES;
    image[object + OBJ_GROW_TIMER] = RESPAWN_ANIM_FRAMES;
    image[A_draw_rows] = 1;                 /* one row, and materialise grows it from there */
    flags |= OBJ_FLAG_ON_PLATFORM;
    wr16(image + object + OBJ_SPAWN_OFFSET, (uint16_t)(spawn - A_spawn_points));

    uint32_t sprite = select_sprite_base(object, flags);
    if (object == A_object_table) draw_lives_p1(image);
    else if (object == A_player2) draw_lives_p2(image);
    commit_and_draw(image, object, flags, sprite);
}

/* @ 0x1337e — walk spawn_points round-robin from the shared cursor, looking for a free pad on a
 * platform that exists this wave and that no other object is standing over. */
static slot_result find_spawn_point(uint8_t *image, uint32_t object, uint32_t flags) {
    if (!(flags & OBJ_FLAG_PLAYER)) {
        /* Enemies queue: one materialises at a time, and none at all while the board is full. */
        if (image[A_respawn_lock] != 0) return SLOT_DONE;
        if ((int8_t)image[A_live_object_count] >= RESPAWN_LIVE_LIMIT) return SLOT_DONE;
    }

    uint32_t cursor = be32(image + A_spawn_point_cursor) + SPAWN_RECORD;
    if (cursor == A_spawn_points_END) cursor = A_spawn_points;
    wr32(image + A_spawn_point_cursor, cursor);

    for (uint32_t spawn = cursor;;) {
        uint32_t present = be32(image + spawn + SPAWN_PRESENT_PTR);
        if (image[spawn + SPAWN_IN_USE] == 0 && image[present] != 0
            && spawn_point_is_clear(image, object, spawn)) {
            place_rider(image, object, flags, spawn);
            return SLOT_DONE;
        }
        spawn += SPAWN_RECORD;
        if (spawn == A_spawn_points_END) spawn = A_spawn_points;
        if (spawn == be32(image + A_spawn_point_cursor)) return SLOT_DONE;   /* all round, none free */
    }
}

static slot_result respawn(uint8_t *image, uint32_t object, uint32_t flags) {
    if (be32(image + object + OBJ_PREV_DST) != 0) return materialise(image, object, flags);
    return find_spawn_point(image, object, flags);
}

/* =================================================================================================
 * The dispatcher and the table walk.
 * ============================================================================================= */

/* @ 0x12cc2 — one slot, restart edges included. The branch order is the original's and matters:
 * an object that is both bumping an edge and in the lava takes the edge branch this frame. */
static void render_slot(uint8_t *image, uint32_t object) {
    for (;;) {
        uint32_t flags = be16(image + object + OBJ_FLAGS);
        if (flags == 0) return;                             /* free slot */

        if (flags & OBJ_FLAG_PLATFORM_BUMP) {
            if (platform_edge_bump(image, object, flags) == SLOT_RESTART) continue;
            return;
        }
        if (flags & OBJ_FLAG_IN_LAVA) { sink_into_lava(image, object); return; }
        if (flags & OBJ_FLAG_RESPAWN) {
            if (respawn(image, object, flags) == SLOT_RESTART) continue;
            return;
        }
        if (flags & OBJ_FLAG_ON_PLATFORM) { walk_on_platform(image, object, flags); return; }
        fly(image, object, flags);
        return;
    }
}

/* @ 0x12cc2 as the game's disassembly names it: this slot and every slot above it, because every
 * branch that finishes one falls into the loop tail rather than returning. */
void render_object_body(uint8_t *image, uint32_t object) {
    for (;;) {
        render_slot(image, object);
        object += OBJ_SIZE;
        if (object == A_object_table_END) return;
    }
}

/* @ 0x12cb2 — the loop tail on its own. Not reachable as a call in the shipped game; it exists as
 * an entry only because the body branches to it. */
void render_objects_next(uint8_t *image, uint32_t object) {
    object += OBJ_SIZE;
    if (object == A_object_table_END) return;
    render_object_body(image, object);
}

/* @ 0x12caa — the whole table, and the only entry the main loop uses. */
void render_objects(uint8_t *image) {
    render_object_body(image, A_object_table);
}

/* ------------------------------------------------------------------------------------- glue ---
 * All three take their object in A0 and return nothing, so each glue is a bare forwarder. */

void g_render_objects(uint8_t *image) {
    render_objects(image);
}

void g_render_objects_next(uint8_t *image, uint32_t object) {
    render_objects_next(image, object);
}

void g_render_object_body(uint8_t *image, uint32_t object) {
    render_object_body(image, object);
}
