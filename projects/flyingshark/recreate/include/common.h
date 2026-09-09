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
#include "os.h"           /* `OS_SCHED_POLL_MAX`, the give-up below counts against */
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

/* THE BUSY-WAIT SEAM: 1 while a spin on an interrupt-written byte may go round again.
 *
 * The original's waits have no bound and a TARGET build must have none either — the ACIA really
 * does write the byte, so the loop really does end. Off target nothing can change memory while the
 * candidate runs except the case's own schedule, so a wait the schedule never releases is an
 * INFINITE LOOP: the suite HANGS instead of failing, and a hung suite decides nothing
 * (`docs/agent-playbook.md` §10). One mutation here already did it — `load_level_assets`' level
 * compare read unsigned takes a negative level into the disc prompt, whose schedule that case has
 * no reason to carry.
 *
 * So the give-up lives behind `RECREATE_HOST_DIFFERENTIAL`, the `-D` the harness build already
 * passes and no `.PRG` build does (`tools/recreate_kit/kit.mk`, `atari/build.sh`), and compiles to
 * a constant 1 on target with the counter and the tally both dropped — which is the original's own
 * behaviour, a spin that ends when and only when the interrupt writes the byte.
 *
 * EXHAUSTION TALLIES A REFUSAL, exactly as `sched_wait8` does (`tools/recreate_kit/include/sched.h`,
 * "WHY A CAP AT ALL"): a wait the case's schedule never released has already decided nothing, so the
 * run must be thrown away with a name on it rather than allowed to compare whatever the routine did
 * next. Without the tally the give-up is worse than the hang it replaces — the candidate silently
 * carries on down a path the original never took, and the case comes back green or red about that.
 * `test_frontend.py::test_a_wait_the_schedule_never_releases_is_REFUSED_and_not_quietly_abandoned`
 * is the positive control, and the only case that reaches this line.
 *
 * WHAT THE DIAGNOSTIC WILL SAY. `os_refused` is one tally shared by every refusing helper, and this
 * is not the kit's own wrapper, so `g_sched_exhausted` stays 0 and `harness._sched_refusal_hint`
 * prints no "ran to OS_SCHED_POLL_MAX" clause: a run that dies here reports a bare refused os_* call
 * and sends the reader after a missing guard. Check the wait sites first (STATUS.md, "Follow-ups the
 * kit should absorb" — the row that asks the kit for this predicate).
 *
 * A CALLER MUST HONOUR THE 0. All four callers do, and each spells it as the shortest correct
 * thing — a `return` out of the routine, not a `break` back into its body:
 * `src/frontend.c`'s `wait_for_disc_swap` (which therefore does NOT run `probe_disc`) and
 * `debug_wait_for_keypad4`, `src/hud.c`'s `console_show_message` fire-release wait, and
 * `src/player.c`'s pause key.
 */
static inline int wait_may_go_round_again(unsigned polls) {
#ifdef RECREATE_HOST_DIFFERENTIAL
    if (polls < OS_SCHED_POLL_MAX)
        return 1;
    os_refused(0);   /* the cap: tally it, so `harness.differential` throws the case away */
    return 0;
#else
    (void)polls;
    return 1;
#endif
}

#endif /* FLYINGSHARK_COMMON_H */
