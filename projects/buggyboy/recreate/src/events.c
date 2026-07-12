/* events.c — course-event engine: the handlers the event jump-table dispatches to.
 *
 * Each event reads the roadside-object type in D6 (and slot in D5) and updates game state:
 * flag-gate sequence + bonus scoring, collision penalty, conditional score message, tune/effect
 * triggers. Scoring reuses the verified add_score; tune/effect starts reuse the sound leaves
 * (play_event_tune -> INITTUNE, handle_marker -> TURNOFF/INITFX).
 */
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

/* collision penalty */
#define COLLISION_RPM_DROP 0x11    /* engine_rpm cut per collision */
#define COLLISION_RPM_MIN  0x0f    /* floored here */
#define SPEED_PER_RPM      3       /* speed = (rpm - min) * 3 */

/* flag-gate sequence */
#define FLAG_SEQ_TARGET    5       /* correct flags in a row for the bonus */
#define FLAG_BONUS_FRAMES  0x3c    /* bonus window (frames) written to bonus_timer */
#define FLAG_TUNE_BONUS    6       /* tune played on the bonus */
#define FLAG_TUNE_NORMAL   7       /* tune played otherwise */

/* tune / effect selection */
#define TUNE_SCORE_MSG     8       /* evt_score_msg tune */
#define TUNE_PRIORITY      6       /* play_event_tune won't interrupt this tune while MZFLAG set */
#define MARKER_TUNE_MIN    7       /* cur_tune_id >= this bypasses the MZFLAG guard in handle_marker */

/* evt_collision @0x11c2c — collision penalty: drop engine_rpm (floored) and recompute speed. */
void g_evt_collision(uint8_t *image) {
    if (be16(image + A_collision_lock) != 0) return;
    int16_t rpm = (int16_t)(uint16_t)be16(image + A_engine_rpm) - COLLISION_RPM_DROP;
    if (rpm < COLLISION_RPM_MIN) rpm = COLLISION_RPM_MIN;
    wr16(image + A_engine_rpm, (uint16_t)rpm);
    wr16(image + A_speed, (uint16_t)((rpm - COLLISION_RPM_MIN) * SPEED_PER_RPM));
}

/* play_event_tune @0x11c7a — start music track `tune`, unless game-over or a higher-priority
 * tune is already playing. Always re-points the VBL sound vector at REFRESH first. */
void g_play_event_tune(uint8_t *image, uint32_t tune) {
    if (be16(image + A_game_over_flag) != 0) return;
    wr32(image + A_vbl_sound_vec, A_refresh);
    if (be16(image + A_cur_tune_id) == TUNE_PRIORITY && image[A_mzflag] != 0) return;
    image[A_fxflag] = 0;
    wr16(image + A_cur_tune_id, (uint16_t)tune);
    g_INITTUNE(image, tune);
}

/* evt_flag_gate @0x11ba4 — match roadside-object type D6 against the expected sequence; award a
 * bonus for FLAG_SEQ_TARGET in a row, else a normal gate score. D5 = object slot. */
void g_evt_flag_gate(uint8_t *image, uint32_t slot, uint32_t obj_type) {
    uint16_t seq_count = be16(image + A_flag_seq_count);
    uint32_t expected = A_flag_seq_table + be16(image + A_flag_seq_off);
    int match = be16(image + A_bonus_timer) != 0 ||
                image[expected + seq_count] == (uint8_t)obj_type;

    uint32_t delta = A_score_delta_gate;
    uint16_t tune = FLAG_TUNE_NORMAL;
    if (match) {
        seq_count += 1;
        wr16(image + A_flag_seq_count, seq_count);
        if (seq_count == FLAG_SEQ_TARGET) {
            wr16(image + A_bonus_timer, FLAG_BONUS_FRAMES);
            delta = A_score_delta_bonus;
            tune = FLAG_TUNE_BONUS;
        } else if (seq_count > FLAG_SEQ_TARGET) {
            wr16(image + A_flag_seq_count, 1);          /* wrap past the window */
        }
    }
    g_add_score(image, delta);
    image[A_obj_active + (uint16_t)slot + 1] = 0;       /* clear the object's active flag */
    g_play_event_tune(image, tune);
}

/* evt_score_msg @0x11c5a — award a score message when both object-type flags are set, then play
 * its tune (falls straight into play_event_tune with tune 8). D6/D7 = object-type flags. */
void g_evt_score_msg(uint8_t *image, uint32_t d6, uint32_t d7) {
    if ((uint16_t)d7 == 0 || (uint16_t)d6 == 0) return;
    g_add_score(image, A_score_delta_msg);
    g_play_event_tune(image, TUNE_SCORE_MSG);
}

/* handle_marker @0x11cb2 — checkpoint marker: stop music and start effect D0, unless game-over
 * or a low-priority tune is protected by MZFLAG. */
void g_handle_marker(uint8_t *image, uint32_t fx_id) {
    if (be16(image + A_game_over_flag) != 0) return;
    if ((int16_t)(uint16_t)be16(image + A_cur_tune_id) < MARKER_TUNE_MIN && image[A_mzflag] != 0)
        return;
    g_TURNOFF(image);
    g_INITFX(image, fx_id);
}