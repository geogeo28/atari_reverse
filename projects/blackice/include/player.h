/*
 * player.h - the player body: a circle that slides along walls.
 *
 * Collision is Wolfenstein-3D style and axis-separated (DESIGN 4): the move is
 * attempted on x, then on y, so a move blocked on one axis still delivers the
 * other component and the player slides along the wall instead of sticking.
 */
#ifndef BLACKICE_PLAYER_H
#define BLACKICE_PLAYER_H

#include <stdint.h>
#include "fixed.h"
#include "game_consts.h"
#include "map.h"

/* Input is a bitmask so a replay script is one word per tick. */
#define INPUT_FORWARD       0x0001
#define INPUT_BACK          0x0002
#define INPUT_TURN_LEFT     0x0004
#define INPUT_TURN_RIGHT    0x0008
#define INPUT_STRAFE_LEFT   0x0010
#define INPUT_STRAFE_RIGHT  0x0020
/* 0x0040 is retired, not reused: DESIGN 6 has no use key, doors open on a
 * bump.  Replay scripts encode the raw mask, so the bit value stays reserved
 * rather than being handed to the next control that comes along. */
#define INPUT_RESERVED_0040 0x0040
#define INPUT_FIRE          0x0080
#define INPUT_THROTTLE_NEXT 0x0100

typedef struct {
    fix88_t x;
    fix88_t y;
    angle_t angle;
} Player;

/*
 * Move and turn the player for one tick.  `speed_scale` is the throttle's 8.8
 * speed multiplier.  Cells the player is pushed against are reported through
 * `bumped_cell` (-1 when nothing was hit) so the caller can open doors on
 * contact without the collider knowing what a door is.
 */
void player_step(Player *player, uint16_t input, uint16_t speed_scale,
                 const MapGrid *grid, const MapBlocking *blocking, int32_t *bumped_cell);

/* Does a circle of PLAYER_RADIUS centred at (x, y) overlap a blocking cell?
 * Returns the blocking cell index, or -1. */
int32_t player_blocking_cell(fix88_t x, fix88_t y, const MapGrid *grid,
                             const MapBlocking *blocking);

#endif /* BLACKICE_PLAYER_H */
