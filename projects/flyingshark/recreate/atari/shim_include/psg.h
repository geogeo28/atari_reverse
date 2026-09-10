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

#include "hw.h"       /* hw_store8, and the counters the doors keep */

/* Writes this seam made, and writes it REFUSED. A register outside 0..15 is refused rather than
 * masked down: the ST's select latch decodes four bits, so a driver that put anything in the upper
 * nibble meant something the chip does not do, and masking would leave a mutated driver silently
 * steering a real chip. The record carries both numbers. */
extern volatile uint32_t fs_psg_writes;
extern volatile uint32_t fs_psg_refused;

/* One half of the select/data pair: hw.h's own store, and the ONE it is worth to `fs_hw_writes`.
 *
 * It is `hw_write8` with the counter taken out from under it. An `addq.l #1,(xxx).L` costs 26 cycles
 * on this bus; the vertical blank's only PSG traffic is `flush_shadow_to_psg`'s thirteen register
 * writes, so hw_write8's per-store increment plus `fs_psg_writes`' own came to THREE of them per
 * register write — 926 cycles a blank spent counting against 352 spent storing (measured 2026-09-09
 * by `profile cycles`; ../STATUS.md, "What a vertical blank costs").
 *
 * Returning the tally instead lets the caller add it once, and the compiler folds the sum to a
 * literal 2 — so the pair costs ONE increment and the count is still DERIVED FROM THE STORES rather
 * than asserted about them. That is what keeps smoke.py's `HW_WRITES == 2 x PSG_WRITES` a check on
 * the pair rather than an identity: a store deleted from this function takes its own tally with it
 * and the two numbers stop agreeing, where a constant `+= 2` written beside the stores would go on
 * claiming both were made. It is the only surface the target build's PSG pair has — `make test`
 * compiles the KIT's psg.c and never this header. */
static inline unsigned fs_psg_store(uint32_t port, uint8_t value) {
    hw_store8(port, value);
    return 1;
}

/* SELECT THEN DATA, AND NOTHING BETWEEN THEM — the protocol this file's header argues. */
static inline void psg_port_write(unsigned reg, uint8_t value) {
    unsigned stores;

    if (reg >= OS_PSG_NREGS) {
        fs_psg_refused++;
        return;
    }
    stores = fs_psg_store(OS_PSG_PORT_SELECT, (uint8_t)reg);
    stores += fs_psg_store(OS_PSG_PORT_DATA, value);
    fs_hw_writes += stores;
    fs_psg_writes++;
}

#endif /* FS_SHIM_PSG_H */
