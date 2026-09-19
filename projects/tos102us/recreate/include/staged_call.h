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
/* Spelt in two pieces because the three shapes at the bottom of this file need A1 for the ROUTINE —
 * their callees read A0, so A0 cannot hold it — and a register an `asm` names as an operand may not
 * also be clobbered. Two lists written out in full would be one rule spelt twice, and the second
 * copy is the one that would miss a register. */
#define STAGED_CALL_CLOBBERS_D1_D7 "d1", "d2", "d3", "d4", "d5", "d6", "d7"
#define STAGED_CALL_CLOBBERS_A2_A4 "a2", "a3", "a4"
#define STAGED_CALL_CLOBBERS STAGED_CALL_CLOBBERS_D1_D7, "a1", STAGED_CALL_CLOBBERS_A2_A4, \
                             "memory", "cc"
/* ...and the same list for a shape whose ROUTINE is in A1, so A1 is an operand rather than free. */
#define STAGED_CALL_CLOBBERS_ROUTINE_IN_A1 STAGED_CALL_CLOBBERS_D1_D7, \
                                           STAGED_CALL_CLOBBERS_A2_A4, "memory", "cc"

/* A5 IS AN OPERAND OF EVERY SHAPE BELOW, NOT A CLOBBER, AND THE VALUE IS THE ROM'S OWN ZERO.
 *
 * Each of these handlers opens `lea 0,a5` inside its `movem` bracket, and every routine TOS installs
 * in one of these slots reaches low RAM and the I/O page through `(a5)` displacements: `$fc29fc`'s
 * first instruction is `lea $d84(a5),a0`, the IOREC it is about to service. `src/bios/isr.S` spells
 * that zero as the PUSHED IMAGE ARGUMENT instead — which the C body needs and the vector does not —
 * so the register itself is pinned HERE, at the one place control leaves for a routine that expects
 * it, rather than in a stub whose value a C body is free to allocate over.
 *
 * WHAT FOUND IT is the ACIA chain's own Tier 3 row. With the captured machine's real service
 * routines back in KBDVECS — rather than a staged stub that reads no register — the cross-compiled
 * `isr_acia` spun until the oracle's cap, because `$fc2a0c` had indexed its IOREC off whatever GCC
 * last left in A5. Every case before that staged a stub that read nothing, so no differential could
 * see it; this is `docs/on-target-execution.md`'s register-contract class, at a RAM vector.
 *
 * Declared read-write ("+a") because the callee owes this caller nothing: it may leave anything in
 * A5, and telling GCC the value does not survive is what makes the next call set it again.
 *
 * THE DECLARATION AND THE CONSTRAINT ARE ONE PIN IN TWO TOKENS: a register variable's declaration and
 * its operand sit in different parts of the statement, so C cannot spell them as one macro. They are
 * defined together here and never used apart, which is what keeps five shapes from carrying five
 * copies of a pin that has to agree with itself. */
#define STAGED_CALL_VECTOR_BASE 0
#define STAGED_CALL_BASE_REGISTER \
    register uint32_t vector_base __asm__("a5") = STAGED_CALL_VECTOR_BASE
#define STAGED_CALL_BASE_OPERAND "+a"(vector_base)

/* `movea.l <vector>,a0 / jsr (a0)` — the whole of the VBL's and the ACIA handler's calls. */
static inline void call_vector(uint8_t *image, uint32_t routine)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    recreate_call_vector(image, routine, STAGED_CALL_NO_ARGUMENT);
#else
    register uint32_t target __asm__("a0") = routine;
    STAGED_CALL_BASE_REGISTER;

    (void)image;
    __asm__ volatile ("jsr (%0)"
                      : "+a"(target), STAGED_CALL_BASE_OPERAND
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
    STAGED_CALL_BASE_REGISTER;

    (void)image;
    __asm__ volatile ("move.w %1,-(%%sp)\n\t"
                      "jsr (%0)\n\t"
                      "addq.w #2,%%sp"
                      : "+a"(target), "+d"(pushed), STAGED_CALL_BASE_OPERAND
                      :
                      : STAGED_CALL_CLOBBERS);
#endif
}

/* ---- the three shapes the IKBD/MIDI input chain adds, all of which put something in A0 ----------
 *
 * The two forms above pass their operand on the STACK, which is what a C handler reads. The 6301's
 * own packet handlers do not: `mousevec`, `clockvec`, `joyvec`, `statvec` and `midivec` are called
 * with A0 naming the packet (or the IOREC) exactly as the ROM's `lea`/`movea.l` left it, which is
 * the published KBDVECS contract. So the ROUTINE moves to A1 here, and A0 carries the argument.
 *
 * OFF TARGET ALL THREE REACH THE SAME HOOK as the two above, with `argument` carrying the packet
 * address or the received byte — because a host stub has no register file and nothing on this side
 * could observe which register a value arrived in. What the register placement IS pinned by is Tier
 * 3: the cross-compiled blob really jumps into whatever the case staged, so a case that leaves the
 * ROM's own `midivec` in the slot has its `move.b d0` and `movea.l a0` read by the ROM's own code.
 */

/* THE TWO PACKET SHAPES ARE ONE SHAPE AND TWO INSTRUCTION SEQUENCES, so the registers, the operands
 * and the clobber list are written once and each caller supplies the ROM's own instructions around
 * the `jsr`. The sequences stay AT the call sites, because which instructions the ROM makes is the
 * fidelity claim and a reader has to be able to see it. */
#define STAGED_CALL_PACKET(image, routine, packet, before, after)                                  \
    do {                                                                                           \
        register uint32_t target __asm__("a1") = (routine);                                        \
        register uint32_t block __asm__("a0") = (packet);                                          \
        STAGED_CALL_BASE_REGISTER;                                                                 \
                                                                                                   \
        (void)(image);                                                                             \
        __asm__ volatile (before "jsr (%0)" after                                                  \
                          : "+a"(target), "+a"(block), STAGED_CALL_BASE_OPERAND                    \
                          :                                                                        \
                          : STAGED_CALL_CLOBBERS_ROUTINE_IN_A1, "d0");                             \
    } while (0)

/* `move.l <packet>,-(sp) / jsr (a2) / addq.w #4,sp`, with A0 already naming the packet — the IKBD
 * packet machine's dispatch at `$fc2afa`. The push and the register are the SAME address: TOS calls
 * these vectors both ways round so that a C handler and an asm one can each read the one it knows. */
static inline void call_vector_packet_pushed(uint8_t *image, uint32_t routine, uint32_t packet)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    recreate_call_vector(image, routine, packet);
#else
    STAGED_CALL_PACKET(image, routine, packet, "move.l %1,-(%%sp)\n\t", "\n\taddq.w #4,%%sp");
#endif
}

/* ...and the same call with NOTHING pushed, which is how the keyboard's own mouse emulation reaches
 * `mousevec` at `$fc2e9a`: A0 names the three-byte packet and the longword under the return address
 * is the caller's own saved A0, not the packet. */
static inline void call_vector_packet(uint8_t *image, uint32_t routine, uint32_t packet)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    recreate_call_vector(image, routine, packet);
#else
    STAGED_CALL_PACKET(image, routine, packet, "", "");
#endif
}

/* `move.b <byte>,d0 / <a0 = the IOREC> / jmp (a2)` — the two places `acia_take_byte` hands a RAW
 * BYTE to a vector: MIDI's `midivec` ($fc2e38) and either 6850's overrun vector ($fc2a3e).
 *
 * THE ROM TAIL-JUMPS AND THIS CALLS, and the difference is the stack depth the callee sees plus the
 * return address it would find there — `src/xbios/supexec.c` carries the same residual for the same
 * reason. Neither build can spell a tail jump out of a C body without owning the frame, and no
 * handler TOS installs in these slots reads either.
 *
 * A SECOND RESIDUAL, in the registers. At the ROM's `jmp (a2)` the callee finds A1 = the 6850's own
 * STATUS ADDRESS ($fffc00 or $fffc04) and D2 = the status byte it just read, because that is simply
 * what the service body was holding; here A1 is the ROUTINE and D2 is a clobber. It is moot for the
 * vectors the capture holds — the error vectors are a bare `rts` and `midivec` reads only A0 and D0
 * — but a Tier 3 case that staged a stub reading A1 would diverge, and it would be right to. */
static inline void call_vector_byte(uint8_t *image, uint32_t routine, uint32_t iorec, uint8_t byte)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    (void)iorec;
    recreate_call_vector(image, routine, byte);
#else
    register uint32_t target __asm__("a1") = routine;
    register uint32_t record __asm__("a0") = iorec;
    register uint32_t received __asm__("d0") = byte;
    STAGED_CALL_BASE_REGISTER;

    (void)image;
    __asm__ volatile ("jsr (%0)"
                      : "+a"(target), "+a"(record), "+d"(received), STAGED_CALL_BASE_OPERAND
                      :
                      : STAGED_CALL_CLOBBERS_ROUTINE_IN_A1);
#endif
}

#endif /* TOS102US_STAGED_CALL_H */
