/* BIOS Bconstat / Bconin / Bcostat (functions 1, 2 and 8) — $fc0984, $fc098c, $fc0994.
 *
 * One file, because they are one routine. Each entry loads a different table address and falls into
 * the same three instructions, and what a device number reaches is a longword in RAM rather than an
 * address in the ROM:
 *
 *      Bconstat:   lea     XCONSTAT_TABLE,a0
 *      Bconin:     lea     XCONIN_TABLE,a0
 *      Bcostat:    lea     XCOSTAT_TABLE,a0
 *                  move.w  4(sp),d0            ; the device number
 *                  lsl.w   #2,d0               ; ...times four, IN THE WORD
 *                  movea.l 0(a0,d0.w),a0       ; ...and SIGN-EXTENDED into the index
 *                  jmp     (a0)                ; a JUMP, not a call: the driver returns to the caller
 *
 * WHAT IS RECONSTRUCTED HERE IS THE COMPOSITION, not just the walk: the differential enters the ROM
 * at the BIOS entry and runs through into the driver, so the C has to be both.
 *
 * WHAT IS IN REACH, and what the reach is. Every driver whose whole body is an IOREC in RAM: the
 * console's and MIDI's input, the RS232's input status, the console's output status (a constant) and
 * the RS232's OUTPUT status, which reads no register at all. And, since a case can DECLARE a
 * hardware byte, every driver whose body is a SINGLE read of one and a test of one bit: all four of
 * Bcostat's — the Centronics BUSY line, the two 6850s' TDRE, and the RS232 ring above.
 *
 * WHAT IS NOT, and it is one shape rather than "hardware": a driver that POLLS — whose successive
 * reads of one address must DIFFER before it can return. `Bconin(PRT:)` ($fc2104) drives the
 * parallel port through the YM2149 and then spins on GPIP bit 0 until it clears; `Bconin(AUX:)`
 * ($fc2150) waits on the RS232 input ring an interrupt fills. Neither is a value a declaration can
 * supply — the first needs the direct-PSG path this project has never used, the second needs an
 * interrupt — so this file HALTS on them rather than guessing: an arm that returned a value would be
 * indistinguishable from a reconstructed one (`recreate.h`).
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
#include "addrs.h"
#include "m68k_idioms.h"

/* What a status driver answers: `moveq #-1` for "there is input" and `moveq #0` for "there is not",
 * both of which set the whole of D0. */
#define BCON_READY      0xffffffffu
#define BCON_NOT_READY  0u

/* A ring buffer is a table of BYTES: the head indexes it directly, whatever a record is worth. */
#define IOREC_BUFFER_ENTRY_BYTES 1

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

/* The D0 a device with NO driver answers: the table entry is the shared `rts` at $fc0670, so what
 * comes back is whatever the dispatch left in D0 — `move.w` and `lsl.w` having replaced its low word
 * with the table offset and left the caller's high half alone. Garbage, faithfully. */
static uint32_t no_driver(uint32_t entry_d0, uint16_t device)
{
    return set_low_word(entry_d0, (uint16_t)(device * XCON_TABLE_ENTRY_BYTES));
}

static uint32_t ring_status(const uint8_t *image, uint32_t ring)
{
    return be16(image + ring + IOREC_HEAD) == be16(image + ring + IOREC_TAIL)
        ? BCON_NOT_READY : BCON_READY;
}

/* ONE RING FIELD, RE-READ NOW. Deliberately not `be16`: the spin below must load the head and the
 * tail on every pass, as the ROM's `bsr` to the status driver does, and nothing inside the loop
 * writes them — so a plain read would be hoisted out and the spin would turn into an endless loop
 * over two registers that can no longer change. The volatile qualifier is what forbids that, and
 * assembling the big-endian word by byte is what keeps the read portable to the differential's
 * little-endian host. */
static uint16_t ring_field_now(const uint8_t *image, uint32_t at)
{
    const volatile uint8_t *field = image + at;

    return (uint16_t)((field[0] << 8) | field[1]);
}

/* THE ROM'S OWN POLL, and the one place where "not reconstructed" would be the wrong answer: the
 * loop IS the routine. Nothing in a differential run can end it — no interrupt fires to fill the
 * ring — so a case stages the pending record first (`test/iorec.py`) and this falls straight
 * through. Entered on an empty ring it does not return, which is what the ORIGINAL does too: that
 * case would run the oracle to its instruction cap. */
static void wait_for_a_record(const uint8_t *image, uint32_t ring)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    /* HOST-ONLY, and a diagnostic rather than a behaviour — both builds go on to spin. It says WHICH
     * case staged an empty ring instead of leaving a pytest worker hanging on the loop below
     * (kit.mk: "asserted where there is a process to abort"). */
    assert(be16(image + ring + IOREC_HEAD) != be16(image + ring + IOREC_TAIL));
#endif
    while (ring_field_now(image, ring + IOREC_HEAD) == ring_field_now(image, ring + IOREC_TAIL))
        ;
}

/* One ring index, one record on, wrapped the ROM's way: `cmp.w 4(a0),d1 / bcs` is an UNSIGNED
 * compare and the arm it skips is `moveq #0,d1`, so an index that reaches the ring's size restarts
 * at 0 rather than at index + record - size.
 *
 * ONE HELPER FOR BOTH DIRECTIONS, because the ROM has one: `$fc28ea` is the whole of it, and the
 * readers call it on the HEAD while the output-status driver calls it on the TAIL. */
static uint16_t ring_index_after(const uint8_t *image, uint32_t ring, uint16_t index,
                                 uint16_t record_bytes)
{
    uint16_t next = (uint16_t)(index + record_bytes);

    return next >= be16(image + ring + IOREC_SIZE) ? 0 : next;
}

static uint16_t head_after_one_record(const uint8_t *image, uint32_t ring, uint16_t record_bytes)
{
    return ring_index_after(image, ring, be16(image + ring + IOREC_HEAD), record_bytes);
}

/* ...and where that record sits: `movea.l (a0),a1 / 0(a1,d1.w)`, so the head is a WORD index off a
 * buffer pointer the ring itself carries. */
static uint32_t record_at(const uint8_t *image, uint32_t ring, uint16_t head)
{
    return addr_add(be32(image + ring + IOREC_BUFFER),
                    word_index(head, IOREC_BUFFER_ENTRY_BYTES));
}

/* The console's input driver: the IKBD ring, four bytes a record — a scancode word and an ASCII
 * word — and the whole longword is the return value. */
static uint32_t ikbd_read(uint8_t *image)
{
    uint16_t head;
    uint32_t record;

    wait_for_a_record(image, IOREC_IKBD);
    head = head_after_one_record(image, IOREC_IKBD, IOREC_KEY_BYTES);
    record = be32(image + record_at(image, IOREC_IKBD, head));
    wr16(image + IOREC_IKBD + IOREC_HEAD, head);     /* ...only once the record is out */
    return record;
}

/* ...and MIDI's: one byte a record, laid into the low byte of the -1 the status driver left. */
static uint32_t midi_read(uint8_t *image)
{
    uint16_t head;
    uint8_t record;

    wait_for_a_record(image, IOREC_MIDI);
    head = head_after_one_record(image, IOREC_MIDI, IOREC_MIDI_BYTES);
    record = image[record_at(image, IOREC_MIDI, head)];
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
 * which is the sense of the line rather than of the branch. */
static uint32_t printer_output_status(void)
{
    return (hw_read8(MFP_GPIP) & (1u << MFP_GPIP_PRINTER_BUSY_BIT)) ? BCON_NOT_READY : BCON_READY;
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
    uint16_t next_tail = ring_index_after(image, IOREC_RS232_OUT,
                                          be16(image + IOREC_RS232_OUT + IOREC_TAIL),
                                          IOREC_RS232_BYTES);

    return next_tail == be16(image + IOREC_RS232_OUT + IOREC_HEAD) ? BCON_NOT_READY : BCON_READY;
}

/* `entry_d0` is the D0 the trap dispatcher leaves — the routine's own address, which it computed to
 * jump through. It reaches the result only for a device with no driver (see `no_driver`). */
uint32_t bios_bconstat(uint8_t *image, uint32_t entry_d0, uint16_t device)
{
    uint32_t driver = device_vector(image, XCONSTAT_TABLE, device);

    switch (driver) {
    case XCONSTAT_RS232: return ring_status(image, IOREC_RS232);
    case XCONSTAT_CON:   return ring_status(image, IOREC_IKBD);
    case XCONSTAT_MIDI:  return ring_status(image, IOREC_MIDI);
    case ROM_BARE_RTS:   return no_driver(entry_d0, device);
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
    case ROM_BARE_RTS: return no_driver(entry_d0, device);
    default: break;
    }
    /* The two that remain are POLLS: the parallel port's ($fc2104) spins on GPIP bit 0 until it
     * clears, after driving the port through the YM2149; the RS232's ($fc2150) waits on a ring an
     * interrupt fills. See this file's header for why neither is a declaration away. */
    recreate_not_reconstructed("BIOS Bconin: an input driver that POLLS — the parallel port through "
                               "the YM2149, or the RS232 ring an interrupt fills");
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
    case ROM_BARE_RTS:  return no_driver(entry_d0, device);
    default: break;
    }
    /* Every driver the captured machine's own table names is above, so this arm is reached only by a
     * case that stages a vector of its own — which is the honest state for a table in RAM that
     * anything may replace. */
    recreate_not_reconstructed("BIOS Bcostat: an output status driver this wave does not reconstruct");
}
