/* entity.c — the enemy entity system: the per-frame movers, the display-list publishers, the
 * big-object depth and hide passes, the power-up items and the frame/animation counters.
 *
 * Every slot is reached through the pointer tables at 0x19246..0x1946e (include/entity.h), never by
 * indexing the arena, so a "group" in this file is always the ADDRESS OF A POINTER ARRAY and an
 * "entity" is always an absolute arena address the game itself stored there.
 *
 * NOTHING HERE STOPS AT A SEAM. `item_drop_if_formation_cleared` @ 0x121fe ends its bonus-item arm
 * with `bsr score_add_1000` (0x10b8c) into the score subsystem's `abcd` chain, and that chain is
 * ported — so the routine is diffed whole, score digits included, and the X FLAG it hands back is
 * the chain's own (see the routine's comment).
 */
#include "machine.h"
#include "common.h"  /* SCC_TRUE and display_record_write, shared with hud.c and weapons.c */
#include "entity.h"
#include "player.h"  /* the player record, whose first three fields the pickup box is built from */
#include "sound.h"   /* sfx_play_2 @ 0x121e6, which the pickup calls */
#include "weapons.h" /* A_weapon_level, the counter the pickup award raises */

/* ================================================================================================
 * The frame counter and the cycling animation frame ids.
 * ============================================================================================= */

/* count_game_frame @ 0x11654 — the frame loop's first call. */
void count_game_frame(uint8_t *image) {
    wr32(image + A_frame_counter, be32(image + A_frame_counter) + 1);
}

/* One `lea <id>+1,a0 / adda.w d0,a0 / move.b (a0),<id>` triple: the id's own little table starts
 * one byte past it, and the phase indexes into that. */
static void anim_frame_pick(uint8_t *image, uint32_t frame_id, uint32_t phase) {
    image[frame_id] = image[frame_id + ANIM_FRAME_TABLE_OFFSET + phase];
}

/* anim_frame_ids_update @ 0x119fc — re-derive the six cycling sprite ids from the frame counter.
 *
 * The counter is re-read for each mask rather than masked once, which is what the original does
 * (`move.l $17764,d0 / andi.l` four times); it cannot change mid-routine, so this is transcription
 * rather than a behaviour. */
void anim_frame_ids_update(uint8_t *image) {
    uint32_t two_phase = be32(image + A_frame_counter) & ANIM_PHASE_MASK_2;
    anim_frame_pick(image, A_anim_frame_a, two_phase);
    anim_frame_pick(image, A_anim_frame_b, two_phase);

    uint32_t four_phase = be32(image + A_frame_counter) & ANIM_PHASE_MASK_3;
    anim_frame_pick(image, A_anim_frame_item0, four_phase);
    anim_frame_pick(image, A_anim_frame_item1, four_phase);
    anim_frame_pick(image, A_anim_frame_item3, four_phase);

    anim_frame_pick(image, A_anim_frame_bomb, two_phase);
}

/* ================================================================================================
 * The movers.
 * ============================================================================================= */

/* enemy_bomb_drop @ 0x12f2e — put a bomb at (x, y) in the first free display record.
 *
 * REPRODUCES A BUG. The scan cursor is bumped on BOTH arms of the loop and compared with the slot
 * count before the record is written, so a free record found in the LAST slot takes the cursor to
 * ENEMY_BOMB_SLOTS and the routine leaves without using it — the sixteenth bomb slot is
 * unreachable. Recreate, not remaster.
 */
void enemy_bomb_drop(uint8_t *image, uint32_t entity, uint16_t x, uint16_t y) {
    uint32_t record = A_display_list;
    wr16(image + A_enemy_bomb_slot_scan, 0);
    for (;;) {
        int occupied = image[record + DISPLAY_REC_ACTIVE] != 0;
        wr16(image + A_enemy_bomb_slot_scan, be16(image + A_enemy_bomb_slot_scan) + 1);
        if (be16(image + A_enemy_bomb_slot_scan) == ENEMY_BOMB_SLOTS)
            return;
        if (!occupied)
            break;
        record += DISPLAY_REC_BYTES;
    }
    display_record_write(image, record, x, y, image[A_anim_frame_bomb],
                         DISPLAY_ACTIVE_UNDER_SCENERY);
    image[entity + ENTITY_HAS_DROPPED] = SCC_TRUE;   /* `st 46(a0)`: the high byte of the word only */
}

/* The live half of entity_move: step by the current velocity, and take the next movement-script
 * record when the countdown runs out. */
static void entity_move_script(uint8_t *image, uint32_t entity) {
    wr16(image + entity + ENTITY_X,
         be16(image + entity + ENTITY_X) + be16(image + entity + ENTITY_DX));
    wr16(image + entity + ENTITY_Y,
         be16(image + entity + ENTITY_Y) + be16(image + entity + ENTITY_DY));
    wr16(image + entity + ENTITY_STEP_COUNTDOWN,
         be16(image + entity + ENTITY_STEP_COUNTDOWN) - 1);
    if (be16(image + entity + ENTITY_STEP_COUNTDOWN) != 0)
        return;

    wr32(image + entity + ENTITY_SCRIPT_CURSOR,
         be32(image + entity + ENTITY_SCRIPT_CURSOR) + MOVE_SCRIPT_BYTES);
    uint32_t step = be32(image + entity + ENTITY_SCRIPT_BASE)
                  + be32(image + entity + ENTITY_SCRIPT_CURSOR);
    if (be16(image + step + MOVE_SCRIPT_DX) == SCRIPT_TERMINATOR) {
        wr16(image + entity + ENTITY_ACTIVE, 0);
        return;
    }
    wr16(image + entity + ENTITY_DX, be16(image + step + MOVE_SCRIPT_DX));
    wr16(image + entity + ENTITY_DY, be16(image + step + MOVE_SCRIPT_DY));
    wr16(image + entity + ENTITY_STEP_COUNTDOWN, be16(image + step + MOVE_SCRIPT_DURATION));
    wr16(image + entity + ENTITY_FRAME_OFFSET, be16(image + step + MOVE_SCRIPT_FRAME));
}

/* ...and the dying half: walk the death-frame table, sink two pixels a frame, and drop this
 * bomber's one bomb on the way down. */
static void entity_move_death_path(uint8_t *image, uint32_t entity) {
    uint32_t table = be32(image + A_entity_path_tbl_ptrs
                          + (uint16_t)(be16(image + entity + ENTITY_PATH_SELECT)
                                       * ENTITY_PATH_PTR_BYTES));
    /* `adda.w d0,a1` sign-extends its word, so a cursor past 0x3fff walks BACKWARDS. Kept. */
    uint32_t step = table + (uint32_t)(int32_t)(int16_t)
                    (uint16_t)(be16(image + entity + ENTITY_PATH_CURSOR) * 2);

    if ((int16_t)be16(image + step) < 0) {          /* the table ends on a negative word */
        if (be16(image + entity + ENTITY_KIND) == ENTITY_KIND_BOMBER)
            wr16(image + entity + ENTITY_HAS_DROPPED, 0);
        wr16(image + entity + ENTITY_ACTIVE, 0);
        return;
    }
    wr16(image + entity + ENTITY_FRAME_OFFSET,
         be16(image + step) - be16(image + entity + ENTITY_BASE_FRAME));
    wr16(image + entity + ENTITY_PATH_CURSOR, be16(image + entity + ENTITY_PATH_CURSOR) + 1);
    wr16(image + entity + ENTITY_Y, be16(image + entity + ENTITY_Y) + ENEMY_BOMB_DY);

    if (be16(image + entity + ENTITY_KIND) != ENTITY_KIND_BOMBER)
        return;
    if (be16(image + entity + ENTITY_HAS_DROPPED) != 0)
        return;
    enemy_bomb_drop(image, entity,
                    be16(image + entity + ENTITY_X), be16(image + entity + ENTITY_Y));
}

/* entity_move @ 0x12e9e — one slot's per-frame update. */
void entity_move(uint8_t *image, uint32_t entity) {
    if (be16(image + entity + ENTITY_ACTIVE) == 0)
        return;
    if (be16(image + entity + ENTITY_DYING) != 0)
        entity_move_death_path(image, entity);
    else
        entity_move_script(image, entity);
}

/* The walk every group mover shares: `movea.l (a6)+,a0 / bsr entity_move`, `count` times. */
static void entities_move_group(uint8_t *image, uint32_t group, unsigned count) {
    for (unsigned slot = 0; slot < count; slot++)
        entity_move(image, be32(image + group + slot * ENTITY_GROUP_PTR_BYTES));
}

/* entities_move_group4 @ 0x12e54 */
void entities_move_group4(uint8_t *image, uint32_t group) {
    entities_move_group(image, group, ENTITY_GROUP_SLOTS);
}

/* entities_move_one_group @ 0x12e82 — `movea.l (a6),a0`, no post-increment: one slot. */
void entities_move_one_group(uint8_t *image, uint32_t group) {
    entity_move(image, be32(image + group));
}

/* entities_move_groups_extra @ 0x12e22 — the five four-slot groups after the big object. */
void entities_move_groups_extra(uint8_t *image) {
    for (unsigned i = 0; i < ENTITY_GROUP_X_COUNT; i++)
        entities_move_group4(image, A_entity_group_x0 + i * ENTITY_GROUP_X_STRIDE);
}

/* entities_move_bigobj @ 0x12e64 — the three single-slot pair objects.
 *
 * The third is reached as `lea $5a960,a0` rather than through the table, which is the SAME slot the
 * third table entry points at (arena slot 70, measured). Spelt as the table entry it equals, with
 * the literal kept beside it in include/entity.h so a moved arena fails by name rather than
 * silently addressing a different record. */
void entities_move_bigobj(uint8_t *image) {
    entities_move_one_group(image, A_entity_group_pair);
    entities_move_one_group(image, A_entity_group_pair + ENTITY_GROUP_PAIR_STRIDE);
    entity_move(image, A_entity_pair_slot_2);
}

/* entities_move_bigobj_parts @ 0x12e88 */
void entities_move_bigobj_parts(uint8_t *image) {
    entities_move_group4(image, A_entity_group_bigobj);
}

/* The four 7-slot groups, IN THE ORIGINAL'S OWN ORDER — a0, a1, a3, a2, which is not address order.
 * The order is observable: `enemy_bomb_drop` allocates from a display list shared by every slot, so
 * two entities dropping a bomb in one frame take slots in the sequence these groups are walked. */
static const uint32_t ENTITY_GROUPS_A[] = {
    A_entity_group_a0, A_entity_group_a1, A_entity_group_a3, A_entity_group_a2,
};

/* entities_move_all @ 0x12d5c — call 10 of the frame loop: every one of the 91 slots. */
void entities_move_all(uint8_t *image) {
    for (unsigned i = 0; i < sizeof ENTITY_GROUPS_A / sizeof *ENTITY_GROUPS_A; i++)
        entities_move_group(image, ENTITY_GROUPS_A[i], ENTITY_GROUP_A_SLOTS);
    for (unsigned i = 0; i < ENTITY_GROUP_T_COUNT; i++)
        entities_move_group4(image, A_entity_group_t0 + i * ENTITY_GROUP_T_STRIDE);
    entities_move_bigobj(image);
    entities_move_bigobj_parts(image);
    entities_move_groups_extra(image);
    entities_move_group4(image, A_entity_group_a4);
}

/* enemy_bombs_move @ 0x1184e — the dropped bombs fall, and every one of the sixteen records gets
 * the current bomb frame WHETHER OR NOT IT IS ACTIVE. Faithful: the frame store is unconditional. */
void enemy_bombs_move(uint8_t *image) {
    uint32_t record = A_display_list;
    for (unsigned slot = 0; slot < ENEMY_BOMB_SLOTS; slot++, record += DISPLAY_REC_BYTES) {
        wr16(image + record + DISPLAY_REC_Y, be16(image + record + DISPLAY_REC_Y) + ENEMY_BOMB_DY);
        if ((int16_t)be16(image + record + DISPLAY_REC_Y) >= (int16_t)ENTITY_RETIRE_Y)
            image[record + DISPLAY_REC_ACTIVE] = 0;
        image[record + DISPLAY_REC_FRAME] = image[A_anim_frame_bomb];
    }
}

/* ================================================================================================
 * The publishers. Each writes one 6-byte display record per slot of the group it walks.
 * ============================================================================================= */

/* The four `clr` stores an empty slot leaves: the whole record zeroed, so the renderer skips it. */
static void publish_clear(uint8_t *image, uint32_t record) {
    display_record_write(image, record, 0, 0, 0, 0);
}

static void publish_position(uint8_t *image, uint32_t entity, uint32_t record) {
    wr16(image + record + DISPLAY_REC_X, be16(image + entity + ENTITY_X));
    wr16(image + record + DISPLAY_REC_Y, be16(image + entity + ENTITY_Y));
}

/* A dying entity is published at an offset, so its explosion sits where the sprite's centre was. */
static void publish_death_offset(uint8_t *image, uint32_t record, uint16_t dx, uint16_t dy) {
    wr16(image + record + DISPLAY_REC_X, be16(image + record + DISPLAY_REC_X) + dx);
    wr16(image + record + DISPLAY_REC_Y, be16(image + record + DISPLAY_REC_Y) + dy);
}

/* The frame byte and the active byte, which every publisher writes the same way: the frame is
 * truncated to a byte (`move.b d0,4(a1)`) and the active byte is the LOW half of ENTITY_DRAW_LAYER
 * (`move.b 7(a2),5(a1)`). */
static void publish_frame(uint8_t *image, uint32_t entity, uint32_t record, uint16_t frame) {
    image[record + DISPLAY_REC_FRAME] = (uint8_t)frame;
    image[record + DISPLAY_REC_ACTIVE] = image[entity + ENTITY_DRAW_LAYER_BYTE];
}

static uint16_t entity_offset_frame(const uint8_t *image, uint32_t entity) {
    return be16(image + entity + ENTITY_FRAME_OFFSET) + be16(image + entity + ENTITY_BASE_FRAME);
}

/* The death offset four of the five publishers take from the DESCRIPTOR's +18/+20. (The fifth,
 * `entity_publish_group_offset`, reads the same two words out of the ENTITY's own +24/+26, which is
 * why it does this step itself.) */
static void publish_desc_death_offset(uint8_t *image, uint32_t record, uint32_t desc) {
    publish_death_offset(image, record, be16(image + desc + ENEMY_DESC_DEATH_DX),
                         be16(image + desc + ENEMY_DESC_DEATH_DY));
}

/* PUBLISH_NO_DEATH_OFFSET: the descriptor argument of the one publisher that never applies one.
 * `entity_publish_group_plain` @ 0x137f4 takes no descriptor at all — the turret bodies are drawn
 * where they stand whether they are dying or not. */
#define PUBLISH_NO_DEATH_OFFSET 0u

/* One live slot's record: the position, the descriptor's death offset while the entity is dying,
 * then the frame byte and the draw-layer active byte. THE FIVE PUBLISHERS' BODIES ARE THIS, and
 * what the original spells as five routines differs only in the arguments — which frame, which
 * descriptor (or none), how many slots, and what counts as an empty slot. Faithfulness is
 * unchanged: every store below is still the store that routine makes, in that order. */
static void publish_entity(uint8_t *image, uint32_t entity, uint32_t record, uint32_t desc,
                           uint16_t frame) {
    publish_position(image, entity, record);
    if (desc != PUBLISH_NO_DEATH_OFFSET && be16(image + entity + ENTITY_DYING) != 0)
        publish_desc_death_offset(image, record, desc);
    publish_frame(image, entity, record, frame);
}

/* The body @ 0x13702 and @ 0x13992 share to the instruction: position, the descriptor's death
 * offset while dying, and base + offset as the frame. Only the slot count differs. */
static void publish_group_offset_frame(uint8_t *image, uint32_t group, uint32_t records,
                                       uint32_t desc, unsigned count) {
    for (unsigned slot = 0; slot < count; slot++, records += DISPLAY_REC_BYTES) {
        uint32_t entity = be32(image + group + slot * ENTITY_GROUP_PTR_BYTES);
        if (be16(image + entity + ENTITY_ACTIVE) == 0) {
            publish_clear(image, records);
            continue;
        }
        publish_entity(image, entity, records, desc, entity_offset_frame(image, entity));
    }
}

/* entity_publish_group_facing @ 0x136a2 — the turret-style groups, whose live frame is the base
 * plus the FACING and whose dying frame is the base plus the frame offset. The original reaches the
 * second by subtracting the facing again, which is the same number. */
void entity_publish_group_facing(uint8_t *image, uint32_t group, uint32_t records, uint32_t desc) {
    for (unsigned slot = 0; slot < ENTITY_GROUP_SLOTS; slot++, records += DISPLAY_REC_BYTES) {
        uint32_t entity = be32(image + group + slot * ENTITY_GROUP_PTR_BYTES);
        if (be16(image + entity + ENTITY_ACTIVE) == 0) {
            publish_clear(image, records);
            continue;
        }
        uint16_t frame = be16(image + entity + ENTITY_DYING) != 0
                         ? entity_offset_frame(image, entity)
                         : (uint16_t)(be16(image + entity + ENTITY_BASE_FRAME)
                                      + be16(image + entity + ENTITY_FACING));
        publish_entity(image, entity, records, desc, frame);
    }
}

/* entity_publish_group_a4 @ 0x13702 — A_entity_group_a4's four slots under A_enemy_desc_14. */
void entity_publish_group_a4(uint8_t *image) {
    publish_group_offset_frame(image, A_entity_group_a4, A_dl_entity_a4, A_enemy_desc_14,
                               ENTITY_GROUP_SLOTS);
}

/* entity_publish_group_last @ 0x13992 — a 7-slot group under its descriptor. */
void entity_publish_group_last(uint8_t *image, uint32_t group, uint32_t records, uint32_t desc) {
    publish_group_offset_frame(image, group, records, desc, ENTITY_GROUP_A_SLOTS);
}

/* entity_publish_group_plain @ 0x137f4 — the turret BODIES. The only publisher that consults
 * ENTITY_HIDDEN_UNDER_BIGOBJ, and the only one that never offsets a dying entity. */
void entity_publish_group_plain(uint8_t *image, uint32_t group, uint32_t records) {
    for (unsigned slot = 0; slot < ENTITY_GROUP_SLOTS; slot++, records += DISPLAY_REC_BYTES) {
        uint32_t entity = be32(image + group + slot * ENTITY_GROUP_PTR_BYTES);
        if (be16(image + entity + ENTITY_ACTIVE) == 0
            || be16(image + entity + ENTITY_HIDDEN_UNDER_BIGOBJ) != 0) {
            publish_clear(image, records);
            continue;
        }
        publish_entity(image, entity, records, PUBLISH_NO_DEATH_OFFSET,
                       entity_offset_frame(image, entity));
    }
}

/* entity_publish_anim @ 0x1387a — ONE slot, and the only publisher that advances an animation.
 *
 * The frame is bumped by one either because a hit set the one-shot ENTITY_FRAME_BUMP latch or
 * because the entity is firing and its ENTITY_ANIM_TIMER has just run out; both arms clear the
 * latch, so a hit flash lasts exactly one published frame. A DYING entity skips the whole thing. */
void entity_publish_anim(uint8_t *image, uint32_t group, uint32_t records, uint32_t desc) {
    uint32_t entity = be32(image + group);
    if (be16(image + entity + ENTITY_ACTIVE) == 0) {
        publish_clear(image, records);
        return;
    }
    publish_position(image, entity, records);
    int dying = be16(image + entity + ENTITY_DYING) != 0;
    if (dying)
        publish_desc_death_offset(image, records, desc);

    uint16_t frame = entity_offset_frame(image, entity);
    int bump = 0;
    if (!dying) {
        if (be16(image + entity + ENTITY_FRAME_BUMP) != 0) {
            bump = 1;
        } else if (be16(image + entity + ENTITY_FIRING) != 0) {
            wr16(image + entity + ENTITY_ANIM_TIMER, be16(image + entity + ENTITY_ANIM_TIMER) - 1);
            if (be16(image + entity + ENTITY_ANIM_TIMER) == 0) {
                wr16(image + entity + ENTITY_ANIM_TIMER, be16(image + entity + ENTITY_ANIM_PERIOD));
                bump = 1;
            }
        }
    }
    if (bump) {
        frame = (uint8_t)(frame + 1);      /* `addi.b #$1,d0` — the byte wraps, the word does not */
        wr16(image + entity + ENTITY_FRAME_BUMP, 0);
    }
    publish_frame(image, entity, records, frame);
}

/* entity_publish_group_offset @ 0x138e8 — the big object's parts, whose death offset comes out of
 * the ENTITY's own +24/+26 rather than out of a descriptor. */
void entity_publish_group_offset(uint8_t *image, uint32_t group, uint32_t records) {
    for (unsigned slot = 0; slot < ENTITY_GROUP_SLOTS; slot++, records += DISPLAY_REC_BYTES) {
        uint32_t entity = be32(image + group + slot * ENTITY_GROUP_PTR_BYTES);
        if (be16(image + entity + ENTITY_ACTIVE) == 0) {
            publish_clear(image, records);
            continue;
        }
        /* NOT `publish_entity`: this is the one publisher whose death offset comes out of the
         * ENTITY's own +24/+26 rather than out of a descriptor. */
        publish_position(image, entity, records);
        if (be16(image + entity + ENTITY_DYING) != 0)
            publish_death_offset(image, records, be16(image + entity + ENTITY_PART_DEATH_DX),
                                 be16(image + entity + ENTITY_PART_DEATH_DY));
        publish_frame(image, entity, records, entity_offset_frame(image, entity));
    }
}

/* entities_publish_facing_groups @ 0x13634 */
void entities_publish_facing_groups(uint8_t *image) {
    static const uint32_t DESCRIPTORS[ENTITY_GROUP_X_COUNT] = {
        A_enemy_desc_12, A_enemy_desc_13, A_enemy_desc_15, A_enemy_desc_16, A_enemy_desc_17,
    };
    for (unsigned i = 0; i < ENTITY_GROUP_X_COUNT; i++)
        entity_publish_group_facing(image, A_entity_group_x0 + i * ENTITY_GROUP_X_STRIDE,
                                    A_dl_entity_x0 + i * DL_GROUP4_STRIDE, DESCRIPTORS[i]);
}

/* entities_publish_bigobj_group @ 0x13764 */
void entities_publish_bigobj_group(uint8_t *image) {
    entity_publish_group_offset(image, A_entity_group_bigobj, A_dl_entity_bigobj);
}

/* entities_publish_plain_groups @ 0x13774 — the eight turret bodies. Their display runs are two
 * separate progressions with the barrel records between them (include/entity.h). */
void entities_publish_plain_groups(uint8_t *image) {
    for (unsigned i = 0; i < ENTITY_GROUP_T_COUNT; i++) {
        uint32_t records = (i < DL_TURRET_RUN_GROUPS)
                         ? A_dl_entity_t0 + i * DL_GROUP4_STRIDE
                         : A_dl_entity_t4 + (i - DL_TURRET_RUN_GROUPS) * DL_GROUP4_STRIDE;
        entity_publish_group_plain(image, A_entity_group_t0 + i * ENTITY_GROUP_T_STRIDE, records);
    }
}

/* entities_publish_anim_groups @ 0x13838 */
void entities_publish_anim_groups(uint8_t *image) {
    static const uint32_t DESCRIPTORS[ENTITY_GROUP_PAIR_COUNT] = {
        A_enemy_desc_10, A_enemy_desc_11, A_enemy_desc_18,
    };
    for (unsigned i = 0; i < ENTITY_GROUP_PAIR_COUNT; i++)
        entity_publish_anim(image, A_entity_group_pair + i * ENTITY_GROUP_PAIR_STRIDE,
                            A_dl_entity_pair + i * DISPLAY_REC_BYTES, DESCRIPTORS[i]);
}

/* entities_publish_last_groups @ 0x1393a — the four 7-slot groups, in the original's order (a0, a1,
 * a3, a2), each with the descriptor whose ENEMY_DESC_GROUP points at it. */
void entities_publish_last_groups(uint8_t *image) {
    static const uint32_t DESCRIPTORS[] = {
        A_enemy_desc_00, A_enemy_desc_01, A_enemy_desc_03, A_enemy_desc_02,
    };
    for (unsigned i = 0; i < sizeof ENTITY_GROUPS_A / sizeof *ENTITY_GROUPS_A; i++)
        entity_publish_group_last(image, ENTITY_GROUPS_A[i],
                                  A_dl_entity_a0 + i * DL_GROUP7_STRIDE, DESCRIPTORS[i]);
}

/* entities_publish_all @ 0x1361c — call 25 of the frame loop. */
void entities_publish_all(uint8_t *image) {
    entities_publish_plain_groups(image);
    entities_publish_anim_groups(image);
    entities_publish_bigobj_group(image);
    entities_publish_facing_groups(image);
    entities_publish_last_groups(image);
    entity_publish_group_a4(image);
}

/* bigobj_extra_parts_publish @ 0x102de — call 26. Stamps three fixed sprite ids over the frame
 * bytes entities_publish_bigobj_group just wrote for parts 1..3, when part 0 carries the marker. */
void bigobj_extra_parts_publish(uint8_t *image) {
    static const uint8_t FRAMES[BIGOBJ_EXTRA_PARTS] = {
        BIGOBJ_EXTRA_PART_FRAME_0, BIGOBJ_EXTRA_PART_FRAME_1, BIGOBJ_EXTRA_PART_FRAME_2,
    };
    uint32_t part = be32(image + A_entity_group_bigobj);
    if (be16(image + part + ENTITY_ACTIVE) == 0)
        return;
    if (be16(image + part + ENTITY_HIT_POINTS) != BIGOBJ_EXTRA_MARKER)
        return;
    for (unsigned i = 0; i < BIGOBJ_EXTRA_PARTS; i++)
        image[A_dl_entity_bigobj + (i + 1) * DISPLAY_REC_BYTES + DISPLAY_REC_FRAME] = FRAMES[i];
}

/* ================================================================================================
 * The big object's two spatial passes.
 * ============================================================================================= */

/* entity_hide_test @ 0x1179a — call 12's leaf: set the entity's hide flag while it lies inside a
 * BIGOBJ_BOX_SIZE box around any live big-object part.
 *
 * THE CLEAR IS INSIDE THE LOOP, not after it, so a non-overlapping part clears the flag and the
 * walk carries on — the settled value is whatever the LAST part tested left. A part that is dying
 * clears the flag and returns, so the effect stops the moment the big object starts exploding. */
void entity_hide_test(uint8_t *image, uint32_t entity) {
    for (unsigned slot = 0; slot < ENTITY_GROUP_SLOTS; slot++) {
        uint32_t part = be32(image + A_entity_group_bigobj + slot * ENTITY_GROUP_PTR_BYTES);
        if (be16(image + part + ENTITY_ACTIVE) != 0) {
            int16_t probe_x = (int16_t)(be16(image + entity + ENTITY_X) + BIGOBJ_PROBE_OFFSET);
            int16_t probe_y = (int16_t)(be16(image + entity + ENTITY_Y) + BIGOBJ_PROBE_OFFSET);
            int16_t box_x = (int16_t)be16(image + part + ENTITY_X);
            int16_t box_y = (int16_t)be16(image + part + ENTITY_Y);
            if (probe_x >= box_x && probe_y >= box_y
                && probe_x <= (int16_t)(box_x + BIGOBJ_BOX_SIZE)
                && probe_y <= (int16_t)(box_y + BIGOBJ_BOX_SIZE)) {
                if (be16(image + part + ENTITY_DYING) != 0)
                    wr16(image + entity + ENTITY_HIDDEN_UNDER_BIGOBJ, 0);
                else
                    image[entity + ENTITY_HIDDEN_UNDER_BIGOBJ] = SCC_TRUE;   /* `st 48(a1)`, one byte */
                return;
            }
        }
        wr16(image + entity + ENTITY_HIDDEN_UNDER_BIGOBJ, 0);
    }
}

/* entity_hide_under_bigobj_group @ 0x11784 */
void entity_hide_under_bigobj_group(uint8_t *image, uint32_t group) {
    for (unsigned slot = 0; slot < ENTITY_GROUP_SLOTS; slot++) {
        uint32_t entity = be32(image + group + slot * ENTITY_GROUP_PTR_BYTES);
        if (be16(image + entity + ENTITY_ACTIVE) != 0)
            entity_hide_test(image, entity);
    }
}

/* entity_hide_under_bigobj @ 0x1175c — call 12. Only the first FOUR turret groups are tested. */
#define HIDE_TEST_GROUPS 4u
void entity_hide_under_bigobj(uint8_t *image) {
    for (unsigned i = 0; i < HIDE_TEST_GROUPS; i++)
        entity_hide_under_bigobj_group(image, A_entity_group_t0 + i * ENTITY_GROUP_T_STRIDE);
}

/* bigobj_depth_test @ 0x11820 — set the big-object part's depth flag when any live member of the
 * group is FURTHER DOWN the screen than it is — the member's y plus the same 0x0e probe still
 * exceeding the part's.
 *
 * THE CLEAR IS AFTER THE LOOP here, unlike entity_hide_test's: a match returns immediately and a
 * full walk with no match clears once. */
void bigobj_depth_test(uint8_t *image, uint32_t part, uint32_t group) {
    for (unsigned slot = 0; slot < ENTITY_GROUP_SLOTS; slot++) {
        uint32_t entity = be32(image + group + slot * ENTITY_GROUP_PTR_BYTES);
        if (be16(image + entity + ENTITY_ACTIVE) == 0)
            continue;
        int16_t part_y = (int16_t)be16(image + part + ENTITY_Y);
        int16_t entity_y = (int16_t)(be16(image + entity + ENTITY_Y) + BIGOBJ_PROBE_OFFSET);
        if (entity_y > part_y) {
            image[part + ENTITY_DEPTH_SELECT] = SCC_TRUE;      /* `st 28(a1)`, one byte */
            return;
        }
    }
    wr16(image + part + ENTITY_DEPTH_SELECT, 0);
}

/* bigobj_overlap_depth_update @ 0x117f4 — call 11. Part 0 is tested against group x0 and part 1
 * against group x1; parts 2 and 3 are never tested. */
void bigobj_overlap_depth_update(uint8_t *image) {
    uint32_t part0 = be32(image + A_entity_group_bigobj);
    if (be16(image + part0 + ENTITY_ACTIVE) != 0)
        bigobj_depth_test(image, part0, A_entity_group_x0);

    uint32_t part1 = be32(image + A_entity_group_bigobj + ENTITY_GROUP_PTR_BYTES);
    if (be16(image + part1 + ENTITY_ACTIVE) != 0)
        bigobj_depth_test(image, part1, A_entity_group_x0 + ENTITY_GROUP_X_STRIDE);
}

/* ================================================================================================
 * The power-up items.
 * ============================================================================================= */

/* item_drop_step @ 0x118a2 — the bomb item: straight down until it leaves the screen. Reached only
 * by `items_move_all`'s tail branch; Ghidra left it unnamed and ../names.txt now carries this name. */
void item_drop_step(uint8_t *image, uint32_t item) {
    if (be16(image + item + ITEM_ACTIVE) == 0)
        return;
    wr16(image + item + ITEM_Y, be16(image + item + ITEM_Y) + ENEMY_BOMB_DY);
    if ((int16_t)be16(image + item + ITEM_Y) >= (int16_t)ENTITY_RETIRE_Y)
        wr16(image + item + ITEM_ACTIVE, 0);
}

/* item_fall_step @ 0x118bc — the bonus item: straight down for as long as its ITEM_CURSOR lasts.
 * The countdown is a LONGWORD and the test is on the sign after the decrement, so the item survives
 * exactly the number of frames the drop seeded (0x32) and is retired on the frame after. */
void item_fall_step(uint8_t *image, uint32_t item) {
    if (be16(image + item + ITEM_ACTIVE) == 0)
        return;
    wr32(image + item + ITEM_CURSOR, be32(image + item + ITEM_CURSOR) - 1);
    if ((int32_t)be32(image + item + ITEM_CURSOR) < 0) {
        wr16(image + item + ITEM_ACTIVE, 0);
        return;
    }
    wr16(image + item + ITEM_Y, be16(image + item + ITEM_Y) + ENEMY_BOMB_DY);
}

/* item_path_step @ 0x118da — the weapon and life items: walk A_item_flight_path, which LOOPS at its
 * terminator rather than ending, and retire only by leaving the bottom of the screen. */
void item_path_step(uint8_t *image, uint32_t item) {
    if (be16(image + item + ITEM_ACTIVE) == 0)
        return;
    uint32_t step = A_item_flight_path + be32(image + item + ITEM_CURSOR);
    if (be16(image + step + ITEM_PATH_DX) == SCRIPT_TERMINATOR) {
        wr32(image + item + ITEM_CURSOR, 0);
        step = A_item_flight_path;
    }
    wr16(image + item + ITEM_X, be16(image + item + ITEM_X) + be16(image + step + ITEM_PATH_DX));
    wr16(image + item + ITEM_Y, be16(image + item + ITEM_Y) + be16(image + step + ITEM_PATH_DY));
    wr32(image + item + ITEM_CURSOR, be32(image + item + ITEM_CURSOR) + ITEM_PATH_STEP_BYTES);
    if ((int16_t)be16(image + item + ITEM_Y) >= (int16_t)ENTITY_RETIRE_Y)
        wr16(image + item + ITEM_ACTIVE, 0);
}

/* items_move_all @ 0x1187a — call 13. */
void items_move_all(uint8_t *image) {
    item_path_step(image, A_item_weapon);
    item_path_step(image, A_item_life);
    item_fall_step(image, A_item_extra);
    item_drop_step(image, A_item_bomb);
}

/* One item's display record: the position and a frame while it is live, four zeroed fields when it
 * is not. The bonus item's frame is a literal and the other three cycle. */
static void item_publish_one(uint8_t *image, uint32_t item, uint32_t record,
                             uint8_t frame, uint8_t active) {
    if (be16(image + item + ITEM_ACTIVE) == 0) {
        publish_clear(image, record);
        return;
    }
    display_record_write(image, record, be16(image + item + ITEM_X),
                         be16(image + item + ITEM_Y), frame, active);
}

/* The bonus item is the one whose sprite never cycles: `move.b #$a1,4(a1)` @ 0x1196e. */
#define ITEM_EXTRA_FRAME  0xa1u

/* items_publish @ 0x1191c — call 34. The order is weapon, extra, life, bomb, which is neither the
 * item records' address order nor the display records'. */
void items_publish(uint8_t *image) {
    item_publish_one(image, A_item_weapon, A_dl_item_0, image[A_anim_frame_item0], DISPLAY_ACTIVE_ON_TOP);
    item_publish_one(image, A_item_extra, A_dl_item_2, ITEM_EXTRA_FRAME, DISPLAY_ACTIVE_ON_TOP);
    item_publish_one(image, A_item_life, A_dl_item_1, image[A_anim_frame_item1], DISPLAY_ACTIVE_ON_TOP);
    item_publish_one(image, A_item_bomb, A_dl_item_3, image[A_anim_frame_item3], DISPLAY_ACTIVE_UNDER_SCENERY);
}

/* The item's own box is a fixed square at its (x, y); the player's comes out of the sprite record
 * of the frame it is drawing. Both axes are tested by the same shape. */
#define ITEM_PICKUP_BOX 0x10u

static int span_overlaps(int16_t box_lo, int16_t box_size, int16_t point) {
    if (box_lo > point)
        return box_lo < (int16_t)(point + ITEM_PICKUP_BOX);
    return (int16_t)(box_lo + box_size) > point;
}

/* sprite_hitbox_test @ 0x11698 — the player-vs-item overlap AND the pickup it performs.
 *
 * The player's box is the sprite record's DRAW offset plus its hit-box corner — the two are added
 * separately (`add.w 8(a4),d2 / add.w 12(a4),d2`), so a record whose draw offset moves shifts the
 * hit box with the sprite. On an overlap the routine retires the item, plays the pickup effect
 * and FALLS THROUGH into item_pickup_award with the kind still in D6 — whose `rts` returns to
 * this routine's own caller, which is why items_pickup_check goes on to the next item. */
void sprite_hitbox_test(uint8_t *image, uint32_t item, uint16_t kind) {
    uint32_t record = A_sprite_bank + (uint32_t)image[A_player + PLAYER_FRAME] * SPRITE_RECORD_BYTES;

    int16_t box_x = (int16_t)(be16(image + A_player + PLAYER_X)
                              + be16(image + record + SPRITE_REC_DRAW_DX)
                              + be16(image + record + SPRITE_REC_HIT_DX));
    if (!span_overlaps(box_x, (int16_t)be16(image + record + SPRITE_REC_HIT_W),
                       (int16_t)be16(image + item + ITEM_X)))
        return;

    int16_t box_y = (int16_t)(be16(image + A_player + PLAYER_Y)
                              + be16(image + record + SPRITE_REC_DRAW_DY)
                              + be16(image + record + SPRITE_REC_HIT_DY));
    if (!span_overlaps(box_y, (int16_t)be16(image + record + SPRITE_REC_HIT_H),
                       (int16_t)be16(image + item + ITEM_Y)))
        return;

    wr16(image + item + ITEM_ACTIVE, 0);
    sfx_play_2(image);
    item_pickup_award(image, kind);
}

/* items_pickup_check @ 0x1165c — call 15 of the frame loop. All three items are offered in turn,
 * so one frame can pick up more than one. */
void items_pickup_check(uint8_t *image) {
    if (be16(image + A_item_weapon + ITEM_ACTIVE) != 0)
        sprite_hitbox_test(image, A_item_weapon, ITEM_KIND_WEAPON);
    if (be16(image + A_item_bomb + ITEM_ACTIVE) != 0)
        sprite_hitbox_test(image, A_item_bomb, ITEM_KIND_BOMB);
    if (be16(image + A_item_life + ITEM_ACTIVE) != 0)
        sprite_hitbox_test(image, A_item_life, ITEM_KIND_LIFE);
}

/* item_pickup_award @ 0x11714 — the counter a pickup raises, entered by falling out of
 * sprite_hitbox_test with the kind in D6. The three caps are spelt three different ways in the
 * original; include/entity.h has the argument for keeping each named for its own comparison. */
void item_pickup_award(uint8_t *image, uint16_t kind) {
    if (kind == ITEM_KIND_WEAPON) {
        if (be16(image + A_weapon_level) != WEAPON_LEVEL_FULL)
            wr16(image + A_weapon_level, be16(image + A_weapon_level) + 1);
        return;
    }
    if (kind == ITEM_KIND_BOMB) {
        if (be16(image + A_bombs) != BOMBS_FULL)
            wr16(image + A_bombs, be16(image + A_bombs) + 1);
        return;
    }
    if ((int16_t)be16(image + A_lives) <= (int16_t)LIVES_NO_AWARD_ABOVE)
        wr16(image + A_lives, be16(image + A_lives) + 1);
}

/* item_drop_if_formation_cleared @ 0x121fe — the whole routine, its `bsr score_add_1000` included.
 *
 * The whole formation must be gone: any slot that is still active and not yet dying aborts the
 * drop, so a squadron rewards only its last kill.
 *
 * THE X FLAG IS AN ARGUMENT AND AN ANSWER, because the bonus arm ends in the score chain (whose
 * first instruction is an `abcd` that adds X — include/hud.h) and the routine's own exit restores
 * only the registers: `movem.l (a7)+,#$7fff` and `rts` write no condition code. So the caller's X
 * reaches the chain untouched — the `lea`/`move`/`clr`/`st` between the entry and the `bsr` leave
 * it alone — and what the chain leaves is what the caller's next instruction sees. On the three
 * arms that never reach the chain the flag simply passes through. */
#define ITEM_EXTRA_FALL_FRAMES 0x32u   /* `move.l #$32,4(a0)` @ 0x12254 */

unsigned item_drop_if_formation_cleared(uint8_t *image, uint32_t group, uint16_t x, uint16_t y,
                                        uint16_t kind, unsigned extend_in) {
    for (unsigned slot = 0; slot < ENTITY_GROUP_A_SLOTS; slot++) {
        uint32_t entity = be32(image + group + slot * ENTITY_GROUP_PTR_BYTES);
        if (be16(image + entity + ENTITY_ACTIVE) != 0 && be16(image + entity + ENTITY_DYING) == 0)
            return extend_in;
    }

    uint32_t item = (kind == ITEM_KIND_WEAPON) ? A_item_weapon
                  : (kind == ITEM_KIND_BOMB)   ? A_item_extra
                                               : A_item_life;
    wr16(image + item + ITEM_X, x);
    wr16(image + item + ITEM_Y, y);
    wr32(image + item + ITEM_CURSOR, kind == ITEM_KIND_BOMB ? ITEM_EXTRA_FALL_FRAMES : 0);
    image[item + ITEM_ACTIVE] = SCC_TRUE;          /* `st 8(a0)`, the high byte of the word only */
    if (kind == ITEM_KIND_WEAPON)
        image[A_item_pickup_pending] = SCC_TRUE;   /* `st $176c2`, likewise one byte */
    if (kind == ITEM_KIND_BOMB)
        return score_add_award(image, SCORE_AWARD_1000, extend_in);   /* `bsr.w $10b8c` @ 0x12260 */
    return extend_in;
}

/* ================================================================================================
 * difficulty_apply_fire_rates @ 0x12cc8 — SLICE [0x12cc8, 0x12d58).
 *
 * The routine has no `rts`: it falls into `start_level` @ 0x11440 through a `bra.w`, so it is
 * verified as a slice ending at that branch. The name is ../names.txt's and is half right — as well
 * as the fire reloads it rewrites two classes' ENEMY_DESC_HIT_POINTS, and it applies the same
 * numbers on every stage rather than a per-level difficulty.
 * ============================================================================================= */
#define FIRE_RELOAD_COMMON  10u   /* `move.w #$a,d0`  -> nine classes' ENEMY_DESC_FIRE_RELOAD */
#define HIT_POINTS_TURRET   12u   /* `move.w #$c,d1`  -> the two facing classes' hit points */
#define FIRE_RELOAD_TURRET   7u   /* `move.w #$7,d2`  -> ...and their fire reload */
#define HIT_POINTS_A4       18u   /* `move.w #$12,d3` -> A_enemy_desc_14's hit points */

void difficulty_apply_fire_rates(uint8_t *image) {
    static const uint32_t COMMON[] = {
        A_enemy_desc_00, A_enemy_desc_04, A_enemy_desc_05, A_enemy_desc_06, A_enemy_desc_07,
        A_enemy_desc_08, A_enemy_desc_09, A_enemy_desc_0a, A_enemy_desc_0b,
    };
    static const uint32_t TURRET[] = { A_enemy_desc_12, A_enemy_desc_13 };

    for (unsigned i = 0; i < sizeof COMMON / sizeof *COMMON; i++)
        wr16(image + COMMON[i] + ENEMY_DESC_FIRE_RELOAD, FIRE_RELOAD_COMMON);
    for (unsigned i = 0; i < sizeof TURRET / sizeof *TURRET; i++) {
        wr16(image + TURRET[i] + ENEMY_DESC_FIRE_RELOAD, FIRE_RELOAD_TURRET);
        wr16(image + TURRET[i] + ENEMY_DESC_HIT_POINTS, HIT_POINTS_TURRET);
    }
    wr16(image + A_enemy_desc_14 + ENEMY_DESC_HIT_POINTS, HIT_POINTS_A4);
}

/* ================================================================================================
 * The glue. Each takes the original's registers; the comment maps register -> role.
 * ============================================================================================= */

/* No arguments. */
void g_count_game_frame(uint8_t *image) { count_game_frame(image); }
void g_anim_frame_ids_update(uint8_t *image) { anim_frame_ids_update(image); }
void g_entities_move_all(uint8_t *image) { entities_move_all(image); }
void g_entities_move_groups_extra(uint8_t *image) { entities_move_groups_extra(image); }
void g_entities_move_bigobj(uint8_t *image) { entities_move_bigobj(image); }
void g_entities_move_bigobj_parts(uint8_t *image) { entities_move_bigobj_parts(image); }
void g_enemy_bombs_move(uint8_t *image) { enemy_bombs_move(image); }
void g_entities_publish_all(uint8_t *image) { entities_publish_all(image); }
void g_entities_publish_facing_groups(uint8_t *image) { entities_publish_facing_groups(image); }
void g_entities_publish_bigobj_group(uint8_t *image) { entities_publish_bigobj_group(image); }
void g_entities_publish_plain_groups(uint8_t *image) { entities_publish_plain_groups(image); }
void g_entities_publish_anim_groups(uint8_t *image) { entities_publish_anim_groups(image); }
void g_entities_publish_last_groups(uint8_t *image) { entities_publish_last_groups(image); }
void g_entity_publish_group_a4(uint8_t *image) { entity_publish_group_a4(image); }
void g_bigobj_extra_parts_publish(uint8_t *image) { bigobj_extra_parts_publish(image); }
void g_entity_hide_under_bigobj(uint8_t *image) { entity_hide_under_bigobj(image); }
void g_bigobj_overlap_depth_update(uint8_t *image) { bigobj_overlap_depth_update(image); }
void g_items_move_all(uint8_t *image) { items_move_all(image); }
void g_items_publish(uint8_t *image) { items_publish(image); }
void g_difficulty_apply_fire_rates(uint8_t *image) { difficulty_apply_fire_rates(image); }

/* A0 = the entity record. */
void g_entity_move(uint8_t *image, uint32_t entity) { entity_move(image, entity); }
/* A6 = the group's pointer array. */
void g_entities_move_group4(uint8_t *image, uint32_t group) { entities_move_group4(image, group); }
void g_entities_move_one_group(uint8_t *image, uint32_t group) {
    entities_move_one_group(image, group);
}
/* A0 = the entity record, D0 = x, D1 = y. */
void g_enemy_bomb_drop(uint8_t *image, uint32_t entity, uint32_t x, uint32_t y) {
    enemy_bomb_drop(image, entity, (uint16_t)x, (uint16_t)y);
}
/* A0 = the group's pointer array, A1 = the display records, A5 = the enemy descriptor. */
void g_entity_publish_group_facing(uint8_t *image, uint32_t group, uint32_t records,
                                   uint32_t desc) {
    entity_publish_group_facing(image, group, records, desc);
}
void g_entity_publish_anim(uint8_t *image, uint32_t group, uint32_t records, uint32_t desc) {
    entity_publish_anim(image, group, records, desc);
}
void g_entity_publish_group_last(uint8_t *image, uint32_t group, uint32_t records, uint32_t desc) {
    entity_publish_group_last(image, group, records, desc);
}
/* A0 = the group's pointer array, A1 = the display records. */
void g_entity_publish_group_plain(uint8_t *image, uint32_t group, uint32_t records) {
    entity_publish_group_plain(image, group, records);
}
void g_entity_publish_group_offset(uint8_t *image, uint32_t group, uint32_t records) {
    entity_publish_group_offset(image, group, records);
}
/* A1 = the entity to hide or reveal. */
void g_entity_hide_test(uint8_t *image, uint32_t entity) { entity_hide_test(image, entity); }
/* A0 = the group's pointer array. */
void g_entity_hide_under_bigobj_group(uint8_t *image, uint32_t group) {
    entity_hide_under_bigobj_group(image, group);
}
/* A1 = the big object's part, A2 = the group tested against it. */
void g_bigobj_depth_test(uint8_t *image, uint32_t part, uint32_t group) {
    bigobj_depth_test(image, part, group);
}
/* A0 = the item record. */
void g_item_fall_step(uint8_t *image, uint32_t item) { item_fall_step(image, item); }
void g_item_drop_step(uint8_t *image, uint32_t item) { item_drop_step(image, item); }
void g_item_path_step(uint8_t *image, uint32_t item) { item_path_step(image, item); }
/* A0 = the item record, D6 = the item kind. */
void g_sprite_hitbox_test(uint8_t *image, uint32_t item, uint32_t kind) {
    sprite_hitbox_test(image, item, (uint16_t)kind);
}
/* No arguments. */
void g_items_pickup_check(uint8_t *image) { items_pickup_check(image); }
/* D6 = the item kind. */
void g_item_pickup_award(uint8_t *image, uint32_t kind) { item_pickup_award(image, (uint16_t)kind); }
/* A0 = the group's pointer array, D0 = x, D1 = y, D2 = the item kind, X = the incoming extend the
 * bonus arm's score chain adds; the return is the X the routine leaves. */
unsigned g_item_drop_if_formation_cleared(uint8_t *image, uint32_t group, uint32_t x, uint32_t y,
                                          uint32_t kind, unsigned extend_in) {
    return item_drop_if_formation_cleared(image, group, (uint16_t)x, (uint16_t)y, (uint16_t)kind,
                                          extend_in);
}
