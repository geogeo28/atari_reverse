/* psg.h — the YM2149 as a 68000 build reaches it: the two ports, written and read directly.
 *
 * It shadows `tools/recreate_kit/include/psg.h`, whose own header states the contract this file is
 * the target half of: "Off-target only ... a build for the real Atari writes the ports itself and
 * does not compile src/psg.c." The seam is the INCLUDE PATH — this directory goes ahead of the kit's
 * — exactly as in projects/zynaps/recreate/atari/shim_include/psg.h. The differential build never
 * sees this directory, so the host `.so` is unchanged and its ordered access ledger still is what
 * Tier 1 compares.
 *
 * WHAT THIS IS FOR TODAY. `src/xbios/giaccess.c` is the ROM's own door onto the chip, and its whole
 * effect is the chip: nothing it does touches a byte of memory. So Tier 3's numerator can only
 * measure it with a target-side implementation of these two doors — and under the oracle, $ff8800
 * and $ff8802 are DECODED into the same seeded model and the same ordered ledger the original's own
 * `move.b` instructions reach (tools/recreate_kit/README.md, "ROM mode"). That is what lets
 * `rom_bench.measure` compare the two sides' chip traffic rather than two identical images.
 *
 * NOT INTERRUPT-MASKED, and that is the caller's business rather than this file's: the ROM's
 * Giaccess brackets its own accesses with `move.w sr,-(sp)` / `ori.w #$700,sr` because the select
 * latch and the data port are two instructions apart. Putting the mask here would charge it to every
 * caller and would model, in the port helper, something the original does in the routine.
 *
 * THE REGISTER IS NOT RANGE-CHECKED HERE, unlike the kit's host model, which refuses one outside
 * 0..15. Its callers mask first — `giaccess.c` ands with GIACCESS_REGISTER_MASK, which is the four
 * bits the chip's select latch decodes — so a check here would be unreachable code in a ROM, and the
 * value that reaches the latch is four bits wide either way.
 */
#ifndef TOS102US_SHIM_PSG_H
#define TOS102US_SHIM_PSG_H

#include <stdint.h>

#include "os.h"     /* OS_PSG_PORT_SELECT / OS_PSG_PORT_DATA — the kit's addresses, not a copy */

/* `move.b <reg>,$ff8800` then `move.b <value>,$ff8802` — the original's own pair, in its order. */
static inline void psg_port_write(unsigned reg, uint8_t value)
{
    *(volatile uint8_t *)OS_PSG_PORT_SELECT = (uint8_t)reg;
    *(volatile uint8_t *)OS_PSG_PORT_DATA = value;
}

/* ...and `move.b <reg>,$ff8800` then `move.b $ff8800,d0`: the select port is also the chip's
 * read-back port, which is the whole reason Giaccess can be used as a read-modify-write primitive. */
static inline uint8_t psg_port_read(unsigned reg)
{
    *(volatile uint8_t *)OS_PSG_PORT_SELECT = (uint8_t)reg;
    return *(volatile uint8_t *)OS_PSG_PORT_SELECT;
}

#endif /* TOS102US_SHIM_PSG_H */
