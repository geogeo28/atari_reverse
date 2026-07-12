/* graphics.c — GRAPHICS.GRA decompression (unpack_graphics @ 0x10620).
 *
 * The loaded GRAPHICS.GRA (at buf_c + 0xc350) is: a 3328-byte header, then an RLE pixel stream.
 * unpack_graphics stashes the header, RLE-decodes the stream, shifts the decoded block into
 * place, de-interleaves eight 4-plane screens, compacts a couple of regions, and finally builds
 * the sprite-shift tables (from the stashed header). Reconstructed end to end, to its rts.
 *
 * All offsets are taken from the disassembly, not the Ghidra decomp (whose undefined4* pointer
 * arithmetic scales every displacement by 4). Buffers keep the game's layout so the baked-in
 * overlaps hold: buf_b == buf_c - 0xd000, buf_aux == buf_c + 0x3a9a0.
 */
#include <string.h>
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

#define GFX_HEADER_DST    28000     /* buf_aux + this: where the header block is stashed */
#define GFX_HEADER_BYTES  3328      /* 0x19f+1 groups * 8 bytes copied aside before decoding */
#define GFX_RLE_SRC       0xd050    /* buf_c + this: compressed pixel stream (past the header) */
#define GFX_RLE_DST       0xd000    /* buf_c - this: RLE output start (== buf_b) */
#define GFX_DECODED_BYTES 0x3e800   /* 256000: decoded block, shifted up to buf_c */
#define GFX_SCREEN_BYTES  32000     /* one 4-plane screen (320x200x4bpp) */
#define GFX_PLANE_BYTES   8000      /* one bit-plane within a screen */
#define GFX_SCREENS       8
#define GFX_COMPACT_PAIRS 2000      /* phase E: 2000 * 2 kept longwords over buf_c[32000..64000) */
#define GFX_TAIL_DST      48000     /* phase F: move buf_c[64000..) down to buf_c[48000..) */
#define GFX_TAIL_SRC      64000
#define GFX_TAIL_BYTES    192000
#define RLE_ZERO_RUN      0x1234u   /* marker: run of 0x0000 words */
#define RLE_FF_RUN        0x5678u   /* marker: run of 0xffff words */
#define RLE_END           ((RLE_ZERO_RUN << 16) | RLE_ZERO_RUN)  /* 0x12341234: end-of-stream long */

/* RLE stream: a 0x1234 / 0x5678 marker is followed by a word count and expands to count+1 fill
 * words (0x0000 / 0xffff); a zero count instead writes the marker word itself as a literal. Any
 * other word is a literal. The stream ends at a 0x1234 immediately followed by the long RLE_END.
 * Decode words from src into dst. */
static void gfx_rle_decode(uint8_t *mem, uint32_t src, uint32_t dst) {
    for (;;) {
        uint16_t word = be16(mem + src); src += 2;
        if (word == RLE_ZERO_RUN && be32(mem + src) == RLE_END) return;       /* end marker */
        if (word == RLE_ZERO_RUN || word == RLE_FF_RUN) {
            uint16_t fill = (word == RLE_FF_RUN) ? 0xffff : 0x0000;
            uint16_t count = be16(mem + src); src += 2;
            if (count == 0) { wr16(mem + dst, word); dst += 2; }              /* literal escape */
            else for (uint32_t i = 0; i <= count; i++) { wr16(mem + dst, fill); dst += 2; }
        } else {
            wr16(mem + dst, word); dst += 2;                                  /* literal */
        }
    }
}

/* De-interleave the eight screens. Each screen is 4 planes of 8000 bytes stored contiguously at
 * buf_c[screen*32000 + plane*8000]; produce chunky words {p0,p1,p2,p3} in buf_b, then copy the
 * 32000 bytes back over the screen in place. */
static void gfx_deinterleave(uint8_t *mem, uint32_t buf_c, uint32_t buf_b) {
    for (int screen = 0; screen < GFX_SCREENS; screen++) {
        uint32_t s = buf_c + (uint32_t)screen * GFX_SCREEN_BYTES;
        uint32_t d = buf_b;
        for (int group = 0; group < GFX_PLANE_BYTES / 2; group++) {           /* 4000 word-groups */
            wr16(mem + d + 0, be16(mem + s + 0 * GFX_PLANE_BYTES));
            wr16(mem + d + 2, be16(mem + s + 1 * GFX_PLANE_BYTES));
            wr16(mem + d + 4, be16(mem + s + 2 * GFX_PLANE_BYTES));
            wr16(mem + d + 6, be16(mem + s + 3 * GFX_PLANE_BYTES));
            s += 2; d += 8;
        }
        memcpy(mem + buf_c + (uint32_t)screen * GFX_SCREEN_BYTES, mem + buf_b, GFX_SCREEN_BYTES);
    }
}

/* Compact buf_c[32000..64000): keep the first longword of each 8-byte pair, drop the second,
 * writing the kept 16000 bytes back at buf_c+32000. */
static void gfx_compact(uint8_t *mem, uint32_t buf_c) {
    uint32_t src = buf_c + GFX_SCREEN_BYTES, dst = buf_c + GFX_SCREEN_BYTES;
    for (int i = 0; i < GFX_COMPACT_PAIRS; i++)
        for (int j = 0; j < 2; j++) { wr32(mem + dst, be32(mem + src)); src += 8; dst += 4; }
}

/* unpack_graphics @ 0x10620 — reads buf_c / buf_b / buf_aux from their globals. */
#define GFX_SPRITE_COUNT 0xcf     /* build_sprite_shifts count arg (D5): 208 sprites */
/* The seven masked builds unpack_graphics issues, as (buf_b offset, source offset, count-1). */
static const struct { uint16_t dst_off, src_off, count; } GFX_MSK_BUILDS[] = {
    {0x14f0, 0x140, 0x13}, {0x3cf0, 0x3c0, 0x13}, {0x6cf0, 0x6c0, 0x13},
    {0x94f0, 0x940, 0x13}, {0x52f0, 0x520, 0x01}, {0x56f0, 0x560, 0x01},
    {0xbcf0, 0xbc0, 0x13},
};

void g_unpack_graphics(uint8_t *image) {
    uint32_t buf_c = be32(image + A_buf_c);
    uint32_t buf_b = be32(image + A_buf_b);
    uint32_t buf_aux = be32(image + A_buf_aux);

    memcpy(image + buf_aux + GFX_HEADER_DST, image + buf_c + GFX_LOAD_OFFSET, GFX_HEADER_BYTES);
    gfx_rle_decode(image, buf_c + GFX_RLE_SRC, buf_c - GFX_RLE_DST);
    memmove(image + buf_c, image + buf_c - GFX_RLE_DST, GFX_DECODED_BYTES);
    gfx_deinterleave(image, buf_c, buf_b);
    gfx_compact(image, buf_c);
    memmove(image + buf_c + GFX_TAIL_DST, image + buf_c + GFX_TAIL_SRC, GFX_TAIL_BYTES);
    /* G: build the sprite pre-shift tables from the stashed header (see below). */
    g_build_sprite_shifts(image, GFX_SPRITE_COUNT);
    for (unsigned i = 0; i < sizeof GFX_MSK_BUILDS / sizeof GFX_MSK_BUILDS[0]; i++)
        g_build_sprite_shifts_msk(image, GFX_MSK_BUILDS[i].dst_off,
                                  GFX_MSK_BUILDS[i].src_off, GFX_MSK_BUILDS[i].count);
}

/* ---- sprite pre-shift tables (build_sprite_shifts @0x1078c, _msk @0x107f2) ------------
 * Both read a 16-byte source group per sprite (from the stashed header at buf_aux+0x6d60) as
 * four 32-bit plane accumulators — plane k = word[k] : word[k+4] (high : low) — and emit 16
 * progressively-shifted copies into buf_b. Each stored shift is 8 words: the four plane words
 * at +0..6, and the four shifted-out (overflow) words at +8..14. */
#define SPRITE_SRC_OFF   GFX_HEADER_DST   /* sprite source = the header stash at buf_aux+0x6d60 */
#define SPRITE_SHIFTS    16               /* pre-shift positions per sprite */
#define SPRITE_SRC_STEP  16               /* source bytes consumed per sprite */
#define SPRITE_MSK_STEP  0x200            /* buf_b advance per sprite in the _msk variant */

static void load_planes(const uint8_t *mem, uint32_t src, uint32_t plane[4]) {
    for (int k = 0; k < 4; k++)
        plane[k] = ((uint32_t)be16(mem + src + 2 * k) << 16) | be16(mem + src + 8 + 2 * k);
}

/* Store one shift position at dst: plane word (high half) at +2k, overflow (low half) at +8+2k. */
static void store_shift(uint8_t *mem, uint32_t dst, const uint32_t plane[4]) {
    for (int k = 0; k < 4; k++) {
        wr16(mem + dst + 2 * k, (uint16_t)(plane[k] >> 16));
        wr16(mem + dst + 8 + 2 * k, (uint16_t)plane[k]);
    }
}

/* build_sprite_shifts @0x1078c — D5 = sprite count (minus one). Emits count+1 sprites' shift
 * tables contiguously into buf_b; each shift step is an arithmetic right shift (asr.l #1). */
void g_build_sprite_shifts(uint8_t *image, uint32_t count) {
    uint32_t src = be32(image + A_buf_aux) + SPRITE_SRC_OFF;
    uint32_t dst = be32(image + A_buf_b);
    for (uint32_t sprite = 0; sprite <= (count & 0xffff); sprite++) {
        uint32_t plane[4];
        load_planes(image, src, plane);
        for (int shift = 0; shift < SPRITE_SHIFTS; shift++) {
            store_shift(image, dst, plane);
            for (int k = 0; k < 4; k++) plane[k] = (uint32_t)((int32_t)plane[k] >> 1);  /* asr.l */
            dst += 16;
        }
        src += SPRITE_SRC_STEP;
    }
}

/* build_sprite_shifts_msk @0x107f2 — D0 = buf_b byte offset, D1 = source byte offset (word,
 * sign-extended), D5 = count-1. Same layout, but the mask shift is left-with-sticky-bit-0
 * ((p<<1)|(p&1)) and the 16 shifts are written *downward* (dst -= 16), the block base rising
 * by 0x200 per sprite. */
void g_build_sprite_shifts_msk(uint8_t *image, uint32_t dst_off, uint32_t src_off, uint32_t count) {
    uint32_t src = be32(image + A_buf_aux) + SPRITE_SRC_OFF + sign_ext16(src_off);
    uint32_t dst = be32(image + A_buf_b) + (dst_off & 0xffff);
    for (uint32_t sprite = 0; sprite <= (count & 0xffff); sprite++) {
        uint32_t plane[4];
        load_planes(image, src, plane);
        for (int shift = 0; shift < SPRITE_SHIFTS; shift++) {
            store_shift(image, dst, plane);
            for (int k = 0; k < 4; k++) plane[k] = (plane[k] << 1) | (plane[k] & 1u);
            dst -= 16;
        }
        dst += SPRITE_MSK_STEP;
        src += SPRITE_SRC_STEP;
    }
}