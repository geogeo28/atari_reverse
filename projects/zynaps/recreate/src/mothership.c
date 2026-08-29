/* mothership.c — the boss encounter, end to end.
 *
 * THE ENCOUNTER HAS NO RECORDS OF ITS OWN. It borrows `include/enemy.h`'s eight wave slots at
 * A_enemy_slots — the head in the first two, four tail SEGMENT PAIRS after them — plus the five
 * tail parts at A_entity_boss_parts that `mothership_place_tail` lays out. include/mothership.h's
 * "THE BOSS'S OWN SLOTS" is the one home for that layout, and it is why the routines here stride
 * MOTHERSHIP_PAIR_BYTES where the wave code strides ENTITY_STRIDE.
 *
 * THE SPRITE BUILD IS A STATE MACHINE, driven by the byte at A_mothership_prep_stage:
 * mothership_place_tail and mothership_segments_respawn set it to 1, mothership_sprite_build_step
 * walks it 1 -> 2 -> 3 -> 4 doing one frame's worth of work per call and clearing it when it
 * arrives, and mothership_move_and_place clears it again on every frame the boss is on screen —
 * which is what stops the build re-running behind the tail it has just placed.
 *
 * Four of the nine routines here reach `enemy`'s script VM (0x14c66) or its formation spawner
 * (0x14a7c), and one reaches `score`; the rest are leaves over the records above.
 */
#include "machine.h"
#include "entity.h"
#include "mothership.h"
#include "init.h"
#include "sprite.h"
#include "enemy.h"
#include "collision.h"
#include "player.h"
#include "score.h"

/* Eight phase slots of MOTHERSHIP_FRAME_BYTES each — the shape sprite_preshift8_2px builds, so the
 * relation is expressed rather than restated as a second literal. */
#define MOTHERSHIP_BANK_BYTES (SPRITE_PRESHIFT_SLOTS * MOTHERSHIP_FRAME_BYTES)

#define PREP_STAGE_COPY 1        /* `cmpi.b #$1` — the stage that copies the raw frames in */
#define PREP_STAGE_PRESHIFT 2    /* ...and the first that pre-shifts one; `sub.b #$2,d0` */
#define PREP_STAGE_DONE 4        /* `cmpi.b #$4` — the stage that arms the encounter and resets */

/* ================================================================================================
 * mothership_place_tail @ 0x14f18 — lay the five boss segments out from the anchor.
 *
 * The anchor's x is read ONCE, before the loop, and stepped in the register; its y is re-read from
 * A_mothership_y inside the loop and written unchanged to every segment. So the five records end up
 * on one horizontal row, MOTHERSHIP_SEGMENT_X_STEP apart, each pointing at its own slice of the
 * sprite bank.
 * ============================================================================================= */
void mothership_place_tail(uint8_t *image) {
    uint32_t segment = A_entity_boss_parts;
    uint32_t sprite = A_mothership_sprite_bank;
    uint16_t x = be16(image + A_mothership_x);

    for (unsigned i = 0; i < MOTHERSHIP_TAIL_SEGMENTS; i++) {
        wr32(image + segment + ENTITY_SPRITE, sprite);
        wr16(image + segment + ENTITY_HEIGHT, MOTHERSHIP_SEGMENT_HEIGHT);
        image[segment + ENTITY_ALIVE] = 1;
        wr16(image + segment + ENTITY_Y, be16(image + A_mothership_y));
        wr16(image + segment + ENTITY_X, x);

        x = (uint16_t)(x + MOTHERSHIP_SEGMENT_X_STEP);
        sprite = addr_add(sprite, MOTHERSHIP_SEGMENT_SPRITE_BYTES);
        segment = addr_add(segment, ENTITY_STRIDE);
    }
    image[A_mothership_prep_stage] = PREP_STAGE_COPY;
}

/* Register map: no register inputs. A2 walks the segments, A4 the sprite bank, D0 carries x and D6
 * counts. No outputs but memory. */
void g_mothership_place_tail(uint8_t *image) {
    mothership_place_tail(image);
}

/* ================================================================================================
 * mothership_sprite_build_step @ 0x15128 — one frame's slice of building the boss sprite banks.
 *
 * Spread over three calls so no single frame pays for the whole build: call one copies both raw
 * frames into the banks, calls two and three pre-shift one bank each, and the third also arms the
 * encounter and resets the stage.
 *
 * THE STAGE ARITHMETIC IS SIGNED THEN UNSIGNED, in that order, and the mix is what bounds the
 * routine: `sub.b #$2` / `ext.w` sign-extends, and `mulu.w` then reads the result as UNSIGNED. A
 * stage of 0 therefore multiplies 0xfffe by the bank size and addresses ~0x5030000 — far outside
 * the image. It is unreachable rather than tolerated: the routine's only caller (0x1117e) is behind
 * `tst.b A_mothership_prep_stage / beq`, so the stage is non-zero on entry, and the stage-3 arm
 * clears it before anyone can call again. See STATUS.md.
 * ============================================================================================= */
static void mothership_copy_raw_frames(uint8_t *image) {
    uint32_t src = A_mothership_sprite_source;
    uint32_t dst = A_mothership_sprite_bank;

    for (unsigned bank = 0; bank < MOTHERSHIP_BANKS; bank++) {
        /* `movem.l` saves both cursors around the copy, so each bank starts from the base below
         * rather than from where the previous run left off — the strides differ, and that is why. */
        for (unsigned offset = 0; offset < MOTHERSHIP_FRAME_BYTES; offset += 4)
            wr32(image + addr_add(dst, offset), be32(image + addr_add(src, offset)));
        src = addr_add(src, MOTHERSHIP_FRAME_BYTES);
        dst = addr_add(dst, MOTHERSHIP_BANK_BYTES);
    }
}

static void mothership_preshift_one_bank(uint8_t *image, uint8_t stage) {
    uint16_t bank_index = (uint16_t)sign_ext8((uint8_t)(stage - PREP_STAGE_PRESHIFT));
    uint32_t bank_at = addr_add(A_mothership_sprite_bank,
                                (uint32_t)bank_index * MOTHERSHIP_BANK_BYTES);

    /* Source and destination are the SAME address: the pre-shift is in place (`movea.l a0,a1`). */
    sprite_preshift8_2px(image, bank_at, bank_at, MOTHERSHIP_FRAME_BYTES);
}

void mothership_sprite_build_step(uint8_t *image) {
    if (image[A_mothership_prep_stage] == PREP_STAGE_COPY) {
        mothership_copy_raw_frames(image);
        image[A_mothership_prep_stage]++;
        return;
    }

    mothership_preshift_one_bank(image, image[A_mothership_prep_stage]);
    image[A_mothership_prep_stage]++;
    if (image[A_mothership_prep_stage] != PREP_STAGE_DONE)
        return;

    image[A_mothership_ready] = 1;
    wr32(image + A_mothership_phase_timer, 0);
    image[A_mothership_prep_stage] = 0;
}

/* Register map: no register inputs. A0/A1 are the copy's cursors and the preshift's source and
 * destination (the same address — the pre-shift is in place); D0 carries the stage, D2 the frame
 * width, D7 counts the banks. No outputs but memory. */
void g_mothership_sprite_build_step(uint8_t *image) {
    mothership_sprite_build_step(image);
}

/* ================================================================================================
 * mothership_begin @ 0x14eda — arm the encounter, once the playfield is clear.
 *
 * The gate is `count_free_wave_slots() == ENEMY_SLOT_COUNT`: every wave slot free. It
 * then unpacks the boss sprite, loads the section's energy, parks the anchor at the right-hand edge
 * and FALLS THROUGH into mothership_place_tail — the two are one routine with two entry points, and
 * the call below is that fall-through spelt out.
 *
 * The energy byte is read UNSIGNED into a word while the SECTION indexing it is read SIGNED
 * (`ext.w`), so a section of 0x80 or more reads a byte below the table. Transcribed; the game's
 * sections are small. The original needs an `and.w #$ff,d0` for the unsigned half because
 * `move.b (a2,d0.w),d0` leaves D0's high byte from the `ext.w`; C's `uint8_t` read has no high
 * byte to clear, so there is no mask here to write — and none to mutate, which is why the
 * sweep in STATUS.md does not claim one.
 * ============================================================================================= */

void mothership_begin(uint8_t *image) {
    uint32_t energy_at;

    /* `cmp.b #$8,d0` — the immediate IS the slot count, i.e. "nothing else alive". */
    if (count_free_wave_slots(image) != ENEMY_SLOT_COUNT)
        return;

    mothership_sprite_expand(image);
    energy_at = addr_add(A_mothership_energy_by_section, sign_ext8(image[A_level_section]));
    wr16(image + A_boss_hitpoints, image[energy_at]);
    wr16(image + A_mothership_y, MOTHERSHIP_START_Y);
    wr16(image + A_mothership_x, MOTHERSHIP_START_X);
    mothership_place_tail(image);
}

/* Register map: no register inputs. D0 and A2 are scratch, and A2 is re-loaded by the tail. */
void g_mothership_begin(uint8_t *image) {
    mothership_begin(image);
}

/* ================================================================================================
 * mothership_draw @ 0x158f4 — blit the five live boss segments.
 *
 * Its only argument to the draw is D2, the bank's HALF-frame stride, which for the boss is the
 * five-cell expander frame halved (include/sprite.h, "how it indexes a preshift bank"). The
 * segments' own sprite pointers are MOTHERSHIP_SEGMENT_SPRITE_BYTES apart, set by
 * mothership_place_tail; this routine reads them and does not compute them.
 * ============================================================================================= */
#define MOTHERSHIP_DRAW_PHASE_STEP (BOSS_SPRITE_FRAME_BYTES / 2u)   /* `move.w #$3e8,d2` */

void mothership_draw(uint8_t *image) {
    uint32_t segment = A_entity_boss_parts;

    for (unsigned i = 0; i < MOTHERSHIP_TAIL_SEGMENTS; i++) {
        if (image[segment + ENTITY_ALIVE] != 0)
            draw_sprite_masked(image, segment, MOTHERSHIP_DRAW_PHASE_STEP);
        segment = addr_add(segment, ENTITY_STRIDE);
    }
}

/* Register map: no register inputs. A2 walks the segments and D6 counts them; both are saved across
 * the `bsr` and restored. */
void g_mothership_draw(uint8_t *image) {
    mothership_draw(image);
}

/* ================================================================================================
 * The encounter's per-section spawn arguments.
 *
 * `mothership_spawn_head` and `mothership_segments_respawn` open with the same seven instructions:
 * read the section, take the formation and the fire-flags byte it names, and turn the formation
 * into the base y `spawn_formation` is given. Both indexes are SIGN-EXTENDED, so a section or a
 * formation byte of 0x80 or more reads below its table — transcribed, the game's are small.
 * ============================================================================================= */
#define MOTHERSHIP_BASE_Y_ENTRY_BYTES 2u   /* `lsl.w #1,d0` — A_formation_base_y holds words */

struct mothership_spawn_args {
    uint16_t formation;    /* D7 after `ext.w`: the formation index spawn_formation is given */
    uint16_t base_y;       /* D4 */
    uint8_t fire_flags;    /* D5 */
};

static struct mothership_spawn_args mothership_spawn_args(const uint8_t *image) {
    uint32_t section = sign_ext8(image[A_level_section]);
    uint8_t formation = image[addr_add(A_mothership_formation_by_section, section)];
    struct mothership_spawn_args args;

    args.fire_flags = image[addr_add(A_mothership_spawn_param_by_section, section)];
    args.formation = (uint16_t)sign_ext8(formation);
    args.base_y = be16(image + addr_add(A_formation_base_y,
                                        sign_ext16((uint16_t)(args.formation
                                                              * MOTHERSHIP_BASE_Y_ENTRY_BYTES))));
    return args;
}

/* ================================================================================================
 * mothership_spawn_head @ 0x14f64 — build the boss sprite and put its head on the playfield.
 *
 * `mothership_sprite_preshift` (src/sprite.c) is what arms the encounter's flags; this routine then
 * spawns the head through the ordinary wave spawner and OVERWRITES the two records it landed in
 * with the head's own sprite and row count — the formation's own graphics attributes describe an
 * ordinary enemy, so the boss corrects them afterwards rather than by having a formation of its own.
 * ============================================================================================= */
void mothership_spawn_head(uint8_t *image) {
    struct mothership_spawn_args args;
    uint32_t record = A_enemy_slots;

    mothership_sprite_preshift(image);
    args = mothership_spawn_args(image);
    spawn_formation(image, args.formation, MOTHERSHIP_HEAD_TYPE, MOTHERSHIP_SPAWN_X, args.base_y,
                    args.fire_flags, A_mothership_head_sprite);

    for (unsigned i = 0; i < MOTHERSHIP_HEAD_RECORDS; i++) {
        wr32(image + record + ENTITY_SPRITE, A_mothership_head_sprite);
        wr16(image + record + ENTITY_HEIGHT, MOTHERSHIP_HEAD_ROWS);
        record = addr_add(record, ENTITY_STRIDE);
    }
}

/* Register map: no register inputs. D0..D5, D7 and A0/A2/A5 are all loaded here as spawn_formation's
 * arguments. No outputs but memory. */
void g_mothership_spawn_head(uint8_t *image) {
    mothership_spawn_head(image);
}

/* ================================================================================================
 * mothership_move_and_place @ 0x14fc8 — one frame of the boss head, and the tail that follows it.
 *
 * It runs the actor script on both head records, notes whether either has left the playfield, and
 * then re-derives the tail's anchor from the FIRST record alone and lays the five segments out from
 * it. Clearing A_mothership_prep_stage on the way out is what stops the sprite build machine
 * (`mothership_place_tail` sets that byte to 1 on every call) from re-running each frame.
 * ============================================================================================= */
#define EXPLOSION_GROUP_SECTION_BIT 0   /* `btst #0,$19670` — enemy.h: the end-of-section blast */

void mothership_move_and_place(uint8_t *image) {
    uint32_t record = A_enemy_slots;

    if (image[A_explosion_group_active_bits] & (1u << EXPLOSION_GROUP_SECTION_BIT))
        return;

    image[A_mothership_offscreen] = 0;
    for (unsigned i = 0; i < MOTHERSHIP_HEAD_RECORDS; i++) {
        int16_t x = (int16_t)be16(image + record + ENTITY_X);

        /* `tst.w` + `bmi` on the left, `cmpi.w` + `bge` on the right: both SIGNED. */
        if (x < 0 || x >= ACTOR_KEEP_X_MAX) {
            image[A_mothership_offscreen] = 1;
        } else {
            actor_script_run(image, record);
            actor_clamp_y(image, record);
        }
        record = addr_add(record, ENTITY_STRIDE);
    }

    wr16(image + A_mothership_x,
         (uint16_t)(be16(image + A_enemy_slots + ENTITY_X) - MOTHERSHIP_ANCHOR_X_LEAD));
    wr16(image + A_mothership_y,
         (uint16_t)(be16(image + A_enemy_slots + ENTITY_Y) - MOTHERSHIP_ANCHOR_Y_LEAD));
    mothership_place_tail(image);
    image[A_mothership_prep_stage] = 0;
}

/* Register map: no register inputs. A2 walks the two records and D0 counts them; both are saved
 * across the two `bsr`s and restored. No outputs but memory. */
void g_mothership_move_and_place(uint8_t *image) {
    mothership_move_and_place(image);
}

/* ================================================================================================
 * mothership_segments_update @ 0x151ba — one frame of the four tail segments.
 *
 * Each pair's EVEN record is the one the script moves; the odd one is a shadow placed to its right,
 * and the two die together. The type guard is what keeps this off the head, which shares the array.
 * ============================================================================================= */
void mothership_segments_update(uint8_t *image) {
    uint32_t segment = A_enemy_slots;

    for (unsigned pair = 0; pair < MOTHERSHIP_SEGMENT_PAIRS; pair++) {
        uint32_t shadow = addr_add(segment, ENTITY_STRIDE);

        if (image[segment + ENTITY_ALIVE] != 0
            && image[segment + ENTITY_TYPE] == MOTHERSHIP_SEGMENT_TYPE) {
            int16_t x;

            actor_script_run(image, segment);
            actor_clamp_y(image, segment);
            wr16(image + shadow + ENTITY_X,
                 (uint16_t)(be16(image + segment + ENTITY_X) + MOTHERSHIP_SHADOW_X_LEAD));
            wr16(image + shadow + ENTITY_Y, be16(image + segment + ENTITY_Y));

            x = (int16_t)be16(image + segment + ENTITY_X);
            if (x <= MOTHERSHIP_SEGMENT_KEEP_X_MIN || x >= ACTOR_KEEP_X_MAX) {
                image[segment + ENTITY_ALIVE] = 0;
                image[shadow + ENTITY_ALIVE] = 0;
            }
        }
        segment = addr_add(segment, MOTHERSHIP_PAIR_BYTES);
    }
}

/* Register map: no register inputs. A2 walks the pairs and D7 counts them; both are saved across
 * the two `bsr`s. No outputs but memory. */
void g_mothership_segments_update(uint8_t *image) {
    mothership_segments_update(image);
}

/* ================================================================================================
 * mothership_segments_respawn @ 0x1504a — bring the four tail segments back.
 *
 * It runs only with EVERY wave slot free, then marks the four ODD slots alive so `spawn_formation`
 * can fill only the even ones, spawns, and finally turns each spawned parent into a segment PAIR:
 * the odd slot is rewritten as the shadow, and the pair's energy byte is refreshed from the
 * section's. A parent the spawner did not manage to fill leaves its shadow dead instead.
 * ============================================================================================= */
#define MOTHERSHIP_SEGMENT_ENERGY_STRIDE 2u   /* `lea 2(a5),a5` — one byte per pair, every other */

/* The odd slot of pair `pair`: the shadow record, and the one the respawn marks alive up front. */
static uint32_t mothership_shadow_slot(unsigned pair) {
    return addr_add(addr_add(A_enemy_slots, ENTITY_STRIDE), pair * MOTHERSHIP_PAIR_BYTES);
}

void mothership_segments_respawn(uint8_t *image) {
    struct mothership_spawn_args args;
    uint32_t parent = A_enemy_slots;
    uint32_t energy_at = A_mothership_segment_energy;
    uint8_t energy;

    if (count_free_wave_slots(image) != ENEMY_SLOT_COUNT)
        return;

    args = mothership_spawn_args(image);
    for (unsigned pair = 0; pair < MOTHERSHIP_SEGMENT_PAIRS; pair++)
        image[mothership_shadow_slot(pair) + ENTITY_ALIVE] = 1;
    spawn_formation(image, args.formation, MOTHERSHIP_SEGMENT_TYPE, MOTHERSHIP_SPAWN_X,
                    args.base_y, args.fire_flags, A_mothership_sprite_bank);

    energy = image[addr_add(A_mothership_energy_by_section, sign_ext8(image[A_level_section]))];
    for (unsigned pair = 0; pair < MOTHERSHIP_SEGMENT_PAIRS; pair++) {
        uint32_t shadow = addr_add(parent, ENTITY_STRIDE);

        if (image[parent + ENTITY_ALIVE] == 0) {
            image[shadow + ENTITY_ALIVE] = 0;
        } else {
            wr16(image + shadow + ENTITY_Y, be16(image + parent + ENTITY_Y));
            wr16(image + shadow + ENTITY_X,
                 (uint16_t)(be16(image + parent + ENTITY_X) + MOTHERSHIP_SHADOW_X_LEAD));
            image[energy_at] = energy;
            wr32(image + shadow + ENTITY_SPRITE, A_mothership_segment_sprite);
            image[shadow + ENTITY_TYPE] = MOTHERSHIP_SEGMENT_TYPE;
            wr16(image + shadow + ENTITY_HEIGHT, MOTHERSHIP_SEGMENT_ROWS);
        }
        parent = addr_add(parent, MOTHERSHIP_PAIR_BYTES);
        energy_at = addr_add(energy_at, MOTHERSHIP_SEGMENT_ENERGY_STRIDE);
    }
    image[A_mothership_prep_stage] = PREP_STAGE_COPY;
}

/* Register map: no register inputs. A2/A3 walk the pairs, A5 the energy bytes, D0..D7 are the spawn
 * arguments and scratch. No outputs but memory. */
void g_mothership_segments_respawn(uint8_t *image) {
    mothership_segments_respawn(image);
}

/* ================================================================================================
 * mothership_segment_hit @ 0x15222 — take a hit on one half of a two-slot enemy.
 *
 * THE ARGUMENT IS EITHER HALF and the routine folds it onto the pair's EVEN member, so a hit on the
 * shadow costs the same pair its energy. The fold is `((index - 1) & ~1) + 1` over the entity index
 * — pairs (9,10), (11,12), (13,14), (15,16) all resolving to 9, 11, 13, 15 — and that index is then
 * both the offset into A_enemy_pair_hitpoints and the record the explosion is written over.
 *
 * `ext.w` AFTER the fold is what makes it a BYTE: only the low eight bits of the folded index
 * survive, sign-extended. And the `and.w #$ffff` between the divide and the fold is a NO-OP on the
 * low word — it does not clear the remainder `divu.w` leaves in the high one, which nothing here
 * reads either. Both are transcribed as what they are.
 *
 * THE DIVIDE COSTS AN `__udivsi3` ON TARGET that the original's one `divu.w #$2c` does not, exactly
 * as `bomb_collision_row` in src/weapon.c does and for the same reason: narrowing the dividend to a
 * word is only equivalent while the record sits within 64 KB of the table, which neither C nor this
 * differential can prove. STATUS.md carries that residual once, for both.
 *
 * AND IT DIVERGES ON QUOTIENT OVERFLOW, which is a second thing the same instruction does and this
 * C does not. `divu.w` leaves its destination UNCHANGED (and sets V) when the quotient will not fit
 * in sixteen bits, so a `segment` below A_entity_table — a difference of 0xffffffxx, a quotient of
 * about 0x5d17_0000 — leaves the fold running on the raw difference's low word, where the C folds
 * the truncated quotient instead. Unreachable from the game: both callers hand it one of entity
 * slots 9..16, all of them above the table. Stated rather than modelled, and recorded in
 * STATUS.md's mothership section beside the cost above.
 * ============================================================================================= */
#define PAIR_INDEX_ALIGN 0xfffeu       /* `and.w #$fffe` — the fold's "round down to even" step */
#define ENTITY_ALIVE_EXPLODING 0x80u   /* `move.b #$80,14(a6)` — entity.h: bit 7 = exploding */

/* Rewrite one record as its half of the pair's explosion. */
static void segment_to_explosion(uint8_t *image, uint32_t record) {
    image[record + ENTITY_TYPE] = EXPLOSION_PART_TYPE;
    wr32(image + record + ENTITY_SPRITE, A_mothership_explosion_sprite);
    wr16(image + record + ENTITY_X,
         (uint16_t)(be16(image + record + ENTITY_X) & EXPLOSION_X_ALIGN));
    image[record + ENTITY_ALIVE] = ENTITY_ALIVE_EXPLODING;
}

void mothership_segment_hit(uint8_t *image, uint32_t segment) {
    uint16_t index = (uint16_t)((segment - A_entity_table) / ENTITY_STRIDE);
    uint16_t pair = (uint16_t)(((uint16_t)(index - 1) & PAIR_INDEX_ALIGN) + 1);
    uint16_t parent_index = (uint16_t)sign_ext8((uint8_t)pair);
    uint32_t energy_at = addr_add(A_enemy_pair_hitpoints, sign_ext16(parent_index));
    uint32_t parent = entity_record(parent_index);   /* include/collision.h — one home for the
                                                      * index -> record multiply */

    image[energy_at]--;
    if (image[energy_at] != 0)
        return;

    /* The two halves are rewritten field by field in the original, interleaved; the order does not
     * reach the diff because no field is written twice. */
    segment_to_explosion(image, parent);
    segment_to_explosion(image, addr_add(parent, ENTITY_STRIDE));
    score_add_bcd(image, A_score_value_segment);
}

/* Register map: A1 = the hit record, either half of the pair. D5 carries the folded index and A5/A6
 * the two addresses it resolves to; A0 and A1 are saved across the score call. No outputs but
 * memory. */
void g_mothership_segment_hit(uint8_t *image, uint32_t segment) {
    mothership_segment_hit(image, segment);
}
