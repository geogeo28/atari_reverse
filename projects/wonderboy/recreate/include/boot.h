/* boot.h — the boot chain's reconstructed routines (src/boot.c).
 *
 * The addresses, geometry and dispatch table are in wonderboy.h, which is the header test/layout.py
 * scrapes; only the signatures are here. src/boot.c's banner says which part of the boot chain this
 * is and ../STATUS.md's batch 44 phase A carries the inventory of the rest.
 */
#ifndef WONDERBOY_BOOT_H
#define WONDERBOY_BOOT_H

#include <stdint.h>

/* $f93c: `count_minus_1 + 1` longwords from `src` to `dst`, ascending. */
void copy_longs(uint8_t *image, uint32_t src, uint32_t dst, uint16_t count_minus_1);

/* $f938: one 32000-byte screen, `copy_longs` with the count preset. */
void copy_screen(uint8_t *image, uint32_t src, uint32_t dst);

/* $f926: WB_SCREEN_CLEAR_LONGS longwords of zero from WB_SCREEN_LOW — both screen buffers and the
 * gap between them. */
void clear_both_screens(uint8_t *image);

/* $e67e: copy every tile WB_TILE_INDEX_TABLE names out of the depacked WB_TILE_BANK into
 * WB_TILE_BITMAPS in table order, rewriting each entry with its own position as it goes.
 * NO `rts` in the original — it falls through into the boot's continuation at $e6c6. */
void bg_tile_install(uint8_t *image);

/* $e92c / $e938 / $e948 / $e95e: `count_minus_1 + 1` cells of 5, 10, 15 or 20 words from `src` to
 * `dst`. Each returns the advanced destination, which is what the caller keeps. */
uint32_t sprite_cru_copy_5w(uint8_t *image, uint32_t src, uint32_t dst, uint16_t count_minus_1);
uint32_t sprite_cru_copy_10w(uint8_t *image, uint32_t src, uint32_t dst, uint16_t count_minus_1);
uint32_t sprite_cru_copy_15w(uint8_t *image, uint32_t src, uint32_t dst, uint16_t count_minus_1);
uint32_t sprite_cru_copy_20w(uint8_t *image, uint32_t src, uint32_t dst, uint16_t count_minus_1);

/* $e87c: turn the raw SPRITES.CRU at WB_SPRITE_CRU_LOAD into the cells at WB_SPRITE_CRU_CELLS,
 * marked by WB_STAGE_NUMBER's row of WB_SPRITE_CRU_MASK_TABLE. Returns WB_SPRITE_CRU_INSTALLED, or
 * WB_SPRITE_CRU_UNKNOWN_COPIER if the dispatch table held a longword that is none of the four
 * copiers — which the original would have `jsr`ed through and no shipped input produces. Its
 * caller's `bsr.w` at $e6e8 spends no register, so both codes are out of band. */
uint32_t sprites_cru_install(uint8_t *image);

/* $e782: the single entry point for all disk loading. Turn `index` into its row of
 * WB_RESOURCE_FILE_TABLE, hand that name and `dest` ACROSS THE DISK SEAM (see wonderboy.h), and on
 * the first load of the boot run the Copylock. Returns WB_LOAD_OK, WB_LOAD_COPYLOCK_RAN or
 * WB_LOAD_DISK_ERROR — all three out of band, because the original leaves d0 holding the seam's own
 * return and no caller reads it. */
uint32_t load_resource_by_index(uint8_t *image, uint32_t index, uint32_t dest);

/* $e768: raise or clear WB_ACTOR_FLAG_SIDE_BIT on one record, from WB_STAGE_SIDE_FLAG. */
void actor_apply_stage_side(uint8_t *image, uint32_t record);

/* $e710: empty all three actor tables and give the two followed records the stage's entry shape. */
void stage_actors_init(uint8_t *image);

/* THE PER-STAGE DISPATCHER AT $e5ba, IN THE THREE PIECES ITS OWN `bsr` CUTS IT INTO. The original is
 * one straight-line block with `bsr load_resource_by_index` in the middle of it, and what survives
 * that call is the ROW POINTER in a0 — which is the whole reason load_resource_by_index opens with
 * `move.l a0,-(a7)`. Each piece is entered and diffed on its own; src/boot.c says where the cuts
 * fall and what the caller owes. */

/* $e5ba..$e5f2: clear WB_ACTOR_PLATFORM_RIDDEN, take WB_LEVEL_SEQ_INDEX's row and step the index
 * past it, and publish WB_STAGE_SECOND_LOAD_FLAG. Returns the row's address. */
uint32_t stage_sequence_advance(uint8_t *image);

/* $e5d8..$e5dc: `moveq #0,d0 / move.b (a0),d0 / addq.b #2,d0` — the row's overlay ordinal turned
 * into a WB_RESOURCE_FILE_TABLE index. A BYTE add, so an ordinal of $fe wraps to 0 (TITLESCR) rather
 * than naming a row past the table's end. */
uint32_t stage_sequence_resource(uint8_t *image, uint32_t row);

/* $e5fe..$e622: the two stores that follow the load — WB_STAGE_SIDE_FLAG from the row's side byte,
 * and WB_STAGE_NUMBER from its stage byte. */
void stage_sequence_apply_row(uint8_t *image, uint32_t row);


/* THE FOUR COMPOSED SLICES ($e494 / $e512 / $e562 / $e5ba), batch 44 phases C and E. Each is a run
 * of the calls
 * above and of src/stage.c's, cut where the boot's own FIRE WAITS cut it: `clr.b WB_JOY1_STATE`
 * and two `tst.b` spins on a byte only the IKBD interrupt writes. The waits are hardware and stay
 * the shim's; everything between them is here. src/boot.c says what each one deviates from, and
 * the cut addresses are WB_BOOT_* in wonderboy.h, so the reconstruction's own header and its
 * differential cannot disagree about where a slice begins or ends.
 *
 * THREE OF THEM ARE THE BOOT AND THE FOURTH IS AN ENDING'S — THREE ENDINGS', in fact.
 * `boot_prompt_screen` is never reached from the other three: what reaches it is a `jmp $e494.l`,
 * and the image holds three of those (ESC's `game_key_actions` arm at $598, the player gate's
 * game-over expiry at $bdc, and slot 61's terminator at $700e — src/boot.c has the census). The
 * prompt's own fire wait then falls through into the boot continuation, so the chain a player walks
 * is prompt, then title, then credits, then stage, and only the last three are what the machine
 * does on its way in. ../atari/'s own-entry build calls all four and wires all three endings.
 *
 * ALL FOUR RETURN ONE OF THE WB_LOAD_* CODES, which is `load_resource_by_index`'s own report
 * raised to the strongest thing any of the slice's loads said. Out of band for the same reason its
 * are: the original leaves d0 holding whatever its last call left and nothing reads it. */

/* $e494..$e4d4 — clear the palette, point the shifter at WB_SCREEN_HIGH, load DATADISK.RAD, inflate
 * it into that buffer and put its palette up. It arms nothing, so it reports WB_LOAD_OK or
 * WB_LOAD_DISK_ERROR and never WB_LOAD_COPYLOCK_RAN. */
uint32_t boot_prompt_screen(uint8_t *image);

/* $e512..$e550 — arm the protection, load TITLESCR.RAD, inflate it into WB_SCREEN_LOW, put its
 * palette on the shifter, start WB_TITLE_SONG. The video/vector prologue at $e4e6 is NOT here. */
uint32_t boot_title_screen(uint8_t *image);

/* $e562..$e5a2 — load CREDITS.RAD, inflate it onto WB_SCREEN_HIGH, copy that down onto the buffer
 * the shifter is showing, run the new-game reset and raise WB_CREDITS_PROMPT_PEN. */
uint32_t boot_credits_screen(uint8_t *image);

/* $e5ba..$f8b4 — the per-stage load: the sequence row, its overlay, TILEDATA.RAD and the two
 * installers, and then the hinge that draws the stage and jumps into game_main_loop. It ends in a
 * TRANSFER, so the last thing it does is call `stage_load_window` and return. */
uint32_t boot_load_stage(uint8_t *image);

#endif /* WONDERBOY_BOOT_H */
