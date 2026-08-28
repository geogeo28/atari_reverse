/* assets.c — read BLACKICE.PAK through GEMDOS and expand it into the resource arena.
 *
 * The archive layout is pipeline/README.md section 7 and the depacker is pipeline/depack.c, both
 * shipped as-is; nothing here reimplements either. What this file owns is the shape of the two
 * dumps atari/dumpassets.c writes (walltex / sprtex), the conversion of a byte-per-texel image
 * into the word form render.S reads, and the shade tables that fold the engine's remap and the
 * chunky buffer's pair scaling into one 16-entry lookup.
 *
 * EVERY MULTI-BYTE FIELD IS READ BYTE BY BYTE. The 68000 is big-endian like the archive, so a
 * cast would work — but a cast would also take an address error the day a directory entry lands
 * on an odd offset, and the archive's alignment is the packer's promise rather than this loader's
 * to rely on.
 */
#include "assets.h"

#include "depack.h"
#include "mem.h"
#include "render.h"
#include "sprite.h"
#include "tos.h"

/* ---- the arena ------------------------------------------------------------------------------
 * A bump allocator growing from the bottom, because nothing resident is ever freed: the set is
 * loaded once and lives for the run. The TOP of the same block is a small stack of TEMPORARY
 * allocations — a member's packed bytes and its expanded byte-per-texel image — which exist only
 * while that member is being converted. One block serves both so the transient 60 KB does not
 * become 60 KB of permanent .bss.
 *
 * The capacity fits DESIGN 17.4's whole resident wall set (15 textures at TEX_WORD_BYTES each is
 * 122,880) alongside the largest temporary that coexists with it, plus the sprites, the HUD, the
 * font and one level. assets_load refuses rather than overruns if a future art drop outgrows it. */
#define ARENA_BYTES         (192 * 1024)

static uint8_t g_arena[ARENA_BYTES];
static unsigned long g_arena_used;          /* permanent blocks, from g_arena upward */
static unsigned long g_arena_temp_top;      /* temporaries, from g_arena + ARENA_BYTES downward */

/* ---- the objects the engine and the asm reach by name --------------------------------------- */

BiTables g_tables;
uint16_t g_ste_palette[PALETTE_PENS];
const uint8_t *g_hud_backdrop;
const uint8_t *g_font;

/* Defined here rather than linked from src/assets_placeholder.c: on the target the sprite images
 * live in the arena, and their `texels` pointer is the WORD form render.S reads (see plat.h).
 * src/sprite.c only ever copies that pointer into a RenderSprite, so the type is honest about
 * ownership even though the pointee is words. */
#define SPRITE_ASSET_MAX    8

static SpriteAsset g_sprite_assets[SPRITE_ASSET_MAX];
const SpriteAsset *g_entity_sprites[ENT_TYPE_COUNT];

/* src/level.c refuses a level that names wall art the build does not have, and this table is the
 * one place it looks. The target's textures are the word form render.S reads; the loader only
 * tests the pointer for NULL, so pointing it at the real image keeps the check honest without a
 * second copy of the presence map. */
const uint8_t *g_wall_textures[WALL_TEXTURE_MAX + 1];

/* ---- PAK directory --------------------------------------------------------------------------
 * pipeline/depack.h names the sizes; these are the field offsets inside one 24-byte entry. */
#define PAK_ENTRY_NAME      0
#define PAK_ENTRY_OFFSET    8
#define PAK_ENTRY_PACKED    12
#define PAK_ENTRY_RAW       16
#define PAK_ENTRY_METHOD    20
#define PAK_MAX_ENTRIES     32

static uint8_t g_directory[PAK_MAX_ENTRIES * PAK_ENTRY_BYTES];
static uint16_t g_entry_count;
static short g_pak_handle;

static uint16_t read_be16(const uint8_t *p)
{
    return (uint16_t)(((uint16_t)p[0] << 8) | p[1]);
}

static unsigned long read_be32(const uint8_t *p)
{
    return ((unsigned long)p[0] << 24) | ((unsigned long)p[1] << 16)
         | ((unsigned long)p[2] << 8) | (unsigned long)p[3];
}

/* Round up so every block starts even: the drawers read the arena with word and long moves. */
static unsigned long arena_round(unsigned long bytes)
{
    return (bytes + 1UL) & ~1UL;
}

static void *arena_alloc(unsigned long bytes)
{
    unsigned long aligned = arena_round(bytes);
    uint8_t *block;

    if (aligned > g_arena_temp_top - g_arena_used) {
        return 0;
    }
    block = g_arena + g_arena_used;
    g_arena_used += aligned;
    return block;
}

static uint8_t *arena_temp_alloc(unsigned long bytes)
{
    unsigned long aligned = arena_round(bytes);

    if (aligned > g_arena_temp_top - g_arena_used) {
        return 0;
    }
    g_arena_temp_top -= aligned;
    return g_arena + g_arena_temp_top;
}

static unsigned long arena_temp_mark(void)          { return g_arena_temp_top; }
static void arena_temp_reset(unsigned long mark)    { g_arena_temp_top = mark; }

unsigned long assets_arena_used(void)      { return g_arena_used; }
unsigned long assets_arena_capacity(void)  { return ARENA_BYTES; }

/* ---- reading one member ---------------------------------------------------------------------- */

static int name_matches(const uint8_t *entry, const char *name)
{
    int i;

    for (i = 0; i < PAK_NAME_BYTES; ++i) {
        char wanted = name[i] ? name[i] : '\0';

        if ((char)entry[PAK_ENTRY_NAME + i] != wanted) {
            return 0;
        }
        if (!wanted) {
            return 1;
        }
    }
    return 1;
}

static const uint8_t *find_entry(const char *name)
{
    uint16_t i;

    for (i = 0; i < g_entry_count; ++i) {
        const uint8_t *entry = g_directory + (unsigned long)i * PAK_ENTRY_BYTES;

        if (name_matches(entry, name)) {
            return entry;
        }
    }
    return 0;
}

/* The raw size the directory claims for a member, or 0 when it is not in the archive. Callers
 * need it before read_member so they can take a temporary of exactly that size. */
static unsigned long member_raw_size(const char *name)
{
    const uint8_t *entry = find_entry(name);

    return entry ? read_be32(entry + PAK_ENTRY_RAW) : 0;
}

/*
 * Read one member and expand it into `dst`, which must have room for `dst_capacity` bytes.
 *
 * The packed bytes go into a TEMPORARY of their own rather than into `dst`: a stored member would
 * otherwise be a memcpy onto itself, and an LZSS one would be a depack whose source and
 * destination overlap. The temporary is released before returning, so the peak arena usage while
 * a member is being converted is its packed image plus its raw image and nothing else.
 */
static AssetsResult read_member(const char *name, uint8_t *dst, unsigned long dst_capacity,
                                unsigned long *raw_out)
{
    const uint8_t *entry = find_entry(name);
    unsigned long mark = arena_temp_mark();
    unsigned long offset;
    unsigned long packed;
    unsigned long raw;
    uint16_t method;
    uint8_t *packed_image;
    AssetsResult result = ASSETS_OK;

    if (!entry) {
        return ASSETS_ERR_MISSING;
    }
    offset = read_be32(entry + PAK_ENTRY_OFFSET);
    packed = read_be32(entry + PAK_ENTRY_PACKED);
    raw = read_be32(entry + PAK_ENTRY_RAW);
    method = read_be16(entry + PAK_ENTRY_METHOD);
    /* BOTH lengths, not just `raw`: the stored path copies `packed` bytes and the depacker reads
     * them, so a directory entry claiming a small raw size and a large packed one would overrun
     * `dst` — and `dst` is sometimes an automatic array. pipeline/depack.h promises the LZSS path
     * cannot walk outside its buffers on a corrupt stream; this is the same promise for the other
     * path, and a truncated archive on a bad floppy is enough to need it. */
    if (raw > dst_capacity || packed > dst_capacity) {
        return ASSETS_ERR_SHAPE;
    }
    packed_image = arena_temp_alloc(packed);
    if (!packed_image) {
        return ASSETS_ERR_SCRATCH;
    }
    if (Fseek((long)offset, g_pak_handle, FSEEK_FROM_START) < 0
        || Fread(g_pak_handle, (long)packed, packed_image) != (long)packed) {
        result = ASSETS_ERR_READ;
    } else if (method == PAK_METHOD_STORED) {
        memcpy(dst, packed_image, packed);
    } else if (method == PAK_METHOD_LZSS) {
        if (stepix_depack(packed_image, packed, dst, raw) != STEPIX_DEPACK_OK) {
            result = ASSETS_ERR_DEPACK;
        }
    } else {
        result = ASSETS_ERR_SHAPE;
    }
    arena_temp_reset(mark);
    *raw_out = raw;
    return result;
}

/* Read a member into a temporary of exactly its raw size. The caller owns the temporary until it
 * resets the mark it took beforehand. */
static AssetsResult read_member_temp(const char *name, uint8_t **image, unsigned long *raw_out)
{
    unsigned long raw = member_raw_size(name);
    uint8_t *buffer;

    if (!raw) {
        return ASSETS_ERR_MISSING;
    }
    buffer = arena_temp_alloc(raw);
    if (!buffer) {
        return ASSETS_ERR_SCRATCH;
    }
    *image = buffer;
    return read_member(name, buffer, raw, raw_out);
}

/* ---- the byte -> word conversion -------------------------------------------------------------
 * A texel byte is a palette index; the word form render.S reads is that index DOUBLED, which is
 * the byte offset of its entry in a 16-word shade table. Masking to PALETTE_SIZE - 1 here is what
 * makes the drawers' lack of a per-pixel range check safe: whatever the archive contains, no
 * lookup this build performs can leave the table. */
static void expand_texels(const uint8_t *src, uint16_t *dst, unsigned long count)
{
    unsigned long i;

    for (i = 0; i < count; ++i) {
        dst[i] = (uint16_t)((src[i] & (PALETTE_SIZE - 1)) * 2);
    }
}

/* ---- the shade tables -------------------------------------------------------------------------
 * shade[level][parity][index] = g_shade_lut[level][index] scaled into the pair position that
 * parity owns. The wall drawer picks the row with `band + side` (include/render.h) and the sprite
 * drawer with the band alone (include/sprite.h); both then need nothing per pixel but this one
 * indexed read. */
static void build_shade_tables(void)
{
    int level;
    int index;

    for (level = 0; level < SHADE_LEVEL_COUNT; ++level) {
        for (index = 0; index < SHADE_TABLE_ENTRIES; ++index) {
            uint16_t shaded = g_shade_lut[level][index];

            g_tables.shade[level][0][index] = (uint16_t)(shaded * PAIR_EVEN_SCALE);
            g_tables.shade[level][1][index] = (uint16_t)(shaded * PAIR_ODD_SCALE);
        }
    }
}

/* ---- the members ------------------------------------------------------------------------------ */

/* walltex.bin: u16 slot_count, u8 present[slot_count], then TEX_SIZE bytes per present slot. */
#define WALLTEX_HEADER_BYTES    2

static AssetsResult load_wall_textures(void)
{
    unsigned long mark = arena_temp_mark();
    unsigned long raw;
    unsigned long cursor;
    uint8_t *image;
    uint16_t slots;
    uint16_t slot;
    AssetsResult result = read_member_temp("WALLTEX", &image, &raw);

    if (result != ASSETS_OK) {
        arena_temp_reset(mark);
        return result;
    }
    if (raw < WALLTEX_HEADER_BYTES) {
        arena_temp_reset(mark);
        return ASSETS_ERR_SHAPE;
    }
    slots = read_be16(image);
    /* The presence byte per slot is read below, so the member has to be long enough to hold them
     * before a single one is looked at — the per-texture guard further down comes too late. */
    if (slots > TBL_TEX_SLOTS || raw < WALLTEX_HEADER_BYTES + (unsigned long)slots) {
        arena_temp_reset(mark);
        return ASSETS_ERR_SHAPE;
    }
    cursor = WALLTEX_HEADER_BYTES + slots;
    for (slot = 0; slot < slots; ++slot) {
        uint16_t *words;

        if (!image[WALLTEX_HEADER_BYTES + slot]) {
            continue;
        }
        if (cursor + TEX_SIZE > raw) {
            result = ASSETS_ERR_SHAPE;
            break;
        }
        words = arena_alloc(TEX_WORD_BYTES);
        if (!words) {
            result = ASSETS_ERR_ARENA;
            break;
        }
        expand_texels(image + cursor, words, TEX_SIZE);
        g_tables.tex[slot] = words;
        g_wall_textures[slot] = (const uint8_t *)words;
        cursor += TEX_SIZE;
    }
    arena_temp_reset(mark);
    return result;
}

/* sprtex.bin: u16 asset_count, u16 type_count, u8 asset_of_type[type_count], pad to even, then per
 * asset a 2 * TEX_DIM span table followed by TEX_SIZE texels. */
#define SPRTEX_HEADER_BYTES     4
#define SPRITE_SPAN_BYTES       (2 * TEX_DIM)
#define SPRITE_RECORD_BYTES     (SPRITE_SPAN_BYTES + TEX_SIZE)
#define SPRITE_TYPE_NONE        255

static AssetsResult load_sprites(void)
{
    unsigned long mark = arena_temp_mark();
    unsigned long raw;
    unsigned long cursor;
    uint8_t *image;
    uint16_t assets;
    uint16_t types;
    uint16_t i;
    AssetsResult result = read_member_temp("SPRTEX", &image, &raw);

    if (result != ASSETS_OK) {
        arena_temp_reset(mark);
        return result;
    }
    if (raw < SPRTEX_HEADER_BYTES) {
        arena_temp_reset(mark);
        return ASSETS_ERR_SHAPE;
    }
    assets = read_be16(image);
    types = read_be16(image + 2);
    /* The type map is read after the records, so it is bounded here rather than there: a member
     * with no records at all would otherwise reach the map loop having checked nothing. */
    if (assets > SPRITE_ASSET_MAX || types != ENT_TYPE_COUNT
        || raw < SPRTEX_HEADER_BYTES + (unsigned long)types) {
        arena_temp_reset(mark);
        return ASSETS_ERR_SHAPE;
    }
    cursor = SPRTEX_HEADER_BYTES + types;
    cursor = (cursor + 1UL) & ~1UL;             /* the packer pads so the records start even */
    for (i = 0; i < assets; ++i) {
        uint8_t *spans;
        uint16_t *words;

        if (cursor + SPRITE_RECORD_BYTES > raw) {
            arena_temp_reset(mark);
            return ASSETS_ERR_SHAPE;
        }
        spans = arena_alloc(SPRITE_SPAN_BYTES);
        words = arena_alloc(TEX_WORD_BYTES);
        if (!spans || !words) {
            arena_temp_reset(mark);
            return ASSETS_ERR_ARENA;
        }
        memcpy(spans, image + cursor, SPRITE_SPAN_BYTES);
        expand_texels(image + cursor + SPRITE_SPAN_BYTES, words, TEX_SIZE);
        g_sprite_assets[i].spans = (const SpriteSpan *)spans;
        g_sprite_assets[i].texels = (const uint8_t *)words;
        cursor += SPRITE_RECORD_BYTES;
    }
    for (i = 0; i < types; ++i) {
        uint8_t which = image[SPRTEX_HEADER_BYTES + i];

        if (which == SPRITE_TYPE_NONE) {
            g_entity_sprites[i] = 0;
        } else if (which >= assets) {
            arena_temp_reset(mark);
            return ASSETS_ERR_SHAPE;
        } else {
            g_entity_sprites[i] = &g_sprite_assets[which];
        }
    }
    arena_temp_reset(mark);
    return ASSETS_OK;
}

#define PALETTE_MEMBER_BYTES    (PALETTE_PENS * 2)

static AssetsResult load_palette(void)
{
    uint8_t words[PALETTE_MEMBER_BYTES];
    unsigned long raw;
    int pen;
    AssetsResult result = read_member("PALETTE", words, PALETTE_MEMBER_BYTES, &raw);

    if (result != ASSETS_OK) {
        return result;
    }
    if (raw != PALETTE_MEMBER_BYTES) {
        return ASSETS_ERR_SHAPE;
    }
    for (pen = 0; pen < PALETTE_PENS; ++pen) {
        g_ste_palette[pen] = read_be16(words + pen * 2);
    }
    return ASSETS_OK;
}

static AssetsResult load_blob(const char *name, unsigned long expected, const uint8_t **out)
{
    unsigned long raw;
    uint8_t *block = arena_alloc(expected);
    AssetsResult result;

    if (!block) {
        return ASSETS_ERR_ARENA;
    }
    result = read_member(name, block, expected, &raw);
    if (result != ASSETS_OK) {
        return result;
    }
    if (raw != expected) {
        return ASSETS_ERR_SHAPE;
    }
    *out = block;
    return ASSETS_OK;
}

/* One .bil at a time is resident, which is DESIGN 17.4's rule for the level as well as for the
 * texture set: the blob is read into a temporary, parsed into the caller's Level, and released. */
static AssetsResult load_level(const char *name, Level *level)
{
    unsigned long mark = arena_temp_mark();
    unsigned long raw;
    uint8_t *blob;
    AssetsResult result = read_member_temp(name, &blob, &raw);

    if (result == ASSETS_OK && level_load_blob(blob, raw, level) != LEVEL_OK) {
        result = ASSETS_ERR_LEVEL;
    }
    arena_temp_reset(mark);
    return result;
}

/* ---- the archive -------------------------------------------------------------------------- */

#define PAK_HEADER_VERSION_OFF  4
#define PAK_HEADER_COUNT_OFF    6

static AssetsResult read_directory(void)
{
    uint8_t header[PAK_HEADER_BYTES];
    unsigned long directory_bytes;

    if (Fread(g_pak_handle, PAK_HEADER_BYTES, header) != PAK_HEADER_BYTES) {
        return ASSETS_ERR_READ;
    }
    if (header[0] != 'S' || header[1] != 'T' || header[2] != 'P' || header[3] != 'K') {
        return ASSETS_ERR_MAGIC;
    }
    if (read_be16(header + PAK_HEADER_VERSION_OFF) != PAK_FORMAT_VERSION) {
        return ASSETS_ERR_MAGIC;
    }
    g_entry_count = read_be16(header + PAK_HEADER_COUNT_OFF);
    if (g_entry_count > PAK_MAX_ENTRIES) {
        return ASSETS_ERR_SHAPE;
    }
    directory_bytes = (unsigned long)g_entry_count * PAK_ENTRY_BYTES;
    if (Fread(g_pak_handle, (long)directory_bytes, g_directory) != (long)directory_bytes) {
        return ASSETS_ERR_READ;
    }
    return ASSETS_OK;
}

/* The level the first playable starts on. DESIGN 18's ladder puts sector 1 first, and the archive
 * numbers its levels from 1 in the order tools/mklevel.py compiled them. */
#define LEVEL_MEMBER_FIRST      "LEVEL1"

AssetsResult assets_load(const char *pak_path, Level *level)
{
    long handle = Fopen(pak_path, FOPEN_READ);
    AssetsResult result;

    if (handle < 0) {
        return ASSETS_ERR_OPEN;
    }
    g_pak_handle = (short)handle;
    g_arena_temp_top = ARENA_BYTES;
    build_shade_tables();

    result = read_directory();
    if (result == ASSETS_OK) {
        result = load_palette();
    }
    if (result == ASSETS_OK) {
        result = load_wall_textures();
    }
    if (result == ASSETS_OK) {
        result = load_sprites();
    }
    if (result == ASSETS_OK) {
        result = load_blob("HUD", HUD_BACKDROP_BYTES, &g_hud_backdrop);
    }
    if (result == ASSETS_OK) {
        result = load_blob("FONT", FONT_GLYPH_COUNT * FONT_GLYPH_BYTES, &g_font);
    }
    if (result == ASSETS_OK) {
        result = load_level(LEVEL_MEMBER_FIRST, level);
    }
    Fclose(g_pak_handle);
    return result;
}
