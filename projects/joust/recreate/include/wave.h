/* wave.h — the wave director: what happens between one wave of riders and the next.
 *
 * Every A_* address is a Ghidra address (image offset + the 0x10000 load base) and mirrors a `var`
 * line in ../../names.txt, which stays the source of truth for the name. Only what this layer alone
 * touches is spelled out here: the globals it shares with the world, object, HUD and egg layers are
 * INCLUDED from their own headers rather than restated (a second copy would drift silently — see
 * the pin in test/test_constants.py).
 *
 * wave_manager is one entry with two code chunks: the dispatcher at 0x1783c and the wave-start body
 * at 0x17012, which nothing else ever branches to. They are one function (Ghidra counts 2660 bytes
 * across both) and the reconstruction keeps them one function.
 */
#ifndef JOUST_WAVE_H
#define JOUST_WAVE_H

#include <stdint.h>

#include "addrs.h"
#include "egg.h"      /* the egg record this layer seeds */
#include "joust.h"
#include "object.h"   /* game_phase, the counts, the message table, the platform boxes and the
                       * pterodactyl table this layer clears */
#include "player.h"   /* BANNER_FRAMES and BANNER_COLOR_P1: player_death posts its end-of-turn
                       * banners with the same timer and the same player-1 colour these do, so they
                       * are INCLUDED rather than restated. They have outgrown that header — the
                       * message record's shared vocabulary belongs beside MSG_* in score.h — but
                       * moving them is a change to the player layer, which this one does not own. */
#include "score.h"    /* find_free_message and the two score_update entries */
#include "world.h"    /* wave_num, the lava floor and the ground burn this layer arms */

/* ---- globals ------------------------------------------------------------------------------- */
/* The drawn wave number: draw_string's `09 01` control pair (laid down by init_game) followed by
 * two digit bytes. The message that shows it is handed THIS ADDRESS as its string. */
#define A_wave_num_text     0x10cf4u  /* .b[4] */
#define A_wave_num_tens     0x10cf6u  /* .b — starts blank and is forced to '1' on the first carry */
#define A_wave_num_units    0x10cf7u  /* .b */

/* platform_present's loop bound: the original's own `cmpa.l #$d02`, which is the next global up.
 * The deliberate duplication object.h documents for its `_END`s. */
#define A_platform_present_END  0x10d02u  /* == A_egg_wave_countdown */

/* The four special-wave latches. Each is a ONE-SHOT: the bonus half arms it to SPECIAL_WAVE_LEAD
 * and the announce half takes one off per game_phase tick, posting its banner as it lands on 0. */
#define A_egg_wave_countdown        0x10d02u  /* .b — 0 during the wave that hatches eggs instead
                                               * of spawning riders */
#define A_team_wave_countdown       0x10d03u  /* .b */
#define A_ptero_wave_countdown      0x10d04u  /* .b */
/* The fourth, A_gladiator_wave_countdown, is addrs.h's — the collision resolver reads it too, along
 * with the player_conflict_flag and first_dismount_owner this layer arms and pays out. */

#define A_spawn_in_progress     0x10d13u  /* .b — nonzero while a rider is materialising; the
                                           * spawn-point scan at 0x13384 stands down while it is set */

/* The per-wave difficulty block, loaded as ONE LONGWORD out of A_wave_layout_table. */
#define A_wave_layout_mask   0x10d54u  /* .b — bit n set = platform n is present this wave */
#define A_wave_type1_count   0x10d55u  /* .b — riders (or eggs) of each type to place */
#define A_wave_type2_count   0x10d56u  /* .b */
#define A_wave_type3_count   0x10d57u  /* .b */

/* The three rider speeds this block goes on to set are addrs.h's — the egg hatch and the enemy
 * driver steer by them. */
/* .w — really the PAIR of byte tallies at 0x10d5e/0x10d5f counting how many enemies are hunting
 * player 1 and player 2 (update_objects compares each against the speed above and bumps it at
 * 0x122b2 / 0x122cc). A new wave clears both with one `clr.w`. */
#define A_hunter_counts  0x10d5eu

#define A_spawn_interval  0x10dfau  /* .w — the pterodactyl scheduler's reload... */
#define A_spawn_timer     0x10dfcu  /* .w — ...and its countdown */

#define A_wave_layout_table    0x11b58u   /* one {mask, count1, count2, count3} longword per wave */

/* The 64 bytes of padding between wave_manager's last `rts` (0x17e79) and the large font at
 * 0x17eba, used as scratch: the {platform, x} pair of every egg placed so far, so the placement can
 * refuse to drop two eggs on top of each other. 16 pairs of room for at most 12 eggs. */
#define A_egg_spread_scratch  0x17e7au

/* ---- the banner strings ---------------------------------------------------------------------- */
#define STR_PREPARE_TO_JOUST  0x18429u
#define STR_BUZZARD_BAIT      0x1843cu
#define STR_WAVE              0x1844cu
#define STR_SURVIVAL_WAVE     0x18453u
#define STR_TEAM_WAVE         0x18463u
#define STR_TEAM_PLAY_BONUS   0x1846fu
#define STR_GLADIATOR_WAVE    0x1848du
#define STR_BOUNTY_OFFER      0x1849eu  /* "3000 POINT BOUNTY FOR" */
#define STR_DISMOUNT_FIRST    0x184b6u  /* "DISMOUNTING FIRST PLAYER" */
#define STR_EGG_WAVE          0x184d1u
#define STR_PTERODACTYL_WAVE  0x184dcu
#define STR_BEWARE_PTERO      0x184efu
#define STR_CO_OPERATION      0x18517u  /* "PLAYER CO-OPERATION - COLLECT 3000 BONUS" */
#define STR_PLAYER_CONFLICT   0x18542u
#define STR_SURVIVAL_BONUS    0x18567u  /* "COLLECT 3000 SURVIVAL POINTS" */
#define STR_NO_BONUS          0x18586u
#define STR_NO_BOUNTY         0x18599u
#define STR_BOUNTY_COLLECTED  0x185adu

/* ---- game_phase, which doubles as a message GENERATION tag ----------------------------------- */
/* The dispatcher holds the countdown while ANY message slot's MSG_KIND equals the current
 * game_phase, so the two constants below are read both as a phase and as a kind. */
#define WAVE_PHASE_PLAYING   0u  /* the wave is running */
#define WAVE_PHASE_ANNOUNCE  1u  /* the next wave's banners are up */
#define WAVE_PHASE_BONUS     2u  /* the finished wave's bonus banners are up */

/* ---- banner geometry ------------------------------------------------------------------------- */
#define BUZZARD_BAIT_CUE  0x4bu  /* "BUZZARD BAIT!" is posted when the PREPARE banner's timer has
                                  * counted down to exactly this, and inherits it, so the two clear
                                  * together */
/* From wave 9 on the drawn number needs two digits, so the label slides left and the number right. */
#define WAVE_NUM_FIRST_2DIGIT     9  /* `cmpi.b #9 ; blt` — a SIGNED byte compare */
#define WAVE_LABEL_SHIFT_1DIGIT   0xbu
#define WAVE_LABEL_SHIFT_2DIGIT   0x8u
#define WAVE_NUMBER_SHIFT_1DIGIT  0x8u
#define WAVE_NUMBER_SHIFT_2DIGIT  0xeu

/* ---- what a finished wave pays ---------------------------------------------------------------- */
#define SPECIAL_WAVE_LEAD    5u  /* game_phase ticks between arming a special-wave latch and its banner */
#define WAVE_BONUS_THOUSANDS 3u  /* `addq.b #3` on OBJ_SCORE_LIFE_DIGIT, i.e. 3000 points */

/* ---- starting the next wave ------------------------------------------------------------------- */
#define WAVE_NUM_WRAP     0x33u  /* the count never passes this... */
#define WAVE_NUM_WRAP_TO  0x29u  /* ...it drops back here and the last ten waves repeat */
#define DIGIT_PAST_9      0x3au  /* ':' — what '9' + 1 is, and the carry's cue */
#define TENS_PAST_BLANK   0x21u  /* '!' — what the blank tens digit becomes on the first carry... */
#define TENS_FIRST        0x31u  /* ...and the '1' it is forced to instead */

#define FLOOR_LAST_WAVE       3  /* `cmpi.b #3 ; bgt` — SIGNED; waves 0-3 are owed more lava */
#define FLOOR_ROWS_PER_WAVE   5u
#define FLAP_DELAY_BASE       5u /* `move.b #5 ; sub.b d0` where d0 = (wave_num >> 4) + 1 */
#define RIDER_SPEED_MAX       4  /* `cmpi.w #4 ; ble` — SIGNED */

/* The ground burn is armed on wave 3 and re-armed on wave 4, each with its own start geometry.
 * Both flames sit on framebuffer row GROUND_BURN_ROW; the offsets below are that row's start plus a
 * whole number of cells, and test_wave.py pins each against that derivation. */
#define GROUND_BURN_FIRST_WAVE  3  /* `cmpi.b #3 ; blt` — SIGNED */
#define GROUND_BURN_LAST_WAVE   4  /* `cmpi.b #4 ; bgt` */
#define GROUND_BURN_ROW  185u
/* Wave 3: the flames start at the two ends of the full-width ground — the left one a whole cell OFF
 * the left edge and the right one in the last cell, which is why each is clipped to a single cell
 * (SPR_CELL_SELECT 1 draws the trailing cell alone, -1 the leading one). */
#define GROUND_BURN_WAVE3_LEFT_DST     0x7398u  /* row 185, cell -1 */
#define GROUND_BURN_WAVE3_RIGHT_DST    0x7438u  /* row 185, cell 19 */
#define GROUND_BURN_WAVE3_LEFT_SHIFT   0xau
#define GROUND_BURN_WAVE3_RIGHT_SHIFT  0xcu
#define GROUND_BURN_WAVE3_LEFT_CELLS   0x1u     /* trailing cell only — the leading one is off-screen */
#define GROUND_BURN_WAVE3_RIGHT_CELLS  0xffffu  /* leading cell only, likewise */
/* Wave 4 starts with three cells of ground already gone at each end, so both flames are fully on
 * screen and neither needs clipping. */
#define GROUND_BURN_WAVE4_LEFT_DST     0x73b0u  /* row 185, cell 2 */
#define GROUND_BURN_WAVE4_RIGHT_DST    0x7428u  /* row 185, cell 17 */
#define GROUND_BURN_WAVE4_LEFT_SHIFT   0x0u
#define GROUND_BURN_WAVE4_RIGHT_SHIFT  0xau
#define GROUND_BURN_WAVE4_CELLS        0x0u     /* both cells drawn */
/* The left flame starts on the first animation frame and the right one two frames in, so the pair
 * never burns in step. Both are offsets into the same four-frame set world.h lays out. */
#define GROUND_BURN_RIGHT_FRAME_INDEX  2u

/* ---- placing this wave's eggs ------------------------------------------------------------------ */
/* `andi.w #$38` on the random word: a whole platform_table record index, 0..PLATFORM_COUNT-1. */
#define EGG_PLATFORM_SELECT_MASK  0x38u
#define EGG_REST_ABOVE_PLATFORM   0xcu  /* the egg sits this far below the platform's top edge */
#define EGG_SPREAD_GAP            0x8u  /* two eggs on one platform must be more than this apart... */
#define EGG_SPREAD_GAP_WRAPPED    0xfff8u  /* ...measured the other way round as an UNSIGNED word */
#define EGG_SPREAD_RECORD         0x4u  /* one {platform, x} scratch pair */
#define EGG_REST_ROWS             0x7u  /* OBJ_EGG_ROWS for a settled egg */
#define EGG_REST_ROLL_TIMER       0x4u
#define EGG_REST_FALL_TIMER       0x6u
#define EGG_HATCH_TIMER_BASE      0x91u /* `move.b #$91 ; sub.b wave_num` — the first egg's wait... */
#define EGG_HATCH_TIMER_STEP      0x7u  /* ...and each later one waits this much longer */
#define RNG_EGG_ADVANCE           0xc4u /* rng_ptr is nudged this far before every re-roll */

/* ---- arming the pterodactyls and spawning the riders -------------------------------------------- */
#define SPAWN_INTERVAL_BASE        0x640u  /* the scheduler's reload at wave 0... */
#define SPAWN_INTERVAL_WAVE_SHIFT  4u      /* ...less `wave_num << 4` per wave */
#define PTERO_FIRST_ARMED_WAVE     0x10u   /* `cmpi.b #$f ; bls` — UNSIGNED, so this is the first */
#define PTERO_IMMEDIATE_TIMER      0x30u   /* from that wave on the first one is nearly instant */

/* --- wave.c ------------------------------------------------------------------------------------ */
void wave_manager(uint8_t *image);

#endif /* JOUST_WAVE_H */
