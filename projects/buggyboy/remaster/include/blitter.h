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
#define BLT_CTL_BUSY_BIT  7                    /* ...as a BIT INDEX: the shared-bus loop needs a bset operand */
#define BLT_CTL_HOG       0x40                 /* 1 = hold the bus until done; 0 = shared (64-word bursts) */
#define BLT_CTL_SMUDGE    0x20
/* The mask and the bit index are the same fact spelled twice (C cannot take a bset operand from a mask),
 * so pin them equal rather than letting one be re-mapped without the other. */
typedef char blt_busy_bit_matches_mask[((1u << BLT_CTL_BUSY_BIT) == BLT_CTL_BUSY) ? 1 : -1];

/* Every pass in this project writes whole destination words, so all three endmasks are all-ones. Named
 * once here, where the rest of the BLT_* vocabulary lives, instead of as a bare literal per pass builder. */
#define BLT_ENDMASK_ALL   0xFFFFu

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

/* Start the chip on the registers already poked, and wait for it to finish. ONE owner of the HOG policy
 * for every pass this project fires — the full-register driver (blit_run) and the skew path's batched
 * passes both come through here, so the bus-hold decision cannot drift between them. HOG (bit 6) holds
 * the bus until the pass completes, so the 68000 is frozen and the very next instruction already sees
 * BUSY clear; the poll is belt-and-braces (and the shape a shared-mode restart would need). See
 * src/blitter.c for the HOG-vs-shared justification. Supervisor only. */
static inline void blit_start_and_wait(void) {
    BLT_B(BLT_CONTROL) = (uint8_t)(BLT_CTL_BUSY | BLT_CTL_HOG);
    while (BLT_B(BLT_CONTROL) & BLT_CTL_BUSY) { /* HOG completes before the next fetch; poll is a no-op */ }
}

/* The SHARED-bus (non-HOG) sibling: the chip yields the bus every 64 words instead of freezing the 68000
 * for the whole pass, and the CPU re-arms BUSY until the pass completes. This is the second half of the
 * ONE bus policy this header owns — the road-scroll route (src/blitter_scroll.c) fires SCREEN-SIZED
 * passes, a different trade from the object blits' tens of microseconds (BLIT_STE_SPEC §16).
 *
 * TWO parts, and the FIRST is the one that is easy to get wrong (measured: without it the sweep fails
 * 640/640 cases, with ~64 words written per pass):
 *   1. an explicit `move.b #BUSY` START. It also CLEARS HOG, which a previous blit_start_and_wait left
 *      set. Without it the loop's own first `bset` would be the start — and its Z flag would report the
 *      PRE-start BUSY (0), so the loop would fall straight through after one burst.
 *   2. BLIT_STE_SPEC §2's restart discipline: `bset` re-arms BUSY and reports the pre-write bit in one
 *      indivisible bus cycle, so the loop spins while the chip is mid-pass and falls through on the
 *      first read of 0 — the completed state, where re-arming is a no-op against y_count == 0. It must
 *      be asm because C has no set-and-test-the-old-value. `nop` lets the chip settle before the branch.
 * Supervisor only. */
static inline void blit_start_and_wait_shared(void) {
    volatile uint8_t *ctl = (volatile uint8_t *)BLT_CONTROL;
    BLT_B(BLT_CONTROL) = BLT_CTL_BUSY;                 /* HOG CLEAR — the start the restart loop resumes */
    __asm__ volatile ("1: bset.b #%c1,(%0)\n\t"
                      "   nop\n\t"
                      "   bne.s 1b"
                      : : "a"(ctl), "i"(BLT_CTL_BUSY_BIT) : "cc", "memory");
}

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

/* Size of, and base for, the objshift2 pre-shift cache. It is NOT static BSS (1 MB memory diet, slice 2):
 * rm_blit_bind_all places it in the free TPA above the program, and only on a machine that actually binds
 * the blitter route. Both are for that owner alone — nothing else may place or size it. */
uint32_t rm_blit_objshift2_cache_bytes(void);
void rm_blit_objshift2_cache_place(void *mem);

/* Colour-indexed pass-1 engine, PRE-SHIFT path (src/blitter_objshift.c): the same 2-pass cookie-cut as
 * objshift2 with a 4-word mask + a colour fill composited into the OR data. MEASUREMENT BUILD ONLY
 * (GAME_STE_SWEEP) — the shipping colour route is the hardware-SKEW path below, which needs no per-call
 * materialise; this stays compiled so the sweep keeps the pre-shift recipe pinned. */
int rm_blit_objshift_blitter(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                             uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                             const uint8_t *color_pairs, int base_cells);

/* Is this draw the BASE family — the only family the blitter paths serve (a positive aligned column
 * below the width-dependent right bound, and a non-zero row count)? Only src/blit.c's engine still
 * open-codes the test inline (it computes the column for its own draw anyway); every path that just
 * ASKS — both blitter colour paths, the skew family gate, the census/sweep bookkeeping — shares this
 * one copy. */
static inline int objsh_is_base(uint16_t x, uint16_t rows_m1, int base_cells) {
    if ((int16_t)rows_m1 + 1 <= 0) return 0;               /* zero rows: no draw, not a BASE case */
    int16_t col = (int16_t)((int16_t)((int16_t)(uint16_t)x >> 1) & (int16_t)COL_ALIGN);
    int16_t ceiling = (int16_t)(OBJSH_RIGHT_BOUND - OBJSH_CELL_BYTES * (base_cells - 1));
    return !(col < 0 || (int16_t)(col - ceiling) >= 0);    /* LEFT / RIGHT clip -> CPU hybrid */
}

/* ---- hardware-SKEW colour path (src/blitter_skew.c) — the SHIPPING colour route ----------------------
 * Same contract as rm_blit_objshift_blitter (1 = drawn, 0 = CPU hybrid) but blits from UNSHIFTED,
 * colour-independent bitmaps with the chip's SKEW register doing the fine-x shift, so a bitmap set
 * depends only on the SPRITE key (src_off, stride, base_cells) — the census-bounded key that lets a
 * static table retire the per-call materialise entirely (BLIT_STE_SPEC §12/§13). */

/* Mutation knob for the sweep's coverage check (-DRM_SKEW_MUTATE=n, set by build_game.sh): each value
 * breaks ONE thing the skew route depends on — a calibrated register (1-5) or the sprite table's grow
 * rule (6) — so a sweep that still passes would prove that part of the route is not really exercised.
 * run_ste_sweep.py names the section each mutation must make FAIL. Declared here because
 * src/blitter_sweep.c reads it too — a mutate build runs the skew grid + the table section alone (the
 * other two grids are unmutated, so re-running them would only burn emulated cycles). */
#define RM_SKEW_MUT_NONE       0
#define RM_SKEW_MUT_SKEW_PLUS  1                           /* skew = fine_x + 1 */
#define RM_SKEW_MUT_FXSR       2                           /* set FXSR (an extra source read per line) */
#define RM_SKEW_MUT_ENDMASK1   3                           /* drop the column-0 leading-edge guard */
#define RM_SKEW_MUT_ENDMASK3   4                           /* drop the last-column trailing-edge guard */
#define RM_SKEW_MUT_PLANE3     5                           /* drop plane 3's `& ~m` is_last special */
#define RM_SKEW_MUT_NOGROW     6                           /* never re-materialise a table entry deeper */
#define RM_SKEW_MUT_SKEW_FIRST RM_SKEW_MUT_SKEW_PLUS
#define RM_SKEW_MUT_SKEW_LAST  RM_SKEW_MUT_NOGROW
/* The ROAD-SCROLL route's mutations (src/blitter_scroll.c) share this one knob rather than adding a
 * second -D and a second set of build-script plumbing; they start at RM_SKEW_MUT_SCROLL_FIRST so a build
 * can tell which route it is breaking (a mutate build sweeps only the sections of THAT route). */
#define RM_SKEW_MUT_SCROLL_FILL_LOP  7                     /* fill the odd plane-words with ones, not zeros */
#define RM_SKEW_MUT_SCROLL_XCOUNT    8                     /* main copy one dst word per row too wide */
#define RM_SKEW_MUT_SCROLL_NOWRAP    9                     /* never fire the wrapped-tail blit */
#define RM_SKEW_MUT_SCROLL_SEAM_1ST 10                     /* run the CPU seam BEFORE the blits, not after */
#define RM_SKEW_MUT_SCROLL_FIRST     RM_SKEW_MUT_SCROLL_FILL_LOP
#define RM_SKEW_MUT_SCROLL_LAST      RM_SKEW_MUT_SCROLL_SEAM_1ST
/* The HUD-DASHBOARD route's mutations (src/blitter_dash.c), on the same knob for the same reason. */
#define RM_SKEW_MUT_DASH_LOP_SWAP   11                     /* swap the cookie-cut's AND and OR passes */
#define RM_SKEW_MUT_DASH_XCOUNT     12                     /* one group per row too wide */
#define RM_SKEW_MUT_DASH_YINC       13                     /* per-row correction one group short */
#define RM_SKEW_MUT_DASH_P2COPY     14                     /* the disproved "7-pass" plane-2 copy */
#define RM_SKEW_MUT_DASH_FIRST       RM_SKEW_MUT_DASH_LOP_SWAP
#define RM_SKEW_MUT_DASH_LAST        RM_SKEW_MUT_DASH_P2COPY
#ifndef RM_SKEW_MUTATE
#define RM_SKEW_MUTATE RM_SKEW_MUT_NONE
#endif
#define RM_SKEW_MUTATED       (RM_SKEW_MUTATE != RM_SKEW_MUT_NONE)
/* One BOUNDED range per route, and every selector reads POSITIVELY ("is this MY route's mutation?").
 * Ranges rather than `>= FIRST` because the next route's numbers would otherwise be swallowed by the
 * previous route's predicate and sweep the wrong section; positive rather than by-exclusion so adding a
 * fifth route is an additive edit instead of an amendment to everyone else's negations. */
#define RM_SKEW_ROUTE_MUTATED (RM_SKEW_MUTATE >= RM_SKEW_MUT_SKEW_FIRST && \
                               RM_SKEW_MUTATE <= RM_SKEW_MUT_SKEW_LAST)
#define RM_SCROLL_MUTATED     (RM_SKEW_MUTATE >= RM_SKEW_MUT_SCROLL_FIRST && \
                               RM_SKEW_MUTATE <= RM_SKEW_MUT_SCROLL_LAST)
#define RM_DASH_MUTATED       (RM_SKEW_MUTATE >= RM_SKEW_MUT_DASH_FIRST && \
                               RM_SKEW_MUTATE <= RM_SKEW_MUT_DASH_LAST)

#define OBJSH_SKEW_MAX_CELLS  2                            /* base_cells family max */
/* Bitmap 0 is the show mask; bitmaps 1..OBJSH_PLANES are the per-plane pixel words. */
#define OBJSH_SKEW_BM_MASK    0
#define OBJSH_SKEW_BM_PLANE0  1
#define OBJSH_SKEW_N_BITMAPS  (1 + OBJSH_PLANES)
/* Pad words past the live rows*base_cells. ONE is the calibrated path's need: every line wastes one
 * source read, and the last line's lands a word past the bitmap (see blitter_skew.c's header), so the
 * shipping table pays exactly one pad word per bitmap. A SKEW-mutate build needs far more:
 * RM_SKEW_MUT_FXSR's extra per-line read drifts the source one word further per line, up to rows words by
 * the last line. A mutate build must still FAIL, but it must not read out of bounds while doing so — and
 * it is a measurement build, so the headroom costs the shipping PRG nothing. Only a SKEW-ROUTE mutation
 * needs it: another route's mutation touches no skew register, so it keeps the shipping pad — and with
 * it the shipping table size, rather than asking rm_blit_bind_all for 61 KB more TPA to pad a route its
 * sweep does not even run. */
#if RM_SKEW_ROUTE_MUTATED
#define OBJSH_SKEW_PAD_WORDS  (OBJSH_MAX_ROWS + 1)
#else
#define OBJSH_SKEW_PAD_WORDS  1
#endif
#define OBJSH_SKEW_BM_WORDS   (OBJSH_MAX_ROWS * OBJSH_SKEW_MAX_CELLS + OBJSH_SKEW_PAD_WORDS)

/* The UNSHIFTED, colour-independent bitmap set one sprite region materialises into — one instance per
 * live table entry, which is why materialise and blit take it explicitly rather than sharing a static. */
typedef struct {
    uint16_t word[OBJSH_SKEW_N_BITMAPS][OBJSH_SKEW_BM_WORDS];
} ObjshSkewBitmaps;

/* Materialise one sprite region into an explicit destination bitmap set — the table's fill seam, and
 * what the sweep times in isolation. */
void rm_objsh_skew_materialise(ObjshSkewBitmaps *bm, const uint8_t *src, uint32_t src_off,
                               int16_t stride, int rows, int base_cells);
/* Blit an ALREADY-materialised bitmap set (the shipping route calls this straight off the table; the
 * sweep re-fires it to time the chip passes in isolation). Returns 1 if drawn, 0 for the CPU hybrid —
 * same family contract as the full entry below, which is materialise + this. Supervisor only. */
int rm_blit_objshift_skew_from(const ObjshSkewBitmaps *bm, uint8_t *dst, uint32_t dst_off, uint16_t x,
                               uint16_t color, uint16_t rows_m1, const uint8_t *color_pairs,
                               int base_cells);
/* Sweep entry (GAME_STE_SWEEP): materialise into a private scratch, then blit it — the un-tabled path,
 * so the sweep pins the recipe without depending on table state. */
int rm_blit_objshift_skew(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                          uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                          const uint8_t *color_pairs, int base_cells);

/* Entries in the static sprite-key table (src/blitter_skew.c): the census measured 98 distinct sprite
 * keys on the worst leg, and this is the next power of two above it (the probe wrap wants a power of
 * two) with headroom for the cross-leg union — run_ste_census.py prints that union. It lives in the
 * header because the sweep's table section fills the table to capacity to pin the full-table decline,
 * and a copy of the number in the sweep or in Python would silently drift from the table itself. */
#define OBJSH_SKEW_TABLE_ENTRIES  128

/* The table-routed skew blit, SUPERVISOR-mode entry: look the sprite key up in the table (materialising
 * or growing the entry as needed), then blit it. Returns 1 if drawn, 0 for the CPU hybrid — a clip
 * family / over-tall sprite, or a table with no room left. This is the dispatch's inner half, called
 * directly by the sweep's table section (already inside one excursion). */
int rm_blit_objshift_skew_tabled(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                                 uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                                 const uint8_t *color_pairs, int base_cells);
/* Runtime dispatch (object_list.c's RM_BLIT_OBJSHIFT seam): the skew table + blitter for BASE, CPU asm
 * for the clip families / an over-tall sprite / a full table. Runs the attempt in one Supexec per blit. */
void rm_blit_objshift_dispatch(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                               uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                               const uint8_t *color_pairs, int base_cells);
/* Bind the RM_BLIT_OBJSHIFT function pointer ONCE at boot — the objshift2 pattern (§11): the blitter
 * dispatch on a blitter machine, the CPU asm engine otherwise, so a plain ST pays no per-blit branch. */
void rm_blit_objshift_bind(int have_blitter);
/* Drop every materialised table entry (and re-arm the full-table latch) — call after the arena.gfx
 * source is rewritten in place (the F10 asset reload), or the table would serve bitmaps built from the
 * old bytes. */
void rm_blit_objshift_skew_table_flush(void);

/* Size of, and base for, the sprite-key table — placed exactly like the objshift2 cache above (slice 2).
 * Until the place call the table declines every blit, so an unplaced route can never dereference it. */
uint32_t rm_blit_objshift_skew_table_bytes(void);
void rm_blit_objshift_skew_table_place(void *mem);

/* ---- the road fine-scroll route (src/blitter_scroll.c) ------------------------------------------
 * The third route, and the only one with NO lookup table: it blits the road band straight out of the
 * `shifted` pre-rotated playfield the CPU reference already reads, so there is nothing to place and
 * nothing to flush. Bind ONCE at boot, like the object routes; the seam itself (a boot-bound function
 * pointer over rm_blit_road_scroll) lives at the sole call site, src/frame.c. The route's own entry
 * points take a ScrollState and so are declared in include/scroll_const.h, which owns that type's
 * geometry — only the bind is needed here, by rm_blit_bind_all below. */
void rm_blit_road_scroll_bind(int have_blitter);
/* Routed / declined call counts for the cadence tail (game_main.c) — the observable that proves the
 * route was live on a run. `declined` is a tripwire, not a family split: see src/blitter_scroll.c. */
extern uint32_t rm_scroll_blit_routed, rm_scroll_blit_declined;

/* ---- the HUD dashboard route (src/blitter_dash.c) -----------------------------------------------
 * The fourth route, and the second with no lookup table: it cookie-cuts the LIVE per-leg dashboard art
 * in place out of the graphics arena (the arena and the framebuffer share a row pitch), so there is
 * nothing to place, nothing to flush and nothing that can go stale. Bound ONCE at boot alongside the
 * road scroll, on the probe alone; the seam itself (a boot-bound function pointer over rm_hud_dashboard)
 * lives at the sole call site, src/hud.c. The route's own entry points take the dashboard geometry and
 * so are declared in include/dash_const.h, which owns it — only the bind is needed here. */
void rm_blit_hud_dashboard_bind(int have_blitter);
/* Routed / declined call counts for the cadence tail — same contract as the scroll pair above; here the
 * tripwire is an odd source/destination address (see src/blitter_dash.c). */
extern uint32_t rm_dash_blit_routed, rm_dash_blit_declined;

/* ---- the four engine routes, enumerated ONCE (src/blitter.c) ------------------------------------
 * Every boot / reload site drives the routes as a SET, so the list lives in one place instead of being
 * repeated at each site (game_main's boot bind + its F10 reload flush) — a new engine's BIND and FLUSH
 * go in these two functions and nowhere else. (The engine itself needs more than that: its own bind
 * declaration above, a seam macro at its sole call site, the Makefile's STE_SRC and build_game.sh's
 * STE_SOURCES, a cadence-tail counter pair, and a sweep section + mutation range.) */
/* Alignment both placed tables need — their entry structs hold longs, so 4 keeps every field naturally
 * aligned. Owned here because TWO sides depend on it: rm_blit_bind_all pads the window base up to it,
 * and game_main.c's TPA map rounds the window base itself (the free TPA starts wherever the BSS ends).
 * A second copy of the number is a second thing to keep in step, so the window side includes this one. */
#define BLIT_TABLE_ALIGN 4
/* Boot: place both routes' lookup tables in `window` (the free TPA above the program) and bind every
 * route to the blitter or the CPU asm engine. Returns the binding actually made — 0 when there is no
 * blitter OR the window is too small for the tables, in which case the CPU engines are bound exactly as
 * on a machine with no blitter. The caller must use the RETURN value, not its own probe result. */
int rm_blit_bind_all(int have_blitter, void *window, uint32_t window_bytes);
void rm_blit_flush_all(void);              /* reload: drop every materialised bitmap both routes hold */

/* Full-sweep proof (GAME_STE_SWEEP build): run rm_blit_objshift2_blitter vs the CPU engine over the
 * objshift2 case space; return a framebuffer encoding per-case results (see src/blitter_sweep.c) and the
 * total mismatch count. `tables_bound` is rm_blit_bind_all's RETURN: 0 means the routes' lookup tables
 * were never placed (no blitter, or no room in the TPA), and the sweep then sweeps nothing and says so
 * in its report rather than reporting a vacuous zero.
 *
 * `dash_stage` / `dash_ctx` let the HUD-dashboard section composite the game's REAL per-leg art. The
 * sweep cannot build that art itself — it comes from the asset files through the game's leg-init code —
 * so the CALLER (game_main.c, which owns the loaded arena and the shell's event context) passes one
 * function that rebuilds leg `leg`'s art, walks its progress marker `extra_label_passes` further, and
 * returns where the art landed. The sweep depends on that one function, not on the shell's struct
 * shapes, which is why nothing here names a game type. */
typedef const uint8_t *(*DashStageFn)(void *ctx, int leg, int extra_label_passes);
const uint8_t *blitter_sweep(long *mismatch_out, int tables_bound, DashStageFn dash_stage,
                             void *dash_ctx);

/* Poke every register of one fully-specified pass WITHOUT starting the chip, so the caller owns the bus
 * policy (blit_start_and_wait / blit_start_and_wait_shared above). Supervisor only. */
void blit_poke(const BlitPass *p);
/* Run one blitter pass to completion (HOG mode) from the current supervisor context: blit_poke + the HOG
 * start. See src/blitter.c for the HOG-vs-shared justification. */
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
