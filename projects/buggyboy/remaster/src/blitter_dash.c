/* blitter_dash.c — the STE hardware-blitter route for the HUD's phase-7 dashboard composite
 * (PERF30 C5, slice 2). The CPU reference (cell_dashboard, include/plane.h, driven by src/hud.c's
 * rm_hud_dashboard) is the single biggest thing left in draw_hud once the object routes and the road
 * scroll are on the chip.
 *
 * It emits the SAME framebuffer bytes as the C reference, so every byte-compare pin still holds; this is
 * a perf swap, never a pixel change. SUPERVISOR ONLY (the register pokes hit 0xFFFF8Axx).
 *
 * ============================ THE RECIPE (BLIT_STE_SPEC §17) ============================
 * The art is DASH_ROWS rows of DASH_GROUPS groups; each group is four source words {mask, ink_a, ink_b,
 * ink_c} and four destination words, one per plane:
 *
 *     plane 0 = (dst & mask) | ink_a      plane 2 = (dst & mask) | ink_b
 *     plane 1 = (dst & mask) | ink_b      plane 3 = (dst & mask) | ink_c
 *
 * Per plane that is the classic two-pass COOKIE-CUT — LOP = AND from the mask word, then LOP = OR from
 * that plane's ink word — so the whole composite is EIGHT passes, four AND then four OR. Plane p owns
 * byte offset 2p of every group, so the four planes write DISJOINT destination words: no plane can
 * observe another's write, only AND-before-OR *within* a plane is ordered, and the regrouping into two
 * LOP groups is byte-identical (the src/blitter_skew.c argument, same shape).
 *
 * NO MATERIALISED STREAM, NO TABLE, NO RAM. The chip reads the LIVE art in place, straight out of the
 * graphics arena, because ARENA_ROW_STRIDE == SCREEN_ROW_BYTES (pinned in dash_const.h): source and
 * destination walk with the SAME x-step (one group) and the SAME per-row correction (DASH_BLIT_Y_INC).
 * That matters beyond tidiness — the per-leg mini-map init_leg_dash builds is rewritten between legs and
 * one word of it is mutated MID-LEG by probe_collision, so anything precomputed would need an
 * invalidation signal (and the last attempt to precompute this blit shipped the mini-map black-
 * background bug — PERF30's dash_pristine revert). Reading in place cannot go stale.
 *
 * WHAT THE CHIP CANNOT SHORTEN. plane 1 and plane 2 take the same ink word, so "blit plane 1, then copy
 * its framebuffer column to plane 2" looks like a 7-pass refinement — it is WRONG. The results are
 * (bg1 & mask) | ink_b and (bg2 & mask) | ink_b, equal only where mask == 0 or bg1 == bg2, and the real
 * background under the dashboard rows is the road top fill, whose plane-1 word is 0x0000 and plane-2
 * word is 0xFFFF (ROAD_TOP_FILL = 0xffff0000). The idea is kept as sweep mutation
 * RM_SKEW_MUT_DASH_P2COPY so the disproof is a measurement, not an argument.
 *
 * BUS POLICY. Eight screen-width passes over 40 rows is the road-scroll trade, not the object blits'
 * tens-of-microseconds shapes, so the default is the SHARED-bus restart loop of BLIT_STE_SPEC §2 rather
 * than HOG — the chip hands the bus back every 64 words instead of freezing the 68000 for the whole
 * pass. BLIT_DASH_HOG=1 rebuilds it on HOG; that knob is the A/B behind §17's measurement, and it is
 * kept so the choice stays reproducible.
 *
 * SUPEXEC. All eight passes of one call share ONE excursion: they are consecutive with no user-mode work
 * between them, so paying eight traps for one stage would be pure overhead.
 */
#include "blitter.h"
#include "dash_const.h"
#include "screen.h"

/* ---- geometry, derived from the reference's own constants (dash_const.h) ------------------------ */

/* The whole composite must land inside the visible screen — it is a HUD overlay, not a clipped draw, so
 * unlike the object routes there is no below-screen family to serve. */
typedef char rm_dash_block_is_on_screen[
    (DASHBOARD_DST + (DASH_ROWS - 1) * SCREEN_ROW_BYTES + DASH_GROUPS * DASH_GROUP_BYTES
     <= SCREEN_BYTES) ? 1 : -1];

/* Source word offsets within a group. The mask feeds every plane's AND pass; the ink words feed the OR
 * passes as {ink_a, ink_b, ink_b, ink_c} — the middle source word drives TWO planes, which is the one
 * thing about this recipe that is not a straight per-plane mapping. */
#define DASH_SRC_MASK_OFF   0
#define DASH_SRC_INK_SHARED_OFF 4                           /* the ink word TWO planes read (see below) */
static const uint8_t DASH_SRC_INK_OFF[SCREEN_PLANES] =
    {2, DASH_SRC_INK_SHARED_OFF, DASH_SRC_INK_SHARED_OFF, 6};
/* The plane pair that shares that word — i.e. the plane the disproved "7-pass refinement" would COPY
 * rather than blit, and the one it would copy FROM. The sharing is spelled structurally above (one
 * macro, twice) so a re-mapped art format cannot leave these two names pointing at planes whose ink
 * words differ, which would make mutation 14 fail for a reason other than the one it exists to prove. */
#define DASH_P2COPY_PLANE      2
#define DASH_P2COPY_SRC_PLANE  1

/* Routed / declined call counts — the cadence tail's observable (game_main.c). */
uint32_t rm_dash_blit_routed, rm_dash_blit_declined;

/* Does the recipe serve this call? Its geometry is entirely COMPILE-TIME (fixed destination, fixed rows,
 * fixed groups, fixed pitches — the asserts above), so the only runtime input is the pair of base
 * addresses, and the only thing the chip cannot express about them is an ODD one: src_addr/dst_addr
 * ignore bit 0, so an odd art pointer would blit from base-1 while the CPU reference reads the words the
 * caller meant. That is a TRIPWIRE on the chip contract, not a family split.
 *
 * It is NOT a safe harbour: the C reference it declines to would take an ADDRESS ERROR on the same odd
 * pointer (be16/wr16 are raw word accesses on the 68000). The decline buys back exactly the behaviour a
 * plain ST has always had; what it prevents is handing that state to the chip, where it is a silently
 * wrong blit rather than a loud one.
 *
 * TWO honest limits, stated rather than papered over (STATUS.md carries them too):
 *  - This branch is UNEXERCISED, not merely quiet. The arena and both screen buffers are word-aligned by
 *    construction, so no build can reach the state that trips it, and the sweep cannot seed one without
 *    deliberately mis-aligning its own framebuffers — which would decline all 16 cases and read as a
 *    route regression. `rm_dash_blit_declined` is structurally 0. src/blitter_scroll.c's x_count
 *    tripwire has the same shape; this is the second instance, and neither is pinned.
 *  - Odd-ness is not the ONLY property the chip cannot express: the address registers hold 24 bits, so a
 *    source above 16 MB (a Falcon running from TT-RAM — blitter_present() accepts Falcon) would be
 *    truncated rather than declined. That is true of all four routes, predates this one and is not fixed
 *    here; it is named so this tripwire is not read as covering more than it does. */
static int dash_blit_serves(const uint8_t *px, const uint8_t *gfx) {
    return ((((uint32_t)px | (uint32_t)gfx) & 1u) == 0);
}

/* Start the pass already poked, under the route's chosen bus policy (see the header's BUS POLICY note). */
static void dash_blit_start(void) {
#if defined(BLIT_DASH_HOG) && BLIT_DASH_HOG
    blit_start_and_wait();
#else
    blit_start_and_wait_shared();
#endif
}

/* The registers every pass of this route shares, poked ONCE per call (the BLIT_STE_SPEC §14 batching
 * shape). x_count is safe to hoist because the chip reloads it from an internal latch at every line and
 * leaves the register holding its initial value; the endmasks are all-ones because every pass writes
 * whole destination words. That leaves 10 + 2 (the two LOP writes) + 8 x 3 = 36 register writes per
 * composite, where blit_run's 17 per pass would be 136. */
static void dash_blit_begin(void) {
    BLT_W(BLT_SRC_X_INC) = DASH_GROUP_BYTES;                /* next group, same plane */
    BLT_W(BLT_DST_X_INC) = DASH_GROUP_BYTES;
#if RM_SKEW_MUTATE == RM_SKEW_MUT_DASH_YINC
    BLT_W(BLT_SRC_Y_INC) = DASH_BLIT_Y_INC - DASH_GROUP_BYTES;   /* mutation: one group short per row */
    BLT_W(BLT_DST_Y_INC) = DASH_BLIT_Y_INC - DASH_GROUP_BYTES;
#else
    BLT_W(BLT_SRC_Y_INC) = DASH_BLIT_Y_INC;                 /* one arena scanline on from the last group */
    BLT_W(BLT_DST_Y_INC) = DASH_BLIT_Y_INC;                 /* ...the SAME step: the two pitches are equal */
#endif
#if RM_SKEW_MUTATE == RM_SKEW_MUT_DASH_XCOUNT
    BLT_W(BLT_X_COUNT)   = DASH_GROUPS + 1;                 /* mutation: one group per row too wide */
#else
    BLT_W(BLT_X_COUNT)   = DASH_GROUPS;                     /* reloaded per line from the chip's latch */
#endif
    BLT_W(BLT_ENDMASK1)  = BLT_ENDMASK_ALL;
    BLT_W(BLT_ENDMASK2)  = BLT_ENDMASK_ALL;
    BLT_W(BLT_ENDMASK3)  = BLT_ENDMASK_ALL;
    BLT_B(BLT_HOP)       = BLT_HOP_SRC;
    BLT_B(BLT_SKEW)      = 0;                               /* every column is word-aligned: no skew */
    /* No halftone seed: HOP is SRC for every pass here, so the halftone RAM is never read. */
}

/* One pass: only the registers the chip consumes while it runs, then start it. `src` is the group word
 * this pass reads (mask or ink), `dst_plane` the plane's word in the first destination group. */
static void dash_blit_fire(const uint8_t *src, uint8_t *dst_plane) {
    BLT_L(BLT_SRC_ADDR) = (uint32_t)src;
    BLT_L(BLT_DST_ADDR) = (uint32_t)dst_plane;
    BLT_W(BLT_Y_COUNT)  = DASH_ROWS;
    dash_blit_start();
}

/* Composite the dashboard art at `gfx` onto the framebuffer `px` with the blitter, or hand it to the C
 * reference if the addresses are outside the recipe's envelope. SUPERVISOR ONLY: the dispatch below
 * reaches this through one Supexec, and the sweep's dashboard section calls it directly (it already runs
 * inside one excursion), so both pin the same code. */
void rm_blit_hud_dashboard_draw(uint8_t *px, const uint8_t *gfx) {
    if (!dash_blit_serves(px, gfx)) {
        rm_dash_blit_declined++;
        rm_hud_dashboard(px, gfx);                          /* whatever the ST would have drawn — see above */
        return;
    }
    rm_dash_blit_routed++;

    uint8_t *dst = px + DASHBOARD_DST;
    dash_blit_begin();

    /* ALL FOUR mask passes first, then the ink passes — not AND/OR interleaved per plane — so one LOP
     * write covers each group of four (the disjoint-planes argument in the header). */
#if RM_SKEW_MUTATE == RM_SKEW_MUT_DASH_LOP_SWAP
    BLT_B(BLT_LOP) = BLT_LOP_OR;                            /* mutation: the cookie-cut's two LOPs swapped */
#else
    BLT_B(BLT_LOP) = BLT_LOP_AND;
#endif
    for (int p = 0; p < SCREEN_PLANES; p++)
        dash_blit_fire(gfx + DASH_SRC_MASK_OFF, dst + 2 * p);

#if RM_SKEW_MUTATE == RM_SKEW_MUT_DASH_LOP_SWAP
    BLT_B(BLT_LOP) = BLT_LOP_AND;
#else
    BLT_B(BLT_LOP) = BLT_LOP_OR;
#endif
    for (int p = 0; p < SCREEN_PLANES; p++) {
#if RM_SKEW_MUTATE == RM_SKEW_MUT_DASH_P2COPY
        if (p == DASH_P2COPY_PLANE) continue;               /* mutation: the "7-pass refinement" below */
#endif
        dash_blit_fire(gfx + DASH_SRC_INK_OFF[p], dst + 2 * p);
    }

#if RM_SKEW_MUTATE == RM_SKEW_MUT_DASH_P2COPY
    /* The disproved refinement: plane 2 takes the same ink word as plane 1, so copy plane 1's finished
     * framebuffer column instead of blitting the pair. Correct only where the mask is 0 or the two
     * planes' background words agree — see the header. */
    BLT_B(BLT_LOP) = BLT_LOP_SRC;
    dash_blit_fire(dst + 2 * DASH_P2COPY_SRC_PLANE, dst + 2 * DASH_P2COPY_PLANE);
#endif
}

/* ---- runtime dispatch + the boot binding (src/hud.c's RM_BLIT_HUD_DASHBOARD seam) ---------------- */
static struct { uint8_t *px; const uint8_t *gfx; } g_dash;

static long dash_draw_super(void) {
    rm_blit_hud_dashboard_draw(g_dash.px, g_dash.gfx);
    return 1;
}

void rm_blit_hud_dashboard_dispatch(uint8_t *px, const uint8_t *gfx) {
    g_dash.px = px;
    g_dash.gfx = gfx;
    Supexec(dash_draw_super);
}

/* The seam src/hud.c calls, bound ONCE at boot — the objshift2 pattern (BLIT_STE_SPEC §11). Defaults to
 * the C reference so it is safe before boot and costs a plain ST nothing but one indirection.
 *
 * Like the road-scroll route (and unlike the two object routes) this one has NO lookup table, so it is
 * bound on have_blitter ALONE: it cannot be retired by a TPA too small to place a table (the 1 MB diet,
 * §15), and rm_blit_bind_all binds it before that placement can veto anything. */
void (*rm_blit_hud_dashboard_fn)(uint8_t *, const uint8_t *) = rm_hud_dashboard;

void rm_blit_hud_dashboard_bind(int have_blitter) {
    rm_blit_hud_dashboard_fn = have_blitter ? rm_blit_hud_dashboard_dispatch : rm_hud_dashboard;
}
