/* infscan.c — the DESKTOP.INF field helpers (`aes/infscan.h`): a hex digit each way, and a two-digit field read from
 * or written into the INF text.
 *
 * Alcyon C in the ROM: every Line-F call here is a C call and the Alcyon epilogue C's own return (`aes/aes.h`,
 * "LINE-F"). The digits are compared as the ROM compares them — hex_dig a SIGNED BYTE (`cmp.b`, then `ext.w`, so a
 * character past $7f is no digit), uhex_dig a SIGNED WORD — and the cursors are the caller's longwords, put on the
 * 24-bit bus per byte and handed back with their top byte.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "aes/infscan.h"

/* $fdaf20 — hex_dig: the value of the hex digit in the low byte of `character` ('0'-'9', 'A'-'F' only: the INF
 * text is upper case), 0 for anything else. */
int16_t aes_hex_dig(int16_t character)
{
    int8_t byte = (int8_t)character;

    if (byte >= '0' && byte <= '9')
        return (int16_t)(byte - '0');
    if (byte >= 'A' && byte <= 'F')
        return (int16_t)(byte - ('A' - INF_DECIMAL_BASE));
    return 0;
}

/* $fdaf5c — uhex_dig: the upper-case hex digit of `digit` (0-15), a space for anything else, negatives included. */
int16_t aes_uhex_dig(int16_t digit)
{
    if (digit >= 0 && digit < INF_DECIMAL_BASE)
        return (int16_t)(digit + '0');
    if (digit >= INF_DECIMAL_BASE && digit <= INF_DIGIT_MASK)
        return (int16_t)(digit + ('A' - INF_DECIMAL_BASE));
    return INF_NOT_A_DIGIT;
}

/* $fdaf92 — scan_2: the two hex digits at `cursor` as one value into the caller's word — "ff", the INF's unset
 * field, as -1 — and the cursor past them AND the separator after them, which is skipped unread. Each digit is read
 * as it is converted (`move.b (a5)+`), so nothing is read past the two. */
uint32_t aes_scan_2(uint8_t *image, uint32_t cursor, uint32_t value_out)
{
    int16_t value = (int16_t)(aes_hex_dig((int8_t)bus_byte(image, cursor)) << INF_DIGIT_BITS);

    value |= aes_hex_dig((int8_t)bus_byte(image, cursor + 1));
    if (value == INF_UNSET_FIELD)
        value = INF_UNSET_VALUE;
    set_bus_word(image, value_out, (uint16_t)value);
    return cursor + INF_FIELD_BYTES;
}

/* $fdafca — save_2: the low byte of `value` as two upper-case hex digits at `cursor`, then the separator; the answer
 * the cursor past all three. A value is written as its low BYTE's digits: the high digit is (value >> 4) & 15. */
uint32_t aes_save_2(uint8_t *image, uint32_t cursor, int16_t value)
{
    set_bus_byte(image, cursor, (uint8_t)aes_uhex_dig((int16_t)(((uint16_t)value >> INF_DIGIT_BITS) & INF_DIGIT_MASK)));
    set_bus_byte(image, cursor + 1, (uint8_t)aes_uhex_dig((int16_t)(value & INF_DIGIT_MASK)));
    set_bus_byte(image, cursor + INF_FIELD_DIGITS, INF_FIELD_SEPARATOR);
    return cursor + INF_FIELD_BYTES;
}
