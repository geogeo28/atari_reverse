/* plat.h — every constant the platform C and the platform asm must agree on.
 *
 * render.S and os.S are `.S` (capital) so cpp runs over them: this file is the ONE definition of
 * the hardware addresses, the chunky-buffer layout, the c2p table shape and the RenderColumn /
 * RenderSprite field offsets the asm reads. A value spelled once in C and once as an asm literal
 * is exactly the drift that shows up as a frame one word wide of the truth, so nothing here is
 * duplicated. The struct offsets are pinned against the engine's own structs by _Static_assert in
 * main.c, so a change in include/render.h fails the build rather than the picture.
 *
 * Lifted from spike/spike.h, which is canonical for the chunky-buffer-as-pair-word design and for
 * the c2p table shape; the engine's geometry (80 rows, a 40-line HUD, a shade LUT per column)
 * replaces the spike's.
 */
#ifndef BLACKICE_PLAT_H
#define BLACKICE_PLAT_H

/* ---------------------------------------------------------------- the machine ---------------- */
#define ST_CPU_HZ                   8000000L    /* nominal 8 MHz; PAL ST is 8.0106 MHz */
#define PLAT_SCREEN_BYTES_PER_LINE  160         /* 16 px = 4 interleaved plane words = 8 bytes */
#define PLAT_SCREEN_BYTES           32000
#define PLAT_SCREEN_ALIGN           256         /* the shifter's base register is 256-granular */
#define SCREEN_GROUP_BYTES          8       /* one 16-pixel group, all four planes */
#define GROUPS_PER_LINE             (PLAT_SCREEN_BYTES_PER_LINE / SCREEN_GROUP_BYTES)  /* 20 */

/* Shifter, palette and the STE's low byte of the video base. */
#define VIDEO_BASE_HIGH_ADDR        0xffff8201L
#define VIDEO_BASE_MID_ADDR         0xffff8203L
#define VIDEO_BASE_LOW_ADDR         0xffff820dL /* STE only; 0 keeps us 256-aligned */
#define PALETTE_ADDR                0xffff8240L
#define PALETTE_PENS                16

/* TOS's own record of the screen base. Its vertical blank reloads the shifter from this on EVERY
 * blank, so a page flip that writes only the hardware registers is undone a few microseconds later
 * on every blank but the one it happened on. */
#define V_BAS_AD_ADDR               0x44e

/* MFP timer C is TOS's own 200 Hz tick; the sub-tick part is its down-counter. */
#define HZ_200_ADDR                 0x4ba       /* _hz_200, a long, supervisor-only */
#define FRCLOCK_ADDR                0x466       /* TOS's VBL frame counter, supervisor-only */
#define TIMER_C_DATA_ADDR           0xfffffa23L /* MFP TCDR */
#define TIMER_C_RELOAD              192         /* 2457600 / 64 / 192 == 200 Hz exactly */
#define TIMER_TICK_NS               26042L      /* 64 / 2457600 s, rounded */

/* TOS's vertical-blank queue: a count and a pointer to that many routine slots. TOS sets the
 * shifter base from _v_bas_ad and THEN walks the queue, which is why the page flip lives in a
 * queue slot and not on the level-4 vector (see os.S). */
#define NVBLS_ADDR                  0x454       /* short: slots in the queue */
#define VBLQUEUE_ADDR               0x456       /* long: pointer to the slot array */
/* The level-4 autovector, which the fallback install chains (os.S). */
#define VBL_VECTOR_ADDR             0x70

/* Shifter resolutions, as Getrez reports them and Setscreen takes them. */
#define REZ_ST_LOW                  0           /* 320x200, 16 colours: the only one this draws */
#define REZ_ST_HIGH                 2           /* 640x400 mono, and a monitor that cannot show 0 */


/* ---------------------------------------------------------------- the render window -----------
 * The engine's window: 160x80 logical pixels doubled to 320x160, over a 40-line HUD.
 *
 * THESE RESTATE include/game_consts.h AND THAT IS DELIBERATE: render.S is assembled through cpp,
 * which cannot swallow game_consts.h (it pulls in fixed.h's typedefs and inline functions). Every
 * one is pinned to the engine's own value by a _Static_assert in main.c, so a change in
 * include/ fails the build rather than the picture. */
#define PLAT_RENDER_H               80          /* == RENDER_H */
#define PLAT_COLUMNS_HIGH           160         /* == RENDER_COLUMNS_HIGH */
#define PLAT_COLUMNS_LOW            80          /* == RENDER_COLUMNS_LOW */
#define PLAT_TEX_DIM                64          /* == TEX_DIM */
#define PLAT_SHADE_LEVELS           6           /* == SHADE_LEVEL_COUNT */
#define PLAT_WALL_TEX_SLOTS         16          /* == WALL_TEXTURE_MAX + 1 */
#define PLAT_SPRITE_TRANSPARENT     15          /* == SPRITE_TRANSPARENT */
#define PLAT_SPRITE_MAX_VISIBLE     32          /* == SPRITE_MAX_VISIBLE */

#define VIEW_PAIRS_HIGH             (PLAT_COLUMNS_HIGH / 2)   /* 80 */
/*
 * THE CHUNKY BUFFER'S ROW PITCH IS A CONSTANT, at both detail levels, and that is what lets the
 * column drawer's unrolled body address eight rows with literal displacements instead of walking a
 * runtime stride. At 80 columns a row uses the first half of its 160 bytes and the rest is not
 * touched; the buffer was always allocated at the wide size, so the waste is address space that was
 * already there. The c2p pays for it with one `lea` per row in the low-detail routine.
 */
#define CHUNKY_ROW_BYTES            (VIEW_PAIRS_HIGH * 2)     /* 160 */
#define CHUNKY_WORDS                (VIEW_PAIRS_HIGH * PLAT_RENDER_H)
/* Screen bytes one logical view row covers: two scanlines, because the view is pixel-doubled. */
#define VIEW_ROW_BYTES              (2 * PLAT_SCREEN_BYTES_PER_LINE)

/* ---------------------------------------------------------------- chunky <-> planar ----------- */
/* THE CHUNKY BUFFER HOLDS ONE WORD PER PIXEL *PAIR*, and the word is already the c2p table's byte
 * offset: pair = even*16 + odd, offset = pair * C2P_ENTRY_BYTES. The even column of a pair writes
 * the word (`move.w`) and the odd column ORs into it (`or.w`), so no clear pass is needed and the
 * c2p does ONE table lookup per two logical pixels instead of two.
 *
 * spike/REPORT.md measured the alternatives: a byte-per-pixel chunky buffer costs the c2p four
 * extra indexed longword reads per 16-pixel group (~156,000 cycles a frame at 160 columns) to save
 * 4 cycles on half the drawn pixels (~32,000), and a 16-bit-index table is 512 KB per plane pair
 * on a 1 MB machine. This layout is internal to the platform: the engine's contract is the
 * RenderColumn / RenderSprite lists in and the planar picture out (include/render.h). */
#define C2P_ENTRY_BYTES             8       /* planes 0/1 long at +0, planes 2/3 long at +4 */
#define C2P_PLANE23_OFF             4
#define C2P_PAIR_COUNT              256
#define C2P_TABLE_BYTES             (C2P_PAIR_COUNT * C2P_ENTRY_BYTES)      /* one position */
#define C2P_POSITIONS_HIGH          4       /* 4 pairs == 8 logical px == one 16-px screen group */
#define C2P_POSITIONS_LOW           2       /* 2 pairs == 4 logical px == one 16-px screen group */
/* At 80 columns a chunky row is half the constant pitch, so the low-detail c2p skips the rest. */
#define C2P_LOW_ROW_SKIP            (CHUNKY_ROW_BYTES - GROUPS_PER_LINE * C2P_POSITIONS_LOW * 2)
#define PAIR_ODD_SCALE              C2P_ENTRY_BYTES         /* 8   */
#define PAIR_EVEN_SCALE             (16 * C2P_ENTRY_BYTES)  /* 128 */
/* The bits of a chunky word each parity owns, so a sprite can replace one pixel of a pair. */
#define PAIR_EVEN_MASK              (15 * PAIR_EVEN_SCALE)  /* 0x780 */
#define PAIR_ODD_MASK               (15 * PAIR_ODD_SCALE)   /* 0x078 */

/* ---------------------------------------------------------------- textures and sprites -------- */
/* SHADING IS A PER-PIXEL REMAP AND NOT A BAKED TEXTURE, and the arithmetic is why. The engine
 * shades through g_shade_lut[band + side], which is SHADE_LEVEL_COUNT (6) rows; a pre-shaded,
 * pre-pair-scaled copy of one 64x64 texture is 8 KB per (level, parity), so all six levels of the
 * ten resident textures would be 10 * 6 * 2 * 8 KB = 983 KB on a 1 MB machine. Instead a texture
 * is stored ONCE as 64x64 words holding `palette_index * 2`, and one 16-entry table per
 * (level, parity) turns that into the pair-scaled chunky word:
 *
 *     tex[u][v]  = index * 2                       (word, column major, TEX_WORD_COL_BYTES apart)
 *     shade[l][p][index] = g_shade_lut[l][index] * (p ? PAIR_ODD_SCALE : PAIR_EVEN_SCALE)
 *
 * The inner loop is then one indexed read into the texture and one into the 32-byte table, which
 * costs 14 cycles a pixel over spike/REPORT.md's pre-shaded texture (70 v 56 on the even column)
 * and 900 KB less RAM. The measured figures are in README.md. */
#define TEX_WORD_COL_BYTES          (PLAT_TEX_DIM * 2)  /* one texture column, word form */
#define TEX_WORD_BYTES              (PLAT_TEX_DIM * TEX_WORD_COL_BYTES)  /* one texture: 8192 */
#define SHADE_TABLE_ENTRIES         16
#define SHADE_TABLE_BYTES           (SHADE_TABLE_ENTRIES * 2)
#define SHADE_PARITY_COUNT          2
#define SHADE_LEVEL_BYTES           (SHADE_PARITY_COUNT * SHADE_TABLE_BYTES)    /* 64 */

/* ---------------------------------------------------------------- BiTables --------------------
 * The wall-texture slot table and the shade tables in ONE object, so the drawer's inner loop can
 * hold the whole of its indexed state in two address registers: %a4 on this structure for the
 * per-column setup, %a5 on the column's own 16-word shade table. Two separate objects would need
 * a third address register the loop does not have. */
#define TBL_TEX                     0                       /* const uint16_t *[WALL_TEX_SLOTS] */
#define TBL_TEX_SLOTS               PLAT_WALL_TEX_SLOTS     /* 16 */
#define TBL_SHADE                   (TBL_TEX + TBL_TEX_SLOTS * 4)
#define TBL_SIZEOF                  (TBL_SHADE + PLAT_SHADE_LEVELS * SHADE_LEVEL_BYTES)

/* ---------------------------------------------------------------- RenderColumn ---------------- */
/* include/render.h's 12-byte layout, restated for the asm and pinned by _Static_assert in main.c. */
#define COL_TEX_ID                  0       /* u8  0 == far fill, else wall texture id */
#define COL_TEX_COL                 1       /* u8  texture column 0..63 */
#define COL_TOP                     2       /* i16 first logical row of the wall */
#define COL_ROWS                    4       /* u16 rows to write */
#define COL_TEX_V                   6       /* u16 texel v at `top`, 8.8 */
#define COL_TEX_STEP                8       /* u16 texel v per row, 8.8 */
#define COL_BAND                    10      /* u8  depth band */
#define COL_SIDE                    11      /* u8  SIDE_NS / SIDE_EW */
#define COL_SIZEOF                  12

/* ---------------------------------------------------------------- RenderSprite ---------------- */
/* include/sprite.h's 26-byte 68000 layout. */
#define SPR_TEXELS                  0       /* const uint16_t * (word form; see the note above) */
#define SPR_SPANS                   4       /* const SpriteSpan * */
#define SPR_LEFT                    8       /* i16 */
#define SPR_COLS                    10      /* u16 */
#define SPR_TOP                     12      /* i16, MAY BE NEGATIVE */
#define SPR_ROWS                    14      /* u16 full projected height before row clipping */
#define SPR_TEX_U                   16      /* u16 8.8 */
#define SPR_TEX_STEP_U              18      /* u16 8.8 */
#define SPR_TEX_STEP_V              20      /* u16 8.8 */
#define SPR_DIST                    22      /* u16 map units, for the z test */
#define SPR_BAND                    24      /* u8, shade level is the band itself */
#define SPR_SIZEOF                  26
/* screen_row_of_texel() in src/sprite.c is `top + (texel_row * rows >> SPRITE_ROW_SHIFT)`. */
#define SPRITE_ROW_SHIFT            6

/* ---------------------------------------------------------------- BiDrawJob ------------------- */
/* One job describes every column of the frame and the asm walks the RenderColumn array itself.
 * spike/REPORT.md measured the alternative: a per-column C call around the same body cost 1,680
 * cycles to draw 13 pixels — the parameter block, the push and the prologue, ten times the pixels
 * — against about 120 cycles a column for the walked version. */
#define JOB_CHUNKY                  0       /* uint16_t *, band_top's row, pair 0 */
#define JOB_COLUMNS                 4       /* const RenderColumn * */
#define JOB_TABLES                  8       /* const BiTables * */
#define JOB_PAIRS                   12      /* i16, columns / 2 */
/* No stride: CHUNKY_ROW_BYTES is a constant and the drawer's displacements are literal. */
#define JOB_BAND_TOP                14      /* i16 */
#define JOB_BAND_BOTTOM             16      /* i16 */
#define JOB_VOID_EVEN               18      /* u16, COLOUR_VOID pair-scaled, the ceiling and floor */
#define JOB_VOID_ODD                20
#define JOB_FAR_EVEN                22      /* u16, COLOUR_FAR_FILL pair-scaled */
#define JOB_FAR_ODD                 24
#define JOB_SIZEOF                  26

/* ---------------------------------------------------------------- BiSpriteJob ----------------- */
#define SJOB_CHUNKY                 0       /* uint16_t *, logical row 0, pair 0 */
#define SJOB_SPRITES                4       /* const RenderSprite * */
#define SJOB_WALL_DIST              8       /* const uint16_t * */
#define SJOB_TABLES                 12      /* const BiTables * */
#define SJOB_COUNT                  16      /* i16 sprites */
#define SJOB_COLUMNS                18      /* i16 screen columns in this mode */
/* No stride: CHUNKY_ROW_BYTES is a constant and bi_chunky_row_offset[] has the row products. */
#define SJOB_BAND_TOP               20      /* i16 first row the drawer may write */
#define SJOB_BAND_BOTTOM            22      /* i16 one past the last row it may write */
#define SJOB_SIZEOF                 24

/* ---------------------------------------------------------------- the fill -------------------- */
/* bi_fill writes FILL_CHUNK_BYTES per MOVEM (ten registers), so its byte count must be a multiple
 * of 40. Every region it is asked for is a whole number of screen lines (160 bytes), so it is. */
#define FILL_CHUNK_BYTES            40

/* ---------------------------------------------------------------- the ledger ------------------ */
/* A FIXED absolute address so a Hatari debugger script can `savebin` it without knowing where
 * GEMDOS put us. We never Mshrink, so the whole TPA is ours: 0xc0000 is far above the BSS image
 * (main.c refuses to run if it is not) and far below the stack GEMDOS leaves at the top of RAM. */
#define BI_LEDGER_ADDR              0xc0000L
#define BI_LEDGER_MAGIC             0x424c4b31L /* 'BLK1' */
#define BI_LEDGER_VERSION           1
/* What atari/bench.py's debugger script `savebin`s from BI_LEDGER_ADDR: a fixed, generous window,
 * so the pass table can grow without the harness and the target having to move together. */
#define BI_LEDGER_CAPTURE_BYTES     4096
#define BI_STAGES                   7           /* sim, cast, columns, sprites, fill, c2p, hud */
#define BI_LEDGER_NAME_BYTES        8

/* ---------------------------------------------------------------- BiCastJob ------------------
 * Everything render_cast needs that does not change across a frame, hoisted so cast.S's per-ray
 * path is table reads and arithmetic and nothing else. The pointer fields are first so they stay
 * longword aligned; the offsets are pinned against the C struct by _Static_assert in main.c.
 *
 * The two `to_next` pairs are src/raycast.c's per-ray `(cosine >= 0) ? CELL_UNITS - frac : frac`,
 * which depends only on the player position: a branch per ray becomes an indexed pick.
 */
#define CJOB_COLUMNS            0       /* RenderColumn * */
#define CJOB_WALL_DIST          4       /* uint16_t * */
#define CJOB_ANGLE_TABLE        8       /* const int16_t *, the ColumnSet's per-column offsets */
#define CJOB_COS_TABLE          12      /* const uint16_t *, the fisheye correction, 1.14 */
#define CJOB_SIN_TABLE          16      /* const int16_t *, g_sin_1024 */
#define CJOB_INV_COS_TABLE      20      /* const uint16_t *, g_inv_cos_dist */
#define CJOB_GRID_CELLS         24      /* const uint8_t * */
#define CJOB_BLOCKING           28      /* const uint8_t *, the solid bitmap */
#define CJOB_DOORS              32      /* const Door * */
#define CJOB_DOOR_OF_CELL       36      /* const uint8_t * */
#define CJOB_SLICE_HEIGHT       40      /* const uint16_t *, g_slice_height */
#define CJOB_TEX_STEP           44      /* const uint16_t *, g_tex_step */
#define CJOB_CELL_TEXTURE       48      /* const uint8_t *, g_cell_texture */
#define CJOB_COUNT              52      /* u16 columns */
#define CJOB_PLAYER_ANGLE       54      /* u16 */
#define CJOB_POS_X              56      /* i16 map units */
#define CJOB_POS_Y              58
#define CJOB_MAX_TRACE          60      /* i16 map units, the throttle radius */
#define CJOB_START_INDEX        62      /* u16 grid index of the player's cell */
#define CJOB_MAP_X              64      /* i16 the player's cell */
#define CJOB_MAP_Y              66
#define CJOB_GRID_WIDTH         68      /* i16 */
#define CJOB_TO_NEXT_X_POS      70      /* u16 CELL_UNITS - (pos_x & CELL_FRAC_MASK) */
#define CJOB_TO_NEXT_X_NEG      72      /* u16 pos_x & CELL_FRAC_MASK */
#define CJOB_TO_NEXT_Y_POS      74
#define CJOB_TO_NEXT_Y_NEG      76
#define CJOB_BAND_LIMIT         78      /* u16 [BAND_COUNT - 1] */
#define CJOB_BAND_LAST          86      /* u8 */
#define CJOB_SIZEOF             88

/* src/fixed.h's and src/game_consts.h's, restated for the assembler and pinned in main.c. */
#define PLAT_TRIG_INDEX_SHIFT   6
#define PLAT_TRIG_SHIFT         14
#define PLAT_TRIG_QUARTER_BYTES 512     /* TRIG_QUARTER_ENTRIES * 2 */
#define PLAT_TRIG_WRAP_BYTES    0x7fe   /* (TRIG_TABLE_SIZE - 1) * 2, as a mask on a byte offset */
#define PLAT_CELL_SHIFT         8
#define PLAT_CELL_UNITS         256
#define PLAT_CELL_FRAC_MASK     255
#define PLAT_TEXEL_SHIFT        2       /* map units per texel: CELL_UNITS / TEX_DIM */
#define PLAT_TEX_INDEX_MASK     63
#define PLAT_DIST_TABLE_MAX     8191
#define PLAT_DELTA_DIST_NEVER   0xffff
#define PLAT_DDA_BEYOND_TRACE   5121    /* RENDER_RADIUS_MAX * CELL_UNITS + 1 */
#define PLAT_WALL_DIST_NONE     0xffff
#define PLAT_CELL_DOOR_BASE     16
#define PLAT_CELL_DOOR_MAX      31
#define PLAT_DOOR_NONE          0xff
#define PLAT_DOOR_STATE_OPEN    2
#define PLAT_DOOR_SIZEOF        8
#define PLAT_DOOR_STATE_OFF     5       /* offsetof(Door, state) */
#define PLAT_BAND_EDGES         4       /* BAND_COUNT - 1 */
#define PLAT_SIDE_NS            0       /* include/render.h's SIDE_NS */
#define PLAT_SIDE_EW            1

/* ---------------------------------------------------------------- the 68000's own divide -----
 * THE COST MODEL DEPENDS ON THIS. include/render.h's cycle model, and the parent Makefile's
 * `libgcc-gate` that enforces it, both say the same thing: a divide compiled as a call to libgcc's
 * __udivsi3 costs several times the DIVU it replaced, and in a per-frame path that is thousands of
 * cycles a frame for nothing. GCC will not pick DIVU on its own — the instruction is 32/16 -> 16
 * and C has no such operator — so the platform names it.
 *
 * THE CALLER GUARANTEES THE QUOTIENT FITS A WORD. On overflow the 68000 sets V and leaves the
 * destination UNTOUCHED, so the result would silently be the numerator's low word rather than a
 * wrong number; every call site below states the bound it relies on.
 */
#ifndef __ASSEMBLER__
#include <stdint.h>

static inline uint16_t divu16(uint32_t numerator, uint16_t denominator)
{
    uint32_t quotient = numerator;

    __asm__ ("divu.w %1,%0" : "+d"(quotient) : "dmi"(denominator));
    return (uint16_t)quotient;      /* the remainder rides in the high word */
}
#endif

#endif /* BLACKICE_PLAT_H */
