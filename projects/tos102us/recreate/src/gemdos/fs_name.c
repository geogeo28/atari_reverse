/* fs_name.c — the GEMDOS file system's 8.3 NAME layer: the three routines that touch no disk.
 *
 * Everything else in this group reaches a sector; these turn text into the eleven bytes a directory
 * entry holds, and compare two of them. They are the bottom of the directory search
 * (`Fsfirst`/`Fsnext`, `Fopen`, `Frename`) and the only part of it a case can prove with nothing
 * staged but two buffers.
 *
 * THE FCB NAME is eleven bytes: eight of stem and three of extension, each padded with SPACE, no
 * dot between them and no terminator. A `*` in the caller's text fills the REST of that field with
 * `?`, which is why the wildcard never reaches the comparison as a character of its own.
 *
 *   $fc50ca  toupper           — 'a'..'z' -> `& 0x5f`, everything else through unchanged
 *   $fc5d28  build_fcb_name    — "name.ext" -> those eleven bytes
 *   $fc5c9a  name_match        — one pattern against one directory entry, `?` and `$e5` included
 */
#include <stdint.h>

#include "gemdos_fs.h"
#include "machine.h"

/* The two characters the FCB form is built out of beyond `include/gemdos_fs.h`'s FCB_PAD, and the
 * three the parser stops a field at besides it (NAME_DOT and PATH_SEPARATOR are that header's too:
 * a path separator ends the name as surely as a NUL does). */
#define FCB_ANY           '?'     /* one position a pattern matches anything in */
#define NAME_WILDCARD     '*'     /* ...and what fills the rest of a field with those */

/* The whole FCB name, its two fields together. */
#define FCB_NAME_BYTES    DIRENT_NAME_BYTES

/* Lower case is upper case with this bit clear, which is how the ROM spells it: `and.w #$5f` rather
 * than a subtraction, applied only inside 'a'..'z' ($fc50d6/$fc50dc, a SIGNED byte compare pair). */
#define LOWER_CASE_BIT    0x20
/* The ROM's operand is `and.w #$5f` on a word that `ext.w` has just sign-extended from a byte in
 * 'a'..'z' — so its high byte is 0 and the two spellings are the same mask there. Written as the
 * BYTE mask because the value this applies to is a byte. */
#define UPPER_CASE_MASK   (0xff & ~LOWER_CASE_BIT)

/* $fc50ca — one character folded to upper case.
 *
 * The argument arrives as a WORD and the routine reads its low byte (`move.b 9(a6),d7`), so a
 * caller passing a wide value has only its bottom eight bits looked at; the result is then
 * sign-extended from that byte. Both compares are SIGNED byte compares, so a character with bit 7
 * set is negative and falls through unchanged — which is what leaves the ST's accented characters
 * alone.
 *
 * THE SIGNEDNESS OF THE COMPARES IS NOT OBSERVABLE, and that is worth saying rather than leaving
 * for someone to rediscover: 'a'..'z' is $61..$7a, so every byte an unsigned compare would let in
 * and a signed one would not ($80..$ff) fails the upper bound anyway. The two spellings are the
 * same function. What IS observable is the sign extension of the RESULT, and that has a case.
 */
uint32_t gemdos_fs_toupper(uint32_t entry_d0, uint16_t character)
{
    int8_t byte = (int8_t)character;
    uint16_t folded = (uint16_t)(int16_t)byte;

    if (byte >= 'a' && byte <= 'z')
        folded &= UPPER_CASE_MASK;
    /* `move.w`/`and.w` on D0: the caller's high half stands. */
    return set_low_word(entry_d0, folded);
}

/* $fc539a — log2 of a power of two: shift right until the word is zero, and subtract one from the
 * count. `asr.w` rather than `lsr.w`, which is the ROM's instruction and not a detail — a value
 * with bit 15 set shifts down to -1 and stays there, so the loop never ends. Nothing in TOS calls
 * it with one — the three call sites are $fc5484, $fc54ae and $fc54d8, which pass `m_clsiz`,
 * `m_recsiz` and `m_clsizb`, all of them BPB geometry — and the loop is transcribed as the ROM has
 * it rather than guarded. NOTHING PINS THAT, and it is said here rather than claimed as a surface:
 * a case reaching it with bit 15 set would hang the oracle rather than fail.
 *
 * log2(0) is -1: the loop makes no pass and the `subq.w #1` runs anyway.
 */
uint32_t gemdos_fs_log2(uint32_t entry_d0, uint16_t value)
{
    int16_t remaining = (int16_t)value;
    uint16_t shifts = 0;

    while (remaining != 0) {
        remaining = (int16_t)(remaining >> 1);
        shifts++;
    }
    return set_low_word(entry_d0, (uint16_t)(shifts - 1));
}

/* Does this character end an FCB field? The ROM's five tests, in its own order ($fc5d50..$fc5d6a
 * and, byte for byte, $fc5dc8..$fc5de2). A space ends a field as surely as a NUL does, which is why
 * "A B.TXT" does not become an eight-character stem. */
static int ends_a_field(uint8_t character)
{
    return character == '\0' || character == NAME_WILDCARD || character == PATH_SEPARATOR
        || character == NAME_DOT || character == FCB_PAD;
}

/* Copy up to `width` upper-cased bytes of `at` into the FCB, stopping at the first character that
 * ends a field. Returns how many were written; `at` and `fcb` are advanced past what was consumed.
 *
 * The ROM has this loop twice in straight-line code, once per field, differing in nothing but the
 * width — so it is one function here. What is NOT shared is what each field does afterwards: the
 * two tails really do differ, and they are written out at the call sites below.
 */
static uint16_t copy_field_text(uint8_t *image, uint32_t *at, uint32_t *fcb, uint16_t width)
{
    uint16_t written = 0;

    while (written < width && !ends_a_field(image[*at])) {
        image[(*fcb)++] = (uint8_t)gemdos_fs_toupper(0, image[(*at)++]);
        written++;
    }
    return written;
}

/* ...and the padding: `?` if the copy stopped on a `*`, space otherwise ($fc5d86, $fc5de4). */
static void pad_field(uint8_t *image, uint8_t stopped_on, uint32_t *fcb, uint16_t written,
                      uint16_t width)
{
    uint8_t pad = (stopped_on == NAME_WILDCARD) ? FCB_ANY : FCB_PAD;

    while (written < width) {
        image[(*fcb)++] = pad;
        written++;
    }
}

/* $fc5d28 — "name.ext" into the eleven bytes of an FCB name.
 *
 * TWO THINGS THE STEM DOES THAT THE EXTENSION DOES NOT, and both are why the fields are not one
 * loop called twice:
 *
 *   * when the stem FILLED all eight bytes the text may still hold more stem characters, and
 *     $fc5d74 throws them away up to the next `.`, `\` or NUL — a skip that, unlike the copy loop,
 *     is not stopped by a `*` or by a space;
 *   * the stem's tail then steps the text PAST the `*` it stopped on and past a `.` after it
 *     ($fc5d94/$fc5d9c), which is what hands the extension's loop the right place to start. The
 *     extension's tail reads the same character to choose its padding and advances nothing — the
 *     routine is over.
 */
void gemdos_build_fcb_name(uint8_t *image, uint32_t path, uint32_t fcb)
{
    uint32_t at = path;
    uint32_t out = fcb;
    uint16_t written = copy_field_text(image, &at, &out, FCB_STEM_BYTES);

    if (written == FCB_STEM_BYTES)
        while (image[at] != '\0' && image[at] != NAME_DOT && image[at] != PATH_SEPARATOR)
            at++;
    pad_field(image, image[at], &out, written, FCB_STEM_BYTES);
    if (image[at] == NAME_WILDCARD)
        at++;
    if (image[at] == NAME_DOT)
        at++;

    written = copy_field_text(image, &at, &out, FCB_EXTENSION_BYTES);
    pad_field(image, image[at], &out, written, FCB_EXTENSION_BYTES);
}

/* $fc5c9a — does `pattern` (eleven FCB bytes) describe `entry` (a directory entry's first eleven)?
 *
 * THREE ARMS AND THEY ARE NOT IN NAME ORDER, which is the whole of this routine's subtlety:
 *
 *   1. the entry is DELETED (`$e5`). Then a pattern whose first byte is `?` does NOT match it —
 *      the one place a `?` is refused — and a pattern whose first byte is `$e5` DOES, which is how
 *      the ROM finds a deleted slot to reuse. Anything else falls into the general comparison,
 *      where the `$e5` is just a byte.
 *   2. the eleven positions, where a `?` in the pattern accepts anything and everything else is
 *      compared UPPER-CASED on both sides.
 *   3. ...and then the ATTRIBUTE byte at +11, which the caller has put in the twelfth position of
 *      both buffers. Two tests, and the first is NARROWER than it looks: an entry attribute of 0
 *      matches anything — which is how a plain file answers a request for "files" — UNLESS the
 *      pattern's attribute is 8, the volume label, which is the one pattern a plain file must not
 *      answer. Everything else, the volume label included, then goes through the same `and.w`: the
 *      two match when they share a bit, so a pattern of 8 matches an entry of $18 as well as one
 *      of 8. Only the SHORTCUT is special-cased, not the comparison.
 */
/* A miss is `clr.w d0`: the low word only, the caller's high half standing. Formed at each return
 * rather than once up front, which is the shape the compiler keeps out of a register across the
 * loop (measured: hoisted, it cost this routine 40 of its Tier 3 cycles). */
static uint32_t no_match(uint32_t entry_d0)
{
    return set_low_word(entry_d0, 0);
}

uint32_t gemdos_name_match(uint32_t entry_d0, const uint8_t *image, uint32_t pattern,
                           uint32_t entry)
{
    uint32_t yes = 1;                       /* `moveq #1,d0`, which writes all of it */
    uint16_t at;

    if (image[entry] == DIRENT_DELETED) {
        if (image[pattern] == FCB_ANY)
            return no_match(entry_d0);
        if (image[pattern] == DIRENT_DELETED)
            return yes;
    }
    for (at = 0; at < FCB_NAME_BYTES; at++) {
        if (image[pattern + at] == FCB_ANY)
            continue;
        if (gemdos_fs_toupper(0, image[entry + at]) != gemdos_fs_toupper(0, image[pattern + at]))
            return no_match(entry_d0);
    }
    if (image[pattern + FCB_NAME_BYTES] != GEMDOS_ATTR_VOLUME && image[entry + FCB_NAME_BYTES] == 0)
        return yes;       /* the shortcut, and the one pattern that loses it */
    return (image[pattern + FCB_NAME_BYTES] & image[entry + FCB_NAME_BYTES]) ? yes : no_match(entry_d0);
}
