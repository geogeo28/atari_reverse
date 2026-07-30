/* score.h — the HUD layer: the lives row, the timed on-screen messages, and the high-score
 * name-entry display. Addresses are Ghidra addresses (image offset + the 0x10000 load base) and
 * mirror `var` lines in ../../names.txt.
 *
 * Only what this layer alone touches is spelled out here. The text engine it paints through
 * (A_text_*, TEXT_FLAG_*) belongs to draw.h, the message table's base/end/stride to object.h, and
 * the object record to joust.h — this layer is the second reader of all three, so those constants
 * are INCLUDED rather than restated (a second copy would drift silently; see the pin in
 * test/test_constants.py). When the layering is next tidied, the text-engine globals and the
 * message record are the two groups that have earned a move into addrs.h.
 */
#ifndef JOUST_SCORE_H
#define JOUST_SCORE_H

#include <stdint.h>

#include "addrs.h"
#include "draw.h"     /* the text engine this layer drives, and draw_string itself */
#include "joust.h"
#include "object.h"   /* the message table: A_message_table(_END), MSG_KIND, MSG_SCREEN_PTR, ... */

/* --- globals ---------------------------------------------------------------------------------- */
#define A_players_alive     0x10cf2u  /* .b — 0 once neither player has a turn left */
#define A_game_over_flag    0x10d12u  /* .b — set when the "THY GAME IS OVER" message expires */
#define A_hiscore_name      0x18396u  /* the name the entry screen types into (HIGH.SCO's record) */

/* THE HIGH-SCORE SCREEN BORROWS THREE SPRITE-DRAW GLOBALS. Nothing is being drawn while a name is
 * being entered, so the entry code reuses that scratch rather than spending three more words on
 * state of its own. Aliased rather than redefined so there is still one address per name. */
#define A_hiscore_cursor    A_draw_shift    /* .w — the column being typed, 0..15 */
#define A_hiscore_letter    A_draw_dst_off  /* .b — the character under the cursor, in the HIGH byte
                                             * of draw_dst_off. draw_string is handed THIS ADDRESS
                                             * as its string, so the next byte up (that word's low
                                             * half) is the terminator. */
#define A_hiscore_flash     A_draw_x        /* .w — the pen-10 colour-cycle counter */

/* --- object record: the HUD fields (the rest of the record is in joust.h) --------------------- */
#define OBJ_SCORE_PTR       0x36u   /* .l — screen address the player's score row is painted at */
#define OBJ_SCORE_SHIFT     0x3au   /* .w — pixels into that cell; draw_lives reads its LOW BYTE */
#define OBJ_SCORE_SHIFT_LO  (OBJ_SCORE_SHIFT + 1u)
#define OBJ_LIVES           0x4cu   /* .b — signed; five positions are drawn whatever it holds */

/* --- message_table record: the fields object.h does not already name -------------------------- */
#define MSG_TIMER           0x1u   /* .b — frames left; counted down with subq.b (0 wraps to 255) */
#define MSG_COLOR           0x2u   /* .b */
#define MSG_SHIFT           0x3u   /* .b */
#define MSG_STRING          0x8u   /* .l — the text; MSG_SCREEN_PTR (+4) is where it lands */
#define MSG_KIND_PERSISTENT 0x3u   /* the one kind that is NOT cut short when the players are out */

/* --- the strings this layer draws ------------------------------------------------------------- */
#define STR_LIFE_BLANK      0x1861bu  /* " " — an unearned life position */
#define STR_LIFE_P1         0x1861du  /* the '$'-over-'%' life glyph, in player 1's colour */
#define STR_LIFE_P2         0x18629u  /* ...and in player 2's */
#define STR_GAME_OVER       0x185c5u  /* "THY GAME IS OVER" — its expiry ends the game */

/* --- score.c ---------------------------------------------------------------------------------- */
uint32_t find_free_message(const uint8_t *image);
void draw_messages(uint8_t *image);
void draw_lives(uint8_t *image, uint32_t object);
void draw_lives_p1(uint8_t *image);
void draw_lives_p2(uint8_t *image);
uint16_t flash_hiscore_color(uint8_t *image);
void draw_hiscore_cursor(uint8_t *image);
void draw_hiscore_entry(uint8_t *image);

#endif /* JOUST_SCORE_H */
