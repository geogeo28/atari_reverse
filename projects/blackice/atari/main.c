/* main.c — the BLACK ICE platform layer: boot, the resource load, the frame, and the bench.
 *
 * Nothing here is a hot loop. Every per-pixel cost lives in render.S; this file decides WHAT the
 * asm is asked to draw, keeps the simulation on DESIGN 4.1's catch-up clock, and measures each
 * stage with the MFP's own timer so README.md's frame-time table is a measurement rather than an
 * estimate.
 *
 * THE FRAME, in the order it happens:
 *   sim       game_step, once per two vertical blanks, catching up if the frame ran long
 *   cast      render_cast + sprite_build_list + the band, all portable C from src/
 *   columns   bi_draw_columns  -> the chunky pair-word buffer
 *   sprites   bi_draw_sprites  -> the same buffer, read-modify-write over the walls
 *   fill      bi_fill          -> the void above and below the band, straight to the screen
 *   c2p       bi_c2p_high/low  -> the band, 160x80 chunky to 320x160 planar, doubled both ways
 *   hud       hud_draw         -> the live fields of the 40-line strip
 *   flip      the page swap, applied by the vertical blank
 *
 * WHY THE BAND. The wall drawer and the c2p only ever touch the rows some column or sprite
 * actually reaches; everything above and below is COLOUR_VOID and is written by a ten-register
 * MOVEM at 2.7 cycles a byte. ../spike/REPORT.md measured that as a 40-42% saving on the whole
 * frame — the largest single lever the feasibility spike found.
 */
#include "assets.h"
#include "hud.h"
#include "overlay.h"
#include "plat.h"
#include "tos.h"

#include "game.h"
#include "level.h"
#include "mem.h"
#include "render.h"
#include "sprite.h"
#include "trace.h"

#include "ym_music.h"
#include "blackice_song.h"
#include "dma_sfx.h"
#include "blackice_sfx_bank.h"
#include "blackice_sfx_ids.h"
#include "blackice_sfx_ids.h"

#ifdef BLACKICE_BENCH
#include "bench_script.h"
#endif

/* ---------------------------------------------------------------- the asm contracts ---------- */
/* plat.h restates include/render.h's and include/sprite.h's layouts for the assembler, which
 * cannot include them. These are the pins: a field that moves in include/ fails the build here
 * rather than showing up as a picture one word wide of the truth. */
_Static_assert(RENDER_H == PLAT_RENDER_H, "PLAT_RENDER_H");
_Static_assert(RENDER_COLUMNS_HIGH == PLAT_COLUMNS_HIGH, "PLAT_COLUMNS_HIGH");
_Static_assert(RENDER_COLUMNS_LOW == PLAT_COLUMNS_LOW, "PLAT_COLUMNS_LOW");
_Static_assert(TEX_DIM == PLAT_TEX_DIM, "PLAT_TEX_DIM");
_Static_assert(SHADE_LEVEL_COUNT == PLAT_SHADE_LEVELS, "PLAT_SHADE_LEVELS");
_Static_assert(WALL_TEXTURE_MAX + 1 == PLAT_WALL_TEX_SLOTS, "PLAT_WALL_TEX_SLOTS");
_Static_assert(SPRITE_TRANSPARENT == PLAT_SPRITE_TRANSPARENT, "PLAT_SPRITE_TRANSPARENT");
_Static_assert(SPRITE_MAX_VISIBLE == PLAT_SPRITE_MAX_VISIBLE, "PLAT_SPRITE_MAX_VISIBLE");
_Static_assert(SCREEN_BYTES_PER_LINE == PLAT_SCREEN_BYTES_PER_LINE, "PLAT_SCREEN_BYTES_PER_LINE");
_Static_assert(SCREEN_BYTES == PLAT_SCREEN_BYTES, "PLAT_SCREEN_BYTES");
_Static_assert(PALETTE_SIZE == PALETTE_PENS, "PALETTE_PENS");
/* render.S's sprite drawer spells src/sprite.c's `>> TEX_DIM_SHIFT` as its own shift, and the
 * shade tables are sized by SHADE_TABLE_ENTRIES while assets.c masks texels to PALETTE_SIZE - 1 —
 * the claim that no lookup can leave the table is only true while those two agree. */
_Static_assert(TEX_DIM_SHIFT == SPRITE_ROW_SHIFT, "SPRITE_ROW_SHIFT");
_Static_assert(PALETTE_SIZE == SHADE_TABLE_ENTRIES, "SHADE_TABLE_ENTRIES");
/* bi_fill writes FILL_CHUNK_BYTES per MOVEM and walks BACKWARD to its low limit, so every count it
 * is handed must be a whole number of them. Every region this file asks for is a whole number of
 * view rows, and this is the one line that says a view row still is. */
_Static_assert(VIEW_ROW_BYTES % FILL_CHUNK_BYTES == 0, "bi_fill's chunk does not divide a view row");
/* bi_fill's other precondition is an EVEN destination — it stores longwords — and the screens are
 * PLAT_SCREEN_ALIGN aligned at run time, which is stronger. This pins the alignment itself. */
_Static_assert(PLAT_SCREEN_ALIGN % 4 == 0, "the screen alignment does not satisfy bi_fill");

_Static_assert(__builtin_offsetof(RenderColumn, tex_id)   == COL_TEX_ID,   "COL_TEX_ID");
_Static_assert(__builtin_offsetof(RenderColumn, tex_col)  == COL_TEX_COL,  "COL_TEX_COL");
_Static_assert(__builtin_offsetof(RenderColumn, top)      == COL_TOP,      "COL_TOP");
_Static_assert(__builtin_offsetof(RenderColumn, rows)     == COL_ROWS,     "COL_ROWS");
_Static_assert(__builtin_offsetof(RenderColumn, tex_v)    == COL_TEX_V,    "COL_TEX_V");
_Static_assert(__builtin_offsetof(RenderColumn, tex_step) == COL_TEX_STEP, "COL_TEX_STEP");
_Static_assert(__builtin_offsetof(RenderColumn, band)     == COL_BAND,     "COL_BAND");
_Static_assert(__builtin_offsetof(RenderColumn, side)     == COL_SIDE,     "COL_SIDE");
_Static_assert(sizeof(RenderColumn) == COL_SIZEOF, "COL_SIZEOF");

_Static_assert(__builtin_offsetof(RenderSprite, texels)     == SPR_TEXELS,     "SPR_TEXELS");
_Static_assert(__builtin_offsetof(RenderSprite, spans)      == SPR_SPANS,      "SPR_SPANS");
_Static_assert(__builtin_offsetof(RenderSprite, left)       == SPR_LEFT,       "SPR_LEFT");
_Static_assert(__builtin_offsetof(RenderSprite, cols)       == SPR_COLS,       "SPR_COLS");
_Static_assert(__builtin_offsetof(RenderSprite, top)        == SPR_TOP,        "SPR_TOP");
_Static_assert(__builtin_offsetof(RenderSprite, rows)       == SPR_ROWS,       "SPR_ROWS");
_Static_assert(__builtin_offsetof(RenderSprite, tex_u)      == SPR_TEX_U,      "SPR_TEX_U");
_Static_assert(__builtin_offsetof(RenderSprite, tex_step_u) == SPR_TEX_STEP_U, "SPR_TEX_STEP_U");
_Static_assert(__builtin_offsetof(RenderSprite, tex_step_v) == SPR_TEX_STEP_V, "SPR_TEX_STEP_V");
_Static_assert(__builtin_offsetof(RenderSprite, dist)       == SPR_DIST,       "SPR_DIST");
_Static_assert(__builtin_offsetof(RenderSprite, band)       == SPR_BAND,       "SPR_BAND");
_Static_assert(sizeof(RenderSprite) == SPR_SIZEOF, "SPR_SIZEOF");

_Static_assert(__builtin_offsetof(BiTables, tex)   == TBL_TEX,   "TBL_TEX");
_Static_assert(__builtin_offsetof(BiTables, shade) == TBL_SHADE, "TBL_SHADE");
_Static_assert(sizeof(BiTables) == TBL_SIZEOF, "TBL_SIZEOF");

typedef struct {
    uint16_t           *chunky;         /* the band's first row, pair 0 */
    const RenderColumn *columns;
    const BiTables     *tables;
    int16_t             pairs;
    int16_t             band_top;
    int16_t             band_bottom;
    uint16_t            void_even;      /* COLOUR_VOID, pair-scaled: the ceiling and the floor */
    uint16_t            void_odd;
    uint16_t            far_even;       /* COLOUR_FAR_FILL, pair-scaled */
    uint16_t            far_odd;
} BiDrawJob;

_Static_assert(__builtin_offsetof(BiDrawJob, chunky)      == JOB_CHUNKY,      "JOB_CHUNKY");
_Static_assert(__builtin_offsetof(BiDrawJob, columns)     == JOB_COLUMNS,     "JOB_COLUMNS");
_Static_assert(__builtin_offsetof(BiDrawJob, tables)      == JOB_TABLES,      "JOB_TABLES");
_Static_assert(__builtin_offsetof(BiDrawJob, pairs)       == JOB_PAIRS,       "JOB_PAIRS");
_Static_assert(__builtin_offsetof(BiDrawJob, band_top)    == JOB_BAND_TOP,    "JOB_BAND_TOP");
_Static_assert(__builtin_offsetof(BiDrawJob, band_bottom) == JOB_BAND_BOTTOM, "JOB_BAND_BOTTOM");
_Static_assert(__builtin_offsetof(BiDrawJob, void_even)   == JOB_VOID_EVEN,   "JOB_VOID_EVEN");
_Static_assert(__builtin_offsetof(BiDrawJob, void_odd)    == JOB_VOID_ODD,    "JOB_VOID_ODD");
_Static_assert(__builtin_offsetof(BiDrawJob, far_even)    == JOB_FAR_EVEN,    "JOB_FAR_EVEN");
_Static_assert(__builtin_offsetof(BiDrawJob, far_odd)     == JOB_FAR_ODD,     "JOB_FAR_ODD");
_Static_assert(sizeof(BiDrawJob) == JOB_SIZEOF, "JOB_SIZEOF");

/*
 * Everything cast.S needs that does not change across a frame. The pointer fields are first so they
 * stay longword aligned; plat.h's CJOB_* are the offsets and the asserts below are the pin.
 */
typedef struct {
    RenderColumn   *columns;
    uint16_t       *wall_dist;
    const int16_t  *angle_table;
    const uint16_t *cos_table;
    const int16_t  *sin_table;
    const uint16_t *inv_cos_table;
    const uint8_t  *grid_cells;
    const uint8_t  *blocking;
    const Door     *doors;
    const uint8_t  *door_of_cell;
    const uint16_t *slice_height;
    const uint16_t *tex_step;
    const uint8_t  *cell_texture;
    uint16_t        count;
    uint16_t        player_angle;
    int16_t         pos_x;
    int16_t         pos_y;
    int16_t         max_trace;
    uint16_t        start_index;
    int16_t         map_x;
    int16_t         map_y;
    int16_t         grid_width;
    uint16_t        to_next_x_pos;
    uint16_t        to_next_x_neg;
    uint16_t        to_next_y_pos;
    uint16_t        to_next_y_neg;
    uint16_t        band_limit[BAND_COUNT - 1];
    uint8_t         band_last;
    uint8_t         pad;
} BiCastJob;

_Static_assert(__builtin_offsetof(BiCastJob, columns)       == CJOB_COLUMNS,       "CJOB_COLUMNS");
_Static_assert(__builtin_offsetof(BiCastJob, wall_dist)     == CJOB_WALL_DIST,     "CJOB_WALL_DIST");
_Static_assert(__builtin_offsetof(BiCastJob, angle_table)   == CJOB_ANGLE_TABLE,   "CJOB_ANGLE_TABLE");
_Static_assert(__builtin_offsetof(BiCastJob, cos_table)     == CJOB_COS_TABLE,     "CJOB_COS_TABLE");
_Static_assert(__builtin_offsetof(BiCastJob, sin_table)     == CJOB_SIN_TABLE,     "CJOB_SIN_TABLE");
_Static_assert(__builtin_offsetof(BiCastJob, inv_cos_table) == CJOB_INV_COS_TABLE, "CJOB_INV_COS_TABLE");
_Static_assert(__builtin_offsetof(BiCastJob, grid_cells)    == CJOB_GRID_CELLS,    "CJOB_GRID_CELLS");
_Static_assert(__builtin_offsetof(BiCastJob, blocking)      == CJOB_BLOCKING,      "CJOB_BLOCKING");
_Static_assert(__builtin_offsetof(BiCastJob, doors)         == CJOB_DOORS,         "CJOB_DOORS");
_Static_assert(__builtin_offsetof(BiCastJob, door_of_cell)  == CJOB_DOOR_OF_CELL,  "CJOB_DOOR_OF_CELL");
_Static_assert(__builtin_offsetof(BiCastJob, slice_height)  == CJOB_SLICE_HEIGHT,  "CJOB_SLICE_HEIGHT");
_Static_assert(__builtin_offsetof(BiCastJob, tex_step)      == CJOB_TEX_STEP,      "CJOB_TEX_STEP");
_Static_assert(__builtin_offsetof(BiCastJob, cell_texture)  == CJOB_CELL_TEXTURE,  "CJOB_CELL_TEXTURE");
_Static_assert(__builtin_offsetof(BiCastJob, count)         == CJOB_COUNT,         "CJOB_COUNT");
_Static_assert(__builtin_offsetof(BiCastJob, player_angle)  == CJOB_PLAYER_ANGLE,  "CJOB_PLAYER_ANGLE");
_Static_assert(__builtin_offsetof(BiCastJob, pos_x)         == CJOB_POS_X,         "CJOB_POS_X");
_Static_assert(__builtin_offsetof(BiCastJob, pos_y)         == CJOB_POS_Y,         "CJOB_POS_Y");
_Static_assert(__builtin_offsetof(BiCastJob, max_trace)     == CJOB_MAX_TRACE,     "CJOB_MAX_TRACE");
_Static_assert(__builtin_offsetof(BiCastJob, start_index)   == CJOB_START_INDEX,   "CJOB_START_INDEX");
_Static_assert(__builtin_offsetof(BiCastJob, map_x)         == CJOB_MAP_X,         "CJOB_MAP_X");
_Static_assert(__builtin_offsetof(BiCastJob, map_y)         == CJOB_MAP_Y,         "CJOB_MAP_Y");
_Static_assert(__builtin_offsetof(BiCastJob, grid_width)    == CJOB_GRID_WIDTH,    "CJOB_GRID_WIDTH");
_Static_assert(__builtin_offsetof(BiCastJob, to_next_x_pos) == CJOB_TO_NEXT_X_POS, "CJOB_TO_NEXT_X_POS");
_Static_assert(__builtin_offsetof(BiCastJob, to_next_y_neg) == CJOB_TO_NEXT_Y_NEG, "CJOB_TO_NEXT_Y_NEG");
_Static_assert(__builtin_offsetof(BiCastJob, band_limit)    == CJOB_BAND_LIMIT,    "CJOB_BAND_LIMIT");
_Static_assert(__builtin_offsetof(BiCastJob, band_last)     == CJOB_BAND_LAST,     "CJOB_BAND_LAST");
_Static_assert(sizeof(BiCastJob) == CJOB_SIZEOF, "CJOB_SIZEOF");

/* cast.S restates these from ../include/; a change there must fail the build, not the picture. */
_Static_assert(TRIG_INDEX_SHIFT == PLAT_TRIG_INDEX_SHIFT, "PLAT_TRIG_INDEX_SHIFT");
_Static_assert(TRIG_SHIFT == PLAT_TRIG_SHIFT, "PLAT_TRIG_SHIFT");
_Static_assert(TRIG_QUARTER_ENTRIES * 2 == PLAT_TRIG_QUARTER_BYTES, "PLAT_TRIG_QUARTER_BYTES");
_Static_assert(TRIG_INDEX_MASK * 2 == PLAT_TRIG_WRAP_BYTES, "PLAT_TRIG_WRAP_BYTES");
_Static_assert(CELL_SHIFT == PLAT_CELL_SHIFT, "PLAT_CELL_SHIFT");
_Static_assert(CELL_UNITS == PLAT_CELL_UNITS, "PLAT_CELL_UNITS");
_Static_assert(CELL_FRAC_MASK == PLAT_CELL_FRAC_MASK, "PLAT_CELL_FRAC_MASK");
_Static_assert(TEX_INDEX_MASK == PLAT_TEX_INDEX_MASK, "PLAT_TEX_INDEX_MASK");
_Static_assert(DIST_TABLE_MAX == PLAT_DIST_TABLE_MAX, "PLAT_DIST_TABLE_MAX");
_Static_assert(DELTA_DIST_NEVER == PLAT_DELTA_DIST_NEVER, "PLAT_DELTA_DIST_NEVER");
_Static_assert(DDA_BEYOND_TRACE == PLAT_DDA_BEYOND_TRACE, "PLAT_DDA_BEYOND_TRACE");
_Static_assert(WALL_DIST_NONE == PLAT_WALL_DIST_NONE, "PLAT_WALL_DIST_NONE");
_Static_assert(CELL_DOOR_BASE == PLAT_CELL_DOOR_BASE, "PLAT_CELL_DOOR_BASE");
_Static_assert(CELL_DOOR_MAX == PLAT_CELL_DOOR_MAX, "PLAT_CELL_DOOR_MAX");
_Static_assert(DOOR_NONE == PLAT_DOOR_NONE, "PLAT_DOOR_NONE");
_Static_assert(DOOR_STATE_OPEN == PLAT_DOOR_STATE_OPEN, "PLAT_DOOR_STATE_OPEN");
_Static_assert(sizeof(Door) == PLAT_DOOR_SIZEOF, "PLAT_DOOR_SIZEOF");
_Static_assert(__builtin_offsetof(Door, state) == PLAT_DOOR_STATE_OFF, "PLAT_DOOR_STATE_OFF");
_Static_assert(BAND_COUNT - 1 == PLAT_BAND_EDGES, "PLAT_BAND_EDGES");
_Static_assert(SIDE_NS == PLAT_SIDE_NS && SIDE_EW == PLAT_SIDE_EW, "PLAT_SIDE_*");
_Static_assert(CELL_UNITS / TEX_DIM == (1 << PLAT_TEXEL_SHIFT), "PLAT_TEXEL_SHIFT");

typedef struct {
    uint16_t           *chunky;         /* logical row 0, pair 0 */
    const RenderSprite *sprites;
    const uint16_t     *wall_dist;
    const BiTables     *tables;
    int16_t             count;
    int16_t             columns;
    int16_t             band_top;
    int16_t             band_bottom;
} BiSpriteJob;

_Static_assert(__builtin_offsetof(BiSpriteJob, chunky)      == SJOB_CHUNKY,      "SJOB_CHUNKY");
_Static_assert(__builtin_offsetof(BiSpriteJob, sprites)     == SJOB_SPRITES,     "SJOB_SPRITES");
_Static_assert(__builtin_offsetof(BiSpriteJob, wall_dist)   == SJOB_WALL_DIST,   "SJOB_WALL_DIST");
_Static_assert(__builtin_offsetof(BiSpriteJob, tables)      == SJOB_TABLES,      "SJOB_TABLES");
_Static_assert(__builtin_offsetof(BiSpriteJob, count)       == SJOB_COUNT,       "SJOB_COUNT");
_Static_assert(__builtin_offsetof(BiSpriteJob, columns)     == SJOB_COLUMNS,     "SJOB_COLUMNS");
_Static_assert(__builtin_offsetof(BiSpriteJob, band_top)    == SJOB_BAND_TOP,    "SJOB_BAND_TOP");
_Static_assert(__builtin_offsetof(BiSpriteJob, band_bottom) == SJOB_BAND_BOTTOM, "SJOB_BAND_BOTTOM");
_Static_assert(sizeof(BiSpriteJob) == SJOB_SIZEOF, "SJOB_SIZEOF");

/* ---------------------------------------------------------------- the world ------------------- */

unsigned long bi_c2p_table_high[C2P_POSITIONS_HIGH * C2P_PAIR_COUNT * 2];
/* row * CHUNKY_ROW_BYTES, for every row of the window. render.S's sprite drawer reads it instead of
 * multiplying: the pitch is a constant, so the eighty products are a table and not 70 cycles a
 * column. Filled once at boot. */
uint16_t bi_chunky_row_offset[RENDER_H];
unsigned long bi_c2p_table_low[C2P_POSITIONS_LOW * C2P_PAIR_COUNT * 2];
volatile uint8_t bi_joy_port1;

static Level g_level;
static GameState g_state;
/*
 * The authored entity list as the archive delivered it. FIXTURE_NEAR_SPRITES moves bodies to build
 * DESIGN 17.3's near-billboard frame, and it moves them in the LEVEL, because entities_init copies
 * the runtime table from there. Without this copy that edit outlived its own pass: the scripted
 * walk that ran after it collected different pickups from the host reference's, and every pixel of
 * atari/verify.py's comparison differed for a reason that had nothing to do with the drawers.
 */
static Entity g_level_entities_pristine[LEVEL_MAX_ENTITIES];
static RenderScratch g_scratch;
static uint16_t g_chunky[CHUNKY_WORDS];

/*
 * Two screens, 256-aligned. tos.ld caps .bss at SUBALIGN(4) — a symbol wanting 256 would push .bss
 * past the end of the emitted image and every .bss access on target would land at the wrong
 * address (its header is canonical for that fault). So the alignment is done at run time on a
 * buffer with one page of slack, and PLAT_SCREEN_BYTES is itself a whole number of 256-byte pages
 * (32,000 == 125 * 256), which is why the second screen needs no slack of its own.
 */
static uint8_t g_screen_store[2 * PLAT_SCREEN_BYTES + PLAT_SCREEN_ALIGN];
static uint8_t *g_screen[2];
static uint8_t *volatile g_screen_front;
static uint8_t *g_screen_back;
/* What the HUD has drawn in each buffer: the strip redraws only what changed, and the two buffers
 * change independently (hud.h). */
static HudState g_hud_shown[2];
static volatile int g_flip_pending;
static int g_vbl_installed;
static int g_music_ready;
/* The song's drum lane needs BOTH: a song the driver accepted and a DMA chip that took the
 * bank. On a plain ST the second is 0, dma_sfx refuses every call, and the YM kit's own noise
 * channel carries the drums (audio/ym_music.h). */
static int g_drums_ready;

static volatile unsigned long g_vbl_count;
static volatile uint8_t g_joy_sticky;   /* DESIGN 4.2: every joystick bit seen since the last read */

/* What the run saves and puts back. Leaving any of it changed is a machine the user has to reboot. */
static void *g_saved_ssp;
static void *g_saved_physbase;
static void *g_saved_logbase;
static short g_saved_rez;
static uint16_t g_saved_palette[PALETTE_PENS];
static uint8_t g_saved_conterm;
static void **g_joyvec_slot;
static void *g_saved_joyvec;
static void **g_vbl_slot;
static int g_vbl_vector_installed;
void *bi_vbl_chain;

/* ---------------------------------------------------------------- hardware -------------------- */

/*
 * A pointer the optimiser cannot fold. GCC 16 turns a copy between two addresses it knows at build
 * time into ONE address register:
 *      move.w (%a0)+,(d,%a0,%d0.l)          | d == destination - source
 * and on the 68000 the source is fetched and %a0 post-incremented BEFORE the destination's
 * effective address is calculated, so every element lands one slot too high. ../spike/REPORT.md
 * measured it on a ledger publish; this build MET IT ON THE PALETTE — the sixteen colour words
 * arrived at $ffff8242 upward, pen 0 kept EmuTOS's white and every colour on screen was one pen
 * out. `volatile` on the destination does NOT stop it, because the fold is a choice of addressing
 * mode and GCC still emits exactly the one store the source asked for; hiding the pointer's value
 * behind an empty asm constraint does.
 *
 * Everything in this file that copies between two fixed addresses goes through here.
 */
static void *opaque_pointer(void *address)
{
    __asm__("" : "+a"(address));
    return address;
}

static void set_palette(const uint16_t *words)
{
    volatile uint16_t *pen = opaque_pointer((void *)PALETTE_ADDR);
    int i;

    for (i = 0; i < PALETTE_PENS; ++i) {
        pen[i] = words[i];
    }
}

/* ---- the trace meter's palette variants (DESIGN 3, DESIGN 9) --------------------------------
 * DESIGN 9 makes the trace meter recolour the world, and DESIGN 3's variant invariant says exactly
 * how much of it: ONLY registers 1..5, the cyan ramp. Registers 0, 6..10 and 11..15 are identical
 * in every variant, which is what keeps the rim gate's 31.3 Y margin and the sprite transparency
 * key true across all four without re-running the harness.
 *
 * The archive ships one PALETTE member, so the variants are DERIVED here rather than shipped:
 *   DEGRADED  registers 1..5 remapped through g_shade_lut[1] — one rung darker, and no new colour
 *   CORRUPT   registers 1..5 take the MAGENTA ramp's values (6..10): the infrastructure itself
 *             reads hostile, and only the white rim still separates ICE from wall
 *   KERNEL    a blue-white wash: each cyan rung blended halfway to white
 *
 * KERNEL IS A STAND-IN. DESIGN 3 says the art pass authors that ramp under both gates and the
 * document "states the constraint and does not hand-author the hexes"; nothing has authored it yet,
 * so this blend fills the slot. It satisfies the invariant (it touches 1..5 and nothing else) and
 * it is the one variant here that is a platform invention rather than a document's instruction.
 */
#define PALETTE_VARIANT_COUNT   4
#define PALETTE_RAMP_FIRST      1       /* the cyan ramp, the only registers a variant may move */
#define PALETTE_RAMP_LAST       5
#define PALETTE_MAGENTA_OFFSET  5       /* register i's magenta twin is i + 5 (DESIGN 3's table) */

static uint16_t g_palette_variants[PALETTE_VARIANT_COUNT][PALETTE_PENS];

/* The STE keeps the ST's three bits where they were and bolted the fourth on as bit 3, where it is
 * the LEAST significant bit of the intensity — so a nibble is a ROTATION of the value and not a
 * widening. pipeline/README.md section 1 is canonical; hand-encoding gets it wrong in a way that
 * looks almost right. */
static uint8_t ste_intensity(uint8_t nibble)
{
    return (uint8_t)(((nibble & 7) << 1) | (nibble >> 3));
}

static uint16_t ste_nibble(uint8_t intensity)
{
    return (uint16_t)(((intensity >> 1) & 7) | ((intensity & 1) << 3));
}

#define STE_CHANNELS        3
#define STE_NIBBLE_MASK     0xf
#define STE_INTENSITY_MAX   15
#define STE_CHANNEL_BITS    4

/*
 * Mix two colour words channel by channel IN INTENSITY SPACE, `num` parts of `b` in `1 << shift`.
 * Intensity space and not nibble space because the STE's nibble is a ROTATION of the value (its
 * low bit is bit 3), so averaging the nibbles averages the wrong numbers.
 *
 * `shift` rather than a divisor: a divide by a runtime value is a call to libgcc's __udivsi3, which
 * the Makefile's gate refuses, and every caller here wants a power of two anyway.
 */
static uint16_t ste_blend(uint16_t a, uint16_t b, uint16_t num, unsigned shift)
{
    int16_t den = (int16_t)(1 << shift);
    uint16_t out = 0;
    int channel;

    for (channel = 0; channel < STE_CHANNELS; ++channel) {
        int at = channel * STE_CHANNEL_BITS;
        int16_t from = ste_intensity((uint8_t)((a >> at) & STE_NIBBLE_MASK));
        int16_t to = ste_intensity((uint8_t)((b >> at) & STE_NIBBLE_MASK));
        /* Both products are at most 15 * 32, so mul16 is the 68000's own muls.w: written in `int`
         * this was two calls to libgcc's __mulsi3 and the Makefile's gate refused the build. */
        int32_t mixed = mul16(from, (int16_t)(den - (int16_t)num)) + mul16(to, (int16_t)num);

        out |= (uint16_t)(ste_nibble((uint8_t)(mixed >> shift)) << at);
    }
    return out;
}

#define STE_HALF_SHIFT      1

/* Halfway towards full white: the flash, and the KERNEL variant's wash. */
static uint16_t ste_wash_to_white(uint16_t word)
{
    return ste_blend(word, 0x0fff, 1, STE_HALF_SHIFT);
}

static void build_palette_variants(void)
{
    int pen;
    int variant;

    for (variant = 0; variant < PALETTE_VARIANT_COUNT; ++variant) {
        for (pen = 0; pen < PALETTE_PENS; ++pen) {
            g_palette_variants[variant][pen] = g_ste_palette[pen];
        }
    }
    for (pen = PALETTE_RAMP_FIRST; pen <= PALETTE_RAMP_LAST; ++pen) {
        g_palette_variants[PALETTE_VARIANT_DEGRADED][pen] = g_ste_palette[g_shade_lut[1][pen]];
        g_palette_variants[PALETTE_VARIANT_CORRUPT][pen] =
            g_ste_palette[pen + PALETTE_MAGENTA_OFFSET];
        g_palette_variants[PALETTE_VARIANT_KERNEL][pen] = ste_wash_to_white(g_ste_palette[pen]);
    }
}

static void save_palette(uint16_t *words)
{
    const volatile uint16_t *pen = opaque_pointer((void *)PALETTE_ADDR);
    int i;

    for (i = 0; i < PALETTE_PENS; ++i) {
        words[i] = pen[i];
    }
}

/*
 * Point the shifter at `screen` — the hardware's three write-only bytes AND TOS's own `_v_bas_ad`,
 * and the second half is not optional.
 *
 * TOS's vertical blank reloads the shifter from `_v_bas_ad` on EVERY blank and then walks the queue
 * this program's flip runs from (os.S says why the flip is in the queue). At 4 to 8 frames a second
 * there are six to twelve blanks per rendered frame and only ONE of them carries a flip, so writing
 * the registers alone left TOS putting the boot buffer back on all the others — for most of every
 * frame the player would be watching the buffer being drawn into. Keeping `_v_bas_ad` in step makes
 * TOS's own reload write the same address we did.
 *
 * The STE's low byte is zero for us because both screens are 256-aligned. Supervisor only.
 */
static void set_video_base(uint8_t *screen)
{
    unsigned long address = (unsigned long)screen;

    *(volatile uint8_t **)V_BAS_AD_ADDR = screen;
    *(volatile uint8_t *)VIDEO_BASE_HIGH_ADDR = (uint8_t)(address >> 16);
    *(volatile uint8_t *)VIDEO_BASE_MID_ADDR = (uint8_t)(address >> 8);
    *(volatile uint8_t *)VIDEO_BASE_LOW_ADDR = 0;
}

/* ---------------------------------------------------------------- the vertical blank ---------- */

#define VBLS_PER_TICK   (50 / SIM_HZ)   /* DESIGN 4: one simulation tick per two PAL blanks */

void bi_vbl_tick(void)
{
    ++g_vbl_count;
    /* The flip first, so it lands as early in the blanking interval as the queue allows. */
    if (g_flip_pending) {
        set_video_base(g_screen_front);
        g_flip_pending = 0;
    }
    g_joy_sticky |= bi_joy_port1;
    if (g_music_ready) {
        /* THE ORDER AND THE TICK RATE ARE THE CONTRACT (audio/ym_music.h): the take is a
         * read-then-clear, so whoever ticks must take on the SAME blank. A taker that runs at the
         * simulation's 25 Hz would not merely miss every second hit, it would play stale ones a
         * blank late — the drum arriving after the beat is worse than the drum never arriving. */
        unsigned int drum_hit;

        ym_music_tick();
        drum_hit = ym_music_take_drum_hit();
        if (drum_hit != YM_DRUM_NONE && g_drums_ready) {
            dma_sfx_play((uint8_t)drum_hit, YM_DRUM_PRIORITY);
        }
    }
}

/*
 * Swap the buffers and wait for the shifter to be showing the new one. Waiting is what makes the
 * picture tear-free, and it is also DESIGN 17.3's flip lock: the frame rate can only be 25, 16.7 or
 * 12.5 fps because those are the multiples of a 50 Hz blank.
 */
static void flip(void)
{
    uint8_t *shown = g_screen_front;

    g_screen_front = g_screen_back;
    g_screen_back = shown;
    if (!g_vbl_installed) {
        set_video_base(g_screen_front);     /* no queue slot: flip by hand and accept the tear */
        return;
    }
    g_flip_pending = 1;
    while (g_flip_pending) {
    }
}

/* ---------------------------------------------------------------- the c2p tables -------------- */

/*
 * One entry per (position, pixel pair): the four plane words that pair contributes to its
 * 16-screen-pixel group, packed as planes 0/1 then 2/3 so the loop stores two longwords and
 * nothing else. `pixel_span` is how many screen pixels one logical pixel covers — 2 at 160 columns
 * and 4 at 80 — and it is the ONLY difference between the two tables.
 */
static void build_c2p_table(unsigned long *table, int positions, int pixel_span)
{
    int position;
    int even;
    int odd;
    int plane;

    for (position = 0; position < positions; ++position) {
        for (even = 0; even < SHADE_TABLE_ENTRIES; ++even) {
            for (odd = 0; odd < SHADE_TABLE_ENTRIES; ++odd) {
                unsigned long word[SCREEN_PLANES];
                int pair = even * SHADE_TABLE_ENTRIES + odd;
                int even_shift = 16 - (position * 2 + 1) * pixel_span;
                int odd_shift = even_shift - pixel_span;
                unsigned long span_mask = (1UL << pixel_span) - 1;
                unsigned long *entry = table + (position * C2P_PAIR_COUNT + pair) * 2;

                for (plane = 0; plane < SCREEN_PLANES; ++plane) {
                    word[plane] = (((even >> plane) & 1) ? (span_mask << even_shift) : 0)
                                | (((odd >> plane) & 1) ? (span_mask << odd_shift) : 0);
                }
                entry[0] = (word[0] << 16) | word[1];
                entry[1] = (word[2] << 16) | word[3];
            }
        }
    }
}

/* ---------------------------------------------------------------- the cast -------------------- */

/*
 * Fill in everything cast.S needs for the frame and run it. Every field here is a value
 * src/raycast.c recomputes per ray or reaches through two pointers; hoisting them is most of the
 * difference between 3,270 cycles a ray and what README.md's table now measures.
 */
static void build_cast_job(BiCastJob *job)
{
    const ThrottleMode *mode = render_mode(&g_state);
    const ColumnSet *set = render_columns(&g_state);
    const MapGrid grid = level_grid(g_state.level);
    int16_t map_x = (int16_t)(g_state.player.x >> CELL_SHIFT);
    int16_t map_y = (int16_t)(g_state.player.y >> CELL_SHIFT);
    uint16_t frac_x = (uint16_t)(g_state.player.x & CELL_FRAC_MASK);
    uint16_t frac_y = (uint16_t)(g_state.player.y & CELL_FRAC_MASK);
    int i;

    job->columns = g_scratch.columns;
    job->wall_dist = g_scratch.wall_dist;
    job->angle_table = set->angle;
    job->cos_table = set->cosine;
    job->sin_table = g_sin_1024;
    job->inv_cos_table = g_inv_cos_dist;
    job->grid_cells = grid.cells;
    job->blocking = g_state.blocking.solid;
    job->doors = g_state.doors;
    job->door_of_cell = g_state.door_of_cell;
    job->slice_height = g_slice_height;
    job->tex_step = g_tex_step;
    job->cell_texture = g_cell_texture;
    job->count = set->count;
    job->player_angle = g_state.player.angle;
    job->pos_x = g_state.player.x;
    job->pos_y = g_state.player.y;
    /* The radius is at most RENDER_RADIUS_MAX cells, so the trace fits a word by construction. */
    job->max_trace = (int16_t)(mode->radius_cells * CELL_UNITS);
    job->start_index = map_cell_index(&grid, map_x, map_y);
    job->map_x = map_x;
    job->map_y = map_y;
    job->grid_width = grid.width;
    job->to_next_x_pos = (uint16_t)(CELL_UNITS - frac_x);
    job->to_next_x_neg = frac_x;
    job->to_next_y_pos = (uint16_t)(CELL_UNITS - frac_y);
    job->to_next_y_neg = frac_y;
    for (i = 0; i < BAND_COUNT - 1; ++i) {
        job->band_limit[i] = mode->band_limit[i];
    }
    job->band_last = (uint8_t)(mode->band_count - 1);
    job->pad = 0;
}

#ifdef BLACKICE_BENCH

/*
 * THE SELF-CHECK IS THE SURFACE FOR cast.S, and it is stronger than the pixel comparison it sits
 * behind: it runs src/raycast.c's render_cast into a shadow scratch and compares the two column
 * lists and distance arrays byte for byte, on EVERY frame of EVERY pass. A rendered frame can hide
 * a wrong RenderColumn — a band the drawer never reaches, a texture column off by one on a face
 * nothing looks at — and this cannot. The ledger publishes the mismatch count; a non-zero one is a
 * failed run whatever the pixels say.
 */
static RenderScratch g_cast_shadow;
static unsigned long g_cast_mismatches;

/*
 * THE ORACLE RUNS OUTSIDE THE TIMED BRACKET, in its own call before the stage starts and its own
 * comparison after the stage ends. Run inside it, the "cast" row measured the C, the asm and the
 * comparison together and reported the asm as twice its real cost — the first bench of this file
 * did exactly that.
 */
static void cast_reference(void)
{
    render_cast(&g_state, &g_cast_shadow);
}

static void cast_compare(void)
{
    uint16_t columns = render_columns(&g_state)->count;
    uint16_t c;

    for (c = 0; c < columns; ++c) {
        const uint8_t *mine = (const uint8_t *)&g_scratch.columns[c];
        const uint8_t *reference = (const uint8_t *)&g_cast_shadow.columns[c];
        uint16_t byte;

        if (g_scratch.wall_dist[c] != g_cast_shadow.wall_dist[c]) {
            ++g_cast_mismatches;
            continue;
        }
        for (byte = 0; byte < sizeof(RenderColumn); ++byte) {
            if (mine[byte] != reference[byte]) {
                ++g_cast_mismatches;
                break;
            }
        }
    }
}

#else

static void cast_reference(void) { }
static void cast_compare(void) { }

#endif /* BLACKICE_BENCH */

static void cast_frame(void)
{
    BiCastJob job;

    build_cast_job(&job);
    bi_render_cast(&job);
}

/* ---------------------------------------------------------------- the frame ------------------- */

typedef struct {
    int16_t  top;
    int16_t  bottom;
} Band;

/*
 * The rows any column or sprite reaches. Outside it the view is COLOUR_VOID, written by bi_fill at
 * 2.7 cycles a byte instead of the drawer's 26 a pixel plus the c2p's 31.
 *
 * THE SPRITES ARE IN IT and they have to be: the chunky buffer outside the band is never converted,
 * so a sprite pixel written there would simply be lost. Their whole projected extent is taken
 * rather than their per-column spans, which is a superset of what bi_draw_sprites can write and
 * costs at most a few converted rows.
 */
static Band frame_band(const RenderScratch *scratch, uint16_t columns)
{
    Band band;
    uint16_t i;

    band.top = RENDER_H;
    band.bottom = 0;
    for (i = 0; i < columns; ++i) {
        const RenderColumn *column = &scratch->columns[i];
        int16_t bottom = (int16_t)(column->top + column->rows);

        if (column->rows == 0) {
            continue;
        }
        if (column->top < band.top) {
            band.top = column->top;
        }
        if (bottom > band.bottom) {
            band.bottom = bottom;
        }
    }
    for (i = 0; i < scratch->sprites.count; ++i) {
        const RenderSprite *sprite = &scratch->sprites.entries[i];
        int16_t top = sprite->top < 0 ? 0 : sprite->top;
        int16_t bottom = (int16_t)(sprite->top + sprite->rows);

        if (bottom > RENDER_H) {
            bottom = RENDER_H;
        }
        if (top >= bottom) {
            continue;
        }
        if (top < band.top) {
            band.top = top;
        }
        if (bottom > band.bottom) {
            band.bottom = bottom;
        }
    }
    /*
     * CLAMPED, and not because anything is known to overflow: the band is what bi_draw_columns,
     * bi_draw_sprites and the c2p all take as their bounds, so a RenderColumn whose top+rows ran
     * past RENDER_H would have the c2p converting rows that do not exist — straight through the
     * HUD strip and off the end of the screen buffer. The sprite half above already clamps; this
     * makes the column half say the same thing rather than trusting src/raycast.c to keep doing so.
     */
    if (band.top < 0) {
        band.top = 0;
    }
    if (band.bottom > RENDER_H) {
        band.bottom = RENDER_H;
    }
    if (band.bottom <= band.top) {          /* an empty view: nothing to draw or convert */
        band.top = 0;
        band.bottom = 0;
    }
    return band;
}

/* The plane pair a solid pen fills with, for bi_fill. */
static void solid_pattern(int pen, unsigned long *plane01, unsigned long *plane23)
{
    unsigned long plane[SCREEN_PLANES];
    int i;

    for (i = 0; i < SCREEN_PLANES; ++i) {
        plane[i] = ((pen >> i) & 1) ? 0xffffUL : 0UL;
    }
    *plane01 = (plane[0] << 16) | plane[1];
    *plane23 = (plane[2] << 16) | plane[3];
}

/* Which of the two per-buffer HUD records belongs to a screen (hud.h: a field that changes has to
 * be redrawn in both buffers, so each keeps its own account of what it is showing). */
static HudState *hud_record_for(const uint8_t *screen)
{
    return &g_hud_shown[screen == g_screen[1]];
}

/* One frame's measurements, in timer units. */
typedef struct {
    unsigned long stage[BI_STAGES];
    unsigned long total;
    unsigned long sprite_pixels;
    unsigned long sprite_count;
    unsigned long wall_rows;
    unsigned long clipped_columns;
    int16_t       band_top;
    int16_t       band_bottom;
} FrameCost;

/* One mark before the first measured stage and one after each of them. STAGE_SIM is measured by
 * the caller, which owns the clock, so the marks here cover STAGE_CAST..STAGE_HUD. */
#define STAGE_MARKS     BI_STAGES

#define STAGE_SIM       0
#define STAGE_CAST      1
#define STAGE_COLUMNS   2
#define STAGE_SPRITES   3
#define STAGE_FILL      4
#define STAGE_C2P       5
#define STAGE_HUD       6

/*
 * Cast, draw and convert one frame into g_screen_back. The simulation is NOT stepped here — the
 * caller owns the clock, because the interactive loop catches up 1-2 ticks and the bench runs
 * exactly one, and a renderer that stepped the world could not be asked to redraw a held frame.
 */
static void render_frame_into_back(const HudState *hud, FrameCost *cost)
{
    const ColumnSet *set = render_columns(&g_state);
    uint16_t columns = set->count;
    uint16_t pairs = (uint16_t)(columns / 2);
    uint16_t *chunky_band;                  /* the band's first row, which two stages start from */
    BiDrawJob job;
    BiSpriteJob sprite_job;
    Band band;
    unsigned long plane01;
    unsigned long plane23;
    unsigned long mark[STAGE_MARKS];
    uint16_t i;

    cast_reference();                   /* bench only, and deliberately before the clock starts */
    mark[0] = bi_ticks();
    cast_frame();
    sprite_build_list(&g_state, &g_scratch.sprites);
    band = frame_band(&g_scratch, columns);
    mark[1] = bi_ticks();

    chunky_band = g_chunky + (long)band.top * (CHUNKY_ROW_BYTES / 2);
    job.chunky = chunky_band;
    job.columns = g_scratch.columns;
    job.tables = &g_tables;
    job.pairs = (int16_t)pairs;
    job.band_top = band.top;
    job.band_bottom = band.bottom;
    job.void_even = (uint16_t)(COLOUR_VOID * PAIR_EVEN_SCALE);
    job.void_odd = (uint16_t)(COLOUR_VOID * PAIR_ODD_SCALE);
    job.far_even = (uint16_t)(COLOUR_FAR_FILL * PAIR_EVEN_SCALE);
    job.far_odd = (uint16_t)(COLOUR_FAR_FILL * PAIR_ODD_SCALE);
    bi_draw_columns(&job);
    mark[2] = bi_ticks();

    sprite_job.chunky = g_chunky;
    sprite_job.sprites = g_scratch.sprites.entries;
    sprite_job.wall_dist = g_scratch.wall_dist;
    sprite_job.tables = &g_tables;
    sprite_job.count = (int16_t)g_scratch.sprites.count;
    sprite_job.columns = (int16_t)columns;
    sprite_job.band_top = band.top;
    sprite_job.band_bottom = band.bottom;
    bi_draw_sprites(&sprite_job);
    mark[3] = bi_ticks();

    solid_pattern(COLOUR_VOID, &plane01, &plane23);
    bi_fill(g_screen_back, (long)band.top * VIEW_ROW_BYTES, plane01, plane23);
    bi_fill(g_screen_back + (long)band.bottom * VIEW_ROW_BYTES,
            (long)(RENDER_H - band.bottom) * VIEW_ROW_BYTES, plane01, plane23);
    mark[4] = bi_ticks();

    {
        uint8_t *screen = g_screen_back + (long)band.top * VIEW_ROW_BYTES;
        long rows = band.bottom - band.top;

        if (columns == RENDER_COLUMNS_HIGH) {
            bi_c2p_high(chunky_band, screen, rows);
        } else {
            bi_c2p_low(chunky_band, screen, rows);
        }
    }
    mark[5] = bi_ticks();

    hud_draw(g_screen_back, hud, hud_record_for(g_screen_back));
    mark[6] = bi_ticks();
    cast_compare();                     /* bench only, and outside every bracket */

    cost->stage[STAGE_SIM] = 0;             /* the caller owns the clock and fills this in */
    for (i = STAGE_CAST; i <= STAGE_HUD; ++i) {
        cost->stage[i] = mark[i] - mark[i - 1];
    }
    cost->total = mark[STAGE_MARKS - 1] - mark[0];
    cost->band_top = band.top;
    cost->band_bottom = band.bottom;
    cost->sprite_count = g_scratch.sprites.count;
    cost->wall_rows = 0;
    cost->clipped_columns = 0;
    for (i = 0; i < columns; ++i) {
        const RenderColumn *column = &g_scratch.columns[i];

        cost->wall_rows += column->rows;
        if (column->rows == RENDER_H && column->tex_v != 0) {
            ++cost->clipped_columns;    /* project_slice only sets tex_v when it clipped the top */
        }
    }
    cost->sprite_pixels = 0;
    for (i = 0; i < g_scratch.sprites.count; ++i) {
        const RenderSprite *sprite = &g_scratch.sprites.entries[i];

        cost->sprite_pixels += (unsigned long)sprite->cols * sprite->rows;
    }
}

/* ---------------------------------------------------------------- the HUD's state ------------- */

/* DESIGN 18 defers the Spike, so there is one weapon and the icon has one state. It is named
 * rather than inlined because weapons.c will hand the strip a real selection. */
#define HUD_WEAPON_BUSTER   0

/*
 * The two divides here are plat.h's DIVU and not C's `/` for the reason that file gives, and each
 * quotient is provably a word: route_ticks over SIM_HZ is the run's length in seconds, and
 * trace_milli is capped at TRACE_MAX_MILLI so the percentage is at most 100.
 */
static void hud_state_from_game(HudState *hud, const char *message, uint16_t frame_ms)
{
    hud->sector_name = g_level.name;
    hud->message = message;
    hud->run_seconds = divu16(g_state.route_ticks, SIM_HZ);
    hud->frame_ms = frame_ms;
    hud->trace_percent = (uint8_t)divu16((uint32_t)g_state.trace_milli, TRACE_MILLI_PER_PERCENT);
    hud->throttle = g_state.throttle;
    hud->integrity = (uint8_t)(g_state.integrity < 0 ? 0 : g_state.integrity);
    hud->cycles = (uint16_t)(g_state.cycles < 0 ? 0 : g_state.cycles);
    hud->tokens = g_state.tokens;
    hud->weapon = HUD_WEAPON_BUSTER;
}

#ifndef BLACKICE_BENCH

/* ---------------------------------------------------------------- the event ring -------------- */

/*
 * include/events.h's ring is the sim's only way to say anything: it pushes an id and the platform
 * decides what that sounds and reads like. DESIGN 16 makes the first playable YM-only, so a cue is
 * ym_music_sfx_play against the macro the song blob carries; the DMA sample path is not linked.
 *
 * THREE CUES HAVE NO YM MACRO. audio/blackice_sfx_ids.h carries ten of DESIGN 16's thirteen
 * samples; gate-close, the door refusal and the throttle change are not among them, so they are
 * SFX_SILENT here rather than borrowed from a cue that means something else. That is a gap in the
 * audio set, recorded in README.md, not a decision taken here.
 */
#define SFX_SILENT  0xff
/* No band chosen yet, so the first tick always sets the tempo. */
#define MUSIC_BAND_NONE 0xff

static const uint8_t EVENT_TO_YM_SFX[] = {
    SFX_BUSTER_SHOT,        /* EV_SFX_BUSTER_SHOT */
    SFX_SPIKE_SHOT,
    SFX_WATCHDOG_SNARL,
    SFX_SENTRY_CHARGE,
    SFX_GATE_OPEN,
    SFX_SILENT,             /* EV_SFX_GATE_CLOSE */
    SFX_TOKEN_GRAB,
    SFX_SILENT,             /* EV_SFX_DOOR_REFUSAL */
    SFX_SILENT,             /* EV_SFX_THROTTLE_CHANGE */
    SFX_TRACE_ALARM,
    SFX_PLAYER_HIT,
    SFX_ENEMY_DISSOLVE,
    SFX_EXFIL_SIREN,
    SFX_SILENT,             /* EV_SFX_TRACER_PING */
    SFX_SILENT              /* EV_SFX_TRACER_SIREN */
};

/* DESIGN 15.1's 38-character message field, in events.h's id order from EV_MSG_ALPHA_REQUIRED. */
static const char *const EVENT_MESSAGES[] = {
    "ALPHA TOKEN REQUIRED",
    "BETA TOKEN REQUIRED",
    "GAMMA TOKEN REQUIRED",
    "COLD BOOT GATE SEALED",
    "ALPHA TOKEN ACQUIRED",
    "BETA TOKEN ACQUIRED",
    "GAMMA TOKEN ACQUIRED",
    "CYCLES RECOVERED",
    "INTEGRITY RESTORED",
    "SCRUBBER APPLIED",
    "DATA CACHE COPIED",
    "TRACE DEGRADED",
    "TRACE TIER RAISED",
    "TRACE CORRUPT",
    "ICE HARDENED",
    "SECTOR CLEAR",
    "CONNECTION TERMINATED"
};

_Static_assert(sizeof(EVENT_TO_YM_SFX) / sizeof(EVENT_TO_YM_SFX[0])
               == EV_SFX_TRACER_SIREN - EV_SFX_BUSTER_SHOT + 1, "an SFX id has no row");
_Static_assert(sizeof(EVENT_MESSAGES) / sizeof(EVENT_MESSAGES[0])
               == EV_ID_COUNT - EV_MSG_ALPHA_REQUIRED, "a message id has no line");

/* DESIGN 15.1: a message holds for two seconds, which is 2 * 50 vertical blanks. */
#define MESSAGE_HOLD_VBLS   100

static const char *g_message;
static unsigned long g_message_until_vbl;

/*
 * Drain the ring into the YM channel and the message line, and return the line the HUD should show
 * (NULL once the last one has timed out). Called once per frame, after the tick, which is why a
 * burst of several cues in one tick keeps only the last message: the strip has one line.
 */
/*
 * DESIGN 16: "the tempo IS the trace meter", and audio/blackice_song.h ships BLACKICE_BAND_SPEED
 * for exactly this — one song blob at four tempi, switched with ym_music_set_speed, not four blobs.
 * The driver's header says the call writes no hardware but races the tick, so it is made from here,
 * inside the same supervisor state the rest of the loop runs in.
 */
static uint8_t g_music_band = MUSIC_BAND_NONE;

static void follow_trace_tempo(void)
{
    uint8_t band = g_state.trace_band;

    if (!g_music_ready || band == g_music_band) {
        return;
    }
    if (band >= BLACKICE_BAND_COUNT) {
        band = BLACKICE_BAND_COUNT - 1;
    }
    ym_music_set_speed(BLACKICE_BAND_SPEED[band]);
    g_music_band = band;
}

static const char *drain_events(void)
{
    uint8_t id;

    follow_trace_tempo();

    while (event_pop(&g_state.events, &id)) {
        if (EVENT_IS_MESSAGE(id)) {
            g_message = EVENT_MESSAGES[id - EV_MSG_ALPHA_REQUIRED];
            g_message_until_vbl = g_vbl_count + MESSAGE_HOLD_VBLS;
        } else if (id >= EV_SFX_BUSTER_SHOT && id <= EV_SFX_TRACER_SIREN) {
            uint8_t sfx = EVENT_TO_YM_SFX[id - EV_SFX_BUSTER_SHOT];

            if (sfx != SFX_SILENT && g_music_ready) {
                ym_music_sfx_play(sfx);
            }
        }
    }
    if (g_message && g_vbl_count >= g_message_until_vbl) {
        g_message = 0;
    }
    return g_message;
}

/* ---------------------------------------------------------------- input ----------------------- */

/* The IKBD's joystick report bitmap. */
#define JOY_UP      0x01
#define JOY_DOWN    0x02
#define JOY_LEFT    0x04
#define JOY_RIGHT   0x08
#define JOY_FIRE    0x80

/* ST keyboard make codes. A break code is the make code with bit 7 set; Bconin never delivers one,
 * which is why the held keys below come from the joystick and these are the discrete actions. */
#define KEY_ESCAPE      0x01
#define KEY_7           0x08
#define KEY_8           0x09
#define KEY_9           0x0a
#define KEY_P           0x19
#define KEY_Z           0x2c
#define KEY_X           0x2d
#define KEY_SPACE       0x39
#define KEY_UP          0x48
#define KEY_LEFT        0x4b
#define KEY_RIGHT       0x4d
#define KEY_DOWN        0x50
#define BCONIN_SCANCODE_SHIFT   16
#define BCONIN_SCANCODE_MASK    0xff

typedef struct {
    uint16_t input;         /* the engine's INPUT_* bitmask for this tick */
    int      quit;
    int      pause_toggle;
} PlayerIntent;

static uint16_t joystick_input(uint8_t joy, int strafing)
{
    uint16_t input = 0;

    if (joy & JOY_UP) {
        input |= INPUT_FORWARD;
    }
    if (joy & JOY_DOWN) {
        input |= INPUT_BACK;
    }
    if (joy & JOY_LEFT) {
        input |= strafing ? INPUT_STRAFE_LEFT : INPUT_TURN_LEFT;
    }
    if (joy & JOY_RIGHT) {
        input |= strafing ? INPUT_STRAFE_RIGHT : INPUT_TURN_RIGHT;
    }
    if (joy & JOY_FIRE) {
        input |= INPUT_FIRE;
    }
    return input;
}

/*
 * DESIGN 5: the direct throttle keys cost the same 12-tick input lock the joystick route does, so
 * the keyboard is never mechanically better than the stick.
 */
static void set_throttle(uint8_t throttle)
{
    if (g_state.throttle_lock || throttle >= THROTTLE_MODE_COUNT) {
        return;
    }
    g_state.throttle = throttle;
    g_state.throttle_lock = THROTTLE_SWITCH_TICKS;
}

static void apply_key(uint8_t scancode, int strafing, PlayerIntent *intent)
{
    switch (scancode) {
    case KEY_UP:    intent->input |= INPUT_FORWARD; break;
    case KEY_DOWN:  intent->input |= INPUT_BACK; break;
    case KEY_LEFT:  intent->input |= strafing ? INPUT_STRAFE_LEFT : INPUT_TURN_LEFT; break;
    case KEY_RIGHT: intent->input |= strafing ? INPUT_STRAFE_RIGHT : INPUT_TURN_RIGHT; break;
    case KEY_Z:     intent->input |= INPUT_STRAFE_LEFT; break;
    case KEY_X:     intent->input |= INPUT_STRAFE_RIGHT; break;
    case KEY_SPACE: intent->input |= INPUT_FIRE; break;
    case KEY_7:     set_throttle(THROTTLE_UNDERCLOCK); break;
    case KEY_8:     set_throttle(THROTTLE_NOMINAL); break;
    case KEY_9:     set_throttle(THROTTLE_OVERCLOCK); break;
    case KEY_P:     intent->pause_toggle = 1; break;
    case KEY_ESCAPE: intent->quit = 1; break;
    /* HOOK: DESIGN 6's 1 and 2 select Buster and Spike. DESIGN 18 defers the Spike, so there is one
     * weapon and nothing to select; the scancodes join this switch when weapons.c has two. */
    default:        break;
    }
}

/*
 * DESIGN 4.2 wants a sticky press so a tap inside one render period is never lost. The joystick's
 * half is g_joy_sticky, ORed every vertical blank and consumed here. The keyboard's half is TOS's
 * own type-ahead buffer, which is a sticky press by construction — and is also why the keyboard
 * carries only the discrete actions: Bconin delivers makes and repeats, never a release, so a held
 * arrow key moves at the repeat rate. The joystick is the movement device (DESIGN 6 says the game
 * is completable with joystick plus Alt, and that is exactly what this supports).
 */
/*
 * Throw away everything TOS has buffered. The press that leaves the title screen, or that
 * dismisses an overlay, must not also be the first tick's input: SPACE is both "start" and INPUT_FIRE,
 * and without this the run began by spending a cycle on a shot nobody aimed (measured on the first
 * headless boot of the title: the HUD read 59 cycles at 00:03).
 */
/*
 * Vertical blanks the keyboard must stay quiet for before the game accepts input again. A single
 * drain is not enough: the key that started the run is still HELD, and TOS's type-ahead keeps
 * delivering repeats for as long as it is — measured, the first tick of the run spent a cycle on a
 * shot nobody aimed and the HUD read 59 cycles at 00:03. Bconin never reports a release, so
 * "quiet for a while" is the only release this layer can see.
 */
#define KEY_SETTLE_VBLS 25

static void drain_keyboard(void)
{
    unsigned long quiet_until = g_vbl_count + KEY_SETTLE_VBLS;

    while (g_vbl_count < quiet_until) {
        if (Bconstat(BCON_DEVICE_KEYBOARD)) {
            (void)Bconin(BCON_DEVICE_KEYBOARD);
            quiet_until = g_vbl_count + KEY_SETTLE_VBLS;
        }
    }
    g_joy_sticky = 0;
}

static PlayerIntent read_input(void)
{
    PlayerIntent intent;
    uint8_t joy;
    /*
     * SHIFT, AND NOT ALT, AND THAT IS A HARDWARE FINDING. DESIGN 6 names Alt first and rests
     * "completable with joystick plus Alt" on it — but TOS eats Alt+arrow for its own keyboard
     * mouse emulation and never puts the arrow's scancode in the buffer, so `Bconin` never sees it
     * and the modifier is dead. QA measured it: from a standing start Shift+Left strafed x 15.50 ->
     * 12.66 and Alt+Left moved neither position nor angle. Shift already worked, so the modifier
     * this build documents is Shift; DESIGN 6 needs the same correction.
     */
    int strafing = (Kbshift(KBSHIFT_READ) & (KBSHIFT_LEFT_SHIFT | KBSHIFT_RIGHT_SHIFT)) != 0;

    intent.input = 0;
    intent.quit = 0;
    intent.pause_toggle = 0;

    joy = (uint8_t)(g_joy_sticky | bi_joy_port1);
    g_joy_sticky = 0;
    intent.input = joystick_input(joy, strafing);

    while (Bconstat(BCON_DEVICE_KEYBOARD)) {
        unsigned long key = (unsigned long)Bconin(BCON_DEVICE_KEYBOARD);

        apply_key((uint8_t)((key >> BCONIN_SCANCODE_SHIFT) & BCONIN_SCANCODE_MASK),
                  strafing, &intent);
    }
    return intent;
}

#endif /* !BLACKICE_BENCH */

/* ---------------------------------------------------------------- boot and teardown ----------- */

/* IKBD set-up, BRIEF.md's gotcha: without $12 the fire button lands in the mouse packet, and
 * without $14 no joystick packet is sent at all. The teardown puts the machine back where TOS
 * expects it — joystick reporting off, mouse in relative mode. */
static const char IKBD_MOUSE_OFF[] = { 0x12 };
static const char IKBD_JOYSTICK_EVENTS[] = { 0x14 };
static const char IKBD_JOYSTICK_OFF[] = { 0x1a };
static const char IKBD_MOUSE_RELATIVE[] = { 0x08 };

static void ikbd_write(const char *bytes, int count)
{
    Ikbdws((short)(count - 1), bytes);
}

/*
 * The vertical blank, by whichever of the two routes is available.
 *
 * TOS's queue is preferred and os.S says why. But it has only `nvbls` slots and a machine with
 * accessories loaded can have none free — and without a vertical blank this program has no frame
 * clock, no page flip and no music tick, which is not a degraded mode but a hang. So the fallback
 * installs on the level-4 autovector and chains, which is safe now that set_video_base writes
 * `_v_bas_ad` as well as the hardware registers.
 */
static void install_vectors(void)
{
    void **queue = *(void ***)VBLQUEUE_ADDR;
    short slots = *(volatile short *)NVBLS_ADDR;
    short slot;

    g_joyvec_slot = (void **)((uint8_t *)Kbdvbase() + KBDVECS_JOYVEC_OFFSET);
    g_saved_joyvec = *g_joyvec_slot;
    *g_joyvec_slot = (void *)bi_joy_entry;

    for (slot = 0; slot < slots; ++slot) {
        if (!queue[slot]) {
            g_vbl_slot = &queue[slot];
            *g_vbl_slot = (void *)bi_vbl_entry;
            g_vbl_installed = 1;
            return;
        }
    }
    bi_vbl_chain = *(void **)VBL_VECTOR_ADDR;
    *(void **)VBL_VECTOR_ADDR = (void *)bi_vbl_vector_entry;
    g_vbl_vector_installed = 1;
    g_vbl_installed = 1;
}

static void remove_vectors(void)
{
    if (g_vbl_slot) {
        *g_vbl_slot = 0;
    }
    if (g_vbl_vector_installed) {
        *(void **)VBL_VECTOR_ADDR = bi_vbl_chain;
        g_vbl_vector_installed = 0;
    }
    g_vbl_installed = 0;
    if (g_joyvec_slot) {
        *g_joyvec_slot = g_saved_joyvec;
    }
}

#define CURSOR_OFF  "\033f"

static void enter_game_video(void)
{
    g_screen[0] = (uint8_t *)(((unsigned long)g_screen_store + PLAT_SCREEN_ALIGN - 1)
                              & ~(unsigned long)(PLAT_SCREEN_ALIGN - 1));
    g_screen[1] = g_screen[0] + PLAT_SCREEN_BYTES;
    g_screen_front = g_screen[0];
    g_screen_back = g_screen[1];
    /*
     * THE MODE SWITCH COMES FIRST AND THE PIXELS AFTER, because Setscreen with a real resolution
     * CLEARS the screen it is given: the first version of this blitted the HUD backdrop and then
     * switched, and TOS wiped the strip on the way — the harness caught it as "the HUD's rules are
     * not at lines 160 and 168", which is what a cleared strip looks like from outside.
     *
     * Setscreen also sets _v_bas_ad, so TOS's own vertical blank keeps writing OUR base every frame
     * rather than putting the desktop back; and it sets the RESOLUTION, which this build needs and
     * used to leave alone. Everything here draws 320x200 in four bitplanes, so launched from a
     * medium-resolution desktop the shifter would read the same bytes 640 pixels wide in two planes
     * and the picture would be nonsense. Saving the old resolution and never setting a new one is
     * the shape of that bug.
     */
    Setscreen(g_screen[0], g_screen[0], REZ_ST_LOW);
    memset(g_screen[0], 0, 2 * PLAT_SCREEN_BYTES);
    hud_blit_backdrop(g_screen[0]);
    hud_blit_backdrop(g_screen[1]);
    hud_reset(&g_hud_shown[0]);
    hud_reset(&g_hud_shown[1]);
}

static void leave_game_video(void)
{
    *(volatile uint8_t *)CONTERM_ADDR = g_saved_conterm;
    set_palette(g_saved_palette);
    Setscreen(g_saved_logbase, g_saved_physbase, g_saved_rez);
}

/*
 * A monochrome monitor cannot show ST Low at all — the shifter has one resolution on that monitor
 * and it is REZ_ST_HIGH — so this build has nothing to draw on one. Refusing with a line of text is
 * the whole handling: there is no fallback to write, and a program that switched anyway would leave
 * the user looking at a black screen with no way back.
 */
static int monitor_cannot_show_the_game(void)
{
    return (short)Getrez() == REZ_ST_HIGH;
}

/* ---------------------------------------------------------------- the interactive loop -------- */

#ifndef BLACKICE_BENCH

/* 27 glyphs against the 28 the title bar's left half holds (hud.c's TITLE_NAME_GLYPHS), so it ends
 * one glyph clear of the run clock. At 28 it read as "ESC ABORT00:09". */
#define PAUSE_MESSAGE   "PAUSED - P RESUME ESC QUIT"
/*
 * Timer units to whole milliseconds for the HUD's readout. TIMER_TICK_NS is 26,042 ns, so a tick is
 * 26.042 us and this rounds it to 26: 0.16% low on a number the player reads to three digits, in
 * exchange for a `mulu.w` and a `DIVU` instead of libgcc's __mulsi3 and __udivsi3 once a frame. The
 * ledger's own microseconds are NOT rounded this way — ticks_to_us keeps the full value, because
 * that number is the measurement.
 */
#define TIMER_TICK_US   (TIMER_TICK_NS / 1000)
#define US_PER_MS       1000
/* Above this a frame's tick count times TIMER_TICK_US would leave a word; 1.7 s of frame. */
#define FRAME_TICKS_MAX 0xffffU

static uint16_t frame_milliseconds(unsigned long ticks)
{
    if (ticks > FRAME_TICKS_MAX) {
        return 0;                   /* a frame this long is a hang, not a measurement */
    }
    return divu16((uint32_t)ticks * TIMER_TICK_US, US_PER_MS);
}

/*
 * The whole ramp lifted halfway to white for ONE frame. DESIGN 7 wants a two-frame register-12
 * muzzle flash and DESIGN 18 item 7 a damage flash; both are sprites in the document and sprites
 * belong to the engine, so the platform's honest version of "the screen flinches" is the palette.
 * QA.md defect 6 is that firing and being hit produced no picture of any kind.
 */
static void palette_flash(const uint16_t *base, uint16_t *out)
{
    int pen;

    for (pen = 0; pen < PALETTE_PENS; ++pen) {
        out[pen] = ste_wash_to_white(base[pen]);
    }
}

/* ---------------------------------------------------------------- the run's flow --------------
 * QA.md's first three defects are all the same shape: the simulation reaches a state and the
 * platform never looks. `phase` becomes PHASE_DEAD and the player keeps walking around a frozen
 * world; it becomes PHASE_LEVEL_CLEAR and the game stays on sector 1 forever. So the loop below is
 * a state machine over the run and not a single `while (running)`.
 */
#define OUTCOME_QUIT        0
#define OUTCOME_DEAD        1
#define OUTCOME_CLEAR       2

/* How long an overlay holds, in vertical blanks. DESIGN 15 gives death a 2 s dissolve. */
#define OVERLAY_HOLD_VBLS   100
/* Screen rows the overlay's three lines sit on, inside the 3D window. */
#define OVERLAY_LINE_1      56
#define OVERLAY_LINE_2      76
#define OVERLAY_LINE_3      96

/* What the strip shows while an overlay is up: the run's real numbers, and no message line. */
static void overlay_hud(HudState *hud)
{
    hud_state_from_game(hud, 0, 0);
}

/*
 * Put the world's own colours back. play() may return on the very frame it lifted the palette for a
 * hit — the frame that killed the player always does — and without this the death overlay came up
 * under the flash, washed grey. Measured on the first headless death: the whole screen, HUD
 * included, was still half-way to white.
 */
/*
 * Force the whole strip to redraw. hud_draw compares the sector name BY POINTER, and every level
 * loads into the same static Level — so the pointer never changes and the name field would never
 * be redrawn: level 2 came up with the corridor of THE LEDGER and the title still reading INGRESS.
 * A new sector invalidates every field, which is what hud_reset is for.
 */
static void hud_invalidate(void)
{
    hud_reset(&g_hud_shown[0]);
    hud_reset(&g_hud_shown[1]);
}

static void restore_palette(void)
{
    uint8_t variant = g_state.palette_variant < PALETTE_VARIANT_COUNT
                    ? g_state.palette_variant : PALETTE_VARIANT_CLEAN;

    set_palette(g_palette_variants[variant]);
}

/*
 * Put an overlay on the screen and hold it. Both buffers are drawn so the page flip cannot show a
 * half-built one, and the loop keeps flipping so the shifter has something stable to display.
 */
static void show_overlay(const char *line1, const char *line2, const char *line3, uint8_t pen)
{
    HudState hud;
    unsigned long until = g_vbl_count + OVERLAY_HOLD_VBLS;
    int buffer;

    restore_palette();
    overlay_hud(&hud);
    for (buffer = 0; buffer < 2; ++buffer) {
        overlay_clear(g_screen_back);
        overlay_centre(g_screen_back, OVERLAY_LINE_1, line1, pen);
        if (line2) {
            overlay_centre(g_screen_back, OVERLAY_LINE_2, line2, OVERLAY_PEN_DIM);
        }
        if (line3) {
            overlay_centre(g_screen_back, OVERLAY_LINE_3, line3, OVERLAY_PEN_DIM);
        }
        hud_draw(g_screen_back, &hud, hud_record_for(g_screen_back));
        flip();
    }
    while (g_vbl_count < until) {
        PlayerIntent intent = read_input();

        if (intent.quit) {
            return;                     /* Escape gets out of an overlay as well as out of a game */
        }
    }
    drain_keyboard();
}

/*
 * The title, DESIGN 15's: the art pass's planar screen, whole-page, with the platform's own
 * controls written into the strapline band the mockup leaves for a prompt (overlay.c says which
 * rows and why). It is the same sixteen colours as the game, so there is no palette to swap.
 *
 * THE PROMPT BREATHES FOR THE COST OF ONE WORD A FRAME. The art uses fifteen of the sixteen
 * registers and leaves 14 free, so the line is drawn in 14 and the pulse is a single palette write
 * on the vertical blank — no redraw, no second page to keep in step, and nothing else on the screen
 * moves. Register 14 is the HUD's integrity green, which is why play()'s first frame writes the
 * whole palette back before anything is drawn in it.
 *
 * Returns 0 if the player quit instead of starting.
 */
#define TITLE_PULSE_VBLS    64      /* a power of two: the phase is a mask, not a __umodsi3 */
#define TITLE_PULSE_SHIFT   5       /* the blend runs 0..32 over half a period */

static void pulse_title_prompt(void)
{
    unsigned long phase = g_vbl_count & (TITLE_PULSE_VBLS - 1);
    unsigned long ramp = phase < TITLE_PULSE_VBLS / 2 ? phase : TITLE_PULSE_VBLS - phase;
    volatile uint16_t *pen = opaque_pointer((void *)PALETTE_ADDR);

    pen[OVERLAY_PEN_PULSE] = ste_blend(g_ste_palette[OVERLAY_PEN_PANEL],
                                       g_ste_palette[OVERLAY_PEN_TEXT],
                                       (uint16_t)ramp, TITLE_PULSE_SHIFT);
}

static int title_screen(void)
{
    int buffer;

    set_palette(g_palette_variants[PALETTE_VARIANT_CLEAN]);
    /* Both pages, because the pulse flips nothing and the shifter may be showing either. */
    for (buffer = 0; buffer < 2; ++buffer) {
        overlay_title(g_screen_back);
        flip();
    }
    for (;;) {
        PlayerIntent intent = read_input();

        pulse_title_prompt();
        if (intent.quit) {
            return 0;
        }
        if (intent.input & INPUT_FIRE) {
            drain_keyboard();
            return 1;
        }
    }
}

/*
 * DESIGN 4.1's catch-up loop, and it is a catch-up loop and not a VBL-driven simulation: the
 * renderer takes two to four blanks, so the tick must be able to run twice between frames rather
 * than the world slowing down when the frame does. One latched input word feeds every tick of a
 * frame, which is DESIGN 4.2's rule.
 *
 * Returns why it stopped, which is the thing the version QA played never asked.
 */
static int play(void)
{
    unsigned long last_tick_vbl = g_vbl_count;
    uint16_t frame_ms = 0;
    uint8_t shown_variant = PALETTE_VARIANT_COUNT;      /* nothing shown yet: force the first write */
    int16_t last_integrity = g_state.integrity;
    int paused = 0;

    for (;;) {
        PlayerIntent intent = read_input();
        HudState hud;
        FrameCost cost;
        unsigned long sim_start = bi_ticks();
        unsigned long sim_end;
        int flashing;

        if (intent.quit) {
            return OUTCOME_QUIT;
        }
        if (intent.pause_toggle) {
            paused = !paused;
            last_tick_vbl = g_vbl_count;
        }
        while (!paused && g_vbl_count - last_tick_vbl >= VBLS_PER_TICK) {
            game_step(&g_state, intent.input);
            last_tick_vbl += VBLS_PER_TICK;
            if (g_state.phase != PHASE_PLAYING) {
                break;              /* the run ended mid-catch-up; do not tick past it */
            }
        }
        sim_end = bi_ticks();

        /*
         * The two things QA.md said the screen never did. A flash is one frame of the whole ramp
         * lifted towards white — the muzzle when weapons.c sets muzzle_flash, and a hit when
         * integrity fell since the last frame. The palette is the platform's stand-in for DESIGN
         * 7's flash sprite, which belongs to the engine and does not exist.
         */
        flashing = g_state.muzzle_flash != 0 || g_state.integrity < last_integrity;
        last_integrity = g_state.integrity;
        if (flashing) {
            uint16_t lifted[PALETTE_PENS];

            palette_flash(g_palette_variants[shown_variant < PALETTE_VARIANT_COUNT
                                             ? shown_variant : PALETTE_VARIANT_CLEAN], lifted);
            set_palette(lifted);
            shown_variant = PALETTE_VARIANT_COUNT;      /* the next frame puts the variant back */
        } else if (g_state.palette_variant != shown_variant) {
            shown_variant = g_state.palette_variant < PALETTE_VARIANT_COUNT
                          ? g_state.palette_variant : PALETTE_VARIANT_CLEAN;
            set_palette(g_palette_variants[shown_variant]);
        }

        hud_state_from_game(&hud, paused ? PAUSE_MESSAGE : drain_events(), frame_ms);
        render_frame_into_back(&hud, &cost);
        cost.stage[STAGE_SIM] = sim_end - sim_start;
        cost.total += cost.stage[STAGE_SIM];
        /* The readout the HUD shows is the frame BEFORE this one: its own cost is not known until
         * after it has been drawn, and a number that lags one frame is better than none. */
        frame_ms = frame_milliseconds(cost.total);
        flip();

        if (g_state.phase == PHASE_DEAD) {
            return OUTCOME_DEAD;
        }
        if (g_state.phase == PHASE_LEVEL_CLEAR) {
            return OUTCOME_CLEAR;
        }
    }
}

/*
 * One run: the title, then sectors until the player dies out of the will to continue, quits, or
 * finishes the last one. DESIGN 15's retry rule is unlimited and restarts the CURRENT sector, and
 * DESIGN 9's start rule turns the death count into the trace it starts at — which is why the
 * RunProgress the sector was started from is kept and reused rather than rebuilt from the corpse.
 */
static void run_the_game(void)
{
    for (;;) {
        RunProgress sector_start;
        uint8_t sector = 0;

        if (!title_screen()) {
            return;
        }
        run_progress_reset(&sector_start);
        for (;;) {
            char clock[8];
            int outcome;

            if (assets_load_level(sector, &g_level) != ASSETS_OK) {
                show_overlay("SECTOR NOT ON DISK", 0, 0, OVERLAY_PEN_ALERT);
                break;
            }
            memcpy(g_level_entities_pristine, g_level.entities, sizeof(g_level.entities));
            game_start_level(&g_state, &g_level, g_level.rng_seed, &sector_start);
            /* The title screen is a whole page, so the HUD's backdrop has to be laid down again
             * before the strip's live fields have anything to sit on. */
            hud_blit_backdrop(g_screen[0]);
            hud_blit_backdrop(g_screen[1]);
            hud_invalidate();
            outcome = play();
            if (outcome == OUTCOME_QUIT) {
                return;
            }
            overlay_format_clock(clock, g_state.route_ticks);
            if (outcome == OUTCOME_DEAD) {
                /* DESIGN 15: retries are unlimited and each death costs starting trace, which
                 * trace_init applies from the count sim.c has already incremented. */
                sector_start.deaths_this_sector = g_state.deaths_this_sector;
                show_overlay("CONNECTION TERMINATED", "RECONNECTING", clock, OVERLAY_PEN_ALERT);
                continue;
            }
            show_overlay("SECTOR CLEAR", g_level.name, clock, OVERLAY_PEN_TEXT);
            /* DESIGN 4: integrity and cycles carry, tokens do not; DESIGN 9: a sector finished
             * over par costs the next one's starting trace. */
            sector_start.deaths_this_sector = 0;
            sector_start.integrity = g_state.integrity;
            sector_start.cycles = g_state.cycles;
            if (g_state.route_ticks > g_level.par_ticks
                && sector_start.sectors_over_par < 0xff) {
                ++sector_start.sectors_over_par;
            }
            sector = g_state.next_sector_index;
            if (sector >= ASSETS_LEVEL_COUNT) {
                show_overlay("RUN COMPLETE", clock, 0, OVERLAY_PEN_TEXT);
                break;
            }
        }
    }
}

#endif /* !BLACKICE_BENCH */

/* ---------------------------------------------------------------- the bench ------------------- */

#ifdef BLACKICE_BENCH


/* ---------------------------------------------------------------- the ledger ------------------ */

typedef struct {
    unsigned long min;
    unsigned long sum;
    unsigned long max;
} BiStageTime;

typedef struct {
    char          name[BI_LEDGER_NAME_BYTES];
    unsigned long columns;
    unsigned long frames;
    unsigned long band_top_sum;
    unsigned long band_bottom_sum;
    unsigned long sprite_px_sum;
    unsigned long sprite_count_sum;
    BiStageTime   total;
    /* Frame SHAPE, not time: the total wall rows the drawer was asked for and how many columns had
     * their slice clipped to the window. DESIGN 17.1 names FOCAL_ROWS as the single knob for how
     * squat the world reads, and the two numbers that decision needs are how much wall a frame
     * actually contains and how often it is taller than the 80 rows there are. */
    unsigned long wall_rows_sum;
    unsigned long clipped_columns_sum;
    unsigned long reserved[3];
    BiStageTime   stage[BI_STAGES];
} BiPassLedger;

#define BI_BENCH_PASSES 5

typedef struct {
    unsigned long magic;            /* written LAST: its arrival means the rest is complete */
    unsigned long version;
    unsigned long tick_ns;
    unsigned long cpu_hz;
    unsigned long pass_count;
    unsigned long timer_c_max;
    unsigned long stage_count;
    unsigned long capture_pass;
    unsigned long capture_frame;
    /* cast.S's self-check: RenderColumns that differed from src/raycast.c's, over the whole run.
     * Anything but zero means the asm cast and its oracle disagree and the run is void. */
    unsigned long cast_mismatches;
    /* What the audio drivers accepted at boot, so a silent run is diagnosable from the ledger and
     * not only from a listener. song_accept is ym_music_init's verdict on the blob (it refuses the
     * old 'YMS1' format outright); bank_accept is dma_sfx_init's, which is 0 on every plain ST
     * because there is no DMA sound chip to take the bank. */
    unsigned long song_accept;
    unsigned long bank_accept;
    BiPassLedger  pass[BI_BENCH_PASSES];
} BiLedger;

_Static_assert(sizeof(BiPassLedger) == 64 + BI_STAGES * 12, "the bench parses a fixed pass stride");
_Static_assert(sizeof(BiLedger) <= BI_LEDGER_CAPTURE_BYTES, "the ledger outgrew the capture window");

static BiLedger g_ledger;

/*
 * The magic goes down last and separately, so a debugger breakpoint on it means every field behind
 * it has landed. The destination is hidden from the optimiser for the reason opaque_pointer's
 * comment gives.
 */
static void publish_ledger(void)
{
    volatile unsigned long *out = opaque_pointer((void *)BI_LEDGER_ADDR);
    const unsigned long *in = (const unsigned long *)&g_ledger;
    unsigned long i;

    for (i = 1; i < sizeof(BiLedger) / sizeof(unsigned long); ++i) {
        out[i] = in[i];
    }
    out[0] = BI_LEDGER_MAGIC;
}

static void record_frame(BiPassLedger *pass, const FrameCost *cost)
{
    int stage;

    for (stage = 0; stage < BI_STAGES; ++stage) {
        unsigned long value = cost->stage[stage];

        if (!pass->frames || value < pass->stage[stage].min) {
            pass->stage[stage].min = value;
        }
        if (value > pass->stage[stage].max) {
            pass->stage[stage].max = value;
        }
        pass->stage[stage].sum += value;
    }
    if (!pass->frames || cost->total < pass->total.min) {
        pass->total.min = cost->total;
    }
    if (cost->total > pass->total.max) {
        pass->total.max = cost->total;
    }
    pass->total.sum += cost->total;
    pass->band_top_sum += (unsigned long)cost->band_top;
    pass->band_bottom_sum += (unsigned long)cost->band_bottom;
    pass->sprite_px_sum += cost->sprite_pixels;
    pass->sprite_count_sum += cost->sprite_count;
    pass->wall_rows_sum += cost->wall_rows;
    pass->clipped_columns_sum += cost->clipped_columns;
    ++pass->frames;
}

/* ---------------------------------------------------------------- text reporting -------------- */

static char g_text[4096];

static char *put_str(char *p, const char *s)
{
    while (*s) {
        *p++ = *s++;
    }
    return p;
}

static char *put_num(char *p, unsigned long value)
{
    char digits[12];
    int n = 0;

    do {
        digits[n++] = (char)('0' + (value % 10));
        value /= 10;
    } while (value);
    while (n) {
        *p++ = digits[--n];
    }
    return p;
}

static char *put_field(char *p, const char *label, unsigned long value)
{
    return put_num(put_str(p, label), value);
}

/*
 * Microseconds per frame from a pass total. The obvious `ticks * TIMER_TICK_NS / frames` overflows
 * a long — a hundred frames of a heavy stage is a million timer units and the product is 2.6e10 —
 * and the obvious fix, dividing by the frame count first, throws away everything under one whole
 * tick per frame: a stage costing a fraction of a tick reported as zero, and atari/bench.py's
 * cross-check against the ledger then disagreed with this file by more than rounding. So the
 * quotient and the remainder are converted separately: the remainder is under `frames`, so its
 * product is small, and the two halves together are exact to the microsecond.
 */
static unsigned long ticks_to_us(unsigned long ticks, unsigned long frames)
{
    unsigned long whole;
    unsigned long rest;

    if (!frames) {
        return 0;
    }
    whole = (ticks / frames) * TIMER_TICK_NS / 1000UL;
    rest = (ticks % frames) * TIMER_TICK_NS / frames / 1000UL;
    return whole + rest;
}

/* Indexed by the STAGE_* constants so the order the ledger publishes is stated exactly once. */
/* One 50 Hz blank, in microseconds: the granularity the flip lock quantises a frame to. */
#define VBL_PERIOD_US   20000UL

/* 50 / ceil(total_us / VBL_PERIOD_US), in tenths, which is what the flip lock actually delivers. */
static unsigned long locked_fps10(unsigned long total_us)
{
    unsigned long blanks = (total_us + VBL_PERIOD_US - 1) / VBL_PERIOD_US;

    return blanks ? 500UL / blanks : 0UL;
}

/* Indexed by the STAGE_* constants so the order the ledger publishes is stated exactly once. */
static const char *const STAGE_NAMES[BI_STAGES] = {
    [STAGE_SIM] = "sim",     [STAGE_CAST] = "cast", [STAGE_COLUMNS] = "columns",
    [STAGE_SPRITES] = "sprites", [STAGE_FILL] = "fill", [STAGE_C2P] = "c2p",
    [STAGE_HUD] = "hud"
};

static void write_bench_text(void)
{
    char *p = g_text;
    unsigned long index;

    p = put_str(p, "BLACK ICE bench (microseconds per frame)\r\n");
    p = put_field(p, "ledger=", BI_LEDGER_ADDR);
    p = put_field(p, " tick_ns=", TIMER_TICK_NS);
    p = put_field(p, " timer_c_max=", g_ledger.timer_c_max);
    p = put_field(p, " arena=", assets_arena_used());
    p = put_field(p, "/", assets_arena_capacity());
    p = put_field(p, " screen=", (unsigned long)g_screen[0]);
    p = put_field(p, " cast_mismatches=", g_ledger.cast_mismatches);
    p = put_field(p, " song_accept=", g_ledger.song_accept);
    p = put_field(p, " bank_accept=", g_ledger.bank_accept);
    p = put_str(p, "\r\n");
    for (index = 0; index < g_ledger.pass_count; ++index) {
        const BiPassLedger *pass = &g_ledger.pass[index];
        unsigned long frames = pass->frames ? pass->frames : 1;
        unsigned long total_us = ticks_to_us(pass->total.sum, pass->frames);
        int stage;

        p = put_str(p, "pass=");
        p = put_str(p, pass->name);
        p = put_field(p, " cols=", pass->columns);
        p = put_field(p, " frames=", pass->frames);
        for (stage = 0; stage < BI_STAGES; ++stage) {
            p = put_str(p, " ");
            p = put_str(p, STAGE_NAMES[stage]);
            p = put_field(p, "=", ticks_to_us(pass->stage[stage].sum, pass->frames));
        }
        p = put_field(p, " tot=", total_us);
        p = put_field(p, " fps10=", total_us ? 10000000UL / total_us : 0UL);
        p = put_field(p, " bt=", pass->band_top_sum / frames);
        p = put_field(p, " bb=", pass->band_bottom_sum / frames);
        p = put_field(p, " sprpx=", pass->sprite_px_sum / frames);
        p = put_field(p, " wallrows=", pass->wall_rows_sum / frames);
        p = put_field(p, " clipped=", pass->clipped_columns_sum / frames);
        /*
         * fps10 is the WORK rate and fps_locked is what the player sees. The loop waits for the
         * vertical blank after every frame (DESIGN 17.3's flip lock), so the only rates available
         * are 50 divided by a whole number of blanks: a frame costing 121,000 us does not deliver
         * 8.2 fps, it delivers 50/7 = 7.1. Reporting only fps10 overstates every pass.
         */
        p = put_field(p, " fpsl10=", locked_fps10(total_us));
        p = put_str(p, "\r\n");
    }
    *p = '\0';
}

#define BENCH_FILENAME  "BENCH.TXT"

static void write_bench_file(void)
{
    long handle = Fcreate(BENCH_FILENAME, FCREATE_NORMAL);
    long length = 0;

    if (handle < 0) {
        return;
    }
    while (g_text[length]) {
        ++length;
    }
    Fwrite((short)handle, length, g_text);
    Fclose((short)handle);
}

/* The run's own check that this TOS programmed timer C the way TIMER_C_RELOAD assumes: a reload of
 * 192 can never be read back above 191, and a larger maximum means every time in the ledger is
 * wrong by that ratio. */
#define TIMER_C_PROBE_READS 4000

static unsigned long probe_timer_c(void)
{
    unsigned long highest = 0;
    int i;

    for (i = 0; i < TIMER_C_PROBE_READS; ++i) {
        unsigned long value = bi_timer_c_read();

        if (value > highest) {
            highest = value;
        }
    }
    return highest;
}

/*
 * The fixtures. DESIGN 17.3 names three canonical worst-case frames; two of them need enemies the
 * gameplay agent has not written yet, so what is measured here is WC-A exactly (nose to wall, every
 * column at the full window height) plus the scripted walk at both column counts and a near-sprite
 * frame built from whatever drawable entities the level's own data provides. The ledger reports the
 * sprite pixels each pass actually spent, so a fixture that found nothing to draw says so rather
 * than pretending.
 */
#define FIXTURE_SCRIPT          0
#define FIXTURE_NOSE_TO_WALL    1
#define FIXTURE_NEAR_SPRITES    2

typedef struct {
    const char name[BI_LEDGER_NAME_BYTES];
    uint8_t    detail;      /* DETAIL_COLUMNS_*: the column count, DESIGN 5's separate setting */
    uint8_t    fixture;
} BenchPass;

/*
 * The CAPTURED pass is the last one, because Hatari's screenshot hands back the last surface it
 * RENDERED: publishing the ledger after an earlier pass would catch a picture from a later one.
 * ../spike/REPORT.md paid for that ordering.
 */
static const BenchPass BENCH_PASSES[BI_BENCH_PASSES] = {
    { "WCA160",  DETAIL_COLUMNS_160, FIXTURE_NOSE_TO_WALL },
    { "WCA80",   DETAIL_COLUMNS_80,  FIXTURE_NOSE_TO_WALL },
    { "WCS160",  DETAIL_COLUMNS_160, FIXTURE_NEAR_SPRITES },
    { "WALK80",  DETAIL_COLUMNS_80,  FIXTURE_SCRIPT },
    { "WALK160", DETAIL_COLUMNS_160, FIXTURE_SCRIPT },
};

/*
 * WHICH PASS THE HELD SCREENSHOT BELONGS TO. It has to be a pass that replays the input script from
 * frame 0, because that is the only kind the host reference can reproduce; the WC fixtures place
 * the player from the map and the host has no way to be told where to stand. The default is the
 * last such pass, and the build can name another with -DBENCH_CAPTURE_PASS so that BOTH column
 * counts get compared: 160 exercises bi_c2p_high and 80 exercises bi_c2p_low, and 80 is what
 * DESIGN v2.1 17.3 made the shipping default.
 */
#ifndef BENCH_CAPTURE_PASS
#define BENCH_CAPTURE_PASS  (BI_BENCH_PASSES - 1)
#endif
#define BENCH_CAPTURE_FRAME (BENCH_SCRIPT_TICKS - 1)
#define BENCH_HOLD_VBLS     120

/* Where a nose-to-wall body stands: hard against the face, at the collision radius plus a unit so
 * the collider does not push it back out. */
#define NOSE_CLEARANCE_UNITS    (PLAYER_RADIUS + 1)
/* How far along +x the fixture searches for a wall face to stand at. */
#define NOSE_SEARCH_CELLS       16

/*
 * Stand the player against the first wall face east of the start cell, facing it. Angle 0 is +x, so
 * a north-south wall projects at a CONSTANT perpendicular distance across the whole field of view:
 * every column is the same height and the window is completely full. That is DESIGN 17.3's WC-A,
 * built from the map rather than from hard-coded coordinates so it survives a level edit.
 */
static int place_nose_to_wall(void)
{
    MapGrid grid = level_grid(&g_level);
    int16_t cell_y = (int16_t)g_level.start_cell_y;
    int16_t cell_x;

    for (cell_x = (int16_t)g_level.start_cell_x; cell_x < g_level.start_cell_x + NOSE_SEARCH_CELLS
                                                 && cell_x + 1 < grid.width; ++cell_x) {
        int32_t ahead = map_cell_index(&grid, (int16_t)(cell_x + 1), cell_y);

        if (!map_cell_blocks(&g_state.blocking, (uint16_t)ahead)) {
            continue;
        }
        g_state.player.x = (fix88_t)((cell_x + 1) * CELL_UNITS - NOSE_CLEARANCE_UNITS);
        g_state.player.y = cell_centre((uint8_t)cell_y);
        g_state.player.angle = 0;
        return 1;
    }
    return 0;
}

/* How far back from the wall the sprite fixture stands, and how far ahead it puts the bodies. */
#define SPRITE_FIXTURE_STANDOFF_CELLS   3
#define SPRITE_FIXTURE_AHEAD_CELLS      2
#define SPRITE_FIXTURE_BODIES           3

/*
 * DESIGN 17.3's WC-B/WC-C shape: a wall filling the view with near billboards in front of it. The
 * bodies are the level's OWN entities, MOVED rather than invented — a fabricated entity would
 * measure a sprite the game cannot actually produce.
 *
 * They are moved in the authored Level and the state is then re-initialised, because
 * entities_init copies the runtime table from that array: writing the runtime records directly
 * would leave the occupancy map claiming the cells they came from. So this runs game_init twice,
 * once to get a blocking map to search and once to plant the result. Returns how many it placed.
 */
static int place_near_sprites(void)
{
    MapGrid grid = level_grid(&g_level);
    int16_t cell_x;
    int16_t cell_y;
    uint16_t entity = 0;
    int placed = 0;
    int lateral;

    if (!place_nose_to_wall()) {
        return 0;
    }
    g_state.player.x -= SPRITE_FIXTURE_STANDOFF_CELLS * CELL_UNITS;
    cell_x = (int16_t)(g_state.player.x >> CELL_SHIFT);
    cell_y = (int16_t)(g_state.player.y >> CELL_SHIFT);

    for (lateral = -1; lateral <= 1 && placed < SPRITE_FIXTURE_BODIES; ++lateral) {
        int16_t at_x = (int16_t)(cell_x + SPRITE_FIXTURE_AHEAD_CELLS);
        int16_t at_y = (int16_t)(cell_y + lateral);

        if (at_x >= grid.width || at_y < 0 || at_y >= grid.height) {
            continue;
        }
        if (map_cell_blocks(&g_state.blocking, map_cell_index(&grid, at_x, at_y))) {
            continue;
        }
        while (entity < g_level.entity_count && !g_entity_sprites[g_level.entities[entity].type]) {
            ++entity;
        }
        if (entity >= g_level.entity_count) {
            break;
        }
        g_level.entities[entity].cell_x = (uint8_t)at_x;
        g_level.entities[entity].cell_y = (uint8_t)at_y;
        ++entity;
        ++placed;
    }
    game_init(&g_state, &g_level, g_level.rng_seed);
    place_nose_to_wall();
    g_state.player.x -= SPRITE_FIXTURE_STANDOFF_CELLS * CELL_UNITS;
    return placed;
}

static void start_pass(const BenchPass *plan)
{
    memcpy(g_level.entities, g_level_entities_pristine, sizeof(g_level.entities));
    game_init(&g_state, &g_level, g_level.rng_seed);
    if (plan->fixture == FIXTURE_NOSE_TO_WALL) {
        place_nose_to_wall();
    } else if (plan->fixture == FIXTURE_NEAR_SPRITES) {
        place_near_sprites();
    }
    /* LAST, because the near-sprite fixture re-runs game_init and that resets the detail level to
     * the engine's DETAIL_DEFAULT — which DESIGN v2.1 17.3 has since made 80 columns, so a pass
     * asking for 160 silently measured 80 until this moved down here. */
    g_state.detail_level = plan->detail;
}

/* One frame of a pass: the scripted tick, then the whole render. `timed` is 0 for the rebuild that
 * puts the captured pass back on screen, which must not pollute its own measurements. */
static void bench_frame(const BenchPass *plan, unsigned long frame, BiPassLedger *pass, int timed)
{
    HudState hud;
    FrameCost cost;
    unsigned long sim_start = bi_ticks();
    unsigned long sim_end;

    if (plan->fixture == FIXTURE_SCRIPT) {
        game_step(&g_state, BENCH_SCRIPT[frame]);
    }
    sim_end = bi_ticks();
    hud_state_from_game(&hud, 0, 0);
    render_frame_into_back(&hud, &cost);
    cost.stage[STAGE_SIM] = sim_end - sim_start;
    cost.total += cost.stage[STAGE_SIM];
    if (timed) {
        record_frame(pass, &cost);
    }
    flip();
}

static void run_pass(unsigned long index, int timed)
{
    const BenchPass *plan = &BENCH_PASSES[index];
    BiPassLedger *pass = &g_ledger.pass[index];
    unsigned long frame;
    int i;

    start_pass(plan);
    if (timed) {
        for (i = 0; i < BI_LEDGER_NAME_BYTES; ++i) {
            pass->name[i] = plan->name[i];
        }
        pass->columns = render_columns(&g_state)->count;
    }
    for (frame = 0; frame < BENCH_SCRIPT_TICKS; ++frame) {
        bench_frame(plan, frame, pass, timed);
    }
}

/*
 * Hold the captured frame on screen, REDRAWING it rather than idling. Hatari's `screenshot` hands
 * back the last surface it RENDERED, and under --fast-forward that is not necessarily the frame the
 * debugger stopped on; were this an idle loop the captured picture could be a frame from an earlier
 * pass, at a different column count from the numbers published beside it.
 */
static void hold_capture(void)
{
    unsigned long until = g_vbl_count + BENCH_HOLD_VBLS;

    while (g_vbl_count < until) {
        HudState hud;
        FrameCost cost;

        hud_state_from_game(&hud, 0, 0);
        render_frame_into_back(&hud, &cost);
        flip();
    }
}

static void bench(void)
{
    unsigned long index;

    g_ledger.version = BI_LEDGER_VERSION;
    g_ledger.tick_ns = TIMER_TICK_NS;
    g_ledger.cpu_hz = ST_CPU_HZ;
    g_ledger.pass_count = BI_BENCH_PASSES;
    g_ledger.stage_count = BI_STAGES;
    g_ledger.capture_pass = BENCH_CAPTURE_PASS;
    g_ledger.capture_frame = BENCH_CAPTURE_FRAME;
    g_ledger.timer_c_max = probe_timer_c();
    for (index = 0; index < BI_BENCH_PASSES; ++index) {
        run_pass(index, 1);
    }
    g_ledger.cast_mismatches = g_cast_mismatches;
    g_ledger.song_accept = (unsigned long)g_music_ready;
    g_ledger.bank_accept = (unsigned long)g_drums_ready;
    /* The captured pass is replayed once more, untimed, so the picture on screen belongs to it:
     * Hatari's screenshot hands back the last surface RENDERED, and the last TIMED pass is not
     * necessarily the one the ledger names. */
    if (BENCH_CAPTURE_PASS != BI_BENCH_PASSES - 1) {
        run_pass(BENCH_CAPTURE_PASS, 0);
    }
    hold_capture();
    publish_ledger();
}

#endif /* BLACKICE_BENCH */

/* ---------------------------------------------------------------- the run --------------------- */

#define PAK_FILENAME    "\\BLACKICE.PAK"

#ifdef BLACKICE_BENCH

/*
 * The ledger sits at a fixed absolute address so a debugger script can find it. It must be clear of
 * the .bss image below it and of the stack above it; the linker gives us the first bound and GEMDOS
 * the second, so both are checked rather than assumed.
 *
 * ONLY THE BENCH BUILD REFUSES ON THIS. The game writes nothing to BI_LEDGER_ADDR — it has no
 * ledger — so gating it on an address it never touches would have refused to start a perfectly good
 * game on any machine whose GEMDOS put the program somewhere this arithmetic did not like.
 */
extern char _bss_end[];
#define LEDGER_STACK_MARGIN 0x4000

static const char *ledger_placement_error(void)
{
    unsigned long stack_here = (unsigned long)&stack_here;

    if ((unsigned long)_bss_end >= BI_LEDGER_ADDR) {
        return "REFUSED: the BSS image has grown into the ledger address\r\n";
    }
    if (BI_LEDGER_ADDR + BI_LEDGER_CAPTURE_BYTES + LEDGER_STACK_MARGIN > stack_here) {
        return "REFUSED: the ledger address is inside the stack\r\n";
    }
    return 0;
}

#else

/* The game has no ledger, so it has nothing to place. */
static const char *ledger_placement_error(void)
{
    return 0;
}

#endif /* BLACKICE_BENCH */

static const char *const ASSET_ERRORS[] = {
    "", "cannot open BLACKICE.PAK", "BLACKICE.PAK read failed", "BLACKICE.PAK is not an archive",
    "BLACKICE.PAK is missing a resource", "a resource is larger than the read buffer",
    "the resource arena is too small", "a packed resource is corrupt",
    "a resource is the wrong shape", "the level blob was rejected"
};

int blackice_main(void)
{
    AssetsResult loaded;
    const char *placement;

    Cconws(CURSOR_OFF);
    placement = ledger_placement_error();
    if (placement) {
        Cconws(placement);
        return 1;
    }
    loaded = assets_load(PAK_FILENAME, &g_level);
    if (loaded != ASSETS_OK) {
        Cconws("BLACK ICE: ");
        Cconws(ASSET_ERRORS[loaded]);
        Cconws("\r\n");
        return 1;
    }
    /* The authored entity list as the archive delivered sector 0, for the bench fixtures; the game
     * re-takes it after every level load in run_the_game. */
    memcpy(g_level_entities_pristine, g_level.entities, sizeof(g_level.entities));
    tables_init();
    {
        int row;

        for (row = 0; row < RENDER_H; ++row) {
            bi_chunky_row_offset[row] = (uint16_t)(row * CHUNKY_ROW_BYTES);
        }
    }
    build_c2p_table(bi_c2p_table_high, C2P_POSITIONS_HIGH, SCREEN_W / RENDER_COLUMNS_HIGH);
    build_c2p_table(bi_c2p_table_low, C2P_POSITIONS_LOW, SCREEN_W / RENDER_COLUMNS_LOW);
    /* The level's own seed, which is what DESIGN 4.3 says and what host/main_host.c uses when no
     * --seed is given — and atari/verify.py gives none. The two runs must seed identically or the
     * pixel comparison measures a different world. */
    game_init(&g_state, &g_level, g_level.rng_seed);

    g_saved_physbase = (void *)Physbase();
    g_saved_logbase = (void *)Logbase();
    g_saved_rez = (short)Getrez();
    if (monitor_cannot_show_the_game()) {
        Cconws("BLACK ICE: needs a colour monitor - ST Low is the only resolution it draws\r\n");
        return 1;
    }
    ikbd_write(IKBD_MOUSE_OFF, sizeof(IKBD_MOUSE_OFF));
    ikbd_write(IKBD_JOYSTICK_EVENTS, sizeof(IKBD_JOYSTICK_EVENTS));
    enter_game_video();

    g_saved_ssp = (void *)Super(0);
    /* BRIEF.md's floppy gotcha: the load is finished, so nothing of ours needs a drive selected.
     * This is the first thing done under Super because it is the one that has been waiting for
     * supervisor mode since the archive closed. */
    bi_floppy_deselect();
    /*
     * SILENCE TOS. Every keypress makes the system key click, and an alert makes the bell, both
     * through the PSG this program's music driver owns — TOS playing over the top of the game. The
     * byte is saved and put back on the way out, because it is the user's setting and not ours.
     * Bit 3, the key repeat, is deliberately left as it was: read_input sees makes and repeats and
     * never a release, so the held-key controls depend on it.
     */
    g_saved_conterm = *(volatile uint8_t *)CONTERM_ADDR;
    *(volatile uint8_t *)CONTERM_ADDR =
        (uint8_t)(g_saved_conterm & (uint8_t)~(CONTERM_KEYCLICK | CONTERM_BELL));
    save_palette(g_saved_palette);
    build_palette_variants();
    set_palette(g_palette_variants[PALETTE_VARIANT_CLEAN]);
    g_music_ready = ym_music_init(blackice_score, BLACKICE_SCORE_BYTES);
    g_drums_ready = dma_sfx_init(blackice_sfx_bank, BLACKICE_SFX_BANK_BYTES);
    if (g_music_ready) {
        ym_music_start();
    }
    install_vectors();

#ifdef BLACKICE_BENCH
    bench();
#else
    run_the_game();
#endif

    remove_vectors();
    if (g_music_ready) {
        ym_music_stop();
    }
    if (g_drums_ready) {
        dma_sfx_stop();
    }
    leave_game_video();
    bi_leave_supervisor(g_saved_ssp);

    ikbd_write(IKBD_JOYSTICK_OFF, sizeof(IKBD_JOYSTICK_OFF));
    ikbd_write(IKBD_MOUSE_RELATIVE, sizeof(IKBD_MOUSE_RELATIVE));
#ifdef BLACKICE_BENCH
    write_bench_text();
    write_bench_file();
    Cconws(g_text);
#endif
    return 0;
}
