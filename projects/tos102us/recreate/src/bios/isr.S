/* isr.S — the four INTERRUPT HANDLERS as the machine reaches them: THE ROM'S OWN INSTRUCTIONS, byte for byte.
 *
 * WHY THIS IS ASSEMBLY, which is `trap.S`'s argument one exception class further out. A handler is
 * entered by the 68000 with an exception frame on the supervisor stack and leaves through `rte`; it
 * saves and restores the interrupted program's register file with a `movem` pair whose list IS its
 * contract (the ACIA handler gives D0-D3/A0-A3/A5 back and NOTHING else — `test_bios_ikbd.py` pins
 * both halves); it acknowledges its own MFP channel after the restore, on a path the register file
 * is no longer saved across; and it reaches every system variable through an A5 it zeroes itself. A
 * C function owes none of that and has no way to say any of it.
 *
 * AND WHY THE BODIES ARE HERE TOO, where this file used to bracket a C body with the ROM's entry and
 * exit. It is the project's rule for hand-written 68000 (`include/transcribed.h`): C first — Tier 1
 * proves it — and where the C measures over Tier 3's bar, SHIP the ROM's own instructions. All three
 * bodies measured over it (the vertical blank 1.23 / 1.24, the tick 1.33, the ACIA 1.71), and a C body
 * under a handler costs two things no ratio shows:
 *
 *   * A REGISTER CONTRACT IT CANNOT KEEP. What a handler calls is a RAM vector, and the ROM gives the
 *     routine there the whole register file (its `movem.l d0-a6` bracket, and `movem.l d7/a0` round
 *     each `_vblqueue` slot). A `jsr` cannot be told to lose A6 by a CLOBBER (`include/staged_call.h`;
 *     an OUTPUT operand in A6 does tell GCC, at a cost over the bar, and is not used), and the C
 *     blank kept its queue pointer there: the VDI's cursor routine in slot 0 returns with A6 = $fd00fe
 *     whenever it redraws, and the blank after a mouse move never reached its `rte`.
 *   * A FRAME ON THE INTERRUPTED STACK. GCC saves every callee-saved register the clobber list names —
 *     40 to 52 bytes a handler, under the AES dispatcher's 640-byte private stack, where the worst
 *     nesting then overran by 60.
 *
 * TWO SYMBOLS PER HANDLER STILL:
 *
 *   `isr_vbl`        the C TWIN (`src/bios/vbl.c`) — the handler as a C function, which Tier 1's host
 *                    differential proves and `test/test_bios_vbl.py` puts its cases to. No entry here
 *                    calls it or any part of it;
 *   `isr_vbl_entry`  THIS FILE — the handler FOR vector $70 (no build stores it there yet: the ROM
 *                    build links no handler, and that store is nobody's test), held to the ROM by two
 *                    surfaces: the BYTE PIN (`test/transcription.py`'s `assert_transcribed`, each
 *                    battery's `test_the_stub_at_the_vector_is_the_rom_s_own_bytes`) and the SECOND
 *                    DIFFERENTIAL of Tier 3's numerator (`RomBench.measure_transcription`: the same
 *                    image, the same WHOLE register file and the same chip traffic as the original).
 *
 * WHAT A HANDLER CALLS BY `bsr` IS LAID OUT HERE AS WELL, each a region of the ROM's own bytes: the
 * alpha cursor's blink and the cell inversion it ends in, Scrdmp, the floppy's VBL service as far as it
 * is reconstructed, the Dosound driver's step and the keyboard's queue-a-key routine. A `bsr` or `bra` from one region to another measures
 * to where THIS file links its target, which is the one kind of word the pin lets differ — and it holds
 * each to the exact value (`Relocated`). NO CALL LEAVES FOR C: the keyboard's queue-a-key routine, which
 * timer C's auto-repeat calls and the rest of the build has as `kbd_queue_key`, is laid out here too —
 * the last routine of this file says what a thunk into the C cost.
 *
 * THE SPELLING POLICY is `include/m68k_encodings.h`'s: where GNU as would pick another encoding for the
 * ROM's instruction, the ROM's word is spelt with `.word` and the instruction is in its comment; an
 * I/O register is addressed SIGN-EXTENDED ($ffff8260), as the ROM's assembler spelt it.
 */
#include "addrs.h"
#include "m68k_encodings.h"

/* An I/O register as the ROM's absolute-long operand names it: `addrs.h` carries the 24-bit bus
 * address ($ff8260), the ROM's word the sign-extended one ($ffff8260). ADDED, not OR-ed: `|` starts a
 * comment in m68k GNU as. */
#define IO(address) ((address) + 0xff000000)

    .text

/* ---- the HORIZONTAL BLANK — vector $68, $fc06c8..$fc06de ---------------------------------------
 * All seven instructions, and no call: the body is the two that read and edit the frame's own SR
 * word. `src/bios/hbl.c` is the same three lines as C, which is what Tier 1 proves.
 *
 * The frame's SR is at 2(sp) rather than 0(sp) because of the push one line above it — the handler
 * makes room for the D0 it is about to use — so the displacement is the saved word plus the field's
 * own offset. */
#define HBL_SAVED_D0_BYTES 2

    .globl  isr_hbl_entry
isr_hbl_entry:
    move.w  %d0,-(%sp)                          /* ...so the frame starts at 2(sp) from here on */
    move.w  (HBL_SAVED_D0_BYTES + EXCEPTION_FRAME_SR,%sp),%d0
    .word   M68K_AND_W_IMMEDIATE(M68K_D0), SR_IPL_MASK      /* and.w #SR_IPL_MASK,%d0 */
    bne.s   .Lhbl_out                           /* anything at all: leave the frame as it is */
    ori.w   #HBL_IPL_FLOOR,(HBL_SAVED_D0_BYTES + EXCEPTION_FRAME_SR,%sp)
.Lhbl_out:
    move.w  (%sp)+,%d0
    rte

/* ---- the VERTICAL BLANK — vector $70, $fc06de..$fc07d0 ------------------------------------------
 * `_frclock` counts blanks that HAPPENED and is bumped before the semaphore can refuse anything;
 * `_vbclock` counts the ones this handler serviced. The semaphore is released on BOTH paths and
 * RE-READ to do it, which is why the last `addq.w` is a memory read-modify-write.
 *
 * NOTHING IS HELD IN A REGISTER ACROSS A CALL OF A RAM VECTOR: what follows `swv_vec` and the queue
 * zeroes A5 again, the queue's count and pointer are on the stack round each slot, and Scrdmp stores
 * its flag through an absolute address. `src/bios/vbl.c` has the handler's story at length. */
    .globl  isr_vbl_entry
isr_vbl_entry:
    addq.l  #1,(SYSVAR_FRCLOCK).l
    subq.w  #1,(SYSVAR_VBLSEM).l
    bmi.w   .Lvbl_release                       /* already taken: no body, and no registers saved */
    movem.l %d0-%a6,-(%sp)
    addq.l  #1,(SYSVAR_VBCLOCK).l
    suba.l  %a5,%a5
    /* the monitor follower: the shifter against the MFP's monitor bit */
    move.b  (IO(SHIFTER_RESOLUTION)).l,%d0
    .word   M68K_AND_B_IMMEDIATE(M68K_D0), GETREZ_MODE_MASK         /* and.b #GETREZ_MODE_MASK,%d0 */
    .word   M68K_CMP_B_IMMEDIATE(M68K_D0), SHIFTER_MODE_HIGH        /* cmp.b #SHIFTER_MODE_HIGH,%d0 */
    bge.s   .Lvbl_on_a_mono_resolution
    btst    #MFP_GPIP_MONOCHROME_BIT,(IO(MFP_GPIP)).l
    bne.s   .Lvbl_blink                         /* still a colour monitor */
    move.w  #SHIFTER_SETTLE_DBF_COUNT,%d0       /* the shifter is given time to settle: pure delay */
.Lvbl_settle:
    dbf     %d0,.Lvbl_settle
    move.b  #SHIFTER_MODE_HIGH,%d0
    bra.s   .Lvbl_change_resolution
.Lvbl_on_a_mono_resolution:
    btst    #MFP_GPIP_MONOCHROME_BIT,(IO(MFP_GPIP)).l
    beq.s   .Lvbl_blink                         /* still mono */
    move.b  (SYSVAR_DEFSHIFTMD,%a5),%d0
    .word   M68K_CMP_B_IMMEDIATE(M68K_D0), SHIFTER_MODE_HIGH        /* cmp.b #SHIFTER_MODE_HIGH,%d0 */
    blt.s   .Lvbl_change_resolution             /* SIGNED: a default with bit 7 set is kept */
    clr.b   %d0
.Lvbl_change_resolution:
    move.b  %d0,(SYSVAR_SSHIFTMD,%a5)
    move.b  %d0,(IO(SHIFTER_RESOLUTION)).l
    movea.l (SYSVAR_SWV_VEC,%a5),%a0
    jsr     (%a0)
.Lvbl_blink:
    bsr.w   isr_vbl_blink_cursor                /* RELOCATED: $fc4666, where this file links it */
    suba.l  %a5,%a5
    /* the palette `Setpalette` queued, and then the pointer is cleared */
    tst.l   (SYSVAR_COLORPTR,%a5)
    beq.s   .Lvbl_screen_base
    movea.l (SYSVAR_COLORPTR,%a5),%a0
    lea     (IO(SHIFTER_PALETTE)).l,%a1
    move.w  #SHIFTER_PALETTE_ENTRIES - 1,%d0
.Lvbl_colour:
    move.w  (%a0)+,(%a1)+
    dbf     %d0,.Lvbl_colour
    clr.l   (SYSVAR_COLORPTR,%a5)
.Lvbl_screen_base:
    /* the screen base `Setscreen` queued — NOT cleared, so it is programmed again every frame */
    tst.l   (SYSVAR_SCREENPT,%a5)
    beq.s   .Lvbl_floppy
    move.l  (SYSVAR_SCREENPT,%a5),(SYSVAR_V_BAS_AD,%a5)
    move.l  (SYSVAR_V_BAS_AD,%a5),%d0
    lsr.l   #SHIFTER_BASE_SHIFT,%d0
    move.b  %d0,(IO(SHIFTER_BASE_MID)).l
    lsr.w   #SHIFTER_BASE_SHIFT,%d0
    move.b  %d0,(IO(SHIFTER_BASE_HIGH)).l
.Lvbl_floppy:
    bsr.w   isr_vbl_floppy_service              /* RELOCATED: $fc1bc4 */
    /* `nvbls` slots of `_vblqueue`, each a routine or 0: D7 and A0 are on the stack round each call */
    move.w  (SYSVAR_NVBLS).l,%d7
    beq.s   .Lvbl_dump
    subq.l  #1,%d7
    movea.l (SYSVAR_VBLQUEUE).l,%a0
.Lvbl_slot:
    movea.l (%a0)+,%a1
    cmpa.l  #0,%a1
    beq.s   .Lvbl_next_slot
    movem.l %d7/%a0,-(%sp)
    jsr     (%a1)
    movem.l (%sp)+,%d7/%a0
.Lvbl_next_slot:
    dbf     %d7,.Lvbl_slot
.Lvbl_dump:
    suba.l  %a5,%a5
    tst.w   (SYSVAR_DUMPFLG,%a5)
    bne.s   .Lvbl_restore                       /* ZERO is the request, which is Alt-Help's doing */
    bsr.w   isr_vbl_scrdmp                      /* RELOCATED: $fc0d50 */
.Lvbl_restore:
    movem.l (%sp)+,%d0-%a6
.Lvbl_release:
    addq.w  #1,(SYSVAR_VBLSEM).l
    rte

/* ...XBIOS Scrdmp's whole body, $fc0d50..$fc0d62, which the blank reaches by `bsr`: call whatever
 * `scr_dump` names, THEN set `_dumpflg` — through an absolute address, so the dump may keep nothing.
 * (The XBIOS door's own Scrdmp is `xbios_scrdmp`, the C of the same four instructions.) */
    .globl  isr_vbl_scrdmp
isr_vbl_scrdmp:
    movea.l (SYSVAR_SCR_DUMP).l,%a0
    jsr     (%a0)
    move.w  #-1,(SYSVAR_DUMPFLG).l
    rts

/* ...the alpha cursor's blink, $fc4666..$fc4698. Three gates, and every store is a read-modify-write
 * that happens whether or not it changes the byte (`src/bios/vbl.c`, blink_cursor). The console block
 * is reached off its STATE FLAGS byte in A4, which the inversion below reads on from. */
#define CON(field) (field - CON_STATE_FLAGS,%a4)

    .globl  isr_vbl_blink_cursor
isr_vbl_blink_cursor:
    lea     (CON_STATE_FLAGS).l,%a4
    tst.w   CON(CON_CURSOR_DISABLE)
    bne.s   .Lblink_out                         /* the cursor is suppressed outright */
    subq.b  #1,CON(CON_BLINK_TIMER)
    bne.s   .Lblink_out                         /* ...not this frame */
    move.b  CON(CON_BLINK_RATE),CON(CON_BLINK_TIMER)
    btst    #CON_FLAG_BLINKS,(%a4)
    beq.s   .Lblink_steady
    bchg    #CON_FLAG_DRAWN,(%a4)
.Lblink_invert:
    movea.l CON(CON_CURSOR_ADDRESS),%a1
    bra.w   isr_vbl_invert_cursor_cell          /* RELOCATED: $fc4a1e */
.Lblink_steady:
    bset    #CON_FLAG_DRAWN,(%a4)               /* a cursor that does not blink is made sure of */
    beq.s   .Lblink_invert
.Lblink_out:
    rts

/* ...and the cell inversion it ends in, $fc4a1e..$fc4a42: `not.b` down one column of every bit plane,
 * A1 the cell and A4 the console block. `include/bios/vt52.h`'s console_invert_cursor_cell is the C. */
    .globl  isr_vbl_invert_cursor_cell
isr_vbl_invert_cursor_cell:
    move.w  CON(CON_LINE_BYTES),%d4
    move.w  CON(CON_CELL_HEIGHT),%d5
    subq.w  #1,%d5
    move.w  CON(CON_PLANES),%d7
    subq.w  #1,%d7
.Linvert_plane:
    movea.l %a1,%a2
    move.w  %d5,%d6
.Linvert_row:
    not.b   (%a2)
    adda.w  %d4,%a2
    dbf     %d6,.Linvert_row
    addq.w  #SCREEN_PLANE_WORD_BYTES,%a1
    dbf     %d7,.Linvert_plane
    rts

/* ...and the floppy's own VBL service, $fc1bc4, AS FAR AS IT IS RECONSTRUCTED: the five instructions
 * up to its `flock` gate ($fc1bc4..$fc1bd6) are the ROM's, and the `rts` the gate branches to is
 * where the ROM has it ($fc1c46), so the `bne.s` is the ROM's own word. EVERYTHING BETWEEN THEM IS
 * NOT RECONSTRUCTED — it drives the drive-select bits through the YM2149's port A (`src/bios/vbl.c`,
 * "WHAT IS NOT RECONSTRUCTED") — and halts as an unreconstructed arm halts on this machine: a field
 * of `trap #7`, one for every word the ROM's body has there. */
    .globl  isr_vbl_floppy_service
isr_vbl_floppy_service:
    suba.l  %a5,%a5
    lea     (IO(FDC_DMA_MODE)).l,%a6
    st      (FLOPPY_VBL_ENTERED,%a5)            /* unconditional, before anything else */
    tst.w   (SYSVAR_FLOCK,%a5)
    bne.s   .Lfloppy_return                     /* a disk operation owns the FDC: hands off */
    .fill   (VBL_FLOPPY_RETURN - VBL_FLOPPY_GATE_END) / 2, 2, M68K_TRAP_NOT_RECONSTRUCTED
.Lfloppy_return:
    rts

/* ---- the MFP's TIMER C — vector $114, $fc30c4..$fc312a, and the Dosound driver's step behind it ---
 * The divider is a ROTATE and not a counter: $4444 -> $8888 -> $1111 -> $2222 is a four-state cycle
 * with exactly one negative state, so the body runs on one tick in four. The tick count and the
 * acknowledgement are on BOTH paths — a tick that does no work still counts and still clears
 * channel 5's in-service bit, which is what keeps the channel firing. `src/bios/timerc.c` is the C. */
    .globl  isr_timer_c_entry
isr_timer_c_entry:
    addq.l  #1,(SYSVAR_HZ_200).l
    rol.w   (SYSVAR_TIMER_C_DIVIDER).l
    bpl.s   .Ltimer_c_acknowledge               /* one tick in four goes past here */
    movem.l %d0-%a6,-(%sp)
    lea     (0).l,%a5
    bsr.s   isr_timer_c_sound_step
    /* the keyboard's auto-repeat: the initial delay, then the rate, then the held key again */
    btst    #CONTERM_REPEAT_BIT,(SYSVAR_CONTERM,%a5)
    beq.s   .Ltimer_c_vector
    tst.b   (SYSVAR_KB_REPEAT_KEY,%a5)
    beq.s   .Ltimer_c_vector
    tst.b   (SYSVAR_KB_REPEAT_DELAY,%a5)
    beq.s   .Ltimer_c_repeating
    subq.b  #1,(SYSVAR_KB_REPEAT_DELAY,%a5)
    bne.s   .Ltimer_c_vector
.Ltimer_c_repeating:
    subq.b  #1,(SYSVAR_KB_REPEAT_LEFT,%a5)
    bne.s   .Ltimer_c_vector
    move.b  (KBRATE_REPEAT,%a5),(SYSVAR_KB_REPEAT_LEFT,%a5)
    move.b  (SYSVAR_KB_REPEAT_KEY,%a5),%d0
    lea     (IOREC_IKBD,%a5),%a0
    bsr.w   isr_timer_c_queue_key               /* RELOCATED: $fc2c42, where this file links it */
.Ltimer_c_vector:
    move.w  (SYSVAR_TIMR_MS,%a5),-(%sp)         /* a WORD of frame, which a C call would widen */
    movea.l (SYSVAR_ETV_TIMER,%a5),%a0
    jsr     (%a0)
    addq.w  #2,%sp
    movem.l (%sp)+,%d0-%a6
.Ltimer_c_acknowledge:
    bclr    #MFP_ISRB_TIMER_C_BIT,(IO(MFP_ISRB)).l
    rte

/* ...the Dosound driver's step, $fc312a..$fc31c2 — where the ROM has it, straight behind the handler,
 * so the `bsr.s` above is the ROM's own word. One pass of the list at `SOUND_LIST_POINTER`: register
 * writes until a command ends the tick (`src/bios/timerc.c`, step_the_sound_driver). A command byte
 * is tested AFTER an `addq.b #1`, which is why each is compared one above its own value. */
    .globl  isr_timer_c_sound_step
isr_timer_c_sound_step:
    movem.l %d0-%d1/%a0,-(%sp)
    move.l  (SOUND_LIST_POINTER,%a5),%d0
    beq.w   .Lsound_out                         /* no list */
    movea.l %d0,%a0
    move.b  (SOUND_LIST_DELAY,%a5),%d0
    beq.s   .Lsound_next
    subq.b  #1,%d0                              /* a pause still running: one tick less of it */
    move.b  %d0,(SOUND_LIST_DELAY,%a5)
    bra.s   .Lsound_out
.Lsound_next:
    move.b  (%a0)+,%d0
    bmi.s   .Lsound_command
    move.b  %d0,(IO(PSG_PORT_SELECT)).l
    cmpi.b  #PSG_MIXER_REGISTER,%d0
    bne.s   .Lsound_register
    move.b  (%a0)+,%d1                          /* the mixer: the list's channel bits, the chip's port bits */
    andi.b  #PSG_MIXER_CHANNEL_MASK,%d1
    move.b  (IO(PSG_PORT_SELECT)).l,%d0
    andi.b  #PSG_MIXER_PORT_MASK,%d0
    or.b    %d1,%d0
    move.b  %d0,(IO(PSG_PORT_DATA)).l
    bra.s   .Lsound_next
.Lsound_register:
    move.b  (%a0)+,(IO(PSG_PORT_DATA)).l
    bra.s   .Lsound_next
.Lsound_command:
    addq.b  #1,%d0
    bpl.s   .Lsound_pause
    cmpi.b  #DOSOUND_LOAD_TEMP + 1,%d0
    bne.s   .Lsound_not_a_load
    move.b  (%a0)+,(SOUND_RAMP_VALUE,%a5)
    bra.s   .Lsound_next
.Lsound_not_a_load:
    cmpi.b  #DOSOUND_RAMP + 1,%d0
    bne.s   .Lsound_pause
    move.b  (%a0)+,(IO(PSG_PORT_SELECT)).l
    move.b  (%a0)+,%d0
    add.b   %d0,(SOUND_RAMP_VALUE,%a5)
    move.b  (%a0)+,%d0
    move.b  (SOUND_RAMP_VALUE,%a5),(IO(PSG_PORT_DATA)).l
    cmp.b   (SOUND_RAMP_VALUE,%a5),%d0
    beq.s   .Lsound_store                       /* the ramp has arrived: go on past it next tick */
    subq.w  #DOSOUND_RAMP_OPERANDS,%a0          /* ...or replay the whole command */
    bra.s   .Lsound_store
.Lsound_pause:
    move.b  (%a0)+,(SOUND_LIST_DELAY,%a5)
    bne.s   .Lsound_store
    movea.w #0,%a0                              /* a pause of zero ends the list */
.Lsound_store:
    move.l  %a0,(SOUND_LIST_POINTER,%a5)
.Lsound_out:
    movem.l (%sp)+,%d0-%d1/%a0
    rts

/* ---- the ACIA channel — vector $118, $fc29ce..$fc29fc -------------------------------------------
 * The whole handler, and it calls nothing but KBDVECS' two service vectors, round and round while
 * either 6850 still wants service. THE LIST IS THE CONTRACT — D0-D3/A0-A3/A5 and nothing else — so a
 * caller of this handler gets D4-D7/A4/A6 back holding whatever the two service routines left in
 * them, which `test_bios_ikbd.py` pins in both directions. `src/bios/ikbd.c` is the C. */
    .globl  isr_acia_entry
isr_acia_entry:
    movem.l %d0-%d3/%a0-%a3/%a5,-(%sp)
    lea     (0).l,%a5
.Lacia_pass:
    movea.l (KBDVECS + KBDVECS_MIDISYS,%a5),%a2
    jsr     (%a2)
    movea.l (KBDVECS + KBDVECS_IKBDSYS,%a5),%a2
    jsr     (%a2)
    btst    #MFP_GPIP_ACIA_BIT,(IO(MFP_GPIP)).l
    beq.s   .Lacia_pass                         /* LOW: one of the two still wants service */
    bclr    #MFP_ISRB_ACIA_BIT,(IO(MFP_ISRB)).l
    movem.l (%sp)+,%d0-%d3/%a0-%a3/%a5
    rte

/* ---- the keyboard's QUEUE-A-KEY routine, $fc2c42..$fc2ea0 — what timer C's auto-repeat calls ----------
 * D0.b the scancode, A0 the IKBD's IOREC, A5 zero: the key click, the three `Keytbl` tables and the
 * CONTROL and ALTERNATE rewrites, the record into the ring — and, with Alternate held, THE MOUSE THE
 * KEYBOARD EMULATES: an arrow becomes a three-byte packet handed to KBDVECS' `mousevec`, which is the
 * VDI's mouse interrupt and the AES's glue under it. `src/bios/keyboard.c`'s `kbd_queue_key` is the C,
 * and it is what the ACIA chain's C calls (`kbd_scancode`); THIS copy is the ROM's own bytes for the
 * one caller that is an interrupt handler. A thunk into the C stood here first, and it cost the
 * interrupted stack 52 bytes on the Alt + arrow arm (196 for the ROM's 144: GCC's `movem` under a call
 * that keeps to nothing, and three argument slots) — 12 past the AES dispatcher's 640 at the worst
 * nesting.
 *
 * THE WHOLE SPAN IS ONE REGION, and two pieces of it are CARRIED AS BYTES AND NEVER ENTERED HERE:
 * `midivec`'s jump ($fc2e34) and the MIDI ring's put ($fc2e3a, which ships as `midi_queue_byte`) lie
 * between the key path and its mouse arm, and laying them out is what keeps every branch across them the
 * ROM's own word. TWO OPERANDS NAME THE ROM ITSELF AND STAY AS THEY ARE, as the C's do: the key click's
 * Dosound list and the table of the four keys Alternate reads as mouse buttons. */
#define KEY(table) (KEYTBL_STRUCT + 4 * (table),%a5)
#define KEYTBL_UNSHIFTED 0
#define KEYTBL_SHIFTED   1
#define KEYTBL_CAPSLOCK  2
#define MOUSE_BY_KEYBOARD_STEP       8          /* an arrow with Alternate: eight pixels... */
#define MOUSE_BY_KEYBOARD_FINE_STEP  1          /* ...and one with a shift key down as well */
#define ALT_DIGIT_FIRST   0x02                  /* Alternate + the top row: scancodes $78.. */
#define ALT_DIGIT_LAST    0x0d
#define ALT_DIGIT_OFFSET  0x76
#define CONTROL_MASK      0x1f

    .globl  isr_timer_c_queue_key
isr_timer_c_queue_key:
    btst    #CONTERM_CLICK_BIT,(SYSVAR_CONTERM,%a5)
    beq.s   .Lkey_translate
    move.l  #KEYCLICK_SOUND_LIST,(SOUND_LIST_POINTER,%a5)
    move.b  #0,(SOUND_LIST_DELAY,%a5)
.Lkey_translate:
    move.l  %a0,-(%sp)
    moveq   #0,%d1
    move.b  %d0,%d1
    movea.l KEY(KEYTBL_UNSHIFTED),%a0
    andi.w  #SCANCODE_INDEX_MASK,%d0
    btst    #KBSHIFT_CAPSLOCK_BIT,(KBSHIFT,%a5)
    beq.s   .Lkey_shifted
    movea.l KEY(KEYTBL_CAPSLOCK),%a0
.Lkey_shifted:
    btst    #KBSHIFT_RIGHT_SHIFT_BIT,(KBSHIFT,%a5)
    bne.s   .Lkey_with_shift
    btst    #KBSHIFT_LEFT_SHIFT_BIT,(KBSHIFT,%a5)
    beq.s   .Lkey_ascii
.Lkey_with_shift:
    cmpi.b  #SCANCODE_FUNCTION_FIRST,%d0
    bcs.s   .Lkey_shift_table
    cmpi.b  #SCANCODE_FUNCTION_LAST,%d0
    bhi.s   .Lkey_shift_table
    addi.w  #SCANCODE_FUNCTION_SHIFTED,%d1      /* a shifted function key: its own scancode, no ASCII */
    moveq   #0,%d0
    bra.w   .Lkey_record
.Lkey_shift_table:
    movea.l KEY(KEYTBL_SHIFTED),%a0
.Lkey_ascii:
    move.b  (0,%a0,%d0.w),%d0
    btst    #KBSHIFT_CONTROL_BIT,(KBSHIFT,%a5)
    beq.s   .Lkey_alternate
    cmpi.b  #0x0d,%d0                           /* CONTROL: Return becomes a line feed... */
    bne.s   .Lkey_control_home
    moveq   #0x0a,%d0
    beq.s   .Lkey_control_codes                 /* (never taken: the `moveq` has just cleared Z) */
.Lkey_control_home:
    cmpi.b  #SCANCODE_HOME,%d1
    bne.s   .Lkey_control_left
    addi.w  #CONTROL_HOME_OFFSET,%d1
    bra.w   .Lkey_record
.Lkey_control_left:
    cmpi.b  #SCANCODE_CURSOR_LEFT,%d1
    bne.s   .Lkey_control_right
    moveq   #CONTROL_CURSOR_LEFT,%d1
    moveq   #0,%d0
    bra.w   .Lkey_record
.Lkey_control_right:
    cmpi.b  #SCANCODE_CURSOR_RIGHT,%d1
    bne.s   .Lkey_control_codes
    moveq   #CONTROL_CURSOR_LEFT + 1,%d1
    moveq   #0,%d0
    bra.w   .Lkey_record
.Lkey_control_codes:
    cmpi.b  #0x32,%d0                           /* ...and `2`, `6` and `-` the codes 0, $1e and $1f */
    bne.s   .Lkey_control_six
    moveq   #0,%d0
    bra.w   .Lkey_record
.Lkey_control_six:
    cmpi.b  #0x36,%d0
    bne.s   .Lkey_control_minus
    moveq   #0x1e,%d0
    bra.w   .Lkey_record
.Lkey_control_minus:
    cmpi.b  #0x2d,%d0
    bne.s   .Lkey_control_mask
    moveq   #0x1f,%d0
    bra.w   .Lkey_record
.Lkey_control_mask:
    andi.w  #CONTROL_MASK,%d0
    bra.w   .Lkey_record
.Lkey_alternate:
    btst    #KBSHIFT_ALTERNATE_BIT,(KBSHIFT,%a5)
    beq.w   .Lkey_record
    cmpi.b  #SCANCODE_HELP,%d1
    bne.s   .Lkey_mouse_buttons
    addq.w  #1,(SYSVAR_DUMPFLG,%a5)             /* Alternate + Help: the screen dump's request */
    movea.l (%sp)+,%a0
    bra.w   .Lkey_out
.Lkey_mouse_buttons:
    lea     (ALT_MOUSE_BUTTON_KEYS).l,%a2       /* the ROM's own table, where the ROM has it */
    moveq   #ALT_MOUSE_BUTTON_KEY_COUNT - 1,%d2
.Lkey_mouse_button:
    cmp.b   (0,%a2,%d2.w),%d1
    beq.w   .Lmouse_button
    dbf     %d2,.Lkey_mouse_button
    cmpi.b  #SCANCODE_CURSOR_UP,%d1
    bne.s   .Lkey_cursor_left
    move.b  #0,%d1
    move.b  #-MOUSE_BY_KEYBOARD_STEP,%d2
    move.b  (KBSHIFT,%a5),%d0
    andi.b  #KBSHIFT_EITHER_SHIFT,%d0
    beq.w   .Lmouse_packet
    move.b  #-MOUSE_BY_KEYBOARD_FINE_STEP,%d2
    bra.w   .Lmouse_packet
.Lkey_cursor_left:
    cmpi.b  #SCANCODE_CURSOR_LEFT,%d1
    bne.s   .Lkey_cursor_right
    move.b  #0,%d2
    move.b  #-MOUSE_BY_KEYBOARD_STEP,%d1
    move.b  (KBSHIFT,%a5),%d0
    andi.b  #KBSHIFT_EITHER_SHIFT,%d0
    beq.w   .Lmouse_packet
    move.b  #-MOUSE_BY_KEYBOARD_FINE_STEP,%d1
    bra.w   .Lmouse_packet
.Lkey_cursor_right:
    cmpi.b  #SCANCODE_CURSOR_RIGHT,%d1
    bne.s   .Lkey_cursor_down
    move.b  #MOUSE_BY_KEYBOARD_STEP,%d1
    move.b  #0,%d2
    move.b  (KBSHIFT,%a5),%d0
    andi.b  #KBSHIFT_EITHER_SHIFT,%d0
    beq.w   .Lmouse_packet
    move.b  #MOUSE_BY_KEYBOARD_FINE_STEP,%d1
    bra.w   .Lmouse_packet
.Lkey_cursor_down:
    cmpi.b  #SCANCODE_CURSOR_DOWN,%d1
    bne.s   .Lkey_alt_digit
    move.b  #0,%d1
    move.b  #MOUSE_BY_KEYBOARD_STEP,%d2
    move.b  (KBSHIFT,%a5),%d0
    andi.b  #KBSHIFT_EITHER_SHIFT,%d0
    beq.w   .Lmouse_packet
    move.b  #MOUSE_BY_KEYBOARD_FINE_STEP,%d2
    bra.w   .Lmouse_packet
.Lkey_alt_digit:
    cmpi.b  #ALT_DIGIT_FIRST,%d1
    bcs.s   .Lkey_alt_letter
    cmpi.b  #ALT_DIGIT_LAST,%d1
    bhi.s   .Lkey_alt_letter
    addi.b  #ALT_DIGIT_OFFSET,%d1
    bra.s   .Lkey_no_ascii
.Lkey_alt_letter:
    cmpi.b  #'A',%d0
    bcs.s   .Lkey_alt_lower
    cmpi.b  #'Z',%d0
    bhi.s   .Lkey_alt_lower
.Lkey_no_ascii:
    moveq   #0,%d0
    bra.s   .Lkey_record
.Lkey_alt_lower:
    cmpi.b  #'a',%d0
    bcs.s   .Lkey_record
    cmpi.b  #'z',%d0
    bhi.s   .Lkey_record
    bra.s   .Lkey_no_ascii
.Lkey_record:
    asl.w   #8,%d1                              /* the record: scancode above ASCII, kbshift on top */
    add.w   %d1,%d0
    movea.l (%sp)+,%a0
    move.w  (IOREC_TAIL,%a0),%d1
    addq.w  #IOREC_KEY_BYTES,%d1
    cmp.w   (IOREC_SIZE,%a0),%d1
    bcs.s   .Lkey_tail
    moveq   #0,%d1
.Lkey_tail:
    cmp.w   (IOREC_HEAD,%a0),%d1
    beq.s   .Lkey_out                           /* the ring is full: the key is dropped */
    .word   M68K_MOVEA_L_D16(M68K_A0, M68K_A2), IOREC_BUFFER    /* movea.l IOREC_BUFFER(%a0),%a2 */
    swap    %d0
    move.w  #0,%d0
    move.b  (KBSHIFT,%a5),%d0
    swap    %d0
    lsl.l   #8,%d0
    lsr.w   #8,%d0
    btst    #CONTERM_KBSHIFT_BIT,(SYSVAR_CONTERM,%a5)
    bne.s   .Lkey_store
    andi.l  #0x00ffffff,%d0
.Lkey_store:
    move.l  %d0,(0,%a2,%d1.w)
    move.w  %d1,(IOREC_TAIL,%a0)
.Lkey_out:
    rts
    /* ...CARRIED AS BYTES, never entered here: `midivec`'s jump, and the MIDI ring's put behind it */
    movea.l (KBDVECS + KBDVECS_MIDIVEC,%a5),%a2
    jmp     (%a2)
    move.w  (IOREC_TAIL,%a0),%d1
    addq.w  #1,%d1
    cmp.w   (IOREC_SIZE,%a0),%d1
    bcs.s   .Lmidi_tail
    moveq   #0,%d1
.Lmidi_tail:
    cmp.w   (IOREC_HEAD,%a0),%d1
    beq.s   .Lmidi_out
    .word   M68K_MOVEA_L_D16(M68K_A0, M68K_A2), IOREC_BUFFER    /* movea.l IOREC_BUFFER(%a0),%a2 */
    move.b  %d0,(0,%a2,%d1.w)
    move.w  %d1,(IOREC_TAIL,%a0)
.Lmidi_out:
    rts
    /* ...and the key path's MOUSE ARM: a button key sets or clears its kbshift bit, an arrow is a
     * movement, and either way the three-byte packet goes to `mousevec` with A0 naming it */
.Lmouse_button:
    moveq   #KBSHIFT_RIGHT_BUTTON_BIT,%d3
    btst    #ALT_MOUSE_BUTTON_SELECT_BIT,%d1
    beq.s   .Lmouse_button_edge
    moveq   #KBSHIFT_LEFT_BUTTON_BIT,%d3
.Lmouse_button_edge:
    btst    #SCANCODE_BREAK_BIT,%d1
    beq.s   .Lmouse_button_down
    bclr    %d3,(KBSHIFT,%a5)
    bra.s   .Lmouse_still
.Lmouse_button_down:
    bset    %d3,(KBSHIFT,%a5)
.Lmouse_still:
    moveq   #0,%d1
    moveq   #0,%d2
.Lmouse_packet:
    lea     (KBD_MOUSE_PACKET,%a5),%a0
    movea.l (KBDVECS + KBDVECS_MOUSEVEC,%a5),%a2
    clr.l   %d0
    move.b  (KBSHIFT,%a5),%d0
    lsr.b   #KBSHIFT_BUTTON_SHIFT,%d0
    addi.b  #KBD_MOUSE_HEADER_BIAS,%d0
    .word   M68K_MOVE_B_TO_D16(M68K_D0, M68K_A0), 0             /* move.b %d0,0(%a0) */
    move.b  %d1,(1,%a0)
    move.b  %d2,(2,%a0)
    jsr     (%a2)
    movea.l (%sp)+,%a0
    rts
