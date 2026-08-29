/* zynaps_backend.c — the seam's target half: every symbol the differential harness MODELLED, done
 * for real on the machine.
 *
 * Off target these live in translation units this build leaves out — `tools/recreate_kit/src/hw.c`
 * (the ordered hardware read/write ledgers) and `tools/recreate_kit/src/psg.c` (the YM2149's two
 * ports). Both files say in their own headers that a build for the real Atari does not compile them
 * and drives the chips itself. This is that file. `README.md`'s seam table is the inventory; this
 * is the code.
 *
 * WHAT MAKES IT SAFE TO SUBSTITUTE. Each routine below has the same signature and the same CALL
 * SITES as the modelled one, so the cores are compiled unchanged and the differential .so is
 * untouched — `make test` is still 3410 (build.sh checks that no core mentions a name from this
 * directory, and that no symbol here collides with one a core now defines). What changes is only
 * what the access lands on: an ordered ledger off target, a device register here.
 *
 * ...AND WHAT DOES NOT MAKE IT SAFE. A seam prices what the substituted code RETURNS, not what it
 * did to shared state on the way (docs/on-target-execution.md class 11). `hw_write*` is write-only
 * to a device and reads nothing back, so there is no protocol under it to drop. `hw_read8` has one
 * caller (`ikbd_send_cmd` in ../src/input.c) and answers the real 6850 rather than the model's
 * seeded byte, which is the whole point of it being here.
 *
 * EVERY HARDWARE ADDRESS IS IN THE 24-BIT-BUS FORM ($ffff8800, not $ff8800). The 68000 aliases the
 * two, and the kit's headers spell the SHORT form because that is what a reconstruction's constant
 * says; a C pointer has to name the address the CPU will actually put on the bus. `HW_BUS` is
 * IDEMPOTENT — it only sets the top eight bits — so the four doors below take either spelling and
 * canonicalise once, which is what lets the cores pass $ff8240 and this file's own callers pass
 * $ffff8240 without two address ladders.
 */
#include <stdint.h>

#include "hw.h"
#include "os.h"
#include "psg.h"

#include "init.h"          /* HW_SHIFTER_MODE — the resolution byte the boot's one store names */
#include "video.h"         /* the colour block: HW_PALETTE_BASE, PALETTE_PENS, the two widths */
#include "zynaps_target.h"

/* ================================================================================================
 * THE FOUR HARDWARE DOORS, IN ONE PLACE. `tools/recreate_kit/include/hw.h` declares all four and
 * states the contract this file is the target half of: "ON TARGET these three names are supplied by
 * the build itself ... an Atari build does not compile src/hw.c and defines each as the real store
 * OF ITS OWN WIDTH". Nothing about them is this project's own — the cores call the KIT's names, and
 * that is why there is no longer a shim header adding a third spelling.
 *
 * WIDTH IS NOT DECORATION. hw.h: "a byte store widened to a word clobbers the register next door
 * (the MFP's timer-A data byte sits beside its in-service register B)". So each door stores through
 * a pointer of its own width and takes `uint32_t` as the kit declares it, letting the store itself
 * do the masking the ledger does off target.
 * ============================================================================================= */

/* Every store made through these doors, so a run that touched no hardware is separable from one
 * whose writes went somewhere unexpected. smoke.py predicts it exactly (README.md's seam table
 * carries the arithmetic), which is only possible while `zy_hw_writes++` stays one `addq.l` — see
 * zynaps_main.c's note on the boot's one critical section. */
volatile uint32_t zy_hw_writes;

/* THREE ADDRESS-KEYED TALLIES, and they exist because three CORE effects are otherwise invisible
 * here. Off target each of the three is held by the kit's ordered (address, width, value) ledger,
 * which `harness.differential` compares entry for entry; on target there is no ledger, so the shim
 * counts the stores as they pass and STATE.BIN carries the counts. Each is keyed on something the
 * shim's OWN traffic cannot forge:
 *
 *   - the resolution byte is at an address nothing else in this build writes;
 *   - the boot's title palette is the only LONGWORD-wide traffic into the colour block
 *     (`set_palette_title` ends in `movem.l #$00ff,$ff8240.l`); the shim's own pen writes and the
 *     control's injected fault are word-wide, so they cannot inflate this count;
 *   - the IKBD data port is written only by `ikbd_send_cmd`, which this build calls twice.
 *
 * They replace ../src/init.c's `init_palette_uploads` / `init_shifter_mode_writes`, which the write
 * ledger retired: the counting moved to where the store now actually happens. */
volatile uint32_t zy_shifter_mode_writes;
volatile uint32_t zy_palette_long_writes;
volatile uint32_t zy_acia_bytes_sent;

/* Where the colour row's LAST LONGWORD starts, so "a long of the palette upload" is a range and not
 * eight comparisons. ../include/video.h owns the base and the pair count.
 *
 * IT IS THE LAST LONGWORD'S ADDRESS AND NOT THE LAST PEN'S, and the difference is a register. A
 * four-byte store beginning at the last PEN ($ff825e) writes $ff825e..$ff8261 — into $ff8260, the
 * RESOLUTION register, which is the class-6 hang this whole file is written against. Admitting such
 * a store as one of the eight legitimate palette longs would leave `palette_long_writes` reading 8
 * over a write that had just changed the screen mode. */
#define HW_PALETTE_LAST_LONG \
    (HW_PALETTE_BASE + PALETTE_LONG_BYTES * (SHIFTER_PALETTE_PAIRS - 1))

static void note_store(uint32_t bus_addr, unsigned width) {
    zy_hw_writes++;
    if (bus_addr == HW_BUS(HW_SHIFTER_MODE))
        zy_shifter_mode_writes++;
    else if (width == PALETTE_LONG_BYTES
             && bus_addr >= HW_BUS(HW_PALETTE_BASE)
             && bus_addr <= HW_BUS(HW_PALETTE_LAST_LONG))
        zy_palette_long_writes++;
    else if (bus_addr == HW_BUS(OS_HW_ACIA_DATA))
        zy_acia_bytes_sent++;
}

void hw_write8(uint32_t addr, uint32_t value) {
    *(volatile uint8_t *)HW_BUS(addr) = (uint8_t)value;
    note_store(HW_BUS(addr), sizeof (uint8_t));
}

void hw_write16(uint32_t addr, uint32_t value) {
    *(volatile uint16_t *)HW_BUS(addr) = (uint16_t)value;
    note_store(HW_BUS(addr), sizeof (uint16_t));
}

void hw_write32(uint32_t addr, uint32_t value) {
    *(volatile uint32_t *)HW_BUS(addr) = value;
    note_store(HW_BUS(addr), sizeof (uint32_t));
}

/* The READ half, and it has exactly one caller: `ikbd_send_cmd` (../src/input.c) spinning on the
 * 6850's transmitter-empty bit. Off target the kit answers a byte the case DECLARED, so the spin
 * leaves on its first poll; here it answers the chip, and the spin is the original's own — see
 * shim_include/tos.h's note on why this build no longer carries a bounded copy of that routine.
 *
 * NOT COUNTED. A read leaves the machine exactly as it found it, so there is nothing for a
 * read-back surface to hold, and a poll count would be a number about the host's timing rather than
 * about the program. What says the spin ended is `zy_acia_bytes_sent`, above. */
uint8_t hw_read8(uint32_t addr) {
    return *(volatile uint8_t *)HW_BUS(addr);
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
