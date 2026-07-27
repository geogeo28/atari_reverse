/* blitter_scroll.c — the STE hardware-blitter route for the road fine-scroll rm_blit_road_scroll
 * (PERF30 C5, slice 1). The CPU reference (src/scroll.c) costs 12.06 ms of the gate frame — the third
 * biggest stage — and was the last big one still running on the 68000 on a blitter machine.
 *
 * It emits the SAME framebuffer bytes as the C reference, so every byte-compare pin still holds; this is
 * a perf swap, never a pixel change. SUPERVISOR ONLY (the register pokes hit 0xFFFF8Axx).
 *
 * ============================ THE RECIPE (BLIT_STE_SPEC §16) ============================
 * The reference does three things per frame. Two of them are pure rectangular moves the chip does far
 * better than a store loop; the third is a 20-row read-modify-write of 4 words, which stays on the CPU.
 *
 * A. TOP FILL — OBJ_ROAD_START_OFF bytes of the constant ROAD_TOP_FILL above the band. In the ST's
 *    interleaved framebuffer that long pattern is "every EVEN plane-word all ones, every ODD plane-word
 *    zero", so it is TWO source-less constant blits over the same 84x40-word grid, offset one word
 *    apart: LOP = ONE for the even words, LOP = ZERO for the odd ones. HOP = ONE and all-ones endmasks
 *    mean the chip needs neither a source nor a destination read — write-only bus cycles.
 *
 * B. MAIN COLUMN COPY — main_cols columns x ROAD_ROWS rows out of this frame's pre-rotated copy. Both
 *    pitches (SRC_ROW_STRIDE, SCREEN_ROW_BYTES) are constant across the rows, so the whole band is ONE
 *    blit (HOP = SRC, LOP = SRC), not one per row. When the scroll has wrapped (edge >= 1) a second blit
 *    of the same shape lays the wrapped tail down from column 0 of the same copy.
 *
 * C. SEAM — the 4-plane masked blend at the last main column (rm_scroll_seam_row, scroll_const.h). The
 *    blitter cannot compute it (the fraction is a shift of a DIFFERENT source word ORed under a mask),
 *    and at 20 rows x 4 words it is not worth a recipe: it stays on the CPU.
 *
 * ORDERING. C reads framebuffer words that B(main) writes, so the seam must run AFTER the main blit. The
 * wrap blit writes columns main_cols..main_cols+edge-1 and the seam writes column main_cols-1 — DISJOINT
 * — so the wrap blit may run either side of it, and it runs before, inside the same excursion. The top
 * fill is disjoint from the band (it stops at OBJ_ROAD_START_OFF, where the band begins) and so is order-
 * free. Net: [fill even, fill odd, main, wrap] in ONE Supexec, then the seam.
 *
 * BUS POLICY. These are screen-sized passes (the fill alone is 6,720 words), not the object blits'
 * tens-of-microseconds shapes, so the default is the SHARED-bus restart loop of BLIT_STE_SPEC §2 rather
 * than HOG — the chip hands the bus back every 64 words instead of freezing the 68000 for the whole
 * pass. BLIT_SCROLL_HOG=1 rebuilds it on HOG; that knob is the A/B that produced §16's measurement, and
 * it is kept so the choice stays reproducible.
 *
 * SUPEXEC. All 3-4 passes of one call share ONE excursion: they are consecutive with no user-mode work
 * between them, so paying four traps for one stage would be pure overhead. (This is NOT the deferred
 * "one excursion for the whole object pass" idea — that one spans user-mode dispatch work.)
 */
#include "blitter.h"
#include "screen.h"
#include "st.h"
#include "game.h"
#include "scroll_const.h"

/* ---- geometry of the two recipes, derived from the reference's own constants ------------------- */

/* ROAD_TOP_FILL is laid down every 4 bytes = one even plane-word + one odd plane-word. The two fill
 * blits walk that pair grid, so the whole recipe follows from the pattern being exactly ones-then-zeros;
 * a different pattern would need different LOPs, which this pins. */
#define SCROLL_FILL_PAIR_BYTES  4
#define SCROLL_FILL_X_COUNT     (SCREEN_ROW_BYTES / SCROLL_FILL_PAIR_BYTES)      /* 40 words per row */
#define SCROLL_FILL_ROWS        (OBJ_ROAD_START_OFF / SCREEN_ROW_BYTES)          /* 84 scanlines */
#define SCROLL_FILL_ODD_OFF     2                                                /* the odd word of a pair */
typedef char rm_scroll_fill_is_ones_then_zeros[(ROAD_TOP_FILL == 0xffff0000u) ? 1 : -1];
typedef char rm_scroll_fill_is_whole_rows[
    (SCROLL_FILL_ROWS * SCREEN_ROW_BYTES == OBJ_ROAD_START_OFF) ? 1 : -1];

#define SCROLL_WORDS_PER_COL    (ROAD_COL_BYTES / 2)                             /* 4 plane words */

/* Routed / declined call counts — the cadence tail's observable (game_main.c). */
uint32_t rm_scroll_blit_routed, rm_scroll_blit_declined;

/* Does the recipe serve this frame's geometry? The ONE thing it needs is a main-column count the CHIP can
 * express: the blitter reads x_count == 0 as 65,536 words, so a zero-width pass would run away over
 * memory with the bus held. rm_scroll_advance bounds main_cols to [1, ROAD_COLS] for every one of the 640
 * reachable hscroll_pos values — the sweep's scroll section walks all 640 and this has never declined —
 * so it is a live TRIPWIRE on that contract, not a family split like the object routes' clip hybrid, and
 * its counter reading 0 on every run is the expected result, not an unexercised branch.
 *
 * It is NOT a safe harbour: the only state that trips it is an out-of-range scroll position, and the C
 * reference it falls back to walks the same underflowed main_cols (its arithmetic is the original game's,
 * single-wrap and unbounded — unchanged here by design, since it is the byte-exact reference). So the
 * decline buys back exactly the CPU behaviour the ST has always had; what it prevents is handing that
 * state to the chip, where it would be a 65,536-word runaway instead of a bad blit. */
static int scroll_blit_serves(const ScrollGeometry *geo) {
    return geo->main_cols >= 1 && geo->main_cols <= ROAD_COLS;
}

/* Start the pass already poked, under the route's chosen bus policy (see the header's BUS POLICY note). */
static void scroll_blit_start(void) {
#if defined(BLIT_SCROLL_HOG) && BLIT_SCROLL_HOG
    blit_start_and_wait();
#else
    blit_start_and_wait_shared();
#endif
}

/* One constant fill pass over the pair grid above the band: no source, no destination read — with
 * HOP = ONE and all-ones endmasks the chip only writes. `lop` selects the word value (ONE / ZERO). */
static void scroll_fill_pass(uint8_t *dst, uint8_t lop) {
    BlitPass pass;
    pass.src_addr  = 0;                                     /* HOP = ONE: the chip never reads a source */
    pass.src_x_inc = 0;
    pass.src_y_inc = 0;
    pass.dst_addr  = (uint32_t)dst;
    pass.dst_x_inc = SCROLL_FILL_PAIR_BYTES;                /* the same plane-word of the next pair */
    pass.dst_y_inc = SCREEN_ROW_BYTES - (SCROLL_FILL_X_COUNT - 1) * SCROLL_FILL_PAIR_BYTES;
    pass.endmask1  = BLT_ENDMASK_ALL;
    pass.endmask2  = BLT_ENDMASK_ALL;
    pass.endmask3  = BLT_ENDMASK_ALL;
    pass.x_count   = SCROLL_FILL_X_COUNT;
    pass.y_count   = SCROLL_FILL_ROWS;
    pass.hop       = BLT_HOP_ONE;
    pass.lop       = lop;
    pass.skew_ctl  = 0;
    blit_poke(&pass);
    scroll_blit_start();
}

/* One band copy pass: `words` destination words per row for ROAD_ROWS rows, source pitch
 * SRC_ROW_STRIDE, destination pitch SCREEN_ROW_BYTES. Both walks are word-contiguous within a row, so
 * the per-row correction is just pitch - (words - 1) * 2. Never called with words == 0 (see the callers:
 * a zero-width wrap is SKIPPED, because x_count 0 means 65,536 to the chip). */
static void scroll_copy_pass(uint8_t *dst, const uint8_t *src, uint16_t words) {
    BlitPass pass;
#if RM_SKEW_MUTATE == RM_SKEW_MUT_SCROLL_XCOUNT
    uint16_t poked = (uint16_t)(words + 1);                 /* mutation: one dst word per row too wide */
#else
    uint16_t poked = words;
#endif
    pass.src_addr  = (uint32_t)src;
    pass.src_x_inc = 2;
    pass.src_y_inc = (int16_t)(SRC_ROW_STRIDE - 2 * (poked - 1));
    pass.dst_addr  = (uint32_t)dst;
    pass.dst_x_inc = 2;
    pass.dst_y_inc = (int16_t)(SCREEN_ROW_BYTES - 2 * (poked - 1));
    pass.endmask1  = BLT_ENDMASK_ALL;
    pass.endmask2  = BLT_ENDMASK_ALL;
    pass.endmask3  = BLT_ENDMASK_ALL;
    pass.x_count   = poked;
    pass.y_count   = ROAD_ROWS;
    pass.hop       = BLT_HOP_SRC;
    pass.lop       = BLT_LOP_SRC;
    pass.skew_ctl  = 0;                                     /* both ends are column-aligned: no skew */
    blit_poke(&pass);
    scroll_blit_start();
}

/* The CPU half: the wrap seam down the whole band. Skipped entirely when shift == 0, where every row's
 * blend is the identity by construction (rm_scroll_seam_row's note). */
static void scroll_seam_band(uint8_t *band, const uint8_t *raw, const ScrollGeometry *geo) {
    if (geo->edge < 0 || geo->shift == 0) return;
    uint8_t *seam = band + (geo->main_cols - 1) * ROAD_COL_BYTES;
    for (unsigned row = 0; row < ROAD_ROWS; row++)
        rm_scroll_seam_row(seam + row * SCREEN_ROW_BYTES, raw + row * SRC_ROW_STRIDE, geo->shift);
}

/* Draw one ALREADY-ADVANCED scroll frame with the blitter, or hand it to the C reference if the geometry
 * is outside the recipe's envelope. SUPERVISOR ONLY: the dispatch below reaches this through one
 * Supexec, and the sweep's scroll section calls it directly (it already runs inside one excursion), so
 * both pin the same code. */
void rm_blit_road_scroll_draw(const ScrollGeometry *geo, const uint8_t *shifted, Framebuffer *fb) {
    if (!scroll_blit_serves(geo)) {
        rm_scroll_blit_declined++;
        rm_scroll_draw(geo, shifted, fb);                   /* whatever the ST would have drawn — see above */
        return;
    }
    rm_scroll_blit_routed++;

    uint8_t *band = fb->px + OBJ_ROAD_START_OFF;
    const uint8_t *copy = rm_scroll_copy(shifted, geo->shift);

#if RM_SKEW_MUTATE == RM_SKEW_MUT_SCROLL_SEAM_1ST
    scroll_seam_band(band, shifted, geo);                   /* mutation: before the blit that overwrites it */
#endif
    scroll_fill_pass(fb->px, BLT_LOP_ONE);                  /* even plane-words: 0xFFFF */
#if RM_SKEW_MUTATE == RM_SKEW_MUT_SCROLL_FILL_LOP
    scroll_fill_pass(fb->px + SCROLL_FILL_ODD_OFF, BLT_LOP_ONE);    /* mutation: ones, not zeros */
#else
    scroll_fill_pass(fb->px + SCROLL_FILL_ODD_OFF, BLT_LOP_ZERO);   /* odd plane-words: 0x0000 */
#endif
    scroll_copy_pass(band, copy + geo->coarse, (uint16_t)(geo->main_cols * SCROLL_WORDS_PER_COL));
    if (geo->edge >= 1) {                                   /* edge 0 wraps no columns: no zero-width pass */
#if RM_SKEW_MUTATE != RM_SKEW_MUT_SCROLL_NOWRAP
        scroll_copy_pass(band + geo->main_cols * ROAD_COL_BYTES, copy,
                         (uint16_t)((unsigned)geo->edge * SCROLL_WORDS_PER_COL));
#endif
    }
#if RM_SKEW_MUTATE != RM_SKEW_MUT_SCROLL_SEAM_1ST
    scroll_seam_band(band, shifted, geo);                   /* reads what the main blit just wrote */
#endif
}

/* ---- runtime dispatch + the boot binding (src/frame.c's rm_blit_road_scroll seam) ----------------
 * The scalar head runs in USER mode — it is state mutation the route never changes — and only the draw
 * enters supervisor, as ONE excursion for the whole stage. */
static struct { ScrollGeometry geo; const uint8_t *shifted; Framebuffer *fb; } g_scroll;

static long scroll_draw_super(void) {
    rm_blit_road_scroll_draw(&g_scroll.geo, g_scroll.shifted, g_scroll.fb);
    return 1;
}

void rm_blit_road_scroll_dispatch(ScrollState *s, const uint8_t *shifted, Framebuffer *fb) {
    g_scroll.geo = rm_scroll_advance(s);                    /* once per call, exactly as the C route does */
    g_scroll.shifted = shifted;
    g_scroll.fb = fb;
    Supexec(scroll_draw_super);
}

/* The seam src/frame.c calls, bound ONCE at boot — the objshift2 pattern (BLIT_STE_SPEC §11). Defaults
 * to the C reference so it is safe before boot and costs a plain ST nothing but one indirection.
 *
 * Unlike the two object routes this one has NO lookup table, so it is bound on have_blitter ALONE: it
 * cannot be retired by a TPA too small to place a table (the 1 MB diet, §15), and rm_blit_bind_all binds
 * it before that placement can veto anything. A 1 MB STE that loses the object tables therefore still
 * keeps the scroll on the chip. */
void (*rm_blit_road_scroll_fn)(ScrollState *, const uint8_t *, Framebuffer *) = rm_blit_road_scroll;

void rm_blit_road_scroll_bind(int have_blitter) {
    rm_blit_road_scroll_fn = have_blitter ? rm_blit_road_scroll_dispatch : rm_blit_road_scroll;
}
