/* stepix LZSS depacker -- the engine-side twin of stepix/pack.py's lz_unpack().
 *
 * WHY it looks like this: this loop is the shape the 68000 version wants, so that the C
 * here and the eventual hand-asm agree byte for byte. The natural register assignment is
 *
 *     a0 = src (packed stream)      a1 = dst (write pointer)      a2 = match source
 *     d0 = control byte             d1 = bits left in d0          d2 = match token / length
 *
 * and the depacker needs no window buffer: matches are copied out
 * of the destination that has already been written, so a match may legally overlap itself
 * (offset 1, length 18 = a 18-byte run fill). That is why the copy is byte-at-a-time and
 * must NOT be turned into memcpy/memmove -- memcpy would read the pre-overlap bytes.
 *
 * Every bound is checked once per token (never per byte, never with a division), so a
 * malformed stream fails with STEPIX_DEPACK_BAD_STREAM instead of walking off either buffer,
 * and the inner loops stay two instructions.
 *
 * Measured: m68k-elf-gcc -m68000 -Os compiles this to 168 bytes of text, no data, no bss
 * (176 at -O2); the bounds checks cost 50 bytes over the unchecked version's 118.
 *
 * The stream carries no end marker: the caller knows raw_len from the PAK directory entry.
 *
 * Stream format (big-endian, matching README.md):
 *   control byte, consumed MSB first, 8 tokens per control byte
 *     bit 1 -> literal byte follows
 *     bit 0 -> 2-byte match token ((len - MIN_MATCH) << 12) | (offset - 1)
 */

#include "depack.h"

#define LZ_MIN_MATCH          3      /* shortest encodable match                       */
#define LZ_LENGTH_SHIFT      12      /* match token: length nibble sits in bits 15..12 */
#define LZ_OFFSET_MASK   0x0fffu     /* 12-bit backwards offset, biased by 1           */
#define LZ_CONTROL_MSB     0x80u     /* control bits are consumed most-significant first */
#define LZ_MATCH_TOKEN_BYTES  2      /* a match token is two stream bytes              */
#define BITS_PER_BYTE         8

int stepix_depack(const unsigned char *src, unsigned long packed_len,
                  unsigned char *dst, unsigned long raw_len)
{
    const unsigned char *src_end = src + packed_len;
    unsigned char *out = dst;
    unsigned char *end = dst + raw_len;
    unsigned int control = 0;
    unsigned int control_bit = 0;

    while (out < end) {
        if (control_bit == 0) {
            if (src >= src_end) {
                return STEPIX_DEPACK_BAD_STREAM;        /* truncated before a control byte */
            }
            control = *src++;
            control_bit = LZ_CONTROL_MSB;
        }

        if (control & control_bit) {
            if (src >= src_end) {
                return STEPIX_DEPACK_BAD_STREAM;        /* truncated before a literal */
            }
            *out++ = *src++;                            /* literal */
        } else {
            unsigned int token;
            unsigned long length, offset, room;
            const unsigned char *match;

            if ((unsigned long)(src_end - src) < LZ_MATCH_TOKEN_BYTES) {
                return STEPIX_DEPACK_BAD_STREAM;        /* truncated inside a match token */
            }
            token = (unsigned int)src[0] << BITS_PER_BYTE | (unsigned int)src[1];
            src += LZ_MATCH_TOKEN_BYTES;
            length = (unsigned long)(token >> LZ_LENGTH_SHIFT) + LZ_MIN_MATCH;
            offset = (unsigned long)(token & LZ_OFFSET_MASK) + 1;

            if (offset > (unsigned long)(out - dst)) {
                return STEPIX_DEPACK_BAD_STREAM;        /* would read before dst */
            }
            room = (unsigned long)(end - out);
            if (length > room) {
                length = room;                          /* the last match may overshoot raw_len */
            }

            match = out - offset;
            while (length--) {
                *out++ = *match++;          /* byte at a time: overlapping matches are legal */
            }
        }
        control_bit >>= 1;
    }
    return STEPIX_DEPACK_OK;
}
