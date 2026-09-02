/* psg.h — the SHIM'S YM2149 port, shadowing `tools/recreate_kit/include/psg.h` for a target build.
 *
 * The kit's header states the contract this file is the target half of: "Off-target only ... a
 * build for the real Atari writes the ports itself and does not compile src/psg.c." It is `hw.h`'s
 * seam exactly, for the same measured reason and by the same mechanism — `shim_include` is first
 * on the include path, so `../src/sound.c`'s `#include "psg.h"` gets this file.
 *
 * WHY INLINE. `flush_shadow` (../src/sound.c) pushes eleven registers every vertical blank and
 * fourteen more from `sound_reset_psg`, which is 71 calls a frame — measured on the `play` build at
 * 177 cycles a call plus the caller's own argument push and `jsr`, about 15,000 cycles a frame for
 * two byte stores and three counters. The register number is a loop variable rather than a
 * constant, so nothing here folds the way `hw_write8`'s address ladder does; what inlining removes
 * is the cross-unit call itself.
 *
 * `psg_port_read` IS DELIBERATELY ABSENT. The kit declares it and no core in this reconstruction
 * calls it — the game writes the chip and keeps its own shadow copy of what it wrote
 * (`A_psg_reg_shadow`). Leaving it undeclared means a core that ACQUIRED a read would fail to
 * compile here, which is the right outcome: on target it would read the real chip with no surface
 * to hold what came back, exactly the shape `hw_read8`'s note in hw.h argues about. The kit's
 * remaining names are the harness's `g_psg_*` ledger accessors, which exist only off target.
 */
#ifndef ZYNAPS_SHIM_PSG_H
#define ZYNAPS_SHIM_PSG_H

#include <stdint.h>

#include "hw.h"   /* hw_write8 — the two ports go through the same door and the same counters */

/* Writes this door has made, and writes it REFUSED. Defined in zynaps_backend.c, beside the other
 * counters and for the same reason: one definition, so the counts are per-run and not per-file. */
extern volatile uint32_t zy_psg_writes;
extern volatile uint32_t zy_psg_refused;

/* `move.b <reg>,$ff8800` then `move.b <val>,$ff8802` — the original's own pair, in its order.
 *
 * NOT bracketed by an interrupt mask: the select latch and the data port are two stores with a
 * window between them, and the original leaves that window open. Nothing else in this build writes
 * the chip while the handler runs — the shim's only other PSG traffic is the teardown silence, made
 * after the vertical-blank vector has already been handed back to TOS.
 *
 * A REGISTER OUTSIDE 0..15 IS REFUSED RATHER THAN MASKED DOWN, which is the kit's rule and not this
 * file's: the ST's select latch decodes four bits, so a driver that put anything in the upper
 * nibble meant something the chip does not do. Masking here would leave a mutated driver silently
 * steering a real chip; counting the refusal makes it a number STATE.BIN carries. */
static inline void psg_port_write(unsigned reg, uint8_t value) {
    if (reg >= OS_PSG_NREGS) {
        zy_psg_refused++;
        return;
    }
    hw_write8(OS_PSG_PORT_SELECT, (uint8_t)reg);
    hw_write8(OS_PSG_PORT_DATA, value);
    zy_psg_writes++;
}

#endif /* ZYNAPS_SHIM_PSG_H */
