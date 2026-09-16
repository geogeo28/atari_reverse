/* ipl.h — the interrupt mask as a 68000 build makes it: the ROM's own two instruction pairs.
 *
 * It shadows `tools/recreate_kit/include/ipl.h`, whose header states this file's contract and the
 * hole it fills: off target the door is a no-op, because the oracle enters at IPL 7, takes no
 * interrupts and reports no SR — so the Tier 1 differential cannot see whether a core masks at all.
 * On target the mask is load-bearing, and here it is the instructions.
 *
 * The seam is the INCLUDE PATH, as it is for `psg.h` and `hw.h` in this directory; the differential
 * build never sees it. OUTRIGHT rather than through `#include_next`, for zynaps' reason.
 *
 * SUPERVISOR-ONLY, AND THAT IS WHY THE KIT CANNOT WRITE THIS HALF. `ori.w #$700,sr` and
 * `move.w d0,sr` are privileged on every 68000; `move.w sr,d0` is not (it became privileged on the
 * 68010). Every routine in this reconstruction is entered through a TRAP — the BIOS/XBIOS dispatcher
 * at `$fc07fc` — so the processor is already in supervisor mode when one runs, on the machine and
 * under the bench alike (`emu.run_bench` enters from a reset, which is supervisor). A core that
 * called this from user mode would take a privilege violation, which is the same thing the ROM's own
 * `Giaccess` would do.
 *
 * WHAT IT COSTS, and why that is the point: the pair is real 68000 cycles, so Tier 3's numerator
 * MOVES when it is there and moves back when it is not. That is the only surface this door has —
 * `bench/tier3.py` pins the rows over `xbios_giaccess` for exactly that reason.
 */
#ifndef TOS102US_SHIM_IPL_H
#define TOS102US_SHIM_IPL_H

#include <stdint.h>

typedef uint16_t os_ipl_t;

/* `move.w sr,<d>` then `ori.w #$700,sr` — the ROM's own pair at `$fc2ea8`, in its order.
 *
 * "memory" in the clobber list, on both halves: the mask is a BARRIER as well as an instruction, and
 * its whole purpose is that the accesses the caller brackets with it stay between the two. Without
 * it GCC is free to hoist a port write above the `ori` or sink one below the restore, which would
 * leave the bracket in the listing and the race in the program. */
static inline os_ipl_t os_ipl_raise(void)
{
    os_ipl_t saved;

    __asm__ volatile ("move.w %%sr,%0\n\t"
                      "ori.w #0x0700,%%sr"
                      : "=d" (saved) : : "cc", "memory");
    return saved;
}

/* `move.w %%sr,<d>` then `andi.w #$f8ff,sr` — the ROM's own pair at `$fc07d0`, in its order: the
 * mask goes to 0 so that the vertical blank `Vsync` is waiting for can actually be taken. The
 * "memory" clobber is the raise's, for the raise's reason.
 *
 * PRIVILEGED for the same half of the pair: `andi.w #imm,sr` is, `move.w sr,<d>` is not. Every
 * caller reaches it through the trap dispatcher, so the processor is already in supervisor mode. */
static inline os_ipl_t os_ipl_unmask(void)
{
    os_ipl_t saved;

    __asm__ volatile ("move.w %%sr,%0\n\t"
                      "andi.w #0xf8ff,%%sr"
                      : "=d" (saved) : : "cc", "memory");
    return saved;
}

/* ...and `move.w <d>,sr`, which restores the whole register either pair above saved. */
static inline void os_ipl_restore(os_ipl_t saved)
{
    __asm__ volatile ("move.w %0,%%sr" : : "d" (saved) : "cc", "memory");
}

#endif /* TOS102US_SHIM_IPL_H */
