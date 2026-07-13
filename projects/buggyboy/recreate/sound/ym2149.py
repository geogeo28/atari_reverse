"""YM2149 (Atari ST PSG) software synth: register-frame stream -> PCM.

Input is one 16-byte register snapshot per 50 Hz frame (as captured from the game's
sound driver); output is mono float samples. The chip is three square-wave tone channels
plus a noise source and one envelope generator, mixed per the mixer register and scaled by
a per-channel 4-bit volume (or the envelope when a channel selects it).

Only what a listening tool needs is modelled: exact DAC curve and envelope edge-cases are
approximated (~3 dB/step volume; the eight canonical envelope shapes). The tone/noise
*timing* is faithful — driven by the real 2 MHz ST clock and the captured periods.
"""
import numpy as np

CLOCK = 2_000_000        # ST YM2149 master clock (Hz)
FPS = 50                 # the sound driver steps once per VBL
RATE = 44100             # output rate; RATE/FPS = 882 samples per frame (integral)

# 4-bit volume -> linear amplitude, ~3 dB/step (level 0 is silence, 15 is full scale).
_VOL = np.array([0.0] + [2.0 ** ((v - 15) / 2.0) for v in range(1, 16)], dtype=np.float64)


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


def _decode(reg):
    """Pull per-channel tone frequencies, noise/env frequencies and flags from a snapshot."""
    tone_f = [CLOCK / (16.0 * ((reg[2 * c] | ((reg[2 * c + 1] & 0x0f) << 8)) or 1))
              for c in range(3)]
    noise_f = CLOCK / (16.0 * ((reg[6] & 0x1f) or 1))
    env_f = CLOCK / (256.0 * ((reg[11] | (reg[12] << 8)) or 1))
    return tone_f, noise_f, env_f


def render(frames, retriggers=None, rate=RATE):
    """Render captured register ``frames`` (list of 16-int snapshots) to mono float PCM.

    ``retriggers[fi]`` true means register 13 was (re)written on frame ``fi``; on real
    hardware that restarts the envelope generator, so we reset its phase there.
    """
    spf = rate // FPS
    out = np.zeros(len(frames) * spf, dtype=np.float64)
    j = np.arange(spf)

    tone_phase = [0.0, 0.0, 0.0]     # cycles, carried across frames for click-free tones
    noise_pos = 0.0                  # noise-tick position (fractional)
    env_pos = 16.0                   # envelope-step position; start past a full cycle so an
                                     # envelope that was never triggered (reg 13 unwritten) reads
                                     # as completed (silent for one-shot shapes), not freshly run

    for fi, reg in enumerate(frames):
        if retriggers and retriggers[fi]:
            env_pos = 0.0            # a reg-13 write restarts the envelope generator
        tone_f, noise_f, env_f = _decode(reg)
        mixer, shape = reg[7], reg[13]

        noise_at = noise_pos + j * (noise_f / rate)
        noise_bit = _NOISE[np.floor(noise_at).astype(np.int64) % _NOISE.size]
        noise_pos = noise_pos + spf * (noise_f / rate)

        env_at = np.floor(env_pos + j * (env_f / rate)).astype(np.int64)
        env_amp = _VOL[_env_levels(env_at, shape)]
        env_pos = env_pos + spf * (env_f / rate)

        frame = np.zeros(spf, dtype=np.float64)
        for c in range(3):
            phase = tone_phase[c] + j * (tone_f[c] / rate)
            tone_phase[c] = (tone_phase[c] + spf * (tone_f[c] / rate)) % 1.0
            tone_bit = (np.mod(phase, 1.0) < 0.5)

            tone_on = not (mixer & (1 << c))          # mixer bits set = channel disabled
            noise_on = not (mixer & (1 << (c + 3)))
            level = (tone_bit | (not tone_on)) & (noise_bit.astype(bool) | (not noise_on))

            vol = reg[8 + c]
            amp = env_amp if (vol & 0x10) else _VOL[vol & 0x0f]
            frame += level * amp

        out[fi * spf:(fi + 1) * spf] = frame

    out -= out.mean()                                 # drop the DC the unipolar mix leaves
    peak = np.abs(out).max()
    if peak > 1e-6:
        out /= peak * 1.05                            # normalise with a little headroom
    return out