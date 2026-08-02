/* scroll.c — the background scroll engine's horizontal half ($75fc, $760c and the four routines
 * under them), out of the cluster at $7522..$8228.
 *
 * WHAT THE CLUSTER IS. The game keeps EIGHT pre-shifted copies of the level background, $5800 bytes
 * each, tiling $44000..$70000. Copy N is the map drawn two pixels further left than copy N-1, so a
 * two-pixel scroll is a change of buffer rather than a redraw, and only the ONE tile column the
 * scroll uncovers has to be produced. That is what these six routines do: a request byte something
 * else raises picks a direction, a step routine moves the position words, and a fill routine draws
 * the new column into the buffer the position now names. wonderboy.h's scroll block has the layout.
 *
 * THE STEPS RETURN THROUGH THE STACK. A step with nothing to do does `addq.l #4,(a7)` and `rts`,
 * which returns PAST its caller's `bsr` to the fill — one act that means both "no movement" and
 * "skip the redraw". Ghidra does not model it (../decomp.c shows a bare `return` and no skip), so
 * it is read off the disassembly, and the C returns it as a flag because C has no other way to say
 * it. It is also the reason a differential case entered at a step needs a second stop PC: the
 * oracle's `rts` lands four bytes past its sentinel (see test/test_scroll.py).
 *
 * WHAT THE NAMES CLAIM is the mechanism, this region's rule. `bg_scroll_fill_right_column` says a
 * tile column is masked and rotated into the buffer at the map cursor plus WB_BG_FILL_RIGHT_MAP_OFF
 * cells; that the result is "the right-hand edge of the visible window" follows from that offset
 * being fifteen cells past the left fill's, not from anything this file proves.
 *
 * TWO THINGS THE DIFFERENTIAL CANNOT SEE, both registered in ../STATUS.md:
 *
 *   * THE REGISTERS THE FILLS LEAVE BEHIND. Both walk out with a0/a1/a2/a3/a4/a6 and d0-d7 well
 *     past where they started; the oracle reports d0/d1/a0/a1 only, and the two call sites
 *     ($75fc/$760c) `rts` immediately after, so there is nothing to compare against anyway.
 *   * THE RUNAWAY COUNTS. Both `dbf` loops take their length from WB_BG_COL_SPLIT_TABLE, and a
 *     count of $ffff in the FIRST word would run 65536 tile rows and walk out of the buffers
 *     entirely. Reproduced by construction (the counters are `uint16_t` and the loops are
 *     do/while), and unreachable through the shipped table, whose first words are 10 down to 0.
 */
#include <stdint.h>

#include "machine.h"
#include "scroll.h"
#include "wonderboy.h"

/* `rol.l d5,dn`. The count is a memory word here (a phase, 0..14) or the literal 16 the right edge
 * substitutes for a phase of zero — a RUNTIME value, unlike src/hud.c's rotate, whose count is
 * always the literal 4 or 8. So this one has to survive a count of 0, where the 68000 rotates by
 * nothing and C's `value >> 32` would be undefined. That guard is the whole difference between the
 * two, and the reason they are not one helper. */
static uint32_t rotate_left32_by_register(uint32_t value, unsigned count) {
    if (count == 0)
        return value;
    return (value << count) | (value >> (32 - count));
}

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
                rotated[plane] = rotate_left32_by_register(
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
