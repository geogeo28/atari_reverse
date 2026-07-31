/* addrs.h — the Joust globals that MORE THAN ONE subsystem touches, by Ghidra address.
 *
 * Every address here is a Ghidra address (image offset + the 0x10000 load base fixed by
 * project.toml / PrgLoader) and mirrors a `var` line in ../../names.txt, which stays the source
 * of truth for the name. A_chasers_p1 / A_chasers_p2 are the one exception, and a documented one:
 * names.txt names their address as the single word `hunter_counts`, and the C needs a name per
 * byte — see the comment on the pair.
 *
 * A global moves here the moment a second subsystem reads it; one that only its own layer touches
 * stays in that layer's header (draw.h, object.h, ...). Two headers spelling out the same address
 * is the arrangement to avoid: no translation unit includes both, so nothing would diagnose the
 * copies drifting apart — nor two names for one address, which
 * test_constants.py::test_no_value_has_two_spellings is what catches.
 */
#ifndef JOUST_ADDRS_H
#define JOUST_ADDRS_H

#define IMAGE_LOAD_BASE 0x10000u   /* where the program image starts; some code holds addresses
                                    * into itself as relocated constants (see rng.c) */

#define A_screen_base       0x10ddeu  /* .l — base of the screen every draw routine addresses from */
#define A_rng_ptr           0x10dfeu  /* .l — the pseudo-random cursor walking the program image */
#define A_playfield_bottom  0x10d60u  /* .l — screen address of the lava surface; a sprite reaching it dies */
#define A_object_table      0x10f36u  /* player 1's object slot, and the object table's base */

/* The sprite-draw scratch: a caller stages one sprite here and a blitter reads it back. The drawing
 * layer both writes and consumes it; the object layer stages it for the blitters it hands over to. */
#define A_draw_dst          0x10de8u  /* .l */
#define A_draw_src          0x10df0u  /* .l */
/* .w — the scratch y. Its partner A_draw_x is still object.h's, which is drift: this one moved
 * here when the high-score entry became a second reader (the egg layer is the other), and moving
 * the pair together would take object.h and its battery with it. */
#define A_draw_y            0x10deeu

/* WIDTH CLASH, FAITHFULLY REPRODUCED. draw_shift and draw_rows are read as BYTES by the rider
 * blitters (draw_object_data) and by the object layer, and as WORDS by the pterodactyl one
 * (blit_sprite_planes) — and a byte read at the word's address takes its HIGH half, so the two
 * readings do not even agree on which half carries the value. The writers split the same way
 * (0x131b4 stores a byte, 0x15006 a word), so each subsystem is self-consistent and the clash only
 * shows if they interleave. Each reconstruction reads exactly the width its own instruction reads. */
#define A_draw_shift        0x10df4u  /* pixel shift within the cell; .b to those readers, .w to the pterodactyl */
#define A_draw_rows         0x10df6u  /* sprite height;               .b to those readers, .w to the pterodactyl */

/* The two-player "gladiator" bookkeeping. Once gladiator_wave_countdown has reached 0, the FIRST
 * dismount of a player-versus-player joust in the wave is worth 3000 instead of 500, and
 * first_dismount_owner records which player took it so it can only happen once. The wave director
 * arms and pays all three; the collision resolver is what sets and reads them during the wave. */
#define A_gladiator_wave_countdown  0x10d05u  /* .b — non-zero disarms the bonus; `tst.b` only */
#define A_player_conflict_flag      0x10d06u  /* .b — the players fought each other this wave, so the
                                               * co-operation bonus is forfeit; set by every player
                                               * death and every duel */
#define A_first_dismount_owner      0x10d07u  /* .b — 0 nobody yet, 1 player 1 took it, above that
                                               * player 2 (a SIGNED test) */

/* .b — the enemy-side respawn interlock: only one enemy is ever growing out of a pad at a time.
 * Taken when a rider whose masked type is <= 3 claims a spawn point (0x13422) and handed back when
 * a NON-PLAYER reaches full height (0x134fe), with the wave director clearing it again at 0x1720e.
 * A PLAYER passes neither test — its OBJ_FLAG_PLAYER lands inside render.h's three-bit
 * OBJ_RIDER_TYPE_MASK, so its type reads 4 or 6 — and it does not consult the byte either. It is
 * named for the lock-out it imposes rather than for a spawn being "in progress", because the only
 * thing that ever reads it is the enemy's spawn-point scan standing down. */
#define A_respawn_lock  0x10d13u

#define A_spawn_point_cursor  0x10d14u  /* .l — the round-robin cursor into spawn_points: where the
                                         * render pass resumes its search, and what a new wave resets */

/* This wave's rider speed by type, three CONTIGUOUS words. The wave director sets all three; the
 * egg hatch steers by type 1, and the enemy driver by all three (type 3's LOW BYTE also caps how
 * many enemies may chase one player at a time). */
#define A_speed_type1  0x10d58u  /* .w */
#define A_speed_type2  0x10d5au  /* .w */
#define A_speed_type3  0x10d5cu  /* .w */

/* .b, .b — how many type-2 riders currently hold a chase slot on each player. A rider claims one
 * before homing in and gives it back when it loses the target, and speed_type3's low byte is the
 * per-player cap. The pair is ADJACENT, so both the enemy driver's "no players left" reset and the
 * wave director's per-wave reset clear the two with a single `clr.w $d5e` word store: one field to
 * those writers and two to everyone else. ../../names.txt names the WORD `hunter_counts`; the two
 * bytes need a name each, so they carry the enemy driver's own vocabulary (OBJ_CHASE_TARGET,
 * chase_side) rather than a third spelling of the pair. */
#define A_chasers_p1  0x10d5eu
#define A_chasers_p2  0x10d5fu

#define A_flap_delay  0x10ddcu  /* .b — frames between an AI rider's wing beats, set once per wave.
                                 * The render pass caps a troll-held rider's step timer to it, so a
                                 * grabbed rider flaps no faster than this either. */

#define A_enemy_objects  0x10fd2u  /* object_table slot 2: the first of the 12 non-player slots, and
                                    * so the `cmpa.l` bound that separates a player from an enemy */

#endif /* JOUST_ADDRS_H */
