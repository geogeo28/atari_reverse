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
#define PALETTE_PENS           16u   /* the shifter's 16 colour registers, uploaded as 8 longs */
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

/* ---- the hardware these handlers touch, which the memory image cannot hold -------------------- */
#define HW_PALETTE_BASE 0xff8240u  /* the shifter's colour registers, one word each */
#define HW_MFP_ISRB     0xfffa0fu  /* MFP interrupt-in-service B; bit 0 is Timer B */
#define MFP_ISRB_TIMER_B_BIT 0u

/* THE HARDWARE STORES, IN A TRANSLATION UNIT OF THEIR OWN.
 *
 * `$ff8240..` and `$fffa0f` are outside the 1 MiB memory image, so no differential can hold them:
 * the oracle DROPS an off-image write (`shim.c`'s memory callbacks) and a reconstruction storing
 * through `image + addr` would index past the buffer. The kit has an ordered ledger for the
 * YM2149's two ports (`psg.h`) and none for any other hardware address, so this half of every
 * handler below is UNPINNED — recorded per row in STATUS.md, with the surface that would catch it.
 *
 * `src/irq_hw_offtarget.c` defines all three, empty, and is the file a build for the real Atari
 * does NOT compile — the same split `tools/recreate_kit/src/psg.c` uses for the one hardware
 * surface the kit does model. Read that file's header for the whole argument.
 */
void shifter_write_palette(const uint8_t *image, unsigned first_pen, unsigned pens,
                           uint32_t shadow);
void shifter_clear_pen0(void);
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
