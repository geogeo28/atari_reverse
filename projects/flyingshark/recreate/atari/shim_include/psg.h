/* psg.h — the SHIM'S YM2149 port, shadowing `tools/recreate_kit/include/psg.h` for a target build.
 *
 * The kit's header states the contract this file is the target half of: off-target only, and a
 * build for the real Atari writes the ports itself and does not compile `src/psg.c`. It is `hw.h`'s
 * seam exactly and by the same mechanism — `shim_include` is first on the include path, so
 * `../src/sound.c`'s `#include "psg.h"` gets this file.
 *
 * `psg_port_read` IS DELIBERATELY ABSENT. The kit declares it and no core in this reconstruction
 * calls it: the driver writes the chip and keeps its own shadow of what it wrote
 * (`A_psg_shadow`, ../include/sound.h). Leaving it undeclared means a core that ACQUIRED a read
 * would fail to compile here, which is the right outcome — on target it would read the real chip
 * with no surface to hold what came back.
 *
 * SELECT THEN DATA, AND NOTHING BETWEEN THEM. The YM2149 latches the register number written to
 * $ff8800 and applies the next $ff8802 write to it, so the pair is a protocol and not two stores.
 * The only caller is `flush_shadow` (../src/sound.c) inside the vertical-blank handler, where
 * nothing else in this program is running — the main line never touches the chip — so the pair
 * needs no mask of its own. A shim that grew a second PSG writer would have to revisit that.
 */
#ifndef FS_SHIM_PSG_H
#define FS_SHIM_PSG_H

#include <stdint.h>

/* Angle brackets for the same reason `hw.h` uses them — this file is IN shim_include, so a quoted
 * include would find the shadowing os.h by directory and strand its `#include_next`. */
#include <os.h>

#include "hw.h"       /* the doors, and the counters they keep */

/* Writes this seam made, and writes it REFUSED. A register outside 0..15 is refused rather than
 * masked down: the ST's select latch decodes four bits, so a driver that put anything in the upper
 * nibble meant something the chip does not do, and masking would leave a mutated driver silently
 * steering a real chip. The record carries both numbers. */
extern volatile uint32_t fs_psg_writes;
extern volatile uint32_t fs_psg_refused;

static inline void psg_port_write(unsigned reg, uint8_t value) {
    if (reg >= OS_PSG_NREGS) {
        fs_psg_refused++;
        return;
    }
    hw_write8(OS_PSG_PORT_SELECT, (uint8_t)reg);
    hw_write8(OS_PSG_PORT_DATA, value);
    fs_psg_writes++;
}

#endif /* FS_SHIM_PSG_H */
