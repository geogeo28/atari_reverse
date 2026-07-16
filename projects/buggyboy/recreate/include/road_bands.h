/* road_bands.h — shared internals of the render_road band pipeline.
 *
 * render_road (the pseudo-3D road rasterizer @0x19144) is drawn in seven `dbf` bands over a shared
 * cursor set (rr_regs). Two implementations of the bands exist and are each verified byte-for-byte
 * against the Musashi oracle:
 *   - the byte-exact 1:1 machine model (the trust anchor) — src/machine/road.c;
 *   - the idiomatic proper-C recreation (the default g_render_road)  — src/road.c.
 * Both drive the SAME pipeline (render_road_impl) and use the SAME 68000-faithful word/blit
 * primitives, which live here so the two layers cannot drift apart.
 */
#ifndef BB_ROAD_BANDS_H
#define BB_ROAD_BANDS_H

#include "machine.h"
#include "addrs.h"
#include "draw.h"

/* ---- entry setup (0x19144-0x9170) ---- */
#define RR_DST_ROAD_OFF   0x4100     /* a2 = draw_buffer + this: top of the on-screen road band */
#define RR_PARAM_TBL      0x1623a    /* a4: per-scanline perspective-offset param stream */
#define RR_EDGE_TBL_BASE  0x15c3a    /* a6 base: per-scanline edge/run table */
#define RR_WIDTH_TBL      0x18f24    /* a5 = road_width_tbl (reset at each band group) */

/* ---- inter-band group step (0x93ac / 0x956e / 0x9868) ---- */
#define RR_DST_BAND_STEP  0x3c00     /* a2 -= this between band groups (rewind up the screen) */
#define RR_SRC_BAND_STEP  0x0a00     /* a3 += this between band groups (next texture sub-block) */
#define RR_EDGE_BAND_STEP 0x00c0     /* a6 -= this between band groups */

/* ---- per-scanline edge-mask reads (d3 = *(a1 + off), a1 = buf_b + fine_x) ---- */
#define RR_MASK_OFF_HI    0x2808     /* bands A/B */
#define RR_MASK_OFF_LO    0x2800     /* bands C/D */

/* ---- control-longword flag bits (btst #n on long d0); each selects a blit variant / src region -- */
#define RR_F_MASK_A       (1u << 16) /* band B: read edge mask, clear left fill (d5=0) */
#define RR_F_SPLIT_B      (1u << 17) /* bands B: row has an edge split (else full-width fill) */
#define RR_F_SPLIT_A      (1u << 18) /* band A:  edge split present (else center-run) */
#define RR_F_SPLIT_C      (1u << 19) /* bands C: edge split present */
#define RR_F_SPLIT_D      (1u << 20) /* bands D: edge split present */
#define RR_F_SRC_400      (1u << 21) /* src sub-offset selector (+0x400) */
#define RR_F_SRC_100      (1u << 22) /* src sub-offset selector (+0x100) / fill-side selector */
#define RR_F_WIDE         (1u << 23) /* wide/solid centre branch (vs the edge-split blit) */
#define RR_F_MASK_A2      (1u << 24) /* bands D: read edge mask (near group) */
#define RR_F_PLANE_HI     (1u << 27) /* swap d6 (hi plane pattern) and select an alternate src region */
#define RR_F_SRC_CONST    (1u << 28) /* select the const edge texture at 0x5baa (when d0 >= 0) */
#define RR_F_SKIP_ABC     (1u << 29) /* bands A/B: gate for the edge-split fast path */
#define RR_F_SKIP_D       (1u << 30) /* bands C/D: gate for the edge-split fast path */

/* ---- const edge textures near buf_b (image-absolute), selected per the flags ---- */
#define RR_CONST_5B7A     0x15b7a
#define RR_CONST_5B9A     0x15b9a
#define RR_CONST_5BAA     0x15baa
/* ---- src sub-region deltas added to a1 (= buf_b + fine_x) per the flags ---- */
#define RR_SRC_A800       0xa800u
#define RR_SRC_5800       0x5800
#define RR_SRC_5000       0x5000
#define RR_SRC_4700       0x4700
#define RR_SRC_3E00       0x3e00
#define RR_SRC_3500       0x3500
#define RR_SRC_0A00       0x0a00
#define RR_SRC_0400       0x0400
#define RR_SRC_0100       0x0100

#define RR_D7_WORD_MASK   0xfff8     /* d7 (bands B/C/D): masks d0.w to a column-aligned offset */
#define RR_ROW_STRIDE_D2  0x00a0     /* d2 = ROW_STRIDE (160 bytes / scanline) at band entry */

/* Threaded 68000 registers that survive band-to-band (bands B/C/D share these across two loops each). */
typedef struct { uint8_t *img; uint32_t a2, a3, a4, a5, a6, d2, d7; } rr_regs;

/* 68000 register-op helpers (word ops touch only the low 16 bits). */
static inline uint32_t rr_wset(uint32_t r, uint16_t low) { return (r & 0xffff0000u) | low; } /* set low word */
static inline int16_t  rr_ws(uint32_t r)  { return (int16_t)(uint16_t)r; }                   /* low word, signed */
static inline uint32_t rr_moveq(int8_t b) { return (uint32_t)(int32_t)b; }                   /* moveq: sign-extend byte */
static inline uint32_t rr_notw(uint32_t r){ return rr_wset(r, (uint16_t)~(uint16_t)r); }     /* not.w */
static inline uint32_t rr_clrw(uint32_t r){ return r & 0xffff0000u; }                        /* clr.w */
static inline uint32_t rr_swap(uint32_t r){ return (r << 16) | (r >> 16); }                  /* swap */
/* dbf dN,label: decrement dN's low word; loop while the result != -1 (0xffff). Returns true to loop. */
static inline int rr_dbf(uint32_t *r) { uint16_t w = (uint16_t)(*r) - 1; *r = rr_wset(*r, w); return w != 0xffff; }
/* signed low-word result of a 68k word op (sub.w / add.w) — wraps mod 2^16, then bit-15 sign. */
static inline int16_t rr_wsub(uint16_t a, uint16_t b) { return (int16_t)(uint16_t)(a - b); }
static inline int16_t rr_wadd(uint16_t a, uint16_t b) { return (int16_t)(uint16_t)(a + b); }

/* ---- blit primitives shared by every band. a0 = dst cursor, a1 = src cursor; both post-increment
 * like the 68k `(an)+` addressing. ---- */

/* move.l (a1)+,(a0)+ : copy one long (half a 4-plane, 16-pixel column) src->dst, advance both. */
static inline void rr_copy_long(uint8_t *img, uint32_t *a0, uint32_t *a1) {
    wr32(img + *a0, be32(img + *a1)); *a1 += 4; *a0 += 4;
}
/* move.l (a1)+,(a0); and.l d3,(a0)+ : copy one long masked by the full-long edge mask d3 (A/C/E). */
static inline void rr_copy_long_masked(uint8_t *img, uint32_t *a0, uint32_t *a1, uint32_t d3) {
    wr32(img + *a0, be32(img + *a1) & d3); *a1 += 4; *a0 += 4;
}
/* move.l d5,(a0)+; move.l d6,(a0)+ : write one forward shoulder-fill pair (interior/edge planes). */
static inline void rr_fill_pair(uint8_t *img, uint32_t *a0, uint32_t d5, uint32_t d6) {
    wr32(img + *a0, d5); *a0 += 4; wr32(img + *a0, d6); *a0 += 4;
}
/* move.l d6,-(a0); move.l d5,-(a0) : write one backward shoulder-fill pair (tail fill, predecrement). */
static inline void rr_fill_pair_rev(uint8_t *img, uint32_t *a0, uint32_t d5, uint32_t d6) {
    *a0 -= 4; wr32(img + *a0, d6); *a0 -= 4; wr32(img + *a0, d5);
}
/* Fill one full 160-byte road row forward through a2 (the 68k `moveq #9,d1; dbf` loop of ten
 * (d5,d6,d5,d6) writes). d1 is left dead by the original at every call site, so we don't model it. */
static inline void rr_fill_full_row(uint8_t *img, uint32_t *a2, uint32_t d5, uint32_t d6) {
    for (int i = 0; i < 10; i++) { rr_fill_pair(img, a2, d5, d6); rr_fill_pair(img, a2, d5, d6); }
}
/* Word memory RMW: word[addr] &= d3.w  (68k `and.w d3,-4(a0)` masks only the high word of a long). */
static inline void rr_andw(uint8_t *img, uint32_t addr, uint32_t d3) {
    wr16(img + addr, (uint16_t)(be16(img + addr) & (uint16_t)d3));
}

/* One selectable set of band implementations. Layer 1 (machine model) is the byte-exact anchor;
 * the Layer-2 table swaps in the idiomatic recreations. Both drive render_road_impl below. */
typedef struct {
    void (*band_A)(rr_regs *r);
    void (*band_B)(rr_regs *r, uint32_t rows_m1, int second);
    void (*band_C_near)(rr_regs *r, uint32_t rows_m1);
    void (*band_C_far)(rr_regs *r, uint32_t rows_m1);
    void (*band_D)(rr_regs *r, uint32_t rows_m1, int second);
} rr_bands;

/* Inter-band-group step (0x93ac / 0x956e / 0x9868): rewind dst up the screen, advance the source to
 * the next texture sub-block and the edge table down, and reset the width-table cursor to its base. */
static inline void rr_group_step(rr_regs *r) {
    r->a2 -= RR_DST_BAND_STEP;
    r->a3 += RR_SRC_BAND_STEP;
    r->a6 -= RR_EDGE_BAND_STEP;
    r->a5 = RR_WIDTH_TBL;
}

/* The seven-band pipeline (0x9172..0x9a3c). a4 streams monotonically across all bands; a5/a6/d7 are
 * reset at each group step. Band A runs alone; B/C/D each run a near then a far copy per group.
 * The `b` table selects which implementation (machine model or idiomatic) draws each band. */
static inline void render_road_impl(uint8_t *image, const rr_bands *b) {
    rr_regs r = {
        .img = image,
        .a2  = draw_buffer(image) + RR_DST_ROAD_OFF,
        .a3  = be32(image + A_buf_b),
        .a4  = RR_PARAM_TBL,
        .a5  = RR_WIDTH_TBL,
        .a6  = RR_EDGE_TBL_BASE + sign_ext16(be16(image + A_road_edge_sel)),
        .d2  = RR_ROW_STRIDE_D2,
        .d7  = 0,                 /* band A never masks d0 with d7 (scratch there) */
    };

    b->band_A(&r);
    rr_group_step(&r);
    r.d7 = rr_moveq((int8_t)0xf8);   /* 0xfffffff8; d7.w=0xfff8 from the first step onward */

    b->band_B(&r, 0x04, 0);   /* 0x93c2 (near copy) */
    b->band_B(&r, 0x5a, 1);   /* 0x948c (far copy: distinct wider blit tail) */
    rr_group_step(&r);        /* 0x956e */
    b->band_C_near(&r, 0x05); /* 0x9582 (near copy) */
    b->band_C_far(&r, 0x59);  /* 0x96b8 (far copy: distinct fast-split + merge tail) */
    rr_group_step(&r);        /* 0x9868 */
    b->band_D(&r, 0x05, 0);   /* 0x987c (near copy) */
    b->band_D(&r, 0x59, 1);   /* 0x9950 (far copy) -> rts */
}

#endif /* BB_ROAD_BANDS_H */
