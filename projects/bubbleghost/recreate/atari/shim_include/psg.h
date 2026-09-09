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
 * it does not make was 20% of what our tick cost (../STATUS.md, "Performance").
 *
 * THAT SHORT PATH IS NO LONGER A DOOR IN THIS FILE, AND SINCE WAVE 7a IT IS NOT A BRANCH HERE
 * EITHER. It began as a `jsr` into bubble_os.s (100 cycles a write), became two `move.b`s the
 * compiler put inline (32), and then stopped having a caller at all: since wave 5b the 200 Hz
 * handler is `../../src/asm/sound_tick.S`, which writes $ffff8800 with its own transcribed store
 * pairs and reaches nothing here. What stood until wave 7a was `psg_untrapped_write` plus the
 * `bg_in_timer_c` test that selected it — a flag NOTHING set. `../../src/sound.c` calls this door
 * on six lines, and GCC's inlining turned them into 25 `tst.b`/branch pairs in the shipped `play`
 * text, each with an untrapped store pair behind it, arming an arm no run could take. Both are
 * deleted; the door below is the
 * trap, unconditionally. THE TWO PORT NUMBERS STAY HERE and this file is still their one home:
 * `atari/build.sh` pins them equal to `bubble_os.s`'s (the trapped gate's own `lea`), and
 * `test/test_constants.py` pins the twin's `.equ`s equal to them, so the gate and the tick cannot
 * drift apart in the address they write. If the ISR's IPL drop is ever made faithful the
 * protection has to come back — `tos.h` says what it would be, and this paragraph is where the
 * deleted spelling of it is named.
 *
 * THE REFUSAL THE MODEL MAKES AND THE CHIP DOES NOT. The kit refuses a READ of a register whose
 * contents the case never declared; that refusal cannot exist here, because the chip answers
 * whatever it holds. Its other refusal — a register number above 15 — is a different thing, and the
 * register mask is what it is about.
 *
 * WHY THE TWO PATHS TO THE CHIP DISAGREE ABOUT THE REGISTER MASK: BECAUSE THE ORIGINAL'S TWO DO.
 * The TRAPPED door masks (`andi.l #PSG_REG_MASK` in `bg_super_gate_entry`) because the original's
 * own gate does (`and.b #$f,d1` @ 0x1495c). The TICK'S OWN STORES (`../../src/asm/sound_tick.S`)
 * do not, because the original's ISR does not either: it loads `a1` with $ffff8800 once
 * @ 0x145a6 and every one of its FIVE write pairs is a
 * bare `move.b <reg>,(a1)` / `move.b <data>,2(a1)` — the volume @ 0x14682, the tone period's two
 * halves @ 0x14780 and 0x14788, the shared noise register @ 0x1485c and the key-off's volume 0 @
 * 0x1487c — on a register number it built as `voice + 8`, `2 * voice` (+1) or a constant, and never
 * bounded. Reproducing that asymmetry is the point; smoothing it would be the change.
 *
 * SO `reg` MUST BE 0..15 ON THAT PATH, AND THAT IS A PRECONDITION RATHER THAN A ROUNDING. An
 * earlier draft of this header claimed a byte with a non-zero upper nibble selects register 0 —
 * "the same four bits a mask would have left" — and that is NOT established: the AY-3-8910
 * compares the upper nibble against its own chip address and stops responding when they differ,
 * the YM2149 replaced those pins with /CS, and nothing in this workspace has measured what an ST
 * actually does with a write of 16 to $ff8800. This build depends on none of it, and the claim is
 * withdrawn rather than replaced by the opposite one.
 *
 * WHAT HOLDS THE PRECONDITION IS A SURFACE AND NOT THE CHIP. The kit's `psg.h` REFUSES a register
 * above 15 instead of masking it down (`tools/recreate_kit/src/psg.c`, through `os_refused`), so a
 * caller that ever grew one is red under `make test` before anything is built for the target. On
 * this side of the seam nothing above 15 is reachable either: the ISR's own register numbers are
 * `voice + 8`, `2 * voice` and `2 * voice + 1` over voices 0..2, so at most 10, and
 * `trap9_psg_handler` masks with `PSG_REG_SELECT_MASK` (../include/sound.h) before it calls.
 *
 * MASKING IN THE UNTRAPPED STORES WAS MEASURED AND DECLINED, and the measurement is kept because
 * it is the argument the twin's five store pairs still rest on. `(uint8_t)(reg & 15)` compiled to
 * the SAME BYTES — GCC proved every call site's register number small at every inlined site and
 * folded the `and` away; `core_sound.o` came back byte-identical at 5,090 B (measured 2026-09-07).
 * What has a surface now is the trapped door's half: `build.sh` pins the `andi.l` in
 * `bg_super_gate_entry`, so THAT door cannot quietly start or stop masking, and the twin's stores
 * are held by the transcription pin in `test/test_sound_asm.py`.
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

/* Every write a CORE makes is a user-mode write, and there is exactly one path for it. The
 * supervisor-side path is not a branch here and not a function here: it is the twin's own
 * transcribed store pairs (see this file's header). */
static inline void psg_port_write(unsigned reg, uint8_t value) {
    bg_super_gate(BG_GATE_PSG_WRITE, reg, value);
}

static inline uint8_t psg_port_read(unsigned reg) {
    return (uint8_t)bg_super_gate(BG_GATE_PSG_READ, reg, 0);
}

#endif /* BUBBLEGHOST_SHIM_PSG_H */
