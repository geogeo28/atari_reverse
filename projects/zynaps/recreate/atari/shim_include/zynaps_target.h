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

#include "video.h"   /* HW_PALETTE_BASE — the shifter's colour registers, in the SHORT form */

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

/* Where the shifter's base register takes its two bytes from, as shifts of the address, and the
 * span of the address each covers. An STF has NO LOW BYTE — $ff8201 and $ff8203 hold bits 23-16 and
 * 15-8 and there is no third register — so an address that is not 256-byte aligned is truncated and
 * the shifter displays from up to 255 bytes below where the program drew
 * (docs/on-target-execution.md class 8). Both shim translation units need these: the backend
 * assembles the published offset out of them and zynaps_main.c reads the register back. */
#define VIDEO_BASE_HIGH_SHIFT 16
#define VIDEO_BASE_MID_SHIFT   8
#define VIDEO_BASE_HIGH_MASK 0x00ff0000u
#define VIDEO_BASE_MID_MASK  0x0000ff00u

/* ...and where pen `n` lives. FOUR loops walk the sixteen colour registers — two in zynaps_main.c
 * (reading them back and putting TOS's back) and two in zynaps_backend.c (the handlers' upload and
 * pen 0's blank) — and this is the address arithmetic all of them share. It is one definition
 * because getting it wrong by one is this workspace's most expensive on-target defect: a loop that
 * runs one register long writes $ff8260, the RESOLUTION register, and hangs the machine
 * (docs/on-target-execution.md class 6). */
static inline uint32_t shifter_pen_register(unsigned pen) {
    return HW_BUS(HW_PALETTE_BASE) + pen * SHIFTER_PEN_BYTES;
}

/* ---- the image, and the ONE address a relocated image cannot publish for itself ----------------
 *
 * The cores index a flat image at Ghidra addresses; on target that is a 1 MiB `.bss` array whose
 * base is rounded up to 256 at run time. `zynaps_main.c` owns the array and this pointer; the
 * BACKEND reads it, and that is the whole of why the pointer is shared.
 *
 * `screen_flip_buffers` (../src/video.c) publishes two bytes of an IMAGE OFFSET to the shifter's
 * base register — exactly right in the differential's world, where the image IS the machine's
 * memory and starts at 0, and exactly right on the original, whose framebuffers are absolute
 * against the base it runs at. Here the shifter needs `zy_image_base + offset`, and the core has no
 * way to know that: it is handed a `uint8_t *` and writes what the original writes.
 *
 * SO THE TRANSLATION LIVES IN THE HARDWARE DOOR, which is where every other image-to-machine
 * question already lives and the one place the CORE ITSELF REACHES. M1 re-published the machine
 * address from the shim after the boot slice, which worked only because the boot flips once;
 * the frame loop flips every frame, so a re-publish after the fact stops being an arrangement at
 * all. `zynaps_backend.c`'s `hw_write8` recognises the shifter's two base bytes, keeps the offset
 * the cores have published so far, and stores the translated address — so a flip from inside the
 * frame loop lands on the right memory with no shim in the path. */
extern uint8_t *zy_image_base;

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
 * kit's `psg_port_write` refuses rather than masking, and so does this. All of them are in the
 * record. */
extern volatile uint32_t zy_psg_writes;
extern volatile uint32_t zy_psg_refused;
extern volatile uint32_t zy_hw_writes;

/* THE THREE CORE EFFECTS THE MACHINE CANNOT BE ASKED ABOUT AFTERWARDS, counted as they go past the
 * hardware doors; zynaps_backend.c says what keys each one and why the shim's own traffic cannot
 * forge it. Off target the kit's ordered write ledger holds all three and `harness.differential`
 * compares it entry for entry, so these exist only on this side of the seam.
 *
 *   zy_shifter_mode_writes  `andi.b #$fc,$ff8260` at 0x10056 — 1 for the boot
 *   zy_palette_long_writes  `movem.l #$00ff,$ff8240.l` at the end of `set_palette_title` — 8 longs
 *   zy_acia_bytes_sent      `move.b d0,$fffc02` in `ikbd_send_cmd` — 2, one per boot command
 */
extern volatile uint32_t zy_shifter_mode_writes;
extern volatile uint32_t zy_palette_long_writes;
extern volatile uint32_t zy_acia_bytes_sent;

/* Read-modify-writes the cores made through the three doors. It says the seam is real: a build in
 * which the kit's own off-target `src/hw.c` had been linked instead would show 0. */
extern volatile uint32_t zy_rmw_stores;

/* The video-base door's own account: the IMAGE offset the cores last published, the MACHINE address
 * it was translated to, and how many times the pair was stored. `zy_video_base_published` is what
 * the register read-back at the anchor must equal, which is the surface for a translation that
 * silently stopped happening. */
extern volatile uint32_t zy_video_base_offset;
extern volatile uint32_t zy_video_base_published;
extern volatile uint32_t zy_video_base_publishes;

/* THE THREE READ-MODIFY-WRITE DOORS ARE NOT DECLARED HERE, and that is deliberate:
 * `tools/recreate_kit/include/hw.h` declares `hw_bset8`/`hw_bclr8`/`hw_and8` beside `hw_write8`
 * now (kit commit 2db68f6), the cores call them, and zynaps_backend.c defines them for the machine.
 * A second declaration in this header would be a second contract for one name.
 */

/* ---- zynaps_main.c, for zynaps_os.s: the third interrupt entry's C half ----------------------- */
void zy_acia_tick(void);
extern volatile uint32_t zy_acia_ticks;

#endif /* ZYNAPS_TARGET_H */
