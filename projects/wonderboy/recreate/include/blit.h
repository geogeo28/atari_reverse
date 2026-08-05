/* blit.h — the SPRITE TIER: the pass at $8f02 that decides what to draw and where, and the twelve
 * MASKED PLANAR SPRITE BLITTERS at $8fce..$989c that draw it. Prototypes, the register files the
 * two are entered with, and the geometry of one sprite row.
 *
 * The sprite pass at $8f02 computes a screen address and a sub-word shift for one actor and then
 * `jsr`s through one of three four-entry jump tables — `blit_table_mid` ($989c) while the x is on
 * screen, `blit_table_left` ($98ac) while it is negative, `blit_table_right` ($98bc) from $b0 on —
 * each indexed by a WIDTH CODE 0..3, i.e. WB_BLIT_COLUMNS_MIN..WB_BLIT_COLUMNS_MAX 16-pixel
 * columns. So there are twelve entry points over four widths and three clip cases, and this file
 * names all of them; ../names.txt is where they and the tables are named in the image. The register
 * interface below is read off the twelve BODIES rather than off their caller, and the pass's own
 * section at the end of this file is read off the caller.
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

/* --- the sprite pass at $8f02 ------------------------------------------------------------------
 *
 * game_main_loop's one `jsr $8f02.l`, and the twelve above have no other caller. It walks the
 * WB_ACTOR_SCREEN_RECORD_COUNT records project_actor_list left at WB_ACTOR_SCREEN_RECORDS and, for
 * each one that names a sprite, reads that sprite's DESCRIPTOR out of WB_RESOURCE_TABLE, clips the
 * sprite against the top and the bottom of the band, builds the screen address and the sub-word
 * shift, and picks a table by the screen x.
 *
 * SO WB_RESOURCE_TABLE'S RECORDS ARE SPRITE DESCRIPTORS. resource_table_relocate ($fe1e, in
 * src/stage.c — see ../names.txt) turns each record's first longword from an offset into an
 * absolute pointer, and this is the routine that reads the result: ten of the twenty bytes, in the
 * five fields below. What the other ten hold is still not established. The offsets live in THIS
 * header rather than beside WB_RESOURCE_TABLE in wonderboy.h because the sprite pass is the only
 * reader of the table that has been read.
 */
#define WB_SPRITE_DESC_SOURCE      0u    /* longword: the cell data, already an absolute pointer */
#define WB_SPRITE_DESC_WIDTH_CODE  4u    /* byte, `ext.w`ed: the jump tables' index, 0..3 */
#define WB_SPRITE_DESC_HEIGHT      5u    /* byte, `ext.w`ed — so a descriptor CAN ask for a
                                          * NEGATIVE number of rows; see src/blit.c */
#define WB_SPRITE_DESC_X_OFFSET    8u    /* word, added to the screen record's own x */
#define WB_SPRITE_DESC_Y_OFFSET    10u   /* word, added to its y */

/* The three jump tables as ADDRESSES, because the pass reads its blitter pointer out of the image
 * rather than knowing it: `lea $989c.l,a2 / adda.w d2,a2 / movea.l (a2),a2 / jsr (a2)`. What each
 * slot holds is pinned against ../names.txt by test/test_blit.py. */
#define WB_BLIT_TABLE_MID          0x989cu
#define WB_BLIT_TABLE_LEFT         0x98acu
#define WB_BLIT_TABLE_RIGHT        0x98bcu
#define WB_BLIT_TABLE_SLOT_SHIFT   2u    /* `lsl.w #2,d2`: one longword per slot */
#define WB_BLIT_WIDTH_CODE_MAX     3u    /* the last slot of a four-entry table */

/* The band the pass clips to, as ROWS of the visible window that starts WB_BG_BLIT_SCREEN_ORIGIN
 * bytes into WB_SCREEN_BACK. One number in two instructions: the `cmpi.w #$9f,d1` that rejects a
 * sprite starting below it and the `move.w #$9f,d2` the row count is clamped against. It is
 * WB_BG_BLIT_SCANLINES - 1 — the same window the background blit fills — but it is spelt as the
 * literal $9f the two instructions carry because test/layout.py scrapes plain integers only and an
 * expression here would drop the constant out of the tests' reach; the identity is held instead by
 * test_blit.py's `test_the_pass_geometry_is_what_the_numbers_say`. */
#define WB_SPRITE_LAST_ROW         0x9fu

/* `cmp.w #$b0,d4`: from this screen x on, the RIGHT table is selected. It is exactly
 * WB_BLIT_SCREEN_EDGE_X - WB_BLIT_COLUMNS_MAX * WB_BLIT_COLUMN_PIXELS — the first x at which even
 * the widest sprite could touch the right edge — which test/test_blit.py states as the identity it
 * is rather than a coincidence. */
#define WB_SPRITE_RIGHT_CLIP_X     0xb0u

/* Splitting the screen x into a column and a sub-word shift: `andi.w #$f,d6` is the shift the
 * blitters rotate by and `andi.w #$fff0,d0` the whole 16-pixel column, and the two masks partition
 * the word. The rounded x then halves into a byte offset, because four interleaved planes put
 * WB_BLIT_COLUMN_PIXELS pixels in WB_BLIT_COLUMN_BYTES — `asr.w #1,d0`, SIGNED, so a negative
 * column steps the screen cursor back. */
#define WB_SPRITE_SHIFT_MASK       0xfu
#define WB_SPRITE_COLUMN_MASK      0xfff0u
#define WB_SPRITE_X_BYTE_SHIFT     1u

/* ...and the row, built out of one register by two `asl.w`s that leave it holding y << 7:
 * (1 << 5) + (1 << (5 + 2)) == WB_SCREEN_LINE, which test/test_blit.py states. */
#define WB_SPRITE_ROW_SHIFT_LOW    5u
#define WB_SPRITE_ROW_SHIFT_HIGH   2u

/* Which of d0..d5 the pass uses for what. d4 is WB_BLIT_X_REG above — the pass computes the screen
 * x into the very register the clip preludes read it from. */
#define WB_SPRITE_WORK_REG         0u    /* the sprite index, then two products, then the offset */
#define WB_SPRITE_Y_REG            1u    /* the screen y, and afterwards y << 7 */
#define WB_SPRITE_WIDTH_REG        2u    /* the width code, and afterwards its table offset */
#define WB_SPRITE_ECHO_Y_REG       5u    /* `move.w d1,d5`, written and never read */

/* The 68000 registers the pass reads and leaves behind: `blit` is exactly what it hands a blitter
 * (and what a blitter hands back), plus the three address registers the walk itself uses.
 * Register map: record = a6, descriptor = a4, blitter = a2.
 *
 * Every field is IN and OUT, as for a blitter. The pass has NO argument — a6, a4 and a2 are loaded
 * from `lea`s and everything else it reads is memory — so the only field that is an input in the
 * ordinary sense is `blit.unwind` (a5), which it never touches and each wholly-off-left sprite
 * takes WB_BLIT_UNWIND_BYTES off. The rest are inputs only through their HIGH halves, which the
 * pass's word operations leave alone. */
typedef struct {
    sprite_blit_regs blit;
    uint32_t record;
    uint32_t descriptor;
    uint32_t blitter;
} sprite_pass_regs;

void sprite_draw_pass(uint8_t *image, sprite_pass_regs *regs);

#endif /* WONDERBOY_BLIT_H */
