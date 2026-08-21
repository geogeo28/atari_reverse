/* game.c — THE SPINE. What the frame loop itself is made of; why it is a module of its own, and
 * why it could not be written before the kit's scheduled-write model, is in ../include/game.h.
 *
 * Both routines here read WB_KEY_LAST_SCANCODE, the byte the IKBD ACIA handler ($754) stores on
 * every keypress and every release. Two of the reads are BUSY-WAITS on a value that byte only takes
 * when the interrupt writes it, and those two — and only those two — go through `sched_poll8`.
 * Every other read of the same address is an ordinary guarded read: `$642` tests the PRESS code
 * before the wait below it, at the same address, and is not a poll.
 */
#include "game.h"

#include "bus.h"
#include "sound.h"
#include "wonderboy.h"

#include "sched.h"     /* the kit's external-agent model — the two waits below, off target only */

/* Wait on WB_KEY_LAST_SCANCODE until it reads `code` — the shape both of this module's spins have.
 *
 * It goes through the kit's `sched_wait8` rather than a `while (bus_read_byte(...))` because the
 * POLL is what the differential counts (tools/recreate_kit/include/sched.h): the oracle counts
 * arrivals at the original's compare and this side counts polls, one per iteration, and the harness
 * compares the two. The capped form is the one to reach for — an uncapped loop turns a case whose
 * schedule never releases the wait into a HUNG suite, which decides nothing.
 *
 * RETURNS 0 WHEN THE WAIT WAS NEVER RELEASED, and every caller returns immediately on that: the
 * model has refused, the harness is about to throw the case away, and carrying on as though the
 * byte had arrived would run the payload on a state the original never reached. On target this is
 * an ordinary uncapped spin and the ACIA interrupt is what ends it. */
static int wait_for_scancode(uint8_t *image, uint8_t code) {
    return sched_wait8(image, WB_KEY_LAST_SCANCODE, code);
}

/* $60e — game_key_actions' PAUSE arm, reached by `beq.w` from $57c and ending in its own `rts`.
 *
 * It is not a routine (nothing calls $60e) and so has no `fn` of its own in ../names.txt; it is a
 * function here because the wait plus the four stores are one act, and because the unpause payload
 * next door is its mirror image. Wait for the pause key's release, forget the scancode, raise the
 * pause flag, and post the pause message with a lifetime of zero.
 *
 * THE LIFETIME STORE IS A BYTE over a WORD. `move.b #$0,$c034.l` at $62e clears only the HIGH byte
 * of WB_TEXT_LIFETIME_REQUEST, leaving the low one as it found it — so a paused box inherits the
 * bottom half of whatever lifetime was last posted. Reproduced as the byte store it is. */
static void pause_the_game(uint8_t *image) {
    if (!wait_for_scancode(image, WB_KEY_SCANCODE_P_RELEASE))
        return;
    image[WB_KEY_LAST_SCANCODE] = 0;
    wr16(image + WB_GAME_PAUSED, WB_GAME_PAUSED_SET);
    image[WB_TEXT_REQUEST] = WB_PAUSE_MESSAGE_ID;
    image[WB_TEXT_LIFETIME_REQUEST] = 0;
}

/* $5a8..$5ce — one step of the cheat sequence walk, reached only while WB_KEY_SEQUENCE_MATCHED is
 * still clear. Returns non-zero when the walk hit the terminator, which is the arm that RAISES the
 * cheat and returns from the whole routine without running the Help block below.
 *
 * The index is `move.b (a0,d0.w),d1` over `move.w $606.l,d0`: a SIGNED word index off the sequence's
 * base, so a cursor past $7fff would read BELOW the table rather than far above it. NO REACHABLE
 * CURSOR DOES — the walk steps only while the byte at it matches, and the byte at index 4 is the
 * terminator, which raises the cheat and returns without stepping; a raised cheat then
 * short-circuits the walk for ever, so the range is 0..4. The signedness is reproduced because it
 * is the instruction's, and test_game.py drives it on a declared-fabricated seed which says so. */
static int cheat_sequence_step(uint8_t *image) {
    int16_t cursor = (int16_t)bus_read_word(image, WB_KEY_SEQUENCE_CURSOR);
    uint8_t wanted = bus_read_byte(image, addr_add(WB_KEY_SEQUENCE_SCANCODES, (uint32_t)(int32_t)cursor));

    if (wanted == WB_KEY_SEQUENCE_TERMINATOR) {
        wr16(image + WB_KEY_SEQUENCE_MATCHED, WB_KEY_SEQUENCE_MATCHED_SET);
        return 1;
    }
    if (wanted == image[WB_KEY_LAST_SCANCODE])
        wr16(image + WB_KEY_SEQUENCE_CURSOR, (uint16_t)(cursor + 1));
    return 0;
}

/* $5d0..$5f8 — the cheat's SECOND action: while the cheat is enabled, Help flips bit 3 of
 * WB_EFFECT_STATE_BD6A's low byte. The `bchg` is a byte read-modify-write however the original
 * spells the address, and it happens only after the key is RELEASED — the second of this module's
 * two waits. */
static void cheat_help_action(uint8_t *image) {
    if (!bus_read_word(image, WB_KEY_SEQUENCE_MATCHED))
        return;
    if (image[WB_KEY_LAST_SCANCODE] != WB_KEY_SCANCODE_HELP)
        return;
    if (!wait_for_scancode(image, WB_KEY_SCANCODE_HELP_RELEASE))
        return;
    image[WB_EFFECT_STATE_BD6A_LOW] ^= (uint8_t)(1u << WB_EFFECT_STATE_BD6A_CHEAT_BIT);
}

uint32_t game_key_actions(uint8_t *image) {
    /* $53e. The round-end request outranks every key: the sequence at $e032 raised it when the
     * bonus countdown finished, and this is what acts on it. */
    if (bus_read_word(image, WB_ROUND_END_RELOAD_REQUEST)) {
        wr16(image + WB_ROUND_END_RELOAD_REQUEST, 0);
        return WB_KEY_ACTIONS_ROUND_END;
    }
    /* $556. N with the cheat on skips the level — the same unwind, and it leaves the request word
     * alone because there was none. */
    if (bus_read_word(image, WB_KEY_SEQUENCE_MATCHED)
            && image[WB_KEY_LAST_SCANCODE] == WB_KEY_SCANCODE_N)
        return WB_KEY_ACTIONS_LEVEL_SKIP;
    /* $574. */
    if (image[WB_KEY_LAST_SCANCODE] == WB_KEY_SCANCODE_P) {
        pause_the_game(image);
        return WB_KEY_ACTIONS_RETURNED;
    }
    /* $580. */
    if (image[WB_KEY_LAST_SCANCODE] == WB_KEY_SCANCODE_ESC) {
        snd_start_fadeout(image);
        return WB_KEY_ACTIONS_QUIT;
    }
    /* $59e. The walk runs only while the cheat is still OFF, and its terminator arm returns at once
     * — so the frame that completes the sequence does not also run the Help action below. */
    if (!bus_read_word(image, WB_KEY_SEQUENCE_MATCHED) && cheat_sequence_step(image))
        return WB_KEY_ACTIONS_RETURNED;
    cheat_help_action(image);
    return WB_KEY_ACTIONS_RETURNED;
}

/* $638. The mirror of pause_the_game: it exists to undo it, and the two spin on the same byte for
 * the same code. Nothing happens unless the game is paused AND the pause key is still held — the
 * `cmpi.b #$19,$879.l` at $642 is a plain read of the byte the wait below then polls. */
void game_unpause_on_key_release(uint8_t *image) {
    if (!bus_read_word(image, WB_GAME_PAUSED))
        return;
    if (image[WB_KEY_LAST_SCANCODE] != WB_KEY_SCANCODE_P)
        return;
    if (!wait_for_scancode(image, WB_KEY_SCANCODE_P_RELEASE))
        return;
    image[WB_KEY_LAST_SCANCODE] = 0;
    wr16(image + WB_GAME_PAUSED, 0);
    image[WB_TEXT_REQUEST] = WB_TEXT_REQUEST_DISMISS;
}
