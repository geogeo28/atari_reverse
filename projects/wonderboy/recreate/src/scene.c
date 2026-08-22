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
 *
 * EVERY ADDRESS THIS FILE TAKES OUT OF MEMORY GOES THROUGH bus.h. Four pointers here are the image's
 * own and nothing bounds any of them: WB_RECORD_PTR_10420's scene descriptor, WB_SHOP_RECORD_PTR's
 * shop record, WB_SPEECH_SCRIPT_CURSOR's byte cursor and WB_SCENE_MARKER_CELL_PTR's collision cell.
 * Musashi puts each on a 24-BIT bus, and off the image the shim answers ZERO for every address but
 * the seven hardware ones bus.h enumerates; `bus_read_word` is that pair of steps and an unguarded
 * index into the buffer is neither, so the two cores agree only while the host heap happens to hold
 * what the image would have. Batch 43
 * phase C measured the gap: `scene_run_frame` read `descriptor + 2` at 2.4 GiB past the buffer on a
 * seed the suite has driven since batch 42, and killed the pytest worker whenever that page was not
 * mapped. THREE FAMILIES ARE DELIBERATELY NOT IN THIS RULE, because none of their addresses comes
 * out of memory at all — each is a literal plus an index the loop itself bounds: the boss fragments'
 * slots (WB_BOSS_FRAGMENT_SLOTS), the fragment PARAMS `scene_run_boss_defeat` hands its builder as a
 * bare pointer (WB_BOSS_FRAGMENT_PARAMS), and `scene_spawn_boss`'s followed record
 * (WB_ACTOR_FOLLOWED_A32). The census that says three is the whole file scanned for `image[X]`,
 * `beNN(image + X)`, `wrNN(image + X)` and `image + X` handed to a callee, with X anything but a
 * bare WB_* constant — an earlier draft of this paragraph ran the same scan and reported two,
 * because the pointer form is the one a narrower recipe drops.
 */
#include "machine.h"
#include "scene.h"
#include "wonderboy.h"
#include "actor.h"
#include "bus.h"
#include "effects.h"
#include "hud.h"
#include "input.h"
#include "map.h"
#include "stage.h"          /* $dfbe's tail IS stage_load_window */
#include "text.h"           /* the id + lifetime pair every arm here posts through */

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

/* Through the bus for its callers' sake: two of the four hand it a field of the SHOP RECORD, whose
 * pointer comes out of the image and can name an address the image has not got. */
static void scene_bump_word(uint8_t *image, uint32_t addr) {
    bus_write_word(image, addr, (uint16_t)(bus_read_word(image, addr) + 1));
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

    scene_run_exit_action(image, bus_read_word(image, addr_add(descriptor, WB_SCENE_EXIT_ACTION)));
    image[WB_TEXT_BOX_ACTIVE] = 0;

    /* The descriptor pointer is RE-READ ($dfea) rather than kept in a6, which the action just
     * dispatched to was free to clobber — so an action that moved WB_RECORD_PTR_10420 would change
     * which start record this picks. Nothing bounds the index: `lsl.w #2` wraps inside the word and
     * `lea 0(a1,d0.w),a1` sign-extends it, so an index outside the eight entries reads a longword
     * on either side of the table and hands stage_load_window whatever it finds. */
    descriptor = be32(image + WB_RECORD_PTR_10420);
    uint16_t start_index = bus_read_word(image, addr_add(descriptor, WB_SCENE_START_INDEX));
    start = bus_read_long(image, addr_add(WB_STAGE_START_TABLE,
                                          sign_ext16((uint16_t)(start_index
                                                                * SCENE_TABLE_ENTRY_BYTES))));

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

/* $1b46, and the same six instructions again at $de94 inside the visit budget below. See scene.h
 * for why one body serves both and what the flag it returns is for.
 *
 * The neighbours are one CELL either side — the collision map is one byte per cell — and the RIGHT
 * one is tested first.
 *
 * THE THREE BYTES GO THROUGH bus.h, as every address this file takes out of memory now does (see
 * the file header), and the reason was first written down here: `cell` is an ADDRESS REGISTER a
 * caller supplies, $1b46 is entered with a6 already loaded, and nothing between the load and here
 * bounds it. Unguarded, the read — and then the WRITE — lands past the ctypes buffer, where the
 * 68000 side merely reaches an address the shim drops. */
int scene_clear_marker_pair(uint8_t *image, uint32_t cell) {
    uint32_t right = addr_add(cell, WB_MAP_NEIGHBOUR_CELL);
    uint32_t left = addr_add(cell, -(uint32_t)WB_MAP_NEIGHBOUR_CELL);
    uint8_t code = bus_read_byte(image, cell);

    bus_write_byte(image, cell, 0);
    if (code == bus_read_byte(image, right)) {
        bus_write_byte(image, right, 0);
        return 1;
    }
    if (code != bus_read_byte(image, left))
        return 0;
    bus_write_byte(image, left, 0);
    return 1;
}

/* $de80. `sub.w d0,32(a1) / bmi` — a WORD subtract, so the borrow is the SIGN of the result and a
 * budget that wraps past $8000 closes the visit exactly as an honestly exhausted one does.
 *
 * Closing it stamps the 2x2 block into the collision map (map_stamp_block, which reads the same
 * descriptor and needs no argument) and then runs the marker-pair clear above over the cell
 * WB_SCENE_MARKER_CELL_PTR names. A cell with no matching neighbour takes the `jmp $1ab4.w`
 * instead — the tail this file does not follow. */
uint32_t scene_spend_visit_budget(uint8_t *image, uint32_t record, uint32_t amount) {
    uint32_t budget = addr_add(record, WB_SHOP_VISIT_BUDGET);
    int16_t left = (int16_t)(bus_read_word(image, budget) - (uint16_t)amount);

    bus_write_word(image, budget, (uint16_t)left);
    if (left >= 0)
        return WB_SCENE_EXIT_RETURN;

    map_stamp_block(image);
    if (!scene_clear_marker_pair(image, be32(image + WB_SCENE_MARKER_CELL_PTR)))
        return WB_SCENE_EXIT_STAGE_RESET;
    return WB_SCENE_EXIT_RETURN;
}

/* $dc00 — the speech script. `tst.b d0 / bpl` is a SIGN test of the edge byte, i.e. the fire bit
 * alone, where the shop's acknowledge test one arm below is a nonzero test of the whole byte. */
static uint32_t scene_run_speech(uint8_t *image) {
    uint32_t cursor;

    if ((int8_t)joy1_newly_pressed(image) >= 0)
        return WB_SCENE_EXIT_RETURN;

    cursor = be32(image + WB_SPEECH_SCRIPT_CURSOR);
    if ((int8_t)bus_read_byte(image, cursor) < 0)
        return scene_reload_and_report(image);

    text_post_message_for(image, bus_read_byte(image, cursor), WB_SPEECH_LIFETIME);
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
    if (bus_read_word(image, addr_add(record, WB_SHOP_GREET_COUNT)) == 0)
        id = bus_read_word(image, addr_add(record, WB_SHOP_GREET_MSG_FIRST));
    else if (be16(image + WB_VECTOR_LINE_A) == WB_VECTOR_ARM_SELECTOR)
        id = bus_read_word(image, addr_add(record, WB_SHOP_GREET_MSG_SECOND));
    else
        id = bus_read_word(image, addr_add(record, WB_SHOP_GREET_MSG_LATER));

    text_post_message_for(image, (uint8_t)id, WB_TEXT_LIFETIME_DEFAULT);
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
    if (bus_read_word(image, addr_add(record, WB_SHOP_FAREWELL_COUNT)) == 0)
        id = WB_SHOP_FAREWELL_ID_FIRST;

    /* The `cmpi.w #$1,$2c.l` slip splits the non-first case in two and BOTH halves post the same
     * id, which is why the vector page does not appear here at all: the two arms are observably
     * one. wonderboy.h's WB_VECTOR_LINE_F records the instruction; the greeting arm above is where
     * the same slip does change what is posted. */
    text_post_message_for(image, id, WB_TEXT_LIFETIME_DEFAULT);
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
    price = bus_read_word(image, addr_add(record, price_field));
    if ((int16_t)price > (int16_t)be16(image + WB_BCD_COUNTER))
        return scene_run_greeting(image);

    /* ASSUMED, not proved — the one site in the port that claims an entry X it cannot read off its
     * own bytes, which is why it spells a different constant (include/hud.h). NOTHING on the path
     * from $dbc0 to the `jsr $b582.l` at $ddae/$de24 writes X: `tst`, `cmpi`, `clr`, `move`,
     * `movea` and the branches all leave it alone, and the one call on that path — `jsr $682.w`,
     * joy1_newly_pressed — is four instructions, `move.b $8b3.l,d0 / move.b $8cf.l,d1 / eor.b d1,d0
     * / and.b d1,d0`, none of which touch X either. So the bit is the CALLER's: `jsr $b346.l` runs
     * immediately before `jsr $dbc0.l` at $4be, and its last act is `addq.w #1,frame_tick_b39a`,
     * which sets X on the frame that word wraps. 0 is right on every other frame and on every run
     * the oracle can enter. ../STATUS.md keeps it as an open row. */
    bcd_sub_counter_bd6e(image, price, WB_BCD_ENTRY_EXTEND_ASSUMED_CLEAR);
    wr16(image + WB_SCENE_MESSAGE_PENDING, WB_SCENE_MESSAGE_PENDING_SET);
    if (bus_read_word(image, addr_add(record, count_field)) == 0)
        id = bus_read_word(image, addr_add(record, first_id_field));
    else
        id = bus_read_word(image, addr_add(record, repeat_id_field));

    text_post_message_for(image, (uint8_t)id, WB_TEXT_LIFETIME_DEFAULT);
    scene_bump_word(image, addr_add(record, count_field));
    /* The effect index is read with the record still in a1; the SPEND that follows is not. */
    record = scene_run_effect(image, bus_read_word(image, addr_add(record, effect_field)), record);
    return scene_spend_visit_budget(image, record, WB_SHOP_PURCHASE_COST);
}

/* $dc2a — the shop counter's whole frame.
 *
 * Two waits guard it. While WB_SCENE_MESSAGE_PENDING is up the shop is finished talking and only
 * the FIRE edge (or a box already gone) lets the player out — through the tail, having spent
 * WB_SHOP_MESSAGE_COST first unless WB_SHOP_REFUSED_COUNT is zero. Otherwise, while
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
        if (bus_read_word(image, addr_add(record, WB_SHOP_REFUSED_COUNT)) == 0)
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
        variant = bus_read_word(image, addr_add(descriptor, WB_SCENE_VARIANT));
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
        kind = bus_read_word(image, addr_add(descriptor, WB_SCENE_KIND));
        if (kind == WB_SCENE_KIND_SPEECH)
            return scene_run_speech(image);
        if (kind == WB_SCENE_KIND_SHOP)
            return scene_run_shop(image);
        return WB_SCENE_EXIT_RETURN;
    }

    if ((int16_t)be16(image + WB_STATE_FLAG_A32) >= 0)
        return WB_SCENE_EXIT_RETURN;

    descriptor = be32(image + WB_RECORD_PTR_10420);
    if (bus_read_word(image, addr_add(descriptor, WB_SCENE_KIND)) != WB_SCENE_KIND_BOSS_DEFEAT)
        return WB_SCENE_EXIT_RETURN;
    return scene_run_boss_defeat(image);
}


/* --- $19ac: THE SCENE-SPAWN TREE ----------------------------------------------------------------
 *
 * What ENTERS a scene, where everything above is what runs one once a frame. Its one caller is the
 * `bsr.w $19ac` at $c66 inside player_pending_event_gate, on the arm the event actor's animation
 * handshake reaches, and it is driven by the SAME descriptor the driver runs on: a byte-coded
 * script read straight out of WB_RECORD_PTR_10420 with a walking cursor, which is why this file
 * walks one too rather than naming a field per read.
 *
 * THREE ARMS, chosen by WB_SCENE_KIND exactly as $dbc0's are, and a fourth ending that is a bare
 * `rts`: a kind that is not 1, 2 or 4 leaves having done nothing but mark
 * WB_SCENE_SPAWN_GATE_SLOT free. Each arm resets one actor table, fills the first few of its slots
 * with the DISPLAY RECORDS the scene is made of — inert type-0 records the sprite pass draws and no
 * behaviour handler runs — marks the rest free again, and hands stage_load_window a map and tile
 * bank out of WB_SCENE_MAP_BANK_TABLE.
 *
 * WHAT MAKES IT THE PROJECT'S THIRD CLOSED DISPATCH TABLE. The speech arm scales a script BYTE by
 * four and `jsr`s through WB_SPAWN_GATE_TABLE, whose three live entries are the gates below. Unlike
 * the two dispatches above it the index cannot wrap or turn negative — a byte times four is at most
 * 1020 — so the offset guard and an index guard coincide here, and the guard is spelt as the offset
 * only because that is what the `lea` adds.
 *
 * ONE ENDING THIS FILE CANNOT FOLLOW, and it is the original's own: the `illegal` at $1d8e, reached
 * when a shop that has already turned the player away three times turns him away a fourth. See
 * WB_SCENE_EXIT_ILLEGAL in scene.h.
 */

/* `move.w (a1)+,d0` and `move.b (a1)+,d0` — the descriptor is READ SEQUENTIALLY, and the cursor is
 * the original's a1. Through the bus because WB_RECORD_PTR_10420 is a pointer a caller supplied and
 * the descriptor table it names lies past the loaded image. */
static uint16_t script_word(const uint8_t *image, uint32_t *at) {
    uint16_t value = bus_read_word(image, *at);

    *at = addr_add(*at, 2);
    return value;
}

static uint8_t script_byte(const uint8_t *image, uint32_t *at) {
    uint8_t value = bus_read_byte(image, *at);

    *at = addr_add(*at, 1);
    return value;
}


/* --- $e43e, $e456, $e46c: the three SPAWN-SCRIPT GATES ------------------------------------------
 *
 * Three near-identical routines of 24, 22 and 22 bytes, and the whole of WB_SPAWN_GATE_TABLE's live
 * entries. Each compares WB_HUD_SLOT_BBC8's HIGH byte — `cmpi.b #n,$bbc8.l`, i.e. the 1..6 variant
 * the panel draws, not the "changed" byte beside it — against its own number and returns having
 * written nothing when they match.
 *
 * OTHERWISE IT REWRITES THE SCRIPT THE CALLER IS IN THE MIDDLE OF READING, which is the whole point
 * of the mechanism and the reason `cursor` is a parameter. `move.b #$7,(a1)` plants
 * WB_SPAWN_GATE_REFUSED_SCRIPT over the speech index the caller reads ONE INSTRUCTION LATER, and
 * `move.w #$0,1(a1)` clears the descriptor's own WB_SCENE_EXIT_ACTION word behind it. So a player
 * carrying the wrong equipment gets script 7 instead of the descriptor's own, and the scene he then
 * leaves runs exit action 0.
 *
 * `cursor` is the original's a1, which the caller has already advanced past the gate byte: it is
 * WB_SCENE_GATE_INDEX + 1 into the descriptor, an ODD address, so the word write at +1 lands EVEN
 * and the 68000 takes no address error. A case that seeds an odd descriptor would break that, which
 * is why test/test_scene.py seeds only even ones — the original's own writer of that pointer
 * ($162e) can produce nothing else. */
static void spawn_gate(uint8_t *image, uint32_t cursor, uint8_t keep) {
    if (image[WB_HUD_SLOT_BBC8] == keep)
        return;
    bus_write_byte(image, cursor, WB_SPAWN_GATE_REFUSED_SCRIPT);
    bus_write_word(image, addr_add(cursor, 1), 0);
}

void spawn_gate_unless_bbc8_eq1(uint8_t *image, uint32_t cursor) { spawn_gate(image, cursor, 1); }
void spawn_gate_unless_bbc8_eq3(uint8_t *image, uint32_t cursor) { spawn_gate(image, cursor, 3); }
void spawn_gate_unless_bbc8_eq4(uint8_t *image, uint32_t cursor) { spawn_gate(image, cursor, 4); }

/* WB_SPAWN_GATE_TABLE's four longwords in the order the image holds them, which
 * test/test_scene.py compares entry by entry against ../names.txt's addresses. Entry 0 is NOT an
 * address (WB_SPAWN_GATE_ENTRY_0_NOT_AN_ADDRESS) and is never fetched, because the dispatcher below
 * returns on a script byte of zero before it scales one. */
static void (*const SPAWN_GATES[WB_SPAWN_GATE_COUNT])(uint8_t *image, uint32_t cursor) = {
    NULL,
    spawn_gate_unless_bbc8_eq1, spawn_gate_unless_bbc8_eq3, spawn_gate_unless_bbc8_eq4,
};

/* `moveq #0,d0 / move.b (a1)+,d0 / beq / lsl.w #2 / lea $e42e.l,a0 / movea.l 0(a0,d0.w),a0 /
 * jsr (a0)`. The index is a BYTE, so the shift cannot wrap the word and the sign-extended offset
 * cannot be negative — the contrast with scene_run_exit_action above, whose index is a word and
 * whose offset therefore aliases. What is refused is the same thing: a `jsr` through a longword
 * outside the table, which no C can stand in for. */
static void spawn_run_gate(uint8_t *image, uint8_t index, uint32_t cursor) {
    uint32_t offset;

    if (index == 0)
        return;
    offset = sign_ext16((uint16_t)(index * SCENE_TABLE_ENTRY_BYTES));
    if (offset >= WB_SPAWN_GATE_COUNT * SCENE_TABLE_ENTRY_BYTES)
        return;
    SPAWN_GATES[offset / SCENE_TABLE_ENTRY_BYTES](image, cursor);
}


/* --- what all three arms share ------------------------------------------------------------------ */

/* `move.w d0,6(a2) / move.w d1,(a2) / move.w d2,2(a2) / clr.w 4(a2)` in the speech arm, and
 * `move.l #imm,(a1)+ / move.w #imm,(a1)+ / move.w n(a0),(a1)+ / lea 24(a1),a1` in the shop's — the
 * same four fields either way.
 *
 * IT IS IN TWO HALVES BECAUSE THE SHOP'S SPRITE SOURCE IS READ BETWEEN THEM. `move.w 54(a0),(a1)+`
 * is the THIRD instruction of its record, so the read happens AFTER that record's own xy and type
 * are in memory — and the record `a0` points at is one a caller supplied, which can be the very
 * words just written (test/test_scene.py's alias case puts field 54 on slot 0's x). Passing the
 * field as a call ARGUMENT would read it first, and C does not even fix which first: argument
 * order is unspecified. The speech arm has no such hazard — it reads all three of its words out of
 * the script cursor before it stores anything — so it keeps the whole-record form below. */
static void spawn_record_open(uint8_t *image, uint32_t at, uint32_t xy, uint16_t type) {
    /* These two are commutative and a mutant that swaps them is EQUIVALENT, proved rather than
     * assumed: the longword covers [at, at + WB_ACTOR_TYPE) and the word [WB_ACTOR_TYPE,
     * WB_ACTOR_TYPE + 2), which are disjoint for every `at`, and each is guarded against the image
     * independently. The gate round's sweep tried the swap and it survived; no seed can separate
     * them. The order below is the original's. */
    bus_write_long(image, at, xy);
    bus_write_word(image, addr_add(at, WB_ACTOR_TYPE), type);
}

/* ...and the sprite word, plus the cursor at the NEXT record, which is what both originals leave in
 * their address register. */
static uint32_t spawn_record_close(uint8_t *image, uint32_t at, uint16_t sprite) {
    bus_write_word(image, addr_add(at, WB_ACTOR_SPRITE), sprite);
    return addr_add(at, WB_ACTOR_RECORD_BYTES);
}

static uint32_t spawn_display_record(uint8_t *image, uint32_t at, uint32_t xy, uint16_t type,
                                     uint16_t sprite) {
    spawn_record_open(image, at, xy, type);
    return spawn_record_close(image, at, sprite);
}

/* `cmpi.l #$ffffffff,(a2) / beq / move.w #$ffbe,(a2) / lea 32(a2),a2 / bra` — every slot from the
 * cursor up to the table's terminator marked free AGAIN, after actor_table_reset has already marked
 * all nineteen and the arm has overwritten the first few.
 *
 * THE LOOP HAS NO BOUND IN THE ORIGINAL and one here, for the reason src/behavior.c's walk has one
 * and with the same constant: a table with no WB_ACTOR_TABLE_END spins until the machine is reset,
 * and once the cursor leaves the loaded image every read is answered with zero and every write
 * dropped (bus.h), so it can never find one. The cursor's stride divides the 24-bit bus exactly, so
 * after WB_ACTOR_WALK_BUS_CYCLE steps it is back on an address it has already read; the oracle's own
 * instruction cap fires long before, so no differential can tell the two apart. */
static void spawn_free_rest_of_table(uint8_t *image, uint32_t at) {
    for (uint32_t step = 0; step < WB_ACTOR_WALK_BUS_CYCLE; step++) {
        if (bus_read_long(image, at) == WB_ACTOR_TABLE_END)
            return;
        bus_write_word(image, at, WB_ACTOR_FREE_MARKER);
        at = addr_add(at, WB_ACTOR_RECORD_BYTES);
    }
}

/* The tail all three arms end in, in TWO halves because the shop arm reads the descriptor once more
 * between them and a store lands in the gap.
 *
 * `movea.l (a1)+,a0 / movea.l (a1)+,a6 / move.w #$ffff,$d76.w` — both longwords fetched out of
 * WB_SCENE_MAP_BANK_TABLE and only THEN the freeze raised. The entry address is unbounded (`lsl.w
 * #3` on a descriptor word, added SIGN-EXTENDED), so the read is reproduced WHEREVER IT LANDS: not
 * clamped, not refused, not made into an error — through the bus, which is the machine folding it to
 * 24 bits and answering zero off the image, exactly as this file's header says. */
static void spawn_fetch_bank_and_freeze(uint8_t *image, uint32_t bank_offset,
                                        uint32_t *map, uint32_t *tiles) {
    uint32_t entry = addr_add(WB_SCENE_MAP_BANK_TABLE, bank_offset);

    *map = bus_read_long(image, entry);
    *tiles = bus_read_long(image, addr_add(entry, WB_SCENE_MAP_BANK_TILES));
    wr16(image + WB_SCROLL_FOLLOW_FROZEN, WB_SCROLL_FOLLOW_FROZEN_SET);
}

/* ...and `jsr $f95c.l / clr.w $a34.w`, which the three arms then spell identically. */
static void spawn_load_stage(uint8_t *image, uint32_t map, uint32_t start, uint32_t tiles) {
    stage_load_window(image, map, start, tiles);
    wr16(image + WB_STATE_FLAG_A34, 0);
}

/* `moveq #0,d0 / move.w 30(a1),d0 / lsl.w #3` off a RE-READ WB_RECORD_PTR_10420 — not off the
 * cursor the arm has been walking, and not off the pointer the arm read on entry. The re-read is
 * the original's and is kept: a gate above may have written through the descriptor, and the
 * descriptor pointer itself is one of the addresses such a write can land on. */
static uint32_t spawn_map_bank_offset(const uint8_t *image) {
    uint32_t descriptor = be32(image + WB_RECORD_PTR_10420);
    uint16_t index = bus_read_word(image, addr_add(descriptor, WB_SCENE_MAP_BANK_INDEX));

    return sign_ext16((uint16_t)(index * WB_SCENE_MAP_BANK_BYTES));
}

static uint32_t spawn_start_record(uint32_t index) {
    return WB_STAGE_START_RECORDS + index * WB_START_RECORD_LEN;
}

/* `cmpi.w #$5,$bd88.l / blt` — SIGNED, and re-read at each of its four sites. */
static int spawn_is_late_stage(const uint8_t *image) {
    return (int16_t)be16(image + WB_STAGE_NUMBER) >= (int16_t)WB_SCENE_LATE_STAGE_FIRST;
}


/* $1ab4..$1aef — the speech arm's last twenty-eight instructions, WHICH HAVE A SECOND ENTRANCE.
 * A whole-image census over every branch form, both absolute encodings and both data widths finds
 * exactly two instructions naming $1ab4: the fall-through inside $19e2, and the `jmp $1ab4.w` at
 * $deb0 — scene_spend_visit_budget's, taken when an exhausted visit's marker cell matches neither
 * neighbour. (The word $1ab4 also sits at $10432, inside WB_SHOP_RECORD_TABLE's pointer $21ab4,
 * which is data and not an operand.)
 *
 * IT IS A SHARED TAIL AND IT IS SPLIT OUT SO THAT IT CAN BE ONE. What differs between the two
 * entrances is only the ENDING: the tree's own path reaches `movea.l (a7)+,a0 / rts` having pushed
 * that a0 at $19ac, and $deb0's has pushed nothing — so the pop takes $de80's own return address
 * and the `rts` returns one frame further out. That unwind is why `scene_spend_visit_budget` above
 * still reports WB_SCENE_EXIT_STAGE_RESET instead of calling this; the tail it declined to follow
 * is now reconstructed, and only the caller-side convention is left. ../STATUS.md carries it. */
static void scene_spawn_speech_tail(uint8_t *image) {
    uint32_t map, tiles;

    spawn_fetch_bank_and_freeze(image, spawn_map_bank_offset(image), &map, &tiles);
    spawn_load_stage(image, map, spawn_start_record(WB_SCENE_START_RECORD_SPEECH), tiles);
    wr16(image + WB_STATE_FLAG_A30, WB_STATE_FLAG_SET);
}


/* --- kind 1, THE SPEECH SCENE ($19e2..$1aef) ---------------------------------------------------
 *
 * Three display records out of two triples of descriptor words — the first triple twice over, once
 * as it stands and once with the sprite bumped and the x moved WB_SCENE_SPAWN_PAIR_DX along, which
 * is a two-cell object drawn as two records. Then the gate, then the speech script.
 *
 * THE SPEECH INDEX IS READ AFTER THE GATE RUNS, and that ordering is the mechanism rather than an
 * accident: the gate's `move.b #$7,(a1)` writes the very byte the next instruction reads. A port
 * that fetched both script bytes before dispatching would be green on every case whose gate matched
 * and wrong on every case whose gate did not. */
static void scene_spawn_speech(uint8_t *image, uint32_t script, uint32_t marker) {
    uint32_t at = WB_ACTOR_TABLE_A30;
    uint16_t sprite, x, y;
    uint8_t gate, index;

    actor_table_reset(image, WB_ACTOR_TABLE_A30);
    /* `clr.w $1017c.l` on a LONGWORD cursor: only the HIGH half goes. */
    wr16(image + WB_SPEECH_SCRIPT_CURSOR, 0);

    sprite = script_word(image, &script);
    x = script_word(image, &script);
    y = script_word(image, &script);
    if (spawn_is_late_stage(image))
        sprite = WB_SCENE_LATE_STAGE_SPRITE;
    at = spawn_display_record(image, at, ((uint32_t)x << 16) | y, 0, sprite);
    at = spawn_display_record(image, at,
                              ((uint32_t)(uint16_t)(x + WB_SCENE_SPAWN_PAIR_DX) << 16) | y, 0,
                              (uint16_t)(sprite + 1));

    sprite = script_word(image, &script);
    x = script_word(image, &script);
    y = script_word(image, &script);
    at = spawn_display_record(image, at, ((uint32_t)x << 16) | y, 0, sprite);
    spawn_free_rest_of_table(image, at);

    /* THE TWO STEPS ARE SEPARATE STATEMENTS ON PURPOSE. C does not order a call's arguments, so
     * `spawn_run_gate(image, script_byte(image, &script), script)` would leave it to the compiler
     * whether the gate is handed the cursor BEFORE or AFTER the gate byte advanced it — and the
     * whole mechanism is that it is handed the byte AFTER. */
    gate = script_byte(image, &script);
    spawn_run_gate(image, gate, script);

    index = script_byte(image, &script);
    wr32(image + WB_SPEECH_SCRIPT_CURSOR,
         bus_read_long(image, addr_add(WB_SPEECH_SCRIPT_TABLE,
                                       sign_ext16((uint16_t)(index * SCENE_TABLE_ENTRY_BYTES)))));
    image[WB_TEXT_REQUEST] = bus_read_byte(image, be32(image + WB_SPEECH_SCRIPT_CURSOR));
    wr16(image + WB_TEXT_LIFETIME_REQUEST, WB_SCENE_SPEECH_LIFETIME_HELD);
    wr32(image + WB_SPEECH_SCRIPT_CURSOR, be32(image + WB_SPEECH_SCRIPT_CURSOR) + 1);

    scene_clear_marker_pair(image, marker);
    map_stamp_block(image);

    scene_spawn_speech_tail(image);
}


/* --- kind 4, THE BOSS SCENE ($1ea8..$1f33) ----------------------------------------------------- */

/* Unlike the other two this one resets WB_ACTOR_TABLE_A32 and writes ONE record — the followed
 * actor's, slot 12 of that table — and it makes it a WB_SCENE_BOSS_FOLLOW_TYPE record, i.e. the
 * PLAYER's own behaviour slot, at a fixed position with a fixed pair of sizes.
 *
 * TWO DEAD COMPUTATIONS, both reproduced nowhere because no exit can observe them: the descriptor
 * word at +12 is loaded into d0 and never spent, and the `lsl.w #3,d0` three instructions before
 * the `lea` is overwritten by `move.w #$10,d0` before the index is used — so this arm always takes
 * WB_SCENE_BOSS_MAP_BANK_OFFSET whatever the descriptor says, where the other two follow the
 * descriptor's own word.
 *
 * IT TAKES NO CURSOR, because the original does not either: `movea.l $10420.l,a0 / lea 4(a0),a0`
 * RE-BUILDS the cursor out of a fresh read of the descriptor pointer rather than carrying on from
 * the head's a1. */
static void scene_spawn_boss(uint8_t *image, uint32_t marker) {
    uint32_t follow = WB_ACTOR_FOLLOWED_A32;
    uint32_t script, map, tiles;

    actor_table_reset(image, WB_ACTOR_TABLE_A32);

    wr16(image + follow + WB_ACTOR_SPRITE, 0);
    wr16(image + follow + WB_ACTOR_TYPE, WB_SCENE_BOSS_FOLLOW_TYPE);
    wr32(image + follow, WB_SCENE_BOSS_FOLLOW_XY);
    wr32(image + follow + WB_ACTOR_HALF_WIDTH, WB_SCENE_BOSS_FOLLOW_SIZES);

    /* `lea 4(a0),a0 / ... / lea 8(a0),a0`, so the pair read is the descriptor's words at +12
     * and +14. The FIRST of the two is dead, per the plate above; the read is kept because it is
     * what steps the cursor onto the second. */
    script = addr_add(be32(image + WB_RECORD_PTR_10420), WB_SCENE_KIND + 2 + 8);
    script_word(image, &script);
    image[WB_TEXT_REQUEST] = (uint8_t)script_word(image, &script);
    wr16(image + WB_TEXT_LIFETIME_REQUEST, WB_TEXT_LIFETIME_DEFAULT);

    scene_clear_marker_pair(image, marker);
    map_stamp_block(image);

    spawn_fetch_bank_and_freeze(image, WB_SCENE_BOSS_MAP_BANK_OFFSET, &map, &tiles);
    spawn_load_stage(image, map, spawn_start_record(WB_SCENE_START_RECORD_BOSS), tiles);
    wr16(image + WB_PANEL_FRAME_HOLD, 0);
    wr16(image + WB_STATE_FLAG_A32, WB_STATE_FLAG_SET);
}


/* --- $1cc0 and $1d1e: THE SHOP'S PRICE PLATES ---------------------------------------------------
 *
 * Two routines of their own — each has an `rts`, and each is reached only by `bsr.w` (twice, both
 * times from inside this tree) — that together draw a four-digit price into a SPRITE's bitmap.
 * They are $b850's packed-BCD digit plotter one tier over: the same WB_DIGIT_GLYPHS_ALT font, the
 * same WB_DIGIT_GLYPH_LEN, the same leading-zero latch, and the same four-plane 8-row glyph. What
 * differs is the destination — a masked sprite out of WB_RESOURCE_TABLE rather than the screen — so
 * the row is WB_GLYPH_STAMP_ROW_BYTES and the cell before each group of planes is a MASK word.
 */

/* The whole distance `glyph_stamp_8_rows` advances before it rewinds: the mask word it skips on
 * entry plus WB_DIGIT_ROWS rows. Named because BOTH `lea` rewinds are this minus a cell step. */
#define GLYPH_STAMP_SPAN  (WB_DIGIT_ROWS * WB_GLYPH_STAMP_ROW_BYTES + WB_GLYPH_STAMP_MASK_BYTES)

/* $1d1e — one 8-pixel glyph column into a masked sprite, and THE CURSOR FOR THE NEXT ONE, which is
 * what the two `lea` rewinds at the end are for and why this returns the original's a0.
 *
 * `lea 2(a0),a0` skips the group's mask word; the four plane bytes then go in two apart, and
 * `lea 14(a0),a0` steps to the next row — WB_GLYPH_STAMP_ROW_BYTES in all. Afterwards
 * `move.w a0,d7 / btst #0,d7` asks whether the CURSOR the caller handed in was even: an even one's
 * next cell is the odd byte of the same group, an odd one's is the next group's even byte. That is
 * bg_plot_banner_glyph's +1/+7 with a 10-byte group instead of an 8-byte one, which is the mask
 * word's whole width. */
uint32_t glyph_stamp_8_rows(uint8_t *image, uint32_t at, uint32_t glyph) {
    unsigned row, plane;

    at = addr_add(at, WB_GLYPH_STAMP_MASK_BYTES);
    for (row = 0; row < WB_DIGIT_ROWS; row++) {
        for (plane = 0; plane < WB_PLANES; plane++) {
            bus_write_byte(image, at, bus_read_byte(image, glyph));
            glyph = addr_add(glyph, 1);
            if (plane + 1 < WB_PLANES)
                at = addr_add(at, WB_GLYPH_STAMP_PLANE_STEP);
        }
        at = addr_add(at, WB_GLYPH_STAMP_ROW_SKIP);
    }
    return addr_add(at, ((at & 1) ? WB_GLYPH_STAMP_NEXT_ODD : WB_GLYPH_STAMP_NEXT_EVEN)
                        - (uint32_t)GLYPH_STAMP_SPAN);
}

/* $1cc0 — WB_SHOP_PRICE_DIGITS digits of one price into the resource `resource` names.
 *
 * `mulu.w #20,d7` picks the WB_RESOURCE_TABLE record and its first longword is the sprite's own
 * bitmap; `move.w 0(a1,d6.w),d0` reads the price out of WB_SHOP_RECORD_PTR at the caller's
 * displacement, which is WB_SHOP_ITEM1_PRICE or WB_SHOP_ITEM2_PRICE. Neither index is bounded — the
 * resource offset is a `mulu` result taken as a SIGN-EXTENDED word and the field displacement is a
 * word too — so both are reproduced wherever they land.
 *
 * `rol.w #4,d0` brings the TOP nibble down, so the digits are drawn most significant first, and a
 * nibble of zero before any nonzero one is drawn as WB_TEXT_GLYPH_TABLE's first glyph (the SPACE:
 * that font starts at character $20). d4 is the latch that ends the blanking, and it is
 * WB_DIGIT_SIGNIFICANT_SEEN's mechanism spelt in a register instead of a word. */
void shop_render_price_digits(uint8_t *image, uint16_t resource, uint16_t price_field) {
    uint32_t entry = addr_add(WB_RESOURCE_TABLE,
                              sign_ext16((uint16_t)(resource * WB_RESOURCE_RECORD_BYTES)));
    uint32_t at = bus_read_long(image, entry);
    uint16_t digits = bus_read_word(image, addr_add(be32(image + WB_SHOP_RECORD_PTR),
                                                    sign_ext16(price_field)));
    int significant = 0;
    unsigned n;

    for (n = 0; n < WB_SHOP_PRICE_DIGITS; n++) {
        uint16_t glyph_offset;

        digits = (uint16_t)((digits << WB_SHOP_PRICE_NIBBLE_BITS)
                            | (digits >> (16 - WB_SHOP_PRICE_NIBBLE_BITS)));
        glyph_offset = (uint16_t)((digits & 0xf) * WB_DIGIT_GLYPH_LEN);
        if (glyph_offset == 0 && !significant) {
            at = glyph_stamp_8_rows(image, at, WB_TEXT_GLYPH_TABLE);
            continue;
        }
        significant = 1;
        at = glyph_stamp_8_rows(image, at, addr_add(WB_DIGIT_GLYPHS_ALT, glyph_offset));
    }
}


/* --- kind 2, THE SHOP COUNTER ($1bb4..$1cbf, then $1d52..$1ea7) --------------------------------- */

/* The eight display records the counter is made of, in the order the arm writes them: the two items
 * at WB_SHOP_DISPLAY_ITEM1_XY / _ITEM2_XY showing the record's own two item sprites, the SIGN as a
 * two-record pair exactly like the speech arm's, the leave marker, the two price plates
 * shop_render_price_digits then draws into, and one more record whose WB_ACTOR_TYPE is the only one
 * of the eight the arm does not clear.
 *
 * EVERY FIELD IS READ WHERE THE ORIGINAL READS IT, and that is a claim about ORDER WITHIN a record
 * as well as across the eight. WB_SHOP_SIGN_XY, WB_SHOP_SIGN_SPRITE and WB_STAGE_NUMBER are each
 * read TWICE, once for each half of the sign pair; and every sprite field is read AFTER its own
 * record's xy and type are stored, because the records this loop writes are addresses a seeded
 * WB_SHOP_RECORD_PTR can name. An earlier draft here read the fields as call arguments, i.e. before
 * the stores, and test/test_scene.py's alias case is what refuted it. */
static uint32_t shop_build_display(uint8_t *image, uint32_t record) {
    uint32_t at = WB_ACTOR_TABLE_A30;
    uint32_t xy;
    uint16_t sprite;

    spawn_record_open(image, at, WB_SHOP_DISPLAY_ITEM1_XY, 0);
    at = spawn_record_close(image, at,
                            bus_read_word(image, addr_add(record, WB_SHOP_ITEM1_SPRITE)));
    spawn_record_open(image, at, WB_SHOP_DISPLAY_ITEM2_XY, 0);
    at = spawn_record_close(image, at,
                            bus_read_word(image, addr_add(record, WB_SHOP_ITEM2_SPRITE)));

    xy = bus_read_long(image, addr_add(record, WB_SHOP_SIGN_XY));
    spawn_record_open(image, at, xy, 0);
    sprite = bus_read_word(image, addr_add(record, WB_SHOP_SIGN_SPRITE));
    if (spawn_is_late_stage(image))
        sprite = WB_SCENE_LATE_STAGE_SPRITE;
    at = spawn_record_close(image, at, sprite);

    /* `move.l 50(a0),(a1) / addi.l #$400000,(a1)+` — a LONGWORD add, so the pair's second half is
     * WB_SCENE_SPAWN_PAIR_DX along in x with its y untouched, and `addq.w #1,(a1)+` bumps the
     * sprite in a WORD. Both of the record's fields are read a SECOND time here, and the sign
     * sprite's read again follows this record's own stores. */
    xy = bus_read_long(image, addr_add(record, WB_SHOP_SIGN_XY));
    spawn_record_open(image, at, xy + (WB_SCENE_SPAWN_PAIR_DX << 16), 0);
    sprite = bus_read_word(image, addr_add(record, WB_SHOP_SIGN_SPRITE));
    if (spawn_is_late_stage(image))
        sprite = WB_SCENE_LATE_STAGE_SPRITE;
    at = spawn_record_close(image, at, (uint16_t)(sprite + 1));

    at = spawn_display_record(image, at, WB_SHOP_DISPLAY_LEAVE_XY, 0,
                              WB_SHOP_DISPLAY_LEAVE_SPRITE);
    at = spawn_display_record(image, at, WB_SHOP_DISPLAY_PRICE1_XY, 0,
                              WB_SHOP_DISPLAY_PRICE1_SPRITE);
    at = spawn_display_record(image, at, WB_SHOP_DISPLAY_PRICE2_XY, 0,
                              WB_SHOP_DISPLAY_PRICE2_SPRITE);
    return spawn_display_record(image, at, WB_SHOP_DISPLAY_EXTRA_XY, WB_SHOP_DISPLAY_EXTRA_TYPE,
                                WB_SHOP_DISPLAY_EXTRA_SPRITE);
}

/* $1d52..$1ea7 — the tail the shop arm `bra.w`s into, and the only ending in this tree that is not
 * an `rts`.
 *
 * THE FIRST ARM IS THE REFUSAL. A counter whose sign is WB_SHOP_SIGN_SPRITE_INTRO, entered with
 * WB_BCD_COUNTER no greater than WB_SHOP_ITEM2_PRICE (a SIGNED word compare, so a purse of $8000 or
 * more reads negative and is refused too), posts WB_SHOP_BROKE_MSG_FIRST/_SECOND/_THIRD by
 * WB_SHOP_REFUSED_COUNT and bumps it — and a FOURTH refusal at the same counter reaches the
 * `illegal` at $1d8e, which is what this function reports rather than follows. Nothing resets that
 * word inside the tree, so the crash is the original's.
 *
 * The other arm is the ordinary entry greeting, off WB_SHOP_ENTER_COUNT and the record's own three
 * ids, and it is the one with a DEFAULT: `cmpi.w #$2,38(a0) / beq` falls through to the FIRST id, so
 * a count of 3 or more posts WB_SHOP_ENTER_MSG_FIRST again rather than crashing. */
static uint32_t shop_post_entry_message(uint8_t *image) {
    uint32_t record = be32(image + WB_SHOP_RECORD_PTR);
    uint16_t count;

    if (bus_read_word(image, addr_add(record, WB_SHOP_SIGN_SPRITE)) == WB_SHOP_SIGN_SPRITE_INTRO
        && (int16_t)be16(image + WB_BCD_COUNTER)
           <= (int16_t)bus_read_word(image, addr_add(record, WB_SHOP_ITEM2_PRICE))) {
        count = bus_read_word(image, addr_add(record, WB_SHOP_REFUSED_COUNT));
        if (count == 0)
            text_post_message_for(image, WB_SHOP_BROKE_MSG_FIRST, WB_TEXT_LIFETIME_DEFAULT);
        else if (count == 1)
            text_post_message_for(image, WB_SHOP_BROKE_MSG_SECOND, WB_TEXT_LIFETIME_DEFAULT);
        else if (count == 2)
            text_post_message_for(image, WB_SHOP_BROKE_MSG_THIRD, WB_TEXT_LIFETIME_DEFAULT);
        else
            return WB_SCENE_EXIT_ILLEGAL;
        wr16(image + WB_SCENE_MESSAGE_PENDING, WB_SCENE_MESSAGE_PENDING_SET);
        /* `addq.w #1,42(a0)` is a MEMORY read-modify-write, and it runs AFTER the post above and
         * after the pending word — so what it increments is not the `count` the message select
         * used. The two differ whenever the record overlaps one of those destinations, which a
         * seeded WB_SHOP_RECORD_PTR can arrange; the same shape as the +38 bump below. */
        bus_write_word(image, addr_add(record, WB_SHOP_REFUSED_COUNT),
                       (uint16_t)(bus_read_word(image,
                                                addr_add(record, WB_SHOP_REFUSED_COUNT)) + 1));
        wr16(image + WB_SCENE_ACK_WAIT, WB_SCENE_MESSAGE_PENDING_SET);
    } else {
        wr16(image + WB_SCENE_ACK_WAIT, WB_SCENE_MESSAGE_PENDING_SET);
        count = bus_read_word(image, addr_add(record, WB_SHOP_ENTER_COUNT));
        if (count == 1)
            text_post_message_for(image,
                               (uint8_t)bus_read_word(image,
                                                      addr_add(record, WB_SHOP_ENTER_MSG_SECOND)),
                               WB_TEXT_LIFETIME_DEFAULT);
        else if (count == 2)
            text_post_message_for(image,
                               (uint8_t)bus_read_word(image,
                                                      addr_add(record, WB_SHOP_ENTER_MSG_LATER)),
                               WB_TEXT_LIFETIME_DEFAULT);
        else
            text_post_message_for(image,
                               (uint8_t)bus_read_word(image,
                                                      addr_add(record, WB_SHOP_ENTER_MSG_FIRST)),
                               WB_TEXT_LIFETIME_DEFAULT);
    }

    /* `addq.w #1,38(a0)` is on BOTH paths, and on the refusal path the record pointer is the one
     * loaded at the top rather than a fresh read. */
    bus_write_word(image, addr_add(record, WB_SHOP_ENTER_COUNT),
                   (uint16_t)(bus_read_word(image, addr_add(record, WB_SHOP_ENTER_COUNT)) + 1));
    return WB_SCENE_EXIT_RETURN;
}

static uint32_t scene_spawn_shop(uint8_t *image, uint32_t script) {
    uint32_t entry, record, exit, map, tiles;
    uint16_t index, variant;

    actor_table_reset(image, WB_ACTOR_TABLE_A30);

    index = script_word(image, &script);
    entry = addr_add(WB_SHOP_RECORD_TABLE,
                     sign_ext16((uint16_t)(index * SCENE_TABLE_ENTRY_BYTES)));
    wr32(image + WB_SHOP_RECORD_PTR, bus_read_long(image, entry));
    record = bus_read_long(image, entry);

    spawn_free_rest_of_table(image, shop_build_display(image, record));

    shop_render_price_digits(image, WB_SHOP_DISPLAY_PRICE1_SPRITE, WB_SHOP_ITEM1_PRICE);
    shop_render_price_digits(image, WB_SHOP_DISPLAY_PRICE2_SPRITE, WB_SHOP_ITEM2_PRICE);

    exit = shop_post_entry_message(image);
    if (exit != WB_SCENE_EXIT_RETURN)
        return exit;

    spawn_fetch_bank_and_freeze(image, spawn_map_bank_offset(image), &map, &tiles);
    /* `movea.l $10420.l,a1 / tst.w 4(a1)` — a SECOND fresh read of the descriptor pointer, made
     * AFTER the freeze above, and the word it tests is WB_SCENE_VARIANT. */
    variant = bus_read_word(image, addr_add(be32(image + WB_RECORD_PTR_10420), WB_SCENE_VARIANT));
    spawn_load_stage(image, map,
                     spawn_start_record(variant != 0 ? WB_SCENE_START_RECORD_SHOP
                                                     : WB_SCENE_START_RECORD_SHOP_ALT),
                     tiles);
    wr16(image + WB_PANEL_FRAME_HOLD, WB_PANEL_FRAME_HOLD_SET);
    wr16(image + WB_STATE_FLAG_A30, WB_STATE_FLAG_SET);
    wr16(image + WB_SHOP_GREET_COUNTDOWN, WB_SHOP_GREET_COUNTDOWN_RESET);
    return WB_SCENE_EXIT_RETURN;
}


uint32_t scene_spawn_from_script(uint8_t *image) {
    uint32_t script = addr_add(be32(image + WB_RECORD_PTR_10420), WB_SCENE_KIND);
    uint32_t marker = be32(image + WB_SCENE_MARKER_CELL_PTR);
    uint16_t kind;

    wr16(image + WB_SCENE_SPAWN_GATE_SLOT, WB_ACTOR_FREE_MARKER);
    kind = script_word(image, &script);

    if (kind == WB_SCENE_KIND_SPEECH) {
        scene_spawn_speech(image, script, marker);
        return WB_SCENE_EXIT_RETURN;
    }
    if (kind == WB_SCENE_KIND_SHOP)
        return scene_spawn_shop(image, script);
    if (kind == WB_SCENE_KIND_BOSS_DEFEAT) {
        scene_spawn_boss(image, marker);
        return WB_SCENE_EXIT_RETURN;
    }
    /* THE LADDER'S FALL-THROUGH IS NOT A RETURN. $19ac's first instruction is `move.l a0,-(a7)` and
     * only the three arms end in the matching `movea.l (a7)+,a0`, so the `rts` at $19e0 pops the
     * SAVED a0 as its return address and leaves the caller's own on the stack. Nothing this port
     * does can stand in for a jump to a register the caller happened to hold, so the arm ends at
     * the report; the case sets `stop_pc` to $19e0. */
    return WB_SCENE_EXIT_WILD_RETURN;
}
