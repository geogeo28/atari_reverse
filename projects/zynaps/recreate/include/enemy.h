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
/* `move.w #$7,d7` + `dbf` over the records at A_enemy_slots. In the header rather than beside
 * its loop because src/mothership.c's arming gate is "every one of them free" and reaches for
 * it — the count and the gate are one fact. */
#define ENEMY_SLOT_COUNT 8

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
#define A_anim_phase_b           0x198acu  /* flipped once per frame by enemies_animate_all */
#define A_free_wave_slot_count   0x198b7u  /* names.txt # ctx — what count_free_wave_slots publishes */
#define A_squadron_kill_counters 0x198bbu  /* names.txt # ctx — six bytes; a squadron at 0 drops a pod */
#define A_asteroid_anim_toggle   0x198fcu  /* `not.b` every call: the columns animate every other one */

/* The three actor-animation cycles the naming pass left with `cmt` lines but no name of their own:
 * names.txt calls their sprite tables `anim_frames_type16/20/22`, and does not name the two
 * per-section frame LIMITS at all. Both limit bytes are loaded once per level section by the
 * section loader at 0x1087e / 0x1088c, out of the tables at 0x1982c / 0x1983c. */
#define A_anim_frames_type16      0x1929cu
#define A_anim_frames_type20      0x191b4u
#define A_anim_frames_type22      0x191ccu

/* The 11 records the per-frame actor passes walk: entity slots 6..16, i.e. the three enemy shot
 * slots followed by the eight wave slots at A_enemy_slots. names.txt `enemy_shot_slots` # ctx names
 * the first of them, and ../out/globals.tsv assigns the address to this subsystem. */
#define A_enemy_shot_slots        0x17b96u

/* The per-TYPE jump tables the two per-frame passes dispatch through. They SHARE STORAGE: the
 * animation table is the move table's 24th longword onward (0x19380 + 0x17 * 4 == 0x193dc), which
 * names.txt records on 0x193dc — so the move table's slots 0x17.. and the animation table's slots
 * 0.. are the same memory read two ways, and each pass bounds its type with its own
 * `cmpi.b #$32`. */
#define A_actor_move_table        0x19380u  /* names.txt `actor_move_table` # ctx */
#define A_actor_anim_table        0x193dcu

/* The actor script VM's own data (src/enemy.c, `actor_script_run`): the byte stream, the 8-entry
 * opcode-class table, the 16-entry extended table, and the per-formation script pointers the
 * spawner turns into a starting pc. */
#define A_actor_script_data       0x19ac2u  /* names.txt `actor_script_data` */
#define A_script_op_table         0x19438u  /* names.txt `script_op_table` — 8 longwords */
#define A_script_op_ext_table     0x19458u  /* names.txt `script_op_ext_table` — 16 longwords */
#define A_actor_script_table      0x194bcu  /* names.txt `actor_script_table` */

/* The formation spawner's tables (src/enemy.c, `spawn_formation`). */
#define A_formation_table         0x19504u  /* names.txt — one longword per formation */
#define A_formation_gfx_attrs     0x19c33u  /* names.txt — 8-byte records, indexed by the kind */
#define A_formation_base_y        0x19498u  /* names.txt — one word per formation */
#define A_actor_spawn_template    0x17a62u  /* names.txt — the 0x2c-byte record it builds and copies */

/* The two level-event script cursors and the spawn gates the wave/ground/squadron tickers read.
 * names.txt's comment on 0x10db2 has the script format: 4-byte records (word map-x, byte type,
 * byte param) sorted by x, with these two longwords as the cursors. */
#define A_wave_script_cursor      0x1824eu  /* names.txt `enemy_spawn_script_ptr` # ctx */
#define A_ground_script_cursor    0x1824au  /* names.txt `map_event_script_ptr` # ctx */
#define A_squadron_spawn_enabled  0x19aaeu  /* names.txt — set/cleared by script types 0x0c/0x0d */
#define A_squadron_spawn_countdown 0x198feu /* names.txt — frames until the next asteroid trio */
#define A_ground_spawn_rnd_param  0x198c1u  /* names.txt # ctx — a fresh 1..0x1f after each spawn */

/* Which actor types may fire, and how often. The three 14-byte class maps are entity_type_in_mask's
 * (see its note); the chance table is indexed by the level section. */
#define A_enemy_types_fire_homing 0x19164u  /* names.txt */
#define A_enemy_types_can_fire    0x19172u  /* names.txt */
#define A_enemy_types_fire_seeker 0x19180u  /* names.txt */
#define A_enemy_fire_chance_table 0x19aafu  /* names.txt — one byte per section */

/* The hit points of the two-slot type-0x02 enemies, one byte per PAIR — ../out/globals.tsv calls it
 * this subsystem's, and src/mothership.c reads it through this header (its segments are such
 * pairs). */
#define A_enemy_pair_hitpoints    0x19884u  /* names.txt # ctx */

/* The sprites the enemy shots and the ground puff are given. Every one is a RELOCATED address —
 * `move.l #$6115e,10(a2)` over the bytes `257c 0005115e` — so the number here is the loaded one,
 * as ../../names.txt's own CORRECTION notes on the weapon launchers describe. */
#define A_shot_sprite_aimed       0x6115eu  /* type 0x0c, the plain aimed shot */
#define A_shot_sprite_homing      0x6e6eeu  /* type 0x0a */
#define A_shot_sprite_seeker      0x65d9eu  /* type 0x0b */
#define A_ground_puff_sprite      0x68d1eu  /* type 0x06, what an expiring seeker becomes */
#define A_wave_trio_sprite        0x60bbeu  /* the type-0x0e sine patrollers */
#define A_ground_actor_sprite     0x62e1eu  /* the type-0x0f / 0x10 ground actors */

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
/* NOT in ../out/globals.tsv at all — ../../names.txt's `var 0x17d7a player_record` is its only
 * source, and globals.tsv's `player` array is the different 0x19f02. Whoever ports the player
 * subsystem owns it; until then the attribution here is names.txt's, not globals.tsv's. */
#define A_player_record        0x17d7au

/* The explosion group's data, borrowed on the same terms as the two above — one edit to move, and
 * STATUS.md's "The globals this subsystem borrows" table lists each with its owner so the merge is
 * expected rather than discovered. Per ../out/globals.tsv: 0x19670 is `player`'s, and 0x19664 /
 * 0x195a8 / 0x191fc are `sprite`'s. THE LAST TWO HAVE NO OWNER AT ALL — neither 0x198ae nor 0x19902
 * appears in globals.tsv, and ../../names.txt's `var` lines are their only source, so "another
 * subsystem owns them" is a guess about them rather than a reading. */
#define A_explosion_group_active_bits 0x19670u  /* names.txt `control_lock_flags` # ctx; bit 0 =
                                                 * the end-of-section blast, bit 1 = the ship's */
#define A_explosion_group_members     0x19664u  /* names.txt # ctx — 6 entity indices per group */
#define A_explosion_particle_offsets  0x195a8u  /* names.txt # ctx — dx/dy/delay per particle */
#define A_explosion_small_frame_ptrs  0x191fcu  /* names.txt # ctx — 12 sprite pointers */
#define A_explosion_frame_toggle      0x198aeu
#define A_fire_charged                0x19902u  /* names.txt # ctx — cleared by the group-1 pass */
/* ../out/globals.tsv gives this one to `player` ("counts down after a section (re)start"), and
 * include/player.h does not name it. `spawn_enemy_shot` both READS and WRITES it as the seeker
 * launcher's own reload gate, so it is borrowed on the same terms as the five above: one edit to
 * move when player.h names it. */
#define A_enemy_seeker_cooldown       0x19abfu  /* names.txt # ctx */

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
#define ACTOR_BOUNCED           0x29u  /* .b — this actor has already bounced off the landscape;
                                       * the script VM clears it on every opcode fetch (0x14cb8) */
#define ACTOR_SPEED             0x1eu  /* .b — the scalar the heading ops multiply the direction by;
                                       * names.txt's record note calls it "speed". The SAME byte as
                                       * ASTEROID_Y_DESCENDING below */
#define ACTOR_SINE_BASE_Y       0x1au  /* .w — the type-14 patroller's centre line, the field
                                       * entity.h names ENTITY_HP for the kinds that fight */
/* .b — an explosion particle's own frame counter, counted up to EXPLOSION_END_FRAME by
 * explosion_animate_all and seeded per particle by explosion_spawn. include/entity.h does not name
 * +0x10 AT ALL — a gap in its frozen block rather than a union role, reported to its owner. */
#define EXPLOSION_PART_FRAME    0x10u
#define ACTOR_SINE_PHASE        0x1cu  /* .w — ...and its angle in degrees; the same word whose low
                                       * byte is ACTOR_FIRE_RELOAD / ACTOR_DIVING above */
/* .b — the column's DIRECTION, and the flag is named for the y axis rather than the picture:
 * non-zero adds to y, which on an ST screen moves the column DOWN. `tst.b 30(a2)` @ 0x15a08. */
#define ASTEROID_Y_DESCENDING   0x1eu
#define ASTEROID_SLOW           0x21u  /* .b — the SAME byte as ENTITY_SQUADRON: 2 px/frame not 4 */
/* .b — the script VM's per-actor frame countdown: `subq.b #1,38(a2)` at the head of
 * `actor_script_run`, reaching zero is what fetches the next opcode, and a script byte with bit 7
 * set reloads it with the low seven bits. */
#define ACTOR_SCRIPT_DELAY      0x26u
/* .b — the opcode byte currently in force; the VM re-dispatches it every frame the delay above has
 * not expired, and `spawn_formation` seeds it with ACTOR_SCRIPT_OPCODE_INITIAL. */
#define ACTOR_SCRIPT_OPCODE     0x28u
/* .b — what an actor may fire, read by `enemy_fire_and_update_shots`: zero means it never fires,
 * bit 1 admits the homing/missile classes and bit 2 halves that chance again. `spawn_formation`
 * writes it from its own argument, which the wave script derives from the opcode's bits 4 and 5. */
#define ACTOR_FIRE_FLAGS        0x2au
/* .b — a spawn-time tag the wave and ground spawners write (2 for the type-0x0e trio, 1 for the two
 * ground types) and which NO ported routine reads. The only reader of the offset anywhere is
 * explosion_animate_all, under EXPLOSION_PART_FRAME above — a different role in a record that is
 * never both, exactly like the unions this header's opening note describes. */
#define ACTOR_SPAWN_TAG         0x10u

/* THE PLAYFIELD'S RIGHT-HAND EDGE, as `cmpi.w #$1b8,0(a2)` + `bge` — a SIGNED word compare. In the
 * header rather than beside `enemy_move_scripted` because src/mothership.c retires the boss and its
 * segments on the same number, and one edge spelt in two files is two things to keep right. Its
 * left-hand partners are NOT shared: the scripted mover uses src/enemy.c's ACTOR_KILL_X and the
 * boss its own, lower bounds. */
#define ACTOR_KEEP_X_MAX 0x1b8

/* WHAT AN EXPLODING RECORD LOOKS LIKE, shared because two subsystems write it. `explosion_spawn`
 * (src/enemy.c) gives each of its six particles this type and this 4-pixel x alignment, and
 * `mothership_segment_hit` (src/mothership.c) rewrites both halves of a killed boss pair the same
 * way — so the pair lives here rather than as two file-private copies under two names, which is
 * the one duplicate `test_constants.py` cannot see. */
#define EXPLOSION_PART_TYPE 0x64      /* `move.b #$64,17(a2)` / `move.b #$64,17(a6)` */
#define EXPLOSION_X_ALIGN 0xfffcu     /* `and.w #$fffc,d0` / `andi.w #$fffc,0(a6)` */

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
void asteroids_draw(uint8_t *image);

/* Both names carry a trailing `# ctx` in ../../names.txt (offered there as `explosion_group_spawn`
 * and `explosion_groups_animate`), so they are proposals a later body read may overturn — README.md
 * asks for this note next to the declaration. What the bodies confirm is the ROLE, not the wording:
 * one seeds six records from a source and the other steps them. */
void explosion_spawn(uint8_t *image, uint32_t source, uint16_t group);
void explosion_animate_all(uint8_t *image);

uint32_t entity_ptr_from_index(uint32_t index);

void anim_enemy_type16(uint8_t *image, uint32_t actor);
void anim_enemy_type20(uint8_t *image, uint32_t actor);
void anim_enemy_type22(uint8_t *image, uint32_t actor);
void enemies_animate_all(uint8_t *image);

void enemy_move_type14_sine(uint8_t *image, uint32_t actor);

unsigned actor_script_op_bounce_fall(uint8_t *image, uint32_t actor);
unsigned actor_script_op_set_heading(uint8_t *image, uint32_t actor, uint8_t opcode);
unsigned actor_script_op_random_heading(uint8_t *image, uint32_t actor);
unsigned actor_script_op_thrust_to_centre_y(uint8_t *image, uint32_t actor);
unsigned actor_script_op_aim_at_player(uint8_t *image, uint32_t actor);
unsigned actor_script_op_thrust_to_centre(uint8_t *image, uint32_t actor);
unsigned actor_script_op_random_speed_nudge(uint8_t *image, uint32_t actor);
unsigned actor_script_continue(void);
unsigned actor_script_op_end_frame(void);

/* 0x141c2 — `entity_ptr_from_index`'s SECOND ENTRY POINT — has no core of its own, and that is the
 * transcription rather than an omission: the two entries share one body, differing only in which
 * register the index arrives in (`move.b d0,d6` is all 0x141c0 adds), and both reach the same
 * `and.l #$ff,d6`. So the C is `entity_ptr_from_index` above and the second entry is one more glue,
 * `g_entity_ptr_from_index_d6` in src/enemy.c. A second core would be a copy, not a routine. */

void enemy_morph_to_type6(uint8_t *image, uint32_t entity);
unsigned actor_script_op_fire(uint8_t *image, uint32_t actor, uint8_t opcode);
unsigned actor_script_op_ext(uint8_t *image, uint32_t actor, uint8_t opcode);

void spawn_enemy_shot(uint8_t *image, uint32_t player, uint32_t firing_enemy, uint32_t shot,
                      unsigned want_seeker);
void enemy_shot_tick_type0a(uint8_t *image, uint32_t shot);
void enemy_shot_tick_type0b(uint8_t *image, uint32_t shot);
/* The argument is the CALLER'S OWN D1, not a value this routine computes: the level section is
 * loaded into that register with `move.b` and indexed with `d1.w` on the next instruction, so the
 * chance table's word offset keeps whatever the caller left in the high byte. */
void enemy_fire_and_update_shots(uint8_t *image, uint32_t chance_index_register);

void wavescript_spawn_trio_type0e(uint8_t *image, uint32_t cursor);
void groundscript_spawn_type10(uint8_t *image, uint32_t cursor, uint32_t y_register);
void groundscript_spawn_type0f(uint8_t *image, uint32_t cursor, uint32_t y_register);
void squadron_spawn_tick(uint8_t *image);

void spawn_formation(uint8_t *image, uint16_t formation, uint8_t actor_type, uint16_t base_x,
                     uint16_t base_y, uint8_t fire_flags, uint32_t sprite);
void wavescript_spawn_wave(uint8_t *image, uint32_t cursor, uint16_t opcode, uint16_t base_y,
                           uint8_t actor_type, uint32_t sprite);

/* `void`, though every opcode handler answers in the carry: the VM's own loop consumes that flag
 * (`bcs` back to its head) and its `rts` is reached only where the flag was CLEAR, so the routine
 * always returns carry clear and has no answer of its own to hand back. */
void actor_script_run(uint8_t *image, uint32_t actor);
void enemy_move_scripted(uint8_t *image, uint32_t actor);
void enemies_move_all(uint8_t *image);

#endif /* ZYNAPS_ENEMY_H */
