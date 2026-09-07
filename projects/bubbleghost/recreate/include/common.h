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
 *   * `copy_longs_ascending` and the run it is built out of are a loop SHAPE — an unroll factor
 *     and a barrier placement measured on this program's own copies — not an opcode. Their
 *     one-`move.l` step is a different question, and the note over it registers the answer.
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

/* ---- the copy run every blit in this program is built out of ------------------------------------
 *
 * WHY THIS IS SPELT THE WAY IT IS, so that the next reader does not simplify it back. The 68000 has
 * no block move: a copy is a run of `move.l (a3)+,(a2)+` at 20 cycles a longword, and the original
 * spends nothing else on any of its blits — `present_room` @ 0x13286 closes ONE `dbf` around
 * COPY_RUN_UNROLL of them, which measured 21.9 cycles a longword. Written as the obvious loop over
 * two 32-bit image OFFSETS (`wr32(image + dst, be32(image + src))`, then `+= 4` on each) the same
 * copy cost 57.4, which was 67% of this port's whole frame-time gap (`atari/README.md`,
 * "Performance"). NONE of that was byte swapping — on the target `be32`/`wr32` ARE the aligned
 * native accesses (machine.h). It was that GCC kept the two OFFSETS and recomputed `image + offset`
 * per longword instead of postincrementing two address registers.
 *
 * Three GCC behaviours shape what is below. `machine.h` OWNS the measurement of each — its
 * CURSOR_BARRIER and COUNT_BARRIER notes — and this is only what they come to here:
 *
 *   * the run walks two LOCAL cursors, barriered after each step, so that each copy addresses
 *     through the cursor it advances instead of as a displacement off the one before it;
 *   * the block is SPELT OUT, because a `for` over COPY_RUN_UNROLL comes back as a counted loop;
 *   * the block COUNT is barriered, because a count GCC can read off the source is not a counter
 *     to it at all.
 *
 * WHAT PINS THE BLOCK'S LENGTH IS THE DIFFERENTIAL, not the assertion under it, which can only
 * compare a constant to a literal: `blocks_left` is `longs / COPY_RUN_UNROLL`, so a block spelling
 * one step too few short-runs every copy in the program by 1/32 — measured 2026-09-07, dropping one
 * `step` reddens 191 cases.
 *
 * Nothing observable moves. A run is still one longword at a time in the original's own order —
 * which is what makes an overlapping source and destination come out as they did — and on the
 * little-endian host the accessors stay the byte assembly the differential runs. The one thing the
 * cursors do NOT reproduce is `addr_add`'s 32-bit wrap, and the FAILURE MODE changed direction with
 * it: where a wrapped offset came back inside the image, an ascending run now walks off the TOP of
 * the buffer and a descending one off the BOTTOM. No span in this program is within three orders of
 * magnitude of that, and `make guarded` is what would find one that was — its PROT_NONE reserves
 * cover both directions (4 GiB above, 16 MiB below).
 *
 * REGISTERED, NOT DONE — THE KIT HOIST. `copy_one_longword` below is the same helper, under the
 * same name, as `projects/wonderboy/recreate/include/scroll.h`'s, whose own header states the
 * trigger — "a user in ANOTHER project" — and the home: `tools/recreate_kit/include/machine.h`,
 * beside the CURSOR_BARRIER it is built on. That trigger is now met, and Zynaps' `src/init.c`
 * registers three more copies of the same loop waiting on the same move. Doing it is a kit change
 * plus a Wonder Boy re-verification, so it belongs to whoever moves the second one — exactly as
 * `atari/README.md`'s "Unpinned" item 12 holds the five files this directory shares with Zynaps.
 */

/* One `move.l (a3)+,(a2)+`. */
static inline void copy_one_longword(const uint8_t **from, uint8_t **to) {
    wr32(*to, be32(*from));
    *from += LONG_BYTES;
    *to += LONG_BYTES;
    CURSOR_BARRIER(*from);
    CURSOR_BARRIER(*to);
}

/* `present_room`'s own `dbf` block: 32 copies to one loop close, which is the unroll the shipped
 * binary chose and the one this port matches. EVERY caller pays that size, not only the ones whose
 * originals unroll — the bonus bar's 40-longword scanline gets a 32-block plus an 8-longword tail
 * where the original spells one `dbf` — and the bill is +1,134 B of `.text` across the three cores,
 * bought knowingly against the size gate's 74,034 B of spare (measured 2026-09-07). */
#define COPY_RUN_UNROLL 32u

/* COPY_RUN_UNROLL of `step`, spelt out — the second GCC behaviour above. A macro cannot repeat
 * itself COPY_RUN_UNROLL times, so the constant is asserted against the length written here; what
 * pins the length itself is the differential, as the note above says. */
#define UNROLLED_RUN_BLOCK(step)                                        \
    do {                                                                \
        step; step; step; step; step; step; step; step;                 \
        step; step; step; step; step; step; step; step;                 \
        step; step; step; step; step; step; step; step;                 \
        step; step; step; step; step; step; step; step;                 \
    } while (0)
_Static_assert(COPY_RUN_UNROLL == 32u, "UNROLLED_RUN_BLOCK is written out at 32 steps");

/* `longs` of `step`, as whole UNROLLED_RUN_BLOCKs and then one at a time. `longs` is a compile-time
 * constant at every call but `room_wipe_in_step`'s present, so the division and one of the two loops
 * usually fold away; where they do not, the division is a shift and a mask paid once for a run of
 * thousands. It is read into a local first so the macro evaluates it ONCE; `step` is expanded once
 * per longword, which is the point.
 *
 * ONLY ONE CALLER EVER REACHES THE SINGLES LOOP — the bonus bar's 40-longword scanline, whose
 * remainder is 8. Every other count in the program is an exact multiple of COPY_RUN_UNROLL (6400,
 * 1280, 1024, 7680, and `room_wipe_in_step`'s present, which is always 160 * (step + 1)), so a
 * fault in that loop is green in all of them and red only through `test_gameplay.py` and
 * `test_frontend.py` — `test_blit.py`, the battery that owns these helpers, does not reach it.
 *
 * THE `blocks_left != 0` GUARD IS NOT DECORATION, and no caller exercises it: the block loop is a
 * `do`/`while` (which is what keeps the count a counter), so a run of fewer than COPY_RUN_UNROLL
 * longwords would go round 2^32 times without it. A future partial-span caller is what it is for. */
#define UNROLLED_RUN(longs, step)                                       \
    do {                                                                \
        uint32_t run_longs = (longs);                                   \
        uint32_t blocks_left = run_longs / COPY_RUN_UNROLL;             \
        uint32_t singles_left = run_longs % COPY_RUN_UNROLL;            \
        if (blocks_left != 0) {                                         \
            COUNT_BARRIER(blocks_left);                                 \
            do {                                                        \
                UNROLLED_RUN_BLOCK(step);                               \
            } while (--blocks_left != 0);                               \
        }                                                               \
        while (singles_left-- != 0) {                                   \
            step;                                                       \
        }                                                               \
    } while (0)

/* One `move.l (a3)+,(a2)+` run: `longs` longwords, ascending, reading and storing one longword at
 * a time. The order is observable whenever the two spans overlap, which is why it is transcribed
 * rather than replaced by a block move. */
static inline void copy_longs_ascending(uint8_t *image, uint32_t src, uint32_t dst,
                                        uint32_t longs) {
    const uint8_t *from = image + src;
    uint8_t *to = image + dst;

    UNROLLED_RUN(longs, copy_one_longword(&from, &to));
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
