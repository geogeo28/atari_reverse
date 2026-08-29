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

/* Set whenever a boss record's x leaves the playfield; names.txt's `mothership_escaped` reading
 * says it is what ends the section. Cleared at the top of every `mothership_move_and_place`. */
#define A_mothership_offscreen     0x19916u  /* names.txt # ctx */

/* Which formation the boss spawns as, and the ACTOR_FIRE_FLAGS byte its actors get — one byte of
 * each per level section, both read with the same SIGN-EXTENDED section index. */
#define A_mothership_formation_by_section   0x19cc3u  /* names.txt */
#define A_mothership_spawn_param_by_section 0x19cd3u  /* names.txt */

/* One energy byte per segment PAIR, refreshed by `mothership_segments_respawn`. It is the same
 * array `include/enemy.h` calls A_enemy_pair_hitpoints, entered nine bytes in: the boss's parents
 * are entity slots 9, 11, 13 and 15, and that routine indexes by the ENTITY index while this one
 * walks the four bytes those indexes name. Both names are in ../../names.txt.
 *
 * THE NINE IS NOT SPELT AS ARITHMETIC because both numbers are names.txt's own `var` lines and
 * `test_constants.py` scrapes plain literals out of these headers; what holds the relation instead
 * is `test_mothership.py::test_segments_respawn_energy_bytes_are_the_pairs_own`, which derives the
 * four bytes twice — once from `mothership_segment_hit`'s FOLD over the eight boss slots and once
 * from this base and its stride — and requires the two sets to be equal. That is CLAUDE.md §5's
 * "pick one canonical definition and pin the other equal with a test", and the same remedy holds
 * A_mothership_segment_sprite and A_score_value_segment below. */
#define A_mothership_segment_energy 0x1988du  /* names.txt # ctx */

/* The sprites and the score award the encounter uses. Every one is a RELOCATED address — the
 * `move.l #$315ae,10(a2)` over `2d7c 000215ae` — as names.txt's CORRECTION notes describe.
 *
 * TWO OF THEM ARE DERIVED ADDRESSES the original spells as literals, and each is pinned equal to
 * its derivation by a test rather than restated as arithmetic here (see the note above):
 * A_mothership_segment_sprite is bank 1, i.e. A_mothership_sprite_bank one whole preshift bank on,
 * and A_score_value_segment is one past the third entry of `include/score.h`'s
 * A_score_award_table_bcd, which is the shape `score_add_bcd` takes its argument in. */
#define A_mothership_head_sprite      0x19e2eu  /* names.txt */
#define A_mothership_segment_sprite   0x315aeu
#define A_mothership_explosion_sprite 0x5cf7eu
#define A_score_value_segment         0x195f0u  /* names.txt — the BCD award for a killed pair */

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
 * THE BOSS'S OWN SLOTS, and why they are a PAIR array over the wave records.
 *
 * The encounter borrows `include/enemy.h`'s eight wave slots at A_enemy_slots rather than having
 * records of its own. Its head lives in the first two; its four tail segments live one per PAIR,
 * the EVEN slot carrying the segment the script moves and the ODD one a shadow record placed
 * MOTHERSHIP_SHADOW_X_LEAD to its right. That is why every boss loop strides
 * MOTHERSHIP_PAIR_BYTES and why the respawn marks the odd slots alive before it spawns: the
 * spawner then fills only the even ones.
 * ============================================================================================= */
#define MOTHERSHIP_PAIR_BYTES 0x58u    /* `lea 88(a2),a2` — two 0x2c-byte records */
#define MOTHERSHIP_SEGMENT_PAIRS 4     /* `move.w #$3,d7` + `dbf` */
#define MOTHERSHIP_HEAD_RECORDS 2      /* `move.w #$1,d7` + `dbf` over the first two slots */
#define MOTHERSHIP_SHADOW_X_LEAD 0x10  /* `add.w #$10,d0` before the shadow's x is stored */
#define MOTHERSHIP_SEGMENT_TYPE 2      /* `cmpi.b #$2,17(a2)` — what the segments are typed */
#define MOTHERSHIP_HEAD_TYPE 1         /* `move.b #$1,d1` into spawn_formation */
#define MOTHERSHIP_HEAD_ROWS 1         /* `move.w #$1,8(a2)` */
#define MOTHERSHIP_SEGMENT_ROWS 0x10u  /* `move.w #$10,8(a2)` */
#define MOTHERSHIP_SPAWN_X 0x180       /* `move.w #$180,d3` into spawn_formation */

/* The anchor the tail is laid out from trails the head record by this much. */
#define MOTHERSHIP_ANCHOR_X_LEAD 0x40  /* `sub.w #$40,d0` */
#define MOTHERSHIP_ANCHOR_Y_LEAD 0x14  /* `sub.w #$14,d0` */

/* Where a segment stops being alive. The right-hand edge is `include/enemy.h`'s ACTOR_KEEP_X_MAX,
 * shared with the scripted movers; the left-hand ones are the boss's own and differ between the two
 * loops — the head is retired only once its x goes NEGATIVE (`tst.w` + `bmi`). */
#define MOTHERSHIP_SEGMENT_KEEP_X_MIN 0x10   /* `cmpi.w #$10,0(a2)` + `ble` */

/* ================================================================================================
 * Prototypes.
 * ============================================================================================= */
void mothership_begin(uint8_t *image);
void mothership_place_tail(uint8_t *image);
void mothership_sprite_build_step(uint8_t *image);
void mothership_draw(uint8_t *image);

void mothership_spawn_head(uint8_t *image);
void mothership_move_and_place(uint8_t *image);
void mothership_segments_update(uint8_t *image);
void mothership_segments_respawn(uint8_t *image);
/* ../../names.txt tags this name `# ctx` (offered there as `enemy_pair_take_hit` too), so it is
 * a proposal a later body read may overturn — README.md asks for this note at the declaration. */
void mothership_segment_hit(uint8_t *image, uint32_t segment);

#endif /* ZYNAPS_MOTHERSHIP_H */
