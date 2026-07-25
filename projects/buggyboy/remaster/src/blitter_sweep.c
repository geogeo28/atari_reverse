/* blitter_sweep.c — the byte-exactness sweep for the STE blitter paths (PERF30 C4). GAME_STE_SWEEP build
 * only. Runs each blitter path against the shipping CPU engine over its whole case space (cribbed from
 * test/test_asm_blit.py's fuzz dimensions) and reports a per-case mismatch grid to SCREEN.BIN.
 *
 * WHAT PINS WHAT. The sweep pins the blit RECIPES — the register programs — case by case; the goldens
 * (run_ste_golden.py) and the same-PRG A/B (run_ste_ab.py) pin the SHIPPING route end to end on real
 * game data. So this file sweeps both colour recipes even though only one of them ships: the hardware-
 * SKEW path (src/blitter_skew.c) is the shipping colour route, and the PRE-SHIFT path
 * (src/blitter_objshift.c) is retired but still swept so its recipe stays pinned for the record.
 *
 * Case space: width_idx 0..2 x fine_x 0..15 x a column set spanning LEFT clip / BASE / RIGHT clip
 * x rows_m1 {0, 3, 0x2a} — plus the bit-15-set (zero-row) rows. The colour-indexed engine's own grid is
 * swept TWICE, once per recipe, into separate arrays. For each case both engines draw the SAME synthetic
 * sprite over the SAME background; the two framebuffers must be byte-identical over the whole 32000
 * bytes (and the guard bands intact). A BASE case that the blitter path handles (returns 1) must match
 * exactly; a CLIP case the path declines (returns 0) is the pinned CPU hybrid and is checked to be
 * declined (not silently mis-drawn). Every case's mismatch count is logged so a single Hatari run shows
 * the whole grid.
 *
 * A fourth section drives the shipping route's sprite-key TABLE (see sweep_table_section): the three
 * grids all call un-tabled entry points, so without it the table's own branches — hit, grow, clip, the
 * full-table decline — would ship unpinned.
 */
#include "blitter.h"
#include "screen.h"
#include "blit_const.h"
#include "game.h"

extern long Supexec(long (*func)(void));

/* Case dimensions — mirror test/test_asm_blit.py so every shape the game data produces is swept. */
static const int SWEEP_WIDTH_IDX[] = {0, 1, 2};
static const int SWEEP_COLUMNS[]   = {-32, -24, -16, -8, 0x0, 0x40, 0x78, 0x80, 0x88, 0x90, 0x98, 0xa0};
static const int SWEEP_ROWS_M1[]   = {0, 3, 0x2a};
#define N_WIDTH   (int)(sizeof SWEEP_WIDTH_IDX / sizeof SWEEP_WIDTH_IDX[0])
#define N_COL     (int)(sizeof SWEEP_COLUMNS   / sizeof SWEEP_COLUMNS[0])
#define N_ROWS    (int)(sizeof SWEEP_ROWS_M1   / sizeof SWEEP_ROWS_M1[0])
#define N_FINEX   16
#define N_CASES   (N_WIDTH * N_FINEX * N_COL * N_ROWS)

#define SWEEP_SRC_ROWS  0x2B                                /* 43 = max rows_m1 0x2a + 1 */
#define SWEEP_BG_BYTE   0x5A
#define GUARD_BYTES     256
#define GUARD_FILL      0xA5

/* x that yields aligned column `col` (multiple of 8) and low nibble `fine_x`: col = ((int16)x>>1)&~7,
 * fine_x = x&0xf, so x = 2*col + fine_x. */
static uint16_t make_x(int col, int fine_x) { return (uint16_t)(2 * col + fine_x); }

static struct { uint8_t lo[GUARD_BYTES]; uint8_t px[SWEEP_SRC_ROWS * OBJSH2_SRC_ROW_BYTES]; uint8_t hi[GUARD_BYTES]; } src_g;
static struct { uint8_t lo[GUARD_BYTES]; uint8_t px[SCREEN_BYTES]; uint8_t hi[GUARD_BYTES]; } test_g;
#define src_sprite (src_g.px)
#define test_fb    (test_g.px)
static uint8_t ref_fb[SCREEN_BYTES];
static uint16_t case_diff[N_CASES];                         /* per-case mismatch count (0 == byte-exact) */
static long sweep_total;
static long sweep_handled;                                  /* cases the blitter path drew (BASE family) */

/* ---- colour-indexed engine (rm_blit_objshift) sweep — mirror test_asm_blit.py's objshift cases ---- */
static const int OSH_BASE_CELLS[]  = {1, 2};
static const int OSH_COLUMNS[]     = {-32, -24, -16, -8, 0x0, 0x30, 0x40, 0x78, 0x88, 0x90, 0x98, 0xa0};
/* (colour, rows_m1, stride) tuples: strides 8 / 0x10 / -8 / 0xa8 (the signed source walk). */
static const int OSH_CRS[][3]      = {{3, 3, 8}, {11, 0, 0x10}, {14, 5, (int)0xfff8}, {7, 0x1f, 0xa8}};
#define N_OSH_BC   (int)(sizeof OSH_BASE_CELLS / sizeof OSH_BASE_CELLS[0])
#define N_OSH_COL  (int)(sizeof OSH_COLUMNS / sizeof OSH_COLUMNS[0])
#define N_OSH_CRS  (int)(sizeof OSH_CRS / sizeof OSH_CRS[0])
#define N_OSH_CASES (N_OSH_BC * N_FINEX * N_OSH_COL * N_OSH_CRS)

/* A big source (the stride walk reaches ~160*rows back / +16*rows forward) with src_off mid-buffer. */
#define OSH_SRC_BYTES   6000
#define OSH_SRC_OFF     5000
#define OSH_N_COLOURS   16                                  /* colour nibble range (OBJSH_COLOR_STRIDE from blitter.h) */
#define OSH_PAIRS_BYTES (OSH_N_COLOURS * OBJSH_COLOR_STRIDE)
static struct { uint8_t lo[GUARD_BYTES]; uint8_t px[OSH_SRC_BYTES]; uint8_t hi[GUARD_BYTES]; } osh_src_g;
#define osh_src (osh_src_g.px)
static uint8_t osh_pairs[OSH_PAIRS_BYTES];                  /* the swept table: arbitrary distinct bytes */
static uint8_t osh_pairs_binary[OSH_PAIRS_BYTES];           /* the GAME's own table (bench; see below) */
static uint16_t osh_case_diff[N_OSH_CASES];
static long osh_handled;

/* The hardware-SKEW colour path (src/blitter_skew.c) is swept over the SAME case grid, in its own
 * arrays, so the pre-shift sweep above stays the untouched pin. */
static uint16_t skew_case_diff[N_OSH_CASES];
static long skew_handled;

/* Either colour-engine blitter path under test — the grid runner is shared (they take the same args). */
typedef int (*ObjshBlitFn)(uint8_t *, uint32_t, const uint8_t *, uint32_t, uint16_t, uint16_t,
                           uint16_t, int16_t, const uint8_t *, int);

static uint16_t pattern(int r, int k, int lane) {
    unsigned v = (unsigned)(r * 2654435761u + k * 40503u + lane * 0x9E37u);
    return (uint16_t)((v >> 11) ^ (v >> 3));
}

static long guard_broken(const uint8_t *g) {
    long bad = 0;
    for (int i = 0; i < GUARD_BYTES; i++) if (g[i] != GUARD_FILL) bad++;
    return bad;
}

/* Draw one case with the CPU engine (ref) and the blitter path (test) over the same background; count
 * differing framebuffer bytes + any broken guard. handled_out reports the blitter path's return. */
static long run_case(int width_idx, int fine_x, int col, int rows_m1, int *handled_out) {
    for (int i = 0; i < SCREEN_BYTES; i++) ref_fb[i] = test_fb[i] = SWEEP_BG_BYTE;
    for (int i = 0; i < GUARD_BYTES; i++) src_g.lo[i] = src_g.hi[i] = test_g.lo[i] = test_g.hi[i] = GUARD_FILL;

    uint16_t x = make_x(col, fine_x);
    int rows = (int16_t)(uint16_t)rows_m1 + 1;
    int nsrc_rows = rows > 0 ? rows : 1;
    if (nsrc_rows > SWEEP_SRC_ROWS) nsrc_rows = SWEEP_SRC_ROWS;
    for (int r = 0; r < nsrc_rows; r++) {
        uint8_t *row = src_sprite + r * OBJSH2_SRC_ROW_BYTES;
        for (int k = 0; k < OBJSH2_BASE_STRADDLE; k++) {
            wr16(row + k * (OBJSH_CELL_BYTES / 2) + 0, pattern(r, k, 0));
            wr16(row + k * (OBJSH_CELL_BYTES / 2) + 2, pattern(r, k, 1));
        }
    }

    /* Address the bottom row (both engines walk up); src_off top row reads offset 0. */
    uint32_t dst_off = (uint32_t)((SCREEN_H / 4 + (rows > 0 ? rows - 1 : 0)) * SCREEN_ROW_BYTES);
    uint32_t src_off = (uint32_t)((rows > 0 ? rows - 1 : 0) * OBJSH2_SRC_ROW_BYTES);

    rm_blit_objshift2(ref_fb, dst_off, src_sprite, src_off, x, (uint16_t)rows_m1, width_idx);
    *handled_out = rm_blit_objshift2_blitter(test_fb, dst_off, src_sprite, src_off, x, (uint16_t)rows_m1, width_idx);

    long n = 0;
    for (int i = 0; i < SCREEN_BYTES; i++) if (ref_fb[i] != test_fb[i]) n++;
    n += guard_broken(src_g.lo) + guard_broken(src_g.hi) + guard_broken(test_g.lo) + guard_broken(test_g.hi);
    return n;
}

/* Both colour tables are case-INVARIANT, so they are built once at sweep start (the per-case refill they
 * replace was pure emulated-cycle waste).
 *   osh_pairs        — an arbitrary distinct-byte table so each colour nibble selects a different 4-plane
 *                      fill (the c*8+b*37+5 generator mirrors test_asm_blit.py's OSH_PAIRS). Fills that
 *                      are neither 0 nor 0xFFFF are the HARDER case for the skew recipe's endmask trick,
 *                      which is why the grid sweeps them.
 *   osh_pairs_binary — what the GAME actually passes: plane p's fill is all-ones iff bit p of the colour
 *                      index is set. Used by the bench only, to measure the OR-pass skipping that real
 *                      data buys (a zero plane fill costs no pass at all). */
static void sweep_init_pairs(void) {
    for (int c = 0; c < OSH_N_COLOURS; c++) {
        for (int b = 0; b < OBJSH_COLOR_STRIDE; b++)
            osh_pairs[c * OBJSH_COLOR_STRIDE + b] = (uint8_t)(c * 8 + b * 37 + 5);
        for (int p = 0; p < OBJSH_PLANES; p++)
            wr16(osh_pairs_binary + c * OBJSH_COLOR_STRIDE + p * 2,
                 ((c >> p) & 1) ? 0xFFFFu : 0u);
    }
}

/* The synthetic source depends only on (base_cells, colour), and the grid walks colour slowly — so
 * refill it only when that key changes. The GUARD bands are still re-armed on EVERY case: they are the
 * overrun tripwire and must not carry a previous case's damage forward. */
static int osh_src_key_cells = -1, osh_src_key_color = -1;
static void osh_src_refill(int base_cells, int color) {
    if (base_cells == osh_src_key_cells && color == osh_src_key_color) return;
    for (int i = 0; i < OSH_SRC_BYTES - 1; i += 2) wr16(osh_src + i, pattern(i, base_cells, color));
    osh_src_key_cells = base_cells;
    osh_src_key_color = color;
}

/* One colour-engine case: draw with the CPU rm_blit_objshift (ref) and `test_fn` (the pre-shift or the
 * hardware-skew blitter path) over the same background; count differing bytes + broken guards. */
static long run_case_objsh(ObjshBlitFn test_fn, int base_cells, int fine_x, int col, int color,
                           int rows_m1, int16_t stride, int *handled_out) {
    for (int i = 0; i < SCREEN_BYTES; i++) ref_fb[i] = test_fb[i] = SWEEP_BG_BYTE;
    for (int i = 0; i < GUARD_BYTES; i++)
        osh_src_g.lo[i] = osh_src_g.hi[i] = test_g.lo[i] = test_g.hi[i] = GUARD_FILL;
    osh_src_refill(base_cells, color);

    uint16_t x = make_x(col, fine_x);
    uint32_t dst_off = (uint32_t)((SCREEN_H / 2) * SCREEN_ROW_BYTES);   /* mid-screen; both engines walk up */
    rm_blit_objshift(ref_fb, dst_off, osh_src, OSH_SRC_OFF, x, (uint16_t)color, (uint16_t)rows_m1, stride,
                     osh_pairs, base_cells);
    *handled_out = test_fn(test_fb, dst_off, osh_src, OSH_SRC_OFF, x, (uint16_t)color,
                           (uint16_t)rows_m1, stride, osh_pairs, base_cells);
    long n = 0;
    for (int i = 0; i < SCREEN_BYTES; i++) if (ref_fb[i] != test_fb[i]) n++;
    n += guard_broken(osh_src_g.lo) + guard_broken(osh_src_g.hi) + guard_broken(test_g.lo) + guard_broken(test_g.hi);
    return n;
}

/* Run the whole colour-engine case grid against one blitter path. Returns the summed mismatch; fills
 * `diff_out` (one word per case) and `handled_out` (BASE cases the path drew). */
static long sweep_objsh_grid(ObjshBlitFn test_fn, uint16_t *diff_out, long *handled_out) {
    int idx = 0;
    long total = 0, handled_count = 0;
    for (int bi = 0; bi < N_OSH_BC; bi++)
        for (int fx = 0; fx < N_FINEX; fx++)
            for (int ci = 0; ci < N_OSH_COL; ci++)
                for (int ti = 0; ti < N_OSH_CRS; ti++) {
                    int handled;
                    long d = run_case_objsh(test_fn, OSH_BASE_CELLS[bi], fx, OSH_COLUMNS[ci],
                                            OSH_CRS[ti][0], OSH_CRS[ti][1], (int16_t)OSH_CRS[ti][2],
                                            &handled);
                    uint16_t logged = handled ? (uint16_t)(d > 0xffff ? 0xffff : d) : 0;
                    diff_out[idx++] = logged;
                    total += logged;
                    handled_count += handled ? 1 : 0;
                }
    *handled_out = handled_count;
    return total;
}

/* The BASE-family case count BOTH colour grids must report handled — enumerated here, from the shared
 * predicate (blitter.h), so the runner can prove the grid is non-vacuous against a number the report
 * carries rather than a Python literal that could drift from this grid. */
static long osh_expected_base_cases(void) {
    long n = 0;
    for (int bi = 0; bi < N_OSH_BC; bi++)
        for (int fx = 0; fx < N_FINEX; fx++)
            for (int ci = 0; ci < N_OSH_COL; ci++)
                for (int ti = 0; ti < N_OSH_CRS; ti++)
                    n += objsh_is_base(make_x(OSH_COLUMNS[ci], fx), (uint16_t)OSH_CRS[ti][1],
                                       OSH_BASE_CELLS[bi]) ? 1 : 0;
    return n;
}

/* ---- the sprite-key TABLE section (src/blitter_skew.c's static table) ---------------------------
 * Every grid above calls an UN-TABLED entry point, so nothing there touches the table the shipping route
 * actually blits from. This section drives the tabled entry (rm_blit_objshift_skew_tabled — the
 * dispatch's supervisor half, which is exactly what a driving blit runs) through each table branch and
 * byte-compares every blit against the CPU reference on a real framebuffer:
 *   GROW  a taller call after a shorter one: the entry must re-materialise deeper.
 *   CLIP  a shorter call after a taller one: y_count must clip the taller entry.
 *   HIT   the same key twice: the second call must serve the materialised entry.
 *   FULL  OBJSH_SKEW_TABLE_ENTRIES distinct keys claim every entry (all must be served), then one more
 *         is DECLINED with the framebuffer untouched and completed byte-exactly by the CPU hybrid; the
 *         call after that is declined too (the full-table latch), and a flush re-arms the route.
 * All of them use base_cells 2 at a BASE column with a non-zero fine_x — a shape the skew grid also
 * sweeps — so a failure here is a TABLE failure, not a recipe one. */
#define TBL_CELLS       2
#define TBL_COLOR       3
#define TBL_COL         0x40                                /* a BASE column (no clip) */
#define TBL_FINE_X      0xb                                 /* non-zero: the straddling shape */
/* A stride that WALKS (sp_step = 8 - stride = -8), so consecutive rows of a materialised entry hold
 * different bytes. With a stride of 8 every row would be identical and the CLIP case could not tell
 * "blit the first 4 rows" from "blit any 4 rows". */
#define TBL_STRIDE      0x10
#define TBL_ROWS_SHORT  4
#define TBL_ROWS_TALL   16
#define TBL_KEY_OFF     1000                                /* the hit/grow/clip key's src_off */
#define TBL_FILL_OFF    2000                                /* the fill keys' first src_off */
#define TBL_FILL_STEP   OBJSH_CELL_BYTES                    /* distinct keys, one source cell apart */
#define TBL_SERVED      1                                   /* the table path must draw this case */
#define TBL_DECLINED    0                                   /* ...must decline it to the CPU hybrid */
/* GROW/CLIP(3) + HIT(2) + the fill + FULL + latched + the post-flush re-arm. */
#define N_TBL_CASES     (OBJSH_SKEW_TABLE_ENTRIES + 8)
#define N_TBL_SERVED    (N_TBL_CASES - 2)                   /* every case but FULL and the latched one */

static uint16_t tbl_case_diff[N_TBL_CASES];
static long tbl_served;                                     /* cases the table path drew */
static uint16_t tbl_cases_run;                              /* cases actually logged (the layout check) */

/* One table case. Draw with the CPU reference, then with the tabled skew path; a case expected to
 * DECLINE must leave the framebuffer untouched and is then completed by the CPU hybrid — the shipping
 * dispatch's own fallback. Returns the mismatch count (0 == the branch behaved AND the pixels match). */
static long run_case_table(uint32_t src_off, int rows, int expect_served, int *served_out) {
    for (int i = 0; i < SCREEN_BYTES; i++) ref_fb[i] = test_fb[i] = SWEEP_BG_BYTE;
    for (int i = 0; i < GUARD_BYTES; i++)
        osh_src_g.lo[i] = osh_src_g.hi[i] = test_g.lo[i] = test_g.hi[i] = GUARD_FILL;
    osh_src_refill(TBL_CELLS, TBL_COLOR);   /* the content must stay put: the table keys on the ADDRESS */

    uint16_t x = make_x(TBL_COL, TBL_FINE_X);
    uint16_t rows_m1 = (uint16_t)(rows - 1);
    uint32_t dst_off = (uint32_t)((SCREEN_H / 2) * SCREEN_ROW_BYTES);   /* mid-screen; both walk up */
    rm_blit_objshift(ref_fb, dst_off, osh_src, src_off, x, TBL_COLOR, rows_m1, TBL_STRIDE,
                     osh_pairs, TBL_CELLS);
    int served = rm_blit_objshift_skew_tabled(test_fb, dst_off, osh_src, src_off, x, TBL_COLOR, rows_m1,
                                              TBL_STRIDE, osh_pairs, TBL_CELLS);
    *served_out = served;

    long n = (served != expect_served) ? 1 : 0;             /* the branch this case exists to pin */
    if (!served) {
        for (int i = 0; i < SCREEN_BYTES; i++) if (test_fb[i] != SWEEP_BG_BYTE) n++;   /* drew nothing */
        RM_BLIT_OBJSHIFT(test_fb, dst_off, osh_src, src_off, x, TBL_COLOR, rows_m1, TBL_STRIDE,
                         osh_pairs, TBL_CELLS);             /* the dispatch's CPU hybrid completes it */
    }
    for (int i = 0; i < SCREEN_BYTES; i++) if (ref_fb[i] != test_fb[i]) n++;
    n += guard_broken(osh_src_g.lo) + guard_broken(osh_src_g.hi) +
         guard_broken(test_g.lo) + guard_broken(test_g.hi);
    return n;
}

/* Run one table case and log it into the report grid. */
static long tbl_case(uint32_t src_off, int rows, int expect_served) {
    int served;
    long d = run_case_table(src_off, rows, expect_served, &served);
    uint16_t logged = (uint16_t)(d > 0xffff ? 0xffff : d);
    if (tbl_cases_run < N_TBL_CASES) tbl_case_diff[tbl_cases_run] = logged;
    tbl_cases_run++;
    tbl_served += served ? 1 : 0;
    return logged;
}

/* Run the whole table section in order; the state each case leaves is the next case's precondition, so
 * the sequence IS the test. Accumulates tbl_served / tbl_cases_run and returns the summed mismatch. */
static long sweep_table_section(void) {
    long total = 0;

    /* GROW FIRST, on a table nothing has touched yet. A missing grow is only VISIBLE if the rows the
     * un-grown entry never materialised hold something other than the right bytes — and had this key's
     * slot already held a taller materialise of the SAME key, those stale words would be exactly right
     * and a dropped grow would blit correct pixels by accident. Before any other case runs, the table is
     * static BSS: the deep words are zero, which no correct blit of this sprite produces. (A flush only
     * frees entries; it does not scrub their bitmaps, and scrubbing 126 KB per flush to make the order
     * not matter would cost the shipping route real time for a measurement build's benefit.) */
    rm_blit_objshift_skew_table_flush();
    total += tbl_case(TBL_KEY_OFF, TBL_ROWS_SHORT, TBL_SERVED);   /* first sight, only 4 rows deep */
    total += tbl_case(TBL_KEY_OFF, TBL_ROWS_TALL,  TBL_SERVED);   /* GROW: re-materialise deeper */
    total += tbl_case(TBL_KEY_OFF, TBL_ROWS_SHORT, TBL_SERVED);   /* CLIP a taller entry via y_count */

    rm_blit_objshift_skew_table_flush();
    total += tbl_case(TBL_KEY_OFF, TBL_ROWS_TALL,  TBL_SERVED);   /* first sight: materialise 16 rows */
    total += tbl_case(TBL_KEY_OFF, TBL_ROWS_TALL,  TBL_SERVED);   /* HIT: served straight off the table */

    rm_blit_objshift_skew_table_flush();
    for (int i = 0; i < OBJSH_SKEW_TABLE_ENTRIES; i++)            /* claim every entry: all must serve */
        total += tbl_case(TBL_FILL_OFF + (uint32_t)i * TBL_FILL_STEP, TBL_ROWS_SHORT, TBL_SERVED);
    total += tbl_case(TBL_FILL_OFF + (uint32_t)OBJSH_SKEW_TABLE_ENTRIES * TBL_FILL_STEP,
                      TBL_ROWS_SHORT, TBL_DECLINED);              /* FULL: no room -> the CPU hybrid */
    total += tbl_case(TBL_FILL_OFF, TBL_ROWS_SHORT, TBL_DECLINED);/* latched: even a TABLED key declines */

    rm_blit_objshift_skew_table_flush();                          /* the flush re-arms the whole route */
    total += tbl_case(TBL_FILL_OFF, TBL_ROWS_SHORT, TBL_SERVED);
    rm_blit_objshift_skew_table_flush();                          /* leave no state for the bench below */
    return total;
}

/* ---- slice-1 cost structure: how expensive is one skew blit, split materialise vs chip passes? ----
 * Timed on the TOS 200 Hz counter (SYS_HZ200, st.h — 5 ms/tick = 40000 cycles at the ST's 8 MHz) over a case the
 * grid above actually SWEEPS — base_cells 2 (the widest family) at rows_m1 0x1f (32 rows, the grid's
 * tallest case), so the timed shape is one the byte-exactness pin covers. The shipping CPU engine
 * (RM_BLIT_OBJSHIFT — the hand-written m68k core where this build selects it, the C reference under a
 * per-core bisect) is timed on the same case as the reference point that decides whether the skew path
 * is worth routing. Reported raw (ticks + iteration count) so the runner does the arithmetic.
 *
 * TWO colour tables, because the pass count depends on the fill: the swept synthetic table has four
 * non-zero plane fills (8 passes), while the GAME's own table at colour 3 fills two planes and zeroes
 * two (6 passes — the OR pass is skipped outright for a zero fill). The chip passes are ALSO timed in
 * isolation, re-fired on an already-materialised bitmap set, rather than inferred by subtracting two
 * near-equal totals. */
#define OSH_BENCH_ITERS   1000
#define OSH_BENCH_CELLS   2
#define OSH_BENCH_ROWS_M1 0x1f
#define OSH_BENCH_STRIDE  8
#define OSH_BENCH_COLOR   3                                 /* binary table: planes 0,1 filled -> 6 passes */
#define OSH_BENCH_COL     0x40                              /* a BASE column (no clip) */
#define OSH_BENCH_FINE_X  0xb                               /* a non-zero fine_x: the straddling shape */
#define OSH_BENCH_ROWS    (OSH_BENCH_ROWS_M1 + 1)

static ObjshSkewBitmaps bench_bm;                           /* the sweep's own set (the slice-2 seam) */
static uint32_t bench_dst_off;
static uint16_t bench_x;
static long bench_declined;                                 /* timed calls that did NOT draw — must be 0 */
static uint16_t bench_mat_ticks, bench_pass_synth_ticks, bench_pass_binary_ticks;
static uint16_t bench_all_synth_ticks, bench_all_binary_ticks, bench_cpu_ticks;

/* A timed call that the path DECLINED would clock a no-op and report a fantasy cost, so every bench
 * loop routes its return through here and the tally ships in its own report word. */
static void bench_note_handled(int handled) { if (!handled) bench_declined++; }

static void bench_materialise(void) {
    rm_objsh_skew_materialise(&bench_bm, osh_src, OSH_SRC_OFF, OSH_BENCH_STRIDE, OSH_BENCH_ROWS,
                              OSH_BENCH_CELLS);
}
static void bench_passes(const uint8_t *pairs) {
    bench_note_handled(rm_blit_objshift_skew_from(&bench_bm, test_fb, bench_dst_off, bench_x,
                                                  OSH_BENCH_COLOR, OSH_BENCH_ROWS_M1, pairs,
                                                  OSH_BENCH_CELLS));
}
static void bench_passes_synth(void)  { bench_passes(osh_pairs); }
static void bench_passes_binary(void) { bench_passes(osh_pairs_binary); }

static void bench_all(const uint8_t *pairs) {
    bench_note_handled(rm_blit_objshift_skew(test_fb, bench_dst_off, osh_src, OSH_SRC_OFF, bench_x,
                                             OSH_BENCH_COLOR, OSH_BENCH_ROWS_M1, OSH_BENCH_STRIDE,
                                             pairs, OSH_BENCH_CELLS));
}
static void bench_all_synth(void)  { bench_all(osh_pairs); }
static void bench_all_binary(void) { bench_all(osh_pairs_binary); }

/* The CPU reference point. RM_BLIT_OBJSHIFT (game.h) is the hand-written core under this build's
 * -DRM_ASM_BLIT and the C engine under a per-core bisect (-URM_ASM_OBJSHIFT), so the sweep build stays
 * bisect-neutral instead of hard-wiring the asm symbol. */
static void bench_cpu(void) {
    RM_BLIT_OBJSHIFT(test_fb, bench_dst_off, osh_src, OSH_SRC_OFF, bench_x, OSH_BENCH_COLOR,
                     OSH_BENCH_ROWS_M1, OSH_BENCH_STRIDE, osh_pairs, OSH_BENCH_CELLS);
}

/* One timing block for all six measurements: same loop, same call overhead, so the numbers compare. */
typedef void (*BenchFn)(void);
static uint16_t bench_ticks(BenchFn fn) {
    uint32_t t0 = SYS_HZ200;
    for (int i = 0; i < OSH_BENCH_ITERS; i++) fn();
    return (uint16_t)(SYS_HZ200 - t0);
}

static void sweep_bench(void) {
    osh_src_refill(OSH_BENCH_CELLS, OSH_BENCH_COLOR);       /* the bench owns its source, not the grid's */
    bench_x = make_x(OSH_BENCH_COL, OSH_BENCH_FINE_X);
    bench_dst_off = (uint32_t)((SCREEN_H / 2) * SCREEN_ROW_BYTES);
    bench_materialise();                                    /* the pass-only loops re-fire this set */

    bench_mat_ticks          = bench_ticks(bench_materialise);
    bench_pass_synth_ticks   = bench_ticks(bench_passes_synth);
    bench_pass_binary_ticks  = bench_ticks(bench_passes_binary);
    bench_all_synth_ticks    = bench_ticks(bench_all_synth);
    bench_all_binary_ticks   = bench_ticks(bench_all_binary);
    bench_cpu_ticks          = bench_ticks(bench_cpu);
}

/* Which sections this build ran (report word; the runner must not read a skipped grid as "clean"). */
#define SWEEP_GRID_OBJSHIFT2    1
#define SWEEP_GRID_OSH_PRESHIFT 2
#define SWEEP_GRID_OSH_SKEW     4
#define SWEEP_GRID_OSH_TABLE    8
static uint16_t sweep_grids_run;

/* The objshift2 grid: the fixed-pass engine's own case space. Same shape as sweep_objsh_grid — returns
 * the summed mismatch and reports the BASE cases the blitter path drew. */
static long sweep_objshift2_grid(long *handled_out) {
    int idx = 0;
    long total = 0, handled_count = 0;
    for (int wi = 0; wi < N_WIDTH; wi++)
        for (int fx = 0; fx < N_FINEX; fx++)
            for (int ci = 0; ci < N_COL; ci++)
                for (int ri = 0; ri < N_ROWS; ri++) {
                    int handled;
                    long d = run_case(SWEEP_WIDTH_IDX[wi], fx, SWEEP_COLUMNS[ci], SWEEP_ROWS_M1[ri], &handled);
                    uint16_t logged = handled ? (uint16_t)(d > 0xffff ? 0xffff : d) : 0;
                    case_diff[idx++] = logged;
                    total += logged;
                    handled_count += handled ? 1 : 0;
                }
    *handled_out = handled_count;
    return total;
}

/* Sweep every case for all four sections. A handled (BASE) case must be byte-exact; a declined (CLIP)
 * case is the CPU hybrid (blitter drew nothing) — EXPECTED, not a mismatch. Only handled cases
 * contribute.
 *
 * A MUTATE build runs the two SKEW-route sections alone — the grid and the table: the mutation knob
 * touches nothing the other two grids drive, so re-sweeping them would only burn emulated cycles (the
 * coverage check builds one of these per mutation). The bench is skipped with them — it would be timing
 * a deliberately broken configuration. sweep_grids_run tells the runner which sections the numbers
 * describe, and run_ste_sweep.py knows which section each mutation must make fail. */
long blitter_sweep_super(void) {
    long total = 0;
    sweep_init_pairs();

    /* A plain `if` on the compile-time knob, not an #if: the mutate build then still COMPILES the grids
     * it skips, so a change that breaks them cannot hide behind the mutation flag. */
    if (!RM_SKEW_MUTATED) {
        total += sweep_objshift2_grid(&sweep_handled);
        sweep_grids_run |= SWEEP_GRID_OBJSHIFT2;
        total += sweep_objsh_grid(rm_blit_objshift_blitter, osh_case_diff, &osh_handled);
        sweep_grids_run |= SWEEP_GRID_OSH_PRESHIFT;
    }
    total += sweep_objsh_grid(rm_blit_objshift_skew, skew_case_diff, &skew_handled);
    sweep_grids_run |= SWEEP_GRID_OSH_SKEW;
    total += sweep_table_section();
    sweep_grids_run |= SWEEP_GRID_OSH_TABLE;

    if (!RM_SKEW_MUTATED) sweep_bench();
    sweep_total = total;                                    /* combined: every section run must be 0 */
    return total;
}

/* Pack the per-case grid into a framebuffer for SCREEN.BIN: word0 = total case count (objshift2, then
 * objshift pre-shift, then objshift hardware-skew, then the table section), word1 = total mismatch
 * (every section run), then the concatenated per-case diff words. run_ste_sweep.py parses it; the tail
 * indices are mirrored there.
 *
 * The tail is SELF-DESCRIBING: besides the BASE-handled counts and the cost bench it carries the section
 * LAYOUT (per-section case counts), the count each section is expected to have drawn, and which sections
 * this build ran. Those let the runner locate each section and prove it non-vacuous from the report
 * itself instead of from Python literals that can silently drift out of step with this file. */
#define SWEEP_REPORT_WORDS        (SCREEN_BYTES / 2)
#define SWEEP_TAIL_HANDLED2       1                         /* counted back from the end of the report */
#define SWEEP_TAIL_HANDLED_OSH    2
#define SWEEP_TAIL_HANDLED_SKEW   3
#define SWEEP_TAIL_N_CASES2       4                         /* layout: objshift2 grid case count */
#define SWEEP_TAIL_N_CASES_OSH    5                         /* layout: each colour grid's case count */
#define SWEEP_TAIL_EXPECT_BASE    6                         /* BASE cases a colour grid must handle */
#define SWEEP_TAIL_GRIDS_RUN      7                         /* SWEEP_GRID_* bitmask */
#define SWEEP_TAIL_BENCH_ITERS    8
#define SWEEP_TAIL_BENCH_MAT      9
#define SWEEP_TAIL_BENCH_PASS_SYN 10
#define SWEEP_TAIL_BENCH_PASS_BIN 11
#define SWEEP_TAIL_BENCH_ALL_SYN  12
#define SWEEP_TAIL_BENCH_ALL_BIN  13
#define SWEEP_TAIL_BENCH_CPU      14
#define SWEEP_TAIL_BENCH_DECLINED 15                        /* timed calls that did NOT draw (must be 0) */
#define SWEEP_TAIL_N_CASES_TBL    16                        /* layout: the table section's case count */
#define SWEEP_TAIL_CASES_RUN_TBL  17                        /* cases it actually logged (layout check) */
#define SWEEP_TAIL_SERVED_TBL     18                        /* table-section cases the table path drew */
#define SWEEP_TAIL_EXPECT_TBL     19                        /* ...and how many it must have drawn */
#define SWEEP_TAIL_WORDS          SWEEP_TAIL_EXPECT_TBL
/* The four per-case sections must not run into the tail words (they share one 32000-byte report). */
typedef char sweep_report_fits[(2 + N_CASES + 2 * N_OSH_CASES + N_TBL_CASES
                                <= SWEEP_REPORT_WORDS - SWEEP_TAIL_WORDS) ? 1 : -1];

const uint8_t *blitter_sweep(long *mismatch_out) {
    Supexec(blitter_sweep_super);
    uint16_t *w = (uint16_t *)test_fb;
    for (int i = 0; i < SWEEP_REPORT_WORDS; i++) w[i] = 0;
    w[0] = (uint16_t)(N_CASES + 2 * N_OSH_CASES + N_TBL_CASES);
    w[1] = (uint16_t)(sweep_total > 0xffff ? 0xffff : sweep_total);
    int at = 2;
    for (int i = 0; i < N_CASES; i++) w[at++] = case_diff[i];
    for (int i = 0; i < N_OSH_CASES; i++) w[at++] = osh_case_diff[i];
    for (int i = 0; i < N_OSH_CASES; i++) w[at++] = skew_case_diff[i];
    for (int i = 0; i < N_TBL_CASES; i++) w[at++] = tbl_case_diff[i];
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_HANDLED2]       = (uint16_t)sweep_handled;  /* objshift2 BASE drawn */
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_HANDLED_OSH]    = (uint16_t)osh_handled;    /* objshift  BASE drawn */
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_HANDLED_SKEW]   = (uint16_t)skew_handled;   /* skew path BASE drawn */
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_N_CASES2]       = (uint16_t)N_CASES;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_N_CASES_OSH]    = (uint16_t)N_OSH_CASES;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_EXPECT_BASE]    = (uint16_t)osh_expected_base_cases();
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_GRIDS_RUN]      = sweep_grids_run;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_N_CASES_TBL]    = (uint16_t)N_TBL_CASES;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_CASES_RUN_TBL]  = tbl_cases_run;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_SERVED_TBL]     = (uint16_t)tbl_served;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_EXPECT_TBL]     = (uint16_t)N_TBL_SERVED;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_BENCH_ITERS]    = OSH_BENCH_ITERS;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_BENCH_MAT]      = bench_mat_ticks;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_BENCH_PASS_SYN] = bench_pass_synth_ticks;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_BENCH_PASS_BIN] = bench_pass_binary_ticks;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_BENCH_ALL_SYN]  = bench_all_synth_ticks;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_BENCH_ALL_BIN]  = bench_all_binary_ticks;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_BENCH_CPU]      = bench_cpu_ticks;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_BENCH_DECLINED] = (uint16_t)(bench_declined > 0xffff ? 0xffff
                                                                                           : bench_declined);
    if (mismatch_out) *mismatch_out = sweep_total;
    return test_fb;
}
