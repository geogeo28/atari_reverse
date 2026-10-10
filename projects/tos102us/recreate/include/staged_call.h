/* staged_call.h — how a reconstructed handler transfers control to a routine a RAM VECTOR names.
 *
 * The interrupt handlers are full of `movea.l <vector>(a5),a0 / jsr (a0)`: the VBL calls `swv_vec`
 * on a monitor change, every non-zero slot of `_vblqueue`, and `scr_dump` through Scrdmp; timer C
 * calls `etv_timer` with a word pushed; the ACIA handler calls KBDVECS' `midisys` and `ikbdsys` on
 * every entry. WHAT runs there is a longword in RAM rather than an address in the ROM — the boot
 * fills it and anything may replace it — so it is an INPUT of the handler, and a case stages a
 * routine of its own exactly as `test_xbios_supexec.py` stages one for Supexec.
 *
 * ONE SHAPE PER CALL THE ROM MAKES, each spelt as the ROM's own instructions rather than as a C call
 * through a function pointer. The first two are the interrupt handlers': a bare `jsr`, and the one
 * timer C makes with a word pushed in front of it. The word matters: `move.w %0,-(sp)` is TWO bytes
 * of frame, where a C call would widen the argument to a four-byte slot and a staged routine reading
 * `4(sp).w` would find the high half. The IKBD/MIDI chain adds three that put something in A0, and
 * the VDI two more — a register-carrying one and one that saves round the `jsr` itself — each
 * introduced where it is defined below.
 *
 * OFF TARGET THE ROUTINE CANNOT RUN AT ALL — it is 68000 code in the image, and the candidate is
 * host code over a byte array — so the host build transfers control through `recreate_call_vector`,
 * a hook the CASE binds to a Python function with the same effect as the stub it staged for the
 * oracle. Keyed BY ADDRESS, which is what makes a decoy staged beside the named routine mean
 * something on this side too.
 *
 * A SECOND HOOK HERE, `recreate_call_vector_registers`, serves the shape that passes REGISTERS back
 * (`call_vector_registers`): a hook of `recreate_call_vector`'s signature has nowhere to put them.
 * The AES's Alcyon object call (the end of this file) reaches it too, with its frame's three values.
 *
 * IT IS ANOTHER HOOK BESIDE `src/xbios/supexec.c`'s `recreate_call_routine`, deliberately and not
 * happily. The two have different signatures — Supexec TAIL-JUMPS and its routine's D0 is the XBIOS
 * call's result, so its hook returns one; a handler CALLS and ignores what comes back, and one of
 * its two forms pushes a word first. And both are bound at their own battery's import, so a single
 * symbol would have the later import silently win under `pytest -n auto`. Folding them into one
 * hook means changing that core's signature and that battery's binding, which belongs with them.
 *
 * WHAT THE HOST BUILD CANNOT MODEL is a staged routine that clobbers a register the C ABI calls
 * callee-saved: off target there is no register file to clobber, so no Tier 1 case can stage one. On
 * TARGET it is answered — the clobber list below says the callee keeps to nothing — for every register
 * BUT A6 (below), and a routine that keeps none at all is staged where the cross-compiled blob runs it
 * for real: `test/isr.py`'s `keeps_nothing`, under the vertical blank's entry at each of its three calls.
 */
#ifndef TOS102US_STAGED_CALL_H
#define TOS102US_STAGED_CALL_H

#include <stdint.h>

/* What `argument` carries for the bare `jsr` form. Not a word the 68000 could push, so a staged
 * host routine can tell "nothing was pushed" from "a zero was". */
#define STAGED_CALL_NO_ARGUMENT 0xffffffffu

/* The REGISTER-CARRYING shape's register file, in the order its host hook hands it over. */
enum { STAGED_D0, STAGED_D1, STAGED_A0, STAGED_REGISTERS };

#ifdef RECREATE_HOST_DIFFERENTIAL
/* Bound by the case through the candidate `.so`'s symbol table (ctypes) — see `test/isr.py`.
 * Deliberately not a parameter of the handlers: the ROM's operand is the address in the vector, and
 * a signature that took a host callable would be a different function from the one the target
 * build compiles. */
extern void (*recreate_call_vector)(uint8_t *image, uint32_t routine, uint32_t argument);
/* ...and the register-carrying shape's (`call_vector_registers`, the end of this file): `registers`
 * is D0, D1, A0 (`STAGED_REGISTERS`), handed in and handed back. Bound in `test/isr.py` too. */
extern void (*recreate_call_vector_registers)(uint8_t *image, uint32_t routine, uint32_t *registers);
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
 * layer above: the handler's own `movem` pair gives the INTERRUPTED PROGRAM A6 back whatever a staged
 * routine did with it. What is left unguarded is a local of our own C body, and only if GCC chose A6
 * for it.
 *
 * IT CHOSE A6, AND THAT IS WHY NO HANDLER SHIPS AS C. `service_this_vertical_blank` held its image
 * pointer in A6 across `swv_vec` and `scr_dump` and its queue pointer across each `_vblqueue` slot, and
 * the VDI's cursor routine (`$fcff2a`, the machine's own slot 0) returns with A6 = `$fd00fe` whenever
 * it redraws: the blank after a mouse move never reached its `rte`. The ROM's handler holds nothing in
 * a register across those calls. C can be made to do the same — NOT BY A CLOBBER (a clobber of A6 makes
 * this compiler want a frame pointer and die in `print_operand_address`, even on an empty `asm`), but A6
 * named as an OUTPUT OPERAND of the `jsr` works (`"=a"` on a variable pinned to it: measured, and NOT
 * USED — no shape below carries it) — at a cost over Tier 3's bar, and the project's rule for that is
 * the ROM's own instructions: `src/bios/isr.S` is the three
 * handlers whole, and the C bodies these shapes serve there are twins no entry calls. The shapes still
 * serve the C that calls a RAM vector elsewhere — the ACIA chain's packet vectors, the VDI's — where the
 * A6 bound stands exactly as written above, and unpinned. */
/* Spelt in two pieces because the three shapes at the bottom of this file need A1 for the ROUTINE —
 * their callees read A0, so A0 cannot hold it — and a register an `asm` names as an operand may not
 * also be clobbered. Two lists written out in full would be one rule spelt twice, and the second
 * copy is the one that would miss a register. */
#define STAGED_CALL_CLOBBERS_D2_D7 "d2", "d3", "d4", "d5", "d6", "d7"
#define STAGED_CALL_CLOBBERS_D1_D7 "d1", STAGED_CALL_CLOBBERS_D2_D7
#define STAGED_CALL_CLOBBERS_A2_A4 "a2", "a3", "a4"
#define STAGED_CALL_CLOBBERS STAGED_CALL_CLOBBERS_D1_D7, "a1", STAGED_CALL_CLOBBERS_A2_A4, \
                             "memory", "cc"
/* ...and the same list for a shape whose ROUTINE is in A1, so A1 is an operand rather than free. */
#define STAGED_CALL_CLOBBERS_ROUTINE_IN_A1 STAGED_CALL_CLOBBERS_D1_D7, \
                                           STAGED_CALL_CLOBBERS_A2_A4, "memory", "cc"

/* A5 IS AN OPERAND OF EVERY INTERRUPT-HANDLER SHAPE BELOW, NOT A CLOBBER, AND THE VALUE IS THE ROM'S OWN
 * ZERO. (The two VDI shapes at the end of the file serve no handler of `src/bios/isr.S`'s and pin no A5;
 * each says why.)
 *
 * Each of these handlers opens `lea 0,a5` inside its `movem` bracket, and every routine TOS installs
 * in one of these slots reaches low RAM and the I/O page through `(a5)` displacements: `$fc29fc`'s
 * first instruction is `lea $d84(a5),a0`, the IOREC it is about to service. A C handler body is handed
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

/* ---- the REGISTER-CARRYING shape: D0, D1 and A0 in AND out --------------------------------------
 *
 * The VDI's two RAM vectors that talk in registers: the mouse ISR's USER_BUT, USER_MOT and USER_CUR
 * (`movea.l USER_x,a1 / jsr (a1)`, D0/D1 handed in and answered, A0 whatever the ISR or the previous
 * routine left — the ISR goes on reading its packet through the A0 USER_BUT hands back, `$fcfe7e`), and
 * the contour fill's SEEDABORT (`movea.l SEEDABORT,a0 / jsr (a0)`, D0.w the answer — its caller loads A0
 * with the routine and this reproduces that). One shape carries all three registers both ways, on
 * target and off, so no caller has to know which of them its routine reads.
 *
 * THE ROUTINE IS IN A1, because A0 is a value here. For SEEDABORT that is a residual beside the ROM,
 * whose A1 at the `jsr` is what the fill left in it: a staged routine reading A1 would diverge, rightly.
 *
 * A5 IS CLOBBERED, NOT PINNED — these callers are no interrupt handler of `src/bios/isr.S`'s, and owe
 * their routine no A5; a routine that uses it (nothing forbids a program's SEEDABORT to) must not take a
 * C local of ours with it. A6 is the toolchain bound above, and here it is not covered by a `movem`
 * bracket: a routine that changes A6 leaves our caller's A6 changed. No routine TOS installs does, and a
 * staged one that did would be a register this project cannot pin. */
static inline void call_vector_registers(uint8_t *image, uint32_t routine, uint32_t registers[STAGED_REGISTERS])
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    recreate_call_vector_registers(image, routine, registers);
#else
    /* D0, D1, A0 as the table names them, and the routine in A1. */
    register uint32_t first __asm__("d0") = registers[STAGED_D0];
    register uint32_t second __asm__("d1") = registers[STAGED_D1];
    register uint32_t pointer __asm__("a0") = registers[STAGED_A0];
    register uint32_t target __asm__("a1") = routine;

    (void)image;
    __asm__ volatile ("jsr (%3)"
                      : "+d"(first), "+d"(second), "+a"(pointer), "+a"(target)
                      :
                      : STAGED_CALL_CLOBBERS_D2_D7, STAGED_CALL_CLOBBERS_A2_A4, "a5", "memory", "cc");
    registers[STAGED_D0] = first;
    registers[STAGED_D1] = second;
    registers[STAGED_A0] = pointer;
#endif
}

/* ---- the bare `jsr` that is its caller's LAST ACT, in a caller that keeps no register for its own ------------
 *
 * The VDI dispatcher's call into the function its opcode table names is its last act (`src/vdi/entry.c`), and
 * a VDI function may change any register (vs_color D3/D4, vr_trnfm D7 — `transcribed.h`). THE ROM'S DISPATCHER
 * KEEPS NONE OF THEM: its `jsr (a0)` is bare and it returns by popping the four registers of its own prologue off
 * its frame ($fcab5e) — because its one caller, the VDI's `trap #2` entry, has saved D1-A6 round the lot
 * (`movem.l d1-a6,-(sp)`, $fc9f9e). So is this: the `jsr` alone, and GCC TOLD ONLY OF D0, D1, A0, A1. What that
 * leaves true, and what holds it:
 *   * the registers the caller's own prologue saved come back off the stack, whatever the function did to them;
 *   * the registers the caller never touched go back to ITS caller as the function left them — a contract no C
 *     caller may rely on: the dispatcher's two callers are the ROM's entry, which needs none, and its C twin,
 *     which saves the lot round its call as the entry does (`src/vdi/entry.c`, dispatched_keeping);
 *   * NOTHING OF THE CALLER'S MAY BE LIVE ACROSS THE CALL in a register GCC believes kept — held on both blobs'
 *     own instructions (`test_vdi_entry.py`: after each `jsr (a0)` of the dispatcher, pops and the return alone).
 * WHY IT IS WORTH A CONTRACT: saved round the `jsr` (the shape this replaced, 2026-10-10) the eleven registers were
 * 44 BYTES UNDER EVERY VDI FUNCTION, on whichever stack the `trap #2` was taken — the screen manager's 1,196 bytes
 * (`test/aes_stack.py`), the dispatcher's 640 — and 196 cycles a call the ROM does not spend.
 * The routine is in A0, as the ROM's own `movea.l (a0,a1.l),a0 / jsr (a0)` has it; nothing is pinned in A5 — the
 * ROM's is its CONTRL pointer, which no VDI function reads on entry. Off target it is `call_vector`'s hook. */
static inline void call_vector_as_the_last_act(uint8_t *image, uint32_t routine)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    recreate_call_vector(image, routine, STAGED_CALL_NO_ARGUMENT);
#else
    register uint32_t target __asm__("a0") = routine;

    (void)image;
    __asm__ volatile ("jsr (%0)"
                      : "+a"(target)
                      :
                      : "d0", "d1", "a1", "memory", "cc");
#endif
}

/* ---- the ALCYON OBJECT CALL: a tree walker's routine, over an Alcyon frame ------------------------------------------
 *
 * The AES's everyobj (`$fed27c`) calls the routine its caller hands it once per object, as Alcyon calls anything:
 * `move.w y,-(sp) / move.w x,-(sp) / move.w object,-(sp) / move.l tree,-(sp) / movea.l <routine>,a0 / jsr (a0) /
 * adda.l #10,sp` — a TEN-byte frame of a longword and three words, which the routine (ob_draw's just_draw, the
 * rectangle lists' mkrect) reads as its own arguments. What it owes the caller is ALCYON's contract, not a vector's:
 * it keeps D3-D7/A3-A6 and may change D0-D2/A0-A2 (everyobj keeps nothing live in those across the call), so those are
 * the clobbers — GCC's D2 and A2 among them.
 *
 * OFF TARGET it reaches the REGISTER-CARRYING hook above rather than a hook of its own (there is ONE such hook): the
 * frame's values in its three slots — the object in D0, x and y as D1's two words (x high), the tree in A0. A host
 * stub has no register file, so nothing on this side could observe which slot a value came in; what the frame's
 * layout IS pinned by is Tier 3, where the cross-compiled blob pushes it for the case's staged 68000 routine (the
 * everyobj rows, `test/test_aes_oblib_walk.py`: a logger that stores each frame it is handed, compared byte for byte). */
static inline void call_alcyon_object(uint8_t *image, uint32_t routine, uint32_t tree, int16_t object, int16_t x,
                                      int16_t y)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    uint32_t registers[STAGED_REGISTERS];

    registers[STAGED_D0] = (uint16_t)object;
    registers[STAGED_D1] = (uint32_t)(uint16_t)x << 16 | (uint16_t)y;
    registers[STAGED_A0] = tree;
    recreate_call_vector_registers(image, routine, registers);
#else
    register uint32_t target __asm__("a0") = routine;

    (void)image;
    /* Every value in a REGISTER ("d", "r"): a stack operand would move under the pushes. */
    __asm__ volatile ("move.w %3,-(%%sp)\n\t"
                      "move.w %2,-(%%sp)\n\t"
                      "move.w %1,-(%%sp)\n\t"
                      "move.l %4,-(%%sp)\n\t"
                      "jsr (%0)\n\t"
                      "lea 10(%%sp),%%sp"
                      : "+a"(target)
                      : "d"(object), "d"(x), "d"(y), "r"(tree)
                      : "d0", "d1", "d2", "a1", "a2", "memory", "cc");
#endif
}

/* ...and THE ROUTINE A CALLER HANDS THE WALKER, BY VALUE (`move.l #<routine>,-(sp)`: ob_draw's just_draw, newrect's
 * mkrect, draw_change's newrect). OFF TARGET it is the ROM routine's own address, as the ROM's: everyobj's call reaches
 * the register-carrying hook, which a case binds to the C core by that address. ON TARGET it is the routine's Alcyon
 * entry linked beside its caller (`obdraw.S`, `wmupdate.S`), which takes everyobj's ten-byte frame into the C core: the
 * ROM's routine run inside our build is what Tier 3's (V) rule refuses (`bench/tier3.py`, AES_OWN_SPANS). The entry is
 * named on target alone — off target it is not linked at all. */
#ifdef RECREATE_HOST_DIFFERENTIAL
#define ALCYON_ROUTINE(rom_address, alcyon_entry) ((uint32_t)(rom_address))
#else
#define ALCYON_ROUTINE(rom_address, alcyon_entry) ((uint32_t)(uintptr_t)(alcyon_entry))

/* ...and THE IMAGE BASE OF AN ENTRY THAT IS HANDED NONE, in C (the fork functions' entries, `src/aes/evfork.c`; the
 * screen manager's, `src/aes/ctlmgr.c`): the target's base, 0, THROUGH A REGISTER GCC CANNOT SEE INTO. With a constant
 * null pointer inlined into a core, every store of the core is a dereference of "null" to the compiler, which ends the
 * function at the first one with a `trap #7` (measured: aes_kchange_fork was `move.w #0,$c72a / trap #7`). A `.S`
 * entry pushes the same 0 at run time (`c_call_glue.h`); this is that, in C. */
static inline uint8_t *target_image(void)
{
    uint8_t *image = 0;

    __asm__ ("" : "+r"(image));
    return image;
}
#endif

/* ---- the ALCYON CALL OF ONE LONGWORD: a routine a caller hands in, over a frame of one pointer -----------------------
 *
 * The shell's sh_find (`$feb0c8`) calls the routine its caller hands it — only sh_main hands one, `$feaddc` — over the
 * path it found: `move.l <path>,-(sp) / movea.l <routine>,a0 / jsr (a0) / addq.l #4,sp`; and the object library's
 * far_call (`$fddec6`) a USERDEF object's drawing routine over its PARMBLK, the same three instructions. THE FORK HOOK
 * is this shape too: forker (`$fe4cb4`) calls each queued FORK FUNCTION — the queue entry's code — over the entry's one
 * longword of data, `move.l 4(a5),-(sp) / movea.l (a5),a0 / jsr (a0) / addq.l #4,sp`, and ignores what comes back. Off
 * target the code is the fork function's ROM address (what the ROM's interrupts queue, and the host's forkq callers
 * store), which a case binds to the C core; on target it is the function's own entry (`src/aes/evfork.c`). ALCYON's
 * contract, as call_alcyon_object's: the routine keeps D3-D7/A3-A6 and may change D0-D2/A0-A2 — and answers in D0,
 * which far_call hands back as its own answer (the object's state, to ob_user's callers) and sh_find ignores.
 *
 * OFF TARGET it reaches the REGISTER-CARRYING hook (there is ONE such hook): the longword in A0's slot, D0 and D1 handed
 * nothing (`STAGED_CALL_NO_ARGUMENT`), and D0's slot as the hook hands it back is the answer. A host stub has no register
 * file, so the frame's layout is pinned at Tier 3, where the cross-compiled blob pushes it for the case's staged 68000
 * routine.
 *
 * ON TARGET D0 IS LIVE ACROSS THE `jsr`, not merely its output: the empty `asm` defines it first and the call reads and
 * writes it ("+d"), so GCC cannot give the pushed longword D0 — exactly as when D0 was a plain clobber, and a caller that
 * ignores the answer (sh_find) compiles to the same bytes (measured). An output-only "=d" — early-clobbered or not — let
 * GCC push the longword from D0 itself: correct, since the push reads it before the routine writes it, but two words
 * different in sh_find. */
static inline uint32_t call_alcyon_pointer(uint8_t *image, uint32_t routine, uint32_t pointer)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    uint32_t registers[STAGED_REGISTERS];

    registers[STAGED_D0] = STAGED_CALL_NO_ARGUMENT;
    registers[STAGED_D1] = STAGED_CALL_NO_ARGUMENT;
    registers[STAGED_A0] = pointer;
    recreate_call_vector_registers(image, routine, registers);
    return registers[STAGED_D0];
#else
    register uint32_t target __asm__("a0") = routine;
    register uint32_t answer __asm__("d0");

    (void)image;
    __asm__ volatile ("" : "=d"(answer));       /* D0 defined here, so it is live into the call below */
    /* The value in a REGISTER ("r"): a stack operand would move under the push. */
    __asm__ volatile ("move.l %2,-(%%sp)\n\t"
                      "jsr (%1)\n\t"
                      "addq.l #4,%%sp"
                      : "+d"(answer), "+a"(target)
                      : "r"(pointer)
                      : "d1", "d2", "a1", "a2", "memory", "cc");
    return answer;
#endif
}

#endif /* TOS102US_STAGED_CALL_H */
