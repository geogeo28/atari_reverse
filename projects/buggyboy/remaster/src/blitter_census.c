/* blitter_census.c — GAME_STE_CENSUS instrumentation (PERF30 C4 slice 5). Counts the DISTINCT
 * materialise-key tuples the object lists actually issue over a real drive, per fine-x engine, so the
 * boot-pre-shift-table decision is made on measured data, not assumption. The key is exactly the
 * blitter cache key sans the (constant) arena.gfx base: what a boot table would have to enumerate.
 *
 * object_list.c routes RM_BLIT_OBJSHIFT{,2} here under -DGAME_STE_CENSUS; each wrapper records the tuple
 * then calls the CPU reference (so pixels are unaffected and every call — BASE and CLIP — is counted).
 * A large open-addressed set counts distinct insertions; game_main's census_dump writes the tallies to
 * SCREEN.BIN for run_ste_census.py. Compiled only in the census build.
 */
#include "game.h"
#include "blit_const.h"
#include "st.h"

#define CENSUS_SLOTS 0x10000                               /* 65536 open-addressed slots per engine */
#define CENSUS_MASK  (CENSUS_SLOTS - 1)

typedef struct {
    uint32_t key[CENSUS_SLOTS];                            /* stored tuple hash (0 == empty; see census_add) */
    int used[CENSUS_SLOTS];                                /* slot occupied (distinguishes a real hash of 0) */
    uint32_t distinct;                                     /* distinct base-family tuples seen */
    uint32_t calls;                                        /* total calls (base + clip) */
    uint32_t base_calls;                                   /* base-family calls (what a table would serve) */
    uint32_t saturated;                                    /* set overflowed CENSUS_SLOTS distinct */
} Census;

static Census census_objsh2_set, census_objsh_set;

/* Insert a tuple hash; bump distinct on first sight. Linear probe. */
static void census_add(Census *cs, uint32_t h) {
    uint32_t i = h & CENSUS_MASK;
    for (uint32_t n = 0; n < CENSUS_SLOTS; n++) {
        if (!cs->used[i]) {
            if (cs->distinct >= CENSUS_SLOTS - 1) { cs->saturated = 1; return; }
            cs->used[i] = 1; cs->key[i] = h; cs->distinct++;
            return;
        }
        if (cs->key[i] == h) return;                       /* already seen */
        i = (i + 1) & CENSUS_MASK;
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

static uint32_t mix(uint32_t h, uint32_t v) { return (h ^ v) * 2654435761u; }

/* ---- census wrappers: record the tuple, then draw with the CPU reference ---- */
void rm_blit_objshift2_census(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                              uint16_t x, uint16_t rows_m1, int width_idx) {
    census_objsh2_set.calls++;
    if (objsh2_is_base(x, rows_m1, width_idx)) {
        census_objsh2_set.base_calls++;
        uint32_t h = mix(mix(mix(mix(0x9e3779b9u, src_off), x & OBJSH_NIBBLE), (uint32_t)width_idx), rows_m1);
        census_add(&census_objsh2_set, h ? h : 1);
    }
    RM_BLIT_OBJSHIFT2(dst, dst_off, src, src_off, x, rows_m1, width_idx);
}

void rm_blit_objshift_census(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                             uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                             const uint8_t *color_pairs, int base_cells) {
    census_objsh_set.calls++;
    if (objsh_is_base(x, rows_m1, base_cells)) {
        census_objsh_set.base_calls++;
        uint32_t h = mix(mix(mix(mix(mix(mix(0x9e3779b9u, src_off), x & OBJSH_NIBBLE), color),
                                 (uint32_t)(uint16_t)stride), rows_m1), (uint32_t)base_cells);
        census_add(&census_objsh_set, h ? h : 1);
    }
    RM_BLIT_OBJSHIFT(dst, dst_off, src, src_off, x, color, rows_m1, stride, color_pairs, base_cells);
}

/* Fill a per-engine block of 7 words (all 32-bit big-endian hi/lo except saturated):
 * {distinct_hi, distinct_lo, base_hi, base_lo, total_hi, total_lo, saturated}. */
void blitter_census_report(uint16_t *w) {
    const Census *e[2] = { &census_objsh2_set, &census_objsh_set };
    for (int i = 0; i < 2; i++) {
        w[i * 7 + 0] = (uint16_t)(e[i]->distinct >> 16);   w[i * 7 + 1] = (uint16_t)e[i]->distinct;
        w[i * 7 + 2] = (uint16_t)(e[i]->base_calls >> 16); w[i * 7 + 3] = (uint16_t)e[i]->base_calls;
        w[i * 7 + 4] = (uint16_t)(e[i]->calls >> 16);      w[i * 7 + 5] = (uint16_t)e[i]->calls;
        w[i * 7 + 6] = (uint16_t)e[i]->saturated;
    }
}
