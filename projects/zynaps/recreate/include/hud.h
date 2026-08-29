/* hud.h — the status panel and the front-end screens (src/hud.c). Subsystem: hud.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 *
 * THE PANEL IS THE BOTTOM 53 ROWS of the 200-row frame, rows 147..199, and nothing here clips: every
 * routine writes a block at an address that is a LITERAL in its own instructions, so a case can vary
 * only what was under it. The graphics all live in bss — `_start` loads POWER.DAT, SMLOGOS.DAT,
 * LIFEGRA.DAT, ZYNLOGO.DAT and STATUS.PI1 over it — so a test that draws anything has to stage the
 * real file bytes, exactly as text.h's font does. Against the zeroed bss every blit would write
 * zeroes and a wrong SOURCE address would be invisible.
 */
#ifndef ZYNAPS_HUD_H
#define ZYNAPS_HUD_H

#include <stdint.h>

/* ================================================================================================
 * The graphics, in bss. Each address is where `_start` loads (or builds) the block; the length
 * beside it is the one `_start` passes `load_file`, not the file's own size on disk.
 * ============================================================================================= */
#define A_power_gauge_frames 0x607beu   /* POWER.DAT, 0x400: four 64x8 four-plane frames */
#define A_smlogos_frames     0x6b46eu   /* SMLOGOS.DAT, 0xa00: two 80x32 frames */
#define A_zynaps_logo        0x6c8eeu   /* ZYNLOGO.DAT, 0x1800: three 32x64 column strips */
#define A_life_icons         0x6c8aeu   /* LIFEGRA.DAT: the full icon then the empty one */
/* The three panel strips are NOT loaded from a file: `_start` carves them back out of the panel
 * image it has just stamped into the screen (0x10564..0x105c4), so their bytes are STATUS.PI1's,
 * read at the screen offset each strip is later redrawn to. names.txt names none of the three. */
#define A_hiscore_panel_strip 0x6c5eeu  /* 8 rows x 40 bytes, from row 188 byte 24 */
#define A_score_panel_strip   0x6c72eu  /* 8 rows x 40 bytes, from row 151 byte 120 */
#define A_player_panel_strip  0x6c86eu  /* 8 rows x  8 bytes, from row 182 byte 120 */
/* STATUS.PI1's own 0x2120 bytes, and the address `status_panel_build_master` snapshots the finished
 * panel back to — one buffer under two uses, the way video.h's A_backdrop_page0 is. */
#define A_panel_master 0x41eaeu

/* ================================================================================================
 * The tables and the state bytes.
 * ============================================================================================= */
/* Longword pointers into SWEAP.DAT / SSWEAP.DAT, indexed by the two cursor bytes below. Both tables
 * are in the .PRG's text, so a case reads the game's own pointers rather than staging any. */
#define A_hud_powerup_icons 0x1931cu
#define A_hud_weapon_icons  0x19330u
#define A_powerup_cursor      0x19905u  /* .b — which power-up-bar icon is showing */
#define A_powerup_active_slot 0x19906u  /* .b # ctx — names.txt's second reading is
                                         * `weapon_icon_index`, which is what this routine uses it
                                         * as: it indexes A_hud_weapon_icons */
#define A_panel_logo_frame  0x1990eu    /* .b — toggled every repaint; picks the smlogos frame */
#define A_power_gauge_display 0x198c3u  /* .b # ctx — the HUD's mirror of the shield level;
                                         * names.txt's second reading is `power_gauge_level` */
#define A_panel_redraw_mask 0x19904u    /* .b — one bit per panel element that wants a repaint */
/* The only bit any ported routine names: `bset #4` when a life is awarded (src/score.c) and
 * `bclr #4` once the icons have been redrawn (`draw_lives_icons`). */
#define PANEL_REDRAW_LIVES_BIT 4u
#define A_show_prepare_for_combat 0x19aacu  /* .b — nonzero adds the second line to the intro */
/* The sixteen-pen row the front-end screens install into irq.h's A_menu_palette. names.txt calls it
 * `palette_frontend`; ../out/globals.tsv assigns it to no subsystem, and this is its first use. */
#define A_palette_frontend 0x195f8u

/* ---- BORROWED: two player globals with no home yet -------------------------------------------
 *
 * ../out/globals.tsv puts both in the **player** subsystem, but `include/player.h` does not spell
 * either — no ported player routine reads them. A subsystem reads another's global by including its
 * header rather than restating the address (README.md), so these two belong there and are here only
 * until they exist there. `test_constants.py`'s duplicate-address check is what will say so if both
 * spellings ever stand at once.
 *
 * THE MOVE IS FOUR EDITS, NOT ONE, and doing part of it reddens the hud battery rather than the
 * player one: delete these two lines, repoint `test_hud.py`'s and `test_score.py`'s MIRRORS rows at
 * `include/player.h`, and swap `src/score.c`'s `#include "hud.h"` for `"player.h"`.
 *
 * `A_lives` IS WRITTEN FROM HERE, not only read — `src/score.c`'s extra-life award does
 * `image[A_lives]++`, from a different translation unit than any player routine. globals.tsv
 * classifies it `read`, which is what a reader of that file alone would take it for. Both names are
 * `# ctx` in ../names.txt (`lives` / `lives_remaining`, `current_player_index` / `current_player`).
 */
#define A_lives 0x1991au                 /* .b # ctx — lives of the live player */
#define A_current_player_index 0x1991bu  /* .b # ctx — 0 or 1 */

/* ================================================================================================
 * Where the panel routines draw.
 *
 * MOST OF THEM CARRY THE BUFFER AS A LITERAL rather than reading the pointer pair the flip swaps:
 * `lea $760c8.l,a0` is the back buffer plus a panel offset, worked out at assembly time. The panel
 * is only ever drawn into both buffers at once, so which one is currently in front does not matter
 * to it — and that is why these two constants exist beside video.h's A_screen_back /
 * A_screen_front, which are the POINTER WORDS at 0x1797e/0x17982 and not the buffers they name.
 * `draw_power_gauge` is the one that does read the pointers, and `status_panel_redraw_all` mixes
 * both — which is why src/hud.c hands some of its pieces a pointer's value and some of them these.
 *
 * BORROWED, on the same terms as the two player globals below: these are the VIDEO subsystem's
 * data — `include/video.h`'s framebuffer block is where they belong, beside the pointer words that
 * name them, and `test/abi.py` already holds the same two numbers as SCREEN_BACK / SCREEN_FRONT for
 * the scratch map. They are here only because no ported video routine needs the absolute bases yet;
 * the first scroll/sprite/video routine that does should MOVE them into video.h and repoint
 * `test_hud.py`'s two MIRRORS rows, rather than spell a third name for either address —
 * `test_constants.py`'s duplicate-address check would refuse that, but only after the merge.
 * ============================================================================================= */
#define A_screen_back_buffer  0x70300u
#define A_screen_front_buffer 0x78000u

/* Panel geometry. Every one of these is a `lea` displacement or an immediate in the routine that
 * uses it; they are named because a bare 24280 hides which row and column of the panel it is. Each
 * offset is from a buffer's own base, and the same offset serves both buffers. */
/* The animated ZYNAPS logo: `eori.b #$1` picks one of two frames, blitted at x=16, y=150. */
#define LOGO_ANIM_FRAMES     2u
#define LOGO_ANIM_FRAME_BYTES 0x500u  /* `mulu.w #$500,d0` — 32 rows x 40 bytes */
#define LOGO_ANIM_ROWS       32u
#define LOGO_ANIM_CELLS      5u       /* five 16-pixel groups, each its own 256-byte column */
#define LOGO_ANIM_CELL_BYTES 8u       /* ...and one row of one group is 8 bytes */
#define LOGO_ANIM_CELL_STRIDE 0x100u  /* `256(a2)`, `512(a2)`, ... — the gap between two columns */
#define LOGO_ANIM_OFFSET     0x5dc8u  /* row 150, byte 8 */

/* The 32x26 power-up-bar icon and the 16x18 weapon glyph. */
#define POWERUP_ICON_ROWS 26u
#define POWERUP_ICON_ROW_BYTES 16u
#define POWERUP_ICON_OFFSET 0x5ec0u        /* row 151, byte 96 */
#define WEAPON_ICON_ROWS 18u
#define WEAPON_ICON_ROW_BYTES 8u
#define WEAPON_ICON_OFFSET 0x5d60u         /* row 149, byte 64 */
#define WEAPON_ICON_RIGHT_CELL_BYTES 16u   /* `lea 16(a0),a0` — the second glyph, 32 pixels along */
#define ICON_TABLE_ENTRY_BYTES 4u          /* `lsl.w #2,d0` — the tables hold longword pointers */

/* The power gauge: four 64x8 frames, drawn into both buffers at row 188 byte 72. */
#define POWER_GAUGE_FRAMES 4u
#define POWER_GAUGE_FRAME_BYTES 0x100u  /* `mulu.w #$100,d0` — 8 rows x 32 bytes */
#define POWER_GAUGE_ROWS 8u
#define POWER_GAUGE_ROW_BYTES 32u
#define POWER_GAUGE_OFFSET 0x75c8u

/* The six life icons, at row 167 columns 32..37 in both buffers. LIFEGRA.DAT holds two 8x8 glyphs
 * back to back — the full icon then the empty one — as four plane bytes a row. */
#define LIVES_ICONS 6u
#define LIFE_ICON_ROWS 8u
#define LIFE_ICON_ROW_BYTES 4u        /* one byte per plane, and the planes are 2 apart on screen */
#define LIFE_ICON_BYTES (LIFE_ICON_ROWS * LIFE_ICON_ROW_BYTES)
#define LIVES_FIRST_COLUMN 0x20u      /* `move.w #$20,d1` */
#define LIVES_ROW_OFFSET 0x6860u      /* row 167, byte 0 */

/* The player digit the panel shows, drawn HALF A CELL to the right: the glyph is rotated four
 * pixels inside its word, so it needs a word-wide read-modify-write rather than draw_char's byte
 * one. The glyph is the font's, one past the digit the player index names ('1' for player 0). */
#define PLAYER_DIGIT_SHIFT 4u
#define PLAYER_DIGIT_GLYPH_BIAS 1u
#define PLAYER_DIGIT_ROW_ADVANCE 152u  /* `lea 152(a0),a0` — the row's 160 less the 8 just walked */

/* The three panel strips, and where each is stamped. The score and hi-score strips are 40 bytes a
 * row (`movem.l #$07fe`, ten longwords); the player strip is 8 (two `move.l`s). */
#define PANEL_STRIP_ROWS 8u
#define PANEL_STRIP_ROW_BYTES 40u
#define PLAYER_STRIP_ROW_BYTES 8u
#define SCORE_STRIP_OFFSET   0x5ed8u  /* row 151, byte 120 */
#define SCORE_DIGITS_OFFSET  0x5e60u  /* row 151, byte 0 — draw_bcd_number takes the ROW's base */
#define SCORE_RIGHTMOST_COLUMN 0x26u  /* `move.w #$26,d1` — column 38 */
#define PLAYER_STRIP_OFFSET  0x7238u  /* row 182, byte 120 */
#define HISCORE_STRIP_OFFSET 0x7598u  /* row 188, byte 24 */
#define HISCORE_DIGITS_OFFSET 0x7580u /* row 188, byte 0 */
/* The hi-score digits' rightmost column is NOT spelt here: it is the same `move.w #$e,d1` the
 * role-of-honour screen uses, and `include/highscore.h`'s HIGHSCORE_DIGITS_COLUMN owns it. A second
 * name for it would be a value `test_constants.py` cannot catch — its duplicate check compares
 * NAMES, and its address check covers only the `A_*` family. */

/* The finished panel, snapshotted so a level change can stamp it back without rebuilding it. */
#define PANEL_TOP_OFFSET 0x5be0u        /* row 147, byte 0 — the panel's first row */
#define PANEL_MASTER_LONGWORDS 0x848u   /* `move.w #$847,d0` + `dbf` — 8480 bytes, 53 rows */

/* ================================================================================================
 * The two logos the front-end screens blit, and the ONE POINTER that walks both.
 *
 * `blit_graphic_block` (video.h) advances its source, so a screen loads A6 once and the strips
 * chain: three 64-row strips exhaust ZYNLOGO.DAT's 0x1800 bytes and A6 then runs straight on into
 * HEWLOGO.DAT, which `_start` loads at the very next address. `title_screen_draw` uses that — its
 * second pair of strips is the Hewson logo and it never reloads A6. Each strip is 32 pixels wide
 * (video.h's GRAPHIC_BLOCK_ROW_BYTES), so three of them side by side are the 96-pixel logo.
 * ============================================================================================= */
#define A_hewson_logo 0x6e0eeu  /* HEWLOGO.DAT, 0x600 — and A_zynaps_logo + 0x1800 */
#define LOGO_STRIPS 3u
#define LOGO_STRIP_LAST_ROW 0x3fu    /* `move.w #$3f,d0` — a `dbf` count, so 64 rows */
#define LOGO_STRIP_BYTES 0x800u      /* 64 rows x 32 bytes */
#define HEWSON_LOGO_STRIPS 2u
#define HEWSON_STRIP_LAST_ROW 0x17u  /* 24 rows */
#define HEWSON_STRIP_BYTES 0x300u
#define LOGO_TITLE_OFFSET  0x668u    /* row 10, byte 40 — the title and role-of-honour screens */
#define LOGO_INTRO_OFFSET  0x348u    /* row 5, byte 40 — the per-player intro */
#define HEWSON_LOGO_OFFSET 0x39b0u   /* row 92, byte 48 — the title screen only */

/* The text records these screens print live in `include/text.h`, which is where ../out/globals.tsv
 * puts them and what owns the record format they are in. This header includes it for them. */
#define PLAYER_DIGIT_CHAR_ZERO 0x31u    /* `add.b #$31,d0` — player 0 draws '1', not '0' */
#define PLAYER_NAME_ROW_OFFSET 0x3200u  /* `lea 12800(a0),a0` — row 80, where the digit goes */

/* ================================================================================================
 * Prototypes. Each takes the whole image; the addresses above are the routine's own literals.
 * ============================================================================================= */
void hud_draw_logo_anim(uint8_t *image);
void hud_draw_powerup_icon(uint8_t *image);
void hud_draw_weapon_icon(uint8_t *image, uint8_t right_cell);
void draw_power_gauge(uint8_t *image);
void draw_lives_icons(uint8_t *image);
void draw_player_digit_shifted(uint8_t *image, uint32_t cell);
void draw_score_panel(uint8_t *image, uint32_t buffer);
void status_panel_build_master(uint8_t *image);
void status_panel_redraw_all(uint8_t *image);
void player_intro_screen(uint8_t *image);
void title_screen_draw(uint8_t *image);

/* Three 64-row strips of A_zynaps_logo into `buffer` at `offset`, the way every front-end screen
 * opens — shared with src/highscore.c's role-of-honour screen, which draws the same three. */
void hud_blit_zynaps_logo(uint8_t *image, uint32_t buffer, uint32_t offset);

#endif /* ZYNAPS_HUD_H */
