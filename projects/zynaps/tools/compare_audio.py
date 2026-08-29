#!/usr/bin/env python3
"""Judge `out/audio/`'s dumps against a recording of the real game, on two surfaces.

    python3 projects/zynaps/tools/compare_audio.py          # needs ref_*.wav / ref_*.regs

`ref_capture.py` boots Zynaps in Hatari and writes, for the title screen and for a level-1 game, an
audio recording and the per-frame PSG register stream the game's own replayer produced.
`extract_audio.py` produces the same two things a completely different way — the original replayer
alone, under the kit's Musashi oracle, rendered by BuggyBoy's software synth. This compares them,
and the point of doing it on TWO surfaces is that they answer different questions:

  registers   Did the CAPTURE record the right stream? An exact per-frame comparison, so it is a
              yes/no about the bytes and not a measurement. It cannot see a renderer fault at all.
  audio       Does the RENDER sound like the machine? Headline figure is ALIGNMENT-FREE: the cosine
              of the two spans' average power spectra. A per-frame "dominant pitch within a
              semitone" figure is reported beside it, at an alignment anchored on the registers —
              but see `spectrum_agreement` for why it is the smaller of the two claims. Neither can
              see a capture fault: two different streams can measure the same.

WHAT AGREEMENT MEANS AND DOES NOT. Hatari's YM2149 is a model too — a much more scrutinised one,
band-limited and volume-tabled — so a high audio number is "two independent implementations agree",
not "this is the chip". The register surface is the stronger of the two: those bytes are the game's,
and Hatari only carried them.

WHY THE REGISTER MATCH IS PER-VOICE FOR EFFECTS. A whole-frame comparison is right for the title
music, which owns all three voices from the moment it starts. It is wrong for an effect: the game
plays one on the voice its `fa <chan>` header picks while the OTHER voices hold whatever the last
sound left in them, and `extract_audio.py` captures it from a silenced chip. So an effect is matched
on its own voice's registers — the two period bytes, the volume, and that channel's two mixer gates
— which is the whole of what the chip does with it.

AND AN EFFECT'S AUDIO FIGURE IS A FLOOR, NOT A SCORE, for the same reason: Zynaps plays music under
the level, so the recording carries the other two voices while the effect sounds, and a one-voice
dump is being compared against a mix. The title screen has no such problem — there the tune owns
all three voices — which is why it is the number to quote.
"""
import argparse
import struct
import sys
import wave
from pathlib import Path

import numpy

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ref_capture                                  # noqa: E402  (the .regs reader and the paths)

DEFAULT_OUT_DIR = PROJECT / "out" / "audio"
FRAME_RATE = 50                                     # the VBL the driver ticks on
SAMPLE_RATE = 44100
SAMPLES_PER_FRAME = SAMPLE_RATE // FRAME_RATE       # 882

# --- the register surface -----------------------------------------------------------------------
YM_REGISTERS = 16
TICK_FLUSH_REGS = 11                                # registers 0..10: what `sound_tick` pushes
MIXER_REG = 7
MIXER_MASK = 0x3f                                   # 3 tone gates + 3 noise gates; bits 6-7 are I/O
VOLUME_REG_A = 8
VOLUME_ENVELOPE_BIT = 0x10
YM_CLOCK = 2_000_000                                # the ST's YM2149 master clock
NOISE_MIXER_SHIFT = 3
# How many consecutive frames have to match before a run counts as "this sound is in the recording".
# A single frame is worth nothing — a held note matches half the set — and half a second is longer
# than any two effects in this game share.
MIN_MATCH_FRAMES = 25
MAX_KEY_OCCURRENCES = 64
# The title music is matched over this many frames from wherever it was found. It is not the whole
# recording because the front end restarts pages (and with them, sometimes, the tune) while a 40 s
# recording is running, and one restart would score as a total mismatch rather than as a restart.
TITLE_MATCH_FRAMES = 1000

# --- the audio surface --------------------------------------------------------------------------
# One analysis window per 20 ms frame, but FOUR frames wide: 882 samples resolve only to 50 Hz,
# which is four semitones at the bottom of this music's range. 4096 samples with a parabolic fit on
# the peak resolves to about a hertz, which is a fraction of a semitone everywhere that matters.
ANALYSIS_WINDOW = 4096
PITCH_LOW_HZ, PITCH_HIGH_HZ = 60.0, 5000.0
SEMITONE = 2.0 ** (1.0 / 12.0)
# A frame quieter than this fraction of the track's peak has no pitch worth comparing; scoring one
# would measure which renderer's noise floor is louder.
SILENCE_FRACTION = 0.02
MIN_SCORED_FRAMES = 25                              # below this an agreement figure is noise
# The recording and the register trace come off one run but not off one clock: the trace's frame
# counter is read a moment before the recorder is told to start, and reading it is not free. The
# skew is FOUND (`audio_start_frame`) rather than assumed, over this many frames of candidates —
# 20 s, far more than any plausible gap.
MAX_SKEW_FRAMES = 1000
SKEW_SCORE_STRIDE = 5                               # every 5th frame is enough to score a candidate
# The alignment-free surface's analysis window. Long, because it is averaged over a whole span and
# only the shape of the average matters — 8192 samples resolve to 5.4 Hz, finer than a semitone
# anywhere in this music.
SPECTRUM_WINDOW = 8192
SPECTRUM_HOP = SPECTRUM_WINDOW // 2


def read_wav(path):
    """One WAV as mono float in -1..1, whatever channel count it carries."""
    with wave.open(str(path)) as handle:
        channels, width, rate = handle.getnchannels(), handle.getsampwidth(), handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    if width != 2 or rate != SAMPLE_RATE:
        raise SystemExit("%s is %d-bit at %d Hz; this compares 16-bit %d Hz files"
                         % (path, 8 * width, rate, SAMPLE_RATE))
    samples = numpy.frombuffer(raw, "<i2").astype(numpy.float64) / 32768.0
    return samples.reshape(-1, channels).mean(axis=1)


def read_ym(path):
    """The register frames of an uncompressed interleaved YM6 file, as `extract_audio.py` writes."""
    blob = Path(path).read_bytes()
    at = len(b"YM6!" + b"LeOnArD!")
    header = ">IIHIHIH"
    count = struct.unpack_from(header, blob, at)[0]
    at += struct.calcsize(header)
    for _string in range(3):                        # title, author, comment: NUL-terminated
        at = blob.index(b"\0", at) + 1
    body = blob[at:at + YM_REGISTERS * count]
    return [bytes(body[reg * count + frame] for reg in range(YM_REGISTERS))
            for frame in range(count)]


def voice_key(frame, voice):
    """Everything the chip does with one voice: its period, its level, and its two gates.

    Registers the voice does not own are left out on purpose — see the module docstring.
    """
    return (frame[2 * voice], frame[2 * voice + 1], frame[VOLUME_REG_A + voice],
            (frame[MIXER_REG] >> voice) & 1, (frame[MIXER_REG] >> (voice + NOISE_MIXER_SHIFT)) & 1)


def _keys(frames, voice):
    """`frames` projected onto one voice, or onto the whole tick flush when `voice` is None.

    "The whole flush" is registers 0..10 and not all sixteen: 11..13 are the envelope, which no tick
    writes, so a .ym frame carries 0xff there (the format's "not written this frame") and a frame
    read back out of a trace carries the chip's own 0. Comparing those would fail every frame for a
    reason that has nothing to do with the music.

    The mixer is masked for the same kind of reason: `note_on` ORs the two I/O-port DIRECTION bits
    into it, the chip takes them, and `extract_audio.py` masks them out of the .ym because YM5/YM6
    read that register's top bits as special-effect codes. They are not part of the mixer.
    """
    if voice is None:
        return [bytes(frame[:MIXER_REG]) + bytes([frame[MIXER_REG] & MIXER_MASK])
                + bytes(frame[MIXER_REG + 1:TICK_FLUSH_REGS]) for frame in frames]
    return [voice_key(frame, voice) for frame in frames]


def find_run(ref_frames, dump_frames, voice, minimum):
    """Where `dump_frames` starts inside `ref_frames`, and how long the two then agree.

    Returns (ref index, dump index, matching frames) for the longest agreement found, or None. The
    dump index is not always 0: the recorder was started mid-tune for the title, so the run begins
    at whatever point of the dump the machine had reached.
    """
    reference, dump = _keys(ref_frames, voice), _keys(dump_frames, voice)
    positions = {}
    for index, key in enumerate(dump):
        positions.setdefault(key, []).append(index)

    best = None
    for at in range(len(reference)):
        candidates = positions.get(reference[at], ())
        # A frame that occurs this often in the dump is a held note or a rest: it locates nothing,
        # and following every one of its positions is what turns this search quadratic.
        if len(candidates) > MAX_KEY_OCCURRENCES:
            continue
        for start in candidates:
            length = 0
            while (at + length < len(reference) and start + length < len(dump)
                   and reference[at + length] == dump[start + length]):
                length += 1
            if length < minimum or (best is not None and length <= best[2]):
                continue
            # A run in which the voice never CHANGES is not evidence that this sound is playing: an
            # idle voice sits at one register file, and so does any other sound's idle voice, so the
            # two match for as long as you care to compare them. Only a run that moves identifies.
            if len(set(dump[start:start + length])) < 2:
                continue
            best = (at, start, length)
    return best


def frame_features(samples):
    """Per 20 ms frame: (RMS, dominant frequency in Hz or 0 where the frame is silent).

    The dominant frequency is the interpolated peak of a Hann-windowed spectrum. It is not a pitch
    tracker and does not try to be: both signals are the same three square waves through different
    synths, so the loudest partial lands in the same place when the synths agree — which is exactly
    the question. Where they disagree it moves, and that is the measurement.
    """
    count = max(0, (len(samples) - ANALYSIS_WINDOW) // SAMPLES_PER_FRAME + 1)
    window = numpy.hanning(ANALYSIS_WINDOW)
    bin_hz = SAMPLE_RATE / ANALYSIS_WINDOW
    low, high = int(PITCH_LOW_HZ / bin_hz), int(PITCH_HIGH_HZ / bin_hz)
    rms = numpy.zeros(count)
    pitch = numpy.zeros(count)
    for index in range(count):
        block = samples[index * SAMPLES_PER_FRAME:index * SAMPLES_PER_FRAME + ANALYSIS_WINDOW]
        rms[index] = numpy.sqrt(numpy.mean(block ** 2))
        spectrum = numpy.abs(numpy.fft.rfft(block * window))
        peak = low + int(numpy.argmax(spectrum[low:high]))
        # A parabola through the peak and its neighbours, which is where the true frequency is when
        # it falls between two bins — without it the answer is quantised to 10.8 Hz.
        left, middle, right = spectrum[peak - 1], spectrum[peak], spectrum[peak + 1]
        divisor = left - 2 * middle + right
        offset = 0.5 * (left - right) / divisor if divisor else 0.0
        pitch[index] = (peak + offset) * bin_hz
    loud = rms > SILENCE_FRACTION * (rms.max() if len(rms) else 0.0)
    return rms, numpy.where(loud, pitch, 0.0)


def _spectra(samples):
    """Hann-windowed magnitude spectra, one per 20 ms frame, of `ANALYSIS_WINDOW` samples each."""
    count = max(0, (len(samples) - ANALYSIS_WINDOW) // SAMPLES_PER_FRAME + 1)
    window = numpy.hanning(ANALYSIS_WINDOW)
    return numpy.array([numpy.abs(numpy.fft.rfft(
        samples[index * SAMPLES_PER_FRAME:index * SAMPLES_PER_FRAME + ANALYSIS_WINDOW] * window))
        for index in range(count)])


def loudest_fundamental(frame):
    """The tone frequency of the loudest channel the chip is actually sounding, or None.

    A channel with its tone gate shut, no level, or an envelope-mode level (this driver never
    retriggers the envelope, so those are silent) is not sounding. The chip reads a period of 0 as
    1, which is 125 kHz — nothing a recording can hold — so those are dropped too.
    """
    best = None
    for channel in range(3):
        if (frame[MIXER_REG] >> channel) & 1:
            continue
        level = frame[VOLUME_REG_A + channel] & 0x1f
        if not level or level & VOLUME_ENVELOPE_BIT:
            continue
        period = frame[2 * channel] | ((frame[2 * channel + 1] & 0x0f) << 8)
        hertz = YM_CLOCK / (16.0 * (period or 1))
        if PITCH_LOW_HZ <= hertz <= PITCH_HIGH_HZ and (best is None or level > best[0]):
            best = (level, hertz)
    return best[1] if best else None


def audio_start_frame(samples, frames):
    """Which register frame the recording's first sample belongs to. See MAX_SKEW_FRAMES.

    Scored against the REGISTERS rather than against the other render, because the registers say
    what each frame's fundamental must be — a fact, not a second opinion. A cross-correlation of the
    two renders' pitch tracks was tried first and is not usable here: three square waves sounding at
    once means the loudest partial is often not a fundamental at all, and the track it produces
    correlates about as well at the wrong offset as at the right one.
    """
    spectra = _spectra(samples)
    if not len(spectra) or not frames:
        return 0
    bin_hz = SAMPLE_RATE / ANALYSIS_WINDOW
    frame_means = spectra.mean(axis=1) + 1e-12
    # Once, not once per candidate skew: the same 2,500 register frames were being decoded for each
    # of a thousand skews. The bin is precomputed with it, so the inner loop is two array reads.
    bins = [None if hertz is None else int(round(hertz / bin_hz))
            for hertz in (loudest_fundamental(frame) for frame in frames)]

    # A skew past this leaves fewer register frames than there is audio to score them against; a
    # recording longer than its own trace (which a truncated trace would give) leaves none at all,
    # and the answer is then 0 rather than an index error.
    limit = min(MAX_SKEW_FRAMES, len(frames) - len(spectra) + 1)
    best, best_score = 0, -numpy.inf
    for skew in range(max(limit, 1)):
        score, scored = 0.0, 0
        for index in range(0, len(spectra), SKEW_SCORE_STRIDE):
            at = bins[index + skew] if index + skew < len(bins) else None
            if at is None:
                continue
            score += spectra[index, at - 1:at + 2].max() / frame_means[index]
            scored += 1
        if scored >= MIN_SCORED_FRAMES and score / scored > best_score:
            best, best_score = skew, score / scored
    return best


def spectrum_agreement(first, second):
    """How alike two signals' AVERAGE spectra are, 0..1 — the ALIGNMENT-FREE audio surface.

    The cosine of the two average power spectra's square roots, over the whole of each span rather
    than frame by frame. This is the headline audio figure here because it needs no alignment, and
    alignment is the hard part: the recorder does not start on a driver frame, and three square
    waves sounding at once make a dominant-pitch track too unstable to correlate (measured: scored
    against the recording's OWN registers, the loudest partial is the sounding fundamental in only
    41% of frames, so that is the ceiling of any pitch-agreement figure on this material).

    It cannot see a timing fault — two performances of different bars of the same tune average to
    the same spectrum, which is exactly what the register surface is for. It sees every difference
    of timbre, gain stage and filtering, which is what a renderer gets wrong.
    """
    def average(samples):
        count = (len(samples) - SPECTRUM_WINDOW) // SPECTRUM_HOP + 1
        if count < 1:
            return None
        window = numpy.hanning(SPECTRUM_WINDOW)
        total = sum(numpy.abs(numpy.fft.rfft(
            samples[at * SPECTRUM_HOP:at * SPECTRUM_HOP + SPECTRUM_WINDOW] * window)) ** 2
            for at in range(count))
        return total / (total.sum() + 1e-30)

    left, right = average(first), average(second)
    if left is None or right is None:
        return None
    return float(numpy.dot(numpy.sqrt(left), numpy.sqrt(right)))


def pitch_agreement(first, second, offset):
    """(fraction of frames agreeing within a semitone, frames scored) at a given alignment."""
    start_first, start_second = max(offset, 0), max(-offset, 0)
    overlap = min(len(first) - start_first, len(second) - start_second)
    if overlap <= 0:
        return 0.0, 0
    left = first[start_first:start_first + overlap]
    right = second[start_second:start_second + overlap]
    scored = (left > 0) & (right > 0)
    if scored.sum() < MIN_SCORED_FRAMES:
        return 0.0, int(scored.sum())
    ratio = numpy.maximum(left[scored], right[scored]) / numpy.minimum(left[scored], right[scored])
    return float((ratio <= SEMITONE).mean()), int(scored.sum())


def compare_audio(ref_samples, dump_samples):
    """(spectrum agreement, pitch agreement, frames scored) of two spans of the same music."""
    _ref_rms, ref_pitch = frame_features(ref_samples)
    _dump_rms, dump_pitch = frame_features(dump_samples)
    agreement, scored = pitch_agreement(ref_pitch, dump_pitch, offset=0)
    return spectrum_agreement(ref_samples, dump_samples), agreement, scored


def aligned_spans(ref_samples, dump_samples, ref_frame, dump_frame, frames):
    """The two signals cut to the same music: `frames` frames from each side's own start frame.

    Either start can be NEGATIVE — the register run the frames come from often begins before the
    recorder was started — and the fix is to move the OTHER side forward by as much, never to clamp
    one of them alone, which would silently compare two different bars.
    """
    if ref_frame < 0:
        dump_frame, ref_frame = dump_frame - ref_frame, 0
    if dump_frame < 0:
        ref_frame, dump_frame = ref_frame - dump_frame, 0
    length = (frames + ANALYSIS_WINDOW // SAMPLES_PER_FRAME) * SAMPLES_PER_FRAME
    return (ref_samples[ref_frame * SAMPLES_PER_FRAME:ref_frame * SAMPLES_PER_FRAME + length],
            dump_samples[dump_frame * SAMPLES_PER_FRAME:dump_frame * SAMPLES_PER_FRAME + length])


def describe(spectrum, agreement, scored):
    return ("spectrum agreement %s; %.0f%% of %d scored 20 ms frames agree on pitch within a "
            "semitone" % ("%.3f" % spectrum if spectrum is not None else "n/a",
                          100 * agreement, scored))


def report_title(out_dir):
    """The title music: sound 0x0b, all three voices, matched whole-frame."""
    ref_frames = ref_capture.read_regs(out_dir / "ref_title.regs")
    dump_frames = read_ym(out_dir / "snd_11.ym")
    span = min(TITLE_MATCH_FRAMES, len(ref_frames))
    run = find_run(ref_frames[:span], dump_frames, voice=None, minimum=MIN_MATCH_FRAMES)
    if not run:
        print("title registers: NO run of %d frames of snd_11.ym appears in the recording"
              % MIN_MATCH_FRAMES)
        return
    ref_at, dump_at, length = run
    print("title registers: %d/%d frames of the recording replay snd_11.ym exactly, from its "
          "frame %d" % (length, span, dump_at))

    wav = out_dir / "snd_11.wav"
    if not wav.is_file():
        print("title audio:     snd_11.wav is not written (see manifest.tsv)")
        return
    ref_samples = read_wav(out_dir / "ref_title.wav")
    skew = audio_start_frame(ref_samples, ref_frames)
    ref_span, dump_span = aligned_spans(ref_samples, read_wav(wav), ref_at - skew, dump_at, length)
    print("title audio:     %s (recording starts at register frame %d)"
          % (describe(*compare_audio(ref_span, dump_span)), skew))


def report_level(out_dir, numbers):
    """Every effect the recording actually holds, found on its own voice and then listened to."""
    ref_frames = ref_capture.read_regs(out_dir / "ref_level1.regs")
    ref_samples = read_wav(out_dir / "ref_level1.wav")
    skew = None
    for number in numbers:
        dump_path = out_dir / ("snd_%02d.ym" % number)
        if not dump_path.is_file():
            continue
        dump_frames = read_ym(dump_path)
        for voice in range(3):
            run = find_run(ref_frames, dump_frames, voice, MIN_MATCH_FRAMES)
            if not run:
                continue
            ref_at, dump_at, length = run
            line = ("level1: sound %2d plays on voice %d — %d frames from the recording's frame %d "
                    "match the dump from its frame %d" % (number, voice + 1, length, ref_at, dump_at))
            wav = out_dir / ("snd_%02d.wav" % number)
            if wav.is_file():
                if skew is None:                   # one skew for the whole recording; found once
                    skew = audio_start_frame(ref_samples, ref_frames)
                ref_span, dump_span = aligned_spans(ref_samples, read_wav(wav),
                                                    ref_at - skew, dump_at, length)
                line += "; " + describe(*compare_audio(ref_span, dump_span))
            else:
                line += "; no .wav is written for it (see manifest.tsv)"
            print(line)
            break


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--numbers", type=int, nargs="*",
                        help="the sound numbers to look for in the level-1 recording "
                             "(default: every number the dump directory holds)")
    options = parser.parse_args()
    out_dir = options.out.resolve()
    missing = [name for name in ("ref_title.wav", "ref_title.regs", "ref_level1.wav",
                                 "ref_level1.regs") if not (out_dir / name).is_file()]
    if missing:
        raise SystemExit("%s has no %s — run tools/ref_capture.py first"
                         % (out_dir, ", ".join(missing)))
    numbers = options.numbers
    if numbers is None:
        numbers = sorted(int(path.stem[4:]) for path in out_dir.glob("snd_*.ym"))
    report_title(out_dir)
    report_level(out_dir, numbers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
