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
#include "player.h"
#include "weapon.h"
#include "collision.h"
#include "util.h"
#include "rng.h"
#include "sprite.h"
#include "sound.h"
/* ...and irq.h for ONE address: A_palette_hw_shadow, which explosion_animate_all clears
 * (`clr.w $18fc4` @ 0x15476). It is the owner's header, so including it is what the
 * conventions ask for — but it also declares the three off-image hardware stores whose
 * definition depends on which TU the build links (src/irq.c vs src/irq_hw_offtarget.c). This
 * translation unit calls none of them and has no stake in that split. */
#include "irq.h"

#define GROUND_ACTOR_COUNT 6    /* `move.w #$5,d0` — the type-0x34 scenery at A_entity_table */
#define ASTEROID_GROUPS 6       /* `move.w #$5,d7` — the outer loop */
#define ASTEROID_COLUMNS 3      /* `move.w #$2,d6` — three records per group */
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

/* ================================================================================================
 * entity_ptr_from_index @ 0x141c0 — the entity index -> record address the whole game shares.
 *
 * Two entry points for one body: 0x141c0 takes the index in D0's low byte (`move.b d0,d6`) and
 * 0x141c2 takes it already in D6. The `and.l #$ff,d6` that follows is what makes them the same
 * function — it discards whatever the caller left above the byte either way — and it is also the
 * whole of the bounds checking: an index of 20 or more addresses past the 20-record table, and one
 * of 0xff lands 0x1c68 bytes past its base. The multiply is `mulu.w`, so the product is the full
 * 32-bit one and never wraps at 16 bits.
 *
 * It belongs to `util` by subject and NOTHING PORTED SO FAR CALLS IT: its callers are weapon's
 * `entity_steer_toward_target` (0x141d6), `seeker_update` (0x140a6) and `homing_missile_update`
 * (0x14126), none of them reconstructed yet. It is here because it is the leaf those three all
 * wait on, and because ../out/globals.tsv puts its base, A_entity_table, in include/player.h —
 * whoever ports them should call this rather than write the multiply a fourth time.
 * ============================================================================================= */
#define ENTITY_INDEX_MASK 0xffu   /* `and.l #$ff,d6` */

uint32_t entity_ptr_from_index(uint32_t index) {
    return addr_add(A_entity_table, (index & ENTITY_INDEX_MASK) * ENTITY_STRIDE);
}

/* Register map: D0.b in at 0x141c0 / D6 in at 0x141c2, A1 out = the record. D6 comes back as the
 * BYTE OFFSET rather than as the index — `mulu.w` overwrote it — so the stub dumps D6 and A1 and
 * the glue mirrors both, which is what separates the multiply from a shift-and-add that left the
 * index behind. */
#define ENTITY_PTR_RESULT_D6 0u     /* the stub's two `move.l <reg>,(a0)+` slots, in that order */
#define ENTITY_PTR_RESULT_A1 4u

void g_entity_ptr_from_index(uint8_t *image, uint32_t index_reg, uint32_t result) {
    uint32_t record = entity_ptr_from_index(index_reg);

    wr32(image + addr_add(result, ENTITY_PTR_RESULT_D6), record - A_entity_table);
    wr32(image + addr_add(result, ENTITY_PTR_RESULT_A1), record);
}

/* ================================================================================================
 * The OTHER actor animation cycle — types 16, 20 and 22 of the table at A_actor_anim_table.
 *
 * Three differences from the four `actor_cycle_four_frames` handlers above, and the third is the
 * one that bites: they are gated on A_anim_phase_b rather than on A_explosion_phase_odd; two of
 * them take their frame count from a per-section GLOBAL rather than from a literal; and their table
 * index is NOT masked (`lsl.w #2` straight off the frame byte, where the four above `andi.l #$f`
 * first), so a frame byte out of range reaches up to 0x3fc bytes past the table it indexes.
 * ============================================================================================= */

/* Count the frame up, restart at ANIM_CYCLE_FIRST on reaching `limit`, and point the record's
 * sprite at frame - 1 of `table`.
 *
 * THE WRAP IS AN EQUALITY TEST (`cmp.b <limit>,d1 / bne`), not a bound: a frame byte that is
 * already past the limit counts on through 0xff and wraps to 0 rather than being pulled back. The
 * index is built through `clr.l d1` and byte arithmetic, so the `lsl.w #2` that follows sees a
 * value of 0..0xff and the word it produces is always positive — the `d1.w` index's sign extension
 * cannot reach here, unlike sprite_ptr_offset's above. */
static void actor_cycle_frames_to_limit(uint8_t *image, uint32_t actor, uint8_t limit,
                                        uint32_t table) {
    uint8_t frame = (uint8_t)(image[actor + ENTITY_ANIM_FRAME] + 1);

    if (frame == limit)
        frame = ANIM_CYCLE_FIRST;
    image[actor + ENTITY_ANIM_FRAME] = frame;

    uint32_t slot = (uint32_t)(uint8_t)(frame - 1) * SPRITE_PTR_BYTES;

    wr32(image + actor + ENTITY_SPRITE, be32(image + addr_add(table, slot)));
}

/* anim_enemy_type16 @ 0x146f6 — the only one of the three whose frame count is a literal, and it is
 * the same 5 the four-frame cycle stops at. */
void anim_enemy_type16(uint8_t *image, uint32_t actor) {
    if (image[A_anim_phase_b] != 0)
        return;
    actor_cycle_frames_to_limit(image, actor, ANIM_CYCLE_END, A_anim_frames_type16);
}

/* anim_enemy_type20 @ 0x1467e — its cycle length is whatever the level section loaded. */
void anim_enemy_type20(uint8_t *image, uint32_t actor) {
    if (image[A_anim_phase_b] != 0)
        return;
    actor_cycle_frames_to_limit(image, actor, image[A_anim_frame_limit_type20],
                                A_anim_frames_type20);
}

/* anim_enemy_type22 @ 0x146ba — the same, from the other limit byte and the other table. */
void anim_enemy_type22(uint8_t *image, uint32_t actor) {
    if (image[A_anim_phase_b] != 0)
        return;
    actor_cycle_frames_to_limit(image, actor, image[A_anim_frame_limit_type22],
                                A_anim_frames_type22);
}

/* Register map for all three: A2 = the actor record; D1 and A0 are scratch. */
void g_anim_enemy_type16(uint8_t *image, uint32_t actor) { anim_enemy_type16(image, actor); }
void g_anim_enemy_type20(uint8_t *image, uint32_t actor) { anim_enemy_type20(image, actor); }
void g_anim_enemy_type22(uint8_t *image, uint32_t actor) { anim_enemy_type22(image, actor); }

/* ================================================================================================
 * enemies_animate_all @ 0x147f2 — the frame's animation pass over the eleven actor records.
 *
 * It flips A_anim_phase_b, then walks entity slots 6..16 calling A_actor_anim_table[type] with the
 * record in A2. THE TABLE IS READ OUT OF THE IMAGE, so the reconstruction reads the same longword
 * and maps it back to the C function that IS that routine; ACTOR_ANIM_HANDLERS below is that map,
 * and test_enemy.py::test_anim_table_is_fully_reconstructed asserts the shipped table holds nothing
 * else. A pointer outside the map is left uncalled — a real limit rather than a default arm, and
 * one the routine's own guard makes reachable: `cmpi.b #$32,17(a2)` + `bge` is a SIGNED compare, so
 * a type of 0x17..0x31, or any negative one, passes it and indexes past the 23-entry table into the
 * script tables that follow it. STATUS.md records that as this routine's unreconstructed edge.
 * ============================================================================================= */
#define ACTOR_UPDATE_SLOTS 11        /* `move.w #$a,d7` + `dbf`, from A_enemy_shot_slots */
#define ACTOR_HANDLER_TYPE_MAX 0x32  /* `cmpi.b #$32,17(a2)` + `bge` — a SIGNED byte compare */

/* The addresses the shipped animation table holds. Entry addresses rather than data, so they are
 * spelt `FN_` and not `A_`: test_constants.py's "one address, one name" rule is about the globals a
 * subsystem could end up owning twice, and a routine's entry point is neither. */
#define FN_actor_handler_none    0x148c8u  /* a bare `rts` — the default entry of BOTH tables */
#define FN_anim_enemy_type20     0x1467eu
#define FN_anim_enemy_type22     0x146bau
#define FN_anim_enemy_type16     0x146f6u
#define FN_anim_enemy_type12     0x14730u
#define FN_anim_enemy_type14     0x1476eu
#define FN_anim_enemy_type15     0x147acu
#define FN_anim_enemy_type17     0x1483eu
#define FN_enemy_set_sprite_b    0x1530eu
#define FN_enemy_anim_puff_b     0x15332u

typedef void (*actor_handler)(uint8_t *image, uint32_t actor);

struct actor_handler_entry {
    uint32_t address;
    actor_handler run;      /* NULL where the original's entry is the bare `rts` */
};

static const struct actor_handler_entry ACTOR_ANIM_HANDLERS[] = {
    {FN_actor_handler_none, 0},
    {FN_anim_enemy_type20, anim_enemy_type20},
    {FN_anim_enemy_type22, anim_enemy_type22},
    {FN_anim_enemy_type16, anim_enemy_type16},
    {FN_anim_enemy_type12, anim_enemy_type12},
    {FN_anim_enemy_type14, anim_enemy_type14},
    {FN_anim_enemy_type15, anim_enemy_type15_diving},
    {FN_anim_enemy_type17, anim_enemy_type17},
    {FN_enemy_set_sprite_b, enemy_set_sprite_b},
    {FN_enemy_anim_puff_b, enemy_anim_puff_b},
};

#define ACTOR_ANIM_HANDLER_COUNT (sizeof ACTOR_ANIM_HANDLERS / sizeof ACTOR_ANIM_HANDLERS[0])

/* `lsl.l #2` — a jump table's entry is a longword, the same width as a sprite pointer and a
 * different thing; SPRITE_PTR_BYTES says which table it is striding and this table is not one. */
#define JUMP_TABLE_ENTRY_BYTES 4u

/* `move.b 17(a2),d1 / and.l #$ff,d1 / lsl.l #2,d1 / movea.l 0(a0,d1.l),a0` — a LONG index, so the
 * byte-masked type reaches 0x3fc bytes into (and past) the table. */
static uint32_t actor_anim_handler_address(const uint8_t *image, uint8_t type) {
    return be32(image + addr_add(A_actor_anim_table, (uint32_t)type * JUMP_TABLE_ENTRY_BYTES));
}

static void run_actor_anim_handler(uint8_t *image, uint32_t actor) {
    if (image[actor + ENTITY_ALIVE] == 0)
        return;
    if ((int8_t)image[actor + ENTITY_TYPE] >= ACTOR_HANDLER_TYPE_MAX)
        return;

    uint32_t address = actor_anim_handler_address(image, image[actor + ENTITY_TYPE]);

    for (unsigned i = 0; i < ACTOR_ANIM_HANDLER_COUNT; i++) {
        if (ACTOR_ANIM_HANDLERS[i].address != address)
            continue;
        if (ACTOR_ANIM_HANDLERS[i].run != 0)
            ACTOR_ANIM_HANDLERS[i].run(image, actor);
        return;
    }
}

void enemies_animate_all(uint8_t *image) {
    uint32_t record = A_enemy_shot_slots;

    image[A_anim_phase_b] = (uint8_t)~image[A_anim_phase_b];
    for (unsigned slot = 0; slot < ACTOR_UPDATE_SLOTS; slot++) {
        run_actor_anim_handler(image, record);
        record = next_record(record);
    }
}

/* Register map: no register inputs. A2 walks the records and D7 counts them; both are saved across
 * the `jsr` and restored, so a handler that clobbers either cannot derail the walk. */
void g_enemies_animate_all(uint8_t *image) {
    enemies_animate_all(image);
}

/* ================================================================================================
 * enemy_move_type14_sine @ 0x1494a — the patroller that marches left along a sine wave.
 *
 * Its y is not integrated: every frame it is recomputed as centre + sin(phase), so the record's
 * velocity words are never read. The phase is in degrees and wraps at a full turn, which is the
 * range sin_scaled's fold expects.
 * ============================================================================================= */
#define SINE_ENEMY_STEP_LEFT 4       /* `sub.w #$4,d0` — twice ENEMY_STEP_LEFT */
#define SINE_ENEMY_AMPLITUDE 6       /* `moveq #$6,d2` */
#define SINE_ENEMY_PHASE_STEP 0x14   /* `add.w #$14,d0` — 20 degrees a frame */

void enemy_move_type14_sine(uint8_t *image, uint32_t actor) {
    int16_t x = (int16_t)(be16(image + actor + ENTITY_X) - SINE_ENEMY_STEP_LEFT);

    if (x < 0) {
        /* The original open-codes actor_despawn here rather than calling it; the two are the same
         * five instructions, sign-extended squadron index included. */
        actor_despawn(image, actor);
        return;
    }
    wr16(image + actor + ENTITY_X, (uint16_t)x);

    uint16_t phase = be16(image + actor + ACTOR_SINE_PHASE);
    uint16_t offset = (uint16_t)sin_scaled(image, phase, SINE_ENEMY_AMPLITUDE);

    wr16(image + actor + ENTITY_Y,
         (uint16_t)(be16(image + actor + ACTOR_SINE_BASE_Y) + offset));

    phase = (uint16_t)(phase + SINE_ENEMY_PHASE_STEP);
    if ((int16_t)phase >= SIN_DEGREES_FULL)
        phase = (uint16_t)(phase - SIN_DEGREES_FULL);
    wr16(image + actor + ACTOR_SINE_PHASE, phase);
}

/* Register map: A2 = the actor record; D0 and D2 are the sine's arguments and scratch. */
void g_enemy_move_type14_sine(uint8_t *image, uint32_t actor) {
    enemy_move_type14_sine(image, actor);
}

/* ================================================================================================
 * The script VM's remaining opcode handlers — the arms that call out to util, collision and the
 * generator. Their answer is the carry described at the top of this file.
 * ============================================================================================= */
#define ACTOR_HEADING_MASK 0x3fu    /* `and.b #$3f` — 64 directions round the circle */
/* `move.w <velocity>,d0 / ext.l d0 / lsl.l #8,d0 / add.l d0,<position>`: entity_apply_velocity's
 * fixed-point step, open-coded on ONE axis by the two arms of the bounce below.
 *
 * THE SAME IDIOM IS OPEN-CODED TWICE MORE, in util.c's `entity_apply_velocity` (once per axis, with
 * the shift as a bare 8). Three copies is two too many and this is the only one that names the
 * fraction width — but util.c is another subsystem's file, so the merge belongs to its owner:
 * hoist this helper into util.h and let entity_apply_velocity call it twice. Recorded in
 * STATUS.md rather than done here. */
#define POSITION_FRACTION_BITS 8

static void step_position_by_velocity(uint8_t *image, uint32_t position_field, uint16_t velocity) {
    uint32_t step = (uint32_t)((int32_t)(int16_t)velocity) << POSITION_FRACTION_BITS;

    wr32(image + position_field, be32(image + position_field) + step);
}

static void negate_word(uint8_t *image, uint32_t field) {
    wr16(image + field, (uint16_t)-be16(image + field));
}

/* The scalar the heading ops multiply their direction by, read SIGNED — `move.b 30(a2),d1` feeding
 * the `ext.w d1` inside entity_set_velocity_from_angle. */
static int16_t actor_speed(const uint8_t *image, uint32_t actor) {
    return (int16_t)(int8_t)image[actor + ACTOR_SPEED];
}

/* Class 3 @ 0x14d14 — fall under gravity and bounce off the landscape.
 *
 * The terrain test is collision_chain_walk on THIS record's entity index, which the original
 * recovers by dividing the record pointer's distance from the table by the stride — an UNSIGNED
 * `divu.w`. A record below A_entity_table would therefore make the dividend enormous and overflow
 * the instruction, which leaves D0 alone and sets V, where the C below truncates a quotient
 * instead. No caller can produce one: the script VM only ever passes an entity_table record or a
 * boss segment at 0x18142, whose index is 39..43 and whose quotient fits a word.
 *
 * The vertical step is applied TWICE per call, and that is the instructions rather than a slip:
 * 0x143f8 ends by falling into entity_apply_velocity, which already adds both velocity words to the
 * position, and the tail here adds the y one again. The floor clamp sits between the two, so it is
 * the bounce's reversed velocity that the second add carries.
 */
#define ACTOR_FLOOR_Y 0xa0      /* `cmpi.w #$a0,4(a2)` — where the landscape stops the fall */

unsigned actor_script_op_bounce_fall(uint8_t *image, uint32_t actor) {
    uint16_t index = (uint16_t)((actor - A_entity_table) / ENTITY_STRIDE);

    if (collision_chain_walk(image, index)) {
        if (image[actor + ACTOR_BOUNCED] != 0) {
            step_position_by_velocity(image, actor + ENTITY_X, be16(image + actor + ENTITY_DX));
            return CARRY_CLEAR;
        }
        image[actor + ACTOR_BOUNCED] = 1;
        negate_word(image, actor + ENTITY_DY);
    }

    entity_apply_accel(image, actor, 1u << ACCEL_BIT_Y_ADD);
    if ((int16_t)be16(image + actor + ENTITY_Y) >= ACTOR_FLOOR_Y) {
        negate_word(image, actor + ENTITY_DY);
        image[actor + ACTOR_BOUNCED] = 1;
        wr16(image + actor + ENTITY_Y, ACTOR_FLOOR_Y);
    }
    step_position_by_velocity(image, actor + ENTITY_Y, be16(image + actor + ENTITY_DY));
    return CARRY_CLEAR;
}

/* Class 5 @ 0x14da2 — steer onto one of sixteen headings named by the opcode's operand.
 *
 * The shift is `lsr.b #1`, not the `lsr.b #3` every other operand class uses, so the operand's four
 * bits land at heading granularity 4 — sixteen of the sixty-four directions. */
#define SCRIPT_HEADING_SHIFT 1

/* What classes 5 and ext 2 both do once they have a heading from somewhere: remember it, turn it
 * into a velocity at the record's own speed, and integrate that velocity in the same call. Ext 5
 * two functions down deliberately does NEITHER the remembering nor the integrating, which is why
 * the three are not one body with a flag. */
static unsigned actor_steer_onto_heading(uint8_t *image, uint32_t actor, uint8_t heading) {
    image[actor + ACTOR_HEADING] = heading;
    entity_set_velocity_from_angle(image, actor, heading, actor_speed(image, actor));
    entity_apply_velocity(image, actor);
    return CARRY_CLEAR;
}

unsigned actor_script_op_set_heading(uint8_t *image, uint32_t actor, uint8_t opcode) {
    return actor_steer_onto_heading(
        image, actor, (uint8_t)((opcode & SCRIPT_OPERAND_MASK) >> SCRIPT_HEADING_SHIFT));
}

/* Ext 2 @ 0x14de2 — the same, onto a heading drawn from the generator. */
unsigned actor_script_op_random_heading(uint8_t *image, uint32_t actor) {
    return actor_steer_onto_heading(image, actor,
                                    (uint8_t)(rand16(image) & ACTOR_HEADING_MASK));
}

/* Ext 5 @ 0x14e38 — aim at the ship. Unlike its two neighbours it neither STORES the heading it
 * computed nor integrates the velocity it set, and it answers carry SET, so the script runs on. */
unsigned actor_script_op_aim_at_player(uint8_t *image, uint32_t actor) {
    uint16_t heading = angle_to_target(image, actor, A_player_record);

    entity_set_velocity_from_angle(image, actor, heading, actor_speed(image, actor));
    return CARRY_SET;
}

/* Ext 4 @ 0x14e1c and ext 9 @ 0x14e5c — accelerate towards the middle of the playfield.
 *
 * Both build a direction mask for entity_apply_accel out of a comparison against a centre line: ext
 * 4 on the vertical axis alone, ext 9 on both. Ext 9's name is ../names.txt's own
 * (`fn 0x14e5c actor_script_op_thrust_to_centre`); EXT 4 HAS NO `fn` LINE THERE, so
 * `actor_script_op_thrust_to_centre_y` is this reconstruction's coinage and STATUS.md says so. */
#define ACTOR_CENTRE_X 0xd8   /* `cmpi.w #$d8,0(a2)` */
#define ACTOR_CENTRE_Y 0x60   /* `cmpi.w #$60,4(a2)` */

static uint8_t thrust_bits_towards_centre_y(const uint8_t *image, uint32_t actor) {
    return (int16_t)be16(image + actor + ENTITY_Y) < ACTOR_CENTRE_Y
               ? (uint8_t)(1u << ACCEL_BIT_Y_ADD) : (uint8_t)(1u << ACCEL_BIT_Y_SUB);
}

unsigned actor_script_op_thrust_to_centre_y(uint8_t *image, uint32_t actor) {
    entity_apply_accel(image, actor, thrust_bits_towards_centre_y(image, actor));
    return CARRY_CLEAR;
}

unsigned actor_script_op_thrust_to_centre(uint8_t *image, uint32_t actor) {
    uint8_t bits = (int16_t)be16(image + actor + ENTITY_X) < ACTOR_CENTRE_X
                       ? (uint8_t)(1u << ACCEL_BIT_X_ADD) : (uint8_t)(1u << ACCEL_BIT_X_SUB);

    entity_apply_accel(image, actor, (uint8_t)(bits | thrust_bits_towards_centre_y(image, actor)));
    return CARRY_CLEAR;
}

/* actor_script_continue @ 0x14eb8 — `ori.b #$1,ccr / rts`, the six bytes a handler branches to in
 * order to say "run the next opcode in this frame". It is also ext 11's tail. */
unsigned actor_script_continue(void) {
    return CARRY_SET;
}

/* actor_script_op_end_frame @ 0x14ebe — its mirror, `andi.b #$fe,ccr / rts`, and ext 15 of the
 * table: an opcode that does nothing but end the actor's frame. */
unsigned actor_script_op_end_frame(void) {
    return CARRY_CLEAR;
}

/* Ext 11 @ 0x14e8c — nudge the speed up or down by one, at random, keeping it in 1..7.
 *
 * BOTH COMPARISONS ARE SIGNED (`cmp.b` + `bge` / `blt`) where the draw they read is a random BYTE,
 * and that has two consequences a paraphrase loses:
 *
 *  * the "+1" arm is UNREACHABLE. Only a draw of 0x55..0x7f gets past the first test — 0x80..0xff
 *    read as negative and take the early return — and every one of those is above 0xaa read as
 *    -86, so the second test always falls through to the negation. The nudge is always -1.
 *  * the early return's CARRY IS THE FIRST COMPARE'S OWN, and `cmp.b` sets it UNSIGNED. So a draw
 *    below 0x55 leaves carry set and the script runs on, while a draw of 0x80 or more leaves it
 *    clear and ends the actor's frame — two different answers out of the one `rts`.
 *
 * Transcribed as written. STATUS.md records the arm as UNREACHABLE rather than as a mutation
 * survivor, and deliberately: swapping the ternary's two values changes the arm that IS
 * reached, so such a mutant dies for the wrong reason. The assertion that stands in for it is
 * test_enemy.py::test_op_random_speed_nudge_never_draws_the_increment.
 */
#define SPEED_NUDGE_MIN_DRAW 0x55   /* `cmp.b #$55,d0` + `bge` */
#define SPEED_NUDGE_UP_DRAW 0xaa    /* `cmp.b #$aa,d0` + `blt` — the arm no draw reaches */
#define ACTOR_SPEED_MASK 0x7u       /* `and.b #$7,d1`, and a result of 0 leaves the speed alone */

unsigned actor_script_op_random_speed_nudge(uint8_t *image, uint32_t actor) {
    uint8_t draw = (uint8_t)rand16(image);

    if ((int8_t)draw < (int8_t)SPEED_NUDGE_MIN_DRAW)
        return draw < SPEED_NUDGE_MIN_DRAW ? CARRY_SET : CARRY_CLEAR;

    int nudge = (int8_t)draw < (int8_t)SPEED_NUDGE_UP_DRAW ? 1 : -1;
    uint8_t speed = (uint8_t)((image[actor + ACTOR_SPEED] + nudge) & ACTOR_SPEED_MASK);

    if (speed != 0)
        image[actor + ACTOR_SPEED] = speed;
    return actor_script_continue();
}

/* Register map for the handlers above: A2 = the record and D1.b = the whole opcode byte (only
 * actor_script_op_set_heading reads it), CARRY out = "run the next opcode in this frame". */
void g_actor_script_op_bounce_fall(uint8_t *image, uint32_t actor, uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_op_bounce_fall(image, actor));
}

void g_actor_script_op_set_heading(uint8_t *image, uint32_t actor, uint32_t opcode_reg,
                                   uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_op_set_heading(image, actor, (uint8_t)opcode_reg));
}

void g_actor_script_op_random_heading(uint8_t *image, uint32_t actor, uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_op_random_heading(image, actor));
}

void g_actor_script_op_aim_at_player(uint8_t *image, uint32_t actor, uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_op_aim_at_player(image, actor));
}

void g_actor_script_op_thrust_to_centre_y(uint8_t *image, uint32_t actor, uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_op_thrust_to_centre_y(image, actor));
}

void g_actor_script_op_thrust_to_centre(uint8_t *image, uint32_t actor, uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_op_thrust_to_centre(image, actor));
}

void g_actor_script_op_random_speed_nudge(uint8_t *image, uint32_t actor, uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_op_random_speed_nudge(image, actor));
}

void g_actor_script_continue(uint8_t *image, uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_continue());
}

void g_actor_script_op_end_frame(uint8_t *image, uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_op_end_frame());
}

/* ================================================================================================
 * The explosion groups — explosion_spawn @ 0x15510 and explosion_animate_all @ 0x1544e.
 *
 * A group is SIX entity records named by a byte list at A_explosion_group_members, and there are
 * two of them: bit 0 of A_explosion_group_active_bits is the end-of-section blast and bit 1 the
 * ship's death. The spawn seeds all six from one source record; the per-frame pass steps each
 * particle's own EXPLOSION_PART_FRAME counter and re-points its sprite until the counter reaches
 * EXPLOSION_END_FRAME, which kills the record.
 * ============================================================================================= */
#define EXPLOSION_GROUPS 2            /* `move.w #$1,d6` + `dbf` */
#define EXPLOSION_PARTS 6             /* `move.w #$5,d7` + `dbf`, and `mulu.w #$6` on the group */
#define EXPLOSION_END_FRAME 0x0d      /* `cmpi.b #$d` — the frame that retires a particle */
#define EXPLOSION_PART_TYPE 0x64      /* `move.b #$64,17(a2)` */
#define EXPLOSION_PART_ROWS 0x10      /* `move.w #$10,8(a2)` */
#define EXPLOSION_X_ALIGN 0xfffcu     /* `and.w #$fffc,d0` — every particle's x is 4-pixel aligned */
#define EXPLOSION_SOUND 0x14          /* `moveq #$14,d1` + `bsr sound_start` */
/* One particle's entry in the offsets table: three words, in this order. */
#define EXPLOSION_OFFSET_DX 0u
#define EXPLOSION_OFFSET_DY 2u
#define EXPLOSION_OFFSET_FRAME 4u
#define EXPLOSION_OFFSET_WORDS 3
/* Group 1 is the SHIP's death (bit 1 of A_explosion_group_active_bits; names.txt on 0x19670),
 * and it is the pass that also clears the charge flag and the palette shadow. */
#define EXPLOSION_GROUP_SHIP 1u
#define EXPLOSION_FRAME_INDEX_MASK 0x7fu   /* `and.l #$7f,d1` before the table index */

/* `move.b (a4)+,d2 / ext.w d2 / mulu.w #$2c,d2` — a group's member list is entity INDICES, and the
 * byte is sign-extended to a WORD and then multiplied UNSIGNED. So a member of 0x80 or more becomes
 * a huge POSITIVE offset (0xff80 * 0x2c) rather than a negative one, and lands outside the image
 * entirely; nothing here bounds it. The shipped lists hold 9..14 and {0,1,2,3,17,18}. */
static uint32_t explosion_part_record(const uint8_t *image, uint32_t group, unsigned part) {
    uint32_t member = addr_add(A_explosion_group_members, group * EXPLOSION_PARTS + part);
    uint32_t index = (uint16_t)sign_ext8(image[member]);

    return addr_add(A_entity_table, index * ENTITY_STRIDE);
}

/* explosion_spawn @ 0x15510 — blow `source` apart into `group`'s six particles.
 *
 * The offsets at A_explosion_particle_offsets are CUMULATIVE, not absolute: each particle adds its
 * dx to the running x and its dy to the running y, so the six land in a chain from the source
 * rather than in a fixed rosette around it. Only x is re-aligned after each step. */
void explosion_spawn(uint8_t *image, uint32_t source, uint16_t group) {
    uint16_t x = be16(image + source + ENTITY_X);
    uint16_t y = be16(image + source + ENTITY_Y);
    uint32_t offset = A_explosion_particle_offsets;

    image[A_explosion_group_active_bits] |= (uint8_t)(1u << (group % 8u));

    for (unsigned part = 0; part < EXPLOSION_PARTS; part++) {
        uint32_t record = explosion_part_record(image, group, part);
        uint8_t frame;

        x = (uint16_t)((x + be16(image + addr_add(offset, EXPLOSION_OFFSET_DX)))
                       & EXPLOSION_X_ALIGN);
        y = (uint16_t)(y + be16(image + addr_add(offset, EXPLOSION_OFFSET_DY)));
        frame = (uint8_t)be16(image + addr_add(offset, EXPLOSION_OFFSET_FRAME));
        offset = addr_add(offset, EXPLOSION_OFFSET_WORDS * 2u);

        image[record + ENTITY_ALIVE] = 0;
        image[record + EXPLOSION_PART_FRAME] = frame;
        wr16(image + record + ENTITY_X, x);
        wr16(image + record + ENTITY_Y, y);
        wr16(image + record + ENTITY_HEIGHT, EXPLOSION_PART_ROWS);
        image[record + ENTITY_TYPE] = EXPLOSION_PART_TYPE;
    }
    image[A_scroll_frozen] = 1;
    /* D0 still holds the last particle's x, and that is what reaches sound_start's channel
     * argument — which only matters for a tune with no 0xfa header (src/sound.c). */
    sound_start(image, EXPLOSION_SOUND, (uint8_t)x);
}

/* Register map: A2 = the record to explode at, D2 = the group. D0/D1 carry the running position and
 * A3/A4/A7 walk the tables; none is an output. */
void g_explosion_spawn(uint8_t *image, uint32_t source, uint32_t group_reg) {
    explosion_spawn(image, source, (uint16_t)group_reg);
}

/* One particle's step: count its frame up, retire it at EXPLOSION_END_FRAME, otherwise mark it
 * alive and point its sprite at frame - 1 of the shared table.
 *
 * THE TWO SKIPS ARE NOT ONE TEST. A counter that reaches 0 (from 0xff) or turns negative (from
 * 0x7f) leaves the record alive-byte and sprite alone but STILL stores the stepped counter, where
 * the retiring arm stores EXPLOSION_END_FRAME and clears the alive byte. */
static void explosion_part_step(uint8_t *image, uint32_t record) {
    uint8_t frame;
    uint32_t slot;

    if (image[record + EXPLOSION_PART_FRAME] == EXPLOSION_END_FRAME)
        return;

    frame = (uint8_t)(image[record + EXPLOSION_PART_FRAME] + 1);
    if (frame == EXPLOSION_END_FRAME) {
        image[record + EXPLOSION_PART_FRAME] = EXPLOSION_END_FRAME;
        image[record + ENTITY_ALIVE] = 0;
        return;
    }

    image[record + EXPLOSION_PART_FRAME] = frame;
    if (frame == 0 || (int8_t)frame < 0)
        return;

    image[record + ENTITY_ALIVE] = 1;
    /* `and.l #$7f,d1 / sub.b #$1,d1 / lsl.w #2,d1` — the mask comes BEFORE the decrement, and the
     * decrement is a byte op on a register whose high bits the `clr.w` left at zero. */
    slot = (uint32_t)(uint8_t)((frame & EXPLOSION_FRAME_INDEX_MASK) - 1u) * SPRITE_PTR_BYTES;
    wr32(image + record + ENTITY_SPRITE,
         be32(image + addr_add(A_explosion_small_frame_ptrs, slot)));
}

/* explosion_animate_all @ 0x1544e — one frame of both groups, at half rate.
 *
 * The two clears on group 1's pass happen BEFORE its active bit is tested, so they run on every
 * ticking frame whether or not the ship is exploding — which is why they are outside the `btst`
 * arm here too. `not.b` both flips the toggle and tests it, and the branch is the OPPOSITE WAY
 * ROUND from asteroids_animate's: `beq` returns, so this pass runs on the call that leaves the
 * toggle NON-zero. */
void explosion_animate_all(uint8_t *image) {
    if (image[A_explosion_group_active_bits] == 0)
        return;
    image[A_explosion_frame_toggle] = (uint8_t)~image[A_explosion_frame_toggle];
    if (image[A_explosion_frame_toggle] == 0)
        return;

    for (uint32_t group = 0; group < EXPLOSION_GROUPS; group++) {
        if (group == EXPLOSION_GROUP_SHIP) {
            image[A_fire_charged] = 0;
            wr16(image + A_palette_hw_shadow, 0);
        }
        if (!((image[A_explosion_group_active_bits] >> (group % 8u)) & 1u))
            continue;
        for (unsigned part = 0; part < EXPLOSION_PARTS; part++)
            explosion_part_step(image, explosion_part_record(image, group, part));
    }
}

/* Register map: no register inputs. D4 counts the groups, D6/D7 the loops, A0/A2/A4 are scratch. */
void g_explosion_animate_all(uint8_t *image) {
    explosion_animate_all(image);
}

/* ================================================================================================
 * asteroids_draw @ 0x159be — blit the eighteen live column records.
 *
 * The only argument the draw takes is D2, the bank's HALF-frame stride: draw_sprite_masked scales
 * the sub-cell phase by it, so it is the asteroid frame's own size halved rather than a number of
 * its own (include/sprite.h, "how it indexes a preshift bank").
 * ============================================================================================= */
#define ASTEROID_DRAW_PHASE_STEP (ASTEROID_FRAME_BYTES / 2u)   /* `move.w #$1e0,d2` */

void asteroids_draw(uint8_t *image) {
    uint32_t record = A_asteroid_records;

    for (unsigned group = 0; group < ASTEROID_GROUPS; group++) {
        for (unsigned column = 0; column < ASTEROID_COLUMNS; column++) {
            if (image[record + ENTITY_ALIVE] != 0)
                draw_sprite_masked(image, record, ASTEROID_DRAW_PHASE_STEP);
            record = next_record(record);
        }
    }
}

/* Register map: no register inputs. A2 walks the records, D7 counts the groups and D6 the columns;
 * both counters are saved across the `bsr` and restored. */
void g_asteroids_draw(uint8_t *image) {
    asteroids_draw(image);
}
