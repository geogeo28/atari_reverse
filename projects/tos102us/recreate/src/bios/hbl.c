/* The HORIZONTAL BLANK handler — vector $68, $fc06c8. Seven instructions, and all of them are
 * about the frame it is going to return through:
 *
 *      move.w  d0,-(sp)            ; ...so 2(sp) is now the frame's SR word
 *      move.w  2(sp),d0
 *      and.w   #$0700,d0           ; the interrupt MASK the machine was running at
 *      bne.s   .out
 *      ori.w   #$0300,2(sp)        ; it was 0 -> resume at level 3 instead
 * .out: move.w  (sp)+,d0
 *      rte
 *
 * TOS installs it and then leaves the horizontal blank DISABLED, so on an ordinary machine it never
 * runs at all. What it is for is the machine where something enabled it: a level-2 interrupt taken
 * while the processor was at IPL 0 would be taken again on the very next scan line, before the
 * interrupted code made any progress, so the handler RAISES THE FRAME'S OWN MASK — the code it
 * returns to resumes at level 3, above the horizontal blank, and gets to run. A frame already at a
 * non-zero level is left exactly as it is: the routine floors the mask, it does not set it.
 *
 * THE FRAME IS THE ARGUMENT, and the signature says so. A C function has no `2(sp)` to reach — the
 * exception frame is the MACHINE's, built by its own exception processing — so the address of it is
 * what the reconstruction takes, and `test/isr.py` is what stages one. The entry glue either side
 * of the body (the `move.w d0,-(sp)` that makes room and the `rte` that consumes the frame) is the
 * machine's too, and stays the ORIGINAL's alone here exactly as Supexec's `jmp` does: the shipped
 * ROM would reach this body through two instructions of its own.
 */
#include <stdint.h>

#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif

#include "machine.h"
#include "addrs.h"

void isr_hbl(uint8_t *image, uint32_t frame)
{
    uint16_t saved_sr;

#ifdef RECREATE_HOST_DIFFERENTIAL
    /* HOST-ONLY, the way the kit prescribes: on the machine the frame is wherever the 68000's own
     * exception processing left it, and there is nothing to check; off target it is an address a
     * case chose, and one outside RAM would index past the image rather than round the original's
     * address space. */
    assert(frame <= ST_RAM_BYTES - EXCEPTION_FRAME_BYTES);
#endif
    saved_sr = be16(image + frame + EXCEPTION_FRAME_SR);

    if ((saved_sr & SR_IPL_MASK) == 0)
        wr16(image + frame + EXCEPTION_FRAME_SR, (uint16_t)(saved_sr | HBL_IPL_FLOOR));
}
