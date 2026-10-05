/* m68k_idioms.h — the 68000 shapes more than one core repeats, spelt once.
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

#include "addrs.h"
#include "machine.h"
#include "os.h"
#include "recreate.h"

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

/* The address of entry `index` of the table at `table`, the index SIGN-EXTENDED first and scaled in the
 * address register (`movea.w` / `ext.l`, then `adda.l An,An` or `asl.l`): a negative index reads below the
 * table, and a doubled one parts from the word-wrapped `word_index` above from 16,384 on. Summed as an
 * ADDRESS before it meets the image, so below the table is not 4 GB above it. The product is SIGNED (no index a
 * word holds overflows it), which leaves GCC free to extend an index it knows is non-negative with `ext.l`
 * rather than `andi.l #$ffff` — a fill's pen lookup costs 12 cycles more spelt unsigned. The AES's object
 * layer indexes a tree the same way (`muls.w #24` — a signed product — then `adda.l`, `aes/objects.h`). */
static inline uint32_t table_entry(uint32_t table, int32_t index, uint32_t entry_bytes)
{
    return table + (uint32_t)(index * (int32_t)entry_bytes);
}

/* A SIGNED WORD added to an address, as `movea.w` — or `ext.l` — then `adda.l` add it: a negative one reaches below
 * the address, never 64 KB above it. */
static inline uint32_t offset_by(uint32_t address, int16_t index)
{
    return address + (uint32_t)(int32_t)index;
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

/* A SHIFT BY A REGISTER COUNT — `asl.w Dn,Dm`, `asr.l Dn,Dm` — takes the count MODULO 64, and a
 * count past the operand's width shifts every bit out: a word shifted 16..63 places left is 0, and a
 * long shifted 32..63 places right ARITHMETICALLY is its sign. C leaves both of those undefined, and
 * the file system reaches them: `$fc53c0` makes a log2 of -1 ($ffff, a count of 63) out of a zero
 * geometry field, and every shift by a DMD log2 then takes it; `$fc67de` shifts a drive's bit by the
 * drive number itself; and Line-A's concat (`$fca1b8`) shifts by a byte of its own code when a caller's
 * plane count runs past its table.
 *
 * ON TARGET THE INSTRUCTION IS THE DEFINITION, so it is spelt as the instruction: the 68000's own
 * shift already does all of the above, and a C spelling of it would cost a mask and a compare the
 * ROM never pays (measured: `$fc7e24` at 1.32x its ROM cycles with the portable form, against the
 * Tier 3 bar of 1.10). Off target the portable form computes the same answer, defined. */
#define M68K_SHIFT_COUNT_MASK 63
#define M68K_WORD_BITS        16
#define M68K_LONG_BITS        32

/* Two words as the one longword a `move.l` moves them as: `high` the one at the lower address. Taken signed, as the
 * coordinates most callers hand it are (unsigned parameters cost a register swap in gsx_blt's m68k code). */
static inline uint32_t words_long(int16_t high, int16_t low)
{
    return (uint32_t)(uint16_t)high << M68K_WORD_BITS | (uint16_t)low;
}

/* An (x, y) or (w, h) pair as the 68000 holds it, ONE longword with x high: a pair moved by `add.l` / `subi.l` lets a
 * carry or borrow out of the low word (y, h) into the high one (x, w) — the AES's outline corner at y < 3 moves left a
 * pixel. Every such site goes through these two, and the words come back out through the two after. */
static inline uint32_t packed_add(uint32_t pair, uint32_t addend)
{
    return pair + addend;
}

static inline uint32_t packed_sub(uint32_t pair, uint32_t subtrahend)
{
    return pair - subtrahend;
}

static inline int16_t pair_high(uint32_t pair)
{
    return (int16_t)(pair >> M68K_WORD_BITS);
}

static inline int16_t pair_low(uint32_t pair)
{
    return (int16_t)pair;
}

static inline uint16_t asl_word_by(uint16_t value, uint16_t count)
{
#ifdef __m68k__
    __asm__("asl.w %1,%0" : "+d"(value) : "d"(count) : "cc");
    return value;
#else
    unsigned bits = count & M68K_SHIFT_COUNT_MASK;

    return bits < M68K_WORD_BITS ? (uint16_t)(value << bits) : 0;
#endif
}

static inline int32_t asr_long_by(int32_t value, uint16_t count)
{
#ifdef __m68k__
    __asm__("asr.l %1,%0" : "+d"(value) : "d"(count) : "cc");
    return value;
#else
    unsigned bits = count & M68K_SHIFT_COUNT_MASK;

    return value >> (bits < M68K_LONG_BITS ? bits : M68K_LONG_BITS - 1);
#endif
}

/* ---- the 68000's two 16-bit DIVIDES, as the instruction defines them ----------------------------
 * `divs.w` / `divu.w` divide a LONGWORD by a word and leave `remainder << 16 | quotient` in the whole
 * register — and when the quotient does not fit a word they set V and leave the register UNCHANGED,
 * which two VDI helpers reach (`clc_dda` over equal sizes, `smul_div` over a product too large for
 * its divisor). A zero divisor takes the zero-divide exception, vector 5.
 *
 * ON TARGET THE INSTRUCTION IS THE DEFINITION — the rule for a shift above: all of the above,
 * vector 5 included, is what the one instruction does, and it is what the ROM pays. OFF TARGET the
 * portable form computes the same register, and REFUSES a zero divisor BY NAME rather than dividing by
 * it: there is no vector 5 to take, and a host `SIGFPE` would name nothing. */
static inline uint32_t m68k_divs_w(uint32_t dividend, uint16_t divisor)
{
#ifdef __m68k__
    __asm__("divs.w %1,%0" : "+d"(dividend) : "d"(divisor) : "cc");
    return dividend;
#else
    int64_t quotient, remainder;

    if (divisor == 0)
        recreate_not_reconstructed("divs.w by zero: the 68000 takes vector 5 (zero divide)");
    quotient = (int64_t)(int32_t)dividend / (int16_t)divisor;
    remainder = (int64_t)(int32_t)dividend % (int16_t)divisor;
    if (quotient < INT16_MIN || quotient > INT16_MAX)
        return dividend;
    return ((uint32_t)(uint16_t)remainder << 16) | (uint16_t)quotient;
#endif
}

static inline uint32_t m68k_divu_w(uint32_t dividend, uint16_t divisor)
{
#ifdef __m68k__
    __asm__("divu.w %1,%0" : "+d"(dividend) : "d"(divisor) : "cc");
    return dividend;
#else
    uint32_t quotient;

    if (divisor == 0)
        recreate_not_reconstructed("divu.w by zero: the 68000 takes vector 5 (zero divide)");
    quotient = dividend / divisor;
    if (quotient > UINT16_MAX)
        return dividend;
    return ((dividend % divisor) << 16) | quotient;
#endif
}

/* ...and the same divide with its V FLAG answered in `overflowed`: the quotient did not fit a word, so the
 * register was left UNCHANGED — and N with it, as the instruction before the divide set it (Musashi; the
 * 68000's manual leaves N undefined there). One divide on target: `divs.w` then `svs`. */
static inline uint32_t m68k_divs_w_v(uint32_t dividend, uint16_t divisor, int *overflowed)
{
#ifdef __m68k__
    uint8_t set;

    __asm__("divs.w %2,%0\n\tsvs %1" : "+d"(dividend), "=d"(set) : "d"(divisor) : "cc");
    *overflowed = set != 0;
    return dividend;
#else
    uint32_t divided = m68k_divs_w(dividend, divisor);
    int64_t quotient = (int64_t)(int32_t)dividend / (int16_t)divisor;

    *overflowed = quotient < INT16_MIN || quotient > INT16_MAX;
    return divided;
#endif
}

/* ...and the two halves of the register a divide leaves, as the signed words a caller reads. */
static inline int16_t quotient_word(uint32_t divided)
{
    return (int16_t)(uint16_t)divided;
}

static inline int16_t remainder_word(uint32_t divided)
{
    return (int16_t)(uint16_t)(divided >> M68K_WORD_BITS);
}

/* `muls.w`: both factors are the LOW WORDS, signed, and the product is the whole long — which a C `*` of
 * two `int16_t` promoted to `int` already is, spelt once so no core writes the unsigned product instead. */
static inline int32_t m68k_muls_w(uint16_t left, uint16_t right)
{
    return (int32_t)(int16_t)left * (int16_t)right;
}

/* `swap Dn`: the register's two words exchanged. */
static inline uint32_t m68k_swap(uint32_t value)
{
    return rotate_left32(value, M68K_WORD_BITS);
}

/* An address as the 68000 DRIVES it: a register holds 32 bits and the bus carries 24, so a sum that ran
 * past $ffffff wraps rather than leaving the image (`OS_BUS_ADDR_MASK`). */
static inline uint32_t bus_address(uint32_t address)
{
    return address & OS_BUS_ADDR_MASK;
}

/* ...and an address that is only DEREFERENCED — its value never stored, compared or carried on — reaches
 * the same byte masked or not ON TARGET. PRECONDITION: the target image base is 0 and the 68000 drives 24
 * address lines, so the bus drops the top byte itself and the mask there is COST ONLY; it is spelt for the
 * host's 16 MB image alone, and the builds compute the same function (`tools/recreate_kit/kit.mk`,
 * RECREATE_HOST_DIFFERENTIAL). A value that IS stored or compared keeps its top byte on both builds, and a
 * sum that must wrap before it is used goes through `bus_address` on both. The font layer reads headers
 * this way (`src/vdi/text.c`), reached through vector longwords whose high bytes are not zero; the VDI's
 * call accessors reach a program's arrays this way (`include/vdi/vdi.h`), and the console its screen
 * (`include/bios/vt52.h`) — each summing its offset FIRST, as `d16(An)` does, and masking the sum. */
static inline uint32_t bus_dereference(uint32_t address)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    return bus_address(address);
#else
    return address;
#endif
}

/* ---- a byte, word or longword READ OR STORED through a caller's pointer ------------------------------------------
 * `bus_dereference` above, spelt once for the accessors every AES core reaches its caller's memory through: the
 * offset summed FIRST (`d16(An)`), the sum put on the bus, then the access. ON TARGET each is the plain access.
 *
 * OFF TARGET a word or longword the 68000 could not make is REFUSED BY NAME rather than made: at an ODD address it
 * takes an address error (vector 3), which the oracle's Musashi — built without address errors — does not model; and
 * one whose bytes run past the top of the bus would reach past the host's 16 MB image, where the 68000 wraps the
 * second word to $000000. The bound is written so it cannot wrap: `at <= OS_BUS_ADDR_MASK - (bytes - 1)`.
 *
 * A STORE is refused by name too where any of its bytes lies AT OR ABOVE THE TOP OF RAM (ST_RAM_BYTES): the ROM, the
 * I/O page and the unmapped band between them. There the oracle drops the store (it is no RAM byte, `oracle/shim.c`'s
 * m68k_write_memory_8), an ST loses it or takes a bus error, and the host's flat image would keep it — a divergence,
 * not a value. An application's alert string with a fifth button reaches it (fm_strbrk's line buffer at $ff1100,
 * `src/aes/fmlib.c`). The screen ($f8000 on the 1 MB machine) lies below the bound.
 *
 * WHAT `ram_store` GUARDS, exactly: the set_bus_* family below; the VDI's call and workstation stores
 * (`include/vdi/vdi.h`: answer_intout, answer_ptsout, set_contrl_word, set_work_word, set_work_long,
 * set_current_work_word); the mouse's (`src/vdi/mouse.c`: poke16, the sprite's save-area, status and screen stores,
 * the VBL-queue slot); the font layer's swapped flag (`src/vdi/text.c`); rs_gaddr's answer slot
 * (`src/aes/resource.c`); eralert's frame (`src/aes/fmdo.c`) — each refused above RAM in `test/test_ram_store.py`
 * but the two no case can reach (eralert's frame is a host slot; the sprite's screen word lies below its status byte,
 * whose guard refuses first). NOT guarded: a store at an address the C names itself
 * (a Line-A or system variable, `set_ram_word`), a store through a pointer a loop walks (the VDI's ptsout cursors
 * in `src/vdi/text.c`, the transposes in `src/vdi/helpers.c`, vdi_dispatch's contrl in `src/vdi/entry.c`) — and the
 * BIOS and GEMDOS cores keep an older spelling of the same bound, an `assert(... <= ST_RAM_BYTES)`, not refused by
 * name. */
#define M68K_WORD_BYTES       2
#define M68K_LONG_BYTES       4
#define M68K_ODD_ADDRESS_BIT  1u

static inline uint32_t bus_span(uint32_t address, uint32_t bytes)
{
    uint32_t at = bus_dereference(address);

#ifdef RECREATE_HOST_DIFFERENTIAL
    if (at & M68K_ODD_ADDRESS_BIT)
        recreate_not_reconstructed("a word or longword at an odd address: the 68000's address error (vector 3)");
    if (at > OS_BUS_ADDR_MASK - (bytes - 1))
        recreate_not_reconstructed("an access running past the top of the 24-bit bus: the 68000 wraps it to $000000");
#else
    (void)bytes;
#endif
    return at;
}

static inline uint32_t ram_store(uint32_t at, uint32_t bytes)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    if (at > ST_RAM_BYTES - bytes)
        recreate_not_reconstructed("a store at or above the top of RAM (ST_RAM_BYTES): the oracle drops it, an ST loses it "
                                   "or takes a bus error");
#else
    (void)bytes;
#endif
    return at;
}

static inline uint8_t bus_byte(const uint8_t *image, uint32_t address)
{
    return image[bus_dereference(address)];
}

static inline void set_bus_byte(uint8_t *image, uint32_t address, uint8_t value)
{
    image[ram_store(bus_dereference(address), 1)] = value;
}

static inline uint16_t bus_word(const uint8_t *image, uint32_t address)
{
    return be16(image + bus_span(address, M68K_WORD_BYTES));
}

static inline void set_bus_word(uint8_t *image, uint32_t address, uint16_t value)
{
    wr16(image + ram_store(bus_span(address, M68K_WORD_BYTES), M68K_WORD_BYTES), value);
}

static inline uint32_t bus_long(const uint8_t *image, uint32_t address)
{
    return be32(image + bus_span(address, M68K_LONG_BYTES));
}

static inline void set_bus_long(uint8_t *image, uint32_t address, uint32_t value)
{
    wr32(image + ram_store(bus_span(address, M68K_LONG_BYTES), M68K_LONG_BYTES), value);
}

/* A SIGNED WORD OF A RECORD, read through the record's pointer on the 24-bit bus: a count, an index, an id, a
 * coordinate — what the ROM compares with `cmp.w` and extends with `ext.l` or `movea.w`. One accessor for every record
 * (a PD's, a QPB's, a rectangle's, a window list's), so that "signed" is said once. */
static inline int16_t signed_field(const uint8_t *image, uint32_t record, uint32_t field)
{
    return (int16_t)bus_word(image, record + field);
}

#endif /* TOS102US_M68K_IDIOMS_H */
