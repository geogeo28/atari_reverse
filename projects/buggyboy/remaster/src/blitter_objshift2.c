/* blitter_objshift2.c — the STE hardware-blitter path for the fixed-pass fine-x masked sprite blitter
 * rm_blit_objshift2 (PERF30 C4, slice 2). GAME_STE build only.
 *
 * RECIPE (see BLIT_STE_SPEC.md §3b). objshift2 is a self-masking cookie-cut: per drawn 16-px 4-plane
 * column, dst = (dst & mask) | data with mask = ~(shifted w0|w1) and data = the fine-x-shifted source
 * (planes 0,1 = w0,w1; planes 2,3 = w0|w1). We reproduce it as a two-pass blitter cookie-cut — AND the
 * mask, OR the per-plane data, HOP=SRC — over ALL FOUR planes.
 *
 * Why pre-shift + skew=0 (not the hardware skew). Slice 1 proved a skew=0 AND/OR cookie-cut reproduces
 * the engine byte-for-byte. The fine-x straddle is done HERE, in the materialiser: each source word is
 * spread across two dst columns exactly as the CPU engine's `<<shl` does, so the blitter runs an aligned
 * blit of the pre-shifted bitmaps. This keeps the pins on the proven aligned recipe and sidesteps the
 * blitter's FXSR/NFSR/endmask edge semantics (a byte-exactness risk that would violate "no approximate
 * pixels"). The cost is table RAM (the pre-shift is 1 column wider than the source); the hardware-skew
 * variant would trade that RAM for the CPU shift but needs a calibrated FXSR/NFSR sweep — deferred as a
 * RAM optimisation. The materialiser reads only the (cached, static) sprite arena, never the framebuffer;
 * the blitter does the expensive framebuffer read-mask-OR-write.
 *
 * HYBRID. This handles the BASE family (sprite fully on-screen). The LEFT/RIGHT clip families keep the
 * CPU path (a pinned hybrid) — their edge cells need per-column endmask calibration, deferred. The
 * caller checks the return: 1 = drawn by the blitter (or a no-op), 0 = caller must run the CPU engine.
 *
 * SUPERVISOR ONLY (blit_run pokes 0xFFFF8Axx). The caller runs the object pass inside one Supexec.
 */
#include "blitter.h"
#include "screen.h"
#include "blit_const.h"
#include "st.h"
#include "game.h"          /* rm_blit_objshift2_asm — the CPU hybrid fallback (RM_ASM_BLIT set on this build) */

#define OBJSH2_MAX_STRADDLE  OBJSH2_BASE_STRADDLE          /* 3 (width_idx 0) */
#define OBJSH2_MAX_COLS      (OBJSH2_MAX_STRADDLE + 1)     /* straddle spreads into straddle+1 dst columns */
#define OBJSH2_MAX_ROWS      0x2B                          /* rows_m1 max 0x2a -> 43 rows */
#define OBJSH2_SRC_CELL_HALF (OBJSH_CELL_BYTES / 2)        /* 4 bytes: one 2-plane (w0,w1) source cell */
#define OBJSH2_MAX_WORDS     (SCREEN_PLANES * OBJSH2_MAX_COLS * OBJSH2_MAX_ROWS)

/* Pre-shifted bitmaps, laid out INTERLEAVED to match the framebuffer (row-major [row][col*4 + plane]).
 * That lets ONE contiguous blit cover all 4 planes of all columns — 2 passes/blit (AND mask, OR data),
 * not 8 — since a 16-px cell's 4 plane words are contiguous in the ST interleaved framebuffer and the
 * cookie-cut mask is the same across planes. Row 0 = the engine's first-drawn (bottom) row, so the
 * blitter walks UP (negative dst_y_inc) to match.
 *
 * MEMOISATION CACHE. Profiling (BLIT_STE_SPEC §6 / PERF30 C4) showed the per-frame MATERIALISE — the
 * fine-x shift + mask build — is ~3 vblanks on the objshift2-dense gate frame, dwarfing the (cheap)
 * blitter passes and making the naive path a NET LOSS vs the CPU asm. But the materialised bitmap is a
 * PURE FUNCTION of (src, src_off, fine_x, width_idx, rows_m1) over the STATIC sprite arena (arena.gfx is
 * read once at asset load and never rewritten during a race — see assets.c / the F10 reload is the only
 * mutation, off the render path). So it is safe to memoise: the same sprite blitted at the same scale/
 * phase every frame (the gate, tunnels, any slow-moving object) re-shifts ZERO times after the first —
 * the blit collapses to the 2 static-table passes (the profiled `nomat` win). A direct-mapped cache of
 * full interleaved (mask,data) bitmaps; a miss materialises into the slot, a hit blits it straight. Never
 * invalidates (static source) — this is a boot-warmed table filled on demand, not a per-frame rebuild. */
typedef struct {
    int valid;
    const uint8_t *src; uint32_t src_off; uint16_t fine_x; uint16_t rows_m1; int width_idx;   /* key */
    int nwords, rows;                                       /* geometry for the blit */
    uint16_t mask[OBJSH2_MAX_WORDS];
    uint16_t data[OBJSH2_MAX_WORDS];
} Objsh2Cache;

#define OBJSH2_CACHE_SLOTS 128                              /* 128 * ~2.7 KB ~= 350 KB (see RAM note) */
static Objsh2Cache objsh2_cache[OBJSH2_CACHE_SLOTS];
uint32_t rm_objsh2_cache_hits, rm_objsh2_cache_misses;      /* profiling (run_cadence / stats dump) */

/* Direct-map slot for a key. A multiplicative (Knuth/Fibonacci) mix of the key fields — the constants are
 * arbitrary odd/prime multipliers, not load-bearing; `>> 15` drops the poorly-mixed low bits before the
 * `% SLOTS` selects the slot. Collisions never corrupt (a key mismatch is treated as a miss). src itself
 * is NOT hashed (src_off already spreads well; two arenas at the same offset just collide → re-materialise
 * — still caught by the full key check in objsh2_cache_hit). */
static unsigned objsh2_cache_hash(uint32_t src_off, unsigned fine_x, int width_idx, uint16_t rows_m1) {
    unsigned h = src_off * 2654435761u + fine_x * 40503u + (unsigned)width_idx * 2246822519u + rows_m1 * 0x9E37u;
    return (h >> 15) % OBJSH2_CACHE_SLOTS;
}

/* Full key comparison (the ONE place the key fields are enumerated for matching) — a hit means the slot's
 * bitmap is byte-identical to re-materialising, since arena.gfx is static. Kept symmetric with
 * objsh2_cache_store below so the key field list can't drift between the write and the check. */
static int objsh2_cache_hit(const Objsh2Cache *e, const uint8_t *src, uint32_t src_off,
                            unsigned fine_x, int width_idx, uint16_t rows_m1) {
    return e->valid && e->src == src && e->src_off == src_off && e->fine_x == (uint16_t)fine_x &&
           e->rows_m1 == rows_m1 && e->width_idx == width_idx;
}

static void objsh2_cache_store(Objsh2Cache *e, const uint8_t *src, uint32_t src_off, unsigned fine_x,
                               int width_idx, uint16_t rows_m1, int nwords, int rows) {
    e->src = src; e->src_off = src_off; e->fine_x = (uint16_t)fine_x;
    e->rows_m1 = rows_m1; e->width_idx = width_idx;
    e->nwords = nwords; e->rows = rows; e->valid = 1;
}

/* Invalidate the cache. The key includes the src POINTER + src_off, so it stays correct as long as the
 * bytes at that address don't change — true during a race (arena.gfx is load-once). The F10 reload
 * (op_reload_assets) re-unpacks arena.gfx IN PLACE at the same address; if it recovers from a corrupt
 * arena the cached bitmaps would be stale, so game_main flushes here on reload. */
void rm_blit_objshift2_cache_flush(void) {
    for (int i = 0; i < OBJSH2_CACHE_SLOTS; i++) objsh2_cache[i].valid = 0;
}

/* The interleaved 2-pass cookie-cut is the shared blit_ste_cookiecut_pass (blitter.h). */

/* Is this call a BASE-family draw the blitter path handles? Cheap arithmetic (no supervisor needed), so
 * the dispatcher can decide in USER mode and only enter Supexec for a case the blitter will actually
 * draw — a declined clip case must not pay the excursion just to fall through to the CPU. Mirrors the
 * family test in rm_blit_objshift2 (blit.c). A zero-row call is a no-op the blitter "handles". */
int rm_blit_objshift2_is_base(uint16_t x, uint16_t rows_m1, int width_idx) {
    if ((int16_t)rows_m1 + 1 <= 0) return 1;               /* draws nothing */
    int16_t col = (int16_t)((int16_t)(uint16_t)x >> 1) & (int16_t)COL_ALIGN;
    int16_t base_ceiling = (int16_t)(OBJSH2_RIGHT_BOUND + OBJSH2_LADDER_STEP * width_idx);
    return !(col < 0 || (int16_t)(col - base_ceiling) >= 0);
}

/* Blitter path for rm_blit_objshift2. Returns 1 if handled (base family or a zero-row no-op), 0 if the
 * caller must fall back to the CPU engine (LEFT/RIGHT clip family). Same signature/contract as the C. */
int rm_blit_objshift2_blitter(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                              uint16_t x, uint16_t rows_m1, int width_idx) {
    int rows = (int16_t)rows_m1 + 1;
    if (rows <= 0) return 1;                                /* draws nothing — matches the C's rows<=0 skip */
    if (rows > OBJSH2_MAX_ROWS) return 0;                   /* beyond the bitmap height -> CPU hybrid (safety) */

    unsigned fine_x = (unsigned)(x & OBJSH_NIBBLE);
    int16_t col = (int16_t)((int16_t)(uint16_t)x >> 1) & (int16_t)COL_ALIGN;
    int16_t base_ceiling = (int16_t)(OBJSH2_RIGHT_BOUND + OBJSH2_LADDER_STEP * width_idx);
    if (col < 0 || (int16_t)(col - base_ceiling) >= 0)
        return 0;                                          /* LEFT/RIGHT clip -> CPU hybrid */

    int straddle = OBJSH2_BASE_STRADDLE - width_idx;       /* 3 / 2 / 1 */
    int ncols = straddle + 1;

    /* Cache lookup on the (static-source) materialise key. Hit -> skip the shift entirely. */
    Objsh2Cache *e = &objsh2_cache[objsh2_cache_hash(src_off, fine_x, width_idx, rows_m1)];
    if (!objsh2_cache_hit(e, src, src_off, fine_x, width_idx, rows_m1)) {
        rm_objsh2_cache_misses++;
        /* Miss: materialise the pre-shifted mask + per-plane data into the slot, bottom-up (row i reads
         * src_off - i*80, the engine's row walk). Per dst column j the fine-x straddle spreads source cell
         * (j-1)'s high part and cell j's low part — the `<<shl` split of the CPU engine's straddle cell. */
        for (int i = 0; i < rows; i++) {
            const uint8_t *srow = src + src_off - (uint32_t)i * OBJSH2_SRC_ROW_BYTES;
            for (int j = 0; j < ncols; j++) {
                uint16_t l0 = (j > 0)        ? be16(srow + (j - 1) * OBJSH2_SRC_CELL_HALF + 0) : 0;
                uint16_t l1 = (j > 0)        ? be16(srow + (j - 1) * OBJSH2_SRC_CELL_HALF + 2) : 0;
                uint16_t r0 = (j < straddle) ? be16(srow + j * OBJSH2_SRC_CELL_HALF + 0) : 0;
                uint16_t r1 = (j < straddle) ? be16(srow + j * OBJSH2_SRC_CELL_HALF + 2) : 0;
                /* right-shift each 16-px source word by fine_x across the column boundary: high part from
                 * the left source cell, low part from this one. fine_x==0 folds cleanly (l<<16 -> 0). */
                uint16_t sh_w0 = (uint16_t)(((uint32_t)l0 << (OBJSH_SUBPX_BITS - fine_x)) | (uint16_t)(r0 >> fine_x));
                uint16_t sh_w1 = (uint16_t)(((uint32_t)l1 << (OBJSH_SUBPX_BITS - fine_x)) | (uint16_t)(r1 >> fine_x));
                uint16_t sh_u  = (uint16_t)(sh_w0 | sh_w1); /* shifted union == ~mask */
                /* interleaved: cell j's 4 plane words are contiguous. mask same across planes; data is
                 * (w0, w1, u, u) for planes 0..3 (planes 2,3 forced to the union — objshift2 high-colour). */
                uint16_t *m = &e->mask[(i * ncols + j) * SCREEN_PLANES];
                uint16_t *d = &e->data[(i * ncols + j) * SCREEN_PLANES];
                m[0] = m[1] = m[2] = m[3] = (uint16_t)~sh_u;
                d[0] = sh_w0; d[1] = sh_w1; d[2] = sh_u; d[3] = sh_u;
            }
        }
        objsh2_cache_store(e, src, src_off, fine_x, width_idx, rows_m1, SCREEN_PLANES * ncols, rows);
    } else {
        rm_objsh2_cache_hits++;
    }

    /* col0 of the BOTTOM row (the engine's first-drawn row): dst + dst_off + aligned_col. */
    uint8_t *col0_bottom = dst + dst_off + sx16((uint16_t)col);
    blit_ste_cookiecut_pass(col0_bottom, e->mask, e->nwords, e->rows, BLT_LOP_AND);
    blit_ste_cookiecut_pass(col0_bottom, e->data, e->nwords, e->rows, BLT_LOP_OR);
    return 1;
}

/* ---- runtime dispatch (the RM_BLIT_OBJSHIFT2 seam for the STE build) ------------------------------
 * object_list.c's RM_BLIT_OBJSHIFT2 macro points here on GAME_STE. Try the blitter (BASE family); on a
 * declined clip case fall back to the CPU asm engine (byte-identical, pinned). The blitter touches the
 * supervisor-only 0xFFFF8Axx page, so the attempt runs inside one Supexec per blit. Per-blit Supexec is
 * the simplest correct shape; the object pass could instead run under ONE excursion — measured in
 * PERF30 (run_cadence.py) and chosen with numbers. The materialiser runs supervisor too (harmless — RAM
 * writes only), so the whole attempt is one function. */
static struct {
    uint8_t *dst; uint32_t dst_off; const uint8_t *src; uint32_t src_off;
    uint16_t x, rows_m1; int width_idx;
} g_objsh2;

static long objsh2_blitter_super(void) {
    return rm_blit_objshift2_blitter(g_objsh2.dst, g_objsh2.dst_off, g_objsh2.src, g_objsh2.src_off,
                                     g_objsh2.x, g_objsh2.rows_m1, g_objsh2.width_idx);
}

void rm_blit_objshift2_dispatch(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                                uint16_t x, uint16_t rows_m1, int width_idx) {
    /* Decide the family in USER mode: a CLIP case goes straight to the CPU engine with no excursion. */
    if (!rm_blit_objshift2_is_base(x, rows_m1, width_idx)) {
        rm_blit_objshift2_asm(dst, dst_off, src, src_off, x, rows_m1, width_idx);   /* CLIP -> CPU hybrid */
        return;
    }
    g_objsh2.dst = dst; g_objsh2.dst_off = dst_off; g_objsh2.src = src; g_objsh2.src_off = src_off;
    g_objsh2.x = x; g_objsh2.rows_m1 = rows_m1; g_objsh2.width_idx = width_idx;
    if (!Supexec(objsh2_blitter_super))                    /* BASE family drawn by the blitter, unless it */
        rm_blit_objshift2_asm(dst, dst_off, src, src_off, x, rows_m1, width_idx);  /* declines (oversized) -> CPU */
}
