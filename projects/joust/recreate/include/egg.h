/* egg.h — the egg subsystem: addresses, record layouts, prototypes.
 *
 * Every A_* address is a Ghidra address (image offset + the 0x10000 load base) and mirrors a `var`
 * line in ../../names.txt, which stays the source of truth for the name.
 *
 * Only what this layer alone touches is declared here. The globals it shares with the drawing layer
 * live in addrs.h, the object record's common fields and the 68000 primitives in joust.h, and the
 * platform tables and their record layouts, which it walks alongside the collision layer, in
 * object.h — src/egg.c includes all three. Several object-record offsets below are egg-only TODAY;
 * they belong in joust.h the moment a second layer reads them.
 */
#ifndef JOUST_EGG_H
#define JOUST_EGG_H

#include <stdint.h>

#include "addrs.h"
#include "joust.h"
#include "object.h"

/* ---- globals ---- */
#define A_draw_y        0x10deeu  /* .w — the draw scratch's y, the partner of addrs.h's A_draw_x */

/* Two tables object.h already names by their neighbours' loop bounds (A_platform_table_END and
 * A_platform_sprites_END are these same two addresses). This layer WALKS them, so it needs them
 * under their own names; the duplication is the one object.h already documents for its `_END`s. */
#define A_platform_edge_table       0x117f4u
#define A_platform_edge_table_END   0x11944u   /* == spawn_pad_colors */
#define A_egg_sprite_ptrs           0x11a54u

/* Sprite bitmaps the code holds as relocated immediates rather than through a table. */
#define A_egg_sprite_still       0x1899au  /* egg at rest, and the frame every edge bump reverts to */
#define A_egg_sprite_roll_left   0x18a0au
#define A_egg_sprite_roll_right  0x18a7au
#define A_rider_sprite_type1     0x18b9au  /* the three hatched-rider sprite sets, by rider type */
#define A_rider_sprite_type2     0x18aeau
#define A_rider_sprite_type3     0x18c4au

/* ---- object record fields only this layer reads (the shared ones are in joust.h) ---- */
#define OBJ_EGG_HATCH_TIMER  0x1fu  /* .b — counts down while the egg sits hatchable */
#define OBJ_EGG_Y            0x22u  /* .w — the egg's own y, the partner of joust.h's OBJ_EGG_X */
#define OBJ_EGG_DX           0x24u  /* .w */
#define OBJ_EGG_DY           0x26u  /* .w */
#define OBJ_EGG_ROLL_TIMER   0x28u  /* .b — frames between roll-friction steps */
#define OBJ_EGG_FALL_TIMER   0x29u  /* .b — frames between gravity steps */
#define OBJ_EGG_SPAWN_FLAGS  0x34u  /* .b — see EGG_SPAWN_UNDRAWN */
#define OBJ_HATCH_MOUNT      0x4au  /* .b — update_objects' newly-hatched-rider state (0/1/other) */

/* OBJ_EGG_SPAWN_FLAGS is the flags word the hatched rider inherits: its low bits are the rider type
 * (1..3, set by the dismount at 0x13b60) and bit 7 says the egg has never been drawn, so
 * update_egg_draw must skip the erase. That bit sits where OBJ_FLAG_RESPAWN sits in the flags word,
 * which is exactly what the hatch relies on — the rider it builds is born awaiting respawn. */
#define EGG_SPAWN_UNDRAWN     (1u << 7)
#define EGG_SPAWN_TYPE_MID    2   /* the middle rider type; `cmpi.b #$2` picks the sprite set */

/* ---- egg states (object + OBJ_EGG_STATE; 0 = this slot carries no egg) ---- */
#define EGG_STATE_HATCH        0x05u  /* this frame the egg becomes a rider */
#define EGG_STATE_BOUNCE_UP    0x0bu  /* the one animation frame drawn four rows higher */
#define EGG_STATE_HATCHING     0x12u  /* head of the hatch animation, and one of its two end marks */
#define EGG_STATE_DEATH_END    0x19u  /* the other end mark: reaching it clears the egg */
#define EGG_STATE_READY        0x21u  /* settled and hatchable */
#define EGG_STATE_RESTING      0x22u  /* resting on a platform */
/* EGG_STATE_LAVA (0x24) is object.h's — draw_egg_sprite sets it. */

/* ---- platform_edge_table record (28 x 12 bytes): the bump boxes at the platforms' ends ----
 * Its first eight bytes are the same {y0,y1,x0,x1} box header platform_table opens with, and
 * update_egg_physics tests both with the same four compares — so the box is addressed through
 * object.h's PLAT_Y0..PLAT_X1 and only the fields beyond it are named here. */
#define EDGE_Y_PUSH    0x8u  /* .b — <0 snap onto the box's top, >0 push down, 0 leave y alone */
#define EDGE_X_PUSH    0x9u  /* .b — <0 roll left, >0 roll right, 0 leave x alone */
#define EDGE_PLATFORM  0xau  /* .w — index into platform_present, added with `adda.w` */
#define EDGE_RECORD    0xcu

/* ---- egg_sprite_ptrs record: {sprite.l, handler.l} indexed by state - 1 ---- */
#define EGG_PTR_SRC      0x0u
#define EGG_PTR_HANDLER  0x4u
#define EGG_PTR_RECORD   0x8u

/* The only two addresses the shipped table's handler longword ever holds. */
#define EGG_HANDLER_DRAW_ONLY  0x12854u  /* `bsr draw_egg_sprite ; bra` the next object */
#define EGG_HANDLER_REDRAW     0x128c0u  /* update_egg_draw's erase / draw / commit tail */

/* ---- egg.c ---- */
void update_eggs(uint8_t *image);

#endif /* JOUST_EGG_H */
