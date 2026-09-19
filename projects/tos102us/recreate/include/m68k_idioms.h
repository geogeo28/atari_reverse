/* m68k_idioms.h — the two 68000 shapes the BIOS/XBIOS leaves repeat, spelt once.
 *
 * Both are things a reconstruction gets WRONG by writing the obvious C, so each one spelt again in
 * another core is another place to get it wrong — and each has a case battery behind it here, which
 * is the other reason they belong in one place: the claim and the code should not drift apart.
 *
 * They live in this project rather than in the kit's `machine.h` because they are OS idioms rather
 * than machine ones: "a negative argument means report only" is a TOS calling convention, and the
 * word-sized table index is the shape TOS's own dispatchers happen to share. A second project that
 * finds it needs them is the moment to move them down into the kit.
 */
#ifndef TOS102US_M68K_IDIOMS_H
#define TOS102US_M68K_IDIOMS_H

#include <stdint.h>

#include "machine.h"

/* A TABLE INDEX COMPUTED INSIDE A WORD, AND THEN SIGN-EXTENDED INTO THE ADDRESS — which is not the
 * same function as `entry * entry_bytes` and diverges from it in two ways at once:
 *
 *   * the product WRAPS at $10000, so a BIOS device of $4000 (`lsl.w #2`) reaches entry 0 and a
 *     Setexc vector of $4000 is vector 0;
 *   * the wrapped product is then SIGNED, so an index whose bit 15 is set walks BACKWARDS from the
 *     table: XBIOS Iorec's device $2000 indexes $ffff8000 off a table in the ROM, and Protobt's
 *     disk type 1725 (`muls.w #19` = $8007) reads 19 bytes from $7ff9 BELOW its prototype table.
 *
 * `lsl.w #2,Dn` / `muls.w #19,Dn` is the product; `movea.w Dn,An` or a `0(An,Dn.w)` index is the
 * sign extension. Neither half is optional: a reconstruction that multiplied in 32 bits would index
 * past the image where the original wraps, and one that zero-extended would read the bytes ABOVE a
 * table where the original reads the bytes below it. `entry_bytes` is 1 for a table of bytes, which
 * is Protobt's — there the running cursor is the word and the extension is all that is left. */
static inline uint32_t word_index(uint32_t entry, uint32_t entry_bytes)
{
    return sign_ext16((uint16_t)(entry * entry_bytes));
}

/* "A NEGATIVE ARGUMENT MEANS REPORT ONLY" — TOS's way of spelling an optional argument, and it is
 * tested AT THE ROM's OWN WIDTH, which is the half a reconstruction drops. Kbshift and Kbrate test
 * a WORD (`tst.w 4(sp)` / `bmi`), so $0080 is a store — bit 7 of the byte they go on to store is not
 * the sign of the word they tested — while $ff80 is a read. Setexc and Keytbl test a LONG, so every
 * handler or table pointer with bit 31 set is a read, and $ffffffff is only the documented spelling
 * of a whole family.
 *
 * Nothing legitimate is refused by either: a state byte is a byte, and every address on a 68000 with
 * a 24-bit bus has bit 31 clear. */
#define SIGN_BIT16 0x8000u
#define SIGN_BIT32 0x80000000u

static inline int keeps_current_value_word(uint16_t argument)
{
    return (argument & SIGN_BIT16) != 0;
}

static inline int keeps_current_value_long(uint32_t argument)
{
    return (argument & SIGN_BIT32) != 0;
}

/* THE N FLAG OF A WORD DIFFERENCE — what `cmp.w Dm,Dn` followed by `bpl`/`bmi` actually tests, and
 * NOT the signed compare `Dn < Dm` a reconstruction reaches for. `bpl` reads bit 15 of the
 * difference alone, so the two answers part company exactly where the subtraction OVERFLOWS a word:
 * the console's column clamp compares a maximum of 39 against a column of $8000 and the ROM's
 * `cmp.w d0,d2 / bpl` sees $8027 — negative, so it CLAMPS — where `39 < -32768` is false and a
 * signed compare leaves the column alone.
 *
 * `blt`/`bge` are the pair that DO make a signed compare, because they read V alongside N; a routine
 * branching on one of those is not this idiom. `$fc49c8` and `$fc49d2` (`cell_address`'s two clamps)
 * are `bpl` and are this; `$fc4746` and `$fc475e` (`advance_cursor`) are `blt` and are a real `<`.
 * `test_bios_vt52.py` drives both halves of the clamp at the overflow window. */
static inline int word_difference_is_negative(uint16_t left, uint16_t right)
{
    return (int16_t)(uint16_t)(left - right) < 0;
}

#endif /* TOS102US_M68K_IDIOMS_H */
