/* actor.c — the followed actor's record ($67e0), the two tests above it ($67c2, $67f8) and the two
 * passes that project actor records into screen coordinates ($8dfe, $8e66).
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
 * test/test_actor.py asserts the ORACLE's against a model instead.
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
        return WB_ACTOR_TA30;
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
