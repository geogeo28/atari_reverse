/*
 * c2p.h - the reference chunky-to-planar + pixel double.
 *
 * This is the oracle the hand-written 68000 c2p is compared against, byte for
 * byte, and the only place the engine's chunky buffer meets the ST's screen
 * format.
 *
 * Output: 320x200, 4 bitplanes INTERLEAVED - sixteen pixels are four
 * consecutive words, one per plane, 160 bytes to a line, 32,000 bytes to a
 * screen.  Only the top SCREEN_WINDOW_LINES lines are written; the bottom
 * SCREEN_HUD_LINES are the platform's static HUD and are left untouched.
 *
 * Doubling: a chunky pixel becomes (SCREEN_W / columns) screen pixels wide and
 * always 2 screen lines tall, so 160 columns give 2x2 and 80 columns 4x2.
 *
 * -------------------------------------------------------------------------
 * 68000 cost model
 * -------------------------------------------------------------------------
 * The output is 25,600 planar bytes = 12,800 words either way, of which 6,400
 * are unique (every line is written twice).  That makes the c2p almost
 * entirely a STORE cost and almost entirely independent of the column count:
 *   stores    6,400 unique words, each written to two lines.  `move.w d0,(a0)`
 *             plus `move.w d0,158(a0)` is ~24 cyc per unique word, or ~28 cyc
 *             per 16-pixel group with `movem.l d0-d1,(a0)` used twice.
 *             -> 1,600 groups x ~56 = 90,000 cycles of stores alone.
 *   gather    8 chunky bytes per group at 160 columns (4 at 80), strided by
 *             CHUNKY_STRIDE because the buffer is column major:
 *             8 x `move.b (a1,d1.w),d2` = ~112 cyc/group = 179,000.
 *   convert   a byte-pair lookup into a 4-word plane pattern, ~40 cyc/group.
 * Naive total at 160 columns: ~330,000 cycles, well past DESIGN 17's 130,000
 * gate.  The fix is the strip transpose described in render.h: read whole
 * chunky columns with `movem.l` (20 longs = 80 rows in ~2.3 cyc/byte) and
 * accumulate plane bits for a 16-column strip, which deletes the strided
 * gather.  That lands the estimate near 150,000, and DESIGN 17 already commits
 * to shipping 80 columns if the measurement misses.
 *
 * These are estimates from the instruction timings, not measurements.  The
 * platform agent must measure on the Musashi oracle and pin the number.
 */
#ifndef BLACKICE_C2P_H
#define BLACKICE_C2P_H

#include <stdint.h>
#include "game_consts.h"

/*
 * Convert `columns` columns of the column-major chunky buffer into the top
 * SCREEN_WINDOW_LINES lines of a SCREEN_BYTES planar buffer.
 * `columns` must divide SCREEN_W.
 */
void c2p_window(const uint8_t *chunky, uint16_t columns, uint8_t *planar);

/* Read one pixel back out of a planar buffer.  Used by the PNG writer, which
 * therefore proves the c2p round-trips rather than trusting it. */
uint8_t planar_pixel(const uint8_t *planar, uint16_t x, uint16_t y);

#endif /* BLACKICE_C2P_H */
