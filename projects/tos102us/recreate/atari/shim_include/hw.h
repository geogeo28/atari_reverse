/* hw.h — the I/O doors this reconstruction has, as a 68000 build makes them: the access itself.
 *
 * It shadows `tools/recreate_kit/include/hw.h`, which states this file's contract in its own words:
 * "ON TARGET the build supplies all three as the real volatile access, exactly as it supplies
 * psg.h's ports and hw_write8/16/32: `*(volatile uint8_t *)addr`, `*(volatile uint16_t *)addr` and
 * `*(volatile uint32_t *)addr`. It does not compile src/hw.c, so there is no map and no declaration
 * in the chain — the machine answers."
 * The seam is the INCLUDE PATH, as it is for `psg.h` next door; the differential build never sees
 * this directory, so the host `.so` keeps the seeded model and the ordered ledger Tier 1 compares.
 *
 * OUTRIGHT rather than through `#include_next`, for zynaps' reason: the kit declares these `extern`
 * and C forbids redeclaring one `static`.
 *
 * SEVEN DOORS NOW, IN THREE GROUPS, AND WHAT IS STILL MISSING IS AS DELIBERATE AS WHAT IS HERE:
 *
 *   * the DECLARED I/O MAP's reads — `io_read8`, `io_read16`, `io_read32` — which is every byte of
 *     the I/O page the named models do not own (`Getrez`'s $ff8260, `Physbase`'s two base bytes,
 *     `Setcolor`'s palette word, `Rsconf`'s four USART registers);
 *   * its STORES — `hw_write8` and `hw_write16` — landed with `xbios_setscreen` and
 *     `xbios_setcolor`, the first cores to write a chip register (see their own note below);
 *   * the SEEDED MODEL's read and its POLL — `hw_read8` landed with `src/xbios/acia.c` and
 *     `hw_poll8` with `src/bios/ikbd.c`'s ACIA handler, where the address is a Phase-7 NAMED slot
 *     rather than an ordinary declared byte (their notes say why the names stay apart in the core
 *     and collapse here).
 *
 * `hw_write32`, `io_poll8` and the three read-modify-writes remain declared by the kit and
 * implemented by NO core here — so a core that acquires one fails at LINK, naming the symbol, which
 * is the right outcome: each is a decision about what the target build does with an access the
 * oracle only ledgers, and writing it before a core needs one would be writing it with nothing to
 * check it against. Add each one here, with its evidence, when the core that needs it lands.
 *
 * Under the oracle these accesses reach the DECLARED I/O MAP exactly as the ROM's own `move.b
 * $ffff8260,d0` does — the shim decodes the I/O page rather than serving it from the image — which
 * is what makes a Tier 3 row over such a core a comparison rather than two fabricated zeroes
 * (tools/recreate_kit/rom_bench.py).
 */
#ifndef TOS102US_SHIM_HW_H
#define TOS102US_SHIM_HW_H

#include <stdint.h>

/* `move.b addr,d0` — the byte the machine answers, with nothing between the core and the bus. */
static inline uint8_t io_read8(uint32_t addr)
{
    return *(volatile uint8_t *)addr;
}

/* ...and `move.w addr,d0`. One access of one width, not two bytes: a 68000 word read of an I/O
 * register is one bus cycle, and a chip that latches on access would see a different thing. */
static inline uint16_t io_read16(uint32_t addr)
{
    return *(volatile uint16_t *)addr;
}

/* ...and `move.l addr,d0`, which the shifter's screen-base and video-counter registers are read
 * through. A 68000 splits it into two bus cycles, but they are the two cycles the ORIGINAL's own
 * `move.l` makes: what would be wrong is spelling it as two `io_read16` calls, which is a different
 * instruction and, on a register that latches, a different thing to the chip. */
static inline uint32_t io_read32(uint32_t addr)
{
    return *(volatile uint32_t *)addr;
}

/* ---- the STORES (Phase 10), which under the oracle are a ledger and here are the instruction ----
 *
 * Added with the cores that needed them, as the note above prescribes: `xbios_setscreen` stores the
 * shifter's two screen-base BYTES at $ff8201/$ff8203 (`move.b 9(sp),$ffff8201`) and `xbios_setcolor`
 * one palette WORD at $ff8240+2n (`move.w 6(sp),0(a0,d1.w)`).
 *
 * THE WIDTH IS THE WHOLE DECISION HERE, and it is why there is one function per width rather than a
 * `size` argument: the shifter's screen-base bytes sit at ODD addresses two apart with the video
 * counter's own registers between them, so a byte store widened to a word writes $ff8202 as well —
 * which is the middle byte of the video address counter on a running machine. The ledger compares
 * the width a core DECLARED, so a mismatch reds under the oracle before it can reach a machine.
 *
 * The read-modify-writes and `hw_write32` stay absent for the reason the header note gives: no core
 * here has one, and a core that acquires one fails at LINK naming the symbol rather than silently
 * getting a definition nobody weighed. */
static inline void hw_write8(uint32_t addr, uint32_t value)
{
    *(volatile uint8_t *)addr = (uint8_t)value;
}

static inline void hw_write16(uint32_t addr, uint32_t value)
{
    *(volatile uint16_t *)addr = (uint16_t)value;
}

/* ---- the SEEDED READ model's one door, which here is the same instruction as `io_read8` --------
 *
 * Added with `src/xbios/acia.c`, whose IKBD sender spins on `$fffc00` until the 6850's transmit
 * register is empty. That address is one of the Phase-7 NAMED slots (os.h, `OS_HW_ACIA_STATUS`)
 * rather than an ordinary byte of the declared I/O map, so off target it is served and ledgered by
 * a DIFFERENT model and a core has to spell which one it means — `hw_read8` for a named slot,
 * `io_read8` for everything else, and each refuses the other's addresses.
 *
 * ON TARGET THE DISTINCTION VANISHES, and that is the whole of this definition: there is no map and
 * no named set on a real machine, only the bus, so this is the same `move.b addr,d0` its neighbour
 * above is. Keeping the two names apart in the CORE is what keeps the off-target models straight;
 * collapsing them here is what the machine does.
 *
 * VOLATILE for the reason `sched.h`'s poll is: the ACIA's status byte is changed by the chip and by
 * nothing in the caller's instruction stream, so a compiler that hoisted the load out of the send
 * loop would leave a program that spins on a register for ever. */
static inline uint8_t hw_read8(uint32_t addr)
{
    return *(volatile uint8_t *)addr;
}

/* ...and the POLL of that same slot, which off target is the read PLUS the model's answer to "could
 * you still serve it?" and here is the read plus `1`.
 *
 * `isr_acia` spins on GPIP bit 4 until both 6850s go idle, and off target that loop ends when the
 * case's declared list runs out — a refused read hands the core `0`, which the loop would read as
 * "still asserting" and spin on for ever. There is no model here and no declaration to run out, so
 * the answer is always "served" and the loop is the machine's own, exactly as `hw_read8`'s note
 * above says. VOLATILE for that note's reason too: the byte is changed by the chips and by nothing
 * in the caller's instruction stream.
 *
 * `io_poll8` stays absent for the header's rule: no core here polls an ordinary I/O byte, and a core
 * that acquires one fails at LINK naming the symbol rather than getting a definition nobody weighed.
 */
static inline int hw_poll8(uint32_t addr, uint8_t *seen)
{
    *seen = *(volatile uint8_t *)addr;
    return 1;
}

#endif /* TOS102US_SHIM_HW_H */
