/* buggyboy.h — reconstruction cores + their image glue.
 *
 * Each function has two parts:
 *   - a *core* that works on idiomatic C types (the readable reconstruction);
 *   - a *glue* g_<name>(image, regs...) that unpacks the core's inputs from the flat
 *     image at their real addresses, calls the core, and lets it write back. The glue
 *     is the function's I/O contract; the differential harness diffs the whole image.
 */
#ifndef BB_BUGGYBOY_H
#define BB_BUGGYBOY_H

#include <stdint.h>

/* ---- score (add_score @ 0x1580a) ---- */
#define SCORE_DIGITS 6
void score_add(uint8_t *score, char *score_str, const uint8_t *delta, int game_over);
void g_add_score(uint8_t *image, uint32_t a1);

#endif /* BB_BUGGYBOY_H */