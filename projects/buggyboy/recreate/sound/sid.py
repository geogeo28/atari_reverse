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
``render`` instead plays it like a native C64 playroutine — the SID's own ADSR shapes each note
(gated on note events recovered from the register stream), through a resonant low-pass with a
swept pulse width, with one constant velocity gain per note rather than the ST's per-frame
software volume (see ``_render_voice_c64``). Output is mono float in [-1, 1].
"""
import datetime
import math
from functools import partial

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

# --- C64-native knobs (only used when render(c64=True)) ---------------------------------------
# Unlike the faithful path (flat 50%-duty pulse, no filter, per-frame software volume), the C64
# path plays like a real C64 playroutine: the SID's own ADSR shapes each note, gated on note
# events recovered from the register stream, and the only software gain is one constant per note
# (its velocity) -- no per-sample volume, so the ADSR contour is never fought or crushed. These
# are aesthetic values chosen by ear, not measured from hardware.
PWM_MIN, PWM_MAX = 0x100, 0x900       # 12-bit duty sweep bounds (~6%..56%): a moving duty is the
PWM_HZ = 0.8                          # signature buzzy/hollow C64 lead. Slow LFO, offset per voice.
FILTER_RES = 0x08                     # resonance nibble (0..15): some analog character, not squelchy
FC_MIN, FC_MAX = 800, 2000            # 11-bit filter-cutoff sweep bounds: bright, with a slow "wah"
FC_HZ = 0.15
C64_ATTACK, C64_DECAY = 0x0, 0x8      # instant attack + moderate decay: a defined note edge...
C64_SUSTAIN, C64_RELEASE = 0x06, 0x0A # ...to a plucky held body, ringing off on note release
LEVEL_EPS = 1e-3                      # YM amplitude at/under this == the channel is silent this frame
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


def _note_velocity(vol_byte):
    """One constant per-note gain in [0, 1] from a YM volume byte -- the SID has no per-voice
    volume register, so relative note loudness is applied in software (once per note, not per
    sample). Envelope-mode ("buzzer") channels have no fixed level, so they play as full-scale."""
    if vol_byte & 0x10:                                # bit 4: hardware-envelope mode
        return 1.0
    return float(ym2149._VOL[vol_byte & 0x0f])         # fixed 4-bit level -> linear amplitude


def _note_events(fn, wave, vol, retriggers):
    """Recover per-frame note ON/OFF gates + a velocity for each frame from the register stream.

    A channel is *audible* when the mixer routes it (wave != 0) and its YM level is above silence.
    A note starts (ON) when a channel becomes audible, when a tone voice's pitch jumps at least
    PITCH_ONSET_RATIO, or on a reg-13 retrigger; it ends (OFF) when the channel stops being audible.
    """
    n = len(wave)
    vel = np.array([_note_velocity(int(v)) for v in vol])
    audible = (wave != 0) & (vel > LEVEL_EPS)
    note_on = np.zeros(n, dtype=bool)
    note_off = np.zeros(n, dtype=bool)
    for fi in range(n):
        if audible[fi]:
            start = fi == 0 or not audible[fi - 1]
            pitch = (wave[fi] == int(C.PULSE) and fi > 0 and fn[fi] > 0 and fn[fi - 1] > 0
                     and max(fn[fi] / fn[fi - 1], fn[fi - 1] / fn[fi]) >= PITCH_ONSET_RATIO)
            retrig = bool(retriggers[fi]) if retriggers is not None else False
            note_on[fi] = start or pitch or retrig
        else:
            note_off[fi] = fi > 0 and audible[fi - 1]
    return note_on, note_off, vel


def _render_voice_c64(frames, fn, wave, vol, env_f, shape, retriggers, model, voice_idx,
                      c64_sustain=C64_SUSTAIN):
    """Render one voice like a native C64 playroutine: SID ADSR + PWM + resonant filter per note.

    The SID's hardware ADSR owns each note's dynamics, gated on the note events from
    ``_note_events``; the only software gain is one constant per note (its velocity). There is no
    per-sample volume envelope, so nothing fights or crushes the ADSR contour (that double-envelope
    was why the earlier transcode-with-ADSR sounded broken). ``env_f``/``shape`` are unused here:
    native mode replaces the YM envelope generator with the SID's own. ``c64_sustain`` (0..15) is
    the ADSR sustain level -- higher holds the note body fuller, lower makes it more percussive. A
    note change on an already-gated voice splits the frame -- a brief gate-low ``gap`` forces
    reSID's attack edge -- and a note-off drops the gate but keeps the waveform so the release rings.
    """
    f_lo, f_hi, pw_lo, pw_hi, ad, sr, ctrl = _V1
    sid = _new_sid(model, c64=True)
    sid.write_register(ad, (C64_ATTACK << 4) | C64_DECAY)
    sid.write_register(sr, ((c64_sustain & 0x0f) << 4) | C64_RELEASE)
    sid.write_register(ctrl, int(C.TEST))              # hold the oscillator at phase 0 until note 1

    note_on, note_off, vel = _note_events(fn, wave, vol, retriggers)
    gap = datetime.timedelta(seconds=RETRIG_GAP_MS / 1000.0)
    body = FRAME_DT - gap

    chunks = []
    velocity = 0.0                                     # held per-note gain (0 -> pre-note silence)
    last_wave = int(C.PULSE)                            # waveform kept selected during the release tail
    gate_high = False
    for fi in range(len(frames)):
        w = int(wave[fi])
        active_wave = w or last_wave                   # follow the live waveform; hold the last while ringing
        sid.write_register(f_lo, int(fn[fi]) & 0xFF)
        sid.write_register(f_hi, (int(fn[fi]) >> 8) & 0xFF)
        if active_wave == int(C.PULSE):                # sweep the duty of a live or ringing pulse
            pw = _pulse_width(fi, voice_idx)
            sid.write_register(pw_lo, pw & 0xFF)
            sid.write_register(pw_hi, (pw >> 8) & 0xFF)
        _set_cutoff(sid, _cutoff(fi))

        if note_on[fi]:
            velocity = float(vel[fi])
            if gate_high:                              # retrigger a still-sounding voice
                sid.write_register(ctrl, active_wave)  # drop gate (keep waveform) for the release edge
                pre = np.asarray(sid.clock(gap), dtype=np.float64)
                sid.write_register(ctrl, active_wave | int(C.GATE))  # re-gate: the 0->1 edge fires an attack
                rest = np.asarray(sid.clock(body), dtype=np.float64)
                samples = np.concatenate([pre, rest])
            else:                                      # first attack from a released/idle voice
                sid.write_register(ctrl, active_wave | int(C.GATE))
                samples = np.asarray(sid.clock(FRAME_DT), dtype=np.float64)
            gate_high = True
        else:
            if note_off[fi]:
                gate_high = False                      # note ended: enter release, keep it ringing
            sid.write_register(ctrl, active_wave | (int(C.GATE) if gate_high else 0))
            samples = np.asarray(sid.clock(FRAME_DT), dtype=np.float64)
        samples *= velocity                            # one constant gain for the whole note
        last_wave = active_wave
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


def render(frames, retriggers=None, model=ChipModel.MOS8580, c64=False, c64_sustain=C64_SUSTAIN):
    """Render captured YM ``frames`` (list of 16-int snapshots) on a SID to mono float PCM.

    ``c64=True`` plays it as a native C64 playroutine (SID ADSR + PWM + resonant filter) instead of
    the clinical transcode; ``c64_sustain`` (0..15) sets that mode's ADSR sustain level. See
    ``_render_voice_c64``.
    """
    if not frames:
        return np.zeros(0)
    fn, wave, vol, env_f, shape = _channel_plan(frames)
    render_voice = partial(_render_voice_c64, c64_sustain=c64_sustain) if c64 else _render_voice
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