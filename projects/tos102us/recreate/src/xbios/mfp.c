/* XBIOS Jdisint ($1a) — $fc2682, Jenabint ($1b) — $fc26bc, Mfpint ($0d) — $fc2658.
 *
 * The three doors TOS offers onto the MFP 68901's interrupt controller. They are one body in the
 * ROM, entered at three points and falling through each other:
 *
 *   Mfpint:                              Jdisint:
 *      move.w  4(sp),d0                     move.w  4(sp),d0
 *      movea.l 6(sp),a2                     andi.l  #15,d0
 *      andi.l  #15,d0                    $fc268c:                       <- Mfpint's first bsr
 *      movem.l d0-d2/a0-a2,-(sp)            movem.l d0-d1/a0-a1,-(sp)
 *      bsr.s   $fc268c   ; disable          lea     $fffffa01,a0
 *      move.l  d0,d2                        lea     18(a0),a1   ; IMRA
 *      asl.w   #2,d2                        bsr.s   $fc26e6     ; which half, which bit
 *      addi.l  #256,d2                      bclr    d1,(a1)
 *      movea.l d2,a1                        lea     6(a0),a1    ; IERA ... and so on for
 *      move.l  a2,(a1)   ; the vector       bsr.s   $fc26e6     ; IPRA ($fc26a6) and ISRA ($fc26ae)
 *      bsr.s   $fc26c6   ; enable           bclr    d1,(a1)
 *      movem.l (sp)+,d0-d2/a0-a2            movem.l (sp)+,d0-d1/a0-a1
 *      rts                                  rts
 *
 *   Jenabint:
 *      move.w  4(sp),d0
 *      andi.l  #15,d0
 *   $fc26c6:                                <- Mfpint's second bsr
 *      movem.l d0-d1/a0-a1,-(sp)
 *      lea     $fffffa01,a0
 *      lea     6(a0),a1    ; IERA
 *      bsr.s   $fc26e6
 *      bset    d1,(a1)
 *      lea     18(a0),a1   ; IMRA
 *      bsr.s   $fc26e6
 *      bset    d1,(a1)
 *      movem.l (sp)+,d0-d1/a0-a1
 *      rts
 *
 * SO `Mfpint` IS LITERALLY `Jdisint`'s BODY, a vector store, AND `Jenabint`'s BODY — it `bsr`s into
 * each of them at the instruction after their own argument fetch. The C says the same thing by
 * calling them, and that is a claim the ROM's own control flow makes rather than a convenience.
 *
 * THE ORDER IS THE BEHAVIOUR, TWICE OVER. Disabling goes MASK, ENABLE, PENDING, IN-SERVICE: the
 * channel is masked off before its enable bit is cleared, so no interrupt can be latched in the
 * window, and only then are a pending request and an in-service acknowledgement thrown away.
 * Enabling goes the other way — ENABLE first, MASK second — so the channel is armed before it is
 * unmasked. A reconstruction that wrote either list in any other order leaves the same four
 * registers holding the same four bytes at the end, and is a different program on a live machine;
 * what separates the two here is the ORDERED hardware write ledger (TRAP_MODEL.md, Phase 10), which
 * the differential compares entry by entry.
 *
 * NEITHER ROUTINE BOUNDS ITS ARGUMENT AND NEITHER NEEDS TO: `andi.l #15,d0` takes four bits, so
 * every one of the 65,536 words a caller can pass names one of the sixteen channels. Channel 13 and
 * channel $fffd are the same call.
 *
 * ...AND THAT MASK IS ALSO THE RESULT. All three push D0 with the `movem.l` that follows the `andi`
 * and restore it with the `movem.l (sp)+` before the `rts`, so the D0 a caller gets back is the
 * MASKED CHANNEL and not the word it passed — `Jdisint($fffd)` returns 13. Nothing in TOS reads it,
 * but it is the register the routine leaves and `case.FULL_D0` compares the whole of it, so the C
 * returns it rather than being `void` and agreeing with a reconstruction that cleared it.
 *
 * WHAT THE DIFFERENTIAL PROVES OF `Mfpint`, AND WHAT IT DOES NOT. `Jdisint` and `Jenabint` are
 * proved whole, at their own entries. `Mfpint` is proved as a SLICE — `[$fc2658, $fc267a)`, the
 * argument fetch, the disable and the vector store — because the run cannot be carried past it: the
 * enable half RE-READS `IERA` and `IMRA`, which the disable half has already STORED to, and the
 * declared I/O map describes the byte a register held on ENTRY. The oracle counts that as a stale
 * read and `harness._vet_io_reads_are_declared` refuses the case (measured: two stale reads, the
 * first at `$fffa07`). What would unblock it is a WRITE-THROUGH arm of that map — a declared byte
 * the run's own store updates — which is a change to the kit rather than to this core. Until then
 * the enable half is pinned where the ROM itself puts it: at `$fc26c6`, inside `Jenabint`, whose own
 * case runs it over the same registers.
 */
#include <stdint.h>

#include "machine.h"
#include "mfp.h"
#include "addrs.h"

/* `$fc268c` — `Jdisint`'s body: disable one MFP channel and forget any request it had outstanding. */
void mfp_disable_channel(unsigned channel)
{
    mfp_clear_channel_bit(MFP_IMRA, channel);    /* mask first: nothing can be latched after this */
    mfp_clear_channel_bit(MFP_IERA, channel);
    mfp_clear_channel_bit(MFP_IPRA, channel);    /* ...then throw away a request already pending */
    mfp_clear_channel_bit(MFP_ISRA, channel);    /* ...and an acknowledgement still in service */
}

/* `$fc26c6` — `Jenabint`'s body: arm one MFP channel, then unmask it. */
void mfp_enable_channel(unsigned channel)
{
    mfp_set_channel_bit(MFP_IERA, channel);
    mfp_set_channel_bit(MFP_IMRA, channel);
}

/* XBIOS $1a — the door onto the first of those: the argument fetch, and then the body. */
uint32_t xbios_jdisint(uint16_t channel_argument)
{
    unsigned channel = channel_argument & MFP_CHANNEL_MASK;

    mfp_disable_channel(channel);
    return channel;
}

/* XBIOS $1b — ...and onto the second. */
uint32_t xbios_jenabint(uint16_t channel_argument)
{
    unsigned channel = channel_argument & MFP_CHANNEL_MASK;

    mfp_enable_channel(channel);
    return channel;
}

/* XBIOS $0d — install `handler` as one MFP channel's interrupt vector, around a disable/enable.
 *
 * IT IS SPLIT IN TWO AT THE SLICE BOUNDARY, and `mfp_install_vector` is the half a case can run:
 * disable the channel, then replace its vector while it is off — which is the reason the disable is
 * there at all, and a whole operation rather than a fragment. `xbios_mfpint` is that plus the
 * enable, and the enable is `Jenabint`, proved at its own entry.
 *
 * The vector table is the 68000's, at $100: the MFP's base vector register holds $40, so its sixteen
 * channels are exception vectors $40..$4f and their longwords are `$100 + channel * 4`. The ROM
 * computes that with `asl.w #2` inside a WORD, which is `m68k_idioms.h`'s wrapping shape — but the
 * channel is at most a BYTE (`Mfpint`'s own entry masks it to four bits, and the one caller that
 * enters past that mask has read it out of a table, so `move.b` bounds it to 255), the product is at
 * most 1020, and the wrap the shape would otherwise have is unreachable. Nothing here is a
 * `word_index`.
 */
static void install_vector(uint8_t *image, unsigned channel, uint32_t handler)
{
    mfp_disable_channel(channel);         /* the channel is off while its vector is replaced */
    wr32(image + MFP_VECTOR_TABLE + channel * VECTOR_BYTES, handler);
}

void mfp_install_vector(uint8_t *image, uint16_t channel_argument, uint32_t handler)
{
    install_vector(image, channel_argument & MFP_CHANNEL_MASK, handler);
}

uint32_t mfp_install_vector_and_enable(uint8_t *image, unsigned channel, uint32_t handler)
{
    install_vector(image, channel, handler);
    mfp_enable_channel(channel);
    return channel;
}

uint32_t xbios_mfpint(uint8_t *image, uint16_t channel_argument, uint32_t handler)
{
    return mfp_install_vector_and_enable(image, channel_argument & MFP_CHANNEL_MASK, handler);
}
