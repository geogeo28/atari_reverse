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

#include "machine.h"      /* the copy run below is CURSOR_BARRIER + the image accessors */
#include "wonderboy.h"    /* WB_LONGWORD_BYTES */

/* ---- the copy run every blit in this game is built out of --------------------------------------
 *
 * The 68000 has no block move, so a copy is a run of `move.l (a0)+,(a1)+` at 20 cycles a longword —
 * and the original spends nothing else on any of its blits. The sixteen background variants below,
 * the message box's row (src/text.c) and the stage builder's tile row (src/stage.c) are all STRAIGHT
 * runs with no loop control at all, because every one of those lengths is fixed where the run is
 * assembled. All three lengths are compile-time constants in this port too, so the run below
 * reproduces them exactly — which is why nothing here takes a length that arrives at run time.
 *
 * It lives in this header rather than in the kit's machine.h because every user is this game;
 * ../STATUS.md holds that registration on its reason rather than a count — trigger = a user in
 * ANOTHER project, home = tools/recreate_kit/include/machine.h. What DID belong to the kit is the
 * codegen barrier the run is built on, and it is there: machine.h's CURSOR_BARRIER.
 */

/* One `move.l (a0)+,(a1)+`. The cursors are taken by pointer so that the runs below can share one
 * body; inlined into a pair of locals it is that single instruction, which is what CURSOR_BARRIER
 * is for (machine.h states the measurement).
 *
 * THE BARRIER IS ONE OF TWO ALIASING WORKAROUNDS IN THE TREE and they are opposites, which is worth
 * knowing from either end: this one HIDES a relationship GCC would otherwise exploit (that the two
 * cursors are one base plus constants), while src/blit.c's `blit_sprite_rows` copies the caller's
 * register file into a LOCAL to destroy one GCC has to assume (that a store through `image` may hit
 * `*regs`), so that the file can live in registers for the whole blit. */
static inline void copy_one_longword(const uint8_t **from, uint8_t **to) {
    wr32(*to, be32(*from));
    *from += WB_LONGWORD_BYTES;
    *to += WB_LONGWORD_BYTES;
    CURSOR_BARRIER(*from);
    CURSOR_BARRIER(*to);
}

/* The longest run the ladder below can spell, and so the longest any caller may ask for. Every
 * length in the game is checked against it where that length is defined — a `_Static_assert` per
 * caller, since a run this cannot spell would silently copy NOTHING. */
#define COPY_CONSTANT_RUN_MAX_LONGWORDS 30u

/* A Duff-style fallthrough of COPY_CONSTANT_RUN_MAX_LONGWORDS `copy_one_longword`, which is a
 * STRAIGHT RUN of exactly `longwords` of them whenever `longwords` is a constant: GCC folds a
 * `switch` on a value it knows before it emits any test at all, so nothing of the ladder survives
 * (checked on the target's own codegen, and the tree is built -fno-jump-tables so there is no table
 * to fall back on).
 *
 * WHY NOT A `for` OVER THE CONSTANT: GCC re-rolls that into a counted loop on -m68000 — the measured
 * `move.l (a1)+,(a0)+ / cmpa.l a0,a2 / bne`, ~36 cycles a longword — which is the whole cost this is
 * here to be rid of.
 *
 * THE CURSORS ARE WALKED THROUGH THE RUN rather than advanced by the caller afterwards, which is
 * what leaves the postincrement chain unbroken from one end of a scanline to the other: the
 * background blit's mid-scanline `lea` adjusts the SAME a0 its first run left behind. */
static inline __attribute__((always_inline))
void copy_constant_run(const uint8_t **from, uint8_t **to, unsigned longwords) {
#define COPY_LONGWORD_STEP(n) case (n): copy_one_longword(from, to); __attribute__((fallthrough))
    switch (longwords) {
    COPY_LONGWORD_STEP(30); COPY_LONGWORD_STEP(29); COPY_LONGWORD_STEP(28); COPY_LONGWORD_STEP(27);
    COPY_LONGWORD_STEP(26); COPY_LONGWORD_STEP(25); COPY_LONGWORD_STEP(24); COPY_LONGWORD_STEP(23);
    COPY_LONGWORD_STEP(22); COPY_LONGWORD_STEP(21); COPY_LONGWORD_STEP(20); COPY_LONGWORD_STEP(19);
    COPY_LONGWORD_STEP(18); COPY_LONGWORD_STEP(17); COPY_LONGWORD_STEP(16); COPY_LONGWORD_STEP(15);
    COPY_LONGWORD_STEP(14); COPY_LONGWORD_STEP(13); COPY_LONGWORD_STEP(12); COPY_LONGWORD_STEP(11);
    COPY_LONGWORD_STEP(10); COPY_LONGWORD_STEP(9);  COPY_LONGWORD_STEP(8);  COPY_LONGWORD_STEP(7);
    COPY_LONGWORD_STEP(6);  COPY_LONGWORD_STEP(5);  COPY_LONGWORD_STEP(4);  COPY_LONGWORD_STEP(3);
    COPY_LONGWORD_STEP(2);  COPY_LONGWORD_STEP(1);
    /* DEAD, and by two separate guarantees: no caller asks for a run of none (the background blit's
     * seam is behind an `after_seam != 0` test the column's constant decides, and the other two
     * lengths are nonzero constants), and every length a caller CAN ask for is asserted at or below
     * COPY_CONSTANT_RUN_MAX_LONGWORDS where it is defined. A `switch` still needs the arm. */
    default: break;
    }
#undef COPY_LONGWORD_STEP
}

/* The run with the game's cursor contract on it: 32-bit image addresses in and out, advanced the way
 * the 68000's address ALU advances them. `source` and `dest` are in/out — each comes back moved on by
 * `longwords * 4`, wrap included, which is what a caller then adds its own row skip to. `longwords`
 * must be a compile-time constant at the call, or the ladder above stays a ladder.
 *
 * ALWAYS INLINE, because GCC's own heuristic says no to a body this size and every caller is a run of
 * `move.l` that must not begin with a `movem`/argument-push prologue — ~160 cycles apiece against the
 * ~440 the message box's twenty-two longwords cost. Behind a real call the two cursors would go back
 * to memory as well: GCC cannot prove a store through `image` misses the caller's `uint32_t *`, and
 * on -m68000 -O2 that came out as SIX instructions per longword (`movea.l a0,a3 / suba.l a2,a3 /
 * move.l (a3,a1.l),(a0)+ / addq.l #1,d0 / cmp.l d1,d0 / bcs`, ~64 cycles) against the one `move.l
 * (a0)+,(a1)+` the original spends. Inlined into locals it is that one instruction.
 *
 * Nothing observable depends on the spelling. The run is a forward longword-at-a-time copy in the
 * original's own order, so an overlapping source and destination see what they did; on the target
 * be32/wr32 ARE the aligned native accesses (machine.h), which is what lets the pair fuse into one
 * `move.l`, and on the little-endian host they stay the byte assembly the differential runs. */
static inline __attribute__((always_inline))
void copy_constant_longwords(uint8_t *image, uint32_t *source, uint32_t *dest, unsigned longwords) {
    const uint8_t *from = image + *source;
    uint8_t *to = image + *dest;
    uint32_t advanced = (uint32_t)longwords * WB_LONGWORD_BYTES;

    copy_constant_run(&from, &to, longwords);
    *source = addr_add(*source, advanced);
    *dest = addr_add(*dest, advanced);
}


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

/* $83b6..$8dfe — the dispatch into the sixteen unrolled copy routines the jump table at
 * WB_BG_BLIT_TABLE names. They are byte-identical apart from where each splits its thirty `move.l`
 * about the source row's 128-byte ring seam, which is exactly what `column` (WB_BG_SCROLL_X, 0..15)
 * says — and the port holds them as the original does, sixteen bodies with that split assembled in,
 * entered ONCE through a table by index. (They were one function taking `column` until 2026-08-26;
 * ../STATUS.md's "## Performance" carries what that cost.) `source` and `dest` are the a0/a1 the
 * dispatcher hands over; `first_rows` and `second_rows` its d7 and d6, one `dbf` count each, the
 * second negative when the window did not run off the source buffer's end. */
void bg_scroll_copy_column(uint8_t *image, uint32_t column, uint32_t source, uint32_t dest,
                           uint32_t first_rows, uint32_t second_rows);

/* $82f8 — once a frame from game_main_loop: copy the visible window out of the pre-shifted buffer
 * WB_BG_SCROLL_PHASE names into WB_SCREEN_BACK, in one or two halves about the buffer's own end. */
void bg_scroll_blit(uint8_t *image);

#endif /* WONDERBOY_SCROLL_H */
