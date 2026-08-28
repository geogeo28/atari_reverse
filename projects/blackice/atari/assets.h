/* assets.h — the resource arena, the BiTables the asm indexes, and the BLACKICE.PAK loader.
 *
 * WHY THE PAK IS GENERATED FROM THE ENGINE'S OWN ARRAYS. atari/verify.py compares this build's
 * rendered pixels against the host reference (host/main_host.c), which draws from the arrays in
 * src/assets_placeholder.c. If the target's art came from anywhere else the comparison would be
 * measuring the art pipeline rather than the drawers, so atari/dumpassets.c dumps those very
 * arrays and atari/mkpak.py packs them. The palette, the HUD strip, the font and the compiled
 * levels ride along in the same archive.
 */
#ifndef BLACKICE_ASSETS_H
#define BLACKICE_ASSETS_H

#include <stdint.h>
#include "game_consts.h"
#include "level.h"
#include "plat.h"

/* ---- the tables render.S indexes ------------------------------------------------------------
 * ONE object, because the wall drawer's inner loop has exactly two address registers to spare:
 * %a4 on this structure for the per-column setup and %a5 on the column's own 16-word shade table.
 * The offsets are plat.h's TBL_* and are pinned by _Static_assert in main.c. */
typedef struct {
    /* Wall texture id -> its 64x64 word image, or NULL for a slot the art does not fill. A word
     * holds `palette_index * 2`, the byte offset into a shade table (see plat.h). */
    const uint16_t *tex[TBL_TEX_SLOTS];
    /* shade[level][parity][index] — the shade LUT and the pair scaling composed into one lookup. */
    uint16_t        shade[SHADE_LEVEL_COUNT][SHADE_PARITY_COUNT][SHADE_TABLE_ENTRIES];
} BiTables;

extern BiTables g_tables;

/* The 16 STE colour words the PAK carries, ready to store at PALETTE_ADDR. */
extern uint16_t g_ste_palette[PALETTE_PENS];

/* The static HUD backdrop: SCREEN_HUD_LINES scanlines of planar screen, blitted once per buffer. */
extern const uint8_t *g_hud_backdrop;
/* 96 glyphs of 8x8, one bitplane, ASCII 32..127; glyph c starts at (c - 32) * FONT_GLYPH_BYTES. */
extern const uint8_t *g_font;

#define FONT_FIRST_CHAR     32
#define FONT_GLYPH_COUNT    96
#define FONT_GLYPH_BYTES    8
#define FONT_GLYPH_WIDTH    8
#define HUD_BACKDROP_BYTES  (SCREEN_HUD_LINES * SCREEN_BYTES_PER_LINE)

/* ---- results ------------------------------------------------------------------------------- */

typedef enum {
    ASSETS_OK               = 0,
    ASSETS_ERR_OPEN         = 1,    /* Fopen refused the archive */
    ASSETS_ERR_READ         = 2,    /* a Fread or Fseek came back short */
    ASSETS_ERR_MAGIC        = 3,    /* not an STPK archive, or a version this loader cannot read */
    ASSETS_ERR_MISSING      = 4,    /* a member the game cannot start without is not in the archive */
    ASSETS_ERR_SCRATCH      = 5,    /* a member's packed image is larger than the read buffer */
    ASSETS_ERR_ARENA        = 6,    /* the resource arena ran out */
    ASSETS_ERR_DEPACK       = 7,    /* stepix_depack refused the stream */
    ASSETS_ERR_SHAPE        = 8,    /* a member is the wrong size or describes impossible contents */
    ASSETS_ERR_LEVEL        = 9     /* level_load_blob refused the .bil */
} AssetsResult;

/* Load the archive, expand every asset into the arena, and fill g_tables, g_ste_palette,
 * g_hud_backdrop, g_font, g_entity_sprites and `level`. Call once, before rendering. */
AssetsResult assets_load(const char *pak_path, Level *level);

/* Bytes of the arena in use, for the memory map in README.md and the boot report. */
unsigned long assets_arena_used(void);
unsigned long assets_arena_capacity(void);

#endif /* BLACKICE_ASSETS_H */
