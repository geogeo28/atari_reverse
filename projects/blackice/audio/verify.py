#!/usr/bin/env python3
"""verify.py — run a harness .PRG in Hatari and prove the audio really reaches the hardware.

    python3 verify.py              the demo tune and the six placeholder samples
    python3 verify.py --blackice   the BLACK ICE score and its ten cues (BICETEST.PRG)
    python3 verify.py --keep       do not re-run Hatari; analyse whatever is already in out/

TWO RUNS, ONE ANALYSER. Everything that differs between them — which .PRG, which ledger, the frame
the SFX rotation starts on, which song the pitch check reads — is in a RunProfile; every check
below is written against the profile and not against one of the two timelines. The BLACK ICE run
adds one check the demo has no material for: the recording's own pulse says WHICH of the four trace
band tempi is playing, which is the only surface that can catch a tempo switch that did not happen.

WHAT IT MEASURES, and why each surface is here rather than one of the others:

  the LEDGER (AUDIOLOG.BIN)  what the .PRG itself saw — the machine type, whether the song and the
        bank were accepted, which vblank-queue slot it took, how many frames ran, and the two timed
        loops the tick cost is computed from. This is the only surface that can say the driver's
        own state machine did what it was asked.
  the TRACE (--trace psg_write,dmasound)  what reached the chips, IN ORDER. A snapshot cannot say
        that the DMA frame registers were set BEFORE the play bit, or that the driver never touched
        the hardware envelope; a trace can.
  the AUDIO (Hatari's recording)  what came OUT. This is the one surface that fails when the
        registers are all correct and the sound is still wrong — which is exactly how the LMC1992
        mixer defect was found (see dma_sfx.c).

Each SFX is checked by CROSS-CORRELATING the recording against the very sample bytes mk_samples.py
packed, not by looking for "some energy". Energy appears whenever anything is loud; a correlation
of 0.7 at the right offset says that sound and no other one came out of the DMA at that frame.
"""
import argparse
import json
import os
import pathlib
import re
import struct
import subprocess
import sys
import wave

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out"
DISK = HERE / "disk"

# Hatari's own EmuTOS, which is the only ROM in this toolchain that supports the STE at all (the
# repo's TOS102/104 images are ST ROMs). Named here because the whole DMA half of the test is
# meaningless on a machine that does not have the hardware.
BUNDLED_EMUTOS = pathlib.Path("/opt/homebrew/Cellar/hatari/2.6.1/Hatari.app/Contents/Resources/"
                              "tos.img")
# An ST ROM for the fallback run: the same .PRG on a machine with no DMA sound at all.
ST_TOS = pathlib.Path("/Volumes/Workspace/repos/my_repos/atari/reverse/tools/hatari/TOS104US.img")

# `uk` is what makes EmuTOS come up in 50 Hz PAL. Left to `us` the machine runs a 60 Hz vblank, the
# tune plays 20% fast, and every frame-to-seconds mapping below is quietly wrong.
COUNTRY = "uk"
MACHINE_STE = "ste"
MACHINE_ST = "st"
# How many vblanks a run needs BESIDES its own frame loop: the ROM's boot, the tick benchmark's two
# timed loops and the ledger write. Expressed as an overhead rather than a total so a longer
# timeline cannot be silently truncated by a --run-vbls somebody forgot to move.
EMUTOS_BOOT_VBLS = 850
# The ST run needs more: a US TOS ROM ignores --country and comes up at a 60 Hz vblank, so the same
# frames of demo are the same count of a SHORTER vblank and the whole run finishes later in them.
ST_TOS_BOOT_VBLS = 2050
AUDIO_RATE_HZ = 44100

# audiotest.c's own constants, per build. Checked against the ledger rather than assumed: a .PRG
# built from a different audiotest.c fails the comparison instead of being measured against the
# wrong shape.
DEMO_FRAMES = 950
DEMO_SFX_FIRST_FRAME = 300
DEMO_SFX_LAST_FRAME = 850
# ...and the BLACKICE_MODE=1 build's, which must stay equal to audiotest.c's #if branch.
BICE_FRAMES = 3700
BICE_SFX_FIRST_FRAME = 2450
BICE_SFX_LAST_FRAME = 2900
BICE_TITLE_FRAMES = 400
BICE_BAND_FIRST_FRAME = BICE_TITLE_FRAMES + 1
BICE_BAND_FRAMES = 250
BICE_BAND_COUNT = 4
# The drum window: band 3 held at one tempo for 20 s, after its own tempo window has been measured.
BICE_DRUM_FIRST_FRAME = BICE_BAND_FIRST_FRAME + BICE_BAND_COUNT * BICE_BAND_FRAMES
BICE_DRUM_FRAMES = 1000
BICE_SONG_STEMS = ("blackice_title", "blackice_score", "blackice_death", "blackice_clear",
                   "blackice_exfil")

SFX_INTERVAL_FRAMES = 50
PROBE_EVENTS = 3           # the priority probe's three requests, past the rotation
LEDGER_MAGIC = 0x41554431
LEDGER_VERSION = 6
LEDGER_SFX_SLOTS = 16
LEDGER_DRUM_SLOTS = 160
LEDGER_DRUM_INDEX_MASK = 0xFF
LEDGER_DRUM_FRAME_SHIFT = 8
LEDGER_FIELDS = ("magic", "version", "text_probe", "machine_has_dma", "song_accepted",
                 "bank_accepted", "vbl_slot", "frames_run", "hz200_elapsed",
                 "bench_idle_iterations", "bench_hz200_idle", "bench_tick_iterations",
                 "bench_hz200_tick", "sfx_events", "dma_starts", "ym_starts", "sfx_refused",
                 "probe_claim_started", "probe_lower_started", "probe_preempt_started",
                 "drum_requests", "drum_started", "drum_window_hits", "drum_window_started")
VBL_SLOT_NONE = 0xFFFF

# The tick's budget, and the arithmetic that turns two 200 Hz counts into cycles.
TICK_CYCLE_BUDGET = 3000
CPU_HZ = 8_000_000
HZ200_RATE = 200
CYCLES_PER_HZ200 = CPU_HZ // HZ200_RATE

PAL_VBL_HZ = 50.0
VBL_RATE_TOLERANCE = 0.02

# Audio analysis.
SILENCE_BLOCK_MS = 20
SILENCE_RMS_FLOOR = 40.0          # out of 32767; EmuTOS's idle output is exactly 0
SILENT_BLOCK_BUDGET = 0.02        # of the run's window, once the music has started
MUSIC_RMS_FLOOR = 500.0
NOTE_SEGMENT_ANALYSE_MS = 180
NOTE_SEGMENT_SKIP_MS = 25         # past the attack, where the envelope is still climbing
# A segment is only checked when the whole analysed window fits INSIDE it. Analysing across the
# channel's next note averages two spectra and reads the peak somewhere between them, which looks
# like a driver that is slightly out of tune; and shortening the window instead costs the frequency
# resolution a 73 Hz bass needs. So the window is fixed and the segment has to be long enough.
NOTE_SEGMENT_MIN_MS = NOTE_SEGMENT_SKIP_MS + NOTE_SEGMENT_ANALYSE_MS
NOTE_PEAK_TOLERANCE = 0.04        # how far the measured peak may sit from the expected frequency
NOTE_PEAK_PROMINENCE = 3.0        # the peak, over the median magnitude of the analysed band
# A note is only checked when the window holds at least this many periods of its fundamental. Below
# that the FFT bin is a bigger share of the frequency than the tolerance is and the interpolated
# peak is not evidence either way: at 180 ms a 58 Hz note gets 10 cycles and a 5.5 Hz bin, which is
# 9% of the note. Excluding it is a statement about the measurement, not about the driver.
NOTE_MIN_CYCLES = 12
NOTE_SEARCH_BINS = 1.0            # ...but always look at least one FFT bin either side
NOTE_BAND_HZ = 2500.0             # squares put most of their energy in the low harmonics
NOTE_CHECK_LIMIT = 26      # enough segments to reach the second pattern, where the lead enters
NOTE_PASS_FRACTION = 0.9

# HOW A SAMPLE IS SAID TO HAVE PLAYED. The correlation alone is not the test: a short burst of
# filtered noise under a full arrangement correlates at 0.3 however perfectly it played, while a
# long tonal sample reaches 0.8, so any single floor either rejects the first or accepts anything.
# What separates them is the SHAPE of the correlation over time — a real match is a spike at one
# offset, and everything around it is the noise floor of correlating that sample against music. So
# the gate is the ratio of the peak to that floor, with a low absolute floor underneath it.
SFX_CORRELATION_FLOOR = 0.15
SFX_PEAK_RATIO_FLOOR = 3.0
SFX_BACKGROUND_MS = 450           # ...measured over this much either side, short of the 1 s
                                  # spacing so the NEXT firing is not in the background estimate
SFX_ANCHOR_SEARCH_MS = 400        # the first sample is found with a wide search...
SFX_SEARCH_MS = 40                # ...and the rest are held to the timeline it establishes
SFX_CORRELATE_MS = 120            # of each sample, which is enough to identify it

# HOW THE TRACE BAND IS MEASURED (BLACK ICE only). Every row of every score pattern carries a
# percussion hit, so the recording's amplitude envelope beats at exactly the row rate — vbl_hz /
# frames-per-row. The check is a CLASSIFICATION and not a frequency reading: the envelope is scored
# against all four candidate row rates the game can be in and has to pick its own. Scoring the
# fundamental together with two harmonics is what makes the four separable — the candidates are
# only 0.45 Hz apart at the fundamental, which is barely two bins of a five-second window, but
# 1.4 Hz apart at the third harmonic.
ENVELOPE_BLOCK_MS = 4
TEMPO_SETTLE_FRAMES = 40          # after a speed change the row in progress finishes at the old one
TEMPO_HARMONICS = 3
TEMPO_MARGIN = 1.10               # the winning candidate over the runner-up
TEMPO_RATE_MIN_HZ = 3.5           # the measured dominant rate is searched in this band...
TEMPO_RATE_MAX_HZ = 8.0           # ...which spans every speed the score is ever played at
# ...and it must also land on the band's OWN rate. The classification alone is relative — it
# says this window is more like band 2 than like the other three — and this says it is band 2's
# rate in absolute terms, which is what catches all four bands being wrong by the same factor.
TEMPO_RATE_TOLERANCE = 0.03

# HOW A DRUM IS SAID TO HAVE PLAYED. Not the cue test: the lane repeats the same four samples every
# few rows, so a hat correlates just as well with the NEXT hat and the peak-over-background ratio
# that identifies a one-off cue means nothing here. The question the lane actually raises is which
# of the four played at this row — so all four are correlated at the row's own instant and the
# strongest has to be the one the ledger says fired. That is a classification, and it is the
# strongest statement the audio can make about a sound that recurs.
DRUM_CORRELATE_MS = 45            # the most of a drum that is ever correlated...
DRUM_MIN_CORRELATE_MS = 12        # ...and the least, whatever its envelope says
DRUM_ENERGY_FRACTION = 0.90       # of the reference's energy: the rest is its own decayed tail
DRUM_SEARCH_MS = 20               # ...held to the window's anchor, which TRACKS the clock skew
DRUM_CLOCK_SEARCH_MS = 150        # how far the clock fit may look for a kick...
DRUM_CLOCK_INLIER_MS = 40         # ...and how far from the median an answer may be and be believed
DRUM_CLOCK_MIN_KICKS = 8          # the fit needs this many that agree, or it is not a clock
DRUM_CLOCK_SAMPLE = "kick"        # the loudest, least ambiguous thing in the lane
# THE LAG THE CLOCK FIT IS ALLOWED TO ABSORB. The fit has a slope and an offset, and the offset
# would otherwise swallow ANY constant error — a lane published a row late, a platform polling the
# take one frame behind — and still report a perfect identification. Measured, +8 frames (one whole
# row at band 3) scored 110/110 before this bound existed. What the offset is FOR is the vblank-to-
# DAC latency and the recording's own onset estimate, both of which are a frame or two.
DRUM_LAG_BUDGET_MS = 45.0


DRUM_IDENTIFY_FRACTION = 0.90     # of the window's hits, and of each sample's own hits
MISREAD_ROWS_SHOWN = 8            # of the misread hits, printed so a failure names itself

TRACE_FLAGS = "psg_write,dmasound"
PSG_ENVELOPE_FIRST_REG = 11       # registers 11-13; the driver must never write one

EPSILON = 1e-9                    # a divisor guard, where the quantity divided by cannot be 0


def fail(message):
    raise SystemExit(f"FAIL: {message}")


# --------------------------------------------------------------------------- the run profile ----

class RunProfile:
    """Everything that differs between the two harness builds, in one object.

    The demo's file names are unsuffixed and the BLACK ICE run's carry `-blackice`, so the two sets
    of recordings, traces and ledgers coexist in out/ and `--keep` can re-analyse either without
    having re-run the other."""

    def __init__(self, name, prg, ledger_name, frames, sfx_first_frame, sfx_last_frame,
                 note_meta_name, note_window_frames, bank_meta_name, bank_blob_name,
                 band_speeds=None, song_meta_names=()):
        self.name = name
        self.suffix = "" if name == "demo" else f"-{name}"
        self.prg = prg
        self.frames = frames
        self.sfx_first_frame = sfx_first_frame
        self.sfx_last_frame = sfx_last_frame
        self.note_window_frames = note_window_frames
        self.band_speeds = band_speeds
        # The STE run's record, kept aside the moment it is read. The plain-ST run that follows
        # writes its own over the top of the ledger, and analysing the STE recording against the ST
        # record rescales the timeline by the ratio of their vblank rates — 50 Hz against 60 —
        # which walks every later SFX out of its search window. `--keep` reads this copy.
        self.ledger = DISK / ledger_name
        self.ste_ledger = OUT / f"ledger-ste{self.suffix}.bin"
        self.avi = OUT / f"audio{self.suffix}.avi"
        self.wav = OUT / f"audio{self.suffix}.wav"
        self.trace = OUT / f"trace{self.suffix}.log"
        self.note_meta = OUT / note_meta_name
        self.song_metas = [OUT / f"{stem}_meta.json" for stem in song_meta_names]
        self.bank_meta = OUT / bank_meta_name
        self.bank_blob = OUT / bank_blob_name

    @property
    def rotation_events(self):
        return 1 + (self.sfx_last_frame - self.sfx_first_frame) // SFX_INTERVAL_FRAMES


def demo_profile():
    return RunProfile("demo", "AUDIOTEST.PRG", "AUDIOLOG.BIN", DEMO_FRAMES, DEMO_SFX_FIRST_FRAME,
                      DEMO_SFX_LAST_FRAME, "song_meta.json", DEMO_SFX_FIRST_FRAME,
                      "sfx_meta.json", "sfx_bank.bin", song_meta_names=("song",))


def read_band_speeds():
    """The four trace-band tempi, read from the score's own metadata rather than restated here —
    songs/blackice.py is the one place they are chosen."""
    path = OUT / "blackice_score_meta.json"
    if not path.exists():
        fail(f"no {path.name} — run `make verify-blackice`, which builds it")
    return json.loads(path.read_text())["band_speeds"]


def blackice_profile(band_speeds):
    return RunProfile("blackice", "BICETEST.PRG", "BICELOG.BIN", BICE_FRAMES,
                      BICE_SFX_FIRST_FRAME, BICE_SFX_LAST_FRAME, "blackice_title_meta.json",
                      BICE_TITLE_FRAMES, "blackice_sfx_meta.json", "blackice_sfx_bank.bin",
                      band_speeds=band_speeds, song_meta_names=BICE_SONG_STEMS)


# ------------------------------------------------------------------------------ running Hatari ---

def run_hatari(machine, tos, extra, log_name, prg, run_vbls):
    """One headless run. Returns Hatari's merged output; the caller reads the files it left."""
    args = ["hatari", "--machine", machine, "--tos", str(tos), "--country", COUNTRY,
            "--sound", str(AUDIO_RATE_HZ), "--fast-forward", "on", "--confirm-quit", "off",
            "--statusbar", "off", "--drive-led", "off", "--memsize", "1", "--monitor", "rgb",
            "--run-vbls", str(run_vbls), "--harddrive", str(DISK), "--auto", f"C:\\{prg}"] + extra
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    done = subprocess.run(args, env=env, stdin=subprocess.DEVNULL, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    OUT.mkdir(exist_ok=True)
    (OUT / log_name).write_text(done.stdout)
    if "Hatari" not in done.stdout:
        fail(f"Hatari printed no banner ({OUT / log_name}) — the run never started")
    return done.stdout


def run_ste(profile):
    """The measured run: audio recorded, both chips traced.

    `--disable-video on` is what makes the recording usable. Hatari's AVI recorder pulls one audio
    chunk per emulated frame either way, but with the video stream on, most of those chunks come
    back ALL ZERO — the samples are dropped while the frames are compressed. Audio-only is the
    supported shape for this and it is also ~200x smaller on disk.
    """
    profile.ledger.unlink(missing_ok=True)
    profile.avi.unlink(missing_ok=True)
    return run_hatari(MACHINE_STE, BUNDLED_EMUTOS,
                      ["--disable-video", "on", "--avirecord", "--avi-file", str(profile.avi),
                       "--trace", TRACE_FLAGS, "--trace-file", str(profile.trace)],
                      f"hatari-ste{profile.suffix}.log", profile.prg,
                      profile.frames + EMUTOS_BOOT_VBLS)


def run_st_fallback(profile):
    """The SAME .PRG on a plain ST: no DMA sound hardware, no cookie jar entry for one.

    It is the negative control for dma_sfx.c's whole detection story. What must happen is that the
    player refuses every request without writing a single $ffff89xx register, the SFX come out of
    the YM instead, and the program still ends normally."""
    profile.ledger.unlink(missing_ok=True)
    run_hatari(MACHINE_ST, ST_TOS, [], f"hatari-st{profile.suffix}.log", profile.prg,
               profile.frames + ST_TOS_BOOT_VBLS)
    return read_ledger(profile.ledger)


# ------------------------------------------------------------------------------- the .PRG ledger --

def read_ledger(path):
    if not path.exists():
        fail(f"the run left no {path.name} — the .PRG never reached its own teardown")
    raw = path.read_bytes()
    want = 4 * (len(LEDGER_FIELDS) + 2 * LEDGER_SFX_SLOTS + LEDGER_DRUM_SLOTS)
    if len(raw) != want:
        fail(f"{path.name} is {len(raw)} bytes, this parser expects {want} — audiotest.c's "
             f"record and this file have drifted apart")
    values = struct.unpack(f">{len(LEDGER_FIELDS)}I", raw[:4 * len(LEDGER_FIELDS)])
    record = dict(zip(LEDGER_FIELDS, values))
    tail = struct.unpack(f">{2 * LEDGER_SFX_SLOTS + LEDGER_DRUM_SLOTS}I",
                         raw[4 * len(LEDGER_FIELDS):])
    record["sfx_frame"] = list(tail[:LEDGER_SFX_SLOTS])
    record["sfx_index"] = list(tail[LEDGER_SFX_SLOTS:2 * LEDGER_SFX_SLOTS])
    # (frame << 8) | bank index, packed by audiotest.c's fire_drum_hit.
    packed = tail[2 * LEDGER_SFX_SLOTS:]
    hits = min(record["drum_window_hits"], LEDGER_DRUM_SLOTS)
    record["drum_hits"] = [(word >> LEDGER_DRUM_FRAME_SHIFT, word & LEDGER_DRUM_INDEX_MASK)
                           for word in packed[:hits]]
    if record["magic"] != LEDGER_MAGIC or record["version"] != LEDGER_VERSION:
        fail(f"{path.name} carries magic {record['magic']:#x} version {record['version']}, not "
             f"{LEDGER_MAGIC:#x} version {LEDGER_VERSION}")
    return record


def tick_cycles(record):
    """The tick's cost, from the two timed loops. Both loops run for about the same wall time on
    purpose (audiotest.c says why), so TOS's own interrupt overhead is in both and subtracts out."""
    per_call = lambda ticks, count: ticks * CYCLES_PER_HZ200 / count
    return (per_call(record["bench_hz200_tick"], record["bench_tick_iterations"])
            - per_call(record["bench_hz200_idle"], record["bench_idle_iterations"]))


def vbl_rate(record):
    return record["frames_run"] / (record["hz200_elapsed"] / HZ200_RATE)


# ---------------------------------------------------------------------------- the audio capture --

AVI_CHUNK_ID = re.compile(rb"^\d\d[a-z][a-z]$")
AVI_AUDIO_CHUNK = b"01wb"


def avi_audio(path):
    """The PCM out of Hatari's AVI, as int16 [samples, channels].

    The chunks are walked by hand rather than through a container library: Hatari leaves the RIFF
    and `movi` sizes at zero when the run ends at --run-vbls, so every index in the file is
    unusable and the chunk chain is the only thing that is not. It also does NOT pad odd-sized
    chunks to even, which the format requires, so a walk that assumes the padding desynchronises a
    few frames in — hence the one-byte resynchronise below."""
    data = path.read_bytes()
    offset = data.find(b"movi")
    if offset < 0:
        fail(f"{path} has no `movi` list — Hatari recorded no stream at all")
    offset += 4
    chunks = []
    while offset + 8 <= len(data):
        chunk_id = data[offset:offset + 4]
        if not AVI_CHUNK_ID.match(chunk_id):
            if AVI_CHUNK_ID.match(data[offset + 1:offset + 5]):
                offset += 1
                continue
            break
        size = struct.unpack("<I", data[offset + 4:offset + 8])[0]
        if chunk_id == AVI_AUDIO_CHUNK:
            chunks.append(data[offset + 8:offset + 8 + size])
        offset += 8 + size
    if not chunks:
        fail(f"{path} carries no {AVI_AUDIO_CHUNK.decode()} chunks — the run recorded no audio")
    samples = np.frombuffer(b"".join(chunks), dtype="<i2")
    return samples.reshape(-1, 2), len(chunks)


def write_wav(path, stereo):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(stereo.shape[1])
        handle.setsampwidth(2)
        handle.setframerate(AUDIO_RATE_HZ)
        handle.writeframes(stereo.astype("<i2").tobytes())


def block_rms(mono, block):
    count = mono.size // block
    return np.sqrt((mono[:count * block].reshape(count, block).astype(np.float64) ** 2).mean(axis=1))


def find_music_onset(mono):
    """The first sample of the .PRG's own output. EmuTOS's idle output is exactly zero, so the
    first block above the floor is the driver's first note and nothing else."""
    block = AUDIO_RATE_HZ * SILENCE_BLOCK_MS // 1000
    loud = np.nonzero(block_rms(mono, block) > SILENCE_RMS_FLOOR)[0]
    if loud.size == 0:
        fail("the recording is silent from end to end — nothing reached the DAC")
    return int(loud[0]) * block


# ---------------------------------------------------------------------------- the YM tone check --

def note_segments(meta, first_frame, last_frame):
    """Every stretch in [first_frame, last_frame) during which one channel holds one SUSTAINED tone.

    A segment ends at the channel's next event, whatever it is, because that is where the sounding
    note can change. Two kinds are dropped: percussion, because a spectral peak at its nominal
    period is exactly what it must NOT have; and any one-shot envelope, because it is over in a
    handful of frames and the window would be measuring the silence after it."""
    per_channel = {}
    for event in meta["events"]:
        per_channel.setdefault(event["channel"], []).append(event)
    segments = []
    for events in per_channel.values():
        for index, event in enumerate(events):
            end = events[index + 1]["frame"] if index + 1 < len(events) else last_frame
            # An arpeggiated instrument steps the pitch every frame, so its written root is in the
            # window for only its share of the chord and the peak there says nothing about the
            # driver. mk_song.py's metadata marks them; reading a chord as a detuned note is what a
            # checker that did not know this would do.
            if not (event["tone"] and event["sustains"]) or event.get("arpeggiated"):
                continue
            if event["frame"] < first_frame or event["frame"] >= last_frame:
                continue
            length_ms = (end - event["frame"]) * 1000.0 / PAL_VBL_HZ  # the song's own clock
            cycles = event["hz"] * NOTE_SEGMENT_ANALYSE_MS / 1000.0
            if length_ms >= NOTE_SEGMENT_MIN_MS and cycles >= NOTE_MIN_CYCLES:
                segments.append((event, end))
    segments.sort(key=lambda pair: pair[0]["frame"])
    return segments


def interpolate_peak(spectrum, index, bin_hz):
    """Where the peak at `index` really sits, interpolated across its two neighbours.

    A 73 Hz note in a 180 ms window sits between bins 5.5 Hz apart, so the raw bin is 1.6% out
    however right the driver is, and a tolerance loose enough to accept that would accept a
    semitone error too. Only applied where the bin really is a local maximum, and never by more
    than half a bin: that is the whole range a three-point parabola can legitimately move a peak,
    and off a maximum the divisor goes through zero and throws the answer across the spectrum."""
    peak_hz = float(index) * bin_hz
    if not 0 < index < spectrum.size - 1:
        return peak_hz
    left, centre, right = spectrum[index - 1], spectrum[index], spectrum[index + 1]
    divisor = left - 2.0 * centre + right
    if divisor < 0.0 and centre >= left and centre >= right:
        shift = 0.5 * (left - right) / divisor
        peak_hz += bin_hz * max(min(shift, 0.5), -0.5)
    return peak_hz


def spectral_peak(window, expected_hz):
    """(peak frequency near `expected_hz`, how far it stands over the band's median magnitude)."""
    spectrum = np.abs(np.fft.rfft(window * np.hanning(window.size)))
    freqs = np.fft.rfftfreq(window.size, 1.0 / AUDIO_RATE_HZ)
    bin_hz = float(freqs[1])
    band = freqs <= NOTE_BAND_HZ
    # The candidate band is the tolerance OR a couple of bins, whichever is wider: a short segment
    # is analysed in a short window, and a 4% tolerance around 73 Hz can be narrower than one bin —
    # which finds no candidate at all and reads as "the note is not there".
    reach = max(expected_hz * NOTE_PEAK_TOLERANCE, NOTE_SEARCH_BINS * bin_hz)
    near = band & (np.abs(freqs - expected_hz) <= reach)
    if not near.any():
        return 0.0, 0.0
    index = int(np.argmax(np.where(near, spectrum, 0.0)))
    median = float(np.median(spectrum[band])) or 1.0
    return interpolate_peak(spectrum, index, bin_hz), float(spectrum[index]) / median


def check_notes(mono, onset, meta, vbl_hz, window_frames):
    """How many of the first few sounding notes put a peak where the song says they should.

    The window is a MUSIC-ONLY stretch at the head of the run — the demo's is everything before the
    first SFX, and BLACK ICE's is the title theme, which plays alone before the score is bound — so
    nothing but one tune is in the spectrum."""
    rows = []
    skip = int(AUDIO_RATE_HZ * NOTE_SEGMENT_SKIP_MS / 1000)
    span = int(AUDIO_RATE_HZ * NOTE_SEGMENT_ANALYSE_MS / 1000)
    for event, _ in note_segments(meta, 0, window_frames)[:NOTE_CHECK_LIMIT]:
        start = onset + int(event["frame"] * AUDIO_RATE_HZ / vbl_hz) + skip
        window = mono[start:start + span].astype(np.float64)
        if window.size < span:
            break
        peak_hz, prominence = spectral_peak(window, event["hz"])
        error = abs(peak_hz - event["hz"]) / event["hz"] if peak_hz else 1.0
        rows.append({"frame": event["frame"], "channel": event["channel"],
                     "instrument": event["instrument"], "expected_hz": event["hz"],
                     "peak_hz": peak_hz, "error": error, "prominence": prominence,
                     "ok": error <= NOTE_PEAK_TOLERANCE and prominence >= NOTE_PEAK_PROMINENCE})
    return rows


# ---------------------------------------------------------------------------- the DMA SFX check --

def loudest_stretch(bank_meta, blob, index, correlate_ms, trim=False):
    """(the sample's LOUDEST `correlate_ms`, resampled to the recording's rate and normalised, how
    far into the sample that stretch starts).

    The loudest stretch and not the first: `door` opens on a swell that is near silence for a
    quarter of a second, and correlating that against a window with music in it scores no better
    than noise — the sound is present and the check would call it absent.

    `trim` then cuts the tail off, which the drum lane wants and the cues do not. A reference padded
    out with its own decay is mostly silence, and the correlation is normalised by the RECORDING's
    energy over the whole reference — so the silent part contributes nothing but the arrangement
    playing underneath it, a divisor with no matching numerator. The cues are one-offs measured
    against a background, where that costs nothing; the lane's four are compared with each other,
    where it is the difference between telling a hi-hat from a kick and not."""
    entry = bank_meta["samples"][index]
    data = np.frombuffer(blob[entry["offset"]:entry["offset"] + entry["bytes"]],
                         dtype=np.int8).astype(np.float64)
    keep = min(data.size, int(bank_meta["rate_hz"] * correlate_ms / 1000))
    energy = np.convolve(data ** 2, np.ones(keep), mode="valid")
    start = int(np.argmax(energy))
    window = data[start:start + keep]
    if trim:
        window = window[:trimmed_length(window, bank_meta["rate_hz"])]
    count = int(round(window.size * AUDIO_RATE_HZ / bank_meta["rate_hz"]))
    resampled = np.interp(np.linspace(0.0, window.size - 1, count), np.arange(window.size), window)
    lead = int(round(start * AUDIO_RATE_HZ / bank_meta["rate_hz"]))
    return resampled / (np.linalg.norm(resampled) or EPSILON), lead


def sample_reference(bank_meta, blob, index):
    """One CUE's reference: its loudest SFX_CORRELATE_MS, untrimmed."""
    return loudest_stretch(bank_meta, blob, index, SFX_CORRELATE_MS)


def correlation_profile(mono, centre, reference, span_ms):
    """|normalised correlation| of `reference` against the recording, for every offset within
    `span_ms` of `centre`, and the sample index the first of those offsets sits at.

    Normalising by the LOCAL window energy is what stops a loud passage of music scoring as a
    match on loudness alone."""
    span = int(AUDIO_RATE_HZ * span_ms / 1000)
    start = max(centre - span, 0)
    stop = min(centre + span + reference.size, mono.size)
    window = mono[start:stop].astype(np.float64)
    if window.size <= reference.size:
        return np.zeros(1), start
    raw = np.correlate(window, reference, mode="valid")
    energy = np.sqrt(np.convolve(window ** 2, np.ones(reference.size), mode="valid"))
    return np.abs(raw / np.maximum(energy, EPSILON)), start


def match_sample(mono, centre, reference, search_ms):
    """(peak correlation, its offset in ms, peak / background). See SFX_PEAK_RATIO_FLOOR.

    The BACKGROUND is what separates this from best_correlation: a cue fires once, so what says it
    played is a spike standing over the correlation of the same sample against the surrounding
    music. A drum recurs every few rows, which is why the lane is measured by comparison instead."""
    scores, start = correlation_profile(mono, centre, reference, SFX_BACKGROUND_MS)
    background = float(np.median(scores)) or EPSILON
    search = int(AUDIO_RATE_HZ * search_ms / 1000)
    low = max(centre - search - start, 0)
    high = min(centre + search - start + 1, scores.size)
    if high <= low:
        return 0.0, 0.0, 0.0
    best = low + int(np.argmax(scores[low:high]))
    return float(scores[best]), (start + best - centre) * 1000.0 / AUDIO_RATE_HZ, \
        float(scores[best]) / background


def check_sfx(mono, onset, record, bank_meta, blob, vbl_hz, last_frame):
    """Every fired SFX, identified in the recording by the bytes that were supposed to play.

    The FIRST one is searched over a wide window and its offset then corrects the timeline: the
    onset is only accurate to a frame or two, and every later check is held to the corrected
    anchor, so a sample that played at the wrong TIME fails even though it played."""
    rows = []
    anchor = onset
    # Clamped: the .PRG records only the first LEDGER_SFX_SLOTS events — audiotest.c's tally_sfx
    # guards the store and asserts at compile time that the count fits — so a run that somehow
    # reported more should fail a check, not IndexError out of the analyser.
    for slot in range(min(record["sfx_events"], LEDGER_SFX_SLOTS)):
        frame = record["sfx_frame"][slot]
        index = record["sfx_index"][slot]
        # The priority probe's three requests land on three consecutive frames and deliberately
        # interrupt each other; "did this sample play cleanly from here" is not a question that has
        # an answer there, and the ledger's own three answers are what checks that part.
        if frame > last_frame:
            break
        reference, lead = sample_reference(bank_meta, blob, index)
        centre = anchor + int((frame - 1) * AUDIO_RATE_HZ / vbl_hz) + lead
        search = SFX_ANCHOR_SEARCH_MS if slot == 0 else SFX_SEARCH_MS
        correlation, offset_ms, ratio = match_sample(mono, centre, reference, search)
        if slot == 0 and ratio >= SFX_PEAK_RATIO_FLOOR:
            anchor += int(offset_ms * AUDIO_RATE_HZ / 1000)
            offset_ms = 0.0
        rows.append({"frame": frame, "index": index, "name": bank_meta["samples"][index]["name"],
                     "correlation": correlation, "offset_ms": offset_ms, "ratio": ratio,
                     "ok": (correlation >= SFX_CORRELATION_FLOOR
                            and ratio >= SFX_PEAK_RATIO_FLOOR
                            and abs(offset_ms) <= SFX_SEARCH_MS)})
    return rows, anchor


# ------------------------------------------------------------------------ the drum lane check ---

def trimmed_length(window, rate_hz):
    """How much of `window` holds DRUM_ENERGY_FRACTION of its energy, floored at a length short
    enough to still be a waveform and not a click."""
    cumulative = np.cumsum(window ** 2)
    if cumulative[-1] <= 0.0:
        return window.size
    needed = int(np.searchsorted(cumulative, DRUM_ENERGY_FRACTION * cumulative[-1])) + 1
    return max(needed, min(window.size, int(rate_hz * DRUM_MIN_CORRELATE_MS / 1000)))


def drum_references(bank_meta, blob):
    """{bank index: (reference, lead samples)} for every sample the drum lane can name."""
    return {index: loudest_stretch(bank_meta, blob, index, DRUM_CORRELATE_MS, trim=True)
            for index in range(bank_meta["drum_first_index"], len(bank_meta["samples"]))}


def best_correlation(mono, centre, reference, search_ms):
    """(the reference's best |correlation| within `search_ms` of `centre`, its offset in ms)."""
    scores, start = correlation_profile(mono, centre, reference, search_ms)
    if scores.size == 0:
        return 0.0, 0.0
    peak = int(np.argmax(scores))
    return float(scores[peak]), (start + peak - centre) * 1000.0 / AUDIO_RATE_HZ


def drum_clock(mono, onset, hits, references, vbl_hz, kick_index):
    """A linear map from a hit's frame to where its audio really is, fitted on the KICKS.

    TWO THINGS ARE BEING SEPARATED HERE, and conflating them is what makes a drum check lie. WHEN a
    sample fired and WHICH one it was are the ledger's, from the machine. Where the recording sits
    against that is a property of HATARI — its audio clock and its vblank clock drift about 0.08%
    apart, 16 ms across this window, and the onset is only good to a frame either way. So the clock
    is measured first, on the one sample that is loud and unambiguous, and by fitting a straight
    line through every kick rather than trusting any single one; identification then runs against a
    timeline that is already right, which is the only way its answer is about the driver.

    The fitted lag is RETURNED, not just applied, because a fit that can absorb any offset can
    absorb a defect: the caller bounds it against DRUM_LAG_BUDGET_MS.

    One circularity to name: the fit uses rows the ledger labels a kick, so the kick column of the
    identification that follows is scored at a centre the kick's own correlation chose. The other
    three samples — 74 of the window's 110 hits — are held to a timeline they had no vote in."""
    reference, lead = references[kick_index]
    measured = [(frame, best_correlation(mono, onset + int(frame * AUDIO_RATE_HZ / vbl_hz) + lead,
                                         reference, DRUM_CLOCK_SEARCH_MS)[1])
                for frame, fired in hits if fired == kick_index]
    # THE FIT IS ON THE ONES THAT AGREE. A wide search has to be wide enough to find the offset
    # before it is known, and at that width the kick reference sometimes locks onto the row before
    # instead — measured, 4 kicks of 36 answered about one row early. Least squares has no defence
    # against that (one outlier at -147 ms moves the intercept by 16), so the median says where the
    # answer is and only the ones near it are fitted.
    frames = np.array([frame for frame, _ in measured], dtype=np.float64)
    offsets = np.array([offset for _, offset in measured], dtype=np.float64)
    inlier = np.abs(offsets - np.median(offsets)) <= DRUM_CLOCK_INLIER_MS
    if int(inlier.sum()) < DRUM_CLOCK_MIN_KICKS:
        fail(f"only {int(inlier.sum())} of {len(measured)} kicks in the drum window agree on an "
             f"offset (need {DRUM_CLOCK_MIN_KICKS}) — there is no clock to fit, which means the "
             f"lane is not where the ledger says it is")
    slope, intercept = np.polyfit(frames[inlier], offsets[inlier], 1)
    lag_ms = lambda frame: slope * frame + intercept
    return (lambda frame: int(lag_ms(frame) * AUDIO_RATE_HZ / 1000.0),
            [lag_ms(float(frames[0])), lag_ms(float(frames[-1]))])


def drum_lane_is_gridded(record, profile):
    """Is every recorded hit inside the drum window, and on the row grid the band's speed sets?

    A hit is published by the row step and by nothing else, so consecutive hits must be a whole
    number of rows apart. This is the surface for the one failure the audio cannot see: a hit the
    platform never took is simply absent, and absence looks exactly like a silent row."""
    rows_apart = profile.band_speeds[-1]        # the drum window is held at the fastest band
    frames = [frame for frame, _ in record["drum_hits"]]
    if not frames:
        return False
    if frames[0] < BICE_DRUM_FIRST_FRAME or frames[-1] >= BICE_DRUM_FIRST_FRAME + BICE_DRUM_FRAMES:
        return False
    return all(0 < later - earlier and (later - earlier) % rows_apart == 0
               for earlier, later in zip(frames, frames[1:]))


def check_drums(mono, onset, record, bank_meta, blob, vbl_hz):
    """Every drum-lane hit the .PRG recorded, identified in the recording at its own row time.

    EACH CANDIDATE IS SCORED AGAINST ITS OWN BACKGROUND, not against the other candidates' raw
    numbers, and that correction is the whole of what makes this measure the lane rather than the
    arrangement. A correlation here is <recording, reference>, and the recording is the YM
    arrangement PLUS one drum — so a reference that happens to resemble the YM part scores well on
    every row whether it played or not. Measured: the kick reference read ~0.45 on rows it had
    never played, because the bass strikes on every row and a low chirp resembles a struck bass
    note; the hi-hat, which shares a band with nothing, reached 0.34 on rows it DID play.
    Comparing those raw numbers compares the two references. Subtracting each one's own background
    leaves the part of the correlation the drum itself put there."""
    hits = record["drum_hits"]
    if not hits:
        return []
    references = drum_references(bank_meta, blob)
    kick_index = bank_meta["drum_bank"][DRUM_CLOCK_SAMPLE]
    clock, lag_ms = drum_clock(mono, onset, hits, references, vbl_hz, kick_index)

    raw = {index: [] for index in references}
    offsets = {index: [] for index in references}
    for frame, _ in hits:
        centre = onset + int(frame * AUDIO_RATE_HZ / vbl_hz) + clock(frame)
        for index, (reference, lead) in references.items():
            score, offset_ms = best_correlation(mono, centre + lead, reference, DRUM_SEARCH_MS)
            raw[index].append(score)
            offsets[index].append(offset_ms)
    # Each reference's background is what it reads ON THE ROWS IT DID NOT PLAY — which the ledger
    # names, so this is not a quantile standing in for the idea, it is the idea. The kick reference
    # reads 0.2-0.5 on a bass attack whether a kick was struck or not; the hi-hat, which shares a
    # band with nothing, reads near zero unless it played. Subtracting each one's own level leaves
    # the part of the correlation that this drum, and only this drum, put there.
    # ...on the rows it did NOT play, which the ledger names. A sample that is the only one the
    # window ever fired has no such rows, and np.median([]) is nan — which is truthy, so an `or 0.0`
    # guard would not catch it and every contrast downstream would be nan.
    def background_of(index):
        elsewhere = [value for value, (_, fired) in zip(raw[index], hits) if fired != index]
        return float(np.median(elsewhere)) if elsewhere else 0.0

    background = {index: background_of(index) for index in raw}

    rows = []
    for slot, (frame, fired) in enumerate(hits):
        contrast = {index: raw[index][slot] - background[index] for index in references}
        # max() on a dict breaks ties by insertion order, i.e. by bank index; sorting on the
        # contrast alone makes the answer independent of how the references were enumerated.
        heard = max(sorted(contrast), key=contrast.get)
        rows.append({"frame": frame, "fired": fired, "heard": heard,
                     "name": bank_meta["samples"][fired]["name"],
                     "heard_name": bank_meta["samples"][heard]["name"],
                     "correlation": raw[fired][slot], "contrast": contrast[fired],
                     "offset_ms": offsets[fired][slot],
                     # The offset is NOT part of this: best_correlation clips its own search to
                     # DRUM_SEARCH_MS, so a bound on it here would be a tautology. The timing
                     # assertion is the clock's fitted lag, checked once by the caller.
                     "ok": heard == fired})
    return rows, lag_ms


# ------------------------------------------------------------------- the trace-band tempo check --

def envelope_of(mono, start, count):
    """(the recording's amplitude envelope over that stretch, zero-meaned; its own sample rate).

    Zero-meaned because what is being measured is how the loudness BEATS, and a DC term is the
    largest number in any spectrum of a signal that is never negative."""
    block = int(AUDIO_RATE_HZ * ENVELOPE_BLOCK_MS / 1000)
    envelope = block_rms(mono[start:start + count], block)
    return envelope - envelope.mean(), AUDIO_RATE_HZ / block


def periodicity(envelope, envelope_rate_hz, row_rate_hz):
    """How strongly `envelope` beats at `row_rate_hz`: the magnitude there plus at its harmonics.

    A plain DFT at the exact candidate frequency rather than an FFT peak — the four candidates are
    known, so the question is which of them the signal answers to, not what the signal's period is
    (which a snare on every fourth row would answer differently and correctly)."""
    axis = np.arange(envelope.size) / envelope_rate_hz
    shaped = envelope * np.hanning(envelope.size)
    return sum(abs(np.sum(shaped * np.exp(-2j * np.pi * harmonic * row_rate_hz * axis)))
               for harmonic in range(1, TEMPO_HARMONICS + 1))


def dominant_rate(envelope, envelope_rate_hz):
    """The envelope's strongest beat between TEMPO_RATE_MIN_HZ and TEMPO_RATE_MAX_HZ."""
    spectrum = np.abs(np.fft.rfft(envelope * np.hanning(envelope.size)))
    freqs = np.fft.rfftfreq(envelope.size, 1.0 / envelope_rate_hz)
    band = (freqs >= TEMPO_RATE_MIN_HZ) & (freqs <= TEMPO_RATE_MAX_HZ)
    if not band.any():
        return 0.0
    index = int(np.argmax(np.where(band, spectrum, 0.0)))
    return interpolate_peak(spectrum, index, float(freqs[1]))


def check_band_tempo(mono, onset, profile, vbl_hz):
    """Which trace band each band window SOUNDS like, measured off the recording alone.

    This is the only surface that can catch a tempo switch that did not happen. The ledger cannot:
    ym_music_set_speed returns nothing and writes no hardware. The register trace cannot: the
    driver publishes all eleven PSG registers on every frame at every tempo, so the traffic is
    identical. What changes is WHEN the rows land, and that is in the audio."""
    rows = []
    for band, speed in enumerate(profile.band_speeds):
        first = BICE_BAND_FIRST_FRAME + band * BICE_BAND_FRAMES + TEMPO_SETTLE_FRAMES
        start = onset + int(first * AUDIO_RATE_HZ / vbl_hz)
        count = int((BICE_BAND_FRAMES - TEMPO_SETTLE_FRAMES) * AUDIO_RATE_HZ / vbl_hz)
        # Said here rather than left to numpy: if audiotest.c's band boundaries and this file's
        # ever drift apart, the window walks off the end of the recording and the operator should
        # be told that, not handed a "number of FFT data points" traceback from three frames down.
        if start + count > mono.size:
            fail(f"band {band}'s window (frames {first}..{first + BICE_BAND_FRAMES}) runs past the "
                 f"{mono.size / AUDIO_RATE_HZ:.1f} s recording — audiotest.c's timeline and this "
                 f"file's BICE_* constants have drifted apart")
        envelope, envelope_rate = envelope_of(mono, start, count)
        expected_hz = vbl_hz / speed
        scores = [periodicity(envelope, envelope_rate, vbl_hz / candidate)
                  for candidate in profile.band_speeds]
        best = int(np.argmax(scores))
        ranked = sorted(scores, reverse=True)
        margin = ranked[0] / (ranked[1] or EPSILON)
        measured_hz = dominant_rate(envelope, envelope_rate)
        error = abs(measured_hz - expected_hz) / expected_hz
        rows.append({"band": band, "speed": speed, "expected_hz": expected_hz,
                     "measured_hz": measured_hz, "error": error,
                     "heard_band": best, "margin": margin,
                     "ok": (best == band and margin >= TEMPO_MARGIN
                            and error <= TEMPO_RATE_TOLERANCE)})
    return rows


# --------------------------------------------------------------------------------- the trace ----

PSG_WRITE_RE = re.compile(r"^ym write data reg=0x([0-9a-f]+) val=0x([0-9a-f]+).*pc=([0-9a-f]+)")
DMA_CONTROL_RE = re.compile(r"^DMA snd control write: 0x([0-9a-f]+).*pc=([0-9a-f]+)")
MICROWIRE_RE = re.compile(r"^Microwire new (\w[\w ]*)=0x([0-9a-f]+)")
# Everything at or above this address is ROM: EmuTOS spans $e00000-$efffff and a TOS 1.x image
# sits at $fc0000, while a .PRG is loaded into RAM well below it. A two-character pc prefix is NOT
# enough — it matched $e0xxxx and missed $e5xxxx, and EmuTOS's own PSG port-A writes then counted
# as ours.
ROM_FIRST_ADDRESS = 0xE00000


def read_trace(path):
    """The trace, split into what OUR code did and what the ROM did.

    Split on the pc, because the ROM writes the same registers we do: EmuTOS's own boot sets the
    LMC1992 and pokes PSG port A for the floppy, and counting those as ours would make every tally
    below meaningless."""
    if not path.exists():
        fail(f"the run left no {path.name}")
    ours = {"psg": [], "dma": [], "microwire": []}
    rom = {"psg": 0, "dma": 0, "microwire": 0}
    for line in path.read_text(errors="replace").splitlines():
        match = PSG_WRITE_RE.match(line)
        if match:
            if int(match.group(3), 16) >= ROM_FIRST_ADDRESS:
                rom["psg"] += 1
            else:
                ours["psg"].append((int(match.group(1), 16), int(match.group(2), 16)))
            continue
        match = DMA_CONTROL_RE.match(line)
        if match:
            if int(match.group(2), 16) >= ROM_FIRST_ADDRESS:
                rom["dma"] += 1
            else:
                ours["dma"].append(int(match.group(1), 16))
            continue
        match = MICROWIRE_RE.match(line)
        if match:
            ours["microwire"].append((match.group(1).strip(), int(match.group(2), 16)))
    return ours, rom


# ------------------------------------------------------------------------------- the report -----

class Report:
    def __init__(self):
        self.rows = []

    def check(self, name, ok, detail):
        self.rows.append((name, bool(ok), detail))
        return ok

    def failures(self):
        return [name for name, ok, _ in self.rows if not ok]

    def render(self):
        width = max(len(name) for name, _, _ in self.rows)
        lines = [f"{'check'.ljust(width)}  result  detail", f"{'-' * width}  ------  " + "-" * 52]
        for name, ok, detail in self.rows:
            lines.append(f"{name.ljust(width)}  {'PASS' if ok else 'FAIL':<6}  {detail}")
        return "\n".join(lines)


def record_only(profile):
    """`make listen-blackice`: the same .PRG, the same machine, recorded and written as a .wav —
    and nothing else. No trace (its log is tens of megabytes and nothing here reads it), no
    plain-ST run, no analysis. This is the one output in this directory meant for a pair of ears
    rather than a number, so it is deliberately not a check that can fail."""
    profile.ledger.unlink(missing_ok=True)
    profile.avi.unlink(missing_ok=True)
    run_hatari(MACHINE_STE, BUNDLED_EMUTOS,
               ["--disable-video", "on", "--avirecord", "--avi-file", str(profile.avi)],
               f"hatari-listen{profile.suffix}.log", profile.prg,
               profile.frames + EMUTOS_BOOT_VBLS)
    stereo, chunks = avi_audio(profile.avi)
    # Trimmed to the first note. A third of the recording is the ROM booting, and a file that opens
    # with 17 seconds of silence is one nobody listens to the end of.
    music = stereo[find_music_onset(stereo.mean(axis=1)):]
    write_wav(profile.wav, music)
    print(f"{profile.wav}: {music.shape[0] / AUDIO_RATE_HZ:.1f} s of music, {AUDIO_RATE_HZ} Hz "
          f"stereo, from {chunks} chunks — {profile.frames} frames of {profile.name}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--blackice", action="store_true",
                        help="run BICETEST.PRG: the BLACK ICE score and its ten cues")
    parser.add_argument("--keep", action="store_true", help="analyse out/ without re-running Hatari")
    parser.add_argument("--listen", action="store_true",
                        help="record the run to a .wav and stop: no trace, no ST run, no checks")
    args = parser.parse_args()

    profile = blackice_profile(read_band_speeds()) if args.blackice else demo_profile()
    if not (DISK / profile.prg).exists():
        fail(f"no {DISK / profile.prg} — run `make` first")
    if not BUNDLED_EMUTOS.exists():
        fail(f"no EmuTOS at {BUNDLED_EMUTOS}; the STE half of this test needs an STE-capable ROM")

    if args.listen:
        return record_only(profile)
    if args.keep:
        record = read_ledger(profile.ste_ledger)
    else:
        run_ste(profile)
        record = read_ledger(profile.ledger)
        OUT.mkdir(exist_ok=True)
        profile.ste_ledger.write_bytes(profile.ledger.read_bytes())
    note_meta = json.loads(profile.note_meta.read_text())
    song_metas = [json.loads(path.read_text()) for path in profile.song_metas]
    bank_meta = json.loads(profile.bank_meta.read_text())
    blob = profile.bank_blob.read_bytes()

    stereo, chunk_count = avi_audio(profile.avi)
    write_wav(profile.wav, stereo)
    mono = stereo.mean(axis=1)
    onset = find_music_onset(mono)
    # The MEASURED vblank rate, not the nominal 50: the ledger's own 200 Hz count says the machine
    # ran at 50.1 Hz, and over an 18-second timeline the 0.2% difference is 35 ms of drift — enough
    # to walk every later SFX out of its search window.
    measured_vbl_hz = vbl_rate(record)
    window_samples = int(record["frames_run"] * AUDIO_RATE_HZ / measured_vbl_hz)
    run_window = mono[onset:onset + window_samples]

    report = Report()
    report.check("machine is an STE", record["machine_has_dma"] == 1,
                 f"_MCH cookie says {'STE-class' if record['machine_has_dma'] else 'plain ST'}")
    song_bytes = sum(meta["bytes"] for meta in song_metas)
    report.check("songs accepted", record["song_accepted"] == 1,
                 f"{len(song_metas)} song(s), {song_bytes} bytes: "
                 + ", ".join(f"{meta['symbol']} {meta['frames_total'] / PAL_VBL_HZ:.1f} s"
                             for meta in song_metas))
    report.check("sample bank accepted", record["bank_accepted"] == 1,
                 f"{len(bank_meta['samples'])} samples, {bank_meta['bytes']} bytes")
    report.check("vblank tick installed", record["vbl_slot"] != VBL_SLOT_NONE,
                 f"_vblqueue slot {record['vbl_slot']}")
    report.check("frames run", record["frames_run"] == profile.frames,
                 f"{record['frames_run']} of {profile.frames}")
    report.check("vblank rate is PAL",
                 abs(measured_vbl_hz - PAL_VBL_HZ) / PAL_VBL_HZ <= VBL_RATE_TOLERANCE,
                 f"{measured_vbl_hz:.2f} Hz measured over {record['hz200_elapsed']} 200 Hz ticks")
    cost = tick_cycles(record)
    report.check("tick within budget", cost < TICK_CYCLE_BUDGET,
                 f"{cost:.0f} cycles/frame against a {TICK_CYCLE_BUDGET} budget "
                 f"({cost / CPU_HZ * 1e6:.0f} us, {cost / 160000 * 100:.1f}% of a 160k frame)")
    rotation_events = profile.rotation_events
    expected_events = rotation_events + PROBE_EVENTS
    report.check("every SFX request answered", record["sfx_events"] == expected_events,
                 f"{record['sfx_events']} requests ({rotation_events} in the rotation, "
                 f"{PROBE_EVENTS} in the priority probe), {record['dma_starts']} started on the "
                 f"DMA, {record['ym_starts']} on the YM, {record['sfx_refused']} refused")
    report.check("SFX took the DMA path", record["dma_starts"] == rotation_events + 2,
                 f"{record['dma_starts']} DMA starts on an STE")
    report.check("priority refuses the quieter claim",
                 record["probe_claim_started"] == 1 and record["probe_lower_started"] == 0
                 and record["probe_preempt_started"] == 1,
                 f"the claim started={record['probe_claim_started']}, then a LOWER priority while "
                 f"it played started={record['probe_lower_started']} (must be 0), then an equal or "
                 f"higher one started={record['probe_preempt_started']}")

    report.check("audio recorded", mono.size > 0,
                 f"{chunk_count} chunks, {mono.size / AUDIO_RATE_HZ:.1f} s at {AUDIO_RATE_HZ} Hz "
                 f"-> {profile.wav.name}")
    run_rms = float(np.sqrt(np.mean(run_window.astype(np.float64) ** 2)))
    report.check("run is not silent", run_rms > MUSIC_RMS_FLOOR,
                 f"RMS {run_rms:.0f} of 32767 over the {record['frames_run']}-frame window")
    block = AUDIO_RATE_HZ * SILENCE_BLOCK_MS // 1000
    silent = float(np.mean(block_rms(run_window, block) <= SILENCE_RMS_FLOOR))
    report.check("music is continuous", silent <= SILENT_BLOCK_BUDGET,
                 f"{silent * 100:.1f}% of {SILENCE_BLOCK_MS} ms blocks silent "
                 f"(budget {SILENT_BLOCK_BUDGET * 100:.0f}%)")

    notes = check_notes(mono, onset, note_meta, measured_vbl_hz, profile.note_window_frames)
    passed = sum(1 for row in notes if row["ok"])
    report.check("YM notes are on pitch", notes and passed >= NOTE_PASS_FRACTION * len(notes),
                 f"{passed}/{len(notes)} sounding notes peak within "
                 f"{NOTE_PEAK_TOLERANCE * 100:.0f}% of the song's own frequency")

    sfx_rows, _ = check_sfx(mono, onset, record, bank_meta, blob, measured_vbl_hz,
                            profile.sfx_last_frame)
    sfx_passed = sum(1 for row in sfx_rows if row["ok"])
    report.check("DMA samples identified", sfx_rows and sfx_passed == len(sfx_rows),
                 f"{sfx_passed}/{len(sfx_rows)} match the packed bytes at the frame they were "
                 f"fired (peak >= {SFX_PEAK_RATIO_FLOOR:.0f}x the background correlation)")

    drum_rows = []
    if profile.band_speeds is not None:
        drum_rows, drum_lag_ms = check_drums(mono, onset, record, bank_meta, blob, measured_vbl_hz)
        identified = sum(1 for row in drum_rows if row["ok"])
        rate = identified / len(drum_rows) if drum_rows else 0.0
        # PER SAMPLE AS WELL AS OVERALL. 58 of the window's 110 hits are hi-hats, so an aggregate
        # floor says nothing about a rare one: relabelling all five claps still scores 95%. Every
        # sample the lane names has to clear the floor on its own.
        per_sample = sorted({row["name"] for row in drum_rows})
        worst = min((sum(1 for row in drum_rows if row["name"] == name and row["ok"])
                     / sum(1 for row in drum_rows if row["name"] == name), name)
                    for name in per_sample) if per_sample else (0.0, "-")
        report.check("drum lane identified",
                     drum_rows and rate >= DRUM_IDENTIFY_FRACTION
                     and worst[0] >= DRUM_IDENTIFY_FRACTION,
                     f"{identified}/{len(drum_rows)} hits ({rate * 100:.1f}%, floor "
                     f"{DRUM_IDENTIFY_FRACTION * 100:.0f}%) are the sample the lane asked for over "
                     f"{BICE_DRUM_FRAMES / PAL_VBL_HZ:.0f} s at one tempo; worst sample "
                     f"'{worst[1]}' at {worst[0] * 100:.1f}%")
        # WHERE the lane sits, which the identification deliberately does not answer: the clock fit
        # would otherwise absorb a constant error — a lane published a row late reads as a perfect
        # score — so the offset it fitted is bounded here instead.
        report.check("the drum lane is on the row grid",
                     max(abs(lag) for lag in drum_lag_ms) <= DRUM_LAG_BUDGET_MS
                     and drum_lane_is_gridded(record, profile),
                     f"lag {drum_lag_ms[0]:+.1f} ms at the window's first hit and "
                     f"{drum_lag_ms[1]:+.1f} ms at its last (budget +/-{DRUM_LAG_BUDGET_MS:.0f}, "
                     f"a row is {1000.0 / (measured_vbl_hz / profile.band_speeds[-1]):.0f} ms); "
                     f"every hit inside the window and on a row boundary")
        report.check("every drum hit reached the DMA",
                     record["drum_window_started"] == record["drum_window_hits"]
                     and record["drum_window_hits"] > 0,
                     f"{record['drum_window_started']} of {record['drum_window_hits']} hits in the "
                     f"drum window started the voice — no cue fires there, so a refusal would be "
                     f"a defect")
        # The other half of the priority rule, and the run-wide numbers are where it shows: the
        # rotation and the probe DO fire cues, and every lane row that landed under one was
        # dropped. A drum lane that never lost an argument would mean YM_DRUM_PRIORITY was wrong.
        outranked = record["drum_requests"] - record["drum_started"]
        report.check("a cue outranks the drum lane", outranked > 0,
                     f"{outranked} of {record['drum_requests']} lane hits over the whole run were "
                     f"refused while a cue held the voice (the lane plays at YM_DRUM_PRIORITY, "
                     f"below every cue)")

    tempo_rows = []
    if profile.band_speeds is not None:
        tempo_rows = check_band_tempo(mono, onset, profile, measured_vbl_hz)
        tempo_passed = sum(1 for row in tempo_rows if row["ok"])
        rates = ", ".join(f"{measured_vbl_hz / speed:.2f}" for speed in profile.band_speeds)
        report.check("trace bands change the tempo", tempo_passed == len(tempo_rows),
                     f"{tempo_passed}/{len(tempo_rows)} band windows beat at their own row rate "
                     f"and no other's ({rates} rows/s)")

    ours, rom = read_trace(profile.trace)
    psg_regs = sorted({reg for reg, _ in ours["psg"]})
    report.check("PSG traffic is ours and bounded", psg_regs == list(range(PSG_ENVELOPE_FIRST_REG)),
                 f"registers {psg_regs} written {len(ours['psg'])} times; the hardware envelope "
                 f"(11-13) never touched; {rom['psg']} ROM writes ignored")
    dma_starts = sum(1 for value in ours["dma"] if value & 1)
    # The cues AND the drum lane share the one voice, so the hardware's own count of starts is the
    # sum of the two the .PRG counted. That the two agree is what says no start happened that
    # neither path asked for, and none was asked for that never reached the chip.
    expected_starts = record["dma_starts"] + record["drum_started"]
    report.check("DMA control writes in order", dma_starts == expected_starts,
                 f"{len(ours['dma'])} control writes, {dma_starts} of them a start "
                 f"({record['dma_starts']} cues + {record['drum_started']} drum lane)")
    route = dict(ours["microwire"])
    report.check("LMC1992 routed and turned up",
                 route.get("mixing") == 1 and route.get("master volume") == 40,
                 f"{route}")

    st = run_st_fallback(profile) if (ST_TOS.exists() and not args.keep) else None
    if st is not None:
        report.check("plain-ST fallback",
                     st["machine_has_dma"] == 0 and st["bank_accepted"] == 0
                     and st["dma_starts"] == 0 and st["frames_run"] == profile.frames
                     and st["ym_starts"] == rotation_events + 2
                     and st["probe_lower_started"] == 0 and st["drum_started"] == 0,
                     f"the same .PRG on a TOS 1.04 ST: no _MCH STE, bank refused, "
                     f"{st['ym_starts']} SFX on the YM, {st['dma_starts']} on the DMA, "
                     f"{st['drum_requests']} drum-lane hits published and {st['drum_started']} "
                     f"played, {st['frames_run']} frames, probe refusal held")

    print(report.render())
    print()
    print("  YM note check (music-only window at the head of the run)")
    print("    frame  ch  instrument     expected     peak    err%   prominence  ok")
    for row in notes:
        print(f"    {row['frame']:5d}  {row['channel']:2d}  {row['instrument']:<12} "
              f"{row['expected_hz']:8.1f} {row['peak_hz']:8.1f}  {row['error'] * 100:5.2f}  "
              f"{row['prominence']:9.1f}   {'ok' if row['ok'] else 'NO'}")
    print()
    print("  DMA sample check (cross-correlation against the packed bytes)")
    print("    frame  id  name             correlation  peak/bg  offset ms  ok")
    for row in sfx_rows:
        print(f"    {row['frame']:5d}  {row['index']:2d}  {row['name']:<14} "
              f"{row['correlation']:11.3f}  {row['ratio']:7.1f}  {row['offset_ms']:9.1f}  "
              f"{'ok' if row['ok'] else 'NO'}")
    if drum_rows:
        misread = [row for row in drum_rows if not row["ok"]]
        print()
        print(f"  Drum lane check — {len(drum_rows)} hits over "
              f"{BICE_DRUM_FRAMES / PAL_VBL_HZ:.0f} s at one tempo, each scored against every lane "
              f"sample (fitted lag {drum_lag_ms[0]:+.1f} to {drum_lag_ms[1]:+.1f} ms)")
        print("    sample    identified  mean correlation  mean contrast")
        for name in sorted({row["name"] for row in drum_rows}):
            same = [row for row in drum_rows if row["name"] == name]
            good = sum(1 for row in same if row["ok"])
            mean = sum(row["correlation"] for row in same) / len(same)
            lift = sum(row["contrast"] for row in same) / len(same)
            print(f"    {name:<8}  {good:4d}/{len(same):<4d}   {mean:11.3f}  {lift:13.3f}")
        print(f"    {len(misread)} misread")
        for row in misread[:MISREAD_ROWS_SHOWN]:
            print(f"      frame {row['frame']}: the lane said {row['name']}, the recording says "
                  f"{row['heard_name']} ({row['correlation']:.3f}, {row['offset_ms']:+.1f} ms)")
    if tempo_rows:
        print()
        print("  Trace band check (which row rate the recording's own pulse beats at)")
        print("    band  speed  expected Hz  measured Hz   err%  heard as  margin  ok")
        for row in tempo_rows:
            print(f"    {row['band']:4d}  {row['speed']:5d}  {row['expected_hz']:11.3f}  "
                  f"{row['measured_hz']:11.3f}  {row['error'] * 100:5.2f}  "
                  f"{row['heard_band']:8d}  {row['margin']:6.2f}  {'ok' if row['ok'] else 'NO'}")

    broken = report.failures()
    if broken:
        print()
        fail(f"{len(broken)} check(s) failed: {', '.join(broken)}")
    print()
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
