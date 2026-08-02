/* scroll.h — the background scroll engine (src/scroll.c), the whole cluster at `$7522..$8228` plus
 * the request raiser at `$d28` that drives it.
 *
 * The shape is a queue drained once a frame:
 *
 *   game_main_loop -> bg_scroll_run_queue ($7522, the image's only caller)
 *     -> bg_scroll_raise_requests ($d28) raises up/down/left/right and returns two distances
 *     -> N x bg_scroll_serve_requests ($759a), which dispatches each raised byte to a handler
 *        that CONSUMES it
 *     -> serve = step (move the position words) + fill (draw the newly uncovered edge),
 *        and vertically a pre-shift as well
 *
 * WHAT A STEP RETURNS is not in a register. A step that has nothing to do adds to its own RETURN
 * ADDRESS (`addq.l #4,(a7)` horizontally, `#8` vertically, where there are two calls to skip),
 * which lands the caller past its `bsr`s — so "no work" and "the redraw is skipped" are one act,
 * invisible to Ghidra (../decomp.c shows a plain `return`) and read off the disassembly. The C
 * returns that decision as a flag and the request handler honours it, which is the only way to
 * write it in C at all.
 *
 * Every ADDRESS these touch is a global named in wonderboy.h, which both languages read; this
 * header carries no constant of its own.
 */
#ifndef WONDERBOY_SCROLL_H
#define WONDERBOY_SCROLL_H

#include <stdint.h>

/* One run of `move.l (a0)+,(a1)+`, which is the only instruction any of the sixteen copy variants
 * below spends its length on — and the same run the message box's blit is built out of, so
 * src/text.c calls it too. `source` and `dest` are in/out: each comes back advanced by
 * `longwords * 4` through the 68000's address ALU, which is what a caller then adds its own row
 * skip to. It lives here rather than in the kit's machine.h because both callers are this game;
 * ../STATUS.md registers a third one as the trigger to move it. */
void copy_longwords(uint8_t *image, uint32_t *source, uint32_t *dest, unsigned longwords);


/* $79d2 / $795e — advance WB_BG_SCROLL_POS_X by WB_BG_SCROLL_STEP towards WB_BG_SCROLL_LIMIT_X
 * (right) or towards zero (left), at half rate through WB_BG_SCROLL_PENDING.
 * Returns nonzero when the original consumed its caller's next `bsr` — see the note above. */
int bg_scroll_step_right(uint8_t *image);
int bg_scroll_step_left(uint8_t *image);

/* $7c08 / $7eb2 — redraw one tile column of the current pre-shifted buffer at the window's right or
 * left edge: clear the pixels the step vacated, then rotate the map's tiles into the gap. */
void bg_scroll_fill_right_column(uint8_t *image);
void bg_scroll_fill_left_column(uint8_t *image);

/* $75fc / $760c — consume WB_BG_REQUEST_RIGHT / _LEFT, step, and fill unless the step said not to. */
void bg_scroll_serve_right(uint8_t *image);
void bg_scroll_serve_left(uint8_t *image);

/* $761c / $77ba — move WB_BG_SCROLL_POS_Y by WB_BG_SCROLL_STEP towards zero (up) or towards
 * WB_BG_SCROLL_LIMIT_Y (down), and with it the two ring row cursors and their sixteen buffer-row
 * pointers. There is no half-rate latch on this axis. Returns nonzero when the original consumed
 * its caller's next TWO `bsr`s — the row fill and the pre-shift together. */
int bg_scroll_step_up(uint8_t *image);
int bg_scroll_step_down(uint8_t *image);

/* $7a3e / $7b1a — copy one map row of tiles, UNROTATED, into the buffer row the corresponding step
 * uncovered, and step WB_BG_TILE_ROW past the scanline pair just drawn (before the draw going up,
 * after it going down). Returns the original's d0: WB_BG_ROW_DRAWN_TOP / _BOTTOM in its low word,
 * over the last tile's byte offset — bg_scroll_preshift_rows' argument, sign and all. */
uint32_t bg_scroll_fill_top_row(uint8_t *image);
uint32_t bg_scroll_fill_bottom_row(uint8_t *image);

/* $8144 — walk the row pair `drawn` names through the seven pre-shifted copies above the one it was
 * drawn into, two pixels left each time. `drawn` is a row fill's d0 and only its low word's SIGN is
 * read. */
void bg_scroll_preshift_rows(uint8_t *image, uint32_t drawn);

/* $75d4 / $75e8 — consume WB_BG_REQUEST_UP / _DOWN, step, and fill + pre-shift unless the step
 * said not to. */
void bg_scroll_serve_up(uint8_t *image);
void bg_scroll_serve_down(uint8_t *image);

/* $759a — serve every raised request byte, in the original's own order: up, down, right, left. */
void bg_scroll_serve_requests(uint8_t *image);

/* $d28 — raise one vertical and one horizontal request from where WB_SCROLL_FOLLOW_X/_Y sit
 * relative to WB_SCROLL_CENTRE_X/_Y, and return the distances (always positive) in the LOW WORDS
 * of `vertical` (d0) and `horizontal` (d1). Both are in/out: the original writes words, so each
 * caller's own high half comes back untouched. */
void bg_scroll_raise_requests(uint8_t *image, uint32_t *vertical, uint32_t *horizontal);

/* $7522 — the whole engine for one frame: raise, then drain half of each distance in two-pixel
 * steps, then clear the request and count pairs. While WB_SCROLL_FOLLOW_FROZEN is set it only
 * serves whatever is already raised. */
void bg_scroll_run_queue(uint8_t *image);


/* ---- the consumer: $82f8 and the sixteen copy routines it jumps into --------------------------
 *
 * Everything above PRODUCES the eight pre-shifted buffers; these two read one of them.
 */

/* $83b6..$8dfe — the sixteen unrolled copy routines the jump table at WB_BG_BLIT_TABLE names, as
 * ONE function. They are byte-identical apart from where each splits its thirty `move.l` about the
 * source row's 128-byte ring seam, which is exactly what `column` (WB_BG_SCROLL_X, 0..15) says — so
 * the table collapses into an argument. `source` and `dest` are the a0/a1 the dispatcher hands
 * over; `first_rows` and `second_rows` its d7 and d6, one `dbf` count each, the second negative
 * when the window did not run off the source buffer's end. */
void bg_scroll_copy_column(uint8_t *image, uint32_t column, uint32_t source, uint32_t dest,
                           uint32_t first_rows, uint32_t second_rows);

/* $82f8 — once a frame from game_main_loop: copy the visible window out of the pre-shifted buffer
 * WB_BG_SCROLL_PHASE names into WB_SCREEN_BACK, in one or two halves about the buffer's own end. */
void bg_scroll_blit(uint8_t *image);

#endif /* WONDERBOY_SCROLL_H */
