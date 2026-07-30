/* player.h — the player-control layer: the joystick-driven rider, and what happens when one dies.
 *
 * Every A_* address is a Ghidra address (image offset + the 0x10000 load base) and mirrors a `var`
 * line in ../../names.txt, which stays the source of truth for the name. Only what this layer alone
 * touches is declared here: the object record and the 68000 primitives are in joust.h, the globals
 * shared with other layers in addrs.h, the message table in object.h, the message record's own
 * fields and the lives row in score.h, the sprite erase in draw.h, and one flags-word bit in
 * world.h.
 */
#ifndef JOUST_PLAYER_H
#define JOUST_PLAYER_H

#include <stdint.h>

#include "addrs.h"
#include "draw.h"    /* draw_object_mask, and A_player2 — the slot both routines here compare against */
#include "joust.h"
#include "object.h"  /* the message table itself: MSG_KIND, MSG_SCREEN_PTR */
#include "score.h"   /* find_free_message, draw_lives_p1/p2, A_players_alive, the message record's
                      * remaining fields, and OBJ_SCORE_LAST_DIGIT / OBJ_LIVES */
#include "world.h"   /* OBJ_FLAG_GRABBED; its partner OBJ_FLAG_DEAD is shared, so it is in joust.h */

/* --- globals ---------------------------------------------------------------------------------- */
#define A_two_player_mode   0x10d11u  /* .b — nonzero once the title screen picked a two-player game */

/* The flags word's two "flapping" bits. ../../names.txt calls bit 6 and bit 11 alike "flapping",
 * and every instruction that touches them touches BOTH in the same breath — bset/bset, bclr/bclr,
 * bchg/bchg — so they are named once as a mask rather than guessed apart. */
#define OBJ_FLAGS_FLAPPING   0x0840u

/* --- the joystick byte control_player is handed in D0 -----------------------------------------
 * SECOND READER, DELIBERATELY NOT SHARED YET: src/input.c names the same three bits JOY_FIRE /
 * JOY_RIGHT / JOY_LEFT for the high-score entry's stick reader. Two layers now read them, so by the
 * rule addrs.h states for globals they have earned a move into a shared header — but that edits
 * input.c, which is outside this change. Until then the two spellings are pinned equal by
 * test_player.py::test_joystick_bits_match_input_c, so a drift fails loudly instead of silently.
 * Only these three bits are tested (`btst #7/#3/#2,d0`), so the up/down bits and the whole high
 * half of D0 are dead here. */
#define STICK_FLAP   0x80u
#define STICK_RIGHT  0x08u
#define STICK_LEFT   0x04u

/* --- control_player --------------------------------------------------------------------------- */
#define PLAYER_STEER_VX  4   /* `move.w #$4` / `#$fffc` — the target speed a pushed stick asks for */

/* Where a dead rider's drift finally carries it off the playfield. The two facings are measured
 * differently and the asymmetry is real: facing right ANY x at or past DEAD_EXIT_RIGHT_X ends the
 * run, facing left only a four-pixel window does, and a corpse that overshoots it hovers on. */
#define DEAD_EXIT_RIGHT_X   0x13c
#define DEAD_EXIT_LEFT_LO   0x130
#define DEAD_EXIT_LEFT_HI   0x133

/* The hover ladder: which altitude a dead rider aims for, chosen by the band its own y is in.
 * Screen y grows downward, so each band aims HIGHER (smaller y) than the one below it. */
#define HOVER_BAND_HIGH_Y   0x28   /* y at or above this (numerically <=) aims for HOVER_TARGET_HIGH */
#define HOVER_BAND_MID_Y    0x64
#define HOVER_TARGET_HIGH   0x0au
#define HOVER_TARGET_MID    0x42u
#define HOVER_TARGET_LOW    0x8cu

/* What control_player reports in place of control flow the C has no analogue for: its no-players-
 * left path drops two return addresses and never comes back (see src/player.c). */
#define CONTROL_RETURNED  0u
#define CONTROL_RESTART   1u

#define GAME_OVER_SET  1u  /* `move.b #$1,game_over_flag` — check_highscore only runs when it is set */

/* --- the restart tail -------------------------------------------------------------------------- */
#define PLAYERS_ALIVE_ONE   1u
#define PLAYERS_ALIVE_TWO   2u
#define PLAYER_START_LIVES  4u
#define SCORE_UNITS_ZERO    0x30u  /* '0' */

/* --- player_death ------------------------------------------------------------------------------ */
#define LIVES_EXHAUSTED  0xffu  /* what `subq.b #1,OBJ_LIVES` leaves when the last life is taken */

/* The three end-of-turn banners, all posted into a message slot with the same shape. The two
 * per-player strings have no `var` line of their own in ../../names.txt yet; STR_GAME_OVER does
 * (score.h), which is why only these two are spelled out here. */
#define STR_PLAYER1_OVER  0x185d8u  /* "PLAYER 1 GAME OVER" */
#define STR_PLAYER2_OVER  0x185edu  /* "PLAYER 2 GAME OVER" */
#define BANNER_FRAMES     0x64u     /* MSG_TIMER: how long any of the three stays up */
#define BANNER_GAME_OVER_DST_OFF   0x3238u  /* added to screen_base for MSG_SCREEN_PTR ... */
#define BANNER_PLAYER_OUT_DST_OFF  0x3230u  /* ... one cell to the left for the per-player one */
#define BANNER_GAME_OVER_SHIFT     0u
#define BANNER_PLAYER_OUT_SHIFT    4u
#define BANNER_COLOR_GAME_OVER  1u
#define BANNER_COLOR_P1         7u
#define BANNER_COLOR_P2         2u

/* --- player.c ---------------------------------------------------------------------------------- */
uint32_t control_player(uint8_t *image, uint32_t object, uint32_t stick);
void restart_reset_players(uint8_t *image);
void player_death(uint8_t *image, uint32_t object);

#endif /* JOUST_PLAYER_H */
