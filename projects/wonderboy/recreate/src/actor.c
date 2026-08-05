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
