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

#endif /* WONDERBOY_BUS_H */
