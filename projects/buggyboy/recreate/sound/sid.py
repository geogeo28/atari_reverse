"""MOS SID (Commodore 64) transcode of the captured YM2149 register stream.

BuggyBoy's driver targets the ST's YM2149 PSG; this plays the *same* per-frame register
stream on a C64 SID instead (via reSID-fp / ``pyresidfp``). It is a faithful **transcode**,
not a copy: the two chips are architecturally different, so each YM concept is mapped to its
SID equivalent, keeping the original 50 Hz timing and arrangement but with SID timbre.

Mapping (per 50 Hz frame, per channel -> SID voice 1/2/3):

* **Tone** -> SID **pulse @ 50% duty** (a YM square is a 50% pulse). YM tone period is turned
  into a frequency, then into the SID's 16-bit ``Fn = f * 2**24 / clk`` (PAL clock).
* **Noise** -> SID **noise** waveform. YM has one shared noise source routed per channel by
  the mixer; SID noise is per-voice, so a channel with noise enabled sets its voice to noise.
  A YM channel that mixes tone *and* noise at once can't be reproduced on a single SID voice
  (SID has no tone+noise mode) -> tone wins (it carries the melody); noise-only stays noise.
* **Volume / envelope** -> **per-voice software scaling**, NOT the SID ADSR. SID has no
  per-voice volume register, and its envelope can't be raised mid-note without re-gating,
  whereas BuggyBoy ramps channel volume every frame. So each voice is rendered in isolation
  at full sustain and scaled by the *exact* YM per-frame amplitude (reusing ``ym2149``'s
  volume DAC and the eight hardware-envelope shapes). This reproduces the ST dynamics
  precisely and also covers YM's hardware-envelope "buzzer" channels, which SID lacks.

The faithful transcode leaves the SID's own character off (filter, ring-mod, sync, PWM,
ADSR): it is a port of the ST sound, not a re-scored native C64 tune. Passing ``c64=True`` to
``render`` re-engages the three signatures that make a SID sound unmistakably "C64" — a slow
pulse-width sweep, a resonant low-pass filter, and a per-note ADSR pluck — layered on top of the
same YM arrangement and dynamics (see ``_render_voice_c64``). Output is mono float in [-1, 1].
"""
import datetime
import math

import numpy as np
from pyresidfp import (SoundInterfaceDevice as SID, WritableRegister as W, ControlBits as C,
                       ModeVolBits, ResFiltBits)
from pyresidfp.sound_interface_device import ChipModel, SamplingMethod

import ym2149  # sibling renderer: reuse its volume DAC, envelope shapes, and frame constants

FPS = ym2149.FPS               # 50 Hz driver frames — identical clock to the YM path
RATE = ym2149.RATE             # 44100; keeps SID and YM renders directly comparable
SID_CLOCK = SID.PAL_CLOCK_FREQUENCY   # PAL C64: ~985 kHz, and PAL VBL is 50 Hz like the ST
SID_ACC_BITS = 1 << 24                # SID phase accumulator: Fn = f * 2**24 / clock
PULSE_HALF = 0x800                    # 12-bit pulse width, 50% duty == a square wave
MASTER_VOL_FULL = 0x0F                # Mode/Vol low nibble: master output volume at maximum
FRAME_DT = datetime.timedelta(seconds=1.0 / FPS)

# --- C64-flavor knobs (only used when render(c64=True)) ---------------------------------------
# The faithful path renders flat 50%-duty pulses, no filter, and pure software volume. These
# re-introduce the three signatures that make a SID sound unmistakably "C64". They are aesthetic
# values chosen by ear, not measured from hardware.
PWM_MIN, PWM_MAX = 0x100, 0x900       # 12-bit duty sweep bounds (~6%..56%): a moving duty is the
PWM_HZ = 0.8                          # signature buzzy/hollow C64 lead. Slow LFO, offset per voice.
FILTER_RES = 0x0B                     # resonance nibble (0..15): high -> squelchy/analog character
FC_MIN, FC_MAX = 500, 1600            # 11-bit filter-cutoff sweep bounds: a slow "wah" over the tune
FC_HZ = 0.15
C64_ATTACK, C64_DECAY = 0x0, 0x8      # fast attack + moderate decay == the percussive pluck
C64_SUSTAIN, C64_RELEASE = 0xA, 0x9   # hold the note body at ~2/3, then ring it off on note release
RETRIG_GAP_MS = 1.5                   # gate-low gap that forces reSID's ADSR to restart mid-note:
                                      # an attack retriggers only on a gate 0->1 edge, so a new note
                                      # on an already-gated voice needs this brief drop first
PITCH_ONSET_RATIO = 2.0 ** (0.5 / 12.0)   # >= half a semitone pitch move == a new note -> re-pluck


def _channel_plan(frames):
    """Per-frame SID drive data for the three channels.

    Returns ``fn`` (SID freq value) and ``wave`` (ControlBits waveform, 0 = silent) per
    (frame, channel), plus what ``_render_voice`` needs to rebuild the YM amplitude at *audio*
    rate: the raw volume byte per (frame, channel) and the shared envelope step-rate/shape per
    frame. Amplitude is applied at audio rate so YM's fast hardware-envelope "buzz" survives as
    amplitude modulation on the SID oscillator (a SID has no hardware-envelope generator, so
    this AM is the faithful stand-in).
    """
    n = len(frames)
    fn = np.zeros((n, 3), dtype=np.int64)
    wave = np.zeros((n, 3), dtype=np.int64)
    vol = np.zeros((n, 3), dtype=np.int64)      # raw YM volume byte (bit 4 = envelope mode)
    env_f = np.zeros(n, dtype=np.float64)
    shape = np.zeros(n, dtype=np.int64)

    for fi, reg in enumerate(frames):
        tone_f, noise_f, envf = ym2149._decode(reg)
        mixer = reg[7]
        env_f[fi], shape[fi] = envf, reg[13]

        for c in range(3):
            tone_on = not (mixer & (1 << c))
            noise_on = not (mixer & (1 << (c + 3)))
            wave[fi, c] = int(C.PULSE) if tone_on else (int(C.NOISE) if noise_on else 0)
            # SID clocks its noise LFSR from the voice frequency, so a noise voice must be
            # driven by the YM noise rate (reg 6), not the channel's stale tone period.
            src_f = tone_f[c] if tone_on else noise_f
            fn[fi, c] = min(0xFFFF, int(round(src_f * SID_ACC_BITS / SID_CLOCK)))
            vol[fi, c] = reg[8 + c]
    return fn, wave, vol, env_f, shape


def _frame_amp(nsamp, vol, env_pos, env_f, shape):
    """YM channel amplitude across one frame's ``nsamp`` samples (constant or hardware-envelope)."""
    if vol & 0x10:                                        # envelope mode: level tracks the EG
        env_at = np.floor(env_pos + np.arange(nsamp) * (env_f / RATE)).astype(np.int64)
        return ym2149._VOL[ym2149._env_levels(env_at, shape)]
    return np.full(nsamp, ym2149._VOL[vol & 0x0f])        # fixed 4-bit level


def _new_sid(model, c64=False):
    sid = SID()
    sid.chip_model = model
    sid.clock_frequency = SID_CLOCK
    sid.sampling_frequency = float(RATE)
    sid.sampling_method = SamplingMethod.RESAMPLE
    sid.reset()
    if c64:                                       # route this voice through the resonant low-pass
        sid.write_register(W.Filter_Res_Filt, (FILTER_RES << 4) | int(ResFiltBits.Filt1))
        sid.write_register(W.Filter_Mode_Vol, int(ModeVolBits.LP) | MASTER_VOL_FULL)
    else:
        sid.write_register(W.Filter_Mode_Vol, MASTER_VOL_FULL)   # full master vol; no filter routing
    return sid


# SID voice-1 registers. Each YM channel is rendered in isolation (so its amplitude can be
# scaled independently in software), always on voice 1; the three renders are summed in render().
_V1 = (W.Voice1_Freq_Lo, W.Voice1_Freq_Hi, W.Voice1_Pw_Lo, W.Voice1_Pw_Hi,
       W.Voice1_Attack_Decay, W.Voice1_Sustain_Release, W.Voice1_Control_Reg)


def _render_voice(frames, fn, wave, vol, env_f, shape, retriggers, model, voice_idx=None):
    """Render one SID voice in isolation, scaling each frame by its YM amplitude at audio rate.

    ``voice_idx`` is accepted for a common dispatch with ``_render_voice_c64`` but unused here: the
    faithful path renders every voice identically (no per-voice PWM/filter phase offset).
    """
    f_lo, f_hi, pw_lo, pw_hi, ad, sr, ctrl = _V1
    sid = _new_sid(model)
    sid.write_register(pw_lo, PULSE_HALF & 0xFF)
    sid.write_register(pw_hi, (PULSE_HALF >> 8) & 0xFF)
    sid.write_register(ad, 0x00)          # attack/decay 0: jump to sustain instantly
    sid.write_register(sr, 0xF0)          # sustain 15 (full); software scaling supplies dynamics
    sid.write_register(ctrl, int(C.TEST)) # hard-restart: hold the oscillator at phase 0 so the
                                          # first gated note starts on a defined edge (no click)

    chunks = []
    env_pos = 16.0                        # matches ym2149: an untriggered env reads done
    for fi in range(len(frames)):
        if retriggers and retriggers[fi]:
            env_pos = 0.0                 # a reg-13 write restarts the envelope generator
        sid.write_register(f_lo, int(fn[fi]) & 0xFF)
        sid.write_register(f_hi, (int(fn[fi]) >> 8) & 0xFF)
        w = int(wave[fi])
        # Hold GATE high for the whole render and let the software amplitude do the muting: a
        # muted frame just drops the waveform bit (output goes to 0 while the envelope stays in
        # sustain), so notes never re-attack from a random phase -> no re-gate clicks.
        sid.write_register(ctrl, w | int(C.GATE))
        samples = np.asarray(sid.clock(FRAME_DT), dtype=np.float64)
        if w:
            samples *= _frame_amp(samples.size, int(vol[fi]), env_pos, env_f[fi], int(shape[fi]))
        else:
            samples[:] = 0.0                  # channel muted by the YM mixer this frame
        # Advance the envelope by the samples actually emitted (reSID returns ~882 ± a few per
        # frame); tying it to the real sample count keeps the AM aligned to the audio with no drift.
        env_pos += samples.size * (env_f[fi] / RATE)
        chunks.append(samples)
    return np.concatenate(chunks) if chunks else np.zeros(0)


def _sine_lfo(hz, frame_i, phase01):
    """LFO value in [-1, 1] sampled at 50 Hz frame ``frame_i``, phase-shifted by ``phase01`` turns."""
    return math.sin(2.0 * math.pi * (hz * frame_i / FPS + phase01))


def _pulse_width(frame_i, voice_idx):
    """Swept 12-bit pulse width for one frame; voices are LFO-offset so they don't buzz in lockstep."""
    center, half = (PWM_MIN + PWM_MAX) / 2.0, (PWM_MAX - PWM_MIN) / 2.0
    return int(center + half * _sine_lfo(PWM_HZ, frame_i, voice_idx / 3.0))


def _cutoff(frame_i):
    """Swept 11-bit filter cutoff for one frame (shared across voices -> a coherent chip-wide wah)."""
    center, half = (FC_MIN + FC_MAX) / 2.0, (FC_MAX - FC_MIN) / 2.0
    return int(center + half * _sine_lfo(FC_HZ, frame_i, 0.0))


def _set_cutoff(sid, fc):
    sid.write_register(W.Filter_Fc_Lo, fc & 0x07)     # 11-bit cutoff: 3 low bits + 8 high bits
    sid.write_register(W.Filter_Fc_Hi, (fc >> 3) & 0xFF)


def _note_onsets(fn, wave):
    """Frames where a new C64 note should be plucked: a channel becoming audible, or (on a tone
    voice) a pitch move of at least PITCH_ONSET_RATIO while it stays audible."""
    n = len(wave)
    onsets = np.zeros(n, dtype=bool)
    for fi in range(n):
        if not wave[fi]:                               # silent frame: nothing to gate
            continue
        if fi == 0 or not wave[fi - 1]:                # silence -> sound: the note starts
            onsets[fi] = True
        elif wave[fi] == int(C.PULSE) and fn[fi] > 0 and fn[fi - 1] > 0:
            ratio = max(fn[fi] / fn[fi - 1], fn[fi - 1] / fn[fi])
            onsets[fi] = ratio >= PITCH_ONSET_RATIO
    return onsets


def _render_voice_c64(frames, fn, wave, vol, env_f, shape, retriggers, model, voice_idx):
    """Render one voice with C64-native PWM + resonant filter + ADSR, scaled by YM amplitude.

    Where ``_render_voice`` plays a flat 50%-duty pulse with the gate held high and lets software
    volume do everything, this gates the SID ADSR per detected note (so each note gets a percussive
    attack), sweeps the pulse width and filter cutoff for the moving SID timbre, and still
    multiplies by the exact YM per-frame amplitude so the ST dynamics ride on top of the ADSR
    contour. To retrigger the attack on a note change while the gate is already high, the frame is
    split: a brief gate-low ``gap`` forces the release edge, then the body re-gates for a new attack.
    """
    f_lo, f_hi, pw_lo, pw_hi, ad, sr, ctrl = _V1
    sid = _new_sid(model, c64=True)
    sid.write_register(ad, (C64_ATTACK << 4) | C64_DECAY)
    sid.write_register(sr, (C64_SUSTAIN << 4) | C64_RELEASE)
    sid.write_register(ctrl, int(C.TEST))              # hold the oscillator at phase 0 until note 1

    onsets = _note_onsets(fn, wave)
    gap = datetime.timedelta(seconds=RETRIG_GAP_MS / 1000.0)
    body = FRAME_DT - gap

    chunks = []
    env_pos = 16.0                                     # matches ym2149: an untriggered env reads done
    gate_high = False
    for fi in range(len(frames)):
        if retriggers and retriggers[fi]:
            env_pos = 0.0                              # a reg-13 write restarts the envelope generator
        w = int(wave[fi])
        sid.write_register(f_lo, int(fn[fi]) & 0xFF)
        sid.write_register(f_hi, (int(fn[fi]) >> 8) & 0xFF)
        pw = _pulse_width(fi, voice_idx) if w == int(C.PULSE) else PULSE_HALF
        sid.write_register(pw_lo, pw & 0xFF)
        sid.write_register(pw_hi, (pw >> 8) & 0xFF)
        _set_cutoff(sid, _cutoff(fi))

        if not w:                                      # muted by the YM mixer this frame
            sid.write_register(ctrl, 0)                # gate low -> ADSR release (output zeroed below)
            samples = np.asarray(sid.clock(FRAME_DT), dtype=np.float64)
            samples[:] = 0.0
        elif onsets[fi] and gate_high:
            sid.write_register(ctrl, w)                # drop gate (keep waveform) for the release edge
            pre = np.asarray(sid.clock(gap), dtype=np.float64)
            sid.write_register(ctrl, w | int(C.GATE))  # re-gate: the 0->1 edge fires a fresh attack
            rest = np.asarray(sid.clock(body), dtype=np.float64)
            samples = np.concatenate([pre, rest])
        else:                                          # first attack, or a sustained note continuing
            sid.write_register(ctrl, w | int(C.GATE))
            samples = np.asarray(sid.clock(FRAME_DT), dtype=np.float64)
        if w:
            samples *= _frame_amp(samples.size, int(vol[fi]), env_pos, env_f[fi], int(shape[fi]))
        gate_high = bool(w)
        env_pos += samples.size * (env_f[fi] / RATE)
        chunks.append(samples)
    return np.concatenate(chunks) if chunks else np.zeros(0)


DC_BLOCK_HZ = 20                      # AC-coupling corner: a real C64 outputs through a cap,
                                      # removing the DC pedestal a unipolar SID pulse leaves
FADE_IN_MS = 10                       # ramp in from silence to swallow reSID's reset/filter
                                      # settling transient (all voices ramp from phase 0)


def _dc_block(x):
    """Remove slow DC drift (subtract a local mean) — mimics the C64's output AC coupling.

    reSID's pulse/noise output is unipolar, so held or phase-aligned voices leave a
    time-varying DC pedestal that a single global mean-subtraction can't. Subtract a local
    mean over a ``DC_BLOCK_HZ`` window; the window shrinks at the ends so the startup pedestal
    is removed too (a fixed-pad boxcar would leave it). O(n) via cumsum."""
    n = x.size
    win = max(1, RATE // DC_BLOCK_HZ)
    if n <= win:
        return x - x.mean()
    half = win // 2
    c = np.cumsum(np.insert(x, 0, 0.0))               # prefix sums, length n + 1
    idx = np.arange(n)
    lo = np.maximum(0, idx - half)
    hi = np.minimum(n, idx + half + 1)
    ma = (c[hi] - c[lo]) / (hi - lo)                  # local mean over a window clipped at edges
    return x - ma


def render(frames, retriggers=None, model=ChipModel.MOS8580, c64=False):
    """Render captured YM ``frames`` (list of 16-int snapshots) on a SID to mono float PCM.

    ``c64=True`` engages the SID-native flavor (PWM + resonant filter + per-note ADSR) instead of
    the clinical transcode; see ``_render_voice_c64``.
    """
    if not frames:
        return np.zeros(0)
    fn, wave, vol, env_f, shape = _channel_plan(frames)
    render_voice = _render_voice_c64 if c64 else _render_voice
    voices = [render_voice(frames, fn[:, c], wave[:, c], vol[:, c],
                           env_f, shape, retriggers, model, c) for c in range(3)]

    length = min(v.size for v in voices)                  # reSID chunk sizes can differ by ±1
    out = _dc_block(sum(v[:length] for v in voices))      # AC-couple like the real C64 output

    nf = min(out.size, int(RATE * FADE_IN_MS / 1000))     # fade in from silence: kill the
    if nf:                                                # reset transient before it sets the peak
        out[:nf] *= np.sin(np.linspace(0.0, np.pi / 2, nf)) ** 2
    peak = np.abs(out).max()
    if peak > 1e-6:
        out /= peak * 1.05
    return out