/* shifter.h — THE PORT'S ONE SHIFTER SINK (this header and src/shifter.c, and nothing else).
 *
 * The ST's video shifter is not in the game's address space as far as this reconstruction models it:
 * the screen base at $ff8201/$ff8203 and the sixteen colour registers at $ff8240.. lie off the
 * loaded image, so the kit's oracle DROPS every write to them (tools/recreate_kit/include/hw.h
 * models hardware READS and has no `hw_write8` to mirror them with). Three reconstructed routines in
 * three files nevertheless make those writes because the original makes them — `flip_screen`
 * (src/game.c), `set_palette` / `clear_palette` (src/stage.c) and the boot slices (src/boot.c) — and
 * this header is where all of them meet.
 *
 * WHY IT IS A MODULE AND NOT A HELPER IN WHICHEVER FILE HAPPENED TO NEED IT FIRST. The sink carries
 * a `WB_ON_TARGET` arm: off target the write vanishes, and on target it is a call into
 * ../atari/wonderboy_backend.c, which owns the translation from the game's 512 KB map onto the array
 * GEMDOS really placed. That arm was written out twice — once in src/game.c for the screen base and
 * the colour-0 flash, once in src/stage.c for the palette row — and a correction applied to one copy
 * would have left the other file writing to the wrong place on the one build where the write is
 * real. One statement, three callers; `../atari/build.sh`'s `assert_the_sink_arm_lives_in_one_place`
 * is what refuses a fourth.
 *
 * WHY THE OFF-TARGET HALF IS `static inline` AND LIVES HERE RATHER THAN IN src/shifter.c, and this
 * is a MEASUREMENT and not a preference. The differential `.so` is linked from separately compiled
 * translation units, so an empty sink DEFINED in another one is a real call the compiler must make:
 * moving the two routines out of src/stage.c and src/game.c and leaving the empties behind an extern
 * declaration turned `set_palette` from two instructions (a HEAD build: the whole sixteen-iteration
 * loop deleted, reads and all) into that loop with sixteen `bl shifter_palette_write` in it, and
 * stage.o from 25 calls to 58. Nothing OBSERVABLE changed — the sink still writes nowhere — but the
 * suite that pins this port would have been measuring different generated code from the one the
 * batch that verified it measured, for no gain. Declared empty and `inline` HERE, every caller's
 * off-target codegen is what it was: the calls fold away and the reads that feed them fold with
 * them. On target the same two names are ordinary externs and src/shifter.c defines them once.
 *
 * WHAT IS AND IS NOT PINNED, and it is the same standing hole `set_palette` has carried since batch
 * 12: no memory differential can see any of these writes HAPPEN, because the destination is not an
 * image byte. What the host suite pins is the reads that FEED them and the order they are made in;
 * what the on-target modes pin is the ordered write stream that reaches the hardware
 * (../atari/README.md §11's timeline). ../STATUS.md registers the kit-side remedy — a
 * dropped-hardware-write LEDGER — as an idea rather than as work any batch has done.
 *
 * THE IMAGE IS NOT A PARAMETER to anything here, exactly as it is not one for the writes
 * `set_palette` makes: every destination is a hardware register and not an image byte.
 *
 * THE ADDRESSES STAY IN ../include/wonderboy.h, which is the port's one source of truth for an
 * address, and this header deliberately defines none of its own: ../atari/layout.py scrapes a NAMED
 * list of headers for `#define`s and a constant defined here would be outside it. The list carries
 * this file so that a later one cannot be added silently.
 */
#ifndef WONDERBOY_SHIFTER_H
#define WONDERBOY_SHIFTER_H

#include <stdint.h>

/* $ff8201/$ff8203 — the screen base, as the TWO BYTES the hardware has rather than as the address
 * they compose. An STF's video base register is bits 23-16 and 15-8 in two registers with no low
 * byte; both callers (`flip_screen` from the image's own front-buffer bytes, `boot_prompt_screen`
 * from two immediates) write them as two separate `move.b`s, and the shim's translation shadows them
 * one at a time (../atari/wonderboy_backend.c). A single address argument would hide the pair the
 * backend has to see.
 *
 * ...and $f944's own sink, one shifter COLOUR register. The index arithmetic happens in
 * src/shifter.c, at the one place that iterates, so the shim's store takes an absolute register and
 * has no loop and no indexed addressing mode of its own to disagree with the 68000 about
 * (docs/on-target-execution.md, taxonomy 6: Joust's sixteenth pen landed in the resolution
 * register). Four callers — `set_palette` and `clear_palette` write the whole row,
 * `boot_credits_screen` raises one pen, and `flip_screen`'s lightning flash writes WB_FLASH_PEN,
 * which is the port's one `move.w #imm,abs.l` outside a palette row and is colour register 0 like
 * any other. */
#ifdef WB_ON_TARGET
void shifter_screen_base_write(uint8_t high, uint8_t mid);
void shifter_palette_write(unsigned index, uint16_t colour);
#else
static inline void shifter_screen_base_write(uint8_t high, uint8_t mid) {
    (void)high;
    (void)mid;
}

static inline void shifter_palette_write(unsigned index, uint16_t colour) {
    (void)index;
    (void)colour;
}
#endif

#endif /* WONDERBOY_SHIFTER_H */
