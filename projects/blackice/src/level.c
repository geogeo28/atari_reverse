/*
 * level.c - the ASCII source parser, the .bil blob reader and the blob writer.
 *
 * The legend table below is the single definition of the glyph mapping on the
 * C side; tools/mklevel.py carries the same table and test/test_level.py pins
 * the two against each other, because a silent divergence between the compiler
 * and the loader is the kind of defect that only shows up as a wrong wall.
 *
 * No libc beyond what the target has: no stdio, no allocation, no strtol.
 */
#include "level.h"

typedef struct {
    char    glyph;
    uint8_t cell;
    uint8_t entity;     /* ENT_NONE when the glyph places no entity */
    uint8_t is_start;
} LegendEntry;

static const LegendEntry LEGEND[] = {
    { '.', CELL_EMPTY,           ENT_NONE,            0 },
    { '#', TEX_CIRCUIT_LATTICE,  ENT_NONE,            0 },
    { '=', TEX_HEX_MESH,         ENT_NONE,            0 },
    { '%', TEX_GLYPH_COLUMN,     ENT_NONE,            0 },
    { '|', TEX_BUS_TRUNK,        ENT_NONE,            0 },
    { '^', TEX_FIREWALL_CHEVRON, ENT_NONE,            0 },
    { '?', TEX_CORRUPT_NOISE,    ENT_NONE,            0 },
    { 'A', TEX_ANCHOR_PYLON,     ENT_NONE,            0 },
    { 'X', TEX_EXIT_PLATING,     ENT_NONE,            0 },
    { '+', DOOR_PLAIN,           ENT_NONE,            0 },
    { '1', DOOR_LOCK_ALPHA,      ENT_NONE,            0 },
    { '2', DOOR_LOCK_BETA,       ENT_NONE,            0 },
    { '3', DOOR_LOCK_GAMMA,      ENT_NONE,            0 },
    { 'S', DOOR_SEALED,          ENT_NONE,            0 },
    { '~', DOOR_CORRUPTED,       ENT_NONE,            0 },
    { '>', DOOR_SECTOR_EXIT,     ENT_NONE,            0 },
    { '@', CELL_EMPTY,           ENT_NONE,            1 },
    { 'w', CELL_EMPTY,           ENT_WATCHDOG,        0 },
    { 't', CELL_EMPTY,           ENT_TRACER,          0 },
    { 'B', CELL_EMPTY,           ENT_BLACK_ICE,       0 },
    { 's', CELL_EMPTY,           ENT_SENTRY,          0 },
    { '*', TEX_ANCHOR_PYLON,     ENT_ANCHOR,          0 },
    { 'p', CELL_EMPTY,           ENT_TOKEN_ALPHA,     0 },
    { 'q', CELL_EMPTY,           ENT_TOKEN_BETA,      0 },
    { 'r', CELL_EMPTY,           ENT_TOKEN_GAMMA,     0 },
    { 'c', CELL_EMPTY,           ENT_CYCLES_SMALL,    0 },
    { 'C', CELL_EMPTY,           ENT_CYCLES_LARGE,    0 },
    { 'i', CELL_EMPTY,           ENT_INTEGRITY_SMALL, 0 },
    { 'I', CELL_EMPTY,           ENT_INTEGRITY_LARGE, 0 },
    { 'u', CELL_EMPTY,           ENT_SCRUBBER,        0 },
    { 'd', CELL_EMPTY,           ENT_DATA_CACHE,      0 },
};

#define LEGEND_COUNT ((int)(sizeof(LEGEND) / sizeof(LEGEND[0])))

/* Defaults for a source file that leaves a header key out. */
#define DEFAULT_PAR_TICKS       3000
#define DEFAULT_TRACE_RATE      400     /* thousandths of a percent per tick */
#define DEFAULT_TRACE_CARRY_CAP 25

static const LegendEntry *legend_lookup(char glyph)
{
    int i;

    for (i = 0; i < LEGEND_COUNT; ++i) {
        if (LEGEND[i].glyph == glyph) {
            return &LEGEND[i];
        }
    }
    return 0;
}

/* ---- tiny text helpers (no libc) ---------------------------------------- */

static int text_equal(const char *a, size_t a_len, const char *b)
{
    size_t i;

    for (i = 0; i < a_len; ++i) {
        if (b[i] == '\0' || a[i] != b[i]) {
            return 0;
        }
    }
    return b[a_len] == '\0';
}

static uint32_t parse_uint(const char *text, size_t len)
{
    uint32_t value = 0;
    size_t i;

    for (i = 0; i < len; ++i) {
        if (text[i] < '0' || text[i] > '9') {
            break;
        }
        value = value * 10 + (uint32_t)(text[i] - '0');
    }
    return value;
}

/* ---- header ------------------------------------------------------------ */

static void level_defaults(Level *level)
{
    int i;

    for (i = 0; i <= LEVEL_NAME_LEN; ++i) {
        level->name[i] = '\0';
    }
    level->width = 0;
    level->height = 0;
    level->sector_index = 0;
    level->palette_variant = 0;
    level->texture_set = 0;
    level->start_cell_x = 0;
    level->start_cell_y = 0;
    level->start_facing_brads = 0;
    level->trace_base_rate = DEFAULT_TRACE_RATE;
    level->trace_start = 0;
    level->trace_carry_cap = DEFAULT_TRACE_CARRY_CAP;
    level->par_ticks = DEFAULT_PAR_TICKS;
    level->entity_count = 0;
}

static void apply_header_line(Level *level, const char *key, size_t key_len,
                              const char *value, size_t value_len)
{
    uint32_t number = parse_uint(value, value_len);

    if (text_equal(key, key_len, "name")) {
        size_t i;

        for (i = 0; i < value_len && i < LEVEL_NAME_LEN; ++i) {
            level->name[i] = value[i];
        }
        level->name[i] = '\0';
    } else if (text_equal(key, key_len, "sector")) {
        level->sector_index = (uint8_t)number;
    } else if (text_equal(key, key_len, "palette")
               || text_equal(key, key_len, "palette_variant")) {
        level->palette_variant = (uint8_t)number;
    } else if (text_equal(key, key_len, "texture_set")) {
        level->texture_set = (uint8_t)number;
    } else if (text_equal(key, key_len, "facing")
               || text_equal(key, key_len, "start_facing")) {
        level->start_facing_brads = (uint16_t)(number % BRADS_PER_TURN);
    } else if (text_equal(key, key_len, "par") || text_equal(key, key_len, "par_ticks")) {
        level->par_ticks = (uint16_t)number;
    } else if (text_equal(key, key_len, "trace_base_rate")) {
        level->trace_base_rate = (uint16_t)number;
    } else if (text_equal(key, key_len, "trace_start")) {
        level->trace_start = (uint8_t)number;
    } else if (text_equal(key, key_len, "trace_carry_cap")) {
        level->trace_carry_cap = (uint8_t)number;
    }
    /*
     * width, height, start_x and start_y appear in authored files but are
     * derived from the map here, so they are ignored - tools/mklevel.py is
     * where they are cross-checked against it and a mismatch is refused.
     * Any other unknown key is ignored on purpose: the design document adds
     * header fields faster than the loader needs them.
     */
}

/*
 * A header line is a '#' followed by a space; a map row starts with a legend
 * glyph and never contains a space, so '#' can safely be both the comment
 * marker and the wall glyph.
 */
static int is_header_line(const char *line, size_t len)
{
    return len >= 2 && line[0] == '#' && line[1] == ' ';
}

static void parse_header_line(Level *level, const char *line, size_t len)
{
    size_t key_start = 2;
    size_t colon = key_start;
    size_t key_end;
    size_t value_start;

    while (colon < len && line[colon] != ':') {
        ++colon;
    }
    if (colon >= len) {
        return;
    }
    key_end = colon;
    while (key_end > key_start && line[key_end - 1] == ' ') {
        --key_end;
    }
    value_start = colon + 1;
    while (value_start < len && line[value_start] == ' ') {
        ++value_start;
    }
    apply_header_line(level, line + key_start, key_end - key_start,
                      line + value_start, len - value_start);
}

/* ---- validation --------------------------------------------------------- */

static LevelResult validate_border(const Level *level)
{
    uint8_t x, y;

    for (x = 0; x < level->width; ++x) {
        if (!CELL_IS_WALL(level->cells[x])
            || !CELL_IS_WALL(level->cells[(level->height - 1) * level->width + x])) {
            return LEVEL_ERR_BORDER;
        }
    }
    for (y = 0; y < level->height; ++y) {
        if (!CELL_IS_WALL(level->cells[y * level->width])
            || !CELL_IS_WALL(level->cells[y * level->width + level->width - 1])) {
            return LEVEL_ERR_BORDER;
        }
    }
    return LEVEL_OK;
}

/* ---- the ASCII source form ---------------------------------------------- */

LevelResult level_parse_text(const char *text, size_t len, Level *out)
{
    size_t pos = 0;
    int have_start = 0;
    uint16_t row = 0;

    level_defaults(out);

    while (pos < len) {
        size_t line_start = pos;
        size_t line_len;
        uint16_t col;

        while (pos < len && text[pos] != '\n') {
            ++pos;
        }
        line_len = pos - line_start;
        if (pos < len) {
            ++pos;                                  /* step over the newline */
        }
        if (line_len && text[line_start + line_len - 1] == '\r') {
            --line_len;
        }
        if (line_len == 0) {
            continue;
        }
        if (is_header_line(text + line_start, line_len)) {
            parse_header_line(out, text + line_start, line_len);
            continue;
        }

        if (row == 0) {
            if (line_len > MAP_MAX_DIM) {
                return LEVEL_ERR_DIMENSIONS;
            }
            out->width = (uint8_t)line_len;
        } else if (line_len != out->width) {
            return LEVEL_ERR_ROW_WIDTH;
        }
        if (row >= MAP_MAX_DIM) {
            return LEVEL_ERR_DIMENSIONS;
        }

        for (col = 0; col < line_len; ++col) {
            const LegendEntry *entry = legend_lookup(text[line_start + col]);

            if (!entry) {
                return LEVEL_ERR_LEGEND;
            }
            out->cells[row * out->width + col] = entry->cell;
            if (entry->is_start) {
                if (have_start) {
                    return LEVEL_ERR_NO_START;      /* a second '@' is as bad as none */
                }
                have_start = 1;
                out->start_cell_x = (uint8_t)col;
                out->start_cell_y = (uint8_t)row;
            }
            if (entry->entity != ENT_NONE) {
                Entity *e;

                if (out->entity_count >= LEVEL_MAX_ENTITIES) {
                    return LEVEL_ERR_TOO_MANY;
                }
                e = &out->entities[out->entity_count++];
                e->type = entry->entity;
                e->cell_x = (uint8_t)col;
                e->cell_y = (uint8_t)row;
                e->facing = 0;
                e->extra = 0;
            }
        }
        ++row;
    }

    out->height = (uint8_t)row;
    if (out->width == 0 || out->height == 0) {
        return LEVEL_ERR_DIMENSIONS;
    }
    if (!have_start) {
        return LEVEL_ERR_NO_START;
    }
    return validate_border(out);
}

/* ---- the .bil blob ------------------------------------------------------ */

static uint16_t read_be16(const uint8_t *p)
{
    return (uint16_t)(((uint16_t)p[0] << 8) | p[1]);
}

static void write_be16(uint8_t *p, uint16_t value)
{
    p[0] = (uint8_t)(value >> 8);
    p[1] = (uint8_t)(value & 0xff);
}

LevelResult level_load_blob(const uint8_t *data, size_t len, Level *out)
{
    static const uint8_t magic[LEVEL_BLOB_MAGIC_BYTES] = {
        LEVEL_BLOB_MAGIC_0, LEVEL_BLOB_MAGIC_1, LEVEL_BLOB_MAGIC_2, LEVEL_BLOB_MAGIC_3
    };
    size_t grid_bytes;
    size_t needed;
    size_t i;

    if (len < LEVEL_BLOB_HEADER_BYTES) {
        return LEVEL_ERR_SIZE;
    }
    for (i = 0; i < LEVEL_BLOB_MAGIC_BYTES; ++i) {
        if (data[i] != magic[i]) {
            return LEVEL_ERR_MAGIC;
        }
    }

    level_defaults(out);
    for (i = 0; i < LEVEL_NAME_LEN; ++i) {
        out->name[i] = (char)data[4 + i];
    }
    out->name[LEVEL_NAME_LEN] = '\0';
    out->width              = data[20];
    out->height             = data[21];
    out->sector_index       = data[22];
    out->palette_variant    = data[23];
    out->texture_set        = data[24];
    out->start_cell_x       = data[26];
    out->start_cell_y       = data[27];
    out->start_facing_brads = read_be16(data + 28);
    out->trace_base_rate    = read_be16(data + 30);
    out->trace_start        = data[32];
    out->trace_carry_cap    = data[33];
    out->par_ticks          = read_be16(data + 34);
    out->entity_count       = read_be16(data + 36);

    if (out->width == 0 || out->height == 0
        || out->width > MAP_MAX_DIM || out->height > MAP_MAX_DIM) {
        return LEVEL_ERR_DIMENSIONS;
    }
    if (out->entity_count > LEVEL_MAX_ENTITIES) {
        return LEVEL_ERR_TOO_MANY;
    }
    grid_bytes = (size_t)out->width * out->height;
    needed = LEVEL_BLOB_HEADER_BYTES + grid_bytes
           + (size_t)out->entity_count * LEVEL_BLOB_ENTITY_BYTES;
    if (len < needed) {
        return LEVEL_ERR_SIZE;
    }

    for (i = 0; i < grid_bytes; ++i) {
        uint8_t value = data[LEVEL_BLOB_HEADER_BYTES + i];

        if (value >= CELL_RESERVED_BASE) {
            return LEVEL_ERR_RESERVED;
        }
        out->cells[i] = value;
    }
    for (i = 0; i < out->entity_count; ++i) {
        const uint8_t *rec = data + LEVEL_BLOB_HEADER_BYTES + grid_bytes
                           + i * LEVEL_BLOB_ENTITY_BYTES;

        out->entities[i].type   = rec[0];
        out->entities[i].cell_x = rec[1];
        out->entities[i].cell_y = rec[2];
        out->entities[i].facing = rec[3];
        out->entities[i].extra  = rec[4];
    }
    return validate_border(out);
}

size_t level_write_blob(const Level *level, uint8_t *out, size_t capacity)
{
    static const uint8_t magic[LEVEL_BLOB_MAGIC_BYTES] = {
        LEVEL_BLOB_MAGIC_0, LEVEL_BLOB_MAGIC_1, LEVEL_BLOB_MAGIC_2, LEVEL_BLOB_MAGIC_3
    };
    size_t grid_bytes = (size_t)level->width * level->height;
    size_t total = level_blob_size(level);
    size_t i;

    if (capacity < total) {
        return 0;
    }
    for (i = 0; i < LEVEL_BLOB_MAGIC_BYTES; ++i) {
        out[i] = magic[i];
    }
    for (i = 0; i < LEVEL_NAME_LEN; ++i) {
        out[4 + i] = (uint8_t)level->name[i];
        if (level->name[i] == '\0') {
            break;
        }
    }
    for (; i < LEVEL_NAME_LEN; ++i) {
        out[4 + i] = 0;
    }
    out[20] = level->width;
    out[21] = level->height;
    out[22] = level->sector_index;
    out[23] = level->palette_variant;
    out[24] = level->texture_set;
    out[25] = 0;
    out[26] = level->start_cell_x;
    out[27] = level->start_cell_y;
    write_be16(out + 28, level->start_facing_brads);
    write_be16(out + 30, level->trace_base_rate);
    out[32] = level->trace_start;
    out[33] = level->trace_carry_cap;
    write_be16(out + 34, level->par_ticks);
    write_be16(out + 36, level->entity_count);

    for (i = 0; i < grid_bytes; ++i) {
        out[LEVEL_BLOB_HEADER_BYTES + i] = level->cells[i];
    }
    for (i = 0; i < level->entity_count; ++i) {
        uint8_t *rec = out + LEVEL_BLOB_HEADER_BYTES + grid_bytes
                     + i * LEVEL_BLOB_ENTITY_BYTES;

        rec[0] = level->entities[i].type;
        rec[1] = level->entities[i].cell_x;
        rec[2] = level->entities[i].cell_y;
        rec[3] = level->entities[i].facing;
        rec[4] = level->entities[i].extra;
    }
    return total;
}
