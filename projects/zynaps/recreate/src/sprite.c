/* sprite.c — the sprite banks, and the two blitters that read them.
 *
 * Two groups. The BUILDERS run once, at boot or when a boss spawns: `_start` loads each graphic
 * straight off the disk and then reshapes it into the form the draw loop wants —
 *
 *   * ship_sprite_deinterleave @ 0x13bde deals a 400-byte ship source into two 200-byte frames
 *     1600 bytes apart;
 *   * sprite_preshift8_2px @ 0x153f6 / sprite_preshift4_4px @ 0x15420 fan one frame of bitmap words
 *     out into a bank of pre-rotated copies, so the draw loop can pick a sub-cell phase by indexing
 *     instead of by shifting;
 *   * sprite_bank_build_preshift8 @ 0x153c0 composes the two of them: it spreads a run of frames
 *     out one bank apart with `copy_block_words` and then preshifts each in place;
 *   * asteroid_preshift_bank @ 0x15758 does the same to a MASKED sprite, by repeated one-pixel
 *     shifts rather than by rotation, and mothership_sprite_expand @ 0x157ca lays the boss sprite
 *     out with the blank margin that shifting needs — which mothership_sprite_preshift @ 0x15838
 *     then shifts it into.
 *
 * ...and the DRAW side is draw_sprite_masked @ 0x15ace and draw_sprite_masked_collide @ 0x15b7c,
 * which run every frame per live entity.
 *
 * Every builder but the two mothership ones is a pure image-to-image transform over
 * caller-supplied pointers; those two and the blitters reach absolute addresses and globals
 * instead (`screen_back`, the entity record, the boss's encounter flags). That is why this file
 * includes five other subsystems' headers: entity.h and video.h for the blitters' record and
 * framebuffer, mothership.h for the boss-sprite addresses and encounter flags that subsystem owns,
 * and collision.h and enemy.h for one value each — plus util.h, whose `copy_block_words` the
 * whole-file bank builder composes. None of them traps.
 */
#include "machine.h"
/* The blitters read an entity record and the framebuffer pointer, and the boss preshifter writes
 * the mothership's encounter flags; every one of those globals lives in the header of the subsystem
 * that OWNS it (README.md, "Adding a function"), so they are included here to be read rather than
 * restated. collision.h and enemy.h come in for one value each: the height field's mask and the
 * byte an `Scc`/`st` stores. */
#include "collision.h"
#include "enemy.h"
#include "entity.h"
#include "mothership.h"
#include "sprite.h"
#include "util.h"
#include "video.h"

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
 * sprite_bank_build_preshift8 @ 0x153c0 — 8 call sites, all in `_start` (0x101b6, 0x10324, 0x1033a,
 * 0x10350, 0x10366, 0x1048c, 0x108d6, 0x10918).
 *
 * A whole graphic file in one call: the disk ships N frames packed end to end, and each of them has
 * to become a SPRITE_PRESHIFT_SLOTS-slot bank of its own. So the routine runs two passes over the
 * same frames. The first SPREADS them — frame i is copied from `src + i*frame_bytes` to
 * `dst + i*frame_bytes*SPRITE_PRESHIFT_SLOTS`, which is where its bank starts — and the second fans
 * each spread frame out into the seven rotations behind it, by tail-calling the 2-px preshifter at
 * its own slot 0.
 *
 * IN PLACE IS THE ONLY SHAPE THE GAME USES: all eight call sites pass `src == dst`, so the first
 * pass rewrites the file where it lies. That is safe in one direction only and it is the direction
 * the passes run: frame 0 copies onto itself, and frame i > 0 is written eight times further out
 * than any frame the pass has still to read. A backwards pass over the same buffers would eat its
 * own source.
 *
 * THE TWO PASSES DISAGREE ON THE WIDTH OF `frame_bytes`, and both readings are the original's.
 * `copy_block_words` takes it as a LONGWORD (`lsr.l #1,d2`), while the preshifter reads only its
 * low word (`move.w d2,d5`). Nothing the game passes comes near the difference — the widest is
 * 0xa0 — but the argument is a longword here because the first pass makes it one.
 * ============================================================================================= */
void sprite_bank_build_preshift8(uint8_t *image, uint32_t src, uint32_t dst, uint32_t frame_bytes,
                                 uint16_t frame_count_minus_one) {
    uint32_t bank_bytes = frame_bytes << SPRITE_PRESHIFT_SLOT_SHIFT;   /* `lsl.l #3,d3` */
    unsigned frames = loop_passes((uint16_t)(frame_count_minus_one + 1u), COUNT_MASK_WORD);
    uint32_t source = src;
    uint32_t bank = dst;

    for (unsigned frame = 0; frame < frames; frame++) {
        copy_block_words(image, source, bank, frame_bytes);
        source = addr_add(source, frame_bytes);
        bank = addr_add(bank, bank_bytes);
    }
    /* The `movem.l (a7)+` at 0x153dc restores A1 and D7 together, so the second pass starts over
     * from the bank base with the same frame count. */
    bank = dst;
    for (unsigned frame = 0; frame < frames; frame++) {
        sprite_preshift8_2px(image, bank, bank, (uint16_t)frame_bytes);
        bank = addr_add(bank, bank_bytes);
    }
}

/* ================================================================================================
 * asteroid_preshift_bank @ 0x15758 — 6 call sites (0x15720..0x15752), one per asteroid size.
 *
 * The bank arrives holding eight IDENTICAL copies of one 48x32 masked frame (the builder above it
 * at 0x156ac lays them out from the 3840-byte file at 0x1974d). This turns copies 1..7 into the
 * seven sub-cell phases by shifting frame k right by k*2 pixels — and it does that by applying a
 * ONE-pixel shift 2k times rather than by a barrel shift, which is what makes the whole routine a
 * `roxr` chain and costs it a loop it could otherwise have skipped.
 *
 * The pass count lives in D4 as a `dbf` register: `move.w #$1,d4` for the first frame and
 * `add.w #$2,d4` between frames, so frames 1..7 run 2, 4, 6, 8, 10, 12 and 14 passes.
 * ============================================================================================= */
#define PRESHIFT_1PX_PASSES_FIRST 1u  /* `move.w #$1,d4` — a dbf count, so two passes */
#define PRESHIFT_1PX_PASSES_STEP  2u  /* `add.w #$2,d4` — each frame is 2 pixels further along */

/* ONE pixel right, across a whole masked frame. Each of the five word columns is its own carry
 * chain running from cell 0 outwards, so a bit leaving one 16-pixel cell arrives in the next and
 * the sprite shifts as one image rather than as three independent cells:
 *
 *   * the MASK column starts with X set — `move.w #$1,d3 / lsr.w #1,d3` leaves the 1 in X — so the
 *     pixel the shift uncovers at the left edge is transparent (`roxr.w (a0)`);
 *   * each colour plane starts with a plain `lsr.w <ea>`, which feeds in a 0 and leaves the bit it
 *     dropped in X for the `roxr.w` on the next cell.
 *
 * Both are the same chain with a different first carry, which is why they are one loop here. */
static void shift_masked_frame_right_1px(uint8_t *image, uint32_t frame, unsigned rows,
                                         unsigned cells, uint32_t cell_bytes) {
    for (unsigned row = 0; row < rows; row++) {
        for (unsigned word = 0; word < SPRITE_MASKED_ROW_WORDS; word++) {
            unsigned carry = (word == SPRITE_MASK_WORD) ? 1u : 0u;
            /* Stepped by `cell_bytes` rather than indexed by `cell * cell_bytes`: the original's
             * three links are the fixed displacements `(a0)`, `320(a0)`, `640(a0)`, and a multiply
             * in the innermost loop of the boot path is not what they compile to. */
            uint32_t at = addr_add(frame, 2u * word);

            for (unsigned cell = 0; cell < cells; cell++) {
                uint16_t pixels = be16(image + at);

                wr16(image + at, (uint16_t)((carry << 15) | (pixels >> 1)));
                carry = pixels & 1u;
                at = addr_add(at, cell_bytes);
            }
        }
        frame = addr_add(frame, SPRITE_MASKED_ROW_BYTES);
    }
}

void asteroid_preshift_bank(uint8_t *image, uint32_t bank) {
    /* `lea 960(a0),a0` before the loop: frame 0 is the phase-0 copy and is left alone. */
    uint32_t frame = addr_add(bank, ASTEROID_FRAME_BYTES);
    uint16_t passes_reg = PRESHIFT_1PX_PASSES_FIRST;

    for (unsigned index = 1; index < SPRITE_PRESHIFT_SLOTS; index++) {
        unsigned passes = loop_passes((uint16_t)(passes_reg + 1u), COUNT_MASK_WORD);

        for (unsigned pass = 0; pass < passes; pass++)
            shift_masked_frame_right_1px(image, frame, ASTEROID_FRAME_ROWS, ASTEROID_FRAME_CELLS,
                                         ASTEROID_CELL_BYTES);
        passes_reg = (uint16_t)(passes_reg + PRESHIFT_1PX_PASSES_STEP);
        frame = addr_add(frame, ASTEROID_FRAME_BYTES);
    }
}

/* ================================================================================================
 * mothership_sprite_expand @ 0x157ca — 1 call site (0x14ee8), when a boss encounter starts.
 *
 * Lays the 64x40 file at A_mothership_sprite_source out as EIGHT IDENTICAL five-cell frames: the
 * source's four cells are copied straight across and a fifth, wholly transparent one is synthesised
 * beside them, which is the margin `mothership_sprite_preshift` then shifts the sprite into. Every
 * frame is the same because the shifting is that routine's job, not this one's — the source pointer
 * is pushed and restored around each frame (`move.l a0,-(a7)` / `movea.l (a7)+,a0`).
 *
 * The original walks five destination cursors in parallel (a1..a5, one per cell) with the source
 * running straight on, so the copy is row-major across the cells while the STORAGE is cell-major.
 * ============================================================================================= */
void mothership_sprite_expand(uint8_t *image) {
    uint32_t frame = A_mothership_sprite_bank;

    for (unsigned index = 0; index < SPRITE_PRESHIFT_SLOTS; index++) {
        /* The original walks five destination cursors (a1..a5, one per cell) and one source, all by
         * postincrement, and restores only the SOURCE between frames. Stepping them the same way
         * keeps the transcription an instruction sequence rather than a re-derivation of one, and
         * keeps the multiplies out of a 1,280-iteration loop. */
        uint32_t src = A_mothership_sprite_source;
        uint32_t row_at = frame;

        for (unsigned row = 0; row < BOSS_SPRITE_ROWS; row++) {
            uint32_t dst = row_at;

            for (unsigned cell = 0; cell < BOSS_SPRITE_SOURCE_CELLS; cell++) {
                for (unsigned word = 0; word < SPRITE_MASKED_ROW_WORDS; word++)
                    wr16(image + addr_add(dst, 2u * word), be16(image + addr_add(src, 2u * word)));
                src = addr_add(src, SPRITE_MASKED_ROW_BYTES);
                dst = addr_add(dst, BOSS_SPRITE_CELL_BYTES);
            }
            /* `move.w #$ffff,(a5)+ / clr.l (a5)+ / clr.l (a5)+` — the synthesised fifth cell. */
            wr16(image + dst, SPRITE_MASK_TRANSPARENT);
            for (unsigned word = 1; word < SPRITE_MASKED_ROW_WORDS; word++)
                wr16(image + addr_add(dst, 2u * word), 0);

            row_at = addr_add(row_at, SPRITE_MASKED_ROW_BYTES);
        }
        frame = addr_add(frame, BOSS_SPRITE_FRAME_BYTES);
    }
}

/* ================================================================================================
 * mothership_sprite_preshift @ 0x15838 — 1 call site (0x14f64, when the boss encounter opens).
 *
 * `asteroid_preshift_bank` one geometry wider, over the bank the expander above just laid out: five
 * cells 400 bytes apart, 40 rows, 2000 bytes between frames, and the same `lsr`/`roxr` carry chain
 * shifting frame k right by k*2 pixels in 2k one-pixel passes. So the two routines share
 * `shift_masked_frame_right_1px` and differ only in the four numbers they hand it and in where the
 * bank is (this one's is an immediate, so it takes no argument at all).
 *
 * IT ALSO ARMS THE ENCOUNTER on its way out, which the asteroid builder has no analogue for: four
 * bytes that belong to the mothership subsystem, three of them named in include/mothership.h and
 * the fourth borrowed into sprite.h (see the BORROWED note there). Every one of them is written
 * unconditionally after the last shift, so they double as the "the bank is ready" signal.
 * ============================================================================================= */
void mothership_sprite_preshift(uint8_t *image) {
    /* `lea 2000(a0),a0` before the loop: frame 0 is the phase-0 copy and is left alone. */
    uint32_t frame = addr_add(A_mothership_sprite_bank, BOSS_SPRITE_FRAME_BYTES);
    uint16_t passes_reg = PRESHIFT_1PX_PASSES_FIRST;

    for (unsigned index = 1; index < SPRITE_PRESHIFT_SLOTS; index++) {
        unsigned passes = loop_passes((uint16_t)(passes_reg + 1u), COUNT_MASK_WORD);

        for (unsigned pass = 0; pass < passes; pass++)
            shift_masked_frame_right_1px(image, frame, BOSS_SPRITE_ROWS, BOSS_SPRITE_FRAME_CELLS,
                                         BOSS_SPRITE_CELL_BYTES);
        passes_reg = (uint16_t)(passes_reg + PRESHIFT_1PX_PASSES_STEP);
        frame = addr_add(frame, BOSS_SPRITE_FRAME_BYTES);
    }
    image[A_boss_sequence_active] = 1;      /* the boss is painted into the playfield from now on */
    image[A_mothership_ready] = 1;
    wr32(image + A_mothership_phase_timer, 0);
    image[A_mothership_prep_stage] = 0;
}

/* ================================================================================================
 * draw_sprite_masked @ 0x15ace — 2 call sites: 0x1590e over the five `entity_boss_parts` records
 * (0x18142) with D2 = 0x3e8, and 0x159dc over the eighteen asteroid records (0x17e2a) with
 * D2 = 0x1e0.
 *
 * D2 IS HALF A PRESHIFT FRAME, which is what makes `mulu.w d2,d0` on an even sub-cell x land on the
 * right slot: slot k of a bank holds phase 2k, so phase p sits at (p/2) * frame_bytes = p * (D2).
 * The two shipped values say so out loud — 0x1e0 = 480 is half the 960-byte asteroid frame and
 * 0x3e8 = 1000 is half the 2000-byte mothership frame (sprite.h's ASTEROID_FRAME_BYTES and
 * BOSS_SPRITE_FRAME_BYTES).
 *
 * The blit itself is one 16-pixel four-plane CELL per row for `height` rows: mask word, four plane
 * words, ten source bytes a row, a whole screen row (160) between destinations. The mask word is
 * doubled into a longword (`move.w (a1),d0 / swap d0 / move.w (a1)+,d0`) so one `and.l` serves two
 * planes at a time, and a mask BIT of 1 keeps the background.
 *
 * FOUR REJECTIONS AND TWO CLIPS, in the original's own order:
 *   * x forced even, then rejected if negative or at/past 320 — the whole sprite, not just its
 *     leading edge, so a sprite leaving the right-hand side vanishes rather than wrapping;
 *   * y rejected at/past the playfield bottom, and y + height rejected at/above its top;
 *   * y ABOVE the top clips the SOURCE forward (`mulu.w #$a,d5`) and leaves the destination at the
 *     playfield's first row;
 *   * y inside the playfield clips the ROW COUNT at the bottom and steps the destination down.
 *
 * The two clips are exclusive arms of one `bge`, so a sprite that starts above the top is NOT also
 * clipped at the bottom — a tall enough one writes past the playfield's last row. That is the
 * instruction sequence, not an oversight in the transcription; no shipped height comes near it
 * (the tallest is the mothership's 40 rows).
 *
 * THE HEIGHT IS NOT MASKED HERE, and the sibling blitter at 0x15b7c masks the same field with
 * `and.w #$7fff`. So a record whose bit 15 is set reaches the `dbf` as a NEGATIVE word and the row
 * loop runs ~65536 times, exactly as a height of 0 does. Both are faithful and neither is reachable
 * from a record any spawner writes; test_sprite.py's `BLIT_FUZZ_MIN_HEIGHT` keeps the fuzz clear of
 * them and STATUS.md records them as unreachable-by-data rather than untested.
 * ============================================================================================= */
/* Where the four colour planes start in a masked row, and how the eight bytes of one screen cell
 * split: the original reads them as `move.l (a1)+` / `move.l (a1)+` after the mask word, and writes
 * `move.l d3,(a0)+` / `move.l d4,(a0)`. */
#define SPRITE_PLANES_01 (2u * (SPRITE_MASK_WORD + 1u))   /* just past the mask word */
#define SPRITE_PLANES_23 (SPRITE_PLANES_01 + 4u)
#define SPRITE_CELL_HALF (SPRITE_CELL_BYTES / SPRITE_CELL_LONGS)  /* one plane PAIR */

void draw_sprite_masked(uint8_t *image, uint32_t entity, uint16_t preshift_bytes_per_pixel) {
    uint32_t screen = be32(image + A_screen_back);
    int16_t x = (int16_t)(be16(image + addr_add(entity, ENTITY_X)) & SPRITE_X_EVEN_MASK);

    if (x < 0 || x >= (int16_t)SCREEN_PIXELS_WIDE)
        return;

    /* `mulu.w` is an unsigned 16x16 -> 32 multiply and `adda.l` takes the whole product. */
    uint32_t sprite = addr_add(be32(image + addr_add(entity, ENTITY_SPRITE)),
                               (uint32_t)(x & SPRITE_X_PHASE_MASK) * preshift_bytes_per_pixel);

    int16_t rows = (int16_t)be16(image + addr_add(entity, ENTITY_HEIGHT));
    int16_t y = (int16_t)be16(image + addr_add(entity, ENTITY_Y));
    int16_t bottom = (int16_t)(y + rows);

    if (y >= (int16_t)PLAYFIELD_BOTTOM_Y || bottom <= (int16_t)PLAYFIELD_TOP_Y)
        return;

    if (y < (int16_t)PLAYFIELD_TOP_Y) {
        int16_t hidden = (int16_t)(PLAYFIELD_TOP_Y - y);

        sprite = addr_add(sprite, (uint32_t)(uint16_t)hidden * SPRITE_MASKED_ROW_BYTES);
        rows = (int16_t)(rows - hidden);
    } else {
        if (bottom > (int16_t)PLAYFIELD_BOTTOM_Y)
            rows = (int16_t)(PLAYFIELD_BOTTOM_Y - y);
        screen = addr_add(screen, (uint32_t)(uint16_t)(y - PLAYFIELD_TOP_Y) * SCREEN_ROW_BYTES);
    }
    /* `and.w #$fff0` then `lsr.w #1` — the cell index times the eight bytes a cell occupies. The
     * original re-reads x here without the even mask, which cannot matter: the cell mask already
     * drops the bit the even mask does. `adda.w` sign-extends, and x is known to be in [0, 320). */
    screen = addr_add(screen, sign_ext16((uint16_t)((x & SPRITE_X_CELL_MASK) / 2u)));

    unsigned passes = loop_passes((uint16_t)rows, COUNT_MASK_WORD);   /* `sub.w #$1,d2` + `dbf` */
    for (unsigned row = 0; row < passes; row++) {
        uint16_t mask = be16(image + sprite);
        uint32_t keep_background = ((uint32_t)mask << 16) | mask;
        uint32_t planes01 = be32(image + addr_add(sprite, SPRITE_PLANES_01));
        uint32_t planes23 = be32(image + addr_add(sprite, SPRITE_PLANES_23));
        uint32_t under01 = be32(image + screen);
        uint32_t under23 = be32(image + addr_add(screen, SPRITE_CELL_HALF));

        wr32(image + screen, (under01 & keep_background) | planes01);
        wr32(image + addr_add(screen, SPRITE_CELL_HALF),
             (under23 & keep_background) | planes23);
        sprite = addr_add(sprite, SPRITE_MASKED_ROW_BYTES);
        screen = addr_add(screen, SCREEN_ROW_BYTES);
    }
}

/* ================================================================================================
 * draw_sprite_masked_collide @ 0x15b7c — 2 call sites: 0x11c48, which walks all twenty
 * `entity_table` records with A5 pointed at each record's own ENTITY_PIXEL_HIT byte, and 0x13096,
 * which draws record 0 of the front-end demo with A5 = 0x19ce3.
 *
 * The blitter above's sibling, and three things separate them. sprite.h's header block says why the
 * first two are what they are; the third is this routine's whole reason to exist.
 *
 *   * IT SPANS TWO CELLS. The sprite word is rotated, not shifted, so the pixels that fall off its
 *     right edge are sitting in its top bits waiting to be dropped into the next cell along. The
 *     keep-mask at `shift_mask_table` splits them, and every band below is one of the three answers
 *     to "how much of that pair is on screen".
 *   * ITS COORDINATES ARE THE WORLD'S. x 0x40 is screen column 0, so the x rejections are at 0x30
 *     and 0x180 rather than at 0 and 320, and the two partial bands either side of the playfield
 *     are real drawing rather than a reject.
 *   * IT REPORTS A PIXEL HIT. For each row it asks whether any BACKGROUND pixel with plane 2 or
 *     plane 3 set lies under an opaque sprite pixel, and if so stores 0xff (an `st`) at the address
 *     the caller passed in A5. Planes 0 and 1 are not consulted: the terrain the scroller draws is
 *     what those two high planes hold, so this is "did the sprite touch the landscape" and not "did
 *     it touch anything". The flag is a byte with two values and no counter, so a row that hits
 *     after another row already did rewrites the same 0xff.
 *
 * THE MIDDLE BAND RE-READS THE SCREEN ROW between the flag store and the composite (`movem.l (a0)`
 * runs twice there and once in each edge band). That is only observable if A5 pointed INTO the row
 * being drawn, which neither call site does — but it is the instruction sequence, so it is
 * transcribed rather than tidied away.
 * ============================================================================================= */
#define COLLIDE_SPAN_CELLS 2u   /* `movem.l (a0),#$003c` — the widest band reads two whole cells */

/* One 16-pixel screen cell of one row. `keep` is the half of the rotated sprite word that belongs
 * in THIS cell — `shift_mask_table`'s entry for the sub-cell shift, or its complement — so the
 * background survives both where the sprite is transparent (a mask bit of 1) and where the sprite's
 * pixels belong to the other cell. */
static uint32_t compose_cell(uint32_t under, uint32_t mask_pair, uint32_t planes, uint32_t keep) {
    return (under & ((mask_pair & keep) | ~keep)) | (planes & keep);
}

/* `movem.l (a0),#$003c` / `#$000c` — one screen row as `cells` cells of two longwords: planes 0+1
 * then planes 2+3. */
static void read_screen_row(const uint8_t *image, uint32_t screen, unsigned cells, uint32_t *under) {
    for (unsigned index = 0; index < cells * SPRITE_CELL_LONGS; index++)
        under[index] = be32(image + addr_add(screen, SPRITE_CELL_HALF * index));
}

static void blit_masked_collide_rows(uint8_t *image, uint32_t screen, uint32_t sprite,
                                     unsigned passes, uint32_t keep_near, unsigned cells,
                                     uint32_t hit_flag) {
    const uint32_t keep[COLLIDE_SPAN_CELLS] = { keep_near, ~keep_near };

    for (unsigned row = 0; row < passes; row++) {
        uint32_t under[COLLIDE_SPAN_CELLS * SPRITE_CELL_LONGS];
        uint16_t mask = be16(image + sprite);
        uint32_t mask_pair = ((uint32_t)mask << 16) | mask;
        uint32_t planes01, planes23;

        read_screen_row(image, screen, cells, under);
        /* Index 1 of a cell is its planes 2 and 3, and `~mask_pair` is the sprite's opaque pixels. */
        for (unsigned cell = 0; cell < cells; cell++) {
            if (under[cell * SPRITE_CELL_LONGS + 1] & ~mask_pair & keep[cell]) {
                image[hit_flag] = SCC_BYTE_TRUE;
                break;                       /* the far cell's `bra` past its own test */
            }
        }
        if (cells == COLLIDE_SPAN_CELLS)
            read_screen_row(image, screen, cells, under);   /* the second `movem.l (a0),#$003c` */

        planes01 = be32(image + addr_add(sprite, SPRITE_PLANES_01));
        planes23 = be32(image + addr_add(sprite, SPRITE_PLANES_23));
        for (unsigned cell = 0; cell < cells; cell++) {
            uint32_t at = addr_add(screen, cell * SPRITE_CELL_BYTES);
            const uint32_t *cell_under = &under[cell * SPRITE_CELL_LONGS];

            wr32(image + at, compose_cell(cell_under[0], mask_pair, planes01, keep[cell]));
            wr32(image + addr_add(at, SPRITE_CELL_HALF),
                 compose_cell(cell_under[1], mask_pair, planes23, keep[cell]));
        }
        sprite = addr_add(sprite, SPRITE_MASKED_ROW_BYTES);
        screen = addr_add(screen, SCREEN_ROW_BYTES);
    }
}

void draw_sprite_masked_collide(uint8_t *image, uint32_t entity, uint32_t hit_flag) {
    uint32_t screen = be32(image + A_screen_back);
    /* `bclr #0,d0` rather than 0x15ace's `and.w #$fffe`, which is the same forcing-to-even. */
    int16_t x = (int16_t)(be16(image + addr_add(entity, ENTITY_X)) & SPRITE_X_EVEN_MASK);
    int16_t rows = (int16_t)(be16(image + addr_add(entity, ENTITY_HEIGHT)) & ENTITY_HEIGHT_MASK);
    /* `mulu.w #$5,d2` and then `mulu.w d2,d0`: the second multiply sees only the LOW WORD of the
     * first's product, so a height past 0x3333 wraps the step. Faithful and out of reach — the
     * tallest record any spawner writes is the boss's 40 rows. */
    uint16_t phase_step = (uint16_t)((uint16_t)rows * SPRITE_COLLIDE_ROW_HALF_WORDS);
    uint32_t sprite = addr_add(be32(image + addr_add(entity, ENTITY_SPRITE)),
                               (uint32_t)(x & SPRITE_X_PHASE_MASK) * phase_step);
    int16_t y = (int16_t)be16(image + addr_add(entity, ENTITY_Y));
    int16_t bottom;
    uint32_t keep_near;
    unsigned cells;

    if (y >= (int16_t)PLAYFIELD_BOTTOM_Y)
        return;
    bottom = (int16_t)(y + rows);
    if (bottom <= (int16_t)PLAYFIELD_TOP_Y)
        return;

    /* The same two exclusive clip arms as 0x15ace, and the same consequence: a sprite that starts
     * above the playfield's top is NOT also clipped at its bottom. */
    if (y < (int16_t)PLAYFIELD_TOP_Y) {
        int16_t hidden = (int16_t)(PLAYFIELD_TOP_Y - y);

        sprite = addr_add(sprite, (uint32_t)(uint16_t)hidden * SPRITE_MASKED_ROW_BYTES);
        rows = (int16_t)(rows - hidden);
    } else {
        if (bottom > (int16_t)PLAYFIELD_BOTTOM_Y)
            rows = (int16_t)(PLAYFIELD_BOTTOM_Y - y);
        screen = addr_add(screen, (uint32_t)(uint16_t)(y - PLAYFIELD_TOP_Y) * SCREEN_ROW_BYTES);
    }
    /* The original re-reads x from the record here, and forces it even a second time, before
     * indexing the keep-mask table — the same value, read twice. */
    keep_near = be32(image + addr_add(A_shift_mask_table,
                                      (uint32_t)(x & SPRITE_X_PHASE_MASK) * SPRITE_SHIFT_MASK_STRIDE));
    cells = COLLIDE_SPAN_CELLS;

    if (x < (int16_t)SPRITE_COLLIDE_ORIGIN_X) {
        if (x <= (int16_t)SPRITE_COLLIDE_LEFT_EDGE)
            return;
        /* Straddling the left edge: only the half that rotated OUT of the sprite's own cell is on
         * screen, and it lands in column 0 — so the row is left where the y clip put it. */
        keep_near = ~keep_near;
        cells = 1;
    } else if (x <= (int16_t)SPRITE_COLLIDE_RIGHT_EDGE) {
        /* `and.w #$fff0` then `lsr.w #1` — the cell index times the eight bytes a cell occupies. */
        screen = addr_add(screen,
                          sign_ext16((uint16_t)(((uint16_t)(x - SPRITE_COLLIDE_ORIGIN_X)
                                                 & SPRITE_X_CELL_MASK) >> 1)));
    } else if (x >= (int16_t)SPRITE_COLLIDE_RIGHT_OFF) {
        return;
    } else {
        /* Straddling the right edge: only the sprite's own half fits, in the row's last cell. */
        screen = addr_add(screen, SCREEN_ROW_BYTES - SPRITE_CELL_BYTES);
        cells = 1;
    }
    blit_masked_collide_rows(image, screen, sprite,
                             loop_passes((uint16_t)rows, COUNT_MASK_WORD),   /* `subq.w #1` + `dbf` */
                             keep_near, cells, hit_flag);
}

/* ================================================================================================
 * Glue. Register map for the first three: A0 = source, A1 = destination, D2 = frame length in bytes
 * (`ship_sprite_deinterleave` has no D2 — its geometry is fixed). The preshift builders return A1.
 * `asteroid_preshift_bank` takes A0 = the bank; `mothership_sprite_expand` takes nothing, both its
 * addresses being absolute.
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

void g_asteroid_preshift_bank(uint8_t *image, uint32_t bank) {
    asteroid_preshift_bank(image, bank);
}

void g_mothership_sprite_expand(uint8_t *image) {
    mothership_sprite_expand(image);
}

/* A2 = the entity record, D2 = half a preshift frame. */
void g_draw_sprite_masked(uint8_t *image, uint32_t entity, uint32_t preshift_bytes_per_pixel) {
    draw_sprite_masked(image, entity, (uint16_t)preshift_bytes_per_pixel);
}

/* A0 = the packed frames, A1 = the bank base, D2 = one frame's length in bytes (a LONGWORD — the
 * copy pass reads all 32 bits of it, the preshift pass only the low word), D7 = frames - 1. */
void g_sprite_bank_build_preshift8(uint8_t *image, uint32_t src, uint32_t dst, uint32_t frame_bytes,
                                   uint32_t frame_count_minus_one) {
    sprite_bank_build_preshift8(image, src, dst, frame_bytes, (uint16_t)frame_count_minus_one);
}

/* No arguments: the bank is an immediate and so are the four flags it arms. */
void g_mothership_sprite_preshift(uint8_t *image) {
    mothership_sprite_preshift(image);
}

/* A2 = the entity record, A5 = the address of the byte a pixel hit sets. */
void g_draw_sprite_masked_collide(uint8_t *image, uint32_t entity, uint32_t hit_flag) {
    draw_sprite_masked_collide(image, entity, hit_flag);
}
