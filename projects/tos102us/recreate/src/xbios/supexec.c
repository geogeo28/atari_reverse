/* XBIOS Supexec (function 38) — $fc097e.
 *
 *      movea.l 4(sp),a0
 *      jmp     (a0)
 *
 * "Run this in supervisor mode" is two instructions, because by the time the trap dispatcher has
 * reached here the processor already IS in supervisor mode — the trap put it there. So Supexec adds
 * nothing at all: no register is saved, no frame is built, and it is a `jmp` rather than a `jsr`, so
 * the routine the caller named returns straight past Supexec to the caller and its D0 IS the XBIOS
 * call's result.
 *
 * THE ARGUMENT IS AN ADDRESS, not a function, and the signature says so. That is what lets the two
 * builds be the same program: each transfers control to the 68000 code at `routine_address`, and
 * they differ only in whether there is a 68000 to transfer it on.
 *
 * ON TARGET IT IS THE TAIL JUMP ITSELF, written as inline asm rather than as a C call through a
 * function pointer, and that is the whole of the reconstruction's contribution. A C call would build
 * a frame: the routine would see a return address of Supexec's own making, and would return INTO
 * Supexec instead of past it — which is precisely the difference between the ROM's `jmp` and a
 * `jsr`. `__builtin_unreachable()` is what says control does not come back, so GCC emits no epilogue
 * after it. (m68k-elf-gcc compiles the body to `move.l 8(%sp),%a0 / jmp (%a0)` — the ROM's own pair,
 * one stack slot over because the harness's `image` is this build's first argument.)
 *
 * OFF TARGET THE ROUTINE CANNOT RUN AT ALL: it is 68000 code in the image, and the differential's
 * candidate is host code over a byte array. So the host build transfers control through a hook the
 * CASE binds — `test_xbios_supexec.py` sets `recreate_call_routine` to a Python function that
 * applies, in the image, exactly what the 68000 stub it staged for the ORACLE does. The hook is
 * keyed BY ADDRESS, which is what makes the decoy case mean something on this side too: a candidate
 * that jumped to a baked-in address would reach the decoy's effect rather than the named stub's.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#include <stddef.h>
#endif
#include <stdint.h>

#ifdef RECREATE_HOST_DIFFERENTIAL
/* Bound by the case through the candidate .so's symbol table (ctypes), once per module. Deliberately
 * NOT a parameter of `xbios_supexec`: the ROM's argument is the address, and a signature that took a
 * host callable would be a different function from the one the target build compiles. */
uint32_t (*recreate_call_routine)(uint8_t *image, uint32_t routine_address);
#endif

uint32_t xbios_supexec(uint8_t *image, uint32_t routine_address)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    assert(recreate_call_routine != NULL &&
           "a Supexec case must bind recreate_call_routine to the effect of the stub it staged");
    return recreate_call_routine(image, routine_address);
#else
    (void)image;
    __asm__ volatile ("jmp (%0)" : : "a"(routine_address));
    __builtin_unreachable();
#endif
}
