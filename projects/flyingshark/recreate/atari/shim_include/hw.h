/* hw.h — the SHIM'S hardware doors, shadowing `tools/recreate_kit/include/hw.h` for a target build.
 *
 * `shim_include` is first on the include path, so every core that says `#include "hw.h"` gets this
 * file instead of the kit's — the same seam `os.h` already is, and the kit's own header asks for it
 * in those words: an Atari build does not compile `src/hw.c` and defines each door as the real
 * store OF ITS OWN WIDTH.
 *
 * WHY `static inline` AND NOT BODIES IN flyshark_backend.c. Measured in the sibling project
 * (projects/zynaps/recreate/atari/shim_include/hw.h): a cross-unit call costs about 205 cycles for
 * a store the 68000 makes in 24, and every caller here passes a CONSTANT address, so a body the
 * call site can see folds the bus arithmetic away and emits the `move`. This game's doors are
 * colder than that project's — four `hw_bclr8`s per ACIA interrupt and one `hw_read8` per
 * interrupt beside them — but the argument is the same and the cost of following it is nil.
 *
 * A READ-MODIFY-WRITE IS NOT A STORE, and that is what `hw_bclr8` exists for. `bclr #6,$fffffa11`
 * clears one bit of a byte the MFP already holds; a reconstruction that computed the value from the
 * model's fabricated 0 and called `hw_write8` would pass every off-target check and, cross-compiled,
 * clear every OTHER in-service bit as well (docs/on-target-execution.md, "The observable surfaces").
 * ../src/irq.c spells the operation, and this is where it becomes the instruction.
 *
 * THE KIT'S HEADER IS NOT `#include_next`ed. Its `hw_read8`/`hw_write*`/`hw_bset8`/`hw_bclr8`/
 * `hw_and8` are declared `extern`, and C forbids a `static inline` definition of a name already
 * declared without `static`; its remaining names are the harness's `g_hw_*` ledger accessors, which
 * exist only off target. So this file replaces the header rather than extending it, and the kit's
 * own text stays the contract both halves are written against.
 *
 * NOTHING HERE MAY BE A SHIM HEADER. Every core says `#include "hw.h"` and gets this file, so
 * whatever it includes lands in ten verified translation units; the sibling project measured what
 * that costs when the shim's own cross-unit header slipped in (`zy_image_base` and `zynaps_main()`
 * in every core's scope, with the containment gate still green). The doors' own arithmetic and
 * counters live HERE, and the one header below is the KIT's.
 */
#ifndef FS_SHIM_HW_H
#define FS_SHIM_HW_H

#include <stdint.h>

/* `<os.h>` AND NOT `"os.h"`, and the angle brackets are load-bearing: this file sits in
 * shim_include beside the os.h that shadows the kit's, and that one reaches the kit's through
 * `#include_next`. A quoted include from HERE would find the sibling by this file's own directory
 * rather than through the -I path, and `#include_next` would then restart at the head of the path,
 * find the shadow again, and never read the kit's header at all — every OS_* constant undeclared
 * (docs/on-target-execution.md class 12b). A core is not in this directory and gets it right for
 * free. */
#include <os.h>

/* ---- the machine's addresses, in the form a C pointer needs ------------------------------------
 *
 * The 68000 ignores address bits 31-24, so `$ff8800` and `$ffff8800` are one address — but a C
 * pointer has to name the one the CPU puts on the bus, and a 68030 in an Atari does NOT ignore
 * them. The kit's constants spell the short form (`OS_HW_ACIA_DATA` is 0xfffc02, `OS_PSG_PORT_DATA`
 * 0xff8802); this is the arithmetic that turns one into the other. It is IDEMPOTENT — it only sets
 * the top eight bits — so a door takes either spelling and canonicalises once. */
#define FS_HW_BUS_HIGH_BITS 0xff000000u
#define FS_HW_BUS(addr) ((uint32_t)((addr) | FS_HW_BUS_HIGH_BITS))

/* What the doors count. Off target the kit's ordered (address, width, value) ledger holds every
 * store and `harness.differential` compares it entry for entry; here there is no ledger, so these
 * are the only surface a target run has for a hardware access, and the record carries them.
 * Defined in flyshark_backend.c, because a definition in a header would be one per translation
 * unit and the counts would be per-file rather than per-run. */
/* Plain stores. Today every one of them is half of a YM2149 register write and reaches this
 * counter from psg.h rather than from a door — see `hw_store8` below — so the number smoke.py
 * checks against `2 x PSG_WRITES` is still the run's store count, and a store made anywhere else,
 * through any of the three widths, is what would break that equality. */
extern volatile uint32_t fs_hw_writes;
extern volatile uint32_t fs_hw_rmw;      /* ...and read-modify-writes, which is the ACIA's EOI */
extern volatile uint32_t fs_hw_reads;    /* reads, which is the ACIA data port and $ff820a */

/* ---- the three plain stores -------------------------------------------------------------------
 *
 * WIDTH IS NOT DECORATION: a byte store widened to a word clobbers the register beside it, and on
 * this bus the register beside a shifter byte is another shifter register.
 *
 * THE BYTE DOOR IS IN TWO HALVES, and the split exists so that the bus arithmetic and the width have
 * ONE spelling. `psg_port_write` (psg.h) is the caller that needs the untallied half: the vertical
 * blank pushes thirteen register writes through the select/data pair, where counting each store
 * separately cost more than making it did, so that seam stores twice and counts once. Nothing else
 * uses `hw_store8` — a store made anywhere else goes through the door and is counted there. */
static inline void hw_store8(uint32_t addr, uint32_t value) {
    *(volatile uint8_t *)FS_HW_BUS(addr) = (uint8_t)value;
}

static inline void hw_write8(uint32_t addr, uint32_t value) {
    hw_store8(addr, value);
    fs_hw_writes++;
}

static inline void hw_write16(uint32_t addr, uint32_t value) {
    *(volatile uint16_t *)FS_HW_BUS(addr) = (uint16_t)value;
    fs_hw_writes++;
}

static inline void hw_write32(uint32_t addr, uint32_t value) {
    *(volatile uint32_t *)FS_HW_BUS(addr) = value;
    fs_hw_writes++;
}

/* ---- and the three read-modify-writes ---------------------------------------------------------
 *
 * Each is ONE 68000 instruction and is written as one: `bset`/`bclr` on a memory byte are
 * indivisible on this CPU, which matters because the only caller is an interrupt handler clearing
 * its own in-service bit while another channel may be trying to set one. Spelling it as a C
 * read-then-write would open a window the instruction does not have. */
static inline void hw_bset8(uint32_t addr, uint32_t bit) {
    volatile uint8_t *reg = (volatile uint8_t *)FS_HW_BUS(addr);

    __asm__ __volatile__("bset %1,%0" : "+m"(*reg) : "d"(bit) : "cc");
    fs_hw_rmw++;
}

static inline void hw_bclr8(uint32_t addr, uint32_t bit) {
    volatile uint8_t *reg = (volatile uint8_t *)FS_HW_BUS(addr);

    __asm__ __volatile__("bclr %1,%0" : "+m"(*reg) : "d"(bit) : "cc");
    fs_hw_rmw++;
}

/* `and.b Dn,<ea>` rather than the `andi.b #mask,<ea>` the kit's door is named after: the mask
 * reaches this body as a variable, and the two instructions perform the same read-modify-write in
 * the same one instruction. */
static inline void hw_and8(uint32_t addr, uint32_t mask) {
    volatile uint8_t *reg = (volatile uint8_t *)FS_HW_BUS(addr);

    __asm__ __volatile__("and.b %1,%0" : "+m"(*reg) : "d"(mask) : "cc");
    fs_hw_rmw++;
}

/* ---- the read half ----------------------------------------------------------------------------
 *
 * Three callers, and each is a byte the model could only fabricate. `acia_ikbd_isr` and its two
 * joystick continuations (../src/irq.c) read the 6850's data port, which is VOLATILE in the model
 * too — each read pops the receive register — and `music_tick_dispatch` (../src/sound.c) reads the
 * shifter's sync byte to find out whether it is on a 50 Hz or a 60 Hz machine. Off target both are
 * DECLARED case inputs (`hw_seed=`); here they are the chip, which is the whole point of the seam.
 */
static inline uint8_t hw_read8(uint32_t addr) {
    uint8_t value = *(volatile uint8_t *)FS_HW_BUS(addr);

    fs_hw_reads++;
    return value;
}

#endif /* FS_SHIM_HW_H */
