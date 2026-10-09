/* trp14.S — THE AES's XBIOS DOOR as the ROM spells it, `$fee488..$fee497`: the TRANSCRIPTION a target build ships.
 *
 * WHY THIS IS ASSEMBLY. The door pops its own return address so that the trap finds ITS CALLER's frame at (sp) — a
 * frame of whatever its caller pushed — and returns through a longword of RAM: a shape no C function has
 * (`aes/trp14.h`). `test/test_aes_trp14.py` pins its sixteen bytes and holds it to the ROM over the frames the
 * ROM's callers push.
 *
 * REGISTERS: D0, the XBIOS's answer, and whatever the function called does not keep (none of the GCC ABI's
 * callee-saved over the cases registered: the XBIOS dispatcher restores them).
 */
#include "addrs.h"
#include "aes/aes.h"

    .text

    .globl  aes_rom_trp14
aes_rom_trp14:
    move.l  (%sp)+,(AES_XBIOS_RETURN).l
    trap    #14
    move.l  (AES_XBIOS_RETURN).l,-(%sp)
    rts
