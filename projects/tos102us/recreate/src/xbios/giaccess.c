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
 * THE INTERRUPT MASK AND THE REGISTER SAVES ARE NOT MODELLED, and nothing is lost by that: the run
 * takes no interrupts (the oracle enters every run at IPL 7 — TRAP_MODEL.md, "The entry state every
 * run begins from") and the saved registers are restored before the `rts`, so the only effects that
 * leave this routine are the chip accesses below. They are off-image on both sides, which is
 * exactly what psg.h's ordered ledger exists to compare (TRAP_MODEL.md, Phase 6).
 */
#include <stdint.h>

#include "psg.h"
#include "addrs.h"

/* NO IMAGE ARGUMENT, unlike every core that touches memory: this one's whole effect is the chip,
 * which is not in the image. What the differential compares here is psg.h's ordered access ledger
 * and the register file behind it, plus the byte returned. */
uint8_t xbios_giaccess(uint16_t data, uint16_t reg_and_flag)
{
    unsigned reg = reg_and_flag & GIACCESS_REGISTER_MASK;

    if (reg_and_flag & GIACCESS_WRITE_FLAG)
        psg_port_write(reg, (uint8_t)data);
    return psg_port_read(reg);
}
