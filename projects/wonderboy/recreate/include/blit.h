/* blit.h — the twelve MASKED PLANAR SPRITE BLITTERS at $8fce..$989c: prototypes, the register file
 * they are entered with, and the geometry of one sprite row.
 *
 * The sprite pass at $8f02 computes a screen address and a sub-word shift for one actor and then
 * `jsr`s through one of three four-entry jump tables — `blit_table_mid` ($989c) while the x is on
 * screen, `blit_table_left` ($98ac) while it is negative, `blit_table_right` ($98bc) from $b0 on —
 * each indexed by a WIDTH CODE 0..3, i.e. WB_BLIT_COLUMNS_MIN..WB_BLIT_COLUMNS_MAX 16-pixel
 * columns. So there are twelve entry points over four widths and three clip cases, and this file
 * names all of them; ../names.txt is where they and the tables are named in the image. THE PASS
 * ITSELF IS NOT RECONSTRUCTED HERE: what it computes is context for these twelve, and the register
 * interface below is read off the twelve bodies rather than off their one caller.
 *
 * WHAT A SPRITE LOOKS LIKE. Row-major, and pre-split for the rotate: per row there is one CELL per
 * column-minus-one, and a cell is WB_BLIT_CELL_WORDS words — an AND mask, then WB_PLANES
 * bitplanes. Every one of those words is rotated RIGHT as a longword by the sub-word shift, which
 * pushes the pixels past the 16-pixel boundary into the longword's high half; the low half draws
 * the column the cell belongs to and the high half is folded into the NEXT one. That is why N
 * columns are drawn from N-1 cells: the first column is a cell's low half alone and the last is a
 * cell's high half alone, and every column between is a seam of two cells.
 *
 * WHAT CLIPPING IS. The eight clip preludes write a byte, WB_BLIT_CLIP_MASK, whose bits say which
 * columns survive — the LEFTMOST column is the HIGHEST bit — and branch into a body that `btst`s
 * that bit per column and steps the screen cursor past the ones it leaves out. A sprite with no
 * column left on screen is not drawn at all; on the LEFT that also winds a caller's pointer back by
 * WB_BLIT_UNWIND_BYTES (`subq.w #6,a5`), and on the right it does not.
 */
#ifndef WONDERBOY_BLIT_H
#define WONDERBOY_BLIT_H

#include <stdint.h>

/* WB_PLANES, WB_SCREEN_LINE and WB_STATE_WORD_LEN below are wonderboy.h's — this family draws on
 * the same screen out of the same header, and the macros here expand to them. */
#include "wonderboy.h"

/* --- one sprite row's geometry ---------------------------------------------------------------- */
#define WB_BLIT_COLUMN_PIXELS     16u  /* one plane word covers this many pixels */
#define WB_BLIT_CELL_WORDS        5u   /* one source cell: the AND mask, then the four planes */
/* What a DRAWN column advances the screen cursor by — and what the row's LAST column advances it
 * by, its final `or.w` being the one write with no post-increment. A column the clip mask leaves
 * out is stepped over by the same two distances (`lea 8(a1),a1` / `lea 6(a1),a1`), so where a row
 * ends does not depend on what was clipped out of it. */
#define WB_BLIT_COLUMN_BYTES      (WB_PLANES * WB_STATE_WORD_LEN)
#define WB_BLIT_LAST_COLUMN_BYTES (WB_BLIT_COLUMN_BYTES - WB_STATE_WORD_LEN)

/* The four widths, as the number of 16-pixel columns each draws. The width CODE the jump tables are
 * indexed by is this minus WB_BLIT_COLUMNS_MIN. */
#define WB_BLIT_COLUMNS_MIN       2u
#define WB_BLIT_COLUMNS_MAX       5u

/* The one width whose bodies count their rows up front, and the one column whose last plane the
 * clipped four-column body merges late — the two places the twelve break their own pattern, as the
 * numbers they are. src/blit.c's file comment reads both off the listing; the widths' table there
 * derives its flag from the first, and test/test_blit.py assembles all twelve out of both. */
#define WB_BLIT_GUARDED_COLUMNS        2u
#define WB_BLIT_DEFERRED_MERGE_COLUMN  2u

/* `lea N(a1),a1` at the end of a row: what is left of a WB_SCREEN_LINE scanline once the row's own
 * columns have been walked. 146/138/130/122 for widths 2..5. */
#define WB_BLIT_ROW_ADVANCE(columns) \
    (WB_SCREEN_LINE - ((columns) * WB_BLIT_COLUMN_BYTES - WB_STATE_WORD_LEN))

/* --- clipping ---------------------------------------------------------------------------------- */
/* The byte the preludes write and the clipped bodies `btst`. Bit 0 is the RIGHTMOST column. */
#define WB_BLIT_CLIP_MASK         0x9966u

/* One past the last on-screen pixel column, as the preludes measure it: their right-hand thresholds
 * are this minus WB_BLIT_COLUMN_PIXELS per column still to be drawn ($b0/$c0/$d0/$e0/$f0), and
 * their left-hand ones are the same step below zero ($fff0/$ffe0/$ffd0/$ffc0). */
#define WB_BLIT_SCREEN_EDGE_X     0x100

/* `subq.w #6,a5` — what a fully-off-screen LEFT sprite takes off a5 before returning. Six bytes is
 * one WB_ACTOR_SCREEN_RECORDS record, but the sprite pass at $8f02 walks that array in a6, so which
 * caller's cursor this unwinds is not established here. */
#define WB_BLIT_UNWIND_BYTES      6

/* --- the register file -------------------------------------------------------------------------- */
/* d0..d5, the window the source cells are loaded through. The original walks it DOWNWARD one cell
 * at a time (the mask lands in d1, d0, d5, d4 for cells 0..3, the planes following the mask
 * upward), which is why six registers serve five words. */
#define WB_BLIT_SCRATCH_REGS      6u

/* d4 carries the screen x into a prelude — and is then clobbered as scratch[4] by the body under
 * it, which is why the two are one field rather than two. */
#define WB_BLIT_X_REG             4u

/* The 68000 registers this family reads and leaves behind. Register map: scratch[n] = dn (with the
 * entry x in scratch[WB_BLIT_X_REG]), shift = d6, rows = d7, source = a0, dest = a1, unwind = a5.
 *
 * Every field is IN and OUT. The four inputs are `source`, `dest`, `shift` and `rows` (plus the x
 * for a prelude and `unwind` for a left one); everything else is scratch whose FINAL value is still
 * observable, since the original leaves it in a register the caller could read. `rows` is an input
 * the bodies consume: a body draws `rows + 1` of them and leaves the counter at its own exit value.
 */
typedef struct {
    uint32_t scratch[WB_BLIT_SCRATCH_REGS];
    uint32_t shift;
    uint32_t rows;
    uint32_t source;
    uint32_t dest;
    uint32_t unwind;
} sprite_blit_regs;

/* --- the twelve entry points --------------------------------------------------------------------- */
/* `blit_table_mid`: the sprite is wholly on screen, so every column is drawn and the clip byte is
 * neither written nor read. $9774 is the one function in the program Ghidra's decompiler dies on
 * (../names.txt), so it is reconstructed from the listing alone. */
void blit_sprite_w2(uint8_t *image, sprite_blit_regs *regs);
void blit_sprite_w3(uint8_t *image, sprite_blit_regs *regs);
void blit_sprite_w4(uint8_t *image, sprite_blit_regs *regs);
void blit_sprite_w5(uint8_t *image, sprite_blit_regs *regs);

/* `blit_table_left`: x < 0. Each arm drops one more of the LEFT-hand columns; past the last one
 * the sprite is wholly off screen and `unwind` is stepped back. */
void blit_clip_left_w2(uint8_t *image, sprite_blit_regs *regs);
void blit_clip_left_w3(uint8_t *image, sprite_blit_regs *regs);
void blit_clip_left_w4(uint8_t *image, sprite_blit_regs *regs);
void blit_clip_left_w5(uint8_t *image, sprite_blit_regs *regs);

/* `blit_table_right`: the sprite pass sends an x of $b0 and up here. Each arm drops one more of the
 * RIGHT-hand columns, and the wholly-off-screen arm returns having touched nothing at all. */
void blit_clip_right_w2(uint8_t *image, sprite_blit_regs *regs);
void blit_clip_right_w3(uint8_t *image, sprite_blit_regs *regs);
void blit_clip_right_w4(uint8_t *image, sprite_blit_regs *regs);
void blit_clip_right_w5(uint8_t *image, sprite_blit_regs *regs);

#endif /* WONDERBOY_BLIT_H */
