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
/* THE TWO BIT NAMES BELOW HAVE NO OFF-TARGET READER, and that is the residual rather than dead
 * code: both acknowledges are `bclr` read-modify-writes whose read half answers a fabricated 0 here,
 * so what the reconstruction stores is a plain 0 and the bit number never reaches an expression.
 * ON TARGET they do have one — `atari/zynaps_backend.c` reads `MFP_ISRB_TIMER_B_BIT` to build the
 * real read-modify-write — which is exactly why both are named. */
#define HW_MFP_ISRA     0xfffa0fu  /* MFP interrupt-in-service A; bit 0 is Timer B */
#define MFP_ISRA_TIMER_B_BIT 0u
#define HW_MFP_ISRB     0xfffa11u  /* ...and in-service B; bit 6 is the keyboard/MIDI ACIA */
/* MFP CHANNEL 6 IS THE KEYBOARD ACIA, and that one number is bit 6 of every B register — the
 * in-service one this handler acknowledges AND the enable/mask pair `_start` opens it up in
 * (src/init.c's `boot_enable_interrupts`, through `$fffa09`/`$fffa15`). One channel, one name. */
#define MFP_ACIA_CHANNEL_BIT 6u
/* `btst #4,$fffffa01` — GPIP bit 4 is the ACIA interrupt line, and it is ACTIVE LOW: the bit reads
 * CLEAR while the keyboard controller still has a byte waiting, which is what sends the handler
 * round again. The address is `OS_HW_MFP_GPIP`, the kit's, because both models must spell it. */
#define MFP_GPIP_ACIA_IDLE 0x10u

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
/* `bclr #6,$fffa11` — the same shape one register over, and it needs its own function for
 * `mfp_ack_timer_b`'s reason and not for tidiness: a build for the real Atari overrides these two
 * with the genuine read-modify-write, and an acknowledge INLINED into its handler has no seam to
 * override. Off target both store a plain 0, which is the residual this header states above. */
void mfp_ack_acia(void);

/* ================================================================================================
 * The IKBD ACIA handler's own state — ikbd_acia_isr @ 0x14456.
 *
 * The keyboard controller sends TWO kinds of byte down one wire, and these four addresses are how
 * the handler tells them apart. A joystick report arrives as a three-byte packet — a `0xfd` header
 * and then one state byte per stick — so the header arms a countdown and the two bytes after it are
 * written through a cursor; anything else is a key scancode, stored on the press and cleared again
 * by its matching release.
 *
 * `A_key_scancode` USED TO LIVE IN include/init.h, borrowed by subject while nothing here wrote it.
 * This handler is what writes it, so the definition moved to its owner and init.c borrows it back
 * (STATUS.md, "## Borrowed globals").
 * ============================================================================================= */
#define A_ikbd_packet_ptr       0x195d4u  /* .l — names.txt; where the next packet byte goes */
#define A_ikbd_packet_remaining 0x19671u  /* .b — names.txt; bytes still to come in this packet */
#define A_ikbd_joystick_state   0x19680u  /* .b x2 — where a report's two state bytes land */
/* The SECOND of that pair — joystick 1, the stick the game actually reads, with the fire button in
 * bit 7. names.txt names it separately (`joystick_state`) and so does this header, because three
 * waits in src/init.c spin on THIS byte rather than on the packet's base. */
#define A_joystick_state        0x19681u
#define A_key_scancode          0x19685u  /* .b — names.txt; the key currently held down */

/* The header byte the controller prefixes a joystick report with, and how many bytes follow it.
 * `move.b #$2,$19671` is the count, and it is the ONE reload site — the cursor rewinds to
 * `A_ikbd_joystick_state` when the countdown reaches zero, so the two bytes always land at 0x19680
 * and 0x19681 however many reports arrive. */
#define IKBD_JOYSTICK_HEADER 0xfdu
#define IKBD_JOYSTICK_PACKET_BYTES 2u

/* The ACIA status bits the handler tests on entry, one after the other: `btst #7` (the 6850 is the
 * reason we are here at all) and then `btst #0` (…and it has a byte). `OS_ACIA_TX_RDY`, the third
 * bit of this register anyone in this project names, is the kit's, in os.h beside the address. */
#define ACIA_STATUS_IRQ 0x80u
#define ACIA_STATUS_RX_FULL 0x01u

/* `bclr #7,d1` — a scancode with bit 7 set is a RELEASE, and the release's own code is the press
 * code with that bit taken back off. */
#define KEY_RELEASE_BIT 0x80u

/* WHY THE RE-ENTRY LOOP HAS A CAP, WHEN THE ORIGINAL HAS NONE — src/input.c's argument for
 * `IKBD_TX_POLL_MAX`, one register over, and the same split. The GPIP is STATIC in the kit's seeded
 * read model, so a run declaring bit 4 CLEAR ("another byte is waiting") would send both sides round
 * for ever: the machine would have raised the line when the controller ran dry and the model has no
 * way to say so. The oracle's instruction cap ends its spin and the run is thrown away; the
 * candidate has no such cap, and a hung suite is worse evidence than a red one. So the loop gives up
 * and tallies a refusal, which `harness.differential` turns into a named failure.
 *
 * The number is small on purpose: under any declaration the model can serve, the loop leaves on its
 * FIRST test of the GPIP, so anything above one is already unreachable. AND IT MUST NOT BIND ON
 * TARGET — a real 6301 sending a three-byte packet raises the line three times, and a build that
 * kept a cap here would drop the tail of every report. The split is the kit's own
 * `OS_NO_REFUSAL_TALLY`, exactly as src/input.c does it. */
#define IKBD_ISR_REENTRY_MAX 4u

/* ---- the handlers ---------------------------------------------------------------------------- */
void vbl_isr(uint8_t *image);
void ikbd_acia_isr(uint8_t *image);
void timer_b_isr(uint8_t *image);
void vbl_isr_title(uint8_t *image);
void timer_b_raster_isr(uint8_t *image);
void attract_vbl_isr(uint8_t *image);
void attract_rasterbar_isr(uint8_t *image);
void vbl_menu(uint8_t *image);

#endif /* ZYNAPS_IRQ_H */
