/* psg.h — the SHIM'S YM2149 doors, shadowing `tools/recreate_kit/include/psg.h` for the PRG build.
 *
 * `shim_include` is first on the include path, so `src/sound.c`'s `#include "psg.h"` gets this file
 * instead of the kit's, and the kit's `src/psg.c` — the ordered ledger and the register file the
 * differential compares — is not linked at all. What the two doors mean here is the real chip.
 *
 * THE KIT'S HEADER IS NOT `#include_next`ed. Its `psg_port_write`/`psg_port_read` are declared
 * `extern`, and C forbids a `static inline` definition of a name already declared without
 * `static`; everything else it declares is the harness's `g_psg_*` ledger accessors, which exist
 * only off target. So this file REPLACES the header rather than extending it, and the kit's own
 * text stays the contract both halves are written against.
 *
 * WHY THESE ARE NOT PLAIN STORES, which is the whole of what makes this file different from
 * Zynaps' copy of it. That build takes supervisor mode once in `_start` and keeps it, so its doors
 * are `move.b reg,$ffff8800`. This one runs in USER mode, because Bubble Ghost is a GEM
 * application and its AES and VDI calls are made from the mode TOS expects them from
 * (`tos.h`'s header comment). $ffff8800 is supervisor-only, so every access goes through the
 * trap #9 gate — which is not a workaround but the ORIGINAL'S OWN MECHANISM: `psg_access`
 * @ 0x14940 is a user-mode stub that pushes three words and traps into the game's supervisor
 * handler at $a4 for exactly this reason.
 *
 * THE REFUSAL THE MODEL MAKES AND THE CHIP DOES NOT. The kit refuses a register number above 15
 * and refuses a READ of a register whose contents the case never declared. Neither refusal can
 * exist here: the chip decodes four bits and answers whatever it holds. The register number is
 * masked in the GATE (`bg_super_gate_entry`, `and.b #15`), which is what the original's handler
 * does too (`and.b #$f,d1` @ 0x1495c) — so a caller that passed 16 selects register 0 on both the
 * machine and the original, and the model's refusal is the off-target half of a seam whose
 * on-target half is the mask. `../src/sound.c` masks before it calls, so no live caller depends on
 * either.
 */
#ifndef BUBBLEGHOST_SHIM_PSG_H
#define BUBBLEGHOST_SHIM_PSG_H

#include <stdint.h>

#include <tos.h>   /* the gate. ANGLE FORM: docs/on-target-execution.md class 12b — a quoted
                    * include from inside shim_include/ resolves by this file's own directory,
                    * which is not what a sibling shadow can rely on. */

static inline void psg_port_write(unsigned reg, uint8_t value) {
    bg_super_gate(BG_GATE_PSG_WRITE, reg, value);
}

static inline uint8_t psg_port_read(unsigned reg) {
    return (uint8_t)bg_super_gate(BG_GATE_PSG_READ, reg, 0);
}

#endif /* BUBBLEGHOST_SHIM_PSG_H */
