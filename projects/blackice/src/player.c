/*
 * player.c - the player body: turning, axis-separated movement, wall sliding.
 *
 * 68000 cost: four `muls` for the direction vectors and up to eight bitmap
 * probes, about 500 cycles a tick.  It runs 25 times a second, so it is
 * nowhere near the frame budget and is written for clarity.
 */
#include "player.h"

/* The body is squared off into an axis-aligned box of this half-extent, which
 * is what makes the "test x, then y" slide exact rather than approximate. */
#define BODY_HALF_EXTENT PLAYER_RADIUS

static int32_t cell_at(fix88_t x, fix88_t y, const MapGrid *grid, const MapBlocking *blocking)
{
    int16_t cell_x = (int16_t)(x >> CELL_SHIFT);
    int16_t cell_y = (int16_t)(y >> CELL_SHIFT);
    uint16_t index;

    if (cell_x < 0 || cell_y < 0 || cell_x >= grid->width || cell_y >= grid->height) {
        return -1;
    }
    index = map_cell_index(grid, cell_x, cell_y);
    return map_cell_blocks(blocking, index) ? (int32_t)index : -1;
}

int32_t player_blocking_cell(fix88_t x, fix88_t y, const MapGrid *grid,
                             const MapBlocking *blocking)
{
    /* BODY_HALF_EXTENT is under half a cell, so the four corners of the body
     * box cover every cell it can possibly touch. */
    static const int8_t CORNER_SIGN[4][2] = { { -1, -1 }, { 1, -1 }, { -1, 1 }, { 1, 1 } };
    int i;

    for (i = 0; i < 4; ++i) {
        fix88_t probe_x = (fix88_t)(x + CORNER_SIGN[i][0] * BODY_HALF_EXTENT);
        fix88_t probe_y = (fix88_t)(y + CORNER_SIGN[i][1] * BODY_HALF_EXTENT);
        int32_t cell = cell_at(probe_x, probe_y, grid, blocking);

        if (cell >= 0) {
            return cell;
        }
    }
    return -1;
}

/* Scale a per-tick speed by the throttle's 8.8 multiplier. */
static int16_t scaled_speed(int16_t base, uint16_t speed_scale)
{
    return (int16_t)(mul16(base, (int16_t)speed_scale) >> 8);
}

void player_step(Player *player, uint16_t input, uint16_t speed_scale,
                 const MapGrid *grid, const MapBlocking *blocking, int32_t *bumped_cell)
{
    int16_t forward = 0;
    int16_t strafe = 0;
    int16_t cosine;
    int16_t sine;
    int32_t move_x;
    int32_t move_y;
    fix88_t target;
    int32_t blocked;

    *bumped_cell = -1;

    if (input & INPUT_TURN_LEFT) {
        player->angle = (angle_t)(player->angle - PLAYER_TURN_SPEED);
    }
    if (input & INPUT_TURN_RIGHT) {
        player->angle = (angle_t)(player->angle + PLAYER_TURN_SPEED);
    }

    if (input & INPUT_FORWARD) {
        forward += scaled_speed(PLAYER_MOVE_SPEED, speed_scale);
    }
    if (input & INPUT_BACK) {
        forward -= scaled_speed(PLAYER_BACK_SPEED, speed_scale);
    }
    if (input & INPUT_STRAFE_RIGHT) {
        strafe += scaled_speed(PLAYER_STRAFE_SPEED, speed_scale);
    }
    if (input & INPUT_STRAFE_LEFT) {
        strafe -= scaled_speed(PLAYER_STRAFE_SPEED, speed_scale);
    }
    if (forward == 0 && strafe == 0) {
        return;
    }

    /* World x runs east and y runs south, so "right" is the view direction
     * turned a quarter turn: (-sin, cos). */
    cosine = angle_cos(player->angle);
    sine = angle_sin(player->angle);
    move_x = (mul16(cosine, forward) - mul16(sine, strafe)) >> TRIG_SHIFT;
    move_y = (mul16(sine, forward) + mul16(cosine, strafe)) >> TRIG_SHIFT;

    /* Axis-separated: a move blocked on one axis still delivers the other, and
     * that is exactly what sliding along a wall is. */
    target = (fix88_t)(player->x + move_x);
    blocked = player_blocking_cell(target, player->y, grid, blocking);
    if (blocked < 0) {
        player->x = target;
    } else {
        *bumped_cell = blocked;
    }

    target = (fix88_t)(player->y + move_y);
    blocked = player_blocking_cell(player->x, target, grid, blocking);
    if (blocked < 0) {
        player->y = target;
    } else if (*bumped_cell < 0) {
        *bumped_cell = blocked;
    }
}

int32_t player_use_target(const Player *player, const MapGrid *grid)
{
    int32_t reach_x = mul16(angle_cos(player->angle), PLAYER_USE_REACH) >> TRIG_SHIFT;
    int32_t reach_y = mul16(angle_sin(player->angle), PLAYER_USE_REACH) >> TRIG_SHIFT;
    int16_t cell_x = (int16_t)((player->x + reach_x) >> CELL_SHIFT);
    int16_t cell_y = (int16_t)((player->y + reach_y) >> CELL_SHIFT);

    if (cell_x < 0 || cell_y < 0 || cell_x >= grid->width || cell_y >= grid->height) {
        return -1;
    }
    return map_cell_index(grid, cell_x, cell_y);
}
