/* collide.h — collision_check @ 0x13842: the per-frame collision resolver.
 *
 * Addresses are Ghidra addresses (image offset + the 0x10000 load base) and mirror `var` lines in
 * ../../names.txt. Only what this routine alone touches is declared here; everything it shares is
 * taken from the header that already owns it — addrs.h (A_object_table, A_screen_base, the
 * gladiator bookkeeping), joust.h (the object record and its flag bits, including the
 * OBJ_FLAG_PLATFORM_BUMP this routine alone sets and the OBJ_FLAG_TYPE_LO/HI it prices a kill by),
 * object.h (the hit boxes and the two stagers that fill them, the platform sprites, the whole
 * pterodactyl table and record, test_overlap / erase_egg_sprite),
 * egg.h (the egg record's fields and A_egg_sprite_still),
 * world.h (OBJ_FLAG_PLAYER / OBJ_FLAG_REMOVED,
 * OBJ_EGG_CHAIN,
 * OBJ_SCORE_PENDING, A_wave_num, the two death sprites), score.h (the message record,
 * find_free_message, the score_update family, A_players_alive) and sound.h (play_sound).
 */
#ifndef JOUST_COLLIDE_H
#define JOUST_COLLIDE_H

#include <stdint.h>

#include "addrs.h"
#include "joust.h"

/* ---- globals ---- */
#define A_egg_bonus_table           0x119b4u

/* ---- egg_bonus_table record: the consecutive-egg chain, 250 / 500 / 750 / 1000 ---- */
#define BONUS_STRING     0x0u  /* .l — the text drawn over the egg that was collected */
#define BONUS_THOUSANDS  0x4u  /* .b, .b, .b — added into the collector's three score digits */
#define BONUS_HUNDREDS   0x5u
#define BONUS_TENS       0x6u
#define BONUS_RECORD     0x8u

/* ---- egg state ---- */
#define EGG_STATE_THROWN  0x23u  /* just dismounted: still worth the extra 500 if caught in flight */

/* ---- collide.c ---- */
void collision_check(uint8_t *image);

#endif /* JOUST_COLLIDE_H */
