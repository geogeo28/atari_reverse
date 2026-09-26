/* The two ACIA SERVICE ROUTINES — $fc29fc (MIDI) and $fc2a0c (IKBD) — and everything one byte out
 * of a 6850 reaches. `src/bios/ikbd.c`'s handler calls both on every entry, through KBDVECS.
 *
 *      midi_acia_service:                    ikbd_acia_service:
 *          lea     $d84(a5),a0                   lea     $c76(a5),a0     ; the IOREC
 *          lea     $fffffc04,a1                  lea     $fffffc00,a1    ; the 6850
 *          movea.l $e1a(a5),a2                   movea.l $e16(a5),a2     ; vmiderr / vkbderr
 *          bra.s   .body                     .body:
 *          move.b  (a1),d2                   ; the status register
 *          btst    #7,d2                     ; ...this chip raised the line?
 *          beq.s   .done
 *          btst    #0,d2                     ; a byte is waiting?
 *          beq.s   .overrun
 *          movem.l d2/a0-a2,-(sp)
 *          bsr.s   acia_take_byte
 *          movem.l (sp)+,d2/a0-a2
 *      .overrun:
 *          andi.b  #$20,d2                   ; ...and one was LOST?
 *          beq.s   .done
 *          move.b  2(a1),d0                  ; the byte that overran, to the error vector
 *          jmp     (a2)
 *      .done:
 *          rts
 *
 * ONE SHARED BODY, TWO ENTRIES, and the difference is three registers. The entries fall through into
 * each other's code, which is why they are one C function with three arguments here.
 *
 * THE ERROR VECTOR IS READ BEFORE THE STATUS BYTE, and the order is a claim rather than a detail:
 * the routine the OVERRUN arm jumps to is the one KBDVECS held on ENTRY, so a packet handler that
 * replaced its own error vector mid-service would not be answered until the next interrupt. In the
 * captured machine both slots hold `$fc2a40` — the body's own `rts` — so an overrun is a no-op.
 *
 * THE STATUS AND DATA READS GO THROUGH TWO DOORS OFF TARGET AND ONE ON. `$fffc00`/`$fffc02` are the
 * seeded model's NAMED slots (`os.h`, `OS_HW_ACIA_STATUS`/`_DATA`) and the MIDI pair two bytes up is
 * an ordinary declared I/O byte (Phase 15), so the two chips' reads land in different ledgers and
 * the case declares them through one `io_seed`. `acia_read` below is that routing, and it exists
 * only in the host build: on the machine both are the same volatile byte on the same bus.
 *
 * EVERY READ OF A DATA PORT POPS THE RECEIVE REGISTER, so a case describes a run with a declared
 * SEQUENCE — `io_seed={ACIA_DATA: [b0, b1, ...]}`, one byte per read (`TRAP_MODEL.md`, Phase 16).
 * That is what makes a whole packet a single case: the handler loops, each pass takes one byte, and
 * the list says what the 6301 sent and how many reads the case is describing.
 */
#include <stdint.h>

#include "machine.h"
#include "hw.h"
#include "addrs.h"
#include "bios/iorec.h"
#include "bios/keyboard.h"
#include "bios/acia_packets.h"
#include "staged_call.h"

/* One byte off a 6850, through whichever model owns that address off target. */
static uint8_t acia_read(uint32_t address)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    /* The IKBD's two registers are Phase 7's named slots and the MIDI's are Phase 15's, so they are
     * ledgered in different streams and a case that declared the wrong one is refused by address.
     * The split is at the MIDI status register, which is the first address above the named pair. */
    return address < MIDI_ACIA_STATUS ? hw_read8(address) : io_read8(address);
#else
    return io_read8(address);       /* on target both spellings are the same volatile access */
#endif
}

/* ---- the packet state machine ------------------------------------------------------------------
 * The 6301 prefixes every report with a header byte $f6..$ff, and the ROM turns that into two bytes
 * of state: WHICH report is in progress (1..7, from the kind table) and how many bytes it still
 * wants. A header arrives only when the kind byte is zero, so the two questions never overlap.
 */

/* `move.l #$0e4e,d1 / add.b <kind>,d1 / subq.b #6,d1 / movea.l d1,a2` — where kinds 6 and 7, the
 * two single-stick joystick reports, put their one data byte. The ROM does this arithmetic on the
 * LOW BYTE of a longword that already holds the address, so a kind the tables cannot produce wraps
 * inside the same 256-byte page instead of walking out of it. */
#define PAGE_OFFSET_MASK 0xffu

static uint32_t joystick_data_slot(uint8_t kind)
{
    uint8_t offset = (uint8_t)((uint8_t)IKBD_JOYSTICK_DATA + kind - IKBD_FIRST_UNTABLED_KIND);

    return (IKBD_JOYSTICK_DATA & ~(uint32_t)PAGE_OFFSET_MASK) | offset;
}

/* `move.l a0,-(sp) / jsr (a2) / addq.w #4,sp / clr.b $e36` — a completed packet to its handler, and
 * the state byte cleared AFTERWARDS, so a handler that looked would see the packet still in
 * progress. Both the tabled kinds and the two joystick ones end here. */
static void dispatch_packet(uint8_t *image, uint32_t packet, uint32_t routine)
{
    call_vector_packet_pushed(image, routine, packet);
    image[IKBD_PACKET_KIND] = 0;
}

/* A header byte: which report it starts, how long it is, and — for the two families whose handler is
 * given the header itself — the header stored at the head of its buffer.
 *
 * BOTH RANGE TESTS ARE SIGNED BYTE COMPARES, which is how `>= $fd` covers $fd, $fe and $ff in one
 * test: as `int8_t` the headers run -10..-1 and $fd is -3. $f6 (status), $f7 (absolute mouse) and
 * $fc (time of day) store no header, and their handlers are given the data alone. */
static void begin_packet(uint8_t *image, uint8_t header)
{
    uint32_t index = (uint8_t)(header - IKBD_FIRST_HEADER);

    image[IKBD_PACKET_KIND] = image[addr_add(IKBD_PACKET_KIND_TABLE, index)];
    image[IKBD_PACKET_REMAINING] = image[addr_add(IKBD_PACKET_COUNT_TABLE, index)];
    if ((int8_t)header >= (int8_t)IKBD_RELATIVE_MOUSE_FIRST
        && (int8_t)header <= (int8_t)IKBD_RELATIVE_MOUSE_LAST)
        image[IKBD_RELATIVE_MOUSE_PACKET] = header;
    else if ((int8_t)header >= (int8_t)IKBD_JOYSTICK_FIRST)
        image[IKBD_JOYSTICK_PACKET] = header;
}

/* ...and every byte after it. The fill runs from the packet's END BACKWARDS by what is still
 * outstanding, so the bytes land in the order they arrived; the handler is called on the byte that
 * takes the count to zero.
 *
 * THE $fd PACKET OVERWRITES ITS OWN HEADER. Kind 5 is two bytes ending at `$e4f`, so its first byte
 * lands on the `$e4d` the header went to — which is the ROM's arrangement, not an accident: joyvec
 * is handed `$e4d`, and for a both-sticks report that byte is stick 0 while for a $fe/$ff report it
 * is the header with the stick beside it. */
static void continue_packet(uint8_t *image, uint8_t byte)
{
    uint8_t kind = image[IKBD_PACKET_KIND];
    uint32_t entry, packet, end, routine;
    uint8_t remaining;

    if (kind >= IKBD_FIRST_UNTABLED_KIND) {
        /* The untabled arm reads its vector AFTER the store, where the tabled one reads it before —
         * the ROM's own order, kept because the two arms' stores can reach different memory. */
        image[joystick_data_slot(kind)] = byte;
        dispatch_packet(image, IKBD_JOYSTICK_PACKET,
                        be32(image + KBDVECS + KBDVECS_JOYVEC));
        return;
    }
    /* All three longwords are read BEFORE the byte is stored, and that is a claim: the fill address
     * is `end - remaining`, so a packet with more outstanding than its own length reaches back into
     * the KBDVECS table this line has already read. The third longword is the ADDRESS OF A SLOT
     * rather than a routine (`movea.l 8(a2,d2.w),a2 / movea.l (a2),a2`), so the handler is the one
     * RAM holds when the packet's last byte arrives. */
    entry = addr_add(IKBD_PACKET_TABLE, (uint32_t)(kind - 1) * IKBD_PACKET_TABLE_STRIDE);
    packet = be32(image + entry + IKBD_PACKET_TABLE_START);
    end = be32(image + entry + IKBD_PACKET_TABLE_END);
    routine = be32(image + be32(image + entry + IKBD_PACKET_TABLE_VECTOR));
    remaining = image[IKBD_PACKET_REMAINING];
    image[addr_add(end, -(uint32_t)remaining)] = byte;
    image[IKBD_PACKET_REMAINING] = (uint8_t)(remaining - 1);
    if (image[IKBD_PACKET_REMAINING] != 0)
        return;
    dispatch_packet(image, packet, routine);
}

/* ---- the routines ------------------------------------------------------------------------------ */

void midi_queue_byte(uint8_t *image, uint32_t iorec, uint8_t byte)
{
    /* The step and the wrap are `include/bios/iorec.h`'s — the ROM's own `$fc28ea` — and what is here is
     * this writer's own FULL rule: the byte is DROPPED and nothing moves, not the tail and not the
     * head. A ring whose tail is one record behind its head never holds that last record. */
    uint16_t next = iorec_index_after(image, iorec, be16(image + iorec + IOREC_TAIL),
                                      IOREC_MIDI_BYTES);

    if (next == be16(image + iorec + IOREC_HEAD))
        return;
    image[iorec_record_at(image, iorec, next)] = byte;
    wr16(image + iorec + IOREC_TAIL, next);
}

void acia_take_byte(uint8_t *image, uint32_t iorec, uint32_t acia_base)
{
    uint8_t byte = acia_read(addr_add(acia_base, ACIA_DATA_OFFSET));

    if (iorec != IOREC_IKBD) {
        call_vector_byte(image, be32(image + KBDVECS + KBDVECS_MIDIVEC), iorec, byte);
        return;
    }
    if (image[IKBD_PACKET_KIND] != 0) {
        continue_packet(image, byte);
        return;
    }
    if (byte < IKBD_FIRST_HEADER) {
        kbd_scancode(image, byte, iorec);
        return;
    }
    begin_packet(image, byte);
}

static void acia_service(uint8_t *image, uint32_t iorec, uint32_t acia_base,
                         uint32_t error_vector_slot)
{
    uint32_t error_routine = be32(image + error_vector_slot);
    uint8_t status = acia_read(acia_base);

    if (!(status & ACIA_INTERRUPT))
        return;
    if (status & ACIA_RECEIVE_FULL)
        acia_take_byte(image, iorec, acia_base);
    if (status & ACIA_OVERRUN)
        call_vector_byte(image, error_routine, iorec,
                         acia_read(addr_add(acia_base, ACIA_DATA_OFFSET)));
}

void midi_acia_service(uint8_t *image)
{
    acia_service(image, IOREC_MIDI, MIDI_ACIA_STATUS, KBDVECS + KBDVECS_VMIDERR);
}

void ikbd_acia_service(uint8_t *image)
{
    acia_service(image, IOREC_IKBD, IKBD_ACIA_STATUS, KBDVECS + KBDVECS_VKBDERR);
}
