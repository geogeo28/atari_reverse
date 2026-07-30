/* score.c — Joust's HUD layer: the timed on-screen messages, the lives row, and the high-score
 * name-entry display.
 *
 * Everything here paints through the text engine in draw.c: a routine stages text_ptr (the screen
 * address), text_shift (pixels into that cell), text_color / text_bg_color / text_flags, and then
 * hands draw_string a string of glyphs and in-line control bytes. draw_string advances text_ptr
 * and text_shift as it goes and stores them back, so consecutive calls continue where the last one
 * stopped — which is how the lives row draws five glyphs from one staged cursor.
 *
 * The scoring routines are here too, and they are not what their name suggests: score_update adds
 * nothing. Callers add their points straight into the object's ASCII score digits and call this to
 * carry the decimal columns, hand out the extra lives those carries earn, and repaint the row.
 */
#include "machine.h"
#include "joust.h"
#include "draw.h"
#include "object.h"
#include "score.h"
#include "sound.h"

/* =================================================================================================
 * find_free_message @ 0x1435c
 * ============================================================================================= */

/* The first message slot the caller may fill in, or 0 (`suba.l a0,a0`) when all 24 are taken. A
 * slot is free iff its kind byte is zero — nothing else is tested, not even the timer. */
uint32_t find_free_message(const uint8_t *image) {
    for (uint32_t message = A_message_table; message != A_message_table_END; message += MSG_RECORD)
        if (image[message + MSG_KIND] == 0) return message;
    return 0;
}

/* =================================================================================================
 * draw_messages @ 0x142de
 * ============================================================================================= */

/* Age every live message by one frame and repaint it.
 *
 * A slot whose timer reaches zero is freed and its colour forced to 0 — and then STILL drawn, in
 * colour 0, which is how a message rubs itself out on its last frame. With no players left every
 * message except MSG_KIND_PERSISTENT is cut short to a single frame (timer := 1, which this same
 * pass immediately decrements to 0), so the between-lives banners clear at once instead of hanging
 * over the game-over screen.
 */
void draw_messages(uint8_t *image) {
    for (uint32_t message = A_message_table; message != A_message_table_END;
         message += MSG_RECORD) {
        if (image[message + MSG_KIND] == 0) continue;

        if (image[A_players_alive] == 0 && image[message + MSG_KIND] != MSG_KIND_PERSISTENT)
            image[message + MSG_TIMER] = 1;

        /* `subq.b`: a timer of 0 wraps to 0xff — 256 more frames, not "already expired". */
        uint8_t timer = (uint8_t)(image[message + MSG_TIMER] - 1u);
        image[message + MSG_TIMER] = timer;

        if (timer == 0) {
            image[A_text_color] = 0;
            image[message + MSG_KIND] = 0;
            if (be32(image + message + MSG_STRING) == STR_GAME_OVER)
                image[A_game_over_flag] = 1;
        } else {
            image[A_text_color] = image[message + MSG_COLOR];
        }

        wr32(image + A_text_ptr, be32(image + message + MSG_SCREEN_PTR));
        image[A_text_shift] = image[message + MSG_SHIFT];
        draw_string(image, be32(image + message + MSG_STRING));
    }
}

/* =================================================================================================
 * draw_lives @ 0x14246, draw_lives_p1 @ 0x1424e, draw_lives_p2 @ 0x14260 — one alias family.
 *
 * 0x14246 is a two-instruction dispatcher that falls THROUGH into 0x1424e; the two entry points
 * below it are the real bodies, identical but for the object they read and the glyph they draw.
 * ============================================================================================= */

#define LIVES_DRAWN         5     /* `moveq #5`: five positions are painted, whatever the count */
#define LIVES_HUD_ADVANCE   0x10u /* the lives row starts this many bytes past the score's cell */
#define LIVES_SHIFT_ADVANCE 0xau  /* ...and 10 pixels further into it */
/* Both HUD rows paint their background bar in colour 15 (`move.b #$f,text_bg_color` at 0x14256 and
 * at 0x1420a) — one value, one name. */
#define HUD_BG_COLOR        0xfu

/* Repaint one player's five life positions: `lives` glyphs, then blanks. Both the large font and
 * the background bar are switched on for the row; only the bar is switched off again at the end,
 * so the font selection LEAKS to whatever draws next (the glyph strings themselves also leave
 * text_color and text_bg_color changed — see STR_LIFE_P1's trailing `03 00`). */
static void draw_lives_row(uint8_t *image, uint32_t object, uint32_t life_glyph) {
    wr32(image + A_text_ptr, be32(image + object + OBJ_SCORE_PTR) + LIVES_HUD_ADVANCE);
    image[A_text_shift] = (uint8_t)(image[object + OBJ_SCORE_SHIFT_LO] + LIVES_SHIFT_ADVANCE);
    image[A_text_flags] |= TEXT_FLAG_LARGE_FONT | TEXT_FLAG_BACKGROUND;
    image[A_text_bg_color] = HUD_BG_COLOR;

    /* The count is re-read from the record on EVERY pass (`cmp.b 76(a0),d0` sits inside the loop),
     * so a row painted over the record itself changes how many of its own positions fill in. Both
     * sides of the comparison are SIGNED bytes: a count of 0x80 draws no glyph at all. */
    for (int8_t position = LIVES_DRAWN; position != 0; position--)
        draw_string(image, position <= (int8_t)image[object + OBJ_LIVES] ? life_glyph
                                                                        : STR_LIFE_BLANK);

    image[A_text_flags] &= (uint8_t)~TEXT_FLAG_BACKGROUND;
}

void draw_lives_p1(uint8_t *image) { draw_lives_row(image, A_object_table, STR_LIFE_P1); }
void draw_lives_p2(uint8_t *image) { draw_lives_row(image, A_player2, STR_LIFE_P2); }

/* The dispatcher: a FULL 32-bit `cmpa.l` against player 2's slot. Any other object — an enemy, a
 * one-byte-off pointer at player 2 — draws PLAYER 1's row, because both entry points reload the
 * object from a constant and ignore the one they were called with. */
void draw_lives(uint8_t *image, uint32_t object) {
    if (object == A_player2) draw_lives_p2(image);
    else                     draw_lives_p1(image);
}

/* =================================================================================================
 * score_update @ 0x14160, score_update_p2 @ 0x14166, score_update_p1 @ 0x14172 — one alias family.
 *
 * Three entry points, six bytes apart, each falling through into the shared body at 0x1417c: the
 * first takes its object in A0, the other two load player 2's or player 1's slot and ignore
 * whatever A0 held.
 *
 * NONE of them adds a score. The caller has already added its points into a digit BYTE of the
 * object's ASCII score string (`addq.b #5,67(a0)` and friends), which can leave that byte above
 * '9' — or, if the position was still blank, at ' ' + n. This routine repairs the string: promote
 * the bumped blanks to digits, carry the decimal columns right to left, pay out the extra lives
 * those carries earn, and repaint the row.
 * ============================================================================================= */

#define SCORE_BLANK          0x20u  /* ' ' — a digit position the score has not reached yet */
#define SCORE_DIGIT_0        0x30u
#define SCORE_DIGIT_9        0x39u
#define SCORE_BLANK_TO_DIGIT 0x10u  /* `addi.b #$10`: ' ' + n becomes '0' + n */
#define SCORE_CARRY          0xau   /* `subi.b #$a` — one decimal column */
#define SND_EXTRA_LIFE       1u

/* A caller that bumps a position still holding ' ' leaves ' ' + n there, which is below '0'. Walk
 * the string and turn every such byte into the digit it means.
 *
 * Two deliberate limits, both reproduced. The leading BLANKS are skipped rather than promoted, so
 * the score stays left-padded with spaces instead of gaining leading zeroes — the scan stops at the
 * first byte that is not exactly ' ', and only from there does the promotion run. And the sweep
 * stops one short of the last digit, which is why a bump landing on the units position would never
 * be promoted at all; the game holds that position at '0', so nothing ever bumps it.
 *
 * The "below '0'" test is a SIGNED byte compare, so a digit that has wrapped past 0x7f is promoted
 * too — `addi.b #$10` on 0xff gives 0x0f, which the carry pass below then leaves alone.
 */
static void promote_blank_digits(uint8_t *image, uint32_t object) {
    uint8_t at = OBJ_SCORE_FIRST_DIGIT;

    while (image[object + at] == SCORE_BLANK)
        if (++at == OBJ_SCORE_LAST_DIGIT) return;

    for (; at != OBJ_SCORE_LAST_DIGIT; at++)
        if ((int8_t)image[object + at] < (int8_t)SCORE_DIGIT_0)
            image[object + at] += SCORE_BLANK_TO_DIGIT;
}

/* Every carry that leaves the 10,000s digit EVEN is a free life — i.e. one per 20,000 points. */
static void award_extra_life(uint8_t *image, uint32_t object) {
    image[object + OBJ_LIVES]++;             /* `addq.b #1`: a count of 0xff wraps to 0 */
    draw_lives(image, object);
    play_sound(image, SND_EXTRA_LIFE);
}

/* Carry the decimal columns, right to left, over the whole string.
 *
 * The sweep starts at the LAST digit and each column's carry lands on the byte one to its left —
 * so the leftmost column carries into the string's colour byte (OBJ_SCORE_TEXT + 1) rather than
 * overflowing cleanly. Reproduced: a score that big cannot be earned inside one game.
 *
 * The `> '9'` test is UNSIGNED, so a digit promote_blank_digits left above 0x7f carries repeatedly
 * until ten-at-a-time brings it back into range. A column still holding a blank when the carry
 * reaches it becomes '0' first, which is how the string grows leftwards one digit at a time.
 */
static void carry_score_digits(uint8_t *image, uint32_t object) {
    for (uint8_t at = OBJ_SCORE_LAST_DIGIT; at != OBJ_SCORE_FIRST_DIGIT - 1u; at--) {
        while (image[object + at] > SCORE_DIGIT_9) {
            uint32_t higher = object + at - 1u;
            if (image[higher] == SCORE_BLANK) image[higher] = SCORE_DIGIT_0;
            image[higher]++;
            image[object + at] -= SCORE_CARRY;

            if (at == OBJ_SCORE_LIFE_DIGIT && !(image[higher] & 1u))
                award_extra_life(image, object);
        }
    }
}

/* Repaint the row from the record's own cursor. The large font is switched on before the carries
 * rather than here (`bset #7,text_flags` at 0x141aa) — which is invisible either way, since the
 * only thing that runs in between is draw_lives, and that sets the same bit itself. */
static void draw_score_row(uint8_t *image, uint32_t object) {
    image[A_text_flags] |= TEXT_FLAG_BACKGROUND;
    image[A_text_bg_color] = HUD_BG_COLOR;
    image[A_text_shift] = image[object + OBJ_SCORE_SHIFT_LO];
    wr32(image + A_text_ptr, be32(image + object + OBJ_SCORE_PTR));
    draw_string(image, object + OBJ_SCORE_TEXT);
    image[A_text_flags] &= (uint8_t)~TEXT_FLAG_BACKGROUND;
}

void score_update(uint8_t *image, uint32_t object) {
    promote_blank_digits(image, object);
    image[A_text_flags] |= TEXT_FLAG_LARGE_FONT;
    carry_score_digits(image, object);
    draw_score_row(image, object);
}

void score_update_p1(uint8_t *image) { score_update(image, A_object_table); }
void score_update_p2(uint8_t *image) { score_update(image, A_player2); }

/* =================================================================================================
 * The high-score name-entry screen: flash_hiscore_color @ 0x144b0, draw_hiscore_cursor @ 0x14658,
 * draw_hiscore_entry @ 0x146a6.
 * ============================================================================================= */

#define HISCORE_FLASH_PEN    0xau    /* XBIOS Setcolor pen 10 */
#define HISCORE_FLASH_SHADES 0x7u    /* `andi.w #7` — the counter's low 3 bits pick the shade */
#define HISCORE_FLASH_BASE   0x400u  /* `ori.w #$400` — full red; the shade rides in green/blue */

/* One step of the colour cycle running behind the name entry.
 *
 * Its only IMAGE effect is the counter bump. The colour leaves through XBIOS Setcolor(pen, colour),
 * which writes the palette hardware rather than memory, so the differential cannot see it at all
 * (the kit models Setcolor as a no-op). Returning the word instead of dropping it is what makes the
 * computation verifiable: the test compares this against the argument the ORIGINAL pushed for its
 * trap. HISCORE_FLASH_PEN has no other reader here for the same reason — the test pins it against
 * the pen the original pushed.
 */
uint16_t flash_hiscore_color(uint8_t *image) {
    uint16_t flash = (uint16_t)(be16(image + A_hiscore_flash) + 1u);
    wr16(image + A_hiscore_flash, flash);
    return (uint16_t)(HISCORE_FLASH_BASE | (flash & HISCORE_FLASH_SHADES));
}

#define HISCORE_UNDERLINE_OFF      0x57b0u  /* from screen_base: the rule under the name */
#define HISCORE_UNDERLINE_CELLS    8u
#define HISCORE_UNDERLINE_PLANES01 0xfefefefeu  /* 7 lit pixels in 8, planes 0 and 1... */
#define HISCORE_UNDERLINE_PLANES23 0u           /* ...and none in 2 or 3 */

/* The cursor bar for the two column parities, each {planes 0+1, planes 2+3}: one cell's four plane
 * words, written as two longwords the way the original holds them in D0/D1. */
#define HISCORE_CURSOR_PLANE_PAIRS 2
static const uint32_t HISCORE_CURSOR_EVEN[HISCORE_CURSOR_PLANE_PAIRS] = {0x00fefefeu, 0x0000fe00u};
static const uint32_t HISCORE_CURSOR_ODD[HISCORE_CURSOR_PLANE_PAIRS] = {0xfe00fefeu, 0x000000feu};

#define HISCORE_COLUMN_BYTES 4u  /* `lsl.w #2` — see hiscore_column_offset */

/* Where column `cursor` starts, as a byte offset into its row. The low bit is cleared first and the
 * rest scaled by HISCORE_COLUMN_BYTES, so the two columns of a pair share one 8-byte cell and each
 * PAIR advances a whole cell. The offset is folded in with `adda.w`, i.e. SIGN-extended from 16
 * bits — a cursor past 0x1fff therefore points at a row BEFORE the one it was measured from. */
static uint32_t hiscore_column_offset(uint16_t cursor) {
    return sign_ext16((uint16_t)((cursor & ~1u) * HISCORE_COLUMN_BYTES));
}

/* Paint the rule the name is typed on, then the wide cursor bar over the column being edited. The
 * bar is written straight on top of the rule, so the two never disagree about the row. */
void draw_hiscore_cursor(uint8_t *image) {
    uint32_t row = be32(image + A_screen_base) + HISCORE_UNDERLINE_OFF;

    uint32_t cell = row;
    for (unsigned painted = 0; painted < HISCORE_UNDERLINE_CELLS; painted++) {
        wr32(image + cell, HISCORE_UNDERLINE_PLANES01);
        wr32(image + cell + 4, HISCORE_UNDERLINE_PLANES23);
        cell += CELL_BYTES;
    }

    uint16_t cursor = be16(image + A_hiscore_cursor);
    const uint32_t *bar_planes = (cursor & 1u) ? HISCORE_CURSOR_ODD : HISCORE_CURSOR_EVEN;
    uint32_t bar = row + hiscore_column_offset(cursor);
    wr32(image + bar, bar_planes[0]);
    wr32(image + bar + 4, bar_planes[1]);
}

#define HISCORE_ENTRY_OFF        0x52b0u /* from screen_base: the row the letters appear on */
#define HISCORE_ENTRY_SHIFT_EVEN 1u      /* pixels into the cell for an even column... */
#define HISCORE_ENTRY_SHIFT_ODD  9u      /* ...and for the odd one sharing it */

/* Commit the letter under the cursor to the name, and draw it in its column. */
void draw_hiscore_entry(uint8_t *image) {
    uint32_t row = be32(image + A_screen_base) + HISCORE_ENTRY_OFF;
    uint16_t cursor = be16(image + A_hiscore_cursor);

    /* The name is indexed by the RAW cursor, sign-extended (`move.b ...,(0,a2,d2.w)`) — while the
     * screen position below uses the same cursor with its low bit cleared. */
    image[A_hiscore_name + sign_ext16(cursor)] = image[A_hiscore_letter];
    image[A_text_shift] = (uint8_t)((cursor & 1u) ? HISCORE_ENTRY_SHIFT_ODD
                                                  : HISCORE_ENTRY_SHIFT_EVEN);
    wr32(image + A_text_ptr, row + hiscore_column_offset(cursor));
    draw_string(image, A_hiscore_letter);
}

/* ------------------------------------------------------------------------------------- glue ---
 *
 * Nothing in this layer takes a stack frame — draw_lives and score_update read their object from A0
 * and the rest work entirely off globals — so each g_* is a bare forwarder rather than the argument
 * unpacker the other layers' glue needs. The two results an image diff cannot see (find_free_message's slot, which the
 * original returns in A0, and the colour word flash_hiscore_color hands XBIOS Setcolor) come back
 * as return values, and the test compares each against what the oracle really produced.
 */

void g_score_update(uint8_t *image, uint32_t object) {
    score_update(image, object);
}

void g_score_update_p1(uint8_t *image) {
    score_update_p1(image);
}

void g_score_update_p2(uint8_t *image) {
    score_update_p2(image);
}

uint32_t g_find_free_message(const uint8_t *image) {
    return find_free_message(image);
}

void g_draw_messages(uint8_t *image) {
    draw_messages(image);
}

void g_draw_lives(uint8_t *image, uint32_t object) {
    draw_lives(image, object);
}

void g_draw_lives_p1(uint8_t *image) {
    draw_lives_p1(image);
}

void g_draw_lives_p2(uint8_t *image) {
    draw_lives_p2(image);
}

uint32_t g_flash_hiscore_color(uint8_t *image) {
    return flash_hiscore_color(image);
}

void g_draw_hiscore_cursor(uint8_t *image) {
    draw_hiscore_cursor(image);
}

void g_draw_hiscore_entry(uint8_t *image) {
    draw_hiscore_entry(image);
}
