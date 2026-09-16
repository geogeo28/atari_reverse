/* XBIOS Ikbdws ($19) — $fc2212, and Midiws ($0c) — $fc2030: bytes out of the two 6850 ACIAs.
 *
 * One shape, twice, with two ports and one difference:
 *
 *   Ikbdws / Midiws:                        $fc21f2 (IKBD) / $fc201a (MIDI), byte in D1:
 *      moveq   #0,d3                           lea     $fffffc00,a1     ; $fffffc04 for MIDI
 *      move.w  4(sp),d3    ; count         .p: move.b  (a1),d2          ; the status register
 *      movea.l 6(sp),a2    ; the bytes         btst    #1,d2            ; TDRE
 *   .b:                                        beq.s   .p
 *      move.b  (a2)+,d1                        move.w  #950,d2          ; IKBD ONLY:
 *      bsr.s   <the sender>               .d:   bsr.s   .rts            ;   951 iterations of
 *      dbf     d3,.b                            dbf     d2,.d           ;   `bsr`+`rts`+`dbf`
 *      rts                                     move.b  d1,2(a1)         ; the data port
 *                                          .rts: rts
 *
 * `count + 1` BYTES, not `count`, and the `+ 1` is `dbf`'s: the loop body runs before the test, so a
 * count of 0 sends one byte. The count is a WORD zero-extended by the `moveq` above it, so a count
 * of `$ffff` is 65,536 bytes rather than none — TOS's own callers pass `n - 1`, and this is the
 * routine, not the convention.
 *
 * THE STATUS POLL IS A LOOP THE MODEL CAN ONLY RUN ONE WAY ROUND. `$fffc00` is one of the seeded
 * hardware model's NAMED slots (os.h, `OS_HW_ACIA_STATUS`) and `$fffc04` is an ordinary declared I/O
 * byte; either way the declaration is a per-RUN CONSTANT, so a case that declares TDRE set leaves
 * the loop on its first read and a case that declares it clear hangs BOTH sides identically. What
 * cannot be expressed today is the interesting sequence — not ready, then ready — because that needs
 * two different bytes out of one address in one run, which is the shape os.h calls out as beyond a
 * constant. So what these cases prove of the poll is that it HAPPENS, in order, once per byte, at
 * the right port: the read ledgers are compared entry for entry, and a reconstruction that dropped
 * the poll or polled the wrong ACIA reds there rather than on any image byte.
 *
 * THE IKBD's SETTLING DELAY IS REPRODUCED, AND ON TARGET IT IS THE ROM'S OWN SHAPE. The 951
 * iterations between the poll and the store are pure delay — no memory, no I/O, a `bsr` to an
 * `rts` — and they are there because the 6301 needs the gap; the MIDI sender has none. What the
 * keyboard controller is owed is ELAPSED TIME, so the delay is a FLOOR and not a count: a
 * reconstruction that made the same 951 passes more cheaply would leave the 6301 short of it. That
 * is what a counted C loop does — measured at 0.86 of the original, a seventh of the gap missing —
 * so the target build spells the loop as the ROM's `bsr`-to-an-`rts` under `dbf`, 44 cycles a pass,
 * and the host keeps the counter. The split is on `__m68k__` rather than on the differential's own
 * macro, exactly as `src/bios/vbl.c`'s shifter delay is: it is a question about the TARGET's
 * instruction set and not about which harness is looking.
 *
 * ITS ONLY SURFACE IS TIER 3. The loop touches no memory, no compared register and no chip, so
 * deleting it outright leaves every Tier 1 case green; what says it is there — and what says it is
 * the right LENGTH — is the measured cycle ratio `bench/tier3.py` pins for `xbios_ikbdws`.
 *
 * THE DATA PORTS ARE WRITES AND NOTHING READS THEM BACK, so the whole of what each byte leaves
 * behind is the ordered hardware WRITE ledger (TRAP_MODEL.md, Phase 10) — address, width and value,
 * compared entry by entry. A reconstruction that sent the bytes in the wrong order, sent one twice,
 * or sent them to the MIDI port would be byte-for-byte identical in memory.
 */
#include <stdint.h>

#include "hw.h"
#include "ikbd.h"
#include "machine.h"
#include "addrs.h"

/* `move.w #950,d2 / bsr .rts / dbf d2` — 951 iterations of nothing, between the IKBD's status poll
 * and its data store. See the header: it is a settling time the 6301 needs, spelt as the ROM's own
 * three instructions on target so the gap is the gap the machine got.
 *
 * `dbf` exits at -1, so the register holds one FEWER than the passes it makes — which is why the
 * immediate is `IKBD_SETTLE_ITERATIONS - 1` and not a second constant beside it. The `bsr` reaches
 * an `rts` the loop then has to jump over; that one `bra.s` is the only instruction here the ROM
 * does not make, and it runs once against the loop's 951 passes. */
static void ikbd_settle(void)
{
#ifdef __m68k__
    uint16_t remaining;

    __asm__ volatile ("      move.w  %[count],%[remaining]\n\t"
                      "0:    bsr.s   1f\n\t"
                      "      dbf     %[remaining],0b\n\t"
                      "      bra.s   2f\n"
                      "1:    rts\n"
                      "2:"
                      : [remaining] "=&d" (remaining)
                      : [count] "i" (IKBD_SETTLE_ITERATIONS - 1)
                      : "cc", "memory");
#else
    for (volatile uint16_t remaining = IKBD_SETTLE_ITERATIONS; remaining != 0; remaining--)
        ;
#endif
}

void ikbd_send_byte(uint8_t byte)
{
    while ((hw_read8(IKBD_ACIA_STATUS) & ACIA_TRANSMIT_READY) == 0)
        ;
    ikbd_settle();
    hw_write8(IKBD_ACIA_DATA, byte);
}

/* ...and the MIDI 6850's, which has no settling delay. Its status register is not one of the seeded
 * model's named slots, so it comes through the DECLARED I/O MAP instead (`io_read8`); both are
 * ledgered and compared, in their own stream. */
static void midi_send_byte(uint8_t byte)
{
    while ((io_read8(MIDI_ACIA_STATUS) & ACIA_TRANSMIT_READY) == 0)
        ;
    hw_write8(MIDI_ACIA_DATA, byte);
}

/* `$fc221c` / `$fc203a` — the send loop both routines are, with the ONE thing that differs between
 * them as its argument: which `bsr` the ROM makes per byte. */
static void acia_send_string(const uint8_t *image, uint16_t count, uint32_t at,
                             void (*send_byte)(uint8_t))
{
    uint32_t remaining = (uint32_t)count + 1;       /* `dbf`: the body runs before the test */

    for (uint32_t i = 0; i < remaining; i++)
        send_byte(image[addr_add(at, i)]);
}

void ikbd_send_string(const uint8_t *image, uint16_t count, uint32_t at)
{
    acia_send_string(image, count, at, ikbd_send_byte);
}

/* XBIOS $19 */
void xbios_ikbdws(const uint8_t *image, uint16_t count, uint32_t at)
{
    ikbd_send_string(image, count, at);
}

/* XBIOS $0c */
void xbios_midiws(const uint8_t *image, uint16_t count, uint32_t at)
{
    acia_send_string(image, count, at, midi_send_byte);
}
