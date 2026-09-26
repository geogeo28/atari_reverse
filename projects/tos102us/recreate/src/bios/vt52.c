/* The BIOS console — `Bconout(CON:)` at $fc42f2 and `Bconout(RAW:)` at $fc42e6.
 *
 * A VT52 terminal on a bitmap: a state machine over the escape sequences, seven control codes, and a
 * glyph renderer that walks the cursor along. Everything it keeps is in one block of RAM the ROM
 * reaches through `lea CON_STATE_FLAGS,a4` and addresses at DISPLACEMENTS off — the cell geometry,
 * the two colours, the cursor, the font and the four screen routines (`src/bios/conout_glyph.c`,
 * which is where every screen byte is written).
 *
 * IT READS NO HARDWARE AT ALL, which is why the whole driver is in reach where `Bconin(PRT:)` is
 * not: the screen base is `_v_bas_ad` ($44e) in RAM and the resolution is the cell geometry the
 * boot derived from it, so the shifter is never asked. A case declares nothing.
 *
 * THE STATE IS A ROM ADDRESS IN RAM ($4a8), and the dispatch is a `jmp` through it:
 *
 *      Bconout(CON:):  move.w  6(sp),d1        ; the character word, above the device word
 *                      lea     CON_STATE_FLAGS,a4
 *                      and.w   #$ff,d1
 *                      movea.l CON_STATE_VECTOR,a0
 *                      jmp     (a0)
 *
 * So which of six routines a character reaches is a fact about RAM — exactly as the four BIOS device
 * tables are — and this file reads it rather than keeping a state of its own. The six are: the
 * normal state, the one ESC leaves behind, ESC Y's two argument states, and the two colour escapes'.
 * `Bconout(RAW:)` skips all of it and goes straight to the glyph renderer, so a control code is
 * DRAWN there rather than obeyed.
 *
 * THE ESCAPES THE ROM REALLY IMPLEMENTS, read off its three jump tables ($fc4330, $fc43e8, $fc4402)
 * rather than off a manual:
 *
 *      ESC A B C D   cursor up / down / right / left      ESC b <c>  foreground colour, biased by $20
 *      ESC E         clear screen and home                ESC c <c>  background colour
 *      ESC H         home                                 ESC d      clear to the start of screen
 *      ESC I         reverse index (scroll down at row 0) ESC e / f  show / hide the cursor
 *      ESC J         clear to the end of screen           ESC j / k  save / restore the position
 *      ESC K         clear to the end of line             ESC l      erase the whole line
 *      ESC L / M     insert / delete a line               ESC o      erase to the start of line
 *      ESC Y <r> <c> position the cursor, both biased     ESC p / q  reverse video on / off
 *                                                         ESC v / w  wrap at the last column on / off
 *
 * and `ESC F`, `ESC G` and `ESC g h i m n r s t u` are entries in those tables that point at a bare
 * `rts`. Everything outside `A`..`M`, `Y` and `b`..`w` returns to the normal state and does nothing.
 *
 * THE CONTROL CODES are `$07`..`$0d` and ESC, and nothing else: `subq.w #7,d1 / bmi / cmp.w #6,d1 /
 * bgt` is the whole gate. BEL is TRAP-FREE — it plants the ROM's own bell list at $fc31c2 in
 * `SOUND_LIST_POINTER` and clears the delay, which is two stores into RAM that the 200 Hz timer C
 * handler then plays (`src/bios/timerc.c`); VT and FF do exactly what LF does.
 *
 * THE CURSOR IS LOCKED AROUND EVERY SCREEN CHANGE, by a DEPTH COUNTER rather than a flag
 * (`CON_CURSOR_DISABLE`), and reading that pair is most of reading this file:
 *
 *      $fc45de  lock:    disable += 1; if the cursor was drawn, invert its cell away
 *      $fc45ae  unlock:  disable -= 1, and when that reaches zero draw it again
 *      $fc45be  ESC e:   force it visible whatever the depth is
 *
 * THE UNLOCK LEAVES THE DEPTH IN D0, which is the same register the driver carries a COLUMN in — so
 * `ESC l`, which erases a line and then places the cursor with whatever D0 holds, puts the cursor in
 * column `depth - 1`. On the machine the depth at a `Bconout` is 0 and that is column 0; on the
 * captured desktop it is 2 and the cursor lands in column 1. It is the ROM's own arithmetic, it is
 * reachable from a `Bconout` a program makes, and `test_bios_vt52.py` drives both.
 */
#include <stdint.h>

#include "machine.h"
#include "recreate.h"
#include "addrs.h"
#include "m68k_idioms.h"
#include "sound.h"
#include "bios/vt52.h"

/* The driver's two live registers, carried together because one of them is the result. D0 holds the
 * COLUMN the position routines take and, at the `rts`, whatever `Bconout` hands its caller — and
 * most arms never write it at all, so the caller's own D0 comes back. `image` rides along because
 * every one of these routines reaches the state block through A4. */
typedef struct {
    uint8_t *image;
    uint32_t result;
} Console;

#define CON_CHARACTER_MASK      0xffu   /* `and.w #$ff,d1` at both entries */
#define GLYPH_OFFSET_ENTRY_BYTES 2      /* `add.w d1,d1`: one WORD per character code */
#define GLYPH_OFFSET_BIT_SHIFT   3      /* `lsr.w #3`: the table is in BITS, the form in bytes */
#define CON_SAVED_ROW            2      /* ESC j's longword is the column word, then the row word */

/* `move.w d0,CON_CURSOR_COLUMN(a4)`-shaped: the column lives in D0's low word throughout. */
static void set_column(Console *con, uint16_t column)
{
    con->result = set_low_word(con->result, column);
}

/* `bset #n,(a4)` / `bclr #n,(a4)` — the four escapes that do nothing but turn a flag on or off.
 * One helper, because one instruction each is exactly how the ROM has them. */
static void set_state_flag(Console *con, unsigned bit, int on)
{
    if (on)
        con->image[CON_STATE_FLAGS] |= (uint8_t)(1u << bit);
    else
        con->image[CON_STATE_FLAGS] &= (uint8_t)~(1u << bit);
}

/* $fc4370 — `move.l a0,CON_STATE_VECTOR`: where the NEXT character goes. */
static void set_state(Console *con, uint32_t state)
{
    wr32(con->image + CON_STATE_VECTOR, state);
}

static uint16_t cursor_depth(const uint8_t *image)
{
    return be16(image + CON_CURSOR_DISABLE);
}

/* ---- the cursor's lock, its tail, and the two routines ESC e / ESC f are ------------------------ */

static void cursor_unlock_tail(uint8_t *image, uint32_t cell);

/* $fc45d8/$fc45de (and the first three instructions of $fc49fc, which are the same four bytes): one
 * more level of lock, and the cell inverted back off the screen if it was drawn.
 *
 * EXPORTED because it is also `Cursconf(0)`: the XBIOS's jump table sends its hide arm straight
 * here, which is why `src/xbios/cursconf.c` had a halt where this call is now. Neither this nor
 * `console_show_cursor` writes D0, so both are `void` and Cursconf's own dispatch scratch is what
 * its caller gets back. */
void console_hide_cursor(uint8_t *image)
{
    uint8_t flags = image[CON_STATE_FLAGS];

    wr16(image + CON_CURSOR_DISABLE, (uint16_t)(cursor_depth(image) + 1));
    image[CON_STATE_FLAGS] = (uint8_t)(flags & ~(1u << CON_FLAG_DRAWN));
    if (flags & (1u << CON_FLAG_DRAWN))
        console_invert_cursor_cell(image, be32(image + CON_CURSOR_ADDRESS));
}

/* $fc45ca — draw it whatever the depth was: the count is FORCED to one so that the tail below sees
 * the last lock going away, and the tail then takes it to zero. */
static void show_cursor_now(uint8_t *image)
{
    wr16(image + CON_CURSOR_DISABLE, 1);
    cursor_unlock_tail(image, be32(image + CON_CURSOR_ADDRESS));
}

/* $fc45ae — one level off, and the cursor back on screen if that was the last one.
 *
 * IT WRITES D0, and that is the whole of the `ESC l` note in this file's header: the register the
 * position routines take a COLUMN in comes back holding `depth - 1`. */
static void unlock_cursor(Console *con)
{
    uint16_t depth = cursor_depth(con->image);

    set_column(con, depth == 0 ? 0 : (uint16_t)(depth - 1));
    if (depth == 0)
        return;                                 /* not locked: nothing to give back */
    if (depth - 1 != 0) {
        wr16(con->image + CON_CURSOR_DISABLE, (uint16_t)(depth - 1));
        return;
    }
    show_cursor_now(con->image);
}

/* $fc45be — ESC e, and `Cursconf(1)`. A cursor that is not locked at all is already on screen. */
void console_show_cursor(uint8_t *image)
{
    if (cursor_depth(image) == 0)
        return;
    show_cursor_now(image);
}

/* $fc479a — what every routine that moved or redrew the cursor ends in: put it back if this was the
 * last lock, reload the blink timer, and drop the depth by one.
 *
 * `CON_STATE_SPARE` is in the middle of it, which is not where a reader would look for it: a NONZERO
 * spare byte suppresses the redraw AND becomes the blink timer's new value. That is the byte
 * `Cursconf(6)` writes and `Cursconf(7)` reads back, so a program can stop the console redrawing its
 * cursor by writing it. */
static void cursor_unlock_tail(uint8_t *image, uint32_t cell)
{
    uint16_t depth = cursor_depth(image);
    uint8_t spare = image[CON_STATE_SPARE];

    if (spare != 0) {
        image[CON_BLINK_TIMER] = spare;
    } else if ((uint16_t)(depth - 1) == 0) {
        console_invert_cursor_cell(image, cell);
        image[CON_STATE_FLAGS] |= (uint8_t)(1u << CON_FLAG_DRAWN);
        image[CON_BLINK_TIMER] = image[CON_BLINK_RATE];
    }
    wr16(image + CON_CURSOR_DISABLE, (uint16_t)(depth - 1));
}

/* ---- where a character cell is, and putting the cursor on one ----------------------------------- */

/* $fc49c4 — the cell's first byte, with both coordinates CLAMPED to the screen on the way (the
 * clamp is what the caller stores, so it is written back through the two pointers).
 *
 *      move.w  d0,d2 / bclr #0,d2 / sne d4 / mulu.w PLANES,d2 / add.b d4,d4 / addx.l d3,d2
 *
 * An ST's 16-pixel group is `CON_PLANES` words side by side and a character cell is eight pixels, so
 * an EVEN column is the group's first byte and an odd one the byte after it — which is what the
 * `bclr` and the X flag it leaves add up to. Both clamps are `cmp.w` + `bpl` — the N FLAG OF THE
 * WORD DIFFERENCE and not a signed compare, which are different functions once the subtraction
 * overflows a word (`m68k_idioms.h`, `word_difference_is_negative`). */
static uint32_t cell_address(const uint8_t *image, uint16_t *column, uint16_t *row)
{
    uint16_t max_column = be16(image + CON_MAX_COLUMN);
    uint16_t max_row = be16(image + CON_MAX_ROW);
    uint32_t offset;

    if (word_difference_is_negative(max_column, *column))
        *column = max_column;
    if (word_difference_is_negative(max_row, *row))
        *row = max_row;
    offset = (uint32_t)*row * be16(image + CON_ROW_BYTES)
           + (uint32_t)(uint16_t)(*column & ~1u) * be16(image + CON_PLANES)
           + (*column & 1u);
    return addr_add(addr_add(be32(image + SYSVAR_V_BAS_AD),
                             sign_ext16(be16(image + CON_CURSOR_OFFSET))),
                    offset);
}

/* $fc49fc — the cursor to (column, row): lock, compute, store all three fields, unlock. */
static void place_cursor(Console *con, uint16_t column, uint16_t row)
{
    uint8_t *image = con->image;
    uint32_t cell;

    console_hide_cursor(con->image);
    cell = cell_address(image, &column, &row);
    /* D0 IS the argument — every caller left the column there — and `cell_address`'s clamp is what
     * survives in it, which is the only reason this routine writes D0 at all. */
    set_column(con, column);
    wr16(image + CON_CURSOR_COLUMN, column);
    wr16(image + CON_CURSOR_ROW, row);
    wr32(image + CON_CURSOR_ADDRESS, cell);
    cursor_unlock_tail(con->image, cell);
}

/* ---- the three screen changes, each bracketed by the cursor lock ------------------------------- */

/* $fc462e — the rectangle clear every ESC that erases anything goes through. */
static void clear_region(Console *con, uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2)
{
    console_hide_cursor(con->image);
    console_clear_cells(con->image, x1, y1, x2, y2);
    unlock_cursor(con);
}

/* $fc484c / $fc48b0 — the two scrolls. Each leaves D0's low word ZERO: `clr.w d0` is the last thing
 * either does before jumping through the clear vector, and the clear gives D0 back. */
static void scroll_up(Console *con, uint16_t row)
{
    console_scroll_up(con->image, row);
    set_column(con, 0);
}

static void scroll_down(Console *con, uint16_t row)
{
    console_scroll_down(con->image, row);
    set_column(con, 0);
}

/* ---- the glyph, and the cursor step that follows it --------------------------------------------- */

/* $fc473a — one cell along, and what happens at the end of a row.
 *
 * `cell` is where the glyph was just drawn. An even column steps ONE byte (the group's second half);
 * an odd one steps to the next group, which is `PLANES * 2 - 2` bytes further on top of that. At the
 * last column the whole thing depends on `CON_FLAG_WRAP`: without it nothing moves at all, and with
 * it the cursor goes to column 0 of the next row — scrolling the screen up first if there is no next
 * row, in which case the cursor stays on the LAST row rather than moving. */
static void advance_cursor(Console *con, uint32_t cell)
{
    uint8_t *image = con->image;
    uint16_t column = be16(image + CON_CURSOR_COLUMN);
    uint16_t row = be16(image + CON_CURSOR_ROW);

    set_column(con, column);
    if ((int16_t)column < (int16_t)be16(image + CON_MAX_COLUMN)) {
        cell = addr_add(cell, 1);
        column++;
        set_column(con, column);
        if ((column & 1u) == 0) {
            /* `lea -2(a1,d2.w),a1` with d2 = PLANES * 2 computed in a WORD. */
            cell = addr_add(addr_add(cell, sign_ext16((uint16_t)(be16(image + CON_PLANES) * 2))),
                            -2u);
        }
        wr16(image + CON_CURSOR_ROW, row);
    } else {
        if ((image[CON_STATE_FLAGS] & (1u << CON_FLAG_WRAP)) == 0) {
            cursor_unlock_tail(con->image, cell);      /* nothing moves, and nothing is stored */
            return;
        }
        int at_the_bottom = (int16_t)row >= (int16_t)be16(image + CON_MAX_ROW);

        column = 0;
        set_column(con, column);
        if (!at_the_bottom)
            row++;
        wr16(image + CON_CURSOR_ROW, row);
        cell = addr_add(be32(image + SYSVAR_V_BAS_AD),
                        (uint32_t)row * be16(image + CON_ROW_BYTES));
        if (at_the_bottom)
            scroll_up(con, 0);          /* ...and the cursor stays on the row it is already on */
    }
    wr16(image + CON_CURSOR_COLUMN, column);
    wr32(image + CON_CURSOR_ADDRESS, cell);
    cursor_unlock_tail(con->image, cell);
}

/* $fc46f0 — the glyph renderer, which is also the whole of `Bconout(RAW:)`.
 *
 * A character outside the font's own range does NOTHING — not even a cursor step — and leaves D0
 * alone. The lock this takes is not `console_hide_cursor`: it bumps the depth and clears the drawn
 * bit WITHOUT inverting the cell away, because the glyph is about to be written over the cell. */
static void put_glyph(Console *con, uint16_t character)
{
    uint8_t *image = con->image;
    uint16_t foreground, background, glyph_bit;
    uint32_t glyph, cell;

    if (character < be16(image + CON_FONT_FIRST) || character > be16(image + CON_FONT_LAST))
        return;
    glyph_bit = be16(image + addr_add(be32(image + CON_FONT_OFFSETS),
                                      word_index(character, GLYPH_OFFSET_ENTRY_BYTES)));
    glyph = addr_add(be32(image + CON_FONT_FORM),
                     sign_ext16((uint16_t)(glyph_bit >> GLYPH_OFFSET_BIT_SHIFT)));
    cell = be32(image + CON_CURSOR_ADDRESS);
    foreground = be16(image + CON_COLOUR_FOREGROUND);
    background = be16(image + CON_COLOUR_BACKGROUND);
    if (image[CON_STATE_FLAGS] & (1u << CON_FLAG_REVERSE)) {
        uint16_t swapped = foreground;

        foreground = background;                /* `exg d6,d7` */
        background = swapped;
    }
    wr16(image + CON_CURSOR_DISABLE, (uint16_t)(cursor_depth(image) + 1));
    image[CON_STATE_FLAGS] &= (uint8_t)~(1u << CON_FLAG_DRAWN);
    console_draw_glyph(image, glyph, cell, foreground, background);
    advance_cursor(con, cell);
}

/* ---- the control codes -------------------------------------------------------------------------- */

/* $fc2270 — BEL, which is two stores and no trap: the ROM's own bell list becomes the 200 Hz sound
 * driver's next command, with no delay before it. `conterm` bit 2 is what a program turns it off
 * with. */
static void bell(uint8_t *image)
{
    if ((image[SYSVAR_CONTERM] & (1u << CONTERM_BELL_BIT)) == 0)
        return;
    sound_start_list(image, BELL_SOUND_LIST);
}

/* $fc4342 — TAB: the next multiple of eight, WITHOUT a bound, so a tab past the last column is
 * clamped by `cell_address` rather than wrapped. */
static void tab(Console *con)
{
    uint8_t *image = con->image;
    uint16_t column = (uint16_t)((be16(image + CON_CURSOR_COLUMN) & CON_TAB_STOP_MASK)
                                 + CON_TAB_WIDTH);

    place_cursor(con, column, be16(image + CON_CURSOR_ROW));
}

/* $fc464e — LF, VT and FF: one row down, or the screen up if there is no row below. */
static void line_feed(Console *con)
{
    uint8_t *image = con->image;
    uint16_t row = be16(image + CON_CURSOR_ROW);

    if (row != be16(image + CON_MAX_ROW)) {
        place_cursor(con, be16(image + CON_CURSOR_COLUMN), (uint16_t)(row + 1));
        return;
    }
    console_hide_cursor(con->image);
    scroll_up(con, 0);
    unlock_cursor(con);
}

/* ---- the cursor-movement escapes ----------------------------------------------------------------
 *
 * All four stop at the edge rather than wrapping, and each is a plain `beq` back to an `rts` — so a
 * cursor already at the edge leaves the screen alone.
 *
 * WHAT IT LEAVES IN D0 SPLITS THEM IN TWO, and the split is which register the arm loads FIRST. The
 * VERTICAL pair test the row in D1 and never reach D0 at all, so a cursor at the top or bottom hands
 * the caller the dispatch's own scratch back; the HORIZONTAL pair open with `move.w
 * CON_CURSOR_COLUMN,d0` and so answer with the column they refused to move. Four instructions
 * apart, and nothing but a case can say which way round it is. */
static void cursor_up(Console *con)
{
    uint8_t *image = con->image;
    uint16_t row = be16(image + CON_CURSOR_ROW);

    if (row != 0)
        place_cursor(con, be16(image + CON_CURSOR_COLUMN), (uint16_t)(row - 1));
}

static void cursor_down(Console *con)
{
    uint8_t *image = con->image;
    uint16_t row = be16(image + CON_CURSOR_ROW);

    if (row != be16(image + CON_MAX_ROW))
        place_cursor(con, be16(image + CON_CURSOR_COLUMN), (uint16_t)(row + 1));
}

static void cursor_right(Console *con)
{
    uint8_t *image = con->image;
    uint16_t column = be16(image + CON_CURSOR_COLUMN);

    set_column(con, column);            /* `move.w CON_CURSOR_COLUMN,d0` is this arm's first word */
    if (column != be16(image + CON_MAX_COLUMN))
        place_cursor(con, (uint16_t)(column + 1), be16(image + CON_CURSOR_ROW));
}

/* ...and $fc44a0, which is `ESC D` and BACKSPACE both. */
static void cursor_left(Console *con)
{
    uint8_t *image = con->image;
    uint16_t column = be16(image + CON_CURSOR_COLUMN);

    set_column(con, column);
    if (column != 0)
        place_cursor(con, (uint16_t)(column - 1), be16(image + CON_CURSOR_ROW));
}

static void cursor_home(Console *con)
{
    place_cursor(con, 0, 0);
}

/* ---- the erasing escapes ------------------------------------------------------------------------ */

static void clear_to_end_of_line(Console *con)              /* $fc44ca — ESC K */
{
    uint8_t *image = con->image;
    uint16_t row = be16(image + CON_CURSOR_ROW);

    clear_region(con, be16(image + CON_CURSOR_COLUMN), row, be16(image + CON_MAX_COLUMN), row);
}

static void clear_to_end_of_screen(Console *con)            /* $fc44b8 — ESC J */
{
    uint8_t *image = con->image;
    uint16_t row = be16(image + CON_CURSOR_ROW);
    uint16_t max_row = be16(image + CON_MAX_ROW);

    clear_to_end_of_line(con);
    if (row == max_row)
        return;
    clear_region(con, 0, (uint16_t)(row + 1), be16(image + CON_MAX_COLUMN), max_row);
}

static void clear_to_start_of_line(Console *con)            /* $fc4622 — ESC o */
{
    uint8_t *image = con->image;
    uint16_t row = be16(image + CON_CURSOR_ROW);

    clear_region(con, 0, row, be16(image + CON_CURSOR_COLUMN), row);
}

static void clear_to_start_of_screen(Console *con)          /* $fc4594 — ESC d */
{
    uint8_t *image = con->image;
    uint16_t row = be16(image + CON_CURSOR_ROW);

    if (row != 0)
        clear_region(con, 0, 0, be16(image + CON_MAX_COLUMN), (uint16_t)(row - 1));
    clear_to_start_of_line(con);
}

/* $fc4610 — ESC l, and the one place the unlock's D0 becomes a column (this file's header). */
static void erase_line(Console *con)
{
    uint8_t *image = con->image;
    uint16_t row = be16(image + CON_CURSOR_ROW);

    clear_region(con, 0, row, be16(image + CON_MAX_COLUMN), row);
    place_cursor(con, (uint16_t)con->result, row);
}

static void clear_screen_and_home(Console *con)             /* $fc4464 — ESC E */
{
    cursor_home(con);
    clear_to_end_of_screen(con);
}

/* ---- the scrolling escapes ---------------------------------------------------------------------- */

static void reverse_index(Console *con)                     /* $fc4560 — ESC I */
{
    uint8_t *image = con->image;
    uint16_t row = be16(image + CON_CURSOR_ROW);

    if (row != 0) {
        place_cursor(con, be16(image + CON_CURSOR_COLUMN), (uint16_t)(row - 1));
        return;
    }
    console_hide_cursor(con->image);
    scroll_down(con, 0);
    unlock_cursor(con);
}

static void insert_line(Console *con)                       /* $fc4572 — ESC L */
{
    uint8_t *image = con->image;

    console_hide_cursor(con->image);
    scroll_down(con, be16(image + CON_CURSOR_ROW));
    place_cursor(con, 0, be16(image + CON_CURSOR_ROW));
    unlock_cursor(con);
}

static void delete_line(Console *con)                       /* $fc4588 — ESC M */
{
    uint8_t *image = con->image;

    console_hide_cursor(con->image);
    scroll_up(con, be16(image + CON_CURSOR_ROW));
    place_cursor(con, 0, be16(image + CON_CURSOR_ROW));
    unlock_cursor(con);
}

/* ---- the position ESC j saves and ESC k puts back ------------------------------------------------ */

static void save_position(Console *con)                     /* $fc45f0 — ESC j */
{
    uint8_t *image = con->image;

    image[CON_STATE_FLAGS] |= (uint8_t)(1u << CON_FLAG_POSITION_SAVED);
    /* `move.l CON_CURSOR_COLUMN(a4),CON_SAVED_POSITION(a4)` — the column and the row as one
     * longword, which is what makes the two fields' adjacency load-bearing. */
    wr32(image + CON_SAVED_POSITION, be32(image + CON_CURSOR_COLUMN));
}

static void restore_position(Console *con)                  /* $fc45fc — ESC k */
{
    uint8_t *image = con->image;
    uint8_t flags = image[CON_STATE_FLAGS];

    image[CON_STATE_FLAGS] = (uint8_t)(flags & ~(1u << CON_FLAG_POSITION_SAVED));
    if ((flags & (1u << CON_FLAG_POSITION_SAVED)) == 0) {
        cursor_home(con);                       /* nothing was saved */
        return;
    }
    place_cursor(con, be16(image + CON_SAVED_POSITION),
                 be16(image + CON_SAVED_POSITION + CON_SAVED_ROW));
}

/* ---- the state machine --------------------------------------------------------------------------- */

/* $fc43d4 — ESC A..M. Five of the thirteen are cursor moves, four erase, two scroll, and `F` and `G`
 * are table entries pointing at a bare `rts`. */
static void escape_upper(Console *con, uint16_t character)
{
    switch (character) {
    case 'A': cursor_up(con); return;
    case 'B': cursor_down(con); return;
    case 'C': cursor_right(con); return;
    case 'D': cursor_left(con); return;
    case 'E': clear_screen_and_home(con); return;
    case 'H': cursor_home(con); return;
    case 'I': reverse_index(con); return;
    case 'J': clear_to_end_of_screen(con); return;
    case 'K': clear_to_end_of_line(con); return;
    case 'L': insert_line(con); return;
    case 'M': delete_line(con); return;
    default: return;                            /* F and G: table entries pointing at a bare `rts` */
    }
}

/* $fc43de — ESC b..w, of which nine are the same bare `rts`. */
static void escape_lower(Console *con, uint16_t character)
{
    switch (character) {
    case 'b': set_state(con, CON_STATE_AWAIT_FOREGROUND); return;
    case 'c': set_state(con, CON_STATE_AWAIT_BACKGROUND); return;
    case 'd': clear_to_start_of_screen(con); return;
    case 'e': console_show_cursor(con->image); return;
    case 'f': console_hide_cursor(con->image); return;
    case 'j': save_position(con); return;
    case 'k': restore_position(con); return;
    case 'l': erase_line(con); return;
    case 'o': clear_to_start_of_line(con); return;
    case 'p': set_state_flag(con, CON_FLAG_REVERSE, 1); return;
    case 'q': set_state_flag(con, CON_FLAG_REVERSE, 0); return;
    case 'v': set_state_flag(con, CON_FLAG_WRAP, 1); return;
    case 'w': set_state_flag(con, CON_FLAG_WRAP, 0); return;
    default: return;          /* g h i m n r s t u: table entries pointing at the same bare `rts` */
    }
}

/* $fc4354 — the character after ESC. The state goes back to normal FIRST, whatever happens next, so
 * an escape this ROM does not implement costs exactly one character. */
static void escape_state(Console *con, uint16_t character)
{
    set_state(con, CON_STATE_NORMAL);
    if (character < CON_ESCAPE_UPPER_FIRST)
        return;
    if (character <= CON_ESCAPE_UPPER_LAST) {
        escape_upper(con, character);
        return;
    }
    if (character == CON_ESCAPE_POSITION) {
        set_state(con, CON_STATE_AWAIT_Y_ROW);
        return;
    }
    if (character < CON_ESCAPE_LOWER_FIRST || character > CON_ESCAPE_LOWER_LAST)
        return;
    escape_lower(con, character);
}

/* $fc4308 — the normal state. Everything from `CON_FIRST_PRINTABLE` up is a glyph. */
static void normal_state(Console *con, uint16_t character)
{
    if (character >= CON_FIRST_PRINTABLE) {
        put_glyph(con, character);
        return;
    }
    if (character == CON_ESC) {
        set_state(con, CON_STATE_ESCAPE);
        return;
    }
    switch (character) {
    case CON_BEL: bell(con->image); return;
    case CON_BS:  cursor_left(con); return;
    case CON_TAB: tab(con); return;
    case CON_LF:
    case CON_VT:
    case CON_FF:  line_feed(con); return;
    case CON_CR:  place_cursor(con, 0, be16(con->image + CON_CURSOR_ROW)); return;
    default: return;                        /* below $07 and above $0d, and nothing happens */
    }
}

uint32_t console_output(uint8_t *image, uint32_t entry_d0, uint16_t character)
{
    Console con = { image, entry_d0 };
    uint16_t ch = (uint16_t)(character & CON_CHARACTER_MASK);

    switch (be32(image + CON_STATE_VECTOR)) {
    case CON_STATE_NORMAL:
        normal_state(&con, ch);
        break;
    case CON_STATE_ESCAPE:
        escape_state(&con, ch);
        break;
    case CON_STATE_AWAIT_Y_ROW:                /* $fc4378 — ESC Y's first argument */
        wr16(image + CON_ESCAPE_Y_ROW, (uint16_t)(ch - CON_ESCAPE_BIAS));
        set_state(&con, CON_STATE_AWAIT_Y_COLUMN);
        break;
    case CON_STATE_AWAIT_Y_COLUMN:             /* $fc4388 — ...and its second */
        place_cursor(&con, (uint16_t)(ch - CON_ESCAPE_BIAS), be16(image + CON_ESCAPE_Y_ROW));
        set_state(&con, CON_STATE_NORMAL);
        break;
    case CON_STATE_AWAIT_FOREGROUND:           /* $fc43a4 — ESC b's colour byte */
        wr16(image + CON_COLOUR_FOREGROUND, (uint16_t)(ch - CON_ESCAPE_BIAS));
        set_state(&con, CON_STATE_NORMAL);
        break;
    case CON_STATE_AWAIT_BACKGROUND:           /* $fc43b8 — ESC c's */
        wr16(image + CON_COLOUR_BACKGROUND, (uint16_t)(ch - CON_ESCAPE_BIAS));
        set_state(&con, CON_STATE_NORMAL);
        break;
    default:
        /* The vector is RAM and a program may point it anywhere — at a VDI escape handler of its
         * own, or at the same six after a resolution change re-initialised the block. */
        recreate_not_reconstructed("BIOS Bconout(CON:): the console state vector at $4a8 is none of "
                                   "the six routines the ROM's own escape machine installs");
    }
    return con.result;
}

uint32_t console_output_raw(uint8_t *image, uint32_t entry_d0, uint16_t character)
{
    Console con = { image, entry_d0 };

    put_glyph(&con, (uint16_t)(character & CON_CHARACTER_MASK));
    return con.result;
}
