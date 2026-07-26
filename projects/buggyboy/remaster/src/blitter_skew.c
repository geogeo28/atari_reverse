/* blitter_skew.c — HARDWARE-SKEW blit path for the COLOUR-INDEXED fine-x engine rm_blit_objshift
 * (PERF30 C4, hardware-SKEW campaign: slice 1 calibrated the recipe, slice 2 routes it off a static
 * table). This is the SHIPPING colour route on a blitter machine, bound at boot like objshift2 (§11).
 *
 * WHY: the older colour path pre-shifts in software (BLIT_STE_SPEC §8) and so must materialise a
 * bitmap per (fine_x, colour, rows) — a key the drive never repeats (§10's NO-GO). Letting the chip do
 * the shift with its SKEW register removes fine_x, colour AND rows from the materialise key, which §12
 * measured BOUNDED at 78-98 sprite keys — small enough for a no-eviction static table, so a blit off the
 * table costs only the register pokes and the chip's passes: 9,400 cyc against the CPU asm engine's
 * 33,920 on the swept shape (run_ste_sweep.py's cost bench, with the poke batching below).
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
 * so every bitmap carries pad words (OBJSH_SKEW_PAD_WORDS, blitter.h).
 *
 * HYBRID: BASE family only; LEFT/RIGHT clip and an over-tall sprite return 0 for the CPU engine, exactly
 * like the pre-shift path. SUPERVISOR ONLY (the register pokes hit 0xFFFF8Axx).
 *
 * SEAM: materialise and blit are separate entry points over an explicit ObjshSkewBitmaps (blitter.h), so
 * the table below hands the blit an entry and the sweep hands it a scratch — one blit side, two owners.
 */
#include "blitter.h"
#include "screen.h"
#include "blit_const.h"
#include "st.h"
#include "game.h"          /* rm_blit_objshift_asm — the CPU hybrid the dispatch falls back to */

#define OBJSH_SKEW_WORD_ONES  0xFFFFu

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

/* ---- register poke batching --------------------------------------------------------------------
 * One objshift blit fires 4 AND + popcount(colour) OR passes (6 on average), and most of the register
 * block is IDENTICAL across them. Only three registers are consumed by the chip as it runs — the source
 * and destination addresses (walked) and y_count (counted down) — so everything else is poked once and
 * left standing:
 *   per BLIT   (blit_skew_begin)  the four increments, HOP, the skew byte and x_count. x_count is safe
 *              to hoist because the chip reloads it from an internal latch at every line and leaves the
 *              register holding its initial value; the sweep re-verifies that (it blits both base_cells
 *              families, so a consumed x_count would corrupt every multi-pass case).
 *   per GROUP  (blit_skew_endmasks + the LOP write) the three endmasks and the logic op, which depend
 *              only on the fill word — constant across the four AND passes, and re-poked per OR pass.
 *   per PASS   (blit_skew_fire) the two addresses, y_count and the start.
 * On the average 4-AND + 2-OR blit that is 7 + (4 + 4x4) + (1 + 2x7) = 42 register writes, where
 * blit_run's 17 per pass would be 102. blit_run itself is left alone for its other callers (objshift2,
 * the self-test), which fire single passes where the batching would buy nothing. */
static void blit_skew_begin(int base_cells, unsigned fine_x) {
    BLT_W(BLT_SRC_X_INC) = 2;
    BLT_W(BLT_SRC_Y_INC) = 0;                              /* x_count-1 x-steps already span the row */
    BLT_W(BLT_DST_X_INC) = OBJSH_CELL_BYTES;               /* next column, same plane */
    BLT_W(BLT_DST_Y_INC) =
        (uint16_t)(-(int16_t)(SCREEN_ROW_BYTES + OBJSH_CELL_BYTES * base_cells));   /* one scanline UP */
    BLT_W(BLT_X_COUNT)   = (uint16_t)(base_cells + 1);     /* reloaded per line from the chip's latch */
    BLT_B(BLT_HOP)       = BLT_HOP_SRC;
#if RM_SKEW_MUTATE == RM_SKEW_MUT_SKEW_PLUS
    BLT_B(BLT_SKEW)      = (uint8_t)((fine_x + 1) & BLT_SKEW_MASK);
#elif RM_SKEW_MUTATE == RM_SKEW_MUT_FXSR
    /* FXSR adds a source read at every line start, so the source drifts one word per line past the
     * calibrated walk — OBJSH_SKEW_PAD_WORDS is sized to keep even that in bounds (blitter.h). */
    BLT_B(BLT_SKEW)      = (uint8_t)(fine_x | BLT_SKEW_FXSR);
#else
    BLT_B(BLT_SKEW)      = (uint8_t)fine_x;
#endif
    /* No halftone seed: HOP is SRC for every pass here, so the halftone RAM is never read. */
}

/* The three endmasks for a group of passes. `fill_mask` is ANDed into all three — 0xFFFF for the mask
 * passes, the plane's colour fill word for a data pass (an OR pass with endmask e computes
 * dst |= src & e). `lead_guard` = 0xFFFF >> fine_x blocks column 0's shifter leftover; its complement
 * blocks the line's one wasted source read in the last column. */
static void blit_skew_endmasks(uint16_t lead_guard, uint16_t fill_mask) {
#if RM_SKEW_MUTATE == RM_SKEW_MUT_ENDMASK1
    BLT_W(BLT_ENDMASK1)  = fill_mask;
#else
    BLT_W(BLT_ENDMASK1)  = (uint16_t)(lead_guard & fill_mask);
#endif
    BLT_W(BLT_ENDMASK2)  = fill_mask;
#if RM_SKEW_MUTATE == RM_SKEW_MUT_ENDMASK3
    BLT_W(BLT_ENDMASK3)  = fill_mask;
#else
    BLT_W(BLT_ENDMASK3)  = (uint16_t)((uint16_t)~lead_guard & fill_mask);
#endif
}

/* One pass: only the registers the chip consumes while it runs, then start it. */
static void blit_skew_fire(const uint16_t *bitmap, uint8_t *dst_plane_col0, int rows) {
    BLT_L(BLT_SRC_ADDR) = (uint32_t)bitmap;
    BLT_L(BLT_DST_ADDR) = (uint32_t)dst_plane_col0;
    BLT_W(BLT_Y_COUNT)  = (uint16_t)rows;
    blit_start_and_wait();
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
    uint16_t lead_guard = (uint16_t)(OBJSH_SKEW_WORD_ONES >> fine_x);   /* column 0: block the top k bits */

    blit_skew_begin(base_cells, fine_x);

    /* ALL FOUR mask passes first, then the data passes — not AND/OR interleaved per plane. The four
     * planes write DISJOINT destination words (plane p owns byte offset 2p of every 8-byte cell), so no
     * plane can observe another's write and the regrouping is byte-identical; within a plane the AND
     * still precedes the OR, which is the only ordering that matters. The win is that one endmask + LOP
     * group setup now covers all four AND passes instead of being re-poked for each. */
    blit_skew_endmasks(lead_guard, OBJSH_SKEW_WORD_ONES);
    BLT_B(BLT_LOP) = BLT_LOP_AND;
    for (int p = 0; p < OBJSH_PLANES; p++)
        blit_skew_fire(bm->word[OBJSH_SKEW_BM_MASK], col0_bottom + 2 * p, rows);

    BLT_B(BLT_LOP) = BLT_LOP_OR;                           /* the data group: only the fill still moves */
    for (int p = 0; p < OBJSH_PLANES; p++) {
        uint16_t fill = be16(color_pairs + col_off + p * 2);
        if (!fill) continue;                               /* OR with nothing — the pass is a no-op */
        blit_skew_endmasks(lead_guard, fill);
        blit_skew_fire(bm->word[OBJSH_SKEW_BM_PLANE0 + p], col0_bottom + 2 * p, rows);
    }
    return 1;
}

#ifdef GAME_STE_SWEEP
/* Un-tabled hardware-skew path for rm_blit_objshift: materialise into a private scratch, then blit it.
 * The SWEEP's entry point — it pins the recipe on its own, independent of any table state. Returns 1 if
 * drawn (BASE family / zero-row no-op), 0 for the CPU hybrid (clip family / over-tall). */
static ObjshSkewBitmaps skew_scratch;

int rm_blit_objshift_skew(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                          uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                          const uint8_t *color_pairs, int base_cells) {
    int rows = (int16_t)rows_m1 + 1;
    if (objsh_skew_draws(x, rows_m1, rows, base_cells))
        rm_objsh_skew_materialise(&skew_scratch, src, src_off, stride, rows, base_cells);
    return rm_blit_objshift_skew_from(&skew_scratch, dst, dst_off, x, color, rows_m1, color_pairs,
                                      base_cells);
}
#endif  /* GAME_STE_SWEEP */

/* ---- the static sprite-key table (BLIT_STE_SPEC §12) ---------------------------------------------
 * A materialised bitmap set is a pure function of the SPRITE key (src_off, stride, base_cells) over the
 * gfx arena: the chip applies fine_x, the colour rides in the endmasks, and rows only bounds y_count.
 * The census measured that key BOUNDED — 78 distinct entries on leg 0, 98 on the worst leg, FLAT from
 * ~80 frames through a 300-frame drive (the last +700 base calls added ZERO new keys). So the table
 * needs no eviction policy at all: a first-sight key claims a free entry and keeps it for the race, and
 * a full table (which the census says cannot happen) is simply declined to the CPU engine.
 *
 * ROWS stays out of the key, but an entry is NOT materialised to the full OBJSH_MAX_ROWS on sight: it
 * remembers how many rows it holds and re-materialises only when a later call wants more. Rows 0..r-1
 * are identical whatever the loop bound, so a grown entry is byte-identical to a max-height one — and
 * this way the materialiser never reads a source row no real call asked for (the per-row source walk is
 * `stride`-driven and can run backwards), and a 4-row roadside sprite never pays for 48.
 *
 * A grow re-materialises from row 0 rather than resuming at rows_done. Resuming would need a start-row
 * parameter through the materialiser, and it can only ever save work during the ~80-frame warm-up (the
 * census: after that the key set is FLAT and no entry grows again) — measured not worth the seam. */
/* OBJSH_SKEW_TABLE_ENTRIES (128 — census 98 on the worst leg, plus headroom, and a power of two for the
 * probe wrap) lives in blitter.h: the sweep's table section fills the table to capacity. */
#define OBJSH_SKEW_TABLE_MASK     (OBJSH_SKEW_TABLE_ENTRIES - 1)

typedef struct {
    const uint8_t *src;                 /* the gfx arena these bitmaps were built from */
    uint32_t src_off;
    int16_t stride;
    int16_t base_cells;
    int16_t rows_done;                  /* rows materialised so far; 0 marks a FREE entry */
    ObjshSkewBitmaps bm;
} ObjshSkewEntry;

/* NOT in BSS (1 MB memory diet, slice 2): 126 KB of table that only a blitter machine ever reads would
 * otherwise be linked into the .PRG's bss size on EVERY machine. rm_blit_bind_all places it in the free
 * TPA above the program when — and only when — the blitter route is bound. */
static ObjshSkewEntry *skew_table;

/* Latched by the first full-table decline. Once every entry belongs to another key, a first-sight key
 * can only be discovered by walking all 128 probes — a scan the route would then pay on EVERY blit for
 * the rest of the race. So the whole route retires to the CPU engine instead: byte-identical pixels
 * (the hybrid is the pinned fallback), a bounded cost, and rm_objsh_skew_full keeps counting so the
 * cadence trace shows it happened. The census says this is unreachable; the flush re-arms it.
 *
 * It starts LATCHED (the one .data initialiser here), which is also what makes an UNPLACED table safe:
 * until rm_blit_objshift_skew_table_place has run, the same single test that declines a full table
 * declines every call, so no path can dereference the null pointer. */
static int skew_table_full = 1;
/* Profiling (game_main.c's cadence tail): served from the table / first-sight materialise / grown to a
 * taller sprite / declined because the table was full. */
uint32_t rm_objsh_skew_hits, rm_objsh_skew_first, rm_objsh_skew_grows, rm_objsh_skew_full;

/* Open-addressed probe start. A shift/xor mix of the key fields — NOT load-bearing (a bad mix costs
 * probes, never correctness), which is why it avoids the 68000's 32-bit multiply: the previous
 * multiplicative mix cost two __mulsi3 calls on every BASE blit, far more than the whole probe walk it
 * was shortening. The fold is a `swap`+`eor` and the shifts are single instructions. */
static unsigned skew_table_hash(uint32_t src_off, int16_t stride, int base_cells) {
    unsigned h = src_off ^ (src_off >> 16) ^ ((unsigned)(uint16_t)stride << 3);
    h ^= h >> 7;
    return (h + (unsigned)base_cells) & OBJSH_SKEW_TABLE_MASK;
}

/* The entry for this sprite key, materialised to at least `rows` rows — claiming a free entry on first
 * sight. Returns 0 only when every entry is taken by another key (counted; the census says never). */
static const ObjshSkewBitmaps *skew_table_lookup(const uint8_t *src, uint32_t src_off, int16_t stride,
                                                 int rows, int base_cells) {
    if (skew_table_full) { rm_objsh_skew_full++; return 0; }   /* latched: decline without the dead scan */
    unsigned slot = skew_table_hash(src_off, stride, base_cells);
    for (int probe = 0; probe < OBJSH_SKEW_TABLE_ENTRIES; probe++) {
        ObjshSkewEntry *e = &skew_table[(slot + probe) & OBJSH_SKEW_TABLE_MASK];
        if (!e->rows_done) {                               /* free: this key is first-sight, claim it */
            e->src = src; e->src_off = src_off; e->stride = stride; e->base_cells = (int16_t)base_cells;
            e->rows_done = (int16_t)rows;
            rm_objsh_skew_first++;
            rm_objsh_skew_materialise(&e->bm, src, src_off, stride, rows, base_cells);
            return &e->bm;
        }
        if (e->src == src && e->src_off == src_off && e->stride == stride &&
            e->base_cells == (int16_t)base_cells) {
#if RM_SKEW_MUTATE == RM_SKEW_MUT_NOGROW
            rm_objsh_skew_hits++;                          /* mutation: an entry is never grown deeper */
#else
            if (rows > e->rows_done) {                     /* taller than we have: re-materialise deeper */
                e->rows_done = (int16_t)rows;
                rm_objsh_skew_grows++;
                rm_objsh_skew_materialise(&e->bm, src, src_off, stride, rows, base_cells);
            } else {
                rm_objsh_skew_hits++;
            }
#endif
            return &e->bm;
        }
    }
    skew_table_full = 1;
    rm_objsh_skew_full++;
    return 0;
}

/* TOTAL: a flush on an UNPLACED table is a no-op, not a null dereference. The F10 asset reload calls it
 * unconditionally, and on a machine whose tables were never placed (no blitter, or no room in the TPA)
 * there is nothing to flush and the route is already declining every call. */
void rm_blit_objshift_skew_table_flush(void) {
    if (!skew_table) return;
    for (int i = 0; i < OBJSH_SKEW_TABLE_ENTRIES; i++) skew_table[i].rows_done = 0;
    skew_table_full = 0;
}

uint32_t rm_blit_objshift_skew_table_bytes(void) {
    return (uint32_t)sizeof(ObjshSkewEntry) * OBJSH_SKEW_TABLE_ENTRIES;
}

void rm_blit_objshift_skew_table_place(void *mem) {
    skew_table = (ObjshSkewEntry *)mem;
}

/* Table lookup + blit, already in supervisor mode. The dispatch below reaches it through one Supexec;
 * the sweep's table section calls it directly (it runs the whole sweep inside one excursion), so both
 * pin the same code. */
int rm_blit_objshift_skew_tabled(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                                 uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                                 const uint8_t *color_pairs, int base_cells) {
    int rows = (int16_t)rows_m1 + 1;
    if (!objsh_skew_draws(x, rows_m1, rows, base_cells))
        return rows <= 0;                                  /* zero rows: handled no-op; else CPU hybrid */
    const ObjshSkewBitmaps *bm = skew_table_lookup(src, src_off, stride, rows, base_cells);
    if (!bm) return 0;                                     /* table full -> the CPU engine draws it */
    return rm_blit_objshift_skew_from(bm, dst, dst_off, x, color, rows_m1, color_pairs, base_cells);
}

/* ---- runtime dispatch + the boot binding (object_list.c's RM_BLIT_OBJSHIFT seam) ------------------
 * The family decision runs in USER mode so a clip case never pays the excursion; only a BASE draw enters
 * the Supexec, where the table lookup (RAM only, harmless in supervisor) and the blit passes run. */
static struct {
    uint8_t *dst; uint32_t dst_off; const uint8_t *src; uint32_t src_off;
    uint16_t x, color, rows_m1; int16_t stride; const uint8_t *pairs; int base_cells;
} g_skew;

static long objsh_skew_super(void) {
    return rm_blit_objshift_skew_tabled(g_skew.dst, g_skew.dst_off, g_skew.src, g_skew.src_off, g_skew.x,
                                        g_skew.color, g_skew.rows_m1, g_skew.stride, g_skew.pairs,
                                        g_skew.base_cells);
}

void rm_blit_objshift_dispatch(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                               uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                               const uint8_t *color_pairs, int base_cells) {
    int rows = (int16_t)rows_m1 + 1;
    if (!objsh_skew_draws(x, rows_m1, rows, base_cells)) {
        rm_blit_objshift_asm(dst, dst_off, src, src_off, x, color, rows_m1, stride, color_pairs,
                             base_cells);                  /* clip family / over-tall / no rows -> CPU */
        return;
    }
    g_skew.dst = dst; g_skew.dst_off = dst_off; g_skew.src = src; g_skew.src_off = src_off;
    g_skew.x = x; g_skew.color = color; g_skew.rows_m1 = rows_m1; g_skew.stride = stride;
    g_skew.pairs = color_pairs; g_skew.base_cells = base_cells;
    if (!Supexec(objsh_skew_super))                        /* declined (table full) -> CPU hybrid */
        rm_blit_objshift_asm(dst, dst_off, src, src_off, x, color, rows_m1, stride, color_pairs,
                             base_cells);
}

/* The RM_BLIT_OBJSHIFT seam (object_list.c), bound ONCE at boot — the objshift2 pattern (§11). Defaults
 * to the CPU asm engine so it is safe before boot and costs a plain ST nothing but one indirection. */
void (*rm_blit_objshift_fn)(uint8_t *, uint32_t, const uint8_t *, uint32_t, uint16_t, uint16_t, uint16_t,
                            int16_t, const uint8_t *, int) = rm_blit_objshift_asm;

void rm_blit_objshift_bind(int have_blitter) {
    rm_blit_objshift_fn = have_blitter ? rm_blit_objshift_dispatch : rm_blit_objshift_asm;
}
