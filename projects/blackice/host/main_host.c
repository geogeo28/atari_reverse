/*
 * main_host.c - the host driver: load a level, run an input script, dump
 *               frames as PNG and per-frame hashes.
 *
 * This is the only executable in the project that touches a file system, and
 * it exists so the pytest suite can drive the portable core exactly the way the
 * Atari build will: fixed timestep, scripted input, deterministic output.
 *
 *   blackice_host --level levels/level1.txt [--script s.txt] [--frames N]
 *                 [--seed N] [--throttle 0|1|2] [--out DIR] [--png all|none|LIST]
 *                 [--hashes PATH]
 *
 * An input script is one line per run of ticks:
 *     <ticks> <token> [<token> ...]
 * with '-' meaning no input.  Lines starting with '#' are comments.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "c2p.h"
#include "game.h"
#include "level.h"
#include "render.h"
#include "render_png.h"

#define MAX_SCRIPT_TICKS    4096
#define MAX_FILE_BYTES      (256 * 1024)
#define PATH_BYTES          512
#define DEFAULT_FRAMES      100

static uint8_t g_file_buffer[MAX_FILE_BYTES];
static Level g_level;
static GameState g_state;
static RenderScratch g_scratch;
static uint8_t g_chunky[CHUNKY_BYTES];
static uint8_t g_planar[SCREEN_BYTES];
static uint16_t g_script[MAX_SCRIPT_TICKS];
static uint16_t g_script_ticks;

typedef struct {
    const char *name;
    uint16_t    bit;
} InputToken;

static const InputToken INPUT_TOKENS[] = {
    { "forward",    INPUT_FORWARD },
    { "back",       INPUT_BACK },
    { "turn_left",  INPUT_TURN_LEFT },
    { "turn_right", INPUT_TURN_RIGHT },
    { "strafe_left",  INPUT_STRAFE_LEFT },
    { "strafe_right", INPUT_STRAFE_RIGHT },
    { "use",        INPUT_USE },
    { "fire",       INPUT_FIRE },
    { "throttle",   INPUT_THROTTLE_NEXT },
};

#define INPUT_TOKEN_COUNT ((int)(sizeof(INPUT_TOKENS) / sizeof(INPUT_TOKENS[0])))

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

static int ends_with(const char *text, const char *suffix)
{
    size_t text_len = strlen(text);
    size_t suffix_len = strlen(suffix);

    return text_len >= suffix_len && strcmp(text + text_len - suffix_len, suffix) == 0;
}

static int load_level(const char *path)
{
    long len = read_file(path, g_file_buffer, sizeof(g_file_buffer));
    LevelResult result;

    if (len < 0) {
        fprintf(stderr, "cannot read level %s\n", path);
        return -1;
    }
    if (ends_with(path, ".bil")) {
        result = level_load_blob(g_file_buffer, (size_t)len, &g_level);
    } else {
        result = level_parse_text((const char *)g_file_buffer, (size_t)len, &g_level);
    }
    if (result != LEVEL_OK) {
        fprintf(stderr, "level %s rejected, LevelResult %d\n", path, (int)result);
        return -1;
    }
    return 0;
}

static uint16_t token_bit(const char *token)
{
    int i;

    for (i = 0; i < INPUT_TOKEN_COUNT; ++i) {
        if (strcmp(token, INPUT_TOKENS[i].name) == 0) {
            return INPUT_TOKENS[i].bit;
        }
    }
    fprintf(stderr, "unknown input token '%s'\n", token);
    return 0;
}

static int load_script(const char *path)
{
    FILE *file = fopen(path, "r");
    char line[256];

    g_script_ticks = 0;
    if (!file) {
        fprintf(stderr, "cannot read script %s\n", path);
        return -1;
    }
    while (fgets(line, sizeof(line), file)) {
        char *cursor = line;
        char *token;
        long repeat;
        uint16_t input = 0;

        if (*cursor == '#' || *cursor == '\n') {
            continue;
        }
        token = strtok(cursor, " \t\r\n");
        if (!token) {
            continue;
        }
        repeat = strtol(token, 0, 10);
        while ((token = strtok(0, " \t\r\n")) != 0) {
            if (strcmp(token, "-") != 0) {
                input |= token_bit(token);
            }
        }
        while (repeat-- > 0 && g_script_ticks < MAX_SCRIPT_TICKS) {
            g_script[g_script_ticks++] = input;
        }
    }
    fclose(file);
    return 0;
}

/* FNV-1a over the planar screen, so a frame can be compared without a PNG. */
static uint32_t screen_hash(const uint8_t *planar)
{
    uint32_t hash = 2166136261u;
    size_t i;

    for (i = 0; i < SCREEN_BYTES; ++i) {
        hash = (hash ^ planar[i]) * 16777619u;
    }
    return hash;
}

static int frame_wanted(const char *selection, uint32_t frame)
{
    const char *cursor = selection;

    if (strcmp(selection, "all") == 0) {
        return 1;
    }
    if (strcmp(selection, "none") == 0) {
        return 0;
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
    const char *script_path = 0;
    const char *out_dir = "host/out";
    const char *png_selection = "none";
    const char *hash_path = 0;
    uint32_t frames = DEFAULT_FRAMES;
    uint16_t seed = RNG_DEFAULT_SEED;
    int throttle = -1;
    FILE *hash_file = 0;
    uint32_t frame;
    int i;

    for (i = 1; i < argc; ++i) {
        const char *arg = argv[i];
        const char *value = (i + 1 < argc) ? argv[i + 1] : 0;

        if (strcmp(arg, "--level") == 0 && value) {
            level_path = argv[++i];
        } else if (strcmp(arg, "--script") == 0 && value) {
            script_path = argv[++i];
        } else if (strcmp(arg, "--frames") == 0 && value) {
            frames = (uint32_t)strtoul(argv[++i], 0, 10);
        } else if (strcmp(arg, "--seed") == 0 && value) {
            seed = (uint16_t)strtoul(argv[++i], 0, 10);
        } else if (strcmp(arg, "--throttle") == 0 && value) {
            throttle = (int)strtol(argv[++i], 0, 10);
        } else if (strcmp(arg, "--out") == 0 && value) {
            out_dir = argv[++i];
        } else if (strcmp(arg, "--png") == 0 && value) {
            png_selection = argv[++i];
        } else if (strcmp(arg, "--hashes") == 0 && value) {
            hash_path = argv[++i];
        } else {
            fprintf(stderr, "unknown argument %s\n", arg);
            return 2;
        }
    }
    if (!level_path) {
        fprintf(stderr, "usage: %s --level PATH [--script PATH] [--frames N]"
                        " [--seed N] [--throttle 0|1|2] [--out DIR]"
                        " [--png all|none|LIST] [--hashes PATH]\n", argv[0]);
        return 2;
    }

    tables_init();
    if (load_level(level_path) != 0) {
        return 1;
    }
    if (script_path && load_script(script_path) != 0) {
        return 1;
    }
    game_init(&g_state, &g_level, seed);
    if (throttle >= 0 && throttle < THROTTLE_MODE_COUNT) {
        g_state.throttle = (uint8_t)throttle;
    }
    if (hash_path) {
        hash_file = fopen(hash_path, "w");
        if (!hash_file) {
            fprintf(stderr, "cannot write hashes to %s\n", hash_path);
            return 1;
        }
    }

    for (frame = 0; frame < frames; ++frame) {
        uint16_t input = (frame < g_script_ticks) ? g_script[frame] : 0;

        game_step(&g_state, input);
        render_frame(&g_state, &g_scratch, g_chunky);
        c2p_window(g_chunky, render_columns(&g_state)->count, g_planar);

        if (hash_file) {
            fprintf(hash_file, "%u %08x %08x\n", frame,
                    game_state_hash(&g_state), screen_hash(g_planar));
        }
        if (frame_wanted(png_selection, frame)) {
            char path[PATH_BYTES];

            snprintf(path, sizeof(path), "%s/frame%04u.png", out_dir, frame);
            if (render_png_write(path, g_planar) != 0) {
                fprintf(stderr, "cannot write %s\n", path);
                if (hash_file) {
                    fclose(hash_file);
                }
                return 1;
            }
        }
    }
    if (hash_file) {
        fclose(hash_file);
    }
    return 0;
}
