/* trp13.S — THE AES's BIOS DOOR as the ROM spells it, `$fee478..$fee487`: the TRANSCRIPTION a target build ships,
 * trp14's sibling (`src/aes/trp14.S`).
 *
 * WHY THIS IS ASSEMBLY, BY THE MEASUREMENT. The door pops its own return address so that the trap finds ITS CALLER's
 * frame at (sp) — whatever its caller pushed — and returns through a longword of RAM. Its C twin (`aes_trp13`,
 * `src/desk/deskleaf.c`) takes the function and the six words the widest caller pushes and lays them again: 214
 * cycles more a call than these four instructions — 1.355 at Drvmap's arrival, 1.253 at the forced media change's,
 * 1.053 at Bconout's (a scratch probe on both blobs, band 6 wave 1a) — over the 1.10 bar on two of the three, so by
 * the rule the door ships as the ROM's own instructions. `test/test_desk_leaves.py` pins its sixteen bytes on both
 * blobs and holds it to the ROM over the frames the hands' chains' callers push.
 *
 * A ROW OF `include/transcribed.h` SINCE ITS FLIP (band 6 slice F1; band 6 wave 1a held it linked and not entered, a
 * kind of its own): the Line-F table's two entries for `$fee478` are this entry, OURS, NATIVE (`bench/linef_table.py`),
 * and a C caller of `aes_trp13` reaches it through the shipped build's glue, as trp14's do.
 *
 * REGISTERS: D0, the BIOS's answer, and whatever the function called does not keep (the BIOS's dispatcher keeps
 * D3-D7/A3-A7 and no more: a C caller's glue owes D2 and A2, as trp14's row says of it).
 */
#include "addrs.h"
#include "aes/aes.h"

    .text

    .globl  aes_rom_trp13
aes_rom_trp13:
    move.l  (%sp)+,(AES_BIOS_RETURN).l
    trap    #13
    move.l  (AES_BIOS_RETURN).l,-(%sp)
    rts
