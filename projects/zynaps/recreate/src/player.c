/* player.c — the ship's vertical movement.
 *
 * The joystick decoder at 0x112a0 turns bit 0 into `ship_move_up` and bit 1 into `ship_move_down`,
 * handing each a2 = the ship's entity record and a6 = the eight-byte A_ship_speed_table entry the
 * current speed level selects. Two things happen per call: the ship's roll ("tilt") bank rolls one
 * frame towards the end the stick is pushed at, once every SHIP_TILT_PERIOD frames, and the y
 * coordinate steps by that entry's own dy — a different one for up than for down.
 */
#include "machine.h"
#include "entity.h"
#include "player.h"

/* Both movers write the SAME y into the ship's two records — slots 17 and 18, its double-buffer
 * pair — but as two independent read-modify-writes, so the pair may hold different values going in
 * and still step together. */
static void ship_y_step(uint8_t *image, uint32_t ship, uint16_t delta) {
    wr16(image + ship + ENTITY_Y, (uint16_t)(be16(image + ship + ENTITY_Y) + delta));
    wr16(image + ship + SHIP_MIRROR_Y, (uint16_t)(be16(image + ship + SHIP_MIRROR_Y) + delta));
}

static void ship_y_clamp(uint8_t *image, uint32_t ship, uint16_t y) {
    wr16(image + ship + ENTITY_Y, y);
    wr16(image + ship + SHIP_MIRROR_Y, y);
}

/* `subq.b #1,$198b2` + `bne`: the countdown is decremented every call and reloaded only on the
 * frame it reaches zero, which is the frame the tilt bank is allowed to roll. */
static int ship_tilt_due(uint8_t *image) {
    image[A_ship_tilt_countdown] -= 1;
    if (image[A_ship_tilt_countdown] != 0)
        return 0;
    image[A_ship_tilt_countdown] = SHIP_TILT_PERIOD;
    return 1;
}

/* ship_move_up @ 0x11318 — a2 = the ship record, a6 = the speed entry. */
void ship_move_up(uint8_t *image, uint32_t ship, uint32_t speed_entry) {
    if (ship_tilt_due(image) && image[A_ship_tilt] != 0)
        image[A_ship_tilt] -= 1;

    if ((int16_t)be16(image + ship + ENTITY_Y) <= SHIP_Y_MIN) {
        ship_y_clamp(image, ship, SHIP_Y_MIN);
        return;
    }
    /* `sub.w d6,4(a2)` — the same step added as its two's complement. */
    ship_y_step(image, ship, (uint16_t)(0u - be16(image + speed_entry + SHIP_SPEED_DY_UP)));
}

/* ship_move_down @ 0x1135a — a2 = the ship record, a6 = the speed entry. The tilt arm differs from
 * its twin above in more than direction: it stops at SHIP_TILT_MAX with `beq`, not with a `tst`, so
 * a bank already PAST the maximum keeps climbing rather than being held. */
void ship_move_down(uint8_t *image, uint32_t ship, uint32_t speed_entry) {
    if (ship_tilt_due(image) && image[A_ship_tilt] != SHIP_TILT_MAX)
        image[A_ship_tilt] += 1;

    if ((int16_t)be16(image + ship + ENTITY_Y) >= SHIP_Y_MAX) {
        ship_y_clamp(image, ship, SHIP_Y_MAX);
        return;
    }
    ship_y_step(image, ship, be16(image + speed_entry + SHIP_SPEED_DY_DOWN));
}

/* ================================================================================================
 * Glue. Register map for both: A2 = the ship record, A6 = the speed-table entry. No register
 * answers — everything either routine does lands in the image.
 * ============================================================================================= */
void g_ship_move_up(uint8_t *image, uint32_t ship, uint32_t speed_entry) {
    ship_move_up(image, ship, speed_entry);
}

void g_ship_move_down(uint8_t *image, uint32_t ship, uint32_t speed_entry) {
    ship_move_down(image, ship, speed_entry);
}
