/* hud.c — the eleven leaves of the status panel pass at $b346.
 *
 * `FUN_0000b346` runs nine `bsr`s once a frame out of the game loop: the record list's display
 * ($b39c), the four-digit counter ($b54c), the score ($b74a), the high score ($b7c6), the meter
 * ($b61e), the six HUD slots ($b8f0), the panel's animation ($bbca), a text pass ($bd32), and the
 * table-select at $b372. Everything reconstructed here is a leaf of that pass, plus the score and
 * counter accumulators the rest of the game calls to move the numbers the pass draws.
 *
 * WHAT THE NAMES CLAIM. The mechanism, and no more — ../names.txt's rule for this whole region.
 * `bcd_add_score_bd70` says a packed-BCD longword is added to $bd70; that $bd70 is "the score" is a
 * reading of three call sites ($b74a draws it as eight digits and thresholds it to size the meter,
 * $b7c6 draws max($bd70, $bd74)), not something this file proves. `hud_blit_panel_frame` says an
 * indexed 24x32-byte bitmap is copied to a fixed spot on the back buffer; what it depicts is open.
 *
 * TWO THINGS THE DIFFERENTIAL CANNOT SEE, both registered in ../recreate/STATUS.md:
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
static uint8_t *screen_at(uint8_t *image, uint32_t origin) {
    return image + addr_add(be32(image + WB_SCREEN_BACK), origin);
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
 * right half of a 16-pixel group), which is why these are byte stores and not a longword.
 */
uint32_t hud_blit_meter_cell(uint8_t *image, uint32_t offset_cursor, uint32_t cell) {
    uint8_t *destination = screen_at(image, sign_ext16(be16(image + offset_cursor)));
    const uint8_t *source = image + cell;
    for (unsigned row = 0; row < WB_METER_CELL_ROWS; row++) {
        for (unsigned plane = 0; plane < WB_PLANES; plane++)
            destination[plane * WB_PLANE_STRIDE] = *source++;
        destination += WB_SCREEN_LINE;
    }
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
