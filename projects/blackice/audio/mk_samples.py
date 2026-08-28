#!/usr/bin/env python3
"""mk_samples.py — build the STE DMA sample bank.

    python3 mk_samples.py                 # synthesize the six placeholder SFX -> sfx_bank.c/.h
    python3 mk_samples.py --wav-dir DIR   # build from DIR/<name>.wav instead, same six names

WHY BOTH PATHS. The game has no recorded SFX yet, and a pipeline that is only exercised by files
nobody has made is a pipeline nobody has tested. The synthesizer produces six sounds of the right
shape, length and level so the whole chain — pack, link, DMA, Hatari, WAV analysis — is real today;
--wav-dir is the door the recorded versions walk in through, and it lands the same bytes in the
same slots.

THE BINARY FORMAT (big-endian; dma_sfx.c's BANK_* constants are the other half of this):

     0  'SFX1'
     4  u16 sample count
     6  u16 reserved (0)
     8  count x (u32 offset from the blob's start, u32 length in bytes)
        the samples, each on an EVEN offset with an EVEN length

Samples are 8-bit SIGNED mono at the STE's 12.5 kHz DMA rate (mode code 01, actually 12517 Hz).
The STE's frame registers hold addresses, not counts, and it walks WORDS: an odd start or an odd
length would make the chip read one byte past the sound, so both are rounded up here rather than
being the player's problem at runtime.
"""
import argparse
import json
import pathlib
import sys
import wave

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out"

# The STE's DMA rate code 01. The chip divides its 50066 Hz master rate by 4, so the nominal
# "12.5 kHz" is really this; resampling to the nominal figure would drift a sample every ~7500.
SAMPLE_RATE_HZ = 12517

# The decimation filter for the --wav-dir path (see anti_alias). 0.45 of the OUTPUT rate leaves a
# little room below the 0.5 where folding starts, so the transition band has somewhere to be; 127
# taps is long enough for that transition to be steep at any realistic source rate and is still a
# millisecond of convolution on a modern host.
ANTI_ALIAS_CUTOFF_FRACTION = 0.45
ANTI_ALIAS_TAPS = 127
ANTI_ALIAS_MIN_TAPS = 15               # below this the kernel shapes nothing worth having

BANK_MAGIC = b"SFX1"
BANK_HEADER_BYTES = 8
BANK_ENTRY_BYTES = 8
BANK_SIZE_BUDGET = 100 * 1024          # the brief's ceiling for the whole blob

SAMPLE_MIN = -128
SAMPLE_MAX = 127
SAMPLE_FULL_SCALE = 127.0

# The six sounds, in the order audiotest.c fires them and mk_song.py's SFX macro table lists them,
# so index N is the same event on the DMA path and on the YM fallback.
SFX_NAMES = ["gunshot", "door", "pickup", "enemy_hit", "player_hurt", "enemy_death"]

SYNTH_SEED = 0x5350                    # fixed, so two builds produce byte-identical banks


def frames(seconds):
    return int(round(seconds * SAMPLE_RATE_HZ))


def time_axis(seconds):
    return np.arange(frames(seconds), dtype=np.float64) / SAMPLE_RATE_HZ


def decay(seconds, half_life):
    """An exponential fade — the envelope almost every impact sound wants."""
    return 0.5 ** (time_axis(seconds) / half_life)


def noise(rng, seconds):
    return rng.uniform(-1.0, 1.0, frames(seconds))


def low_pass(signal, cutoff_hz):
    """A one-pole filter, applied forwards. Enough to turn white noise into something with a body;
    numpy has no filter primitive and pulling in scipy for one pole would be the bigger cost."""
    alpha = 1.0 - np.exp(-2.0 * np.pi * cutoff_hz / SAMPLE_RATE_HZ)
    out = np.empty_like(signal)
    state = 0.0
    for index, value in enumerate(signal):
        state += alpha * (value - state)
        out[index] = state
    return out


def sweep(seconds, start_hz, end_hz):
    """A sine whose frequency glides from start to end — phase integrated so it does not click."""
    axis = time_axis(seconds)
    span = max(seconds, 1e-9)
    instantaneous = start_hz + (end_hz - start_hz) * (axis / span)
    return np.sin(2.0 * np.pi * np.cumsum(instantaneous) / SAMPLE_RATE_HZ)


def square(seconds, hz):
    return np.sign(np.sin(2.0 * np.pi * hz * time_axis(seconds)))


def synth_gunshot(rng):
    """A crack and a tail: full-scale noise through a fast decay, with a low thump under it."""
    seconds = 0.32
    crack = low_pass(noise(rng, seconds), 5200.0) * decay(seconds, 0.035)
    thump = sweep(seconds, 190.0, 60.0) * decay(seconds, 0.055) * 0.7
    return crack + thump


def synth_door(rng):
    """A heavy door: a slow scrape (band-ish noise, swelling then dying) over a low groan."""
    seconds = 0.90
    axis = time_axis(seconds)
    swell = np.clip(np.sin(np.pi * axis / seconds), 0.0, 1.0) ** 1.5
    scrape = (low_pass(noise(rng, seconds), 900.0) - low_pass(noise(rng, seconds), 200.0)) * swell
    groan = sweep(seconds, 84.0, 52.0) * swell * 0.55
    return scrape * 1.8 + groan


def synth_pickup(_rng):
    """Three rising blips — the one sound in the set that should feel like a reward."""
    seconds = 0.30
    step = seconds / 3.0
    out = np.zeros(frames(seconds))
    for index, hz in enumerate((660.0, 880.0, 1320.0)):
        blip = square(step, hz) * decay(step, 0.045) * 0.8
        start = frames(step) * index
        out[start:start + blip.size] += blip[:out.size - start]
    return out


def synth_enemy_hit(rng):
    """Short, dry, mid-range: a hit has to be legible under everything else."""
    seconds = 0.16
    body = low_pass(noise(rng, seconds), 2600.0) * decay(seconds, 0.022)
    click = sweep(seconds, 420.0, 240.0) * decay(seconds, 0.030) * 0.6
    return body * 1.4 + click


def synth_player_hurt(rng):
    """Falling and rough — the player's own damage should not be mistakable for an enemy's."""
    seconds = 0.45
    tone = sweep(seconds, 430.0, 110.0) * decay(seconds, 0.16)
    grit = low_pass(noise(rng, seconds), 1500.0) * decay(seconds, 0.07) * 0.5
    return tone + grit


def synth_enemy_death(rng):
    """A long collapse: a tone dropping two octaves into a noise tail."""
    seconds = 0.75
    tone = sweep(seconds, 320.0, 60.0) * decay(seconds, 0.22)
    tail = low_pass(noise(rng, seconds), 1100.0) * decay(seconds, 0.13) * 0.65
    return tone * 0.9 + tail


SYNTHESIZERS = {"gunshot": synth_gunshot, "door": synth_door, "pickup": synth_pickup,
                "enemy_hit": synth_enemy_hit, "player_hurt": synth_player_hurt,
                "enemy_death": synth_enemy_death}


def normalise(signal, headroom=0.94):
    """Scale to just under full scale. Every one of these is a foreground sound; the DMA voice has
    no mixer to lose a quiet sample in."""
    peak = float(np.max(np.abs(signal))) or 1.0
    return signal * (headroom / peak)


def to_signed_bytes(signal):
    quantised = np.clip(np.rint(normalise(signal) * SAMPLE_FULL_SCALE), SAMPLE_MIN, SAMPLE_MAX)
    return quantised.astype(np.int8).tobytes()


def anti_alias(data, rate):
    """Low-pass `data`, which is at `rate`, to below half the STE's rate — BEFORE it is decimated.

    WITHOUT THIS THE WAV PATH IS BROKEN AND SOUNDS FINE. Dropping samples to get from 44.1 kHz to
    12.5 kHz does not remove what is above 6.25 kHz; it FOLDS it back down. A cymbal or a sibilant
    comes out as a descending whistle somewhere in the middle of the sound, and the result is a
    plausible-sounding sample that no amount of listening identifies as an artefact of the tool
    rather than of the recording. The synthesized placeholders never showed it because they are
    generated at the target rate and have nothing up there to fold.

    A windowed-sinc kernel rather than the one-pole `low_pass` above: one pole is 6 dB per octave,
    which at this ratio still leaves most of the offending band in place. The cutoff is a fraction
    of the OUTPUT rate expressed in cycles per INPUT sample, which is what makes one kernel right
    for any source rate."""
    cutoff = ANTI_ALIAS_CUTOFF_FRACTION * SAMPLE_RATE_HZ / rate
    # An even tap count has no centre sample and would shift the sound half a sample; and a kernel
    # longer than the sound itself has nothing to convolve with.
    taps = min(ANTI_ALIAS_TAPS, data.size if data.size % 2 else data.size - 1)
    if taps < ANTI_ALIAS_MIN_TAPS:
        return data
    offsets = np.arange(taps) - (taps - 1) / 2.0
    kernel = 2.0 * cutoff * np.sinc(2.0 * cutoff * offsets) * np.hamming(taps)
    return np.convolve(data, kernel / kernel.sum(), mode="same")


def read_wav(path):
    """A WAV file -> mono float in [-1, 1] at SAMPLE_RATE_HZ, anti-aliased and then resampled."""
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    if width == 1:
        # WAV 8-bit is UNSIGNED; the STE's is signed. Getting this backwards is a full-scale DC
        # offset that sounds like a click and looks like a working pipeline.
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    elif width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    else:
        raise SystemExit(f"{path}: {width * 8}-bit WAV is not supported (use 8- or 16-bit)")
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    # Only downwards: a source already at or below the STE's rate has nothing above half of it to
    # fold, and filtering it would just take the top off a sample that was already band-limited.
    if rate > SAMPLE_RATE_HZ:
        data = anti_alias(data, rate)
    if rate != SAMPLE_RATE_HZ:
        count = int(round(data.size * SAMPLE_RATE_HZ / rate))
        data = np.interp(np.linspace(0.0, data.size - 1, count), np.arange(data.size), data)
    return data


def synthesize_placeholder(name, rng):
    return SYNTHESIZERS[name](rng)


def build_samples(wav_dir, names=None, synthesize=synthesize_placeholder, seed=SYNTH_SEED):
    """[(name, packed bytes)] for `names`, from `wav_dir/<name>.wav` when there is one and from
    `synthesize(name, rng)` otherwise.

    Parameterised because songs/blackice_sfx.py builds a SECOND bank with its own names, its own
    synthesizers and its own seed; the WAV path, the quantiser and the seeded RNG are the same
    machinery either way and there should be one copy of it. The defaults are this module's own
    six placeholders, so mk_samples.py's own behaviour is unchanged."""
    rng = np.random.default_rng(seed)
    samples = []
    for name in names if names is not None else SFX_NAMES:
        if wav_dir is not None:
            samples.append((name, to_signed_bytes(read_wav(wav_dir / f"{name}.wav"))))
        else:
            samples.append((name, to_signed_bytes(synthesize(name, rng))))
    return samples


def pack(samples):
    """Samples -> (blob, metadata). Offsets and lengths are rounded up to even (see the docstring);
    the pad byte is 0, which is silence in signed 8-bit."""
    table_bytes = BANK_HEADER_BYTES + len(samples) * BANK_ENTRY_BYTES
    body = bytearray()
    entries = []
    meta = []
    for name, data in samples:
        if len(body) & 1:
            body.append(0)
        offset = table_bytes + len(body)
        body.extend(data)
        if len(data) & 1:
            body.append(0)
        length = len(data) + (len(data) & 1)
        entries.append((offset, length))
        meta.append({"name": name, "offset": offset, "bytes": length,
                     "seconds": length / SAMPLE_RATE_HZ})

    header = bytearray(BANK_MAGIC)
    header += len(samples).to_bytes(2, "big") + (0).to_bytes(2, "big")
    for offset, length in entries:
        header += offset.to_bytes(4, "big") + length.to_bytes(4, "big")
    assert len(header) == table_bytes
    blob = bytes(header) + bytes(body)
    if len(blob) > BANK_SIZE_BUDGET:
        raise SystemExit(f"the bank is {len(blob)} bytes, over the {BANK_SIZE_BUDGET}-byte budget")
    return blob, {"rate_hz": SAMPLE_RATE_HZ, "bytes": len(blob), "samples": meta}


def c_array(name, blob):
    lines = [f"const unsigned char {name}[{len(blob)}] = {{"]
    for start in range(0, len(blob), 16):
        lines.append("    " + " ".join(f"0x{byte:02x}," for byte in blob[start:start + 16]))
    lines.append("};")
    return "\n".join(lines)


def write_bank_source(blob, meta, header_path, source_path, symbol):
    """The bank is linked in rather than Fread. It is rodata either way and dma_sfx_init takes a
    pointer and a length, so a game that wants it off the floppy passes the buffer and the number of
    bytes it actually read — nothing in the player knows the difference, and a short read is refused
    rather than played. THE SAMPLE DATA MUST STAY WORD-ALIGNED, hence the alignment attribute:
    pack() made every offset even RELATIVE to the blob, which is only an even address if the blob
    itself starts on one, and dma_sfx_init now checks both halves of that."""
    roster = "\n".join(f" *   {index}  {entry['name']:<12} {entry['bytes']:6d} B  "
                       f"{entry['seconds']:.2f} s" for index, entry in enumerate(meta["samples"]))
    header_path.write_text(f"""/* sfx_bank.h — GENERATED by mk_samples.py; edit that, not this.
 *
 * {len(meta['samples'])} samples, 8-bit signed mono at {meta['rate_hz']} Hz, {len(blob)} bytes:
{roster}
 */
#ifndef SFX_BANK_H
#define SFX_BANK_H

#define SFX_BANK_BYTES {len(blob)}
#define SFX_BANK_COUNT {len(meta['samples'])}

extern const unsigned char {symbol}[SFX_BANK_BYTES];

#endif /* SFX_BANK_H */
""")
    source_path.write_text(f"""/* sfx_bank.c — GENERATED by mk_samples.py; {len(blob)} bytes of samples. */
#include "sfx_bank.h"

__attribute__((aligned(2)))
{c_array(symbol, blob)}
""")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wav-dir", type=pathlib.Path,
                        help=f"build from <dir>/<name>.wav for {', '.join(SFX_NAMES)}")
    args = parser.parse_args()

    samples = build_samples(args.wav_dir)
    blob, meta = pack(samples)

    OUT.mkdir(exist_ok=True)
    (OUT / "sfx_bank.bin").write_bytes(blob)
    (OUT / "sfx_meta.json").write_text(json.dumps(meta, indent=1))
    write_bank_source(blob, meta, HERE / "sfx_bank.h", HERE / "sfx_bank.c", "sfx_bank")

    total = sum(entry["seconds"] for entry in meta["samples"])
    print(f"bank: {len(blob)} bytes (budget {BANK_SIZE_BUDGET}), {len(samples)} samples, "
          f"{total:.2f} s at {SAMPLE_RATE_HZ} Hz")
    for index, entry in enumerate(meta["samples"]):
        print(f"  {index}  {entry['name']:<12} {entry['bytes']:6d} B  {entry['seconds']:.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
