/* objects.h — update_objects @ 0x12014: the per-frame enemy driver.
 *
 * Addresses are Ghidra addresses (image offset + the 0x10000 load base) and mirror `var` lines in
 * ../../names.txt. Only what this routine alone touches is declared here; everything it shares is
 * taken from the header that already owns it — addrs.h (A_object_table, the three rider speeds,
 * A_enemy_objects, the two chase counts), joust.h (the object record, its flag bits and the rider
 * types), draw.h (A_player2, draw_object_mask), object.h (A_object_table_END, erase_egg_sprite),
 * egg.h (OBJ_EGG_Y, OBJ_HATCH_MOUNT) and world.h (OBJ_FLAG_REMOVED).
 */
#ifndef JOUST_OBJECTS_H
#define JOUST_OBJECTS_H

#include <stdint.h>

#include "addrs.h"
#include "joust.h"

/* ---- globals ---- */
/* .b — which players are on the board this frame, rebuilt at the top of every call. Bit 0 is
 * player 1 and bit 1 player 2; a slot counts only while it is live, not dead and not waiting to
 * respawn, so the AI stops steering at a player who is mid-death. */
#define A_active_players  0x10d09u
/* The two chase counts, A_chasers_p1 / A_chasers_p2, are addrs.h's — the wave director clears them
 * at the start of every wave. */

/* ---- object-record fields this layer owns ---- */
#define OBJ_CHASE_TARGET  0x48u  /* .b, SIGNED — 0 none, 1/2 closing on that player, -1/-2 attacking it */

/* ---- active_players ---- */
#define ACTIVE_PLAYER1  1u
#define ACTIVE_PLAYER2  2u
#define ACTIVE_BOTH     3u   /* `cmpi.b #3` — both on the board, so the chase counts decide */

/* ---- what joust.h's OBJ_TURN_TIMER has to reach for this routine to flip the facing ---- */
#define TURN_TIMER_LIMIT  3u  /* `cmpi.b #3` + `bcs` — UNSIGNED, so 0x80 is over the limit */

/* ---- geometry ----
 * The playfield is one screen wide, so a negative x gap is brought back into range by adding it.
 * The SAME quantity is spelled three more times in this reconstruction — world.h's TROLL_X_WRAP,
 * render.h's RIDER_X_WRAP (already aliased to that one) and src/egg.c's EGG_X_WRAP — because no
 * shared header owns it yet. Derived from the screen geometry the way TROLL_X_WRAP is, rather than
 * written as a fourth 0x140, so what would have to drift is a derivation and not a literal. */
#define PLAYFIELD_WIDTH       ((int)(SCREEN_ROW_BYTES / CELL_BYTES * CELL_PIXELS))
#define PLAYFIELD_HALF_WIDTH  ((uint16_t)(PLAYFIELD_WIDTH / 2))  /* where "right" becomes "left" */

/* ---- objects.c ---- */
void update_objects(uint8_t *image, uint16_t flags_in, uint16_t probe_in);

#endif /* JOUST_OBJECTS_H */
