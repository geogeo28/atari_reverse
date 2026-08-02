/* rad.c — the game's own resource depacker (rad_depack @ 0x5d62), which inflates every packed
 * resource the game loads off disk: disk 1's CREDITS.RAD and TITLESCR.RAD, and disk 2's
 * OVALAY*.RAD / TILEDATA.RAD / DATADISK.RAD. It covers the whole routine,
 * 0x5d62..0x5e3a: ../names.txt splits it into three (rad_depack, plus the leaf helpers
 * rad_refill_bit_buffer @ 0x5e14 and rad_get_bits @ 0x5e20), and each is named below where it lands.
 *
 * Backwards LZ77 over a longword-buffered bitstream: both the stream and the output are walked
 * DOWNWARDS, from EOF and from the end of the destination. The container and every token width are
 * in include/rad.h; the routine itself is transcribed in ../../notes/rad_depacker.asm.
 *
 * The whole observable effect is the destination buffer plus the one scratch long the original
 * parks its caller's stack pointer in (WB_RAD_SAVED_SP) — no hardware, no OS call, no disk — so
 * this is a function the memory differential can see in full.
 *
 * It has essentially no error handling: it decodes whatever it is handed, and reports exactly one
 * thing, a checksum that did not cancel. Reproduced as such (this is the recreate track — original
 * behaviour beats defensive behaviour), so a damaged stream reads and writes outside its buffers
 * here exactly as it does on the 68000 — WITHIN THE MAPPED IMAGE, which is what lets the disk's
 * four damaged overlays pin the failure path.
 *
 * OFF the image the two diverge by construction, and knowingly: the oracle's shim answers a read
 * past the image with zeros and drops the write (tools/recreate_kit/oracle/shim.c), while this C
 * indexes a host buffer and is plain undefined behaviour there. Every one of the 45 corpus cases
 * lays both buffers inside the image (the differential's `_check_layout`) and the oracle's write
 * set stays inside them (`_stray_writes`), so no case in the battery is in that territory. An
 * access layer that emulated the bounds would be a kit change, not a port one, and is not built.
 */
#include "machine.h"
#include "rad.h"
#include "wonderboy.h"

/* The stream as the original holds it, in three registers: a0 / d0 / d5. */
typedef struct {
    uint8_t *image;      /* the flat 68000 image; every address below is an index into it */
    uint32_t cursor;     /* a0: predecrement pointer — the next longword read lies just below it */
    uint32_t bit_buffer; /* d0: emptied LSB-first, refilled a longword at a time */
    uint32_t checksum;   /* d5: seeded from the header, XORed with every longword read; a correct
                          * decode brings it back to 0 */
} rad_stream;

/* `move.l -(a0),d0 / eor.l d0,d5` — the first half of rad_refill_bit_buffer @ 0x5e14, and the same
 * two instructions the SEED read uses (@ 0x5d74). The three HEADER longwords are read differently:
 * POST-increment `move.l (a0)+,dN` with no checksum XOR (@ 0x5d68), which is why rad_depack reads
 * them straight out of the image rather than through this helper. */
static uint32_t rad_read_long(rad_stream *stream) {
    stream->cursor -= RAD_LONG;
    uint32_t value = be32(stream->image + stream->cursor);
    stream->checksum ^= value;
    return value;
}

/* One stream bit. A buffer whose remainder is 0 is spent: the refill brings the next longword's
 * bit 0 out immediately and rotates the fresh marker into bit 31 above it. Folds the original's
 * inline `lsr.l #1,d0` getbit together with the rad_refill_bit_buffer @ 0x5e14 it falls into, which
 * every one of its four call sites pairs it with. */
static uint32_t rad_bit(rad_stream *stream) {
    uint32_t bit = stream->bit_buffer & 1u;
    stream->bit_buffer >>= 1;
    if (stream->bit_buffer != 0) return bit;
    uint32_t refill = rad_read_long(stream);
    stream->bit_buffer = RAD_END_MARKER | (refill >> 1);
    return refill & 1u;
}

/* A field of `count` stream bits, MSB first — rad_get_bits @ 0x5e20 (its `roxl.l #1,d2` loop). */
static uint32_t rad_get_bits(rad_stream *stream, uint32_t count) {
    uint32_t value = 0;
    while (count-- != 0) value = (value << 1) | rad_bit(stream);
    return value;
}

/* `count` literal bytes, each 8 plain stream bits. The original reads them inline rather than
 * through its get-bits helper, which changes nothing: only the low byte of the field is stored. */
static uint32_t rad_copy_literals(rad_stream *stream, uint32_t write_ptr, uint32_t count) {
    while (count-- != 0) {
        write_ptr--;
        stream->image[write_ptr] = (uint8_t)rad_get_bits(stream, RAD_LITERAL_BITS);
    }
    return write_ptr;
}

/* `move.b 0(a2,d2.w),(a2)`: the source is ABOVE the write pointer, i.e. output already written,
 * since the destination fills downwards. Byte at a time is not an implementation detail — an offset
 * smaller than the length makes the copy re-read bytes this same match has just written, which is
 * how the format encodes runs. (The 68000 indexes with a SIGN-EXTENDED word, but every offset field
 * is at most 12 bits, so the index is always positive.) */
static uint32_t rad_copy_match(uint8_t *image, uint32_t write_ptr, uint32_t length,
                               uint32_t offset) {
    while (length-- != 0) {
        write_ptr--;
        image[write_ptr] = image[write_ptr + offset];
    }
    return write_ptr;
}

/* Decode one token at `write_ptr`; return the new write pointer. */
static uint32_t rad_decode_token(rad_stream *stream, uint32_t write_ptr) {
    if (rad_bit(stream) == 0) {
        if (rad_bit(stream) != 0) {
            uint32_t offset = rad_get_bits(stream, RAD_MATCH2_OFF_BITS);
            return rad_copy_match(stream->image, write_ptr, RAD_MATCH2_LEN, offset);
        }
        return rad_copy_literals(stream, write_ptr,
                                 rad_get_bits(stream, RAD_LIT_SHORT_BITS) + RAD_LIT_SHORT_BASE);
    }
    uint32_t selector = rad_get_bits(stream, RAD_SEL_BITS);
    if (selector == RAD_SEL_LONG_LITERALS) {
        return rad_copy_literals(stream, write_ptr,
                                 rad_get_bits(stream, RAD_LIT_LONG_BITS) + RAD_LIT_LONG_BASE);
    }
    if (selector == RAD_SEL_LONG_MATCH) {
        uint32_t length = rad_get_bits(stream, RAD_LONG_MATCH_LEN_BITS) + RAD_LONG_MATCH_LEN_BASE;
        return rad_copy_match(stream->image, write_ptr, length,
                              rad_get_bits(stream, RAD_LONG_MATCH_OFF_BITS));
    }
    uint32_t offset = rad_get_bits(stream, selector + RAD_SHORT_MATCH_OFF_BASE);
    return rad_copy_match(stream->image, write_ptr, selector + RAD_SHORT_MATCH_LEN_BASE, offset);
}

uint32_t rad_depack(uint8_t *image, uint32_t src, uint32_t dst) {
    uint32_t packed = be32(image + src + RAD_HDR_PACKED_OFF);
    uint32_t unpacked = be32(image + src + RAD_HDR_UNPACKED_OFF);
    rad_stream stream = {image, src + RAD_HDR_LEN + packed, 0,
                         be32(image + src + RAD_HDR_CHECKSUM_OFF)};
    stream.bit_buffer = rad_read_long(&stream);   /* the seed longword carries no injected marker */

    uint32_t write_ptr = dst + unpacked;          /* a2, filling downwards towards dst */
    do {
        write_ptr = rad_decode_token(&stream, write_ptr);
    } while ((int32_t)dst < (int32_t)write_ptr);  /* `cmpa.l a2,a1 / blt`: a SIGNED compare, and
                                                   * tested BETWEEN tokens only, so a token may
                                                   * overrun the start */

    /* The original spins a 65536-iteration delay loop before reporting; that is timing alone, and
     * this differential's surface is memory plus the returned d0. */
    if (stream.checksum != 0) return WB_RAD_BAD_CHECKSUM;
    return stream.bit_buffer;   /* d0 on the success path: the spent buffer, and not a status */
}

/* Differential glue. The scratch long is not part of the algorithm: the 68000 routine parks its
 * CALLER's stack pointer there (`move.l a7,$5e3a.l`) so the success path can restore it, and a C
 * port has no such register to save. The harness supplies the stack pointer the oracle entered
 * with, so the byte-for-byte diff still covers the write — see test/test_rad_depack.py. */
uint32_t g_rad_depack(uint8_t *image, uint32_t src, uint32_t dst, uint32_t entry_sp) {
    wr32(image + WB_RAD_SAVED_SP, entry_sp);
    return rad_depack(image, src, dst);
}
