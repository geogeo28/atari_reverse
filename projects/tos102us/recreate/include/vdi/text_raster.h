/* vdi/text_raster.h — the TEXT RASTER: $a008 TextBlt and v_gtext's byte-aligned fast path, with the CPU
 * bodies behind drawing vectors 9 and 5 (`src/vdi/text_raster.c`).
 *
 * THE REGISTER CONTRACTS are the batteries' (`test/vdi_text.py`, through `test/vdi.py`'s
 * `declare_primitive`). $a008 takes nothing: it reads the Line-A block, and its CPU body is entered by
 * the `jmp (a4)` of $fcee54 with A6 = the block's base and A5/A6 pushed under the caller's return
 * address — which is why that body can only be reached through a front end or a staged caller that
 * builds the same stack. The fast path's front end `$fcf96a` takes nothing and answers D0 (1 drawn, 0
 * refused); its body `$fd1cc4` is entered by `jmp (a4)` with D0-D3 = x, y, characters, rows, A5 =
 * &LINEA_FBASE and the front end's A5 pushed.
 *
 * The ROM TABLES are read BY ADDRESS in the C (`vdi/raster.h`'s convention: the host runs over the
 * captured ROM, so the address IS the table), and `text_raster.S` carries its own copy of each, in the
 * ROM's layout, inside the region it transcribes — all but the fringe masks, which it reads from
 * `raster.S`'s copy (RASTER_FRINGE_MASK_TABLE).
 */
#ifndef TOS102US_VDI_TEXT_RASTER_H
#define TOS102US_VDI_TEXT_RASTER_H

#include "vdi/linea.h"
#include "vdi/vdi.h"

/* ---- the fast path ($fcf96a / $fd1cc4) ----------------------------------------------------------------
 * It draws only a glyph whose left edge is on a byte: x & 7 must be 0 ($fcf976). */
#define TEXT_FAST_X_ALIGN_MASK    7
#define TEXT_FAST_GLYPH_SHIFT     3          /* a character is eight pixels ($fcf9aa `lsl.w #3`)      */
/* Vector 5's eight byte arms, by WRT_MODE * 2 plus this when the plane's colour bit is set ($fd1d10). A
 * word table of offsets from its own start, which is where the jump counts from ($fd1d16). */
#define TEXT_FAST_ARM_TABLE       0xfd1d42
#define TEXT_FAST_ARM_COLOUR_SET  8

/* ---- TextBlt's tables ($fd1df6..$fd2d31) --------------------------------------------------------------
 * A GROUP's bytes by plane count — 2, 4, 0, 8 for 1..4 planes — a byte table indexed by LINEA_PLANES
 * itself, so entry 0 is the low byte of the `bra.s` in front of it ($fd2172 `(pc,d0.w)` at $fd2159). */
#define TEXT_GROUP_BYTES_TABLE    0xfd2159
/* The logic op by write mode and colour: a byte (the op * 2) at WRT_MODE * 4 + fg * 2 + bg ($fd234c).
 * Modes 0..3 are the VDI's four, which ignore the background bit; 4..19 are the sixteen BitBlt ops. */
#define TEXT_OP_INDEX_TABLE       0xfd23b2
/* ...and each op's two FRAGMENTS, as offsets from TEXT_FRAGMENTS: under a mask (a row's fringe words)
 * and whole (its middle words) — sixteen words each ($fd2350, $fd2360). */
#define TEXT_OP_MASKED_TABLE      0xfd2372
#define TEXT_OP_WHOLE_TABLE       0xfd2392
#define TEXT_OP_COUNT             16
#define TEXT_FRAGMENTS            0xfd2506   /* every fragment offset counts from here ($fd24d8)   */

/* The ROW LOOPS, as the offsets `$fd24e6 jsr (a3,a4.w)` enters them at: one word a row, two, and the
 * multi-word loops shifting the glyph right or left ($fd22d8, $fd22e0, $fd22fe, $fd230a). */
#define TEXT_ROWS_ONE_WORD        40
#define TEXT_ROWS_TWO_WORDS       116
#define TEXT_ROWS_RIGHT           278
#define TEXT_ROWS_LEFT            122
/* The EFFECT FRAGMENTS a styled row runs before its op, each ending in a jump to the one it replaced
 * ($fd2424..$fd2494): the first (or only) word of a row, its middle words, its two edge words. */
#define TEXT_FRAGMENT_THICKEN_FIRST  638
#define TEXT_FRAGMENT_THICKEN_MIDDLE 740
#define TEXT_FRAGMENT_THICKEN_EDGE   790
#define TEXT_FRAGMENT_LIGHTEN_FIRST  940
#define TEXT_FRAGMENT_LIGHTEN_MIDDLE 960
#define TEXT_FRAGMENT_LIGHTEN_EDGE   972
#define TEXT_FRAGMENT_SKEW           984

/* The write mode the effects' pre-pass copies the glyph into the scratch buffer with, one plane in
 * colour 1 on 0: BitBlt op 3, "source" ($fd2034 `move.w #7`). */
#define TEXT_SCRATCH_WRITE_MODE   7
/* The effects that make TextBlt pre-pass a glyph (with a turn, an outline, or a clipped italic —
 * $fd1f4e `andi.w #21`), and the two of them the pre-pass itself applies ($fd2050 `andi.w #5`). Spelt
 * with `+` so the `.S` can use them: `|` starts a comment in m68k GNU as, and the bits are disjoint. */
#define TEXT_PREPASS_EFFECTS      (VDI_STYLE_THICKEN_MASK + VDI_STYLE_SKEW_MASK + VDI_STYLE_OUTLINE_MASK)
#define TEXT_PREPASS_APPLIED      (VDI_STYLE_THICKEN_MASK + VDI_STYLE_SKEW_MASK)
/* An outlined glyph is a pixel bigger all round ($fd1eaa `addq.w #2`), and its pre-pass blits it three
 * pixels wider, a pixel in from a cleared border ($fd1fc8 `addq.w #3`). */
#define TEXT_OUTLINE_GROWTH       2
#define TEXT_OUTLINE_BLIT_WIDTH   3
/* A row that ends inside the first screen word is a one-word row ($fd22c6 `cmpi.w #16`); one that ends
 * in the second is a two-word row unless its source needs a third word ($fd22f8 `cmpi.w #32`). */
#define TEXT_ONE_WORD_SPAN        16
#define TEXT_TWO_WORD_SOURCE_SPAN 32
/* The rotations TextBlt knows, in tenths of a degree (LINEA_CHUP). Anything else nonzero is taken as a
 * quarter turn that swaps the glyph's axes without moving it ($fd1ed2). */
#define TEXT_ROTATION_90          900
#define TEXT_ROTATION_180         1800
#define TEXT_ROTATION_270         2700

#ifndef __ASSEMBLER__
#include <stdint.h>

/* $fcee54 — $a008 TextBlt through vector 9, and the vector's CPU body. */
void linea_textblt(uint8_t *image);
void linea_cpu_textblt(uint8_t *image);
/* $fcf96a — v_gtext's fast path: 1 when vector 5 drew the string, 0 when it is not the fast shape. */
uint32_t linea_fast_text(uint8_t *image);
/* $fd1cc4 — vector 5's CPU body, as the front end enters it: D0-D3. Answers 1. */
uint32_t linea_cpu_fast_text(uint8_t *image, uint32_t x, uint32_t y, uint32_t characters, uint32_t rows);
#endif

#endif /* TOS102US_VDI_TEXT_RASTER_H */
