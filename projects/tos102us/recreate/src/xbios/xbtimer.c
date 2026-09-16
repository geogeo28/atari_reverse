/* XBIOS Xbtimer ($1f) — $fc2ff2, and the MFP timer programmer at $fc25b0 that it and `Rsconf` share.
 *
 *   Xbtimer:                                  $fc25b0 (the programmer):
 *      moveq   #0,d0                             movem.l d0-d4/a0-a3,-(sp)
 *      moveq   #0,d1                             movea.l #$fffffa01,a0
 *      moveq   #0,d2                             movea.l #$fc2644,a3   ; IMR offsets
 *      move.w  4(sp),d0    ; timer               movea.l #$fc2648,a2   ; the interrupt-bit masks
 *      move.w  6(sp),d1    ; control             bsr.s   $fc2622
 *      move.w  8(sp),d2    ; data                ... three more, for IER, IPR and ISR ...
 *      bsr.w   $fc25b0                           movea.l #$fc264c,a3   ; control offsets
 *      tst.l   10(sp)      ; the vector          movea.l #$fc2650,a2   ; ...and their masks
 *      bmi.s   .out                              bsr.s   $fc2622
 *      movea.l 10(sp),a2                         exg     a3,a1         ; keep the control register
 *      moveq   #0,d1                             lea     $fc2654,a3    ; data offsets
 *      lea     $fc302a,a1                        moveq   #0,d3
 *      andi.l  #255,d0                           move.b  (a3,d0.w),d3
 *      move.b  (a1,d0.w),d0 ; the channel   .st: move.b  d2,(a0,d3.w)  ; write the data register
 *      bsr.w   $fc2666      ; Mfpint's body      cmp.b   (a0,d3.w),d2  ; ...and read it back
 *   .out:                                        bne.s   .st           ; ...until it sticks
 *      rts                                       exg     a3,a1
 *                                                or.b    d1,(a3)       ; the control bits, last
 *                                                movem.l (sp)+,d0-d4/a0-a3
 *                                                rts
 *
 *      $fc2622:  bsr.s $fc262a          $fc262a:  moveq   #0,d3
 *                move.b (a2),d3                   adda.w  d0,a3        ; offsets + timer
 *                and.b  d3,(a3)                   move.b  (a3),d3
 *                rts                              add.l   a0,d3
 *                                                 movea.l d3,a3        ; = the MFP register
 *                                                 adda.w  d0,a2        ; masks + timer
 *                                                 rts
 *
 * THE FIVE CLEARS ARE `Jdisint` WRITTEN OUT WITH TABLES, and that is a measurement rather than a
 * reading: the four interrupt tables and the mask table give, for timers A..D, exactly the registers
 * and bits `mfp_channel_register`/`mfp_channel_bit` give for MFP channels 13, 8, 5 and 4 — the
 * channels `$fc302a` says those timers are — in `Jdisint`'s own order, mask before enable before
 * pending before in-service. `test_xbios_xbtimer.py` reads all six tables out of the mapped ROM and
 * asserts that identity, so the claim is checked rather than asserted here in prose.
 *
 * THE FIFTH CLEAR IS THE ONE THE TABLES ARE REALLY FOR: the CONTROL registers are not a pair.
 * Timers A and B own a whole byte each ($fffa19, $fffa1b) and their mask is `$00` — the clear wipes
 * the register — while timers C and D SHARE one byte ($fffa1d), so C's mask is `$8f` (keep bit 7 and
 * bits 0-3, clearing its own field at bits 4-6) and D's is `$f8` (keep bits 3-7, clearing bits 0-2).
 * A reconstruction that wiped `$fffa1d` for timer D would stop timer C dead, and the only surface
 * that separates the two is the hardware write ledger's VALUE — which is why these go through the
 * declared I/O map rather than through `hw.h`'s `hw_and8` (`include/mfp.h` has that argument).
 *
 * THE TABLES ARE READ OUT OF THE IMAGE, not copied into C arrays, and `adda.w d0,a3` is a WORD add
 * SIGN-EXTENDED into the address (`m68k_idioms.h`, `word_index`) — so the routine is unbounded in
 * its timer exactly as the ROM is, and a timer of 4 reads the next table along rather than whatever
 * a C array would have done at the end of its storage.
 *
 * ---- WHAT IS NOT RECONSTRUCTED, AND WHY --------------------------------------------------------
 *
 * `.st` above is a WRITE FOLLOWED BY A READ OF THE SAME REGISTER: the 68901 needs a settling time on
 * its data registers, so the ROM stores the byte and re-reads it until the chip agrees. The declared
 * I/O map (TRAP_MODEL.md, Phase 15) serves a per-run CONSTANT describing what a register held on
 * ENTRY; a byte the run itself stored to and then reads back is refused outright, and the refusal
 * says in as many words that no bigger declaration can fix it. Measured on this routine: with the
 * data register left undeclared the run never terminates (the compare can never come true), and with
 * it declared equal to the byte written the run completes and the oracle reports stale reads — at
 * `$fffa1f` for `Xbtimer(timer A)` and `$fffa25` for `Rsconf`'s baud arm — which
 * `harness._vet_io_reads_are_declared` refuses.
 *
 * So `mfp_timer_program` does the part a case can prove and then HALTS (`recreate.h`) rather than
 * carrying on into a write nothing here could check. That halt reaches `Xbtimer` whole and
 * `Rsconf`'s baud arm, which are the two callers; both say so at their own entry.
 *
 * WHAT WOULD UNBLOCK IT: a WRITE-THROUGH arm of the declared I/O map — a declared byte whose value
 * the run's own store replaces, so that a read-back is served what was written rather than what was
 * declared. That is a change to `tools/recreate_kit` (a Phase-16-shaped one, and the FDC/DMA
 * registers Phase 7 names as its non-goal want the same thing), not to this core.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "mfp.h"
#include "recreate.h"
#include "addrs.h"

/* One of the programmer's five clears: `bsr $fc2622` with `a3` an offset table and `a2` a mask one.
 *
 * `image` is the ROM's own tables, which live in it; `index` is the sign-extended timer (see the
 * header note) and is shared by both tables, as the ROM's two `adda.w d0` are.
 */
static void mfp_timer_keep_bits(const uint8_t *image, uint32_t offsets, uint32_t masks,
                                uint32_t index)
{
    uint32_t reg = MFP_GPIP + image[addr_add(offsets, index)];

    mfp_keep_bits(reg, image[addr_add(masks, index)]);
}

void mfp_timer_clear(const uint8_t *image, uint16_t timer)
{
    uint32_t index = word_index(timer, 1);

    mfp_timer_keep_bits(image, MFP_TIMER_IMR_OFFSETS, MFP_TIMER_INTERRUPT_MASKS, index);
    mfp_timer_keep_bits(image, MFP_TIMER_IER_OFFSETS, MFP_TIMER_INTERRUPT_MASKS, index);
    mfp_timer_keep_bits(image, MFP_TIMER_IPR_OFFSETS, MFP_TIMER_INTERRUPT_MASKS, index);
    mfp_timer_keep_bits(image, MFP_TIMER_ISR_OFFSETS, MFP_TIMER_INTERRUPT_MASKS, index);
    mfp_timer_keep_bits(image, MFP_TIMER_CONTROL_OFFSETS, MFP_TIMER_CONTROL_MASKS, index);
}

void mfp_timer_program(const uint8_t *image, uint16_t timer, uint16_t control, uint16_t data)
{
    mfp_timer_clear(image, timer);
    (void)control;      /* ...which the ROM ORs into the control register after the data write */
    (void)data;         /* ...and which it writes and re-reads until the 68901 agrees */
    recreate_not_reconstructed("mfp_timer_program: the timer data register is written and read back "
                               "until it sticks ($fc260e), which the declared I/O map cannot serve "
                               "— see the header of src/xbios/xbtimer.c");
}

/* XBIOS $1f — program one of the four MFP timers and, unless the vector argument is negative,
 * install a handler on the interrupt channel that timer raises.
 *
 * The channel comes out of a four-byte ROM table (`$fc302a`: 13, 8, 5, 4 for timers A..D), read with
 * the timer masked to a BYTE — `andi.l #255,d0` — rather than to the two bits four timers need, so
 * the table read is as unbounded as the programmer's.
 *
 * AND THE BYTE IT READS IS NEVER MASKED AGAIN. `bsr.w $fc2666` enters `Mfpint` at its `movem.l` —
 * PAST the `andi.l #15,d0` at `$fc2660` — so the whole byte is the channel: a timer of 4 reads
 * `$fc302e`, the first byte of the `tst.l 10(sp)` that follows the table, and installs the handler
 * on "channel $4a". Two things follow, and neither is what masking would have given. The vector slot
 * is `$100 + $4a * 4` = `$228`, which is exception vector $8a and not one of the MFP's sixteen. And
 * the half-select at `$fc26e6` is a SIGNED byte compare (`include/mfp.h`), so a byte of $80 or more
 * is negative and takes the B register's arm where masking would have left it in A's. Reproduced by
 * calling the body rather than the door: `mfp_install_vector_and_enable`, not `xbios_mfpint`.
 */

/* `$fc3008` to `$fc3028` — the vector arm on its own, because it is the part a case can REACH.
 *
 * Nothing entered at `xbios_xbtimer` gets here on either side: the programmer above halts our build
 * and refuses the oracle's run, so a case that called the whole routine would prove nothing about
 * these five instructions. Split out, the table read and the unmasked entry are a unit a
 * candidate-only case can run — `test_xbios_xbtimer.py`'s raw-byte cases, which say in as many
 * words which side they are about.
 *
 * The result is the D0 the ROM leaves, and it differs by ARM: the negative-vector arm returns
 * through `$fc3028` with the timer still in D0 (the programmer restores it with its own `movem`),
 * and the install arm returns what `Mfpint`'s body left, which is the raw channel byte.
 */
uint32_t xbtimer_install_handler(uint8_t *image, uint16_t timer, uint32_t vector)
{
    unsigned channel;

    if (keeps_current_value_long(vector))
        return timer;
    channel = image[addr_add(XBTIMER_CHANNEL_TABLE, word_index(timer & XBTIMER_TIMER_MASK, 1))];
    return mfp_install_vector_and_enable(image, channel, vector);
}

uint32_t xbios_xbtimer(uint8_t *image, uint16_t timer, uint16_t control, uint16_t data,
                       uint32_t vector)
{
    mfp_timer_program(image, timer, control, data);     /* does not return: see above */
    return xbtimer_install_handler(image, timer, vector);
}
