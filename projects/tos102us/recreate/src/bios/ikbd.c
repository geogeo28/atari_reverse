/* The ACIA handler — vector $118, $fc29ce. The MFP channel the IKBD's 6850 and the MIDI 6850 share,
 * which is why the handler is a LOOP over two service routines rather than one routine:
 *
 *      movem.l d0-d3/a0-a3/a5,-(sp)
 *      lea     0,a5
 *  .again:
 *      movea.l KBDVECS+midisys(a5),a2
 *      jsr     (a2)                    ; the MIDI 6850's service routine
 *      movea.l KBDVECS+ikbdsys(a5),a2
 *      jsr     (a2)                    ; ...and the IKBD's
 *      btst    #4,$fffa01
 *      beq.s   .again                  ; the line is ACTIVE LOW: still asserted, so round again
 *      bclr    #6,$fffa11
 *      movem.l (sp)+,d0-d3/a0-a3/a5
 *      rte
 *
 * ONE INTERRUPT LINE, TWO CHIPS. The MFP gives channel 6 to both 6850s, so an interrupt says only
 * that one of them wants service — the handler asks each in turn and then asks the MFP whether
 * anybody still does. GPIP bit 4 is LOW while either chip is asserting, so `beq` is the LOOP and not
 * the exit, and a byte that arrives while the first pass is running is serviced by the second.
 *
 * THE TWO ROUTINES ARE RAM. `midisys` and `ikbdsys` are the last two longwords of KBDVECS — the
 * table `Kbdvbase` hands a caller for exactly this purpose — and the vectors are RE-READ on every
 * pass, so a routine that replaces its own is answered from the next one. They are staged
 * (`include/staged_call.h`), which is also what makes the handler itself provable: the ROM's own
 * service routines at $fc29fc and $fc2a0c read the 6850s' data ports, and those are not
 * reconstructed here.
 *
 * WHAT IS NOT RECONSTRUCTED, and why it is not a halt: the two service routines are not ARMS of this
 * function, they are separate ROM routines reached through a vector — so this file has nothing to
 * halt on. `test_bios_ikbd.py` pins that the captured machine really has $fc29fc and $fc2a0c in
 * those slots, so what is deferred stays checkable: the packet parser (mouse, joystick, clock and
 * status packets into their buffers), the scancode translation through the `Keytbl` tables into the
 * console IOREC, and MIDI's own ring. All of it needs something this model does not have — a
 * declared SEQUENCE of bytes out of $fffc02, where one per-run constant describes exactly one read
 * (os.h, `OS_HW_ACIA_DATA`).
 *
 * THE LOOP RUNS ONCE PER CASE, for the same reason: GPIP bit 4 is a per-run constant, so a case
 * declares it HIGH and the handler makes one pass. Declared low it would spin on both builds — a
 * case that never terminates rather than a case that lies — because nothing in either core can
 * change what the declaration answers. That half is DRIVEN rather than described, on the ORIGINAL
 * alone (`test_bios_ikbd.py::test_a_line_declared_still_asserted_spins_until_the_oracle_s_cap`):
 * the oracle has an instruction cap to refuse the run with and this C has none.
 */
#include <stdint.h>

#include "machine.h"
#include "hw.h"
#include "addrs.h"
#include "mfp.h"
#include "staged_call.h"

void isr_acia(uint8_t *image)
{
    do {
        call_vector(image, be32(image + KBDVECS + KBDVECS_MIDISYS));
        call_vector(image, be32(image + KBDVECS + KBDVECS_IKBDSYS));
    } while ((hw_read8(MFP_GPIP) & (1u << MFP_GPIP_ACIA_BIT)) == 0);
    mfp_clear_bit(MFP_ISRB, MFP_ISRB_ACIA_BIT);
}
