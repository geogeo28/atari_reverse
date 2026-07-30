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

/* ---- pterodactyl record (0x20 bytes, pterodactyl_table) ---- */
#define PT_X                0x0cu   /* .w */
#define PT_Y                0x0eu   /* .w */
#define PT_SWOOP_TIMER      0x1eu   /* .b — armed to 0x14 when a player is spotted */

#define PT_FLAG_MOVING_RIGHT (1u << 2)

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
void joust_bounce(uint8_t *image, uint32_t obj_a, uint32_t obj_b, uint16_t flags_a, uint16_t flags_b);
uint32_t check_platform(uint8_t *image, uint32_t object, uint32_t flags);
void erase_egg_sprite(uint8_t *image, uint32_t object);
void draw_egg_sprite(uint8_t *image, uint32_t object);
uint32_t ptero_avoid_platform(uint8_t *image, uint32_t pterodactyl, uint32_t scratch);
void ptero_spot_player(uint8_t *image, uint32_t pterodactyl, uint32_t player, uint32_t flags);
void count_objects_and_pad(uint8_t *image);

#endif /* JOUST_OBJECT_H */
