/* sched.h — a busy-wait as a 68000 build makes it: the loop itself, with the interrupt real.
 *
 * It shadows `tools/recreate_kit/include/sched.h`, whose header states this file's contract: "ON
 * TARGET this file IS EXCLUDED FROM THE BUILD, exactly like src/hw.c and src/psg.c: a build for the
 * real machine spins on the address itself, because the interrupt really does write it, and
 * supplies its own `sched_wait8`/`sched_poll16`/`sched_poll32` that loop without a cap."
 * The seam is the INCLUDE PATH, as it is for `psg.h`, `hw.h` and `ipl.h` in this directory; the
 * differential build never sees this file, so the host `.so` keeps the scheduled-write model, the
 * per-site poll count and the cap that `harness.differential` compares against the oracle's.
 *
 * OUTRIGHT rather than through `#include_next`, for zynaps' reason: the kit declares these `extern`
 * and C forbids redeclaring one `static`.
 *
 * THE TWO THINGS THE MODEL ADDS ARE EXACTLY THE TWO THINGS A MACHINE DOES NOT NEED. The per-site
 * POLL COUNT is the candidate's substitute for a program counter, so that an off-target run can be
 * compared with the oracle's arrivals; here the processor has one. The CAP is what stops a case
 * whose schedule never comes due from hanging the suite; here there is no schedule — the vertical
 * blank, or the ACIA, or the timer really does store the byte — and a cap would end the wait EARLY,
 * which is a different program from the one the ROM ships. So `site_pc` is ignored and the return
 * is always "go round again"; the caller's own compare is what ends the loop, exactly as the
 * original's `beq` is.
 *
 * ONLY THE LONGWORD POLL, and the omission is the point, as it is in `hw.h` next door: `xbios_vsync`
 * is the one core here that waits, and a core that acquires a byte or word wait fails at LINK naming
 * the symbol rather than getting a definition nobody weighed against the instruction it stands for.
 */
#ifndef TOS102US_SHIM_SCHED_H
#define TOS102US_SHIM_SCHED_H

#include <stdint.h>

/* One iteration of a longword busy-wait: read `addr` and tell the caller to go round again.
 *
 * VOLATILE, and that is the whole of what this file has to get right: the value is changed by an
 * interrupt handler and by nothing in the caller's own instruction stream, so a compiler that hoists
 * the load out of the loop — which it may, and at -O2 will — leaves a program that spins on a
 * register forever. It is the same hazard `ipl.h`'s "memory" clobber closes one level up.
 */
static inline int sched_poll32(uint8_t *image, uint32_t addr, uint32_t site_pc, uint32_t *seen)
{
    (void)site_pc;              /* the machine has a program counter; the model needed a substitute */
    *seen = *(volatile uint32_t *)(image + addr);
    return 1;                   /* no cap: the original's own loop has none */
}

#endif /* TOS102US_SHIM_SCHED_H */
