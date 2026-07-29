/* blit.c — the three rectangular block moves (blit_copy @ 0x1042a, blit_or @ 0x10456,
 * blit_andnot @ 0x10482).
 *
 * The shipped binary carries the same 44-byte routine three times over, differing only in how each
 * source longword is combined into the destination, so one core serves all three here. Each moves
 * `cols` 4-plane cells per row for `rows` rows: the source is read straight through, while the
 * destination restarts one full scanline further down every row — which is what makes it a
 * rectangle rather than a run. Nothing clips, and rows overlap freely when a row is wider than a
 * scanline; the order below is the original's, so the overlap resolves the same way.
 */
#include "machine.h"
#include "joust.h"

typedef enum { BLIT_OP_COPY, BLIT_OP_OR, BLIT_OP_ANDNOT } blit_op;

/* One `move.l (a1)+,d3` and its combine into `(a2)+`: the unit each blit repeats twice per cell. */
static void blit_longword(uint8_t *image, uint32_t dst, uint32_t src, blit_op op) {
    uint32_t pixels = be32(image + src);
    switch (op) {
    case BLIT_OP_COPY:                                            break;
    case BLIT_OP_OR:     pixels |= be32(image + dst);             break;
    case BLIT_OP_ANDNOT: pixels = be32(image + dst) & ~pixels;    break;   /* not.l d3 ; and.l d3 */
    }
    wr32(image + dst, pixels);
}

/* One row — the inner loop at 0x440 / 0x46c / 0x498. Register map: a2 = running destination,
 * a1 = source, d0 = the column counter (`subq.b`, so only its low byte counts), d3 = the source
 * longword. Returns where the source ran to: a1 is never reset between rows, so the two callers
 * below thread it on rather than recomputing it. */
static uint32_t blit_row(uint8_t *image, uint32_t dst, uint32_t src, uint16_t cols, blit_op op) {
    unsigned col_passes = loop_passes(cols, COUNT_MASK_BYTE);

    for (unsigned col = 0; col < col_passes; col++) {
        blit_longword(image, dst, src, op);
        blit_longword(image, dst + 4, src + 4, op);
        dst += CELL_BYTES;
        src += CELL_BYTES;
    }
    return src;
}

/* Stack ABI, identical for all three: the caller pushes a 12-byte block that the routine reads
 * from 4(a7). `args` is that block's image address. */
#define BLIT_ARG_DST  0u   /*  4(a7) .l — destination of the top-left cell */
#define BLIT_ARG_SRC  4u   /*  8(a7) .l — source, read straight through */
#define BLIT_ARG_COLS 8u   /* 12(a7) .w — cells per row (low byte only; 0 means 256) */
#define BLIT_ARG_ROWS 10u  /* 14(a7) .w — rows          (low byte only; 0 means 256) */

/* The differential-verified entity: one blit driven from its argument block, byte for byte as the
 * original drives it — which includes re-reading `cols` from that block once per row. The row
 * branch (`bne.s` at 0x452 / 0x47e / 0x4aa) targets the `move.w 12(a7),d0` that fetches `cols`,
 * whereas `rows` is fetched once, above the loop (0x436). That distinction is observable exactly
 * when the destination rectangle covers the argument block itself, so it is modelled here — in the
 * only layer that still has a block to re-read from. */
static void blit_from_args(uint8_t *image, uint32_t args, blit_op op) {
    uint32_t dst = be32(image + args + BLIT_ARG_DST);
    uint32_t src = be32(image + args + BLIT_ARG_SRC);
    unsigned row_passes = loop_passes(be16(image + args + BLIT_ARG_ROWS), COUNT_MASK_BYTE);

    for (unsigned row = 0; row < row_passes; row++) {
        src = blit_row(image, dst, src, be16(image + args + BLIT_ARG_COLS), op);
        dst += SCREEN_ROW_BYTES;                                  /* adda.w #$a0,a0 — next line */
    }
}

void g_blit_copy(uint8_t *image, uint32_t args)   { blit_from_args(image, args, BLIT_OP_COPY); }
void g_blit_or(uint8_t *image, uint32_t args)     { blit_from_args(image, args, BLIT_OP_OR); }
void g_blit_andnot(uint8_t *image, uint32_t args) { blit_from_args(image, args, BLIT_OP_ANDNOT); }

/* The same rectangle for reconstructed C callers, which pass `cols`/`rows` in registers instead of
 * through an image-resident block. `cols` is therefore held in a parameter rather than re-read: a
 * caller with no argument block in the image has nothing to re-read, and no destination can alias
 * one. This form is NOT what the differential runs (that is blit_from_args above), so no verified
 * result rests on it. a0 = row base, d1 = the row counter (`subq.b` again). */
static void blit_rect(uint8_t *image, uint32_t dst, uint32_t src,
                      uint16_t cols, uint16_t rows, blit_op op) {
    unsigned row_passes = loop_passes(rows, COUNT_MASK_BYTE);

    for (unsigned row = 0; row < row_passes; row++) {
        src = blit_row(image, dst, src, cols, op);
        dst += SCREEN_ROW_BYTES;
    }
}

void blit_copy(uint8_t *image, uint32_t dst, uint32_t src, uint16_t cols, uint16_t rows) {
    blit_rect(image, dst, src, cols, rows, BLIT_OP_COPY);
}

void blit_or(uint8_t *image, uint32_t dst, uint32_t src, uint16_t cols, uint16_t rows) {
    blit_rect(image, dst, src, cols, rows, BLIT_OP_OR);
}

void blit_andnot(uint8_t *image, uint32_t dst, uint32_t src, uint16_t cols, uint16_t rows) {
    blit_rect(image, dst, src, cols, rows, BLIT_OP_ANDNOT);
}
