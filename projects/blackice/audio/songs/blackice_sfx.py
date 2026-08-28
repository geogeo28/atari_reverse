#!/usr/bin/env python3
"""blackice_sfx.py — the BLACK ICE DMA sample bank, synthesized.

    python3 songs/blackice_sfx.py                 -> blackice_sfx_bank.c/.h, out/blackice_sfx_*
    python3 songs/blackice_sfx.py --wav-dir DIR   -> the same slots from DIR/<name>.wav

A SEPARATE ENTRY POINT, not an edit to mk_samples.py: that tool's six placeholders are what the
demo .PRG and its 20-check verify run on, and they must keep landing byte-for-byte where they do.
Everything reusable — the rate, the packer, the WAV reader, the quantiser — is imported from it, so
there is still one definition of the bank format.

WHAT THESE ARE DESIGNED AS. Every one of the ten is a SOUND, not a shaped noise burst: each has a
pitch envelope a listener can follow, and the ICE-flavoured ones (spike, dissolve, and the buster's
own zap) are RING-MODULATED — a carrier multiplied by a second oscillator, which puts energy at the
sum and difference frequencies and nowhere else. That is the classic way to make something sound
synthetic and metallic rather than organic, and it is what the design's "cyan infrastructure vs
magenta ICE" asks the ICE cues to sound like.

THE LENGTHS AND PRIORITIES ARE IMPORTED, not restated. songs/blackice.py owns SFX_CATALOGUE —
DESIGN.md §16's table — and generates blackice_sfx_ids.h from it; this file reads the same list to
size and order the samples. That is what makes "index N is the same event on both paths" a fact
about the build rather than a promise in two docstrings.
"""
import argparse
import json
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
AUDIO_DIR = HERE.parent
sys.path.insert(0, str(AUDIO_DIR))

import blackice                                                         # noqa: E402  (after path)
import mk_samples                                                       # noqa: E402  (after path)
from mk_samples import (SAMPLE_RATE_HZ, decay, frames, low_pass, noise,  # noqa: E402
                        time_axis)

OUT = AUDIO_DIR / "out"

BANK_HEADER = AUDIO_DIR / "blackice_sfx_bank.h"
BANK_SOURCE = AUDIO_DIR / "blackice_sfx_bank.c"
BANK_SYMBOL = "blackice_sfx_bank"

# A different seed from mk_samples.SYNTH_SEED so the two banks' noise beds are independent — the
# verifier identifies a sample by cross-correlating it against the recording, and two banks sharing
# a noise sequence would be two sounds that correlate with each other.
SYNTH_SEED = 0x424943                  # 'BIC'

# The cue, its length and its priority, from the one place they are written down.
SFX_CATALOGUE = blackice.SFX_CATALOGUE
SFX_NAMES = [entry["name"] for entry in SFX_CATALOGUE]
SFX_SECONDS = blackice.SFX_SECONDS

# Every cue is ramped to zero over its last few milliseconds. The DMA stops dead at the end of a
# frame, so a sample that ends mid-waveform is a step to silence — an audible click, and the louder
# the sound the worse it is. Measured before this: sentry_charge ended at 30% of full scale.
SFX_FADE_OUT_MS = 4.0


# ------------------------------------------------------------------------------- oscillators ----

def phase_tone(instantaneous_hz):
    """A sine whose frequency is `instantaneous_hz`, one entry per sample.

    The phase is INTEGRATED rather than computed per sample from t*f: a sound whose pitch moves has
    a discontinuity at every sample if you do the latter, and it clicks all the way through."""
    return np.sin(2.0 * np.pi * np.cumsum(instantaneous_hz) / SAMPLE_RATE_HZ)


def exponential_hz(seconds, start_hz, end_hz):
    """A pitch glide that is straight in SEMITONES rather than in hertz — which is what "falling an
    octave" means, and what a linear ramp gets audibly wrong over a wide interval."""
    if start_hz <= 0.0 or end_hz <= 0.0:
        raise SystemExit("an exponential glide has no meaning through or from 0 Hz")
    axis = time_axis(seconds)
    return start_hz * (end_hz / start_hz) ** (axis / max(seconds, 1e-9))


def siren_hz(seconds, low_hz, high_hz, cycles):
    """The wail: the pitch swings sinusoidally between two frequencies `cycles` times."""
    axis = time_axis(seconds)
    swing = 0.5 - 0.5 * np.cos(2.0 * np.pi * cycles * axis / max(seconds, 1e-9))
    return low_hz + (high_hz - low_hz) * swing


def ring_modulate(carrier_hz, modulator_hz):
    """Carrier x modulator. The product has energy ONLY at the sum and difference frequencies, so
    the result is inharmonic — the sound of something synthetic, which is what ICE is."""
    return phase_tone(carrier_hz) * phase_tone(modulator_hz)


def constant_hz(seconds, hz):
    return np.full(frames(seconds), float(hz))


def harmonic_tone(instantaneous_hz, partials):
    """A tone built from `partials` = [(multiple, level), ...] of one moving fundamental."""
    return sum(level * phase_tone(instantaneous_hz * multiple) for multiple, level in partials)


def tremolo(seconds, hz, depth):
    """A gain that pulses between 1 - depth and 1 — the growl in the snarl, the beat in the siren."""
    return 1.0 - depth * (0.5 - 0.5 * np.cos(2.0 * np.pi * hz * time_axis(seconds)))


def fade_edges(signal, in_ms, out_ms):
    """Ramp the first and last few milliseconds to zero. A sustained sound that starts or stops at
    full amplitude is a step, and a step in an 8-bit sample is an audible click at both ends."""
    gain = np.ones(signal.size)
    rise = min(int(SAMPLE_RATE_HZ * in_ms / 1000), signal.size // 2)
    fall = min(int(SAMPLE_RATE_HZ * out_ms / 1000), signal.size // 2)
    if rise:
        gain[:rise] = np.linspace(0.0, 1.0, rise)
    if fall:
        gain[-fall:] = np.linspace(1.0, 0.0, fall)
    return signal * gain


def at(target, source, seconds_in):
    """Mix `source` into `target` starting `seconds_in` from the top, clipped to fit. Mutates
    `target` and returns nothing, so no call site can read as if it returned a new buffer."""
    if seconds_in < 0.0:
        raise SystemExit(f"a cue cannot place a layer at {seconds_in} s")
    start = frames(seconds_in)
    span = min(source.size, target.size - start)
    if span > 0:
        target[start:start + span] += source[:span]


# ------------------------------------------------------------------------------ the ten cues ----

def synth_buster_shot(rng):
    """The player's energy weapon. 0.10 s is DESIGN.md's own number, chosen so that the channel is
    idle half the time at the Buster's 0.20 s rate of fire — the sound has to be a stab, not a
    tail, or a second shot would sound like a stutter of the first."""
    seconds = SFX_SECONDS["buster_shot"]
    zap = ring_modulate(exponential_hz(seconds, 2400.0, 520.0), constant_hz(seconds, 780.0))
    click = low_pass(noise(rng, seconds), 3400.0) * decay(seconds, 0.006)
    return zap * decay(seconds, 0.018) + click * 0.55


def synth_spike_shot(rng):
    """The ICE-piercing round: heavier and more metallic than the Buster, and it has to be
    distinguishable from it in one hearing, because the two are the player's only two weapons."""
    seconds = SFX_SECONDS["spike_shot"]
    dart = ring_modulate(exponential_hz(seconds, 1500.0, 300.0), constant_hz(seconds, 430.0))
    chuff = low_pass(noise(rng, seconds), 4200.0) * decay(seconds, 0.012)
    body = phase_tone(exponential_hz(seconds, 700.0, 180.0)) * decay(seconds, 0.11) * 0.5
    return dart * decay(seconds, 0.085) + chuff * 0.6 + body


def synth_watchdog_snarl(rng):
    """The Watchdog going to ALERT. Two detuned saw-ish glides beating against each other under a
    28 Hz growl: the beat and the growl are what make it read as an animal instead of a machine,
    which is the point — the Watchdog is the one enemy that hunts."""
    seconds = SFX_SECONDS["watchdog_snarl"]
    partials = [(1.0, 1.0), (2.0, 0.45), (3.0, 0.22)]
    first = harmonic_tone(exponential_hz(seconds, 300.0, 150.0), partials)
    second = harmonic_tone(exponential_hz(seconds, 307.0, 148.0), partials)
    bed = low_pass(noise(rng, seconds), 1200.0) * 0.35
    growl = tremolo(seconds, 28.0, 0.55)
    return (first + second + bed) * growl * decay(seconds, 0.12)


def synth_sentry_charge(rng):
    """A capacitor winding up, then the snap of it letting go. The rise IS the tell — the player
    has 0.45 s of warning before a Sentry fires, and the sound has to spend all of it climbing."""
    seconds = SFX_SECONDS["sentry_charge"]
    snap_seconds = 0.05
    whine_hz = exponential_hz(seconds, 190.0, 1500.0)
    wobble = 1.0 + 0.02 * np.sin(2.0 * np.pi * 34.0 * time_axis(seconds)) * (
        time_axis(seconds) / seconds)
    whine = harmonic_tone(whine_hz * wobble, [(1.0, 1.0), (2.0, 0.3)])
    swell = (time_axis(seconds) / seconds) ** 1.6
    out = whine * swell
    snap = low_pass(noise(rng, snap_seconds), 5000.0) * decay(snap_seconds, 0.008)
    at(out, snap * 1.3, seconds - snap_seconds)
    return out


def synth_gate_open(rng):
    """A heavy servo: a low groan, a scrape swelling over it, and the clunk of the gate seating.
    The clunk is the part the player listens for — it is the frame the door is passable."""
    seconds = SFX_SECONDS["gate_open"]
    clunk_seconds = 0.09
    axis = time_axis(seconds)
    swell = np.clip(np.sin(np.pi * axis / seconds), 0.0, 1.0) ** 1.3
    groan = harmonic_tone(exponential_hz(seconds, 75.0, 48.0), [(1.0, 1.0), (2.0, 0.5), (4.0, 0.2)])
    scrape = (low_pass(noise(rng, seconds), 1100.0) - low_pass(noise(rng, seconds), 240.0)) * 2.0
    out = (groan * 0.8 + scrape) * swell * tremolo(seconds, 17.0, 0.3)
    clunk = (phase_tone(exponential_hz(clunk_seconds, 150.0, 70.0))
             + low_pass(noise(rng, clunk_seconds), 900.0) * 0.7) * decay(clunk_seconds, 0.020)
    at(out, clunk * 1.4, seconds - clunk_seconds)
    return out


def synth_token_grab(_rng):
    """The one reward sound in the set, and the only cue with a major interval in it: three rising
    blips a fifth and an octave apart, each with a shimmering fifth over it."""
    seconds = SFX_SECONDS["token_grab"]
    blip_hz = (784.0, 1175.0, 1568.0)                        # G5, D6, G6
    blip_seconds = seconds / len(blip_hz)
    out = np.zeros(frames(seconds))
    for index, hz in enumerate(blip_hz):
        shimmer = harmonic_tone(constant_hz(blip_seconds, hz), [(1.0, 1.0), (1.5, 0.35),
                                                                (2.0, 0.2)])
        at(out, shimmer * decay(blip_seconds, 0.038), index * blip_seconds)
    return out


def synth_trace_alarm(_rng):
    """The threshold warning: a two-tone alarm, high-low, that also drifts DOWN across its length.
    This one has to cut through the music at any tempo, so it is the most tonal thing in the bank —
    and it is the sound the whole trace mechanic hangs on."""
    seconds = SFX_SECONDS["trace_alarm"]
    tone_hz = (880.0, 660.0)
    segments = 6
    segment_seconds = seconds / segments
    drift = np.linspace(1.0, 0.97, frames(seconds))          # the alarm sags as the trace climbs
    out = np.zeros(frames(seconds))
    for index in range(segments):
        hz = tone_hz[index % len(tone_hz)]
        blast = harmonic_tone(constant_hz(segment_seconds, hz), [(1.0, 1.0), (3.0, 0.28)])
        shaped = fade_edges(blast * decay(segment_seconds, 0.9), 8.0, 25.0)
        at(out, shaped, index * segment_seconds)
    hum = phase_tone(constant_hz(seconds, 110.0)) * 0.22
    return (out + hum) * drift


def synth_player_hit(rng):
    """The player taking damage. Dry, hard and short: it must not be mistakable for an enemy's
    death, so it has a body thud no other cue in the bank has."""
    seconds = SFX_SECONDS["player_hit"]
    crack = low_pass(noise(rng, seconds), 3200.0) * decay(seconds, 0.018)
    thud = phase_tone(exponential_hz(seconds, 220.0, 65.0)) * decay(seconds, 0.075)
    bite = ring_modulate(constant_hz(seconds, 300.0), constant_hz(seconds, 90.0))
    return crack * 1.3 + thud * 1.1 + bite * decay(seconds, 0.045) * 0.5


def synth_enemy_dissolve(rng):
    """ICE coming apart. A ring-modulated tone falling three octaves crossfades into filtered
    noise: the thing stops being a tone and becomes static, which is the sound of the pattern that
    was holding it together going away."""
    seconds = SFX_SECONDS["enemy_dissolve"]
    collapse = ring_modulate(exponential_hz(seconds, 950.0, 110.0), constant_hz(seconds, 187.0))
    static = low_pass(noise(rng, seconds), 900.0)
    crossfade = time_axis(seconds) / seconds
    return collapse * decay(seconds, 0.15) * (1.0 - crossfade) + static * crossfade * 0.85


def synth_exfil_siren(rng):
    """A real siren, not a beep: the pitch swings sinusoidally between two frequencies two and a
    half times across 1.2 s, over a wind bed. At 100% trace this is the loudest thing in the mix
    and it locks the DMA channel for its whole length — which is exactly what the design wants it
    to mean."""
    seconds = SFX_SECONDS["exfil_siren"]
    wail = harmonic_tone(siren_hz(seconds, 520.0, 1150.0, 2.5), [(1.0, 1.0), (2.0, 0.38),
                                                                 (3.0, 0.14)])
    wind = low_pass(noise(rng, seconds), 700.0) * 0.18
    return fade_edges(wail * tremolo(seconds, 5.0, 0.2) + wind, 40.0, 90.0)


SYNTHESIZERS = {
    "buster_shot": synth_buster_shot,
    "spike_shot": synth_spike_shot,
    "watchdog_snarl": synth_watchdog_snarl,
    "sentry_charge": synth_sentry_charge,
    "gate_open": synth_gate_open,
    "token_grab": synth_token_grab,
    "trace_alarm": synth_trace_alarm,
    "player_hit": synth_player_hit,
    "enemy_dissolve": synth_enemy_dissolve,
    "exfil_siren": synth_exfil_siren,
}


def synthesize(name, rng):
    """One cue, ramped out so the DMA's hard stop is not a step. The fade is applied here and not
    inside each synthesizer so that no new cue can forget it."""
    return fade_edges(SYNTHESIZERS[name](rng), 0.0, SFX_FADE_OUT_MS)


# --------------------------------------------------------------------------- the C emitters -----

def write_bank_source(blob, meta):
    """Its own header guard and its own macro names, so this bank and mk_samples.py's demo bank can
    both be on an include path (and, in the harness, both be built) without colliding."""
    roster = "\n".join(f" *   {index}  {entry['name']:<16} {entry['bytes']:6d} B  "
                       f"{entry['seconds']:.2f} s  priority {entry['priority']}"
                       for index, entry in enumerate(meta["samples"]))
    BANK_HEADER.write_text(f"""/* blackice_sfx_bank.h — GENERATED by songs/blackice_sfx.py; edit that, not this.
 *
 * {len(meta['samples'])} samples, 8-bit signed mono at {meta['rate_hz']} Hz, {len(blob)} bytes:
{roster}
 */
#ifndef BLACKICE_SFX_BANK_H
#define BLACKICE_SFX_BANK_H

#define BLACKICE_SFX_BANK_BYTES {len(blob)}
#define BLACKICE_SFX_BANK_COUNT {len(meta['samples'])}

extern const unsigned char {BANK_SYMBOL}[BLACKICE_SFX_BANK_BYTES];

#endif /* BLACKICE_SFX_BANK_H */
""")
    BANK_SOURCE.write_text(f"""/* blackice_sfx_bank.c — GENERATED by songs/blackice_sfx.py; {len(blob)} bytes of samples.
 *
 * WORD-ALIGNED: pack() made every offset even RELATIVE to the blob, which is only an even address
 * — the one the STE's DMA frame registers can be given — if the blob itself starts on one. */
#include "blackice_sfx_bank.h"

__attribute__((aligned(2)))
{mk_samples.c_array(BANK_SYMBOL, blob)}
""")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wav-dir", type=pathlib.Path,
                        help=f"build from <dir>/<name>.wav for {', '.join(SFX_NAMES)}")
    args = parser.parse_args()

    samples = mk_samples.build_samples(args.wav_dir, SFX_NAMES, synthesize, SYNTH_SEED)
    blob, meta = mk_samples.pack(samples)
    for entry, cue in zip(meta["samples"], SFX_CATALOGUE):
        entry["priority"] = cue["priority"]

    OUT.mkdir(exist_ok=True)
    (OUT / "blackice_sfx_bank.bin").write_bytes(blob)
    (OUT / "blackice_sfx_meta.json").write_text(json.dumps(meta, indent=1))
    write_bank_source(blob, meta)

    total = sum(entry["seconds"] for entry in meta["samples"])
    print(f"blackice bank: {len(blob)} bytes (budget {mk_samples.BANK_SIZE_BUDGET}), "
          f"{len(samples)} samples, {total:.2f} s at {SAMPLE_RATE_HZ} Hz")
    for index, entry in enumerate(meta["samples"]):
        print(f"  {index}  {entry['name']:<16} {entry['bytes']:6d} B  {entry['seconds']:.2f} s  "
              f"priority {entry['priority']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
