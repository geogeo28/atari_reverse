/* player.c — Joust's player-control layer: what a joystick does to a rider, and what happens to a
 * rider that dies.
 *
 * read_joysticks (0x11d9a, blocked — see src/input.c) calls control_player twice a frame, once per
 * player, with the object slot in A0 and that player's joystick byte in D0. Three shapes come out
 * of it: an EMPTY slot, where the fire button is the "insert coin" of the game-over screen; a LIVE
 * rider, where the stick sets the speed the physics pass will ease it towards; and a DEAD one,
 * whose corpse hovers under its own wingbeats until it drifts off the end of the playfield and
 * player_death takes its next life away.
 *
 * TWO THINGS HERE ARE NOT PLAIN FUNCTION RETURNS, and both are handled the way src/input.c handles
 * its quit and restart exits: the C reports the branch through its return value, and the
 * differential diffs the original at a checkpoint PC instead of at `rts`.
 *
 *   * control_player's no-players-left path drops TWO return addresses (`addq.w #8,a7` — its own
 *     and read_joysticks') and restarts the game through check_highscore / init_game / init_video
 *     and a `jmp` into the main loop. All three are unported, so the C stops at the last store
 *     before the first of them and returns CONTROL_RESTART.
 *   * restart_reset_players is the piece of that path that lies BETWEEN two of those calls. It is
 *     reconstructed, but it cannot be called from here yet; see its own comment.
 */
#include "machine.h"

#include "joust.h"
#include "player.h"

/* =================================================================================================
 * player_death @ 0x11f28
 * ============================================================================================= */

/* Fill the first free message slot with one of the three end-of-turn banners.
 *
 * find_free_message hands back 0 when all 24 slots are taken and the original tests nothing, so a
 * full table writes this twelve-byte record over addresses 0..0xb — the bottom of the 68000's
 * vector page. Reproduced rather than guarded.
 *
 * The original spells the screen pointer as a `move.l` of screen_base followed by an `addi.l` to
 * the same word. Folding the two is exact: the intermediate is never read, and no message slot can
 * overlap screen_base (the table runs 0x10e16..0x10f36, and the full-table case writes at 0).
 */
static void post_banner(uint8_t *image, uint32_t dst_off, uint8_t shift, uint8_t colour,
                        uint32_t string) {
    uint32_t message = find_free_message(image);

    wr32(image + message + MSG_SCREEN_PTR, be32(image + A_screen_base) + dst_off);
    wr32(image + message + MSG_STRING, string);
    image[message + MSG_KIND] = MSG_KIND_PERSISTENT;
    image[message + MSG_TIMER] = BANNER_FRAMES;
    image[message + MSG_COLOR] = colour;
    image[message + MSG_SHIFT] = shift;
}

/* Take a life off the rider in `object`, and post whatever banner that leaves owing.
 *
 * The identity test is `cmpa.l #player2 ; bls` — an UNSIGNED compare on the WHOLE pointer, so every
 * slot at or below player 2's takes the losing-a-life path and only the enemy slots above it are
 * simply removed from the table. A pointer one byte under player 2's would be treated as a player.
 */
void player_death(uint8_t *image, uint32_t object) {
    if (object > A_player2) {
        wr16(image + object + OBJ_FLAGS, 0);
        return;
    }

    image[object + OBJ_LIVES]--;
    /* The count is RE-READ rather than branched on the `subq`'s own flags: a count of 0 wraps to
     * LIVES_EXHAUSTED, which is how the turn after the last life is spotted. */
    if (image[object + OBJ_LIVES] != LIVES_EXHAUSTED) {
        /* Forget where the rider was last drawn, so the respawn does not erase a stale sprite. */
        wr32(image + object + OBJ_PREV_DST, 0);
        image[object + OBJ_PREV_ROWS] = 0;
        wr16(image + object + OBJ_VX, 0);

        uint16_t flags = be16(image + object + OBJ_FLAGS);
        flags &= (uint16_t)~(OBJ_FLAG_GRABBED | OBJ_FLAG_DEAD | OBJ_FLAG_IN_LAVA);
        flags |= OBJ_FLAG_RESPAWN;
        wr16(image + object + OBJ_FLAGS, flags);

        /* BOTH rows are repainted, whichever player died: each entry point reloads its own slot
         * from a constant and ignores everything else (see src/score.c). */
        draw_lives_p1(image);
        draw_lives_p2(image);
        return;
    }

    wr16(image + object + OBJ_FLAGS, 0);   /* the slot is done for the rest of the game */
    /* `subq.b #1` on the byte, branching on ITS flags this time: only an exact 1 -> 0 reaches the
     * game-over banner, so a call with nobody already alive wraps to 0xff and posts a per-player
     * banner instead. */
    image[A_players_alive]--;
    if (image[A_players_alive] == 0) {
        post_banner(image, BANNER_GAME_OVER_DST_OFF, BANNER_GAME_OVER_SHIFT,
                    BANNER_COLOR_GAME_OVER, STR_GAME_OVER);
        return;
    }

    /* Which of the two ran out — again a full `cmpa.l`, against player 1's slot this time, so
     * anything that is not exactly player 1 gets player 2's wording and colour. */
    int is_player1 = (object == A_object_table);
    post_banner(image, BANNER_PLAYER_OUT_DST_OFF, BANNER_PLAYER_OUT_SHIFT,
                is_player1 ? BANNER_COLOR_P1 : BANNER_COLOR_P2,
                is_player1 ? STR_PLAYER1_OVER : STR_PLAYER2_OVER);
}

/* =================================================================================================
 * control_player @ 0x11dd6
 * ============================================================================================= */

/* A live rider under the stick: the flap bits follow the fire button, and OBJ_TARGET_VX gets the
 * speed the rider is being asked for.
 *
 * That target is written three times over in the original — the rider's current vx, then 0 if it is
 * still waiting to respawn, then a fixed walk speed if the stick is pushed — and only the last
 * survives. The intermediate stores go to the same word, so computing the value once is exact.
 */
static void steer_rider(uint8_t *image, uint32_t object, uint32_t stick, uint16_t flags) {
    if (stick & STICK_FLAP) flags |= OBJ_FLAGS_FLAPPING;
    else                    flags &= (uint16_t)~OBJ_FLAGS_FLAPPING;

    uint16_t target_vx = be16(image + object + OBJ_VX);
    if (flags & OBJ_FLAG_RESPAWN) target_vx = 0;
    if (stick & STICK_RIGHT)     target_vx = PLAYER_STEER_VX;
    else if (stick & STICK_LEFT) target_vx = (uint16_t)-PLAYER_STEER_VX;

    wr16(image + object + OBJ_TARGET_VX, target_vx);
    wr16(image + object + OBJ_FLAGS, flags);
}

/* Has a dead rider's drift finally carried it off the playfield? See DEAD_EXIT_* in player.h for
 * why the two facings are not measured the same way. */
static int dead_rider_has_left(uint16_t flags, int16_t x) {
    if (flags & OBJ_FLAG_FACING_RIGHT) return x >= DEAD_EXIT_RIGHT_X;
    return x >= DEAD_EXIT_LEFT_LO && x <= DEAD_EXIT_LEFT_HI;
}

static uint16_t hover_target_y(int16_t y) {
    if (y <= HOVER_BAND_HIGH_Y) return HOVER_TARGET_HIGH;
    if (y <= HOVER_BAND_MID_Y)  return HOVER_TARGET_MID;
    return HOVER_TARGET_LOW;
}

/* A dead rider still on screen: it keeps drifting the way it already was, at a fixed speed, and
 * beats its wings while it is below the altitude its band asks for and not already falling. The
 * wingbeat is a TOGGLE, one flip per frame, which is what makes the corpse bob. */
static void hover_dead_rider(uint8_t *image, uint32_t object, uint16_t flags) {
    /* `move.w #$4` then `neg.w` on the stored word if vx is negative — so a vx of exactly 0 drifts
     * right (`bge` takes the un-negated path). */
    int16_t drift = (int16_t)be16(image + object + OBJ_VX) < 0 ? -PLAYER_STEER_VX
                                                               : PLAYER_STEER_VX;
    wr16(image + object + OBJ_TARGET_VX, (uint16_t)drift);

    int16_t y = (int16_t)be16(image + object + OBJ_Y);
    uint16_t target_y = hover_target_y(y);
    wr16(image + object + OBJ_TARGET_Y, target_y);

    if (y > (int16_t)target_y && (int16_t)be16(image + object + OBJ_VY) >= 0)
        flags ^= OBJ_FLAGS_FLAPPING;
    else
        flags &= (uint16_t)~OBJ_FLAGS_FLAPPING;
    wr16(image + object + OBJ_FLAGS, flags);
}

/* control_player(object = A0, stick = D0) -> CONTROL_RETURNED or CONTROL_RESTART.
 *
 * `stick` is a longword because the caller hands one over (`move.l d1,d0` for player 2, whose high
 * half is whatever D1 last held); only STICK_FLAP / STICK_RIGHT / STICK_LEFT are ever looked at.
 *
 * The empty-slot path is the game-over screen's only input. With any player still alive the fire
 * button does nothing at all; with none left it restarts the game — and NEVER RETURNS, which is why
 * this function has a result at all. The original drops its own return address AND read_joysticks'
 * (`addq.w #8,a7`), sets game_over_flag, and runs check_highscore, init_game and init_video before
 * jumping into the main loop. All three are unported, so the reconstruction stops after the store
 * that precedes the first of them and reports CONTROL_RESTART; test_player.py diffs the original at
 * that same instruction and separately proves the run really does not reach `rts`.
 */
uint32_t control_player(uint8_t *image, uint32_t object, uint32_t stick) {
    uint16_t flags = be16(image + object + OBJ_FLAGS);

    if (flags == 0) {
        if (!(stick & STICK_FLAP)) return CONTROL_RETURNED;
        if (image[A_players_alive] != 0) return CONTROL_RETURNED;
        image[A_game_over_flag] = GAME_OVER_SET;
        return CONTROL_RESTART;
    }

    if (!(flags & OBJ_FLAG_DEAD)) {
        steer_rider(image, object, stick, flags);
        return CONTROL_RETURNED;
    }

    if (dead_rider_has_left(flags, (int16_t)be16(image + object + OBJ_X))) {
        /* Rub the corpse's last sprite out before the slot is reused. draw_object_mask leaves A0
         * alone, so player_death really does get the same object. */
        draw_object_mask(image, object);
        player_death(image, object);
        return CONTROL_RETURNED;
    }
    hover_dead_rider(image, object, flags);
    return CONTROL_RETURNED;
}

/* control_player's restart tail @ 0x11e50, between init_game and init_video: how many players the
 * new game has, and each of them with a zeroed score display and a fresh set of lives. In a
 * one-player game player 2's slot is emptied instead of being handed anything.
 *
 * NOT CALLED FROM control_player ABOVE, deliberately. check_highscore and init_game sit between the
 * two, and neither is ported — a candidate that ran this would be ahead of an oracle stopped at the
 * first of them, and the checkpoint would fail. It is verified on its own instead, with the oracle
 * entered at 0x11e50 and stopped at the `jsr init_video` that follows. When those two land, the
 * restart path becomes: check_highscore, init_game, this, init_video, jump to the main loop.
 */
static void reset_player_hud(uint8_t *image, uint32_t player) {
    image[player + OBJ_SCORE_LAST_DIGIT] = SCORE_UNITS_ZERO;
    image[player + OBJ_LIVES] = PLAYER_START_LIVES;
}

void restart_reset_players(uint8_t *image) {
    if (image[A_two_player_mode] != 0) {
        image[A_players_alive] = PLAYERS_ALIVE_TWO;
        reset_player_hud(image, A_player2);
    } else {
        wr16(image + A_player2 + OBJ_FLAGS, 0);
        image[A_players_alive] = PLAYERS_ALIVE_ONE;
    }
    reset_player_hud(image, A_object_table);
}

/* ------------------------------------------------------------------------------------- glue ---
 *
 * Both entry points take their arguments in registers (A0, D0) and neither returns anything the
 * original's callers read, so the glue is a bare forwarder. control_player's result is the branch
 * report described above, not a value the game itself produces.
 */

uint32_t g_control_player(uint8_t *image, uint32_t object, uint32_t stick) {
    return control_player(image, object, stick);
}

void g_restart_reset_players(uint8_t *image) {
    restart_reset_players(image);
}

void g_player_death(uint8_t *image, uint32_t object) {
    player_death(image, object);
}
