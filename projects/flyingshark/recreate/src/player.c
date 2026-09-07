/* player.c — the player's plane: input, the scripted take-off and fly-off, the bank, the death
 * sequence, firing, and the two collision passes that kill it.
 *
 * THREE SEAMS, all of them into routines that never come back, and each diffed at a checkpoint PC
 * rather than at an `rts` (test_player.py names them):
 *
 *   * `player_death_sequence_step`'s "lives left" arm ends `addq.l #4,a7 / bra.w
 *     restart_level_at_checkpoint` — it UNWINDS its caller's return address and re-enters the frame
 *     loop. Only the head of that routine is reconstructed here, so the arm stops at its entry;
 *   * the same routine's "no lives, banner expired" arm and `read_player_input`'s ABORT key both
 *     end in `game_over_hiscore_check`, which is the hud slice's and is CALLED rather than stopped
 *     at — it is verified, so the two are diffed all the way to its own re-entry into `main`;
 *   * `level_progress_check`'s level-advance arm unwinds the same way into the frame loop.
 *
 * WHAT THE PLANE READS is filled by an interrupt, not by anything here: `read_player_input`'s pause
 * key spins on a byte only the ACIA handler writes, so that wait goes through `sched_poll8` and the
 * harness compares the candidate's polls against the oracle's scheduled arrivals. A plain read
 * would never leave the loop off target and would compare nothing on it.
 */
#include "machine.h"
#include "os.h"
#include "sched.h"
#include "common.h"  /* SCC_TRUE, the one spelling of the `Scc` byte */
#include "player.h"

/* The five weapon patterns, as `weapon_fire_tbl` holds them — the dispatch below turns one of these
 * addresses back into a call, the way `src/hud.c`'s cheat dispatch does. */
#define FN_FIRE_PATTERN_LEVEL0 0x13ee0u
#define FN_FIRE_PATTERN_LEVEL1 0x13f20u
#define FN_FIRE_PATTERN_LEVEL2 0x13f72u
#define FN_FIRE_PATTERN_LEVEL3 0x13fdau
#define FN_FIRE_PATTERN_LEVEL4 0x1404cu

/* One `btst #n,<byte>`, which is how every one of the input tests below is spelt. */
static int bit_held(uint8_t byte, unsigned bit) { return (byte >> bit) & 1u; }

/* The PC of the pause key's `tst.b joy1_state` @ 0x14394, which is the read `sched_poll8` counts. */
#define PAUSE_WAIT_PC 0x14394u

/* Bits of `joy1_state`. Bit 7 is `include/hud.h`'s JOY_FIRE_BIT, read from there. */
#define JOY_UP_BIT    0u
#define JOY_DOWN_BIT  1u
#define JOY_LEFT_BIT  2u
#define JOY_RIGHT_BIT 3u
/* ...and of `key_bits`, which `acia_ikbd_isr` maintains from the eight watched scancodes. */
#define KEY_PAUSE_BIT 1u   /* 'P' */
#define KEY_ABORT_BIT 2u   /* F10 */
#define KEY_BOMB_BIT  5u   /* space */

/* One word out of `A_const_words_0123`, the table of 0..9 this program reads its small immediates
 * out of instead of spelling them (`move.w $176ae,$17712` is "lives = 1"). The index IS the value,
 * so the call reads as the constant it stands for while the read stays the original's. */
static uint16_t const_word(const uint8_t *image, unsigned value) {
    return be16(image + A_const_words_0123 + value * CONST_WORD_BYTES);
}

/* ================================================================================================
 * The take-off and fly-in scripts
 * ============================================================================================= */

/* The body both `*_reset`s are: five words copied over the live script, and its cursor rewound. */
static void script_reset(uint8_t *image, uint32_t template, uint32_t script, uint32_t cursor) {
    for (unsigned word = 0; word < SCRIPT_TEMPLATE_WORDS; word++)
        wr16(image + script + 2u * word, be16(image + template + 2u * word));
    wr16(image + cursor, 0);
}

/* takeoff_script_reset @ 0x139e4. */
void takeoff_script_reset(uint8_t *image) {
    script_reset(image, A_takeoff_start_pos, A_takeoff_script, A_takeoff_script_cursor);
}

/* landing_script_reset @ 0x13a02. */
void landing_script_reset(uint8_t *image) {
    script_reset(image, A_landing_start_pos, A_landing_script, A_landing_script_cursor);
}

/* Advance one of the two scripts by a frame and stamp its frame id on the plane.
 *
 * Returns the live record, or 0 once the script has run out. The countdown word is decremented IN
 * PLACE — the script is a copy for exactly that reason — and a record whose countdown goes negative
 * is retired by stepping the cursor, so a record with a countdown of 0 lasts ONE frame.
 */
static uint32_t script_step(uint8_t *image, uint32_t player, uint32_t script, uint32_t cursor) {
    for (;;) {
        uint32_t record = script + be16(image + cursor);

        if ((int16_t)be16(image + record) < 0)
            return 0;
        wr16(image + record, be16(image + record) - 1u);
        if ((int16_t)be16(image + record) >= 0) {
            image[player + PLAYER_FRAME] = image[record + SCRIPT_STEP_FRAME];
            return record;
        }
        wr16(image + cursor, be16(image + cursor) + SCRIPT_STEP_BYTES);
    }
}

/* The take-off arm of `player_script_step` @ 0x13ab2: climb away from the deck, walking the shadow
 * out from under the plane one step every TAKEOFF_SHADOW_PERIOD frames. */
static void player_takeoff_step(uint8_t *image, uint32_t player) {
    image[A_player_input_locked] = SCC_TRUE;
    wr16(image + A_level_complete, 0);
    image[player + PLAYER_SHADOW_FRAME] = SHADOW_FRAME_AIRBORNE;

    if (script_step(image, player, A_takeoff_script, A_takeoff_script_cursor) != 0) {
        wr16(image + A_takeoff_shadow_timer, be16(image + A_takeoff_shadow_timer) - 1u);
        if ((int16_t)be16(image + A_takeoff_shadow_timer) >= 0)
            return;
        wr16(image + A_shadow_offset, be16(image + A_shadow_offset) + 1u);
        wr16(image + A_takeoff_shadow_timer, TAKEOFF_SHADOW_PERIOD);
        return;
    }
    wr16(image + A_player_input_locked, 0);
    image[player + PLAYER_MODE] = PLAYER_MODE_JOYSTICK;
    image[player + PLAYER_SHADOW_FRAME] = SHADOW_FRAME_ON_DECK;
    wr16(image + A_takeoff_script_cursor, 0);
    wr16(image + A_shadow_offset, SHADOW_OFFSET_AIRBORNE);
}

/* The landing arm @ 0x13b26: settle back on to the deck, and cash one spare bomb for 3000 points
 * every BOMB_CASH_PERIOD frames on the way down. */
static void player_landing_step(uint8_t *image, uint32_t player) {
    image[A_player_input_locked] = SCC_TRUE;

    if (script_step(image, player, A_landing_script, A_landing_script_cursor) == 0) {
        wr16(image + A_shadow_offset, SHADOW_OFFSET_LANDED);
        image[A_level_complete] = SCC_TRUE;
        return;
    }
    wr16(image + A_landing_shadow_timer, be16(image + A_landing_shadow_timer) - 1u);
    if ((int16_t)be16(image + A_landing_shadow_timer) < 0) {
        wr16(image + A_shadow_offset, be16(image + A_shadow_offset) - 1u);
        wr16(image + A_landing_shadow_timer, LANDING_SHADOW_PERIOD);
    }
    wr16(image + A_landing_bomb_cash_timer, be16(image + A_landing_bomb_cash_timer) - 1u);
    if ((int16_t)be16(image + A_landing_bomb_cash_timer) >= 0)
        return;
    if ((int16_t)be16(image + A_bombs) < (int16_t)BOMBS_MIN_TO_DROP)
        return;
    wr16(image + A_bombs, be16(image + A_bombs) - 1u);
    /* X is the `subi.w #$1,$17710` above's borrow, and there is none: the `blt` two lines up has
     * already refused a bombs count below 1, so the subtraction never wraps. */
    score_add_award(image, SCORE_AWARD_3000, EXTEND_CLEAR);
    sfx_play_2(image);
    wr16(image + A_landing_bomb_cash_timer, BOMB_CASH_PERIOD);
}

/* The fly-off arm @ 0x13a42: after the level's end, steer the plane to the landing point and hold
 * it there for FLYOFF_HOVER_FRAMES before handing over to the landing script.
 *
 * The x leg and the y leg are two independent one-step-per-frame drifts through the ordinary move
 * routines, so the plane arrives on a diagonal; `player_script_fire_enable` is the "x has arrived"
 * latch that the y leg's centre test consults.
 */
static void player_flyoff_step(uint8_t *image, uint32_t player) {
    image[A_player_input_locked] = SCC_TRUE;
    image[A_player_turning] = SCC_TRUE;
    wr16(image + A_player_script_timer, be16(image + A_player_script_timer) + 1u);

    if ((int16_t)be16(image + player + PLAYER_X) < (int16_t)FLYOFF_TARGET_X) {
        player_move_right(image, player);
        wr16(image + A_player_script_fire_enable, 0);
    } else if ((int16_t)be16(image + player + PLAYER_X) > (int16_t)FLYOFF_TARGET_X) {
        player_move_left(image, player);
        wr16(image + A_player_script_fire_enable, 0);
    } else {
        image[A_player_script_fire_enable] = SCC_TRUE;
    }

    if ((int16_t)be16(image + player + PLAYER_Y) < (int16_t)FLYOFF_TARGET_Y) {
        player_move_down(image, player);
        return;
    }
    if ((int16_t)be16(image + player + PLAYER_Y) > (int16_t)FLYOFF_TARGET_Y) {
        player_move_up(image, player);
        return;
    }
    if (be16(image + A_player_script_fire_enable) == 0)
        return;
    if ((int16_t)be16(image + A_player_script_timer) < (int16_t)FLYOFF_HOVER_FRAMES)
        return;
    image[player + PLAYER_MODE] = PLAYER_MODE_LANDING;
    wr16(image + A_player_script_timer, 0);
}

/* player_script_step @ 0x13a20 — the frame loop's third call: whichever script owns the plane. */
void player_script_step(uint8_t *image) {
    uint8_t mode = image[A_player + PLAYER_MODE];

    if ((int8_t)mode < 0)
        player_takeoff_step(image, A_player);
    else if (mode == PLAYER_MODE_FLYOFF)
        player_flyoff_step(image, A_player);
    else if (mode == PLAYER_MODE_LANDING)
        player_landing_step(image, A_player);
}

/* ================================================================================================
 * The bank, and the four move routines the input and the scripts share
 * ============================================================================================= */

/* player_bank_recentre @ 0x13baa — one step back toward centre on any frame the plane is not
 * turning. `player_turning` is set by the two turn routines and cleared once a frame by
 * `read_player_input`, so a released stick lets the plane level out. */
void player_bank_recentre(uint8_t *image) {
    if (be16(image + A_player_turning) != 0)
        return;
    if ((int16_t)be16(image + A_player_bank) < (int16_t)PLAYER_BANK_CENTRE)
        wr16(image + A_player_bank, be16(image + A_player_bank) + 1u);
    else if ((int16_t)be16(image + A_player_bank) > (int16_t)PLAYER_BANK_CENTRE)
        wr16(image + A_player_bank, be16(image + A_player_bank) - 1u);
}

/* player_frame_from_bank @ 0x13d12 — the plane's sprite id is its bank index into a byte table. */
void player_frame_from_bank(uint8_t *image, uint32_t player) {
    image[player + PLAYER_FRAME] = image[A_player_bank_frames + be16(image + A_player_bank)];
}

/* player_move_up @ 0x13da0. The test is `cmpi.w #$c,2(a0) / blt`, so a plane already ABOVE the
 * limit simply does not move — the limit is a gate, not a clamp, and y is never snapped to it. */
void player_move_up(uint8_t *image, uint32_t player) {
    if ((int16_t)be16(image + player + PLAYER_Y) < (int16_t)PLAYER_Y_MIN)
        return;
    wr16(image + player + PLAYER_Y, be16(image + player + PLAYER_Y) - PLAYER_STEP_PIXELS);
}

/* player_move_down @ 0x13db0. */
void player_move_down(uint8_t *image, uint32_t player) {
    if ((int16_t)be16(image + player + PLAYER_Y) > (int16_t)PLAYER_Y_MAX)
        return;
    wr16(image + player + PLAYER_Y, be16(image + player + PLAYER_Y) + PLAYER_STEP_PIXELS);
}

/* player_move_left @ 0x13dc2. The x gate is `tst.w (a0) / beq / bmi`: it refuses at zero AND at any
 * negative x, so the two are one test rather than a range. The bank then steps down unless the byte
 * BEFORE the current one in `player_bank_frames` is the table's negative end marker. */
void player_move_left(uint8_t *image, uint32_t player) {
    if ((int16_t)be16(image + player + PLAYER_X) <= 0)
        return;
    wr16(image + player + PLAYER_X, be16(image + player + PLAYER_X) - PLAYER_STEP_PIXELS);
    if ((int8_t)image[A_player_bank_frames + be16(image + A_player_bank) - 1u] < 0)
        return;
    wr16(image + A_player_bank, be16(image + A_player_bank) - 1u);
}

/* player_move_right @ 0x13de8 — the same shape against the table's other end marker. */
void player_move_right(uint8_t *image, uint32_t player) {
    if ((int16_t)be16(image + player + PLAYER_X) > (int16_t)PLAYER_X_MAX)
        return;
    wr16(image + player + PLAYER_X, be16(image + player + PLAYER_X) + PLAYER_STEP_PIXELS);
    if ((int8_t)image[A_player_bank_frames + be16(image + A_player_bank) + 1u] < 0)
        return;
    wr16(image + A_player_bank, be16(image + A_player_bank) + 1u);
}

/* player_reset_to_start @ 0x13d24 — put the plane back on the template at 0x1909c.
 *
 * It WRITES THE TEMPLATE on the way past: the bank's current frame is stamped into the template's
 * own frame byte before the seven bytes are copied, so the template carries the last reset's bank
 * from then on rather than the shipped 0.
 */
void player_reset_to_start(uint8_t *image) {
    image[A_player_start_template + PLAYER_FRAME] =
        image[A_player_bank_frames + be16(image + A_player_bank)];
    for (unsigned byte = 0; byte < PLAYER_RECORD_BYTES; byte++)
        image[A_player + byte] = image[A_player_start_template + byte];
}

/* ================================================================================================
 * The bomb
 * ============================================================================================= */

/* bomb_drop @ 0x13d5c — one bomb, if none is already in the air or going off. */
void bomb_drop(uint8_t *image, uint32_t player) {
    if (be16(image + A_bomb_exploding) != 0 || be16(image + A_bomb_falling) != 0)
        return;
    if (image[A_infinite_bombs_flag] == 0) {
        if ((int16_t)be16(image + A_bombs) < (int16_t)BOMBS_MIN_TO_DROP)
            return;
        wr16(image + A_bombs, be16(image + A_bombs) - 1u);
    }
    image[A_bomb_falling] = SCC_TRUE;
    wr16(image + A_player_bomb + BOMB_X,
         be16(image + player + PLAYER_X) + BOMB_DROP_X_OFFSET);
    wr16(image + A_player_bomb + BOMB_START_Y, be16(image + player + PLAYER_Y));
}

/* ================================================================================================
 * Firing: the five patterns, the slot allocator and the button
 * ============================================================================================= */

/* One bullet of a shot. `st` sets the HIGH byte of the state word, which is what makes a launched
 * bullet 0xff00 rather than 1 — `player_bullets_move_all` reads the whole word. */
static void bullet_launch(uint8_t *image, uint32_t bullet, uint16_t x, uint16_t y, uint16_t dx) {
    wr16(image + bullet + PLAYER_BULLET_X, x);
    wr16(image + bullet + PLAYER_BULLET_Y, y);
    wr16(image + bullet + PLAYER_BULLET_DX, dx);
    image[bullet + PLAYER_BULLET_STATE] = SCC_TRUE;
}

/* The FOURTH bullet of every pattern above level 0 is launched differently: its state word is
 * CLEARED before the `st` sets the high byte, where the other four are only `st`. Two of the four
 * patterns write its dx on the way past and two do not — so in patterns 1 and 3 that bullet flies
 * with whatever dx the PREVIOUS shot in the same slot left behind. Reproduced, not repaired.
 *
 * `dx_or_keep` is the dx to write, or NO_DX for the patterns that never write one. */
#define NO_DX (-1)

static void bullet_launch_clearing_state(uint8_t *image, uint32_t bullet, uint16_t x, uint16_t y,
                                         int dx_or_keep) {
    wr16(image + bullet + PLAYER_BULLET_X, x);
    wr16(image + bullet + PLAYER_BULLET_Y, y);
    if (dx_or_keep != NO_DX)
        wr16(image + bullet + PLAYER_BULLET_DX, (uint16_t)dx_or_keep);
    wr16(image + bullet + PLAYER_BULLET_STATE, 0);
    image[bullet + PLAYER_BULLET_STATE] = SCC_TRUE;
}

static void bullet_hold(uint8_t *image, uint32_t bullet) {
    wr16(image + bullet + PLAYER_BULLET_STATE, 0);
}

/* The `movea.l (a6)+,a5` walk every pattern makes: bullet `index` of the shot slot. */
static uint32_t shot_bullet(const uint8_t *image, uint32_t slot, unsigned index) {
    return be32(image + slot + index * ENTITY_GROUP_PTR_BYTES);
}

/* fire_pattern_level0 @ 0x13ee0 — one bullet, straight up, from the nose. */
void fire_pattern_level0(uint8_t *image, uint32_t slot) {
    uint16_t muzzle_y = be16(image + A_player + PLAYER_Y) + BULLET_MUZZLE_DY;
    uint16_t centre_x = be16(image + A_player + PLAYER_X) + 9u;

    bullet_hold(image, shot_bullet(image, slot, 0));
    bullet_hold(image, shot_bullet(image, slot, 1));
    bullet_launch(image, shot_bullet(image, slot, 2), centre_x, muzzle_y, 0);
    bullet_hold(image, shot_bullet(image, slot, 3));
    bullet_hold(image, shot_bullet(image, slot, 4));
}

/* fire_pattern_level1 @ 0x13f20 — two straight bullets, one from each wing root. */
void fire_pattern_level1(uint8_t *image, uint32_t slot) {
    uint16_t player_x = be16(image + A_player + PLAYER_X);
    uint16_t muzzle_y = be16(image + A_player + PLAYER_Y) + BULLET_MUZZLE_DY;

    bullet_hold(image, shot_bullet(image, slot, 0));
    bullet_hold(image, shot_bullet(image, slot, 1));
    bullet_launch(image, shot_bullet(image, slot, 2), player_x + 2u, muzzle_y, 0);
    bullet_launch_clearing_state(image, shot_bullet(image, slot, 3), player_x + 0x10u, muzzle_y,
                                 NO_DX);
    bullet_hold(image, shot_bullet(image, slot, 4));
}

/* fire_pattern_level2 @ 0x13f72 — three bullets: one leaning left, one straight, one leaning right.
 *
 * From here on the x's are a RUNNING sum in the original's D0 (`addi.w #$8,d0` on top of the last),
 * except the fourth bullet, which re-reads the player's own x. The arithmetic below keeps that
 * distinction: a chain that recomputed every offset from the player would be a different routine
 * the moment one of the adds overflowed a word.
 */
void fire_pattern_level2(uint8_t *image, uint32_t slot) {
    uint16_t player_x = be16(image + A_player + PLAYER_X);
    uint16_t muzzle_y = be16(image + A_player + PLAYER_Y) + BULLET_MUZZLE_DY;
    uint16_t running_x = player_x + 2u;

    bullet_hold(image, shot_bullet(image, slot, 0));
    bullet_launch(image, shot_bullet(image, slot, 1), running_x, muzzle_y, 0xffffu);
    running_x += 8u;
    bullet_launch(image, shot_bullet(image, slot, 2), running_x, muzzle_y, 0);
    bullet_launch_clearing_state(image, shot_bullet(image, slot, 3), player_x + 0x12u, muzzle_y, 1);
    bullet_hold(image, shot_bullet(image, slot, 4));
}

/* fire_pattern_level3 @ 0x13fda — four bullets, the outer pair at twice the spread. */
void fire_pattern_level3(uint8_t *image, uint32_t slot) {
    uint16_t player_x = be16(image + A_player + PLAYER_X);
    uint16_t muzzle_y = be16(image + A_player + PLAYER_Y) + BULLET_MUZZLE_DY;
    uint16_t running_x = player_x + 2u + 1u;

    bullet_hold(image, shot_bullet(image, slot, 0));
    bullet_launch(image, shot_bullet(image, slot, 1), running_x, muzzle_y, 0xfffeu);
    bullet_launch(image, shot_bullet(image, slot, 2), running_x, muzzle_y, 0);
    running_x = player_x + 0x11u;
    bullet_launch_clearing_state(image, shot_bullet(image, slot, 3), running_x, muzzle_y, NO_DX);
    running_x += 2u;
    bullet_launch(image, shot_bullet(image, slot, 4), running_x, muzzle_y, 2);
}

/* fire_pattern_level4 @ 0x1404c — the full five-way fan. */
void fire_pattern_level4(uint8_t *image, uint32_t slot) {
    uint16_t player_x = be16(image + A_player + PLAYER_X);
    uint16_t muzzle_y = be16(image + A_player + PLAYER_Y) + BULLET_MUZZLE_DY;
    uint16_t running_x = player_x + 2u;

    bullet_launch(image, shot_bullet(image, slot, 0), running_x, muzzle_y, 0xfffdu);
    bullet_launch(image, shot_bullet(image, slot, 1), running_x, muzzle_y, 0xffffu);
    running_x += 8u;
    bullet_launch(image, shot_bullet(image, slot, 2), running_x, muzzle_y, 0);
    running_x = player_x + 0x12u;
    bullet_launch_clearing_state(image, shot_bullet(image, slot, 3), running_x, muzzle_y, 1);
    bullet_launch(image, shot_bullet(image, slot, 4), running_x, muzzle_y, 3);
}

/* The `jmp (a0)` at 0x13ede, as a call. The pointer is read out of the image, so a table the game
 * rewrote would still dispatch through this; the default arm is for one it cannot hold. */
static void fire_pattern_dispatch(uint8_t *image, uint32_t pattern, uint32_t slot) {
    switch (pattern) {
    case FN_FIRE_PATTERN_LEVEL0: fire_pattern_level0(image, slot); break;
    case FN_FIRE_PATTERN_LEVEL1: fire_pattern_level1(image, slot); break;
    case FN_FIRE_PATTERN_LEVEL2: fire_pattern_level2(image, slot); break;
    case FN_FIRE_PATTERN_LEVEL3: fire_pattern_level3(image, slot); break;
    case FN_FIRE_PATTERN_LEVEL4: fire_pattern_level4(image, slot); break;
    default: break;
    }
}

/* player_fire_by_weapon_level @ 0x13ebc — pick the pattern the power-up level has earned.
 *
 * `lsl.w #2,d1` scales the level in a WORD, so a level past 0x3fff would wrap the offset rather
 * than run off the table; the game's own level is 0..4. */
void player_fire_by_weapon_level(uint8_t *image, uint32_t slot) {
    uint16_t offset;

    if (image[A_max_weapon_flag] != 0)
        wr16(image + A_weapon_level, WEAPON_LEVEL_MAX);
    offset = (uint16_t)(be16(image + A_weapon_level) * WEAPON_FIRE_PTR_BYTES);
    fire_pattern_dispatch(image, be32(image + A_weapon_fire_tbl + offset), slot);
}

/* player_shot_slot_alloc @ 0x13e4e — take the first of the three shot slots that is free. */
void player_shot_slot_alloc(uint8_t *image) {
    for (unsigned index = 0; index < PLAYER_SHOT_SLOTS; index++) {
        uint32_t busy = A_shot_slot_busy_0 + index * SHOT_SLOT_BUSY_BYTES;

        if (be16(image + busy) != 0)
            continue;
        wr16(image + busy, 1);
        player_fire_by_weapon_level(image, A_player_shot_slot_0 + index * PLAYER_SHOT_TABLE_STRIDE);
        wr16(image + A_shot_slots_full, 0);
        return;
    }
    image[A_shot_slots_full] = SCC_TRUE;
}

/* player_fire @ 0x13e12 — one shot per press of the button, with its own sound.
 *
 * The sound is started INLINE rather than through one of the six `sfx_play_*` wrappers, and unlike
 * every one of them it is gated on the module reporting no effect already running — so the fire
 * sound is the one effect in the game that yields to whatever is playing.
 *
 * The debug-overlay arm is the original's `bsr debug_show_counters`, which FALLS THROUGH into
 * `console_show_message` rather than returning (src/hud.c). It is unreachable in the shipped game —
 * `debug_overlay_flag` is written nowhere — and test_player.py drives it with a checkpoint at that
 * fall-through instead of following the original off into a console spin.
 */
void player_fire(uint8_t *image) {
    if (image[A_debug_overlay_flag] != 0)
        debug_show_counters(image);
    if (be16(image + A_fire_held) != 0)
        return;
    player_shot_slot_alloc(image);
    if (be16(image + A_shot_slots_full) != 0)
        return;
    if (image[A_sound_module + SND_SFX_ACTIVE] == 0)
        sfx_start(image, SFX_PLAYER_FIRE);
    image[A_fire_held] = SCC_TRUE;
}

/* ================================================================================================
 * Publishing the plane, and dying
 * ============================================================================================= */

/* The game-over banner @ 0x13c68, reached from the death sequence and from `player_publish`'s
 * mode-4 arm: clear the two player slots, compile "GAME OVER" into the bomb-icon run, and count the
 * dwell down. When it expires the routine UNWINDS its caller and re-enters the hall of fame. */
static void player_game_over_display(uint8_t *image, uint32_t text_x, uint32_t text_y) {
    uint32_t script = A_text_game_over;
    uint32_t dest = A_dl_bomb_icons;

    clear_player_display_slots(image);
    build_text_display_list(image, &script, &dest, &text_x, &text_y);
    image[A_game_over_flag] = SCC_TRUE;
    wr16(image + A_game_over_delay, be16(image + A_game_over_delay) - 1u);
    if ((int16_t)be16(image + A_game_over_delay) < 0)
        game_over_hiscore_check(image);
}

/* player_death_sequence_step @ 0x13bd6 — walk the death animation, then spend a life.
 *
 * While the frame table lasts the plane sinks DEATH_SINK_PIXELS a frame and publishes itself with
 * its shadow record CLEARED, which is what makes the wreck cast none. When the table runs out the
 * routine either restarts the stage at its checkpoint (never returning — the slice stops at that
 * routine's entry) or, with the last life gone, puts the plane in game-over mode and falls into the
 * banner above.
 */
void player_death_sequence_step(uint8_t *image, uint32_t player, uint32_t text_x, uint32_t text_y) {
    uint32_t frame = A_player_death_frames + be16(image + A_death_anim_cursor);

    if ((int16_t)be16(image + frame) >= 0) {
        image[player + PLAYER_FRAME] = (uint8_t)be16(image + frame);
        wr16(image + A_death_anim_cursor, be16(image + A_death_anim_cursor) + DEATH_FRAME_BYTES);
        image[A_player_input_locked] = SCC_TRUE;
        wr16(image + player + PLAYER_Y, be16(image + player + PLAYER_Y) + DEATH_SINK_PIXELS);

        wr16(image + A_dl_player + DISPLAY_REC_X, be16(image + player + PLAYER_X));
        wr16(image + A_dl_player + DISPLAY_REC_Y, be16(image + player + PLAYER_Y));
        image[A_dl_player + DISPLAY_REC_FRAME] = image[player + PLAYER_FRAME];
        image[A_dl_player + DISPLAY_REC_ACTIVE] = DISPLAY_ACTIVE_ON_TOP;

        wr16(image + A_dl_player_shadow + DISPLAY_REC_X, 0);
        wr16(image + A_dl_player_shadow + DISPLAY_REC_Y, 0);
        image[A_dl_player_shadow + DISPLAY_REC_FRAME] = 0;
        image[A_dl_player_shadow + DISPLAY_REC_ACTIVE] = 0;
        return;
    }

    if (image[A_infinite_lives_flag] != 0)
        return;                                  /* @ 0x13c62: restart the stage, and never return */
    wr16(image + A_lives, be16(image + A_lives) - 1u);
    if (be16(image + A_lives) != 0)
        return;                                  /* ...the same arm */

    image[player + PLAYER_MODE] = PLAYER_MODE_GAMEOVER;
    wr16(image + A_lives, const_word(image, LIVES_AFTER_GAME_OVER));
    wr16(image + A_bombs, const_word(image, BOMBS_AFTER_GAME_OVER));
    player_game_over_display(image, text_x, text_y);
}

/* player_publish @ 0x13c96 — the plane and its shadow into the last two display records.
 *
 * The frame comes from the bank only in the modes where the player is flying it: the two scripts
 * and the death sequence each stamp their own, and mode 4 never gets that far. The shadow is the
 * same record offset by `shadow_offset` in BOTH axes with the sprite id seven higher, which is why
 * it slides out from under the plane as the take-off script runs.
 */
void player_publish(uint8_t *image, uint32_t text_x, uint32_t text_y) {
    uint8_t mode = image[A_player + PLAYER_MODE];
    uint16_t shadow_offset;

    if ((int8_t)mode >= 0 && mode != PLAYER_MODE_LANDING) {
        if (mode == PLAYER_MODE_DYING) {
            player_death_sequence_step(image, A_player, text_x, text_y);
            return;
        }
        if (mode == PLAYER_MODE_GAMEOVER) {
            player_game_over_display(image, text_x, text_y);
            return;
        }
        player_frame_from_bank(image, A_player);
    }

    wr16(image + A_dl_player + DISPLAY_REC_X, be16(image + A_player + PLAYER_X));
    wr16(image + A_dl_player + DISPLAY_REC_Y, be16(image + A_player + PLAYER_Y));
    image[A_dl_player + DISPLAY_REC_FRAME] = image[A_player + PLAYER_FRAME];
    image[A_dl_player + DISPLAY_REC_ACTIVE] = image[A_player + PLAYER_SHADOW_FRAME];

    shadow_offset = be16(image + A_shadow_offset);
    wr16(image + A_dl_player_shadow + DISPLAY_REC_X,
         be16(image + A_player + PLAYER_X) + shadow_offset);
    wr16(image + A_dl_player_shadow + DISPLAY_REC_Y,
         be16(image + A_player + PLAYER_Y) + shadow_offset);
    image[A_dl_player_shadow + DISPLAY_REC_FRAME] =
        (uint8_t)(image[A_player + PLAYER_FRAME] + SHADOW_FRAME_OFFSET);
    image[A_dl_player_shadow + DISPLAY_REC_ACTIVE] = image[A_player + PLAYER_SHADOW_FRAME];
}

/* ================================================================================================
 * Input
 * ============================================================================================= */

/* read_player_input @ 0x14354 — the frame loop's sixth call: joystick 1 into the plane.
 *
 * THE KEYBOARD IS DEAD. `use_keyboard_flag` chooses `key_bits` over `joy1_state` for the byte the
 * bomb test reads, and no instruction in the image ever writes that flag — and the DIRECTION tests
 * below re-read `joy1_state` unconditionally anyway, so even a set flag would only move the bomb
 * button. Both are reproduced as they are.
 *
 * The pause key SPINS until joystick 1 reports anything at all, which is why the read goes through
 * `sched_poll8`: the byte is the ACIA interrupt's and nothing in this routine writes it. The abort
 * key does not return at all — `adda.l #$40,a7` throws away this routine's own register save AND
 * its caller's return address before branching into the hall of fame.
 */
void read_player_input(uint8_t *image) {
    uint8_t bomb_button_byte = image[be16(image + A_use_keyboard_flag) != 0 ? A_key_bits
                                                                           : A_joy1_state];
    uint8_t stick;

    if (be16(image + A_player_input_locked) != 0)
        return;

    if (be16(image + A_level_just_started) == 0) {
        if (bit_held(image[A_key_bits], KEY_PAUSE_BIT))
            for (unsigned poll = 0; poll < OS_SCHED_POLL_MAX; poll++)
                if (sched_poll8(image, A_joy1_state, PAUSE_WAIT_PC) != 0)
                    break;
        if (bit_held(image[A_key_bits], KEY_ABORT_BIT)) {
            game_over_hiscore_check(image);
            return;
        }
    }

    wr16(image + A_player_turning, 0);
    if (bit_held(image[A_key_bits], KEY_BOMB_BIT)
        || bit_held(image[A_joy0_state], JOY_FIRE_BIT)) {
        bomb_drop(image, A_player);
    } else if (bomb_button_byte == 0) {
        /* Nothing held at all: level out and let go of the fire button, without reading the stick. */
        wr16(image + A_player_turning, 0);
        wr16(image + A_fire_held, 0);
        return;
    }

    stick = image[A_joy1_state];
    if (bit_held(stick, JOY_UP_BIT))
        player_move_up(image, A_player);
    if (bit_held(stick, JOY_DOWN_BIT))
        player_move_down(image, A_player);
    if (bit_held(stick, JOY_LEFT_BIT)) {
        image[A_player_turning] = SCC_TRUE;
        player_move_left(image, A_player);
    }
    if (bit_held(stick, JOY_RIGHT_BIT)) {
        image[A_player_turning] = SCC_TRUE;
        player_move_right(image, A_player);
    }
    if (!bit_held(stick, JOY_FIRE_BIT)) {
        wr16(image + A_fire_held, 0);
        return;
    }
    player_fire(image);
}

/* ================================================================================================
 * The two collision passes
 * ============================================================================================= */

/* One axis of the entity box test, @ 0x10fbc (x) and @ 0x10fde (y): does the player's own span meet
 * the entity's? The two ends are asked in different orders — the far edge when the entity starts to
 * the right of the player, the near edge otherwise — and both compares are SIGNED words. */
static int spans_meet(uint16_t near, uint16_t size, uint16_t point, uint16_t point_size) {
    if ((int16_t)near > (int16_t)point)
        return (int16_t)(uint16_t)(point + point_size) > (int16_t)near;
    return (int16_t)(uint16_t)(near + size) > (int16_t)point;
}

/* player_vs_entity_group_test @ 0x10fa0 — the shared loop both variants fall into.
 *
 * REPRODUCES A BUG. The loop's box WIDTH lives in D1, and the y test overwrites D1 with the box
 * HEIGHT from D6 before it uses it (`move.w d6,d1` @ 0x10fe8). So the first slot whose x span meets
 * the player's narrows the box for every slot after it in the same group: 0x1b becomes 0x17 for the
 * a-groups and 0x39 becomes 0x1b for the a4 group. Recreate, not remaster — a version that kept the
 * width is red against the original.
 *
 * The player's control mode is re-read at the top of EVERY iteration, because `lea $190a4,a1` IS
 * the `dbf`'s own target. In the original a dying plane leaves the remaining passes spinning the
 * counter down without touching a slot; this returns instead, which reads and writes exactly the
 * same bytes.
 */
void player_vs_entity_group_test(uint8_t *image, uint32_t group, uint32_t slots, uint32_t box_dx,
                                 uint32_t box_dy, uint32_t box_h, uint32_t box_w) {
    uint16_t width = (uint16_t)box_w;

    for (unsigned slot = 0; slot < slots; slot++) {
        uint32_t entity;

        if (image[A_player + PLAYER_MODE] == PLAYER_MODE_DYING)
            return;
        entity = be32(image + group + slot * ENTITY_GROUP_PTR_BYTES);
        if (be16(image + entity + ENTITY_ACTIVE) == 0 || be16(image + entity + ENTITY_DYING) != 0)
            continue;
        if (!spans_meet((uint16_t)(be16(image + entity + ENTITY_X) + box_dx), width,
                        be16(image + A_player + PLAYER_X), PLAYER_HIT_BOX_W))
            continue;
        width = (uint16_t)box_h;   /* the clobber: D1 := D6, and it sticks for the rest of the group */
        if (!spans_meet((uint16_t)(be16(image + entity + ENTITY_Y) + box_dy), (uint16_t)box_h,
                        be16(image + A_player + PLAYER_Y), PLAYER_HIT_BOX_H))
            continue;

        image[entity + ENTITY_DYING] = SCC_TRUE;
        image[A_player + PLAYER_MODE] = PLAYER_MODE_DYING;
        sfx_play_10(image);
        return;   /* the seam: `bra.w score_add_200` @ 0x11018 — see the note above */
    }
}

/* player_vs_entities_group @ 0x10f88 — seven slots against the standard 0x1b x 0x17 box. */
void player_vs_entities_group(uint8_t *image, uint32_t group) {
    player_vs_entity_group_test(image, group, ENTITY_A_GROUP_SLOTS, ENTITY_BOX_DX, ENTITY_BOX_DY,
                                ENTITY_BOX_H, ENTITY_BOX_W);
}

/* player_vs_entities_group_a4 @ 0x10f70 — four slots against a box more than twice as wide. Ghidra
 * left it unnamed and ../names.txt now carries this name. */
void player_vs_entities_group_a4(uint8_t *image, uint32_t group) {
    player_vs_entity_group_test(image, group, ENTITY_A4_GROUP_SLOTS, ENTITY_BOX_A4_DX,
                                ENTITY_BOX_A4_DY, ENTITY_BOX_A4_H, ENTITY_BOX_A4_W);
}

/* player_vs_entities @ 0x10f26 — the plane against the five groups that can ram it. */
void player_vs_entities(uint8_t *image) {
    static const uint32_t groups[] = {
        A_entity_group_a0, A_entity_group_a1, A_entity_group_a2, A_entity_group_a3,
    };

    if (image[A_invuln_flag] != 0)
        return;
    if (image[A_player + PLAYER_MODE] == PLAYER_MODE_GAMEOVER)
        return;
    for (unsigned group = 0; group < sizeof groups / sizeof groups[0]; group++)
        player_vs_entities_group(image, groups[group]);
    player_vs_entities_group_a4(image, A_entity_group_a4);
}

/* player_vs_enemy_bullets @ 0x1101c — the sixteen aimed shots against the plane's own sprite box.
 *
 * The box is the sprite record's, so it changes with the plane's bank; the bullet is a POINT
 * ENEMY_BULLET_HIT_OFFSET down and right of its record. Two `add.w 18(a4),d2` instructions inside
 * the test (@ 0x11090 and @ 0x11098) add the box HEIGHT to registers nothing reads afterwards, and
 * the pair of position loads at 0x11040 is written twice; both are dead and leave no trace in
 * memory, so they are named here rather than transcribed.
 *
 * The box is derived ONCE here where the original rebuilds it inside every iteration. Nothing in
 * the loop writes the player's frame or position — the one arm that does returns — so the two are
 * the same computation, hoisted.
 */
void player_vs_enemy_bullets(uint8_t *image) {
    uint32_t sprite;
    uint16_t left, top, right, bottom;

    if (image[A_invuln_flag] != 0)
        return;
    sprite = A_sprite_bank + image[A_player + PLAYER_FRAME] * SPRITE_RECORD_BYTES;
    left = be16(image + A_player + PLAYER_X) + be16(image + sprite + SPRITE_REC_DRAW_DX);
    right = left + be16(image + sprite + SPRITE_REC_HIT_W) - be16(image + sprite + SPRITE_REC_DRAW_DX);
    top = be16(image + A_player + PLAYER_Y) + be16(image + sprite + SPRITE_REC_DRAW_DY);
    bottom = top + be16(image + sprite + SPRITE_REC_HIT_H) - be16(image + sprite + SPRITE_REC_DRAW_DY);

    for (unsigned slot = 0; slot < ENEMY_BULLET_SLOTS; slot++) {
        uint32_t bullet = A_enemy_bullets + slot * ENEMY_BULLET_BYTES;
        uint16_t x, y;

        if (be16(image + bullet + ENEMY_BULLET_ACTIVE) == 0)
            continue;
        x = be16(image + bullet + ENEMY_BULLET_X) + ENEMY_BULLET_HIT_OFFSET;
        y = be16(image + bullet + ENEMY_BULLET_Y) + ENEMY_BULLET_HIT_OFFSET;
        if ((int16_t)x < (int16_t)left || (int16_t)y < (int16_t)top)
            continue;
        if ((int16_t)x > (int16_t)right || (int16_t)y > (int16_t)bottom)
            continue;

        if (image[A_player + PLAYER_MODE] == PLAYER_MODE_DYING)
            return;
        image[A_player + PLAYER_MODE] = PLAYER_MODE_DYING;
        wr16(image + bullet + ENEMY_BULLET_ACTIVE, 0);
        image[A_music_suspend_flag] = SCC_TRUE;
        image[A_player_hit] = SCC_TRUE;
        music_stop(image);
        sfx_play_6(image);
        return;
    }
}

/* ================================================================================================
 * Level flow
 * ============================================================================================= */

/* The level-advance arm @ 0x12504, which every path leaves by re-entering the frame loop.
 *
 * Past the fifth level the game LOOPS, and where it restarts is one of three one-shot flags: the
 * second time through it starts at level 1, the third at 2, the fourth at 3, and the fifth clears
 * all three and starts again at 0. Each start index is read out of `const_words_0123` rather than
 * spelt as an immediate.
 */
static void level_advance(uint8_t *image) {
    static const struct { uint32_t flag; unsigned start; } loops[] = {
        { A_level_loop_flag_1, LEVEL_LOOP_1_START },
        { A_level_loop_flag_2, LEVEL_LOOP_2_START },
        { A_level_loop_flag_3, LEVEL_LOOP_3_START },
    };

    wr16(image + A_level_number, be16(image + A_level_number) + 1u);
    if (be16(image + A_level_number) == LEVELS) {
        unsigned loop;

        for (loop = 0; loop < sizeof loops / sizeof loops[0]; loop++) {
            if (be16(image + loops[loop].flag) != 0)
                continue;
            image[loops[loop].flag] = SCC_TRUE;
            wr16(image + A_level_number, const_word(image, loops[loop].start));
            break;
        }
        if (loop == sizeof loops / sizeof loops[0]) {
            for (loop = 0; loop < sizeof loops / sizeof loops[0]; loop++)
                wr16(image + loops[loop].flag, 0);
            wr16(image + A_level_number, 0);
        }
    }
    wr16(image + A_level_complete, 0);
}

/* level_progress_check @ 0x124ae — the frame loop's fourth call: where the stage has got to.
 *
 * Three things in one routine, in the order the scroll passes them: the LEVEL ADVANCE, once the
 * landing script has finished; the END OF LEVEL, which starts the clear tune and puts the plane in
 * fly-off mode; and the BOSS trigger, which raises `player_hit`. `game_over_flag` gates the last
 * two off, and a plane already on the landing script leaves through a bare `rts` shared with the
 * two turn routines.
 */
void level_progress_check(uint8_t *image) {
    if (be16(image + A_level_complete) != 0) {
        level_advance(image);
        return;
    }
    if (image[A_player + PLAYER_MODE] == PLAYER_MODE_LANDING)
        return;
    if (be16(image + A_game_over_flag) != 0)
        return;
    if ((int16_t)be16(image + A_level_end_scroll_pos) <= (int16_t)be16(image + A_scroll_pos)) {
        music_play(image, LEVEL_CLEAR_TUNE);
        image[A_player + PLAYER_MODE] = PLAYER_MODE_FLYOFF;
        return;
    }
    if ((int16_t)be16(image + A_boss_scroll_pos) > (int16_t)be16(image + A_scroll_pos))
        return;
    image[A_player_hit] = SCC_TRUE;
}

/* restart_level_at_checkpoint @ 0x14aa8, SLICE [0x14aac, 0x14b22) — everything the stage restart
 * does before it reaches `clear_actor_arrays`, which is the init subsystem's and unported.
 *
 * THE CHECKPOINT SCAN WALKS BACKWARDS AND HAS NO FLOOR. It starts on the SCROLL_POS word of the
 * table's seventh record — the shipped tables end with a 0x2710 sentinel there, far past any real
 * scroll — and steps back a record at a time until one is behind the plane. Nothing stops it at
 * record 0: a scroll position low enough would walk off the front of the table into the pointer
 * array above it. The game's own restart never can, because a stage's scroll always starts past
 * CHECKPOINT_SCROLL_BACK; the case that drives it is test_player.py's, and the walk is the
 * original's either way.
 */
void restart_level_at_checkpoint_setup(uint8_t *image) {
    uint32_t table;
    uint32_t record;

    image[A_level_just_started] = SCC_TRUE;
    /* The RAW scancode byte, not `key_bits` beside it — so a held pause or abort key really does
     * survive the restart, and `level_just_started` is what stops it acting on the next frame. */
    image[A_key_last_scancode] = 0;
    image[A_joy1_state] = 0;
    image[A_joy0_state] = 0;
    wr16(image + A_player_hit, 0);

    table = be32(image + A_checkpoint_tables
                 + (uint16_t)(be16(image + A_level_number) * CHECKPOINT_TABLE_PTR_BYTES));
    wr16(image + A_scroll_pos, be16(image + A_scroll_pos) - CHECKPOINT_SCROLL_BACK);
    record = table + CHECKPOINT_SCAN_FROM;
    while ((int16_t)be16(image + record) >= (int16_t)be16(image + A_scroll_pos))
        record -= CHECKPOINT_REC_BYTES;
    record -= CHECKPOINT_REC_SCROLL_POS;

    wr16(image + A_checkpoint_map_offset, be16(image + record + CHECKPOINT_REC_MAP_OFFSET));
    wr16(image + A_checkpoint_scroll_pos, be16(image + record + CHECKPOINT_REC_SCROLL_POS));
    wr16(image + A_checkpoint_scroll_fine, be16(image + record + CHECKPOINT_REC_SCROLL_FINE));
    wr16(image + A_checkpoint_scroll_pos,
         be16(image + A_checkpoint_scroll_pos) + CHECKPOINT_SCROLL_BACK);
    clear_display_list(image);
}

/* ================================================================================================
 * The glue: register ABI in, core out
 * ============================================================================================= */

/* No arguments at all: each loads the player record or its own tables. */
void g_takeoff_script_reset(uint8_t *image) { takeoff_script_reset(image); }
void g_landing_script_reset(uint8_t *image) { landing_script_reset(image); }
void g_player_script_step(uint8_t *image) { player_script_step(image); }
void g_player_bank_recentre(uint8_t *image) { player_bank_recentre(image); }
void g_player_reset_to_start(uint8_t *image) { player_reset_to_start(image); }
void g_player_shot_slot_alloc(uint8_t *image) { player_shot_slot_alloc(image); }
void g_player_fire(uint8_t *image) { player_fire(image); }
void g_read_player_input(uint8_t *image) { read_player_input(image); }
void g_player_vs_entities(uint8_t *image) { player_vs_entities(image); }
void g_player_vs_enemy_bullets(uint8_t *image) { player_vs_enemy_bullets(image); }
void g_level_progress_check(uint8_t *image) { level_progress_check(image); }
void g_restart_level_at_checkpoint_setup(uint8_t *image) { restart_level_at_checkpoint_setup(image); }

/* A0 = the player record. */
void g_player_frame_from_bank(uint8_t *image, uint32_t player) {
    player_frame_from_bank(image, player);
}
void g_player_move_up(uint8_t *image, uint32_t player) { player_move_up(image, player); }
void g_player_move_down(uint8_t *image, uint32_t player) { player_move_down(image, player); }
void g_player_move_left(uint8_t *image, uint32_t player) { player_move_left(image, player); }
void g_player_move_right(uint8_t *image, uint32_t player) { player_move_right(image, player); }
void g_bomb_drop(uint8_t *image, uint32_t player) { bomb_drop(image, player); }

/* A6 = the shot slot's five bullet pointers. */
void g_fire_pattern_level0(uint8_t *image, uint32_t slot) { fire_pattern_level0(image, slot); }
void g_fire_pattern_level1(uint8_t *image, uint32_t slot) { fire_pattern_level1(image, slot); }
void g_fire_pattern_level2(uint8_t *image, uint32_t slot) { fire_pattern_level2(image, slot); }
void g_fire_pattern_level3(uint8_t *image, uint32_t slot) { fire_pattern_level3(image, slot); }
void g_fire_pattern_level4(uint8_t *image, uint32_t slot) { fire_pattern_level4(image, slot); }
void g_player_fire_by_weapon_level(uint8_t *image, uint32_t slot) {
    player_fire_by_weapon_level(image, slot);
}

/* A3 = the group's pointer array. */
void g_player_vs_entities_group(uint8_t *image, uint32_t group) {
    player_vs_entities_group(image, group);
}
void g_player_vs_entities_group_a4(uint8_t *image, uint32_t group) {
    player_vs_entities_group_a4(image, group);
}
/* A3 = the group, D7 = slots - 1, D3 = box dx, D4 = box dy, D6 = box height, D1 = box width. */
void g_player_vs_entity_group_test(uint8_t *image, uint32_t group, uint32_t slots_minus_one,
                                   uint32_t box_dx, uint32_t box_dy, uint32_t box_h,
                                   uint32_t box_w) {
    player_vs_entity_group_test(image, group, slots_minus_one + 1u, box_dx, box_dy, box_h, box_w);
}

/* A0 = the player record, D1 and D2 = the text cursor the game-over banner inherits. */
void g_player_death_sequence_step(uint8_t *image, uint32_t player, uint32_t text_x,
                                  uint32_t text_y) {
    player_death_sequence_step(image, player, text_x, text_y);
}
/* D1 and D2 = the same, for the mode-4 arm. */
void g_player_publish(uint8_t *image, uint32_t text_x, uint32_t text_y) {
    player_publish(image, text_x, text_y);
}
