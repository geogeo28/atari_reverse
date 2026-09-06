/* raster.c — the bit-level raster model. WHAT it is and WHY it is stateless is in ../include/raster.h;
 * what the VDI opcodes above it do and do not capture is in TRAP_MODEL.md, "Phase 11".
 *
 * Written a pixel at a time rather than a word at a time. The word-parallel form is what a real VDI
 * does and is perhaps twenty times quicker, but it needs edge masks, a shift between differing
 * source and destination alignments, and a separate first/last-word path — three places for an
 * off-by-one that the differential could not see, because both sides would run the SAME wrong code.
 * The per-pixel form is the definition of the operation, and the runs that use it move at most a few
 * hundred thousand pixels.
 */
#include <stdint.h>

#include "os.h"
#include "raster.h"

/* The truth-table encoding: op n written b3 b2 b1 b0 answers b(3 - ((S << 1) | D)). See raster.h. */
#define RASTER_OP_TABLE_INDEX_MAX 3

int raster_logic_op(int op, int src_bit, int dst_bit) {
    if (op < 0 || op >= RASTER_OP_COUNT) return 0;
    int index = ((src_bit & 1) << 1) | (dst_bit & 1);
    return (op >> (RASTER_OP_TABLE_INDEX_MAX - index)) & 1;
}

uint64_t raster_bytes(const raster_t *raster) {
    return (uint64_t)raster->h * (uint64_t)raster->wdwidth * RASTER_WORD_BYTES
           * (uint64_t)raster->nplanes;
}

int raster_valid(const raster_t *raster) {
    if (raster->w <= 0 || raster->h <= 0 || raster->wdwidth <= 0) return 0;
    if (raster->nplanes < RASTER_MIN_PLANES || raster->nplanes > RASTER_MAX_PLANES) return 0;
    /* The declared width must fit the declared word count, or a pixel inside the extent addresses a
     * word outside the row and lands in the NEXT row's planes. */
    if (raster->w > raster->wdwidth * RASTER_PIXELS_PER_WORD) return 0;
    /* raster_bytes() is 64-bit precisely because these three come off the emulated program's stack;
     * the length is bounded by the image BEFORE it is narrowed to the in-image test's uint32. */
    uint64_t bytes = raster_bytes(raster);
    if (bytes > OS_IMAGE_SIZE) return 0;
    return os_in_image(raster->addr, (uint32_t)bytes);
}

int raster_in_extent(const raster_t *raster, int32_t x, int32_t y) {
    return x >= 0 && y >= 0 && x < raster->w && y < raster->h;
}

/* Where one pixel lives: the byte holding PLANE 0's bit, and the mask within it. Every other plane
 * is the same mask RASTER_WORD_BYTES further on, which is what lets a caller resolve this once per
 * pixel and then walk the planes. */
raster_at_t raster_locate(const raster_t *raster, int32_t x, int32_t y) {
    int32_t word_stride = RASTER_WORD_BYTES * raster->nplanes;   /* one 16-pixel column, all planes */
    int32_t row = y * raster->wdwidth * word_stride;
    int32_t word = (x / RASTER_PIXELS_PER_WORD) * word_stride;
    int bit = (RASTER_PIXELS_PER_WORD - 1) - (int)(x % RASTER_PIXELS_PER_WORD);
    int high_byte = bit >= 8;                       /* bit 15 is the MSB of the word's FIRST byte */
    raster_at_t at;

    at.byte = raster->addr + (uint32_t)(row + word) + (high_byte ? 0u : 1u);
    at.mask = (uint8_t)(1u << (bit & 7));
    return at;
}

int raster_at_plane_bit(const uint8_t *mem, const raster_at_t *at, int plane) {
    return (mem[at->byte + (uint32_t)plane * RASTER_WORD_BYTES] & at->mask) ? 1 : 0;
}

void raster_at_set_plane_bit(uint8_t *mem, const raster_at_t *at, int plane, int bit) {
    uint8_t *cell = mem + at->byte + (uint32_t)plane * RASTER_WORD_BYTES;
    *cell = bit ? (uint8_t)(*cell | at->mask) : (uint8_t)(*cell & (uint8_t)~at->mask);
}

/* The colour INDEX written across `nplanes` planes of one located pixel: plane p takes bit p. */
void raster_at_set_pixel(uint8_t *mem, const raster_at_t *at, int nplanes, int colour) {
    for (int plane = 0; plane < nplanes; plane++)
        raster_at_set_plane_bit(mem, at, plane, (colour >> plane) & 1);
}

/* The single-pixel spellings, over the same addressing rather than beside it. */
int raster_plane_bit(const uint8_t *mem, const raster_t *raster, int32_t x, int32_t y, int plane) {
    raster_at_t at = raster_locate(raster, x, y);
    return raster_at_plane_bit(mem, &at, plane);
}

void raster_set_plane_bit(uint8_t *mem, const raster_t *raster, int32_t x, int32_t y,
                          int plane, int bit) {
    raster_at_t at = raster_locate(raster, x, y);
    raster_at_set_plane_bit(mem, &at, plane, bit);
}

int raster_pixel(const uint8_t *mem, const raster_t *raster, int32_t x, int32_t y) {
    raster_at_t at = raster_locate(raster, x, y);
    int colour = 0;
    for (int plane = 0; plane < raster->nplanes; plane++)
        colour |= raster_at_plane_bit(mem, &at, plane) << plane;
    return colour;
}

void raster_set_pixel(uint8_t *mem, const raster_t *raster, int32_t x, int32_t y, int colour) {
    raster_at_t at = raster_locate(raster, x, y);
    raster_at_set_pixel(mem, &at, raster->nplanes, colour);
}

/* Row `row` of `ch`'s glyph: the character's own byte rotated left by the row number. `row` is
 * masked rather than bounded, so the eighth row wraps back to the character itself and no caller can
 * step outside the glyph. */
uint8_t raster_font_row(uint8_t ch, int row) {
    unsigned n = (unsigned)row & (RASTER_FONT_H - 1);
    return (uint8_t)((ch << n) | (ch >> (RASTER_FONT_H - n)));   /* n = 0 shifts the byte out: 0 */
}
