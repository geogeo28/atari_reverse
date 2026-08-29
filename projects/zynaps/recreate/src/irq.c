/* irq.c — the VBL and Timer B handlers.
 *
 * Three pairs, installed by whichever screen is running: the in-game pair (0x10776 / 0x10782), the
 * title pair (0x106a2 / 0x106ae, whose Timer B does the raster palette split and the colour
 * cycling), and attract mode's (0x12c9e / 0x12cc0, which paints a band of colour bars a scanline at
 * a time). Every one of them returns with `rte`.
 *
 * WHAT THE DIFFERENTIAL HOLDS HERE. The flags, the counters, the shadow palette and the colour-bar
 * list are all in the image and fully compared; `sound_tick`'s chip traffic is compared through the
 * kit's PSG ledger; and the shifter and MFP stores are compared through the kit's hardware WRITE
 * ledger — see include/irq.h, which also names the one residual that leaves.
 */
#include "machine.h"
#include "hw.h"        /* the kit's hardware read and write ledgers — include/irq.h says what each pins */
#include "os.h"        /* OS_HW_ACIA_STATUS / OS_HW_ACIA_DATA / OS_HW_MFP_GPIP, and os_refused */
#include "irq.h"
#include "sound.h"
#include "util.h"      /* REGISTER_SWAP_BITS — the count machine.h's rotate needs to be a `swap` */
#include "video.h"     /* the shifter's own stores and its geometry — see include/irq.h */

/* `bclr #0,$fffa0f.l` — acknowledge Timer B in the MFP's in-service register B.
 *
 * A read-modify-write of a register the kit's seeded READ model does not name: off target the read
 * answers a fabricated 0, so this stores 0 and both sides agree, while on the machine that
 * acknowledges every in-service bit rather than Timer B's. include/irq.h states that residual and
 * says a target build must not ship this expression. The shifter's stores live in src/video.c, with
 * the registers they name. */
void mfp_ack_timer_b(void) {
    hw_write8(HW_MFP_ISRA, 0);
}

/* `bclr #6,$fffa11.l` — the keyboard ACIA's own acknowledge, in the OTHER in-service register.
 * Same residual, same reason, and a separate function so a target build has the same seam to
 * override that `mfp_ack_timer_b` gives it. */
void mfp_ack_acia(void) {
    hw_write8(HW_MFP_ISRB, 0);
}


/* ================================================================================================
 * The in-game pair — vbl_isr @ 0x10776, timer_b_isr @ 0x10782
 * ============================================================================================= */

/* THE ONLY HANDLER WITH NO HARDWARE STORE AT ALL, which is why it is the one that is verified end
 * to end: it clears the frame's sync flag (the frame loop spins on it) and runs the sound driver. */
void vbl_isr(uint8_t *image) {
    image[A_vsync_flag] = 0;
    sound_tick(image);
}

/* The same flag, but no sound: this pair is installed where Timer B is the frame's heartbeat, so
 * the flag is cleared here instead and the driver runs off the VBL as usual. */
void timer_b_isr(uint8_t *image) {
    image[A_vsync_flag] = 0;
    mfp_ack_timer_b();
}

/* ================================================================================================
 * The title pair — vbl_isr_title @ 0x106a2, timer_b_raster_isr @ 0x106ae
 * ============================================================================================= */

/* Tick the sound and blank pen 0 for the top of the frame; the Timer B below repaints all sixteen
 * pens at the split. No sync flag: the title screen's own loop waits on the raster phase instead. */
void vbl_isr_title(uint8_t *image) {
    sound_tick(image);
    shifter_clear_pen0();
}

/* Rotate the five cycle words right by one, the last becoming the first. Spelt as the original's
 * chain of `move.w`s rather than as a memmove because it walks DOWNWARD through overlapping words
 * — each store overwrites the source of the store after it, so the direction is the algorithm. */
static void rotate_cycle_words(uint8_t *image) {
    uint16_t last = be16(image + A_palette_cycle_words + 2 * (PALETTE_CYCLE_WORDS - 1));

    for (unsigned word = PALETTE_CYCLE_WORDS - 1; word > 0; word--)
        wr16(image + A_palette_cycle_words + 2 * word,
             be16(image + A_palette_cycle_words + 2 * (word - 1)));
    wr16(image + A_palette_cycle_words, last);
}

/* Count a countdown byte down and, when it lands on zero, reload it. Returns whether it fired.
 *
 * `subq.b` then `bne`: the byte is decremented in place whether or not it fires, so a countdown of
 * 0 wraps to 0xff and takes 255 more frames rather than firing at once. */
static int countdown_elapsed(uint8_t *image, uint32_t counter, uint8_t period) {
    image[counter] = (uint8_t)(image[counter] - 1);
    if (image[counter] != 0)
        return 0;
    image[counter] = period;
    return 1;
}

/* The raster split: repaint every pen from the shadow, then advance the two colour cycles.
 *
 * THE ORDER IS UPLOAD-THEN-CYCLE, so what reaches the screen this frame is last frame's cycle
 * state — the same one-frame lag the sound driver's flush has, and for the same reason: the split
 * has to happen at a fixed point in the raster, not after a variable amount of work. */
void timer_b_raster_isr(uint8_t *image) {
    shifter_upload_palette_longs(image, A_palette_hw_shadow);

    if (countdown_elapsed(image, A_palette_swap_countdown, PALETTE_SWAP_PERIOD))
        wr32(image + A_palette_swap_long,                                 /* `swap d7` */
             rotate_left32(be32(image + A_palette_swap_long), REGISTER_SWAP_BITS));
    if (countdown_elapsed(image, A_palette_rotate_countdown, PALETTE_ROTATE_PERIOD))
        rotate_cycle_words(image);
    mfp_ack_timer_b();
}

/* ================================================================================================
 * Attract mode — attract_vbl_isr @ 0x12c9e, attract_rasterbar_isr @ 0x12cc0
 * ============================================================================================= */

/* Rewind the bar band for the new frame: line 0, pen 0 black, the list cursor back to its start. */
void attract_vbl_isr(uint8_t *image) {
    wr16(image + A_attract_raster_line, 0);
    image[A_vsync_flag] = 0;
    shifter_clear_pen0();
    wr32(image + A_attract_raster_list_ptr, A_attract_raster_list);
    sound_tick(image);
}

/* One scanline of the colour-bar band.
 *
 * Outside the band (before line 1, or at line 0x27 and after) pen 0 is forced black and nothing
 * else happens — those two arms differ only in a delay loop the original runs on the late one to
 * push the store past the visible edge, which has no memory effect and so is not reconstructed.
 *
 * Inside it, the list's leading count word is decremented IN PLACE and the cursor is advanced past
 * the pair ONLY when that count reaches zero. So the count is destroyed as the band is drawn, which
 * is what the VBL's rewind above is for — and it means a bar list is single-use per pass, not
 * re-read. */
void attract_rasterbar_isr(uint8_t *image) {
    uint16_t line = (uint16_t)(be16(image + A_attract_raster_line) + 1);
    uint32_t cursor;

    wr16(image + A_attract_raster_line, line);
    if ((int16_t)line < (int16_t)ATTRACT_BAR_FIRST_LINE
        || (int16_t)line >= (int16_t)ATTRACT_BAR_LAST_LINE) {
        shifter_clear_pen0();
        mfp_ack_timer_b();
        return;
    }

    cursor = be32(image + A_attract_raster_list_ptr);
    wr16(image + cursor, (uint16_t)(be16(image + cursor) - 1));
    if (be16(image + cursor) == 0) {
        /* The colour word sits after the count; the cursor steps past both. */
        shifter_write_pen(0, be16(image + addr_add(cursor, 2)));
        wr32(image + A_attract_raster_list_ptr, addr_add(cursor, 4));
    }
    mfp_ack_timer_b();
}

/* ================================================================================================
 * The title/menu VBL — vbl_menu @ 0x13c26
 * ============================================================================================= */

/* Installed on the $70 vector for the title and menu screens (0x105ca and 0x10650 set it): upload
 * the menu's own eight-pen palette, tick the raster phase, and run the sound.
 *
 * THE PHASE IS WHAT HALVES THE MENU'S FRAME RATE. It counts up and wraps at 2, and the wait flag is
 * cleared only on the wrap — so the menu loop, which spins on that flag, gets one pass per two
 * frames. Written as a count-up-and-compare rather than a toggle because that is the instruction
 * pair (`addq.b` then `cmpi.b #$2`), and the two differ on any phase byte that starts above 1. */
void vbl_menu(uint8_t *image) {
    shifter_upload_palette_longs(image, A_menu_palette);

    image[A_raster_phase] = (uint8_t)(image[A_raster_phase] + 1);
    if (image[A_raster_phase] == RASTER_PHASE_PERIOD) {
        image[A_raster_phase] = 0;
        image[A_vbl_wait_flag] = 0;
    }
    sound_tick(image);
}

/* ================================================================================================
 * The IKBD ACIA handler — ikbd_acia_isr @ 0x14456
 *
 * The one handler that is not a VBL or a Timer B: it is entered when the keyboard controller has a
 * byte for the machine, and its job is to decide what that byte was. include/irq.h describes the
 * two kinds and the four globals that tell them apart.
 *
 * WHAT IS HARDWARE HERE, and where each half is compared. The status byte and the data byte are
 * READS, through the kit's seeded read model (`OS_HW_ACIA_STATUS` carries a model default, the data
 * port is the case's to declare and is VOLATILE — one read per run, kit TRAP_MODEL.md Phase 7). The
 * acknowledge is a WRITE, through the write ledger. The GPIP test that decides whether to go round
 * again is a read too, and include/irq.h says why its loop is capped off target and must not be on.
 * ============================================================================================= */

/* One pass over the byte the controller is offering, which is everything between 0x1445a and
 * 0x144a2 and the three `bra`s that rejoin there.
 *
 * IT READS THE DATA PORT AT MOST ONCE, and that is what makes the whole handler runnable under a
 * per-run declaration: whichever arm it takes, the port is popped a single time (or not at all, when
 * the status says there is nothing to pop). */
static void ikbd_acia_service_one_byte(uint8_t *image) {
    uint8_t status = hw_read8(OS_HW_ACIA_STATUS);
    uint8_t byte;

    if (!(status & ACIA_STATUS_IRQ) || !(status & ACIA_STATUS_RX_FULL))
        return;

    /* Mid-packet: the byte belongs to a joystick report, so it goes through the cursor rather than
     * being read as a scancode. The cursor rewinds on the LAST byte, not on the header, so a report
     * always lands at `A_ikbd_joystick_state` and the one beside it. */
    if (image[A_ikbd_packet_remaining] != 0) {
        uint32_t cursor = be32(image + A_ikbd_packet_ptr);

        image[cursor] = hw_read8(OS_HW_ACIA_DATA);
        wr32(image + A_ikbd_packet_ptr, addr_add(cursor, 1));
        image[A_ikbd_packet_remaining]--;
        if (image[A_ikbd_packet_remaining] == 0)
            wr32(image + A_ikbd_packet_ptr, A_ikbd_joystick_state);
        return;
    }

    byte = hw_read8(OS_HW_ACIA_DATA);
    if (byte == IKBD_JOYSTICK_HEADER) {
        image[A_ikbd_packet_remaining] = IKBD_JOYSTICK_PACKET_BYTES;
        return;
    }
    /* `cmp.b #$fd,d1 / bmi` — the release arm is chosen by the SIGN OF THE DIFFERENCE and not by
     * bit 7 of the byte, and the two disagree at both ends of the range: 0x7d..0x7f are press codes
     * that take the release arm, and 0xfe/0xff are release codes that are stored as presses. That is
     * the instruction, so it is transcribed as the instruction; the keyboard sends none of the five. */
    if ((int8_t)(uint8_t)(byte - IKBD_JOYSTICK_HEADER) < 0) {
        uint8_t released = (uint8_t)(byte & (uint8_t)~KEY_RELEASE_BIT);

        if (released == image[A_key_scancode])
            image[A_key_scancode] = 0;
        return;
    }
    image[A_key_scancode] = byte;
}

/* ikbd_acia_isr @ 0x14456 — service bytes until the controller lowers its interrupt line, then
 * acknowledge it in the MFP.
 *
 * `bclr #6,$fffa11` has `mfp_ack_timer_b`'s residual, one register over and for the same reason:
 * the read half of the read-modify-write answers a fabricated 0 off target, so this stores 0 and the
 * ledger holds the address and the width while the BIT stays unpinned — and on the machine that
 * store acknowledges every in-service bit rather than the ACIA's. include/irq.h states the rule. */
void ikbd_acia_isr(uint8_t *image) {
    for (unsigned pass = 0; ; pass++) {
        ikbd_acia_service_one_byte(image);
        if (hw_read8(OS_HW_MFP_GPIP) & MFP_GPIP_ACIA_IDLE)
            break;
#ifndef OS_NO_REFUSAL_TALLY
        /* OFF TARGET ONLY — include/irq.h says why the bound must not survive into a target build. */
        if (pass + 1 >= IKBD_ISR_REENTRY_MAX) {
            os_refused(0);
            break;
        }
#endif
    }
    mfp_ack_acia();
}

/* Register map: none. Every handler is entered on an interrupt, so nothing is passed in and the
 * three that touch registers save and restore them (`movem.l` at both ends of the attract pair,
 * a `move.l d7,-(a7)` around each cycle in the raster split). */
void g_vbl_isr(uint8_t *image) { vbl_isr(image); }
void g_ikbd_acia_isr(uint8_t *image) { ikbd_acia_isr(image); }
void g_timer_b_isr(uint8_t *image) { timer_b_isr(image); }
void g_vbl_isr_title(uint8_t *image) { vbl_isr_title(image); }
void g_timer_b_raster_isr(uint8_t *image) { timer_b_raster_isr(image); }
void g_attract_vbl_isr(uint8_t *image) { attract_vbl_isr(image); }
void g_attract_rasterbar_isr(uint8_t *image) { attract_rasterbar_isr(image); }
void g_vbl_menu(uint8_t *image) { vbl_menu(image); }
