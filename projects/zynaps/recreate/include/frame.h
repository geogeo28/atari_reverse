/* frame.h — the game's per-frame loop, in src/frame.c. Subsystem: frame.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 *
 * THIS SUBSYSTEM IS A FLOW, NOT A SET OF FUNCTIONS, exactly as include/init.h's is. The loop runs
 * from 0x10f4e to the `bra.w $10f4e` at 0x1296a and there is not an `rts` anywhere between them:
 * ../../names.txt's four `fn` lines inside it (0x113c0, 0x11c00, 0x11d30, plus the loop head that
 * has only a `cmt`) are `bra` targets, not called routines. So each routine here is a SLICE — a
 * named address range the differential enters at and stops at, `docs/agent-playbook.md` §5's
 * checkpoint-PC and mid-entry-slice techniques — and each carries its range in its own comment.
 *
 * THE STAGE BOUNDARIES ../../names.txt NAMES ARE NOT CONTROL-FLOW BOUNDARIES, and the slices below
 * say so. `frame_panel_scroll_and_ship_stage` either falls through into 0x113c0 or branches PAST it
 * to 0x1167c (three gates on the player's own record), so 0x113c0 is a fall-through address rather
 * than a join. The slices are cut where control really does converge:
 *
 *   [0x10f4e, 0x113c0)  frame_panel_scroll_and_ship_stage   two exits: 0x113c0 and 0x1167c
 *   [0x113c0, 0x1167c)  frame_drone_and_fire_stage          one exit: 0x1167c
 *   [0x1167c, 0x11c00)  frame_spawn_and_move_stage          one exit: 0x11c00
 *   [0x11c00, 0x11d30)  frame_draw_objects_and_collide      one exit: 0x11d30
 *   [0x11d30, 0x1296e)  frame_resolve_hits_and_game_state   FIVE exits (FRAME_EXIT_* below)
 *
 * WHICH OF THE FIVE NAMES ARE ../../names.txt's, exactly. 0x11c00 and 0x11d30 are its own, and the
 * slices are those whole routines. 0x113c0 is its own too — `frame_weapons_and_spawn_stage` — but
 * that name covers the WHOLE 0x113c0..0x11c00, which the cut above splits in two, so each half
 * carries a name of its own, exactly as `highscore_rank_and_shift` does inside
 * `highscore_check_and_insert`. 0x10f4e has only a `cmt` line there and 0x1167c has nothing at all.
 * So three of the five names below are this reconstruction's, proposed in ../out/names_frame.txt;
 * nothing in ../../names.txt is renamed.
 *
 * THE TWO SCRATCH REGISTERS THE LOOP CARRIES ACROSS A VERIFIED CALLEE'S `rts`. Three call sites in
 * `frame_spawn_and_move_stage` read a register that no instruction of the frame loop has written
 * since the last `bsr`, so the value is whatever the callee left behind — and every callee's C is
 * `void`, because a differential of a leaf compares memory and not the registers it did not
 * promise. They are `chance_index_register` and `ground_spawn_y_register` below, they are
 * PARAMETERS rather than derivations, and STATUS.md's "## Coverage limits" carries the residual and
 * what would close it.
 *
 * `ground_spawn_y_register` IS DERIVED WHERE THE LOOP'S OWN INSTRUCTIONS WRITE IT, and the parameter
 * is only the fallback: the wave-script block leaves D7 as the trigger word rounded down to a
 * column (the common path, and the one the ground script almost always fires on) or as the opcode
 * (0x0c / 0x0d), and `frame_wave_script` returns those. Three paths are left — the block skipped
 * because a mothership is pending, and the two that call a spawner and inherit ITS D7 — and those
 * are what the parameter is for.
 */
#ifndef ZYNAPS_FRAME_H
#define ZYNAPS_FRAME_H

#include <stdint.h>

/* ================================================================================================
 * The globals this file names because nothing else does.
 *
 * ../out/globals.tsv assigns most of them to another subsystem, but no ported routine of that
 * subsystem reads them, so its header does not spell them — the house rule (README.md, "Adding a
 * function") puts the definition where it is first read, and STATUS.md's "## Borrowed globals"
 * table carries the debt so the owner can find it. The ones marked NO OWNER are in neither
 * globals.tsv nor any header; ../../names.txt's `var` line is their only prior source.
 * ============================================================================================= */
/* ---- scroll, by subject ---- */
/* Twenty routine pointers, indexed by A_map_column: one specialised page-to-screen blit per
 * 16-pixel column phase (src/scroll.c's `scroll_page_to_screen_p00..p19`). */
#define A_scroll_blit_jump_table 0x179aau

/* ---- video, by ../out/globals.tsv ---- */
/* Three parallax layers x six stars x {screen byte offset .w, x .w}. */
#define A_starfield_table 0x179fau
/* Sixteen single-bit words, indexed by `star_x & 0xf` doubled. */
#define A_starfield_pixel_masks 0x17a42u
/* Halves the middle layer's speed; `not.b` once a frame. */
/* Quarters the far layer's speed; counts 3..0 with `subq.b`+`bpl`. */

/* ---- sprite, by ../out/globals.tsv ---- */
/* Gates the type-0x64 explosion to alternate frames; `not.b` once a frame. */
#define A_explosion_phase_even 0x198adu
/* Twelve sprite pointers, the type-0x65 (large) explosion's frames. Its type-0x64 twin is
 * `A_explosion_small_frame_ptrs` in include/enemy.h. */

/* ---- player, by ../out/globals.tsv ---- */
/* The level section of the player who has just lost a life, compared after the two-player swap to
 * decide whether the game resumes in place or reloads. */
#define A_dying_player_section_index 0x19896u
/* Two 14-byte per-player save records, swapped on death. */
/* Frames between the end-of-section explosion finishing and the section advancing. */

/* ---- weapon, by ../out/globals.tsv ---- */
/* Live type-0x34 projectiles (the plain bullet). include/weapon.h spells its three siblings
 * (0x1990b, 0x1990c, 0x1990d) and not this one. */

/* ---- mothership, by ../out/globals.tsv ---- */
/* Clearing all eight enemy slots twice ends a late section early. */

/* ---- NO OWNER: ../../names.txt's `var` line is the only prior source ---- */
/* The joystick byte the IKBD interrupt publishes: bits 0..3 up/down/left/right, bit 7 fire. */
/* Set while the fire button is held, so the charge counter only runs on a continuous press. */
#define A_fire_button_held 0x198b9u
/* Frames the fire button has been held for; at FIRE_CHARGE_FULL it sets A_fire_charged. */
#define A_fire_charge_counter 0x19901u
/* Which way the charged-weapon palette flash is currently stepping. */
#define A_charge_flash_dir 0x19903u
/* Ten {x .w, y .w} pairs — the ship's position ten frames back, which the trail drone follows. */
#define A_ship_pos_history 0x19f86u
/* Which of those ten pairs is the oldest; wraps at SHIP_POS_HISTORY_ENTRIES. */
#define A_ship_pos_history_index 0x198ffu
/* 500-frame countdown between two frames of the panel's animated logo. */
/* WRITE-ONLY, and the whole image holds exactly one reference to each: `eori.b #$1,$198c7` when a
 * bullet is fired, and `st`/`sf` on 0x19ce5 around the hard section end. ../out/globals.tsv
 * classifies 0x19ce5 `dead` for that reason; 0x198c7 it does not carry at all. Both are
 * transcribed because they are stores the image diff compares, not because they mean anything. */
#define A_bullet_fire_toggle 0x198c7u
#define A_unused_section_end_flag 0x19ce5u

/* ---- sprite banks the loop names as bare longword immediates ---- */
/* The ship's seven tilt frames. src/init.c's `BOOT_SHIP_SOURCE` is the same address under the boot
 * slice's own name — that file has no header, so the two spellings cannot be collapsed today;
 * test_frame.py pins them equal. */
#define A_ship_sprite_bank 0x577feu
/* The two alien banks the attack script's default opcode picks between on a coin flip. */
#define A_wave_alien_sprite_a 0x54ffeu
#define A_wave_alien_sprite_b 0x563feu
/* The power-up capsule a wiped-out squadron leaves behind (type 0x11). */
#define A_powerup_capsule_sprite 0x5f3beu
/* The large (type 0x65) explosion's first frame, and the player's plain bullet (type 0x34). */
#define A_explosion_large_sprite 0x61b5eu
#define A_player_bullet_sprite 0x62a5eu
/* The trail drone the level-4 weapon flies (type 0x35). */

/* ================================================================================================
 * The MFP register the frame's tail re-enables the keyboard interrupt in.
 *
 * `bset #6,$fffa09` is a READ-MODIFY-WRITE of a register outside the image, and the kit's ledger
 * holds its address, its width and its value — but the oracle's read of an unmodeled register
 * answers a fabricated 0, so both sides store `0 | bit` and the five bits the original preserves
 * are unpinned. That is the same residual `mfp_ack_timer_b` (src/irq.c) carries, for the same
 * reason, and `docs/on-target-execution.md`'s hardware-state vector is its surface.
 *
 * IT IS ALSO AN ON-TARGET DEFECT, exactly as include/init.h's `andi.b #$fc,$ff8260` is, and this is
 * the place that says so. A target build compiles `hw_write8` as a plain volatile store
 * (tools/recreate_kit/include/hw.h), so it writes 0x40 into the MFP's interrupt-enable B and CLEARS
 * every other bit TOS had set there — where the original ORs bit 6 into them. Zynaps writes IERB
 * only through this `bset` and its twin in `_start`, so nothing puts them back. A Zynaps build for
 * the real Atari must give the address a read — the kit's seeded READ set, or its own code — rather
 * than compile the expression below. STATUS.md carries the instance.
 *
 * The register is include/init.h's HW_MFP_IERB ($fffa09 — interrupt enable B, whose bit 6 is the
 * keyboard ACIA: include/irq.h's MFP_ACIA_CHANNEL_BIT); the boot's twin `bset` at 0x1068e writes it
 * through the same names. Only the fabricated read-half is spelt here.
 * ============================================================================================= */
#define MFP_IERB_UNMODELED_READ 0u

/* ================================================================================================
 * WHAT THIS FILE DELIBERATELY DOES NOT NAME.
 *
 * Thirteen of the frame loop's constants already have a home in the header of the subsystem that
 * owns the thing they describe, and `src/frame.c` includes those headers rather than making a
 * second copy — which `test_constants.py` cannot see, because it compares names and not meanings
 * (`include/enemy.h` says exactly that above its own pair):
 *
 *   include/weapon.h  TYPE_TRAIL_DRONE, TYPE_POWERUP_CAPSULE, ENTITY_INDEX_SHIP,
 *                     ENTITY_INDEX_TRAIL_DRONE (the gunsight's slot, and the fallback target a
 *                     seeker keeps), WEAPON_KIND_BOMB / _MISSILE / _SEEKER,
 *                     SHIP_DEATH_EXPLOSION_GROUP, DEATH_EVENT_BIT_SHIP
 *   include/enemy.h   EXPLOSION_PART_TYPE (0x64), EXPLOSION_X_ALIGN, EXPLOSION_PART_FRAME (the
 *                     particle's frame counter at +0x10 — NOT EXPLOSION_PART_FRAME, which is the other
 *                     role of the same byte)
 *   include/player.h  POWERUP_DECAY_TICKS
 *   include/mothership.h  MOTHERSHIP_PAIR_BYTES, MOTHERSHIP_TAIL_SEGMENTS
 *
 * The names below that LOOK like duplicates of those are not: each says so where it is defined.
 * ============================================================================================= */

/* ================================================================================================
 * The frame's own shapes.
 * ============================================================================================= */
/* `cmpi.b #$39,$19685` — the space bar's scancode, which pauses the game. */
#define KEY_SCANCODE_SPACE 0x39u
/* `move.b #$8,...` into both palette-cycle counters when the pause begins. */
#define PAUSE_PALETTE_COUNTDOWN 8u

/* The four bits of A_panel_redraw_mask the loop head services are include/hud.h's
 * PANEL_REDRAW_*_BIT. Bit 3 is not tested here (nothing sets it) and bit 4 is the only one NOT
 * cleared after its job runs — `draw_lives_icons` re-runs every frame while the bit stands.
 * `move.w #$1f4,$19dce` is how long the logo frame stands. */
#define PANEL_LOGO_PERIOD 0x1f4u
/* `clr.b d0` before `bsr hud_draw_weapon_icon` — the left cell of the two-cell icon. */
#define PANEL_WEAPON_ICON_LEFT_CELL 0u

/* `lea 152(a0),a0` — the scroll writes its fresh column at byte 152 of the playfield row, which is
 * include/scroll.h's SCROLL_WINDOW_BYTES: the 20th 16-pixel cell, past the visible window. */

/* `lsl.l #2` on the page number — one POINTER per page of include/init.h's A_map_page_table. It is
 * 4 like `include/collision.h`'s COLLISION_ROW_BYTES and unrelated to it: one is a pointer, the
 * other a bitmask row. */
#define MAP_PAGE_PTR_BYTES 4u
/* `lsl.l #3` on the speed level — one ENTRY of include/player.h's A_ship_speed_table, whose three
 * fields that header names (SHIP_SPEED_DY_UP, SHIP_SPEED_DY_DOWN, and the two dx offsets below).
 * It is 8 like include/scroll.h's SCROLL_PHASE_STEP and, again, unrelated: that 8 is a 16-pixel
 * cell of the scroller's workspace. */
#define SHIP_SPEED_ENTRY_BYTES 8u

/* `cmpi.l #$c80,$195cc` + `blt` — how far the level must have scrolled before the mothership is
 * armed, and the mothership index at which the encounter respawns segments instead of starting.
 *
 * The two `move.w`s before each of the two calls (`#$a` into D2, `#$0` into D5) are NOT named here:
 * neither `mothership_begin` nor `mothership_segments_respawn` takes a register, so there is nothing
 * for a constant to be the name of. A target build re-deriving the call sites reads them off the
 * listing at 0x11144 and 0x11150. */
#define MOTHERSHIP_TRIGGER_SCROLL_POS 0xc80u
#define MOTHERSHIP_INDEX_SEGMENTED 5

/* ================================================================================================
 * The trail drone (weapon 4) and the fire/charge state machine.
 * ============================================================================================= */
/* The drone flies the ship's position from SHIP_POS_HISTORY_ENTRIES frames ago, offset by a packed
 * longword: `add.l #$800005,d1` on {x .w, y .w}, so +0x80 in x and +5 in y, with the low word's
 * carry reaching x exactly as the 68000's longword add does. */
#define SHIP_POS_HISTORY_ENTRIES 0xau
#define SHIP_POS_HISTORY_ENTRY_BYTES 4u
#define TRAIL_DRONE_OFFSET_PACKED 0x800005u
#define TRAIL_DRONE_ROWS 9u

/* `addi.b #$1,$19901` + `cmpi.b #$8` — frames of continuous fire before the charged weapon arms. */
#define FIRE_CHARGE_FULL 8u
/* The two horizontal steps of one A_ship_speed_table entry; include/player.h names the vertical
 * pair (SHIP_SPEED_DY_UP at +4, SHIP_SPEED_DY_DOWN at +6) and not these, and this file is their
 * first reader. `move.w (a6),d6` on the way left and `move.w 2(a6),d6` on the way right. */
#define SHIP_SPEED_DX_LEFT 0u
#define SHIP_SPEED_DX_RIGHT 2u
/* The charged flash walks A_palette_hw_shadow up in steps of 0x111 to 0x444 and back down to 0. */
#define CHARGE_FLASH_STEP 0x111u
#define CHARGE_FLASH_PEAK 0x444u

/* `cmpi.b #$4,$198b4` and its three siblings: which weapon the fire button launches. */
/* The one weapon kind include/weapon.h does not name: `cmpi.b #$3,$198b4` is the plain
 * bullet's arm, and nothing outside this loop dispatches on it. */
#define WEAPON_BULLET 3
/* `tst.b $1990a` — a shield level of 0 allows one shot of the selected weapon in flight, any other
 * allows two. It is a test against zero and not a count, which is why 0xff allows two as well. */
#define WEAPON_SHOTS_WITHOUT_SHIELD 1
#define WEAPON_SHOTS_WITH_SHIELD 2
/* `moveq #$13,d6` — the entity index a seeker keeps as its target when the gunsight has no lock. */

/* The plain bullet the fall-through arm launches, at the ship's own position plus this offset. */
#define BULLET_TYPE 0x34u
#define BULLET_SPAWN_DX 0x14u
#define BULLET_SPAWN_DY 8u
#define BULLET_ROWS 3u
#define BULLET_STEP_X 0xcu
#define BULLET_RETIRE_X 0x180u
#define BULLET_SOUND 0xeu

/* ================================================================================================
 * The spawn scripts, the per-slot shot maintenance, and the boss.
 * ============================================================================================= */
/* `move.w (a4),d7` / `divu.w #$24` / `mulu.w #$24`: the wave script's trigger is a map offset
 * rounded DOWN to a whole column, compared against the cursor's own column plus one. */
#define SCRIPT_TRIGGER_LOOKAHEAD 0x24u
/* The three opcodes the wave script handles itself; anything else spawns a formation. */
#define WAVE_OPCODE_TRIO 0x0bu
#define WAVE_OPCODE_SQUADRONS_ON 0x0cu
#define WAVE_OPCODE_SQUADRONS_OFF 0x0du
#define WAVE_SCRIPT_ENTRY_BYTES 4u
/* `bsr rand16` / `lsr.l #4,d0` / `btst #0,d0` — which alien bank a default opcode spawns, and the
 * actor type that goes with each. */
#define WAVE_ALIEN_SHIFT 4
#define WAVE_ALIEN_TYPE_A 0x14u
#define WAVE_ALIEN_TYPE_B 0x16u

/* The per-slot pass over entity slots 0..5. WHICH types get a steering update is
 * include/weapon.h's SHOT_TYPE_SEEKER / SHOT_TYPE_MISSILE; here is the box outside which any of
 * them is retired. */
#define SHOT_X_MIN 0x30
#define SHOT_X_MAX 0x180
#define SHOT_Y_MIN 0x15
#define SHOT_Y_MAX 0xb0
/* `bclr #0,1(a3)` — the low byte of ENTITY_X, so every player shot is forced to an even column. */
#define SHOT_X_ALIGN_BIT 0

/* ================================================================================================
 * The draw-and-collide stage.
 * ============================================================================================= */
#define ENTITY_SLOTS 0x14u
/* `move.w #$14,d0` + `clr.l (a0)+` — TWENTY-ONE longwords cleared over a twenty-entry table. The
 * extra one is the guard row `A_lower_index_masks` describes; include/collision.h's own comment
 * calls the table 21 longs for the same reason. */
#define COLLISION_MASK_LONGS (ENTITY_SLOTS + 1u)

/* ================================================================================================
 * The resolve stage.
 * ============================================================================================= */
/* `moveq #$2,d7` / `moveq #$8,d0` — enemy-shot slots 8, 7 and 6, walked downwards. */
#define ENEMY_SHOT_TOP_SLOT 8u
#define ENEMY_SHOT_SLOT_COUNT 3u
/* `moveq #$13,d0` / `move.b #$9,...` — while the boss owns the playfield the gunsight's answer is
 * forced to slot 9 rather than searched for. */
/* The two entity slots the ship occupies — its live record and the one the draw side left behind.
 * include/player.h names both ADDRESSES (A_player_record is enemy.h's); these are their INDEXES,
 * which is what the collision table is keyed by. */
/* ...and the shadow's, which is ENTITY_INDEX_SHIP + 1 and has no name of its own there. */
#define SHIP_SHADOW_SLOT 18u
/* ...and where the enemy shots start, which is also where "an entity that can explain a ship hit"
 * begins (SHIP_HIT_OWN_SHOT_MASK is the six below it). */
/* It is 6 like include/weapon.h's SHIP_HIT_SCAN_FIRST and says the same thing from the
 * other side: slots 0..5 are the player's shots, so 6 is where everything else starts. */
#define ENEMY_SHOT_SLOT_FIRST 6u
#define ENEMY_SLOT_FIRST 9u
/* `and.l #$1fe00,d1` — bits 9..16, the eight enemy slots, in a gunsight collision row. */
#define GUNSIGHT_ENEMY_MASK 0x1fe00u
/* `and.l #$ffffffc0` / `and.l #$3f` — a ship hit explained by an entity at index 6 or above is a
 * real collision; one explained only by the player's own six shot slots is not; and one explained
 * by nothing at all is the landscape. */
#define SHIP_HIT_ENTITY_MASK 0xffffffc0u
#define SHIP_HIT_OWN_SHOT_MASK 0x3fu
#define BOSS_EXPLOSION_GROUP 0u
/* `btst #1,$19670` — group 1 is the ship's death explosion; group 0 the end-of-section one. */
#define EXPLOSION_BIT_SHIP_DEATH 1
#define EXPLOSION_BIT_SECTION_END 0
#define EXPLOSION_GROUP_COUNT 2u
#define EXPLOSION_GROUP_MEMBERS 6u
/* `cmpi.b #$d,16(a2)` — a group is finished when all six of its particles have reached this frame
 * in their own tag byte (include/enemy.h's EXPLOSION_PART_FRAME offset). */
#define EXPLOSION_DONE_FRAME 0x0du

/* The projectile pass over slots 0..5, and the boss's own damage arm. The two types it names are
 * include/weapon.h's SHOT_TYPE_PUFF and SHOT_TYPE_BOMB. */
#define BOSS_HIT_SOUND 0x2cu
/* Where the boss's death explosion is parked, relative to the mothership anchor. */
#define BOSS_DEATH_EXPLOSION_DX 0x50u
#define BOSS_DEATH_EXPLOSION_DY 6u
/* `bset #1,$198c4` — the death-event flag the boss kill sets; bit 0 is the ship's own. */
#define DEATH_EVENT_BOSS_BIT 1

/* The two explosion animations, which differ only in their gate, their type, their frame table and
 * one extra pair of stores. */
#define EXPLOSION_TYPE_LARGE 0x65u
/* `btst #7,d1` on ENTITY_ALIVE — the record is EXPLODING, and carries its frame in the low seven
 * bits. include/entity.h documents the bit on the field; this is its number, and it is deliberately
 * not spelt as the joystick's fire bit, which is also 7 and means nothing like it.
 *
 * `src/enemy.c` has the same bit as a file-static ENTITY_EXPLODING_BIT; the name differs because a
 * static in a .c cannot be included and `test_constants.py` refuses one constant NAME in two files.
 * STATUS.md's borrowed-globals note carries the pair. */
#define ALIVE_BIT_EXPLODING 7
#define EXPLOSION_FRAME_MASK 0x7fu
/* `cmp.b #$d,d1` — the frame the animation retires on. `src/enemy.c` has the same value as
 * a file-static EXPLOSION_END_FRAME, which a header cannot include. */
#define EXPLOSION_LAST_FRAME 0x0du
/* `lsl.w #2` — one longword of the frame-pointer table per step. THE INDEX IS NOT BOUNDED: the
 * original masks the frame to seven bits, subtracts one AS A BYTE and shifts, so a record whose
 * alive byte was 0xff steps to 0x80 and reads 0x3fc past the table's base — 0x195f8, which is
 * inside the image and is `A_rng_lfsr_state`'s neighbourhood rather than a sprite. Faithful, and
 * the case that drives it is test_frame.py's alive-byte sweep. */
#define EXPLOSION_FRAME_PTR_BYTES 4u
/* `cmpi.b #$aa,20(a2)` — an actor whose spawn tag holds this is not credited to a squadron, so no
 * capsule can be left where it died. */
#define EXPLOSION_NO_CREDIT_TAG 0xaau
/* ...and WHERE that tag is read: `cmpi.b #$aa,20(a2)` is offset 0x14, which include/entity.h's
 * frozen block calls ENTITY_DY. This is its high byte, so the union has one more member than that
 * block lists — a spawn-credit tag the explosion pass reads and nothing else does. Named here
 * rather than in the frozen header, and the tag upgrade it wants is in this wave's report. */
#define EXPLOSION_CREDIT_TAG_OFFSET 0x14u
#define SQUADRON_ID_MASK 0xfu
/* What a wiped-out squadron leaves behind. */
#define POWERUP_CAPSULE_ROWS 0x10u
#define POWERUP_CAPSULE_SPAWN_TAG 1u
#define POWERUP_CAPSULE_SOUND 0x1cu
/* `move.b #$55,30(a2)` and `subi.w #$3,4(a2)` — the large explosion's capsule also gets an anim
 * frame of 0x55 and drifts three pixels up; the small one does neither. */
#define POWERUP_CAPSULE_LARGE_ANIM_FRAME 0x55u
#define POWERUP_CAPSULE_LARGE_RISE 3u

/* The ram / shoot dispatch, shared by the two pairwise passes. */
#define ENEMY_TYPE_BOSS_SEGMENT 0x02u
#define ENEMY_TYPE_INVULNERABLE 0x01u
#define ENEMY_TYPE_ARMOURED_A 0x10u
#define ENEMY_TYPE_ARMOURED_B 0x0fu
#define ENEMY_TYPE_BIG 0x0eu
#define ENEMY_TYPE_SMALL_A 0x14u
#define ENEMY_TYPE_SMALL_B 0x16u
#define ENEMY_HIT_SOUND 0x2cu
/* `move.b #$80,d2` then into ENTITY_ALIVE: the exploding bit with frame 0. */
#define ENEMY_EXPLODING_ALIVE 0x80u
/* `andi.w #$fffc,0(a1)` — an exploding enemy's x is aligned to four pixels. */
/* `and.l #$60000,d1` — bits 17 and 18, the ship's own two records, in an enemy's collision row. */
#define SHIP_RECORD_MASK 0x60000u
/* Which award each kill pays, as an index into include/score.h's four-entry table. */
#define SCORE_AWARD_ENEMY_BIG 0
#define SCORE_AWARD_ENEMY_SMALL 1
#define SCORE_AWARD_CAPSULE 1
#define SCORE_AWARD_BOSS 3

/* THE ORIGINAL'S OWN DEFECT, at 0x122c2 and again at 0x123f4: `33fc 0010 00000008` is
 * `move.w #$10,$8.l` — a word into the 68000's BUS ERROR vector — where `337c 0010 0008` would have
 * been `move.w #$10,8(a1)`, the exploding enemy's row count, which is exactly what the two sibling
 * arms at 0x1225c and 0x123c4 write. names.txt carries the finding on both addresses. It is
 * transcribed rather than corrected, and the address is inside the image, so the byte diff compares
 * it like any other store. */
#define BUS_ERROR_VECTOR 0x8u
#define ENEMY_EXPLOSION_ROWS 0x10u
#define ENEMY_EXPLOSION_ROWS_LARGE 8u

/* The enemy-shot terrain pass, slots 6..8. */
#define GROUND_ABSORB_TYPE_SEEKER 0x0bu
#define GROUND_ABSORB_TYPE_AIMED 0x0cu

/* The starfield: three layers of six stars, each {screen offset .w, x .w}. */
/* Three layers, and `frame_starfield` spells its three calls out rather than looping over
 * this: each layer has its own plane mask and its own speed divider, so a loop would need a
 * table of three two-field rows to say the same thing. It is the TABLE's shape and
 * test_frame.py's star-table staging is its reader. */
#define STARFIELD_LAYERS 3u
#define STARFIELD_STARS 6u
#define STARFIELD_ENTRY_BYTES 4u
#define STARFIELD_RESPAWN_X 0x13fu
/* `and.w #$f,d1` doubled indexes the mask table; `and.w #$fff0,d1` then `lsr.w #1` turns the rest
 * of x into the byte offset of its 16-pixel cell. */
#define STARFIELD_X_PIXEL_MASK 0xfu
#define STARFIELD_X_CELL_MASK 0xfff0u
/* `movem.w (a0),#$00f0` — the four plane words of the cell, tested together so a star is only
 * drawn where the playfield is empty. */
#define STARFIELD_PLANES 4u
#define STARFIELD_PLANE2_OFFSET 4u

/* The three power-up decay timers, all reloaded with the same period. */

/* The scroll step's two wrapping counters — include/init.h's MAP_PAGES and include/scroll.h's
 * SCROLL_PHASES are the same two bounds, read from there. */

/* `cmpi.b #$1,$198a8` + `bne` and `tst.b $198a7` + `bne`: the two busy-waits that end a frame. Both
 * spin on a byte only an interrupt handler writes, so the reconstruction polls them through the
 * kit's scheduled-write model (tools/recreate_kit/include/sched.h) at the PC the ORIGINAL re-reads
 * the byte at, which is what the case's `wait_sites` names. */
#define FRAME_RASTER_WAIT_PC 0x126eeu
#define FRAME_RASTER_PHASE_READY 1u
#define FRAME_VBL_WAIT_PC 0x1270cu
#define FRAME_VBL_WAIT_ARMED 1u
#define FRAME_VBL_WAIT_DONE 0u
/* `move.b #$16,d0` + `bsr ikbd_send_cmd` — interrogate, which makes the controller send one
 * joystick packet. */
#define IKBD_CMD_INTERROGATE_JOYSTICK 0x16u

/* The end-of-game state machine's own numbers. The save record's fields are the seven `(a0)+`
 * steps of 0x12796 and 0x127de, in that order — a longword, three bytes, a longword, three bytes —
 * and naming them is what makes the save half and the restore half visibly mirror each other. The
 * eighth step is a `clr.b` on the save side that the restore side does not read. */
#define PLAYER_SAVE_SCORE 0x0u
#define PLAYER_SAVE_LIVES 0x4u
#define PLAYER_SAVE_SECTION 0x5u
#define PLAYER_SAVE_MAP_PTR 0x6u
#define PLAYER_SAVE_POWERUP_CURSOR 0xau
#define PLAYER_SAVE_WEAPON_LEVEL 0xbu
#define PLAYER_SAVE_SPEED_LEVEL 0xcu
#define PLAYER_SAVE_UNUSED 0xdu
#define PLAYER_SWAP_ATTEMPTS 3u
#define MOTHERSHIP_TURN_FRAME 0x5dcu
#define MOTHERSHIP_LEAVE_FRAME 0x640u
/* The two shapes the turn takes: motherships 0..4 own two adjacent enemy records, 5..15 own four
 * records two apart. */
#define MOTHERSHIP_TAIL_PAIRS 4u
/* ...and the two ADJACENT records the other shape turns (`move.b` twice, 44 apart). */
#define MOTHERSHIP_TAIL_ADJACENT 2u
#define MOTHERSHIP_TURN_HEADING 0x7fu
#define MOTHERSHIP_TURN_SPEED 0xc0u
#define MOTHERSHIP_TURN_FLAG 1u
/* Offsets into the enemy record the turn writes, spelt as the instructions carry them: the second
 * of each pair is one ENTITY_STRIDE further on. */
#define MOTHERSHIP_TURN_HEADING_OFF 0x28u
#define MOTHERSHIP_TURN_SPEED_OFF 0x22u
#define MOTHERSHIP_TURN_FLAG_OFF 0x26u
#define MOTHERSHIP_TURN_CLEAR_OFF 0x27u
/* `cmpi.b #$2,$19915` — two clean sweeps of the eight enemy slots end a late section. */
#define MOTHERSHIP_WAVE_CLEARS_TO_END 2u

/* ================================================================================================
 * TEMPORARY until src/highscore.c's `game_over_screen` lands.
 *
 * 0x12e66 is being ported CONCURRENTLY by another agent; today `include/highscore.h` declares only
 * `game_over_screen_prologue`, the verified `[0x12e66, 0x12e94)` half. The frame's last-life arm
 * calls the WHOLE routine, so this reconstruction declares it here and defines a stub at the end of
 * src/frame.c under the same guard. THE ORCHESTRATOR DELETES THIS BLOCK AT MERGE: when
 * highscore.h declares `game_over_screen` it defines ZYNAPS_HIGHSCORE_HAS_GAME_OVER beside it and
 * BOTH HALVES DISAPPEAR ON THEIR OWN — which is why this file includes that header rather than
 * leaving the guard to an edit somebody has to remember to make. STATUS.md records that the arm is
 * unverified until then, and the stub at the bottom of src/frame.c tallies a REFUSAL rather than
 * returning quietly, so a case that ever reaches it is thrown away by name instead of passing.
 * ============================================================================================= */
#include "highscore.h"

#ifndef ZYNAPS_HIGHSCORE_HAS_GAME_OVER
void game_over_screen(uint8_t *image);
#endif

/* ================================================================================================
 * Prototypes. Each is one slice; the range it covers is in its comment in src/frame.c.
 * ============================================================================================= */
/* Where `frame_resolve_hits_and_game_state` leaves, in the order the disassembly reaches them.
 * The five values are the five addresses the stage's `bra`/`beq` operands name. */
typedef enum {
    FRAME_EXIT_TITLE = 0,            /* 0x10500 — three swaps with nobody alive */
    FRAME_EXIT_RELOAD_SECTION,       /* 0x1083a — the other player is in a different section */
    FRAME_EXIT_RESTART_SECTION,      /* 0x10b6e — ...or in the same one */
    FRAME_EXIT_ADVANCE_SECTION,      /* 0x10814 — the section is over */
    FRAME_EXIT_NEXT_FRAME            /* 0x10f4e — the ordinary case */
} frame_exit;

/* [0x10f4e, 0x113c0) — 1 when control fell through into 0x113c0, 0 when one of the three player
 * gates at 0x111c4/0x111da/0x111e2 branched past it to 0x1167c. */
unsigned frame_panel_scroll_and_ship_stage(uint8_t *image);

/* [0x113c0, 0x1167c). TWO ENTRY REGISTERS, both left by the stage above: `ship` is A2, which
 * 0x111d0 loaded with A_player_record, and `joystick` is D0, which 0x112a0 read out of
 * A_joystick_state. They are parameters rather than the constants the loop always passes, because
 * the range has its own entry point and a case drives it with values the globals do not hold. */
void frame_drone_and_fire_stage(uint8_t *image, uint32_t ship, uint8_t joystick);

/* [0x1167c, 0x11c00). The two register parameters are the ones the header comment describes:
 * `chance_index_register` is D1 at the `bsr` to `enemy_fire_and_update_shots` (0x118cc), whose HIGH
 * BYTE indexes the per-section fire-chance table; `ground_spawn_y_register` is D7 at the `bsr` to
 * `groundscript_spawn_type10`/`_type0f` (0x11818 / 0x11820), whose high word its free-slot guard
 * tests as part of a longword. Both are read straight into a verified callee that takes them, and
 * neither is derivable here. */
void frame_spawn_and_move_stage(uint8_t *image, uint32_t chance_index_register,
                                uint32_t ground_spawn_y_register);

/* [0x11c00, 0x11d30). */
void frame_draw_objects_and_collide(uint8_t *image);

/* [0x11d30, 0x1296e). Returns which of the five addresses the stage left through.
 *
 * `sound_channel` is D0 at 0x11d30, and it is a real input: the stage arms several tunes with it
 * before its own instructions reload it (src/frame.c, "WHAT A VERIFIED CALLEE LEAVES IN D0"). The
 * stage above always leaves ENTITY_SLOTS there, which is what `frame_loop_once` passes. */
frame_exit frame_resolve_hits_and_game_state(uint8_t *image, uint32_t sound_channel);

/* The whole loop body, once: the five slices above in order, with the joystick byte read where the
 * original reads it. The two register parameters are `frame_spawn_and_move_stage`'s, passed
 * straight through — see the header comment. */
frame_exit frame_loop_once(uint8_t *image, uint32_t chance_index_register,
                           uint32_t ground_spawn_y_register);

#endif /* ZYNAPS_FRAME_H */
