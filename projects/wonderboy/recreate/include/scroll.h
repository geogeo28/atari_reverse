/* scroll.h — the background scroll engine's HORIZONTAL half (src/scroll.c).
 *
 * Six routines out of the cluster at $7522..$8228: the two request handlers `$75fc`/`$760c`, the
 * two position steps under them, and the two column fills those steps gate. `$759a` dispatches to
 * the pair on request bytes something else raises, and `$7522` above it drains a queue of such
 * requests; both are named in ../names.txt and queued in ../STATUS.md with the whole VERTICAL half
 * ($761c/$77ba/$7a3e/$7b1a/$8144/$75d4/$75e8), which is where they belong.
 *
 * WHAT A STEP RETURNS is not in a register. A step that has nothing to do adds to its own RETURN
 * ADDRESS (`addq.l #4,(a7)`), which lands the caller past its `bsr` to the fill — so "no work" and
 * "the fill is skipped" are one act, invisible to Ghidra (../decomp.c shows a plain `return`) and
 * read off the disassembly. The C returns that decision as a flag and the request handler honours
 * it, which is the only way to write it in C at all.
 *
 * Every ADDRESS these touch is a global named in wonderboy.h, which both languages read; this
 * header carries no constant of its own.
 */
#ifndef WONDERBOY_SCROLL_H
#define WONDERBOY_SCROLL_H

#include <stdint.h>

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

#endif /* WONDERBOY_SCROLL_H */
