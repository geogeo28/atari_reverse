/* collision.h — the per-frame overlap bookkeeping and the type-class tests in src/collision.c.
 * Subsystem: collision.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 */
#ifndef ZYNAPS_COLLISION_H
#define ZYNAPS_COLLISION_H

#include <stdint.h>

/* ================================================================================================
 * The tables this subsystem owns (../out/globals.tsv).
 * ============================================================================================= */
/* 21 longs, one row per entity index: bit j of row i is set while entity i's box overlaps
 * entity j this frame. Built by `frame_draw_objects_and_collide` @ 0x11c00, which clears the whole
 * table and then calls `object_pair_overlap_mark` once per ordered pair. */
#define A_entity_collision_masks 0x18252u
/* 21 longs, entry i = (1 << i) - 1: the bits of every index BELOW i. Masking a collision row with
 * it is what makes `collision_chain_walk` descend strictly and therefore terminate. */
#define A_lower_index_masks 0x19ddau
/* The 56-bit big-endian bit table of entity types that react to a landscape pixel hit. */
#define A_type_hits_terrain_bits 0x19196u
/* ...and of the types that kill the ship on contact. */
#define A_type_lethal_to_ship_bits 0x191a4u

/* ================================================================================================
 * Shared shapes.
 * ============================================================================================= */
/* Entity field 8 carries the sprite's row count in its low 15 bits; bit 15 is a flag the weapon
 * code owns (see include/weapon.h). Every reader of the row count masks it off. */
#define ENTITY_HEIGHT_MASK 0x7fffu

/* The last type the three TARGETING tables describe. Spelt as 0x31 because that is what the shared
 * bound below compares against; the instruction is `cmp.b #$32,dn` + `blt`, and 0x32 is where the
 * PLAYER's own entities start — 0x32 missile, 0x33 bomb, 0x35 drone, 0x36 seeker, 0x37 hit flash —
 * none of which those three tables describe. */
#define TYPE_TARGETABLE_MAX 0x31
/* `cmp.b #$37,d2` + `ble` in object_type_is_collidable: the last type the terrain table describes.
 * WIDER than the bound above, and deliberately: a player shot does react to the landscape. */
#define TYPE_TERRAIN_SENSITIVE_MAX 0x37

/* ================================================================================================
 * Prototypes.
 * ============================================================================================= */
/* The four type-class tests (0x12dc6, 0x13d3e, 0x13d6e, 0x140f6) are ONE routine four times over:
 * read the record's type byte as SIGNED, refuse it if it is past the last type the table describes,
 * and otherwise probe that table's bit for it. `table` and `last_type` are the whole difference.
 *
 * It lives here rather than beside the record it reads because include/entity.h is frozen; the two
 * weapon-owned tests reach it by including this header, which README.md's "Adding a function"
 * allows. If entity.h ever opens, this belongs there. */
int entity_type_in_class(const uint8_t *image, uint32_t entity, uint32_t table, int8_t last_type);

/* Glue-side, and shared with src/weapon.c: record a routine's Z-flag answer where the image diff
 * can see it, in the encoding test/abi.py's `seq` stub uses. `seq` stores 0xff when Z was SET at
 * the rts, and every routine these serve says "yes" by CLEARING Z — so a "yes" is 0x00. The pair is
 * here rather than file-static in src/collision.c so that src/weapon.c's glue can see the contract
 * it calls across the subsystem boundary. */
#define SCC_ANSWER_YES 0x00u
#define SCC_ANSWER_NO 0xffu

void store_z_flag_answer(uint8_t *image, uint32_t result, int answer_is_yes);
/* Where g_collision_chain_walk's stub stores D7: the flag byte, one pad byte for alignment, then
 * the longword — the layout of `seq (a0)+ / addq.l #1,a0 / move.l d7,(a0)+`. */
#define CHAIN_WALK_D7_OFFSET 2u

int object_type_is_collidable(const uint8_t *image, uint32_t object);
int entity_type_is_lethal(const uint8_t *image, uint32_t entity);
int collision_chain_walk(const uint8_t *image, uint16_t index);
void object_pair_overlap_mark(uint8_t *image, uint32_t left, uint32_t right,
                              uint32_t left_row, uint32_t right_row,
                              uint32_t left_index, uint32_t right_index);

#endif /* ZYNAPS_COLLISION_H */
