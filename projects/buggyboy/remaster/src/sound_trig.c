/* sound_trig.c — the in-race sound TRIGGER layer (slice 2).
 *
 * The events / physics / flow slices decide WHEN music and effects start and stop; this is the small
 * set of leaves they call — a native port of recreate's play_event_tune (@0x11c7a) / handle_marker
 * (@0x11cb2) / stop_music (@0x12ec4) / stop_music_chk (@0x12ebc) plus game_update §1's engine-sound
 * enable. They drive the slice-1 REFRESH core (rm_inittune / rm_initfx / rm_turnoff / rm_egoff) and own
 * two more image globals the driver-not-the-state carries: the VBL sound-handler vector (parked at an
 * rts vs pointing at REFRESH) and the current tune id the priority guards read — both in the SoundDriver
 * wrapper AFTER the byte-compared SoundState (see sound.h).
 *
 * The mzflag / fxflag the guards read are SoundState header bytes (SND_MUSIC_ON / SND_FX_FLAG); the
 * game-over guard is threaded as a parameter (the caller's game_over_flag). Nothing here touches
 * hardware: rm_dosound logs to a host-side ledger (the drive diffs it against the oracle's Dosound trap
 * stream), and the VBL vector is a two-state enable — slice 3 maps both to the real XBIOS.
 */
#include "sound.h"

/* ---- Dosound side-effect ledger (host .so only) ---------------------------------------------- */

#define RM_DOSOUND_LOG_MAX 256

static uint32_t rm_dosound_log[RM_DOSOUND_LOG_MAX];
static uint32_t rm_dosound_log_n;

void            rm_dosound_reset(void) { rm_dosound_log_n = 0; }
uint32_t        rm_dosound_count(void) { return rm_dosound_log_n; }
const uint32_t *rm_dosound_args(void)  { return rm_dosound_log; }

/* Log the list's image address (SND_DOSOUND_BASE + the SND_DOSOUND_* offset) so the ledger diff can
 * compare directly against the oracle's Dosound trap A0 (both Ghidra image addresses). */
void rm_dosound(uint16_t list_off) {
    if (rm_dosound_log_n < RM_DOSOUND_LOG_MAX)
        rm_dosound_log[rm_dosound_log_n++] = SND_DOSOUND_BASE + list_off;
}

/* ---- the trigger leaves -------------------------------------------------------------------------- */

void rm_play_event_tune(SoundDriver *snd, uint32_t tune, bool game_over) {
    if (game_over) return;
    snd->vbl_enable = RM_VBL_RUNNING;                          /* always re-point at REFRESH first */
    if (snd->cur_tune_id == SND_TUNE_PRIORITY && snd->state.header[SND_MUSIC_ON]) return;
    snd->state.header[SND_FX_FLAG] = 0;
    snd->cur_tune_id = (uint16_t)tune;
    rm_inittune(&snd->state, tune);
}

void rm_handle_marker(SoundDriver *snd, uint32_t fx_id, bool game_over) {
    if (game_over) return;
    if ((int16_t)snd->cur_tune_id < SND_MARKER_TUNE_MIN && snd->state.header[SND_MUSIC_ON]) return;
    rm_turnoff(&snd->state);
    rm_initfx(&snd->state, fx_id);
}

void rm_stop_music(SoundDriver *snd, uint16_t list_off, bool game_over) {
    if (game_over) return;
    rm_turnoff(&snd->state);
    snd->state.header[SND_FX_FLAG] = 0;
    snd->cur_tune_id = 0;
    snd->vbl_enable = RM_VBL_PARKED;                           /* park the VBL handler at a bare rts */
    rm_dosound(list_off);                                      /* XBIOS Dosound(A0): hardware-only */
}

void rm_stop_music_chk(SoundDriver *snd, uint16_t list_off, bool game_over) {
    if (snd->state.header[SND_MUSIC_ON]) return;               /* only when no music is playing */
    rm_stop_music(snd, list_off, game_over);
}

void rm_sound_engine_update(SoundDriver *snd, uint16_t speed, int16_t crash_phase,
                            uint16_t crash_frame, bool game_over) {
    if (!game_over && crash_phase >= 0 && crash_phase != 1 && crash_frame == 0) {
        if (speed == 0)
            rm_stop_music_chk(snd, SND_DOSOUND_IDLE, game_over);   /* stopped: engine idle (rev_reload skipped) */
        else {
            snd->state.header[SND_EG_FLAG] = 1;                    /* moving: arm the engine EG */
            snd->vbl_enable = RM_VBL_RUNNING;
        }
    } else {
        rm_egoff(&snd->state);
    }
}

bool rm_sound_music_on(const SoundDriver *snd) {
    return snd->state.header[SND_MUSIC_ON] != 0;
}
