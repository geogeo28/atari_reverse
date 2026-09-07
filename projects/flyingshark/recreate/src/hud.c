/* hud.c — the score, the hall of fame, the readouts they feed, and the console leftovers.
 *
 * The subsystem's shape is argued in include/hud.h; this file is the code. Everything here is
 * arithmetic over the flat image — the display list these routines fill is data the renderer walks
 * a frame later, so not one of them touches a pixel.
 *
 * THE GLUE'S REGISTER MAP is on the `g_*` wrapper, one line each. This game is hand-written 68000
 * with a register ABI throughout, so most cores take their arguments as plain values and the glue
 * is what names which register carried each.
 */
#include "machine.h"
#include "os.h"
#include "sched.h"
#include "common.h"  /* SCC_TRUE, addr_sub, const_word and display_record_write */
#include "hud.h"
#include "player.h"  /* the player record and the counters the icon rows draw */

/* =================================================================================================
 * The score: packed BCD, and the nine awards that move it
 * ============================================================================================== */

/* ONE 68000 `abcd`: a decimal add of two bytes and the X flag.
 *
 * The correction order is the instruction's — the low nibbles and the carry-in first, +6 if that
 * came out above 9, then the high nibbles, and a sum above 0x99 wraps by 0xa0 and carries out. For
 * the valid BCD this game's award table holds, that is the schoolbook decimal add and any order
 * agrees; the order only shows on a nibble above 9, which test_hud.py drives anyway because the
 * oracle rather than this comment is the authority on them.
 */
static uint8_t bcd_add_byte(uint8_t augend, uint8_t addend, unsigned *carry) {
    unsigned sum = (augend & 0x0fu) + (addend & 0x0fu) + *carry;

    if (sum > 9u)
        sum += 6u;
    sum += (augend & 0xf0u) + (addend & 0xf0u);
    *carry = sum > 0x99u;
    if (*carry)
        sum -= 0xa0u;
    return (uint8_t)sum;
}

/* `abcd -(a1),-(a0)` three times @ 0x10bf2..0x10bf6: add the three BCD bytes ending at `value_end`
 * into the score.
 *
 * BOTH POINTERS START ONE PAST THEIR VALUE and step back together, so the add runs least-significant
 * byte first and the carry rides up. The accumulator's end is `A_hiscore_bcd` and that is not a
 * coincidence in the data either: the hi-score sits immediately above the score, so the routine's
 * own `lea $15a2d,a0` names it.
 *
 * THE FIRST `abcd`'s CARRY-IN IS THE 68000's X ON ENTRY, and it is an INPUT rather than a zero. The
 * two instructions before every `bsr` here are a `movem.l` and a `lea`, neither of which touches the
 * condition codes — so what reaches the first `abcd` is whatever the CALLER's own arithmetic left.
 * Returns the carry the last `abcd` produced, which is the X the caller's next instruction sees.
 *
 * THE SCORE WRAPS AT 999999 rather than saturating: the carry out of the top byte is discarded, so
 * an award past six digits rolls the display over. Reproduced, not repaired.
 */
unsigned score_add_bcd(uint8_t *image, uint32_t value_end, unsigned extend_in) {
    uint32_t score_end = A_score_bcd + SCORE_BCD_BYTES;
    unsigned carry = extend_in;

    for (unsigned byte = 0; byte < SCORE_BCD_BYTES; byte++) {
        /* `-(aN)`: one byte back, wrapping in 32 bits the way the address ALU does. */
        score_end = addr_sub(score_end, 1u);
        value_end = addr_sub(value_end, 1u);
        image[score_end] = bcd_add_byte(image[score_end], image[value_end], &carry);
    }
    return carry;
}

/* The nine award wrappers @ 0x10b28, 0x10b3c, ... 0x10bb4 and 0x10bd8, which differ only in the
 * `lea` that picks the value. Each names the address ONE PAST its own three bytes, because that is
 * where `score_add_bcd` starts walking backwards from — so award n's `lea` is the START of award
 * n+1, and `score_add_50`'s operand 0x15a33 is `score_value_100`'s address.
 *
 * The `movem.l #$00c0,-(a7)` each opens with saves A0 and A1 and neither touches the condition
 * codes, so the X the wrapper was entered with is still the one the first `abcd` adds.
 */
unsigned score_add_award(uint8_t *image, unsigned award, unsigned extend_in) {
    uint32_t value_end = A_score_award_values + (award + 1u) * SCORE_BCD_BYTES;

    return score_add_bcd(image, value_end, extend_in);
}

/* `bcd3_to_digits` @ 0x10b04: three packed-BCD bytes -> six glyph ids, high nibble first.
 *
 * Adding GLYPH_ZERO to each nibble is the whole of the conversion, and it is why the alphabet's '0'
 * is 0xc5. The add is a `.b`, so a nibble is never anything but 0..15 and the result never leaves
 * the digit run — a nibble above 9 (which valid BCD has none of) simply lands past '9'.
 */
void bcd3_to_digits(uint8_t *image, uint32_t bcd, uint32_t digits) {
    for (unsigned byte = 0; byte < SCORE_BCD_BYTES; byte++) {
        uint8_t packed = image[addr_add(bcd, byte)];

        image[addr_add(digits, 2u * byte)] = (uint8_t)((packed >> 4) + GLYPH_ZERO);
        image[addr_add(digits, 2u * byte + 1u)] = (uint8_t)((packed & 0x0fu) + GLYPH_ZERO);
    }
}

/* `scores_bcd_to_chars` @ 0x10ae4: both readouts at once. */
void scores_bcd_to_chars(uint8_t *image) {
    bcd3_to_digits(image, A_score_bcd, A_score_digits);
    bcd3_to_digits(image, A_hiscore_bcd, A_hiscore_digits);
}

/* `clear_3_bytes` @ 0x1162e: `clr.b (a0)+` three times. `score_reset` is its only caller. */
void clear_3_bytes(uint8_t *image, uint32_t dest) {
    for (unsigned byte = 0; byte < SCORE_BCD_BYTES; byte++)
        image[addr_add(dest, byte)] = 0;
}

/* `score_reset` @ 0x11616: zero the BCD score and stamp its LAST digit glyph back to '0'.
 *
 * The other five digit glyphs are deliberately left alone — the next `scores_bcd_to_chars` rewrites
 * them all — but the sixth is what `hud_blank_leading_zeros` stops at, so it has to read as a digit
 * for the readout to show anything at all before the first award.
 */
void score_reset(uint8_t *image) {
    clear_3_bytes(image, A_score_bcd);
    image[A_score_digits + SCORE_DIGITS - 1u] = GLYPH_ZERO;
}

/* `format_5_digits` @ 0x14a76: five ASCII '0's forward from `field_start`, then the value's decimal
 * digits written BACKWARDS over them.
 *
 * ../names.txt calls the parameter `field_end`, and the entry value is the field's START: the five
 * `move.b #$30,(a0)+` are what leave A0 at the end, and only then does the `move.b d0,-(a0)` loop
 * begin. Returns where A0 stopped, which is the field's start plus the leading zeros left standing.
 *
 * THE VALUE IS 16 BITS, not 32: `swap / clr.w / swap` @ 0x14a8a throws the high word away before the
 * first divide, so a caller handing this a longword — `debug_show_counters` hands it a pointer
 * difference — gets that difference modulo 65536. Five digits is exactly enough for what is left.
 */
uint32_t format_5_digits(uint8_t *image, uint32_t field_start, uint32_t value) {
    uint32_t cursor = field_start;
    uint16_t remaining = (uint16_t)value;

    for (unsigned digit = 0; digit < FORMAT_DIGITS; digit++)
        image[addr_add(cursor, digit)] = ASCII_ZERO;
    cursor = addr_add(cursor, FORMAT_DIGITS);
    while (remaining != 0) {
        uint8_t digit = (uint8_t)(remaining % FORMAT_RADIX);

        cursor = addr_sub(cursor, 1u);
        image[cursor] = (uint8_t)(ASCII_ZERO + digit);
        remaining = (uint16_t)(remaining / FORMAT_RADIX);
    }
    return cursor;
}

/* =================================================================================================
 * Comparing scores: the hall-of-fame test and the extra life
 * ============================================================================================== */

/* `digits6_compare` @ 0x108f8: six glyphs at `*score` against the six at `*entry + 16`.
 *
 * `cmpm.b (a5)+,(a6)+` compares DESTINATION minus SOURCE, so the answer is about the SCORE: +1 at
 * the first digit where the score is higher, -1 at the first where it is lower — and -1 again when
 * all six are equal, because the `dbf` falls out into the same `move.w #$ffff,d0`. A tie therefore
 * does NOT take a hall-of-fame row, and does not award an extra life.
 *
 * THE COMPARE IS SIGNED. `blt`/`bgt` read the byte as two's complement, and every glyph in the
 * digit run is 0xc5 or above — negative. Among digits that changes nothing, because the whole run
 * is negative and the ordering within it survives. It decides the one case where the operands are
 * NOT both digits: `game_over_hiscore_check`'s rank walk runs off the bottom of the hall-of-fame
 * table into the front end's own text, whose bytes are small and POSITIVE, and the signed compare
 * is what makes the score read as LOWER there and stops the walk after a single step off the end.
 *
 * Both cursors are advanced past the digits they compared, and the callers rely on it: the entry
 * pointer arrives 16 bytes BELOW the row so that this routine's own `lea 16(a5),a5` lands it on the
 * score field (`award_extra_life` subtracts exactly that much before calling).
 *
 * The answer is a WORD — `move.w #$ffff,d0` leaves the caller's high half alone — and every caller
 * tests it with `tst.w`.
 */
uint16_t digits6_compare(uint8_t *image, uint32_t *entry, uint32_t *score) {
    uint32_t entry_digits = addr_add(*entry, HISCORE_SCORE);

    for (unsigned digit = 0; digit < SCORE_DIGITS; digit++) {
        uint8_t from_entry = image[entry_digits];
        uint8_t from_score = image[*score];

        entry_digits = addr_add(entry_digits, 1u);
        *score = addr_add(*score, 1u);
        if (from_score != from_entry) {
            *entry = entry_digits;
            return (int8_t)from_score > (int8_t)from_entry ? DIGITS_COMPARE_HIGHER
                                                           : DIGITS_COMPARE_LOWER_OR_EQUAL;
        }
    }
    *entry = entry_digits;
    return DIGITS_COMPARE_LOWER_OR_EQUAL;
}

/* `check_beat_hiscore` @ 0x10a2a: raise `hiscore_beaten` the moment the score passes the hi-score.
 *
 * Its own digit walk rather than `digits6_compare`'s, and it stops at the first digit that differs
 * either way — a lower digit simply returns. `bgt`/`blt` again, so the compare is SIGNED, and again
 * that only shows on a byte outside the digit run. The flag is set with `st`, a BYTE store into a
 * word the readout then reads with `tst.w`, so only the high byte of `hiscore_beaten` ever moves.
 */
void check_beat_hiscore(uint8_t *image) {
    for (unsigned digit = 0; digit < SCORE_DIGITS; digit++) {
        int8_t from_score = (int8_t)image[A_score_digits + digit];
        int8_t from_hiscore = (int8_t)image[A_hiscore_digits + digit];

        if (from_score > from_hiscore) {
            image[A_hiscore_beaten] = SCC_TRUE;   /* `st $176e4` */
            return;
        }
        if (from_score < from_hiscore)
            return;
    }
}

/* `award_extra_life` @ 0x110d4: one life at each of the seven bonus thresholds, once each.
 *
 * The seven arms are spelt out in the original, each testing its own flag word and falling through
 * to the next when it is already set — so the routine grants the FIRST unclaimed threshold the score
 * has reached and no more, and a score that jumps two of them in one award collects the second on a
 * later call. With every flag set it returns without comparing anything at all.
 *
 * RETURNS whether the original would tail-call the sound module. The last instruction of the award
 * arm is `bra.w $121e6`, the sfx wrapper — an exit, not a call, so everything this routine does to
 * the image is already done when it is taken. The differential checkpoints there (test_hud.py), and
 * the sound trigger itself belongs to the sound subsystem.
 */
unsigned award_extra_life(uint8_t *image) {
    uint32_t score = A_score_digits;
    uint32_t threshold_row;
    uint32_t flag;
    unsigned row;

    bcd3_to_digits(image, A_score_bcd, A_score_digits);
    for (row = 0; row < BONUS_LIFE_THRESHOLDS; row++) {
        flag = A_bonus_life_awarded_0 + row * BONUS_LIFE_FLAG_BYTES;
        if (be16(image + flag) == 0)
            break;
    }
    if (row == BONUS_LIFE_THRESHOLDS)
        return 0;

    /* `suba.l #$10,a5` @ 0x11184, undone by `digits6_compare`'s own `lea 16(a5),a5`. */
    threshold_row = addr_sub(A_bonus_life_thresholds + row * SCORE_DIGITS, HISCORE_SCORE);
    if (digits6_compare(image, &threshold_row, &score) == DIGITS_COMPARE_LOWER_OR_EQUAL)
        return 0;

    wr16(image + A_lives, (uint16_t)(be16(image + A_lives) + 1u));
    wr16(image + flag, BONUS_LIFE_AWARDED);
    return 1;
}

/* =================================================================================================
 * The readouts: display-list slots the renderer walks
 * ============================================================================================== */

/* One six-byte slot: `move.w d1,(a1)+ / move.w d2,(a1)+ / move.b (a0)+,(a1)+ / move.b #$1,(a1)+`. */
static void publish_slot(uint8_t *image, uint32_t slot, uint16_t x, uint16_t y, uint8_t glyph) {
    display_record_write(image, slot, x, y, glyph, DISPLAY_ACTIVE_ON_TOP);
}

/* `hud_publish_digit_row` @ 0x10a90: five digit slots stepping x by 8, then a sixth forced to '0'.
 *
 * THE SIXTH SLOT IS A LITERAL, not the sixth glyph of the row — which is why every score on screen
 * ends in a zero, and why only five of the six digits the BCD holds are ever readable. The tail
 * block also differs in the last store: `move.b #$1,(a1)` without the postincrement, so A1 comes to
 * rest one byte short of the row's end.
 */
void hud_publish_digit_row(uint8_t *image, uint32_t chars, uint32_t slots, uint32_t x, uint32_t y) {
    uint16_t column = (uint16_t)x;

    for (unsigned slot = 0; slot < HUD_DIGIT_SLOTS - 1u; slot++) {
        publish_slot(image, addr_add(slots, slot * DISPLAY_REC_BYTES), column, (uint16_t)y,
                     image[addr_add(chars, slot)]);
        column = (uint16_t)(column + HUD_DIGIT_X_STEP);
    }
    publish_slot(image, addr_add(slots, (HUD_DIGIT_SLOTS - 1u) * DISPLAY_REC_BYTES), column,
                 (uint16_t)y, GLYPH_ZERO);
}

/* `hud_build_score_digits` @ 0x10a50: the score readout, then the hi-score readout.
 *
 * Once `hiscore_beaten` is up the SECOND readout is fed from the score too, so both halves of the
 * bar show the same number for the rest of the game. `hiscore_beaten` is tested as a word although
 * `check_beat_hiscore` only ever writes its high byte.
 */
void hud_build_score_digits(uint8_t *image) {
    uint32_t hiscore_source = be16(image + A_hiscore_beaten) != 0 ? A_score_digits
                                                                 : A_hiscore_digits;

    hud_publish_digit_row(image, A_score_digits, A_hud_score_slots, HUD_SCORE_X, HUD_DIGIT_Y);
    hud_publish_digit_row(image, hiscore_source, A_hud_hiscore_slots, HUD_HISCORE_X, HUD_DIGIT_Y);
}

/* `hud_blank_leading_zeros_row` @ 0x10ac8: clear the enable byte of every leading '0'.
 *
 * It walks at most five slots and stops at the first glyph that is not '0', so the sixth — the
 * literal zero `hud_publish_digit_row` forces — is never blanked and a score of nothing still shows
 * one digit.
 */
void hud_blank_leading_zeros_row(uint8_t *image, uint32_t slots) {
    for (unsigned slot = 0; slot < HUD_BLANKABLE_SLOTS; slot++) {
        uint32_t record = addr_add(slots, slot * DISPLAY_REC_BYTES);

        if (image[addr_add(record, DISPLAY_REC_FRAME)] != GLYPH_ZERO)
            return;
        image[addr_add(record, DISPLAY_REC_ACTIVE)] = 0;
    }
}

/* `hud_blank_leading_zeros` @ 0x10ab4: both readouts. */
void hud_blank_leading_zeros(uint8_t *image) {
    hud_blank_leading_zeros_row(image, A_hud_score_slots);
    hud_blank_leading_zeros_row(image, A_hud_hiscore_slots);
}

/* `hud_build_labels` @ 0x10a02: the two captions, written once and never moved. */
void hud_build_labels(uint8_t *image) {
    publish_slot(image, A_hud_label_slots, HUD_LABEL_SCORE_X, HUD_LABEL_Y, GLYPH_SCORE_CAPTION);
    publish_slot(image, addr_add(A_hud_label_slots, DISPLAY_REC_BYTES), HUD_LABEL_HISCORE_X,
                 HUD_LABEL_Y, GLYPH_HISCORE_CAPTION);
}

/* `clear_display_list` @ 0x115a8: byte-clear the whole list, 0x177ce..0x17d07. */
void clear_display_list(uint8_t *image) {
    for (uint32_t slot = A_display_list; slot < A_display_list_end; slot++)
        image[slot] = 0;
}

/* `clear_player_display_slots` @ 0x115c2: twelve bytes cleared with six `clr` of mixed width.
 *
 * The two slots are the PLAYER'S, which the address settles: 0x17cfc is `dl_player_shadow` and
 * `dl_player` follows it. Its one caller is `hud_publish_bomb_and_life_icons`, which reaches it on
 * the game-over arm and so hides the plane and its shadow.
 */
void clear_player_display_slots(uint8_t *image) {
    for (unsigned byte = 0; byte < 2u * DISPLAY_REC_BYTES; byte++)
        image[addr_add(A_dl_player_shadow, byte)] = 0;
}

/* Clear the seven enable bytes an icon row starts with: `clr.b 5(a0)`, `clr.b 11(a0)`, ... */
static void clear_icon_row(uint8_t *image, uint32_t slots) {
    for (unsigned slot = 0; slot < HUD_ICON_SLOTS_CLEARED; slot++)
        image[addr_add(slots, slot * DISPLAY_REC_BYTES + DISPLAY_REC_ACTIVE)] = 0;
}

/* `hud_publish_bomb_and_life_icons` @ 0x123d8: the two icon rows along the bottom of the bar.
 *
 * Both halves are skipped once the player's control mode is "game over"; the bomb half is skipped
 * again by clearing the player's own two slots instead.
 *
 * NEITHER LOOP IS BOUNDED BY THE SEVEN SLOTS IT CLEARED, and both bugs are reproduced:
 *
 *   * the bomb loop is a `dbf` over `bombs - 1` guarded by a `bmi`, so 0 bombs draws none — but any
 *     count above seven walks straight off the end of the row into whatever follows it;
 *   * the life loop has NO such guard. `lives` is clamped to seven from above (and written back),
 *     `subi.w #$1,d7` is not tested, and `dbf` runs its body before it looks — so 0 lives publishes
 *     65,536 icons rather than none. The game reaches the loop with 0 lives only in the window
 *     before the death handler sets mode 4, which is what has kept it from being noticed.
 */
/* One icon row: `icons` slots from `slots`, stepping the column by `step` (the bomb row's step is
 * negative, so it fills leftward). Neither caller bounds `icons` — see the routine below. */
static void publish_icon_row(uint8_t *image, uint32_t slots, unsigned icons, uint16_t column,
                             uint16_t y, uint16_t step, uint8_t glyph) {
    for (unsigned icon = 0; icon < icons; icon++) {
        publish_slot(image, addr_add(slots, icon * DISPLAY_REC_BYTES), column, y, glyph);
        column = (uint16_t)(column + step);
    }
}

void hud_publish_bomb_and_life_icons(uint8_t *image) {
    uint16_t lives;

    if (image[addr_add(A_player, PLAYER_MODE)] == PLAYER_MODE_GAMEOVER) {
        clear_player_display_slots(image);
    } else {
        /* `subi.w #$1,d7 / bmi` @ 0x12414: 0 bombs (and any count whose predecessor reads negative
         * as a word) draws none. Anything else runs `bombs` passes of the `dbf`. */
        int16_t last_bomb = (int16_t)(be16(image + A_bombs) - 1u);

        clear_icon_row(image, A_dl_bomb_icons);
        if (last_bomb >= 0)
            publish_icon_row(image, A_dl_bomb_icons, (unsigned)last_bomb + 1u, HUD_BOMB_ICON_X,
                             HUD_BOMB_ICON_Y, (uint16_t)-HUD_BOMB_ICON_X_STEP, GLYPH_BOMB_ICON);
    }
    /* The mode is re-read rather than reused: the original reloads A0 and compares again @ 0x12444,
     * and nothing the bomb arm did could have changed it. */
    if (image[addr_add(A_player, PLAYER_MODE)] == PLAYER_MODE_GAMEOVER)
        return;

    clear_icon_row(image, A_dl_life_icons);
    lives = be16(image + A_lives);
    if ((int16_t)lives >= (int16_t)HUD_LIVES_SHOWN_MAX) {
        lives = HUD_LIVES_SHOWN_MAX;
        wr16(image + A_lives, lives);
    }
    /* No `bmi` guard here, and the `dbf` runs its body first: 0 lives means 65,536 icons. */
    publish_icon_row(image, A_dl_life_icons, loop_passes(lives, COUNT_MASK_WORD), HUD_LIFE_ICON_X,
                     HUD_LIFE_ICON_Y, HUD_LIFE_ICON_X_STEP, GLYPH_LIFE_ICON);
}

/* `build_text_display_list` @ 0x10698: a text script compiled into display-list slots.
 *
 * The script opens with a BYTE x and a BYTE y, and both land in the low byte of a register whose
 * high byte the caller supplies — `move.b (a0)+,d1`, not `moveq`. Every caller in the shipped
 * binary clears the registers as longwords first, so the high bytes are zero in practice; they are
 * threaded through here because the instruction stream says they are the caller's.
 *
 * THE 0x06 OPCODE READS ABSOLUTE ADDRESS 0x40 — the 68000 vector page, not this program's data at
 * all. Nothing in the game ever writes it, so a script using the opcode indents by whatever the
 * operating system left there. Reproduced rather than repaired (include/hud.h names the address).
 *
 * `script`, `dest`, `x` and `y` are all in/out: the cursors come back advanced, which is what lets
 * `hiscore_show_entry_screen` compile a second script straight on to the end of the first.
 */
void build_text_display_list(uint8_t *image, uint32_t *script, uint32_t *dest, uint32_t *x,
                             uint32_t *y) {
    *x = set_low_word(*x, set_low_byte((uint16_t)*x, image[*script]));
    *script = addr_add(*script, 1u);
    *y = set_low_word(*y, set_low_byte((uint16_t)*y, image[*script]));
    *script = addr_add(*script, 1u);

    for (;;) {
        uint8_t op = image[*script];

        *script = addr_add(*script, 1u);
        switch (op) {
        case TEXT_OP_END:
            return;
        case TEXT_OP_SPACE:
            *x = set_low_word(*x, (uint16_t)(*x + TEXT_GLYPH_WIDTH));
            break;
        case TEXT_OP_TAB:
            *x = set_low_word(*x, (uint16_t)(*x + TEXT_TAB_WIDTH));
            break;
        case TEXT_OP_NEWLINE:
            *y = set_low_word(*y, (uint16_t)(*y + TEXT_LINE_HEIGHT));
            *x = set_low_word(*x, 0);
            break;
        case TEXT_OP_INDENT:
            *x = set_low_word(*x, (uint16_t)(*x + be16(image + LOW_MEMORY_INDENT_WORD)));
            break;
        default:
            publish_slot(image, *dest, (uint16_t)*x, (uint16_t)*y, op);
            *dest = addr_add(*dest, DISPLAY_REC_BYTES);
            *x = set_low_word(*x, (uint16_t)(*x + TEXT_GLYPH_WIDTH));
            break;
        }
    }
}

/* =================================================================================================
 * The hall of fame
 * ============================================================================================== */

/* `hiscore_shift_entry_down` @ 0x108aa: push one row's name and score into the row below it.
 *
 * Thirteen bytes from +9, which spans the two spaces, the three name glyphs, two more spaces and the
 * six score glyphs — everything but the leading script bytes and the rank digit at +8, which stay
 * where they are so the rows keep printing "1" to "6" down the page.
 *
 * The copy runs FORWARD from the low address into an overlapping destination 22 bytes above, which
 * cannot alias: the gap is wider than the run.
 */
void hiscore_shift_entry_down(uint8_t *image, uint32_t entry) {
    uint32_t source = addr_add(entry, HISCORE_SHIFT_FROM);
    uint32_t dest = addr_add(source, HISCORE_STRIDE);

    for (unsigned byte = 0; byte < HISCORE_SHIFT_BYTES; byte++)
        image[addr_add(dest, byte)] = image[addr_add(source, byte)];
}

/* `hiscore_reset_last_digit` @ 0x108c0: stamp '0' over every row's last score glyph. */
void hiscore_reset_last_digit(uint8_t *image) {
    for (unsigned entry = 0; entry < HISCORE_ENTRIES; entry++)
        image[A_hiscore_table + entry * HISCORE_STRIDE + HISCORE_LAST_DIGIT] = GLYPH_ZERO;
}

/* The row `game_over_hiscore_check` shifts down for a given rank: entries 4 down to `rank`, each
 * pushed into the one below. The original spells the five chains out, one `bra` target per rank. */
static void shift_entries_below(uint8_t *image, unsigned rank) {
    for (unsigned entry = HISCORE_ENTRIES - 1u; entry > rank; entry--)
        hiscore_shift_entry_down(image, A_hiscore_table + (entry - 1u) * HISCORE_STRIDE);
}

/* The lowest rank the dispatch below has an arm of its own for: `cmp.w #$1,d4` @ 0x107c0 is the
 * last of the five, and everything it does not match falls through. */
#define HISCORE_DISPATCH_FIRST_RANK 1

/* hiscore_insert_score_at_rank @ 0x1079c — SLICE [0x1079c, 0x15754): the tail
 * `game_over_hiscore_check` reaches once its rank walk has stopped. Like the routine it belongs to
 * it has no `rts` — it ends `bra.w $15754`, re-entering `main` — so it is diffed at that branch.
 *
 * THE RANK IS DISPATCHED, NOT RANGE-TESTED, and that is the whole reason this is a function of its
 * own. Five `cmp.w #n,d4 / beq` @ 0x1079c..0x107c4 pick rank 5 (shift nothing) down to rank 1
 * (shift four rows), and the `bra` @ 0x107c6 behind them is a FALL-THROUGH arm that takes every
 * OTHER value and shifts all five: rank 0 and the negative ranks the missing floor makes reachable,
 * and equally any rank ABOVE 5.
 *
 * Its own caller can hand it only 5 or less — it writes 5 and its walk only decrements — so the
 * arm above 5 is contract coverage rather than game coverage, and entering here with the rank poked
 * is the only thing that separates the dispatch from a `rank < 5` guard (`test_hud.py`).
 */
void hiscore_insert_score_at_rank(uint8_t *image) {
    int16_t rank = (int16_t)be16(image + A_hiscore_rank);   /* `move.w $176e0,d4` @ 0x1079c */
    unsigned shift_from = (rank >= HISCORE_DISPATCH_FIRST_RANK
                           && rank <= (int16_t)HISCORE_LOWEST_RANK)
                          ? (unsigned)rank : 0u;
    /* `move.w $176e0,d0 / muls.w #$16,d0 / adda.l d0,a5 / lea 16(a5),a5` @ 0x107d4 — the rank is
     * RE-READ here, and `muls.w` sign-extends it, so a negative rank addresses below the table. */
    uint32_t row = addr_add(A_hiscore_table,
                            (uint32_t)((int32_t)(int16_t)be16(image + A_hiscore_rank)
                                       * (int32_t)HISCORE_STRIDE)
                            + HISCORE_SCORE);

    shift_entries_below(image, shift_from);
    for (unsigned digit = 0; digit < SCORE_DIGITS; digit++)
        image[addr_add(row, digit)] = image[A_score_digits + digit];
    image[A_new_hiscore_pending] = SCC_TRUE;   /* `st $176e8`, into a word */
    wr16(image + A_name_entry_timeout, const_word(image, CONST_WORD_ZERO));
}

/* `game_over_hiscore_check` @ 0x10724: place the finished score in the hall of fame, if it earns it.
 *
 * It never returns — both arms end `bra.w $15754`, re-entering `main` past its two init calls — so
 * the reconstruction ends where those branches do and test_hud.py checkpoints there.
 *
 * TWO FAULTS IN THE ORIGINAL, both reproduced:
 *
 *   * `move.b #$f0,5(a1)` @ 0x1073e is a DEAD STORE. It stamps a glyph above every digit into the
 *     score's last character so that a tying score would compare high — but the very next
 *     instruction calls `bcd3_to_digits`, which rewrites all six characters including that one. A
 *     tie therefore loses (`digits6_compare` answers "lower or equal"), which is what the store was
 *     written to prevent.
 *   * THE RANK WALK HAS NO FLOOR. It steps up while the score beats the entry above, and a score
 *     that beats row 0 leaves the rank at 0 and then compares against "entry -1" — 22 bytes BELOW
 *     the table, which is the tail of `text_hall_of_fame`'s own script. It keeps walking down
 *     through the front end's text until it meets a byte that outranks a digit glyph. Only a score
 *     above the leading entry reaches it.
 */
void game_over_hiscore_check(uint8_t *image) {
    uint32_t score = A_score_digits;
    uint32_t lowest_entry = A_hiscore_table + HISCORE_LOWEST_RANK * HISCORE_STRIDE;

    image[A_hard_mode] = 0;
    wr16(image + A_hiscore_rank, HISCORE_LOWEST_RANK);
    image[A_score_digits + SCORE_DIGITS - 1u] = SCORE_TIE_BREAK_GLYPH;   /* dead: see above */
    bcd3_to_digits(image, A_score_bcd, A_score_digits);

    if (digits6_compare(image, &lowest_entry, &score) == DIGITS_COMPARE_LOWER_OR_EQUAL) {
        wr16(image + A_new_hiscore_pending, 0);
        return;
    }

    for (;;) {
        /* `muls.w #$16,d3` sign-extends the rank, so a rank of 0 addresses 22 bytes BELOW the
         * table rather than clamping — the missing floor above. */
        int32_t above = (int32_t)(int16_t)(be16(image + A_hiscore_rank) - 1u) * (int32_t)HISCORE_STRIDE;
        uint32_t entry = addr_add(A_hiscore_table, (uint32_t)above);

        score = A_score_digits;
        if (digits6_compare(image, &entry, &score) == DIGITS_COMPARE_LOWER_OR_EQUAL)
            break;
        wr16(image + A_hiscore_rank, (uint16_t)(be16(image + A_hiscore_rank) - 1u));
    }

    hiscore_insert_score_at_rank(image);
}

/* `hiscore_show_entry_screen` @ 0x106f2: build the hall-of-fame page.
 *
 * The reconstruction is the SLICE [0x106f2, 0x10916): the routine's last instruction is a branch
 * into `hiscore_name_entry`, which is deferred (STATUS.md says why), so this ends where that branch
 * lands and test_hud.py checkpoints there.
 *
 * Both scripts compile into ONE run of slots — the second call continues where the first left off —
 * and the hall-of-fame table is itself the tail of the first script, so the six live rows are drawn
 * by walking the same bytes `hiscore_shift_entry_down` rearranges.
 */
void hiscore_show_entry_screen(uint8_t *image) {
    uint32_t script = A_text_hall_of_fame;
    uint32_t dest = A_display_list;
    uint32_t x = 0;
    uint32_t y = 0;

    hiscore_reset_last_digit(image);
    build_text_display_list(image, &script, &dest, &x, &y);
    if (be16(image + A_name_entry_done) != 0)
        return;
    script = A_text_enter_your_name;
    build_text_display_list(image, &script, &dest, &x, &y);
}

/* =================================================================================================
 * The cheats
 * ============================================================================================== */

/* Cheat "HSC" @ 0x10e30. The first use makes the player invulnerable; a SECOND use kills them
 * instead, because the arm is chosen by the flag the first use set. */
void cheat_hsc_invulnerable(uint8_t *image) {
    if (image[A_invuln_flag] != 0)
        wr16(image + A_player_hit, CHEAT_FLAG_SET);
    else
        image[A_invuln_flag] = CHEAT_FLAG_SET;
}

void cheat_kdj_infinite_lives(uint8_t *image) { image[A_infinite_lives_flag] = CHEAT_FLAG_SET; }
void cheat_jgl_infinite_bombs(uint8_t *image) { image[A_infinite_bombs_flag] = CHEAT_FLAG_SET; }
void cheat_gcc_alt_glyph(uint8_t *image) { image[A_alt_bullet_glyph_flag] = CHEAT_FLAG_SET; }
void cheat_jh_max_weapon(uint8_t *image) { image[A_max_weapon_flag] = CHEAT_FLAG_SET; }

/* `jsr (a0)` @ 0x10e14 with the handler read out of `cheat_handler_table`.
 *
 * Dispatched on the ADDRESS rather than on the table index, so the reconstruction follows the same
 * pointer the original does and a table edited under it would land in the same place.
 *
 * `cheat_jml_crash` @ 0x10e6a IS DELIBERATELY ABSENT, and its arm says so rather than falling into
 * the default. It is `movea.l #0,a0 / jsr (a0)` — a booby trap that calls address zero — so neither
 * this switch nor any differential case may reach it, and STATUS.md's "Not reconstructed" table
 * carries the row. The default arm is for a handler pointer the game's own table cannot hold.
 */
static void cheat_dispatch(uint8_t *image, uint32_t handler) {
    switch (handler) {
    case FN_CHEAT_HSC:  cheat_hsc_invulnerable(image);   break;
    case FN_CHEAT_KDJ:  cheat_kdj_infinite_lives(image); break;
    case FN_CHEAT_JGL:  cheat_jgl_infinite_bombs(image); break;
    case FN_CHEAT_GCC:  cheat_gcc_alt_glyph(image);      break;
    case FN_CHEAT_JH:   cheat_jh_max_weapon(image);      break;
    case FN_CHEAT_JML:  /* the `jsr 0` booby trap — never dispatched, never verified */
    default:            break;
    }
}

/* `check_cheat_name` @ 0x10d92: match the three initials just entered against the cheat table.
 *
 * THE ARM KEY. It first spins up to 5001 times looking for keypad '4' to be HELD (bit 0 of
 * `key_bits`, which the ACIA interrupt maintains), and simply returns if it never appears — so a
 * cheat only takes while that key is down. The spin goes through `sched_poll8` because the byte is
 * written by that interrupt and by nothing this routine does: without it the ITERATION COUNT is
 * invisible off target, since the byte a plain read returns cannot change while the candidate runs.
 * The game's own 5001 is still the bound — the kit's cap never comes into it.
 *
 * THE REWIND AFTER A PARTIAL MATCH IS OFF BY ONE, and it is reproduced. After two matching glyphs
 * the cursor is at name[2]; the mismatch arm @ 0x10df8 backs it up by ONE rather than two, so every
 * later row is compared against name[1] and name[2] instead of name[0] and name[1]. Three rows begin
 * with 'J', so a name starting "J?" really can reach it.
 */
void check_cheat_name(uint8_t *image, uint32_t name_last_char) {
    uint32_t name = addr_sub(name_last_char, HISCORE_NAME_CHARS - 1u);
    uint32_t row = A_cheat_name_table;
    unsigned armed = 0;

    for (unsigned spin = 0; spin < CHEAT_ARM_SPINS; spin++)
        if ((sched_poll8(image, A_key_bits, CHEAT_ARM_WAIT_PC) >> CHEAT_ARM_KEY_BIT) & 1u) {
            armed = 1;
            break;
        }
    if (!armed)
        return;

    image[A_cheat_used_flag] = SCC_TRUE;   /* `st $176d4`, and nothing reads it */
    for (;;) {
        if (image[row] == CHEAT_TABLE_END)
            return;
        if (image[row] != image[name]) {           /* @ 0x10dc0: no match at all */
            row = addr_add(row, CHEAT_ROW_BYTES);
            continue;
        }
        name = addr_add(name, 1u);                 /* @ 0x10dd2: one glyph matched */
        row = addr_add(row, 1u);
        if (image[row] != image[name]) {
            name = addr_sub(name, 1u);
            row = addr_add(row, CHEAT_ROW_BYTES - 1u);
            continue;
        }
        name = addr_add(name, 1u);                 /* @ 0x10dea: two glyphs matched */
        row = addr_add(row, 1u);
        if (image[row] == image[name])
            break;                                 /* @ 0x10e02: all three */
        /* THE OFF-BY-ONE: `suba.w #$1,a0` @ 0x10df8 backs the name cursor up by one where two
         * glyphs were consumed, so every later row is matched against name[1..] instead. */
        name = addr_sub(name, 1u);
        row = addr_add(row, CHEAT_ROW_BYTES - 2u);
    }

    {
        uint8_t index = image[addr_add(row, CHEAT_INDEX_PAST_LAST_GLYPH)];
        /* `lsl.w #2,d0` scales a byte index in a WORD, so the table offset wraps at 16 bits. */
        uint16_t offset = (uint16_t)(index * CHEAT_HANDLER_BYTES);

        cheat_dispatch(image, be32(image + addr_add(A_cheat_handler_table, offset)));
    }
    for (unsigned glyph = 0; glyph < TITLE_WORD_GLYPHS; glyph++)
        image[A_title_word_easy + glyph] = image[A_title_word_spam + glyph];
}

/* =================================================================================================
 * The console leftovers
 * ============================================================================================== */

/* `console_putc` @ 0x1159c: GEMDOS Cconout of D0's low byte. */
void console_putc(uint32_t ch) {
    os_cconout((uint8_t)ch);
}

/* `debug_print_word_binary` @ 0x11570: D4's sixteen bits as ASCII '0'/'1', then a carriage return.
 *
 * `lsl.w #1,d4` shifts the WORD and the branch reads the bit that fell out of it, so the printout is
 * most-significant bit first and the register is left shifted out to zero. Nothing in the image
 * calls it — leftover development code that survived the link.
 */
void debug_print_word_binary(uint32_t value) {
    uint16_t bits = (uint16_t)value;

    for (unsigned bit = 0; bit < BINARY_DUMP_BITS; bit++) {
        console_putc((bits & 0x8000u) ? ASCII_ONE : ASCII_ZERO);
        bits = (uint16_t)(bits << 1);
    }
    console_putc(ASCII_CR);
}

/* `console_show_message` @ 0x14996: print a message over the game through TOS's VT52 console.
 *
 * XBIOS Setscreen points the LOGICAL base at the previous frame's buffer so the console draws where
 * the player is not looking, and never puts it back. Then ESC 'Y' 0x38 0x20 addresses the cursor to
 * row 24 column 0, the message bytes go out until one has bit 7 set — the terminator is >= 0x80, not
 * a NUL — and the routine spins until joystick fire is RELEASED, leaving the press test to whoever
 * called it.
 *
 * THE SPIN GOES THROUGH `sched_poll8`, because the byte it waits on is written by the ACIA interrupt
 * and nothing inside this routine ever changes it: a plain read would spin forever off target. The
 * poll counts against the wait site the case declares, so a reconstruction that polled a different
 * number of times fails rather than agreeing by accident.
 */
void console_show_message(uint8_t *image, uint32_t text) {
    static const uint8_t cursor_home[] = {
        CONSOLE_ESCAPE, CONSOLE_POSITION, CONSOLE_ROW_24, CONSOLE_COLUMN_0
    };

    os_setscreen(be32(image + A_screen_prev1), (uint32_t)CONSOLE_KEEP_PHYSBASE,
                 CONSOLE_KEEP_RESOLUTION);
    for (unsigned byte = 0; byte < sizeof cursor_home; byte++)
        os_cconout(cursor_home[byte]);
    for (;;) {
        uint8_t ch = image[text];

        text = addr_add(text, 1u);
        if (ch >= CONSOLE_TEXT_END)
            break;
        os_cconout(ch);
    }
    for (unsigned poll = 0; poll < OS_SCHED_POLL_MAX; poll++)
        if (((sched_poll8(image, A_joy1_state, FIRE_RELEASE_WAIT_PC) >> JOY_FIRE_BIT) & 1u) == 0)
            return;
    os_refused(0);   /* the cap: the case is void, so there is nothing left to do but leave */
}

/* `debug_show_counters` @ 0x14960: three counters patched into the message, in place.
 *
 * The reconstruction is the SLICE [0x14960, 0x14996): the original FALLS THROUGH into
 * `console_show_message` without ever loading A6 with the string it just patched, so what it prints
 * is whatever the caller happened to leave there. That fall-through is the caller's register, not
 * this routine's work, so the slice ends at it and test_hud.py checkpoints there.
 *
 * Reachable only through `debug_overlay_flag`, which no instruction in the image writes — the
 * overlay is permanently off, and the missing A6 is very likely why.
 */
void debug_show_counters(uint8_t *image) {
    format_5_digits(image, A_debug_map_advance_field,
                    be32(image + A_map_row_ptr) - be32(image + A_map_row_ptr_reset));
    format_5_digits(image, A_debug_scroll_pos_field, be16(image + A_scroll_pos));
    format_5_digits(image, A_debug_scroll_fine_field, be16(image + A_scroll_fine));
}

/* =================================================================================================
 * The glue: register ABI in, core out
 * ============================================================================================== */

/* A1 = one past the award's three BCD bytes; X in = the flag the first `abcd` adds. */
unsigned g_score_add_bcd(uint8_t *image, uint32_t value_end, unsigned extend_in) {
    return score_add_bcd(image, value_end, extend_in);
}

/* The nine wrappers take no arguments at all: each is a `lea` of its own award and a `bsr`. */
#define SCORE_AWARD_GLUE(name, award)                                        \
    unsigned name(uint8_t *image, unsigned extend_in) {                      \
        return score_add_award(image, (award), extend_in);                   \
    }
SCORE_AWARD_GLUE(g_score_add_50, SCORE_AWARD_50)
SCORE_AWARD_GLUE(g_score_add_100, SCORE_AWARD_100)
SCORE_AWARD_GLUE(g_score_add_200, SCORE_AWARD_200)
SCORE_AWARD_GLUE(g_score_add_250, SCORE_AWARD_250)
SCORE_AWARD_GLUE(g_score_add_500, SCORE_AWARD_500)
SCORE_AWARD_GLUE(g_score_add_1000, SCORE_AWARD_1000)
SCORE_AWARD_GLUE(g_score_add_3000, SCORE_AWARD_3000)
SCORE_AWARD_GLUE(g_score_add_5000, SCORE_AWARD_5000)
SCORE_AWARD_GLUE(g_score_add_10000, SCORE_AWARD_10000)
#undef SCORE_AWARD_GLUE

/* A0 = the packed BCD, A1 = the glyph run it expands into. */
void g_bcd3_to_digits(uint8_t *image, uint32_t bcd, uint32_t glyphs) {
    bcd3_to_digits(image, bcd, glyphs);
}

void g_scores_bcd_to_chars(uint8_t *image) { scores_bcd_to_chars(image); }
void g_score_reset(uint8_t *image) { score_reset(image); }

/* A0 = the destination. */
void g_clear_3_bytes(uint8_t *image, uint32_t dest) { clear_3_bytes(image, dest); }

/* Mirrors `abi.register_dump_pokes(ENTRY_FORMAT_5_DIGITS, ("d0", "a0"))`: the digits themselves land
 * in the diffed image, but where A0 came to rest does not, and the routine walks A0 so the dump stub
 * is what can record it. D0 is left at zero by the divide loop and is recorded beside it. */
/* A0 = the field's first glyph, D0 = the value; `result` is the dump stub's landing address. */
void g_format_5_digits(uint8_t *image, uint32_t field, uint32_t value, uint32_t result) {
    uint32_t cursor = format_5_digits(image, field, value);

    /* `swap / clr.w / swap` masks D0 to 16 bits before the loop and the loop divides it to zero, so
     * what the original leaves in D0 is 0 — not the value it was handed. */
    (void)value;
    wr32(image + result, 0);
    wr32(image + addr_add(result, 4u), cursor);
}

/* Mirrors `abi.register_call_pokes(ENTRY_DIGITS6_COMPARE, ("d0", "a5", "a6"))`: the routine answers
 * in registers alone, so the stub stores those three where the image diff can see them and this
 * writes the same three longwords at the same address. D0 comes back as a WORD merged into the
 * caller's own high half, because `move.w #$ffff,d0` is what the routine writes. */
/* A5 = the table entry - 16, A6 = the score glyphs, D0 = the caller's own D0 (only its LOW word is
 * written); both cursors are walked and come back through the dump stub's `result`. */
void g_digits6_compare(uint8_t *image, uint32_t entry, uint32_t score, uint32_t d0_in,
                       uint32_t result) {
    uint16_t answer = digits6_compare(image, &entry, &score);

    wr32(image + result, set_low_word(d0_in, answer));
    wr32(image + addr_add(result, 4u), entry);
    wr32(image + addr_add(result, 8u), score);
}

void g_check_beat_hiscore(uint8_t *image) { check_beat_hiscore(image); }
unsigned g_award_extra_life(uint8_t *image) { return award_extra_life(image); }

/* A0 = the glyph run, A1 = the display slots, D1 = x, D2 = y. */
void g_hud_publish_digit_row(uint8_t *image, uint32_t glyphs, uint32_t slots, uint32_t x,
                             uint32_t y) {
    hud_publish_digit_row(image, glyphs, slots, x, y);
}

void g_hud_build_score_digits(uint8_t *image) { hud_build_score_digits(image); }

/* A1 = the readout's first slot. */
void g_hud_blank_leading_zeros_row(uint8_t *image, uint32_t slots) {
    hud_blank_leading_zeros_row(image, slots);
}

void g_hud_blank_leading_zeros(uint8_t *image) { hud_blank_leading_zeros(image); }
void g_hud_build_labels(uint8_t *image) { hud_build_labels(image); }
void g_hud_publish_bomb_and_life_icons(uint8_t *image) { hud_publish_bomb_and_life_icons(image); }
void g_clear_display_list(uint8_t *image) { clear_display_list(image); }
void g_clear_player_display_slots(uint8_t *image) { clear_player_display_slots(image); }

/* Mirrors `abi.register_dump_pokes(ENTRY_BUILD_TEXT_DISPLAY_LIST, ("d1", "d2", "a0", "a1"))` —
 * `movem.l` order, D-registers before A-registers, which is why the four longwords come out in that
 * order and not in the argument order. A dump stub rather than `register_call_pokes` because the
 * routine walks A0 itself, so A0 cannot also be the result cursor. */
/* A0 = the script, A1 = the display slots, D1 = x, D2 = y — all four walked, all four dumped. */
void g_build_text_display_list(uint8_t *image, uint32_t script, uint32_t slots, uint32_t x,
                               uint32_t y, uint32_t result) {
    build_text_display_list(image, &script, &slots, &x, &y);
    wr32(image + result, x);
    wr32(image + addr_add(result, 4u), y);
    wr32(image + addr_add(result, 8u), script);
    wr32(image + addr_add(result, 12u), slots);
}

/* A0 = the row to push down. */
void g_hiscore_shift_entry_down(uint8_t *image, uint32_t row) {
    hiscore_shift_entry_down(image, row);
}

void g_hiscore_reset_last_digit(uint8_t *image) { hiscore_reset_last_digit(image); }
void g_hiscore_show_entry_screen(uint8_t *image) { hiscore_show_entry_screen(image); }
void g_game_over_hiscore_check(uint8_t *image) { game_over_hiscore_check(image); }
/* No arguments: the rank is in `hiscore_rank` and the score in `score_digits`. */
void g_hiscore_insert_score_at_rank(uint8_t *image) { hiscore_insert_score_at_rank(image); }

/* A0 = the LAST of the three name glyphs. */
void g_check_cheat_name(uint8_t *image, uint32_t name_last_char) {
    check_cheat_name(image, name_last_char);
}

void g_cheat_hsc_invulnerable(uint8_t *image) { cheat_hsc_invulnerable(image); }
void g_cheat_kdj_infinite_lives(uint8_t *image) { cheat_kdj_infinite_lives(image); }
void g_cheat_jgl_infinite_bombs(uint8_t *image) { cheat_jgl_infinite_bombs(image); }
void g_cheat_gcc_alt_glyph(uint8_t *image) { cheat_gcc_alt_glyph(image); }
void g_cheat_jh_max_weapon(uint8_t *image) { cheat_jh_max_weapon(image); }

/* Neither of these two touches the image at all — their whole effect is the OS event ledger — so the
 * cores take no image and the glue is what discards the one the harness hands every candidate. */
/* D0 = the byte. */
void g_console_putc(uint8_t *image, uint32_t byte) {
    (void)image;
    console_putc(byte);
}

/* D4 = the word to dump. */
void g_debug_print_word_binary(uint8_t *image, uint32_t value) {
    (void)image;
    debug_print_word_binary(value);
}

/* A6 = the message, ended by a byte >= 0x80. */
void g_console_show_message(uint8_t *image, uint32_t message) {
    console_show_message(image, message);
}

void g_debug_show_counters(uint8_t *image) { debug_show_counters(image); }
