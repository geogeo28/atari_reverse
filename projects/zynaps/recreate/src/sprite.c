/* sprite.c — the boot-time sprite table builders.
 *
 * `_start` loads each graphic straight off the disk and then reshapes it in place into the form the
 * draw loop wants. Two shapes appear:
 *
 *   * ship_sprite_deinterleave @ 0x13bde deals a 400-byte ship source into two 200-byte frames
 *     1600 bytes apart, and
 *   * sprite_preshift8_2px @ 0x153f6 / sprite_preshift4_4px @ 0x15420 fan one frame of bitmap words
 *     out into a bank of pre-rotated copies, so the draw loop can pick a sub-cell phase by indexing
 *     instead of by shifting.
 *
 * All three are pure image-to-image transforms over caller-supplied pointers: no globals, no traps.
 */
#include "machine.h"
#include "sprite.h"

/* ================================================================================================
 * ship_sprite_deinterleave @ 0x13bde — 7 call sites, all in `_start` (bsr at 0x100d2, 0x100e2,
 * 0x100f2, 0x10102, 0x10112, 0x10122, 0x10132).
 *
 * The source is 20 rows of 20 bytes; the first 10 bytes of each row go to `dst` and the second 10
 * to `dst + 1600`, both packed 10 bytes per row. Every caller passes a source inside the single
 * 0xaf0-byte file staged at 0x577fe (seven 400-byte records, one per call) and a destination 3200
 * bytes apart from its neighbour's — 3200 being sixteen 200-byte frames, of which this fills frames
 * 0 and 8. The last call (0x10132) passes src == dst == 0x577fe and rewrites the file in place.
 * ============================================================================================= */
#define SHIP_SPRITE_ROWS       20u    /* `move.w #$13,d1` + `dbf`: a fixed count, not an argument */
#define SHIP_SPRITE_HALF_BYTES 10u    /* `move.l / move.l / move.w` — one half of one source row */
#define SHIP_SPRITE_GAP      1600u    /* `lea 1600(a1),a2` — where the second frame starts */

/* One `move.l (a0)+,(a1)+ / move.l (a0)+,(a1)+ / move.w (a0)+,(a1)+` run, spelt out in the
 * original's read-then-store order. That order is observable whenever the source overlaps EITHER
 * destination frame — test_sprite.py's seven overlap offsets are what hold it. It is NOT observable
 * in the in-place shape the seventh call site uses: there the write cursor trails the read cursor
 * by 10 bytes per row and the second frame sits 1600 bytes past the 400-byte source, so no store
 * ever lands on a byte still to be read. */
static void copy_half_row(uint8_t *image, uint32_t src, uint32_t dst) {
    wr32(image + dst,     be32(image + src));
    wr32(image + dst + 4, be32(image + src + 4));
    wr16(image + dst + 8, be16(image + src + 8));
}

void ship_sprite_deinterleave(uint8_t *image, uint32_t src, uint32_t dst) {
    uint32_t first_frame = dst;
    uint32_t second_frame = addr_add(dst, SHIP_SPRITE_GAP);

    for (unsigned row = 0; row < SHIP_SPRITE_ROWS; row++) {
        copy_half_row(image, src, first_frame);
        src = addr_add(src, SHIP_SPRITE_HALF_BYTES);
        first_frame = addr_add(first_frame, SHIP_SPRITE_HALF_BYTES);

        copy_half_row(image, src, second_frame);
        src = addr_add(src, SHIP_SPRITE_HALF_BYTES);
        second_frame = addr_add(second_frame, SHIP_SPRITE_HALF_BYTES);
    }
}

/* ================================================================================================
 * sprite_preshift8_2px @ 0x153f6 (10 call sites) and sprite_preshift4_4px @ 0x15420 (6).
 *
 * Both read `frame_bytes / 2` words straight through from `src` and lay each one down repeatedly,
 * rotating it right a fixed number of bits between stores. Store j of a row lands at
 * `dst + j*slot_span*frame_bytes + 2*row`, so the destination reads as a bank of eight
 * `frame_bytes`-sized SLOTS holding the same frame at successive sub-cell phases:
 *
 *   2px: 7 stores, slot_span 1  -> slots 1..7 hold phases 2,4,6,8,10,12,14
 *   4px: 3 stores, slot_span 2  -> slots 2,4,6  hold phases 4,8,12
 *
 * Slot 0 is never written: every call site passes src == dst (in place), so slot 0 IS the source
 * frame and is already the phase-0 copy. The two entries therefore build the same eight-slot bank
 * to two granularities — every 2 pixels, or every 4. names.txt: the 4-px twin serves objects whose
 * x is forced to a multiple of 4, and the draw side re-splits the bank with the keep-masks at
 * `shift_mask_table` (0x1821e).
 *
 * SHIPPED WIDTHS — the provenance lives here, and the battery cites it rather than restating it.
 * Sixteen call sites reach the two entries. FIFTEEN load D2 from an immediate right above the
 * `bsr`: nine into the 2-px entry (0x50, 0x5a, 0xc8, 0x50, then 0xa0 five times) and six into the
 * 4-px one (0xa0, 0x50, then 0x5a four times). The sixteenth, at 0x153e6, is the tail `bsr` inside
 * sprite_bank_build_preshift8 @ 0x153c0, which sets no D2 of its own and passes on whatever its
 * eight callers loaded — 0x50, 0x6e, 0xa0, 0x6e, 0x1e, 0xa0, 0xa0, 0xa0.
 *
 * So the union is 0x1e, 0x50, 0x5a, 0x6e, 0xa0, 0xc8, and the smallest shipped width is 0x1e
 * (15 rows) — reachable only through that inherited path, not through any direct call site.
 *
 * The loop count is a word (`lsr.w #1,d2 / sub.w #$1,d2 / dbf`), so a `frame_bytes` below 2 wraps
 * to 65536 rows rather than running none. No caller comes near that.
 * ============================================================================================= */
#define PRESHIFT_WORD_BYTES 2u  /* `move.w (a0)+,d1` and `lea 2(a1),a1` — the unit of a row */
#define PRESHIFT_2PX_COPIES 7u  /* `moveq #$6,d4` + `dbf` */
#define PRESHIFT_2PX_PHASE  2u  /* `ror.w #2,d1` */
#define PRESHIFT_2PX_SPAN   1u  /* `move.w d2,d3` alone, and one `sub.w d2,d5` */
#define PRESHIFT_4PX_COPIES 3u  /* `moveq #$2,d4` + `dbf` */
#define PRESHIFT_4PX_PHASE  4u  /* `ror.w #4,d1` */
#define PRESHIFT_4PX_SPAN   2u  /* `move.w d2,d3 / lsl.w #1,d3`, and two `sub.w d2,d5` */

/* `slot_span` is ONE fact spelt twice by the original, so it is one constant here: it is both how
 * many `frame_bytes` a store advances the cursor (`lsl.w #1,d3` for the 4-px entry, nothing for the
 * 2-px one) and how many times `frame_bytes` comes off the eight-slot total to build the step-back
 * the run gives back at the end of each row. `dst` is left one word past the row's slot-0 cell,
 * which is the routine's only output besides the image. */
static uint32_t build_preshift_bank(uint8_t *image, uint32_t src, uint32_t dst, uint16_t frame_bytes,
                                    unsigned copies, unsigned phase_bits, unsigned slot_span) {
    uint32_t slot_step = sign_ext16((uint16_t)(frame_bytes * slot_span));   /* adda.w d3,a1 */
    /* `clr.l d5 / move.w d2,d5 / lsl.l #3,d5`, then one `sub.w d2,d5` per spanned slot. The
     * subtractions go through the kit's `word_sub` rather than a multiply because `sub.w` on a
     * longword register leaves the high half alone (machine.h); from frame_bytes 0x2000 up the two
     * stop agreeing. */
    uint32_t back_step = frame_bytes * SPRITE_PRESHIFT_SLOTS;
    for (unsigned slot = 0; slot < slot_span; slot++)
        back_step = word_sub(back_step, frame_bytes);

    unsigned rows = loop_passes((uint16_t)(frame_bytes >> 1), COUNT_MASK_WORD);
    for (unsigned row = 0; row < rows; row++) {
        uint16_t pixels = be16(image + src);
        src = addr_add(src, PRESHIFT_WORD_BYTES);

        for (unsigned copy = 0; copy < copies; copy++) {
            dst = addr_add(dst, slot_step);
            pixels = rotate_right16(pixels, phase_bits);
            wr16(image + dst, pixels);
        }
        dst = addr_add(dst, PRESHIFT_WORD_BYTES - back_step);   /* suba.l d5,a1 ; lea 2(a1),a1 */
    }
    return dst;
}

uint32_t sprite_preshift8_2px(uint8_t *image, uint32_t src, uint32_t dst, uint16_t frame_bytes) {
    return build_preshift_bank(image, src, dst, frame_bytes,
                               PRESHIFT_2PX_COPIES, PRESHIFT_2PX_PHASE, PRESHIFT_2PX_SPAN);
}

uint32_t sprite_preshift4_4px(uint8_t *image, uint32_t src, uint32_t dst, uint16_t frame_bytes) {
    return build_preshift_bank(image, src, dst, frame_bytes,
                               PRESHIFT_4PX_COPIES, PRESHIFT_4PX_PHASE, PRESHIFT_4PX_SPAN);
}

/* ================================================================================================
 * Glue. Register map for all three: A0 = source, A1 = destination, D2 = frame length in bytes
 * (`ship_sprite_deinterleave` has no D2 — its geometry is fixed). The preshift builders return A1.
 * ============================================================================================= */
void g_ship_sprite_deinterleave(uint8_t *image, uint32_t src, uint32_t dst) {
    ship_sprite_deinterleave(image, src, dst);
}

uint32_t g_sprite_preshift8_2px(uint8_t *image, uint32_t src, uint32_t dst, uint32_t frame_bytes) {
    return sprite_preshift8_2px(image, src, dst, (uint16_t)frame_bytes);
}

uint32_t g_sprite_preshift4_4px(uint8_t *image, uint32_t src, uint32_t dst, uint32_t frame_bytes) {
    return sprite_preshift4_4px(image, src, dst, (uint16_t)frame_bytes);
}
