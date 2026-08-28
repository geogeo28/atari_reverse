/* enemy.h — the enemy subsystem's globals, actor-record roles and prototypes (src/enemy.c).
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function". A `# ctx` name
 * carried over from there says so at its definition, because such a name is a proposal a later body
 * read may overturn.
 *
 * THE RECORD IS THE ONE IN include/entity.h, and this file does not repeat it — the fields the
 * routines here share with the rest of the game (x, y, alive, sprite, anim frame, squadron) come
 * from that FROZEN block. What it adds is the bytes the record leaves to the actor's own kind:
 * +0x1b..+0x1e and +0x22..+0x28 are a UNION, read differently by each type, and entity.h names only
 * one reading of two of them. `ENTITY_BOUNCE` (+0x1b) is `ACTOR_FIRE_COUNTDOWN` to the script VM's
 * opcode class 2, and `ENTITY_SQUADRON` (+0x21) is a speed flag to the asteroid columns. Naming the
 * second role here rather than editing entity.h is what the freeze asks for: two names for one
 * offset is the honest transcription of a union, and `test_constants.py` only refuses two names for
 * one ADDRESS, which these are not.
 */
#ifndef ZYNAPS_ENEMY_H
#define ZYNAPS_ENEMY_H

#include <stdint.h>

/* ================================================================================================
 * Globals this subsystem OWNS (../out/globals.tsv).
 * ============================================================================================= */
#define A_enemy_slots            0x17c1au  /* names.txt # ctx — the 8 wave-enemy records,
                                           * entity slots 9..16 */
#define A_asteroid_records       0x17e2au  /* names.txt `object_array_2` # ctx — 6 x 3 columns */
#define A_anim_frames_type17     0x1925cu  /* 4 sprite pointers, the gemgraf cycle */
#define A_anim_frames_type14     0x1926cu
#define A_anim_frames_type12     0x1927cu  /* the spinners */
#define A_anim_frames_ground_t34 0x1928cu  /* the 6 scenery actors' 4 frames */
#define A_asteroid_bank_ptrs     0x191e4u  /* 6 frame banks; a column adds its own byte offset */
#define A_enemy_sprite_ptrs_b    0x192ccu
#define A_puff_frame_ptrs_b      0x192ecu
#define A_anim_frames_type15     0x1930cu  /* the diver's cycle */
#define A_shot_variant_table     0x18f7cu  /* heading -> sprite variant, for enemy_set_sprite_b */
#define A_anim_phase_b           0x198acu  /* flipped once per frame by enemies_animate_all */
#define A_free_wave_slot_count   0x198b7u  /* names.txt # ctx — what count_free_wave_slots publishes */
#define A_squadron_kill_counters 0x198bbu  /* names.txt # ctx — six bytes; a squadron at 0 drops a pod */
#define A_asteroid_anim_toggle   0x198fcu  /* `not.b` every call: the columns animate every other one */

/* ================================================================================================
 * Globals another subsystem owns, BORROWED because no owner's header DEFINES them yet.
 *
 * Not because the owner's header is missing — `include/sprite.h` exists and this file's neighbour
 * already includes it — but because the address itself has no home: each owner is porting its first
 * function concurrently with this one, and none of these four has been written down anywhere but
 * ../../names.txt. They are collected here rather than spelt at their use sites so the move is one
 * edit: when the owner names the address, delete the entry here and include that header.
 * `test_constants.py::test_no_address_has_two_spellings` is what fails if both survive the merge,
 * and it will fail in the OWNER's diff rather than this one, so the four are listed in
 * STATUS.md too.
 *
 * THREE OF THE FOUR ARE READ-ONLY here; A_entity_table is NOT. anim_ground_objects writes
 * ENTITY_ANIM_FRAME and ENTITY_SPRITE into its first six records, faithfully — the original
 * does the same at 0x1465e / 0x14670 — so whoever ports the player subsystem must not assume
 * those slots are theirs alone.
 * ============================================================================================= */
#define A_scroll_frozen        0x198b1u  /* names.txt # ctx. scroll-map (../out/globals.tsv). Set
                                          * while the mothership holds the map still */
#define A_explosion_phase_odd  0x198c5u  /* names.txt # ctx — offered there as anim_phase_a /
                                          * anim_freeze too, so the ROLE is a proposal even though
                                          * the address is certain. sprite (../out/globals.tsv):
                                          * the half-frame gate the actor animations share */
#define A_entity_table         0x17a8eu  /* names.txt # ctx. player (../out/globals.tsv). Slot 0 of
                                          * the one record array; the six scenery actors are its
                                          * first records, and anim_ground_objects WRITES them */
/* NOT in ../out/globals.tsv at all — ../../names.txt's `var 0x17d7a player_record` is its only
 * source, and globals.tsv's `player` array is the different 0x19f02. Whoever ports the player
 * subsystem owns it; until then the attribution here is names.txt's, not globals.tsv's. */
#define A_player_record        0x17d7au

/* ================================================================================================
 * Actor-record roles this subsystem adds to entity.h's frozen block. Offsets are from ../names.txt.
 * ============================================================================================= */
#define ACTOR_FIRE_COUNTDOWN    0x1bu  /* .b — ticks down to a shot; entity.h calls it ENTITY_BOUNCE */
#define ACTOR_FIRE_RELOAD       0x1cu  /* .b — what the countdown reloads to */
#define ACTOR_DIVING            0x1cu  /* .b — the SAME byte to a type-15 diver: its dive is armed */
#define ACTOR_HEADING           0x1du  /* .b — 6-bit direction, and the shot-variant index */
#define ACTOR_SCRIPT_PC         0x22u  /* .w — byte offset into the script data at 0x19ac2 */
#define ACTOR_SCRIPT_LOOP_PC    0x24u  /* .w — the pc a loop rewinds to */
#define ACTOR_SCRIPT_LOOP_COUNT 0x27u  /* .b — passes left in that loop */
/* .b — the column's DIRECTION, and the flag is named for the y axis rather than the picture:
 * non-zero adds to y, which on an ST screen moves the column DOWN. `tst.b 30(a2)` @ 0x15a08. */
#define ASTEROID_Y_DESCENDING   0x1eu
#define ASTEROID_SLOW           0x21u  /* .b — the SAME byte as ENTITY_SQUADRON: 2 px/frame not 4 */

/* ================================================================================================
 * THE CARRY/ZERO ANSWER, and the two bytes that carry it across the differential.
 *
 * Most script-VM handlers return their answer in the 68000's CARRY flag rather than in memory or a
 * register — set means "run the next opcode this frame", clear means "the frame is done" — and the
 * image diff cannot see a flag. So the test enters at a stub that ends in `Scc <ea>` (test/abi.py,
 * `flag_call_pokes`), which stores exactly these two bytes, and each glue below mirrors that store
 * at the same address. The values are the 68000's own, not a convention of ours.
 *
 * THEY ARE NOT ENEMY-SPECIFIC, and they live here only because this reconstruction has no shared
 * header (README.md: "There is no addrs.h and no zynaps.h"). A subsystem that ports its own
 * flag-answering routine should INCLUDE this header rather than restate them — `test_constants.py`
 * refuses a constant spelt in two files, and that refusal is the reminder.
 * ============================================================================================= */
#define SCC_BYTE_TRUE   0xffu
#define SCC_BYTE_FALSE  0x00u

/* ================================================================================================
 * Prototypes. A routine returning `unsigned` returns the FLAG the original leaves — see above.
 * ============================================================================================= */
uint8_t count_free_wave_slots(uint8_t *image);
unsigned enemy_alloc_slot(uint8_t *image, uint32_t *slot);
unsigned entity_type_in_mask(const uint8_t *image, uint32_t bitmap, uint16_t type);

void actor_clamp_y(uint8_t *image, uint32_t actor);
void actor_despawn(uint8_t *image, uint32_t actor);

void enemy_move_type16_left(uint8_t *image, uint32_t actor);
void enemy_move_type17_left(uint8_t *image, uint32_t actor);
void enemy_move_type15_dive(uint8_t *image, uint32_t actor);

unsigned actor_script_op_loop_begin(uint8_t *image, uint32_t actor, uint8_t opcode);
unsigned actor_script_op_set_fire_rate(uint8_t *image, uint32_t actor, uint8_t opcode);
unsigned actor_script_op_drift_left(uint8_t *image, uint32_t actor);
unsigned actor_script_op_halt(uint8_t *image, uint32_t actor);
unsigned actor_script_op_loop_end(uint8_t *image, uint32_t actor);
unsigned actor_script_op_step_left(uint8_t *image, uint32_t actor);

void anim_enemy_type12(uint8_t *image, uint32_t actor);
void anim_enemy_type14(uint8_t *image, uint32_t actor);
void anim_enemy_type15_diving(uint8_t *image, uint32_t actor);
void anim_enemy_type17(uint8_t *image, uint32_t actor);
void enemy_set_sprite_b(uint8_t *image, uint32_t actor);
void enemy_anim_puff_b(uint8_t *image, uint32_t actor);
void anim_ground_objects(uint8_t *image);

void asteroids_move(uint8_t *image);
void asteroids_animate(uint8_t *image);

#endif /* ZYNAPS_ENEMY_H */
