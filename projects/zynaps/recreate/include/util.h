/* util.h — the game's small shared arithmetic and block-move leaves (src/util.c). Subsystem: util.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 */
#ifndef ZYNAPS_UTIL_H
#define ZYNAPS_UTIL_H

#include <stdint.h>

/* 68000 `swap Dn` — exchange a register's halves — is `rol.l #16`, so machine.h's `rotate_left32`
 * IS the instruction and this is its count. It lives in this subsystem's header, and callers
 * elsewhere include it, because two subsystems transcribe the same instruction (`sin_quadrant_scaled`
 * here and `timer_b_raster_isr`'s colour swap in src/irq.c) and a second spelling of it is a second
 * thing to keep right. */
#define REGISTER_SWAP_BITS 16u

/* ---- tables these routines index -------------------------------------------------------------
 *
 * Both are read-only data inside the text segment. `A_sine_table_q1` is names.txt's own name;
 * `A_cos_table_64` is its `# ctx` alias for 0x18efc — names.txt's primary spelling there is
 * `sine_table`, and its comment on 0x142d4 reads the same 64 words as a COSINE table. The alias is
 * used here because the one routine that indexes it is entity_set_velocity_from_angle, whose x
 * component comes straight out of entry [angle]; a later body read may overturn that.
 */
#define A_sine_table_q1 0x18e46u  /* 91 words: sin(0..90 deg) * 0xffff, first quadrant */
#define A_cos_table_64  0x18efcu  /* # ctx — 64 words, amplitude +/-0x100, indexed by a 6-bit angle */

/* The first quadrant's table is 91 entries, so it holds 0..90 degrees INCLUSIVE. Every fold in
 * sin_scaled lands in that closed range, which is why the boundary is `<=` in all three places. */
#define SIN_DEGREES_QUADRANT 90
#define SIN_DEGREES_HALF     180
#define SIN_DEGREES_THREE_QUARTERS 270
#define SIN_DEGREES_FULL     360

/* ---- the entity record's ACCELERATION pair --------------------------------------------------
 *
 * NOT in include/entity.h, and that is a GAP IN THE FREEZE rather than a decision made here.
 * entity.h justifies being frozen on the premise that "the naming pass recovered the whole record
 * from full-body reads"; offsets 0x16 and 0x18 are live fields it does not name, so the premise is
 * not quite true and `entity_apply_accel` — a `util` routine — has nowhere else to put them.
 *
 * THIS IS A HOLDING PLACE, NOT THE RIGHT HOME. The record should be described by one file, and the
 * fix belongs to whoever owns entity.h: add both with a `pinned by test_util.py` tag, and give the
 * freeze rule in README.md an explicit escape hatch (a field the naming pass missed is added by
 * whoever pins it). While these live here, a subsystem that meets the same fields under a different
 * name — `ENTITY_ACCEL_X`, say — gets a silent second home, because test_constants.py's duplicate
 * check compares NAMES. names.txt's comment on 0x143f8 ("Applies ax/ay to vx/vy per the direction
 * bits in d1.b") is the provenance. src/util.c carries a second correction entity.h needs: its
 * `ENTITY_X`/`ENTITY_Y` tags read `.w signed`, but both fields are 32-bit.
 */

/* Which bit of D1 picks which adjustment, in entity_apply_accel. The pairs are exclusive and
 * tested in this order, so bit 3 wins over bit 4 and bit 5 over bit 6. */
#define ACCEL_BIT_X_ADD 3
#define ACCEL_BIT_X_SUB 4
#define ACCEL_BIT_Y_ADD 5
#define ACCEL_BIT_Y_SUB 6

/* ---- prototypes ----------------------------------------------------------------------------- */
unsigned copy_block_words(uint8_t *image, uint32_t src, uint32_t dst, uint32_t byte_count);
uint32_t sin_quadrant_scaled(const uint8_t *image, uint16_t angle, uint16_t amplitude);
uint32_t sin_scaled(const uint8_t *image, uint16_t angle, uint16_t amplitude);
uint32_t cos_scaled(const uint8_t *image, uint16_t angle, uint16_t amplitude);
uint16_t angle_to_target(const uint8_t *image, uint32_t self, uint32_t target);
void entity_set_velocity_from_angle(uint8_t *image, uint32_t entity, uint32_t angle, int16_t speed);
void entity_apply_velocity(uint8_t *image, uint32_t entity);
void entity_apply_accel(uint8_t *image, uint32_t entity, uint8_t direction_bits);

#endif /* ZYNAPS_UTIL_H */
