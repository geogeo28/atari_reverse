/*
 * ai.h - the one navigation field, the grid line walk, and the sight rules.
 *
 * ---------------------------------------------------------------------------
 * The distance field (DESIGN 8.1)
 * ---------------------------------------------------------------------------
 * There is no straight-line chase rule in this game.  A breadth-first flood
 * from the player's cell over the walkable grid gives every cell its distance
 * in steps, and an enemy at a cell centre simply picks the neighbour with the
 * lowest value and commits to it.  Because the field is a true BFS, that
 * neighbour always exists and always reduces the distance, so the movement
 * cannot jam - which is the whole reason the field is here and not a chase
 * vector.  A field up to NAV_REBUILD_TICKS old at worst makes an enemy
 * overshoot by a cell.
 *
 * ---------------------------------------------------------------------------
 * The grid line walk
 * ---------------------------------------------------------------------------
 * Line of sight and the Buster's hitscan are the same walk: step from one point
 * to another cell by cell and look at what is in each cell.  It is the
 * raycaster's DDA with the ray angle replaced by an endpoint, and it is written
 * once, here, in integers - the choice of which boundary comes next is a
 * comparison of two cross products, never a divide and never a float.
 */
#ifndef BLACKICE_AI_H
#define BLACKICE_AI_H

#include <stdint.h>
#include "fixed.h"
#include "game_consts.h"
#include "game_rules.h"
#include "map.h"

struct GameState;   /* game.h owns the definition; declared to break the cycle */

/* ---- the BFS distance field --------------------------------------------- */

/*
 * The field is read a byte at a time and cleared a longword at a time: the
 * clear is 4,096 bytes of NAV_UNREACHABLE at 3.125 Hz, which byte-wise is
 * 114,688 cycles on the 68000 and longword-wise is a thirty-second of that.
 * A union rather than a cast, so the array is 4-byte aligned by construction -
 * a misaligned `move.l` is an address error on a 68000, not a slow store.
 */
typedef union {
    uint8_t  byte[MAP_MAX_CELLS];       /* NAV_UNREACHABLE where the flood did not reach */
    uint32_t word[MAP_MAX_CELLS / 4];
} NavSteps;

typedef struct {
    NavSteps steps;
    uint16_t queue[NAV_QUEUE_MAX];      /* the flood's frontier; see NAV_QUEUE_MAX */
    uint16_t origin_cell;               /* the cell the flood started from */
    /* Cells the last flood dequeued.  It is what the rebuild's cost is
     * proportional to, so the cycle budget is checkable from a run instead of
     * only from the emitted loop: it can never exceed the level's walkable
     * cell count, because a cell is enqueued exactly when it is first reached. */
    uint16_t visited;
    uint32_t next_rebuild_tick;         /* GameState.tick's width, so a long run
                                         * cannot wrap the comparison */
} NavField;

/* Flood from `origin_cell` over cells the blocking bitmap says are open.  Only
 * the width * height cells the grid actually has are cleared and filled; the
 * rest of the array is never read, because no cell index can name it. */
void nav_rebuild(NavField *field, const MapGrid *grid, const MapBlocking *blocking,
                 uint16_t origin_cell);

static inline uint8_t nav_steps(const NavField *field, uint16_t cell)
{
    return field->steps.byte[cell];
}

/* ---- the grid line walk -------------------------------------------------- */

/*
 * A cursor stepping from cell to cell along a line.  `err_x` and `err_y` are
 * the crossing parameters of the next vertical and horizontal grid line, both
 * scaled by |dx|*|dy| so the comparison between them needs no divide.
 *
 * `cell` is the same position as (cell_x, cell_y) as a grid index, carried
 * alongside them and advanced by a stride: line of sight and the Buster's
 * hitscan both look the cell up in a byte map every step, and recomputing
 * `y * width` per step is a `muls.w` in the innermost loop of the AI.
 *
 * `steps_left` is the EXACT number of grid lines between the two endpoints, so
 * a walk stops when it arrives instead of running to a safety limit: an enemy
 * sighting eight cells away costs eight steps and not GRID_WALK_MAX_STEPS.
 */
typedef struct {
    int16_t  cell_x;
    int16_t  cell_y;
    uint16_t cell;          /* map_cell_index(cell_x, cell_y), kept in step */
    int16_t  step_x;        /* +1, -1 or 0 */
    int16_t  step_y;
    int16_t  stride_x;      /* cell delta of one x step: step_x */
    int16_t  stride_y;      /* cell delta of one y step: step_y * width */
    uint16_t steps_left;    /* grid lines still to cross before the target cell */
    int32_t  err_x;
    int32_t  err_y;
    int32_t  err_step_x;    /* added to err_x on each crossing of a vertical line */
    int32_t  err_step_y;
} GridWalk;

void grid_walk_init(GridWalk *walk, const MapGrid *grid,
                    fix88_t from_x, fix88_t from_y, fix88_t to_x, fix88_t to_y);
void grid_walk_step(GridWalk *walk);

/* ---- the neighbour offsets ----------------------------------------------- */

/*
 * The cell delta of each of the eight neighbours on a grid `width` cells wide,
 * in the neighbour order below.  Written once at level load into
 * GameState.neighbour_offset and read from there: `NEIGHBOUR_DY[n] * width`
 * inside a loop is a runtime multiply per neighbour, and the flood, the mover,
 * the facing and the alcove test between them ask for it thousands of times a
 * second.
 */
void ai_neighbour_offsets(int16_t width, int16_t *out);

/* ---- the neighbour tables ------------------------------------------------ */

/*
 * Neighbour n of a cell, as a cell delta.  The orthogonals are 0..3 (north,
 * east, south, west) and the diagonals 4..7.  Exposed as accessors rather than
 * as arrays so there is one definition and a test can walk it.
 */
int8_t  ai_neighbour_dx(int n);
int8_t  ai_neighbour_dy(int n);
/* The engine angle a body faces when it looks along orthogonal n. */
angle_t ai_ortho_facing(int n);

/* ---- sight -------------------------------------------------------------- */

/*
 * DESIGN 8's uniform sight rule, in its three separable parts.  They are
 * exposed separately because the trace meter wants the LOS half on its own and
 * the noise alert wants neither.
 */

/* A clear grid walk between two points: no wall cell and no non-OPEN door. */
int ai_line_of_sight(const struct GameState *state, fix88_t from_x, fix88_t from_y,
                     fix88_t to_x, fix88_t to_y);

/*
 * Is the point (dx, dy) away from a body facing `facing` inside its cone?
 * `half_cone_tan_q8` is tan(half the cone angle) in 8.8, so the test is the
 * cross/dot comparison |cross| * 256 <= dot * tan and never an arctangent.
 */
int ai_within_cone(angle_t facing, int16_t dx, int16_t dy, int16_t half_cone_tan_q8);

/* Squared distance between two points, in map units squared. */
int32_t ai_distance_squared(fix88_t ax, fix88_t ay, fix88_t bx, fix88_t by);

/* The full DESIGN 8 predicate for entity `index`: grid LOS, inside the cone,
 * and within base sight scaled by the throttle's emission multiplier. */
int ai_can_see_player(const struct GameState *state, uint16_t index);

/* ---- the tick ------------------------------------------------------------ */

/* Rebuild the field if it is due, then run every enemy's state machine. */
void ai_step(struct GameState *state);

/*
 * Wake an IDLE enemy into its ALERT tell.  Called by sight, by the noise of a
 * shot, and by a Watchdog waking its pack.  Returns 1 if this call is what woke
 * it: a body already awake, one that is not an enemy, and a Sentry still inside
 * its iris cooldown all return 0, and DESIGN 9's noise charge counts exactly
 * the bodies that were woken.
 */
int entity_alert(struct GameState *state, uint16_t index);

#endif /* BLACKICE_AI_H */
