/* blitter_selftest.c — on-target proof that the STE blitter driver reproduces the 68000 masked-blit
 * engine byte-for-byte (PERF30 C4, slice 1). Compiled + run ONLY in the GAME_STE_SELFTEST build.
 *
 * The pin: at fine_x == 0 the fixed-pass engine rm_blit_objshift2 (src/blit.c, the shipping reference)
 * degenerates to an ALIGNED per-plane cookie-cut into one column set — shl == 16 sends the whole source
 * word into col0 and leaves col1 untouched, so each drawn 16-px column is exactly
 *     plane0 = (dst & mask) | w0        plane2 = (dst & mask) | (w0|w1)
 *     plane1 = (dst & mask) | w1        plane3 = (dst & mask) | (w0|w1)      mask = ~(w0|w1)
 * (derive it from blit.c objsh2_straddle_cell with shl==16). That is precisely a two-pass blitter
 * cookie-cut: an AND pass with `mask` then an OR pass with the per-plane data. So we:
 *   1. draw a synthetic 3-cell sprite with the REAL rm_blit_objshift2 into ref_fb (the reference), and
 *   2. draw the SAME pixels by materialising the mask + per-plane data bitmaps and firing 8 blitter
 *      passes (4 planes x {AND mask, OR data}) into test_fb over the identical background, then
 *   3. XOR the two framebuffers — a byte-exact blitter reproduces the engine, so the diff is all zero.
 * The headless harness (run_ste_selftest.py) asserts SCREEN.BIN is all-zero == PASS.
 *
 * This proves the driver end to end on emulated STE hardware: register poking, HOP=SRC + LOP AND/OR,
 * the interleaved 4-plane dst walk (dst_x_inc=8 / dst_y_inc), endmasks, and Hatari's blitter model.
 * The fine_x != 0 SKEW mapping (skew=fine_x + FXSR/NFSR + edge endmasks) is specified in
 * BLIT_STE_SPEC.md and lands with the engine wiring in slice 2. */
#include "blitter.h"          /* also the ONE Supexec extern (the whole test runs supervisor) */
#include "screen.h"
#include "blit_const.h"
#include "game.h"

/* ---- synthetic sprite geometry ---- */
#define ST_CELLS     3            /* base straddle for width_idx 0 (3 cells wide) */
#define ST_ROWS      40           /* sprite height in rows */
#define ST_SRC_ROWS  ST_ROWS      /* source rows == drawn rows */
#define ST_X         0x40         /* x with fine_x==0 (multiple of 16); aligned_col = 0x20 */
#define ST_ALIGNED_COL 0x20       /* (ST_X>>1) & 0xfff8 — byte column of col0 in each row */
#define ST_Y_TOP     100          /* top screen row of the sprite */
#define ST_WIDTH_IDX 0            /* base family, straddle 3 */
#define ST_BG_BYTE   0x5A         /* non-trivial background so the AND pass's preserve path is tested */

/* Guard band: physically-adjacent sentinel bytes bracketing every buffer the blitter (or the CPU
 * materialiser) writes. Any out-of-bounds write — the failure mode the slice-2 skew/clip sweeps must not
 * hide — flips a guard byte, which the compare counts as a mismatch. The struct wrapping makes lo/px/hi
 * contiguous (separate arrays give no adjacency guarantee). */
#define GUARD_BYTES  256
#define GUARD_FILL   0xA5

/* Source sprite (2-plane, w0,w1 per 4-byte cell) and the blitter target, each guard-bracketed. */
static struct { uint8_t lo[GUARD_BYTES]; uint8_t px[ST_SRC_ROWS * OBJSH2_SRC_ROW_BYTES]; uint8_t hi[GUARD_BYTES]; } src_guard;
static struct { uint8_t lo[GUARD_BYTES]; uint8_t px[SCREEN_BYTES]; uint8_t hi[GUARD_BYTES]; } test_guard;
#define src_sprite (src_guard.px)
#define test_fb    (test_guard.px)

/* Materialised blitter bitmaps (tightly packed, ST_CELLS words per row): one shared AND mask and four
 * per-plane OR data planes. Big-endian words (native on m68k), read directly by the blitter. */
static uint16_t mask_bm[ST_ROWS * ST_CELLS];
static uint16_t data_bm[SCREEN_PLANES][ST_ROWS * ST_CELLS];

static uint8_t ref_fb[SCREEN_BYTES];
static uint8_t diff_fb[SCREEN_BYTES];
static long selftest_mismatch;                 /* Supexec passes results through file scope */

/* Count guard bytes that no longer hold GUARD_FILL (0 == intact). */
static long guard_broken(const uint8_t *g) {
    long bad = 0;
    for (int i = 0; i < GUARD_BYTES; i++) if (g[i] != GUARD_FILL) bad++;
    return bad;
}

/* A varied, deterministic 16-bit fill so every (row,cell) exercises a different mask/plane pattern. */
static uint16_t pattern(int row, int cell, int lane) {
    unsigned v = (unsigned)(row * 2654435761u + cell * 40503u + lane * 0x9E37u);
    return (uint16_t)((v >> 11) ^ (v >> 3));
}

static void build_source(void) {
    for (int r = 0; r < ST_SRC_ROWS; r++) {
        uint8_t *row = src_sprite + r * OBJSH2_SRC_ROW_BYTES;
        for (int k = 0; k < ST_CELLS; k++) {
            wr16(row + k * OBJSH_CELL_BYTES / 2 + 0, pattern(r, k, 0));   /* w0 */
            wr16(row + k * OBJSH_CELL_BYTES / 2 + 2, pattern(r, k, 1));   /* w1 */
        }
    }
}

/* Materialise the mask + per-plane data words from the source, top-down (the blitter's forward walk).
 * rm_blit_objshift2 draws bottom-up reading source row rr for screen row rr (top-down); see the file
 * header. So screen row rr reads source offset rr*80 — mask/data align cell-for-cell. */
static void build_bitmaps(void) {
    for (int rr = 0; rr < ST_ROWS; rr++) {
        const uint8_t *srow = src_sprite + rr * OBJSH2_SRC_ROW_BYTES;
        for (int k = 0; k < ST_CELLS; k++) {
            uint16_t w0 = be16(srow + k * OBJSH_CELL_BYTES / 2 + 0);
            uint16_t w1 = be16(srow + k * OBJSH_CELL_BYTES / 2 + 2);
            uint16_t uni = (uint16_t)(w0 | w1);
            int idx = rr * ST_CELLS + k;
            mask_bm[idx]    = (uint16_t)~uni;      /* AND pass: keep background where transparent */
            data_bm[0][idx] = w0;                  /* OR pass: plane 0 = w0 */
            data_bm[1][idx] = w1;                  /* plane 1 = w1 */
            data_bm[2][idx] = uni;                 /* plane 2 = w0|w1 (~mask) */
            data_bm[3][idx] = uni;                 /* plane 3 = w0|w1 */
        }
    }
}

/* One blitter pass over ST_CELLS columns x ST_ROWS rows of a single plane `p` into the interleaved fb. */
static void blit_plane(uint8_t *fb, int plane, const uint16_t *src_bm, uint8_t lop) {
    BlitPass pass;
    pass.src_addr  = (uint32_t)src_bm;
    pass.src_x_inc = 2;                            /* tightly packed: next word */
    pass.src_y_inc = 2;                            /* after (x_count-1) x-steps, one more to next row */
    pass.dst_addr  = (uint32_t)(fb + ST_Y_TOP * SCREEN_ROW_BYTES + ST_ALIGNED_COL + plane * 2);
    pass.dst_x_inc = OBJSH_CELL_BYTES;             /* next 16-px column, same plane (interleaved) */
    pass.dst_y_inc = SCREEN_ROW_BYTES - OBJSH_CELL_BYTES * (ST_CELLS - 1);   /* next line, back to col 0 */
    pass.endmask1  = 0xFFFF;                        /* no edge clip — bitmap zeros carry transparency */
    pass.endmask2  = 0xFFFF;
    pass.endmask3  = 0xFFFF;
    pass.x_count   = ST_CELLS;
    pass.y_count   = ST_ROWS;
    pass.hop       = BLT_HOP_SRC;
    pass.lop       = lop;
    pass.skew_ctl  = 0;                            /* aligned (fine_x==0) */
    blit_run(&pass);
}

/* The whole test, run under Supexec (blitter access is supervisor-only). Returns via file scope. */
long blitter_selftest_super(void) {
    for (int i = 0; i < GUARD_BYTES; i++)
        src_guard.lo[i] = src_guard.hi[i] = test_guard.lo[i] = test_guard.hi[i] = GUARD_FILL;

    build_source();
    build_bitmaps();

    for (int i = 0; i < SCREEN_BYTES; i++) ref_fb[i] = test_fb[i] = ST_BG_BYTE;

    /* Reference: the real shipping engine at fine_x==0, base family. dst_off/src_off address the BOTTOM
     * row (it walks up); src_off=(ST_ROWS-1)*80 so the top row reads offset 0. dst_off is the ROW base
     * only — rm_blit_objshift2 adds aligned_col (ST_ALIGNED_COL) itself, so pre-adding it would
     * double-count the column. */
    uint32_t dst_off = (uint32_t)((ST_Y_TOP + ST_ROWS - 1) * SCREEN_ROW_BYTES);
    uint32_t src_off = (uint32_t)((ST_ROWS - 1) * OBJSH2_SRC_ROW_BYTES);
    rm_blit_objshift2(ref_fb, dst_off, src_sprite, src_off, ST_X, ST_ROWS - 1, ST_WIDTH_IDX);

    /* Blitter: AND the shared mask into every plane, then OR each plane's data (per-plane AND precedes
     * that plane's OR — the objshift2 cell order). */
    for (int p = 0; p < SCREEN_PLANES; p++) blit_plane(test_fb, p, mask_bm, BLT_LOP_AND);
    for (int p = 0; p < SCREEN_PLANES; p++) blit_plane(test_fb, p, data_bm[p], BLT_LOP_OR);

    long n = 0;
    for (int i = 0; i < SCREEN_BYTES; i++) {
        diff_fb[i] = (uint8_t)(ref_fb[i] ^ test_fb[i]);
        if (diff_fb[i]) n++;
    }
    /* Guard bands must be untouched — an out-of-bounds blitter/materialiser write fails the test. */
    n += guard_broken(src_guard.lo) + guard_broken(src_guard.hi)
       + guard_broken(test_guard.lo) + guard_broken(test_guard.hi);
    selftest_mismatch = n;
    return n;
}

/* Public entry: run the self-test in supervisor, hand back the XOR-diff framebuffer for the SCREEN.BIN
 * dump (all-zero == the blitter reproduced the engine byte-for-byte) and the mismatch byte count. */
const uint8_t *blitter_selftest(long *mismatch_out) {
    Supexec(blitter_selftest_super);
    if (mismatch_out) *mismatch_out = selftest_mismatch;
    return diff_fb;
}
