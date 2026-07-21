/* assets.h — the game's two data files, loaded and unpacked into one arena.
 *
 * BuggyBoy ships its assets in `COURSES.DAT` (the five legs) and `GRAPHICS.GRA` (every sprite,
 * screen and road texture, RLE-compressed). The remaster reads both **unmodified** at boot, so the
 * original data files remain the source of truth — there is no baked asset blob.
 *
 * The arena's internal offsets are NOT ours to choose. Both files address themselves: a course
 * record's sprite pointer is a byte offset into the graphics region, and the decompressor's phases
 * are defined in terms of the same fixed sub-buffer spacing (the RLE output lands exactly one
 * sprite-table span below the graphics base, and the de-interleave bounces through it). So the
 * layout below mirrors the original's Malloc block verbatim, and `test/test_assets.py` pins the
 * unpacked arena byte-for-byte against recreate's verified `g_unpack_graphics`.
 *
 * What this module does NOT own: the tables that live in the original program's own data segment
 * (fonts, colour pairs, perspective tables, the object jump table). Those are program constants,
 * not asset-file content, and are modelled separately.
 *
 * Use:
 *     static uint8_t block[RM_ARENA_BYTES];
 *     RmArena arena;
 *     rm_arena_init(&arena, block);
 *     read_file("COURSES.DAT",  arena.course,                  RM_COURSE_FILE_BYTES);
 *     read_file("GRAPHICS.GRA", arena.gfx + RM_GFX_LOAD_OFF,   RM_GFX_FILE_MAX);
 *     rm_assets_unpack(&arena);
 *
 * `rm_assets_unpack` does no I/O: the caller supplies the bytes (GEMDOS Fread on the ST, a plain
 * buffer poke in the host tests), which keeps this file free of any platform seam.
 */
#ifndef RM_ASSETS_H
#define RM_ASSETS_H

#include <stdint.h>

/* ---- arena layout (mirrors main @0x10100's Malloc + buffer-base setup) ---------------------- */
#define RM_ARENA_BYTES      0x5ee08   /* the original's Malloc size; every region below fits inside */
#define RM_COURSE_OFF       0x00000   /* COURSES.DAT image           (the original's `mem_base`) */
#define RM_TABLES_OFF       0x01900   /* course tables + leg streams (the original's `buf_a`) */
#define RM_SCRATCH_OFF      0x0f660   /* unpack scratch -> sprite shift tables (`buf_b`) */
#define RM_GFX_OFF          0x1c660   /* unpacked graphics arena     (the original's `buf_c`) */
#define RM_AUX_OFF          0x57000   /* header stash                (the original's `buf_aux`) */

/* ---- the two files ------------------------------------------------------------------------- */
#define RM_COURSE_FILE_BYTES 0xf660   /* COURSES.DAT is read whole; this is exactly its size */
#define RM_GFX_LOAD_OFF      0xc350   /* GRAPHICS.GRA is read to gfx + this, ahead of the decode */
#define RM_GFX_FILE_MAX      0x3f500  /* read count: comfortably >= the file, so it lands whole */

/* The arena and its named regions. All are raw ST-format bytes (big-endian, plane-interleaved):
 * read them through st.h's accessors, never as native types. */
typedef struct {
    uint8_t *base;      /* the whole block: RM_ARENA_BYTES */
    uint8_t *course;    /* COURSES.DAT, verbatim */
    uint8_t *tables;    /* course tables + the per-leg record streams */
    uint8_t *scratch;   /* unpack scratch; holds the sprite pre-shift tables afterwards */
    uint8_t *gfx;       /* unpacked graphics: screens, sprites, road texture */
    uint8_t *aux;       /* stashed graphics header (the sprite-shift source groups) */
} RmArena;

/* Point the region pointers at `block`, which the caller owns and must be RM_ARENA_BYTES long. */
void rm_arena_init(RmArena *arena, uint8_t *block);

/* Decompress the loaded GRAPHICS.GRA in place: RLE-decode, de-interleave the screens, compact,
 * and build the sprite pre-shift tables. COURSES.DAT needs no unpacking — it is used as loaded. */
void rm_assets_unpack(RmArena *arena);

#endif /* RM_ASSETS_H */
