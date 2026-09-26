/* The BIOS console's four SCREEN routines — $fd141c, $fd149a, $fd14de and $fd1542.
 *
 * (The fifth thing the driver writes screen with, the cursor cell inversion at $fc4a1e, is NOT here:
 * the vertical blank calls it too, so it is a `static inline` in `include/bios/vt52.h` and that header's
 * note says what the cross-file call would have cost.)
 *
 * The console driver next door ($fc42f2, `src/bios/vt52.c`) never touches the screen itself. It
 * reaches these four through LONGWORDS OF RAM in its own state block, which is how TOS 1.02 swaps
 * in the BLITTER variants ($fc47be, $fc4852, $fc48b6, $fc4936) on a Mega ST:
 *
 *      move.l  CON_VECTOR_GLYPH(a4),a5 / jsr (a5)       ; $fc4734, the glyph
 *      move.l  CON_VECTOR_SCROLL_UP(a4),a5 / jmp (a5)   ; $fc484c
 *      move.l  CON_VECTOR_SCROLL_DOWN(a4),a5 / jmp (a5) ; $fc48b0
 *      move.l  CON_VECTOR_CLEAR(a4),a5 / jmp (a5)       ; $fc4930
 *
 * SO EACH OF THESE READS ITS VECTOR AND HALTS ON ANYTHING BUT THE CPU ROUTINE, exactly as
 * `src/bios/bcon.c` reads the four BIOS device tables rather than assuming them. The captured
 * machine is a plain 1 MB ST and holds the CPU set; the blitter set is a wave of its own, and a
 * reconstruction that ran the CPU code for a machine whose vector says otherwise would be
 * describing a machine that does not exist.
 *
 * THE GEOMETRY IS ALL RAM, and that is why nothing here takes it as an argument: the screen base is
 * `_v_bas_ad` ($44e), and the cell height, the plane count, the line pitch and the text-row pitch
 * are fields of the console's block. A case that wants a different screen shape pokes them.
 *
 * THE THREE LOOP IDIOMS ARE NOT THE SAME FUNCTION, which is the one thing here worth reading twice:
 *
 *   * `subq.w #1,d7` then `.loop: <body> / dbf d7,.loop` — the two scrolls' copy — runs the body
 *     first, so a register holding N makes N passes and 0 makes 65,536 (`loop_passes`);
 *   * `bra .test / .loop: <body> / .test: dbf d7,.loop` — the clear's row loop — tests FIRST, so a
 *     register holding N makes exactly N passes and 0 makes none;
 *   * and `subq.w #1,d6 / bcs` twice before a `dbf d6` — the clear's run across one row — is how
 *     the ROM spends the left edge, the middle and the right edge out of one span count.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "machine.h"
#include "recreate.h"
#include "addrs.h"
#include "bios/vt52.h"

/* Every group of 16 screen pixels is `plane_words` words side by side, and the mask that selects a
 * pixel column inside one is the same word in each of them. */
#define ALL_PIXELS_IN_A_GROUP 0xffffu

/* Which of four one-byte column writers a plane takes, as the ROM's own `lsr.w #1,d6 / addx.w /
 * lsr.w #1,d7 / roxl.w #3,d5` index over a four-entry jump table ($fd1446) names them: this plane's
 * FOREGROUND bit above its BACKGROUND bit. Two of the four never read the font at all. */
#define PLANE_ALL_BACKGROUND 0      /* fg 0, bg 0 — `moveq #0,d5`, the column stored as zero */
#define PLANE_GLYPH_INVERTED 1      /* fg 0, bg 1 — `not.b` over the font byte */
#define PLANE_GLYPH          2      /* fg 1, bg 0 — the font byte itself */
#define PLANE_ALL_FOREGROUND 3      /* fg 1, bg 1 — `moveq #-1,d5` */

/* THE TWO BOUNDS THIS FILE CHECKS, each stated once and each a NO-OP ON TARGET — for
 * `console_screen_byte`'s reason: a bound is something a differential host has a process to abort
 * with, where the machine simply has its own address space. Keeping the `#ifdef` inside them is what
 * lets every caller below read as one line of arithmetic.
 *
 * A span is checked ONCE, at its two ends, rather than per byte, which is what lets the runs below
 * address through the cursor they advance (`machine.h`, `CURSOR_BARRIER`) instead of recomputing
 * `image + address` every longword. */
static void assert_in_ram(uint32_t at, uint32_t bytes)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    assert(bytes <= ST_RAM_BYTES && at <= ST_RAM_BYTES - bytes);
#else
    (void)at;
    (void)bytes;
#endif
}

/* ...and the FONT's bound, which is the machine's whole memory rather than its RAM: `CON_FONT_FORM`
 * is a ROM address on the captured machine and may be a RAM one on a machine that loaded a font.
 * Both ends are named by the caller, because the row stride is a SIGNED word and a negative one
 * walks the column backwards. */
static void assert_in_machine_memory(uint32_t first, uint32_t last)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    assert((first < ST_RAM_BYTES || (first >= ROM_BASE && first < ROM_BASE + ROM_BYTES))
           && (last < ST_RAM_BYTES || (last >= ROM_BASE && last < ROM_BASE + ROM_BYTES)));
#else
    (void)first;
    (void)last;
#endif
}

static uint8_t *screen_block(uint8_t *image, uint32_t at, uint32_t bytes)
{
    assert_in_ram(at, bytes);
    return image + at;
}

static const uint8_t *font_column(const uint8_t *image, uint32_t at, unsigned rows,
                                  uint16_t stride)
{
    assert_in_machine_memory(at, addr_add(at, sign_ext16(stride) * (rows - 1)));
    return image + at;
}

/* `move.l CON_VECTOR_*(a4),a5 / jmp (a5)` — the vector, checked against the one routine this file
 * reconstructs. `what` names the caller for a reader who hits the halt. */
static void require_cpu_routine(const uint8_t *image, uint32_t vector, uint32_t cpu_routine,
                                const char *what)
{
    if (be32(image + vector) != cpu_routine)
        recreate_not_reconstructed(what);
}

/* ---- $fd141c: one glyph, one byte-wide column at a time ----------------------------------------
 *
 * The font is a BITMAP whose rows are `CON_FONT_FORM_BYTES` apart and whose glyphs sit side by side
 * across it, so a glyph's column is a byte of each row; the screen cell is a byte of each scan line
 * of each plane. What the two colours do is select, PER PLANE, which of four things that byte is
 * (`PLANE_*` above) — and the ROM branches to a separate loop for each, so the two solid arms never
 * read the font. The branch is made once per plane here too; what is one loop rather than four is
 * the body it chooses between. */
static void draw_plane_column(uint8_t *image, uint32_t glyph, uint32_t cell, unsigned selector,
                              unsigned rows, uint16_t font_stride, uint16_t line_bytes)
{
    /* The ROM branches ONCE per plane, into one of four loops. So does this: the two solid arms
     * store a constant and never read the font, and the two glyph arms differ by an XOR. */
    int from_font = selector == PLANE_GLYPH || selector == PLANE_GLYPH_INVERTED;
    uint8_t solid = selector == PLANE_ALL_FOREGROUND ? 0xff : 0x00;
    uint8_t complement = selector == PLANE_GLYPH_INVERTED ? 0xff : 0x00;
    /* ...and a solid arm never dereferences it, exactly as the ROM's two `moveq` loops do not — so
     * the font's own bound is only asked about on the two arms that read it. */
    const uint8_t *from = from_font ? font_column(image, glyph, rows, font_stride) : image;
    /* The two cursors walk as POINTERS, which is what keeps the ROM's `move.b (a2),(a3)` a single
     * instruction: recomputing `image + address` inside the loop turns each store into an add, a
     * `lea` and a move (`machine.h`, CURSOR_BARRIER). The FONT's extent is checked at BOTH ends and
     * against the machine's whole memory rather than its RAM, because the boot leaves
     * `CON_FONT_FORM` pointing into the ROM; the screen column's is checked at both ends too, one
     * cell at a time, by the caller.
     *
     * NO `CURSOR_BARRIER` on either, unlike the copy runs below, and that is measured rather than an
     * oversight: both strides here are RUNTIME words GCC cannot fold into a displacement anyway, so
     * hiding them buys nothing and costs the allocator the two address registers it wants — 4288 ->
     * 4934 cycles on `bios_bconout / console glyph` (2026-09-19). The scroll's and the clear's go
     * the other way, where the step really is a literal. */
    /* The column's own extent: the last row's byte, `rows - 1` line pitches along, plus itself. */
    uint8_t *to = screen_block(image, cell, (uint32_t)(rows - 1) * sign_ext16(line_bytes) + 1);

    while (rows-- != 0) {
        *to = from_font ? (uint8_t)(*from ^ complement) : solid;
        from += sign_ext16(font_stride);
        to += sign_ext16(line_bytes);
    }
}

void console_draw_glyph(uint8_t *image, uint32_t glyph, uint32_t cell,
                        uint16_t foreground, uint16_t background)
{
    uint16_t font_stride = be16(image + CON_FONT_FORM_BYTES);
    uint16_t line_bytes = be16(image + CON_LINE_BYTES);
    unsigned rows = loop_passes(be16(image + CON_CELL_HEIGHT), COUNT_MASK_WORD);
    unsigned planes = loop_passes(be16(image + CON_PLANES), COUNT_MASK_WORD);

    require_cpu_routine(image, CON_VECTOR_GLYPH, CONOUT_GLYPH_CPU,
                        "BIOS Bconout(CON:): the console's GLYPH vector is not the CPU routine at "
                        "$fd141c — the blitter variant ($fc47be) is not reconstructed");
    while (planes-- != 0) {
        /* `lsr.w #1,d6 / addx.w d5,d5 / lsr.w #1,d7 / roxl.w #3,d5`: the foreground's next bit
         * above the background's, which is the jump table's index. Both colours are shifted down
         * once a plane, LSB first. */
        unsigned selector = ((foreground & 1u) << 1) | (background & 1u);

        foreground = (uint16_t)(foreground >> 1);
        background = (uint16_t)(background >> 1);
        draw_plane_column(image, glyph, cell, selector, rows, font_stride, line_bytes);
        cell = addr_add(cell, SCREEN_PLANE_WORD_BYTES);
    }
}

/* ---- $fd1542: one rectangle of cells, filled with the background colour -------------------------
 *
 * The ROM's shape, which the formulation below is arithmetic for. A cell is EIGHT pixels wide and a
 * screen group is SIXTEEN, so the rectangle's two edge columns land inside a group and the mask that
 * says which half of each to touch comes out of an eight-entry table in the ROM ($fd1522), indexed
 * by the two edges' parity and by whether the run spans more than one group:
 *
 *      lsr.w #1,d4 / addx.w d0,d0      ; x1's parity...
 *      lsr.w #1,d5 / addx.w d0,d0      ; ...over x2's
 *      sub.w d4,d5 / sne d5 / add.b d5,d5 / roxl.w #3,d0    ; ...and "more than one group"
 *      lea TABLE(pc,d0.w),a3           ; two words: the LEFT edge's mask and the RIGHT edge's
 *
 * Then one of three fill routines, chosen by `(planes >> 1) * 4` off a THREE-entry table ($fd15ba):
 * one word a group for a monochrome screen, two for four colours, four for sixteen. They are one
 * loop here because they are one function — the mono arm picks `and ~mask` or `or mask` where the
 * others do `and ~mask` then `or (colour & mask)`, which is the same word for a one-bit colour.
 * What is NOT the same function is the number of words a group is: `1 << (planes >> 1)`, so a
 * three-plane screen is filled two words a group while its glyphs are drawn in three. That is the
 * ROM's own inconsistency, and each routine here is faithful to its own.
 *
 * A PLANE COUNT OF SIX OR MORE INDEXES PAST THAT THREE-ENTRY TABLE and the ROM jumps through the
 * first longword of the routine below it, so this halts rather than inventing a fourth arm. */
#define CLEAR_MASK_ENTRY_BYTES 4        /* two words: the left edge's mask, then the right edge's */
#define CLEAR_MASK_RIGHT_WORD  2        /* ...and where the second of them starts */

/* `(planes >> 1) * 4` into a three-longword table: the arms are for 1, 2 and 4 planes, and the
 * count of WORDS each fills per 16-pixel group is `1 << (planes >> 1)`. */
static unsigned plane_words(uint16_t planes)
{
    unsigned arm = planes >> 1;

    if (arm >= CONOUT_CLEAR_PLANE_ARMS)
        recreate_not_reconstructed("BIOS Bconout(CON:): a screen of six or more bit planes, which "
                                   "indexes past the ROM's own three-entry fill table at $fd15ba");
    return 1u << arm;
}

/* The three arms of that table, by the number of screen WORDS one 16-pixel group is on each. */
#define CLEAR_WORDS_MONO       1        /* one bit plane: a word a group */
#define CLEAR_WORDS_TWO_PLANE  2        /* four colours: one longword */
#define CLEAR_WORDS_FOUR_PLANE 4        /* sixteen colours: two longwords, and the widest arm */

/* The background colour expanded to ONE WORD PER PLANE: all ones where that plane's bit is set. The
 * ROM builds the same thing out of `lsr.w #1,d6 / subx.l d0,d0` pairs before either loop below. */
/* `1 << (CONOUT_CLEAR_PLANE_ARMS - 1)`, which is the four-plane arm. */
#define CLEAR_MAX_PLANE_WORDS CLEAR_WORDS_FOUR_PLANE

static void expand_colour(uint16_t colour, unsigned words, uint16_t *plane_colour,
                          uint32_t *plane_pair)
{
    unsigned plane;

    for (plane = 0; plane < words; plane++)
        plane_colour[plane] = (colour & (1u << plane)) ? ALL_PIXELS_IN_A_GROUP : 0;
    /* ...and the same words PAIRED, which is the width the ROM stores a whole group in. A single
     * word pairs with nothing and is read back out of the high half. */
    for (plane = 0; plane < words; plane += 2)
        plane_pair[plane / 2] = ((uint32_t)plane_colour[plane] << 16)
                              | (plane + 1 < words ? plane_colour[plane + 1] : 0);
}

/* One 16-pixel group of one row that the run covers only PART of — the left edge or the right:
 * `and.l ~mask,(a2) / or.l colour,(a2)+`, spelt word by word because the plane count decides how
 * many words a group is. Returns the address past it. */
static uint8_t *fill_edge_group(uint8_t *at, unsigned words, uint16_t mask,
                                const uint16_t *plane_colour)
{
    unsigned plane;

    for (plane = 0; plane < words; plane++) {
        wr16(at, (uint16_t)((be16(at) & ~mask) | (plane_colour[plane] & mask)));
        at += SCREEN_PLANE_WORD_BYTES;
    }
    return at;
}

/* ...and the groups the run covers WHOLLY, which the ROM stores outright — `move.l a0,(a2)+`, with
 * no read at all, because every pixel of them becomes the background. A separate routine from the
 * edges for the cycles: the masked form above works for these too, and spending it on them cost a
 * full-screen clear 8.2x the ROM (measured 2026-09-19, and 1.4x with this).
 *
 * ONE LOOP PER PLANE COUNT, as the ROM has one fill routine per plane count, because the width of a
 * group IS the loop body. Counting the words inside the group loop instead leaves GCC a count, a
 * compare and a branch per longword and the run goes back to 2x; written out, the four-plane arm is
 * the ROM's own `move.l (a2)+ / move.l (a2)+ / dbf`. A group of a single word is the MONOCHROME
 * arm, which has no pair and stores the high half of the one it was given. */
static uint8_t *fill_whole_groups(uint8_t *at, uint16_t groups, unsigned words,
                                  const uint32_t *plane_pair)
{
    if (words == CLEAR_WORDS_FOUR_PLANE) {
        while (groups-- != 0) {
            wr32(at, plane_pair[0]);
            at += 2 * SCREEN_PLANE_WORD_BYTES;
            CURSOR_BARRIER(at);
            wr32(at, plane_pair[1]);
            at += 2 * SCREEN_PLANE_WORD_BYTES;
            CURSOR_BARRIER(at);
        }
    } else if (words == CLEAR_WORDS_TWO_PLANE) {
        while (groups-- != 0) {
            wr32(at, plane_pair[0]);
            at += 2 * SCREEN_PLANE_WORD_BYTES;
            CURSOR_BARRIER(at);
        }
    } else {
        uint16_t monochrome = (uint16_t)(plane_pair[0] >> 16);

        while (groups-- != 0) {
            wr16(at, monochrome);
            at += SCREEN_PLANE_WORD_BYTES;
            CURSOR_BARRIER(at);
        }
    }
    return at;
}

static void cpu_clear_cells(uint8_t *image, uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2)
{
    unsigned words = plane_words(be16(image + CON_PLANES));
    uint16_t left_group = (uint16_t)(x1 >> 1);
    uint16_t span = (uint16_t)((x2 >> 1) - left_group);
    uint32_t entry = CONOUT_CLEAR_MASKS + (((x1 & 1u) << 1 | (x2 & 1u)) * 2u + (span != 0))
                                          * CLEAR_MASK_ENTRY_BYTES;
    uint16_t left_mask = be16(image + entry);
    uint16_t right_mask = be16(image + entry + CLEAR_MASK_RIGHT_WORD);
    uint16_t group_bytes = (uint16_t)(words * SCREEN_PLANE_WORD_BYTES);
    uint16_t plane_colour[CLEAR_MAX_PLANE_WORDS];
    uint32_t plane_pair[CLEAR_MAX_PLANE_WORDS / 2];
    /* `move.w a5,d0 / addq.w #1,d0 / add.w d0,d0 / lsl.w d6,d0 / neg.w d0 / add.w LINE_BYTES,d0` */
    uint16_t next_row = (uint16_t)(be16(image + CON_LINE_BYTES) - (span + 1) * group_bytes);
    uint32_t at = addr_add(addr_add(be32(image + SYSVAR_V_BAS_AD),
                                    (uint32_t)y1 * be16(image + CON_ROW_BYTES)),
                           sign_ext16((uint16_t)(left_group * group_bytes)));
    /* `sub.w d1,d3 / addq.w #1,d3 / mulu.w CELL_HEIGHT,d3 / move.w d3,d7`, and then a `dbf` that
     * TESTS FIRST — so this is the pass count exactly, and zero of them is zero passes. */
    uint16_t scan_lines = (uint16_t)((uint16_t)(y2 - y1 + 1) * be16(image + CON_CELL_HEIGHT));

    expand_colour(be16(image + CON_COLOUR_BACKGROUND), words, plane_colour, plane_pair);
    while (scan_lines-- != 0) {
        /* `span + 1` groups: the left edge, then whole ones, then the right edge. A run of ONE
         * group takes the LEFT mask alone, which is the table entry that carries both edges —
         * `subq.w #1,d6 / bcs` before the ROM's own middle loop is what says so.
         *
         * The run walks as a POINTER, with its extent checked once per scan line: `image + address`
         * inside it would put an add and a `lea` in front of every store the ROM makes with a
         * postincrement (`machine.h`, CURSOR_BARRIER). */
        uint32_t run_bytes = (span + 1u) * group_bytes;
        uint8_t *run = fill_edge_group(screen_block(image, at, run_bytes),
                                       words, left_mask, plane_colour);

        if (span != 0) {
            run = fill_whole_groups(run, (uint16_t)(span - 1), words, plane_pair);
            (void)fill_edge_group(run, words, right_mask, plane_colour);
        }
        /* `adda.w a3,a2` onto the cursor the run left, which is `at + line_bytes` for every
         * geometry that fits in a word and the ROM's own wrap for one that does not. */
        at = addr_add(addr_add(at, run_bytes), sign_ext16(next_row));
    }
}

void console_clear_cells(uint8_t *image, uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2)
{
    require_cpu_routine(image, CON_VECTOR_CLEAR, CONOUT_CLEAR_CPU,
                        "BIOS Bconout(CON:): the console's CLEAR vector is not the CPU routine at "
                        "$fd1542 — the blitter variant ($fc4936) is not reconstructed");
    cpu_clear_cells(image, x1, y1, x2, y2);
}

/* ---- $fd149a and $fd14de: the two scrolls -------------------------------------------------------
 *
 * Both move whole SCAN LINES rather than cells — `move.l (a2)+,(a3)+` four times under a `dbf`, so
 * the count is scan lines times `CON_LINE_BYTES >> 4` — and both end by jumping through the CLEAR
 * vector for the row the move opened up. The only differences are the direction and which row that
 * is: scrolling up leaves the LAST row blank, scrolling down leaves `row` itself blank.
 *
 * `move.w row_bytes,d0 / mulu.w d0,d1 / adda.w d1,a3` is a 32-bit product added through a
 * SIGN-EXTENDED WORD, so a text row past 32 KB into the screen would step backwards. */
#define SCROLL_LONGS_PER_PASS 4         /* `move.l (a2)+,(a3)+` four times... */
#define SCROLL_LONG_BYTES     4
#define SCROLL_BYTES_PER_PASS (SCROLL_LONGS_PER_PASS * SCROLL_LONG_BYTES)
#define SCROLL_PASS_SHIFT     4         /* ...hence the `lsr.w #4` on the line pitch */

/* THE FOUR COPIES ARE SPELT OUT rather than left as an inner `for`, and the pass counter is a WORD
 * counted down AFTER the body — which is the ROM's `subq.w #1,d7` / `dbf d7` and not a decoration.
 * Written as a counted inner loop, GCC keeps the count, the compare and a branch per LONGWORD and
 * the copy runs 2x the ROM; written this way it emits exactly `move.l (a1)+,(a0)+` four times under
 * a `dbra`. Each direction is one macro because it is one 68000 instruction repeated, and a
 * function would put the two cursors behind pointers the barrier could no longer pin. */
#define SCROLL_COPY_LONG_UP()   do { wr32(target, be32(source));                                   \
                                     source += SCROLL_LONG_BYTES;                                  \
                                     target += SCROLL_LONG_BYTES;                                  \
                                     CURSOR_BARRIER(source); CURSOR_BARRIER(target); } while (0)

/* ...and backwards, where the ROM's `move.l -(a2),-(a3)` predecrements. GCC never emits `-(An)`, so
 * the four copies become four displaced moves and one `lea` a cursor — which needs the barriers
 * ONCE A PASS rather than once a copy, or each displacement becomes a `lea` of its own. */
#define SCROLL_COPY_LONG_DOWN() do { source -= SCROLL_LONG_BYTES;                                  \
                                     target -= SCROLL_LONG_BYTES;                                  \
                                     wr32(target, be32(source)); } while (0)

static unsigned scroll_passes(const uint8_t *image, uint16_t rows_to_move)
{
    uint32_t scan_lines = (uint32_t)rows_to_move * be16(image + CON_CELL_HEIGHT);
    /* `mulu.w d0,d7` reads d7's LOW WORD, so the product above is narrowed here and not before. */
    uint32_t longs = (uint32_t)(uint16_t)scan_lines * (be16(image + CON_LINE_BYTES)
                                                       >> SCROLL_PASS_SHIFT);

    /* `subq.w #1,d7` on that product and then a `dbf` on its low word: the body runs first, so the
     * register stands for the passes and a low word of zero is a full 65,536 of them. */
    return loop_passes((uint16_t)longs, COUNT_MASK_WORD);
}

static uint32_t text_row_at(const uint8_t *image, uint16_t row)
{
    return addr_add(be32(image + SYSVAR_V_BAS_AD),
                    sign_ext16((uint16_t)(row * be16(image + CON_ROW_BYTES))));
}

void console_scroll_up(uint8_t *image, uint16_t row)
{
    uint16_t max_row = be16(image + CON_MAX_ROW);
    uint16_t rows_to_move = (uint16_t)(max_row - row);

    require_cpu_routine(image, CON_VECTOR_SCROLL_UP, CONOUT_SCROLL_UP_CPU,
                        "BIOS Bconout(CON:): the console's SCROLL UP vector is not the CPU routine "
                        "at $fd149a — the blitter variant ($fc4852) is not reconstructed");
    if (rows_to_move != 0) {
        uint32_t at = text_row_at(image, row);
        uint16_t row_bytes = be16(image + CON_ROW_BYTES);
        unsigned passes = scroll_passes(image, rows_to_move);
        /* The block the two cursors cover between them: the target walks up from `at` and the
         * source one text row ahead of it, so the last byte read is a row past the last written. */
        uint8_t *target = screen_block(image, at,
                                       passes * SCROLL_BYTES_PER_PASS + sign_ext16(row_bytes));
        uint8_t *source = target + sign_ext16(row_bytes);
        uint16_t left = (uint16_t)(passes - 1);         /* `subq.w #1,d7`, and then `dbf d7` */

        do {
            SCROLL_COPY_LONG_UP();
            SCROLL_COPY_LONG_UP();
            SCROLL_COPY_LONG_UP();
            SCROLL_COPY_LONG_UP();
        } while (left-- != 0);
    }
    console_clear_cells(image, 0, max_row, be16(image + CON_MAX_COLUMN), max_row);
}

void console_scroll_down(uint8_t *image, uint16_t row)
{
    uint16_t max_row = be16(image + CON_MAX_ROW);
    uint16_t rows_to_move = (uint16_t)(max_row - row);

    require_cpu_routine(image, CON_VECTOR_SCROLL_DOWN, CONOUT_SCROLL_DOWN_CPU,
                        "BIOS Bconout(CON:): the console's SCROLL DOWN vector is not the CPU "
                        "routine at $fd14de — the blitter variant ($fc48b6) is not reconstructed");
    if (rows_to_move != 0) {
        /* Both cursors start at the END of the block and walk BACKWARDS (`move.l -(a2),-(a3)`):
         * the source at the last row's first byte, the target one row below it. */
        uint32_t at = text_row_at(image, max_row);
        uint16_t row_bytes = be16(image + CON_ROW_BYTES);
        unsigned passes = scroll_passes(image, rows_to_move);
        uint32_t walked = passes * SCROLL_BYTES_PER_PASS;
        /* ...and the mirror block: the source walks DOWN from `at` and the target one row above
         * it, so the span runs from `at - walked` to a row past `at`. */
        uint8_t *source = screen_block(image, addr_add(at, -walked),
                                       walked + sign_ext16(row_bytes)) + walked;
        uint8_t *target = source + sign_ext16(row_bytes);
        uint16_t left = (uint16_t)(passes - 1);         /* `subq.w #1,d7`, and then `dbf d7` */

        do {
            SCROLL_COPY_LONG_DOWN();
            SCROLL_COPY_LONG_DOWN();
            SCROLL_COPY_LONG_DOWN();
            SCROLL_COPY_LONG_DOWN();
            CURSOR_BARRIER(source);
            CURSOR_BARRIER(target);
        } while (left-- != 0);
    }
    console_clear_cells(image, 0, row, be16(image + CON_MAX_COLUMN), row);
}
