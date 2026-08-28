/* player.h — the ship's own state and the vertical movers in src/player.c. Subsystem: player.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 */
#ifndef ZYNAPS_PLAYER_H
#define ZYNAPS_PLAYER_H

#include <stdint.h>

/* ================================================================================================
 * The globals this subsystem owns (../out/globals.tsv).
 * ============================================================================================= */
/* The one 0x2c-byte entity array; the index range gives the role (include/entity.h). It is the
 * player's because slots 17/18 are the ship, and every other subsystem reaches it through here. */
#define A_entity_table 0x17a8eu
/* Entity slot 18: the ship record the DRAW side left behind, and the position every player weapon
 * spawns from (`entity_pos_from_ship` @ 0x14092). */
#define A_ship_record_shadow 0x17da6u
/* Frames left before the tilt bank rolls one step; reloaded with SHIP_TILT_PERIOD. */
#define A_ship_tilt_countdown 0x198b2u
/* The ship's roll frame, 0..SHIP_TILT_MAX — which sprite of the bank is drawn. */
#define A_ship_tilt 0x198b3u
/* Eight-byte entries indexed by A_ship_speed_level: +0 dx, +4 dy up, +6 dy down. */
#define A_ship_speed_table 0x19370u
/* The speed entry in force, and the weapon power level; both decay towards a floor. */
#define A_ship_speed_level 0x19907u
#define A_weapon_power_level 0x19908u
/* The 1000-frame timer that steps the weapon level back down. Its sibling for the speed level lives
 * at 0x19dc8 and is not named here, because no routine ported so far reads it — an address nothing
 * pins is one nothing has checked. */
#define A_weapon_decay_timer 0x19dccu

/* ================================================================================================
 * Shared shapes.
 * ============================================================================================= */
/* What a collected power-up reloads either decay timer with (`move.w #$3e8,...`). */
#define POWERUP_DECAY_TICKS 0x3e8u
/* `cmpi.b #$2,$19908` + `bge` in powerup_downgrade_on_death: losing a ship never drops the weapon
 * below level 2, though the speed level does floor at 0. */
#define WEAPON_POWER_LEVEL_MIN 2

/* Offsets into one A_ship_speed_table entry, as ship_move_up / ship_move_down read them. */
#define SHIP_SPEED_DY_UP 4u
#define SHIP_SPEED_DY_DOWN 6u

/* The ship occupies TWO adjacent entity records (slots 17 and 18, its double-buffer pair), and
 * every mover writes the same coordinate into both. 0x30 is `4(a2) + ENTITY_STRIDE`, i.e. the
 * twin's ENTITY_Y — spelt as the literal the instructions carry (`48(a2)`). */
#define SHIP_MIRROR_Y 0x30u

/* The band the ship's y is clamped into (`cmpi.w #$20` + `ble`, `cmpi.w #$9c` + `bge`). */
#define SHIP_Y_MIN 0x20
#define SHIP_Y_MAX 0x9c

/* The tilt bank rolls one frame every SHIP_TILT_PERIOD frames, between 0 and SHIP_TILT_MAX. */
#define SHIP_TILT_PERIOD 4u
#define SHIP_TILT_MAX 6u

/* ================================================================================================
 * Prototypes.
 * ============================================================================================= */
void ship_move_up(uint8_t *image, uint32_t ship, uint32_t speed_entry);
void ship_move_down(uint8_t *image, uint32_t ship, uint32_t speed_entry);

#endif /* ZYNAPS_PLAYER_H */
