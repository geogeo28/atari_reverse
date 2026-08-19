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


/* --- $1f54: the stage transition, and the frame's LAST call ---------------------------------------
 *
 * FOUR ARMS OVER FOUR FLAG WORDS, tested in one chain ($1f54 / $1fa2 / $1fd6 / $1ffc) with two
 * shared tails ($205c's bare `rts` and the posture selector at $205e). The first three are
 * cutscene animations that own the player's sprite outright; the fourth is what runs on an ordinary
 * frame, and it is where the player's POSTURE — standing, walking, jumping, falling, climbing,
 * swinging — becomes a sprite id.
 *
 * IT IS ALSO WHERE THE WALK'S TWO FLAG BITS ARE SPENT. WB_ACTOR_FLAG_FIRED_BIT (raised at $efa) is
 * read at $20ca and lowered at $212a, and WB_ACTOR_FLAG_MOVED_BIT (three sites in the walk) is read
 * at $2184 — so what `player_step_and_arm` buys by writing them is decided here and nowhere else,
 * which retires the last of batch 40's honesty items about the pair.
 */

/* The shape all four animations share: the cursor is the word IMMEDIATELY BELOW its own table and
 * the frame is fetched at `table + cursor` with the cursor SIGN-EXTENDED, which is what
 * `lea 0(a1,d0.w),a1 / move.w (a1),6(a0)` does. */
static void transition_publish_frame(uint8_t *image, uint32_t actor, uint32_t table,
                                     uint16_t cursor) {
    set_field_w(image, actor, WB_ACTOR_SPRITE,
                bus_read_word(image, addr_add(table, sign_ext16(cursor))));
}

/* $1faa / $1fde — arms 2 and 3, which are one body with the cursor exchanged: sixteen words wrapped
 * by WB_ACTOR_ANIM32_MASK. Returns the WRAPPED cursor, because `move.w d0,<cursor>` is what sets the
 * Z the completion test below reads. */
static uint16_t transition_step_anim32(uint8_t *image, uint32_t actor, uint32_t cursor_at) {
    uint16_t cursor = be16(image + cursor_at);

    transition_publish_frame(image, actor, cursor_at + WB_WORD_BYTES, cursor);
    cursor = (uint16_t)((cursor + WB_ACTOR_ANIM_FRAME_BYTES) & WB_ACTOR_ANIM32_MASK);
    wr16(image + cursor_at, cursor);
    return cursor;
}

/* $1f66 — ARM 1, the transition proper, and the only animation here with TWO tables: `lea 48(a1),a1`
 * picks the second while WB_EFFECT_STATE_21E4 is nonzero, so the same cursor drives whichever of the
 * two the game is in. Its wrap is `cmp.w #$30,d0` — an EQUALITY, not a mask, so a cursor that never
 * lands on WB_PLAYER_TRANSITION_TABLE_BYTES walks straight out of the first table into the second. */
static void transition_play(uint8_t *image, uint32_t actor) {
    uint32_t table = WB_PLAYER_TRANSITION_CURSOR + WB_WORD_BYTES;
    uint16_t cursor = be16(image + WB_PLAYER_TRANSITION_CURSOR);

    if (be16(image + WB_EFFECT_STATE_21E4) != 0)
        table += WB_PLAYER_TRANSITION_TABLE_BYTES;

    transition_publish_frame(image, actor, table, cursor);
    cursor = (uint16_t)(cursor + WB_ACTOR_ANIM_FRAME_BYTES);
    if (cursor == WB_PLAYER_TRANSITION_TABLE_BYTES)
        cursor = 0;

    wr16(image + WB_PLAYER_TRANSITION_CURSOR, cursor);
    if (cursor != 0)
        return;
    wr16(image + WB_STAGE_ANIM_DONE_B10, WB_EVENT_DONE_SET);
}

/* $2096 — THE LADDER, and the one animation whose table is EIGHT BYTES OF DATA INSIDE THE BODY.
 * WB_ACTOR_FIELD_18 is a byte offset masked to WB_PLAYER_LADDER_SPRITE_MASK, and it advances only on
 * the frames WB_TILE_33_STEP says the climb actually moved — so a player holding still on a ladder
 * holds one frame. The cursor's own step is `addq.b #2 / andi.b #$7` IN MEMORY, two stores to one
 * byte, where the fetch above it is a masked COPY that leaves the field alone. */
static void transition_ladder_frame(uint8_t *image, uint32_t actor) {
    uint8_t cursor = (uint8_t)(field_b(image, actor, WB_ACTOR_FIELD_18)
                               & WB_PLAYER_LADDER_SPRITE_MASK);

    transition_publish_frame(image, actor, WB_PLAYER_LADDER_SPRITES, cursor);
    if (be16(image + WB_TILE_33_STEP) == 0)
        return;
    set_field_b(image, actor, WB_ACTOR_FIELD_18,
                (uint8_t)((field_b(image, actor, WB_ACTOR_FIELD_18)
                           + WB_ACTOR_ANIM_FRAME_BYTES) & WB_PLAYER_LADDER_SPRITE_MASK));
}

/* $20ca — THE SWING, the arm WB_ACTOR_FLAG_FIRED_BIT gates, and the only reader of that bit in the
 * image. Eight frames off one of two tables, the SFX fired on the frame the cursor is found at zero
 * (so once per swing rather than once per frame), and the bit lowered when the cursor comes back
 * round — which is what ends the swing. It runs only while WB_EFFECT_STATE_21E4 is nonzero: an
 * armed player in state 0 keeps the bit and shows an ordinary posture.
 *
 * d0 IS THE FRAME INDEX AND THE SFX ID, IN THAT ORDER, AND THE SECOND ONE SURVIVES. On the frame the
 * cursor is zero the original writes `move.w #$6,d0` for the effect id, calls the stub — which is
 * `movem.l d0-a6` either side of its `bsr`, so every register comes back — and then indexes the
 * frame table with THAT d0. So the swing's first published frame is table entry
 * WB_PLAYER_ATTACK_SFX, the cursor is stored as that plus one frame, and entries 0, 2 and 4 of both
 * tables are unreachable from a swing that starts at zero — which every swing does, because the
 * wrap that ends one leaves the cursor there. It is the stale-register-as-input class this project
 * has met before, and it is reproduced rather than tidied. */
static void transition_swing_frame(uint8_t *image, uint32_t actor) {
    uint16_t cursor = be16(image + WB_PLAYER_ATTACK_CURSOR);
    uint16_t index = cursor;

    if (cursor == 0) {
        snd_call_trigger_effect(image, WB_PLAYER_ATTACK_SFX, WB_SND_CHANNEL_A);
        index = WB_PLAYER_ATTACK_SFX;
    }

    transition_publish_frame(image, actor,
                             flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT)
                                 ? WB_PLAYER_ATTACK_TABLE_LEFT : WB_PLAYER_ATTACK_TABLE_RIGHT,
                             index);
    index = (uint16_t)((index + WB_ACTOR_ANIM_FRAME_BYTES) & WB_PLAYER_ATTACK_MASK);
    wr16(image + WB_PLAYER_ATTACK_CURSOR, index);
    if (index != 0)
        return;
    flag_clear(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FIRED_BIT);
}

/* $21a6 / $21ca — THE WALK CYCLE, whose cursor lives in the POSTURE RECORD rather than in a global,
 * one per facing. `addq.w #2,54(a6) / andi.w #$1f,54(a6)` steps it IN MEMORY below the fetch, so the
 * frame published is the cursor as it was. */
static void transition_walk_frame(uint8_t *image, uint32_t actor, uint32_t cursor_at) {
    uint16_t cursor = be16(image + cursor_at);

    transition_publish_frame(image, actor, cursor_at + WB_WORD_BYTES, cursor);
    wr16(image + cursor_at,
         (uint16_t)((be16(image + cursor_at) + WB_ACTOR_ANIM_FRAME_BYTES) & WB_ACTOR_ANIM32_MASK));
}

/* $2132 — THE POSTURE SELECTOR, four questions in order over one posture record, and each of the
 * four answers with the pair of fields WB_ACTOR_FLAG_SIDE_BIT then chooses between. MOVING or
 * LAUNCHED is asked as one question (`bne` on the first, `beq` past both on the second), so a record
 * carrying either shows the jump.
 *
 * THE FIELD ORDER FLIPS between the first question and the rest: idle is (right, left) where jump,
 * fall and walk are all (left, right) — see WB_PLAYER_POSTURE_IDLE_RIGHT. */
static void transition_posture(uint8_t *image, uint32_t actor, uint32_t posture) {
    int facing_left = flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
    uint32_t field;

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT)
        || flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_LAUNCHED_BIT))
        field = facing_left ? WB_PLAYER_POSTURE_JUMP_LEFT : WB_PLAYER_POSTURE_JUMP_RIGHT;
    else if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FALLING_BIT))
        field = facing_left ? WB_PLAYER_POSTURE_FALL_LEFT : WB_PLAYER_POSTURE_FALL_RIGHT;
    else if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVED_BIT)) {
        transition_walk_frame(image, actor,
                              posture + (facing_left ? WB_PLAYER_POSTURE_WALK_LEFT
                                                     : WB_PLAYER_POSTURE_WALK_RIGHT));
        return;
    } else
        field = facing_left ? WB_PLAYER_POSTURE_IDLE_LEFT : WB_PLAYER_POSTURE_IDLE_RIGHT;

    set_field_w(image, actor, WB_ACTOR_SPRITE, be16(image + posture + field));
}

/* $205e — the shared tail: pick the posture record WB_EFFECT_STATE_21E4 names, then the LADDER, the
 * SWING or the posture, in that order. */
static void transition_select_sprite(uint8_t *image, uint32_t actor) {
    uint16_t state = be16(image + WB_EFFECT_STATE_21E4);
    uint32_t posture = state == 0 ? WB_PLAYER_POSTURE_TABLE_0
                                  : (state == WB_PLAYER_POSTURE_STATE_ONE
                                         ? WB_PLAYER_POSTURE_TABLE_1 : WB_PLAYER_POSTURE_TABLE_2);

    if (be16(image + WB_TILE_33_MODE) != 0) {
        transition_ladder_frame(image, actor);
        return;
    }
    if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FIRED_BIT)
        && be16(image + WB_EFFECT_STATE_21E4) != 0) {
        transition_swing_frame(image, actor);
        return;
    }
    transition_posture(image, actor, posture);
}

/* $1ffc — the HURT arm, and the one place the record's own WB_ACTOR_FLAGS2_BIT_0 reaches this
 * routine. A hurt record that is STANDING falls through to the ordinary selector (through a
 * `bsr $205c` into a bare `rts`, i.e. a call that does nothing); one that is not shows a fixed pair
 * of sprites and ends the frame there. */
static void transition_hurt_or_posture(uint8_t *image, uint32_t actor) {
    int facing_left, state_one;

    /* TWO transfers reach the selector and they are one condition: $2002's `beq` on the hurt bit,
     * and $2014's `bra` below the `bsr $205c` — a call into a bare `rts`, which is why the two are
     * spelt as one arm here. */
    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0)
        || flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT)) {
        transition_select_sprite(image, actor);
        return;
    }

    facing_left = flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
    state_one = be16(image + WB_EFFECT_STATE_21E4) == WB_PLAYER_POSTURE_STATE_ONE;
    set_field_w(image, actor, WB_ACTOR_SPRITE,
                state_one ? (facing_left ? WB_PLAYER_HURT_SPRITE_LEFT
                                         : WB_PLAYER_HURT_SPRITE_RIGHT)
                          : (facing_left ? WB_PLAYER_HURT2_SPRITE_LEFT
                                         : WB_PLAYER_HURT2_SPRITE_RIGHT));
}

void player_stage_transition(uint8_t *image, uint32_t actor) {
    if (be16(image + WB_STAGE_ANIM_DONE_B10) != 0)
        return;

    if (be16(image + WB_STAGE_ANIM_REQUEST_B0E) != 0) {
        transition_play(image, actor);
        return;
    }
    if (be16(image + WB_EVENT_ANIM_DONE_B16) != 0) {
        /* The frame the sixteen-word cursor comes back to zero raises the gate's own handshake AND
         * blanks the sprite, which is the only arm here that publishes twice in one frame. */
        if (transition_step_anim32(image, actor, WB_PLAYER_EVENT_ANIM_CURSOR) != 0)
            return;
        wr16(image + WB_STAGE_ANIM_DONE_B18, WB_EVENT_DONE_SET);
        set_field_w(image, actor, WB_ACTOR_SPRITE, WB_ACTOR_SPRITE_HIDDEN);
        return;
    }
    if (be16(image + WB_STAGE_RESET_BLOCK) != 0) {
        transition_step_anim32(image, actor, WB_PLAYER_DEATH_ANIM_CURSOR);
        return;
    }
    transition_hurt_or_posture(image, actor);
}


/* --- $151a: what the player's own map cell does -------------------------------------------------
 *
 * One cell lookup and three bands; player.h's plate names them and wonderboy.h's `$151a` block
 * carries the constants. Everything below is reached from `player_run_map_cell` at the bottom.
 */

/* THE HURT ARM DOES NOT USE bus.h's `launch_at_inline_speed`, and that is the original's asymmetry
 * rather than an oversight: `bra.w $6ade` at $15e8 is a real transfer, so that arm calls
 * `actor_knock_back_and_launch`, whose tail writes the same four fields through src/actor.c's DIRECT
 * buffer access. Three arms here spell the four writes inline and the fourth branches into a shared
 * tail; ../STATUS.md registers what the differing bus routing leaves unpinned. */

/* The collision-map cell the record is standing in, and it is NOT src/map.c's `cell_pointer`: the
 * stride comes from WB_MAP_ROW_STRIDE rather than from the map's own header word, and the map is
 * WB_COLLISION_MAP_DEFAULT whatever WB_STATE_FLAG_A32 says (see wonderboy.h).
 *
 * `mulu.w` is UNSIGNED over the whole 32 bits and the `add.w` under it keeps only the low word, so a
 * row far enough down wraps the index instead of running off the map; the `lea` then SIGN-extends
 * what is left, which is what puts a wrapped index BELOW the map rather than 64 KB above it. */
static uint32_t player_collision_cell(const uint8_t *image, uint32_t actor) {
    uint16_t column = (uint16_t)(field_w(image, actor, WB_ACTOR_X) >> WB_MAP_CELL_SHIFT);
    uint16_t row = (uint16_t)((int16_t)(field_w(image, actor, WB_ACTOR_Y) - WB_PLAYER_CELL_Y_BIAS)
                              >> WB_MAP_CELL_SHIFT);
    uint32_t product = (uint32_t)be16(image + WB_MAP_ROW_STRIDE) * row;
    uint16_t index = (uint16_t)(product + column);

    return addr_add(WB_COLLISION_MAP_DEFAULT + WB_COLLISION_MAP_CELLS, sign_ext16(index));
}


/* --- the six special tiles, $23..$7f ------------------------------------------------------------ */

/* $1576 — WB_MAP_TILE_34, and only under a SUPPORTED record. A full high pool costs the arm nothing:
 * the launch has already happened and the spawn simply does not. */
static void player_tile_34(uint8_t *image, uint32_t actor) {
    uint32_t spawned;

    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT))
        return;

    launch_at_inline_speed(image, actor, WB_PLAYER_TILE_34_SPEED);

    spawned = actor_alloc_slot_high(image);
    if (spawned == WB_ACTOR_ALLOC_NONE)
        return;

    /* `move.l (a0),(a1)` — the x and the y as ONE operand, which is why this is the longword pair
     * and not two word copies: the shim drops a longword straddling the image's top entirely. */
    bus_write_long(image, spawned, bus_read_long(image, actor));
    set_field_w(image, spawned, WB_ACTOR_TYPE, WB_PLAYER_TILE_34_SPAWN_TYPE);
}

/* $15ba — WB_MAP_TILE_35 and WB_MAP_TILE_36 are ONE arm. A record already carrying
 * WB_ACTOR_FLAG_FLICKER_BIT pays nothing and is not knocked back either. */
static void player_tile_hurt(uint8_t *image, uint32_t actor) {
    uint16_t left;

    if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT))
        return;

    flag_set(image, actor, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_BIT_0);
    flag_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT);
    set_field_b(image, actor, WB_ACTOR_FLICKER_COUNTDOWN, WB_ACTOR_DAMAGE_FLICKER_FRAMES);

    /* `subq.w #4,$b6fa.l / bpl / clr.w`: the branch reads the RESULT, so a meter already negative
     * that the subtraction carries back into the positive half is STORED rather than floored — the
     * same read-modify-write `actor_charge_damage` documents, on a fixed cost. */
    left = (uint16_t)(be16(image + WB_HUD_METER_VALUE) - WB_PLAYER_TILE_HURT_COST);
    wr16(image + WB_HUD_METER_VALUE, (int16_t)left < 0 ? 0 : left);

    actor_knock_back_and_launch(image, actor);
}

/* $1554 — the ladder of `cmpi.b`s the second band falls into. Every arm ends the routine: the codes
 * are distinct, so an arm that falls through only meets tests it cannot pass. */
static uint32_t player_run_special_tile(uint8_t *image, uint32_t actor, uint8_t code) {
    switch (code) {
    case WB_MAP_TILE_33:
        /* `st $1514.w` — the flag's HIGH byte alone, where `actor_fall_and_settle` raises the whole
         * word with a `move.w #$ffff`. */
        image[WB_TILE_33_FLAG] = WB_TILE_33_FLAG_RAISED_BYTE;
        break;
    case WB_MAP_TILE_34:
        player_tile_34(image, actor);
        break;
    case WB_MAP_TILE_35:
    case WB_MAP_TILE_36:
        player_tile_hurt(image, actor);
        break;
    case WB_MAP_TILE_37:
        if (flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT))
            set_field_w(image, actor, WB_ACTOR_X,
                        (uint16_t)(field_w(image, actor, WB_ACTOR_X) - WB_PLAYER_TILE_37_X_STEP));
        break;
    case WB_MAP_TILE_38:
        /* TWO stores to one word — `subq.w #1` and then `andi.w #$fffe` over what it left. The
         * ledger records final values, so folding them would be invisible; spelt as the pair. */
        wr16(image + WB_PANEL_FRAME_DELAY, (uint16_t)(be16(image + WB_PANEL_FRAME_DELAY) - 1));
        wr16(image + WB_PANEL_FRAME_DELAY,
             (uint16_t)(be16(image + WB_PANEL_FRAME_DELAY) & WB_PANEL_FRAME_DELAY_EVEN));
        break;
    case WB_MAP_TILE_39:
        return WB_PLAYER_COLLIDE_UNWIND;
    default:
        break;
    }
    return WB_PLAYER_COLLIDE_RETURN;
}


/* --- the scene triggers, cells 3..$22 ----------------------------------------------------------- */

/* `move.l $10420.l,$10424.l` — the copy SIX of the eight arms make, and a whole-image sweep for
 * that encoding finds exactly those six, all of them in this routine. Kinds 4 and 7 are the two
 * that do not. */
static void scene_trigger_republish(uint8_t *image) {
    wr32(image + WB_RECORD_PTR_10424, be32(image + WB_RECORD_PTR_10420));
}


/* `tst.w (a2) / bmi` on WB_SCENE_TRIGGER_SPAWN_SLOT's x: the four spawning arms refuse a slot whose
 * x is not NEGATIVE, which WB_ACTOR_FREE_MARKER is and a map position is not. */
static int scene_trigger_slot_is_free(const uint8_t *image) {
    return field_w(image, WB_SCENE_TRIGGER_SPAWN_SLOT, WB_ACTOR_X) < 0;
}

/* The two instructions all four SPAWNING arms open with, and the answer they all branch on: the
 * descriptor pointer republished, and then the scene's own actor slot refused unless it is free.
 *
 * THIS IS THE GUARD AND NOT THE ARM. The four arms stay four functions because their BODIES differ
 * — different effects, different sprites, and kind 6's head is even spelt inline where the other
 * three share `_trigger_slot_pieces`' three instructions — but every one of them asks these two
 * questions first and in this order, so asking them in one place is a de-duplication and not a
 * merge. Returns whether the arm may continue. */
static int scene_trigger_spawn_gate(uint8_t *image) {
    scene_trigger_republish(image);
    return scene_trigger_slot_is_free(image);
}

/* One of the four `move.w (a1)+` every spawning arm makes: a word out of the descriptor, which is a
 * computed address, into the fixed slot. */
static void scene_trigger_copy_word(uint8_t *image, uint32_t descriptor, uint32_t from,
                                    uint32_t to) {
    set_field_w(image, WB_SCENE_TRIGGER_SPAWN_SLOT, to,
                bus_read_word(image, addr_add(descriptor, from)));
}

/* ...and all four, in the order the post-increments take them — which is what makes the descriptor's
 * field layout the same for every spawning kind. */
static void scene_trigger_copy_spawn_fields(uint8_t *image, uint32_t descriptor) {
    scene_trigger_copy_word(image, descriptor, WB_SCENE_TRIGGER_X, WB_ACTOR_X);
    scene_trigger_copy_word(image, descriptor, WB_SCENE_TRIGGER_SPAWN_Y, WB_ACTOR_Y);
    scene_trigger_copy_word(image, descriptor, WB_SCENE_TRIGGER_SPAWN_TYPE, WB_ACTOR_TYPE);
    scene_trigger_copy_word(image, descriptor, WB_SCENE_TRIGGER_SPAWN_FIELD, WB_ACTOR_FIELD_12);
}

/* `subq.w #1,(a1)+ / bne / clr.b (a6)` — one visit spent, and the visit that empties the counter
 * CLEARS THE MAP CELL, so a trigger fires a fixed number of times and then is not there any more. */
static void scene_trigger_spend_visit(uint8_t *image, uint32_t descriptor, uint32_t cell) {
    uint32_t at = addr_add(descriptor, WB_SCENE_TRIGGER_VISITS);
    uint16_t left = (uint16_t)(bus_read_word(image, at) - 1);

    bus_write_word(image, at, left);
    if (left == 0)
        bus_write_byte(image, cell, 0);
}

/* $1684 — kind 1, the only arm that copies the FOLLOWED record's side bit, and it copies it
 * INVERTED: `btst #3,8(a5) / bne` jumps to the `bclr`, so the spawn faces the way the player is not
 * facing. (Kind 7 reads that record too — its supported bit and its x — so "the only arm that reads
 * it" would be two arms.) */
static void scene_trigger_spawn_1(uint8_t *image, uint32_t descriptor, uint32_t cell) {
    uint32_t slot = WB_SCENE_TRIGGER_SPAWN_SLOT;

    if (!scene_trigger_spawn_gate(image))
        return;

    snd_call_trigger_effect(image, WB_SCENE_TRIGGER_SFX_1, WB_SND_CHANNEL_A);
    scene_trigger_copy_spawn_fields(image, descriptor);

    if (flag_is_set(image, WB_ACTOR_FOLLOWED_DEFAULT, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT))
        flag_clear(image, slot, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
    else
        flag_set(image, slot, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);

    flag_clear(image, slot, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT);
    launch_at_inline_speed(image, slot, WB_SCENE_TRIGGER_SPAWN_SPEED);
    set_field_b(image, slot, WB_ACTOR_FIELD_10, WB_SCENE_TRIGGER_SPAWN_1_FIELD_10);
    set_field_w(image, slot, WB_ACTOR_SPRITE, WB_SCENE_TRIGGER_SPRITE_1);
    scene_trigger_spend_visit(image, descriptor, cell);
}

/* $170e — kind 2. Kind 1 without the side bit and without WB_ACTOR_FIELD_10, and the flicker is
 * lowered AFTER the sprite rather than before the launch — one bit, one final value. */
static void scene_trigger_spawn_2(uint8_t *image, uint32_t descriptor, uint32_t cell) {
    uint32_t slot = WB_SCENE_TRIGGER_SPAWN_SLOT;

    if (!scene_trigger_spawn_gate(image))
        return;

    snd_call_trigger_effect(image, WB_SCENE_TRIGGER_SFX_2, WB_SND_CHANNEL_A);
    scene_trigger_copy_spawn_fields(image, descriptor);
    launch_at_inline_speed(image, slot, WB_SCENE_TRIGGER_SPAWN_SPEED);
    set_field_w(image, slot, WB_ACTOR_SPRITE, WB_SCENE_TRIGGER_SPRITE_2);
    flag_clear(image, slot, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT);
    scene_trigger_spend_visit(image, descriptor, cell);
}

/* The four writes kinds 5 and 6 share below their heads. The heads are NOT shared, because the two
 * originals do not share them: kind 5's is `_trigger_slot_pieces`' three instructions with an SFX
 * and kind 6's is the same republish and slot test spelt inline with none, which is why the entry
 * pin emits two different byte sequences and why these are two functions rather than one with a
 * flag. */
static void scene_trigger_finish_quiet_spawn(uint8_t *image, uint32_t descriptor, uint32_t cell,
                                             uint16_t sprite) {
    scene_trigger_copy_spawn_fields(image, descriptor);
    set_field_w(image, WB_SCENE_TRIGGER_SPAWN_SLOT, WB_ACTOR_SPRITE, sprite);
    flag_clear(image, WB_SCENE_TRIGGER_SPAWN_SLOT, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FLICKER_BIT);
    scene_trigger_spend_visit(image, descriptor, cell);
}

/* $17a4 — kind 5. Kind 2's arrival effect without its launch, plus the one write in this routine
 * that crosses back from the scene's record to the PLAYER's. */
static void scene_trigger_spawn_5(uint8_t *image, uint32_t actor, uint32_t descriptor,
                                  uint32_t cell) {
    if (!scene_trigger_spawn_gate(image))
        return;

    snd_call_trigger_effect(image, WB_SCENE_TRIGGER_SFX_2, WB_SND_CHANNEL_A);
    /* `clr.b 30(a0)` — on the record the CALLER handed in, not on the one being spawned. */
    set_field_b(image, actor, WB_ACTOR_FIELD_30, 0);
    scene_trigger_finish_quiet_spawn(image, descriptor, cell, WB_SCENE_TRIGGER_SPRITE_5);
}

/* $17f4 — kind 6, the quietest of the eight: four words, a sprite, a flicker bit and a visit. It
 * plays no effect, touches the player's record nowhere, and its head is inline rather than the
 * three-instruction one the other three spawning arms share. */
static void scene_trigger_spawn_6(uint8_t *image, uint32_t descriptor, uint32_t cell) {
    if (!scene_trigger_spawn_gate(image))
        return;

    scene_trigger_finish_quiet_spawn(image, descriptor, cell, WB_SCENE_TRIGGER_SPRITE_6);
}

/* $1772 — kind 3, the message. WB_TEXT_REQUEST is PRIMED with WB_TEXT_REQUEST_PRIMED before the id
 * is read, so a descriptor holding zero leaves that $ff standing and posts no lifetime; and the id
 * is tested as a WORD but written as its LOW BYTE, so $100 posts message 0. Either way the cell is
 * cleared, which makes this the one arm that spends no visit and still fires once. */
static void scene_trigger_message(uint8_t *image, uint32_t descriptor, uint32_t cell) {
    uint16_t id;

    scene_trigger_republish(image);
    image[WB_TEXT_REQUEST] = WB_TEXT_REQUEST_PRIMED;

    id = bus_read_word(image, addr_add(descriptor, WB_SCENE_TRIGGER_MESSAGE));
    if (id != 0)
        text_post_message(image, (uint8_t)id);          /* the id's LOW byte, and the default life */
    bus_write_byte(image, cell, 0);
}

/* $1964 — kind 4, the boss defeat. The cell address is published to WB_SCENE_MARKER_CELL_PTR FIRST,
 * before either gate, so the scene tier is handed it even on the frames nothing else happens. */
static void scene_trigger_boss_defeat(uint8_t *image, uint32_t actor, uint32_t cell) {
    wr32(image + WB_SCENE_MARKER_CELL_PTR, cell);

    if (!flag_is_set(image, actor, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT))
        return;
    if (image[WB_KEY_LAST_SCANCODE] != WB_SCENE_TRIGGER_BOSS_KEY)
        return;

    snd_stop(image);
    snd_call_trigger_effect(image, WB_SCENE_TRIGGER_BOSS_SFX, WB_SND_CHANNEL_A);
    wr16(image + WB_STATE_FLAG_A34, WB_SCENE_TRIGGER_FLAG_SET);
    wr16(image + WB_PANEL_FRAME_HOLD, WB_SCENE_TRIGGER_FLAG_SET);
    wr16(image + WB_STAGE_ANIM_REQUEST_B0E, WB_SCENE_TRIGGER_FLAG_SET);
}

/* $1830's two gates, which are a LATTICE rather than a chain: `cmpi.b #$1,$bbc4.l` picks which pair
 * of questions is asked, and the two orders meet at the same two answers. An ARMED slot admits a
 * descriptor whose sub-kind is not WB_SCENE_TRIGGER_ALIGN_SECOND outright; everything else needs the
 * flute to have been played AND the sub-kind to BE that value. */
static int scene_trigger_door_is_open(const uint8_t *image, int second_sub_kind) {
    int slot_armed = image[WB_HUD_SLOT_BBC4] == WB_HUD_SLOT_BBC4_ARMED;
    int flute_played = be16(image + WB_SCENE_FLUTE_PLAYED) == WB_SCENE_FLUTE_PLAYED_SET;

    return (slot_armed && !second_sub_kind) || (flute_played && second_sub_kind);
}

/* $1862 — the alignment window. `subq.w #4` / `addq.w #8` / `subq.w #4` all WRAP in sixteen bits and
 * both compares are signed, so the window is the descriptor's x plus or minus
 * WB_SCENE_TRIGGER_ALIGN_REACH, INCLUSIVE at both ends. The x compared is the FOLLOWED record's; the
 * x written is the CALLER's a0, and nothing here proves the two are one record.
 *
 * IT RE-READS THE DESCRIPTOR rather than taking its caller's, because the original does: `movea.l
 * $10420.l,a3` at $1872, where every other field of this arm comes off the a1 the kind word's
 * post-increment left. The two are the same pointer on every path that reaches here — the arm's own
 * head wrote it — so the re-read is reproduced rather than relied on. */
static int scene_trigger_align_player(uint8_t *image, uint32_t actor) {
    uint32_t descriptor = be32(image + WB_RECORD_PTR_10420);
    int16_t followed_x = field_w(image, WB_ACTOR_FOLLOWED_DEFAULT, WB_ACTOR_X);
    uint16_t probe = (uint16_t)(bus_read_word(image, addr_add(descriptor, WB_SCENE_TRIGGER_X))
                                - WB_SCENE_TRIGGER_ALIGN_REACH);

    if ((int16_t)probe > followed_x)
        return 0;
    probe = (uint16_t)(probe + 2 * WB_SCENE_TRIGGER_ALIGN_REACH);
    if ((int16_t)probe < followed_x)
        return 0;

    set_field_w(image, actor, WB_ACTOR_X, (uint16_t)(probe - WB_SCENE_TRIGGER_ALIGN_REACH));
    return 1;
}

/* `cmpi.w #$2,6(a1)` — the descriptor's sub-kind, asked at $184a, at $1856 and AGAIN at $18ce. It is
 * a function and not a local because the third ask is BELOW the `move.w d0,(a0)` snap, and a0 is the
 * CALLER's record: on a record that aliases this word the store changes the answer. Caching it is
 * the read-after-store defect batch 32 found at `snd_channel_step`'s $18036 — and test_player.py
 * drives the alias, so this is pinned rather than argued. */
static int scene_trigger_sub_kind_is_second(const uint8_t *image, uint32_t descriptor) {
    return bus_read_word(image, addr_add(descriptor, WB_SCENE_TRIGGER_ALIGN_SUBKIND))
           == WB_SCENE_TRIGGER_ALIGN_SECOND;
}

/* $1830 — kind 7, the hidden door: the flute's other half. */
static void scene_trigger_align(uint8_t *image, uint32_t actor, uint32_t descriptor) {
    uint16_t sequence;
    int second_sub_kind = scene_trigger_sub_kind_is_second(image, descriptor);

    if (!scene_trigger_door_is_open(image, second_sub_kind))
        return;
    if (!flag_is_set(image, WB_ACTOR_FOLLOWED_DEFAULT, WB_ACTOR_FLAGS,
                     WB_ACTOR_FLAG_SUPPORTED_BIT))
        return;
    if (!scene_trigger_align_player(image, actor))
        return;

    wr16(image + WB_SCENE_FLUTE_PLAYED, 0);
    /* `move.w #$ff,$bbc4.l` — a WORD write over the slot the `cmpi.b` above read as a BYTE, so the
     * high byte it clears is the one that test looks at. */
    wr16(image + WB_HUD_SLOT_BBC4, WB_HUD_SLOT_BBC4_SPENT);
    wr16(image + WB_SCROLL_FOLLOW_FROZEN, WB_SCENE_TRIGGER_FLAG_SET);
    wr16(image + WB_PANEL_FRAME_HOLD, WB_SCENE_TRIGGER_FLAG_SET);
    wr16(image + WB_SCENE_ALIGN_REQUEST_B14, WB_SCENE_TRIGGER_FLAG_SET);

    /* The door only MOVES the game on from two points of the level sequence; from anywhere else it
     * has already frozen the scroll and raised the gate's flag and that is all it does. */
    sequence = be16(image + WB_LEVEL_SEQ_INDEX);
    if (sequence != WB_LEVEL_SEQ_DOOR_A && sequence != WB_LEVEL_SEQ_DOOR_B)
        return;

    /* RE-READ, and not the `second_sub_kind` above: `scene_trigger_align_player` has stored the
     * snapped x through the caller's a0 since that answer was taken. */
    if (scene_trigger_sub_kind_is_second(image, descriptor))
        wr16(image + WB_STAGE_ADVANCE_REQUEST, WB_STAGE_ADVANCE_REQUEST_SET);
    else
        wr16(image + WB_LEVEL_SEQ_INDEX, (uint16_t)(sequence + WB_LEVEL_SEQ_DOOR_STEP));
}

/* $18ea — kind 8: the flute, or the view. The one arm of the eight that reads the player's own
 * position, and the one that reaches the busy-wait player.h prices. */
static uint32_t scene_trigger_tune(uint8_t *image, uint32_t actor, uint32_t cell) {
    if (field_w(image, actor, WB_ACTOR_Y) >= (int16_t)WB_SCENE_TRIGGER_TUNE_MAX_Y)
        return WB_PLAYER_COLLIDE_RETURN;

    scene_trigger_republish(image);
    bus_write_byte(image, cell, 0);

    if (image[WB_HUD_SLOT_BBC8] != WB_HUD_SLOT_BBC8_FLUTE) {
        text_post_message(image, WB_TEXT_MESSAGE_NICE_VIEW);
        return WB_PLAYER_COLLIDE_RETURN;
    }

    text_post_message(image, WB_TEXT_MESSAGE_PLAYED_FLUTE);
    snd_play_song(image, WB_SCENE_TRIGGER_FLUTE_SONG);

    /* `tst.b 378(a5) / bne.s $1932`, and THE CALL ABOVE HAS JUST RAISED THAT BYTE — see
     * WB_PLAYER_COLLIDE_SOUND_WAIT in player.h. There is no seed that enters the spin with it clear
     * and no interrupt under either core to clear it, so the wait is where this arm ends. */
    return WB_PLAYER_COLLIDE_SOUND_WAIT;
}

/* $162c — the cell names a descriptor. The pointer is published BEFORE the kind word is read and on
 * every path, which is what hands the scene driver a descriptor for a kind this ladder ignores. */
static uint32_t player_run_scene_trigger(uint8_t *image, uint32_t actor, uint32_t cell,
                                         uint8_t code) {
    uint16_t offset = (uint16_t)((code - WB_SCENE_TRIGGER_CODE_FIRST)
                                 << WB_SCENE_TRIGGER_RECORD_SHIFT);
    uint32_t descriptor = addr_add(WB_SCENE_TRIGGER_TABLE, sign_ext16(offset));

    wr32(image + WB_RECORD_PTR_10420, descriptor);
    switch (bus_read_word(image, addr_add(descriptor, WB_SCENE_TRIGGER_KIND))) {
    case WB_SCENE_TRIGGER_KIND_SPAWN_1:
        scene_trigger_spawn_1(image, descriptor, cell);
        break;
    case WB_SCENE_TRIGGER_KIND_SPAWN_2:
        scene_trigger_spawn_2(image, descriptor, cell);
        break;
    case WB_SCENE_TRIGGER_KIND_MESSAGE:
        scene_trigger_message(image, descriptor, cell);
        break;
    case WB_SCENE_TRIGGER_KIND_BOSS_DEFEAT:
        scene_trigger_boss_defeat(image, actor, cell);
        break;
    case WB_SCENE_TRIGGER_KIND_SPAWN_5:
        scene_trigger_spawn_5(image, actor, descriptor, cell);
        break;
    case WB_SCENE_TRIGGER_KIND_SPAWN_6:
        scene_trigger_spawn_6(image, descriptor, cell);
        break;
    case WB_SCENE_TRIGGER_KIND_ALIGN:
        scene_trigger_align(image, actor, descriptor);
        break;
    case WB_SCENE_TRIGGER_KIND_TUNE:
        return scene_trigger_tune(image, actor, cell);
    default:
        break;
    }
    return WB_PLAYER_COLLIDE_RETURN;
}

uint32_t player_run_map_cell(uint8_t *image, uint32_t actor) {
    uint32_t cell = player_collision_cell(image, actor);
    uint8_t code = bus_read_byte(image, cell);

    /* `cmpi.b #$3,(a6) / blt` — a SIGNED byte test, so this takes every code from $80 up as well as
     * 0..2, and that is why the band below reaches only 3..$22. */
    if ((int8_t)code < (int8_t)WB_SCENE_TRIGGER_CODE_FIRST) {
        image[WB_TILE_33_FLAG] = 0;                     /* `clr.b`, the high byte alone */
        return WB_PLAYER_COLLIDE_RETURN;
    }
    if ((int8_t)code <= (int8_t)WB_SCENE_TRIGGER_CODE_LAST)
        return player_run_scene_trigger(image, actor, cell, code);
    return player_run_special_tile(image, actor, code);
}
