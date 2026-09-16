/* mfp.h — the MFP 68901's register arithmetic, and the one door a reconstruction changes a bit of
 * one of its registers through.
 *
 * Three ROM routines share it verbatim — `Jdisint`, `Jenabint` and the timer programmer the ROM
 * calls out of both `Xbtimer` and `Rsconf` — so it is spelt once here rather than three times in
 * three cores. What makes it worth a header rather than a copy is that every one of these shapes is
 * a thing a reconstruction gets WRONG by writing the obvious C (`m68k_idioms.h` says the same of
 * the two shapes it carries).
 *
 * THE CHIP'S REGISTERS ARE PAIRS. Its sixteen interrupt channels live in two eight-bit halves — an
 * "A" register holding channels 8..15 and a "B" register two bytes above it holding channels 0..7 —
 * and enable, pending, in-service and mask are four such pairs. The ROM spells the split ONCE, in a
 * four-instruction subroutine at `$fc26e6` that takes the channel in D0 and the A register in A1:
 *
 *      move.b  d0,d1
 *      cmpi.b  #8,d1
 *      blt.s   .low
 *        subq.w  #8,d1       ; 8..15: bit = channel - 8, and A1 already names the A register
 *        rts
 *   .low:
 *      addq.l  #2,a1         ; 0..7:  bit = channel, and the B register is two bytes up
 *      rts
 *
 * `mfp_channel_register` and `mfp_channel_bit` below are that subroutine, split into its two answers.
 *
 * AND IT IS A SIGNED BYTE COMPARE, WHICH MATTERS FOR EXACTLY ONE CALLER. `cmpi.b #8,d1` / `blt.s`
 * reads D1's low byte as an `int8_t`, so a channel of $8a — which no masked entry can produce, since
 * `andi.l #15` bounds all three of them to 0..15 — is NEGATIVE and takes the B register's arm. The
 * caller that can produce one is `Xbtimer`: it `bsr`s into `Mfpint`'s body PAST that mask ($fc3024 ->
 * $fc2666) with the RAW byte it read out of `$fc302a`, and that table is only four bytes long
 * (`src/xbios/xbtimer.c`). The bit is then `bclr d1,(a1)`'s, which on a MEMORY destination is modulo
 * 8 — `MFP_BIT_NUMBER_MASK` — and the `subq.w #8` never borrows into the bits that mask keeps,
 * because the arm that subtracts is reached only for a byte of 8..127. Over 0..15 all of this is the
 * plain unsigned reading, which is why every case at `Jdisint`'s own entry says the same either way.
 *
 * A BIT CHANGE IS A READ AND A STORE, AND BOTH HALVES ARE COMPARED. The ROM's instruction is
 * `bclr d1,(a1)` / `bset d1,(a1)`, which on the 68000 is a byte read of the register followed by a
 * byte store of the modified value. `hw.h` offers `hw_bclr8`/`hw_bset8` for that shape, and they are
 * DELIBERATELY NOT what these use: those exist for a register the seeded read model does not name,
 * where the oracle's own read answers a fabricated 0 — so what they can pin is the address and the
 * fact of the store, while the five bits the instruction PRESERVES stay unpinned. That header names
 * the remedy in as many words: "a routine that needs the mask held wants a sink of its own, or the
 * address in the READ model". The DECLARED I/O MAP is that read model (TRAP_MODEL.md, Phase 15), and
 * an MFP register is declarable in it — so a case says what the chip held, the read is served and
 * ledgered on both sides, and the byte stored is a function of it. A reconstruction that cleared the
 * wrong bit, or that cleared the whole byte, then reds on the write ledger's VALUE rather than
 * passing on a zero both sides invented.
 *
 * ON TARGET this is two bus accesses where the ROM makes one instruction, and they are the same two
 * the instruction itself makes: `bclr` reads the register and writes it back. What the target build
 * supplies is `io_read8` and `hw_write8` as the real volatile accesses (`atari/shim_include/hw.h`).
 *
 * WHAT A WRITE-THROUGH DECLARATION SAYS, and it is what makes the re-reading routines runnable at
 * all: a case may declare a register one whose store the chip LATCHES and reads back (TRAP_MODEL.md,
 * Phase 15, "The write-through arm"), and every register this header changes a bit of is one — the
 * interrupt MASK and ENABLE pairs, the timer CONTROL registers, and a STOPPED timer's data register.
 * So `Mfpint`'s enable half is served the IERA its disable half cleared a bit of, and the timer
 * programmer's write-and-verify loop terminates because the register really holds what it stored.
 * `test/mfp.py` carries the claim register by register, including the two pairs it makes only on a
 * narrower reading: PENDING and IN-SERVICE are write-to-clear rather than latches, and they read
 * back what was stored because every store these routines make is `read & mask`, a pure clear.
 */
#ifndef TOS102US_MFP_H
#define TOS102US_MFP_H

#include <stdint.h>

#include "hw.h"
#include "addrs.h"

/* `move.b d0,d1` / `cmpi.b #8,d1` / `blt.s` — the half-select's test, as the SIGNED byte compare it
 * is (see the header note, and `MFP_BIT_NUMBER_MASK` in addrs.h for the bound it puts on the bit). */
static inline int mfp_channel_is_in_register_a(unsigned channel)
{
    return (int8_t)(uint8_t)channel >= (int8_t)MFP_CHANNELS_PER_HALF;
}

/* Which of a register PAIR a channel lives in, given the pair's "A" half. */
static inline uint32_t mfp_channel_register(uint32_t register_a, unsigned channel)
{
    return mfp_channel_is_in_register_a(channel) ? register_a : register_a + MFP_HALF_B_STEP;
}

/* ...and which bit of it. */
static inline unsigned mfp_channel_bit(unsigned channel)
{
    unsigned bit = mfp_channel_is_in_register_a(channel) ? channel - MFP_CHANNELS_PER_HALF : channel;

    return bit & MFP_BIT_NUMBER_MASK;
}

/* `bclr d1,(a1)` on a declared MFP register — see the header note on why not `hw_bclr8`. */
static inline void mfp_clear_bit(uint32_t reg, unsigned bit)
{
    hw_write8(reg, (uint8_t)(io_read8(reg) & ~(1u << bit)));
}

/* ...and `bset d1,(a1)`. */
static inline void mfp_set_bit(uint32_t reg, unsigned bit)
{
    hw_write8(reg, (uint8_t)(io_read8(reg) | (1u << bit)));
}

/* ...and `and.b d3,(a3)`, the timer programmer's shape: keep the bits `mask` names. */
static inline void mfp_keep_bits(uint32_t reg, uint8_t mask)
{
    hw_write8(reg, (uint8_t)(io_read8(reg) & mask));
}

/* ...and `or.b d1,(a3)`, the same programmer's last instruction: put the caller's bits in without
 * disturbing the rest — which for timers C and D is the OTHER timer's field in the byte they share.
 * It re-reads a register the routine has already written, so it runs only because the case declares
 * the control registers WRITE-THROUGH (`test/mfp.py` carries that claim). */
static inline void mfp_set_bits(uint32_t reg, uint8_t bits)
{
    hw_write8(reg, (uint8_t)(io_read8(reg) | bits));
}

/* One channel's bit, in whichever half of the pair holds it: `bclr`/`bset` at the channel level. */
static inline void mfp_clear_channel_bit(uint32_t register_a, unsigned channel)
{
    mfp_clear_bit(mfp_channel_register(register_a, channel), mfp_channel_bit(channel));
}

static inline void mfp_set_channel_bit(uint32_t register_a, unsigned channel)
{
    mfp_set_bit(mfp_channel_register(register_a, channel), mfp_channel_bit(channel));
}

/* ---- the cores, for the two files that call each other's ($fc2666 and $fc296c are ROM `bsr`s) ---- */

/* XBIOS $1a / $1b — one MFP interrupt channel off and on (`src/xbios/mfp.c`). Each returns the
 * MASKED channel, which is the D0 its `movem.l (sp)+` restores — see that file. */
uint32_t xbios_jdisint(uint16_t channel_argument);
uint32_t xbios_jenabint(uint16_t channel_argument);

/* ...and the two ROM BODIES those doors are the argument fetch of, at `$fc268c` and `$fc26c6`. They
 * take a channel that has already been selected, because the two callers that enter here have each
 * selected one their own way: the doors above by `andi.l #15,d0`, and `Xbtimer` by a table read the
 * ROM never masks at all. */
void mfp_disable_channel(unsigned channel);
void mfp_enable_channel(unsigned channel);

/* ...and the disable-then-store half of `Mfpint`, which is the part a differential can run whole:
 * `[$fc2658, $fc267a)`, up to the `bsr` into `Jenabint`'s body (`src/xbios/mfp.c` says why). Its
 * argument is `Mfpint`'s own, so it masks as `Mfpint`'s entry does. */
void mfp_install_vector(uint8_t *image, uint16_t channel_argument, uint32_t handler);

/* `$fc2666` — `Mfpint`'s WHOLE body, entered past its argument fetch: the disable, the vector store
 * and the enable, over a channel the caller selected. This is what `Xbtimer`'s `bsr.w` at `$fc3024`
 * reaches, with the raw byte out of `$fc302a` (`src/xbios/xbtimer.c`). */
uint32_t mfp_install_vector_and_enable(uint8_t *image, unsigned channel, uint32_t handler);

/* XBIOS $0d — ...and the door onto it, which masks first. */
uint32_t xbios_mfpint(uint8_t *image, uint16_t channel_argument, uint32_t handler);

/* The four interrupt-register pairs and the control register, cleared for one timer — the first
 * five sixths of the ROM's shared timer programmer at `$fc25b0` (`src/xbios/xbtimer.c`). Still its
 * own entry point because it is the slice `[$fc25b0, $fc2600)` a battery drives on its own, and
 * because clearing the control register is what STOPS the timer the rest of the routine programs.
 * `image` is the ROM's own offset and mask tables, which the routine indexes by timer. */
void mfp_timer_clear(const uint8_t *image, uint16_t timer);

/* ...and the whole of that routine, which `Xbtimer` and `Rsconf`'s baud arm both call: the five
 * clears, the data register written and re-read until the 68901 agrees, and the control bits ORed
 * in last. */
void mfp_timer_program(const uint8_t *image, uint16_t timer, uint16_t control, uint16_t data);

#endif /* TOS102US_MFP_H */
