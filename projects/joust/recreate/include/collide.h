/* collide.h — collision_check @ 0x13842: the per-frame collision resolver.
 *
 * Addresses are Ghidra addresses (image offset + the 0x10000 load base) and mirror `var` lines in
 * ../../names.txt. Only what this routine alone touches is declared here; everything it shares is
 * taken from the header that already owns it — addrs.h (A_object_table, A_screen_base, the
 * gladiator bookkeeping), joust.h (the object record and its flag bits, including the
 * OBJ_FLAG_PLATFORM_BUMP this routine alone sets and the OBJ_FLAG_TYPE_LO/HI it prices a kill by),
 * object.h (the hit boxes, the platform sprites, the pterodactyl table and record, test_overlap /
 * erase_egg_sprite), egg.h (the egg record's fields and A_egg_sprite_still),
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

/* ---- pterodactyl record: the fields object.h does not already name ---- */
#define PT_DST        0x2u   /* .l — screen address, before screen_base and PT_DST_OFF are added */
#define PT_SRC        0x6u   /* .l */
/* .b, .b — the LOW BYTES of the shift and rows WORDS at +0xa and +0x18 (update_pterodactyl clears
 * both as words at 0x14b5e / 0x14b66 and reads both as bytes at 0x14c0a / 0x14c10, exactly as the
 * collision box staging here does). The same width split addrs.h documents for draw_shift. */
#define PT_SHIFT      0xbu
#define PT_ROWS       0x19u
#define PT_DST_OFF    0x16u  /* .w — SIGN-extended, added to the screen address */
/* .b — the second of the pair names.txt calls the direction/dwell timers (update_pterodactyl counts
 * it down with `subq.b` at 0x14ec2 and reloads it to 3). The death frame arms it and
 * PT_SWOOP_TIMER together. */
#define PT_DWELL_TIMER 0x1fu

#define PT_FLAG_JUST_SPAWNED  (1u << 0)   /* not solid yet — it is still fading in */
#define PT_FLAG_DYING         (1u << 5)   /* already lanced this frame or an earlier one */

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
