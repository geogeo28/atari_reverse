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
 * blitter walks UP (negative dst_y_inc) to match. */
static uint16_t bl_mask[OBJSH2_MAX_WORDS];
static uint16_t bl_data[OBJSH2_MAX_WORDS];

/* Fire one aligned (skew=0) blitter pass over the whole interleaved region (nwords = 4*ncols words/row,
 * fully contiguous in the framebuffer), all 4 planes at once. */
static void objsh2_blit_pass(uint8_t *col0_bottom, const uint16_t *src_bm, int nwords, int rows, uint8_t lop) {
    BlitPass pass;
    pass.src_addr  = (uint32_t)src_bm;
    pass.src_x_inc = 2;
    pass.src_y_inc = 2;                                     /* tightly packed nwords words per row */
    pass.dst_addr  = (uint32_t)col0_bottom;
    pass.dst_x_inc = 2;                                     /* contiguous interleaved words */
    pass.dst_y_inc = -(int16_t)(SCREEN_ROW_BYTES + 2 * (nwords - 1));  /* one scanline UP, back to col0 */
    pass.endmask1  = 0xFFFF;
    pass.endmask2  = 0xFFFF;
    pass.endmask3  = 0xFFFF;
    pass.x_count   = (uint16_t)nwords;
    pass.y_count   = (uint16_t)rows;
    pass.hop       = BLT_HOP_SRC;
    pass.lop       = lop;
    pass.skew_ctl  = 0;
    blit_run(&pass);
}

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

    unsigned fine_x = (unsigned)(x & OBJSH_NIBBLE);
    int16_t col = (int16_t)((int16_t)(uint16_t)x >> 1) & (int16_t)COL_ALIGN;
    int16_t base_ceiling = (int16_t)(OBJSH2_RIGHT_BOUND + OBJSH2_LADDER_STEP * width_idx);
    if (col < 0 || (int16_t)(col - base_ceiling) >= 0)
        return 0;                                          /* LEFT/RIGHT clip -> CPU hybrid */

    int straddle = OBJSH2_BASE_STRADDLE - width_idx;       /* 3 / 2 / 1 */
    int ncols = straddle + 1;

    /* Materialise the pre-shifted mask + per-plane data, bottom-up (row i reads src_off - i*80, exactly
     * the engine's row walk). Per dst column j the fine-x straddle spreads source cell (j-1)'s high part
     * and cell j's low part — the `<<shl` split the CPU engine's straddle cell does (blit.c). */
    for (int i = 0; i < rows; i++) {
        const uint8_t *srow = src + src_off - (uint32_t)i * OBJSH2_SRC_ROW_BYTES;
        for (int j = 0; j < ncols; j++) {
            uint16_t l0 = (j > 0)        ? be16(srow + (j - 1) * OBJSH2_SRC_CELL_HALF + 0) : 0;
            uint16_t l1 = (j > 0)        ? be16(srow + (j - 1) * OBJSH2_SRC_CELL_HALF + 2) : 0;
            uint16_t r0 = (j < straddle) ? be16(srow + j * OBJSH2_SRC_CELL_HALF + 0) : 0;
            uint16_t r1 = (j < straddle) ? be16(srow + j * OBJSH2_SRC_CELL_HALF + 2) : 0;
            /* right-shift each 16-px source word by fine_x across the column boundary: high part from the
             * left source cell, low part from this one. fine_x==0 folds cleanly (l<<16 -> 0). */
            uint16_t sh_w0 = (uint16_t)(((uint32_t)l0 << (OBJSH_SUBPX_BITS - fine_x)) | (uint16_t)(r0 >> fine_x));
            uint16_t sh_w1 = (uint16_t)(((uint32_t)l1 << (OBJSH_SUBPX_BITS - fine_x)) | (uint16_t)(r1 >> fine_x));
            uint16_t sh_u  = (uint16_t)(sh_w0 | sh_w1);     /* shifted union == ~mask */
            /* interleaved: cell j's 4 plane words are contiguous. mask is the SAME across planes; data is
             * (w0, w1, u, u) for planes 0..3 (planes 2,3 forced to the union — objshift2's high-colour). */
            uint16_t *m = &bl_mask[(i * ncols + j) * SCREEN_PLANES];
            uint16_t *d = &bl_data[(i * ncols + j) * SCREEN_PLANES];
            m[0] = m[1] = m[2] = m[3] = (uint16_t)~sh_u;
            d[0] = sh_w0; d[1] = sh_w1; d[2] = sh_u; d[3] = sh_u;
        }
    }

    /* col0 of the BOTTOM row (the engine's first-drawn row): dst + dst_off + aligned_col. */
    uint8_t *col0_bottom = dst + dst_off + sx16((uint16_t)col);
    int nwords = SCREEN_PLANES * ncols;
    objsh2_blit_pass(col0_bottom, bl_mask, nwords, rows, BLT_LOP_AND);
    objsh2_blit_pass(col0_bottom, bl_data, nwords, rows, BLT_LOP_OR);
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
    Supexec(objsh2_blitter_super);                         /* BASE family drawn by the blitter */
}
