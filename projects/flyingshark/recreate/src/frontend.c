/* frontend.c — what runs between games, plus the two odd routines that belong to nothing else.
 *
 * MOST OF WHAT IS HERE IS A SLICE, and the reason is the title flow's SHAPE rather than anything
 * missing: it never returns. `hiscore_name_entry`'s every arm ends in a `bra` back into the attract
 * loop, and the loop itself is a spin whose four exits are four branches. So a slice is diffed at a
 * checkpoint PC rather than at an `rts`, and STATUS.md files each under the address it starts at
 * with its `[start, end)` span — which, as in `hiscore_name_entry`'s case, may run backwards.
 *
 * THE TITLE FLOW IS FOUR CORES AND THE LOOP THAT READS THEM. `enter_title` @ 0x1030e,
 * `title_attract_prescroll` @ 0x104f2, `title_attract_start_tune` @ 0x1054a, `title_attract_poll`
 * @ 0x10562 and `title_frame_step` @ 0x10594 each answer with the branch they took
 * (`include/frontend.h` names every exit), and `title_attract_loop` composes them. Only the fire
 * button leaves: the tune ending goes back to 0x1054a, the scroll running out to 0x104f2, and the
 * high-score branch to `hiscore_show_entry_screen`, which falls through `hiscore_name_entry` into
 * the frame step the loop was about to run anyway — so that one is a CALL here and not an exit.
 *
 * THE SPIN IS A WAIT ON THE STICK. `A_joy1_state` is written by the ACIA interrupt and by nothing
 * in this program, so the poll's `btst #7` goes through `sched_poll8` at TITLE_FIRE_WAIT_PC and the
 * harness compares the candidate's polls against the oracle's arrivals. Without it the loop could
 * never end off target. The mode toggle's two reads of the SAME byte are ordinary reads and not
 * polls: they are not what the loop is waiting on (tools/recreate_kit/include/sched.h).
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
#include "init.h"     /* the two palette wrappers, and `clear_actor_arrays` */
#include "sound.h"    /* the sfx wrappers the name entry and the mode toggle arm, and `music_play` */
#include "sprite.h"   /* the screen and tile geometry the scenery band is blitted with, and
                       * `render_frame`, which is the whole of one attract frame */
#include "weapons.h"  /* `clear_object_list`, the third of the three lists the attract start wipes */

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

/* The one surviving disc prompt @ 0x103cc, and it prompts for nothing.
 *
 * `a6 = A_disc_prompt_message` is the middle of a word table rather than a string, so
 * `console_show_message` points the logical screen at the previous frame, addresses the cursor to
 * row 24 and stops on the first byte. What is left is TWO WAITS — fire RELEASED, inside that
 * routine, then fire PRESSED here — and a `probe_disc` whose answer the patched `bra.w` @ 0x103ea
 * throws away, so the `tst.l A_disc_probe_result` between them steers nothing and the reconstruction
 * does not spell it.
 *
 * The press spin goes through `sched_poll8` for `debug_wait_for_keypad4`'s reason: the byte is the
 * ACIA interrupt's and nothing here writes it, so off target a plain read could never end the loop.
 */
static void wait_for_disc_swap(uint8_t *image) {
    unsigned polls;

    console_show_message(image, A_disc_prompt_message);   /* `lea` + `bsr.w $14996` @ 0x103cc */
    /* `btst #7,$1777f / beq.s $103d6` — unbounded in the original and unbounded on target;
     * `wait_may_go_round_again` is the harness-only give-up (include/common.h). */
    for (polls = 0; wait_may_go_round_again(polls); polls++)
        if ((sched_poll8(image, A_joy1_state, DISC_PROMPT_WAIT_PC) >> JOY_FIRE_BIT) & 1u) {
            probe_disc(image);                            /* `bsr.w $10c4c` @ 0x103e0 */
            return;
        }
    /* The cap, and the give-up has already tallied the refusal: the case is void, so the probe is
     * NOT made — carrying on past a refused wait would compare a call the original never reached
     * (`tools/recreate_kit/include/sched.h`, "A CALLER MUST HONOUR THE 0"). Unreachable on target,
     * where the helper is a constant 1. */
}

/* load_level_assets @ 0x10332 — the digit patch, and then the level's five files.
 *
 * D0 is the level number and the routine has neither floor nor ceiling: `muls.w #$5` is signed and
 * the dispatch below is three exact tests, so a level outside 0..4 reads a digit row past the table
 * and then takes the ordinary arm.
 *
 * THE TWO LETTERED ARMS ARE THE SAME FIVE LOADS IN THE SAME ORDER, one copy each at 0x10404 and
 * 0x1047a — the original carries the block twice, as it does the title screen's stage start — and
 * BOTH RE-LOAD A\HSC_0.DAT, which the head above has already read. That second read is the
 * original's and is reproduced; the differential drives both levels, so a difference between the
 * two copies would fail at whichever site it is in.
 */
void load_level_assets(uint8_t *image, uint16_t level) {
    load_level_assets_patch_filenames(image, level);      /* 0x10332 */
    load_file(image, A_file_rec_hsc_0);                   /* `lea $16346,a0 / bsr` @ 0x10372 */

    if (level == LEVEL_ASSETS_ORDER_LEVEL_2 || level == LEVEL_ASSETS_ORDER_LEVEL_3) {
        load_file(image, A_file_rec_hsc_0);               /* again — 0x10404 and 0x1047a */
        load_file(image, A_file_rec_hsc_1);
        load_file(image, A_file_rec_hsc_2);
        load_file(image, A_file_rec_hsc_3);
        load_file(image, A_file_rec_level_map);
        return;
    }

    load_file(image, A_file_rec_level_map);               /* 0x103b0 */
    load_file(image, A_file_rec_hsc_1);                   /* 0x103ba */
    if ((int16_t)level >= (int16_t)DISC_SWAP_ABOVE_LEVEL)       /* `blt.w $103f0` @ 0x103c8 */
        wait_for_disc_swap(image);
    load_file(image, A_file_rec_hsc_2);                   /* 0x103f0 */
    load_file(image, A_file_rec_hsc_3);                   /* `bra.w $10bfa` @ 0x10400, a tail call */
}

/* ================================================================================================
 * title_attract_loop @ 0x104f2, slice [0x104f2, 0x1054a) — the attract screen's stage start
 * ============================================================================================= */

/* Rewind the scroll to the top of the map and scroll a whole screen of terrain in behind a black
 * palette, so that the attract text appears over a moving landscape rather than over the last
 * frame of whatever came before.
 *
 * IT OPENS ON THE PALETTE DOOR: `bsr.w set_palette_black` @ 0x104f2 writes no image byte at all, so
 * the ordered OS EVENT is the only thing that separates a prescroll the player cannot see from one
 * drawn in full view. `title_frame_step`'s restart branch re-enters here, which is why the black is
 * laid down once per attract cycle rather than once per game.
 *
 * The scroll position is read out of `A_const_words_0123` rather than written as an immediate,
 * which is this program's habit everywhere (`src/player.c`'s `const_word`); the scroll phase is a
 * real immediate, and is one step short of its own mask so the first frame wraps it to 0.
 */
void title_attract_prescroll(uint8_t *image) {
    set_palette_black(image);                    /* `bsr.w $111a6` @ 0x104f2 */
    wr16(image + A_scroll_pos, const_word(image, TITLE_SCROLL_POS_START));
    wr16(image + A_scroll_fine, SCROLL_FINE_SEED);
    seed_map_row_cursor(image);
    prescroll_stage(image);
}

/* ================================================================================================
 * enter_title @ 0x1030e — the four instructions in front of the attract loop
 * ============================================================================================= */

/* Raise the "just entered" flag, black the palette, and say whether level 0's files still have to
 * be loaded. Both answers end in a branch rather than a return, so both are exits.
 *
 * `st $17698` and `st $176ea` are BYTE stores into words the `tst.w`s read, so each leaves 0xff00
 * and not 0xffff — the width fact `include/common.h`'s SCC_TRUE exists for.
 */
enter_title_exit enter_title(uint8_t *image) {
    image[A_title_just_entered] = SCC_TRUE;              /* `st $17698` @ 0x1030e */
    set_palette_black(image);                            /* `bsr.w $111a6` @ 0x10314 */
    if (be16(image + A_level0_assets_loaded) != 0)       /* `tst.w $176ea` @ 0x10318 */
        return ENTER_TITLE_ATTRACT;
    image[A_level0_assets_loaded] = SCC_TRUE;            /* `st $176ea` @ 0x10322 */
    return ENTER_TITLE_LOAD_LEVEL0;
}

/* ================================================================================================
 * title_attract_loop @ 0x1054a, slice [0x1054a, 0x10562) — the jingle and the three lists
 * ============================================================================================= */

/* Where the attract loop restarts every time the tune runs out: the jingle again, the display list,
 * the entity arena and the enemy-bullet array all cleared, and the game palette back up. All five
 * are other subsystems' verified cores; this slice is the ORDER they are called in.
 */
void title_attract_start_tune(uint8_t *image) {
    music_play(image, ATTRACT_TUNE);   /* `move.w #$4,d0 / bsr.w $12588` @ 0x1054a */
    clear_display_list(image);         /* `bsr.w $115a8` @ 0x10552 */
    clear_actor_arrays(image);         /* `bsr.w $115e2` @ 0x10556 */
    clear_object_list(image);          /* `bsr.w $115fc` @ 0x1055a */
    set_palette_game(image);           /* `bsr.w $111be` @ 0x1055e */
}

/* ================================================================================================
 * title_attract_loop @ 0x10562, slice [0x10562, 0x10594) — the poll and the attract pages
 * ============================================================================================= */

/* One of the three attract text scripts, compiled into the display list from its head.
 *
 * The original clears D0, D1 and D2 as LONGWORDS at 0x105a8 before every arm, because
 * `build_text_display_list` moves the script's start x and y in as BYTES and keeps the caller's
 * high halves (include/hud.h). Passing zeroes is that clear.
 */
static void title_publish_page(uint8_t *image, uint32_t script) {
    uint32_t dest = A_display_list;
    uint32_t text_x = 0;
    uint32_t text_y = 0;

    build_text_display_list(image, &script, &dest, &text_x, &text_y);
}

/* The four-character mode word inside the (undrawn) "MODE EASY" script, replaced from `word`. */
static void title_set_mode_word(uint8_t *image, uint32_t word) {
    unsigned character;

    for (character = 0; character < TITLE_MODE_WORD_BYTES; character++)
        image[A_text_title_mode + TITLE_MODE_WORD_OFFSET + character] = image[word + character];
}

/* The difficulty toggle @ 0x105ea — the only thing on the attract screen the player can change, and
 * the one block in this program that saves every register around code that calls nothing.
 *
 * THE "JUST ENTERED" FLAG TAKES THE EASY ARM WITHOUT THE STICK, and then suppresses that arm's
 * sound effect and clears itself: entering the title screen resets the mode silently, and pushing
 * the stick left afterwards does the same thing audibly. The flag is read twice (`tst.w $17698` @
 * 0x105ee and @ 0x10624) with nothing in between that writes it — and nothing OUTSIDE the routine
 * writes it either, so one read stands for both.
 *
 * THE STICK IS NOT THAT, and is read twice here because the original reads it twice: `btst #2` @
 * 0x105f8 and `btst #3` @ 0x1063a are two loads of `A_joy1_state`, which the ACIA interrupt writes
 * — so on the machine a stick flicked from left to right between them really is seen as neither.
 * Nothing off target can separate the two spellings (`STATUS.md`, "Unpinned on target"): the reads
 * are ordinary `bus_read_byte`s, not the wait the loop polls, so a single cached read would compare
 * identically. It is written as the original has it because the difference is the machine's.
 */
static void title_difficulty_toggle(uint8_t *image) {
    int just_entered = be16(image + A_title_just_entered) != 0;

    if (just_entered
        || ((image[A_joy1_state] >> TITLE_MODE_EASY_BIT) & 1u)) { /* `btst #2,$1777f` @ 0x105f8 */
        title_set_mode_word(image, A_title_word_easy);            /* 0x10612 */
        image[A_hard_mode] = image[A_const_words_0123];           /* `move.b $176ac,$177cc` */
        if (!just_entered)
            sfx_play_2(image);                                    /* `bsr.w $121e6` @ 0x1062e */
        wr16(image + A_title_just_entered, 0);                    /* `clr.w $17698` @ 0x10632 */
        return;
    }
    if (((image[A_joy1_state] >> TITLE_MODE_HARD_BIT) & 1u) == 0) /* `btst #3,$1777f` @ 0x1063a */
        return;
    title_set_mode_word(image, A_title_word_hard);                /* 0x10654 */
    image[A_hard_mode] = TITLE_HARD_MODE_ON;                      /* `move.b #$1,$177cc` @ 0x1065c */
    sfx_play_2(image);                                            /* `bsr.w $121e6` @ 0x10664 */
}

/* The attract page cycle @ 0x105a8: step the page timer and compile whichever script it now names.
 *
 * The timer counts DOWN once a frame and reloads from `A_attract_page_reload` when the subtraction
 * goes negative, so the three pages come round in a fixed order. Both thresholds are SIGNED tests
 * on what the subtraction left, which is what makes the reload's own value part of the choice.
 */
static void title_attract_page_step(uint8_t *image) {
    uint16_t timer = (uint16_t)(be16(image + A_attract_page_timer) - 1u); /* `subi.w #$1` @ 0x105ae */

    wr16(image + A_attract_page_timer, timer);
    if ((int16_t)timer < 0)                                               /* `bpl.s $105c2` */
        wr16(image + A_attract_page_timer, be16(image + A_attract_page_reload));

    timer = be16(image + A_attract_page_timer);
    if ((int16_t)timer < (int16_t)ATTRACT_PAGE_HALL_OF_FAME_BELOW) {
        title_publish_page(image, A_text_hall_of_fame);                   /* 0x10684 */
        return;
    }
    if ((int16_t)timer < (int16_t)ATTRACT_PAGE_CREDITS_BELOW) {
        title_publish_page(image, A_text_credits);                        /* 0x10670 */
        return;
    }
    title_publish_page(image, A_text_publisher);                          /* 0x105da */
    title_difficulty_toggle(image);                                       /* 0x105ea */
}

/* One pass of the attract poll: the two tests at 0x10562, a scroll step, and the page for the frame
 * `title_frame_step` is about to draw.
 *
 * THE ORDER OF THE TWO TESTS IS THE ORIGINAL'S AND IT MATTERS. The fire button starts a game only
 * while no high score is waiting to be entered, and the tune's "still playing" byte is read BEFORE
 * anything is drawn — so a tune that has just ended restarts without a frame going by.
 *
 * THE HIGH-SCORE ARM IS A CALL, NOT AN EXIT. `bra.w $106f2` @ 0x10590 goes to
 * `hiscore_show_entry_screen`, which falls into `hiscore_name_entry`, whose every arm branches to
 * 0x10594 — the frame step this pass was about to reach anyway. So it leaves and comes straight
 * back, once a frame, and the two are called here rather than answered for.
 */
title_poll_exit title_attract_poll(uint8_t *image) {
    if (be16(image + A_new_hiscore_pending) == 0                          /* `tst.w $176e8` @ 0x10562 */
        && ((sched_poll8(image, A_joy1_state, TITLE_FIRE_WAIT_PC) >> JOY_FIRE_BIT) & 1u))
        return TITLE_POLL_START_GAME;                                     /* `rts` @ 0x105a6 */
    if (image[A_sound_module + SND_MUSIC_ACTIVE] == 0)                    /* `tst.b 30(a0)` @ 0x1057a */
        return TITLE_POLL_TUNE_ENDED;                                     /* `beq.s $1054a` */

    scroll_advance(image);                                                /* `bsr.w $111ee` @ 0x10580 */
    clear_display_list(image);                                            /* `bsr.w $115a8` @ 0x10584 */
    if (be16(image + A_new_hiscore_pending) != 0) {                       /* `tst.w $176e8` @ 0x10588 */
        hiscore_show_entry_screen(image);                                 /* `bra.w $106f2` @ 0x10590 */
        hiscore_name_entry(image);                                        /* ...which falls into it */
        return TITLE_POLL_NEXT_FRAME;
    }
    title_attract_page_step(image);                                       /* `beq.s $105a8` @ 0x1058e */
    return TITLE_POLL_NEXT_FRAME;
}

/* ================================================================================================
 * title_frame_step @ 0x10594, slice [0x10594, 0x10562) — one attract frame
 * ============================================================================================= */

/* Draw the frame the poll has just built a display list for, and answer whether the scroll has run
 * out of map. It is two instructions and a branch, and it is a routine of its own only because
 * `hiscore_name_entry` re-enters the loop here rather than at the poll.
 */
title_frame_exit title_frame_step(uint8_t *image) {
    render_frame(image);                                          /* `bsr.w $14446` @ 0x10594 */
    if ((int16_t)be16(image + A_scroll_pos) < (int16_t)ATTRACT_END_SCROLL_POS)
        return TITLE_FRAME_POLL_AGAIN;                            /* `blt.s $10562` @ 0x105a0 */
    return TITLE_FRAME_ATTRACT_OVER;                              /* `bra.w $104f2` @ 0x105a2 */
}

/* ================================================================================================
 * title_attract_loop @ 0x104f2 — the loop the five cores above make
 * ============================================================================================= */

/* The whole attract screen, from its stage start to the `rts` that is its only way out. Every byte
 * of it is one of the slices above; this is the branch structure that joins them, and it is what a
 * whole-flow differential runs from 0x104f2 to that `rts`.
 */
void title_attract_loop(uint8_t *image) {
    title_attract_prescroll(image);                       /* 0x104f2 */
    for (;;) {
        title_attract_start_tune(image);                  /* 0x1054a */
        for (;;) {
            title_poll_exit poll = title_attract_poll(image);   /* 0x10562 */

            if (poll == TITLE_POLL_START_GAME)
                return;                                   /* `rts` @ 0x105a6 */
            if (poll == TITLE_POLL_TUNE_ENDED)
                break;                                    /* `beq.s $1054a` @ 0x1057e */
            if (title_frame_step(image) == TITLE_FRAME_ATTRACT_OVER) {
                title_attract_prescroll(image);           /* `bra.w $104f2` @ 0x105a2 */
                break;
            }
        }
    }
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
 *
 * WHICH IS ALSO WHY THE SPIN IS BEHIND `wait_may_go_round_again` rather than a bare `while`: a case
 * whose schedule never brings the key down would hang the suite for ever here, and a hung suite
 * decides nothing. On target the helper is a constant 1 and this is the original's unbounded loop.
 */
void debug_wait_for_keypad4(uint8_t *image) {
    unsigned polls;

    for (polls = 0; wait_may_go_round_again(polls); polls++)
        if ((sched_poll8(image, A_key_bits, DEBUG_WAIT_KEY_PC) >> CHEAT_ARM_KEY_BIT) & 1u)
            return;
    /* the cap; the refusal is tallied and the case is void (include/common.h) */
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

void g_load_level_assets(uint8_t *image, uint32_t level) {
    load_level_assets(image, (uint16_t)level);
}

uint32_t g_enter_title(uint8_t *image)             { return (uint32_t)enter_title(image); }
void g_title_attract_prescroll(uint8_t *image)     { title_attract_prescroll(image); }
void g_title_attract_start_tune(uint8_t *image)    { title_attract_start_tune(image); }
uint32_t g_title_attract_poll(uint8_t *image)      { return (uint32_t)title_attract_poll(image); }
uint32_t g_title_frame_step(uint8_t *image)        { return (uint32_t)title_frame_step(image); }
void g_title_attract_loop(uint8_t *image)          { title_attract_loop(image); }
void g_level2_scenery_effect(uint8_t *image)       { level2_scenery_effect(image); }
void g_level2_scenery_effect_gate(uint8_t *image)  { level2_scenery_effect_gate(image); }
void g_debug_wait_for_keypad4(uint8_t *image)      { debug_wait_for_keypad4(image); }
void g_hiscore_name_entry(uint8_t *image)          { hiscore_name_entry(image); }
