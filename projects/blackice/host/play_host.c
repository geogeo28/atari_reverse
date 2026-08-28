/*
 * play_host.c - drive a level with the game layer live and look at the result.
 *
 * main_host.c replays a recorded input script and hashes what comes out; that
 * is the regression harness and it is deliberately blind.  This is the other
 * thing a host build is for: pointing the camera at an enemy, letting the sim
 * run, and printing what the game layer thinks is happening beside the pixels
 * it produced - so "the Watchdogs are coming and they die when shot" is
 * something a person can check rather than infer from a hash.
 *
 *   blackice_play --level levels/level1.txt [--frames N] [--out DIR]
 *                 [--at X,Y] [--face BRADS] [--fire] [--png LIST]
 *                 [--throttle 0|1|2]
 *
 * It prints one line per frame: the tick, the player's cell, integrity,
 * cycles, the trace meter, and a letter per live enemy naming its state.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "c2p.h"
#include "game.h"
#include "level.h"
#include "render.h"
#include "render_png.h"
#include "sim.h"

#define MAX_FILE_BYTES  (256 * 1024)
#define PATH_BYTES      512
#define DEFAULT_FRAMES  120

static uint8_t g_file_buffer[MAX_FILE_BYTES];
static Level g_level;
static GameState g_state;
static RenderScratch g_scratch;
static uint8_t g_chunky[CHUNKY_BYTES];
static uint8_t g_planar[SCREEN_BYTES];

/* One letter per state, so a frame's roster fits in a column of the log. */
static char state_letter(const EntityRuntime *body)
{
    switch (body->state) {
    case ENT_STATE_IDLE:      return '.';
    case ENT_STATE_ALERT:     return '!';
    case ENT_STATE_CHASE:     return '>';
    case ENT_STATE_ATTACK:    return '*';
    case ENT_STATE_FLEE:      return '<';
    case ENT_STATE_DEAD:      return 'x';
    case ENT_STATE_DESTROYED: return 'X';
    default:                  return '?';
    }
}

static void print_roster(void)
{
    uint16_t i;

    for (i = 0; i < g_level.entity_count; ++i) {
        const EntityRuntime *body = &g_state.entities[i];

        if (!entity_type_is_enemy(body->type)) {
            continue;
        }
        putchar(g_state.entity_alive[i] ? state_letter(body) : '_');
    }
}

static long read_file(const char *path, uint8_t *buffer, size_t capacity)
{
    FILE *file = fopen(path, "rb");
    size_t got;

    if (!file) {
        return -1;
    }
    got = fread(buffer, 1, capacity, file);
    fclose(file);
    return (long)got;
}

static int load_level(const char *path)
{
    long len = read_file(path, g_file_buffer, sizeof(g_file_buffer));
    LevelResult result;

    if (len < 0) {
        fprintf(stderr, "cannot read level %s\n", path);
        return -1;
    }
    result = level_parse_text((const char *)g_file_buffer, (size_t)len, &g_level);
    if (result != LEVEL_OK) {
        fprintf(stderr, "level %s rejected, LevelResult %d\n", path, (int)result);
        return -1;
    }
    return 0;
}

static int frame_wanted(const char *selection, uint32_t frame)
{
    const char *cursor = selection;

    if (strcmp(selection, "all") == 0) {
        return 1;
    }
    while (*cursor) {
        char *end;
        long value = strtol(cursor, &end, 10);

        if (end == cursor) {
            break;
        }
        if ((uint32_t)value == frame) {
            return 1;
        }
        cursor = (*end == ',') ? end + 1 : end;
    }
    return 0;
}

int main(int argc, char **argv)
{
    const char *level_path = 0;
    const char *out_dir = "host/out";
    const char *png_selection = "";
    uint32_t frames = DEFAULT_FRAMES;
    int place_x = -1;
    int place_y = -1;
    int facing_brads = -1;
    int fire = 0;
    int throttle = -1;
    uint32_t frame;
    int i;

    for (i = 1; i < argc; ++i) {
        const char *arg = argv[i];
        const char *value = (i + 1 < argc) ? argv[i + 1] : 0;

        if (strcmp(arg, "--level") == 0 && value) {
            level_path = argv[++i];
        } else if (strcmp(arg, "--frames") == 0 && value) {
            frames = (uint32_t)strtoul(argv[++i], 0, 10);
        } else if (strcmp(arg, "--out") == 0 && value) {
            out_dir = argv[++i];
        } else if (strcmp(arg, "--png") == 0 && value) {
            png_selection = argv[++i];
        } else if (strcmp(arg, "--at") == 0 && value) {
            sscanf(argv[++i], "%d,%d", &place_x, &place_y);
        } else if (strcmp(arg, "--face") == 0 && value) {
            facing_brads = (int)strtol(argv[++i], 0, 10);
        } else if (strcmp(arg, "--throttle") == 0 && value) {
            throttle = (int)strtol(argv[++i], 0, 10);
        } else if (strcmp(arg, "--fire") == 0) {
            fire = 1;
        } else {
            fprintf(stderr, "unknown argument %s\n", arg);
            return 2;
        }
    }
    if (!level_path) {
        fprintf(stderr, "usage: %s --level PATH [--frames N] [--out DIR] [--png LIST]"
                        " [--at X,Y] [--face BRADS] [--fire] [--throttle 0|1|2]\n", argv[0]);
        return 2;
    }

    tables_init();
    if (load_level(level_path) != 0) {
        return 1;
    }
    game_init(&g_state, &g_level, g_level.rng_seed);
    if (place_x >= 0 && place_y >= 0) {
        g_state.player.x = cell_centre((uint8_t)place_x);
        g_state.player.y = cell_centre((uint8_t)place_y);
    }
    if (facing_brads >= 0) {
        g_state.player.angle = ANGLE_FROM_BRADS((uint16_t)facing_brads);
    }
    if (throttle >= 0 && throttle < THROTTLE_MODE_COUNT) {
        g_state.throttle = (uint8_t)throttle;
    }

    for (frame = 0; frame < frames; ++frame) {
        game_step(&g_state, fire ? INPUT_FIRE : 0);
        render_frame(&g_state, &g_scratch, g_chunky);
        c2p_window(g_chunky, render_columns(&g_state)->count, g_planar);

        printf("%4u  cell %2d,%2d  hp %3d  cyc %3d  trace %5d  sprites %2u  roster ",
               frame,
               g_state.player.x >> CELL_SHIFT, g_state.player.y >> CELL_SHIFT,
               g_state.integrity, g_state.cycles, g_state.trace_milli,
               g_scratch.sprites.count);
        print_roster();
        putchar('\n');

        if (frame_wanted(png_selection, frame)) {
            char path[PATH_BYTES];

            snprintf(path, sizeof(path), "%s/play%04u.png", out_dir, frame);
            if (render_png_write(path, g_planar) != 0) {
                fprintf(stderr, "cannot write %s\n", path);
                return 1;
            }
        }
    }
    return 0;
}
