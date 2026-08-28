/* enemy.c — the enemy subsystem: slot housekeeping, the per-type movers and animators, the script
 * VM's arithmetic opcodes, and the asteroid columns.
 *
 * Everything here works on the 0x2c-byte record include/entity.h describes; enemy.h adds the roles
 * the actor kinds give the record's union bytes, and the globals this subsystem owns.
 *
 * MANY OF THESE ROUTINES ANSWER IN THE CARRY FLAG rather than in memory, because the script VM at
 * 0x14c66 loops `jsr (a0)` / `bcs` — set means "run the next opcode in the same frame", clear means
 * "this actor is done until the next one". The cores return that flag as an `unsigned`; the glue
 * stores it as the byte an `Scc` would (enemy.h, SCC_BYTE_TRUE), which is how the image diff sees
 * an answer the 68000 keeps in a status bit.
 */
#include "machine.h"
#include "entity.h"
#include "enemy.h"

#define ENEMY_SLOT_COUNT 8      /* `move.w #$7,d7` + `dbf` over the records at A_enemy_slots */
#define GROUND_ACTOR_COUNT 6    /* `move.w #$5,d0` — the type-0x34 scenery at A_entity_table */
#define ASTEROID_GROUPS 6       /* `move.w #$5,d7` — the outer loop */
#define ASTEROID_COLUMNS 3      /* `move.w #$2,d6` — three records per group */
#define SPRITE_PTR_BYTES 4      /* every frame table here is an array of 32-bit sprite pointers */
#define SPRITE_PTR_SHIFT 2      /* ...and `lsl #2` is how each one turns a frame into a byte offset */


/* Playfield geometry. Here rather than in the header because no other translation unit uses it —
 * CLAUDE.md §5 puts a constant at the narrowest scope that covers its uses, and the header's job is
 * the addresses and record fields another subsystem may need to read. */
#define ACTOR_KEEP_Y_MIN  0x10  /* actor_clamp_y's floor, and where a risen diver is retired */
#define ACTOR_KEEP_Y_MAX  0xb0  /* ...its ceiling, and the asteroid columns' wrap point */
#define ACTOR_KILL_X      0x30  /* a type-17 enemy stops being alive left of this */

/* The two answers a routine can leave in the carry, named because `return 1` at the bottom of an
 * opcode handler says nothing about what the VM does with it. */
#define CARRY_SET 1u      /* `ori.b #$1,ccr` — "run the next opcode", or "no slot" */
#define CARRY_CLEAR 0u    /* `andi.b #$fe,ccr` */

/* What a glue writes where the test's `Scc` stub writes — see the header note above. */
static void store_flag(uint8_t *image, uint32_t flag_out, unsigned condition) {
    image[flag_out] = condition ? SCC_BYTE_TRUE : SCC_BYTE_FALSE;
}

/* `lea 44(a2),a2` — the step every loop over the record array makes. */
static uint32_t next_record(uint32_t record) {
    return addr_add(record, ENTITY_STRIDE);
}

/* `ext.w dN / lsl.w #2,dN` feeding a `dN.w` index: how a SIGNED byte — a frame, a sprite variant —
 * becomes the offset of a 32-bit pointer. Both extensions are live at the edges of the byte's
 * range, so neither is folded away: a byte of 0x80 or more reaches BELOW the table it indexes. */
static uint32_t sprite_ptr_offset(uint8_t entry) {
    return sign_ext16((uint16_t)(sign_ext8(entry) << SPRITE_PTR_SHIFT));
}

/* ================================================================================================
 * count_free_wave_slots @ 0x13828 — how many of the eight wave slots are unused.
 *
 * `tst.b 14(a0)` counts the records whose ALIVE byte is zero, so the answer is FREE slots, not live
 * ones. It publishes the count to A_free_wave_slot_count and leaves it in D0 as well; its one
 * caller, enemy_alloc_slot, branches on the register rather than re-reading the global.
 * ============================================================================================= */
uint8_t count_free_wave_slots(uint8_t *image) {
    uint8_t free_slots = 0;
    uint32_t record = A_enemy_slots;

    for (unsigned i = 0; i < ENEMY_SLOT_COUNT; i++) {
        if (image[record + ENTITY_ALIVE] == 0)
            free_slots++;
        record = next_record(record);
    }
    image[A_free_wave_slot_count] = free_slots;
    return free_slots;
}

/* Register map: no register inputs. D0.b out = the count, and A_free_wave_slot_count holds it too;
 * D7 and A0 are saved and restored by the original, so neither is an output. */
void g_count_free_wave_slots(uint8_t *image) {
    count_free_wave_slots(image);
}

/* ================================================================================================
 * enemy_alloc_slot @ 0x14be0 — the first free wave record, or failure.
 *
 * Returns the 68000 CARRY: clear means `*slot` now addresses a free record, set means there was
 * none. Note which arm leaves `*slot` alone: the early return on a zero count never loads A2 at
 * all, so the caller's own A2 survives it, while the loop-exhausted arm returns A2 walked one past
 * the array. That second arm is UNREACHABLE — it needs a non-zero free count with no free record,
 * and the count IS the number of free records — but it is transcribed rather than dropped, because
 * the instructions are there. See STATUS.md's mutation ledger.
 * ============================================================================================= */
unsigned enemy_alloc_slot(uint8_t *image, uint32_t *slot) {
    if (count_free_wave_slots(image) == 0)
        return CARRY_SET;

    uint32_t record = A_enemy_slots;
    for (unsigned i = 0; i < ENEMY_SLOT_COUNT; i++) {
        if (image[record + ENTITY_ALIVE] == 0) {
            *slot = record;
            return CARRY_CLEAR;
        }
        record = next_record(record);
    }
    *slot = record;
    return CARRY_SET;
}

/* Register map: A2 in/out = the record (untouched on the zero-count arm), CARRY out = failure. */
uint32_t g_enemy_alloc_slot(uint8_t *image, uint32_t slot_in, uint32_t carry_out) {
    uint32_t slot = slot_in;

    store_flag(image, carry_out, enemy_alloc_slot(image, &slot));
    return slot;
}

/* ================================================================================================
 * entity_type_in_mask @ 0x13bc2 — is this actor type a member of an 8-byte class bitmap?
 *
 * The bit order is MSB-first within each big-endian word: `not.w` turns the low nibble of the type
 * into `15 - (type & 15)`, which is the bit number `btst` wants for "the (type & 15)th bit from the
 * left". The word is picked by `(type >> 3) & 0xfffe`, i.e. by `type >> 4`.
 *
 * IT DOES NOT BOUND THE TYPE, AND NEITHER DOES ANY CALLER. `andi.w #$ff,d0` admits all 256. The
 * three maps its callers pass are `enemy_types_fire_homing` (0x19164), `enemy_types_can_fire`
 * (0x19172) and `enemy_types_fire_seeker` (0x19180) — fourteen bytes each, from the `lea` at
 * 0x11a64 / 0x11984 / 0x1196a — and each caller reaches here straight off a `move.b 17(a1),d0` with
 * no range test at all, so a type of 112 or more reads past the map it was given. (The 8-byte class
 * bitmaps at 0x19196 / 0x191a4 / 0x191ac belong to OTHER routines, which do bound their types; do
 * not import their bound into this one.) Transcribed as-is.
 * ============================================================================================= */
#define TYPE_MASK 0xffu            /* `andi.w #$ff,d0` */
#define TYPE_WORD_SHIFT 3          /* `lsr.w #3` ... */
#define TYPE_WORD_ALIGN 0xfffeu    /* ...then `andi.w #$fffe`: a byte offset forced even */
#define TYPE_BIT_MASK 0xfu         /* `not.w` + `andi.w #$f`: the bit's place inside that word */

unsigned entity_type_in_mask(const uint8_t *image, uint32_t bitmap, uint16_t type) {
    uint16_t masked = type & TYPE_MASK;
    uint32_t word = addr_add(bitmap, sign_ext16((masked >> TYPE_WORD_SHIFT) & TYPE_WORD_ALIGN));
    unsigned bit = (unsigned)(~masked & TYPE_BIT_MASK);

    return (be16(image + word) >> bit) & 1u;
}

/* Register map: A6 in = the bitmap, D0.w in = the type. The answer is the ZERO flag, which `btst`
 * sets when the bit is CLEAR — so the stub's `seq` byte is the INVERSE of the core's return. */
void g_entity_type_in_mask(uint8_t *image, uint32_t bitmap, uint32_t type_reg, uint32_t zero_out) {
    store_flag(image, zero_out, !entity_type_in_mask(image, bitmap, (uint16_t)type_reg));
}

/* ================================================================================================
 * actor_clamp_y @ 0x14c44 — hold an actor's integer y inside the playfield.
 *
 * The record is re-read between the two tests because the original re-reads it (`cmpi.w #$b0,4(a2)`
 * addresses memory, not a register the floor above left behind).
 * ============================================================================================= */
void actor_clamp_y(uint8_t *image, uint32_t actor) {
    if ((int16_t)be16(image + actor + ENTITY_Y) < ACTOR_KEEP_Y_MIN)
        wr16(image + actor + ENTITY_Y, ACTOR_KEEP_Y_MIN);
    if ((int16_t)be16(image + actor + ENTITY_Y) >= ACTOR_KEEP_Y_MAX)
        wr16(image + actor + ENTITY_Y, ACTOR_KEEP_Y_MAX);
}

/* Register map: A2 = the actor record. No outputs but the record. */
void g_actor_clamp_y(uint8_t *image, uint32_t actor) {
    actor_clamp_y(image, actor);
}

/* ================================================================================================
 * actor_despawn @ 0x14a64 — free an actor and credit its squadron.
 *
 * The squadron id is SIGN-EXTENDED before it indexes the counters (`ext.w d0` feeding a `d0.w`
 * index), so an id of 0x80..0xff decrements a byte BELOW A_squadron_kill_counters. names.txt's own
 * comment on that global says the game masks the id with 0xf at its two write sites and that only
 * six counters are ever cleared, so the range is the caller's business; here it is transcribed.
 * ============================================================================================= */
void actor_despawn(uint8_t *image, uint32_t actor) {
    uint32_t counter = addr_add(A_squadron_kill_counters,
                                sign_ext8(image[actor + ENTITY_SQUADRON]));

    image[counter]--;
    image[actor + ENTITY_ALIVE] = 0;
}

/* Register map: A2 = the actor record; D0 and A6 are scratch. No outputs but memory. */
void g_actor_despawn(uint8_t *image, uint32_t actor) {
    actor_despawn(image, actor);
}

/* ================================================================================================
 * The left-marching movers. Each is an entry of the kind-handler table at 0x19380.
 * ============================================================================================= */
#define ENEMY_STEP_LEFT 2   /* `sub.w #$2,d0` / `subi.w #$2,0(a2)`: all three march at this rate */

/* enemy_move_type16_left @ 0x1499e — 2 px/frame left, frozen with the map, despawns off the left. */
void enemy_move_type16_left(uint8_t *image, uint32_t actor) {
    if (image[A_scroll_frozen] != 0)
        return;

    int16_t x = (int16_t)(be16(image + actor + ENTITY_X) - ENEMY_STEP_LEFT);
    if (x < 0) {
        actor_despawn(image, actor);
        return;
    }
    wr16(image + actor + ENTITY_X, (uint16_t)x);
}

/* Register map: A2 = the actor record. */
void g_enemy_move_type16_left(uint8_t *image, uint32_t actor) {
    enemy_move_type16_left(image, actor);
}

/* enemy_move_type17_left @ 0x14ec4 — the same march, but it retires at the playfield edge rather
 * than at zero, and does NOT credit its squadron: the kill is a bare `clr.b` with no counter step
 * beside it. It also writes x back BEFORE deciding, so a retired record still carries its last x. */
void enemy_move_type17_left(uint8_t *image, uint32_t actor) {
    int16_t x = (int16_t)(be16(image + actor + ENTITY_X) - ENEMY_STEP_LEFT);

    wr16(image + actor + ENTITY_X, (uint16_t)x);
    if (x < ACTOR_KILL_X)
        image[actor + ENTITY_ALIVE] = 0;
}

/* Register map: A2 = the actor record. */
void g_enemy_move_type17_left(uint8_t *image, uint32_t actor) {
    enemy_move_type17_left(image, actor);
}

/* enemy_move_type15_dive @ 0x149d2 — march left until the player is inside a 45-degree cone ahead,
 * then climb.
 *
 * THE CONE IS `dx <= |dy|`, and that is not the test reversed: `cmp.w d2,d0 / bgt` skips the arming
 * while D0 (the diver's x minus the player's) exceeds D2 (the absolute y gap), so the dive arms
 * once the horizontal gap has closed to within the vertical one. dx is signed and goes negative
 * past the player, which keeps the dive armed rather than disarming it.
 *
 * Once armed, +0x1c stays set and the actor rises 2 px/frame — the x march is skipped entirely,
 * because the freeze test at the top and the armed test in the middle both jump into the same tail.
 */
void enemy_move_type15_dive(uint8_t *image, uint32_t actor) {
    if (image[A_scroll_frozen] == 0) {
        int16_t x = (int16_t)(be16(image + actor + ENTITY_X) - ENEMY_STEP_LEFT);
        if (x < 0) {
            actor_despawn(image, actor);
            return;
        }
        wr16(image + actor + ENTITY_X, (uint16_t)x);

        if (image[actor + ACTOR_DIVING] == 0) {
            int16_t dx = (int16_t)(x - (int16_t)be16(image + A_player_record + ENTITY_X));
            int16_t dy = (int16_t)((int16_t)be16(image + A_player_record + ENTITY_Y)
                                   - (int16_t)be16(image + actor + ENTITY_Y));
            if (dy < 0)
                dy = (int16_t)-dy;
            if (dx <= dy)
                image[actor + ACTOR_DIVING] = 1;
        }
    }

    if (image[actor + ACTOR_DIVING] == 0)
        return;

    int16_t y = (int16_t)(be16(image + actor + ENTITY_Y) - ENEMY_STEP_LEFT);
    wr16(image + actor + ENTITY_Y, (uint16_t)y);
    if (y < ACTOR_KEEP_Y_MIN)
        actor_despawn(image, actor);
}

/* Register map: A2 = the actor record; A1 = the player record, D0/D1/D2 scratch. */
void g_enemy_move_type15_dive(uint8_t *image, uint32_t actor) {
    enemy_move_type15_dive(image, actor);
}

/* ================================================================================================
 * The script VM's opcode handlers. Each is reached through the table at 0x19438 (an opcode class,
 * `opcode & 7`) or 0x19458 (an extended sub-op, `(opcode & 0x78) >> 3`), with D1 = the whole opcode
 * byte and A2 = the record. Their answer is the carry described at the top of this file.
 * ============================================================================================= */
#define SCRIPT_OPERAND_MASK 0x78u   /* `andi.b #$78` — bits 3..6 of the opcode are its operand */
#define SCRIPT_OPERAND_SHIFT 3      /* `lsr.b #3` */

/* The operand every class decodes the same way out of its own opcode byte. */
static uint8_t script_operand(uint8_t opcode) {
    return (uint8_t)((opcode & SCRIPT_OPERAND_MASK) >> SCRIPT_OPERAND_SHIFT);
}

/* Class 1 @ 0x14ce8 — open a loop: the operand is the pass count, and the CURRENT pc is remembered
 * as the point to rewind to. */
unsigned actor_script_op_loop_begin(uint8_t *image, uint32_t actor, uint8_t opcode) {
    image[actor + ACTOR_SCRIPT_LOOP_COUNT] = script_operand(opcode);
    wr16(image + actor + ACTOR_SCRIPT_LOOP_PC, be16(image + actor + ACTOR_SCRIPT_PC));
    return CARRY_SET;
}

/* Class 2 @ 0x14d00 — set the fire countdown and the value it reloads to, both from the operand. */
unsigned actor_script_op_set_fire_rate(uint8_t *image, uint32_t actor, uint8_t opcode) {
    uint8_t rate = script_operand(opcode);

    image[actor + ACTOR_FIRE_COUNTDOWN] = rate;
    image[actor + ACTOR_FIRE_RELOAD] = rate;
    return CARRY_SET;
}

/* Ext 0 @ 0x14dc0 — drift left, unless the map is frozen. Both arms answer carry CLEAR: the freeze
 * arm returns on `tst.b`, which clears C, and the moving arm clears it explicitly. */
unsigned actor_script_op_drift_left(uint8_t *image, uint32_t actor) {
    if (image[A_scroll_frozen] == 0)
        wr16(image + actor + ENTITY_X,
             (uint16_t)(be16(image + actor + ENTITY_X) - ENEMY_STEP_LEFT));
    return CARRY_CLEAR;
}

/* Ext 1 @ 0x14dd8 — stop dead. `clr.w` leaves the carry clear, so the frame ends here. */
unsigned actor_script_op_halt(uint8_t *image, uint32_t actor) {
    wr16(image + actor + ENTITY_DX, 0);
    wr16(image + actor + ENTITY_DY, 0);
    return CARRY_CLEAR;
}

/* Ext 3 @ 0x14e00 — close a loop, `dbf`-style but counting to zero rather than to -1: the count is
 * decremented and the pc rewound while it is still non-zero. Both arms answer carry SET, so the
 * opcode after the loop runs in the same frame either way. */
unsigned actor_script_op_loop_end(uint8_t *image, uint32_t actor) {
    uint8_t left = (uint8_t)(image[actor + ACTOR_SCRIPT_LOOP_COUNT] - 1);

    image[actor + ACTOR_SCRIPT_LOOP_COUNT] = left;
    if (left != 0)
        wr16(image + actor + ACTOR_SCRIPT_PC, be16(image + actor + ACTOR_SCRIPT_LOOP_PC));
    return CARRY_SET;
}

/* Ext 6 @ 0x14e50 — one unconditional step left, and the frame ends. */
unsigned actor_script_op_step_left(uint8_t *image, uint32_t actor) {
    wr16(image + actor + ENTITY_X,
         (uint16_t)(be16(image + actor + ENTITY_X) - ENEMY_STEP_LEFT));
    return CARRY_CLEAR;
}

/* Register map for the six handlers above: A2 = the record, D1.b = the whole opcode byte (only the
 * two operand classes read it), CARRY out = "the VM runs the next opcode in this frame". The
 * operand classes also leave their decoded operand in a data register, which is NOT an output: the
 * VM re-reads the opcode from the record at the top of every pass (0x14c76). */
void g_actor_script_op_loop_begin(uint8_t *image, uint32_t actor, uint32_t opcode_reg,
                                  uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_op_loop_begin(image, actor, (uint8_t)opcode_reg));
}

void g_actor_script_op_set_fire_rate(uint8_t *image, uint32_t actor, uint32_t opcode_reg,
                                     uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_op_set_fire_rate(image, actor, (uint8_t)opcode_reg));
}

void g_actor_script_op_drift_left(uint8_t *image, uint32_t actor, uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_op_drift_left(image, actor));
}

void g_actor_script_op_halt(uint8_t *image, uint32_t actor, uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_op_halt(image, actor));
}

void g_actor_script_op_loop_end(uint8_t *image, uint32_t actor, uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_op_loop_end(image, actor));
}

void g_actor_script_op_step_left(uint8_t *image, uint32_t actor, uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_op_step_left(image, actor));
}

/* ================================================================================================
 * The animation handlers. Each is an entry of the table at 0x193dc, called with A2 = the record.
 * ============================================================================================= */
#define ANIM_CYCLE_END 5            /* `cmpi.b #$5,+0x20` — the frame the four-frame cycle stops at */
#define ANIM_CYCLE_FIRST 1          /* ...and the one it restarts from */
#define ANIM_TABLE_INDEX_MASK 0xfu  /* `andi.l #$f` — sixteen slots, though only four are cycled */

/* `addi.b #1,32(a2)` — the byte step the five cycling handlers share. Returns the new frame so the
 * caller can compare it against ANIM_CYCLE_END, which is what `cmpi.b` does against the record. */
static uint8_t actor_bump_anim_frame(uint8_t *image, uint32_t actor) {
    uint8_t frame = (uint8_t)(image[actor + ENTITY_ANIM_FRAME] + 1);

    image[actor + ENTITY_ANIM_FRAME] = frame;
    return frame;
}

/* `move.b 32(a2),d1 / sub.b #1,d1 / andi.l #$f,d1 / lsl.l #2,d1 / move.l 0(a0,d1.l),10(a2)`.
 *
 * The frame is RE-READ from the record rather than taken from the bump above, because the wrap
 * writes 1 back first and the original reads the record again after it. The mask is four bits wide
 * where the cycle only ever produces 1..4, so a record whose frame byte arrives out of range still
 * resolves to one of sixteen table slots instead of running off — transcribed, not tidied. Unlike
 * sprite_ptr_offset above, this index is UNSIGNED: the mask leaves nothing for `ext` to extend. */
static void actor_set_sprite_from_frame_table(uint8_t *image, uint32_t actor, uint32_t table) {
    uint32_t slot = ((uint32_t)(uint8_t)(image[actor + ENTITY_ANIM_FRAME] - 1)
                     & ANIM_TABLE_INDEX_MASK) * SPRITE_PTR_BYTES;

    wr32(image + actor + ENTITY_SPRITE, be32(image + addr_add(table, slot)));
}

/* THE OTHER CYCLE. anim_ground_objects and asteroids_animate count 0..N-1 rather than 1..4, and
 * their `cmp.b #N / blt` is SIGNED — so a frame byte of 0x7f steps to 0x80 and is kept as a negative
 * table index rather than wrapping to 0. Shared because the signedness is the subtle half and a
 * second copy of it would be the one a later edit forgot. Returns the new frame. */
static uint8_t actor_advance_frame_signed(uint8_t *image, uint32_t record, int8_t frame_count) {
    int8_t frame = (int8_t)(image[record + ENTITY_ANIM_FRAME] + 1);

    if (frame >= frame_count)
        frame = 0;
    image[record + ENTITY_ANIM_FRAME] = (uint8_t)frame;
    return (uint8_t)frame;
}

/* The whole body types 12, 14, 15 and 17 share: advance, wrap at the end, point the record's sprite
 * at the frame. Only their gate and their table differ. */
static void actor_cycle_four_frames(uint8_t *image, uint32_t actor, uint32_t table) {
    if (actor_bump_anim_frame(image, actor) == ANIM_CYCLE_END)
        image[actor + ENTITY_ANIM_FRAME] = ANIM_CYCLE_FIRST;
    actor_set_sprite_from_frame_table(image, actor, table);
}

/* anim_enemy_type12 @ 0x14730 — the spinners, on the even half-frame. */
void anim_enemy_type12(uint8_t *image, uint32_t actor) {
    if (image[A_explosion_phase_odd] != 0)
        return;
    actor_cycle_four_frames(image, actor, A_anim_frames_type12);
}

/* anim_enemy_type14 @ 0x1476e — the same, from its own table. */
void anim_enemy_type14(uint8_t *image, uint32_t actor) {
    if (image[A_explosion_phase_odd] != 0)
        return;
    actor_cycle_four_frames(image, actor, A_anim_frames_type14);
}

/* anim_enemy_type15_diving @ 0x147ac — the diver animates only once its dive is armed. */
void anim_enemy_type15_diving(uint8_t *image, uint32_t actor) {
    if (image[A_explosion_phase_odd] != 0)
        return;
    if (image[actor + ACTOR_DIVING] == 0)
        return;
    actor_cycle_four_frames(image, actor, A_anim_frames_type15);
}

/* anim_enemy_type17 @ 0x1483e — gated on the OTHER half-frame, and by the other flag: this one runs
 * while A_anim_phase_b is SET, where the three above run while A_explosion_phase_odd is CLEAR. */
void anim_enemy_type17(uint8_t *image, uint32_t actor) {
    if (image[A_anim_phase_b] == 0)
        return;
    actor_cycle_four_frames(image, actor, A_anim_frames_type17);
}

/* Register map for all four: A2 = the actor record; D1 and A0 are scratch. */
void g_anim_enemy_type12(uint8_t *image, uint32_t actor) { anim_enemy_type12(image, actor); }
void g_anim_enemy_type14(uint8_t *image, uint32_t actor) { anim_enemy_type14(image, actor); }
void g_anim_enemy_type15_diving(uint8_t *image, uint32_t actor) {
    anim_enemy_type15_diving(image, actor);
}
void g_anim_enemy_type17(uint8_t *image, uint32_t actor) { anim_enemy_type17(image, actor); }

/* ================================================================================================
 * enemy_anim_puff_b @ 0x15332 — the same cycle, but the fifth frame KILLS the record instead of
 * wrapping: this is a one-shot puff, not a loop.
 * ============================================================================================= */
void enemy_anim_puff_b(uint8_t *image, uint32_t actor) {
    if (image[A_explosion_phase_odd] != 0)
        return;
    if (actor_bump_anim_frame(image, actor) == ANIM_CYCLE_END) {
        image[actor + ENTITY_ALIVE] = 0;
        return;
    }
    actor_set_sprite_from_frame_table(image, actor, A_puff_frame_ptrs_b);
}

/* Register map: A2 = the actor record. */
void g_enemy_anim_puff_b(uint8_t *image, uint32_t actor) {
    enemy_anim_puff_b(image, actor);
}

/* ================================================================================================
 * enemy_set_sprite_b @ 0x1530e — not an animation at all: it re-points the record's sprite from its
 * HEADING, through a variant byte. Two sign extensions in a row, both live for a heading byte of
 * 0x80 or more, so the second one goes through sprite_ptr_offset rather than being folded away.
 * ============================================================================================= */
void enemy_set_sprite_b(uint8_t *image, uint32_t actor) {
    uint32_t variant_at = addr_add(A_shot_variant_table,
                                   sign_ext8(image[actor + ACTOR_HEADING]));

    wr32(image + actor + ENTITY_SPRITE,
         be32(image + addr_add(A_enemy_sprite_ptrs_b, sprite_ptr_offset(image[variant_at]))));
}

/* Register map: A2 = the actor record; D0 and A0 are scratch. */
void g_enemy_set_sprite_b(uint8_t *image, uint32_t actor) {
    enemy_set_sprite_b(image, actor);
}

/* ================================================================================================
 * anim_ground_objects @ 0x14626 — the six scenery actors at the head of the record array.
 *
 * It uses the SIGNED cycle above, counting 0..3, rather than the 1..4 wrap the four actor handlers
 * share — so a frame byte of 0x7f is kept as a negative index and sprite_ptr_offset reaches 0x200
 * bytes BELOW the table. The game's own frames are 0..3.
 * ============================================================================================= */
#define GROUND_ACTOR_TYPE 0x34    /* `cmpi.b #$34,17(a2)` */
#define GROUND_ANIM_FRAMES 4      /* `cmp.b #$4,d1` */

void anim_ground_objects(uint8_t *image) {
    if (image[A_explosion_phase_odd] != 0)
        return;

    uint32_t record = A_entity_table;
    for (unsigned i = 0; i < GROUND_ACTOR_COUNT; i++) {
        if (image[record + ENTITY_ALIVE] != 0 && image[record + ENTITY_TYPE] == GROUND_ACTOR_TYPE) {
            uint8_t frame = actor_advance_frame_signed(image, record, GROUND_ANIM_FRAMES);

            wr32(image + record + ENTITY_SPRITE,
                 be32(image + addr_add(A_anim_frames_ground_t34, sprite_ptr_offset(frame))));
        }
        record = next_record(record);
    }
}

/* Register map: no register inputs. A2 walks the record array; D0 is the loop count, D1 and A0 are
 * scratch. */
void g_anim_ground_objects(uint8_t *image) {
    anim_ground_objects(image);
}

/* ================================================================================================
 * The asteroid columns: eighteen records, read as six groups of three.
 * ============================================================================================= */
#define ASTEROID_Y_STEP 1            /* `addi.w #$1` / `subi.w #$1` */
#define ASTEROID_X_STEP_SLOW 2       /* `subi.w #$2,0(a2)` when the slow flag is set */
#define ASTEROID_X_STEP_FAST 4       /* `subi.w #$4,0(a2)` otherwise */
#define ASTEROID_ANIM_FRAMES 6       /* `cmp.b #$6,d1` — six frames, counted 0..5 */
#define ASTEROID_COLUMN_BYTES 0x140  /* `add.l #$140,d3` — one column's slice of a frame bank */

/* asteroids_move @ 0x159f2 — drift each live column one pixel vertically, wrapping at both ends,
 * and two or four pixels left, killing it off the left edge.
 *
 * The wrap is ASYMMETRIC and deliberately so: falling past ACTOR_KEEP_Y_MAX restarts at 0, but
 * rising past 0 restarts at ACTOR_KEEP_Y_MAX — two tests, not one range check. The second is
 * `tst.b 4(a2)`, the HIGH byte of the y word, whose sign bit IS the word's, so it gives the same
 * answer a `tst.w` would. */
void asteroids_move(uint8_t *image) {
    uint32_t record = A_asteroid_records;

    for (unsigned group = 0; group < ASTEROID_GROUPS; group++) {
        for (unsigned column = 0; column < ASTEROID_COLUMNS; column++) {
            if (image[record + ENTITY_ALIVE] != 0) {
                int16_t y = (int16_t)be16(image + record + ENTITY_Y);
                y = (int16_t)(image[record + ASTEROID_Y_DESCENDING] != 0 ? y + ASTEROID_Y_STEP
                                                                        : y - ASTEROID_Y_STEP);
                if (y >= ACTOR_KEEP_Y_MAX)
                    y = 0;
                if (y < 0)
                    y = ACTOR_KEEP_Y_MAX;
                wr16(image + record + ENTITY_Y, (uint16_t)y);

                int16_t x = (int16_t)(be16(image + record + ENTITY_X)
                                      - (image[record + ASTEROID_SLOW] != 0
                                         ? ASTEROID_X_STEP_SLOW : ASTEROID_X_STEP_FAST));
                wr16(image + record + ENTITY_X, (uint16_t)x);
                if (x < 0)
                    image[record + ENTITY_ALIVE] = 0;
            }
            record = next_record(record);
        }
    }
}

/* Register map: no register inputs. A2 walks the records, D7 counts the groups and D6 the columns. */
void g_asteroids_move(uint8_t *image) {
    asteroids_move(image);
}

/* asteroids_animate @ 0x15a6a — cycle every live column's frame, on every OTHER call.
 *
 * `not.b` both flips the toggle and tests it, so the routine runs on the call that leaves the byte
 * ZERO — a half-rate gate that owns its own state rather than reading someone else's phase.
 *
 * The bank pointer picks the frame and the column offset picks the slice: each of the three records
 * in a group reads the SAME bank pointer and adds a further ASTEROID_COLUMN_BYTES, and the offset
 * restarts at every group. It also advances on a DEAD record, so a column's slice is fixed by its
 * position in the group rather than by how many of its neighbours are alive. */
void asteroids_animate(uint8_t *image) {
    image[A_asteroid_anim_toggle] = (uint8_t)~image[A_asteroid_anim_toggle];
    if (image[A_asteroid_anim_toggle] != 0)
        return;

    uint32_t record = A_asteroid_records;
    for (unsigned group = 0; group < ASTEROID_GROUPS; group++) {
        uint32_t column_offset = 0;
        for (unsigned column = 0; column < ASTEROID_COLUMNS; column++) {
            if (image[record + ENTITY_ALIVE] != 0) {
                uint8_t frame = actor_advance_frame_signed(image, record, ASTEROID_ANIM_FRAMES);
                uint32_t bank = be32(image + addr_add(A_asteroid_bank_ptrs,
                                                      sprite_ptr_offset(frame)));
                wr32(image + record + ENTITY_SPRITE, addr_add(bank, column_offset));
            }
            column_offset = addr_add(column_offset, ASTEROID_COLUMN_BYTES);
            record = next_record(record);
        }
    }
}

/* Register map: no register inputs. A2 walks the records, D6 counts the groups and D7 the columns,
 * and D3 carries the column offset. */
void g_asteroids_animate(uint8_t *image) {
    asteroids_animate(image);
}
