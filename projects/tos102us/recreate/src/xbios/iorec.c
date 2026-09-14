/* XBIOS Iorec (function 14) — $fc28f6.
 *
 * Hands back the address of one of the three IOREC rings, so a program can read the serial port's
 * buffer size, resize it, or watch the keyboard queue without going through Bconin.
 *
 *      move.w  4(sp),d1            ; the device: 0 = RS232, 1 = IKBD, 2 = MIDI
 *      asl.l   #2,d1
 *      move.l  IOREC_TABLE(pc,d1.w),d0
 *      rts
 *
 * THERE IS NO BOUNDS CHECK. The table is three longwords in the ROM at $fc2902 and a device above 2
 * reads whatever follows it — the first instructions of `Rsconf` — as if it were an address. That is
 * the ROM's behaviour and it is reproduced by reading the image rather than by a switch, so the
 * cases that ask for device 3 and 4 get the ROM's own bytes and not a reconstruction's idea of them.
 *
 * The shift is `asl.l` but the index is taken as `d1.w`, so it is an `asl.w` in every bit that
 * matters: a device of $4000 selects entry 0, exactly as the BIOS's `lsl.w` dispatch does.
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "m68k_idioms.h"

uint32_t xbios_iorec(const uint8_t *image, uint16_t device)
{
    return be32(image + addr_add(IOREC_TABLE, word_index(device, IOREC_TABLE_ENTRY_BYTES)));
}
