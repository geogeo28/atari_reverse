/* weapons.c — everything that shoots and everything that is shot at: the player's three five-shot
 * slots, the smart bomb and its blast, the enemy bullets, the turret barrels, the two collision
 * passes with their twenty-three hit handlers, and the level spawn script.
 *
 * THE 68000 X FLAG IS AN ARGUMENT HERE, and it is the one thing about this file that is not
 * obvious. Half the hit handlers end in a `bsr`/`bra` into the score chain, whose first instruction
 * is an `abcd` that ADDS X (include/hud.h) — so the score a hit awards depends on a condition code
 * the handler inherited from its caller. Every step of that inheritance is a plain 68000 rule and
 * none of it is guessed: `Scc`, `move`, `clr`, `tst`, `cmp`, `movem` and `lea` leave X alone, an
 * `addi`/`subi` sets it, `lsl` sets it to the last bit shifted out, and the four sfx wrappers
 * (0x121ce and siblings) pass it straight through — their module entry @ 0x58df0 executes nothing
 * that writes X. So each handler below takes the X its dispatcher left and threads the value the
 * original's flags would have carried.
 *
 * NO SEAMS: every routine a handler reaches is ported, `item_drop_if_formation_cleared` @ 0x121fe
 * (src/entity.c) and the score chain behind it included, so the handlers below are diffed whole.
 */
#include "machine.h"
#include "common.h"  /* SCC_TRUE, the one spelling of the `Scc` byte every core here stores */
#include "player.h"  /* the player record: every aim point and hit box is measured from it */
#include "weapons.h"

/* clear_object_list @ 0x115fc — word-clear the enemy-bullet array up to its own sentinel.
 *
 * ../names.txt files this under the boot chain's neighbours, but the only array it touches is
 * `A_enemy_bullets` and the only routine here that calls it is `bomb_blast_step`, so it is ported
 * with the data. Every word of a record is cleared, ENEMY_BULLET_ACTIVE included, which is why the
 * walk has to test the sentinel BEFORE it clears rather than after. */
void clear_object_list(uint8_t *image) {
    uint32_t word;
    for (word = A_enemy_bullets; be16(image + word) != ENEMY_BULLET_END; word += 2)
        wr16(image + word, 0);
}

/* ================================================================================================
 * The smart bomb: the fall, the impact, and the blast that follows it.
 * ============================================================================================= */

/* bomb_fall_step @ 0x10e7c — walk the dropped bomb down its fall path, then arm the blast.
 *
 * The path's dy is added to BOMB_START_Y and not to the live row, so the table is an absolute
 * profile rather than a per-frame delta. */
void bomb_fall_step(uint8_t *image) {
    if (be16(image + A_bomb_falling) == 0)
        return;

    if (be16(image + A_bomb_exploding) == 0) {
        uint32_t step = A_bomb_fall_path + be32(image + A_bomb_path_cursor);
        if (be16(image + step + BOMB_PATH_DY) != SCRIPT_TERMINATOR) {
            wr16(image + A_player_bomb + BOMB_FRAME, be16(image + step + BOMB_PATH_FRAME));
            wr16(image + A_player_bomb + BOMB_Y,
                 be16(image + A_player_bomb + BOMB_START_Y) + be16(image + step + BOMB_PATH_DY));
            wr32(image + A_bomb_path_cursor,
                 be32(image + A_bomb_path_cursor) + BOMB_PATH_STEP_BYTES);
            return;
        }
    }

    wr16(image + A_blast_state + BLAST_X, be16(image + A_player_bomb + BOMB_X));
    wr16(image + A_blast_state + BLAST_Y, be16(image + A_player_bomb + BOMB_Y));
    wr16(image + A_bomb_falling, 0);
    image[A_bomb_exploding] = SCC_TRUE;   /* `st $176f0`: the high byte of the word only */
}

/* bomb_publish @ 0x10ee2 — one display record while the bomb is in the air, cleared otherwise. */
void bomb_publish(uint8_t *image) {
    if (be16(image + A_bomb_falling) == 0 || be16(image + A_bomb_exploding) != 0) {
        wr16(image + A_dl_bomb + DISPLAY_REC_X, 0);
        wr16(image + A_dl_bomb + DISPLAY_REC_Y, 0);
        image[A_dl_bomb + DISPLAY_REC_FRAME] = 0;
        image[A_dl_bomb + DISPLAY_REC_ACTIVE] = 0;
        return;
    }
    wr16(image + A_dl_bomb + DISPLAY_REC_X, be16(image + A_player_bomb + BOMB_X));
    wr16(image + A_dl_bomb + DISPLAY_REC_Y, be16(image + A_player_bomb + BOMB_Y));
    image[A_dl_bomb + DISPLAY_REC_FRAME] = (uint8_t)be16(image + A_player_bomb + BOMB_FRAME);
    image[A_dl_bomb + DISPLAY_REC_ACTIVE] = DISPLAY_ACTIVE_ON_TOP;
}

/* bomb_blast_step @ 0x10c8c — advance the blast, or retire it at the last step.
 *
 * `clear_object_list` and the explosion sound go off on EVERY step, not only the first: the
 * enemy-bullet array is wiped and the effect retriggered once a frame for the blast's whole life.
 *
 * D0 IS AN INPUT, and an accidental one. `move.w $176ec,d0 / lsl.w #3,d0 / adda.l d0,a0` loads only
 * the low word and never touches the high one, and the add is a LONG — so which row of
 * `A_blast_offset_tbl` the routine reads depends on what its caller left in the top half of D0.
 * Reproduced rather than assumed away, and the value is MEASURED and not assumed: the only call
 * site is `frame_loop_once` @ 0x157d4, and
 * `test_init.py::test_the_frame_loops_register_carries_are_what_the_original_leaves` reads D0 out
 * of the ORACLE there over every staged frame. Its high word is 0 on all of them (its LOW word is
 * not, and is overwritten below);
 * `test_weapons.py::test_blast_step_indexes_the_table_with_the_WHOLE_of_d0` is the case that proves
 * the dependency is real. */
void bomb_blast_step(uint8_t *image, uint32_t scratch) {
    uint32_t offsets;
    unsigned point;

    if (be16(image + A_bomb_exploding) == 0)
        return;

    clear_object_list(image);
    sfx_play_10(image);

    if (be16(image + A_blast_step) >= BLAST_LAST_STEP) {
        wr16(image + A_blast_step, 0);
        wr16(image + A_bomb_exploding, 0);
        wr16(image + A_bomb_falling, 0);
        wr32(image + A_bomb_path_cursor, 0);
        return;
    }

    offsets = addr_add(A_blast_offset_tbl,
                       (scratch & 0xffff0000u)
                       | (uint16_t)(be16(image + A_blast_step) * BLAST_OFFSET_STEP_BYTES));
    wr16(image + A_blast_step, be16(image + A_blast_step) + 1);
    for (point = 0; point < BLAST_POINTS_COUNT; point++) {
        uint32_t slot = A_blast_state + BLAST_POINTS + point * BLAST_POINT_BYTES;
        wr16(image + slot + 0, be16(image + A_blast_state + BLAST_X)
                               + (uint16_t)sign_ext8(image[offsets + point * 2]));
        wr16(image + slot + 2, be16(image + A_blast_state + BLAST_Y)
                               + (uint16_t)sign_ext8(image[offsets + point * 2 + 1]));
    }
}

/* bomb_blast_publish @ 0x10d20 — the blast's four sprites, or four cleared records. */
void bomb_blast_publish(uint8_t *image) {
    int exploding = be16(image + A_bomb_exploding) != 0;
    unsigned point;

    for (point = 0; point < BLAST_POINTS_COUNT; point++) {
        uint32_t record = A_dl_blast + point * DISPLAY_REC_BYTES;
        uint32_t slot = A_blast_state + BLAST_POINTS + point * BLAST_POINT_BYTES;
        wr16(image + record + DISPLAY_REC_X, exploding ? be16(image + slot + 0) : 0);
        wr16(image + record + DISPLAY_REC_Y, exploding ? be16(image + slot + 2) : 0);
        image[record + DISPLAY_REC_FRAME] = exploding ? BLAST_GLYPH : 0;
        image[record + DISPLAY_REC_ACTIVE] = exploding ? DISPLAY_ACTIVE_ON_TOP : 0;
    }
}

/* ================================================================================================
 * The player's bullets.
 * ============================================================================================= */

/* player_bullets_move_group @ 0x140ea — step one shot's five bullets.
 *
 * REPRODUCES A QUIRK: only PLAYER_BULLET_HIT short-circuits the step, so a FREE slot is moved too —
 * its dead x and y drift every frame until the retire test frees it again. Nothing reads either
 * field while the state is free, so it is invisible on screen and visible in the diff. */
void player_bullets_move_group(uint8_t *image, uint32_t slots) {
    unsigned index;
    for (index = 0; index < PLAYER_SHOT_BULLETS; index++) {
        uint32_t bullet = be32(image + slots + index * ENTITY_GROUP_PTR_BYTES);
        if (be16(image + bullet + PLAYER_BULLET_STATE) != PLAYER_BULLET_HIT) {
            wr16(image + bullet + PLAYER_BULLET_X, be16(image + bullet + PLAYER_BULLET_X)
                                                   + be16(image + bullet + PLAYER_BULLET_DX));
            wr16(image + bullet + PLAYER_BULLET_Y,
                 be16(image + bullet + PLAYER_BULLET_Y) - PLAYER_BULLET_DY);
            if ((int16_t)be16(image + bullet + PLAYER_BULLET_Y)
                > (int16_t)(uint16_t)PLAYER_BULLET_RETIRE_Y)
                continue;
        }
        wr16(image + bullet + PLAYER_BULLET_STATE, PLAYER_BULLET_FREE);
    }
}

void player_bullets_move_all(uint8_t *image) {
    unsigned shot;
    for (shot = 0; shot < PLAYER_SHOT_SLOTS; shot++)
        player_bullets_move_group(image, A_player_shot_slot_0 + shot * PLAYER_SHOT_TABLE_STRIDE);
}

/* player_bullets_publish_group @ 0x14148 — one shot's five display records.
 *
 * The impact state draws frame PLAYER_BULLET_IMPACT_GLYPH for exactly one frame and frees the slot
 * in the same pass, so nothing else has to retire it. */
void player_bullets_publish_group(uint8_t *image, uint32_t slots, uint32_t records) {
    unsigned index;
    for (index = 0; index < PLAYER_SHOT_BULLETS; index++) {
        uint32_t bullet = be32(image + slots + index * ENTITY_GROUP_PTR_BYTES);
        uint32_t record = records + index * DISPLAY_REC_BYTES;
        uint16_t state = be16(image + bullet + PLAYER_BULLET_STATE);

        if (state == PLAYER_BULLET_FREE) {
            wr16(image + record + DISPLAY_REC_X, 0);
            wr16(image + record + DISPLAY_REC_Y, 0);
            image[record + DISPLAY_REC_FRAME] = 0;
            image[record + DISPLAY_REC_ACTIVE] = 0;
            continue;
        }

        wr16(image + record + DISPLAY_REC_X, be16(image + bullet + PLAYER_BULLET_X));
        wr16(image + record + DISPLAY_REC_Y, be16(image + bullet + PLAYER_BULLET_Y));
        if (state == PLAYER_BULLET_HIT) {
            image[record + DISPLAY_REC_FRAME] = PLAYER_BULLET_IMPACT_GLYPH;
            image[record + DISPLAY_REC_ACTIVE] = DISPLAY_ACTIVE_ON_TOP;
            wr16(image + bullet + PLAYER_BULLET_STATE, PLAYER_BULLET_FREE);
            continue;
        }
        image[record + DISPLAY_REC_FRAME] = image[A_alt_bullet_glyph_flag] != 0
                                          ? PLAYER_BULLET_GLYPH_ALT : PLAYER_BULLET_GLYPH;
        image[record + DISPLAY_REC_ACTIVE] = DISPLAY_ACTIVE_ON_TOP;
    }
}

void player_bullets_publish_all(uint8_t *image) {
    unsigned shot;
    for (shot = 0; shot < PLAYER_SHOT_SLOTS; shot++)
        player_bullets_publish_group(image, A_player_shot_slot_0 + shot * PLAYER_SHOT_TABLE_STRIDE,
                                     A_dl_player_bullets_0 + shot * DL_SHOT_STRIDE);
}

/* player_shot_slot_release_if_empty @ 0x141e4 — free the shot once all five bullets are free. */
void player_shot_slot_release_if_empty(uint8_t *image, uint32_t slots, uint32_t busy) {
    unsigned index;
    for (index = 0; index < PLAYER_SHOT_BULLETS; index++) {
        uint32_t bullet = be32(image + slots + index * ENTITY_GROUP_PTR_BYTES);
        if (be16(image + bullet + PLAYER_BULLET_STATE) != PLAYER_BULLET_FREE)
            return;
    }
    wr16(image + busy, 0);
}

void player_shot_slots_release(uint8_t *image) {
    unsigned shot;
    for (shot = 0; shot < PLAYER_SHOT_SLOTS; shot++)
        player_shot_slot_release_if_empty(image,
                                          A_player_shot_slot_0 + shot * PLAYER_SHOT_TABLE_STRIDE,
                                          A_shot_slot_busy_0 + shot * SHOT_SLOT_BUSY_BYTES);
}

/* ================================================================================================
 * The twenty-three hit handlers, and the two dispatchers that reach them.
 * ============================================================================================= */

/* The sprite-bank record the collision passes measure an entity by: its live frame is the sum of
 * the two frame words, and `muls.w` makes the product a SIGNED word before it is added. */
static uint32_t entity_sprite_record(const uint8_t *image, uint32_t entity) {
    uint16_t frame = (uint16_t)(be16(image + entity + ENTITY_FRAME_OFFSET)
                                + be16(image + entity + ENTITY_BASE_FRAME));
    return addr_add(A_sprite_bank, sign_ext16((uint16_t)(frame * SPRITE_RECORD_BYTES)));
}

/* The `bsr item_drop_if_formation_cleared` @ 0x121fe six handlers share (`move.w 6(a5),d2 /
 * movea.l (a5),a0 / bsr.w`), X threaded through it: the routine's bonus arm ends in the score
 * chain, which is what the handler's own following `bsr` then inherits. */
static unsigned drop_item_and_score(uint8_t *image, uint32_t desc, uint16_t x, uint16_t y,
                                    unsigned extend_in) {
    return item_drop_if_formation_cleared(image, be32(image + desc + ENEMY_DESC_GROUP), x, y,
                                          be16(image + desc + ENEMY_DESC_ITEM_KIND), extend_in);
}

/* `st 16(a3)` + `addi.w #$11` twice + the drop + the award: the body three blast handlers and three
 * bullet handlers share verbatim, differing only in whether the bullet slot is freed first. */
static void hit_kill_and_drop_item(uint8_t *image, uint32_t entity, uint32_t desc,
                                   unsigned extend_in) {
    uint16_t drop_x = (uint16_t)(be16(image + entity + ENTITY_X) + ENEMY_HIT_DROP_OFFSET);
    uint16_t drop_y = (uint16_t)(be16(image + entity + ENTITY_Y) + ENEMY_HIT_DROP_OFFSET);
    /* The X the dispatcher left is DEAD here: the two `addi.w #$11` overwrite it before the award,
     * and it is the SECOND one's carry that survives into the score chain. */
    unsigned extend = word_add_extend(be16(image + entity + ENTITY_Y), ENEMY_HIT_DROP_OFFSET);
    (void)extend_in;

    image[entity + ENTITY_DYING] = SCC_TRUE;
    extend = drop_item_and_score(image, desc, drop_x, drop_y, extend);
    score_add_award(image, SCORE_AWARD_200, extend);
    sfx_play_6(image);
}

/* The tail the four damage handlers' survive paths share: start firing back once the hit points
 * have fallen to the descriptor's threshold, and award 50.
 *
 * `bumps_the_hurt_frame` is the whole of what separates the `_b` pair from the `_c` pair, and it
 * separates them TWICE — the two that move the enemy's base frame on ALSO return without an award
 * while it is still above the threshold (`blt.s $11d6c` @ 0x11d5c), where the two that do not fall
 * into the award (`blt.s $11d9e` @ 0x11d98). One flag because that is one difference between two
 * shapes rather than two coincidences. */
static void hit_damage_survivor(uint8_t *image, uint32_t entity, uint32_t desc, unsigned extend,
                                int bumps_the_hurt_frame) {
    sfx_play_5(image);   /* preserves X — its module entry @ 0x58df0 writes no condition code */

    if (be16(image + entity + ENTITY_FIRING) != 0) {
        score_add_award(image, SCORE_AWARD_50, extend);
        return;
    }
    if ((int16_t)be16(image + desc + ENEMY_DESC_FIRING_HP)
        < (int16_t)be16(image + entity + ENTITY_HIT_POINTS)) {
        if (bumps_the_hurt_frame)
            return;
        score_add_award(image, SCORE_AWARD_50, extend);
        return;
    }
    image[entity + ENTITY_FIRING] = SCC_TRUE;
    if (bumps_the_hurt_frame) {
        uint16_t frame = be16(image + entity + ENTITY_BASE_FRAME);
        extend = word_add_extend(frame, ENEMY_FRAME_HURT_BUMP);
        wr16(image + entity + ENTITY_BASE_FRAME, (uint16_t)(frame + ENEMY_FRAME_HURT_BUMP));
    }
    score_add_award(image, SCORE_AWARD_50, extend);
}

/* ---- the blast handlers, dispatched through A_blast_hit_handler_tbl -------------------------- */

/* blast_hit_score200 @ 0x11c76 */
static void blast_hit_score200(uint8_t *image, uint32_t entity, uint32_t desc, uint32_t point,
                               unsigned extend_in) {
    (void)desc; (void)point;
    image[entity + ENTITY_DYING] = SCC_TRUE;
    score_add_award(image, SCORE_AWARD_200, extend_in);
    sfx_play_6(image);
}

/* blast_hit_score200_drop_item_a/b/c @ 0x11c84, 0x11caa, 0x11cce — three byte-identical bodies. */
static void blast_hit_score200_drop_item(uint8_t *image, uint32_t entity, uint32_t desc,
                                         uint32_t point, unsigned extend_in) {
    (void)point;
    hit_kill_and_drop_item(image, entity, desc, extend_in);
}

/* blast_hit_score200_if_visible @ 0x11cf2 — an entity hidden under the big object takes no hit. */
static void blast_hit_score200_if_visible(uint8_t *image, uint32_t entity, uint32_t desc,
                                          uint32_t point, unsigned extend_in) {
    (void)desc; (void)point;
    if (be16(image + entity + ENTITY_HIDDEN_UNDER_BIGOBJ) != 0)
        return;
    image[entity + ENTITY_DYING] = SCC_TRUE;
    score_add_award(image, SCORE_AWARD_200, extend_in);
    sfx_play_6(image);
}

/* blast_hit_immune @ 0x11d06 — a bare `rts`, and the table's entry for everything indestructible. */
static void blast_hit_immune(uint8_t *image, uint32_t entity, uint32_t desc, uint32_t point,
                             unsigned extend_in) {
    (void)image; (void)entity; (void)desc; (void)point; (void)extend_in;
}

/* blast_hit_damage4_a @ 0x11d08 — four damage, 5000 for the kill, and the one handler that also
 * sets ENTITY_FRAME_BUMP (the one-frame flash an object shows when it survives a hit). */
static void blast_hit_damage4_a(uint8_t *image, uint32_t entity, uint32_t desc, uint32_t point,
                                unsigned extend_in) {
    uint16_t hit_points = be16(image + entity + ENTITY_HIT_POINTS);
    unsigned extend = word_sub_extend(hit_points, BLAST_DAMAGE_4);
    (void)point; (void)extend_in;

    hit_points = (uint16_t)(hit_points - BLAST_DAMAGE_4);
    wr16(image + entity + ENTITY_HIT_POINTS, hit_points);
    if ((int16_t)hit_points <= 0) {
        image[entity + ENTITY_DYING] = SCC_TRUE;
        score_add_award(image, SCORE_AWARD_5000, extend);
        sfx_play_10(image);
        return;
    }
    sfx_play_5(image);
    image[entity + ENTITY_FRAME_BUMP] = SCC_TRUE;
    if (be16(image + entity + ENTITY_FIRING) != 0)
        return;
    if ((int16_t)be16(image + desc + ENEMY_DESC_FIRING_HP) < (int16_t)hit_points)
        return;
    image[entity + ENTITY_FIRING] = SCC_TRUE;
    score_add_award(image, SCORE_AWARD_50, extend);
}

/* blast_hit_damage4_b @ 0x11d40 — four damage, 200 for the kill, and the base frame moves on when
 * the enemy starts firing back. */
static void blast_hit_damage4_b(uint8_t *image, uint32_t entity, uint32_t desc, uint32_t point,
                                unsigned extend_in) {
    uint16_t hit_points = be16(image + entity + ENTITY_HIT_POINTS);
    unsigned extend = word_sub_extend(hit_points, BLAST_DAMAGE_4);
    (void)point; (void)extend_in;

    hit_points = (uint16_t)(hit_points - BLAST_DAMAGE_4);
    wr16(image + entity + ENTITY_HIT_POINTS, hit_points);
    if ((int16_t)hit_points <= 0) {
        image[entity + ENTITY_DYING] = SCC_TRUE;
        score_add_award(image, SCORE_AWARD_200, extend);
        sfx_play_6(image);
        return;
    }
    hit_damage_survivor(image, entity, desc, extend, 1);
}

/* blast_hit_damage5 @ 0x11d7c — five damage, and 500 for the kill. */
static void blast_hit_damage5(uint8_t *image, uint32_t entity, uint32_t desc, uint32_t point,
                                unsigned extend_in) {
    uint16_t hit_points = be16(image + entity + ENTITY_HIT_POINTS);
    unsigned extend = word_sub_extend(hit_points, BLAST_DAMAGE_5);
    (void)point; (void)extend_in;

    hit_points = (uint16_t)(hit_points - BLAST_DAMAGE_5);
    wr16(image + entity + ENTITY_HIT_POINTS, hit_points);
    if ((int16_t)hit_points <= 0) {
        image[entity + ENTITY_DYING] = SCC_TRUE;
        score_add_award(image, SCORE_AWARD_500, extend);
        sfx_play_6(image);
        return;
    }
    hit_damage_survivor(image, entity, desc, extend, 0);
}

/* blast_hit_score100 @ 0x11dae */
static void blast_hit_score100(uint8_t *image, uint32_t entity, uint32_t desc, uint32_t point,
                               unsigned extend_in) {
    (void)desc; (void)point;
    image[entity + ENTITY_DYING] = SCC_TRUE;
    score_add_award(image, SCORE_AWARD_100, extend_in);
    sfx_play_6(image);
}

/* blast_hit_damage6 @ 0x11dba — SIX damage, and the only blast handler whose kill test is `bmi`
 * alone: hit points reaching exactly zero leaves the enemy alive on 0 and awards 50. */
static void blast_hit_damage6(uint8_t *image, uint32_t entity, uint32_t desc, uint32_t point,
                                unsigned extend_in) {
    uint16_t hit_points = be16(image + entity + ENTITY_HIT_POINTS);
    unsigned extend;
    (void)point; (void)desc;

    if (hit_points == ENEMY_INDESTRUCTIBLE || be16(image + entity + ENTITY_DEPTH_SELECT) != 0) {
        (void)extend_in;   /* `beq.s $11dd8`, and 0x11dd8 is a bare `rts` — the BULLET twin's
                            * refusal arm awards 50 here and this one does not */
        return;
    }
    extend = word_sub_extend(hit_points, BLAST_DAMAGE_6);
    hit_points = (uint16_t)(hit_points - BLAST_DAMAGE_6);
    wr16(image + entity + ENTITY_HIT_POINTS, hit_points);
    if ((int16_t)hit_points < 0) {
        image[entity + ENTITY_DYING] = SCC_TRUE;
        score_add_award(image, SCORE_AWARD_500, extend);
        sfx_play_10(image);
        return;
    }
    sfx_play_5(image);
    score_add_award(image, SCORE_AWARD_50, extend);
}

/* ---- the bullet handlers, dispatched through A_bullet_hit_handler_tbl ------------------------ */

/* bullet_hit_score200 @ 0x11fca */
static void bullet_hit_score200(uint8_t *image, uint32_t entity, uint32_t desc, uint32_t bullet,
                                unsigned extend_in) {
    (void)desc;
    image[entity + ENTITY_DYING] = SCC_TRUE;
    wr16(image + bullet + PLAYER_BULLET_STATE, PLAYER_BULLET_FREE);
    score_add_award(image, SCORE_AWARD_200, extend_in);
    sfx_play_6(image);
}

/* bullet_hit_score200_drop_item_a/b/c @ 0x11fdc, 0x12004, 0x1202c — three identical bodies. */
static void bullet_hit_score200_drop_item(uint8_t *image, uint32_t entity, uint32_t desc,
                                          uint32_t bullet, unsigned extend_in) {
    wr16(image + bullet + PLAYER_BULLET_STATE, PLAYER_BULLET_FREE);
    hit_kill_and_drop_item(image, entity, desc, extend_in);
}

/* bullet_hit_two_stage_100_then_50 @ 0x12054 — a TWO-STAGE object: the first bullet marks
 * ENTITY_DEPTH_SELECT and awards 100, the second kills for 50. ../names.txt's old name
 * (`bullet_hit_score50`) covered only that second stage. */
static void bullet_hit_two_stage_100_then_50(uint8_t *image, uint32_t entity, uint32_t desc,
                                             uint32_t bullet, unsigned extend_in) {
    (void)desc;
    if (be16(image + entity + ENTITY_HIDDEN_UNDER_BIGOBJ) != 0)
        return;
    if (be16(image + entity + ENTITY_DEPTH_SELECT) != 0) {
        image[entity + ENTITY_DYING] = SCC_TRUE;
        wr16(image + bullet + PLAYER_BULLET_STATE, PLAYER_BULLET_FREE);
        score_add_award(image, SCORE_AWARD_50, extend_in);
        sfx_play_6(image);
        return;
    }
    wr16(image + entity + ENTITY_DEPTH_SELECT, 1);
    sfx_play_6(image);
    wr16(image + bullet + PLAYER_BULLET_STATE, PLAYER_BULLET_FREE);
    score_add_award(image, SCORE_AWARD_100, extend_in);
}

/* bullet_hit_immune @ 0x12084 — a bare `rts`. */
static void bullet_hit_immune(uint8_t *image, uint32_t entity, uint32_t desc, uint32_t bullet,
                              unsigned extend_in) {
    (void)image; (void)entity; (void)desc; (void)bullet; (void)extend_in;
}

/* bullet_hit_damage_a @ 0x12086 — one damage, and the kill test is `cmpi.w #$1` AFTER the subtract,
 * so the enemy dies with ONE hit point left rather than with none. Reproduced, not corrected. */
static void bullet_hit_damage_a(uint8_t *image, uint32_t entity, uint32_t desc, uint32_t bullet,
                                unsigned extend_in) {
    uint16_t hit_points = be16(image + entity + ENTITY_HIT_POINTS);
    unsigned extend = word_sub_extend(hit_points, BULLET_DAMAGE);
    (void)extend_in;

    wr16(image + bullet + PLAYER_BULLET_STATE, PLAYER_BULLET_HIT);
    hit_points = (uint16_t)(hit_points - BULLET_DAMAGE);
    wr16(image + entity + ENTITY_HIT_POINTS, hit_points);
    if (hit_points == BULLET_KILL_AT_HIT_POINTS) {
        image[entity + ENTITY_DYING] = SCC_TRUE;
        score_add_award(image, SCORE_AWARD_5000, extend);
        sfx_play_10(image);
        return;
    }
    sfx_play_5(image);
    image[entity + ENTITY_FRAME_BUMP] = SCC_TRUE;
    if (be16(image + entity + ENTITY_FIRING) == 0
        && (int16_t)be16(image + desc + ENEMY_DESC_FIRING_HP) >= (int16_t)hit_points)
        image[entity + ENTITY_FIRING] = SCC_TRUE;
    score_add_award(image, SCORE_AWARD_50, extend);
}

/* bullet_hit_damage_b @ 0x120c6 — one damage, 100 for the kill, base frame moves on. */
static void bullet_hit_damage_b(uint8_t *image, uint32_t entity, uint32_t desc, uint32_t bullet,
                                unsigned extend_in) {
    uint16_t hit_points = be16(image + entity + ENTITY_HIT_POINTS);
    unsigned extend = word_sub_extend(hit_points, BULLET_DAMAGE);
    (void)extend_in;

    wr16(image + bullet + PLAYER_BULLET_STATE, PLAYER_BULLET_HIT);
    hit_points = (uint16_t)(hit_points - BULLET_DAMAGE);
    wr16(image + entity + ENTITY_HIT_POINTS, hit_points);
    if (hit_points == 0) {
        image[entity + ENTITY_DYING] = SCC_TRUE;
        score_add_award(image, SCORE_AWARD_100, extend);
        sfx_play_6(image);
        return;
    }
    hit_damage_survivor(image, entity, desc, extend, 1);
}

/* bullet_hit_damage_c @ 0x12104 — one damage, 500 for the kill. */
static void bullet_hit_damage_c(uint8_t *image, uint32_t entity, uint32_t desc, uint32_t bullet,
                                unsigned extend_in) {
    uint16_t hit_points = be16(image + entity + ENTITY_HIT_POINTS);
    unsigned extend = word_sub_extend(hit_points, BULLET_DAMAGE);
    (void)extend_in;

    wr16(image + bullet + PLAYER_BULLET_STATE, PLAYER_BULLET_HIT);
    hit_points = (uint16_t)(hit_points - BULLET_DAMAGE);
    wr16(image + entity + ENTITY_HIT_POINTS, hit_points);
    if (hit_points == 0) {
        image[entity + ENTITY_DYING] = SCC_TRUE;
        score_add_award(image, SCORE_AWARD_500, extend);
        sfx_play_6(image);
        return;
    }
    hit_damage_survivor(image, entity, desc, extend, 0);
}

/* bullet_hit_score100 @ 0x1213a */
static void bullet_hit_score100(uint8_t *image, uint32_t entity, uint32_t desc, uint32_t bullet,
                                unsigned extend_in) {
    (void)desc;
    wr16(image + bullet + PLAYER_BULLET_STATE, PLAYER_BULLET_FREE);
    image[entity + ENTITY_DYING] = SCC_TRUE;
    score_add_award(image, SCORE_AWARD_100, extend_in);
    sfx_play_6(image);
}

/* bullet_hit_damage_d @ 0x1214a — one damage, 500 for the kill, and 50 even when the object refuses
 * the hit outright: an indestructible or already-depth-marked entity still scores. */
static void bullet_hit_damage_d(uint8_t *image, uint32_t entity, uint32_t desc, uint32_t bullet,
                                unsigned extend_in) {
    uint16_t hit_points = be16(image + entity + ENTITY_HIT_POINTS);
    unsigned extend;
    (void)desc;

    if (hit_points == ENEMY_INDESTRUCTIBLE || be16(image + entity + ENTITY_DEPTH_SELECT) != 0) {
        score_add_award(image, SCORE_AWARD_50, extend_in);
        return;
    }
    wr16(image + bullet + PLAYER_BULLET_STATE, PLAYER_BULLET_HIT);
    extend = word_sub_extend(hit_points, BULLET_DAMAGE);
    hit_points = (uint16_t)(hit_points - BULLET_DAMAGE);
    wr16(image + entity + ENTITY_HIT_POINTS, hit_points);
    if (hit_points == 0) {
        image[entity + ENTITY_DYING] = SCC_TRUE;
        score_add_award(image, SCORE_AWARD_500, extend);
        sfx_play_10(image);
        return;
    }
    sfx_play_5(image);
    score_add_award(image, SCORE_AWARD_50, extend);
}

/* ---- the dispatch ---------------------------------------------------------------------------- */

/* The X a dispatcher leaves for its handler: the last bit out of `lsl.w #2,d0` on the handler
 * index, which is bit 14. Both tables hold nineteen entries, so it is ZERO for every index either
 * can serve — a constant rather than a computation, because an index wide enough to make it 1 would
 * read a table entry 0x10000 bytes past the table and outside the program altogether. */
#define HIT_DISPATCH_EXTEND 0u

/* The handler tables hold ADDRESSES, and the original `jsr`s whatever it finds there, so the C
 * resolves the pointer it reads out of the image rather than indexing a C array by the same number.
 * A table entry that names no routine below cannot be reached from the game's own data — both
 * tables are constant DATA that nothing writes at run time — and is left alone rather than guessed. */
typedef struct {
    uint32_t address;
    hit_handler handler;
} hit_handler_row;

static const hit_handler_row BLAST_HIT_HANDLERS[] = {
    {0x11c76u, blast_hit_score200},
    {0x11c84u, blast_hit_score200_drop_item},
    {0x11caau, blast_hit_score200_drop_item},
    {0x11cceu, blast_hit_score200_drop_item},
    {0x11cf2u, blast_hit_score200_if_visible},
    {0x11d06u, blast_hit_immune},
    {0x11d08u, blast_hit_damage4_a},
    {0x11d40u, blast_hit_damage4_b},
    {0x11d7cu, blast_hit_damage5},
    {0x11daeu, blast_hit_score100},
    {0x11dbau, blast_hit_damage6},
};

static const hit_handler_row BULLET_HIT_HANDLERS[] = {
    {0x11fcau, bullet_hit_score200},
    {0x11fdcu, bullet_hit_score200_drop_item},
    {0x12004u, bullet_hit_score200_drop_item},
    {0x1202cu, bullet_hit_score200_drop_item},
    {0x12054u, bullet_hit_two_stage_100_then_50},
    {0x12084u, bullet_hit_immune},
    {0x12086u, bullet_hit_damage_a},
    {0x120c6u, bullet_hit_damage_b},
    {0x12104u, bullet_hit_damage_c},
    {0x1213au, bullet_hit_score100},
    {0x1214au, bullet_hit_damage_d},
};

static void hit_dispatch(uint8_t *image, uint32_t table, const hit_handler_row *rows,
                         unsigned row_count, uint32_t entity, uint32_t desc, uint32_t projectile) {
    uint16_t index = be16(image + desc + ENEMY_DESC_KIND);
    uint32_t target = be32(image + table + (uint16_t)(index * HIT_HANDLER_PTR_BYTES));
    unsigned row;

    for (row = 0; row < row_count; row++)
        if (rows[row].address == target) {
            rows[row].handler(image, entity, desc, projectile, HIT_DISPATCH_EXTEND);
            return;
        }
}

/* ---- the two collision passes ----------------------------------------------------------------- */

/* bomb_blast_vs_entity_groups @ 0x11bb6 — the blast's four points against one group's entities.
 *
 * The blast point is a BLAST_HIT_BOX square and the entity's box comes out of its sprite record:
 * near corner at +8/+10 of the record and far corner at +16/+18, both RELATIVE to the entity's own
 * position, which is why the width is `record[16] - record[8]` rather than `record[16]`. */
void bomb_blast_vs_entity_groups(uint8_t *image, uint32_t point, uint32_t desc) {
    unsigned index;

    for (index = 0; index < BLAST_POINTS_COUNT; index++) {
        uint32_t slot = point + (index + 1) * BLAST_POINT_BYTES;
        uint32_t slots = be32(image + desc + ENEMY_DESC_GROUP);
        unsigned count = (uint16_t)be16(image + desc + ENEMY_DESC_COUNT_MINUS_1) + 1u;
        unsigned entity_index;

        for (entity_index = 0; entity_index < count; entity_index++) {
            uint32_t entity = be32(image + slots + entity_index * ENTITY_GROUP_PTR_BYTES);
            uint32_t record;
            int16_t near_dx, near_dy, span_x, span_y, blast_x, blast_y, edge;

            if (be16(image + entity + ENTITY_ACTIVE) == 0
                || be16(image + entity + ENTITY_DYING) != 0)
                continue;

            record = entity_sprite_record(image, entity);
            near_dx = (int16_t)(be16(image + record + SPRITE_REC_HIT_DX)
                                - be16(image + record + SPRITE_REC_DRAW_DX));
            span_x = (int16_t)(be16(image + record + SPRITE_REC_HIT_W) - (uint16_t)near_dx);
            near_dy = (int16_t)(be16(image + record + SPRITE_REC_HIT_DY)
                                - be16(image + record + SPRITE_REC_DRAW_DY));
            span_y = (int16_t)(be16(image + record + SPRITE_REC_HIT_H)
                               - be16(image + record + SPRITE_REC_DRAW_DY));

            blast_x = (int16_t)be16(image + slot + 0);
            edge = (int16_t)(uint16_t)(be16(image + entity + ENTITY_X) + (uint16_t)near_dx);
            if (edge > blast_x) {
                if ((int16_t)(uint16_t)(blast_x + BLAST_HIT_BOX) <= edge)
                    continue;
            } else if ((int16_t)(uint16_t)(edge + span_x) <= blast_x) {
                continue;
            }

            blast_y = (int16_t)be16(image + slot + 2);
            edge = (int16_t)(uint16_t)(be16(image + entity + ENTITY_Y) + (uint16_t)near_dy);
            if (edge > blast_y) {
                if ((int16_t)(uint16_t)(blast_y + BLAST_HIT_BOX) <= edge)
                    continue;
            } else if ((int16_t)(uint16_t)(edge + span_y) <= blast_y) {
                continue;
            }

            hit_dispatch(image, A_blast_hit_handler_tbl, BLAST_HIT_HANDLERS,
                         sizeof BLAST_HIT_HANDLERS / sizeof BLAST_HIT_HANDLERS[0],
                         entity, desc, slot);
        }
    }
}

/* bomb_blast_vs_entities_if_active @ 0x11b90 — the guard the 22 group calls share. */
void bomb_blast_vs_entities_if_active(uint8_t *image, uint32_t blast, uint32_t desc) {
    if (be16(image + A_bomb_exploding) == 0)
        return;
    bomb_blast_vs_entity_groups(image, blast, desc);
}

/* The 22 descriptors both collision passes walk, in the order their unrolled `lea`s spell. */
static const uint32_t HIT_GROUP_DESCRIPTORS[HIT_GROUPS] = {
    A_enemy_desc_18, A_enemy_desc_00, A_enemy_desc_01, A_enemy_desc_03, A_enemy_desc_02,
    A_enemy_desc_14, A_enemy_desc_10, A_enemy_desc_11, A_enemy_desc_12, A_enemy_desc_13,
    A_enemy_desc_0e, A_enemy_desc_15, A_enemy_desc_16, A_enemy_desc_17, A_enemy_desc_04,
    A_enemy_desc_05, A_enemy_desc_06, A_enemy_desc_07, A_enemy_desc_08, A_enemy_desc_09,
    A_enemy_desc_0a, A_enemy_desc_0b,
};

void bomb_blast_vs_entities(uint8_t *image) {
    unsigned group;
    for (group = 0; group < HIT_GROUPS; group++)
        bomb_blast_vs_entities_if_active(image, A_blast_state, HIT_GROUP_DESCRIPTORS[group]);
}

/* player_bullet_vs_entity_groups @ 0x11f0c — one shot's five bullets against one group.
 *
 * The bullet tests as a POINT, PLAYER_BULLET_HIT_DX inside its own record on both axes, and a hit
 * ends that BULLET rather than that entity: the original's `dbf d7` after the handler takes it to
 * the next bullet, not to the next entity. */
void player_bullet_vs_entity_groups(uint8_t *image, uint32_t slots, uint32_t desc) {
    unsigned index;

    for (index = 0; index < PLAYER_SHOT_BULLETS; index++) {
        uint32_t bullet = be32(image + slots + index * ENTITY_GROUP_PTR_BYTES);
        uint16_t state = be16(image + bullet + PLAYER_BULLET_STATE);
        uint32_t entities;
        unsigned count, entity_index;
        int16_t probe_x, probe_y;

        if (state == PLAYER_BULLET_FREE || state == PLAYER_BULLET_HIT)
            continue;

        probe_x = (int16_t)(be16(image + bullet + PLAYER_BULLET_X) + PLAYER_BULLET_HIT_DX);
        probe_y = (int16_t)(be16(image + bullet + PLAYER_BULLET_Y) + PLAYER_BULLET_HIT_DX);
        entities = be32(image + desc + ENEMY_DESC_GROUP);
        count = (uint16_t)be16(image + desc + ENEMY_DESC_COUNT_MINUS_1) + 1u;

        for (entity_index = 0; entity_index < count; entity_index++) {
            uint32_t entity = be32(image + entities + entity_index * ENTITY_GROUP_PTR_BYTES);
            uint32_t record;
            int16_t left, top, right, bottom;

            if (be16(image + entity + ENTITY_ACTIVE) == 0
                || be16(image + entity + ENTITY_DYING) != 0)
                continue;

            record = entity_sprite_record(image, entity);
            left = (int16_t)(uint16_t)(be16(image + entity + ENTITY_X)
                                       + be16(image + record + SPRITE_REC_DRAW_DX));
            right = (int16_t)(uint16_t)(be16(image + entity + ENTITY_X)
                                        + be16(image + record + SPRITE_REC_HIT_W));
            top = (int16_t)(uint16_t)(be16(image + entity + ENTITY_Y)
                                      + be16(image + record + SPRITE_REC_DRAW_DY));
            bottom = (int16_t)(uint16_t)(be16(image + entity + ENTITY_Y)
                                         + be16(image + record + SPRITE_REC_HIT_H));

            if (probe_x < left || probe_y < top || probe_x > right || probe_y > bottom)
                continue;

            hit_dispatch(image, A_bullet_hit_handler_tbl, BULLET_HIT_HANDLERS,
                         sizeof BULLET_HIT_HANDLERS / sizeof BULLET_HIT_HANDLERS[0],
                         entity, desc, bullet);
            break;   /* `dbf d7` after the handler: the bullet is spent, not the group */
        }
    }
}

void player_bullets_vs_entities_group(uint8_t *image, uint32_t slots) {
    unsigned group;
    for (group = 0; group < HIT_GROUPS; group++)
        player_bullet_vs_entity_groups(image, slots, HIT_GROUP_DESCRIPTORS[group]);
}

void player_bullets_vs_entities(uint8_t *image) {
    unsigned shot;
    for (shot = 0; shot < PLAYER_SHOT_SLOTS; shot++)
        player_bullets_vs_entities_group(image,
                                         A_player_shot_slot_0 + shot * PLAYER_SHOT_TABLE_STRIDE);
}

/* ================================================================================================
 * The muzzle flash — two display records per firing entity.
 * ============================================================================================= */

/* The four-field clear both forms share when the entity is not firing. It steps the cursor by a
 * whole PAIR, so a silent entity leaves both of its records blank. */
static void muzzle_flash_clear_pair(uint8_t *image, uint32_t records) {
    unsigned half;
    for (half = 0; half < 2; half++) {
        uint32_t record = records + half * DISPLAY_REC_BYTES;
        wr16(image + record + DISPLAY_REC_X, 0);
        wr16(image + record + DISPLAY_REC_Y, 0);
        image[record + DISPLAY_REC_FRAME] = 0;
        image[record + DISPLAY_REC_ACTIVE] = 0;
    }
}

static int muzzle_flash_is_lit(const uint8_t *image, uint32_t entity) {
    return be16(image + entity + ENTITY_ACTIVE) != 0
        && be16(image + entity + ENTITY_DYING) == 0
        && be16(image + entity + ENTITY_FIRING) != 0;
}

/* muzzle_flash_publish_pair @ 0x122c0 — the single-slot objects' form, which reads all four of the
 * descriptor's flash offsets and publishes the second sprite relative to the first. */
void muzzle_flash_publish_pair(uint8_t *image, uint32_t desc, uint32_t records) {
    uint32_t entity = be32(image + be32(image + desc + ENEMY_DESC_GROUP));
    uint8_t glyph;
    uint16_t position;

    if (!muzzle_flash_is_lit(image, entity)) {
        muzzle_flash_clear_pair(image, records);
        return;
    }

    glyph = (uint8_t)(image[A_anim_frame_a] + MUZZLE_FLASH_GLYPH_BUMP);
    image[records + DISPLAY_REC_FRAME] = glyph;
    image[records + DISPLAY_REC_BYTES + DISPLAY_REC_FRAME] = glyph;
    image[records + DISPLAY_REC_ACTIVE] = DISPLAY_ACTIVE_ON_TOP;
    image[records + DISPLAY_REC_BYTES + DISPLAY_REC_ACTIVE] = DISPLAY_ACTIVE_ON_TOP;

    position = (uint16_t)(be16(image + entity + ENTITY_X)
                          + be16(image + desc + ENEMY_DESC_FLASH_DX));
    wr16(image + records + DISPLAY_REC_X, position);
    position = (uint16_t)(position + be16(image + desc + ENEMY_DESC_FLASH2_DX));
    wr16(image + records + DISPLAY_REC_BYTES + DISPLAY_REC_X, position);

    position = (uint16_t)(be16(image + entity + ENTITY_Y)
                          + be16(image + desc + ENEMY_DESC_FLASH_DY));
    wr16(image + records + DISPLAY_REC_Y, position);
    position = (uint16_t)(position + be16(image + desc + ENEMY_DESC_FLASH2_DY));
    wr16(image + records + DISPLAY_REC_BYTES + DISPLAY_REC_Y, position);
}

/* muzzle_flash_publish_group @ 0x12348 — the four-slot form. Its second sprite sits a fixed
 * MUZZLE_FLASH_GROUP_DX to the right, and the entity's frame offset selects between two looks:
 * offset zero takes the bumped glyph and no vertical shift, anything else the plain glyph six rows
 * down. (The `subi.w #$6` then `addi.w #$6` the original spells is one branch writing zero.) */
void muzzle_flash_publish_group(uint8_t *image, uint32_t desc, uint32_t records, uint32_t count) {
    uint32_t slots = be32(image + desc + ENEMY_DESC_GROUP);
    unsigned index;

    for (index = 0; index <= count; index++) {
        uint32_t entity = be32(image + slots + index * ENTITY_GROUP_PTR_BYTES);
        uint32_t pair = records + index * DL_FLASH_PAIR;
        int plain_frame = be16(image + entity + ENTITY_FRAME_OFFSET) == 0;
        uint8_t glyph;
        uint16_t drop, x, y;

        if (!muzzle_flash_is_lit(image, entity)) {
            muzzle_flash_clear_pair(image, pair);
            continue;
        }

        glyph = (uint8_t)(image[A_anim_frame_a] + (plain_frame ? MUZZLE_FLASH_GLYPH_BUMP : 0));
        drop = plain_frame ? 0 : MUZZLE_FLASH_GROUP_DY;
        image[pair + DISPLAY_REC_FRAME] = glyph;
        image[pair + DISPLAY_REC_BYTES + DISPLAY_REC_FRAME] = glyph;
        image[pair + DISPLAY_REC_ACTIVE] = DISPLAY_ACTIVE_ON_TOP;
        image[pair + DISPLAY_REC_BYTES + DISPLAY_REC_ACTIVE] = DISPLAY_ACTIVE_ON_TOP;

        x = (uint16_t)(be16(image + entity + ENTITY_X) + be16(image + desc + ENEMY_DESC_FLASH_DX));
        wr16(image + pair + DISPLAY_REC_X, x);
        wr16(image + pair + DISPLAY_REC_BYTES + DISPLAY_REC_X,
             (uint16_t)(x + MUZZLE_FLASH_GROUP_DX));

        y = (uint16_t)(be16(image + entity + ENTITY_Y) + be16(image + desc + ENEMY_DESC_FLASH_DY));
        wr16(image + pair + DISPLAY_REC_Y, (uint16_t)(y + drop));
        wr16(image + pair + DISPLAY_REC_BYTES + DISPLAY_REC_Y, (uint16_t)(y + drop));
    }
}

/* muzzle_flash_publish_all @ 0x1227c — the one four-slot group, then the three single objects. */
void muzzle_flash_publish_all(uint8_t *image) {
    static const uint32_t PAIR_DESCRIPTORS[] =
        {A_enemy_desc_10, A_enemy_desc_11, A_enemy_desc_18};
    unsigned index;

    muzzle_flash_publish_group(image, A_enemy_desc_14, A_dl_muzzle_group,
                               ENTITY_GROUP_SLOTS - 1u);
    for (index = 0; index < sizeof PAIR_DESCRIPTORS / sizeof PAIR_DESCRIPTORS[0]; index++)
        muzzle_flash_publish_pair(image, PAIR_DESCRIPTORS[index],
                                  A_dl_muzzle_pair_0 + index * DL_FLASH_PAIR);
}

/* ================================================================================================
 * The enemy bullets: the aimed spawn, the per-frame step and the publisher.
 * ============================================================================================= */

/* enemy_bullet_spawn_aimed @ 0x128ce — put one bullet in the first free slot, aimed at (aim_x,
 * aim_y) from (x, y) through the direction grid.
 *
 * `cursor` is the caller's scan position and is an IN/OUT: `enemies_fire_all` sets it once and every
 * group inherits where the last spawn left it, so the array fills forward across a whole frame and
 * a frame that reaches the sentinel silently drops every later shot. */
void enemy_bullet_spawn_aimed(uint8_t *image, uint32_t desc, uint32_t *cursor,
                              uint16_t aim_x, uint16_t aim_y, uint16_t x, uint16_t y) {
    int16_t cell_x, cell_y;
    uint16_t direction, position;
    uint32_t velocity;

    while (be16(image + *cursor + ENEMY_BULLET_ACTIVE) != ENEMY_BULLET_END) {
        if (be16(image + *cursor + ENEMY_BULLET_ACTIVE) == 0)
            break;
        *cursor += ENEMY_BULLET_BYTES;
    }
    if (be16(image + *cursor + ENEMY_BULLET_ACTIVE) == ENEMY_BULLET_END)
        return;

    wr16(image + *cursor + ENEMY_BULLET_X, x);
    wr16(image + *cursor + ENEMY_BULLET_Y, y);

    cell_x = (int16_t)(int16_t)(x - aim_x) >> AIM_CELL_SHIFT;
    cell_y = (int16_t)(int16_t)(y - aim_y) >> AIM_CELL_SHIFT;
    direction = (uint16_t)(cell_y * AIM_LUT_ROW_STRIDE + cell_x);
    direction = (uint16_t)sign_ext8(image[addr_add(A_enemy_aim_dir_lut, sign_ext16(direction))]);
    velocity = addr_add(A_enemy_bullet_velocity_tbl,
                        sign_ext16((uint16_t)(direction * AIM_VELOCITY_BYTES)));

    wr16(image + *cursor + ENEMY_BULLET_DX, be16(image + velocity + 0));
    wr16(image + *cursor + ENEMY_BULLET_DY, be16(image + velocity + 2));
    wr16(image + *cursor + ENEMY_BULLET_ACTIVE, ENEMY_BULLET_LIVE);

    position = (uint16_t)(be16(image + *cursor + ENEMY_BULLET_X)
                          + be16(image + desc + ENEMY_DESC_MUZZLE_DX));
    wr16(image + *cursor + ENEMY_BULLET_X,
         (uint16_t)(position + be16(image + *cursor + ENEMY_BULLET_DX)));
    position = (uint16_t)(be16(image + *cursor + ENEMY_BULLET_Y)
                          + be16(image + desc + ENEMY_DESC_MUZZLE_DY));
    wr16(image + *cursor + ENEMY_BULLET_Y,
         (uint16_t)(position + be16(image + *cursor + ENEMY_BULLET_DY)));

    /* The one place in the game that tests the sound module's own busy byte before triggering: a
     * salvo of shots in one frame must not restart the effect on every one of them. */
    if (image[A_sound_module + SND_SFX_ACTIVE] == 0)
        sfx_play_5(image);
}

/* enemy_bullets_move @ 0x12964 — step every live bullet and retire the ones outside the clip box. */
void enemy_bullets_move(uint8_t *image) {
    uint32_t bullet;
    for (bullet = A_enemy_bullets;
         be16(image + bullet + ENEMY_BULLET_ACTIVE) != ENEMY_BULLET_END;
         bullet += ENEMY_BULLET_BYTES) {
        int16_t x, y;
        if (be16(image + bullet + ENEMY_BULLET_ACTIVE) == 0)
            continue;
        wr16(image + bullet + ENEMY_BULLET_X, be16(image + bullet + ENEMY_BULLET_X)
                                              + be16(image + bullet + ENEMY_BULLET_DX));
        wr16(image + bullet + ENEMY_BULLET_Y, be16(image + bullet + ENEMY_BULLET_Y)
                                              + be16(image + bullet + ENEMY_BULLET_DY));
        x = (int16_t)be16(image + bullet + ENEMY_BULLET_X);
        y = (int16_t)be16(image + bullet + ENEMY_BULLET_Y);
        if (x < (int16_t)(uint16_t)ENEMY_BULLET_CLIP_LEFT || x > (int16_t)ENEMY_BULLET_CLIP_RIGHT
            || y < (int16_t)(uint16_t)ENEMY_BULLET_CLIP_TOP
            || y > (int16_t)ENEMY_BULLET_CLIP_BOTTOM)
            wr16(image + bullet + ENEMY_BULLET_ACTIVE, 0);
    }
}

/* enemy_bullets_publish @ 0x125bc — one display record per slot, up to the sentinel. */
void enemy_bullets_publish(uint8_t *image) {
    uint32_t bullet = A_enemy_bullets;
    uint32_t record = A_dl_enemy_bullets;

    for (; be16(image + bullet + ENEMY_BULLET_ACTIVE) != ENEMY_BULLET_END;
         bullet += ENEMY_BULLET_BYTES, record += DISPLAY_REC_BYTES) {
        if (be16(image + bullet + ENEMY_BULLET_ACTIVE) == 0) {
            wr16(image + record + DISPLAY_REC_X, 0);
            wr16(image + record + DISPLAY_REC_Y, 0);
            image[record + DISPLAY_REC_FRAME] = 0;
            image[record + DISPLAY_REC_ACTIVE] = 0;
            continue;
        }
        wr16(image + record + DISPLAY_REC_X, be16(image + bullet + ENEMY_BULLET_X));
        wr16(image + record + DISPLAY_REC_Y, be16(image + bullet + ENEMY_BULLET_Y));
        image[record + DISPLAY_REC_FRAME] = ENEMY_BULLET_GLYPH;
        image[record + DISPLAY_REC_ACTIVE] = DISPLAY_ACTIVE_ON_TOP;
    }
}

/* ---- the four firing groups ------------------------------------------------------------------ */

/* The reload every group shares: fire this frame if the countdown is already zero, otherwise run it
 * down and fire only on the frame it REACHES zero — so a countdown of one fires next frame, and one
 * that starts at zero fires every frame. */
static int enemy_fire_is_due(uint8_t *image, uint32_t entity) {
    if (be16(image + entity + ENTITY_FIRE_COUNTDOWN) != 0) {
        wr16(image + entity + ENTITY_FIRE_COUNTDOWN,
             be16(image + entity + ENTITY_FIRE_COUNTDOWN) - 1);
        if (be16(image + entity + ENTITY_FIRE_COUNTDOWN) != 0)
            return 0;
    }
    wr16(image + entity + ENTITY_FIRE_COUNTDOWN, be16(image + entity + ENTITY_FIRE_RELOAD));
    return 1;
}

/* The window an entity has to be inside to shoot. `y_min` is the only thing that differs between
 * the four groups: group B lets an entity a little above the screen fire, the others do not. */
static int enemy_fire_in_window(const uint8_t *image, uint32_t entity, int16_t y_min) {
    int16_t x = (int16_t)be16(image + entity + ENTITY_X);
    int16_t y = (int16_t)be16(image + entity + ENTITY_Y);
    return x >= 0 && x <= (int16_t)ENEMY_FIRE_X_MAX
        && y >= y_min && y <= (int16_t)ENEMY_FIRE_Y_MAX;
}

/* enemies_fire_group_b @ 0x1273a — the three-way spread, and the group whose window opens above the
 * screen. `aim_x` is a POINTER because the original never restores D0: every shot this group and
 * group A fire moves the shared aim point ENEMY_FIRE_SPREAD further left for the rest of the frame. */
static void enemies_fire_group_b(uint8_t *image, uint32_t desc, uint32_t slots, unsigned count,
                                 uint32_t *cursor, uint16_t *aim_x, uint16_t aim_y) {
    unsigned index;
    for (index = 0; index <= count; index++) {
        uint32_t entity = be32(image + slots + index * ENTITY_GROUP_PTR_BYTES);
        uint16_t x, y;

        if (be16(image + entity + ENTITY_ACTIVE) == 0
            || be16(image + entity + ENTITY_DYING) != 0
            || !enemy_fire_is_due(image, entity))
            continue;

        *aim_x = (uint16_t)(*aim_x - ENEMY_FIRE_SPREAD);
        if (!enemy_fire_in_window(image, entity, (int16_t)(uint16_t)ENEMY_FIRE_Y_MIN_B))
            continue;

        x = be16(image + entity + ENTITY_X);
        y = be16(image + entity + ENTITY_Y);
        enemy_bullet_spawn_aimed(image, desc, cursor, *aim_x, aim_y, x, y);
        enemy_bullet_spawn_aimed(image, desc, cursor, (uint16_t)(*aim_x - ENEMY_FIRE_SPREAD),
                                 (uint16_t)(aim_y - ENEMY_FIRE_SPREAD), x, y);
        enemy_bullet_spawn_aimed(image, desc, cursor, (uint16_t)(*aim_x + ENEMY_FIRE_SPREAD),
                                 (uint16_t)(aim_y + ENEMY_FIRE_SPREAD), x, y);
    }
}

/* enemies_fire_group_a @ 0x127ba — one shot, and the same permanent shift of the aim point. */
static void enemies_fire_group_a(uint8_t *image, uint32_t desc, uint32_t slots, unsigned count,
                                 uint32_t *cursor, uint16_t *aim_x, uint16_t aim_y) {
    unsigned index;
    for (index = 0; index <= count; index++) {
        uint32_t entity = be32(image + slots + index * ENTITY_GROUP_PTR_BYTES);

        if (be16(image + entity + ENTITY_ACTIVE) == 0
            || be16(image + entity + ENTITY_DYING) != 0
            || !enemy_fire_is_due(image, entity))
            continue;

        *aim_x = (uint16_t)(*aim_x - ENEMY_FIRE_SPREAD);
        if (!enemy_fire_in_window(image, entity, 0))
            continue;
        enemy_bullet_spawn_aimed(image, desc, cursor, *aim_x, aim_y,
                                 be16(image + entity + ENTITY_X),
                                 be16(image + entity + ENTITY_Y));
    }
}

/* enemies_fire_group_c @ 0x12810 — one shot, and the aim point is shifted for THIS shot only. */
static void enemies_fire_group_c(uint8_t *image, uint32_t desc, uint32_t slots, unsigned count,
                                 uint32_t *cursor, uint16_t aim_x, uint16_t aim_y) {
    unsigned index;
    for (index = 0; index <= count; index++) {
        uint32_t entity = be32(image + slots + index * ENTITY_GROUP_PTR_BYTES);

        if (be16(image + entity + ENTITY_ACTIVE) == 0
            || be16(image + entity + ENTITY_DYING) != 0
            || !enemy_fire_is_due(image, entity)
            || !enemy_fire_in_window(image, entity, 0))
            continue;
        enemy_bullet_spawn_aimed(image, desc, cursor, (uint16_t)(aim_x - ENEMY_FIRE_SPREAD), aim_y,
                                 be16(image + entity + ENTITY_X),
                                 be16(image + entity + ENTITY_Y));
    }
}

/* enemies_fire_group_d @ 0x1286c — the turrets' own, with three extra gates (hidden, wrecked, and
 * mid-rotation) and a recoil that pulls the spawned bullet back towards the barrel. */
static void enemies_fire_group_d(uint8_t *image, uint32_t desc, uint32_t slots, unsigned count,
                                 uint32_t *cursor, uint16_t aim_x, uint16_t aim_y) {
    unsigned index;
    for (index = 0; index <= count; index++) {
        uint32_t entity = be32(image + slots + index * ENTITY_GROUP_PTR_BYTES);

        if (be16(image + entity + ENTITY_HIDDEN_UNDER_BIGOBJ) != 0
            || be16(image + entity + ENTITY_ACTIVE) == 0
            || be16(image + entity + ENTITY_DEPTH_SELECT) != 0
            || be16(image + entity + ENTITY_AIM_CHANGED) != 0
            || !enemy_fire_is_due(image, entity)
            || !enemy_fire_in_window(image, entity, 0))
            continue;
        enemy_bullet_spawn_aimed(image, desc, cursor, aim_x, aim_y,
                                 be16(image + entity + ENTITY_X),
                                 be16(image + entity + ENTITY_Y));
        wr16(image + *cursor + ENEMY_BULLET_X,
             be16(image + *cursor + ENEMY_BULLET_X) - ENEMY_FIRE_RECOIL);
        wr16(image + *cursor + ENEMY_BULLET_Y,
             be16(image + *cursor + ENEMY_BULLET_Y) - ENEMY_FIRE_RECOIL);
    }
}

/* Which group routine each of the 22 descriptors `enemies_fire_all` walks is handed to, in the
 * order the original's unrolled calls spell it. */
typedef enum {
    FIRE_GROUP_A, FIRE_GROUP_B, FIRE_GROUP_C, FIRE_GROUP_D
} enemy_fire_group;

typedef struct {
    uint32_t desc;
    unsigned count_minus_1;   /* the D7 the call site loads, NOT the descriptor's own +14 */
    enemy_fire_group group;
} enemy_fire_row;

static const enemy_fire_row ENEMY_FIRE_ORDER[] = {
    {A_enemy_desc_10, 0, FIRE_GROUP_A}, {A_enemy_desc_11, 0, FIRE_GROUP_A},
    {A_enemy_desc_18, 0, FIRE_GROUP_A}, {A_enemy_desc_14, 3, FIRE_GROUP_B},
    {A_enemy_desc_12, 3, FIRE_GROUP_C}, {A_enemy_desc_13, 3, FIRE_GROUP_C},
    {A_enemy_desc_15, 3, FIRE_GROUP_C}, {A_enemy_desc_16, 3, FIRE_GROUP_C},
    {A_enemy_desc_17, 3, FIRE_GROUP_C}, {A_enemy_desc_00, 6, FIRE_GROUP_C},
    {A_enemy_desc_04, 3, FIRE_GROUP_D}, {A_enemy_desc_05, 3, FIRE_GROUP_D},
    {A_enemy_desc_06, 3, FIRE_GROUP_D}, {A_enemy_desc_07, 3, FIRE_GROUP_D},
    {A_enemy_desc_08, 3, FIRE_GROUP_D}, {A_enemy_desc_09, 3, FIRE_GROUP_D},
    {A_enemy_desc_0a, 3, FIRE_GROUP_D}, {A_enemy_desc_0b, 3, FIRE_GROUP_D},
};

/* enemies_fire_all @ 0x12602 — every firing group, in one pass, off one shared bullet cursor.
 *
 * The abort is `enemies_fire_abort_if_inhibited` @ 0x12856, which the name map used to call
 * `enemies_fire_nop` and which is not a nop at all: called with `bsr`, it discards its own return
 * address with `addq.l #4,a7` when `A_enemy_fire_inhibit` is set, so the `rts` that follows returns
 * out of THIS routine and no enemy fires. Reproduced as the guard it really is. */
void enemies_fire_all(uint8_t *image) {
    uint16_t aim_x, aim_y;
    uint32_t cursor = A_enemy_bullets;
    unsigned row;

    if (be16(image + A_enemy_fire_inhibit) != 0)
        return;

    aim_x = (uint16_t)(be16(image + A_player + PLAYER_X) + ENEMY_AIM_PLAYER_OFFSET);
    aim_y = (uint16_t)(be16(image + A_player + PLAYER_Y) + ENEMY_AIM_PLAYER_OFFSET);

    for (row = 0; row < sizeof ENEMY_FIRE_ORDER / sizeof ENEMY_FIRE_ORDER[0]; row++) {
        uint32_t desc = ENEMY_FIRE_ORDER[row].desc;
        uint32_t slots = be32(image + desc + ENEMY_DESC_GROUP);
        unsigned count = ENEMY_FIRE_ORDER[row].count_minus_1;

        switch (ENEMY_FIRE_ORDER[row].group) {
        case FIRE_GROUP_A: enemies_fire_group_a(image, desc, slots, count, &cursor,
                                                &aim_x, aim_y); break;
        case FIRE_GROUP_B: enemies_fire_group_b(image, desc, slots, count, &cursor,
                                                &aim_x, aim_y); break;
        case FIRE_GROUP_C: enemies_fire_group_c(image, desc, slots, count, &cursor,
                                                aim_x, aim_y); break;
        case FIRE_GROUP_D: enemies_fire_group_d(image, desc, slots, count, &cursor,
                                                aim_x, aim_y); break;
        }
    }
}

/* ================================================================================================
 * The turrets: aiming, and the barrel sprite that follows the aim.
 * ============================================================================================= */

/* turret_aim_step @ 0x12c04 — rotate one turret one step of twelve towards the player.
 *
 * The desired facing comes out of a 23-column grid of 32-pixel cells centred on the player, and the
 * turret's own facing is compared to it HALF A TURN ROUND (`addi.b #$6` then a wrap at 12), so
 * "already aimed" is a byte difference of exactly TURRET_HALF_TURN — or of -TURRET_HALF_TURN on the
 * negative side, which is the same bearing read the other way. */
void turret_aim_step(uint8_t *image, uint32_t entity) {
    int16_t cell_x = (int16_t)(be16(image + entity + ENTITY_X)
                               - (uint16_t)(be16(image + A_player + PLAYER_X)
                                            + TURRET_AIM_PLAYER_DX)) >> AIM_CELL_SHIFT;
    int16_t cell_y = (int16_t)(be16(image + entity + ENTITY_Y)
                               - be16(image + A_player + PLAYER_Y)) >> AIM_CELL_SHIFT;
    uint16_t cell = (uint16_t)(cell_y * TURRET_LUT_ROW_STRIDE + cell_x);
    uint8_t wanted = image[addr_add(A_turret_facing_lut, sign_ext16(cell))];
    uint16_t facing = be16(image + entity + ENTITY_FACING);
    int8_t bearing = (int8_t)(facing + TURRET_HALF_TURN);

    if (bearing >= (int8_t)TURRET_FACINGS)
        bearing = (int8_t)(bearing - TURRET_FACINGS);
    bearing = (int8_t)(bearing - wanted);

    /* Both arms compare against the SAME half turn, one as +6 and one as -6, which is why an
     * already-aimed turret is the only case that clears ENTITY_AIM_CHANGED. */
    if (bearing == (int8_t)TURRET_HALF_TURN || bearing == -(int8_t)TURRET_HALF_TURN) {
        wr16(image + entity + ENTITY_AIM_CHANGED, 0);
        return;
    }
    if (bearing > (int8_t)TURRET_HALF_TURN
        || (bearing < 0 && bearing > -(int8_t)TURRET_HALF_TURN))
        wr16(image + entity + ENTITY_FACING,
             facing == 0 ? (uint16_t)(TURRET_FACINGS - 1u) : (uint16_t)(facing - 1u));
    else
        wr16(image + entity + ENTITY_FACING,
             facing == TURRET_FACINGS - 1u ? 0u : (uint16_t)(facing + 1u));
    image[entity + ENTITY_AIM_CHANGED] = SCC_TRUE;
}

/* turrets_aim_group @ 0x12a50 — one turret group, unconditionally: the eight turret groups aim even
 * while inactive or dying, which their `_active` sibling below does not. */
void turrets_aim_group(uint8_t *image, uint32_t group) {
    unsigned index;
    for (index = 0; index < ENTITY_GROUP_SLOTS; index++)
        turret_aim_step(image, be32(image + group + index * ENTITY_GROUP_PTR_BYTES));
}

/* turrets_aim_group_active @ 0x12a34 — the facing groups' form, which skips the dead. */
void turrets_aim_group_active(uint8_t *image, uint32_t group) {
    unsigned index;
    for (index = 0; index < ENTITY_GROUP_SLOTS; index++) {
        uint32_t entity = be32(image + group + index * ENTITY_GROUP_PTR_BYTES);
        if (be16(image + entity + ENTITY_ACTIVE) != 0 && be16(image + entity + ENTITY_DYING) == 0)
            turret_aim_step(image, entity);
    }
}

void turrets_aim_all(uint8_t *image) {
    unsigned index;
    for (index = 0; index < ENTITY_GROUP_T_COUNT; index++)
        turrets_aim_group(image, A_entity_group_t0 + index * ENTITY_GROUP_T_STRIDE);
    for (index = 0; index < ENTITY_GROUP_X_COUNT; index++)
        turrets_aim_group_active(image, A_entity_group_x0 + index * ENTITY_GROUP_X_STRIDE);
}

/* turret_publish_group @ 0x12b40 — one group's four BARREL records.
 *
 * The turret reuses ENTITY_DEPTH_SELECT as a state: TURRET_STATE_AIMING draws the barrel from the
 * facing table, TURRET_STATE_HIT draws the wreck from the hit table, and any other value publishes
 * nothing at all — the record keeps whatever the previous frame left in it. */
void turret_publish_group(uint8_t *image, uint32_t group, uint32_t records,
                          uint32_t barrel_tbl, uint32_t hit_tbl) {
    unsigned index;

    for (index = 0; index < ENTITY_GROUP_SLOTS; index++) {
        uint32_t record = be32(image + records + index * ENTITY_GROUP_PTR_BYTES);
        uint32_t entity = be32(image + group + index * ENTITY_GROUP_PTR_BYTES);
        uint16_t state, frame_offset;
        uint32_t entry;

        if (be16(image + entity + ENTITY_ACTIVE) == 0
            || be16(image + entity + ENTITY_DYING) != 0
            || be16(image + entity + ENTITY_HIDDEN_UNDER_BIGOBJ) != 0) {
            wr16(image + record + DISPLAY_REC_X, 0);
            wr16(image + record + DISPLAY_REC_Y, 0);
            image[record + DISPLAY_REC_FRAME] = 0;
            image[record + DISPLAY_REC_ACTIVE] = 0;
            continue;
        }

        state = be16(image + entity + ENTITY_DEPTH_SELECT);
        if (state != TURRET_STATE_AIMING && state != TURRET_STATE_HIT)
            continue;

        wr16(image + record + DISPLAY_REC_X, be16(image + entity + ENTITY_X));
        wr16(image + record + DISPLAY_REC_Y, be16(image + entity + ENTITY_Y));
        frame_offset = be16(image + entity + ENTITY_FRAME_OFFSET);

        if (state == TURRET_STATE_HIT) {
            entry = addr_add(hit_tbl, (uint16_t)(frame_offset * TURRET_HIT_ENTRY_BYTES));
            wr16(image + record + DISPLAY_REC_X,
                 be16(image + record + DISPLAY_REC_X) + be16(image + entry + 0));
            wr16(image + record + DISPLAY_REC_Y,
                 be16(image + record + DISPLAY_REC_Y) + be16(image + entry + 2));
            image[record + DISPLAY_REC_FRAME] = image[A_anim_frame_b];
            image[record + DISPLAY_REC_ACTIVE] = DISPLAY_ACTIVE_UNDER_SCENERY;
            continue;
        }

        image[record + DISPLAY_REC_FRAME] =
            (uint8_t)(image[A_turret_barrel_base_frame + TURRET_BARREL_BASE_FRAME_BYTE]
                      + be16(image + entity + ENTITY_FACING));
        image[record + DISPLAY_REC_ACTIVE] = DISPLAY_ACTIVE_UNDER_SCENERY;
        entry = addr_add(barrel_tbl,
                         sign_ext16((uint16_t)(frame_offset * TURRET_BARREL_STRIDE)));
        entry = addr_add(entry, sign_ext16((uint16_t)(be16(image + entity + ENTITY_FACING)
                                                      * TURRET_BARREL_ENTRY_BYTES)));
        wr16(image + record + DISPLAY_REC_X,
             be16(image + record + DISPLAY_REC_X) + (uint16_t)sign_ext8(image[entry]));
        wr16(image + record + DISPLAY_REC_Y,
             be16(image + record + DISPLAY_REC_Y) + (uint16_t)sign_ext8(image[entry + 1]));
    }
}

/* turrets_publish_all @ 0x12a60 — the eight groups, the first four off the low offset tables. */
void turrets_publish_all(uint8_t *image) {
    unsigned index;
    for (index = 0; index < ENTITY_GROUP_T_COUNT; index++) {
        int low = index < DL_TURRET_RUN_GROUPS;
        turret_publish_group(image,
                             A_entity_group_t0 + index * ENTITY_GROUP_T_STRIDE,
                             A_dl_turret_ptrs_t0 + index * ENTITY_GROUP_T_STRIDE,
                             low ? A_turret_barrel_tbl_lo : A_turret_barrel_tbl_hi,
                             low ? A_turret_hit_tbl_lo : A_turret_hit_tbl_hi);
    }
}

/* ================================================================================================
 * The level spawn script and its five common bodies.
 * ============================================================================================= */

/* spawn_item_bomb @ 0x13044 — the one handler that is not a formation at all: it arms the bomb
 * power-up item where the script record says. */
void spawn_item_bomb(uint8_t *image, uint32_t record) {
    wr16(image + A_item_bomb + ITEM_X, be16(image + record + SPAWN_REC_X));
    wr16(image + A_item_bomb + ITEM_Y, be16(image + record + SPAWN_REC_Y));
    image[A_item_bomb + ITEM_ACTIVE] = SCC_TRUE;   /* `st 8(a1)`: the high byte of the word only */
}

/* A formation record's three field groups, all derived from the body's slot count because they are
 * packed back to back: `slots` positions, then `slots` script offsets, then one script base. */
static uint32_t formation_script_offset(uint32_t formation, unsigned slots, unsigned index) {
    return formation + slots * FORMATION_POS_BYTES + index * FORMATION_SCRIPT_PTR_BYTES;
}

static uint32_t formation_script_base(uint32_t formation, unsigned slots) {
    return formation + slots * (FORMATION_POS_BYTES + FORMATION_SCRIPT_PTR_BYTES);
}

/* PASS ONE, shared by all five bodies: place each slot and give it its script, marking the slots
 * the formation leaves out with -1 in the cursor so pass two can retire them. */
static void spawn_place_slots(uint8_t *image, uint32_t record, uint32_t desc, uint32_t formation,
                              unsigned slots) {
    uint32_t entities = be32(image + desc + ENEMY_DESC_GROUP);
    uint16_t origin_x = be16(image + record + SPAWN_REC_X);
    uint16_t origin_y = be16(image + record + SPAWN_REC_Y);
    unsigned index;

    for (index = 0; index < slots; index++) {
        uint32_t entity = be32(image + entities + index * ENTITY_GROUP_PTR_BYTES);
        uint32_t position = formation + index * FORMATION_POS_BYTES;
        uint16_t dx = be16(image + position + FORMATION_POS_DX);
        uint16_t dy = be16(image + position + FORMATION_POS_DY);

        if (dx == FORMATION_SLOT_UNUSED || dy == FORMATION_SLOT_UNUSED) {
            wr32(image + entity + ENTITY_SCRIPT_CURSOR, 0xffffffffu);
            continue;
        }
        wr16(image + entity + ENTITY_X, (uint16_t)(dx + origin_x));
        wr16(image + entity + ENTITY_Y, (uint16_t)(dy + origin_y));
        wr32(image + entity + ENTITY_SCRIPT_CURSOR,
             be32(image + formation_script_offset(formation, slots, index)));
        wr32(image + entity + ENTITY_SCRIPT_BASE,
             be32(image + formation_script_base(formation, slots)));
    }
}

/* The fields PASS TWO writes in all five bodies. What differs is only the draw layer, the fire
 * countdown, the aim-changed byte and a handful of per-body extras, so those are arguments and the
 * extras are written by the caller. Returns the entity, or 0 for a slot the formation retired. */
static uint32_t spawn_arm_slot(uint8_t *image, uint32_t desc, uint32_t formation, unsigned slots,
                               unsigned index, uint16_t draw_layer, uint16_t fire_countdown,
                               int set_aim_changed) {
    uint32_t entities = be32(image + desc + ENEMY_DESC_GROUP);
    uint32_t entity = be32(image + entities + index * ENTITY_GROUP_PTR_BYTES);
    uint32_t step;

    if ((int32_t)be32(image + entity + ENTITY_SCRIPT_CURSOR) < 0) {
        wr16(image + entity + ENTITY_ACTIVE, 0);
        return 0;
    }
    step = addr_add(be32(image + formation_script_base(formation, slots)),
                    be32(image + entity + ENTITY_SCRIPT_CURSOR));

    wr16(image + entity + ENTITY_DX, be16(image + step + MOVE_SCRIPT_DX));
    wr16(image + entity + ENTITY_DY, be16(image + step + MOVE_SCRIPT_DY));
    wr16(image + entity + ENTITY_STEP_COUNTDOWN, be16(image + step + MOVE_SCRIPT_DURATION));
    wr16(image + entity + ENTITY_DRAW_LAYER, draw_layer);
    wr16(image + entity + ENTITY_ACTIVE, 1);
    wr16(image + entity + ENTITY_DYING, 0);
    wr16(image + entity + ENTITY_BASE_FRAME, be16(image + desc + ENEMY_DESC_BASE_FRAME));
    wr16(image + entity + ENTITY_ITEM_KIND, be16(image + desc + ENEMY_DESC_ITEM_KIND));
    wr16(image + entity + ENTITY_FRAME_OFFSET, be16(image + step + MOVE_SCRIPT_FRAME));
    wr16(image + entity + ENTITY_FIRE_COUNTDOWN, fire_countdown);
    wr16(image + entity + ENTITY_FIRE_RELOAD, be16(image + desc + ENEMY_DESC_FIRE_RELOAD));
    /* `st 24(a3)` on three bodies and `clr.w 24(a3)` on the other two, and the difference is
     * observable: the `st` writes ONE byte of the word and leaves the other as the arena had it. */
    if (set_aim_changed)
        image[entity + ENTITY_AIM_CHANGED] = SCC_TRUE;
    else
        wr16(image + entity + ENTITY_AIM_CHANGED, 0);
    wr16(image + entity + ENTITY_PATH_SELECT, be16(image + desc + ENEMY_DESC_HANDLER));
    wr16(image + entity + ENTITY_PATH_CURSOR, 0);
    return entity;
}

/* The `movea.l (a1),a1` every body opens with: the formation index selects a longword pointer.
 *
 * `move.w 8(a0),d1 / lsl.w #2,d1 / adda.l d1,a1` has the same shape as `bomb_blast_step`'s D0 read
 * — a word load feeding a LONG add — but not the same hazard, and the difference is provable rather
 * than assumed: the only route into any of the five bodies is `spawn_script_step` @ 0x12fc4, whose
 * `clr.l d1` @ 0x12fe8 and `muls.w #$4,d1` leave D1 a clean 32-bit value, and the sixteen-byte
 * stubs between them touch no data register. So the high word is zero on every reachable path and
 * the index is the zero-extension below. */
static uint32_t spawn_formation_record(const uint8_t *image, uint32_t record, uint32_t table) {
    uint16_t index = be16(image + record + SPAWN_REC_FORMATION);
    return be32(image + table + (uint16_t)(index * FORMATION_TBL_ENTRY_BYTES));
}

/* spawn_formation_common @ 0x130aa — the four-slot plain enemy formation. */
void spawn_formation_common(uint8_t *image, uint32_t record, uint32_t desc, uint32_t table) {
    uint32_t formation = spawn_formation_record(image, record, table);
    unsigned index;

    spawn_place_slots(image, record, desc, formation, ENTITY_GROUP_SLOTS);
    for (index = 0; index < ENTITY_GROUP_SLOTS; index++) {
        uint32_t entity = spawn_arm_slot(image, desc, formation, ENTITY_GROUP_SLOTS, index,
                                         SPAWN_DRAW_LAYER_TOP, SPAWN_FIRE_COUNTDOWN_15, 1);
        if (entity == 0)
            continue;
        wr16(image + entity + ENTITY_FACING, 0);
        wr16(image + entity + ENTITY_HIT_POINTS, be16(image + desc + ENEMY_DESC_HIT_POINTS));
        wr16(image + entity + ENTITY_FIRING, 0);
    }
}

/* spawn_single_common @ 0x131a4 — the one-slot objects, whose hit-point word doubles as the
 * animation period (include/entity.h, ENTITY_ANIM_PERIOD) and is written into both fields. */
void spawn_single_common(uint8_t *image, uint32_t record, uint32_t desc) {
    uint32_t formation = spawn_formation_record(image, record, A_formation_tbl_single);
    uint32_t entity;

    spawn_place_slots(image, record, desc, formation, 1);
    entity = spawn_arm_slot(image, desc, formation, 1, 0, SPAWN_DRAW_LAYER_UNDER,
                            SPAWN_FIRE_COUNTDOWN_15, 1);
    if (entity == 0)
        return;
    wr16(image + entity + ENTITY_DEPTH_SELECT, 0);
    wr16(image + entity + ENTITY_HIT_POINTS, be16(image + desc + ENEMY_DESC_HIT_POINTS));
    wr16(image + entity + ENTITY_ANIM_TIMER, be16(image + desc + ENEMY_DESC_HIT_POINTS));
    wr16(image + entity + ENTITY_FIRING, 0);
}

/* spawn_bigobj_parts_common @ 0x132dc — the big object's four parts, which
 * are the only entities whose +24/+26 hold a DEATH OFFSET rather than an aim flag and a facing
 * (include/entity.h, ENTITY_PART_DEATH_DX). Its aim-changed byte is cleared, not set. */
void spawn_bigobj_parts_common(uint8_t *image, uint32_t record, uint32_t desc, uint32_t table) {
    uint32_t formation = spawn_formation_record(image, record, table);
    unsigned index;

    spawn_place_slots(image, record, desc, formation, ENTITY_GROUP_SLOTS);
    for (index = 0; index < ENTITY_GROUP_SLOTS; index++) {
        uint32_t entity = spawn_arm_slot(image, desc, formation, ENTITY_GROUP_SLOTS, index,
                                         SPAWN_DRAW_LAYER_TOP, SPAWN_FIRE_COUNTDOWN_10, 0);
        if (entity == 0)
            continue;
        wr16(image + entity + ENTITY_FIRING, 0);
        wr16(image + entity + ENTITY_HIT_POINTS, be16(image + desc + ENEMY_DESC_HIT_POINTS));
        wr16(image + entity + ENTITY_PART_DEATH_DX, be16(image + desc + ENEMY_DESC_DEATH_DX));
        wr16(image + entity + ENTITY_PART_DEATH_DY, be16(image + desc + ENEMY_DESC_DEATH_DY));
    }
}

/* spawn_turret_common @ 0x1343e — the eight turret groups. The only body
 * that writes ENTITY_KIND, and the only one that gives a facing other than zero. It writes NO hit
 * points at all: a turret keeps whatever `clear_actor_arrays` or its last life left there. */
void spawn_turret_common(uint8_t *image, uint32_t record, uint32_t desc, uint32_t table) {
    uint32_t formation = spawn_formation_record(image, record, table);
    unsigned index;

    spawn_place_slots(image, record, desc, formation, ENTITY_GROUP_SLOTS);
    for (index = 0; index < ENTITY_GROUP_SLOTS; index++) {
        uint32_t entity = spawn_arm_slot(image, desc, formation, ENTITY_GROUP_SLOTS, index,
                                         SPAWN_DRAW_LAYER_UNDER,
                                         SPAWN_FIRE_COUNTDOWN_15, 1);
        if (entity == 0)
            continue;
        wr16(image + entity + ENTITY_DEPTH_SELECT, 0);
        wr16(image + entity + ENTITY_FACING, SPAWN_FACING_START);
        wr16(image + entity + ENTITY_KIND, be16(image + desc + ENEMY_DESC_KIND));
    }
}

/* spawn_squadron_common @ 0x13544 — the four seven-slot a-groups, whose
 * formation records are therefore seven positions, seven script offsets and one base. */
void spawn_squadron_common(uint8_t *image, uint32_t record, uint32_t desc) {
    uint32_t formation = spawn_formation_record(image, record, A_formation_tbl_squadron);
    unsigned index;

    spawn_place_slots(image, record, desc, formation, ENTITY_GROUP_A_SLOTS);
    for (index = 0; index < ENTITY_GROUP_A_SLOTS; index++) {
        uint32_t entity = spawn_arm_slot(image, desc, formation, ENTITY_GROUP_A_SLOTS, index,
                                         SPAWN_DRAW_LAYER_TOP, SPAWN_FIRE_COUNTDOWN_10, 0);
        if (entity != 0)
            wr16(image + entity + ENTITY_HIT_POINTS, be16(image + desc + ENEMY_DESC_HIT_POINTS));
    }
}

/* The 26 stubs `A_spawn_handler_tbl` points at. Each is sixteen bytes that load an enemy descriptor
 * and a formation table and `bra` into one of the five bodies, so the DATA is what distinguishes
 * them and it is data here too. `table` is unused by the two bodies that carry their own. */
typedef enum {
    SPAWN_BODY_SQUADRON, SPAWN_BODY_TURRET, SPAWN_BODY_SINGLE,
    SPAWN_BODY_PARTS, SPAWN_BODY_FORMATION, SPAWN_BODY_ITEM_BOMB
} spawn_body;

typedef struct {
    uint32_t desc;
    uint32_t table;
    spawn_body body;
} spawn_stub_row;

static const spawn_stub_row SPAWN_STUBS[] = {
    {A_enemy_desc_00, 0,                        SPAWN_BODY_SQUADRON},   /*  0 @ 0x1351c */
    {A_enemy_desc_01, 0,                        SPAWN_BODY_SQUADRON},   /*  1 @ 0x13526 */
    {A_enemy_desc_03, 0,                        SPAWN_BODY_SQUADRON},   /*  2 @ 0x13530 */
    {A_enemy_desc_02, 0,                        SPAWN_BODY_SQUADRON},   /*  3 @ 0x1353a */
    {A_enemy_desc_04, A_formation_tbl_turret_b, SPAWN_BODY_TURRET},     /*  4 @ 0x133fe */
    {A_enemy_desc_05, A_formation_tbl_turret_b, SPAWN_BODY_TURRET},     /*  5 @ 0x1340e */
    {A_enemy_desc_06, A_formation_tbl_turret_b, SPAWN_BODY_TURRET},     /*  6 @ 0x1341e */
    {A_enemy_desc_07, A_formation_tbl_turret_b, SPAWN_BODY_TURRET},     /*  7 @ 0x1342e */
    {A_enemy_desc_08, A_formation_tbl_turret_a, SPAWN_BODY_TURRET},     /*  8 @ 0x133be */
    {A_enemy_desc_09, A_formation_tbl_turret_a, SPAWN_BODY_TURRET},     /*  9 @ 0x133ce */
    {A_enemy_desc_0a, A_formation_tbl_turret_a, SPAWN_BODY_TURRET},     /* 10 @ 0x133de */
    {A_enemy_desc_0b, A_formation_tbl_turret_a, SPAWN_BODY_TURRET},     /* 11 @ 0x133ee */
    {A_enemy_desc_10, 0,                        SPAWN_BODY_SINGLE},     /* 12 @ 0x13190 */
    {A_enemy_desc_11, 0,                        SPAWN_BODY_SINGLE},     /* 13 @ 0x1319a */
    {A_enemy_desc_0c, A_formation_tbl_parts,    SPAWN_BODY_PARTS},      /* 14 @ 0x1329c */
    {A_enemy_desc_0e, A_formation_tbl_parts,    SPAWN_BODY_PARTS},      /* 15 @ 0x1328c */
    {A_enemy_desc_0d, A_formation_tbl_parts,    SPAWN_BODY_PARTS},      /* 16 @ 0x132ac */
    {A_enemy_desc_12, A_formation_tbl_a,        SPAWN_BODY_FORMATION},  /* 17 @ 0x1305a */
    {A_enemy_desc_13, A_formation_tbl_a,        SPAWN_BODY_FORMATION},  /* 18 @ 0x1306a */
    {A_enemy_desc_14, A_formation_tbl_parts_c,  SPAWN_BODY_PARTS},      /* 19 @ 0x132cc */
    {A_enemy_desc_15, A_formation_tbl_b,        SPAWN_BODY_FORMATION},  /* 20 @ 0x1307a */
    {A_enemy_desc_16, A_formation_tbl_b,        SPAWN_BODY_FORMATION},  /* 21 @ 0x1308a */
    {A_enemy_desc_17, A_formation_tbl_b,        SPAWN_BODY_FORMATION},  /* 22 @ 0x1309a */
    {0,               0,                        SPAWN_BODY_ITEM_BOMB},  /* 23 @ 0x13044 */
    {A_enemy_desc_18, 0,                        SPAWN_BODY_SINGLE},     /* 24 @ 0x13186 */
    {A_enemy_desc_0f, A_formation_tbl_parts_b,  SPAWN_BODY_PARTS},      /* 25 @ 0x132bc */
};
#define SPAWN_STUB_COUNT (sizeof SPAWN_STUBS / sizeof SPAWN_STUBS[0])

static void spawn_stub(uint8_t *image, uint32_t record, unsigned stub) {
    const spawn_stub_row *row = &SPAWN_STUBS[stub];
    switch (row->body) {
    case SPAWN_BODY_SQUADRON:  spawn_squadron_common(image, record, row->desc); break;
    case SPAWN_BODY_TURRET:    spawn_turret_common(image, record, row->desc, row->table); break;
    case SPAWN_BODY_SINGLE:    spawn_single_common(image, record, row->desc); break;
    case SPAWN_BODY_PARTS:     spawn_bigobj_parts_common(image, record, row->desc, row->table);
                               break;
    case SPAWN_BODY_FORMATION: spawn_formation_common(image, record, row->desc, row->table); break;
    case SPAWN_BODY_ITEM_BOMB: spawn_item_bomb(image, record); break;
    }
}

/* spawn_script_step @ 0x12fc4 — fire at most one script record per call.
 *
 * The two ITEM types are OFFERS rather than commands: a weapon power-up the player cannot use (the
 * level is already at WEAPON_LEVEL_FULL, or one is already on screen) and a bomb item after the
 * first both fall back to SPAWN_TYPE_FALLBACK, which is an ordinary enemy. The weapon arm also
 * CLEARS `A_item_pickup_pending` as it declines — so declining once re-arms the next offer. */
void spawn_script_step(uint8_t *image) {
    uint32_t record = addr_add(be32(image + A_spawn_script_ptr), be32(image + A_spawn_script_cursor));
    uint16_t type;

    if (be16(image + record + SPAWN_REC_TRIGGER) == SPAWN_SCRIPT_END)
        return;
    if ((int16_t)be16(image + A_scroll_pos) < (int16_t)be16(image + record + SPAWN_REC_TRIGGER))
        return;

    type = be16(image + record + SPAWN_REC_TYPE);
    if (type == SPAWN_TYPE_WEAPON_ITEM) {
        if (be16(image + A_weapon_level) == WEAPON_LEVEL_FULL
            || be16(image + A_item_pickup_pending) != 0) {
            type = SPAWN_TYPE_FALLBACK;
            wr16(image + A_item_pickup_pending, 0);
        }
    }
    if (type == SPAWN_TYPE_BOMB_ITEM) {
        if (be16(image + A_item_bomb_spawned) != 0)
            type = SPAWN_TYPE_FALLBACK;
        else
            image[A_item_bomb_spawned] = SCC_TRUE;   /* `st $176a6`: one byte of the word */
    }

    /* A type past the table's twenty-six entries reads a longword past it and `jsr`s whatever is
     * there — which is not a behaviour to reconstruct, only a crash. No script in the game carries
     * one; the guard says so rather than inventing a target. */
    if (type < SPAWN_STUB_COUNT)
        spawn_stub(image, record, type);
    wr32(image + A_spawn_script_cursor, be32(image + A_spawn_script_cursor) + SPAWN_REC_BYTES);
}

/* ================================================================================================
 * The glue. Each takes the original's registers; the comment maps register -> role.
 * ============================================================================================= */
void g_clear_object_list(uint8_t *image) { clear_object_list(image); }
void g_bomb_fall_step(uint8_t *image) { bomb_fall_step(image); }
void g_bomb_publish(uint8_t *image) { bomb_publish(image); }
/* D0 = whatever the frame loop left there; its HIGH WORD selects the offset row. */
void g_bomb_blast_step(uint8_t *image, uint32_t scratch) { bomb_blast_step(image, scratch); }
void g_bomb_blast_publish(uint8_t *image) { bomb_blast_publish(image); }
void g_player_bullets_move_all(uint8_t *image) { player_bullets_move_all(image); }
void g_player_bullets_publish_all(uint8_t *image) { player_bullets_publish_all(image); }
void g_player_shot_slots_release(uint8_t *image) { player_shot_slots_release(image); }
void g_bomb_blast_vs_entities(uint8_t *image) { bomb_blast_vs_entities(image); }
void g_player_bullets_vs_entities(uint8_t *image) { player_bullets_vs_entities(image); }
void g_muzzle_flash_publish_all(uint8_t *image) { muzzle_flash_publish_all(image); }
void g_enemy_bullets_move(uint8_t *image) { enemy_bullets_move(image); }
void g_enemy_bullets_publish(uint8_t *image) { enemy_bullets_publish(image); }
void g_enemies_fire_all(uint8_t *image) { enemies_fire_all(image); }
void g_turrets_aim_all(uint8_t *image) { turrets_aim_all(image); }
void g_turrets_publish_all(uint8_t *image) { turrets_publish_all(image); }
void g_spawn_script_step(uint8_t *image) { spawn_script_step(image); }

/* A0 = the shot's five-pointer slot table. */
void g_player_bullets_move_group(uint8_t *image, uint32_t slots) {
    player_bullets_move_group(image, slots);
}
/* A0 = the slot table, A1 = the five display records. */
void g_player_bullets_publish_group(uint8_t *image, uint32_t slots, uint32_t records) {
    player_bullets_publish_group(image, slots, records);
}
/* A0 = the slot table, A4 = the shot's busy flag. */
void g_player_shot_slot_release_if_empty(uint8_t *image, uint32_t slots, uint32_t busy) {
    player_shot_slot_release_if_empty(image, slots, busy);
}
/* A1 = the blast state (the four points start one record in), A5 = the enemy descriptor. */
void g_bomb_blast_vs_entity_groups(uint8_t *image, uint32_t point, uint32_t desc) {
    bomb_blast_vs_entity_groups(image, point, desc);
}
/* A0 = the blast state, A5 = the enemy descriptor. */
void g_bomb_blast_vs_entities_if_active(uint8_t *image, uint32_t blast, uint32_t desc) {
    bomb_blast_vs_entities_if_active(image, blast, desc);
}
/* A0 = the shot's slot table, A5 = the enemy descriptor. */
void g_player_bullet_vs_entity_groups(uint8_t *image, uint32_t slots, uint32_t desc) {
    player_bullet_vs_entity_groups(image, slots, desc);
}
/* A0 = the shot's slot table. */
void g_player_bullets_vs_entities_group(uint8_t *image, uint32_t slots) {
    player_bullets_vs_entities_group(image, slots);
}
/* A5 = the enemy descriptor, A1 = the two display records. */
void g_muzzle_flash_publish_pair(uint8_t *image, uint32_t desc, uint32_t records) {
    muzzle_flash_publish_pair(image, desc, records);
}
/* A5 = the descriptor, A1 = the display records, D7 = the slot count minus one. */
void g_muzzle_flash_publish_group(uint8_t *image, uint32_t desc, uint32_t records,
                                  uint32_t count) {
    muzzle_flash_publish_group(image, desc, records, count);
}
/* A5 = the descriptor, A6 = the bullet-array cursor, D2/D3 = the aim point, D4/D5 = the muzzle. */
void g_enemy_bullet_spawn_aimed(uint8_t *image, uint32_t desc, uint32_t cursor,
                                uint32_t aim_x, uint32_t aim_y, uint32_t x, uint32_t y) {
    enemy_bullet_spawn_aimed(image, desc, &cursor, (uint16_t)aim_x, (uint16_t)aim_y,
                             (uint16_t)x, (uint16_t)y);
}
/* A0 = the turret's entity record. */
void g_turret_aim_step(uint8_t *image, uint32_t entity) { turret_aim_step(image, entity); }
/* A1 = the group's pointer array. */
void g_turrets_aim_group(uint8_t *image, uint32_t group) { turrets_aim_group(image, group); }
void g_turrets_aim_group_active(uint8_t *image, uint32_t group) {
    turrets_aim_group_active(image, group);
}
/* A0 = the group's slots, A3 = its barrel display records, A4/A6 = the two offset tables. */
void g_turret_publish_group(uint8_t *image, uint32_t group, uint32_t records,
                            uint32_t barrel_tbl, uint32_t hit_tbl) {
    turret_publish_group(image, group, records, barrel_tbl, hit_tbl);
}
/* A0 = the script record. */
void g_spawn_item_bomb(uint8_t *image, uint32_t record) { spawn_item_bomb(image, record); }
/* A0 = the script record, A5 = the descriptor, A1 = the formation table. */
void g_spawn_formation_common(uint8_t *image, uint32_t record, uint32_t desc, uint32_t table) {
    spawn_formation_common(image, record, desc, table);
}
void g_spawn_bigobj_parts_common(uint8_t *image, uint32_t record, uint32_t desc, uint32_t table) {
    spawn_bigobj_parts_common(image, record, desc, table);
}
void g_spawn_turret_common(uint8_t *image, uint32_t record, uint32_t desc, uint32_t table) {
    spawn_turret_common(image, record, desc, table);
}
/* A0 = the script record, A5 = the descriptor. */
void g_spawn_single_common(uint8_t *image, uint32_t record, uint32_t desc) {
    spawn_single_common(image, record, desc);
}
void g_spawn_squadron_common(uint8_t *image, uint32_t record, uint32_t desc) {
    spawn_squadron_common(image, record, desc);
}
