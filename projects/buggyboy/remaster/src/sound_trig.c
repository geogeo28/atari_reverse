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

/* ---- Dosound side-effect ledger (host .so only) ----------------------------------------------
 * On the m68k PRG (RM_SOUND_TARGET) rm_dosound is instead the REAL XBIOS Dosound over the baked
 * command-list blob — the shell provides it in game_main.c, so this host ledger (the differential's
 * observable) is compiled out there. The host/bench builds leave RM_SOUND_TARGET undefined and keep
 * the ledger, so test_sound_trig's Dosound diff is unchanged. */
#ifndef RM_SOUND_TARGET

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

#endif /* !RM_SOUND_TARGET */

/* ---- the trigger leaves -------------------------------------------------------------------------- */

/* No lock here: the priority guard runs first (a clean early return), and the only multi-store publish
 * is rm_inittune, which brackets itself (sound.c). The single stores around it — vbl_enable, the fxflag
 * byte, cur_tune_id (the pump never reads it) — are each atomic w.r.t. the VBL on their own. */
void rm_play_event_tune(SoundDriver *snd, uint32_t tune, bool game_over) {
    if (game_over) return;
    snd->vbl_enable = RM_VBL_RUNNING;                          /* always re-point at REFRESH first */
    if (snd->cur_tune_id == SND_TUNE_PRIORITY && snd->state.header[SND_MUSIC_ON]) return;
    snd->state.header[SND_FX_FLAG] = 0;
    snd->cur_tune_id = (uint16_t)tune;
    rm_inittune(&snd->state, tune);
}

/* rm_turnoff then rm_initfx each self-bracket (sound.c); between them the state is consistent (music off,
 * the prior fx record intact), so no outer bracket is needed. */
void rm_handle_marker(SoundDriver *snd, uint32_t fx_id, bool game_over) {
    if (game_over) return;
    if ((int16_t)snd->cur_tune_id < SND_MARKER_TUNE_MIN && snd->state.header[SND_MUSIC_ON]) return;
    rm_turnoff(&snd->state);
    rm_initfx(&snd->state, fx_id);
}

/* This ONE leaf still needs its own bracket: TURNOFF -> clear fxflag -> clear tune -> PARK must publish
 * as a unit, so the pump can't refresh one more frame with the tune half-torn down after PARK is meant.
 * (rm_turnoff self-brackets too; the nesting counter makes that inner lock harmless — see sound.h.) */
void rm_stop_music(SoundDriver *snd, uint16_t list_off, bool game_over) {
    if (game_over) return;
    RM_SOUND_LOCK();
    rm_turnoff(&snd->state);
    snd->state.header[SND_FX_FLAG] = 0;
    snd->cur_tune_id = 0;
    snd->vbl_enable = RM_VBL_PARKED;                           /* park the VBL handler at a bare rts */
    RM_SOUND_UNLOCK();
    rm_dosound(list_off);          /* XBIOS Dosound(A0) on target / ledger on host — no SoundState touch */
}

void rm_stop_music_chk(SoundDriver *snd, uint16_t list_off, bool game_over) {
    if (snd->state.header[SND_MUSIC_ON]) return;               /* only when no music is playing */
    rm_stop_music(snd, list_off, game_over);
}

/* Silence for the Help-key pause: keep the pump RUNNING (pointed at REFRESH) but stop music, the envelope
 * generator and any effect. Bracketed as a unit — like rm_stop_music, the whole tear-down must publish
 * atomically so the VBL pump never refreshes a half-silenced record (rm_turnoff / rm_egoff self-bracket
 * too; the nesting counter makes those inner locks harmless — see sound.h). No PARK, no Dosound. */
void rm_pause_silence(SoundDriver *snd) {
    RM_SOUND_LOCK();
    snd->vbl_enable = RM_VBL_RUNNING;              /* vbl_sound_vec = &REFRESH (0x2ac) */
    rm_turnoff(&snd->state);                       /* TURNOFF (0x2b8): mzflag + music bytes off */
    rm_egoff(&snd->state);                         /* EGOFF (0x2be): envelope generator off */
    snd->state.header[SND_FX_FLAG] = 0;            /* FXFLAG = 0 (0x2c4) */
    RM_SOUND_UNLOCK();
}

bool rm_sound_engine_update(SoundDriver *snd, uint16_t speed, int16_t crash_phase,
                            uint16_t crash_frame, bool game_over) {
    if (!game_over && crash_phase >= 0 && crash_phase != 1 && crash_frame == 0) {
        if (speed == 0) {
            rm_stop_music_chk(snd, SND_DOSOUND_IDLE, game_over);   /* stopped: engine idle */
            return true;                                           /* ...and the rev_reload poke fires */
        } else {
            snd->state.header[SND_EG_FLAG] = 1;                    /* moving: arm the engine EG (atomic store) */
            snd->vbl_enable = RM_VBL_RUNNING;                      /* atomic store; no torn multi-store here */
        }
    } else {
        rm_egoff(&snd->state);                                    /* self-brackets its two stores (sound.c) */
    }
    return false;
}

bool rm_sound_music_on(const SoundDriver *snd) {
    return snd->state.header[SND_MUSIC_ON] != 0;
}
