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
#define A_troll_state           0x10dc4u  /* .w — see TROLL_STATE_* */
#define A_troll_x               0x10dd0u  /* .w — the hand's pixel column... */
#define A_troll_y               0x10dd2u  /* .w — ...and the scanline its wrist is on */
#define A_troll_target          0x10dd4u  /* .l — the object it has hold of */
#define A_troll_frame           0x10ddau  /* .w — a BYTE offset into troll_sprite_table */
#define A_troll_step_timer      0x10dddu  /* .b — frames left before the hand steps a sprite */
#define A_troll_sprite_table    0x14abau  /* TROLL_SPR_* records, one per hand frame */
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
/* One ASCII DIGIT of the object's score string (include/score.h lays the string out): the second
 * from the right, the rightmost being the units the game holds at '0'. A caller adds its points
 * straight into this byte — `addq.b #5,67(a0)` is 50 points, not 500 — and score_update then
 * carries the decimal columns. */
#define OBJ_SCORE_PENDING   0x43u  /* .b */
#define OBJ_FLAG_PLAYER     0x0004u  /* bit2 — not an enemy; only a player is paid for an escape */
#define OBJ_FLAG_GRABBED    0x0010u  /* bit4 — the lava troll has hold of this object */
/* bit12 — the slot is on its way OFF the board, as opposed to merely OBJ_FLAG_DEAD (joust.h's
 * bit13, which a freshly hatched rider carries too). The two are set together by every death:
 * `bset #13` then `bset #12`, at 0x13ac8 / 0x13e72 in collision_check and at 0x14098 here.
 *
 * update_objects also latches it alone. `btst #12,d0` at 0x12438 branches to 0x124a6 while it is
 * clear; that tests OBJ_EGG_STATE and, when the state has run down to 0, does `bset #12,d0` at
 * 0x124ac and branches back to the same btst — which now falls through to the removal tail: the
 * off-playfield x compares, `jsr draw_object_mask` to erase, and `clr.l d0`, zeroing the flags word
 * and freeing the slot. render_object_body is the other reader: inside its bit-13 branch,
 * `btst #12,d0` at 0x12faa skips the draw_half_select `bset`s for an object already being removed.
 *
 * Both readers live in routines that are not ported yet, which is why nothing in the differential
 * exercises this bit — only start_death_anim, which sets it. */
#define OBJ_FLAG_REMOVED    (1u << 12)

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
#define TROLL_STATE_HAND_OUT     1u        /* `btst #0,d0` — the hand is on screen */
#define TROLL_STATE_HOLDING      0x2u     /* bit1 — ...and it has hold of troll_target */
#define TROLL_STATE_FACING_RIGHT 0x4u     /* bit2 — copied off the target when the hand is raised;
                                           * the sprite set has one direction, so nothing reads it */
/* One rotated longword of AND mask per row. Same sprite layout as SPR_MASK_OFF above, and the same
 * value as src/draw.c's SPR_MASK_ROW_BYTES — that one is private to draw.c, so hoisting it into
 * draw.h next to SPR_MASK_OFF would collapse the pair. Flagged for the drawing layer. */
#define TROLL_MASK_ROW_BYTES  4u

/* ---- troll_sprite_table record: one hand frame, indexed by troll_frame's BYTE offset ---- */
#define TROLL_SPR_SRC     0x0u  /* .l — the sprite; its AND mask sits SPR_MASK_OFF in */
#define TROLL_SPR_ROWS    0x4u  /* .w */

#define TROLL_FIRST_WAVE   4     /* `cmpi.b #4,wave_num ; blt` — a SIGNED byte compare */
#define TROLL_STEP_PERIOD  2u    /* the timer's reload: the hand steps a frame every third call */
#define TROLL_TIMER_ARMED  0xffu /* what a freshly raised hand starts on — negative, so the very
                                  * next call reloads it and the first frame is held an extra tick */

/* The hand fishes at the two ENDS of the lava: `x - 0x32` must be ABOVE 0xdc as an unsigned word,
 * i.e. x < 0x32 or x > 0x10e. Everything between is the ground, where nothing can fall in. */
#define TROLL_PIT_X0    0x32u
#define TROLL_PIT_SPAN  0xdcu
#define TROLL_REACH_Y   0x8fu    /* an object above this scanline is out of reach (signed) */
#define TROLL_GRAB_DX   0xcu     /* ...and it must be within this many pixels to the hand's right */
#define TROLL_GRAB_DX_WRAPPED 0xfeccu  /* the same window measured the other way round the screen,
                                        * as a SIGNED word: -0x134 == 0xc - TROLL_X_WRAP */
#define TROLL_GRAB_DY   0xbu     /* contact: the hand is this close under the object (unsigned) */
#define TROLL_ESCAPE_Y  0x8cu    /* a held object that climbs above this line is free (signed) */
#define TROLL_ESCAPE_SCORE 5u    /* `addq.b #5,67(a0)` — what a player is paid for the escape */

#define TROLL_ARM_Y        0xafu    /* the scanline a new hand rises from... */
#define TROLL_ARM_X_BACK   0xcu     /* ...and how far LEFT of its target it starts */
#define TROLL_ARM_ROWS     9u       /* the prev_* block a new hand's first erase pass undoes: */
#define TROLL_ARM_PREV_SRC 0x18f0au /* the first sprite (a RELOCATED immediate, so an address)... */
#define TROLL_ARM_PREV_DST 0x5dc0u  /* ...and an offset from screen_base (not relocated) */

#define TROLL_HOLD_DY 0xcu       /* a held object is carried this far above the hand's wrist... */
#define TROLL_HOLD_DX 2u         /* ...and two pixels to its right */

#define TROLL_FRAME_STEP       8u     /* `addq.w #8` — one whole record of the table, which is
                                      * why the same value is the climb's step and the stride */
#define TROLL_FRAME_CLIMB_LAST 0x10u  /* the climb stops stepping here (an UNSIGNED clamp) */
#define TROLL_FRAME_HELD       0x18u  /* the frame a hand with something in it uses */

/* The playfield width in pixels (`addi.w #$140` / `subi.w #$140`), written as the derivation of the
 * scanline geometry rather than as 320 so that the two cannot drift apart. */
#define TROLL_X_WRAP  (SCREEN_ROW_BYTES / CELL_BYTES * CELL_PIXELS)
/* `lsr.l #8 ; lsr.l #5` on the SWAPPED divu result: 16 - log2(CELL_BYTES), i.e. the cell index
 * scaled straight to bytes with the pixel remainder shifted out underneath it. */
#define TROLL_CELL_SHIFT  13u

/* --- world.c --- */
void draw_platforms(uint8_t *image);
void raise_floor(uint8_t *image);
void flash_spawn_pad(uint8_t *image, uint32_t object, uint32_t flags);
void troll_erase_hand(uint8_t *image);
void troll_draw_hand(uint8_t *image, uint32_t state);
void lava_troll(uint8_t *image);
uint32_t start_death_anim(uint8_t *image, uint32_t object, uint32_t flags);
void animate_ground_shrink(uint8_t *image);
void dissolve_platforms(uint8_t *image);

#endif /* JOUST_WORLD_H */
