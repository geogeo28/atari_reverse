/* blit.h — the screen, the 32x32 tile, and the RAW copy loops that move them.
 *
 * Bubble Ghost has two drawing families (../notes/gameplay.md, "The blitters"). This subsystem is
 * the RAW one: unrolled `move.l (a3)+,(a2)+` runs over the two 32,000-byte screens, plus the one
 * tile blit every background draw shares. The other family goes through the game's own VDI binding
 * (`vro_cpyfm` @ 0x16b12) and is NOT here — the kit's TOS model refuses `trap #2` VDI opcode 109,
 * so those routines cannot be run by the differential at all (STATUS.md, "Model gaps").
 *
 * THIS SUBSYSTEM OWNS THE SCREEN. `A_screen_phys` / `A_screen_back` / `A_dat_bank` /
 * `A_bank_index` and the geometry below live here, and another subsystem that needs one includes
 * this header to READ it (README.md, "Adding a function"). Three globals at the bottom are
 * BORROWED from subsystems that are not ported yet; STATUS.md's "Borrowed globals" carries the loan.
 */
#ifndef BG_BLIT_H
#define BG_BLIT_H

#include <stdint.h>

/* ---- screen geometry -------------------------------------------------------------------------
 * 320x200 low resolution: four bit-planes interleaved word by word, so a 16-pixel cell is 8 bytes
 * and a scanline is 160. `init_gem_and_screens` @ 0x10118 asks XBIOS for Logbase and puts the work
 * buffer SCREEN_BYTES below it, so the two screens are adjacent (../notes/frontend.md, §5). */
#define SCREEN_ROW_BYTES        160u    /* 320 px x 4 planes / 8; the blit's `adda.w #$90` + 16 */
#define SCREEN_PLANES           4u      /* the MFDB field, and why a 32-px cell row is 16 bytes */
#define SCREEN_BYTES            32000u  /* 200 rows; `Logbase - 0x7d00` is screen_back */
#define CLEARED_SCREEN_BYTES    30720u  /* `move.w #$1dff` + dbf = 7,680 longs = the top 192 rows,
                                         * which is all a full-screen picture ever covers */

/* ---- the tile ---------------------------------------------------------------------------------
 * Every background graphic in this game is a 32x32 four-plane cell, stored row-major inside a
 * GHOST.DAT bank. Tile n is `dat_bank[n / TILES_PER_BANK] + (n % TILES_PER_BANK) * TILE_BYTES`. */
#define TILE_PIXELS             32u     /* rows per tile, and its width in pixels */
#define TILE_ROW_BYTES          16u     /* 4 x `move.l (a3)+,(a2)+`: 32 px x 4 planes */
#define TILE_BYTES              512u    /* `muls.w #$200`: TILE_PIXELS x TILE_ROW_BYTES */
#define TILE_ROW_SCREEN_BYTES   0x1400u /* `muls.w #$1400`: TILE_PIXELS screen rows = 5,120 bytes.
                                         * Also exactly what `present_hud_row` copies */
#define TILES_PER_BANK          60u     /* `divs.w #$3c` / `muls.w #$3c`: 30,720 / TILE_BYTES */
#define DAT_BANKS               7u      /* dat_bank[0..5] = GHOST.DAT, [6] = the GHOST.PRE picture */

/* ---- the tile grids ---------------------------------------------------------------------------
 * A room is 10 x 5 tiles (rows 0..159); the HUD is one more tile row (rows 160..191); the bank
 * screen `build_sprite_bank` grabs its sprites off is 10 x 6, i.e. one whole 60-tile bank. */
#define ROOM_TILE_COLS          10u     /* `cmpi.w #$a` in every column loop */
#define ROOM_TILE_ROWS          5u      /* `cmpi.w #$5` in draw_room_to_stage */
#define BANK_TILE_ROWS          6u      /* `cmpi.w #$6` in draw_tile_bank_screen */
#define ROOM_BYTES              0x6400u /* 25,600 = ROOM_TILE_ROWS x TILE_ROW_SCREEN_BYTES. The room
                                         * area of a screen, the offset of the HUD row above it, and
                                         * the distance DOWN from screen_back to the staging area */
#define SCORE_STRIP_OFFSET      0x6540u /* `add.l #$6540`: the counters' band inside the HUD row */
#define SCORE_STRIP_BYTES       4096u   /* `move.w #$3ff` + dbf = 1,024 longs */

/* ---- the HUD row's source ---------------------------------------------------------------------
 * draw_hud_row_tiles reads bank 5 through the absolute `-7644(a4)` = &dat_bank[5], not through
 * bank_index: the HUD tiles 350..359 are that bank's last ten. */
#define HUD_TILE_BANK           5u
#define HUD_FIRST_TILE_IN_BANK  50u     /* tile 350 = 5 * TILES_PER_BANK + 50; `add.l #$6400` is
                                         * this times TILE_BYTES, and is NOT ROOM_BYTES' 0x6400 */

/* ---- room_wipe_in's slide ---------------------------------------------------------------------
 * The staged room is moved down four scanlines at a time and the part of screen_back it has
 * reached is presented after each step, so the room appears to slide in from the top. */
#define WIPE_STEPS              40u     /* `cmpi.w #$28,d7`: 40 x 4 rows = the room's 160 rows */
#define WIPE_STEP_BYTES         640u    /* `move.w #$280`: four scanlines */

/* ---- the object records the animator steps ----------------------------------------------------
 * 36 rooms x 10 slots x 14 bytes (../notes/gameplay.md, §4). BORROWED layout — see the note on
 * A_object_table below.
 *
 * PROVENANCE. The Alcyon compiler reaches each field through its OWN `lea -n(a4),a0`, so every
 * offset below is a displacement read off one named instruction rather than a layout inferred from
 * the record's shape — and each is DIFFERENTIAL-pinned by `test/test_blit.py`'s object cases, which
 * poke the fields by these offsets and compare the whole image (a wrong offset moves both what the
 * routine reads and what it writes). `A_object_table` is `A4_BASE - 18560`, so the displacement
 * NAMES the offset: -18560 is field 0, -18558 is field 2, and so on. */
#define OBJECT_SLOTS            10u     /* `cmpi.w #$a` @ 0x1394c */
#define OBJECT_STRIDE           14u     /* `muls.w #$e` @ 0x13790 */
#define OBJECT_ROOM_STRIDE      140u    /* `muls.w #$8c` @ 0x13786 = OBJECT_SLOTS x OBJECT_STRIDE */
/* word: base GHOST.DAT tile; negative = empty slot. `lea -18560(a4)` @ 0x1378a; pinned by
 * test_blit.py::test_objects_animate_and_draw_word_edge_branches */
#define OBJECT_TILE             0u
/* word: frames left; the frame steps when it is already 0. `lea -18558(a4)` @ 0x137ac; pinned by
 * test_blit.py::test_objects_animate_and_draw_countdown_reaches_zero_and_reloads */
#define OBJECT_COUNTDOWN        2u
/* word: what COUNTDOWN is reloaded with. `lea -18556(a4)` @ 0x137d2; pinned by the same case */
#define OBJECT_RELOAD           4u
/* word: tile column 0..9. `lea -18554(a4)` @ 0x12d54; pinned by
 * test_blit.py::test_objects_animate_and_draw_fuzz, which varies it over the grid */
#define OBJECT_X                6u
/* word: tile row 0..4. `lea -18552(a4)` @ 0x12d88; pinned by the same case */
#define OBJECT_Y                8u
/* word: animation frame; the tile drawn is TILE + FRAME. `lea -18550(a4)` @ 0x1380a; pinned by
 * test_blit.py::test_objects_animate_and_draw_shipped_rooms */
#define OBJECT_FRAME            10u
/* word: FRAME wraps to 0 when it reaches this minus one. `lea -18548(a4)` @ 0x13828; pinned by
 * test_blit.py::test_objects_animate_and_draw_countdown_reaches_zero_and_reloads, which arms the
 * wrap on the same slot that reloads */
#define OBJECT_FRAME_COUNT      12u

/* ---- the room record the stage draw reads -----------------------------------------------------
 * 36 rooms x 120 bytes, opening with a 5 x 10 word tile map. BORROWED, as above, and pinned the
 * same way: `test/test_blit.py`'s `draw_room_to_stage` cases poke a map cell computed from these
 * three and the tile that lands on the screen is what says the address was right. */
#define ROOM_STRIDE             120u    /* `muls.w #$78` @ 0x13a40 */
#define ROOM_MAP_ROW_BYTES      20u     /* `muls.w #$14` @ 0x13a4a = ROOM_TILE_COLS words */
#define ROOM_MAP_CELL_BYTES     2u      /* `asl.l #1,d0` @ 0x13a58: a map cell is a word */

/* ---- the two MFDBs build_sprite_bank hands to vro_cpyfm ---------------------------------------
 * A GEM Memory Form Definition Block. Only the six fields below exist; `fd_addr` = 0 is the VDI's
 * "the screen", which for this program means screen_back (../notes/frontend.md, §1). */
#define MFDB_ADDR               0u      /* long */
#define MFDB_WIDTH              4u      /* word, in pixels */
#define MFDB_HEIGHT             6u      /* word, in rows */
#define MFDB_WDWIDTH            8u      /* word, width in 16-bit words */
#define MFDB_STANDARD           10u     /* word, 0 = device-specific format */
#define MFDB_PLANES             12u     /* word */
#define MFDB_SPRITE_WDWIDTH     2u      /* TILE_PIXELS / 16: what a 32-px cell is in VDI words */

/* ---- globals this subsystem owns -------------------------------------------------------------- */
#define A_screen_phys           0x23148u  /* long: XBIOS Logbase, the visible screen */
#define A_screen_back           0x2314cu  /* long: Logbase - SCREEN_BYTES, the work buffer */
#define A_dat_bank              0x2312au  /* long[DAT_BANKS]: the picture buffers */
#define A_bank_index            0x2311eu  /* word: which dat_bank[] draw_tile_bank_screen paints */
#define A_mfdb_src              0x23100u  /* the source MFDB build_sprite_bank fills in */
#define A_mfdb_dst              0x230ecu  /* ...and the destination one */

/* ---- BORROWED globals ------------------------------------------------------------------------
 * These belong to the GAMEPLAY subsystem (the rooms and their objects), which is not ported yet.
 * Each is a LOAN with a row in STATUS.md, "Borrowed globals": when `include/gameplay.h` appears,
 * `test_constants.py`'s duplicate check is what will say so — in the OTHER agent's diff — and
 * deleting the row and the three defines below is the whole of the migration. The record layouts
 * above (OBJECT_*, ROOM_*) move with them. */
#define A_room_number           0x23120u  /* word: 0..35, = room_grid[grid_row][grid_col] */
#define A_object_table          0x2069au  /* 36 rooms x OBJECT_ROOM_STRIDE bytes */
#define A_room_table            0x21a4au  /* 36 rooms x ROOM_STRIDE bytes */

/* ---- cores ----------------------------------------------------------------------------------- */
void clear_physical_screen(uint8_t *image);
void present_room(uint8_t *image);
void present_hud_row(uint8_t *image);
void present_score_strip(uint8_t *image);
void stage_to_work(uint8_t *image);
void draw_tile_bank_screen(uint8_t *image);
void draw_hud_row_tiles(uint8_t *image);
void objects_animate_and_draw(uint8_t *image);
void build_sprite_bank_prepare(uint8_t *image);
void draw_room_tile_to_stage(uint8_t *image, int16_t tile_row, int16_t tile_col);
void room_wipe_in_slide(uint8_t *image);
void room_wipe_in_step(uint8_t *image, int16_t step);

#endif /* BG_BLIT_H */
