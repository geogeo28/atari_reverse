/* scroll.h — the level map, the off-screen page ring and the column emitters in src/scroll.c.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function". The screen
 * geometry these routines share with the front end lives in video.h, which owns it.
 *
 * HOW THE SCROLLER IS SHAPED, because every routine here is one step of it:
 *
 *   * the level arrives as an RLE stream and is unpacked COLUMN-MAJOR — 400 columns of 18 tile
 *     words — by `map_rle_decompress`;
 *   * `scroll_emit_tile_column` (not ported) decodes one map column into a 32-pixel workspace, and
 *     `scroll_emit_column_shift2` / `_shift0` walk that workspace two pixels at a time, emitting the
 *     visible half into one of eight off-screen PAGES and into the screen's right-edge column;
 *   * a page is a full playfield (144 rows of 160 bytes) holding the background at one 16-pixel
 *     bank, and `scroll_page_to_screen_p00..p19` copy a 152-byte RING WINDOW out of it onto the
 *     screen — twenty entry points, one per 8-byte column phase, reached only through the jump
 *     table at `scroll_blit_jump_table` (0x179aa).
 */
#ifndef ZYNAPS_SCROLL_H
#define ZYNAPS_SCROLL_H

#include <stdint.h>

/* ================================================================================================
 * The map.
 * ============================================================================================= */
/* names.txt calls 0x4b3be `tile_set_base`, and it is BOTH: `_start` reads the level file in here
 * (`load_file` at 0x10a04), unpacks it to A_map_unpacked, and then loads the tile set over the top
 * (0x10a36). One buffer, two uses in sequence — not two names for one address.
 *
 * The two `load_file` sizes are READ CAPS, not lengths: 0x3840 for the map and 0xea60 for the tile
 * set. 0x3840 is also, and coincidentally, MAP_COLUMNS * MAP_COLUMN_BYTES — the size of the
 * UNPACKED map — so it is not a figure to size a stream buffer from. The twelve shipped LEV*.MAP
 * files are 4,118 to 8,718 bytes, and each is consumed to exactly its own last byte (measured
 * across all twelve; test_scroll.py drives them). */
#define A_tile_set_base  0x4b3beu
/* names.txt has no name for the unpacked side; `map_rle_decompress` @ 0x15920 is what establishes
 * its shape. */
#define A_map_unpacked   0x478aeu

#define MAP_ROWS            18u    /* `move.w #$11,d5` + dbf — words down one column */
#define MAP_COLUMNS        400u    /* `move.w #$190,d6` — columns per row pass */
#define MAP_COLUMN_BYTES  0x24u    /* `lea 36(a1),a1` — the stride between two columns' same row */
#define MAP_RUN_FLAG    0x8000u    /* `bmi` on the token word: set = repeat one tile */
#define MAP_RUN_LENGTH_MASK 0x7fffu /* `and.w #$7fff,d7` */

/* ================================================================================================
 * The page ring. A page is one playfield (video.h's PLAYFIELD_BYTES) at the screen's own 160-byte
 * row stride; the twenty blits below differ only in where in each page row their window starts.
 * ============================================================================================= */
#define SCROLL_PHASES        20u   /* entries in scroll_blit_jump_table (0x179aa) */
#define SCROLL_PHASE_STEP     8u   /* `lea 8(a5),a5` ... `lea 152(a5),a5`: one 16-pixel cell */
#define SCROLL_WINDOW_BYTES 152u   /* 304 of the screen's 320 pixels; the last cell is the edge */

/* ================================================================================================
 * The column workspace the two emitters drain. names.txt: `scroll_col_workspace`.
 * ============================================================================================= */
#define A_scroll_col_workspace 0x19faeu
/* names.txt: set while the scroller is pre-filling the pages with the screen hidden. Non-zero
 * redirects the emitters' SCREEN destination onto their page destination, so the right-edge column
 * is written twice into the page and never onto the display. */
#define A_scroll_prefill_hide_screen 0x19ac1u

#define SCROLL_COLUMN_PASSES     72u  /* `moveq #$47,d0` + dbf — two screen rows a pass */
#define SCROLL_COLUMN_CELL_LONGS  8u  /* `movem.l (a0),#$00ff`: two rows x four planes */
#define SCROLL_COLUMN_ROW_LONGS   4u  /* ...of which one row is four, one per plane */
#define SCROLL_COLUMN_SHIFT_BITS  2u  /* `lsl.l #2,dN` — the 2-pixel step the scroll advances by */

/* ================================================================================================
 * Prototypes. The twenty blits are separate entry points because the original's jump table has
 * twenty, and a reader who greps names.txt for one of them must land on it.
 * ============================================================================================= */
void map_rle_decompress(uint8_t *image);
void blit_page0_to_playfield(uint8_t *image);

void scroll_page_to_screen_p00(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p01(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p02(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p03(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p04(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p05(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p06(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p07(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p08(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p09(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p10(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p11(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p12(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p13(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p14(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p15(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p16(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p17(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p18(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p19(uint8_t *image, uint32_t page, uint32_t screen);

void scroll_emit_column_shift2(uint8_t *image, uint32_t workspace, uint32_t page, uint32_t edge);
void scroll_emit_column_shift0(uint8_t *image, uint32_t workspace, uint32_t page, uint32_t edge);

#endif /* ZYNAPS_SCROLL_H */
