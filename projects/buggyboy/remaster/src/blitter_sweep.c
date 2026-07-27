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
 * full-table decline — would ship unpinned. A fifth blits at and past the BOTTOM EDGE (see
 * sweep_below_screen_grid), where the sprite fragments the shell's overdraw tail exists for land. A
 * sixth sweeps the ROAD FINE-SCROLL route (see sweep_scroll_section) over every reachable scroll
 * position — a different engine entirely: whole-band rectangular blits, not a masked sprite.
 */
#include "blitter.h"
#include "screen.h"
#include "blit_const.h"
#include "game.h"
#include "scroll_const.h"

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

/* Both framebuffers carry a TAIL past the visible screen, and every compare in this file spans it. The
 * below-screen section deliberately blits with its first-drawn row up to SWEEP_BELOW_UNDER_MAX scanlines
 * under the bottom edge, so the tail is sized from THAT case space (+1 row of slack for the blit itself)
 * rather than copied from the shell's SCREEN_OVERDRAW — the sweep owns its own buffers. The on-screen
 * grids then also prove they leave the tail alone, and the guard bands past it stay the overrun trip. */
#define SWEEP_BELOW_UNDER_MAX 16
#define SWEEP_FB_TAIL   ((SWEEP_BELOW_UNDER_MAX + 2) * SCREEN_ROW_BYTES)
#define SWEEP_FB_BYTES  (SCREEN_BYTES + SWEEP_FB_TAIL)

/* x that yields aligned column `col` (multiple of 8) and low nibble `fine_x`: col = ((int16)x>>1)&~7,
 * fine_x = x&0xf, so x = 2*col + fine_x. */
static uint16_t make_x(int col, int fine_x) { return (uint16_t)(2 * col + fine_x); }

static struct { uint8_t lo[GUARD_BYTES]; uint8_t px[SWEEP_SRC_ROWS * OBJSH2_SRC_ROW_BYTES]; uint8_t hi[GUARD_BYTES]; } src_g;
static struct { uint8_t lo[GUARD_BYTES]; uint8_t px[SWEEP_FB_BYTES]; uint8_t hi[GUARD_BYTES]; } test_g;
/* The CPU reference framebuffer is guarded too, now that the sweep deliberately blits below the visible
 * screen: a reference engine that ran off the end would otherwise silently eat the next BSS object. */
static struct { uint8_t lo[GUARD_BYTES]; uint8_t px[SWEEP_FB_BYTES]; uint8_t hi[GUARD_BYTES]; } ref_g;
#define src_sprite (src_g.px)
#define test_fb    (test_g.px)
#define ref_fb     (ref_g.px)
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

/* Every case re-arms the guard bands on all four buffers — both sources and both framebuffers: they are
 * the overrun tripwire and must not carry a previous case's damage forward. */
static void sweep_arm_guards(void) {
    for (int i = 0; i < GUARD_BYTES; i++)
        src_g.lo[i] = src_g.hi[i] = osh_src_g.lo[i] = osh_src_g.hi[i] =
            test_g.lo[i] = test_g.hi[i] = ref_g.lo[i] = ref_g.hi[i] = GUARD_FILL;
}

static long sweep_guards_broken(void) {
    return guard_broken(src_g.lo) + guard_broken(src_g.hi) +
           guard_broken(osh_src_g.lo) + guard_broken(osh_src_g.hi) +
           guard_broken(test_g.lo) + guard_broken(test_g.hi) +
           guard_broken(ref_g.lo) + guard_broken(ref_g.hi);
}

/* Bytes on which the two framebuffers disagree, over the visible screen AND the overdraw tail — so a
 * chip path that wrote past the bottom edge where the CPU path did not is a mismatch, not invisible. */
static long sweep_fb_diff(void) {
    long n = 0;
    for (int i = 0; i < SWEEP_FB_BYTES; i++) if (ref_fb[i] != test_fb[i]) n++;
    return n;
}

/* Draw one case with the CPU engine (ref) and the blitter path (test) over the same background; count
 * differing framebuffer bytes + any broken guard. handled_out reports the blitter path's return.
 * dst_off addresses the blit's first-drawn (bottom) row — the below-screen section puts it under the
 * visible screen, the grids mid-screen. */
static long run_case(int width_idx, int fine_x, int col, int rows_m1, uint32_t dst_off,
                     int *handled_out) {
    for (int i = 0; i < SWEEP_FB_BYTES; i++) ref_fb[i] = test_fb[i] = SWEEP_BG_BYTE;
    sweep_arm_guards();

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

    /* src_off top row reads offset 0 (both engines walk up from the caller's bottom row). */
    uint32_t src_off = (uint32_t)((rows > 0 ? rows - 1 : 0) * OBJSH2_SRC_ROW_BYTES);

    rm_blit_objshift2(ref_fb, dst_off, src_sprite, src_off, x, (uint16_t)rows_m1, width_idx);
    *handled_out = rm_blit_objshift2_blitter(test_fb, dst_off, src_sprite, src_off, x, (uint16_t)rows_m1, width_idx);

    return sweep_fb_diff() + sweep_guards_broken();
}

/* The bottom row the objshift2 grid blits at: low enough on the screen that even its tallest case
 * (rows_m1 0x2a) stays wholly visible. */
static uint32_t sweep_grid_dst_off(int rows) {
    return (uint32_t)((SCREEN_H / 4 + (rows > 0 ? rows - 1 : 0)) * SCREEN_ROW_BYTES);
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
 * refill it only when that key changes (sweep_arm_guards still re-arms every band on every case). */
static int osh_src_key_cells = -1, osh_src_key_color = -1;
static void osh_src_refill(int base_cells, int color) {
    if (base_cells == osh_src_key_cells && color == osh_src_key_color) return;
    for (int i = 0; i < OSH_SRC_BYTES - 1; i += 2) wr16(osh_src + i, pattern(i, base_cells, color));
    osh_src_key_cells = base_cells;
    osh_src_key_color = color;
}

/* The mid-screen bottom row the colour grids blit at (the colour engine's own tallest case still fits). */
#define OSH_GRID_DST_OFF ((uint32_t)((SCREEN_H / 2) * SCREEN_ROW_BYTES))

/* One colour-engine case: draw with the CPU rm_blit_objshift (ref) and `test_fn` (the pre-shift or the
 * hardware-skew blitter path) over the same background; count differing bytes + broken guards.
 * dst_off addresses the blit's first-drawn (bottom) row (see run_case). */
static long run_case_objsh(ObjshBlitFn test_fn, int base_cells, int fine_x, int col, int color,
                           int rows_m1, int16_t stride, uint32_t dst_off, int *handled_out) {
    for (int i = 0; i < SWEEP_FB_BYTES; i++) ref_fb[i] = test_fb[i] = SWEEP_BG_BYTE;
    sweep_arm_guards();
    osh_src_refill(base_cells, color);

    uint16_t x = make_x(col, fine_x);
    rm_blit_objshift(ref_fb, dst_off, osh_src, OSH_SRC_OFF, x, (uint16_t)color, (uint16_t)rows_m1, stride,
                     osh_pairs, base_cells);
    *handled_out = test_fn(test_fb, dst_off, osh_src, OSH_SRC_OFF, x, (uint16_t)color,
                           (uint16_t)rows_m1, stride, osh_pairs, base_cells);
    return sweep_fb_diff() + sweep_guards_broken();
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
                                            OSH_GRID_DST_OFF, &handled);
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
    for (int i = 0; i < SWEEP_FB_BYTES; i++) ref_fb[i] = test_fb[i] = SWEEP_BG_BYTE;
    sweep_arm_guards();
    osh_src_refill(TBL_CELLS, TBL_COLOR);   /* the content must stay put: the table keys on the ADDRESS */

    uint16_t x = make_x(TBL_COL, TBL_FINE_X);
    uint16_t rows_m1 = (uint16_t)(rows - 1);
    rm_blit_objshift(ref_fb, OSH_GRID_DST_OFF, osh_src, src_off, x, TBL_COLOR, rows_m1, TBL_STRIDE,
                     osh_pairs, TBL_CELLS);
    int served = rm_blit_objshift_skew_tabled(test_fb, OSH_GRID_DST_OFF, osh_src, src_off, x, TBL_COLOR,
                                              rows_m1, TBL_STRIDE, osh_pairs, TBL_CELLS);
    *served_out = served;

    long n = (served != expect_served) ? 1 : 0;             /* the branch this case exists to pin */
    if (!served) {
        for (int i = 0; i < SWEEP_FB_BYTES; i++) if (test_fb[i] != SWEEP_BG_BYTE) n++;  /* drew nothing */
        RM_BLIT_OBJSHIFT(test_fb, OSH_GRID_DST_OFF, osh_src, src_off, x, TBL_COLOR, rows_m1, TBL_STRIDE,
                         osh_pairs, TBL_CELLS);             /* the dispatch's CPU hybrid completes it */
    }
    return n + sweep_fb_diff() + sweep_guards_broken();
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
     * and a dropped grow would blit correct pixels by accident. Before any other case runs the table is
     * still all zeroes: rm_blit_bind_all ZEROES the window it places both tables in (src/blitter.c — the
     * free TPA it carves them from is uninitialised, so the placer scrubs it), and zero deep words are
     * what no correct blit of this sprite produces. That placement is also why the sweep must run AFTER
     * the boot bind — main() binds first, then enters this build's entry point. (A flush only frees
     * entries; it does not scrub their bitmaps, and scrubbing 126 KB per flush to make the order not
     * matter would cost the shipping route real time for a measurement build's benefit.) */
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

/* ---- the BELOW-SCREEN section: both shipping routes at and past the bottom edge -------------------
 * Every grid above blits mid-screen, so nothing there pins what either path writes BELOW the last
 * visible scanline — which is exactly the region game_main.c's SCREEN_OVERDRAW tail exists to absorb,
 * and exactly where a chip path that clipped, clamped or wrapped differently from the CPU engine would
 * corrupt whatever follows the buffer. The family predicates (rm_blit_objshift2_is_base / objsh_is_base,
 * blitter.h) are purely HORIZONTAL — they never look at the destination row — so neither path declines a
 * below-screen destination: both really draw, and the pin is the full-buffer comparison, tail included
 * (sweep_fb_diff spans SWEEP_FB_BYTES, and the guard bands past it catch anyone who goes further).
 *
 * Cases: each route x {flush with the bottom edge, straddling it, wholly below it} x fine_x {0, a
 * straddling nibble} x its two extreme width/base_cells. BASE columns throughout, so every case draws. */
static const int SWEEP_BELOW_UNDER[]  = {0, 1, 3, SWEEP_BELOW_UNDER_MAX};  /* rows under the last visible one */
static const int SWEEP_BELOW_FINE_X[] = {0, 0xb};                          /* aligned, and a straddling nibble */
static const int SWEEP_BELOW_WIDTH[]  = {0, 2};                            /* objshift2's widest / narrowest */
#define SWEEP_BELOW_COL     0x40                            /* a BASE column for both routes */
#define SWEEP_BELOW_ROWS_M1 3
#define SWEEP_BELOW_COLOR   3
#define SWEEP_BELOW_STRIDE  0x10
#define N_BELOW_UNDER  (int)(sizeof SWEEP_BELOW_UNDER  / sizeof SWEEP_BELOW_UNDER[0])
#define N_BELOW_FINEX  (int)(sizeof SWEEP_BELOW_FINE_X / sizeof SWEEP_BELOW_FINE_X[0])
#define N_BELOW_WIDTH  (int)(sizeof SWEEP_BELOW_WIDTH  / sizeof SWEEP_BELOW_WIDTH[0])
/* objshift2 (one case per width) + the colour skew route (one per base_cells), at every under x fine_x. */
#define N_BELOW_CASES  (N_BELOW_UNDER * N_BELOW_FINEX * (N_BELOW_WIDTH + N_OSH_BC))

static uint16_t below_case_diff[N_BELOW_CASES];
static long below_handled;
static int below_idx;                                       /* the case cursor sweep_below_case logs at */

/* The blit's first-drawn (bottom) row `under` scanlines below the last visible one. */
static uint32_t below_dst_off(int under) {
    return (uint32_t)((SCREEN_H - 1 + under) * SCREEN_ROW_BYTES);
}

/* Log one below-screen case. Unlike the grids above, a DECLINED case is logged with its real mismatch
 * rather than as 0: no case here may be declined (the family predicates are horizontal-only), so a
 * blitter path that drew nothing while the CPU engine drew must show up as the failure it is. */
static long sweep_below_case(long d, int handled) {
    uint16_t logged = (uint16_t)(d > 0xffff ? 0xffff : d);
    below_case_diff[below_idx++] = logged;
    below_handled += handled ? 1 : 0;
    return logged;
}

static long sweep_below_screen_grid(void) {
    long total = 0;
    for (int ui = 0; ui < N_BELOW_UNDER; ui++)
        for (int fi = 0; fi < N_BELOW_FINEX; fi++) {
            uint32_t dst_off = below_dst_off(SWEEP_BELOW_UNDER[ui]);
            int fine_x = SWEEP_BELOW_FINE_X[fi];
            int handled;
            long d;
            for (int wi = 0; wi < N_BELOW_WIDTH; wi++) {
                d = run_case(SWEEP_BELOW_WIDTH[wi], fine_x, SWEEP_BELOW_COL, SWEEP_BELOW_ROWS_M1,
                             dst_off, &handled);
                total += sweep_below_case(d, handled);
            }
            for (int bi = 0; bi < N_OSH_BC; bi++) {
                d = run_case_objsh(rm_blit_objshift_skew, OSH_BASE_CELLS[bi], fine_x, SWEEP_BELOW_COL,
                                   SWEEP_BELOW_COLOR, SWEEP_BELOW_ROWS_M1, SWEEP_BELOW_STRIDE,
                                   dst_off, &handled);
                total += sweep_below_case(d, handled);
            }
        }
    return total;
}

/* ---- the ROAD FINE-SCROLL section (src/blitter_scroll.c) ----------------------------------------
 * A different engine from everything above: no sprite, no mask — two source-less constant fills and one
 * or two whole-band rectangular copies, with a CPU seam the chip cannot compute. Its whole case space is
 * the scroll POSITION, and that space is small enough to sweep EXHAUSTIVELY: hscroll_pos wraps modulo
 * SCROLL_WRAP, so 640 cases cover every (shift x coarse column x edge) combination the game can reach —
 * including edge == -1 (no wrap), edge == 0 (a seam with no wrap columns), shift == 0 with an edge (the
 * seam that computes to a no-op), and the maximum edge (one main column left).
 *
 * The playfield is deterministic pseudo-random (a seeded LCG — no clock, no host randomness, so every
 * run compares the same bytes) put through the REAL rm_scroll_prebuild, so the 16 pre-rotated copies the
 * routes read have exactly the shipping shape, copy 0 raw included (which is what the seam reads).
 *
 * The scalar head is swept too: each case starts from the hscroll_pos that a NON-ZERO delta advances onto
 * the case's position, alternating the delta's SIGN case by case so both wrap branches run (a negative
 * seg_head is a left curve; positive-only cases never reach the `(int16_t)h < 0` correction). What the
 * ScrollState compare then pins is that rm_blit_road_scroll — the C entry the ST calls — is exactly
 * `head once, then draw`: the reference side calls it whole, the test side calls the head and the draw
 * separately, so a wrapper that advanced twice would show up as a position mismatch. It does NOT pin the
 * blitter DISPATCH's own head-once property (the dispatch takes a Supexec, which cannot nest inside the
 * one this sweep already runs in); run_ste_ab.py is what pins that, by diffing whole frames of the SAME
 * PRG driven on both machines. */
#define SCROLL_SEG_HEAD    3                                /* |delta| = SEG_HEAD * SPEED = 15: a non-zero */
#define SCROLL_SPEED       5                                /* head, so the wrap arithmetic really runs */
#define SCROLL_DELTA       (SCROLL_SEG_HEAD * SCROLL_SPEED)
#define SCROLL_PLAYFIELD_BYTES (RM_SCROLL_WINDOW + ROAD_COL_BYTES)   /* prebuild pairs word b with b+8 */
#define N_SCROLL_CASES     SCROLL_WRAP                      /* 640 = every reachable hscroll_pos */
/* A plain LCG (the classic glibc constants); only its determinism matters, not its statistics. */
#define SCROLL_LCG_SEED    0x13579BDFu
#define SCROLL_LCG_MUL     1103515245u
#define SCROLL_LCG_ADD     12345u

/* aligned(2) like the shell's own copies (game_main.c / bench_main.c): the prebuild's wr16/be16 are raw
 * word accesses on the big-endian target, and the blitter's src_addr ignores bit 0 — an odd base would
 * address-error on one route and silently blit from base-1 on the other. */
static uint8_t scroll_playfield[SCROLL_PLAYFIELD_BYTES] __attribute__((aligned(2)));
static uint8_t scroll_shifted[RM_SCROLL_SHIFTS * RM_SCROLL_WINDOW] __attribute__((aligned(2)));
static uint16_t scroll_case_diff[N_SCROLL_CASES];
static long scroll_routed;                                  /* cases the blitter route drew */

static void scroll_init_playfield(void) {
    uint32_t r = SCROLL_LCG_SEED;
    for (uint32_t i = 0; i < SCROLL_PLAYFIELD_BYTES; i++) {
        r = r * SCROLL_LCG_MUL + SCROLL_LCG_ADD;
        scroll_playfield[i] = (uint8_t)(r >> 24);           /* the high byte: the LCG's best-mixed bits */
    }
    rm_scroll_prebuild(scroll_playfield, scroll_shifted);
}

/* The freestanding shim (render/atari/shim.c) has no memcmp, and adding one for a measurement build
 * would put dead code in the shipping PRG — so compare the state's bytes here. */
static int scroll_state_differs(const ScrollState *a, const ScrollState *b) {
    const uint8_t *pa = (const uint8_t *)a, *pb = (const uint8_t *)b;
    for (unsigned i = 0; i < sizeof(ScrollState); i++) if (pa[i] != pb[i]) return 1;
    return 0;
}

/* One scroll case: land both routes on scroll position `hpos` from a state SCROLL_DELTA behind it, draw
 * with the C reference (ref) and the blitter route (test), and count differing framebuffer bytes, broken
 * guards, and any disagreement in the ScrollState the head left. */
static long run_case_scroll(uint16_t hpos, int negative_delta) {
    for (int i = 0; i < SWEEP_FB_BYTES; i++) ref_fb[i] = test_fb[i] = SWEEP_BG_BYTE;
    sweep_arm_guards();

    /* Start SCROLL_DELTA short of (or past) hpos so the head lands exactly on it either way. */
    ScrollState ref_state, test_state;
    ref_state.seg_head = (int16_t)(negative_delta ? -SCROLL_SEG_HEAD : SCROLL_SEG_HEAD);
    ref_state.scroll_speed = SCROLL_SPEED;
    ref_state.hscroll_pos = (uint16_t)((hpos + (negative_delta ? SCROLL_DELTA
                                                              : SCROLL_WRAP - SCROLL_DELTA)) % SCROLL_WRAP);
    ref_state.hscroll_step2 = 0;
    test_state = ref_state;

    rm_blit_road_scroll(&ref_state, scroll_shifted, (Framebuffer *)ref_fb);
    /* The blitter route's dispatch would enter a nested Supexec (the whole sweep already runs in one),
     * so drive its supervisor half directly — head first, exactly as the dispatch does. */
    ScrollGeometry geo = rm_scroll_advance(&test_state);
    rm_blit_road_scroll_draw(&geo, scroll_shifted, (Framebuffer *)test_fb);

    long n = sweep_fb_diff() + sweep_guards_broken();
    /* The WHOLE state, not the two fields the head writes: a route that clobbered seg_head or
     * scroll_speed would draw perfect pixels and pass a field-picked compare. */
    return n + scroll_state_differs(&test_state, &ref_state);
}

static long sweep_scroll_section(void) {
    uint32_t routed_before = rm_scroll_blit_routed;
    long total = 0;
    scroll_init_playfield();
    for (int i = 0; i < N_SCROLL_CASES; i++) {
        long d = run_case_scroll((uint16_t)i, i & 1);       /* alternate the delta sign: both wrap branches */
        uint16_t logged = (uint16_t)(d > 0xffff ? 0xffff : d);
        scroll_case_diff[i] = logged;
        total += logged;
    }
    scroll_routed = (long)(rm_scroll_blit_routed - routed_before);
    return total;
}

/* Which sections this build ran (report word; the runner must not read a skipped grid as "clean"). */
#define SWEEP_GRID_OBJSHIFT2    1
#define SWEEP_GRID_OSH_PRESHIFT 2
#define SWEEP_GRID_OSH_SKEW     4
#define SWEEP_GRID_OSH_TABLE    8
#define SWEEP_GRID_BELOW        16
#define SWEEP_GRID_SCROLL       32
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
                    int rows_m1 = SWEEP_ROWS_M1[ri];
                    long d = run_case(SWEEP_WIDTH_IDX[wi], fx, SWEEP_COLUMNS[ci], rows_m1,
                                      sweep_grid_dst_off((int16_t)(uint16_t)rows_m1 + 1), &handled);
                    uint16_t logged = handled ? (uint16_t)(d > 0xffff ? 0xffff : d) : 0;
                    case_diff[idx++] = logged;
                    total += logged;
                    handled_count += handled ? 1 : 0;
                }
    *handled_out = handled_count;
    return total;
}

/* Sweep every case for all six sections. A handled (BASE) case must be byte-exact; a declined (CLIP)
 * case is the CPU hybrid (blitter drew nothing) — EXPECTED, not a mismatch. Only handled cases
 * contribute.
 *
 * A MUTATE build runs only the sections of the ROUTE its mutation breaks — the skew grid + the table for
 * mutations 1-6, the scroll section for 7-10: the knob touches nothing the other sections drive, so
 * re-sweeping them would only burn emulated cycles (the coverage check builds one PRG per mutation). The
 * bench is skipped with them — it would be timing a deliberately broken configuration. sweep_grids_run
 * tells the runner which sections the numbers describe, and run_ste_sweep.py knows which section each
 * mutation must make fail. */
long blitter_sweep_super(void) {
    long total = 0;
    /* Plain `if`s on the compile-time knobs, not #ifs: a mutate build then still COMPILES the sections it
     * skips, so a change that breaks them cannot hide behind the mutation flag. */
    int sweep_all = !RM_SKEW_MUTATED;                      /* no mutation: every section */
    int sweep_skew = !RM_SCROLL_MUTATED;                    /* no mutation, or one that breaks the skew route */
    int sweep_scroll = sweep_all || RM_SCROLL_MUTATED;      /* no mutation, or one that breaks this route */
    sweep_init_pairs();

    if (sweep_all) {
        total += sweep_objshift2_grid(&sweep_handled);
        sweep_grids_run |= SWEEP_GRID_OBJSHIFT2;
        total += sweep_objsh_grid(rm_blit_objshift_blitter, osh_case_diff, &osh_handled);
        sweep_grids_run |= SWEEP_GRID_OSH_PRESHIFT;
        total += sweep_below_screen_grid();
        sweep_grids_run |= SWEEP_GRID_BELOW;
    }
    if (sweep_skew) {
        total += sweep_objsh_grid(rm_blit_objshift_skew, skew_case_diff, &skew_handled);
        sweep_grids_run |= SWEEP_GRID_OSH_SKEW;
        total += sweep_table_section();
        sweep_grids_run |= SWEEP_GRID_OSH_TABLE;
    }
    if (sweep_scroll) {
        total += sweep_scroll_section();
        sweep_grids_run |= SWEEP_GRID_SCROLL;
    }

    if (sweep_all) sweep_bench();
    sweep_total = total;                                    /* combined: every section run must be 0 */
    return total;
}

/* Pack the per-case grid into a framebuffer for SCREEN.BIN: word0 = total case count (objshift2, then
 * objshift pre-shift, then objshift hardware-skew, then the table section, then the below-screen
 * section), word1 = total mismatch (every section run), then the concatenated per-case diff words.
 * run_ste_sweep.py parses it; the tail indices are mirrored there.
 *
 * The tail is SELF-DESCRIBING: besides the BASE-handled counts and the cost bench it carries the section
 * LAYOUT (per-section case counts), the count each section is expected to have drawn, which sections
 * this build ran, and whether the boot bind PLACED the routes' tables at all. Those let the runner locate
 * each section and prove it non-vacuous from the report itself instead of from Python literals that can
 * silently drift out of step with this file. */
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
#define SWEEP_TAIL_N_CASES_BELOW  20                        /* layout: the below-screen section's case count */
#define SWEEP_TAIL_HANDLED_BELOW  21                        /* below-screen cases the blitter paths drew */
#define SWEEP_TAIL_TABLES_BOUND   22                        /* 0 = the boot bind placed no tables (see below) */
#define SWEEP_TAIL_N_CASES_SCROLL 23                        /* layout: the road-scroll section's case count */
#define SWEEP_TAIL_ROUTED_SCROLL  24                        /* road-scroll cases the blitter route drew */
#define SWEEP_TAIL_WORDS          SWEEP_TAIL_ROUTED_SCROLL
/* The six per-case sections must not run into the tail words (they share one 32000-byte report). */
typedef char sweep_report_fits[(2 + N_CASES + 2 * N_OSH_CASES + N_TBL_CASES + N_BELOW_CASES
                                + N_SCROLL_CASES <= SWEEP_REPORT_WORDS - SWEEP_TAIL_WORDS) ? 1 : -1];

/* `tables_bound` is rm_blit_bind_all's return (game_main.c passes it straight through). When it is 0 the
 * routes' lookup tables were never placed — GAME_FORCE_NO_BLITTER, a machine with no blitter, or a TPA
 * too small — and every blitter path declines by design. Sweeping then would report a vacuous all-zero
 * grid that LOOKS like a pass, so nothing is swept and the report says so in its own tail word instead. */
const uint8_t *blitter_sweep(long *mismatch_out, int tables_bound) {
    if (tables_bound) Supexec(blitter_sweep_super);
    uint16_t *w = (uint16_t *)test_fb;
    for (int i = 0; i < SWEEP_REPORT_WORDS; i++) w[i] = 0;
    w[0] = (uint16_t)(N_CASES + 2 * N_OSH_CASES + N_TBL_CASES + N_BELOW_CASES + N_SCROLL_CASES);
    w[1] = (uint16_t)(sweep_total > 0xffff ? 0xffff : sweep_total);
    int at = 2;
    for (int i = 0; i < N_CASES; i++) w[at++] = case_diff[i];
    for (int i = 0; i < N_OSH_CASES; i++) w[at++] = osh_case_diff[i];
    for (int i = 0; i < N_OSH_CASES; i++) w[at++] = skew_case_diff[i];
    for (int i = 0; i < N_TBL_CASES; i++) w[at++] = tbl_case_diff[i];
    for (int i = 0; i < N_BELOW_CASES; i++) w[at++] = below_case_diff[i];
    for (int i = 0; i < N_SCROLL_CASES; i++) w[at++] = scroll_case_diff[i];
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
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_N_CASES_BELOW]  = (uint16_t)N_BELOW_CASES;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_HANDLED_BELOW]  = (uint16_t)below_handled;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_TABLES_BOUND]   = (uint16_t)(tables_bound ? 1 : 0);
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_N_CASES_SCROLL] = (uint16_t)N_SCROLL_CASES;
    w[SWEEP_REPORT_WORDS - SWEEP_TAIL_ROUTED_SCROLL]  = (uint16_t)scroll_routed;
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
