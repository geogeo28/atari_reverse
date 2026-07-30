/* world.h — the world layer: the platforms and their dissolve, the rising lava floor, the ground
 * burn, the spawn pad, the lava troll's hand and the sprite a killed rider leaves behind.
 *
 * Every A_* address is a Ghidra address (image offset + the 0x10000 load base) and mirrors a `var`
 * line in ../../names.txt, which stays the source of truth for the name. Only what this layer
 * alone touches is declared here: the globals the drawing and object layers read too are in
 * addrs.h, the object record and the 68000 primitives in joust.h, the sprite/platform record
 * layouts in draw.h and object.h.
 */
#ifndef JOUST_WORLD_H
#define JOUST_WORLD_H

#include <stdint.h>

#include "addrs.h"
#include "draw.h"
#include "joust.h"
#include "object.h"

/* ---- globals ---- */
#define A_wave_num              0x10cf3u  /* .b — 0-based; the ground burn only shrinks on wave 3 */
#define A_floor_step_timer      0x10d64u  /* .b — frames left before the lava rises one more row */
#define A_floor_rows_left       0x10d65u  /* .b — rows of lava still owed; 0 = the floor is done */
#define A_ground_anim_timer     0x10d66u  /* .b — frames left before the ground burn steps */
#define A_ground_anim           0x10d68u  /* the live ground-burn state block (GA_* below) */
#define A_ground_anim_next      0x10d84u  /* the frame's working copy, blitted then copied back */
#define A_troll_prev_dst        0x10dc6u  /* .l — screen offset the hand was last drawn at */
#define A_troll_prev_src        0x10dcau  /* .l — and the sprite it was drawn from */
#define A_troll_prev_shift      0x10dceu  /* .w */
#define A_troll_prev_rows       0x10dd8u  /* .w */
#define A_effect_table          0x1137au  /* the dissolve slots (EFF_* below) */
#define A_effect_table_END      0x113bau  /* == pterodactyl_table, the original's own `cmpa.l` bound */
#define A_ground_x0             0x117b8u  /* .w — platform 0's landable left edge (== PLAT_X0) */
#define A_ground_x1             0x117bau  /* .w — and its right edge (== PLAT_X1) */
#define A_spawn_pad_colors      0x11944u  /* .b[8] — one plane-select byte per flash phase */
#define A_spawn_pad_pattern     0x1194cu  /* the pad's three row masks */
#define A_spawn_points          0x11964u  /* SPAWN_* records, indexed by a byte offset */
#define A_death_sprite_p1       0x1922au  /* the dismount sprite player 1 leaves behind */
#define A_death_sprite_other    0x193dau  /* ... and everyone else's */

/* ---- object-record fields only this layer touches. They belong in joust.h the moment a second
 *      subsystem reads them, the way addrs.h describes for globals. ---- */
#define OBJ_EGG_CHAIN       0x35u  /* .b — consecutive-egg counter, reset when the rider dies */
#define OBJ_SCORE_PENDING   0x43u  /* .b — score to award, in hundreds (`addq.b #5` = 500) */
#define OBJ_FLAG_DEAD       (1u << 13)
#define OBJ_FLAG_REMOVED    (1u << 12)

/* ---- platform_sprites fields the redraw pass needs; object.h names the rest of the record ---- */
#define PSPR_COLS  0x6u  /* .w — cells per row */
#define PSPR_SRC   0x8u  /* .l — the platform bitmap */

/* ---- draw_platforms ---- */
#define PLATFORM_COUNT  8u     /* `moveq #$8,d7` */
#define PLATFORM_SPENT  0xffu  /* the countdown latches here, and -1 is <= 0 on the next pass */

/* ---- raise_floor ---- */
#define FLOOR_STEP_FRAMES    7u     /* one lava row every 7 calls */
/* The original hands paint_floor_row an ADDRESS REGISTER that the callee leaves advanced past the
 * cells it painted, then adds 0x50 to it before calling again. The C paint_floor_row takes its row
 * by value, so the advance has to be spelled out here; test_world.py pins it equal to
 * src/draw.c's FLOOR_ROW_CELLS * CELL_BYTES. */
#define FLOOR_PAINT_ADVANCE  0x28u  /* what one paint_floor_row call consumes */
#define FLOOR_SECOND_STRIP   0x50u  /* `adda.l #$50,a1` between the two calls */

/* ---- flash_spawn_pad: the pad is three scanlines of three cells, and the pattern's three row
 *      masks sit SPAWN_PAD_ROW_STRIDE apart while its per-cell columns sit two bytes apart ---- */
#define SPAWN_PAD_CELLS       3u
#define SPAWN_PAD_ROW_STRIDE  8u
#define SPAWN_PAD_CELL_STRIDE 2u
#define SPAWN_PAD_PHASE_MASK  3u  /* `and.l #$3` on the rider's step timer */
#define SPAWN_PAD_PHASE_ALT   1u  /* the one phase that takes its colour from the flags instead */
#define SPAWN_PAD_ALT_FLAG    4u  /* `btst #2,d0` — the flag bit that arms that substitution */
#define SPAWN_PAD_COLOR_MASK  7u  /* `moveq #$7 ; and.l d0,d1` — index into A_spawn_pad_colors */

/* ---- spawn_points record ---- */
#define SPAWN_SHIFT    0x1u  /* .b — pixels into the leading cell */
#define SPAWN_DST_OFF  0xeu  /* .w — SIGN-extended, added to screen_base */

/* ---- the ground-burn state block (0x1c bytes, mirrored at A_ground_anim_next) ---- */
#define GA_ROWS_LATCH   0x00u  /* .w — copy of GA_ROWS; <= 0 disarms the whole routine */
#define GA_ROWS         0x02u  /* .w — rows both flames are blitted with */
#define GA_FLAME_LEFT   0x04u  /* an SPR_* record — the flame eating rightwards */
#define GA_FLAME_RIGHT  0x10u  /* an SPR_* record — the flame eating leftwards */
#define GA_BLOCK_BYTES  0x1cu  /* the copy loop's `move.l` at d0 = 0x18 down to 0 */

/* The flame is four 18-row frames laid end to end; the cursor walks one frame per step and wraps. */
#define FLAME_FRAME_BYTES  0xd8u
#define FLAME_FRAME_FIRST  0x18636u
#define FLAME_FRAME_END    0x18996u  /* one past the last frame (`cmpi.l` + `blt`, so SIGNED) */

#define GROUND_ANIM_PERIOD   3u      /* the burn steps every third call */
#define GROUND_SINK_SHIFT    0xcu    /* the right flame's phase at which a sink may start */
#define GROUND_SINK_GAP      0x60    /* ... and the byte gap under which the flames count as met */
#define GROUND_ROWS_MIN      0x11    /* below this the flames climb back up a row */
#define GROUND_SHRINK_WAVE   3u      /* only wave 3 narrows the ground's landable x range */
#define GROUND_X1_WRAP       0x13e   /* past here the two edges restart from... */
#define GROUND_X1_RESET      0x134
#define GROUND_X0_RESET      0xfff5  /* ... -11, i.e. just off the left of the screen */

/* ---- effect_table record (0x10 bytes): one dissolving platform ---- */
#define EFF_TIMER   0x00u  /* .w — DISSOLVE_FRAMES down to 0; 1 is the last, noise-free frame */
#define EFF_KIND    0x02u  /* .w — 1-based platform index; 0 = free slot */
#define EFF_ROWS    0x04u  /* .w — copied from PSPR_ROWS (with EFF_COLS, as one longword) */
#define EFF_COLS    0x06u  /* .w — copied from PSPR_COLS; re-read once per row */
#define EFF_SRC     0x08u  /* .l — bitmap cursor, left where the previous pass ran to */
#define EFF_DST     0x0cu  /* .l — screen cursor, likewise; the dissolve walks BACKWARDS from it */
#define EFF_RECORD  0x10u

#define DISSOLVE_FRAMES  0x1au
#define DISSOLVE_LAST_FRAME 1  /* `cmpi.w #$1` — the frame that lays no noise */
/* platform_sprites indexed by a 1-BASED kind, so the base is one record below the table. */
#define DISSOLVE_SPRITE_BASE  (A_platform_sprites - PSPR_RECORD)
/* Offset of a cell's planes-2-and-3 half: the WORD the setup pass masks (plane 2), and the
 * LONGWORD the crumble ORs its noise into. Planes 0 and 1 are the cell's first half. */
#define DISSOLVE_PLANE23  4u
#define DISSOLVE_PLANE3   (DISSOLVE_PLANE23 + 2u)  /* the platform's silhouette lives in plane 3 */
#define DISSOLVE_NOISE_ADVANCE  0x8eu  /* rng_ptr is nudged this far before rng_advance re-steps it */

/* ---- lava troll ---- */
#define TROLL_STATE_HAND_OUT  1u  /* `btst #0,d0` — the hand is on screen */
/* One rotated longword of AND mask per row. Same sprite layout as SPR_MASK_OFF above, and the same
 * value as src/draw.c's SPR_MASK_ROW_BYTES — that one is private to draw.c, so hoisting it into
 * draw.h next to SPR_MASK_OFF would collapse the pair. Flagged for the drawing layer. */
#define TROLL_MASK_ROW_BYTES  4u

/* --- world.c --- */
void draw_platforms(uint8_t *image);
void raise_floor(uint8_t *image);
void flash_spawn_pad(uint8_t *image, uint32_t object, uint32_t flags);
void troll_erase_hand(uint8_t *image);
void troll_draw_hand(uint8_t *image, uint32_t state);
uint32_t start_death_anim(uint8_t *image, uint32_t object, uint32_t flags);
void animate_ground_shrink(uint8_t *image);
void dissolve_platforms(uint8_t *image);

#endif /* JOUST_WORLD_H */
