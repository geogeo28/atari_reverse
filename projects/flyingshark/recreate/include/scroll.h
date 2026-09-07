/* scroll.h — THE SCROLLER BLOCK, and the two routines that establish and step it.
 *
 * Flying Shark scrolls by moving a video base through the circular framebuffer `include/globals.h`
 * describes, and by walking a cursor BACKWARDS through the level map as it goes. The state that
 * says how far the stage has scrolled, which map row is being read and how far into a tile the
 * screen is lives in one run of words at 0x163da..0x16436 — the SCROLLER BLOCK — plus the two
 * counters in bss the level-flow code compares against (`A_scroll_pos`, `A_level_distance`).
 *
 * THIS HEADER IS THAT BLOCK'S HOME, and it was not always: while this subsystem was unported the
 * block was held on loan in `include/sprite.h` (which READS all of it, in `render_frame`) and
 * `include/hud.h` (the debug overlay). Those loans are closed — the defines and their STATUS.md
 * "Borrowed globals" rows were deleted in the same change that filed this file's first row — and
 * both headers now include this one to read what they do not own. `A_level_number` @ 0x1642a sits
 * inside the same address run and is NOT here: it is the level-flow state `include/player.h` owns,
 * and one address has one home whatever its neighbours are.
 *
 * PROVENANCE. Every `A_*` is a `var` line in ../names.txt at load base 0x10000 and every routine
 * address an `fn` line; the instruction that establishes each figure is named beside it, read off
 * ../out/prg_dis.txt. ../notes/gameplay.md has the prose.
 */
#ifndef FS_SCROLL_H
#define FS_SCROLL_H

#include <stdint.h>

#include "globals.h"

/* ---- how far the stage has scrolled -----------------------------------------------------------
 *
 * `scroll_advance` @ 0x111ee is the frame loop's 43rd call and the only writer of both: two pixels
 * of scroll a frame, and a second counter derived from the first that the level-2 scenery effect
 * and the spawn scripts compare against.
 */
#define A_scroll_pos      0x17758u /* `addi.w #$2,$17758` @ 0x111ee — "MASTY" in the debug overlay */
#define A_level_distance  0x1779au /* `move.w d0,$1779a` @ 0x11202 */
#define SCROLL_POS_STEP     2u     /* `addi.w #$2,$17758` — two pixels a frame */
#define SCROLL_POS_BIAS  0x30u     /* `subi.w #$30,d0` @ 0x111fc, before the halving */

/* ---- the map cursor ---------------------------------------------------------------------------
 *
 * The map is read from its END backwards, because the game scrolls upward: the cursor starts one
 * past the last cell and steps back one 20-byte row every 32 pixels of scroll (`render_frame`'s
 * `advance_scroll`, src/sprite.c). `A_map_row_ptr_reset` keeps the seed the cursor started from —
 * `restart_level_at_checkpoint` @ 0x14b9a re-derives the cursor from it, and `render_frame` @
 * 0x147dc stores it back over the cursor on an arm the program itself disabled.
 */
#define A_map_row_ptr_reset 0x163feu /* `move.l d1,$163fe` @ 0x10524 and @ 0x1153a */
#define A_map_row_ptr       0x16402u /* `move.l d1,$16402` @ 0x1051e and @ 0x11534 */

/* ...and the LEVELn.MAP header the seed is computed from. `include/globals.h` owns the first word,
 * because it is also the address the file's record loads to; the rest of the header is this
 * subsystem's, which is what that header's comment says. */
#define A_level_map_rows  0x16434u /* `move.w $16434,d1` @ 0x10508 — header word 1: tile rows */
#define A_level_map_data  0x16436u /* `addi.l #$16436,d1` @ 0x10518 — the cells start here */

/* ---- the sub-tile phase, and the four screens it rotates ---------------------------------------
 *
 * `scroll_fine` runs 0,2,...,30 over sixteen frames and its wrap to 0 is what steps the map cursor.
 * The title screen and `start_level` seed it to 0x1e so that the FIRST frame wraps it.
 */
#define A_prescroll_flag    0x1642cu /* `move.b #$1,$1642c` @ 0x1052a and @ 0x11544 — set while a
                                      * stage prescrolls with the palette black, and read by
                                      * `render_frame` @ 0x14474 to skip everything that draws a
                                      * sprite or publishes a frame */
#define A_screen_ring_index 0x1642eu /* `move.w $1642e,d0` @ 0x1448a — which of the four screens is
                                      * being drawn, 0..3 */
#define A_scroll_fine       0x16430u /* `move.w #$1e,$16430` @ 0x10500 — "TCOUNT" in the overlay */
#define SCROLL_FINE_SEED  0x1eu      /* ...and the value both seeders write: one step short of the
                                      * mask, so the first frame's `addq #2` wraps it to 0 */

#define A_tile_split_row_table 0x163dau /* `lea $163da,a0` @ 0x1484a — 16 byte PAIRS indexed by
                                         * `A_scroll_fine`: (rows taken from the LOWER map cell's
                                         * tile, rows taken from the upper one) */

/* ---- how many frames a stage is scrolled before the player sees it ----------------------------- */
#define A_prescroll_frames 0x17752u /* `move.w $17752,d0` @ 0x10532 and @ 0x1154c, then a `dbf` —
                                     * so the loop runs this many PLUS ONE times */

/* ---- the five per-level records `start_level` installs -----------------------------------------
 *
 * `../names.txt`'s `level_table`. Twenty bytes each, indexed by `A_level_number` with `muls.w #$14`
 * @ 0x1146a; the last ten bytes of every record are zero padding no instruction reads.
 */
#define A_level_table       0x15a4cu /* `lea $15a4c,a0` @ 0x1146e */
#define LEVEL_REC_BYTES       20u    /* `muls.w #$14,d0` @ 0x1146a */
#define LEVEL_REC_END_SCROLL   0u    /* WORD -> `A_level_end_scroll_pos` (include/player.h) */
#define LEVEL_REC_BOSS_SCROLL  2u    /* WORD -> `A_boss_scroll_pos` */
#define LEVEL_REC_TUNE         4u    /* WORD -> `A_level_tune_id` below */
#define LEVEL_REC_SCRIPT       6u    /* LONG, relocated -> `A_spawn_script_ptr` (include/weapons.h) */

/* The tune the stage plays, copied out of that record's LEVEL_REC_TUNE by `start_level` @ 0x11484 —
 * which is this subsystem's core and the only instruction in the program that writes it. The sound
 * driver READS it (`music_stop` @ 0x121a2, where the module ignores it, and
 * `music_restart_if_stopped` @ 0x125b0) and `src/sound.c` includes this header to do so; it was on
 * loan to `include/sound.h` while the writer was unported. */
#define A_level_tune_id     0x1776eu /* `move.w 4(a0),$1776e` @ 0x11484 */

#define BOMBS_AT_LEVEL_START   3u    /* `move.w $176b2,$17710` @ 0x11440 — `A_const_words_0123`
                                      * (include/hud.h) index 3, this program's way of spelling an
                                      * immediate. Same store, same index, in
                                      * `restart_level_at_checkpoint` @ 0x14b6e */

/* ================================================================================================
 * The cores. Every one takes the flat image and reads its inputs out of the globals above, because
 * this program is hand-written assembly with a register ABI and no pointer arguments.
 * ============================================================================================= */

/* `scroll_advance` @ 0x111ee — the whole routine: two pixels of scroll, and `level_distance`
 * re-derived from the new position. */
void scroll_advance(uint8_t *image);

/* THE TWO BLOCKS THE ORIGINAL REPEATS AT ITS THREE STAGE-START SITES, as one core each.
 *
 * `title_attract_loop` @ 0x10508 and `start_level` @ 0x1151e are the same eight instructions, and
 * @ 0x1052a and @ 0x11544 the same prescroll loop. They are not a shared subroutine in the original
 * — each site is its own copy of the code — but they are one BEHAVIOUR, and a reconstruction that
 * copied them too would be two places to fix a fault in. Each is verified as a SLICE at BOTH sites
 * (STATUS.md's rows name the addresses), so the sharing is a claim the differential tests rather
 * than an assumption: a difference between the two copies would fail at whichever site it is in.
 */
void seed_map_row_cursor(uint8_t *image);
void prescroll_stage(uint8_t *image);

/* `start_level` @ 0x11440's other two slices. It ends `bra.w music_play` rather than returning, so
 * there is no `rts` a whole-routine differential could stop at; STATUS.md files each slice's span,
 * and folding them into one case diffed at that branch is a follow-up there. */
void start_level_reset_actors(uint8_t *image);      /* [0x11440, 0x1145a) */
void start_level_install_record(uint8_t *image);    /* [0x1145e, 0x11494) */

#endif /* FS_SCROLL_H */
