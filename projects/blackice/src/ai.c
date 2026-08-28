/*
 * ai.c - the BFS distance field, the grid line walk, sight, and DESIGN 8's
 *        three state machines.
 *
 * ---------------------------------------------------------------------------
 * Why the flood needs no bounds test
 * ---------------------------------------------------------------------------
 * DESIGN 11 rule 2 seals every map border with a wall or a terminal door, and
 * both are blocking: a sealed gate and a sector exit are touched, never opened
 * (map.c's door_variant_is_fixed refuses all three).  So no border cell is ever
 * walkable, no walkable cell is ever on the border, and `index +/- 1` and
 * `index +/- width` from a walkable cell always land inside the grid without
 * wrapping a row.  That is the same invariant the raycaster's DDA relies on,
 * and it is what lets the flood below be pure index arithmetic - no divide, no
 * row test, no clamp - which is what makes it affordable at 3.125 Hz.
 *
 * ---------------------------------------------------------------------------
 * No divides, no floats, no 32-bit multiplies
 * ---------------------------------------------------------------------------
 * The cone test is a cross/dot comparison against a tangent, not an
 * arctangent.  Ranges are compared as squares, not distances.  Every widening
 * product goes through fixed.h's mul16, so the 68000 emits `muls.w` and never
 * calls libgcc.  The only divides are the two in claim_take, which run once per
 * cell an enemy enters and not once per tick.
 */
#include "ai.h"
#include "entities.h"
#include "events.h"
#include "game.h"
#include "sim.h"
#include "trace.h"

/*
 * Neighbour order: the four orthogonals first, then the four diagonals, so a
 * loop over the first four is the flood's 4-neighbourhood and a loop over all
 * eight is the mover's "best of 8" (DESIGN 8.1).
 */
static const int8_t NEIGHBOUR_DX[NEIGHBOUR_COUNT] = { 0, 1, 0, -1,  1,  1, -1, -1 };
static const int8_t NEIGHBOUR_DY[NEIGHBOUR_COUNT] = { -1, 0, 1, 0, -1,  1,  1, -1 };

/*
 * A diagonal is legal only if BOTH the orthogonals it cuts between are open,
 * or a body would clip the corner of a wall.  Row k names the two orthogonal
 * neighbour indices that diagonal NEIGHBOUR_ORTHO_COUNT + k lies between.
 */
static const uint8_t DIAGONAL_ORTHO[NEIGHBOUR_COUNT - NEIGHBOUR_ORTHO_COUNT][2] = {
    { 0, 1 },   /* north-east */
    { 1, 2 },   /* south-east */
    { 2, 3 },   /* south-west */
    { 3, 0 },   /* north-west */
};

/* DESIGN 5's enemy-sight multipliers, 8.8: 0.5 / 1.0 / 1.5. */
static const uint16_t THROTTLE_SIGHT_SCALE[THROTTLE_MODE_COUNT] = {
    THROTTLE_SIGHT_UNDERCLOCK, THROTTLE_SIGHT_NOMINAL, THROTTLE_SIGHT_OVERCLOCK
};

static const uint8_t ALERT_SFX[ENT_TYPE_COUNT] = {
    /* Only the three first-playable enemies have a cue (DESIGN 8). */
    [ENT_WATCHDOG] = EV_SFX_WATCHDOG_SNARL,
    [ENT_SENTRY]   = EV_SFX_SENTRY_CHARGE,
    [ENT_TRACER]   = EV_SFX_TRACER_PING,
};

static const uint16_t ALERT_TICKS[ENT_TYPE_COUNT] = {
    [ENT_WATCHDOG] = WATCHDOG_ALERT_TICKS,
    [ENT_SENTRY]   = SENTRY_CHARGE_TICKS,
    [ENT_TRACER]   = TRACER_ALERT_TICKS,
};

int8_t ai_neighbour_dx(int n)
{
    return NEIGHBOUR_DX[n];
}

int8_t ai_neighbour_dy(int n)
{
    return NEIGHBOUR_DY[n];
}

void ai_neighbour_offsets(int16_t width, int16_t *out)
{
    int n;

    for (n = 0; n < NEIGHBOUR_COUNT; ++n) {
        out[n] = (int16_t)(NEIGHBOUR_DX[n] + NEIGHBOUR_DY[n] * width);
    }
}

angle_t ai_ortho_facing(int n)
{
    /* Engine angle of each orthogonal direction; see fixed.h for why east is 0. */
    static const angle_t FACING[NEIGHBOUR_ORTHO_COUNT] = {
        (angle_t)(3 * ANGLE_QUARTER_TURN),  /* north, -y */
        0,                                  /* east,  +x */
        ANGLE_QUARTER_TURN,                 /* south, +y */
        (angle_t)(2 * ANGLE_QUARTER_TURN),  /* west,  -x */
    };

    return FACING[n];
}

/* ---- the BFS distance field (DESIGN 8.1) -------------------------------- */

/*
 * NAV_UNREACHABLE in all four bytes of a longword.  The flood clears the field
 * a longword at a time: at 3.125 Hz over a 32x32 grid the byte-wise clear this
 * replaced was 114,688 cycles of the rebuild's budget, and it cleared 4,096
 * cells for a level that has 1,024.
 */
#define NAV_UNREACHABLE_WORD ((uint32_t)NAV_UNREACHABLE * 0x01010101u)

/* Longwords needed to cover `cells` bytes.  Rounding up can only touch the
 * three bytes past the grid, and a full 64x64 grid is an exact multiple, so the
 * write always stays inside NavSteps. */
static void nav_clear(NavField *field, uint16_t cells)
{
    uint16_t words = (uint16_t)((cells + 3) >> 2);
    uint16_t i;

    for (i = 0; i < words; ++i) {
        field->steps.word[i] = NAV_UNREACHABLE_WORD;
    }
}

void nav_rebuild(NavField *field, const MapGrid *grid, const MapBlocking *blocking,
                 uint16_t origin_cell)
{
    /* The flood is 4-neighbour, so only the first NEIGHBOUR_ORTHO_COUNT of
     * these are read; taking all eight keeps one definition of the order. */
    int16_t offset[NEIGHBOUR_COUNT];
    /* Hoisted out of `field`: through the struct, GCC recomputed the base of
     * each array from the pointer on every access, which is a 32-bit add and a
     * mask per neighbour in the innermost loop of the whole AI. */
    uint8_t *steps = field->steps.byte;
    uint16_t *queue = field->queue;
    uint16_t head = 0;
    uint16_t tail = 0;

    ai_neighbour_offsets(grid->width, offset);
    nav_clear(field, (uint16_t)((uint16_t)grid->width * grid->height));
    field->origin_cell = origin_cell;
    field->visited = 0;
    if (map_cell_blocks(blocking, origin_cell)) {
        return;                         /* nothing can path to a body inside a wall */
    }
    steps[origin_cell] = 0;
    queue[head++] = origin_cell;

    while (tail < head) {
        uint16_t cell = queue[tail++];
        uint8_t next_steps = (uint8_t)(steps[cell] + 1);
        int n;

        if (next_steps > NAV_RADIUS_STEPS) {
            continue;                   /* the flood is radius limited, not exhaustive */
        }
        for (n = 0; n < NEIGHBOUR_ORTHO_COUNT; ++n) {
            uint16_t neighbour = (uint16_t)(cell + offset[n]);

            if (steps[neighbour] != NAV_UNREACHABLE
                || map_cell_blocks(blocking, neighbour)) {
                continue;
            }
            steps[neighbour] = next_steps;
            queue[head++] = neighbour;
        }
    }
    field->visited = tail;
}

/* ---- the grid line walk -------------------------------------------------- */

/* Grid lines the walk crosses between two cells: one per row and one per
 * column, because a step is one line and never two. */
static uint16_t cells_apart(int16_t from, int16_t to)
{
    int16_t span = (int16_t)(to - from);

    return (uint16_t)(span < 0 ? -span : span);
}

void grid_walk_init(GridWalk *walk, const MapGrid *grid,
                    fix88_t from_x, fix88_t from_y, fix88_t to_x, fix88_t to_y)
{
    /*
     * Both endpoints are map coordinates, so the deltas and their magnitudes
     * are words by construction.  Keeping them int16 all the way is not just
     * tidiness: carrying a 32-bit span turns mul16 into a __mulsi3 call in the
     * negative-delta branches, which is 250 cycles inside the line of sight
     * every enemy walks every tick.
     */
    int16_t dx = (int16_t)(to_x - from_x);
    int16_t dy = (int16_t)(to_y - from_y);
    int16_t span_x = dx;
    int16_t span_y = dy;
    int16_t to_boundary_x;
    int16_t to_boundary_y;

    /* Negating in place rather than through a conditional expression: the
     * expression form leaves GCC holding a widened copy in an address register
     * and mul16 degrades to __mulsi3 on that branch. */
    if (span_x < 0) {
        span_x = (int16_t)-span_x;
    }
    if (span_y < 0) {
        span_y = (int16_t)-span_y;
    }

    walk->cell_x = (int16_t)(from_x >> CELL_SHIFT);
    walk->cell_y = (int16_t)(from_y >> CELL_SHIFT);
    walk->cell = map_cell_index(grid, walk->cell_x, walk->cell_y);
    walk->step_x = (int16_t)(dx > 0 ? 1 : (dx < 0 ? -1 : 0));
    walk->step_y = (int16_t)(dy > 0 ? 1 : (dy < 0 ? -1 : 0));
    walk->stride_x = walk->step_x;
    walk->stride_y = (int16_t)(walk->step_y * grid->width);
    walk->steps_left = cells_apart(walk->cell_x, (int16_t)(to_x >> CELL_SHIFT))
                     + cells_apart(walk->cell_y, (int16_t)(to_y >> CELL_SHIFT));

    to_boundary_x = (int16_t)(dx >= 0 ? (CELL_UNITS - (from_x & CELL_FRAC_MASK))
                                      : (from_x & CELL_FRAC_MASK));
    to_boundary_y = (int16_t)(dy >= 0 ? (CELL_UNITS - (from_y & CELL_FRAC_MASK))
                                      : (from_y & CELL_FRAC_MASK));

    /*
     * Both crossing parameters are scaled by span_x * span_y, so comparing
     * them needs no divide.  A zero span leaves that axis' parameter pinned at
     * zero with a zero increment, which makes the other axis win every
     * comparison - exactly right for an axis-aligned line.
     */
    walk->err_x = mul16(to_boundary_x, span_y);
    walk->err_y = mul16(to_boundary_y, span_x);
    walk->err_step_x = mul16((int16_t)CELL_UNITS, span_y);
    walk->err_step_y = mul16((int16_t)CELL_UNITS, span_x);
}

void grid_walk_step(GridWalk *walk)
{
    if (walk->err_x <= walk->err_y) {
        walk->cell_x = (int16_t)(walk->cell_x + walk->step_x);
        walk->cell = (uint16_t)(walk->cell + walk->stride_x);
        walk->err_x += walk->err_step_x;
    } else {
        walk->cell_y = (int16_t)(walk->cell_y + walk->step_y);
        walk->cell = (uint16_t)(walk->cell + walk->stride_y);
        walk->err_y += walk->err_step_y;
    }
    if (walk->steps_left > 0) {
        --walk->steps_left;
    }
}

/* ---- sight --------------------------------------------------------------- */

int32_t ai_distance_squared(fix88_t ax, fix88_t ay, fix88_t bx, fix88_t by)
{
    int16_t dx = (int16_t)(bx - ax);
    int16_t dy = (int16_t)(by - ay);

    return mul16(dx, dx) + mul16(dy, dy);
}

int ai_line_of_sight(const GameState *state, fix88_t from_x, fix88_t from_y,
                     fix88_t to_x, fix88_t to_y)
{
    const MapGrid grid = level_grid(state->level);
    GridWalk walk;
    uint16_t steps;

    grid_walk_init(&walk, &grid, from_x, from_y, to_x, to_y);
    /*
     * steps_left is exactly the number of grid lines between the two cells, so
     * the walk stops when it arrives instead of running to a safety limit: a
     * sighting across two cells costs two steps, not GRID_WALK_MAX_STEPS.  The
     * limit is still the outer bound, because a hand-built level may place two
     * bodies further apart than a walk should ever run.
     */
    steps = walk.steps_left;
    if (steps > GRID_WALK_MAX_STEPS) {
        return 0;
    }
    while (steps-- > 0) {
        grid_walk_step(&walk);
        if (map_cell_blocks(&state->blocking, walk.cell)) {
            return 0;                   /* a wall, or a door that is not OPEN */
        }
    }
    return 1;
}

int ai_within_cone(angle_t facing, int16_t dx, int16_t dy, int16_t half_cone_tan_q8)
{
    int16_t cosine = angle_cos(facing);
    int16_t sine = angle_sin(facing);
    int32_t along = (mul16(dx, cosine) + mul16(dy, sine)) >> TRIG_SHIFT;
    int32_t across = (mul16(dy, cosine) - mul16(dx, sine)) >> TRIG_SHIFT;

    if (along <= 0) {
        return 0;                       /* behind the body: no cone reaches back */
    }
    if (across < 0) {
        across = -across;
    }
    /*
     * |across| <= along * tan(half cone), with the tangent in 8.8.  Both terms
     * are bounded by the map diagonal (about 23,200 map units) times tan(75
     * deg), so the comparison stays inside a 32-bit word product.
     */
    return (across << 8) <= mul16((int16_t)along, half_cone_tan_q8);
}

/* DESIGN 8's base sight, after the throttle multiplier and the 25% trace bonus. */
static int32_t sight_range_units(const GameState *state, const EntityRuntime *body)
{
    const EnemyStats *stats = entity_stats(body->type);
    int32_t range = stats->sight_units;

    if (body->type == ENT_WATCHDOG && state->trace_band >= TRACE_BAND_DEGRADED) {
        range += WATCHDOG_ALERT_BONUS_UNITS;    /* DESIGN 9's 25% threshold */
    }
    return mul16((int16_t)range, (int16_t)THROTTLE_SIGHT_SCALE[state->throttle]) >> 8;
}

/*
 * The three predicates below take the record and not its index.  The record is
 * ENTITY_RUNTIME_BYTES wide and the 68000 has no addressing mode for a table
 * of that stride, so re-deriving &entities[index] inside each of them was a
 * shift-and-add chain per call - paid three times over for one sighting.
 */

/* The range half of DESIGN 8's predicate. */
static int within_sight_range(const GameState *state, const EntityRuntime *body)
{
    int32_t range = sight_range_units(state, body);

    return ai_distance_squared(body->x, body->y, state->player.x, state->player.y)
           <= mul16((int16_t)range, (int16_t)range);
}

/* The cone half. */
static int within_sight_cone(const GameState *state, const EntityRuntime *body)
{
    return ai_within_cone(body->facing,
                          (int16_t)(state->player.x - body->x),
                          (int16_t)(state->player.y - body->y),
                          entity_stats(body->type)->cone_tan_q8);
}

int ai_can_see_player(const GameState *state, uint16_t index)
{
    const EntityRuntime *body = &state->entities[index];

    return within_sight_range(state, body)
        && within_sight_cone(state, body)
        && ai_line_of_sight(state, body->x, body->y, state->player.x, state->player.y);
}

/*
 * The same predicate inside the tick, where ai_step has already paid for the
 * range and line-of-sight halves and left the answer in ENTITY_FLAG_SEES_PLAYER.
 * Only the cone is left, which is four multiplies.
 */
static int sees_player_now(const GameState *state, const EntityRuntime *body)
{
    return (body->flags & ENTITY_FLAG_SEES_PLAYER)
        && within_sight_cone(state, body);
}

/* ---- alerting ------------------------------------------------------------ */

/* The transition itself, written once so the pack wake cannot drift from it. */
static void begin_alert(GameState *state, uint16_t index)
{
    EntityRuntime *body = &state->entities[index];

    body->state = ENT_STATE_ALERT;
    body->state_timer = ALERT_TICKS[body->type];
    event_push(&state->events, ALERT_SFX[body->type]);
}

/* DESIGN 8: an alerted Watchdog wakes its pack inside WATCHDOG_PACK_WAKE_UNITS.
 * It calls begin_alert and not entity_alert, so waking cannot recurse. */
static void wake_pack(GameState *state, uint16_t index)
{
    const EntityRuntime *waker = &state->entities[index];
    const int32_t radius_squared = mul16((int16_t)WATCHDOG_PACK_WAKE_UNITS,
                                         (int16_t)WATCHDOG_PACK_WAKE_UNITS);
    uint16_t i;

    for (i = 0; i < state->level->entity_count; ++i) {
        const EntityRuntime *other = &state->entities[i];

        if (i == index || !entity_is_live(state, i) || other->type != ENT_WATCHDOG
            || other->state != ENT_STATE_IDLE) {
            continue;
        }
        if (ai_distance_squared(waker->x, waker->y, other->x, other->y) <= radius_squared) {
            begin_alert(state, i);
        }
    }
}

/*
 * DESIGN 8's Sentry closes its iris for SENTRY_IRIS_SHUT_TICKS after a burst,
 * and sentry_step spends that cooldown in IDLE with a running state_timer.  A
 * body with its iris shut is invulnerable AND deaf - it is not watching, and a
 * shot next to it is not something it can react to until the iris opens again -
 * so nothing may wake it before the timer runs out.  Written here rather than
 * in sentry_step because sight is only one of three ways in: the noise of a
 * shot and a Watchdog's pack wake are the others.
 */
static int entity_is_deaf(const EntityRuntime *body)
{
    return body->type == ENT_SENTRY && body->state == ENT_STATE_IDLE
        && body->state_timer > 0;
}

int entity_alert(GameState *state, uint16_t index)
{
    EntityRuntime *body = &state->entities[index];

    if (body->state != ENT_STATE_IDLE || !entity_type_is_enemy(body->type)
        || entity_is_deaf(body)) {
        return 0;
    }
    begin_alert(state, index);
    if (body->type == ENT_WATCHDOG) {
        wake_pack(state, index);
    }
    return 1;
}

/* ---- movement ------------------------------------------------------------ */

/*
 * Geometry only: is neighbour `n` of `cell` an open cell that a body may cross
 * into, ignoring who has claimed it?  A diagonal also needs both orthogonals
 * it cuts between to be open, or the body clips a wall corner.
 */
static int neighbour_is_open(const GameState *state, uint16_t cell, int n,
                             uint16_t *out_cell)
{
    const int16_t *offset = state->neighbour_offset;
    uint16_t neighbour = (uint16_t)(cell + offset[n]);

    if (map_cell_blocks(&state->blocking, neighbour)) {
        return 0;
    }
    if (n >= NEIGHBOUR_ORTHO_COUNT) {
        const uint8_t *pair = DIAGONAL_ORTHO[n - NEIGHBOUR_ORTHO_COUNT];

        if (map_cell_blocks(&state->blocking, (uint16_t)(cell + offset[pair[0]]))
            || map_cell_blocks(&state->blocking, (uint16_t)(cell + offset[pair[1]]))) {
            return 0;
        }
    }
    *out_cell = neighbour;
    return 1;
}

/*
 * DESIGN 8.1's one-per-cell claim.  The player's own cell is deliberately
 * claimable: a Watchdog that could not enter it could never close to its
 * 0.6-cell melee reach, and standing on the player is what contact means.
 */
static int cell_is_unclaimed(const GameState *state, uint16_t index, uint16_t cell)
{
    int32_t owner = occupancy_owner(&state->occupancy, cell);

    return owner < 0 || owner == (int32_t)index;
}

/* Move one coordinate toward `target` by at most `speed`.  Returns 1 on arrival. */
static int step_toward(fix88_t *coord, fix88_t target, int16_t speed)
{
    int32_t delta = (int32_t)target - *coord;

    if (delta > speed) {
        delta = speed;
    } else if (delta < -speed) {
        delta = -speed;
    }
    *coord = (fix88_t)(*coord + delta);
    return *coord == target;
}

/*
 * Walk toward the centre of the cell this body has claimed.  Returns 1 when it
 * is standing on that centre and may pick again (DESIGN 8.1's commit rule).
 * Both axes move at full speed, Wolfenstein-style, so a diagonal is faster than
 * an orthogonal by root two; that is the classic behaviour and it is cheap.
 */
static int advance_to_claim(GameState *state, uint16_t index, int16_t speed)
{
    EntityRuntime *body = &state->entities[index];
    int arrived_x = step_toward(&body->x, body->target_x, speed);
    int arrived_y = step_toward(&body->y, body->target_y, speed);

    return arrived_x && arrived_y;
}

/*
 * The choice a mover makes at a cell centre.  `prefer_high` ascends the field
 * instead of descending it, which is the only difference between a Watchdog
 * closing and a Tracer fleeing (DESIGN 8.1).  `*queued` reports that a better
 * neighbour existed but another body had claimed it - the difference between a
 * queue and an arrival, which is what the navigation soak asserts on.
 */
static int pick_gradient_neighbour(const GameState *state, uint16_t index, int prefer_high,
                                   uint16_t *out_cell, int *queued)
{
    const EntityRuntime *body = &state->entities[index];
    uint8_t best_steps = nav_steps(&state->nav, body->claim_cell);
    int found = 0;
    int n;

    *queued = 0;
    for (n = 0; n < NEIGHBOUR_COUNT; ++n) {
        uint16_t neighbour;
        uint8_t steps;

        if (!neighbour_is_open(state, body->claim_cell, n, &neighbour)) {
            continue;
        }
        steps = nav_steps(&state->nav, neighbour);
        if (steps == NAV_UNREACHABLE) {
            continue;
        }
        if (!(prefer_high ? (steps > best_steps) : (steps < best_steps))) {
            continue;
        }
        if (!cell_is_unclaimed(state, index, neighbour)) {
            *queued = 1;
            continue;
        }
        best_steps = steps;
        *out_cell = neighbour;
        found = 1;
    }
    return found;
}

/* Face the direction of travel, so an enemy's cone means what it looks like. */
static void face_cell(GameState *state, uint16_t index, uint16_t from, uint16_t to)
{
    int16_t delta = (int16_t)((int32_t)to - from);
    int n;

    for (n = 0; n < NEIGHBOUR_COUNT; ++n) {
        if (delta == state->neighbour_offset[n]) {
            /* A diagonal takes the facing of its first orthogonal: every cone
             * in the game is wider than the 45 degrees that costs. */
            int ortho = (n < NEIGHBOUR_ORTHO_COUNT)
                      ? n : DIAGONAL_ORTHO[n - NEIGHBOUR_ORTHO_COUNT][0];

            state->entities[index].facing = ai_ortho_facing(ortho);
            return;
        }
    }
}

/*
 * One tick of DESIGN 8.1's movement: at a cell centre, pick a neighbour and
 * commit to it; otherwise keep walking to the centre of the cell already
 * claimed.
 */
static void move_along_field(GameState *state, uint16_t index, int16_t speed, int prefer_high)
{
    EntityRuntime *body = &state->entities[index];
    uint16_t chosen = 0;
    int queued;

    body->flags &= (uint8_t)~ENTITY_FLAG_BLOCKED;
    if (!advance_to_claim(state, index, speed)) {
        return;                                 /* still crossing: it committed */
    }
    if (!pick_gradient_neighbour(state, index, prefer_high, &chosen, &queued)) {
        if (queued) {
            body->flags |= ENTITY_FLAG_BLOCKED;
        }
        return;                                 /* arrived, or waiting its turn */
    }
    face_cell(state, index, body->claim_cell, chosen);
    claim_take(state, index, chosen);
}

/* ---- the Watchdog (DESIGN 8) --------------------------------------------- */

static int within_melee(const GameState *state, const EntityRuntime *body)
{
    const int32_t reach_squared = mul16((int16_t)WATCHDOG_MELEE_REACH,
                                        (int16_t)WATCHDOG_MELEE_REACH);

    return ai_distance_squared(body->x, body->y, state->player.x, state->player.y)
           <= reach_squared;
}

static void watchdog_step(GameState *state, uint16_t index)
{
    EntityRuntime *body = &state->entities[index];

    switch (body->state) {
    case ENT_STATE_IDLE:
        if (sees_player_now(state, body)) {
            entity_alert(state, index);
        }
        break;

    case ENT_STATE_ALERT:
        if (--body->state_timer == 0) {
            body->state = ENT_STATE_CHASE;
        }
        break;

    case ENT_STATE_CHASE:
        if (within_melee(state, body) && body->attack_timer == 0) {
            body->state = ENT_STATE_ATTACK;
            body->state_timer = WATCHDOG_BITE_WINDUP_TICKS;
            break;
        }
        move_along_field(state, index, WATCHDOG_SPEED, 0);
        break;

    case ENT_STATE_ATTACK:
        /* The wind-up is the player's window to back out of reach. */
        if (--body->state_timer == 0) {
            if (within_melee(state, body)) {
                sim_damage_player(state, WATCHDOG_MELEE_DAMAGE);
            }
            body->attack_timer = WATCHDOG_ATTACK_TICKS;
            body->state = ENT_STATE_CHASE;
        }
        break;

    default:
        break;                                  /* DEAD belongs to entities_step */
    }
}

/* ---- the Sentry (DESIGN 8) ----------------------------------------------- */

static void sentry_step(GameState *state, uint16_t index)
{
    EntityRuntime *body = &state->entities[index];

    switch (body->state) {
    case ENT_STATE_IDLE:
        /* The iris is shut: invulnerable, and deaf until its cooldown ends. */
        if (body->state_timer > 0) {
            --body->state_timer;
            break;
        }
        if (sees_player_now(state, body)) {
            entity_alert(state, index);
        }
        break;

    case ENT_STATE_ALERT:
        /* The charge whine.  Still shut, still invulnerable. */
        if (--body->state_timer == 0) {
            body->state = ENT_STATE_ATTACK;
            body->state_timer = SENTRY_IRIS_OPEN_TICKS;
            body->attack_timer = 0;
        }
        break;

    case ENT_STATE_ATTACK:
        /* Iris open: this is the whole of the vulnerability window. */
        if (body->attack_timer == 0 && sees_player_now(state, body)) {
            sim_damage_player(state, SENTRY_HITSCAN_DAMAGE);
            body->attack_timer = SENTRY_FIRE_TICKS;
        }
        if (--body->state_timer == 0) {
            body->state = ENT_STATE_IDLE;
            body->state_timer = SENTRY_IRIS_SHUT_TICKS;
        }
        break;

    default:
        break;
    }
}

/* ---- the Tracer (DESIGN 8, DESIGN 8.1) ----------------------------------- */

/*
 * The outer walkable ring: a cell inside the border wall, which is as close to
 * leaving the sector as a body can get.  DESIGN 8's fleeing Tracer "ascends the
 * field to the nearest sector-edge cell"; arriving there costs the player 15%
 * trace and the body despawns.  A Tracer that has climbed out of the 20-cell
 * field entirely has escaped just as thoroughly, and that second rule is what
 * stops a flee from stalling on an interior local maximum.
 *
 * Both shipped maps reach this ring: level 1's exit throat is floor at (15, 1)
 * and its start chamber is floor along y = 30, and level 2's throat is floor at
 * (27, 1) with the same southern chamber - 13 and 11 qualifying floor cells.
 * The predicate is exercised, not dead.
 */
static int cell_is_sector_edge(const GameState *state, uint16_t cell)
{
    const uint16_t width = state->level->width;
    const uint16_t height = state->level->height;
    uint16_t x = (uint16_t)(cell % width);
    uint16_t y = (uint16_t)(cell / width);

    return x <= 1 || y <= 1 || x >= (uint16_t)(width - 2) || y >= (uint16_t)(height - 2);
}

static void tracer_escape(GameState *state, uint16_t index)
{
    claim_release(state, index);
    state->entity_alive[index] = 0;
    trace_apply(state, TRACE_BUMP_TRACER_ESCAPE);
    event_push(&state->events, EV_SFX_TRACER_SIREN);
}

/* The centre of a cell, as a point.  Two divides, paid once per candidate the
 * ring pick considers and never inside a per-tick loop. */
static void cell_centre_point(const GameState *state, uint16_t cell,
                              fix88_t *out_x, fix88_t *out_y)
{
    const uint16_t width = state->level->width;

    *out_x = cell_centre((uint8_t)(cell % width));
    *out_y = cell_centre((uint8_t)(cell / width));
}

/*
 * Holding the ring: the lateral neighbour is the legal one whose direction is
 * most perpendicular to the player's bearing, whose own field value keeps the
 * body inside the 3..5 band, and which still has line of sight to the player.
 *
 * The LOS filter is DESIGN 8.1's wording and not a refinement of it: the Tracer
 * "prefers cells whose field value is 3-5 WITH line of sight to the player,
 * holding that ring and firing".  A ring cell behind a pillar is a cell the
 * body cannot shoot from, so strafing into one is strafing out of the fight.
 */
static int pick_lateral_neighbour(const GameState *state, uint16_t index, uint16_t *out_cell)
{
    const EntityRuntime *body = &state->entities[index];
    int16_t bearing_x = (int16_t)(state->player.x - body->x);
    int16_t bearing_y = (int16_t)(state->player.y - body->y);
    int32_t best_alignment = 0;
    int found = 0;
    int n;

    for (n = 0; n < NEIGHBOUR_COUNT; ++n) {
        uint16_t neighbour;
        uint8_t steps;
        int32_t alignment;
        fix88_t centre_x;
        fix88_t centre_y;

        if (!neighbour_is_open(state, body->claim_cell, n, &neighbour)
            || !cell_is_unclaimed(state, index, neighbour)) {
            continue;
        }
        steps = nav_steps(&state->nav, neighbour);
        if (steps < TRACER_RING_MIN_STEPS || steps > TRACER_RING_MAX_STEPS) {
            continue;
        }
        cell_centre_point(state, neighbour, &centre_x, &centre_y);
        if (!ai_line_of_sight(state, centre_x, centre_y, state->player.x, state->player.y)) {
            continue;
        }
        alignment = mul16(NEIGHBOUR_DX[n], bearing_x) + mul16(NEIGHBOUR_DY[n], bearing_y);
        if (alignment < 0) {
            alignment = -alignment;
        }
        if (!found || alignment < best_alignment) {
            best_alignment = alignment;
            *out_cell = neighbour;
            found = 1;
        }
    }
    return found;
}

static void tracer_hold_ring(GameState *state, uint16_t index)
{
    EntityRuntime *body = &state->entities[index];
    uint8_t steps = nav_steps(&state->nav, body->claim_cell);
    uint16_t chosen = 0;

    if (steps == NAV_UNREACHABLE || steps > TRACER_RING_MAX_STEPS) {
        move_along_field(state, index, TRACER_SPEED, 0);        /* close in */
        return;
    }
    if (steps < TRACER_RING_MIN_STEPS) {
        move_along_field(state, index, TRACER_SPEED, 1);        /* back off */
        return;
    }
    if (!advance_to_claim(state, index, TRACER_SPEED)) {
        return;
    }
    if (pick_lateral_neighbour(state, index, &chosen)) {
        claim_take(state, index, chosen);       /* the facing stays on the player */
    }
}

/*
 * A body holding the ring keeps its gun on the player, not on its heading.
 * Four facings are all a 150-degree cone needs, and picking the most aligned
 * one is a comparison of four dot products - no arctangent.
 */
static void face_player(GameState *state, uint16_t index)
{
    const EntityRuntime *body = &state->entities[index];
    int16_t dx = (int16_t)(state->player.x - body->x);
    int16_t dy = (int16_t)(state->player.y - body->y);
    int32_t best_alignment = 0;
    int best = 0;
    int n;

    for (n = 0; n < NEIGHBOUR_ORTHO_COUNT; ++n) {
        int32_t alignment = mul16(NEIGHBOUR_DX[n], dx) + mul16(NEIGHBOUR_DY[n], dy);

        if (n == 0 || alignment > best_alignment) {
            best_alignment = alignment;
            best = n;
        }
    }
    state->entities[index].facing = ai_ortho_facing(best);
}

/*
 * DESIGN 8's state table: an IDLE Tracer "patrols its spawn room".  The level
 * format marks no rooms, so the patrol is a bounded random walk instead - it
 * takes the same committed cell steps CHASE does, but picks the next cell at
 * random from the ones within TRACER_PATROL_RADIUS_UNITS of where it spawned.
 * That reads as a body on a beat rather than a statue, and it keeps the Tracer
 * inside the chamber it was authored into.
 *
 * It is also the simulation's only consumer of DESIGN 4.3's LCG.  Until it
 * existed, rng_seed was carried through the level header, hashed, and read by
 * nothing - a determinism contract with nothing behind it.
 */
static void tracer_patrol(GameState *state, uint16_t index)
{
    EntityRuntime *body = &state->entities[index];
    const int32_t radius_squared = mul16((int16_t)TRACER_PATROL_RADIUS_UNITS,
                                         (int16_t)TRACER_PATROL_RADIUS_UNITS);
    fix88_t spawn_x;
    fix88_t spawn_y;
    uint16_t first;
    uint16_t n;

    if (!advance_to_claim(state, index, TRACER_SPEED)) {
        return;                                 /* still crossing: it committed */
    }
    cell_centre_point(state, body->spawn_cell, &spawn_x, &spawn_y);
    /* Starting the scan at a random neighbour and taking the first legal one
     * bounds the work at eight tests however crowded the room is, and spends
     * exactly one draw per re-pick. */
    first = rng_below(&state->rng, NEIGHBOUR_COUNT);
    for (n = 0; n < NEIGHBOUR_COUNT; ++n) {
        int which = (int)((uint16_t)(first + n) % NEIGHBOUR_COUNT);
        uint16_t neighbour;
        fix88_t centre_x;
        fix88_t centre_y;

        if (!neighbour_is_open(state, body->claim_cell, which, &neighbour)
            || !cell_is_unclaimed(state, index, neighbour)) {
            continue;
        }
        cell_centre_point(state, neighbour, &centre_x, &centre_y);
        if (ai_distance_squared(centre_x, centre_y, spawn_x, spawn_y) > radius_squared) {
            continue;                           /* that is another room's business */
        }
        face_cell(state, index, body->claim_cell, neighbour);
        claim_take(state, index, neighbour);
        return;
    }
}

static void tracer_step(GameState *state, uint16_t index)
{
    EntityRuntime *body = &state->entities[index];

    switch (body->state) {
    case ENT_STATE_IDLE:
        if (sees_player_now(state, body)) {
            entity_alert(state, index);
            break;
        }
        tracer_patrol(state, index);
        break;

    case ENT_STATE_ALERT:
        if (--body->state_timer == 0) {
            body->state = ENT_STATE_CHASE;
        }
        break;

    case ENT_STATE_CHASE:
        if (body->hp < TRACER_FLEE_HP) {
            body->state = ENT_STATE_FLEE;
            event_push(&state->events, EV_SFX_TRACER_SIREN);
            break;
        }
        face_player(state, index);
        if (body->attack_timer == 0 && sees_player_now(state, body)) {
            sim_damage_player(state, TRACER_SHOT_DAMAGE);
            body->attack_timer = TRACER_FIRE_TICKS;
        }
        tracer_hold_ring(state, index);
        break;

    case ENT_STATE_FLEE:
        if (cell_is_sector_edge(state, body->claim_cell)
            || nav_steps(&state->nav, body->claim_cell) == NAV_UNREACHABLE) {
            tracer_escape(state, index);
            break;
        }
        move_along_field(state, index, TRACER_SPEED, 1);
        break;

    default:
        break;
    }
}

/* ---- the tick ------------------------------------------------------------ */

/*
 * DESIGN 8: a Watchdog or Tracer that is hunting opens a plain gate by
 * contact, using the identical predicate the player uses.  Contact is
 * adjacency, because a closed door is solid and the body can never stand in
 * it; the field picks the route up on its next rebuild.  Locked and jammed
 * variants are not offered, which is what closes the retreat-through-a-door
 * cheese DESIGN 8 names.
 */
static void open_plain_doors_around(GameState *state, uint16_t cell)
{
    int n;

    for (n = 0; n < NEIGHBOUR_ORTHO_COUNT; ++n) {
        uint16_t neighbour = (uint16_t)(cell + state->neighbour_offset[n]);
        uint8_t door = state->door_of_cell[neighbour];

        if (door != DOOR_NONE && state->doors[door].variant == DOOR_PLAIN) {
            game_touch_door(state, (int32_t)neighbour);
        }
    }
}

/*
 * Contact is judged from both cells a crossing body is in: the one it has
 * claimed and the one it is drawn in.  Claiming the cell ahead is what makes
 * the body reach a door a cell early; standing in the cell behind is what makes
 * it still be touching the door it has just walked past, which is the case a
 * claim-only test misses when the body turns a corner beside a gate.
 */
static void open_adjacent_plain_door(GameState *state, const EntityRuntime *body)
{
    uint16_t drawn = cell_of_point((uint8_t)state->level->width, body->x, body->y);

    open_plain_doors_around(state, body->claim_cell);
    if (drawn != body->claim_cell) {
        open_plain_doors_around(state, drawn);
    }
}

/* DESIGN 8: the hunting states.  ALERT is one of them - the tell runs for eight
 * ticks with the body already committed, and a Watchdog that has snarled at you
 * through an open doorway must not be stopped by the gate swinging shut. */
static int state_is_hunting(uint8_t state_id)
{
    return state_id == ENT_STATE_ALERT || state_id == ENT_STATE_CHASE
        || state_id == ENT_STATE_FLEE;
}

void ai_step(GameState *state)
{
    const MapGrid grid = level_grid(state->level);
    uint16_t player_cell = cell_of_point(grid.width, state->player.x, state->player.y);
    uint16_t i;

    if (state->tick >= state->nav.next_rebuild_tick) {
        nav_rebuild(&state->nav, &grid, &state->blocking, player_cell);
        state->nav.next_rebuild_tick = state->tick + NAV_REBUILD_TICKS;
    }

    state->enemy_has_los = 0;
    for (i = 0; i < state->level->entity_count; ++i) {
        EntityRuntime *body = &state->entities[i];

        if (!entity_is_live(state, i) || !entity_type_is_enemy(body->type)) {
            continue;
        }
        if (body->attack_timer > 0) {
            --body->attack_timer;
        }
        if (body->state == ENT_STATE_DEAD || body->state == ENT_STATE_DESTROYED) {
            continue;
        }

        /*
         * DESIGN 9 charges +0.6 %/s "while any enemy has LOS on you", which is
         * the sight predicate without the cone: a body that has you in the open
         * is watching you whichever way its sprite faces.  So the cone cannot be
         * used as a cheap gate here - it is not part of the question - and the
         * two halves that ARE are ordered by what they cost.  The range test is
         * four multiplies; the grid walk is a cell per step and is the most
         * expensive thing the tick does per body, so nothing reaches it that a
         * squared-distance compare could have turned away.  A Sentry with its
         * iris shut is not watching at all and is turned away before both.
         */
        body->flags &= (uint8_t)~ENTITY_FLAG_SEES_PLAYER;
        if (!entity_is_deaf(body) && within_sight_range(state, body)
            && ai_line_of_sight(state, body->x, body->y, state->player.x, state->player.y)) {
            body->flags |= ENTITY_FLAG_SEES_PLAYER;
            state->enemy_has_los = 1;
        }

        switch (body->type) {
        case ENT_WATCHDOG:
            watchdog_step(state, i);
            break;
        case ENT_SENTRY:
            sentry_step(state, i);
            break;
        case ENT_TRACER:
            tracer_step(state, i);
            break;
        default:
            break;
        }

        if (state_is_hunting(body->state)) {
            open_adjacent_plain_door(state, body);
        }
    }
}
