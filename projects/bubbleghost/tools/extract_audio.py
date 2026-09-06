#!/usr/bin/env python3
"""Dump Bubble Ghost's (Atari ST, ERE Informatique / Accolade 1988) digitised speech.

Usage:
  python3 projects/bubbleghost/tools/extract_audio.py [OUT_DIR]

OUT_DIR defaults to `projects/bubbleghost/out/assets` (gitignored). Reads only
`projects/bubbleghost/bin/GHOST.VOI` and writes the WAV plus `voi_envelope.png`, the amplitude
envelope — the surface that shows the phrase's word structure without anyone here being able to
listen to it.

The evidence for everything below is in `notes/assets_survey.md` (the container) and
`notes/loader.md` (the player). What the code embodies:

* ONE SAMPLE, NOT SEVERAL. `bin/GHOST.LOA` plays [address, address+0x7594) as a single sample, and
  0x7594 = 30,100 = the whole of GHOST.VOI. So the five gaps an envelope finds are pauses BETWEEN
  WORDS of the "Welcome to Bubble Ghost" phrase, not sound boundaries, and the file is exported
  whole.

* THE BYTES PASS THROUGH UNTOUCHED. GHOST.LOA's Timer A handler biases each byte by 0x80 and uses
  it to index a table of PSG volume triples that runs loud-to-quiet — i.e. unsigned 8-bit PCM
  centred on 128, which is exactly WAV's own 8-bit format. Polarity is NOT normalised (inaudible,
  and leaving it alone keeps the WAV a byte-for-byte copy of the file).

* THE RATE IS 14,985 Hz. The LOA header's rate index 3 selects MFP Timer A prescaler /4, data 41,
  so 2,457,600 / (4 x 41) = 14,985.37 Hz. A WAV header holds an integer, so it is floored — 0.0024%
  low. CONFIRMED that index 3 is what plays: the game's loader pokes only the sample-ADDRESS field
  at +0x1e of the LOA image and leaves the rate word as shipped (notes/loader.md).

THE MUSIC AND THE IN-GAME EFFECTS ARE NOT HERE and no disk file holds them: both come from the PSG
synth engine and replayer inside GHOST.PRG. Capturing them needs the original code running under a
Musashi oracle with the $ff8800 writes logged, the way projects/zynaps/tools/extract_audio.py does
it — which needs a `recreate/` project this game does not have yet.
"""

import itertools
import os
import sys
import wave

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(PROJECT_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from st_pixels import to_rgb_image  # noqa: E402  (needs the path above)

BIN_DIR = os.path.join(PROJECT_DIR, "bin")
DEFAULT_OUT_DIR = os.path.join(PROJECT_DIR, "out", "assets")
VOI_NAME = "GHOST.VOI"
VOI_SOUND_NAME = "welcome"  # the phrase the one sample holds

# Unsigned 8-bit PCM: this is the value a silent sample sits on, and WAV's own 8-bit zero.
PCM_ZERO = 128
BYTES_PER_SAMPLE = 1
CHANNELS = 1

# The playback rate, from the MFP registers GHOST.LOA programs (see the docstring).
MFP_CLOCK_HZ = 2457600
TIMER_A_PRESCALE = 4   # Timer A control 1
TIMER_A_DATA = 41      # Timer A data 0x29
# Exactly 14985.3658... Hz; a WAV header holds an integer, and rounding down costs 0.0024%.
VOI_RATE_HZ = MFP_CLOCK_HZ // (TIMER_A_PRESCALE * TIMER_A_DATA)

ENVELOPE_WINDOW = 256  # ~17 ms at the real rate: long enough to ride over a waveform's zero
ENVELOPE_PNG_HEIGHT = 200
ENVELOPE_PNG_DECIMATION = 10  # one pixel column per this many samples
ENVELOPE_PNG_FULL_SCALE = 128  # |sample - 128| at the top of the plot
BACKGROUND_INDEX, WAVE_INDEX, ENVELOPE_INDEX = 0, 1, 2
ENVELOPE_PALETTE = [(0, 0, 0), (70, 70, 70), (240, 90, 90)]


def windowed_mean_deviation(samples, window, at_samples):
    """Mean |sample - 128| over a `window` centred on each of `at_samples`.

    A prefix sum makes every value one subtraction, and each mean is divided by its own CLIPPED
    span rather than by a running count: a full-window divisor at the tail made a constant input's
    last window/2 values ramp down to half of the true level.
    """
    totals = list(itertools.accumulate((abs(sample - PCM_ZERO) for sample in samples), initial=0))
    half = window // 2
    means = []
    for at in at_samples:
        start = max(0, at - half)
        stop = min(len(samples), at - half + window)
        means.append((totals[stop] - totals[start]) / (stop - start))
    return means


def write_wav(path, samples):
    with wave.open(path, "wb") as handle:
        handle.setnchannels(CHANNELS)
        handle.setsampwidth(BYTES_PER_SAMPLE)
        handle.setframerate(VOI_RATE_HZ)
        handle.writeframes(samples)


def waveform_stats(samples):
    """(DC offset from 128, peak deviation, RMS deviation) — the listen test stand-in."""
    deviations = [sample - PCM_ZERO for sample in samples]
    mean = sum(deviations) / len(deviations)
    rms = (sum(value * value for value in deviations) / len(deviations)) ** 0.5
    return mean, max(abs(value) for value in deviations), rms


def plot_row(deviation):
    """The pixel row a deviation from 128 plots at, 0 being the top of the picture."""
    scaled = int(deviation / ENVELOPE_PNG_FULL_SCALE * (ENVELOPE_PNG_HEIGHT - 1))
    return ENVELOPE_PNG_HEIGHT - 1 - max(0, min(ENVELOPE_PNG_HEIGHT - 1, scaled))


def write_envelope_png(path, samples):
    """The waveform under its smoothed envelope: the phrase's words show as separated bursts."""
    width = len(samples) // ENVELOPE_PNG_DECIMATION
    at_samples = [column * ENVELOPE_PNG_DECIMATION for column in range(width)]
    envelope = windowed_mean_deviation(samples, ENVELOPE_WINDOW, at_samples)
    rows = [[BACKGROUND_INDEX] * width for _ in range(ENVELOPE_PNG_HEIGHT)]
    for column, (at, mean) in enumerate(zip(at_samples, envelope)):
        for row in range(plot_row(abs(samples[at] - PCM_ZERO)), ENVELOPE_PNG_HEIGHT):
            rows[row][column] = WAVE_INDEX
        rows[plot_row(mean)][column] = ENVELOPE_INDEX
    to_rgb_image(rows, ENVELOPE_PALETTE).save(path)


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(BIN_DIR, VOI_NAME), "rb") as handle:
        samples = handle.read()

    name = "voi_%s_%dhz.wav" % (VOI_SOUND_NAME, VOI_RATE_HZ)
    write_wav(os.path.join(out_dir, name), samples)
    write_envelope_png(os.path.join(out_dir, "voi_envelope.png"), samples)

    seconds = len(samples) / VOI_RATE_HZ
    dc, peak, rms = waveform_stats(samples)
    print("%d bytes -> one %.2f s sample at %d Hz (DC %+.1f, peak %d, RMS %.1f) -> %s"
          % (len(samples), seconds, VOI_RATE_HZ, dc, peak, rms, out_dir))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT_DIR)
