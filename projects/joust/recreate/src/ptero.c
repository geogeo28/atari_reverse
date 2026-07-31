/* ptero.c — update_pterodactyl @ 0x14ada, the pterodactyl scheduler, driver and blitter.
 *
 * One pass over the four slots of pterodactyl_table. An empty slot is the scheduler's business: it
 * arms itself once spawn_timer runs out, and spawn_interval HALVES every time, so the birds arrive
 * faster and faster through a wave. An occupied slot is driven and drawn, in five stages:
 *
 *   1. a slot that is only ARMED is built — the sound, the pose, the entry edge (chosen by a bit
 *      sampled through rng_ptr) and the clip counters that fade it in;
 *   2. its sprite is swept against every platform present this wave, and the first one it overlaps
 *      turns it away — left, right, or over/under;
 *   3. failing that it either dies (the death animation, which ends by posting the "1000" popup and
 *      releasing the slot), or is separated from any other bird it has drifted into and then either
 *      LEAVES (the wave is over, or it is already on its way out) or HUNTS: it looks for a player to
 *      lock onto, dives at one it has locked, and otherwise cruises at the nearer player's altitude;
 *   4. the pose advances and the frame's sprite, height and offset are read out of
 *      ptero_frame_table;
 *   5. x and y move by PT_VX / PT_VY in the directions the flag bits say, the three per-cell clip
 *      suppressors are staged, the previous frame is erased and the new one drawn, and the record is
 *      rewritten from the draw scratch so the NEXT frame's erase knows where this one landed.
 *
 * Register map of the original: a0 = the slot, d0 = its flags word (only the low half is ever
 * stored back), a1/a2 = the two hit boxes, a3 = platform_sprites, a5 = ptero_bump_table.
 */
#include "machine.h"

#include "addrs.h"
#include "draw.h"     /* the clip suppressors, draw_dst_off, and the bird's two blitters */
#include "joust.h"
#include "object.h"   /* the pterodactyl record, the hit boxes and their stagers, the ptero_* helpers */
#include "objects.h"  /* active_players, PLAYFIELD_WIDTH */
#include "ptero.h"
#include "score.h"    /* the message record the bounty popup fills in */
#include "sound.h"    /* play_sound, SND_PTERO_CRY */
#include "wave.h"     /* spawn_interval / spawn_timer, ptero_wave_countdown */

/* =================================================================================================
 * 68000 semantics this routine leans on.
 * ============================================================================================= */

/* `subq.b #1,<mem> ; bne` — the byte is stored and the branch tests the stored result, so a counter
 * of 0 wraps to 0xff and is 256 ticks from firing rather than already spent. */
static int tick_down_to_zero(uint8_t *image, uint32_t counter) {
    uint8_t left = (uint8_t)(image[counter] - 1u);
    image[counter] = left;
    return left == 0;
}

/* `subq.b #1,<mem> ; b(gt|ge)` — these two branches test N == V, not the sign of the truncated
 * byte, so taking one off 0x80 stores 0x7f and still compares NEGATIVE. Doing the subtraction on the
 * SIGNED byte at full precision reproduces exactly that; the caller compares the result the way its
 * own branch does. (src/wave.c's take_one_off_count and src/input.c's subq_condition are the same
 * hazard — it has bitten this project four times now.) */
static int32_t take_one_off(uint8_t *image, uint32_t counter) {
    int32_t left = (int8_t)image[counter] - 1;
    image[counter] = (uint8_t)left;
    return left;
}

/* =================================================================================================
 * Stage 0 — the scheduler.
 * ============================================================================================= */

#define SPAWN_TIMER_MARGIN  0x20u  /* addi.w #$20 — the reload is the HALVED interval plus this */

/* An empty slot arms itself, but only while a wave is actually being played and there is somebody
 * to hunt. `lsr.w` on memory shifts by exactly one bit, so each bird costs half the wait of the
 * one before it. */
static void schedule_spawn(uint8_t *image, uint32_t slot) {
    if (image[A_game_phase] != 0) return;
    if (image[A_active_players] == 0) return;
    if ((int16_t)be16(image + A_spawn_timer) > 0) return;      /* `tst.w` + `bgt`: SIGNED */

    uint16_t interval = (uint16_t)(be16(image + A_spawn_interval) >> 1);
    wr16(image + A_spawn_interval, interval);
    wr16(image + A_spawn_timer, (uint16_t)(interval + SPAWN_TIMER_MARGIN));
    wr16(image + slot + PT_FLAGS, PT_FLAG_JUST_SPAWNED);
}

/* =================================================================================================
 * Stage 1 — building an armed slot.
 * ============================================================================================= */

#define PTERO_Y_MAX        0x96u  /* the bird's lowest scanline: where it enters, and the clamp its
                                   * downward travel runs into */
#define PTERO_ENTRY_SPEED  2u
#define PTERO_ENTRY_FADE   0xbu   /* frames the half of the sprite that is still off-screen stays
                                   * suppressed, which is what makes the bird slide into view */

/* The two sprite sets, and the entry position that goes with each. Both sprite addresses are
 * RELOCATED longwords, so the listing's raw `#$131aa` / `#$1332a` are the PRE-relocation
 * spellings; at the 0x10000 load base the sprite sets really live at 0x231aa / 0x2332a.
 * A bird entering LEFTWARD starts at x 0 and its first move wraps it to the right edge; one entering
 * RIGHTWARD starts near the right edge, where only its wrapped cells are on screen, so it appears at
 * the left. Which of the two the bird gets is bit 0 of the byte the random cursor happens to point
 * at. */
#define PTERO_SPRITE_LEFTWARD   0x231aau
#define PTERO_SPRITE_RIGHTWARD  0x2332au
#define PTERO_FACING_STRIDE     0x180u   /* `addi.l #$180` — and RIGHTWARD less LEFTWARD */
/* The screen address the FIRST erase pass would use. It never draws anything: PT_ROWS_W is cleared
 * just above, and blit_mask_wide's `subq.w`/`bge` counter refuses a row count of 0. Reproduced
 * because the store is real, not because the value is ever read as geometry. */
#define PTERO_ENTRY_DST_LEFTWARD   0x5dc0u  /* PTERO_Y_MAX scanlines down, column 0 */
#define PTERO_ENTRY_DST_RIGHTWARD  0x5e40u  /* ...and 16 cells along */
#define PTERO_ENTRY_X_RIGHTWARD    0x120u

/* Build a bird into a slot that the scheduler (or the wave director) has only ARMED, and return the
 * flags word it starts life with. PT_FLAG_IN_PLAY is all that word carries at first — it is there to
 * keep the word non-zero, which is the only test anyone makes of occupancy.
 *
 * rng_advance is handed the flags word as its restart nudge; only the low byte of it survives that
 * routine's `andi.l #$fe`, so the caller's garbage in D0's high half cannot matter.
 */
static uint16_t spawn_pterodactyl(uint8_t *image, uint32_t slot) {
    play_sound(image, SND_PTERO_CRY);
    image[A_ptero_spawn_count]++;
    uint16_t flags = PT_FLAG_IN_PLAY;

    wr16(image + slot + PT_SPARE, 0);
    wr16(image + slot + PT_VX, PTERO_ENTRY_SPEED);
    wr16(image + slot + PT_VY, 0);
    wr16(image + slot + PT_SHIFT_W, 0);
    wr16(image + slot + PT_ANIM, 0);
    wr16(image + slot + PT_ROWS_W, 0);
    wr16(image + slot + PT_DST_OFF, 0);
    image[slot + PT_DWELL_TIMER] = 0;
    image[slot + PT_CLIP_WRAPPED] = 0;
    image[slot + PT_CLIP_ONSCREEN] = 0;
    image[slot + PT_SWOOP_TIMER] = 0;
    wr16(image + slot + PT_Y, PTERO_Y_MAX);

    rng_advance(image, flags);
    /* `btst #0,(a1)+` — bit 0 of the BYTE the cursor points at; the post-increment is discarded. */
    if (image[be32(image + A_rng_ptr)] & 1u) {
        flags |= PT_FLAG_MOVING_RIGHT;
        wr32(image + slot + PT_SRC, PTERO_SPRITE_RIGHTWARD);
        wr32(image + slot + PT_DST, PTERO_ENTRY_DST_RIGHTWARD);
        wr16(image + slot + PT_X, PTERO_ENTRY_X_RIGHTWARD);
        image[slot + PT_CLIP_ONSCREEN] = PTERO_ENTRY_FADE;
    } else {
        wr32(image + slot + PT_SRC, PTERO_SPRITE_LEFTWARD);
        wr32(image + slot + PT_DST, PTERO_ENTRY_DST_LEFTWARD);
        wr16(image + slot + PT_X, 0);
        image[slot + PT_CLIP_WRAPPED] = PTERO_ENTRY_FADE;
    }
    return flags;
}

/* =================================================================================================
 * Stage 2 — the platforms.
 * ============================================================================================= */

#define PTERO_BOUNCE_SPEED    4u   /* the step a bird turned away by a platform travels at */
#define PLATFORM_PRESENT_SET  1u   /* what the hit writes back into platform_present — see below */

/* Which way a platform sends the bird. The bump record's two x bounds are tested against the bird's
 * x from the outside in: past the left one it is turned LEFT, past the right one RIGHT, and between
 * them it is sent vertically instead, over or under according to the record's y. Both x tests are
 * SIGNED word compares of the bound against the bird, so their sense reads backwards from the
 * instruction (`cmp.w x,bound ; blt` falls through when bound >= x). */
static uint16_t platform_bounce(uint8_t *image, uint32_t slot, uint16_t flags, uint32_t bump) {
    int16_t x = (int16_t)be16(image + slot + PT_X);
    if ((int16_t)be16(image + bump + BUMP_X_LEFT) >= x) {
        wr16(image + slot + PT_VX, PTERO_BOUNCE_SPEED);
        return flags & (uint16_t)~PT_FLAG_MOVING_RIGHT;
    }
    if ((int16_t)be16(image + bump + BUMP_X_RIGHT) <= x) {
        wr16(image + slot + PT_VX, PTERO_BOUNCE_SPEED);
        return flags | PT_FLAG_MOVING_RIGHT;
    }

    wr16(image + slot + PT_VY, PTERO_BOUNCE_SPEED);
    flags &= (uint16_t)~PT_FLAG_MOVING_DOWN;
    if ((int16_t)be16(image + bump + BUMP_Y) <= (int16_t)be16(image + slot + PT_Y))
        flags |= PT_FLAG_MOVING_DOWN;
    return flags;
}

/* Sweep the bird's sprite against every platform present this wave and let the first overlap turn
 * it away; returns whether one did. The bird's box is re-staged on EVERY pass, absent platforms
 * included, because test_overlap uses the boxes' HB_SRC and HB_CUR_COL as its own cursors.
 *
 * The hit also writes 1 back into that platform's platform_present byte. Nothing needs it — the byte
 * is already non-zero or the sweep would have skipped the platform, and the wave director only ever
 * stores 0 or 1 there — so in the shipped game it is a store of the value that is already in place.
 * Reproduced rather than dropped: it is a real write, and a present byte holding anything else would
 * be normalised by it.
 */
static int platform_turned_it_away(uint8_t *image, uint32_t slot, uint16_t *flags) {
    uint32_t bump = A_ptero_bump_table;
    for (uint32_t sprite = A_platform_sprites; sprite != A_platform_sprites_END;
         sprite += PSPR_RECORD, bump += BUMP_RECORD) {
        stage_ptero_box(image, A_hit_box_a, slot);
        uint32_t present = be32(image + sprite + PSPR_PRESENT);
        if (image[present] == 0) continue;                 /* absent this wave */

        stage_platform_box(image, sprite);
        test_overlap(image);
        if (image[A_collision_hit] == 0) continue;

        image[present] = PLATFORM_PRESENT_SET;
        *flags = platform_bounce(image, slot, *flags, bump);
        return 1;
    }
    return 0;
}

/* =================================================================================================
 * Stage 3a — dying.
 * ============================================================================================= */

#define PTERO_DEATH_POSE_FRAMES  4u  /* frames each half of the death flap is held for... */
#define PTERO_DEATH_CLIP         4u  /* ...and what both clip counters are left at on the last one */
#define PTERO_BOUNTY_KIND        1u  /* the message record the popup fills in */
#define PTERO_BOUNTY_COLOR       8u
#define PTERO_BOUNTY_FRAMES      0x3cu
#define PTERO_BOUNTY_Y_BIAS      2u  /* the popup sits two scanlines below the bird... */
#define PTERO_BOUNTY_X_BIAS      8u  /* ...and half a cell to its right */

/* Post the "1000" over the spot the bird died at, into the first free message slot. This walks the
 * table itself rather than calling find_free_message, and the difference shows on a FULL table:
 * find_free_message hands back 0 and its callers write the record over addresses 0..0xb, whereas
 * this loop simply gives up and writes nothing at all.
 *
 * The screen address is built in two halves, as the original does: the row from the bird's y, then
 * the column from its x through `divu.w #$10` — remainder to MSG_SHIFT, quotient scaled by
 * CELL_BYTES into the address. Both biases are applied to a WORD, so an x or y near 0xffff wraps
 * inside that word rather than carrying.
 */
static void post_bounty(uint8_t *image, uint32_t slot) {
    for (uint32_t message = A_message_table; message != A_message_table_END;
         message += MSG_RECORD) {
        if (image[message + MSG_KIND] != 0) continue;

        wr32(image + message + MSG_STRING, STR_PTERO_BOUNTY);
        image[message + MSG_COLOR] = PTERO_BOUNTY_COLOR;
        image[message + MSG_KIND] = PTERO_BOUNTY_KIND;
        image[message + MSG_TIMER] = PTERO_BOUNTY_FRAMES;

        uint32_t row = (uint32_t)(uint16_t)(be16(image + slot + PT_Y) + PTERO_BOUNTY_Y_BIAS)
                       * SCREEN_ROW_BYTES;
        uint32_t split = divu_w((uint16_t)(be16(image + slot + PT_X) + PTERO_BOUNTY_X_BIAS),
                                CELL_PIXELS);
        image[message + MSG_SHIFT] = (uint8_t)(split >> 16);          /* the remainder */
        wr32(image + message + MSG_SCREEN_PTR,
             row + (split & 0xffffu) * CELL_BYTES + be32(image + A_screen_base));
        return;
    }
}

/* The death animation. The bird stops dead and flaps between two poses, PTERO_DEATH_POSE_FRAMES to
 * a pose and PT_DWELL_TIMER poses in all, flipping its facing at each change so the corpse tumbles.
 * The last pose clears the whole flags word — which is how the slot is RELEASED — and posts the
 * bounty. Clearing the word also drops PT_FLAG_DYING, so the shared pose advance below runs one
 * last time on this frame.
 */
static uint16_t die(uint8_t *image, uint32_t slot, uint16_t flags) {
    image[slot + PT_CLIP_ONSCREEN] = 0;
    image[slot + PT_CLIP_WRAPPED] = 0;
    wr16(image + slot + PT_VX, 0);
    wr16(image + slot + PT_VY, 0);

    if (tick_down_to_zero(image, slot + PT_SWOOP_TIMER)) {
        flags ^= PT_FLAG_MOVING_RIGHT;                     /* `bchg #2,d0` */
        image[slot + PT_SWOOP_TIMER] = PTERO_DEATH_POSE_FRAMES;
        if (tick_down_to_zero(image, slot + PT_DWELL_TIMER)) {
            image[slot + PT_CLIP_ONSCREEN] = PTERO_DEATH_CLIP;
            image[slot + PT_CLIP_WRAPPED] = PTERO_DEATH_CLIP;
            post_bounty(image, slot);
            return 0;
        }
    }

    wr16(image + slot + PT_ANIM,
         (int16_t)be16(image + slot + PT_ANIM) < (int16_t)PT_ANIM_POSE3 ? PT_ANIM_POSE3
                                                                       : PT_ANIM_POSE2);
    return flags;
}

/* =================================================================================================
 * Stage 3b — keeping two birds apart.
 * ============================================================================================= */

#define PTERO_CROWD_X     0x1eu  /* the x band inside which two birds count as crowded... */
#define PTERO_CROWD_Y     0xcu   /* ...and the y band */
#define PTERO_CROWD_STEP  2u     /* how far each of the pair is nudged, per frame */

/* Push this bird away from every LATER slot it has drifted into, one step each per frame — so an
 * unordered pair meets exactly once. A dying bird is not pushed and does not push.
 *
 * The vertical test is the signedness trap: `sub.w` + `blt` branches on N != V, a true signed
 * comparison of the two y values, while the band test that follows reads the TRUNCATED difference.
 * The two disagree exactly when the subtraction overflows — y 0x8000 against y 1 is "above" by the
 * first reading and +0x7fff by the second.
 */
static void separate_from_later_slots(uint8_t *image, uint32_t slot) {
    for (uint32_t other = slot + PT_RECORD; other < A_pterodactyl_table_END; other += PT_RECORD) {
        uint16_t other_flags = be16(image + other + PT_FLAGS);
        if (other_flags == 0 || (other_flags & PT_FLAG_DYING)) continue;

        int16_t x_gap = (int16_t)(be16(image + slot + PT_X) - be16(image + other + PT_X));
        if (x_gap > (int16_t)PTERO_CROWD_X || x_gap < -(int16_t)PTERO_CROWD_X) continue;

        uint16_t y = be16(image + slot + PT_Y), other_y = be16(image + other + PT_Y);
        int16_t y_gap = (int16_t)(y - other_y);
        int nudge_up = (int16_t)y < (int16_t)other_y;
        if (nudge_up ? y_gap < -(int16_t)PTERO_CROWD_Y : y_gap > (int16_t)PTERO_CROWD_Y) continue;

        uint16_t step = nudge_up ? (uint16_t)-(int16_t)PTERO_CROWD_STEP : PTERO_CROWD_STEP;
        wr16(image + slot + PT_Y, (uint16_t)(y + step));
        wr16(image + other + PT_Y, (uint16_t)(other_y - step));
    }
}

/* =================================================================================================
 * Stage 3c — leaving.
 * ============================================================================================= */

#define PTERO_LEAVE_SPEED       6u
#define PTERO_EXIT_COLUMN_SIZE  6u     /* `divu.w #$6` — the x scale the exit is measured on */
#define PTERO_EXIT_COLUMN_LAST  0x2fu  /* the last of those columns, i.e. x 0x11a..0x11f */
#define PTERO_EXIT_FADE         7u     /* the counter the exit edge's cells are suppressed for */
#define PTERO_EXIT_RELEASE      2u     /* ...and the value of it at which the slot is released */
#define PTERO_EXIT_HOLD         3u     /* what the OTHER counter is left at — rightward exits only */

/* The bird is on its way off the screen: PT_FLAG_LEAVING is one-way, so nothing turns it back. It
 * still climbs and dives around platforms on the way out.
 *
 * The exit is a fade run by the clip counter belonging to the edge it is leaving by: the counter is
 * armed to PTERO_EXIT_FADE once the bird reaches the last column on that side, counts down one a
 * frame with the rest of the draw, and the frame it reads PTERO_EXIT_RELEASE the flags word is
 * cleared and the slot goes back to the scheduler. The two directions are not mirror images — the
 * rightward one also leaves the opposite counter at PTERO_EXIT_HOLD — which is the original's own
 * asymmetry, not a transcription slip.
 */
static uint16_t fly_away(uint8_t *image, uint32_t slot, uint16_t flags) {
    flags |= PT_FLAG_LEAVING;
    wr16(image + slot + PT_VX, PTERO_LEAVE_SPEED);
    flags &= (uint16_t)~PT_FLAG_MOVING_DOWN;
    /* Only D1's low word reaches PT_VY, so what the routine is handed as scratch cannot matter. */
    wr16(image + slot + PT_VY, (uint16_t)ptero_avoid_platform(image, slot, 0));

    uint16_t column = (uint16_t)divu_w(be16(image + slot + PT_X), PTERO_EXIT_COLUMN_SIZE);
    if (flags & PT_FLAG_MOVING_RIGHT) {
        image[slot + PT_CLIP_ONSCREEN] = 0;
        if (image[slot + PT_CLIP_WRAPPED] == PTERO_EXIT_RELEASE) {
            flags = 0;
            image[slot + PT_CLIP_ONSCREEN] = PTERO_EXIT_HOLD;
        }
        if (column == PTERO_EXIT_COLUMN_LAST) image[slot + PT_CLIP_WRAPPED] = PTERO_EXIT_FADE;
    } else {
        image[slot + PT_CLIP_WRAPPED] = 0;
        if (image[slot + PT_CLIP_ONSCREEN] == PTERO_EXIT_RELEASE) flags = 0;
        if (column == 0) image[slot + PT_CLIP_ONSCREEN] = PTERO_EXIT_FADE;
    }
    return flags;
}

/* =================================================================================================
 * Stage 3d — hunting.
 * ============================================================================================= */

#define PTERO_CRUISE_SPEED  3u   /* the horizontal step while hunting... */
#define PTERO_DIVE_SPEED    6u   /* ...and while diving */
#define PTERO_CLIMB_STEP    1u   /* the vertical step, once a direction has been chosen */
#define PTERO_DWELL_FRAMES  3u   /* frames between two choices of altitude */

/* The dive, once ptero_spot_player has armed PT_SWOOP_TIMER. Returns whether the pose advanced:
 * once the ladder reaches PT_ANIM_POSE2 the routine branches PAST the shared advance below, so the
 * bird holds that one pose for the rest of the dive. That branch is the only path in the whole
 * routine that skips it.
 *
 * The swoop timer is decremented and NOT tested — the dive ends when the pose ladder or a platform
 * ends it, not when the counter runs out — so a timer of 0 simply wraps to 0xff.
 */
static int dive_at_player(uint8_t *image, uint32_t slot) {
    wr16(image + slot + PT_VX, PTERO_DIVE_SPEED);
    wr16(image + slot + PT_VY, 0);
    image[slot + PT_SWOOP_TIMER]--;

    uint16_t anim = be16(image + slot + PT_ANIM);
    if ((anim & PT_ANIM_FRAME_MASK) == PT_ANIM_POSE2) return 0;
    wr16(image + slot + PT_ANIM, (uint16_t)(anim + 1u));
    return 1;
}

/* `muls.w` then `cmp.w`: the two squared row gaps are compared as SIGNED WORDS, so only the low
 * half of each product takes part — a gap of 0x100 rows squares to 0x10000 and compares as 0, and
 * one of 0xb6 squares to 0x8164, which reads NEGATIVE and so counts as the nearer. */
static int player2_is_nearer(const uint8_t *image, uint16_t y) {
    int16_t gap1 = (int16_t)(be16(image + A_object_table + OBJ_Y) - y);
    int16_t gap2 = (int16_t)(be16(image + A_player2 + OBJ_Y) - y);
    return (int16_t)(uint16_t)(gap2 * gap2) < (int16_t)(uint16_t)(gap1 * gap1);
}

/* Steer toward a player's altitude — but only once every PTERO_DWELL_FRAMES, so the bird commits to
 * a direction for a few frames at a time instead of chattering. With both players on the board the
 * one whose row is nearer is chased. */
static uint16_t chase_a_player(uint8_t *image, uint32_t slot, uint16_t flags) {
    wr16(image + slot + PT_VY, 0);
    if (take_one_off(image, slot + PT_DWELL_TIMER) > 0) return flags;   /* `subq.b` + `bgt` */

    image[slot + PT_DWELL_TIMER] = PTERO_DWELL_FRAMES;
    wr16(image + slot + PT_VY, PTERO_CLIMB_STEP);

    uint16_t y = be16(image + slot + PT_Y);
    uint8_t active = image[A_active_players];
    uint32_t target = A_player2;
    if ((active & ACTIVE_PLAYER1)
        && !((active & ACTIVE_PLAYER2) && player2_is_nearer(image, y)))
        target = A_object_table;

    if ((int16_t)be16(image + target + OBJ_Y) < (int16_t)y)
        return flags & (uint16_t)~PT_FLAG_MOVING_DOWN;
    return flags | PT_FLAG_MOVING_DOWN;
}

/* With nobody left to chase the bird just clears the platforms, and any non-zero step from
 * ptero_avoid_platform is flattened to PTERO_CLIMB_STEP. */
static uint16_t climb_over_platforms(uint8_t *image, uint32_t slot, uint16_t flags) {
    flags &= (uint16_t)~PT_FLAG_MOVING_DOWN;               /* cleared BEFORE the call */
    uint16_t step = (uint16_t)ptero_avoid_platform(image, slot, 0);
    wr16(image + slot + PT_VY, step);
    if (step != 0) wr16(image + slot + PT_VY, PTERO_CLIMB_STEP);
    return flags;
}

/* The hunt. A bird that is still fading in or out (either clip counter non-zero) neither looks for a
 * player nor dives; one that has already locked on dives; otherwise it offers itself to each player
 * on the board through ptero_spot_player and then cruises. `*advance_pose` is cleared only by the
 * dive holding its last pose, which is the one path that branches past the shared advance.
 */
static uint16_t hunt(uint8_t *image, uint32_t slot, uint16_t flags, int *advance_pose) {
    int settled = image[slot + PT_CLIP_ONSCREEN] == 0 && image[slot + PT_CLIP_WRAPPED] == 0;
    if (settled) {
        if (image[slot + PT_SWOOP_TIMER] != 0) {
            *advance_pose = dive_at_player(image, slot);
            return flags;
        }
        if (image[A_active_players] & ACTIVE_PLAYER1)
            ptero_spot_player(image, slot, A_object_table, flags);
        if (image[A_active_players] & ACTIVE_PLAYER2)
            ptero_spot_player(image, slot, A_player2, flags);
    }

    wr16(image + slot + PT_VX, PTERO_CRUISE_SPEED);
    if (image[A_active_players] == 0) return climb_over_platforms(image, slot, flags);
    return chase_a_player(image, slot, flags);
}

/* =================================================================================================
 * Stages 4 and 5 — moving and drawing.
 * ============================================================================================= */

#define PT_ANIM_STEP  3u   /* `addq.w #3` — the wing beat, on every frame the bird is alive */

/* `subq.b #1,<mem> ; bge ; clr.b` — take one off a clip counter and floor it at 0. The `bge` is the
 * N == V test again, so a counter of exactly 0x80 clamps to 0 rather than carrying on at 0x7f. */
static void fade_clip_counter(uint8_t *image, uint32_t counter) {
    if (take_one_off(image, counter) < 0) image[counter] = 0;
}

/* Stage the three per-cell suppressors from the record's two counters. Which cells the bird's three
 * occupy is decided by its x: PT_CLIP_ONSCREEN covers the cells still on this scanline and
 * PT_CLIP_WRAPPED the ones that have run past the right edge and reappear a scanline down — one
 * cell of the three from PTERO_WRAP_ONE_CELL, two from PTERO_WRAP_TWO_CELLS. Both bounds are
 * UNSIGNED word compares. */
#define PTERO_WRAP_ONE_CELL   0x120u   /* `cmpi.w #$120` + `bcs` */
#define PTERO_WRAP_TWO_CELLS  0x130u

static void stage_clip_suppressors(uint8_t *image, uint32_t slot) {
    image[A_draw_clip_cell0] = image[slot + PT_CLIP_ONSCREEN];
    image[A_draw_clip_cell1] = image[slot + PT_CLIP_ONSCREEN];
    image[A_draw_clip_cell2] = image[slot + PT_CLIP_ONSCREEN];

    uint16_t x = be16(image + slot + PT_X);
    if (x < PTERO_WRAP_ONE_CELL) return;
    image[A_draw_clip_cell2] = image[slot + PT_CLIP_WRAPPED];
    if (x < PTERO_WRAP_TWO_CELLS) return;
    image[A_draw_clip_cell1] = image[slot + PT_CLIP_WRAPPED];
}

/* Move the bird one frame along each axis. The two clamps are NOT the same shape: horizontally the
 * step is a `sub.w`/`bge` or an `add.w` against a SIGNED 0x140 bound, so x wraps round the playfield
 * either way; vertically the down clamp is an UNSIGNED `bcs` against PTERO_Y_MAX and the up clamp is
 * the `sub.w`/`bge` again, so y is pinned inside [0, PTERO_Y_MAX] instead of wrapping. */
static void move_pterodactyl(uint8_t *image, uint32_t slot, uint16_t flags) {
    uint16_t step_x = be16(image + slot + PT_VX);
    uint16_t x = be16(image + slot + PT_X);
    if (flags & PT_FLAG_MOVING_RIGHT) {
        wr16(image + slot + PT_X, (uint16_t)(x + step_x));
        if ((int16_t)be16(image + slot + PT_X) >= (int16_t)PLAYFIELD_WIDTH)
            wr16(image + slot + PT_X, 0);
    } else {
        wr16(image + slot + PT_X, (uint16_t)(x - step_x));
        if ((int16_t)x < (int16_t)step_x) wr16(image + slot + PT_X, PLAYFIELD_WIDTH - 1);
    }

    uint16_t step_y = be16(image + slot + PT_VY);
    uint16_t y = be16(image + slot + PT_Y);
    if (flags & PT_FLAG_MOVING_DOWN) {
        wr16(image + slot + PT_Y, (uint16_t)(y + step_y));
        if (be16(image + slot + PT_Y) >= PTERO_Y_MAX) wr16(image + slot + PT_Y, PTERO_Y_MAX);
    } else {
        wr16(image + slot + PT_Y, (uint16_t)(y - step_y));
        if ((int16_t)y < (int16_t)step_y) wr16(image + slot + PT_Y, 0);
    }
}

/* Erase the previous frame, draw this one, and write the draw scratch back into the record so that
 * the NEXT frame's erase knows where this one landed. Both blitters preserve D0, which is why the
 * flags word survives the calls and is stored afterwards.
 *
 * The scratch is re-read from memory after the blits rather than carried in locals: a bird drawn
 * over the draw_* globals themselves would store what it painted there.
 */
static void draw_pterodactyl(uint8_t *image, uint32_t slot, uint16_t flags) {
    uint32_t frame = A_ptero_frame_table
                     + (be16(image + slot + PT_ANIM) & PT_ANIM_FRAME_MASK);
    wr32(image + A_draw_src, be32(image + frame + FRAME_SRC));
    wr16(image + A_draw_dst_off, be16(image + frame + FRAME_DST_OFF));
    wr16(image + A_draw_rows, be16(image + frame + FRAME_ROWS));
    if (flags & PT_FLAG_MOVING_RIGHT)
        wr32(image + A_draw_src, be32(image + A_draw_src) + PTERO_FACING_STRIDE);

    move_pterodactyl(image, slot, flags);

    /* The screen address the sprite lands at, and the pixel shift within its leading cell. Unlike
     * every other reader of draw_shift, this one writes it as a WORD (see addrs.h's width clash). */
    uint16_t y = be16(image + slot + PT_Y);
    uint32_t split = divu_w(be16(image + slot + PT_X), CELL_PIXELS);
    wr16(image + A_draw_shift, (uint16_t)(split >> 16));
    wr32(image + A_draw_dst, (uint32_t)y * SCREEN_ROW_BYTES + (split & 0xffffu) * CELL_BYTES);

    fade_clip_counter(image, slot + PT_CLIP_WRAPPED);
    fade_clip_counter(image, slot + PT_CLIP_ONSCREEN);
    stage_clip_suppressors(image, slot);

    blit_mask_wide(image, slot);
    blit_sprite_planes(image);

    wr16(image + slot + PT_FLAGS, flags);
    wr16(image + slot + PT_ROWS_W, be16(image + A_draw_rows));
    wr16(image + slot + PT_SHIFT_W, be16(image + A_draw_shift));
    wr16(image + slot + PT_DST_OFF, be16(image + A_draw_dst_off));
    wr32(image + slot + PT_DST, be32(image + A_draw_dst));
    wr32(image + slot + PT_SRC, be32(image + A_draw_src));
}

/* =================================================================================================
 * update_pterodactyl @ 0x14ada.
 * ============================================================================================= */

/* A bird stops hunting and heads off the screen once the wave is between rounds, once it has been
 * sent on its way already, or once a pterodactyl wave has been announced and nobody is left to hunt.
 * Note which way round the last pair reads: it is a PENDING pterodactyl wave (the countdown still
 * running) plus an empty board that sends the bird away. */
static int is_leaving(const uint8_t *image, uint16_t flags) {
    return image[A_game_phase] != 0
           || (flags & PT_FLAG_LEAVING) != 0
           || (image[A_ptero_wave_countdown] != 0 && image[A_active_players] == 0);
}

/* One occupied slot: build it if it has only been armed, then run whichever of the three drivers
 * applies, advance the pose and draw. */
static void update_slot(uint8_t *image, uint32_t slot, uint16_t flags) {
    if (flags & PT_FLAG_JUST_SPAWNED) flags = spawn_pterodactyl(image, slot);

    int advance_pose = 1;
    if (!platform_turned_it_away(image, slot, &flags)) {
        if (flags & PT_FLAG_DYING) {
            flags = die(image, slot, flags);
        } else {
            separate_from_later_slots(image, slot);
            flags = is_leaving(image, flags) ? fly_away(image, slot, flags)
                                             : hunt(image, slot, flags, &advance_pose);
        }
    }

    if (advance_pose && !(flags & PT_FLAG_DYING))
        wr16(image + slot + PT_ANIM, (uint16_t)(be16(image + slot + PT_ANIM) + PT_ANIM_STEP));

    draw_pterodactyl(image, slot, flags);
}

/* update_pterodactyl() — the whole pterodactyl subsystem, once per frame.
 *
 * spawn_timer is taken down once for the frame, not once per slot, before the walk begins.
 */
void update_pterodactyl(uint8_t *image) {
    wr16(image + A_spawn_timer, (uint16_t)(be16(image + A_spawn_timer) - 1u));

    for (uint32_t slot = A_pterodactyl_table; slot != A_pterodactyl_table_END; slot += PT_RECORD) {
        uint16_t flags = be16(image + slot + PT_FLAGS);
        if (flags == 0) schedule_spawn(image, slot);
        else update_slot(image, slot, flags);
    }
}

/* ------------------------------------------------------------------------------------- glue ---
 * The routine takes no arguments and returns none: everything it reads and writes is in memory, so
 * the glue is a bare forwarder and the differential enters the oracle at 0x14ada directly. */

void g_update_pterodactyl(uint8_t *image) {
    update_pterodactyl(image);
}
