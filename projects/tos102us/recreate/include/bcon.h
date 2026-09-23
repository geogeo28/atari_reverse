/* bcon.h — the BIOS cores another translation unit calls, and the door it calls them through.
 *
 * `src/bios/bcon.c` is `Bconstat`/`Bconin`/`Bconout`/`Bcostat` and `src/bios/drvmap.c` is `Drvmap`
 * — `trap #13` leaves the rest of TOS reaches a character device (and the drive map) through.
 * GEMDOS is the first caller outside the BIOS, and it is a caller BY TRAP: the ROM reaches all five
 * through `GEMDOS_BIOS_TRAMPOLINE` ($fc4eac), which parks its own return address at
 * `GEMDOS_BIOS_RETURN_SLOT` and takes the machine's own `trap #13` over the frame its caller
 * pushed. Deliberately not an inventory of `src/bios/`: `include/xbios.h`'s rule, said for the
 * BIOS — what is declared is what another translation unit calls.
 *
 * THE TWO BUILDS REACH THEM TWO WAYS, and that is what the helpers at the bottom are:
 *
 *   * ON TARGET there is a machine, so the call is the ROM's: push the trampoline's frame, take a
 *     real `trap #13`, and let the vector at $b4 dispatch it. A GEMDOS leaf's cost therefore
 *     includes the trap and the BIOS dispatcher, exactly as the original's does.
 *   * OFF TARGET (`RECREATE_HOST_DIFFERENTIAL`) there is no trap to take, so a caller calls the
 *     core directly, which is what ROM mode asks of it (`tools/recreate_kit/TRAP_MODEL.md`), and
 *     these declarations are what let the compiler check that call.
 *
 * `entry_d0` IS PART OF THE FOUR CHARACTER-DEVICE CONTRACTS, not a formality — and only of the
 * DIRECT call, since a trap hands the register over by itself. Every one of the four can give a
 * caller back a register it never wrote — a device whose table entry is the shared `rts`, or a driver whose whole body
 * writes no D0 at all — so what the trap dispatcher left in D0 has to arrive as an argument. A
 * caller inside TOS reaches them through that dispatcher, whose `move.l 0(a0,d0.w),d0` leaves the
 * ROUTINE'S OWN ADDRESS there: `BIOS_BCONOUT` and its siblings, which are the values a GEMDOS leaf
 * passes.
 */
#ifndef TOS102US_BCON_H
#define TOS102US_BCON_H

#include <stdint.h>

/* $fc0984 — is there a character waiting on `device`? `$ffffffff` if there is, 0 if not. */
uint32_t bios_bconstat(uint8_t *image, uint32_t entry_d0, uint16_t device);

/* $fc098c — one character off `device`, BLOCKING until the interrupt handler queues one. The whole
 * longword is the result: the IKBD's is a scancode word over an ASCII word. */
uint32_t bios_bconin(uint8_t *image, uint32_t entry_d0, uint16_t device);

/* $fc099c — one character to `device`. What comes back is per driver and mostly scratch. */
uint32_t bios_bconout(uint8_t *image, uint32_t entry_d0, uint16_t device, uint16_t character);

/* $fc0994 — can `device` take another character? `$ffffffff` if it can, 0 if not. */
uint32_t bios_bcostat(uint8_t *image, uint32_t entry_d0, uint16_t device);

/* $fc0a2e — which drives exist, as one bit each. `Dsetdrv` answers with it. */
uint32_t bios_drvmap(const uint8_t *image);

#ifndef RECREATE_HOST_DIFFERENTIAL
/* ---- the trampoline's frame, on target ---------------------------------------------------------
 *
 * Three shapes, because the BIOS calls GEMDOS makes take one, two or three argument words. Each is
 * the frame `GEMDOS_BIOS_TRAMPOLINE`'s caller pushed — the function number at `(sp)`, its arguments
 * above it — with the `trap #13` the trampoline itself takes, and the caller's own `addq.l` to drop
 * it again.
 *
 * WHAT THE TRAP TAKES AND GIVES BACK is `src/bios/trap.S`'s published contract: D0 is the result,
 * and D1/D2/A0/A1/A2 come back holding whatever the dispatcher and the driver left in them.
 *
 * THE PUSHES MUST USE `d` CONSTRAINTS (or pinned register variables), never `g`: a `g` operand can
 * be a memory operand relative to SP, and the second push would then read it through a stack
 * pointer the first push has already moved. Measured, not feared.
 */
#define BIOS_TRAP_CLOBBERS "d1", "d2", "a0", "a1", "a2", "memory", "cc"

/* fn — `Drvmap` ($0a) and every other BIOS call that takes no argument: one word, `addq.l #2`. */
static inline uint32_t bios_trap_plain(uint16_t fn)
{
    register uint32_t result __asm__("d0");

    __asm__ volatile ("move.w %1,-(%%sp)\n\t"
                      "trap #13\n\t"
                      "addq.l #2,%%sp"
                      : "=d"(result)
                      : "i"(fn)
                      : BIOS_TRAP_CLOBBERS);
    return result;
}

/* fn, device — `Bconstat` ($01), `Bconin` ($02) and `Bcostat` ($08): two words, `addq.l #4`. */
static inline uint32_t bios_trap_device(uint16_t fn, uint16_t device)
{
    register uint32_t result __asm__("d0");

    __asm__ volatile ("move.w %1,-(%%sp)\n\t"
                      "move.w %2,-(%%sp)\n\t"
                      "trap #13\n\t"
                      "addq.l #4,%%sp"
                      : "=d"(result)
                      : "d"(device), "i"(fn)
                      : BIOS_TRAP_CLOBBERS);
    return result;
}

/* fn, device, character — `Bconout` ($03): three words, `addq.l #6`. */
static inline uint32_t bios_trap_device_char(uint16_t fn, uint16_t device, uint16_t character)
{
    register uint32_t result __asm__("d0");

    __asm__ volatile ("move.w %1,-(%%sp)\n\t"
                      "move.w %2,-(%%sp)\n\t"
                      "move.w %3,-(%%sp)\n\t"
                      "trap #13\n\t"
                      "addq.l #6,%%sp"
                      : "=d"(result)
                      : "d"(character), "d"(device), "i"(fn)
                      : BIOS_TRAP_CLOBBERS);
    return result;
}
#endif /* !RECREATE_HOST_DIFFERENTIAL */

#endif /* TOS102US_BCON_H */
