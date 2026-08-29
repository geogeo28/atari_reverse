/* score.h — the packed-BCD score and the extra-life award (src/score.c). Subsystem: score.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 *
 * FOUR LONGWORDS IN A ROW, and the routine reaches every one of them by walking BACKWARDS off the
 * end of the one before: `abcd -(a1),-(a0)` takes both operands one past their last byte. So the
 * addresses below are adjacent by design, not by accident, and the code spells each end as
 * `<name> + SCORE_BCD_BYTES` rather than as the next value's address — which would read as though it
 * were touching the next value.
 *
 *   0x195d8  extra_life_threshold_bcd       the score that awards the next life
 *   0x195dc  extra_life_threshold_step_bcd  what the threshold grows by afterwards
 *   0x195e0  player_score_bcd               the live player's score
 *   0x195e4  score_award_table_bcd          four awards; a caller passes ONE PAST the one it wants
 */
#ifndef ZYNAPS_SCORE_H
#define ZYNAPS_SCORE_H

#include <stdint.h>

/* The first three carry ../names.txt's `# ctx` tag — the names come from the call sites rather than
 * from a body read of anything that produces them, so a later reading may overturn them.
 * `A_player_score_bcd` is names.txt's SECOND reading of 0x195e0 (its first is the bare `score`);
 * spelt the long way here because `score` alone does not say the bytes are packed BCD. */
#define A_extra_life_threshold_bcd      0x195d8u  /* # ctx: also read as next_extra_life_score */
#define A_extra_life_threshold_step_bcd 0x195dcu  /* # ctx */
#define A_player_score_bcd              0x195e0u  /* # ctx: names.txt's first reading is `score` */
#define A_score_award_table_bcd         0x195e4u

#define SCORE_BCD_BYTES 4u   /* four `abcd`s — an eight-digit score, which is what the HUD draws */
#define SCORE_AWARDS    4u   /* the table's entries: 50, 100, 250 and 1000 in the shipped .PRG */

/* `moveq #$10,d1` before the `bsr` to sound_start — the extra-life jingle. NOT spelt `SOUND_*`:
 * that prefix is `include/sound.h`'s (SOUND_CMD_*, SOUND_CHANNEL_*, SOUND_ROW_*), and a tune id
 * named into it from here would collide by NAME the day the sound subsystem lists its own ids —
 * which is the one duplicate `test_constants.py` does catch, suite-wide. */
#define EXTRA_LIFE_SOUND 0x10u

/* `extend_in` is the 68000's X flag at the `bsr`, which the first `abcd` ADDS; the return value is
 * the X this routine leaves, which its caller's next `abcd` will add in turn. Neither is a register,
 * so neither reaches the image diff — `test/abi.py`'s `extend_call_pokes` drives the input
 * (`extend_in=1`) and reads the output, and src/score.c has the measured defect that made the flag
 * an input rather than a fabricated 0. */
unsigned score_add_bcd(uint8_t *image, uint32_t award_end, unsigned extend_in);

#endif /* ZYNAPS_SCORE_H */
