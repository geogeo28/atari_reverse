/* strings.c — the utility layer's MEMORY and STRING helpers (`aes/strings.h`). Hand 68000 in the ROM, ported to C
 * over its own ORDER and its own WIDTHS: counts are the words (or, twice, the BYTE) the ROM counts in, every loop
 * runs the passes its `dbf` / `subq; bne` / `subq; bpl` runs — a zero count included — and every byte is read and
 * stored one at a time, in the ROM's order, so a copy over itself leaves what the ROM leaves.
 *
 * WHAT SHIPS IS `optimize.S`: every core here but lmul measures over Tier 3's 1.10 bar against the ROM's tight loops
 * on its callers' shapes, so by the user's rule the target carries the ROM's own instructions (`include/transcribed.h`)
 * and this C is what Tier 1's host differential proves; lmul's C is under the bar, and ships as `.S` only because the
 * transcribed merge_str calls it. Each core is `TRANSCRIBED_CORE`, and none calls another — a C caller of a transcribed core is
 * priced through glue.
 *
 * A pointer argument is a caller's longword: each byte it reaches is put on the 24-bit bus (`bus_dereference`), and a
 * pointer the routine ANSWERS is the whole register, top byte and all. `CURSOR_BARRIER` on a loop's cursor keeps GCC
 * from recognising a copy or fill as `memcpy`/`memset`, which the freestanding 68000 build does not have.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "transcribed.h"
#include "aes/aes.h"
#include "aes/strings.h"

/* `subq.w #1,dN; bne` over a word count: 0 runs the body 65536 times. */
static inline int word_count_left(uint16_t *count)
{
    *count = (uint16_t)(*count - 1);
    return *count != 0;
}

/* `move.b (a0)+,(a1)+; bne` — the NUL-ended copy strcpy and strcat end in: the destination past the NUL. */
static inline uint32_t copy_string(uint8_t *image, uint32_t source, uint32_t destination)
{
    uint8_t byte;

    do {
        byte = bus_byte(image, source++);
        set_bus_byte(image, destination++, byte);
        CURSOR_BARRIER(destination);
    } while (byte != STRING_NUL);
    return destination;
}

/* A NUL-ended string's length, COUNTED IN A WORD (65536 bytes are 0): lstrlen's and strlen's answer alike. */
static inline int16_t string_length(const uint8_t *image, uint32_t string)
{
    uint16_t length = 0;

    while (bus_byte(image, string++) != STRING_NUL)
        length++;
    return (int16_t)length;
}

/* ================================================================================================================
 * Arithmetic, the VDI contrl[] pointer slots, and the Alcyon runtime's long multiply and divide.
 * ============================================================================================================= */

/* $fecb6e — `multiplicand * multiplier / divisor`, rounded half away from zero, as one `muls.w` of the multiplicand by
 * TWICE the multiplier (a WORD `add.w d0,d0`, which wraps), one `divs.w`, then the quotient word moved one step
 * toward the sign `bmi` read and halved by `asr.w`.
 *
 * `bmi` reads the N the divide left: the QUOTIENT word's sign — or, when the quotient overflows a word and `divs.w`
 * leaves the register (the product) unchanged, the N the `muls.w` before it set, the PRODUCT's sign. THAT ARM IS
 * ORACLE-DEFINED: the 68000's manual calls N undefined there, Musashi's divide leaves it alone (so this C does), and
 * Hatari's 68000 sets it — a positive product then rounds the other way (mul_div(1000, 1000, 1): -15808 here, -15809
 * on the machine). The shipped `.S` is the ROM's own `divs.w; bmi`, so the target does what the machine does. A zero
 * divisor takes vector 5 (`m68k_divs_w_v`). */
TRANSCRIBED_CORE
int16_t aes_mul_div(int16_t multiplicand, int16_t multiplier, int16_t divisor)
{
    uint16_t doubled = (uint16_t)((uint16_t)multiplier + (uint16_t)multiplier);
    int32_t product = m68k_muls_w(doubled, (uint16_t)multiplicand);
    int overflowed;
    uint32_t divided = m68k_divs_w_v((uint32_t)product, (uint16_t)divisor, &overflowed);
    int negative = overflowed ? product < 0 : quotient_word(divided) < 0;
    uint16_t stepped = (uint16_t)((uint16_t)divided + (negative ? -1 : 1));

    return (int16_t)((int16_t)stepped >> 1);
}

/* $fecbc6 — contrl[7..8] := `pointer`, the address a VDI call in contrl carries. */
TRANSCRIBED_CORE
void aes_set_contrl_ptr(uint8_t *image, uint32_t pointer)
{
    wr32(image + AES_GSX_CONTRL_PTR, pointer);
}

/* $fecbda — contrl[9..10], the address a VDI call answered, into the caller's longword. */
TRANSCRIBED_CORE
void aes_get_contrl_ptr2(uint8_t *image, uint32_t answer)
{
    set_bus_long(image, answer, be32(image + AES_GSX_CONTRL_PTR2));
}

/* $fece42 / $fece4e — the smaller / larger of two signed words (a tie answers the second either way). */
TRANSCRIBED_CORE
int16_t aes_min(int16_t left, int16_t right)
{
    return left < right ? left : right;
}

TRANSCRIBED_CORE
int16_t aes_max(int16_t left, int16_t right)
{
    return left > right ? left : right;
}

/* $fece74 — the argument's LOW BYTE, sign-extended (`ext.w`), moved to upper case when it is a-z: a byte from $80 up
 * answers negative, a high byte of the argument is ignored. */
TRANSCRIBED_CORE
int16_t aes_toupper(int16_t character)
{
    int16_t byte = (int8_t)(uint8_t)character;

    if (byte >= TOUPPER_FIRST && byte <= TOUPPER_LAST)
        return (int16_t)(byte + TOUPPER_DISTANCE);
    return byte;
}

/* $fe3db4 — the Alcyon runtime's signed long multiply: the product's low longword. The ROM multiplies the two
 * MAGNITUDES by three `mulu.w` and negates for an odd count of negative factors — the same longword as a wrapping
 * multiply, $80000000's own negation included. It negates the factors IN ITS CALLER'S FRAME (`neg.l 8(a6)`), which
 * a C caller never reads back: the frame is the caller's scratch. */
TRANSCRIBED_CORE
int32_t aes_lmul(int32_t multiplicand, int32_t multiplier)
{
    return (int32_t)((uint32_t)multiplicand * (uint32_t)multiplier);
}

/* The ldiv algorithm, over the MAGNITUDES (each `neg.l`'d when negative, so $80000000 stays itself and NEGATIVE):
 *   * a divisor greater than the dividend as SIGNED longs: quotient 0, the remainder the dividend's magnitude;
 *   * an equal one: 1 and 0;
 *   * a dividend below 65536: one `divu.w` by the divisor's LOW WORD (0 there takes vector 5);
 *   * else a restoring divide, bit by bit, UNSIGNED;
 * then quotient and remainder negated only when EXACTLY ONE operand was negative — so -7 / -2 leaves a remainder of
 * +1 where C's is -1. The remainder is stored at AES_LDIV_REMAINDER; a zero divisor stores $80000000 there first and
 * takes vector 5 (`divs.w #0`), which the host refuses by name. */
static inline int32_t alcyon_ldiv(uint8_t *image, int32_t dividend, int32_t divisor)
{
    uint32_t magnitude = (uint32_t)dividend, by = (uint32_t)divisor, quotient, remainder;
    int negations = 0;

    if (divisor == 0) {
        wr32(image + AES_LDIV_REMAINDER, LDIV_BY_ZERO_REMAINDER);
        m68k_divs_w(LDIV_BY_ZERO_REMAINDER, 0);
    }
    if (divisor < 0) {
        by = 0u - by;
        negations++;
    }
    if (dividend < 0) {
        magnitude = 0u - magnitude;
        negations++;
    }
    if ((int32_t)by > (int32_t)magnitude) {
        quotient = 0;
        remainder = magnitude;
    } else if (by == magnitude) {
        quotient = 1;
        remainder = 0;
    } else if ((int32_t)magnitude < LDIV_ONE_DIVIDE_BELOW) {
        uint32_t divided = m68k_divu_w(magnitude, (uint16_t)by);

        quotient = (uint16_t)divided;
        remainder = divided >> M68K_WORD_BITS;
    } else {
        quotient = magnitude / by;
        remainder = magnitude % by;
    }
    if (negations == 1) {
        remainder = 0u - remainder;
        quotient = 0u - quotient;
    }
    wr32(image + AES_LDIV_REMAINDER, remainder);
    return (int32_t)quotient;
}

/* $fe3e08 — the Alcyon runtime's signed long divide: the quotient, the remainder left at AES_LDIV_REMAINDER. */
TRANSCRIBED_CORE
int32_t aes_ldiv(uint8_t *image, int32_t dividend, int32_t divisor)
{
    return alcyon_ldiv(image, dividend, divisor);
}

/* ================================================================================================================
 * Copies and fills.
 * ============================================================================================================= */

/* $fecbe6 — `source` into `destination`, its NUL included. The answer is the length COUNTED IN A BYTE (`addq.b`
 * per byte moved, NUL included, then `subq.w #1`): a string of 255 bytes answers -1, of 256 answers 0. */
TRANSCRIBED_CORE
int16_t aes_lstcpy(uint8_t *image, uint32_t destination, uint32_t source)
{
    uint8_t moved = 0, byte;

    do {
        moved++;
        byte = bus_byte(image, source++);
        set_bus_byte(image, destination++, byte);
        CURSOR_BARRIER(destination);
    } while (byte != STRING_NUL);
    return (int16_t)(uint16_t)(moved - 1);
}

/* $fecbfa — a string's bytes widened to words (the high byte 0) into `destination`, the NUL not stored; the answer
 * the words stored, COUNTED IN A BYTE (`addq.b`): 256 words answer 0. */
TRANSCRIBED_CORE
int16_t aes_xstrpix(uint8_t *image, uint32_t destination, uint32_t source)
{
    uint8_t stored = 0, byte;

    while ((byte = bus_byte(image, source++)) != STRING_NUL) {
        set_bus_word(image, destination, byte);
        destination += M68K_WORD_BYTES;
        CURSOR_BARRIER(destination);
        stored++;
    }
    return stored;
}

/* $fecc12 — `words` words of `value`; a count of 0 stores none. No ROM code calls it. */
TRANSCRIBED_CORE
void aes_wset(uint8_t *image, uint32_t destination, int16_t words, int16_t value)
{
    uint16_t count = (uint16_t)words;

    if (count == 0)
        return;
    do {
        set_bus_word(image, destination, (uint16_t)value);
        destination += M68K_WORD_BYTES;
        CURSOR_BARRIER(destination);
    } while (word_count_left(&count));
}

/* $fecc28 — `bytes` bytes widened to words, NULs and all; a count of 0 is 65536 (no guard). No ROM code calls it. */
TRANSCRIBED_CORE
void aes_xstrpix_n(uint8_t *image, uint32_t destination, uint32_t source, int16_t bytes)
{
    uint16_t count = (uint16_t)bytes;

    do {
        set_bus_word(image, destination, bus_byte(image, source++));
        destination += M68K_WORD_BYTES;
        CURSOR_BARRIER(destination);
    } while (word_count_left(&count));
}

/* $fecc40 — `words` words from `source`, in ascending order; a count of 0 moves none. */
TRANSCRIBED_CORE
void aes_wcopy(uint8_t *image, uint32_t destination, uint32_t source, int16_t words)
{
    uint16_t count = (uint16_t)words;

    if (count == 0)
        return;
    do {
        set_bus_word(image, destination, bus_word(image, source));
        source += M68K_WORD_BYTES;
        destination += M68K_WORD_BYTES;
        CURSOR_BARRIER(destination);
    } while (word_count_left(&count));
}

/* $fecc56 — `words` words of `value`, and the ROM's own slip kept: its guard is the `beq` after the LAST of its two
 * loads, the value's — so a value of 0 stores nothing at all, and a count of 0 (with a value) stores 65536 words.
 * No ROM code calls it. */
TRANSCRIBED_CORE
void aes_wfill(uint8_t *image, uint32_t destination, int16_t words, int16_t value)
{
    uint16_t count = (uint16_t)words;

    if (value == 0)
        return;
    do {
        set_bus_word(image, destination, (uint16_t)value);
        destination += M68K_WORD_BYTES;
        CURSOR_BARRIER(destination);
    } while (word_count_left(&count));
}

/* $fecc6c — a string's length as a word (65536 wraps to 0). The ROM counts each byte before it tests it and takes
 * the one it counted for the NUL back after (`addq; cmpi.b; bne; subq`), which leaves the same word as strlen's. */
TRANSCRIBED_CORE
int16_t aes_lstrlen(uint8_t *image, uint32_t string)
{
    return string_length(image, string);
}

/* $fecc7e — `bytes` bytes from `source` to `destination`, overlap-safe: FORWARD unless the source lies below the
 * destination — a SIGNED compare of the two whole longwords (`cmpa.l; blt`), top bytes included — else BACKWARD
 * from both ends (`adda.l` of the count, zero-extended). A count of 0 moves nothing.
 *
 * The backward loop counts in a SIGNED word (`subq.w #1` first, then `move.b; subq.w; bpl`): from 32770 bytes up
 * the first count is already negative, so it moves ONE byte — the last — and stops. */
TRANSCRIBED_CORE
void aes_lbcopy(uint8_t *image, uint32_t destination, uint32_t source, int16_t bytes)
{
    uint16_t count = (uint16_t)bytes, left;

    if (count == 0)
        return;
    if ((int32_t)source >= (int32_t)destination) {
        do {
            set_bus_byte(image, destination++, bus_byte(image, source++));
            CURSOR_BARRIER(destination);
        } while (word_count_left(&count));
        return;
    }
    source += count;
    destination += count;
    left = (uint16_t)(count - 1);
    do {
        set_bus_byte(image, --destination, bus_byte(image, --source));
        CURSOR_BARRIER(destination);
        left = (uint16_t)(left - 1);
    } while (!(left & SIGN_BIT16));
}

/* $fece2e — `bytes` bytes from `source`, forward, as a `dbf` counts: 0 moves none, and the count is UNSIGNED (a
 * word from $8000 up moves that many). */
TRANSCRIBED_CORE
void aes_movs(uint8_t *image, int16_t bytes, uint32_t source, uint32_t destination)
{
    uint16_t count = (uint16_t)bytes;

    while (count-- != 0) {
        set_bus_byte(image, destination++, bus_byte(image, source++));
        CURSOR_BARRIER(destination);
    }
}

/* $fece5e — `bytes` bytes of the value word's LOW byte, as a `dbf` counts. */
TRANSCRIBED_CORE
void aes_bfill(uint8_t *image, int16_t bytes, int16_t value, uint32_t destination)
{
    uint16_t count = (uint16_t)bytes;

    while (count-- != 0) {
        set_bus_byte(image, destination++, (uint8_t)value);
        CURSOR_BARRIER(destination);
    }
}

/* ================================================================================================================
 * Strings.
 * ============================================================================================================= */

/* $fece8c — a string's length as a word; each byte tested before it is counted. */
TRANSCRIBED_CORE
int16_t aes_strlen(uint8_t *image, uint32_t string)
{
    return string_length(image, string);
}

/* $fece9c — 1 when the two strings are equal to their NULs, else 0 (the shared tails). */
TRANSCRIBED_CORE
int16_t aes_streq(uint8_t *image, uint32_t left, uint32_t right)
{
    while (bus_byte(image, left) != STRING_NUL)
        if (bus_byte(image, left++) != bus_byte(image, right++))
            return 0;
    return bus_byte(image, right) == STRING_NUL;
}

/* $feceb8 — `source` into `destination`, its NUL included; the answer the destination PAST that NUL. */
TRANSCRIBED_CORE
uint32_t aes_strcpy(uint8_t *image, uint32_t source, uint32_t destination)
{
    return copy_string(image, source, destination);
}

/* $fecec4 — `source` into `destination` up to (not including) the first `stop` byte or the NUL — `stop` tested
 * first, so a NUL stop is the NUL — with NOTHING terminated; the answer where the destination got to. */
TRANSCRIBED_CORE
uint32_t aes_strscn(uint8_t *image, uint32_t source, uint32_t destination, int16_t stop)
{
    uint8_t byte;

    while ((byte = bus_byte(image, source)) != (uint8_t)stop && byte != STRING_NUL) {
        set_bus_byte(image, destination++, bus_byte(image, source++));
        CURSOR_BARRIER(destination);
    }
    return destination;
}

/* $feceda — `source` after `destination`'s NUL (over it), its own NUL included; the answer past that NUL. */
TRANSCRIBED_CORE
uint32_t aes_strcat(uint8_t *image, uint32_t source, uint32_t destination)
{
    while (bus_byte(image, destination++) != STRING_NUL)
        continue;
    return copy_string(image, source, destination - 1);
}

/* $feceee — where `character` (the word's LOW byte) first occurs in `string`, or its NUL. Called by the desk
 * alone. */
TRANSCRIBED_CORE
uint32_t aes_scasb(uint8_t *image, uint32_t string, int16_t character)
{
    uint8_t byte;

    while ((byte = bus_byte(image, string)) != STRING_NUL && byte != (uint8_t)character)
        string++;
    return string;
}

/* $fecf02 — 0 when the two strings are equal to their NULs, else the difference of the first two bytes that differ,
 * each SIGN-extended (`ext.w`): "a" against "b" is -1, "\x80" against "a" is -225. */
TRANSCRIBED_CORE
int16_t aes_strchk(uint8_t *image, uint32_t left, uint32_t right)
{
    for (;;) {
        uint8_t byte = bus_byte(image, left);

        if (byte != bus_byte(image, right++))
            return (int16_t)((int8_t)bus_byte(image, left) - (int8_t)bus_byte(image, right - 1));
        if (bus_byte(image, left++) == STRING_NUL)
            return 0;
    }
}

/* $fecf24 — a file name as the 8.3 form a directory entry holds: the name's first eight bytes, space-padded to 8
 * when a dot ends it early, then the extension with no dot. Three ROM shapes kept:
 *   * a name with NO dot is copied as it is, unpadded ("ABC" stays "ABC");
 *   * after eight bytes the ninth is SKIPPED whatever it is (taken for the dot): "ABCDEFGHIJ" -> "ABCDEFGHJ";
 *   * the extension is copied to its NUL, however long. */
TRANSCRIBED_CORE
void aes_fmt_str(uint8_t *image, uint32_t source, uint32_t destination)
{
    uint16_t left = FMT_NAME_BYTES;
    uint8_t byte;

    for (;;) {
        byte = bus_byte(image, source);
        if (byte == STRING_NUL)
            goto terminate;
        if (byte == STRING_DOT)
            break;
        set_bus_byte(image, destination++, bus_byte(image, source++));
        if (--left == 0)
            goto extension;
    }
    while (left-- != 0)
        set_bus_byte(image, destination++, STRING_SPACE);
extension:
    if (bus_byte(image, source++) == STRING_NUL)
        goto terminate;
    while (bus_byte(image, source) != STRING_NUL)
        set_bus_byte(image, destination++, bus_byte(image, source++));
terminate:
    set_bus_byte(image, destination, STRING_NUL);
}

/* $fecf58 — the 8.3 form back to a name: its first eight bytes with every space dropped (a NUL among them ends the
 * name with no dot), then a dot and the rest to its NUL — so an 8-byte form with nothing after it gains a bare dot. */
TRANSCRIBED_CORE
void aes_unfmt_str(uint8_t *image, uint32_t source, uint32_t destination)
{
    uint16_t left = FMT_NAME_BYTES;
    uint8_t byte;

    do {
        byte = bus_byte(image, source++);
        if (byte == STRING_NUL)
            goto terminate;
        if (byte != STRING_SPACE)
            set_bus_byte(image, destination++, byte);
    } while (--left != 0);
    set_bus_byte(image, destination++, STRING_DOT);
    while (bus_byte(image, source) != STRING_NUL)
        set_bus_byte(image, destination++, bus_byte(image, source++));
terminate:
    set_bus_byte(image, destination, STRING_NUL);
}

/* A number's decimal digits for merge_str, least significant first, each the low byte of `value - 10 * quotient +
 * '0'` through ldiv (so a negative %L's digits are the bytes BELOW '0', and $80000000, whose magnitude ldiv takes
 * for less than ten, is the one digit '0'); none for 0, which the caller writes as '0'. Answers the count. */
static uint16_t decimal_digits(uint8_t *image, uint32_t value, uint8_t *digits)
{
    uint16_t count = 0;

    while (value != 0) {
        int32_t quotient = alcyon_ldiv(image, (int32_t)value, DECIMAL_BASE);

        digits[count++] = (uint8_t)(value - (uint32_t)quotient * DECIMAL_BASE + DIGIT_ZERO);
        value = (uint32_t)quotient;
    }
    return count;
}

/* $fed070 — `template` into `destination` with each `%` code replaced: %L a longword parameter in decimal, %W the
 * first word of its slot in decimal, %S the string its slot points at (without its NUL), %% a percent; any other
 * code is dropped with its percent. Every %L, %W and %S takes the next 4-byte slot of `parameters` — %% and a dropped
 * code take none ($fed0c0 `bne` leaves before any `addq.w #4`) — the slot offset a word, sign-extended when it is
 * added. The destination is NUL-terminated.
 *
 * A `%` as the template's LAST byte takes the NUL for its code and reads ON PAST IT, as the ROM does. */
TRANSCRIBED_CORE
void aes_merge_str(uint8_t *image, uint32_t destination, uint32_t template, uint32_t parameters)
{
    uint16_t slot = 0;
    uint8_t digits[MERGE_DIGITS_BYTES];
    uint8_t code;
    uint32_t value, parameter;
    uint16_t count;

    while (bus_byte(image, template) != STRING_NUL) {
        if (bus_byte(image, template) != STRING_PERCENT) {
            set_bus_byte(image, destination++, bus_byte(image, template++));
            continue;
        }
        template++;
        code = bus_byte(image, template++);
        if (code == STRING_PERCENT) {
            set_bus_byte(image, destination++, code);
            continue;
        }
        parameter = parameters + (uint32_t)(int32_t)(int16_t)slot;
        if (code == MERGE_CODE_LONG) {
            value = bus_long(image, parameter);
        } else if (code == MERGE_CODE_WORD) {
            value = bus_word(image, parameter);
        } else if (code == MERGE_CODE_STRING) {
            uint32_t string = bus_long(image, parameter);

            slot = (uint16_t)(slot + MERGE_SLOT_BYTES);
            while (bus_byte(image, string) != STRING_NUL)
                set_bus_byte(image, destination++, bus_byte(image, string++));
            continue;
        } else {
            continue;
        }
        slot = (uint16_t)(slot + MERGE_SLOT_BYTES);
        count = decimal_digits(image, value, digits);
        if (count == 0)
            set_bus_byte(image, destination++, DIGIT_ZERO);
        while (count != 0)
            set_bus_byte(image, destination++, digits[--count]);
    }
    set_bus_byte(image, destination, STRING_NUL);
}

/* $fed12e — 1 when `name` matches `pattern`, else 0. `?` matches any one byte but a dot (and none at the dot, where
 * the pattern moves on alone); `*` matches bytes up to the next dot; any other byte must match exactly. When either
 * string runs out, the rest of the pattern must be only `*`, `?` and dots, and the name must be at its NUL. */
TRANSCRIBED_CORE
int16_t aes_wildcmp(uint8_t *image, uint32_t pattern, uint32_t name)
{
    uint8_t wanted;

    while ((wanted = bus_byte(image, pattern)) != STRING_NUL && bus_byte(image, name) != STRING_NUL) {
        if (wanted == STRING_WILDCARD_ONE) {
            pattern++;
            if (bus_byte(image, name) != STRING_DOT)
                name++;
        } else if (wanted == STRING_WILDCARD_ANY) {
            if (bus_byte(image, name) == STRING_DOT)
                pattern++;
            else
                name++;
        } else {
            if (wanted != bus_byte(image, name))
                return 0;
            pattern++;
            name++;
        }
    }
    while ((wanted = bus_byte(image, pattern)) == STRING_WILDCARD_ANY || wanted == STRING_WILDCARD_ONE
           || wanted == STRING_DOT)
        pattern++;
    return wanted == STRING_NUL && bus_byte(image, name) == STRING_NUL;
}
