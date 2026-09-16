/* XBIOS Kbdvbase ($22) — $fc30bc.
 *
 *      move.l  #$e12,d0
 *      rts
 *
 * TWO INSTRUCTIONS, and what they report is the address of KBDVECS — the block of longwords in the
 * OS's own low RAM through which every IKBD and MIDI interrupt is dispatched. A program that wants
 * its own mouse, joystick or clock handler asks for this and stores into the slot it wants
 * (`Initmous` next door stores `mousevec` at `+$10` through exactly this block), which is why the
 * routine hands back a POINTER and reads nothing: the table is at a fixed address in this ROM.
 *
 * It touches no memory at all, so the constant IS the routine, and a case's whole claim is that the
 * address is the one the ROM's own `move.l #` carries — asserted against the block's contents, which
 * are ROM handler addresses the boot installed.
 */
#include <stdint.h>

#include "addrs.h"

uint32_t xbios_kbdvbase(void)
{
    return KBDVECS;
}
