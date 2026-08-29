/* irq.h — the game's interrupt handlers (src/irq.c). Subsystem: interrupt.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 *
 * There are two VBL/Timer-B pairs plus the attract mode's own: `_start` installs whichever pair the
 * screen it is about to show needs. All of them end in `rte`, so a test enters them around an
 * interrupt frame (test/abi.py, `interrupt_frame_pokes`).
 */
#ifndef ZYNAPS_IRQ_H
#define ZYNAPS_IRQ_H

#include <stdint.h>

/* ---- the flags and counters the handlers tick ------------------------------------------------ */
#define A_vsync_flag 0x198abu  /* .b — set by the frame loop, cleared here; the frame's own sync */

/* The 16-word shadow the raster split uploads, and the two colour-cycle machines that live INSIDE
 * it — `A_palette_cycle_words` is pens 6..10 and `A_palette_swap_long` pens 11 and 12, so cycling
 * them is cycling the colours the next upload will push. */
#define A_palette_hw_shadow    0x18fc4u
#define A_palette_cycle_words  0x18fd0u
#define A_palette_swap_long    0x18fdau
/* PALETTE_PENS is include/video.h's, with the rest of the shifter's geometry — one register block,
 * one home. It is named here only because this subsystem's shadows are sixteen pens wide. */
#define PALETTE_CYCLE_WORDS    5u    /* 0x18fd0..0x18fd8 rotate by one every countdown */

#define A_palette_swap_countdown   0x19683u  /* .b — frames until the swap long flips its halves */
#define A_palette_rotate_countdown 0x19684u  /* .b — ...and until the five words rotate */
#define PALETTE_SWAP_PERIOD    8u    /* `move.b #$8,$19683` — reloaded after each swap */
#define PALETTE_ROTATE_PERIOD  4u    /* `move.b #$4,$19684` */

/* ---- the menu VBL's own palette and its two-frame sync ---------------------------------------
 *
 * A SECOND sixteen-pen shadow, uploaded by the title/menu VBL as its own eight `move.l`s — the same
 * sixteen registers as the raster split above, from a different source. Beside it, a phase counter
 * the menu loop waits on: the flag is cleared every SECOND frame, so the menu runs at half rate.
 */
#define A_menu_palette      0x19f46u
#define A_vbl_wait_flag     0x198a7u  /* .b — cleared on the phase the menu loop is waiting for */
#define A_raster_phase      0x198a8u  /* .b — counts 0, 1, 0, ... */
#define RASTER_PHASE_PERIOD 2u        /* `cmpi.b #$2` — the count the phase wraps at */

/* ---- attract mode's colour bars --------------------------------------------------------------
 *
 * A list of {count, colour} word pairs walked one scanline at a time: each Timer B decrements the
 * count IN PLACE and, when it reaches zero, writes the colour and steps the pointer past the pair.
 */
#define A_attract_raster_line     0x19f22u  /* .w — which scanline of the bar band this is */
#define A_attract_raster_list_ptr 0x19f24u  /* .l — the cursor into the list */
#define A_attract_raster_list     0x1a976u  /* what the VBL rewinds that cursor to */
#define ATTRACT_BAR_FIRST_LINE 1u     /* `cmpi.w #$1` + `blt` — before this, colour 0 is forced */
#define ATTRACT_BAR_LAST_LINE  0x27u  /* `cmpi.w #$27` + `bge` — and at or after it, likewise */

/* ---- the hardware these handlers touch, which the memory image cannot hold --------------------
 * The shifter's own constants — its colour-register base and the two widths the row goes up in —
 * are include/video.h's, because that is where the other two routines writing those registers live
 * and one register block has one home. Only the MFP's is this subsystem's.
 */
#define HW_MFP_ISRB     0xfffa0fu  /* MFP interrupt-in-service B; bit 0 is Timer B */
#define MFP_ISRB_TIMER_B_BIT 0u

/* THE HARDWARE STORES ARE PINNED, through the kit's hardware WRITE ledger.
 *
 * `$fffa0f` (here) and `$ff8240..` (include/video.h, which owns the shifter) are outside the 1 MiB
 * memory image, so no BYTE DIFF can hold them: the oracle drops such a store and a reconstruction
 * storing through `image + addr` would index past the buffer. What holds them is
 * `tools/recreate_kit/include/hw.h`'s `hw_write8/16/32` — an ordered (address, width, value) ledger
 * both sides keep and `harness.differential` compares entry for entry, the shape `psg.h` has always
 * had for the YM2149's two ports (kit TRAP_MODEL.md, "Phase 10"). Deleting one of these calls,
 * aiming it at the wrong register, or storing a word where the original stores a longword is a red.
 *
 * THE ONE RESIDUAL IS THIS ONE'S VALUE, and it is an ON-TARGET DEFECT and not merely an unpinned
 * byte. `bclr #0,$fffa0f` is a read-modify-write; off target the oracle's read of an address the
 * seeded READ model does not name answers a fabricated 0, so both sides store 0 and agree — but on
 * the machine that store acknowledges EVERY in-service bit rather than Timer B's. A Zynaps build
 * for the real Atari must not ship this expression; hw.h's "WHAT THIS SEAM DOES NOT GIVE YOU IS A
 * READ-MODIFY-WRITE" states the rule once, for every game, and STATUS.md carries the residual.
 *
 * `mfp_ack_timer_b` is an ordinary function in src/irq.c now: `hw_write*` is the seam, and a build
 * for the real Atari supplies it as the real `*(volatile uint8_t *)addr = value` store — a BYTE
 * store, because $fffa10 is the MFP's timer-A data register and a widened one would clobber it —
 * instead of compiling the kit's src/hw.c. (There used to be a src/irq_hw_offtarget.c holding three
 * EMPTY bodies for exactly that split; with a ledger to write through there is nothing empty left.)
 */
void mfp_ack_timer_b(void);

/* ---- the handlers ---------------------------------------------------------------------------- */
void vbl_isr(uint8_t *image);
void timer_b_isr(uint8_t *image);
void vbl_isr_title(uint8_t *image);
void timer_b_raster_isr(uint8_t *image);
void attract_vbl_isr(uint8_t *image);
void attract_rasterbar_isr(uint8_t *image);
void vbl_menu(uint8_t *image);

#endif /* ZYNAPS_IRQ_H */
