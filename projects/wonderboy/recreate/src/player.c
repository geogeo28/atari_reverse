/* player.c — the player's own frame: the routines behaviour slot 1 calls that reach nothing this
 * port lacks, and the spawn helper beside them. See player.h for what each one is and
 * ../STATUS.md's batch-40 partition for what the frame still calls that is not here.
 *
 * THE RECORD IS AN ADDRESS REGISTER, so every field access goes through bus.h's own accessors —
 * the same eight src/behavior.c uses, which is why they live in that header rather than twice here:
 * `actor_behavior_pass` follows a table pointer out of memory and hands it on, and nothing between
 * there and here bounds it. The GLOBALS are a different matter — every one of them is a fixed
 * operand in the instruction, so those are read and written directly.
 *
 * EVERY COMPARISON HERE IS A SIGNED ONE OF THE OPERANDS at the width the instruction names, which is
 * where this file's one byte-sized trap lives: `subq.b` on a byte field wraps into $ff rather than
 * going negative, so the ascent entered on a zero speed runs for another 255 frames.
 */
#include <stdint.h>

#include "actor.h"
#include "bus.h"
#include "hud.h"
#include "input.h"
#include "machine.h"
#include "map.h"
#include "os.h"
#include "player.h"
#include "sound.h"
#include "text.h"
#include "wonderboy.h"

/* `subq.b #n,d16(An)` — a byte field spent IN MEMORY, and the value that lands there. The store
 * happens whether or not the caller reads the answer, and a caller that reads the field AGAIN must
 * re-read it: a record at an address bus.h refuses is written nowhere and reads back as zero. */
static uint8_t spend_field_b(uint8_t *image, uint32_t record, uint32_t offset, uint8_t amount) {
    uint8_t left = (uint8_t)(field_b(image, record, offset) - amount);

    set_field_b(image, record, offset, left);
    return left;
}

/* --- $a76: the death check ---------------------------------------------------------------------
 *
 * `tst.w WB_HUD_METER_VALUE / bne` — the whole routine is behind an empty meter, so on all but one
 * frame of a life it writes nothing at all.
 */

/* $a92 — the revival arm. The rearm is SKIPPED while the cheat word is up, which is what makes the
 * medicine unspendable rather than merely plentiful: the same word chose this arm in the first
 * place, so a cheating player revives on every death for ever. */
static void player_revive(uint8_t *image) {
    snd_call_trigger_effect(image, WB_PLAYER_DEATH_SFX, WB_SND_CHANNEL_A);
    if (be16(image + WB_KEY_SEQUENCE_MATCHED) == 0)
        wr16(image + WB_HUD_SLOT_BBC6, WB_HUD_SLOT_REARM);

    text_post_message(image, WB_TEXT_MESSAGE_REVIVAL_USED);
    wr16(image + WB_HUD_METER_VALUE, WB_PLAYER_METER_REVIVE);
}

/* $acc — the death itself. `tst.w / bmi` on WB_STAGE_RESET_BLOCK's first word is a SIGN test and not
 * a zero one, so a word already holding the $ffff this arm writes takes no second death — that word
 * is the handshake `player_pending_event_gate` spends on the frames after. */
static void player_die(uint8_t *image, uint32_t actor) {
    flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT);
    if ((int16_t)be16(image + WB_STAGE_RESET_BLOCK) < 0)
        return;

    wr16(image + WB_STATE_FLAG_A34, WB_PLAYER_DEATH_FLAG_SET);
    snd_play_song(image, WB_PLAYER_DEATH_SONG);
    wr16(image + WB_STAGE_RESET_BLOCK, WB_PLAYER_DEATH_FLAG_SET);
    wr16(image + WB_SCROLL_FOLLOW_FROZEN, WB_PLAYER_DEATH_FLAG_SET);
    wr16(image + WB_PANEL_FRAME_HOLD, WB_PLAYER_DEATH_FLAG_SET);
}

void player_meter_empty_check(uint8_t *image, uint32_t actor) {
    if (be16(image + WB_HUD_METER_VALUE) != 0)
        return;

    /* `tst.b` on the slot's VALUE byte, not on the word: a slot holding $00ff — rearmed, redraw
     * pending — is an empty slot to this test. */
    if (image[WB_HUD_SLOT_BBC6] != 0 || be16(image + WB_KEY_SEQUENCE_MATCHED) != 0) {
        player_revive(image);
        return;
    }
    player_die(image, actor);
}


/* --- $e06: the jump machine --------------------------------------------------------------------
 *
 * Entered only from `player_gate_on_1516`'s `beq.w`, which is the whole of its caller census.
 */

/* $ea8 — the ascent. `sub.w d0,2(a0)` takes a ZERO-EXTENDED byte off the y, so the record always
 * rises; the `bne` then reads the byte the `subq.b` just left, and a speed of 0 wraps to $ff rather
 * than ending the climb — 255 more frames of it. */
static void player_ascend(uint8_t *image, uint32_t actor) {
    uint8_t speed = field_b(image, actor, WB_ACTOR_SPEED);

    set_field_w(image, actor, WB_ACTOR_Y, (uint16_t)(field_w(image, actor, WB_ACTOR_Y) - speed));
    if (spend_field_b(image, actor, WB_ACTOR_SPEED, 1) != 0)
        return;

    flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT);
    set_field_b(image, actor, WB_ACTOR_SPEED, WB_PLAYER_SPEED_AFTER_JUMP);
}

/* $e6c — the launch, on the rising edge alone. The speed it loads is WB_ACTOR_FIELD_10, the byte the
 * head of this routine has just written, so the strength is this frame's and not the one the record
 * was carrying. */
static void player_launch_jump(uint8_t *image, uint32_t actor) {
    if (!(joy1_newly_pressed(image) & (1u << WB_JOY1_UP_BIT)))
        return;

    snd_call_trigger_effect(image, WB_PLAYER_JUMP_SFX, WB_SND_CHANNEL_A);
    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT);
    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_LAUNCHED_BIT);
    flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
    set_field_b(image, actor, WB_ACTOR_SPEED, field_b(image, actor, WB_ACTOR_FIELD_10));
}

/* $e2e — the wing boots. `subq.b #1,$bbc2.l` spends the slot's VALUE byte and the `bne` reads what
 * it left, so the rearm fires on the frame the last charge goes — and the rearm is a WORD write, so
 * the value goes back to zero and the request byte beside it comes up.
 *
 * IT IS THE THIRD ORIGINAL OF ONE IDIOM and is spelt here rather than shared: src/actor.c's
 * `hud_slot_spend_charge` is the same four instructions for the two damage paths, and that file's
 * own comment argues against exporting a symbol to save one `wr16`. What is different here is the
 * `btst` on the joystick between the test and the spend, and the speed write above it. */
static void player_hover_on_wing_boots(uint8_t *image, uint32_t actor) {
    if (image[WB_HUD_SLOT_BBC2] == 0)
        return;
    if (!(image[WB_JOY1_CURRENT] & (1u << WB_JOY1_UP_BIT)))
        return;

    set_field_b(image, actor, WB_ACTOR_SPEED, WB_PLAYER_SPEED_AFTER_JUMP);
    image[WB_HUD_SLOT_BBC2] = (uint8_t)(image[WB_HUD_SLOT_BBC2] - 1);
    if (image[WB_HUD_SLOT_BBC2] != 0)
        return;

    wr16(image + WB_HUD_SLOT_BBC2, WB_HUD_SLOT_REARM);
    text_post_message(image, WB_TEXT_MESSAGE_WING_BOOTS_LOST);
}

void player_jump_step(uint8_t *image, uint32_t actor) {
    uint16_t strength = be16(image + WB_EFFECT_STATE_BD6A);

    wr16(image + WB_TILE_33_STEP, 0);
    /* `addi.b #$8,d0` — the low BYTE of the state word, so nothing carries into its high half. */
    set_field_b(image, actor, WB_ACTOR_FIELD_10,
                (uint8_t)(strength + WB_PLAYER_JUMP_STRENGTH_BIAS));

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT))
        player_ascend(image, actor);
    else if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT))
        player_launch_jump(image, actor);
    else
        player_hover_on_wing_boots(image, actor);
}


/* --- $d84: the ladder --------------------------------------------------------------------------
 *
 * The two arms are one body with the y step and the mode word changed, which is how they are
 * written; what they share is the snap that puts the record on the ladder's own centre line.
 */
static void player_climb(uint8_t *image, uint32_t actor, int up) {
    int16_t y;

    flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT);
    flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_LAUNCHED_BIT);
    wr16(image + WB_TILE_33_STEP, WB_TILE_33_STEP_RAISED);

    set_field_w(image, actor, WB_ACTOR_X,
                (uint16_t)((field_w(image, actor, WB_ACTOR_X) & WB_PLAYER_LADDER_X_MASK)
                           + WB_PLAYER_LADDER_X_BIAS));
    wr16(image + WB_TILE_33_MODE, up ? WB_TILE_33_MODE_UP : WB_TILE_33_MODE_DOWN);

    /* THE y IS READ HERE, not at the top: `subq.w #2,2(a0)` is the LAST instruction but one, below
     * both global stores. For a record whose address makes `actor + 2` one of them — WB_TILE_33_MODE
     * is $1516 and WB_TILE_33_STEP $1518, so `actor` of $1514 or $1516 does it — the original reads
     * back the word it has just published and this reads the same one. Hoisting the read would be a
     * divergence no case here can drive, since every case seeds its record in an actor table. */
    y = field_w(image, actor, WB_ACTOR_Y);
    y = (int16_t)(up ? y - WB_PLAYER_LADDER_STEP : y + WB_PLAYER_LADDER_STEP);
    set_field_w(image, actor, WB_ACTOR_Y, (uint16_t)y & WB_PLAYER_LADDER_Y_MASK);
}

void player_apply_joystick(uint8_t *image, uint32_t actor) {
    uint8_t held = image[WB_JOY1_CURRENT];

    if (be16(image + WB_TILE_33_FLAG) != 0) {
        if (held & (1u << WB_JOY1_UP_BIT)) {
            player_climb(image, actor, 1);
            return;
        }
        if (held & (1u << WB_JOY1_DOWN_BIT)) {
            player_climb(image, actor, 0);
            return;
        }
    }
    wr16(image + WB_TILE_33_STEP, 0);
}


/* --- $107c: leaving the ladder ---------------------------------------------------------------- */
void player_reset_ground_state(uint8_t *image, uint32_t actor) {
    wr16(image + WB_TILE_33_MODE, 0);
    flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT);
    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_LAUNCHED_BIT);

    /* `move.w $bd6a.l,d0` sits BELOW the three bit writes, where the jump machine's sits above its
     * own — so the read is spelt here rather than hoisted: a record at $bd62 puts its flag byte on
     * WB_EFFECT_STATE_BD6A's high half and the original would read back what it just wrote. Then
     * `addq.b #8,d0`, where $e12 spells `addi.b #$8,d0`: one number, two encodings. */
    set_field_b(image, actor, WB_ACTOR_SPEED,
                (uint8_t)(be16(image + WB_EFFECT_STATE_BD6A) + WB_PLAYER_JUMP_STRENGTH_BIAS));
}


/* --- $539e: the event actor's spawn ------------------------------------------------------------
 *
 * EIGHT `move.l`s through two post-incrementing registers, and the first of them is not the
 * template's: the record's x and y come out of the scene descriptor. That is why the template at
 * WB_ACTOR_TYPE35_TEMPLATE opens with four bytes nothing ever reads.
 */
/* The seven longwords the TEMPLATE supplies, which is the destination RECORD's size less the
 * position longword that took the first one's place — the two sizes are the same 32 bytes and the
 * coupling is real rather than a coincidence, because `scene_copy_record_fields` fills a record
 * from a template shaped exactly like one. */
#define TEMPLATE_LONGWORDS ((WB_ACTOR_RECORD_BYTES - WB_LONGWORD_BYTES) / WB_LONGWORD_BYTES)

void scene_copy_record_fields(uint8_t *image, uint32_t spawn_template,
                              uint32_t destination) {
    uint32_t scene = be32(image + WB_RECORD_PTR_10420);
    uint32_t source = addr_add(spawn_template, WB_SPAWN_TEMPLATE_UNREAD);
    unsigned i;

    bus_write_long(image, destination,
                   bus_read_long(image, addr_add(scene, WB_SCENE_SPAWN_POSITION)));

    for (i = 0; i < TEMPLATE_LONGWORDS; i++)
        bus_write_long(image, addr_add(destination, (i + 1) * WB_LONGWORD_BYTES),
                       bus_read_long(image, addr_add(source, i * WB_LONGWORD_BYTES)));
}


/* --- $ec8: the walk ------------------------------------------------------------------------------
 *
 * FIVE SECTIONS IN A ROW, each falling into the next and none of them returning early out of the
 * routine — which is why they are five `static void`s called in order rather than one body. Only
 * the last of them, the accelerator, has arms that end the frame.
 */

/* $ec8 — THE KNOCK-BACK. WB_ACTOR_FIELD_29 is the step count `actor_stun_followed` ($6796) seeds;
 * while it is nonzero the record is pushed one map step in the direction OPPOSITE to the side flag
 * — set means the followed record is to the LEFT (actor.h), and this steps right — and one is spent.
 *
 * The count is read into d7 BEFORE the probe and spent from MEMORY afterwards, which is what the
 * two statements below are: `moveq #0,d7 / move.b 29(a0),d7 / ... / subq.b #1,29(a0)`. */
static void player_spend_knockback(uint8_t *image, uint32_t actor) {
    uint8_t steps = field_b(image, actor, WB_ACTOR_FIELD_29);

    if (steps == 0)
        return;

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT))
        step_right(image, actor, steps);
    else
        step_left(image, actor, steps);
    spend_field_b(image, actor, WB_ACTOR_FIELD_29, 1);
}

/* $ef0 — THE FIRE EDGE. `tst.b d0 / bpl` on `joy1_newly_pressed`'s byte is a SIGN test of bit 7, the
 * fire button, so this is a rising edge whatever else the stick is doing — where the weapon's own
 * gate one call later wants that byte to be WB_PLAYER_FIRE_EDGE_EXACT and nothing else. */
static void player_arm_on_fire(uint8_t *image, uint32_t actor) {
    if (!(joy1_newly_pressed(image) & (1u << WB_JOY1_FIRE_BIT)))
        return;

    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FIRED_BIT);
    flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
    set_field_b(image, actor, WB_ACTOR_FIELD_22, 0);
}

/* $f0a — THE FLICKER COUNTDOWN, and `subq.b #1,21(a0)` here is WB_ACTOR_FLICKER_COUNTDOWN's ONE
 * reader in the image. The frame it reaches zero lowers the flicker bit AND the invulnerability the
 * damage path raised beside it. */
static void player_tick_flicker(uint8_t *image, uint32_t actor) {
    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT))
        return;
    if (spend_field_b(image, actor, WB_ACTOR_FLICKER_COUNTDOWN, 1) != 0)
        return;

    flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT);
    flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_INVULNERABLE_BIT);
}

/* $f28 — THE HURT DRIFT, the arm WB_ACTOR_FLAGS2_BIT_0 gates. `actor_damage_followed` ($69fe) is
 * what writes the pair this spends: WB_ACTOR_FIELD_31 is how far the knock-back has left to run
 * (WB_ACTOR_DAMAGE_FIELD_31_BASE less twice a state word) and WB_ACTOR_FIELD_30 is which way.
 *
 * LANDING ENDS IT: a record that has picked WB_ACTOR_FLAG_SUPPORTED_BIT back up lowers the gate bit
 * instead of drifting. And the step distance is the count as it was BEFORE the spend — d7 is loaded
 * above the `subq.b` — so a count of zero still takes a probe, of zero pixels. */
static void player_run_hurt_drift(uint8_t *image, uint32_t actor) {
    uint8_t steps;

    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0))
        return;
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT)) {
        flag_clear(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
        return;
    }

    steps = field_b(image, actor, WB_ACTOR_FIELD_31);
    if (steps != 0)
        spend_field_b(image, actor, WB_ACTOR_FIELD_31, WB_PLAYER_DRIFT_SPEND);

    if (field_b(image, actor, WB_ACTOR_FIELD_30) != 0)
        step_right(image, actor, steps);
    else
        step_left(image, actor, steps);
}

/* $ff2 / $105c — THE TWO TAILS every arm of the accelerator leaves through. Each RE-READS
 * WB_ACTOR_FIELD_22 rather than carrying the arm's own value down, because the arms above write it
 * and the tail is what a `bra` reaches: `clr.w d7 / move.b 22(a0),d7 / beq / bsr`. A zero speed
 * takes no probe at all. */
static void player_take_walk_step(uint8_t *image, uint32_t actor, int travelling_right) {
    uint8_t speed = field_b(image, actor, WB_ACTOR_FIELD_22);

    if (speed == 0)
        return;

    if (travelling_right)
        step_right(image, actor, speed);
    else
        step_left(image, actor, speed);
}

/* $1002 / $106a — TURNING, i.e. the frame a held direction disagrees with WB_ACTOR_FIELD_23. The
 * speed is spent DOWN first and the record keeps travelling the OLD way while it lasts; the frame
 * the `subq.b` goes negative zeroes the speed, writes the new direction and steps the NEW way,
 * which with a zero speed is no step at all.
 *
 * THE TWO RATES DIFFER — see WB_PLAYER_TURN_DECEL_RIGHT/_LEFT — and this is the one asymmetry in
 * the accelerator. `bpl` reads what the `subq.b` LEFT, so a speed of zero on entry wraps to $ff and
 * takes the flip arm rather than running 255 frames of turn. */
static void player_turn_around(uint8_t *image, uint32_t actor, int turning_right) {
    uint8_t decel = turning_right ? WB_PLAYER_TURN_DECEL_RIGHT : WB_PLAYER_TURN_DECEL_LEFT;

    if ((int8_t)spend_field_b(image, actor, WB_ACTOR_FIELD_22, decel) >= 0) {
        player_take_walk_step(image, actor, !turning_right);
        return;
    }

    set_field_b(image, actor, WB_ACTOR_FIELD_22, 0);
    set_field_b(image, actor, WB_ACTOR_FIELD_23,
                turning_right ? WB_ACTOR_ST_BYTE : 0);
    player_take_walk_step(image, actor, turning_right);
}

/* $fcc / $1036 — the acceleration itself, and it runs on one frame in four. The ceiling is
 * WB_EFFECT_STATE_BD6A plus WB_PLAYER_WALK_SPEED_BIAS, and `cmp.b 22(a0),d0 / bgt` is a SIGNED BYTE
 * comparison of that word's LOW BYTE against the field — so a ceiling byte above $7f reads as below
 * every ordinary speed and clamps on the spot. */
static void player_accelerate_walk(uint8_t *image, uint32_t actor) {
    uint8_t subframe, ceiling;

    /* `addq.b #1,24(a0)` then `andi.b #$3,24(a0)`: two stores to one byte, and the ledger records
     * the final value, so they are ONE expression here — the same silence player_climb's x and y
     * carry.
     *
     * BOTH TESTS BELOW RE-READ THE FIELD rather than the value just computed, because both original
     * instructions do: `andi.b` and `cmp.b` fetch 24(a0) and 22(a0) again, and for a record at an
     * address bus.h refuses the store is dropped and the fetch answers ZERO — so a port that tested
     * its own local would take the other arm. Nothing here can reach such a record (the player's
     * comes out of the actor table), but this file's own `spend_field_b` plate states the rule and
     * player_spend_one_shot obeys it, so the walk does too. */
    subframe = (uint8_t)((field_b(image, actor, WB_ACTOR_FIELD_24) + 1)
                         & WB_PLAYER_WALK_SUBFRAME_MASK);
    set_field_b(image, actor, WB_ACTOR_FIELD_24, subframe);
    if (field_b(image, actor, WB_ACTOR_FIELD_24) != 0)
        return;

    set_field_b(image, actor, WB_ACTOR_FIELD_22,
                (uint8_t)(field_b(image, actor, WB_ACTOR_FIELD_22) + 1));

    ceiling = (uint8_t)(be16(image + WB_EFFECT_STATE_BD6A) + WB_PLAYER_WALK_SPEED_BIAS);
    if ((int8_t)ceiling > (int8_t)field_b(image, actor, WB_ACTOR_FIELD_22))
        return;
    set_field_b(image, actor, WB_ACTOR_FIELD_22, ceiling);
}

/* $fa8 / $1014 — the arm a HELD direction takes. Its first act is to leave a ladder, which is
 * `player_reset_ground_state`'s only pair of call sites in the image. */
static void player_walk_arm(uint8_t *image, uint32_t actor, int rightward) {
    if (be16(image + WB_TILE_33_MODE) != 0)
        player_reset_ground_state(image, actor);

    if (rightward)
        flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
    else
        flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVED_BIT);

    /* `move.b 23(a0),d6 / bne` on the left arm and `/ beq` on the right: the same question asked
     * with opposite polarity, i.e. "does the direction byte already agree with the stick". */
    if ((field_b(image, actor, WB_ACTOR_FIELD_23) != 0) != (rightward != 0)) {
        player_turn_around(image, actor, rightward);
        return;
    }
    player_accelerate_walk(image, actor);
    player_take_walk_step(image, actor, rightward);
}

/* $f7e — the arm NEITHER direction takes: the moved bit lowered and one off the speed a frame,
 * still travelling whichever way WB_ACTOR_FIELD_23 says. `bpl` reads what the `subq.b` left, so a
 * speed that was already negative is zeroed and the frame ends without a step. */
static void player_coast(uint8_t *image, uint32_t actor) {
    flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVED_BIT);

    if (field_b(image, actor, WB_ACTOR_FIELD_22) == 0)
        return;
    if ((int8_t)spend_field_b(image, actor, WB_ACTOR_FIELD_22, 1) < 0) {
        set_field_b(image, actor, WB_ACTOR_FIELD_22, 0);
        return;
    }
    player_take_walk_step(image, actor, field_b(image, actor, WB_ACTOR_FIELD_23) != 0);
}

/* $f6a — the accelerator's own head: `btst #3,$8cf.w` then `btst #2`, so RIGHT is tested first and
 * holding both walks right. */
static void player_walk(uint8_t *image, uint32_t actor) {
    uint8_t held = image[WB_JOY1_CURRENT];

    if (held & (1u << WB_JOY1_RIGHT_BIT))
        player_walk_arm(image, actor, 1);
    else if (held & (1u << WB_JOY1_LEFT_BIT))
        player_walk_arm(image, actor, 0);
    else
        player_coast(image, actor);
}

void player_step_and_arm(uint8_t *image, uint32_t actor) {
    player_spend_knockback(image, actor);
    player_arm_on_fire(image, actor);
    player_tick_flicker(image, actor);
    player_run_hurt_drift(image, actor);
    player_walk(image, actor);
}


/* --- $1208: the weapon --------------------------------------------------------------------------
 *
 * DOWN plus a FIRE edge spends one packed-BCD unit off the newest WB_EFFECT_RECORD_LIST record and
 * spawns whatever that record's HIGH byte names. See player.h for the entry-X reading.
 */

/* $1292 — the block the WIND SPOUT runs and the BOMB branches into, which is why it is one function
 * here rather than two copies: $1308 writes its own type and lifetime and then `bra.w $1292`.
 *
 * The shot inherits the player's WHOLE WB_ACTOR_FLAGS byte (so it flies the way he faces), is put
 * into the launched state with the flicker bit knocked back down, and takes its position from the
 * player's own x,y longword. */
static void player_arm_thrown_shot(uint8_t *image, uint32_t actor, uint32_t shot) {
    set_field_w(image, shot, WB_ACTOR_SPRITE, 0);
    set_field_b(image, shot, WB_ACTOR_FLAGS, field_b(image, actor, WB_ACTOR_FLAGS));
    set_field_b(image, shot, WB_ACTOR_FLAGS2, 0);
    flag_clear(image, shot, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT);
    flag_set(image, shot, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT);
    flag_set(image, shot, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_LAUNCHED_BIT);
    set_field_b(image, shot, WB_ACTOR_SPEED, WB_PLAYER_SHOT_SPEED);

    bus_write_long(image, addr_add(shot, WB_ACTOR_X),
                   bus_read_long(image, addr_add(actor, WB_ACTOR_X)));
    /* `move.l #$60008,14(a1)` — WB_ACTOR_HALF_WIDTH and WB_ACTOR_SIZE_SECOND in one store. */
    bus_write_long(image, addr_add(shot, WB_ACTOR_HALF_WIDTH),
                   ((uint32_t)WB_PLAYER_SHOT_HALF_WIDTH << 16) | WB_PLAYER_SHOT_SIZE_SECOND);
}

/* $12c4 — the FIREBALL, which shares nothing below its own `bsr $1b8e`: it copies only the side bit
 * rather than the whole flags byte, clears the sprite word's HIGH BYTE alone (`clr.b 6(a1)` against
 * the block above's `clr.w`), and leaves the shot eight pixels above the player.
 *
 * IT RETURNS THAT `subq.w #8,2(a1)`'s BORROW, which is the X the `sbcd` below folds in — the one
 * arm of the four that produces the bit rather than inheriting it. */
static unsigned player_arm_fireball(uint8_t *image, uint32_t actor, uint32_t shot) {
    uint16_t y;
    unsigned borrow;

    set_field_w(image, shot, WB_ACTOR_TYPE, WB_PLAYER_SHOT_TYPE_FIREBALL);
    set_field_b(image, shot, WB_ACTOR_FIELD_30, WB_PLAYER_SHOT_LIFETIME);
    bus_write_long(image, addr_add(shot, WB_ACTOR_X),
                   bus_read_long(image, addr_add(actor, WB_ACTOR_X)));

    y = (uint16_t)field_w(image, shot, WB_ACTOR_Y);
    set_field_w(image, shot, WB_ACTOR_Y, (uint16_t)(y - WB_PLAYER_FIREBALL_Y_RISE));
    borrow = y < WB_PLAYER_FIREBALL_Y_RISE;

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT))
        flag_set(image, shot, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
    else
        flag_clear(image, shot, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
    set_field_b(image, shot, WB_ACTOR_SPRITE, 0);
    return borrow;
}

/* $1258 — ONE SHOT SPENT, and the record POPPED when the count runs out.
 *
 * `addq.l #2,a6 / lea $1333.l,a2 / sbcd -(a2),-(a6)` lands the subtract on WB_RECORD_LOW_BYTE of the
 * record WB_EFFECT_RECORD_WRITE_PTR names, with the subtrahend a byte of this routine's OWN 300
 * (WB_PLAYER_WEAPON_SPEND_BCD). `tst.b (a6)` then RE-READS the byte just written — the store can be
 * dropped for a record the bus refuses — and a zero rewinds the write pointer by one record. */
static void player_spend_one_shot(uint8_t *image, uint32_t record, unsigned entry_extend) {
    uint32_t count_at = addr_add(record, WB_RECORD_LOW_BYTE);
    unsigned extend = entry_extend;

    bus_write_byte(image, count_at,
                   sbcd_byte(image[WB_PLAYER_WEAPON_SPEND_BCD], bus_read_byte(image, count_at),
                             &extend));
    image[WB_RECORD_FRESH_FLAG] = WB_ACTOR_ST_BYTE;

    if (bus_read_byte(image, count_at) != 0)
        return;
    wr32(image + WB_EFFECT_RECORD_WRITE_PTR,
         be32(image + WB_EFFECT_RECORD_WRITE_PTR) - WB_EFFECT_RECORD_LEN);
}

void player_weapon_fire(uint8_t *image, uint32_t actor, unsigned entry_extend) {
    unsigned extend_at_sbcd = entry_extend;
    uint32_t record, shot;
    uint8_t item;

    if (be16(image + WB_TILE_33_FLAG) != 0)
        return;
    /* `cmpi.l #$b444,$b546.l` — the write pointer still at the base of the list, i.e. nothing held.
     * The list grows UPWARD and the pointer addresses the newest record (wonderboy.h). */
    if (be32(image + WB_EFFECT_RECORD_WRITE_PTR) == WB_EFFECT_RECORD_LIST)
        return;
    if (joy1_newly_pressed(image) != WB_PLAYER_FIRE_EDGE_EXACT)
        return;
    if (!(image[WB_JOY1_CURRENT] & (1u << WB_JOY1_DOWN_BIT)))
        return;

    record = be32(image + WB_EFFECT_RECORD_WRITE_PTR);
    item = bus_read_byte(image, record);
    if (item == WB_PLAYER_WEAPON_LIGHTNING) {
        wr16(image + WB_FLASH_TIMER, WB_PLAYER_LIGHTNING_FLASH);
        player_spend_one_shot(image, record, extend_at_sbcd);
        return;
    }

    /* THE OTHER THREE ARMS ALL OPEN `bsr $1b8e / cmpa.l #$0,a1 / bne / rts`, and the allocation is
     * lifted out of them here rather than spelt three times: it is each arm's FIRST act, it writes
     * no memory and reads only the table, and the lightning arm above never reaches it — so one
     * call is the same three calls. A FULL POOL ENDS THE FRAME WITHOUT SPENDING ANYTHING, which is
     * what those three `rts` above the shared `sbcd` are for. */
    shot = actor_alloc_slot_high(image);
    if (shot == WB_ACTOR_ALLOC_NONE)
        return;

    if (item == WB_PLAYER_WEAPON_WIND_SPOUTS) {
        set_field_w(image, shot, WB_ACTOR_TYPE, WB_PLAYER_SHOT_TYPE_WIND);
        set_field_b(image, shot, WB_ACTOR_FIELD_30, WB_PLAYER_SHOT_LIFETIME_WIND);
        player_arm_thrown_shot(image, actor, shot);
    } else if (item == WB_PLAYER_WEAPON_FIRE_BALLS) {
        extend_at_sbcd = player_arm_fireball(image, actor, shot);
    } else {
        set_field_b(image, shot, WB_ACTOR_FIELD_30, WB_PLAYER_SHOT_LIFETIME);
        set_field_w(image, shot, WB_ACTOR_TYPE, WB_PLAYER_SHOT_TYPE_BOMB);
        player_arm_thrown_shot(image, actor, shot);
    }
    player_spend_one_shot(image, record, extend_at_sbcd);
}
