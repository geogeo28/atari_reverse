/* blitter_objshift.c — the STE hardware-blitter path for the COLOUR-INDEXED fine-x masked blitter
 * rm_blit_objshift (recreate's blit_objshift @0x14680, PERF30 C4 slice 4). GAME_STE build only. This is
 * the bigger of the two fine-x object passes (~25% of the gate frame).
 *
 * RECIPE (BLIT_STE_SPEC §8). Same cache-keyed pre-shift + 2-pass cookie-cut as objshift2, but the source
 * is 4-plane (four words A,B,C,D per cell), the show mask is ~(A|B|C)&D (not ~(w0|w1)), and each plane's
 * pixels are gated by a per-plane COLOUR FILL from color_pairs[colour]. No third pass: the fill is
 * composited into the OR-data at materialise time. The per-column values are the exact algebraic
 * reduction of the CPU engine's sequential AND-then-OR straddle (blit.c objsh_row): a column j is written
 * first by cell (j-1)'s col1 half, then cell j's col0 half, so
 *     net_mask[j] = m_col1[j-1] & m_col0[j]
 *     net_data_p[j] = (pix_lo_p[j-1] & m_col0[j]) | pix_hi_p[j]
 * with an absent neighbour contributing the 0xFFFF mask seed / 0 pixels (the engine's `moveq #-1` fill
 * that keeps the background outside the sprite). Plane 3 (D) additionally masks its pixels by ~m (the
 * engine's is_last special). Verified byte-for-byte over the full objshift case space by run_ste_sweep.py.
 *
 * HYBRID: BASE family only; LEFT/RIGHT clip stays on the CPU asm engine (pinned), like objshift2.
 * SUPERVISOR ONLY (blit_run pokes 0xFFFF8Axx) — the dispatch runs the attempt in one Supexec per blit.
 */
#include "blitter.h"
#include "screen.h"
#include "blit_const.h"
#include "st.h"
#include "game.h"          /* rm_blit_objshift / rm_blit_objshift_asm — the byte-exact ref + CPU hybrid */

/* OBJSH_PLANES / OBJSH_MAX_ROWS are the shared contract caps (blit_const.h) — src/blitter_skew.c sizes
 * its own materialise buffers from the same two. */
#define OBJSH_CELL_WORDS     4                             /* A,B,C,D — one 4-plane source cell = 8 bytes */
#define OBJSH_MAX_STRADDLE   2                             /* base_cells max = 2 */
#define OBJSH_MAX_COLS       (OBJSH_MAX_STRADDLE + 1)
#define OBJSH_MAX_WORDS      (OBJSH_PLANES * OBJSH_MAX_COLS * OBJSH_MAX_ROWS)
#define OBJSH_MASK_SEED      0xFFFF0000u                   /* rol.l seed: 1s rotate in outside the sprite */
/* OBJSH_COLOR_STRIDE is shared from blitter.h (also used by the sweep). */

static uint32_t objsh_rotl32(uint32_t v, unsigned count) {
    count &= 31;
    return count ? ((v << count) | (v >> (32 - count))) : v;
}

/* Memoisation cache — same rationale as objshift2 (arena.gfx is static; see BLIT_STE_SPEC §6). Key adds
 * colour (selects the fill), stride (the per-row source walk) and base_cells (the width family). */
typedef struct {
    int valid;
    const uint8_t *src; const uint8_t *pairs; uint32_t src_off;
    uint16_t fine_x, color, rows_m1; int16_t stride; int base_cells;
    int nwords, rows;
    uint16_t mask[OBJSH_MAX_WORDS];
    uint16_t data[OBJSH_MAX_WORDS];
} ObjshCache;

#define OBJSH_CACHE_SLOTS 96                               /* 96 * ~2 KB ~= 190 KB (see combined RAM note) */
static ObjshCache objsh_cache[OBJSH_CACHE_SLOTS];
uint32_t rm_objsh_cache_hits, rm_objsh_cache_misses;       /* profiling (run_cadence / stats dump) */

/* Direct-map slot: a multiplicative mix of the key fields (arbitrary odd/prime multipliers, not
 * load-bearing; a bad mix is caught as a miss), `>> 15` before `% SLOTS` — same scheme as
 * objsh2_cache_hash (blitter_objshift2.c). */
static unsigned objsh_cache_hash(uint32_t src_off, unsigned fine_x, int base_cells, uint16_t color,
                                 int16_t stride, uint16_t rows_m1) {
    unsigned h = src_off * 2654435761u + fine_x * 40503u + (unsigned)base_cells * 2246822519u +
                 color * 0x9E37u + (unsigned)(uint16_t)stride * 40507u + rows_m1 * 0x85EBu;
    return (h >> 15) % OBJSH_CACHE_SLOTS;
}

/* Full key comparison / slot write — the ONE place each enumerates the key, kept symmetric so a future
 * key field can't be added to one and forgotten in the other (mirrors objsh2_cache_hit/store). */
static int objsh_cache_hit(const ObjshCache *e, const uint8_t *src, const uint8_t *pairs, uint32_t src_off,
                           unsigned fine_x, uint16_t color, int16_t stride, uint16_t rows_m1, int base_cells) {
    return e->valid && e->src == src && e->pairs == pairs && e->src_off == src_off &&
           e->fine_x == (uint16_t)fine_x && e->color == color && e->stride == stride &&
           e->rows_m1 == rows_m1 && e->base_cells == base_cells;
}

static void objsh_cache_store(ObjshCache *e, const uint8_t *src, const uint8_t *pairs, uint32_t src_off,
                              unsigned fine_x, uint16_t color, int16_t stride, uint16_t rows_m1,
                              int base_cells, int nwords, int rows) {
    e->src = src; e->pairs = pairs; e->src_off = src_off; e->fine_x = (uint16_t)fine_x;
    e->color = color; e->stride = stride; e->rows_m1 = rows_m1; e->base_cells = base_cells;
    e->nwords = nwords; e->rows = rows; e->valid = 1;
}

/* The interleaved 2-pass cookie-cut is the shared blit_ste_cookiecut_pass (blitter.h). */

/* One cell's straddle contribution: the col0 (high) mask + per-plane pixels, or the col1 (low) ones.
 * mask16 = ~(A|B|C)&D; pixels = (word_p << shl) gated by the plane fill; plane 3 masked by ~m (is_last). */
typedef struct { uint16_t m; uint16_t pix[OBJSH_PLANES]; } ObjshHalf;

static ObjshHalf objsh_cell_half(const uint8_t *cell, unsigned shl, const uint16_t fill[OBJSH_PLANES], int col0_side) {
    uint16_t a = be16(cell), b = be16(cell + 2), c = be16(cell + 4), d = be16(cell + 6);
    uint16_t mask16 = (uint16_t)(~(uint16_t)(a | b | c) & d);
    uint32_t mask32 = objsh_rotl32(OBJSH_MASK_SEED | mask16, shl);
    uint16_t m = col0_side ? (uint16_t)(mask32 >> 16) : (uint16_t)mask32;
    ObjshHalf h;
    h.m = m;
    for (int p = 0; p < OBJSH_PLANES; p++) {
        uint32_t pix32 = (uint32_t)be16(cell + p * 2) << shl;
        uint16_t pix = (uint16_t)((col0_side ? (pix32 >> 16) : pix32) & fill[p]);
        if (p == OBJSH_PLANES - 1) pix = (uint16_t)(pix & (uint16_t)~m);   /* plane 3 is_last special */
        h.pix[p] = pix;
    }
    return h;
}

static const ObjshHalf OBJSH_ABSENT = { 0xFFFF, { 0, 0, 0, 0 } };   /* absent neighbour: seed mask, no pixels */

/* Blitter path for rm_blit_objshift. Returns 1 if handled (BASE family / zero-row no-op), 0 for the CPU
 * hybrid (clip family / oversized). Same signature/contract as the C reference. */
int rm_blit_objshift_blitter(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                             uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                             const uint8_t *color_pairs, int base_cells) {
    int rows = (int16_t)rows_m1 + 1;
    if (rows <= 0) return 1;
    if (rows > OBJSH_MAX_ROWS) return 0;

    unsigned fine_x = (unsigned)(x & OBJSH_NIBBLE);
    unsigned shl = OBJSH_SUBPX_BITS - fine_x;
    int16_t A = (int16_t)((int16_t)((int16_t)(uint16_t)x >> 1) & (int16_t)COL_ALIGN);
    int16_t base_ceiling = (int16_t)(OBJSH_RIGHT_BOUND - OBJSH_CELL_BYTES * (base_cells - 1));
    if (A < 0 || (int16_t)(A - base_ceiling) >= 0)
        return 0;                                          /* LEFT/RIGHT clip -> CPU hybrid */

    int straddle = base_cells;                             /* BASE family: 1 or 2 */
    int ncols = straddle + 1;

    ObjshCache *e = &objsh_cache[objsh_cache_hash(src_off, fine_x, base_cells, color, stride, rows_m1)];
    if (objsh_cache_hit(e, src, color_pairs, src_off, fine_x, color, stride, rows_m1, base_cells)) {
        rm_objsh_cache_hits++;
    } else {
        rm_objsh_cache_misses++;
        uint16_t fill[OBJSH_PLANES];
        uint16_t col_off = (uint16_t)((color & OBJSH_NIBBLE) * OBJSH_COLOR_STRIDE);
        for (int p = 0; p < OBJSH_PLANES; p++) fill[p] = be16(color_pairs + col_off + p * 2);

        int32_t sp_step = OBJSH_CELL_BYTES - sx16((uint16_t)stride);   /* signed per-row source walk */
        for (int i = 0; i < rows; i++) {
            const uint8_t *srow = src + src_off + (uint32_t)((int32_t)i * sp_step);
            for (int j = 0; j < ncols; j++) {
                /* column j = cell (j-1)'s col1 (low) then cell j's col0 (high) — the CPU's write order. */
                ObjshHalf hi = (j < straddle) ? objsh_cell_half(srow + j * OBJSH_CELL_BYTES, shl, fill, 1) : OBJSH_ABSENT;
                ObjshHalf lo = (j > 0)        ? objsh_cell_half(srow + (j - 1) * OBJSH_CELL_BYTES, shl, fill, 0) : OBJSH_ABSENT;
                uint16_t net_mask = (uint16_t)(lo.m & hi.m);
                uint16_t *m = &e->mask[(i * ncols + j) * OBJSH_PLANES];
                uint16_t *dp = &e->data[(i * ncols + j) * OBJSH_PLANES];
                for (int p = 0; p < OBJSH_PLANES; p++) {
                    m[p] = net_mask;                                   /* mask same across planes */
                    dp[p] = (uint16_t)((lo.pix[p] & hi.m) | hi.pix[p]);
                }
            }
        }
        objsh_cache_store(e, src, color_pairs, src_off, fine_x, color, stride, rows_m1, base_cells,
                          OBJSH_PLANES * ncols, rows);
    }

    uint8_t *col0_bottom = dst + dst_off + sx16((uint16_t)A);
    blit_ste_cookiecut_pass(col0_bottom, e->mask, e->nwords, e->rows, BLT_LOP_AND);
    blit_ste_cookiecut_pass(col0_bottom, e->data, e->nwords, e->rows, BLT_LOP_OR);
    return 1;
}

void rm_blit_objshift_cache_flush(void) {
    for (int i = 0; i < OBJSH_CACHE_SLOTS; i++) objsh_cache[i].valid = 0;
}

/* ---- runtime dispatch (object_list.c's RM_BLIT_OBJSHIFT, only under -DRM_STE_OBJSH_ROUTE) ----
 * Off by default: the colour engine regresses driving with the on-demand cache (see the routing note in
 * object_list.c). The byte-exact rm_blit_objshift_blitter above is always compiled + swept; this glue is
 * only reached when the engine is opted back in. */
#ifdef RM_STE_OBJSH_ROUTE
static struct {
    uint8_t *dst; uint32_t dst_off; const uint8_t *src; uint32_t src_off;
    uint16_t x, color, rows_m1; int16_t stride; const uint8_t *pairs; int base_cells;
} g_objsh;

static long objsh_blitter_super(void) {
    return rm_blit_objshift_blitter(g_objsh.dst, g_objsh.dst_off, g_objsh.src, g_objsh.src_off,
                                    g_objsh.x, g_objsh.color, g_objsh.rows_m1, g_objsh.stride,
                                    g_objsh.pairs, g_objsh.base_cells);
}

void rm_blit_objshift_dispatch(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                               uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                               const uint8_t *color_pairs, int base_cells) {
    /* Decide the family in USER mode; a clip case skips the excursion (mirrors the C's family test). */
    int16_t A = (int16_t)((int16_t)((int16_t)(uint16_t)x >> 1) & (int16_t)COL_ALIGN);
    int16_t base_ceiling = (int16_t)(OBJSH_RIGHT_BOUND - OBJSH_CELL_BYTES * (base_cells - 1));
    if ((int16_t)rows_m1 + 1 > 0 && (A < 0 || (int16_t)(A - base_ceiling) >= 0)) {
        rm_blit_objshift_asm(dst, dst_off, src, src_off, x, color, rows_m1, stride, color_pairs, base_cells);
        return;
    }
    g_objsh.dst = dst; g_objsh.dst_off = dst_off; g_objsh.src = src; g_objsh.src_off = src_off;
    g_objsh.x = x; g_objsh.color = color; g_objsh.rows_m1 = rows_m1; g_objsh.stride = stride;
    g_objsh.pairs = color_pairs; g_objsh.base_cells = base_cells;
    if (!Supexec(objsh_blitter_super))
        rm_blit_objshift_asm(dst, dst_off, src, src_off, x, color, rows_m1, stride, color_pairs, base_cells);
}
#endif  /* RM_STE_OBJSH_ROUTE */
