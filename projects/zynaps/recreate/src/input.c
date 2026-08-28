/* input.c — the on-screen keyboard's hit test.
 *
 * The high-score name-entry screen (0x12fd4) draws three rows of letters and moves a gunsight
 * cursor over them with the joystick; pressing fire asks this routine which key, if any, the cursor
 * is on. Its answer is a raw IKBD scancode, or 0 for "off the grid".
 */
#include "machine.h"
#include "input.h"

/* Which row table a biased y falls in, or 0 for none.
 *
 * The original spells this as six comparisons, not three: after each `ble` that selects a row it
 * repeats the same bound as a `blt` to the miss. Those three repeats are UNREACHABLE — the `ble`
 * before each has already taken every value they could catch — so they are not reproduced. */
static uint32_t osk_row_table(int16_t y) {
    if (y < OSK_ROW_BAND_TOP)
        return 0;
    if (y <= OSK_ROW_TOP_MAX)
        return A_osk_row_top;
    if (y <= OSK_ROW_MIDDLE_MAX)
        return A_osk_row_middle;
    if (y <= OSK_ROW_BOTTOM_MAX)
        return A_osk_row_bottom;
    return 0;
}

/* onscreen_keyboard_hit_test @ 0x1326e — no register inputs but D0's own previous contents.
 *
 * D0 IS THE ANSWER AND ALSO AN INPUT. The routine loads the cursor's y into D0 as a WORD, works on
 * it there, and then overwrites only the low BYTE with the scancode — so on a hit the register
 * comes back carrying the caller's own high word, and the high byte of the biased y under that.
 * A miss is the one path that clears the whole register (`moveq #$0,d0`). `scratch` is that
 * incoming D0, and the returned value is the outgoing one.
 *
 * Everything else the routine touches is saved and restored by its own `movem`. */
uint32_t onscreen_keyboard_hit_test(const uint8_t *image, uint32_t scratch) {
    uint16_t column = (uint16_t)(be16(image + A_osk_cursor_x) - OSK_X_ORIGIN);
    uint16_t probe = (uint16_t)(be16(image + A_osk_cursor_y) - OSK_Y_ORIGIN);
    uint32_t row = osk_row_table((int16_t)probe);

    if (row == 0)
        return 0;
    if ((int16_t)column < OSK_COLUMN_FIRST || (int16_t)column > OSK_COLUMN_LAST)
        return 0;

    uint16_t index = (uint16_t)(column - OSK_COLUMN_FIRST) >> OSK_COLUMN_SHIFT;

    return set_low_word(scratch, set_low_byte(probe, image[row + index]));
}

/* ================================================================================================
 * Glue. Register map: D0 in = the caller's scratch (see above), D0 out = the scancode. Neither is
 * memory, so the answer reaches the diff through the `jsr`+store stub in test/abi.py.
 * ============================================================================================= */
void g_onscreen_keyboard_hit_test(uint8_t *image, uint32_t result, uint32_t scratch) {
    wr32(image + result, onscreen_keyboard_hit_test(image, scratch));
}
