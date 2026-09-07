/* hud.h — the score, the hall of fame, the readouts they feed, and the console leftovers.
 *
 * WHAT THIS SUBSYSTEM IS. Flying Shark keeps the score as three packed-BCD bytes, expands them into
 * six GLYPH IDS, and publishes those (plus the bomb and life icons) as six-byte records in the
 * display list the renderer walks. The hall of fame is the same glyph alphabet again: its six rows
 * are simultaneously the tail of the attract screen's text script, so one table is both data and
 * program (../notes/frontend.md §5). Everything here is arithmetic over the image — nothing in this
 * file draws a pixel.
 *
 * THE GLYPH ALPHABET is the game's own, not ASCII: 0xab..0xc4 = 'A'..'Z', 0xc5..0xce = '0'..'9',
 * 0xcf = space, 0xd0 and up = HUD captions and icons (../notes/frontend.md §1). `bcd3_to_digits`
 * adding 0xc5 to each nibble is where that mapping comes from, and it is why the glyph for '0' is
 * the one constant this file names most often.
 *
 * ADDRESS PROVENANCE. Every `A_*` is a `var` line in ../names.txt at load base 0x10000; every
 * routine address is an `fn` line there. Offsets and counts are read off ../out/prg_dis.txt at the
 * instruction named beside them, so a reader can check a number without a disassembler.
 */
#ifndef FS_HUD_H
#define FS_HUD_H

#include <stdint.h>

#include "globals.h"       /* the memory model — `A_screen_prev1` is its, and is read here */
#include "display_list.h"  /* the six-byte record every routine here publishes — frozen, not restated */
#include "sprite.h"        /* `A_map_row_ptr`, `A_map_row_ptr_reset` and `A_scroll_fine`, which the
                            * debug overlay formats. The scroll subsystem owns them and is unported,
                            * so sprite.h holds them on loan and this header READS them from there */

/* ---- the glyph alphabet -------------------------------------------------------------------- */
#define GLYPH_A      0xabu   /* `cmpi.b #$ab,(a0)` @ 0x10984 — the wrap floor of name entry */
#define GLYPH_ZERO   0xc5u   /* `addi.b #$c5,d0` @ 0x10b12 — digit 0; digit n is GLYPH_ZERO + n */
#define GLYPH_SPACE  0xcfu   /* `move.b #$cf,(a0)` @ 0x10946 — and name entry's wrap ceiling */
#define GLYPH_SCORE_CAPTION   0xd0u /* `move.b #$d0,(a0)+` @ 0x10a10 */
#define GLYPH_HISCORE_CAPTION 0xd1u /* `move.b #$d1,(a0)+` @ 0x10a20 */
#define GLYPH_BOMB_ICON       0x81u /* `move.b #$81,4(a0)` @ 0x12428 */
#define GLYPH_LIFE_ICON       0x82u /* `move.b #$82,4(a0)` @ 0x12496 */

/* ---- the score ------------------------------------------------------------------------------
 * Three packed-BCD bytes = six digits, and the HUD prints five of them plus a literal '0'
 * (`hud_publish_digit_row`), so the lowest digit is always zero and every award is a multiple of 10.
 */
#define A_score_bcd     0x15a2au /* `lea $15a2a,a0` @ 0x110d4 */
#define A_hiscore_bcd   0x15a2du /* `lea $15a2d,a0` @ 0x10bec — ALSO one past A_score_bcd's end */
#define SCORE_BCD_BYTES 3u       /* the three `abcd -(a1),-(a0)` @ 0x10bf2..0x10bf6 */

#define A_score_digits   0x159f4u /* `lea $159f4,a0` @ 0x10a2a */
#define A_hiscore_digits 0x159fau /* `lea $159fa,a1` @ 0x10a30 */
#define SCORE_DIGITS     6u       /* `move.w #$5,d7` + dbf @ 0x10a36 — and 2 * SCORE_BCD_BYTES */

/* The nine awards, back to back, three BCD bytes each: 50, 100, 200, 250, 500, 1000, 3000, 5000,
 * 10000. `score_add_bcd` walks its addend BACKWARDS, so each wrapper passes the address ONE PAST
 * its own value — `score_add_50` @ 0x10b28 loads `lea $15a33,a1`, which is award 0's end. */
#define A_score_award_values 0x15a30u /* `var 0x15a30 score_value_50` */
#define SCORE_AWARDS         9u       /* 0x10b28, 0x10b3c, ... 0x10bb4 and 0x10bd8 */

/* The index into that run each wrapper selects, so that a caller's `bsr score_add_1000` reads as
 * one. Here rather than in the calling subsystem because the run is this header's and
 * `test_constants.py::test_no_constant_is_defined_in_two_files` allows one home per name — three
 * subsystems now reach the chain (hud's own wrappers, weapons' hit handlers, entity's bonus drop). */
#define SCORE_AWARD_50     0u
#define SCORE_AWARD_100    1u
#define SCORE_AWARD_200    2u
#define SCORE_AWARD_250    3u
#define SCORE_AWARD_500    4u
#define SCORE_AWARD_1000   5u
#define SCORE_AWARD_3000   6u
#define SCORE_AWARD_5000   7u
#define SCORE_AWARD_10000  8u

/* ---- the extra-life thresholds --------------------------------------------------------------
 * Seven six-glyph scores — 050000, 200000, 350000, 500000, 650000, 800000, 950000 — each granting
 * one life exactly once, tracked by its own word flag. `award_extra_life` @ 0x110d4 tests them in
 * order and stops at the first flag that is still clear, so a score that jumps two thresholds in one
 * award collects the second only on the next call.
 */
#define A_bonus_life_thresholds 0x15a00u /* `lea $15a00,a5` @ 0x110f8 */
#define A_bonus_life_awarded_0  0x176c6u /* `lea $176c6,a3` @ 0x110f2; the flags are consecutive */
#define BONUS_LIFE_THRESHOLDS   7u       /* the seven `tst.w` arms @ 0x110ea..0x11170 */
#define BONUS_LIFE_FLAG_BYTES   2u       /* `move.w #$1,(a3)` @ 0x1119c — a WORD flag */
#define BONUS_LIFE_AWARDED      1u       /* ...and the value it is set to */

/* `A_lives` and `A_bombs` are `include/player.h`'s: the extra-life award raises one and the icon
 * rows draw both, but the counters are the player's state. `src/hud.c` includes that header. */

/* ---- the hall of fame ------------------------------------------------------------------------
 * Six 22-byte rows that ARE the tail of `text_hall_of_fame`'s display-list script, which is why the
 * layout carries script opcodes as well as data (../notes/frontend.md §5).
 */
#define A_hiscore_table    0x161ddu /* `lea $161dd,a0` @ 0x108c4 */
#define HISCORE_ENTRIES    6u       /* `move.w #$5,d7` + dbf @ 0x108ca */
#define HISCORE_STRIDE     22u      /* `muls.w #$16,d0` @ 0x107da */
#define HISCORE_NAME       11u      /* `lea 11(a0),a0` @ 0x10934 — three name glyphs */
#define HISCORE_NAME_CHARS 3u       /* `cmpi.w #$2,$176e2` @ 0x109aa caps the cursor at 2 */
#define HISCORE_SCORE      16u      /* `lea 16(a5),a5` @ 0x108fc — six score glyphs */
/* `hiscore_shift_entry_down` @ 0x108aa pushes one row's name and score into the NEXT row without
 * moving the leading script bytes or the rank digit at +8. */
#define HISCORE_SHIFT_FROM  9u      /* `lea 9(a0),a0` @ 0x108ae */
#define HISCORE_SHIFT_BYTES 13u     /* `move.w #$c,d7` + dbf @ 0x108aa */
/* ...and the last score glyph, which `hiscore_reset_last_digit` stamps back to '0'. */
#define HISCORE_LAST_DIGIT 21u      /* `move.b #$c5,21(a0)` @ 0x108ce */

#define A_hard_mode           0x177ccu /* `clr.b $177cc` @ 0x10724 */
#define A_name_entry_done     0x176dcu /* `tst.w $176dc` @ 0x10916 */
#define A_name_entry_timeout  0x176deu /* `move.w #$32,$176de` @ 0x109f6 */
#define A_hiscore_rank        0x176e0u /* `move.w #$5,$176e0` @ 0x1072a */
#define A_hiscore_beaten      0x176e4u /* `st $176e4` @ 0x10a48 — a BYTE store into a word */
#define A_new_hiscore_pending 0x176e8u /* `st $176e8` @ 0x107ee */
#define A_const_words_0123    0x176acu /* `move.w $176ac,$176de` @ 0x107f4 — a constant 0 word */

#define HISCORE_LOWEST_RANK 5u /* `move.w #$5,$176e0` @ 0x1072a: rank 5 is the SIXTH row */
/* `game_over_hiscore_check` stamps this over score digit 5 to make a tying score compare HIGH — and
 * the very next instruction calls `bcd3_to_digits`, which rewrites all six digits including that
 * one. A DEAD STORE, and the tie it was meant to win is lost instead (src/hud.c says how). */
#define SCORE_TIE_BREAK_GLYPH 0xf0u /* `move.b #$f0,5(a1)` @ 0x1073e */

/* `digits6_compare`'s answer, a WORD in D0 (`move.w #$ffff,d0` / `move.w #$1,d0`). */
#define DIGITS_COMPARE_LOWER_OR_EQUAL 0xffffu /* @ 0x1090a — and the ALL-EQUAL result too */
#define DIGITS_COMPARE_HIGHER         0x0001u /* @ 0x10910 */

/* ---- the cheat system ------------------------------------------------------------------------ */
#define A_cheat_handler_table 0x191ccu /* `lea $191cc,a0` @ 0x10e08 */
#define A_cheat_name_table    0x191e4u /* `lea $191e4,a1` @ 0x10db4 */
#define CHEAT_ROW_BYTES       4u       /* `lea 4(a1),a1` @ 0x10dc6: three glyphs + a handler index */
#define CHEAT_INDEX_PAST_LAST_GLYPH 1u /* `move.b 1(a1),d0` @ 0x10e04, with a1 on the row's THIRD
                                        * glyph — so the handler index is the byte after it */
#define CHEAT_TABLE_END       0x64u    /* `cmpi.b #$64,(a1)` @ 0x10dba */
#define CHEAT_HANDLER_BYTES   4u       /* `lsl.w #2,d0` @ 0x10e0e — longword pointers */
/* The arm key: a cheat only takes while keypad '4' is held, which the ACIA ISR reports as bit 0 of
 * `key_bits`. `check_cheat_name` spins CHEAT_ARM_SPINS times looking for it and gives up. */
#define A_key_bits        0x17780u /* `btst #0,$17780` @ 0x10d9a */
#define CHEAT_ARM_KEY_BIT 0u
#define CHEAT_ARM_SPINS   0x1389u  /* `move.w #$1388,d7` + dbf @ 0x10d96: 5000 means 5001 passes */
/* The PC the arm spin RE-READS `key_bits` at — the site every `sched_poll8` names and the trigger a
 * case's schedule declares. The byte is the ACIA interrupt's, so the count of iterations is only
 * observable through that model (tools/recreate_kit/include/sched.h, "WAIT SITES"). */
#define CHEAT_ARM_WAIT_PC 0x10d9au
#define A_cheat_used_flag 0x176d4u /* `st $176d4` @ 0x10daa — set on any match, never read */
/* ...and the title screen's tell: "MODE EASY" becomes "MODE SPAM" once any cheat has taken. */
#define A_title_word_easy 0x16132u /* `lea $16132,a0` @ 0x10e1c */
#define A_title_word_spam 0x16136u /* `lea $16136,a1` @ 0x10e16 */
#define TITLE_WORD_GLYPHS 4u       /* the four `move.b (a1)+,(a0)+` @ 0x10e22..0x10e28 */

/* The six handlers `cheat_handler_table` holds, as `fn` lines in ../names.txt. `check_cheat_name`
 * dispatches on the ADDRESS it read out of that table, so these are the cases of its switch. */
#define FN_CHEAT_HSC  0x10e30u
#define FN_CHEAT_KDJ  0x10e4cu
#define FN_CHEAT_JGL  0x10e56u
#define FN_CHEAT_GCC  0x10e60u
#define FN_CHEAT_JML  0x10e6au  /* `movea.l #0,a0 / jsr (a0)` — never dispatched; see src/hud.c */
#define FN_CHEAT_JH   0x10e72u

#define A_invuln_flag            0x177c6u /* `move.b #$1,$177c6` @ 0x10e42 */
#define A_infinite_lives_flag    0x177c7u /* `move.b #$1,$177c7` @ 0x10e4c */
#define A_infinite_bombs_flag    0x177c8u /* `move.b #$1,$177c8` @ 0x10e56 */
#define A_alt_bullet_glyph_flag  0x177c9u /* `move.b #$1,$177c9` @ 0x10e60 */
#define A_max_weapon_flag        0x177cau /* `move.b #$1,$177ca` @ 0x10e72 */
#define CHEAT_FLAG_SET           1u       /* every handler stores 1, not 0xff */
/* THE FIVE FLAGS ABOVE ARE THIS HEADER'S AND ARE NOT ON LOAN, which STATUS.md's table used to say
 * they were. `check_cheat_name` @ 0x10e16 and its five handlers — all `src/hud.c` — are the only
 * things that WRITE them; the player and weapons cores read them out of this header. A global lives
 * with the subsystem that owns the data (../README.md), and the data is the cheat state.
 *
 * `A_player_hit`, which the invulnerability cheat also writes, is NOT one of them: it is the
 * player's own state that everything which fires reads, so it lives in `include/player.h`. */

/* ---- the display-list records this subsystem publishes into -----------------------------------
 * The RECORD is `include/display_list.h`'s and is not restated; what is here is where each of this
 * subsystem's own runs of records begins. `clear_display_list` @ 0x115a8 byte-clears the whole list
 * between that header's `A_display_list` and `A_display_list_end`.
 */
#define A_hud_label_slots   0x17ca8u /* `lea $17ca8,a0` @ 0x10a02 — the two captions */
#define A_hud_score_slots   0x17cb4u /* `lea $17cb4,a1` @ 0x10a56 */
#define A_hud_hiscore_slots 0x17cd8u /* `lea $17cd8,a1` @ 0x10a7e */
#define A_dl_bomb_icons     0x17c36u /* `lea $17c36,a0` @ 0x123ec */
#define A_dl_life_icons     0x17c60u /* `lea $17c60,a0` @ 0x1244c */
/* `clear_player_display_slots` @ 0x115c2 clears the PLAYER's two records; their address is
 * `A_dl_player_shadow` in `include/player.h`, which this subsystem reads rather than restates. */

/* `hud_build_score_digits` writes six slots per readout but the leading-zero blanker only ever walks
 * five: the sixth is the forced '0' and is never blanked. */
#define HUD_DIGIT_SLOTS         6u    /* five from the dbf @ 0x10a94, plus the tail @ 0x10aa6 */
#define HUD_BLANKABLE_SLOTS     5u    /* `move.w #$4,d7` + dbf @ 0x10ac8 */
#define HUD_SCORE_X             0x50u /* `move.w #$50,d1` @ 0x10a5c */
#define HUD_HISCORE_X           0xc0u /* `move.w #$c0,d1` @ 0x10a84 */
#define HUD_DIGIT_Y             0x0cu /* `move.w #$c,d2` @ 0x10a60 and 0x10a88 */
#define HUD_DIGIT_X_STEP        8u    /* `addi.w #$8,d1` @ 0x10a9e */
#define HUD_LABEL_SCORE_X       0x5cu /* `move.w #$5c,(a0)+` @ 0x10a08 */
#define HUD_LABEL_HISCORE_X     0xc8u /* `move.w #$c8,(a0)+` @ 0x10a18 */
#define HUD_LABEL_Y             2u    /* `move.w #$2,(a0)+` @ 0x10a0c and 0x10a1c */

/* The icon rows. Both clear seven enable bytes and then publish as many icons as the counter says —
 * with no upper bound on the counter, which is a real overrun the reconstruction reproduces. */
#define HUD_ICON_SLOTS_CLEARED 7u     /* the seven `clr.b n(a0)` @ 0x123f2..0x1240a and 0x12452.. */
#define HUD_BOMB_ICON_X        0x130u /* `move.w #$130,d6` @ 0x1241a */
#define HUD_BOMB_ICON_Y        0x0bfu /* `move.w #$bf,d5` @ 0x1241e */
#define HUD_BOMB_ICON_X_STEP   0x10u  /* `subi.w #$10,d6` @ 0x12434 — the row grows LEFTWARD */
#define HUD_LIFE_ICON_X        2u     /* `move.w #$2,d6` @ 0x12488 */
#define HUD_LIFE_ICON_Y        0x0beu /* `move.w #$be,d5` @ 0x1248c */
#define HUD_LIFE_ICON_X_STEP   0x0cu  /* `addi.w #$c,d6` @ 0x124a2 */
#define HUD_LIVES_SHOWN_MAX    7u     /* `cmp.w #$7,d7` @ 0x12474 — and it is written BACK */

/* `hud_publish_bomb_and_life_icons` gates both halves on the player's control mode. `A_player`,
 * `PLAYER_MODE` and `PLAYER_MODE_GAMEOVER` are `include/player.h`'s — the whole record is. */

/* ---- the text-script compiler ---------------------------------------------------------------
 * `build_text_display_list` @ 0x10698 reads `[x.b][y.b]` and then a byte stream, emitting one slot
 * per glyph. ../notes/frontend.md §5 has the script table.
 */
#define TEXT_OP_SPACE   0x00u /* `addi.w #$8,d1` @ 0x106d6 */
#define TEXT_OP_TAB     0x04u /* `addi.w #$40,d1` @ 0x106dc */
#define TEXT_OP_NEWLINE 0x05u /* `addi.w #$8,d2 / clr.w d1` @ 0x106e2 */
#define TEXT_OP_INDENT  0x06u /* `add.w $40.l,d1` @ 0x106ea — see LOW_MEMORY_INDENT_WORD */
#define TEXT_OP_END     0x09u /* `rts` @ 0x106c4 */
#define TEXT_LINE_HEIGHT  8u  /* the newline's `addi.w #$8,d2` @ 0x106e2 */
#define TEXT_GLYPH_WIDTH  8u  /* `addi.w #$8,d1` @ 0x106d0 (a glyph) and @ 0x106d6 (a space) */
#define TEXT_TAB_WIDTH    0x40u

/* THE 0x06 OPCODE READS ABSOLUTE ADDRESS 0x40, which is the 68000's vector page and not this
 * program's data at all — the high word of TOS's `_etv_timer` slot on a real machine. Nothing in
 * the game ever writes it, and the scripts that use the opcode therefore indent by whatever the OS
 * left there. It is reproduced rather than repaired (recreate, not remaster); ../names.txt @ 0x10698
 * calls it "almost certainly a bug" and this is the address it means. */
#define LOW_MEMORY_INDENT_WORD 0x40u   /* deliberately not an `A_*`: it is not in the program */

#define A_text_hall_of_fame     0x161ceu /* `lea $161ce,a0` @ 0x106fc */
#define A_text_enter_your_name  0x16262u /* `lea $16262,a0` @ 0x10712 */

/* ---- the console leftovers -------------------------------------------------------------------
 * Development code that survived into the shipped binary: a binary-dump printer with no caller at
 * all, and an overlay gated on a flag nothing ever writes (../notes/frontend.md §7).
 */
#define A_joy1_state   0x1777fu /* `btst #7,$1777f` @ 0x149f0 */
#define JOY_FIRE_BIT   7u
/* The PC the fire-release wait RE-READS the byte at, which is the site every `sched_poll8` names and
 * the trigger a case's schedule declares (tools/recreate_kit/include/sched.h, "WAIT SITES"). */
#define FIRE_RELEASE_WAIT_PC 0x149f0u

#define CONSOLE_ESCAPE     0x1bu /* the four `move.w #..,-(a7) / Cconout` @ 0x149b2..0x149d8: */
#define CONSOLE_POSITION   0x59u /* ESC 'Y' <row+0x20> <column+0x20>, VT52 cursor addressing... */
#define CONSOLE_ROW_24     0x38u /* ...row 24... */
#define CONSOLE_COLUMN_0   0x20u /* ...column 0 */
#define CONSOLE_TEXT_END   0x80u /* `bmi.s` @ 0x149e2: a byte with bit 7 set ends the message */
#define CONSOLE_KEEP_PHYSBASE (-1) /* Setscreen(log, -1, -1) @ 0x149a0: change only the LOGICAL base */
#define CONSOLE_KEEP_RESOLUTION ((int16_t)-1)

#define BINARY_DUMP_BITS 0x10u /* `move.w #$10,d5` @ 0x11574 */
#define ASCII_ZERO       0x30u /* `move.w #$30,d0` @ 0x11596, and format_5_digits' fill */
#define ASCII_ONE        0x31u /* `move.w #$31,d0` @ 0x1157c */
#define ASCII_CR         0x0du /* `move.w #$d,d0` @ 0x11588 */

/* `debug_show_counters` @ 0x14960 patches three five-digit fields into the message in place. */
#define A_debug_map_advance_field 0x14a05u /* `lea $14a05,a0` @ 0x14960 */
#define A_debug_scroll_pos_field  0x14a11u /* `lea $14a11,a0` @ 0x14976 */
#define A_debug_scroll_fine_field 0x14a1eu /* `lea $14a1e,a0` @ 0x14986 */
/* All four counters it formats belong to subsystems that are unported. `A_map_row_ptr`,
 * `A_map_row_ptr_reset` and `A_scroll_fine` are on loan in `include/sprite.h` and read from there;
 * `A_scroll_pos` is the frontend's and is on loan HERE, because nothing else defines it yet. Each
 * has a row in STATUS.md's "Borrowed globals". */
#define A_scroll_pos              0x17758u /* `move.w $17758,d0` @ 0x1497c — BORROWED, see STATUS */
#define FORMAT_DIGITS             5u       /* the five `move.b #$30,(a0)+` @ 0x14a76..0x14a86 */
#define FORMAT_RADIX              10u      /* `divu.w #$a,d0` @ 0x14a96 */

/* ---- the cores ------------------------------------------------------------------------------
 * Every one of them takes the flat image; the register ABI is spelt in the `g_*` glue in src/hud.c,
 * one line per routine.
 */
unsigned score_add_bcd(uint8_t *image, uint32_t value_end, unsigned extend_in);
unsigned score_add_award(uint8_t *image, unsigned award, unsigned extend_in);
void bcd3_to_digits(uint8_t *image, uint32_t bcd, uint32_t digits);
void scores_bcd_to_chars(uint8_t *image);
void score_reset(uint8_t *image);
void clear_3_bytes(uint8_t *image, uint32_t dest);
uint32_t format_5_digits(uint8_t *image, uint32_t field_end, uint32_t value);

uint16_t digits6_compare(uint8_t *image, uint32_t *entry, uint32_t *score);
void check_beat_hiscore(uint8_t *image);
unsigned award_extra_life(uint8_t *image);

void hud_publish_digit_row(uint8_t *image, uint32_t chars, uint32_t slots, uint32_t x, uint32_t y);
void hud_build_score_digits(uint8_t *image);
void hud_blank_leading_zeros_row(uint8_t *image, uint32_t slots);
void hud_blank_leading_zeros(uint8_t *image);
void hud_build_labels(uint8_t *image);
void hud_publish_bomb_and_life_icons(uint8_t *image);
void clear_display_list(uint8_t *image);
void clear_player_display_slots(uint8_t *image);
void build_text_display_list(uint8_t *image, uint32_t *script, uint32_t *dest, uint32_t *x,
                             uint32_t *y);

void hiscore_shift_entry_down(uint8_t *image, uint32_t entry);
void hiscore_reset_last_digit(uint8_t *image);
void hiscore_show_entry_screen(uint8_t *image);
void game_over_hiscore_check(uint8_t *image);
void hiscore_insert_score_at_rank(uint8_t *image);
void check_cheat_name(uint8_t *image, uint32_t name_last_char);
void cheat_hsc_invulnerable(uint8_t *image);
void cheat_kdj_infinite_lives(uint8_t *image);
void cheat_jgl_infinite_bombs(uint8_t *image);
void cheat_gcc_alt_glyph(uint8_t *image);
void cheat_jh_max_weapon(uint8_t *image);

void console_putc(uint32_t ch);
void debug_print_word_binary(uint32_t value);
void console_show_message(uint8_t *image, uint32_t text);
void debug_show_counters(uint8_t *image);

#endif /* FS_HUD_H */
