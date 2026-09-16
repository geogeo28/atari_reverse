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
 * ---- THE WRITE-AND-VERIFY LOOP, AND WHY IT RUNS -------------------------------------------------
 *
 * `.st` above is a WRITE FOLLOWED BY A READ OF THE SAME REGISTER: the 68901 needs a settling time on
 * its data registers, so the ROM stores the byte and re-reads it until the chip agrees. A declared
 * I/O byte used to be a per-run CONSTANT describing what a register held on ENTRY, so a read-back of
 * a byte the run itself stored was refused outright — measured on this routine at `$fffa1f` for
 * `Xbtimer(timer A)` and `$fffa25` for `Rsconf`'s baud arm — and undeclared the loop never
 * terminated at all. `mfp_timer_program` HALTED there, and with it both of its callers.
 *
 * IT RUNS NOW BECAUSE THE CASE DECLARES THE REGISTER WRITE-THROUGH (TRAP_MODEL.md, Phase 15, "The
 * write-through arm"): a store to a marked address replaces the byte later reads are served, on both
 * shores, so the compare comes true on the first pass and the ledger carries exactly one read —
 * which is what pins this loop's SHAPE to the ROM's rather than merely its effect.
 *
 * AND THE CLAIM IS TRUE HERE FOR A REASON THE ROUTINE'S OWN ORDER GIVES. A timer's data register is
 * a RELOAD LATCH while the timer is stopped and the live down-counter while it runs — so a
 * read-back is the store only in the first case. The five clears run FIRST, and the fifth clears the
 * timer's own field of its control register ($00 for A and B, which own a byte each; $8f and $f8 for
 * C and D, which share `$fffa1d`) — a control field of zero is a STOPPED timer on the 68901. So the
 * data register this loop writes is a latch by the time it is written. `test_xbios_xbtimer.py` pins
 * that order, and `test/mfp.py` carries the claim register by register.
 *
 * The `or.b d1,(a3)` that follows re-reads the CONTROL register the same clear had just written,
 * which is a latch outright — the same arm serves it.
 *
 * THE OFF-TARGET BUILD CAPS THE LOOP; THE TARGET ONE DOES NOT, and that costs the differential
 * nothing. What the harness compares is the LEDGER, and on a correct run the ledger is one store and
 * one read on both shores — the cap is never reached, so nothing it could change is looked at. What
 * it buys is the failure mode: a mutation that mis-addresses the register makes the loop never
 * agree, which on target is the ROM's own hang and off target used to be a HUNG pytest worker rather
 * than a red. `MFP_VERIFY_PASSES` below turns that into a refusal.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "mfp.h"
#include "addrs.h"

#ifndef __m68k__
#include "os.h"        /* os_refused — the host-only pass cap on the verify loop; see the header */

/* How many times the OFF-TARGET build writes and re-reads the data register before it gives up.
 *
 * BOUNDED, WHERE THE ROM'S IS NOT, and the split is `tools/recreate_kit/test/kit_candidate.c`'s
 * KIT_VERIFY_PASSES verbatim: the 68000 side spins forever if the register does not latch, which is
 * what the oracle's instruction cap is for, while this side is C running inside pytest and a
 * mis-addressed register HANGS THE SUITE instead of reddening it — measured on this very routine
 * (STATUS.md's mutation row for `$fc25b0`). A correct run never reaches the cap: the register is a
 * stopped timer's reload latch and the write-through arm answers on the first pass, which
 * `test_the_data_register_is_written_and_then_read_back_exactly_once` pins on the LEDGER. So the cap
 * changes nothing the differential claims — the ledger it compares is one store and one read either
 * way, and the only run that can tell the two builds apart is one this side refuses outright. */
#define MFP_VERIFY_PASSES 8
#endif

/* `$fc262a` — which MFP register one of the routine's tables names for this timer: `adda.w d0,a3`,
 * `move.b (a3),d3`, `add.l a0,d3`. The offsets are displacements off `$fffa01`, and the index is the
 * sign-extended timer (see the header note), so the routine is as unbounded in its timer as the ROM.
 */
static uint32_t mfp_timer_select_register(const uint8_t *image, uint32_t offsets, uint32_t index)
{
    return MFP_GPIP + image[addr_add(offsets, index)];
}

/* One of the programmer's five clears: `bsr $fc2622` with `a3` an offset table and `a2` a mask one.
 *
 * `image` is the ROM's own tables, which live in it; `index` is the sign-extended timer and is
 * shared by both tables, as the ROM's two `adda.w d0` are.
 */
static void mfp_timer_keep_bits(const uint8_t *image, uint32_t offsets, uint32_t masks,
                                uint32_t index)
{
    mfp_keep_bits(mfp_timer_select_register(image, offsets, index), image[addr_add(masks, index)]);
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
    uint32_t index = word_index(timer, 1);
    uint32_t control_register, data_register;

    mfp_timer_clear(image, timer);        /* ...whose fifth clear STOPS the timer: see the header */
    control_register = mfp_timer_select_register(image, MFP_TIMER_CONTROL_OFFSETS, index);
    data_register = mfp_timer_select_register(image, MFP_TIMER_DATA_OFFSETS, index);

    /* `.st: move.b d2,(a0,d3.w) / cmp.b (a0,d3.w),d2 / bne.s .st` — store the reload byte and read
     * it back until the 68901 agrees, which is the settling time the chip needs. One pass is what a
     * stopped timer's latch produces; a case that declared the register a per-run CONSTANT would
     * spin here, and its ORACLE would already have died at the instruction cap before this side was
     * armed.
     *
     * ON TARGET the ROM's own unbounded spin, because that is the program the machine runs. Off
     * target it is capped and the cap is a REFUSAL — see MFP_VERIFY_PASSES above for why the two
     * builds are still the same claim. */
#ifdef __m68k__
    do {
        hw_write8(data_register, (uint8_t)data);
    } while (io_read8(data_register) != (uint8_t)data);
#else
    unsigned pass;

    for (pass = 0; pass < MFP_VERIFY_PASSES; pass++) {
        hw_write8(data_register, (uint8_t)data);
        if (io_read8(data_register) == (uint8_t)data)
            break;
    }
    if (pass == MFP_VERIFY_PASSES)
        os_refused(0);      /* the register never agreed: throw the case away rather than spin */
#endif

    /* `or.b d1,(a3)` — the control bits LAST, into the register the clear above emptied. For timers
     * C and D that byte is shared, so this must OR rather than store: the other timer's field is in
     * the five bits the clear kept. */
    mfp_set_bits(control_register, (uint8_t)control);
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

/* `$fc3008` to `$fc3028` — the vector arm on its own, because it is a unit worth driving directly.
 *
 * It is `Xbtimer`'s second half and nothing else calls it, but the two table reads it makes are
 * unbounded (see above) and a case that wants a timer past the four has no way to reach the
 * arithmetic through the whole routine without also programming a timer that does not exist. Split
 * out, the table read and the unmasked entry into `Mfpint`'s body are one call a battery drives at
 * every byte the table can produce.
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
    mfp_timer_program(image, timer, control, data);
    return xbtimer_install_handler(image, timer, vector);
}
