/* mothership.h — the boss encounter's globals and the routines in src/mothership.c.
 *
 * Names and addresses are ../../names.txt's; where a name carries a `# ctx` tag there it says so
 * here too, because such a name is a proposal a later body read may overturn. The boss's records
 * are the ordinary 0x2c-byte ones include/entity.h describes.
 */
#ifndef ZYNAPS_MOTHERSHIP_H
#define ZYNAPS_MOTHERSHIP_H

#include <stdint.h>

/* ================================================================================================
 * Globals this subsystem owns.
 * ============================================================================================= */
#define A_entity_boss_parts       0x18142u  /* names.txt # ctx — the 5 tail/column records */
#define A_mothership_ready        0x198b0u  /* names.txt # ctx — the encounter is armed */
#define A_mothership_prep_stage   0x19911u  /* names.txt # ctx — 0..4, the sprite build's state */
#define A_mothership_x            0x19dd0u  /* names.txt # ctx — the anchor the tail is placed from */
#define A_mothership_y            0x19dd2u  /* names.txt # ctx */
#define A_mothership_phase_timer  0x19efeu  /* names.txt # ctx — .l, zeroed when the build finishes */
#define A_boss_hitpoints          0x19f44u  /* names.txt # ctx — .w, the encounter's energy */
#define A_mothership_energy_by_section 0x1987du /* names.txt # ctx — one energy byte per section */

/* The level section the game is playing, named in ../../names.txt but assigned to no subsystem by
 * ../out/globals.tsv. It is read here only as the index into the energy table above; whoever ends
 * up owning the level machinery should take it and this header should include theirs. */

/* The two rotate preshift banks the boss sprite is built into, and the raw frames they are built
 * from. Neither is named in ../../names.txt — both are bare `lea` operands — so the names are this
 * reconstruction's, proposed for the map in ../out/names_enemy.txt rather than assumed. */
#define A_mothership_sprite_bank   0x310aeu  /* bank 0; bank 1 is a MOTHERSHIP_BANK_BYTES further on */
#define A_mothership_sprite_source 0x5ed7eu  /* the two unshifted frames the build copies in */

/* ================================================================================================
 * Geometry.
 * ============================================================================================= */
#define MOTHERSHIP_TAIL_SEGMENTS 5     /* `move.w #$4,d6` + `dbf` over A_entity_boss_parts */
#define MOTHERSHIP_SEGMENT_HEIGHT 0x28 /* `move.w #$28,8(a2)` — rows, written into every segment */
#define MOTHERSHIP_SEGMENT_X_STEP 0x10 /* `add.w #$10,d0` — the segments are laid out left to right */
/* `lea 400(a4),a4` — one segment's slice of the bank. Hex, though the disassembly renders
 * the displacement in decimal, so it can be compared at a glance with the 0xa0 frame and the
 * 0x500 bank below rather than through a conversion. */
#define MOTHERSHIP_SEGMENT_SPRITE_BYTES 0x190u
#define MOTHERSHIP_FRAME_BYTES 0xa0u   /* one unshifted frame; also the preshift's D2 */
#define MOTHERSHIP_BANKS 2             /* `move.w #$1,d7` + `dbf`: two banks are built */

/* Where the encounter starts the boss: `move.w #$140,$19dd0` / `move.w #$0,$19dd2`. */
#define MOTHERSHIP_START_X 0x140
#define MOTHERSHIP_START_Y 0

/* ================================================================================================
 * Prototypes.
 * ============================================================================================= */
void mothership_begin(uint8_t *image);
void mothership_place_tail(uint8_t *image);
void mothership_sprite_build_step(uint8_t *image);
void mothership_draw(uint8_t *image);

#endif /* ZYNAPS_MOTHERSHIP_H */
