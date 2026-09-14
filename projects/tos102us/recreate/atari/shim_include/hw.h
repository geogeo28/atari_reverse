/* hw.h — the DECLARED I/O MAP's three read doors as a 68000 build makes them: the access itself.
 *
 * It shadows `tools/recreate_kit/include/hw.h`, which states this file's contract in its own words:
 * "ON TARGET the build supplies all three as the real volatile access, exactly as it supplies
 * psg.h's ports and hw_write8/16/32: `*(volatile uint8_t *)addr`, `*(volatile uint16_t *)addr` and
 * `*(volatile uint32_t *)addr`. It does not compile src/hw.c, so there is no map and no declaration
 * in the chain — the machine answers."
 * The seam is the INCLUDE PATH, as it is for `psg.h` next door; the differential build never sees
 * this directory, so the host `.so` keeps the seeded model and the ordered ledger Tier 1 compares.
 *
 * OUTRIGHT rather than through `#include_next`, for zynaps' reason: the kit declares these `extern`
 * and C forbids redeclaring one `static`.
 *
 * ONLY THE THREE READ DOORS, and the omissions are the point. `hw_read8`, `hw_write8/16/32` and the
 * three read-modify-writes are declared by the kit and implemented by NO core in this reconstruction
 * yet — so a core that acquires one fails at LINK, naming the symbol, which is the right outcome:
 * each of those is a decision about what the target build does with a store the oracle only
 * ledgers, and writing them before a core needs one would be writing them with nothing to check
 * them against. Add each one here, with its evidence, when the core that needs it lands.
 *
 * Under the oracle these accesses reach the DECLARED I/O MAP exactly as the ROM's own `move.b
 * $ffff8260,d0` does — the shim decodes the I/O page rather than serving it from the image — which
 * is what makes a Tier 3 row over such a core a comparison rather than two fabricated zeroes
 * (tools/recreate_kit/rom_bench.py).
 */
#ifndef TOS102US_SHIM_HW_H
#define TOS102US_SHIM_HW_H

#include <stdint.h>

/* `move.b addr,d0` — the byte the machine answers, with nothing between the core and the bus. */
static inline uint8_t io_read8(uint32_t addr)
{
    return *(volatile uint8_t *)addr;
}

/* ...and `move.w addr,d0`. One access of one width, not two bytes: a 68000 word read of an I/O
 * register is one bus cycle, and a chip that latches on access would see a different thing. */
static inline uint16_t io_read16(uint32_t addr)
{
    return *(volatile uint16_t *)addr;
}

/* ...and `move.l addr,d0`, which the shifter's screen-base and video-counter registers are read
 * through. A 68000 splits it into two bus cycles, but they are the two cycles the ORIGINAL's own
 * `move.l` makes: what would be wrong is spelling it as two `io_read16` calls, which is a different
 * instruction and, on a register that latches, a different thing to the chip. */
static inline uint32_t io_read32(uint32_t addr)
{
    return *(volatile uint32_t *)addr;
}

#endif /* TOS102US_SHIM_HW_H */
