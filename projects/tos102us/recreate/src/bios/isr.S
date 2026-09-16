/* isr.S — the four INTERRUPT HANDLERS as the machine reaches them: the ROM's own entry and exit
 * sequences, with the reconstruction's C core in the middle.
 *
 * WHY THIS IS ASSEMBLY, which is `trap.S`'s argument one exception class further out. A handler is
 * entered by the 68000 with an exception frame on the supervisor stack and leaves through `rte`; it
 * saves and restores the interrupted program's register file with a `movem` pair whose list IS its
 * contract (the ACIA handler gives D0-D3/A0-A3/A5 back and NOTHING else — `test_bios_ikbd.py` pins
 * both halves); it acknowledges its own MFP channel after the restore, on a path the register file
 * is no longer saved across; and it reaches every system variable through an A5 it zeroes itself. A
 * C function owes none of that and has no way to say any of it, so the reconstruction carries the
 * ROM's own instruction sequence and is proved against it by the SECOND DIFFERENTIAL of Tier 3's
 * numerator (`tools/recreate_kit/rom_bench.py`, `RomBench.measure_transcription`): the m68k assembly
 * of this file, entered over the same staged frame as the original, must leave the same image, the
 * same WHOLE register file and the same chip traffic.
 *
 * TWO SYMBOLS PER HANDLER, and the split is the whole design of this file:
 *
 *   `isr_vbl`        the C core — the handler as a C function, which is what Tier 1's host
 *                    differential proves and what `test/test_bios_vbl.py` puts its cases to;
 *   `isr_vbl_entry`  THIS FILE — what a shipped ROM installs in vector $70. It is the ROM's own
 *                    entry sequence around the C, so the two are the asm-twin pair this workspace
 *                    already uses for a routine that cannot be C on the target, and the Tier 3
 *                    table measures both against the same original over the same cases.
 *
 * WHERE THE SPLIT FALLS IS THE ROM'S CHOICE, not a convenience. The VBL and timer C do real work
 * BEFORE they save any register — `addq.l #1,_frclock` counts blanks that happened even when the
 * semaphore refuses the body, and `addq.l #1,_hz_200` counts ticks the divider throws away — and
 * timer C acknowledges its channel AFTER the restore, on both paths. Those instructions are the
 * handler rather than the body, so they are here, and the C each stub calls is the SERVICED body
 * alone (`service_this_vertical_blank`, `service_this_timer_c_tick`). The ACIA handler does none of
 * it: its whole body is inside the `movem` pair, so its stub is a bracket and the C it calls is the
 * whole of `isr_acia`. The HBL saves nothing but D0 and its body is three instructions, so it is
 * transcribed outright and calls nothing.
 *
 * THE IMAGE ARGUMENT IS A PUSHED ZERO. Every core in this recreate takes `uint8_t *image` and the
 * machine's own base for it is 0 — the ROM reaches the same memory through `suba.l a5,a5` and an
 * `(a5)` displacement, which has no C analogue — so each stub pushes a literal 0 where the ROM
 * zeroes A5. That is the one instruction here the ROM does not have, and the one place these ratios
 * differ from 1.00 for a reason that is not the `jsr`.
 *
 * THE TRANSCRIPTION IS BYTE-FOR-BYTE THE ROM'S wherever it is literal, and each handler's battery
 * says so in its own `test_the_stub_at_the_vector_is_the_rom_s_own_bytes`: the assembled words are
 * read back out of the cross-compiled blob and compared with the ROM's at $fc06c8 / $fc06de /
 * $fc30c4 / $fc29ce. `isr.LITERAL_SPANS` carries the three differences an assembler makes and the
 * reason each is the same instruction — a branch displacement that measures to our own body, GNU
 * as's `andi.w` encoding of `and.w #imm,Dn`, and an absolute address the ROM spells sign-extended
 * ($fffffa11 for the MFP, which a 24-bit bus makes `addrs.h`'s $fffa11).
 */
#include "addrs.h"

/* The pushed image pointer, which every stub below drops after its `jsr`. Named because it is an
 * ARGUMENT SLOT and not a stack tidy-up: the m68k SysV ABI puts the first argument at 4(sp). */
#define IMAGE_ARGUMENT_BYTES 4

    .text

/* ---- the HORIZONTAL BLANK — vector $68, $fc06c8 ------------------------------------------------
 * All seven instructions, and no call: the body is the two that read and edit the frame's own SR
 * word. `src/bios/hbl.c` is the same three lines as C, which is what Tier 1 proves and what makes
 * every frame this file's two registered cases do not stage a compared fact.
 *
 * The frame's SR is at 2(sp) rather than 0(sp) because of the push one line above it — the handler
 * makes room for the D0 it is about to use — so the displacement is the saved word plus the field's
 * own offset. */
#define HBL_SAVED_D0_BYTES 2

    .globl  isr_hbl_entry
isr_hbl_entry:
    move.w  %d0,-(%sp)                          /* ...so the frame starts at 2(sp) from here on */
    move.w  (HBL_SAVED_D0_BYTES + EXCEPTION_FRAME_SR,%sp),%d0
    and.w   #SR_IPL_MASK,%d0                    /* what the interrupted code was masked at */
    bne.s   .Lhbl_out                           /* anything at all: leave the frame as it is */
    ori.w   #HBL_IPL_FLOOR,(HBL_SAVED_D0_BYTES + EXCEPTION_FRAME_SR,%sp)
.Lhbl_out:
    move.w  (%sp)+,%d0
    rte

/* ---- the VERTICAL BLANK — vector $70, $fc06de ---------------------------------------------------
 * `_frclock` counts blanks that HAPPENED and is bumped before the semaphore can refuse anything;
 * `_vbclock`, inside the C, counts the ones this handler serviced. The semaphore is released on
 * BOTH paths and RE-READ to do it, which is why the `addq.w` below is a memory read-modify-write
 * and not the value the `subq.w` computed. */
    .globl  isr_vbl_entry
isr_vbl_entry:
    addq.l  #1,(SYSVAR_FRCLOCK).l
    subq.w  #1,(SYSVAR_VBLSEM).l
    bmi.w   .Lvbl_release                       /* already taken: no body, and no registers saved */
    movem.l %d0-%a6,-(%sp)
    pea     (0).w                               /* the image base, where the ROM zeroes A5 */
    jsr     service_this_vertical_blank
    addq.l  #IMAGE_ARGUMENT_BYTES,%sp
    movem.l (%sp)+,%d0-%a6
.Lvbl_release:
    addq.w  #1,(SYSVAR_VBLSEM).l
    rte

/* ---- the MFP's TIMER C — vector $114, $fc30c4 ---------------------------------------------------
 * The divider is a ROTATE and not a counter: $4444 -> $8888 -> $1111 -> $2222 is a four-state cycle
 * with exactly one negative state, so the body runs on one tick in four. The tick count and the
 * acknowledgement are on BOTH paths — a tick that does no work still counts and still clears
 * channel 5's in-service bit, which is what keeps the channel firing.
 *
 * THE ACKNOWLEDGEMENT IS ONE INSTRUCTION HERE and two bus accesses in the C (`include/mfp.h`: a
 * declared read and a ledgered store, because $fffa11's other seven bits are seven other channels'
 * flags and a door whose read half is a fabricated 0 cannot hold them). The ROM's `bclr` on memory
 * IS a read and a write, so the two are the same ordered traffic; what differs is the cycles, which
 * is mechanism (H) in `bench/tier3.py` and the reason this stub carries the instruction itself. */
    .globl  isr_timer_c_entry
isr_timer_c_entry:
    addq.l  #1,(SYSVAR_HZ_200).l
    rol.w   (SYSVAR_TIMER_C_DIVIDER).l
    bpl.s   .Ltimer_c_acknowledge               /* one tick in four goes past here */
    movem.l %d0-%a6,-(%sp)
    pea     (0).w
    jsr     service_this_timer_c_tick
    addq.l  #IMAGE_ARGUMENT_BYTES,%sp
    movem.l (%sp)+,%d0-%a6
.Ltimer_c_acknowledge:
    bclr    #MFP_ISRB_TIMER_C_BIT,(MFP_ISRB).l
    rte

/* ---- the ACIA channel — vector $118, $fc29ce ----------------------------------------------------
 * A pure bracket: everything the handler does, including its own acknowledgement, is inside the
 * `movem` pair and therefore inside `isr_acia`. THE LIST IS THE CONTRACT — D0-D3/A0-A3/A5 and
 * nothing else — so a caller of this handler gets D4-D7/A4/A6 back holding whatever the two staged
 * service routines left in them, which `test_bios_ikbd.py` pins in both directions. */
    .globl  isr_acia_entry
isr_acia_entry:
    movem.l %d0-%d3/%a0-%a3/%a5,-(%sp)
    pea     (0).w
    jsr     isr_acia
    addq.l  #IMAGE_ARGUMENT_BYTES,%sp
    movem.l (%sp)+,%d0-%d3/%a0-%a3/%a5
    rte
