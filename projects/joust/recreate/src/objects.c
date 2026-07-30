/* objects.c — update_objects @ 0x12014, the per-frame enemy driver.
 *
 * One call walks object_table slots 2..13 (the players' two slots are steered by control_player)
 * and, for each live enemy, decides two things: the altitude it should be at (OBJ_TARGET_Y) and
 * the horizontal speed it should be doing (OBJ_TARGET_VX). It does not move anything — that is
 * render_object_body's job, which eases the real velocity toward these two targets. What this
 * routine writes besides them is the flap state in the flags word, the AI bytes at the end of the
 * record, and the two chase counters.
 *
 * The shape is: a prologue that works out which players are on the board, then per slot a dispatch
 * on the rider type (the flags word's low two bits), then one of eight shared TAILS that all the
 * type handlers branch into. The tails are what actually set the flap bits, so they are written
 * first here, bottom-up.
 *
 * A NINTH tail exists in the original and is not reconstructed: the three instructions at 0x12546
 * (`cmpi.w #$ffff,8(a0)` / `bge` / `bra`) — a sign-flipped twin of the 0x1253c tail below — are
 * DEAD. The evidence is static and exhaustive: no branch anywhere in the image targets 0x12546,
 * and nothing falls into it either (0x12544 is a `bra`). So there is no behaviour to reproduce —
 * and nothing the differential could pin, which is why no test claims to cover it.
 *
 * Two registers outlive a single slot's update and are therefore parameters of the whole routine:
 *
 *   * D0, the flags word. rng_advance takes its restart offset from D0, and the call sits at the
 *     TOP of each pass — so it is fed the flags word the PREVIOUS slot stored, or the caller's D0
 *     on the first slot.
 *   * D2, a scratch word here called `probe`. The type-1 chase test reads it on a path that never
 *     writes it (active_players == 2 skips the `move.w speed_type2,d2` that sets it up), so what
 *     it decides on is whatever the previous slot — or the caller — left behind.
 *
 * Neither is a designed argument; both are live values the original never initialises, and the
 * glue passes them because that is the routine's real I/O contract.
 */
#include "machine.h"
#include "addrs.h"    /* the object table, rng_ptr and the three wave speeds A_speed_type1/2/3 */
#include "joust.h"
#include "draw.h"     /* draw_object_mask, A_player2 */
#include "egg.h"      /* OBJ_EGG_Y, OBJ_HATCH_MOUNT */
#include "object.h"   /* erase_egg_sprite, A_object_table_END */
#include "objects.h"
#include "player.h"   /* the dead-rider exit strip and hover ladder — see remove_object */
#include "world.h"    /* OBJ_FLAG_REMOVED */

/* ------------------------------------------------------------------------------- the prologue */

/* A player is worth steering at while its slot is live, not dead and not waiting to respawn. */
static int player_is_on_the_board(const uint8_t *image, uint32_t player) {
    uint16_t flags = be16(image + player + OBJ_FLAGS);
    return flags != 0 && !(flags & OBJ_FLAG_DEAD) && !(flags & OBJ_FLAG_RESPAWN);
}

static void refresh_active_players(uint8_t *image) {
    image[A_active_players] = 0;
    if (player_is_on_the_board(image, A_object_table)) image[A_active_players] = ACTIVE_PLAYER1;
    if (player_is_on_the_board(image, A_player2)) image[A_active_players] |= ACTIVE_PLAYER2;
}

/* ------------------------------------------------------------------------------ the flap tails
 *
 * Every type handler ends in one of these. Each carries the address of the label it reconstructs,
 * because the handlers below read as "branch to 0x125a4" in the original and the mapping is the
 * only way to check them against it.
 */

#define FALL_SPEED_FLAP_MIN  1  /* `cmpi.w #$1,8(a0)` + `bgt` — only a rider already falling faster
                                 * than this keeps beating its wings */

/* 0x12598 — alternate between wings up and wings down, i.e. keep flapping. */
static uint16_t tail_flap_toggle(uint16_t flags) {
    return (uint16_t)(flags ^ (OBJ_FLAG_FLAP_REQUEST | OBJ_FLAG_WINGS_UP));
}

/* 0x125a4 — stop flapping, wings down. */
static uint16_t tail_flap_stop(uint16_t flags) {
    return (uint16_t)(flags & ~(OBJ_FLAG_FLAP_REQUEST | OBJ_FLAG_WINGS_UP));
}

/* 0x125b0 — start a flap, re-arming the impulse render_object_body applies on bit 11's edge. */
static uint16_t tail_flap_start(uint16_t flags) {
    return (uint16_t)(((flags | OBJ_FLAG_FLAP_REQUEST) & ~OBJ_FLAG_FLAP_TAKEN) ^ OBJ_FLAG_WINGS_UP);
}

/* 0x125c0 — one frame further into a flap burst: the wings keep beating but no new flap starts. */
static uint16_t tail_flap_burst_step(uint8_t *image, uint32_t object, uint16_t flags) {
    image[object + OBJ_FLAP_TIMER]--;
    return (uint16_t)((flags & ~OBJ_FLAG_FLAP_REQUEST) ^ OBJ_FLAG_WINGS_UP);
}

/* 0x1253c — flap only while already falling fast. */
static uint16_t tail_by_fall_speed(const uint8_t *image, uint32_t object, uint16_t flags) {
    return (int16_t)be16(image + object + OBJ_VY) > FALL_SPEED_FLAP_MIN
           ? tail_flap_toggle(flags) : tail_flap_stop(flags);
}

/* 0x12588 — flap only while BELOW the altitude the handler just asked for and not already rising. */
static uint16_t tail_by_target_y(const uint8_t *image, uint32_t object, uint16_t flags) {
    if ((int16_t)be16(image + object + OBJ_Y) <= (int16_t)be16(image + object + OBJ_TARGET_Y))
        return tail_flap_stop(flags);
    if ((int16_t)be16(image + object + OBJ_VY) < 0) return tail_flap_stop(flags);
    return tail_flap_toggle(flags);
}

#define FLAP_BUDGET_BASE  9  /* `move.w #$9,d2` — the wave speeds are subtracted from this, so a
                              * fast wave leaves the rider fewer frames between flaps */

/* 0x12550 — the climb budget. The timer counts down; while it is still above the budget this wave
 * allows, the rider flaps and the timer is clamped to one past the budget, so the very next pass
 * ends the burst. Also writes `probe`, which outlives the slot.
 */
static uint16_t tail_flap_budget(uint8_t *image, uint32_t object, uint16_t flags,
                                 uint16_t *probe) {
    image[object + OBJ_FLAP_TIMER]--;
    uint16_t budget = (uint16_t)(FLAP_BUDGET_BASE - be16(image + A_speed_type2)
                                 - (be16(image + A_speed_type1) >> 1));
    *probe = budget;
    /* `cmp.b` + `bcc`: an UNSIGNED byte compare, so only the low byte of the budget is looked at. */
    if ((uint8_t)budget >= image[object + OBJ_FLAP_TIMER]) return tail_flap_stop(flags);

    flags &= (uint16_t)~(OBJ_FLAG_ON_PLATFORM | OBJ_FLAG_FLAP_TAKEN);
    flags |= OBJ_FLAG_FLAP_REQUEST | OBJ_FLAG_WINGS_UP;
    *probe = (uint16_t)(budget + 1u);
    image[object + OBJ_FLAP_TIMER] = (uint8_t)*probe;
    return flags;
}

/* 0x125d0 — point the rider at whatever it is chasing and pick a flap tail from that.
 *
 * Standing on a platform it simply runs off at the wave's type-2 speed. In the air it REVERSES:
 * the target speed becomes the negation of the speed it currently has, and the facing flips to
 * match.
 */
static uint16_t tail_pursue(uint8_t *image, uint32_t object, uint16_t flags) {
    if (flags & OBJ_FLAG_ON_PLATFORM) {
        uint16_t speed = be16(image + A_speed_type2);
        wr16(image + object + OBJ_TARGET_VX,
             flags & OBJ_FLAG_FACING_RIGHT ? speed : (uint16_t)-speed);
        return tail_by_fall_speed(image, object, flags);
    }

    uint16_t speed = be16(image + object + OBJ_VX);
    wr16(image + object + OBJ_TARGET_VX, speed);
    if (speed == 0) return tail_flap_stop(flags);

    flags &= (uint16_t)~OBJ_FLAG_FACING_RIGHT;
    uint16_t negated = (uint16_t)-speed;
    wr16(image + object + OBJ_TARGET_VX, negated);
    /* `neg.w` + `blt`: blt is N != V, and negating 0x8000 OVERFLOWS (V set, result still 0x8000),
     * so the most negative speed takes the branch a positive result would — it ends up facing
     * right despite having been negated to a negative number. */
    int result_is_negative = (int16_t)negated < 0;
    int overflowed = speed == 0x8000u;
    if (result_is_negative != overflowed) return tail_flap_start(flags);
    return tail_flap_start((uint16_t)(flags | OBJ_FLAG_FACING_RIGHT));
}

/* ------------------------------------------------------------------- shared handler machinery */

/* The `move.w <speed>,12(a0)` + `neg.w` pair every type handler opens with: aim the target speed
 * along the rider's current facing. */
static void aim_target_vx(uint8_t *image, uint32_t object, uint16_t flags, uint16_t speed) {
    wr16(image + object + OBJ_TARGET_VX, speed);
    if (!(flags & OBJ_FLAG_FACING_RIGHT))
        wr16(image + object + OBJ_TARGET_VX, (uint16_t)-speed);
}

/* `move.w 4(a3),d1 ; sub.w d2,d1 ; cmp.w 4(a0),d1 ; ble` — is the player, lifted by `bias`, still
 * no higher up the screen than this rider? (Larger y is further DOWN, so "below" is the compare's
 * <= side.) The `cmp` computes its own overflow, so this one really is a plain signed test. */
static int player_stays_below(const uint8_t *image, uint32_t player, uint32_t object,
                              uint16_t bias) {
    int16_t probe_y = (int16_t)(be16(image + player + OBJ_Y) - bias);
    return probe_y <= (int16_t)be16(image + object + OBJ_Y);
}

/* ------------------------------------------------------------------------- type 1 @ 0x120b0 */

#define TYPE1_RESPAWN_CLIMB  6u   /* `subq.w #6` — how far above itself a respawning rider aims */
#define TYPE1_CRUISE_CLIMB   4u   /* `subq.w #4` — and how far while cruising */
#define TYPE1_CHASE_Y_BIAS   6u   /* `lsl.w #2` on speed_type2 then `subq.w #6`: how far above a
                                   * player this rider still counts as being chased from below */

/* The simplest rider: it cruises at the wave's type-1 speed and climbs when a player is above it,
 * spending its climb budget to do so. */
static uint16_t update_type1(uint8_t *image, uint32_t object, uint16_t flags, uint16_t *probe) {
    uint16_t speed = be16(image + A_speed_type1);
    uint16_t y = be16(image + object + OBJ_Y);

    if (flags & OBJ_FLAG_RESPAWN) {
        image[object + OBJ_TURN_TIMER] = 0;
        wr16(image + object + OBJ_TARGET_Y, (uint16_t)(y - TYPE1_RESPAWN_CLIMB));
        aim_target_vx(image, object, flags, speed);
        return tail_flap_toggle(flags);
    }

    aim_target_vx(image, object, flags, speed);
    uint8_t active = image[A_active_players];
    if (active == 0) return tail_by_target_y(image, object, flags);
    wr16(image + object + OBJ_TARGET_Y, (uint16_t)(y - TYPE1_CRUISE_CLIMB));

    if (active & ACTIVE_PLAYER1) {
        *probe = (uint16_t)((be16(image + A_speed_type2) << 2) - TYPE1_CHASE_Y_BIAS);
        if (player_stays_below(image, A_object_table, object, *probe))
            return tail_flap_budget(image, object, flags, probe);
    }
    /* With player 1 off the board `probe` was never set up here — the compare below runs on
     * whatever the previous slot left in D2. Reproduced, not repaired. */
    if (!(active & ACTIVE_PLAYER2)) return tail_by_fall_speed(image, object, flags);
    if (player_stays_below(image, A_player2, object, *probe))
        return tail_flap_budget(image, object, flags, probe);
    return tail_by_fall_speed(image, object, flags);
}

/* ------------------------------------------------------------------------- type 2 @ 0x12148 */

#define TYPE2_RESPAWN_CLIMB        0xfu  /* `subi.w #$f` */
#define TYPE2_RESPAWN_JITTER_MASK  3u    /* `andi.w #$3` on a word of rng noise, added back on */
#define TYPE2_CRUISE_CLIMB         4u    /* `subq.w #4` */
#define TYPE2_ATTACK_Y_BIAS        0x1eu /* `subi.w #$1e` — a player this far above is out of reach */
#define TYPE2_RETREAT_Y_BIAS       4     /* `subq.w #4` on the player's y in the retreat test */
#define TYPE2_RETREAT_Y_MAX        0x28  /* `cmpi.w #$28` — dropped this far behind, give up */

#define CHASE_SEEK_P1    1u     /* OBJ_CHASE_TARGET while closing on a player... */
#define CHASE_SEEK_P2    2u
#define CHASE_ATTACK_P1  0xffu  /* ...and once in range of it (-1 / -2, the `blt` side) */
#define CHASE_ATTACK_P2  0xfeu

/* The gap between a rider and its egg / its quarry, in x, brought back into 0..PLAYFIELD_WIDTH. */
static uint16_t x_gap_to(const uint8_t *image, uint32_t object, uint16_t from_x) {
    /* `sub.w` + `bge`: bge is N == V, so a subtraction that overflowed 16 bits keeps the sign the
     * hardware saw — done here at full precision, with the truncated word carried forward. */
    int32_t exact = (int32_t)(int16_t)from_x - (int32_t)(int16_t)be16(image + object + OBJ_X);
    return exact < 0 ? (uint16_t)(exact + PLAYFIELD_WIDTH) : (uint16_t)exact;
}

/* Everything the type-2 chase needs to address one player rather than the other. The original
 * spells all three out twice — once in each of the four mirrored arms — with A3/A4 and the two
 * counters swapped; naming the triple collapses the four copies into two. */
struct chase_side {
    uint32_t player;     /* the object slot being chased */
    uint32_t counter;    /* its chase counter */
    uint8_t active_bit;  /* its bit in active_players */
};

static struct chase_side chase_side(int player_one) {
    struct chase_side p1 = {A_object_table, A_chasers_p1, ACTIVE_PLAYER1};
    struct chase_side p2 = {A_player2, A_chasers_p2, ACTIVE_PLAYER2};
    return player_one ? p1 : p2;
}

/* 0x121d8 / 0x1223e / 0x122e8 / 0x1231a — the player being chased has left the board (or pulled
 * too far ahead): forget it and hand the chase slot back. */
static uint16_t release_chase_slot(uint8_t *image, uint32_t object, uint16_t flags,
                                   uint32_t counter) {
    image[object + OBJ_CHASE_TARGET] = 0;
    image[counter]--;
    return tail_by_target_y(image, object, flags);
}

/* 0x121fc / 0x12262 — in range at last: turn to face the quarry and beat once toward it. */
static uint16_t turn_toward_player(uint8_t *image, uint32_t object, uint16_t flags,
                                   uint32_t player, uint16_t *probe) {
    *probe = x_gap_to(image, object, be16(image + player + OBJ_X));
    uint16_t speed = be16(image + A_speed_type2);
    if (*probe < PLAYFIELD_HALF_WIDTH) {
        flags |= OBJ_FLAG_FACING_RIGHT;
        wr16(image + object + OBJ_TARGET_VX, speed);
    } else {
        flags &= (uint16_t)~OBJ_FLAG_FACING_RIGHT;
        wr16(image + object + OBJ_TARGET_VX, (uint16_t)-speed);
    }
    return tail_flap_start(flags);
}

/* 0x121ce / 0x12234 — closing on a player (OBJ_CHASE_TARGET 1 or 2). Any value above 1 means
 * player 2: the original tests `cmpi.b #1` and takes every other non-negative value the other way. */
static uint16_t type2_close_in(uint8_t *image, uint32_t object, uint16_t flags, int chasing_p1,
                               uint16_t *probe) {
    struct chase_side side = chase_side(chasing_p1);

    if (!(image[A_active_players] & side.active_bit))
        return release_chase_slot(image, object, flags, side.counter);
    if (player_stays_below(image, side.player, object, TYPE2_ATTACK_Y_BIAS))
        return tail_flap_budget(image, object, flags, probe);

    image[object + OBJ_CHASE_TARGET] = chasing_p1 ? CHASE_ATTACK_P1 : CHASE_ATTACK_P2;
    return turn_toward_player(image, object, flags, side.player, probe);
}

#define RETREAT_X_CLOSE       0xcu     /* `cmpi.w #$c` + `bls` — right on top of the quarry */
#define RETREAT_X_CLOSE_LEFT  0xfff4u  /* `cmpi.w #$fff4` + `bcc` — the same 12 px the other way */
/* The same two distances measured the long way round the 320-px playfield (0x140 - 0xc). */
#define RETREAT_X_WRAP_RIGHT  0x134
#define RETREAT_X_WRAP_LEFT   ((int16_t)0xfeccu)

/* 0x12340 — how the attack ends. Within a dozen pixels of the quarry (either way round the
 * playfield) the rider commits and pursues; anywhere else it breaks off and just falls. */
static uint16_t type2_attack_range(uint8_t *image, uint32_t object, uint16_t flags,
                                   uint16_t *probe) {
    *probe = (uint16_t)(*probe - be16(image + object + OBJ_X));
    int within_reach = *probe <= RETREAT_X_CLOSE
                    || *probe >= RETREAT_X_CLOSE_LEFT
                    || (int16_t)*probe >= RETREAT_X_WRAP_RIGHT
                    || (int16_t)*probe <= RETREAT_X_WRAP_LEFT;
    return within_reach ? tail_pursue(image, object, flags)
                        : tail_by_fall_speed(image, object, flags);
}

/* 0x122d6 — attacking (OBJ_CHASE_TARGET negative). The attack holds only while the quarry is
 * still below and not too far below; otherwise the chase slot goes back. */
static uint16_t type2_attack(uint8_t *image, uint32_t object, uint16_t flags, uint16_t *probe) {
    struct chase_side side = chase_side(image[object + OBJ_CHASE_TARGET]
                                        == (uint8_t)CHASE_ATTACK_P1);

    if (!(image[A_active_players] & side.active_bit))
        return release_chase_slot(image, object, flags, side.counter);

    /* `subq.w #4` then `sub.w` then `ble`: the subq's result is TRUNCATED to a word before the
     * second subtraction, whose own overflow is what `ble` (Z or N != V) reads. */
    uint16_t lifted = (uint16_t)(be16(image + side.player + OBJ_Y) - TYPE2_RETREAT_Y_BIAS);
    int32_t drop = (int32_t)(int16_t)lifted - (int32_t)(int16_t)be16(image + object + OBJ_Y);
    *probe = (uint16_t)drop;
    if (drop <= 0) return release_chase_slot(image, object, flags, side.counter);
    if ((int16_t)*probe >= TYPE2_RETREAT_Y_MAX) return tail_by_fall_speed(image, object, flags);

    *probe = be16(image + side.player + OBJ_X);
    return type2_attack_range(image, object, flags, probe);
}

/* 0x12278 — no target yet. Pick the player with the smaller chase count (or the only one on the
 * board) and claim a slot on it, provided this wave's cap has room. */
static uint16_t type2_claim_target(uint8_t *image, uint32_t object, uint16_t flags,
                                   uint16_t *probe) {
    *probe = be16(image + A_speed_type3);   /* its LOW BYTE is the per-player chase cap */

    int take_p2;
    if (image[A_active_players] == ACTIVE_BOTH)
        take_p2 = (int8_t)image[A_chasers_p1] > (int8_t)image[A_chasers_p2];
    else
        take_p2 = (image[A_active_players] & ACTIVE_PLAYER2) != 0;

    struct chase_side side = chase_side(!take_p2);
    if ((uint8_t)*probe > image[side.counter]) {     /* `cmp.b` + `bls` — UNSIGNED */
        image[object + OBJ_CHASE_TARGET] = take_p2 ? CHASE_SEEK_P2 : CHASE_SEEK_P1;
        image[side.counter]++;
    }
    return tail_by_target_y(image, object, flags);
}

/* The hunter. It holds a chase slot on one player at a time, closes until it is level, then
 * attacks; losing the player at any stage gives the slot back. */
static uint16_t update_type2(uint8_t *image, uint32_t object, uint16_t flags, uint32_t rng_cursor,
                             uint16_t *probe) {
    uint16_t speed = be16(image + A_speed_type2);
    uint16_t y = be16(image + object + OBJ_Y);

    if (flags & OBJ_FLAG_RESPAWN) {
        image[object + OBJ_CHASE_TARGET] = 0;
        image[object + OBJ_TURN_TIMER] = 0;
        *probe = (uint16_t)(be16(image + rng_cursor) & TYPE2_RESPAWN_JITTER_MASK);
        wr16(image + object + OBJ_TARGET_Y, (uint16_t)(y - TYPE2_RESPAWN_CLIMB + *probe));
        aim_target_vx(image, object, flags, speed);
        return tail_flap_toggle(flags);
    }

    aim_target_vx(image, object, flags, speed);
    if (image[A_active_players] == 0) {
        image[object + OBJ_CHASE_TARGET] = 0;
        /* `clr.w $d5e` — ONE word store, so it zeroes both chase counters at once. */
        wr16(image + A_chasers_p1, 0);
        return tail_by_target_y(image, object, flags);
    }

    int8_t target = (int8_t)image[object + OBJ_CHASE_TARGET];
    if (target == 0) return type2_claim_target(image, object, flags, probe);

    wr16(image + object + OBJ_TARGET_Y, (uint16_t)(y - TYPE2_CRUISE_CLIMB));
    if (target < 0) return type2_attack(image, object, flags, probe);
    return type2_close_in(image, object, flags, target == (int8_t)CHASE_SEEK_P1, probe);
}

/* ------------------------------------------------------------------------- type 3 @ 0x12368 */

#define TYPE3_RESPAWN_CLIMB  8u    /* `subq.w #8` */
#define TYPE3_DIVE_Y_BIAS    0xa   /* `addi.w #$a` — how far above a player still counts as a dive */
#define TYPE3_DIVE_Y_MAX     0x32  /* `cmpi.w #$32` + `bgt` — further below than this is out of reach */
#define TYPE3_DIVE_CEILING   4     /* `cmpi.w #$4,4(a0)` + `bge` — too near the top of the screen
                                    * to give up altitude, so climb instead */
#define TYPE3_DIVE_FRAMES    0xbu  /* `move.b #$b,73(a0)` — how long one dive glide lasts */

enum dive_choice { DIVE_CLIMB, DIVE_COMMIT, DIVE_OUT_OF_REACH };

/* 0x123d6 / 0x1240c — should this rider dive at `player`? */
static enum dive_choice choose_dive(const uint8_t *image, uint32_t object, uint32_t player) {
    uint16_t drop = (uint16_t)(be16(image + player + OBJ_Y) - be16(image + object + OBJ_Y));
    /* `addi.w` + `blt`: blt is N != V, so what is tested is the sum at FULL precision, not the
     * sign of the truncated word the following `cmpi.w` then works on. */
    int32_t reach = (int32_t)(int16_t)drop + TYPE3_DIVE_Y_BIAS;
    if (reach < 0) return DIVE_CLIMB;                                  /* the player is above */
    if ((int16_t)(uint16_t)reach > TYPE3_DIVE_Y_MAX) return DIVE_OUT_OF_REACH;
    if ((int16_t)be16(image + object + OBJ_Y) >= TYPE3_DIVE_CEILING) return DIVE_CLIMB;
    return DIVE_COMMIT;
}

/* 0x123f6 / 0x1242e — what either dive arm does once it has decided. Committing arms the glide
 * timer and steps it; climbing just starts a flap. Only DIVE_OUT_OF_REACH differs between the two
 * arms, so only that answer is left to the caller. */
static uint16_t act_on_dive(uint8_t *image, uint32_t object, uint16_t flags,
                            enum dive_choice choice) {
    if (choice == DIVE_CLIMB) return tail_flap_start(flags);
    image[object + OBJ_FLAP_TIMER] = TYPE3_DIVE_FRAMES;
    return tail_flap_burst_step(image, object, flags);
}

/* The diver. It holds its altitude until a player passes just below, then spends TYPE3_DIVE_FRAMES
 * gliding down at it. */
static uint16_t update_type3(uint8_t *image, uint32_t object, uint16_t flags) {
    uint16_t speed = be16(image + A_speed_type3);
    uint16_t y = be16(image + object + OBJ_Y);

    if (flags & OBJ_FLAG_RESPAWN) {
        image[object + OBJ_FLAP_TIMER] = 0;
        image[object + OBJ_TURN_TIMER] = 0;
        wr16(image + object + OBJ_TARGET_Y, (uint16_t)(y - TYPE3_RESPAWN_CLIMB));
        aim_target_vx(image, object, flags, speed);
        return flags;   /* the one handler that touches no flap tail at all */
    }

    aim_target_vx(image, object, flags, speed);
    uint8_t active = image[A_active_players];
    if (active == 0) return tail_by_target_y(image, object, flags);

    wr16(image + object + OBJ_TARGET_Y, y);
    if (flags & OBJ_FLAG_ON_PLATFORM) image[object + OBJ_FLAP_TIMER] = 0;
    if (image[object + OBJ_FLAP_TIMER] != 0) return tail_flap_burst_step(image, object, flags);

    /* Both arms answer CLIMB and COMMIT identically; the ONLY asymmetry is where OUT_OF_REACH
     * goes — player 1's falls through to the player-2 test, player 2's ends the pass. That is why
     * the shared part is the helper and the fall-through is what is spelled out here. */
    if (active & ACTIVE_PLAYER1) {
        enum dive_choice choice = choose_dive(image, object, A_object_table);
        if (choice != DIVE_OUT_OF_REACH) return act_on_dive(image, object, flags, choice);
    }
    if (!(active & ACTIVE_PLAYER2)) return tail_by_fall_speed(image, object, flags);

    enum dive_choice choice = choose_dive(image, object, A_player2);
    if (choice != DIVE_OUT_OF_REACH) return act_on_dive(image, object, flags, choice);
    return tail_by_fall_speed(image, object, flags);
}

/* --------------------------------------------------------- the dead slot's tail @ 0x12438 */

/* THE SAME EXIT STRIP, DRIFT SPEED AND HOVER LADDER control_player uses on a dead player: the
 * original carries two copies of this logic (0x11e.. and here) with identical constants, so the
 * constants are taken from player.h rather than written out a second time. The two ROUTINES stay
 * separate — they are separate originals, and each is verified at its own entry. */

/* Has the slot reached the strip of x it is being walked off through? Facing right, any x at or
 * past DEAD_EXIT_RIGHT_X; facing left, only the four-pixel window — a corpse that overshot it has
 * wrapped round the right edge and drifts on. */
static int reached_the_exit(const uint8_t *image, uint32_t object, uint16_t flags) {
    int16_t x = (int16_t)be16(image + object + OBJ_X);
    if (flags & OBJ_FLAG_FACING_RIGHT) return x >= DEAD_EXIT_RIGHT_X;
    return x >= DEAD_EXIT_LEFT_LO && x <= DEAD_EXIT_LEFT_HI;
}

/* 0x1243e — the removal tail, reached with OBJ_FLAG_REMOVED set. At the exit strip the sprite is
 * masked off the screen and the flags word is ZEROED, which is what frees the slot; short of it
 * the object drifts on toward the nearest exit altitude. */
static uint16_t remove_object(uint8_t *image, uint32_t object, uint16_t flags) {
    flags &= (uint16_t)~OBJ_FLAG_CORPSE_INSIDE;
    if (reached_the_exit(image, object, flags)) {
        draw_object_mask(image, object);
        return 0;
    }

    /* `move.w #$4` then `neg.w` if vx is negative — a vx of exactly 0 drifts RIGHT (`bge`). */
    wr16(image + object + OBJ_TARGET_VX, PLAYER_STEER_VX);
    if ((int16_t)be16(image + object + OBJ_VX) < 0)
        wr16(image + object + OBJ_TARGET_VX, (uint16_t)-PLAYER_STEER_VX);

    /* The hover ladder, written out the way the original walks it: each altitude is STORED and
     * then kept or overwritten by the next band's test, so the y compares run in this order. */
    int16_t y = (int16_t)be16(image + object + OBJ_Y);
    wr16(image + object + OBJ_TARGET_Y, HOVER_TARGET_LOW);
    if (y > HOVER_BAND_MID_Y) return tail_by_target_y(image, object, flags);
    wr16(image + object + OBJ_TARGET_Y, HOVER_TARGET_MID);
    if (y > HOVER_BAND_HIGH_Y) return tail_by_target_y(image, object, flags);
    wr16(image + object + OBJ_TARGET_Y, HOVER_TARGET_HIGH);
    return tail_by_target_y(image, object, flags);
}

#define EGG_RECOVERY_X_MAX  0x12cu  /* `cmpi.w #$12c` + `bcc` — UNSIGNED, so a negative x is out */
#define EGG_RECOVERY_X_MIN  2u      /* `cmpi.w #$2` + `bls` */
#define EGG_REACH_X_BIAS    2u      /* `addq.w #2` — the rider's grab point is right of its x */
/* Standing over the egg: within EGG_REACH of it either way, measured both directly and the long
 * way round the playfield (0x140 - 2 == 0x13e). */
#define EGG_REACH_RIGHT       2u
#define EGG_REACH_LEFT        0xfffeu
#define EGG_REACH_WRAP_RIGHT  0x13e
#define EGG_REACH_WRAP_LEFT   ((int16_t)0xfec2u)

#define HATCH_MOUNT_TURNED  1u  /* OBJ_HATCH_MOUNT: the rider has turned back toward its egg */
#define EGG_MOUNT_Y_BIAS    2u  /* `subq.w #2` on the egg's y — the altitude it walks in at */

static int standing_over_the_egg(uint16_t gap) {
    return gap <= EGG_REACH_RIGHT
        || (int16_t)gap <= EGG_REACH_WRAP_LEFT
        || gap >= EGG_REACH_LEFT
        || (int16_t)gap >= EGG_REACH_WRAP_RIGHT;
}

/* 0x12512 — over the egg. Having already turned back once, the rider remounts: bit 13 clears, the
 * egg sprite is erased and the egg record freed, and the slot goes back to being a live rider. */
static uint16_t mount_the_egg(uint8_t *image, uint32_t object, uint16_t flags) {
    if (image[object + OBJ_HATCH_MOUNT] == HATCH_MOUNT_TURNED) {
        flags &= (uint16_t)~OBJ_FLAG_DEAD;
        erase_egg_sprite(image, object);
        image[object + OBJ_EGG_STATE] = 0;
        return flags;
    }
    image[object + OBJ_HATCH_MOUNT] = 0;
    wr16(image + object + OBJ_TARGET_Y,
         (uint16_t)(be16(image + object + OBJ_EGG_Y) - EGG_MOUNT_Y_BIAS));
    return tail_by_target_y(image, object, flags);
}

/* 0x124a6 — a dead slot that has not been marked for removal yet.
 *
 * With no egg left there is nothing to come back for, so OBJ_FLAG_REMOVED is latched and the same
 * `btst #12` is re-run, which now falls straight into the removal tail. With an egg the rider
 * walks back to it: on-screen it gets OBJ_FLAG_CORPSE_INSIDE, and once it has overshot the egg it
 * reverses ONCE (OBJ_HATCH_MOUNT) and remounts on the way back.
 */
static uint16_t update_dead(uint8_t *image, uint32_t object, uint16_t flags) {
    if (flags & OBJ_FLAG_REMOVED) return remove_object(image, object, flags);
    if (image[object + OBJ_EGG_STATE] == 0)
        return remove_object(image, object, (uint16_t)(flags | OBJ_FLAG_REMOVED));

    uint16_t x = be16(image + object + OBJ_X);
    if (x < EGG_RECOVERY_X_MAX && x > EGG_RECOVERY_X_MIN) flags |= OBJ_FLAG_CORPSE_INSIDE;
    if (!(flags & OBJ_FLAG_CORPSE_INSIDE)) return tail_by_target_y(image, object, flags);

    image[object + OBJ_FLAP_TIMER] = 0;
    image[object + OBJ_TURN_TIMER] = 0;
    image[object + OBJ_CHASE_TARGET] = 0;

    uint16_t gap = (uint16_t)(x + EGG_REACH_X_BIAS - be16(image + object + OBJ_EGG_X));
    if (standing_over_the_egg(gap)) return mount_the_egg(image, object, flags);

    if (image[object + OBJ_HATCH_MOUNT] != 0) return tail_by_target_y(image, object, flags);
    /* `neg.w 12(a0)` with nothing branching on it, so 0x8000 negates to itself and the rider keeps
     * walking the way it was — reproduced, not repaired. */
    wr16(image + object + OBJ_TARGET_VX, (uint16_t)-be16(image + object + OBJ_TARGET_VX));
    image[object + OBJ_HATCH_MOUNT] = HATCH_MOUNT_TURNED;
    return tail_by_target_y(image, object, flags);
}

/* ------------------------------------------------------------------------------ the driver */

/* One slot's update: the dispatch at 0x12084 down to whichever tail it ends in, returning the
 * flags word the caller stores back. */
static uint16_t update_object(uint8_t *image, uint32_t object, uint16_t flags,
                              uint32_t rng_cursor, uint16_t *probe) {
    if (flags == 0) return flags;                                   /* a free slot */
    if (flags & OBJ_FLAG_DEAD) return update_dead(image, object, flags);

    uint16_t type = flags & ENEMY_TYPE_MASK;
    if (type == 0) return flags;                                    /* a player, not an enemy */

    if (image[object + OBJ_TURN_TIMER] >= TURN_TIMER_LIMIT) {
        flags ^= OBJ_FLAG_FACING_RIGHT;
        image[object + OBJ_TURN_TIMER] = 0;
    }

    if (type == ENEMY_TYPE_1) return update_type1(image, object, flags, probe);
    if (type == ENEMY_TYPE_2) return update_type2(image, object, flags, rng_cursor, probe);
    return update_type3(image, object, flags);
}

void update_objects(uint8_t *image, uint16_t flags_in, uint16_t probe_in) {
    refresh_active_players(image);

    uint16_t flags = flags_in;
    uint16_t probe = probe_in;
    for (uint32_t object = A_enemy_objects; object != A_object_table_END; object += OBJ_SIZE) {
        /* rng_advance's restart offset comes from D0, which at this point still holds the flags
         * word the PREVIOUS slot stored — see the file header. */
        rng_advance(image, flags);
        uint32_t rng_cursor = be32(image + A_rng_ptr);

        flags = be16(image + object + OBJ_FLAGS);
        flags = update_object(image, object, flags, rng_cursor, &probe);
        wr16(image + object + OBJ_FLAGS, flags);
    }
}

/* ------------------------------------------------------------------------------------ glue ---
 *
 * update_objects takes no designed arguments, but it does read D0 and D2 before writing them (see
 * the file header), so the glue passes both — that is the routine's real entry contract, and the
 * differential drives it with the same two registers.
 */
void g_update_objects(uint8_t *image, uint32_t flags_in, uint32_t probe_in) {
    update_objects(image, (uint16_t)flags_in, (uint16_t)probe_in);
}
