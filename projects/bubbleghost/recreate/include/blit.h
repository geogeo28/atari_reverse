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
 * this header to READ it (README.md, "Adding a function"). The room and object TABLES this
 * subsystem draws from are `include/gameplay.h`'s, and `src/blit.c` includes that header to read
 * them — they were on loan here until the gameplay subsystem landed.
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
#define TILE_ROW_DEST_STEP_BYTES (SCREEN_ROW_BYTES - TILE_ROW_BYTES)
                                        /* 144 = the tile blit's own `adda.w #$90,a2`: what the
                                         * destination still needs once the row's four copies have
                                         * carried it TILE_ROW_BYTES along */
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
/* ...and the sound around it, which every voice is silenced for first. WHICH definition it plays is
 * `include/sound.h`'s `SND_FX_ROOM_WIPE`, with the rest of the fx table's indices. */
#define WIPE_SFX_VOICE          0
#define WIPE_SFX_VOLUME         8       /* `muls.w #$8` on `sound_enabled` */
#define WIPE_SFX_NOTE        0x3c
#define WIPE_SFX_PRIORITY       5

/* ---- the object and room records ---------------------------------------------------------------
 * `objects_animate_and_draw` steps the 14-byte object slots and `draw_room_to_stage` reads the
 * room's 5 x 10 tile map, but neither record is this subsystem's: both live in
 * `include/gameplay.h`, which `src/blit.c` includes to read them. They were defined HERE on loan
 * while the gameplay subsystem was unported, and STATUS.md's "Borrowed globals" rows predicted
 * exactly this move. */

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
/* Answers the A2 it leaves behind — one tile band past the destination it started from — because
 * `draw_room_to_stage`'s NEXT cell traps with that in A2 and the trampoline files it. Reported by
 * the routine that computes it rather than re-derived by the caller: `src/frontend.c` carried the
 * derivation as a second copy of the destination arithmetic until this return type existed. */
uint32_t draw_room_tile_to_stage(uint8_t *image, int16_t tile_row, int16_t tile_col);
void room_wipe_in(uint8_t *image);
void room_wipe_in_slide(uint8_t *image);
void room_wipe_in_step(uint8_t *image, int16_t step);

#endif /* BG_BLIT_H */
