/* hw.h — the SHIM'S hardware door, shadowing `tools/recreate_kit/include/hw.h` for the PRG build.
 *
 * `shim_include` is first on the include path, so `src/sound.c`'s `#include "hw.h"` gets this file
 * instead of the kit's, and the kit's `src/hw.c` — the ordered (address, width, value) ledger the
 * differential compares entry for entry — is not linked at all. The kit's own header asks for this
 * in those words: "ON TARGET these three names are supplied by the build itself ... an Atari build
 * does not compile src/hw.c and defines each as the real store OF ITS OWN WIDTH".
 *
 * ONE DOOR IS DEFINED AND FIVE ARE NOT, and the asymmetry is measured rather than assumed:
 * `hw_write8` is the only one this game's cores call, at exactly two sites — `install_sound_vectors`
 * and `remove_sound_vectors` (../src/sound.c), both writing the MFP's vector register $fffffa17 to
 * choose between automatic and software end-of-interrupt. `build.sh`'s hardware-door gate reads both
 * halves of that sentence off the tree every build: it refuses a core that names a door this file
 * does not define, and it refuses a change in the NUMBER of call sites. The first would otherwise
 * arrive as a link error naming a symbol and not the claim it broke; the second would arrive as a
 * record field quietly counting something else.
 *
 * THE KIT'S HEADER IS NOT `#include_next`ed, for psg.h's reason: its doors are declared `extern`
 * and C forbids a `static inline` definition of a name already declared without `static`.
 *
 * WHY THE STORE IS NOT A STORE. This build runs in USER mode (`tos.h`'s header comment says why),
 * and $fffffa17 is supervisor-only, so the byte goes through the same trap #9 gate the two PSG
 * ports go through. What that costs is about forty cycles on a store made twice per sound
 * start/stop; what it buys is that the door is correct wherever a core calls it from, rather than
 * only inside a supervisor bracket the shim would have to remember to put there.
 */
#ifndef BUBBLEGHOST_SHIM_HW_H
#define BUBBLEGHOST_SHIM_HW_H

#include <stdint.h>

#include <tos.h>   /* the gate. ANGLE FORM — docs/on-target-execution.md class 12b */

/* NOTHING SHIM-OWNED IS PULLED IN HERE. Every core that says `#include "hw.h"` gets this file, so
 * whatever this file includes lands in a verified translation unit; `tos.h` is the trap layer and
 * carries no `bg_image_base`, no composition and no record. Zynaps' copy of this header records
 * the same rule after a draft broke it. */

/* Count them, because a store the machine cannot be asked about afterwards has no other surface:
 * the MFP's vector register reads back as itself, but nothing says how many times it was written
 * or in which order. STATE.BIN carries the count and `smoke.py` predicts it exactly: TWO for a run
 * that starts the sound engine and stops it again, which is what a boot to the anchor and a
 * hand-back through the verified `sound_stop` is. */
extern volatile uint32_t bg_hw_writes;

static inline void hw_write8(uint32_t addr, uint32_t value) {
    bg_hw_writes++;
    bg_super_gate(BG_GATE_STORE8, addr, value & 0xffu);
}

#endif /* BUBBLEGHOST_SHIM_HW_H */
