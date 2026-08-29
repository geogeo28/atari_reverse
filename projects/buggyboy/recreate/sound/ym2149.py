"""YM2149 (Atari ST PSG) software synth: register-frame stream -> PCM.

Input is one 16-byte register snapshot per 50 Hz frame (as captured from the game's
sound driver); output is mono float samples. The chip is three square-wave tone channels
plus a noise source and one envelope generator, mixed per the mixer register and scaled by
a per-channel 4-bit volume (or the envelope when a channel selects it).

Only what a listening tool needs is modelled: exact DAC curve and envelope edge-cases are
approximated (~3 dB/step volume; the eight canonical envelope shapes). The tone/noise
*timing* is faithful — driven by the real 2 MHz ST clock and the captured periods.

The output is BAND-LIMITED by oversampling (see OVERSAMPLE). That is not a refinement: the chip's
tone counter runs at CLOCK/16, so the shortest period it can be given is a 125 kHz square, and a
driver reaches that far more often than it sounds like it would — writing a tone period of 0 is
enough, and the chip reads a 0 period as 1. Sampled straight at 44100 Hz such a tone folds back
into the audio band at full amplitude and is the loudest thing in the render, while on the machine
it is an inaudible ultrasonic that the analog stage averages away.
"""
import numpy as np

CLOCK = 2_000_000        # ST YM2149 master clock (Hz)
FPS = 50                 # the sound driver steps once per VBL
RATE = 44100             # output rate; RATE/FPS = 882 samples per frame (integral)
CHANNELS = 3             # three square-wave tone channels sharing one noise source and one envelope

# 4-bit volume -> linear amplitude, ~3 dB/step (level 0 is silence, 15 is full scale).
_VOL = np.array([0.0] + [2.0 ** ((v - 15) / 2.0) for v in range(1, 16)], dtype=np.float64)

# Every channel is evaluated this many times per output sample, and each output sample is the MEAN
# of its interval — the same integration the machine's analog stage does. 8 puts the highest tone
# the chip can produce (CLOCK/16 = 125 kHz, from a period of 0 or 1) below the oversampled Nyquist.
#
# It ATTENUATES rather than removes: a mean over 8 samples is a box filter, and a square wave's own
# odd harmonics still fold. Measured on one channel at volume 15 with a period of 0, the render
# peaks at 0.125 against 0.249 for an audible note — 6 dB down, its loudest in-band component at
# 21.9 kHz, where nothing else in this workspace's material lives. That is the honest limit: it
# turns "the loudest thing in the file" into "an inaudible artefact at half level", and 16 was
# measured as worth 0.002 on the agreement against a recording of the real machine (docs/sound.md).
OVERSAMPLE = 8

# The loudest the mix can be: three channels, each fully on at volume 15. `render(normalise=False)`
# divides by this, which cannot clip (the unipolar sum never leaves 0..MIXED_FULL_SCALE) and keeps
# one render's loudness comparable with another's — which per-track normalisation destroys.
MIXED_FULL_SCALE = CHANNELS * _VOL[15]
_ALL_NOISE_GATES = 0b111000                # mixer bits 3-5, all set = no channel takes the noise
# The machine's audio output is AC-coupled, so the DC each unipolar square carries never reaches a
# speaker. Subtracting the track's own mean does not model that, because the DC MOVES with the
# volume registers: a tremolo leaves a full-depth sub-audio staircase in the render. Measured on
# Zynaps' title tune, that put 20% of the whole track's energy below 50 Hz against 8% in a recording
# of the real game. A moving mean over this many seconds is the coupling capacitor.
DC_BLOCK_SECONDS = 0.05                   # a corner near 20 Hz, well under the lowest tone
_NORMALISE_HEADROOM = 1.05                # a little room under full scale for the normalised path
_NORMALISE_FLOOR = 1e-6                   # below this the track is silence, and dividing is noise


def _lfsr_bitstream(n):
    """First ``n`` output bits of the YM2149 17-bit noise LFSR (taps at bits 0 and 3)."""
    bits = np.empty(n, dtype=np.float64)
    lfsr = 1
    for i in range(n):
        bits[i] = lfsr & 1
        feedback = (lfsr ^ (lfsr >> 3)) & 1
        lfsr = (lfsr >> 1) | (feedback << 16)
    return bits


_NOISE = _lfsr_bitstream((1 << 17) - 1)   # one full LFSR period (2^17-1); indexed by noise-tick count


def _env_levels(steps, shape):
    """Envelope level (0..15) for an array of elapsed envelope steps, per shape (reg 13)."""
    cont, att, alt, hold = shape & 8, shape & 4, shape & 2, shape & 1
    pos = steps % 16
    cyc = steps // 16
    ramp = pos if att else 15 - pos                 # first period: up if attack, else down
    if not cont:                                    # shapes 0-7: one ramp, then silence
        return np.where(cyc == 0, ramp, 0)
    if hold:                                         # ramp once, then hold the end value
        held = (15 if att else 0)
        if alt:
            held = 15 - held
        return np.where(cyc == 0, ramp, held)
    if alt:                                          # triangle: direction flips each period
        rising = (cyc % 2 == 0) == bool(att)
        return np.where(rising, pos, 15 - pos)
    return ramp                                      # sawtooth: repeat the ramp


def _dc_block(samples, window):
    """Subtract a moving mean over ``window`` samples: the AC coupling on the audio output.

    A moving mean is a linear-phase high-pass whose corner the window sets. The alternative — one
    mean for the whole track — leaves exactly the DC the volume registers move; see DC_BLOCK_SECONDS.
    """
    if window < 2 or window >= len(samples):
        return samples - samples.mean()
    before, after = window // 2, window - window // 2 - 1
    padded = np.concatenate((np.full(before, samples[0]), samples, np.full(after, samples[-1])))
    running = np.concatenate(([0.0], np.cumsum(padded)))
    return samples - (running[window:window + len(samples)] - running[:len(samples)]) / window


def _decode(reg):
    """Pull per-channel tone frequencies, noise/env frequencies and flags from a snapshot.

    The ``or 1`` on each period is the chip and not a guard against dividing by zero: a period of 0
    reloads the same counter a period of 1 does, so both run at the divider's full rate.
    """
    tone_f = [CLOCK / (16.0 * ((reg[2 * c] | ((reg[2 * c + 1] & 0x0f) << 8)) or 1))
              for c in range(CHANNELS)]
    noise_f = CLOCK / (16.0 * ((reg[6] & 0x1f) or 1))
    env_f = CLOCK / (256.0 * ((reg[11] | (reg[12] << 8)) or 1))
    return tone_f, noise_f, env_f


def render(frames, retriggers=None, rate=RATE, normalise=True):
    """Render captured register ``frames`` (list of 16-int snapshots) to mono float PCM.

    ``retriggers[fi]`` true means register 13 was (re)written on frame ``fi``; on real
    hardware that restarts the envelope generator, so we reset its phase there.

    ``normalise`` divides by the track's own peak, which is what a single track played on its own
    wants. Pass False for the chip's own scale instead (``MIXED_FULL_SCALE``): quieter, but two
    renders are then comparable, and a track that is genuinely near-silent stays near-silent rather
    than being amplified into the loudest file in the set. Neither path can clip.
    """
    spf = rate // FPS
    steps = spf * OVERSAMPLE                          # evaluation points per frame
    step_rate = rate * OVERSAMPLE
    out = np.zeros(len(frames) * spf, dtype=np.float64)
    j = np.arange(steps)

    tone_phase = [0.0] * CHANNELS    # cycles, carried across frames for click-free tones
    noise_pos = 0.0                  # noise-tick position (fractional)
    env_pos = 16.0                   # envelope-step position; start past a full cycle so an
                                     # envelope that was never triggered (reg 13 unwritten) reads
                                     # as completed (silent for one-shot shapes), not freshly run

    for fi, reg in enumerate(frames):
        if retriggers and retriggers[fi]:
            env_pos = 0.0            # a reg-13 write restarts the envelope generator
        tone_f, noise_f, env_f = _decode(reg)
        mixer, shape = reg[7], reg[13]

        # The two shared sources are built only when a channel asks for them, and their positions
        # advance either way: they are scalars, so a frame that wants neither costs nothing. This
        # is a quarter of the render's time on music that uses neither, which is most of it.
        wants_noise = (mixer & _ALL_NOISE_GATES) != _ALL_NOISE_GATES
        wants_envelope = any(reg[8 + c] & 0x10 for c in range(CHANNELS))

        noise_bit = None
        if wants_noise:
            noise_at = noise_pos + j * (noise_f / step_rate)
            noise_bit = _NOISE[np.floor(noise_at).astype(np.int64) % _NOISE.size].astype(bool)
        noise_pos = noise_pos + steps * (noise_f / step_rate)

        env_amp = None
        if wants_envelope:
            env_at = np.floor(env_pos + j * (env_f / step_rate)).astype(np.int64)
            env_amp = _VOL[_env_levels(env_at, shape)]
        env_pos = env_pos + steps * (env_f / step_rate)

        frame = np.zeros(steps, dtype=np.float64)
        for c in range(CHANNELS):
            phase = tone_phase[c] + j * (tone_f[c] / step_rate)
            tone_phase[c] = (tone_phase[c] + steps * (tone_f[c] / step_rate)) % 1.0

            vol = reg[8 + c]
            amp = env_amp if (vol & 0x10) else _VOL[vol & 0x0f]
            if not np.any(amp):                       # a silent channel still has to advance its
                continue                              # phase, but contributes nothing to the mix

            tone_on = not (mixer & (1 << c))          # mixer bits set = channel disabled
            noise_on = not (mixer & (1 << (c + CHANNELS)))
            tone_bit = (np.mod(phase, 1.0) < 0.5) if tone_on else None
            if tone_on and noise_on:
                level = tone_bit & noise_bit
            elif tone_on:
                level = tone_bit
            elif noise_on:
                level = noise_bit
            else:
                level = True                          # both gates shut: the DAC is held, i.e. DC
            frame += level * amp

        # ...and the output sample is the MEAN of its interval: the analog stage's integration, and
        # what keeps a tone above the output Nyquist out of the audio band instead of folded into it.
        out[fi * spf:(fi + 1) * spf] = frame.reshape(spf, OVERSAMPLE).mean(axis=1)

    out = _dc_block(out, int(round(rate * DC_BLOCK_SECONDS)))
    if not normalise:
        return out / MIXED_FULL_SCALE
    peak = np.abs(out).max()
    if peak > _NORMALISE_FLOOR:
        out /= peak * _NORMALISE_HEADROOM
    return out