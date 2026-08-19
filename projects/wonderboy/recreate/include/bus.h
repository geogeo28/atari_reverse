/* bus.h — reading a byte through an address the RECONSTRUCTION computed.
 *
 * THREE ROUTINES NEED THE SAME TWO LINES, which is what moved them here: src/rng.c's stage draw
 * (an entry d2 whose high half the `add.l` folds into the table index), and src/sound.c's envelope,
 * arpeggio and volume-stream cursors, which come out of image bands the .PRG ships holding residue
 * from a run at another load base. Any of them can name an address the loaded image does not have.
 *
 * WHY IT IS A PROJECT HEADER and not tools/recreate_kit/include/machine.h, where `addr_add` and
 * `set_low_word` live: machine.h is the KIT's, shared by every game, and this pairs a 68000 fact
 * (the 24-bit address bus) with an os.h fact (what lies inside the loaded image) — a combination
 * only a game's own reconstruction has an opinion about. Promoting it is registered in ../STATUS.md
 * rather than done here.
 *
 * NOT src/blit.c's `state_word`/`state_word_write` pair: those guard a FIXED address against the
 * image's bounds and never mask, because nothing computes them. They are noted beside this and left
 * alone.
 */
#ifndef WONDERBOY_BUS_H
#define WONDERBOY_BUS_H

#include <stdint.h>

#include "os.h"
#include "wonderboy.h"

/* The byte at `at`, as the 68000 would fetch it: the address goes on the 24-bit bus FIRST — so
 * $0100e3a3 and $0000e3a3 are one location — and only then is it checked against the image. A read
 * past the image is answered with zero, which is what the kit's shim answers the ORACLE with, so the
 * two cores agree about an address neither of them can really reach.
 *
 * MASK BEFORE GUARD, in that order. Guarding first would refuse an address the machine folds back
 * into the image, and the guard is not a substitute for the mask: it is the second half of it. */
static inline uint8_t bus_read_byte(const uint8_t *image, uint32_t at) {
    uint32_t address = at & WB_BUS_ADDR_MASK;
    return os_in_image(address, 1) ? image[address] : (uint8_t)0;
}

/* The same rule at the two wider operand sizes, for src/behavior.c: the per-frame actor walk
 * follows a table pointer out of memory (`movea.l $a098.l,a0`) and every animation stepper in the
 * behaviour tier follows a frame-list pointer its CALLER supplied in a1, so a record word, a
 * record longword and a frame word can all be fetched through an address the reconstruction
 * computed rather than one the image is known to hold.
 *
 * The shim answers a straddle THE SAME WAY — `m68k_read_memory_16`/`_32` bound the WHOLE operand
 * against the image and return 0 when it does not fit, rather than splitting it
 * (tools/recreate_kit/oracle/shim.c) — so these agree with the oracle at the top of the image as
 * well as inside it. */
static inline uint16_t bus_read_word(const uint8_t *image, uint32_t at) {
    uint32_t address = at & WB_BUS_ADDR_MASK;
    return os_in_image(address, 2) ? be16(image + address) : (uint16_t)0;
}

static inline uint32_t bus_read_long(const uint8_t *image, uint32_t at) {
    uint32_t address = at & WB_BUS_ADDR_MASK;
    return os_in_image(address, 4) ? be32(image + address) : 0u;
}

/* ...and the WRITE side of the same rule, which is the half a guarded read alone does not buy.
 *
 * A reconstruction that guards its reads and then stores through a raw `image + addr` is worse off
 * than one that guards neither: the address it refused to trust for a read is trusted for a write,
 * and a write past the image walks off the ctypes buffer into the host heap where the 68000 side
 * merely reaches an address the shim does not map. The shim DROPS such a write, so that is what
 * these do — the same answer src/blit.c's `blit_write_word` gives for the same reason, and the same
 * divergence class closed the same way. */
static inline void bus_write_byte(uint8_t *image, uint32_t at, uint8_t value) {
    uint32_t address = at & WB_BUS_ADDR_MASK;
    if (os_in_image(address, 1))
        image[address] = value;
}

static inline void bus_write_word(uint8_t *image, uint32_t at, uint16_t value) {
    uint32_t address = at & WB_BUS_ADDR_MASK;
    if (os_in_image(address, 2))
        wr16(image + address, value);
}

/* The LONGWORD write, for the one `move.l (a0),(a1)` in the behaviour tier (slot 6 copies a whole
 * coordinate pair into the record it spawns). It is not two `bus_write_word`s: the shim bounds the
 * WHOLE operand, so a longword straddling the image's top is dropped ENTIRELY on both sides where
 * a pair of word writes would land the first half. */
static inline void bus_write_long(uint8_t *image, uint32_t at, uint32_t value) {
    uint32_t address = at & WB_BUS_ADDR_MASK;
    if (os_in_image(address, 4))
        wr32(image + address, value);
}


/* --- A RECORD'S FIELDS, through the same bus ----------------------------------------------------
 *
 * `base + offset` on an address register, guarded exactly as above, and the bit helpers over it.
 * They are here rather than duplicated per module because TWO modules now spell them: src/behavior.c
 * wrote them for the sixty-one dispatch rows and src/player.c needs the same eight for the player's
 * own frame, whose record arrives the same way — out of a table pointer nothing between the walk and
 * the field access bounds.
 *
 * A SECOND COPY IS THE ONE DIVERGENCE NOTHING CATCHES: each module's battery only pins its own
 * routines, so both stay green while one copy drifts (a dropped guard, a changed signedness). They
 * are `static inline` and export no symbol, which is what the two `static` sets bought; sharing them
 * costs nothing and removes the drift.
 *
 * `field_w` returns a SIGNED word because every caller that does arithmetic on a coordinate wants
 * the 68000's own sign; a caller that wants the raw bits casts.
 */
static inline uint8_t field_b(const uint8_t *image, uint32_t record, uint32_t offset) {
    return bus_read_byte(image, addr_add(record, offset));
}

static inline void set_field_b(uint8_t *image, uint32_t record, uint32_t offset, uint8_t value) {
    bus_write_byte(image, addr_add(record, offset), value);
}

static inline int16_t field_w(const uint8_t *image, uint32_t record, uint32_t offset) {
    return (int16_t)bus_read_word(image, addr_add(record, offset));
}

static inline void set_field_w(uint8_t *image, uint32_t record, uint32_t offset, uint16_t value) {
    bus_write_word(image, addr_add(record, offset), value);
}

static inline int flag_is_set(const uint8_t *image, uint32_t record, uint32_t offset, unsigned bit) {
    return (field_b(image, record, offset) & (1u << bit)) != 0;
}

/* `bset`/`bclr`/`bchg #n,d16(An)` are BYTE read-modify-writes on memory whatever the register form
 * is, which is what these three reproduce. */
static inline void flag_set(uint8_t *image, uint32_t record, uint32_t offset, unsigned bit) {
    set_field_b(image, record, offset,
                (uint8_t)(field_b(image, record, offset) | (1u << bit)));
}

static inline void flag_clear(uint8_t *image, uint32_t record, uint32_t offset, unsigned bit) {
    set_field_b(image, record, offset,
                (uint8_t)(field_b(image, record, offset) & ~(1u << bit)));
}

static inline void flag_flip(uint8_t *image, uint32_t record, uint32_t offset, unsigned bit) {
    set_field_b(image, record, offset,
                (uint8_t)(field_b(image, record, offset) ^ (1u << bit)));
}


#endif /* WONDERBOY_BUS_H */
