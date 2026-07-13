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

Unused SID features (filter, ring-mod, sync, PWM sweeps) are left off: this is a faithful
port of the ST sound, not a re-scored native C64 tune. Output is mono float in [-1, 1].
"""
import datetime

import numpy as np
from pyresidfp import SoundInterfaceDevice as SID, WritableRegister as W, ControlBits as C
from pyresidfp.sound_interface_device import ChipModel, SamplingMethod

import ym2149  # sibling renderer: reuse its volume DAC, envelope shapes, and frame constants

FPS = ym2149.FPS               # 50 Hz driver frames — identical clock to the YM path
RATE = ym2149.RATE             # 44100; keeps SID and YM renders directly comparable
SID_CLOCK = SID.PAL_CLOCK_FREQUENCY   # PAL C64: ~985 kHz, and PAL VBL is 50 Hz like the ST
SID_ACC_BITS = 1 << 24                # SID phase accumulator: Fn = f * 2**24 / clock
PULSE_HALF = 0x800                    # 12-bit pulse width, 50% duty == a square wave
FRAME_DT = datetime.timedelta(seconds=1.0 / FPS)


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


def _new_sid(model):
    sid = SID()
    sid.chip_model = model
    sid.clock_frequency = SID_CLOCK
    sid.sampling_frequency = float(RATE)
    sid.sampling_method = SamplingMethod.RESAMPLE
    sid.reset()
    sid.write_register(W.Filter_Mode_Vol, 0x0F)   # master volume full; no filter routing
    return sid


# SID voice-1 registers. Each YM channel is rendered in isolation (so its amplitude can be
# scaled independently in software), always on voice 1; the three renders are summed in render().
_V1 = (W.Voice1_Freq_Lo, W.Voice1_Freq_Hi, W.Voice1_Pw_Lo, W.Voice1_Pw_Hi,
       W.Voice1_Attack_Decay, W.Voice1_Sustain_Release, W.Voice1_Control_Reg)


def _render_voice(frames, fn, wave, vol, env_f, shape, retriggers, model):
    """Render one SID voice in isolation, scaling each frame by its YM amplitude at audio rate."""
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


def render(frames, retriggers=None, model=ChipModel.MOS8580):
    """Render captured YM ``frames`` (list of 16-int snapshots) on a SID to mono float PCM."""
    if not frames:
        return np.zeros(0)
    fn, wave, vol, env_f, shape = _channel_plan(frames)
    voices = [_render_voice(frames, fn[:, c], wave[:, c], vol[:, c],
                            env_f, shape, retriggers, model) for c in range(3)]

    length = min(v.size for v in voices)                  # reSID chunk sizes can differ by ±1
    out = _dc_block(sum(v[:length] for v in voices))      # AC-couple like the real C64 output

    nf = min(out.size, int(RATE * FADE_IN_MS / 1000))     # fade in from silence: kill the
    if nf:                                                # reset transient before it sets the peak
        out[:nf] *= np.sin(np.linspace(0.0, np.pi / 2, nf)) ** 2
    peak = np.abs(out).max()
    if peak > 1e-6:
        out /= peak * 1.05
    return out