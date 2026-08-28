/*
 * map.h - the grid, the cell encoding, the door table and the blocking bitmap.
 *
 * Cell encoding (DESIGN 11), one byte per cell:
 *      0        empty
 *      1..15    wall, the value is the wall texture id
 *      16..31   door variant; the open fraction lives in the door table
 *      32..     reserved, rejected by the level compiler and the loader
 *
 * The raycaster and the collider do not read the grid to decide whether a cell
 * blocks: they test one bit in MapBlocking.solid.  That turns the DDA's inner
 * test into a shift and a btst, which is the form the hand-written 68000 DDA
 * will consume.  The grid is only read once a hit is confirmed, to pick the
 * texture and to refine a partly-open door.
 *
 * A door cell keeps its solid bit set in every state but OPEN, so a door
 * that is still travelling stops a body.  On a ray hit the DDA refines against
 * the door plane, which sits on the CELL MIDLINE perpendicular to the axis the
 * ray crossed: the ray advances half a delta along that axis and the hit only
 * counts if it is still inside the same cell.  v1 renders two states - the
 * closed leaf, or no hit at all once the door is open.
 */
#ifndef BLACKICE_MAP_H
#define BLACKICE_MAP_H

#include <stdint.h>
#include "game_consts.h"

#define CELL_EMPTY              0
#define CELL_WALL_MIN           1
#define CELL_WALL_MAX           15
#define CELL_DOOR_BASE          16
#define CELL_DOOR_MAX           31
#define CELL_RESERVED_BASE      32

/* Wall texture ids the level legend names (DESIGN 11). */
#define TEX_CIRCUIT_LATTICE     1
#define TEX_HEX_MESH            2
#define TEX_GLYPH_COLUMN        3
#define TEX_BUS_TRUNK           4
#define TEX_FIREWALL_CHEVRON    5
#define TEX_CORRUPT_NOISE       6
#define TEX_ANCHOR_PYLON        7
#define TEX_EXIT_PLATING        8
#define TEX_GATE_PANEL          9    /* plain and exit doors */
#define TEX_LOCKED_PANEL        10   /* locked, sealed and corrupted doors */

/* Door variants (DESIGN 10). */
#define DOOR_PLAIN              16
#define DOOR_LOCK_ALPHA         17
#define DOOR_LOCK_BETA          18
#define DOOR_LOCK_GAMMA         19
#define DOOR_SEALED             21
#define DOOR_CORRUPTED          22
#define DOOR_SECTOR_EXIT        23

#define CELL_IS_WALL(c)         ((c) >= CELL_WALL_MIN && (c) <= CELL_WALL_MAX)
#define CELL_IS_DOOR(c)         ((c) >= CELL_DOOR_BASE && (c) <= CELL_DOOR_MAX)

/* States, distinct from the DOOR_* cell variants above. */
#define DOOR_STATE_CLOSED   0
#define DOOR_STATE_OPENING  1
#define DOOR_STATE_OPEN     2
#define DOOR_STATE_CLOSING  3

typedef struct {
    uint16_t cell;          /* grid index: y * width + x */
    uint8_t  variant;       /* the cell value, CELL_DOOR_BASE..CELL_DOOR_MAX */
    uint8_t  state;         /* DOOR_STATE_* */
    uint16_t timer;         /* ticks left in the current state */
} Door;

/* Only a fully open door lets a body or a ray through. */
#define DOOR_IS_PASSABLE(door) ((door).state == DOOR_STATE_OPEN)

/* Read-only grid, owned by the Level. */
typedef struct {
    const uint8_t *cells;
    uint8_t        width;
    uint8_t        height;
} MapGrid;

/* Mutable blocking state derived from the grid and the door table. */
typedef struct {
    uint8_t solid[MAP_BITMAP_BYTES];
} MapBlocking;

static inline uint16_t map_cell_index(const MapGrid *grid, int16_t x, int16_t y)
{
    return (uint16_t)(y * grid->width + x);
}

static inline int map_cell_blocks(const MapBlocking *blocking, uint16_t cell)
{
    return (blocking->solid[cell >> 3] >> (cell & 7)) & 1;
}

static inline void map_set_blocking(MapBlocking *blocking, uint16_t cell, int blocks)
{
    uint8_t bit = (uint8_t)(1u << (cell & 7));

    if (blocks) {
        blocking->solid[cell >> 3] |= bit;
    } else {
        blocking->solid[cell >> 3] &= (uint8_t)~bit;
    }
}

/* Texture a cell is drawn with; 0 for an empty cell. */
uint8_t map_cell_texture(uint8_t cell_value);

/* A door variant that can never be opened by walking into it. */
int door_variant_is_fixed(uint8_t variant);

/* Rebuild the whole blocking bitmap from the grid and the current door state. */
void map_build_blocking(const MapGrid *grid, const Door *doors, uint16_t door_count,
                        MapBlocking *blocking);

/* Collect every door cell of the grid into `doors`, closed.  Returns the
 * count, capped at DOOR_MAX_COUNT. */
uint16_t map_collect_doors(const MapGrid *grid, Door *doors);

/*
 * Per-cell door index, DOOR_NONE where there is no door.  The DDA needs the
 * open fraction of a door it hits and cannot afford to search the door table,
 * so the mapping is materialised once at level load.  The Door table stays the
 * single source of truth for door state; this is only an index into it.
 */
#define DOOR_NONE 0xff
void map_build_door_index(const MapGrid *grid, const Door *doors, uint16_t door_count,
                          uint8_t *door_of_cell);

#endif /* BLACKICE_MAP_H */
