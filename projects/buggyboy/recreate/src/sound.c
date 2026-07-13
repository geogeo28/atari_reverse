/* sound.c — sound-driver leaves used by the course-event engine.
 *
 * TURNOFF/INITFX/INITTUNE set up the driver's per-voice music/effect state (the block at
 * SND_STATE and the voice-control records at SND_VOICE_CTRL) from const parameter tables. The
 * block's individual field *meanings* are only partly reversed, so its fields are named by
 * offset+role; the differential test against the oracle is what guarantees the reconstruction is
 * exact. These routines are pure (no OS traps, no further calls) — the driver runs from the VBL.
 */
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

#define SND_STATE      0x1b05c   /* driver state block (music header + effect voice) */
#define SND_FX_TABLE   0x1bc56   /* const: per-effect parameter records */
#define SND_TUNE_TAB_B 0x1b5f3   /* const: per-tune byte parameter */
#define SND_TUNE_TAB_W 0x1b5f4   /* const: per-tune word parameters (3 per tune) */
#define SND_VOICE_CTRL 0x1b64a   /* three voice-control records */

/* SND_STATE field offsets (A_mzflag / A_fxflag are the same block at +0x1e / +0x1f). */
#define SND_MUSIC_BYTE 0x07      /* TURNOFF/EGOFF clear this (music-playing state; DAT_0001b063) */
#define SND_MUSIC_WORD 0x08
#define SND_EG_FLAG    0x20      /* EGOFF clears this (envelope-generator active; 0x1b07c) */
#define SND_FX_PRE_LO  0x0a      /* two words below the effect params (record words 7,8) */
#define SND_FX_PRE_HI  0x0c
#define SND_FX_PARAMS  0x0e      /* SND_FX_WORDS-word effect parameter block */
#define SND_FX_REREAD  0x18      /* param word re-read into SND_FX_TAIL */
#define SND_FX_TAIL    0x1c
#define SND_TUNE_LEN   0x24      /* INITTUNE music header: length (=SND_TUNE_LEN_VAL) */
#define SND_TUNE_PARAM 0x25      /*                        per-tune byte */
#define SND_TUNE_ON    0x26      /*                        active flag (=0xff) */

#define SND_FX_RECORD  0x12      /* per-effect record size (mulu factor) */
#define SND_FX_WORDS   7         /* effect words copied into SND_FX_PARAMS */
#define SND_TUNE_LEN_VAL 6       /* value written to the music-header length field */

/* Voice-control record (3 records at SND_VOICE_CTRL, stride SND_VOICE_STRIDE). INITTUNE seeds
 * it; snd_voice_step drives it each frame off the note stream. Field roles are only partly
 * reversed, so they are named by offset+observed role; the differential test is the guarantee. */
#define SND_VOICES        3
#define SND_VOICE_STRIDE  0x18
#define SND_VC_FLAGS   0x00      /* state/mode bits (glide/vibrato/…); INITTUNE writes word => byte0=0 */
#define SND_VC_LOOP_CNT 0x01     /* byte index into the loop-point table (cmd 0x85); INITTUNE seeds =2 */
#define SND_VC_STREAM  0x02      /* word: current note-stream offset (relative to SND_STATE) */
#define SND_VC_LOOP_OFF 0x04     /* word: loop-point table offset relative to SND_STATE (cmd 0x85) */
#define SND_VC_PORTA_STEP 0x06   /* portamento step (cmd 0x82) */
#define SND_VC_PORTA_LEN  0x07   /* portamento length (cmd 0x82) */
#define SND_VC_GLIDE_ACC 0x08    /* word: glide/portamento accumulator (cleared per note) */
#define SND_VC_TIMER   0x0a      /* note-duration countdown (per frame); reloads from SND_VC_DUR */
#define SND_VC_DUR     0x0b      /* note-duration reload value (stream 0xe0..0xff) */
#define SND_VC_NOTE    0x0c      /* current note / glide accumulator */
#define SND_VC_ENV_D   0x0d
#define SND_VC_ENV_E   0x0e
#define SND_VC_PITCH_F 0x0f      /* pitch field (stream 0xc0..0xdf) */
#define SND_VC_VIB_2X  0x10      /* vibrato depth*2 (cmd 0x86) */
#define SND_VC_VIB_A   0x11      /* vibrato param (cmd 0x86) */
#define SND_VC_VIB_B   0x12      /* vibrato depth (cmd 0x86) */
#define SND_VC_F13     0x13      /* cmd 0x89 target; INITTUNE clears it */
#define SND_VC_ENV_FLG 0x14      /* set to 2 for notes >= SND_NOTE_SPLIT */
#define SND_VC_WAVE    0x15      /* waveform index (stream 0xb0..0xbf, via SND_PITCH_TABLE) */
#define SND_VC_WAVE_CUR 0x16     /* working copy of SND_VC_WAVE, latched per note */
#define SND_VC_STATE_VAL  2      /* INITTUNE seeds the word@0 with this (=> flags 0, loop_cnt 2) */
#define SND_TUNE_STEP     2      /* per-voice advance through the tune word table (addq.b #2) */

/* snd_voice flag bits (SND_VC_FLAGS). */
#define VC_F_BIT0        0x01    /* toggled every cmd_handler frame */
#define VC_F_BIT1        0x02    /* cmds 0x87/0x8a/0x8b */
#define VC_F_BIT2        0x04    /* cmds 0x8a/0x8b */
#define VC_F_PORTA       0x08    /* cmd 0x82; enables the pitch glide in cmd_handler */
#define VC_F_VIBRATO     0x10    /* cmd 0x86 */
#define VC_F_VIB_DIR     0x20    /* vibrato ramp direction (toggled at the range limits) */
#define VC_F_RETRIG_KEEP 0x30    /* bits preserved when a note re-triggers (andi.b #0x30) */
#define VC_F_GLIDE_EN    0x40
#define VC_F_GLIDE_DOWN  0x80

/* snd_voice stream/table constants. */
#define SND_PITCH_TABLE  0x1b2be /* byte table indexed by stream 0xb0..0xbf (via +0x40) */
#define SND_STATE_R6     0x06    /* SND_STATE[0x06] (0x1b062): PSG noise/mixer staging */
#define SND_STATE_NOTE   0x27    /* SND_STATE[0x27] (0x1b083): last note - SND_NOTE_SPLIT */
#define SND_STATE_CMD8B  0x28    /* SND_STATE[0x28] (0x1b084): cmd 0x8b target / R6 source */
#define SND_STATE_MVOL   0x29    /* SND_STATE[0x29] (0x1b085): master volume added to each voice */
#define SND_NOTE_SPLIT   0x54    /* notes >= this set SND_VC_ENV_FLG and SND_STATE_NOTE */
#define SND_CMD_LO       0x80    /* stream bytes < this are notes; 0x80..0x8c are commands */
#define SND_PITCH_LO     0xb0    /* stream bytes >= this are pitch/param sets, not commands */
#define SND_PITCH_MID_LO 0xc0    /* stream 0xc0..0xdf set SND_VC_PITCH_F */
#define SND_PITCH_DUR_LO 0xe0    /* stream 0xe0..0xff set SND_VC_DUR */

/* snd_cmd_handler tables (byte/word LUTs baked into the driver image). */
#define SND_ENV_TABLE    0x1b440 /* envelope-segment byte table, indexed by SND_VC_PITCH_F */
#define SND_PERIOD_TABLE 0x1b446 /* tone-period word table, indexed by 2*(lfo+note+f13) */
#define SND_MOD_ENV_OFF  0x1a    /* offset into the A1 modulation table for the envelope reload */
#define SND_ENV_STEP     0x10    /* envelope level lives in the high nibble; decays by this/frame */
#define SND_ENV_MAX      0xf0    /* envelope level >= this is inactive (no decay / silent) */

/* REFRESH (@0x1b086) — the 50 Hz VBL orchestrator. SND_STATE fields it drives beyond the voice
 * records; roles are partly reversed (named by offset+role). SND_STATE[0x00..0x0c] double as the
 * PSG register-staging bytes the frame ends by dumping to the chip. */
#define SND_PERIOD_A     0x00    /* word: channel A tone period (regs 1 coarse, 0 fine) */
#define SND_PERIOD_B     0x02    /* word: channel B tone period (regs 3, 2) */
#define SND_PERIOD_C     0x04    /* word: channel C tone period (regs 5, 4) */
#define SND_VOL_A        0x07    /* reg 8 volume A staging (aliases SND_MUSIC_BYTE) */
#define SND_VOL_C        0x09    /* reg 0xa volume C staging */
#define SND_ENV_SHAPE    0x0c    /* reg 0xd envelope shape: written only when nonzero, then cleared */
#define SND_FX_CTR       0x0d    /* effect total-duration countdown */
#define SND_FX_FREQ_ADD  0x0e    /* word: per-frame FX frequency increment */
#define SND_FX_FREQ_SET  0x10    /* word: FX frequency reset value */
#define SND_FX_SWEEP     0x12    /* long: pitch-sweep delta (its two halves swap per rotate state) */
#define SND_FX_FREQ      0x16    /* word: running FX frequency -> channel C period */
#define SND_FX_NOISE     0x17    /* noise value written to reg 6 when the noise gate fires */
#define SND_FX_NZ_RELOAD 0x18    /* noise-phase reload */
#define SND_FX_SWEEP_GATE 0x19   /* nonzero enables the pitch sweep */
#define SND_FX_SWEEP_ROT 0x1a    /* sweep-direction rotate state */
#define SND_FX_NZ_ROT    0x1b    /* noise-gate rotate state */
#define SND_FX_NZ_TMR    0x1c    /* noise-phase countdown */
#define SND_FX_SWEEP_TMR 0x1d    /* sweep-tick countdown */
#define SND_MUSIC_ON     0x1e    /* music master enable */
#define SND_EG_P1        0x21    /* EG pitch parameter */
#define SND_EG_VOL       0x22    /* EG volume -> volume A */
#define SND_EG_PHASE     0x23    /* EG phase counter (decremented by SND_EG_PHASE_DEC/frame) */
#define SND_TEMPO_DIV    0x24    /* tempo prescaler countdown (reload SND_TEMPO_RELOAD) */
#define SND_TEMPO_ACC    0x26    /* tempo accumulator; a carry advances the note stream */
/* SND_TUNE_PARAM (0x25) doubles as the per-frame tempo increment added to SND_TEMPO_ACC. */

#define SND_TEMPO_RELOAD 6       /* SND_TEMPO_DIV reload value */
#define SND_EG_PHASE_DEC 0x0d    /* EG phase decrement per frame */
#define SND_EG_PERIOD_HI 0x0100  /* high byte of the EG period seed (0x120's low byte is overwritten) */
#define SND_VOL_ENV_MODE 0x10    /* volume byte value that selects the envelope generator */
#define SND_MOD_TABLE    0x1b77f /* A1 modulation-table base passed to the DSP */

/* PSG register dump. SND_STATE staging byte per register, in the driver's write order; reg 7 is
 * the computed mixer (PSG_SRC_MIXER), and reg 0xd (shape) is emitted separately, only if nonzero. */
#define PSG_SRC_MIXER    0xff
#define SND_REG_ENV_SHAPE 0x0d   /* PSG envelope-shape register */
#define SND_MIXER_BASE   0xf8    /* reg 7 base: all tone + noise disabled */
#define SND_MIXER_A      0x09    /* per-voice tone+noise enable masks, EOR'd in when the voice's */
#define SND_MIXER_B      0x12    /* ENV_FLG bit0 is set */
#define SND_MIXER_C      0x24

/* Stop music: clear the music-active byte/word and MZFLAG. Shared by TURNOFF and the stream's
 * end-tune command (0x88), which reaches the same three writes by falling into TURNOFF's body. */
static void snd_music_off(uint8_t *image) {
    image[A_mzflag] = 0;
    image[SND_STATE + SND_MUSIC_BYTE] = 0;
    wr16(image + SND_STATE + SND_MUSIC_WORD, 0);
}

/* TURNOFF @0x1b268 — stop music: clear the music-active byte/word and MZFLAG. */
void g_TURNOFF(uint8_t *image) {
    snd_music_off(image);
}

/* EGOFF @0x1b252 — stop the envelope generator: clear EGFLAG and the music-active byte. */
void g_EGOFF(uint8_t *image) {
    image[SND_STATE + SND_EG_FLAG] = 0;
    image[SND_STATE + SND_MUSIC_BYTE] = 0;
}

/* INITFX @0x1b560 — load effect D0's parameter record into the effect voice state. */
void g_INITFX(uint8_t *image, uint32_t fx_id) {
    uint16_t idx = (uint16_t)(int16_t)(int8_t)fx_id;         /* ext.w d0 */
    uint16_t prod = (uint16_t)(idx * SND_FX_RECORD);         /* mulu.w #0x12 (low word) */
    uint32_t src = SND_FX_TABLE + sign_ext16(prod);          /* adda.w d0, a0 */

    image[A_fxflag] = 0;
    for (int i = 0; i < SND_FX_WORDS; i++)
        wr16(image + SND_STATE + SND_FX_PARAMS + 2 * i, be16(image + src + 2 * i));
    wr16(image + SND_STATE + SND_FX_PRE_LO, be16(image + src + SND_FX_WORDS * 2));       /* word 7 */
    wr16(image + SND_STATE + SND_FX_PRE_HI, be16(image + src + SND_FX_WORDS * 2 + 2));   /* word 8 */
    wr16(image + SND_STATE + SND_FX_TAIL, be16(image + SND_STATE + SND_FX_REREAD));
    image[A_fxflag] = 0xff;
}

/* INITTUNE @0x1b59c — start music track D0: seed the music header and the three voice-control
 * records from the per-tune tables, then flag music active. */
void g_INITTUNE(uint8_t *image, uint32_t tune_id) {
    uint16_t d0 = (uint16_t)(int16_t)(int8_t)tune_id;        /* ext.w d0 */
    uint16_t idx = set_low_byte(d0, (uint8_t)(d0 << 3));     /* asl.b #3 (8-byte tune stride) */

    image[A_mzflag] = 0;
    image[SND_STATE + SND_TUNE_LEN] = SND_TUNE_LEN_VAL;
    image[SND_STATE + SND_TUNE_ON] = 0xff;
    image[SND_STATE + SND_TUNE_PARAM] = image[SND_TUNE_TAB_B + idx];

    uint32_t rec = SND_VOICE_CTRL;
    uint16_t cur = idx;                                      /* d0.w indexes the word table */
    for (int voice = 0; voice < SND_VOICES; voice++) {
        uint16_t param = be16(image + SND_TUNE_TAB_W + cur);
        cur = set_low_byte(cur, (uint8_t)(cur + SND_TUNE_STEP));          /* addq.b #2, d0 */
        image[rec + SND_VC_TIMER] = 1;
        wr16(image + rec + SND_VC_FLAGS, SND_VC_STATE_VAL);
        image[rec + SND_VC_F13] = 0;
        wr16(image + rec + SND_VC_LOOP_OFF, param);
        wr16(image + rec + SND_VC_STREAM, be16(image + SND_STATE + param));
        rec += SND_VOICE_STRIDE;
    }
    image[A_mzflag] = 0xff;
}

/* --- snd_voice: per-frame note-stream stepper (snd_voice_b @0x1b2ec; snd_voice_a @0x1b2e8) ---
 *
 * Register contract (from REFRESH @0x1b086): A0 = voice-control record, A3 = SND_STATE. D0 is
 * pure scratch — its low byte is overwritten by the first stream read, and its high byte is 0 by
 * design (it indexes a 256-entry byte table and a 13-entry command jump table; a nonzero high
 * byte would run off both), so nothing is carried in. snd_voice_a is a 4-byte entry alias that
 * adds one voice stride to A0 and falls into this body — REFRESH calls _b for voice 0, then _a
 * twice (voices 1 and 2).
 *
 * Each frame the note-duration timer counts down; while it is still running only glide steps the
 * note. On expiry the stream is read: bytes >= 0xb0 set pitch/param fields, 0x80..0x8c are
 * commands (a 13-entry jump table), and a byte < 0x80 is the next note (which finalises the frame
 * and reloads the timer). Returns 1 iff the stream hit command 0x88 ("end tune"): on the real 68k
 * that command rewrites the caller's return address to re-enter REFRESH past its whole music block,
 * so REFRESH must abort the remaining voices + DSP for the frame — the caller acts on the flag. */
static int snd_voice_step(uint8_t *image, uint32_t rec) {
    uint8_t timer = (uint8_t)(image[rec + SND_VC_TIMER] - 1);
    image[rec + SND_VC_TIMER] = timer;
    if (timer != 0) {                           /* note still sounding: only glide runs */
        if (image[rec + SND_VC_FLAGS] & VC_F_GLIDE_EN) {
            if (image[rec + SND_VC_FLAGS] & VC_F_GLIDE_DOWN)
                image[rec + SND_VC_NOTE]--;
            else
                image[rec + SND_VC_NOTE]++;
        }
        return 0;
    }

    image[rec + SND_VC_FLAGS] &= VC_F_RETRIG_KEEP;                  /* re-trigger */
    uint32_t stream = SND_STATE + be16(image + rec + SND_VC_STREAM);

    for (;;) {
        uint8_t b = image[stream++];
        if (b >= SND_PITCH_LO) {                /* 0xb0..0xff: pitch / param set */
            if (b >= SND_PITCH_DUR_LO)
                image[rec + SND_VC_DUR] = (uint8_t)(b + 0x21);
            else if (b >= SND_PITCH_MID_LO)
                image[rec + SND_VC_PITCH_F] = (uint8_t)(b + 0x40);
            else                                /* 0xb0..0xbf: waveform from the pitch table */
                image[rec + SND_VC_WAVE] = image[SND_PITCH_TABLE + (uint8_t)(b + 0x40)];
            continue;
        }
        if (b >= SND_CMD_LO) {                  /* 0x80..0x8c: command jump table */
            switch (b) {
            case 0x80:                          /* set env field, then finalise (no note setup) */
                image[rec + SND_VC_ENV_E] = 0xf0;
                goto note_tail;
            case 0x81: image[rec + SND_VC_FLAGS] = 0; continue;
            case 0x82:
                image[rec + SND_VC_PORTA_STEP] = image[stream++];
                image[rec + SND_VC_FLAGS] |= VC_F_PORTA;
                image[rec + SND_VC_PORTA_LEN] = image[stream++];
                continue;
            case 0x83: image[rec + SND_VC_FLAGS] |= VC_F_GLIDE_DOWN; /* fall through */
            case 0x84: image[rec + SND_VC_FLAGS] |= VC_F_GLIDE_EN; continue;
            case 0x85: {                        /* loop/repeat: jump to the next loop-table entry */
                uint32_t table = SND_STATE + be16(image + rec + SND_VC_LOOP_OFF);
                uint8_t idx = image[rec + SND_VC_LOOP_CNT];       /* byte index, steps by 2 */
                if (be16(image + table + idx) == 0) idx = 0;      /* 0 entry => restart the loop */
                stream = SND_STATE + be16(image + table + idx);
                image[rec + SND_VC_LOOP_CNT] = (uint8_t)(idx + 2);
                continue;
            }
            case 0x86: {                        /* vibrato */
                image[rec + SND_VC_VIB_A] = image[stream++];
                uint8_t depth = image[stream++];
                image[rec + SND_VC_VIB_B] = depth;
                image[rec + SND_VC_VIB_2X] = (uint8_t)(depth + depth);
                image[rec + SND_VC_FLAGS] |= VC_F_VIBRATO;
                continue;
            }
            case 0x87: image[rec + SND_VC_FLAGS] |= VC_F_BIT1; continue;
            case 0x88:                          /* end tune: TURNOFF, then signal REFRESH to abort */
                snd_music_off(image);
                return 1;
            case 0x89: image[rec + SND_VC_F13] = image[stream++]; continue;
            case 0x8a:
                image[rec + SND_VC_FLAGS] |= (VC_F_BIT1 | VC_F_BIT2);
                continue;
            case 0x8b:
                image[SND_STATE + SND_STATE_CMD8B] = image[stream++];
                image[rec + SND_VC_FLAGS] |= (VC_F_BIT1 | VC_F_BIT2);
                continue;
            case 0x8c: image[rec + SND_VC_NOTE] = 0xff; continue;
            }
        }

        /* b < 0x80: a note. Set it up, then fall into the tail. */
        wr16(image + rec + SND_VC_GLIDE_ACC, 0);
        if (!(image[rec + SND_VC_NOTE] & 0x80)) {
            image[rec + SND_VC_ENV_E] = 0;
            image[rec + SND_VC_ENV_D] = 0;
        }
        image[rec + SND_VC_NOTE] = b;
        image[rec + SND_VC_WAVE_CUR] = image[rec + SND_VC_WAVE];
        image[rec + SND_VC_ENV_FLG] = 0;
        if (b >= SND_NOTE_SPLIT) {
            image[rec + SND_VC_ENV_FLG] = 2;
            image[SND_STATE + SND_STATE_NOTE] = (uint8_t)(b - SND_NOTE_SPLIT);
        }
    note_tail:
        image[rec + SND_VC_TIMER] = image[rec + SND_VC_DUR];
        wr16(image + rec + SND_VC_STREAM, (uint16_t)(stream - SND_STATE));
        return 0;
    }
}

void g_snd_voice_b(uint8_t *image, uint32_t rec) {
    (void)snd_voice_step(image, rec);
}

void g_snd_voice_a(uint8_t *image, uint32_t rec) {
    (void)snd_voice_step(image, rec + SND_VOICE_STRIDE);
}

/* --- snd_cmd_handler: per-frame voice DSP (snd_cmd_handler @0x1b3be; snd_stub @0x1b3ba) ---
 *
 * Register contract (from REFRESH): A0 = voice record, A1 = modulation-table base (0x1b77f), A2 =
 * PSG volume-output cursor (0x1b063, advanced one byte per voice), A3 = SND_STATE; the tone period
 * is returned in D1. D0 is scratch with a high byte of 0 by design (byte-indexed tables). snd_stub
 * is the +1-voice-stride entry alias that falls into this body — REFRESH runs voice 0 through
 * snd_cmd_handler, then voices 1/2 through snd_stub. Each frame it emits the voice's volume byte
 * (envelope generator + master volume), computes its tone period (base pitch + vibrato +
 * portamento), and advances the envelope / vibrato / portamento state. */
static uint16_t snd_cmd_step(uint8_t *image, uint32_t rec, uint32_t mod_tab, uint32_t out) {
    /* Envelope decay: step the level down; on underflow reload the next segment. */
    if (image[rec + SND_VC_ENV_E] < SND_ENV_MAX) {
        uint8_t level = image[rec + SND_VC_ENV_E];
        image[rec + SND_VC_ENV_E] = (uint8_t)(level - SND_ENV_STEP);
        if (level < SND_ENV_STEP) {                      /* underflow: reload envelope segment */
            uint8_t idx = image[SND_ENV_TABLE + image[rec + SND_VC_PITCH_F]];
            idx = (uint8_t)(idx + image[rec + SND_VC_ENV_D]);
            image[rec + SND_VC_ENV_D]++;
            image[rec + SND_VC_ENV_E] = image[mod_tab + SND_MOD_ENV_OFF + idx];
        }
    }
    uint8_t vol = (uint8_t)((image[rec + SND_VC_ENV_E] | SND_ENV_MAX) + 1);
    uint16_t vsum = (uint16_t)vol + image[SND_STATE + SND_STATE_MVOL];
    image[out] = (vsum & 0x100) ? (uint8_t)vsum : 0;     /* silence unless the add carried */

    /* Pitch: advance the LFO phase (waveform restarts when the table byte is negative), then look
     * up the base tone period for (lfo + note + f13). */
    uint8_t phase = (uint8_t)(image[rec + SND_VC_WAVE_CUR] + 1);
    uint8_t lfo = image[mod_tab + phase];
    if (lfo & 0x80) {                                    /* restart the modulation waveform */
        phase = image[rec + SND_VC_WAVE];
        lfo &= 0x7f;
    }
    image[rec + SND_VC_WAVE_CUR] = phase;
    uint8_t pidx = (uint8_t)(lfo + image[rec + SND_VC_NOTE] + image[rec + SND_VC_F13]);
    pidx = (uint8_t)(pidx + pidx);                       /* *2: word-table index */
    uint16_t period = be16(image + SND_PERIOD_TABLE + pidx);

    /* Vibrato: ramp the phase toward each range limit, flipping direction at the ends, and add the
     * signed offset from the range midpoint to the period. */
    if (image[rec + SND_VC_FLAGS] & VC_F_VIBRATO) {
        uint8_t range = image[rec + SND_VC_VIB_2X];
        uint8_t ph = image[rec + SND_VC_VIB_B];
        uint8_t step = image[rec + SND_VC_VIB_A];
        int at_limit;
        if (image[rec + SND_VC_FLAGS] & VC_F_VIB_DIR) {
            ph = (uint8_t)(ph + step);
            at_limit = (ph == range);
        } else {
            ph = (uint8_t)(ph - step);
            at_limit = (ph == 0);
        }
        if (at_limit) image[rec + SND_VC_FLAGS] ^= VC_F_VIB_DIR;
        image[rec + SND_VC_VIB_B] = ph;
        uint8_t half = (uint8_t)(range >> 1);
        if (ph < half) period = (uint16_t)(period - 0x100);   /* sign-extend the byte offset */
        period = (uint16_t)(period + (uint8_t)(ph - half));
    }

    /* Portamento: bit0 toggles every frame; when the glide is armed (bit3) it slides the period by
     * an accumulated signed step once the per-note delay elapses. */
    image[rec + SND_VC_FLAGS] ^= VC_F_BIT0;
    if (image[rec + SND_VC_FLAGS] & VC_F_PORTA) {
        if (image[rec + SND_VC_PORTA_LEN] != 0) {
            image[rec + SND_VC_PORTA_LEN]--;
        } else {
            int16_t step = (int8_t)image[rec + SND_VC_PORTA_STEP];
            uint16_t acc = (uint16_t)(be16(image + rec + SND_VC_GLIDE_ACC) + step);
            wr16(image + rec + SND_VC_GLIDE_ACC, acc);
            period = (uint16_t)(period + acc);
        }
    }

    /* Next frame's control byte: 3 if the note's env-flag is armed, else 0; then, when flags bits
     * 0+1 are both set, feed R6 from the cmd-0x8b slot and OR in 1. */
    uint8_t ctl = (image[rec + SND_VC_ENV_FLG] & VC_F_BIT1) ? 3 : 0;
    if ((image[rec + SND_VC_FLAGS] & VC_F_BIT1) && (image[rec + SND_VC_FLAGS] & VC_F_BIT0)) {
        image[SND_STATE + SND_STATE_R6] = image[SND_STATE + SND_STATE_CMD8B];
        ctl |= 1;
    }
    if (image[rec + SND_VC_FLAGS] & VC_F_BIT2)
        image[rec + SND_VC_FLAGS] &= (uint8_t)~VC_F_BIT1;
    image[rec + SND_VC_ENV_FLG] = ctl;
    return period;
}

uint32_t g_snd_cmd_handler(uint8_t *image, uint32_t rec, uint32_t mod_tab, uint32_t out) {
    return snd_cmd_step(image, rec, mod_tab, out);
}

uint32_t g_snd_stub(uint8_t *image, uint32_t rec, uint32_t mod_tab, uint32_t out) {
    return snd_cmd_step(image, rec + SND_VOICE_STRIDE, mod_tab, out);
}

/* --- REFRESH @0x1b086 — the 50 Hz VBL sound driver, run once per frame ---
 *
 * Not one of the 91 tracked functions (it's the untracked VBL orchestrator). It updates the three
 * voices' music/envelope/effect state, then emits the frame's YM2149 register writes. The chip
 * ports ($ffff8800/8802) live outside the image, so instead of writing them this reconstruction
 * appends each (reg, value) to the caller's buffers (mirroring the oracle's shim capture) and
 * returns the count; the memory image carries all the intermediate state. The video-sync register
 * `btst #1,$ffff820a` reads 0 in the oracle (address above the image), so its branch is modelled
 * as always taking the tempo-prescaler path. Reuses the verified snd_voice_step / snd_cmd_step. */
uint32_t g_REFRESH(uint8_t *image, uint8_t *psg_reg, uint8_t *psg_val, uint32_t cap) {
    const uint32_t v0 = SND_VOICE_CTRL;                       /* voice 0 record; +stride per voice */
    const uint32_t env0 = SND_VOICE_CTRL + SND_VC_ENV_FLG;

    /* --- music: prescale the tempo, step the note stream on a carry, then run the DSP --- */
    if (image[SND_STATE + SND_MUSIC_ON]) {
        if (--image[SND_STATE + SND_TEMPO_DIV] == 0) {
            image[SND_STATE + SND_TEMPO_DIV] = SND_TEMPO_RELOAD;
        } else {
            uint16_t acc = image[SND_STATE + SND_TEMPO_ACC] + image[SND_STATE + SND_TUNE_PARAM];
            image[SND_STATE + SND_TEMPO_ACC] = (uint8_t)acc;
            int ended = 0;
            if (acc & 0x100) {                               /* carry: advance the three voices */
                ended = snd_voice_step(image, v0)
                     || snd_voice_step(image, v0 + SND_VOICE_STRIDE)
                     || snd_voice_step(image, v0 + 2 * SND_VOICE_STRIDE);
            }
            /* An "end tune" (cmd 0x88) rewrites the return so REFRESH skips straight to the EG
             * block, dropping the rest of the voices' steps and the whole DSP pass this frame. */
            if (!ended) {
                image[SND_STATE + SND_STATE_R6] = image[SND_STATE + SND_STATE_NOTE];
                wr16(image + SND_STATE + SND_PERIOD_A,
                     snd_cmd_step(image, v0, SND_MOD_TABLE, SND_STATE + SND_VOL_A));
                wr16(image + SND_STATE + SND_PERIOD_B,
                     snd_cmd_step(image, v0 + SND_VOICE_STRIDE, SND_MOD_TABLE, SND_STATE + SND_VOL_A + 1));
                wr16(image + SND_STATE + SND_PERIOD_C,
                     snd_cmd_step(image, v0 + 2 * SND_VOICE_STRIDE, SND_MOD_TABLE, SND_STATE + SND_VOL_A + 2));
            }
        }
    }

    /* --- envelope generator: synthesize channel A's period from the EG parameters --- */
    if (image[SND_STATE + SND_EG_FLAG]) {
        image[SND_STATE + SND_VOL_A] = image[SND_STATE + SND_EG_VOL];
        uint16_t d0 = (uint16_t)(SND_EG_PERIOD_HI | (uint8_t)~image[SND_STATE + SND_EG_P1]);
        uint16_t d1 = (uint8_t)~image[SND_STATE + SND_EG_P1];
        d0 = (uint16_t)(d0 + d0); d0 = (uint16_t)(d0 + d1);   /* d0 = 4*d0_init + 3*d1 */
        d0 = (uint16_t)(d0 + d0); d0 = (uint16_t)(d0 + d1);
        uint8_t phase = image[SND_STATE + SND_EG_PHASE];
        d0 = (uint16_t)(d0 + (phase & 0x1f));
        image[SND_STATE + SND_EG_PHASE] = (uint8_t)(phase - SND_EG_PHASE_DEC);
        if (image[SND_STATE + SND_EG_PHASE] & 1) d0 = (uint16_t)(d0 + 0x100);
        wr16(image + SND_STATE + SND_PERIOD_A, d0);
        image[env0] &= (uint8_t)~VC_F_BIT0;
    }

    /* --- effects: sweep the frequency / gate the noise, drive channel C --- */
    if (image[A_fxflag]) {
        if (--image[SND_STATE + SND_FX_CTR] == 0) {          /* effect elapsed: silence C, stop */
            image[SND_STATE + SND_VOL_C] = 0;
            image[A_fxflag] = 0;
        } else {
            if (image[SND_STATE + SND_FX_SWEEP_GATE] && --image[SND_STATE + SND_FX_SWEEP_TMR] == 0) {
                image[SND_STATE + SND_FX_SWEEP_TMR] = image[SND_STATE + SND_FX_SWEEP_GATE];
                uint32_t sweep = be32(image + SND_STATE + SND_FX_SWEEP);
                uint8_t rot = image[SND_STATE + SND_FX_SWEEP_ROT];
                int bit0 = rot & 1;
                image[SND_STATE + SND_FX_SWEEP_ROT] = (uint8_t)((rot >> 1) | (rot << 7));   /* ror.b #1 */
                if (!bit0) sweep = (sweep >> 16) | (sweep << 16);                            /* swap */
                wr16(image + SND_STATE + SND_FX_FREQ,
                     (uint16_t)(be16(image + SND_STATE + SND_FX_FREQ) + (uint16_t)sweep));
            }
            wr16(image + SND_STATE + SND_FX_FREQ,
                 (uint16_t)(be16(image + SND_STATE + SND_FX_FREQ) + be16(image + SND_STATE + SND_FX_FREQ_ADD)));
            if (image[SND_STATE + SND_FX_NZ_RELOAD] && --image[SND_STATE + SND_FX_NZ_TMR] == 0) {
                image[SND_STATE + SND_FX_NZ_TMR] = image[SND_STATE + SND_FX_NZ_RELOAD];
                wr16(image + SND_STATE + SND_FX_FREQ, be16(image + SND_STATE + SND_FX_FREQ_SET));
            }
            image[SND_STATE + SND_VOL_C] = SND_VOL_ENV_MODE;
            wr16(image + SND_STATE + SND_PERIOD_C, be16(image + SND_STATE + SND_FX_FREQ));
            uint32_t env2 = SND_VOICE_CTRL + 2 * SND_VOICE_STRIDE + SND_VC_ENV_FLG;
            image[env2] &= (uint8_t)~VC_F_BIT0;
            uint8_t rot = image[SND_STATE + SND_FX_NZ_ROT];
            int bit0 = rot & 1;
            image[SND_STATE + SND_FX_NZ_ROT] = (uint8_t)((rot >> 1) | (rot << 7));           /* ror.b #1 */
            if (bit0) {                                      /* noise gate fires this frame */
                image[env2]++;
                image[SND_STATE + SND_STATE_R6] = image[SND_STATE + SND_FX_NOISE];
            }
        }
    }

    /* --- mixer byte: enable tone+noise per voice whose control bit is set --- */
    static const uint8_t mixer_mask[SND_VOICES] = {SND_MIXER_A, SND_MIXER_B, SND_MIXER_C};
    uint8_t mixer = SND_MIXER_BASE;
    for (int v = 0; v < SND_VOICES; v++)
        if (image[SND_VOICE_CTRL + v * SND_VOICE_STRIDE + SND_VC_ENV_FLG] & VC_F_BIT0)
            mixer ^= mixer_mask[v];

    /* --- dump the PSG registers (reg, value) in the driver's fixed order --- */
    static const uint8_t psg_regs[] = {1, 0, 3, 2, 5, 4, 6, 7, 8, 9, 0xa, 0xc, 0xb};
    static const uint8_t psg_src[]  = {0, 1, 2, 3, 4, 5, 6, PSG_SRC_MIXER, 7, 8, 9, 0xa, 0xb};
    uint32_t n = 0;
    for (unsigned i = 0; i < sizeof(psg_regs) && n < cap; i++) {
        psg_reg[n] = psg_regs[i];
        psg_val[n] = (psg_src[i] == PSG_SRC_MIXER) ? mixer : image[SND_STATE + psg_src[i]];
        n++;
    }
    uint8_t shape = image[SND_STATE + SND_ENV_SHAPE];         /* reg 0xd: only when nonzero, then clear */
    if (shape != 0 && n < cap) {
        psg_reg[n] = SND_REG_ENV_SHAPE;
        psg_val[n] = shape;
        n++;
        image[SND_STATE + SND_ENV_SHAPE] = 0;
    }
    return n;
}