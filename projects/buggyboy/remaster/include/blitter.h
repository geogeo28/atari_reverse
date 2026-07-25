/* blitter.h — the Atari STE/Mega-ST hardware BLiTTER (0xFFFF8A00) register block + a small masked-blit
 * driver. Used ONLY by the STE build target (GAME_STE, render/atari/build_game.sh); the stock ST binary
 * never sees this file. The blitter emits the SAME framebuffer bytes as the 68000 RMW engines it
 * replaces, so the byte-compare pins still hold — that is the whole point of the STE build (PERF30 C4).
 *
 * SUPERVISOR ONLY: the 0xFFFF8Axx I/O page bus-errors from user mode. Every register access below runs
 * from a Supexec excursion or the VBL (already supervisor) — see src/blitter.c and game_main.c.
 *
 * Register map (STE hardware, big-endian; the byte registers are the control tail):
 *   0x8A00..0x8A1E  halftone RAM        16 words       (HOP source when HOP selects halftone)
 *   0x8A20          src_x_inc  word (signed)  0x8A22 src_y_inc word (signed)   0x8A24 src_addr long
 *   0x8A28/2A/2C    endmask1/2/3  words        (first / middle / last dst word of each line)
 *   0x8A2E          dst_x_inc  word (signed)  0x8A30 dst_y_inc word (signed)   0x8A32 dst_addr long
 *   0x8A36          x_count word  0x8A38 y_count word
 *   0x8A3A          HOP byte      0x8A3B LOP byte
 *   0x8A3C          control byte  (bit7 BUSY/START, bit6 HOG, bit5 SMUDGE, bits3-0 halftone line)
 *   0x8A3D          skew byte     (bit7 FXSR, bit6 NFSR, bits3-0 skew count)
 */
#ifndef RM_BLITTER_H
#define RM_BLITTER_H

#include <stdint.h>
#include "st.h"
#include "screen.h"        /* SCREEN_ROW_BYTES — used by the shared cookie-cut pass below */
#include "blit_const.h"    /* OBJSH_* geometry + contract caps — shared with the C/asm engines */

/* XBIOS 38 (os.s): run func in supervisor, return to the caller's mode. Declared here as the ONE source
 * for the STE driver + self-test (both reach the supervisor-only 0xFFFF8Axx page through it). */
extern long Supexec(long (*func)(void));

/* ---- register addresses (one source of truth; no bare 0x8Axx literals anywhere else) ---- */
#define BLT_BASE          0xFFFF8A00UL
#define BLT_HALFTONE      (BLT_BASE + 0x00)    /* 16 words */
#define BLT_SRC_X_INC     (BLT_BASE + 0x20)    /* word, signed */
#define BLT_SRC_Y_INC     (BLT_BASE + 0x22)    /* word, signed */
#define BLT_SRC_ADDR      (BLT_BASE + 0x24)    /* long */
#define BLT_ENDMASK1      (BLT_BASE + 0x28)    /* word — first dst word of each line */
#define BLT_ENDMASK2      (BLT_BASE + 0x2A)    /* word — middle dst words */
#define BLT_ENDMASK3      (BLT_BASE + 0x2C)    /* word — last dst word of each line */
#define BLT_DST_X_INC     (BLT_BASE + 0x2E)    /* word, signed */
#define BLT_DST_Y_INC     (BLT_BASE + 0x30)    /* word, signed */
#define BLT_DST_ADDR      (BLT_BASE + 0x32)    /* long */
#define BLT_X_COUNT       (BLT_BASE + 0x36)    /* word — dst words per line */
#define BLT_Y_COUNT       (BLT_BASE + 0x38)    /* word — number of lines */
#define BLT_HOP           (BLT_BASE + 0x3A)    /* byte */
#define BLT_LOP           (BLT_BASE + 0x3B)    /* byte */
#define BLT_CONTROL       (BLT_BASE + 0x3C)    /* byte */
#define BLT_SKEW          (BLT_BASE + 0x3D)    /* byte */

/* ---- control byte bits (0x8A3C) ---- */
#define BLT_CTL_BUSY      0x80                 /* write 1 = start; reads 1 while running */
#define BLT_CTL_HOG       0x40                 /* 1 = hold the bus until done; 0 = shared (64-word bursts) */
#define BLT_CTL_SMUDGE    0x20

/* ---- skew byte bits (0x8A3D) ---- */
#define BLT_SKEW_FXSR     0x80                 /* force an extra source read at line start */
#define BLT_SKEW_NFSR     0x40                 /* suppress the final source read at line end */
#define BLT_SKEW_MASK     0x0F                 /* skew count (bit shift applied to the source, 0..15) */

/* ---- HOP (halftone operation, 0x8A3A) ---- */
#define BLT_HOP_ONE       0                    /* operand = all ones */
#define BLT_HOP_HALFTONE  1                    /* operand = halftone RAM */
#define BLT_HOP_SRC       2                    /* operand = source (the masked-blit choice) */
#define BLT_HOP_SRC_AND_HT 3                   /* operand = source AND halftone */

/* ---- LOP (logic operation, 0x8A3B) — 16 ops of (source op dst) ---- */
#define BLT_LOP_ZERO      0x0
#define BLT_LOP_AND       0x1                  /* dst = src AND dst  (the cookie-cut CLEAR pass) */
#define BLT_LOP_SRC       0x3                  /* dst = src          (plain copy) */
#define BLT_LOP_DST       0x5                  /* dst = dst */
#define BLT_LOP_XOR       0x6                  /* dst = src XOR dst */
#define BLT_LOP_OR        0x7                  /* dst = src OR dst   (the cookie-cut PAINT pass) */
#define BLT_LOP_ONE       0xF

/* color_pairs table stride: one colour's 4-plane fill = 4 words = 8 bytes (blit.c reaches it as `<<3`).
 * ONE definition shared by the colour engine + its sweep (was duplicated in both). */
#define OBJSH_COLOR_STRIDE   8

/* ---- typed register accessors (supervisor only) ---- */
#define BLT_W(reg)   (*(volatile uint16_t *)(reg))
#define BLT_L(reg)   (*(volatile uint32_t *)(reg))
#define BLT_B(reg)   (*(volatile uint8_t  *)(reg))

/* One fully-specified blitter pass. All fields map 1:1 to registers; the driver (blit_run) pokes them
 * and starts the chip. x_count is dst words per line, y_count lines. src/dst_addr are byte addresses of
 * the first (top) word; the +inc walk goes forward through memory. endmask1/3 clip the first/last dst
 * word of every line; endmask2 (usually 0xFFFF) covers the middle. skew shifts the source right 0..15
 * bits into the dst word grid; fxsr/nfsr handle the edge source reads for a skewed run. */
typedef struct {
    uint32_t src_addr, dst_addr;
    int16_t  src_x_inc, src_y_inc, dst_x_inc, dst_y_inc;
    uint16_t endmask1, endmask2, endmask3;
    uint16_t x_count, y_count;
    uint8_t  hop, lop, skew_ctl;               /* skew_ctl = skew count | FXSR/NFSR bits */
} BlitPass;

/* Detect a usable blitter (STE or better) via the _MCH cookie. Must run supervisor (reads _p_cookies at
 * 0x5A0). Returns 1 if the machine has a blitter, 0 on a plain ST / no cookie jar. */
int blitter_present(void);

/* Same check, callable from user mode: wraps blitter_present() in a Supexec excursion. */
int blitter_available(void);

/* On-target driver proof (GAME_STE_SELFTEST build): reproduce rm_blit_objshift2 with the blitter and
 * return the XOR-diff framebuffer (all-zero == byte-exact) plus the mismatch byte count. */
const uint8_t *blitter_selftest(long *mismatch_out);

/* Blitter path for the fixed-pass fine-x masked blit (src/blitter_objshift2.c). Same signature/contract
 * as rm_blit_objshift2. Returns 1 if drawn by the blitter (BASE family or a zero-row no-op), 0 if the
 * caller must run the CPU engine (LEFT/RIGHT clip family — a pinned hybrid). Supervisor only. */
int rm_blit_objshift2_blitter(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                              uint16_t x, uint16_t rows_m1, int width_idx);

/* Runtime dispatch (object_list.c's RM_BLIT_OBJSHIFT2 seam): blitter for BASE, CPU asm for CLIP.
 * Same signature/contract as rm_blit_objshift2; runs the blitter attempt in a Supexec. */
void rm_blit_objshift2_dispatch(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                                uint16_t x, uint16_t rows_m1, int width_idx);

/* Bind the RM_BLIT_OBJSHIFT2 function pointer ONCE at boot: have_blitter → the blitter dispatch, else the
 * CPU asm engine (a plain ST/TT binds the CPU path — no bail). Call from main() after blitter_available(). */
void rm_blit_objshift2_bind(int have_blitter);

/* Invalidate the objshift2 pre-shift memoisation cache — call after the arena.gfx source is rewritten in
 * place (the F10 asset reload), or the cache would serve stale bitmaps. */
void rm_blit_objshift2_cache_flush(void);

/* Colour-indexed pass-1 engine (src/blitter_objshift.c): same 2-pass cookie-cut, 4-word mask + colour
 * fill. Blitter path (BASE family, 0 = CPU hybrid), the runtime dispatch, and the reload cache flush. */
int rm_blit_objshift_blitter(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                             uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                             const uint8_t *color_pairs, int base_cells);
void rm_blit_objshift_dispatch(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                               uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                               const uint8_t *color_pairs, int base_cells);
void rm_blit_objshift_cache_flush(void);

/* Is this draw the BASE family — the only family the blitter paths serve (a positive aligned column
 * below the width-dependent right bound, and a non-zero row count)? The engines that must run the test
 * inline open-code it (src/blit.c, src/blitter_objshift.c); the paths that only ASK — the skew path's
 * family gate and the census/sweep bookkeeping — share this one copy. */
static inline int objsh_is_base(uint16_t x, uint16_t rows_m1, int base_cells) {
    if ((int16_t)rows_m1 + 1 <= 0) return 0;               /* zero rows: no draw, not a BASE case */
    int16_t col = (int16_t)((int16_t)((int16_t)(uint16_t)x >> 1) & (int16_t)COL_ALIGN);
    int16_t ceiling = (int16_t)(OBJSH_RIGHT_BOUND - OBJSH_CELL_BYTES * (base_cells - 1));
    return !(col < 0 || (int16_t)(col - ceiling) >= 0);    /* LEFT / RIGHT clip -> CPU hybrid */
}

/* ---- hardware-SKEW colour path (src/blitter_skew.c) — MEASUREMENT BUILD ONLY (GAME_STE_SWEEP) ----
 * Same contract as rm_blit_objshift_blitter (1 = drawn, 0 = CPU hybrid) but blits from UNSHIFTED,
 * colour-independent bitmaps with the chip's SKEW register doing the fine-x shift. Slice 1 of the
 * hardware-SKEW campaign calibrates it against the sweep; routing + the static sprite table are slice 2. */
#define OBJSH_SKEW_MAX_CELLS  2                            /* base_cells family max */
/* Bitmap 0 is the show mask; bitmaps 1..OBJSH_PLANES are the per-plane pixel words. */
#define OBJSH_SKEW_BM_MASK    0
#define OBJSH_SKEW_BM_PLANE0  1
#define OBJSH_SKEW_N_BITMAPS  (1 + OBJSH_PLANES)
/* Pad words past the live rows*base_cells. ONE is the calibrated path's need: every line wastes one
 * source read, and the last line's lands a word past the bitmap (see blitter_skew.c's header). The rest
 * covers the RM_SKEW_MUT_FXSR mutation, whose extra per-line read drifts the source one word further
 * per line — up to rows words by the last line. A mutate build must still FAIL, but it must not read
 * out of bounds while doing so. */
#define OBJSH_SKEW_PAD_WORDS  (OBJSH_MAX_ROWS + 1)
#define OBJSH_SKEW_BM_WORDS   (OBJSH_MAX_ROWS * OBJSH_SKEW_MAX_CELLS + OBJSH_SKEW_PAD_WORDS)

/* The UNSHIFTED, colour-independent bitmap set one sprite region materialises into. Slice 1 keeps a
 * single scratch instance; slice 2's bounded sprite-key table hands out one instance per key, which is
 * why materialise and blit take it explicitly rather than sharing a hidden static. */
typedef struct {
    uint16_t word[OBJSH_SKEW_N_BITMAPS][OBJSH_SKEW_BM_WORDS];
} ObjshSkewBitmaps;

/* Mutation knob for the sweep's coverage check (-DRM_SKEW_MUTATE=n, set by build_game.sh): each value
 * breaks ONE calibrated register, so a sweep that still passes would prove the skew path is not really
 * exercised. Declared here because src/blitter_sweep.c reads it too — a mutate build runs the skew grid
 * ALONE (the other two grids are unmutated, so re-running them would only burn emulated cycles). */
#define RM_SKEW_MUT_NONE       0
#define RM_SKEW_MUT_SKEW_PLUS  1                           /* skew = fine_x + 1 */
#define RM_SKEW_MUT_FXSR       2                           /* set FXSR (an extra source read per line) */
#define RM_SKEW_MUT_ENDMASK1   3                           /* drop the column-0 leading-edge guard */
#define RM_SKEW_MUT_ENDMASK3   4                           /* drop the last-column trailing-edge guard */
#define RM_SKEW_MUT_PLANE3     5                           /* drop plane 3's `& ~m` is_last special */
#ifndef RM_SKEW_MUTATE
#define RM_SKEW_MUTATE RM_SKEW_MUT_NONE
#endif
#define RM_SKEW_MUTATED       (RM_SKEW_MUTATE != RM_SKEW_MUT_NONE)

/* Materialise one sprite region into an explicit destination bitmap set — slice 2's table seam, and what
 * the sweep times in isolation. */
void rm_objsh_skew_materialise(ObjshSkewBitmaps *bm, const uint8_t *src, uint32_t src_off,
                               int16_t stride, int rows, int base_cells);
/* Blit an ALREADY-materialised bitmap set (slice 2 calls this straight off the table; the sweep re-fires
 * it to time the chip passes in isolation). Returns 1 if drawn, 0 for the CPU hybrid — same family
 * contract as the full entry below, which is materialise + this. Supervisor only. */
int rm_blit_objshift_skew_from(const ObjshSkewBitmaps *bm, uint8_t *dst, uint32_t dst_off, uint16_t x,
                               uint16_t color, uint16_t rows_m1, const uint8_t *color_pairs,
                               int base_cells);
/* Slice-1 entry: materialise into a private static scratch, then blit it. */
int rm_blit_objshift_skew(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                          uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                          const uint8_t *color_pairs, int base_cells);

/* Full-sweep proof (GAME_STE_SWEEP build): run rm_blit_objshift2_blitter vs the CPU engine over the
 * objshift2 case space; return a framebuffer encoding per-case results (see src/blitter_sweep.c) and the
 * total mismatch count. */
const uint8_t *blitter_sweep(long *mismatch_out);

/* Run one blitter pass to completion (HOG mode) from the current supervisor context. See src/blitter.c
 * for the HOG-vs-shared justification. */
void blit_run(const BlitPass *p);

/* The shared cookie-cut pass both fine-x engines fire: one aligned (skew=0) blit over an INTERLEAVED
 * pre-shifted bitmap (`nwords` = 4 planes * ncols words/row, contiguous), all 4 planes at once, walking
 * UP one scanline per row (negative dst_y_inc) to match the CPU engines' bottom-up draw. col0_bottom is
 * the first-drawn (bottom) row's col0; lop = AND (mask pass) or OR (data pass). */
static inline void blit_ste_cookiecut_pass(uint8_t *col0_bottom, const uint16_t *src_bm,
                                           int nwords, int rows, uint8_t lop) {
    BlitPass pass;
    pass.src_addr  = (uint32_t)src_bm;
    pass.src_x_inc = 2;
    pass.src_y_inc = 2;                                     /* tightly packed nwords words/row */
    pass.dst_addr  = (uint32_t)col0_bottom;
    pass.dst_x_inc = 2;                                     /* contiguous interleaved words */
    pass.dst_y_inc = -(int16_t)(SCREEN_ROW_BYTES + 2 * (nwords - 1));   /* one scanline UP, back to col0 */
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

#endif /* RM_BLITTER_H */
