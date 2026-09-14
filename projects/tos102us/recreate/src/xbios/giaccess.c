/* XBIOS Giaccess (function $1c) — $fc2ea4.
 *
 * The one door TOS offers onto the YM2149's register file. It selects a register, optionally writes
 * a byte to it, and always reads the selected register back — which is what makes it usable as a
 * read-modify-write primitive by Ongibit/Offgibit next door.
 *
 *      move.w  4(sp),d0            ; the data byte
 *      move.w  6(sp),d1            ; the register, with GIACCESS_WRITE_FLAG for "write"
 *      move.w  sr,-(sp)
 *      ori.w   #$700,sr            ; the select latch and the data port are two instructions apart
 *      movem.l d1/d2/a0,-(sp)
 *      lea     $ffff8800,a0
 *      move.b  d1,d2
 *      andi.b  #GIACCESS_REGISTER_MASK,d1
 *      move.b  d1,(a0)             ; select
 *      asl.b   #1,d2               ; ...shifting bit 7 into X/C
 *      bcc.s   .read
 *        move.b  d0,2(a0)          ; data
 *   .read:
 *      moveq   #0,d0
 *      move.b  (a0),d0             ; read the selected register back
 *      movem.l (sp)+,d1/d2/a0
 *      move.w  (sp)+,sr
 *
 * THE INTERRUPT MASK IS RECONSTRUCTED; THE REGISTER SAVES ARE NOT. The `movem` pair is the 1987
 * compiler's calling convention and nothing else — C's own callee-saved rule is the same promise, and
 * `rom_bench`'s callee-saved check is what holds the target build to it. The MASK is a behaviour: the
 * select latch and the data port are two instructions apart, and TOS's own 200 Hz timer path writes
 * `$ff8800`, so an interrupt landing between this routine's select and its read leaves the caller
 * reading whichever register the handler selected. It goes through `ipl.h`'s door, which is a no-op
 * off target (the oracle enters at IPL 7, takes no interrupts and reports no SR) and the real
 * `move.w sr,d0` / `ori.w #$700,sr` pair on the machine.
 *
 * SO THE DIFFERENTIAL CANNOT SEE THE BRACKET AND TIER 3 CAN. Delete the two calls and every Tier 1
 * case stays green; what moves is the 68000 cycle count, which is why `bench/tier3.py` pins this
 * routine's measured ratio with that as the reason (`tools/recreate_kit/include/ipl.h`).
 *
 * The remaining effects are the chip accesses below. They are off-image on both sides, which is
 * exactly what psg.h's ordered ledger exists to compare (TRAP_MODEL.md, Phase 6).
 */
#include <stdint.h>

#include "ipl.h"
#include "psg.h"
#include "addrs.h"

/* NO IMAGE ARGUMENT, unlike every core that touches memory: this one's whole effect is the chip,
 * which is not in the image. What the differential compares here is psg.h's ordered access ledger
 * and the register file behind it, plus the byte returned. */
uint8_t xbios_giaccess(uint16_t data, uint16_t reg_and_flag)
{
    unsigned reg = reg_and_flag & GIACCESS_REGISTER_MASK;
    os_ipl_t mask;
    uint8_t value;

    /* The bracket spans the SELECT and the DATA access together, exactly where the ROM's own
     * `ori.w #$700,sr` .. `move.w (sp)+,sr` spans them — a mask around each half separately would
     * leave the window this exists to close wide open between them. */
    mask = os_ipl_raise();
    if (reg_and_flag & GIACCESS_WRITE_FLAG)
        psg_port_write(reg, (uint8_t)data);
    value = psg_port_read(reg);
    os_ipl_restore(mask);
    return value;
}
