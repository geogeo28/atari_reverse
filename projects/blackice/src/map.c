/*
 * map.c - cell classification, the door table and the blocking bitmap.
 */
#include "map.h"

uint8_t map_cell_texture(uint8_t cell_value)
{
    if (CELL_IS_WALL(cell_value)) {
        return cell_value;
    }
    if (CELL_IS_DOOR(cell_value)) {
        /* Plain and exit gates read as infrastructure; everything a token or
         * the trace meter controls reads as locked. */
        if (cell_value == DOOR_PLAIN || cell_value == DOOR_SECTOR_EXIT) {
            return TEX_GATE_PANEL;
        }
        return TEX_LOCKED_PANEL;
    }
    return 0;
}

int door_variant_is_fixed(uint8_t variant)
{
    /*
     * A corrupted door is frozen part-open forever; a sealed gate only ever
     * opens as the 100%-trace exfil, which the sim layer above drives; and a
     * sector exit is an arch that ENDS the level on contact rather than a leaf
     * that travels - opening it would unblock a border cell and let the DDA,
     * which has no bounds test, walk out of the map.
     *
     * HOOK for the game layer: game_touch_door returns 0 for a sector exit, so
     * the "walking into `>` finishes the sector" rule is driven from the tick
     * above (the bumped cell is reported to it), not from the door table.
     */
    return variant == DOOR_CORRUPTED || variant == DOOR_SEALED
        || variant == DOOR_SECTOR_EXIT;
}

int door_variant_is_locked(uint8_t variant)
{
    return variant == DOOR_LOCK_ALPHA || variant == DOOR_LOCK_BETA
        || variant == DOOR_LOCK_GAMMA;
}

void map_build_blocking(const MapGrid *grid, const Door *doors, uint16_t door_count,
                        MapBlocking *blocking)
{
    uint16_t cells = (uint16_t)grid->width * grid->height;
    uint16_t i;

    for (i = 0; i < MAP_BITMAP_BYTES; ++i) {
        blocking->solid[i] = 0;
    }
    for (i = 0; i < cells; ++i) {
        if (grid->cells[i] != CELL_EMPTY) {
            map_set_blocking(blocking, i, 1);
        }
    }
    /* A door stops bodies in every state but OPEN. */
    for (i = 0; i < door_count; ++i) {
        map_set_blocking(blocking, doors[i].cell, !DOOR_IS_PASSABLE(doors[i]));
    }
}

uint16_t map_collect_doors(const MapGrid *grid, Door *doors)
{
    uint16_t count = 0;
    uint16_t index = 0;
    uint8_t x;
    uint8_t y;

    /* x and y are walked alongside the index rather than divided out of it:
     * this is the only place a door's cell coordinates are ever computed. */
    for (y = 0; y < grid->height; ++y) {
        for (x = 0; x < grid->width; ++x, ++index) {
            uint8_t value = grid->cells[index];

            if (!CELL_IS_DOOR(value) || count >= DOOR_MAX_COUNT) {
                continue;
            }
            doors[count].cell = index;
            doors[count].cell_x = x;
            doors[count].cell_y = y;
            doors[count].variant = value;
            doors[count].state = DOOR_STATE_CLOSED;
            doors[count].timer = 0;
            ++count;
        }
    }
    return count;
}

void map_build_door_index(const MapGrid *grid, const Door *doors, uint16_t door_count,
                          uint8_t *door_of_cell)
{
    uint16_t cells = (uint16_t)grid->width * grid->height;
    uint16_t i;

    for (i = 0; i < cells; ++i) {
        door_of_cell[i] = DOOR_NONE;
    }
    for (i = 0; i < door_count; ++i) {
        door_of_cell[doors[i].cell] = (uint8_t)i;
    }
}
