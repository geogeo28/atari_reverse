/* wonderboy_backend.c — THE ON-TARGET SIDE OF THE KIT'S FOUR MODELS.
 *
 * The differential harness models four things the loaded image cannot hold: a seeded hardware READ
 * (`hw.h`), the direct YM2149 ports (`psg.h`), a scheduled write that releases a busy-wait
 * (`sched.h`), and the shifter WRITES the reconstruction sinks because the oracle drops them
 * (`src/game.c`, `src/stage.c`). Each of those headers says in as many words that a build for the
 * real machine excludes the kit's own C sources and supplies its own. This file is that supply.
 *
 * THE SURFACE IS A SET, AND IT IS SIX SYMBOLS PLUS THREE SINK SITES — enumerated, not estimated.
 * Taken from the union of the sixteen translation units under `../src/`, undefined symbols minus the
 * game's own; the kit's own `nm` agrees (`build/libwonderboy.so` has exactly one undefined symbol,
 * `bzero`, because kit.mk sweeps the kit sources into the same .so).
 *
 *   hw_read8        5 call sites   ../src/rng.c:33, ../src/behavior.c:2520,2522, ../src/sound.c:1057,1059
 *   psg_port_write 10 call sites   ../src/game.c:308, ../src/sound.c:145,147,148,149,989,995,996,998,1005
 *   psg_port_read   3 call sites   ../src/game.c:307, ../src/sound.c:146,1003
 *   sched_wait8     1 call site    ../src/game.c:47   (two wait SITES reach it: $60e and $64e)
 *   sched_poll16    2 call sites   ../src/game.c:398, 413
 *   os_refused      1 call site    ../src/sound.c:786 — NOT defined here: -DOS_NO_REFUSAL_TALLY makes
 *                                  the kit's os.h serve a `static inline` identity (os.h:57)
 *
 * THE LINE NUMBERS ARE A SNAPSHOT AND THEY SELF-STALED ONCE ALREADY — this very commit's `#ifdef`
 * insertion in ../src/game.c moved `sched_poll16`'s pair from 386/401 to 398/413 and the first draft
 * of this table shipped the old ones. Re-derive rather than trust:
 *
 *     grep -nE '\b(hw_read8|psg_port_read|psg_port_write|sched_wait8|sched_poll16|os_refused)\s*\(' ../src/*.c
 *
 * The COUNTS are what the claim rests on; ../atari/build.sh checks the SET after every link and does
 * not look at line numbers at all.
 *
 * AND FOUR MORE THE PORT DOES NOT NEED, stated because a set is only a claim if its complement is:
 *   sched_poll8     0 direct call sites — reached only THROUGH sched_wait8/sched_poll16, which this
 *                   file implements whole, so it is deliberately NOT defined. A future core that
 *                   calls it gets a link error, which is the failure this wants.
 *   g_dosound       0 call sites — Wonder Boy drives the chip directly and never issues XBIOS
 *                   Dosound, so `src/dosound_log.c` is simply left out of the link.
 *   os_giaccess / os_random / os_super / os_bconstat / os_bconin / os_crawio / the whole staged-file
 *                   model — 0 call sites each. THIS IS WHY THERE IS NO `shim_include/os.h` HERE.
 *                   Joust needs one because it calls five `static inline` os.h helpers that have no
 *                   link symbol; Wonder Boy calls none of them (project.toml's byte scan: the whole
 *                   program issues ONE TOS trap in its life, a Super). Every kit dependency this
 *                   game has is a real symbol, so the seam is pure link-time replacement.
 *   os_in_image     2 call sites (../src/blit.c) — `static inline` arithmetic over OS_IMAGE_SIZE,
 *                   correct on target unchanged.
 *
 * THE ADDRESSES ARE WRITTEN IN THE 24-BIT BUS FORM the reconstruction spells (`$ff820a`, `$fffa01`)
 * and put on the bus in the CPU's own form (`$ffff820a`, `$fffffa01`) by `hw_addr` below. On a 68000
 * the two are one location — there are no address lines above A23 — but a build whose CPU decodes 32
 * bits would fetch from an undecoded page, and the difference costs one `or.l`.
 */
#include <stdint.h>

#include "hw.h"
#include "psg.h"
#include "sched.h"
#include "os.h"
#include "wonderboy.h"

#include "wonderboy_target.h"

/* The 68000 puts 24 bits on the bus, so $00ff820a and $ffff820a are the same register. The
 * reconstruction spells the low form (bus.h, and the kit's hw.h: "pass os.h's constants"); the CPU
 * is handed the high one so that a 32-bit-decoding host reaches the same chip. */
#define HW_IO_PAGE      0xff000000u
#define HW_IO_LOW_BOUND 0x00ff0000u

static volatile uint8_t *hw_byte(uint32_t addr) {
    return (volatile uint8_t *)(uintptr_t)(addr >= HW_IO_LOW_BOUND ? (addr | HW_IO_PAGE) : addr);
}

static volatile uint16_t *hw_word(uint32_t addr) {
    return (volatile uint16_t *)(uintptr_t)(addr >= HW_IO_LOW_BOUND ? (addr | HW_IO_PAGE) : addr);
}


/* ---- hw.h: the seeded hardware READ becomes the read ------------------------------------------
 *
 * The model serves a byte the case DECLARED, refuses an undeclared one, and refuses a second read of
 * a volatile address in one run because "one number cannot be two". On target all four of those
 * refusals dissolve into the same sentence: THE READ IS REAL. Written out one per slot, because each
 * refusal's on-target truth is a different fact and the set is what this file is claiming:
 *
 *   OS_HW_MFP_GPIP     $fffa01  bit 7 is the monitor-detect line — a real level, and it is what
 *                               tempo_drop_value branches on first (../src/sound.c:1057).
 *   OS_HW_SHIFTER_SYNC $ff820a  bit 1 is the 50/60 Hz sync mode. THIS IS THE BuggyBoy REGISTER —
 *                               PORTABILITY.md §5's last row, the read that was green all the way to
 *                               real hardware because the oracle answered 0 for it. Here it answers
 *                               what the shifter holds. NOTE the model's refusal #4 (write-then-read)
 *                               is live for a whole-frame run: the boot chain writes this register at
 *                               $f91c and this port has not reconstructed the boot chain, so on
 *                               target the value read is whatever the SHIM's own video init left —
 *                               see wonderboy_main.c, which writes it exactly as $f906 does.
 *   OS_HW_SHIFTER_VCOUNT_MID/_LOW  $ff8207/$ff8209, the video address counter. The model's fourth
 *                               refusal exists because these two GENUINELY DIFFER between two reads
 *                               in one run; on target that is not a limitation, it is the point —
 *                               both PRNGs (../src/rng.c:33, ../src/behavior.c:2520) mix this
 *                               counter, and under the oracle it is always 0, "so the diff stays
 *                               clean while the game's randomness silently disappears"
 *                               (PORTABILITY.md §5). This is where the randomness comes back.
 *
 * NO ADDRESS FILTER. The model refuses an address outside its four because an undeclared byte would
 * be a fabrication; here every address answers for itself, and narrowing to the four would be a
 * check that can only ever reject a caller the model has already rejected off target. */
uint8_t hw_read8(uint32_t addr) {
    return *hw_byte(addr);
}


/* ---- psg.h: the ledger and the register file become the chip ----------------------------------
 *
 * $ff8800 is the select latch AND the read-back port; $ff8802 is write-only data. A read of the
 * chip is therefore "select, then read $ff8800", which is what the model's comment describes and
 * what the original does.
 *
 * THE SELECT/DATA PAIR IS NOT MADE ATOMIC, AND THAT IS THE ORIGINAL'S RACE REPRODUCED RATHER THAN A
 * HAZARD INTRODUCED. Two threads write this chip: `snd_music_tick`'s driver, from the vertical-blank
 * handler fifty times a second, and `snd_psg_silence` / `psg_set_drive_select`, from the frame. An
 * interrupt landing between a select and its data writes the interrupted register's value into the
 * interrupting one. Masking interrupts here would be a change to what the machine does that no
 * surface in this project could tell from the original, so it is recorded instead of taken: the
 * surface that would show it is the PSG WRITE TIMELINE (Hatari `--trace psg_write`) compared against
 * the shipped binary's, which is an M6-class check and is listed as such in README.md.
 *
 * `reg` IS NOT MASKED, for the model's reason: the ST's select latch decodes four bits, so a driver
 * that put anything in the upper nibble meant something the chip does not do, and masking here would
 * hide from the machine exactly what the model refuses. The chip does its own truncation. */
void psg_port_write(unsigned reg, uint8_t value) {
    *hw_byte(OS_PSG_PORT_SELECT) = (uint8_t)reg;
    *hw_byte(OS_PSG_PORT_DATA) = value;
}

uint8_t psg_port_read(unsigned reg) {
    *hw_byte(OS_PSG_PORT_SELECT) = (uint8_t)reg;
    return *hw_byte(OS_PSG_PORT_SELECT);
}


/* ---- sched.h: the scheduled store becomes the interrupt that really makes it ------------------
 *
 * Off target nothing can change memory while the candidate runs, so a busy-wait needs an agent and a
 * cap. On target both go away: the byte is written by an interrupt, and the wait ends when the
 * machine says so. sched.h states this contract itself — "ON TARGET this file IS EXCLUDED FROM THE
 * BUILD ... supplies its own `sched_wait8`/`sched_poll16` that loop without a cap".
 *
 * THE READ MUST BE `volatile` AND THAT IS THE WHOLE BUG THIS FUNCTION EXISTS TO NOT HAVE. The
 * reconstruction's own `bus_read_byte` is a plain array read; GCC is entitled to hoist it out of a
 * loop whose body it can see writes nothing, and the spin would never end. The two waits below read
 * through a `volatile` pointer for that reason and nothing else.
 *
 * `site_pc` IS THE MODEL'S BOOKKEEPING AND HAS NO MEANING HERE. It names the address at which the
 * ORIGINAL re-reads the polled byte, so that the candidate's polls and the oracle's arrivals can be
 * counted per wait; a real machine keeps that count in the program counter. Taken and dropped rather
 * than removed from the signature, because the signature is the kit's.
 *
 * WHAT WRITES THE BYTE, per site — the set, because a wait with no writer is a hang:
 *   $60e / $64e   WB_KEY_LAST_SCANCODE ($879) — the IKBD ACIA interrupt at $118. The reconstruction
 *                 has no `ikbd_acia_handler` ($754 is unported), so wonderboy_main.c installs one.
 *   $6aa / $6d0   WB_VBL_COUNTER ($74a) — `vbl_handler` (../src/game.c:334), which IS reconstructed
 *                 and which wonderboy_main.c hangs off the level-4 autovector, exactly as
 *                 `hw_init_vectors` ($f8bc) and the boot continuation ($e4e6) do.
 *
 * A GUARD, NOT A MASK. The addresses are the reconstruction's own constants and both are inside the
 * image, but the model bounds them and a backend that did not would differ from it on the one input
 * that could ever be wrong. `os_in_image` is the same test both shores use. */
static volatile uint8_t *image_byte(uint8_t *image, uint32_t addr) {
    uint32_t at = addr & WB_BUS_ADDR_MASK;
    return os_in_image(at, 1) ? (volatile uint8_t *)(image + at) : (volatile uint8_t *)0;
}

int sched_wait8(uint8_t *image, uint32_t addr, uint8_t until, uint32_t site_pc) {
    volatile uint8_t *at = image_byte(image, addr);

    (void)site_pc;
    if (!at)
        return 1;   /* the model reads 0 for an out-of-image byte and does not refuse; a wait on one
                     * would hang identically on both shores, so do not manufacture a hang here. */
    while (*at != until)
        ;
    return 1;
}

/* The WORD iterator. Always 1: the cap is the model's, and the caller owns the predicate
 * (../src/game.c's `wait_for_vbl_ready` and `wait_for_vbl_tick`), so this returns "go round again"
 * for ever and the loop ends on the game's own compare. The word is read at full width from an even
 * address, which is what the 68000 does and what `be16` compiles to on a big-endian target. */
int sched_poll16(uint8_t *image, uint32_t addr, uint32_t site_pc, uint16_t *seen) {
    uint32_t at = addr & WB_BUS_ADDR_MASK;

    (void)site_pc;
    *seen = os_in_image(at, 2) ? *(volatile uint16_t *)(image + at) : (uint16_t)0;
    return 1;
}


/* ---- the shifter sinks become stores ----------------------------------------------------------
 *
 * ../src/game.c and ../src/stage.c sink four write instructions over three registers, and
 * ../STATUS.md's batch 42 phase C measures the hole exactly: four named mutants over them — the
 * wrong buffer published, the two base bytes swapped, the flash's two arms swapped, and the sink
 * write moved above the timer store — ALL SURVIVE the whole differential suite. On target the sinks
 * become these two functions and every one of the four becomes measurable; README.md's milestone
 * table says by which check.
 *
 * THE SCREEN BASE NEEDS TRANSLATING AND THAT IS THIS FILE'S ONE PIECE OF REAL LOGIC.
 *
 * The game publishes an address out of its OWN address space: `move.b $74d.l,$ff8201.l` sends bits
 * 23-16 of WB_SCREEN_FRONT, whose value is $070000 or $078000 — absolute addresses in the 512 KB map
 * the original owns outright, because SWB.PRG relocates itself to $400 and takes the machine. This
 * build does not own the machine: the reconstruction runs on a 1 MiB array GEMDOS placed wherever
 * the TPA fell, so the buffer the game means is at `image + $70000`, and $070000 is TOS's own memory.
 * Publishing the game's byte unchanged would point the shifter at the operating system.
 *
 * So the two bytes are SHADOWED and re-emitted as `image_base + what the game asked for`. The
 * shadow is what makes it possible at all: bits 23-16 and 15-8 arrive in two separate instructions,
 * and the sum can carry out of the low half into the high one, so neither byte can be translated
 * without the other. Both hardware bytes are rewritten on each of the game's two writes.
 *
 * THE LOW BYTE IS NOT LOST, AND THAT IS AN ASSERTION ABOUT THE BASE. An STF's video base register
 * has no low byte (docs/on-target-execution.md, taxonomy 8), so this arithmetic is only exact while
 * `image_base` is 256-aligned — wonderboy_main.c rounds it up once at startup and READS THE RESULT
 * BACK. The game's own halves are 256-aligned by construction ($70000, $78000).
 *
 * ONE TRANSIENT IS INHERITED RATHER THAN ADDED: between the game's first byte and its second the
 * shifter is pointed at a mixed address, exactly as it is in the original, which also writes the two
 * bytes in two instructions. A vertical blank in that window displays one frame from the wrong
 * place. flip_screen issues both writes between its two waits, i.e. just after a vblank, which is
 * why the original gets away with it and so does this. */
static uint32_t screen_base_shadow;      /* what the GAME asked for, in ITS address space */
uint32_t wb_target_screen_base;          /* ...and what went on the bus. Read back by the smoke. */

void wb_target_shifter_byte(uint32_t reg, uint8_t value) {
    uint32_t published;

    if (reg == WB_SHIFTER_SCREEN_BASE_HIGH)
        screen_base_shadow = (screen_base_shadow & ~0xff0000u) | ((uint32_t)value << 16);
    else if (reg == WB_SHIFTER_SCREEN_BASE_MID)
        screen_base_shadow = (screen_base_shadow & ~0x00ff00u) | ((uint32_t)value << 8);
    else
        return;      /* no third byte-wide shifter register is written by this reconstruction */

    published = wb_target_image_base() + screen_base_shadow;
    wb_target_screen_base = published;
    *hw_byte(WB_SHIFTER_SCREEN_BASE_HIGH) = (uint8_t)(published >> 16);
    *hw_byte(WB_SHIFTER_SCREEN_BASE_MID) = (uint8_t)(published >> 8);
}

/* The colour registers need no translation — they hold colours, not addresses. `reg` is the absolute
 * register the reconstruction named ($ff8240 for colour 0 from flip_screen's flash, $ff8240 + 2*index
 * from set_palette's sixteen), so the index arithmetic stays at the call site where a reader meets
 * it and this is one store.
 *
 * ONE STORE THROUGH ONE POINTER, DELIBERATELY, and it is Joust's bug not being had again: a loop
 * over a `volatile uint16_t *` compiled to `move.w (%a0)+,(%a0,%d0.l)`, whose destination effective
 * address the 68000 computes AFTER the source postincrement, so every pen landed one register high
 * and the sixteenth hit the resolution register (docs/on-target-execution.md, taxonomy 6). There is
 * no loop here and no indexed addressing mode to get wrong; ../src/stage.c's `set_palette` owns the
 * iteration, one call per colour. */
void wb_target_shifter_word(uint32_t reg, uint16_t value) {
    *hw_word(reg) = value;
}


/* ---- freestanding libc ------------------------------------------------------------------------
 *
 * m68k-elf ships no libc for a `-nostdlib` link, and the reconstruction reaches one symbol:
 * `bzero`, which the compiler recognises out of `clear_message_buffer`'s 6400-byte clear
 * (../src/text.c). `memset`/`memcpy` are the shim's own, and are named here rather than in
 * wonderboy_main.c so that every definition GCC may synthesise a call to lives in one place.
 *
 * -fno-tree-loop-distribute-patterns keeps GCC from compiling each of these into a call to itself. */
void *memset(void *dst, int c, unsigned long n) {
    uint8_t *p = (uint8_t *)dst;
    while (n--)
        *p++ = (uint8_t)c;
    return dst;
}

void bzero(void *dst, unsigned long n) {
    (void)memset(dst, 0, n);
}

void *memcpy(void *dst, const void *src, unsigned long n) {
    uint8_t *d = (uint8_t *)dst;
    const uint8_t *s = (const uint8_t *)src;
    while (n--)
        *d++ = *s++;
    return dst;
}
