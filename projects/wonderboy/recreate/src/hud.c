/* hud.c — the status panel pass at $b346, everywhere below its own entry.
 *
 * `panel_refresh_frame` ($b346) runs nine `bsr`s once a frame out of the game loop: the record
 * list's display ($b39c), the four-digit counter ($b54c), the score ($b74a), the high score ($b7c6),
 * the meter ($b61e), the six HUD slots ($b8f0), the panel's animation ($bbca), the stage number
 * ($bd32) and the table-select at $b372. This file holds twenty of the routines under it — the
 * ELEVEN LEAVES of batch 2 first, then THE SECOND TIER above them (see the banner further down; by
 * leaf and non-leaf the split is TWELVE and EIGHT, since the digit plotter calls nothing) — plus the
 * score and counter accumulators the rest of the game calls to move the numbers the pass draws.
 * $b346 itself is not here: four of its ten calls are still unported (../names.txt says which).
 *
 * WHAT THE NAMES CLAIM. The mechanism, and no more — ../names.txt's rule for this whole region.
 * `bcd_add_score_bd70` says a packed-BCD longword is added to $bd70; that $bd70 is "the score" is a
 * reading of three call sites ($b74a draws it as eight digits and thresholds it to size the meter,
 * $b7c6 draws max($bd70, $bd74)), not something this file proves. `hud_blit_panel_frame` says an
 * indexed 24x32-byte bitmap is copied to a fixed spot on the back buffer; what it depicts is open.
 *
 * FOUR THINGS THE DIFFERENTIAL CANNOT SEE, all registered in ../recreate/STATUS.md:
 *
 *   * THE X FLAG THE FOUR BCD ROUTINES ARE ENTERED WITH. `abcd`/`sbcd` add in the 68000's extend
 *     bit, and the two instructions before the first one (`move.w d0,$bd78` and `lea`) leave X
 *     alone — so the first digit pair inherits the CALLER's X. The kit's oracle FORCES SR = $2700
 *     after its reset (a 68000 reset leaves the condition codes alone, so without the force a run
 *     would inherit the previous one's), and `emu.run` has no way to set the entry CCR — so X = 0 is
 *     the only entry condition any case can produce and the only one reproduced below. It is not
 *     always 0 in the game: at $e058 `subq.w #1,hud_meter_value` sets X when the meter was already
 *     zero, and $e064 calls bcd_add_score_bd70 two instructions later, so a meter at zero scores one
 *     extra unit. Pinned as far as it goes — a case adding 0 to 0 reddens if the port assumes
 *     X = 1 — and honestly unpinned beyond that.
 *   * THE REGISTERS THE BLITS LEAVE BEHIND. Each advances its source and destination past the last
 *     byte it moved; only `hud_blit_meter_cell`'s cursor is read back by a caller ($b61e divides
 *     the distance it travelled by 2 to count the cells it drew), so only that one is returned.
 *     The others are dead at every call site, which is checked rather than assumed: all eighteen
 *     $bb8a/$bba0 sites in $b8f0 reload both registers immediately before the `bsr`, and all five
 *     $b6c2 sites in $b61e ($b648, $b660, $b676, $b68c, $b6b8 — two of them inside a `dbf` loop and
 *     three the arms of a one-shot branch chain) `lea` a2 in the instruction immediately before.
 *   * THE DIGIT REGISTER `hud_plot_digit` LEAVES BEHIND. d7 is that routine's other output — every
 *     plot rotates it left by a nibble and the caller keeps the result — and d7 is not one of the
 *     four registers the oracle reports. The rotation is pinned through what it SELECTS (all sixteen
 *     nibbles) and through the three field walks, which draw the wrong digits if it is wrong; only
 *     the register's value at the `rts` is unobservable.
 *   * WHICH HALF OF THE CALLER'S d7 ENDS UP UNDER A WORD FIELD. `move.w field,d7 / swap d7` puts the
 *     caller's high word in the low half, and no walk rotates it back up — so `>> 16` and
 *     `& 0xffff` are indistinguishable here. Faithful by reading, and no seeding can change that.
 */
#include "machine.h"
#include "hud.h"
#include "wonderboy.h"

/* EVERY address below goes through machine.h's `addr_add`, which moves a base by a delta in 32 bits
 * the way the 68000's address ALU does, and only the RESULT is added to `image` — see that helper
 * for why a host pointer cannot be handed the delta directly. The `$20` selector case reddened
 * until it was.
 *
 * Where a blit's rows land: the back buffer is a longword IN MEMORY, so each of the three blits that
 * resolve their own destination reads it rather than carrying an address
 * (`movea.l $750.w,a1 / adda.w #origin,a1`). */
static uint32_t screen_cursor(const uint8_t *image, uint32_t origin) {
    return addr_add(be32(image + WB_SCREEN_BACK), origin);
}

static uint8_t *screen_at(uint8_t *image, uint32_t origin) {
    return image + screen_cursor(image, origin);
}

/* `mulu.w #stride,d0` is a 32-bit multiply, but the `adda.w`/`lea (0,An,d0.w)` that consumes it
 * keeps only the LOW WORD and sign-extends that — so an index big enough to push a bit past 15
 * loses it, and one whose product has bit 15 set addresses BELOW the table. Both are reproduced
 * because they are what the instructions do; the game's own indices stay far inside the table. */
static const uint8_t *indexed_bitmap(const uint8_t *image, uint32_t table, uint32_t index,
                                     uint32_t stride) {
    return image + addr_add(table, sign_ext16(index * stride));
}

/* A rectangular blit of `rows` rows of `row_bytes`, moved as `move.l (a0)+,(a1)+`: the source runs
 * contiguously and the destination steps one scanline per row. Three of the four longword blits
 * below are exactly this and differ only in their geometry (the record bitmap, the HUD-slot copy and
 * the panel frame). `hud_blit_cell_or` is the fourth and stays separate: its combine has to READ the
 * destination, which is the whole difference between it and the copy. */
static void copy_rows(uint8_t *destination, const uint8_t *source, unsigned row_bytes,
                      unsigned rows) {
    for (unsigned row = 0; row < rows; row++) {
        for (unsigned i = 0; i < row_bytes; i += 4)
            wr32(destination + i, be32(source + i));
        source += row_bytes;
        destination += WB_SCREEN_LINE;
    }
}

/* One 8-pixel COLUMN: `rows` rows of the four plane bytes at +0/+2/+4/+6, stepping one scanline per
 * row and `source_step` bytes along the source. Two routines plot exactly this — the meter's cell
 * ($b6c2, WB_METER_CELL_ROWS rows) and the digit plotter ($b850, WB_DIGIT_ROWS) — with the same
 * `move.b` / `lea 160(a0)` shape and different sources. Returns the cursor the original leaves in
 * a0, which only the digit plotter's caller reads back. */
static uint32_t plot_column(uint8_t *image, uint32_t cursor, const uint8_t *source,
                            unsigned source_step, unsigned rows) {
    for (unsigned row = 0; row < rows; row++) {
        for (unsigned plane = 0; plane < WB_PLANES; plane++)
            image[addr_add(cursor, plane * WB_PLANE_STRIDE)] = source[plane];
        source += source_step;
        cursor = addr_add(cursor, WB_SCREEN_LINE);
    }
    return cursor;
}

/* ---- $b372: publish a table, tick the counter -------------------------------------------------
 *
 * The two halves are unrelated to each other and to the rest of the panel; they are one routine
 * because the pass calls one thing last. The tick is `rng_next`'s only non-hardware entropy, and
 * this is its ONLY writer in the whole image (a longword scan finds two operand references: this
 * one and `rng_next`'s read).
 */
void select_table_21e8c_and_tick_b39a(uint8_t *image) {
    uint32_t table = be16(image + WB_STATE_FLAG_A32) ? WB_TABLE_A32_SET : WB_TABLE_A32_CLEAR;
    wr32(image + WB_TABLE_PTR_21E8C, table);
    wr16(image + WB_FRAME_TICK_B39A, (uint16_t)(be16(image + WB_FRAME_TICK_B39A) + 1));
}

/* ---- $b410: the record list's bitmap ----------------------------------------------------------
 *
 * Called from $b3be with a0 = effect_record_write_ptr's value, so the byte it reads is the HIGH
 * byte of the newest record — the 5/6/7/8 of the four `effect_push_record_*` handlers.
 *
 * `move.b (a0),d0` replaces only d0's low byte, so d0's own high byte survives into the `mulu.w`.
 * It cannot reach the result: the product's low word is `(byte & $3f) << 10`, and everything the
 * high byte contributes is at bit 18 and above, which the `adda.w` discards. test_hud.py enters
 * the oracle with a poisoned d0 to pin that rather than leave it argued.
 */
void hud_blit_record_bitmap(uint8_t *image, uint32_t record) {
    const uint8_t *source = indexed_bitmap(image, WB_RECORD_BITMAP_TABLE, image[record],
                                           WB_RECORD_BITMAP_LEN);
    copy_rows(screen_at(image, WB_RECORD_BITMAP_ORIGIN), source,
              WB_RECORD_BITMAP_BYTES, WB_RECORD_BITMAP_ROWS);
}

/* ---- the packed-BCD accumulators --------------------------------------------------------------
 *
 * `abcd`/`sbcd` in the 68000's exact shape, extend bit and all — the decimal correction happens on
 * the nibble sums, not on the byte, so a nibble above 9 (which the game never produces, and which
 * the 68000's manual leaves undefined) still has a defined result under the oracle. The unsigned
 * wrap in the subtract is deliberate: a borrow makes the intermediate huge, which is exactly what
 * drives the `> 9` and `> 0x99` corrections.
 */
static uint8_t abcd_byte(uint8_t addend, uint8_t accumulator, unsigned *extend) {
    unsigned result = (addend & 0x0fu) + (accumulator & 0x0fu) + *extend;
    if (result > 9u)
        result += 6u;
    result += (addend & 0xf0u) + (accumulator & 0xf0u);
    *extend = result > 0x99u;
    if (*extend)
        result -= 0xa0u;
    return (uint8_t)result;
}

static uint8_t sbcd_byte(uint8_t subtrahend, uint8_t accumulator, unsigned *extend) {
    unsigned result = (accumulator & 0x0fu) - (subtrahend & 0x0fu) - *extend;
    if (result > 9u)
        result -= 6u;
    result += (accumulator & 0xf0u) - (subtrahend & 0xf0u);
    *extend = result > 0x99u;
    if (*extend)
        result += 0xa0u;
    return (uint8_t)result;
}

/* The extend bit the FIRST digit pair folds in. Zero is what the oracle's reset SR gives and all a
 * case can produce; the file comment above says why that is a claim about the harness rather than
 * about the game. */
#define BCD_ENTRY_EXTEND 0u

/* All four routines are the same walk: `abcd -(a0),-(a1)` pairs stepping DOWN from the byte past
 * the addend and the byte past the accumulator, so index `i` reads the same offset into both. */
static void bcd_add(uint8_t *image, uint32_t accumulator, unsigned length) {
    unsigned extend = BCD_ENTRY_EXTEND;
    for (unsigned i = length; i-- > 0; )
        image[accumulator + i] = abcd_byte(image[WB_BCD_ADDEND + i], image[accumulator + i],
                                           &extend);
}

static void bcd_sub(uint8_t *image, uint32_t accumulator, unsigned length) {
    unsigned extend = BCD_ENTRY_EXTEND;
    for (unsigned i = length; i-- > 0; )
        image[accumulator + i] = sbcd_byte(image[WB_BCD_ADDEND + i], image[accumulator + i],
                                           &extend);
}

/* `move.w d0,$bd78` stages only two bytes, so the addend's high word never reaches the digits. */
void bcd_add_counter_bd6e(uint8_t *image, uint32_t addend) {
    wr16(image + WB_BCD_ADDEND, (uint16_t)addend);
    bcd_add(image, WB_BCD_COUNTER, WB_BCD_COUNTER_LEN);
}

void bcd_sub_counter_bd6e(uint8_t *image, uint32_t subtrahend) {
    wr16(image + WB_BCD_ADDEND, (uint16_t)subtrahend);
    bcd_sub(image, WB_BCD_COUNTER, WB_BCD_COUNTER_LEN);
}

/* ...and `move.l d0,$bd78` stages all four, for the eight-digit score. */
void bcd_add_score_bd70(uint8_t *image, uint32_t addend) {
    wr32(image + WB_BCD_ADDEND, addend);
    bcd_add(image, WB_BCD_SCORE, WB_BCD_SCORE_LEN);
}

void bcd_sub_score_bd70(uint8_t *image, uint32_t subtrahend) {
    wr32(image + WB_BCD_ADDEND, subtrahend);
    bcd_sub(image, WB_BCD_SCORE, WB_BCD_SCORE_LEN);
}

/* ---- $b6c2: one meter cell --------------------------------------------------------------------
 *
 * `adda.w (a1)+,a0` adds the cell's screen offset as a SIGNED word and leaves the cursor on the
 * next entry, which is the routine's return value. The four `move.b` per row write the four plane
 * bytes of one 8-pixel column; the table's offsets are odd as often as even (an odd one is the
 * right half of a 16-pixel group), which is why these are byte stores and not a longword. That
 * column is `plot_column` above — the same shape the digit plotter draws, and the ADVANCED cursor
 * it returns is the one thing this routine does NOT hand back (its caller reads the offset cursor).
 */
uint32_t hud_blit_meter_cell(uint8_t *image, uint32_t offset_cursor, uint32_t cell) {
    uint32_t cursor = screen_cursor(image, sign_ext16(be16(image + offset_cursor)));
    plot_column(image, cursor, image + cell, WB_PLANES, WB_METER_CELL_ROWS);
    return offset_cursor + WB_METER_CELL_OFFSET_LEN;
}

/* ---- $b6fe: the meter's clamped add -----------------------------------------------------------
 *
 * The general form of the two fixed-amount handlers in src/effects.c, and NOT the same comparison:
 * this one stores the raised value into the meter FIRST (`add.w d0,$b6fa` is a read-modify-write on
 * memory) and only then tests, and its `ble` clamps when the raised value REACHES the maximum where
 * the handlers' `bgt` still stores. Both are signed 16-bit, and both wrap.
 */
void hud_meter_add_clamped(uint8_t *image, uint32_t amount) {
    uint16_t raised = (uint16_t)(be16(image + WB_HUD_METER_VALUE) + (uint16_t)amount);
    wr16(image + WB_HUD_METER_VALUE, raised);
    int16_t maximum = (int16_t)be16(image + WB_HUD_METER_MAX);
    if (maximum <= (int16_t)raised)
        wr16(image + WB_HUD_METER_VALUE, (uint16_t)maximum);
}

/* ---- $bb8a / $bba0: one HUD-slot cell ---------------------------------------------------------
 *
 * Identical geometry, different combine. $b8f0 uses the copy to blank a slot's cell (its source is
 * a blank tile) and the OR to lay an icon over the blanked cell, which is why the OR form must READ
 * the destination — a port that copied would agree with it on a zeroed screen and on nothing else.
 */
void hud_blit_cell_copy(uint8_t *image, uint32_t source, uint32_t destination) {
    /* Both come in as whole addresses (a0, a1) — this pair is the one that does NOT read $750. */
    copy_rows(image + destination, image + source, WB_HUD_CELL_BYTES, WB_HUD_CELL_ROWS);
}

void hud_blit_cell_or(uint8_t *image, uint32_t source, uint32_t destination) {
    const uint8_t *from = image + source;
    uint8_t *to = image + destination;
    for (unsigned row = 0; row < WB_HUD_CELL_ROWS; row++) {
        for (unsigned i = 0; i < WB_HUD_CELL_BYTES; i += 4)
            wr32(to + i, be32(to + i) | be32(from + i));
        from += WB_HUD_CELL_BYTES;
        to += WB_SCREEN_LINE;
    }
}

/* ---- $bcd6: the panel's animation frame -------------------------------------------------------
 *
 * The original moves each row as `movem.l (a0)+,d0-d5 / movem.l d0-d5,offset(a1)`, six longwords at
 * a time and four rows per iteration — a speed shape, not a semantic one, so the C is one row loop.
 * The index is a word in memory that $bbca cycles 0..12; no register reaches this routine.
 */
void hud_blit_panel_frame(uint8_t *image) {
    const uint8_t *source = indexed_bitmap(image, WB_PANEL_FRAME_TABLE,
                                           be16(image + WB_PANEL_FRAME_INDEX), WB_PANEL_FRAME_LEN);
    copy_rows(screen_at(image, WB_PANEL_FRAME_ORIGIN), source,
              WB_PANEL_FRAME_BYTES, WB_PANEL_FRAME_ROWS);
}

/* ================================================================================================
 * THE SECOND TIER — the routines that CALL the leaves above.
 *
 * Each one runs its callees under the oracle on the original's side and calls the ported C here on
 * ours, which is the whole difference from the batches before it. Two things follow.
 *
 * WHERE A CURSOR LIVES. The digit plotter and the meter both hand their caller an advanced 68000
 * ADDRESS REGISTER, and both callers consume it: the digit walks step the cursor to the next column,
 * the meter halves the distance its cursor travelled to count the cells it drew. So those addresses
 * are `uint32_t`s threaded through the C the way they are threaded through a0/a1, not host pointers.
 *
 * THE REGISTERS THAT ARRIVE UNSET. $bd32/$bd4a and $b74a/$b7c6/$b7ea read d0 without any caller in
 * the image ever setting it — panel_refresh_frame `bsr`s straight into them — so the glyph table
 * these four fields are drawn with is whatever the previous routine happened to leave behind. That
 * is the game's behaviour, not a gap in the reading: the port takes d0 as an argument and every
 * battery sweeps both sides of the `cmpi.w #1,d0`.
 * ============================================================================================== */

/* ---- $b850: one packed-BCD digit ---------------------------------------------------------------
 *
 * `rol.l #4,d7` FIRST, then `d6 = d7 & $f` — so the digit drawn is the nibble that was at the TOP of
 * the register on entry, and the caller keeps the rotated value for the next column. Eight rows of
 * one 8-pixel column: the four plane bytes at +0/+2/+4/+6, `adda.l #$a0,a0` between rows.
 *
 * `digit_significant_seen_b84e` is the leading-zero latch. While it is clear a zero nibble is drawn
 * BLANK and no glyph is fetched; the first non-zero nibble raises it, and every digit after that
 * prints. A blank is not the same thing under both fonts: under the alternate glyphs it is four
 * cleared planes, under the default ones plane 1 is `st` to $ff — a solid bar, not nothing.
 */

/* `rol.l #n,Dn` — a 32-bit ROTATE, not a shift: the bits that leave the top come back in at the
 * bottom, and both users depend on that. */
static uint32_t rotate_left32(uint32_t value, unsigned bits) {
    return (value << bits) | (value >> (32 - bits));
}

/* One nibble is what `rol.l #4,d7` brings to the top of the register, and one byte what `rol.l #8`
 * does in hud_draw_stage_number. */
#define BITS_PER_NIBBLE 4u
#define BITS_PER_BYTE   8u

/* A blank column holds one row's worth of bytes and repeats it, so its source does not advance. */
#define BLANK_SOURCE_STEP 0u

uint32_t hud_plot_digit(uint8_t *image, uint32_t font_select, uint32_t cursor, uint32_t *digits) {
    /* `cmpi.w #$1,d0` reads d0's low WORD only, so a caller's high half cannot select a font. */
    int alternate = (uint16_t)font_select == WB_DIGIT_FONT_ALT;
    *digits = rotate_left32(*digits, BITS_PER_NIBBLE);
    unsigned nibble = *digits & WB_DIGIT_NIBBLE_MASK;

    if (be16(image + WB_DIGIT_SIGNIFICANT_SEEN) == 0) {
        if (nibble == 0) {
            uint8_t blank[WB_PLANES] = {0};
            if (!alternate)
                blank[WB_DIGIT_BLANK_PLANE] = WB_DIGIT_BLANK_FILL;
            return plot_column(image, cursor, blank, BLANK_SOURCE_STEP, WB_DIGIT_ROWS);
        }
        wr16(image + WB_DIGIT_SIGNIFICANT_SEEN, WB_DIGIT_SIGNIFICANT_SET);
    }
    uint32_t glyphs = alternate ? WB_DIGIT_GLYPHS_ALT : WB_DIGIT_GLYPHS;
    /* `asl.w #5,d6 / adda.l d6,a1`: the `andi.l` above cleared d6's high word and the shifted
     * nibble cannot reach it again, so this is a plain 32-bit add of 0..480. */
    const uint8_t *glyph = image + addr_add(glyphs, nibble * WB_DIGIT_GLYPH_LEN);
    return plot_column(image, cursor, glyph, WB_PLANES, WB_DIGIT_ROWS);
}

/* ---- $b5ea / $b7ea / $bd4a: one field of digits ------------------------------------------------
 *
 * The same walk three times over, and deliberately not folded into one loop: the three differ in
 * where they force the latch, in which digits get the caller's font, and in whether the cursor is
 * stepped after the LAST digit — differences a shared loop would have to carry as three flags.
 * `rewind` is the caller's own `suba.l`, applied to the cursor $b850 left eight scanlines down.
 */
static uint32_t plot_digit_then_step(uint8_t *image, uint32_t font_select, uint32_t cursor,
                                     uint32_t *digits, uint32_t rewind) {
    return addr_add(hud_plot_digit(image, font_select, cursor, digits), 0u - rewind);
}

static void force_significant(uint8_t *image) {
    wr16(image + WB_DIGIT_SIGNIFICANT_SEEN, WB_DIGIT_SIGNIFICANT_SET);
}

static void clear_significant(uint8_t *image) {
    wr16(image + WB_DIGIT_SIGNIFICANT_SEEN, 0);
}

void hud_draw_four_digits(uint8_t *image, uint32_t cursor, uint32_t digits) {
    /* `moveq #0,d0` before the first plot, and nothing touches d0 after it. */
    const uint32_t font = WB_DIGIT_FONT_DEFAULT;
    cursor = plot_digit_then_step(image, font, cursor, &digits, WB_DIGIT_REWIND_RIGHT_HALF);
    cursor = plot_digit_then_step(image, font, cursor, &digits, WB_DIGIT_REWIND_NEXT_GROUP);
    cursor = plot_digit_then_step(image, font, cursor, &digits, WB_DIGIT_REWIND_RIGHT_HALF);
    force_significant(image);           /* so the LAST digit prints even when the field is zero */
    hud_plot_digit(image, font, cursor, &digits);
    clear_significant(image);
}

void hud_draw_eight_digits(uint8_t *image, uint32_t font_select, uint32_t cursor, uint32_t digits) {
    /* Only the first plot sees the caller's d0: a `moveq #0,d0` follows each of the next five
     * steps, and the last two run on the 0 the sixth left. */
    cursor = plot_digit_then_step(image, font_select, cursor, &digits, WB_DIGIT_REWIND_NEXT_GROUP);
    /* ...and the step alternates from there to the end of the field. Written out, like the original,
     * because the latch is forced before the seventh digit rather than on any cycle. */
    const uint32_t font = WB_DIGIT_FONT_DEFAULT;
    cursor = plot_digit_then_step(image, font, cursor, &digits, WB_DIGIT_REWIND_RIGHT_HALF);
    cursor = plot_digit_then_step(image, font, cursor, &digits, WB_DIGIT_REWIND_NEXT_GROUP);
    cursor = plot_digit_then_step(image, font, cursor, &digits, WB_DIGIT_REWIND_RIGHT_HALF);
    cursor = plot_digit_then_step(image, font, cursor, &digits, WB_DIGIT_REWIND_NEXT_GROUP);
    cursor = plot_digit_then_step(image, font, cursor, &digits, WB_DIGIT_REWIND_RIGHT_HALF);
    force_significant(image);           /* the last TWO digits print whatever the field holds */
    cursor = plot_digit_then_step(image, font, cursor, &digits, WB_DIGIT_REWIND_NEXT_GROUP);
    hud_plot_digit(image, font, cursor, &digits);
    clear_significant(image);
}

void hud_draw_two_digits(uint8_t *image, uint32_t font_select, uint32_t cursor, uint32_t digits) {
    /* The odd one out twice over: the caller's d0 reaches BOTH digits, nothing forces the latch (so
     * a zero high digit is drawn blank), and the cursor is stepped again after the last one. */
    cursor = plot_digit_then_step(image, font_select, cursor, &digits, WB_DIGIT_REWIND_NEXT_GROUP);
    plot_digit_then_step(image, font_select, cursor, &digits, WB_DIGIT_REWIND_RIGHT_HALF);
    clear_significant(image);
}

/* ---- $b54c / $b74a / $b7c6 / $bd32: the four fields panel_refresh_frame draws -------------------
 *
 * Each resolves its own origin in `screen_back` and hands a field of packed BCD to the walk above.
 * The two that load a WORD (`move.w field,d7 / swap d7`) leave the caller's own high word in d7's
 * low half, where the rotations cannot reach it — the cases feed a poisoned d7 to pin that rather
 * than argue it. The two that load a LONGWORD overwrite d7 outright.
 */
/* `move.w field,d7 / swap d7`: the field becomes d7's HIGH word, i.e. the first nibble the walk
 * rotates out, and the caller's high word lands harmlessly below it. */
#define BITS_PER_WORD 16u

static uint32_t staged_word_field(const uint8_t *image, uint32_t field, uint32_t entry_digits) {
    return ((uint32_t)be16(image + field) << BITS_PER_WORD) | (entry_digits >> BITS_PER_WORD);
}

void hud_draw_counter_bd6e(uint8_t *image, uint32_t digits) {
    hud_draw_four_digits(image, screen_cursor(image, WB_COUNTER_ORIGIN),
                         staged_word_field(image, WB_BCD_COUNTER, digits));
}

void hud_draw_stage_number(uint8_t *image, uint32_t font_select, uint32_t digits) {
    uint32_t staged = staged_word_field(image, WB_STAGE_NUMBER, digits);
    /* `rol.l #8,d7`: the two digits drawn are the stage word's LOW byte, since the walk takes the
     * top nibble first and this rotation puts that byte's high nibble there. */
    staged = rotate_left32(staged, BITS_PER_BYTE);
    hud_draw_two_digits(image, font_select, screen_cursor(image, WB_STAGE_ORIGIN), staged);
}

/* The steps of `cmp.l #imm,d7 / blt / move.w #max,hud_meter_max`, in the order the original tests
 * them: highest first, and the first match returns. */
static const struct {
    int32_t score;
    uint16_t maximum;
} METER_SIZE_STEPS[WB_METER_SIZE_STEPS] = {
    {WB_METER_SIZE_SCORE_5, WB_METER_SIZE_MAX_5},
    {WB_METER_SIZE_SCORE_4, WB_METER_SIZE_MAX_4},
    {WB_METER_SIZE_SCORE_3, WB_METER_SIZE_MAX_3},
    {WB_METER_SIZE_SCORE_2, WB_METER_SIZE_MAX_2},
    {WB_METER_SIZE_SCORE_1, WB_METER_SIZE_MAX_1},
};

void hud_draw_score_and_size_meter(uint8_t *image, uint32_t font_select) {
    hud_draw_eight_digits(image, font_select, screen_cursor(image, WB_SCORE_ORIGIN),
                          be32(image + WB_BCD_SCORE));
    /* The score is re-read AFTER the draw, and compared SIGNED — a field whose top nibble is 8 or 9
     * reads negative and matches no step, leaving hud_meter_max untouched. */
    int32_t score = (int32_t)be32(image + WB_BCD_SCORE);
    for (unsigned step = 0; step < WB_METER_SIZE_STEPS; step++) {
        if (score >= METER_SIZE_STEPS[step].score) {
            wr16(image + WB_HUD_METER_MAX, METER_SIZE_STEPS[step].maximum);
            return;
        }
    }
}

void hud_draw_larger_score(uint8_t *image, uint32_t font_select) {
    /* `cmp.l hiscore,d7 / bgt` — signed and strict, so an equal pair takes the HISCORE arm; the two
     * fields hold the same bytes there, which is why only the branch and not the value shows it. */
    int32_t score = (int32_t)be32(image + WB_BCD_SCORE);
    int32_t hiscore = (int32_t)be32(image + WB_BCD_HISCORE);
    hud_draw_eight_digits(image, font_select, screen_cursor(image, WB_HISCORE_ORIGIN),
                          (uint32_t)(score > hiscore ? score : hiscore));
}

/* ---- $b61e: the meter's own pass ---------------------------------------------------------------
 *
 * `value / 4` full cells, then ONE partial cell chosen by `value % 4` (and none at all when the
 * remainder is zero), then `max / 4 - (cells drawn)` empty ones — the count of cells drawn being
 * recovered from the cursor `hud_blit_meter_cell` returns rather than from a counter, which is why
 * that routine's advanced a1 is the one register of the batch below that a caller reads.
 *
 * EVERY ARITHMETIC STEP AFTER THE DIVIDE IS 16-BIT: `asr.w`, `sub.w`, and a `dbf` whose counter is a
 * word. So a maximum smaller than the value drives the empty count NEGATIVE, the `bne` passes, and
 * the `dbf` then runs it down through 65535 iterations, walking the cursor far past
 * meter_cell_offsets. The port reproduces that (`empty` is a uint16_t and the loop is its exact
 * count); no case reaches it, and recreate/STATUS.md registers why.
 */

/* `asr.w #n` — an arithmetic shift of a register's LOW WORD, the high word untouched. */
static uint16_t asr_word(uint16_t value, unsigned bits) {
    return (uint16_t)((int16_t)value >> bits);
}

void hud_draw_meter(uint8_t *image) {
    uint32_t cursor = WB_METER_CELL_TABLE;
    image[WB_PANEL_RESTORE_FLAG_DBB3] = WB_PANEL_RESTORE_FLAG_SET;

    /* `moveq #0,d6 / move.w value,d6 / divu.w #4,d6` — the dividend is zero-extended, so this is an
     * unsigned 16-bit divide and its quotient cannot overflow the word `divu` returns. */
    uint16_t value = be16(image + WB_HUD_METER_VALUE);
    for (uint16_t full = value / WB_METER_CELL_UNITS; full-- > 0; )
        cursor = hud_blit_meter_cell(image, cursor, WB_METER_CELL_FULL);

    switch (value % WB_METER_CELL_UNITS) {
    case 3: cursor = hud_blit_meter_cell(image, cursor, WB_METER_CELL_PARTIAL_3); break;
    case 2: cursor = hud_blit_meter_cell(image, cursor, WB_METER_CELL_PARTIAL_2); break;
    case 1: cursor = hud_blit_meter_cell(image, cursor, WB_METER_CELL_PARTIAL_1); break;
    default: break;
    }

    uint16_t drawn = asr_word((uint16_t)(cursor - WB_METER_CELL_TABLE), 1);
    uint16_t empty = (uint16_t)(asr_word(be16(image + WB_HUD_METER_MAX), 2) - drawn);
    for (uint16_t remaining = empty; remaining-- > 0; )
        cursor = hud_blit_meter_cell(image, cursor, WB_METER_CELL_EMPTY);
}
