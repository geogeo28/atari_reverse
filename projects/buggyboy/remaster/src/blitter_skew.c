/* blitter_skew.c — HARDWARE-SKEW blit path for the COLOUR-INDEXED fine-x engine rm_blit_objshift
 * (PERF30 C4, hardware-SKEW campaign slice 1: CALIBRATION ONLY — not routed, no static table yet).
 *
 * MEASUREMENT BUILD ONLY: compiled solely under GAME_STE_SWEEP (build_game.sh), so the shipping
 * BUGGYBOY.PRG is byte-identical while this is being calibrated.
 *
 * WHY: the shipping colour path pre-shifts in software (BLIT_STE_SPEC §8) and so must materialise a
 * bitmap per (fine_x, colour, rows) — a key the drive never repeats (§10's NO-GO). Letting the chip do
 * the shift with its SKEW register removes fine_x, colour AND rows from the materialise key, which §12
 * measured BOUNDED at 78-98 sprite keys. This file is the byte-exactness calibration that §12 flagged
 * as the open risk.
 *
 * ============================ THE RECIPE (spec §13) ============================
 * The CPU engine (src/blit.c rm_blit_objshift, BASE family) writes ncols = base_cells+1 destination
 * columns per row; column c is written first by cell c-1's col1 (low) half, then by cell c's col0 (high)
 * half. With k = fine_x and shl = 16-k that reduces to (see §8):
 *     net_mask[c]   = m_lo[c-1] & m_hi[c]
 *     net_data_p[c] = (pix_lo_p[c-1] & m_hi[c]) | pix_hi_p[c]
 * Expanding the engine's rol.l/lsl.l halves, with m = ~(A|B|C)&D and f_p the colour fill word:
 *     m_hi[c]  = (m_c >> k) | (top k bits set)        m_lo[c-1] = (m_{c-1} << (16-k)) | (low 16-k set)
 * so  net_mask[c] = (m_{c-1} << (16-k)) | (m_c >> k)
 * which is EXACTLY the blitter's skew output for source words (m_{c-1}, m_c) at skew = k. The same
 * expansion of the pixel halves gives
 *     net_data_p[c] = ((P_p[c-1] << (16-k)) | (P_p[c] >> k)) & f_p
 * because both halves are gated by the SAME destination-space fill word f_p, and the `& m_hi[c]` on the
 * low half is a no-op (m_hi's top k bits are the rol seed's 1s). P_p is the UNSHIFTED, COLOUR-INDEPENDENT
 * per-plane bitmap:
 *     P_0 = A   P_1 = B   P_2 = C   P_3 = D & ~m   (= D & (A|B|C), the engine's is_last special)
 *
 * So per plane p the blit is two skew passes over unshifted bitmaps:
 *   AND pass  src = M,   HOP = SRC, LOP = AND, skew = k
 *   OR  pass  src = P_p, HOP = SRC, LOP = OR,  skew = k       (skipped entirely when f_p == 0)
 * and the colour fill is carried by the ENDMASKS, not by the data: an OR pass with endmask e computes
 * dst |= (src & e), so ANDing f_p into all three endmasks applies the fill for free. That is why the
 * materialised bitmaps stay colour-independent even for a fill word that is not 0/0xFFFF (the sweep's
 * synthetic colour table is arbitrary bytes, and is byte-exact here). The GAME's own color_pairs is the
 * plain bit-expansion of the colour index — every word is 0 or 0xFFFF — so on real data a blit fires
 * 4 AND passes + popcount(colour) OR passes, 6 on average, not 8.
 *
 * EDGE COLUMNS — no FXSR, no NFSR. The source row holds base_cells words but the blit writes
 * base_cells+1 columns, so x_count = base_cells+1 and the chip performs one source read per destination
 * word (FXSR = NFSR = 0):
 *   - column 0's top k bits come from the shifter's leftover (no cell -1 exists). The CPU engine leaves
 *     them untouched (mask seed 1s / no pixels), so ENDMASK1 = 0xFFFF >> k blocks them.
 *   - column base_cells' low 16-k bits come from the line's one wasted read (the next row's first word).
 *     The CPU engine leaves those untouched too, so ENDMASK3 = ~(0xFFFF >> k) blocks them.
 *   - ENDMASK2 = 0xFFFF (the interior columns are fully written).
 * Since exactly one source read is wasted per line and it lands on the next row's first word, the
 * per-line source advance must be src_x_inc*(x_count-1) + src_y_inc = 2*base_cells, i.e. SRC_Y_INC = 0
 * over a tightly packed base_cells-word row. The last line's wasted read runs one word past the bitmap,
 * so the scratch carries pad words (OBJSH_SKEW_PAD_WORDS, blitter.h).
 *
 * HYBRID: BASE family only; LEFT/RIGHT clip and an over-tall sprite return 0 for the CPU engine, exactly
 * like the pre-shift path. SUPERVISOR ONLY (blit_run pokes 0xFFFF8Axx).
 *
 * SEAM: materialise and blit are separate entry points over an explicit ObjshSkewBitmaps (blitter.h).
 * Slice 1 keeps ONE static scratch, re-materialised per call; slice 2's bounded sprite-key table hands
 * the blit a table entry instead, with no change to the blit side.
 */
#include "blitter.h"
#include "screen.h"
#include "blit_const.h"
#include "st.h"
#include "game.h"

#define OBJSH_SKEW_WORD_ONES  0xFFFFu

/* Slice-1 scratch: ONE sprite region at a time, re-materialised per call. */
static ObjshSkewBitmaps skew_scratch;

/* Materialise the five UNSHIFTED, colour-independent bitmaps for one sprite region into `bm`.
 * Row-major, base_cells words per row, rows in DRAW order (row 0 = the bottom row the blit starts on). */
void rm_objsh_skew_materialise(ObjshSkewBitmaps *bm, const uint8_t *src, uint32_t src_off,
                               int16_t stride, int rows, int base_cells) {
    /* sp_step is signed and stays signed through the pointer walk — stride > 8 makes the source walk
     * BACK, and a real host pointer cannot wrap a uint32_t round-trip (see Offset in st.h, blit.c). */
    int32_t sp_step = OBJSH_CELL_BYTES - sx16((uint16_t)stride);
    const uint8_t *srow = src + src_off;
    for (int i = 0; i < rows; i++, srow += sp_step) {
        for (int j = 0; j < base_cells; j++) {
            const uint8_t *cell = srow + j * OBJSH_CELL_BYTES;
            uint16_t a = be16(cell), b = be16(cell + 2), c = be16(cell + 4), d = be16(cell + 6);
            uint16_t m = (uint16_t)(~(uint16_t)(a | b | c) & d);
            int word_idx = i * base_cells + j;
            bm->word[OBJSH_SKEW_BM_MASK][word_idx] = m;
            bm->word[OBJSH_SKEW_BM_PLANE0 + 0][word_idx] = a;
            bm->word[OBJSH_SKEW_BM_PLANE0 + 1][word_idx] = b;
            bm->word[OBJSH_SKEW_BM_PLANE0 + 2][word_idx] = c;
#if RM_SKEW_MUTATE == RM_SKEW_MUT_PLANE3
            bm->word[OBJSH_SKEW_BM_PLANE0 + 3][word_idx] = d;
#else
            bm->word[OBJSH_SKEW_BM_PLANE0 + 3][word_idx] = (uint16_t)(d & (uint16_t)~m);
#endif
        }
    }
    /* The wasted read of the last line: pad deterministically (its bits are endmask3-blocked anyway).
     * Only the FIRST pad word is zeroed — the calibrated path never reads further, and paying for the
     * whole mutation headroom here would tax the materialise bench for a build that must fail anyway. */
    for (int bitmap = 0; bitmap < OBJSH_SKEW_N_BITMAPS; bitmap++) bm->word[bitmap][rows * base_cells] = 0;
}

/* One skew pass for one plane, into that plane's word of the destination cells. `fill_mask` is ANDed
 * into all three endmasks — 0xFFFF for the mask pass, the plane's colour fill word for the data pass
 * (an OR pass with endmask e computes dst |= src & e). */
static void blit_skew_pass(uint8_t *dst_plane_col0, const uint16_t *bitmap, int base_cells, int rows,
                           unsigned fine_x, uint8_t lop, uint16_t fill_mask) {
    uint16_t lead_guard = (uint16_t)(OBJSH_SKEW_WORD_ONES >> fine_x);   /* column 0: block the top k bits */
    BlitPass pass;
    pass.src_addr  = (uint32_t)bitmap;
    pass.src_x_inc = 2;
    pass.src_y_inc = 0;                                    /* x_count-1 x-steps already span the row */
    pass.dst_addr  = (uint32_t)dst_plane_col0;
    pass.dst_x_inc = OBJSH_CELL_BYTES;                     /* next column, same plane */
    pass.dst_y_inc = -(int16_t)(SCREEN_ROW_BYTES + OBJSH_CELL_BYTES * base_cells);   /* one scanline UP */
#if RM_SKEW_MUTATE == RM_SKEW_MUT_ENDMASK1
    pass.endmask1  = fill_mask;
#else
    pass.endmask1  = (uint16_t)(lead_guard & fill_mask);
#endif
    pass.endmask2  = fill_mask;
#if RM_SKEW_MUTATE == RM_SKEW_MUT_ENDMASK3
    pass.endmask3  = fill_mask;
#else
    pass.endmask3  = (uint16_t)((uint16_t)~lead_guard & fill_mask);
#endif
    pass.x_count   = (uint16_t)(base_cells + 1);
    pass.y_count   = (uint16_t)rows;
    pass.hop       = BLT_HOP_SRC;
    pass.lop       = lop;
#if RM_SKEW_MUTATE == RM_SKEW_MUT_SKEW_PLUS
    pass.skew_ctl  = (uint8_t)((fine_x + 1) & BLT_SKEW_MASK);
#elif RM_SKEW_MUTATE == RM_SKEW_MUT_FXSR
    /* FXSR adds a source read at every line start, so the source drifts one word per line past the
     * calibrated walk — OBJSH_SKEW_PAD_WORDS is sized to keep even that in bounds (blitter.h). */
    pass.skew_ctl  = (uint8_t)(fine_x | BLT_SKEW_FXSR);
#else
    pass.skew_ctl  = (uint8_t)fine_x;
#endif
    blit_run(&pass);
}

/* Does the skew path serve this draw, or is it the pinned CPU hybrid? objsh_is_base (blitter.h) also
 * rejects the zero-row case, which the entry points report as a handled no-op. */
static int objsh_skew_draws(uint16_t x, uint16_t rows_m1, int rows, int base_cells) {
    return rows <= OBJSH_MAX_ROWS && base_cells <= OBJSH_SKEW_MAX_CELLS &&
           objsh_is_base(x, rows_m1, base_cells);
}

int rm_blit_objshift_skew_from(const ObjshSkewBitmaps *bm, uint8_t *dst, uint32_t dst_off, uint16_t x,
                               uint16_t color, uint16_t rows_m1, const uint8_t *color_pairs,
                               int base_cells) {
    int rows = (int16_t)rows_m1 + 1;
    if (!objsh_skew_draws(x, rows_m1, rows, base_cells))
        return rows <= 0;                                  /* zero rows: handled no-op; else CPU hybrid */

    unsigned fine_x = (unsigned)(x & OBJSH_NIBBLE);
    int16_t aligned_col = (int16_t)((int16_t)((int16_t)(uint16_t)x >> 1) & (int16_t)COL_ALIGN);
    uint8_t *col0_bottom = dst + dst_off + sx16((uint16_t)aligned_col);
    uint16_t col_off = (uint16_t)((color & OBJSH_NIBBLE) * OBJSH_COLOR_STRIDE);
    for (int p = 0; p < OBJSH_PLANES; p++) {
        uint8_t *plane_col0 = col0_bottom + 2 * p;         /* this plane's word inside the 4-plane cell */
        blit_skew_pass(plane_col0, bm->word[OBJSH_SKEW_BM_MASK], base_cells, rows, fine_x,
                       BLT_LOP_AND, OBJSH_SKEW_WORD_ONES);
        uint16_t fill = be16(color_pairs + col_off + p * 2);
        if (!fill) continue;                               /* OR with nothing — the pass is a no-op */
        blit_skew_pass(plane_col0, bm->word[OBJSH_SKEW_BM_PLANE0 + p], base_cells, rows, fine_x,
                       BLT_LOP_OR, fill);
    }
    return 1;
}

/* Hardware-skew path for rm_blit_objshift. Returns 1 if drawn (BASE family / zero-row no-op), 0 for the
 * CPU hybrid (clip family / over-tall). Same signature/contract as the C reference. Supervisor only. */
int rm_blit_objshift_skew(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                          uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                          const uint8_t *color_pairs, int base_cells) {
    int rows = (int16_t)rows_m1 + 1;
    if (objsh_skew_draws(x, rows_m1, rows, base_cells))
        rm_objsh_skew_materialise(&skew_scratch, src, src_off, stride, rows, base_cells);
    return rm_blit_objshift_skew_from(&skew_scratch, dst, dst_off, x, color, rows_m1, color_pairs,
                                      base_cells);
}
