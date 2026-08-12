/* behavior.c — the per-actor BEHAVIOUR tier's foundation.
 *
 * `actor_behavior_pass` ($8d0) walks the actor table once a frame and `actor_dispatch_behavior`
 * ($928) tail-jumps through WB_ACTOR_BEHAVIOR_TABLE on each live record's WB_ACTOR_TYPE. Behind
 * those two are 61 distinct handlers; behind the handlers are the thirteen shared leaves, the spawn
 * animation and the two overlap tests in this file. See behavior.h for the interface and
 * ../PORTABILITY.md §0k for why none of it was measured until batch 28.
 *
 * THE DISPATCH IS ON THE WRAPPED OFFSET, which is batch 27's lesson applied to a bigger table.
 * `lsl.w #2,d1` wraps inside 16 bits and `lea (0x938,PC,d1.w),a1` then adds the result
 * SIGN-EXTENDED, so what selects the entry is the OFFSET and not the index: types $4000..$403d,
 * $8000..$803d and $c000..$c03d alias onto slots 0..61 exactly as 0..61 do, and 248 of the 65,536
 * type values dispatch a table entry. A guard on the raw type would silently refuse 186 types the
 * original dispatches ported code for. Only an offset that genuinely LEAVES the table is refused,
 * and that refusal is a refusal: the original reads a longword outside the table and `jmp`s to it,
 * and no C stands in for that (the same refusal src/blit.c's sprite_dispatch and src/scene.c's
 * scene_run_exit_action make).
 *
 * EVERY COMPARISON HERE IS A SIGNED 16-BIT ONE OF THE OPERANDS, not a test of the wrapped
 * difference — `cmp.w` + `blt`/`bgt` read N xor V (docs/m68k-disassembly.md) — while every ADD and
 * SUBTRACT really does wrap into the value the following compare reads. The (int16_t) casts below
 * are where the two rules meet.
 */
#include <stddef.h>
#include <stdint.h>

#include "actor.h"
#include "behavior.h"
#include "bus.h"
#include "machine.h"
#include "map.h"
#include "rng.h"
#include "wonderboy.h"

/* --- reading and writing a record -----------------------------------------------------------------
 *
 * A record address is a 68000 ADDRESS REGISTER and nothing here bounds one: `actor_behavior_pass`
 * follows a table pointer out of memory, and every leaf below is entered with a record, a frame list
 * or a band record its CALLER supplied. So no field address is known to be inside the image before
 * it is used, and every access — read AND write, byte and word — goes through bus.h. Guarding only
 * the reads would be worse than guarding neither: the address the routine refused to trust for a
 * read would be trusted for a store, and a store past the image leaves the buffer entirely where the
 * 68000 side merely reaches an address the shim drops.
 */
static int16_t field_w(const uint8_t *image, uint32_t record, uint32_t offset) {
    return (int16_t)bus_read_word(image, addr_add(record, offset));
}

static uint8_t field_b(const uint8_t *image, uint32_t record, uint32_t offset) {
    return bus_read_byte(image, addr_add(record, offset));
}

static void set_field_w(uint8_t *image, uint32_t record, uint32_t offset, uint16_t value) {
    bus_write_word(image, addr_add(record, offset), value);
}

static void set_field_b(uint8_t *image, uint32_t record, uint32_t offset, uint8_t value) {
    bus_write_byte(image, addr_add(record, offset), value);
}

static int flag_is_set(const uint8_t *image, uint32_t record, uint32_t offset, unsigned bit) {
    return (field_b(image, record, offset) & (1u << bit)) != 0;
}

/* `bset`/`bclr`/`bchg #n,d16(An)` are BYTE read-modify-writes on memory whatever the register form
 * is, which is what these three reproduce. */
static void flag_set(uint8_t *image, uint32_t record, uint32_t offset, unsigned bit) {
    set_field_b(image, record, offset,
                (uint8_t)(field_b(image, record, offset) | (1u << bit)));
}

static void flag_clear(uint8_t *image, uint32_t record, uint32_t offset, unsigned bit) {
    set_field_b(image, record, offset,
                (uint8_t)(field_b(image, record, offset) & ~(1u << bit)));
}

static void flag_flip(uint8_t *image, uint32_t record, uint32_t offset, unsigned bit) {
    set_field_b(image, record, offset,
                (uint8_t)(field_b(image, record, offset) ^ (1u << bit)));
}

/* `tst.b d0` on what the two map probes leave in d0: only the LOW BYTE decides. */
static int step_was_blocked(uint32_t step_outcome) {
    return (uint8_t)step_outcome == WB_ACTOR_STEP_BLOCKED;
}

/* The `btst #3,8(a0)` every routine in this file opens with, and the direction it names: SET means
 * the followed record is to the actor's LEFT (actor.h, $67c2). */
static int faces_left(const uint8_t *image, uint32_t actor) {
    return flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
}

/* One map probe in the direction a flag names, with the ground flags the caller has no use for
 * dropped — six routines here take a step and none of them reads d1. */
static uint32_t step_left(uint8_t *image, uint32_t actor, uint32_t step) {
    uint32_t ground = 0;
    return actor_step_left_against_map(image, actor, step, &ground);
}

static uint32_t step_right(uint8_t *image, uint32_t actor, uint32_t step) {
    uint32_t ground = 0;
    return actor_step_right_against_map(image, actor, step, &ground);
}


/* --- $698a: the animation every spawned record plays --------------------------------------------
 *
 * THE CURSOR IS A BYTE OFFSET, not an index — `lea 0(a1,d0.w),a1` on WB_ACTOR_FIELD_18 — and the
 * wrap is `andi.w #$1f`, so it reaches byte offsets 0..30, i.e. the FIRST SIXTEEN words of the
 * table. The 32 bytes above them ($69de..$69fd, up to actor_damage_followed's own entry) have no
 * reader anywhere in the image: `lea $69be.l` at $6994 is the only reference to any address in the
 * table, and nothing computes one. Batch 28 registered "what reads the second half"; the answer is
 * nothing, and that is recorded rather than the table being trimmed.
 */
void actor_spawn_anim_step(uint8_t *image, uint32_t actor) {
    uint8_t cursor = field_b(image, actor, WB_ACTOR_FIELD_18);
    uint16_t frame = bus_read_word(image, addr_add(WB_ACTOR_SPAWN_ANIM_FRAMES, cursor));

    set_field_w(image, actor, WB_ACTOR_SPRITE, frame);

    /* `addi.w #$2,d0 / andi.w #$1f,d0` is a WORD step over a register holding a BYTE, and the
     * `addq.b #2` that commits it is a byte one — so a cursor of $ff advances to $01 while the
     * wrap test sees $101 masked to 1, and the two agree. */
    if ((uint16_t)(((uint16_t)cursor + WB_ACTOR_ANIM_FRAME_BYTES) & WB_ACTOR_SPAWN_ANIM_MASK)
        != 0) {
        set_field_b(image, actor, WB_ACTOR_FIELD_18,
                    (uint8_t)(cursor + WB_ACTOR_ANIM_FRAME_BYTES));
        return;
    }
    flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_SPAWNED_BIT);
    set_field_b(image, actor, WB_ACTOR_FIELD_18, 0);
}


/* --- $928 and $8d0: the dispatch, and the walk that feeds it ------------------------------------ */

/* $a36 — two bytes, and both of the slots that hold it are reconstructed by this doing nothing. */
void actor_behavior_null(uint8_t *image, uint32_t actor) {
    (void)image;
    (void)actor;
}

/* THE TARGET IS FETCHED, not transcribed. The original is `movea.l (a1),a1 / jmp (a1)` — it reads
 * the longword out of the image — so this reads it too, through bus.h like every other computed
 * address. Carrying a compile-time copy of the 62 entries would have been a third spelling of a
 * table the image already holds and ../names.txt already names, and it would have made a POKED
 * table (which the original follows) dispatch the entry the copy remembered.
 *
 * What this port does have is the list of targets it has a RECONSTRUCTION for, keyed by the ADDRESS
 * rather than by the slot — because the slot is not what the original jumps through. One row today;
 * a later batch adds a row and touches nothing else. Both slot 0 and slot 58 hold
 * WB_ACTOR_BEHAVIOR_NULL, so one row covers two slots by construction.
 *
 * test/test_behavior.py pins the image's own 62 longwords against ../names.txt entry by entry, and
 * drives one differential per slot through the arithmetic below. */
typedef struct {
    uint32_t target;
    void (*handler)(uint8_t *image, uint32_t actor);
} BehaviorHandler;

static const BehaviorHandler PORTED_HANDLERS[] = {
    {WB_ACTOR_BEHAVIOR_NULL, actor_behavior_null},
};

static const BehaviorHandler *ported_handler(uint32_t target) {
    for (size_t row = 0; row < sizeof PORTED_HANDLERS / sizeof PORTED_HANDLERS[0]; row++) {
        if (PORTED_HANDLERS[row].target == target)
            return &PORTED_HANDLERS[row];
    }
    return NULL;
}

uint32_t actor_dispatch_behavior(uint8_t *image, uint32_t actor) {
    uint16_t type = (uint16_t)field_w(image, actor, WB_ACTOR_TYPE);
    /* Unsigned, so a sign-extended NEGATIVE offset is huge here and fails the same bound. */
    uint32_t offset = sign_ext16((uint16_t)(type * WB_ACTOR_BEHAVIOR_ENTRY));
    const BehaviorHandler *ported;
    uint32_t target;

    if (offset >= WB_ACTOR_BEHAVIOR_SLOTS * WB_ACTOR_BEHAVIOR_ENTRY)
        return WB_ACTOR_DISPATCH_REFUSED;

    target = bus_read_long(image, addr_add(WB_ACTOR_BEHAVIOR_TABLE, offset));
    ported = ported_handler(target);
    if (ported == NULL)
        return target;
    ported->handler(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}

/* One record of the walk: the free check the ordinary loop and the first two fixed slots share. */
static uint32_t dispatch_unless_free(uint8_t *image, uint32_t record) {
    if (field_w(image, record, WB_ACTOR_X) == (int16_t)WB_ACTOR_FREE_MARKER)
        return WB_ACTOR_DISPATCH_RAN;
    return actor_dispatch_behavior(image, record);
}

/* $904 — the arm WB_STATE_FLAG_A34 selects: not a walk at all but THREE FIXED RECORDS, slot 0, slot
 * 1 and then WB_ACTOR_BEHAVIOR_FIXED_SKIP further on, which lands exactly on
 * WB_ACTOR_FOLLOWED_SLOT. It never looks at WB_ACTOR_TABLE_END, so a table shorter than thirteen
 * records is walked into regardless.
 *
 * AND THE THIRD DISPATCH IS UNCONDITIONAL. The first two are guarded by `cmpi.w #$ffbe,(a0) / beq`;
 * the third is `lea 352(a0),a0 / bra.w $928` with no test at all, so a FREE followed slot is
 * dispatched on whatever WB_ACTOR_TYPE its 32 bytes happen to hold. (Batch 28's plate said all
 * three were guarded and that the third was slot 13; both are corrected here from the bytes.) */
static uint32_t behavior_pass_fixed_three(uint8_t *image, uint32_t table) {
    uint32_t boundary = dispatch_unless_free(image, table);

    if (boundary != WB_ACTOR_DISPATCH_RAN)
        return boundary;

    uint32_t second = addr_add(table, WB_ACTOR_RECORD_BYTES);
    boundary = dispatch_unless_free(image, second);
    if (boundary != WB_ACTOR_DISPATCH_RAN)
        return boundary;

    return actor_dispatch_behavior(image, addr_add(second, WB_ACTOR_BEHAVIOR_FIXED_SKIP));
}

/* THE WALK HAS NO BOUND IN THE ORIGINAL and one here, which is the one place this file is not the
 * original. `cmpi.l #$ffffffff,(a0)` is the only exit, so a table with no terminator spins until
 * the machine is reset — and once the cursor leaves the loaded image every read is answered with
 * zero (bus.h), which is neither the terminator nor the free marker, so it dispatches slot 0 for
 * ever. The cursor's stride divides the 24-bit bus exactly, so after WB_ACTOR_WALK_BUS_CYCLE steps
 * it has returned to an address it has already read, and stopping there reports the runaway instead
 * of hanging the suite. The oracle's own instruction cap fires long before, so no differential can
 * tell the two apart.
 *
 * THE PREMISE THE CAP RESTS ON, named because it will expire. "Already read" is only "already read
 * WITH THE SAME ANSWER" while every handler the walk dispatches writes nothing — which is true today
 * because the one reconstructed handler is `actor_behavior_null`. The FIRST ported handler that
 * writes a record makes the loop mutate what it is walking, and the cap stops being a proof of
 * non-termination and becomes a safety bound. That is still the right thing to do (the alternative
 * is hanging), but it is a different claim, and it is why the runaway has a code of its own rather
 * than sharing the dispatcher's refusal. */
uint32_t actor_behavior_pass(uint8_t *image) {
    uint32_t record = be32(image + WB_ACTOR_TABLE_SELECTED);

    if (be16(image + WB_STATE_FLAG_A34) != 0)
        return behavior_pass_fixed_three(image, record);

    for (uint32_t step = 0; step < WB_ACTOR_WALK_BUS_CYCLE; step++) {
        if (bus_read_long(image, record) == WB_ACTOR_TABLE_END)
            return WB_ACTOR_DISPATCH_RAN;

        uint32_t boundary = dispatch_unless_free(image, record);
        if (boundary != WB_ACTOR_DISPATCH_RAN)
            return boundary;

        record = addr_add(record, WB_ACTOR_RECORD_BYTES);
    }
    return WB_ACTOR_DISPATCH_UNBOUNDED;
}


/* --- the shared leaves --------------------------------------------------------------------------
 *
 * $2f22, $2fce and $2fe8 are three spellings of "probe the map in the direction a flag names", and
 * they are three bodies rather than one because they disagree: $2f22 does not touch the side flag
 * before stepping and flips it afterwards, $2fce faces first and steps TOWARD, and $2fe8 faces first
 * and steps AWAY. The last is the one whose plate was wrong — the two arms of its `btst` are the
 * other way round from $2fce's, which is the whole of the difference between the two bodies.
 */
void actor_step_facing(uint8_t *image, uint32_t actor, uint32_t step) {
    uint32_t outcome = faces_left(image, actor) ? step_left(image, actor, step)
                                                : step_right(image, actor, step);

    /* `bchg #3,8(a0)` — the same eight bytes src/actor.c's `flip_side_flag` reproduces, spelt here
     * because this is a different routine and the two share no code. */
    if (step_was_blocked(outcome))
        flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
}

void actor_face_and_step_toward(uint8_t *image, uint32_t actor, uint32_t step) {
    actor_set_side_flag(image, actor);
    if (faces_left(image, actor))
        step_left(image, actor, step);
    else
        step_right(image, actor, step);
}

void actor_face_and_step_away4(uint8_t *image, uint32_t actor) {
    actor_set_side_flag(image, actor);
    if (faces_left(image, actor))
        step_right(image, actor, WB_ACTOR_STEP_AWAY_PIXELS);
    else
        step_left(image, actor, WB_ACTOR_STEP_AWAY_PIXELS);
}

/* $2f86 — the countdown, and what running out does. The relaunch is
 * `actor_start_motion_at_speed`'s three flag writes with the speed spelt inline (the shape
 * `actor_turn_and_launch` also has), plus a cursor reset, and it happens only for a SUPPORTED
 * record that `rng_next` gives permission to: one bit of the generator's word decides.
 *
 * NOTE THE RELOAD RUNS FIRST. WB_ACTOR_FIELD_30 is reloaded before the SUPPORTED test, so a record
 * that is not supported still gets a fresh countdown — the reload is the timer's, not the launch's. */
void actor_tick_timer30(uint8_t *image, uint32_t actor) {
    uint8_t timer = field_b(image, actor, WB_ACTOR_FIELD_30);

    if (timer != 0) {
        set_field_b(image, actor, WB_ACTOR_FIELD_30, (uint8_t)(timer - 1));
        return;
    }
    set_field_b(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TIMER30_RELOAD);

    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT))
        return;

    /* `btst #2,d0` is a LONGWORD test of a data register, but rng_next writes only d0's LOW WORD
     * and the bit read here is in it — so neither the generator's untouched high half nor the
     * caller's can reach the test, which is why 0 is handed in rather than an entry register this
     * routine's two callers would have to carry. src/rng.c's own draw passes 0 for that reason. */
    if ((rng_next(image, 0) & (1u << WB_ACTOR_TIMER30_RNG_BIT)) != 0)
        return;

    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT);
    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_LAUNCHED_BIT);
    flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
    set_field_b(image, actor, WB_ACTOR_SPEED, WB_ACTOR_TIMER30_SPEED);
    set_field_b(image, actor, WB_ACTOR_FIELD_18, 0);
}

/* $3006 — `list_pair` is two longwords and WB_ACTOR_FLAG_SIDE_BIT picks one: (a1) while it is SET,
 * 4(a1) while it is clear. The list is terminated by a NEGATIVE word, which is read one word PAST
 * the frame just published — so the last frame of a list is shown and then the cursor is zeroed,
 * and the terminator is never itself published. */
void actor_anim_step_facing_list(uint8_t *image, uint32_t actor, uint32_t list_pair) {
    uint32_t list = bus_read_long(image, faces_left(image, actor)
                                             ? list_pair
                                             : addr_add(list_pair, WB_ACTOR_ANIM_LIST_ENTRY));
    uint8_t cursor = field_b(image, actor, WB_ACTOR_FIELD_18);
    uint32_t frame = addr_add(list, cursor);

    set_field_w(image, actor, WB_ACTOR_SPRITE, bus_read_word(image, frame));

    if ((int16_t)bus_read_word(image, addr_add(frame, WB_ACTOR_ANIM_FRAME_BYTES)) < 0)
        set_field_b(image, actor, WB_ACTOR_FIELD_18, 0);
    else
        set_field_b(image, actor, WB_ACTOR_FIELD_18,
                    (uint8_t)(cursor + WB_ACTOR_ANIM_FRAME_BYTES));
}

void actor_select_sprite_by_flag(uint8_t *image, uint32_t actor) {
    uint16_t sprite = WB_ACTOR_SPRITE_IDLE;

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT))
        sprite = WB_ACTOR_SPRITE_SUPPORTED;
    else if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT))
        sprite = WB_ACTOR_SPRITE_MOVING;

    set_field_w(image, actor, WB_ACTOR_SPRITE, sprite);
}

/* $5a3c — eighteen bytes, and both of its registers are the caller's: `frame` is the word to publish
 * and `cursor` the byte offset to advance. `addi.b` and `andi.b` write only the LOW BYTE of d0, so
 * the caller's upper three bytes come back untouched, which is what the return reproduces. */
uint32_t actor_advance_anim16(uint8_t *image, uint32_t actor, uint32_t frame, uint32_t cursor) {
    uint8_t stepped = (uint8_t)(((uint8_t)cursor + WB_ACTOR_ANIM_FRAME_BYTES)
                                & WB_ACTOR_ANIM16_MASK);

    set_field_w(image, actor, WB_ACTOR_SPRITE, bus_read_word(image, frame));
    set_field_b(image, actor, WB_ACTOR_FIELD_18, stepped);
    return (cursor & ~0xffu) | stepped;
}

/* $6840 — a HOMING step, and the one routine in this file that writes both coordinate words. Each
 * axis moves `step` pixels toward the followed record's, with the vertical one aimed at
 * WB_ACTOR_PLATFORM_TOP ABOVE its y rather than at it — the same ride height $6d70 snaps to, which
 * is what says the two are about the same geometry. Both `add.w`/`sub.w` wrap in sixteen bits. */
void actor_step_toward_followed(uint8_t *image, uint32_t actor, uint32_t step) {
    uint32_t followed = followed_actor_record(image);
    uint16_t x = (uint16_t)field_w(image, actor, WB_ACTOR_X);
    int16_t target_y;
    uint16_t y;

    set_field_w(image, actor, WB_ACTOR_X,
                (uint16_t)((int16_t)x > field_w(image, followed, WB_ACTOR_X)
                           ? x - (uint16_t)step : x + (uint16_t)step));

    /* The vertical half re-reads BOTH records after the horizontal store, exactly where $6854 does:
     * a caller that handed in a record overlapping the followed one would see the first write in
     * the second comparison, and the original would too. */
    target_y = (int16_t)(field_w(image, followed, WB_ACTOR_Y) - WB_ACTOR_PLATFORM_TOP);
    y = (uint16_t)field_w(image, actor, WB_ACTOR_Y);
    set_field_w(image, actor, WB_ACTOR_Y,
                (uint16_t)((int16_t)y > target_y ? y - (uint16_t)step : y + (uint16_t)step));
}

/* $6872 — the WB_ACTOR_ANIM_5160_FRAMES stepper with a relaunch in front of it.
 *
 * THE COUNTDOWN STOPS ON WB_ACTOR_ANIM_5160_HOLD, NOT ON ZERO: `cmpi.b #$1,30(a0) / beq` skips the
 * whole arm while the byte already holds it, so the launch fires on the tick that takes it from 2
 * to 1 and never again — and the speed the record launches at is that same 1. A byte of 0 is not
 * the stop value, so it wraps to $ff and counts the long way round. */
void actor_relaunch_and_anim_5160(uint8_t *image, uint32_t actor) {
    uint8_t timer = field_b(image, actor, WB_ACTOR_FIELD_30);
    uint8_t cursor;
    uint32_t frame;

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT)
        && timer != WB_ACTOR_ANIM_5160_HOLD) {
        timer = (uint8_t)(timer - 1);
        set_field_b(image, actor, WB_ACTOR_FIELD_30, timer);
        set_field_b(image, actor, WB_ACTOR_SPEED, timer);
        flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
        flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT);
        flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_LAUNCHED_BIT);
    }

    cursor = field_b(image, actor, WB_ACTOR_FIELD_18);
    frame = addr_add(WB_ACTOR_ANIM_5160_FRAMES, cursor);
    set_field_w(image, actor, WB_ACTOR_SPRITE, bus_read_word(image, frame));

    /* The advance is committed BEFORE the terminator is read, and the reset then overwrites it —
     * two writes to the same byte on the wrapping path, which is what the original does. */
    set_field_b(image, actor, WB_ACTOR_FIELD_18, (uint8_t)(cursor + WB_ACTOR_ANIM_FRAME_BYTES));
    if (bus_read_word(image, addr_add(frame, WB_ACTOR_ANIM_FRAME_BYTES)) == WB_ACTOR_ANIM_5160_END)
        set_field_b(image, actor, WB_ACTOR_FIELD_18, 0);
}

/* $6d5a — twenty-two bytes ending in `bra.w $67e0`, so the followed record `followed_actor_record`
 * names is this routine's own result. `lsl.w #3` scales inside the WORD and `adda.w d0,a2` then
 * SIGN-EXTENDS what is left, so a WB_ACTOR_HALF_WIDTH of $1000..$1fff addresses BELOW the table and
 * one of $2000 lands back on the table itself — the index wraps twice over, not once. */
uint32_t actor_sprite_from_6ed8(uint8_t *image, uint32_t actor) {
    uint16_t index = (uint16_t)(field_w(image, actor, WB_ACTOR_HALF_WIDTH)
                                * WB_ACTOR_SPRITE_6ED8_STRIDE);
    uint32_t row = addr_add(WB_ACTOR_SPRITE_TABLE_6ED8, sign_ext16(index));

    set_field_w(image, actor, WB_ACTOR_SPRITE, bus_read_word(image, row));
    return followed_actor_record(image);
}

/* --- $6d70 and $6dd8: the moving platform -------------------------------------------------------
 *
 * The band the followed record has to be inside is the caller's, in a2: it starts
 * WB_ACTOR_BAND_LEFT pixels back from the platform's own x and runs WB_ACTOR_BAND_WIDTH pixels on.
 * Both routines compute it the same way, which is the only code they share.
 */
static int followed_is_over_platform(const uint8_t *image, uint32_t actor, uint32_t followed,
                                     uint32_t band) {
    int16_t left = (int16_t)(field_w(image, actor, WB_ACTOR_X)
                             - field_w(image, band, WB_ACTOR_BAND_LEFT));
    int16_t x = field_w(image, followed, WB_ACTOR_X);

    return x >= left && x <= (int16_t)(left + field_w(image, band, WB_ACTOR_BAND_WIDTH));
}

/* $6d70 — catch the followed record onto the platform. The vertical test is one-sided and shallow:
 * the record must be at or below the platform's top and no more than WB_ACTOR_PLATFORM_CATCH
 * pixels below it, which is what stops a record that is under the platform being lifted onto it. */
void actor_platform_carry_followed(uint8_t *image, uint32_t actor, uint32_t followed,
                                   uint32_t band) {
    int16_t top = (int16_t)(field_w(image, actor, WB_ACTOR_Y) - WB_ACTOR_PLATFORM_TOP);
    int16_t below = (int16_t)(field_w(image, followed, WB_ACTOR_Y) - top);

    if (below < 0 || below > (int16_t)WB_ACTOR_PLATFORM_CATCH)
        return;
    if (!followed_is_over_platform(image, actor, followed, band))
        return;

    wr16(image + WB_ACTOR_PLATFORM_RIDDEN, 1);
    flag_set(image, actor, WB_ACTOR_FIELD_22, WB_ACTOR_FIELD_22_RIDING_BIT);

    set_field_w(image, followed, WB_ACTOR_Y, (uint16_t)top);
    flag_set(image, followed, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
    flag_clear(image, followed, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FALLING_BIT);
    flag_clear(image, followed, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT);
    flag_clear(image, followed, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_LAUNCHED_BIT);
    flag_set(image, followed, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_CARRIED_BIT);
    set_field_b(image, followed, WB_ACTOR_SPEED, 0);
}

/* $6dd8 — let it go again. FOUR ways to lose the ride and only one to keep it: the record must still
 * be inside the band, must have neither WB_ACTOR_FLAGS2_LANDED_BIT nor
 * WB_ACTOR_FLAGS2_INVULNERABLE_BIT up, AND must not be moving under its own power. Every other path
 * clears both the record's riding bit and the global word. */
void actor_platform_release_check(uint8_t *image, uint32_t actor, uint32_t followed,
                                  uint32_t band) {
    if (followed_is_over_platform(image, actor, followed, band)
        && !flag_is_set(image, followed, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_LANDED_BIT)
        && !flag_is_set(image, followed, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_INVULNERABLE_BIT)
        && !flag_is_set(image, followed, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT))
        return;

    flag_clear(image, actor, WB_ACTOR_FIELD_22, WB_ACTOR_FIELD_22_RIDING_BIT);
    wr16(image + WB_ACTOR_PLATFORM_RIDDEN, 0);
}

/* $701c — THE SIDE FLAG, THE OTHER WAY ROUND. `actor_set_side_flag` ($67c2) raises the bit while the
 * actor's x is strictly GREATER than the followed record's, i.e. while the followed record is to its
 * LEFT; this raises it while the followed record's x is strictly greater, i.e. while it is to its
 * RIGHT. Two routines eight hundred bytes apart write one bit with opposite meanings, and this one
 * has the two callers. (Batch 28's plate called it "compare and step"; it takes no step at all.) */
void actor_face_followed_reset_22(uint8_t *image, uint32_t actor) {
    uint32_t followed = followed_actor_record(image);

    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
    if (field_w(image, followed, WB_ACTOR_X) <= field_w(image, actor, WB_ACTOR_X))
        flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);

    if (field_b(image, actor, WB_ACTOR_FIELD_22) != 0)
        set_field_b(image, actor, WB_ACTOR_FIELD_22, WB_ACTOR_FIELD_22_HOLD);
}

/* $501a — the ascent of a hop, decelerating by construction: the record rises by its own
 * WB_ACTOR_SPEED and that speed then drops by one, so the rise shortens each frame and ends when the
 * byte reaches zero. The byte is then reset to ONE rather than to zero, so the next hop's first
 * frame lifts a single pixel unless something else seeds it. */
void actor_hop_ascend_step(uint8_t *image, uint32_t actor) {
    uint8_t speed = field_b(image, actor, WB_ACTOR_SPEED);

    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT))
        return;

    /* `sub.w d0,2(a0)` on a zero-extended BYTE: the rise is 0..255 pixels and the word wraps. */
    set_field_w(image, actor, WB_ACTOR_Y,
                (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_Y) - speed));

    speed = (uint8_t)(speed - 1);
    set_field_b(image, actor, WB_ACTOR_SPEED, speed);
    if (speed == 0) {
        flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT);
        set_field_b(image, actor, WB_ACTOR_SPEED, 1);
    }
}


/* --- $5c6e: how the actor's box overlaps the followed record's ----------------------------------
 *
 * THREE INDEPENDENT TESTS INTO THREE BITS, and two of them are gated on the FOLLOWED record's
 * current sprite id — so what the player's animation is showing decides which of them run at all.
 * The actor's box is `x - half_width .. x + half_width` by `y - size_second .. y`, computed once at
 * the top and shared by all three.
 *
 * `clr.w d0` clears only the LOW WORD of the result register, so the caller's upper half comes back
 * untouched; nothing in the image reads it, and ../STATUS.md records that rather than this taking an
 * entry register it would have no way to pin.
 */
typedef struct {
    int16_t left, right, top, bottom;
} ActorBox;

static ActorBox actor_box(const uint8_t *image, uint32_t actor) {
    int16_t x = field_w(image, actor, WB_ACTOR_X);
    int16_t y = field_w(image, actor, WB_ACTOR_Y);
    ActorBox box;

    box.left = (int16_t)(x - field_w(image, actor, WB_ACTOR_HALF_WIDTH));
    box.right = (int16_t)(x + field_w(image, actor, WB_ACTOR_HALF_WIDTH));
    box.top = (int16_t)(y - field_w(image, actor, WB_ACTOR_SIZE_SECOND));
    box.bottom = y;
    return box;
}

static int point_in_box(const ActorBox *box, int16_t x, int16_t y) {
    return x >= box->left && x <= box->right && y >= box->top && y <= box->bottom;
}

/* Bit 0 — a small box in FRONT of the followed record, live only while its sprite is in
 * WB_FOLLOWED_SPRITE_STRIKE_LO..HI. Above WB_FOLLOWED_SPRITE_STRIKE_FLIP the box moves
 * WB_ACTOR_STRIKE_BOX_FLIP pixels the other way, which is the same reach mirrored. */
static int strike_box_overlaps(const uint8_t *image, uint32_t followed, int16_t sprite,
                               const ActorBox *box) {
    int16_t x, near, far, top;

    if (sprite < (int16_t)WB_FOLLOWED_SPRITE_STRIKE_LO
        || sprite > (int16_t)WB_FOLLOWED_SPRITE_STRIKE_HI)
        return 0;

    top = (int16_t)(field_w(image, followed, WB_ACTOR_Y) - WB_ACTOR_STRIKE_BOX_TOP);
    if (box->bottom < top || box->top > (int16_t)(top + WB_ACTOR_STRIKE_BOX_DEPTH))
        return 0;

    x = field_w(image, followed, WB_ACTOR_X);
    near = (int16_t)(x + WB_ACTOR_STRIKE_BOX_NEAR);
    far = (int16_t)(x + WB_ACTOR_STRIKE_BOX_FAR);
    if (sprite > (int16_t)WB_FOLLOWED_SPRITE_STRIKE_FLIP) {
        near = (int16_t)(near - WB_ACTOR_STRIKE_BOX_FLIP);
        far = (int16_t)(far - WB_ACTOR_STRIKE_BOX_FLIP);
    }
    return box->right >= near && box->left <= far;
}

/* Bit 1 — the two footprints. The followed record's is `x - 14(a1) .. x + 14(a1)` by
 * `y - 16(a1) .. y`, the same shape `actor_box` builds, but the four compares are NOT a symmetric
 * overlap: the bottom edge is tested against the ACTOR's bottom rather than its top, which is the
 * asymmetry the original has and this reproduces. */
static int footprints_overlap(const uint8_t *image, uint32_t followed, const ActorBox *box) {
    int16_t x = field_w(image, followed, WB_ACTOR_X);
    int16_t y = field_w(image, followed, WB_ACTOR_Y);

    if ((int16_t)(x - field_w(image, followed, WB_ACTOR_HALF_WIDTH)) > box->right)
        return 0;
    if ((int16_t)(y - field_w(image, followed, WB_ACTOR_SIZE_SECOND)) > box->bottom)
        return 0;
    if ((int16_t)(x + field_w(image, followed, WB_ACTOR_HALF_WIDTH)) < box->left)
        return 0;
    return y >= box->top;
}

/* Bit 2 — ONE POINT, and only for two sprite ids: WB_ACTOR_POINT_RIGHT pixels to the right of the
 * followed record for the first, WB_ACTOR_POINT_FLIP back from there (i.e. the same distance to the
 * LEFT) for the second, and WB_ACTOR_POINT_UP above it for both. */
static int reach_point_in_box(const uint8_t *image, uint32_t followed, int16_t sprite,
                              const ActorBox *box) {
    int16_t x = (int16_t)(field_w(image, followed, WB_ACTOR_X) + WB_ACTOR_POINT_RIGHT);

    if (sprite != WB_FOLLOWED_SPRITE_POINT_LO) {
        if (sprite != WB_FOLLOWED_SPRITE_POINT_HI)
            return 0;
        x = (int16_t)(x - WB_ACTOR_POINT_FLIP);
    }
    return point_in_box(box, x,
                        (int16_t)(field_w(image, followed, WB_ACTOR_Y) - WB_ACTOR_POINT_UP));
}

uint32_t actor_followed_overlap_mask(uint8_t *image, uint32_t actor) {
    uint32_t followed = followed_actor_record(image);
    int16_t sprite = field_w(image, followed, WB_ACTOR_SPRITE);
    ActorBox box = actor_box(image, actor);
    uint32_t mask = 0;

    if (strike_box_overlaps(image, followed, sprite, &box))
        mask |= 1u << WB_ACTOR_OVERLAP_STRIKE_BIT;
    if (footprints_overlap(image, followed, &box))
        mask |= 1u << WB_ACTOR_OVERLAP_BODY_BIT;
    if (reach_point_in_box(image, followed, sprite, &box))
        mask |= 1u << WB_ACTOR_OVERLAP_POINT_BIT;
    return mask;
}


/* --- $23b6: did anything the player threw land on this actor ------------------------------------
 *
 * TWO WAYS IN, and the first is the screen flash. While WB_FLASH_TIMER is running, every actor
 * within WB_ACTOR_FLASH_REACH of the followed record horizontally reports a hit — one test, no
 * projectile, no consumption. The second is the search below.
 *
 * THE SEARCH CONSUMES WHAT IT FINDS. It scans the HIGH allocation pool only
 * (WB_ACTOR_ALLOC_HIGH_FIRST..+HIGH_SLOTS, the six records the low pool cannot reach) for a live
 * record of type WB_ACTOR_SHOT_TYPE_LO..HI whose footprint sum covers the distance to this actor on
 * BOTH axes, and on finding one it FREES that record — except WB_ACTOR_SHOT_TYPE_KEPT, which is
 * stamped with WB_ACTOR_SHOT_HIT_MARK instead and left alive. Either way the scan stops there.
 *
 * THE FINAL `clr.w d7` IS A NO-OP. `moveq #0,d7` at the top already cleared the register and
 * nothing in the loop writes it, so $245e re-clears a word that is already zero — the deliberate
 * dead instruction class ../names.txt records at $7366, reproduced by writing nothing here.
 */
static int footprint_reaches(const uint8_t *image, uint32_t actor, uint32_t other,
                             uint32_t offset, uint32_t extent) {
    int16_t reach = (int16_t)(field_w(image, actor, extent) + field_w(image, other, extent));
    int16_t apart = (int16_t)(field_w(image, other, offset) - field_w(image, actor, offset));

    /* `neg.w d3` on $8000 leaves $8000, so a distance of exactly -32768 stays negative and fails
     * the compare against any reach — the wrap the original has and does not guard. */
    if (apart < 0)
        apart = (int16_t)-apart;
    return apart <= reach;
}

uint32_t actor_hit_by_player_shot(uint8_t *image, uint32_t actor) {
    uint32_t shot;

    if (be16(image + WB_FLASH_TIMER) != 0
        && (int16_t)actor_followed_x_within(image, actor, WB_ACTOR_FLASH_REACH) >= 0)
        return WB_ACTOR_HIT;

    shot = addr_add(be32(image + WB_ACTOR_TABLE_SELECTED),
                    WB_ACTOR_ALLOC_HIGH_FIRST * WB_ACTOR_RECORD_BYTES);

    for (unsigned slot = 0; slot < WB_ACTOR_ALLOC_HIGH_SLOTS; slot++,
         shot = addr_add(shot, WB_ACTOR_RECORD_BYTES)) {
        int16_t type;

        if (field_w(image, shot, WB_ACTOR_X) == (int16_t)WB_ACTOR_FREE_MARKER)
            continue;
        type = field_w(image, shot, WB_ACTOR_TYPE);
        if (type > (int16_t)WB_ACTOR_SHOT_TYPE_HI || type < (int16_t)WB_ACTOR_SHOT_TYPE_LO)
            continue;
        if (!footprint_reaches(image, actor, shot, WB_ACTOR_X, WB_ACTOR_HALF_WIDTH))
            continue;
        if (!footprint_reaches(image, actor, shot, WB_ACTOR_Y, WB_ACTOR_SIZE_SECOND))
            continue;

        if (type == WB_ACTOR_SHOT_TYPE_KEPT)
            set_field_b(image, shot, WB_ACTOR_FIELD_30, WB_ACTOR_SHOT_HIT_MARK);
        else
            set_field_w(image, shot, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
        return WB_ACTOR_HIT;
    }
    return WB_ACTOR_NOT_HIT;
}
