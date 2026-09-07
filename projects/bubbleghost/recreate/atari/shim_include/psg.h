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
 * (`tos.h`'s header comment). $ffff8800 is supervisor-only, so a user-mode access goes through the
 * trap #9 gate — which is not a workaround but the ORIGINAL'S OWN MECHANISM: `psg_access`
 * @ 0x14940 is a user-mode stub that pushes three words and traps into the game's supervisor
 * handler at $a4 for exactly this reason.
 *
 * ...EXCEPT FROM INSIDE THE SOUND ISR, WHICH IS ALREADY SUPERVISOR, and that is where nearly every
 * write in this program is made: ~3 a tick, 200 times a second. `tos.h` argues the privilege and
 * the interrupt mask; the ORIGINAL's ISR writes the ports itself for the same reason, and the trap
 * it does not make was 20% of what our tick cost (../STATUS.md, "Performance"). The WRITE is what
 * takes the short path — `psg_port_read` is reached only from `trap9_psg_handler`, which nothing on
 * the interrupt's own path calls, so it would be a branch that is never taken.
 *
 * AND THE SHORT PATH IS SPELT HERE RATHER THAN CALLED. It was a `jsr` into bubble_os.s with two
 * stack arguments around two `move.b`, which measured 100 cycles a write against the ~40 the two
 * stores are — 300 of a 3,887-cycle tick for plumbing (../STATUS.md, "Performance", wave 3a). The
 * two numbers it needs are the gate's own, below, and `atari/build.sh` pins them equal to
 * bubble_os.s's — and pins this function's body to be those two macros and nothing else — so that
 * the two doors cannot drift apart in the address they write.
 *
 * THE REFUSAL THE MODEL MAKES AND THE CHIP DOES NOT. The kit refuses a register number above 15
 * and refuses a READ of a register whose contents the case never declared. Neither refusal can
 * exist here: the chip decodes four bits and answers whatever it holds. The TRAPPED door masks
 * (`andi.l #PSG_REG_MASK` in `bg_super_gate_entry`) because the original's own gate does
 * (`and.b #$f,d1` @ 0x1495c); the UNTRAPPED one below does not, because the original's ISR does not
 * either (`move.b d1,(a1)` @ 0x14780) — and it needs no mask to agree with it, since narrowing to a
 * byte and then letting the latch decode four bits is the same four bits a mask would have left.
 * So a caller that passed 16 selects register 0 on the machine, on the original and through either
 * door, and the model's refusal is the off-target half of a seam whose on-target half is the chip.
 * `../src/sound.c` never reaches either door with more than 10.
 */
#ifndef BUBBLEGHOST_SHIM_PSG_H
#define BUBBLEGHOST_SHIM_PSG_H

#include <stdint.h>

#include <tos.h>   /* the gate. ANGLE FORM: docs/on-target-execution.md class 12b — a quoted
                    * include from inside shim_include/ resolves by this file's own directory,
                    * which is not what a sibling shadow can rely on. */

/* THE SAME TWO NUMBERS AS bubble_os.s's `PSG_SELECT` and `PSG_DATA`, pinned equal to them by
 * atari/build.sh beside the supervisor gate's three operation codes.
 *
 * REGISTERED, NOT DONE — the kit already owns this pair as `OS_PSG_PORT_SELECT` / `OS_PSG_PORT_DATA`
 * (tools/recreate_kit/include/os.h), pinned across the language boundary by tools/hw_portability.py,
 * and Zynaps' shim reaches them through `hw_write8`. This build cannot: its `hw_write8` is the
 * trap #9 gate (shim_include/hw.h) and would put a trap back on the path this wave took one off,
 * and the kit's constants are in the 24-BIT bus form, whose widening to $ffff8800 lives only in
 * bubble_os.s's `BUS_HIGH_BYTE`. Closing it means that widening spelt in C — at which point this
 * pair becomes one expression and the scrape below retires. */
#define BG_PSG_SELECT      0xffff8800u  /* write = select a register, read = the selected one */
#define BG_PSG_DATA_OFFSET 2u           /* ...and $ffff8802 is where a write's data goes */

/* The untrapped write, for a caller that is already supervisor with the MFP masked — the sound ISR
 * and nothing else. Two ordered stores and NOTHING ELSE, which is what the original's handler
 * spends here (`move.b d1,(a1)` / `move.b d0,2(a1)` @ 0x14780); the mask that the trapped door
 * carries is argued away in this file's header. */
static inline void psg_untrapped_write(unsigned reg, uint8_t value) {
    *(volatile uint8_t *)BG_PSG_SELECT = (uint8_t)reg;
    *(volatile uint8_t *)(BG_PSG_SELECT + BG_PSG_DATA_OFFSET) = value;
}

static inline void psg_port_write(unsigned reg, uint8_t value) {
    if (bg_in_timer_c)
        psg_untrapped_write(reg, value);
    else
        bg_super_gate(BG_GATE_PSG_WRITE, reg, value);
}

static inline uint8_t psg_port_read(unsigned reg) {
    return (uint8_t)bg_super_gate(BG_GATE_PSG_READ, reg, 0);
}

#endif /* BUBBLEGHOST_SHIM_PSG_H */
