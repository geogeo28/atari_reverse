/* BIOS Bconstat / Bconin / Bconout / Bcostat (functions 1, 2, 3 and 8) — $fc0984, $fc098c, $fc099c,
 * $fc0994.
 *
 * One file, because they are one routine. Each entry loads a different table address and falls into
 * the same three instructions, and what a device number reaches is a longword in RAM rather than an
 * address in the ROM:
 *
 *      Bconstat:   lea     XCONSTAT_TABLE,a0
 *      Bconin:     lea     XCONIN_TABLE,a0
 *      Bconout:    lea     XCONOUT_TABLE,a0
 *      Bcostat:    lea     XCOSTAT_TABLE,a0
 *                  move.w  4(sp),d0            ; the device number
 *                  lsl.w   #2,d0               ; ...times four, IN THE WORD
 *                  movea.l 0(a0,d0.w),a0       ; ...and SIGN-EXTENDED into the index
 *                  jmp     (a0)                ; a JUMP, not a call: the driver returns to the caller
 *
 * WHAT IS RECONSTRUCTED HERE IS THE COMPOSITION, not just the walk: the differential enters the ROM
 * at the BIOS entry and runs through into the driver, so the C has to be both.
 *
 * WHAT IS IN REACH. Every driver whose whole body is an IOREC in RAM: the console's and MIDI's
 * input, the RS232's input status, the console's output status (a constant) and the RS232's OUTPUT
 * status, which reads no register at all. Every driver whose body is a SINGLE read of a hardware
 * byte and a test of one bit, since a case can DECLARE that byte — all four of Bcostat's. And, since
 * a case can declare a LIST of them (TRAP_MODEL.md, Phase 16), every driver that POLLS one: the two
 * 6850 senders `Bconout` reaches, the Centronics BUSY wait, and the MFP USART's transmitter status.
 * A poll is spelt with the kit's `hw_poll8`/`io_poll8` rather than a plain read, so a case whose
 * declaration runs out ends the loop with a refusal instead of hanging the suite.
 *
 * WHAT IS NOT is `Bconin`'s two remaining drivers — and BOTH are DEFERRALS rather than limits, which
 * is a correction this file has now had to make twice.
 *
 *   * `Bconin(AUX:)` ($fc2150) was recorded as needing an interrupt. It does not. Its body is
 *     `lea $c54,a0 / bsr $fc2892` — the same blocking ring reader `rs232_ring_get` below already is,
 *     entered on the RS232's INPUT ring instead of its output one — and a case STAGES the pending
 *     record exactly as `test_bios_bconin.py` does for the console and MIDI, so the spin falls
 *     straight through. What follows the read is a FLOW-CONTROL TAIL and nothing more: `tst.b 32(a0)`
 *     for the mode, a low-water compare of the ring's own fill against `10(a0)`, and then either
 *     `bsr $fc28ae` (a direct `$ff8800` read-modify-write dropping RTS, which `psg_seed` serves) or
 *     an XON planted at `33(a0)` followed by `bsr $fc21c2` — the MFP TSR test and transmitter prime
 *     THIS WAVE RECONSTRUCTED for `Bconout(AUX:)`, which a declared `$fffa2d` serves. What is
 *     missing is the cases and one parameter: `rs232_ring_get` names `IOREC_RS232_OUT` where the ROM
 *     takes its ring in A0.
 *   * `Bconin(PRT:)` ($fc2104) is a DEFERRAL for its own reasons, and saying so was the first
 *     correction.
 *     It was recorded as needing "the direct-PSG path this project has never used"; it does not.
 *     Every chip access it makes is a `bsr $fc2eac` — `Giaccess`'s own body, the same door the
 *     printer's OUTPUT driver below goes through — so `psg_seed` serves it and no mixed-path
 *     question arises. Its wait is `bsr $fc2124 / tst.w d0 / bne`, which spins while the Centronics
 *     BUSY line is CLEAR and ends when the printer ASSERTS it (the opposite way round from the
 *     other correction this note used to carry), and a declared LIST says exactly that. What is
 *     missing is the cases, not the model.
 *
 * So this file HALTS on both rather than guessing: an arm that returned a value would be
 * indistinguishable from a reconstructed one (`recreate.h`). A halt is what a DEFERRAL looks like
 * from the outside; what makes these two deferrals rather than limits is that the model already has
 * everything they ask of it.
 *
 * `Bconstat`'s own halt is unreachable on the captured machine: its table carries THREE drivers —
 * $fc2138 (RS232), $fc2226 (console) and $fc2044 (MIDI), devices 1/2/3, where 0 and 4-7 are the bare
 * `rts` — all three are ring readers and all three are here. It stays because the table is RAM and
 * anything may replace an entry (`test_bios_bconstat.py` reads the table out of the snapshot rather
 * than assuming it, which is what contradicted the "four" this note used to claim).
 *
 * THE DRIVERS, verbatim:
 *
 *   status, $fc2138 (RS232, ring $c54) / $fc2226 (console, ring $c76) / $fc2044 (MIDI, ring $d84)
 *      lea     <ring>,a0
 *      moveq   #-1,d0
 *      lea     6(a0),a2 / lea 8(a0),a3
 *      cmpm.w  (a3)+,(a2)+         ; head == tail?
 *      bne.s   .ready
 *      moveq   #0,d0
 *   .ready: rts
 *
 *   console input, $fc223c (and MIDI's $fc2060, identical but for the record width and the load)
 *   .poll:
 *      bsr.s   <the status driver above>   ; ...which also leaves the ring in A0
 *      tst.w   d0
 *      beq.s   .poll               ; SPINS until the interrupt handler puts something in the ring
 *      move.w  sr,-(sp)
 *      ori.w   #$700,sr
 *      move.w  6(a0),d1            ; head
 *      cmp.w   8(a0),d1
 *      beq.s   .out                ; unreachable: the poll above just said they differ
 *      addq.w  #4,d1               ; ...#1 for MIDI: the record width, in BYTES
 *      cmp.w   4(a0),d1
 *      bcs.s   .keep               ; UNSIGNED: the ring wraps to 0 on reaching its size
 *      moveq   #0,d1
 *   .keep:
 *      movea.l (a0),a1
 *      move.l  0(a1,d1.w),d0       ; ...move.b for MIDI — see below
 *      move.w  d1,6(a0)            ; the head is only advanced once the record is out
 *   .out:
 *      move.w  (sp)+,sr
 *      rts
 *
 *   console output status, $fc226c:  moveq #-1,d0 / rts     (the screen is never busy)
 *
 * THREE THINGS A RECONSTRUCTION GETS WRONG WITHOUT A CASE SAYING SO.
 *
 * The MIDI reader's `move.b` writes the LOW BYTE of D0 only, and D0 came from the status driver's
 * `moveq #-1` — so MIDI input returns $ffffff00 | byte, not the byte (`MIDI_RESULT_PREFIX`).
 *
 * The record is READ BEFORE THE HEAD IS STORED, which is only visible on a ring whose buffer
 * overlaps its own head word — `movea.l (a0),a1 / move.l 0(a1,d1.w),d0` and only then
 * `move.w d1,6(a0)`. A reconstruction that advanced the head first would hand such a caller the head
 * it was about to write instead of the one it arrived with; `test_bios_bconin.py` stages exactly
 * that ring.
 *
 * And the `beq.s .out` arm above leaves the status driver's -1 in D0; it is unreachable in this
 * model (the oracle runs at IPL 7 and takes no interrupt between the poll and the re-read), so it is
 * transcribed as the ROM has it and read-verified, not exercised.
 *
 * THE INTERRUPT MASK IS NOT MODELLED, for the reason giaccess.c gives: the run takes no interrupts,
 * and the saved SR is restored before the `rts`.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "machine.h"
#include "recreate.h"
#include "hw.h"
#include "ipl.h"
#include "sched.h"
#include "addrs.h"
#include "ikbd.h"
#include "iorec.h"
#include "m68k_idioms.h"
#include "vt52.h"
#include "xbios.h"

/* What a status driver answers: `moveq #-1` for "there is input" and `moveq #0` for "there is not",
 * both of which set the whole of D0. */
#define BCON_READY      0xffffffffu
#define BCON_NOT_READY  0u

/* The longword the BIOS entry jumps through, with the 68000's word-only index arithmetic
 * (`word_index`): the device number is multiplied inside a WORD and the product is then
 * sign-extended, so device $4000 reaches entry 0 and device $2000 would index $ffff8000 off the
 * table. */
static uint32_t device_vector(const uint8_t *image, uint32_t table, uint16_t device)
{
    uint32_t at = addr_add(table, word_index(device, XCON_TABLE_ENTRY_BYTES));

#ifdef RECREATE_HOST_DIFFERENTIAL
    /* HOST-ONLY, the way the kit prescribes (kit.mk: "asserted where there is a process to abort").
     * A device number that indexes outside RAM is unreachable through the trap (GEMDOS bounds it)
     * and unrunnable here (the index lands in the I/O page, which ROM mode refuses). */
    assert(at + XCON_TABLE_ENTRY_BYTES <= ST_RAM_BYTES);
#endif
    return be32(image + at);
}

/* THE D0 THE DISPATCH ITSELF LEAVES, which is every driver's ENTERING D0 and not only the
 * no-driver answer: `move.w 4(sp),d0 / lsl.w #2,d0` has replaced the caller's low word with the
 * table offset and left its high half alone, and the `jmp` changes nothing.
 *
 * For `Bconstat`, `Bconin` and `Bcostat` it only ever reaches a RESULT through the shared `rts` at
 * $fc0670, because every driver of theirs opens with a `moveq`. `Bconout`'s two 6850 senders write
 * no D0 at all, so for them it IS the result — and the ROM's own garbage is what a caller gets. */
static uint32_t dispatch_scratch(uint32_t entry_d0, uint16_t device)
{
    return set_low_word(entry_d0, (uint16_t)(device * XCON_TABLE_ENTRY_BYTES));
}

static uint32_t ring_status(const uint8_t *image, uint32_t ring)
{
    return be16(image + ring + IOREC_HEAD) == be16(image + ring + IOREC_TAIL)
        ? BCON_NOT_READY : BCON_READY;
}

/* The console's input driver: the IKBD ring, four bytes a record — a scancode word and an ASCII
 * word — and the whole longword is the return value. */
static uint32_t ikbd_read(uint8_t *image)
{
    uint16_t head;
    uint32_t record;

    iorec_wait_for_a_record(image, IOREC_IKBD);
    head = iorec_head_after_one_record(image, IOREC_IKBD, IOREC_KEY_BYTES);
    record = be32(image + iorec_record_at(image, IOREC_IKBD, head));
    wr16(image + IOREC_IKBD + IOREC_HEAD, head);     /* ...only once the record is out */
    return record;
}

/* ...and MIDI's: one byte a record, laid into the low byte of the -1 the status driver left. */
static uint32_t midi_read(uint8_t *image)
{
    uint16_t head;
    uint8_t record;

    iorec_wait_for_a_record(image, IOREC_MIDI);
    head = iorec_head_after_one_record(image, IOREC_MIDI, IOREC_MIDI_BYTES);
    record = image[iorec_record_at(image, IOREC_MIDI, head)];
    wr16(image + IOREC_MIDI + IOREC_HEAD, head);
    return MIDI_RESULT_PREFIX | record;
}

/* ---- Bcostat's four hardware drivers: "can this device take another character?" ----------------
 *
 * Each is a SINGLE read of one byte and a test of one bit — no loop, nothing that has to change
 * between two reads — so each is describable by a declaration the case writes
 * (`io_seed={<address>: <byte>}`, TRAP_MODEL.md, Phases 7 and 15). Which of the three the kit
 * happens to serve each address from is its own bookkeeping: `$fffa01` and `$fffc00` are NAMED
 * SLOTS and go through `hw_read8`, `$fffc04` is an ordinary declared byte and goes through
 * `io_read8`, and a case declares all three through the one `io_seed` door.
 */

/* MFP GPIP bit 0 is the Centronics BUSY line, and the ROM's test reads the opposite way round to the
 * answer: `btst #0,(a0) / beq` KEEPS the `moveq #-1` when the bit is CLEAR. So busy means not ready,
 * which is the sense of the line rather than of the branch.
 *
 * ONE ITERATION OF A POLL, because `Bconout(PRT:)` below calls this same driver in a LOOP: a read
 * the model refuses hands this shore 0, which reads as "not busy" here and as "still busy" to the
 * printer's wait — so the loop's own condition has to be the model's answer (`hw.h`). `Bcostat`'s
 * driver is the same read made once, which is what the wrapper below it is. */
static int poll_printer_output_status(uint32_t *ready)
{
    uint8_t gpip;
    int served = hw_poll8(MFP_GPIP, &gpip);

    /* A REFUSED read reports BUSY, and that is not a nicety. The byte `hw_poll8` hands back on a
     * refusal is 0, which through the test below reads as NOT BUSY — so the wait would leave its
     * loop and go on to SEND the character, driving the YM2149 over a case the model has already
     * refused. Reporting busy puts the void case on the give-up arm, which is the arm that touches
     * no chip at all. */
    *ready = (!served || (gpip & (1u << MFP_GPIP_PRINTER_BUSY_BIT))) ? BCON_NOT_READY : BCON_READY;
    return served;
}

static uint32_t printer_output_status(void)
{
    uint32_t ready;

    (void)poll_printer_output_status(&ready);
    return ready;
}

/* ...and both 6850s answer the same question the same way, one register block apart: bit 1 of the
 * status register is TDRE, "the transmit register is empty". `btst #1,d2 / bne` keeps the -1 when it
 * is SET, which is the plain reading for once. The byte is the argument rather than the address so
 * that the two drivers differ only in which door reads them, which is the whole of the difference. */
static uint32_t acia_output_status(uint8_t status)
{
    return (status & ACIA_TRANSMIT_READY) ? BCON_READY : BCON_NOT_READY;
}

/* The RS232's is the one that reads NO byte at all, and the halt this file used to carry said
 * otherwise. Its whole body is the OUTPUT ring: advance the tail one record, and if that lands on
 * the head the ring is full and the port cannot take another character. `$fc28ea` — the `bsr` in the
 * middle of it — is the wrap arithmetic above, not an access. */
static uint32_t rs232_output_status(const uint8_t *image)
{
    uint16_t next_tail = iorec_index_after(image, IOREC_RS232_OUT,
                                           be16(image + IOREC_RS232_OUT + IOREC_TAIL),
                                           IOREC_RS232_BYTES);

    return next_tail == be16(image + IOREC_RS232_OUT + IOREC_HEAD) ? BCON_NOT_READY : BCON_READY;
}

/* `entry_d0` is the D0 the trap dispatcher leaves — the routine's own address, which it computed to
 * jump through. It reaches the result only for a device with no driver (`dispatch_scratch`). */
uint32_t bios_bconstat(uint8_t *image, uint32_t entry_d0, uint16_t device)
{
    uint32_t driver = device_vector(image, XCONSTAT_TABLE, device);

    switch (driver) {
    case XCONSTAT_RS232: return ring_status(image, IOREC_RS232);
    case XCONSTAT_CON:   return ring_status(image, IOREC_IKBD);
    case XCONSTAT_MIDI:  return ring_status(image, IOREC_MIDI);
    case ROM_BARE_RTS:   return dispatch_scratch(entry_d0, device);
    default: break;
    }
    recreate_not_reconstructed("BIOS Bconstat: an input status driver this wave does not reconstruct");
}

uint32_t bios_bconin(uint8_t *image, uint32_t entry_d0, uint16_t device)
{
    uint32_t driver = device_vector(image, XCONIN_TABLE, device);

    switch (driver) {
    case XCONIN_CON:   return ikbd_read(image);
    case XCONIN_MIDI:  return midi_read(image);
    case ROM_BARE_RTS: return dispatch_scratch(entry_d0, device);
    default: break;
    }
    /* The two that remain both WAIT, and a DECLARATION could already describe either: the parallel
     * port's ($fc2104) spins on GPIP bit 0 until the printer ASSERTS busy, having driven the port
     * through `Giaccess`; the RS232's ($fc2150) reads a STAGED ring and then runs a flow-control
     * tail of a PSG write and this file's own transmitter prime. Both are deferrals rather than
     * limits — this file's header says what each would take. */
    recreate_not_reconstructed("BIOS Bconin: the parallel port ($fc2104) or the RS232 ($fc2150) — "
                               "both DEFERRED rather than out of reach; see src/bios/bcon.c");
}

uint32_t bios_bcostat(uint8_t *image, uint32_t entry_d0, uint16_t device)
{
    uint32_t driver = device_vector(image, XCOSTAT_TABLE, device);

    switch (driver) {
    case XCOSTAT_CON:   return BCON_READY;
    case XCOSTAT_PRT:   return printer_output_status();
    case XCOSTAT_RS232: return rs232_output_status(image);
    case XCOSTAT_IKBD:  return acia_output_status(hw_read8(IKBD_ACIA_STATUS));
    case XCOSTAT_MIDI:  return acia_output_status(io_read8(MIDI_ACIA_STATUS));
    case ROM_BARE_RTS:  return dispatch_scratch(entry_d0, device);
    default: break;
    }
    /* Every driver the captured machine's own table names is above, so this arm is reached only by a
     * case that stages a vector of its own — which is the honest state for a table in RAM that
     * anything may replace. */
    recreate_not_reconstructed("BIOS Bcostat: an output status driver this wave does not reconstruct");
}

/* ================================================================================================
 * Bconout (BIOS $03) — $fc099c, and the four of its six drivers that are not the console.
 *
 * The same four-instruction walk over the fourth table, and one more argument: the CHARACTER WORD at
 * 6(sp), above the device word. CON: and RAW: are `src/bios/vt52.c`; what is here is the two 6850
 * senders, the parallel port and the RS232.
 *
 * WHAT EACH DRIVER LEAVES IN D0 IS A CLAIM OF ITS OWN, and only two of the six make one. The two
 * ACIA senders never write D0 at all, so `Bconout(MIDI:)` hands back the register the trap
 * dispatcher left; the printer's is `moveq #-1` or `moveq #0`; and the RS232's is whatever fell out
 * of the flow-control half it ran — a ring index, a pending character, or the byte it sent. Each is
 * transcribed rather than tidied, because a caller cannot tell a tidied one from a reconstructed
 * one.
 * ============================================================================================= */

/* `move.b <memory>,d0` on a longword register: the low BYTE is replaced and the other three are
 * left alone, which is how the RS232's flow-control half comes to answer a caller's own D0 with one
 * byte changed. */
static uint32_t set_low_byte_of_long(uint32_t reg, uint8_t byte)
{
    return set_low_word(reg, set_low_byte((uint16_t)reg, byte));
}

/* ---- the RS232's output ring, and the USART it feeds -------------------------------------------- */

/* $fc2878 — one byte INTO the ring, blocking while it is FULL. The mirror of `Bconin`'s reader: the
 * tail is advanced FIRST and the byte stored at the advanced slot, and the spin re-reads only the
 * HEAD, which is the index the transmit interrupt moves. */
static void rs232_ring_put(uint8_t *image, uint8_t byte)
{
    uint16_t tail = iorec_index_after(image, IOREC_RS232_OUT,
                                      be16(image + IOREC_RS232_OUT + IOREC_TAIL),
                                      IOREC_RS232_BYTES);

    iorec_wait_for_room(image, IOREC_RS232_OUT, tail);
    image[iorec_record_at(image, IOREC_RS232_OUT, tail)] = byte;
    wr16(image + IOREC_RS232_OUT + IOREC_TAIL, tail);
}

/* $fc2892 — one byte OUT of it, blocking while it is EMPTY, and the WHOLE of D0: `moveq #0,d0`
 * before the `move.b`, where `Bconin(MIDI:)`'s reader laid its byte into a `moveq #-1`. */
static uint32_t rs232_ring_get(uint8_t *image)
{
    uint16_t head;
    uint8_t byte;

    iorec_wait_for_a_record(image, IOREC_RS232_OUT);
    head = iorec_head_after_one_record(image, IOREC_RS232_OUT, IOREC_RS232_BYTES);
    byte = image[iorec_record_at(image, IOREC_RS232_OUT, head)];
    wr16(image + IOREC_RS232_OUT + IOREC_HEAD, head);       /* ...only once the byte is out */
    return byte;
}

/* $fc2836 — put the NEXT byte into the USART's data register, if there is one and the far end has
 * not asked us to stop. Three ways in and one way out:
 *
 *      move.b  RSCONF_FLOW_CONTROL,d0      ; the mode...
 *      and.b   RS232_REMOTE_STOPPED,d0     ; ...and whether we are being held off
 *      bne.s   .out                        ; ...which together mean "send nothing"
 *      move.b  RS232_PENDING_CHARACTER,d0  ; an XON/XOFF jumps the queue
 *      beq.s   .ring
 *        clr.b RS232_PENDING_CHARACTER
 *        bra.s .send
 *   .ring: <the output ring, or nothing if it is empty>
 *   .send: <spin on TSR's BUFFER EMPTY, save the TSR byte, store the character in the UDR>
 *
 * The TSR is read TWICE on the way out — once as the poll's last look and once to be saved in
 * `RS232_TRANSMIT_STATUS` — so a case that declares it as one byte serves both and a LIST of two
 * says what the poll saw and what was saved. */
static uint32_t rs232_prime_transmitter(uint8_t *image, uint32_t result)
{
    uint8_t status;

    result = set_low_byte_of_long(result, (uint8_t)(image[RSCONF_FLOW_CONTROL]
                                                    & image[RS232_REMOTE_STOPPED]));
    if ((uint8_t)result != 0)
        return result;
    result = set_low_byte_of_long(result, image[RS232_PENDING_CHARACTER]);
    if ((uint8_t)result != 0) {
        image[RS232_PENDING_CHARACTER] = 0;
    } else {
        uint16_t head = be16(image + IOREC_RS232_OUT + IOREC_HEAD);

        result = set_low_word(result, head);        /* `move.w 6(a0),d0` — a WORD, over the byte */
        if (head == be16(image + IOREC_RS232_OUT + IOREC_TAIL))
            return result;                          /* nothing queued */
        result = rs232_ring_get(image);
    }
    while (io_poll8(MFP_TSR, &status)
           && (status & (1u << MFP_TSR_BUFFER_EMPTY_BIT)) == 0)
        ;                                           /* a refused read voids the case (`hw.h`) */
    image[RS232_TRANSMIT_STATUS] = io_read8(MFP_TSR);
    hw_write8(MFP_UDR, (uint8_t)result);
    return result;
}

/* $fc21b4 — the AUX: driver. The byte goes into the ring whatever happens; the USART is only primed
 * when it is IDLE, because a busy transmitter will fetch the next byte through its own interrupt. */
static uint32_t rs232_output(uint8_t *image, uint32_t entry_d0, uint16_t character)
{
    uint32_t result = set_low_word(entry_d0, character);
    os_ipl_t mask;

    rs232_ring_put(image, (uint8_t)result);
    if ((io_read8(MFP_TSR) & (1u << MFP_TSR_BUFFER_EMPTY_BIT)) == 0)
        return result;                  /* `tst.b TSR / bpl` — a transmitter mid-character */
    /* `move.w sr,-(sp) / ori.w #$700,sr` around the prime ALONE, for `src/xbios/gibit.c`'s reason:
     * the prime is a read-modify-write of the ring and the USART together, and TOS's own 200 Hz
     * driver runs between any two of its instructions. Invisible to Tier 1 — `ipl.h` is a no-op off
     * target — so what holds it is the Tier 3 cycle count, as it holds every other bracket here. */
    mask = os_ipl_raise();
    result = rs232_prime_transmitter(image, result);
    os_ipl_restore(mask);
    return result;
}

/* ---- the parallel port ($fc2090), which is the YM2149's port B ---------------------------------- */

/* $fc20f8 and $fc20fe — `moveq #32,d2 / bra Ongibit_body` and `moveq #-33,d2 / bra Offgibit_body`:
 * the Centronics strobe, driven through the two read-modify-writes' own bodies ($fc2ee2 / $fc2f08),
 * entered below their argument fetch with the mask already in D2.
 *
 * WHAT D0 IS HERE IS NOTHING AT ALL, and that is why a constant stands in for it. Both bodies give
 * D0 back unchanged (`movem.l (sp)+,d0-d2`) and the driver replaces it with `moveq #-1` afterwards,
 * so whatever the ROM happened to be carrying is neither read nor returned. Passing the character
 * would say it was one of the two, and it is not. */
#define PRINTER_STROBE_UNREAD_D0 0      /* the argument the strobe's two bodies hand straight back */

static void printer_strobe(void)
{
    unsigned pulse;

    for (pulse = 0; pulse < PRINTER_STROBE_ASSERTIONS; pulse++)
        (void)xbios_offgibit(PRINTER_STROBE_UNREAD_D0, PRINTER_STROBE_CLEAR_MASK);
    (void)xbios_ongibit(PRINTER_STROBE_UNREAD_D0, PRINTER_STROBE_SET_MASK);
}

/* $fc20cc — the byte itself: make port B an output, put the byte on it, pulse the strobe. The first
 * two accesses are BRACKETED AGAINST INTERRUPTS together because they are one read-modify-write of
 * the mixer register (`ipl.h`, and `src/xbios/gibit.c`'s note on why the bracket is invisible to
 * Tier 1); the port-B write below is a plain store and is outside it. */
static uint32_t printer_send(uint16_t character)
{
    os_ipl_t mask = os_ipl_raise();
    /* 0 is the data argument a READ never looks at (`src/xbios/gibit.c`'s `UNUSED_DATA`); what the
     * ROM has in D0 here is the -1 the BUSY test left, and it is just as unread. */
    uint8_t mixer = xbios_giaccess(0, PSG_MIXER_REGISTER);

    xbios_giaccess(mixer | PSG_PORT_B_OUTPUT, GIACCESS_WRITE_FLAG | PSG_MIXER_REGISTER);
    os_ipl_restore(mask);
    xbios_giaccess(character, GIACCESS_WRITE_FLAG | PSG_PORT_B);
    printer_strobe();
    return PRINTER_SENT;
}

/* `moveq #0,d0 / move.l _hz_200,PRINTER_RETRY_AT` — the port did not take the byte, and the instant
 * of that is remembered so the next call does not spend thirty seconds finding out again. */
static uint32_t printer_give_up(uint8_t *image)
{
    wr32(image + PRINTER_RETRY_AT, be32(image + SYSVAR_HZ_200));
    return PRINTER_TIMED_OUT;
}

/* $fc2090 — the PRT: driver.
 *
 * THE SERIAL-PORT TEST READS THE WRONG BYTE, and that is a finding rather than a transcription slip:
 * `btst #4,PRINTER_CONFIG` is a BYTE operation on a WORD field, so it tests bit 4 of the config's
 * HIGH byte — bit 12 of the word — where every other reader of the same field takes bit 4 of the
 * word itself (the screen dump at $fc0da2 does `lsr.w #4 / and.w #1`). So a machine configured the
 * documented way for a serial printer still sends through the parallel port here.
 *
 * THE TWO TIME COMPARES ARE NOT THE SAME COMPARE either: the hold-off is `cmpi.l / bcs`, UNSIGNED,
 * and the timeout is `cmpi.l / blt`, SIGNED. */
static uint32_t printer_output(uint8_t *image, uint32_t entry_d0, uint16_t character)
{
    uint32_t started;
    uint32_t ready;

    if (image[PRINTER_CONFIG] & (1u << PRINTER_CONFIG_SERIAL_BIT))
        return rs232_output(image, entry_d0, character);     /* a `bne` INTO the RS232 driver */
    if (be32(image + SYSVAR_HZ_200) - be32(image + PRINTER_RETRY_AT) < PRINTER_RETRY_HOLDOFF_TICKS)
        return printer_give_up(image);
    started = be32(image + SYSVAR_HZ_200);
    while (poll_printer_output_status(&ready) && (uint16_t)ready == 0) {
        uint32_t now;

        /* `move.l _hz_200,d3` — the clock the thirty seconds are measured against, re-read once a
         * pass. Through the SCHEDULED-WRITE model, because nothing inside a differential run
         * advances the 200 Hz tick: it is an interrupt, so without a case saying what that
         * interrupt did this loop never ends on either shore, exactly as `Vsync`'s does not
         * (`sched.h`; TRAP_MODEL.md, Phase 8). */
        if (!sched_poll32(image, SYSVAR_HZ_200, PRINTER_WAIT_SITE, &now))
            break;                          /* the cap — the case is void, and the exit is below */
        if ((int32_t)(now - started) >= PRINTER_TIMEOUT_TICKS)
            break;                          /* ...and the ROM's own thirty seconds */
    }
    /* ONE EXIT, which is the ROM's `$fc20c2`: BUSY never cleared. Both of the loop's own give-ups
     * land here as well — a refused GPIP read and a refused clock poll — each with `ready` reporting
     * BUSY, so a case the model has already voided leaves through the arm that touches no chip
     * (`hw.h`, `sched.h`). */
    if ((uint16_t)ready == 0)
        return printer_give_up(image);
    return printer_send(character);
}

uint32_t bios_bconout(uint8_t *image, uint32_t entry_d0, uint16_t device, uint16_t character)
{
    uint32_t driver = device_vector(image, XCONOUT_TABLE, device);
    /* What the drivers are ENTERED with, which four of the six give back untouched or nearly so. */
    uint32_t entered = dispatch_scratch(entry_d0, device);

    switch (driver) {
    case XCONOUT_PRT:   return printer_output(image, entered, character);
    case XCONOUT_RS232: return rs232_output(image, entered, character);
    case XCONOUT_CON:   return console_output(image, entered, character);
    case XCONOUT_RAW:   return console_output_raw(image, entered, character);
    /* Both 6850 senders are the XBIOS routines' own bodies, one `move.w 6(sp),d1` further up — so
     * `Bconout(IKBD:)` IS `Ikbdws` of a single byte, 951-iteration settling delay and all, and
     * neither writes D0 (`src/xbios/acia.c`). */
    case XCONOUT_MIDI:  midi_send_byte((uint8_t)character); return entered;
    case XCONOUT_IKBD:  ikbd_send_byte((uint8_t)character); return entered;
    case ROM_BARE_RTS:  return entered;
    default: break;
    }
    recreate_not_reconstructed("BIOS Bconout: an output driver this wave does not reconstruct");
}
