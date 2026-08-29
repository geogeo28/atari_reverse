/* zynaps_target.h — the shim's own cross-translation-unit surface.
 *
 * Three files make up the shim — `zynaps_os.s`, `zynaps_main.c`, `zynaps_backend.c` — and this is
 * everything they hand each other. Nothing here exists off target: the differential build never
 * sees this directory, and no core includes this file.
 *
 * `tos.h` is the neighbouring header and the split is by WHO IMPLEMENTS: tos.h is what zynaps_os.s
 * provides (traps and machine primitives), this is what the two C files provide.
 */
#ifndef ZYNAPS_TARGET_H
#define ZYNAPS_TARGET_H

#include <stdint.h>

#include "irq.h"     /* HW_PALETTE_BASE — the shifter's colour registers, in the SHORT form */

/* ---- the machine's addresses, in the form a C pointer needs ------------------------------------
 *
 * The 68000 ignores address bits 31-24, so `$ff8240` and `$ffff8240` are one address — but a C
 * pointer has to name the one the CPU puts on the bus. The kit's and the project's headers spell
 * the SHORT form, because that is what a reconstruction's own constant says; this is the arithmetic
 * that turns one into the other, and it is HERE rather than in each .c because both shim
 * translation units need it and CLAUDE.md §5 says a value used across files gets one definition.
 * ============================================================================================= */
#define HW_BUS_HIGH_BITS 0xff000000u
#define HW_BUS(addr) ((uint32_t)((addr) | HW_BUS_HIGH_BITS))

/* One shifter colour register is a word. */
#define SHIFTER_PEN_BYTES 2u

/* ...and where pen `n` lives. FOUR loops walk the sixteen colour registers — two in zynaps_main.c
 * (reading them back and putting TOS's back) and two in zynaps_backend.c (the handlers' upload and
 * pen 0's blank) — and this is the address arithmetic all of them share. It is one definition
 * because getting it wrong by one is this workspace's most expensive on-target defect: a loop that
 * runs one register long writes $ff8260, the RESOLUTION register, and hangs the machine
 * (docs/on-target-execution.md class 6). */
static inline uint32_t shifter_pen_register(unsigned pen) {
    return HW_BUS(HW_PALETTE_BASE) + pen * SHIFTER_PEN_BYTES;
}

/* ---- zynaps_main.c, for zynaps_os.s ----------------------------------------------------------- */

/* `_start` calls this, and its `rts` is followed by Pterm0. */
void zynaps_main(void);

/* The supervisor stack pointer `_start`'s own `Super(0)` handed back, written from the assembly and
 * read by `zynaps_main`'s hand-back. It is a longword and not a token: docs/on-target-execution.md
 * class 9 is why the way out is `zy_leave_supervisor` and not a second `Super`. */
extern void *zy_saved_ssp;

/* The C halves of the two exception entries in zynaps_os.s. Each bumps its count and calls the
 * verified handler in ../src/irq.c. */
void zy_vbl_tick(void);
void zy_timer_b_tick(void);

/* Vertical blanks and Timer B interrupts this run has taken. `volatile` because every reader is a
 * spin loop whose only way out is the interrupt itself; both are published in STATE.BIN, and the
 * Timer B one is expected to be 0 (nothing in M1 starts an MFP timer). */
extern volatile uint32_t zy_vbl_ticks;
extern volatile uint32_t zy_timer_b_ticks;

/* ---- zynaps_backend.c, for zynaps_main.c ------------------------------------------------------ */

/* What the seam's target half actually did, so a run that touched no hardware is separable from one
 * whose writes went somewhere unexpected. `zy_psg_refused` counts a register outside 0..15 — the
 * kit's `psg_port_write` refuses rather than masking, and so does this. All three are in the
 * record. */
extern volatile uint32_t zy_psg_writes;
extern volatile uint32_t zy_psg_refused;
extern volatile uint32_t zy_hw_writes;

/* ---- ../src/video.c's glue, which has no header of its own ------------------------------------ */

/* `g_set_palette_title` clears video.c's shifter sink, calls the verified `set_palette_title`, and
 * writes the eight longwords the CORE's own loop produced to the image at `result`. The shim reads
 * them back from there and pushes them to $ff8240, so a mutation inside the core reaches the screen
 * instead of being mirrored by a shim that recomputed the same answer.
 *
 * WHY IT IS DECLARED HERE. The `g_*` glue exists to be dlsym'd by the differential harness and has
 * no header by design — ../README.md gives headers to the cores only. One declaration in the shim's
 * own header, with this paragraph beside it, beats a new header in ../include that nobody else
 * would include and that the layout rules say belongs to a subsystem owner. If the signature ever
 * moves, the link fails rather than the machine. */
void g_set_palette_title(uint8_t *image, uint32_t result);

#endif /* ZYNAPS_TARGET_H */
