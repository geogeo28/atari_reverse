/* hud.h — the status panel (src/hud.c).
 *
 * Twenty routines under `panel_refresh_frame` ($b346), the game loop's once-a-frame panel pass.
 * TWELVE LEAVES: four packed-BCD accumulators, five blits (three of which read the `screen_back`
 * longword themselves, while the HUD-slot pair is handed a destination), the meter's clamped add,
 * the table-select / tick at the end of the pass, and the digit plotter — which calls nothing, and
 * is here rather than with the other eleven only because it landed with the tier that needs it.
 * EIGHT NON-LEAVES: the three digit-field walks above the plotter, the four routines $b346 itself
 * calls — the counter, the score, the high score and the stage number — and the meter's own pass.
 * Names are ../names.txt's, unchanged.
 *
 * Every ADDRESS they touch is a global named in wonderboy.h, which both languages read; nothing
 * here needs a constant of its own, which is why this header carries none.
 *
 * REGISTER ARGUMENTS. Unlike the effect handlers, most of these are entered with values in
 * registers. Ghidra recovered `void FUN(void)` for all twenty, so ../names.txt carries a `proto`
 * line committing the storage for each routine whose interface that directive can express. The two
 * it cannot are `hud_blit_meter_cell` and `hud_plot_digit`, whose results are in a1 and a0 — a
 * `proto` forces a void return — and whose d7 is IN AND OUT in the second case. The C takes those
 * registers as parameters, one `uint32_t` each (a pointer for d7), so that the operand size
 * the original applies to them is applied HERE where a differential case can pin it.
 */
#ifndef WONDERBOY_HUD_H
#define WONDERBOY_HUD_H

#include <stdint.h>

/* $b372 — publish one of two table addresses, then tick the counter rng_next mixes in. */
void select_table_21e8c_and_tick_b39a(uint8_t *image);

/* $b410 — a0 = the record whose first byte selects the bitmap. */
void hud_blit_record_bitmap(uint8_t *image, uint32_t record);

/* $b562/$b582 — d0's low WORD is the packed-BCD amount; $b5a2/$b5c6 — d0's whole LONGWORD is. */
void bcd_add_counter_bd6e(uint8_t *image, uint32_t addend);
void bcd_sub_counter_bd6e(uint8_t *image, uint32_t subtrahend);
void bcd_add_score_bd70(uint8_t *image, uint32_t addend);
void bcd_sub_score_bd70(uint8_t *image, uint32_t subtrahend);

/* $b6c2 — a1 = the cursor into the cell-offset table, a2 = the cell's 32 bytes. Returns the
 * ADVANCED cursor, which is the one register its caller reads back (see src/hud.c). */
uint32_t hud_blit_meter_cell(uint8_t *image, uint32_t offset_cursor, uint32_t cell);

/* $b6fe — d0's low word is added to the meter, which is then clamped to its maximum. */
void hud_meter_add_clamped(uint8_t *image, uint32_t amount);

/* $bb8a/$bba0 — a0 = source cell, a1 = destination in screen_back. */
void hud_blit_cell_copy(uint8_t *image, uint32_t source, uint32_t destination);
void hud_blit_cell_or(uint8_t *image, uint32_t source, uint32_t destination);

/* $bcd6 — no arguments: the frame index comes out of memory. */
void hud_blit_panel_frame(uint8_t *image);

/* ---- the second tier: the four routines panel_refresh_frame calls, and their two helpers -------
 *
 * All but the first of these CALL a reconstruction above, which is why their differential cases run
 * the original's callees under the oracle while the C calls the ported C directly. `hud_plot_digit`
 * is the exception and is itself a leaf; it sits here because the walks below cannot be ported
 * without it.
 *
 * `font_select` is the 68000's d0 and `digits` its d7, both taken as whole longwords for the same
 * reason as above: the original applies `cmpi.w` to one and `rol.l`/`swap` to the other, and those
 * operand sizes belong where a case can pin them. `digits` is IN/OUT on `hud_plot_digit` because the
 * original's d7 is: every plot rotates it left by a nibble, and its caller keeps the rotated value.
 */

/* $b850 — d0 = font_select, a0 = the cursor, d7 = the digit register (rotated in place).
 * Returns the cursor eight scanlines lower, which is what the original leaves in a0. */
uint32_t hud_plot_digit(uint8_t *image, uint32_t font_select, uint32_t cursor, uint32_t *digits);

/* $b5ea / $b7ea / $bd4a — one field of digits, left to right, from the top nibble of `digits` down.
 * Only the four-digit form forces the glyphs (`moveq #0,d0`); the other two pass the caller's d0
 * through, the eight-digit one to its FIRST digit only. */
void hud_draw_four_digits(uint8_t *image, uint32_t cursor, uint32_t digits);
void hud_draw_eight_digits(uint8_t *image, uint32_t font_select, uint32_t cursor, uint32_t digits);
void hud_draw_two_digits(uint8_t *image, uint32_t font_select, uint32_t cursor, uint32_t digits);

/* $b54c — d7's LOW word is the dead half: `move.w bcd_counter_bd6e,d7` overwrites it and the `swap`
 * then lifts the counter into the high half, leaving the caller's own HIGH word below the digits —
 * live input, but buried where no rotation reaches it. d0 is unread, since the four-digit form
 * forces its own. */
void hud_draw_counter_bd6e(uint8_t *image, uint32_t digits);

/* $b74a / $b7c6 — d7 is dead at both (each reloads it from memory); d0 reaches the first digit. */
void hud_draw_score_and_size_meter(uint8_t *image, uint32_t font_select);
void hud_draw_larger_score(uint8_t *image, uint32_t font_select);

/* $bd32 — d0 reaches BOTH digits; d7's LOW word is the dead half and its high word survives buried,
 * as in hud_draw_counter_bd6e. */
void hud_draw_stage_number(uint8_t *image, uint32_t font_select, uint32_t digits);

/* $b61e — no registers at all: every input is a word in memory. */
void hud_draw_meter(uint8_t *image);

#endif /* WONDERBOY_HUD_H */
