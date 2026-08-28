/*
 * dumpassets.c - dump the engine's own asset arrays to flat big-endian blobs.
 *
 * WHY THIS EXISTS.  The Atari target loads its art from BLACKICE.PAK, while the
 * host reference build renders from the arrays compiled into
 * src/assets_data.c and src/tables.c.  atari/verify.py compares the
 * target's rendered pixels against the host's, so the two builds have to hold
 * BYTE-IDENTICAL art: any second copy of the art - hand-maintained, re-exported,
 * re-quantised - is a divergence waiting to happen, and it would surface as a
 * pixel diff nobody can attribute.
 *
 * So the PAK is GENERATED from the engine's arrays rather than authored beside
 * them.  This program is the extractor: it is built for the host, linked against
 * the same src/assets_data.c and src/tables.c the host renderer uses, and
 * writes what those arrays actually contain.  atari/mkpak.py then packs the
 * dumps.  There is exactly one source of truth and it is the C.
 *
 * Every multi-byte field is written BIG-ENDIAN, one byte at a time, because the
 * 68000 reads these blobs with word moves and the host's own endianness must not
 * reach the file.
 *
 *   usage: dumpassets <outdir>
 */
#include <stdio.h>
#include <stdint.h>

#include "render.h"
#include "sprite.h"

/* ---- output files ------------------------------------------------------- */

#define WALLTEX_FILE_NAME   "walltex.bin"
#define SPRTEX_FILE_NAME    "sprtex.bin"
#define PALETTE_FILE_NAME   "palette.bin"

#define OUTPUT_PATH_BYTES   1024

/* ---- blob layout constants ---------------------------------------------- */

/* Slot 0 is the far-fill sentinel, so the table is one longer than the max id. */
#define WALL_SLOT_COUNT     (WALL_TEXTURE_MAX + 1)
#define WALL_SLOT_ABSENT    0
#define WALL_SLOT_PRESENT   1

/* SpriteSpan is a { first, last } pair per texture column. */
#define SPRITE_SPAN_BYTES   (2 * TEX_DIM)

/* asset_of_type[] entry for an entity type that is never drawn. */
#define ASSET_INDEX_NONE    255

#define RGB_CHANNELS        3

/* ---- byte-level output --------------------------------------------------- */

/*
 * The writers below do not test each fputc/fwrite.  A short write means the dump
 * is unusable however few bytes were lost, so one ferror() sweep in
 * close_output() carries every failure and the write paths stay branch-free.
 */
static void put_u8(FILE *out, unsigned value)
{
    fputc((int)(value & 0xffu), out);
}

static void put_be16(FILE *out, unsigned value)
{
    fputc((int)((value >> 8) & 0xffu), out);
    fputc((int)(value & 0xffu), out);
}

static FILE *open_output(const char *dir, const char *file_name, char *path, size_t path_bytes)
{
    FILE *out;
    int length = snprintf(path, path_bytes, "%s/%s", dir, file_name);

    if (length < 0 || (size_t)length >= path_bytes) {
        fprintf(stderr, "dumpassets: output path for %s does not fit %zu bytes\n", file_name, path_bytes);
        return NULL;
    }
    out = fopen(path, "wb");
    if (out == NULL) {
        fprintf(stderr, "dumpassets: cannot open %s for writing\n", path);
    }
    return out;
}

/* Close `out` and return the bytes written, or -1 if anything went wrong. */
static long close_output(FILE *out, const char *path)
{
    long written = ftell(out);
    int failed = ferror(out);

    if (fclose(out) != 0 || failed || written < 0) {
        fprintf(stderr, "dumpassets: writing %s failed\n", path);
        return -1;
    }
    return written;
}

/* ---- walltex.bin --------------------------------------------------------- */

/*
 * u16 slot_count, u8 present[slot_count], then TEX_SIZE texels for each present
 * slot in ascending index order.  The presence bitmap rather than an offset
 * table: slots are few and fixed, and the engine only ever asks "is id N a
 * texture?" and "where is it?", both of which a prefix count answers.
 */
static long dump_wall_textures(const char *dir, const char *file_name)
{
    char path[OUTPUT_PATH_BYTES];
    FILE *out = open_output(dir, file_name, path, sizeof path);
    int slot;

    if (out == NULL) {
        return -1;
    }
    put_be16(out, WALL_SLOT_COUNT);
    for (slot = 0; slot < WALL_SLOT_COUNT; ++slot) {
        put_u8(out, g_wall_textures[slot] != NULL ? WALL_SLOT_PRESENT : WALL_SLOT_ABSENT);
    }
    for (slot = 0; slot < WALL_SLOT_COUNT; ++slot) {
        if (g_wall_textures[slot] != NULL) {
            fwrite(g_wall_textures[slot], 1, TEX_SIZE, out);
        }
    }
    return close_output(out, path);
}

/* ---- sprtex.bin ---------------------------------------------------------- */

/*
 * Several entity types share one SpriteAsset, so the blob stores each asset once
 * and gives every type an index into that table.  Assets are numbered by first
 * appearance while walking g_entity_sprites, deduplicated by POINTER IDENTITY -
 * the same rule the engine's own table expresses.
 *
 * Returns the number of distinct assets and fills `asset_of_type`.
 */
static unsigned collect_sprite_assets(const SpriteAsset *assets[ENT_TYPE_COUNT],
                                      uint8_t asset_of_type[ENT_TYPE_COUNT])
{
    unsigned count = 0;
    int type;

    for (type = 0; type < ENT_TYPE_COUNT; ++type) {
        const SpriteAsset *asset = g_entity_sprites[type];
        unsigned index;

        if (asset == NULL) {
            asset_of_type[type] = ASSET_INDEX_NONE;
            continue;
        }
        for (index = 0; index < count; ++index) {
            if (assets[index] == asset) {
                break;
            }
        }
        if (index == count) {
            assets[count++] = asset;
        }
        asset_of_type[type] = (uint8_t)index;
    }
    return count;
}

static void put_sprite_asset(FILE *out, const SpriteAsset *asset)
{
    int column;

    for (column = 0; column < TEX_DIM; ++column) {
        put_u8(out, asset->spans[column].first);
        put_u8(out, asset->spans[column].last);
    }
    fwrite(asset->texels, 1, TEX_SIZE, out);
}

static long dump_sprites(const char *dir, const char *file_name)
{
    char path[OUTPUT_PATH_BYTES];
    const SpriteAsset *assets[ENT_TYPE_COUNT];
    uint8_t asset_of_type[ENT_TYPE_COUNT];
    unsigned asset_count = collect_sprite_assets(assets, asset_of_type);
    FILE *out = open_output(dir, file_name, path, sizeof path);
    unsigned index;
    int type;

    if (out == NULL) {
        return -1;
    }
    put_be16(out, asset_count);
    put_be16(out, ENT_TYPE_COUNT);
    for (type = 0; type < ENT_TYPE_COUNT; ++type) {
        put_u8(out, asset_of_type[type]);
    }
    /* Pad so the records start even: the 68000 reads the texels with word moves. */
    if (ENT_TYPE_COUNT % 2 != 0) {
        put_u8(out, 0);
    }
    for (index = 0; index < asset_count; ++index) {
        put_sprite_asset(out, assets[index]);
    }
    return close_output(out, path);
}

/* ---- palette.bin -----------------------------------------------------------
 * The shade LUT is NOT dumped: the target builds its shade tables from g_shade_lut linked out of
 * src/tables.c, exactly as the host reference does, so there is nothing for an archive copy to be
 * checked against and a dump nothing reads is a pipeline stage that rots. */

/*
 * 8-bit RGB triples, not the STE colour words: this is what the host's PNG
 * writer uses, and mkpak.py encodes the hardware words from it.  Keeping the
 * 8-bit form here means the two builds compare the same numbers.
 */
static long dump_palette(const char *dir, const char *file_name)
{
    char path[OUTPUT_PATH_BYTES];
    FILE *out = open_output(dir, file_name, path, sizeof path);

    if (out == NULL) {
        return -1;
    }
    fwrite(g_palette_rgb, RGB_CHANNELS, PALETTE_SIZE, out);
    return close_output(out, path);
}

/* ---- driver -------------------------------------------------------------- */

typedef long (*DumpFn)(const char *dir, const char *file_name);

typedef struct {
    const char *file_name;
    DumpFn      dump;
} DumpJob;

static const DumpJob DUMP_JOBS[] = {
    { WALLTEX_FILE_NAME, dump_wall_textures },
    { SPRTEX_FILE_NAME,  dump_sprites },
    { PALETTE_FILE_NAME, dump_palette },
};

#define DUMP_JOB_COUNT (sizeof DUMP_JOBS / sizeof DUMP_JOBS[0])

int main(int argc, char **argv)
{
    size_t job;

    if (argc != 2) {
        fprintf(stderr, "usage: %s <outdir>\n", argv[0]);
        return 2;
    }
    for (job = 0; job < DUMP_JOB_COUNT; ++job) {
        long written = DUMP_JOBS[job].dump(argv[1], DUMP_JOBS[job].file_name);

        if (written < 0) {
            return 1;
        }
        printf("%-12s %ld bytes\n", DUMP_JOBS[job].file_name, written);
    }
    return 0;
}
