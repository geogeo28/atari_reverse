/* common.h — the 68000-shaped helpers more than one of this reconstruction's cores needs.
 *
 * WHY THESE ARE NOT IN THE KIT'S `machine.h`, which is where `sign_ext16`, `addr_add` and
 * `loop_passes` live. That header is the ISA: an instruction's semantics, spelt once for every
 * project the kit serves. What is below is one step above that — an IDIOM the Alcyon compiler and
 * this program's hand-written loops happen to use, named for this program:
 *
 *   * `muls_ext_w` is a `muls.w` FOLLOWED BY an `ext.l`, which is a code-generation habit and not
 *     an instruction. A project whose compiler emitted `mulu.w` + `swap`, or a 32-bit multiply,
 *     would want a different helper under the same obvious name.
 *   * `copy_longs_ascending` is a loop shape, not an opcode.
 *   * `LONG_BYTES` is the size of the unit those loops count in.
 *
 * Growing the KIT for them would make every other project compile against Bubble Ghost's habits and
 * would need a kit test each; keeping them here keeps the seam where the evidence is. They live in
 * a header of their own rather than in one subsystem's because `src/blit.c`, `src/frontend.c` and
 * `src/gameplay.c` all reach for them, and a helper defined in the header of a subsystem that does
 * not own the caller is the "borrowed global" shape ../STATUS.md exists to retire.
 */
#ifndef BUBBLEGHOST_COMMON_H
#define BUBBLEGHOST_COMMON_H

#include "machine.h"

/* One `move.l`: the unit every copy loop in this program counts in, and the stride of every
 * POINTER table it indexes (the parameter blocks' array pointers, the GHOST.DAT bank table, the two
 * sprite tables and the hall of fame's two). */
#define LONG_BYTES 4u

/* `muls.w #k,Dn` FOLLOWED BY `ext.l Dn`, which is how the compiler built every screen offset and
 * every table index in this program: the 32-bit product is thrown away and replaced by its own low
 * word, sign-extended. So an operand big enough to overflow a signed word WRAPS the offset rather
 * than growing it, and a reconstruction that multiplied in 32 bits would diverge exactly there
 * (`test_blit.py`'s two `..._wraps_in_a_signed_word` cases, and `test_gameplay.py`'s three).
 *
 * The products that are NOT truncated — a room's stride, a map row's — are spelt in 32 bits at
 * their call sites rather than passed through here. */
static inline uint32_t muls_ext_w(int32_t multiplicand, int32_t multiplier) {
    return sign_ext16((uint32_t)(multiplicand * multiplier));
}

/* One `move.l (a3)+,(a2)+` run: `longs` longwords, ascending, reading and storing one longword at
 * a time. The order is observable whenever the two spans overlap, which is why it is transcribed
 * rather than replaced by a block move. */
static inline void copy_longs_ascending(uint8_t *image, uint32_t src, uint32_t dst,
                                        uint32_t longs) {
    for (uint32_t i = 0; i < longs; i++) {
        wr32(image + dst, be32(image + src));
        src = addr_add(src, LONG_BYTES);
        dst = addr_add(dst, LONG_BYTES);
    }
}

/* A longword table slot reached the way the 68000 reaches it: the index is scaled in 32 bits and
 * then added as a WORD (`asl.l #2` + `adda.w`), so a table index big enough to overflow a signed
 * word wraps rather than reaching past the table. */
static inline uint32_t longword_slot(uint32_t table, int16_t index) {
    return addr_add(table, muls_ext_w(index, (int32_t)LONG_BYTES));
}

/* A game WORD, read and written as the 68000 does: every one of this program's globals is a signed
 * word reached through `a4`, and `move.w`/`ext.w` is what a core means by reading one — the SIGN is
 * the game-specific half, which is why these are here rather than in the kit's `machine.h` beside
 * `be16`/`wr16`. They were `src/gameplay.c`'s private pair; they moved when `src/frontend.c` became
 * the second core to want them, which is the rule this header states above. */
static inline int16_t word_at(const uint8_t *image, uint32_t address) {
    return (int16_t)be16(image + address);
}

static inline void set_word(uint8_t *image, uint32_t address, int16_t value) {
    wr16(image + address, (uint16_t)value);
}

/* One `move.w`: the width of every one of this program's globals, and the stride of every WORD table
 * it indexes — the room grid's columns, a room's four entry points, the GEM parameter block's
 * arrays. The 68000 reaches them with an `asl.l #1` or a `muls.w #2` on the index. */
#define WORD_BYTES 2u

#endif /* BUBBLEGHOST_COMMON_H */
