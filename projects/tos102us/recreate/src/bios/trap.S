/* trap.S — the BIOS (trap #13) and XBIOS (trap #14) entries and the dispatcher they share.
 *
 * WHY THIS IS ASSEMBLY AND NOT C, which is the whole reason this file exists in a C recreate. The
 * routine is an EXCEPTION HANDLER: it is entered by the 68000 with a group-2 exception frame on the
 * supervisor stack and it leaves through `rte`, it moves the stack pointer between the supervisor
 * and user stacks, it saves the caller's register file into the BIOS's own save area rather than
 * into a C frame, and the register file it hands back is part of its contract — the published TOS
 * ABI is "D3-D7/A3-A6 preserved, everything else the callee's". A C compiler owes none of that and
 * has no way to say any of it, so the reconstruction carries the ROM's own instruction sequence
 * (the games' asm-twin convention) and is proved against it by the SECOND DIFFERENTIAL of Tier 3's
 * numerator: the m68k assembly of this file, entered over the same staged frame as the original,
 * must leave the same image, the same register file and the same chip traffic
 * (`tools/recreate_kit/rom_bench.py`, `RomBench.measure_transcription`).
 *
 * THE TRANSCRIPTION IS BYTE-FOR-BYTE THE ROM'S but for THREE OPCODE WORDS. The ROM reaches its
 * dispatch tables PC-relatively (`lea (d16,pc),a0`, 8 cycles) because they sit 84 and 76 bytes past
 * the instruction; this file is linked wherever the build puts it, so both of those `lea`s assemble
 * as absolute long (12 cycles, and six bytes where the ROM's are four). The third is the `bra.s`
 * between them, which now has two more bytes to clear: its displacement is 6 where the ROM's is 4,
 * at the same two cycles. So the cost is four cycles, once per call, and every opcode word from
 * `trap_dispatch_common` on matches the ROM's at $fc07fc..$fc0845 exactly — which
 * `test_bios_trap.py::test_the_transcription_is_the_roms_bytes_but_for_the_two_leas` compares byte
 * for byte, splicing those three encodings and nothing else.
 *
 * THE REGISTER MAP, which the instructions below cannot carry in their operand names:
 *
 *   a0   the dispatch table, then the routine to call — the only thing the two entries differ in
 *   a1   the walking `savptr` frame pointer ($4a2): the BIOS's own register-save area
 *   d0   the exception frame's SR word, then the function number, then the ROUTINE'S RESULT
 *   a5   ZEROED before the call, which is why every BIOS/XBIOS routine in this recreate is entered
 *        with A5 = 0 and reaches low RAM and the I/O page through 16-bit displacements off it
 *
 * WHAT THE CALLER GETS BACK, and it is a ROM FACT this file must REPRODUCE rather than improve on:
 * the `movem` pair below saves and restores D3-D7/A3-A7 and NOTHING ELSE. D0 is the result; D1, D2,
 * A0, A1 and A2 come back holding whatever the dispatcher and the called routine left in them. That
 * is the hardware half of `docs/on-target-execution.md`'s "TOS traps clobber d2/a2 that GCC thinks
 * are callee-saved" — the bug class that cost a real-hardware run — and the battery
 * (`test/test_bios_trap.py`) pins it by comparing the WHOLE register file on both sides.
 *
 * THE BOUND CHECK IS SIGNED (`bge`), which bounds the function number from ABOVE ONLY. A number at
 * or past the table's count word returns without dispatching, leaving the function number itself in
 * D0's low word and the CALLER's own high word above it; a NEGATIVE one passes the test and indexes
 * BACKWARDS out of the table, off into whatever precedes it. Both are transcribed as they stand —
 * see the battery for the first, which is a case, and for why the second is documented rather than
 * executed.
 */
#include "addrs.h"

    .text

/* XBIOS — trap #14, vector $b8. The entry is the table and nothing else. */
    .globl  xbios_trap14
xbios_trap14:
    lea     XBIOS_FUNCTION_TABLE, %a0
    bra.s   trap_dispatch_common

/* BIOS — trap #13, vector $b4. Falls through, as the ROM's does. */
    .globl  bios_trap13
bios_trap13:
    lea     BIOS_FUNCTION_TABLE, %a0

/* ...and everything from here on is shared by both traps. */
    .globl  trap_dispatch_common
trap_dispatch_common:
    movea.l (SYSVAR_SAVPTR).l, %a1      /* the BIOS's register-save area, wherever it has got to */
    move.w  (%sp)+, %d0                 /* the exception frame: its SR word... */
    move.w  %d0, -(%a1)                 /* ...pushed into the save area... */
    move.l  (%sp)+, -(%a1)              /* ...and its return PC after it */
    movem.l %d3-%d7/%a3-%a6/%sp, -(%a1) /* the registers the ABI promises the caller back */
    move.l  %a1, (SYSVAR_SAVPTR).l      /* ...and savptr now names THIS frame, so a trap taken
                                         * inside the called routine nests under it */
    btst    #SR_SUPERVISOR_BIT, %d0     /* was the caller in supervisor mode? */
    bne.s   .Largs_are_here
    move.l  %usp, %sp                   /* no: its arguments are on the USER stack, so run there */
.Largs_are_here:
    move.w  (%sp)+, %d0                 /* the function number, off the caller's own stack */
    cmp.w   (%a0)+, %d0                 /* ...against the table's count word (and a0 -> the entries) */
    bge.s   .Lreturn                    /* out of range: no call, and D0 keeps the number */
    lsl.w   #TRAP_TABLE_ENTRY_SHIFT, %d0    /* a WORD shift — the index is never wider */
    move.l  (0,%a0,%d0.w), %d0
    movea.l %d0, %a0
    bpl.s   .Lcall
    movea.l (%a0), %a0                  /* bit 31 set: the entry is a RAM vector, not a routine */
.Lcall:
    suba.l  %a5, %a5                    /* every BIOS/XBIOS routine is entered with A5 = 0 */
    jsr     (%a0)
.Lreturn:
    movea.l (SYSVAR_SAVPTR).l, %a1      /* re-read, because the called routine may have nested */
    movem.l (%a1)+, %d3-%d7/%a3-%a6/%sp /* ...which also puts the caller's stack pointer back */
    move.l  (%a1)+, -(%sp)              /* rebuild the exception frame the `rte` needs: PC... */
    move.w  (%a1)+, -(%sp)              /* ...and SR */
    move.l  %a1, (SYSVAR_SAVPTR).l      /* ...and savptr is back to the frame above ours */
    rte
