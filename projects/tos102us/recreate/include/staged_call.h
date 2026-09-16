/* staged_call.h — how a reconstructed handler transfers control to a routine a RAM VECTOR names.
 *
 * The interrupt handlers are full of `movea.l <vector>(a5),a0 / jsr (a0)`: the VBL calls `swv_vec`
 * on a monitor change, every non-zero slot of `_vblqueue`, and `scr_dump` through Scrdmp; timer C
 * calls `etv_timer` with a word pushed; the ACIA handler calls KBDVECS' `midisys` and `ikbdsys` on
 * every entry. WHAT runs there is a longword in RAM rather than an address in the ROM — the boot
 * fills it and anything may replace it — so it is an INPUT of the handler, and a case stages a
 * routine of its own exactly as `test_xbios_supexec.py` stages one for Supexec.
 *
 * TWO SHAPES, because the ROM has two: a bare `jsr`, and the one timer C makes with a word pushed
 * in front of it. The word matters: `move.w %0,-(sp)` is TWO bytes of frame, where a C call would
 * widen the argument to a four-byte slot and a staged routine reading `4(sp).w` would find the high
 * half. So the target build spells both as the ROM's own instructions rather than as a C call
 * through a function pointer.
 *
 * OFF TARGET THE ROUTINE CANNOT RUN AT ALL — it is 68000 code in the image, and the candidate is
 * host code over a byte array — so the host build transfers control through `recreate_call_vector`,
 * a hook the CASE binds to a Python function with the same effect as the stub it staged for the
 * oracle. Keyed BY ADDRESS, which is what makes a decoy staged beside the named routine mean
 * something on this side too.
 *
 * IT IS A SECOND HOOK BESIDE `src/xbios/supexec.c`'s `recreate_call_routine`, deliberately and not
 * happily. The two have different signatures — Supexec TAIL-JUMPS and its routine's D0 is the XBIOS
 * call's result, so its hook returns one; a handler CALLS and ignores what comes back, and one of
 * its two forms pushes a word first. And both are bound at their own battery's import, so a single
 * symbol would have the later import silently win under `pytest -n auto`. Folding them into one
 * hook means changing that core's signature and that battery's binding, which belongs with them.
 *
 * WHAT NEITHER BUILD MODELS is a staged routine that clobbers a register the C ABI calls
 * callee-saved. On TARGET that is answered rather than modelled — the clobber list below says the
 * callee keeps to nothing — but off target there is no register file to clobber, so a case cannot
 * stage a routine that does it and no differential here would see one.
 */
#ifndef TOS102US_STAGED_CALL_H
#define TOS102US_STAGED_CALL_H

#include <stdint.h>

/* What `argument` carries for the bare `jsr` form. Not a word the 68000 could push, so a staged
 * host routine can tell "nothing was pushed" from "a zero was". */
#define STAGED_CALL_NO_ARGUMENT 0xffffffffu

#ifdef RECREATE_HOST_DIFFERENTIAL
/* Bound by the case through the candidate `.so`'s symbol table (ctypes) — see `test/isr.py`.
 * Deliberately not a parameter of the handlers: the ROM's operand is the address in the vector, and
 * a signature that took a host callable would be a different function from the one the target
 * build compiles. */
extern void (*recreate_call_vector)(uint8_t *image, uint32_t routine, uint32_t argument);
#endif

/* WHAT THE TWO `jsr`s BELOW CLOBBER, and it is not the C ABI's list. A routine in a RAM vector owes
 * this caller nothing: it is whatever the boot, a driver or a program left there, and the only
 * contract it has is the ROM's own — which is why every ROM caller of one defends itself by hand
 * (the VBL's `movem.l d7/a0,-(sp)` around each `_vblqueue` slot, inside the handler's own
 * `movem.l d0-a6` around the lot). D2-D7 and A2-A6 are callee-saved to a C compiler and are NOT
 * callee-saved here, which is `docs/on-target-execution.md`'s d2/a2 bug class exactly, so the list
 * says so: every data register, and every address register the stub does not need itself.
 *
 * THE STUB'S OWN OPERANDS ARE PINNED rather than clobbered, and that is why they are missing from
 * the list: a register an `asm` names as an operand may not also be clobbered, and a list that left
 * GCC nothing to allocate is a compile error rather than a safer program (measured, both ways). So
 * A0 holds the routine — the register the ROM's own `movea.l <vector>,a0` uses — and D0 the pushed
 * word, each declared read-write ("+"), which tells GCC the value does not survive the call. Between
 * the two operands and the list below, every data register and A0-A5 are accounted for.
 *
 * A6 IS THE ONE EXCEPTION, and it is a toolchain bound rather than a judgement: GCC 16 cannot
 * compile a `jsr` through an address register with A6 clobbered as well — it runs out of ADDR_REGS,
 * and pinning A0 to free one up ICEs in `print_operand_address` instead. What makes it safe is the
 * layer above: `src/bios/isr.S` brackets the whole handler in the ROM's own `movem` pair, so the
 * INTERRUPTED PROGRAM gets A6 back whatever a staged routine did with it. What is left unguarded is
 * a local of our own C body, and only if GCC chose A6 for it. */
#define STAGED_CALL_CLOBBERS "d1", "d2", "d3", "d4", "d5", "d6", "d7", \
                             "a1", "a2", "a3", "a4", "a5", "memory", "cc"

/* `movea.l <vector>,a0 / jsr (a0)` — the whole of the VBL's and the ACIA handler's calls. */
static inline void call_vector(uint8_t *image, uint32_t routine)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    recreate_call_vector(image, routine, STAGED_CALL_NO_ARGUMENT);
#else
    register uint32_t target __asm__("a0") = routine;

    (void)image;
    __asm__ volatile ("jsr (%0)"
                      : "+a"(target)
                      :
                      : STAGED_CALL_CLOBBERS, "d0");   /* no pushed word: D0 is a clobber here */
#endif
}

/* ...and `move.w <arg>,-(sp) / movea.l <vector>,a0 / jsr (a0) / addq.w #2,sp`, which is timer C's
 * call into `etv_timer` and the only place in this wave that passes one. */
static inline void call_vector_word(uint8_t *image, uint32_t routine, uint16_t argument)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    recreate_call_vector(image, routine, argument);
#else
    register uint32_t target __asm__("a0") = routine;
    register uint16_t pushed __asm__("d0") = argument;

    (void)image;
    __asm__ volatile ("move.w %1,-(%%sp)\n\t"
                      "jsr (%0)\n\t"
                      "addq.w #2,%%sp"
                      : "+a"(target), "+d"(pushed)
                      :
                      : STAGED_CALL_CLOBBERS);
#endif
}

#endif /* TOS102US_STAGED_CALL_H */
