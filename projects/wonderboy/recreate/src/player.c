/* player.c — the player's own frame: the five routines behaviour slot 1 calls that reach nothing
 * this port lacks, and the spawn helper beside them. See player.h for what each one is and
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

#include "bus.h"
#include "input.h"
#include "machine.h"
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
