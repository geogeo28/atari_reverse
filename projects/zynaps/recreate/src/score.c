/* score.c — adding to the packed-BCD score, and the extra life it can award.
 *
 * `score_add_bcd` @ 0x12df6 is the one way the score moves: every scoring site loads A1 with a
 * pointer one past its award in the table and calls here. Eight `abcd`s and a signed longword
 * compare; the interesting part is that both operands are walked BACKWARDS from their ends.
 */
#include "machine.h"
#include "score.h"
#include "hud.h"
#include "sound.h"

/* ONE 68000 `abcd`: a decimal add of two bytes and the X flag.
 *
 * The correction order is the instruction's — the low nibbles and the carry-in first, +6 if that
 * came out above 9, then the high nibbles, and a sum above 0x99 wraps by 0xa0 and carries out.
 * For the valid BCD the score tables hold this is the schoolbook decimal add and any order agrees;
 * the order only shows on a nibble above 9, which nothing the game adds has (test_score.py drives
 * those anyway, since the oracle is the authority on them and not this comment).
 */
static uint8_t bcd_add_byte(uint8_t augend, uint8_t addend, unsigned *carry) {
    unsigned sum = (augend & 0xfu) + (addend & 0xfu) + *carry;

    if (sum > 9u)
        sum += 6u;
    sum += (augend & 0xf0u) + (addend & 0xf0u);
    *carry = sum > 0x99u;
    if (*carry)
        sum -= 0xa0u;
    return (uint8_t)sum;
}

/* `abcd -(a1),-(a0)` SCORE_BCD_BYTES times: both pointers start one past their value's last byte
 * and step back together, so the add runs least-significant byte first and the carry rides up.
 *
 * THE CARRY STARTS CLEAR, and that is the harness's answer rather than the game's. The 68000's X
 * flag on entry is whatever the caller last left it as, and no caller of this routine sets it —
 * every one of the eight call sites reaches the `bsr` through `movem.l` and `lea`, neither of which
 * touches the condition codes. The oracle enters every routine with SR = 0x2700 (shim.c's
 * ENTRY_SR), so X = 0 is what the differential compares against; on the real machine an entry with
 * X set would add one extra point. STATUS.md carries that as a residual.
 */
static void bcd_add_longword(uint8_t *image, uint32_t augend_end, uint32_t addend_end) {
    unsigned carry = 0;

    for (unsigned i = 0; i < SCORE_BCD_BYTES; i++) {
        /* `-(aN)`: one byte back, wrapping in 32 bits the way the address ALU does. */
        augend_end = addr_add(augend_end, -1u);
        addend_end = addr_add(addend_end, -1u);
        image[augend_end] = bcd_add_byte(image[augend_end], image[addend_end], &carry);
    }
}

/* Add the four-byte BCD value ending at `award_end` to the score, and award a life if that put the
 * score at or past the threshold.
 *
 * THE THRESHOLD TEST IS A SIGNED LONGWORD COMPARE of two BCD values, so a score whose top digit
 * reaches 8 reads as negative and stops awarding lives — 80000000 in BCD is 0x80000000. The game
 * ships the threshold at 10000 and the step at 20000, and eight digits of score run out long before
 * that, so the arm is real but unreachable from the game's own data.
 *
 * The channel handed to `sound_start` is D0, which at that point still holds the threshold longword
 * the compare was made with — nothing sets it deliberately. It is DEAD in the shipped binary: tune
 * 0x10 opens with its own `fa 04` header, so `sound_start` overwrites the channel before using it.
 * Passed on because that is what the instruction stream does.
 */
void score_add_bcd(uint8_t *image, uint32_t award_end) {
    uint32_t threshold;

    bcd_add_longword(image, A_player_score_bcd + SCORE_BCD_BYTES, award_end);
    threshold = be32(image + A_extra_life_threshold_bcd);
    if ((int32_t)threshold > (int32_t)be32(image + A_player_score_bcd))
        return;
    sound_start(image, EXTRA_LIFE_SOUND, (uint8_t)threshold);
    bcd_add_longword(image, A_extra_life_threshold_bcd + SCORE_BCD_BYTES,
                     A_extra_life_threshold_step_bcd + SCORE_BCD_BYTES);
    image[A_lives]++;
    image[A_panel_redraw_mask] |= (uint8_t)(1u << PANEL_REDRAW_LIVES_BIT);
}

/* Register map: A1 = one past the last byte of the four-byte BCD award. It comes back four bytes
 * lower (the `-(a1)` chain exhausted) but no call site reads it — every one reloads A1 with its own
 * `lea` — so only memory is compared. */
void g_score_add_bcd(uint8_t *image, uint32_t award_end) {
    score_add_bcd(image, award_end);
}
