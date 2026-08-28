/* util.c — the small shared leaves: a word block copy, the scaled sine, and the four entity
 * arithmetic helpers the enemy update runs every frame.
 *
 * None of them touches hardware or issues a trap; each runs to `rts` on a staged image.
 */
#include "machine.h"
#include "entity.h"
#include "util.h"

/* ================================================================================================
 * copy_block_words @ 0x13858 — `lsr.l #1,d2 / sub.l #$1,d2 / move.w (a0)+,(a1)+ / dbf d2`
 * ============================================================================================= */

#define COPY_WORD_BYTES 2u

/* Copy `byte_count >> 1` words from `src` to `dst` and return how many words that was.
 *
 * THE COUNT IS A `dbf` ON A LONGWORD REGISTER, which is two facts, not one. The halving and the
 * decrement are 32-bit (`lsr.l`, `sub.l`), but `dbf` counts the LOW WORD alone — so a byte count
 * whose half exceeds 0xffff copies only its low word's worth of words, and a half of exactly 0
 * copies 0x10000 of them rather than none. `loop_passes` is that idiom (see machine.h); the
 * caller's job is to hand it the count the register stands for.
 */
unsigned copy_block_words(uint8_t *image, uint32_t src, uint32_t dst, uint32_t byte_count) {
    unsigned words = loop_passes(byte_count >> 1, COUNT_MASK_WORD);

    for (unsigned i = 0; i < words; i++) {
        wr16(image + dst, be16(image + src));
        src = addr_add(src, COPY_WORD_BYTES);
        dst = addr_add(dst, COPY_WORD_BYTES);
    }
    return words;
}

/* Register map: A0 = source, A1 = destination, D2 = the byte count. Both pointers come back one
 * past the last word copied and D2 comes back as the exhausted loop counter, so the stub dumps
 * D2/A0/A1 at `result` (movem order — see test/abi.py).
 *
 * D2's FINAL VALUE IS NOT ZERO AND NOT THE COUNT. `dbf` leaves the low word at -1 and never borrows
 * into the high one, so what comes back is the high half of `(byte_count >> 1) - 1` over an
 * all-ones low word. Storing it is what separates `lsr.l`/`sub.l` from their word-sized twins,
 * which the copied bytes alone cannot: for every count the game passes, the two agree on the words
 * and disagree only here. */
void g_copy_block_words(uint8_t *image, uint32_t src, uint32_t dst, uint32_t byte_count,
                        uint32_t result) {
    unsigned words = copy_block_words(image, src, dst, byte_count);
    uint32_t counter_high_half = ((byte_count >> 1) - 1u) & ~COUNT_MASK_WORD;

    wr32(image + result,     counter_high_half | COUNT_MASK_WORD);
    wr32(image + result + 4, addr_add(src, words * COPY_WORD_BYTES));
    wr32(image + result + 8, addr_add(dst, words * COPY_WORD_BYTES));
}

/* ================================================================================================
 * The scaled sine — sin_quadrant_scaled @ 0x15694, sin_scaled @ 0x15654, cos_scaled @ 0x15644
 * ============================================================================================= */

/* `angle` is the first-quadrant degree count, 0..90; the caller has already folded it. The table
 * index is `angle * 2` computed as a WORD (`lsl.w #1,d0`) and then sign-extended by the `d0.w`
 * index register, so an angle at or above 0x4000 indexes BELOW the table — faithful, and the
 * reason test_util.py stops the fuzz short of it (see FUZZ_MAX_ANGLE there).
 *
 * The table word is read UNSIGNED (`and.l #$ffff,d0` before `mulu.w`), so the quarter-wave runs
 * 0x0000..0xffff and the product is an unsigned 32-bit one.
 *
 * THE ANSWER IS A `swap`, NOT A SHIFT. The routine multiplies the table's 16-bit sine by the
 * amplitude into a 32-bit product and then swaps D0's halves, so the caller reads the high half of
 * the product in D0's LOW word — and the product's low half comes back in the high word rather
 * than being discarded. `>> 16` would agree on the low word and differ on the high one, which is
 * exactly what the differential compares. A 68000 `swap` is `rol.l #16`, which is what machine.h's
 * rotate is, so it is spelt as that rather than as a private helper. */
uint32_t sin_quadrant_scaled(const uint8_t *image, uint16_t angle, uint16_t amplitude) {
    uint32_t entry = addr_add(A_sine_table_q1, sign_ext16((uint16_t)(angle * 2u)));

    return rotate_left32((uint32_t)be16(image + entry) * amplitude, REGISTER_SWAP_BITS);
}

/* `neg.w d0` negates the low word only and leaves the high one — which for this routine means the
 * product's low half survives the negation unchanged in D0's high word. */
static uint32_t negate_low_word(uint32_t value) {
    return set_low_word(value, (uint16_t)-(uint16_t)value);
}

/* Fold a 0..359 degree angle onto the first quadrant and scale it. All four comparisons are SIGNED
 * word compares, so a negative angle takes the first arm and indexes below the table exactly as
 * `sin_quadrant_scaled`'s note describes. */
uint32_t sin_scaled(const uint8_t *image, uint16_t angle, uint16_t amplitude) {
    int16_t degrees = (int16_t)angle;

    if (degrees <= SIN_DEGREES_QUADRANT)
        return sin_quadrant_scaled(image, angle, amplitude);
    if (degrees <= SIN_DEGREES_HALF)
        return sin_quadrant_scaled(image, (uint16_t)(SIN_DEGREES_HALF - angle), amplitude);
    if (degrees <= SIN_DEGREES_THREE_QUARTERS)
        return negate_low_word(
            sin_quadrant_scaled(image, (uint16_t)(angle - SIN_DEGREES_HALF), amplitude));
    return negate_low_word(sin_quadrant_scaled(
        image, (uint16_t)(SIN_DEGREES_HALF - (uint16_t)(angle - SIN_DEGREES_HALF)), amplitude));
}

/* cos(x) = sin(x + 90), with the sum brought back under a full turn. The wrap test is `blt`, a
 * SIGNED compare against 360, so it is the sum's signedness and not its magnitude that decides —
 * and it subtracts at most once, which is all a 0..359 argument can need. names.txt reports no
 * caller for this entry; it is here because it falls straight into sin_scaled below it and a
 * reconstruction that stopped at the fall-through boundary would leave a live entry point out. */
uint32_t cos_scaled(const uint8_t *image, uint16_t angle, uint16_t amplitude) {
    uint16_t shifted = (uint16_t)(angle + SIN_DEGREES_QUADRANT);

    if ((int16_t)shifted >= SIN_DEGREES_FULL)
        shifted = (uint16_t)(shifted - SIN_DEGREES_FULL);
    return sin_scaled(image, shifted, amplitude);
}

/* Register map: D0 = the angle in degrees, D2 = the amplitude, A0 = scratch (the table). The answer
 * is D0 alone and no memory is written, so the stub dumps D0 at `result` — see test/abi.py.
 *
 * D0's HIGH WORD ON ENTRY CANNOT MATTER and the glue's `uint16_t` says so: every step from the fold
 * to `lsl.w #1` is a word operation, and `and.l #$ffff,d0` clears whatever survived before the
 * multiply. D2's high word is likewise unread — `mulu.w` takes the low word. */
void g_sin_scaled(uint8_t *image, uint32_t angle_reg, uint32_t amplitude_reg, uint32_t result) {
    wr32(image + result, sin_scaled(image, (uint16_t)angle_reg, (uint16_t)amplitude_reg));
}

void g_cos_scaled(uint8_t *image, uint32_t angle_reg, uint32_t amplitude_reg, uint32_t result) {
    wr32(image + result, cos_scaled(image, (uint16_t)angle_reg, (uint16_t)amplitude_reg));
}

void g_sin_quadrant_scaled(uint8_t *image, uint32_t angle_reg, uint32_t amplitude_reg,
                           uint32_t result) {
    wr32(image + result, sin_quadrant_scaled(image, (uint16_t)angle_reg, (uint16_t)amplitude_reg));
}

/* ================================================================================================
 * angle_to_target @ 0x1424c — a 6-bit direction from one entity towards another
 * ============================================================================================= */

/* The position words are read at CELL resolution: `lsr.w #3` divides by 8 (logically, so a negative
 * coordinate reads as a large positive one), and the target's bit 2 — the half-cell — rounds its
 * cell up. Only the target is rounded; the source is not. */
#define COORD_CELL_SHIFT     3
#define COORD_HALF_CELL_BIT  (1u << 2)

/* The octant flags D3 accumulates, and the sub-step search's start. Each flag is the reflection
 * that brought the vector into the first octant, applied to the answer by `eor` at the end:
 * 0x3f flips the whole 6-bit circle for a negative y, 0x1f the half for a negative x, and 0x0f the
 * octant for the x/y swap. The first is a MOVE rather than an eor in the original — D3 is cleared
 * just above it, so the two agree, and it is written as an assignment here for the same reason. */
#define ANGLE_FLAG_Y_NEGATIVE 0x3fu
#define ANGLE_FLAG_X_NEGATIVE 0x1fu
#define ANGLE_FLAG_SWAPPED    0x0fu
#define ANGLE_OCTANT_STEPS    8      /* `move.w #$8,d4` — the search counts down from here */

static uint16_t target_cell_delta(const uint8_t *image, uint32_t self, uint32_t target,
                                  unsigned field) {
    uint16_t here = (uint16_t)(be16(image + self + field) >> COORD_CELL_SHIFT);
    uint16_t there_raw = be16(image + target + field);
    uint16_t there = (uint16_t)(there_raw >> COORD_CELL_SHIFT);

    if (there_raw & COORD_HALF_CELL_BIT)
        there = (uint16_t)(there + 1);
    return (uint16_t)(there - here);
}

/* The slope search: how many eighths of the octant the vector has turned through.
 *
 * `across` is the longer leg and `up` the shorter, both already non-negative. The loop counts D4
 * down from 8 and stops at the first D4 with `across * D4 < up * 8`, or at 0 if there is none — so
 * a vector on the octant's DIAGONAL gives 7 (the first pass already satisfies it) and one along the
 * AXIS gives 0 (no pass ever does, since `up * 8` is then zero). Both are driven by test_util.py's
 * ring.
 *
 * Both legs are multiplied as WORDS and compared SIGNED, so a leg AT 0x1000 already makes
 * `leg * 8` read negative and the answer wraps rather than saturating; that is the instruction and
 * it is left as it is. No pair of playfield coordinates gets near it. */
static uint16_t octant_substep(uint16_t across, uint16_t up) {
    uint16_t steps = ANGLE_OCTANT_STEPS;
    uint16_t limit = (uint16_t)(up * ANGLE_OCTANT_STEPS);
    uint16_t slope = (uint16_t)(across * ANGLE_OCTANT_STEPS);

    for (;;) {
        steps = (uint16_t)(steps - 1);
        if (steps == 0)
            return 0;
        slope = (uint16_t)(slope - across);
        if ((int16_t)slope < (int16_t)limit)
            return steps;
    }
}

/* The 6-bit (0..0x3f) direction from entity `self` towards entity `target`. */
uint16_t angle_to_target(const uint8_t *image, uint32_t self, uint32_t target) {
    uint16_t across = target_cell_delta(image, self, target, ENTITY_X);
    uint16_t up = target_cell_delta(image, self, target, ENTITY_Y);
    uint8_t flags = 0;

    if ((int16_t)up < 0) {
        up = (uint16_t)-up;
        flags = ANGLE_FLAG_Y_NEGATIVE;
    }
    if ((int16_t)across < 0) {
        across = (uint16_t)-across;
        flags ^= ANGLE_FLAG_X_NEGATIVE;
    }
    if ((int16_t)across < (int16_t)up) {
        uint16_t swapped = across;

        across = up;
        up = swapped;
        flags ^= ANGLE_FLAG_SWAPPED;
    }
    return (uint16_t)(octant_substep(across, up) ^ flags);
}

/* Register map: A2 = the entity asking, A1 = the entity aimed at; the answer is D0's low word, over
 * the caller's own high word (`move.w d4,d0`). D1..D5 come back as scratch — the one caller, at
 * 0x141ec, reloads every one of them — so the stub dumps D0 alone. */
void g_angle_to_target(uint8_t *image, uint32_t self, uint32_t target, uint32_t d0_reg,
                       uint32_t result) {
    wr32(image + result, set_low_word(d0_reg, angle_to_target(image, self, target)));
}

/* ================================================================================================
 * The per-frame entity motion — 0x142d4, 0x14306, 0x143f8
 * ============================================================================================= */

#define VELOCITY_TABLE_ENTRY_BYTES 2u
/* The y component reads the same cosine table a quarter-turn back: `sub.w #$10,d3 / and.w #$3f,d3`
 * on a 64-entry circle is cos(angle - 90 deg) = sin(angle). */
#define VELOCITY_QUARTER_TURN 0x10u
#define VELOCITY_ANGLE_MASK   0x3fu
/* ...but the X component's own index is masked to a BYTE, not to the circle (`and.l #$ff,d0`), so
 * an angle above 0x3f indexes past the 64-word table into whatever follows it. Faithful; the game
 * passes 0..0x3f (names.txt on 0x142d4). */
#define VELOCITY_ANGLE_BYTE_MASK 0xffu

static int16_t velocity_component(const uint8_t *image, uint16_t table_index, int16_t speed) {
    uint32_t entry = addr_add(A_cos_table_64,
                              sign_ext16((uint16_t)(table_index * VELOCITY_TABLE_ENTRY_BYTES)));

    /* `muls.w` is a SIGNED 16x16 multiply and `move.w d0,18(a2)` keeps its low word. */
    return (int16_t)((int16_t)be16(image + entry) * speed);
}

void entity_set_velocity_from_angle(uint8_t *image, uint32_t entity, uint32_t angle,
                                    int16_t speed) {
    uint16_t across = (uint16_t)(angle & VELOCITY_ANGLE_BYTE_MASK);
    uint16_t up = (uint16_t)((across - VELOCITY_QUARTER_TURN) & VELOCITY_ANGLE_MASK);

    wr16(image + entity + ENTITY_DX, (uint16_t)velocity_component(image, across, speed));
    wr16(image + entity + ENTITY_DY, (uint16_t)velocity_component(image, up, speed));
}

/* Register map: A2 = the entity, D0.b = the angle, D1.b = the SIGNED speed (`ext.w d1` before the
 * multiply). D0 and D3 come back as scratch; the outputs are the two record fields. */
void g_entity_set_velocity_from_angle(uint8_t *image, uint32_t entity, uint32_t angle_reg,
                                      uint32_t speed_reg) {
    entity_set_velocity_from_angle(image, entity, angle_reg,
                                   (int16_t)(uint16_t)sign_ext8(speed_reg));
}

/* The position is 32-bit fixed point with 8 fractional bits, and the velocity is the whole-pixel
 * word: `ext.l` then `lsl.l #8` turns the signed velocity into that fixed-point delta.
 *
 * NOTE FOR include/entity.h, WHICH IS FROZEN: its `ENTITY_X`/`ENTITY_Y` are tagged ".w signed",
 * but the field each names is the HIGH WORD of a 32-bit quantity — this routine adds a longword at
 * both offsets, which is also why ENTITY_Y is four bytes past ENTITY_X rather than two. The two
 * readings agree wherever only the integer part is wanted (entity_kill_if_offscreen's box test), so
 * nothing is wrong today; the tag is narrower than the field. */
void entity_apply_velocity(uint8_t *image, uint32_t entity) {
    int32_t dx = (int16_t)be16(image + entity + ENTITY_DX);
    int32_t dy = (int16_t)be16(image + entity + ENTITY_DY);

    wr32(image + entity + ENTITY_X, be32(image + entity + ENTITY_X) + ((uint32_t)dx << 8));
    wr32(image + entity + ENTITY_Y, be32(image + entity + ENTITY_Y) + ((uint32_t)dy << 8));
}

void g_entity_apply_velocity(uint8_t *image, uint32_t entity) {
    entity_apply_velocity(image, entity);
}

/* One axis of the acceleration step. The two direction bits are exclusive and tested in order, and
 * — this is the part a paraphrase loses — the field is STORED ONLY IF ONE OF THEM IS SET: with
 * neither bit the original branches past its own `move.w d2,18(a2)`, so a record whose velocity
 * word holds something the routine never computed keeps it. */
static void accelerate_axis(uint8_t *image, uint32_t entity, unsigned velocity_field,
                            unsigned accel_field, uint8_t direction_bits, unsigned add_bit,
                            unsigned sub_bit) {
    uint16_t velocity = be16(image + entity + velocity_field);
    uint16_t accel = be16(image + entity + accel_field);

    if (direction_bits & (1u << add_bit))
        velocity = (uint16_t)(velocity + accel);
    else if (direction_bits & (1u << sub_bit))
        velocity = (uint16_t)(velocity - accel);
    else
        return;
    wr16(image + entity + velocity_field, velocity);
}

void entity_apply_accel(uint8_t *image, uint32_t entity, uint8_t direction_bits) {
    accelerate_axis(image, entity, ENTITY_DX, ENTITY_AX, direction_bits,
                    ACCEL_BIT_X_ADD, ACCEL_BIT_X_SUB);
    accelerate_axis(image, entity, ENTITY_DY, ENTITY_AY, direction_bits,
                    ACCEL_BIT_Y_ADD, ACCEL_BIT_Y_SUB);
    entity_apply_velocity(image, entity);      /* the original's `bra.w $14306` tail call */
}

/* Register map: A2 = the entity, D1.b = the direction bits. The `btst`s are on a data register, so
 * they address D1's bits modulo 32 — but every bit used is inside the low byte, which is what
 * names.txt calls the argument, so the glue takes a byte. */
void g_entity_apply_accel(uint8_t *image, uint32_t entity, uint32_t direction_reg) {
    entity_apply_accel(image, entity, (uint8_t)direction_reg);
}
