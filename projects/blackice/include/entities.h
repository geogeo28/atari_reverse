/*
 * entities.h - the runtime entity table.
 *
 * A Level's `entities` array is static authored data: a type and a cell.  This
 * is its mutable twin - where each body actually is this tick, what state its
 * machine is in, how much it has left and what it is waiting on.  One record
 * per authored entity, indexed identically, so entity i here is entity i there
 * and neither array needs a back pointer.
 *
 * Fixed size, no allocation: LEVEL_MAX_ENTITIES records live inside GameState.
 *
 * The occupancy map is the other half of the table.  It holds, per grid cell,
 * the index of the entity that has CLAIMED that cell, biased by one so that
 * zero means free.  DESIGN 8.1 moves an enemy cell to cell: it picks a
 * neighbour, claims it, and walks to its centre before picking again, so at any
 * instant an enemy owns exactly one cell and no two enemies own the same one.
 * That claim is also what makes the Buster's hitscan a per-cell lookup instead
 * of a scan of the whole table.
 */
#ifndef BLACKICE_ENTITIES_H
#define BLACKICE_ENTITIES_H

#include <stdint.h>
#include "fixed.h"
#include "game_consts.h"
#include "level.h"

struct GameState;   /* game.h owns the definition; declared to break the cycle */

/*
 * The state machines of DESIGN 8, unified.  Not every enemy uses every state:
 * a Sentry never CHASEs and never FLEEs, a Watchdog never FLEEs, and a pickup
 * sits in IDLE until it is collected and then stops being alive.
 */
#define ENT_STATE_IDLE      0
#define ENT_STATE_ALERT     1   /* the tell: a Watchdog's snarl, a Sentry's charge whine */
#define ENT_STATE_CHASE     2
#define ENT_STATE_ATTACK    3
#define ENT_STATE_FLEE      4
#define ENT_STATE_DEAD      5   /* dissolving; removed when the timer runs out */
#define ENT_STATE_DESTROYED 6   /* a killed Sentry stays as scenery (DESIGN 8) */

/* The best neighbour the mover wanted was owned by another body (DESIGN 8.1's
 * one-per-cell claim).  Read by the navigation soak to tell a jam from a queue. */
#define ENTITY_FLAG_BLOCKED     0x01
/* This body had line of sight to the player on the tick just simulated. */
#define ENTITY_FLAG_SEES_PLAYER 0x02

/*
 * 24 bytes, and the size is load-bearing, not incidental.  ai.c indexes this
 * table in every predicate it runs; at the 22 bytes the fields alone need, the
 * 68000 has no addressing mode for `index * 22` and GCC emitted a seven
 * instruction shift-and-add chain per access.  24 is 8 + 16, which is two
 * shifts and an add, and `spawn_cell` is what fills the two bytes rather than a
 * pad - so the record pays for its own alignment.  ENTITY_RUNTIME_BYTES pins it.
 */
typedef struct {
    uint8_t  type;          /* EntityType, copied from the Level at init */
    uint8_t  state;         /* ENT_STATE_* */
    uint8_t  flags;         /* ENTITY_FLAG_* */
    uint8_t  hp;
    fix88_t  x;             /* map units; a pickup never moves off its cell centre */
    fix88_t  y;
    angle_t  facing;
    uint16_t state_timer;   /* ticks left in ALERT, ATTACK, DEAD, ... */
    uint16_t attack_timer;  /* ticks until this body may attack again */
    uint16_t claim_cell;    /* the grid cell it owns, and is walking to the centre of */
    uint16_t spawn_cell;    /* the cell it was authored in; the Tracer patrol's anchor */
    fix88_t  target_x;      /* claim_cell's centre, cached by claim_take so the */
    fix88_t  target_y;      /* mover pays no divide per tick, only per cell */
} EntityRuntime;

#define ENTITY_RUNTIME_BYTES 24

/* The grid cell a point in map units falls in.  Pure: no GameState, so both
 * the mover and the pickup sweep can use it. */
static inline uint16_t cell_of_point(uint8_t grid_width, fix88_t x, fix88_t y)
{
    return (uint16_t)(((x >> CELL_SHIFT) + (y >> CELL_SHIFT) * grid_width));
}

/* Cell -> owning entity index, biased by one.  Zero is "no body claims it". */
#define ENTITY_CLAIM_NONE 0

typedef struct {
    uint8_t owner[MAP_MAX_CELLS];
} EntityOccupancy;

/*
 * The entity claiming `cell`, or -1.  Inline and taking the map rather than the
 * GameState, because game.h has not defined GameState yet where this header is
 * read - and because the mover asks it eight times per re-pick and the hitscan
 * once per cell it crosses, which is no place for a cross-module `jsr`.
 */
static inline int32_t occupancy_owner(const EntityOccupancy *occupancy, uint16_t cell)
{
    uint8_t owner = occupancy->owner[cell];

    return owner == ENTITY_CLAIM_NONE ? -1 : (int32_t)(owner - 1);
}

/*
 * DESIGN 8's per-type statistics.  ai.c reads the same rows the damage path
 * does, so an enemy's sight and its hit points can never disagree about which
 * kind of thing it is.
 */
typedef struct {
    uint8_t  hp;
    uint8_t  speed;             /* map units per tick; 0 means it never moves */
    uint16_t sight_units;
    uint16_t noise_units;
    int16_t  cone_tan_q8;       /* tan(half cone), 8.8; see game_rules.h */
} EnemyStats;

/* The table itself, so entity_stats can be an inline: every sight test in the
 * tick reads a row, and a cross-translation-unit `jsr` per read is 40 cycles to
 * fetch a pointer the caller could have computed in two. */
extern const EnemyStats g_enemy_stats[ENT_TYPE_COUNT];

static inline const EnemyStats *entity_stats(uint8_t type)
{
    return &g_enemy_stats[type < ENT_TYPE_COUNT ? type : ENT_NONE];
}

/* Watchdog, Sentry or Tracer: a body with a state machine and a weapon. */
static inline int entity_type_is_enemy(uint8_t type)
{
    return type == ENT_WATCHDOG || type == ENT_SENTRY || type == ENT_TRACER;
}

/* The two functions that write the occupancy map, and the only two. */
void claim_take(struct GameState *state, uint16_t index, uint16_t cell);
void claim_release(struct GameState *state, uint16_t index);

/* Reset the table from the level's authored entity list. */
void entities_init(struct GameState *state);

/* The type-independent half of a tick: retire what has finished dissolving.
 * The per-type state machines are ai_step's. */
void entities_step(struct GameState *state);

/* World position of entity `index`, for the sprite projection. */
fix88_t entity_world_x(const struct GameState *state, uint16_t index);
fix88_t entity_world_y(const struct GameState *state, uint16_t index);

/* Deal `damage` to entity `index`, running the death path if it lands the
 * killing blow.  Damage to an invulnerable body is absorbed and returns 0. */
int entity_damage(struct GameState *state, uint16_t index, uint8_t damage);

/* Is this entity a body that blocks a shot and can be shot at? */
int entity_is_shootable(const struct GameState *state, uint16_t index);

/* The entity claiming `cell`, or -1.  Dissolving and collected bodies do not
 * claim anything, so this only ever names something a shot can hit.  The
 * exported form of occupancy_owner, for the callers that hold a GameState. */
int32_t entity_at_cell(const struct GameState *state, uint16_t cell);

/*
 * The shootable body a shot crossing `cell` hits, or -1.
 *
 * THE RULE, decided here and stated once: a body is hittable in the cell it has
 * CLAIMED and in the cell containing its REAL position.  DESIGN 8.1 has a mover
 * claim the cell ahead and then walk to its centre, so for most of a crossing
 * those are two different cells - the claim map names the one it owns and the
 * sprite the player is aiming at stands in the other.  Honouring only the claim
 * makes a body crossing sideways across the player's line unhittable while it
 * is plainly drawn on it; honouring only the real position makes a body the
 * occupancy map says is in the way not stop the shot.  The visible body must
 * always be shootable, so both count.
 */
int32_t entity_hittable_in_cell(const struct GameState *state, uint16_t cell);

/* Wake every enemy of any type within `radius_units` of the player that is
 * still IDLE - DESIGN 8's "firing alerts it regardless of cone".  Returns the
 * number woken, which is what the trace meter's noise bump keys off. */
uint16_t entities_alert_by_noise(struct GameState *state);

/* FNV-1a of the table, folded into the caller's running hash. */
uint32_t entities_hash(const struct GameState *state, uint32_t hash);

#endif /* BLACKICE_ENTITIES_H */
