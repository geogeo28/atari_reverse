/* draw.c — Joust's drawing layer: the screen clear, the text engine, the flat-pattern and floor
 * painters, and the three sprite engines (rider, pterodactyl, ground animation) with their
 * erase/draw pairs.
 *
 * Everything here writes the low-resolution ST screen described in joust.h: 16-pixel cells of four
 * interleaved bitplane words, 0xa0 bytes per scanline. Three shapes recur, and naming them once
 * makes the rest readable:
 *
 *   MASK   — one word ANDed into all four planes of a cell. Because every plane gets the same
 *            value it punches a silhouette rather than pixels (blit_mask_wide, blit_sprite_mask).
 *   DATA   — four different words ORed one per plane, i.e. actual colour (blit_sprite, the rest).
 *   SHIFT  — a sprite is stored cell-aligned and drawn at an arbitrary pixel column, so each
 *            source word is shifted right and its overflow lands in the NEXT cell. The routines
 *            differ in how they get that overflow: some pair two source words in one longword and
 *            shift, some rotate a mask so the overflow reappears in the other half.
 */
#include "machine.h"
#include "joust.h"
#include "draw.h"
#include "object.h"   /* the pterodactyl record blit_mask_wide indexes */

/* =================================================================================================
 * fill_screen @ 0x102e2 — the whole-screen flat fill.
 * ============================================================================================= */

/* `move.l #$fa0,d3` + `dbf` = 4001 passes of an 8-byte cell = 32008 bytes, while the ST screen is
 * 32000. The last pass therefore writes 8 bytes PAST the framebuffer, every time. Harmless on the
 * real machine (Physbase is 256-byte aligned, so the next 8 bytes are the slack above the screen)
 * and reproduced here because the differential compares those bytes like any other. */
#define FILL_SCREEN_CELLS 0xfa1u

/* Stack ABI: the caller pushes one word, which fill_screen passes straight to make_fill_pattern —
 * so, that routine being degenerate (see fill.c), only bit 0 of it survives. */
void fill_screen(uint8_t *image, uint16_t colour) {
    uint32_t dst = be32(image + A_screen_base);
    uint32_t planes01, planes23;
    make_fill_pattern(colour, &planes01, &planes23);

    for (unsigned cell = 0; cell < FILL_SCREEN_CELLS; cell++) {
        wr32(image + dst, planes01);
        wr32(image + dst + 4, planes23);
        dst += CELL_BYTES;
    }
}

#define FILL_SCREEN_ARG_COLOUR 0u   /* 4(a7) .w */

void g_fill_screen(uint8_t *image, uint32_t args) {
    fill_screen(image, be16(image + args + FILL_SCREEN_ARG_COLOUR));
}

/* =================================================================================================
 * draw_string @ 0x10700 — the text engine.
 * ============================================================================================= */

/* The two fonts are one byte per row per character, from ' ' up, with no padding — so the glyph
 * stride and the row count are the same number. `bar` is the background block for one character
 * cell, left-aligned in a longword so it shifts alongside the glyph: it is `advance` bits wide in
 * both fonts, but the original carries it as its own immediate rather than deriving it, so the two
 * fields are kept independent here and must be changed together. */
typedef struct {
    uint32_t glyphs;
    unsigned rows;
    uint32_t bar;
    unsigned advance;   /* pixels the cursor moves per character */
} text_font;

#define FONT_FIRST_CHAR 0x20u

static const text_font FONT_SMALL = {A_font_small, 5, 0xf0000000u, 4};   /* 4 px wide, 5 rows */
static const text_font FONT_LARGE = {A_font_large, 8, 0xfc000000u, 6};   /* 6 px wide, 8 rows */

/* The control bytes the string carries in-line. Everything else is a glyph — including 0x0b, 0x0c
 * and 0x0e..0x1f, which fall through to the font as characters below ' '. */
#define TEXT_END        0x00u
#define TEXT_SET_POS    0x01u   /* two words follow: x, y */
#define TEXT_COLOUR     0x02u   /* one byte follows */
#define TEXT_BACKGROUND 0x03u   /* one byte follows; 0 turns the background bar back off */
#define TEXT_BACKSPACE  0x08u
#define TEXT_FONT       0x09u   /* one byte follows: non-zero selects the 8-row font */

/* Reached but inert in the shipped routine: each of these has its own `beq` that branches straight
 * back to the top of the loop, consuming the byte and nothing more. Listed rather than folded into
 * `default` because they are decoded, not rendered. */
#define TEXT_NOP_4      0x04u
#define TEXT_NOP_5      0x05u
#define TEXT_NOP_6      0x06u
#define TEXT_NOP_7      0x07u
#define TEXT_NOP_LF     0x0au
#define TEXT_NOP_CR     0x0du

#define TEXT_CELL_BIT   0x10u   /* the cursor has advanced a whole cell once this bit of the shift sets */

/* `or.w dn,8(a2) / swap dn / or.w dn,(a2)` and its `not.l`/`and.w` twin: one shifted longword laid
 * across a cell boundary. The HIGH half belongs to the cell the cursor is on, the LOW half to the
 * next one — which is where the pixels that shifted off the right edge end up. `set` is the
 * colour bit for this plane: set ORs the ink in, clear masks it out. */
static void text_combine(uint8_t *image, uint32_t cell, uint32_t value, int set) {
    uint32_t next = cell + CELL_BYTES;
    uint16_t low = (uint16_t)value, high = (uint16_t)(value >> 16);

    if (set) {
        wr16(image + next, (uint16_t)(be16(image + next) | low));
        wr16(image + cell, (uint16_t)(be16(image + cell) | high));
    } else {
        wr16(image + next, (uint16_t)(be16(image + next) & (uint16_t)~low));
        wr16(image + cell, (uint16_t)(be16(image + cell) & (uint16_t)~high));
    }
}

/* One character at (cursor, shift). The cursor is restored before returning (the original walks it
 * down `rows` scanlines with adda.w and then subtracts the lot back), so advancing it is the
 * caller's job.
 *
 * text_flags, text_color and text_bg_color are re-read from the image inside the loops, exactly
 * where the original re-tests them — a glyph drawn over those globals changes its own colour
 * partway through, and only a reconstruction that re-reads them bends the same way. */
static void draw_char(uint8_t *image, uint32_t cursor, uint32_t shift, uint8_t ch,
                      const text_font *font) {
    uint32_t glyph = font->glyphs + (uint32_t)(uint8_t)(ch - FONT_FIRST_CHAR) * font->rows;
    uint32_t bar = lsr32(font->bar, shift);

    for (unsigned row = 0; row < font->rows; row++) {
        /* move.b (a1)+,d2 ; lsl.l #8 ; swap — the glyph byte ends up in the top 8 bits. */
        uint32_t pixels = lsr32((uint32_t)image[glyph + row] << 24, shift);
        uint32_t cell = cursor;

        for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++) {
            if (image[A_text_flags] & TEXT_FLAG_BACKGROUND)
                text_combine(image, cell, bar, image[A_text_bg_color] & (1u << plane));
            text_combine(image, cell, pixels, image[A_text_color] & (1u << plane));
            cell += 2;
        }
        cursor += SCREEN_ROW_BYTES;
    }
}

/* draw_string(text): walk the string, acting on the control bytes and rendering everything else.
 * The cursor (text_ptr) and the sub-cell shift (text_shift) persist in the image across calls, so
 * the routine loads them on entry and stores them back at the terminator.
 *
 * Register map: a0 = the string, a2 = the cursor, d3 = the shift, d0 = the current byte. d3 is
 * held as a full longword here because TEXT_BACKSPACE moves it with a LONG subtract, which can
 * take it negative, while the character advance moves only its low byte. */
void draw_string(uint8_t *image, uint32_t string) {
    uint32_t cursor = be32(image + A_text_ptr);
    uint32_t shift = image[A_text_shift];

    for (;;) {
        uint8_t ch = image[string++];

        switch (ch) {
        case TEXT_END:
            wr32(image + A_text_ptr, cursor);
            image[A_text_shift] = (uint8_t)shift;
            return;

        case TEXT_SET_POS: {
            /* The two words go through text_x/text_y rather than straight into the call: the
             * original stores them, then pushes them back off those globals. */
            wr16(image + A_text_x, be16(image + string));
            wr16(image + A_text_y, be16(image + string + 2));
            string += 4;
            uint16_t new_shift;
            cursor = pos_to_screen(image, be16(image + A_text_x), be16(image + A_text_y),
                                   &new_shift);
            shift = (shift & 0xffff0000u) | new_shift;   /* move.w (a7)+,d3 — the low word only */
            break;
        }

        case TEXT_COLOUR:
            image[A_text_color] = image[string++];
            break;

        case TEXT_BACKGROUND: {
            /* bset first, then clear again when the new colour is 0 — so "background 0" means off,
             * not "background in colour 0". */
            image[A_text_flags] |= TEXT_FLAG_BACKGROUND;
            uint8_t colour = image[string++];
            image[A_text_bg_color] = colour;
            if (!colour) image[A_text_flags] &= (uint8_t)~TEXT_FLAG_BACKGROUND;
            break;
        }

        case TEXT_BACKSPACE:
            /* Always the LARGE font's 6 pixels, whichever font is selected — so backing up over
             * small text lands the cursor 6 px left, not 4. Borrowing a cell when that goes
             * negative is what makes 0 - 6 come out as the previous cell's column 10.
             *
             * The original branches on BGE (N == V), not on the sign of the result, so the two
             * would part company for a shift within 6 of INT32_MIN, where `subq.l` overflows.
             * Nothing can put d3 there: only this subtraction ever touches its high half, so
             * reaching it would take ~3.5e8 backspaces inside one string. */
            shift -= FONT_LARGE.advance;
            if ((int32_t)shift < 0) {
                shift += CELL_PIXELS;
                cursor -= CELL_BYTES;
            }
            break;

        case TEXT_FONT:
            if (image[string++]) image[A_text_flags] |= TEXT_FLAG_LARGE_FONT;
            else                 image[A_text_flags] &= (uint8_t)~TEXT_FLAG_LARGE_FONT;
            break;

        case TEXT_NOP_4: case TEXT_NOP_5: case TEXT_NOP_6:
        case TEXT_NOP_7: case TEXT_NOP_LF: case TEXT_NOP_CR:
            break;

        default: {
            const text_font *font = (image[A_text_flags] & TEXT_FLAG_LARGE_FONT) ? &FONT_LARGE
                                                                                 : &FONT_SMALL;
            draw_char(image, cursor, shift, ch, font);
            shift = (shift & ~0xffu) | ((shift + font->advance) & 0xffu);   /* addq.b */
            if (shift & TEXT_CELL_BIT) {
                cursor += CELL_BYTES;
                shift &= ~(uint32_t)TEXT_CELL_BIT;
            }
            break;
        }
        }
    }
}

#define DRAW_STRING_ARG_TEXT 0u   /* 4(a7) .l */

void g_draw_string(uint8_t *image, uint32_t args) {
    draw_string(image, be32(image + args + DRAW_STRING_ARG_TEXT));
}

/* =================================================================================================
 * select_sprite_base @ 0x135f4 — which rider sprite set an object draws from.
 * ============================================================================================= */

#define SPRITE_SET_PLAYER1   0x1c64au
#define SPRITE_SET_PLAYER2   0x1ebaau
#define SPRITE_SET_ENEMY     0x22f4au
#define SPRITE_SET_FACING    0x130u    /* the mirrored half of each set */

/* Register map: a0 = the object, d0 = its flags word; the answer comes back in d1, which callers
 * store into draw_src. Identity, not type: only the two player slots have their own sprites, and
 * every enemy shares the third set. */
uint32_t select_sprite_base(uint32_t object, uint32_t flags) {
    uint32_t base = object == A_object_table ? SPRITE_SET_PLAYER1
                  : object == A_player2      ? SPRITE_SET_PLAYER2
                                             : SPRITE_SET_ENEMY;
    return (flags & OBJ_FLAG_FACING_RIGHT) ? base + SPRITE_SET_FACING : base;
}

/* No image argument: the routine reads no memory, and its result is a register the diff cannot
 * see, so the test compares the oracle's D1 against this return value. */
uint32_t g_select_sprite_base(uint32_t object, uint32_t flags) {
    return select_sprite_base(object, flags);
}

/* =================================================================================================
 * blit_pattern_rows @ 0x1369c — three scanlines of a flat-coloured pattern.
 * ============================================================================================= */

#define PATTERN_ROWS 3u

/* Register map: a3 = the top-left cell, d2 = one bit per bitplane, d5/d6/d7 = the three row masks
 * (word ops throughout, so only their low words count).
 *
 * Per plane: OR the mask in where that plane's bit is set, AND it out where it is clear — i.e.
 * paint the pattern in one solid colour, replacing whatever it covers rather than blending. Planes
 * run 3 down to 0, which is only observable if the destination overlaps itself. */
void blit_pattern_rows(uint8_t *image, uint32_t dst, uint32_t plane_select,
                       uint32_t row0, uint32_t row1, uint32_t row2) {
    const uint16_t rows[PATTERN_ROWS] = {(uint16_t)row0, (uint16_t)row1, (uint16_t)row2};

    for (int plane = (int)CELL_PLANE_WORDS - 1; plane >= 0; plane--) {
        int set = (plane_select >> plane) & 1u;

        for (unsigned row = 0; row < PATTERN_ROWS; row++) {
            uint32_t at = dst + (uint32_t)plane * 2u + row * SCREEN_ROW_BYTES;
            uint16_t was = be16(image + at);
            wr16(image + at, set ? (uint16_t)(was | rows[row])
                                 : (uint16_t)(was & (uint16_t)~rows[row]));
        }
    }
}

void g_blit_pattern_rows(uint8_t *image, uint32_t dst, uint32_t plane_select,
                         uint32_t row0, uint32_t row1, uint32_t row2) {
    blit_pattern_rows(image, dst, plane_select, row0, row1, row2);
}

/* =================================================================================================
 * draw_object_data @ 0x136e8 and draw_object_mask @ 0x137bc — the rider blitter.
 * ============================================================================================= */

/* A rider sprite is 4 plane words wide (one cell) per row, but stored two cells to a row: the
 * leading cell at +0 and, 8 bytes on, the copy whose bits fill the wrap column. Both passes below
 * step the source by SPRITE_SRC_ROW_BYTES and the destination by a scanline. */
#define SPRITE_SRC_ROW_BYTES 0x10u

/* Past this x the destination cell one to the right has already spilled onto the next scanline, so
 * the wrap column is pulled back a row to land on the left edge of the same one. */
#define SPRITE_WRAP_X 0x130u

typedef enum { SPRITE_OP_OR, SPRITE_OP_ANDNOT } sprite_op;

/* One row: four plane words shifted right by `shift` and combined into four consecutive
 * destination words. `carry_in` picks where the bits that arrive from the left come from — nothing
 * on the leading pass, and the word 8 bytes back (the same plane of the previous cell) on the wrap
 * column, which is exactly the overflow the leading pass shifted away. */
static void sprite_row(uint8_t *image, uint32_t dst, uint32_t src, uint32_t shift,
                       int carry_in, sprite_op op) {
    for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++) {
        uint32_t pixels = carry_in ? (uint32_t)be16(image + src - CELL_BYTES) << 16 : 0u;
        pixels = lsr32(pixels | be16(image + src), shift);

        uint16_t was = be16(image + dst);
        wr16(image + dst, op == SPRITE_OP_OR ? (uint16_t)(was | (uint16_t)pixels)
                                             : (uint16_t)(was & (uint16_t)~(uint16_t)pixels));
        dst += 2;
        src += 2;
    }
}

static void sprite_pass(uint8_t *image, uint32_t dst, uint32_t src, uint32_t shift,
                        unsigned rows, int carry_in, sprite_op op) {
    for (unsigned row = 0; row < rows; row++) {
        sprite_row(image, dst, src, shift, carry_in, op);
        dst += SCREEN_ROW_BYTES;
        src += SPRITE_SRC_ROW_BYTES;
    }
}

/* Where the wrap column starts, given the sprite's x. */
static uint32_t wrap_column(uint32_t dst, uint16_t x) {
    uint32_t at = dst + CELL_BYTES;
    return (int16_t)x < (int16_t)SPRITE_WRAP_X ? at : at - SCREEN_ROW_BYTES;
}

#define HALF_SELECT_SKIP_LEADING 0x02u   /* btst #1 */
#define HALF_SELECT_SKIP_WRAP    0x01u   /* btst #0 */

/* The leading pass, with the lava check the mask pass has no use for: before every row, if the
 * destination has reached playfield_bottom the object is flagged as falling in and the pass stops.
 * draw_rows is then rewritten to the number of rows actually drawn, so the wrap column stops at
 * the same scanline — which also means a sprite that is already at the bottom on row 0 leaves
 * draw_rows at 0, and the wrap pass's `subq.b` loop reads that as 256 rows, not none.
 *
 * `remaining` is D1: a `subq.b` counter loaded once, so a sprite that draws over draw_rows does not
 * change how many rows this pass makes. playfield_bottom and draw_rows themselves ARE re-read where
 * the original re-reads them — the compare is `cmpa.l $d60.l,a3` inside the loop, and the row count
 * it leaves behind is `sub.b $df6.l,d1 / neg.b d1`, i.e. a fresh read minus the counter. Both bend
 * only when the sprite is drawn over those globals, and both bend the original's way here. */
static void draw_object_data_leading(uint8_t *image, uint32_t object, uint32_t dst, uint32_t src,
                                     uint32_t shift) {
    uint8_t remaining = image[A_draw_rows];

    do {
        if ((int32_t)dst >= (int32_t)be32(image + A_playfield_bottom)) {
            wr16(image + object + OBJ_FLAGS,
                 (uint16_t)(be16(image + object + OBJ_FLAGS) | OBJ_FLAG_IN_LAVA));
            image[A_draw_rows] = (uint8_t)(image[A_draw_rows] - remaining);
            return;
        }
        sprite_row(image, dst, src, shift, 0, SPRITE_OP_OR);
        dst += SCREEN_ROW_BYTES;
        src += SPRITE_SRC_ROW_BYTES;
    } while (--remaining);
}

/* draw_object_data(object): OR the object's current sprite (staged in the draw_* globals) onto the
 * screen. A zero flags word means the slot is empty and nothing is drawn. */
void draw_object_data(uint8_t *image, uint32_t object) {
    if (be16(image + object + OBJ_FLAGS) == 0) return;

    uint32_t shift = image[A_draw_shift];
    uint32_t dst = be32(image + A_draw_dst);
    uint32_t src = be32(image + A_draw_src);

    if (!(image[A_draw_half_select] & HALF_SELECT_SKIP_LEADING))
        draw_object_data_leading(image, object, dst, src, shift);

    if (image[A_draw_half_select] & HALF_SELECT_SKIP_WRAP) return;

    /* draw_rows and draw_src are re-read for this pass — the leading one may have just shortened
     * the row count, and both globals lie in memory a sprite could have drawn over. draw_dst is
     * NOT re-read: the original keeps it in A1 across both passes. */
    sprite_pass(image, wrap_column(dst, be16(image + object + OBJ_X)),
                be32(image + A_draw_src) + CELL_BYTES, shift,
                loop_passes(image[A_draw_rows], COUNT_MASK_BYTE), 1, SPRITE_OP_OR);
}

void g_draw_object_data(uint8_t *image, uint32_t object) {
    draw_object_data(image, object);
}

/* draw_object_mask(object): AND-NOT the object's PREVIOUS sprite back out of the screen. It reads
 * that position from the object itself (the +0x14.. block the drawing pass left behind) rather
 * than from the draw_* globals, which by now describe the new position — so erase and redraw can
 * be issued back to back. Neither pass is optional and neither checks the lava. */
void draw_object_mask(uint8_t *image, uint32_t object) {
    uint32_t shift = image[object + OBJ_PREV_SHIFT];
    uint32_t dst = be32(image + object + OBJ_PREV_DST);

    sprite_pass(image, dst, be32(image + object + OBJ_PREV_SRC), shift,
                loop_passes(image[object + OBJ_PREV_ROWS], COUNT_MASK_BYTE), 0, SPRITE_OP_ANDNOT);
    /* Row count and source are re-read for the wrap column (the shift and the destination are
     * not); the first pass could have masked the object's own record. */
    sprite_pass(image, wrap_column(dst, be16(image + object + OBJ_PREV_X)),
                be32(image + object + OBJ_PREV_SRC) + CELL_BYTES, shift,
                loop_passes(image[object + OBJ_PREV_ROWS], COUNT_MASK_BYTE), 1, SPRITE_OP_ANDNOT);
}

void g_draw_object_mask(uint8_t *image, uint32_t object) {
    draw_object_mask(image, object);
}

/* =================================================================================================
 * blit_mask_wide @ 0x15098 and blit_sprite_planes @ 0x1510c — the pterodactyl's erase and draw.
 * ============================================================================================= */

/* `and.w dn,k(a1)` four times over: one mask word into all four planes of a cell. */
static void mask_cell(uint8_t *image, uint32_t cell, uint16_t mask) {
    for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++) {
        uint32_t at = cell + plane * 2u;
        wr16(image + at, (uint16_t)(be16(image + at) & mask));
    }
}

/* The pterodactyl is two cells of mask per row, laid across three cells of screen once shifted.
 * The mask arrives as two longwords and is ROTATED, not shifted: what leaves the low half comes
 * back round in the high half, which is how the same longword serves both the cell it starts in
 * and the one it spills into. Cell 1 is therefore masked twice per row — once by each longword —
 * and the order below is the original's.
 *
 * The row count is a `subq.w`/`bge` counter read as a signed word, so 0 or any negative value
 * draws nothing at all — 0x8000 included, where the decrement overflows to +0x7fff but BGE (which
 * tests N == V, not the sign of the result) still fails. Every field is read once, before the
 * loop, so a destination laid over the record does not change the pass. */
void blit_mask_wide(uint8_t *image, uint32_t record) {
    uint32_t src = be32(image + record + PT_SRC) + PTERO_MASK_OFF;
    uint32_t dst = be32(image + record + PT_DST) + be32(image + A_screen_base)
                 + sign_ext16(be16(image + record + PT_DST_OFF));
    uint32_t shift = be16(image + record + PT_SHIFT_W);
    int16_t rows = (int16_t)be16(image + record + PT_ROWS_W);

    for (int16_t row = 0; row < rows; row++) {
        uint32_t left = ror32(be32(image + src), shift);
        uint32_t right = ror32(be32(image + src + 4), shift);
        src += PTERO_MASK_ROW_BYTES;

        mask_cell(image, dst + CELL_BYTES, (uint16_t)left);
        mask_cell(image, dst + 2 * CELL_BYTES, (uint16_t)right);
        mask_cell(image, dst, (uint16_t)(left >> 16));
        mask_cell(image, dst + CELL_BYTES, (uint16_t)(right >> 16));

        dst += SCREEN_ROW_BYTES;
    }
}

void g_blit_mask_wide(uint8_t *image, uint32_t record) {
    blit_mask_wide(image, record);
}

/* One plane word ORed into a cell. */
static void or_plane(uint8_t *image, uint32_t cell, unsigned plane, uint16_t pixels) {
    uint32_t at = cell + plane * 2u;
    wr16(image + at, (uint16_t)(be16(image + at) | pixels));
}

#define PTERO_SRC_ROW_BYTES 0x18u   /* adda.w #$18,a1 — 12 words, of which 8 are read */

/* The trailing word of plane `plane`, shifted on its own: what spills past the middle cell. */
static uint32_t trailing_spill(const uint8_t *image, uint32_t src, unsigned plane, uint32_t shift) {
    return lsr32((uint32_t)be16(image + src + CELL_BYTES + plane * 2u) << 16, shift);
}

/* blit_sprite_planes(): OR the pterodactyl's colour data over the three cells the mask just
 * cleared. Each row holds two cells of plane words — words 0..3 for the leading cell, 4..7 for the
 * trailing one — and the routine pairs word p with word p+4 in one longword so a single shift
 * produces both the leading cell's pixels (high half) and the middle cell's (low half). A third
 * pass shifts word p+4 on its own to recover what spilled past the middle cell.
 *
 * Each of the three cells has its own suppressor byte; a non-zero one drops that cell for the
 * whole row, which is how the sprite is clipped at the screen edges.
 *
 * The three passes are kept whole, in the original's order (middle, leading, trailing), rather than
 * folded into one loop over the planes: the original reads all four pairs before it writes
 * anything, tests each suppressor once per row, and RE-READS the trailing words from memory for
 * the third pass — so a sprite drawn over its own source, or over the suppressor bytes, bends
 * differently from an interleaved reconstruction. */
void blit_sprite_planes(uint8_t *image) {
    uint32_t src = be32(image + A_draw_src);
    uint32_t dst = be32(image + A_draw_dst) + be32(image + A_screen_base)
                 + sign_ext16(be16(image + A_draw_dst_off));
    uint32_t shift = be16(image + A_draw_shift);
    int16_t rows = (int16_t)be16(image + A_draw_rows);

    for (int16_t row = 0; row < rows; row++) {
        uint32_t pair[CELL_PLANE_WORDS];
        for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++)
            pair[plane] = lsr32(((uint32_t)be16(image + src + plane * 2u) << 16)
                                | be16(image + src + CELL_BYTES + plane * 2u), shift);

        if (!image[A_draw_clip_cell1])
            for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++)
                or_plane(image, dst + CELL_BYTES, plane, (uint16_t)pair[plane]);

        if (!image[A_draw_clip_cell0])
            for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++)
                or_plane(image, dst, plane, (uint16_t)(pair[plane] >> 16));

        if (!image[A_draw_clip_cell2]) {
            /* All four re-reads happen before any of the four writes (`move.l 8(a1),d1` ..
             * `move.l 14(a1),d4` at 0x5119a, then the ORs at 0x511ba) — which is observable
             * whenever the source sits 2, 4 or 6 bytes below the trailing cell. */
            uint32_t spill[CELL_PLANE_WORDS];
            for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++)
                spill[plane] = trailing_spill(image, src, plane, shift);
            for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++)
                or_plane(image, dst + 2 * CELL_BYTES, plane, (uint16_t)spill[plane]);
        }

        src += PTERO_SRC_ROW_BYTES;
        dst += SCREEN_ROW_BYTES;
    }
}

void g_blit_sprite_planes(uint8_t *image) {
    blit_sprite_planes(image);
}

/* =================================================================================================
 * paint_floor_row @ 0x175ba — recolour the newly exposed lava row.
 * ============================================================================================= */

#define FLOOR_ROW_CELLS 5u   /* 80 pixels: half the screen width, painted in two calls */
#define PLANE3_OFFSET   6u

/* Register map: a1 = the row's leftmost cell. For each cell, sets plane 3 on every pixel whose
 * four planes are all zero — colour 0 becomes colour 8, and anything already drawn is left alone.
 * A repair pass, not a fill. */
void paint_floor_row(uint8_t *image, uint32_t row) {
    for (unsigned cell = 0; cell < FLOOR_ROW_CELLS; cell++) {
        uint16_t painted = 0;
        for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++)
            painted |= be16(image + row + plane * 2u);

        uint32_t plane3 = row + PLANE3_OFFSET;
        wr16(image + plane3, (uint16_t)(be16(image + plane3) | (uint16_t)~painted));
        row += CELL_BYTES;
    }
}

void g_paint_floor_row(uint8_t *image, uint32_t row) {
    paint_floor_row(image, row);
}

/* =================================================================================================
 * blit_sprite_mask @ 0x17752 and blit_sprite @ 0x177a2 — the ground-animation blitter.
 * ============================================================================================= */

/* Both read the same record and both take the row count in D7 as a signed word (0 or less draws
 * nothing). The AND mask is one rotated longword per row covering two cells; the low byte of the
 * record's cell-select word decides which of the two is touched, so a sprite straddling the screen
 * edge can be drawn in halves. */
#define SPR_MASK_ROW_BYTES 4u
#define SPR_DATA_ROW_BYTES 8u

/* Which cells this row touches. The original tests the same byte twice, `blt` then `bgt`, so zero
 * means both — and no value means neither. */
static int draws_trailing_cell(int8_t cell_select) { return cell_select >= 0; }
static int draws_leading_cell(int8_t cell_select) { return cell_select <= 0; }

/* The shipped binary carries the erase and the draw as two routines that differ only in whether the
 * colour data is ORed in behind the mask, so — as in blit.c — one core serves both. */
typedef enum { GROUND_MASK_ONLY, GROUND_MASK_AND_DATA } ground_op;

/* Register map: a5 = the record, d7 = rows, a3 = the mask cursor, a1 = the data cursor, a2 = the
 * running destination, d4 = shift, d5 = cell select. Rotating the mask (rather than shifting it)
 * puts the bits that leave the trailing cell's word back into the leading cell's, while the colour
 * data is SHIFTED, one word per plane, so a plane's overflow lands in the trailing cell instead.
 *
 * Every read of a row happens before any write of it, as in the original (`move.l (a3)+,d6` and the
 * four `move.l k(a1)` at 0x77c2..0x77d8, then the AND/OR passes). */
static void ground_blit(uint8_t *image, uint32_t record, uint16_t rows, ground_op op) {
    uint32_t data = be32(image + record + SPR_SRC);
    uint32_t mask = data + SPR_MASK_OFF;
    uint32_t dst = be32(image + record + SPR_DST_OFF) + be32(image + A_screen_base);
    uint32_t shift = be16(image + record + SPR_SHIFT);
    int8_t cell_select = (int8_t)image[record + SPR_CELL_SELECT + 1];
    int with_data = op == GROUND_MASK_AND_DATA;

    for (int16_t row = 0; row < (int16_t)rows; row++) {
        uint32_t bits = ror32(be32(image + mask), shift);
        uint32_t pixels[CELL_PLANE_WORDS] = {0};
        if (with_data)
            for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++)
                pixels[plane] = lsr32((uint32_t)be16(image + data + plane * 2u) << 16, shift);
        mask += SPR_MASK_ROW_BYTES;

        if (draws_trailing_cell(cell_select)) {
            mask_cell(image, dst + CELL_BYTES, (uint16_t)bits);
            if (with_data)
                for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++)
                    or_plane(image, dst + CELL_BYTES, plane, (uint16_t)pixels[plane]);
        }
        if (draws_leading_cell(cell_select)) {
            mask_cell(image, dst, (uint16_t)(bits >> 16));
            if (with_data)
                for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++)
                    or_plane(image, dst, plane, (uint16_t)(pixels[plane] >> 16));
        }
        dst += SCREEN_ROW_BYTES;
        data += SPR_DATA_ROW_BYTES;
    }
}

/* blit_sprite_mask(): punch the silhouette out, i.e. erase the sprite's previous frame. */
void blit_sprite_mask(uint8_t *image, uint32_t record, uint16_t rows) {
    ground_blit(image, record, rows, GROUND_MASK_ONLY);
}

/* blit_sprite(): the same mask pass, with the colour data ORed in behind it — the record's mask
 * (at SPR_MASK_OFF) punches the silhouette, then the four plane words at the record's data base
 * fill it. */
void blit_sprite(uint8_t *image, uint32_t record, uint16_t rows) {
    ground_blit(image, record, rows, GROUND_MASK_AND_DATA);
}

void g_blit_sprite_mask(uint8_t *image, uint32_t record, uint32_t rows) {
    blit_sprite_mask(image, record, (uint16_t)rows);
}

void g_blit_sprite(uint8_t *image, uint32_t record, uint32_t rows) {
    blit_sprite(image, record, (uint16_t)rows);
}
