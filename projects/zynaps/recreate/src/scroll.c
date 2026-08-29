/* scroll.c — the level map, the off-screen page ring and the column emitters.
 *
 * include/scroll.h's header comment lays out how the four groups here fit together. What they have
 * in common is that all of them are pure image-to-image work over the game's own buffers: no trap,
 * no hardware address, and only one global read between them (`scroll_prefill_hide_screen`).
 */
#include "machine.h"
#include "scroll.h"
#include "video.h"

/* One `move.l (a1)+,(a0)+` run. The 68000 has no block move, so every copy in this file is a run of
 * longwords; every span either end of one is a multiple of eight bytes, so the run never has an odd
 * tail to deal with. */
static void copy_longs(uint8_t *image, uint32_t src, uint32_t dst, unsigned bytes) {
    for (unsigned offset = 0; offset < bytes; offset += 4)
        wr32(image + addr_add(dst, offset), be32(image + addr_add(src, offset)));
}

/* ================================================================================================
 * map_rle_decompress @ 0x15920 — 1 call site (0x10a08, `_start`, right after the level file is
 * read into A_tile_set_base).
 *
 * The stream is a flat sequence of tokens with no per-row header: one pass per MAP ROW, each
 * consuming tokens until it has emitted 400 columns' worth. A token's sign bit picks the kind —
 * clear = that many LITERAL tile words follow, set = a length whose low 15 bits repeat the ONE tile
 * word that follows. Both write down the column stride, so a row pass strides 36 bytes 400 times
 * and the next pass starts two bytes along; the unpacked map is therefore COLUMN-MAJOR, which is
 * what the scroller wants (it consumes one column per 16 pixels of travel).
 *
 * THE COLUMN BUDGET IS CHECKED ONLY BETWEEN TOKENS (`tst.w d6` at the top of the loop), so a token
 * whose length overshoots 400 is not clipped — it runs to its own end and leaves the budget
 * NEGATIVE, and the pass then continues because the test is against zero rather than against a
 * sign. MEASURED, not assumed: decoding all twelve shipped LEV*.MAP streams gives 641 to 1,448
 * tokens each, no overshoot anywhere, and every stream consumed to exactly its own file length. The
 * loop is still transcribed as the original's `!= 0` rather than as a `> 0`, because that is the
 * instruction and a `> 0` reading would silently repair a corrupt stream instead of reproducing
 * it.
 * ============================================================================================= */
void map_rle_decompress(uint8_t *image) {
    uint32_t src = A_tile_set_base;
    uint32_t column_top = A_map_unpacked;

    for (unsigned row = 0; row < MAP_ROWS; row++) {
        uint32_t dst = column_top;
        uint16_t remaining = MAP_COLUMNS;

        while (remaining != 0) {
            uint16_t token = be16(image + src);
            src = addr_add(src, 2);

            unsigned run = (token & MAP_RUN_FLAG) != 0;
            unsigned cells = loop_passes(run ? (uint16_t)(token & MAP_RUN_LENGTH_MASK) : token,
                                         COUNT_MASK_WORD);
            uint16_t tile = 0;
            if (run) {
                tile = be16(image + src);
                src = addr_add(src, 2);
            }

            /* A run repeats one tile; a literal span takes a fresh one per cell. Either way the
             * cells walk the same column, so the kind decides where the tile comes from and
             * nothing else. */
            for (unsigned cell = 0; cell < cells; cell++) {
                remaining--;
                if (!run) {
                    tile = be16(image + src);
                    src = addr_add(src, 2);
                }
                wr16(image + dst, tile);
                dst = addr_add(dst, MAP_COLUMN_BYTES);
            }
        }
        column_top = addr_add(column_top, 2);
    }
}

/* ================================================================================================
 * blit_page0_to_playfield @ 0x15d3e — 1 call site (0x1308c, the front end's compose step).
 *
 * `move.w #$167f,d0` + `move.l (a1)+,(a0)+`: one playfield straight from the backdrop page onto
 * whichever buffer `screen_back` names. The same 23040 bytes `clear_backdrop_page0` zeroes.
 * ============================================================================================= */
void blit_page0_to_playfield(uint8_t *image) {
    copy_longs(image, A_backdrop_page0, be32(image + A_screen_back), PLAYFIELD_BYTES);
}

/* ================================================================================================
 * scroll_page_to_screen_p00 @ 0x15d56 .. _p19 @ 0x16284 — twenty entry points, reached only
 * through `scroll_blit_jump_table` (0x179aa) indexed by the column phase at 0x198a6 (call site
 * 0x1119e, with A6 = screen_back and A5 = the current page).
 *
 * Each copies 144 rows of SCROLL_WINDOW_BYTES from the page to the screen. The page is a RING one
 * screen row wide: the window starts `SCROLL_PHASE_STEP * (phase + 1)` bytes into the row, runs to
 * the row's end, and picks up the rest from the row's START — the wrap stays inside the same row.
 * Phase 19's start is 160, which is 0, so it is the one that does not wrap; phase 0's window is
 * [8, 160), the one that ends exactly at the row end. The last cell of the screen row (bytes 152 to
 * 160) is never written here — that is the right-edge column the two emitters below own.
 *
 * WHAT THE TWENTY BODIES ACTUALLY DIFFER IN is the chunking, not the result: each is a hand-unrolled
 * run of `movem.l` pairs whose register sets are cut to land the wrap on a movem boundary (phase 2
 * copies 48+48+40 then 16, phase 12 copies 48+8 then 48+48, and so on). A movem pair reads a whole
 * chunk before storing any of it, so the chunk boundaries would be observable IF the page and the
 * screen overlapped — they never can: a page is one of the eight 0x5a00 buffers at
 * `map_page_table` (0x1798a) and the screen is a framebuffer at 0x70300/0x78000. The reconstruction
 * therefore copies the window in order and STATUS.md records the chunking as unmodelled.
 * ============================================================================================= */
static void scroll_page_to_screen(uint8_t *image, uint32_t page, uint32_t screen, unsigned phase) {
    unsigned start = (SCROLL_PHASE_STEP * (phase + 1)) % SCREEN_ROW_BYTES;
    unsigned head = SCREEN_ROW_BYTES - start;        /* bytes from `start` to the row's end */

    if (head > SCROLL_WINDOW_BYTES)                  /* phase 19: start 0, so nothing wraps */
        head = SCROLL_WINDOW_BYTES;

    for (unsigned row = 0; row < PLAYFIELD_ROWS; row++) {
        copy_longs(image, addr_add(page, start), screen, head);
        copy_longs(image, page, addr_add(screen, head), SCROLL_WINDOW_BYTES - head);
        page = addr_add(page, SCREEN_ROW_BYTES);
        screen = addr_add(screen, SCREEN_ROW_BYTES);
    }
}

/* The twenty entries are spelt out rather than generated, so that greping ../names.txt's name for
 * one of them lands on it here. The jump table below is the original's own (0x179aa). */
void scroll_page_to_screen_p00(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 0); }
void scroll_page_to_screen_p01(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 1); }
void scroll_page_to_screen_p02(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 2); }
void scroll_page_to_screen_p03(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 3); }
void scroll_page_to_screen_p04(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 4); }
void scroll_page_to_screen_p05(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 5); }
void scroll_page_to_screen_p06(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 6); }
void scroll_page_to_screen_p07(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 7); }
void scroll_page_to_screen_p08(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 8); }
void scroll_page_to_screen_p09(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 9); }
void scroll_page_to_screen_p10(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 10); }
void scroll_page_to_screen_p11(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 11); }
void scroll_page_to_screen_p12(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 12); }
void scroll_page_to_screen_p13(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 13); }
void scroll_page_to_screen_p14(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 14); }
void scroll_page_to_screen_p15(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 15); }
void scroll_page_to_screen_p16(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 16); }
void scroll_page_to_screen_p17(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 17); }
void scroll_page_to_screen_p18(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 18); }
void scroll_page_to_screen_p19(uint8_t *image, uint32_t page, uint32_t screen) { scroll_page_to_screen(image, page, screen, 19); }

/* ================================================================================================
 * scroll_emit_column_shift2 @ 0x169f2 (2 call sites: 0x10d5c, 0x110f6) and
 * scroll_emit_column_shift0 @ 0x16a56 (1: 0x110fe).
 *
 * Both drain the 32-pixel column workspace `scroll_emit_tile_column` filled, emitting its VISIBLE
 * half — one 16-pixel cell of four planes — into the page and into the screen's right-edge column,
 * two screen rows per pass for 72 passes. A workspace cell is eight longwords: four planes of row
 * `2n`, then four of row `2n + 1`, each holding 32 pixels of which the top 16 are on screen.
 *
 * The pair differ in one step. `_shift2` first shifts every longword left by two pixels and writes
 * the workspace back, so the next pass emits a column two pixels further along; `_shift0` emits the
 * workspace untouched and leaves it alone, which is what the scroller uses while the scroll is
 * frozen. Both then take the HIGH word of each longword (`swap` + `movem.w`, which stores the low
 * words), because that is the half that is on screen.
 *
 * `scroll_prefill_hide_screen` redirects the edge destination onto the page destination while the
 * pages are being pre-filled with the display hidden — the same 8 bytes are then written twice into
 * the page and never onto the screen.
 * ============================================================================================= */
#define SCROLL_COLUMN_CELL_BYTES (SCROLL_COLUMN_CELL_LONGS * 4u)
#define SCROLL_COLUMN_ROWS_PER_PASS (SCROLL_COLUMN_CELL_LONGS / SCROLL_COLUMN_ROW_LONGS)

static void scroll_emit_column(uint8_t *image, uint32_t workspace, uint32_t page, uint32_t edge,
                               unsigned shift_bits) {
    if (image[A_scroll_prefill_hide_screen] != 0)
        edge = page;

    for (unsigned pass = 0; pass < SCROLL_COLUMN_PASSES; pass++) {
        uint32_t cell[SCROLL_COLUMN_CELL_LONGS];

        for (unsigned i = 0; i < SCROLL_COLUMN_CELL_LONGS; i++)
            cell[i] = be32(image + addr_add(workspace, 4u * i));
        if (shift_bits != 0) {
            for (unsigned i = 0; i < SCROLL_COLUMN_CELL_LONGS; i++)
                cell[i] <<= shift_bits;
            for (unsigned i = 0; i < SCROLL_COLUMN_CELL_LONGS; i++)
                wr32(image + addr_add(workspace, 4u * i), cell[i]);
        }
        workspace = addr_add(workspace, SCROLL_COLUMN_CELL_BYTES);

        /* `swap` then `movem.w`, which stores the LOW words — so what lands on screen is each
         * longword's high half. The page row is written whole and then the edge row is, because
         * that is two `movem.w`s and not four interleaved pairs; with the prefill flag set the two
         * destinations are the same address and the second pass simply rewrites the first's bytes. */
        for (unsigned row = 0; row < SCROLL_COLUMN_ROWS_PER_PASS; row++) {
            const uint32_t *planes = &cell[row * SCROLL_COLUMN_ROW_LONGS];

            for (unsigned plane = 0; plane < SCROLL_COLUMN_ROW_LONGS; plane++)
                wr16(image + addr_add(page, 2u * plane), (uint16_t)(planes[plane] >> 16));
            for (unsigned plane = 0; plane < SCROLL_COLUMN_ROW_LONGS; plane++)
                wr16(image + addr_add(edge, 2u * plane), (uint16_t)(planes[plane] >> 16));
            page = addr_add(page, SCREEN_ROW_BYTES);
            edge = addr_add(edge, SCREEN_ROW_BYTES);
        }
    }
}

void scroll_emit_column_shift2(uint8_t *image, uint32_t workspace, uint32_t page, uint32_t edge) {
    scroll_emit_column(image, workspace, page, edge, SCROLL_COLUMN_SHIFT_BITS);
}

void scroll_emit_column_shift0(uint8_t *image, uint32_t workspace, uint32_t page, uint32_t edge) {
    scroll_emit_column(image, workspace, page, edge, 0);
}

/* ================================================================================================
 * scroll_emit_tile_column @ 0x162c2 — 2 call sites (0x10d28 in the section's page pre-fill, and
 * 0x110b8 in the frame loop's scroll advance). A6 = the map cursor, A5 = the page's own column,
 * A0 = the screen's right-edge column (`screen_back + 152`).
 *
 * This is the step ahead of the two emitters above: it fills the workspace they drain. Eighteen
 * tile rows, eight pixel rows each, 144 rows in all — one whole playfield-height column — and each
 * of those rows is written THREE times over:
 *
 *   * to the screen's right-edge column and to the page's column, both as the NEAR tile's four
 *     plane words, one 16-pixel cell;
 *   * to the workspace as four LONGWORDS, each one `near word : far word` — 32 pixels of which the
 *     left 16 are what the screen and the page just received. That pairing is the whole point: the
 *     emitters shift the workspace left two pixels a frame, so the far tile's pixels walk into the
 *     visible half one step at a time and the scroll is smooth between two whole tiles.
 *
 * THE FAR TILE IS THE NEXT MAP COLUMN'S, at the same row (`move.w 34(a6),d1` after the `(a6)+`).
 * So a call reads two adjacent columns and advances the cursor by one, which is what the caller
 * stores back into `map_ptr`.
 *
 * FOUR ARMS, ONE BODY. Bit 15 of a map word flips its tile VERTICALLY, and the original writes the
 * eight-row body out four times over — near flipped or not, crossed with far flipped or not — so
 * that each cursor is a straight `(aN)+` or a `lea 56` start and a `lea -8` step with no test in the
 * inner loop. 1,840 bytes of code for one loop that reads its direction out of a struct here. The
 * arms also differ in whether they mask the index with `and.w #$7fff`: they mask only the side whose
 * bit 15 they have just branched on, because the other side's is known clear. Masking both
 * unconditionally is therefore the same arithmetic, and it is what makes one body serve four.
 *
 * `scroll_prefill_hide_screen` redirects the SCREEN destination onto the page, exactly as it does
 * for the two emitters: while the pages are being pre-filled with the display hidden, the column is
 * written into the page twice and never onto the screen.
 * ============================================================================================= */

/* One side of the pair: where the tile's next row is, and which way the cursor walks it. */
typedef struct {
    uint32_t at;
    uint32_t row_step;   /* forward, or backward for a vertically flipped tile */
} tile_cursor;

static tile_cursor tile_cursor_for(uint16_t map_word) {
    /* `moveq #$0,dN` before `move.w (a6)+,dN`, so the index is the unsigned 16-bit value, and
     * `lsl.l #6,dN` scales it as a longword. */
    uint32_t base = addr_add(A_tile_set_base,
                             (uint32_t)(map_word & SCROLL_TILE_INDEX_MASK) * SCROLL_TILE_BYTES);
    tile_cursor cursor;

    if ((map_word & SCROLL_TILE_FLIP_FLAG) != 0) {
        cursor.at = addr_add(base, SCROLL_TILE_LAST_ROW);
        cursor.row_step = (uint32_t)(-(int32_t)SCROLL_TILE_ROW_BYTES);
    } else {
        cursor.at = base;
        cursor.row_step = SCROLL_TILE_ROW_BYTES;
    }
    return cursor;
}

/* `movem.w (aN)+,#$000f` (or `movem.w (aN),#$000f` + `lea -8(aN),aN`): one tile row's four plane
 * words, and the cursor steps to the row this tile's direction calls next. */
static void take_tile_row(const uint8_t *image, tile_cursor *cursor, uint16_t *planes) {
    for (unsigned plane = 0; plane < SCROLL_COLUMN_ROW_LONGS; plane++)
        planes[plane] = be16(image + addr_add(cursor->at, 2u * plane));
    cursor->at = addr_add(cursor->at, cursor->row_step);
}

/* `movem.w #$000f,(aN)` + `lea 160(aN),aN`: the four plane words as one 16-pixel cell, then down a
 * screen row. */
static void put_column_row(uint8_t *image, uint32_t *at, const uint16_t *planes) {
    for (unsigned plane = 0; plane < SCROLL_COLUMN_ROW_LONGS; plane++)
        wr16(image + addr_add(*at, 2u * plane), planes[plane]);
    *at = addr_add(*at, SCREEN_ROW_BYTES);
}

uint32_t scroll_emit_tile_column(uint8_t *image, uint32_t screen_edge, uint32_t page,
                                 uint32_t map_column) {
    uint32_t workspace = A_scroll_col_workspace;

    if (image[A_scroll_prefill_hide_screen] != 0)
        screen_edge = page;

    for (unsigned tile_row = 0; tile_row < MAP_ROWS; tile_row++) {
        tile_cursor near_tile = tile_cursor_for(be16(image + map_column));
        tile_cursor far_tile;

        map_column = addr_add(map_column, 2);      /* `move.w (a6)+,d0` */
        far_tile = tile_cursor_for(be16(image + addr_add(map_column, SCROLL_MAP_PEEK_NEXT)));

        for (unsigned pixel_row = 0; pixel_row < SCROLL_TILE_PIXEL_ROWS; pixel_row++) {
            uint16_t near_planes[SCROLL_COLUMN_ROW_LONGS];
            uint16_t far_planes[SCROLL_COLUMN_ROW_LONGS];

            /* The original's order, and it is an order: the near row is read and BOTH its
             * destinations written before the far row is read at all. */
            take_tile_row(image, &near_tile, near_planes);
            put_column_row(image, &screen_edge, near_planes);
            put_column_row(image, &page, near_planes);
            take_tile_row(image, &far_tile, far_planes);

            /* `swap dN` then `move.w d(N+4),dN` — the near word into the high half, the far word
             * into the low. */
            for (unsigned plane = 0; plane < SCROLL_COLUMN_ROW_LONGS; plane++)
                wr32(image + addr_add(workspace, 4u * plane),
                     ((uint32_t)near_planes[plane] << 16) | far_planes[plane]);
            workspace = addr_add(workspace, 4u * SCROLL_COLUMN_ROW_LONGS);
        }
    }
    return map_column;
}

/* ================================================================================================
 * Glue.
 *
 * Register maps: the twenty blits take A5 = page, A6 = screen; the two emitters take A0 = the
 * workspace, A1 = the page column, A2 = the screen's right-edge column. The other two take no
 * arguments — every address they touch is absolute or comes from `screen_back`.
 * ============================================================================================= */
void g_map_rle_decompress(uint8_t *image) {
    map_rle_decompress(image);
}

void g_blit_page0_to_playfield(uint8_t *image) {
    blit_page0_to_playfield(image);
}

/* The original's own jump table (0x179aa), so the glue takes the phase the game indexes it by
 * rather than needing twenty ctypes bindings for twenty one-line entry points. */
static void (*const scroll_blit_jump_table[SCROLL_PHASES])(uint8_t *, uint32_t, uint32_t) = {
    scroll_page_to_screen_p00, scroll_page_to_screen_p01, scroll_page_to_screen_p02,
    scroll_page_to_screen_p03, scroll_page_to_screen_p04, scroll_page_to_screen_p05,
    scroll_page_to_screen_p06, scroll_page_to_screen_p07, scroll_page_to_screen_p08,
    scroll_page_to_screen_p09, scroll_page_to_screen_p10, scroll_page_to_screen_p11,
    scroll_page_to_screen_p12, scroll_page_to_screen_p13, scroll_page_to_screen_p14,
    scroll_page_to_screen_p15, scroll_page_to_screen_p16, scroll_page_to_screen_p17,
    scroll_page_to_screen_p18, scroll_page_to_screen_p19,
};

void g_scroll_page_to_screen(uint8_t *image, uint32_t phase, uint32_t page, uint32_t screen) {
    if (phase < SCROLL_PHASES)
        scroll_blit_jump_table[phase](image, page, screen);
}

void g_scroll_emit_column_shift2(uint8_t *image, uint32_t workspace, uint32_t page, uint32_t edge) {
    scroll_emit_column_shift2(image, workspace, page, edge);
}

void g_scroll_emit_column_shift0(uint8_t *image, uint32_t workspace, uint32_t page, uint32_t edge) {
    scroll_emit_column_shift0(image, workspace, page, edge);
}

/* A0 = the screen's right-edge column, A5 = the page's column, A6 = the map cursor — and A6 comes
 * back one column on, which is the routine's only register output its caller uses (0x10d2c and
 * 0x110bc both store it into `map_ptr`). */
uint32_t g_scroll_emit_tile_column(uint8_t *image, uint32_t screen_edge, uint32_t page,
                                   uint32_t map_column) {
    return scroll_emit_tile_column(image, screen_edge, page, map_column);
}
