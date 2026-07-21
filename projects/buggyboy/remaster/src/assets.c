/* assets.c — decompress GRAPHICS.GRA into the arena (see include/assets.h for the layout).
 *
 * The file is a 3328-byte header followed by an RLE pixel stream. Unpacking runs seven phases, in
 * order, each consuming the previous one's output in place:
 *
 *   A  stash the header aside (the sprite pre-shift tables are built from it in G/H, long after
 *      the decoded pixels have overwritten where it was loaded)
 *   B  RLE-decode the stream into the scratch region
 *   C  slide the decoded block up to the graphics base
 *   D  de-interleave eight 4-plane screens (planar -> chunky), bouncing through scratch
 *   E  compact the second screen's span, keeping one longword per pair
 *   F  slide the tail down over the gap that compaction opened
 *   G  build 208 sprites' pre-shift tables from the stashed header
 *   H  build seven more with the mask variant's shift rule
 *
 * Ported from the verified recreate/src/graphics.c (`g_unpack_graphics` @0x10620), which is proven
 * byte-exact against the 68000; test/test_assets.py pins this port against it over the whole arena.
 */
#include <string.h>

#include "assets.h"
#include "st.h"

/* ---- phase A: the header stash --------------------------------------------------------------
 * The 0x19f+1 sprite groups at the head of the file, copied into the aux region before the decode
 * overruns them. Phases G/H read the sprite-shift source groups back from here. */
#define GFX_HEADER_BYTES     3328
#define GFX_HEADER_STASH_OFF 28000   /* aux + this: where the header block lives afterwards */

/* ---- phase B: the RLE stream ---------------------------------------------------------------- */
#define GFX_RLE_SRC_OFF   (RM_GFX_LOAD_OFF + GFX_HEADER_BYTES)  /* gfx + this: the stream itself */
#define GFX_DECODED_BYTES 0x3e800    /* 256000: what the stream expands to */
#define RLE_ZERO_RUN      0x1234u    /* marker: a run of 0x0000 words */
#define RLE_FF_RUN        0x5678u    /* marker: a run of 0xffff words */
#define RLE_END           ((RLE_ZERO_RUN << 16) | RLE_ZERO_RUN)  /* the end-of-stream long */

/* ---- phase D: the screens -------------------------------------------------------------------- */
#define GFX_SCREENS      8
#define GFX_SCREEN_BYTES 32000       /* one 4-plane 320x200 screen */
#define GFX_PLANE_BYTES  8000        /* one bit-plane within a screen */
#define GFX_PLANES       4

/* ---- phases E/F: compaction and the tail slide ----------------------------------------------- */
#define GFX_COMPACT_LONGS 4000       /* longwords kept over gfx[32000..64000), one per 8-byte pair */
#define GFX_TAIL_DST      48000      /* the compacted span ends here... */
#define GFX_TAIL_SRC      64000      /* ...so everything from here slides down onto it */
#define GFX_TAIL_BYTES    192000

/* ---- phases G/H: the sprite pre-shift tables --------------------------------------------------
 * Each sprite is pre-rendered at all 16 fine-x positions so a blit is a plain copy. One source
 * group is four 32-bit plane accumulators, each assembled from a high and a low word 8 bytes apart;
 * every shift position stores the four plane words followed by the four shifted-out overflow words. */
#define SPRITE_COUNT_M1  0xcf        /* 208 sprites, expressed as the original's count-1 */
#define SPRITE_SHIFTS    16          /* pre-shift positions per sprite */
#define SPRITE_SRC_STEP  16          /* header bytes consumed per sprite */
#define SPRITE_STORE_BYTES 16        /* bytes one shift position occupies */
#define SPRITE_MSK_STEP  0x200       /* the mask variant's per-sprite advance */

/* The seven masked builds, as (scratch offset, header offset, count-1). */
static const struct { uint16_t dst_off, src_off, count_m1; } GFX_MSK_BUILDS[] = {
    {0x14f0, 0x140, 0x13}, {0x3cf0, 0x3c0, 0x13}, {0x6cf0, 0x6c0, 0x13},
    {0x94f0, 0x940, 0x13}, {0x52f0, 0x520, 0x01}, {0x56f0, 0x560, 0x01},
    {0xbcf0, 0xbc0, 0x13},
};
#define GFX_MSK_BUILD_COUNT (sizeof GFX_MSK_BUILDS / sizeof GFX_MSK_BUILDS[0])

void rm_arena_init(RmArena *arena, uint8_t *block) {
    arena->base    = block;
    arena->course  = block + RM_COURSE_OFF;
    arena->tables  = block + RM_TABLES_OFF;
    arena->scratch = block + RM_SCRATCH_OFF;
    arena->gfx     = block + RM_GFX_OFF;
    arena->aux     = block + RM_AUX_OFF;
}

/* Decode the RLE stream at `src` into `dst`. A 0x1234 / 0x5678 marker is followed by a word count
 * and expands to count+1 fill words (0x0000 / 0xffff); a zero count instead emits the marker word
 * itself, which is how those two values appear as literals. Any other word is a literal. The stream
 * ends at a 0x1234 immediately followed by RLE_END.
 *
 * `dst` trails `src` by 0x1a050 bytes and the whole stream expands by less than that, so the write
 * cursor never overtakes the read cursor — which is why the decode can run in place. */
static void rle_decode(const uint8_t *src, uint8_t *dst) {
    for (;;) {
        uint16_t word = be16(src); src += 2;
        if (word == RLE_ZERO_RUN && be32(src) == RLE_END) return;
        if (word != RLE_ZERO_RUN && word != RLE_FF_RUN) {
            wr16(dst, word); dst += 2;                       /* literal */
            continue;
        }
        uint16_t fill = (word == RLE_FF_RUN) ? 0xffff : 0x0000;
        uint16_t count = be16(src); src += 2;
        if (count == 0) {
            wr16(dst, word); dst += 2;                       /* escaped marker-as-literal */
        } else {
            for (uint32_t i = 0; i <= count; i++) { wr16(dst, fill); dst += 2; }
        }
    }
}

/* Phase D. Each screen arrives as four contiguous 8000-byte bit-planes; the blitters want chunky
 * 4-plane groups {p0,p1,p2,p3}. Interleave into `scratch`, then copy back over the screen. */
static void deinterleave_screens(uint8_t *gfx, uint8_t *scratch) {
    for (int screen = 0; screen < GFX_SCREENS; screen++) {
        uint8_t *src = gfx + (uint32_t)screen * GFX_SCREEN_BYTES;
        uint8_t *dst = scratch;
        for (int group = 0; group < GFX_PLANE_BYTES / 2; group++) {
            for (int plane = 0; plane < GFX_PLANES; plane++)
                wr16(dst + 2 * plane, be16(src + plane * GFX_PLANE_BYTES));
            src += 2;
            dst += 2 * GFX_PLANES;
        }
        memcpy(gfx + (uint32_t)screen * GFX_SCREEN_BYTES, scratch, GFX_SCREEN_BYTES);
    }
}

/* Phase E. Over gfx[32000..64000) keep the first longword of every 8-byte pair, dropping the
 * second, and write the kept 16000 bytes back from the span's start. */
static void compact_pairs(uint8_t *gfx) {
    const uint8_t *src = gfx + GFX_SCREEN_BYTES;
    uint8_t *dst = gfx + GFX_SCREEN_BYTES;
    for (int i = 0; i < GFX_COMPACT_LONGS; i++) {
        wr32(dst, be32(src));
        src += 8;
        dst += 4;
    }
}

/* Load one sprite's four plane accumulators: plane k is word[k] (high half) : word[k+4] (low). */
static void load_planes(const uint8_t *src, uint32_t plane[GFX_PLANES]) {
    for (int k = 0; k < GFX_PLANES; k++)
        plane[k] = ((uint32_t)be16(src + 2 * k) << 16) | be16(src + 2 * GFX_PLANES + 2 * k);
}

/* Store one shift position: the four plane words at +0..6, the four overflow words at +8..14. */
static void store_shift(uint8_t *dst, const uint32_t plane[GFX_PLANES]) {
    for (int k = 0; k < GFX_PLANES; k++) {
        wr16(dst + 2 * k, (uint16_t)(plane[k] >> 16));
        wr16(dst + 2 * GFX_PLANES + 2 * k, (uint16_t)plane[k]);
    }
}

/* Phase G — the pixel sprites. Emit `count_m1`+1 sprites' shift tables contiguously from the start
 * of scratch, each step an arithmetic right shift (the pixels walk right, sign-filling from the
 * left edge). */
static void build_sprite_shifts(const uint8_t *header, uint8_t *scratch, uint32_t count_m1) {
    const uint8_t *src = header;
    uint8_t *dst = scratch;
    for (uint32_t sprite = 0; sprite <= count_m1; sprite++) {
        uint32_t plane[GFX_PLANES];
        load_planes(src, plane);
        for (int shift = 0; shift < SPRITE_SHIFTS; shift++) {
            store_shift(dst, plane);
            for (int k = 0; k < GFX_PLANES; k++) plane[k] = (uint32_t)((int32_t)plane[k] >> 1);
            dst += SPRITE_STORE_BYTES;
        }
        src += SPRITE_SRC_STEP;
    }
}

/* Phase H — the masks. Same table shape, but a mask shifts left with a sticky bit 0 (so the mask
 * grows rather than sign-filling) and the 16 positions are written *downward* from the block's
 * offset, the block base rising by SPRITE_MSK_STEP per sprite. */
static void build_mask_shifts(const uint8_t *header, uint8_t *scratch,
                              uint16_t dst_off, uint16_t src_off, uint32_t count_m1) {
    const uint8_t *src = header + sx16(src_off);
    uint8_t *dst = scratch + dst_off;
    for (uint32_t sprite = 0; sprite <= count_m1; sprite++) {
        uint32_t plane[GFX_PLANES];
        load_planes(src, plane);
        for (int shift = 0; shift < SPRITE_SHIFTS; shift++) {
            store_shift(dst, plane);
            for (int k = 0; k < GFX_PLANES; k++) plane[k] = (plane[k] << 1) | (plane[k] & 1u);
            dst -= SPRITE_STORE_BYTES;
        }
        dst += SPRITE_MSK_STEP;
        src += SPRITE_SRC_STEP;
    }
}

void rm_assets_unpack(RmArena *arena) {
    uint8_t *gfx = arena->gfx;
    uint8_t *scratch = arena->scratch;
    uint8_t *header = arena->aux + GFX_HEADER_STASH_OFF;

    memcpy(header, gfx + RM_GFX_LOAD_OFF, GFX_HEADER_BYTES);                        /* A */
    rle_decode(gfx + GFX_RLE_SRC_OFF, scratch);                                     /* B */
    memmove(gfx, scratch, GFX_DECODED_BYTES);                                       /* C */
    deinterleave_screens(gfx, scratch);                                             /* D */
    compact_pairs(gfx);                                                             /* E */
    memmove(gfx + GFX_TAIL_DST, gfx + GFX_TAIL_SRC, GFX_TAIL_BYTES);                /* F */
    build_sprite_shifts(header, scratch, SPRITE_COUNT_M1);                          /* G */
    for (unsigned i = 0; i < GFX_MSK_BUILD_COUNT; i++)                              /* H */
        build_mask_shifts(header, scratch, GFX_MSK_BUILDS[i].dst_off,
                          GFX_MSK_BUILDS[i].src_off, GFX_MSK_BUILDS[i].count_m1);
}
