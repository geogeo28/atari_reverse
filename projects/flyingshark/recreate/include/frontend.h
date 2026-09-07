/* frontend.h — the title screen, the asset loader's filename patch, the hall-of-fame name entry and
 * the one scenery animation that is not part of the scroller.
 *
 * These are the routines that run BETWEEN games, plus two that run during one and belong to nothing
 * else: `level2_scenery_effect` @ 0x1003c, a hand-blitted band that grows and shrinks across a
 * window of level 2, and `debug_wait_for_keypad4` @ 0x11ba2, a single-step hook with no caller.
 *
 * WHAT IS NOT HERE. The scroller block — `A_scroll_pos`, `A_scroll_fine`, the map cursor, the
 * prescroll flag — is `include/scroll.h`'s, and the title screen's own stage start is two of that
 * subsystem's cores rather than a copy of them here. The hall-of-fame table, the glyph alphabet and
 * the name-entry counters that `hiscore_show_entry_screen` also writes are `include/hud.h`'s. This
 * header defines only what its own routines OWN.
 *
 * PROVENANCE. Every `A_*` is a `var` line in ../names.txt at load base 0x10000 and every routine
 * address an `fn` line; the instruction that establishes each figure is named beside it, read off
 * ../out/prg_dis.txt. ../notes/frontend.md has the prose.
 */
#ifndef FS_FRONTEND_H
#define FS_FRONTEND_H

#include <stdint.h>

#include "globals.h"
#include "hud.h"      /* the hiscore table and its counters, the glyph alphabet, `A_key_bits` */
#include "scroll.h"   /* the two stage-start cores the title screen shares with `start_level` */

/* ---- load_level_assets @ 0x10332: one record set, five stages ----------------------------------
 *
 * The four "A\HSC_n.DAT" records and the "A\LEVEL1.MAP" record are the ONLY ones the game has, and
 * the routine rewrites a digit inside each name before it opens them — so the same five records
 * serve every stage. The digits come five at a time out of a table indexed by the level number.
 */
#define A_level_bank_digits 0x162d4u /* `lea $162d4,a0` @ 0x10332 */
#define LEVEL_BANK_DIGITS   5u       /* `muls.w #$5,d0` @ 0x1033a — four bank digits and a map one */
#define HSC_NAME_DIGIT      6u       /* `move.b (a0)+,6(a2)` @ 0x10346, with a2 on the record's
                                      * NAME field: the '0' of "A\HSC_0.DAT" */
#define MAP_NAME_DIGIT      7u       /* `move.b (a0),7(a2)` @ 0x1036e: the '1' of "A\LEVEL1.MAP" */

/* ---- title_attract_loop @ 0x104f2: the stage start the attract screen does ---------------------- */
#define TITLE_SCROLL_POS_START 0u    /* `move.w $176ac,$17758` @ 0x104f6 — `A_const_words_0123`
                                      * index 0, this program's way of spelling a zero */

/* ---- level2_scenery_effect @ 0x1003c ----------------------------------------------------------
 *
 * A band of tiles blitted straight onto the draw screen — no display record, no map cell — over a
 * window of level 2's scroll. It GROWS while `level_distance` is inside the first half of the
 * window and SHRINKS through the second, and the three counters below are the whole of its state.
 */
#define A_scenery_band_offset  0x17798u /* `adda.w $17798,a5` @ 0x100ce — a SIGNED word offset from
                                         * `A_screen_draw` to the band's top-left corner */
#define A_scenery_band_rows    0x1779eu /* `move.w $1779e,d6` @ 0x100d4 — whole tile rows */
#define A_scenery_band_partial 0x177a0u /* `move.w $177a0,d5` @ 0x100da — scanlines of the row below
                                         * the whole ones, 0..32 */
#define A_charset_order_table  0x177a6u /* `lea $177a6,a6` @ 0x100e0 — the tile ids the band is made
                                         * of, one byte a tile, read forward and never reset within
                                         * a call. Initialised DATA ('89:;<=>?01234567,-./ !"#$%&'),
                                         * and this routine is its only reader */

#define SCENERY_WINDOW_START 0x8a2u /* `cmpi.w #$8a2,$1779a` @ 0x1003c — below this, nothing */
#define SCENERY_WINDOW_GROW  0x96eu /* `cmpi.w #$96e,$1779a` @ 0x10058 — the growing half ends */
#define SCENERY_WINDOW_END   0x9c6u /* `cmpi.w #$9c6,$1779a` @ 0x10090 — above this, nothing */
#define SCENERY_BAND_OFFSET_SEED 0x8100u /* `move.w #$8100,$17798` @ 0x10050, on the ONE frame
                                          * `level_distance` equals SCENERY_WINDOW_START */
#define SCENERY_BAND_ROWS_MAX 0x20u /* `cmpi.w #$20,$177a0` @ 0x10068 and `move.w #$20,$177a0`
                                     * @ 0x100a4 — the partial row is full at 32 scanlines and
                                     * carries into a whole row */
#define SCENERY_GROW_OFFSET_STEP   0xa0u  /* `subi.w #$a0,$17798` @ 0x10086 — the band's top rises
                                           * four scanlines a frame while it grows */
#define SCENERY_SHRINK_OFFSET_STEP 0x140u /* `addi.w #$140,$17798` @ 0x100c0 — and falls eight
                                           * while it shrinks */
#define SCENERY_SHRINK_ROW_STEP    2u     /* `subq.w #2,$177a0` @ 0x100b2 */
#define SCENERY_COLUMNS            4u     /* `move.w #$3,d7` + `dbf` @ 0x100ec and @ 0x10292 */
#define SCENERY_TILE_BANK          2u     /* `lea $48928,a4` @ 0x100f8 = `A_tile_banks` + 2 banks —
                                           * the THIRD HSC file of the stage */
#define SCENERY_COLUMN_LONGS       4u     /* the four `move.l (a4)+,(a5)+` a row of a column is */

#define SCENERY_GATE_LEVEL 2u /* `cmpi.w #$2,$1642a` @ 0x10bc8 — `A_level_number`
                               * (include/player.h); the effect is level 2's alone */

/* ---- debug_wait_for_keypad4 @ 0x11ba2 ---------------------------------------------------------
 *
 * Spin until keypad '4' is held. NO CALLER — a leftover single-step hook — and the same key bit
 * `check_cheat_name` arms on, so `CHEAT_ARM_KEY_BIT` (include/hud.h) is the one spelling of it.
 * Unlike that spin this one has no bound at all: it returns only when the ACIA interrupt sets the
 * bit, which is what makes the kit's SCHEDULED WRITE model the only way to run it off target.
 */
#define DEBUG_WAIT_KEY_PC 0x11ba6u /* the `btst #0,$17780` the loop re-reads the byte at */

/* ---- hiscore_name_entry @ 0x10916 -------------------------------------------------------------
 *
 * Three initials, one glyph at a time, into `A_hiscore_table` + HISCORE_STRIDE * rank + HISCORE_NAME
 * (include/hud.h). The counters below are what this routine adds to the ones that header carries.
 */
#define A_name_entry_first_pass 0x176d6u /* `tst.w $176d6` @ 0x10938 — clear until the three glyphs
                                          * have been filled with spaces once. `init_new_game`
                                          * @ 0x11364 is the other writer */
#define A_name_entry_cursor     0x176e2u /* `adda.w $176e2,a0` @ 0x10956 — 0, 1 or 2 */
#define NAME_ENTRY_LAST_CURSOR  2u       /* `cmpi.w #$2,$176e2` @ 0x109aa: the third fire confirms */
#define NAME_ENTRY_TIMEOUT_RELOAD 0x32u  /* `move.w #$32,$176de` @ 0x109f6 — the frames the finished
                                          * name is left on screen before the attract resumes */
/* The two joystick-1 bits this routine reads, named for what they do HERE. They are `src/player.c`'s
 * JOY_RIGHT_BIT and JOY_LEFT_BIT — the same stick, the same bits — and the flight code's names would
 * read as movement at a site where the stick picks a letter. */
#define NAME_ENTRY_NEXT_GLYPH_BIT 3u /* `btst #3,$1777f` @ 0x1095c — stick right */
#define NAME_ENTRY_PREV_GLYPH_BIT 2u /* `btst #2,$1777f` @ 0x10976 — stick left */
/* The two effects it arms are `sfx_play_5` @ 0x121ce (either direction) and `sfx_play_2` @ 0x121e6
 * (the button); both are `include/sound.h`'s wrappers and carry their own effect number. */

/* ================================================================================================
 * The cores. Each takes the flat image; `load_level_assets_patch_filenames` is the only one that
 * takes an argument, and it is the D0 the caller loads with the level number.
 * ============================================================================================= */

/* `load_level_assets` @ 0x10332, SLICE [0x10332, 0x10372): the five filename digits, up to the first
 * `bsr load_file`. The rest of the routine is a sequence of calls into `load_file` @ 0x10bfa, which
 * is the `init` subsystem's and is verified now — so the span stops there because that is where
 * this slice's own work ends, not because anything past it is missing. */
void load_level_assets_patch_filenames(uint8_t *image, uint16_t level);

/* `title_attract_loop` @ 0x104f2, SLICE [0x104f6, 0x1054a): the attract screen's stage start —
 * scroll position, scroll phase, map cursor, and the whole screen scrolled in with the palette
 * black. The entry instruction is a `bsr set_palette_black` (the `init` subsystem's, and verified),
 * so the slice starts after it, and it ends where the attract poll begins — the loop past that
 * point is one spin with four exits and no checkpoint a slice could stop at. */
void title_attract_prescroll(uint8_t *image);

/* `level2_scenery_effect` @ 0x1003c and its caller `level2_scenery_effect_gate` @ 0x10bc8, whole. */
void level2_scenery_effect(uint8_t *image);
void level2_scenery_effect_gate(uint8_t *image);

/* `debug_wait_for_keypad4` @ 0x11ba2, whole. */
void debug_wait_for_keypad4(uint8_t *image);

/* `hiscore_name_entry` @ 0x10916, SLICE [0x10916, 0x10720): every arm ends `bra.w $10720`, a branch
 * into `title_frame_step`, so the routine has no `rts` and the slice is diffed at that branch. */
void hiscore_name_entry(uint8_t *image);

#endif /* FS_FRONTEND_H */
