/* hud.h — the status panel's leaves (src/hud.c).
 *
 * Eleven routines under `FUN_0000b346` ($b346), the game loop's once-a-frame panel pass: four
 * packed-BCD accumulators, five blits (three of which read the `screen_back` longword themselves,
 * while the HUD-slot pair is handed a destination), the meter's clamped add and the table-select /
 * tick at the end of the pass. Names are ../names.txt's, unchanged.
 *
 * Every ADDRESS they touch is a global named in wonderboy.h, which both languages read; nothing
 * here needs a constant of its own, which is why this header carries none.
 *
 * REGISTER ARGUMENTS. Unlike the effect handlers, most of these are entered with values in
 * registers. Ghidra recovered `void FUN(void)` for all eleven, so ../names.txt carries a `proto`
 * line committing the storage for each routine whose interface that directive can express — all but
 * `hud_blit_meter_cell`, whose result is in a1, which a `proto` cannot say (it forces a void
 * return). The C takes those registers as parameters, one `uint32_t` each, so that the operand size
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

#endif /* WONDERBOY_HUD_H */
