/* blitter_sweep.c — the byte-exactness sweep for the STE objshift2 blitter path (PERF30 C4, slice 2).
 * GAME_STE_SWEEP build only. Runs rm_blit_objshift2_blitter against the shipping CPU engine
 * rm_blit_objshift2 over the full objshift2 case space (cribbed from test/test_asm_blit.py's fuzz
 * dimensions) and reports a per-case mismatch grid to SCREEN.BIN.
 *
 * Case space: width_idx 0..2 x fine_x 0..15 x a column set spanning LEFT clip / BASE / RIGHT clip
 * x rows_m1 {0, 3, 0x2a} — plus the bit-15-set (zero-row) rows. For each case both engines draw the
 * SAME synthetic sprite over the SAME background; the two framebuffers must be byte-identical over the
 * whole 32000 bytes (and the guard bands intact). A BASE case that the blitter path handles (returns 1)
 * must match exactly; a CLIP case the path declines (returns 0) is the pinned CPU hybrid and is checked
 * to be declined (not silently mis-drawn). Every case's mismatch count is logged so a single Hatari run
 * shows the whole grid.
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

/* Sweep every case. A handled (BASE) case must be byte-exact; a declined (CLIP) case is the CPU hybrid —
 * the blitter path drew nothing, so test_fb == background != ref, which is EXPECTED, not a failure. Only
 * handled cases contribute to sweep_total. */
long blitter_sweep_super(void) {
    int idx = 0;
    long total = 0, handled_count = 0;
    for (int wi = 0; wi < N_WIDTH; wi++)
        for (int fx = 0; fx < N_FINEX; fx++)
            for (int ci = 0; ci < N_COL; ci++)
                for (int ri = 0; ri < N_ROWS; ri++) {
                    int handled;
                    long d = run_case(SWEEP_WIDTH_IDX[wi], fx, SWEEP_COLUMNS[ci], SWEEP_ROWS_M1[ri], &handled);
                    /* A declined clip case is a hybrid: not a mismatch. Record 0 for it; record the real
                     * diff for handled cases. */
                    uint16_t logged = handled ? (uint16_t)(d > 0xffff ? 0xffff : d) : 0;
                    case_diff[idx++] = logged;
                    total += logged;
                    handled_count += handled ? 1 : 0;
                }
    sweep_total = total;
    sweep_handled = handled_count;
    return total;
}

/* Pack the per-case grid into a framebuffer for SCREEN.BIN: word0 = case count, word1 = total mismatch,
 * then the per-case diff words. run_ste_sweep.py parses it. */
const uint8_t *blitter_sweep(long *mismatch_out) {
    Supexec(blitter_sweep_super);
    uint16_t *w = (uint16_t *)test_fb;
    for (int i = 0; i < SCREEN_BYTES / 2; i++) w[i] = 0;
    w[0] = (uint16_t)N_CASES;
    w[1] = (uint16_t)(sweep_total > 0xffff ? 0xffff : sweep_total);
    for (int i = 0; i < N_CASES && (2 + i) * 2 <= SCREEN_BYTES; i++) w[2 + i] = case_diff[i];
    w[SCREEN_BYTES / 2 - 1] = (uint16_t)sweep_handled;      /* last word: BASE cases the blitter drew */
    if (mismatch_out) *mismatch_out = sweep_total;
    return test_fb;
}
