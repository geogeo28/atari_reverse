/* sprite.c — everything that puts a pixel on Flying Shark's screen.
 *
 * Three layers, bottom up:
 *
 *   * the TWELVE masked sprite blitters — four width classes, each with a left- and a right-clipped
 *     variant. They share one body (`blit_sprite_rows` below); the twelve entry points differ only
 *     in how many 16-pixel groups they span and which of them a clip lets through;
 *   * the FIVE restore blitters and `scroll_wrap_copy_1280`, which are unrolled `move.l` runs, and
 *     `tile_blit_overlay_masked`, which merges an overlay tile over a base tile;
 *   * `render_frame` @ 0x14446, the 45th and last call of the frame loop, which drives all of them:
 *     the ring seam, two display-list passes, the overlay repaint, the flip, the newly exposed tile
 *     band and the restore-list replay.
 *
 * THE DISPATCH TABLES ARE READ-ONLY DATA AND THIS FILE DISPATCHES DIRECTLY. The original picks a
 * blitter with `lea <table>,a2 / lsl.w #2,d2 / adda.w d2,a2 / movea.l (a2),a2 / jsr (a2)`; the four
 * tables live in the DATA segment and no instruction in the program writes one. So a `switch` on
 * the same index is the same call, and `test_sprite.py`'s
 * `test_the_blit_tables_name_the_routines_this_file_dispatches_to` reads all seventeen longwords
 * out of the image and checks they are the routines named here — which is the pin that makes the
 * shortcut sound rather than assumed.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif

#include "machine.h"
#include "common.h"       /* addr_sub and copy_longs, shared with hud.c and the two blit paths */
#include "os.h"
#include "sched.h"

#include "display_list.h"
#include "globals.h"
#include "sprite.h"

/* ================================================================================================
 * The masked sprite blitters — sprite_blit_w16/w32/w48/w64 @ 0x153b2/0x15408/0x154a4/0x15586 and
 * their clip_left / clip_right variants @ 0x14dda..0x151d2.
 *
 * One row of a class-`c` sprite is (c + 1) source groups of five words: mask, then planes 0..3. The
 * blitter loads each word into the low half of a 32-bit register — the mask's register preloaded
 * with 0xffff0000 — and `ror.l`s all five by the sub-word shift. That rotate is the whole trick:
 * afterwards the register's LOW half is the piece of the source group that belongs in this screen
 * group and its HIGH half is the piece that spills into the next one. So screen group `g` takes the
 * low half of source group `g` ANDed/ORed with the high half of source group `g - 1`, with an
 * absent group standing in as "opaque mask, no pixels" at either end. That is exactly what the
 * `swap` in the original produces, and why a class-`c` sprite covers c + 2 screen groups.
 * ============================================================================================= */

/* `move.l #$ffffffff,d1` before `move.w (a0)+,d1`: the mask word arrives in the low half and the
 * high half stays all ones, so the spill into the next group leaves that group's background alone
 * wherever this group's mask did not reach it. */
#define SPRITE_MASK_PRELOAD 0xffff0000u
/* ...and the register a group that does not exist would have held: opaque in both halves. `d2..d5`
 * are `clr.l`ed for the plane half of the same idea, which is a plain zero. */
#define SPRITE_GROUP_ABSENT 0xffffffffu

/* How a blitter decides whether to draw a group, which is the ONE difference between the clipped
 * and unclipped entries: a clipped one `btst #n,$16426.l` before each group's merge (0x14e40,
 * 0x14e6c, 0x1512e, 0x1515c and their siblings), an unclipped one has no test at all and merges
 * every group. Two spellings of the same body, so the flag is passed rather than a gate byte.
 *
 * THE CLIPPED FORM RE-READS THE BYTE FROM MEMORY at every group of every row, and that is not an
 * accident of the transcription: the original never holds `blit_clip_mask` in a register, so a blit
 * whose own destination covers 0x16426 draws its later groups under the gate its earlier ones
 * wrote. Nothing the game does puts a screen there — the ring is at 0x60000 and above — but the
 * faithful spelling costs one image read, and a poked destination is what pins it. */
#define SPRITE_GATE_UNCLIPPED 0   /* no `btst`: draw every group */
#define SPRITE_GATE_CLIP_MASK 1   /* `btst #n,$16426.l` once per group, re-read each time */

/* `asr.w #n,Dn` — an ARITHMETIC right shift of a signed word. C leaves `negative >> n`
 * implementation-defined, and both callers here shift a NEGATIVE x (a sprite clipped off the left
 * edge), so it is spelt out rather than left to the compiler: shift the bits, then put the sign
 * back into the top `count` of them. */
static int16_t asr16(int16_t value, unsigned count) {
    uint16_t bits = (uint16_t)((uint16_t)value >> count);

    if (count != 0 && value < 0)
        bits = (uint16_t)(bits | (uint16_t)(0xffffu << (16u - count)));
    return (int16_t)bits;
}

static uint16_t low_word(uint32_t value)  { return (uint16_t)value; }
static uint16_t high_word(uint32_t value) { return (uint16_t)(value >> 16); }

/* `and.w <keep>,(aN) / or.w <pixels>,(aN)` — the masked read-modify-write of ONE plane word, which
 * is the primitive under every drawing routine in this file: the sprite blitters' per-group write,
 * the overlay repaint's, and the tile merge's. One definition, so a faithfulness correction to it
 * cannot reach one caller and miss another. */
static void merge_plane_word(uint8_t *image, uint32_t word, uint16_t pixels, uint16_t keep) {
    wr16(image + word, (uint16_t)((be16(image + word) & keep) | pixels));
}

/* One screen row. Returns the source cursor advanced past the row's groups, as the original's
 * `(a0)+` leaves it. `dst` is not returned because the caller steps whole 160-byte rows: the
 * original's per-group `lea 8(a1),a1` / `lea 6(a1),a1` and its closing `lea N(a1),a1` add up to
 * exactly one row for every width class (146/138/130/122 for classes 0..3). */
static uint32_t blit_sprite_row(uint8_t *image, uint32_t src, uint32_t dst,
                                unsigned source_groups, unsigned shift, int gated) {
    unsigned screen_groups = source_groups + 1u;
    uint32_t spill_mask = SPRITE_GROUP_ABSENT;              /* from the group before the first: none */
    uint32_t spill_plane[SPRITE_PLANES] = {0u, 0u, 0u, 0u};

    for (unsigned group = 0; group < screen_groups; group++) {
        uint32_t mask = SPRITE_GROUP_ABSENT;
        uint32_t plane[SPRITE_PLANES] = {0u, 0u, 0u, 0u};

        if (group < source_groups) {
            mask = rotate_right32(SPRITE_MASK_PRELOAD | be16(image + src), shift);
            for (unsigned p = 0; p < SPRITE_PLANES; p++)
                plane[p] = rotate_right32(be16(image + src + (1u + p) * 2u), shift);
            src = addr_add(src, SPRITE_GROUP_BYTES);
        }

        /* Bit 0 of the gate is the LAST screen group and the bits run leftward — `btst #1` then
         * `btst #0` for a class-0 sprite, `btst #4`..`btst #0` for a class-3 one. Read afresh
         * here, not hoisted: see SPRITE_GATE_CLIP_MASK. */
        if (!gated || (image[A_blit_clip_mask] & (1u << (screen_groups - 1u - group)))) {
            uint16_t keep = (uint16_t)(low_word(mask) & high_word(spill_mask));
            for (unsigned p = 0; p < SPRITE_PLANES; p++)
                merge_plane_word(image, addr_add(dst, group * SCREEN_GROUP_BYTES + p * 2u),
                                 (uint16_t)(low_word(plane[p]) | high_word(spill_plane[p])), keep);
        }

        spill_mask = mask;
        /* SPELT OUT RATHER THAN `memcpy`, and it is a performance fact rather than a style one.
         * `atari/build.sh` compiles with `-ffreestanding`, which implies `-fno-builtin`, so a
         * 16-byte `memcpy` here is a real `jsr` into the shim's byte loop — 588 cycles a call,
         * 802 calls a frame, 472,000 cycles a frame, 28% of the whole window (measured with
         * `atari/profile.py ours`). The four assignments are four `move.l`s and no call.
         */
        for (unsigned p = 0; p < SPRITE_PLANES; p++)
            spill_plane[p] = plane[p];
    }
    return src;
}

static void blit_sprite_rows(uint8_t *image, uint32_t src, uint32_t dst, unsigned width_class,
                             unsigned shift, uint32_t rows_minus_one, int gated) {
    unsigned rows = loop_passes(rows_minus_one + 1u, COUNT_MASK_WORD);   /* the closing `dbf d7` */

    for (unsigned row = 0; row < rows; row++) {
        src = blit_sprite_row(image, src, dst, width_class + 1u, shift, gated);
        dst = addr_add(dst, SCREEN_ROW_BYTES);
    }
}

/* ---- THE ASM-TWIN SEAM, and it covers the UNGATED half of the routine above ---------------------
 *
 * `src/asm/sprite.S` transcribes the original's own four unclipped blitters (0x153b2 / 0x15408 /
 * 0x154a4 / 0x15586) and `atari/build.sh` links that twin into the TARGET build, where it is 3.2x
 * the C's speed because it is the original's instruction sequence and nothing else
 * (`atari/profile.py`, and `../STATUS.md`'s "On-target performance"). The differential build never
 * sees it: `test/test_asm_sprite.py` is what proves the two equal, over this file's own cases.
 *
 * A MACRO OVER THE ARGUMENTS RATHER THAN A WRAPPER FUNCTION, so that the gated call site below
 * keeps `blit_sprite_rows` referenced in both builds. A wrapper would be an unused `static` in the
 * build that has the twin, which is a warning at best and a silently dropped body at worst.
 *
 * THE GATED HALF KEEPS THE C. `blit_sprite_clipped` is 8% of the blitter's cycles measured over the
 * attract screen (53,398 a frame against 582,591), it is four more transcribed bodies, and the four
 * it would add are the ones with a `btst` on an absolute address that the image base makes
 * un-transcribable byte for byte. `../STATUS.md` carries the row.
 */
#ifdef FS_ASM_SPRITE
void blit_sprite_rows_unclipped_asm(uint8_t *image, uint32_t src, uint32_t dst,
                                    unsigned width_class, unsigned shift, uint32_t rows_minus_one);
#define BLIT_SPRITE_ROWS_UNCLIPPED(image, src, dst, klass, shift, rows)                            \
    blit_sprite_rows_unclipped_asm((image), (src), (dst), (klass), (shift), (rows))
#else
#define BLIT_SPRITE_ROWS_UNCLIPPED(image, src, dst, klass, shift, rows)                            \
    blit_sprite_rows((image), (src), (dst), (klass), (shift), (rows), SPRITE_GATE_UNCLIPPED)
#endif

void sprite_blit_w16(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift, uint32_t rows_minus_one) {
    BLIT_SPRITE_ROWS_UNCLIPPED(image, src, dst, 0u, shift, rows_minus_one);
}

void sprite_blit_w32(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift, uint32_t rows_minus_one) {
    BLIT_SPRITE_ROWS_UNCLIPPED(image, src, dst, 1u, shift, rows_minus_one);
}

void sprite_blit_w48(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift, uint32_t rows_minus_one) {
    BLIT_SPRITE_ROWS_UNCLIPPED(image, src, dst, 2u, shift, rows_minus_one);
}

void sprite_blit_w64(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift, uint32_t rows_minus_one) {
    BLIT_SPRITE_ROWS_UNCLIPPED(image, src, dst, 3u, shift, rows_minus_one);
}

/* ---- the clip ladders -------------------------------------------------------------------------
 *
 * Each clipped blitter opens with a run of `cmp.w #<edge>,d4 / b<cc>` rungs; the first one the
 * sprite's final x satisfies names the group gate to install in `blit_clip_mask`, and two of them
 * also narrow the restore record the caller has just appended. A sprite past the last rung is not
 * drawn at all and the caller's restore cursor is rewound over that record.
 *
 * The rungs are transcribed rather than derived, because the right-hand ladders are NOT regular:
 * the two narrow classes rewrite the restore width where a right-edge clip leaves one or two groups
 * showing (`move.w #$4,-4(a5)` @ 0x14e10 and @ 0x14ef8, `move.w #$0,-4(a5)` @ 0x14ee0), and
 * classes 2 and 3 simply do not — so `sprite_blit_w48_clip_right` at x = 0x120 draws two of its
 * four groups and still restores all four, 16 bytes past the row's end into the left edge of the
 * row below, and at x = 0x130 it draws ONE and overruns by 24. That is the ORIGINAL's behaviour and
 * is reproduced, not repaired (`../STATUS.md`).
 */
/* `-4(a5)`: the cursor points one record PAST the one render_frame has just appended, so the class
 * word of that record is four bytes behind it. */
#define PENDING_RESTORE_CLASS_BACK (SPRITE_RESTORE_REC_BYTES - SPRITE_RESTORE_CLASS)

typedef struct {
    int16_t x_limit;        /* the `cmp.w` immediate, exactly as the instruction spells it */
    uint8_t group_gate;     /* the byte the rung stores in blit_clip_mask */
    int16_t restore_class;  /* the width class it rewrites into the pending restore record... */
} SpriteClipRung;

typedef struct {
    const SpriteClipRung *rung;
    unsigned rungs;
} SpriteClipLadder;

/* Which comparison walks the ladder. It is a property of WHICH TABLE the ladder came out of, so it
 * travels with the call rather than being copied into all eight table entries. */
typedef enum { CLIP_AT_LEFT_EDGE, CLIP_AT_RIGHT_EDGE } SpriteClipSide;

static const SpriteClipRung CLIP_LEFT_W16[] = {{-0x10, 0x01, RESTORE_CLASS_KEEP}};
static const SpriteClipRung CLIP_LEFT_W32[] = {{-0x10, 0x03, RESTORE_CLASS_KEEP},
                                               {-0x20, 0x01, RESTORE_CLASS_KEEP}};
static const SpriteClipRung CLIP_LEFT_W48[] = {{-0x10, 0x07, RESTORE_CLASS_KEEP},
                                               {-0x20, 0x03, RESTORE_CLASS_KEEP},
                                               {-0x30, 0x01, RESTORE_CLASS_KEEP}};
static const SpriteClipRung CLIP_LEFT_W64[] = {{-0x10, 0x0f, RESTORE_CLASS_KEEP},
                                               {-0x20, 0x07, RESTORE_CLASS_KEEP},
                                               {-0x30, 0x03, RESTORE_CLASS_KEEP},
                                               {-0x40, 0x01, RESTORE_CLASS_KEEP}};

static const SpriteClipRung CLIP_RIGHT_W16[] = {{0x130, 0x03, RESTORE_CLASS_KEEP},
                                                {0x140, 0x02, RESTORE_CLASS_W16}};
static const SpriteClipRung CLIP_RIGHT_W32[] = {{0x120, 0x07, RESTORE_CLASS_KEEP},
                                                {0x130, 0x06, 0},
                                                {0x140, 0x04, RESTORE_CLASS_W16}};
static const SpriteClipRung CLIP_RIGHT_W48[] = {{0x110, 0x0f, RESTORE_CLASS_KEEP},
                                                {0x120, 0x0e, RESTORE_CLASS_KEEP},
                                                {0x130, 0x0c, RESTORE_CLASS_KEEP},
                                                {0x140, 0x08, RESTORE_CLASS_KEEP}};
static const SpriteClipRung CLIP_RIGHT_W64[] = {{0x100, 0x1f, RESTORE_CLASS_KEEP},
                                                {0x110, 0x1e, RESTORE_CLASS_KEEP},
                                                {0x120, 0x1c, RESTORE_CLASS_KEEP},
                                                {0x130, 0x18, RESTORE_CLASS_KEEP},
                                                {0x140, 0x10, RESTORE_CLASS_KEEP}};

#define LADDER(rows) {(rows), (unsigned)(sizeof (rows) / sizeof *(rows))}

static const SpriteClipLadder CLIP_LEFT_LADDER[SPRITE_WIDTH_CLASSES] = {
    LADDER(CLIP_LEFT_W16), LADDER(CLIP_LEFT_W32), LADDER(CLIP_LEFT_W48), LADDER(CLIP_LEFT_W64),
};
static const SpriteClipLadder CLIP_RIGHT_LADDER[SPRITE_WIDTH_CLASSES] = {
    LADDER(CLIP_RIGHT_W16), LADDER(CLIP_RIGHT_W32), LADDER(CLIP_RIGHT_W48), LADDER(CLIP_RIGHT_W64),
};

static const SpriteClipRung *clip_rung(const SpriteClipLadder *ladder, SpriteClipSide side,
                                       int16_t x) {
    for (unsigned i = 0; i < ladder->rungs; i++) {
        const SpriteClipRung *rung = &ladder->rung[i];
        int taken = side == CLIP_AT_LEFT_EDGE ? (x >= rung->x_limit) : (x < rung->x_limit);
        if (taken)
            return rung;
    }
    return 0;   /* past the last rung: wholly off screen */
}

static uint32_t blit_sprite_clipped(uint8_t *image, const SpriteClipLadder *ladder,
                                    SpriteClipSide side, uint32_t src, uint32_t dst,
                                    unsigned width_class, uint32_t shift, uint32_t rows_minus_one,
                                    uint32_t x, uint32_t restore_cursor) {
    const SpriteClipRung *rung = clip_rung(ladder, side, (int16_t)x);

    if (!rung)   /* `subq.w #6,a5 / rts`: nothing drawn, and the restore record just appended is
                  * taken back — a full 32-bit subtract, as `subq` on an address register always is */
        return addr_sub(restore_cursor, SPRITE_RESTORE_REC_BYTES);

    image[A_blit_clip_mask] = rung->group_gate;
    if (rung->restore_class != RESTORE_CLASS_KEEP)
        wr16(image + addr_sub(restore_cursor, PENDING_RESTORE_CLASS_BACK),
             (uint16_t)rung->restore_class);

    blit_sprite_rows(image, src, dst, width_class, shift, rows_minus_one, SPRITE_GATE_CLIP_MASK);
    return restore_cursor;
}

#define DEFINE_CLIPPED_BLITTER(name, ladder, side, width_class)                                    \
    uint32_t name(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift,                      \
                  uint32_t rows_minus_one, uint32_t x, uint32_t restore_cursor) {                  \
        return blit_sprite_clipped(image, &(ladder)[width_class], (side), src, dst,                \
                                   (width_class), shift, rows_minus_one, x, restore_cursor);       \
    }

#define DEFINE_CLIP_LEFT_BLITTER(name, width_class)                                                \
    DEFINE_CLIPPED_BLITTER(name, CLIP_LEFT_LADDER, CLIP_AT_LEFT_EDGE, width_class)
#define DEFINE_CLIP_RIGHT_BLITTER(name, width_class)                                               \
    DEFINE_CLIPPED_BLITTER(name, CLIP_RIGHT_LADDER, CLIP_AT_RIGHT_EDGE, width_class)

DEFINE_CLIP_LEFT_BLITTER(sprite_blit_w16_clip_left,  0u)
DEFINE_CLIP_LEFT_BLITTER(sprite_blit_w32_clip_left,  1u)
DEFINE_CLIP_LEFT_BLITTER(sprite_blit_w48_clip_left,  2u)
DEFINE_CLIP_LEFT_BLITTER(sprite_blit_w64_clip_left,  3u)
DEFINE_CLIP_RIGHT_BLITTER(sprite_blit_w16_clip_right, 0u)
DEFINE_CLIP_RIGHT_BLITTER(sprite_blit_w32_clip_right, 1u)
DEFINE_CLIP_RIGHT_BLITTER(sprite_blit_w48_clip_right, 2u)
DEFINE_CLIP_RIGHT_BLITTER(sprite_blit_w64_clip_right, 3u)

/* ================================================================================================
 * The unrolled copy loops — restore_blit_w16..w80 @ 0x14d58..0x14db8 and scroll_wrap_copy_1280
 * @ 0x156ae. Each row is N `move.l (a0)+,(a1)+` and then a `lea` on both cursors that completes a
 * 160-byte screen row; the seam copy has no row structure at all and is one 320-byte run.
 * ============================================================================================= */

#define RESTORE_LONGS_W16  2u   /* 8 bytes = one 16-pixel group; `lea 152` closes the row */
#define RESTORE_LONGS_W32  4u   /* `lea 144` */
#define RESTORE_LONGS_W48  6u   /* `lea 136` */
#define RESTORE_LONGS_W64  8u   /* `lea 128` */
#define RESTORE_LONGS_W80 10u   /* `lea 120` */
static void restore_blit_rows(uint8_t *image, uint32_t src, uint32_t dst, uint32_t rows_minus_one,
                              unsigned longs_per_row) {
    unsigned rows = loop_passes(rows_minus_one + 1u, COUNT_MASK_WORD);

    for (unsigned row = 0; row < rows; row++) {
        copy_longs(image, src, dst, longs_per_row);
        src = addr_add(src, SCREEN_ROW_BYTES);
        dst = addr_add(dst, SCREEN_ROW_BYTES);
    }
}

void restore_blit_w16(uint8_t *image, uint32_t src, uint32_t dst, uint32_t rows_minus_one) {
    restore_blit_rows(image, src, dst, rows_minus_one, RESTORE_LONGS_W16);
}

void restore_blit_w32(uint8_t *image, uint32_t src, uint32_t dst, uint32_t rows_minus_one) {
    restore_blit_rows(image, src, dst, rows_minus_one, RESTORE_LONGS_W32);
}

void restore_blit_w48(uint8_t *image, uint32_t src, uint32_t dst, uint32_t rows_minus_one) {
    restore_blit_rows(image, src, dst, rows_minus_one, RESTORE_LONGS_W48);
}

void restore_blit_w64(uint8_t *image, uint32_t src, uint32_t dst, uint32_t rows_minus_one) {
    restore_blit_rows(image, src, dst, rows_minus_one, RESTORE_LONGS_W64);
}

void restore_blit_w80(uint8_t *image, uint32_t src, uint32_t dst, uint32_t rows_minus_one) {
    restore_blit_rows(image, src, dst, rows_minus_one, RESTORE_LONGS_W80);
}

void scroll_wrap_copy_1280(uint8_t *image, uint32_t src, uint32_t dst) {
    copy_longs(image, src, dst, SCROLL_WRAP_COPY_LONGS);
}

/* ================================================================================================
 * The two tile paths — tile_blit_overlay_masked @ 0x14d0a and the overlay repaint inside
 * render_frame @ 0x14642. Both merge an overlay tile with colour 0 transparent; the first lays an
 * opaque base tile down first, the second merges over whatever the screen already holds.
 * ============================================================================================= */

/* `move.w d0,d6 / or.w d1,d6 / or.w d2,d6 / or.w d5,d6 / not.w d6`: a pixel of the overlay is
 * transparent exactly where all four of its planes are 0, so the OR of the four planes is where the
 * overlay paints and its complement is where the background survives. */
static uint16_t overlay_keep_mask(const uint16_t plane[SPRITE_PLANES]) {
    uint16_t painted = 0;

    for (unsigned p = 0; p < SPRITE_PLANES; p++)
        painted = (uint16_t)(painted | plane[p]);
    return (uint16_t)~painted;
}

static void read_planes(const uint8_t *image, uint32_t src, uint16_t plane[SPRITE_PLANES]) {
    for (unsigned p = 0; p < SPRITE_PLANES; p++)
        plane[p] = be16(image + addr_add(src, p * 2u));
}

static void merge_plane_words(uint8_t *image, uint32_t dst, const uint16_t plane[SPRITE_PLANES],
                              uint16_t keep) {
    for (unsigned p = 0; p < SPRITE_PLANES; p++)
        merge_plane_word(image, addr_add(dst, p * 2u), plane[p], keep);
}

/* One tile's worth of rows merged over whatever the screen already holds — the overlay repaint's
 * inner pair of loops @ 0x14642, factored out of `repaint_overlay_tiles` so that the clip
 * arithmetic above it reads on its own.
 *
 * SEPARATE FROM `tile_blit_overlay_masked` BELOW ON PURPOSE, though both merge with colour 0
 * transparent. That one lays an opaque base tile down FIRST and interleaves the two operations —
 * `move.l (a0)+,(a2)` and then the mask-and-merge of the two words it just wrote, twice — because
 * its base source may overlap the screen it is writing to, so the order of the stores is part of
 * the behaviour. This one has no base tile and no such order to preserve. Folding them together
 * would have to reproduce that interleaving anyway, under a flag, in a routine neither caller
 * would then read straight through. */
static void merge_overlay_tile_rows(uint8_t *image, uint32_t src, uint32_t dst, unsigned rows) {
    for (unsigned row = 0; row < rows; row++) {
        for (unsigned group = 0; group < TILE_ROW_GROUPS; group++) {
            uint16_t plane[SPRITE_PLANES];

            read_planes(image, src, plane);
            merge_plane_words(image, addr_add(dst, group * SCREEN_GROUP_BYTES), plane,
                              overlay_keep_mask(plane));
            src = addr_add(src, SPRITE_PLANES * 2u);
        }
        dst = addr_add(dst, SCREEN_ROW_BYTES);
    }
}

/* Two planes at a time, because the base tile arrives as two longwords: the original writes one
 * (`move.l (a0)+,(a2)`) and immediately masks and merges the two words it just laid down, then does
 * the same with the second. Spelt in that order because the base source may overlap the screen. */
#define PLANES_PER_LONG 2u

void tile_blit_overlay_masked(uint8_t *image, uint32_t base_src, uint32_t overlay_src, uint32_t dst,
                              uint32_t rows_minus_one) {
    unsigned rows = loop_passes(rows_minus_one + 1u, COUNT_MASK_WORD);

    for (unsigned row = 0; row < rows; row++) {
        for (unsigned group = 0; group < TILE_ROW_GROUPS; group++) {
            uint32_t screen = addr_add(dst, group * SCREEN_GROUP_BYTES);
            uint16_t plane[SPRITE_PLANES];
            uint16_t keep;

            read_planes(image, overlay_src, plane);
            keep = overlay_keep_mask(plane);
            for (unsigned half = 0; half < SPRITE_PLANES / PLANES_PER_LONG; half++) {
                uint32_t pair = addr_add(screen, half * LONG_BYTES);

                wr32(image + pair, be32(image + addr_add(base_src, half * LONG_BYTES)));
                merge_plane_word(image, pair, plane[half * PLANES_PER_LONG], keep);
                merge_plane_word(image, addr_add(pair, 2u), plane[half * PLANES_PER_LONG + 1u], keep);
            }
            base_src = addr_add(base_src, SPRITE_PLANES * 2u);
            overlay_src = addr_add(overlay_src, SPRITE_PLANES * 2u);
        }
        dst = addr_add(dst, SCREEN_ROW_BYTES);
    }
}

/* ================================================================================================
 * render_frame @ 0x14446, phase by phase.
 * ============================================================================================= */

/* ---- phase 1: the circular seam ---------------------------------------------------------------
 * The shifter reads straight across the ring's wrap, so whenever the draw base sits in the ring's
 * bottom frame the eight rows above the ring's top have to hold the eight at the draw base: four
 * calls of 80 longwords each, 1280 bytes.
 * `cmpa.l a1,a0 / bge` @ 0x14458 is a SIGNED long compare of the draw base against ring_base +
 * one frame. */
static void copy_ring_seam(uint8_t *image) {
    uint32_t draw = be32(image + A_screen_draw);
    uint32_t seam_limit = addr_add(be32(image + A_screen_ring_base), SCREEN_BYTES);
    uint32_t src = draw;
    uint32_t dst;

    if ((int32_t)draw >= (int32_t)seam_limit)
        return;

    dst = addr_add(draw, SCREEN_RING_BYTES);
    for (unsigned call = 0; call < SCROLL_WRAP_COPY_CALLS; call++) {
        scroll_wrap_copy_1280(image, src, dst);
        src = addr_add(src, SCROLL_WRAP_COPY_LONGS * LONG_BYTES);
        dst = addr_add(dst, SCROLL_WRAP_COPY_LONGS * LONG_BYTES);
    }
}

/* ---- phase 2/4: the two display-list passes ---------------------------------------------------
 *
 * The same 90 instructions twice, at 0x1449e and 0x146ae, differing in three things: which active
 * bytes the pass takes, where its right-edge clip starts, and whether it marks the tile repair
 * grid. Pass A draws under the scenery and pass B on top of it.
 */
typedef enum { DRAW_PASS_UNDER_SCENERY, DRAW_PASS_ON_TOP } DrawPass;

/* Pass A clips right from `cmp.w #$110,d4 / blt` @ 0x145a2; pass B from `cmp.w #$f0,d4 / ble`
 * @ 0x14742 — one is `>=` and the other `>`, which is the original's own asymmetry. */
#define PASS_A_CLIP_RIGHT_FROM_X 0x110
#define PASS_B_CLIP_RIGHT_AFTER_X 0x0f0

static int pass_draws(DrawPass pass, uint8_t active) {
    if (pass == DRAW_PASS_UNDER_SCENERY)
        return (active & DISPLAY_ACTIVE_PASS_A_BIT) != 0;   /* `tst.b 5(a6) / bpl` -> skip */
    /* `bmi` -> skip, then `beq` -> skip: 0x01..0x7f and nothing else */
    return active != DISPLAY_ACTIVE_HIDDEN && (active & DISPLAY_ACTIVE_PASS_A_BIT) == 0;
}

static int pass_clips_right(DrawPass pass, int16_t x) {
    return pass == DRAW_PASS_UNDER_SCENERY ? (x >= PASS_A_CLIP_RIGHT_FROM_X)
                                           : (x > PASS_B_CLIP_RIGHT_AFTER_X);
}

/* One cell's overlay tile id, copied out of the map into the repair grid at the same word index.
 * `move.b 1(a3,d0.w),1(a2,d0.w)` and its three neighbours @ 0x14550..0x14576: the displacement is
 * the overlay byte plus however many cells right and rows down the neighbour is. */
static void copy_overlay_id_to_repair_grid(uint8_t *image, uint32_t map_cursor, int16_t cell_index,
                                           unsigned cells_right, unsigned rows_down) {
    uint32_t displacement = MAP_CELL_OVERLAY + cells_right * MAP_CELL_BYTES
                            + rows_down * MAP_ROW_BYTES;
    uint32_t index = addr_add(sign_ext16((uint16_t)cell_index), displacement);

    image[addr_add(A_tile_repair_grid, index)] = image[addr_add(map_cursor, index)];
}

/* Pass A only: remember the overlay tiles of the up-to-four map cells this sprite lands on, so the
 * repaint that follows puts the scenery back over it. */
static void mark_tile_repair_cells(uint8_t *image, int16_t x, int16_t y) {
    uint16_t scroll_fine = be16(image + A_scroll_fine);
    uint32_t map_cursor = be32(image + A_map_row_ptr);
    /* The cell the sprite's top-left corner is in. The row is an UNSIGNED shift of y biased by one
     * tile (`addi.w #$20,d0 / sub.w scroll_fine,d0 / lsr.w #5,d0`); the column is a SIGNED one of
     * x, so a sprite clipped off the left edge names column -1 and the index below goes backwards.
     * That is the original's arithmetic and the grid write really does land before the grid. */
    uint16_t row = (uint16_t)((uint16_t)(y + (int16_t)TILE_PIXELS - (int16_t)scroll_fine)
                              >> TILE_INDEX_SHIFT);
    int16_t column = asr16(x, TILE_INDEX_SHIFT);
    int16_t cell_index = (int16_t)((int16_t)(row * TILE_REPAIR_COLUMNS + column) * MAP_CELL_BYTES);
    int spans_next_column = (x & (int16_t)(TILE_PIXELS - 1u)) != 0;
    int spans_next_row = ((y - (int16_t)scroll_fine) & (int16_t)(TILE_PIXELS - 1u)) != 0;

    copy_overlay_id_to_repair_grid(image, map_cursor, cell_index, 0u, 0u);
    if (spans_next_column)
        copy_overlay_id_to_repair_grid(image, map_cursor, cell_index, 1u, 0u);
    if (spans_next_row) {
        copy_overlay_id_to_repair_grid(image, map_cursor, cell_index, 0u, 1u);
        if (spans_next_column)
            copy_overlay_id_to_repair_grid(image, map_cursor, cell_index, 1u, 1u);
    }
}

/* ---- the blitter jump tables are ONE run of longwords ------------------------------------------
 *
 * `lea <table>,a2 / lsl.w #2,d2 / adda.w d2,a2 / movea.l (a2),a2 / jsr (a2)` @ 0x14592..0x145b4:
 * the dispatch picks one of three tables by the sprite's x and indexes it by the width class WITH
 * NO BOUND. Those three sit back to back in DATA — `A_sprite_blit_tbl` @ 0x16396,
 * `A_sprite_blit_clip_left_tbl` @ 0x163a6, `A_sprite_blit_clip_right_tbl` @ 0x163b6, four
 * longwords each, with `A_restore_blit_tbl` @ 0x163c6 behind them — so a class of 4 does not run
 * off a table. It lands on the FIRST ENTRY OF THE NEXT ONE and the machine draws a real, wrong
 * sprite through the registers this dispatch has already set.
 *
 * All 256 shipped records hold 0..3, so nothing in the game reaches it, and it is MODELLED rather
 * than asserted away for two reasons: a host array indexed at 4 is undefined behaviour, which
 * neither the byte diff nor `make guarded` can see; and the model costs one flat table, because the
 * twelve entries of the three tables differ only in which clip ladder they carry. Index = table
 * base + class is then the whole dispatch, exactly as the `adda.w` is. `test_sprite.py`'s class-4
 * case is what separates this from a bounds check. */
typedef struct {
    const SpriteClipLadder *ladder;   /* 0 for the four unclipped entries, which have no `btst` */
    SpriteClipSide side;              /* meaningless without a ladder, as the entry itself is */
    unsigned width_class;
} SpriteBlitEntry;

#define SPRITE_BLIT_TBL_PLAIN       0u  /* A_sprite_blit_tbl @ 0x16396 */
#define SPRITE_BLIT_TBL_CLIP_LEFT   4u  /* A_sprite_blit_clip_left_tbl @ 0x163a6 */
#define SPRITE_BLIT_TBL_CLIP_RIGHT  8u  /* A_sprite_blit_clip_right_tbl @ 0x163b6 */
#define SPRITE_BLIT_TBL_RESTORE    12u  /* A_restore_blit_tbl @ 0x163c6 — a DIFFERENT family, so
                                         * the flat table stops here and its first entry is an arm */

#define PLAIN_ENTRY(klass)      {0, CLIP_AT_LEFT_EDGE, (klass)}
#define CLIP_LEFT_ENTRY(klass)  {&CLIP_LEFT_LADDER[klass], CLIP_AT_LEFT_EDGE, (klass)}
#define CLIP_RIGHT_ENTRY(klass) {&CLIP_RIGHT_LADDER[klass], CLIP_AT_RIGHT_EDGE, (klass)}

static const SpriteBlitEntry SPRITE_BLIT_TABLE[SPRITE_BLIT_TBL_RESTORE] = {
    PLAIN_ENTRY(0u), PLAIN_ENTRY(1u), PLAIN_ENTRY(2u), PLAIN_ENTRY(3u),
    CLIP_LEFT_ENTRY(0u), CLIP_LEFT_ENTRY(1u), CLIP_LEFT_ENTRY(2u), CLIP_LEFT_ENTRY(3u),
    CLIP_RIGHT_ENTRY(0u), CLIP_RIGHT_ENTRY(1u), CLIP_RIGHT_ENTRY(2u), CLIP_RIGHT_ENTRY(3u),
};

static uint32_t dispatch_sprite_blit(uint8_t *image, DrawPass pass, unsigned width_class,
                                     uint32_t src, uint32_t dst, uint32_t shift,
                                     uint32_t rows_minus_one, int16_t x, uint32_t restore_cursor) {
    unsigned table = x < 0                 ? SPRITE_BLIT_TBL_CLIP_LEFT
                   : pass_clips_right(pass, x) ? SPRITE_BLIT_TBL_CLIP_RIGHT
                                               : SPRITE_BLIT_TBL_PLAIN;
    unsigned index = table + width_class;
    const SpriteBlitEntry *entry;

    if (index == SPRITE_BLIT_TBL_RESTORE) {
        /* The clip-RIGHT table at class 4: `A_restore_blit_tbl`'s first entry, `restore_blit_w32`
         * @ 0x14d58, entered with the same A0/A1/D7 — an unmasked eight-byte-a-row COPY where a
         * masked blit was meant, and it leaves the restore cursor alone. */
        restore_blit_rows(image, src, dst, rows_minus_one, RESTORE_LONGS_W32);
        return restore_cursor;
    }
#ifdef RECREATE_HOST_DIFFERENTIAL
    /* Class 5 and above walks on into the restore table's LATER entries, whose signatures differ
     * again. No sprite record in the bank holds one and no case pokes one, so the model stops at
     * the one adjacency the class the bank could plausibly grow reaches. HOST-ONLY, the way the kit
     * prescribes (kit.mk: "asserted where there is a process to abort"). */
    assert(index < SPRITE_BLIT_TBL_RESTORE);
#endif
    entry = &SPRITE_BLIT_TABLE[index];
    if (!entry->ladder) {
        BLIT_SPRITE_ROWS_UNCLIPPED(image, src, dst, entry->width_class, shift, rows_minus_one);
        return restore_cursor;
    }
    return blit_sprite_clipped(image, entry->ladder, entry->side, src, dst, entry->width_class,
                               shift, rows_minus_one, (uint32_t)(uint16_t)x, restore_cursor);
}

static uint32_t draw_display_list_pass(uint8_t *image, DrawPass pass, uint32_t restore_cursor) {
    for (uint32_t record = A_display_list; record < A_display_list_end;
         record = addr_add(record, DISPLAY_REC_BYTES)) {
        uint32_t sprite_rec, src, screen, dst;
        int16_t rows_minus_one, x, y, screen_offset;
        uint16_t width_class;
        unsigned shift;

        if (!pass_draws(pass, image[record + DISPLAY_REC_ACTIVE]))
            continue;

        sprite_rec = addr_add(A_sprite_bank,
                              (uint16_t)(image[record + DISPLAY_REC_FRAME] * SPRITE_RECORD_BYTES));
        rows_minus_one = (int16_t)be16(image + sprite_rec + SPRITE_REC_ROWS);
        src = be32(image + sprite_rec + SPRITE_REC_DATA);
        width_class = be16(image + sprite_rec + SPRITE_REC_WIDTH_CLASS);
        /* The class comes out of A\SPRITES.cru, which is loaded at run time, so the image cannot
         * prove its range — and it is NOT bounded here, because the original does not bound it
         * either: `dispatch_sprite_blit` models what a class of 4 really reaches. */
        y = (int16_t)(be16(image + record + DISPLAY_REC_Y)
                      + be16(image + sprite_rec + SPRITE_REC_DRAW_DY));

        if (y < 0) {
            /* Clipped at the top: fewer rows, and the source skips the hidden ones. The stride is
             * `(class + 1) * 10` (`mulu.w #$a`), and `muls.w d1,d0 / suba.l d0,a0` subtracts a
             * NEGATIVE product, which is how a subtract advances the cursor. */
            uint16_t row_stride = (uint16_t)((uint16_t)(width_class + 1u) * SPRITE_GROUP_BYTES);

            rows_minus_one = (int16_t)(rows_minus_one + y);
            if (rows_minus_one < 0)
                continue;
            src = addr_add(src, (uint32_t)-((int32_t)(int16_t)row_stride * (int32_t)y));
            y = 0;
        } else {
            int16_t room_below;

            if (y > (int16_t)SCREEN_LAST_ROW)
                continue;
            room_below = (int16_t)((int16_t)SCREEN_LAST_ROW - y);
            if (room_below < rows_minus_one)
                rows_minus_one = room_below;
        }

        screen = be32(image + A_screen_draw);
        x = (int16_t)(be16(image + record + DISPLAY_REC_X)
                      + be16(image + sprite_rec + SPRITE_REC_DRAW_DX));
        shift = (unsigned)(x & (int16_t)(GROUP_PIXELS - 1u));
        /* `andi.w #$fff0 / asr.w #1` is the byte offset of the 16-pixel group, and `asl.w #5 / add /
         * asl.w #2 / add` is y * 160 — all WORD arithmetic, so the offset wraps at 16 bits and is
         * added to the screen base sign-extended (`adda.w d0,a1`). */
        screen_offset = (int16_t)(asr16((int16_t)(x & (int16_t)~(GROUP_PIXELS - 1u)), 1)
                                  + (int16_t)(y * (int16_t)SCREEN_ROW_BYTES));
        dst = addr_add(screen, sign_ext16((uint16_t)screen_offset));

        wr16(image + restore_cursor + SPRITE_RESTORE_OFFSET, (uint16_t)screen_offset);
        wr16(image + restore_cursor + SPRITE_RESTORE_CLASS, width_class);
        wr16(image + restore_cursor + SPRITE_RESTORE_ROWS, (uint16_t)rows_minus_one);
        restore_cursor = addr_add(restore_cursor, SPRITE_RESTORE_REC_BYTES);

        if (pass == DRAW_PASS_UNDER_SCENERY)
            mark_tile_repair_cells(image, x, y);

        restore_cursor = dispatch_sprite_blit(image, pass, width_class, src, dst, shift,
                                              (uint32_t)(uint16_t)rows_minus_one, x, restore_cursor);
    }
    return restore_cursor;
}

/* ---- phase 3: the overlay repaint @ 0x145c4 ---------------------------------------------------
 *
 * Drain the repair grid: every non-zero word names an overlay tile to paint back over the pass-A
 * sprites, clearing the word as it goes. The grid cursor runs STRAIGHT THROUGH the whole grid — it
 * is not reset per row — and the row loop walks the tile rows down the screen, clipping the first
 * against the top and the last against the bottom.
 */
#define TILE_REPAIR_BOTTOM_CLIP_FROM_Y 0xa8  /* `cmpi.w #$a8,d1 / ble` @ 0x1461c */
#define TILE_REPAIR_ROWS_AT_TOP         7u   /* `move.w #$7,d7` — the rows left below y = 0xa8... */
#define TILE_REPAIR_ROWS_WRAPPED      0x27u  /* ...and `move.w #$27,d7` once the phase has wrapped */
#define TILE_REPAIR_PHASE_WRAP          8u   /* `cmpi.w #$8,scroll_fine / blt` picks between them */

static void repaint_overlay_tiles(uint8_t *image) {
    uint16_t scroll_fine = be16(image + A_scroll_fine);
    uint32_t grid = A_tile_repair_grid;
    int16_t tile_y = (int16_t)(scroll_fine - TILE_PIXELS);

    do {
        for (unsigned column_byte = 0; column_byte < TILE_REPAIR_ROW_BYTES;
             column_byte += MAP_CELL_BYTES) {   /* `addq.w #2,d0 / cmpi.w #$14,d0` @ 0x14686 */
            uint32_t entry = grid;
            uint16_t tile = be16(image + entry);
            uint32_t src, dst;
            uint16_t rows_minus_one;
            unsigned rows;

            grid = addr_add(grid, MAP_CELL_BYTES);   /* `move.w (a0)+,d2` — always, tile or none */
            if (tile == 0)
                continue;
            wr16(image + entry, 0);                  /* `clr.w -2(a0)` */

            src = addr_add(A_tile_banks, tile * TILE_BYTES);
            dst = addr_add(be32(image + A_screen_draw),
                           column_byte / MAP_CELL_BYTES * TILE_BAND_COLUMN_BYTES);
            rows_minus_one = (uint16_t)(TILE_PIXELS - 1u);   /* `move.w #$1f,d7` @ 0x145ee */

            if (tile_y < 0) {
                /* The top tile row is cut by the scroll phase, and its source starts that far in.
                 * `move.w scroll_fine,d7 / subq.w #1,d7 / bmi` @ 0x14602 is what drops a phase of
                 * 0 — a whole tile row above the screen has nothing of itself to show. The test is
                 * on the DECREMENTED word, so it is not "scroll_fine <= 0": a phase of 0x8000
                 * leaves 0x7fff and paints 32,768 rows. */
                rows_minus_one = (uint16_t)(scroll_fine - 1u);
                if ((int16_t)rows_minus_one < 0)
                    continue;
                /* `move.w #$20,d3 / sub.w scroll_fine,d3 / lsl.w #4,d3 / adda.w d3,a2` — a WORD
                 * product sign-extended into the address. */
                src = addr_add(src, sign_ext16((uint16_t)((TILE_PIXELS - scroll_fine)
                                                          * TILE_ROW_BYTES)));
            } else {
                if (tile_y > TILE_REPAIR_BOTTOM_CLIP_FROM_Y) {
                    /* The bottom row is cut to what is left below y = 0xa8:
                     * `move.w #$7,d7 / cmpi.w #$8,scroll_fine / blt / move.w #$27,d7 /
                     *  sub.w scroll_fine,d7` @ 0x14622.
                     *
                     * TWO THINGS THE SHAPE HIDES, both reachable only from a scroll phase the game
                     * itself never reaches (`advance_scroll` keeps it in 0..0x1f) and both pinned
                     * as contract-coverage cases. The compare is `blt`, so it is SIGNED — a phase
                     * of 0xffff picks the SMALLER constant, not the larger. And the difference has
                     * NO guard before the `dbf`, so a phase past the chosen constant wraps the
                     * count to a whole 65,536-row pass rather than painting nothing. */
                    uint16_t last = (int16_t)scroll_fine < (int16_t)TILE_REPAIR_PHASE_WRAP
                                    ? TILE_REPAIR_ROWS_AT_TOP : TILE_REPAIR_ROWS_WRAPPED;
                    rows_minus_one = (uint16_t)(last - scroll_fine);
                }
                dst = addr_add(dst, sign_ext16((uint16_t)(tile_y * (int16_t)SCREEN_ROW_BYTES)));
            }

            rows = loop_passes(rows_minus_one + 1u, COUNT_MASK_WORD);   /* `dbf d7` @ 0x14682 */
            merge_overlay_tile_rows(image, src, dst, rows);
        }
        tile_y = (int16_t)(tile_y + (int16_t)TILE_PIXELS);
    } while (tile_y < (int16_t)SCREEN_LAST_ROW);
}

/* ---- phase 5: publish the frame and spend the rest of its budget ------------------------------ */
#define SETSCREEN_UNCHANGED 0xffffffffu  /* the -1 the game passes for the LOGICAL base... */
#define SETSCREEN_KEEP_RESOLUTION (-1)   /* ...and for the resolution */

/* The VBL counter has to be read afresh every time round the wait, because on an Atari it is the
 * level-4 handler and not this code that moves it. That is the whole reason this spells out what
 * the kit's `be32` already does: `be32` takes a plain `const uint8_t *`, so an optimiser is free to
 * hoist it out of the loop below and spin on a value that can never change. The `volatile` view is
 * the point, not the byte order. */
static int32_t vbl_tick_now(const uint8_t *image) {
    const volatile uint8_t *counter = image + A_vbl_tick;

    return (int32_t)(((uint32_t)counter[0] << 24) | ((uint32_t)counter[1] << 16)
                     | ((uint32_t)counter[2] << 8) | (uint32_t)counter[3]);
}

/* `move.l $17720.l,d1` @ 0x1479c — the instruction the original's wait RE-READS the counter at, and
 * therefore the wait site both shores key their clocks to (`sched.h`, "EVERY POLL NAMES ITS WAIT
 * SITE"). The `cmpi.l` two instructions on re-reads it as well; the site is the FIRST read of the
 * iteration, because the agent's store lands just before the site's instruction on both sides. */
#define RENDER_FRAME_VBL_WAIT_PC 0x1479cu

static void publish_and_wait(uint8_t *image) {
    os_setscreen(SETSCREEN_UNCHANGED, be32(image + A_screen_draw), SETSCREEN_KEEP_RESOLUTION);

    /* The gate at 0x14786 is a read at its OWN pc, not part of the wait, so it is not a poll
     * (`sched.h`, "a guard that reads the same address BEFORE the loop is not a poll"). */
    if (vbl_tick_now(image) >= (int32_t)RENDER_FRAME_VBL_BUDGET) {
        os_vsync();
    } else {
        /* The frame came in under budget: spin until the level-4 handler has counted the third VBL.
         * Nothing inside this program writes the counter, so the wait goes through the kit's
         * SCHEDULED WRITE model — ONE poll an iteration is the clock, and the case's store lands
         * just before the poll that brings it due. `sched_poll32` because the compare is a LONG;
         * what the wrapper adds over a hand-rolled poll-and-read is the CAP, without which a case
         * whose schedule never comes due HANGS here instead of being refused (measured:
         * `RENDER_FRAME_VBL_BUDGET` mutated to 4 hung the whole suite against that pair). */
        uint32_t tick;

        while (sched_poll32(image, A_vbl_tick, RENDER_FRAME_VBL_WAIT_PC, &tick)) {
            if ((int32_t)tick >= (int32_t)RENDER_FRAME_VBL_BUDGET)
                break;
        }
    }
    wr32(image + A_vbl_tick, 0);
}

/* ---- phase 6: advance the scroll and rotate the four screens @ 0x147ba ------------------------ */
#define SCROLL_FINE_STEP    2u     /* `addq.w #2,$16430` — two pixels a frame */
#define SCROLL_FINE_MASK 0x1fu     /* `andi.w #$1f`: 0,2,...,30 over sixteen frames */
#define SCREEN_STEP_BYTES 0x500u   /* `subi.l #$500,(a0)` — eight scanlines, four frames of scroll */

static void advance_scroll(uint8_t *image) {
    uint16_t scroll_fine = (uint16_t)((be16(image + A_scroll_fine) + SCROLL_FINE_STEP)
                                      & SCROLL_FINE_MASK);
    uint16_t index;
    uint32_t slot, base;

    wr16(image + A_scroll_fine, scroll_fine);
    if (scroll_fine == 0) {
        /* One whole map row of scroll has gone by. The RESET ARM IS DEAD: 0x147da is a `nop` where
         * the bound test used to be, so the store it guarded at 0x147dc always runs and is always
         * overwritten two instructions later. Both stores are spelt out because both really happen;
         * only the second is ever read. */
        uint32_t stepped = addr_sub(be32(image + A_map_row_ptr), MAP_ROW_BYTES);

        wr32(image + A_map_row_ptr, be32(image + A_map_row_ptr_reset));
        wr32(image + A_map_row_ptr, stepped);
    }

    index = (uint16_t)((be16(image + A_screen_ring_index) + 1u) & (SCREEN_RING_SLOTS - 1u));
    wr16(image + A_screen_ring_index, index);

    slot = addr_add(A_screen_ring, index * (uint16_t)LONG_BYTES);
    base = addr_sub(be32(image + slot), SCREEN_STEP_BYTES);
    /* `cmpa.l (a0),a1 / blt` keeps the stepped base while ring_base is still BELOW it; otherwise the
     * slot is reseated a whole ring above the ring's low limit — not wrapped by adding to itself. */
    if ((int32_t)be32(image + A_screen_ring_base) >= (int32_t)base)
        base = addr_add(be32(image + A_screen_ring_base), SCREEN_RING_BYTES);
    wr32(image + slot, base);

    wr32(image + A_screen_prev2, be32(image + A_screen_prev1));
    wr32(image + A_screen_prev1, be32(image + A_screen_draw));
    wr32(image + A_screen_draw, base);
}

/* ---- phase 7: the newly exposed 8-scanline tile band @ 0x1483a --------------------------------
 *
 * Ten columns. Each takes the LAST `upper_rows` rows of the tile the map cursor names and the FIRST
 * `lower_rows` rows of the tile one map row on, the pair coming from tile_split_row_table and always
 * summing to TILE_BAND_ROWS. Where either cell carries an overlay the merge path runs instead of the
 * plain copy.
 */
static uint32_t tile_address(uint8_t tile) {
    return addr_add(A_tile_banks, tile * TILE_BYTES);
}

/* The address of the row `scroll_fine` rows up from the END of a tile — where a column's upper half
 * starts. `adda.w #$200,a0` then `lsl.w #4 / suba.w d0,a0` @ 0x14874. */
static uint32_t tile_bottom_rows(uint32_t tile, uint16_t scroll_fine) {
    return addr_sub(addr_add(tile, TILE_BYTES), (uint16_t)(scroll_fine * TILE_ROW_BYTES));
}

/* `subq.b #1,dN / bmi` on the split table's byte: the half is skipped when the decrement goes
 * negative AS A BYTE, which is a count of 0 and equally one of 0x81..0xff, and otherwise the
 * decremented byte is the `dbf` count. The shipped table holds only 0..8, so only the zero arm is
 * live — transcribed as the byte test the instruction is rather than as `!= 0`. */
static int tile_half_dbf_count(unsigned count, unsigned *rows_minus_one) {
    uint8_t stepped = (uint8_t)(count - 1u);

    if (stepped & 0x80u)
        return 0;
    *rows_minus_one = stepped;
    return 1;
}

static uint32_t copy_tile_rows(uint8_t *image, uint32_t src, uint32_t dst, unsigned rows) {
    for (unsigned row = 0; row < rows; row++) {
        copy_longs(image, src, dst, TILE_ROW_BYTES / LONG_BYTES);
        src = addr_add(src, TILE_ROW_BYTES);
        dst = addr_add(dst, SCREEN_ROW_BYTES);
    }
    return dst;
}

static void draw_exposed_tile_band(uint8_t *image) {
    uint32_t map_cursor = be32(image + A_map_row_ptr);
    uint32_t dst = be32(image + A_screen_draw);

    for (unsigned column = 0; column < MAP_COLUMNS; column++) {
        uint16_t scroll_fine = be16(image + A_scroll_fine);
        uint32_t split = addr_add(A_tile_split_row_table, scroll_fine);
        /* `subq.b #1,d3 / bmi` skips a half whose count is zero, so a count of 0 means no rows. */
        unsigned lower_rows = image[split];
        unsigned upper_rows = image[split + 1];
        uint32_t lower_cell = addr_add(map_cursor, MAP_ROW_BYTES);
        uint32_t upper_src = tile_bottom_rows(tile_address(image[map_cursor]), scroll_fine);
        uint32_t lower_src = tile_address(image[lower_cell]);
        uint8_t overlays = (uint8_t)(image[map_cursor + MAP_CELL_OVERLAY]
                                     | image[lower_cell + MAP_CELL_OVERLAY]);
        uint32_t row_dst = dst;
        unsigned rows_minus_one;

        if (overlays == 0) {
            if (tile_half_dbf_count(upper_rows, &rows_minus_one))
                row_dst = copy_tile_rows(image, upper_src, row_dst, rows_minus_one + 1u);
            if (tile_half_dbf_count(lower_rows, &rows_minus_one))
                row_dst = copy_tile_rows(image, lower_src, row_dst, rows_minus_one + 1u);
        } else {
            uint32_t upper_overlay =
                tile_bottom_rows(tile_address(image[map_cursor + MAP_CELL_OVERLAY]), scroll_fine);
            uint32_t lower_overlay = tile_address(image[lower_cell + MAP_CELL_OVERLAY]);

            if (tile_half_dbf_count(upper_rows, &rows_minus_one)) {
                tile_blit_overlay_masked(image, upper_src, upper_overlay, row_dst, rows_minus_one);
                row_dst = addr_add(row_dst, (rows_minus_one + 1u) * SCREEN_ROW_BYTES);
            }
            if (tile_half_dbf_count(lower_rows, &rows_minus_one)) {
                tile_blit_overlay_masked(image, lower_src, lower_overlay, row_dst, rows_minus_one);
                row_dst = addr_add(row_dst, (rows_minus_one + 1u) * SCREEN_ROW_BYTES);
            }
        }

        map_cursor = addr_add(map_cursor, MAP_CELL_BYTES);
        /* `lea -1264(a2),a2` — applied to the cursor THE TWO HALVES LEFT, not to the band's top.
         * That is only the same thing while the split pair sums to TILE_BAND_ROWS: the pair is read
         * out of a table indexed by the scroll phase, and every phase the game can hold is even and
         * every even entry sums to 8. At an ODD phase the pair sums to 6 and the original's next
         * column starts 304 bytes BELOW this one — reproduced, and `test_sprite.py`'s odd-phase case
         * is what separates it (contract coverage; ../STATUS.md says the game cannot reach it). */
        dst = addr_sub(row_dst, TILE_BAND_COLUMN_BACKSTEP);
    }
}

/* ---- phase 8: replay the restore list written two frames ago @ 0x14912 ------------------------ */
#define RESTORE_SOURCE_SKEW 0x280u  /* `adda.w #$280,a0` — the four scanlines of scroll between the
                                     * buffer being drawn and the one being repaired, so the same
                                     * world content is copied onto the same place */
#define RESTORE_LIST_LOOKBACK 2u    /* `subq.w #2,d0` on the ring index */

static void restore_blit(uint8_t *image, uint16_t width_class, uint32_t src, uint32_t dst,
                         uint32_t rows_minus_one) {
    static const unsigned longs[RESTORE_BLIT_TABLE_ENTRIES] = {
        RESTORE_LONGS_W32, RESTORE_LONGS_W48, RESTORE_LONGS_W64, RESTORE_LONGS_W80,
        RESTORE_LONGS_W16,
    };

#ifdef RECREATE_HOST_DIFFERENTIAL
    /* A class the five-entry table cannot answer would fetch a longword of neighbouring DATA and
     * `jsr` through it, and here it would index a host array off its end — invisible to the byte
     * diff AND to `make guarded`, which bounds the image and not the candidate's own stack. Only
     * render_frame's own two writers put a class here — a sprite record's 0..3, or the 4 a
     * right-edge clip substitutes — so it cannot happen. HOST-ONLY, the way the kit prescribes
     * (kit.mk: "asserted where there is a process to abort").
     */
    assert(width_class < RESTORE_BLIT_TABLE_ENTRIES);
#endif
    restore_blit_rows(image, src, dst, rows_minus_one, longs[width_class]);
}

static void replay_restore_list(uint8_t *image) {
    uint16_t index = (uint16_t)((be16(image + A_screen_ring_index) - RESTORE_LIST_LOOKBACK)
                                & (SCREEN_RING_SLOTS - 1u));
    uint32_t cursor = addr_add(A_sprite_restore_lists,
                               sign_ext16((uint16_t)(index * SPRITE_RESTORE_LIST_BYTES)));

    for (;;) {
        uint16_t offset = be16(image + cursor + SPRITE_RESTORE_OFFSET);
        uint32_t src = addr_add(addr_add(be32(image + A_screen_draw), sign_ext16(offset)),
                                RESTORE_SOURCE_SKEW);
        uint32_t dst = addr_add(be32(image + A_screen_prev2), sign_ext16(offset));
        uint32_t rows_minus_one = be16(image + cursor + SPRITE_RESTORE_ROWS);
        uint16_t width_class = be16(image + cursor + SPRITE_RESTORE_CLASS);

        if ((int16_t)width_class < 0)       /* the 0xffff terminator */
            return;
        restore_blit(image, width_class, src, dst, rows_minus_one);
        cursor = addr_add(cursor, SPRITE_RESTORE_REC_BYTES);
    }
}

void render_frame(uint8_t *image) {
    copy_ring_seam(image);

    /* `prescroll_flag` short-circuits everything that draws a sprite or publishes a frame, so
     * `start_level` can fill a whole screen of tiles with the palette black. */
    if (image[A_prescroll_flag] == 0) {
        uint16_t index = be16(image + A_screen_ring_index);
        uint32_t restore_cursor =
            addr_add(A_sprite_restore_lists,
                     sign_ext16((uint16_t)(index * SPRITE_RESTORE_LIST_BYTES)));

        restore_cursor = draw_display_list_pass(image, DRAW_PASS_UNDER_SCENERY, restore_cursor);
        repaint_overlay_tiles(image);
        restore_cursor = draw_display_list_pass(image, DRAW_PASS_ON_TOP, restore_cursor);
        /* `move.w #$ffff,2(a5)`: the terminator is the CLASS word of the record after the last, not
         * its first word — which is what makes globals.h's SPRITE_RESTORE_FIRST_ENTRY 2. */
        wr16(image + addr_add(restore_cursor, SPRITE_RESTORE_CLASS), SPRITE_RESTORE_TERMINATOR);
        publish_and_wait(image);
    }

    advance_scroll(image);
    draw_exposed_tile_band(image);
    replay_restore_list(image);
}

/* ================================================================================================
 * The register glue. This program is hand-written assembly with a REGISTER ABI, so each glue names
 * the registers the original's callers load and hands them straight to the core.
 * ============================================================================================= */

/* a0 = sprite data, a1 = screen, d6 = x & 0xf, d7 = clipped row count. */
#define DEFINE_BLIT_GLUE(name)                                                                     \
    void g_##name(uint8_t *image, uint32_t a0_src, uint32_t a1_dst, uint32_t d6_shift,             \
                  uint32_t d7_rows_minus_one) {                                                    \
        name(image, a0_src, a1_dst, d6_shift, d7_rows_minus_one);                                  \
    }

DEFINE_BLIT_GLUE(sprite_blit_w16)
DEFINE_BLIT_GLUE(sprite_blit_w32)
DEFINE_BLIT_GLUE(sprite_blit_w48)
DEFINE_BLIT_GLUE(sprite_blit_w64)

/* ...the same four registers, plus d4 = the sprite's final x and a5 = the restore-list write cursor,
 * which the routine rewinds and returns when the sprite is wholly off the edge. */
#define DEFINE_CLIPPED_BLIT_GLUE(name)                                                             \
    uint32_t g_##name(uint8_t *image, uint32_t a0_src, uint32_t a1_dst, uint32_t d6_shift,         \
                      uint32_t d7_rows_minus_one, uint32_t d4_x, uint32_t a5_restore_cursor) {     \
        return name(image, a0_src, a1_dst, d6_shift, d7_rows_minus_one, d4_x, a5_restore_cursor);  \
    }

DEFINE_CLIPPED_BLIT_GLUE(sprite_blit_w16_clip_left)
DEFINE_CLIPPED_BLIT_GLUE(sprite_blit_w32_clip_left)
DEFINE_CLIPPED_BLIT_GLUE(sprite_blit_w48_clip_left)
DEFINE_CLIPPED_BLIT_GLUE(sprite_blit_w64_clip_left)
DEFINE_CLIPPED_BLIT_GLUE(sprite_blit_w16_clip_right)
DEFINE_CLIPPED_BLIT_GLUE(sprite_blit_w32_clip_right)
DEFINE_CLIPPED_BLIT_GLUE(sprite_blit_w48_clip_right)
DEFINE_CLIPPED_BLIT_GLUE(sprite_blit_w64_clip_right)

/* a0 = source, a1 = destination, d7 = row count. */
#define DEFINE_RESTORE_GLUE(name)                                                                  \
    void g_##name(uint8_t *image, uint32_t a0_src, uint32_t a1_dst, uint32_t d7_rows_minus_one) {  \
        name(image, a0_src, a1_dst, d7_rows_minus_one);                                            \
    }

DEFINE_RESTORE_GLUE(restore_blit_w16)
DEFINE_RESTORE_GLUE(restore_blit_w32)
DEFINE_RESTORE_GLUE(restore_blit_w48)
DEFINE_RESTORE_GLUE(restore_blit_w64)
DEFINE_RESTORE_GLUE(restore_blit_w80)

/* a0 = base tile rows, a5 = overlay tile rows, a2 = screen, d3 = row count. */
void g_tile_blit_overlay_masked(uint8_t *image, uint32_t a0_base, uint32_t a5_overlay,
                                uint32_t a2_dst, uint32_t d3_rows_minus_one) {
    tile_blit_overlay_masked(image, a0_base, a5_overlay, a2_dst, d3_rows_minus_one);
}

/* a0 = source, a1 = destination. */
void g_scroll_wrap_copy_1280(uint8_t *image, uint32_t a0_src, uint32_t a1_dst) {
    scroll_wrap_copy_1280(image, a0_src, a1_dst);
}

/* No arguments: render_frame reads every input out of the globals. */
void g_render_frame(uint8_t *image) {
    render_frame(image);
}
