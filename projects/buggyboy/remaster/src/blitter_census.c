/* blitter_census.c — GAME_STE_CENSUS instrumentation (PERF30 C4 slice 5). Counts the DISTINCT
 * materialise-key tuples the object lists actually issue over a real drive, per fine-x engine, so the
 * boot-pre-shift-table decision is made on measured data, not assumption. The key is exactly the
 * blitter cache key sans the (constant) arena.gfx base: what a boot table would have to enumerate.
 * The colour engine is counted under FOUR progressively coarser keys, because what a table must
 * enumerate depends on the blit scheme (see the CENSUS_SET block below).
 *
 * object_list.c routes RM_BLIT_OBJSHIFT{,2} here under -DGAME_STE_CENSUS; each wrapper records the tuple
 * then calls the CPU reference (so pixels are unaffected and every call — BASE and CLIP — is counted).
 * A large open-addressed set counts distinct insertions; game_main's census_dump writes the tallies to
 * SCREEN.BIN for run_ste_census.py. Compiled only in the census build.
 */
#include "game.h"
#include "blit_const.h"
#include "st.h"

#define CENSUS_SLOTS_FULL    0x10000                       /* 65536 slots for the two full-key engine sets */
#define CENSUS_SLOTS_REDUCED 0x4000                        /* 16384 slots for the reduced colour keys: a
                                                            * reduced key that saturates 16 K is a NO-GO
                                                            * anyway, so the cap costs no verdict. */

typedef struct {
    uint32_t *key;                                         /* stored tuple hash (0 == empty; see census_add) */
    uint32_t mask;                                         /* slots - 1 (slot count is a power of two) */
    uint32_t distinct;                                     /* distinct base-family tuples seen */
    uint32_t calls;                                        /* total calls (base + clip) */
    uint32_t base_calls;                                   /* base-family calls (what a table would serve) */
    uint32_t saturated;                                    /* set ran out of slots */
} Census;

/* Declare a Census plus its backing arrays. `slots` must be a power of two. */
#define CENSUS_SET(name, slots)                                                                            \
    static uint32_t name##_key[slots];                                                                     \
    static Census name = { name##_key, (slots) - 1u, 0, 0, 0, 0 }

CENSUS_SET(census_objsh2_set, CENSUS_SLOTS_FULL);
CENSUS_SET(census_objsh_set, CENSUS_SLOTS_FULL);

/* Reduced colour-engine keys — the hardware-SKEW hypothesis (BLIT_STE_SPEC §10's "only remaining lever"):
 * skewing at blit time from UNSHIFTED bitmaps drops fine_x from the materialised content; the per-plane
 * colour fill is a binary select (fill_p in {0, 0xFFFF}), so `color` drops out too; and materialising at
 * max rows per sprite and blitting fewer via y_count drops rows_m1. `sprite` is the resulting static-table
 * key. Each is a strict subset of the one above it, so the four hashes chain (see the wrapper). */
CENSUS_SET(census_objsh_noshift_set, CENSUS_SLOTS_REDUCED);         /* full key minus fine_x */
CENSUS_SET(census_objsh_nocolor_set, CENSUS_SLOTS_REDUCED);         /* ... minus color */
CENSUS_SET(census_objsh_sprite_set, CENSUS_SLOTS_REDUCED);          /* ... minus rows_m1 */

/* Insert a tuple hash; bump distinct on first sight. Linear probe. Hash value 0 is RESERVED as the
 * empty-slot marker, which is why both call sites insert `h ? h : 1` — so a zero key means "empty". */
static void census_add(Census *cs, uint32_t h) {
    if (cs->saturated) return;                             /* a full set costs ~half a table of probes per call */
    uint32_t slots = cs->mask + 1u;
    uint32_t i = h & cs->mask;
    for (uint32_t n = 0; n < slots; n++) {
        if (cs->key[i] == 0) {
            if (cs->distinct >= slots - 1) { cs->saturated = 1; return; }
            cs->key[i] = h; cs->distinct++;
            return;
        }
        if (cs->key[i] == h) return;                       /* already seen */
        i = (i + 1) & cs->mask;
    }
    cs->saturated = 1;
}

/* The materialise-family test (mirrors the blitter engines): is this a BASE-family draw a table serves? */
static int objsh2_is_base(uint16_t x, uint16_t rows_m1, int width_idx) {
    if ((int16_t)rows_m1 + 1 <= 0) return 0;               /* zero rows: no draw, not a table entry */
    int16_t col = (int16_t)((int16_t)((int16_t)(uint16_t)x >> 1) & (int16_t)COL_ALIGN);
    int16_t ceil = (int16_t)(OBJSH2_RIGHT_BOUND + OBJSH2_LADDER_STEP * width_idx);
    return !(col < 0 || (int16_t)(col - ceil) >= 0);
}
static int objsh_is_base(uint16_t x, uint16_t rows_m1, int base_cells) {
    if ((int16_t)rows_m1 + 1 <= 0) return 0;
    int16_t col = (int16_t)((int16_t)((int16_t)(uint16_t)x >> 1) & (int16_t)COL_ALIGN);
    int16_t ceil = (int16_t)(OBJSH_RIGHT_BOUND - OBJSH_CELL_BYTES * (base_cells - 1));
    return !(col < 0 || (int16_t)(col - ceil) >= 0);
}

#define CENSUS_SEED 0x9e3779b9u
static uint32_t mix(uint32_t h, uint32_t v) { return (h ^ v) * 2654435761u; }

/* The colour engine's four keys, coarsest last; the wrapper walks them via `objsh_key_sets`
 * (the report's block order is declared separately, by `report_sets`). */
enum { OBJSH_KEY_FULL, OBJSH_KEY_NOSHIFT, OBJSH_KEY_NOCOLOR, OBJSH_KEY_SPRITE, OBJSH_KEY_COUNT };
static Census *const objsh_key_sets[OBJSH_KEY_COUNT] = {
    &census_objsh_set, &census_objsh_noshift_set, &census_objsh_nocolor_set, &census_objsh_sprite_set
};

/* ---- census wrappers: record the tuple, then draw with the CPU reference ----
 * NOTE: the colour wrapper below is a THIRD enumeration of the objshift cache key, alongside
 * objsh_cache_hit / objsh_cache_store in src/blitter_objshift.c. A field added to that key must be
 * added here too, or the census silently under-counts distinct tuples. */
void rm_blit_objshift2_census(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                              uint16_t x, uint16_t rows_m1, int width_idx) {
    census_objsh2_set.calls++;
    if (objsh2_is_base(x, rows_m1, width_idx)) {
        census_objsh2_set.base_calls++;
        uint32_t h = mix(mix(mix(mix(CENSUS_SEED, src_off), x & OBJSH_NIBBLE), (uint32_t)width_idx), rows_m1);
        census_add(&census_objsh2_set, h ? h : 1);
    }
    RM_BLIT_OBJSHIFT2(dst, dst_off, src, src_off, x, rows_m1, width_idx);
}

void rm_blit_objshift_census(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                             uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                             const uint8_t *color_pairs, int base_cells) {
    /* The four keys share ONE call stream (they differ only in which fields the hash covers), so the call
     * counters live on the full-key set alone; blitter_census_report copies them into the reduced blocks. */
    census_objsh_set.calls++;
    if (objsh_is_base(x, rows_m1, base_cells)) {
        census_objsh_set.base_calls++;
        /* Each key is a strict subset of the previous one, so one chain of mixes yields all four hashes.
         * (The chain visits the full key's fields in a different order than the original single-key census
         * did; it covers the same TUPLE, so the distinct count is unchanged — the 30/40/60-frame leg-0
         * full-key control reproduces 100/149/349 exactly.)
         * The chain hashes the FULL 16-bit `color`, mirroring the runtime cache key (blitter_objshift.c),
         * while the engine itself consumes only `color & OBJSH_NIBBLE` (blit.c). Measured across all legs
         * the colour records only ever carry {0,3,5,7,13,15}, so the two widths coincide on real data. */
        uint32_t h[OBJSH_KEY_COUNT];
        h[OBJSH_KEY_SPRITE]  = mix(mix(mix(CENSUS_SEED, src_off), (uint32_t)(uint16_t)stride),
                                   (uint32_t)base_cells);
        h[OBJSH_KEY_NOCOLOR] = mix(h[OBJSH_KEY_SPRITE], rows_m1);
        h[OBJSH_KEY_NOSHIFT] = mix(h[OBJSH_KEY_NOCOLOR], color);
        h[OBJSH_KEY_FULL]    = mix(h[OBJSH_KEY_NOSHIFT], x & OBJSH_NIBBLE);
        for (int i = 0; i < OBJSH_KEY_COUNT; i++) census_add(objsh_key_sets[i], h[i] ? h[i] : 1);
    }
    RM_BLIT_OBJSHIFT(dst, dst_off, src, src_off, x, color, rows_m1, stride, color_pairs, base_cells);
}

/* The report's wire format (run_ste_census.py mirrors it): a 2-word header {CENSUS_MAGIC, set count},
 * then one 7-word block per set from word CENSUS_HEADER_WORDS. Each block is
 * {distinct_hi, distinct_lo, base_hi, base_lo, total_hi, total_lo, saturated} — 32-bit big-endian hi/lo
 * except saturated. The header is the tripwire: SCREEN.BIN is also written by other build variants
 * (the boot golden), so a reader that finds no magic knows it is looking at something else. */
#define CENSUS_MAGIC        0xC5C5u
#define CENSUS_HEADER_WORDS 2
#define CENSUS_REPORT_SETS  (1 + OBJSH_KEY_COUNT)
#define CENSUS_BLOCK_WORDS  7

/* The block order, declared once — run_ste_census.py's SETS tuple mirrors it element for element. */
static const Census *const report_sets[CENSUS_REPORT_SETS] = {
    &census_objsh2_set, &census_objsh_set,
    &census_objsh_noshift_set, &census_objsh_nocolor_set, &census_objsh_sprite_set
};

void blitter_census_report(uint16_t *w) {
    w[0] = CENSUS_MAGIC;
    w[1] = CENSUS_REPORT_SETS;
    for (int i = 0; i < CENSUS_REPORT_SETS; i++) {
        const Census *cs = report_sets[i];
        /* The colour engine's four keys share one call stream, counted on the full-key set (see the
         * wrapper); every colour block reports those same counts. */
        const Census *counts = (i == 0) ? cs : &census_objsh_set;
        uint16_t *b = w + CENSUS_HEADER_WORDS + i * CENSUS_BLOCK_WORDS;
        b[0] = (uint16_t)(cs->distinct >> 16);            b[1] = (uint16_t)cs->distinct;
        b[2] = (uint16_t)(counts->base_calls >> 16);      b[3] = (uint16_t)counts->base_calls;
        b[4] = (uint16_t)(counts->calls >> 16);           b[5] = (uint16_t)counts->calls;
        b[6] = (uint16_t)cs->saturated;
    }
}
