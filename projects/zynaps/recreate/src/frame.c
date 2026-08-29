/* frame.c — the game's per-frame loop.
 *
 * include/frame.h's header comment says why every routine here is a SLICE of one long `bra` chain
 * rather than a function with an `rts`, where the slice boundaries really are (they are not the
 * three addresses ../../names.txt names), and which two 68000 scratch registers the loop carries
 * across a verified callee's `rts` and therefore takes as parameters.
 *
 * Almost nothing here is new work: the five slices are ORCHESTRATION over leaves other files have
 * verified — the panel (src/hud.c), the scroller (src/scroll.c), the ship's movers (src/player.c),
 * the weapons and the shot maintenance (src/weapon.c), the enemies and their scripts (src/enemy.c),
 * the mothership (src/mothership.c), the masked blitter and the pairwise overlap test
 * (src/sprite.c, src/collision.c), the screen flip (src/video.c) and the IKBD (src/input.c). What
 * the slices add is the ORDER, the gates, and the state machine that ends a life or a section.
 */
#include "machine.h"
#include "hw.h"          /* the kit's hardware write ledger — include/frame.h says what it pins */
#include "os.h"          /* os_refused, for the TEMPORARY stub at the bottom of this file */
#include "sched.h"       /* ...and its scheduled-write model, for the frame's two busy-waits */

#include "collision.h"
#include "enemy.h"
#include "entity.h"
#include "frame.h"
#include "highscore.h"
#include "hud.h"
#include "init.h"
#include "input.h"
#include "irq.h"
#include "mothership.h"
#include "player.h"
#include "rng.h"
#include "score.h"
#include "scroll.h"
#include "sound.h"
#include "sprite.h"
#include "video.h"
#include "weapon.h"

/* The next record of a 0x2c-byte array, stepped the way the 68000's address ALU does. Every pass
 * below walks one array with `lea 44(aN),aN`, and this is that instruction.
 *
 * IT IS `src/enemy.c`'s FILE-STATIC OF THE SAME NAME, and the duplicate is deliberate rather than
 * unnoticed: that copy is static, this subsystem does not own that file, and the migration is one
 * prototype in `include/collision.h` beside `entity_record` — exactly the move that header's own
 * comment describes for COLLISION_ROW_BYTES. STATUS.md carries the debt. */
static uint32_t next_record(uint32_t record) {
    return addr_add(record, ENTITY_STRIDE);
}

/* One entity's row of the all-pairs overlap table. */
static uint32_t collision_row(unsigned index) {
    return collision_table_row(A_entity_collision_masks, (uint16_t)index);
}

/* ================================================================================================
 * frame_panel_scroll_and_ship_stage — [0x10f4e, 0x113c0).
 *
 * The loop head: repaint whichever pieces of the status panel have asked for it, service the pause
 * key, advance the backdrop scroller by one 2-pixel step, arm the mothership when the level has
 * scrolled far enough, paint the playfield, and then read the joystick and move the ship.
 *
 * IT HAS TWO EXITS. The player-control block is guarded by three tests — the ship's death explosion
 * running, its record dead, its record exploding — and each of them branches to 0x1167c, PAST the
 * 0x113c0 that ../../names.txt calls the next stage. The return value is which exit was taken.
 * ============================================================================================= */

/* `btst #n,$19904` + `bsr` + `bclr #n,$19904`. Bit 4 is the odd one out and is not spelt with this:
 * it has no `bclr`, so the lives strip is repainted on every frame the bit stands. */
static void panel_redraw_if_asked(uint8_t *image, unsigned bit, void (*repaint)(uint8_t *)) {
    if ((image[A_panel_redraw_mask] & (1u << bit)) == 0)
        return;
    repaint(image);
    image[A_panel_redraw_mask] &= (uint8_t)~(1u << bit);
}

/* The weapon icon's repaint takes an argument the other three do not, so it does not fit the
 * function pointer above. */
static void panel_redraw_weapon_icon(uint8_t *image) {
    hud_draw_weapon_icon(image, PANEL_WEAPON_ICON_LEFT_CELL);
}

static void frame_panel_repaint(uint8_t *image) {
    draw_score_panel(image, be32(image + A_screen_front));
    if (image[A_panel_redraw_mask] & (1u << PANEL_REDRAW_LIVES_BIT))
        draw_lives_icons(image);
    image[A_explosion_phase_odd] = (uint8_t)~image[A_explosion_phase_odd];
    /* The logo animation runs only while NO repaint is pending at all — `tst.b` on the whole mask,
     * not on a bit of it — and then only once every PANEL_LOGO_PERIOD frames. */
    if (image[A_panel_redraw_mask] == 0) {
        wr16(image + A_panel_logo_countdown, (uint16_t)(be16(image + A_panel_logo_countdown) - 1u));
        if (be16(image + A_panel_logo_countdown) == 0) {
            wr16(image + A_panel_logo_countdown, PANEL_LOGO_PERIOD);
            hud_draw_logo_anim(image);
        }
    }
    panel_redraw_if_asked(image, PANEL_REDRAW_POWERUP_BIT, hud_draw_powerup_icon);
    panel_redraw_if_asked(image, PANEL_REDRAW_WEAPON_BIT, panel_redraw_weapon_icon);
    panel_redraw_if_asked(image, PANEL_REDRAW_GAUGE_BIT, draw_power_gauge);
}

/* The pause, at 0x10fda. Space held down pauses; the loop then waits for the release, restarts both
 * palette-cycle counters, waits for the next press and for ITS release.
 *
 * THREE SPINS ON A BYTE ONLY THE KEYBOARD INTERRUPT WRITES, and the middle one is a loop whose BODY
 * rewrites the two counters, so the reload happens once per pass rather than once before the wait.
 * Each poll goes through the kit's scheduled-write model at the address the ORIGINAL re-reads the
 * byte at, which is what a case's `wait_sites` names.
 *
 * A poll that exhausts its cap has already tallied the refusal and the case is void, so the only
 * correct thing left is to return — sched.h, "A CALLER MUST HONOUR THE 0". */
#define PAUSE_RELEASE_WAIT_PC 0x10fe6u
#define PAUSE_PRESS_WAIT_PC 0x10ffeu
#define PAUSE_SECOND_RELEASE_WAIT_PC 0x11008u

static void frame_pause_if_space(uint8_t *image) {
    if (image[A_key_scancode] != KEY_SCANCODE_SPACE)
        return;
    if (!sched_wait8(image, A_key_scancode, 0, PAUSE_RELEASE_WAIT_PC))
        return;
    /* The middle wait cannot be a `sched_wait8`: its body REWRITES the two counters on every pass,
     * so the loop has to be spelt out — and then it needs the cap `sched_wait8` would have given it,
     * or a case whose schedule never releases hangs the candidate instead of failing it. Same bound
     * and same tally as the kit's own (sched.h, "WHY A CAP AT ALL"), and the same `#ifndef` as
     * `ikbd_send_cmd`'s (src/input.c), because on target the spin is the original's, unbounded. */
    for (unsigned poll = 0; ; poll++) {
        image[A_palette_swap_countdown] = PAUSE_PALETTE_COUNTDOWN;
        image[A_palette_rotate_countdown] = PAUSE_PALETTE_COUNTDOWN;
        if (sched_poll8(image, A_key_scancode, PAUSE_PRESS_WAIT_PC) == KEY_SCANCODE_SPACE)
            break;
#ifndef OS_NO_REFUSAL_TALLY
        if (poll + 1 >= OS_SCHED_POLL_MAX) {
            os_refused(0);
            return;
        }
#endif
    }
    (void)sched_wait8(image, A_key_scancode, 0, PAUSE_SECOND_RELEASE_WAIT_PC);
}

/* An asteroid section has no map, so its cursor is derived from the scroll position rather than
 * stepped: `lsr.l #3` undoes SCROLL_PHASE_STEP and `mulu.w #$24` scales the column back to bytes. */
static void frame_scroll_cursor_from_scroll_pos(uint8_t *image) {
    /* `lsr.l #3,d7` then `mulu.w #$24,d7` — a 16x16 multiply, so only the shifted longword's LOW
     * WORD is a factor. The cast is what makes a scroll position past 0x80000 fold the way the
     * 68000 folds it rather than producing a cursor megabytes past the map. */
    uint32_t offset = (uint16_t)(be32(image + A_scroll_pos) >> 3) * MAP_COLUMN_BYTES;

    wr32(image + A_map_offset, offset);
    wr32(image + A_map_ptr, addr_add(A_map_unpacked, offset));
}

/* Page 0 of the eight-page ring is the one that decodes a fresh tile column and advances the map
 * cursor; pages 1..7 re-emit the workspace that page 0 filled, two pixels further along. */
static void frame_scroll_emit_column(uint8_t *image) {
    uint32_t page = be32(image + addr_add(A_map_page_table, MAP_PAGE_PTR_BYTES * image[A_map_page]));
    uint32_t phase;

    wr32(image + A_map_page_ptr, page);
    phase = SCROLL_PHASE_STEP * image[A_map_column];
    if (image[A_map_page] != 0) {
        uint32_t edge = addr_add(be32(image + A_screen_back), SCROLL_WINDOW_BYTES);

        if (image[A_scroll_frozen])
            scroll_emit_column_shift0(image, A_scroll_col_workspace, addr_add(page, phase), edge);
        else
            scroll_emit_column_shift2(image, A_scroll_col_workspace, addr_add(page, phase), edge);
        return;
    }
    {
        /* `map_offset` is republished from the cursor only on the UNFROZEN arm; the frozen one
         * steps the cursor back a column instead and leaves the offset where it was. */
        uint32_t cursor = be32(image + A_map_ptr);

        if (image[A_scroll_frozen]) {
            cursor = addr_add(cursor, (uint32_t)-(int32_t)MAP_COLUMN_BYTES);
        } else {
            wr32(image + A_map_offset, addr_add(cursor, (uint32_t)-(int32_t)A_map_unpacked));
            cursor = be32(image + A_map_ptr);
        }
        cursor = scroll_emit_tile_column(image,
                                         addr_add(be32(image + A_screen_back), SCROLL_WINDOW_BYTES),
                                         addr_add(page, phase), cursor);
        wr32(image + A_map_ptr, cursor);
    }
}

/* The mothership trigger at 0x11102, and the sprite build that follows it. Both are gated on the
 * boss not already owning the playfield. */
static void frame_mothership_gates(uint8_t *image) {
    if (image[A_boss_sequence_active] == 0 && image[A_mothership_ready] == 0
        && (int32_t)be32(image + A_scroll_pos) >= (int32_t)MOTHERSHIP_TRIGGER_SCROLL_POS) {
        image[A_mothership_pending] = 1;
        image[A_scroll_frozen] = 1;
        if ((int16_t)sign_ext8(image[A_mothership_index]) < MOTHERSHIP_INDEX_SEGMENTED)
            mothership_begin(image);
        else
            mothership_segments_respawn(image);
    }
    if (image[A_mothership_prep_stage] == 0)
        return;
    /* `cmp.b #$5,d2` after an `ext.w` — a BYTE compare of a sign-extended byte, unlike the word
     * compare the trigger above makes of the same global. Transcribed, not tidied. */
    if ((int8_t)image[A_mothership_index] < MOTHERSHIP_INDEX_SEGMENTED)
        mothership_spawn_head(image);
    else
        mothership_sprite_build_step(image);
}

/* The twenty page-to-screen blits the jump table at 0x179aa selects between, in table order.
 *
 * IT IS A SECOND COPY of `src/scroll.c`'s file-static `scroll_blit_jump_table`, for `next_record`'s
 * reason: that array is static, this subsystem does not own the file, and the migration is dropping
 * its `static` and declaring it in `include/scroll.h`. STATUS.md carries the debt. */
static void (*const FRAME_SCROLL_BLITS[SCROLL_PHASES])(uint8_t *, uint32_t, uint32_t) = {
    scroll_page_to_screen_p00, scroll_page_to_screen_p01, scroll_page_to_screen_p02,
    scroll_page_to_screen_p03, scroll_page_to_screen_p04, scroll_page_to_screen_p05,
    scroll_page_to_screen_p06, scroll_page_to_screen_p07, scroll_page_to_screen_p08,
    scroll_page_to_screen_p09, scroll_page_to_screen_p10, scroll_page_to_screen_p11,
    scroll_page_to_screen_p12, scroll_page_to_screen_p13, scroll_page_to_screen_p14,
    scroll_page_to_screen_p15, scroll_page_to_screen_p16, scroll_page_to_screen_p17,
    scroll_page_to_screen_p18, scroll_page_to_screen_p19,
};

/* A boss encounter and an asteroid field both have no backdrop, so the playfield is cleared rather
 * than blitted; otherwise the column phase picks one of the twenty specialised copies.
 *
 * THE INDEX IS NOT BOUNDED HERE AND THE ORIGINAL DOES NOT BOUND IT EITHER (`and.l #$ff` then
 * `lsl.l #2` straight into the table), but the two are not the same risk: past the twentieth entry
 * the original reads a defined address while this array read would be undefined behaviour. What
 * keeps it in range is that A_map_column has exactly two writers and both wrap it at SCROLL_PHASES
 * — the frame's own tail (`frame_scroll_step` below) and `section_start_prefill` (src/init.c) —
 * which `test_the_scroll_step_wraps_both_counters` holds. A fuzz that poked a wider column would be
 * testing neither program. */
static void frame_paint_playfield(uint8_t *image) {
    if (image[A_boss_sequence_active] != 0 || image[A_asteroid_section_flag] != 0) {
        playfield_clear(image);
        return;
    }
    FRAME_SCROLL_BLITS[image[A_map_column]](image, be32(image + A_map_page_ptr),
                                            be32(image + A_screen_back));
}

/* The auto-centre at 0x111f4: with neither up nor down pressed the tilt bank rolls back towards its
 * middle frame, one step every SHIP_TILT_PERIOD frames, and the ship's y follows it. */
#define SHIP_TILT_CENTRE 3
#define JOYSTICK_UP_DOWN_MASK 3u

/* THE SHIP IS TWO ENTITY RECORDS — slots 17 and 18, its double-buffer pair — and every mover writes
 * the same coordinate into both, as two independent read-modify-writes. `field` is the offset in the
 * first record and `mirror` the same field in the second; include/player.h's SHIP_MIRROR_Y is the
 * one it names, and SHIP_MIRROR_X below is its horizontal twin.
 *
 * src/player.c has the same pair of writers as file-statics for `ship_move_up`/`_down`; they are
 * not shared because they are static there, and STATUS.md carries the debt. */
static void ship_pair_set(uint8_t *image, uint32_t ship, uint32_t field, uint32_t mirror,
                          uint16_t value) {
    wr16(image + ship + field, value);
    wr16(image + ship + mirror, value);
}

static void ship_pair_add(uint8_t *image, uint32_t ship, uint32_t field, uint32_t mirror,
                          uint16_t delta) {
    wr16(image + ship + field, (uint16_t)(be16(image + ship + field) + delta));
    wr16(image + ship + mirror, (uint16_t)(be16(image + ship + mirror) + delta));
}

static void frame_ship_tilt_recentre(uint8_t *image) {
    uint32_t speed_entry;

    if (image[A_joystick_state] & JOYSTICK_UP_DOWN_MASK)
        return;
    image[A_ship_tilt_countdown] -= 1;
    if (image[A_ship_tilt_countdown] != 0)
        return;
    image[A_ship_tilt_countdown] = SHIP_TILT_PERIOD;
    if (image[A_ship_tilt] == SHIP_TILT_CENTRE)
        return;

    speed_entry = addr_add(A_ship_speed_table,
                           sign_ext8(image[A_ship_speed_level]) * SHIP_SPEED_ENTRY_BYTES);
    if ((int8_t)image[A_ship_tilt] >= SHIP_TILT_CENTRE) {
        ship_pair_add(image, A_player_record, ENTITY_Y, SHIP_MIRROR_Y,
                      be16(image + speed_entry + SHIP_SPEED_DY_DOWN));
        if ((int16_t)be16(image + A_player_record + ENTITY_Y) > SHIP_Y_MAX)
            ship_pair_set(image, A_player_record, ENTITY_Y, SHIP_MIRROR_Y, SHIP_Y_MAX);
        image[A_ship_tilt] -= 1;
        return;
    }
    ship_pair_add(image, A_player_record, ENTITY_Y, SHIP_MIRROR_Y,
                  (uint16_t)(0u - be16(image + speed_entry + SHIP_SPEED_DY_UP)));
    if ((int16_t)be16(image + A_player_record + ENTITY_Y) < SHIP_Y_MIN)
        ship_pair_set(image, A_player_record, ENTITY_Y, SHIP_MIRROR_Y, SHIP_Y_MIN);
    image[A_ship_tilt] += 1;
}

/* The joystick decode at 0x112a0. The horizontal arms are here rather than in src/player.c because
 * they have no `rts` of their own — `bra 0x113c0` ends each of them — while the two vertical ones
 * are real routines ../../names.txt names (`ship_move_up`, `ship_move_down`). */
#define JOYSTICK_UP_BIT 0
#define JOYSTICK_DOWN_BIT 1
#define JOYSTICK_LEFT_BIT 2
#define JOYSTICK_RIGHT_BIT 3
#define JOYSTICK_FIRE_BIT 7
/* `cmpi.w #$42` + `ble` on the way left, `cmpi.w #$150` + `bge` on the way right. */
#define SHIP_X_HOME_EDGE 0x42
#define SHIP_X_MAX 0x150
/* The pair's home column; the shadow sits SHIP_X_SHADOW_GAP to its right. */
#define SHIP_X_HOME 0x40u
#define SHIP_X_SHADOW_HOME 0x50u
#define SHIP_MIRROR_X 0x2cu
/* `mulu.w #$c80,d1` — one tilt frame of the ship bank is two sprites (the ship and its shadow). */
#define SHIP_TILT_BANK_BYTES (2u * SHIP_SPRITE_GAP)
#define SHIP_MIRROR_SPRITE 0x36u

static void frame_ship_move(uint8_t *image, uint8_t joystick) {
    uint32_t speed_entry = addr_add(A_ship_speed_table,
                                    sign_ext8(image[A_ship_speed_level]) * SHIP_SPEED_ENTRY_BYTES);
    uint32_t bank;

    if (joystick & (1u << JOYSTICK_UP_BIT))
        ship_move_up(image, A_player_record, speed_entry);
    if (joystick & (1u << JOYSTICK_DOWN_BIT))
        ship_move_down(image, A_player_record, speed_entry);

    bank = addr_add(A_ship_sprite_bank, image[A_ship_tilt] * SHIP_TILT_BANK_BYTES);
    wr32(image + A_player_record + ENTITY_SPRITE, bank);
    wr32(image + A_player_record + SHIP_MIRROR_SPRITE, addr_add(bank, SHIP_SPRITE_GAP));

    if (joystick & (1u << JOYSTICK_RIGHT_BIT)) {
        /* THE CLAMP ON THIS ARM IS DEAD CODE: `bge` jumps straight to the stage's end, so the two
         * stores at 0x113b4 that would park the pair at 0x150/0x160 are unreachable. Transcribing
         * them would be transcribing bytes no path executes. */
        if ((int16_t)be16(image + A_player_record + ENTITY_X) < SHIP_X_MAX)
            ship_pair_add(image, A_player_record, ENTITY_X, SHIP_MIRROR_X,
                          be16(image + speed_entry + SHIP_SPEED_DX_RIGHT));
        return;
    }
    if ((joystick & (1u << JOYSTICK_LEFT_BIT)) == 0)
        return;
    if ((int16_t)be16(image + A_player_record + ENTITY_X) > SHIP_X_HOME_EDGE) {
        ship_pair_add(image, A_player_record, ENTITY_X, SHIP_MIRROR_X,
                      (uint16_t)(0u - be16(image + speed_entry + SHIP_SPEED_DX_LEFT)));
        return;
    }
    wr16(image + A_player_record + ENTITY_X, SHIP_X_HOME);
    wr16(image + A_player_record + SHIP_MIRROR_X, SHIP_X_SHADOW_HOME);
}

unsigned frame_panel_scroll_and_ship_stage(uint8_t *image) {
    frame_panel_repaint(image);
    frame_pause_if_space(image);

    if (image[A_boss_sequence_active] == 0) {
        if (image[A_asteroid_section_flag])
            frame_scroll_cursor_from_scroll_pos(image);
        else
            frame_scroll_emit_column(image);
    }
    frame_mothership_gates(image);
    frame_paint_playfield(image);

    if (image[A_explosion_group_active_bits] & (1u << EXPLOSION_BIT_SHIP_DEATH))
        return 0;
    if (image[A_player_record + ENTITY_ALIVE] == 0)
        return 0;
    if (image[A_player_record + ENTITY_ALIVE] & (1u << ALIVE_BIT_EXPLODING))
        return 0;

    frame_ship_tilt_recentre(image);
    frame_ship_move(image, image[A_joystick_state]);
    return 1;
}

/* ================================================================================================
 * frame_drone_and_fire_stage — [0x113c0, 0x1167c).
 *
 * The trail drone (weapon 4's escort, which flies the ship's own position ten frames stale), and
 * then the fire button: released, it clears the charge state; held, it counts up to a charged shot;
 * newly pressed, it launches whichever weapon is selected — and falls through to the plain bullet
 * when the selected weapon is already at its limit.
 * ============================================================================================= */

/* The drone's record is entity slot 19, which include/weapon.h names for its OTHER role: the same
 * record is the gunsight the seeker locks through. One address, two jobs, and both names are
 * ../../names.txt's. */
static void frame_trail_drone(uint8_t *image, uint32_t ship) {
    uint32_t history;
    uint32_t packed;
    unsigned index;

    if (image[A_entity_gunsight + ENTITY_ALIVE] == 0) {
        if (image[A_selected_weapon] != WEAPON_KIND_SEEKER)
            return;
        image[A_trail_drone_active] = 1;
        image[A_entity_gunsight + ENTITY_ALIVE] = 1;
        image[A_entity_gunsight + ENTITY_TYPE] = TYPE_TRAIL_DRONE;
        wr32(image + A_entity_gunsight + ENTITY_SPRITE, A_gunsight_sprite);
        wr16(image + A_entity_gunsight + ENTITY_HEIGHT, TRAIL_DRONE_ROWS);
        /* The whole history is primed with the ship's position, so a drone just launched follows
         * the ship instead of a stale record's leftovers. */
        for (index = 0; index < SHIP_POS_HISTORY_ENTRIES; index++) {
            uint32_t slot = addr_add(A_ship_pos_history,
                                     SHIP_POS_HISTORY_ENTRY_BYTES * index);

            wr16(image + slot, be16(image + ship + ENTITY_X));
            wr16(image + slot + 2u, be16(image + ship + ENTITY_Y));
        }
        image[A_ship_pos_history_index] = 0;
        image[A_active_count_seekers] = 0;
    }

    history = addr_add(A_ship_pos_history,
                       sign_ext8(image[A_ship_pos_history_index]) * SHIP_POS_HISTORY_ENTRY_BYTES);
    /* ONE LONGWORD ADD over the packed {x, y} pair, so a y that overflows its word carries into x
     * exactly as the original's `add.l` does. */
    packed = be32(image + history) + TRAIL_DRONE_OFFSET_PACKED;
    wr16(image + A_entity_gunsight + ENTITY_Y, (uint16_t)packed);
    wr16(image + A_entity_gunsight + ENTITY_X, (uint16_t)(packed >> 16));

    wr16(image + history, be16(image + ship + ENTITY_X));
    wr16(image + history + 2u, be16(image + ship + ENTITY_Y));
    image[A_ship_pos_history_index] += 1;
    if (image[A_ship_pos_history_index] == SHIP_POS_HISTORY_ENTRIES)
        image[A_ship_pos_history_index] = 0;
}

/* `tst.b $1990a` — the shield gates how many of the selected weapon may be in flight at once. */
static uint8_t weapon_shots_allowed(const uint8_t *image) {
    return image[A_shield_level] ? WEAPON_SHOTS_WITH_SHIELD : WEAPON_SHOTS_WITHOUT_SHIELD;
}

/* The first free slot of entity slots 0..5, or PLAYER_SHOT_SLOTS when they are all in use. */
static unsigned first_free_shot_slot(const uint8_t *image) {
    unsigned slot;

    for (slot = 0; slot < PLAYER_SHOT_SLOTS; slot++)
        if (image[entity_record((uint16_t)slot) + ENTITY_ALIVE] == 0)
            return slot;
    return PLAYER_SHOT_SLOTS;
}

/* The plain bullet at 0x11600, which three of the four weapon arms fall THROUGH to when their own
 * count is at its limit — the `bge` targets this rather than the stage's end. */
static void frame_fire_bullet(uint8_t *image, uint32_t ship, uint8_t joystick) {
    unsigned slot;
    uint32_t shot;

    if ((int8_t)image[A_active_bullets] >= (int8_t)image[A_weapon_power_level])
        return;
    slot = first_free_shot_slot(image);
    if (slot == PLAYER_SHOT_SLOTS)
        return;

    shot = entity_record((uint16_t)slot);
    wr16(image + shot + ENTITY_X,
         (uint16_t)(be16(image + ship + ENTITY_X) + BULLET_SPAWN_DX));
    wr16(image + shot + ENTITY_Y,
         (uint16_t)(be16(image + ship + ENTITY_Y) + BULLET_SPAWN_DY));
    image[shot + ENTITY_ALIVE] = 1;
    wr32(image + shot + ENTITY_SPRITE, A_player_bullet_sprite);
    image[shot + ENTITY_ANIM_FRAME] = 0;
    wr16(image + shot + ENTITY_HEIGHT, BULLET_ROWS);
    image[shot + ENTITY_TYPE] = BULLET_TYPE;
    image[A_active_bullets] += 1;
    image[A_bullet_fire_toggle] ^= 1u;
    sound_start(image, BULLET_SOUND, joystick);
}

/* The three counted weapons. All three have the SAME shape — a signed byte count against the shield
 * allowance, then the first free slot of 0..5 — and differ only in the counter and the launcher. The
 * seeker's arm spells its slot scan with the opposite branch polarity (`beq` out of the loop rather
 * than `bne` round it) and its bomb sibling reloads A3 the loop already holds, but both walk the
 * same six records from slot 0 and both give up the press when every one of them is busy.
 *
 * They are three functions rather than one table-driven body because `fire_seeker` and `fire_bomb`
 * take a sound channel and `fire_homing_missile` takes none, so the three launcher calls have three
 * shapes; the count-and-scan half above them is `weapon_shots_allowed` + `first_free_shot_slot`.
 *
 * Returns 1 when the arm has dealt with the press, 0 when it fell through to the plain bullet. */
static unsigned frame_fire_seeker_arm(uint8_t *image, uint8_t joystick) {
    unsigned slot;

    if ((int8_t)image[A_active_count_seekers] >= (int8_t)weapon_shots_allowed(image))
        return 0;
    slot = first_free_shot_slot(image);
    if (slot == PLAYER_SHOT_SLOTS)
        return 1;
    image[A_active_count_seekers] += 1;
    fire_seeker(image, entity_record((uint16_t)slot), ENTITY_INDEX_TRAIL_DRONE, joystick);
    return 1;
}

static unsigned frame_fire_missile_arm(uint8_t *image) {
    unsigned slot;

    if ((int8_t)image[A_active_count_type32] >= (int8_t)weapon_shots_allowed(image))
        return 0;
    slot = first_free_shot_slot(image);
    if (slot == PLAYER_SHOT_SLOTS)
        return 1;
    image[A_active_count_type32] += 1;
    fire_homing_missile(image, entity_record((uint16_t)slot));
    return 1;
}

static unsigned frame_fire_bomb_arm(uint8_t *image, uint8_t joystick) {
    unsigned slot;

    if ((int8_t)image[A_active_count_bombs] >= (int8_t)weapon_shots_allowed(image))
        return 0;
    slot = first_free_shot_slot(image);
    if (slot == PLAYER_SHOT_SLOTS)
        return 1;
    image[A_active_count_bombs] += 1;
    fire_bomb(image, entity_record((uint16_t)slot), joystick);
    return 1;
}

/* The fire button's own state machine, at 0x11474. */
static void frame_fire_button(uint8_t *image, uint32_t ship, uint8_t joystick) {
    if ((joystick & (1u << JOYSTICK_FIRE_BIT)) == 0) {
        image[A_fire_button_held] = 0;
        image[A_fire_charge_counter] = 0;
        image[A_fire_charged] = 0;
        wr16(image + A_palette_hw_shadow, 0);
        image[A_charge_flash_dir] = 0;
        return;
    }
    if (image[A_fire_button_held]) {
        if (image[A_fire_charged])
            return;
        image[A_fire_charge_counter] += 1;
        if (image[A_fire_charge_counter] == FIRE_CHARGE_FULL)
            image[A_fire_charged] = 1;
        return;
    }

    image[A_fire_button_held] = 1;
    switch (image[A_selected_weapon]) {
    case WEAPON_KIND_SEEKER:
        if (frame_fire_seeker_arm(image, joystick))
            return;
        break;
    case WEAPON_KIND_MISSILE:
        if (frame_fire_missile_arm(image))
            return;
        break;
    case WEAPON_KIND_BOMB:
        if (frame_fire_bomb_arm(image, joystick))
            return;
        break;
    case WEAPON_BULLET:
        break;
    default:
        /* No `bra` to the bullet arm on this path: an unknown weapon fires nothing at all. */
        return;
    }
    frame_fire_bullet(image, ship, joystick);
}

void frame_drone_and_fire_stage(uint8_t *image, uint32_t ship, uint8_t joystick) {
    frame_trail_drone(image, ship);
    frame_fire_button(image, ship, joystick);
}

/* ================================================================================================
 * frame_spawn_and_move_stage — [0x1167c, 0x11c00).
 *
 * Where the three player gates in the first slice converge with the fire button's every arm. It
 * animates the charged weapon's palette flash, steps the plain bullets, runs the explosion and
 * scenery animations, fires the two map-driven spawn scripts, moves and animates every enemy,
 * maintains the player's own six shot slots, and ends with the enemy fire pass and the boss.
 * ============================================================================================= */

/* The charged flash walks the palette shadow up to CHARGE_FLASH_PEAK and back down to 0, one
 * CHARGE_FLASH_STEP a frame, turning round with a `not.b` at each end. It runs on the frames the
 * animation phase is clear, so at half rate. */
static void frame_charge_flash(uint8_t *image) {
    if (image[A_fire_charged] == 0 || image[A_explosion_phase_odd] != 0)
        return;
    if (image[A_charge_flash_dir] == 0) {
        wr16(image + A_palette_hw_shadow,
             (uint16_t)(be16(image + A_palette_hw_shadow) + CHARGE_FLASH_STEP));
        if (be16(image + A_palette_hw_shadow) == CHARGE_FLASH_PEAK)
            image[A_charge_flash_dir] = (uint8_t)~image[A_charge_flash_dir];
        return;
    }
    wr16(image + A_palette_hw_shadow,
         (uint16_t)(be16(image + A_palette_hw_shadow) - CHARGE_FLASH_STEP));
    if (be16(image + A_palette_hw_shadow) == 0)
        image[A_charge_flash_dir] = (uint8_t)~image[A_charge_flash_dir];
}

/* Every live type-0x34 bullet steps right and is retired at the screen's edge, which is also where
 * its count is given back. */
static void frame_bullets_advance(uint8_t *image) {
    uint32_t shot = A_entity_table;
    unsigned slot;

    for (slot = 0; slot < PLAYER_SHOT_SLOTS; slot++, shot = next_record(shot)) {
        if (image[shot + ENTITY_ALIVE] == 0 || image[shot + ENTITY_TYPE] != BULLET_TYPE)
            continue;
        wr16(image + shot + ENTITY_X, (uint16_t)(be16(image + shot + ENTITY_X) + BULLET_STEP_X));
        if ((int16_t)be16(image + shot + ENTITY_X) < (int16_t)BULLET_RETIRE_X)
            continue;
        image[A_active_bullets] -= 1;
        image[shot + ENTITY_ALIVE] = 0;
    }
}

/* A script fires when the map cursor's own column, plus one column of look-ahead, equals the
 * cursor word the script's next record carries. The wave script rounds that word DOWN to a whole
 * column first; the ground script compares it as it stands. */
static uint32_t frame_script_trigger_column(const uint8_t *image) {
    return (be32(image + A_map_offset) & 0xffffu) + SCRIPT_TRIGGER_LOOKAHEAD;
}

/* The attack script at 0x11722. Opcodes 0x0c and 0x0d only flip the asteroid squadron switch and
 * step the cursor; 0x0b spawns a trio; anything else spawns a formation from one of two alien
 * banks, chosen on a coin flip. */
static uint32_t frame_wave_script(uint8_t *image, uint32_t carried_y_register) {
    uint32_t cursor;
    uint16_t trigger;
    uint16_t entry;
    uint16_t opcode;

    if (image[A_mothership_pending])
        return carried_y_register;
    cursor = be32(image + A_wave_script_cursor);
    /* `move.w (a4),d7` / `and.l #$ffff` / `divu.w #$24` / `and.l #$ffff` / `mulu.w #$24` — five
     * instructions that leave D7 as the trigger word rounded DOWN to a whole column, with its high
     * word cleared. That register is the ground script's `ground_spawn_y_register` a few
     * instructions later, which is why this block returns it. */
    trigger = (uint16_t)((be16(image + cursor) / SCRIPT_TRIGGER_LOOKAHEAD)
                         * SCRIPT_TRIGGER_LOOKAHEAD);
    if ((uint16_t)frame_script_trigger_column(image) != trigger)
        return trigger;

    entry = be16(image + cursor + 2u);
    /* `move.w 2(a4),d7` then `lsr.w #8,d7` — D7's low word becomes the opcode, its high word still
     * the 0 the `and.l` above left. */
    opcode = (uint16_t)(entry >> 8);
    if (opcode == WAVE_OPCODE_TRIO) {
        wavescript_spawn_trio_type0e(image, cursor);
        /* ...and this arm and the default one below leave whatever the spawner did with D7, which
         * is the residual include/frame.h describes. */
        return carried_y_register;
    }
    if (opcode == WAVE_OPCODE_SQUADRONS_ON) {
        wr32(image + A_wave_script_cursor, addr_add(cursor, WAVE_SCRIPT_ENTRY_BYTES));
        image[A_squadron_spawn_enabled] = 1;
        return opcode;
    }
    if (opcode == WAVE_OPCODE_SQUADRONS_OFF) {
        wr32(image + A_wave_script_cursor, addr_add(cursor, WAVE_SCRIPT_ENTRY_BYTES));
        image[A_squadron_spawn_enabled] = 0;
        return opcode;
    }
    /* `move.b d7,d6` at 0x1175a — a BYTE move, so D6's high byte is stale caller state and only
     * the low byte of `entry` is really the register. `wavescript_spawn_wave` masks with 0xff
     * (src/enemy.c's WAVE_SPAWN_Y_MASK), which is why passing the whole word is equivalent; if that
     * mask ever widens, this call site has to narrow instead. */
    if ((rand16(image) >> WAVE_ALIEN_SHIFT) & 1u)
        wavescript_spawn_wave(image, cursor, opcode, entry, WAVE_ALIEN_TYPE_A,
                              A_wave_alien_sprite_a);
    else
        wavescript_spawn_wave(image, cursor, opcode, entry, WAVE_ALIEN_TYPE_B,
                              A_wave_alien_sprite_b);
    return carried_y_register;
}

/* The ground script at 0x117d2. Which of the two spawners runs is the section's own table byte. */
static void frame_ground_script(uint8_t *image, uint32_t ground_spawn_y_register) {
    uint32_t cursor;

    if (image[A_asteroid_section_flag] || image[A_scroll_frozen] || image[A_map_page])
        return;
    cursor = be32(image + A_ground_script_cursor);
    if ((uint16_t)frame_script_trigger_column(image) != be16(image + cursor))
        return;
    if (image[A_section_ground_target_flag])
        groundscript_spawn_type10(image, cursor, ground_spawn_y_register);
    else
        groundscript_spawn_type0f(image, cursor, ground_spawn_y_register);
}

/* The per-slot pass over the player's six shot slots at 0x1182c: steer the two steered kinds, force
 * every shot to an even column, and retire any that has left the box. */
static void frame_player_shots_maintain(uint8_t *image) {
    uint32_t shot = A_entity_table;
    unsigned slot;

    for (slot = 0; slot < PLAYER_SHOT_SLOTS; slot++, shot = next_record(shot)) {
        int16_t x;
        int16_t y;

        if (image[shot + ENTITY_ALIVE] == 0)
            continue;
        if (image[shot + ENTITY_TYPE] == SHOT_TYPE_SEEKER)
            seeker_update(image, shot);
        else if (image[shot + ENTITY_TYPE] == SHOT_TYPE_MISSILE)
            homing_missile_update(image, shot);
        else
            continue;

        image[shot + ENTITY_X + 1u] &= (uint8_t)~(1u << SHOT_X_ALIGN_BIT);
        x = (int16_t)be16(image + shot + ENTITY_X);
        y = (int16_t)be16(image + shot + ENTITY_Y);
        if (x < SHOT_X_MIN || x > SHOT_X_MAX || y < SHOT_Y_MIN || y > SHOT_Y_MAX)
            shot_retire_kind32(image, shot);
    }
}

void frame_spawn_and_move_stage(uint8_t *image, uint32_t chance_index_register,
                                uint32_t ground_spawn_y_register) {
    frame_charge_flash(image);
    frame_bullets_advance(image);
    explosion_animate_all(image);
    anim_ground_objects(image);
    /* The wave-script block writes D7 on every path but the one `mothership_pending` skips, and
     * the ground script below reads it — so the parameter is only the answer where the block did
     * not produce one. include/frame.h's header comment says which three paths those are. */
    frame_ground_script(image, frame_wave_script(image, ground_spawn_y_register));
    enemies_animate_all(image);
    enemies_move_all(image);
    frame_player_shots_maintain(image);
    player_shot_update_all(image);
    enemy_fire_and_update_shots(image, chance_index_register);

    if (image[A_asteroid_section_flag]) {
        squadron_spawn_tick(image);
        asteroids_move(image);
        asteroids_animate(image);
    }
    if (image[A_boss_sequence_active] == 0)
        return;
    mothership_move_and_place(image);
    wr32(image + A_mothership_phase_timer, be32(image + A_mothership_phase_timer) + 1u);
    mothership_draw(image);
}

/* ================================================================================================
 * frame_draw_objects_and_collide — [0x11c00, 0x11d30).
 *
 * Draw everything, then work out what touched what. The blitter publishes a per-record "this sprite
 * overlapped background pixels" byte as it goes, and the all-pairs sweep afterwards fills a bitmask
 * row per entity — which is what the resolve stage reads instead of testing boxes again.
 * ============================================================================================= */
void frame_draw_objects_and_collide(uint8_t *image) {
    unsigned left;
    unsigned index;

    asteroids_draw(image);
    if (image[A_mothership_ready]
        && (int16_t)sign_ext8(image[A_mothership_index]) >= MOTHERSHIP_INDEX_SEGMENTED) {
        mothership_segments_update(image);
        wr32(image + A_mothership_phase_timer, be32(image + A_mothership_phase_timer) + 1u);
    }

    for (index = 0; index < ENTITY_SLOTS; index++) {
        uint32_t object = entity_record((uint16_t)index);

        image[object + ENTITY_PIXEL_HIT] = 0;
        if (image[object + ENTITY_ALIVE])
            draw_sprite_masked_collide(image, object, object + ENTITY_PIXEL_HIT);
    }

    for (index = 0; index < COLLISION_MASK_LONGS; index++)
        wr32(image + collision_row(index), 0);

    /* Ordered pairs, and only downwards: entity `left` is tested against every entity BELOW it, so
     * each pair is visited once and both rows are marked by the one call. Slot 0 is never a `left`,
     * which is why the walk starts at 1. */
    for (left = 1; left < ENTITY_SLOTS; left++) {
        uint32_t left_record = entity_record((uint16_t)left);
        unsigned right;

        if (image[left_record + ENTITY_PIXEL_HIT] == 0)
            continue;
        for (right = 0; right < left; right++) {
            uint32_t right_record = entity_record((uint16_t)right);

            if (image[right_record + ENTITY_ALIVE])
                object_pair_overlap_mark(image, left_record, right_record,
                                         collision_row(left), collision_row(right),
                                         left, right);
        }
    }
}

/* ================================================================================================
 * frame_resolve_hits_and_game_state — [0x11d30, 0x1296e).
 *
 * The longest slice and the only one with more than one way out: resolve every hit the stage above
 * recorded, animate the two explosion kinds, scroll the starfield, run the three power-up decay
 * timers, step the scroller's own counters, wait for the raster and flip the buffers — and then run
 * the state machine that decides whether the next frame happens at all.
 * ============================================================================================= */

/* Enemy shots 8, 7 and 6 that hit the landscape with nothing else to explain it are absorbed. The
 * walk is DOWNWARDS and its `d0` is the index `collision_chain_walk` is asked about; the same
 * register is `bomb_update`'s sound channel two blocks later, which is why it is returned. */
static uint32_t frame_enemy_shots_absorb(uint8_t *image, uint32_t index) {
    unsigned pass;

    for (pass = 0; pass < ENEMY_SHOT_SLOT_COUNT; pass++, index--) {
        if (collision_chain_walk(image, (uint16_t)index))
            image[entity_record((uint16_t)index) + ENTITY_ALIVE] = 0;
    }
    return index;
}

/* Bouncing bombs. NO ALIVE GUARD — the type byte alone decides, so a dead slot whose type is still
 * 0x33 is stepped; `bomb_update` has its own. */
static void frame_bombs_update(uint8_t *image, uint32_t sound_channel) {
    uint32_t bomb = A_entity_table;
    unsigned slot;

    for (slot = 0; slot < PLAYER_SHOT_SLOTS; slot++, bomb = next_record(bomb))
        if (image[bomb + ENTITY_TYPE] == SHOT_TYPE_BOMB)
            bomb_update(image, bomb, (uint8_t)sound_channel);
}

/* What the gunsight is sitting on, published for the seeker to chase. While the boss owns the
 * playfield the answer is forced to the first enemy slot rather than searched for. */
static void frame_seeker_lock(uint8_t *image) {
    uint32_t gunsight_row = collision_row(ENTITY_INDEX_TRAIL_DRONE);
    uint32_t overlaps;
    unsigned slot;

    if (image[A_entity_gunsight + ENTITY_ALIVE] == 0) {
        image[A_seeker_lock_target_index] = 0;
        return;
    }
    if (image[A_boss_sequence_active]
        && collision_chain_walk(image, (uint16_t)ENTITY_INDEX_TRAIL_DRONE)) {
        image[A_seeker_lock_target_index] = (uint8_t)ENEMY_SLOT_FIRST;
        return;
    }
    overlaps = be32(image + gunsight_row);
    if ((overlaps & GUNSIGHT_ENEMY_MASK) == 0) {
        image[A_seeker_lock_target_index] = 0;
        return;
    }
    for (slot = 0; slot < ENEMY_SLOT_COUNT; slot++) {
        unsigned index = ENEMY_SLOT_FIRST + slot;
        uint32_t enemy = entity_record((uint16_t)index);

        /* The row is re-read every pass, exactly as the original's `move.l (a4),d1` inside the loop
         * does, and `entity_type_is_lockable` cannot change it — but the read is the instruction. */
        overlaps = be32(image + gunsight_row);
        if (image[enemy + ENTITY_ALIVE] == 0 || ((overlaps >> index) & 1u) == 0)
            continue;
        if (!entity_type_is_lockable(image, enemy))
            continue;
        image[A_seeker_lock_target_index] = (uint8_t)index;
        return;
    }
    image[A_seeker_lock_target_index] = 0;
}

/* One of the ship's two records against its own overlap row. A hit explained by an entity at index
 * 6 or above goes to the pick-up/death resolver; one explained only by the player's own six shot
 * slots is harmless; one explained by nothing at all is the landscape, and lethal.
 *
 * Returns 1 when the record answered — 0 sends the caller on to the OTHER ship record.
 *
 * `resolver_ship` IS NOT `hit_record`, and that is the original: the second pass advances only the
 * ROW pointer, so `ship_resolve_entity_hits` is called with entity slot 17 either way. */
static unsigned frame_ship_hit(uint8_t *image, uint32_t hit_record, uint32_t row,
                               uint32_t resolver_ship) {
    uint32_t overlaps;

    if (image[hit_record + ENTITY_PIXEL_HIT] == 0)
        return 0;
    overlaps = be32(image + row);
    if (overlaps & SHIP_HIT_ENTITY_MASK) {
        ship_resolve_entity_hits(image, resolver_ship, row);
        return 1;
    }
    if (overlaps & SHIP_HIT_OWN_SHOT_MASK)
        return 0;
    if (image[A_ship_invulnerable])
        return 1;
    image[A_death_event_flags] |= (uint8_t)(1u << DEATH_EVENT_BIT_SHIP);
    explosion_spawn(image, A_player_record, SHIP_DEATH_EXPLOSION_GROUP);
    return 1;
}

static void frame_ship_collision(uint8_t *image) {
    if (image[A_explosion_group_active_bits] & (1u << EXPLOSION_BIT_SHIP_DEATH))
        return;
    if (frame_ship_hit(image, A_player_record, collision_row(ENTITY_INDEX_SHIP), A_player_record))
        return;
    (void)frame_ship_hit(image, A_ship_record_shadow, collision_row(SHIP_SHADOW_SLOT),
                         A_player_record);
}

/* ================================================================================================
 * WHAT A VERIFIED CALLEE LEAVES IN D0, and why this stage has to know.
 *
 * `sound_start`'s channel IS D0 (include/sound.h's SOUND_CHANNEL_VOICE1 / _VOICE2, everything else
 * voice 3) and the stage reloads that register only in a few places, so between them each tune is
 * armed on whatever the last callee left behind. Two callees change it and this file models both:
 *
 *  - `score_add_bcd` ends with `move.l $195d8,d0` — the extra-life threshold AS IT WAS BEFORE the
 *    award, because 0x12e04 loads it before 0x12e26 rewrites it. Its own `sound_start` preserves
 *    every register (`movem.l #$fffe` / `#$7fff` around the whole body), so nothing disturbs it.
 *  - `mothership_segment_hit` calls that same routine on the one arm where a segment PAIR dies,
 *    under a `movem` that saves only A0 and A1, so it leaks the same value — and only there. The
 *    pair's death is observable from outside: both its records become EXPLOSION_PART_TYPE.
 *
 * `collision_chain_walk` is always called here under a `movem` that restores D0; `shot_retire_kind32`
 * / `_kind33` / `_kind36` never touch it; `explosion_spawn` and `ship_resolve_entity_hits` are only
 * called where the next instruction reloads it. `bomb_update` is the ONE that is not modelled, and
 * STATUS.md's "## Coverage limits" says what that costs and what would close it.
 * ============================================================================================= */
static uint32_t frame_award_score(uint8_t *image, unsigned award) {
    uint32_t threshold_before = be32(image + A_extra_life_threshold_bcd);

    score_add_bcd(image, A_score_award_table_bcd + SCORE_BCD_BYTES * (award + 1u));
    return threshold_before;
}

/* `bsr mothership_segment_hit` plus the D0 it may leak. `segment` is one of the pair's two records
 * and the routine rewrites BOTH, so this record's own type is what says the pair died. */
static uint32_t frame_segment_hit(uint8_t *image, uint32_t segment, uint32_t sound_channel) {
    uint32_t threshold_before = be32(image + A_extra_life_threshold_bcd);

    mothership_segment_hit(image, segment);
    return image[segment + ENTITY_TYPE] == EXPLOSION_PART_TYPE ? threshold_before : sound_channel;
}

/* The boss's own death, inside the projectile pass: park the big explosion on the anchor, pay for
 * it, and clear the five tail records.
 *
 * ITS SCORE DOES NOT REACH THE SOUND CHANNEL, unlike every other award in this stage: 0x11f38 and
 * 0x11f92 push and pop D0 around the whole arm. */
static void frame_boss_destroyed(uint8_t *image) {
    uint32_t part = A_entity_boss_parts;
    unsigned index;

    wr16(image + A_enemy_slots + ENTITY_X,
         (uint16_t)(be16(image + A_mothership_x) + BOSS_DEATH_EXPLOSION_DX));
    wr16(image + A_enemy_slots + ENTITY_Y,
         (uint16_t)(be16(image + A_mothership_y) + BOSS_DEATH_EXPLOSION_DY));
    (void)frame_award_score(image, SCORE_AWARD_BOSS);
    image[A_death_event_flags] |= (uint8_t)(1u << DEATH_EVENT_BOSS_BIT);
    explosion_spawn(image, A_enemy_slots, BOSS_EXPLOSION_GROUP);
    for (index = 0; index < MOTHERSHIP_TAIL_SEGMENTS; index++, part = next_record(part))
        image[part + ENTITY_ALIVE] = 0;
}

/* Slots 0..5: a player projectile whose blit touched non-background pixels. The impact puff is
 * skipped (it is already an effect), and while the boss owns the playfield "the landscape" IS the
 * boss, so the hit costs it a hit point.
 *
 * THE SOUND'S CHANNEL IS THE LOOP'S OWN COUNTER — `moveq #$0,d0` at 0x11ee4 and `addq.l #1,d0` per
 * pass — so slots 0 and 1 arm voices 1 and 2 and the rest arm voice 3. */
static void frame_player_shots_resolve(uint8_t *image) {
    uint32_t shot = A_entity_table;
    unsigned slot;

    for (slot = 0; slot < PLAYER_SHOT_SLOTS; slot++, shot = next_record(shot)) {
        if (image[shot + ENTITY_ALIVE] == 0 || image[shot + ENTITY_TYPE] == SHOT_TYPE_PUFF)
            continue;
        if (!collision_chain_walk(image, (uint16_t)slot))
            continue;

        if (image[A_boss_sequence_active]) {
            if (image[shot + ENTITY_TYPE] == SHOT_TYPE_BOMB)
                shot_retire_kind33(image, shot);
            sound_start(image, BOSS_HIT_SOUND, (uint8_t)slot);
            wr16(image + A_boss_hitpoints, (uint16_t)(be16(image + A_boss_hitpoints) - 1u));
            if (be16(image + A_boss_hitpoints) == 0)
                frame_boss_destroyed(image);
        }
        if (image[shot + ENTITY_TYPE] == SHOT_TYPE_MISSILE) {
            shot_retire_kind32(image, shot);
        } else if (image[shot + ENTITY_TYPE] == SHOT_TYPE_SEEKER) {
            shot_retire_kind36(image, shot);
        } else if (image[shot + ENTITY_TYPE] == BULLET_TYPE) {
            image[shot + ENTITY_ALIVE] = 0;
            image[A_active_bullets] -= 1;
        }
    }
}

/* The two explosion animations at 0x11fe0 and 0x120c8. They differ in four things — the phase byte
 * that gates them, the type they animate, the frame table they read, and one extra pair of stores
 * on the capsule arm — and in nothing else, so they are one body with those four as parameters.
 * `sound_channel` is D0 in and out: a capsule's award moves it (see the note above). */
static uint32_t frame_explosion_animate(uint8_t *image, uint8_t type, uint32_t frame_table,
                                        unsigned leaves_rising_capsule, uint32_t sound_channel) {
    uint32_t enemy = A_enemy_slots;
    unsigned slot;

    for (slot = 0; slot < ENEMY_SLOT_COUNT; slot++, enemy = next_record(enemy)) {
        unsigned index = ENEMY_SLOT_FIRST + slot;
        uint8_t alive = image[enemy + ENTITY_ALIVE];
        uint8_t frame;

        if (image[enemy + ENTITY_TYPE] != type)
            continue;
        if ((alive & (1u << ALIVE_BIT_EXPLODING)) == 0)
            continue;

        frame = (uint8_t)((alive & EXPLOSION_FRAME_MASK) + 1u);
        if (frame != EXPLOSION_LAST_FRAME) {
            /* `bset #7,d1` / `and.l #$7f,d1` / `sub.b #$1,d1` / `lsl.w #2,d1`: the frame is put back
             * WITH its exploding bit, and the table index is that byte less one — a BYTE subtract,
             * so a frame that wrapped to 0x80 indexes 0x3fc rather than 0. The step is not masked
             * to the table's own length anywhere; include/frame.h says what that costs. */
            uint8_t marked = (uint8_t)(frame | (1u << ALIVE_BIT_EXPLODING));
            uint32_t entry = EXPLOSION_FRAME_PTR_BYTES
                             * (uint8_t)((marked & EXPLOSION_FRAME_MASK) - 1u);

            image[enemy + ENTITY_ALIVE] = marked;
            wr32(image + enemy + ENTITY_SPRITE, be32(image + addr_add(frame_table, entry)));
            continue;
        }
        /* The last frame. A record with the no-credit tag simply dies; otherwise its squadron loses
         * a mark, and the squadron that runs out leaves a power-up capsule where it fell. */
        if (image[enemy + EXPLOSION_CREDIT_TAG_OFFSET] != EXPLOSION_NO_CREDIT_TAG) {
            uint32_t counter = addr_add(A_squadron_kill_counters,
                                        image[enemy + ENTITY_SQUADRON] & SQUADRON_ID_MASK);

            image[counter] -= 1;
            if (image[counter] == 0) {
                if (leaves_rising_capsule)
                    image[enemy + ACTOR_SPEED] = POWERUP_CAPSULE_LARGE_ANIM_FRAME;
                image[enemy + ENTITY_TYPE] = TYPE_POWERUP_CAPSULE;
                image[enemy + ENTITY_ANIM_FRAME] = POWERUP_CAPSULE_SPAWN_TAG;
                wr16(image + enemy + ENTITY_HEIGHT, POWERUP_CAPSULE_ROWS);
                if (leaves_rising_capsule)
                    wr16(image + enemy + ENTITY_Y,
                         (uint16_t)(be16(image + enemy + ENTITY_Y) - POWERUP_CAPSULE_LARGE_RISE));
                image[enemy + ENTITY_ALIVE] = 1;
                wr32(image + enemy + ENTITY_SPRITE, A_powerup_capsule_sprite);
                sound_channel = frame_award_score(image, SCORE_AWARD_CAPSULE);
                /* `bne 0x12092` — a capsule that lands ON THE TERRAIN is killed on the spot
                 * instead of announcing itself, and only the other answer plays the tune. Both
                 * arms end the pass for this record. */
                if (collision_chain_walk(image, (uint16_t)index))
                    image[enemy + ENTITY_ALIVE] = 0;
                else
                    sound_start(image, POWERUP_CAPSULE_SOUND, (uint8_t)sound_channel);
                continue;
            }
        }
        image[enemy + ENTITY_ALIVE] = 0;
    }
    return sound_channel;
}

/* `cmpi.b #$10` / `cmpi.b #$f` then `subq.b #1,26(a1)`: an armoured enemy spends a hit point instead
 * of exploding, and survives while it has one left. Returns 1 when it survived.
 *
 * THE RAM PASS PLAYS A TUNE HERE AND THE SHOOT PASS DOES NOT — 0x1222e loads one, 0x1239c does not
 * — and that is the only difference between the two spellings of this arm. */
static unsigned frame_enemy_absorbs_a_hit(uint8_t *image, uint32_t enemy, unsigned plays_sound,
                                          uint32_t sound_channel) {
    if (image[enemy + ENTITY_TYPE] != ENEMY_TYPE_ARMOURED_A
        && image[enemy + ENTITY_TYPE] != ENEMY_TYPE_ARMOURED_B)
        return 0;
    if (plays_sound)
        sound_start(image, ENEMY_HIT_SOUND, (uint8_t)sound_channel);
    image[enemy + ENTITY_HP] -= 1;
    return image[enemy + ENTITY_HP] != 0;
}

/* ...and what an enemy becomes once its last hit point is gone: one of the two explosion kinds,
 * aligned to four pixels, worth one of the two awards. Returns the D0 the award left. */
static uint32_t frame_enemy_explodes(uint8_t *image, uint32_t enemy) {
    unsigned big = image[enemy + ENTITY_TYPE] == ENEMY_TYPE_BIG;

    image[enemy + ENTITY_ALIVE] = ENEMY_EXPLODING_ALIVE;
    if (big) {
        image[enemy + ENTITY_TYPE] = EXPLOSION_TYPE_LARGE;
        wr32(image + enemy + ENTITY_SPRITE, A_explosion_large_sprite);
        wr16(image + enemy + ENTITY_HEIGHT, ENEMY_EXPLOSION_ROWS_LARGE);
    } else {
        image[enemy + ENTITY_TYPE] = EXPLOSION_PART_TYPE;
        wr32(image + enemy + ENTITY_SPRITE, A_mothership_explosion_sprite);
        /* THE ORIGINAL'S DEFECT, transcribed: `move.w #$10,$8.l` writes the row count into the
         * 68000's bus-error vector instead of into the record. include/frame.h states the finding
         * and ../../names.txt carries it on both of the two addresses it happens at. */
        wr16(image + BUS_ERROR_VECTOR, ENEMY_EXPLOSION_ROWS);
    }
    wr16(image + enemy + ENTITY_X,
         (uint16_t)(be16(image + enemy + ENTITY_X) & EXPLOSION_X_ALIGN));
    return frame_award_score(image, big ? SCORE_AWARD_ENEMY_BIG : SCORE_AWARD_ENEMY_SMALL);
}

/* The five types the second gate at 0x12284 admits — an armoured enemy whose hit points have just
 * run out is one of them, which is how the fall-through from the arm above reaches the explosion. */
static unsigned enemy_type_explodes_on_contact(uint8_t type) {
    return type == ENEMY_TYPE_BIG || type == ENEMY_TYPE_SMALL_A || type == ENEMY_TYPE_SMALL_B
           || type == ENEMY_TYPE_ARMOURED_A || type == ENEMY_TYPE_ARMOURED_B;
}

/* An enemy that has rammed one of the ship's two records. */
static uint32_t frame_enemy_rams_ship(uint8_t *image, uint32_t sound_channel) {
    uint32_t enemy = A_enemy_slots;
    unsigned slot;

    if (image[A_explosion_group_active_bits] & (1u << EXPLOSION_BIT_SHIP_DEATH))
        return sound_channel;
    for (slot = 0; slot < ENEMY_SLOT_COUNT; slot++, enemy = next_record(enemy)) {
        uint8_t type = image[enemy + ENTITY_TYPE];

        if (image[enemy + ENTITY_ALIVE] == 0
            || type == TYPE_POWERUP_CAPSULE || type == EXPLOSION_PART_TYPE)
            continue;
        if ((be32(image + collision_row(ENEMY_SLOT_FIRST + slot)) & SHIP_RECORD_MASK) == 0)
            continue;

        if (type == ENEMY_TYPE_BOSS_SEGMENT) {
            sound_channel = frame_segment_hit(image, enemy, sound_channel);
            continue;
        }
        if (type == ENEMY_TYPE_INVULNERABLE)
            continue;
        if (frame_enemy_absorbs_a_hit(image, enemy, 1, sound_channel))
            continue;
        if (!enemy_type_explodes_on_contact(image[enemy + ENTITY_TYPE]))
            continue;
        sound_channel = frame_enemy_explodes(image, enemy);
        sound_start(image, ENEMY_HIT_SOUND, (uint8_t)sound_channel);
    }
    return sound_channel;
}

/* What the shoot pass does to the SHOT once its hit has been dealt with (0x12414 onwards). Returns
 * 1 when the shot's retire path ends the inner walk over the eight enemies. */
static unsigned frame_shot_retires_on_hit(uint8_t *image, uint32_t shot, uint32_t shot_bit) {
    uint8_t type = image[shot + ENTITY_TYPE];

    if (type == SHOT_TYPE_MISSILE)
        return 1;
    if (type == SHOT_TYPE_BOMB) {
        shot_retire_kind33(image, shot);
        return 1;
    }
    if (type == SHOT_TYPE_SEEKER) {
        shot_retire_kind36(image, shot);
        return 1;
    }
    if (type != BULLET_TYPE)
        return 0;
    image[A_active_bullets] -= 1;
    image[shot + ENTITY_ALIVE] = 0;
    sound_start(image, ENEMY_HIT_SOUND, (uint8_t)shot_bit);
    return 0;
}

/* The 6 x 8 pairwise sweep of the player's shots against the eight enemy slots.
 *
 * D0 DOES THREE JOBS HERE AT ONCE, and the third is what makes the sweep's later passes depend on
 * its earlier ones. `move.l #$1,d0` at 0x122fa and `lsl.l #1,d0` at 0x12474 make it the SHOT'S OWN
 * BIT, which is the mask every collision row is tested with; every `sound_start` in the pass is
 * armed on that same register, so shot 0 reaches voice 1 and shot 1 voice 2; AND `score_add_bcd`
 * overwrites it with the extra-life threshold, under a `movem` that saves only A0 and A1. So the
 * first kill of the sweep REPLACES the shot mask for every pair after it, and the outer loop then
 * shifts the threshold instead of the bit.
 *
 * That is the original, not a defect this file is working around: it is why an enemy the shipped
 * rows do not put under a shot can still be hit, and a reconstruction that kept a tidy `1 << slot`
 * differs on the first frame two enemies die in (measured — that is the case that caught it).
 * ============================================================================================= */
static void frame_player_shots_hit_enemies(uint8_t *image) {
    uint32_t shot = A_entity_table;
    uint32_t overlap_mask = 1;              /* D0 — see the note above */
    unsigned shot_slot;

    for (shot_slot = 0; shot_slot < PLAYER_SHOT_SLOTS;
         shot_slot++, shot = next_record(shot), overlap_mask <<= 1) {
        uint32_t enemy = A_enemy_slots;
        unsigned enemy_slot;

        if (image[shot + ENTITY_ALIVE] == 0)
            continue;
        for (enemy_slot = 0; enemy_slot < ENEMY_SLOT_COUNT;
             enemy_slot++, enemy = next_record(enemy)) {
            uint8_t enemy_type;
            uint8_t alive;

            /* Re-tested every pass, because the arms below can retire the shot mid-walk. */
            if (image[shot + ENTITY_ALIVE] == 0
                || image[shot + ENTITY_TYPE] == EXPLOSION_PART_TYPE)
                break;
            alive = image[enemy + ENTITY_ALIVE];
            enemy_type = image[enemy + ENTITY_TYPE];
            if (alive == 0 || (alive & (1u << ALIVE_BIT_EXPLODING))
                || enemy_type == TYPE_POWERUP_CAPSULE || enemy_type == EXPLOSION_PART_TYPE)
                continue;
            if ((be32(image + collision_row(ENEMY_SLOT_FIRST + enemy_slot)) & overlap_mask) == 0)
                continue;

            if (enemy_type == ENEMY_TYPE_BOSS_SEGMENT) {
                overlap_mask = frame_segment_hit(image, enemy, overlap_mask);
                if (image[shot + ENTITY_TYPE] == SHOT_TYPE_MISSILE) {
                    shot_retire_kind32(image, shot);
                    sound_start(image, ENEMY_HIT_SOUND, (uint8_t)overlap_mask);
                    break;
                }
                /* `bne 0x1241e` skips the missile test below, which this arm has just made. */
            } else if (enemy_type != ENEMY_TYPE_INVULNERABLE
                       && !frame_enemy_absorbs_a_hit(image, enemy, 0, overlap_mask)) {
                overlap_mask = frame_enemy_explodes(image, enemy);
            }
            /* 0x12414: a missile is the one kind that neither retires nor goes on to the next
             * enemy — it plays the hit and leaves the walk. */
            if (frame_shot_retires_on_hit(image, shot, overlap_mask)) {
                sound_start(image, ENEMY_HIT_SOUND, (uint8_t)overlap_mask);
                break;
            }
        }
    }
}

/* Enemy shots 6..8 that touched the landscape with no entity overlap at all: a seeker leaves a
 * ground puff, an aimed shot just vanishes, and neither happens while the boss is up. */
static void frame_enemy_shots_ground(uint8_t *image) {
    uint32_t shot = A_enemy_shot_slots;
    unsigned slot;

    for (slot = 0; slot < ENEMY_SHOT_SLOT_COUNT; slot++, shot = next_record(shot)) {
        if (image[shot + ENTITY_ALIVE] == 0 || image[shot + ENTITY_PIXEL_HIT] == 0)
            continue;
        if (be32(image + collision_row(ENEMY_SHOT_SLOT_FIRST + slot)) != 0 || image[A_boss_sequence_active])
            continue;
        if (image[shot + ENTITY_TYPE] == GROUND_ABSORB_TYPE_SEEKER)
            enemy_morph_to_type6(image, shot);
        else if (image[shot + ENTITY_TYPE] == GROUND_ABSORB_TYPE_AIMED)
            image[shot + ENTITY_ALIVE] = 0;
    }
}

/* One parallax layer of six stars. `planes` names which of the four plane words the star is drawn
 * into; `moves` is the layer's own speed divider, already evaluated. Returns the cursor the next
 * layer starts from, because the three layers share one walking pointer. */
static uint32_t frame_starfield_layer(uint8_t *image, uint32_t cursor, unsigned plane0,
                                      unsigned plane2, unsigned moves) {
    unsigned star;

    for (star = 0; star < STARFIELD_STARS; star++) {
        uint16_t offset = be16(image + cursor);
        uint16_t x = be16(image + cursor + 2u);
        uint32_t mask_slot;
        uint16_t mask;
        uint32_t cell;
        uint16_t under = 0;
        unsigned plane;

        if ((int16_t)x < 0) {
            wr16(image + cursor + 2u, STARFIELD_RESPAWN_X);
            cursor = addr_add(cursor, STARFIELD_ENTRY_BYTES);
            continue;
        }
        mask_slot = addr_add(A_starfield_pixel_masks, 2u * (x & STARFIELD_X_PIXEL_MASK));
        mask = be16(image + mask_slot);
        cell = addr_add(be32(image + A_screen_back),
                        sign_ext16((uint16_t)(offset + ((x & STARFIELD_X_CELL_MASK) >> 1))));
        /* `movem.w (a0),#$00f0` then three `or.w`s: the star is drawn only where all four plane
         * words are clear of it, so it never lands on the playfield. */
        for (plane = 0; plane < STARFIELD_PLANES; plane++)
            under |= be16(image + addr_add(cell, 2u * plane));
        if ((under & mask) == 0) {
            if (plane0)
                wr16(image + cell, (uint16_t)(be16(image + cell) | mask));
            if (plane2)
                wr16(image + addr_add(cell, STARFIELD_PLANE2_OFFSET),
                     (uint16_t)(be16(image + addr_add(cell, STARFIELD_PLANE2_OFFSET)) | mask));
        }
        if (moves)
            wr16(image + cursor + 2u, (uint16_t)(x - 1u));
        cursor = addr_add(cursor, STARFIELD_ENTRY_BYTES);
    }
    return cursor;
}

static void frame_starfield(uint8_t *image) {
    uint32_t cursor = A_starfield_table;

    cursor = frame_starfield_layer(image, cursor, 1, 0, 1);
    cursor = frame_starfield_layer(image, cursor, 1, 1, image[A_starfield_layer2_phase] == 0);
    (void)frame_starfield_layer(image, cursor, 0, 1, image[A_starfield_layer3_countdown] == 0);

    image[A_starfield_layer3_countdown] -= 1;
    if ((int8_t)image[A_starfield_layer3_countdown] < 0)
        image[A_starfield_layer3_countdown] = STARFIELD_LAYER3_PERIOD;
    image[A_starfield_layer2_phase] = (uint8_t)~image[A_starfield_layer2_phase];
}

/* One power-up level stepping back down after POWERUP_DECAY_TICKS frames. `floor` is the value the
 * level stops at, and the shield's arm is the only one that also mirrors itself into the HUD. */
static void frame_decay_timer(uint8_t *image, uint32_t timer, uint32_t level, uint8_t floor,
                              unsigned mirrors_to_hud) {
    uint8_t stepped;

    wr16(image + timer, (uint16_t)(be16(image + timer) - 1u));
    if (be16(image + timer) != 0)
        return;
    wr16(image + timer, POWERUP_DECAY_TICKS);
    if (image[level] == floor)
        return;
    stepped = (uint8_t)(image[level] - 1u);
    if (mirrors_to_hud) {
        image[A_power_gauge_display] = stepped;
        image[A_panel_redraw_mask] |= (uint8_t)(1u << PANEL_REDRAW_GAUGE_BIT);
    }
    image[level] = stepped;
}

/* One 2-pixel step of the scroller, and the page/phase counters that follow it round their ring. */
static void frame_scroll_step(uint8_t *image) {
    wr32(image + A_scroll_pos, be32(image + A_scroll_pos) + 1u);
    if (image[A_scroll_frozen])
        return;
    image[A_map_page] += 1;
    if (image[A_map_page] != MAP_PAGES)
        return;
    image[A_map_page] = 0;
    image[A_map_column] += 1;
    if (image[A_map_column] == SCROLL_PHASES)
        image[A_map_column] = 0;
}

/* The frame's own end: wait for the raster to reach the phase the Timer B handler publishes, flip
 * the buffers, ask the keyboard controller for a joystick packet, wait for the vertical blank
 * handler to acknowledge it, and re-enable the ACIA interrupt.
 *
 * BOTH SPINS ARE ON A BYTE ONLY AN INTERRUPT WRITES, so both go through the kit's scheduled-write
 * model. `frame_pause_if_space` above says what an exhausted poll means. */
static void frame_end_and_flip(uint8_t *image) {
    if (!sched_wait8(image, A_raster_phase, FRAME_RASTER_PHASE_READY, FRAME_RASTER_WAIT_PC))
        return;
    screen_flip_buffers(image);
    ikbd_send_cmd(IKBD_CMD_INTERROGATE_JOYSTICK);
    image[A_vbl_wait_flag] = FRAME_VBL_WAIT_ARMED;
    if (!sched_wait8(image, A_vbl_wait_flag, FRAME_VBL_WAIT_DONE, FRAME_VBL_WAIT_PC))
        return;
    /* `bset #6,$fffa09` — a read-modify-write whose READ half has no modelled answer, so the value
     * stored is the bit ALONE rather than the bit OR'd into what the register held. Off target that
     * is the right store and an unpinned five bits; ON TARGET it is a DEFECT, and include/frame.h
     * says so beside MFP_IERB_UNMODELED_READ in the same words include/init.h uses for `andi.b #$fc,$ff8260`. */
    hw_write8(HW_MFP_IERB, MFP_IERB_UNMODELED_READ | (1u << MFP_ACIA_CHANNEL_BIT));
}

/* Which explosion groups have finished: a group is done when all six of the entity slots its member
 * list names have reached EXPLOSION_DONE_FRAME. Group 1 is the ship's death, group 0 the
 * end-of-section one, and the scan walks them in that order because its `dbf` counts down. */
static uint32_t frame_finished_explosion_groups(const uint8_t *image) {
    uint32_t done = 0;
    unsigned group;

    if (image[A_explosion_group_active_bits] == 0)
        return 0;
    for (group = EXPLOSION_GROUP_COUNT; group-- > 0;) {
        uint32_t members = addr_add(A_explosion_group_members, EXPLOSION_GROUP_MEMBERS * group);
        unsigned member;

        if ((image[A_explosion_group_active_bits] & (1u << group)) == 0)
            continue;
        for (member = 0; member < EXPLOSION_GROUP_MEMBERS; member++) {
            uint32_t record = entity_record(
                (uint16_t)sign_ext8(image[addr_add(members, member)]));

            if (image[record + EXPLOSION_PART_FRAME] != EXPLOSION_DONE_FRAME)
                break;
        }
        if (member == EXPLOSION_GROUP_MEMBERS)
            done |= 1u << group;
    }
    return done;
}

/* The two-player save/restore at 0x12796: park everything the live globals hold in this player's
 * record, swap to the other player, and read that player's record back. */
static void frame_player_swap(uint8_t *image) {
    uint32_t record = addr_add(A_player_records,
                               sign_ext8(image[A_current_player_index]) * PLAYER_RECORD_BYTES);

    wr32(image + record + PLAYER_SAVE_SCORE, be32(image + A_player_score_bcd));
    image[record + PLAYER_SAVE_LIVES] = image[A_lives];
    image[record + PLAYER_SAVE_SECTION] = image[A_level_section];
    wr32(image + record + PLAYER_SAVE_MAP_PTR, be32(image + A_map_ptr));
    image[record + PLAYER_SAVE_POWERUP_CURSOR] = image[A_powerup_cursor];
    image[record + PLAYER_SAVE_WEAPON_LEVEL] = image[A_weapon_power_level];
    image[record + PLAYER_SAVE_SPEED_LEVEL] = image[A_ship_speed_level];
    image[record + PLAYER_SAVE_UNUSED] = 0;

    image[A_current_player_index] ^= 1u;
    record = addr_add(A_player_records,
                      sign_ext8(image[A_current_player_index]) * PLAYER_RECORD_BYTES);
    wr32(image + A_player_score_bcd, be32(image + record + PLAYER_SAVE_SCORE));
    image[A_lives] = image[record + PLAYER_SAVE_LIVES];
    image[A_level_section] = image[record + PLAYER_SAVE_SECTION];
    wr32(image + A_map_ptr, be32(image + record + PLAYER_SAVE_MAP_PTR));
    image[A_powerup_cursor] = image[record + PLAYER_SAVE_POWERUP_CURSOR];
    image[A_weapon_power_level] = image[record + PLAYER_SAVE_WEAPON_LEVEL];
    image[A_ship_speed_level] = image[record + PLAYER_SAVE_SPEED_LEVEL];
}

/* The ship's death, once its explosion has finished. */
static frame_exit frame_player_died(uint8_t *image) {
    unsigned attempt;

    powerup_downgrade_on_death(image);
    image[A_lives] -= 1;
    if (image[A_lives] == 0)
        game_over_screen(image);
    image[A_dying_player_section_index] = image[A_level_section];

    for (attempt = 1; ; attempt++) {
        frame_player_swap(image);
        if (attempt == PLAYER_SWAP_ATTEMPTS)
            return FRAME_EXIT_TITLE;
        if (image[A_lives] == 0)
            continue;
        return image[A_level_section] == image[A_dying_player_section_index]
               ? FRAME_EXIT_RESTART_SECTION : FRAME_EXIT_RELOAD_SECTION;
    }
}

/* The four bytes the turn writes into one record, which both shapes below write identically. */
static void mothership_turn_record(uint8_t *image, uint32_t record) {
    image[record + MOTHERSHIP_TURN_HEADING_OFF] = MOTHERSHIP_TURN_HEADING;
    wr16(image + record + MOTHERSHIP_TURN_SPEED_OFF, MOTHERSHIP_TURN_SPEED);
    image[record + MOTHERSHIP_TURN_FLAG_OFF] = MOTHERSHIP_TURN_FLAG;
    image[record + MOTHERSHIP_TURN_CLEAR_OFF] = 0;
}

/* The mothership's turn at MOTHERSHIP_TURN_FRAME, which is what makes it leave. Motherships below
 * MOTHERSHIP_INDEX_SEGMENTED own two adjacent enemy records; the rest own four records two apart,
 * and only the live ones are turned. */
static void frame_mothership_turns(uint8_t *image) {
    uint32_t record = A_enemy_slots;
    unsigned pair;

    if ((int8_t)image[A_mothership_index] < MOTHERSHIP_INDEX_SEGMENTED) {
        unsigned half;

        for (half = 0; half < MOTHERSHIP_TAIL_ADJACENT; half++)
            mothership_turn_record(image, addr_add(record, ENTITY_STRIDE * half));
        return;
    }
    for (pair = 0; pair < MOTHERSHIP_TAIL_PAIRS;
         pair++, record = addr_add(record, MOTHERSHIP_PAIR_BYTES)) {
        if (image[record + ENTITY_ALIVE] == 0)
            continue;
        mothership_turn_record(image, record);
    }
}

/* Are all eight enemy slots empty? Two such sweeps in a row end a late section early. */
static unsigned frame_enemy_slots_all_clear(const uint8_t *image) {
    uint32_t enemy = A_enemy_slots;
    unsigned slot;

    for (slot = 0; slot < ENEMY_SLOT_COUNT; slot++, enemy = next_record(enemy))
        if (image[enemy + ENTITY_ALIVE])
            return 0;
    return 1;
}

/* The section-end tests at 0x1285e. Returns FRAME_EXIT_NEXT_FRAME when none of them fired, which
 * sends the caller on to the grace counter and the next frame. */
static frame_exit frame_section_end_tests(uint8_t *image) {
    if (image[A_mothership_ready]) {
        if (be32(image + A_mothership_phase_timer) == MOTHERSHIP_TURN_FRAME)
            frame_mothership_turns(image);
        if (image[A_explosion_group_active_bits] & (1u << EXPLOSION_BIT_SHIP_DEATH))
            return FRAME_EXIT_NEXT_FRAME;
        if ((int8_t)image[A_mothership_index] >= MOTHERSHIP_INDEX_SEGMENTED
            && frame_enemy_slots_all_clear(image)) {
            image[A_mothership_wave_clear_count] += 1;
            if (image[A_mothership_wave_clear_count] == MOTHERSHIP_WAVE_CLEARS_TO_END)
                return FRAME_EXIT_ADVANCE_SECTION;
        }
    }
    /* `st`/`sf` on a byte nothing in the image ever reads; transcribed because the stores are in
     * the diff. */
    image[A_unused_section_end_flag] = 0xff;
    if (be32(image + A_mothership_phase_timer) == MOTHERSHIP_LEAVE_FRAME)
        return FRAME_EXIT_ADVANCE_SECTION;
    if (image[A_mothership_offscreen])
        return FRAME_EXIT_ADVANCE_SECTION;
    image[A_unused_section_end_flag] = 0;
    return FRAME_EXIT_NEXT_FRAME;
}

frame_exit frame_resolve_hits_and_game_state(uint8_t *image, uint32_t sound_channel) {
    uint32_t groups_done;

    if (image[A_boss_sequence_active] == 0)
        sound_channel = frame_enemy_shots_absorb(image, ENEMY_SHOT_TOP_SLOT);
    frame_bombs_update(image, sound_channel);
    frame_seeker_lock(image);
    frame_ship_collision(image);
    frame_player_shots_resolve(image);
    /* The projectile pass leaves its own loop counter behind, and it always runs all six passes. */
    sound_channel = PLAYER_SHOT_SLOTS;

    image[A_explosion_phase_even] = (uint8_t)~image[A_explosion_phase_even];
    if (image[A_explosion_phase_even] == 0)
        sound_channel = frame_explosion_animate(image, EXPLOSION_PART_TYPE,
                                                A_explosion_small_frame_ptrs, 0, sound_channel);
    if (image[A_explosion_phase_odd] == 0)
        sound_channel = frame_explosion_animate(image, EXPLOSION_TYPE_LARGE,
                                                A_explosion_large_frame_ptrs, 1, sound_channel);

    /* The shoot pass below does not read this register: it makes its own (see its
     * comment), which is why the stage's carried channel ends here. */
    (void)frame_enemy_rams_ship(image, sound_channel);
    frame_player_shots_hit_enemies(image);
    frame_enemy_shots_ground(image);
    frame_starfield(image);

    frame_decay_timer(image, A_shield_decay_timer, A_shield_level, 0, 1);
    frame_decay_timer(image, A_weapon_decay_timer, A_weapon_power_level,
                      WEAPON_POWER_LEVEL_MIN, 0);
    frame_decay_timer(image, A_speed_decay_timer, A_ship_speed_level, 0, 0);

    frame_scroll_step(image);
    frame_end_and_flip(image);

    groups_done = frame_finished_explosion_groups(image);
    if (groups_done & (1u << EXPLOSION_BIT_SHIP_DEATH))
        return frame_player_died(image);
    if (groups_done & (1u << EXPLOSION_BIT_SECTION_END)) {
        image[A_section_end_delay_counter] -= 1;
        if (image[A_section_end_delay_counter] == 0)
            return FRAME_EXIT_ADVANCE_SECTION;
    } else {
        frame_exit ended = frame_section_end_tests(image);

        if (ended != FRAME_EXIT_NEXT_FRAME)
            return ended;
    }

    /* The post-restart grace counter, which every path but the four exits above runs down. */
    image[A_enemy_seeker_cooldown] -= 1;
    if ((int8_t)image[A_enemy_seeker_cooldown] < 0)
        image[A_enemy_seeker_cooldown] = 0;
    return FRAME_EXIT_NEXT_FRAME;
}

/* ================================================================================================
 * frame_loop_once — the five slices in order, which is the whole of 0x10f4e..0x1296a.
 * ============================================================================================= */
frame_exit frame_loop_once(uint8_t *image, uint32_t chance_index_register,
                           uint32_t ground_spawn_y_register) {
    if (frame_panel_scroll_and_ship_stage(image))
        frame_drone_and_fire_stage(image, A_player_record, image[A_joystick_state]);
    frame_spawn_and_move_stage(image, chance_index_register, ground_spawn_y_register);
    frame_draw_objects_and_collide(image);
    /* D0 comes out of the stage above as ENTITY_SLOTS: its outer sweep runs `d0` from 1 up to that
     * bound and leaves it there (`cmp.l #$14,d0` + `bne`). */
    return frame_resolve_hits_and_game_state(image, ENTITY_SLOTS);
}

/* ================================================================================================
 * Glue.
 *
 * Register maps. `frame_panel_scroll_and_ship_stage` and `frame_draw_objects_and_collide` take no
 * register inputs at all — every address they touch is absolute. `frame_drone_and_fire_stage` takes
 * A2 and D0, the ship record and the joystick byte the stage above left. `frame_spawn_and_move_stage`
 * takes D1 and D7, the two registers include/frame.h's header comment describes.
 * `frame_resolve_hits_and_game_state` takes D0, which is the channel `sound_start` uses
 * until the stage's own instructions reload it.
 *
 * THREE OF THE SIX ANSWER WITH WHICH ADDRESS THEY LEFT THROUGH, and that is not a register the
 * original carries — it is the `bra` target itself. So the answer comes back as the glue's own
 * return value (`harness.differential`'s `info["ret"]`) rather than being stored into the image:
 * the oracle publishes the same fact by WHERE it stopped, so a case compares the two and no
 * scratch longword has to be excluded from the byte diff. */
uint32_t g_frame_panel_scroll_and_ship_stage(uint8_t *image) {
    return frame_panel_scroll_and_ship_stage(image);
}

void g_frame_drone_and_fire_stage(uint8_t *image, uint32_t ship, uint32_t joystick) {
    frame_drone_and_fire_stage(image, ship, (uint8_t)joystick);
}

void g_frame_spawn_and_move_stage(uint8_t *image, uint32_t chance_index_register,
                                  uint32_t ground_spawn_y_register) {
    frame_spawn_and_move_stage(image, chance_index_register, ground_spawn_y_register);
}

void g_frame_draw_objects_and_collide(uint8_t *image) {
    frame_draw_objects_and_collide(image);
}

uint32_t g_frame_resolve_hits_and_game_state(uint8_t *image, uint32_t sound_channel) {
    return (uint32_t)frame_resolve_hits_and_game_state(image, sound_channel);
}

uint32_t g_frame_loop_once(uint8_t *image, uint32_t chance_index_register,
                           uint32_t ground_spawn_y_register) {
    return (uint32_t)frame_loop_once(image, chance_index_register, ground_spawn_y_register);
}

/* ================================================================================================
 * TEMPORARY until src/highscore.c's `game_over_screen` lands — include/frame.h's block of the same
 * name says why, and the orchestrator deletes both halves at merge.
 * ============================================================================================= */
#ifndef ZYNAPS_HIGHSCORE_HAS_GAME_OVER
void game_over_screen(uint8_t *image) {
    (void)image;
    /* NOT a silent no-op: the routine draws a whole screen, so a run that reached it and came back
     * having drawn nothing would differ against the oracle on tens of thousands of bytes — or, in a
     * target build, look fine and be wrong. The tally is this project's own way of saying "this
     * case tested nothing": `harness.differential` throws the run away by name. */
    os_refused(0);
}
#endif
