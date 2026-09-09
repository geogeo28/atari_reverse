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

/* WHICH FIVE FILES, AND IN WHAT ORDER, is a dispatch on the level number. Levels 2 and 3 have an
 * arm each and everything else shares a third; the two lettered arms are the same five loads in the
 * same order as one another and differ from the third only in where the map goes.
 *
 * ALL FIVE PROMPTS IN THIS ROUTINE BUT ONE ARE PATCHED OUT (../names.txt @ 0x10390, 0x10422,
 * 0x1044c, 0x10498, 0x104cc: each prompt's `lea <message>,a6` head was overwritten with a `bra.s`
 * past the block, leaving the operand behind as unreachable bytes). This is a single-disc build.
 * The one that survives is 0x103cc, on the arm a level ABOVE 3 takes — and its own retry was
 * patched too (0x103ea: `bpl.w` -> `bra.w`), so it asks once and proceeds whatever the disc says. */
#define LEVEL_ASSETS_ORDER_LEVEL_2 2u /* `cmp.w #$2,d1 / beq.w $10404` @ 0x1037c */
#define LEVEL_ASSETS_ORDER_LEVEL_3 3u /* `cmp.w #$3,d1 / beq.w $1047a` @ 0x10384 */
/* ONE IMMEDIATE, TWO QUESTIONS, and they deserve two names. `cmp.w #$3,d1` appears again at
 * 0x103c4, but the branch under it is `blt.w $103f0` — "is the level PAST 3?", a SIGNED lower bound
 * on the arm that stops for a disc swap, not the equality dispatch above. The two are equal in the
 * shipped binary and are not the same fact: a build with a sixth stage would move one and not the
 * other, and a reader who saw `LEVEL_ASSETS_ORDER_LEVEL_3` at both sites could not tell which. */
#define DISC_SWAP_ABOVE_LEVEL 3u      /* `cmp.w #$3,d1 / blt.w $103f0` @ 0x103c4 — SIGNED */
/* `lea $16022,a6` @ 0x103cc — and it is NOT a string: 0x16022 is the middle of a word table, so its
 * first byte is >= 0x80 and `console_show_message` addresses the cursor and stops without printing
 * anything. What is left of the prompt is the two waits and the probe. (../names.txt @ 0x103ea.) */
#define A_disc_prompt_message 0x16022u
/* The `btst #7,$1777f` @ 0x103d6 the prompt's fire-PRESS spin re-reads the stick at. The fire
 * RELEASE it waits for first is inside `console_show_message`, at `include/hud.h`'s
 * FIRE_RELEASE_WAIT_PC — two wait sites in one call, which is why a case here names both. */
#define DISC_PROMPT_WAIT_PC 0x103d6u

/* ---- enter_title @ 0x1030e ---------------------------------------------------------------------
 *
 * Four instructions between a `bsr set_palette_black` and a `bra title_attract_loop`. The one
 * decision it makes is whether level 0's five files still have to be loaded, and its own answer to
 * that is `A_level0_assets_loaded` (include/init.h) — a byte the boot chain has already set, so the
 * load arm is unreachable in an ordinary boot and reached here by poking the word clear.
 */
#define A_title_just_entered 0x17698u /* `st $17698` @ 0x1030e, `clr.w $17698` @ 0x10632 — a BYTE
                                       * store into a word two `tst.w`s read. Set on the way into
                                       * the title screen and cleared by the mode toggle's first
                                       * pass, which is how the toggle tells "the screen has just
                                       * opened" from "the player pushed the stick left" */

/* ---- title_attract_loop @ 0x104f2: the stage start the attract screen does ---------------------- */
#define TITLE_SCROLL_POS_START 0u    /* `move.w $176ac,$17758` @ 0x104f6 — `A_const_words_0123`
                                      * index 0, this program's way of spelling a zero */

/* ---- title_attract_loop @ 0x1054a and @ 0x10562: the tune, and the spin it plays under ---------
 *
 * The attract screen is ONE loop with four branch exits and no `rts` but its own. From 0x1054a it
 * starts the jingle and clears the three lists; from 0x10562 it polls, draws a frame and comes
 * back. The four exits are: the fire button (its `rts`), the module saying the tune has finished
 * (back to 0x1054a), a high score waiting to be entered (into `hiscore_show_entry_screen`, which
 * comes straight back), and the scroll running out of map (back to 0x104f2).
 */
#define ATTRACT_TUNE 4u              /* `move.w #$4,d0 / bsr music_play` @ 0x1054a */
#define ATTRACT_END_SCROLL_POS 0xbb8u /* `cmpi.w #$bb8,$17758 / blt.s` @ 0x10598 — a SIGNED compare
                                       * whose NEGATIVE side the game's own data cannot reach: the
                                       * stage start seeds `scroll_pos` from `const_words_0123[0]`
                                       * (0) and `scroll_advance` only ever adds 2, so the word
                                       * climbs to 0xbb8 and the attract restarts. (`level_distance`
                                       * is the word that runs near 0xffff for the first two dozen
                                       * frames — include/scroll.h — and it is not this compare's.)
                                       * The sign is reproduced because it is the instruction, and
                                       * test_frontend.py's two negative positions are CONTRACT
                                       * coverage, reachable here only by a poke */
/* The `btst #7,$1777f` @ 0x1056a: the instruction the spin RE-READS the stick at, and therefore the
 * wait site both shores key their clocks to (tools/recreate_kit/include/sched.h). Nothing in the
 * program writes `A_joy1_state` — the ACIA interrupt does — so off target this loop could never end
 * without the kit's scheduled-write model. The bit is `include/hud.h`'s JOY_FIRE_BIT. */
#define TITLE_FIRE_WAIT_PC 0x1056au

/* ---- the attract pages @ 0x105a8, and the difficulty toggle inside the first of them ------------
 *
 * `A_attract_page_timer` counts DOWN once a frame and reloads from `A_attract_page_reload` when it
 * goes negative; which of three text scripts is compiled into the display list is a signed test on
 * what is left. The publisher page is also the one the stick can change the difficulty on.
 */
#define A_attract_page_timer  0x176e6u /* `subi.w #$1,$176e6` @ 0x105ae */
#define A_attract_page_reload 0x1771eu /* `move.w $1771e,$176e6` @ 0x105b8 */
#define A_text_publisher      0x160deu /* `lea $160de,a0` @ 0x105da */
#define A_text_credits        0x16146u /* `lea $16146,a0` @ 0x10670 */
#define ATTRACT_PAGE_HALL_OF_FAME_BELOW 0xc8u  /* `cmpi.w #$c8,$176e6 / blt.w` @ 0x105c2 */
#define ATTRACT_PAGE_CREDITS_BELOW      0x226u /* `cmpi.w #$226,$176e6 / blt.w` @ 0x105ce */

#define A_text_title_mode 0x16120u /* `lea $16120,a0` @ 0x10608 and 0x10644 */
#define A_title_word_hard 0x1612eu /* `lea $1612e,a1` @ 0x1064e; the EASY and SPAM words beside it
                                    * are `include/hud.h`'s `A_title_word_easy` and `_spam` */
#define TITLE_MODE_WORD_OFFSET 10u /* `lea 10(a0),a0` @ 0x1060e and 0x1064a — where inside the
                                    * "MODE EASY" script the four-character word sits. NOTHING
                                    * DRAWS THAT SCRIPT (../names.txt @ 0x16120): it is not one of
                                    * the three pages `build_text_display_list` is given, so the
                                    * copy is latent and the flag beside it is the live half */
#define TITLE_MODE_WORD_BYTES  4u  /* three `move.b (a1)+,(a0)+` and a fourth without the step */
/* The two stick bits, named for what they do HERE — `src/player.c` spells the same two privately as
 * JOY_LEFT_BIT and JOY_RIGHT_BIT, and the flight code's names would read as movement at a site
 * where the stick picks a difficulty. `include/frontend.h`'s NAME_ENTRY_*_GLYPH_BIT below is the
 * same argument at the same two bits. */
#define TITLE_MODE_EASY_BIT 2u /* `btst #2,$1777f` @ 0x105f8 — stick left */
#define TITLE_MODE_HARD_BIT 3u /* `btst #3,$1777f` @ 0x1063a — stick right */
/* What the HARD arm writes to `A_hard_mode` (include/hud.h): `move.b #$1,$177cc` @ 0x1065c, a 1 and
 * not the 0xff an `Scc` leaves — which `start_level`'s two `st $177cc` are. Every reader tests the
 * byte against zero, so the difference is invisible to the game and visible only here. The EASY arm
 * writes the high byte of `A_const_words_0123` instead (`move.b $176ac,$177cc` @ 0x1061a), which is
 * this program's habit of spelling a 0 as a table read. */
#define TITLE_HARD_MODE_ON 1u

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

/* `load_level_assets` @ 0x10332, whole: the digit patch and then the level's five files. D0 is the
 * level number; the routine has neither floor nor ceiling and the multiply is SIGNED. */
void load_level_assets(uint8_t *image, uint16_t level);

/* Its head, [0x10332, 0x10372) — the five filename digits, up to the first `bsr load_file`. It is a
 * core of its own because the digit table is what the whole routine is indexed by, and because the
 * out-of-range levels that pin `muls.w #$5` as signed cannot be driven through the loads. */
void load_level_assets_patch_filenames(uint8_t *image, uint16_t level);

/* ---- the title flow's four cores, and the exit each answers with ------------------------------
 *
 * The original spells every one of these exits as a BRANCH, which is why the flow had no core until
 * the routines behind those branches were all verified. Each enum value carries the instruction it
 * stands for, and `title_attract_loop` below is the loop that reads them.
 */

/* `enter_title` @ 0x1030e. */
typedef enum {
    ENTER_TITLE_LOAD_LEVEL0, /* `bsr.w load_level_assets` @ 0x1032a, with D0 = 0 */
    ENTER_TITLE_ATTRACT      /* `bne.w $104f2` @ 0x1031e, and the `bra.w $104f2` below it */
} enter_title_exit;

/* One pass of the attract poll @ 0x10562. */
typedef enum {
    TITLE_POLL_NEXT_FRAME, /* `beq.s $105a8` and every page arm's `bra.w $10594` */
    TITLE_POLL_START_GAME, /* `bne.s $105a6` -> `rts`: fire, and no high score to enter */
    TITLE_POLL_TUNE_ENDED  /* `beq.s $1054a`: the module's `music_active` byte has gone clear */
} title_poll_exit;

/* ...and one attract frame @ 0x10594. */
typedef enum {
    TITLE_FRAME_POLL_AGAIN,  /* `blt.s $10562` */
    TITLE_FRAME_ATTRACT_OVER /* `bra.w $104f2`: the scroll has run out of map */
} title_frame_exit;

/* `enter_title` @ 0x1030e, SLICE [0x1030e, 0x1032a) on its load arm and [0x1030e, 0x104f2) on the
 * other: the "just entered" flag, the black palette and the one test it makes. It ends in a branch
 * either way, so both arms are diffed at a checkpoint PC. */
enter_title_exit enter_title(uint8_t *image);

/* `title_attract_loop` @ 0x104f2, SLICE [0x104f2, 0x1054a): the attract screen's stage start —
 * the palette blacked, then scroll position, scroll phase, map cursor, and the whole screen
 * scrolled in behind it. The opening `bsr set_palette_black` is the `init` subsystem's and writes
 * no image byte: the ordered OS EVENT is its whole surface. */
void title_attract_prescroll(uint8_t *image);

/* `title_attract_loop` @ 0x1054a, SLICE [0x1054a, 0x10562): the jingle and the three lists cleared,
 * where the loop restarts whenever the tune runs out. */
void title_attract_start_tune(uint8_t *image);

/* `title_attract_loop` @ 0x10562, SLICE [0x10562, 0x10594): the poll, and — through the `beq.s
 * $105a8` at its foot — the attract page cycle at 0x105a8..0x10696 that every arm of ends
 * `bra.w $10594`. So the span is not contiguous, in the way `hiscore_name_entry`'s is not. */
title_poll_exit title_attract_poll(uint8_t *image);

/* `title_frame_step` @ 0x10594, SLICE [0x10594, 0x10562): one frame drawn, and the scroll test that
 * decides whether the attract screen carries on or starts again. */
title_frame_exit title_frame_step(uint8_t *image);

/* The loop those four make: `title_attract_loop` from its 0x104f2 head to the `rts` @ 0x105a6 that
 * is its only way out. It is a composition and not a fifth slice — every byte of it is one of the
 * rows above — but it is what a whole-flow differential runs, and what an on-target build calls. */
void title_attract_loop(uint8_t *image);

/* `level2_scenery_effect` @ 0x1003c and its caller `level2_scenery_effect_gate` @ 0x10bc8, whole. */
void level2_scenery_effect(uint8_t *image);
void level2_scenery_effect_gate(uint8_t *image);

/* `debug_wait_for_keypad4` @ 0x11ba2, whole. */
void debug_wait_for_keypad4(uint8_t *image);

/* `hiscore_name_entry` @ 0x10916, SLICE [0x10916, 0x10720): every arm ends `bra.w $10720`, a branch
 * into `title_frame_step`, so the routine has no `rts` and the slice is diffed at that branch. */
void hiscore_name_entry(uint8_t *image);

#endif /* FS_FRONTEND_H */
