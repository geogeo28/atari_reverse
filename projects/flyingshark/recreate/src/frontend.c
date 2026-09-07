/* frontend.c — what runs between games, plus the two odd routines that belong to nothing else.
 *
 * Four of the six cores here are WHOLE routines; the other two are slices, and the reason is the
 * title flow's SHAPE rather than anything missing: it never returns. `hiscore_name_entry`'s every
 * arm ends in a `bra` back into the attract loop, and `title_attract_loop`'s stage start opens on a
 * `bsr set_palette_black` and runs into the attract poll. So a slice is diffed at a checkpoint PC
 * rather than at an `rts`, and STATUS.md files each under the address it starts at with its
 * `[start, end)` span. (The three routines these slices skip past — `set_palette_black` @ 0x111a6,
 * `set_palette_game` @ 0x111be and `load_file` @ 0x10bfa — were the `init` subsystem's and unported
 * when the spans were chosen; all three are verified now.)
 *
 * THE TITLE SCREEN'S STAGE START IS THE SCROLL SUBSYSTEM'S. `title_attract_loop` seeds the map
 * cursor and prescrolls exactly as `start_level` does — the original carries both blocks twice, one
 * copy per site — so `title_attract_prescroll` calls `seed_map_row_cursor` and `prescroll_stage`
 * (include/scroll.h) rather than restating them, and both are verified at both addresses.
 */
#include "machine.h"
#include "sched.h"

#include "common.h"   /* SCC_TRUE, and `const_word` — the table read this game spells 0..9 with */

#include "frontend.h"
#include "globals.h"
#include "hud.h"      /* the hiscore table, the glyph alphabet, `check_cheat_name` */
#include "irq.h"      /* `A_key_bits` and `A_joy1_state`, the ACIA handler's two input bytes */
#include "player.h"   /* `A_level_number`, which the scenery gate tests */
#include "scroll.h"   /* `A_level_distance`, `A_scroll_pos`, and the two stage-start cores */
#include "sound.h"    /* the two sfx wrappers the name entry arms */
#include "sprite.h"   /* the screen and tile geometry the scenery band is blitted with */

/* ================================================================================================
 * load_level_assets @ 0x10332, slice [0x10332, 0x10372) — the filename patch
 * ============================================================================================= */

/* Rewrite the digit inside each of the five asset filenames so that one record set serves every
 * stage: "A\HSC_0.DAT" .. "A\HSC_3.DAT" take byte 6 of their names from the level's row of
 * `level_bank_digits`, and "A\LEVEL1.MAP" takes byte 7 from the fifth entry of the same row.
 *
 * The four bank digits are read `(a0)+` and the map digit `(a0)` — the same cursor, the fifth byte
 * without a step — which is why a level's row is LEVEL_BANK_DIGITS long and not four.
 *
 * `muls.w #$5,d0` is a SIGNED multiply on the level number, so a negative level would index
 * backwards out of the table. Nothing writes `A_level_number` out of 0..4; the arm is reproduced
 * rather than guarded, as everywhere else in this reconstruction.
 */
void load_level_assets_patch_filenames(uint8_t *image, uint16_t level) {
    static const uint32_t bank_records[TILE_BANKS] = {A_file_rec_hsc_0, A_file_rec_hsc_1,
                                                      A_file_rec_hsc_2, A_file_rec_hsc_3};
    /* `muls.w` is a SIGNED 16x16 -> 32: both operands are widened to int32_t so that a negative
     * level really does index backwards, which an unsigned stride would quietly turn into a huge
     * forward offset that happens to wrap to the same address. */
    uint32_t digits = addr_add(A_level_bank_digits,
                               (uint32_t)((int32_t)(int16_t)level * (int32_t)LEVEL_BANK_DIGITS));
    unsigned bank;

    for (bank = 0; bank < TILE_BANKS; bank++)
        image[bank_records[bank] + FILE_REC_NAME + HSC_NAME_DIGIT] = image[digits + bank];
    image[A_file_rec_level_map + FILE_REC_NAME + MAP_NAME_DIGIT] = image[digits + TILE_BANKS];
}

/* ================================================================================================
 * title_attract_loop @ 0x104f2, slice [0x104f6, 0x1054a) — the attract screen's stage start
 * ============================================================================================= */

/* Rewind the scroll to the top of the map and scroll a whole screen of terrain in behind a black
 * palette, so that the attract text appears over a moving landscape rather than over the last
 * frame of whatever came before.
 *
 * The scroll position is read out of `A_const_words_0123` rather than written as an immediate,
 * which is this program's habit everywhere (`src/player.c`'s `const_word`); the scroll phase is a
 * real immediate, and is one step short of its own mask so the first frame wraps it to 0.
 */
void title_attract_prescroll(uint8_t *image) {
    wr16(image + A_scroll_pos, const_word(image, TITLE_SCROLL_POS_START));
    wr16(image + A_scroll_fine, SCROLL_FINE_SEED);
    seed_map_row_cursor(image);
    prescroll_stage(image);
}

/* ================================================================================================
 * level2_scenery_effect @ 0x1003c, and its gate @ 0x10bc8
 * ============================================================================================= */

/* The band's geometry. A column of the band is ONE TILE WIDE and a whole row of it ONE TILE HIGH,
 * so `include/sprite.h`'s tile figures are the geometry and nothing here restates them: the four
 * `move.l (a4)+,(a5)+` of a row are TILE_ROW_BYTES, and the `lea 144(a5),a5` that closes it is what
 * is left of a screen row after them. */
#define SCENERY_BAND_ROW_BYTES (TILE_PIXELS * SCREEN_ROW_BYTES)

/* One column of one tile row of the band: `rows` screen rows of TILE_ROW_BYTES, straight copies
 * with no mask — the band is opaque.
 *
 * Both loops in the routine are this, and they differ only in where the cursor is left: the
 * whole-row loop's last row has no `lea 144` after it and closes with `lea -4960(a5),a5` instead,
 * the partial-row loop's `lea` is inside the `dbf` and its caller reseats the cursor from a saved
 * copy. Both land on the same address — the column's top plus one tile width — so the difference is
 * in the original's instruction stream and not in its effect.
 */
static void blit_scenery_column(uint8_t *image, uint32_t tile, uint32_t dst, unsigned rows) {
    unsigned row;

    for (row = 0; row < rows; row++) {
        copy_longs(image, tile, dst, SCENERY_COLUMN_LONGS);
        tile = addr_add(tile, TILE_ROW_BYTES);
        /* the four `move.l (a4)+,(a5)+` and the `lea 144(a5),a5` after them: one screen row down */
        dst = addr_add(dst, SCREEN_ROW_BYTES);
    }
}

/* Where the tile a byte of `charset_order_table` names starts.
 *
 * `lsl.w #5 / lsl.w #4` is a WORD shift, so a tile id of 128 or more wraps its offset round zero
 * instead of reaching the second half of the bank — and the `adda.w` that adds it to the bank base
 * SIGN-EXTENDS, so an id of 64..127 subtracts. The shipped table holds ASCII punctuation and digits
 * (0x20..0x3f), all of which land inside the bank; the wrap is latent and is reproduced.
 */
static uint32_t scenery_tile_address(uint8_t tile_id) {
    uint32_t bank = A_tile_banks + SCENERY_TILE_BANK * TILE_BANK_BYTES;

    return addr_add(bank, sign_ext16((uint16_t)(tile_id * TILE_BYTES)));
}

/* Step the band's three counters for this frame, and answer whether the window is still open.
 *
 * The window has three parts. At its first position the counters are reset — `clr.l $1779e` clears
 * BOTH the whole-row count and the partial-row count, being one longword over two adjacent words.
 * Through the growing half the partial row gains a scanline a frame and carries into a whole row at
 * SCENERY_BAND_ROWS_MAX (via a deliberate 0xffff, so the `addq` that follows lands on 0), and the
 * band's top rises. Through the shrinking half it loses two scanlines a frame, borrows a whole row
 * back when it is empty, and the top falls twice as fast as it rose.
 */
static int scenery_step_counters(uint8_t *image) {
    int16_t distance = (int16_t)be16(image + A_level_distance);
    uint16_t partial;

    if (distance < (int16_t)SCENERY_WINDOW_START)
        return 0;
    if (distance == (int16_t)SCENERY_WINDOW_START) {
        wr32(image + A_scenery_band_rows, 0);   /* `clr.l $1779e` — rows AND partial rows */
        wr16(image + A_scenery_band_offset, SCENERY_BAND_OFFSET_SEED);
    }

    partial = be16(image + A_scenery_band_partial);
    if (distance <= (int16_t)SCENERY_WINDOW_GROW) {
        if (partial == SCENERY_BAND_ROWS_MAX) {
            partial = 0xffffu;   /* `move.w #$ffff,$177a0`, so the `addq #1` below reaches 0 */
            wr16(image + A_scenery_band_rows, (uint16_t)(be16(image + A_scenery_band_rows) + 1u));
        }
        wr16(image + A_scenery_band_partial, (uint16_t)(partial + 1u));
        wr16(image + A_scenery_band_offset,
             (uint16_t)(be16(image + A_scenery_band_offset) - SCENERY_GROW_OFFSET_STEP));
        return 1;
    }
    if (distance > (int16_t)SCENERY_WINDOW_END)
        return 0;

    if (partial == 0) {
        partial = SCENERY_BAND_ROWS_MAX;
        wr16(image + A_scenery_band_rows, (uint16_t)(be16(image + A_scenery_band_rows) - 1u));
    }
    partial = (uint16_t)(partial - SCENERY_SHRINK_ROW_STEP);
    /* `subq.w #2,$177a0 / bpl / clr.w $177a0`: the store happens either way, and a result that went
     * negative is replaced by zero rather than clamped before the store. */
    wr16(image + A_scenery_band_partial, (int16_t)partial < 0 ? 0 : partial);
    wr16(image + A_scenery_band_offset,
         (uint16_t)(be16(image + A_scenery_band_offset) + SCENERY_SHRINK_OFFSET_STEP));
    return 1;
}

/* Level 2's growing-then-shrinking band of scenery tiles, blitted straight onto the draw screen.
 *
 * Nothing else in the game draws this way: there is no display record, no map cell and no restore
 * list, so the band is simply overwritten by the scroll and repainted every frame while its window
 * is open. The destination is `screen_draw` plus a SIGNED word, which is why the band can sit above
 * the buffer's own base.
 */
void level2_scenery_effect(uint8_t *image) {
    uint32_t band, tile_ids = A_charset_order_table;
    uint16_t whole_rows, partial_rows;
    unsigned row, column;

    if (!scenery_step_counters(image))
        return;

    band = addr_add(be32(image + A_screen_draw),
                    sign_ext16(be16(image + A_scenery_band_offset)));
    whole_rows = be16(image + A_scenery_band_rows);
    partial_rows = be16(image + A_scenery_band_partial);

    /* Each loop is a `tst.w / beq` guard over a count-down loop — `subq.w #1,d6 / bne` for the
     * whole rows, `dbf d0` on `d5 - 1` for the partial one. A `<` bound is both at once: it runs
     * the count the register stands for, and none at all at zero, which is what the guards are
     * there to prevent the count-down forms from turning into 65,536 passes. */
    for (row = 0; row < whole_rows; row++) {
        for (column = 0; column < SCENERY_COLUMNS; column++) {
            blit_scenery_column(image, scenery_tile_address(image[tile_ids]),
                                addr_add(band, column * TILE_ROW_BYTES), TILE_PIXELS);
            tile_ids = addr_add(tile_ids, 1u);
        }
        band = addr_add(band, SCENERY_BAND_ROW_BYTES);
    }

    for (column = 0; column < SCENERY_COLUMNS; column++) {
        blit_scenery_column(image, scenery_tile_address(image[tile_ids]),
                            addr_add(band, column * TILE_ROW_BYTES), partial_rows);
        tile_ids = addr_add(tile_ids, 1u);
    }
}

/* The frame loop's 44th call of forty-five: the effect belongs to level 2 and to no other stage. */
void level2_scenery_effect_gate(uint8_t *image) {
    if (be16(image + A_level_number) == SCENERY_GATE_LEVEL)
        level2_scenery_effect(image);
}

/* ================================================================================================
 * debug_wait_for_keypad4 @ 0x11ba2
 * ============================================================================================= */

/* Spin until keypad '4' is held, and return. NO INSTRUCTION IN THE IMAGE CALLS IT — a leftover
 * single-step hook — and it has no bound of its own, unlike `check_cheat_name`'s 5001-pass arm spin
 * on the same bit.
 *
 * The byte is written by the ACIA interrupt and by nothing this routine does, so the read goes
 * through `sched_poll8`: off target a plain read could never change and the loop would never end,
 * and the number of iterations — the only thing this routine has to say — is invisible without the
 * kit comparing the candidate's polls against the oracle's arrivals at the same PC.
 */
void debug_wait_for_keypad4(uint8_t *image) {
    while (((sched_poll8(image, A_key_bits, DEBUG_WAIT_KEY_PC) >> CHEAT_ARM_KEY_BIT) & 1u) == 0)
        ;
}

/* ================================================================================================
 * hiscore_name_entry @ 0x10916, slice [0x10916, 0x10720)
 * ============================================================================================= */

/* Three initials into the hall of fame, one glyph at a time, and then a countdown.
 *
 * The stick picks a letter — right steps forward and wraps SPACE round to 'A', left steps back and
 * wraps 'A' round to SPACE — and fire confirms one glyph. The third fire runs `check_cheat_name`
 * over the three characters and sets `name_entry_done`; from then on the routine only counts
 * `name_entry_timeout` down, and at -1 resets every counter so the attract loop resumes.
 *
 * TWO THINGS ARE WORTH NAMING. Confirming a glyph COPIES IT FORWARD (`move.b (a0),1(a0)`), so the
 * next initial starts as the one just entered rather than as a space — the space fill happens once
 * per name, not once per glyph. And the countdown's reset writes `new_hiscore_pending` out of
 * `const_words_0123` while writing `name_entry_timeout` as a real immediate, two spellings of a
 * constant in four instructions.
 *
 * IT NEVER RETURNS: every arm ends `bra.w $10720`, a branch into `title_frame_step` @ 0x10594, so
 * the reconstruction returns where the original branches and the differential stops at that PC.
 */
void hiscore_name_entry(uint8_t *image) {
    uint32_t name, glyph;
    uint8_t stick;

    if (be16(image + A_name_entry_done) != 0) {
        uint16_t timeout = (uint16_t)(be16(image + A_name_entry_timeout) - 1u);

        wr16(image + A_name_entry_timeout, timeout);
        if ((int16_t)timeout >= 0)
            return;
        wr16(image + A_new_hiscore_pending, const_word(image, CONST_WORD_ZERO));
        wr16(image + A_name_entry_cursor, 0);
        wr16(image + A_name_entry_done, 0);
        wr16(image + A_name_entry_timeout, NAME_ENTRY_TIMEOUT_RELOAD);
        return;
    }

    name = addr_add(addr_add(A_hiscore_table,
                             (uint32_t)((int32_t)(int16_t)be16(image + A_hiscore_rank)
                                        * (int32_t)HISCORE_STRIDE)),
                    HISCORE_NAME);
    if (be16(image + A_name_entry_first_pass) == 0) {
        unsigned character;

        /* `st $176d6` is a BYTE store into a word `tst.w` reads, so it leaves 0xff00 rather
         * than 0xffff — the width fact `include/common.h`'s SCC_TRUE exists for. */
        image[A_name_entry_first_pass] = SCC_TRUE;
        for (character = 0; character < HISCORE_NAME_CHARS; character++)
            image[name + character] = GLYPH_SPACE;
    }
    glyph = addr_add(name, sign_ext16(be16(image + A_name_entry_cursor)));

    stick = image[A_joy1_state];
    if ((stick >> NAME_ENTRY_NEXT_GLYPH_BIT) & 1u) {
        sfx_play_5(image);
        image[glyph] = image[glyph] == GLYPH_SPACE ? GLYPH_A : (uint8_t)(image[glyph] + 1u);
        return;
    }
    if ((stick >> NAME_ENTRY_PREV_GLYPH_BIT) & 1u) {
        sfx_play_5(image);
        image[glyph] = image[glyph] == GLYPH_A ? GLYPH_SPACE : (uint8_t)(image[glyph] - 1u);
        return;
    }
    if (((stick >> JOY_FIRE_BIT) & 1u) == 0)
        return;

    sfx_play_2(image);
    if (be16(image + A_name_entry_cursor) == NAME_ENTRY_LAST_CURSOR) {
        check_cheat_name(image, glyph);
        image[A_name_entry_done] = SCC_TRUE;   /* `st $176dc`, a byte again */
        return;
    }
    image[glyph + 1] = image[glyph];
    wr16(image + A_name_entry_cursor, (uint16_t)(be16(image + A_name_entry_cursor) + 1u));
}

/* ================================================================================================
 * The register glue. Only the filename patch takes an argument; the rest read their inputs out of
 * the globals, so each glue is the core under its own name.
 * ============================================================================================= */

/* D0.w = the level number, 0..4. */
void g_load_level_assets_patch_filenames(uint8_t *image, uint32_t level) {
    load_level_assets_patch_filenames(image, (uint16_t)level);
}

void g_title_attract_prescroll(uint8_t *image)     { title_attract_prescroll(image); }
void g_level2_scenery_effect(uint8_t *image)       { level2_scenery_effect(image); }
void g_level2_scenery_effect_gate(uint8_t *image)  { level2_scenery_effect_gate(image); }
void g_debug_wait_for_keypad4(uint8_t *image)      { debug_wait_for_keypad4(image); }
void g_hiscore_name_entry(uint8_t *image)          { hiscore_name_entry(image); }
