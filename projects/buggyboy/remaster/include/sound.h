/* sound.h — the REFRESH sound driver's owned state + public API.
 *
 * A native port of recreate/src/sound.c (verified byte-exact against the 68000 under Musashi). The
 * remaster owns the driver state in this struct instead of threading the flat image pointer, and
 * reads the const tables / tune note streams from a baked blob (render/atari/build/sound_data.h,
 * SND_CONST — the shared fixture home) whose
 * offsets are all relative to the original SND_STATE base — so a stream cursor stored in a voice
 * record indexes SND_CONST directly, and an absolute table at Ghidra address A is SND_CONST[A -
 * SND_STATE]. See render/atari/gen_sound_fixture.py for how the blob is baked.
 *
 * The state field *meanings* are only partly reversed, so — exactly as the reference does — the two
 * state regions stay flat byte arrays named by offset+role, not decomposed into distinct C fields:
 * their offsets alias heavily (the PSG staging bytes double as the music header, e.g. SND_VOL_A ==
 * SND_MUSIC_BYTE at 0x07; SND_TUNE_LEN == SND_TEMPO_DIV at 0x24), so distinct fields would misrepresent
 * the layout the driver relies on. Keeping the SAME byte layout as the image also lets the differential
 * (test/test_sound_rm.py) byte-compare the whole state against recreate's image, not just the PSG stream.
 *
 * All multi-byte fields are big-endian (the 68000's order), matching the image and SND_CONST, so the
 * byte layout is identical on both sides of the differential.
 */
#ifndef RM_SOUND_H
#define RM_SOUND_H

#include <stdbool.h>
#include <stdint.h>

/* ---- state block geometry --------------------------------------------------------------------- */
#define SND_STATE_BYTES   0x2a    /* the driver state block (music header + effect voice + PSG staging) */
#define SND_VOICES        3       /* three music voices (PSG channels A/B/C) */
#define SND_VOICE_STRIDE  0x18    /* one voice-control record */

/* ---- SND_STATE field offsets (into SoundState.header) -----------------------------------------
 * SND_STATE[0x00..0x0c] double as the PSG register-staging bytes the frame ends by dumping. */
#define SND_PERIOD_A      0x00    /* word: channel A tone period (regs 1 coarse, 0 fine) */
#define SND_PERIOD_B      0x02    /* word: channel B tone period (regs 3, 2) */
#define SND_PERIOD_C      0x04    /* word: channel C tone period (regs 5, 4) */
#define SND_STATE_R6      0x06    /* reg 6 noise / mixer staging */
#define SND_VOL_A         0x07    /* reg 8 volume A staging (aliases SND_MUSIC_BYTE) */
#define SND_MUSIC_BYTE    0x07    /* music-playing state; TURNOFF/EGOFF clear it (aliases SND_VOL_A) */
#define SND_MUSIC_WORD    0x08    /* word cleared by stop-music */
#define SND_VOL_C         0x09    /* reg 0xa volume C staging */
#define SND_FX_PRE_LO     0x0a    /* effect record word 7 (also reg 0xb env-period staging) */
#define SND_ENV_SHAPE     0x0c    /* reg 0xd envelope shape: emitted only when nonzero, then cleared */
#define SND_FX_PRE_HI     0x0c    /* effect record word 8 (aliases SND_ENV_SHAPE) */
#define SND_FX_CTR        0x0d    /* effect total-duration countdown (low byte of FX_PRE_HI word) */
#define SND_FX_PARAMS     0x0e    /* SND_FX_WORDS-word effect parameter block */
#define SND_FX_FREQ_ADD   0x0e    /* word: per-frame FX frequency increment */
#define SND_FX_FREQ_SET   0x10    /* word: FX frequency reset value */
#define SND_FX_SWEEP      0x12    /* long: pitch-sweep delta (halves swap per rotate state) */
#define SND_FX_FREQ       0x16    /* word: running FX frequency -> channel C period */
#define SND_FX_NOISE      0x17    /* noise value written to reg 6 when the noise gate fires */
#define SND_FX_REREAD     0x18    /* param word re-read into SND_FX_TAIL */
#define SND_FX_NZ_RELOAD  0x18    /* noise-phase reload */
#define SND_FX_SWEEP_GATE 0x19    /* nonzero enables the pitch sweep */
#define SND_FX_SWEEP_ROT  0x1a    /* sweep-direction rotate state */
#define SND_FX_NZ_ROT     0x1b    /* noise-gate rotate state */
#define SND_FX_NZ_TMR     0x1c    /* noise-phase countdown */
#define SND_FX_TAIL       0x1c    /* re-read param word (aliases SND_FX_NZ_TMR) */
#define SND_FX_SWEEP_TMR  0x1d    /* sweep-tick countdown */
#define SND_MUSIC_ON      0x1e    /* music master enable (A_mzflag) */
#define SND_FX_FLAG       0x1f    /* effect active (A_fxflag) */
#define SND_EG_FLAG       0x20    /* envelope generator active (EGFLAG @0x1b07c) */
#define SND_EG_P1         0x21    /* EG pitch parameter (engfreq @0x1b07d) */
#define SND_EG_VOL        0x22    /* EG volume -> volume A (power-on default 0x0e) */
#define SND_EG_PHASE      0x23    /* EG phase counter (decremented by SND_EG_PHASE_DEC/frame) */
#define SND_TUNE_LEN      0x24    /* INITTUNE music-header length (== SND_TEMPO_DIV reload) */
#define SND_TEMPO_DIV     0x24    /* tempo prescaler countdown (aliases SND_TUNE_LEN) */
#define SND_TUNE_PARAM    0x25    /* per-tune byte; doubles as the per-frame tempo increment */
#define SND_TUNE_ON       0x26    /* INITTUNE active flag (== the initial SND_TEMPO_ACC) */
#define SND_TEMPO_ACC     0x26    /* tempo accumulator; a carry advances the note stream */
#define SND_STATE_NOTE    0x27    /* last note - SND_NOTE_SPLIT */
#define SND_STATE_CMD8B   0x28    /* cmd 0x8b target / R6 source */
#define SND_STATE_MVOL    0x29    /* master volume added to each voice (power-on default 0x0f) */

#define SND_TUNE_LEN_VAL  6       /* value INITTUNE writes to the music-header length field */
#define SND_TEMPO_RELOAD  6       /* SND_TEMPO_DIV reload value */

/* ---- voice-control record field offsets (into SoundState.voice[v]) ----------------------------
 * INITTUNE seeds it; the stepper drives it each frame off the note stream. Roles partly reversed. */
#define SND_VC_FLAGS      0x00    /* state/mode bits; INITTUNE writes word => byte0=0, LOOP_CNT=2 */
#define SND_VC_LOOP_CNT   0x01    /* byte index into the loop-point table (cmd 0x85); seeded = 2 */
#define SND_VC_STREAM     0x02    /* word: current note-stream cursor (SND_CONST offset) */
#define SND_VC_LOOP_OFF   0x04    /* word: loop-point table cursor (SND_CONST offset; cmd 0x85) */
#define SND_VC_PORTA_STEP 0x06    /* portamento step (cmd 0x82) */
#define SND_VC_PORTA_LEN  0x07    /* portamento length (cmd 0x82) */
#define SND_VC_GLIDE_ACC  0x08    /* word: glide/portamento accumulator (cleared per note) */
#define SND_VC_TIMER      0x0a    /* note-duration countdown; reloads from SND_VC_DUR */
#define SND_VC_DUR        0x0b    /* note-duration reload value (stream 0xe0..0xff) */
#define SND_VC_NOTE       0x0c    /* current note / glide accumulator */
#define SND_VC_ENV_D      0x0d    /* envelope segment index */
#define SND_VC_ENV_E      0x0e    /* envelope level (decays; high nibble is the volume) */
#define SND_VC_PITCH_F    0x0f    /* pitch field (stream 0xc0..0xdf) */
#define SND_VC_VIB_2X     0x10    /* vibrato depth*2 (cmd 0x86) */
#define SND_VC_VIB_A      0x11    /* vibrato step (cmd 0x86) */
#define SND_VC_VIB_B      0x12    /* vibrato phase / depth (cmd 0x86) */
#define SND_VC_F13        0x13    /* cmd 0x89 target; INITTUNE clears it */
#define SND_VC_ENV_FLG    0x14    /* per-frame control bits (set to 2 for notes >= SND_NOTE_SPLIT) */
#define SND_VC_WAVE       0x15    /* waveform index (stream 0xb0..0xbf via SND_PITCH_TABLE) */
#define SND_VC_WAVE_CUR   0x16    /* working copy of SND_VC_WAVE, latched per note */

#define SND_VC_STATE_VAL  2       /* INITTUNE seeds word@0 with this (=> FLAGS 0, LOOP_CNT 2) */
#define SND_TUNE_STEP     2       /* per-voice advance through the tune word table (addq.b #2) */

/* ---- voice FLAGS (SND_VC_FLAGS) bits ---------------------------------------------------------- */
#define VC_F_BIT0         0x01    /* toggled every cmd-step frame */
#define VC_F_BIT1         0x02    /* cmds 0x87/0x8a/0x8b */
#define VC_F_BIT2         0x04    /* cmds 0x8a/0x8b */
#define VC_F_PORTA        0x08    /* cmd 0x82; enables the pitch glide in cmd-step */
#define VC_F_VIBRATO      0x10    /* cmd 0x86 */
#define VC_F_VIB_DIR      0x20    /* vibrato ramp direction (toggled at the range limits) */
#define VC_F_RETRIG_KEEP  0x30    /* bits preserved when a note re-triggers (andi.b #0x30) */
#define VC_F_GLIDE_EN     0x40
#define VC_F_GLIDE_DOWN   0x80

/* ---- note-stream byte classes + related state constants --------------------------------------- */
#define SND_NOTE_SPLIT    0x54    /* notes >= this set SND_VC_ENV_FLG and SND_STATE_NOTE */
#define SND_CMD_LO        0x80    /* stream bytes < this are notes; 0x80..0x8c are commands */
#define SND_PITCH_LO      0xb0    /* stream bytes >= this are pitch/param sets, not commands */
#define SND_PITCH_MID_LO  0xc0    /* stream 0xc0..0xdf set SND_VC_PITCH_F */
#define SND_PITCH_DUR_LO  0xe0    /* stream 0xe0..0xff set SND_VC_DUR */
#define SND_STREAM_PITCH_BIAS 0x40  /* added to a 0xb0/0xc0-class stream byte -> pitch field / table index */
#define SND_STREAM_DUR_BIAS   0x21  /* added to a 0xe0-class stream byte -> note duration */
#define SND_BYTE_CARRY   0x100    /* carry out of an 8-bit add (bit 8) — the volume/tempo carry gate */

/* ---- cmd-step envelope / period constants ----------------------------------------------------- */
#define SND_MOD_ENV_OFF   0x1a    /* offset into the modulation table for the envelope reload */
#define SND_ENV_STEP      0x10    /* envelope level lives in the high nibble; decays by this/frame */
#define SND_ENV_MAX       0xf0    /* envelope level >= this is inactive (no decay / silent) */

/* ---- EG (envelope generator) constants -------------------------------------------------------- */
#define SND_EG_PHASE_DEC  0x0d    /* EG phase decrement per frame */
#define SND_EG_PERIOD_HI  0x0100  /* high byte of the EG period seed */
#define SND_VOL_ENV_MODE  0x10    /* volume byte value that selects the envelope generator */

/* ---- mixer + PSG dump ------------------------------------------------------------------------- */
#define SND_MIXER_BASE    0xf8    /* reg 7 base: all tone + noise disabled */
#define SND_MIXER_A       0x09    /* per-voice tone+noise enable masks, EOR'd in when the voice's */
#define SND_MIXER_B       0x12    /* ENV_FLG bit0 is set */
#define SND_MIXER_C       0x24
#define SND_REG_ENV_SHAPE 0x0d    /* PSG envelope-shape register (emitted only when shape != 0) */

/* ---- effect / tune record constants ----------------------------------------------------------- */
#define SND_FX_RECORD     0x12    /* per-effect record size (mulu factor) */
#define SND_FX_WORDS      7       /* effect words copied into SND_FX_PARAMS */

/* ---- SND_CONST offsets of the absolute const tables (Ghidra address - SND_STATE) --------------- */
#define SND_PITCH_TABLE_OFF   0x262   /* 0x1b2be: byte table indexed by stream 0xb0..0xbf (via +0x40) */
#define SND_ENV_TABLE_OFF     0x3e4   /* 0x1b440: envelope-segment byte table, indexed by SND_VC_PITCH_F */
#define SND_PERIOD_TABLE_OFF  0x3ea   /* 0x1b446: tone-period word table, indexed by 2*(lfo+note+f13) */
#define SND_TUNE_TAB_B_OFF    0x597   /* 0x1b5f3: per-tune byte parameter */
#define SND_TUNE_TAB_W_OFF    0x598   /* 0x1b5f4: per-tune word parameters (3 per tune, 8-byte stride) */
#define SND_MOD_TABLE_OFF     0x723   /* 0x1b77f: modulation-table base passed to the DSP */
#define SND_FX_TABLE_OFF      0xbfa   /* 0x1bc56: per-effect parameter records */

/* ---- Dosound command-list offsets within SND_DOSOUND (for slice 2) ----------------------------- */
#define SND_DOSOUND_BASE      0x18b78 /* the first Dosound list's image address; offset 0 aliases it */
#define SND_DOSOUND_COLLIDE   0x00    /* 0x18b78: collision / spin-out */
#define SND_DOSOUND_CRASH     0x1a    /* 0x18b92: crash sound */
#define SND_DOSOUND_IDLE      0x2a    /* 0x18ba2: engine idle */
#define SND_DOSOUND_BEEP      0x42    /* 0x18bba: one leg-start countdown beep */
#define SND_DOSOUND_GO        0x52    /* 0x18bca: the final "go" beep */

/* ---- the owned driver state -------------------------------------------------------------------
 * aligned(2): the word fields are read/written through st.h's accessors, which on the m68k build are
 * native uint16_t moves — an odd base address would raise a 68000 address error. An all-byte struct
 * has alignment 1, so pin it even (the generator pins SND_CONST the same way). */
typedef struct {
    uint8_t header[SND_STATE_BYTES];               /* music header + effect voice + PSG staging (SND_*) */
    uint8_t voice[SND_VOICES][SND_VOICE_STRIDE];   /* the three voice-control records (SND_VC_*) */
} __attribute__((aligned(2))) SoundState;

/* Reset the driver to its power-on state (the two nonzero defaults + zeroed voices). */
void rm_sound_reset(SoundState *s);

/* TURNOFF @0x1b268 — stop music: clear the music-active byte/word and mzflag. */
void rm_turnoff(SoundState *s);

/* EGOFF @0x1b252 — stop the envelope generator: clear EGFLAG and the music-active byte. */
void rm_egoff(SoundState *s);

/* INITFX @0x1b560 — load effect `fx_id`'s parameter record into the effect voice state. */
void rm_initfx(SoundState *s, uint32_t fx_id);

/* INITTUNE @0x1b59c — start music track `tune_id`: seed the music header + the three voice records. */
void rm_inittune(SoundState *s, uint32_t tune_id);

/* REFRESH @0x1b086 — one 50 Hz VBL frame. Updates voice/EG/FX state and appends the frame's YM2149
 * (reg, value) writes to regs[]/vals[] (up to `cap`); returns the write count. Touches no hardware —
 * the caller drives the chip from the returned stream (the same seam recreate's g_REFRESH uses). */
uint32_t rm_refresh(SoundState *s, uint8_t *regs, uint8_t *vals, int cap);

/* ---- slice 2: the TRIGGER layer (the game's in-race sound decisions) --------------------------
 *
 * The events / physics / flow slices decide WHEN music and effects start and stop; this is the small
 * set of leaves they call. It owns two more image globals the driver-not-the-state carries — the VBL
 * sound-handler vector (parked at an rts vs pointing at REFRESH) and the "current tune id" the priority
 * guards read — in a SoundDriver wrapper AFTER the byte-compared SoundState, so the slice-1 state
 * compare (test_sound_rm) is untouched while these two are still differentially compared (against image
 * 0x18c0c parked/running and 0x18cfa). The game-over guard is threaded as a parameter (the caller's
 * game_over_flag), matching how the tree threads such guards. REFRESH itself still runs off the VBL
 * (slice 3 maps rm_dosound + the VBL vector to the real XBIOS).
 *
 * VBL REENTRANCY (slice 3): once the VBL pumps rm_refresh, it and these leaves both touch one SoundState.
 * The original stays safe by asm publication ORDER (mzflag cleared first, records rewritten, mzflag set
 * last); -O2 C does not guarantee that, so the slice-3 shell must MASK the VBL around each trigger mutation
 * (a short interrupt-disable window), NOT rely on store ordering. Full write-up in game_main.c's snd TODO. */

/* A_vbl_sound_vec @0x18c0c models a two-state enable: parked at a bare rts (music silent) or pointing
 * at REFRESH (running). The image stores the actual handler address; the differential maps it to this. */
typedef enum { RM_VBL_PARKED = 0, RM_VBL_RUNNING = 1 } RmVblEnable;

/* The owned driver: the byte-compared slice-1 state, plus the two trigger-owned globals appended after
 * it so the slice-1 SoundState byte-compare stays intact. */
typedef struct SoundDriver {
    SoundState state;        /* slice-1 driver state (SND_STATE + the three voice records) */
    uint16_t   vbl_enable;   /* A_vbl_sound_vec: RM_VBL_PARKED (rts) / RM_VBL_RUNNING (REFRESH) */
    uint16_t   cur_tune_id;  /* A_cur_tune_id @0x18cfa: the tune the priority guards test */
} SoundDriver;

/* ---- guard / id constants (recreate events.c / sound.c / highscore.c) ------------------------- */
#define SND_TUNE_PRIORITY   6    /* play_event_tune won't interrupt this tune while music is playing */
#define SND_MARKER_TUNE_MIN 7    /* cur_tune_id >= this bypasses handle_marker's music-playing guard */

/* Dosound side-effect ledger (host .so only): rm_dosound appends the list's image address; slice 3's
 * PRG seam issues the real XBIOS Dosound instead. Resettable, with accessors, mirroring recreate's
 * g_dosound_log — the drive diffs this ordered stream against the oracle's Dosound trap stream. */
void            rm_dosound(uint16_t list_off);   /* logs SND_DOSOUND_BASE + list_off */
void            rm_dosound_reset(void);
uint32_t        rm_dosound_count(void);
const uint32_t *rm_dosound_args(void);

/* play_event_tune @0x11c7a — start music track `tune`, unless game-over or a higher-priority tune is
 * playing. Always re-points the VBL vector at REFRESH first. */
void rm_play_event_tune(SoundDriver *snd, uint32_t tune, bool game_over);

/* handle_marker @0x11cb2 — stop music and start effect `fx_id`, unless game-over or a low-priority
 * tune is protected while music plays. */
void rm_handle_marker(SoundDriver *snd, uint32_t fx_id, bool game_over);

/* stop_music @0x12ec4 — silence the driver (unless game-over): TURNOFF the music state, clear the
 * effect flag + current tune, PARK the VBL vector, then Dosound the given SND_DOSOUND_* list. */
void rm_stop_music(SoundDriver *snd, uint16_t list_off, bool game_over);

/* stop_music_chk @0x12ebc — stop_music, but only when no music is playing (mzflag == 0). */
void rm_stop_music_chk(SoundDriver *snd, uint16_t list_off, bool game_over);

/* game_update §1's engine-sound enable (recreate game_update.c:252-258): while the buggy is under the
 * player's control (not game-over / not a crash phase 1 / not mid-tally), a stopped buggy silences the
 * envelope generator via stop_music_chk(idle) and a moving one arms it (EG_FLAG + REFRESH); otherwise
 * EGOFF. The `rev_reload` poke the original pairs with the idle case aliases lean_frame (no compared
 * surface reads it) and stays skipped, as everywhere in the tree. */
void rm_sound_engine_update(SoundDriver *snd, uint16_t speed, int16_t crash_phase,
                            uint16_t crash_frame, bool game_over);

/* "Is a tune still playing?" — the flow's terminal jingle waits (mzflag spins: highscore.c @0x25bc /
 * game_over @0x2406) are slice-3 SHELL seams; the host driver never busy-waits. This query is what the
 * shell polls on-target to know when a jingle has finished: it returns header[SND_MUSIC_ON] != 0, so a
 * false result (header[SND_MUSIC_ON] == 0) means the music has finished and the wait may break. */
bool rm_sound_music_on(const SoundDriver *snd);

#endif /* RM_SOUND_H */
