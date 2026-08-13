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
#include "hud.h"
#include "hw.h"
#include "input.h"
#include "machine.h"
#include "map.h"
#include "os.h"
#include "rng.h"
#include "sound.h"
#include "wonderboy.h"

/* What a call hands actor_fall_and_settle where nothing reads its d7 back. The register really is
 * the HANDLER's own entry d7 — a death arm reaches the settle without $23b6 or $5c6e having run —
 * and no memory depends on it: the settles read only its low word and $13be rewrites that before
 * anything does (map.h). Only the two walk arms below hand over a value they can name. */
#define SETTLE_SPAN_UNREAD 0u

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

/* `addq.b #1,d16(An)` — a byte field stepped IN MEMORY, and the value that lands there. Four sites
 * spell it, and the rule they share is why it is one helper: the store happens whether or not the
 * caller reads the answer, and an instruction that reads the field again afterwards must RE-READ it
 * rather than reuse this return — a record at an address bus.h refuses is written nowhere and read
 * back as zero (batch 31's `index/type61-cursor-reread`). Callers that must re-read say so. */
static uint8_t bump_field_b(uint8_t *image, uint32_t record, uint32_t offset) {
    uint8_t stepped = (uint8_t)(field_b(image, record, offset) + 1);

    set_field_b(image, record, offset, stepped);
    return stepped;
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

/* `btst #3,8(a0) / bne / bsr $1170 / bra / bsr $10a2` — the four instructions that pick a probe by
 * the side flag, spelt in three routines below and the same in all three. What they do with the
 * OUTCOME is where they part: $2f22 tests its byte, $5ab2 tests its byte and raises a switch, and
 * $4e38 tests the whole low WORD. So the select is shared and the test is not. */
static uint32_t step_facing(uint8_t *image, uint32_t actor, uint32_t step) {
    return faces_left(image, actor) ? step_left(image, actor, step)
                                    : step_right(image, actor, step);
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
uint32_t actor_behavior_null(uint8_t *image, uint32_t actor) {
    (void)image;
    (void)actor;
    return WB_ACTOR_DISPATCH_RAN;
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
    uint32_t (*handler)(uint8_t *image, uint32_t actor);
} BehaviorHandler;

static const BehaviorHandler PORTED_HANDLERS[] = {
    {WB_ACTOR_BEHAVIOR_NULL, actor_behavior_null},
    {WB_ACTOR_BEHAVIOR_TYPE02, actor_behavior_type02},
    {WB_ACTOR_BEHAVIOR_TYPE03, actor_behavior_type03},
    {WB_ACTOR_BEHAVIOR_TYPE04, actor_behavior_type04},
    {WB_ACTOR_BEHAVIOR_TYPE05, actor_behavior_type05},
    {WB_ACTOR_BEHAVIOR_TYPE06, actor_behavior_type06},
    {WB_ACTOR_BEHAVIOR_TYPE07, actor_behavior_type07},
    {WB_ACTOR_BEHAVIOR_TYPE28, actor_behavior_type28},
    /* Slot 29's two bytes are the same `rts` slots 0 and 58 hold, at an address of its own — so
     * one more row and no more code. */
    {WB_ACTOR_BEHAVIOR_TYPE29, actor_behavior_null},
    {WB_ACTOR_BEHAVIOR_TYPE30, actor_behavior_type30},
    {WB_ACTOR_BEHAVIOR_TYPE31, actor_behavior_type31},
    {WB_ACTOR_BEHAVIOR_TYPE47, actor_behavior_type47},
    {WB_ACTOR_BEHAVIOR_TYPE48, actor_behavior_type48},
    {WB_ACTOR_BEHAVIOR_TYPE49, actor_behavior_type49},
    {WB_ACTOR_BEHAVIOR_TYPE50, actor_behavior_type50},
    {WB_ACTOR_BEHAVIOR_TYPE51, actor_behavior_type51},
    {WB_ACTOR_BEHAVIOR_TYPE52, actor_behavior_type52},
    {WB_ACTOR_BEHAVIOR_TYPE53, actor_behavior_type53},
    {WB_ACTOR_BEHAVIOR_TYPE54, actor_behavior_type54},
    {WB_ACTOR_BEHAVIOR_TYPE55, actor_behavior_type55},
    {WB_ACTOR_BEHAVIOR_TYPE56, actor_behavior_type56},
    {WB_ACTOR_BEHAVIOR_TYPE59, actor_behavior_type59},
    {WB_ACTOR_BEHAVIOR_TYPE08, actor_behavior_type08},
    {WB_ACTOR_BEHAVIOR_TYPE60, actor_behavior_type60},
    {WB_ACTOR_BEHAVIOR_TYPE61, actor_behavior_type61},
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
    /* ...and a handler that HAS a reconstruction can still leave one, so its answer is this
     * routine's answer rather than an assumed WB_ACTOR_DISPATCH_RAN (behavior.h's boundary). */
    return ported->handler(image, actor);
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
 * THE PREMISE THE CAP RESTED ON HAS EXPIRED, which is recorded rather than papered over. "Already
 * read" was only "already read WITH THE SAME ANSWER" while every handler the walk dispatched wrote
 * nothing, and that was true only while `actor_behavior_null` was the sole reconstruction. Batch 30
 * ported handlers that write records, and batch 31's slot 60 writes WB_ACTOR_TYPE itself — so a
 * walk can now change WHICH handler a later dispatch of the same record runs. The cap is therefore
 * a SAFETY BOUND and no longer a proof of non-termination. That is still the right thing to do (the
 * alternative is hanging), but it is a weaker claim, and it is why the runaway has a code of its own
 * rather than sharing the dispatcher's refusal. */
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
    uint32_t outcome = step_facing(image, actor, step);

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

/* $6d5a's a2 — the row it leaves behind, which is its SECOND result: all three of its callers hand
 * that register straight to $6d70/$6dd8 as their band record, so a platform's WB_ACTOR_HALF_WIDTH
 * picks its sprite and its band together out of one eight-byte row.
 *
 * `lsl.w #3` scales inside the WORD and `adda.w d0,a2` then SIGN-EXTENDS what is left, so a
 * WB_ACTOR_HALF_WIDTH of $1000..$1fff addresses BELOW the table and one of $2000 lands back on the
 * table itself — the index wraps twice over, not once. */
static uint32_t sprite_6ed8_row(const uint8_t *image, uint32_t actor) {
    uint16_t index = (uint16_t)(field_w(image, actor, WB_ACTOR_HALF_WIDTH)
                                * WB_ACTOR_SPRITE_6ED8_STRIDE);

    return addr_add(WB_ACTOR_SPRITE_TABLE_6ED8, sign_ext16(index));
}

/* $6d5a — twenty-two bytes ending in `bra.w $67e0`, so the followed record `followed_actor_record`
 * names is this routine's own result. */
uint32_t actor_sprite_from_6ed8(uint8_t *image, uint32_t actor) {
    set_field_w(image, actor, WB_ACTOR_SPRITE,
                bus_read_word(image, sprite_6ed8_row(image, actor)));
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


/* $6786 — the request FIVE rows of the $4e38..$5406 band fire when they are collected ($4e4e,
 * $4ee0, $4fca, $506c, $5214 — slots 28, 30, 31, 32 and 33, not every slot in the band). No other
 * control-flow site reaches it; its `jmp 56(a1)` is a tail jump, so nothing follows it. */
void sound_request_9(uint8_t *image) {
    snd_call_trigger_effect(image, WB_ACTOR_REQUEST9_SFX, WB_SND_CHANNEL_A);
}

/* --- $6796: the stun eleven handlers reach ------------------------------------------------------
 *
 * One sound effect, then a STEP COUNT stamped into the FOLLOWED record — the same
 * `n - 2 * <state word>` shape actor_damage_followed spells over WB_EFFECT_STATE_BD66, here over
 * WB_EFFECT_STATE_BD68, which had no reader among the recovered functions until this one was read.
 * (Batch 28's plate called the tail "a facing update"; it writes no facing bit at all.)
 */
void actor_stun_followed(uint8_t *image) {
    uint32_t followed;

    snd_call_trigger_effect(image, WB_ACTOR_STUN_SFX, WB_SND_CHANNEL_A);
    followed = followed_actor_record(image);

    /* `move.w $bd68.l,d0 / add.w d0,d0 / move.w #$a,d1 / sub.w d0,d1` is 16-bit throughout and only
     * the low BYTE of the difference is stored, so a state word above 5 wraps into a large count. */
    set_field_b(image, followed, WB_ACTOR_FIELD_29,
                (uint8_t)(WB_ACTOR_STUN_STEPS_BASE
                          - 2u * be16(image + WB_EFFECT_STATE_BD68)));
    set_field_b(image, followed, WB_ACTOR_FIELD_22, 0);
}


/* --- what every monster handler below is built from ---------------------------------------------
 *
 * The five handlers in the $2462..$2db1 band are one shape with five bodies in the middle of it,
 * and these four helpers are the parts that really are the same instructions rather than merely
 * similar ones. Everything that differs between the slots — which frames, which step, which flag —
 * stays in the handler.
 */

/* `btst #2,9(a0) / bne.w $698a`: the FIRST TWO INSTRUCTIONS of twenty-five handlers, and a BRANCH
 * rather than a call — the spawn animation returns through the handler's own frame, so a handler
 * whose record is still spawning is done for the frame. */
static int spawn_animation_took_the_frame(uint8_t *image, uint32_t actor) {
    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_SPAWNED_BIT))
        return 0;
    actor_spawn_anim_step(image, actor);
    return 1;
}

/* What a monster's frame finds when it asks whether it has been touched. THE ORDER IS THE WHOLE OF
 * IT: `bsr $23b6 / tst.w d7 / bne` short-circuits, so on a shot hit $5c6e does not run at all —
 * which also means d7 below is only the followed record's sprite on the paths that reach the walk. */
typedef enum {
    MONSTER_UNTOUCHED,
    MONSTER_TOUCHED_FOLLOWED,   /* bit 1, the two footprints: the monster DEALS damage */
    MONSTER_STRUCK              /* $23b6's verdict, or bit 2: the monster TAKES it */
} MonsterContact;

static MonsterContact monster_contact(uint8_t *image, uint32_t actor) {
    uint32_t overlap;

    if (actor_hit_by_player_shot(image, actor) != WB_ACTOR_NOT_HIT)
        return MONSTER_STRUCK;

    overlap = actor_followed_overlap_mask(image, actor);
    if (overlap & (1u << WB_ACTOR_OVERLAP_BODY_BIT))
        return MONSTER_TOUCHED_FOLLOWED;
    if (overlap & (1u << WB_ACTOR_OVERLAP_POINT_BIT))
        return MONSTER_STRUCK;
    return MONSTER_UNTOUCHED;
}

/* `bset #0,9(a0) / clr.b 18(a0)` — the two writes every STRUCK arm opens with before its tail jump
 * into actor_damage_template_hitpoints. The jump itself stays at each site because slot 6 faces the
 * followed record in between and the others do not. */
static void monster_enter_hit_animation(uint8_t *image, uint32_t actor) {
    flag_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
    set_field_b(image, actor, WB_ACTOR_FIELD_18, 0);
}

/* The d7 $5c6e leaves: the FOLLOWED record's own sprite id, over the long `moveq #0,d7` $23b6
 * cleared first. Every walk arm below enters actor_fall_and_settle with it, and slots 3 and 6 then
 * read a BYTE of what comes back (map.h) — which is the whole reason this value has a name. */
static uint32_t followed_sprite_left_in_d7(const uint8_t *image) {
    return bus_read_word(image, addr_add(followed_actor_record(image), WB_ACTOR_SPRITE));
}

/* `move.w 0(a1,d0.w),6(a0)` — the frame a byte cursor names in a word table, published. */
static void publish_frame(uint8_t *image, uint32_t actor, uint32_t frames, uint8_t cursor) {
    set_field_w(image, actor, WB_ACTOR_SPRITE, bus_read_word(image, addr_add(frames, cursor)));
}

/* `addi #2,d0 / andi #mask,d0` over a cursor `moveq #0,d0 / move.b 18(a0),d0` zero-extended — which
 * is why the word and byte spellings of the pair agree on every value a record can hold. */
static uint8_t step_cursor(uint8_t cursor, uint8_t mask) {
    return (uint8_t)((cursor + WB_ACTOR_ANIM_FRAME_BYTES) & mask);
}

/* Publish this frame and hand back the STEPPED cursor without storing it: where the store goes is
 * the caller's, and it is not the same place twice — slots 2, 3 and 4 skip it entirely on the frame
 * the wrap sends them to actor_defeat_and_score, while slots 5 and 6 commit it first. */
static uint8_t advance_frame_cursor(uint8_t *image, uint32_t actor, uint32_t frames, uint8_t mask) {
    uint8_t cursor = field_b(image, actor, WB_ACTOR_FIELD_18);

    publish_frame(image, actor, frames, cursor);
    return step_cursor(cursor, mask);
}

/* `move.b #$2,d7` — a step written into the LOW BYTE ALONE of a register the settle above left
 * something in. Slots 3 and 6 both spell their LEFT arm this way and their right one `move.w`, so
 * the two arms walk the same two pixels only while what actor_fall_and_settle left is below $100 —
 * which its own scan guarantees for a non-negative footprint and nothing guarantees otherwise. */
static uint32_t step_over_low_byte(uint32_t settle_span, uint8_t step) {
    return (settle_span & ~0xffu) | step;
}

/* The `bclr #3,9(a0) / bne.w $6bb8` every death animation ends its last frame with: the bit is
 * lowered whatever it held and the branch reads what it HELD, so the transfer is on the old value.
 * Reports whether the defeat ran, because the two slots that spell it as `btst` do not clear it. */
static int monster_defeat_if_marked(uint8_t *image, uint32_t actor) {
    int defeated = flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT);

    flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT);
    if (defeated)
        actor_defeat_and_score(image, actor);
    return defeated;
}


/* --- slot 2 ($2462): the walker that faces the player ------------------------------------------
 *
 * It takes no step at all while it is alive: WB_ACTOR_FLAG_SIDE_BIT and the frame list follow the
 * followed record's x and the record only ever falls. The death animation is the half that moves —
 * a recoil of WB_ACTOR_TYPE02_DEAD_STEP pixels AWAY, sixteen frames long, and it is skipped once
 * the record is marked defeated so a dying monster stands still.
 */
static void type02_death_frame(uint8_t *image, uint32_t actor) {
    uint32_t frames;
    uint8_t stepped;

    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);

    /* SET here steps RIGHT, which is the OPPOSITE arm to $2f22's: the bit says the followed record
     * is to the LEFT (actor.h), so the recoil is away from it rather than toward it. */
    if (faces_left(image, actor)) {
        if (!flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT))
            step_right(image, actor, WB_ACTOR_TYPE02_DEAD_STEP);
        frames = WB_ACTOR_TYPE02_DEAD_RIGHT;
    } else {
        if (!flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT))
            step_left(image, actor, WB_ACTOR_TYPE02_DEAD_STEP);
        frames = WB_ACTOR_TYPE02_DEAD_LEFT;
    }

    stepped = advance_frame_cursor(image, actor, frames, WB_ACTOR_ANIM32_MASK);
    if (stepped == 0) {
        flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
        /* The tail jump into actor_defeat_and_score SKIPS the store below — the cursor is left
         * holding the last frame's offset on the one frame the record dies. */
        if (monster_defeat_if_marked(image, actor))
            return;
    }
    set_field_b(image, actor, WB_ACTOR_FIELD_18, stepped);
}

uint32_t actor_behavior_type02(uint8_t *image, uint32_t actor) {
    uint32_t frames;
    uint8_t cursor;

    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        type02_death_frame(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
        monster_enter_hit_animation(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    actor_fall_and_settle(image, actor, followed_sprite_left_in_d7(image));

    /* `move.w $9aec.l,d1` — WB_ACTOR_FOLLOWED_DEFAULT's x read DIRECTLY, not through
     * followed_actor_record, so this handler faces the default record even while WB_STATE_FLAG_A32
     * names the other one. The compare is INCLUSIVE where $67c2's is strict. */
    if ((int16_t)be16(image + WB_ACTOR_FOLLOWED_DEFAULT) > field_w(image, actor, WB_ACTOR_X)) {
        frames = WB_ACTOR_TYPE02_WALK_RIGHT;
        flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
    } else {
        frames = WB_ACTOR_TYPE02_WALK_LEFT;
        flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
    }

    /* The eighteen bytes at $24d4 ARE actor_advance_anim16's, spelt inline rather than called. */
    cursor = field_b(image, actor, WB_ACTOR_FIELD_18);
    actor_advance_anim16(image, actor, addr_add(frames, cursor), cursor);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 3 ($25c0): the patroller ---------------------------------------------------------------
 *
 * It walks WB_ACTOR_TYPE03_WALK_STEP pixels a frame and turns round twice over: on
 * WB_ACTOR_TYPE03_TURN_FRAMES elapsing, and on actor_toggle_side_flag's reading of the ground the
 * step came back with. Its death arm faces the followed record through a THIRD spelling of that
 * record and then retreats from it.
 */
static void type03_death_frame(uint8_t *image, uint32_t actor) {
    uint32_t frames;
    uint8_t stepped;
    /* `movea.l $a098.l,a1 / adda.l #$180,a1` — the PUBLISHED table pointer stepped to the followed
     * slot, where slot 2 reads an absolute word and $67e0 branches on WB_STATE_FLAG_A32. Three
     * spellings of one record, and this one follows whichever table is published. */
    uint32_t followed = addr_add(be32(image + WB_ACTOR_TABLE_SELECTED),
                                 WB_ACTOR_FOLLOWED_SLOT * WB_ACTOR_RECORD_BYTES);
    int defeated = flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT);

    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);

    if (field_w(image, followed, WB_ACTOR_X) >= field_w(image, actor, WB_ACTOR_X)) {
        flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
        frames = defeated ? WB_ACTOR_TYPE03_HELD_LEFT : WB_ACTOR_TYPE03_DEAD_LEFT;
        if (!defeated)
            step_left(image, actor, WB_ACTOR_TYPE03_DEAD_STEP);
    } else {
        flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
        frames = defeated ? WB_ACTOR_TYPE03_HELD_RIGHT : WB_ACTOR_TYPE03_DEAD_RIGHT;
        if (!defeated)
            step_right(image, actor, WB_ACTOR_TYPE03_DEAD_STEP);
    }

    stepped = advance_frame_cursor(image, actor, frames, WB_ACTOR_ANIM16_MASK);
    if (stepped == 0) {
        flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
        if (monster_defeat_if_marked(image, actor))
            return;
    }
    set_field_b(image, actor, WB_ACTOR_FIELD_18, stepped);
}

uint32_t actor_behavior_type03(uint8_t *image, uint32_t actor) {
    uint32_t settle_span, frames, ground = 0, outcome;
    uint8_t timer, cursor;

    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        type03_death_frame(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
        monster_enter_hit_animation(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    settle_span = actor_fall_and_settle(image, actor, followed_sprite_left_in_d7(image));

    timer = field_b(image, actor, WB_ACTOR_FIELD_30);
    if (timer != 0) {
        set_field_b(image, actor, WB_ACTOR_FIELD_30, (uint8_t)(timer - 1));
    } else {
        set_field_b(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE03_TURN_FRAMES);
        flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
    }

    if (faces_left(image, actor)) {
        outcome = actor_step_left_against_map(
            image, actor, step_over_low_byte(settle_span, WB_ACTOR_TYPE03_WALK_STEP), &ground);
        frames = WB_ACTOR_TYPE03_WALK_LEFT;
    } else {
        outcome = actor_step_right_against_map(image, actor, WB_ACTOR_TYPE03_WALK_STEP, &ground);
        frames = WB_ACTOR_TYPE03_WALK_RIGHT;
    }
    actor_toggle_side_flag(image, actor, outcome, ground);

    /* The frame list is the one the facing chose BEFORE the step, so a turn taken by
     * actor_toggle_side_flag shows in next frame's list and not in this one's. */
    cursor = field_b(image, actor, WB_ACTOR_FIELD_18);
    actor_advance_anim16(image, actor, addr_add(frames, cursor), cursor);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 4 ($2796): the hoverer ----------------------------------------------------------------
 *
 * The one handler here that never touches the collision map while alive: it chases the followed
 * record horizontally, one pixel a frame and only from inside WB_ACTOR_CHASE_REACH, while a
 * 64-word table of signed deltas moves it up and down every frame whether it is chasing or not.
 */
static void type04_hover_step(uint8_t *image, uint32_t actor) {
    uint8_t cursor = field_b(image, actor, WB_ACTOR_FIELD_30);
    int16_t delta = (int16_t)bus_read_word(image, addr_add(WB_ACTOR_TYPE04_HOVER, cursor));

    set_field_w(image, actor, WB_ACTOR_Y,
                (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_Y) + (uint16_t)delta));
    set_field_b(image, actor, WB_ACTOR_FIELD_30,
                step_cursor(cursor, WB_ACTOR_TYPE04_HOVER_MASK));
}

static void type04_death_frame(uint8_t *image, uint32_t actor) {
    uint32_t frames;
    uint8_t stepped;
    int defeated = flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT);

    /* No settle at all on this arm — a dead hoverer neither falls nor lands. */
    if (faces_left(image, actor)) {
        if (!defeated)
            step_right(image, actor, WB_ACTOR_TYPE04_DEAD_STEP);
        frames = WB_ACTOR_TYPE04_DEAD_RIGHT;
    } else {
        if (!defeated)
            step_left(image, actor, WB_ACTOR_TYPE04_DEAD_STEP);
        frames = WB_ACTOR_TYPE04_DEAD_LEFT;
    }

    stepped = advance_frame_cursor(image, actor, frames, WB_ACTOR_ANIM32_MASK);
    if (stepped == 0) {
        flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
        if (monster_defeat_if_marked(image, actor))
            return;
    }
    set_field_b(image, actor, WB_ACTOR_FIELD_18, stepped);
}

uint32_t actor_behavior_type04(uint8_t *image, uint32_t actor) {
    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        type04_death_frame(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
        monster_enter_hit_animation(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    actor_set_side_flag(image, actor);
    if ((int16_t)actor_followed_x_within(image, actor, WB_ACTOR_CHASE_REACH) >= 0) {
        uint32_t followed = followed_actor_record(image);
        int left = faces_left(image, actor);

        /* Level with the followed record it stops stepping but keeps animating — `cmp.w (a1),d0 /
         * beq` skips only the two probe calls. */
        if (field_w(image, actor, WB_ACTOR_X) != field_w(image, followed, WB_ACTOR_X)) {
            if (left)
                step_left(image, actor, WB_ACTOR_TYPE04_FLY_STEP);
            else
                step_right(image, actor, WB_ACTOR_TYPE04_FLY_STEP);
        }

        /* `move.l #$0,d0` where every other cursor here is a `moveq`: six bytes for the same zero,
         * the deliberate-waste class ../names.txt records at $7366. */
        set_field_b(image, actor, WB_ACTOR_FIELD_18,
                    advance_frame_cursor(image, actor,
                                         left ? WB_ACTOR_TYPE04_FLY_LEFT
                                              : WB_ACTOR_TYPE04_FLY_RIGHT,
                                         WB_ACTOR_ANIM32_MASK));
    }
    type04_hover_step(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 5 ($29ec): the hopper -----------------------------------------------------------------
 *
 * One pixel a frame, and actor_hop_or_flip_side turns the ground the step reported into a hop or a
 * turn — the first two handlers in this file to read the map probes' SECOND result. Its death arm
 * is the only one here that shares ONE frame list between the two facings.
 */
static void type05_death_frame(uint8_t *image, uint32_t actor) {
    uint8_t stepped;

    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    actor_hop_ascend_step(image, actor);
    actor_set_side_flag(image, actor);

    stepped = advance_frame_cursor(image, actor, WB_ACTOR_TYPE05_DEAD, WB_ACTOR_ANIM16_MASK);
    /* Committed BEFORE the branch, unlike slots 2..4 — so the cursor is stored even on the frame
     * the transfer into actor_defeat_and_score happens. */
    set_field_b(image, actor, WB_ACTOR_FIELD_18, stepped);

    if (stepped == 0) {
        /* `btst`, not `bclr`: the defeated bit survives the transfer here. */
        if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT)) {
            actor_defeat_and_score(image, actor);
            return;
        }
        flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
        return;
    }

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT))
        return;
    if (faces_left(image, actor))
        step_right(image, actor, WB_ACTOR_TYPE05_DEAD_STEP);
    else
        step_left(image, actor, WB_ACTOR_TYPE05_DEAD_STEP);
}

uint32_t actor_behavior_type05(uint8_t *image, uint32_t actor) {
    uint32_t frames, ground = 0, outcome;

    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        type05_death_frame(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
        monster_enter_hit_animation(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    actor_fall_and_settle(image, actor, followed_sprite_left_in_d7(image));
    actor_hop_ascend_step(image, actor);

    if (faces_left(image, actor)) {
        outcome = actor_step_left_against_map(image, actor, WB_ACTOR_TYPE05_HOP_STEP, &ground);
        frames = WB_ACTOR_TYPE05_HOP_LEFT;
    } else {
        outcome = actor_step_right_against_map(image, actor, WB_ACTOR_TYPE05_HOP_STEP, &ground);
        frames = WB_ACTOR_TYPE05_HOP_RIGHT;
    }
    actor_hop_or_flip_side(image, actor, outcome, ground);

    set_field_b(image, actor, WB_ACTOR_FIELD_18,
                advance_frame_cursor(image, actor, frames, WB_ACTOR_ANIM32_MASK));
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 6 ($2bc8): the thrower ----------------------------------------------------------------
 *
 * The only handler in this batch that SPAWNS, and the THROW IS ON THE LANDING. Every
 * WB_ACTOR_TYPE06_RELOAD frames it looks for the followed record inside WB_ACTOR_CHASE_REACH, faces
 * it and launches itself at WB_ACTOR_TYPE06_CHARGE_SPEED — which CLEARS
 * WB_ACTOR_FLAG_SUPPORTED_BIT (`bclr #2,8(a0)` inside actor_start_motion_at_speed). While that bit
 * is down the record is in the air and holds one standing frame; the frame $1400's landing arm
 * raises it again is the frame `btst #2,8(a0)` passes and a HIGH-pool record of
 * WB_ACTOR_TYPE06_SHOT_TYPE is allocated beside it.
 *
 * AND IT SAVES ITS OWN FLAG BYTE ACROSS THAT, in WB_ACTOR_FIELD_29. `move.b 8(a0),29(a0)` runs
 * before actor_set_side_flag and actor_start_motion_at_speed and `move.b 29(a0),8(a0)` puts the
 * byte back afterwards, so both routines' writes to the flag byte are UNDONE — except on the
 * AIRBORNE arm, which returns before reaching the restore. The
 * restore is also reached on frames the save did not run, and then it writes back a byte saved on
 * some earlier frame.
 */
static void type06_throw_shot(uint8_t *image, uint32_t actor) {
    uint32_t shot = actor_alloc_slot_high(image);

    if (shot == 0)
        return;

    /* `move.l (a0),(a1)` — the x and y words in ONE operand, which is why this goes through the
     * longword guard rather than two word writes. */
    bus_write_long(image, shot, bus_read_long(image, actor));
    set_field_w(image, shot, WB_ACTOR_Y,
                (uint16_t)((uint16_t)field_w(image, shot, WB_ACTOR_Y) - WB_ACTOR_TYPE06_SHOT_UP));
    set_field_w(image, shot, WB_ACTOR_X,
                (uint16_t)((uint16_t)field_w(image, shot, WB_ACTOR_X)
                           + (faces_left(image, actor) ? WB_ACTOR_TYPE06_SHOT_BEHIND
                                                       : WB_ACTOR_TYPE06_SHOT_AHEAD)));
    set_field_w(image, shot, WB_ACTOR_TYPE, WB_ACTOR_TYPE06_SHOT_TYPE);
    set_field_b(image, shot, WB_ACTOR_FLAGS, field_b(image, actor, WB_ACTOR_FLAGS));
    bus_write_long(image, addr_add(shot, WB_ACTOR_HALF_WIDTH), WB_ACTOR_TYPE06_SHOT_SIZE);
    set_field_w(image, shot, WB_ACTOR_FIELD_30, 0);
    set_field_b(image, shot, WB_ACTOR_FIELD_18, 0);
    flag_clear(image, shot, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
}

/* $2cd0 — put the saved flag byte back and arm the next throw. Three entrances: the followed record
 * being out of reach, the allocation failing, and the spawn falling through. */
static void type06_restore_flags_and_turn(uint8_t *image, uint32_t actor) {
    set_field_b(image, actor, WB_ACTOR_FLAGS, field_b(image, actor, WB_ACTOR_FIELD_29));
    set_field_b(image, actor, WB_ACTOR_FIELD_31, 0);
    set_field_b(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE06_RELOAD);
    flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
}

/* $2ce6 — the walk both the reload arm and the throw arm end in. */
static void type06_walk_step(uint8_t *image, uint32_t actor, uint32_t settle_span) {
    uint32_t ground = 0, outcome;

    if (faces_left(image, actor))
        outcome = actor_step_left_against_map(
            image, actor, step_over_low_byte(settle_span, WB_ACTOR_TYPE06_WALK_STEP), &ground);
    else
        outcome = actor_step_right_against_map(image, actor, WB_ACTOR_TYPE06_WALK_STEP, &ground);
    actor_toggle_side_flag(image, actor, outcome, ground);

    /* The facing is read AGAIN here, after actor_toggle_side_flag may have turned the record — so
     * unlike slot 3 the frame list can be this frame's turn rather than last frame's. */
    set_field_b(image, actor, WB_ACTOR_FIELD_18,
                advance_frame_cursor(image, actor,
                                     faces_left(image, actor) ? WB_ACTOR_TYPE06_WALK_LEFT
                                                              : WB_ACTOR_TYPE06_WALK_RIGHT,
                                     WB_ACTOR_ANIM32_MASK));
}

static void type06_death_frame(uint8_t *image, uint32_t actor) {
    uint32_t frames;
    uint8_t stepped;
    int defeated = flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT);
    int left = faces_left(image, actor);

    if (!defeated) {
        if (left)
            step_right(image, actor, WB_ACTOR_TYPE06_DEAD_STEP);
        else
            step_left(image, actor, WB_ACTOR_TYPE06_DEAD_STEP);
    }
    frames = left ? WB_ACTOR_TYPE06_DEAD_RIGHT : WB_ACTOR_TYPE06_DEAD_LEFT;

    stepped = advance_frame_cursor(image, actor, frames, WB_ACTOR_ANIM16_MASK);
    set_field_b(image, actor, WB_ACTOR_FIELD_18, stepped);
    if (stepped != 0)
        return;

    flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT))
        actor_defeat_and_score(image, actor);
}

uint32_t actor_behavior_type06(uint8_t *image, uint32_t actor) {
    uint32_t settle_span;

    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        type06_death_frame(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
        monster_enter_hit_animation(image, actor);
        actor_set_side_flag(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    settle_span = actor_fall_and_settle(image, actor, followed_sprite_left_in_d7(image));
    actor_hop_ascend_step(image, actor);

    if (field_b(image, actor, WB_ACTOR_FIELD_30) != 0) {
        set_field_b(image, actor, WB_ACTOR_FIELD_31, 0);
        set_field_b(image, actor, WB_ACTOR_FIELD_30,
                    (uint8_t)(field_b(image, actor, WB_ACTOR_FIELD_30) - 1));
        type06_walk_step(image, actor, settle_span);
        return WB_ACTOR_DISPATCH_RAN;
    }

    if (field_b(image, actor, WB_ACTOR_FIELD_31) == 0) {
        set_field_b(image, actor, WB_ACTOR_FIELD_29, field_b(image, actor, WB_ACTOR_FLAGS));
        set_field_b(image, actor, WB_ACTOR_FIELD_31, WB_ACTOR_ST_BYTE);

        if ((int16_t)actor_followed_x_within(image, actor, WB_ACTOR_CHASE_REACH) < 0) {
            type06_restore_flags_and_turn(image, actor);
            type06_walk_step(image, actor, settle_span);
            return WB_ACTOR_DISPATCH_RAN;
        }
        actor_set_side_flag(image, actor);
        actor_start_motion_at_speed(image, actor, WB_ACTOR_TYPE06_CHARGE_SPEED);
    }

    /* STILL IN THE AIR — WB_ACTOR_FLAG_SUPPORTED_BIT is what $1400's landing arm raises, and
     * actor_start_motion_at_speed cleared it on the frame this record launched. It holds one of two
     * standing frames and the frame ENDS: no throw, no walk, and no restore, so the flag byte that
     * launch just wrote stays written until the record lands. */
    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT)) {
        set_field_w(image, actor, WB_ACTOR_SPRITE,
                    faces_left(image, actor) ? WB_ACTOR_TYPE06_SPRITE_LEFT
                                             : WB_ACTOR_TYPE06_SPRITE_RIGHT);
        return WB_ACTOR_DISPATCH_RAN;
    }

    type06_throw_shot(image, actor);
    type06_restore_flags_and_turn(image, actor);
    type06_walk_step(image, actor, settle_span);
    return WB_ACTOR_DISPATCH_RAN;
}


/* `subq.b #1,30(a0)` — the countdown slots 48, 49 and 50 spend, and the byte it left. The `bne`
 * above every site reads the SUBTRACTION's own flags, so the answer really is the stored byte and
 * no site re-reads the field. */
static uint8_t tick_countdown30(uint8_t *image, uint32_t actor) {
    uint8_t timer = (uint8_t)(field_b(image, actor, WB_ACTOR_FIELD_30) - 1);

    set_field_b(image, actor, WB_ACTOR_FIELD_30, timer);
    return timer;
}

/* $59ae / $5a8c — the tail slots 48 and 50 end in: one frame published out of the handler's own
 * table, the cursor committed, and `subq.b #1,30(a0)` handing the slot back on the frame the
 * countdown reaches zero. The free marker goes over the x word THIS SAME FRAME may have stepped.
 *
 * THE TWO ARE NOT THE SAME BYTES. Slot 48 spells its cursor step `addi.b`/`andi.b` and slot 50
 * `addi.w`/`andi.w`, 230 bytes apart, and slot 50 has a dead `lea` above its own. What makes one
 * helper right is `step_cursor`'s argument: the byte and word spellings agree for every cursor a
 * record can hold, because the register is `moveq #0,d0 / move.b` zero-extended first. */
static void animate_then_free_on_countdown(uint8_t *image, uint32_t actor, uint32_t frames,
                                           uint8_t mask) {
    set_field_b(image, actor, WB_ACTOR_FIELD_18,
                advance_frame_cursor(image, actor, frames, mask));

    if (tick_countdown30(image, actor) == 0)
        set_field_w(image, actor, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
}

/* --- slot 50 ($5a6e): the eight-pixel drift ------------------------------------------------------
 *
 * No spawn gate, no contact test, no map: it slides WB_ACTOR_TYPE50_STEP pixels a frame the way its
 * side bit points, plays two frames, and FREES ITS OWN SLOT when WB_ACTOR_FIELD_30 runs out.
 *
 * `lea $5aae.l,a1` at $5a80 is DEAD — the `lea $5aae(pc,d0.w),a1` six instructions later overwrites
 * a1 before anything reads it. It is also the only absolute reference to the frame table anywhere
 * in the image, which is what made those two words visible to a scan at all.
 */
uint32_t actor_behavior_type50(uint8_t *image, uint32_t actor) {
    uint16_t x = (uint16_t)field_w(image, actor, WB_ACTOR_X);

    set_field_w(image, actor, WB_ACTOR_X,
                (uint16_t)(faces_left(image, actor) ? x - WB_ACTOR_TYPE50_STEP
                                                    : x + WB_ACTOR_TYPE50_STEP));
    animate_then_free_on_countdown(image, actor, WB_ACTOR_TYPE50_FRAMES, WB_ACTOR_TYPE50_MASK);
    return WB_ACTOR_DISPATCH_RAN;
}


/* THE CONTACT PAIR ALL THREE SLOTS SPELL IDENTICALLY, written in `spawn_animation_took_the_frame`'s
 * shape: it answers whether the frame is over. There is no `actor_hit_by_player_shot` in front of it
 * here, so this is NOT `monster_contact` above — these three slots read only the overlap mask, and
 * its bit 2 not at all. */
static int switched_contact_took_the_frame(uint8_t *image, uint32_t actor) {
    uint32_t overlap = actor_followed_overlap_mask(image, actor);

    /* Bit 0: the record stuns the followed one and switches itself off, through a tail jump. */
    if (overlap & (1u << WB_ACTOR_OVERLAP_STRIKE_BIT)) {
        flag_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
        actor_stun_followed(image);
        return 1;
    }

    /* Bit 1: it spends WB_ACTOR_CONTACT_DAMAGE_INLINE instead. The record's own
     * WB_ACTOR_TEMPLATE_SLOT byte is overwritten with that INLINE damage word — the sign bit
     * actor_damage_followed reads as "the cost is in my low seven bits". */
    if (overlap & (1u << WB_ACTOR_OVERLAP_BODY_BIT)) {
        set_field_b(image, actor, WB_ACTOR_TEMPLATE_SLOT, WB_ACTOR_CONTACT_DAMAGE_INLINE);
        flag_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
        actor_damage_followed(image, actor);
        set_field_b(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_ST_BYTE);
        return 1;
    }
    return 0;
}

/* --- slot 51 ($5ab2): the charger that dies on landing -------------------------------------------
 *
 * Bit 0 of WB_ACTOR_FLAGS2 is a one-way switch here, not a death animation: while it is clear the
 * record walks and tests; every arm that raises it hands the record to the fall below, which frees
 * the slot the moment the record is supported again.
 */
uint32_t actor_behavior_type51(uint8_t *image, uint32_t actor) {
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
        actor_hop_ascend_step(image, actor);
        if (!flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT))
            return WB_ACTOR_DISPATCH_RAN;
        set_field_w(image, actor, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
        flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
        return WB_ACTOR_DISPATCH_RAN;
    }

    if (switched_contact_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;

    set_field_w(image, actor, WB_ACTOR_SPRITE, WB_ACTOR_TYPE51_SPRITE);
    if (step_was_blocked(step_facing(image, actor, WB_ACTOR_TYPE51_STEP)))
        flag_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- $6e8c and the three moving platforms (slots 54, 55, 56) ------------------------------------
 *
 * All three open with actor_sprite_from_6ed8, so a0 is the platform, a1 the followed record and a2
 * the eight-byte WB_ACTOR_SPRITE_TABLE_6ED8 row WB_ACTOR_HALF_WIDTH picked — its first word the
 * sprite and its second and third the band $6d70/$6dd8 test against. WB_ACTOR_SIZE_SECOND is the
 * travel LIMIT and WB_ACTOR_FIELD_24 the cursor against it.
 */

/* $6e8c — the cell the RIDER stands in, and what a platform does when it is solid: back the rider
 * out by one step and end the ride. Slots 54 and 56 call it, on the frames they move DOWN.
 *
 * IT PROBES WB_COLLISION_MAP_DEFAULT UNCONDITIONALLY, where every other probe in the game picks a
 * map on WB_STATE_FLAG_A32 — the same asymmetry $10a2's ground test has, in a second routine. And
 * the two shifts are `lsr.w`, UNSIGNED, where $13c8's are `asr.w`: a negative coordinate lands on a
 * cell 4096 columns along instead of below zero. */
static int cell_is_solid(const uint8_t *image, uint32_t cell) {
    uint8_t tile = bus_read_byte(image, cell);

    return tile == WB_MAP_TILE_BLOCK || tile == WB_MAP_TILE_LEDGE;
}

void actor_platform_release_blocked_rider(uint8_t *image, uint32_t actor, uint32_t followed) {
    uint16_t stride = bus_read_word(image, WB_COLLISION_MAP_DEFAULT);
    uint16_t column = (uint16_t)(((uint16_t)field_w(image, followed, WB_ACTOR_X)
                                  >> WB_MAP_CELL_SHIFT) + WB_COLLISION_MAP_CELLS);
    uint16_t row = (uint16_t)((uint16_t)field_w(image, followed, WB_ACTOR_Y)
                              >> WB_MAP_CELL_SHIFT);
    /* `adda.w d0,a6` sign-extends the column and `adda.l d1,a6` adds the whole `mulu.w` product. */
    uint32_t cell = addr_add(addr_add(WB_COLLISION_MAP_DEFAULT, sign_ext16(column)),
                             (uint32_t)stride * row);

    if (!cell_is_solid(image, cell) && !cell_is_solid(image, addr_add(cell, 1)))
        return;

    set_field_w(image, followed, WB_ACTOR_Y,
                (uint16_t)((uint16_t)field_w(image, followed, WB_ACTOR_Y)
                           - WB_ACTOR_PLATFORM_STEP));
    wr16(image + WB_ACTOR_PLATFORM_RIDDEN, 0);
    flag_clear(image, actor, WB_ACTOR_FIELD_22, WB_ACTOR_FIELD_22_RIDING_BIT);
}

/* $6e70 — the travel cursor slots 54 and 55 share (55 reaches it by three `bra.w`s into 54's body).
 * The turn is on EQUALITY with the limit, not on passing it, so a limit the step cannot land on
 * exactly is never reached and the platform travels until the word wraps. */
static void platform_travel_step(uint8_t *image, uint32_t actor) {
    uint16_t travelled = (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_FIELD_24)
                                    + WB_ACTOR_PLATFORM_STEP);

    set_field_w(image, actor, WB_ACTOR_FIELD_24, travelled);
    if ((int16_t)travelled != field_w(image, actor, WB_ACTOR_SIZE_SECOND))
        return;
    set_field_w(image, actor, WB_ACTOR_FIELD_24, 0);
    flag_flip(image, actor, WB_ACTOR_FIELD_22, WB_ACTOR_FIELD_22_DIRECTION_BIT);
}

static int travelling_back(const uint8_t *image, uint32_t actor) {
    return flag_is_set(image, actor, WB_ACTOR_FIELD_22, WB_ACTOR_FIELD_22_DIRECTION_BIT);
}

static int is_the_ridden_platform(const uint8_t *image, uint32_t actor) {
    return flag_is_set(image, actor, WB_ACTOR_FIELD_22, WB_ACTOR_FIELD_22_RIDING_BIT);
}

/* $6e1c — the VERTICAL platform. It snaps the rider to its own top every frame rather than letting
 * $6d70 do it, and on the way DOWN it checks the rider against the map: a rider pushed into solid
 * ground is lifted back out and dropped. */
uint32_t actor_behavior_type54(uint8_t *image, uint32_t actor) {
    uint32_t followed = actor_sprite_from_6ed8(image, actor);
    uint32_t band = sprite_6ed8_row(image, actor);
    uint16_t y = (uint16_t)field_w(image, actor, WB_ACTOR_Y);

    set_field_w(image, actor, WB_ACTOR_Y,
                (uint16_t)(travelling_back(image, actor) ? y - WB_ACTOR_PLATFORM_STEP
                                                         : y + WB_ACTOR_PLATFORM_STEP));

    if (be16(image + WB_ACTOR_PLATFORM_RIDDEN) == 0) {
        actor_platform_carry_followed(image, actor, followed, band);
    } else if (is_the_ridden_platform(image, actor)) {
        set_field_w(image, followed, WB_ACTOR_Y,
                    (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_Y)
                               - WB_ACTOR_PLATFORM_TOP));
        actor_platform_release_check(image, actor, followed, band);
        if (!travelling_back(image, actor))
            actor_platform_release_blocked_rider(image, actor, followed);
    }
    platform_travel_step(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}

/* $6ef4 — the HORIZONTAL one: the same body over the x word, carrying the rider sideways by the
 * same two pixels instead of snapping it, and with no map check at all. `tst.w $6ef0.w` here is an
 * absolute-SHORT read of the word slot 54 reads absolute-long. */
uint32_t actor_behavior_type55(uint8_t *image, uint32_t actor) {
    uint32_t followed = actor_sprite_from_6ed8(image, actor);
    uint32_t band = sprite_6ed8_row(image, actor);
    uint16_t x = (uint16_t)field_w(image, actor, WB_ACTOR_X);

    set_field_w(image, actor, WB_ACTOR_X,
                (uint16_t)(travelling_back(image, actor) ? x - WB_ACTOR_PLATFORM_STEP
                                                         : x + WB_ACTOR_PLATFORM_STEP));

    if (be16(image + WB_ACTOR_PLATFORM_RIDDEN) == 0) {
        actor_platform_carry_followed(image, actor, followed, band);
    } else if (is_the_ridden_platform(image, actor)) {
        uint16_t rider = (uint16_t)field_w(image, followed, WB_ACTOR_X);

        set_field_w(image, followed, WB_ACTOR_X,
                    (uint16_t)(travelling_back(image, actor) ? rider - WB_ACTOR_PLATFORM_STEP
                                                             : rider + WB_ACTOR_PLATFORM_STEP));
        actor_platform_release_check(image, actor, followed, band);
    }
    platform_travel_step(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}

/* $6f3e — the SINKING one. It has no direction bit and no limit: WB_ACTOR_FIELD_24 counts the
 * frames it has been stood on, one per two pixels down, and it rises back a frame at a time the
 * moment nothing is riding it. */
uint32_t actor_behavior_type56(uint8_t *image, uint32_t actor) {
    uint32_t followed = actor_sprite_from_6ed8(image, actor);
    uint32_t band = sprite_6ed8_row(image, actor);

    if (be16(image + WB_ACTOR_PLATFORM_RIDDEN) == 0) {
        if (field_w(image, actor, WB_ACTOR_FIELD_24) != 0) {
            set_field_w(image, actor, WB_ACTOR_Y,
                        (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_Y)
                                   - WB_ACTOR_PLATFORM_STEP));
            set_field_w(image, actor, WB_ACTOR_FIELD_24,
                        (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_FIELD_24)
                                   - WB_ACTOR_PLATFORM_SINK_TICK));
        }
        actor_platform_carry_followed(image, actor, followed, band);
        return WB_ACTOR_DISPATCH_RAN;
    }

    if (!is_the_ridden_platform(image, actor))
        return WB_ACTOR_DISPATCH_RAN;

    set_field_w(image, followed, WB_ACTOR_Y,
                (uint16_t)((uint16_t)field_w(image, followed, WB_ACTOR_Y)
                           + WB_ACTOR_PLATFORM_STEP));
    set_field_w(image, actor, WB_ACTOR_Y,
                (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_Y)
                           + WB_ACTOR_PLATFORM_STEP));
    set_field_w(image, actor, WB_ACTOR_FIELD_24,
                (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_FIELD_24)
                           + WB_ACTOR_PLATFORM_SINK_TICK));
    actor_platform_release_blocked_rider(image, actor, followed);
    actor_platform_release_check(image, actor, followed, band);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slots 52 and 53 ($5b3c, $5be4): slot 51's two neighbours -----------------------------------
 *
 * ONE GRAMMAR WITH SLOT 51 AND THREE ENDINGS. All three open on bit 0 of WB_ACTOR_FLAGS2 as a
 * ONE-WAY SWITCH, then ask actor_followed_overlap_mask the same two questions in the same order —
 * a STRIKE tail-jumps into actor_stun_followed, a BODY overlap writes the inline damage byte, calls
 * actor_damage_followed and stamps WB_ACTOR_ST_BYTE — and what differs is entirely what happens
 * afterwards. Slot 51 falls until it is supported and then frees itself; slot 52 walks and animates
 * every frame and frees itself the moment it IS supported; slot 53 neither falls nor animates but
 * slides a fixed step and counts a timer down to its own end.
 *
 * THE SWITCH ARM IS THE FREE ARM in both of these, which is where they part from slot 51: `btst #0,
 * 9(a0) / bne` jumps straight to the exit rather than to a fall, so a record that has raised the
 * bit gives its slot back on the NEXT frame with nothing else run. The contact pair itself is
 * `switched_contact_took_the_frame`, which sits above slot 51 because that slot calls it first.
 */

/* $5bc8 / $5c5a — the exit both entrances of EITHER handler reach: the switch lowered and the slot
 * handed back. The two are the same two instructions in the same order; slot 53's has one more
 * below them, which is why that one wraps this rather than repeating it. */
static void switched_free_slot(uint8_t *image, uint32_t actor) {
    flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
    set_field_w(image, actor, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
}


/* $5b3c — the walker that dies on LANDING. Its step is not a constant: `moveq #0,d7 / move.b
 * 30(a0),d7` makes WB_ACTOR_FIELD_30 the pixel count, so the same byte the damage arm stamps
 * WB_ACTOR_ST_BYTE into is what a live record walks by. The probe's blocked/clear answer is
 * discarded — nothing follows the `bsr` — so a wall only stops the record by leaving its x alone. */
uint32_t actor_behavior_type52(uint8_t *image, uint32_t actor) {
    uint32_t step;

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        switched_free_slot(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }

    if (switched_contact_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;

    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    actor_hop_ascend_step(image, actor);

    step = field_b(image, actor, WB_ACTOR_FIELD_30);
    if (faces_left(image, actor))
        step_left(image, actor, step);
    else
        step_right(image, actor, step);

    /* The cursor is masked AFTER the read, so the frame comes out of a 256-byte window —
     * WB_ACTOR_TYPE52_FRAMES..+$ff, wholly inside the image — and only the STORE is bounded to the
     * eight words. `advance_frame_cursor` reads it through bus.h like every other computed
     * address. */
    set_field_b(image, actor, WB_ACTOR_FIELD_18,
                advance_frame_cursor(image, actor, WB_ACTOR_TYPE52_FRAMES,
                                     WB_ACTOR_TYPE52_MASK));

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT))
        switched_free_slot(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}


/* $d78 — TWELVE BYTES, and the one player-tier routine a monster slot reaches: `tst.w $1516 /
 * beq.w $e06 / rts`. While WB_TILE_33_MODE is set it writes nothing at all and returns; while it is
 * clear the original BRANCHES into WB_PLAYER_STEP_BODY, the body actor_behavior_type01_player's own
 * $d84 falls into, which this port does not have — so that arm is a boundary and not a result.
 *
 * Its other caller is the player handler, which is unported; slot 53 below is the reader that made
 * these three instructions worth reconstructing. */
uint32_t player_gate_on_1516(const uint8_t *image) {
    if (be16(image + WB_TILE_33_MODE) != 0)
        return WB_ACTOR_DISPATCH_RAN;
    return WB_PLAYER_STEP_BODY;
}

/* $5c5a — slot 53's exit, which is slot 52's plus the live flag lowered. */
static void type53_free_slot(uint8_t *image, uint32_t actor) {
    switched_free_slot(image, actor);
    wr16(image + WB_ACTOR_TYPE53_ALIVE, 0);
}

/* $5be4 — the slider, and the only handler in the tier that publishes a GLOBAL. Its first
 * instruction raises WB_ACTOR_TYPE53_ALIVE unconditionally — every frame, on every arm — and its
 * exit lowers it, so the word is "a type-53 record ran this frame and has not finished"; the one
 * reader is the `tst.w` at $454c, inside a handler this port does not have.
 *
 * It takes no map probe: actor_fall_and_settle is the only thing it asks about the ground, and its
 * step is an unconditional WB_ACTOR_TYPE53_STEP added straight to the x word. */
uint32_t actor_behavior_type53(uint8_t *image, uint32_t actor) {
    uint32_t boundary;
    uint8_t timer;
    uint16_t x;

    wr16(image + WB_ACTOR_TYPE53_ALIVE, WB_ACTOR_TYPE53_ALIVE_SET);

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        type53_free_slot(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }

    if (switched_contact_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;

    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    boundary = player_gate_on_1516(image);
    if (boundary != WB_ACTOR_DISPATCH_RAN)
        return boundary;

    x = (uint16_t)field_w(image, actor, WB_ACTOR_X);
    set_field_w(image, actor, WB_ACTOR_X,
                (uint16_t)(faces_left(image, actor) ? x - WB_ACTOR_TYPE53_STEP
                                                    : x + WB_ACTOR_TYPE53_STEP));
    set_field_w(image, actor, WB_ACTOR_SPRITE, WB_ACTOR_TYPE53_SPRITE);

    timer = field_b(image, actor, WB_ACTOR_FIELD_30);
    if (timer == 0) {
        type53_free_slot(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }
    set_field_b(image, actor, WB_ACTOR_FIELD_30, (uint8_t)(timer - 1));
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 60 ($6f7e): the record that turns into a moving platform ------------------------------
 *
 * THIRTY BYTES AND NO MOVEMENT AT ALL. It publishes WB_ACTOR_SPRITE_NONE every frame — so a type-60
 * record is invisible while it waits — and watches one word: WB_STATE_WORD_6F9C, which
 * set_state_6f9c_ffff ($10232, src/effects.c) raises and this is the only thing that lowers. On the
 * frame it finds it raised it consumes it and writes WB_ACTOR_TYPE60_BECOMES into its own
 * WB_ACTOR_TYPE, i.e. RETYPES ITSELF into slot 54 — so the next dispatch of this record runs
 * actor_behavior_type54 and it becomes the vertical moving platform.
 *
 * That closes batch 29's open question about the $36: it is a behaviour slot number, not an object
 * id, and test/test_behavior.py pins it against the image's own table rather than against this
 * paragraph. */
uint32_t actor_behavior_type60(uint8_t *image, uint32_t actor) {
    set_field_w(image, actor, WB_ACTOR_SPRITE, WB_ACTOR_SPRITE_NONE);
    if (be16(image + WB_STATE_WORD_6F9C) == 0)
        return WB_ACTOR_DISPATCH_RAN;

    wr16(image + WB_STATE_WORD_6F9C, 0);
    set_field_w(image, actor, WB_ACTOR_TYPE, WB_ACTOR_TYPE60_BECOMES);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 61 ($6f9e): the four-message sequence, and the way out of the game --------------------
 *
 * NOT A CREATURE. It plays song WB_ACTOR_TYPE61_SONG once, posts the four highest WB_TEXT_REQUEST
 * ids in the game one at a time as the FIRE button is pressed, and when the table runs out resets
 * a7 to the top of a 512 KB ST and `jmp`s to show_data_disk_prompt — a restart, not a return. Its
 * other caller is the copylock failure path's `jsr $6f9e.w` at $f56e (../names.txt), which is what
 * says what the four messages are for.
 *
 * The record's WB_ACTOR_FIELD_31 is the cursor and WB_ACTOR_TYPE61_ACTIVE the "the sequence is
 * running" byte. Nothing masks the cursor: `moveq #0,d0 / move.b 31(a0),d0 / lea 0(a1,d0.w),a1`
 * reads WB_ACTOR_TYPE61_MESSAGES + 0..255, a window of $7016..$7115 that stays inside the image but
 * leaves the five-byte table after four presses, so a record entered with a stale cursor posts
 * whatever byte of the code image it lands on. The game's own flow cannot: the opening frame writes
 * the cursor 0. */

/* $6fc2 — the four writes BOTH arms end in; the second arm reaches them by a `bne.s` backwards.
 * All four are FIXED absolute operands, so they are plain image stores; the only address this
 * handler computes is the message-table read below, and that one goes through bus.h. */
static void type61_post_message(uint8_t *image, uint8_t message) {
    image[WB_TEXT_REQUEST] = message;
    /* `clr.b $c034.l` over a WORD field: only WB_TEXT_LIFETIME_REQUEST's HIGH byte is cleared, so
     * the low one stands and the `tst.w` that reads it can still see a request (wonderboy.h). */
    image[WB_TEXT_LIFETIME_REQUEST] = 0;
    image[WB_TEXT_BOX_ACTIVE] = 0;
    image[WB_ACTOR_TYPE61_ACTIVE] = WB_ACTOR_TYPE61_ACTIVE_SET;
}

uint32_t actor_behavior_type61(uint8_t *image, uint32_t actor) {
    uint8_t cursor;
    uint8_t message;

    if (image[WB_ACTOR_TYPE61_ACTIVE] == 0) {
        /* `lea $17adc.l,a5 / jsr (a5)` — stub +0, whose `movem` pair is why nothing here has to
         * care what snd_play_song leaves in a register. */
        snd_play_song(image, WB_ACTOR_TYPE61_SONG);
        set_field_b(image, actor, WB_ACTOR_FIELD_31, 0);
        type61_post_message(image, WB_ACTOR_TYPE61_FIRST_MESSAGE);
        return WB_ACTOR_DISPATCH_RAN;
    }

    /* `jsr $682.w / tst.b d0 / bpl` — the rising-edge byte's SIGN bit, i.e. fire pressed this frame
     * and not last. Nothing else in the byte can hold the frame. */
    if ((joy1_newly_pressed(image) & (1u << WB_ACTOR_TYPE61_FIRE_BIT)) == 0)
        return WB_ACTOR_DISPATCH_RAN;

    /* `addq.b #1,31(a0)` then `move.b 31(a0),d0` — a read-modify-write and then a SECOND READ of
     * the same byte, not a register kept across. The two differ wherever the store did not land:
     * a record at an address bus.h refuses is written nowhere and read back as zero, so the
     * original posts message table entry 0 while a port holding the value in a local posts 1. */
    bump_field_b(image, actor, WB_ACTOR_FIELD_31);
    cursor = field_b(image, actor, WB_ACTOR_FIELD_31);

    message = bus_read_byte(image, addr_add(WB_ACTOR_TYPE61_MESSAGES, cursor));
    if (message != WB_ACTOR_TYPE61_MESSAGE_END) {
        type61_post_message(image, message);
        return WB_ACTOR_DISPATCH_RAN;
    }

    image[WB_ACTOR_TYPE61_ACTIVE] = 0;
    /* `movea.l #$80000,a7 / jmp $e494.l`: the stack is thrown away and the boundary is a TRANSFER,
     * so nothing below this ever runs and the a7 write is a register this port does not model. */
    return WB_SHOW_DATA_DISK_PROMPT;
}


/* --- slots 59 and 8 ($7044, $705a): two more ways into slot 7 ------------------------------------
 *
 * NEITHER IS A HANDLER OF ITS OWN. Slot 59 is twenty-two bytes and slot 8 is six, and both end in
 * WB_ACTOR_BEHAVIOR_TYPE07's body — slot 59 by `bra.w $7060` and slot 8 by simply running into it.
 * What each does first is raise ITS OWN BIT of WB_ACTOR_FIELD_30, which is how one shared body is
 * told which of its three table entries was dispatched.
 *
 * BOTH BOUNDARIES ARE GONE (batch 32). Through batch 31 each stopped at $7060 and reported that
 * address; the body below is reconstructed now, so each runs straight on into it and hands back
 * whatever it hands back. What crosses the join is memory alone — slot 59 leaves WB_TABLE_A32_SET
 * in a1 and slot 8 whatever the dispatcher's `movea.l (a1),a1` left, and $7060 reads neither. */
uint32_t actor_behavior_type59(uint8_t *image, uint32_t actor) {
    flag_set(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE59_MARK_BIT);
    /* `lea $21e6a.l,a1 / move.w #$15,8(a1)` — the A32 template table's FIRST record, addressed
     * directly rather than through WB_TABLE_PTR_21E8C, so which table is currently selected does
     * not steer this write. */
    wr16(image + WB_TABLE_A32_SET + WB_SPAWN_RESPAWN_KIND, WB_ACTOR_TYPE59_RESPAWN_KIND);
    return actor_behavior_type07(image, actor);
}

uint32_t actor_behavior_type08(uint8_t *image, uint32_t actor) {
    flag_set(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE08_MARK_BIT);
    return actor_behavior_type07(image, actor);
}


/* --- slots 47, 48 and 49 ($5928, $5972, $59d0): the rest of the $5a band -------------------------
 *
 * NONE OF THE THREE HAS A SPAWN GATE OR A CONTACT TEST, which is what the whole band has in common
 * with slot 50 and against slots 2..6: no `btst #2,9(a0)` in front, no actor_followed_overlap_mask,
 * no actor_hit_by_player_shot, and no arm that reaches actor_defeat_and_score. Each simply plays a
 * table until something in the record runs out and then writes WB_ACTOR_FREE_MARKER over its own x.
 */

/* $5928 — FORTY-TWO BYTES and the smallest live handler in the table after slot 8's six: no map
 * probe, no settle, no step, nothing but the cursor. The wrap is what ends the record — `move.b
 * d0,18(a0) / bne` reads the flags of the STORE, so the frame the sixteenth word is published on is
 * the frame after which the slot is handed back — and the countdown byte every other handler in
 * this band spends is never touched here. */
uint32_t actor_behavior_type47(uint8_t *image, uint32_t actor) {
    uint8_t stepped = advance_frame_cursor(image, actor, WB_ACTOR_TYPE47_FRAMES,
                                           WB_ACTOR_ANIM32_MASK);

    set_field_b(image, actor, WB_ACTOR_FIELD_18, stepped);
    if (stepped == 0)
        set_field_w(image, actor, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
    return WB_ACTOR_DISPATCH_RAN;
}

/* $5972 / $59d0 — the forty-two bytes slots 48 and 49 open with, spelt twice in the image and once
 * here. The last three instructions of it ARE actor_step_facing's body ($2f22) inline: step the way
 * WB_ACTOR_FLAG_SIDE_BIT points and `bchg` that bit when the probe answers WB_ACTOR_STEP_BLOCKED —
 * so a record in this band turns round at a wall rather than stopping at it.
 *
 * `move.w #$3,d7` sits AFTER the settle, so it replaces only the low word of the span
 * actor_fall_and_settle hands back; the probes read that word alone (map.h), which is why the step
 * is the constant it looks like and not slot 3's byte-wide surprise. */
static void settle_hop_and_step_facing(uint8_t *image, uint32_t actor, uint32_t step) {
    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    actor_hop_ascend_step(image, actor);
    actor_step_facing(image, actor, step);
}

/* $5972 — that walk, then slot 50's tail over a FOUR-word table. The two tails are the same SHAPE
 * and not the same bytes (this one steps its cursor `addi.b`/`andi.b` where slot 50 spells the word
 * forms), which is the distinction `animate_then_free_on_countdown`'s plate carries. */
uint32_t actor_behavior_type48(uint8_t *image, uint32_t actor) {
    settle_hop_and_step_facing(image, actor, WB_ACTOR_TYPE48_STEP);
    animate_then_free_on_countdown(image, actor, WB_ACTOR_TYPE48_FRAMES, WB_ACTOR_TYPE48_MASK);
    return WB_ACTOR_DISPATCH_RAN;
}

/* $59d0 — the same walk, then TWO ANIMATIONS OVER ONE CURSOR. WB_ACTOR_FIELD_31 is the phase byte
 * and WB_ACTOR_FIELD_18 is read ONCE, before the phase is tested, so whichever table runs indexes
 * the same offset; a record that changes phase mid-table therefore carries its cursor across.
 *
 * The two phases end differently, and neither ending is the other's. Phase one counts
 * WB_ACTOR_FIELD_30 down and `st 31(a0)` at zero — it cannot free the slot however long it runs.
 * Phase two ignores the countdown entirely and watches the cursor actor_advance_anim16 hands back
 * in d0: the frame it wraps to 0 lowers the phase byte and frees the slot. So the record's whole
 * life is "phase one until the timer expires, then exactly one pass of phase two".
 */
uint32_t actor_behavior_type49(uint8_t *image, uint32_t actor) {
    uint8_t cursor;

    settle_hop_and_step_facing(image, actor, WB_ACTOR_TYPE49_STEP);
    cursor = field_b(image, actor, WB_ACTOR_FIELD_18);

    if (field_b(image, actor, WB_ACTOR_FIELD_31) != 0) {
        /* `tst.b d0` on the returned cursor — the low byte alone, which is all $5a3c writes. */
        if ((uint8_t)actor_advance_anim16(image, actor,
                                          addr_add(WB_ACTOR_TYPE49_FRAMES_PHASE2, cursor),
                                          cursor) == 0) {
            set_field_b(image, actor, WB_ACTOR_FIELD_31, 0);
            set_field_w(image, actor, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
        }
        return WB_ACTOR_DISPATCH_RAN;
    }

    actor_advance_anim16(image, actor, addr_add(WB_ACTOR_TYPE49_FRAMES_PHASE1, cursor), cursor);
    if (tick_countdown30(image, actor) == 0)
        set_field_b(image, actor, WB_ACTOR_FIELD_31, WB_ACTOR_ST_BYTE);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- the SWOOP state machine ($72c2..$73cd): four states over WB_ACTOR_FIELD_22 ------------------
 *
 * ONE MACHINE, and behaviour slot 7's body is its only caller — the `jsr` through
 * WB_ACTOR_SWOOP_STATE_TABLE is the sole reference to any of these four addresses in the image.
 * A record acquires a target, flies a canned path at it, closes the last of the horizontal gap and
 * then climbs back to where it started, at which point the state byte is zero and it may acquire
 * again. WB_ACTOR_FIELD_24 is the path cursor and WB_ACTOR_FIELD_26 the launch y.
 */

/* $72c2 — state 0. It writes nothing at all unless every gate passes, and the gates are three: the
 * followed record within WB_ACTOR_SWOOP_X_REACH either side, at or BELOW the record (`bmi` on the
 * y difference), and at least WB_ACTOR_SWOOP_Y_FLOOR below it.
 *
 * `subq.w #8,d0 / bmi` is what makes the shift's index non-negative, so the four-entry table cannot
 * be indexed backwards; and `cmp.w #$40,d0 / ble` caps it above, so a drop past that takes
 * WB_ACTOR_SWOOP_PATH_FAR instead. The chosen path is stored as an OFFSET from
 * WB_ACTOR_SWOOP_PATHS rather than as an address, which is what lets it live in a word field. */
void actor_swoop_state0_acquire(uint8_t *image, uint32_t actor) {
    uint32_t followed;
    int16_t gap;
    int16_t drop;
    uint32_t path;

    actor_set_side_flag(image, actor);
    followed = followed_actor_record(image);

    gap = (int16_t)((uint16_t)field_w(image, actor, WB_ACTOR_X)
                    - (uint16_t)field_w(image, followed, WB_ACTOR_X));
    if (gap < -(int16_t)WB_ACTOR_SWOOP_X_REACH || gap > (int16_t)WB_ACTOR_SWOOP_X_REACH)
        return;

    drop = (int16_t)((uint16_t)field_w(image, followed, WB_ACTOR_Y)
                     - (uint16_t)field_w(image, actor, WB_ACTOR_Y));
    if (drop < 0)
        return;

    if (drop > (int16_t)WB_ACTOR_SWOOP_Y_NEAR) {
        path = WB_ACTOR_SWOOP_PATH_FAR;
    } else {
        drop = (int16_t)(drop - WB_ACTOR_SWOOP_Y_FLOOR);
        if (drop < 0)
            return;
        /* `lsr.w #4` is UNSIGNED and `lsl.w #2` scales to a longword; the `bmi` above is the whole
         * of what keeps the pair inside the four entries. */
        path = bus_read_long(image,
                             addr_add(WB_ACTOR_SWOOP_PATH_TABLE,
                                      (uint16_t)(((uint16_t)drop >> WB_ACTOR_SWOOP_Y_SHIFT)
                                                 * WB_ACTOR_SWOOP_PATH_ENTRY)));
    }

    set_field_w(image, actor, WB_ACTOR_FIELD_24, (uint16_t)(path - WB_ACTOR_SWOOP_PATHS));
    set_field_w(image, actor, WB_ACTOR_FIELD_26, (uint16_t)field_w(image, actor, WB_ACTOR_Y));
    set_field_b(image, actor, WB_ACTOR_FIELD_22, WB_ACTOR_SWOOP_RUN_PATH);
}

/* $7328 — state 1. One word PAIR of the path per frame: dx applied the way
 * WB_ACTOR_FLAG_SIDE_BIT points and dy added downward, then the advanced cursor written back.
 *
 * `adda.w d1,a1` SIGN-EXTENDS the cursor, so a record entered with a negative WB_ACTOR_FIELD_24
 * reads below the path blob; nothing bounds it and this reads it through bus.h like every other
 * computed address. On the sentinel the cursor is NOT written back — the state store is the whole
 * of that arm — so a record leaves state 1 with the offset of the word that ended it. */
void actor_swoop_state1_run_path(uint8_t *image, uint32_t actor) {
    uint32_t cursor = sign_ext16((uint16_t)field_w(image, actor, WB_ACTOR_FIELD_24));
    uint32_t at = addr_add(WB_ACTOR_SWOOP_PATHS, cursor);
    uint16_t dx = bus_read_word(image, at);
    uint16_t dy;
    uint16_t x;

    if ((int16_t)dx < 0) {
        set_field_b(image, actor, WB_ACTOR_FIELD_22, WB_ACTOR_SWOOP_HOME_X);
        return;
    }

    x = (uint16_t)field_w(image, actor, WB_ACTOR_X);
    set_field_w(image, actor, WB_ACTOR_X, (uint16_t)(faces_left(image, actor) ? x - dx : x + dx));

    dy = bus_read_word(image, addr_add(at, WB_ACTOR_SWOOP_PATH_DY));
    set_field_w(image, actor, WB_ACTOR_Y,
                (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_Y) + dy));
    set_field_w(image, actor, WB_ACTOR_FIELD_24, (uint16_t)(cursor + WB_ACTOR_SWOOP_PATH_STEP));
}

/* $7366 — state 2. WB_ACTOR_SWOOP_HOME_STEP pixels a frame toward the followed record's x, and the
 * arrival test is on the SIDE the record is walking: `bge` after stepping left and `ble` after
 * stepping right, both INCLUSIVE, so landing exactly on the target arrives.
 *
 * THE TWO `bchg #3,8(a0)` ARE A NO-OP PAIR and are spelt here because they are what the bytes do.
 * Both are byte read-modify-writes, so the original's ledger holds the address; the value it holds
 * is the one it started with, which is why no differential can separate this from dropping them. */
void actor_swoop_state2_home_x(uint8_t *image, uint32_t actor) {
    uint32_t followed = followed_actor_record(image);
    int16_t target = field_w(image, followed, WB_ACTOR_X);
    uint16_t x = (uint16_t)field_w(image, actor, WB_ACTOR_X);

    /* `subq.w #4,(a0) / cmp.w (a0),d0` — the compare RE-READS the word the step just stored, so a
     * record at an address bus.h refuses is compared against the zero the read answers and not
     * against the value the step computed. Batch 31's stale-register class, in this direction. */
    if (faces_left(image, actor)) {
        set_field_w(image, actor, WB_ACTOR_X, (uint16_t)(x - WB_ACTOR_SWOOP_HOME_STEP));
        if (target < field_w(image, actor, WB_ACTOR_X))
            return;
    } else {
        set_field_w(image, actor, WB_ACTOR_X, (uint16_t)(x + WB_ACTOR_SWOOP_HOME_STEP));
        if (target > field_w(image, actor, WB_ACTOR_X))
            return;
    }

    flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
    flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
    set_field_b(image, actor, WB_ACTOR_FIELD_22, WB_ACTOR_SWOOP_DESCEND);
}

/* $739e — state 3, and the machine's only map probe. It walks WB_ACTOR_SWOOP_DESCEND_STEP pixels
 * the way the side bit points, discarding the blocked/clear answer entirely — no `tst.b d0` follows
 * the `bsr`, so a wall stops the record only by leaving its x alone — and rises
 * WB_ACTOR_SWOOP_RISE pixels a frame until it is back at or above WB_ACTOR_FIELD_26. */
void actor_swoop_state3_descend(uint8_t *image, uint32_t actor) {
    if (faces_left(image, actor))
        step_left(image, actor, WB_ACTOR_SWOOP_DESCEND_STEP);
    else
        step_right(image, actor, WB_ACTOR_SWOOP_DESCEND_STEP);

    set_field_w(image, actor, WB_ACTOR_Y,
                (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_Y) - WB_ACTOR_SWOOP_RISE));
    /* `subq.w #2,2(a0) / cmp.w 2(a0),d0` — the launch test RE-READS the y the rise just stored,
     * the same way state 2's arrival test re-reads its x. */
    if (field_w(image, actor, WB_ACTOR_FIELD_26) >= field_w(image, actor, WB_ACTOR_Y))
        set_field_b(image, actor, WB_ACTOR_FIELD_22, WB_ACTOR_SWOOP_ACQUIRE);
}


/* --- slot 7 ($7060): the body three table rows share ---------------------------------------------
 *
 * 424 BYTES AND THREE ENTRANCES. Its own row enters with neither mark bit raised; slot 59's
 * prologue raises WB_ACTOR_TYPE59_MARK_BIT and slot 8's WB_ACTOR_TYPE08_MARK_BIT, and everything
 * below that reads WB_ACTOR_FIELD_30 is asking which row fired. The two bits are independent — a
 * record carrying both would take every marked arm — but nothing in the image raises both.
 */

/* $708e — the damage arm, and it is NOT an ending unless the record dies. `bset #0,9(a0)` is up
 * only across actor_damage_template_hitpoints and is lowered again immediately after, so the bit
 * this handler uses as a hit-animation switch elsewhere is a CALL-SCOPED flag here. The `btst #3,
 * 9(a0) / bne.w $6bb8` below it is the ordinary defeat tail; when it does not fire the frame falls
 * straight through into the sprite and the state below. */
static int type07_take_damage(uint8_t *image, uint32_t actor) {
    actor_face_followed_reset_22(image, actor);
    monster_enter_hit_animation(image, actor);
    actor_damage_template_hitpoints(image, actor);
    flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);

    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT))
        return 0;
    actor_defeat_and_score(image, actor);
    return 1;
}

/* $70d2 — the animation an UNMARKED record plays. The wrap is a SIGNED `cmpi.b #$c,23(a0) / blt`,
 * so it holds for 0..11 and lets a negative byte through; the game's own flow cannot produce one.
 *
 * THE LIST IS PICKED BY TWO OVERLAPPING WRITES OF a1, not by a four-way test. $74a0 goes in first,
 * WB_ACTOR_TYPE08_MARK_BIT replaces it with $74ee, and then the SIDE BIT decides whether either
 * stands: set keeps it, clear starts again from $74ba and lets the mark bit replace THAT with
 * $7508. So the side bit is the outer axis even though it is tested second. */
static uint32_t type07_frame_list(const uint8_t *image, uint32_t actor) {
    int marked = flag_is_set(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE08_MARK_BIT);

    if (faces_left(image, actor))
        return marked ? WB_ACTOR_TYPE07_FRAMES_MARKED_LEFT : WB_ACTOR_TYPE07_FRAMES_LEFT;
    return marked ? WB_ACTOR_TYPE07_FRAMES_MARKED_RIGHT : WB_ACTOR_TYPE07_FRAMES_RIGHT;
}

static void type07_animate(uint8_t *image, uint32_t actor) {
    /* Each of the three steps RE-READS the byte the one above it wrote — `addq.b #1,23(a0) /
     * cmpi.b #$c,23(a0) / move.b 23(a0),d0` — so a record at an address bus.h refuses publishes
     * frame 0 where a port holding the value in a local would publish the stepped one. */
    set_field_b(image, actor, WB_ACTOR_FIELD_23,
                (uint8_t)(field_b(image, actor, WB_ACTOR_FIELD_23) + 1));
    if ((int8_t)field_b(image, actor, WB_ACTOR_FIELD_23) >= (int8_t)WB_ACTOR_TYPE07_FRAME_COUNT)
        set_field_b(image, actor, WB_ACTOR_FIELD_23, 0);

    /* `lsl.w #1,d0` scales a WORD-wide cursor, so a byte above $7f reaches past the twelve words
     * rather than wrapping — which is why this one is not `publish_frame`'s byte offset. */
    set_field_w(image, actor, WB_ACTOR_SPRITE,
                bus_read_word(image,
                              addr_add(type07_frame_list(image, actor),
                                       (uint16_t)(field_b(image, actor, WB_ACTOR_FIELD_23)
                                                  * WB_ACTOR_ANIM_FRAME_BYTES))));
}

/* $7128 — the state `jsr`, which nothing bounds: `move.b 22(a0),d0 / lsl.w #2 / movea.l
 * 0(a1,d0.w),a1 / jsr (a1)`. The target is FETCHED out of the image like the behaviour dispatch's,
 * so a poked table is followed, and a state byte above 3 reads past the four entries and calls
 * whatever longword it lands on.
 *
 * THE ANSWER CANNOT BE THE ADDRESS ALONE, which is where this differs from
 * actor_dispatch_behavior: that one's 62 entries are all real code, while the span this reaches is
 * ordinary data and holds zeros — state byte 65 lands on $7594, whose longword is $00000000, and
 * that is WB_ACTOR_DISPATCH_RAN's own value. A single `uint32_t` would report "the state ran" for
 * a `jsr 0` and let the frame continue into both spawners. So the RAN/boundary answer is the
 * return and the address is an out-parameter; the address itself may legitimately be 0, and
 * behavior.h's own contract still cannot separate a boundary at 0 from a clean run — which is why
 * the caller stops here rather than leaving that to whoever reads its result. */
static int type07_run_state(uint8_t *image, uint32_t actor, uint32_t *boundary) {
    uint8_t state = field_b(image, actor, WB_ACTOR_FIELD_22);
    uint32_t target = bus_read_long(image,
                                    addr_add(WB_ACTOR_SWOOP_STATE_TABLE,
                                             (uint16_t)(state * WB_ACTOR_SWOOP_STATE_ENTRY)));

    switch (target) {
    case WB_ACTOR_SWOOP_STATE0: actor_swoop_state0_acquire(image, actor); break;
    case WB_ACTOR_SWOOP_STATE1: actor_swoop_state1_run_path(image, actor); break;
    case WB_ACTOR_SWOOP_STATE2: actor_swoop_state2_home_x(image, actor); break;
    case WB_ACTOR_SWOOP_STATE3: actor_swoop_state3_descend(image, actor); break;
    default:
        *boundary = target;
        return 0;
    }
    return 1;
}

/* $7184 / $71ce — the four writes BOTH spawners make into a fresh record. `move.l (a0),(a1)` copies
 * WB_ACTOR_X and WB_ACTOR_Y as ONE longword, which is why the dropper's `subi.w #$20,2(a1)` is a
 * separate instruction rather than part of the copy.
 *
 * THE ORDER IS NOT QUITE SHARED: the dropper interleaves that `subi.w` between the copy and the
 * type store ($71d0), where this helper leaves the rise to its caller AFTER all four. Nothing reads
 * either write in between, so the memory the two spellings leave is identical — an ordering the
 * write ledger is address-keyed over and no differential can separate, like the three already named
 * at the top of this file. */
static void type07_fill_shot(uint8_t *image, uint32_t actor, uint32_t shot) {
    bus_write_long(image, shot, bus_read_long(image, actor));
    set_field_w(image, shot, WB_ACTOR_TYPE, WB_ACTOR_TYPE07_SHOT_TYPE);
    set_field_b(image, shot, WB_ACTOR_FLAGS, field_b(image, actor, WB_ACTOR_FLAGS));
    bus_write_long(image, addr_add(shot, WB_ACTOR_HALF_WIDTH), WB_ACTOR_TYPE07_SHOT_SIZE);
}

/* `andi.b #mask,31(a0) / bne` — the cadence gate BOTH spawners end with, and the answer the branch
 * reads. The mask is applied IN MEMORY: the read is the `andi`'s own (so it sees whatever the
 * `addq.b` above it managed to store), the store is the masked byte, and the branch is on the ALU
 * RESULT rather than on a third look at the field.
 *
 * The computed value and a re-read agree unconditionally here, which is why the local is the form
 * that stays: bus.h guards reads and writes with ONE predicate, so a refused field reads back 0,
 * masks to 0 and stores nowhere — and 0 & mask is 0. Nothing separates the two spellings, and this
 * one models the instruction. */
static int cadence_reached_zero(uint8_t *image, uint32_t actor, uint8_t mask) {
    uint8_t masked = (uint8_t)(field_b(image, actor, WB_ACTOR_FIELD_31) & mask);

    set_field_b(image, actor, WB_ACTOR_FIELD_31, masked);
    return masked == 0;
}

/* $713c — the FIVE-SHOT burst slot 8's row arms. Answers whether the frame may continue: the one
 * arm that says no is a FAILED ALLOCATION, whose `beq.w $7206` leaves the whole routine and so
 * skips the dropper below as well.
 *
 * TWO THINGS THE ORDER DECIDES. The cursor is stepped BEFORE the state test, so it advances on
 * every frame of a swoop and not only on the frames that could fire; and `andi.b #$7f,31(a0)`
 * RE-READS the byte the `addq.b` above it wrote, so a record at an address bus.h refuses steps a
 * cursor the mask then reads back as zero — the batch-31 class, one field over.
 *
 * AND THE ALLOCATION IS INSIDE THE `dbf`. The loop branches back to the `bsr $1b8e` itself, so five
 * separate records are taken; only the velocity pointer carries across an iteration. */
static int type07_burst_spawn(uint8_t *image, uint32_t actor) {
    uint32_t velocities;
    unsigned shot_index;

    bump_field_b(image, actor, WB_ACTOR_FIELD_31);
    if (field_b(image, actor, WB_ACTOR_FIELD_22) != 0)
        return 1;
    if (!cadence_reached_zero(image, actor, WB_ACTOR_TYPE07_BURST_MASK))
        return 1;

    velocities = faces_left(image, actor) ? WB_ACTOR_TYPE07_BURST_LEFT
                                          : WB_ACTOR_TYPE07_BURST_RIGHT;
    for (shot_index = 0; shot_index <= WB_ACTOR_TYPE07_BURST_LAST; shot_index++) {
        uint32_t shot = actor_alloc_slot_high(image);

        if (shot == WB_ACTOR_ALLOC_NONE)
            return 0;
        type07_fill_shot(image, actor, shot);
        set_field_w(image, shot, WB_ACTOR_SPRITE, WB_ACTOR_TYPE07_BURST_SPRITE);
        bus_write_long(image, addr_add(shot, WB_ACTOR_FIELD_24),
                       bus_read_long(image, addr_add(velocities,
                                                     shot_index * WB_ACTOR_TYPE07_BURST_ENTRY)));
    }
    return 1;
}

/* $71a8 — the single dropper slot 59's row arms, and the frame's last act.
 *
 * THE ALLOCATION HAPPENS BEFORE THE CADENCE TEST, which is the arm's real shape: the first free
 * record of the high pool is looked up on EVERY frame this arm runs and thrown away on all but one
 * frame in WB_ACTOR_TYPE07_DROP_MASK + 1. Nothing is leaked by that — the allocators MARK NOTHING
 * (actor.h), and what makes a record no longer free is the `move.l (a0),(a1)` below overwriting its
 * WB_ACTOR_FREE_MARKER, which is also how the burst's five `bsr`s find five different slots. But a
 * failed lookup returns BEFORE `addq.b #1,31(a0)`, so the cursor does not advance on a full pool. */
static void type07_dropper_spawn(uint8_t *image, uint32_t actor) {
    uint32_t shot = actor_alloc_slot_high(image);

    if (shot == WB_ACTOR_ALLOC_NONE)
        return;

    bump_field_b(image, actor, WB_ACTOR_FIELD_31);
    if (!cadence_reached_zero(image, actor, WB_ACTOR_TYPE07_DROP_MASK))
        return;

    type07_fill_shot(image, actor, shot);
    set_field_w(image, shot, WB_ACTOR_Y,
                (uint16_t)((uint16_t)field_w(image, shot, WB_ACTOR_Y)
                           - WB_ACTOR_TYPE07_DROP_RISE));
    set_field_w(image, shot, WB_ACTOR_SPRITE, WB_ACTOR_TYPE07_DROP_SPRITE);
    set_field_w(image, shot, WB_ACTOR_FIELD_24, WB_ACTOR_TYPE07_DROP_VELOCITY);
    if (faces_left(image, actor))
        set_field_w(image, shot, WB_ACTOR_FIELD_26, WB_ACTOR_TYPE07_DROP_FIELD_26);
}

uint32_t actor_behavior_type07(uint8_t *image, uint32_t actor) {
    uint32_t boundary;

    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        /* `bsr.s $701c / bra.w $69fe` — the only arm of this handler that ends on a tail jump. */
        actor_face_followed_reset_22(image, actor);
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
        if (type07_take_damage(image, actor))
            return WB_ACTOR_DISPATCH_RAN;
        break;
    case MONSTER_UNTOUCHED:
        break;
    }

    /* $70ae — a record marked by slot 59's row holds a constant frame instead of animating, and
     * the SPRITE it holds is the one the side bit names. Both arms then skip to the state. */
    if (flag_is_set(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE59_MARK_BIT)) {
        set_field_w(image, actor, WB_ACTOR_SPRITE, WB_ACTOR_TYPE07_SPRITE_LEFT);
        if (!faces_left(image, actor))
            set_field_w(image, actor, WB_ACTOR_SPRITE, WB_ACTOR_TYPE07_SPRITE_RIGHT);
    } else {
        type07_animate(image, actor);
    }

    if (!type07_run_state(image, actor, &boundary))
        return boundary;

    if (flag_is_set(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE08_MARK_BIT)
        && !type07_burst_spawn(image, actor))
        return WB_ACTOR_DISPATCH_RAN;

    if (flag_is_set(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE59_MARK_BIT))
        type07_dropper_spawn(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- $517a..$5207: what a collected record pays out ----------------------------------------------
 *
 * Three routines nothing but this tier calls, and their whole subject is the two shipped
 * accumulators and one shipped STRING. They live here rather than in src/hud.c because their
 * addresses are inside the behaviour band — $517a..$5207 sits between slot 32's body and slot 33's
 * entry — and both of the payout's callers are dispatch rows, which is `sound_request_9`'s
 * argument one file up.
 *
 * THE NAMES ../names.txt CARRIED FOR TWO OF THEM WERE WRONG, and the same instruction is behind
 * both corrections: `abcd`. out/wonderboy_dis.txt prints the `c101` at $51d4 as `and.b d0,d1` —
 * the disassembler bug that plate already documents for $b562's `c308`/`8308` — but opmode 100 with
 * an ea mode of 000 is `abcd Dy,Dx` and not an AND, which Ghidra's own decompile agrees with
 * (`bcdAdjust` in ../decomp.c). So $51ac does not MASK the caller's d0, it adds a packed-BCD one to
 * four INTO it and answers in d0; and $51d8 does not unpack four digits, it draws TWO with the
 * leading zero blanked.
 */

/* $51d8 — the digits, tens first. `andi.w #$f` selects the units, `addi.b #$30` makes it ASCII, and
 * `ror.w #4,d0` then brings the tens nibble down for the same treatment — except that a ZERO tens
 * digit is written as a space, which is what leaves a one-digit amount left-blanked in the message.
 * The two characters are inside a shipped string, so the box the payout posts reads the amount. */
void text_write_gold_digits_a2ac(uint8_t *image, uint32_t entry_d0) {
    uint16_t amount = (uint16_t)entry_d0;
    uint8_t tens = (uint8_t)((amount >> WB_BCD_DIGIT_BITS) & WB_BCD_DIGIT_MASK);

    image[WB_TEXT_GOLD_DIGITS + 1] = (uint8_t)((amount & WB_BCD_DIGIT_MASK) + WB_TEXT_DIGIT_ZERO);
    image[WB_TEXT_GOLD_DIGITS] = tens == 0 ? (uint8_t)WB_TEXT_DIGIT_BLANK
                                           : (uint8_t)(tens + WB_TEXT_DIGIT_ZERO);
}

/* $51ac — a one-to-four draw added to `entry_d0` in packed BCD.
 *
 * THE FOUR READS ARE ORDERED AND TWO OF THEM ARE HARDWARE, which is why they are four statements
 * and not one sum: the kit compares both cores' ordered hardware read stream, so $ff8209 must be
 * read before $ff8207 here as it is in the image, and C would otherwise be free to swap them.
 * WB_ACTOR_FOLLOWED_DEFAULT's two bytes are its x word read a byte at a time, so the non-machine
 * half of the entropy is where the player is standing.
 *
 * THE EXTEND BIT THE `abcd` FOLDS IN IS ITS OWN. `addi`/`andi` leave X alone but `addq.b #1,d1` sets
 * it, and the byte it steps is WB_BCD_RANDOM_MASK-ed to 0..3 — so the carry is always 0 and no
 * caller's X can reach the addition. What this routine LEAVES in X is a different matter: it is the
 * BCD carry out, `*exit_extend` hands it back, and $517a's next call folds it in (hud.h). */
uint32_t bcd_add_random_1_to_4(const uint8_t *image, uint32_t entry_d0, unsigned *exit_extend) {
    unsigned extend = 0;
    uint8_t draw = hw_read8(OS_HW_SHIFTER_VCOUNT_LOW);

    draw = (uint8_t)(draw + hw_read8(OS_HW_SHIFTER_VCOUNT_MID));
    draw = (uint8_t)(draw + image[WB_ACTOR_FOLLOWED_DEFAULT]);
    draw = (uint8_t)(draw + image[WB_ACTOR_FOLLOWED_DEFAULT + 1]);
    draw = (uint8_t)((draw & WB_BCD_RANDOM_MASK) + 1);

    /* `abcd d1,d0` writes d0's LOW BYTE and nothing above it, so both of the caller's other halves
     * come back — the low word's high byte as well as the register's own. */
    uint8_t sum = abcd_byte(draw, (uint8_t)entry_d0, &extend);

    *exit_extend = extend;
    return set_low_word(entry_d0, set_low_byte((uint16_t)entry_d0, sum));
}

/* $517a — the payout itself. The award is a WORD out of the scene descriptor and every consumer
 * below reads a different width of it: `bcd_add_random_1_to_4` and the digits take the low BYTE,
 * `bcd_add_counter_bd6e` stages the whole WORD, and the score's addend is a constant longword that
 * has nothing to do with the amount at all. */
void hud_award_gold_from_descriptor(uint8_t *image) {
    uint32_t descriptor = be32(image + WB_RECORD_PTR_10424);
    uint32_t award = bus_read_word(image, addr_add(descriptor, WB_SCENE_GOLD_AWARD));
    unsigned draw_carry;

    /* THE CHAIN, $5184 -> $5188: the draw's `abcd d1,d0` is the instruction before the `bsr`, so
     * its carry is the counter's entry X. */
    award = bcd_add_random_1_to_4(image, award, &draw_carry);
    bcd_add_counter_bd6e(image, award, draw_carry);
    text_write_gold_digits_a2ac(image, award);
    /* ...and NOT a chain at $5196: the digits above are the last thing to write X, and on both of
     * their exits that is `addi.b #$30` on a nibble masked to $0..$f, which cannot carry out of
     * $30..$3f. The counter's own carry-out is dead here — $b562's `rts` is followed by the `bsr`
     * to those digits, not by the score add. */
    bcd_add_score_bd70(image, WB_ACTOR_COLLECT_SCORE, WB_BCD_ENTRY_EXTEND_CLEAR);

    /* The id-and-lifetime pair, inline for src/actor.c's stated reason rather than shared: making
     * it one symbol across three modules would export a function to save one `wr16`, and the three
     * sites do not agree anyway — src/scene.c posts a lifetime of zero on its speech arm and
     * `type61_post_message` above CLEARS only the high byte of this word. */
    image[WB_TEXT_REQUEST] = WB_TEXT_MESSAGE_GOLD_GET;
    wr16(image + WB_TEXT_LIFETIME_REQUEST, WB_TEXT_LIFETIME_DEFAULT);
}


/* --- slots 28, 30 and 31 ($4e38, $4eca, $4f9c): the collectables -------------------------------
 *
 * ONE SHAPE AND THREE PAYOUTS. Each opens (or, in slot 31's case, arrives) at `bsr $5c6e / btst
 * #1,d0` — the FOOTPRINT bit alone, so what collects them is the followed record standing on them
 * and not a shot — fires WB_ACTOR_REQUEST9_SFX, pays, and writes WB_ACTOR_FREE_MARKER over its own
 * x. Each also runs WB_ACTOR_FIELD_12 down and raises WB_ACTOR_FLAG_FLICKER_BIT on the way, so an
 * uncollected one blinks out; slots 30 and 31 count that field as a WORD and slot 28 as a BYTE.
 */

/* `bclr #6,8(a0)` then the free marker: the flicker stopped and the slot handed back, in that
 * order. TWO of the three handlers end this way and slot 28 does NOT — its expiry `bset`s the bit
 * instead of clearing it, so its two free sites are a bare free marker and route nowhere near here.
 * Slot 30 spells the pair inline because its `clr.w` of the global cursor sits BETWEEN the two. */
static void collectable_free_slot(uint8_t *image, uint32_t actor) {
    flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT);
    set_field_w(image, actor, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
}

/* `bsr $5c6e / btst #1,d0` — bit 1 and nothing else. This is NOT `monster_contact`: no
 * actor_hit_by_player_shot runs in front of it and bits 0 and 2 are never read, which is the whole
 * difference between a collectable and a creature. */
static int followed_stood_on_it(uint8_t *image, uint32_t actor) {
    return (actor_followed_overlap_mask(image, actor)
            & (1u << WB_ACTOR_OVERLAP_BODY_BIT)) != 0;
}

/* `cmpi.w #$14,12(a0) / bne / bset #6,8(a0)` — the flicker started on ONE value of the countdown
 * rather than below a threshold, so a record seeded past it never flickers at all. Slots 30 and 31
 * spell it identically, in the same place in their frame. */
static void flicker_when_field_12_reaches_the_mark(uint8_t *image, uint32_t actor) {
    if (field_w(image, actor, WB_ACTOR_FIELD_12) == (int16_t)WB_ACTOR_FLICKER_AT_FIELD_12)
        flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT);
}

/* `subq.w #1,12(a0) / bne` — a memory read-modify-write whose branch reads the ALU's flags, so what
 * decides is the value computed and not a re-read of the field. Answers whether the record is out
 * of time. The `cmpi.w` above it is a SECOND read of the same word, which is why that one is not
 * folded in here. */
static int field_12_word_ran_out(uint8_t *image, uint32_t actor) {
    uint16_t left = (uint16_t)(field_w(image, actor, WB_ACTOR_FIELD_12) - 1);

    set_field_w(image, actor, WB_ACTOR_FIELD_12, left);
    return left == 0;
}

/* $4e98's `tst.w d0` — the ONE step test in this tier that reads the WORD.
 *
 * Every other one is `tst.b d0` (`step_was_blocked` above), and the difference is not cosmetic: the
 * probes leave a map COLUMN — or a clamp limit, or a parked x — in the byte ABOVE the outcome
 * (map.h), so this arm turns the record round only when that byte is zero too. A step blocked at
 * column $10 reports $1000 and the `bchg` does not fire; a step blocked at column 0 reports $0000
 * and it does. Both are reachable with the game's own geometry — the right-edge clamp reports the
 * level's own width, and a record walking off the left edge reports a NEGATIVE column.
 *
 * The constant is WB_ACTOR_STEP_BLOCKED at the WIDER operand and not a bare zero: what the `tst.w`
 * answers is "blocked AND the column above it was zero too", which is why the two helpers name the
 * same value and read as one question asked at two widths. */
static int step_word_was_blocked_at_column_0(uint32_t step_outcome) {
    return (uint16_t)step_outcome == WB_ACTOR_STEP_BLOCKED;
}

/* $4e78 — the walk slot 28 takes while it waits, and the reason it is a helper is the register:
 * `moveq #$0,d7 / move.b 31(a0),d7` clears the WHOLE of d7 before the byte lands in it, so unlike
 * slots 3 and 6 the step carries nothing of what actor_fall_and_settle left behind. Slot 52 spells
 * the same two instructions over WB_ACTOR_FIELD_30. */
static void type28_walk_and_turn(uint8_t *image, uint32_t actor) {
    uint32_t step = field_b(image, actor, WB_ACTOR_FIELD_31);
    uint32_t outcome;

    if (step == 0)
        return;

    outcome = step_facing(image, actor, step);
    if (step_word_was_blocked_at_column_0(outcome))
        flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);

    set_field_b(image, actor, WB_ACTOR_FIELD_31,
                (uint8_t)(field_b(image, actor, WB_ACTOR_FIELD_31) - 1));
}

/* $4e38 — 144 bytes. THE COLLECT ARM IS GATED TWICE: the footprint bit AND
 * WB_ACTOR_FLAG_MOVING_BIT down, so a record that is mid-hop cannot be picked up.
 *
 * THE COUNTDOWN IS A BYTE HERE, and it expires twice. `subq.b #1,12(a0) / bne` runs the frame out;
 * on zero, `bset #6,8(a0) / bne` reads the bit the instruction just OVERWROTE — so the first expiry
 * finds the flicker down, raises it and reloads the byte, and the second finds it up and frees the
 * slot. That is what gives an uncollected record WB_ACTOR_TYPE28_FIELD_12_RELOAD flickering frames.
 *
 * THE TWO ACCUMULATORS RUN BACK TO BACK, `bsr $b562` then `bsr $b5a2` with only a `move.l #imm,d0`
 * between them — so the score's first `abcd` folds in the carry the counter's last one left. The
 * port CARRIES that (hud.h), and test_behavior.py drives a counter within WB_ACTOR_TYPE28_GOLD of
 * overflowing four digits, which is the seed that separates it from a folded-in zero. */
uint32_t actor_behavior_type28(uint8_t *image, uint32_t actor) {
    uint8_t left;
    int was_flickering;

    if (followed_stood_on_it(image, actor)
        && !flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT)) {
        sound_request_9(image);
        set_field_w(image, actor, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
        /* THE CHAIN, $4e5a -> $4e64. The counter's own entry X is the sound trigger's, which is not
         * readable off these bytes — it is pinned by the differential instead (test_behavior.py).
         * Its carry-out is the score's entry X: `move.l #$20,d0` at $4e5e does not touch X. */
        unsigned gold_carry = bcd_add_counter_bd6e(image, WB_ACTOR_TYPE28_GOLD,
                                                   WB_BCD_ENTRY_EXTEND_CLEAR);
        bcd_add_score_bd70(image, WB_ACTOR_COLLECT_SCORE, gold_carry);
        return WB_ACTOR_DISPATCH_RAN;
    }

    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    actor_hop_ascend_step(image, actor);
    actor_relaunch_and_anim_5160(image, actor);
    type28_walk_and_turn(image, actor);

    /* `subq.b #1,12(a0) / bne` — one read-modify-write whose branch reads the ALU's flags, the BYTE
     * spelling of `field_12_word_ran_out` above. The store happens on every path out. */
    left = (uint8_t)(field_b(image, actor, WB_ACTOR_FIELD_12) - 1);
    set_field_b(image, actor, WB_ACTOR_FIELD_12, left);
    if (left != 0)
        return WB_ACTOR_DISPATCH_RAN;

    /* `bset #6,8(a0) / bne` — ONE write, and the branch reads the bit the write overwrote. Both
     * arms therefore leave the bit up and only the OLD value chooses between them. */
    was_flickering = flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT);
    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT);
    if (was_flickering) {
        set_field_w(image, actor, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
        return WB_ACTOR_DISPATCH_RAN;
    }
    set_field_b(image, actor, WB_ACTOR_FIELD_12, WB_ACTOR_TYPE28_FIELD_12_RELOAD);
    return WB_ACTOR_DISPATCH_RAN;
}

/* $4ee4 — THE MISSING STORE, reproduced. `move.w $b6fa,d0 / addq.w #4,d0 / cmp.w $b6f8,d0 / blt`
 * computes the topped-up meter and then writes it NOWHERE: the only arm that stores anything is the
 * one where the sum reached WB_HUD_METER_MAX, and it stores the maximum rather than the sum. So a
 * collected slot-30 record refills the meter only when the player was already within
 * WB_ACTOR_TYPE30_METER_STEP of full, and does nothing at all otherwise. That is a shipped bug —
 * `hud_meter_add_clamped` ($b6fe) is the routine that does this properly and this handler does not
 * call it — and faithfulness is the rule (README), so the sum is computed and dropped here too. */
static void type30_top_up_the_meter(uint8_t *image) {
    uint16_t topped = (uint16_t)(be16(image + WB_HUD_METER_VALUE) + WB_ACTOR_TYPE30_METER_STEP);

    if ((int16_t)topped >= (int16_t)be16(image + WB_HUD_METER_MAX))
        wr16(image + WB_HUD_METER_VALUE, be16(image + WB_HUD_METER_MAX));
}

/* $4f14 — the drift, and the one animation cursor in this tier that is NOT a record field.
 * WB_ACTOR_TYPE30_CURSOR is a global word, so two live type-30 records step the same table together
 * and a record spawned mid-cycle joins it wherever the other left it. The cursor is masked AFTER
 * the read, so the fetch reaches WB_ACTOR_TYPE30_DRIFT + a SIGN-EXTENDED word and only the store is
 * bounded to the 32 entries — the same shape slot 52's frame cursor has. */
static void type30_drift_step(uint8_t *image, uint32_t actor) {
    uint16_t cursor = be16(image + WB_ACTOR_TYPE30_CURSOR);
    uint16_t drift = bus_read_word(image, addr_add(WB_ACTOR_TYPE30_DRIFT, sign_ext16(cursor)));

    set_field_w(image, actor, WB_ACTOR_X,
                (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_X) + drift));
    wr16(image + WB_ACTOR_TYPE30_CURSOR,
         (uint16_t)((cursor + WB_ACTOR_TYPE30_DRIFT_STRIDE) & WB_ACTOR_TYPE30_DRIFT_MASK));
}

/* $4eca — 142 bytes. It hovers: WB_ACTOR_TYPE30_DRIFT's triangle moves it left and right by a net
 * zero over 32 frames, and `tst.b $712.w / beq` lifts it one pixel on the frames WB_FRAME_TOGGLE is
 * nonzero — a BYTE test on the HIGH half of that word, so it reads the flag the way flip_screen
 * writes it ($0000 or $ffff) and nothing narrower would do.
 *
 * IT CANNOT BE COLLECTED IMMEDIATELY. `addq.b #1,30(a0)` counts WB_ACTOR_FIELD_30 UP every waiting
 * frame and `cmpi.b #$a,30(a0) / blt` refuses the collect below WB_ACTOR_TYPE30_COLLECT_MIN — a
 * SIGNED compare, so a byte that has counted past $7f is refused again until it wraps back. */
uint32_t actor_behavior_type30(uint8_t *image, uint32_t actor) {
    if (followed_stood_on_it(image, actor)
        && (int8_t)field_b(image, actor, WB_ACTOR_FIELD_30)
           >= (int8_t)WB_ACTOR_TYPE30_COLLECT_MIN) {
        sound_request_9(image);
        type30_top_up_the_meter(image);
    } else {
        bump_field_b(image, actor, WB_ACTOR_FIELD_30);
        if (image[WB_FRAME_TOGGLE] != 0)
            set_field_w(image, actor, WB_ACTOR_Y,
                        (uint16_t)(field_w(image, actor, WB_ACTOR_Y) - 1));
        type30_drift_step(image, actor);

        flicker_when_field_12_reaches_the_mark(image, actor);
        if (!field_12_word_ran_out(image, actor))
            return WB_ACTOR_DISPATCH_RAN;
    }

    /* $4f46 — the ending BOTH arms reach, and the cursor is cleared between the two writes
     * `collectable_free_slot` makes rather than after them. */
    flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT);
    wr16(image + WB_ACTOR_TYPE30_CURSOR, 0);
    set_field_w(image, actor, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
    return WB_ACTOR_DISPATCH_RAN;
}

/* $4f9c — 78 bytes, $4f9c..$4fe9, and it has TWO EXITS. Its own `rts` at $4fe8 is the last of those
 * bytes and both the collect and the free arm reach it; the LIVE-countdown arm leaves instead, by
 * the `bne.w $4fea` at $4fda, for actor_select_sprite_by_flag — a routine of its own with a second
 * caller at $54d6, already reconstructed, whose `rts` returns to the dispatcher. What bounds this
 * handler at 78 bytes is THAT routine's entry, not the branch: a scan running on to the next `rts`
 * gives it 146 and swallows those 48 bytes whole.
 *
 * THE COLLECT ARM IS SKIPPED WHILE THE RECORD IS MOVING, the same `btst #0,8(a0)` gate slot 28 has
 * — but here the gate jumps STRAIGHT to the countdown, so a moving record still ages. */
uint32_t actor_behavior_type31(uint8_t *image, uint32_t actor) {
    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    actor_hop_ascend_step(image, actor);
    flicker_when_field_12_reaches_the_mark(image, actor);

    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT)
        && followed_stood_on_it(image, actor)) {
        sound_request_9(image);
        hud_award_gold_from_descriptor(image);
        collectable_free_slot(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }

    if (field_12_word_ran_out(image, actor)) {
        collectable_free_slot(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }

    actor_select_sprite_by_flag(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}
