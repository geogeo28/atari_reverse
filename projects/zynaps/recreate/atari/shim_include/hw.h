/* hw.h — the SHIM'S hardware doors, shadowing `tools/recreate_kit/include/hw.h` for a target build.
 *
 * `shim_include` is first on the include path, so every core that says `#include "hw.h"` gets this
 * file instead of the kit's — the same seam `os.h` already is, and the kit's own header asks for it
 * in those words: "ON TARGET these three names are supplied by the build itself ... an Atari build
 * does not compile src/hw.c and defines each as the real store OF ITS OWN WIDTH".
 *
 * WHY A HEADER AND NOT zynaps_backend.c, WHICH IS WHERE THESE BODIES USED TO LIVE. Measured on the
 * `play` build (atari/profile.py ours, 155 frames, 2026-09-01): as out-of-line functions in another
 * translation unit the four doors cost 37,864 cycles a frame, of which `hw_write32` alone was
 * 21,183 at 205 cycles a CALL — for a store the 68000 makes in 24. Nothing in those 205 is the
 * store: it is the argument loads, the `oril` that widens the address to the bus form, the RTS, and
 * a classification chain that compares a runtime value against four immediates. Every one of them
 * is knowable at the CALL SITE, because every caller passes a CONSTANT address — so with the bodies
 * visible the compiler folds the whole chain and emits the `move` plus the counter the shim needs.
 * The proof it works was already in the binary before this file existed: `psg_port_write` lives in
 * the same translation unit as the old `hw_write8` and compiled to `move.b %d0,$ffff8800`, with the
 * address ladder gone, while its cross-unit callers paid all 205.
 *
 * WHAT DOES NOT CHANGE IS THE COUNTING. `zy_hw_writes` and the three address-keyed tallies are the
 * only surface a target run has for a store — off target the kit's ordered (address, width, value)
 * ledger holds it and `harness.differential` compares it entry for entry; here there is no ledger,
 * so STATE.BIN carries the counts and `smoke.py` predicts them exactly. Every build keeps every
 * counter, in every door, and that is a deliberate refusal of the cheaper thing: compiling the
 * tallies out of the `play` build would make `atari/profile.py` — which measures `play` — a reading
 * of a program `smoke.py` never judges. What the folding removes is the SEARCH, not the tally.
 *
 * EVERY HARDWARE ADDRESS IS IN THE 24-BIT-BUS FORM ($ffff8800, not $ff8800), and `HW_BUS` is
 * idempotent, so a caller may pass either spelling — see zynaps_target.h, which owns that
 * arithmetic and the counters these doors keep.
 *
 * THE KIT'S HEADER IS NOT `#include_next`ed. Its `hw_read8`/`hw_write*`/`hw_bset8`/`hw_bclr8`/
 * `hw_and8` are declared `extern`, and C forbids a `static inline` definition of a name already
 * declared without `static`; its remaining names are the harness's `g_hw_*` ledger accessors, which
 * exist only off target. So this file replaces the header rather than extending it, and the kit's
 * own text stays the contract both halves are written against.
 */
#ifndef ZYNAPS_SHIM_HW_H
#define ZYNAPS_SHIM_HW_H

#include <stdint.h>

/* NOTHING HERE IS A SHIM HEADER, AND THAT IS LOAD-BEARING. Every core says `#include "hw.h"` and
 * gets this file, so whatever this file includes lands in ~six verified translation units. A first
 * draft took `HW_BUS` and the counters from `zynaps_target.h` — the shim's own cross-unit surface —
 * which put `zy_image_base`, `zynaps_main()` and every `zy_*` global into the cores' scope while
 * `build.sh`'s "the cores take nothing from this directory" gate, which greps for a DIRECT
 * `#include`, went on printing green. So the doors' own arithmetic and the doors' own counters live
 * HERE, where the doors are, and the two headers below are a CORE header and a KIT header. */
#include "init.h"           /* HW_SHIFTER_MODE — the resolution byte, keyed below */
#include "video.h"          /* the colour block and the shifter's two video-base bytes */

/* `<os.h>` AND NOT `"os.h"`, FOR OS_HW_ACIA_DATA, and the angle brackets are load-bearing. This
 * file sits in shim_include beside the os.h that shadows the kit's, and that one reaches the kit's
 * through `#include_next`. A quoted include from HERE would find the sibling by its directory
 * rather than through the -I path, and GCC's `#include_next` then has no search position to
 * continue FROM — it restarts at the head of the path, finds the shadow again, and the kit's
 * header is never read at all (measured: every OS_* constant undeclared). The angle form makes the
 * shadow be found in `-I shim_include`, which is the position `#include_next` steps past. Every
 * core gets this right for free, because a core is not in this directory. */
#include <os.h>

/* ---- the machine's addresses, in the form a C pointer needs ------------------------------------
 *
 * The 68000 ignores address bits 31-24, so `$ff8240` and `$ffff8240` are one address — but a C
 * pointer has to name the one the CPU puts on the bus. The kit's and the project's headers spell
 * the SHORT form, because that is what a reconstruction's own constant says; this is the arithmetic
 * that turns one into the other. It is IDEMPOTENT — it only sets the top eight bits — so a door
 * takes either spelling and canonicalises once. */
#define HW_BUS_HIGH_BITS 0xff000000u
#define HW_BUS(addr) ((uint32_t)((addr) | HW_BUS_HIGH_BITS))

/* ---- what the doors count ---------------------------------------------------------------------
 *
 * Every store made through them, so a run that touched no hardware is separable from one whose
 * writes went somewhere unexpected; `smoke.py` predicts the total exactly (atari/README.md's seam
 * table carries the arithmetic). Defined in zynaps_backend.c, because a definition in a header
 * would be one per translation unit and the counts would be per-file rather than per-run.
 *
 * THE THREE KEYED TALLIES exist because three CORE effects are otherwise invisible on target: off
 * target the kit's ordered (address, width, value) ledger holds them and `harness.differential`
 * compares it entry for entry, and here there is no ledger. `zy_rmw_stores` is the fourth and says
 * the seam is real — a build that had somehow linked the kit's own off-target `src/hw.c` instead
 * would show 0. */
extern volatile uint32_t zy_hw_writes;
extern volatile uint32_t zy_shifter_mode_writes;
extern volatile uint32_t zy_palette_long_writes;
extern volatile uint32_t zy_acia_bytes_sent;
extern volatile uint32_t zy_rmw_stores;

/* Where the colour row's LAST LONGWORD starts, so "a long of the palette upload" is a range and not
 * eight comparisons. ../include/video.h owns the base and the pair count.
 *
 * IT IS THE LAST LONGWORD'S ADDRESS AND NOT THE LAST PEN'S, and the difference is a register. A
 * four-byte store beginning at the last PEN ($ff825e) writes $ff825e..$ff8261 — into $ff8260, the
 * RESOLUTION register, which is the class-6 hang this whole seam is written against. Admitting such
 * a store as one of the eight legitimate palette longs would leave `palette_long_writes` reading 8
 * over a write that had just changed the screen mode. */
#define HW_PALETTE_LAST_LONG \
    (HW_PALETTE_BASE + PALETTE_LONG_BYTES * (SHIFTER_PALETTE_PAIRS - 1))

/* THREE ADDRESS-KEYED TALLIES, and they exist because three CORE effects are otherwise invisible
 * here. Each is keyed on something the shim's OWN traffic cannot forge:
 *
 *   - the resolution byte is at an address nothing else in this build writes;
 *   - the boot's title palette is the only LONGWORD-wide traffic into the colour block
 *     (`set_palette_title` ends in `movem.l #$00ff,$ff8240.l`); the shim's own pen writes and the
 *     control's injected fault are word-wide, so they cannot inflate this count;
 *   - the IKBD data port is written only by `ikbd_send_cmd`, which this build calls twice.
 *
 * They replace ../src/init.c's `init_palette_uploads` / `init_shifter_mode_writes`, which the write
 * ledger retired: the counting moved to where the store now actually happens.
 *
 * THE CHAIN IS FOUR COMPARES AGAINST IMMEDIATES AND COSTS NOTHING AT A CONSTANT ADDRESS, which is
 * every call site in the program. What survives the fold is one `addq.l` for the total and at most
 * one more for the key — and each stays a SINGLE instruction, which is what makes it safe against
 * an interrupt that counts through the same doors (zynaps_main.c's note on the boot's one critical
 * section carries that argument). */
static inline void zy_note_store(uint32_t bus_addr, unsigned width) {
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

/* The shifter's video base is the one store whose VALUE means something else on this side of the
 * seam — the cores publish an IMAGE offset and the chip needs `zy_image_base + offset` — so it is
 * not a store at all but a small protocol, and it stays OUT OF LINE in zynaps_backend.c beside the
 * offset it accumulates. It happens twice a frame; what it costs is not a number this file is
 * about. `bus_addr` is $ffff8201 or $ffff8203 and nothing else. */
void zy_store_video_base_byte(uint32_t bus_addr, uint32_t value);

/* ---- THE THREE PLAIN STORES ------------------------------------------------------------------
 *
 * WIDTH IS NOT DECORATION. The kit's header: "a byte store widened to a word clobbers the register
 * next door (the MFP's timer-A data byte sits beside its in-service register B)". So each door
 * stores through a pointer of its own width and takes `uint32_t` as the kit declares it, letting
 * the store itself do the masking the ledger does off target. */
static inline void hw_write8(uint32_t addr, uint32_t value) {
    uint32_t bus_addr = HW_BUS(addr);

    if (bus_addr == HW_BUS(HW_SCREEN_BASE_MID) || bus_addr == HW_BUS(HW_SCREEN_BASE_HIGH)) {
        zy_store_video_base_byte(bus_addr, value);
        return;
    }
    *(volatile uint8_t *)bus_addr = (uint8_t)value;
    zy_note_store(bus_addr, sizeof (uint8_t));
}

static inline void hw_write16(uint32_t addr, uint32_t value) {
    uint32_t bus_addr = HW_BUS(addr);

    *(volatile uint16_t *)bus_addr = (uint16_t)value;
    zy_note_store(bus_addr, sizeof (uint16_t));
}

static inline void hw_write32(uint32_t addr, uint32_t value) {
    uint32_t bus_addr = HW_BUS(addr);

    *(volatile uint32_t *)bus_addr = value;
    zy_note_store(bus_addr, sizeof (uint32_t));
}

/* ---- THE THREE READ-MODIFY-WRITES, WHICH A PLAIN STORE IS NOT --------------------------------
 *
 * `andi.b #$fc,$ff8260` (../src/init.c), `bclr #0,$fffa0f` and `bclr #6,$fffa11` (../src/irq.c's
 * two acknowledges), `bset #6,$fffa09` / `$fffa15` (../src/init.c and ../src/frame.c). Off target
 * the READ half has no modelled answer, so the oracle serves a fabricated 0 and both sides store
 * the bare mask or the bare bit; the ledger holds that the store happened, at that register, one
 * byte wide, and cannot hold what it was on top of.
 *
 * ON THE MACHINE THE DIFFERENCE IS THE RUN. `move.b #$40,$fffa09` does not enable MFP channel 6, it
 * DISABLES every other channel of interrupt-enable B — Timer C among them, which is TOS's 200 Hz
 * clock and the floppy driver's motor timeout, so a game that shipped the plain store would lose
 * its disk the moment it enabled its keyboard.
 *
 * Each body is the instruction its name says: the operand is a constant bit or mask and the
 * destination is one `volatile` byte, which is what makes GCC emit `bset`/`bclr`/`andi.b` on the
 * address rather than a load, an arithmetic op and a store.
 *
 * THE READ IS OF A DEVICE REGISTER AND THE WRITE IS BACK TO IT, which on an interrupt-driven MFP is
 * not atomic the way the original's single instruction is: a handler landing between the two halves
 * would have its own change overwritten. Every caller is already inside an interrupt or inside the
 * boot's masked window, so nothing in this build can take that window — but it is a real difference
 * from the original and README.md's M2 unpinned list carries it.
 *
 * `zy_rmw_stores` is a surface and not bookkeeping: the whole argument for this seam is that the
 * cores' `bclr` really becomes a `bclr` on the machine, and a build that had somehow linked the
 * kit's own off-target `src/hw.c` instead would show 0. */
static inline void hw_bset8(uint32_t addr, uint32_t bit) {
    volatile uint8_t *port = (volatile uint8_t *)HW_BUS(addr);

    *port = (uint8_t)(*port | (uint8_t)(1u << bit));
    zy_note_store(HW_BUS(addr), sizeof (uint8_t));
    zy_rmw_stores++;
}

static inline void hw_bclr8(uint32_t addr, uint32_t bit) {
    volatile uint8_t *port = (volatile uint8_t *)HW_BUS(addr);

    *port = (uint8_t)(*port & (uint8_t)~(1u << bit));
    zy_note_store(HW_BUS(addr), sizeof (uint8_t));
    zy_rmw_stores++;
}

static inline void hw_and8(uint32_t addr, uint32_t mask) {
    volatile uint8_t *port = (volatile uint8_t *)HW_BUS(addr);

    *port = (uint8_t)(*port & (uint8_t)mask);
    zy_note_store(HW_BUS(addr), sizeof (uint8_t));
    zy_rmw_stores++;
}

/* THE TRAINER'S ONE TAP ON THE MACHINE, and it is here for the same reason the video base is:
 * reading the 6850's data port POPS it, so the byte the keyboard sent exists for exactly one read
 * and `ikbd_acia_isr` makes it. A watcher that wanted to see keys could not read the port again
 * afterwards, and it could not read them out of the image either — the program keeps ONE byte,
 * `A_key_scancode`, holding the key currently down, so three keys held together are not
 * representable there and a release of anything but the newest is invisible. So the door hands
 * every popped byte on, and atari/zynaps_cheats.c decides what it was.
 *
 * DECLARED HERE RATHER THAN INCLUDED, exactly as `zy_store_video_base_byte` below it is: this
 * header is reached by every verified core, and pulling atari/zynaps_cheats.h in would put the
 * shim's own names into six verified translation units — the defect this file's opening note
 * records having already been made once.
 *
 * IT IS UNCONDITIONAL, AND THAT IS THE WHOLE POINT — `zy_store_video_base_byte`'s precedent again,
 * and a defect this file carried for one draft. Wrapping the call in `#ifdef ZY_CHEATS` would make
 * `../src/irq.c`'s `ikbd_acia_service_one_byte` — a DIFFERENTIAL-PINNED CORE — compile to different
 * machine code in the default build and in the purist one, from a `-D` build.sh passes to the core
 * compile. `make test` never compiles this header, so it could not see the difference; and the gate
 * written for exactly that risk greps `../src` and `../include` for the macro name, which a shim
 * header is not. So the tap is always emitted, the purist build links the empty
 * `zy_cheat_note_ikbd_byte` in atari/zynaps_cheats.c's `#else` arm, and `ZY_CHEATS` reaches no core
 * translation unit at all. What it costs there is one `bsr`+`rts` per IKBD byte — about 3 bytes a
 * frame — in the build nothing measures.
 *
 * IT COSTS NOTHING AT ANY OTHER CALL SITE. Every caller of `hw_read8` in this program passes a
 * CONSTANT address, so the comparison below folds at compile time: `ikbd_send_cmd`'s status poll,
 * the handler's GPIP test and zynaps_main.c's four MFP read-backs emit the bare `move.b` they
 * always did, and only the one site that reads $fffffc02 keeps the call. */
void zy_cheat_note_ikbd_byte(uint8_t byte);

/* The READ half. Two callers: `ikbd_send_cmd` (../src/input.c) spinning on the 6850's
 * transmitter-empty bit, and zynaps_main.c reading TOS's MFP registers back at the hand-back. Off
 * target the kit answers a byte the case DECLARED, so the spin leaves on its first poll; here it
 * answers the chip, and the spin is the original's own.
 *
 * NOT COUNTED. A read leaves the machine exactly as it found it, so there is nothing for a
 * read-back surface to hold, and a poll count would be a number about the host's timing rather than
 * about the program. What says the spin ended is `zy_acia_bytes_sent`. */
static inline uint8_t hw_read8(uint32_t addr) {
    uint32_t bus_addr = HW_BUS(addr);
    uint8_t value = *(volatile uint8_t *)bus_addr;

    if (bus_addr == HW_BUS(OS_HW_ACIA_DATA))
        zy_cheat_note_ikbd_byte(value);
    return value;
}

#endif /* ZYNAPS_SHIM_HW_H */
