/* stage.c — the stage loader: $fa30, $fb06, $fd46, $fe1e, $fed2 and the banner pair at
 * $e110..$e198.
 *
 * WHAT THIS TIER IS, AND WHY IT IS NOT src/scroll.c. The scroll engine MAINTAINS the eight
 * pre-shifted background buffers — one uncovered tile column or one row pair per frame, forever.
 * This is what FILLS them, once, when a stage is entered: `bg_build_buffer` draws the map's visible
 * window into copy 0 out of a tile bank, `bg_build_preshifted_copies` derives copies 1..7 from it
 * two pixels at a time, and `stage_publish_scroll_state` writes the position words, the map cursor,
 * the two limits and the sixteen buffer row pointers the engine then steps. $f95c calls the three
 * back to back and is NOT reconstructed: it ends by writing the shifter's palette through
 * set_palette and by calling into the sound module at $17adc, neither of which the harness models.
 *
 * THE SEAM WITH scroll.c IS THE SIXTEEN POINTERS, AND IT IS PINNED FROM BOTH SIDES.
 * WB_BG_BUFFER_ROWS' invariant — `WB_BG_BUFFER_BASE + copy * WB_BG_BUFFER_LEN + row *
 * WB_BG_BUFFER_LINE` — is what the vertical steps preserve; here is where the rows start at 0 and
 * WB_BG_SCROLL_Y_BOTTOM_INIT. Nothing below restates a buffer address: the sixteen longwords the
 * image carries are DERIVED from that formula and test_stage.py requires the shipped bytes to equal
 * what it derives, so a wrong buffer stride fails on the instruction bytes.
 *
 * THREE SEMANTICS THE PORT REPRODUCES RATHER THAN TIDIES, each with a case of its own:
 *
 *   * THE MAP-ROW SKIP IS NOT A SIGNED STEP BACK. `moveq #0,d7 / move.w d2,d7 / subi.w #$10,d7 /
 *     adda.l d7,a0` subtracts the sixteen columns just walked from the row stride as a WORD, in a
 *     register whose high half is ZERO, and then adds the whole LONGWORD. A stride below
 *     WB_BG_BUILD_MAP_SKIP therefore advances the map cursor by nearly 64 KB where a signed reading
 *     would step it back — see bg_build_buffer's row loop.
 *   * THE TILE INDEX IS A WORD AND THE BITMAP SHIFT IS A LONG. `lsl.l #7,d7 / lea 0(a1,d7.l),a1`
 *     over a 16-bit index reaches WB_TILE_BITMAP_LEN * 65535, so a bank pointer plus a large index
 *     is a real address rather than a wrapped one.
 *   * EACH SCANLINE OF THE PRE-SHIFT CLOSES AS A RING. The first cell's shifted-out bits are held
 *     in WB_BG_BUILD_CARRY across the whole 128-byte row and ORed into the LAST cell, so pixels
 *     leaving the left edge of a buffer row re-enter at its right. That is the same ring the
 *     horizontal scroll reads, and it is why `bg_build_preshifted_copies` cannot be written as a
 *     plain left shift.
 *
 * WHAT THE BANNER PAIR SHARES WITH src/text.c AND WHAT IT DOES NOT. The glyph geometry is
 * identical — 32 bytes, WB_TEXT_GLYPH_ROWS rows, one byte per plane at WB_PLANE_STRIDE, and the
 * same alternating one-or-seven cell advance — but the FONT is a second one (WB_BG_BANNER_FONT,
 * reached from $e158 and nowhere else in the image) and the destination line is the background
 * buffer's 128 bytes rather than the message box's 88. So the two plotters are not one routine with
 * a parameter; they are two routines over one cell layout, and the layout constants are shared
 * while the code is not.
 */
#include <stdint.h>

#include "hud.h"            /* the perfect-bonus arm IS bcd_add_score_bd70 */
#include "machine.h"
#include "scroll.h"         /* copy_longwords — a tile row is the same run of `move.l (a0)+,(a1)+` */
#include "stage.h"
#include "wonderboy.h"

#define BYTE_MASK 0xffu
#define WORD_BITS 16u
#define LONGWORD_BYTES 4u


/* --- $fa30: draw the map's visible window into pre-shifted copy 0 ------------------------------ */

/* `moveq #0,d7 / move.b (a0)+,d7` then, only while WB_STAGE_RAW_TILE_INDEX is ZERO,
 * `add.w d7,d7 / lea $21e90.l,a5 / move.w 0(a5,d7.w),d7`.
 *
 * So the index table is a property of the SHIPPED tile bank alone: $f95c raises the flag for any
 * other bank, and a raised flag makes the map's own byte the tile number. Both readings end in a
 * 16-bit value, which the caller shifts as a LONG. */
static uint32_t tile_number(const uint8_t *image, uint8_t cell) {
    if (be16(image + WB_STAGE_RAW_TILE_INDEX) != 0)
        return cell;
    return be16(image + WB_TILE_INDEX_TABLE + (uint16_t)(2u * cell));
}

/* One tile: WB_BG_TILE_ROWS rows of WB_BG_CELL_BYTES, laid down a WB_BG_BUFFER_LINE apart.
 *
 * The original walks the destination with `move.l (a1)+,(a2)+` twice and a `lea` per row, which is
 * why the last row's `lea` is WB_BG_BUILD_CELL_REWIND rather than the WB_BG_BUILD_ROW_SKIP of the
 * fifteen above it: the whole tile leaves the cursor exactly one cell further along the scanline.
 * Returned that way rather than computed by the caller, so a mutated step reaches this loop.
 *
 * The row itself is copy_longwords — the same postincrementing run the scroll's blit and the message
 * box's are built out of, and the third user src/scroll.c's registration named as the trigger. */
static uint32_t draw_tile(uint8_t *image, uint32_t bitmap, uint32_t dest) {
    for (unsigned row = 0; row < WB_BG_TILE_ROWS; row++) {
        copy_longwords(image, &bitmap, &dest, WB_BG_CELL_BYTES / LONGWORD_BYTES);
        dest = addr_add(dest, row + 1 == WB_BG_TILE_ROWS
                              ? (uint32_t)-(int32_t)WB_BG_BUILD_CELL_REWIND
                              : WB_BG_BUILD_ROW_SKIP);
    }
    return dest;
}

void bg_build_buffer(uint8_t *image, uint32_t map, uint32_t start, uint32_t tiles) {
    /* `move.w (a1)+,d0 / move.w (a1)+,d1 / move.w (a0),d2 / mulu.w d2,d1 / add.w d0,d1 /
     * lea 4(a0,d1.w),a0`: the cell index is built in a WORD and the `lea` sign-extends it, so a
     * start row past the map's own height names a cell BELOW the map rather than far above it. */
    uint16_t column = be16(image + start);
    uint16_t row = be16(image + addr_add(start, WB_BG_STATE_WORD_LEN));
    uint16_t row_stride = be16(image + addr_add(map, WB_MAP_HEADER_WIDTH));
    uint16_t cell_index = (uint16_t)(row * row_stride + column);
    uint32_t cursor = addr_add(map, sign_ext16(cell_index) + WB_MAP_HEADER_BYTES);

    uint32_t dest = WB_BG_BUFFER_BASE;
    for (unsigned tile_row = 0; tile_row < WB_BG_BUILD_TILE_ROWS; tile_row++) {
        for (unsigned tile_column = 0; tile_column < WB_BG_BUILD_TILE_COLUMNS; tile_column++) {
            uint32_t number = tile_number(image, image[cursor]);
            cursor = addr_add(cursor, 1);
            dest = draw_tile(image, addr_add(tiles, number << WB_BG_BUILD_TILE_SHIFT), dest);
        }
        dest = addr_add(dest, WB_BG_BUILD_ROW_ADVANCE);
        /* The row skip, UNSIGNED — see the file comment. `moveq` zeroes the high half and the
         * `subi.w` never reaches it, so `adda.l` adds a value in [0, $ffff]. */
        cursor = addr_add(cursor, (uint16_t)(row_stride - WB_BG_BUILD_MAP_SKIP));
    }
}


/* --- $fb06: publish the stage's scroll state --------------------------------------------------- */

/* `move.w (a0)+,d0 / lsl.w #4,d0 / subi.w #$f0,d0` — a header word of cells becomes a pixel limit.
 * Both are WORD operations over a register whose high half the caller left, and only the low word
 * is stored, so nothing above 16 bits can matter. */
static uint16_t pixel_limit(uint16_t cells, uint16_t bias) {
    return (uint16_t)((cells << WB_MAP_CELL_SHIFT) - bias);
}

void stage_publish_scroll_state(uint8_t *image) {
    uint32_t map = be32(image + WB_STAGE_MAP_PTR);
    uint32_t start = be32(image + WB_STAGE_START_PTR);

    wr16(image + WB_BG_SCROLL_LIMIT_X,
         pixel_limit(be16(image + addr_add(map, WB_MAP_HEADER_WIDTH)), WB_BG_LIMIT_X_BIAS));
    wr16(image + WB_BG_SCROLL_LIMIT_Y,
         pixel_limit(be16(image + addr_add(map, WB_MAP_HEADER_HEIGHT)), WB_BG_LIMIT_Y_BIAS));

    /* The window's top-left map cell, as a cell index and then as two pixel positions. The index is
     * the SAME `mulu.w`/`add.w` pair bg_build_buffer walks the map with, over WB_MAP_ROW_STRIDE's
     * own word rather than the level map's — the two agree only because $f95c passes the same map,
     * which nothing here establishes. */
    uint16_t column = be16(image + start);
    uint16_t row = be16(image + addr_add(start, WB_BG_STATE_WORD_LEN));
    wr16(image + WB_BG_MAP_CURSOR, (uint16_t)(row * be16(image + WB_MAP_ROW_STRIDE) + column));
    wr16(image + WB_BG_SCROLL_POS_X, (uint16_t)(column << WB_MAP_CELL_SHIFT));
    wr16(image + WB_BG_SCROLL_POS_Y, (uint16_t)(row << WB_MAP_CELL_SHIFT));

    for (unsigned plane = 0; plane < WB_PLANES; plane++)
        wr16(image + WB_BG_PRESHIFT_CARRY + plane * WB_BG_STATE_WORD_LEN, 0);
    wr16(image + WB_BG_TILE_ROW, 0);
    wr16(image + WB_BG_SCROLL_Y_COARSE, 0);
    wr16(image + WB_BG_ROW_BYTE_OFFSET, 0);
    wr16(image + WB_BG_SCROLL_X, 0);
    wr16(image + WB_BG_SCROLL_Y, 0);
    wr16(image + WB_COPYLOCK_FLAG_A, 0);
    image[WB_COPYLOCK_FLAG_B] = BYTE_MASK;      /* `st` — a Scc is a BYTE, not the word beside it */
    wr16(image + WB_BG_SCROLL_Y_BOTTOM, WB_BG_SCROLL_Y_BOTTOM_INIT);
    wr16(image + WB_BG_SCROLL_PHASE, 0);

    /* The sixteen row pointers, as WB_BG_BUFFER_ROWS' own invariant rather than as sixteen
     * constants: copy k's two cursors are its base and that base WB_BG_SCROLL_Y_BOTTOM_INIT
     * scanlines down. */
    for (unsigned copy = 0; copy < WB_BG_BUFFERS; copy++) {
        uint32_t buffer = addr_add(WB_BG_BUFFER_BASE, copy * WB_BG_BUFFER_LEN);
        uint32_t pair = WB_BG_BUFFER_ROWS + copy * WB_BG_BUFFER_ROW_PAIR;
        wr32(image + pair + WB_BG_BUFFER_ROW_TOP, buffer);
        wr32(image + pair + WB_BG_BUFFER_ROW_BOTTOM,
             addr_add(buffer, WB_BG_SCROLL_Y_BOTTOM_INIT * WB_BG_BUFFER_LINE));
    }
}


/* --- $fd46: derive pre-shifted copies 1..7 from copy 0 ----------------------------------------- */

/* One 8-byte cell, read as WB_PLANES words and rotated LEFT by WB_BG_PRESHIFT_BITS in 32 bits.
 * `moveq #0,d4 / ... / move.w (a0)+,d4 / rol.l #2,d4`: the register's high half is cleared first,
 * so the rotate is a shift and the two pixels leaving the top of each plane word land in bits 16
 * and 17 — the carry the cell to its LEFT is owed. */
static void shift_cell(const uint8_t *image, uint32_t *source, uint32_t shifted[WB_PLANES]) {
    for (unsigned plane = 0; plane < WB_PLANES; plane++) {
        shifted[plane] = rotate_left32(be16(image + *source), WB_BG_PRESHIFT_BITS);
        *source = addr_add(*source, WB_BG_STATE_WORD_LEN);
    }
}

static void write_cell_pixels(uint8_t *image, uint32_t dest, const uint32_t shifted[WB_PLANES]) {
    for (unsigned plane = 0; plane < WB_PLANES; plane++)
        wr16(image + dest + plane * WB_BG_STATE_WORD_LEN, (uint16_t)shifted[plane]);
}

static void or_cell_carry(uint8_t *image, uint32_t dest, const uint32_t carry[WB_PLANES]) {
    for (unsigned plane = 0; plane < WB_PLANES; plane++) {
        uint32_t at = dest + plane * WB_BG_STATE_WORD_LEN;
        wr16(image + at, (uint16_t)(be16(image + at) | (uint16_t)(carry[plane] >> WORD_BITS)));
    }
}

/* One 128-byte scanline of one pass. The cell whose carry a cell owes is the one to its LEFT, so
 * the walk is "step back a cell, OR the carry in, step forward and write the pixels" — and the
 * FIRST cell's carry is held in WB_BG_BUILD_CARRY until the last cell has been written, which is
 * what closes the row as a ring. */
static void shift_scanline(uint8_t *image, uint32_t *source, uint32_t *dest) {
    uint32_t shifted[WB_PLANES];

    shift_cell(image, source, shifted);
    write_cell_pixels(image, *dest, shifted);
    *dest = addr_add(*dest, WB_BG_CELL_BYTES);
    for (unsigned plane = 0; plane < WB_PLANES; plane++)
        wr16(image + WB_BG_BUILD_CARRY + plane * WB_BG_STATE_WORD_LEN,
             (uint16_t)(shifted[plane] >> WORD_BITS));

    for (unsigned cell = 0; cell < WB_BG_BUILD_CELLS_AFTER; cell++) {
        *dest = addr_add(*dest, -(int32_t)WB_BG_CELL_BYTES);
        shift_cell(image, source, shifted);
        or_cell_carry(image, *dest, shifted);
        *dest = addr_add(*dest, WB_BG_CELL_BYTES);
        write_cell_pixels(image, *dest, shifted);
        *dest = addr_add(*dest, WB_BG_CELL_BYTES);
    }

    *dest = addr_add(*dest, -(int32_t)WB_BG_CELL_BYTES);
    uint32_t held[WB_PLANES];
    for (unsigned plane = 0; plane < WB_PLANES; plane++)
        held[plane] = (uint32_t)be16(image + WB_BG_BUILD_CARRY + plane * WB_BG_STATE_WORD_LEN)
                      << WORD_BITS;
    or_cell_carry(image, *dest, held);
    *dest = addr_add(*dest, WB_BG_CELL_BYTES);
}

void bg_build_preshifted_copies(uint8_t *image) {
    /* a0 and a1 are `lea`d ONCE and never reloaded, so pass n reads copy n and writes copy n+1 —
     * each pass consumes exactly WB_BG_BUFFER_LEN and leaves the cursors one buffer on. */
    uint32_t source = WB_BG_BUFFER_BASE;
    uint32_t dest = addr_add(WB_BG_BUFFER_BASE, WB_BG_BUFFER_LEN);
    for (unsigned pass = 0; pass < WB_BG_BUILD_PASSES; pass++)
        for (unsigned line = 0; line < WB_BG_BUILD_SCANLINES; line++)
            shift_scanline(image, &source, &dest);
}


/* --- $fe1e: relocate a loaded table, once ------------------------------------------------------ */

void resource_table_relocate(uint8_t *image) {
    if (image[WB_RESOURCE_HEADER] == WB_RESOURCE_RELOCATED)
        return;
    image[WB_RESOURCE_HEADER] = WB_RESOURCE_RELOCATED;

    /* `move.w 8(a6),d7` then `dbf d7` — the count is a WORD and the loop is a do/while, so a count
     * of 0 relocates ONE record and a count of $ffff relocates 65,536. */
    uint16_t remaining = be16(image + WB_RESOURCE_HEADER + WB_RESOURCE_COUNT_OFF);
    uint32_t record = WB_RESOURCE_TABLE;
    do {
        wr32(image + record, addr_add(be32(image + record), WB_RESOURCE_TABLE));
        record = addr_add(record, WB_RESOURCE_RECORD_BYTES);
    } while (remaining-- != 0);
}


/* --- $fed2: the per-stage state reset ---------------------------------------------------------- */

void stage_reset_state(uint8_t *image) {
    uint32_t cursor = WB_STAGE_RESET_BLOCK;         /* `lea $b08.w,a0` then five `clr` postincs */
    for (unsigned i = 0; i < WB_STAGE_RESET_BLOCK_LONGS; i++) {
        wr32(image + cursor, 0);
        cursor = addr_add(cursor, LONGWORD_BYTES);
    }
    for (unsigned i = 0; i < WB_STAGE_RESET_BLOCK_WORDS; i++) {
        wr16(image + cursor, 0);
        cursor = addr_add(cursor, WB_BG_STATE_WORD_LEN);
    }

    wr16(image + WB_PANEL_FRAME_TIMER, 0);
    wr16(image + WB_PANEL_FRAME_DELAY, WB_PANEL_FRAME_DELAY_INIT);
    wr16(image + WB_PANEL_FRAME_PHASE, 0);
    wr16(image + WB_PANEL_FRAME_INDEX, 0);
    wr16(image + WB_PANEL_FRAME_SPARE, 0);

    /* `clr.l $1514.w` — ONE longword over WB_TILE_33_FLAG and WB_TILE_33_MODE together. */
    wr32(image + WB_TILE_33_FLAG, 0);

    wr16(image + WB_STATE_FLAG_A34, 0);
    wr16(image + WB_SCROLL_FOLLOW_FROZEN, 0);
    wr16(image + WB_STATE_FLAG_A30, 0);
    wr16(image + WB_STATE_FLAG_A32, 0);
    wr32(image + WB_ACTOR_TABLE_SELECTED, WB_ACTOR_TABLE_DEFAULT);

    /* The index table's last eight entries are written HERE, not shipped — `lea $21e90.l,a1 /
     * lea 496(a1),a1` then four `move.l #imm,(a1)+`. */
    static const uint32_t tail[WB_TILE_INDEX_TAIL_LONGS] = {
        0x00460047u, 0x00480049u, 0x004a004bu, 0x0040004du,
    };
    for (unsigned i = 0; i < WB_TILE_INDEX_TAIL_LONGS; i++)
        wr32(image + WB_TILE_INDEX_TAIL + LONGWORD_BYTES * i, tail[i]);
}


/* --- $e110..$e198: the banners plotted into copy 0 --------------------------------------------- */

uint32_t bg_plot_banner_glyph(uint8_t *image, uint32_t glyph, uint32_t cursor) {
    for (unsigned row = 0; row < WB_TEXT_GLYPH_ROWS; row++) {
        for (unsigned plane = 0; plane < WB_PLANES; plane++) {
            image[addr_add(cursor, plane * WB_PLANE_STRIDE)] = image[glyph];
            glyph = addr_add(glyph, 1);
        }
        cursor = addr_add(cursor, WB_BG_BUFFER_LINE);
    }
    /* `move.w a1,d0 / btst #0,d0`: the cursor's PARITY, which the eight whole scanlines above left
     * as it was on entry. An even cell shares its 8-byte plane group with the odd one after it, so
     * the advance is one byte; an odd cell's successor is the next group's first byte, seven on. */
    uint32_t advance = (cursor & 1u) ? WB_TEXT_CELL_ADVANCE_ODD : WB_TEXT_CELL_ADVANCE_EVEN;
    return addr_add(cursor, advance - WB_TEXT_GLYPH_ROWS * WB_BG_BUFFER_LINE);
}

uint32_t bg_plot_banner(uint8_t *image, uint32_t record) {
    /* `move.w (a6)+,d0 / lea 0(a1,d0.w),a1` — the record's first word is a SIGN-EXTENDED byte
     * offset into copy 0. */
    uint32_t cursor = addr_add(WB_BG_BUFFER_BASE, sign_ext16(be16(image + record)));
    record = addr_add(record, WB_BG_STATE_WORD_LEN);
    do {
        /* `moveq #0,d0 / move.b (a6)+,d0 / subi.b #$20,d0 / lsl.w #5,d0`: a BYTE subtract, so a
         * character below WB_TEXT_FIRST_GLYPH_CHAR wraps inside the low byte and indexes the far
         * end of the font rather than in front of it. */
        uint8_t index = (uint8_t)(image[record] - WB_TEXT_FIRST_GLYPH_CHAR);
        record = addr_add(record, 1);
        uint32_t glyph = addr_add(WB_BG_BANNER_FONT,
                                  sign_ext16((uint16_t)(index << WB_TEXT_GLYPH_SHIFT)));
        cursor = bg_plot_banner_glyph(image, glyph, cursor);
    } while ((image[record] & WB_BG_BANNER_END) == 0);
    /* `tst.b (a6) / bpl` does NOT consume the terminator, so a6 comes back pointing AT it. */
    return record;
}

void bg_plot_round_banner(uint8_t *image) {
    bg_plot_banner(image, WB_BG_BANNER_ROUND);
    if (be16(image + WB_HUD_METER_VALUE) != be16(image + WB_HUD_METER_MAX))
        return;
    bcd_add_score_bd70(image, WB_BG_BANNER_BONUS);
    bg_plot_banner(image, WB_BG_BANNER_PERFECT);
}

/* --- $fe4a and $fe8c: the two resets that share one tail -----------------------------------------
 *
 * Ghidra records ONE 136-byte function at $fe4a, and the whole-image scan says it is two: $fe4a has
 * a single `bsr` caller ($e59e) and $fe8c a single `jsr $fe8c.l` one ($c00, the instruction
 * immediately after the `subq.w #1,$be2.w` at $bfc). So the head is what only a NEW GAME clears —
 * the level cursor, the lives count, the effect record list, the six HUD slots — and the tail is
 * what both entrants run.
 *
 * It is in this file rather than in src/hud.c because it is the sibling of `stage_reset_state`
 * immediately below it in the image and resets the same tier of state; it reaches into the panel
 * only through `hud_draw_lives`.
 */

/* The six `clr.w`s, in the original's own order. There is no stride constant in the instruction
 * stream — six separate absolute operands — so the six names are spelt out rather than stepped. */
static const uint32_t GAME_RESET_HUD_SLOTS[WB_HUD_SLOTS] = {
    WB_HUD_SLOT_BBBE, WB_HUD_SLOT_BBC0, WB_HUD_SLOT_BBC2,
    WB_HUD_SLOT_BBC4, WB_HUD_SLOT_BBC6, WB_HUD_SLOT_BBC8,
};

void game_life_restart_reset(uint8_t *image) {
    hud_draw_lives(image);
    wr16(image + WB_HUD_METER_VALUE, WB_HUD_METER_ON_RESTART);
    wr16(image + WB_HUD_METER_MAX, WB_HUD_METER_ON_RESTART);
    wr32(image + WB_BCD_SCORE, 0);              /* `clr.l` — the score is a LONGWORD */
    wr16(image + WB_BCD_COUNTER, 0);
    wr16(image + WB_EFFECT_STATE_BD66, 0);
    wr16(image + WB_EFFECT_STATE_BD68, 0);
    wr16(image + WB_EFFECT_STATE_BD6C, 0);
    image[WB_STAGE_TUNE_LATCH] = WB_STAGE_TUNE_LATCH_RESET;
    /* Back to the list's own base, where the head has just left WB_EFFECT_RECORD_EMPTY — so a game
     * restarted this way reads as empty, while a life restarted this way does not. */
    wr32(image + WB_EFFECT_RECORD_WRITE_PTR, WB_EFFECT_RECORD_LIST);
}

void game_restart_reset(uint8_t *image) {
    wr16(image + WB_LEVEL_SEQ_INDEX, 0);
    wr16(image + WB_LIVES, WB_LIVES_ON_RESTART);
    wr16(image + WB_EFFECT_STATE_21E4, 0);
    wr16(image + WB_EFFECT_RECORD_LIST, WB_EFFECT_RECORD_EMPTY);
    for (unsigned slot = 0; slot < WB_HUD_SLOTS; slot++)
        wr16(image + GAME_RESET_HUD_SLOTS[slot], 0);
    wr16(image + WB_EFFECT_STATE_BD6A, 0);
    game_life_restart_reset(image);             /* the head's last `clr.w` FALLS THROUGH to $fe8c */
}
