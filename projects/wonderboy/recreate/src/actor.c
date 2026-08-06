/* actor.c — the followed actor's record ($67e0), the two tests above it ($67c2, $67f8), the two
 * passes that project actor records into screen coordinates ($8dfe, $8e66), and the table's own
 * LIFECYCLE: reset ($1f36), free ($df9e), allocate ($1b68, $1b8e), spawn ($ffe4) and the two
 * routines that move a record between standing and falling ($2af2, $14d6).
 *
 * WHAT TIES THE FIVE TOGETHER. The game's moving objects live in three parallel tables of
 * WB_ACTOR_SCREEN_RECORD_COUNT records; two mode flags pick one, and slot WB_ACTOR_FOLLOWED_SLOT of
 * it is the actor everything else is measured against — which way an enemy faces ($67c2), whether
 * it is close enough to act ($67f8), and where the background scroll should be looking ($8dfe,
 * whose destination is the WB_SCROLL_FOLLOW_X the queue already reads). $67e0 is the one routine
 * that names that record, and the other four are its callers.
 *
 * THE TWO FLAGS ARE READ TWO DIFFERENT WAYS, and the reconstruction keeps both. $67e0 tests
 * WB_STATE_FLAG_A32 with `bne` (nonzero) while $8e66 tests the same word with `bpl` (negative), and
 * ../names.txt records that the image only ever writes it $0000 or $ffff — so the two agree on
 * every value the GAME can produce and part company on a small positive one, which is a case in
 * test/test_actor.py rather than a comment here.
 *
 * $67e0 HAS NO A30 FORM, which is why $8dfe is gated. In the A30 mode $8e66 projects
 * WB_ACTOR_TABLE_A30, whose slot 12 is an address $67e0 never returns; $8dfe's `tst.w / bpl / rts`
 * is what stops it refreshing that slot from the wrong table.
 *
 * EVERY COMPARISON HERE IS A SIGNED 16-BIT ONE OF THE OPERANDS, not a test of the wrapped
 * difference: `cmp.w` + `ble`/`bgt`/`blt` read N xor V (docs/m68k-disassembly.md). $67f8's ADD is
 * the exception — `add.w d0,d1` really does wrap into the value the following compare reads, and
 * the (int16_t) casts below reproduce that.
 *
 * WHAT THE DIFFERENTIAL CANNOT SEE, registered in ../STATUS.md: the registers the two projections
 * leave behind. Both walk out with a0 one record on and a1 one screen record on, and their one
 * caller (game_main_loop) reloads everything before its next call, so the C returns neither —
 * test/test_actor.py asserts the ORACLE's against a model instead. The lifecycle routines below
 * are the same family: only the two allocators have a result worth returning (their a1), and the
 * rest walk out with a cursor nothing reads.
 *
 * AND THE PASS THAT DRIVES ALL OF IT is $ff42: the once-a-frame spawn driver, its hit-point seeder
 * ($1006a), and the three routines that turn a map step's two result registers into a flag flip, a
 * hop or a launch ($2b5a, $2b82, $2b8e).
 *
 * AT THE BOTTOM, THE TWO DAMAGE PATHS ($69fe, $6b46) — where a hit is actually paid for, and the
 * only routines in this file that call out of the actor tier at all (into src/sound.c).
 *
 * WHAT THE LIFECYCLE TURNS OUT TO BE. A table is nineteen records; `actor_table_reset` marks every
 * one of them free, `actor_slots_mark_free` marks a RUN of them free again, and the two allocators
 * hand back the first free record of one of two POOLS — WB_ACTOR_ALLOC_LOW_FIRST..+LOW_SLOTS and
 * WB_ACTOR_ALLOC_HIGH_FIRST..+HIGH_SLOTS, which meet either side of WB_ACTOR_FOLLOWED_SLOT and so
 * can never hand out the followed actor's own slot. `actor_spawn_from_template` then fills the slot
 * in from a 32-byte template. The two allocators are BYTE-IDENTICAL apart from their first slot and
 * their count, so they are one function here — test/test_actor.py asserts that, for batch 7's
 * reason: a pattern that was wrong in the same way twice would pass two pins built from it.
 */
#include <stdint.h>

#include "actor.h"
#include "machine.h"
#include "sound.h"
#include "wonderboy.h"

uint32_t followed_actor_record(const uint8_t *image) {
    if (be16(image + WB_STATE_FLAG_A32) != 0)
        return WB_ACTOR_FOLLOWED_A32;
    return WB_ACTOR_FOLLOWED_DEFAULT;
}

static int16_t actor_x(const uint8_t *image, uint32_t record) {
    return (int16_t)be16(image + addr_add(record, WB_ACTOR_X));
}

void actor_set_side_flag(uint8_t *image, uint32_t actor) {
    const uint8_t side = (uint8_t)(1u << WB_ACTOR_FLAG_SIDE_BIT);
    uint8_t *flags = image + addr_add(actor, WB_ACTOR_FLAGS);

    /* `cmp.w d0,d1 / ble` on (followed.x, actor.x): the bit is raised only where the actor is
     * STRICTLY to the right of the followed one, i.e. where the followed one is to its left. */
    if (actor_x(image, actor) > actor_x(image, followed_actor_record(image)))
        *flags |= side;
    else
        *flags &= (uint8_t)~side;
}

uint32_t actor_followed_x_within(const uint8_t *image, uint32_t actor, uint32_t reach) {
    int16_t here = actor_x(image, actor);
    int16_t followed = actor_x(image, followed_actor_record(image));
    int outside;

    /* The reach is added to whichever of the two is BEHIND — the original picks the arm with
     * `cmp.w d1,d2 / bgt` and adds `d0` to the loser — and the sum is a 16-bit one the following
     * compare reads as it lands, wrap and all. */
    if (followed > here)
        outside = followed > (int16_t)(here + (uint16_t)reach);
    else
        outside = (int16_t)(followed + (uint16_t)reach) < here;

    return set_low_word(reach, outside ? WB_ACTOR_OUT_OF_REACH : 0);
}

/* The eleven instructions $8dfe and $8e66 spell identically: one actor record into one screen
 * record. The two scroll words are arguments because $8e66 reads them ONCE, above its loop. */
static void project_actor(uint8_t *image, uint32_t record, uint32_t screen,
                          uint16_t scroll_x, uint16_t scroll_y) {
    uint16_t x = (uint16_t)(be16(image + addr_add(record, WB_ACTOR_X))
                            - WB_ACTOR_SCREEN_X_BIAS - scroll_x);
    wr16(image + addr_add(screen, WB_ACTOR_SCREEN_X), x);

    uint16_t y = (uint16_t)(be16(image + addr_add(record, WB_ACTOR_Y))
                            - WB_ACTOR_SCREEN_Y_BIAS - scroll_y);
    wr16(image + addr_add(screen, WB_ACTOR_SCREEN_Y), y);

    /* `btst #6,8(a0) / beq` then `tst.w $712.w / beq`: the sprite is withheld only when the record
     * asks to flicker AND this is one of the frames the toggle is nonzero on. */
    int flickering = (image[addr_add(record, WB_ACTOR_FLAGS)] & (1u << WB_ACTOR_FLAG_FLICKER_BIT))
                     && be16(image + WB_FRAME_TOGGLE) != 0;
    wr16(image + addr_add(screen, WB_ACTOR_SCREEN_SPRITE),
         flickering ? WB_ACTOR_SPRITE_HIDDEN
                    : be16(image + addr_add(record, WB_ACTOR_SPRITE)));
}

void project_followed_actor(uint8_t *image) {
    /* `tst.w $a30.w / bpl`: `bpl` reads N alone, so this is the word's own sign and not a
     * comparison (docs/m68k-disassembly.md). */
    if ((int16_t)be16(image + WB_STATE_FLAG_A30) < 0)
        return;

    project_actor(image, followed_actor_record(image), WB_SCROLL_FOLLOW_X,
                  be16(image + WB_BG_SCROLL_POS_X), be16(image + WB_BG_SCROLL_POS_Y));
}

/* Which of the three tables the two mode flags name. Both tests are `bpl` on the word's own sign. */
static uint32_t selected_actor_table(const uint8_t *image) {
    if ((int16_t)be16(image + WB_STATE_FLAG_A30) < 0)
        return WB_ACTOR_TABLE_A30;
    if ((int16_t)be16(image + WB_STATE_FLAG_A32) < 0)
        return WB_ACTOR_TABLE_A32;
    return WB_ACTOR_TABLE_DEFAULT;
}

void project_actor_list(uint8_t *image) {
    wr32(image + WB_ACTOR_TABLE_SELECTED, selected_actor_table(image));

    /* The original re-READS the longword it just published (`movea.l $a098.l,a0`), so a caller
     * that had left something else there gets no say and the two are always the same table. */
    uint32_t record = be32(image + WB_ACTOR_TABLE_SELECTED);
    uint32_t screen = WB_ACTOR_SCREEN_RECORDS;
    uint16_t scroll_x = be16(image + WB_BG_SCROLL_POS_X);
    uint16_t scroll_y = be16(image + WB_BG_SCROLL_POS_Y);

    /* `cmpa.l #$995e,a1 / bne` closes the loop, so it is a do/while on the DESTINATION cursor. */
    do {
        project_actor(image, record, screen, scroll_x, scroll_y);
        record = addr_add(record, WB_ACTOR_RECORD_BYTES);
        screen = addr_add(screen, WB_ACTOR_SCREEN_RECORD_BYTES);
    } while (screen != WB_ACTOR_SCREEN_RECORDS_END);
}

/* --- the table's lifecycle ---------------------------------------------------------------------
 *
 * A `dbf Dn` runs its body Dn + 1 times and leaves Dn at $ffff, so every count below is spelt as
 * the original's own operand and the loop as a do/while: `remaining-- != 0` is exactly the
 * decrement-and-test the instruction does, wrap included.
 */

void actor_table_reset(uint8_t *image, uint32_t table) {
    uint32_t record = table;
    uint16_t remaining = WB_ACTOR_SCREEN_RECORD_COUNT - 1;      /* `move.w #$12,d0` */

    do {
        /* `move.l #$ffbe0000,(a0)+` then seven `clr.l (a0)+`: the marker sits in WB_ACTOR_X and the
         * rest of the record — WB_ACTOR_Y included — goes to zero. */
        wr32(image + record, (uint32_t)WB_ACTOR_FREE_MARKER << 16);
        for (unsigned offset = sizeof(uint32_t); offset < WB_ACTOR_RECORD_BYTES;
             offset += sizeof(uint32_t))
            wr32(image + addr_add(record, offset), 0);
        record = addr_add(record, WB_ACTOR_RECORD_BYTES);
    } while (remaining-- != 0);
}

void actor_slots_mark_free(uint8_t *image, uint32_t first, uint32_t count) {
    uint32_t record = first;
    uint16_t remaining = (uint16_t)count;                       /* d7, a `dbf` count */

    /* Only the marker word: unlike the reset above, this leaves every other field of the freed
     * records exactly as the actor that occupied them left it. */
    do {
        wr16(image + addr_add(record, WB_ACTOR_X), WB_ACTOR_FREE_MARKER);
        record = addr_add(record, WB_ACTOR_RECORD_BYTES);
    } while (remaining-- != 0);
}

/* The thirty-eight bytes $1b68 and $1b8e spell identically bar two operand words. Both walk the
 * table WB_ACTOR_TABLE_SELECTED publishes, not a table of their own — so an allocation follows
 * whichever table `project_actor_list` last named. */
static uint32_t actor_alloc_slot(const uint8_t *image, unsigned first, unsigned slots) {
    uint32_t record = addr_add(be32(image + WB_ACTOR_TABLE_SELECTED),
                               first * WB_ACTOR_RECORD_BYTES);
    uint16_t remaining = (uint16_t)(slots - 1);

    do {
        if (be16(image + addr_add(record, WB_ACTOR_X)) == WB_ACTOR_FREE_MARKER)
            return record;
        record = addr_add(record, WB_ACTOR_RECORD_BYTES);
    } while (remaining-- != 0);

    return WB_ACTOR_ALLOC_NONE;
}

uint32_t actor_alloc_slot_low(const uint8_t *image) {
    return actor_alloc_slot(image, WB_ACTOR_ALLOC_LOW_FIRST, WB_ACTOR_ALLOC_LOW_SLOTS);
}

uint32_t actor_alloc_slot_high(const uint8_t *image) {
    return actor_alloc_slot(image, WB_ACTOR_ALLOC_HIGH_FIRST, WB_ACTOR_ALLOC_HIGH_SLOTS);
}

/* `cmp.w #$36/$37/$38/$3b/$3c,d0` — five separate compares, in this order. These are the types
 * whose footprint comes out of the TEMPLATE; every other type's comes out of WB_ACTOR_SIZE_TABLE. */
static const uint16_t SPAWN_TYPES_WITH_OWN_SIZE[] = {0x36, 0x37, 0x38, 0x3b, 0x3c};

static int spawn_type_carries_its_own_size(uint16_t type) {
    for (unsigned i = 0; i < sizeof SPAWN_TYPES_WITH_OWN_SIZE / sizeof *SPAWN_TYPES_WITH_OWN_SIZE;
         i++)
        if (type == SPAWN_TYPES_WITH_OWN_SIZE[i])
            return 1;
    return 0;
}

void actor_spawn_from_template(uint8_t *image, uint32_t template_record, uint32_t record) {
    uint16_t type = be16(image + addr_add(template_record, WB_SPAWN_TYPE));

    /* `clr.w 8(a1)` reaches BOTH flag bytes, which is why the `bset` below is the record's only
     * raised bit however the slot's previous occupant left it. */
    wr16(image + addr_add(record, WB_ACTOR_FLAGS), 0);
    wr16(image + addr_add(record, WB_ACTOR_X),
         be16(image + addr_add(template_record, WB_SPAWN_X)));
    wr16(image + addr_add(record, WB_ACTOR_Y),
         be16(image + addr_add(template_record, WB_SPAWN_Y)));
    wr16(image + addr_add(record, WB_ACTOR_TYPE), type);

    if (spawn_type_carries_its_own_size(type)) {
        wr16(image + addr_add(record, WB_ACTOR_HALF_WIDTH),
             be16(image + addr_add(template_record, WB_SPAWN_SIZE)));
        wr16(image + addr_add(record, WB_ACTOR_SIZE_SECOND),
             be16(image + addr_add(template_record, WB_SPAWN_SIZE + sizeof(uint16_t))));
    } else {
        /* `lsl.w #2` on a d0 whose high half a `moveq #0` cleared: the index is a WORD, so a type
         * from $4000 up wraps back into the table rather than running past it. */
        uint16_t index = (uint16_t)(type << 2);
        wr32(image + addr_add(record, WB_ACTOR_HALF_WIDTH),
             be32(image + addr_add(WB_ACTOR_SIZE_TABLE, index)));
    }

    wr16(image + addr_add(record, WB_ACTOR_SPRITE), 0);
    image[addr_add(record, WB_ACTOR_FIELD_30)] = 0;
    image[addr_add(record, WB_ACTOR_FIELD_31)] = 0;
    image[addr_add(record, WB_ACTOR_FIELD_18)] = 0;
    image[addr_add(record, WB_ACTOR_FLAGS2)] |= (uint8_t)(1u << WB_ACTOR_FLAGS2_SPAWNED_BIT);

    /* `move.l a0,d0 / sub.l $21e8c,d0 / asr.l #5 / move.b d0,19(a1)`: a SIGNED longword shift, and
     * only its low byte is stored — a template past record 127 of the table records a slot number
     * that has wrapped. */
    image[addr_add(record, WB_ACTOR_TEMPLATE_SLOT)] =
        (uint8_t)((int32_t)(template_record - be32(image + WB_TABLE_PTR_21E8C))
                  >> WB_ACTOR_TEMPLATE_SLOT_SHIFT);
}

void actor_start_motion_at_speed(uint8_t *image, uint32_t actor, uint32_t speed) {
    uint8_t *flags = image + addr_add(actor, WB_ACTOR_FLAGS);

    *flags &= (uint8_t)~(1u << WB_ACTOR_FLAG_SUPPORTED_BIT);
    *flags |= (uint8_t)((1u << WB_ACTOR_FLAG_MOVING_BIT) | (1u << WB_ACTOR_FLAG_LAUNCHED_BIT));
    image[addr_add(actor, WB_ACTOR_SPEED)] = (uint8_t)speed;    /* `move.b d0,11(a0)` */
}

void actor_accelerate_fall(uint8_t *image, uint32_t actor) {
    uint8_t *flags = image + addr_add(actor, WB_ACTOR_FLAGS);
    uint8_t *speed = image + addr_add(actor, WB_ACTOR_SPEED);

    *flags &= (uint8_t)~(1u << WB_ACTOR_FLAG_SUPPORTED_BIT);
    *flags |= (uint8_t)(1u << WB_ACTOR_FLAG_FALLING_BIT);

    /* `cmpi.b #$8,d0 / beq`: the terminal speed is reached EXACTLY, so a record already carrying a
     * larger byte keeps climbing — and `addq.b` wraps rather than saturating. */
    if (*speed != WB_ACTOR_FALL_SPEED_MAX)
        *speed = (uint8_t)(*speed + 1);
}

/* --- the per-frame spawn pass ($ff42, $1006a) ---------------------------------------------------
 *
 * The lifecycle above CREATES records; this is what decides when. The template table's four-word
 * header carries a capacity, a live count, a cursor and a "the cursor has been all the way round"
 * flag, and the pass runs one of two arms off them: while the cursor is still walking, spawn the
 * ONE template it names and step it on; afterwards, sweep the whole table and spawn every template
 * whose countdown has reached zero.
 */

/* `move.w -8(a6),d0` and its three neighbours, as offsets from one header base — so a field that
 * moves fails in one place rather than in four `-N(a6)` literals. */
static uint32_t spawn_header(uint32_t table) {
    return addr_add(table, (uint32_t)-(int32_t)WB_SPAWN_HEADER_BYTES);
}

static uint16_t spawn_header_word(const uint8_t *image, uint32_t table, unsigned field) {
    return be16(image + addr_add(spawn_header(table), field));
}

static void spawn_header_set(uint8_t *image, uint32_t table, unsigned field, uint16_t value) {
    wr16(image + addr_add(spawn_header(table), field), value);
}

/* One spawn, as both arms spell it: raise the live count, take a slot, fill it in, seed the
 * template's hit points.
 *
 * THE ALLOCATOR'S RESULT IS NOT TESTED, and that is behaviour rather than an omission here: the
 * two `jsr $1b68.w` sites in this routine hand a1 straight to `actor_spawn_from_template`, so a
 * FULL POOL spawns over WB_ACTOR_ALLOC_NONE and its stores land on the 68000 vector page. The
 * third site in the image, $101dc, is the only one that does test it. */
static void spawn_one(uint8_t *image, uint32_t table, uint32_t template_record) {
    spawn_header_set(image, table, WB_SPAWN_HEADER_LIVE,
                     (uint16_t)(spawn_header_word(image, table, WB_SPAWN_HEADER_LIVE) + 1));
    actor_spawn_from_template(image, template_record, actor_alloc_slot_low(image));
    actor_template_set_hitpoints(image, template_record);
}

/* Both walks close the same way — `lea 32(a0),a0 / cmpi.w #$ffff,(a0) / bne` — so the terminator is
 * tested only AFTER a record has been handled, and the first record is handled unconditionally. */
static int spawn_table_ends_at(const uint8_t *image, uint32_t record) {
    return be16(image + record) == WB_SPAWN_TERMINATOR;
}

void actor_spawn_pass(uint8_t *image) {
    /* `tst.w $a30.w / bne`: a NONZERO test, unlike the `bpl` the projections read the same word
     * with (src/actor.c's header) — the whole pass is skipped in the A30 mode. */
    if (be16(image + WB_STATE_FLAG_A30) != 0)
        return;

    uint32_t table = be32(image + WB_TABLE_PTR_21E8C);

    /* The countdown walk, and it runs on EVERY frame — before the capacity test below can return.
     * `subq.b #1` WRAPS rather than sticking at zero. In the sweep arm that never shows, because the
     * sweep disarms the record on the frame the byte reaches 0; in the cursor arm, where no sweep
     * runs, an armed record really does count down past zero and round again. */
    uint32_t record = table;
    do {
        if (image[addr_add(record, WB_SPAWN_ARMED)] != 0)
            image[addr_add(record, WB_SPAWN_COUNTDOWN)] -= 1;
        record = addr_add(record, WB_SPAWN_RECORD_BYTES);
    } while (!spawn_table_ends_at(image, record));

    if (spawn_header_word(image, table, WB_SPAWN_HEADER_MAX_LIVE)
        == spawn_header_word(image, table, WB_SPAWN_HEADER_LIVE))
        return;

    if (spawn_header_word(image, table, WB_SPAWN_HEADER_WRAPPED) != WB_SPAWN_WRAPPED_SET) {
        /* `lsl.l #5,d0` builds the byte offset as a LONGWORD and `lea 0(a0,d0.w),a0` then indexes
         * with its SIGN-EXTENDED LOW WORD — the extension word is $0000, not the $0800 the size
         * table's lookup carries. So a cursor of 1024 names a template 32 KB BELOW the table and
         * one of 2048 names the table itself: the shift's own long result never reaches the sum. */
        uint16_t cursor = spawn_header_word(image, table, WB_SPAWN_HEADER_CURSOR);
        spawn_header_set(image, table, WB_SPAWN_HEADER_CURSOR, (uint16_t)(cursor + 1));

        uint32_t next = addr_add(table,
                                 sign_ext16((uint16_t)(cursor * WB_SPAWN_RECORD_BYTES)));
        if (spawn_table_ends_at(image, addr_add(next, WB_SPAWN_RECORD_BYTES)))
            spawn_header_set(image, table, WB_SPAWN_HEADER_WRAPPED, WB_SPAWN_WRAPPED_SET);
        spawn_one(image, table, next);
        return;
    }

    /* ...and once it has been round, every armed template whose countdown has run out. The capacity
     * test above ran ONCE, so this arm can raise the live count past WB_SPAWN_HEADER_MAX_LIVE in a
     * single pass. */
    record = table;
    do {
        if (image[addr_add(record, WB_SPAWN_ARMED)] != 0
            && image[addr_add(record, WB_SPAWN_COUNTDOWN)] == 0) {
            image[addr_add(record, WB_SPAWN_ARMED)] = 0;
            spawn_one(image, table, record);
        }
        record = addr_add(record, WB_SPAWN_RECORD_BYTES);
    } while (!spawn_table_ends_at(image, record));
}

void actor_template_set_hitpoints(uint8_t *image, uint32_t template_record) {
    /* `moveq #0,d0 / move.w 6(a0),d0 / asr.w #1,d0` — a SIGNED WORD shift in a register whose high
     * half a `moveq` cleared, and every add below is a `.w`, so the whole sum is one word wide. */
    int16_t kills = (int16_t)be16(image + addr_add(template_record, WB_SPAWN_KILL_COUNT));
    uint16_t type = be16(image + addr_add(template_record, WB_SPAWN_TYPE));
    uint16_t hitpoints = (uint16_t)(kills >> 1);

    if (type == WB_SPAWN_HITPOINT_TYPE_FIXED) {
        hitpoints = (uint16_t)(hitpoints + WB_SPAWN_HITPOINT_FIXED_BASE);
    } else {
        /* `add.w d1,d1` on a zero-extended type, then `adda.l d1,a2`: the index is a WORD — it
         * wraps for a type from $8000 up — and the address arithmetic that consumes it is long. */
        uint16_t index = (uint16_t)(type + type);
        hitpoints = (uint16_t)(hitpoints
                               + be16(image + addr_add(WB_SPAWN_HITPOINT_TABLE, index)));
    }

    wr16(image + addr_add(template_record, WB_SPAWN_HITPOINTS), hitpoints);
}

/* --- what an actor does when a map step reports back ($2b5a, $2b82, $2b8e) ----------------------
 *
 * All three are entered with the pair actor_step_left_against_map / _right leave behind: d0's low
 * BYTE is the step's outcome and d1's low word the ground flags. They share the eight bytes at
 * $2b7a, which four branches reach and no call does — `flip_side_flag` below is those eight bytes,
 * and test_actor.py pins all three whole bodies including it.
 */
static void flip_side_flag(uint8_t *image, uint32_t actor) {
    image[addr_add(actor, WB_ACTOR_FLAGS)] ^= (uint8_t)(1u << WB_ACTOR_FLAG_SIDE_BIT);
}

/* `tst.b d0` — only the LOW BYTE decides, so a caller's high bits are invisible to all three. */
static int step_was_blocked(uint32_t step_outcome) {
    return (uint8_t)step_outcome == WB_ACTOR_STEP_BLOCKED;
}

/* `btst #n,d1` on a data register is a LONGWORD test; every bit these three read is in the low
 * word, so the two readings agree, and this is the register-wide one the instruction does. */
static int ground_flag(uint32_t ground_flags, unsigned bit) {
    return (ground_flags & (1u << bit)) != 0;
}

void actor_hop_or_flip_side(uint8_t *image, uint32_t actor, uint32_t step_outcome,
                            uint32_t ground_flags) {
    if (!step_was_blocked(step_outcome)) {
        /* The step went through: the only thing that turns the actor round is a two-cell drop. */
        if (ground_flag(ground_flags, WB_ACTOR_GROUND_DROP_TWO_BIT))
            flip_side_flag(image, actor);
        return;
    }
    if (ground_flag(ground_flags, WB_ACTOR_GROUND_STEP_UP_BIT))
        actor_start_motion_at_speed(image, actor, WB_ACTOR_HOP_SPEED);
    else
        flip_side_flag(image, actor);
}

void actor_toggle_side_flag(uint8_t *image, uint32_t actor, uint32_t step_outcome,
                            uint32_t ground_flags) {
    if (step_was_blocked(step_outcome) || ground_flag(ground_flags, WB_ACTOR_GROUND_DROP_ONE_BIT))
        flip_side_flag(image, actor);
}

void actor_turn_and_launch(uint8_t *image, uint32_t actor, uint32_t step_outcome,
                           uint32_t ground_flags) {
    uint8_t *flags = image + addr_add(actor, WB_ACTOR_FLAGS);

    if (!step_was_blocked(step_outcome) && !ground_flag(ground_flags, WB_ACTOR_GROUND_DROP_ONE_BIT))
        return;

    /* `btst #2,8(a0) / beq`: a record that is not SUPPORTED is left entirely alone — the side flip
     * included, which is the whole difference between this and actor_toggle_side_flag's head. */
    if (!(*flags & (1u << WB_ACTOR_FLAG_SUPPORTED_BIT)))
        return;

    /* The rest is `bchg #3` over exactly what actor_start_motion_at_speed writes, with the speed a
     * literal rather than a register — which is why it is spelt out here instead of calling it. */
    flip_side_flag(image, actor);
    *flags &= (uint8_t)~(1u << WB_ACTOR_FLAG_SUPPORTED_BIT);
    *flags |= (uint8_t)((1u << WB_ACTOR_FLAG_MOVING_BIT) | (1u << WB_ACTOR_FLAG_LAUNCHED_BIT));
    image[addr_add(actor, WB_ACTOR_SPEED)] = WB_ACTOR_TURN_LAUNCH_SPEED;
}

/* --- $69fe and $6b46: the two damage paths ------------------------------------------------------
 *
 * ONE SHAPE, TWO POOLS. Both are entered with the actor record in a0, both trigger an SFX through
 * src/sound.c's stub, and both spend a HUD slot one charge at a time — and each has a SECOND pool
 * it falls back on when its slot is empty. $69fe takes the hit ON the followed record: a charge off
 * WB_HUD_SLOT_BBBE if it has one, otherwise WB_HUD_METER_VALUE. $6b46 deals one: it spends
 * WB_HUD_SLOT_BBC0 to DOUBLE the damage it takes off the attacker's template pool.
 *
 * WHAT NAMES THE TWO SLOTS is the message each posts as it empties, resolved through the message
 * table rather than transcribed — and TWO NUMBERING BASES meet here, so both are spelt out. A
 * message ID is 1-BASED (`subi.b #$1,d0`, WB_TEXT_MESSAGE_FIRST_ID), while the table's RECORDS are
 * indexed from 0, so record N holds message id N+1:
 *
 *   WB_TEXT_MSG_HELMET_BROKEN   = id $18 = record $17, "   Helmet is Broken"  ($69fe's)
 *   WB_TEXT_MSG_GAUNTLET_BROKEN = id $19 = record $18, " Gauntlet is Broken"  ($6b46's)
 *
 * $18 is therefore BOTH the helmet's id and the gauntlet's record index, which is why each constant
 * is written beside its own string. test/test_actor.py's
 * `test_the_two_slots_are_named_by_the_messages_their_paths_post` pins the id-to-string resolution
 * against the image; that the string then names the SLOT the path spends is the reading it
 * supports, not something the battery proves.
 *
 * THE ONE CALL SITE IN THE IMAGE THAT IS NOT CHANNEL A is $6b46's first two instructions
 * (`move.w #$13,d0 / move.w #$1,d1`), so the trigger's B arm is live code and not the dead arm
 * batch 16b took it for. It runs BEFORE any state is read, which is why the two routines sat
 * unportable until $1a48a was.
 */

/* `tst.b slot / beq` then `subq.b #1,slot / bne`: one charge off a HUD slot, and on the frame it
 * empties, the slot is rearmed and its message posted. The answer is what BOTH paths branch on —
 * each does something different when the slot had nothing to give.
 *
 * The rearm is the same word src/effects.c's `hud_slot_set(image, slot, 0)` composes, and is NOT
 * routed through it: that helper is `static` to effects.c, and the originals are unrelated code —
 * `move.w #$ff,slot.l` inside this body against a whole separate dispatch-table leaf there. Making
 * it shared would export a symbol across two modules to save one `wr16`. */
static int hud_slot_spend_charge(uint8_t *image, uint32_t slot, uint8_t message_id) {
    if (image[slot] == 0)
        return 0;

    image[slot] = (uint8_t)(image[slot] - 1);
    if (image[slot] == 0) {
        wr16(image + slot, WB_HUD_SLOT_REARM);
        image[WB_TEXT_REQUEST] = message_id;
        wr16(image + WB_TEXT_LIFETIME_REQUEST, WB_TEXT_LIFETIME_DEFAULT);
    }
    return 1;
}

/* How much the record `attacker` takes off, from its WB_ACTOR_TEMPLATE_SLOT byte.
 *
 * `moveq #0,d0 / move.b 19(a0),d0 / bmi` — the byte's SIGN BIT is a discriminator, not part of a
 * slot number: a byte of $80 or more carries the damage in its own low seven bits and no table is
 * read at all. */
static uint16_t actor_damage_word(const uint8_t *image, uint32_t attacker) {
    uint8_t slot = image[addr_add(attacker, WB_ACTOR_TEMPLATE_SLOT)];

    if (slot & (uint8_t)~WB_ACTOR_DAMAGE_INLINE_MASK)
        return slot & WB_ACTOR_DAMAGE_INLINE_MASK;

    /* `lsl.l #5,d0 / move.w 12(a6,d0.w),d0`: the shift is a longword one and the index that
     * consumes it a SIGN-EXTENDED word, but this arm's slot is at most
     * WB_ACTOR_DAMAGE_INLINE_MASK, so the product cannot leave the positive half and the sign
     * extension is provably a no-op here. */
    uint32_t template_record = addr_add(be32(image + WB_TABLE_PTR_21E8C),
                                        (uint32_t)slot * WB_SPAWN_RECORD_BYTES);
    uint16_t type = be16(image + addr_add(template_record, WB_SPAWN_TYPE));

    /* ...and the second index is NOT sign-extended: `add.w d0,d0` wraps in sixteen bits over a
     * register whose high half the `moveq` cleared, and `move.w 0(a2,d0.l),d0` then takes the whole
     * longword. So a type from $4000 up reads up to 64 KB ABOVE the table rather than below it. */
    return be16(image + addr_add(WB_ACTOR_DAMAGE_TABLE, (uint16_t)(type + type)));
}

/* The arm the flicker test guards: the helmet if it has a charge, the meter if it has not. */
static void actor_charge_damage(uint8_t *image, uint32_t record, uint16_t damage) {
    if (hud_slot_spend_charge(image, WB_HUD_SLOT_BBBE, WB_TEXT_MSG_HELMET_BROKEN))
        return;

    /* `sub.w d0,$b6fa / bpl / clr.w $b6fa` — a read-modify-write ON MEMORY whose branch reads the
     * RESULT, so a meter already NEGATIVE that the subtraction carries back into the positive half
     * is stored rather than floored. The floor's own strictness is invisible: landing exactly on
     * zero stores zero on either arm. */
    uint16_t left = (uint16_t)(be16(image + WB_HUD_METER_VALUE) - damage);
    wr16(image + WB_HUD_METER_VALUE, (int16_t)left < 0 ? 0 : left);
    image[addr_add(record, WB_ACTOR_FLICKER_COUNTDOWN)] = WB_ACTOR_DAMAGE_FLICKER_FRAMES;
}

void actor_damage_followed(uint8_t *image, uint32_t attacker) {
    /* `tst.b $a32.w` — the mode word's HIGH BYTE, where every other reader of it in the image is a
     * `tst.w` (../names.txt). The game only ever writes $0000 or $ffff, so the two readings agree
     * on its own data and part company on a small positive word — in the OPPOSITE direction from
     * `followed_actor_record`, whose `bne` on the same word picks the A32 record for a $0001 this
     * one leaves on the default. */
    uint32_t record = image[WB_STATE_FLAG_A32] != 0 ? WB_ACTOR_FOLLOWED_A32
                                                    : WB_ACTOR_FOLLOWED_DEFAULT;
    uint8_t *flags = image + addr_add(record, WB_ACTOR_FLAGS);
    uint8_t *flags2 = image + addr_add(record, WB_ACTOR_FLAGS2);

    /* The one path out that writes NOTHING AT ALL. */
    if (*flags2 & (1u << WB_ACTOR_FLAGS2_INVULNERABLE_BIT))
        return;

    *flags2 |= (uint8_t)(1u << WB_ACTOR_FLAGS2_BIT_0);
    image[addr_add(record, WB_ACTOR_FIELD_31)] = (uint8_t)(
        WB_ACTOR_DAMAGE_FIELD_31_BASE - 2 * be16(image + WB_EFFECT_STATE_BD66));
    image[addr_add(record, WB_ACTOR_FIELD_22)] = 0;

    /* `bset #6,8(a1) / bne`: the flicker goes up either way, and the whole COST of the hit is
     * skipped when it was already up — a record still flickering from the last one is knocked back
     * again but pays nothing. */
    int was_flickering = *flags & (1u << WB_ACTOR_FLAG_FLICKER_BIT);
    *flags |= (uint8_t)(1u << WB_ACTOR_FLAG_FLICKER_BIT);
    if (!was_flickering)
        actor_charge_damage(image, record, actor_damage_word(image, attacker));

    /* `move.w (a1),d0 / move.w (a0),d1 / cmp.w d0,d1 / bgt` — the same signed comparison
     * `actor_set_side_flag` makes, read the other way round (the bit lands on the record being
     * damaged, not on the attacker) and INCLUSIVE where that one's `ble` is strict: an attacker
     * exactly level with the record raises the bit here and would clear it there. */
    if (actor_x(image, attacker) > actor_x(image, record)) {
        *flags &= (uint8_t)~(1u << WB_ACTOR_FLAG_SIDE_BIT);
        image[addr_add(record, WB_ACTOR_FIELD_30)] = 0;
    } else {
        *flags |= (uint8_t)(1u << WB_ACTOR_FLAG_SIDE_BIT);
        image[addr_add(record, WB_ACTOR_FIELD_30)] = WB_ACTOR_DAMAGE_FIELD_30_SET;
    }

    snd_call_trigger_effect(image, WB_ACTOR_DAMAGE_FOLLOWED_SFX, WB_SND_CHANNEL_A);

    /* The three flag bits and the speed byte `actor_start_motion_at_speed` writes, reached here as
     * `bset #0 / bset #1 / bclr #2` against $2af2's `bclr #2 / bset #0 / bset #1`. One byte and one
     * final value, so the two orders are indistinguishable in the image; the instruction stream is
     * what test/test_actor.py's entry pin carries. */
    actor_start_motion_at_speed(image, record, WB_ACTOR_DAMAGE_KNOCKBACK_SPEED);
}

void actor_damage_template_hitpoints(uint8_t *image, uint32_t actor) {
    /* FIRST, before a byte of state is read — which is why no seeding could ever avoid this call. */
    snd_call_trigger_effect(image, WB_ACTOR_DAMAGE_TEMPLATE_SFX, WB_SND_CHANNEL_B);

    /* `lsl.l #5,d0 / lea 0(a1,d0.w),a1` — the same long-shift/word-index pair `actor_damage_word`
     * documents, and here too the slot is a BYTE, so the product stays inside the positive half. */
    uint32_t template_record = addr_add(
        be32(image + WB_TABLE_PTR_21E8C),
        (uint32_t)image[addr_add(actor, WB_ACTOR_TEMPLATE_SLOT)] * WB_SPAWN_RECORD_BYTES);

    /* `moveq #0,d0 / move.b $b444.l,d0 / addq.b #1,d0` — the list's first BYTE, and a BYTE add, so
     * a $ff there comes back 0 rather than $100. */
    uint16_t damage = (uint8_t)(image[WB_EFFECT_RECORD_LIST] + 1);

    /* The `beq` at the top of the slot test jumps PAST the `add.w d0,d0`, so the doubling runs on
     * both arms that spent a charge — the one that only decremented and the one that emptied the
     * slot — and is skipped only when the slot was already empty on entry. */
    if (hud_slot_spend_charge(image, WB_HUD_SLOT_BBC0, WB_TEXT_MSG_GAUNTLET_BROKEN))
        damage = (uint16_t)(damage + damage);

    uint32_t pool = addr_add(template_record, WB_SPAWN_HITPOINTS);
    uint16_t left = (uint16_t)(be16(image + pool) - damage);
    wr16(image + pool, left);

    /* `beq` then `bmi`, so a pool landing EXACTLY on zero is spent too — and the test is signed, so
     * a pool of $8000 that the subtraction carries into the positive half is not. */
    if ((int16_t)left <= 0)
        image[addr_add(actor, WB_ACTOR_FLAGS2)] |= (uint8_t)(1u << WB_ACTOR_FLAGS2_DEFEATED_BIT);
}
