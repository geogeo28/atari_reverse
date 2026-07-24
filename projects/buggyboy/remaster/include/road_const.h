/* road_const.h — render_road engine constants shared by the C references (src/road.c) and the
 * hand-written m68k band cores (src/asm/road_band.S). ONE source of truth (CLAUDE.md §5): these
 * literals were road.c #defines; the band-B/D hand-asm cores (PERF30 road-asm slices 1-2) need the same
 * values, so they are hoisted here — exactly the blit_const.h precedent for the objshift cores.
 *
 * #define-ONLY so it is safe to #include from a .S file: the m68k builds run cpp over road_band.S,
 * then the assembler sees the expanded text — anything but preprocessor directives would break
 * assembly. Any macro road_band.S actually references as an immediate (RR_FB_* bit numbers / RR_SRC_* /
 * RR_MASK_OFF_* / RR_CONST_* / RR_OFF_* / RR_ROW_*) is bare (no `u`/`L` suffix GNU as would reject).
 * The RR_F_* flag MASKS keep their `u` suffix because they are used ONLY by the C reference (the asm
 * tests flags with `btst #RR_FB_*` bit numbers, never the mask) — unused macros are never expanded into
 * the assembled text, and the `u` is load-bearing for the C: dropping it made the per-row flag tests
 * emit signed-int code and regressed the road ~8k cyc (measured).
 */
#ifndef RM_ROAD_CONST_H
#define RM_ROAD_CONST_H

#include "screen.h"                      /* SCREEN_ROW_BYTES (asm-safe: C-only parts behind __ASSEMBLER__) */

/* Per-core selection (mirrors game.h's RM_ASM_BLIT -> RM_ASM_OBJSHIFT* pattern): the m68k builds pass the
 * umbrella -DRM_ASM_ROAD, which turns on each band's individual core flag. Slice 1 = band D
 * (RM_ASM_RR_BAND_D), slice 2 = band B (RM_ASM_RR_BAND_B), slice 3 = band C (RM_ASM_RR_BAND_C, gating BOTH
 * the near and far C cores — they always ship together, so one flag keeps the umbrella simple) then band A
 * (RM_ASM_RR_BAND_A) — with A asm too the whole road is asm. Only road.c's RR_BAND_?_FN dispatch keys off a
 * flag; road_band.S assembles the cores unconditionally and
 * road.c compiles the C references unconditionally (as blit.c/objshift2.S do), so undefining one flag A/Bs
 * that band on every build without pulling code in and out. */
#ifdef RM_ASM_ROAD
#  ifndef RM_ASM_RR_BAND_D
#    define RM_ASM_RR_BAND_D
#  endif
#  ifndef RM_ASM_RR_BAND_B
#    define RM_ASM_RR_BAND_B
#  endif
#  ifndef RM_ASM_RR_BAND_C
#    define RM_ASM_RR_BAND_C
#  endif
#  ifndef RM_ASM_RR_BAND_A
#    define RM_ASM_RR_BAND_A
#  endif
#endif

/* ---- entry setup ---- */
#define RR_DST_ROAD_OFF   0x4100     /* dst = fb->px + this: top of the on-screen road band (row 104) */
#define RR_ROW_STRIDE_D2  SCREEN_ROW_BYTES   /* 160 bytes / scanline (the framebuffer row stride, d2) */

/* ---- inter-band-group step ---- */
#define RR_DST_BAND_STEP  0x3c00     /* dst -= this between groups (rewind up to the road band top) */
#define RR_SRC_BAND_STEP  0x0a00     /* tex base += this between groups (next texture sub-block) */
#define RR_EDGE_BAND_STEP 0x00c0     /* edge cursor -= this between groups */

/* ---- per-band scanline counts the pipeline dbf's (rows_m1: drawn count-1) ---- */
#define RR_ROWS_A         0x5f       /* band A: 96 scanlines (dbf count = rows-1) */
#define RR_ROWS_B_NEAR    0x04       /* band B near copy */
#define RR_ROWS_B_FAR     0x5a       /* band B far copy  */
#define RR_ROWS_C_NEAR    0x05       /* band C near copy */
#define RR_ROWS_C_FAR     0x59       /* band C far copy  */
#define RR_ROWS_D_NEAR    0x05       /* band D near copy */
#define RR_ROWS_D_FAR     0x59       /* band D far copy  */

/* ---- per-scanline edge-mask reads (mask = be32(src + off), src = tex origin + fine_x) ---- */
#define RR_MASK_OFF_HI    0x2808     /* bands A/B */
#define RR_MASK_OFF_LO    0x2800     /* bands C/D */

/* ---- control-longword flag BIT NUMBERS (the asm's `btst #RR_FB_*, %d0`) ---- */
#define RR_FB_MASK_A      16         /* band B: read edge mask, clear left fill */
#define RR_FB_SPLIT_B     17         /* band B: row has an edge split (else full-width fill) */
#define RR_FB_SPLIT_A     18         /* band A: edge split present (else centre-run) */
#define RR_FB_SPLIT_C     19         /* band C: edge split present */
#define RR_FB_SPLIT_D     20         /* band D: edge split present */
#define RR_FB_SRC_400     21         /* src sub-offset selector (+0x400) */
#define RR_FB_SRC_100     22         /* src sub-offset selector (+0x100) / fill-side selector */
#define RR_FB_WIDE        23         /* wide/solid-centre branch (vs the edge-split blit) */
#define RR_FB_MASK_A2     24         /* band D: read edge mask (near group) */
#define RR_FB_PLANE_HI    27         /* swap hi plane pattern and select an alternate src region */
#define RR_FB_SRC_CONST   28         /* select the const edge texture (when the control long >= 0) */
#define RR_FB_SKIP_ABC    29         /* bands A/B: gate for the edge-split fast path */
#define RR_FB_SKIP_D      30         /* bands C/D: gate for the edge-split fast path */

/* ---- the same flags as MASKS, for the C reference (`ctrl & RR_F_*`) ---- */
#define RR_F_MASK_A       (1u << RR_FB_MASK_A)
#define RR_F_SPLIT_B      (1u << RR_FB_SPLIT_B)
#define RR_F_SPLIT_A      (1u << RR_FB_SPLIT_A)
#define RR_F_SPLIT_C      (1u << RR_FB_SPLIT_C)
#define RR_F_SPLIT_D      (1u << RR_FB_SPLIT_D)
#define RR_F_SRC_400      (1u << RR_FB_SRC_400)
#define RR_F_SRC_100      (1u << RR_FB_SRC_100)
#define RR_F_WIDE         (1u << RR_FB_WIDE)
#define RR_F_MASK_A2      (1u << RR_FB_MASK_A2)
#define RR_F_PLANE_HI     (1u << RR_FB_PLANE_HI)
#define RR_F_SRC_CONST    (1u << RR_FB_SRC_CONST)
#define RR_F_SKIP_ABC     (1u << RR_FB_SKIP_ABC)
#define RR_F_SKIP_D       (1u << RR_FB_SKIP_D)

/* ---- const edge-texture strips (STATIC region), as offsets into `edge_const` (base 0x15b7a) ---- */
#define RR_CONST_5B7A     0x00
#define RR_CONST_5B9A     0x20
#define RR_CONST_5BAA     0x30
/* ---- src sub-region deltas added to `src` (the buf_b texture) per the flags ---- */
#define RR_SRC_A800       0xa800
#define RR_SRC_5800       0x5800
#define RR_SRC_5000       0x5000
#define RR_SRC_4700       0x4700
#define RR_SRC_3E00       0x3e00
#define RR_SRC_3500       0x3500
#define RR_SRC_0A00       0x0a00
#define RR_SRC_0400       0x0400
#define RR_SRC_0100       0x0100

#define RR_D7_WORD_MASK   0xfff8     /* masks the road half-width to a column-aligned (8-byte) offset */
#define RR_ROW_LONG_PAIRS 20         /* a 160-byte scanline = 20 (fill_lo, fill_hi) long pairs */
/* dbf counts (one less than the iteration count) for the three full-row fill shapes in road_band.S:
 *   _DBF      — quad-store fill (4 longs = 2 pairs per iteration): RR_ROW_LONG_PAIRS/2 iterations. Used by
 *               every core's full-row (col >= stride) fill.
 *   _PAIR_DBF — pair-store fill of the whole row (no edge cell): RR_ROW_LONG_PAIRS pairs. Bands B far and A
 *               fast-split, col<0, col+8<0.
 *   _EDGE_DBF — pair-store fill after one 2-long edge cell: 2 pairs fewer. Bands B far and A, col<0, col+8>=0. */
#define RR_ROW_FILL_DBF      (RR_ROW_LONG_PAIRS / 2 - 1)
#define RR_ROW_FILL_PAIR_DBF (RR_ROW_LONG_PAIRS - 1)
#define RR_ROW_FILL_EDGE_DBF (RR_ROW_LONG_PAIRS - 2)

/* ---- rr_regs field byte offsets on the 32-bit m68k target (4-byte pointers/Offset, 2-byte int16) ----
 * Both band cores read/write the threaded cursor struct through these (via the shared RR_BAND_PROLOGUE /
 * RR_BAND_EPILOGUE macros in road_band.S); src/road.c pins them equal to the real struct layout with a
 * _Static_assert (guarded to the 32-bit target — the 64-bit host build never touches the asm, so its
 * 8-byte-pointer layout is irrelevant). Keep in step with `rr_regs`. */
#define RR_OFF_FB          0         /* Framebuffer   *fb         */
#define RR_OFF_DST         4         /* Offset         dst        */
#define RR_OFF_TEX         8         /* const uint8_t *tex        */
#define RR_OFF_PARAM      12         /* const uint8_t *param      */
#define RR_OFF_WIDTH      16         /* const uint8_t *width      */
#define RR_OFF_EDGE       20         /* const uint8_t *edge       */
#define RR_OFF_EDGE_CONST 24         /* const uint8_t *edge_const */
#define RR_OFF_WIDTH_BASE 28         /* const uint8_t *width_base  (asm does not read it) */
#define RR_OFF_STRIDE     32         /* int16_t        stride     */
#define RR_OFF_D7         34         /* uint16_t       d7         */

#endif /* RM_ROAD_CONST_H */
