/* sprite.h — the sprite bank's directory record, the twelve masked blitters that read it, the five
 * restore blitters that undo them, and `render_frame` @ 0x14446, which drives all of it.
 *
 * PROVENANCE. Every address is a `var` or `fn` line in `../names.txt` at load base 0x10000, and the
 * instruction that establishes each figure is named beside it. `../notes/gameplay.md` §5 has the
 * prose; this header is the machine-checkable half.
 */
#ifndef FS_SPRITE_H
#define FS_SPRITE_H

#include <stdint.h>

#include "display_list.h"
#include "globals.h"
#include "irq.h"           /* `A_vbl_tick`, the frame counter the VBL handler owns and this file
                            * only waits on */
#include "scroll.h"        /* the scroller block `render_frame` reads and steps but does not own:
                            * `A_map_row_ptr`, `A_map_row_ptr_reset`, `A_scroll_fine`,
                            * `A_screen_ring_index`, `A_prescroll_flag`, `A_tile_split_row_table` */

/* ---- one record of A\SPRITES.cru's 256-record directory ---------------------------------------
 *
 * `include/globals.h` owns where the bank is (`A_sprite_bank`), how many records there are
 * (SPRITE_RECORDS) and the stride (SPRITE_RECORD_BYTES), because the BOOT CHAIN relocates the first
 * longword of each. The FIELDS are here, read off the two routines that index the record:
 * `render_frame`'s two draw passes (@ 0x144a4 and @ 0x146b4) and `sprite_hit_test` @ 0x11698.
 *
 * `../notes/assets_survey.md` §SPRITES.CRU is the same table with the file-format argument; where
 * the two disagree the instruction cited here wins.
 */
#define SPRITE_REC_DATA        0u  /* LONG: the pixel data. FILE-RELATIVE in the file and ABSOLUTE in
                                    * memory — the boot chain's `addi.l #$1be36,(a0)` @ 0x112cc makes
                                    * it so. `movea.l (a4),a0` @ 0x144bc reads it as an address */
#define SPRITE_REC_WIDTH_CLASS 4u  /* WORD: width in 16-pixel groups MINUS 1, i.e. 0..3. It is the
                                    * index into all four blitter tables (`lsl.w #2,d2 / adda.w d2,a2`
                                    * @ 0x145ae) AND the value stored in the restore record */
#define SPRITE_REC_ROWS        6u  /* WORD: height in rows MINUS 1 — a `dbf` count. `move.w 6(a4),d7`
                                    * @ 0x144b8 hands it straight to the blitter's `dbf d7` */
#define SPRITE_REC_DRAW_DX     8u  /* WORD, signed: added to the display record's x before clipping
                                    * (`add.w 8(a4),d0` @ 0x144fe) and by sprite_hit_test too */
#define SPRITE_REC_DRAW_DY    10u  /* WORD, signed: likewise for y (`add.w 10(a4),d1` @ 0x144c2) */
#define SPRITE_REC_HIT_DX     12u  /* WORD: an EXTRA hit-box offset, added on top of the draw offset
                                    * by `sprite_hit_test` @ 0x11698 alone — no blitter reads it */
#define SPRITE_REC_HIT_DY     14u  /* WORD: ...and its y */
#define SPRITE_REC_HIT_W      16u  /* WORD: hit-box width in pixels (`add.w 16(a4)` gives the far
                                    * edge), which is NOT the bitmap's width */
#define SPRITE_REC_HIT_H      18u  /* WORD: hit-box height, likewise */

/* ---- the masked bitmap the record points at ---------------------------------------------------
 *
 * Five words to a 16-pixel group — mask first, then planes 0..3 — so one source row of a class-`c`
 * sprite is (c + 1) groups of 10 bytes. The blitter reads them with five `move.w (a0)+` @ 0x153c0
 * and the top-clip arm computes the row stride as `(class + 1) * 10` @ 0x144ce, which is the
 * cleanest statement of it in the program.
 */
#define SPRITE_PLANES           4u  /* the four `or.w dN,(a1)` per group */
#define SPRITE_GROUP_BYTES     10u  /* `mulu.w #$a,d0` @ 0x144d4 — the source stride of one group */
#define SPRITE_WIDTH_CLASSES    4u  /* the four longwords in each blitter table */

/* A class-`c` sprite is (c + 1) source groups wide and lands on (c + 1) + 1 SCREEN groups, because
 * a sub-word shift spills every group into the one after it — the extra group is the `swap` half of
 * the blitter's rotated registers. That is where the width classes' names come from: class 0 is a
 * 16-pixel sprite over 32 pixels of screen, class 3 a 64-pixel one over 80.
 */
#define GROUP_PIXELS 16u   /* one mask + 4 plane words, and one screen longword pair, cover this */

/* ---- the screen a blitter writes -------------------------------------------------------------- */
#define SCREEN_ROW_BYTES   160u /* `lea 146(a1),a1` after eight group bytes plus six, and the
                                 * `mulu.w #$a0,d3` @ 0x1463c — one 320-pixel 4-plane row */
#define SCREEN_GROUP_BYTES   8u /* SPRITE_PLANES interleaved words: one 16-pixel column of a row */
#define SCREEN_ROWS        200u /* the `cmpi.w #$c7,d1` clip @ 0x144e0 is against the LAST row */
#define SCREEN_LAST_ROW    199u /* ...which is this, and is what the code actually spells */

/* ---- blit_clip_mask: which 16-pixel groups of a clipped sprite reach the screen ----------------
 *
 * The eight clipped blitters store a byte here and then `btst` one bit of it per group. Bit 0 is
 * the LAST group (the `swap` half) and the bits run leftward, so group `g` of a class-`c` sprite is
 * gated by bit `c + 1 - g`.
 */
#define A_blit_clip_mask 0x16426u /* `move.b #$1,$16426.l` @ 0x14de0 and 15 siblings */

/* ---- the four blitter dispatch tables, and the fifth restore entry ----------------------------- */
#define A_sprite_blit_tbl            0x16396u /* `lea $16396.l,a2` @ 0x14592 / @ 0x14732 */
#define A_sprite_blit_clip_left_tbl  0x163a6u /* `lea $163a6.l,a2` @ 0x1459c — taken when x < 0 */
#define A_sprite_blit_clip_right_tbl 0x163b6u /* `lea $163b6.l,a2` @ 0x145a8 / @ 0x14748 */
#define A_restore_blit_tbl           0x163c6u /* `lea $163c6.l,a2` @ 0x14944 */
#define BLIT_TABLE_ENTRY_BYTES 4u             /* `lsl.w #2,d2` before every one of those `adda.w` */

/* The restore table has FIVE entries, not four: index 4 is `restore_blit_w16` @ 0x14d58, and the
 * two narrow clip-right blitters reach it by rewriting the pending restore record's class word
 * (`move.w #$4,-4(a5)` @ 0x14e10 and @ 0x14ef8). `../notes/gameplay.md` §"Restore blitters" says
 * 0x14d58 "is not reached through it" — that is WRONG, and `test_sprite.py`'s
 * `test_the_blit_tables_name_the_routines_this_file_dispatches_to` reads the fifth longword. */
#define RESTORE_BLIT_TABLE_ENTRIES 5u
#define RESTORE_CLASS_W16          4u  /* the index whose blitter restores ONE 16-pixel group */
#define RESTORE_CLASS_KEEP        (-1) /* ...and "this rung leaves the record's own class alone" */

/* ---- the scroll state, READ from include/scroll.h ----------------------------------------------
 *
 * `render_frame` READS and STEPS `A_map_row_ptr`, `A_screen_ring_index`, `A_scroll_fine`,
 * `A_tile_split_row_table`, `A_prescroll_flag` and `A_map_row_ptr_reset`; it does not own any of
 * them. They were held HERE on loan while the scroll subsystem was unported, and the loan is closed:
 * `include/scroll.h` defines them, this header includes it, and STATUS.md's "Borrowed globals" rows
 * went with the defines. What is below is what the SPRITE side of that reading needs — the geometry
 * of a tile, a map row and the band the scroll exposes.
 * ---------------------------------------------------------------------------------------------- */
#define TILE_BAND_ROWS       8u       /* the strip the scroll exposes per frame, and what every pair
                                       * in the table above adds up to */
#define TILE_PIXELS          32u      /* one tile is 32x32: `asl.l #4 / asl.l #5` = *512 @ 0x1486e */
#define TILE_ROW_BYTES       16u      /* ...so one row of one tile is 16 bytes, 4 interleaved planes */
#define TILE_BAND_COLUMN_BYTES 16u    /* ...and 32 pixels is 16 bytes of a screen row too: the
                                       * `lsl.w #3` on a two-byte cell cursor @ 0x145ea */
#define TILE_BAND_COLUMN_BACKSTEP 1264u /* `lea -1264(a2),a2` @ 0x1490a. It lands on the next
                                         * column's top only because the band is 8 rows of 160 and
                                         * 1280 - 1264 is one column — see src/sprite.c */
#define TILE_INDEX_SHIFT       5u     /* `lsr.w #5` / `asr.w #5`: a pixel coordinate to a tile
                                       * index, TILE_PIXELS being 1 << this */
#define TILE_BYTES           512u     /* TILE_PIXELS * TILE_ROW_BYTES */
/* The two `movem.w (a5)+,#$003c` per tile row @ 0x14642 and @ 0x14d18 — a 32-pixel tile row is two
 * 16-pixel groups. Derived rather than spelt, so the 32 and the 16 cannot drift apart. */
#define TILE_ROW_GROUPS (TILE_PIXELS / GROUP_PIXELS)
#define MAP_CELL_BYTES       2u       /* `lea 2(a3),a3` @ 0x14906: base tile byte, overlay tile byte */
#define MAP_CELL_OVERLAY     1u       /* ...the odd one; `move.b 1(a3),d1` @ 0x1488e */
#define MAP_COLUMNS          10u      /* `move.w #$9,d7` + `dbf` @ 0x14846 */
#define MAP_ROW_BYTES        20u      /* = MAP_COLUMNS * MAP_CELL_BYTES; `suba.w #$14,a0` @ 0x147d0
                                       * and the `20(a3)` / `21(a3)` displacements @ 0x14884. It is
                                       * numerically TILE_REPAIR_ROW_BYTES and not the same fact:
                                       * that the two agree is WHY one word index walks the map and
                                       * the repair grid alike (include/display_list.h) */

/* `A_vbl_tick` is `include/irq.h`'s — `vbl_handler` @ 0x11636 is its only writer — and is read from
 * there. What IS this routine's is the count it waits for: `cmpi.l #$3,$17720` @ 0x14786. */
#define RENDER_FRAME_VBL_BUDGET 3u   /* 3 VBLs a frame, ~16.7 fps nominal on a 50 Hz machine */

/* ---- the ring seam ----------------------------------------------------------------------------
 * The shifter reads across the ring's wrap, so the bottom SCREEN_BYTES of the ring is duplicated
 * one ring above itself whenever the draw base is inside it. */
#define SCROLL_WRAP_COPY_LONGS 80u   /* the 80 unrolled `move.l (a0)+,(a1)+` @ 0x156ae */
#define SCROLL_WRAP_COPY_CALLS  4u   /* `bsr.w $156ae` x4 @ 0x14464..0x14470 */

/* ================================================================================================
 * The cores. Every one of them takes the flat image and absolute addresses, because this program is
 * hand-written assembly with a register ABI and no such thing as a pointer argument.
 * ============================================================================================= */

/* The four unclipped masked blitters. `src` = the sprite's pixel data (already advanced past any
 * rows clipped off the top), `dst` = the screen address of the first group, `shift` = x & 0xf,
 * `rows_minus_one` = the `dbf` count. */
void sprite_blit_w16(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift, uint32_t rows_minus_one);
void sprite_blit_w32(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift, uint32_t rows_minus_one);
void sprite_blit_w48(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift, uint32_t rows_minus_one);
void sprite_blit_w64(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift, uint32_t rows_minus_one);

/* ...and the eight clipped ones. Each first decides, from the sprite's final x, which groups reach
 * the screen — storing the answer in `blit_clip_mask` — and a sprite wholly off the edge is not
 * drawn at all: the routine REWINDS the caller's restore-list cursor by one record and returns.
 * That cursor is the return value, which is why these eight are not void. */
uint32_t sprite_blit_w16_clip_left(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift,
                                   uint32_t rows_minus_one, uint32_t x, uint32_t restore_cursor);
uint32_t sprite_blit_w32_clip_left(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift,
                                   uint32_t rows_minus_one, uint32_t x, uint32_t restore_cursor);
uint32_t sprite_blit_w48_clip_left(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift,
                                   uint32_t rows_minus_one, uint32_t x, uint32_t restore_cursor);
uint32_t sprite_blit_w64_clip_left(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift,
                                   uint32_t rows_minus_one, uint32_t x, uint32_t restore_cursor);
uint32_t sprite_blit_w16_clip_right(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift,
                                    uint32_t rows_minus_one, uint32_t x, uint32_t restore_cursor);
uint32_t sprite_blit_w32_clip_right(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift,
                                    uint32_t rows_minus_one, uint32_t x, uint32_t restore_cursor);
uint32_t sprite_blit_w48_clip_right(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift,
                                    uint32_t rows_minus_one, uint32_t x, uint32_t restore_cursor);
uint32_t sprite_blit_w64_clip_right(uint8_t *image, uint32_t src, uint32_t dst, uint32_t shift,
                                    uint32_t rows_minus_one, uint32_t x, uint32_t restore_cursor);

/* The five restore blitters: an unrolled `move.l (a0)+,(a1)+` run of 2/4/6/8/10 longwords per row,
 * each followed by the `lea` that completes a 160-byte row on both pointers. */
void restore_blit_w16(uint8_t *image, uint32_t src, uint32_t dst, uint32_t rows_minus_one);
void restore_blit_w32(uint8_t *image, uint32_t src, uint32_t dst, uint32_t rows_minus_one);
void restore_blit_w48(uint8_t *image, uint32_t src, uint32_t dst, uint32_t rows_minus_one);
void restore_blit_w64(uint8_t *image, uint32_t src, uint32_t dst, uint32_t rows_minus_one);
void restore_blit_w80(uint8_t *image, uint32_t src, uint32_t dst, uint32_t rows_minus_one);

/* One 32-pixel-wide strip of a map cell, base tile under overlay tile with the overlay's colour 0
 * transparent. `base_src`/`overlay_src` are tile-row addresses, `dst` the screen. */
void tile_blit_overlay_masked(uint8_t *image, uint32_t base_src, uint32_t overlay_src, uint32_t dst,
                              uint32_t rows_minus_one);

/* 80 longwords — two whole screen rows — from `src` to `dst`. */
void scroll_wrap_copy_1280(uint8_t *image, uint32_t src, uint32_t dst);

/* The whole frame: seam, both draw passes, the overlay repaint, the flip, the new tile band and the
 * restore-list replay. Reads and writes only globals; takes no arguments of its own. */
void render_frame(uint8_t *image);

/* ================================================================================================
 * The ASM TWINS the target build substitutes for four of the cores above.
 *
 * `../src/asm/sprite.S`, `../src/asm/restore.S` and `../src/asm/clipped.S` transcribe the ORIGINAL's
 * own instruction sequence for these routines, and `atari/build.sh` links them into the .PRG with
 * `-DFS_ASM_SPRITE`, which is what makes `../src/sprite.c`'s four seams call a twin instead of its
 * own C. The differential build never defines it and never links them; `test/test_asm_sprite.py`,
 * `test/test_asm_restore.py` and `test/test_asm_clipped.py` are what prove each twin equal to the
 * core it stands in for.
 *
 * THE SIGNATURES LIVE HERE AND NOWHERE ELSE, which is the point of the block rather than a tidying.
 * They were `extern`s inside `src/sprite.c` that the host build never compiles, so a twin that
 * gained an argument and a declaration that did not would have pushed the wrong frame with only
 * `atari/smoke.py`'s single framebuffer compare able to notice (`../STATUS.md` carried that as a
 * named gap). `atari/build.sh` reads the twin NAMES out of this block too, so the objects its gate
 * interrogates and the declarations the core compiles cannot drift apart.
 * ============================================================================================= */
#ifdef FS_ASM_SPRITE
void blit_sprite_rows_unclipped_asm(uint8_t *image, uint32_t src, uint32_t dst,
                                    unsigned width_class, unsigned shift, uint32_t rows_minus_one);
/* ...and the GATED half of the same core, `src/asm/clipped.S`. Same arguments: the caller has
 * already installed the gate byte at `A_blit_clip_mask`, exactly as the clip ladders do. */
void blit_sprite_rows_gated_asm(uint8_t *image, uint32_t src, uint32_t dst,
                                unsigned width_class, unsigned shift, uint32_t rows_minus_one);
void restore_blit_rows_asm(uint8_t *image, uint32_t src, uint32_t dst, uint32_t rows_minus_one,
                           unsigned longs_per_row);
void scroll_wrap_copy_1280_asm(uint8_t *image, uint32_t src, uint32_t dst);
#endif

#endif /* FS_SPRITE_H */
