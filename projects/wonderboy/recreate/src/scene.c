/* scene.c — the scene driver at $dbc0 and the visit budget at $de80.
 *
 * ONE ROUTINE, THREE SCENES. game_main_loop runs $dbc0 once a frame and it returns immediately
 * unless a mode flag is negative. WB_STATE_FLAG_A30 hands it the descriptor WB_RECORD_PTR_10420
 * names and two of that descriptor's kinds:
 *
 *   kind 1, THE SPEECH SCRIPT — a byte cursor over a list of message ids. Each rising edge of the
 *           fire button posts the next id with a lifetime of zero (so the box waits rather than
 *           expiring); a byte with its sign bit set ends the scene.
 *   kind 2, THE SHOP — the largest arm. It greets on a countdown, serves the request the player
 *           made by standing on one of three spots, and charges for it: the price is compared
 *           against WB_BCD_COUNTER, subtracted from it, and the item's own
 *           WB_EFFECT_HANDLER_TABLE entry is then run. Every message and every purchase also
 *           spends the shop's VISIT BUDGET, and running that out closes the visit.
 *
 * ...and WB_STATE_FLAG_A32 hands it kind 4, the eight fragments a defeated boss leaves.
 *
 * WHAT PINS THE READING. The two ids the farewell arm hardcodes resolve through the message table
 * in the image: 9 is " Please come again." and $12 "  Never Come Back!!". Together with the price
 * compare against the counter under the score and the purchase dispatch into the effect handlers,
 * that is what makes this a shop rather than a mechanism with an open meaning. What each shipped
 * shop SELLS is not pinned — the records live past the image and are loaded from disk.
 *
 * THE ONE BOUNDARY LEFT. Four exits transfer to $dfbe and one to $1ab4. $dfbe is reconstructed here
 * (batch 27) and runs — its dispatch table's eight entries are all ported code and
 * `stage_load_window` below it has run whole since batch 26 — so those four arms follow their tail
 * to the end. $1ab4 is not reconstructed and `WB_SCENE_EXIT_STAGE_RESET` is still a transfer this
 * file declines to follow; see scene.h. Every `return WB_SCENE_EXIT_*` below names which exit the
 * original took, whether or not this file followed it.
 */
#include "machine.h"
#include "scene.h"
#include "wonderboy.h"
#include "actor.h"
#include "effects.h"
#include "hud.h"
#include "input.h"
#include "map.h"
#include "stage.h"          /* $dfbe's tail IS stage_load_window */

/* $ddf2..$ddfe and $de68..$de74 — the table is read out of the IMAGE and the call goes to the C.
 * The order matches WB_EFFECT_HANDLER_TABLE's own longwords, which test/test_scene.py compares
 * entry by entry against ../names.txt's addresses, so a handler out of place here fails there
 * rather than silently running the wrong effect. */
static void (*const EFFECT_HANDLERS[WB_EFFECT_HANDLER_COUNT])(uint8_t *image) = {
    effect_add4_clamped_b6fa, effect_add2_clamped_b6fa,
    effect_set_bd6a_1, effect_set_bd6a_2, effect_set_bd6a_3, effect_set_bd6a_4,
    effect_set_bbc2_80ff,
    effect_set_bd66_1, effect_set_bd66_2, effect_set_bd66_3, effect_set_bd66_4, effect_set_bd66_5,
    effect_set_bbbe_05ff,
    effect_set_bd68_1, effect_set_bd68_2, effect_set_bd68_3,
    effect_set_bbc0_05ff, effect_set_bbc6_01ff,
    effect_push_record_0605, effect_push_record_0508, effect_push_record_0705,
    effect_push_record_0803,
    effect_restore_b6fa_to_max,
};

/* `moveq #0,d0 / move.w n(a1),d0 / lsl.w #2 / lea table,a0 / lea 0(a0,d0.w),a0 / movea.l (a0),a0 /
 * jsr (a0)`. The index is scaled by a WORD shift and then added as a SIGN-EXTENDED word, so an
 * index outside 0..WB_EFFECT_HANDLER_COUNT-1 reads a longword outside the table and the original
 * calls whatever it finds. Nothing in this port can stand in for that — the same refusal
 * src/blit.c's sprite_dispatch makes for a width code past its four-entry table — so the guard
 * keeps the C inside its own array and test/test_scene.py refuses those indices as inputs.
 *
 * THE HANDLER CAN MOVE THE RECORD POINTER, which is why this returns one. The dispatcher holds the
 * shop record in a1 and spends the visit budget through it two instructions later — but the four
 * PUSH handlers reach the record list with `movea.l $b546,a1`, so they hand a1 back pointing at the
 * word they just pushed, and the `sub.w d0,32(a1)` then lands 32 bytes into the RECORD LIST instead
 * of on the shop's budget. Nothing restores a1 in between. The other nineteen handlers touch no
 * address register at all, so for them a1 is still the record.
 */
static uint32_t scene_run_effect(uint8_t *image, uint16_t index, uint32_t record) {
    if (index >= WB_EFFECT_HANDLER_COUNT)
        return record;
    EFFECT_HANDLERS[index](image);
    if (index >= WB_EFFECT_HANDLER_PUSH_FIRST
        && index < WB_EFFECT_HANDLER_PUSH_FIRST + WB_EFFECT_HANDLER_PUSH_COUNT)
        return be32(image + WB_EFFECT_RECORD_WRITE_PTR);
    return record;
}

/* The one way any arm posts a message: an id byte and a lifetime word, the pair every writer of
 * WB_TEXT_REQUEST in this routine spells. */
static void scene_post_message(uint8_t *image, uint8_t id, uint16_t lifetime) {
    image[WB_TEXT_REQUEST] = id;
    wr16(image + WB_TEXT_LIFETIME_REQUEST, lifetime);
}

static void scene_bump_word(uint8_t *image, uint32_t addr) {
    wr16(image + addr, (uint16_t)(be16(image + addr) + 1));
}


/* --- $101bc, $101be and $dfbe: leaving the scene ----------------------------------------------- */

/* Both of $dfbe's tables hold longwords, and both are indexed with the SAME `lsl.w #2`. */
#define SCENE_TABLE_ENTRY_BYTES  4u

/* $101bc — entry 0 of WB_SCENE_EXIT_ACTION_TABLE: an `rts` and nothing else, the exit action that
 * does nothing. It also BOUNDS the table — being the first of its own targets is what says the
 * table is eight entries and not nine. */
void scene_exit_action_none(uint8_t *image) {
    (void)image;
}

/* `move.w #$1ff,$bbc6.l` — the same word effect_set_bbc6_01ff ($10390) writes, and spelt here as
 * its own immediate because that is what the instruction is: the value in the high byte over the
 * "changed" byte that makes the panel's redraw scanner pick the slot up (effects.h). */
#define SCENE_EXIT_SLOT_BBC6  ((uint16_t)((1u << 8) | WB_HUD_SLOT_CHANGED))

/* $101be — entry 1, and the reason $dfbe could not be ported before batch 27.
 *
 * THE ALLOCATION'S RECORD IS DISCARDED. `jsr $1b68.w` leaves the first free record of slots 3..11 in
 * a1 and the routine never writes through it: all that survives is WB_SCENE_EXIT_ALLOC_COUNT, a word
 * with one operand site in the whole image and therefore NO READER. So the allocation is run for a
 * counter nothing counts.
 *
 * THE PUBLISH/ALLOCATE/REPUBLISH ORDER IS LOAD-BEARING and is the whole of what this routine gets
 * wrong-looking. WB_ACTOR_TABLE_SELECTED is set to WB_ACTOR_TABLE_DEFAULT, the allocator scans THAT
 * table (it reads the published pointer out of memory), and the pointer is then immediately
 * overwritten with WB_ACTOR_TABLE_A30 — so the table the search ran against is NOT the one left
 * selected. Reordering the two stores would leave the same longword behind and search a different
 * table, which is exactly why the two writes and the call are three statements here.
 *
 * The `clr.b` is a BYTE at WB_EFFECT_RECORD_LIST's first address, which the record list's own plate
 * reads as the 0..4 attack level rather than as the list — so it clears that counter and leaves the
 * first record's second byte alone. */
void scene_exit_action_select_a30_table(uint8_t *image) {
    wr16(image + WB_HUD_SLOT_BBC6, SCENE_EXIT_SLOT_BBC6);
    wr16(image + WB_EFFECT_STATE_21E4, 1);
    image[WB_EFFECT_RECORD_LIST] = 0;

    wr32(image + WB_ACTOR_TABLE_SELECTED, WB_ACTOR_TABLE_DEFAULT);
    uint32_t slot = actor_alloc_slot_low(image);
    wr32(image + WB_ACTOR_TABLE_SELECTED, WB_ACTOR_TABLE_A30);

    if (slot != WB_ACTOR_ALLOC_NONE)
        scene_bump_word(image, WB_SCENE_EXIT_ALLOC_COUNT);
}

/* The eight longwords at WB_SCENE_EXIT_ACTION_TABLE, in the order the image holds them. Entries 2..7
 * are effects.h's `set_state_*` stubs, so every target is reconstructed and the dispatch below has
 * no boundary; test/test_scene.py compares this array entry by entry against ../names.txt's
 * addresses, so a handler out of place here fails there rather than silently running the wrong one.
 */
static void (*const EXIT_ACTIONS[WB_SCENE_EXIT_ACTION_COUNT])(uint8_t *image) = {
    scene_exit_action_none, scene_exit_action_select_a30_table,
    set_state_bbc8_1ff, set_state_bbc8_2ff, set_state_bbc8_3ff, set_state_bbc8_4ff,
    set_state_bbc8_6ff, set_state_6f9c_ffff,
};

/* THE INDEX IS NOT THE ENTRY, and the difference is 24 more indices than it looks.
 *
 * `move.w 18(a6),d0 / lsl.w #2 / lea 0(a6,d0.w),a6` scales the index by a WORD shift — which wraps
 * inside 16 bits — and then adds it SIGN-EXTENDED. So what selects the entry is the OFFSET, not the
 * index, and every index whose offset wraps back under the table's 32 bytes dispatches an ordinary
 * entry: $4000..$4007, $8000..$8007 and $c000..$c007 alias onto entries 0..7 exactly as 0..7 do.
 * A guard on the raw index would silently do nothing for all 24 of them while the original ran
 * ported code, so the offset is computed here the same way the start-table read below computes its
 * own, and only an offset that genuinely LEAVES the table is refused.
 *
 * What is refused, then, is a `jsr` through a longword outside the table, which no C can stand in
 * for — the refusal src/blit.c's sprite_dispatch makes for a width code past its four entries. The
 * start-table index below is NOT refused, and that contrast is the point: that one is a data READ,
 * which this file reproduces exactly however far outside the table it lands.
 *
 * scene_run_effect above has the same latent shape over WB_EFFECT_HANDLER_TABLE and still guards on
 * its raw index; ../STATUS.md registers it rather than this batch changing that tier. */
static void scene_run_exit_action(uint8_t *image, uint16_t index) {
    /* Unsigned, so a sign-extended NEGATIVE offset is huge here and fails the same bound. */
    uint32_t offset = sign_ext16((uint16_t)(index * SCENE_TABLE_ENTRY_BYTES));

    if (offset >= WB_SCENE_EXIT_ACTION_COUNT * SCENE_TABLE_ENTRY_BYTES)
        return;
    EXIT_ACTIONS[offset / SCENE_TABLE_ENTRY_BYTES](image);
}

void scene_exit_and_reload(uint8_t *image) {
    uint32_t descriptor = be32(image + WB_RECORD_PTR_10420);
    uint32_t start;

    scene_run_exit_action(image, be16(image + addr_add(descriptor, WB_SCENE_EXIT_ACTION)));
    image[WB_TEXT_BOX_ACTIVE] = 0;

    /* The descriptor pointer is RE-READ ($dfea) rather than kept in a6, which the action just
     * dispatched to was free to clobber — so an action that moved WB_RECORD_PTR_10420 would change
     * which start record this picks. Nothing bounds the index: `lsl.w #2` wraps inside the word and
     * `lea 0(a1,d0.w),a1` sign-extends it, so an index outside the eight entries reads a longword
     * on either side of the table and hands stage_load_window whatever it finds. */
    descriptor = be32(image + WB_RECORD_PTR_10420);
    uint16_t start_index = be16(image + addr_add(descriptor, WB_SCENE_START_INDEX));
    start = be32(image + addr_add(WB_STAGE_START_TABLE,
                                  sign_ext16((uint16_t)(start_index * SCENE_TABLE_ENTRY_BYTES))));

    /* Cleared LAST, one instruction before the call — so this path always hands the hinge an
     * unfrozen scroll and its WB_SCROLL_FOLLOW_X/_Y arm always runs, whatever raised the flag. */
    wr16(image + WB_SCROLL_FOLLOW_FROZEN, 0);
    stage_load_window(image, WB_MAP_ROW_STRIDE, start, WB_TILE_BITMAPS);

    wr16(image + WB_STATE_FLAG_A34, 0);
    wr16(image + WB_PANEL_FRAME_HOLD, 0);
    wr16(image + WB_STATE_FLAG_A30, 0);
    wr16(image + WB_STATE_FLAG_A32, 0);
    wr16(image + WB_SCENE_MESSAGE_PENDING, 0);
}

/* The four transfers into $dfbe — three branches and one `bsr` + `rts`, all of which leave
 * scene_run_frame through that routine's own `rts`. The C calls it and still reports WHICH exit it
 * took, because that is what a case names its expectation with. */
static uint32_t scene_reload_and_report(uint8_t *image) {
    scene_exit_and_reload(image);
    return WB_SCENE_EXIT_RELOAD;
}

/* $de80. `sub.w d0,32(a1) / bmi` — a WORD subtract, so the borrow is the SIGN of the result and a
 * budget that wraps past $8000 closes the visit exactly as an honestly exhausted one does.
 *
 * Closing it stamps the 2x2 block into the collision map (map_stamp_block, which reads the same
 * descriptor and needs no argument) and then clears the marker cell WB_SCENE_MARKER_CELL_PTR
 * names, TOGETHER WITH ITS TWIN: the byte is compared against its right neighbour first and its
 * left one second, and the matching one is cleared as well. A cell with no matching neighbour
 * takes the `jmp $1ab4.w` instead — the tail this file does not follow. */
uint32_t scene_spend_visit_budget(uint8_t *image, uint32_t record, uint32_t amount) {
    uint32_t budget = addr_add(record, WB_SHOP_VISIT_BUDGET);
    int16_t left = (int16_t)(be16(image + budget) - (uint16_t)amount);
    uint32_t cell;
    uint8_t code;

    wr16(image + budget, (uint16_t)left);
    if (left >= 0)
        return WB_SCENE_EXIT_RETURN;

    map_stamp_block(image);
    cell = be32(image + WB_SCENE_MARKER_CELL_PTR);
    code = image[cell];
    image[cell] = 0;
    if (code == image[addr_add(cell, 1)]) {
        image[addr_add(cell, 1)] = 0;
        return WB_SCENE_EXIT_RETURN;
    }
    if (code != image[addr_add(cell, -1)])
        return WB_SCENE_EXIT_STAGE_RESET;
    image[addr_add(cell, -1)] = 0;
    return WB_SCENE_EXIT_RETURN;
}

/* $dc00 — the speech script. `tst.b d0 / bpl` is a SIGN test of the edge byte, i.e. the fire bit
 * alone, where the shop's acknowledge test one arm below is a nonzero test of the whole byte. */
static uint32_t scene_run_speech(uint8_t *image) {
    uint32_t cursor;

    if ((int8_t)joy1_newly_pressed(image) >= 0)
        return WB_SCENE_EXIT_RETURN;

    cursor = be32(image + WB_SPEECH_SCRIPT_CURSOR);
    if ((int8_t)image[cursor] < 0)
        return scene_reload_and_report(image);

    scene_post_message(image, image[cursor], WB_SPEECH_LIFETIME);
    wr32(image + WB_SPEECH_SCRIPT_CURSOR, addr_add(cursor, 1));
    return WB_SCENE_EXIT_RETURN;
}

/* $dd12 — the greeting, and the arm a purchase the player cannot afford falls into (`bgt $dd12`).
 * The `subq.w #1 / bne` tests the DECREMENTED word, so a countdown seeded 0 wraps to $ffff and
 * takes 65536 frames rather than firing at once. Which of the three ids it posts is chosen by
 * WB_SHOP_GREET_COUNT and — on the arm the shipped `cmpi.w #$1,$28.l` slip made unreachable — by
 * the vector page; wonderboy.h's WB_VECTOR_LINE_A records the slip. */
static uint32_t scene_run_greeting(uint8_t *image) {
    uint32_t record;
    uint16_t id;
    uint16_t left = (uint16_t)(be16(image + WB_SHOP_GREET_COUNTDOWN) - 1);

    wr16(image + WB_SHOP_GREET_COUNTDOWN, left);
    if (left != 0)
        return WB_SCENE_EXIT_RETURN;

    wr16(image + WB_SCENE_MESSAGE_PENDING, WB_SCENE_MESSAGE_PENDING_SET);
    record = be32(image + WB_SHOP_RECORD_PTR);
    if (be16(image + addr_add(record, WB_SHOP_GREET_COUNT)) == 0)
        id = be16(image + addr_add(record, WB_SHOP_GREET_MSG_FIRST));
    else if (be16(image + WB_VECTOR_LINE_A) == WB_VECTOR_ARM_SELECTOR)
        id = be16(image + addr_add(record, WB_SHOP_GREET_MSG_SECOND));
    else
        id = be16(image + addr_add(record, WB_SHOP_GREET_MSG_LATER));

    scene_post_message(image, (uint8_t)id, WB_TEXT_LIFETIME_DEFAULT);
    scene_bump_word(image, addr_add(record, WB_SHOP_GREET_COUNT));
    return scene_spend_visit_budget(image, record, WB_SHOP_MESSAGE_COST);
}

/* $dca6 — the farewell. Its three `move.w n(a1),d0` loads are DEAD: every arm overwrites d0 with a
 * hardcoded id before storing, and the `move.w #$2,d0` below overwrites it again before any exit,
 * so the three record words at 26, 28 and 30 are read and discarded. Not reproduced here, on
 * src/blit.c's rule — a register write no exit can observe is not program output. */
static uint32_t scene_run_farewell(uint8_t *image) {
    uint32_t record;
    uint8_t id = WB_SHOP_FAREWELL_ID_REPEAT;

    wr16(image + WB_SHOP_REQUEST, 0);
    record = be32(image + WB_SHOP_RECORD_PTR);
    wr16(image + WB_SCENE_MESSAGE_PENDING, WB_SCENE_MESSAGE_PENDING_SET);
    if (be16(image + addr_add(record, WB_SHOP_FAREWELL_COUNT)) == 0)
        id = WB_SHOP_FAREWELL_ID_FIRST;

    /* The `cmpi.w #$1,$2c.l` slip splits the non-first case in two and BOTH halves post the same
     * id, which is why the vector page does not appear here at all: the two arms are observably
     * one. wonderboy.h's WB_VECTOR_LINE_F records the instruction; the greeting arm above is where
     * the same slip does change what is posted. */
    scene_post_message(image, id, WB_TEXT_LIFETIME_DEFAULT);
    scene_bump_word(image, addr_add(record, WB_SHOP_FAREWELL_COUNT));
    return scene_spend_visit_budget(image, record, WB_SHOP_MESSAGE_COST);
}

/* $dd94 and $de0a — one purchase, twice, differing only in which five fields of the record it
 * reads. The compare is `cmp.w counter,d0 / bgt`, a SIGNED word compare of the price against
 * WB_BCD_COUNTER: four packed BCD digits, so a purse of 8000 or more reads NEGATIVE and every
 * priced item is refused until it is spent back below that. Refusing does not return — it falls
 * into the greeting arm, countdown and all. */
static uint32_t scene_run_purchase(uint8_t *image, uint32_t price_field, uint32_t count_field,
                                   uint32_t first_id_field, uint32_t repeat_id_field,
                                   uint32_t effect_field) {
    uint32_t record;
    uint16_t price;
    uint16_t id;

    wr16(image + WB_SHOP_REQUEST, 0);
    record = be32(image + WB_SHOP_RECORD_PTR);
    price = be16(image + addr_add(record, price_field));
    if ((int16_t)price > (int16_t)be16(image + WB_BCD_COUNTER))
        return scene_run_greeting(image);

    bcd_sub_counter_bd6e(image, price);
    wr16(image + WB_SCENE_MESSAGE_PENDING, WB_SCENE_MESSAGE_PENDING_SET);
    if (be16(image + addr_add(record, count_field)) == 0)
        id = be16(image + addr_add(record, first_id_field));
    else
        id = be16(image + addr_add(record, repeat_id_field));

    scene_post_message(image, (uint8_t)id, WB_TEXT_LIFETIME_DEFAULT);
    scene_bump_word(image, addr_add(record, count_field));
    /* The effect index is read with the record still in a1; the SPEND that follows is not. */
    record = scene_run_effect(image, be16(image + addr_add(record, effect_field)), record);
    return scene_spend_visit_budget(image, record, WB_SHOP_PURCHASE_COST);
}

/* $dc2a — the shop counter's whole frame.
 *
 * Two waits guard it. While WB_SCENE_MESSAGE_PENDING is up the shop is finished talking and only
 * the FIRE edge (or a box already gone) lets the player out — through the tail, having spent
 * WB_SHOP_MESSAGE_COST first unless WB_SHOP_LEAVE_CHARGED is zero. Otherwise, while
 * WB_SCENE_ACK_WAIT is up, ANY edge (or a box already gone) takes the box down and clears the wait
 * — and then the frame carries on into the request rather than returning. */
static uint32_t scene_run_shop(uint8_t *image) {
    uint32_t record;
    uint16_t request;

    if (be16(image + WB_SCENE_MESSAGE_PENDING) != 0) {
        uint32_t spent;

        if ((int8_t)joy1_newly_pressed(image) >= 0 && image[WB_TEXT_BOX_ACTIVE] != 0)
            return WB_SCENE_EXIT_RETURN;
        record = be32(image + WB_SHOP_RECORD_PTR);
        if (be16(image + addr_add(record, WB_SHOP_LEAVE_CHARGED)) == 0)
            return scene_reload_and_report(image);
        /* The spend's own tail wins where it has one: `bsr $de80` returns here only when the budget
         * held, and the `bra $dfbe` below it is what the leave itself is. */
        spent = scene_spend_visit_budget(image, record, WB_SHOP_MESSAGE_COST);
        return spent == WB_SCENE_EXIT_RETURN ? scene_reload_and_report(image) : spent;
    }

    if (be16(image + WB_SCENE_ACK_WAIT) != 0) {
        if (joy1_newly_pressed(image) == 0 && image[WB_TEXT_BOX_ACTIVE] != 0)
            return WB_SCENE_EXIT_RETURN;
        image[WB_TEXT_BOX_ACTIVE] = 0;
        wr16(image + WB_SCENE_ACK_WAIT, 0);
    }

    request = be16(image + WB_SHOP_REQUEST);
    if (request == 0)
        return scene_run_greeting(image);
    if (request == WB_SHOP_REQUEST_FAREWELL)
        return scene_run_farewell(image);
    if (request == WB_SHOP_REQUEST_ITEM2)
        return scene_run_purchase(image, WB_SHOP_ITEM2_PRICE, WB_SHOP_ITEM2_COUNT,
                                  WB_SHOP_ITEM2_MSG_FIRST, WB_SHOP_ITEM2_MSG_REPEAT,
                                  WB_SHOP_ITEM2_EFFECT);
    /* `cmpi.w #$1 / beq` then `cmpi.w #$2 / beq` and no third test, so item 1 is what EVERY other
     * value lands on, not just WB_SHOP_REQUEST_ITEM1. */
    return scene_run_purchase(image, WB_SHOP_ITEM1_PRICE, WB_SHOP_ITEM1_COUNT,
                              WB_SHOP_ITEM1_MSG_FIRST, WB_SHOP_ITEM1_MSG_REPEAT,
                              WB_SHOP_ITEM1_EFFECT);
}

/* $df24..$df7a — one fragment record, built from the two parameter bytes and the descriptor's
 * variant. `move.b (a2),10(a1)` then `move.b (a2)+,11(a1)` read the SAME byte twice, which is why
 * WB_ACTOR_FIELD_10 and WB_ACTOR_SPEED always agree.
 *
 * The original writes WB_ACTOR_FLAGS four times (three single-bit ops, then the mirror decision).
 * Only the byte's FINAL value is observable — nothing reads the field in between — so this composes
 * it in a register and stores once, the same "model the file where a caller can observe it" rule
 * sprite_draw_record states. */
static void scene_build_fragment(uint8_t *image, uint32_t slot, uint16_t type, uint32_t origin_xy,
                                 const uint8_t *params, int mirrored) {
    uint8_t flags = image[addr_add(slot, WB_ACTOR_FLAGS)];

    wr32(image + addr_add(slot, WB_ACTOR_X), origin_xy);
    wr16(image + addr_add(slot, WB_ACTOR_TYPE), type);
    wr32(image + addr_add(slot, WB_ACTOR_HALF_WIDTH), WB_BOSS_FRAGMENT_SIZE);

    flags |= (uint8_t)(1u << WB_ACTOR_FLAG_MOVING_BIT);
    flags |= (uint8_t)(1u << WB_ACTOR_FLAG_LAUNCHED_BIT);
    flags &= (uint8_t)~(1u << WB_ACTOR_FLAG_SUPPORTED_BIT);
    if (mirrored)
        flags &= (uint8_t)~(1u << WB_ACTOR_FLAG_SIDE_BIT);
    else
        flags |= (uint8_t)(1u << WB_ACTOR_FLAG_SIDE_BIT);
    image[addr_add(slot, WB_ACTOR_FLAGS)] = flags;

    image[addr_add(slot, WB_ACTOR_FIELD_10)] = params[0];
    image[addr_add(slot, WB_ACTOR_SPEED)] = params[0];
    image[addr_add(slot, WB_ACTOR_FIELD_12)] = WB_BOSS_FRAGMENT_FIELD_12;
    image[addr_add(slot, WB_ACTOR_FIELD_30)] = WB_BOSS_FRAGMENT_FIELD_30;
    image[addr_add(slot, WB_ACTOR_FIELD_31)] = params[1];
}

/* $deba — the boss-defeat arm. It frees ten slots whether or not it then refills eight of them:
 * a zero variant returns with WB_BOSS_FRAGMENT_SLOTS left holding WB_ACTOR_FREE_MARKER, and any
 * other variant overwrites those markers immediately. `move.w #$1,d7` is TWO records and
 * `move.w #$7,d6` EIGHT, both being `dbf` counters. */
static uint32_t scene_run_boss_defeat(uint8_t *image) {
    uint32_t descriptor;
    uint32_t origin_xy;
    uint16_t variant;
    uint16_t type;
    unsigned index;
    int leaving = 0;

    if (be16(image + WB_BOSS_DEFEAT_FLAG) != 0) {
        wr16(image + WB_BOSS_DEFEAT_FLAG, 0);
        /* Both counts are `dbf` counts on the wire, which is the argument actor_slots_mark_free
         * takes: it frees one more record than the number it is handed. */
        actor_slots_mark_free(image, WB_ACTOR_TABLE_A32, WB_BOSS_HEAD_SLOT_COUNT - 1u);
        actor_slots_mark_free(image, WB_BOSS_FRAGMENT_SLOTS, WB_BOSS_FRAGMENT_COUNT - 1u);

        descriptor = be32(image + WB_RECORD_PTR_10420);
        variant = be16(image + addr_add(descriptor, WB_SCENE_VARIANT));
        if (variant == 0)
            return WB_SCENE_EXIT_RETURN;

        type = variant == 1 ? WB_BOSS_FRAGMENT_TYPE_1 : WB_BOSS_FRAGMENT_TYPE_2;
        /* `move.l $9e94.l,d0` is read ONCE, before the loop, so all eight fragments carry the
         * position slot 3 held on entry even though the loop writes over slot 3's neighbours. */
        origin_xy = be32(image + WB_BOSS_FRAGMENT_ORIGIN);
        for (index = 0; index < WB_BOSS_FRAGMENT_COUNT; index++) {
            unsigned counter = WB_BOSS_FRAGMENT_COUNT - 1 - index;   /* d6, counting down */

            scene_build_fragment(image,
                                 addr_add(WB_BOSS_FRAGMENT_SLOTS,
                                          index * WB_ACTOR_RECORD_BYTES),
                                 type, origin_xy,
                                 image + addr_add(WB_BOSS_FRAGMENT_PARAMS,
                                                  index * WB_BOSS_FRAGMENT_PARAM_LEN),
                                 counter <= WB_BOSS_FRAGMENT_MIRROR_AT);
        }

        /* `tst.b $bbc4.l / bne $df92` — this arm is WB_HUD_SLOT_BBC4's only reader among the
         * routines reconstructed so far, and it skips the exit-request test below rather than
         * replacing it. */
        leaving = image[WB_HUD_SLOT_BBC4] != 0;
    }

    if (!leaving && be16(image + WB_SCENE_EXIT_REQUEST) == 0)
        return WB_SCENE_EXIT_RETURN;
    wr16(image + WB_SCENE_EXIT_REQUEST, 0);
    return scene_reload_and_report(image);
}

uint32_t scene_run_frame(uint8_t *image) {
    uint32_t descriptor;
    uint16_t kind;

    if ((int16_t)be16(image + WB_STATE_FLAG_A30) < 0) {
        descriptor = be32(image + WB_RECORD_PTR_10420);
        kind = be16(image + addr_add(descriptor, WB_SCENE_KIND));
        if (kind == WB_SCENE_KIND_SPEECH)
            return scene_run_speech(image);
        if (kind == WB_SCENE_KIND_SHOP)
            return scene_run_shop(image);
        return WB_SCENE_EXIT_RETURN;
    }

    if ((int16_t)be16(image + WB_STATE_FLAG_A32) >= 0)
        return WB_SCENE_EXIT_RETURN;

    descriptor = be32(image + WB_RECORD_PTR_10420);
    if (be16(image + addr_add(descriptor, WB_SCENE_KIND)) != WB_SCENE_KIND_BOSS_DEFEAT)
        return WB_SCENE_EXIT_RETURN;
    return scene_run_boss_defeat(image);
}
