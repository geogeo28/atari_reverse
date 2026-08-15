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
#include "effects.h"
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

/* ...and the same four instructions with the two arms EXCHANGED, which is a step AWAY from the
 * followed record: bit 3 SET means it is to the actor's LEFT (actor.h, $67c2), so the set arm walks
 * right. SIX routines spell it and TWO BRANCH POLARITIES do: slots 10, 13, 18, 20, 25 and 27 are
 * `btst #3,8(a0) / beq -> $10a2` with `bsr $1170` falling through ($313e, $35a0, $3dca, $422e,
 * $4a5c and $4d74), while $2fe8 is `bne -> $1170` with `bsr $10a2` falling through — the same
 * mapping written the other way up. */
static void step_away_without_facing(uint8_t *image, uint32_t actor, uint32_t step) {
    if (faces_left(image, actor))
        step_right(image, actor, step);
    else
        step_left(image, actor, step);
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
    {WB_ACTOR_BEHAVIOR_TYPE09, actor_behavior_type09},
    {WB_ACTOR_BEHAVIOR_TYPE10, actor_behavior_type10},
    {WB_ACTOR_BEHAVIOR_TYPE11, actor_behavior_type11},
    {WB_ACTOR_BEHAVIOR_TYPE12, actor_behavior_type12},
    {WB_ACTOR_BEHAVIOR_TYPE13, actor_behavior_type13},
    {WB_ACTOR_BEHAVIOR_TYPE14, actor_behavior_type14},
    {WB_ACTOR_BEHAVIOR_TYPE15, actor_behavior_type15},
    {WB_ACTOR_BEHAVIOR_TYPE16, actor_behavior_type16},
    {WB_ACTOR_BEHAVIOR_TYPE17, actor_behavior_type17},
    {WB_ACTOR_BEHAVIOR_TYPE18, actor_behavior_type18},
    {WB_ACTOR_BEHAVIOR_TYPE19, actor_behavior_type19},
    {WB_ACTOR_BEHAVIOR_TYPE20, actor_behavior_type20},
    {WB_ACTOR_BEHAVIOR_TYPE21, actor_behavior_type21},
    {WB_ACTOR_BEHAVIOR_TYPE22, actor_behavior_type22},
    {WB_ACTOR_BEHAVIOR_TYPE23, actor_behavior_type23},
    {WB_ACTOR_BEHAVIOR_TYPE24, actor_behavior_type24},
    {WB_ACTOR_BEHAVIOR_TYPE25, actor_behavior_type25},
    {WB_ACTOR_BEHAVIOR_TYPE26, actor_behavior_type26},
    {WB_ACTOR_BEHAVIOR_TYPE27, actor_behavior_type27},
    {WB_ACTOR_BEHAVIOR_TYPE28, actor_behavior_type28},
    /* Slot 29's two bytes are the same `rts` slots 0 and 58 hold, at an address of its own — so
     * one more row and no more code. */
    {WB_ACTOR_BEHAVIOR_TYPE29, actor_behavior_null},
    {WB_ACTOR_BEHAVIOR_TYPE30, actor_behavior_type30},
    {WB_ACTOR_BEHAVIOR_TYPE31, actor_behavior_type31},
    {WB_ACTOR_BEHAVIOR_TYPE32, actor_behavior_type32},
    {WB_ACTOR_BEHAVIOR_TYPE33, actor_behavior_type33},
    {WB_ACTOR_BEHAVIOR_TYPE34, actor_behavior_type34},
    {WB_ACTOR_BEHAVIOR_TYPE35, actor_behavior_type35},
    {WB_ACTOR_BEHAVIOR_TYPE36, actor_behavior_type36},
    {WB_ACTOR_BEHAVIOR_TYPE37, actor_behavior_type37},
    {WB_ACTOR_BEHAVIOR_TYPE38, actor_behavior_type38_pickup},
    {WB_ACTOR_BEHAVIOR_TYPE39, actor_behavior_type39},
    {WB_ACTOR_BEHAVIOR_TYPE40, actor_behavior_type40},
    {WB_ACTOR_BEHAVIOR_TYPE41, actor_behavior_type41},
    {WB_ACTOR_BEHAVIOR_TYPE42, actor_behavior_type42},
    {WB_ACTOR_BEHAVIOR_TYPE43, actor_behavior_type43},
    {WB_ACTOR_BEHAVIOR_TYPE44, actor_behavior_type44},
    {WB_ACTOR_BEHAVIOR_TYPE45, actor_behavior_type45},
    {WB_ACTOR_BEHAVIOR_TYPE46, actor_behavior_type46},
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
    {WB_ACTOR_BEHAVIOR_TYPE57, actor_behavior_type57},
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
    step_away_without_facing(image, actor, WB_ACTOR_STEP_AWAY_PIXELS);
}

/* `bset #0,8(a0) / bset #1,8(a0) / bclr #2,8(a0) / move.b #n,11(a0)` — actor_start_motion_at_speed's
 * three writes with the speed a LITERAL rather than a register, which is why the four sites that
 * spell it in this file ($2f46, $2fb0, $3528 and $357a) call nothing. The raises come first here and
 * $2af2 clears first; the three bits are disjoint and the differential compares the byte the frame
 * ENDS on, so no case can see the order.
 *
 * IT IS NOT actor_start_motion_at_speed, for two reasons that both matter. The original does not
 * CALL that routine at any of these four sites — the entry pins hold the inline bytes — and this
 * file writes a record through bus.h (see the header) where src/actor.c writes the buffer directly,
 * so the two spellings part on any record the bus refuses. (src/actor.c's `actor_turn_and_launch`
 * is the same shape again over its own record, for the same reason.) */
static void launch_at_inline_speed(uint8_t *image, uint32_t actor, uint8_t speed) {
    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT);
    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_LAUNCHED_BIT);
    flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
    set_field_b(image, actor, WB_ACTOR_SPEED, speed);
}

/* $2f86 — the countdown, and what running out does. The relaunch is `launch_at_inline_speed` plus a
 * cursor reset, and it happens only for a SUPPORTED record that `rng_next` gives permission to: one
 * bit of the generator's word decides.
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

    launch_at_inline_speed(image, actor, WB_ACTOR_TIMER30_SPEED);
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

/* $68a6 and $58f2 — the WB_ACTOR_ANIM_5160_FRAMES step itself, which the stepper below and
 * behaviour slot 46 spell as the same five instructions over the same table and the same record
 * byte. `move.w (a1)+,6(a0)` publishes at the cursor and the `cmpi.w` then reads the word ONE
 * FRAME AHEAD, so the WB_ACTOR_ANIM_5160_END word is never itself drawn.
 *
 * The advance is committed BEFORE the terminator is read, and the reset then overwrites it — two
 * writes to the same byte on the wrapping path, which is what the original does. */
static void anim_5160_publish_and_step(uint8_t *image, uint32_t actor) {
    uint8_t cursor = field_b(image, actor, WB_ACTOR_FIELD_18);
    uint32_t frame = addr_add(WB_ACTOR_ANIM_5160_FRAMES, cursor);

    set_field_w(image, actor, WB_ACTOR_SPRITE, bus_read_word(image, frame));
    set_field_b(image, actor, WB_ACTOR_FIELD_18, (uint8_t)(cursor + WB_ACTOR_ANIM_FRAME_BYTES));
    if (bus_read_word(image, addr_add(frame, WB_ACTOR_ANIM_FRAME_BYTES)) == WB_ACTOR_ANIM_5160_END)
        set_field_b(image, actor, WB_ACTOR_FIELD_18, 0);
}

/* $6872 — that step with a relaunch in front of it.
 *
 * THE COUNTDOWN STOPS ON WB_ACTOR_ANIM_5160_HOLD, NOT ON ZERO: `cmpi.b #$1,30(a0) / beq` skips the
 * whole arm while the byte already holds it, so the launch fires on the tick that takes it from 2
 * to 1 and never again — and the speed the record launches at is that same 1. A byte of 0 is not
 * the stop value, so it wraps to $ff and counts the long way round. */
void actor_relaunch_and_anim_5160(uint8_t *image, uint32_t actor) {
    uint8_t timer = field_b(image, actor, WB_ACTOR_FIELD_30);

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT)
        && timer != WB_ACTOR_ANIM_5160_HOLD) {
        timer = (uint8_t)(timer - 1);
        set_field_b(image, actor, WB_ACTOR_FIELD_30, timer);
        set_field_b(image, actor, WB_ACTOR_SPEED, timer);
        flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
        flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT);
        flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_LAUNCHED_BIT);
    }

    anim_5160_publish_and_step(image, actor);
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

/* THE X FLAG $5c6e HANDS BACK, which slot 23's `bsr $b582` two calls later reads as its BCD entry
 * extend (hud.h's site table). It is not a claim here but a reading: the bit-2 block above is the
 * last arithmetic on EVERY path to the routine's single `rts` at $5d60, and `bset`, `cmp` and
 * `tst` leave X alone. So
 *   * for the two sprite ids that have a reach point, `subi.w #$9,d6` at $5d40 on the followed
 *     record's y is the last writer, and X is its BORROW;
 *   * for every other sprite the `bne.w $5d60` at $5d34 leaves `addi.w #$16,d5` at $5d24 on the
 *     followed record's x as the last writer, and X is its CARRY.
 * Both are DATA DEPENDENT, so the site threads this rather than asserting a constant — which is
 * what makes slot 23 the fourth threaded site rather than a sixth assumed one. */
static unsigned overlap_mask_exit_extend(const uint8_t *image) {
    uint32_t followed = followed_actor_record(image);
    int16_t sprite = field_w(image, followed, WB_ACTOR_SPRITE);

    if (sprite == (int16_t)WB_FOLLOWED_SPRITE_POINT_LO
        || sprite == (int16_t)WB_FOLLOWED_SPRITE_POINT_HI)
        return (uint16_t)field_w(image, followed, WB_ACTOR_Y) < WB_ACTOR_POINT_UP;
    return ((uint32_t)(uint16_t)field_w(image, followed, WB_ACTOR_X)
            + WB_ACTOR_POINT_RIGHT) > 0xffffu;
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
/* THE TWO STRUCK ARMS ARE TWO ENUMERATORS, not one plus a flag, because in the original they are
 * two ENTRY POINTS: at $3cb8 the overlap-point branch falls through `bsr $67c2` into the join the
 * shot arm at $3c9e jumps straight to, and $3ec0/$3ea6 are the same shape. SIX handlers read the
 * difference — 18, 19 and (batch 37) 20, 21, 25 and 27 face the followed record on the point arm
 * and not on the shot's — and the rest name both enumerators on one arm. That is deliberate:
 * `-Wswitch` then makes the next handler's author DECIDE, where an out-parameter defaulted to
 * "no" would let a `bsr $67c2` on the point arm be missed in silence. */
typedef enum {
    MONSTER_UNTOUCHED,
    MONSTER_TOUCHED_FOLLOWED,   /* bit 1, the two footprints: the monster DEALS damage */
    MONSTER_STRUCK,             /* $23b6's verdict: something the player threw landed */
    MONSTER_STRUCK_BY_POINT     /* bit 2 of $5c6e's mask: the player's own reach point */
} MonsterContact;

static MonsterContact monster_contact(uint8_t *image, uint32_t actor) {
    uint32_t overlap;

    if (actor_hit_by_player_shot(image, actor) != WB_ACTOR_NOT_HIT)
        return MONSTER_STRUCK;

    overlap = actor_followed_overlap_mask(image, actor);
    if (overlap & (1u << WB_ACTOR_OVERLAP_BODY_BIT))
        return MONSTER_TOUCHED_FOLLOWED;
    if (overlap & (1u << WB_ACTOR_OVERLAP_POINT_BIT))
        return MONSTER_STRUCK_BY_POINT;
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

/* ...and the ten sites that COMMIT IT IMMEDIATELY: `move.b d0,18(a0)` follows the `andi.b` and the
 * `bne` below reads the register. What the wrap MEANS is still the caller's — a recovery, a defeat,
 * or a phase change — so only the store is shared. Three older bodies (slots 5, 6 and 47) spell the
 * same pair inline and are left alone: converting them is a change to verified code this batch has
 * no reason to touch, so "calls this helper" is not yet the whole census of the shape. */
static uint8_t publish_and_store_cursor(uint8_t *image, uint32_t actor, uint32_t frames,
                                        uint8_t mask) {
    uint8_t stepped = advance_frame_cursor(image, actor, frames, mask);

    set_field_b(image, actor, WB_ACTOR_FIELD_18, stepped);
    return stepped;
}

/* `move.b #$2,d7` — a step written into the LOW BYTE ALONE of a register the settle above left
 * something in. FIVE slots spell their LEFT arm this way and their right one `move.w`: slot 3 in
 * its own body, and slots 6, 14, 18 and 25 through `walk_and_toggle` below. So the two arms walk the
 * same number of pixels only while what actor_fall_and_settle left is below $100 — and the settle's
 * EARLY EXIT makes the other case reachable, since a record already MOVING is returned from with
 * the caller's own d7 untouched. test/test_behavior.py drives slot 3 in its own case and 6, 14 and
 * 18 through WALK_ARM_SLOTS. */
static uint32_t step_over_low_byte(uint32_t settle_span, uint8_t step) {
    return (settle_span & ~0xffu) | step;
}

/* `btst #3,8(a0)` picking a probe, `move.b #n,d7` in the LEFT arm against `move.w #n,d7` in the
 * right, then `bsr $2b82` on what the probe left — the walk slots 6, 14, 18 and 25 spell identically.
 * (Slot 3 spells the same instructions but reads the facing again for its frame list BEFORE the
 * toggle can turn the record, so its copy stays in its own body.) */
static void walk_and_toggle(uint8_t *image, uint32_t actor, uint32_t settle_span, uint8_t step) {
    uint32_t ground = 0, outcome;

    if (faces_left(image, actor))
        outcome = actor_step_left_against_map(image, actor,
                                              step_over_low_byte(settle_span, step), &ground);
    else
        outcome = actor_step_right_against_map(image, actor, step, &ground);
    actor_toggle_side_flag(image, actor, outcome, ground);
}

/* $2cd0 and $3d48 — how slots 6 and 18 both come out of a charge: the flag byte each saved before
 * launching is put back, the latch cleared, the countdown reloaded and the record turned round.
 * Slot 6 ($2cd0) has three entrances — the followed record out of reach, the allocation failing,
 * and the spawn falling through — and slot 18 ($3d48) one.
 *
 * THE TWO SPELL THE FOUR WRITES IN DIFFERENT ORDERS, and the C can only have one:
 *   $2cd0  move.b 29(a0),8(a0) / clr.b 31(a0)      / move.b #n,30(a0) / bchg #3,8(a0)
 *   $3d48  move.b 29(a0),8(a0) / bchg #3,8(a0)     / move.b #n,30(a0) / clr.b 31(a0)
 * The restore is FIRST in both — which is the one ordering that matters, since the `bchg` reads the
 * byte it left — and 30 and 31 are disjoint from 8 and from each other, so the frame's write set is
 * the same either way and no differential can separate them. Recorded because a later reader
 * checking this helper against $3d48 would otherwise find an order it does not have.
 *
 * The reload is a parameter for NAMING and not for value: WB_ACTOR_TYPE06_RELOAD and
 * WB_ACTOR_TYPE18_TURN_FRAMES are both $46 today, so each site naming its own is what will survive
 * one of them being re-read. */
static void restore_flags_and_turn(uint8_t *image, uint32_t actor, uint8_t reload) {
    set_field_b(image, actor, WB_ACTOR_FLAGS, field_b(image, actor, WB_ACTOR_FIELD_29));
    set_field_b(image, actor, WB_ACTOR_FIELD_31, 0);
    set_field_b(image, actor, WB_ACTOR_FIELD_30, reload);
    flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
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
    case MONSTER_STRUCK_BY_POINT:
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
    case MONSTER_STRUCK_BY_POINT:
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
/* $285e — the hover, and SLOT 23 RUNS THESE VERY INSTRUCTIONS: its own copy at $4740 reads the same
 * WB_ACTOR_TYPE04_HOVER through the SHORT absolute encoding, and one of its live-arm paths reaches
 * $2840 above by `bra.w` and falls into this. So the table has TWO operand sites in the image, not
 * the one its plate used to claim. */
static void hover_step(uint8_t *image, uint32_t actor) {
    uint8_t cursor = field_b(image, actor, WB_ACTOR_FIELD_30);
    int16_t delta = (int16_t)bus_read_word(image, addr_add(WB_ACTOR_TYPE04_HOVER, cursor));

    set_field_w(image, actor, WB_ACTOR_Y,
                (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_Y) + (uint16_t)delta));
    set_field_b(image, actor, WB_ACTOR_FIELD_30,
                step_cursor(cursor, WB_ACTOR_TYPE04_HOVER_MASK));
}

/* $2880 and $4760 — the death arm slots 4 and 23 share, transcribed once. No settle at all: a dead
 * hoverer neither falls nor lands, it recoils `step` pixels AWAY unless the mark is already up, and
 * its wrap is the `bclr #0 / bclr #3 / bne` spelling that CLEARS the defeated bit and skips the
 * cursor store on the frame it transfers. */
static void hover_death_frame(uint8_t *image, uint32_t actor, uint32_t dead_left,
                              uint32_t dead_right, uint32_t step) {
    uint32_t frames;
    uint8_t stepped;
    int defeated = flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT);

    if (faces_left(image, actor)) {
        if (!defeated)
            step_right(image, actor, step);
        frames = dead_right;
    } else {
        if (!defeated)
            step_left(image, actor, step);
        frames = dead_left;
    }

    stepped = advance_frame_cursor(image, actor, frames, WB_ACTOR_ANIM32_MASK);
    if (stepped == 0) {
        flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
        if (monster_defeat_if_marked(image, actor))
            return;
    }
    set_field_b(image, actor, WB_ACTOR_FIELD_18, stepped);
}

/* $27da..$287e and $46bc..$475e — the LIVE arm the same two share: close on the followed record
 * while it is within WB_ACTOR_CHASE_REACH, animate, and hover whatever happened. */
static void hover_chase_frame(uint8_t *image, uint32_t actor, uint32_t fly_left,
                              uint32_t fly_right, uint32_t step) {
    actor_set_side_flag(image, actor);
    if ((int16_t)actor_followed_x_within(image, actor, WB_ACTOR_CHASE_REACH) >= 0) {
        uint32_t followed = followed_actor_record(image);
        int left = faces_left(image, actor);

        /* Level with the followed record it stops stepping but keeps animating — `cmp.w (a1),d0 /
         * beq` skips only the two probe calls. */
        if (field_w(image, actor, WB_ACTOR_X) != field_w(image, followed, WB_ACTOR_X)) {
            if (left)
                step_left(image, actor, step);
            else
                step_right(image, actor, step);
        }

        /* `move.l #$0,d0` where every other cursor here is a `moveq`: six bytes for the same zero,
         * the deliberate-waste class ../names.txt records at $7366. */
        set_field_b(image, actor, WB_ACTOR_FIELD_18,
                    advance_frame_cursor(image, actor, left ? fly_left : fly_right,
                                         WB_ACTOR_ANIM32_MASK));
    }
    hover_step(image, actor);
}

uint32_t actor_behavior_type04(uint8_t *image, uint32_t actor) {
    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        hover_death_frame(image, actor, WB_ACTOR_TYPE04_DEAD_LEFT, WB_ACTOR_TYPE04_DEAD_RIGHT,
                          WB_ACTOR_TYPE04_DEAD_STEP);
        return WB_ACTOR_DISPATCH_RAN;
    }

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
    case MONSTER_STRUCK_BY_POINT:
        monster_enter_hit_animation(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    hover_chase_frame(image, actor, WB_ACTOR_TYPE04_FLY_LEFT, WB_ACTOR_TYPE04_FLY_RIGHT,
                      WB_ACTOR_TYPE04_FLY_STEP);
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
    case MONSTER_STRUCK_BY_POINT:
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

/* $2ce6 — the walk both the reload arm and the throw arm end in. */
static void type06_walk_step(uint8_t *image, uint32_t actor, uint32_t settle_span) {
    walk_and_toggle(image, actor, settle_span, WB_ACTOR_TYPE06_WALK_STEP);

    /* The facing is read AGAIN here, after actor_toggle_side_flag may have turned the record — so
     * unlike slot 3 the frame list can be this frame's turn rather than last frame's. */
    publish_and_store_cursor(image, actor,
                             faces_left(image, actor) ? WB_ACTOR_TYPE06_WALK_LEFT
                                                      : WB_ACTOR_TYPE06_WALK_RIGHT,
                             WB_ACTOR_ANIM32_MASK);
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
    case MONSTER_STRUCK_BY_POINT:
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
            restore_flags_and_turn(image, actor, WB_ACTOR_TYPE06_RELOAD);
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
    restore_flags_and_turn(image, actor, WB_ACTOR_TYPE06_RELOAD);
    type06_walk_step(image, actor, settle_span);
    return WB_ACTOR_DISPATCH_RAN;
}


/* `subq.b #n,d16(a0)` over a countdown byte, and the byte it left. The `bne`/`beq` above every site
 * reads the SUBTRACTION's own flags, so the answer really is the stored byte and no site re-reads
 * the field. Slot 44 is the one caller that spends a field other than WB_ACTOR_FIELD_30, and the
 * only one whose step is not 1. */
static uint8_t tick_countdown(uint8_t *image, uint32_t actor, uint32_t offset, uint8_t step) {
    uint8_t timer = (uint8_t)(field_b(image, actor, offset) - step);

    set_field_b(image, actor, offset, timer);
    return timer;
}

/* ...and the spelling slots 45, 46, 48, 49 and 50 share. */
static uint8_t tick_countdown30(uint8_t *image, uint32_t actor) {
    return tick_countdown(image, actor, WB_ACTOR_FIELD_30, 1);
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


/* THE CONTACT PAIR SEVEN SLOTS SPELL, written in `spawn_animation_took_the_frame`'s shape: it
 * answers whether the frame is over. There is no `actor_hit_by_player_shot` in front of it here, so
 * this is NOT `monster_contact` above — these slots read only the overlap mask, and its bit 2 not at
 * all.
 *
 * `latches_countdown` is the ONE instruction the seven do not all have: slots 51, 52, 53, 40 and 43
 * end the body arm `st 30(a0)` and slots 44 and 45 do not. It is a parameter rather than two bodies
 * because everything above it — the inline damage word, the mode bit and the call — is the same six
 * instructions at all seven sites. */
#define CONTACT_LATCHES_COUNTDOWN 1
#define CONTACT_NO_LATCH          0

static int switched_contact_took_the_frame(uint8_t *image, uint32_t actor, int latches_countdown) {
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
        if (latches_countdown)
            set_field_b(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_ST_BYTE);
        return 1;
    }
    return 0;
}

/* $5ab2's own arm, $561e and $57a0 — the fall slots 51, 40 and 43 share once their mode bit is up:
 * settle, ascend, and give the slot back the frame the record is supported again. The free marker
 * goes over the x word the settle may have moved this same frame. */
static void fall_until_supported_then_free(uint8_t *image, uint32_t actor) {
    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    actor_hop_ascend_step(image, actor);
    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT))
        return;
    set_field_w(image, actor, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
    flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
}

/* --- slot 51 ($5ab2): the charger that dies on landing -------------------------------------------
 *
 * Bit 0 of WB_ACTOR_FLAGS2 is a one-way switch here, not a death animation: while it is clear the
 * record walks and tests; every arm that raises it hands the record to the fall above, which frees
 * the slot the moment the record is supported again.
 */
uint32_t actor_behavior_type51(uint8_t *image, uint32_t actor) {
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        fall_until_supported_then_free(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }

    if (switched_contact_took_the_frame(image, actor, CONTACT_LATCHES_COUNTDOWN))
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

    if (switched_contact_took_the_frame(image, actor, CONTACT_LATCHES_COUNTDOWN))
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
 * reader is the `tst.w` at $454c, which batch 37 read — it is slot 22's veto on its own minion
 * spawn, so a live type-53 record stops that handler seeding.
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

    if (switched_contact_took_the_frame(image, actor, CONTACT_LATCHES_COUNTDOWN))
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
    case MONSTER_STRUCK_BY_POINT:
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

/* $517e..$51ab, AND $544c..$5471: the payout's own five calls, which TWO addresses spell.
 * `actor_behavior_type38_pickup`'s gold arm is these instructions with a different amount above
 * them and a `bra.w` into `actor_defeat_and_score` where this one has an `rts` — so `award` is the
 * parameter and the two callers differ in nothing else.
 *
 * The award is a WORD and every consumer reads a different width of it: `bcd_add_random_1_to_4` and
 * the digits take the low BYTE, `bcd_add_counter_bd6e` stages the whole WORD, and the score's
 * addend is a constant longword that has nothing to do with the amount at all. */
static void pay_gold_award(uint8_t *image, uint32_t award) {
    unsigned draw_carry;

    /* THE CHAIN, $5184 -> $5188 (and $544c -> $5450): the draw's `abcd d1,d0` is the instruction
     * before the `bsr`, so its carry is the counter's entry X. */
    award = bcd_add_random_1_to_4(image, award, &draw_carry);
    bcd_add_counter_bd6e(image, award, draw_carry);
    text_write_gold_digits_a2ac(image, award);
    /* ...and NOT a chain at $5196 (or $545e): the digits above are the last thing to write X, and on
     * both of their exits that is `addi.b #$30` on a nibble masked to $0..$f, which cannot carry out
     * of $30..$3f. The counter's own carry-out is dead here — $b562's `rts` is followed by the `bsr`
     * to those digits, not by the score add. */
    bcd_add_score_bd70(image, WB_ACTOR_COLLECT_SCORE, WB_BCD_ENTRY_EXTEND_CLEAR);

    /* The id-and-lifetime pair, inline for src/actor.c's stated reason rather than shared: making
     * it one symbol across three modules would export a function to save one `wr16`, and the three
     * sites do not agree anyway — src/scene.c posts a lifetime of zero on its speech arm and
     * `type61_post_message` above CLEARS only the high byte of this word. */
    image[WB_TEXT_REQUEST] = WB_TEXT_MESSAGE_GOLD_GET;
    wr16(image + WB_TEXT_LIFETIME_REQUEST, WB_TEXT_LIFETIME_DEFAULT);
}

/* $517a — the payout, entered from slots 31 and 32. Its own four bytes are the two instructions
 * that fetch the amount out of the SCENE DESCRIPTOR; everything below them is shared. */
void hud_award_gold_from_descriptor(uint8_t *image) {
    uint32_t descriptor = be32(image + WB_RECORD_PTR_10424);

    pay_gold_award(image, bus_read_word(image, addr_add(descriptor, WB_SCENE_GOLD_AWARD)));
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

/* $4e98's `tst.w d0` — the step test that reads the WORD. THREE dispatch rows spell it over TWO
 * call sites: slot 28 in its own body, and slots 20 and 27 through the one shared `hopper_frame`
 * below. (Batch 33 called it the tier's only one; batch 37 read the two hoppers.)
 *
 * Every other step test is `tst.b d0` (`step_was_blocked` above), and the difference is not
 * cosmetic: the
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


/* --- slots 32..37 ($5046..$5407): what CLOSES the $4e38..$5407 band ------------------------------
 *
 * Two more collectables and then four routines that are not collectables at all. Slot 32 is slot
 * 31's payout with a HOP MACHINE in front of it; slot 33 pays the panel's own clock instead of any
 * counter. Slot 34 is the SHOP's item cursor — a record whose WB_ACTOR_X is a menu selection the
 * joystick moves. Slots 35, 36 and 37 are the actors `player_pending_event_gate` ($b1a) spawns and
 * then waits on: each raises one of the two flags inside WB_STAGE_RESET_BLOCK that gate tests, and
 * that is the whole of what they are for.
 */

/* $5116, $511c and $5128 — slot 32's ending, and the two clears sit BETWEEN the `bclr` and the free
 * marker exactly as slot 30's cursor clear does, which is why `collectable_free_slot` is spelt out
 * here rather than called. It does NOT clear WB_ACTOR_TYPE32_CURSOR, where slot 30's ending clears
 * its own — so the next type-32 record picks the animation up where this one left it.
 *
 * THE SECOND CLEAR IS DEAD. `clr.w $515c.l` writes BOTH latch bytes and the `clr.b $515d.l` after
 * it writes the second one again with the same zero — the deliberate dead-instruction class
 * ../names.txt records at $7366 and $245e. It is reproduced because it is what the bytes do, and no
 * case can hold it: the oracle's write ledger is address-keyed, so one zero and two are the same
 * ledger (../STATUS.md's not-pinned list). */
static void type32_free_slot(uint8_t *image, uint32_t actor) {
    flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT);
    wr16(image + WB_ACTOR_TYPE32_WALKING, 0);
    image[WB_ACTOR_TYPE32_HOPS_SPENT] = 0;
    set_field_w(image, actor, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
}

/* $504c — WHEN THE CONTACT TEST RUNS AT ALL. `tst.b $515c.l / bne` jumps STRAIGHT to it, so once
 * the record has landed once it is collectable on every frame; only a record that has never landed
 * and is mid-hop skips the test, which is slot 28's and slot 31's gate with the latch in front. */
static int type32_contact_is_tested(const uint8_t *image, uint32_t actor) {
    return image[WB_ACTOR_TYPE32_WALKING] != 0
           || !flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT);
}

/* $5078 — the hop machine. It runs only on the frames the record is SUPPORTED, so one hop is one
 * WB_ACTOR_FIELD_10, and the byte it counts down is ALSO the speed the next hop launches at: the
 * hops therefore get shorter and the last one is skipped, because the frame the count reaches zero
 * raises WB_ACTOR_TYPE32_HOPS_SPENT and launches nothing.
 *
 * WB_ACTOR_TYPE32_WALKING IS RAISED FIRST, above the countdown and both of its arms, so the walk
 * and the contact test open on the record's very first landing whether or not it hops again. */
static void type32_relaunch_on_landing(uint8_t *image, uint32_t actor) {
    uint8_t hops_left;

    if (image[WB_ACTOR_TYPE32_HOPS_SPENT] != 0)
        return;
    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT))
        return;

    image[WB_ACTOR_TYPE32_WALKING] = WB_ACTOR_TYPE32_LATCH_SET;

    /* `subq.b #1,10(a0) / bne` — one read-modify-write whose branch reads the ALU's flags. */
    hops_left = (uint8_t)(field_b(image, actor, WB_ACTOR_FIELD_10) - 1);
    set_field_b(image, actor, WB_ACTOR_FIELD_10, hops_left);
    if (hops_left == 0) {
        image[WB_ACTOR_TYPE32_HOPS_SPENT] = WB_ACTOR_TYPE32_LATCH_SET;
        return;
    }

    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT);
    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_LAUNCHED_BIT);
    flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
    /* `move.b 10(a0),d0 / move.b d0,11(a0)` RE-READS the byte the `subq.b` above stored rather than
     * reusing the value it computed. No case can separate the two, and the reason is NOT that the
     * SUPPORTED gate above blocks it — a record at $ffff7 puts WB_ACTOR_FLAGS on $fffff, the last
     * byte os_in_image admits, so the gate can be satisfied with the counter and the speed both
     * outside. The reason is that the STORE THAT CONSUMES THE RE-READ IS DROPPED WHENEVER ITS
     * SOURCE IS: WB_ACTOR_SPEED is the byte after WB_ACTOR_FIELD_10, so an address that puts the
     * counter outside the image puts the speed outside too, and the differing value lands nowhere.
     * The one address where they part is the 24-bit fold at $fffff5 (counter $ffffff, speed wrapped
     * to 0) — and there WB_ACTOR_FLAGS is $fffffd, outside, so that record cannot pass the gate.
     * ../STATUS.md carries it; `reread/type32-speed-from-the-computed-local` is the mutant. */
    set_field_b(image, actor, WB_ACTOR_SPEED, field_b(image, actor, WB_ACTOR_FIELD_10));
}

/* $5130 — THE SECOND OF THREE READERS OF WB_ACTOR_ANIM_5160_FRAMES (the third, `$58f8` inside the
 * unported actor_behavior_type46, is $6872's shape again), and it differs from $6872 in three ways
 * that all come off the cursor rather than off the table. `actor_relaunch_and_anim_5160` reads a zero-extended
 * record BYTE and commits `addq.b #2` to memory BEFORE it reads the terminator, so the wrapping
 * frame writes that field TWICE; this reads a GLOBAL WORD, indexes it SIGN-EXTENDED and stores the
 * stepped cursor ONCE, after the test. What they agree on is the LOOK-AHEAD: both read the word one
 * past the frame they just published, so the $ffff terminator is never itself drawn. (An earlier
 * ../names.txt plate said this one zeroed the cursor "one word EARLY"; the bytes say otherwise —
 * $6872's `move.w (a1)+,6(a0)` is a POST-INCREMENT, so its `cmpi.w #$ffff,(a1)` and this one's
 * `cmpi.w #$ffff,2(a1)` read the same word.) */
static void type32_publish_frame(uint8_t *image, uint32_t actor) {
    uint16_t cursor = be16(image + WB_ACTOR_TYPE32_CURSOR);
    uint32_t frame = addr_add(WB_ACTOR_ANIM_5160_FRAMES, sign_ext16(cursor));
    uint16_t stepped = (uint16_t)(cursor + WB_ACTOR_ANIM_FRAME_BYTES);

    set_field_w(image, actor, WB_ACTOR_SPRITE, bus_read_word(image, frame));
    if (bus_read_word(image, addr_add(frame, WB_ACTOR_ANIM_FRAME_BYTES)) == WB_ACTOR_ANIM_5160_END)
        stepped = 0;
    wr16(image + WB_ACTOR_TYPE32_CURSOR, stepped);
}

/* $5046 — 278 bytes. A HOPPING GOLD COLLECTABLE: it pays `hud_award_gold_from_descriptor` exactly
 * as slot 31 does, but between spawning and being taken it hops WB_ACTOR_FIELD_10 times and then
 * walks one pixel a frame, turning round on a blocked probe.
 *
 * ALL THREE OF ITS STATE BYTES ARE GLOBALS, which is what makes it the tier's second
 * WB_ACTOR_TYPE30_CURSOR: two live type-32 records share one hop machine, one walk gate and one
 * animation phase, and a record spawned while another is walking is walking from its first frame. */
uint32_t actor_behavior_type32(uint8_t *image, uint32_t actor) {
    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    actor_hop_ascend_step(image, actor);

    if (type32_contact_is_tested(image, actor) && followed_stood_on_it(image, actor)) {
        sound_request_9(image);
        hud_award_gold_from_descriptor(image);
        type32_free_slot(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }

    type32_relaunch_on_landing(image, actor);
    /* $50c8 — actor_step_facing's own thirty-six bytes, spelt inline here with the two probe arms
     * the other way round. Slots 48 and 49 have the same inline spelling and CALL that routine
     * (`settle_hop_and_step_facing`), so this does too: the C is identical either way and the
     * original's own bytes are pinned by `_type32_pieces`. The step is written by a `move.w` into
     * d7's LOW WORD, and the probes read that word alone (map.h), so what the settle left in the
     * register's high half cannot reach them and the step really is the one it looks like. */
    if (image[WB_ACTOR_TYPE32_WALKING] != 0)
        actor_step_facing(image, actor, WB_ACTOR_TYPE32_WALK_STEP);

    flicker_when_field_12_reaches_the_mark(image, actor);
    if (field_12_word_ran_out(image, actor)) {
        type32_free_slot(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }
    type32_publish_frame(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}

/* $5208 — 82 bytes, and the only collectable in the band that pays neither gold nor the meter: it
 * raises WB_PANEL_FRAME_REWIND and WB_PANEL_FRAME_HOLD together, one instruction apart, which winds
 * WB_PANEL_FRAME_DELAY back up to WB_PANEL_FRAME_DELAY_INIT in WB_PANEL_FRAME_REWIND_STEP a frame
 * and freezes the countdown while it climbs. So this is the game's CLOCK pickup. It also has no
 * `btst #0,8(a0)` gate at all — a record mid-hop is collectable here where slots 28, 31 and 32
 * refuse.
 *
 * THE SCORE'S ENTRY X is the sound trigger's, which is not readable off these bytes. The
 * differential PINS it over the paths the cases drive ($20 added to any seeded score differs in its
 * lowest digit between a folded-in 0 and a folded-in 1) — but `snd_trigger_effect` has three exits
 * whose last X-writer is data dependent, so that is a pin and not a proof; hud.h's audit block and
 * ../STATUS.md carry the distinction and the work it needs. Slot 28's $4e5a is the same claim. */
uint32_t actor_behavior_type33(uint8_t *image, uint32_t actor) {
    if (followed_stood_on_it(image, actor)) {
        sound_request_9(image);
        wr16(image + WB_PANEL_FRAME_REWIND, WB_PANEL_FRAME_REWIND_SET);
        wr16(image + WB_PANEL_FRAME_HOLD, WB_PANEL_FRAME_HOLD_SET);
        bcd_add_score_bd70(image, WB_ACTOR_COLLECT_SCORE, WB_BCD_ENTRY_EXTEND_CLEAR);
        collectable_free_slot(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }

    flicker_when_field_12_reaches_the_mark(image, actor);
    if (!field_12_word_ran_out(image, actor))
        return WB_ACTOR_DISPATCH_RAN;

    collectable_free_slot(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}

/* $52b0, $52c0 and $52e0 — one position planted as ONE `move.l #imm,(a0)` over WB_ACTOR_X and
 * WB_ACTOR_Y together. The longword is composed from the same two constants the `cmpi.w`s above
 * read, so the menu's geometry has one definition rather than a literal per arm. */
static void type34_park_cursor(uint8_t *image, uint32_t actor, uint16_t x, uint16_t y) {
    bus_write_long(image, actor, ((uint32_t)x << 16) | y);
}

/* ...and the two ends also POST the item's own message, where the middle only dismisses the box:
 * `move.b #$ff,$c030.l` with no lifetime beside it, so nothing re-arms WB_TEXT_LIFETIME_REQUEST. */
static void type34_park_on_item(uint8_t *image, uint32_t actor, uint16_t x, uint32_t message_field) {
    uint32_t shop = be32(image + WB_SHOP_RECORD_PTR);

    /* `move.w 66(a1),d0 / move.b d0,$c030.l` — a WORD read and a BYTE store, so an id above 255
     * posts its low half. */
    image[WB_TEXT_REQUEST] = (uint8_t)bus_read_word(image, addr_add(shop, message_field));
    wr16(image + WB_TEXT_LIFETIME_REQUEST, WB_TEXT_LIFETIME_DEFAULT);
    type34_park_cursor(image, actor, x, WB_ACTOR_TYPE34_ITEM_Y);
}

static void type34_park_on_middle(uint8_t *image, uint32_t actor) {
    image[WB_TEXT_REQUEST] = WB_TEXT_REQUEST_DISMISS;
    type34_park_cursor(image, actor, WB_ACTOR_TYPE34_MIDDLE_X, WB_ACTOR_TYPE34_MIDDLE_Y);
}

/* $525a — 220 bytes, and NOT a creature: this record is the shop's CURSOR. Its own WB_ACTOR_X is
 * the selection — WB_ACTOR_TYPE34_ITEM1_X, _MIDDLE_X or _ITEM2_X — the joystick's left and right
 * edges walk it along the three, and fire posts the WB_SHOP_REQUEST `scene_run_frame` serves.
 *
 * THE FIRE MAPPING IS NOT THE POSITIONAL ORDER. Left buys item 1 and right buys item 2, but the
 * MIDDLE is WB_SHOP_REQUEST_FAREWELL — so the request word runs 1, 3, 2 across the screen.
 *
 * IT IS DEAF WHILE THE DRIVER IS TALKING. WB_SCENE_MESSAGE_PENDING or WB_SCENE_ACK_WAIT being
 * nonzero ends the frame before the joystick is even read, which is what stops a held direction
 * walking the cursor under an open box. */
uint32_t actor_behavior_type34(uint8_t *image, uint32_t actor) {
    uint8_t edges;
    uint16_t x;

    if (be16(image + WB_SCENE_MESSAGE_PENDING) != 0)
        return WB_ACTOR_DISPATCH_RAN;
    if (be16(image + WB_SCENE_ACK_WAIT) != 0)
        return WB_ACTOR_DISPATCH_RAN;

    edges = joy1_newly_pressed(image);
    /* Every arm below re-reads (a0) with its own `cmpi.w`, and one read stands in for all of them:
     * nothing between them writes the record, and a bus read is answered the same way twice. The
     * hoist also reads the word on the no-edge frame, where the original reaches its `rts` at $528a
     * having never touched (a0) — unobservable, because a read is not in the write ledger and
     * bus.h answers an address outside the image with zero and no side effect. */
    x = (uint16_t)field_w(image, actor, WB_ACTOR_X);

    if (edges & (1u << WB_JOY1_LEFT_BIT)) {
        if (x == WB_ACTOR_TYPE34_ITEM2_X)
            type34_park_on_middle(image, actor);
        else if (x == WB_ACTOR_TYPE34_MIDDLE_X)
            type34_park_on_item(image, actor, WB_ACTOR_TYPE34_ITEM1_X, WB_SHOP_ITEM1_CURSOR_MSG);
        return WB_ACTOR_DISPATCH_RAN;
    }

    if (edges & (1u << WB_JOY1_RIGHT_BIT)) {
        if (x == WB_ACTOR_TYPE34_ITEM1_X)
            type34_park_on_middle(image, actor);
        else if (x == WB_ACTOR_TYPE34_MIDDLE_X)
            type34_park_on_item(image, actor, WB_ACTOR_TYPE34_ITEM2_X, WB_SHOP_ITEM2_CURSOR_MSG);
        return WB_ACTOR_DISPATCH_RAN;
    }

    if (edges & (1u << WB_JOY1_FIRE_BIT)) {
        if (x == WB_ACTOR_TYPE34_ITEM1_X)
            wr16(image + WB_SHOP_REQUEST, WB_SHOP_REQUEST_ITEM1);
        else if (x == WB_ACTOR_TYPE34_ITEM2_X)
            wr16(image + WB_SHOP_REQUEST, WB_SHOP_REQUEST_ITEM2);
        else if (x == WB_ACTOR_TYPE34_MIDDLE_X)
            wr16(image + WB_SHOP_REQUEST, WB_SHOP_REQUEST_FAREWELL);
    }
    return WB_ACTOR_DISPATCH_RAN;
}

/* $533c and $53c0 — the SAME six instructions in two table rows, and the same GLOBAL cursor: one
 * word of WB_ACTOR_EVENT_ANIM_FRAMES published, then the cursor stepped and masked to the table's
 * 32 bytes. Answers whether the cursor came back to ZERO, which is what each row's own tail acts
 * on.
 *
 * THE FETCH IS NOT BOUNDED AND THE STORE IS: the mask is applied AFTER the read, so a cursor poked
 * outside the table indexes WB_ACTOR_EVENT_ANIM_FRAMES plus a SIGN-EXTENDED word and only the value
 * that lands back in memory is inside it — WB_ACTOR_TYPE30_DRIFT's shape exactly. */
static int event_anim_step(uint8_t *image, uint32_t actor) {
    uint16_t cursor = be16(image + WB_ACTOR_EVENT_ANIM_CURSOR);
    uint16_t stepped = (uint16_t)((cursor + WB_ACTOR_ANIM_FRAME_BYTES)
                                  & WB_ACTOR_EVENT_ANIM_MASK);

    set_field_w(image, actor, WB_ACTOR_SPRITE,
                bus_read_word(image, addr_add(WB_ACTOR_EVENT_ANIM_FRAMES, sign_ext16(cursor))));
    wr16(image + WB_ACTOR_EVENT_ANIM_CURSOR, stepped);
    return stepped == 0;
}

/* $5336 — 38 bytes, then its cursor and its sixteen frame words. It plays the animation and, on the
 * frame the cursor wraps, raises WB_EVENT_ANIM_DONE_B12 — which is the only thing this handler is
 * for: `player_pending_event_gate` spawns a type-35 record from the template at $537e and waits for
 * exactly this word before it runs the scene's script. The record keeps its slot for ever. */
uint32_t actor_behavior_type35(uint8_t *image, uint32_t actor) {
    if (event_anim_step(image, actor))
        wr16(image + WB_EVENT_ANIM_DONE_B12, WB_EVENT_DONE_SET);
    return WB_ACTOR_DISPATCH_RAN;
}

/* $53bc — 38 bytes, and slot 35 with two differences: the flag is WB_EVENT_ANIM_DONE_B16, and the
 * wrap also `clr.w`s the record's own WB_ACTOR_TYPE. So this row RETYPES ITSELF to slot 0 — the
 * bare `rts` — which is how it stops without giving its slot back and leaves the sprite it drew
 * standing. (Slot 60 is the tier's other self-retyper, and it moves the other way.) */
uint32_t actor_behavior_type36(uint8_t *image, uint32_t actor) {
    if (event_anim_step(image, actor)) {
        wr16(image + WB_EVENT_ANIM_DONE_B16, WB_EVENT_DONE_SET);
        set_field_w(image, actor, WB_ACTOR_TYPE, 0);
    }
    return WB_ACTOR_DISPATCH_RAN;
}

/* $53e2 — 38 bytes, slot 36's ALTERNATIVE: $cd8 picks between the two on one word of the scene
 * descriptor, and they raise the same flag. This one has no animation and no table — it lifts one
 * pixel a frame until its y is exactly WB_ACTOR_TYPE37_RISE above the descriptor's own
 * WB_SCENE_VARIANT word, which is the y it was spawned at.
 *
 * THE ARRIVAL TEST IS AN EQUALITY and the last instruction of the band is the `rts` BOTH arms
 * reach — the risen frame by falling through the flag write and every other frame by a `bra.w` over
 * it. Nothing else in the image branches to $5406. */
uint32_t actor_behavior_type37(uint8_t *image, uint32_t actor) {
    uint32_t descriptor = be32(image + WB_RECORD_PTR_10420);
    int16_t target = (int16_t)(bus_read_word(image, addr_add(descriptor, WB_SCENE_VARIANT))
                               - WB_ACTOR_TYPE37_RISE);

    if (target != field_w(image, actor, WB_ACTOR_Y)) {
        set_field_w(image, actor, WB_ACTOR_Y,
                    (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_Y) - 1));
        return WB_ACTOR_DISPATCH_RAN;
    }
    wr16(image + WB_EVENT_ANIM_DONE_B16, WB_EVENT_DONE_SET);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- batch 35: the MONSTER-PROLOGUE family, dispatch rows 9..13 ----------------------------------
 *
 * Five more bodies inside the $2462 band's grammar. What they add to it is three shapes the five
 * handlers below share and slots 2..6 do not, so each is a helper here rather than five copies.
 */

/* `addq.b #2,d16(a0)` then `andi.b #mask,d16(a0)` — a cursor stepped and masked as TWO
 * read-modify-writes on memory, where every other cursor in the tier is computed in a register and
 * stored once. Three sites spell it (slot 10's hover cursor and its walk cursor, slot 13's).
 *
 * THE MASK MUST RE-READ what the step wrote: on a record bus.h refuses, the step lands nowhere and
 * the mask reads back zero, which is batch 31's `type61-cursor-reread` one field over. What comes
 * BACK is the computed value rather than a third read — the `andi.b` sets the condition codes from
 * its own result, and slot 10 branches on them. */
static uint8_t step_cursor_in_memory(uint8_t *image, uint32_t actor, uint32_t offset, uint8_t mask) {
    uint8_t masked;

    set_field_b(image, actor, offset,
                (uint8_t)(field_b(image, actor, offset) + WB_ACTOR_ANIM_FRAME_BYTES));
    masked = (uint8_t)(field_b(image, actor, offset) & mask);
    set_field_b(image, actor, offset, masked);
    return masked;
}

/* `bclr #0,9(a0) / btst #3,9(a0) / bne.w $6bb8` — FOURTEEN slots end their hurt animation this way
 * (9, 10, 11 and 12 from batch 35; 14, 17 and 18 from batch 36; 20..22 and 24..27 from batch 37),
 * over NINE call sites, because four of the nine are shared: `gated_hurt_frame` carries 9, 12, 22
 * and 26, `charger_hurt_frame` 18 and 25, and `hopper_hurt_frame` 20 and 27. The figure is a grep
 * of this file's call sites, not a running tally. The DEFEATED bit is only TESTED, where slots 2, 3
 * and 4 `bclr` it, so a record that runs out of hit points and survives the wrap keeps the mark; and
 * the `btst` RE-READS the byte the `bclr` just wrote rather than reasoning about it, which is what
 * the original does. Slots 15 and 16 read the two marks the other way round —
 * `monster_hurt_wrap_test_then_clear` below. */
static void monster_hurt_wrap_clear_then_test(uint8_t *image, uint32_t actor) {
    flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT))
        actor_defeat_and_score(image, actor);
}

/* $2f46 — 64 bytes, ONE `bsr` caller (slot 9's walk), and NOT the "coin-flip turn" its `# ctx` plate
 * called it: it turns AND launches, and the launch is unconditional once the record is supported.
 * One `rng_next` word does both jobs — bit 2 picks the facing and nothing vetoes the hop.
 *
 * The record must be SUPPORTED or the whole body is skipped, so a monster already in the air is
 * left to finish its arc. */
void actor_random_facing_hop(uint8_t *image, uint32_t actor) {
    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT))
        return;

    /* `btst #2,d0` is a longword test of a register rng_next writes only the low WORD of, and the
     * bit is inside it — actor_tick_timer30's argument for handing in 0 here too. */
    if ((rng_next(image, 0) & (1u << WB_ACTOR_RANDOM_HOP_RNG_BIT)) != 0)
        flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
    else
        flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);

    launch_at_inline_speed(image, actor, WB_ACTOR_RANDOM_HOP_SPEED);
}


/* --- slot 9 ($2e12): the random hopper -----------------------------------------------------------
 *
 * 152 bytes, and the shortest body in the family: every arm is a chain of calls. The live frame
 * falls, ascends, walks WB_ACTOR_TYPE09_WALK_STEP toward the followed record and then asks
 * actor_random_facing_hop for a new direction and a new hop; the hurt frame retreats
 * WB_ACTOR_STEP_AWAY_PIXELS and plays the shorter list pair until it terminates.
 *
 * ITS HURT ARM IS BOUNDED, and the boundary is not this handler's own: `bsr $d78` reaches
 * player_gate_on_1516, which BRANCHES into WB_PLAYER_STEP_BODY while WB_TILE_33_MODE is clear. Slot
 * 53 met the same edge first and slot 12 below meets it again.
 */
/* THE HURT ARM FOUR SLOTS SHARE — 9, 12 and (batch 37) 22 and 26 — instruction for instruction bar
 * the list pair: the settle, the player gate, a four-pixel retreat, one frame, and the wrap. The
 * four bodies really do differ only in the `lea` operand, which is why this is one function, and
 * all four are BOUNDED at WB_PLAYER_STEP_BODY for the same reason. */
static uint32_t gated_hurt_frame(uint8_t *image, uint32_t actor, uint32_t hurt_lists) {
    uint32_t boundary;

    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    boundary = player_gate_on_1516(image);
    if (boundary != WB_ACTOR_DISPATCH_RAN)
        return boundary;

    actor_face_and_step_away4(image, actor);
    actor_anim_step_facing_list(image, actor, hurt_lists);

    /* `tst.b 18(a0)` — the cursor RE-READ out of memory after $3006 stored it, so the wrap is what
     * the list's own terminator produced and not a value this frame kept in a register. */
    if (field_b(image, actor, WB_ACTOR_FIELD_18) == 0)
        monster_hurt_wrap_clear_then_test(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}

uint32_t actor_behavior_type09(uint8_t *image, uint32_t actor) {
    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0))
        return gated_hurt_frame(image, actor, WB_ACTOR_TYPE09_HURT_LISTS);

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
    case MONSTER_STRUCK_BY_POINT:
        monster_enter_hit_animation(image, actor);
        actor_set_side_flag(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    actor_fall_and_settle(image, actor, followed_sprite_left_in_d7(image));
    actor_hop_ascend_step(image, actor);
    /* `move.w #$3,d7` — a WORD write, so what the settle left in d7 cannot reach the step. */
    actor_step_facing(image, actor, WB_ACTOR_TYPE09_WALK_STEP);
    actor_random_facing_hop(image, actor);
    actor_anim_step_facing_list(image, actor, WB_ACTOR_TYPE09_WALK_LISTS);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 10 ($303a): the flier ------------------------------------------------------------------
 *
 * 350 bytes, and the one handler in the family that never touches the collision map while alive.
 * Slot 4's hover table one size down (32 words rather than 64) carries it up and down every frame,
 * it drifts WB_ACTOR_TYPE10_DRIFT_STEP horizontally toward the side flag, and every
 * WB_ACTOR_TYPE10_TURN_FRAMES frames it turns round and takes ONE homing step on both axes.
 *
 * AND THE VERTICAL CLOSE HAPPENS ONCE A HOVER CYCLE, not once a frame: `bne.w` on the masked cursor
 * skips it on the other 31 frames, so the record is pulled WB_ACTOR_TYPE10_CLOSE_STEP pixels toward
 * the followed record's y only when the hover comes back round to its first word.
 */
static void type10_hover_and_close(uint8_t *image, uint32_t actor) {
    uint8_t cursor = field_b(image, actor, WB_ACTOR_FIELD_31);
    int16_t delta = (int16_t)bus_read_word(image, addr_add(WB_ACTOR_TYPE10_HOVER, cursor));
    uint32_t followed;
    uint16_t close;

    set_field_w(image, actor, WB_ACTOR_Y,
                (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_Y) + (uint16_t)delta));
    if (step_cursor_in_memory(image, actor, WB_ACTOR_FIELD_31, WB_ACTOR_TYPE10_HOVER_MASK) != 0)
        return;

    /* `cmp.w 2(a1),d1 / blt` — a SIGNED compare of the two y words, and the y is re-read here
     * rather than carried over the hover step above. */
    followed = followed_actor_record(image);
    close = (field_w(image, actor, WB_ACTOR_Y) < field_w(image, followed, WB_ACTOR_Y))
                ? WB_ACTOR_TYPE10_CLOSE_STEP
                : (uint16_t)-WB_ACTOR_TYPE10_CLOSE_STEP;
    set_field_w(image, actor, WB_ACTOR_Y,
                (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_Y) + close));
}

static uint32_t type10_hurt_frame(uint8_t *image, uint32_t actor) {
    /* The retreat is the only thing the defeated mark suppresses — a marked record still animates,
     * and it is the animation that carries it to actor_defeat_and_score. */
    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT))
        step_away_without_facing(image, actor, WB_ACTOR_TYPE10_HURT_STEP);

    if (publish_and_store_cursor(image, actor,
                                 faces_left(image, actor) ? WB_ACTOR_TYPE10_HURT_LEFT
                                                          : WB_ACTOR_TYPE10_HURT_RIGHT,
                                 WB_ACTOR_ANIM16_MASK) == 0)
        monster_hurt_wrap_clear_then_test(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}

uint32_t actor_behavior_type10(uint8_t *image, uint32_t actor) {
    uint8_t timer;

    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0))
        return type10_hurt_frame(image, actor);

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
    case MONSTER_STRUCK_BY_POINT:
        monster_enter_hit_animation(image, actor);
        actor_set_side_flag(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    type10_hover_and_close(image, actor);

    set_field_w(image, actor, WB_ACTOR_X,
                (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_X)
                           + (faces_left(image, actor) ? (uint16_t)-WB_ACTOR_TYPE10_DRIFT_STEP
                                                       : WB_ACTOR_TYPE10_DRIFT_STEP)));

    timer = field_b(image, actor, WB_ACTOR_FIELD_30);
    if (timer != 0) {
        set_field_b(image, actor, WB_ACTOR_FIELD_30, (uint8_t)(timer - 1));
    } else {
        flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
        set_field_b(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE10_TURN_FRAMES);
        actor_step_toward_followed(image, actor, WB_ACTOR_TYPE10_HOME_STEP);
    }

    /* The facing is re-read AFTER the turn above, so the frame published on a turn frame is already
     * the new side's — where slot 3's walk chooses its list before its own turn. */
    publish_frame(image, actor,
                  faces_left(image, actor) ? WB_ACTOR_TYPE10_WALK_LEFT
                                           : WB_ACTOR_TYPE10_WALK_RIGHT,
                  field_b(image, actor, WB_ACTOR_FIELD_18));
    step_cursor_in_memory(image, actor, WB_ACTOR_FIELD_18, WB_ACTOR_ANIM16_MASK);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 11 ($3218): the decider ----------------------------------------------------------------
 *
 * 324 bytes. It walks WB_ACTOR_TYPE11_WALK_STEP a frame while its countdown runs, and on the frame
 * the countdown reaches zero it stops walking entirely and makes a DECISION out of one `rng_next`
 * word instead: bit 2 picks a new facing and bit 1 decides whether to hop. Both arms then return —
 * the decision frame publishes no animation at all.
 *
 * THE DECISION IS GATED ON BEING SUPPORTED and the RELOAD is not, exactly as actor_tick_timer30
 * orders the same two things: a record caught in the air still gets a fresh WB_ACTOR_TYPE11_RELOAD
 * and simply does nothing with it.
 */
static uint32_t type11_decide(uint8_t *image, uint32_t actor) {
    uint32_t draw;

    set_field_b(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE11_RELOAD);
    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT))
        return WB_ACTOR_DISPATCH_RAN;

    draw = rng_next(image, 0);
    if ((draw & (1u << WB_ACTOR_TYPE11_FACE_RNG_BIT)) != 0)
        flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
    else
        flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);

    if ((draw & (1u << WB_ACTOR_TYPE11_HOP_RNG_BIT)) == 0)
        actor_start_motion_at_speed(image, actor, WB_ACTOR_TYPE11_HOP_SPEED);
    return WB_ACTOR_DISPATCH_RAN;
}

static uint32_t type11_hurt_frame(uint8_t *image, uint32_t actor) {
    /* THE ONE TABLE SELECT IN THE FAMILY THAT IS NOT THE SIDE FLAG: `btst #3,30(a0)` reads bit 3 of
     * the very byte the live arm reloads with WB_ACTOR_TYPE11_RELOAD, so which of the two hurt
     * lists plays depends on how far through its countdown the record was when it was hit. */
    uint32_t frames = flag_is_set(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE11_HURT_BIT)
                          ? WB_ACTOR_TYPE11_HURT_MARKED
                          : WB_ACTOR_TYPE11_HURT_PLAIN;

    if (publish_and_store_cursor(image, actor, frames, WB_ACTOR_ANIM16_MASK) == 0)
        monster_hurt_wrap_clear_then_test(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}

uint32_t actor_behavior_type11(uint8_t *image, uint32_t actor) {
    uint8_t timer, cursor;

    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0))
        return type11_hurt_frame(image, actor);

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
    case MONSTER_STRUCK_BY_POINT:
        /* No actor_set_side_flag between the two writes and the tail jump — slot 11 takes the hit
         * facing wherever it already was, as slot 13 does and slots 9, 10 and 12 do not. */
        monster_enter_hit_animation(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    actor_fall_and_settle(image, actor, followed_sprite_left_in_d7(image));
    actor_hop_ascend_step(image, actor);

    timer = field_b(image, actor, WB_ACTOR_FIELD_30);
    if (timer == 0)
        return type11_decide(image, actor);
    set_field_b(image, actor, WB_ACTOR_FIELD_30, (uint8_t)(timer - 1));

    /* $32b2..$32db is actor_step_facing's body spelt inline, with `move.w #$2,d7` in each arm
     * instead of the caller's register — down to the `tst.b d0` and the `bchg` over it. */
    actor_step_facing(image, actor, WB_ACTOR_TYPE11_WALK_STEP);

    cursor = field_b(image, actor, WB_ACTOR_FIELD_18);
    publish_frame(image, actor,
                  faces_left(image, actor) ? WB_ACTOR_TYPE11_WALK_LEFT
                                           : WB_ACTOR_TYPE11_WALK_RIGHT,
                  cursor);
    set_field_b(image, actor, WB_ACTOR_FIELD_18, step_cursor(cursor, WB_ACTOR_ANIM16_MASK));
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 12 ($33bc): the chaser -----------------------------------------------------------------
 *
 * 174 bytes, and the family's only user of the two leaves $2fce and $2f86: every frame it faces the
 * followed record and steps WB_ACTOR_TYPE12_WALK_STEP TOWARD it, and actor_tick_timer30 hops it
 * every WB_ACTOR_TIMER30_RELOAD frames on the generator's permission.
 *
 * ITS ANIMATION IS PICKED BY WB_ACTOR_FLAG_SUPPORTED_BIT rather than by a cursor: on the ground it
 * plays WB_ACTOR_TYPE12_GROUND_LISTS, and in the air WB_ACTOR_TYPE12_AIR_LISTS, whose lists are ONE
 * word and a terminator — so an airborne record shows a single frame and its cursor is zeroed every
 * frame by $3006's own look-ahead.
 *
 * Its hurt arm is slot 9's, and BOUNDED at WB_PLAYER_STEP_BODY for the same reason.
 */
uint32_t actor_behavior_type12(uint8_t *image, uint32_t actor) {
    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0))
        return gated_hurt_frame(image, actor, WB_ACTOR_TYPE12_HURT_LISTS);

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
    case MONSTER_STRUCK_BY_POINT:
        monster_enter_hit_animation(image, actor);
        actor_set_side_flag(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    actor_fall_and_settle(image, actor, followed_sprite_left_in_d7(image));
    actor_hop_ascend_step(image, actor);
    actor_face_and_step_toward(image, actor, WB_ACTOR_TYPE12_WALK_STEP);
    actor_tick_timer30(image, actor);

    actor_anim_step_facing_list(
        image, actor,
        flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT)
            ? WB_ACTOR_TYPE12_GROUND_LISTS
            : WB_ACTOR_TYPE12_AIR_LISTS);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 13 ($34d2): the bouncer, and the family's one CERTAIN death -----------------------------
 *
 * 246 bytes. It hops on EVERY frame it is supported — no countdown, no draw, no facing change — so
 * it is airborne almost always and its whole live frame is the settle, the ascent, the relaunch and
 * eight frames of WB_ACTOR_TYPE13_FRAMES over one cursor.
 *
 * AND ITS HURT ARM IS NOT A HURT ARM: it never lowers WB_ACTOR_FLAGS2_BIT_0 and never tests the
 * defeated mark. WB_ACTOR_FIELD_30 latched to WB_ACTOR_TYPE13_DYING arms a WB_ACTOR_TYPE13_DEATH_FRAMES
 * throe in WB_ACTOR_FIELD_31, and the frame that runs out `bra.w`s into actor_defeat_and_score
 * unconditionally — the ONE dispatch row in the family whose transfer is not a `bne`. So a struck
 * type-13 record always dies, whatever the template's hit-point pool said.
 */
static uint32_t type13_hurt_frame(uint8_t *image, uint32_t actor) {
    uint8_t throe;

    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    actor_hop_ascend_step(image, actor);

    /* `tst.b 30(a0)` — the latch is what makes this setup run on the throe's FIRST frame only. */
    if (field_b(image, actor, WB_ACTOR_FIELD_30) == 0) {
        set_field_b(image, actor, WB_ACTOR_FIELD_31, WB_ACTOR_TYPE13_DEATH_FRAMES);
        set_field_b(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE13_DYING);
        launch_at_inline_speed(image, actor, WB_ACTOR_TYPE13_DEATH_SPEED);
        actor_set_side_flag(image, actor);
    }

    step_away_without_facing(image, actor, WB_ACTOR_TYPE13_HURT_STEP);
    set_field_w(image, actor, WB_ACTOR_SPRITE, WB_ACTOR_TYPE13_HURT_SPRITE);

    /* `subq.b #1,31(a0) / bne` — the byte is stepped IN MEMORY and the branch reads that result. */
    throe = (uint8_t)(field_b(image, actor, WB_ACTOR_FIELD_31) - 1);
    set_field_b(image, actor, WB_ACTOR_FIELD_31, throe);
    if (throe != 0)
        return WB_ACTOR_DISPATCH_RAN;

    set_field_b(image, actor, WB_ACTOR_FIELD_30, 0);
    actor_defeat_and_score(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}

uint32_t actor_behavior_type13(uint8_t *image, uint32_t actor) {
    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0))
        return type13_hurt_frame(image, actor);

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
    case MONSTER_STRUCK_BY_POINT:
        monster_enter_hit_animation(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    actor_fall_and_settle(image, actor, followed_sprite_left_in_d7(image));
    actor_hop_ascend_step(image, actor);

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT))
        launch_at_inline_speed(image, actor, WB_ACTOR_TYPE13_HOP_SPEED);

    publish_frame(image, actor, WB_ACTOR_TYPE13_FRAMES,
                  field_b(image, actor, WB_ACTOR_FIELD_18));
    step_cursor_in_memory(image, actor, WB_ACTOR_FIELD_18, WB_ACTOR_ANIM16_MASK);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- batch 36: the family's second block, dispatch rows 14..19 -----------------------------------
 *
 * Six more bodies inside the same grammar, and every callee of all six is reconstructed — so unlike
 * slots 9 and 12 none of them reports a boundary. Three shapes below are shared and the rest is
 * each handler's own.
 */

/* `btst #3,9(a0) / bne.w $6bb8 / bclr #0,9(a0)` — slots 15 and 16 read the two marks in the OTHER
 * order from monster_hurt_wrap_clear_then_test's fourteen slots: the defeated bit is tested FIRST
 * and bit 0 is lowered only when the mark is down. So a record that transfers keeps BOTH marks
 * where those fourteen keep only the defeated one, and 9(a0) is where the difference shows. */
static void monster_hurt_wrap_test_then_clear(uint8_t *image, uint32_t actor) {
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT)) {
        actor_defeat_and_score(image, actor);
        return;
    }
    flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
}

/* `bsr $1b8e / cmpa.l #$0,a1 / beq` and then `move.l (a0),(a1) / move.w #type,4(a1)` — the
 * allocation, the x/y copy and the type word — the three things every spawner in this batch does,
 * though not always adjacently: slot 19 puts `subq.w #6,2(a1)` and its x offset between the copy and
 * the type, and slot 17 writes two of its own fields before the copy. Those are all disjoint
 * addresses, so the ORDER is unobservable and only the set matters.
 *
 * WHAT A REFUSAL DOES IS THE CALLER'S, AND IT DIFFERS AT ALL FOUR — this helper only reports it.
 * Slot 14 returns, but its success writes WB_ACTOR_TYPE14_SPAWN_GAP BELOW the join, so the refused
 * frame is not the successful one minus a record; slots 16 and 18 return with the launch they have
 * already made standing; slot 17 leaves its `dbf` with the seeds it already placed; and SLOT 19
 * DOES NOT RETURN AT ALL — its `beq.w $3f98` continues into the shared publish with a1 at ZERO,
 * which is the whole of type19_drop_shot's defect below and of the section
 * docs/m68k-disassembly.md writes from the same bytes.
 *
 * The x/y longword is read off the PARENT at the moment of the copy, so a spawner that has already
 * moved this frame drops its record where it now stands. */
static uint32_t spawn_minion(uint8_t *image, uint32_t actor, uint16_t type) {
    uint32_t minion = actor_alloc_slot_high(image);

    if (minion == WB_ACTOR_ALLOC_NONE)
        return WB_ACTOR_ALLOC_NONE;
    bus_write_long(image, minion, bus_read_long(image, actor));
    set_field_w(image, minion, WB_ACTOR_TYPE, type);
    return minion;
}

/* ...and the WHOLE spawn slots 16 and 18 share, which is the same instructions bar the type word:
 * the parent's flag byte AS IT STANDS (both arms have already rewritten it), the minion's speed,
 * and its countdown pair and frame cursor cleared. */
static void spawn_companion(uint8_t *image, uint32_t actor, uint16_t type) {
    uint32_t minion = spawn_minion(image, actor, type);

    if (minion == WB_ACTOR_ALLOC_NONE)
        return;
    set_field_b(image, minion, WB_ACTOR_FLAGS, field_b(image, actor, WB_ACTOR_FLAGS));
    set_field_b(image, minion, WB_ACTOR_SPEED, WB_ACTOR_MINION_SPEED);
    bus_write_long(image, addr_add(minion, WB_ACTOR_HALF_WIDTH), WB_ACTOR_MINION_SIZE);
    set_field_w(image, minion, WB_ACTOR_FIELD_30, 0);
    set_field_b(image, minion, WB_ACTOR_FIELD_18, 0);
}


/* --- slot 14 ($35d8): the patroller that drops escorts -------------------------------------------
 *
 * 316 bytes. One pixel a frame between turns, WB_ACTOR_TYPE14_TURN_FRAMES of walking per leg, and
 * every WB_ACTOR_TYPE14_SPAWN_GAP walking frames it drops a WB_ACTOR_TYPE14_MINION_TYPE record on
 * its own square. THE TURN FRAME AND THE DROP FRAME BOTH END THE FRAME — neither steps and neither
 * animates — so the record stands still on one frame in WB_ACTOR_TYPE14_TURN_FRAMES and again on
 * one in WB_ACTOR_TYPE14_SPAWN_GAP.
 *
 * Its hurt arm publishes out of ONE table for both facings and never moves at all: no settle, no
 * ascent, no retreat.
 */
static uint32_t type14_hurt_frame(uint8_t *image, uint32_t actor) {
    if (publish_and_store_cursor(image, actor, WB_ACTOR_TYPE14_HURT, WB_ACTOR_ANIM16_MASK) == 0)
        monster_hurt_wrap_clear_then_test(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}

/* $3640 — the drop. `move.b #$1e,31(a0)` is BELOW the failed-allocation branch, so a full pool
 * leaves the gap byte at zero and the record tries again on the very next walking frame. */
static void type14_drop_escort(uint8_t *image, uint32_t actor) {
    uint32_t escort = spawn_minion(image, actor, WB_ACTOR_TYPE14_MINION_TYPE);

    if (escort == WB_ACTOR_ALLOC_NONE)
        return;
    bus_write_long(image, addr_add(escort, WB_ACTOR_HALF_WIDTH), WB_ACTOR_MINION_SIZE);
    set_field_b(image, escort, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE14_MINION_TIMER);
    set_field_b(image, escort, WB_ACTOR_FIELD_31, 0);
    set_field_b(image, escort, WB_ACTOR_FIELD_18, 0);
    set_field_b(image, actor, WB_ACTOR_FIELD_31, WB_ACTOR_TYPE14_SPAWN_GAP);
}

uint32_t actor_behavior_type14(uint8_t *image, uint32_t actor) {
    uint32_t settle_span;
    uint8_t timer, gap;

    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0))
        return type14_hurt_frame(image, actor);

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
    case MONSTER_STRUCK_BY_POINT:
        monster_enter_hit_animation(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    settle_span = actor_fall_and_settle(image, actor, followed_sprite_left_in_d7(image));
    actor_hop_ascend_step(image, actor);

    timer = field_b(image, actor, WB_ACTOR_FIELD_30);
    if (timer == 0) {
        flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
        set_field_b(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE14_TURN_FRAMES);
        return WB_ACTOR_DISPATCH_RAN;
    }
    set_field_b(image, actor, WB_ACTOR_FIELD_30, (uint8_t)(timer - 1));

    gap = field_b(image, actor, WB_ACTOR_FIELD_31);
    if (gap == 0) {
        type14_drop_escort(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }
    set_field_b(image, actor, WB_ACTOR_FIELD_31, (uint8_t)(gap - 1));

    walk_and_toggle(image, actor, settle_span, WB_ACTOR_TYPE14_WALK_STEP);
    /* The facing is read AGAIN after actor_toggle_side_flag, so a blocked step's turn shows in THIS
     * frame's list — slot 6's order rather than slot 3's. */
    publish_and_store_cursor(image, actor,
                             faces_left(image, actor) ? WB_ACTOR_TYPE14_WALK_LEFT
                                                      : WB_ACTOR_TYPE14_WALK_RIGHT,
                             WB_ACTOR_ANIM32_MASK);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 15 ($3764): the walker that turns AND hops ---------------------------------------------
 *
 * 234 bytes, and the only handler in the family whose walk ends in actor_turn_and_launch ($2b8e) —
 * the two `bsr` sites that routine's plate counts are this handler's two arms. So a blocked step or
 * a one-cell drop turns the record round AND relaunches it at WB_ACTOR_TURN_LAUNCH_SPEED, where
 * slots 6, 14, 18 and 25 only turn.
 *
 * THE FRAME LIST IS CHOSEN BEFORE THE TURN CAN HAPPEN — the `lea` sits between the probe and the
 * `bsr` — so a turn shows in NEXT frame's list. Slot 14 above is the other way round.
 *
 * AND ITS TWO ARMS STEP THEIR CURSOR DIFFERENTLY: the walk is `addq.b`/`andi.b` on 18(a0) IN MEMORY
 * and the hurt arm computes in d0 and stores once, which is also why the two masks differ.
 */
static uint32_t type15_hurt_frame(uint8_t *image, uint32_t actor) {
    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    actor_hop_ascend_step(image, actor);

    if (publish_and_store_cursor(image, actor,
                                 faces_left(image, actor) ? WB_ACTOR_TYPE15_HURT_LEFT
                                                          : WB_ACTOR_TYPE15_HURT_RIGHT,
                                 WB_ACTOR_ANIM32_MASK) == 0)
        monster_hurt_wrap_test_then_clear(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}

uint32_t actor_behavior_type15(uint8_t *image, uint32_t actor) {
    uint32_t frames, ground = 0, outcome;

    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0))
        return type15_hurt_frame(image, actor);

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
    case MONSTER_STRUCK_BY_POINT:
        monster_enter_hit_animation(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    actor_fall_and_settle(image, actor, followed_sprite_left_in_d7(image));
    actor_hop_ascend_step(image, actor);

    /* `move.w #$4,d7` in BOTH arms — a WORD write, so what the settle left in the register cannot
     * reach the step. Slots 14 and 18 spell their left arm `move.b` and this one does not. */
    if (faces_left(image, actor)) {
        outcome = actor_step_left_against_map(image, actor, WB_ACTOR_TYPE15_WALK_STEP, &ground);
        frames = WB_ACTOR_TYPE15_WALK_LEFT;
    } else {
        outcome = actor_step_right_against_map(image, actor, WB_ACTOR_TYPE15_WALK_STEP, &ground);
        frames = WB_ACTOR_TYPE15_WALK_RIGHT;
    }
    actor_turn_and_launch(image, actor, outcome, ground);

    publish_frame(image, actor, frames, field_b(image, actor, WB_ACTOR_FIELD_18));
    step_cursor_in_memory(image, actor, WB_ACTOR_FIELD_18, WB_ACTOR_ANIM16_MASK);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 16 ($38ae): the hopper that lobs -------------------------------------------------------
 *
 * 312 bytes. It faces the followed record every frame and animates, and on the frame
 * WB_ACTOR_FIELD_30 runs out it launches itself and lobs a WB_ACTOR_TYPE16_MINION_TYPE record.
 *
 * `bclr #2,8(a0)` IS THE TEST AND THE WRITE. The branch reads the bit as it WAS, so an airborne
 * record leaves with its flag byte stored (unchanged in value) and nothing else done; a supported
 * one has already lost the bit by the time the launch below raises the other two.
 */
static uint32_t type16_hurt_frame(uint8_t *image, uint32_t actor) {
    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    actor_hop_ascend_step(image, actor);

    if (publish_and_store_cursor(image, actor,
                                 faces_left(image, actor) ? WB_ACTOR_TYPE16_HURT_LEFT
                                                          : WB_ACTOR_TYPE16_HURT_RIGHT,
                                 WB_ACTOR_ANIM32_MASK) == 0)
        monster_hurt_wrap_test_then_clear(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}

/* $393e — the launch and the lob. The minion inherits the flag byte AFTER the three bit writes
 * above it, so it leaves the ground with its parent. */
static void type16_launch_and_lob(uint8_t *image, uint32_t actor) {
    int was_supported = flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);

    flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
    if (!was_supported)
        return;

    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT);
    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_LAUNCHED_BIT);
    set_field_b(image, actor, WB_ACTOR_SPEED, WB_ACTOR_TYPE16_HOP_SPEED);
    set_field_b(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE16_RELOAD);
    spawn_companion(image, actor, WB_ACTOR_TYPE16_MINION_TYPE);
}

uint32_t actor_behavior_type16(uint8_t *image, uint32_t actor) {
    uint8_t timer;

    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0))
        return type16_hurt_frame(image, actor);

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
    case MONSTER_STRUCK_BY_POINT:
        monster_enter_hit_animation(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    actor_fall_and_settle(image, actor, followed_sprite_left_in_d7(image));
    actor_hop_ascend_step(image, actor);
    /* The facing is set BEFORE the list is chosen, so the frame published is always the side the
     * followed record is on this frame. */
    actor_set_side_flag(image, actor);
    publish_frame(image, actor,
                  faces_left(image, actor) ? WB_ACTOR_TYPE16_WALK_LEFT
                                           : WB_ACTOR_TYPE16_WALK_RIGHT,
                  field_b(image, actor, WB_ACTOR_FIELD_18));
    step_cursor_in_memory(image, actor, WB_ACTOR_FIELD_18, WB_ACTOR_ANIM16_MASK);

    timer = field_b(image, actor, WB_ACTOR_FIELD_30);
    if (timer != 0) {
        set_field_b(image, actor, WB_ACTOR_FIELD_30, (uint8_t)(timer - 1));
        return WB_ACTOR_DISPATCH_RAN;
    }
    type16_launch_and_lob(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 17 ($3a46): the drifter that seeds five ------------------------------------------------
 *
 * 290 bytes, and the second handler in the family that never touches the collision map: no settle,
 * no ascent, no probe, on either arm. Two GLOBAL cursors drift it on both axes out of two signed
 * tables, and when the y cursor comes back round a one-in-eight draw seeds FIVE
 * WB_ACTOR_TYPE17_SEED_TYPE records on the drifter's own square, numbered
 * WB_ACTOR_TYPE17_SEED_FIRST down to 1 in WB_ACTOR_FIELD_30.
 *
 * THE CURSORS ARE GLOBALS, so two live type-17 records drift in LOCKSTEP and one that spawns
 * mid-cycle joins wherever the other left the pair — WB_ACTOR_TYPE30_CURSOR and
 * WB_ACTOR_TYPE32_CURSOR are the tier's two other cursors of that kind. And the y table is HALF the
 * x one (WB_ACTOR_TYPE17_DY_MASK against _DX_MASK), so the y cursor comes round TWICE per
 * horizontal lap and the seeding is offered a draw at each.
 */
static uint16_t type17_drift_axis(uint8_t *image, uint32_t actor, uint32_t field,
                                  uint32_t cursor_at, uint32_t table, uint16_t mask) {
    uint16_t cursor = be16(image + cursor_at);
    /* The mask runs on the value going BACK into the global, never on the one that indexes: the
     * fetch is `lea 0(a1,d0.w),a1` on the word AS READ, sign-extended. */
    uint16_t delta = bus_read_word(image, addr_add(table, sign_ext16(cursor)));
    uint16_t stepped = (uint16_t)((cursor + WB_ACTOR_ANIM_FRAME_BYTES) & mask);

    set_field_w(image, actor, field,
                (uint16_t)((uint16_t)field_w(image, actor, field) + delta));
    wr16(image + cursor_at, stepped);
    return stepped;
}

/* $3ae6 — the seeding. A SECOND ROUTINE ENTERS HERE: `bra.w $3ae6` at $48b2 is SLOT 24's whole
 * tail, so these instructions are not slot 17's alone (../names.txt records the shared span) and
 * `actor_behavior_type24` calls this helper rather than carrying a second copy. The `dbf` loop
 * takes a fresh record each turn and RETURNS on the first refusal, so a pool with room for three
 * seeds three and stops. */
static void type17_seed_burst(uint8_t *image, uint32_t actor) {
    uint8_t ordinal = WB_ACTOR_TYPE17_SEED_FIRST;
    unsigned remaining;

    if ((rng_next(image, 0) & WB_ACTOR_TYPE17_SEED_ODDS_MASK) != 0)
        return;

    for (remaining = WB_ACTOR_TYPE17_SEED_DBF_COUNT + 1; remaining > 0; remaining--) {
        /* The original writes the flag byte and the ordinal BEFORE the x/y copy `spawn_minion`
         * makes; the two touch different fields, so only the bit writes below — which read 8(a1)
         * back — depend on the order, and they follow it. */
        uint32_t seed = actor_alloc_slot_high(image);

        if (seed == WB_ACTOR_ALLOC_NONE)
            return;
        set_field_b(image, seed, WB_ACTOR_FLAGS, field_b(image, actor, WB_ACTOR_FLAGS));
        set_field_b(image, seed, WB_ACTOR_FIELD_30, ordinal--);
        bus_write_long(image, seed, bus_read_long(image, actor));
        bus_write_long(image, addr_add(seed, WB_ACTOR_HALF_WIDTH), WB_ACTOR_TYPE17_SEED_SIZE);
        set_field_w(image, seed, WB_ACTOR_TYPE, WB_ACTOR_TYPE17_SEED_TYPE);
        flag_set(image, seed, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT);
        flag_set(image, seed, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_LAUNCHED_BIT);
        flag_clear(image, seed, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
        set_field_b(image, seed, WB_ACTOR_SPEED, WB_ACTOR_TYPE17_SEED_SPEED);
    }
}

uint32_t actor_behavior_type17(uint8_t *image, uint32_t actor) {
    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        actor_anim_step_facing_list(image, actor, WB_ACTOR_TYPE17_HURT_LISTS);
        /* `tst.b 18(a0)` — the cursor RE-READ after $3006 stored it, so the wrap is the list's own
         * terminator and not a value this frame kept. */
        if (field_b(image, actor, WB_ACTOR_FIELD_18) == 0)
            monster_hurt_wrap_clear_then_test(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
    case MONSTER_STRUCK_BY_POINT:
        monster_enter_hit_animation(image, actor);
        actor_set_side_flag(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    actor_set_side_flag(image, actor);
    actor_anim_step_facing_list(image, actor, WB_ACTOR_TYPE17_LIVE_LISTS);
    type17_drift_axis(image, actor, WB_ACTOR_X, WB_ACTOR_TYPE17_DX_CURSOR,
                      WB_ACTOR_TYPE17_DX, WB_ACTOR_TYPE17_DX_MASK);
    if (type17_drift_axis(image, actor, WB_ACTOR_Y, WB_ACTOR_TYPE17_DY_CURSOR,
                          WB_ACTOR_TYPE17_DY, WB_ACTOR_TYPE17_DY_MASK) != 0)
        return WB_ACTOR_DISPATCH_RAN;

    type17_seed_burst(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 18 ($3c84): the charger --------------------------------------------------------------
 *
 * 424 bytes, the largest body in the family. It walks WB_ACTOR_TYPE18_WALK_STEP a frame while
 * WB_ACTOR_FIELD_30 runs, and when that reaches zero it CHARGES: the whole flag byte is saved into
 * WB_ACTOR_FIELD_29, the record faces the followed one and launches, and a
 * WB_ACTOR_TYPE18_MINION_TYPE record is spawned beside it. WB_ACTOR_FIELD_31 latched to
 * WB_ACTOR_TYPE18_CHARGING is what says a charge is running; when the record is supported again the
 * saved byte goes back, the latch is cleared and it turns round.
 *
 * SLOT 18 AND SLOT 19 SPLIT THE STRUCK ARM: actor_set_side_flag runs on the overlap-POINT arm only,
 * and the body arm flips the facing before actor_damage_followed — which no other handler in the
 * family does.
 */
/* SLOT 25 IS THIS SAME ROUTINE. $4916..$4abd repeats $3c84..$3e2b instruction for instruction with
 * four table addresses and one minion type changed — batch 37 read both — so the body below is
 * parametrised and each row names its own constants. Slot 25's last `rts` is not even its own: its
 * `bne.w $3e2a` at $4aa8 borrows slot 18's. */
typedef struct {
    uint32_t walk_left, walk_right;   /* 16 words each, WB_ACTOR_ANIM32_MASK */
    uint32_t hurt_left, hurt_right;   /* 8 words each, WB_ACTOR_ANIM16_MASK */
    uint8_t walk_step, hurt_step, charging, hop_speed, turn_frames;
    uint16_t minion_type;
} ChargerFrames;

static const ChargerFrames TYPE18_FRAMES = {
    WB_ACTOR_TYPE18_WALK_LEFT, WB_ACTOR_TYPE18_WALK_RIGHT,
    WB_ACTOR_TYPE18_HURT_LEFT, WB_ACTOR_TYPE18_HURT_RIGHT,
    WB_ACTOR_TYPE18_WALK_STEP, WB_ACTOR_TYPE18_HURT_STEP, WB_ACTOR_TYPE18_CHARGING,
    WB_ACTOR_TYPE18_HOP_SPEED, WB_ACTOR_TYPE18_TURN_FRAMES, WB_ACTOR_TYPE18_MINION_TYPE,
};

static const ChargerFrames TYPE25_FRAMES = {
    WB_ACTOR_TYPE25_WALK_LEFT, WB_ACTOR_TYPE25_WALK_RIGHT,
    WB_ACTOR_TYPE25_HURT_LEFT, WB_ACTOR_TYPE25_HURT_RIGHT,
    WB_ACTOR_TYPE25_WALK_STEP, WB_ACTOR_TYPE25_HURT_STEP, WB_ACTOR_TYPE25_CHARGING,
    WB_ACTOR_TYPE25_HOP_SPEED, WB_ACTOR_TYPE25_TURN_FRAMES, WB_ACTOR_TYPE25_MINION_TYPE,
};

static uint32_t charger_hurt_frame(uint8_t *image, uint32_t actor, const ChargerFrames *f) {
    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT))
        step_away_without_facing(image, actor, f->hurt_step);

    if (publish_and_store_cursor(image, actor,
                                 faces_left(image, actor) ? f->hurt_left : f->hurt_right,
                                 WB_ACTOR_ANIM16_MASK) == 0)
        monster_hurt_wrap_clear_then_test(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}

/* $3cf2 / $4984 — the charge. The flag byte is saved BEFORE actor_set_side_flag and
 * actor_start_motion_at_speed rewrite it, which is what makes the restore below a restore. */
static void charger_charge(uint8_t *image, uint32_t actor, const ChargerFrames *f) {
    set_field_b(image, actor, WB_ACTOR_FIELD_31, f->charging);
    set_field_b(image, actor, WB_ACTOR_FIELD_29, field_b(image, actor, WB_ACTOR_FLAGS));
    actor_set_side_flag(image, actor);
    actor_start_motion_at_speed(image, actor, f->hop_speed);
    spawn_companion(image, actor, f->minion_type);
}

static uint32_t charger_frame(uint8_t *image, uint32_t actor, const ChargerFrames *f) {
    uint32_t settle_span;
    uint8_t timer;

    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0))
        return charger_hurt_frame(image, actor, f);

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK_BY_POINT:
        actor_set_side_flag(image, actor);
        /* fall through — the point arm's `bsr $67c2` sits ABOVE the join the shot arm enters */
    case MONSTER_STRUCK:
        monster_enter_hit_animation(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    settle_span = actor_fall_and_settle(image, actor, followed_sprite_left_in_d7(image));
    actor_hop_ascend_step(image, actor);

    timer = field_b(image, actor, WB_ACTOR_FIELD_30);
    if (timer != 0) {
        set_field_b(image, actor, WB_ACTOR_FIELD_30, (uint8_t)(timer - 1));
        walk_and_toggle(image, actor, settle_span, f->walk_step);
    } else if (field_b(image, actor, WB_ACTOR_FIELD_31) == 0) {
        charger_charge(image, actor, f);
        return WB_ACTOR_DISPATCH_RAN;
    } else if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT)) {
        restore_flags_and_turn(image, actor, f->turn_frames);
        return WB_ACTOR_DISPATCH_RAN;
    }

    /* A record still in the air mid-charge reaches this ANIMATION ALONE: no step and no turn, which
     * is what the `beq.w $3d86` past the restore does. */
    publish_and_store_cursor(image, actor,
                             faces_left(image, actor) ? f->walk_left : f->walk_right,
                             WB_ACTOR_ANIM32_MASK);
    return WB_ACTOR_DISPATCH_RAN;
}

uint32_t actor_behavior_type18(uint8_t *image, uint32_t actor) {
    return charger_frame(image, actor, &TYPE18_FRAMES);
}


/* --- slot 19 ($3e8c): the glider that turns into an attacker -------------------------------------
 *
 * 364 bytes, and a record that ALTERNATES between two phases: while WB_ACTOR_FIELD_31 is clear it
 * glides on WB_ACTOR_TYPE19_DRIFT's 64 signed words with one fixed sprite and a narrow box, and the
 * frame the drift cursor wraps `st 31(a0)` puts it into its attack phase — until the ATTACK cursor
 * wraps in turn and `clr.b 31(a0)` at $3fb0 puts it back in the glide. Neither latch is permanent,
 * and an earlier revision of this plate called the first latch permanent. There it faces the
 * followed record, doubles its box, animates over WB_ACTOR_TYPE19_FRAME_MASK, and on the ONE cursor
 * value WB_ACTOR_TYPE19_SHOT_CURSOR drops a WB_ACTOR_TYPE19_SHOT_TYPE record.
 *
 * THE HURT ARM LETS AN UNDEFEATED RECORD OUT AT ONCE — bit 0 down and return, no animation at all —
 * and a DEFEATED one plays WB_ACTOR_TYPE19_DEATH and ends `bclr #0,9(a0) / bra.w $6bb8`, the second
 * unconditional transfer in the family after slot 13's.
 */
static uint32_t type19_hurt_frame(uint8_t *image, uint32_t actor) {
    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT)) {
        flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
        return WB_ACTOR_DISPATCH_RAN;
    }

    if (publish_and_store_cursor(image, actor, WB_ACTOR_TYPE19_DEATH, WB_ACTOR_ANIM32_MASK) == 0) {
        flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
        actor_defeat_and_score(image, actor);
    }
    return WB_ACTOR_DISPATCH_RAN;
}

/* $3ee2 — the glide. The cursor is WB_ACTOR_FIELD_30, not the frame cursor, and the sprite and the
 * box are rewritten on EVERY glide frame rather than once. */
static void type19_glide(uint8_t *image, uint32_t actor) {
    uint8_t cursor = field_b(image, actor, WB_ACTOR_FIELD_30);
    uint16_t delta = bus_read_word(image, addr_add(WB_ACTOR_TYPE19_DRIFT, cursor));
    uint8_t stepped = (uint8_t)((cursor + WB_ACTOR_ANIM_FRAME_BYTES) & WB_ACTOR_TYPE19_DRIFT_MASK);

    set_field_w(image, actor, WB_ACTOR_SPRITE, WB_ACTOR_TYPE19_GLIDE_SPRITE);
    set_field_w(image, actor, WB_ACTOR_SIZE_SECOND, WB_ACTOR_TYPE19_GLIDE_HEIGHT);
    set_field_w(image, actor, WB_ACTOR_X,
                (uint16_t)((uint16_t)field_w(image, actor, WB_ACTOR_X) + delta));
    set_field_b(image, actor, WB_ACTOR_FIELD_30, stepped);
    if (stepped == 0)
        set_field_b(image, actor, WB_ACTOR_FIELD_31, WB_ACTOR_TYPE19_PHASE2);
}

/* $3f4a — the shot, and it hands back the ADDRESS the caller's `a1` now holds. That is not a
 * convenience: `bsr $1b8e` returns in the very register the frame table was `lea`d into, and the
 * publish below the two arms' join reads through it. So the frame published on the firing frame is
 * a word of the NEW RECORD, and on a full pool a1 is 0 and the word comes from address $14. */
static uint32_t type19_drop_shot(uint8_t *image, uint32_t actor) {
    uint32_t shot = spawn_minion(image, actor, WB_ACTOR_TYPE19_SHOT_TYPE);

    if (shot == WB_ACTOR_ALLOC_NONE)
        return WB_ACTOR_ALLOC_NONE;
    set_field_w(image, shot, WB_ACTOR_Y,
                (uint16_t)((uint16_t)field_w(image, shot, WB_ACTOR_Y)
                           - WB_ACTOR_TYPE19_SHOT_RISE));
    set_field_w(image, shot, WB_ACTOR_X,
                (uint16_t)((uint16_t)field_w(image, shot, WB_ACTOR_X)
                           + (faces_left(image, actor) ? WB_ACTOR_TYPE19_SHOT_DX_LEFT
                                                       : WB_ACTOR_TYPE19_SHOT_DX_RIGHT)));
    set_field_b(image, shot, WB_ACTOR_FLAGS, field_b(image, actor, WB_ACTOR_FLAGS));
    bus_write_long(image, addr_add(shot, WB_ACTOR_HALF_WIDTH), WB_ACTOR_TYPE19_SHOT_SIZE);
    set_field_w(image, shot, WB_ACTOR_FIELD_30, 0);
    set_field_b(image, shot, WB_ACTOR_FIELD_18, 0);
    flag_clear(image, shot, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
    return shot;
}

/* $3f18 — the attack phase. */
static void type19_attack(uint8_t *image, uint32_t actor) {
    uint32_t frames;
    uint8_t cursor, stepped;

    set_field_w(image, actor, WB_ACTOR_SIZE_SECOND, WB_ACTOR_TYPE19_ATTACK_HEIGHT);
    actor_set_side_flag(image, actor);
    frames = faces_left(image, actor) ? WB_ACTOR_TYPE19_FRAMES_LEFT
                                      : WB_ACTOR_TYPE19_FRAMES_RIGHT;

    cursor = field_b(image, actor, WB_ACTOR_FIELD_18);
    if (cursor == WB_ACTOR_TYPE19_SHOT_CURSOR)
        frames = type19_drop_shot(image, actor);

    publish_frame(image, actor, frames, cursor);
    stepped = step_cursor(cursor, WB_ACTOR_TYPE19_FRAME_MASK);
    set_field_b(image, actor, WB_ACTOR_FIELD_18, stepped);
    /* The wrap ends the attack RUN, not the record: WB_ACTOR_FIELD_31 back to zero puts it in the
     * glide again, whose own wrap will latch it back here. */
    if (stepped == 0)
        set_field_b(image, actor, WB_ACTOR_FIELD_31, 0);
}

uint32_t actor_behavior_type19(uint8_t *image, uint32_t actor) {

    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0))
        return type19_hurt_frame(image, actor);

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK_BY_POINT:
        actor_set_side_flag(image, actor);
        /* fall through — the point arm's `bsr $67c2` sits ABOVE the join the shot arm enters */
    case MONSTER_STRUCK:
        monster_enter_hit_animation(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    if (field_b(image, actor, WB_ACTOR_FIELD_31) == 0)
        type19_glide(image, actor);
    else
        type19_attack(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- the family CLOSES, dispatch rows 20..27 ($4118..$4dd7; batch 37) ---------------------------
 *
 * Eight more middles, and what the block adds is REUSE. Slot 20 and slot 27 are the same 378 bytes
 * twice; slot 23 is slot 4's body with a different contact arm and BRANCHES INTO IT; slot 25 is
 * slot 18's charge; slot 26 is slot 12's chase; slots 22 and 26 share slot 9's gated hurt arm; and
 * slot 24 LEAVES for slot 17's seeding. So five of the eight are parametrisations of code this port
 * already had, and only slots 21, 23's theft and 24 are new instructions.
 */

/* Slots 20 and 27, whose ONE body reads six addresses at a time. LEFT is what the
 * `btst #3,8(a0) / bne` arm reaches — the list played while WB_ACTOR_FLAG_SIDE_BIT is SET. */
typedef struct {
    uint32_t walk_left, walk_right;   /* 8 words each, WB_ACTOR_ANIM16_MASK */
    uint32_t hurt_left, hurt_right;   /* 16 words each, WB_ACTOR_ANIM32_MASK */
    uint16_t air_left, air_right;     /* published straight while the record is off the ground */
} HopperFrames;

static const HopperFrames TYPE20_FRAMES = {
    WB_ACTOR_TYPE20_WALK_LEFT, WB_ACTOR_TYPE20_WALK_RIGHT,
    WB_ACTOR_TYPE20_HURT_LEFT, WB_ACTOR_TYPE20_HURT_RIGHT,
    WB_ACTOR_TYPE20_AIR_LEFT, WB_ACTOR_TYPE20_AIR_RIGHT,
};

static const HopperFrames TYPE27_FRAMES = {
    WB_ACTOR_TYPE27_WALK_LEFT, WB_ACTOR_TYPE27_WALK_RIGHT,
    WB_ACTOR_TYPE27_HURT_LEFT, WB_ACTOR_TYPE27_HURT_RIGHT,
    WB_ACTOR_TYPE27_AIR_LEFT, WB_ACTOR_TYPE27_AIR_RIGHT,
};

/* $4214 / $4d5a. The retreat is suppressed once the record is marked defeated, and the wrap does
 * one thing no other hurt arm in the family does: `st 30(a0)` BEFORE the two mark instructions, so
 * a recovered record's very next live frame finds its countdown already negative and goes straight
 * to the reload and the draw. */
static uint32_t hopper_hurt_frame(uint8_t *image, uint32_t actor, const HopperFrames *f) {
    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    actor_hop_ascend_step(image, actor);
    actor_set_side_flag(image, actor);

    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_DEFEATED_BIT))
        step_away_without_facing(image, actor, WB_ACTOR_TYPE20_HURT_STEP);

    if (publish_and_store_cursor(image, actor,
                                 faces_left(image, actor) ? f->hurt_left : f->hurt_right,
                                 WB_ACTOR_ANIM32_MASK) == 0) {
        set_field_b(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE20_RECOVER);
        monster_hurt_wrap_clear_then_test(image, actor);
    }
    return WB_ACTOR_DISPATCH_RAN;
}

/* $415c / $4ca2. A supported record counts WB_ACTOR_FIELD_30 down and, on the frame the decrement
 * goes NEGATIVE, reloads and rolls for a hop; the hop is a TAIL jump into
 * actor_start_motion_at_speed, so it ends the frame with no step and no animation. */
static uint32_t hopper_live_frame(uint8_t *image, uint32_t actor, const HopperFrames *f) {
    uint32_t outcome;

    actor_fall_and_settle(image, actor, followed_sprite_left_in_d7(image));
    actor_hop_ascend_step(image, actor);

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT)) {
        /* `subq.b #1,30(a0) / bpl` — the SIGN of what the decrement LEFT, so the reload fires on
         * the frame the byte passes $00 into $ff and not on the frame it reaches zero. */
        uint8_t timer = (uint8_t)(field_b(image, actor, WB_ACTOR_FIELD_30) - 1);

        actor_set_side_flag(image, actor);
        set_field_b(image, actor, WB_ACTOR_FIELD_30, timer);
        if ((int8_t)timer < 0) {
            set_field_b(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE20_HOP_RELOAD);
            /* `btst #2,d0 / bne` — the bit SET is the veto, so the hop takes half the reloads. */
            if ((rng_next(image, 0) & (1u << WB_ACTOR_TYPE20_HOP_RNG_BIT)) == 0) {
                actor_start_motion_at_speed(image, actor, WB_ACTOR_TYPE20_HOP_SPEED);
                return WB_ACTOR_DISPATCH_RAN;
            }
        }
    }

    /* `move.w #$2,d7` in BOTH arms, so nothing of the settle's register reaches the step. */
    outcome = step_facing(image, actor, WB_ACTOR_TYPE20_WALK_STEP);
    /* `tst.w d0` — the WORD test slot 28 spells too; these two bodies and its own are the whole
     * census of it. */
    if (step_word_was_blocked_at_column_0(outcome))
        flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);

    /* The facing is read AGAIN below the turn, so a blocked step's turn shows in THIS frame's
     * sprite — slot 6's order rather than slot 3's. */
    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT)) {
        set_field_w(image, actor, WB_ACTOR_SPRITE,
                    faces_left(image, actor) ? f->air_left : f->air_right);
        return WB_ACTOR_DISPATCH_RAN;
    }
    publish_and_store_cursor(image, actor,
                             faces_left(image, actor) ? f->walk_left : f->walk_right,
                             WB_ACTOR_ANIM16_MASK);
    return WB_ACTOR_DISPATCH_RAN;
}

static uint32_t hopper_frame(uint8_t *image, uint32_t actor, const HopperFrames *f) {
    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0))
        return hopper_hurt_frame(image, actor, f);

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK_BY_POINT:
        actor_set_side_flag(image, actor);
        /* fall through — the point arm's `bsr $67c2` sits ABOVE the join the shot arm enters */
    case MONSTER_STRUCK:
        monster_enter_hit_animation(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }
    return hopper_live_frame(image, actor, f);
}

uint32_t actor_behavior_type20(uint8_t *image, uint32_t actor) {
    return hopper_frame(image, actor, &TYPE20_FRAMES);
}

uint32_t actor_behavior_type27(uint8_t *image, uint32_t actor) {
    return hopper_frame(image, actor, &TYPE27_FRAMES);
}


/* --- slot 21 ($42f2): the sentry that aims -------------------------------------------------------
 *
 * 362 bytes, and the ONLY handler in the family that never calls actor_fall_and_settle: it does not
 * fall, hop or step on any arm. WB_ACTOR_FIELD_30 is a FLAG rather than a countdown — nothing steps
 * it — and it says which of the two halves the frame runs:
 *   * CLEAR: play the walk list, and on its wrap `st 30(a0)` puts the record into the other half;
 *   * SET: if the followed record is within WB_ACTOR_TYPE21_REACH and a
 *     WB_ACTOR_TYPE21_SHOT_ODDS_MASK draw comes up zero, clear the flag and fire.
 * THE FLAG IS CLEARED BEFORE THE ALLOCATION, so a refused shot still puts the record back into its
 * animation half — where slot 14's refused drop leaves its own gap byte standing.
 *
 * THE SHOT IS AIMED, which nothing else in this tier is: $6528 quantises the vector to the followed
 * record into one of sixteen directions and the pair it returns becomes the shot's
 * WB_ACTOR_FIELD_30 / _31. And `clr.w d1` on an EQUAL y overwrites the returned dy with zero, so a
 * shot fired at a record on the same line travels flat whatever the table said.
 */
static uint32_t type21_hurt_frame(uint8_t *image, uint32_t actor) {
    if (publish_and_store_cursor(image, actor,
                                 faces_left(image, actor) ? WB_ACTOR_TYPE21_HURT_LEFT
                                                          : WB_ACTOR_TYPE21_HURT_RIGHT,
                                 WB_ACTOR_ANIM16_MASK) == 0)
        monster_hurt_wrap_clear_then_test(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}

static void type21_fire(uint8_t *image, uint32_t actor) {
    uint32_t followed = followed_actor_record(image);
    uint32_t shot;
    int16_t dx, dy;

    set_field_b(image, actor, WB_ACTOR_FIELD_30, 0);
    shot = spawn_minion(image, actor, WB_ACTOR_TYPE21_SHOT_TYPE);
    if (shot == WB_ACTOR_ALLOC_NONE)
        return;

    set_field_w(image, shot, WB_ACTOR_Y,
                (uint16_t)(field_w(image, shot, WB_ACTOR_Y) - WB_ACTOR_TYPE21_SHOT_RISE));
    set_field_b(image, shot, WB_ACTOR_FLAGS, field_b(image, actor, WB_ACTOR_FLAGS));
    bus_write_long(image, addr_add(shot, WB_ACTOR_HALF_WIDTH), WB_ACTOR_TYPE21_SHOT_SIZE);

    actor_aim_velocity(image, (uint16_t)field_w(image, actor, WB_ACTOR_X),
                       (uint16_t)field_w(image, actor, WB_ACTOR_Y),
                       (uint16_t)field_w(image, followed, WB_ACTOR_X),
                       (uint16_t)field_w(image, followed, WB_ACTOR_Y),
                       WB_ACTOR_TYPE21_AIM_ROW, &dx, &dy);
    set_field_b(image, shot, WB_ACTOR_FIELD_30, (uint8_t)dx);
    if (field_w(image, actor, WB_ACTOR_Y) == field_w(image, followed, WB_ACTOR_Y))
        dy = 0;
    set_field_b(image, shot, WB_ACTOR_FIELD_31, (uint8_t)dy);

    set_field_b(image, shot, WB_ACTOR_FIELD_29, WB_ACTOR_TYPE21_SHOT_LIFE);
    set_field_b(image, shot, WB_ACTOR_FIELD_18, 0);
    flag_clear(image, shot, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
}

uint32_t actor_behavior_type21(uint8_t *image, uint32_t actor) {
    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0))
        return type21_hurt_frame(image, actor);

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK_BY_POINT:
        actor_set_side_flag(image, actor);
        /* fall through — the point arm's `bsr $67c2` sits ABOVE the join the shot arm enters */
    case MONSTER_STRUCK:
        monster_enter_hit_animation(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    actor_set_side_flag(image, actor);
    if (field_b(image, actor, WB_ACTOR_FIELD_30) == 0) {
        if (publish_and_store_cursor(image, actor,
                                     faces_left(image, actor) ? WB_ACTOR_TYPE21_WALK_LEFT
                                                              : WB_ACTOR_TYPE21_WALK_RIGHT,
                                     WB_ACTOR_ANIM32_MASK) == 0)
            set_field_b(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE21_AIMING);
        return WB_ACTOR_DISPATCH_RAN;
    }

    if ((int16_t)actor_followed_x_within(image, actor, WB_ACTOR_TYPE21_REACH) < 0)
        return WB_ACTOR_DISPATCH_RAN;
    if ((rng_next(image, 0) & WB_ACTOR_TYPE21_SHOT_ODDS_MASK) != 0)
        return WB_ACTOR_DISPATCH_RAN;

    type21_fire(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 22 ($44bc): the launcher ---------------------------------------------------------------
 *
 * 264 bytes. It takes no step on any arm; WB_ACTOR_FIELD_30 runs down and the frame it reaches zero
 * the record LAUNCHES ITSELF — three bit writes and a speed spelt inline rather than through
 * actor_start_motion_at_speed — and reloads. Below that it animates and then, while
 * WB_ACTOR_TYPE53_ALIVE is clear and one draw in eight, drops a WB_ACTOR_TYPE22_MINION_TYPE record.
 *
 * `bclr #2,8(a0) / beq` IS THE TEST AND THE WRITE: an AIRBORNE record with a zero countdown stores
 * its flag byte unchanged and then falls into `subq.b #1,30(a0)`, which wraps the byte to $ff — so
 * the launch is not merely skipped, the countdown is re-armed at its longest.
 *
 * Its hurt arm is slot 9's `gated_hurt_frame`, and BOUNDED at WB_PLAYER_STEP_BODY for the same
 * reason: `bsr $d78` while WB_TILE_33_MODE is clear reports an address rather than a result.
 */
static void type22_drop_minion(uint8_t *image, uint32_t actor) {
    uint32_t minion = spawn_minion(image, actor, WB_ACTOR_TYPE22_MINION_TYPE);

    if (minion == WB_ACTOR_ALLOC_NONE)
        return;
    set_field_w(image, minion, WB_ACTOR_Y,
                (uint16_t)(field_w(image, minion, WB_ACTOR_Y) - WB_ACTOR_TYPE22_MINION_RISE));
    /* `move.w 8(a0),8(a1)` — a WORD, so WB_ACTOR_FLAGS2 comes across with the flag byte. */
    set_field_w(image, minion, WB_ACTOR_FLAGS, (uint16_t)field_w(image, actor, WB_ACTOR_FLAGS));
    set_field_b(image, minion, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE22_MINION_TIMER);
    bus_write_long(image, addr_add(minion, WB_ACTOR_HALF_WIDTH), WB_ACTOR_TYPE22_MINION_SIZE);
}

uint32_t actor_behavior_type22(uint8_t *image, uint32_t actor) {
    uint8_t timer;
    int launched;

    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0))
        return gated_hurt_frame(image, actor, WB_ACTOR_TYPE22_HURT_LISTS);

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
    case MONSTER_STRUCK_BY_POINT:
        /* The facing runs BELOW both writes here, where slot 6 puts it between them. */
        monster_enter_hit_animation(image, actor);
        actor_set_side_flag(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    actor_fall_and_settle(image, actor, followed_sprite_left_in_d7(image));
    actor_hop_ascend_step(image, actor);
    actor_set_side_flag(image, actor);

    timer = field_b(image, actor, WB_ACTOR_FIELD_30);
    launched = 0;
    if (timer == 0) {
        /* `bclr #2,8(a0) / beq` — the bit is CLEARED whichever arm the branch takes, so an airborne
         * record stores its flag byte unchanged and then falls into the decrement below. */
        launched = flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
        flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
    }
    if (launched) {
        set_field_b(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE22_RELOAD);
        flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT);
        flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_LAUNCHED_BIT);
        set_field_b(image, actor, WB_ACTOR_SPEED, WB_ACTOR_TYPE22_LAUNCH_SPEED);
    } else {
        /* ...and on a countdown ALREADY zero that decrement wraps the byte to $ff, so the record
         * waits the longest possible time for its next launch rather than retrying at once. */
        set_field_b(image, actor, WB_ACTOR_FIELD_30, (uint8_t)(timer - 1));
    }

    actor_anim_step_facing_list(image, actor, WB_ACTOR_TYPE22_LIVE_LISTS);

    if (be16(image + WB_ACTOR_TYPE53_ALIVE) != 0)
        return WB_ACTOR_DISPATCH_RAN;
    if ((rng_next(image, 0) & WB_ACTOR_TYPE22_SEED_ODDS_MASK) != 0)
        return WB_ACTOR_DISPATCH_RAN;

    type22_drop_minion(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 23 ($461c): the GOLD THIEF, and slot 4's body -------------------------------------------
 *
 * 432 bytes, of which the live arm and the death arm are actor_behavior_type04's instruction for
 * instruction — `hover_chase_frame` and `hover_death_frame` above serve both — and only the
 * footprint arm is this handler's own. It also BRANCHES INTO SLOT 4: `bra.w $2840` at $46fe leaves
 * this extent for slot 4's publish-and-hover tail, so one of its own paths runs another handler's
 * bytes, and its copy of the hover reads WB_ACTOR_TYPE04_HOVER through the SHORT absolute encoding.
 *
 * THE THEFT. Touching the followed record charges WB_ACTOR_TYPE23_STEAL_MAX from
 * WB_BCD_COUNTER and drops a WB_ACTOR_TYPE23_LOOT_TYPE record carrying it — unless the record
 * is already flickering (WB_ACTOR_FLAG_FLICKER_BIT, i.e. mid-invulnerability) or its purse is
 * already empty, in which cases the frame is an ordinary actor_damage_followed. A purse AT OR BELOW
 * the maximum is `clr.w`ed rather than subtracted, so the two arms are not one clamped subtraction.
 *
 * AND WB_ACTOR_TYPE23_STUN_FRAMES IS WRITTEN BELOW THE FAILED-ALLOCATION BRANCH, so a full pool
 * puts it at offset WB_ACTOR_FIELD_21 of address ZERO — slot 19's defect one handler on, and
 * reproduced rather than repaired.
 */
static void type23_rob_the_followed(uint8_t *image, uint32_t actor) {
    uint32_t followed = followed_actor_record(image);
    uint32_t loot;
    uint16_t purse;

    if (flag_is_set(image, followed, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT))
        return;
    purse = be16(image + WB_BCD_COUNTER);
    if (purse == 0)
        return;

    if ((int16_t)purse > (int16_t)WB_ACTOR_TYPE23_STEAL_MAX)
        bcd_sub_counter_bd6e(image, WB_ACTOR_TYPE23_STEAL_MAX, overlap_mask_exit_extend(image));
    else
        wr16(image + WB_BCD_COUNTER, 0);

    loot = spawn_minion(image, actor, WB_ACTOR_TYPE23_LOOT_TYPE);
    if (loot != WB_ACTOR_ALLOC_NONE) {
        set_field_b(image, loot, WB_ACTOR_FIELD_30, WB_ACTOR_TYPE23_LOOT_TIMER);
        set_field_b(image, loot, WB_ACTOR_FIELD_18, 0);
    }
    set_field_b(image, loot, WB_ACTOR_FIELD_21, WB_ACTOR_TYPE23_STUN_FRAMES);
}

uint32_t actor_behavior_type23(uint8_t *image, uint32_t actor) {
    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        hover_death_frame(image, actor, WB_ACTOR_TYPE23_DEAD_LEFT, WB_ACTOR_TYPE23_DEAD_RIGHT,
                          WB_ACTOR_TYPE23_DEAD_STEP);
        return WB_ACTOR_DISPATCH_RAN;
    }

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        type23_rob_the_followed(image, actor);
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
    case MONSTER_STRUCK_BY_POINT:
        monster_enter_hit_animation(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    hover_chase_frame(image, actor, WB_ACTOR_TYPE23_FLY_LEFT, WB_ACTOR_TYPE23_FLY_RIGHT,
                      WB_ACTOR_TYPE23_FLY_STEP);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 24 ($484c): the drifter's twin ----------------------------------------------------------
 *
 * 150 bytes, the shortest body in the family, and it does not END in its own extent: the
 * `bra.w $3ae6` at $48b2 leaves for actor_behavior_type17's seeding block, so this handler's tail is
 * slot 17's. `type17_seed_burst` is called rather than re-ported, which is the obligation
 * ../names.txt's plate on $484c states.
 *
 * Both of its list PAIRS hold the SAME list twice, so the facing $3006 reads decides nothing.
 */
static uint32_t type24_hurt_frame(uint8_t *image, uint32_t actor) {
    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    actor_hop_ascend_step(image, actor);
    actor_anim_step_facing_list(image, actor, WB_ACTOR_TYPE24_HURT_LISTS);

    /* `tst.b 18(a0)` — the cursor RE-READ after $3006 stored it. */
    if (field_b(image, actor, WB_ACTOR_FIELD_18) == 0)
        monster_hurt_wrap_clear_then_test(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}

uint32_t actor_behavior_type24(uint8_t *image, uint32_t actor) {
    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0))
        return type24_hurt_frame(image, actor);

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
    case MONSTER_STRUCK_BY_POINT:
        monster_enter_hit_animation(image, actor);
        actor_set_side_flag(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    actor_fall_and_settle(image, actor, followed_sprite_left_in_d7(image));
    actor_hop_ascend_step(image, actor);
    actor_set_side_flag(image, actor);
    actor_step_facing(image, actor, WB_ACTOR_TYPE24_WALK_STEP);
    actor_anim_step_facing_list(image, actor, WB_ACTOR_TYPE24_LIVE_LISTS);
    type17_seed_burst(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 25 ($4916): slot 18's charge again ------------------------------------------------------
 *
 * 424 bytes and not one of them new: every instruction of $3c84..$3e2b appears here with four table
 * addresses and one minion type changed, and the hurt arm's own wrap branch leaves for slot 18's
 * `rts` rather than spelling one. `charger_frame` above is the whole of it.
 */
uint32_t actor_behavior_type25(uint8_t *image, uint32_t actor) {
    return charger_frame(image, actor, &TYPE25_FRAMES);
}


/* --- slot 26 ($4b1e): the chaser that shoots ------------------------------------------------------
 *
 * 216 bytes, and slot 12's live arm with one instruction added: face the followed record, step
 * WB_ACTOR_TYPE26_STEP toward it, tick the hop timer — and then choose the frame list by
 * WB_ACTOR_FLAG_MOVING_BIT rather than by the supported one. On the arm that bit picks, the record
 * also drops a WB_ACTOR_TYPE26_SHOT_TYPE record with the widest box any spawner in this tier writes.
 *
 * THE SHOT IS ON THE SAME ARM AS THE FRAME LIST, so a refused allocation still plays the moving
 * list; and the bit is read AFTER actor_tick_timer30, which is what can raise it.
 *
 * Its hurt arm is slot 9's `gated_hurt_frame`, and BOUNDED for the same reason.
 */
static void type26_drop_shot(uint8_t *image, uint32_t actor) {
    uint32_t shot = spawn_minion(image, actor, WB_ACTOR_TYPE26_SHOT_TYPE);

    if (shot == WB_ACTOR_ALLOC_NONE)
        return;
    set_field_w(image, shot, WB_ACTOR_Y,
                (uint16_t)(field_w(image, shot, WB_ACTOR_Y) - WB_ACTOR_TYPE26_SHOT_RISE));
    set_field_w(image, shot, WB_ACTOR_FLAGS, (uint16_t)field_w(image, actor, WB_ACTOR_FLAGS));
    bus_write_long(image, addr_add(shot, WB_ACTOR_HALF_WIDTH), WB_ACTOR_TYPE26_SHOT_SIZE);
}

uint32_t actor_behavior_type26(uint8_t *image, uint32_t actor) {
    if (spawn_animation_took_the_frame(image, actor))
        return WB_ACTOR_DISPATCH_RAN;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0))
        return gated_hurt_frame(image, actor, WB_ACTOR_TYPE26_HURT_LISTS);

    switch (monster_contact(image, actor)) {
    case MONSTER_TOUCHED_FOLLOWED:
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_STRUCK:
    case MONSTER_STRUCK_BY_POINT:
        monster_enter_hit_animation(image, actor);
        actor_set_side_flag(image, actor);
        actor_damage_template_hitpoints(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    case MONSTER_UNTOUCHED:
        break;
    }

    actor_fall_and_settle(image, actor, followed_sprite_left_in_d7(image));
    actor_hop_ascend_step(image, actor);
    actor_face_and_step_toward(image, actor, WB_ACTOR_TYPE26_STEP);
    actor_tick_timer30(image, actor);

    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT)) {
        actor_anim_step_facing_list(image, actor, WB_ACTOR_TYPE26_STILL_LISTS);
        return WB_ACTOR_DISPATCH_RAN;
    }
    type26_drop_shot(image, actor);
    actor_anim_step_facing_list(image, actor, WB_ACTOR_TYPE26_MOVING_LISTS);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- slot 38 ($5408) and the PICKUP TIER behind it (batch 38) -------------------------------------
 *
 * A COLLECTABLE WHOSE PAYOUT IS A TABLE LOOKUP, and what is new is that a collected record reads
 * its OWN KIND ROW out of WB_ACTOR_KIND_TABLE and pays what the row says — a packed-BCD score
 * longword and an index into a second dispatch table.
 *
 * WHAT IT SHARES WITH SLOT 31 IS FOUR INSTRUCTIONS, not a frame. The shorthand this comment used to
 * carry claimed the whole waiting arm was that handler's byte for byte, which is the tier's
 * recurring over-claim; what the two really have in common is
 * `bsr $1334`, `bsr $501a`, the `btst #0,8(a0)` gate and `bsr $5c6e / btst #1,d0`. Past
 * those four the two part on everything. Slot 31 compares WB_ACTOR_FIELD_12 as a WORD at the TOP of
 * its frame (`cmpi.w #$14` starting the flicker) and frees itself on the single expiry of a WORD
 * countdown; this handler has no such compare at all, counts the same field as a BYTE, expires
 * TWICE — the second expiry leaving for actor_defeat_and_score rather than writing a free marker —
 * and adds three splits slot 31 does not have: the kind compare on the waiting arm, the
 * WB_STATE_FLAG_A32 gate under it, and the kind-byte test that chooses between the relaunch and the
 * sprite. The BYTE double expiry is slot 28's shape, not slot 31's.
 *
 * THE ROW INDEX IS BOUNDED HERE AND NOT AT THE TIER'S OTHER READER. `actor_respawn_as_new_kind`
 * bounds its kind at neither end; this site's `cmpi.b #$2,20(a0) / bge` is SIGNED, so the kind arm
 * runs only for 2..127 and the read lands within 2032 bytes of the table — inside the image at both
 * ends, and never past the 22 shipped rows by more than the pickup table and its own handlers.
 */

/* $6938 — the score arm's digits. `swap d0` puts nibble 4 of the addend in the low position and
 * `rol.l #4` walks down to nibble 0, so WHAT IS DRAWN IS THE LOW FIVE DIGITS and anything above
 * them is invisible however large the addend is.
 *
 * THE TWO LOOPS ARE NOT ONE LOOP WITH A FLAG, and the difference is the counter. The blanking loop
 * ($6944) writes a space and decrements WITHOUT testing, so it is bounded only by finding a nonzero
 * nibble — an addend of ZERO never leaves it. The digit loop ($695e) tests AFTER decrementing, so
 * entering it with the counter already at zero wraps to $ffff and writes 65,536 more characters.
 * Both are reachable only through an addend the one caller cannot produce: it `beq`s on zero, and
 * five leading zero nibbles need the low 20 bits clear with something above them, which no shipped
 * kind row has. Reproduced as it stands; ../STATUS.md carries both as unreachable rather than
 * pinned.
 */
void text_post_bonus_points_a4be(uint8_t *image, uint32_t entry_d0) {
    /* `swap d0` — a rotate by half a longword, which is what brings nibble 4 down. */
    uint32_t digits = rotate_left32(entry_d0, 16);
    uint32_t at = WB_TEXT_BONUS_DIGITS;
    uint16_t left = WB_TEXT_BONUS_DIGIT_COUNT;

    /* `move.l d0,d1 / andi.l #$f,d1 / tst.w d1 / bne` — the mask is a LONGWORD one and the test a
     * word one, which agree because the mask leaves nothing above bit 3. */
    while ((digits & WB_BCD_DIGIT_MASK) == 0) {
        bus_write_byte(image, at, WB_TEXT_DIGIT_BLANK);
        at = addr_add(at, 1);
        left--;
        digits = rotate_left32(digits, WB_BCD_DIGIT_BITS);
    }

    for (;;) {
        bus_write_byte(image, at,
                       (uint8_t)((digits & WB_BCD_DIGIT_MASK) + WB_TEXT_DIGIT_ZERO));
        at = addr_add(at, 1);
        /* `subi.w #1,d7 / beq` — the decrement is a WORD one and the branch reads its flags, so a
         * counter that started at zero goes to $ffff and does not stop here. */
        if (--left == 0)
            break;
        digits = rotate_left32(digits, WB_BCD_DIGIT_BITS);
    }

    image[WB_TEXT_REQUEST] = WB_TEXT_MESSAGE_BONUS_POINTS;
    wr16(image + WB_TEXT_LIFETIME_REQUEST, WB_TEXT_LIFETIME_DEFAULT);
}

/* $5476..$54a5 — the kind row's own payout, and the second dispatch under it.
 *
 * THE REFUSAL IS A CODE AND NOT AN ADDRESS, which is where this differs from slot 7's state `jsr`
 * even though the two instructions are the same shape. Slot 7's four entries are real code and the
 * span around them holds zeros, so that one reports the address and lets `actor_behavior_type07`
 * decide; here every legal entry is one of fourteen known addresses, so the answer is which of them
 * ran, and "none of them" is a value that must not collide with any of them. behavior.h's
 * WB_ACTOR_DISPATCH_PICKUP_REFUSED is that value and test_behavior.py checks the image's own
 * fourteen longwords against it.
 *
 * `add.w d0,d0` twice is a SIXTEEN-BIT scale and `0(a1,d0.w)` then sign-extends, so the index
 * aliases in exactly `actor_dispatch_behavior`'s way: entry `s` is reached by `s`, `s + $4000`,
 * `s + $8000` and `s + $c000`. */
static int run_pickup_effect(uint8_t *image, uint16_t index) {
    uint16_t offset = (uint16_t)(index * WB_PICKUP_EFFECT_ENTRY);
    uint32_t target = bus_read_long(image,
                                    addr_add(WB_PICKUP_EFFECT_TABLE, sign_ext16(offset)));

    switch (target) {
    case WB_PICKUP_EFFECT_NONE:        pickup_effect_none(image); break;
    case WB_PICKUP_EFFECT_BBC4:        pickup_effect_grant_bbc4(image); break;
    case WB_PICKUP_EFFECT_WING_BOOTS:  pickup_effect_grant_wing_boots(image); break;
    case WB_PICKUP_EFFECT_HELMET:      pickup_effect_grant_helmet(image); break;
    case WB_PICKUP_EFFECT_GAUNTLET:    pickup_effect_grant_gauntlet(image); break;
    case WB_PICKUP_EFFECT_REVIVAL:     pickup_effect_grant_revival(image); break;
    case WB_PICKUP_EFFECT_FIRE_BALLS:  pickup_effect_grant_fire_balls(image); break;
    case WB_PICKUP_EFFECT_BOMBS:       pickup_effect_grant_bombs(image); break;
    case WB_PICKUP_EFFECT_WIND_SPOUTS: pickup_effect_grant_wind_spouts(image); break;
    case WB_PICKUP_EFFECT_LIGHTNING:   pickup_effect_grant_lightning(image); break;
    case WB_PICKUP_EFFECT_REFILL:      pickup_effect_refill_meter(image); break;
    case WB_PICKUP_EFFECT_ADD4:        pickup_effect_add4_meter(image); break;
    case WB_PICKUP_EFFECT_ATTACK:      pickup_effect_bump_attack_level(image); break;
    case WB_PICKUP_EFFECT_VANISH:      pickup_effect_vanish_followed(image); break;
    default:
        return 0;
    }
    return 1;
}

static int type38_pay_for_kind(uint8_t *image, uint32_t actor) {
    /* `moveq #$0,d0 / move.b 20(a0),d0 / lsl.l #4,d0` — the byte is zero-extended before the shift,
     * so the offset is 0..$ff0 and `0(a1,d0.w)` sign-extends a positive word. */
    uint32_t row = addr_add(WB_ACTOR_KIND_TABLE,
                            (uint16_t)(field_b(image, actor, WB_ACTOR_KIND)
                                       * WB_ACTOR_KIND_RECORD_BYTES));
    uint32_t score = bus_read_long(image, addr_add(row, WB_ACTOR_KIND_SCORE));

    if (score != 0) {
        /* THE ENTRY X IS ZERO BY CONSTRUCTION, and the writer is the shift: `lsl.l #4,d0` leaves X
         * the last bit shifted out, which is bit 28 of a zero-extended BYTE and therefore always 0.
         * `lea`, `move.l` and `beq` between it and the `bsr` leave X alone. hud.h's audit block is
         * the single place that COUNTS the proved sites; this comment states the proof and does not
         * number it, because two counters drift. */
        bcd_add_score_bd70(image, score, WB_BCD_ENTRY_EXTEND_CLEAR);
        text_post_bonus_points_a4be(image, score);
    }
    return run_pickup_effect(image, bus_read_word(image,
                                                  addr_add(row, WB_ACTOR_KIND_PICKUP_EFFECT)));
}

/* $54aa..$54f2 — the waiting arm, which a MOVING record reaches too (the `btst #0,8(a0)` at $5410
 * jumps straight here, so a record mid-hop still ages).
 *
 * IT SPLITS ON THE SAME KIND COMPARE the collect arm does, and the two halves have nothing in
 * common: a pickup kind whose byte is at or above WB_ACTOR_PICKUP_KIND_FIRST is given
 * WB_ACTOR_TYPE38_FLASH frames while WB_STATE_FLAG_A32 is nonzero and left alone otherwise, and a
 * gold one either relaunches (kind byte zero) or publishes a sprite. */
static void type38_wait(uint8_t *image, uint32_t actor) {
    if ((int8_t)field_b(image, actor, WB_ACTOR_KIND) >= (int8_t)WB_ACTOR_PICKUP_KIND_FIRST) {
        if (be16(image + WB_STATE_FLAG_A32) != 0)
            set_field_b(image, actor, WB_ACTOR_FIELD_12, WB_ACTOR_TYPE38_FLASH);
        return;
    }
    if (field_b(image, actor, WB_ACTOR_KIND) == 0)
        actor_relaunch_and_anim_5160(image, actor);
    else
        actor_select_sprite_by_flag(image, actor);
}

uint32_t actor_behavior_type38_pickup(uint8_t *image, uint32_t actor) {
    uint8_t left;
    int was_flickering;

    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    actor_hop_ascend_step(image, actor);

    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT)
        && followed_stood_on_it(image, actor)) {
        /* NOT `sound_request_9`, and the difference is a fact about the image rather than a style:
         * this handler SPELLS that routine's four instructions inline with a `jsr 56(a1)` where
         * $6786 has a `jmp`, so it is not one of that routine's five `bsr` callers and its plate's
         * caller list stays correct. What the two leave in memory is identical — the tail jump
         * makes the call equivalent — so only the census would have known. */
        snd_call_trigger_effect(image, WB_ACTOR_REQUEST9_SFX, WB_SND_CHANNEL_A);
        /* `cmpi.b #$2,20(a0)` is a SECOND read of the byte `move.b 20(a0),d0` has already taken,
         * and the port re-reads it too: bus.h answers a refused field 0 for both, so the two
         * spellings agree, and the original's is what is being ported. */
        if ((int8_t)field_b(image, actor, WB_ACTOR_KIND) < (int8_t)WB_ACTOR_PICKUP_KIND_FIRST)
            pay_gold_award(image, be16(image + WB_STAGE_NUMBER));
        else if (!type38_pay_for_kind(image, actor))
            return WB_ACTOR_DISPATCH_PICKUP_REFUSED;

        actor_defeat_and_score(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }

    type38_wait(image, actor);

    /* `subq.b #1,12(a0) / bne` then `bset #6,8(a0) / bne` — slot 28's double expiry exactly: the
     * branch reads the bit the `bset` has just overwritten, so the first expiry raises the flicker
     * and reloads the byte and the second leaves for `actor_defeat_and_score`. */
    left = (uint8_t)(field_b(image, actor, WB_ACTOR_FIELD_12) - 1);
    set_field_b(image, actor, WB_ACTOR_FIELD_12, left);
    if (left != 0)
        return WB_ACTOR_DISPATCH_RAN;

    was_flickering = flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT);
    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT);
    if (was_flickering) {
        actor_defeat_and_score(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }
    set_field_b(image, actor, WB_ACTOR_FIELD_12, WB_ACTOR_TYPE38_FIELD_12_RELOAD);
    return WB_ACTOR_DISPATCH_RAN;
}


/* --- batch 39: slots 39..46 and 57 — THE TIER'S OWN AMMUNITION -----------------------------------
 *
 * The last nine non-player rows, and every one of them is the record an already-reconstructed
 * handler spawns — one parent each, and NOT all of what the tier spawns (slots 51, 52 and 53 are
 * spawned rows too, ported three batches earlier). behavior.h carries both halves. All nine are
 * CLEAN.
 *
 * They share the $5a band's grammar and not the monster family's: no spawn gate, no player-shot
 * scan, and a contact test that reads only bits 0 and 1 of `actor_followed_overlap_mask`.
 */

/* $5534 — the tail slots 39 and 41 share. Slot 41 reaches it by `bra.w`/`beq.w` from its own body
 * and slot 39 by the same two branches from its; the whole-image census finds those four sites and
 * no other reference to the address.
 *
 * WHAT ENDS THE DRIFT is either mark: a record STRUCK this frame or earlier (WB_ACTOR_FIELD_30
 * nonzero — the struck arm `st`s it) or one that has LANDED. Only an untouched airborne record
 * drifts, and a blocked probe turns it round rather than stopping it. */
static void shatterer_move_or_break(uint8_t *image, uint32_t actor) {
    if (field_b(image, actor, WB_ACTOR_FIELD_30) != 0
        || flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT)) {
        /* THE INDEX IS THE RAW RECORD BYTE — `move.w $5598(pc,d0.w),6(a0)` runs before the
         * `andi.b`, which bounds only where the cursor GOES (batch 35's correction). */
        publish_frame(image, actor, WB_ACTOR_TYPE39_FRAMES,
                      field_b(image, actor, WB_ACTOR_FIELD_18));
        if (step_cursor_in_memory(image, actor, WB_ACTOR_FIELD_18, WB_ACTOR_ANIM16_MASK) == 0)
            set_field_w(image, actor, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
        return;
    }
    if (step_was_blocked(step_facing(image, actor, WB_ACTOR_TYPE39_STEP)))
        flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
}

/* $54f4 and $563c — one body with the sprite id as its parameter, because that id is the only thing
 * that differs between the two handlers' 64 opening bytes.
 *
 * THE STRIKE ARM DOES NOT END THE FRAME. It turns the record round, stuns, and falls into the tail
 * above — where the BODY arm returns, having latched WB_ACTOR_FIELD_30 so that every later frame
 * plays the break-up. */
static uint32_t shatterer_frame(uint8_t *image, uint32_t actor, uint16_t sprite) {
    uint32_t overlap;

    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    actor_hop_ascend_step(image, actor);
    set_field_w(image, actor, WB_ACTOR_SPRITE, sprite);
    overlap = actor_followed_overlap_mask(image, actor);

    if (overlap & (1u << WB_ACTOR_OVERLAP_STRIKE_BIT)) {
        flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
        actor_stun_followed(image);
    } else if (overlap & (1u << WB_ACTOR_OVERLAP_BODY_BIT)) {
        set_field_b(image, actor, WB_ACTOR_TEMPLATE_SLOT, WB_ACTOR_CONTACT_DAMAGE_INLINE);
        actor_damage_followed(image, actor);
        set_field_b(image, actor, WB_ACTOR_FIELD_30, WB_ACTOR_ST_BYTE);
        return WB_ACTOR_DISPATCH_RAN;
    }
    shatterer_move_or_break(image, actor);
    return WB_ACTOR_DISPATCH_RAN;
}

uint32_t actor_behavior_type39(uint8_t *image, uint32_t actor) {
    return shatterer_frame(image, actor, WB_ACTOR_TYPE39_SPRITE);
}

uint32_t actor_behavior_type41(uint8_t *image, uint32_t actor) {
    return shatterer_frame(image, actor, WB_ACTOR_TYPE41_SPRITE);
}

/* $55a8 and $572a — slot 51's shape with a sprite per arm: walk while the mode bit is down, and the
 * frame a probe refuses raise it and hand the record to the fall that frees it on landing.
 *
 * `btst #3,8(a0)` picks the sprite AND the probe in one test, and nothing here turns the record —
 * so the frame published is always the one for the side the record already faced. Slot 43 spells
 * the same id in both arms, which is why the two are one call with two parameters rather than a
 * facing lookup. */
static uint32_t walker_dies_where_it_stops(uint8_t *image, uint32_t actor, uint16_t left_sprite,
                                           uint16_t right_sprite, uint32_t step) {
    uint32_t outcome;

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        fall_until_supported_then_free(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }
    if (switched_contact_took_the_frame(image, actor, CONTACT_LATCHES_COUNTDOWN))
        return WB_ACTOR_DISPATCH_RAN;

    if (faces_left(image, actor)) {
        set_field_w(image, actor, WB_ACTOR_SPRITE, left_sprite);
        outcome = step_left(image, actor, step);
    } else {
        set_field_w(image, actor, WB_ACTOR_SPRITE, right_sprite);
        outcome = step_right(image, actor, step);
    }
    if (step_was_blocked(outcome))
        flag_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
    return WB_ACTOR_DISPATCH_RAN;
}

uint32_t actor_behavior_type40(uint8_t *image, uint32_t actor) {
    return walker_dies_where_it_stops(image, actor, WB_ACTOR_TYPE40_SPRITE_LEFT,
                                      WB_ACTOR_TYPE40_SPRITE_RIGHT, WB_ACTOR_TYPE40_STEP);
}

uint32_t actor_behavior_type43(uint8_t *image, uint32_t actor) {
    return walker_dies_where_it_stops(image, actor, WB_ACTOR_TYPE43_SPRITE,
                                      WB_ACTOR_TYPE43_SPRITE, WB_ACTOR_TYPE43_STEP);
}

/* $56f0, $5824 and $58c4 — the break-up slots 42, 44 and 45 spend their last frames in, and the
 * REGISTER spelling of the shatterers' cursor step: `addi.b #2,d0 / andi.b #$f,d0 / move.b d0,18(a0)`
 * commits once where $5588 writes the field twice. On the wrap the slot is given back AND the mode
 * bit lowered, which is the instruction slots 39 and 41 do not have. */
static void break_up_then_free(uint8_t *image, uint32_t actor, uint32_t frames) {
    if (publish_and_store_cursor(image, actor, frames, WB_ACTOR_ANIM16_MASK) != 0)
        return;
    set_field_w(image, actor, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
    flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
}

/* $567c — the walker that BREAKS UP instead of falling, and the only handler in this batch whose
 * strike arm neither ends the frame nor is a tail jump: it turns the record, stuns, raises the mode
 * bit and then RUNS THE WALK ANYWAY, so a striking type-42 record takes one more step before its
 * next frame becomes the break-up. Its body arm returns without raising anything, so a record that
 * merely touches the followed one goes on walking. */
uint32_t actor_behavior_type42(uint8_t *image, uint32_t actor) {
    uint32_t overlap;

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        break_up_then_free(image, actor, WB_ACTOR_TYPE42_FRAMES);
        return WB_ACTOR_DISPATCH_RAN;
    }

    overlap = actor_followed_overlap_mask(image, actor);
    if (overlap & (1u << WB_ACTOR_OVERLAP_STRIKE_BIT)) {
        flag_flip(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
        actor_stun_followed(image);
        flag_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
    } else if (overlap & (1u << WB_ACTOR_OVERLAP_BODY_BIT)) {
        set_field_b(image, actor, WB_ACTOR_TEMPLATE_SLOT, WB_ACTOR_CONTACT_DAMAGE_INLINE);
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }

    actor_fall_and_settle(image, actor, SETTLE_SPAN_UNREAD);
    actor_hop_ascend_step(image, actor);
    set_field_w(image, actor, WB_ACTOR_SPRITE, WB_ACTOR_TYPE42_SPRITE);
    if (step_was_blocked(step_facing(image, actor, WB_ACTOR_TYPE42_STEP)))
        flag_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
    return WB_ACTOR_DISPATCH_RAN;
}

/* $57be — slot 21's aimed shot, in flight. `actor_aim_velocity` gave its spawner a SIGNED BYTE PAIR
 * and the spawner stamped it into WB_ACTOR_FIELD_30/_31; this handler spends it every frame with
 * `ext.w` on each byte, so both are signed — and the y one is SUBTRACTED, so a positive
 * WB_ACTOR_FIELD_31 carries the shot UP.
 *
 * Its life is WB_ACTOR_FIELD_29, the one countdown in this file that is not WB_ACTOR_FIELD_30, and
 * it is spent WB_ACTOR_TYPE44_LIFE_STEP at a time. */
uint32_t actor_behavior_type44(uint8_t *image, uint32_t actor) {
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        break_up_then_free(image, actor, WB_ACTOR_TYPE39_FRAMES);
        return WB_ACTOR_DISPATCH_RAN;
    }
    if (switched_contact_took_the_frame(image, actor, CONTACT_NO_LATCH))
        return WB_ACTOR_DISPATCH_RAN;

    set_field_w(image, actor, WB_ACTOR_SPRITE, WB_ACTOR_TYPE44_SPRITE);
    set_field_w(image, actor, WB_ACTOR_X,
                (uint16_t)(field_w(image, actor, WB_ACTOR_X)
                           + (int8_t)field_b(image, actor, WB_ACTOR_FIELD_30)));
    set_field_w(image, actor, WB_ACTOR_Y,
                (uint16_t)(field_w(image, actor, WB_ACTOR_Y)
                           - (int8_t)field_b(image, actor, WB_ACTOR_FIELD_31)));
    if (tick_countdown(image, actor, WB_ACTOR_FIELD_29, WB_ACTOR_TYPE44_LIFE_STEP) == 0)
        flag_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
    return WB_ACTOR_DISPATCH_RAN;
}

/* $5852 — slot 14's escort, and the tier's one HOMING record: it does not carry a velocity at all
 * but asks `actor_aim_velocity` for a fresh one every frame, from where it is to where the followed
 * record is, out of WB_ACTOR_TYPE45_AIM_ROW. That makes this the aim table's SECOND caller, and the
 * two are the whole census of it.
 *
 * The two stores re-read the record's own words after the call, which is what the original does —
 * `move.w (a0),d0` before the `jsr` and `add.w d0,(a0)` after it — and the aim table writes no
 * memory, so the two readings can only differ if the record moved, which nothing here does. */
uint32_t actor_behavior_type45(uint8_t *image, uint32_t actor) {
    uint32_t followed;
    int16_t dx, dy;

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        break_up_then_free(image, actor, WB_ACTOR_TYPE39_FRAMES);
        return WB_ACTOR_DISPATCH_RAN;
    }
    if (switched_contact_took_the_frame(image, actor, CONTACT_NO_LATCH))
        return WB_ACTOR_DISPATCH_RAN;

    set_field_w(image, actor, WB_ACTOR_SPRITE, WB_ACTOR_TYPE45_SPRITE);
    followed = followed_actor_record(image);
    actor_aim_velocity(image, (uint16_t)field_w(image, actor, WB_ACTOR_X),
                       (uint16_t)field_w(image, actor, WB_ACTOR_Y),
                       (uint16_t)field_w(image, followed, WB_ACTOR_X),
                       (uint16_t)field_w(image, followed, WB_ACTOR_Y),
                       WB_ACTOR_TYPE45_AIM_ROW, &dx, &dy);
    set_field_w(image, actor, WB_ACTOR_X, (uint16_t)(field_w(image, actor, WB_ACTOR_X) + dx));
    set_field_w(image, actor, WB_ACTOR_Y, (uint16_t)(field_w(image, actor, WB_ACTOR_Y) - dy));
    if (tick_countdown30(image, actor) == 0)
        flag_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
    return WB_ACTOR_DISPATCH_RAN;
}

/* $58f2 — slot 23's stolen gold, floating away. FIFTY-FOUR BYTES and the shortest live handler in
 * the table after slot 8's six: no contact test, no map, no flags — the animation step
 * `actor_relaunch_and_anim_5160` shares, one countdown, and a rise.
 *
 * THE COUNTDOWN AND THE RISE ARE EXCLUSIVE. `subq.b #1,30(a0) / beq` frees the slot on the frame
 * the byte reaches zero and the `subq.w #4,2(a0)` sits on the OTHER arm, so the last frame of a
 * type-46 record's life publishes a frame and does not move. */
uint32_t actor_behavior_type46(uint8_t *image, uint32_t actor) {
    anim_5160_publish_and_step(image, actor);
    if (tick_countdown30(image, actor) == 0) {
        set_field_w(image, actor, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
        return WB_ACTOR_DISPATCH_RAN;
    }
    set_field_w(image, actor, WB_ACTOR_Y,
                (uint16_t)(field_w(image, actor, WB_ACTOR_Y) - WB_ACTOR_TYPE46_RISE));
    return WB_ACTOR_DISPATCH_RAN;
}

/* $7260 — slot 7's burst shot, and the only handler in this batch whose velocity is a WORD pair:
 * AND THE ONLY ONE THAT PUBLISHES NO SPRITE AT ALL. There is no `move.w #id,6(a0)` anywhere in
 * these 98 bytes, so a type-57 record wears whatever its spawner stamped —
 * WB_ACTOR_TYPE07_BURST_SPRITE for a burst shot and WB_ACTOR_TYPE07_DROP_SPRITE for a dropped
 * one — for its whole life.
 * `type07_fill_shot`'s caller copies one WB_ACTOR_TYPE07_BURST_* longword straight into
 * WB_ACTOR_FIELD_24, so 24(a0) is dx and 26(a0) is dy — and BOTH are ADDED, where slot 44 subtracts
 * its y.
 *
 * ITS BODY-CONTACT ARM IS A TAIL JUMP (`bne.w $69fe`), so the damage call is the last thing the
 * frame does and nothing is latched behind it: a type-57 record can damage the followed one on
 * every frame it overlaps.
 *
 * THE DEATH ARM CLEARS EIGHT BYTES WITH TWO `clr.l`s, covering WB_ACTOR_FIELD_22 through
 * WB_ACTOR_FIELD_28 + 1. That is NOT "the swoop's block": the swoop machine's own state is
 * WB_ACTOR_FIELD_22 (the state byte), WB_ACTOR_FIELD_24 (the path cursor) and WB_ACTOR_FIELD_26
 * (the launch y) — offsets 22..27 — and the last word, WB_ACTOR_FIELD_28, is this handler's OWN
 * frame count, which nothing else in the tier reads. So the clears are the swoop's 22..27 plus
 * slot 57's own 28..29. They go through `bus_write_long` and not four word writes because the shim
 * bounds the WHOLE operand: a longword straddling the image's top is dropped entirely on both
 * sides. */
uint32_t actor_behavior_type57(uint8_t *image, uint32_t actor) {
    uint32_t overlap;

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)) {
        bus_write_long(image, addr_add(actor, WB_ACTOR_FIELD_22), 0);
        bus_write_long(image, addr_add(actor, WB_ACTOR_FIELD_26), 0);
        set_field_w(image, actor, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
        flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
        return WB_ACTOR_DISPATCH_RAN;
    }

    overlap = actor_followed_overlap_mask(image, actor);
    if (overlap & (1u << WB_ACTOR_OVERLAP_STRIKE_BIT)) {
        flag_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
        actor_stun_followed(image);
        return WB_ACTOR_DISPATCH_RAN;
    }
    if (overlap & (1u << WB_ACTOR_OVERLAP_BODY_BIT)) {
        actor_damage_followed(image, actor);
        return WB_ACTOR_DISPATCH_RAN;
    }

    set_field_w(image, actor, WB_ACTOR_X,
                (uint16_t)(field_w(image, actor, WB_ACTOR_X)
                           + (uint16_t)field_w(image, actor, WB_ACTOR_FIELD_24)));
    set_field_w(image, actor, WB_ACTOR_Y,
                (uint16_t)(field_w(image, actor, WB_ACTOR_Y)
                           + (uint16_t)field_w(image, actor, WB_ACTOR_FIELD_26)));

    /* `addq.w #1,28(a0)` and then `cmpi.w #$28,28(a0)`, which RE-READS the word the step just
     * wrote — so a record at an address bus.h refuses compares 0 against the limit rather than the
     * value it computed. */
    set_field_w(image, actor, WB_ACTOR_FIELD_28,
                (uint16_t)(field_w(image, actor, WB_ACTOR_FIELD_28) + 1));
    if ((uint16_t)field_w(image, actor, WB_ACTOR_FIELD_28) == WB_ACTOR_TYPE57_LIFETIME) {
        set_field_w(image, actor, WB_ACTOR_FIELD_28, 0);
        set_field_w(image, actor, WB_ACTOR_X, WB_ACTOR_FREE_MARKER);
    }
    return WB_ACTOR_DISPATCH_RAN;
}
