/* sound.c — the REFRESH sound driver, native port of recreate/src/sound.c (verified byte-exact vs
 * the 68000). The driver owns its state in SoundState (include/sound.h) and reads the const tables +
 * tune note streams from the baked SND_CONST blob (build/sound_data.h); nothing threads an image
 * pointer. Every SND_CONST index is relative to the original SND_STATE base, so a voice record's
 * stored stream/loop cursor indexes the blob directly and an absolute table sits at its *_OFF.
 *
 * The whole driver runs from the VBL and is pure state: REFRESH does not touch the YM2149 (its ports
 * live off-image), it appends the frame's (reg, value) writes to caller buffers — the identical seam
 * recreate's g_REFRESH uses, so test/test_sound_rm.py can compare the streams and the whole state.
 *
 * All state/const bytes keep the 68000's big-endian order, so be16/be32/wr16 (st.h) read them as the
 * machine does — one aligned move on the m68k target, byte-assembly on the little-endian test host.
 */
#include <string.h>

#include "sound.h"
#include "sound_data.h"
#include "st.h"   /* be16/be32/wr16 (big-endian, one aligned move on m68k), sx16, set_low_byte */

/* ---- reset / stop-music ----------------------------------------------------------------------- */

void rm_sound_reset(SoundState *s) {
    memcpy(s->header, SND_CONST, SND_STATE_BYTES);   /* power-on state: EG vol 0x0e, master vol 0x0f */
    memset(s->voice, 0, sizeof s->voice);
}

/* Stop music: clear the music-active byte/word and mzflag. Shared by TURNOFF and the note stream's
 * end-tune command (0x88), which reaches the same three writes by falling into TURNOFF's body. */
static void snd_music_off(SoundState *s) {
    s->header[SND_MUSIC_ON] = 0;
    s->header[SND_MUSIC_BYTE] = 0;
    wr16(s->header + SND_MUSIC_WORD, 0);
}

void rm_turnoff(SoundState *s) {
    snd_music_off(s);
}

void rm_egoff(SoundState *s) {
    s->header[SND_EG_FLAG] = 0;
    s->header[SND_MUSIC_BYTE] = 0;
}

/* ---- INITFX / INITTUNE ------------------------------------------------------------------------ */

void rm_initfx(SoundState *s, uint32_t fx_id) {
    uint16_t idx = (uint16_t)(int16_t)(int8_t)fx_id;            /* ext.w d0 */
    uint16_t prod = (uint16_t)(idx * SND_FX_RECORD);           /* mulu.w #0x12 (low word) */
    uint32_t src = SND_FX_TABLE_OFF + sx16(prod);              /* adda.w d0, a0 */

    s->header[SND_FX_FLAG] = 0;
    for (int i = 0; i < SND_FX_WORDS; i++)
        wr16(s->header + SND_FX_PARAMS + 2 * i, be16(SND_CONST + src + 2 * i));
    wr16(s->header + SND_FX_PRE_LO, be16(SND_CONST + src + SND_FX_WORDS * 2));       /* word 7 */
    wr16(s->header + SND_FX_PRE_HI, be16(SND_CONST + src + SND_FX_WORDS * 2 + 2));   /* word 8 */
    wr16(s->header + SND_FX_TAIL, be16(s->header + SND_FX_REREAD));
    s->header[SND_FX_FLAG] = 0xff;
}

void rm_inittune(SoundState *s, uint32_t tune_id) {
    uint16_t tune_ext = (uint16_t)(int16_t)(int8_t)tune_id;           /* ext.w d0 */
    uint16_t idx = set_low_byte(tune_ext, (uint8_t)(tune_ext << 3));  /* asl.b #3 (8-byte tune stride) */

    s->header[SND_MUSIC_ON] = 0;
    s->header[SND_TUNE_LEN] = SND_TUNE_LEN_VAL;
    s->header[SND_TUNE_ON] = 0xff;
    s->header[SND_TUNE_PARAM] = SND_CONST[SND_TUNE_TAB_B_OFF + idx];

    uint16_t cur = idx;                                              /* d0.w indexes the word table */
    for (int voice = 0; voice < SND_VOICES; voice++) {
        uint8_t *rec = s->voice[voice];
        uint16_t param = be16(SND_CONST + SND_TUNE_TAB_W_OFF + cur);
        cur = set_low_byte(cur, (uint8_t)(cur + SND_TUNE_STEP));     /* addq.b #2, d0 */
        rec[SND_VC_TIMER] = 1;
        wr16(rec + SND_VC_FLAGS, SND_VC_STATE_VAL);
        rec[SND_VC_F13] = 0;
        wr16(rec + SND_VC_LOOP_OFF, param);
        wr16(rec + SND_VC_STREAM, be16(SND_CONST + param));         /* per-voice stream start */
    }
    s->header[SND_MUSIC_ON] = 0xff;
}

/* ---- snd_voice_step: per-frame note-stream stepper -------------------------------------------
 *
 * Each frame the note-duration timer counts down; while it still runs only glide steps the note. On
 * expiry the stream is read: bytes >= 0xb0 set pitch/param fields, 0x80..0x8c are commands (a 13-entry
 * jump table), and a byte < 0x80 is the next note (which finalises the frame and reloads the timer).
 * Returns 1 iff the stream hit command 0x88 ("end tune"): on the real 68k that rewrote the caller's
 * return to re-enter REFRESH past its whole music block, so REFRESH must abort the rest of the frame. */
static int snd_voice_step(SoundState *s, uint8_t *rec) {
    uint8_t timer = (uint8_t)(rec[SND_VC_TIMER] - 1);
    rec[SND_VC_TIMER] = timer;
    if (timer != 0) {                           /* note still sounding: only glide runs */
        if (rec[SND_VC_FLAGS] & VC_F_GLIDE_EN) {
            if (rec[SND_VC_FLAGS] & VC_F_GLIDE_DOWN)
                rec[SND_VC_NOTE]--;
            else
                rec[SND_VC_NOTE]++;
        }
        return 0;
    }

    rec[SND_VC_FLAGS] &= VC_F_RETRIG_KEEP;                          /* re-trigger */
    uint32_t stream = be16(rec + SND_VC_STREAM);                    /* SND_CONST cursor */

    for (;;) {
        uint8_t b = SND_CONST[stream++];
        if (b >= SND_PITCH_LO) {                /* 0xb0..0xff: pitch / param set */
            if (b >= SND_PITCH_DUR_LO)
                rec[SND_VC_DUR] = (uint8_t)(b + SND_STREAM_DUR_BIAS);
            else if (b >= SND_PITCH_MID_LO)
                rec[SND_VC_PITCH_F] = (uint8_t)(b + SND_STREAM_PITCH_BIAS);
            else                                /* 0xb0..0xbf: waveform from the pitch table */
                rec[SND_VC_WAVE] = SND_CONST[SND_PITCH_TABLE_OFF + (uint8_t)(b + SND_STREAM_PITCH_BIAS)];
            continue;
        }
        if (b >= SND_CMD_LO) {                  /* 0x80..0x8c: command jump table */
            switch (b) {
            case 0x80:                          /* set env inactive, then finalise (no note setup) */
                rec[SND_VC_ENV_E] = SND_ENV_MAX;
                goto note_tail;
            case 0x81: rec[SND_VC_FLAGS] = 0; continue;
            case 0x82:
                rec[SND_VC_PORTA_STEP] = SND_CONST[stream++];
                rec[SND_VC_FLAGS] |= VC_F_PORTA;
                rec[SND_VC_PORTA_LEN] = SND_CONST[stream++];
                continue;
            case 0x83: rec[SND_VC_FLAGS] |= VC_F_GLIDE_DOWN; /* fall through */
            case 0x84: rec[SND_VC_FLAGS] |= VC_F_GLIDE_EN; continue;
            case 0x85: {                        /* loop/repeat: jump to the next loop-table entry */
                uint32_t table = be16(rec + SND_VC_LOOP_OFF);       /* SND_CONST cursor */
                uint8_t idx = rec[SND_VC_LOOP_CNT];                 /* byte index, steps by 2 */
                if (be16(SND_CONST + table + idx) == 0) idx = 0;    /* 0 entry => restart the loop */
                stream = be16(SND_CONST + table + idx);
                rec[SND_VC_LOOP_CNT] = (uint8_t)(idx + 2);
                continue;
            }
            case 0x86: {                        /* vibrato */
                rec[SND_VC_VIB_A] = SND_CONST[stream++];
                uint8_t depth = SND_CONST[stream++];
                rec[SND_VC_VIB_B] = depth;
                rec[SND_VC_VIB_2X] = (uint8_t)(depth + depth);
                rec[SND_VC_FLAGS] |= VC_F_VIBRATO;
                continue;
            }
            case 0x87: rec[SND_VC_FLAGS] |= VC_F_BIT1; continue;
            case 0x88:                          /* end tune: TURNOFF, then signal REFRESH to abort */
                snd_music_off(s);
                return 1;
            case 0x89: rec[SND_VC_F13] = SND_CONST[stream++]; continue;
            case 0x8a:
                rec[SND_VC_FLAGS] |= (VC_F_BIT1 | VC_F_BIT2);
                continue;
            case 0x8b:
                s->header[SND_STATE_CMD8B] = SND_CONST[stream++];
                rec[SND_VC_FLAGS] |= (VC_F_BIT1 | VC_F_BIT2);
                continue;
            case 0x8c: rec[SND_VC_NOTE] = 0xff; continue;
            }
        }

        /* b < 0x80: a note. Set it up, then fall into the tail. */
        wr16(rec + SND_VC_GLIDE_ACC, 0);
        if (!(rec[SND_VC_NOTE] & 0x80)) {
            rec[SND_VC_ENV_E] = 0;
            rec[SND_VC_ENV_D] = 0;
        }
        rec[SND_VC_NOTE] = b;
        rec[SND_VC_WAVE_CUR] = rec[SND_VC_WAVE];
        rec[SND_VC_ENV_FLG] = 0;
        if (b >= SND_NOTE_SPLIT) {
            rec[SND_VC_ENV_FLG] = 2;
            s->header[SND_STATE_NOTE] = (uint8_t)(b - SND_NOTE_SPLIT);
        }
    note_tail:
        rec[SND_VC_TIMER] = rec[SND_VC_DUR];
        wr16(rec + SND_VC_STREAM, (uint16_t)stream);
        return 0;
    }
}

/* ---- snd_cmd_step: per-frame voice DSP -------------------------------------------------------
 *
 * Emits the voice's volume byte (envelope generator + master volume) into header[out_off], computes
 * its tone period (base pitch + vibrato + portamento), and advances the envelope / vibrato /
 * portamento state. The modulation table is always SND_MOD_TABLE, so it is read straight from
 * SND_CONST rather than passed as a base. Returns the tone period. */
static uint16_t snd_cmd_step(SoundState *s, uint8_t *rec, uint32_t out_off) {
    const uint32_t mod = SND_MOD_TABLE_OFF;

    /* Envelope decay: step the level down; on underflow reload the next segment. */
    if (rec[SND_VC_ENV_E] < SND_ENV_MAX) {
        uint8_t level = rec[SND_VC_ENV_E];
        rec[SND_VC_ENV_E] = (uint8_t)(level - SND_ENV_STEP);
        if (level < SND_ENV_STEP) {                      /* underflow: reload envelope segment */
            uint8_t idx = SND_CONST[SND_ENV_TABLE_OFF + rec[SND_VC_PITCH_F]];
            idx = (uint8_t)(idx + rec[SND_VC_ENV_D]);
            rec[SND_VC_ENV_D]++;
            rec[SND_VC_ENV_E] = SND_CONST[mod + SND_MOD_ENV_OFF + idx];
        }
    }
    uint8_t vol = (uint8_t)((rec[SND_VC_ENV_E] | SND_ENV_MAX) + 1);
    uint16_t vsum = (uint16_t)vol + s->header[SND_STATE_MVOL];
    s->header[out_off] = (vsum & SND_BYTE_CARRY) ? (uint8_t)vsum : 0;   /* silence unless the add carried */

    /* Pitch: advance the LFO phase (waveform restarts when the table byte is negative), then look up
     * the base tone period for (lfo + note + f13). */
    uint8_t phase = (uint8_t)(rec[SND_VC_WAVE_CUR] + 1);
    uint8_t lfo = SND_CONST[mod + phase];
    if (lfo & 0x80) {                                    /* restart the modulation waveform */
        phase = rec[SND_VC_WAVE];
        lfo &= 0x7f;
    }
    rec[SND_VC_WAVE_CUR] = phase;
    uint8_t pidx = (uint8_t)(lfo + rec[SND_VC_NOTE] + rec[SND_VC_F13]);
    pidx = (uint8_t)(pidx + pidx);                       /* *2: word-table index */
    uint16_t period = be16(SND_CONST + SND_PERIOD_TABLE_OFF + pidx);

    /* Vibrato: ramp the phase toward each range limit, flipping direction at the ends, and add the
     * signed offset from the range midpoint to the period. */
    if (rec[SND_VC_FLAGS] & VC_F_VIBRATO) {
        uint8_t range = rec[SND_VC_VIB_2X];
        uint8_t ph = rec[SND_VC_VIB_B];
        uint8_t step = rec[SND_VC_VIB_A];
        int at_limit;
        if (rec[SND_VC_FLAGS] & VC_F_VIB_DIR) {
            ph = (uint8_t)(ph + step);
            at_limit = (ph == range);
        } else {
            ph = (uint8_t)(ph - step);
            at_limit = (ph == 0);
        }
        if (at_limit) rec[SND_VC_FLAGS] ^= VC_F_VIB_DIR;
        rec[SND_VC_VIB_B] = ph;
        uint8_t half = (uint8_t)(range >> 1);
        if (ph < half) period = (uint16_t)(period - SND_BYTE_CARRY);   /* sign-extend the byte offset */
        period = (uint16_t)(period + (uint8_t)(ph - half));
    }

    /* Portamento: bit0 toggles every frame; when the glide is armed (bit3) it slides the period by an
     * accumulated signed step once the per-note delay elapses. */
    rec[SND_VC_FLAGS] ^= VC_F_BIT0;
    if (rec[SND_VC_FLAGS] & VC_F_PORTA) {
        if (rec[SND_VC_PORTA_LEN] != 0) {
            rec[SND_VC_PORTA_LEN]--;
        } else {
            int16_t step = (int8_t)rec[SND_VC_PORTA_STEP];
            uint16_t acc = (uint16_t)(be16(rec + SND_VC_GLIDE_ACC) + step);
            wr16(rec + SND_VC_GLIDE_ACC, acc);
            period = (uint16_t)(period + acc);
        }
    }

    /* Next frame's control byte: 3 if the note's env-flag is armed, else 0; then, when flags bits 0+1
     * are both set, feed R6 from the cmd-0x8b slot and OR in 1. */
    uint8_t ctl = (rec[SND_VC_ENV_FLG] & VC_F_BIT1) ? 3 : 0;
    if ((rec[SND_VC_FLAGS] & VC_F_BIT1) && (rec[SND_VC_FLAGS] & VC_F_BIT0)) {
        s->header[SND_STATE_R6] = s->header[SND_STATE_CMD8B];
        ctl |= 1;
    }
    if (rec[SND_VC_FLAGS] & VC_F_BIT2)
        rec[SND_VC_FLAGS] &= (uint8_t)~VC_F_BIT1;
    rec[SND_VC_ENV_FLG] = ctl;
    return period;
}

/* ---- REFRESH — the 50 Hz VBL sound driver ---------------------------------------------------- */

uint32_t rm_refresh(SoundState *s, uint8_t *regs, uint8_t *vals, int cap) {
    uint8_t *v0 = s->voice[0];

    /* --- music: prescale the tempo, step the note stream on a carry, then run the DSP --- */
    if (s->header[SND_MUSIC_ON]) {
        if (--s->header[SND_TEMPO_DIV] == 0) {
            s->header[SND_TEMPO_DIV] = SND_TEMPO_RELOAD;
        } else {
            uint16_t acc = s->header[SND_TEMPO_ACC] + s->header[SND_TUNE_PARAM];
            s->header[SND_TEMPO_ACC] = (uint8_t)acc;
            int ended = 0;
            if (acc & SND_BYTE_CARRY) {                      /* carry: advance the three voices */
                ended = snd_voice_step(s, s->voice[0])
                     || snd_voice_step(s, s->voice[1])
                     || snd_voice_step(s, s->voice[2]);
            }
            /* An "end tune" (cmd 0x88) skips straight to the EG block, dropping the rest of the
             * voices' steps and the whole DSP pass this frame. */
            if (!ended) {
                s->header[SND_STATE_R6] = s->header[SND_STATE_NOTE];
                wr16(s->header + SND_PERIOD_A, snd_cmd_step(s, s->voice[0], SND_VOL_A));
                wr16(s->header + SND_PERIOD_B, snd_cmd_step(s, s->voice[1], SND_VOL_A + 1));
                wr16(s->header + SND_PERIOD_C, snd_cmd_step(s, s->voice[2], SND_VOL_A + 2));
            }
        }
    }

    /* --- envelope generator: synthesize channel A's period from the EG parameters --- */
    if (s->header[SND_EG_FLAG]) {
        s->header[SND_VOL_A] = s->header[SND_EG_VOL];
        uint16_t eg_period = (uint16_t)(SND_EG_PERIOD_HI | (uint8_t)~s->header[SND_EG_P1]);
        uint16_t pitch_inv = (uint8_t)~s->header[SND_EG_P1];             /* inverted EG pitch param */
        eg_period = (uint16_t)(eg_period + eg_period); eg_period = (uint16_t)(eg_period + pitch_inv);
        eg_period = (uint16_t)(eg_period + eg_period); eg_period = (uint16_t)(eg_period + pitch_inv);
        uint8_t phase = s->header[SND_EG_PHASE];
        eg_period = (uint16_t)(eg_period + (phase & 0x1f));
        s->header[SND_EG_PHASE] = (uint8_t)(phase - SND_EG_PHASE_DEC);
        if (s->header[SND_EG_PHASE] & 1) eg_period = (uint16_t)(eg_period + SND_EG_PERIOD_HI);
        wr16(s->header + SND_PERIOD_A, eg_period);
        v0[SND_VC_ENV_FLG] &= (uint8_t)~VC_F_BIT0;
    }

    /* --- effects: sweep the frequency / gate the noise, drive channel C --- */
    if (s->header[SND_FX_FLAG]) {
        if (--s->header[SND_FX_CTR] == 0) {              /* effect elapsed: silence C, stop */
            s->header[SND_VOL_C] = 0;
            s->header[SND_FX_FLAG] = 0;
        } else {
            if (s->header[SND_FX_SWEEP_GATE] && --s->header[SND_FX_SWEEP_TMR] == 0) {
                s->header[SND_FX_SWEEP_TMR] = s->header[SND_FX_SWEEP_GATE];
                uint32_t sweep = be32(s->header + SND_FX_SWEEP);
                uint8_t rot = s->header[SND_FX_SWEEP_ROT];
                int bit0 = rot & 1;
                s->header[SND_FX_SWEEP_ROT] = (uint8_t)((rot >> 1) | (rot << 7));   /* ror.b #1 */
                if (!bit0) sweep = (sweep >> 16) | (sweep << 16);                    /* swap */
                wr16(s->header + SND_FX_FREQ,
                     (uint16_t)(be16(s->header + SND_FX_FREQ) + (uint16_t)sweep));
            }
            wr16(s->header + SND_FX_FREQ,
                 (uint16_t)(be16(s->header + SND_FX_FREQ) + be16(s->header + SND_FX_FREQ_ADD)));
            if (s->header[SND_FX_NZ_RELOAD] && --s->header[SND_FX_NZ_TMR] == 0) {
                s->header[SND_FX_NZ_TMR] = s->header[SND_FX_NZ_RELOAD];
                wr16(s->header + SND_FX_FREQ, be16(s->header + SND_FX_FREQ_SET));
            }
            s->header[SND_VOL_C] = SND_VOL_ENV_MODE;
            wr16(s->header + SND_PERIOD_C, be16(s->header + SND_FX_FREQ));
            uint8_t *v2 = s->voice[2];
            v2[SND_VC_ENV_FLG] &= (uint8_t)~VC_F_BIT0;
            uint8_t rot = s->header[SND_FX_NZ_ROT];
            int bit0 = rot & 1;
            s->header[SND_FX_NZ_ROT] = (uint8_t)((rot >> 1) | (rot << 7));           /* ror.b #1 */
            if (bit0) {                                  /* noise gate fires this frame */
                v2[SND_VC_ENV_FLG]++;
                s->header[SND_STATE_R6] = s->header[SND_FX_NOISE];
            }
        }
    }

    /* --- mixer byte: enable tone+noise per voice whose control bit is set --- */
    static const uint8_t mixer_mask[SND_VOICES] = {SND_MIXER_A, SND_MIXER_B, SND_MIXER_C};
    uint8_t mixer = SND_MIXER_BASE;
    for (int v = 0; v < SND_VOICES; v++)
        if (s->voice[v][SND_VC_ENV_FLG] & VC_F_BIT0)
            mixer ^= mixer_mask[v];

    /* --- dump the PSG registers (reg, value) in the driver's fixed order --- */
#define PSG_SRC_MIXER 0xff   /* psg_src sentinel: value comes from the computed mixer, not a staging byte */
    static const uint8_t psg_regs[] = {1, 0, 3, 2, 5, 4, 6, 7, 8, 9, 0xa, 0xc, 0xb};
    static const uint8_t psg_src[]  = {0, 1, 2, 3, 4, 5, 6, PSG_SRC_MIXER, 7, 8, 9, 0xa, 0xb};
    uint32_t n = 0;
    for (unsigned i = 0; i < sizeof(psg_regs) && (int)n < cap; i++) {
        regs[n] = psg_regs[i];
        vals[n] = (psg_src[i] == PSG_SRC_MIXER) ? mixer : s->header[psg_src[i]];
        n++;
    }
    uint8_t shape = s->header[SND_ENV_SHAPE];             /* reg 0xd: only when nonzero, then clear */
    if (shape != 0 && (int)n < cap) {
        regs[n] = SND_REG_ENV_SHAPE;
        vals[n] = shape;
        n++;
        s->header[SND_ENV_SHAPE] = 0;
    }
    return n;
}
