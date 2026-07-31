/* object.h — the object / physics / collision layer: addresses, record layouts, prototypes.
 *
 * Every A_* address is a Ghidra address (image offset + the 0x10000 load base) and mirrors a `var`
 * line in ../../names.txt, which stays the source of truth for the name. The record layouts mirror
 * the object-model `cmt` lines there; nothing in src/object.c indexes a record by bare hex.
 *
 * Only what this layer alone touches is declared here: the globals the drawing layer reads too are
 * in addrs.h, and the object record itself — which both layers walk — is in joust.h.
 */
#ifndef JOUST_OBJECT_H
#define JOUST_OBJECT_H

#include <stdint.h>

#include "addrs.h"
#include "joust.h"

/* ---- globals ---- */
#define A_platform_present      0x10cfau  /* .b[8] — 0 = platform absent this wave */
#define A_game_phase            0x10d08u  /* .b — 0 = playing, otherwise between waves */
#define A_live_object_count     0x10d0au  /* .b */
#define A_egg_count             0x10d0bu  /* .b */
#define A_message_char_count    0x10d0cu  /* .b */
#define A_ptero_spawn_count     0x10d0du  /* .b */
#define A_hit_box_a             0x10da0u  /* the two staged collision boxes (HB_* below) */
#define A_hit_box_b             0x10db0u
#define A_hit_rows              0x10dc0u  /* .b — overlapping rows, set by test_overlap */
#define A_collision_hit         0x10dc1u  /* .b — COLLISION_HIT_SET when the pixel test found a hit */
#define COLLISION_HIT_SET       0xffu     /* move.b #$ff — callers only ever test it against 0 */
#define A_draw_x                0x10decu  /* .w */
#define A_message_table         0x10e16u
#define A_platform_table        0x117b4u
#define A_platform_sprites      0x119d4u

/* Table ends. Each is the address the original's own `cmpa.l` loop bound uses — which is the start
 * of the NEXT table, so these deliberately duplicate the neighbouring A_* above where they touch.
 * ../../names.txt names every table; only the ones this layer walks are repeated here. */
#define A_message_table_END        0x10f36u   /* == object_table */
#define A_object_table_END         0x1137au   /* == effect_table */
#define A_platform_table_END       0x117f4u   /* == platform_edge_table */
#define A_platform_sprites_END     0x11a54u

/* ---- pterodactyl record (0x20 bytes, pterodactyl_table) ----
 *
 * THE WHOLE RECORD LIVES HERE, because all three layers that touch a bird read it: the driver
 * (src/ptero.c), the collision resolver (src/collide.c) and the two blitters (src/draw.c). The
 * shift and the row count are each read BOTH ways — as the whole word the erase blit takes, and as
 * that word's LOW BYTE where a collision box or a `subq.b` wants one number — so each carries two
 * names for the two addresses, the same width split addrs.h documents for draw_shift/draw_rows.
 */
#define A_pterodactyl_table      0x113bau
#define A_pterodactyl_table_END  0x1143au  /* the original's own `cmpa.l` bound: 4 x PT_RECORD on */

#define PT_FLAGS            0x00u   /* .w — 0 = the slot is free */
#define PT_DST              0x02u   /* .l — screen address, before screen_base and PT_DST_OFF */
#define PT_SRC              0x06u   /* .l — the sprite set; the erase mask sits PTERO_MASK_OFF in */
#define PT_SHIFT_W          0x0au   /* .w — what blit_mask_wide rotates by (cleared at 0x14b5e) */
#define PT_SHIFT            0x0bu   /* .b — its LOW byte, which a collision box takes (0x14c0a) */
#define PT_X                0x0cu   /* .w */
#define PT_Y                0x0eu   /* .w */
#define PT_VX               0x10u   /* .w — pixels of horizontal travel per frame; the direction is
                                     * PT_FLAG_MOVING_RIGHT, not this field's sign */
#define PT_VY               0x12u   /* .w — likewise, steered by PT_FLAG_MOVING_DOWN */
#define PT_SPARE            0x14u   /* .w — cleared on spawn and never read again, by any routine in
                                     * the image; reproduced because the clear is a real write */
#define PT_DST_OFF          0x16u   /* .w — SIGN-extended, added to the screen address */
#define PT_ROWS_W           0x18u   /* .w — signed; <= 0 blits nothing (cleared at 0x14b66) */
#define PT_ROWS             0x19u   /* .b — its LOW byte, which a collision box takes (0x14c10) */
#define PT_ANIM             0x1au   /* .w — the wing-beat counter. Bits 3-4 pick the sprite and the
                                     * rest is sub-frame phase; the driver that reads it that way
                                     * names the mask and the poses (ptero.h's PT_ANIM_*) */
/* .b, .b — the two per-CELL clip counters the driver stages into draw_clip_cell0/1/2 (draw.h), so a
 * NON-ZERO one hides those cells of the bird. Which cells each covers is fixed by where the sprite
 * sits: PT_CLIP_WRAPPED hides only the cells that have run past the right screen edge and reappear
 * a scanline down, PT_CLIP_ONSCREEN the ones still on this scanline. Both double as countdowns —
 * the driver takes one off each per frame — which is how a bird fades in as it enters and fades out
 * as it leaves. */
#define PT_CLIP_WRAPPED     0x1cu
#define PT_CLIP_ONSCREEN    0x1du
#define PT_SWOOP_TIMER      0x1eu   /* .b — armed to 0x14 when a player is spotted, and re-used as
                                     * the death animation's frame timer */
#define PT_DWELL_TIMER      0x1fu   /* .b — frames between two hunting decisions, and re-used as the
                                     * death animation's flap count */
#define PT_RECORD           0x20u

#define PT_FLAG_JUST_SPAWNED  (1u << 0)   /* armed but not built yet — and not solid, so the
                                           * collision resolver skips it */
#define PT_FLAG_MOVING_DOWN   (1u << 1)
#define PT_FLAG_MOVING_RIGHT  (1u << 2)
#define PT_FLAG_LEAVING       (1u << 3)   /* heading off the screen; nothing turns it back */
#define PT_FLAG_DYING         (1u << 5)   /* lanced: playing out the death animation */
/* bit6 — carries no meaning of its own. The driver raises it the moment it clears the flags word to
 * build a newly armed bird, and it is what keeps that word NON-ZERO, which is the only test anyone
 * makes of a slot's occupancy. Clearing the word is therefore how a slot is released, and every
 * release in the driver is a `clr.l d0`. */
#define PT_FLAG_IN_PLAY       (1u << 6)

/* The bird is three cells wide, in both boxes that are ever staged for it: `move.w #$3,8(a1)` in
 * update_pterodactyl and `move.w #$3,8(a2)` in collision_check. */
#define PTERO_BOX_COLS  3u

/* ---- collision box, staged in hit_box_a / hit_box_b (0x10 bytes) ---- */
#define HB_DST      0x0u   /* .l — screen address of the sprite's top-left cell */
#define HB_SRC      0x4u   /* .l — sprite plane words; advanced in place by test_overlap */
#define HB_COLS     0x8u   /* .w — cells per row */
#define HB_SHIFT    0xau   /* .b — pixel shift within the cell */
#define HB_ROWS     0xbu   /* .b */
#define HB_CUR_COL  0xcu   /* .w — column cursor, 0..COLS */
#define HB_Y        0xeu   /* .w — top scanline */

/* ---- platform_table record: the landable boxes ---- */
#define PLAT_Y0     0x0u
#define PLAT_Y1     0x2u
#define PLAT_X0     0x4u
#define PLAT_X1     0x6u
#define PLAT_RECORD 0x8u

/* ---- platform_sprites record: the platform bitmaps, also the pixel-collision surface ---- */
#define PSPR_PRESENT  0x0u   /* .l — points at this platform's platform_present byte */
#define PSPR_ROWS     0x4u   /* .w */
#define PSPR_ROWS_LO  0x5u   /* .b — its LOW byte, which is all a collision box ever takes
                              * (`addq.l #1,a3 ; move.b (a3)+`), as with PT_ROWS above */
#define PSPR_COLS     0x6u   /* .w — cells per row */
#define PSPR_SRC      0x8u   /* .l — the platform bitmap */
#define PSPR_DST_OFF  0xcu   /* .l — offset from screen_base */
#define PSPR_RECORD   0x10u

/* ---- message_table record ---- */
#define MSG_KIND       0x0u   /* .b — 0 = free slot */
#define MSG_SCREEN_PTR 0x4u   /* .l — where draw_string paints (see count_objects_and_pad) */
#define MSG_RECORD     0xcu

/* ---- egg states ---- */
#define EGG_STATE_LAVA  0x24u   /* fell into the lava */

/* ---- geometry this layer alone uses ---- */
#define CELLS_PER_ROW  20u    /* SCREEN_ROW_BYTES / CELL_BYTES; test_overlap's `sub.w #$14` */

/* ---- object.c ---- */
void pixel_collision(uint8_t *image, uint32_t box_a, uint32_t box_b);
void test_overlap(uint8_t *image);
/* stage_platform_box always fills hit_box_b — both of its callers put the moving party in
 * hit_box_a — which is why, unlike stage_ptero_box, it takes no destination. */
void stage_platform_box(uint8_t *image, uint32_t sprite);
void stage_ptero_box(uint8_t *image, uint32_t box, uint32_t ptero);
void joust_bounce(uint8_t *image, uint32_t obj_a, uint32_t obj_b, uint16_t flags_a, uint16_t flags_b);
uint32_t check_platform(uint8_t *image, uint32_t object, uint32_t flags);
void erase_egg_sprite(uint8_t *image, uint32_t object);
void draw_egg_sprite(uint8_t *image, uint32_t object);
uint32_t ptero_avoid_platform(uint8_t *image, uint32_t pterodactyl, uint32_t scratch);
void ptero_spot_player(uint8_t *image, uint32_t pterodactyl, uint32_t player, uint32_t flags);
void count_objects_and_pad(uint8_t *image);

#endif /* JOUST_OBJECT_H */
