/* XBIOS Vsync (function $25) — $fc07d0.
 *
 * Wait for the next vertical blank. The whole routine is a spin on `_frclock`, the longword the VBL
 * handler at $fc06de opens by incrementing:
 *
 *      move.w  sr,-(sp)
 *      andi.w  #$f8ff,sr           ; $fc07d2: IPL -> 0, or the blank this waits for is never taken
 *      move.l  SYSVAR_FRCLOCK,d0   ; $fc07d6: ...and the sample comes AFTER it. See below.
 *   .spin:
 *      cmp.l   SYSVAR_FRCLOCK,d0   ; VSYNC_WAIT_SITE
 *      beq.s   .spin
 *      move.w  (sp)+,sr
 *      rts
 *
 * IT WAITS FOR A CHANGE AND NOT FOR AN INCREMENT. The test is `cmp`/`beq`, so anything that makes
 * the longword differ from the sample releases it — a counter someone reset, or one that went
 * backwards, ends the wait exactly as the handler's `addq.l #1` does. The distinction is reachable
 * (a program may clear `_frclock`) and the battery drives it.
 *
 * THE UNMASK COMES BEFORE THE SAMPLE, AND THAT ORDER IS THE WAIT'S MEANING. $fc07d2 clears the mask
 * and only then does $fc07d6 read `_frclock`. A caller that enters at a raised IPL can have a blank
 * ALREADY PENDING — it is the mask that is holding the level-4 autovector off — and the unmask is
 * what lets the handler take it, so the value sampled is the one that blank has already been counted
 * into. Sampling first and unmasking after would let that same pending blank, the one the caller had
 * ALREADY missed, release the wait immediately, and `Vsync` would come back without waiting for a
 * frame. Off target neither order is visible (`ipl.h` is a no-op there and no interrupt fires, so
 * both leave the same image and the same D0), which is why the order is taken from the ROM here and
 * held by nothing else.
 *
 * THE UNMASK IS THE ROUTINE'S TERMINATION, NOT ITS MANNERS. Nothing in this body writes `_frclock`;
 * the level-4 autovector does, so at IPL 7 — inside another handler, or under a caller's own
 * `Giaccess`-style bracket — the loop is infinite. `ipl.h` is that door: a no-op off target (the
 * oracle enters at IPL 7, takes no interrupts and reports no SR) and the real `move.w sr,d0` /
 * `andi.w #$f8ff,sr` on the machine, which is why the Tier 1 differential cannot see it.
 *
 * SO THE WAIT IS DRIVEN BY THE SCHEDULED-WRITE MODEL (`sched.h`; TRAP_MODEL.md, Phase 8). Nothing
 * changes memory while an `emu.run` is in flight, so under the oracle this loop is infinite on BOTH
 * sides and the routine is not runnable at all until a case says what the interrupt did: an external
 * agent stores the new `_frclock` at the spin's own PC, on both shores, and the candidate polls once
 * per iteration where the ROM re-executes its `cmp.l`. The comparison of the oracle's ARRIVALS at
 * that PC against this core's POLLS is what stops a reconstruction that spun a different number of
 * times from passing — the store lands on both sides from the same list, so the final image cannot
 * say. That is also why the poll is the LONGWORD wrapper rather than four byte polls: several polls
 * per arrival is the aliasing mutant Phase 8 documents.
 *
 * WHAT IT LEAVES IN D0 is the `_frclock` it sampled BEFORE the wait — `move.l SYSVAR_FRCLOCK,d0` is
 * the last thing to touch the register — so the core returns it. Callers are documented to ignore
 * the result and this is not a documented return value; it is what the differential compares, and a
 * `void` core would agree with one that had left anything at all there.
 */
#include <stdint.h>

#include "ipl.h"
#include "machine.h"
#include "sched.h"
#include "addrs.h"

uint32_t xbios_vsync(uint8_t *image)
{
    /* The mask goes down FIRST — a pending blank is counted before the sample is taken, not after
     * it; the header says what the other order would do. */
    os_ipl_t mask = os_ipl_unmask();
    uint32_t entry_clock = be32(image + SYSVAR_FRCLOCK);
    uint32_t now;

    /* That sample is an ORDINARY read and not a poll: the ROM makes it once, before the loop, and a
     * poll there would spend an arrival the original never has (sched.h, "WHAT IT IS NOT"). */
    while (sched_poll32(image, SYSVAR_FRCLOCK, VSYNC_WAIT_SITE, &now))
        if (now != entry_clock) {
            os_ipl_restore(mask);
            return entry_clock;
        }
    /* The cap. `sched_poll32` has already tallied the refusal, so the case is void whatever happens
     * next; put the caller's mask back and return rather than carrying on as though a blank came. */
    os_ipl_restore(mask);
    return entry_clock;
}
