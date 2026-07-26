/* reach_probe.c — MEASUREMENT-ONLY instrumentation for the 1 MB memory-diet campaign (slice 1).
 *
 * SCREEN_OVERDRAW (render/atari/game_main.c) gives each of the two draw buffers a scratch tail because
 * clipped roadside-object draws can write past the visible 32000 bytes. This probe is what MEASURED
 * that reach — the number the tail is now sized from (slice 1: the three fine-x engines never left the
 * visible screen at all, deepest write 31,039, and a whole composed frame reached 8 bytes past it, so
 * the "~102 KB" guess behind the old 0x20000 tail became a measured 0x1000). It also splits the reach
 * into "the whole destination lies below the visible screen" (dispatch-cullable — pure waste, no pin
 * can see it) versus "straddles the bottom edge" (a real partial clip that needs a tail), and can CULL
 * the former so the visible-byte equality of the cull can be pre-proved against recreate.
 *
 * Compiled ONLY into build/libremaster_probe.so (-DRM_REACH_PROBE) by tools/reach_census.py. It is in
 * tools/, not src/, precisely so no build's src wildcard can pick it up: it is never part of
 * libremaster.so, bench.elf, or the shipped .PRG. Its two hooks in src/blit.c and src/object_list.c
 * are both #ifdef RM_REACH_PROBE and compile to nothing everywhere else.
 *
 * All three fine-x engines walk their destination cursor UP one scanline per row (row 0 is the
 * DEEPEST row — see the constant-step folds in blit.c), so a blit's topmost row starts at
 * dst_off - (rows-1)*SCREEN_ROW_BYTES. That is the cull predicate's input.
 */
#include <stdint.h>
#include <string.h>

#include "screen.h"

#define RM_REACH_MAX_RECS 32768

/* Engine tags (the three fine-x leaves the roadside-object dispatcher feeds). */
#define RM_REACH_OBJSPRITE 0
#define RM_REACH_OBJSHIFT  1
#define RM_REACH_OBJSHIFT2 2

typedef struct {
    int32_t engine;    /* RM_REACH_* above */
    int32_t pass;      /* rm_draw_object_list invocation index within this frame (0,1,2) */
    int32_t dst_off;   /* row-0 (deepest) destination byte offset, as the dispatcher computed it */
    int32_t rows;      /* rows the engine will draw (<=0 means the row loop never runs) */
    int32_t min_off;   /* lowest framebuffer byte offset actually written (INT32_MAX if none) */
    int32_t max_off;   /* highest framebuffer byte offset actually written (INT32_MIN if none) */
    int32_t cullable;  /* 1 if the whole destination lies at/below the cull threshold */
    int32_t culled;    /* 1 if this probe skipped the draw because it was cullable and culling is on */
    int32_t neg;       /* RM_REACH_NEG_* — how negative this blit's first destination cursor was */
    int32_t x;         /* the fine-x the dispatcher passed (context for a `neg` record) */
} RmReachRec;

/* `neg` codes. A blit's first destination cursor is `dst_off + aligned_col(x)`, which the dispatcher
 * lets go NEGATIVE for an object clipped off the left edge at the very top of the screen. */
#define RM_REACH_NEG_NONE    0        /* the cursor started inside the buffer */
#define RM_REACH_NEG_BIASED  1        /* negative, but within RM_REACH_DST_BIAS — measured faithfully */
#define RM_REACH_NEG_ASSERT  2        /* blit.c's non-wrap invariant tripped (see rm_reach_assert) */
#define RM_REACH_NEG_SKIPPED 3        /* more negative than the bias: the draw was SKIPPED, not measured */

static RmReachRec g_recs[RM_REACH_MAX_RECS];
static int32_t g_n;
static int32_t g_overflow;
static RmReachRec *g_cur;             /* the record the running blit writes into (0 once records overflow) */
static const uint8_t *g_base;         /* fb->px — offsets are relative to this */
static int32_t g_cull;                /* 1 = actually skip cullable draws */
static int32_t g_cull_thresh;         /* a blit is cullable when its TOP row starts at/after this */
static int32_t g_pass;
static int32_t g_neg_total;
static int32_t g_neg_skipped;

/* On the 32-bit target a negative first cursor wraps correctly (the cursor is walked back into the
 * buffer before the first write); on a 64-bit host `dst + (uint32_t)negative` is a ~4 GB forward walk,
 * which is what blit.c's RM_HOST_ASSERT exists to catch. To MEASURE such a blit instead of aborting on
 * it, call the engine with the destination base biased down and the offset biased up by the same
 * constant — algebraically identical for the engine, and the recorded offsets stay relative to the real
 * base because rm_reach_note subtracts g_base. Requires the caller's buffer to have this much head room.
 *
 * A cursor MORE negative than the bias would walk off the front of that head room, so the shim SKIPS
 * that draw and records it as RM_REACH_NEG_SKIPPED (counted in rm_reach_neg_skipped). The frame's pixels
 * are then unfaithful — which is fine here and nowhere else: this is a measurement build whose output is
 * a census, never a compared framebuffer, and a run that segfaulted would measure nothing at all. The
 * driver reports the count so a nonzero one is visible rather than silently under-measuring. */
#define RM_REACH_DST_BIAS 4096

/* ---- the frame/pass/write hooks -------------------------------------------------------------- */

void rm_reach_frame_begin(const uint8_t *fb_px, int cull, int32_t cull_thresh) {
    g_n = 0;
    g_overflow = 0;
    g_cur = 0;
    g_pass = -1;
    g_base = fb_px;
    g_cull = cull;
    g_cull_thresh = cull_thresh;
    g_neg_total = 0;
    g_neg_skipped = 0;
}

void rm_reach_pass_begin(void) { g_pass++; }

/* Called from every destination write in src/blit.c (the wr16/wr32 shim there). */
void rm_reach_note(const void *p, unsigned n) {
    if (!g_cur) return;
    int32_t lo = (int32_t)((const uint8_t *)p - g_base);
    int32_t hi = lo + (int32_t)n - 1;
    if (lo < g_cur->min_off) g_cur->min_off = lo;
    if (hi > g_cur->max_off) g_cur->max_off = hi;
}

/* Called from src/blit.c's RM_HOST_ASSERT on the measurement build. With the bias above in force it
 * should never trip; a nonzero count means a blit reached more than RM_REACH_DST_BIAS below the
 * framebuffer base and the census under-measured it. */
void rm_reach_assert(int ok) {
    if (ok) return;
    g_neg_total++;
    if (g_cur) g_cur->neg = RM_REACH_NEG_ASSERT;
}

int32_t rm_reach_neg_total(void)   { return g_neg_total; }
int32_t rm_reach_neg_skipped(void) { return g_neg_skipped; }
int32_t rm_reach_count(void)    { return g_n; }
int32_t rm_reach_overflow(void) { return g_overflow; }
int32_t rm_reach_rec_bytes(void) { return (int32_t)sizeof(RmReachRec); }
const RmReachRec *rm_reach_recs(void) { return g_recs; }

/* Open a record for one blit; returns 1 when the caller must SKIP the draw — because culling is on and
 * the draw is cullable, or because its first cursor is further below the buffer than the bias covers
 * (see RM_REACH_DST_BIAS). Owns EVERY field of the record, so the wrappers never touch g_cur — which is
 * null once the record array overflows, and was a null dereference away from ending the run. */
static int reach_blit_begin(int engine, uint32_t dst_off, uint16_t x, uint16_t rows_m1) {
    int32_t rows = (int32_t)(int16_t)rows_m1 + 1;
    int32_t deepest = (int32_t)dst_off;
    int32_t top = rows > 0 ? deepest - (rows - 1) * SCREEN_ROW_BYTES : deepest;
    int cullable = rows > 0 && top >= g_cull_thresh;
    /* aligned_col mirrors blit.c's objsh_aligned_col: ((int16_t)x >> 1) & COL_ALIGN. */
    int32_t first = deepest + (int32_t)(int16_t)(uint16_t)(((int16_t)x >> 1) & (int16_t)0xfff8);
    int neg = first >= 0 ? RM_REACH_NEG_NONE
                         : (first < -RM_REACH_DST_BIAS ? RM_REACH_NEG_SKIPPED : RM_REACH_NEG_BIASED);
    int culled = cullable && g_cull;
    int skip = culled || neg == RM_REACH_NEG_SKIPPED;
    if (neg == RM_REACH_NEG_SKIPPED) g_neg_skipped++;

    if (g_n >= RM_REACH_MAX_RECS) { g_overflow++; g_cur = 0; return skip; }
    g_cur = &g_recs[g_n++];
    g_cur->engine = engine;
    g_cur->pass = g_pass;
    g_cur->dst_off = deepest;
    g_cur->rows = rows;
    g_cur->min_off = INT32_MAX;
    g_cur->max_off = INT32_MIN;
    g_cur->cullable = cullable;
    g_cur->culled = culled;
    g_cur->neg = neg;
    g_cur->x = x;
    return skip;
}

static void reach_blit_end(void) { g_cur = 0; }

/* ---- the three leaf wrappers object_list.c is redirected to -----------------------------------
 * Signatures mirror include/game.h; the real engines keep their names (this TU does not shadow them). */

void rm_blit_objshift(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                      uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                      const uint8_t *color_pairs, int base_cells);
void rm_blit_objshift2(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                       uint16_t x, uint16_t rows_m1, int width_idx);
void rm_objsprite(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                  uint16_t x, uint16_t rows_m1, int width_idx);

void rm_probe_objshift(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                       uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                       const uint8_t *color_pairs, int base_cells) {
    if (reach_blit_begin(RM_REACH_OBJSHIFT, dst_off, x, rows_m1)) return;
    rm_blit_objshift(dst - RM_REACH_DST_BIAS, dst_off + RM_REACH_DST_BIAS, src, src_off, x, color,
                     rows_m1, stride, color_pairs, base_cells);
    reach_blit_end();
}

void rm_probe_objshift2(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                        uint16_t x, uint16_t rows_m1, int width_idx) {
    if (reach_blit_begin(RM_REACH_OBJSHIFT2, dst_off, x, rows_m1)) return;
    rm_blit_objshift2(dst - RM_REACH_DST_BIAS, dst_off + RM_REACH_DST_BIAS, src, src_off, x,
                      rows_m1, width_idx);
    reach_blit_end();
}

void rm_probe_objsprite(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                        uint16_t x, uint16_t rows_m1, int width_idx) {
    if (reach_blit_begin(RM_REACH_OBJSPRITE, dst_off, x, rows_m1)) return;
    rm_objsprite(dst - RM_REACH_DST_BIAS, dst_off + RM_REACH_DST_BIAS, src, src_off, x, rows_m1,
                 width_idx);
    reach_blit_end();
}
