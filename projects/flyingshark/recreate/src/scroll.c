/* scroll.c — how far the stage has scrolled, where the map is read from, and what a stage start
 * does to both.
 *
 * Two routines, and only one of them is whole:
 *
 *   * `scroll_advance` @ 0x111ee — the frame loop's scroll step. Self-contained, so it is ported
 *     whole;
 *   * `start_level` @ 0x11440 — the stage start, ported as SLICES: four `[start, end)` spans with
 *     a STATUS.md row each. TWO REASONS, and only one of them still bites. It ends
 *     `bra.w music_play` rather than returning, so there is no `rts` a whole-routine case could
 *     stop at — that is structural. The other was that the three routines it calls in between
 *     (`clear_actor_arrays` @ 0x115e2, `set_palette_black` @ 0x111a6 and `set_palette_game`
 *     @ 0x111be) were unported when these slices were written; all three are the `init`
 *     subsystem's and all three are verified now, so folding the four spans into one case diffed
 *     at that `bra` is a FOLLOW-UP rather than a blocker (STATUS.md carries the row).
 *
 * TWO OF THOSE SLICES ARE ALSO THE TITLE SCREEN'S. `title_attract_loop` @ 0x104f2 opens a stage the
 * same way `start_level` does — seed the map cursor from the map header, then scroll the whole
 * screen in with the palette black — and the original carries both blocks TWICE, once per site.
 * `seed_map_row_cursor` and `prescroll_stage` are those blocks as one core each, verified as a
 * slice at BOTH addresses (`test_scroll.py`), so the claim that the two copies are the same code is
 * something the differential settles rather than something this file assumes.
 */
#include "machine.h"

#include "common.h"    /* `const_word`, the read this program spells its small immediates as */
#include "globals.h"
#include "player.h"    /* the three per-stage resets and the level parameters */
#include "scroll.h"
#include "sprite.h"    /* `render_frame`, which the prescroll calls once per frame */
#include "weapons.h"   /* `clear_object_list` and `A_spawn_script_ptr` */

/* ================================================================================================
 * scroll_advance @ 0x111ee — the frame loop's 43rd call of forty-five
 * ============================================================================================= */

/* Two pixels of scroll, and `level_distance` re-derived from the new position.
 *
 * The derivation is `(scroll_pos - 0x30) >> 1` plus one, all in 16 bits — a LOGICAL shift, so a
 * scroll position below the bias does not come back negative but as a number just under 0x8000.
 * That is reachable: the title screen seeds `scroll_pos` to 0 and steps it two at a time, so the
 * first 24 attract frames run with `level_distance` up near 0xffe9. Nothing reads it there (the
 * scenery effect's window opens at 0x8a2 and the spawn scripts compare `scroll_pos` itself), which
 * is why the original never needed the shift to be arithmetic.
 */
void scroll_advance(uint8_t *image) {
    uint16_t scroll_pos = (uint16_t)(be16(image + A_scroll_pos) + SCROLL_POS_STEP);
    uint16_t distance;

    wr16(image + A_scroll_pos, scroll_pos);
    distance = (uint16_t)((uint16_t)(scroll_pos - SCROLL_POS_BIAS) >> 1);
    /* `move.w d0,$1779a` and then `addi.w #$1,$1779a`: two stores, one value. Spelt as one store of
     * the sum, because nothing can read the intermediate — the two instructions are adjacent. */
    wr16(image + A_level_distance, (uint16_t)(distance + 1u));
}

/* ================================================================================================
 * The two blocks a stage start repeats — `title_attract_loop` @ 0x10508 / 0x1052a and
 * `start_level` @ 0x1151e / 0x11544
 * ============================================================================================= */

/* Point the map cursor one past the END of the level map, and remember where that was.
 *
 * `rows * (columns * 2)` with the doubling done as a WORD (`asl.w #1,d0`) and the multiply as an
 * unsigned 16x16 -> 32 (`mulu.w d0,d1`), so a map wider than 0x8000 columns would wrap the stride
 * before the product is widened. The five shipped maps are all 10 columns; the widths are read out
 * of the map's own header rather than compiled in, which is what makes that reachable at all.
 */
void seed_map_row_cursor(uint8_t *image) {
    uint16_t rows = be16(image + A_level_map_rows);
    uint16_t row_bytes = (uint16_t)(be16(image + A_level_map_cols) << 1);
    uint32_t end_of_map = A_level_map_data + (uint32_t)rows * row_bytes;

    wr32(image + A_map_row_ptr, end_of_map);
    wr32(image + A_map_row_ptr_reset, end_of_map);
}

/* Scroll a whole screen of tiles in with `prescroll_flag` set, which is what makes it invisible:
 * `render_frame` reads that flag and skips both draw passes, the overlay repaint, the Setscreen
 * and the VBL wait, leaving only the seam, the scroll step and the newly exposed tile band. The
 * caller has already blacked the palette.
 *
 * `move.w $17752,d0` then `dbf d0`, so the loop runs `prescroll_frames + 1` times and a stored 0
 * still draws one frame. The original pushes and pops D0 around each call because `render_frame`
 * clobbers it; nothing observable turns on that, and a C loop counter is the same fact.
 */
void prescroll_stage(uint8_t *image) {
    unsigned frames = loop_passes(be16(image + A_prescroll_frames) + 1u, COUNT_MASK_WORD);

    image[A_prescroll_flag] = 1;   /* `move.b #$1,$1642c` — a 1, not an `st`'s 0xff */
    while (frames--)
        render_frame(image);
    image[A_prescroll_flag] = 0;   /* `clr.b $1642c` */
}

/* ================================================================================================
 * start_level @ 0x11440 — the rest of its slices
 * ============================================================================================= */

/* [0x11440, 0x1145a): the bomb count and the three per-stage resets, up to the `bsr` into
 * `clear_actor_arrays` @ 0x115e2 that the `init` subsystem owns.
 *
 * The bomb count is `const_words_0123[3]` and not an immediate — this program reads its small
 * constants out of that table (see `src/player.c`'s `const_word`), and reproducing the READ is what
 * makes a case that poisons the table visible.
 */
void start_level_reset_actors(uint8_t *image) {
    wr16(image + A_bombs, const_word(image, BOMBS_AT_LEVEL_START));
    player_reset_to_start(image);
    takeoff_script_reset(image);
    landing_script_reset(image);
    clear_display_list(image);
}

/* [0x1145e, 0x11494): the object list cleared, and the level's own record copied into the four live
 * parameters the rest of the game reads.
 *
 * The index is `muls.w` — a SIGNED multiply — on a level number the game keeps in 0..4. A negative
 * one would index backwards out of the table, which is a floor the routine does not have; nothing
 * writes `level_number` out of range, so the arm is latent and is reproduced rather than guarded.
 */
void start_level_install_record(uint8_t *image) {
    uint32_t record;

    clear_object_list(image);
    record = addr_add(A_level_table,
                      (uint32_t)((int32_t)(int16_t)be16(image + A_level_number)
                                 * (int32_t)LEVEL_REC_BYTES));
    wr16(image + A_level_end_scroll_pos, be16(image + record + LEVEL_REC_END_SCROLL));
    wr16(image + A_boss_scroll_pos,      be16(image + record + LEVEL_REC_BOSS_SCROLL));
    wr16(image + A_level_tune_id,        be16(image + record + LEVEL_REC_TUNE));
    wr32(image + A_spawn_script_ptr,     be32(image + record + LEVEL_REC_SCRIPT));
}

/* ================================================================================================
 * The register glue. Every core here reads its inputs out of the globals, so none of these routines
 * takes an argument in a register and each glue is the core under its own name.
 * ============================================================================================= */

void g_scroll_advance(uint8_t *image)             { scroll_advance(image); }
void g_seed_map_row_cursor(uint8_t *image)        { seed_map_row_cursor(image); }
void g_prescroll_stage(uint8_t *image)            { prescroll_stage(image); }
void g_start_level_reset_actors(uint8_t *image)   { start_level_reset_actors(image); }
void g_start_level_install_record(uint8_t *image) { start_level_install_record(image); }
