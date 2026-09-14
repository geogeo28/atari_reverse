/* XBIOS Keytbl (16) — $fc302e — and Bioskeys (24) — $fc305a.
 *
 * One file: they are the two halves of one mechanism, the three-longword `keytbl` struct at $0e62
 * that the IKBD interrupt handler translates scancodes through. Keytbl replaces any of the three
 * tables and reports the struct; Bioskeys puts the ROM's own three back.
 *
 *   Keytbl:  tst.l   4(sp)                   ; unshifted
 *            bmi.s   .shifted                ; ...a NEGATIVE pointer means "leave this one alone"
 *            move.l  4(sp),KEYTBL_STRUCT
 *   .shifted: ...the same for 8(sp) at +4, and 12(sp) at +8
 *            move.l  #KEYTBL_STRUCT,d0       ; ...and the struct itself is the return value
 *            rts
 *
 *   Bioskeys: move.l #KEYTBL_UNSHIFTED_ROM,KEYTBL_STRUCT
 *             move.l #KEYTBL_SHIFTED_ROM,KEYTBL_STRUCT+4
 *             move.l #KEYTBL_CAPSLOCK_ROM,KEYTBL_STRUCT+8
 *             rts
 *
 * BIOSKEYS LEAVES D0 ALONE — it sets no return value at all, so what a caller sees is whatever the
 * trap dispatcher left there. Hence the `void`: there is no result to describe.
 *
 * THE THREE POINTERS ARE TESTED AS SIGNED LONGS, which is the ROM's way of spelling "-1 means skip"
 * and costs nothing real: every address on an ST has bit 31 clear.
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "m68k_idioms.h"

static void install(uint8_t *image, uint32_t field, uint32_t table)
{
    if (!keeps_current_value_long(table))
        wr32(image + KEYTBL_STRUCT + field, table);
}

uint32_t xbios_keytbl(uint8_t *image, uint32_t unshifted, uint32_t shifted, uint32_t capslock)
{
    install(image, KEYTBL_FIELD_UNSHIFTED, unshifted);
    install(image, KEYTBL_FIELD_SHIFTED, shifted);
    install(image, KEYTBL_FIELD_CAPSLOCK, capslock);
    return KEYTBL_STRUCT;
}

void xbios_bioskeys(uint8_t *image)
{
    wr32(image + KEYTBL_STRUCT + KEYTBL_FIELD_UNSHIFTED, KEYTBL_UNSHIFTED_ROM);
    wr32(image + KEYTBL_STRUCT + KEYTBL_FIELD_SHIFTED, KEYTBL_SHIFTED_ROM);
    wr32(image + KEYTBL_STRUCT + KEYTBL_FIELD_CAPSLOCK, KEYTBL_CAPSLOCK_ROM);
}
