/* collide.c — collision_check @ 0x13842, Joust's per-frame collision resolver.
 *
 * One pass over object_table. For each live slot it runs four sweeps, in this order, and every one
 * of them is the same two-stage test: stage two boxes in hit_box_a / hit_box_b, call test_overlap
 * (which aligns them and hands each shared column to pixel_collision) and read collision_hit.
 *
 *   1. the platforms   — a rider whose sprite overlaps a platform bitmap gets OBJ_FLAG_PLATFORM_BUMP
 *                        and, if it is a player, the bump sound. First match ends the sweep.
 *   2. the other riders — THE JOUST. Only the slots LATER IN THE TABLE are tested, so each
 *                        unordered pair meets exactly once per frame. The higher rider (smaller y)
 *                        wins; a tie bounces both apart. Only a PLAYER can unseat anyone: an enemy
 *                        that happens to be on top merely shoves.
 *   3. the eggs        — a player that touches an egg held by an enemy slot collects it, paying the
 *                        250/500/750/1000 chain from egg_bonus_table and 500 more if the egg is
 *                        still in flight from the dismount that made it.
 *   4. the pterodactyls — a player that touches one dies, unless the bird is exactly one scanline
 *                        above it and it is facing into the bird, in which case the bird dies.
 *
 * Register map of the original, which the structure below follows: a0 = the object whose turn it
 * is, d0 = its flags word, a3 = the other party (rider / platform record / egg holder / bird),
 * d1 = the other party's flags, a1/a2 = the two hit boxes.
 */
#include "machine.h"

#include "collide.h"
#include "egg.h"     /* the egg record the dismount builds, and A_egg_sprite_still */
#include "object.h"  /* the hit boxes, the platform sprites, test_overlap, erase_egg_sprite */
#include "score.h"   /* find_free_message, the score_update family, the message record */
#include "sound.h"   /* play_sound */
#include "world.h"   /* OBJ_FLAG_PLAYER / OBJ_FLAG_REMOVED, start_death_anim, the death sprites */

/* ---- sound_table indices, by what the play triggers ---- */
#define SND_PLATFORM_BUMP   7u
#define SND_JOUST_TIE       0xbu
#define SND_RIDER_UNSEATED  5u
#define SND_EGG_COLLECTED   8u
#define SND_PTERO_LANCED    2u

/* ---- what a hit is worth ----
 * Points are paid by adding straight into the object's ASCII score digits and leaving score_update
 * to carry the decimal columns, so each constant below is an `addq.b` operand and its value is the
 * points divided by the digit's place value. Named by the amount, since that is what the site
 * means; the digit it lands on is spelled at the site itself. */
#define PAY_1000  1u   /* into OBJ_SCORE_LIFE_DIGIT, the thousands */
#define PAY_2000  2u
#define PAY_500   5u   /* into OBJ_SCORE_HUNDREDS, the hundreds */
#define PAY_700   7u
#define PAY_50    5u   /* into OBJ_SCORE_PENDING, the tens */

/* The object's score string: the two digits between score.h's OBJ_SCORE_LIFE_DIGIT (thousands) and
 * world.h's OBJ_SCORE_PENDING (tens), plus the colour byte the message layer borrows. */
#define OBJ_SCORE_HUNDREDS  0x42u  /* .b */
#define OBJ_SCORE_COLOR     0x3du  /* .b — the `02 <colour>` pair OBJ_SCORE_TEXT opens with */

/* first_dismount_owner: which player took the wave's first player-versus-player dismount. The
 * object loop walks the table upwards and the players are its first two slots, so "the object won"
 * always means player 1 and "the object lost" always means player 2. */
#define DISMOUNT_OWNER_P1  1u
#define DISMOUNT_OWNER_P2  2u

/* Both `force_fall_sign` directions, spelled so a call site says which way the rider is thrown. */
#define FALL_UPWARD    0
#define FALL_DOWNWARD  1

/* =================================================================================================
 * Shared helpers.
 * ============================================================================================= */

/* `tst.w 8(an) ; b(ge|le) ; neg.w 8(an)` — point a rider's FALL speed the way the joust sends it,
 * if it is not already going that way. As in joust_bounce (whose force_velocity_sign is this same
 * shape on OBJ_VX, one layer down in src/object.c), the field is written only on the flip, so a vy
 * of exactly 0 is left alone — and `neg.w` of 0 would store the same 0 back anyway. */
static void force_fall_sign(uint8_t *image, uint32_t object, int downward) {
    int16_t vy = (int16_t)be16(image + object + OBJ_VY);
    if (downward ? vy < 0 : vy > 0)
        wr16(image + object + OBJ_VY, (uint16_t)(0u - (uint32_t)(uint16_t)vy));
}

/* Every rider sprite is two cells wide (`move.w #$2,8(a1)`). */
#define RIDER_BOX_COLS 2u

/* A rider's collision box is where its sprite was last DRAWN, not where its coordinates say it is:
 * the pixels on the screen are what the narrow phase walks. Only OBJ_Y comes from the live
 * coordinates, because test_overlap needs a scanline to measure the band with. */
static void stage_rider_box(uint8_t *image, uint32_t box, uint32_t object) {
    wr32(image + box + HB_DST, be32(image + object + OBJ_PREV_DST));
    wr32(image + box + HB_SRC, be32(image + object + OBJ_PREV_SRC));
    wr16(image + box + HB_COLS, RIDER_BOX_COLS);
    image[box + HB_SHIFT] = image[object + OBJ_PREV_SHIFT];
    image[box + HB_ROWS] = image[object + OBJ_PREV_ROWS];
    wr16(image + box + HB_Y, be16(image + object + OBJ_Y));
}

/* =================================================================================================
 * Sweep 1 — the platforms (0x13868..0x13908).
 * ============================================================================================= */

/* A platform's own bitmap record IS its collision box: platform_sprites already holds the source,
 * the cell width and the screen offset draw_platforms blits it at.
 *
 * The row count is read as the LOW BYTE of PSPR_ROWS (`addq.l #1,a3 ; move.b (a3)+,11(a2)`), so a
 * platform more than 255 rows tall would be measured wrong; none is. The box's own y is that screen
 * offset's scanline, and `divu.w` leaves the dividend untouched on overflow — an offset past
 * 0x63ffa0 would therefore carry its own low word into the y field rather than a quotient.
 */
static void stage_platform_box(uint8_t *image, uint32_t sprite) {
    uint32_t dst_off = be32(image + sprite + PSPR_DST_OFF);
    image[A_hit_box_b + HB_ROWS] = image[sprite + PSPR_ROWS + 1];
    wr16(image + A_hit_box_b + HB_COLS, be16(image + sprite + PSPR_COLS));
    wr32(image + A_hit_box_b + HB_SRC, be32(image + sprite + PSPR_SRC));
    image[A_hit_box_b + HB_SHIFT] = 0;
    /* The original stores dst_off and then adds screen_base to the field in place; folding the two
     * into one write is exact — hit_box_b lies below screen_base, so it cannot alias it. */
    wr32(image + A_hit_box_b + HB_DST, dst_off + be32(image + A_screen_base));
    wr16(image + A_hit_box_b + HB_Y, (uint16_t)divu_w(dst_off, SCREEN_ROW_BYTES));
}

/* The platform sweep. hit_box_a is re-staged on EVERY pass, not once before the loop: test_overlap
 * uses the boxes' HB_SRC and HB_CUR_COL as its own cursors, so the previous platform's sweep has
 * left them somewhere else. The first platform that touches ends the sweep. */
static uint32_t hit_platforms(uint8_t *image, uint32_t object, uint32_t flags) {
    for (uint32_t sprite = A_platform_sprites; sprite != A_platform_sprites_END;
         sprite += PSPR_RECORD) {
        stage_rider_box(image, A_hit_box_a, object);
        if (image[be32(image + sprite + PSPR_PRESENT)] == 0) continue;   /* absent this wave */

        stage_platform_box(image, sprite);
        test_overlap(image);
        if (image[A_collision_hit] == 0) continue;

        flags |= OBJ_FLAG_PLATFORM_BUMP;
        wr16(image + object + OBJ_FLAGS, (uint16_t)flags);
        if (flags & OBJ_FLAG_PLAYER) play_sound(image, SND_PLATFORM_BUMP);
        return flags;
    }
    return flags;
}

/* =================================================================================================
 * Sweep 2 — the joust (0x13912..0x13b96).
 * ============================================================================================= */

/* joust_bounce adjusts the facing bit of BOTH flags words and commits each to its own record, so
 * the record is where the original's D0 now is. Reading it back is how the loop carries D0 on. */
static uint32_t bounce_apart(uint8_t *image, uint32_t object, uint32_t other,
                             uint32_t flags, uint32_t other_flags) {
    joust_bounce(image, object, other, (uint16_t)flags, (uint16_t)other_flags);
    return be16(image + object + OBJ_FLAGS);
}

/* The shared tail of a joust one rider does not survive (0x13a9a..0x13ac4, reached from both sides
 * of the height test): both HUD scores are redrawn, the clash sound plays, the pair bounce apart
 * and the winner is thrown upward.
 *
 * `object`/`other` keep the loop's own pairing because that is the order joust_bounce measures the
 * horizontal gap in; `winner` says which of the two the upward shove goes to. The original then
 * re-stores the LOSER's flags word — but joust_bounce has just committed that same register to that
 * same field, so the store puts back what is already there and is not repeated here.
 */
static uint32_t settle_fatal_joust(uint8_t *image, uint32_t object, uint32_t other,
                                   uint32_t flags, uint32_t other_flags, uint32_t winner) {
    score_update_p1(image);
    score_update_p2(image);
    play_sound(image, SND_RIDER_UNSEATED);
    flags = bounce_apart(image, object, other, flags, other_flags);
    force_fall_sign(image, winner, FALL_UPWARD);
    return flags;
}

/* The gladiator bonus. A player-versus-player dismount always pays 500 and raises
 * player_conflict_flag; the wave's FIRST one pays 2500 more — 3000 in all — but only once the
 * wave's gladiator countdown has reached 0 and only while no dismount has been claimed yet. Note
 * that the extra is TWO `addq.b`s, +2 on the thousands and a second +5 on the hundreds, so
 * score_update's carry sweep is what finally turns it into a 3 in the thousands column. */
static void pay_player_duel(uint8_t *image, uint32_t winner, uint8_t owner) {
    image[A_player_conflict_flag] = 1;
    image[winner + OBJ_SCORE_HUNDREDS] += PAY_500;
    if (image[A_gladiator_wave_countdown] != 0) return;
    if (image[A_first_dismount_owner] != 0) return;
    image[A_first_dismount_owner] = owner;
    image[winner + OBJ_SCORE_LIFE_DIGIT] += PAY_2000;
    image[winner + OBJ_SCORE_HUNDREDS] += PAY_500;
}

/* The dismount (0x13b00..0x13b7a): the unseated enemy's own record is turned into the egg it drops.
 * The egg inherits the rider's position (five scanlines lower), its velocity and its pixel phase,
 * and starts six scanlines below where the rider was last drawn.
 *
 * OBJ_EGG_SPAWN_FLAGS is the handshake with the egg subsystem (`cmt 0x12606`): its low bits are the
 * rider type the hatched rider will inherit — this rider's own type bumped by one and capped at the
 * top type, so each generation comes back tougher — and EGG_SPAWN_UNDRAWN says the egg has never
 * been drawn, so update_egg_draw skips the erase on its first frame.
 */
#define EGG_DROP_DY       5u    /* `addq.w #5` on the rider's y */
#define EGG_DROP_ROWS     6u    /* `addi.l #$3c0` on the rider's last screen address */
#define EGG_FALL_FRAMES   6u
#define EGG_ROLL_FRAMES   4u
#define EGG_SPRITE_ROWS   7u
#define EGG_HATCH_FRAMES  0x88u /* the hatch wait, less wave_num: later waves hatch sooner */

static void dismount_egg(uint8_t *image, uint32_t rider, uint32_t rider_flags) {
    wr16(image + rider + OBJ_EGG_X, be16(image + rider + OBJ_X));
    wr16(image + rider + OBJ_EGG_Y, (uint16_t)(be16(image + rider + OBJ_Y) + EGG_DROP_DY));
    wr16(image + rider + OBJ_EGG_DX, be16(image + rider + OBJ_VX));
    wr16(image + rider + OBJ_EGG_DY, be16(image + rider + OBJ_VY));
    image[rider + OBJ_EGG_FALL_TIMER] = EGG_FALL_FRAMES;
    image[rider + OBJ_EGG_ROLL_TIMER] = EGG_ROLL_FRAMES;
    wr32(image + rider + OBJ_EGG_DST,
         be32(image + rider + OBJ_PREV_DST) + EGG_DROP_ROWS * SCREEN_ROW_BYTES);
    image[rider + OBJ_EGG_SHIFT] = image[rider + OBJ_PREV_SHIFT];
    /* Written as `move.b #$88` then `sub.b wave_num` to the same byte; the intermediate is never
     * read, and wave_num lies well below object_table so it cannot be the byte being written. */
    image[rider + OBJ_EGG_HATCH_TIMER] = (uint8_t)(EGG_HATCH_FRAMES - image[A_wave_num]);
    wr32(image + rider + OBJ_EGG_SRC, A_egg_sprite_still);
    image[rider + OBJ_EGG_ROWS] = EGG_SPRITE_ROWS;
    image[rider + OBJ_EGG_STATE] = EGG_STATE_THROWN;

    /* `andi.b #$3` then `cmpi.b #$3` — the hatched rider is one type harder than its parent, and
     * type 3 is already the hardest. */
    uint8_t hatched_type = (uint8_t)(rider_flags & ENEMY_TYPE_MASK);
    if (hatched_type != ENEMY_TYPE_3) hatched_type++;
    image[rider + OBJ_EGG_SPAWN_FLAGS] = (uint8_t)(hatched_type | EGG_SPAWN_UNDRAWN);
}

/* A player unseating an ENEMY (0x13ac8..0x13b7c). The bounty is read off the enemy's type bits: 500
 * for type 1, 1500 for type 3, and 750 for the two shapes with bit 0 clear (types 0 and 2). The
 * enemy's score digits are never touched — the player is paid — and the enemy's record becomes the
 * egg it drops. */
static uint32_t unseat_enemy(uint8_t *image, uint32_t player, uint32_t enemy,
                             uint32_t enemy_flags) {
    enemy_flags |= OBJ_FLAG_DEAD | OBJ_FLAG_REMOVED;

    if (enemy_flags & OBJ_FLAG_TYPE_LO) {
        image[player + OBJ_SCORE_HUNDREDS] += PAY_500;
        if (enemy_flags & OBJ_FLAG_TYPE_HI) image[player + OBJ_SCORE_LIFE_DIGIT] += PAY_1000;
    } else {
        image[player + OBJ_SCORE_HUNDREDS] += PAY_700;
        image[player + OBJ_SCORE_PENDING] += PAY_50;
    }
    score_update(image, player);
    play_sound(image, SND_RIDER_UNSEATED);
    dismount_egg(image, enemy, enemy_flags);
    return enemy_flags;
}

/* The joust sweep. `other` starts one slot LATER IN THE TABLE than `object`, so every unordered
 * pair of live riders is tested exactly once per frame — which is why the "object loses" and
 * "object wins" branches below both have to be complete, rather than one of them being reached on
 * the other rider's own turn.
 *
 * Returns the object's flags word. It leaves the loop early on exactly one path: the object is a
 * player and it is the one being unseated, after which there is nothing left for it to bump into.
 */
static uint32_t joust_riders(uint8_t *image, uint32_t object, uint32_t flags) {
    for (uint32_t other = object + OBJ_SIZE; other != A_object_table_END; other += OBJ_SIZE) {
        uint32_t other_flags = be16(image + other + OBJ_FLAGS);
        if (other_flags == 0) continue;                                   /* empty slot */
        if (other_flags & (OBJ_FLAG_DEAD | OBJ_FLAG_RESPAWN)) continue;   /* not on the playfield */

        stage_rider_box(image, A_hit_box_a, object);
        stage_rider_box(image, A_hit_box_b, other);
        test_overlap(image);
        if (image[A_collision_hit] == 0) continue;

        /* Smaller y is higher up the screen, and the higher lance wins. */
        int16_t other_y = (int16_t)be16(image + other + OBJ_Y);
        int16_t object_y = (int16_t)be16(image + object + OBJ_Y);
        if (other_y == object_y) {                       /* a dead heat: neither is unseated */
            play_sound(image, SND_JOUST_TIE);
            flags = bounce_apart(image, object, other, flags, other_flags);
            continue;
        }

        uint32_t winner = other_y > object_y ? object : other;
        uint32_t loser = other_y > object_y ? other : object;
        if (!(flags & OBJ_FLAG_PLAYER)) {
            /* Only a player can unseat anyone. Between two enemies, or when an enemy is the one on
             * top, the pair just get pushed apart vertically as well as horizontally. */
            force_fall_sign(image, loser, FALL_DOWNWARD);
            force_fall_sign(image, winner, FALL_UPWARD);
            flags = bounce_apart(image, object, other, flags, other_flags);
            continue;
        }

        if (winner == object) {
            if (other_flags & OBJ_FLAG_PLAYER) {
                other_flags = start_death_anim(image, other, other_flags);
                pay_player_duel(image, object, DISMOUNT_OWNER_P1);
            } else {
                other_flags = unseat_enemy(image, object, other, other_flags);
            }
            flags = settle_fatal_joust(image, object, other, flags, other_flags, object);
            continue;
        }

        /* The object is the player being unseated. */
        if (other_flags & OBJ_FLAG_PLAYER) pay_player_duel(image, other, DISMOUNT_OWNER_P2);
        if (image[A_players_alive] == 1) image[A_player_conflict_flag] = 1;
        flags = start_death_anim(image, object, flags);
        return settle_fatal_joust(image, object, other, flags, other_flags, other);
    }
    return flags;
}

/* =================================================================================================
 * Sweep 3 — the eggs (0x13b9a..0x13d1a).
 * ============================================================================================= */

/* The sweep starts at object_table slot 2 (names.txt's enemy_objects), so neither player's own egg
 * record — which is what start_death_anim turns a dying player into — is ever collectable. */
#define EGG_SWEEP_FIRST_SLOT  2u

#define MSG_BONUS_FRAMES  0x32u  /* how long either message stays on screen */
#define MSG_BONUS_COLOR   6u     /* the in-flight bonus draws in its own colour; the chain message
                                  * takes the collector's, out of its score string */
#define EGG_CHAIN_TOP     3u     /* `cmpi.b #$3` — the chain stops climbing at the 1000 record */
/* "500", the text the in-flight bonus draws. The original holds it as its own relocated immediate,
 * and it is also what egg_bonus_table's second record points at. */
#define STR_BONUS_500     0x18608u

/* Where a bonus message is painted, relative to the egg's own screen address. */
#define MSG_INFLIGHT_RISE      (5u * SCREEN_ROW_BYTES)                 /* `subi.l #$320` */
#define MSG_INFLIGHT_FALLBACK  (SCREEN_ROW_BYTES + CELL_BYTES)         /* `addi.l #$a8` */
#define MSG_CHAIN_DROP         SCREEN_ROW_BYTES                        /* `addi.l #$a0` */

/* Fill in the fields both bonus messages share. `msg` is whatever find_free_message handed back —
 * INCLUDING 0 when the table is full, in which case the record is written over image addresses
 * 0..0xb. That is the same original bug player_death carries, reproduced rather than guarded. */
static void fill_bonus_message(uint8_t *image, uint32_t msg, uint32_t string, uint32_t screen_ptr,
                               uint8_t shift, uint8_t color) {
    wr32(image + msg + MSG_STRING, string);
    wr32(image + msg + MSG_SCREEN_PTR, screen_ptr);
    image[msg + MSG_SHIFT] = shift;
    image[msg + MSG_TIMER] = MSG_BONUS_FRAMES;
    image[msg + MSG_KIND] = MSG_KIND_PERSISTENT;
    image[msg + MSG_COLOR] = color;
}

/* The extra 500 for catching an egg that is still in flight from the dismount that made it. Its
 * message floats five scanlines above the egg — unless that would put it at or above screen_base
 * (a SIGNED `cmp.l`), in which case it goes one scanline BELOW and one cell right instead.
 * Claiming the slot's kind byte here is what stops the chain message below from finding the same
 * free slot. */
static void pay_egg_in_flight(uint8_t *image, uint32_t player, uint32_t egg_holder) {
    uint32_t egg_dst = be32(image + egg_holder + OBJ_EGG_DST);
    uint32_t above = egg_dst - MSG_INFLIGHT_RISE;
    if ((int32_t)be32(image + A_screen_base) >= (int32_t)above)
        above = egg_dst + MSG_INFLIGHT_FALLBACK;

    fill_bonus_message(image, find_free_message(image), STR_BONUS_500, above,
                       image[egg_holder + OBJ_EGG_SHIFT], MSG_BONUS_COLOR);
    image[player + OBJ_SCORE_HUNDREDS] += PAY_500;
}

/* The consecutive-egg chain: each egg a player catches without dying is worth more than the last,
 * 250 then 500 then 750 then 1000, and the counter sticks at the top record. The three digit
 * increments come straight out of the record, so the amounts live in the game's data, not here. */
static void pay_egg_chain(uint8_t *image, uint32_t player, uint32_t egg_holder) {
    /* `clr.w d5 ; move.b OBJ_EGG_CHAIN,d5 ; lsl.l #3` then a WORD index: the counter is a byte, so
     * the scaled index tops out at 0x7f8 and its sign extension can never bite. It is not bounds
     * checked either — a counter poked past 3 reads past the table. */
    uint32_t bonus = A_egg_bonus_table + (uint32_t)image[player + OBJ_EGG_CHAIN] * BONUS_RECORD;

    fill_bonus_message(image, find_free_message(image), be32(image + bonus + BONUS_STRING),
                       be32(image + egg_holder + OBJ_EGG_DST) + MSG_CHAIN_DROP,
                       image[egg_holder + OBJ_EGG_SHIFT], image[player + OBJ_SCORE_COLOR]);

    image[player + OBJ_SCORE_LIFE_DIGIT] += image[bonus + BONUS_THOUSANDS];
    image[player + OBJ_SCORE_HUNDREDS] += image[bonus + BONUS_HUNDREDS];
    image[player + OBJ_SCORE_PENDING] += image[bonus + BONUS_TENS];
    if (image[player + OBJ_EGG_CHAIN] != EGG_CHAIN_TOP) image[player + OBJ_EGG_CHAIN]++;
}

/* The egg sweep, players only. The box the egg is tested with is the egg record's own draw state,
 * so — as with the riders — it is the pixels the last frame put on the screen that are compared.
 *
 * The original swaps the player into A4 across this whole block so that A0 is free for the message
 * records find_free_message hands back, and restores it with `movea.l a4,a0` before the erase. One
 * step of that dance is dead: `movea.l (a7),a0` at 0x13c76 loads the routine's own return address
 * into A0, which the next find_free_message call overwrites before anything reads it.
 */
static void collect_eggs(uint8_t *image, uint32_t player) {
    for (uint32_t holder = A_object_table + EGG_SWEEP_FIRST_SLOT * OBJ_SIZE;
         holder != A_object_table_END; holder += OBJ_SIZE) {
        if (image[holder + OBJ_EGG_STATE] == 0) continue;         /* this slot carries no egg */

        stage_rider_box(image, A_hit_box_a, player);
        wr32(image + A_hit_box_b + HB_DST, be32(image + holder + OBJ_EGG_DST));
        wr32(image + A_hit_box_b + HB_SRC, be32(image + holder + OBJ_EGG_SRC));
        wr16(image + A_hit_box_b + HB_COLS, RIDER_BOX_COLS);
        image[A_hit_box_b + HB_SHIFT] = image[holder + OBJ_EGG_SHIFT];
        image[A_hit_box_b + HB_ROWS] = image[holder + OBJ_EGG_ROWS];
        wr16(image + A_hit_box_b + HB_Y, be16(image + holder + OBJ_EGG_Y));
        test_overlap(image);
        if (image[A_collision_hit] == 0) continue;

        if (image[holder + OBJ_EGG_STATE] == EGG_STATE_THROWN)
            pay_egg_in_flight(image, player, holder);
        pay_egg_chain(image, player, holder);

        play_sound(image, SND_EGG_COLLECTED);
        if (player == A_object_table) score_update_p1(image);
        if (player == A_player2) score_update_p2(image);
        image[holder + OBJ_EGG_STATE] = 0;
        erase_egg_sprite(image, holder);
    }
}

/* =================================================================================================
 * Sweep 4 — the pterodactyls (0x13d1e..0x13ee6).
 * ============================================================================================= */

#define PTERO_BOX_COLS  3u       /* `move.w #$3,8(a2)` — the bird is three cells wide */
#define PTERO_DEATH_TIMERS  4u   /* both byte timers are armed to this on the frame it is lanced */

/* The lance connects only when the bird is exactly one scanline above the player. */
#define PTERO_LANCE_DY  0xffffu  /* `cmpi.w #$ffff` — an exact word compare, not a band */
/* Bird flying LEFT, into a right-facing player. The SIGNED bound caps the gap at 0x11 pixels to the
 * player's right; the UNSIGNED one then throws out the near-negative gaps, -1 down to -0x12e. What
 * survives on that side is -0x12f and beyond, which — x wrapping at 320 — is the same bird just to
 * the player's right, measured the other way round the screen. */
#define PTERO_LEFT_GAP_MAX   ((int16_t)0x11)   /* `cmpi.w #$11` + bgt: SIGNED */
#define PTERO_LEFT_GAP_WRAP  0xfed1u           /* `cmpi.w #$fed1` + bhi: UNSIGNED */
/* Bird flying RIGHT, into a left-facing player: the mirror window, biased by 0xf BEFORE the two
 * compares so the same pair of constants can express it. */
#define PTERO_RIGHT_GAP_BIAS  0xfu
#define PTERO_RIGHT_GAP_MIN   ((int16_t)0xfff0)  /* `cmpi.w #$fff0` + blt: SIGNED */
#define PTERO_RIGHT_GAP_WRAP  0x130u             /* `cmpi.w #$130`  + bcs: UNSIGNED */

/* Does the player's lance beat the bird? Both directions want the player facing INTO the bird and
 * the bird just ahead of the lance; everything else — including touching it from behind, or being
 * level with it rather than one row under it — kills the player instead. */
static int lance_connects(uint8_t *image, uint32_t player, uint32_t flags, uint32_t ptero,
                          uint32_t ptero_flags) {
    if ((uint16_t)(be16(image + ptero + PT_Y) - be16(image + player + OBJ_Y)) != PTERO_LANCE_DY)
        return 0;

    uint16_t gap = (uint16_t)(be16(image + ptero + PT_X) - be16(image + player + OBJ_X));
    if (ptero_flags & PT_FLAG_MOVING_RIGHT) {
        if (flags & OBJ_FLAG_FACING_RIGHT) return 0;
        gap = (uint16_t)(gap + PTERO_RIGHT_GAP_BIAS);
        return (int16_t)gap >= PTERO_RIGHT_GAP_MIN && gap >= PTERO_RIGHT_GAP_WRAP;
    }
    if (!(flags & OBJ_FLAG_FACING_RIGHT)) return 0;
    return (int16_t)gap <= PTERO_LEFT_GAP_MAX && gap <= PTERO_LEFT_GAP_WRAP;
}

/* The bird dies: it is marked dying, both of its byte timers are armed for the death animation, and
 * the player is turned round, pushed the other way and paid 1000. */
static uint32_t lance_pterodactyl(uint8_t *image, uint32_t player, uint32_t flags,
                                  uint32_t ptero, uint32_t ptero_flags) {
    ptero_flags |= PT_FLAG_DYING;
    image[ptero + PT_SWOOP_TIMER] = PTERO_DEATH_TIMERS;
    image[ptero + PT_DWELL_TIMER] = PTERO_DEATH_TIMERS;
    play_sound(image, SND_PTERO_LANCED);
    wr16(image + ptero + PT_FLAGS, (uint16_t)ptero_flags);

    flags ^= OBJ_FLAG_FACING_RIGHT;                              /* `bchg #15,d0` */
    wr16(image + player + OBJ_TARGET_VX,
         (uint16_t)(0u - be16(image + player + OBJ_TARGET_VX)));
    wr16(image + player + OBJ_VX, (uint16_t)(0u - be16(image + player + OBJ_VX)));
    image[player + OBJ_SCORE_LIFE_DIGIT] += PAY_1000;
    wr16(image + player + OBJ_FLAGS, (uint16_t)flags);
    score_update(image, player);
    return flags;
}

/* KNOWN DUPLICATE. The block below is start_death_anim's body (src/world.c, 0x14098) copied inline
 * by the original compiler, minus its `clr.b OBJ_EGG_CHAIN` — so a player killed by a bird keeps
 * the consecutive-egg chain it had built up, where a player unseated in a joust loses it. Its five
 * constants are spelled in src/world.c as DEATH_SPRITE_RISE / DEATH_SPRITE_ROWS /
 * DEATH_EGG_STATE_P1 / DEATH_EGG_STATE_OTHER / DEATH_SCORE_HUNDREDS, private to that file;
 * collapsing the copies means hoisting them into include/world.h, which is the world layer's call.
 * Flagged rather than papered over. */
#define LANCED_SPRITE_RISE      0x280u  /* four scanlines: the dismount starts above the rider */
#define LANCED_SPRITE_ROWS      9u
#define LANCED_EGG_STATE_P1     0x19u
#define LANCED_EGG_STATE_OTHER  0x20u

static uint32_t player_lanced(uint8_t *image, uint32_t player, uint32_t flags) {
    image[A_player_conflict_flag] = 1;
    flags |= OBJ_FLAG_DEAD | OBJ_FLAG_REMOVED;

    uint32_t rider_dst = be32(image + player + OBJ_PREV_DST);
    uint32_t death_dst = rider_dst - LANCED_SPRITE_RISE;
    if ((int32_t)be32(image + A_screen_base) >= (int32_t)death_dst) death_dst = rider_dst;
    wr32(image + player + OBJ_EGG_DST, death_dst);

    image[player + OBJ_EGG_SHIFT] = image[player + OBJ_PREV_SHIFT];
    image[player + OBJ_EGG_ROWS] = LANCED_SPRITE_ROWS;

    int is_player1 = player == A_object_table;
    image[player + OBJ_EGG_STATE] = is_player1 ? LANCED_EGG_STATE_P1 : LANCED_EGG_STATE_OTHER;
    wr32(image + player + OBJ_EGG_SRC, is_player1 ? A_death_sprite_p1 : A_death_sprite_other);

    image[player + OBJ_SCORE_PENDING] += PAY_50;
    wr16(image + player + OBJ_FLAGS, (uint16_t)flags);
    score_update(image, player);
    play_sound(image, SND_RIDER_UNSEATED);
    return flags;
}

/* The pterodactyl sweep, players only and only while the player is still alive. The bird's box is
 * assembled from three pieces — a screen address, screen_base and a SIGN-extended offset — and its
 * y is its own y plus that offset's scanline count. The first bird that touches ends the sweep,
 * whichever way the exchange goes. */
static void joust_pterodactyls(uint8_t *image, uint32_t player, uint32_t flags) {
    for (uint32_t ptero = A_pterodactyl_table; ptero != A_pterodactyl_table_END;
         ptero += PT_RECORD) {
        uint32_t ptero_flags = be16(image + ptero + PT_FLAGS);
        if (ptero_flags == 0) continue;                                        /* empty slot */
        if (ptero_flags & (PT_FLAG_JUST_SPAWNED | PT_FLAG_DYING)) continue;    /* not solid */

        stage_rider_box(image, A_hit_box_a, player);
        uint32_t dst_off = be16(image + ptero + PT_DST_OFF);
        wr32(image + A_hit_box_b + HB_DST, be32(image + ptero + PT_DST)
             + be32(image + A_screen_base) + sign_ext16(dst_off));
        wr32(image + A_hit_box_b + HB_SRC, be32(image + ptero + PT_SRC));
        wr16(image + A_hit_box_b + HB_COLS, PTERO_BOX_COLS);
        image[A_hit_box_b + HB_SHIFT] = image[ptero + PT_SHIFT];
        image[A_hit_box_b + HB_ROWS] = image[ptero + PT_ROWS];
        wr16(image + A_hit_box_b + HB_Y, (uint16_t)(be16(image + ptero + PT_Y)
                                                    + (uint16_t)divu_w(dst_off, SCREEN_ROW_BYTES)));
        test_overlap(image);
        if (image[A_collision_hit] == 0) continue;

        if (lance_connects(image, player, flags, ptero, ptero_flags))
            lance_pterodactyl(image, player, flags, ptero, ptero_flags);
        else
            player_lanced(image, player, flags);
        return;
    }
}

/* =================================================================================================
 * collision_check @ 0x13842.
 * ============================================================================================= */

void collision_check(uint8_t *image) {
    for (uint32_t object = A_object_table; object != A_object_table_END; object += OBJ_SIZE) {
        uint32_t flags = be16(image + object + OBJ_FLAGS);
        if (flags == 0) continue;                        /* empty slot */
        if (flags & OBJ_FLAG_RESPAWN) continue;          /* not on the playfield yet */

        flags = hit_platforms(image, object, flags);
        if (flags & OBJ_FLAG_DEAD) continue;             /* a corpse still bumps platforms */

        flags = joust_riders(image, object, flags);
        if (!(flags & OBJ_FLAG_PLAYER)) continue;        /* eggs and birds are a player's business */

        collect_eggs(image, object);
        /* Re-tested because the joust above can have killed this player on its way here; the eggs
         * are still collected on the frame it dies, but it can no longer trade with a bird. */
        if (flags & OBJ_FLAG_DEAD) continue;
        joust_pterodactyls(image, object, flags);
    }
}

/* ------------------------------------------------------------------------------------- glue ---
 *
 * collision_check takes no arguments and returns nothing: it walks object_table itself and every
 * result it produces is a memory write, so the image diff sees all of it. */
void g_collision_check(uint8_t *image) {
    collision_check(image);
}
