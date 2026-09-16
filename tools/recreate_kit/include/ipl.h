/* ipl.h — the 68000's INTERRUPT MASK, as a reconstruction raises and restores it.
 *
 * A routine that drives a two-part device — select a register, then access the data port — masks
 * interrupts across the pair, because a handler that ran in between would leave the latch selecting
 * something else. TOS's XBIOS `Giaccess` is the worked case ($fc2ea4: `move.w sr,-(sp)`,
 * `ori.w #$700,sr`, the two accesses, `move.w (sp)+,sr`), and so is its own 200 Hz path, which
 * writes $ff8800 from the timer interrupt: without the bracket that interrupt can land between a
 * caller's select and its read, and the caller reads the timer's register.
 *
 * OFF TARGET THIS IS A NO-OP, AND THAT IS HONEST RATHER THAN CONVENIENT. The oracle enters every run
 * at IPL 7 already (TRAP_MODEL.md, "The entry state every run begins from") and takes no interrupts,
 * and it reports no SR at all — `emu.REPORTED_REGS` is d0..d7 and a0..a6 — so there is nothing on
 * this side for a mask to change and nothing that could observe it if there were. What that means
 * for the reconstruction is stated plainly, because it is a hole and not a feature:
 *
 *   **THE TIER 1 DIFFERENTIAL CANNOT PIN THIS DOOR.** Delete the two calls from a core and every
 *   differential stays green. What DOES see them is TIER 3: the pair costs real 68000 cycles, so a
 *   vanished bracket moves the core's measured ratio and its bench row reddens against the pinned
 *   one (`rom_bench.py`; the project's `bench/tier3.py` carries the pin with the reason).
 *
 * ON TARGET the build supplies both as the real instructions, exactly as it supplies `psg.h`'s ports
 * and `hw.h`'s read doors: an `atari/shim_include/ipl.h` that shadows this file on the include path.
 * The kit cannot write that half — `move.w <ea>,sr` is privileged, so whether it is legal at all is
 * a fact about where the project's code runs (TOS's is entered through a trap, in supervisor mode),
 * and that is the project's claim to make.
 */
#ifndef RECREATE_KIT_IPL_H
#define RECREATE_KIT_IPL_H

#include <stdint.h>

/* The saved mask `os_ipl_raise` hands back and `os_ipl_restore` takes. A whole SR word rather than
 * the three mask bits: the 68000's `move.w (sp)+,sr` restores the register, not the field, and a
 * target half that saved only the mask would silently drop the caller's condition codes. */
typedef uint16_t os_ipl_t;

/* Mask every interrupt, returning what the mask was — `move.w sr,d0` / `ori.w #$700,sr`. */
static inline os_ipl_t os_ipl_raise(void)
{
    return 0;
}

/* ...AND THE OTHER DIRECTION, which a routine that WAITS for an interrupt needs: clear the mask so
 * that every level is taken — `move.w sr,d0` / `andi.w #$f8ff,sr` — returning what the SR was, for
 * the same `os_ipl_restore` to put back.
 *
 * It is not `os_ipl_raise`'s opposite by accident of symmetry. TOS's XBIOS `Vsync` ($fc07d0) opens
 * with exactly that pair and then spins on `_frclock`, which only the vertical-blank handler
 * increments: called at a raised IPL — from inside another handler, or from a routine that had
 * bracketed something — the wait would never end, so the unmask is the routine's TERMINATION rather
 * than a nicety. Off target it is the same no-op the raise is, and for the same reason (the oracle
 * enters at IPL 7, takes no interrupts and reports no SR), so the note above applies unchanged:
 * deleting it leaves every Tier 1 differential green and moves the Tier 3 cycle count. */
static inline os_ipl_t os_ipl_unmask(void)
{
    return 0;
}

/* ...and put it back: `move.w d0,sr`. `saved` must be what `os_ipl_raise` or `os_ipl_unmask`
 * returned. */
static inline void os_ipl_restore(os_ipl_t saved)
{
    (void)saved;
}

#endif /* RECREATE_KIT_IPL_H */
