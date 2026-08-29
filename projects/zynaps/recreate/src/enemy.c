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
#include "init.h"
#include "player.h"
#include "weapon.h"
#include "collision.h"
#include "mothership.h"
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
    actor_cycle_frames_to_limit(image, actor, image[A_section_param_a],
                                A_anim_frames_type20);
}

/* anim_enemy_type22 @ 0x146ba — the same, from the other limit byte and the other table. */
void anim_enemy_type22(uint8_t *image, uint32_t actor) {
    if (image[A_anim_phase_b] != 0)
        return;
    actor_cycle_frames_to_limit(image, actor, image[A_section_param_b],
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

/* ONE HELPER FOR EVERY JUMP TABLE IN THIS FILE — the two per-type dispatch tables and the script
 * VM's two — because the index arithmetic is the same however the original spells it:
 * `and.l #$ff / lsl.l #2 / movea.l 0(a0,d1.l),a0` in the per-type passes, a LONG index so a
 * byte-masked type reaches 0x3fc bytes into (and past) the table; `ext.w / lsl.w #2 /
 * movea.l 0(a0,d0.w),a0` in the script VM, where the index has already been masked to three or four
 * bits so the sign extension cannot reach and the word index is always positive. Both are
 * `table + index * 4` over a byte index. */
static uint32_t jump_table_entry(const uint8_t *image, uint32_t table, uint8_t index) {
    return be32(image + addr_add(table, (uint32_t)index * JUMP_TABLE_ENTRY_BYTES));
}

/* THE MAPS ONE PASS CONSULTS, in order. The move pass has two of them, because its table's neighbour
 * in memory is the animation table and its own type guard reaches into it — see `enemies_move_all`.
 * The animation pass has one: what lies past ITS table is the script VM's, whose handlers answer in
 * the carry and take an opcode, so those cannot be run from here at all (STATUS.md). */
struct actor_handler_map {
    const struct actor_handler_entry *entries;
    unsigned count;
};

/* The guard and the lookup BOTH passes share, parameterised by which table is being read.
 * `enemies_move_all` @ 0x1487c is `enemies_animate_all` @ 0x147f2 with the other table and no phase
 * flip, down to the same `cmpi.b #$32` + `bge` on the type, so the walk is written once here. */
static void run_actor_handler(uint8_t *image, uint32_t actor, uint32_t table,
                              const struct actor_handler_map *maps, unsigned map_count) {
    if (image[actor + ENTITY_ALIVE] == 0)
        return;
    if ((int8_t)image[actor + ENTITY_TYPE] >= ACTOR_HANDLER_TYPE_MAX)
        return;

    uint32_t address = jump_table_entry(image, table, image[actor + ENTITY_TYPE]);

    for (unsigned m = 0; m < map_count; m++) {
        for (unsigned i = 0; i < maps[m].count; i++) {
            if (maps[m].entries[i].address != address)
                continue;
            if (maps[m].entries[i].run != 0)
                maps[m].entries[i].run(image, actor);
            return;
        }
    }
}

static const struct actor_handler_map ANIM_PASS_MAPS[] = {
    {ACTOR_ANIM_HANDLERS, ACTOR_ANIM_HANDLER_COUNT},
};

#define ANIM_PASS_MAP_COUNT (sizeof ANIM_PASS_MAPS / sizeof ANIM_PASS_MAPS[0])

void enemies_animate_all(uint8_t *image) {
    uint32_t record = A_enemy_shot_slots;

    image[A_anim_phase_b] = (uint8_t)~image[A_anim_phase_b];
    for (unsigned slot = 0; slot < ACTOR_UPDATE_SLOTS; slot++) {
        run_actor_handler(image, record, A_actor_anim_table, ANIM_PASS_MAPS,
                          ANIM_PASS_MAP_COUNT);
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
#define EXPLOSION_PART_ROWS 0x10      /* `move.w #$10,8(a2)` */
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

/* ================================================================================================
 * entity_ptr_from_index's SECOND ENTRY @ 0x141c2 — the index already in D6.
 *
 * There is no core here on purpose: the two entries share one body (0x141c0 only prepends
 * `move.b d0,d6`), so the routine IS `entity_ptr_from_index` above and this is the other way in.
 * Once it is spelt, `entity_record` in include/collision.h and `entity_from_index` in src/weapon.c
 * are both this arithmetic written again — three copies of one multiply. The swap is theirs to make
 * (this batch owns neither file); STATUS.md's enemy section carries the row that says so.
 * ============================================================================================= */

/* Register map: D6 in = the index (its high three bytes are discarded by the `and.l #$ff`), A1 out
 * = the record, D6 out = the byte offset. The two stores are the D0 entry's, so they are made
 * there and mirrored by calling it. */
void g_entity_ptr_from_index_d6(uint8_t *image, uint32_t index_reg, uint32_t result) {
    g_entity_ptr_from_index(image, index_reg, result);
}

/* ================================================================================================
 * enemy_morph_to_type6 @ 0x13ad0 — turn a spent projectile into a ground-impact puff.
 *
 * A leaf: five stores over the record it is given, no call and no guard. Its one caller is
 * `enemy_shot_tick_type0b`, which reaches it when a type-0x0b seeker's time-to-live runs out.
 * ============================================================================================= */
#define GROUND_PUFF_TYPE 6
#define GROUND_PUFF_ROWS 0x10        /* `move.w #$10,8(a2)` */
#define GROUND_PUFF_RISE 2           /* `subi.w #$2,4(a2)` — the puff sits two pixels higher */
#define GROUND_PUFF_FIRST_FRAME 1

void enemy_morph_to_type6(uint8_t *image, uint32_t entity) {
    image[entity + ENTITY_TYPE] = GROUND_PUFF_TYPE;
    wr16(image + entity + ENTITY_HEIGHT, GROUND_PUFF_ROWS);
    wr16(image + entity + ENTITY_Y,
         (uint16_t)(be16(image + entity + ENTITY_Y) - GROUND_PUFF_RISE));
    wr32(image + entity + ENTITY_SPRITE, A_ground_puff_sprite);
    image[entity + ENTITY_ANIM_FRAME] = GROUND_PUFF_FIRST_FRAME;
}

/* Register map: A2 = the record. No outputs but memory. */
void g_enemy_morph_to_type6(uint8_t *image, uint32_t entity) {
    enemy_morph_to_type6(image, entity);
}

/* ================================================================================================
 * The script VM — actor_script_run @ 0x14c66 and its two dispatch tables.
 *
 * One actor's script is a byte stream at A_actor_script_data. A byte with bit 7 set is a DELAY and
 * reloads ACTOR_SCRIPT_DELAY with its low seven bits; a byte without it is an OPCODE, stored in
 * ACTOR_SCRIPT_OPCODE and re-run every frame until the delay expires. The opcode's low three bits
 * pick a class out of A_script_op_table, and class 7 fans out again through A_script_op_ext_table
 * on bits 3..6; every handler answers in the CARRY, set meaning "run the next opcode in this same
 * frame" (include/enemy.h's note on SCC_BYTE_TRUE).
 *
 * BOTH TABLES ARE READ OUT OF THE IMAGE and mapped back to C, exactly as `enemies_animate_all`
 * does with its own, so a case that pokes a table entry drives the reconstruction's lookup and not
 * a compiled-in choice. An address neither map holds is left uncalled and answers CARRY CLEAR — the
 * original would `jsr` it, and for the five NULL longwords the tables ship (class 6, ext 10 and
 * 12..14) that means entering the 68000 vector page. No differential can compare that, so the arm
 * is stated here and in STATUS.md rather than pinned; names.txt's accounting of both tables says no
 * shipped opcode reaches one.
 * ============================================================================================= */
#define SCRIPT_CLASS_MASK 0x7u        /* `and.b #$7,d0` — which of the eight opcode classes */
#define SCRIPT_DELAY_RELOAD 1         /* `move.b #$1,38(a2)` once an opcode has been fetched */
#define SCRIPT_BYTE_IS_DELAY 0x80u    /* `bpl` on the fetched byte: bit 7 set makes it a delay... */
#define SCRIPT_DELAY_MASK 0x7fu       /* ...whose low seven bits are the frame count */

/* One arm of either table. Every handler takes the record in A2 and answers in the carry, but only
 * some read the opcode byte in D1 — so an entry carries whichever shape its routine has, and a
 * `run` of 0 means the opcode goes in too. */
struct script_arm {
    uint32_t address;
    unsigned (*run)(uint8_t *image, uint32_t actor);
    unsigned (*run_with_opcode)(uint8_t *image, uint32_t actor, uint8_t opcode);
};

/* The four handlers whose C signature is neither of those two shapes. Each one's `return` is the
 * flag the original leaves, taken from its last instruction rather than from its subject. */

/* Class 0 — entity_apply_accel @ 0x143f8 reads the WHOLE opcode byte as its direction bits, and
 * falls into entity_apply_velocity, whose `andi #$fe,ccr` is the answer. */
static unsigned script_apply_accel(uint8_t *image, uint32_t actor, uint8_t opcode) {
    entity_apply_accel(image, actor, opcode);
    return CARRY_CLEAR;
}

/* Ext 7 — entity_apply_velocity @ 0x14306 itself, which ends on that same `andi #$fe,ccr`. */
static unsigned script_apply_velocity(uint8_t *image, uint32_t actor) {
    entity_apply_velocity(image, actor);
    return CARRY_CLEAR;
}

/* Ext 8 — entity_steer_toward_target @ 0x141d6. BOTH its exits run into 0x14306, so it answers
 * CARRY CLEAR as well. THE C CANNOT SAY SO — it is `void` and its own glue stores no flag — so this
 * one line is the whole of the claim, taken from ../../names.txt's comment on 0x14242 and from
 * STATUS.md's weapon-section residual rather than from anything a memory differential can see. The
 * ext battery in test/test_enemy.py drives it and IS the surface that residual asked for. */
static unsigned script_steer_toward_target(uint8_t *image, uint32_t actor) {
    entity_steer_toward_target(image, actor);
    return CARRY_CLEAR;
}

/* Ext 15 — actor_script_op_end_frame @ 0x14ebe takes no argument at all. */
static unsigned script_end_frame(uint8_t *image, uint32_t actor) {
    (void)image;
    (void)actor;
    return actor_script_op_end_frame();
}

/* The addresses both shipped tables hold, per ../../names.txt's accounting of 0x19438 / 0x19458 and
 * read back off the image by test_enemy.py. Entry points, so `FN_` and not `A_`. */
#define FN_entity_apply_accel                  0x143f8u
#define FN_entity_apply_velocity               0x14306u
#define FN_entity_steer_toward_target          0x141d6u
#define FN_actor_script_op_ext                 0x14cceu
#define FN_actor_script_op_loop_begin          0x14ce8u
#define FN_actor_script_op_set_fire_rate       0x14d00u
#define FN_actor_script_op_bounce_fall         0x14d14u
#define FN_actor_script_op_fire                0x14d88u
#define FN_actor_script_op_set_heading         0x14da2u
#define FN_actor_script_op_drift_left          0x14dc0u
#define FN_actor_script_op_halt                0x14dd8u
#define FN_actor_script_op_random_heading      0x14de2u
#define FN_actor_script_op_loop_end            0x14e00u
#define FN_actor_script_op_thrust_to_centre_y  0x14e1cu
#define FN_actor_script_op_aim_at_player       0x14e38u
#define FN_actor_script_op_step_left           0x14e50u
#define FN_actor_script_op_thrust_to_centre    0x14e5cu
#define FN_actor_script_op_random_speed_nudge  0x14e8cu
#define FN_actor_script_op_end_frame           0x14ebeu

static const struct script_arm SCRIPT_CLASS_ARMS[] = {
    {FN_entity_apply_accel, 0, script_apply_accel},
    {FN_actor_script_op_loop_begin, 0, actor_script_op_loop_begin},
    {FN_actor_script_op_set_fire_rate, 0, actor_script_op_set_fire_rate},
    {FN_actor_script_op_bounce_fall, actor_script_op_bounce_fall, 0},
    {FN_actor_script_op_fire, 0, actor_script_op_fire},
    {FN_actor_script_op_set_heading, 0, actor_script_op_set_heading},
    {FN_actor_script_op_ext, 0, actor_script_op_ext},
};

static const struct script_arm SCRIPT_EXT_ARMS[] = {
    {FN_actor_script_op_drift_left, actor_script_op_drift_left, 0},
    {FN_actor_script_op_halt, actor_script_op_halt, 0},
    {FN_actor_script_op_random_heading, actor_script_op_random_heading, 0},
    {FN_actor_script_op_loop_end, actor_script_op_loop_end, 0},
    {FN_actor_script_op_thrust_to_centre_y, actor_script_op_thrust_to_centre_y, 0},
    {FN_actor_script_op_aim_at_player, actor_script_op_aim_at_player, 0},
    {FN_actor_script_op_step_left, actor_script_op_step_left, 0},
    {FN_entity_apply_velocity, script_apply_velocity, 0},
    {FN_entity_steer_toward_target, script_steer_toward_target, 0},
    {FN_actor_script_op_thrust_to_centre, actor_script_op_thrust_to_centre, 0},
    {FN_actor_script_op_random_speed_nudge, actor_script_op_random_speed_nudge, 0},
    {FN_actor_script_op_end_frame, script_end_frame, 0},
};

#define SCRIPT_CLASS_ARM_COUNT (sizeof SCRIPT_CLASS_ARMS / sizeof SCRIPT_CLASS_ARMS[0])
#define SCRIPT_EXT_ARM_COUNT (sizeof SCRIPT_EXT_ARMS / sizeof SCRIPT_EXT_ARMS[0])

static unsigned run_script_arm(uint8_t *image, uint32_t actor, uint8_t opcode, uint32_t address,
                               const struct script_arm *arms, unsigned count) {
    for (unsigned i = 0; i < count; i++) {
        if (arms[i].address != address)
            continue;
        if (arms[i].run_with_opcode)
            return arms[i].run_with_opcode(image, actor, opcode);
        if (arms[i].run)
            return arms[i].run(image, actor);
        break;               /* an arm with neither pointer runs nothing, as `struct
                              * actor_handler_entry`'s zero `run` does */
    }
    return CARRY_CLEAR;      /* an address the map does not hold — see the section note */
}

/* actor_script_op_ext @ 0x14cce — opcode class 7's second dispatch, on bits 3..6.
 *
 * It is `jsr (a0)` + `rts`, so the sub-handler's carry is its own answer and nothing is added. */
unsigned actor_script_op_ext(uint8_t *image, uint32_t actor, uint8_t opcode) {
    uint32_t handler = jump_table_entry(image, A_script_op_ext_table, script_operand(opcode));

    return run_script_arm(image, actor, opcode, handler, SCRIPT_EXT_ARMS, SCRIPT_EXT_ARM_COUNT);
}

/* actor_script_op_fire @ 0x14d88 — opcode class 4: point the actor at the player and steer.
 *
 * The two stores are the STEERED-SHOT block include/weapon.h names: the target is the player's own
 * entity index and the operand becomes the most the heading may move per turn. It then calls
 * `entity_steer_toward_target` and ends `andi #$fe,ccr` — this actor's frame is over. */
#define PLAYER_ENTITY_INDEX 0x11u  /* `move.b #$11,26(a2)`; A_entity_table + 0x11 * 0x2c is the ship */

unsigned actor_script_op_fire(uint8_t *image, uint32_t actor, uint8_t opcode) {
    image[actor + SHOT_TARGET_INDEX] = PLAYER_ENTITY_INDEX;
    image[actor + SHOT_MAX_TURN] = script_operand(opcode);
    entity_steer_toward_target(image, actor);
    return CARRY_CLEAR;
}

/* Fetch bytes from the actor's script until one is an opcode, storing the delays on the way. The
 * pc is written back ONLY once an opcode is found, and it is a SIGNED word offset from the script
 * base (`move.w 34(a2),d0 / ext.l d0 / add.l #$19ac2,d0`). */
static void script_fetch_next_opcode(uint8_t *image, uint32_t actor) {
    uint32_t pc = addr_add(A_actor_script_data,
                           sign_ext16(be16(image + actor + ACTOR_SCRIPT_PC)));

    image[actor + ACTOR_SCRIPT_DELAY] = SCRIPT_DELAY_RELOAD;
    for (;;) {
        uint8_t byte = image[pc];

        pc = addr_add(pc, 1);
        if ((byte & SCRIPT_BYTE_IS_DELAY) == 0) {
            image[actor + ACTOR_BOUNCED] = 0;
            image[actor + ACTOR_SCRIPT_OPCODE] = byte;
            wr16(image + actor + ACTOR_SCRIPT_PC, (uint16_t)(pc - A_actor_script_data));
            return;
        }
        image[actor + ACTOR_SCRIPT_DELAY] = (uint8_t)(byte & SCRIPT_DELAY_MASK);
    }
}

/* actor_script_run @ 0x14c66 — one actor's frame of script.
 *
 * The `bcs` at the bottom goes back to the ROUTINE'S FIRST INSTRUCTION, not to the dispatch, so a
 * handler answering "continue" ticks the delay again before the next opcode runs. That is why this
 * is a loop over the whole body rather than over the dispatch alone.
 *
 * The decrement is STORED BEFORE IT IS TESTED, and the arm that puts it back is the one a delay of
 * 0 takes: `subq.b` wraps it to 0xff, `bpl` fails, and `addq.b #1` restores the 0 — so a stalled
 * actor re-runs its current opcode for ever rather than counting down through the whole byte. */
void actor_script_run(uint8_t *image, uint32_t actor) {
    for (;;) {
        uint8_t delay = (uint8_t)(image[actor + ACTOR_SCRIPT_DELAY] - 1);
        uint8_t opcode;
        uint32_t handler;

        image[actor + ACTOR_SCRIPT_DELAY] = delay;
        if (delay == 0)
            script_fetch_next_opcode(image, actor);
        else if ((int8_t)delay < 0)
            image[actor + ACTOR_SCRIPT_DELAY] = (uint8_t)(delay + 1);

        opcode = image[actor + ACTOR_SCRIPT_OPCODE];
        handler = jump_table_entry(image, A_script_op_table,
                                   (uint8_t)(opcode & SCRIPT_CLASS_MASK));
        if (!run_script_arm(image, actor, opcode, handler, SCRIPT_CLASS_ARMS,
                            SCRIPT_CLASS_ARM_COUNT))
            return;
    }
}

/* Register map for the three above: A2 = the actor record, D1.b = the opcode where one is read.
 * `actor_script_op_ext` and `actor_script_op_fire` answer in the CARRY, so their glue stores the
 * `Scc` byte; `actor_script_run` consumes every such flag itself and has none to hand back. */
void g_actor_script_op_ext(uint8_t *image, uint32_t actor, uint32_t opcode_reg,
                           uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_op_ext(image, actor, (uint8_t)opcode_reg));
}

void g_actor_script_op_fire(uint8_t *image, uint32_t actor, uint32_t opcode_reg,
                            uint32_t carry_out) {
    store_flag(image, carry_out, actor_script_op_fire(image, actor, (uint8_t)opcode_reg));
}

void g_actor_script_run(uint8_t *image, uint32_t actor) {
    actor_script_run(image, actor);
}

/* ================================================================================================
 * enemy_move_scripted @ 0x14c16 — the move handler both scripted actor types share.
 *
 * Entries 0x14 and 0x16 of A_actor_move_table are the same address. While the boss is in the
 * playfield the script runs whatever the actor's x is; otherwise an actor outside the keep band is
 * despawned instead, crediting its squadron.
 * ============================================================================================= */
void enemy_move_scripted(uint8_t *image, uint32_t actor) {
    /* The original re-reads the record for the second compare; nothing between them can write it. */
    int16_t x = (int16_t)be16(image + actor + ENTITY_X);

    if (image[A_boss_sequence_active] == 0 && (x <= ACTOR_KILL_X || x >= ACTOR_KEEP_X_MAX)) {
        actor_despawn(image, actor);
        return;
    }
    actor_script_run(image, actor);
    actor_clamp_y(image, actor);
}

/* Register map: A2 = the actor record. No outputs but memory. */
void g_enemy_move_scripted(uint8_t *image, uint32_t actor) {
    enemy_move_scripted(image, actor);
}

/* ================================================================================================
 * enemies_move_all @ 0x1487c — the frame's movement pass over the same eleven actor records.
 *
 * `enemies_animate_all`'s twin: the same alive test, the same SIGNED `cmpi.b #$32` type guard and
 * the same "read the handler out of the image" dispatch, against A_actor_move_table. Two
 * differences, neither observable here: it flips no phase byte, and it keeps a slot INDEX in D6
 * alongside the record pointer — which none of the six shipped handlers reads. The only routine
 * that would is 0x148ca, and nothing anywhere calls that (STATUS.md keeps its dead-code row).
 *
 * IT DISPATCHES THROUGH THE ANIMATION MAP TOO, and that is transcription rather than generosity.
 * A_actor_move_table holds 23 longwords and A_actor_anim_table is the 24th onward — one array read
 * two ways — while this routine's guard admits every type below 0x32. So a type of 0x17..0x2d takes
 * its target from the ANIMATION table, and nine of those slots hold animation handlers, which take
 * exactly the arguments a move handler does. Only 0x2e..0x31 reach past both, into the script class
 * table, whose handlers have another shape entirely; that is this pass's unreconstructed edge and
 * STATUS.md is its home.
 * ============================================================================================= */
#define FN_enemy_move_type14_sine 0x1494au
#define FN_enemy_move_type15_dive 0x149d2u
#define FN_enemy_move_type16_left 0x1499eu
#define FN_enemy_move_type17_left 0x14ec4u
#define FN_enemy_move_scripted    0x14c16u

static const struct actor_handler_entry ACTOR_MOVE_HANDLERS[] = {
    {FN_actor_handler_none, 0},
    {FN_enemy_move_type14_sine, enemy_move_type14_sine},
    {FN_enemy_move_type15_dive, enemy_move_type15_dive},
    {FN_enemy_move_type16_left, enemy_move_type16_left},
    {FN_enemy_move_type17_left, enemy_move_type17_left},
    {FN_enemy_move_scripted, enemy_move_scripted},
};

#define ACTOR_MOVE_HANDLER_COUNT (sizeof ACTOR_MOVE_HANDLERS / sizeof ACTOR_MOVE_HANDLERS[0])

static const struct actor_handler_map MOVE_PASS_MAPS[] = {
    {ACTOR_MOVE_HANDLERS, ACTOR_MOVE_HANDLER_COUNT},
    {ACTOR_ANIM_HANDLERS, ACTOR_ANIM_HANDLER_COUNT},   /* the types past the move table */
};

#define MOVE_PASS_MAP_COUNT (sizeof MOVE_PASS_MAPS / sizeof MOVE_PASS_MAPS[0])

void enemies_move_all(uint8_t *image) {
    uint32_t record = A_enemy_shot_slots;

    for (unsigned slot = 0; slot < ACTOR_UPDATE_SLOTS; slot++) {
        run_actor_handler(image, record, A_actor_move_table, MOVE_PASS_MAPS,
                          MOVE_PASS_MAP_COUNT);
        record = next_record(record);
    }
}

/* Register map: no register inputs. A2 walks the records, D6 counts the slot index and D7 the
 * passes; all three are saved across the `jsr` and restored. */
void g_enemies_move_all(uint8_t *image) {
    enemies_move_all(image);
}

/* ================================================================================================
 * The enemy shots — spawn_enemy_shot @ 0x11a2c and the two per-frame tickers.
 *
 * Three shot slots (entity slots 6..8, at A_enemy_shot_slots) serve all eight wave enemies. Three
 * kinds go into them: a plain AIMED shot (type 0x0c) that flies the angle it was launched on, a
 * HOMING one (0x0a) and a SEEKER (0x0b), the last two steered every frame by the shared
 * `entity_steer_toward_target` and retired by their own time-to-live in ENTITY_ANIM_FRAME.
 * ============================================================================================= */
#define ENEMY_SHOT_SLOTS 3            /* `move.w #$2,d7` + `dbf`, once for the launch scan and
                                       * once for the tick pass */
#define ENEMY_SHOT_MIN_X 0x50         /* `cmpi.w #$50,0(a1)` + `blt` — a SIGNED word compare: an
                                       * enemy left of this fires nothing */
#define ENEMY_HOMING_CHANCE 0x32      /* `cmp.w #$32,d0` + `bge` — the second flag bit halves the
                                       * homing chance again, and a draw of 0..0x31 keeps it */
#define ENEMY_AIM_LEAD 0x0e           /* the player's y is nudged UP by this while the angle is
                                       * taken, then put back — enemy fire leads the ship */
#define ENEMY_SHOT_SPEED 4
#define ENEMY_SHOT_ROWS 8
#define ENEMY_SHOT_TYPE_AIMED 0x0cu
#define ENEMY_SHOT_TYPE_HOMING 0x0au
#define ENEMY_SHOT_TYPE_SEEKER 0x0bu
#define ENEMY_SHOT_AIMED_FRAME 1      /* the aimed shot has no ticker, so this is an anim frame */
#define ENEMY_SHOT_STEERED_TTL 0x64u  /* ...while both steered kinds count this down to nothing */
#define ENEMY_HOMING_TURN_PERIOD 6
#define ENEMY_STEERED_MAX_TURN 1
#define ENEMY_SEEKER_COOLDOWN 6       /* frames before another seeker may be launched */
#define ENEMY_SEEKER_ROWS 0x0bu
#define ENEMY_SEEKER_TURN_PERIOD 2
#define ENEMY_SEEKER_SPEED 2
#define ENEMY_SEEKER_HEADING 0x30u    /* a fixed launch direction — the seeker takes no aim */
#define ENEMY_FIRE_BIT_STEERED 1      /* `btst #1,42(a1)` — this enemy may launch a steered shot */
#define ENEMY_FIRE_BIT_HALVED 2       /* `btst #2,42(a1)` — ...but only ENEMY_HOMING_CHANCE often */

/* The signed byte SHOT_SPEED holds, as `entity_set_velocity_from_angle`'s `ext.w d1` reads it. */
static int16_t shot_speed(const uint8_t *image, uint32_t shot) {
    return (int16_t)(int8_t)image[shot + SHOT_SPEED];
}

/* Copy the firing enemy's position into the shot and take the angle to the player, with the
 * player's own y temporarily raised by ENEMY_AIM_LEAD across the measurement. */
static uint16_t aim_shot_at_player(uint8_t *image, uint32_t player, uint32_t firing_enemy,
                                   uint32_t shot) {
    uint16_t angle;

    wr16(image + player + ENTITY_Y, (uint16_t)(be16(image + player + ENTITY_Y) - ENEMY_AIM_LEAD));
    wr16(image + shot + ENTITY_X, be16(image + firing_enemy + ENTITY_X));
    wr16(image + shot + ENTITY_Y, be16(image + firing_enemy + ENTITY_Y));
    angle = angle_to_target(image, shot, player);
    wr16(image + player + ENTITY_Y, (uint16_t)(be16(image + player + ENTITY_Y) + ENEMY_AIM_LEAD));
    return angle;
}

/* The plain aimed shot @ 0x11a7a — it flies the launch angle and is never steered again, so it
 * stores no heading and no turn block. */
static void launch_aimed_shot(uint8_t *image, uint32_t player, uint32_t firing_enemy,
                              uint32_t shot) {
    uint16_t angle;

    image[shot + SHOT_SPEED] = ENEMY_SHOT_SPEED;
    angle = aim_shot_at_player(image, player, firing_enemy, shot);
    entity_set_velocity_from_angle(image, shot, angle, shot_speed(image, shot));
    image[shot + ENTITY_ALIVE] = 1;
    image[shot + ENTITY_TYPE] = ENEMY_SHOT_TYPE_AIMED;
    wr16(image + shot + ENTITY_HEIGHT, ENEMY_SHOT_ROWS);
    image[shot + ENTITY_ANIM_FRAME] = ENEMY_SHOT_AIMED_FRAME;
    wr32(image + shot + ENTITY_SPRITE, A_shot_sprite_aimed);
}

/* The homing missile @ 0x11acc — the aimed shot plus the steered-shot block include/weapon.h names,
 * so `entity_steer_toward_target` can turn it towards the player every ENEMY_HOMING_TURN_PERIOD. */
static void launch_homing_shot(uint8_t *image, uint32_t player, uint32_t firing_enemy,
                               uint32_t shot) {
    uint16_t angle;

    image[shot + SHOT_TARGET_INDEX] = PLAYER_ENTITY_INDEX;
    image[shot + SHOT_SPEED] = ENEMY_SHOT_SPEED;
    angle = aim_shot_at_player(image, player, firing_enemy, shot);
    image[shot + SHOT_HEADING] = (uint8_t)angle;
    entity_set_velocity_from_angle(image, shot, angle, shot_speed(image, shot));
    image[shot + ENTITY_ALIVE] = 1;
    image[shot + ENTITY_TYPE] = ENEMY_SHOT_TYPE_HOMING;
    wr16(image + shot + ENTITY_HEIGHT, ENEMY_SHOT_ROWS);
    image[shot + ENTITY_ANIM_FRAME] = ENEMY_SHOT_STEERED_TTL;
    wr32(image + shot + ENTITY_SPRITE, A_shot_sprite_homing);
    image[shot + SHOT_TURN_PERIOD] = ENEMY_HOMING_TURN_PERIOD;
    image[shot + SHOT_MAX_TURN] = ENEMY_STEERED_MAX_TURN;
    image[shot + SHOT_TURN_COUNTDOWN] = image[shot + SHOT_TURN_PERIOD];
}

/* The seeker @ 0x11b3a — the slow drifting kind, on its own global cooldown and launched only
 * while the ship is at or left of the firing enemy. It takes NO aim: the heading is a literal and
 * `entity_set_velocity_from_angle` is given that same literal rather than a measured angle. */
static void launch_seeker_shot(uint8_t *image, uint32_t player, uint32_t firing_enemy,
                               uint32_t shot) {
    if (image[A_enemy_seeker_cooldown] != 0)
        return;
    image[A_enemy_seeker_cooldown] = ENEMY_SEEKER_COOLDOWN;
    if ((int16_t)be16(image + player + ENTITY_X) > (int16_t)be16(image + firing_enemy + ENTITY_X))
        return;

    image[shot + SHOT_TARGET_INDEX] = PLAYER_ENTITY_INDEX;
    wr16(image + shot + ENTITY_X, be16(image + firing_enemy + ENTITY_X));
    wr16(image + shot + ENTITY_Y, be16(image + firing_enemy + ENTITY_Y));
    image[shot + ENTITY_ALIVE] = 1;
    image[shot + ENTITY_TYPE] = ENEMY_SHOT_TYPE_SEEKER;
    wr16(image + shot + ENTITY_HEIGHT, ENEMY_SEEKER_ROWS);
    wr32(image + shot + ENTITY_SPRITE, A_shot_sprite_seeker);
    image[shot + SHOT_TURN_PERIOD] = ENEMY_SEEKER_TURN_PERIOD;
    image[shot + SHOT_SPEED] = ENEMY_SEEKER_SPEED;
    image[shot + SHOT_MAX_TURN] = ENEMY_STEERED_MAX_TURN;
    image[shot + SHOT_TURN_COUNTDOWN] = image[shot + SHOT_TURN_PERIOD];
    image[shot + SHOT_HEADING] = ENEMY_SEEKER_HEADING;
    image[shot + ENTITY_ANIM_FRAME] = ENEMY_SHOT_STEERED_TTL;
    /* The original also does `movea.l a0,a1` here; `entity_set_velocity_from_angle` reads no A1,
     * so the copy is dead and there is nothing to transcribe but this note. */
    entity_set_velocity_from_angle(image, shot, ENEMY_SEEKER_HEADING, shot_speed(image, shot));
}

/* Whether a steered shot is what this enemy launches, and how hard that is: the flags byte's first
 * bit admits the class at all, its second makes the launch a ENEMY_HOMING_CHANCE-in-0x100 draw, and
 * the type must additionally be in the homing class map. */
static unsigned enemy_launches_homing(uint8_t *image, uint32_t firing_enemy) {
    if ((image[firing_enemy + ACTOR_FIRE_FLAGS] & (1u << ENEMY_FIRE_BIT_STEERED)) == 0)
        return 0;
    /* `&&` short-circuits exactly where the original's `beq` branches past the draw. */
    if ((image[firing_enemy + ACTOR_FIRE_FLAGS] & (1u << ENEMY_FIRE_BIT_HALVED)) != 0
        && (rand16(image) & 0xff) >= ENEMY_HOMING_CHANCE)
        return 0;
    return entity_type_in_mask(image, A_enemy_types_fire_homing,
                               image[firing_enemy + ENTITY_TYPE]);
}

void spawn_enemy_shot(uint8_t *image, uint32_t player, uint32_t firing_enemy, uint32_t shot,
                      unsigned want_seeker) {
    if (want_seeker) {
        launch_seeker_shot(image, player, firing_enemy, shot);
        return;
    }
    if ((int16_t)be16(image + firing_enemy + ENTITY_X) < ENEMY_SHOT_MIN_X)
        return;
    if (enemy_launches_homing(image, firing_enemy))
        launch_homing_shot(image, player, firing_enemy, shot);
    else
        launch_aimed_shot(image, player, firing_enemy, shot);
}

/* Register map: A0 = the player record, A1 = the firing enemy, A2 = the free shot slot, D3.b = the
 * kind the caller's class tests chose (non-zero = a seeker). No outputs but memory. */
void g_spawn_enemy_shot(uint8_t *image, uint32_t player, uint32_t firing_enemy, uint32_t shot,
                        uint32_t kind_reg) {
    spawn_enemy_shot(image, player, firing_enemy, shot, (uint8_t)kind_reg != 0);
}

/* enemy_shot_tick_type0a @ 0x11bde / enemy_shot_tick_type0b @ 0x11bbc — the two steered kinds'
 * per-frame step. Identical but for what expiry does: the homing shot simply stops being alive,
 * while the seeker becomes a ground-impact puff. */
static void enemy_shot_steer_and_move(uint8_t *image, uint32_t shot) {
    entity_steer_toward_target(image, shot);
    entity_kill_if_offscreen(image, shot);
}

void enemy_shot_tick_type0a(uint8_t *image, uint32_t shot) {
    image[shot + ENTITY_ANIM_FRAME]--;
    if (image[shot + ENTITY_ANIM_FRAME] == 0) {
        image[shot + ENTITY_ALIVE] = 0;
        return;
    }
    enemy_shot_steer_and_move(image, shot);
}

void enemy_shot_tick_type0b(uint8_t *image, uint32_t shot) {
    image[shot + ENTITY_ANIM_FRAME]--;
    if (image[shot + ENTITY_ANIM_FRAME] == 0) {
        enemy_morph_to_type6(image, shot);
        return;
    }
    enemy_shot_steer_and_move(image, shot);
}

/* Register map for both: A2 = the shot record. No outputs but memory. */
void g_enemy_shot_tick_type0a(uint8_t *image, uint32_t shot) {
    enemy_shot_tick_type0a(image, shot);
}

void g_enemy_shot_tick_type0b(uint8_t *image, uint32_t shot) {
    enemy_shot_tick_type0b(image, shot);
}

/* ================================================================================================
 * enemy_fire_and_update_shots @ 0x11906 — one frame of enemy fire.
 *
 * It picks ONE of the eight wave records at random, decides whether that enemy fires, drops a shot
 * into the first free slot if it does, and then ticks all three slots whatever happened.
 *
 * ELEVEN INSTRUCTIONS OF THIS ROUTINE ARE DEAD, at 0x119ba..0x119d8: they sit past an unconditional
 * `bra`, nothing anywhere branches to them, and they would have written a second shape of shot
 * record (a word at ACTOR_SPAWN_TAG, the position pair, alive, and D2 masked to 0x7ff into
 * ENTITY_HP). They are left out rather than transcribed, and STATUS.md records that.
 * ============================================================================================= */
#define ENEMY_SLOT_PICK_MASK 7u        /* `and.w #$7,d0` — which of the eight wave records fires */
#define ENEMY_FIRE_ROLL_MASK 3u        /* `and.w #$3,d0` — only one frame in four even tries */
#define ENEMY_FIRE_CHANCE_SHIFT 4      /* `lsr.l #4,d0` ... */
#define ENEMY_FIRE_CHANCE_MASK 0x1fu   /* ...`and.w #$1f,d0`: the draw the section's chance must beat */
#define ENTITY_EXPLODING_BIT 7         /* `btst #7,d2` on the alive byte */

/* THE CHANCE TABLE'S INDEX KEEPS THE CALLER'S OWN HIGH BYTE. The section is loaded with `move.b`
 * into D1 and the very next instruction indexes with `d1.w`, so the word offset is
 * (caller's D1 & 0xff00) | section — an `ext.w` the routine never makes. Faithful, and the reason
 * this core takes a register rather than nothing. */
static unsigned enemy_fire_chance_passes(uint8_t *image, uint32_t chance_index_register) {
    uint16_t draw = (uint16_t)((rand16(image) >> ENEMY_FIRE_CHANCE_SHIFT) & ENEMY_FIRE_CHANCE_MASK);
    uint16_t index = set_low_byte((uint16_t)chance_index_register, image[A_level_section]);
    int16_t chance =
        (int16_t)(int8_t)image[addr_add(A_enemy_fire_chance_table, sign_ext16(index))];

    return chance >= (int16_t)draw;
}

/* Does this enemy fire this frame, and with which kind? The boss encounter bypasses both the flags
 * byte and the per-section chance entirely — while A_mothership_ready is set, every pick that names
 * a firing type fires. */
static unsigned enemy_wants_to_fire(uint8_t *image, uint32_t firing_enemy,
                                    uint32_t chance_index_register, unsigned *want_seeker) {
    uint8_t alive;

    if (image[A_mothership_ready] == 0) {
        if (image[firing_enemy + ACTOR_FIRE_FLAGS] == 0)
            return 0;
        if ((rand16(image) & ENEMY_FIRE_ROLL_MASK) != 0)
            return 0;
        if (!enemy_fire_chance_passes(image, chance_index_register))
            return 0;
    }

    if (entity_type_in_mask(image, A_enemy_types_fire_seeker, image[firing_enemy + ENTITY_TYPE]))
        *want_seeker = 1;
    else if (entity_type_in_mask(image, A_enemy_types_can_fire, image[firing_enemy + ENTITY_TYPE]))
        *want_seeker = 0;
    else
        return 0;

    alive = image[firing_enemy + ENTITY_ALIVE];
    return alive != 0 && (alive & (1u << ENTITY_EXPLODING_BIT)) == 0;
}

/* One shot slot's frame: the two steered kinds have their own tickers and everything else just
 * drifts and is retired off the edges. */
static void enemy_shot_tick(uint8_t *image, uint32_t shot) {
    if (image[shot + ENTITY_ALIVE] == 0)
        return;
    if (image[shot + ENTITY_TYPE] == ENEMY_SHOT_TYPE_SEEKER) {
        enemy_shot_tick_type0b(image, shot);
        return;
    }
    if (image[shot + ENTITY_TYPE] == ENEMY_SHOT_TYPE_HOMING) {
        enemy_shot_tick_type0a(image, shot);
        return;
    }
    entity_apply_velocity(image, shot);
    entity_kill_if_offscreen(image, shot);
}

void enemy_fire_and_update_shots(uint8_t *image, uint32_t chance_index_register) {
    uint32_t firing_enemy = addr_add(A_enemy_slots,
                                     (rand16(image) & ENEMY_SLOT_PICK_MASK) * ENTITY_STRIDE);
    unsigned want_seeker = 0;
    uint32_t shot = A_enemy_shot_slots;

    if (enemy_wants_to_fire(image, firing_enemy, chance_index_register, &want_seeker)) {
        for (unsigned slot = 0; slot < ENEMY_SHOT_SLOTS; slot++) {
            if (image[shot + ENTITY_ALIVE] == 0) {
                spawn_enemy_shot(image, A_player_record, firing_enemy, shot, want_seeker);
                break;
            }
            shot = next_record(shot);
        }
    }

    shot = A_enemy_shot_slots;
    for (unsigned slot = 0; slot < ENEMY_SHOT_SLOTS; slot++) {
        enemy_shot_tick(image, shot);
        shot = next_record(shot);
    }
}

/* Register map: D1 in = the register the level section's byte is loaded into, whose HIGH BYTE
 * survives into the chance table's word index (see enemy_fire_chance_passes). A0/A1/A2 are loaded
 * by the routine itself and D0/D2/D3/D7 are scratch. No outputs but memory. */
void g_enemy_fire_and_update_shots(uint8_t *image, uint32_t chance_index_reg) {
    enemy_fire_and_update_shots(image, chance_index_reg);
}

/* ================================================================================================
 * The three spawn-script opcodes and the squadron ticker.
 *
 * All four fill free records at A_enemy_slots and all but the last claim a SQUADRON — one of the
 * six counters at A_squadron_kill_counters, marked with how many kills clear it again. A squadron
 * whose counter is non-zero is taken, which is what stops two waves sharing one.
 * ============================================================================================= */
#define SQUADRON_COUNT 6              /* `move.w #$5,d3` + `dbf` over A_squadron_kill_counters */
#define WAVE_SCRIPT_RECORD_BYTES 4    /* `lea 4(a4),a4` — the script's fixed record width */
#define GROUND_SCRIPT_Y_OFFSET 2      /* `lea 2(a4),a4` before the `move.w (a4)+` */

/* `lea $198bb,a0 / move.w #$5,d3 / tst.b (a0)+ / beq` — the index of the first counter at zero, or
 * failure. Every spawner below opens with it. */
static unsigned first_free_squadron(const uint8_t *image, unsigned *squadron) {
    for (unsigned i = 0; i < SQUADRON_COUNT; i++) {
        if (image[A_squadron_kill_counters + i] == 0) {
            *squadron = i;
            return 1;
        }
    }
    return 0;
}

/* wavescript_spawn_trio_type0e @ 0x13898 — attack-script opcode 0x0b: three sine patrollers.
 *
 * The three share a squadron and are spread out in BOTH senses — their centre lines step by a
 * random amount and their sine phases by a fifth of a turn — so they fly one behind another rather
 * than as a column. */
#define TRIO_MIN_FREE_SLOTS 4      /* `cmpi.b #$4,$198b7` + `blt` — a SIGNED byte compare */
#define TRIO_ACTORS 3
#define TRIO_SPAWN_X 0x190
#define TRIO_ROWS 9
#define TRIO_Y_STEP_MASK 0x1fu     /* `and.w #$1f,d0` ... */
#define TRIO_Y_STEP_BASE 0x19      /* ...`add.w #$19,d0`: the gap between the three centre lines */
#define TRIO_FIRST_BASE_Y 0x68     /* `move.w #$68,d1 / sub.w d0,d1` — the first one's centre */
#define TRIO_PHASE_STEP 0x50       /* `add.w #$50,d2` */
#define TRIO_TYPE 0x0eu            /* move-table entry 0x0e is enemy_move_type14_sine */
#define TRIO_SPAWN_TAG 2
#define TRIO_SQUADRON_MARK 3       /* three kills clear the squadron again */

void wavescript_spawn_trio_type0e(uint8_t *image, uint32_t cursor) {
    unsigned squadron;
    uint16_t step, base_y, phase;
    uint32_t record = A_enemy_slots;
    uint8_t remaining = TRIO_ACTORS;

    wr32(image + A_wave_script_cursor, addr_add(cursor, WAVE_SCRIPT_RECORD_BYTES));
    count_free_wave_slots(image);
    if ((int8_t)image[A_free_wave_slot_count] < TRIO_MIN_FREE_SLOTS)
        return;
    if (!first_free_squadron(image, &squadron))
        return;

    step = (uint16_t)((rand16(image) & TRIO_Y_STEP_MASK) + TRIO_Y_STEP_BASE);
    base_y = (uint16_t)(TRIO_FIRST_BASE_Y - step);
    phase = 0;
    for (unsigned slot = 0; slot < ENEMY_SLOT_COUNT; slot++) {
        if (image[record + ENTITY_ALIVE] == 0) {
            remaining--;
            wr16(image + record + ENTITY_X, TRIO_SPAWN_X);
            wr16(image + record + ACTOR_SINE_PHASE, phase);
            wr16(image + record + ACTOR_SINE_BASE_Y, base_y);
            image[record + ACTOR_SPAWN_TAG] = TRIO_SPAWN_TAG;
            wr32(image + record + ENTITY_SPRITE, A_wave_trio_sprite);
            wr16(image + record + ENTITY_HEIGHT, TRIO_ROWS);
            image[record + ENTITY_ALIVE] = 1;
            image[record + ENTITY_SQUADRON] = (uint8_t)squadron;
            image[record + ENTITY_ANIM_FRAME] = 1;
            image[record + ENTITY_TYPE] = TRIO_TYPE;
            base_y = (uint16_t)(base_y + step);
            phase = (uint16_t)(phase + TRIO_PHASE_STEP);
            if (remaining == 0)
                break;
        }
        record = next_record(record);
    }
    image[addr_add(A_squadron_kill_counters, squadron)] = TRIO_SQUADRON_MARK;
}

/* Register map: A4 = the script cursor, which is advanced past this record and republished to
 * A_wave_script_cursor. D0..D5 are scratch and A0/A2 are loaded here. No outputs but memory. */
void g_wavescript_spawn_trio_type0e(uint8_t *image, uint32_t cursor) {
    wavescript_spawn_trio_type0e(image, cursor);
}

/* groundscript_spawn_type10 @ 0x13958 and groundscript_spawn_type0f @ 0x13a12 — one ground actor
 * each, at the y the script names. The two differ in the actor type they write and in the extra
 * `clr.b` the type-0x0f arm makes: its move handler is the diver at 0x149d2, and that byte is
 * ACTOR_DIVING, so a fresh type-0x0f is spawned with its dive UNARMED.
 *
 * THE FREE-SLOT GUARD IS NOT ONE. `bsr count_free_wave_slots` + `beq` reads as "return when no slot
 * is free", but `count_free_wave_slots` ends `movea.l (a7)+,a0 / move.l (a7)+,d7 / rts` and it is
 * that last MOVE that sets the flags — so the `beq` tests the RESTORED D7, whose low word this
 * routine has just loaded with the scripted y plus GROUND_SPAWN_Y_BIAS and whose high word is the
 * caller's. The routine therefore returns only when that whole longword is zero, and spawns for
 * every other y. Every other caller of 0x13828 in the game re-tests D0 or the published global
 * explicitly; these two do not. Transcribed as written, which is why the core takes the register. */
#define GROUND_SPAWN_X 0x180
#define GROUND_SPAWN_Y_BIAS 0x20      /* `add.w #$20,d7` */
#define GROUND_ACTOR_HP 2
#define GROUND_ACTOR_ROWS 0x10
#define GROUND_ACTOR_SPAWN_TAG 1
#define GROUND_SQUADRON_MARK 1
#define GROUND_TYPE_WALKER 0x10u      /* move-table entry 0x10 is enemy_move_type16_left */
#define GROUND_TYPE_DIVER 0x0fu       /* ...and 0x0f is enemy_move_type15_dive */
#define GROUND_RND_PARAM_MASK 0x1fu   /* `and.b #$1f,d0`, redrawn until non-zero */

static void groundscript_spawn(uint8_t *image, uint32_t cursor, uint32_t y_register,
                               uint8_t actor_type, unsigned clear_dive_flag) {
    uint32_t scripted_y_at = addr_add(cursor, GROUND_SCRIPT_Y_OFFSET);
    uint32_t spawn_y = set_low_word(y_register,
                                    (uint16_t)(be16(image + scripted_y_at) + GROUND_SPAWN_Y_BIAS));
    uint32_t record = A_enemy_slots;
    unsigned squadron;
    uint8_t draw;

    wr32(image + A_ground_script_cursor, addr_add(scripted_y_at, 2));
    count_free_wave_slots(image);
    if (spawn_y == 0)
        return;
    if (!first_free_squadron(image, &squadron))
        return;

    for (unsigned slot = 0; slot < ENEMY_SLOT_COUNT; slot++) {
        if (image[record + ENTITY_ALIVE] == 0) {
            wr16(image + record + ENTITY_X, GROUND_SPAWN_X);
            wr16(image + record + ENTITY_Y, (uint16_t)spawn_y);
            image[record + ENTITY_HP] = GROUND_ACTOR_HP;
            image[record + ACTOR_SPAWN_TAG] = GROUND_ACTOR_SPAWN_TAG;
            wr32(image + record + ENTITY_SPRITE, A_ground_actor_sprite);
            wr16(image + record + ENTITY_HEIGHT, GROUND_ACTOR_ROWS);
            image[record + ENTITY_ALIVE] = 1;
            image[record + ENTITY_SQUADRON] = (uint8_t)squadron;
            image[record + ENTITY_TYPE] = actor_type;
            if (clear_dive_flag)
                image[record + ACTOR_DIVING] = 0;
            image[record + ENTITY_ANIM_FRAME] = 1;
            break;
        }
        record = next_record(record);
    }
    image[addr_add(A_squadron_kill_counters, squadron)] = GROUND_SQUADRON_MARK;
    do
        draw = (uint8_t)(rand16(image) & GROUND_RND_PARAM_MASK);
    while (draw == 0);
    image[A_ground_spawn_rnd_param] = draw;
}

void groundscript_spawn_type10(uint8_t *image, uint32_t cursor, uint32_t y_register) {
    groundscript_spawn(image, cursor, y_register, GROUND_TYPE_WALKER, 0);
}

void groundscript_spawn_type0f(uint8_t *image, uint32_t cursor, uint32_t y_register) {
    groundscript_spawn(image, cursor, y_register, GROUND_TYPE_DIVER, 1);
}

/* Register map for both: A4 = the ground-script cursor, D7 = the register the scripted y is read
 * into — its high word is the caller's and the guard above tests the whole longword. */
void g_groundscript_spawn_type10(uint8_t *image, uint32_t cursor, uint32_t y_reg) {
    groundscript_spawn_type10(image, cursor, y_reg);
}

void g_groundscript_spawn_type0f(uint8_t *image, uint32_t cursor, uint32_t y_reg) {
    groundscript_spawn_type0f(image, cursor, y_reg);
}

/* squadron_spawn_tick @ 0x13af2 — the asteroid columns' own spawner.
 *
 * Gated on A_squadron_spawn_enabled, which the level event script sets and clears, and paced by a
 * countdown it reloads with a fresh random period WHETHER OR NOT it found a group to fill. The
 * three routines names.txt reaches at 0x13b56 / 0x13b72 / 0x13bae are not helpers at all: each is
 * the target of a `bra` inside this body, and nothing calls them. See STATUS.md.
 * ============================================================================================= */
#define ASTEROID_GROUP_BYTES (ASTEROID_COLUMNS * ENTITY_STRIDE)   /* `lea 132(a3),a3` */
#define SQUADRON_SPAWN_X 0x140
#define SQUADRON_SPAWN_X_STEP 0x10
#define SQUADRON_SPAWN_Y_MASK 0x7fu
#define SQUADRON_SPAWN_Y_BASE 0x20
#define SQUADRON_FLAG_DRAW_MASK 7u    /* both flags are drawn from three bits of one word... */
#define SQUADRON_FLAG_DRAW_EDGE 4     /* ...and split at the middle, in OPPOSITE senses */
#define SQUADRON_RELOAD_MASK 0xfu
#define SQUADRON_RELOAD_BASE 7

/* The first group whose three columns are ALL dead, as `or.b` over their alive bytes finds it. */
static unsigned first_dead_asteroid_group(const uint8_t *image, uint32_t *group) {
    uint32_t record = A_asteroid_records;

    *group = A_asteroid_records;
    for (unsigned g = 0; g < ASTEROID_GROUPS; g++) {
        uint8_t any_alive = 0;

        for (unsigned column = 0; column < ASTEROID_COLUMNS; column++) {
            any_alive |= image[record + ENTITY_ALIVE];
            record = next_record(record);
        }
        if (any_alive == 0)
            return 1;
        *group = addr_add(*group, ASTEROID_GROUP_BYTES);
    }
    return 0;
}

static void fill_asteroid_group(uint8_t *image, uint32_t group) {
    uint8_t descending = ((rand16(image) >> 2) & SQUADRON_FLAG_DRAW_MASK) < SQUADRON_FLAG_DRAW_EDGE;
    uint8_t slow = ((rand16(image) >> 1) & SQUADRON_FLAG_DRAW_MASK) >= SQUADRON_FLAG_DRAW_EDGE;
    uint16_t y = (uint16_t)((rand16(image) & SQUADRON_SPAWN_Y_MASK) + SQUADRON_SPAWN_Y_BASE);
    uint16_t x = SQUADRON_SPAWN_X;

    for (unsigned column = 0; column < ASTEROID_COLUMNS; column++) {
        image[group + ENTITY_ALIVE] = 1;
        wr16(image + group + ENTITY_X, x);
        wr16(image + group + ENTITY_Y, y);
        image[group + ASTEROID_Y_DESCENDING] = descending;
        image[group + ASTEROID_SLOW] = slow;
        image[group + ENTITY_ANIM_FRAME] = 0;
        x = (uint16_t)(x + SQUADRON_SPAWN_X_STEP);
        group = next_record(group);
    }
}

void squadron_spawn_tick(uint8_t *image) {
    uint32_t group;

    if (image[A_squadron_spawn_enabled] == 0)
        return;
    image[A_squadron_spawn_countdown]--;
    if (image[A_squadron_spawn_countdown] != 0)
        return;

    if (first_dead_asteroid_group(image, &group))
        fill_asteroid_group(image, group);
    image[A_squadron_spawn_countdown] =
        (uint8_t)((rand16(image) & SQUADRON_RELOAD_MASK) + SQUADRON_RELOAD_BASE);
}

/* Register map: no register inputs. A2/A3 walk the columns, D0..D3 and D6/D7 are scratch. */
void g_squadron_spawn_tick(uint8_t *image) {
    squadron_spawn_tick(image);
}

/* ================================================================================================
 * spawn_formation @ 0x14a7c — the wave spawner every attack script and the boss go through.
 *
 * It reads a FORMATION RECORD out of A_formation_table, builds one 0x2c-byte actor at
 * A_actor_spawn_template from that record's graphics attributes and its caller's arguments, and
 * then copies that template into as many free wave slots as the record asks for, giving each its
 * own position offset and its own script start delay.
 *
 * THE FORMATION INDEX SURVIVES IN THE HIGH BYTE OF TWO LATER VALUES, and that is not cosmetic. The
 * index is shifted into D7 (`lsl.w #2`) and the record's count and kind bytes are then dropped into
 * the LOW BYTE of that same word (`move.b (a1)+,d7`), so both carry `(index * 4) >> 8` above them.
 * For an index below 0x40 that byte is zero and the two readings agree; the boss reaches here with
 * a byte out of A_mothership_formation_by_section, which is not bounded to 0x3f by anything. Both
 * are modelled as the registers they are.
 * ============================================================================================= */
/* `lsl.w #2` — one longword per entry in either of the two POINTER tables spawn_formation reads:
 * A_formation_table's record pointers and A_actor_script_table's script pointers. Not
 * JUMP_TABLE_ENTRY_BYTES above, which is the same width over a table of ENTRY POINTS. */
#define POINTER_TABLE_ENTRY_BYTES 4u
#define FORMATION_FLAGS 1u              /* byte 1 of the record; byte 0 is skipped unread */
#define FORMATION_COUNT 2u              /* byte 2: how many actors to place */
#define FORMATION_KIND_IN_BYTE3 0x80u   /* ...and when byte 1 carries this bit... */
#define FORMATION_KIND 3u               /* ...byte 3 is the kind and byte 4 is skipped as well */
#define FORMATION_BODY_SHORT 3u         /* where the per-actor bytes start without that bit... */
#define FORMATION_BODY_LONG 5u          /* ...and with it */

#define FORMATION_ATTRS_BYTES 8u        /* `lsl.w #3,d7` — the graphics-attribute record's stride */
#define FORMATION_ATTRS_SPEED 2u        /* +2, HIGH nibble (`lsr.b #4`) -> ACTOR_SPEED */
#define FORMATION_ATTRS_ACCEL_X 3u      /* +3 -> the low byte of ENTITY_AX */
#define FORMATION_ATTRS_ACCEL_Y 4u      /* +4 -> the low byte of ENTITY_AY */
#define FORMATION_ATTRS_SPEED_SHIFT 4

#define SPAWN_TEMPLATE_ROWS 0x10u
/* `move.b #$7f,$17a8a` — class 7, ext operand 15, i.e. actor_script_op_end_frame: a freshly spawned
 * actor does nothing at all on its first frame and starts its script on the next one. */
#define ACTOR_SCRIPT_OPCODE_INITIAL 0x7fu
#define SPAWN_STAGGER_FIRST 1           /* `move.w #$1,d2` — the first actor's script delay */
#define SPAWN_RANDOM_Y 0xffu            /* `cmp.b #$ff,d0` on the y offset byte... */
#define SPAWN_RANDOM_Y_MASK 0x7fu       /* ...replaces it with a fresh draw in this band */
#define SPAWN_RANDOM_Y_BASE 0x28

/* The 0x2c bytes every actor of this formation starts from: cleared, then the fields that do not
 * vary between them. `attrs` is the graphics-attribute record the kind resolved to. */
static void build_spawn_template(uint8_t *image, uint32_t attrs, uint8_t actor_type,
                                 unsigned squadron, uint8_t fire_flags, uint32_t sprite) {
    uint32_t record = A_actor_spawn_template;

    for (unsigned i = 0; i < ENTITY_STRIDE; i++)
        image[record + i] = 0;
    image[record + SHOT_TARGET_INDEX] = PLAYER_ENTITY_INDEX;
    image[record + ACTOR_SPEED] =
        (uint8_t)(image[attrs + FORMATION_ATTRS_SPEED] >> FORMATION_ATTRS_SPEED_SHIFT);
    /* Only the LOW byte of each acceleration word is written, over the zero the clear left. */
    image[record + ENTITY_AX + 1] = image[attrs + FORMATION_ATTRS_ACCEL_X];
    image[record + ENTITY_AY + 1] = image[attrs + FORMATION_ATTRS_ACCEL_Y];
    image[record + ENTITY_ALIVE] = 1;
    wr16(image + record + ENTITY_HEIGHT, SPAWN_TEMPLATE_ROWS);
    image[record + ENTITY_SQUADRON] = (uint8_t)squadron;
    image[record + ENTITY_ANIM_FRAME] = 1;
    wr32(image + record + ENTITY_SPRITE, sprite);
    image[record + ENTITY_TYPE] = actor_type;
    image[record + ACTOR_SCRIPT_OPCODE] = ACTOR_SCRIPT_OPCODE_INITIAL;
    image[record + ACTOR_FIRE_FLAGS] = fire_flags;
}

/* Where this kind's script starts, as the word offset ACTOR_SCRIPT_PC holds: the pointer table's
 * entry less the script base. The index is masked to a byte (`and.l #$ff,d6`), so the high byte the
 * section note describes cannot reach this one. */
static uint16_t formation_script_pc(const uint8_t *image, uint8_t kind) {
    uint32_t entry = addr_add(A_actor_script_table, (uint32_t)kind * POINTER_TABLE_ENTRY_BYTES);

    return (uint16_t)(be32(image + entry) - A_actor_script_data);
}

void spawn_formation(uint8_t *image, uint16_t formation, uint8_t actor_type, uint16_t base_x,
                     uint16_t base_y, uint8_t fire_flags, uint32_t sprite) {
    uint16_t index_register = (uint16_t)(formation * POINTER_TABLE_ENTRY_BYTES);
    uint32_t record, cursor, counter;
    uint16_t count_register, kind_register;
    uint8_t flags, kind, stagger_step, stagger;
    unsigned squadron, passes;

    if (count_free_wave_slots(image) == 0)
        return;
    if (!first_free_squadron(image, &squadron))
        return;
    counter = addr_add(A_squadron_kill_counters, squadron);

    record = be32(image + addr_add(A_formation_table, sign_ext16(index_register)));
    flags = image[record + FORMATION_FLAGS];
    count_register = set_low_byte(index_register, image[record + FORMATION_COUNT]);
    if (flags & FORMATION_KIND_IN_BYTE3) {
        kind_register = set_low_byte(index_register, image[record + FORMATION_KIND]);
        cursor = addr_add(record, FORMATION_BODY_LONG);
    } else {
        kind_register = set_low_byte(index_register, flags);
        cursor = addr_add(record, FORMATION_BODY_SHORT);
    }
    kind = (uint8_t)kind_register;

    build_spawn_template(image,
                         addr_add(A_formation_gfx_attrs,
                                  sign_ext16((uint16_t)(kind_register * FORMATION_ATTRS_BYTES))),
                         actor_type, squadron, fire_flags, sprite);

    stagger_step = image[cursor];
    cursor = addr_add(cursor, 1);
    stagger = SPAWN_STAGGER_FIRST;
    /* `subq.l #1,d7` then `dbf d7`: the pushed count word is the pass count, and a count of 0 walks
     * the whole word rather than placing nothing. */
    passes = loop_passes(count_register, COUNT_MASK_WORD);
    for (unsigned actor = 0; actor < passes; actor++) {
        uint32_t slot = 0;      /* the failing arm never reads it — `bcs` leaves at once */
        uint16_t y;

        if (enemy_alloc_slot(image, &slot) != CARRY_CLEAR)
            return;
        image[counter]++;
        for (unsigned i = 0; i < ENTITY_STRIDE; i++)
            image[slot + i] = image[A_actor_spawn_template + i];

        wr16(image + slot + ACTOR_SCRIPT_PC, formation_script_pc(image, kind));
        image[slot + ACTOR_SCRIPT_DELAY] = stagger;
        stagger = (uint8_t)(stagger + stagger_step);

        /* The x offset is a SIGNED byte off the caller's base; the y offset is an UNSIGNED one. */
        wr16(image + slot + ENTITY_X, (uint16_t)(sign_ext8(image[cursor]) + base_x));
        cursor = addr_add(cursor, 1);
        y = image[cursor];
        cursor = addr_add(cursor, 1);
        y = (y == SPAWN_RANDOM_Y)
            ? (uint16_t)((rand16(image) & SPAWN_RANDOM_Y_MASK) + SPAWN_RANDOM_Y_BASE)
            : (uint16_t)(y + base_y);
        wr16(image + slot + ENTITY_Y, y);
    }
}

/* Register map: D7.w in = the formation index, D1.b = the actor type, D3.w / D4.w = the base x and
 * y, D5.b = the fire flags, A5 = the sprite pointer. D3 and D4 are saved at entry and restored just
 * before the placement loop, which is how the squadron scan can use D4 as scratch in between. */
void g_spawn_formation(uint8_t *image, uint32_t formation_reg, uint32_t type_reg, uint32_t base_x,
                       uint32_t base_y, uint32_t flags_reg, uint32_t sprite) {
    spawn_formation(image, (uint16_t)formation_reg, (uint8_t)type_reg, (uint16_t)base_x,
                    (uint16_t)base_y, (uint8_t)flags_reg, sprite);
}

/* ================================================================================================
 * wavescript_spawn_wave @ 0x13868 — the attack script's default opcode.
 *
 * Four instructions of its own: advance the cursor, turn the opcode's bits 4 and 5 into the fire
 * flags every spawned actor gets, and TAIL-CALL spawn_formation with the opcode's low nibble as the
 * formation and 0x180 as the base x. (The `rts` at 0x13896 sits past that `bra.w` and is
 * unreachable; there is nothing to transcribe.)
 * ============================================================================================= */
#define WAVE_OPCODE_FORMATION_MASK 0xfu  /* `and.w #$f,d7` */
#define WAVE_OPCODE_FIRE_BIT 4           /* `btst #4,d7` */
#define WAVE_OPCODE_HOMING_BIT 5         /* `btst #5,d7`, tested only when bit 4 is set */
#define WAVE_FIRE_FLAGS_AIMED 1          /* `moveq #$1,d5` — ACTOR_FIRE_FLAGS' plain-shot value */
#define WAVE_FIRE_FLAGS_STEERED 3        /* `moveq #$3,d5` — ...and with the steered bit as well */
#define WAVE_SPAWN_X 0x180               /* `move.w #$180,d3` */
#define WAVE_SPAWN_Y_MASK 0xffu          /* `and.w #$ff,d6` */

void wavescript_spawn_wave(uint8_t *image, uint32_t cursor, uint16_t opcode, uint16_t base_y,
                           uint8_t actor_type, uint32_t sprite) {
    uint8_t fire_flags = 0;

    wr32(image + A_wave_script_cursor, addr_add(cursor, WAVE_SCRIPT_RECORD_BYTES));
    if (opcode & (1u << WAVE_OPCODE_FIRE_BIT)) {
        fire_flags = WAVE_FIRE_FLAGS_AIMED;
        if (opcode & (1u << WAVE_OPCODE_HOMING_BIT))
            fire_flags = WAVE_FIRE_FLAGS_STEERED;
    }
    spawn_formation(image, (uint16_t)(opcode & WAVE_OPCODE_FORMATION_MASK), actor_type,
                    WAVE_SPAWN_X, (uint16_t)(base_y & WAVE_SPAWN_Y_MASK), fire_flags, sprite);
}

/* Register map: A4 = the script cursor, D7.w = the opcode, D6.w = the base y, D1.b = the actor
 * type, A5 = the sprite pointer. D3, D4, D5 and D7 are OUTPUTS to the tail call rather than to the
 * caller, so the glue has nothing to store beyond what spawn_formation writes. */
void g_wavescript_spawn_wave(uint8_t *image, uint32_t cursor, uint32_t opcode_reg,
                             uint32_t base_y_reg, uint32_t type_reg, uint32_t sprite) {
    wavescript_spawn_wave(image, cursor, (uint16_t)opcode_reg, (uint16_t)base_y_reg,
                          (uint8_t)type_reg, sprite);
}
