/*
 * level.h - the level container, its ASCII source form and its .bil blob.
 *
 * A Level is pure static data: grid, entity list, header.  Everything that
 * changes during play (door state, blocking bits, the player, the trace meter)
 * lives in GameState.  A Level is a fixed-size object with no allocation, so
 * both the host and the target hold one in .bss.
 *
 * ---------------------------------------------------------------------------
 * .bil binary layout (big endian, the 68000's byte order) - DESIGN 11
 * ---------------------------------------------------------------------------
 *   off  size  field
 *     0     4  magic 'BIL0'
 *     4    16  name, NUL padded ASCII
 *    20     1  width                 1..64
 *    21     1  height                1..64
 *    22     1  sector_index          0..7
 *    23     1  palette_variant       0 CLEAN / 1 DEGRADED / 2 CORRUPT / 3 KERNEL
 *    24     1  texture_set           0..2
 *    25     1  pad                   0
 *    26     1  start_x               player start cell
 *    27     1  start_y
 *    28     2  start_facing          brads, 0..1023
 *    30     2  trace_base_rate       thousandths of a percent per tick
 *    32     1  trace_start           percent
 *    33     1  trace_carry_cap       percent
 *    34     2  par_ticks             at SIM_HZ
 *    36     2  entity_count          <= LEVEL_MAX_ENTITIES
 *    38   w*h  cells, row major
 *     .   5*n  entities: type u8, x u8, y u8, facing u8 (brads >> 2), extra u8
 * ---------------------------------------------------------------------------
 *
 * ASCII source form (levels/ *.txt), compiled by tools/mklevel.py: a run of
 * "# key: value" header lines, then the map block.  A header line is a '#'
 * followed by a space; a map row starts with a legend glyph and never contains
 * a space, so the two can never be confused.
 *
 * Legend (DESIGN 11, the compiler owns this table):
 *   '.' 0 empty        '#' 1 circuit lattice   '=' 2 hex mesh
 *   '%' 3 glyph column '|' 4 bus trunk         '^' 5 firewall chevron
 *   '?' 6 corrupt noise 'A' 7 anchor pylon     'X' 8 exit plating
 *   '+' 16 plain door  '1' '2' '3' 17/18/19 locked doors
 *   'S' 21 sealed gate '~' 22 corrupted door   '>' 23 sector exit
 *   '@' player start (cell becomes empty; facing comes from the header)
 *   'w' 't' 'B' Watchdog / Tracer / Black ICE, cell becomes empty
 *   's' Sentry, a floor entity in an alcove  '*' anchor, cell becomes wall 7
 *   'p' 'q' 'r' tokens ALPHA / BETA / GAMMA
 *   'c' 'C' cycles small/large   'i' 'I' integrity small/large
 *   'u' scrubber                 'd' data cache
 *
 * The map must be enclosed by blocking cells: the DDA relies on that border
 * instead of a bounds test in its inner loop.
 */
#ifndef BLACKICE_LEVEL_H
#define BLACKICE_LEVEL_H

#include <stdint.h>
#include <stddef.h>
#include "fixed.h"
#include "game_consts.h"
#include "map.h"

/* 'BIL0', spelled out so the loader can compare bytes without a string. */
#define LEVEL_BLOB_MAGIC_BYTES  4
#define LEVEL_BLOB_MAGIC_0      'B'
#define LEVEL_BLOB_MAGIC_1      'I'
#define LEVEL_BLOB_MAGIC_2      'L'
#define LEVEL_BLOB_MAGIC_3      '0'
#define LEVEL_BLOB_HEADER_BYTES 38
#define LEVEL_BLOB_ENTITY_BYTES 5

typedef enum {
    ENT_NONE             = 0,
    ENT_WATCHDOG         = 1,
    ENT_SENTRY           = 2,
    ENT_TRACER           = 3,
    ENT_BLACK_ICE        = 4,
    ENT_ANCHOR           = 5,
    ENT_TOKEN_ALPHA      = 6,
    ENT_TOKEN_BETA       = 7,
    ENT_TOKEN_GAMMA      = 8,
    ENT_CYCLES_SMALL     = 9,
    ENT_CYCLES_LARGE     = 10,
    ENT_INTEGRITY_SMALL  = 11,
    ENT_INTEGRITY_LARGE  = 12,
    ENT_SCRUBBER         = 13,
    ENT_DATA_CACHE       = 14,
    ENT_TYPE_COUNT
} EntityType;

/* Entities as the file stores them: cell coordinates and a brads>>2 facing. */
typedef struct {
    uint8_t type;       /* EntityType */
    uint8_t cell_x;
    uint8_t cell_y;
    uint8_t facing;     /* brads >> 2, so 0..255 */
    uint8_t extra;      /* per-type payload */
} Entity;               /* 5 bytes, matching the .bil record */

typedef struct {
    char     name[LEVEL_NAME_LEN + 1];
    uint8_t  width;
    uint8_t  height;
    uint8_t  sector_index;
    uint8_t  palette_variant;
    uint8_t  texture_set;
    uint8_t  start_cell_x;
    uint8_t  start_cell_y;
    uint16_t start_facing_brads;
    uint16_t trace_base_rate;       /* thousandths of a percent per tick */
    uint8_t  trace_start;           /* percent */
    uint8_t  trace_carry_cap;       /* percent */
    uint16_t par_ticks;
    uint16_t entity_count;
    uint8_t  cells[MAP_MAX_CELLS];
    Entity   entities[LEVEL_MAX_ENTITIES];
} Level;

typedef enum {
    LEVEL_OK              = 0,
    LEVEL_ERR_MAGIC       = 1,
    LEVEL_ERR_SIZE        = 2,
    LEVEL_ERR_DIMENSIONS  = 3,
    LEVEL_ERR_BORDER      = 4,
    LEVEL_ERR_NO_START    = 5,
    LEVEL_ERR_TOO_MANY    = 6,
    LEVEL_ERR_LEGEND      = 7,
    LEVEL_ERR_ROW_WIDTH   = 8,
    LEVEL_ERR_RESERVED    = 9
} LevelResult;

/* Parse the ASCII source form.  `text` need not be NUL terminated. */
LevelResult level_parse_text(const char *text, size_t len, Level *out);

/* Parse a .bil blob as produced by tools/mklevel.py. */
LevelResult level_load_blob(const uint8_t *data, size_t len, Level *out);

/* Serialise to the .bil blob.  Returns the bytes written, or 0 if the buffer
 * is too small.  The host tests use it to prove text and blob agree. */
size_t level_write_blob(const Level *level, uint8_t *out, size_t capacity);

static inline size_t level_blob_size(const Level *level)
{
    return (size_t)LEVEL_BLOB_HEADER_BYTES
         + (size_t)level->width * level->height
         + (size_t)level->entity_count * LEVEL_BLOB_ENTITY_BYTES;
}

static inline MapGrid level_grid(const Level *level)
{
    MapGrid grid;

    grid.cells  = level->cells;
    grid.width  = level->width;
    grid.height = level->height;
    return grid;
}

/* Centre of a grid cell in map units. */
static inline fix88_t cell_centre(uint8_t cell)
{
    return (fix88_t)(cell * CELL_UNITS + CELL_UNITS / 2);
}

#endif /* BLACKICE_LEVEL_H */
