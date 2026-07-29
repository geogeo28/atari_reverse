/* object.h — the object / physics / collision layer: addresses, record layouts, prototypes.
 *
 * Every A_* address is a Ghidra address (image offset + the 0x10000 load base) and mirrors a `var`
 * line in ../../names.txt, which stays the source of truth for the name. The record layouts mirror
 * the object-model `cmt` lines there; nothing in src/object.c indexes a record by bare hex.
 */
#ifndef JOUST_OBJECT_H
#define JOUST_OBJECT_H

#include <stdint.h>

/* ---- globals ---- */
#define A_platform_present      0x10cfau  /* .b[8] — 0 = platform absent this wave */
#define A_game_phase            0x10d08u  /* .b — 0 = playing, otherwise between waves */
#define A_live_object_count     0x10d0au  /* .b */
#define A_egg_count             0x10d0bu  /* .b */
#define A_message_char_count    0x10d0cu  /* .b */
#define A_ptero_spawn_count     0x10d0du  /* .b */
#define A_snd_priority          0x10d4cu  /* .w — lower index = higher priority */
#define A_playfield_bottom      0x10d60u  /* .l — screen address of the lava surface */
#define A_hit_box_a             0x10da0u  /* the two staged collision boxes (HB_* below) */
#define A_hit_box_b             0x10db0u
#define A_hit_rows              0x10dc0u  /* .b — overlapping rows, set by test_overlap */
#define A_collision_hit         0x10dc1u  /* .b — COLLISION_HIT_SET when the pixel test found a hit */
#define COLLISION_HIT_SET       0xffu     /* move.b #$ff — callers only ever test it against 0 */
#define A_draw_dst              0x10de8u  /* .l */
#define A_draw_x                0x10decu  /* .w */
#define A_draw_src              0x10df0u  /* .l */
/* Both of these sit in word-aligned slots but every access is `move.b`, so only the byte AT the
 * address — the slot's high half — carries anything. */
#define A_draw_shift            0x10df4u  /* .b — pixel shift within the cell */
#define A_draw_rows             0x10df6u  /* .b — sprite height */
#define A_message_table         0x10e16u
#define A_object_table          0x10f36u
#define A_sound_table           0x11774u  /* .l[] — Dosound command lists, indexed by sound number */
#define A_platform_table        0x117b4u
#define A_platform_sprites      0x119d4u

/* Table ends. Each is the address the original's own `cmpa.l` loop bound uses — which is the start
 * of the NEXT table, so these deliberately duplicate the neighbouring A_* above where they touch.
 * ../../names.txt names every table; only the ones this layer walks are repeated here. */
#define A_message_table_END        0x10f36u   /* == object_table */
#define A_object_table_END         0x1137au   /* == effect_table */
#define A_platform_table_END       0x117f4u   /* == platform_edge_table */
#define A_platform_sprites_END     0x11a54u

/* ---- object record (0x4e bytes) ----
 * Only the fields the nine routines here touch are named; ../../names.txt documents the whole
 * record, and a field earns a name here when a routine that uses it is ported. */
#define OBJ_FLAGS           0x00u   /* .w */
#define OBJ_X               0x02u   /* .w */
#define OBJ_Y               0x04u   /* .w */
#define OBJ_VX              0x06u   /* .w */
#define OBJ_VY              0x08u   /* .w */
#define OBJ_ANIM_TIMER      0x0au   /* .b */
#define OBJ_STEP_TIMER      0x0bu   /* .b */
#define OBJ_FLAP_FRAME      0x0eu   /* .w */
#define OBJ_PREV_DST        0x14u   /* .l — last drawn screen address */
#define OBJ_EGG_STATE       0x1eu   /* .b */
#define OBJ_EGG_X           0x20u   /* .w */
#define OBJ_EGG_DST         0x2au   /* .l — screen address the egg sprite was drawn at */
#define OBJ_EGG_SRC         0x2eu   /* .l */
#define OBJ_EGG_ROWS        0x32u   /* .b */
#define OBJ_EGG_SHIFT       0x33u   /* .b */
#define OBJ_SIZE            0x4eu

#define OBJ_FLAG_RESPAWN       (1u << 7)    /* awaiting respawn */
#define OBJ_FLAG_ON_PLATFORM   (1u << 9)    /* standing on a platform */
#define OBJ_FLAG_FACING_RIGHT  (1u << 15)

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
#define PSPR_DST_OFF  0xcu   /* .l — offset from screen_base */
#define PSPR_RECORD   0x10u

/* ---- message_table record ---- */
#define MSG_KIND       0x0u   /* .b — 0 = free slot */
#define MSG_SCREEN_PTR 0x4u   /* .l — where draw_string paints (see count_objects_and_pad) */
#define MSG_RECORD     0xcu

/* ---- egg states ---- */
#define EGG_STATE_LAVA  0x24u   /* fell into the lava */

/* ---- shared geometry ---- */
#define CELLS_PER_ROW  20u    /* SCREEN_ROW_BYTES / CELL_BYTES; test_overlap's `sub.w #$14` */
#define SPRITE_PLANES  4u     /* plane words per cell — every `moveq #$4` blit counter here */

/* ---- 68000 primitives this layer needs ---- */

/* DIVU.W leaves the destination as (remainder << 16) | quotient — unless the quotient would not fit
 * in 16 bits, in which case V is set and the destination is left UNCHANGED. No caller here tests V,
 * so an out-of-range dividend simply carries forward undivided.
 *
 * DUPLICATE, deliberately: src/screen.c carries a byte-identical private copy. Both belong in
 * include/joust.h next to loop_passes, but that header is outside this change's scope — merging
 * them is the first thing to do when it is next touched. */
static inline uint32_t divu_w(uint32_t dividend, uint16_t divisor) {
    uint32_t quotient = dividend / divisor;
    if (quotient > 0xffffu) return dividend;
    return ((dividend % divisor) << 16) | quotient;
}

/* LSR.L Dx,Dy takes its count modulo 64, and a count of 32..63 shifts every bit out. The sprite
 * shifts below feed it a whole byte, so the wide counts are reachable. */
static inline uint32_t lsr_l(uint32_t value, uint8_t count) {
    count &= 63u;
    return count < 32u ? value >> count : 0u;
}

/* ---- the kit's XBIOS Dosound side-effect ledger (tools/recreate_kit/src/dosound_log.c) ---- */
void g_dosound(uint8_t *image, uint32_t list_addr);

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
