/* joust.h — the reconstruction's public API, plus what more than one subsystem shares: the screen
 * geometry, the 68000 primitives, and the object record.
 *
 * Joust runs on a 320x200 Atari ST low-resolution screen: 16 colours from four interleaved
 * bitplanes. Pixels are grouped into 16-pixel cells of four bitplane words, and every routine
 * here steps in whole cells, so the four constants below fix the entire memory layout.
 *
 * What belongs here is what two or more layers need; anything one layer owns stays in its own
 * header (draw.h, object.h, ...). The globals shared by address live in addrs.h instead.
 */
#ifndef JOUST_H
#define JOUST_H

#include <stdint.h>

#include "machine.h"   /* the shared 68000 primitives: loop_passes + COUNT_MASK_*, the rotates,
                        * the big-endian accessors. What is below is only what THIS game adds. */

#define SCREEN_ROW_BYTES 0xa0u   /* 160: one low-res scanline (320 px / 16 px per cell * 8 bytes) */
#define CELL_PIXELS      16u     /* pixels spanned by one 4-plane cell */
#define CELL_BYTES       8u      /* bytes in one 4-plane cell (four bitplane words) */
#define CELL_PLANE_WORDS 4u      /* those four words, the unit every plane-by-plane blit counts in
                                  * (`moveq #$4` in the original) */

/* ================================================================================================
 * 68000 semantics the reconstructions lean on. The width-independent ones (loop_passes and its
 * count masks, the 32- and 16-bit rotates) moved to the kit's machine.h, included above, so that
 * Zynaps' byte-identical copy could go away; what stays here is what only Joust's code shapes need.
 * ============================================================================================= */

/* A shift or rotate with a register count takes that count from the low 6 bits of the register,
 * then performs that many single-bit steps. For a shift that means anything >= 32 clears the
 * register; for a rotate, n steps of a longword is n mod 32, so the top bit never matters.
 *
 * The count's WIDTH is the caller's business, not this code's: the drawing layer feeds lsr32 a word
 * read of draw_shift and the object layer a byte read of the same address (see addrs.h), so each
 * call site passes a value of exactly the width its own instruction read. */
#define SHIFT_COUNT_MASK   0x3fu
#define ROTATE_COUNT_MASK  0x1fu

static inline uint32_t lsr32(uint32_t value, uint32_t count) {
    count &= SHIFT_COUNT_MASK;
    return count >= 32u ? 0u : value >> count;
}

static inline uint32_t ror32(uint32_t value, uint32_t count) {
    count &= ROTATE_COUNT_MASK;
    return count ? (value >> count) | (value << (32u - count)) : value;
}

/* DIVU.W leaves the destination as (remainder << 16) | quotient — unless the quotient would not fit
 * in 16 bits, in which case V is set and the destination is left UNCHANGED. No caller tests V, so
 * an out-of-range dividend simply carries forward undivided. */
static inline uint32_t divu_w(uint32_t dividend, uint16_t divisor) {
    uint32_t quotient = dividend / divisor;
    if (quotient > 0xffffu) return dividend;
    return ((dividend % divisor) << 16) | quotient;
}

/* ================================================================================================
 * The object record (0x4e bytes, object_table) — read by the drawing layer and the object layer
 * alike, so the layout is fixed once here. ../../names.txt documents the whole record; a field
 * earns a name here when a routine that uses it is ported.
 * ============================================================================================= */
#define OBJ_FLAGS           0x00u   /* .w */
#define OBJ_X               0x02u   /* .w */
#define OBJ_Y               0x04u   /* .w */
#define OBJ_VX              0x06u   /* .w */
#define OBJ_VY              0x08u   /* .w */
#define OBJ_ANIM_TIMER      0x0au   /* .b */
#define OBJ_STEP_TIMER      0x0bu   /* .b */
#define OBJ_TARGET_VX       0x0cu   /* .w — the horizontal speed the physics pass eases OBJ_VX to */
#define OBJ_FLAP_FRAME      0x0eu   /* .w */
#define OBJ_PREV_X          0x10u   /* .w */
#define OBJ_PREV_DST        0x14u   /* .l — last drawn screen address */
#define OBJ_PREV_SRC        0x18u   /* .l */
#define OBJ_PREV_ROWS       0x1cu   /* .b */
#define OBJ_PREV_SHIFT      0x1du   /* .b */
#define OBJ_EGG_STATE       0x1eu   /* .b */
#define OBJ_EGG_X           0x20u   /* .w */
#define OBJ_EGG_DST         0x2au   /* .l — screen address the egg sprite was drawn at */
#define OBJ_EGG_SRC         0x2eu   /* .l */
#define OBJ_EGG_ROWS        0x32u   /* .b */
#define OBJ_EGG_SHIFT       0x33u   /* .b */
#define OBJ_TARGET_Y        0x46u   /* .w — the altitude a rider steers toward: the hatch's AI
                                     * target, and the height a dead rider's hover aims for */
/* .b — frames left in the rider's current flap burst; 0 means "may start a new one". update_objects
 * counts it down each pass and clamps it to the wave's climb budget, and arms it to the dive length
 * when a type-3 commits; render_object_body's only write reloads it when an edge box parks a
 * type-3. ../../names.txt calls this the first of the pair of "AI timers". */
#define OBJ_FLAP_TIMER      0x49u
/* .b — how many sideways edge shoves the rider has taken. render_object_body bumps it once per
 * horizontal edge push (0x130c4); update_objects flips the facing and clears it at
 * TURN_TIMER_LIMIT, and clears it outright on respawn and on entering egg recovery. It counts
 * events, not frames — the "timer" is ../../names.txt's spelling for the pair. */
#define OBJ_TURN_TIMER      0x4bu
#define OBJ_SIZE            0x4eu

/* bit5 — this rider's x is comfortably inside the playfield (2 <= x < 0x12c). update_objects owns
 * it, on DEAD slots only: `bset #5` at 0x124c2 once the corpse's x is in that band, `bclr #5` at
 * 0x1243e the moment the slot enters the removal tail. It is the gate on both consequences — the
 * corpse walking back to its egg there, and render_object_body (its only reader, at 0x12f9c)
 * holding off the off-screen removal while it is set. Named for the position it records rather
 * than for either consequence, because the two readers act on it differently. */
#define OBJ_FLAG_CORPSE_INSIDE (1u << 5)

/* The flap trio. The joystick raises bits 6 and 11 TOGETHER (player.h's OBJ_FLAGS_FLAPPING, 0x840),
 * but update_objects' tails move them apart — 0x125b0 sets 11 and toggles 6, 0x125c0 clears 11 and
 * toggles 6 — so each carries its own meaning and its own name. */
#define OBJ_FLAG_WINGS_UP      (1u << 6)   /* the wings-up pose. It is TOGGLED, not set, which is
                                            * what makes the beat alternate; the sprite select at
                                            * 0x12f20 is what reads it. */
#define OBJ_FLAG_FLAP_REQUEST  (1u << 11)  /* a flap is being ASKED for this frame, by the stick or
                                            * by the AI */
/* bit10 — that request has already been acted on. render_object_body's edge detector sets it with
 * the upward kick (`bset #10,d0` at 0x12d2a, reached only when the `btst #11` at 0x12d1e finds a
 * request and the `btst #10` at 0x12d24 finds it untaken) and clears it once the request goes away
 * (0x12d80, 0x1321a, 0x135e8), which is why holding fire costs one kick rather than one per frame. */
#define OBJ_FLAG_FLAP_TAKEN    (1u << 10)

#define OBJ_FLAG_RESPAWN       (1u << 7)   /* awaiting respawn */
#define OBJ_FLAG_IN_LAVA       0x0100u     /* bit8: the sprite reached playfield_bottom while being drawn */
#define OBJ_FLAG_ON_PLATFORM   (1u << 9)   /* standing on a platform */
/* bit13 — this slot is not a live rider on the playfield. Set by every death (`bset #13` at 0x13ac8
 * / 0x13e72 in collision_check and at 0x14098 in start_death_anim, each immediately followed by the
 * `bset #12` of OBJ_FLAG_REMOVED) and, alone, by the egg hatch (`bset #13,d0` at 0x1277e) on the
 * rider it builds; cleared by `bclr #13,d0` at 0x1252a when update_objects places that rider. Read
 * by control_player, player_death, update_objects, render_object_body, collision_check, lava_troll
 * and ptero_spot_player — all three ported layers read it, hence its home here. */
#define OBJ_FLAG_DEAD          (1u << 13)
/* bit14 — this object's sprite overlapped a platform's bitmap this frame. collision_check's first
 * sweep sets it and nothing else does; render_object_body is its only reader, and answers it by
 * looking the object up in platform_edge_table and pushing it off the box it lands in — a lookup
 * that may find nothing, which is why the bit is named for the overlap that sets it rather than for
 * that response. names.txt calls it "bumped a platform edge". */
#define OBJ_FLAG_PLATFORM_BUMP (1u << 14)
#define OBJ_FLAG_FACING_RIGHT  0x8000u     /* bit15 — `btst #15,d0`, a bit test on the whole longword */

/* The rider TYPE, in the flags word's low two bits: 0 for a player, 1..3 for an enemy. The enemy
 * driver switches on the pair and the render pass compares against type 3, so the group is shared.
 * (The render pass also takes bits 0-2 together as one small number for the respawn branch — that
 * wider mask is render.h's, since nothing else reads bit 2.) */
#define ENEMY_TYPE_MASK  3u
/* The same pair one bit at a time, for the readers that take it that way: collision_check `btst`s
 * them separately to price a kill, and the sprite select reads bit 1 alone to tell the two players
 * apart. Anything reading the pair as a number uses ENEMY_TYPE_MASK above, which is the single
 * `andi #$3` the original issues there. */
#define OBJ_FLAG_TYPE_LO  (1u << 0)
#define OBJ_FLAG_TYPE_HI  (1u << 1)
#define ENEMY_TYPE_1     1u  /* cruises; climbs only while a player is above it */
#define ENEMY_TYPE_2     2u  /* claims a chase slot and homes in, then breaks off and retreats */
#define ENEMY_TYPE_3     3u  /* dives at a player below it, gliding through the dive */

/* --- rng.c --- */
void rng_advance(uint8_t *image, uint32_t mix);

/* --- screen.c --- */
uint32_t pos_to_screen(const uint8_t *image, uint16_t x, uint16_t y, uint16_t *shift);
void screen_to_pos(const uint8_t *image, uint32_t addr, uint16_t shift, uint16_t *x, uint16_t *y);

/* --- fill.c --- */
void make_fill_pattern(uint32_t colour, uint32_t *planes01, uint32_t *planes23);
uint32_t fill_pattern_n(uint8_t *image, uint32_t dst, uint16_t count,
                        uint32_t planes01, uint32_t planes23);

/* --- blit.c --- */
void blit_copy(uint8_t *image, uint32_t dst, uint32_t src, uint16_t cols, uint16_t rows);
void blit_or(uint8_t *image, uint32_t dst, uint32_t src, uint16_t cols, uint16_t rows);
void blit_andnot(uint8_t *image, uint32_t dst, uint32_t src, uint16_t cols, uint16_t rows);

#endif /* JOUST_H */
