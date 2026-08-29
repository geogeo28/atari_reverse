/* zynaps_backend.c — the seam's target half: every symbol the differential harness MODELLED, done
 * for real on the machine.
 *
 * Off target these live in translation units this build leaves out — `tools/recreate_kit/src/psg.c`
 * (the YM2149's ordered write ledger) and `../src/irq_hw_offtarget.c` (the shifter and MFP stores
 * the interrupt handlers make). Both files say in their own headers that a build for the real Atari
 * does not compile them and writes the ports itself. This is that file. `README.md`'s seam table is
 * the inventory; this is the code.
 *
 * WHAT MAKES IT SAFE TO SUBSTITUTE. Each routine below has the same signature and the same CALL
 * SITES as the modelled one, so the cores are compiled unchanged and the differential .so is
 * untouched — `make test` is still 2700 (build.sh checks that no core mentions a name from this
 * file). What changes is only what the write lands on: an ordered ledger off target, a device
 * register here.
 *
 * ...AND WHAT DOES NOT MAKE IT SAFE. A seam prices what the substituted code RETURNS, not what it
 * did to shared state on the way (docs/on-target-execution.md class 11). Everything here is
 * write-only to a device and reads nothing back, so there is no protocol under it to drop — which
 * is worth stating rather than assuming, and is the reason `hw_read8` is deliberately NOT defined
 * here: no Zynaps core calls it (measured), and a stub would be a fabricated machine byte.
 *
 * EVERY HARDWARE ADDRESS IS IN THE 24-BIT-BUS FORM ($ffff8800, not $ff8800). The 68000 aliases the
 * two, and the kit's headers spell the SHORT form because that is what a reconstruction's constant
 * says; a C pointer has to name the address the CPU will actually put on the bus.
 */
#include <stdint.h>

#include "hw.h"
#include "machine.h"
#include "os.h"
#include "psg.h"

#include "irq.h"
#include "zynaps_target.h"

/* ================================================================================================
 * THE HARDWARE STORE, IN ONE PLACE. shim_include/hw.h declares the three and says why they carry
 * the KIT'S future names rather than names of this project's own.
 * ============================================================================================= */
volatile uint32_t zy_hw_writes;

void hw_write8(uint32_t addr, uint8_t value) {
    *(volatile uint8_t *)addr = value;
    zy_hw_writes++;
}

void hw_write16(uint32_t addr, uint16_t value) {
    *(volatile uint16_t *)addr = value;
    zy_hw_writes++;
}

void hw_write32(uint32_t addr, uint32_t value) {
    *(volatile uint32_t *)addr = value;
    zy_hw_writes++;
}

/* ================================================================================================
 * The shifter and the MFP — `../src/irq_hw_offtarget.c`'s three empty bodies, for real.
 * ============================================================================================= */

/* `HW_BUS`, `SHIFTER_PEN_BYTES` and `shifter_pen_register` are shim_include/zynaps_target.h's —
 * both shim translation units need them and one definition is what stops the two spellings
 * drifting (CLAUDE.md §5).
 *
 * `movem.l <shadow>,#$00ff / movem.l #$00ff,$ff8240.l` — sixteen colour words, or one for
 * `attract_rasterbar_isr`'s single-pen store. `first_pen` and `pens` are the call site's own
 * arguments, which is what `irq_hw_offtarget.c`'s header means by "the arguments say WHICH pens and
 * WHICH shadow at every call site, so a future ledger has the whole contract already written down".
 *
 * ONE STORE PER PEN, THROUGH A CALL, AND THAT IS DELIBERATE. The obvious spelling — a
 * `volatile uint16_t *` walked over the registers — is the shape that produced the sibling
 * project's worst on-target defect: GCC folded it to `move.w (%a0)+,(%a0,%d0.l)`, and on the 68000
 * a MOVE's DESTINATION effective address is computed AFTER the source's postincrement, so every pen
 * landed one register high and the sixteenth write hit $ff8260 — the RESOLUTION register — and hung
 * the machine (docs/on-target-execution.md class 6). Computing each address as a value and handing
 * it to `hw_write16` cannot produce that instruction, and build.sh greps the linked binary for the
 * shape anyway, because "cannot" is a claim about a compiler. */
void shifter_write_palette(const uint8_t *image, unsigned first_pen, unsigned pens,
                           uint32_t shadow) {
    for (unsigned pen = 0; pen < pens; pen++)
        hw_write16(shifter_pen_register(first_pen + pen),
                   be16(image + shadow + pen * SHIFTER_PEN_BYTES));
}

/* `clr.w $ff8240` — force pen 0 to black for the top of the frame. */
void shifter_clear_pen0(void) {
    hw_write16(shifter_pen_register(0), 0);
}

/* `bclr #0,$fffa0f` — acknowledge Timer B in the MFP's in-service register B.
 *
 * IT IS A READ-MODIFY-WRITE AND NOT A STORE. The MC68901's in-service register is cleared by
 * writing a ZERO to the bit and ONES everywhere else, so a `move.b` of a constant would clear every
 * other in-service channel at the same time. `&= ~bit` is the C that compiles to the `bclr`/`andi`
 * the original uses — which is also why this one does not go through `hw_write8`: that helper
 * writes a value, and what this needs is the read half as well. */
void mfp_ack_timer_b(void) {
    *(volatile uint8_t *)HW_BUS(HW_MFP_ISRB) &= (uint8_t)~(1u << MFP_ISRB_TIMER_B_BIT);
    zy_hw_writes++;
}

/* ================================================================================================
 * The YM2149's two ports — `tools/recreate_kit/src/psg.c`'s off-target ledger, for real.
 *
 * `psg.h`: "Off-target only ... a build for the real Atari writes the ports itself and does not
 * compile src/psg.c." The one caller is `flush_shadow` in ../src/sound.c, which pushes registers
 * 10..0 every vertical blank (and 13..0 from `sound_reset_psg`) — so on target this runs from
 * inside the interrupt, in supervisor mode, which is where $ff8800 is reachable at all.
 * ============================================================================================= */
#define HW_PSG_SELECT HW_BUS(OS_PSG_PORT_SELECT)
#define HW_PSG_DATA   HW_BUS(OS_PSG_PORT_DATA)

/* Writes this build has made, and writes it REFUSED. The kit's `psg_port_write` refuses a register
 * outside 0..15 rather than masking it down, because the ST's select latch decodes four bits and a
 * driver that put anything in the upper nibble meant something the chip does not do. Masking here
 * would leave a mutated driver silently steering a real chip; counting the refusal makes it a
 * number STATE.BIN carries. */
volatile uint32_t zy_psg_writes;
volatile uint32_t zy_psg_refused;

/* ...and the file seam's, declared in shim_include/os.h beside the guards that keep them. Defined
 * HERE rather than in zynaps_main.c because os.h is included by the CORES too: a definition in a
 * header would be one per translation unit, and the counts would be per-file rather than per-run. */
volatile uint32_t zy_file_opens;
volatile uint32_t zy_file_open_failures;
volatile uint32_t zy_file_refusals;

void psg_port_write(unsigned reg, uint8_t value) {
    if (reg >= OS_PSG_NREGS) {
        zy_psg_refused++;
        return;
    }
    /* `move.b <reg>,$ff8800` then `move.b <val>,$ff8802` — the original's own pair, in its order.
     * NOT bracketed by an interrupt mask: the select latch and the data port are two stores with a
     * window between them, and the original leaves that window open. Nothing else in this build
     * writes the chip while the handler runs — the shim's only other PSG traffic is the teardown
     * silence, made after the vertical-blank vector has already been handed back to TOS. */
    hw_write8(HW_PSG_SELECT, (uint8_t)reg);
    hw_write8(HW_PSG_DATA, value);
    zy_psg_writes++;
}

/* ================================================================================================
 * The freestanding libc the cores need. m68k-elf ships none, and `-ffreestanding -nostdlib` is
 * what makes that explicit rather than accidental.
 *
 * `-fno-tree-loop-distribute-patterns` is what stops GCC recognising each of these loops and
 * replacing it with a call to itself.
 * ============================================================================================= */
void *memset(void *dst, int c, unsigned long n) {
    unsigned char *out = dst;

    while (n--)
        *out++ = (unsigned char)c;
    return dst;
}

void *memcpy(void *dst, const void *src, unsigned long n) {
    unsigned char *out = dst;
    const unsigned char *in = src;

    while (n--)
        *out++ = *in++;
    return dst;
}

/* Overlap-safe, which memcpy is not: ../src/text.c is the caller and it is the reason this is a
 * separate body rather than an alias. */
void *memmove(void *dst, const void *src, unsigned long n) {
    unsigned char *out = dst;
    const unsigned char *in = src;

    if (out <= in)
        return memcpy(dst, src, n);
    out += n;
    in += n;
    while (n--)
        *--out = *--in;
    return dst;
}
