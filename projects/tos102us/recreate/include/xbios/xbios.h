/* The XBIOS cores one ANOTHER XBIOS core calls.
 *
 * Deliberately not an inventory of `src/xbios/`: everything else in there is reached only from
 * Python, through the candidate `.so`'s symbol table, and a declaration nobody includes is a second
 * place for a signature to drift. This header holds the cross-translation-unit calls the ROM itself
 * makes, so the compiler checks them.
 */
#ifndef TOS102US_XBIOS_H
#define TOS102US_XBIOS_H

#include <stdint.h>

/* $fc1510 — `Protobt` ($fc1636) calls it for a serial number that will not fit in three bytes. */
uint32_t xbios_random(uint8_t *image);

/* $fc2ea4 — `Ongibit` ($fc2edc) and `Offgibit` ($fc2f02) each call it twice, entering two
 * instructions in at $fc2eac with the two arguments already in D0/D1. */
uint8_t xbios_giaccess(uint16_t data, uint16_t reg_and_flag);

/* $fc2edc / $fc2f02 — port A's two read-modify-writes. `Bconout(PRT:)` ($fc2090) pulses the
 * Centronics strobe through their BODIES ($fc2ee2 / $fc2f08), which is the same routine entered
 * below its argument fetch with the mask already in D2; `entry_d0` is what both give back. */
uint32_t xbios_ongibit(uint32_t entry_d0, uint16_t bits);
uint32_t xbios_offgibit(uint32_t entry_d0, uint16_t bits);

/* $fc2f28 — `Initmous`. The VDI's mouse_init ($fca86a) and mouse_off ($fca882) take it through the
 * machine's own `trap #14` on target (the helpers at the end); off target they call it directly
 * (`src/vdi/mouse.c`). */
uint32_t xbios_initmous(uint8_t *image, uint16_t mode, uint32_t param, uint32_t vector);

/* $fc0aac / $fc0ab8 / $fc0b06 — `Getrez`, `Setscreen` and `Setpalette`, which the VDI's setres ($fca6d4)
 * takes through its own `trap #14` on target and calls directly off it (`src/vdi/screen.c`). */
uint8_t xbios_getrez(void);
uint32_t xbios_setscreen(uint8_t *image, uint32_t entry_d0, uint32_t logical, uint32_t physical,
                         uint16_t resolution);
uint32_t xbios_setpalette(uint8_t *image, uint32_t entry_d0, uint32_t palette);

/* $fc0d50 — `Scrdmp`, whose body is the VBL's screen dump (`src/bios/vbl.c`): the VDI's v_hardcopy
 * (`src/vdi/escape.c`) takes it through `trap #14` on target and calls it directly off it. It writes no D0
 * of its own, and its one caller discards what the trap answers. */
void xbios_scrdmp(uint8_t *image);

#ifndef RECREATE_HOST_DIFFERENTIAL
/* ---- the machine's own `trap #14`, on target ---------------------------------------------------
 *
 * `include/bios/bcon.h`'s arrangement, for the other trap: off target a caller calls the core above
 * directly; on target it pushes the ROM's frame and takes the real trap. One helper per FRAME SHAPE —
 * the function number at `(sp)` and the arguments above it in the order the XBIOS reads them — each
 * with the caller's own drop after. `trap #14` enters the dispatcher `trap #13` does (`src/bios/trap.S`),
 * so the register contract is `BIOS_TRAP_CLOBBERS`, and the pushes take `d` operands for `bcon.h`'s
 * reason.
 *
 * A SHAPE WITH TWO OR MORE ARGUMENTS PINS THEM IN THE REGISTERS THE TRAP TAKES ANYWAY — the first pushed in
 * D0, the next in D1, then D2, each at the width it is pushed — as `+d` operands, and leaves those out of
 * its clobbers. Those shapes answer nothing: the three calls they carry (`Settime`, `Setscreen`,
 * `Initmous`) are void, and a D0 bound as an argument has no width left to answer a longword in. A plain
 * `d` input cannot sit in a clobbered register, so the second argument would take a callee-saved one (D3)
 * and every caller would save and restore it round the whole function (measured: +32 cycles on
 * `Tsettime`, whose rejecting arms never trap).
 *
 * THE FUNCTION NUMBER IS PUSHED AS THE ROM PUSHES IT: `clr.w -(sp)` for Initmous' 0, `move.w #n,-(sp)`
 * for every other. */
#include "bios/bcon.h"

#define XBIOS_TRAP_CLOBBERS BIOS_TRAP_CLOBBERS
#define XBIOS_TRAP_ADDRESS_CLOBBERS "a0", "a1", "a2", "memory", "cc"   /* ...less D1/D2, when they are operands */
/* What each shape's caller drops after the trap: the function word and the arguments it pushed. */
#define XBIOS_PLAIN_FRAME_BYTES          (sizeof(uint16_t))
#define XBIOS_LONG_FRAME_BYTES           (sizeof(uint16_t) + sizeof(uint32_t))
#define XBIOS_WORD_WORD_FRAME_BYTES      (3 * sizeof(uint16_t))
#define XBIOS_WORD_TWO_LONGS_FRAME_BYTES (2 * sizeof(uint16_t) + 2 * sizeof(uint32_t))   /* either order */
#define XBIOS_PUSH_FUNCTION(operand) \
    ".if " operand " == 0\n\tclr.w -(%%sp)\n\t.else\n\tmove.w #" operand ",-(%%sp)\n\t.endif\n\t"

/* fn — `Getrez` ($04): one word. */
static inline uint32_t xbios_trap_plain(uint16_t fn)
{
    register uint32_t result __asm__("d0");

    __asm__ volatile (XBIOS_PUSH_FUNCTION("%c1")
                      "trap #14\n\t"
                      "addq.l #%c2,%%sp"
                      : "=d"(result)
                      : "i"(fn), "i"(XBIOS_PLAIN_FRAME_BYTES)
                      : XBIOS_TRAP_CLOBBERS);
    return result;
}

/* fn, long — `Setpalette` ($06): a word and a longword. */
static inline uint32_t xbios_trap_long(uint16_t fn, uint32_t value)
{
    register uint32_t result __asm__("d0");

    __asm__ volatile ("move.l %1,-(%%sp)\n\t"
                      XBIOS_PUSH_FUNCTION("%c2")
                      "trap #14\n\t"
                      "addq.l #%c3,%%sp"
                      : "=d"(result)
                      : "d"(value), "i"(fn), "i"(XBIOS_LONG_FRAME_BYTES)
                      : XBIOS_TRAP_CLOBBERS);
    return result;
}

/* fn, word, word — `Settime` ($16), the date over the time: three words. */
static inline void xbios_trap_word_word(uint16_t fn, uint16_t first, uint16_t second)
{
    register uint16_t pushed_second __asm__("d0") = second;
    register uint16_t pushed_first __asm__("d1") = first;

    __asm__ volatile ("move.w %0,-(%%sp)\n\t"
                      "move.w %1,-(%%sp)\n\t"
                      XBIOS_PUSH_FUNCTION("%c2")
                      "trap #14\n\t"
                      "addq.l #%c3,%%sp"
                      : "+d"(pushed_second), "+d"(pushed_first)
                      : "i"(fn), "i"(XBIOS_WORD_WORD_FRAME_BYTES)
                      : "d2", XBIOS_TRAP_ADDRESS_CLOBBERS);
}

/* fn, long, long, word — `Setscreen` ($05), dropped by `lea 12(sp),sp`. */
static inline void xbios_trap_long_long_word(uint16_t fn, uint32_t first, uint32_t second, uint16_t third)
{
    register uint16_t pushed_third __asm__("d0") = third;
    register uint32_t pushed_second __asm__("d1") = second;
    register uint32_t pushed_first __asm__("d2") = first;

    __asm__ volatile ("move.w %0,-(%%sp)\n\t"
                      "move.l %1,-(%%sp)\n\t"
                      "move.l %2,-(%%sp)\n\t"
                      XBIOS_PUSH_FUNCTION("%c3")
                      "trap #14\n\t"
                      "lea %c4(%%sp),%%sp"
                      : "+d"(pushed_third), "+d"(pushed_second), "+d"(pushed_first)
                      : "i"(fn), "i"(XBIOS_WORD_TWO_LONGS_FRAME_BYTES)
                      : XBIOS_TRAP_ADDRESS_CLOBBERS);
}

/* fn, word, long, long — `Initmous` ($00), dropped by `lea 12(sp),sp`. */
static inline void xbios_trap_word_long_long(uint16_t fn, uint16_t first, uint32_t second, uint32_t third)
{
    register uint32_t pushed_third __asm__("d0") = third;
    register uint32_t pushed_second __asm__("d1") = second;
    register uint16_t pushed_first __asm__("d2") = first;

    __asm__ volatile ("move.l %0,-(%%sp)\n\t"
                      "move.l %1,-(%%sp)\n\t"
                      "move.w %2,-(%%sp)\n\t"
                      XBIOS_PUSH_FUNCTION("%c3")
                      "trap #14\n\t"
                      "lea %c4(%%sp),%%sp"
                      : "+d"(pushed_third), "+d"(pushed_second), "+d"(pushed_first)
                      : "i"(fn), "i"(XBIOS_WORD_TWO_LONGS_FRAME_BYTES)
                      : XBIOS_TRAP_ADDRESS_CLOBBERS);
}
#endif /* !RECREATE_HOST_DIFFERENTIAL */

#endif /* TOS102US_XBIOS_H */
