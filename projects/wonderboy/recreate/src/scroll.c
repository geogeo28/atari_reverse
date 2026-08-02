/* scroll.c — the background scroll engine, the whole cluster at $7522..$8228 plus the request
 * raiser at $d28 that drives it, and the CONSUMER at $82f8..$8dfe that reads what it produces.
 *
 * WHAT THE CLUSTER IS. The game keeps EIGHT pre-shifted copies of the level background, $5800 bytes
 * each, tiling $44000..$70000. Copy N is the map drawn two pixels further left than copy N-1, so a
 * two-pixel scroll is a change of buffer rather than a redraw, and only the ONE tile column the
 * scroll uncovers has to be produced. That is what the horizontal half does: a request byte picks a
 * direction, a step routine moves the position words, and a fill routine draws the new column into
 * the buffer the position now names. wonderboy.h's scroll block has the layout.
 *
 * THE VERTICAL HALF IS THE OTHER SHAPE OF THE SAME SCHEME. There is nothing to pre-shift vertically,
 * so its position is a ROW INDEX and the eight buffers' row pointers are simply moved; the fill then
 * copies one tile row into copy 0 UNROTATED, and `bg_scroll_preshift_rows` walks that row through the
 * remaining seven copies, `rol.l #2` at a time. That routine is the other half of the pre-shift
 * scheme and the reason the horizontal half can be a buffer switch at all.
 *
 * THE STEPS RETURN THROUGH THE STACK. A step with nothing to do does `addq.l #4,(a7)` — `#8` in the
 * vertical pair, which has TWO calls to consume — and `rts`, which returns PAST its caller's `bsr`s.
 * One act means both "no movement" and "skip the redraw". Ghidra does not model it (../decomp.c
 * shows a bare `return` and no skip), so it is read off the disassembly, and the C returns it as a
 * flag because C has no other way to say it. It is also the reason a differential case entered at a
 * step needs a second stop PC: the oracle's `rts` lands past its sentinel (see test/test_scroll.py).
 *
 * WHAT THE NAMES CLAIM is the mechanism, this region's rule. `bg_scroll_fill_right_column` says a
 * tile column is masked and rotated into the buffer at the map cursor plus WB_BG_FILL_RIGHT_MAP_OFF
 * cells; that the result is "the right-hand edge of the visible window" follows from that offset
 * being fifteen cells past the left fill's, not from anything this file proves.
 *
 * THREE THINGS THE DIFFERENTIAL CANNOT SEE, all registered in ../STATUS.md:
 *
 *   * THE REGISTERS THE FILLS LEAVE BEHIND. Both column fills walk out with a0/a1/a2/a3/a4/a6 and
 *     d0-d7 well past where they started; the oracle reports d0/d1/a0/a1 only, and the two call
 *     sites ($75fc/$760c) `rts` immediately after, so there is nothing to compare against anyway.
 *     The two ROW fills are the exception: their d0 IS an output, read by the routine after them.
 *   * THE RUNAWAY COUNTS. Every `dbf` loop here takes its length from WB_BG_COL_SPLIT_TABLE or
 *     WB_BG_ROW_SPLIT_TABLE, and a count of $ffff in the FIRST word would run 65536 iterations and
 *     walk out of the buffers entirely. Reproduced by construction (the counters are `uint16_t` and
 *     the loops are do/while), and unreachable through the shipped tables, whose first words count
 *     down to 0. `bg_scroll_run_queue`'s two drains have the same SHAPE but not the same argument —
 *     their count is a halved distance rather than a table entry, and $d28 can return a negative
 *     one. See drain_requests.
 *   * THE CALLERS' REGISTER HALVES. `bg_scroll_raise_requests` returns two distances in the LOW
 *     WORDS of d0/d1 and never touches their high halves, so the caller's own are what come back.
 *     They are arguments here for exactly that reason — see its comment.
 */
#include <stdint.h>

#include "machine.h"
#include "scroll.h"
#include "wonderboy.h"

/* Both row fills end with `move.w #imm,d0`, so what they hand `bg_scroll_preshift_rows` is a marker
 * word sitting on top of the last tile's byte offset — machine.h's set_low_word, and only the
 * marker is ever tested. */
#define WORD_BITS 16u

/* The rotation the right edge uses in place of a phase of zero: `move.w #$10,d5` — a whole cell, so
 * every plane word crosses into the neighbouring cell and none of it stays. */
#define BG_FULL_CELL_ROTATION 16u

/* What separates $7c08 from $7eb2. Everything else about the two fills is the same walk, so the
 * differences are stated once here rather than spelt twice below. */
typedef struct {
    uint16_t x_bias;            /* added to WB_BG_SCROLL_X before the nibble mask and the *8 */
    uint16_t map_offset;        /* ...and to WB_BG_MAP_CURSOR, to reach this edge's map column */
    int32_t second_cell;        /* where the overwritten cell sits relative to the ORed one */
    uint16_t wrap_at_scroll_x;  /* the WB_BG_SCROLL_X at which that cell leaves the 128-byte row */
    int32_t wrap_delta;         /* ...and what brings it back */
    int invert_mask;            /* $7eb2's `not.l d6`, applied only while the phase is nonzero */
    int full_cell_at_phase_zero;/* $7c08's `move.w #$10,d5 / lea -1(a3),a3` */
    int or_takes_low_half;      /* which half of the rotated longword is ORed rather than written */
} bg_edge;

static const bg_edge BG_EDGE_RIGHT = {
    .x_bias = WB_BG_FILL_RIGHT_X_BIAS,
    .map_offset = WB_BG_FILL_RIGHT_MAP_OFF,
    .second_cell = (int32_t)WB_BG_CELL_BYTES,
    .wrap_at_scroll_x = 1,
    .wrap_delta = -(int32_t)WB_BG_BUFFER_LINE,
    .invert_mask = 0,
    .full_cell_at_phase_zero = 1,
    .or_takes_low_half = 0,
};

static const bg_edge BG_EDGE_LEFT = {
    .x_bias = 0,
    .map_offset = WB_BG_FILL_LEFT_MAP_OFF,
    .second_cell = -(int32_t)WB_BG_CELL_BYTES,
    .wrap_at_scroll_x = 0,
    .wrap_delta = (int32_t)WB_BG_BUFFER_LINE,
    .invert_mask = 1,
    .full_cell_at_phase_zero = 0,
    .or_takes_low_half = 1,
};

/* The two cursors a fill's tile loop advances, and the map cell it reads next. Passed as one object
 * because the second half of a fill resumes all three where the first half left them. */
typedef struct {
    uint32_t ored;      /* a1 */
    uint32_t written;   /* a2 */
    uint32_t map;       /* a3 */
} bg_cursors;

/* Where in the pre-shifted buffers this fill's column starts: the phase picks the buffer, the
 * coarse scroll row picks the tile row within it, and WB_BG_SCROLL_X (biased, for the right edge)
 * picks the 8-byte cell within the 128-byte scanline. */
static uint32_t column_origin(const uint8_t *image, const bg_edge *edge) {
    uint32_t cursor = WB_BG_BUFFER_BASE;
    cursor = addr_add(cursor,
                      (uint32_t)be16(image + WB_BG_SCROLL_PHASE) * WB_BG_BUFFER_PHASE_STRIDE);
    cursor = addr_add(cursor,
                      (uint32_t)be16(image + WB_BG_SCROLL_Y_COARSE) * WB_BG_TILE_BLOCK_LEN);
    uint16_t cell = (uint16_t)(((be16(image + WB_BG_SCROLL_X) + edge->x_bias) & WB_BG_PHASE_MASK)
                               * WB_BG_CELL_BYTES);
    return addr_add(cursor, sign_ext16(cell));
}

/* `lea $8276,a5 / move.w (a5)+,d0 / lsl.w #2,d0 / lea (0,a5,d0.w),a5 / move.l (a5)+,$7eae`: the
 * coarse scroll row indexes a table that begins in the word immediately after it, and the pair of
 * counts is copied WHOLE into the scratch longword both halves then read back a word at a time. */
static void publish_split_counts(uint8_t *image) {
    uint16_t index = (uint16_t)(be16(image + WB_BG_SCROLL_Y_COARSE) * sizeof(uint32_t));
    wr32(image + WB_BG_FILL_COUNTS,
         be32(image + addr_add(WB_BG_COL_SPLIT_TABLE, sign_ext16(index))));
}

/* The phase's own mask word, duplicated into both halves of a longword by `swap` — so one `and.l`
 * per longword keeps exactly the pixels the two-pixel scroll did not vacate. The left edge inverts
 * it, keeping the other end of each word instead. */
static uint32_t edge_mask(const uint8_t *image, const bg_edge *edge) {
    uint16_t phase = be16(image + WB_BG_SCROLL_PHASE);
    uint16_t half = be16(image + addr_add(WB_BG_EDGE_MASK_TABLE, sign_ext16(phase)));
    uint32_t mask = ((uint32_t)half << 16) | half;
    if (edge->invert_mask && phase != 0)
        mask = ~mask;
    return mask;
}

/* `move.b (a3),d0 / add.w d0,d0 / move.w (0,a5,d0.w),d0 / lsl.l #7,d0 / lea (0,a4,d0.l),a4` — the
 * map holds a byte, WB_TILE_INDEX_TABLE turns it into a tile number, and the number scales by the
 * bitmap length. The multiply is 32-bit, so a large table entry addresses far past the tiles. */
static uint32_t tile_bitmap(const uint8_t *image, uint8_t map_cell) {
    uint16_t tile = be16(image + WB_TILE_INDEX_TABLE + map_cell * sizeof(uint16_t));
    return addr_add(WB_TILE_BITMAPS, (uint32_t)tile * WB_TILE_BITMAP_LEN);
}

/* `16 x { and.l d6,(a0)+ ; and.l d6,(a0)+ ; lea 120(a0),a0 }` under one `dbf`: `tile_rows + 1` tile
 * rows of scanlines, each having its 8-byte cell masked down. Returns the advanced cursor, which
 * the second half of the fill resumes from. */
static uint32_t clear_cells(uint8_t *image, uint32_t cursor, uint32_t mask, uint16_t tile_rows) {
    uint16_t remaining = tile_rows;
    do {
        for (unsigned row = 0; row < WB_BG_TILE_ROWS; row++) {
            for (unsigned at = 0; at < WB_BG_CELL_BYTES; at += sizeof(uint32_t)) {
                uint32_t cell = addr_add(cursor, at);
                wr32(image + cell, be32(image + cell) & mask);
            }
            cursor = addr_add(cursor, WB_BG_BUFFER_LINE);
        }
    } while (remaining-- != 0);
    return cursor;
}

/* One map cell per pass, `tile_rows + 1` of them, walking DOWN the map by its row stride. Each of a
 * tile's sixteen scanlines is four plane words rotated left as LONGWORDS, which splits every word
 * across two adjacent cells; which half is ORed into the cell that stays and which overwrites the
 * cell the scroll uncovered is the whole difference between the two edges.
 *
 * The original reads all four planes into d0-d3 before storing any, and this does the same. The two
 * cells never overlap — they are 8 or 120 bytes apart for either edge and every WB_BG_SCROLL_X — so
 * the order the two stores happen in is unobservable, and only the read/write order matters. */
static void draw_tiles(uint8_t *image, bg_cursors *at, unsigned shift, uint16_t tile_rows,
                       const bg_edge *edge) {
    uint16_t remaining = tile_rows;
    do {
        uint32_t tile = tile_bitmap(image, image[at->map]);
        at->map = addr_add(at->map, sign_ext16(be16(image + WB_MAP_ROW_STRIDE)));
        for (unsigned row = 0; row < WB_BG_TILE_ROWS; row++) {
            uint32_t rotated[WB_PLANES];
            for (unsigned plane = 0; plane < WB_PLANES; plane++)
                rotated[plane] = rotate_left32(
                    be16(image + addr_add(tile, plane * WB_PLANE_STRIDE)), shift);
            tile = addr_add(tile, WB_BG_CELL_BYTES);

            for (unsigned plane = 0; plane < WB_PLANES; plane++) {
                uint16_t low = (uint16_t)rotated[plane];
                uint16_t high = (uint16_t)(rotated[plane] >> 16);
                uint32_t ored = addr_add(at->ored, plane * WB_PLANE_STRIDE);
                uint32_t written = addr_add(at->written, plane * WB_PLANE_STRIDE);
                wr16(image + ored,
                     be16(image + ored) | (edge->or_takes_low_half ? low : high));
                wr16(image + written, edge->or_takes_low_half ? high : low);
            }
            at->ored = addr_add(at->ored, WB_BG_BUFFER_LINE);
            at->written = addr_add(at->written, WB_BG_BUFFER_LINE);
        }
    } while (remaining-- != 0);
}

/* The whole of $7c08 and $7eb2. Each draws the column in TWO halves because the buffer is a ring:
 * the first runs from the coarse scroll row to the buffer's end, then all three cursors step back
 * one whole buffer and the second runs from its start. The two counts sum to
 * WB_BG_BUFFER_TILE_ROWS - 2, so the column is always drawn exactly once over. A negative second
 * count means the window began at the buffer's top and there is no second half. */
static void fill_column(uint8_t *image, const bg_edge *edge) {
    uint32_t cleared = column_origin(image, edge);
    uint32_t written = addr_add(cleared, (uint32_t)edge->second_cell);
    if (be16(image + WB_BG_SCROLL_X) == edge->wrap_at_scroll_x)
        written = addr_add(written, (uint32_t)edge->wrap_delta);

    publish_split_counts(image);
    uint32_t mask = edge_mask(image, edge);
    bg_cursors at = {
        .ored = cleared,
        .written = written,
        .map = addr_add(WB_MAP_DATA,
                        sign_ext16((uint16_t)(be16(image + WB_BG_MAP_CURSOR) + edge->map_offset))),
    };

    uint16_t first = be16(image + WB_BG_FILL_COUNTS);
    cleared = clear_cells(image, cleared, mask, first);

    unsigned shift = be16(image + WB_BG_SCROLL_PHASE);
    if (edge->full_cell_at_phase_zero && shift == 0) {
        shift = BG_FULL_CELL_ROTATION;
        at.map = addr_add(at.map, (uint32_t)-1);
    }
    draw_tiles(image, &at, shift, first, edge);

    cleared = addr_add(cleared, (uint32_t)-(int32_t)WB_BG_BUFFER_LEN);
    at.ored = addr_add(at.ored, (uint32_t)-(int32_t)WB_BG_BUFFER_LEN);
    at.written = addr_add(at.written, (uint32_t)-(int32_t)WB_BG_BUFFER_LEN);

    uint16_t second = be16(image + WB_BG_FILL_COUNT_SECOND);
    if ((int16_t)second < 0)
        return;
    clear_cells(image, cleared, mask, second);
    draw_tiles(image, &at, shift, second, edge);
}

void bg_scroll_fill_right_column(uint8_t *image) {
    fill_column(image, &BG_EDGE_RIGHT);
}

void bg_scroll_fill_left_column(uint8_t *image) {
    fill_column(image, &BG_EDGE_LEFT);
}

/* $79d2. The latch is the half-rate divider the two steps share: a step that finds it disarmed arms
 * it and moves nothing, so the position advances on every SECOND request. Note the asymmetry with
 * $795e below — this one re-arms on any non-NEGATIVE latch, that one clears any NONZERO latch, so a
 * latch holding a small positive word behaves differently in the two directions. */
int bg_scroll_step_right(uint8_t *image) {
    if (be16(image + WB_BG_SCROLL_POS_X) == be16(image + WB_BG_SCROLL_LIMIT_X))
        return 1;
    if ((int16_t)be16(image + WB_BG_SCROLL_PENDING) >= 0) {
        wr16(image + WB_BG_SCROLL_PENDING, WB_BG_PENDING_SET);
        return 0;
    }
    wr16(image + WB_BG_SCROLL_POS_X,
         (uint16_t)(be16(image + WB_BG_SCROLL_POS_X) + WB_BG_SCROLL_STEP));

    /* `addq.w #2,$83ac / andi.w #$f,$83ac` — the mask is what sets Z, so the cell only moves on the
     * step that carries the phase out of the nibble. */
    uint16_t phase = (uint16_t)((be16(image + WB_BG_SCROLL_PHASE) + WB_BG_SCROLL_STEP)
                                & WB_BG_PHASE_MASK);
    wr16(image + WB_BG_SCROLL_PHASE, phase);
    if (phase != 0)
        return 0;

    wr16(image + WB_BG_ROW_BYTE_OFFSET,
         (uint16_t)(be16(image + WB_BG_ROW_BYTE_OFFSET) + WB_BG_CELL_BYTES));
    wr16(image + WB_BG_MAP_CURSOR, (uint16_t)(be16(image + WB_BG_MAP_CURSOR) + 1));
    uint16_t column = (uint16_t)((be16(image + WB_BG_SCROLL_X) + 1) & WB_BG_PHASE_MASK);
    wr16(image + WB_BG_SCROLL_X, column);
    if (column == 0)
        wr16(image + WB_BG_ROW_BYTE_OFFSET, 0);
    return 0;
}

/* $795e — the mirror, with two asymmetries the port reproduces rather than tidies: the phase
 * UNDERFLOWS into an explicit WB_BG_PHASE_LAST instead of wrapping through the nibble mask, and the
 * row offset is masked to WB_BG_ROW_OFFSET_MASK where $79d2 lets it grow unmasked. */
int bg_scroll_step_left(uint8_t *image) {
    if (be16(image + WB_BG_SCROLL_POS_X) == 0)
        return 1;
    if (be16(image + WB_BG_SCROLL_PENDING) != 0) {
        wr16(image + WB_BG_SCROLL_PENDING, 0);
        return 0;
    }
    wr16(image + WB_BG_SCROLL_POS_X,
         (uint16_t)(be16(image + WB_BG_SCROLL_POS_X) - WB_BG_SCROLL_STEP));

    uint16_t phase = (uint16_t)(be16(image + WB_BG_SCROLL_PHASE) - WB_BG_SCROLL_STEP);
    if ((int16_t)phase >= 0) {
        wr16(image + WB_BG_SCROLL_PHASE, phase & WB_BG_PHASE_MASK);
        return 0;
    }
    wr16(image + WB_BG_SCROLL_PHASE, WB_BG_PHASE_LAST);

    wr16(image + WB_BG_MAP_CURSOR, (uint16_t)(be16(image + WB_BG_MAP_CURSOR) - 1));
    wr16(image + WB_BG_ROW_BYTE_OFFSET,
         (uint16_t)(be16(image + WB_BG_ROW_BYTE_OFFSET) - WB_BG_CELL_BYTES)
         & WB_BG_ROW_OFFSET_MASK);
    uint16_t column = (uint16_t)((be16(image + WB_BG_SCROLL_X) - 1) & WB_BG_PHASE_MASK);
    wr16(image + WB_BG_SCROLL_X, column);
    if (column == 0)
        wr16(image + WB_BG_ROW_BYTE_OFFSET, 0);
    return 0;
}

/* $75fc / $760c — one request served. The request byte is CONSUMED, cleared before anything else
 * happens, exactly as the status panel's three table walks consume theirs. */
void bg_scroll_serve_right(uint8_t *image) {
    image[WB_BG_REQUEST_RIGHT] = 0;
    if (bg_scroll_step_right(image))
        return;
    bg_scroll_fill_right_column(image);
}

void bg_scroll_serve_left(uint8_t *image) {
    image[WB_BG_REQUEST_LEFT] = 0;
    if (bg_scroll_step_left(image))
        return;
    bg_scroll_fill_left_column(image);
}


/* ---- the vertical half ------------------------------------------------------------------------
 *
 * Where the horizontal steps move a phase and let the buffer switch do the work, these move a ring
 * ROW INDEX and the eight cached row pointers that must stay equal to
 * `WB_BG_BUFFER_BASE + copy * WB_BG_BUFFER_LEN + row * WB_BG_BUFFER_LINE`. There are two such
 * cursors — the visible window's top scanline pair and its bottom one — and each wraps on its own
 * test, which is why the wrap reload writes a WHOLE set of pointers rather than adjusting them. */

/* One cursor's step. `wrap_from` is the row at which it must reload instead of move, `wrap_to` what
 * it reloads to, and `row_delta` the two rows it moves otherwise — the pointers follow at
 * `row_delta * WB_BG_BUFFER_LINE`, which is the `$100` both directions spell as a literal. */
static void step_row_cursor(uint8_t *image, uint32_t row_word, uint32_t first_pointer,
                            uint16_t wrap_from, uint16_t wrap_to, int16_t row_delta) {
    if (be16(image + row_word) == wrap_from) {
        wr16(image + row_word, wrap_to);
        for (unsigned copy = 0; copy < WB_BG_BUFFERS; copy++)
            wr32(image + first_pointer + copy * WB_BG_BUFFER_ROW_PAIR,
                 WB_BG_BUFFER_BASE + copy * WB_BG_BUFFER_LEN + wrap_to * WB_BG_BUFFER_LINE);
        return;
    }
    wr16(image + row_word, (uint16_t)(be16(image + row_word) + (uint16_t)row_delta));
    for (unsigned copy = 0; copy < WB_BG_BUFFERS; copy++) {
        uint32_t at = first_pointer + copy * WB_BG_BUFFER_ROW_PAIR;
        wr32(image + at,
             addr_add(be32(image + at), (uint32_t)(row_delta * (int32_t)WB_BG_BUFFER_LINE)));
    }
}

/* The whole of a vertical step below its boundary test: both cursors, then the coarse row. Each
 * cursor takes the SAME wrap and delta but keeps its own row word, so a step that reached the wrap
 * on one and not the other moves one and reloads the other.
 *
 * The coarse row (`asr.w #4,$83a8`) is read by the two COLUMN fills, which is the one place the two
 * halves of the engine meet — and only the TOP cursor feeds it. */
static void move_row_cursors(uint8_t *image, uint16_t wrap_from, uint16_t wrap_to,
                             int16_t row_delta) {
    step_row_cursor(image, WB_BG_SCROLL_Y, WB_BG_BUFFER_ROWS + WB_BG_BUFFER_ROW_TOP,
                    wrap_from, wrap_to, row_delta);
    step_row_cursor(image, WB_BG_SCROLL_Y_BOTTOM, WB_BG_BUFFER_ROWS + WB_BG_BUFFER_ROW_BOTTOM,
                    wrap_from, wrap_to, row_delta);
    wr16(image + WB_BG_SCROLL_Y_COARSE,
         (uint16_t)((int16_t)be16(image + WB_BG_SCROLL_Y) >> WB_BG_Y_COARSE_SHIFT));
}

/* $761c / $77ba. Both return nonzero when the original consumed its caller's next TWO `bsr`s
 * (`addq.l #8,(a7)`): the row fill AND the pre-shift are skipped together.
 *
 * The two boundary tests are NOT mirror images — up compares against 0 and down against
 * WB_BG_SCROLL_LIMIT_Y — and neither is the ring wrap: up reloads when the row IS 0 (`tst.w`) and
 * down when it IS WB_BG_SCROLL_Y_LAST (`cmpi.w`), so a row that starts off the 0..$ae grid wraps in
 * one direction and runs away in the other. Both reproduced rather than tidied. */
int bg_scroll_step_up(uint8_t *image) {
    if (be16(image + WB_BG_SCROLL_POS_Y) == 0)
        return 1;
    wr16(image + WB_BG_SCROLL_POS_Y,
         (uint16_t)(be16(image + WB_BG_SCROLL_POS_Y) - WB_BG_SCROLL_STEP));
    move_row_cursors(image, 0, WB_BG_SCROLL_Y_LAST, -(int16_t)WB_BG_SCROLL_STEP);
    return 0;
}

int bg_scroll_step_down(uint8_t *image) {
    if (be16(image + WB_BG_SCROLL_POS_Y) == be16(image + WB_BG_SCROLL_LIMIT_Y))
        return 1;
    wr16(image + WB_BG_SCROLL_POS_Y,
         (uint16_t)(be16(image + WB_BG_SCROLL_POS_Y) + WB_BG_SCROLL_STEP));
    move_row_cursors(image, WB_BG_SCROLL_Y_LAST, 0, (int16_t)WB_BG_SCROLL_STEP);
    return 0;
}


/* The two cursors a row fill's cell loop advances. Passed as one object because the second half of
 * a fill resumes both where the first left them — the map pointer especially, which is NOT re-based
 * between the halves the way the destination is. */
typedef struct {
    uint32_t dest;      /* a1 */
    uint32_t map;       /* a6 */
} bg_row_cursors;

/* One half of a row fill: `cells + 1` map cells, each contributing WB_BG_ROW_FILL_SCANLINES
 * scanlines of one WB_BG_CELL_BYTES cell, copied out of the tile bitmap UNROTATED. `tile_byte_offset`
 * is WB_BG_TILE_ROW, the byte offset within the 128-byte bitmap that names which scanline pair.
 *
 * Returns the 68000's d0 as the loop leaves it: the LAST tile's byte offset (`move.w (0,a5,d0.w),d0
 * / lsl.l #7,d0`). Both fills then stamp their marker into its low word and hand the whole longword
 * to bg_scroll_preshift_rows, so the high half travels with it and is worth reproducing. */
static uint32_t copy_row_cells(uint8_t *image, bg_row_cursors *at, uint16_t cells,
                               uint16_t tile_byte_offset) {
    uint32_t tile_offset = 0;
    uint16_t remaining = cells;
    do {
        uint16_t tile = be16(image + WB_TILE_INDEX_TABLE + image[at->map] * sizeof(uint16_t));
        at->map = addr_add(at->map, 1);
        tile_offset = (uint32_t)tile * WB_TILE_BITMAP_LEN;
        uint32_t source = addr_add(addr_add(WB_TILE_BITMAPS, tile_offset),
                                   sign_ext16(tile_byte_offset));

        for (unsigned scanline = 0; scanline < WB_BG_ROW_FILL_SCANLINES; scanline++) {
            for (unsigned byte = 0; byte < WB_BG_CELL_BYTES; byte += sizeof(uint32_t)) {
                uint32_t from = addr_add(source, scanline * WB_BG_CELL_BYTES + byte);
                uint32_t to = addr_add(at->dest, scanline * WB_BG_BUFFER_LINE + byte);
                wr32(image + to, be32(image + from));
            }
        }
        at->dest = addr_add(at->dest, WB_BG_CELL_BYTES);
    } while (remaining-- != 0);
    return tile_offset;
}

/* The body both row fills share. Like the column fills it draws in TWO halves — the buffer row is a
 * 128-byte RING and the seam sits at WB_BG_ROW_BYTE_OFFSET — but the wrap is horizontal, so between
 * them only the destination steps back, by one whole scanline. A negative second count means the
 * seam was at the row's start and there is no second half. */
static uint32_t fill_buffer_row(uint8_t *image, uint32_t row_pointer, uint16_t map_offset) {
    bg_row_cursors at = {
        .dest = addr_add(be32(image + row_pointer),
                         sign_ext16(be16(image + WB_BG_ROW_BYTE_OFFSET))),
        .map = addr_add(WB_MAP_DATA_ROW, sign_ext16(map_offset)),
    };
    uint16_t index = (uint16_t)(be16(image + WB_BG_SCROLL_X) * sizeof(uint32_t));
    uint32_t counts = addr_add(WB_BG_ROW_SPLIT_TABLE, sign_ext16(index));
    uint16_t tile_byte_offset = be16(image + WB_BG_TILE_ROW);

    uint32_t drawn = copy_row_cells(image, &at, be16(image + counts), tile_byte_offset);
    at.dest = addr_add(at.dest, (uint32_t)-(int32_t)WB_BG_BUFFER_LINE);

    uint16_t second = be16(image + addr_add(counts, WB_BG_STATE_WORD_LEN));
    if ((int16_t)second < 0)
        return drawn;
    return copy_row_cells(image, &at, second, tile_byte_offset);
}

/* $7a3e. The tile row steps BACK first — and a step past the top of the bitmap pulls the map cursor
 * back one map row — because the scanline pair being redrawn is the one the step just uncovered
 * ABOVE the window. $7b1a is the mirror and does the same step AFTER its draw. */
uint32_t bg_scroll_fill_top_row(uint8_t *image) {
    uint16_t row = (uint16_t)(be16(image + WB_BG_TILE_ROW) - WB_BG_TILE_ROW_STEP);
    if ((int16_t)row < 0)
        wr16(image + WB_BG_MAP_CURSOR,
             (uint16_t)(be16(image + WB_BG_MAP_CURSOR) - be16(image + WB_MAP_ROW_STRIDE)));
    wr16(image + WB_BG_TILE_ROW, (uint16_t)(row & WB_BG_TILE_ROW_MASK));

    uint32_t drawn = fill_buffer_row(image, WB_BG_BUFFER_ROWS + WB_BG_BUFFER_ROW_TOP,
                                     be16(image + WB_BG_MAP_CURSOR));
    return set_low_word(drawn, WB_BG_ROW_DRAWN_TOP);
}

uint32_t bg_scroll_fill_bottom_row(uint8_t *image) {
    uint16_t map_offset = (uint16_t)(be16(image + WB_BG_MAP_CURSOR)
                                     + WB_BG_BOTTOM_ROW_STRIDES * be16(image + WB_MAP_ROW_STRIDE));
    uint32_t drawn = fill_buffer_row(image, WB_BG_BUFFER_ROWS + WB_BG_BUFFER_ROW_BOTTOM, map_offset);

    uint16_t row = (uint16_t)((be16(image + WB_BG_TILE_ROW) + WB_BG_TILE_ROW_STEP)
                              & WB_BG_TILE_ROW_MASK);
    if (row == 0)
        wr16(image + WB_BG_MAP_CURSOR,
             (uint16_t)(be16(image + WB_BG_MAP_CURSOR) + be16(image + WB_MAP_ROW_STRIDE)));
    wr16(image + WB_BG_TILE_ROW, row);
    return set_low_word(drawn, WB_BG_ROW_DRAWN_BOTTOM);
}


/* $8144 — the pre-shift, and the other half of the eight-copy scheme.
 *
 * A cell's four plane words are rotated left as LONGWORDS by WB_BG_PRESHIFT_BITS, which puts the two
 * pixels that leave the top of each word in the rotated longword's HIGH half. The low half is
 * WRITTEN to the cell, the high half is ORed into the cell BEFORE it — so a whole row shifts two
 * pixels left in one pass, and the bits that fall off the row's start come round to its end. That
 * wrap is what WB_BG_PRESHIFT_CARRY parks: cell 0's carry, ORed into cell 15 when the row is done. */

static void read_plane_words(const uint8_t *image, uint32_t at, uint16_t *words) {
    for (unsigned plane = 0; plane < WB_PLANES; plane++)
        words[plane] = be16(image + addr_add(at, plane * WB_PLANE_STRIDE));
}

static void write_plane_words(uint8_t *image, uint32_t at, const uint16_t *words) {
    for (unsigned plane = 0; plane < WB_PLANES; plane++)
        wr16(image + addr_add(at, plane * WB_PLANE_STRIDE), words[plane]);
}

static void or_plane_words(uint8_t *image, uint32_t at, const uint16_t *words) {
    for (unsigned plane = 0; plane < WB_PLANES; plane++) {
        uint32_t word_at = addr_add(at, plane * WB_PLANE_STRIDE);
        wr16(image + word_at, (uint16_t)(be16(image + word_at) | words[plane]));
    }
}

/* One cell read and rotated: `shifted` is what lands in the cell, `carried` what belongs to its
 * left-hand neighbour. The 68000 reads all four planes into d0-d3 before storing any, and so does
 * this — the two destinations are eight bytes apart, so only the read/write order can matter. */
static void rotate_cell(const uint8_t *image, uint32_t cell, uint16_t *shifted, uint16_t *carried) {
    read_plane_words(image, cell, shifted);
    for (unsigned plane = 0; plane < WB_PLANES; plane++) {
        uint32_t rotated = rotate_left32(shifted[plane], WB_BG_PRESHIFT_BITS);
        shifted[plane] = (uint16_t)rotated;
        carried[plane] = (uint16_t)(rotated >> WORD_BITS);
    }
}

/* One 128-byte buffer row, shifted two pixels left into the copy above it. Advances both cursors to
 * the next scanline, which is how the two rows of a pair run under one loop. */
static void preshift_one_row(uint8_t *image, uint32_t *source, uint32_t *dest) {
    uint16_t shifted[WB_PLANES];
    uint16_t carried[WB_PLANES];

    rotate_cell(image, *source, shifted, carried);
    *source = addr_add(*source, WB_BG_CELL_BYTES);
    write_plane_words(image, *dest, shifted);
    write_plane_words(image, WB_BG_PRESHIFT_CARRY, carried);
    *dest = addr_add(*dest, WB_BG_CELL_BYTES);

    for (unsigned cell = 1; cell < WB_BG_ROW_CELLS; cell++) {
        rotate_cell(image, *source, shifted, carried);
        *source = addr_add(*source, WB_BG_CELL_BYTES);
        or_plane_words(image, addr_add(*dest, (uint32_t)-(int32_t)WB_BG_CELL_BYTES), carried);
        write_plane_words(image, *dest, shifted);
        *dest = addr_add(*dest, WB_BG_CELL_BYTES);
    }

    read_plane_words(image, WB_BG_PRESHIFT_CARRY, carried);
    or_plane_words(image, addr_add(*dest, (uint32_t)-(int32_t)WB_BG_CELL_BYTES), carried);
}

/* `drawn` is the row fills' d0: its LOW WORD's sign is the whole selector (`tst.w d0 / bmi`), which
 * is exactly what WB_BG_ROW_DRAWN_TOP and WB_BG_ROW_DRAWN_BOTTOM are. */
void bg_scroll_preshift_rows(uint8_t *image, uint32_t drawn) {
    uint32_t pair_member = ((int16_t)(uint16_t)drawn < 0)
                           ? WB_BG_BUFFER_ROW_BOTTOM : WB_BG_BUFFER_ROW_TOP;
    uint32_t source = be32(image + WB_BG_BUFFER_ROWS + pair_member);
    uint32_t dest = addr_add(source, WB_BG_BUFFER_LEN);

    for (unsigned copy = 0; copy < WB_BG_PRESHIFT_COPIES; copy++) {
        for (unsigned row = 0; row < WB_BG_PRESHIFT_ROWS; row++)
            preshift_one_row(image, &source, &dest);
        /* `lea -256(a1),a0 / lea $5800(a0),a1`: the copy just written becomes the next one's
         * source, so nothing re-reads the row pointers and the walk is a chain. */
        source = addr_add(dest, (uint32_t)-(int32_t)(WB_BG_PRESHIFT_ROWS * WB_BG_BUFFER_LINE));
        dest = addr_add(source, WB_BG_BUFFER_LEN);
    }
}


/* $75d4 / $75e8 — one vertical request served. Same shape as the horizontal pair, with one more
 * call under the same skip: the row fill's d0 IS the pre-shift's argument. */
void bg_scroll_serve_up(uint8_t *image) {
    image[WB_BG_REQUEST_UP] = 0;
    if (bg_scroll_step_up(image))
        return;
    bg_scroll_preshift_rows(image, bg_scroll_fill_top_row(image));
}

void bg_scroll_serve_down(uint8_t *image) {
    image[WB_BG_REQUEST_DOWN] = 0;
    if (bg_scroll_step_down(image))
        return;
    bg_scroll_preshift_rows(image, bg_scroll_fill_bottom_row(image));
}


/* ---- the tier above: raise, queue, dispatch ---------------------------------------------------- */

/* $759a. Four `tst.b`/`beq`/`bsr` in line, not a dispatch table — and the order is the original's:
 * up, down, RIGHT, left. Each handler consumes its own byte, so a pass can serve all four. */
void bg_scroll_serve_requests(uint8_t *image) {
    if (image[WB_BG_REQUEST_UP])
        bg_scroll_serve_up(image);
    if (image[WB_BG_REQUEST_DOWN])
        bg_scroll_serve_down(image);
    if (image[WB_BG_REQUEST_RIGHT])
        bg_scroll_serve_right(image);
    if (image[WB_BG_REQUEST_LEFT])
        bg_scroll_serve_left(image);
}

/* $d28. Raises one horizontal and one vertical request byte from where the followed object sits
 * relative to WB_SCROLL_CENTRE_X/_Y, and returns the two distances — negated, so both come back
 * positive — in d0 (vertical) and d1 (horizontal).
 *
 * They are IN/OUT arguments because the original writes only the low words (`move.w`, `neg.w`), so
 * each caller's own high half is what it gets back. Nothing observes that: the one caller does
 * `asr.w` and `move.w` on both. Passing them makes the register interface exact anyway, which is
 * what lets a case compare the oracle's whole d0/d1 rather than half of each.
 *
 * WHICH SIDE THE OBJECT IS ON IS NOT THE SIGN OF THE DIFFERENCE. `subi.w` sets the overflow flag and
 * `bgt`/`blt` read it, so the test is a signed 16-bit comparison of the POSITION against the centre,
 * not of the wrapped difference against zero. A position of $8000 gives a difference of $7fd0, which
 * reads positive on its own and yet takes the `blt` arm. The DISTANCE returned is still the wrapped
 * difference — value and flags part company here, which is exactly what the two are. */
void bg_scroll_raise_requests(uint8_t *image, uint32_t *vertical, uint32_t *horizontal) {
    int16_t follow_y = (int16_t)be16(image + WB_SCROLL_FOLLOW_Y);
    uint16_t from_centre_y = (uint16_t)((uint16_t)follow_y - WB_SCROLL_CENTRE_Y);
    if (follow_y > (int16_t)WB_SCROLL_CENTRE_Y) {
        image[WB_BG_RAISED_V_DOWN] = WB_BG_RAISED_SET;
    } else if (follow_y < (int16_t)WB_SCROLL_CENTRE_Y) {
        image[WB_BG_RAISED_V_UP] = WB_BG_RAISED_SET;
        from_centre_y = (uint16_t)-from_centre_y;
    }
    *vertical = set_low_word(*vertical, from_centre_y);

    int16_t follow_x = (int16_t)be16(image + WB_SCROLL_FOLLOW_X);
    uint16_t from_centre_x = (uint16_t)((uint16_t)follow_x - WB_SCROLL_CENTRE_X);
    if (follow_x < (int16_t)WB_SCROLL_CENTRE_X) {
        image[WB_BG_RAISED_H_LEFT] = WB_BG_RAISED_SET;
        from_centre_x = (uint16_t)-from_centre_x;
    } else if (follow_x > (int16_t)WB_SCROLL_CENTRE_X) {
        image[WB_BG_RAISED_H_RIGHT] = WB_BG_RAISED_SET;
    }
    *horizontal = set_low_word(*horizontal, from_centre_x);
}

/* One of the two drains: serve the raised pair `count_word` times, two pixels each. The count word
 * is re-read from the image every pass because the original re-reads it (`tst.w`/`subq.w` on
 * memory), and a serve could in principle write it — nothing in the image does, but the loop's
 * shape is the claim, not the outcome. A count that arrived NEGATIVE runs its own value in passes
 * rather than none — 32,768 to 65,535 of them — because the loop tests against zero and counts DOWN.
 * $d28 can produce one: a follow position of $8000 comes back as a distance of $8030, which the
 * `asr.w #1` above turns into $c018, i.e. 49,176 passes. Reproduced by construction and left
 * unreached — what keeps it unreached is the range of the game's own follow positions, which this
 * batch did not establish, and NOT the range of what $d28 can return. */
static void drain_requests(uint8_t *image, uint32_t count_word, uint32_t raised, uint32_t request) {
    while (be16(image + count_word) != 0) {
        wr16(image + count_word, (uint16_t)(be16(image + count_word) - 1));
        /* A WORD move of a byte PAIR — which is how the down/right bytes are raised at all: neither
         * has a writer of its own anywhere in the image. */
        wr16(image + request, be16(image + raised));
        bg_scroll_serve_requests(image);
    }
}

/* $7522, once a frame from game_main_loop ($4d0, the image's only reference to it). */
void bg_scroll_run_queue(uint8_t *image) {
    if (be16(image + WB_SCROLL_FOLLOW_FROZEN) != 0) {
        bg_scroll_serve_requests(image);
        return;
    }

    /* Zero rather than the original's own entry d0/d1, which are whatever game_main_loop left: the
     * only reads of either are the `asr.w` and `move.w` below, both word ops, so no high half the
     * caller could supply is ever observed. */
    uint32_t vertical = 0;
    uint32_t horizontal = 0;
    bg_scroll_raise_requests(image, &vertical, &horizontal);
    /* `asr.w #1` on each: the distances are in pixels and a step is WB_BG_SCROLL_STEP of them. */
    wr16(image + WB_BG_QUEUE_V_COUNT, (uint16_t)((int16_t)(uint16_t)vertical >> 1));
    wr16(image + WB_BG_QUEUE_H_COUNT, (uint16_t)((int16_t)(uint16_t)horizontal >> 1));

    drain_requests(image, WB_BG_QUEUE_H_COUNT, WB_BG_RAISED_H, WB_BG_REQUEST_LEFT);
    drain_requests(image, WB_BG_QUEUE_V_COUNT, WB_BG_RAISED_V, WB_BG_REQUEST_UP);

    /* Two `clr.l`, each covering a PAIR: $7596/$7598 and $7592/$7594. */
    wr32(image + WB_BG_RAISED_V, 0);
    wr32(image + WB_BG_QUEUE_H_COUNT, 0);
}


/* ---- the consumer: $82f8 and the sixteen copy routines it jumps into ---------------------------
 *
 * Everything above PRODUCES the eight pre-shifted buffers; this reads one. Once a frame
 * bg_scroll_blit copies the visible window out of the buffer WB_BG_SCROLL_PHASE names into
 * WB_SCREEN_BACK, and BOTH of the rings the engine maintains surface here as a SPLIT rather than as
 * arithmetic:
 *
 *   * VERTICALLY the window may run off the end of the 176-scanline buffer, so the copy is two
 *     halves with a `lea -$5800(a0),a0` between them — d7 scanlines before the buffer's end and d6
 *     after it, d6 negative meaning there is no second half.
 *   * HORIZONTALLY each source ROW is a 128-byte ring whose seam sits at WB_BG_SCROLL_X, so a
 *     SCANLINE is two runs of `move.l` with a `lea -128(a0),a0` between them.
 *
 * THE SECOND SPLIT IS THE ONLY THING SEPARATING THE SIXTEEN unrolled routines the jump table names,
 * which is why one parametrised function is all sixteen of them: test/test_scroll.py assembles each
 * variant from this same pattern and pins it against the image, so the collapse is verified rather
 * than assumed.
 *
 * WHAT C CANNOT REPRODUCE, stated because it is the one place this port is narrower than the
 * original: `movea.l (0,a2,d1.w),a2` indexes the table with WB_BG_SCROLL_X * 4 and bounds nothing,
 * so a column outside 0..15 would make the original jump through whatever longword follows the
 * table (which is WB_BG_SCROLL_X itself). A whole-image abs.l scan gives that word exactly three
 * writers — the two horizontal steps, both ending in `andi.w #$f`, and the `clr.w` at $fb7e — so
 * the domain really is 0..15; `column` outside it has no defined behaviour here and cannot have.
 */

/* Declared in scroll.h and shared with src/text.c — see the note there. */
void copy_longwords(uint8_t *image, uint32_t *source, uint32_t *dest, unsigned longwords) {
    for (unsigned at = 0; at < longwords; at++) {
        wr32(image + *dest, be32(image + *source));
        *source = addr_add(*source, sizeof(uint32_t));
        *dest = addr_add(*dest, sizeof(uint32_t));
    }
}

/* How much of the scanline comes out of the source row before the copy reaches the row's END. The
 * column starts WB_BG_CELL_LONGWORDS * column into a row of WB_BG_ROW_LONGWORDS, so columns 0 and 1
 * never reach it at all — which is why their two variants are the twelve bytes shorter ones. */
static unsigned longwords_before_the_seam(uint32_t column) {
    return WB_BG_ROW_LONGWORDS - WB_BG_CELL_LONGWORDS * column;
}

static void copy_one_scanline(uint8_t *image, uint32_t column, uint32_t *source, uint32_t *dest) {
    unsigned before_seam = longwords_before_the_seam(column);
    int wraps = before_seam < WB_BG_BLIT_LONGWORDS;

    copy_longwords(image, source, dest, wraps ? before_seam : WB_BG_BLIT_LONGWORDS);
    if (wraps) {
        /* `lea -128(a0),a0` — back to the START of the same source row, not on to the next one. */
        *source = addr_add(*source, (uint32_t)-(int32_t)WB_BG_BUFFER_LINE);
        copy_longwords(image, source, dest, WB_BG_BLIT_LONGWORDS - before_seam);
    }
    /* `lea 40(a1),a1` on to the next SCREEN scanline, and `addq.l #8,a0` (or `lea 136(a0),a0`,
     * which is that plus the row the wrap above rewound) on to the same column of the next source
     * row. Both variants therefore leave a0 advanced by exactly one WB_BG_BUFFER_LINE. */
    *dest = addr_add(*dest, WB_SCREEN_LINE - WB_BG_BLIT_ROW_BYTES);
    *source = addr_add(*source, WB_BG_CELL_BYTES + (wraps ? WB_BG_BUFFER_LINE : 0));
}

/* One half of a variant: `rows + 1` scanlines under a single `dbf`, so a count that arrived
 * NEGATIVE would run 65536 of them. Reproduced by construction (`uint16_t`, do/while) and out of
 * reach through bg_scroll_blit, whose two counts always sum to WB_BG_BLIT_SCANLINES. */
static void copy_scanlines(uint8_t *image, uint32_t column, uint32_t *source, uint32_t *dest,
                           uint16_t rows) {
    uint16_t remaining = rows;
    do {
        copy_one_scanline(image, column, source, dest);
    } while (remaining-- != 0);
}

void bg_scroll_copy_column(uint8_t *image, uint32_t column, uint32_t source, uint32_t dest,
                           uint32_t first_rows, uint32_t second_rows) {
    copy_scanlines(image, column, &source, &dest, (uint16_t)first_rows);
    if ((int16_t)(uint16_t)second_rows < 0)
        return;
    /* `lea -$5800(a0),a0`: the first half ran off the buffer's end, so the second starts one whole
     * buffer back — the same column of the row 176 scanlines earlier, i.e. the buffer's own top. */
    source = addr_add(source, (uint32_t)-(int32_t)WB_BG_BUFFER_LEN);
    copy_scanlines(image, column, &source, &dest, (uint16_t)second_rows);
}

/* $82f8. Three position words become one source address, one screen address and the two `dbf`
 * counts; the jump table then picks the variant WB_BG_SCROLL_X names, which here is `column`. */
void bg_scroll_blit(uint8_t *image) {
    uint16_t phase = be16(image + WB_BG_SCROLL_PHASE);
    uint16_t row = be16(image + WB_BG_SCROLL_Y);
    uint16_t column = be16(image + WB_BG_SCROLL_X);

    uint32_t dest = addr_add(be32(image + WB_SCREEN_BACK), WB_BG_BLIT_SCREEN_ORIGIN);
    /* `mulu.w` is a 32-bit product and its `lea` a longword index, but the row's `asl.w #7` and the
     * column's `asl.w #3` are WORD shifts indexed a word at a time — so the buffer is picked in 32
     * bits and the offset within it in 16, sign-extended. */
    uint32_t source = addr_add(WB_BG_BUFFER_BASE, (uint32_t)phase * WB_BG_BUFFER_PHASE_STRIDE);
    source = addr_add(source, sign_ext16((uint16_t)(row << WB_BG_BLIT_ROW_SHIFT)));
    source = addr_add(source, sign_ext16((uint16_t)(column * WB_BG_CELL_BYTES)));

    /* `subi.w #$10,d6 / bpl` — the sign of the WRAPPED difference, because `bpl` reads N alone. */
    uint16_t first;
    uint16_t second;
    if ((int16_t)(uint16_t)(row - WB_BG_BLIT_WRAP_ROW) < 0) {
        first = WB_BG_BLIT_SCANLINES - 1;
        second = WB_BG_BLIT_NO_SECOND_HALF;
    } else {
        /* `move.w #$b0,d7 / sub.w $83a8,d7 / move.w #$9f,d6 / sub.w d7,d6 / subq.w #1,d7`: the two
         * halves are "to the buffer's end" and "the rest", and they sum to the window's height. */
        uint16_t to_the_end = (uint16_t)(WB_BG_BUFFER_SCANLINES - row);
        second = (uint16_t)((WB_BG_BLIT_SCANLINES - 1) - to_the_end);
        first = (uint16_t)(to_the_end - 1);
    }
    bg_scroll_copy_column(image, column, source, dest, first, second);
}
