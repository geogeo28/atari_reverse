/* scroll.h — the level map, the off-screen page ring and the column emitters in src/scroll.c.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function". The screen
 * geometry these routines share with the front end lives in video.h, which owns it.
 *
 * HOW THE SCROLLER IS SHAPED, because every routine here is one step of it:
 *
 *   * the level arrives as an RLE stream and is unpacked COLUMN-MAJOR — 400 columns of 18 tile
 *     words — by `map_rle_decompress`;
 *   * `scroll_emit_tile_column` decodes one map column — and the same column of the next map column
 *     along — into a 32-pixel workspace, and `scroll_emit_column_shift2` / `_shift0` walk that
 *     workspace two pixels at a time, emitting the visible half into one of eight off-screen PAGES
 *     and into the screen's right-edge column;
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
/* ...of which one row is four, one per plane. THE PLANE COUNT IS WHAT THIS NUMBER IS, which is why
 * `scroll_emit_tile_column` counts a tile row's four plane WORDS with it as well: the workspace's
 * longs and the tile's words are the same four planes seen at two widths. One fact, one name. */
#define SCROLL_COLUMN_ROW_LONGS   4u
#define SCROLL_COLUMN_SHIFT_BITS  2u  /* `lsl.l #2,dN` — the 2-pixel step the scroll advances by */

/* ================================================================================================
 * The tile decoder, `scroll_emit_tile_column` @ 0x162c2 — the step ahead of the two emitters above.
 * It reads ONE map column (MAP_ROWS words at MAP_COLUMN_BYTES stride) and the same column of the
 * NEXT map column along, decodes both through the tile set at `A_tile_set_base`, and lays 144 rows
 * down in three places at once: the screen's right-edge column, the page's own column, and the
 * workspace, where each longword is `this column's word : the next column's word` — 32 pixels of
 * which the emitters shift the visible 16 out, two pixels a frame.
 * ============================================================================================= */
#define SCROLL_TILE_BYTES      64u  /* `lsl.l #6,d0` — a tile index scaled to its own bytes */
#define SCROLL_TILE_PIXEL_ROWS  8u  /* the eight unrolled row decodes inside each arm */
#define SCROLL_TILE_ROW_BYTES (2u * SCROLL_COLUMN_ROW_LONGS)   /* four plane words */
#define SCROLL_TILE_LAST_ROW (SCROLL_TILE_BYTES - SCROLL_TILE_ROW_BYTES)   /* `lea 56(aN),aN` */
/* `move.w 34(a6),d1`, and the 34 is 36 minus the 2 the `(a6)+` beside it has already stepped: the
 * peek is at the SAME row of the next map column. */
#define SCROLL_MAP_PEEK_NEXT (MAP_COLUMN_BYTES - 2u)
/* Bit 15 of an UNPACKED map word flips its tile vertically. It is the same bit as MAP_RUN_FLAG
 * above and a different fact — that one marks an RLE token in the compressed stream, this one a
 * flipped tile in the map the stream unpacks to — so it gets its own name rather than sharing one. */
#define SCROLL_TILE_FLIP_FLAG  0x8000u  /* `bmi` on the map word */
#define SCROLL_TILE_INDEX_MASK 0x7fffu  /* `and.w #$7fff,dN`, on a flipped word only */

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

/* Returns the map cursor one column on, which its caller stores back into `map_ptr` (0x18242). */
uint32_t scroll_emit_tile_column(uint8_t *image, uint32_t screen_edge, uint32_t page,
                                 uint32_t map_column);

/* ================================================================================================
 * THE ASM TWINS — the .S files in src/asm/, substituted for the cores above on the TARGET build.
 *
 * A twin is a transcription of the ORIGINAL binary's own instruction sequence for one routine,
 * carrying that routine's C signature. The C above stays the reference and stays compiled: it is
 * what the host differential proves equal to the original (test/test_scroll.py) and what the twin
 * is in turn proved equal to (test/test_asm_scroll.py). Nothing here changes what the program
 * computes — only which of two byte-identical implementations of it runs on the Atari.
 *
 * THE SEAM IS AT THE CALL SITE, and deliberately: a twin cannot simply define the core's own name,
 * because src/frame.c's dispatch table and src/scroll.c's own would then bind to whichever the
 * linker saw first. `ZY_SCROLL(fn)` names the one to call, so a reader greping ../names.txt for
 * `scroll_page_to_screen_p07` still lands on every place it is reached from.
 *
 * atari/build.sh defines ZY_ASM_SCROLL and links src/asm/; it also GATES that the twins really
 * arrived, since a twin dropped from the link would otherwise leave the C running and nothing but
 * the frame rate to say so. The host differential build never defines it.
 * ============================================================================================= */
#ifdef ZY_ASM_SCROLL
void scroll_page_to_screen_p00_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p01_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p02_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p03_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p04_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p05_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p06_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p07_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p08_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p09_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p10_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p11_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p12_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p13_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p14_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p15_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p16_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p17_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p18_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_page_to_screen_p19_asm(uint8_t *image, uint32_t page, uint32_t screen);
void scroll_emit_column_shift2_asm(uint8_t *image, uint32_t workspace, uint32_t page, uint32_t edge);
void scroll_emit_column_shift0_asm(uint8_t *image, uint32_t workspace, uint32_t page, uint32_t edge);
uint32_t scroll_emit_tile_column_asm(uint8_t *image, uint32_t screen_edge, uint32_t page,
                                     uint32_t map_column);
#define ZY_SCROLL(fn) fn##_asm
#else
#define ZY_SCROLL(fn) fn
#endif

#endif /* ZYNAPS_SCROLL_H */
