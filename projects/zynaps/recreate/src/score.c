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
 * THE FIRST `abcd`'s CARRY-IN IS THE 68000's X ON ENTRY, and it is an INPUT rather than a zero. The
 * two instructions before every `bsr` here are a `movem.l` and a `lea`, neither of which touches the
 * condition codes — but X SURVIVES them, so what reaches the first `abcd` is whatever the caller's
 * own arithmetic left. `mothership_segment_hit` (0x15222) is the measured case: it ends its
 * non-fatal arm on `subi.b #$1,(a5)`, whose BORROW sets X, and the frame loop's shoot sweep calls
 * this routine a few instructions later — one BCD unit high, and green for as long as this file
 * fabricated a 0. Returns the carry the LAST `abcd` produced, because that is the X the caller's own
 * next instruction sees.
 */
static unsigned bcd_add_longword(uint8_t *image, uint32_t augend_end, uint32_t addend_end,
                                 unsigned carry) {
    for (unsigned i = 0; i < SCORE_BCD_BYTES; i++) {
        /* `-(aN)`: one byte back, wrapping in 32 bits the way the address ALU does. */
        augend_end = addr_add(augend_end, -1u);
        addend_end = addr_add(addend_end, -1u);
        image[augend_end] = bcd_add_byte(image[augend_end], image[addend_end], &carry);
    }
    return carry;
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
unsigned score_add_bcd(uint8_t *image, uint32_t award_end, unsigned extend_in) {
    uint32_t threshold;
    unsigned carry = bcd_add_longword(image, A_player_score_bcd + SCORE_BCD_BYTES, award_end,
                                      extend_in);

    threshold = be32(image + A_extra_life_threshold_bcd);
    /* `cmp.l` sets no X, so the four `abcd`s above are still the last thing that touched it. */
    if ((int32_t)threshold > (int32_t)be32(image + A_player_score_bcd))
        return carry;
    sound_start(image, EXTRA_LIFE_SOUND, (uint8_t)threshold);
    /* THE SECOND CHAIN'S CARRY-IN IS `sound_start`'s OUTGOING X, not this routine's own — `moveq
     * #$10,d1` at 0x12e14 leaves X alone and the `bsr` at 0x12e16 does not. include/sound.h's
     * `sound_start_leaves_extend` is that one bit, derived from the tune id the call was made with. */
    bcd_add_longword(image, A_extra_life_threshold_bcd + SCORE_BCD_BYTES,
                     A_extra_life_threshold_step_bcd + SCORE_BCD_BYTES,
                     sound_start_leaves_extend(EXTRA_LIFE_SOUND));
    /* `addi.b #$1,$1991a` at 0x12e2e is the last instruction on this arm that touches X — the
     * `bset` after it does not — so the routine's outgoing X is that byte's CARRY OUT
     * (machine.h's `byte_add_extend`, the kit's one model of what a byte add leaves in the flag). */
    unsigned lives_carried = byte_add_extend(image[A_lives], 1);

    image[A_lives]++;
    image[A_panel_redraw_mask] |= (uint8_t)(1u << PANEL_REDRAW_LIVES_BIT);
    return lives_carried;
}

/* Register map: A1 = one past the last byte of the four-byte BCD award. It comes back four bytes
 * lower (the `-(a1)` chain exhausted) but no call site reads it — every one reloads A1 with its own
 * `lea` — so only memory is compared.
 *
 * `extend_in` is the 68000's X on entry, which no register carries: a case drives it through
 * `test/abi.py`'s `extend_call_pokes` stub with `extend_in=1`, or through an ordinary entry
 * (X = 0, the oracle's own SR), and the two must agree with what is passed here. The RETURN is
 * this routine's outgoing X, which no memory records either — the same stub reads the oracle's,
 * with `addx.b` into a reported register. */
uint32_t g_score_add_bcd(uint8_t *image, uint32_t award_end, uint32_t extend_in) {
    return score_add_bcd(image, award_end, extend_in);
}
