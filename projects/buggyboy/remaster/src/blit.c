/* blit.c — remaster of the two fine-x (sub-pixel) 4-plane masked-sprite blit engines that the
 * roadside-object dispatcher feeds: blit_objshift (recreate's @0x14680, colour-indexed) and
 * blit_objshift2 (@0x13ed6, plain masked OR). Both shift each 16-pixel source column to an arbitrary
 * pixel x so a sprite straddles two 16-pixel destination columns (col0 = dst+aligned_col, col1 =
 * col0+8), walking one scanline up per row.
 *
 * These are the leaf writers under draw_object_list. Unlike recreate's single flat image, the
 * destination (framebuffer) and the source (sprite arena) are separate buffers here: `dst`/`dst_off`
 * name the target, `src`/`src_off` the sprite pixels. That is the only structural change — the shift/
 * mask/ladder arithmetic is transcribed 1:1 (16-bit register wraps mirrored with explicit
 * int16/uint16), so the output is byte-identical (see test/test_blit.py).
 */
#include "game.h"
#include "screen.h"
#include "st.h"
#include "blit_const.h"   /* OBJSH_CELL_BYTES / OBJSH2_* — shared with src/asm/objshift2.S (F11) */

/* Host-only invariant guard: enforces the pointer-walking non-wrap rule (see Offset in st.h) on the
 * 64-bit test build (clang, NDEBUG unset → assert is live), and compiles to nothing on the m68k
 * target (__m68k__), so the shipped blit costs no cycles for it. */
#ifdef __m68k__
#define RM_HOST_ASSERT(cond) ((void)0)
#else
#include <assert.h>
#define RM_HOST_ASSERT(cond) assert(cond)
#endif

/* ---- shared fine-x geometry ---- */
/* OBJSH_NIBBLE / OBJSH_SUBPX_BITS / COL_ALIGN / OBJSH_CELL_BYTES / OBJSH_RIGHT_BOUND / OBJSH_PLANES are
 * shared with the asm cores — defined in blit_const.h (included above), the single source for the blit
 * engines (F11).
 * (object.c carries a historical duplicate COL_ALIGN 0xfff8 of its own — see PERF30 A3 follow-ups.) */

static uint16_t objsh_aligned_col(uint16_t x) {
    return (uint16_t)((int16_t)x >> 1) & (uint16_t)COL_ALIGN;
}

/* Rotate a 32-bit value left (68k rol.l); count is 1..16 here. */
static uint32_t rotl32(uint32_t v, unsigned count) {
    count &= 31;
    return count ? ((v << count) | (v >> (32 - count))) : v;
}

/* Masked OR-in of one plane word into a destination column: keep the background where mask is set,
 * drop in the shifted pixels (68k `and.w mask,(ptr)` + `or.w pix,(ptr)`). All three fine-x engines
 * write through this by-pointer form (their cursors are real pointers — PERF30 P4 for objshift/
 * objshift2, C3 for objsprite). */
static void plane_write_p(uint8_t *dst_col, uint16_t mask, uint16_t pix) {
    wr16(dst_col, (uint16_t)((be16(dst_col) & mask) | pix));
}

/* ============================================================================================
 * blit_objshift @0x14680 — colour-indexed fine-x masked sprite blitter.
 *
 * The transparency SHOW mask is ~(A|B|C) & D from four source plane words, with a load-bearing
 * 0xFFFF high word (68k moveq #$ff seed) that rotates into the straddled column. Pixels are gated by
 * a per-plane colour fill (from color_pairs[colour]). Two width families: base_cells 1 (0x14680
 * "0x98") / 2 (0x144ac "0x90").
 * ============================================================================================ */
/* OBJSH_RIGHT_BOUND is shared with the asm core — defined in blit_const.h (included at the top). */
#define OBJSH_MASK_HI     0xffff0000u

static uint32_t objsh_build_mask_p(const uint8_t *src_words) {
    uint16_t a = be16(src_words), b = be16(src_words + 2), c = be16(src_words + 4), d = be16(src_words + 6);
    return OBJSH_MASK_HI | (uint16_t)(~(a | b | c) & d);
}

/* The four per-plane 16-bit colour-fill words (plane order 0..3 = fill_lo hi / fill_lo lo /
 * fill_hi hi / fill_hi lo — the asm's swap-toggled order), derived once per call and carried down
 * by value. Replaces the old per-plane objsh_fill_half, whose (plane<2 ? …)/(plane&1 ? …) ladder GCC
 * compiled into a per-plane compare + stack reload (PERF30 P1). */
typedef struct { uint16_t plane[OBJSH_PLANES]; } ObjshFill;

/* The three loop cursors carried by value between cells and rows: the two destination columns and the
 * source pointer. Passing this by value (not by pointer) keeps col0/col1/sp register-pinned once the
 * static cell helpers inline — the by-pointer shape address-took them and forced per-cell memory RMW
 * plus movel sp@,sp@ spill shuffling (PERF30 A1). The three fields are REAL pointers, not byte offsets
 * (PERF30 P4): the cell body reads/writes through them directly and the row loop steps them directly,
 * so GCC never rebuilds `dst + offset` per access nor re-adds the dst base with a per-row `lea`.
 * Byte-identical on both builds by the pointer-walking rule (see Offset in st.h); pinned by
 * test/test_blit_engines.py. */
typedef struct { uint8_t *col0, *col1; const uint8_t *sp; } ObjshCursor;

/* One plane of a STRADDLE cell: left-shift the source word across both columns, gate by this plane's
 * colour fill, drop the low half into col1 and the high half into col0. Split out so the 4-plane
 * unroll in objsh_straddle_cell is straight-line (PERF30 P2) — no loop counter, no per-plane branch.
 * always_inline so the value-passed cursor stays register-resident across the four calls (A1). */
static inline __attribute__((always_inline))
ObjshCursor objsh_straddle_plane(ObjshCursor cur, unsigned shl,
                                 uint16_t mask_hi, uint16_t mask_lo, ObjshFill fill, int plane) {
    uint16_t f = fill.plane[plane];
    int is_last = plane == OBJSH_PLANES - 1;
    uint32_t pix32 = (uint32_t)be16(cur.sp) << shl;
    cur.sp += 2;
    uint16_t pix_lo = (uint16_t)((pix32 & 0xffff) & f);
    uint16_t pix_hi = (uint16_t)((pix32 >> OBJSH_SUBPX_BITS) & f);
    if (is_last) { pix_lo &= (uint16_t)~mask_lo; pix_hi &= (uint16_t)~mask_hi; }
    plane_write_p(cur.col1, mask_lo, pix_lo);   /* col1 first */
    plane_write_p(cur.col0, mask_hi, pix_hi);
    cur.col0 += 2; cur.col1 += 2;
    return cur;
}

/* STRADDLE cell: 32-bit left shift straddles both columns; high half -> col0, low half -> col1.
 * Planes unrolled (PERF30 P2); plane 3 applies the transparency special case (~mask) inline.
 * always_inline (matching objsh_edge_cell): a second call site or compiler bump must not flip GCC's
 * called-once heuristic and reintroduce a real call that re-spills the value-passed cursor. */
static inline __attribute__((always_inline))
ObjshCursor objsh_straddle_cell(ObjshCursor cur, unsigned shl, ObjshFill fill) {
    uint32_t mask32 = rotl32(objsh_build_mask_p(cur.sp), shl);
    uint16_t mask_hi = (uint16_t)(mask32 >> OBJSH_SUBPX_BITS);   /* col0 */
    uint16_t mask_lo = (uint16_t)mask32;                         /* col1 */
    cur = objsh_straddle_plane(cur, shl, mask_hi, mask_lo, fill, 0);
    cur = objsh_straddle_plane(cur, shl, mask_hi, mask_lo, fill, 1);
    cur = objsh_straddle_plane(cur, shl, mask_hi, mask_lo, fill, 2);
    cur = objsh_straddle_plane(cur, shl, mask_hi, mask_lo, fill, 3);
    return cur;
}

/* One plane of an EDGE cell: single column, mask already reduced to the low word. RIGHT shifts the
 * source word right and walks col0; LEFT shifts left and walks col1 (is_right is a compile-time
 * constant at each call site, so the ternaries fold). Split out for the same straight-line 4-plane
 * unroll as the straddle cell (PERF30 P2). */
static inline __attribute__((always_inline))
ObjshCursor objsh_edge_plane(ObjshCursor cur, unsigned shift,
                             int is_right, uint16_t mask, ObjshFill fill, int plane) {
    uint16_t f = fill.plane[plane];
    int is_last = plane == OBJSH_PLANES - 1;
    uint16_t word = be16(cur.sp);
    cur.sp += 2;
    uint16_t pix = is_right ? (uint16_t)(word >> shift) : (uint16_t)((uint32_t)word << shift);
    pix = (uint16_t)(pix & f);
    if (is_last) pix &= (uint16_t)~mask;
    if (is_right) { plane_write_p(cur.col0, mask, pix); cur.col0 += 2; }
    else          { plane_write_p(cur.col1, mask, pix); cur.col1 += 2; }
    return cur;
}

/* EDGE cell (single on-screen column): mask built + shifted as the full 32-bit register (rol.l shl
 * for LEFT, lsr.l shr for RIGHT); low word gates the column. Planes unrolled (PERF30 P2), plane 3
 * inline. always_inline: it has two call sites, so GCC's size heuristic leaves it a real call
 * otherwise — which re-spills the cursor across the call and defeats the register-pinning. */
static inline __attribute__((always_inline))
ObjshCursor objsh_edge_cell(ObjshCursor cur, unsigned shift, int is_right, ObjshFill fill) {
    uint32_t m32 = objsh_build_mask_p(cur.sp);
    uint16_t mask = (uint16_t)(is_right ? (m32 >> shift) : rotl32(m32, shift));
    cur = objsh_edge_plane(cur, shift, is_right, mask, fill, 0);
    cur = objsh_edge_plane(cur, shift, is_right, mask, fill, 1);
    cur = objsh_edge_plane(cur, shift, is_right, mask, fill, 2);
    cur = objsh_edge_plane(cur, shift, is_right, mask, fill, 3);
    return cur;
}

enum objsh_family { OBJSH_CLIP, OBJSH_BASE, OBJSH_LEFT, OBJSH_RIGHT };

/* always_inline (like the cell helpers): keeps the value-passed cursor register-resident across the
 * row body instead of re-spilling it around a real call if GCC's heuristic ever demotes this. */
static inline __attribute__((always_inline))
ObjshCursor objsh_row(ObjshCursor cur, enum objsh_family fam, int straddle,
                      unsigned shl, unsigned shr, ObjshFill fill) {
    if (fam == OBJSH_LEFT) {
        cur = objsh_edge_cell(cur, shl, /*is_right=*/0, fill);
        cur.col0 += OBJSH_CELL_BYTES;
    }
    for (int i = 0; i < straddle; i++)
        cur = objsh_straddle_cell(cur, shl, fill);
    if (fam == OBJSH_RIGHT) {
        cur = objsh_edge_cell(cur, shr, /*is_right=*/1, fill);
        cur.col1 += OBJSH_CELL_BYTES;
    }
    return cur;
}

/* Colour-indexed fine-x blit. `stride` is the per-row src-stride word (recreate's blit_mode: 8 or
 * 0xa8). base_cells 1 / 2 select the width family. */
/* Per-function register-allocator override (m68k target only; clang ignores it on the host build, so
 * the differential tests still compile identical C). The straddle row loop is register-pressure-bound —
 * the L2 note in PERF30.md showed GCC spills the col0/col1/sp cursor triple to the stack under the
 * default IRA no matter how the C is shaped, and forcing residency by hand (local register vars) makes
 * it worse. -fira-region=one + -fira-algorithm=priority let the allocator FIND the better assignment
 * instead of us forcing it: measured bench_objlist_pass1 248,796 -> 231,480 cyc on top of the global
 * -O3 (the function itself: 199,152 -> 181,836, -17,316). Scoped to this ONE function on purpose — the same two flags REGRESS rm_blit_objshift2
 * (+4,440), so a per-file or global flag can't be used; the attribute is the only way to give objshift
 * the allocator lever without touching objshift2. Byte-identical (register choice is semantically
 * transparent) — pinned by test/test_blit_engines.py + run_golden.py. Keep paired with -O3 in
 * build_game.sh / bench_build.sh. See PERF30.md "GCC-level sweep". */
__attribute__((optimize("-fira-region=one", "-fira-algorithm=priority")))
void rm_blit_objshift(uint8_t *dst, Offset dst_off, const uint8_t *src, uint32_t src_off,
                      uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                      const uint8_t *color_pairs, int base_cells) {
    unsigned fine_x = (unsigned)(x & OBJSH_NIBBLE);
    unsigned shl = OBJSH_SUBPX_BITS - fine_x;
    unsigned shr = fine_x;

    uint16_t col_off = (uint16_t)((color & OBJSH_NIBBLE) << 3);

    /* P1: read the four per-plane 16-bit colour-fill words once per call (plane order at the
     * ObjshFill typedef; offsets +0/+2/+4/+6 are the two fill pairs' hi/lo halves in that order). */
    ObjshFill fill;
    fill.plane[0] = be16(color_pairs + col_off);
    fill.plane[1] = be16(color_pairs + col_off + 2);
    fill.plane[2] = be16(color_pairs + col_off + 4);
    fill.plane[3] = be16(color_pairs + col_off + 6);

    int16_t A = (int16_t)objsh_aligned_col(x);
    int16_t base_ceiling = (int16_t)(OBJSH_RIGHT_BOUND - OBJSH_CELL_BYTES * (base_cells - 1));

    enum objsh_family fam;
    int straddle, skips = 0;
    if (A < 0) {
        int k = (int)(-A) / OBJSH_CELL_BYTES;
        if (k > base_cells) return;                       /* off the left edge */
        fam = OBJSH_LEFT; straddle = base_cells - k; skips = k - 1;
    } else if ((int16_t)(A - base_ceiling) >= 0) {
        int s = (OBJSH_RIGHT_BOUND - A) / OBJSH_CELL_BYTES;
        if (s < 0) return;                                /* off the right edge */
        fam = OBJSH_RIGHT; straddle = s;
    } else {
        fam = OBJSH_BASE; straddle = base_cells;
    }

    int rows = (int16_t)rows_m1 + 1;

    /* Form each cursor from its (non-wrapping, non-negative) byte offset once, then walk the pointer
     * (pointer-walking rule: see Offset in st.h). */
    Offset col0_off = (dst_off + sx16((uint16_t)A)) + (uint32_t)(OBJSH_CELL_BYTES * skips);
    RM_HOST_ASSERT((int32_t)col0_off >= 0);   /* enforce the non-wrap invariant on the host build */
    ObjshCursor cur;
    cur.sp = src + src_off + (uint32_t)(OBJSH_CELL_BYTES * skips);
    cur.col0 = dst + col0_off;
    cur.col1 = cur.col0 + OBJSH_CELL_BYTES;

    /* The per-row bookkeeping is a constant step in disguise: every family advances both columns AND the
     * source by 8*total_cells per row, then rewinds 0xa8+8*(total_cells-1) (dst) / stride+8*(total_cells
     * -1) (src). The total_cells terms cancel, so the net per-row step is constant — both columns move
     * one scanline up (−SCREEN_ROW_BYTES) and the source steps OBJSH_CELL_BYTES − stride. Save the
     * row-start cursor, run the row's writes, then set the next row from row-start + the constant delta
     * (col1 stays col0 + OBJSH_CELL_BYTES). sp_step is signed: stride > 8 makes it negative (the source
     * walks back) — a real host pointer can't wrap it, so the sign must be real (see Offset in st.h). */
    int32_t sp_step = OBJSH_CELL_BYTES - sx16((uint16_t)stride);
    for (int row = 0; row < rows; row++) {
        uint8_t *row_col0 = cur.col0;
        const uint8_t *row_sp = cur.sp;
        cur = objsh_row(cur, fam, straddle, shl, shr, fill);
        cur.col0 = row_col0 - SCREEN_ROW_BYTES;
        cur.col1 = cur.col0 + OBJSH_CELL_BYTES;
        cur.sp = row_sp + sp_step;
    }
}

/* ============================================================================================
 * blit_objshift2 @0x13ed6 — plain (no colour) fine-x masked sprite blitter. SHOW mask is ~(w0|w1)
 * from two source words; pixels copied plain-shifted and OR'd. Three width families
 * (width_idx 0/1/2 = base ceiling 0x88/0x90/0x98).
 * ============================================================================================ */
/* OBJSH2_RIGHT_BOUND / OBJSH2_LADDER_STEP / OBJSH2_BASE_STRADDLE / OBJSH2_SRC_ROW_BYTES are shared with
 * the asm core — defined in blit_const.h (included at the top). */
#define OBJSH2_MASK_INIT   0xffffffffu

/* objshift2 carries the same {col0, col1, sp} cursor triple but is NOT value-passed: unlike objshift its
 * baseline has no mem-to-mem cursor shuffle, and its cost is arithmetic/RMW-bound. Forcing the cursors
 * register-resident across the row loop (the value-struct A1 shape) only steals the address registers
 * the RMW cell needs and spills the loop counter instead (measured +1.98 ms, PERF30 A1) — so the
 * by-pointer calling shape stays. The pointees are REAL pointers (uint8_t **), not byte offsets
 * (PERF30 P4b): the cell writes through them (wr32(*col0)) and the row loop steps them directly, so GCC
 * no longer rebuilds each row's column pointers with a base+index `lea %a5@(0,%d3:l)`. Byte-identical by
 * the pointer-walking rule (see Offset in st.h). */
/* always_inline: the C1 fall-through switch in objsh2_row calls this from three case labels, which
 * trips GCC's called-more-than-once heuristic into emitting a real call — and a real call spills the
 * by-pointer (uint8_t **) cursor args to memory (the A1 wall). Forcing the three straight-line inlined
 * copies is the whole point of C1 (no per-cell loop control), so pin the inline. */
static inline __attribute__((always_inline))
void objsh2_straddle_cell(uint8_t **col0, uint8_t **col1, const uint8_t **sp, unsigned shl) {
    uint16_t w0 = be16(*sp);
    uint16_t w1 = be16(*sp + 2);
    uint32_t mask_col0 = OBJSH2_MASK_INIT;
    mask_col0 = (mask_col0 & 0xffff0000u) | w0;
    mask_col0 = (mask_col0 & 0xffff0000u) | (uint16_t)(mask_col0 | w1);
    mask_col0 = (mask_col0 & 0xffff0000u) | (uint16_t)(~mask_col0);
    mask_col0 = rotl32(mask_col0, shl);
    uint32_t mask_col1 = dup16((uint16_t)mask_col0);
    uint32_t swapped = (mask_col0 >> 16) | (mask_col0 << 16);
    mask_col0 = (mask_col0 & 0xffff0000u) | (uint16_t)swapped;
    wr32(*col0, be32(*col0) & mask_col0);
    wr32(*col1, be32(*col1) & mask_col1);

    /* The two straddle-pixel iterations unrolled straight-line (PERF30 L1): with fixed base pointers
     * and +0/+2 displacements GCC emits cheap displacement addressing (col@/col@(2)) and zero loop
     * control, where the rolled 2-iteration loop compiled to indexed `col@(0,i:l)` reads/RMWs plus
     * per-iteration counter arithmetic. Source read order and the col1-then-col0 write order per
     * iteration are preserved; the two iterations write disjoint 2-byte cells, so this is byte-exact. */
    uint8_t *c0 = *col0, *c1 = *col1;
    const uint8_t *s = *sp;
    uint32_t pix0 = (uint32_t)be16(s) << shl;
    wr16(c1, (uint16_t)(be16(c1) | (uint16_t)pix0));
    wr16(c0, (uint16_t)(be16(c0) | (uint16_t)(pix0 >> 16)));
    uint32_t pix1 = (uint32_t)be16(s + 2) << shl;
    wr16(c1 + 2, (uint16_t)(be16(c1 + 2) | (uint16_t)pix1));
    wr16(c0 + 2, (uint16_t)(be16(c0 + 2) | (uint16_t)(pix1 >> 16)));
    *sp = s + 4;
    *col0 = c0 + 4; *col1 = c1 + 4;

    wr32(*col0, (be32(*col0) & mask_col0) | ~mask_col0);
    *col0 += 4;
    wr32(*col1, (be32(*col1) & mask_col1) | ~mask_col1);
    *col1 += 4;
}

static void objsh2_left_edge_cell(uint8_t **col0, uint8_t **col1, const uint8_t **sp, unsigned shl) {
    uint32_t both = be32(*sp);
    /* lo = low word OR high word of the long be32 already loaded; the high word IS be16(*sp)
     * (bytes [0,1]) — reuse the loaded halves instead of re-reading (PERF30 L1). Byte-equivalent. */
    uint16_t lo = (uint16_t)((uint16_t)both | (uint16_t)(both >> 16));
    *sp += 2;
    uint16_t mask = (uint16_t)(~(uint16_t)(lo << shl));
    uint32_t mask_col1 = dup16(mask);
    wr32(*col1, be32(*col1) & mask_col1);
    uint16_t w0 = (uint16_t)(both >> 16);
    wr16(*col1, (uint16_t)(be16(*col1) | (uint16_t)(w0 << shl)));
    *col1 += 2;
    uint16_t w1 = be16(*sp);
    *sp += 2;
    wr16(*col1, (uint16_t)(be16(*col1) | (uint16_t)(w1 << shl)));
    *col1 += 2;
    wr32(*col1, (be32(*col1) & mask_col1) | ~mask_col1);
    *col1 += 4;
    *col0 += OBJSH_CELL_BYTES;
}

static void objsh2_right_edge_cell(uint8_t **col0, uint8_t **col1, const uint8_t **sp, unsigned shr) {
    uint32_t both = be32(*sp);
    /* lo = low word OR high word of the long be32 already loaded; the high word IS be16(*sp)
     * (bytes [0,1]) — reuse the loaded halves instead of re-reading (PERF30 L1). Byte-equivalent. */
    uint16_t lo = (uint16_t)((uint16_t)both | (uint16_t)(both >> 16));
    *sp += 2;
    uint16_t mask = (uint16_t)(~(uint16_t)(lo >> shr));
    uint32_t mask_col0 = dup16(mask);
    wr32(*col0, be32(*col0) & mask_col0);
    uint16_t w0 = (uint16_t)(both >> 16);
    wr16(*col0, (uint16_t)(be16(*col0) | (uint16_t)(w0 >> shr)));
    *col0 += 2;
    uint16_t w1 = be16(*sp);
    *sp += 2;
    wr16(*col0, (uint16_t)(be16(*col0) | (uint16_t)(w1 >> shr)));
    *col0 += 2;
    wr32(*col0, (be32(*col0) & mask_col0) | ~mask_col0);
    *col0 += 4;
    *col1 += OBJSH_CELL_BYTES;
}

enum objsh2_edge { OBJSH2_EDGE_NONE, OBJSH2_EDGE_LEFT, OBJSH2_EDGE_RIGHT };

static void objsh2_row(uint8_t **col0, uint8_t **col1, const uint8_t **sp,
                       enum objsh2_edge edge, int straddle, unsigned shl, unsigned shr) {
    if (edge == OBJSH2_EDGE_LEFT) objsh2_left_edge_cell(col0, col1, sp, shl);
    /* straddle is 0..3 and loop-invariant per call, so specialize the cell run as a fall-through
     * switch instead of a counted loop (PERF30 C1): each case is straight-line (no per-cell
     * addql/cmpl/bne loop control, ~23 cyc/cell) and lets GCC schedule across cell boundaries. The
     * switch itself compiles to a compare chain (-fno-jump-tables) evaluated once per row, not per
     * cell. Byte-exact: same objsh2_straddle_cell calls in the same order. */
    switch (straddle) {
        case OBJSH2_BASE_STRADDLE:     objsh2_straddle_cell(col0, col1, sp, shl); /* fallthrough */
        case OBJSH2_BASE_STRADDLE - 1: objsh2_straddle_cell(col0, col1, sp, shl); /* fallthrough */
        case OBJSH2_BASE_STRADDLE - 2: objsh2_straddle_cell(col0, col1, sp, shl); /* fallthrough */
        default: break;
    }
    if (edge == OBJSH2_EDGE_RIGHT) objsh2_right_edge_cell(col0, col1, sp, shr);
}

/* This is the byte-exact REFERENCE. On the m68k builds -DRM_ASM_BLIT (via RM_ASM_OBJSHIFT2) points the
 * dispatcher's RM_BLIT_OBJSHIFT2 macro at the hand-written core rm_blit_objshift2_asm (src/asm/
 * objshift2.S); this C is still compiled and pinned equal to the asm by test/test_asm_blit.py. */
void rm_blit_objshift2(uint8_t *dst, Offset dst_off, const uint8_t *src, uint32_t src_off,
                       uint16_t x, uint16_t rows_m1, int width_idx) {
    unsigned fine_x = (unsigned)(x & OBJSH_NIBBLE);
    unsigned shl = OBJSH_SUBPX_BITS - fine_x;
    unsigned shr = fine_x;

    int16_t col = (int16_t)((int16_t)(uint16_t)x >> 1) & (int16_t)COL_ALIGN;
    int16_t base_ceiling = (int16_t)(OBJSH2_RIGHT_BOUND + OBJSH2_LADDER_STEP * width_idx);
    /* Real pointers, not byte offsets (PERF30 P4b — see the cell-helper comment). Form col0 from its
     * (non-wrapping, non-negative) offset once, then walk the pointer (pointer-walking rule: Offset in
     * st.h). */
    Offset col0_off = dst_off + sx16((uint16_t)col);
    RM_HOST_ASSERT((int32_t)col0_off >= 0);   /* enforce the non-wrap invariant on the host build */
    uint8_t *col0 = dst + col0_off;
    const uint8_t *sp = src + src_off;

    enum objsh2_edge edge;
    int straddle;

    if (col < 0) {
        int16_t c = col;
        int rung;
        edge = OBJSH2_EDGE_LEFT; straddle = -1;
        for (rung = width_idx; rung <= OBJSH2_BASE_STRADDLE - 1; rung++) {
            c = (int16_t)(c + OBJSH2_LADDER_STEP);
            if (c >= 0) { straddle = (OBJSH2_BASE_STRADDLE - 1) - rung; break; }
            if (rung < OBJSH2_BASE_STRADDLE - 1) { sp += 4; col0 += OBJSH_CELL_BYTES; }
        }
        if (straddle < 0) return;                         /* off the left edge */
    } else if ((int16_t)(col - base_ceiling) >= 0) {
        int16_t c = (int16_t)(col - OBJSH2_RIGHT_BOUND);
        c = (int16_t)(c - OBJSH2_LADDER_STEP);
        if (c < 0) straddle = 2;
        else {
            c = (int16_t)(c - OBJSH2_LADDER_STEP);
            if (c < 0) straddle = 1;
            else {
                c = (int16_t)(c - OBJSH2_LADDER_STEP);
                if (c < 0) straddle = 0;
                else return;                              /* off the right edge */
            }
        }
        edge = OBJSH2_EDGE_RIGHT;
    } else {
        edge = OBJSH2_EDGE_NONE;
        straddle = OBJSH2_BASE_STRADDLE - width_idx;
    }

    /* Same constant-step fold as objshift: each row advances both columns by 8*cells and the source by
     * 4*cells, then rewinds 8*cells+160 (dst) / 4*cells+80 (src). The cells terms cancel, so the net
     * per-row step is constant — both columns one scanline up (−SCREEN_ROW_BYTES), the source back one
     * sprite row (−OBJSH2_SRC_ROW_BYTES). Save the row-start cursors, run the row's writes, then set the
     * next row from row-start + the constant delta (col1 stays col0 + OBJSH_CELL_BYTES). Both deltas are
     * always negative here — no stride word — so no signed-step subtlety (cf. objshift). */
    uint8_t *col1 = col0 + OBJSH_CELL_BYTES;
    int rows = (int16_t)rows_m1 + 1;
    for (int row = 0; row < rows; row++) {
        uint8_t *row_col0 = col0;
        const uint8_t *row_sp = sp;
        objsh2_row(&col0, &col1, &sp, edge, straddle, shl, shr);
        col0 = row_col0 - SCREEN_ROW_BYTES;
        col1 = col0 + OBJSH_CELL_BYTES;
        sp = row_sp - OBJSH2_SRC_ROW_BYTES;
    }
}

/* ============================================================================================
 * objsprite engine @0x131f6 — the third fine-x blitter (the sibling of blit_objshift2). Same three-
 * primitive shell (straddle / left-edge / right-edge) and the same col0/col1 pairing, but its SHOW
 * mask is built from FOUR source words ~(w0|w1|w2)&w3 (the blit_transp_cell / objsh_build_mask
 * formula, 0xFFFF high word) and there is NO colour indexing — pixels are copied plain-shifted and
 * OR'd. Four width families width_idx 0..3 (WIDTH 0x80/0x88/0x90/0x98). PURE LEAF. Used by the
 * roadside-object dispatcher's t1/t2/t4/w88/t53 handlers.
 *
 * Real-pointer cursors like its two sibling engines (PERF30 C3, applying the P4 mechanism here): the
 * cells walk col0/col1/sp as pointers via local copies, so -O3 already unrolls the plane loops to
 * displacement addressing (the P2 shape — no explicit unroll needed here). This family is cold on the
 * gate frame (rm_objsprite ≈ 2.1 ms of objlist pass 1), but the conversion is byte-exact and drops the
 * offset-wrapper helpers (plane_write / objsh_build_mask) that existed only for it.
 * ============================================================================================ */
#define OBJSP_WIDTH_80    0x80    /* width_idx 0 base width; WIDTH = this + 8*width_idx */
#define OBJSP_WIDTHS      4       /* four width families */
#define OBJSP_LADDER_STEP 8
#define OBJSP_REWIND_C0   0xc0    /* per-row rewind base (col/src step back = this - 8*rung) */
#define OBJSP_BASE_CELLS  4       /* BASE straddle cells for width_idx 0 (4 - width_idx) */

/* STRADDLE cell: like objsh but no colour fill (pixels copied plain). Real-pointer cursors (PERF30
 * C3/P4): the cell reads the source and writes both columns through the real pointers directly (local
 * copies walked with displacement addressing), so GCC no longer rebuilds a dst+offset base+index per
 * plane word. Byte-identical by the pointer-walking rule (see Offset in st.h). */
static void objsp_straddle_cell(uint8_t **col0, uint8_t **col1, const uint8_t **sp, unsigned shl) {
    const uint8_t *s = *sp;
    uint8_t *c0 = *col0, *c1 = *col1;
    uint32_t mask32 = rotl32(objsh_build_mask_p(s), shl);
    uint16_t col0_mask = (uint16_t)(mask32 >> OBJSH_SUBPX_BITS);
    uint16_t col1_mask = (uint16_t)mask32;
    for (int plane = 0; plane < OBJSH_PLANES; plane++) {
        uint32_t pix32 = (uint32_t)be16(s) << shl;
        s += 2;
        uint16_t col1_pix = (uint16_t)pix32;
        uint16_t col0_pix = (uint16_t)(pix32 >> OBJSH_SUBPX_BITS);
        if (plane == OBJSH_PLANES - 1) {
            col1_pix = (uint16_t)(col1_pix & (uint16_t)~col1_mask);
            col0_pix = (uint16_t)(col0_pix & (uint16_t)~col0_mask);
        }
        plane_write_p(c1, col1_mask, col1_pix);   /* col1 first */
        plane_write_p(c0, col0_mask, col0_pix);
        c0 += 2; c1 += 2;
    }
    *sp = s; *col0 = c0; *col1 = c1;
}

/* LEFT-EDGE cell: only col1 drawn, mask rol.l'd (low word used), pixels shift left as words. */
static void objsp_left_edge_cell(uint8_t **col1, const uint8_t **sp, unsigned shl) {
    const uint8_t *s = *sp;
    uint8_t *c1 = *col1;
    uint16_t mask = (uint16_t)rotl32(objsh_build_mask_p(s), shl);
    for (int plane = 0; plane < OBJSH_PLANES; plane++) {
        uint16_t pix = (uint16_t)((uint32_t)be16(s) << shl);
        s += 2;
        if (plane == OBJSH_PLANES - 1) pix = (uint16_t)(pix & (uint16_t)~mask);
        plane_write_p(c1, mask, pix);
        c1 += 2;
    }
    *sp = s; *col1 = c1;
}

/* RIGHT-EDGE cell: only col0 drawn, mask lsr.l'd by shr, pixels shift right as words. */
static void objsp_right_edge_cell(uint8_t **col0, const uint8_t **sp, unsigned shr) {
    const uint8_t *s = *sp;
    uint8_t *c0 = *col0;
    uint16_t mask = (uint16_t)(objsh_build_mask_p(s) >> shr);
    for (int plane = 0; plane < OBJSH_PLANES; plane++) {
        uint16_t pix = (uint16_t)(be16(s) >> shr);
        s += 2;
        if (plane == OBJSH_PLANES - 1) pix = (uint16_t)(pix & (uint16_t)~mask);
        plane_write_p(c0, mask, pix);
        c0 += 2;
    }
    *sp = s; *col0 = c0;
}

enum objsp_family { OBJSP_CLIP, OBJSP_BASE, OBJSP_LEFT, OBJSP_WIDE };

static void objsp_row(uint8_t **col0, uint8_t **col1, const uint8_t **sp,
                      enum objsp_family fam, int straddle, unsigned shl, unsigned shr) {
    if (fam == OBJSP_LEFT) {
        objsp_left_edge_cell(col1, sp, shl);
        *col0 += OBJSH_CELL_BYTES;
    }
    for (int i = 0; i < straddle; i++)
        objsp_straddle_cell(col0, col1, sp, shl);
    if (fam == OBJSP_WIDE) {
        objsp_right_edge_cell(col0, sp, shr);
        *col1 += OBJSH_CELL_BYTES;
    }
}

/* The shared parameterized objsprite core (@0x13206). width_idx = (WIDTH - 0x80)/8 selects the
 * width bound + the entry rung of both clip ladders. col0_init = dst_off + aligned_col. */
static void objsp_core(uint8_t *dst, const uint8_t *src, uint16_t aligned_col, unsigned shl,
                       unsigned shr, uint16_t rows_m1, Offset col0_init, uint32_t src_init,
                       int width_idx) {
    RM_HOST_ASSERT((int32_t)col0_init >= 0);   /* enforce the non-wrap invariant on the host build */
    uint8_t *col0 = dst + col0_init;
    const uint8_t *sp = src + src_init;
    enum objsp_family fam;
    int straddle, rung;

    if ((int16_t)aligned_col < 0) {
        int16_t col_walk = (int16_t)aligned_col;
        fam = OBJSP_CLIP;
        for (rung = width_idx; rung < OBJSP_WIDTHS; rung++) {
            col_walk = (int16_t)(col_walk + OBJSP_LADDER_STEP);
            if (col_walk >= 0) { fam = OBJSP_LEFT; break; }
            sp += OBJSH_CELL_BYTES;
            col0 += OBJSH_CELL_BYTES;
        }
        if (fam == OBJSP_CLIP) return;                    /* fully off-left */
        straddle = (OBJSP_WIDTHS - 1) - rung;
    } else {
        int16_t width = (int16_t)(OBJSP_WIDTH_80 + OBJSP_LADDER_STEP * width_idx);
        int16_t col_walk = (int16_t)((int16_t)aligned_col - width);
        if (col_walk < 0) {
            fam = OBJSP_BASE;
            straddle = OBJSP_BASE_CELLS - width_idx;
            rung = width_idx;
        } else {
            fam = OBJSP_CLIP;
            for (rung = width_idx; rung < OBJSP_WIDTHS; rung++) {
                col_walk = (int16_t)(col_walk - OBJSP_LADDER_STEP);
                if (col_walk < 0) { fam = OBJSP_WIDE; break; }
            }
            if (fam == OBJSP_CLIP) return;                /* fully off-right */
            straddle = (OBJSP_WIDTHS - 1) - rung;
        }
    }

    /* Per-row rewind = 0xc0 − 8*rung, subtracted equally from both columns and the source (all now real
     * pointers — PERF30 C3/P4). rewind is always positive here (rung 0..3), so the cursors walk back up
     * one scanline; no signed-step subtlety (cf. objshift's stride). The constant-step fold that helped
     * objshift2 is byte-exact here too (net step is −SCREEN_ROW_BYTES for all three) but measured a
     * no-op on this frame, so the faithful rewind form is kept (PERF30 C3c). */
    uint16_t rewind = (uint16_t)(OBJSP_REWIND_C0 - OBJSP_LADDER_STEP * rung);
    uint8_t *col1 = col0 + OBJSH_CELL_BYTES;
    int rows = (int16_t)rows_m1 + 1;
    for (int row = 0; row < rows; row++) {
        objsp_row(&col0, &col1, &sp, fam, straddle, shl, shr);
        col0 -= sx16(rewind);
        col1 -= sx16(rewind);
        sp -= sx16(rewind);
    }
}

/* Fine-x prologue (@0x131f6): derive fine_x/shl/shr + aligned_col from x, add the aligned column
 * into the dst, then run the core. `width_idx` folds in the width immediate (t4=0, w88=1, t2=2,
 * t1=3). */
void rm_objsprite(uint8_t *dst, Offset dst_off, const uint8_t *src, uint32_t src_off,
                  uint16_t x, uint16_t rows_m1, int width_idx) {
    unsigned fine_x = (unsigned)(x & OBJSH_NIBBLE);
    unsigned shl = OBJSH_SUBPX_BITS - fine_x;
    unsigned shr = fine_x;
    uint16_t col = objsh_aligned_col(x);
    Offset col0_init = (Offset)(dst_off + sx16(col));
    objsp_core(dst, src, col, shl, shr, rows_m1, col0_init, src_off, width_idx);
}

/* Alt entry (@0x13204, t53): the caller pre-computes aligned_col / shl / shr; skips the fine-x calc.
 * Joins the width-0x80 dispatch. */
void rm_objsprite_alt(uint8_t *dst, Offset dst_off, const uint8_t *src, uint32_t src_off,
                      uint16_t aligned_col, unsigned shl, unsigned shr, uint16_t rows_m1) {
    Offset col0_init = (Offset)(dst_off + sx16(aligned_col));
    objsp_core(dst, src, aligned_col, shl, shr, rows_m1, col0_init, src_off, 0);
}
