/* XBIOS Rsconf ($0f) — $fc290e.
 *
 * The RS232 port's whole configuration in one call: the baud rate (which is MFP timer D), the
 * handshake mode, and the four USART registers, each argument optional and each spelt the same way —
 * a NEGATIVE word means "leave this one alone".
 *
 *      ori.w   #$700,sr              ; ...and never restored: see below
 *      lea     $c54,a0               ; the RS232 input IOREC
 *      lea     $fffffa01,a1          ; the MFP
 *      movep.l 40(a1),d7             ; UCR, RSR, TSR, UDR -> one longword, the RESULT
 *      tst.w   6(sp) / bmi .baud     ; flowctl
 *        move.b  7(sp),32(a0)        ; store it in the IOREC...
 *        move.b  32(a0),d0           ; ...and read it straight back
 *        beq.s   .baud               ; 0 stands
 *        andi.b  #$fd,d0
 *        beq.s   .baud               ; 2 stands
 *        move.b  #1,32(a0)           ; ...and everything else becomes 1
 *  .baud: tst.w 4(sp) / bmi .ucr
 *        moveq   #0,d0
 *        move.b  d0,42(a1) / move.b d0,44(a1)      ; RSR = TSR = 0 across the change
 *        move.w  4(sp),d1
 *        move.b  $fc29ae(d1.w),d0    ; timer D's control byte for this rate
 *        move.b  $fc29be(d1.w),d2    ; ...and its divider
 *        move.l  d0,d1 / moveq #3,d0 / bsr.w $fc25b0
 *        moveq   #1,d0
 *        move.b  d0,42(a1) / move.b d0,44(a1)      ; ...and on again
 *  .ucr: tst.w 8(sp)  / bmi + / move.b  9(sp),40(a1)
 *        tst.w 10(sp) / bmi + / move.b 11(sp),42(a1)
 *        tst.w 12(sp) / bmi + / move.b 13(sp),44(a1)
 *        tst.w 14(sp) / bmi + / move.b 15(sp),38(a1)
 *        move.l  d7,d0
 *        rts
 *
 * THE RESULT IS READ FIRST, AND IT IS FOUR SEPARATE BYTES. `movep.l` is the 68000's instruction for
 * a peripheral on every other byte of the bus, which is exactly how the 68901 is wired: one longword
 * in D7 out of `$fffa29`, `$fffa2b`, `$fffa2d` and `$fffa2f`, high byte first. So the previous
 * configuration a caller gets back is UCR:RSR:TSR:UDR — and the low byte of it is the USART's DATA
 * register, which is a byte of received traffic rather than a setting. That is the ROM's answer, not
 * a slip, and a case pins it by declaring four distinct bytes and asserting where each one lands.
 *
 * THE MASK IS RAISED AND NEVER LOWERED, which looks like a leak and is not: every XBIOS routine is
 * entered through the `trap #14` dispatcher and left through its `rte`, which restores the whole SR
 * from the exception frame. `ipl.h`'s door pairs a raise with a restore because most callers want
 * the pair; this one deliberately discards what it saved, and says so at the call.
 *
 * THE HANDSHAKE BYTE IS STORED, READ BACK AND SOMETIMES REWRITTEN, and the read-back is of RAM
 * rather than of a register, so it is an ordinary image access — but it is a real read: the ROM
 * decides what to do from the byte it just stored, not from the argument. What the arithmetic comes
 * to is that 0 and 2 stand and every other value becomes 1 (`$fd` clears bit 1, so only a byte whose
 * every other bit is clear survives it), which means mode 3 — "both kinds of handshake", as the
 * documentation has it — is quietly demoted to XON/XOFF by this ROM.
 *
 * THE BAUD INDEX IS UNBOUNDED, and doubly so: `move.b TABLE(d1.w),d0` is `m68k_idioms.h`'s SIGNED
 * word index, so rate $8000 reads $8000 bytes BELOW the table and rate 16 reads the byte after its
 * last — the two tables are 16 bytes each and adjacent, so rate 16 reads the first byte of the other
 * one. Reproduced by construction: both tables are read out of the mapped ROM.
 *
 * THE BAUD ARM IS THE SHARED TIMER PROGRAMMER, for timer D. `bsr.w $fc25b0` writes the timer's data
 * register and READS IT BACK until the 68901 agrees, and re-reads the control register to OR the
 * rate's control bits in — two read-backs a declaration describing the machine on ENTRY could not
 * serve, which is why this arm used to halt. A case declares both registers WRITE-THROUGH now
 * (TRAP_MODEL.md, Phase 15), which is true of them because the programmer's own clears stop the
 * timer first; `src/xbios/xbtimer.c`'s header carries that argument.
 *
 * WHAT SURROUNDS THE CALL IS THIS ROUTINE'S OWN: the receiver and transmitter are turned OFF across
 * the rate change and back ON after it — four byte stores, and the pair that brackets the call is
 * what says a caller's RSR/TSR arguments below are applied AFTER the port comes back up.
 */
#include <stdint.h>

#include "hw.h"
#include "ipl.h"
#include "m68k_idioms.h"
#include "machine.h"
#include "mfp.h"
#include "addrs.h"

/* `tst.w 8(sp) / bmi / move.b 9(sp),reg` — one optional USART register, stored as its LOW byte. */
static void rsconf_store(uint32_t reg, uint16_t argument)
{
    if (!keeps_current_value_word(argument))
        hw_write8(reg, (uint8_t)argument);
}

/* THE SIX ARGUMENTS ARE A BLOCK IN MEMORY, not six C parameters, and it is the ROM's own shape: the
 * routine reads `4(sp)` through `14(sp)` out of its caller's frame and never takes a register. The
 * C says the same — `arguments` is where that frame is — which is also the only form Tier 3 can
 * measure: seven C parameters reach thirty-two bytes above the stack pointer, past the twenty-eight
 * the harness reserves for a call's arguments (`rom_bench._vet_stack_args_fit`). */
static uint16_t rsconf_argument(const uint8_t *image, uint32_t arguments, uint32_t field)
{
    return be16(image + addr_add(arguments, field));
}

uint32_t xbios_rsconf(uint8_t *image, uint32_t arguments)
{
    uint32_t previous;
    uint16_t flow, baud;
    uint8_t mode;

    /* The saved SR is DISCARDED: the dispatcher's `rte` is what puts the mask back (see above). */
    (void)os_ipl_raise();

    /* `movep.l 40(a1),d7`, as the four byte reads it is — in the ROM's order, which the ordered I/O
     * read ledger compares, so they are written as statements rather than as one expression whose
     * operand order C leaves unspecified. */
    previous = (uint32_t)io_read8(MFP_UCR) << 24;
    previous |= (uint32_t)io_read8(MFP_RSR) << 16;
    previous |= (uint32_t)io_read8(MFP_TSR) << 8;
    previous |= io_read8(MFP_UDR);

    /* EACH ARGUMENT IS READ WHERE THE ROM READS IT, not hoisted to the top: the block is the
     * CALLER's memory and nothing bounds it, so a caller whose frame lies over `$c74` has the
     * handshake store below change the words this routine has not read yet. That is `Getmpb`'s
     * lesson next door, and it is the one thing a hoist here could get wrong. */
    flow = rsconf_argument(image, arguments, RSCONF_ARG_FLOW);
    if (!keeps_current_value_word(flow)) {
        image[RSCONF_FLOW_CONTROL] = (uint8_t)flow;
        mode = image[RSCONF_FLOW_CONTROL];          /* the ROM reads its own store back */
        if (mode != RSCONF_FLOW_NONE && (mode & RSCONF_FLOW_KEEP_MASK) != 0)
            image[RSCONF_FLOW_CONTROL] = RSCONF_FLOW_XON_XOFF;
    }

    baud = rsconf_argument(image, arguments, RSCONF_ARG_BAUD);
    if (!keeps_current_value_word(baud)) {
        uint32_t index = word_index(baud, 1);

        hw_write8(MFP_RSR, RSCONF_USART_OFF);       /* receiver and transmitter off across the... */
        hw_write8(MFP_TSR, RSCONF_USART_OFF);
        mfp_timer_program(image, MFP_TIMER_D,       /* ...baud-rate change, which IS timer D */
                          image[addr_add(RSCONF_BAUD_CONTROL_TABLE, index)],
                          image[addr_add(RSCONF_BAUD_DATA_TABLE, index)]);
        hw_write8(MFP_RSR, RSCONF_USART_ON);
        hw_write8(MFP_TSR, RSCONF_USART_ON);
    }

    rsconf_store(MFP_UCR, rsconf_argument(image, arguments, RSCONF_ARG_UCR));
    rsconf_store(MFP_RSR, rsconf_argument(image, arguments, RSCONF_ARG_RSR));
    rsconf_store(MFP_TSR, rsconf_argument(image, arguments, RSCONF_ARG_TSR));
    rsconf_store(MFP_SCR, rsconf_argument(image, arguments, RSCONF_ARG_SCR));
    return previous;
}
