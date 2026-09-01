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
#include "irq.h"           /* HW_MFP_ISRA / HW_MFP_ISRB and the two bit numbers they acknowledge */
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

/* ================================================================================================
 * THE ADDRESS-KEYED LEDGER THAT IS NOT HERE, and the measurement that took it out.
 *
 * README.md's Unpinned 15 asked for one: the three tallies above are keyed on arguments about
 * today's call sites (a width, an address nothing else writes), and the depth-correct replacement is
 * a small on-target ledger of stores PER ADDRESS, which would subsume all three. It was written,
 * twice, and both drafts had to be deleted for a reason that is a finding in its own right.
 *
 * ATTRACT MODE'S TIMER B FIRES EVERY TWO SCANLINES — about 1024 CPU cycles at 8 MHz — and its
 * handler makes two hardware stores (pen 0 and the MFP acknowledge). MEASURED on `build.sh game`
 * under Hatari: WITH the ledger the handler took about 2000 cycles, i.e. longer than its own
 * period, and the main line advanced a couple of instructions a frame — twenty seconds inside an
 * eight-iteration palette upload, and the title page never drawn. WITHOUT it the same build runs the
 * attract loop, starts a game and reaches the section start. The second draft replaced the linear
 * scan with a direct-mapped hash and was still over the cliff: what costs is the extra CALL and its
 * argument, not the search.
 *
 * THE RATE THIS PARAGRAPH USED TO QUOTE — "only 79 of the frame's 156 interrupts arrived" — WAS
 * WRONG IN BOTH HALVES AND IS RETRACTED. Timer B is in EVENT-COUNT mode, so the event it counts is
 * the shifter's display-enable pulse, one per DISPLAYED scanline: ST low resolution has 200 of
 * those, not 313, and at a period of 2 the chip offers 100 interrupts a vertical blank rather than
 * 156. And the build this file describes serves 6,263 of them over 64 attract vertical blanks —
 * 98% — which `smoke.py`'s `check_the_pacing` now holds to a floor. What is quoted above is the
 * measurement that stands: the ledger made the handler longer than its period, and deleting it is
 * what fixed that.
 *
 * So the shape a target build can afford is a fixed set of NAMED counters — the three above, which
 * compile to one compare and one `addq` each — and not a table. `docs/on-target-execution.md`'s
 * taxonomy 13 is the class this belongs to, and atari/README.md's PERFORMANCE section carries the
 * whole table.
 * ============================================================================================= */

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

/* ================================================================================================
 * THE READ-MODIFY-WRITES, WHICH A PLAIN STORE IS NOT.
 *
 * `tools/recreate_kit/include/hw.h` states the rule once for every game: "WHAT THIS SEAM DOES NOT
 * GIVE YOU IS A READ-MODIFY-WRITE". Six sites in this reconstruction are one — `andi.b #$fc,$ff8260`
 * (src/init.c), `bclr #0,$fffa0f` and `bclr #6,$fffa11` (src/irq.c's two acknowledges), and
 * `bset #6,$fffa09` / `$fffa15` (src/init.c's `boot_enable_interrupts`, and once more in
 * src/frame.c). Off target the READ half has no modelled answer, so the oracle serves a fabricated 0
 * and both sides store the bare mask or the bare bit; the ledger holds that the store happened, at
 * that register, one byte wide, and cannot hold what it was on top of.
 *
 * ON THE MACHINE THE DIFFERENCE IS THE RUN. `move.b #$40,$fffa09` does not enable MFP channel 6, it
 * DISABLES every other channel of interrupt-enable B — Timer C among them, which is TOS's 200 Hz
 * clock and the floppy driver's motor timeout, so a game that shipped the plain store would lose its
 * disk the moment it enabled its keyboard. `move.b #$0,$fffa0f` acknowledges every in-service
 * channel rather than Timer B's, and `move.b #$0,$fffa11` every one rather than the ACIA's.
 *
 * The three doors below are the target half of the kit's own read-modify-write names, and each is
 * the instruction its name says: the operand is a constant bit or mask and the destination is one
 * `volatile` byte, which is what makes GCC emit `bset`/`bclr`/`andi.b` on the address rather than a
 * load, an arithmetic op and a store. Their signatures are the kit's, `uint32_t` and all.
 *
 * THE READ IS OF A DEVICE REGISTER AND THE WRITE IS BACK TO IT, which on an interrupt-driven MFP is
 * not atomic the way the original's single instruction is: a handler landing between the two halves
 * would have its own change overwritten. Every caller here is already inside an interrupt or inside
 * the boot's masked window, so nothing in this build can take that window — but it is a real
 * difference from the original and README.md's M2 unpinned list carries it rather than this comment
 * quietly absorbing it.
 * ============================================================================================= */

/* Read-modify-writes made through the three doors. It is a surface and not bookkeeping: the whole
 * argument for this file is that the cores' `bclr` really becomes a `bclr` on the machine, and a
 * build that had somehow linked the kit's own off-target `src/hw.c` instead would show 0 here. */
volatile uint32_t zy_rmw_stores;

void hw_bset8(uint32_t addr, uint32_t bit) {
    volatile uint8_t *port = (volatile uint8_t *)HW_BUS(addr);

    *port = (uint8_t)(*port | (uint8_t)(1u << bit));
    note_store(HW_BUS(addr), sizeof (uint8_t));
    zy_rmw_stores++;
}

void hw_bclr8(uint32_t addr, uint32_t bit) {
    volatile uint8_t *port = (volatile uint8_t *)HW_BUS(addr);

    *port = (uint8_t)(*port & (uint8_t)~(1u << bit));
    note_store(HW_BUS(addr), sizeof (uint8_t));
    zy_rmw_stores++;
}

void hw_and8(uint32_t addr, uint32_t mask) {
    volatile uint8_t *port = (volatile uint8_t *)HW_BUS(addr);

    *port = (uint8_t)(*port & (uint8_t)mask);
    note_store(HW_BUS(addr), sizeof (uint8_t));
    zy_rmw_stores++;
}

/* ================================================================================================
 * THE VIDEO BASE, WHICH IS THE ONE STORE WHOSE VALUE MEANS SOMETHING ELSE HERE.
 *
 * `screen_flip_buffers` publishes `offset >> 8` and `offset >> 16` of the buffer it has just drawn
 * into — an IMAGE offset, because in the differential's world the image is the machine's memory and
 * starts at 0, and because the original's framebuffers are absolute against the base it runs at.
 * This build stages the image in a `.bss` array, so the shifter needs `zy_image_base + offset`.
 *
 * IT IS DONE HERE AND NOT IN THE SHIM'S MAIN LINE, and that is M2's change: the frame loop flips
 * every frame, so re-publishing the machine address after the fact — M1's arrangement, workable
 * while the boot flipped once — would leave the shifter pointed at $0703xx for most of every frame.
 * The door is the one place the CORE ITSELF REACHES.
 *
 * THE OFFSET IS ASSEMBLED ACROSS THE TWO STORES because a byte of a sum is not the sum of a byte:
 * `zy_image_base + offset` carries out of bits 8-15 into 16-23, so neither store can be translated
 * on its own. Each store updates its own half of the remembered offset and then publishes the WHOLE
 * translated address, so after the pair the register is right whichever order the two arrive in.
 * What that costs is the same transient the original has: between the two stores the register holds
 * an address one byte of which is a frame old — and the shifter latches its base at the next
 * vertical blank, not at the store, so no frame is ever fetched from the intermediate value unless
 * a vertical blank falls exactly between two instructions. The original's own pair has that window
 * too, and this build does not widen it. */
static volatile uint32_t g_video_base_offset;

/* What the cores have published, for the record: the offset they last named and the machine address
 * this file translated it to. `smoke.py game` asserts that the second is the first plus the image
 * base, which is the surface for a translation that silently stopped happening. */
volatile uint32_t zy_video_base_offset;
volatile uint32_t zy_video_base_published;
volatile uint32_t zy_video_base_publishes;

static void publish_translated_video_base(void) {
    uint32_t machine = (uint32_t)(uintptr_t)zy_image_base + g_video_base_offset;

    *(volatile uint8_t *)HW_BUS(HW_SCREEN_BASE_MID) = (uint8_t)(machine >> VIDEO_BASE_MID_SHIFT);
    *(volatile uint8_t *)HW_BUS(HW_SCREEN_BASE_HIGH) = (uint8_t)(machine >> VIDEO_BASE_HIGH_SHIFT);
    note_store(HW_BUS(HW_SCREEN_BASE_MID), sizeof (uint8_t));
    note_store(HW_BUS(HW_SCREEN_BASE_HIGH), sizeof (uint8_t));
    zy_video_base_offset = g_video_base_offset;
    zy_video_base_published = machine;
    zy_video_base_publishes++;
}

/* ================================================================================================
 * THE TEMPORARY BRIDGE THAT USED TO BE HERE IS GONE, and its absence is worth a paragraph.
 *
 * Until kit commit `2db68f6` the cores spelt all six read-modify-write sites as
 * `hw_write8(<register>, <the byte a fabricated 0 read produces>)`, and this file recognised those
 * five registers by ADDRESS and made the real operation anyway — because shipping the plain store
 * would have disabled Timer C, TOS's 200 Hz clock and the floppy's motor timeout, the first time
 * the game enabled its keyboard. The cores call `hw_bclr8`, `hw_bset8` and `hw_and8` themselves
 * now, so the bridge would be a second implementation of an operation its callers already spell,
 * and the only honest thing to do with it was delete it. `zy_rmw_stores` above is what is left:
 * the count that says the operation really happens on the machine.
 * ============================================================================================= */

/* 1 when the byte store was the shifter's VIDEO BASE and has been translated and made; 0 when it is
 * an ordinary store. A `switch` rather than two `if`s so that the MISS — which is every other byte
 * store the program makes, inside an interrupt with about a thousand cycles to live — costs one
 * compare chain against immediates and no call. */
static int video_base_store(uint32_t addr, uint32_t value) {
    switch (HW_BUS(addr)) {
    case HW_BUS(HW_SCREEN_BASE_MID):
        g_video_base_offset = (g_video_base_offset & ~(uint32_t)VIDEO_BASE_MID_MASK)
                              | ((value & 0xffu) << VIDEO_BASE_MID_SHIFT);
        publish_translated_video_base();
        return 1;
    case HW_BUS(HW_SCREEN_BASE_HIGH):
        g_video_base_offset = (g_video_base_offset & ~(uint32_t)VIDEO_BASE_HIGH_MASK)
                              | ((value & 0xffu) << VIDEO_BASE_HIGH_SHIFT);
        publish_translated_video_base();
        return 1;
    default:
        return 0;
    }
}

void hw_write8(uint32_t addr, uint32_t value) {
    if (video_base_store(addr, value))
        return;
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
