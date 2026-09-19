/* iorec.h — TOS's IOREC ring, which is one data structure and three routines' worth of arithmetic.
 *
 * Every character device TOS buffers — the IKBD, MIDI, the RS232's two directions — is the same
 * six-field record in low RAM: a buffer pointer, the buffer's size, a head index, a tail index and
 * the two flow-control marks. A RECORD is one byte for MIDI and the RS232 and four for the IKBD, so
 * the record size is an argument everywhere below rather than a constant.
 *
 * THE ARITHMETIC BELONGS IN ONE PLACE because the ROM keeps it in one place: `$fc28ea` is the index
 * step, and the readers call it on the HEAD while the writers call it on the TAIL. Three cores here
 * put a record into one of these rings — `kbd_queue_record` ($fc2dee), `midi_queue_byte` ($fc2e3a)
 * and `rs232_ring_put` ($fc2878) — and what they DIFFER in is the full rule, not the step: the first
 * two DROP the record, and the third SPINS until the transmit interrupt makes room.
 *
 * THE WRAP IS AT THE SIZE AND NOT A MODULO. `cmp.w IOREC_SIZE(a0),d1 / bcs` is an UNSIGNED compare
 * and the arm it skips is `moveq #0,d1`, so an index that REACHES the ring's length restarts at 0
 * rather than at `index + record - size`. A ring whose length is not a multiple of its record simply
 * never uses its last few bytes.
 */
#ifndef TOS102US_IOREC_H
#define TOS102US_IOREC_H

#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "m68k_idioms.h"

/* ONE FIELD OF THE IMAGE, RE-READ NOW. Deliberately not `be16`: the ring spins below must load their
 * condition on every pass, as the ROM's own re-reads do, and nothing inside those loops writes what
 * they watch — so a plain read would be hoisted out and the spin would become an endless loop over
 * registers that can no longer change. The volatile qualifier is what forbids that, and assembling
 * the big-endian word by byte is what keeps the read portable to the differential's little-endian
 * host.
 *
 * The printer's own wait does NOT come through here: what it watches is the 200 Hz clock, which an
 * INTERRUPT advances, so it is polled through the scheduled-write model instead (`sched.h`). */
static inline uint16_t iorec_index_now(const uint8_t *image, uint32_t at)
{
    const volatile uint8_t *field = image + at;

    return (uint16_t)((field[0] << 8) | field[1]);
}

/* `$fc28ea` — one ring index, one record on, wrapped the ROM's way (see the header note). */
static inline uint16_t iorec_index_after(const uint8_t *image, uint32_t ring, uint16_t index,
                                         uint16_t record_bytes)
{
    uint16_t next = (uint16_t)(index + record_bytes);

    return next >= be16(image + ring + IOREC_SIZE) ? 0 : next;
}

static inline uint16_t iorec_head_after_one_record(const uint8_t *image, uint32_t ring,
                                                   uint16_t record_bytes)
{
    return iorec_index_after(image, ring, be16(image + ring + IOREC_HEAD), record_bytes);
}

/* A ring buffer is a table of BYTES: an index reaches it directly, whatever a record is worth. */
#define IOREC_BUFFER_ENTRY_BYTES 1

/* ...and where a record sits: `movea.l (a0),a1 / 0(a1,d1.w)`, so the index is a WORD off a buffer
 * pointer the ring itself carries — and a SIGN-EXTENDED one, which is `word_index`'s whole subject
 * (`m68k_idioms.h`). */
static inline uint32_t iorec_record_at(const uint8_t *image, uint32_t ring, uint16_t index)
{
    return addr_add(be32(image + ring + IOREC_BUFFER),
                    word_index(index, IOREC_BUFFER_ENTRY_BYTES));
}

/* THE ROM'S OWN POLL, and the one place where "not reconstructed" would be the wrong answer: the
 * loop IS the routine. Nothing in a differential run can end it — no interrupt fires to fill the
 * ring — so a case stages the pending record first (`test/iorec.py`) and this falls straight
 * through. Entered on an empty ring it does not return, which is what the ORIGINAL does too: that
 * case would run the oracle to its instruction cap. */
static inline void iorec_wait_for_a_record(const uint8_t *image, uint32_t ring)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    /* HOST-ONLY, and a diagnostic rather than a behaviour — both builds go on to spin. It says WHICH
     * case staged an empty ring instead of leaving a pytest worker hanging on the loop below
     * (kit.mk: "asserted where there is a process to abort"). */
    assert(be16(image + ring + IOREC_HEAD) != be16(image + ring + IOREC_TAIL));
#endif
    while (iorec_index_now(image, ring + IOREC_HEAD) == iorec_index_now(image, ring + IOREC_TAIL))
        ;
}

/* ...and the mirror, for the one writer that BLOCKS: spin while the stepped tail is on the head,
 * which is the index the transmit interrupt moves. */
static inline void iorec_wait_for_room(const uint8_t *image, uint32_t ring, uint16_t tail)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    assert(tail != be16(image + ring + IOREC_HEAD));       /* `iorec_wait_for_a_record`'s reason */
#endif
    while (tail == iorec_index_now(image, ring + IOREC_HEAD))
        ;
}

#endif /* TOS102US_IOREC_H */
