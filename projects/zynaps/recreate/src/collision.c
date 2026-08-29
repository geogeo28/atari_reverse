/* collision.c — the type-class bit tables, the all-pairs overlap marker, and the chain walk that
 * decides whether a pixel hit was the landscape.
 *
 * The frame stage above these (`frame_draw_objects_and_collide` @ 0x11c00) draws all 20 entity
 * slots, which is what sets each record's ENTITY_PIXEL_HIT, and then builds the 21-row overlap
 * table at A_entity_collision_masks by calling `object_pair_overlap_mark` once per ordered pair.
 * `collision_chain_walk` is the consumer: a set pixel-hit flag means the sprite overlapped
 * background pixels, and the walk decides whether another, lower-indexed entity explains that
 * overlap — if none does, the entity hit the terrain.
 */
#include "machine.h"
#include "entity.h"
#include "collision.h"
#include "player.h"

/* ================================================================================================
 * The type-class bit tables.
 *
 * Each table is a big-endian bit array indexed by the entity's type byte, MSB first: type t lives
 * in word t>>4, at bit 15-(t&15). The four routines that read one differ ONLY in which table and
 * which range bound they use, so they are one shared body with two arguments. Their answer is the
 * 68000's Z flag (clear = the type is in the class), which is why each is `int` here and why the
 * battery captures the flag through a stub rather than looking for a memory write. Their scratch
 * data registers are clobber, not answers — ../../names.txt says so per routine.
 * ============================================================================================= */
#define TYPE_CLASS_WORD_SHIFT 3   /* `lsr.w #3` — three of the four index bits, before the mask */
#define TYPE_CLASS_WORD_MASK 0xfffeu  /* `and.w #$fffe` — round the byte offset down to a word */
#define TYPE_CLASS_BIT_MASK 0xfu      /* `not.w` + `and.w #$f` — bit 15-(t&15), counted from the LSB */

int entity_type_in_class(const uint8_t *image, uint32_t entity, uint32_t table, int8_t last_type) {
    int8_t type = (int8_t)image[entity + ENTITY_TYPE];   /* `move.b 17(an),dn`, read SIGNED */

    if (type > last_type)
        return 0;

    uint16_t index = (uint16_t)(int16_t)type;                       /* `ext.w` */
    uint32_t word = addr_add(table, (index >> TYPE_CLASS_WORD_SHIFT) & TYPE_CLASS_WORD_MASK);
    unsigned bit = (unsigned)~index & TYPE_CLASS_BIT_MASK;

    return (be16(image + word) >> bit) & 1u;
}

/* object_type_is_collidable @ 0x12dc6 — a0 = the record. Does this type react to the landscape? */
int object_type_is_collidable(const uint8_t *image, uint32_t object) {
    return entity_type_in_class(image, object, A_type_hits_terrain_bits,
                                TYPE_TERRAIN_SENSITIVE_MAX);
}

/* entity_type_is_lethal @ 0x13d6e — a4 = the record. Does touching this entity kill the ship? */
int entity_type_is_lethal(const uint8_t *image, uint32_t entity) {
    return entity_type_in_class(image, entity, A_type_lethal_to_ship_bits, TYPE_TARGETABLE_MAX);
}

/* ================================================================================================
 * Turning an entity INDEX into an address — the two computations every consumer of the collision
 * tables makes. Both are exported (include/collision.h) rather than file-static, because
 * `bomb_update` in src/weapon.c makes exactly the same two and a second spelling of either would be
 * a copy that can silently diverge from the instruction each one transcribes.
 * ============================================================================================= */
uint32_t entity_record(uint16_t index) {
    /* `mulu.w #$2c,d0` + `adda.l d0,a0`: a 16x16 unsigned multiply, so a big index stays in range. */
    return addr_add(A_entity_table, (uint32_t)index * ENTITY_STRIDE);
}

/* Both row pointers are built as `lea table,an` + `adda.w`, which SIGN-EXTENDS the word offset. */
uint32_t collision_table_row(uint32_t table, uint16_t index) {
    return addr_add(table, sign_ext16((uint16_t)(index * COLLISION_ROW_BYTES)));
}

/* ================================================================================================
 * collision_chain_walk @ 0x12d44 — d0 = an entity index, d7 = the answer (1 = it hit the terrain).
 *
 * The blitter flags a pixel hit whenever a sprite landed on non-background pixels, and it cannot
 * tell the landscape from another sprite. This walk resolves that: follow the entity's overlap row
 * down to the LOWEST-indexed entity it overlaps, and repeat. If every link in that chain also has
 * its pixel-hit flag set, the overlaps explain themselves and the answer is 1; if any link is clear
 * — or the entity's own type is not terrain-sensitive — the answer is 0.
 * ============================================================================================= */

/* `clr.w d4` then `btst d4,d0` / `addq.w #1,d4` until a bit answers. `bits` is never 0 here — the
 * caller returns first — which matters, because `btst` on a data register counts modulo 32 and an
 * all-zero word would spin. */
static unsigned lowest_set_bit(uint32_t bits) {
    unsigned bit = 0;

    while (!(bits & (1u << bit)))
        bit++;
    return bit;
}

int collision_chain_walk(const uint8_t *image, uint16_t index) {
    uint32_t record = entity_record(index);

    if (image[record + ENTITY_PIXEL_HIT] == 0 || !object_type_is_collidable(image, record))
        return 0;

    for (;;) {
        /* The entity's overlaps, restricted to indices below its own — 0x12d9a, the loop head the
         * original re-enters at 0x12d78, which repeats the pixel-hit test but not the type test. */
        uint32_t overlaps = be32(image + collision_table_row(A_entity_collision_masks, index))
                          & be32(image + collision_table_row(A_lower_index_masks, index));

        if (overlaps == 0)
            return 1;
        index = (uint16_t)lowest_set_bit(overlaps);
        if (image[entity_record(index) + ENTITY_PIXEL_HIT] == 0)
            return 0;
    }
}

/* ================================================================================================
 * object_pair_overlap_mark @ 0x11cce — the all-pairs box test.
 *
 * Registers: a2/a1 = the two records, a3/a4 = their rows in A_entity_collision_masks, a5/a6 = their
 * indices. Every box is OBJECT_BOX_WIDTH wide and the record's own row count tall, and all four
 * comparisons are signed word `blt`s, so a box touching another edge to edge does not overlap. On a
 * hit the mark is reciprocal: bit j goes into row i and bit i into row j.
 * ============================================================================================= */
#define OBJECT_BOX_WIDTH 0x10  /* `add.w #$10,d3` — every entity's box is 16 pixels wide */
#define COLLISION_ROW_BITS 32u /* `bset dn,dm` on a data register counts modulo the long's width */

/* Both edges are `add.w` sums read back by a SIGNED `blt`, so the truncation to 16 bits happens
 * before the comparison and a box near the word's top edge really does end up "above" its own top. */
static int16_t box_bottom(const uint8_t *image, uint32_t record) {
    uint16_t rows = be16(image + record + ENTITY_HEIGHT) & ENTITY_HEIGHT_MASK;

    return (int16_t)(uint16_t)(be16(image + record + ENTITY_Y) + rows);
}

static int16_t box_right(const uint8_t *image, uint32_t record) {
    return (int16_t)(uint16_t)(be16(image + record + ENTITY_X) + OBJECT_BOX_WIDTH);
}

/* BOTH ROWS ARE READ BEFORE EITHER IS STORED — `move.l (a3),d3 / move.l (a4),d4 / bset / bset /
 * move.l d3,(a3) / move.l d4,(a4)`. That is not the same program as two read-modify-writes: when
 * the two row pointers name the SAME longword, the second store discards the first `bset`, so one
 * bit survives rather than two. The game's own builder always passes distinct rows, but the
 * pointers are arguments and the ordering is what the instructions do. */
static void mark_overlap_pair(uint8_t *image, uint32_t left_row, uint32_t right_row,
                              uint32_t left_index, uint32_t right_index) {
    uint32_t left_bits = be32(image + left_row);
    uint32_t right_bits = be32(image + right_row);

    left_bits |= 1u << (right_index % COLLISION_ROW_BITS);
    right_bits |= 1u << (left_index % COLLISION_ROW_BITS);
    wr32(image + left_row, left_bits);
    wr32(image + right_row, right_bits);
}

void object_pair_overlap_mark(uint8_t *image, uint32_t left, uint32_t right,
                              uint32_t left_row, uint32_t right_row,
                              uint32_t left_index, uint32_t right_index) {
    int16_t left_x = (int16_t)be16(image + left + ENTITY_X);
    int16_t left_y = (int16_t)be16(image + left + ENTITY_Y);
    int16_t right_x = (int16_t)be16(image + right + ENTITY_X);
    int16_t right_y = (int16_t)be16(image + right + ENTITY_Y);

    if (right_y >= box_bottom(image, left) || left_x >= box_right(image, right)
        || right_x >= box_right(image, left) || left_y >= box_bottom(image, right))
        return;

    mark_overlap_pair(image, left_row, right_row, left_index, right_index);
}

/* ================================================================================================
 * Glue. Each `g_*` unpacks the routine's register contract and stores whatever the image diff
 * cannot otherwise see at `result` — see test/abi.py.
 * ============================================================================================= */
/* Every routine here and the two in weapon.c answers in the 68000's Z FLAG and writes no memory of
 * its own, so the batteries enter through a stub that turns the flag into a byte with `seq` (see
 * test/abi.py). This is the reconstruction's half of that. The polarity is uniform across all five:
 * each says "yes" by CLEARING Z (a `btst` on a set bit, or `moveq #1`), so the inversion happens
 * here once. The two encoding constants are in collision.h, beside the prototype, so weapon.c can
 * see the contract it is calling rather than inferring it. */
void store_z_flag_answer(uint8_t *image, uint32_t result, int answer_is_yes) {
    image[result] = answer_is_yes ? SCC_ANSWER_YES : SCC_ANSWER_NO;
}

/* Register map: A0 = the record; answer in Z (set = not collidable). */
void g_object_type_is_collidable(uint8_t *image, uint32_t result, uint32_t object) {
    store_z_flag_answer(image, result, object_type_is_collidable(image, object));
}

/* Register map: A4 = the record; answer in Z (set = harmless). */
void g_entity_type_is_lethal(uint8_t *image, uint32_t result, uint32_t entity) {
    store_z_flag_answer(image, result, entity_type_is_lethal(image, entity));
}

/* Register map: D0.w in = the entity index; D7 out = the answer, and Z mirrors it (`moveq` sets the
 * flags). The stub records both, so a reconstruction that got them out of step would fail. Note the
 * sense is the same as the class tests': Z is set when the walk answers 0. */
void g_collision_chain_walk(uint8_t *image, uint32_t result, uint32_t index) {
    int hit_terrain = collision_chain_walk(image, (uint16_t)index);

    store_z_flag_answer(image, result, hit_terrain);
    wr32(image + result + CHAIN_WALK_D7_OFFSET, (uint32_t)hit_terrain);
}

/* Register map: A2/A1 = the two records, A3/A4 = their mask rows, A5/A6 = their indices. */
void g_object_pair_overlap_mark(uint8_t *image, uint32_t left, uint32_t right,
                                uint32_t left_row, uint32_t right_row,
                                uint32_t left_index, uint32_t right_index) {
    object_pair_overlap_mark(image, left, right, left_row, right_row, left_index, right_index);
}
