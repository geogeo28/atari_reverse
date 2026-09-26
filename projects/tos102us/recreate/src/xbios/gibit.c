/* XBIOS Ongibit ($1e) and Offgibit ($1d) — $fc2edc and $fc2f02.
 *
 * The read-modify-write of the YM2149's PORT A, which is where an ST keeps everything that is
 * neither sound nor an ACIA: the two drive selects, the side select, the printer strobe and the
 * RS232 handshake lines. Setting or clearing one of them means preserving the other seven, so both
 * routines are a read, one boolean operation, and a write back.
 *
 *      moveq   #0,d2
 *      move.w  4(sp),d2            ; the mask, of which only the LOW BYTE is ever used
 *      movem.l d0-d2,-(sp)
 *      move.w  sr,-(sp)
 *      ori.w   #$700,sr            ; ...the OUTER bracket; see below
 *      moveq   #PSG_PORT_A,d1
 *      move.l  d2,-(sp)
 *      bsr.s   $fc2eac             ; Giaccess's internal entry: d0 = data, d1 = register
 *      move.l  (sp)+,d2
 *      or.b    d2,d0               ; ...`and.b d2,d0` in Offgibit, and that is the whole difference
 *      moveq   #PSG_PORT_A|GIACCESS_WRITE_FLAG,d1
 *      bsr.s   $fc2eac
 *      move.w  (sp)+,sr
 *      movem.l (sp)+,d0-d2
 *      rts
 *
 * THEY COMPOSE OVER `Giaccess` RATHER THAN OVER THE PORTS, and so does this reconstruction: the
 * `bsr.s $fc2eac` is an entry two instructions INSIDE `xbios_giaccess` ($fc2ea4), past the two
 * `move.w`s that fetch its arguments off the stack, so the ROM is calling that routine with its
 * arguments already in D0/D1 rather than reimplementing it. Re-implementing the select-and-access
 * pair here would be a second copy of the one thing the chip's ordered access ledger is comparing.
 *
 * THE OUTER INTERRUPT BRACKET IS A SECOND ONE, and it is not redundant. `Giaccess` masks across its
 * own select-and-access pair; this masks across BOTH CALLS, which is what makes the read-modify-write
 * atomic — without it the 200 Hz sound driver ($fc312a, which writes $ff8800 directly) can land
 * between the read and the write back, and its register selection, or another caller's `Ongibit`,
 * is lost. `ipl.h` is the door and the masks nest exactly as the ROM's do: each `os_ipl_raise`
 * returns the whole SR its own `restore` puts back. As everywhere else, the bracket is invisible to
 * the Tier 1 differential and shows only in the Tier 3 cycle count.
 *
 * ONLY THE LOW BYTE OF THE ARGUMENT REACHES THE CHIP. `moveq #0,d2` then `move.w 4(sp),d2` leaves a
 * zero-extended word, and `or.b`/`and.b` then use one byte of it — so `Ongibit($ff01)` sets bit 0
 * and `Offgibit($0000)` clears the port to zero. The high byte is not masked away, it is simply
 * never read, which is the same answer by a different route and the reason the battery sweeps words
 * rather than bytes.
 *
 * NEITHER SETS A RESULT, AND THAT IS A CLAIM ABOUT D0 RATHER THAN AN ABSENCE OF ONE. The
 * `movem.l (sp)+,d0-d2` puts the caller's D0 back over the byte the second `Giaccess` read, so what
 * a caller gets back is the register it came in with — unlike `Giaccess` itself, whose whole point
 * is the byte it hands back. A `void` core would say nothing about that half of the machine and
 * would agree with a reconstruction that had left the port byte in D0, so both take the entering D0
 * as an argument and return it, as `Setprt` and `Cursconf` do for the routines that write D0's low
 * word (`kbrate.c` states the shape in full).
 *
 * THE ALTERNATE ENTRY AT $fc2ed8 is not reconstructed and needs none: `moveq #-17,d2 / bra.s
 * $fc2f08` jumps into Offgibit's body BELOW its argument fetch, with the mask $ef already in D2 —
 * TOS's own "clear port A bit 4" for an internal caller. It is the same body with a constant, not a
 * third routine.
 */
#include <stdint.h>

#include "ipl.h"
#include "addrs.h"
#include "xbios/xbios.h"

/* The data word `Giaccess` is given for the READ: the ROM leaves whatever the caller had in D0
 * there, and the routine never looks at it — bit 7 of the register argument is clear, so the write
 * path is not taken. Zero, named, so the call site does not read as a value that matters. */
#define UNUSED_DATA 0

/* ...and the register argument the WRITE back takes, which is the same register with the direction
 * bit set. `Giaccess` reads the register back after writing it either way, so both calls leave an
 * entry in the chip's ordered ledger. */
#define PORT_A_WRITE (GIACCESS_WRITE_FLAG | PSG_PORT_A)

/* The `(uint8_t)` on the argument is the ROM's OPERAND SIZE and not a safety cast: `or.b d2,d0`
 * reads one byte of a register holding a zero-extended word. `Giaccess` narrows what it is given to
 * a byte anyway, so dropping it would compute the same value — and would stop saying which half of
 * the argument the ROM looks at, which is the one thing about these two that is easy to get wrong.
 * (A mutant widening it is EQUIVALENT for that reason; one taking `bits >> 8` is not, and is what
 * the batteries kill.) */
uint32_t xbios_ongibit(uint32_t entry_d0, uint16_t bits)
{
    os_ipl_t mask = os_ipl_raise();
    uint8_t port_a = xbios_giaccess(UNUSED_DATA, PSG_PORT_A);

    xbios_giaccess(port_a | (uint8_t)bits, PORT_A_WRITE);
    os_ipl_restore(mask);
    return entry_d0;                /* `movem.l (sp)+,d0-d2` — the caller's own register, whole */
}

uint32_t xbios_offgibit(uint32_t entry_d0, uint16_t bits)
{
    os_ipl_t mask = os_ipl_raise();
    uint8_t port_a = xbios_giaccess(UNUSED_DATA, PSG_PORT_A);

    xbios_giaccess(port_a & (uint8_t)bits, PORT_A_WRITE);
    os_ipl_restore(mask);
    return entry_d0;
}
