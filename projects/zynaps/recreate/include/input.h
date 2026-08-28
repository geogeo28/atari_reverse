/* input.h — the on-screen keyboard's hit test in src/input.c. Subsystem: input.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 *
 * The other input routine of this subsystem, `ikbd_send_cmd` @ 0x14444, is BLOCKED at kit level
 * (it busy-waits on the IKBD ACIA status at $fffc00 and writes $fffc02, neither of which the trap
 * model can serve) — its row in STATUS.md's "Not reconstructed, and why" is the whole argument.
 * Nothing here depends on it.
 */
#ifndef ZYNAPS_INPUT_H
#define ZYNAPS_INPUT_H

#include <stdint.h>

/* ================================================================================================
 * The globals this subsystem owns.
 * ============================================================================================= */
/* Where the name-entry screen's gunsight cursor sits, in playfield pixels. */
#define A_osk_cursor_x 0x19d44u
#define A_osk_cursor_y 0x19d46u

/* One byte per screen column of the on-screen keyboard, three rows of them, sitting as PC-relative
 * data inside the text segment. Ten keys per row at a three-column stride, and the two bytes
 * between neighbouring keys are 0 — so the cursor only picks a key when it is on the key's own
 * column. Read off the image: the rows spell A..J, K..T and U..Z plus space, Delete, Esc, Return
 * (scancodes 0x1e/0x30/0x2e/0x20/0x12/0x21/0x22/0x23/0x17/0x24, then 0x25..0x14, then
 * 0x16/0x2f/0x11/0x2d/0x15/0x2c/0x39/0x53/0x01/0x1c). */
#define A_osk_row_top 0x132e2u
#define A_osk_row_middle 0x132feu
#define A_osk_row_bottom 0x1331au

/* ================================================================================================
 * The grid, in the coordinates the routine works in.
 * ============================================================================================= */
/* Both cursor coordinates are first biased by the grid's own origin (`sub.w #$38` / `sub.w #$20`).
 * The x bias is undone again by OSK_COLUMN_FIRST below — the two together are names.txt's
 * "column = (X-0x68)>>3" — but they are spelt separately because the instructions are. */
#define OSK_X_ORIGIN 0x38
#define OSK_Y_ORIGIN 0x20

/* The three row bands, as biased y. They are closed at the top and inclusive at the bottom, and
 * they SHARE their boundaries: a biased y of exactly 0x70 belongs to the top row, because that
 * row's `ble` is tested first. */
#define OSK_ROW_BAND_TOP 0x60
#define OSK_ROW_TOP_MAX 0x70
#define OSK_ROW_MIDDLE_MAX 0x80
#define OSK_ROW_BOTTOM_MAX 0x90

/* The column band, as biased x, and the shift from pixels to columns. */
#define OSK_COLUMN_FIRST 0x30
#define OSK_COLUMN_LAST 0x110
#define OSK_COLUMN_SHIFT 3

/* ================================================================================================
 * Prototypes.
 * ============================================================================================= */
uint32_t onscreen_keyboard_hit_test(const uint8_t *image, uint32_t scratch);

#endif /* ZYNAPS_INPUT_H */
