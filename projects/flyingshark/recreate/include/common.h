/* common.h — the idioms MORE THAN ONE core needs, and nothing else.
 *
 * `../README.md` ("Adding a function") says a helper with one caller belongs in that caller's file
 * and that the day a SECOND core needs one it moves here. This file is that day. It exists because
 * `test_constants.py::test_no_constant_is_defined_in_two_files` refuses one NAME in two files and
 * the alternative was one fact under four names: `SCC_TRUE` in `src/entity.c`, `SCC_BYTE_SET` in
 * `src/weapons.c`, `PLAYER_FLAG_SET` in `src/player.c` and `SND_FLAG_SET` in `include/sound.h` were
 * all 0xff and all the same 68000 instruction.
 *
 * APPEND-ONLY, and the bar for appending is TWO CORES. Something one subsystem uses stays in that
 * subsystem's header, where its owner can read it beside the routine it belongs to.
 *
 * What is NOT here: the 68000 primitives themselves — `be16`, `wr16`, `addr_add`, `rotate_right32`,
 * `loop_passes` — which are the kit's, in `tools/recreate_kit/include/machine.h`, and shared by
 * every project rather than by this one. `SCC_TRUE` and `addr_sub` below arguably belong there too
 * (`STATUS.md`, "Follow-ups the kit should absorb"); they are here until the kit takes them.
 */
#ifndef FLYINGSHARK_COMMON_H
#define FLYINGSHARK_COMMON_H

#include <stdint.h>

#include "machine.h"
#include "display_list.h"
#include "hud.h"          /* `A_const_words_0123` and its stride, which `const_word` below reads */

/* What a 68000 `Scc` writes when its condition holds: ONE BYTE of ones.
 *
 * This is a width fact and not merely a value. Every flag in this program that is SET by `st` is
 * CLEARED by `clr.w`, so the set half touches the high byte of a word the clear half zeroes whole —
 * and a candidate that stored the word 0xffff would agree with every case whose record was already
 * zero and differ the moment one was not. Each store below is therefore spelt at the width the
 * instruction really has, with `image[addr] = SCC_TRUE` and not `wr16`.
 */
#define SCC_TRUE 0xffu

/* The 68000 pointer step BACKWARD, which `machine.h` gives no name of its own.
 *
 * `addr_add(base, (uint32_t)-(int32_t)delta)` is the alternative at each site and is the least
 * readable expression either file had. Same wraparound, same 32 bits, spelt as what it is: a
 * `subq`/`suba` on an address register is a full 32-bit subtract however narrow its operand.
 */
static inline uint32_t addr_sub(uint32_t base, uint32_t delta) { return base - delta; }

/* One whole six-byte display record: `move.w / move.w / move.b / move.b` in field order.
 *
 * Four routines in two subsystems write a record whole — `hud.c`'s `publish_slot`, and `entity.c`'s
 * `enemy_bomb_drop`, `item_publish_one` and `publish_clear` — and every one of them writes these
 * four fields in this order at these widths, because that is the order and the width the original's
 * four stores have. The narrowing of `frame` and `active` to bytes is the whole point: the frame is
 * `move.b d0,4(a1)` on a word the caller computed, and the active byte is the LOW half of a word
 * (`include/display_list.h`).
 *
 * `include/display_list.h` stays a LAYOUT-ONLY header — offsets, sizes and the two active values,
 * no code — so the writer lives here, where a core that includes it gets both.
 */
static inline void display_record_write(uint8_t *image, uint32_t record, uint16_t x, uint16_t y,
                                        uint8_t frame, uint8_t active) {
    wr16(image + addr_add(record, DISPLAY_REC_X), x);
    wr16(image + addr_add(record, DISPLAY_REC_Y), y);
    image[addr_add(record, DISPLAY_REC_FRAME)] = frame;
    image[addr_add(record, DISPLAY_REC_ACTIVE)] = active;
}

/* ONE WORD OUT OF `A_const_words_0123`, the table of 0..9 this program spells its small immediates
 * by READING rather than by writing (`move.w $176ae,$17712` is "lives = 1").
 *
 * The index IS the value, because the table is the identity — but the call has to reproduce the
 * READ: a case that poisons the table sees an immediate and a table read differ. Five files make
 * it — `src/init.c`, `src/player.c`, `src/frontend.c`, `src/scroll.c` and `src/hud.c` — and
 * `be16(image + A_const_words_0123 + 5 * CONST_WORD_BYTES)` at each site reads as arithmetic
 * rather than as the index the instruction names.
 */
static inline uint16_t const_word(const uint8_t *image, unsigned index) {
    return be16(image + A_const_words_0123 + index * CONST_WORD_BYTES);
}

/* A RUN OF `move.l (a0)+,(a1)+` — the copy this program's unrolled blitters, the title picture's
 * 8,000-longword move and level 2's scenery band are all made of.
 *
 * Longwords and not bytes because that is the instruction: a byte loop would agree with every case
 * whose length is a multiple of four and differ on none of them, and the width is what says the
 * original moved 32 bits at a time. `addr_add` on each step, so the cursors wrap at 32 bits the way
 * an address register does.
 */
#define LONG_BYTES 4u

static inline void copy_longs(uint8_t *image, uint32_t src, uint32_t dst, unsigned longs) {
    for (unsigned index = 0; index < longs; index++)
        wr32(image + addr_add(dst, index * LONG_BYTES), be32(image + addr_add(src, index * LONG_BYTES)));
}

#endif /* FLYINGSHARK_COMMON_H */
