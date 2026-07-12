/* score.c — player score: six ASCII digits (most-significant first) with decimal carry.
 *
 * Reconstruction of add_score @ 0x1580a. The six digits live contiguously in memory as
 * score_bcd (4 bytes) + a 2-byte counter; the HUD copy sits in score_str[4..9]. Scoring
 * adds a per-digit delta, fixes up any digit that passed '9' by borrowing a decimal ten
 * into the next-higher digit, then refreshes the display and blanks leading zeros.
 */
#include <string.h>
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

/* Add v to the n-byte big-endian integer at p (binary carry across bytes, as 68k add.l/.w). */
static void add_be(uint8_t *p, int n, uint32_t v) {
    uint32_t acc = 0;
    for (int i = 0; i < n; i++) acc = (acc << 8) | p[i];
    acc += v;
    for (int i = n - 1; i >= 0; i--) { p[i] = (uint8_t)acc; acc >>= 8; }
}

void score_add(uint8_t *score, char *score_str, const uint8_t *delta, int game_over) {
    if (game_over) return;

    /* 68k adds the top four digits as one long and the low two as a word. */
    add_be(score,     4, be32(delta));
    add_be(score + 4, 2, be16(delta + 4));

    /* Decimal carry, least-significant digit upward (five inter-digit boundaries). */
    for (int i = SCORE_DIGITS - 1; i >= 1; i--) {
        if ((int8_t)('9' - score[i]) < 0) { score[i] -= 10; score[i - 1] += 1; }
    }

    /* Refresh the on-screen digits, then blank leading zeros ('0' -> '/'). */
    memcpy(score_str + 4, score, SCORE_DIGITS);
    for (char *p = score_str + 4; *p == '0'; p++) *p -= 1;
}

/* Glue / I/O contract: A1 -> 6-byte delta; reads game_over_flag; writes score + score_str. */
void g_add_score(uint8_t *image, uint32_t delta_ptr) {
    int game_over = be16(image + A_game_over_flag) != 0;
    score_add(image + A_score_bcd, (char *)(image + A_score_str), image + delta_ptr, game_over);
}