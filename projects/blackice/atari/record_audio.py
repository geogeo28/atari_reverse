#!/usr/bin/env python3
"""Record the GAME's audio and prove the song's drum lane fires inside it.

WHY THIS EXISTS.  audio/verify.py already proves the drum lane in audio/audiotest.c -- a .PRG whose
whole job is to play the song and publish a ledger of every hit.  That says the DRIVER works.  It
says nothing about this directory: the lane only reaches a player if main.c's vertical blank calls
`ym_music_take_drum_hit` on the same tick it called `ym_music_tick`, and a platform that forgets
the take is silent in exactly the way a correct one is quiet between hits.  So the check is run
again here, on BLACKICE.PRG itself, playing the actual game.

WHAT STANDS IN FOR THE LEDGER.  The game publishes no ledger, so the hits come from the machine
instead: Hatari's `dmasound` trace prints every DMA sound frame-address write, and the address is
the sample's own offset inside the linked bank -- which names WHICH drum played.  `video_vbl`
interleaves the frame count, which says WHEN.  That is the same (frame, sample) sequence
audiotest.c writes into its ledger, recovered from outside the program.

THE IDENTIFICATION IS audio/verify.py's, IMPORTED AND NOT RE-TYPED.  Its `check_drums` fits the
audio clock on the kicks and then scores all four references against each hit's own background;
copying that recipe here would be a second copy to drift.  This file only recovers the hit list and
reports what the shared code makes of it.
"""
import argparse
import importlib.util
import re
import sys
import time
import wave
from collections import namedtuple
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent

if str(HERE) not in sys.path:                    # play_headless.py, this file's own neighbour
    sys.path.insert(0, str(HERE))

import play_headless                             # noqa: E402  (path set up above)


def _load_audio_verify():
    """audio/verify.py, loaded BY PATH.

    There is a verify.py in this directory too, and which one a plain `import verify` would find
    depends on the order two paths were pushed onto sys.path -- a coin-flip that would swap the
    pixel harness in for the audio one.  Both keep all their work behind main(), so loading either
    runs nothing."""
    spec = importlib.util.spec_from_file_location("audio_verify", PROJECT / "audio" / "verify.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audio_verify = _load_audio_verify()

BANK_BLOB = PROJECT / "audio" / "out" / "blackice_sfx_bank.bin"
BANK_META = PROJECT / "audio" / "out" / "blackice_sfx_meta.json"

# Hatari's trace, one line per write.  The pc separates our driver from EmuTOS's own boot-time
# pokes at the same registers, exactly as audio/verify.py's read_trace does.
FRAME_START_RE = re.compile(r"^DMA snd frame start (high|med|low): 0x([0-9a-f]+).*pc=([0-9a-f]+)")
VBL_RE = re.compile(r"^VBL (\d+) video_cyc=")
# The same vblank again, with the CPU's cycle counter beside it: dividing the counter by the vblank
# count MEASURES the machine's frame rate instead of assuming it, which is what says PAL or NTSC.
VBL_CLOCK_RE = re.compile(r"^VBL=(\d+) clock=(\d+)")
ROM_FIRST_ADDRESS = 0xE00000

# The three writes that make one address, in the order the hardware lays them out.
FRAME_BYTE_SHIFT = {"high": 16, "med": 8, "low": 0}

# psg_write is in the trace only to date the music: the FIRST write our code makes to the sound
# chip is the driver's first, and the vblank it lands on is what the recording's music onset means
# in frames.  Without that origin the hits are numbered from Hatari's boot and the audio clock has
# fourteen seconds of ROM to fit across.
TRACE_FLAGS = "dmasound,video_vbl,psg_write"
PAL_VBL_HZ = 50.0
VBL_RATE_TOLERANCE = 0.02         # of PAL; a 60 Hz machine is 20% out and fails this by a mile
ST_CPU_HZ = 8_000_000

# EMUTOS COMES UP 60 Hz UNLESS IT IS TOLD OTHERWISE, and audio/verify.py had to learn it first: left
# at the default country the vblank is 60 Hz, the song plays 20% fast, and every frame-to-seconds
# mapping here is quietly wrong (measured on this game: 59.90 Hz, and the drum identification fell
# from 96% to 32% because the hits were looked for in the wrong place).  The .PRG does not choose
# the machine's sync -- the ROM does, before the program runs -- so the country is set here.
PAL_COUNTRY = "uk"

# The run: boot, hear the title, start, then play.  REAL TIME, so a wall-clock second is a second
# of emulated time and the run's length is known in advance -- which is what keeps the trace to
# tens of megabytes.  (Fast-forward was tried and is worse here for one reason: every wall-clock
# wait then burns an unpredictable number of vblanks, and the run has to be given a --run-vbls
# ceiling it cannot be allowed to hit mid-recording.)
TITLE_SECONDS = 4.0                 # the title holds the song but not the tick, so this one wait
                                    # is on the clock rather than on the game's own counter
PLAY_TICKS = 750                    # ~30 s of play, which is several hundred rows of the song
STEP_SECONDS = 2.0                  # one leg of the walk-and-turn loop, as a held key
BOOT_TRIES = 40                     # state_address polls while EmuTOS, GEMDOS and the PAK load
PLAY_WALL_LIMIT = 120.0             # a stuck run must end as a short recording, not as a 500 MB one
# Hatari stops itself here.  Everything above is a floor on how much gets recorded; this is the
# ceiling, and it exists because the trace grows by megabytes a second and the default run length
# is measured in hours.
RUN_VBLS = 12000                    # ~240 s of PAL: the boot, the title, and the play window


def read_wav(path):
    """The recording as one mono float track."""
    with wave.open(str(path), "rb") as handle:
        if handle.getsampwidth() != 2:
            raise SystemExit(f"{path} is not 16-bit; this reader only knows Hatari's own output")
        frames = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2")
        channels = handle.getnchannels()
        rate = handle.getframerate()
    if rate != audio_verify.AUDIO_RATE_HZ:
        raise SystemExit(f"{path} is {rate} Hz; the shared analysis is written for "
                         f"{audio_verify.AUDIO_RATE_HZ}")
    return frames.reshape(-1, channels).mean(axis=1).astype(np.float64)


# Everything the trace says about one run.  `plays` and `music_frame` are counted in Hatari's own
# absolute vblanks; `vbl_hz` is the machine's rate and `vbl_count` how many blanks the run lasted.
TraceRun = namedtuple("TraceRun", "plays music_frame vbl_hz vbl_count")


def read_drum_plays(trace_path):
    """The TraceRun the trace describes: every sample OUR code started, and the clocks to date it.

    A play is complete when its low byte lands: the driver writes high, med, low, and the low write
    is the last thing that can change the address the chip will read from."""
    plays, pending, frame, music_frame = [], {}, 0, None
    first_vbl = last_vbl = None
    with trace_path.open(errors="replace") as handle:
        for line in handle:
            match = VBL_RE.match(line)
            if match:
                frame = int(match.group(1))
                continue
            match = VBL_CLOCK_RE.match(line)
            if match:
                last_vbl = (int(match.group(1)), int(match.group(2)))
                first_vbl = first_vbl or last_vbl
                continue
            match = audio_verify.PSG_WRITE_RE.match(line)
            if match:
                if music_frame is None and int(match.group(3), 16) < ROM_FIRST_ADDRESS:
                    music_frame = frame
                continue
            match = FRAME_START_RE.match(line)
            if not match or int(match.group(3), 16) >= ROM_FIRST_ADDRESS:
                continue
            byte, value = match.group(1), int(match.group(2), 16)
            pending[byte] = value << FRAME_BYTE_SHIFT[byte]
            if byte == "low" and len(pending) == len(FRAME_BYTE_SHIFT):
                plays.append((frame, sum(pending.values())))
                pending = {}
    if not last_vbl:
        raise SystemExit("the trace counted no vblanks — there is no clock to date the hits by")
    return TraceRun(plays, music_frame, vbl_rate_of(first_vbl, last_vbl), last_vbl[0])


def vbl_rate_of(first_vbl, last_vbl):
    """The MACHINE's vblank rate in Hz, from the CPU cycles it spent between two counted vblanks.

    This is what says PAL or NTSC.  It is deliberately NOT what the audio is indexed by: see
    audio_frame_rate."""
    if last_vbl[0] == first_vbl[0]:
        raise SystemExit("the trace counted one vblank — there is no rate to measure")
    cycles_per_vbl = (last_vbl[1] - first_vbl[1]) / (last_vbl[0] - first_vbl[0])
    return ST_CPU_HZ / cycles_per_vbl


def audio_frame_rate(mono, vbl_count):
    """The rate the RECORDING is indexed by: how many vblanks a second of the .wav holds.

    Hatari writes one audio chunk per emulated frame, and the chunk holds however many samples that
    frame produced -- which is not exactly AUDIO_RATE_HZ / the machine's vblank rate.  Measured on
    a PAL run: 878 samples a frame where the machine's own 49.92 Hz implies 883, a 0.6% difference
    that walks a hit half a second out of place across two minutes and is the difference between
    identifying a quarter of the lane and identifying nearly all of it.  So the recording's own
    samples-per-frame is measured and used, and the machine's vblank rate is left to say PAL."""
    return audio_verify.AUDIO_RATE_HZ / (mono.size / vbl_count)


def bank_base_of(addresses, drum_offsets):
    """Where the linked sample bank sits in the running machine, solved from the plays themselves.

    The .PRG is relocated by TOS to an address this script cannot know, so the base is not computed
    from the ELF -- it is the candidate that explains every observed start address as some drum in
    the bank.  If two candidates could, the run is not identifiable and saying so is the only honest
    answer; picking the first would be a guess dressed as a measurement."""
    explains_all = [candidate
                    for candidate in {address - offset
                                      for address in addresses for offset in drum_offsets}
                    if all(address - candidate in drum_offsets for address in addresses)]
    if len(explains_all) != 1:
        return None
    return explains_all[0]


def play_the_game(out_dir, avi_path, trace_path):
    """A title-to-play run of BLACKICE.PRG with the sound and the trace recorded.

    THE SOUND COMES OUT INSIDE AN AVI because this Hatari has no --sound-file; audio/verify.py
    records the same way and unpacks the audio chunks with avi_audio.  The video is disabled for
    the reason its run_ste names: Hatari pulls one audio chunk per emulated frame either way, but
    with the video stream on most of those chunks come back ALL ZERO, the samples dropped while the
    frames are compressed.  The emulator still runs at 1.0x wall clock with it off, which is what
    the driver's held keys are timed against."""
    avi_path.unlink(missing_ok=True)
    extra = ["--country", PAL_COUNTRY,
             "--sound", str(audio_verify.AUDIO_RATE_HZ),
             "--disable-video", "on", "--avirecord", "--avi-file", str(avi_path),
             "--trace", TRACE_FLAGS, "--trace-file", str(trace_path)]
    session = play_headless.Session(HERE / "disk", out_dir, run_vbls=RUN_VBLS, extra=extra)
    await_the_title(session)
    session.wait(TITLE_SECONDS)
    session.tap("space")                        # leave the title for the first sector
    play_until(session, session.state()["tick"] + PLAY_TICKS)
    session.tap("esc")
    return session.close()


def await_the_title(session):
    """Block until the game is up, by asking RAM rather than by sleeping for a guessed while.

    What is waited on is the state structure appearing where play_headless finds it, which is the
    game running: EmuTOS, GEMDOS and the PAK load take as long as the host lets them."""
    for _ in range(BOOT_TRIES):
        try:
            session.state_address()
            return
        except SystemExit:
            session.wait(1.0)
    raise SystemExit("the game never reached its first frame")


def play_until(session, target_tick):
    """Walk and turn until the game's own tick counter passes `target_tick`.

    Moving matters: the trace meter drives the song's tempo, so a player standing still would
    record one band of the drum lane and nothing of the other three."""
    deadline = time.time() + PLAY_WALL_LIMIT
    while session.state()["tick"] < target_tick and time.time() < deadline:
        session.hold("up", STEP_SECONDS)
        session.hold("right", STEP_SECONDS)


def report(mono, run, bank_meta, blob):
    """Identify every play in the recording and print the hit rate."""
    drum_offsets = {bank_meta["samples"][index]["offset"]: index
                    for index in range(bank_meta["drum_first_index"], len(bank_meta["samples"]))}
    base = bank_base_of([address for _, address in run.plays], drum_offsets)
    if base is None:
        raise SystemExit(f"{len(run.plays)} DMA plays, and no one bank address explains them all "
                         "as drums")
    # Numbered from the driver's first sound-chip write, which is what the audio onset is too.
    hits = [(frame - run.music_frame, drum_offsets[address - base]) for frame, address in run.plays]
    vbl_hz = run.vbl_hz
    if abs(vbl_hz - PAL_VBL_HZ) / PAL_VBL_HZ > VBL_RATE_TOLERANCE:
        raise SystemExit(f"the machine's vblank is {vbl_hz:.2f} Hz, not PAL's {PAL_VBL_HZ} — the "
                         f"song is authored in PAL frames, so measure it on a --country "
                         f"{PAL_COUNTRY} machine or every hit is looked for in the wrong place")

    onset = audio_verify.find_music_onset(mono)
    recorded_hz = audio_frame_rate(mono, run.vbl_count)
    rows, lag_ms = audio_verify.check_drums(mono, onset, {"drum_hits": hits},
                                            bank_meta, blob, recorded_hz)
    heard = sum(1 for row in rows if row["ok"])
    span_seconds = (hits[-1][0] - hits[0][0]) / vbl_hz

    print(f"the machine's vblank measured {vbl_hz:.2f} Hz; the recording holds "
          f"{mono.size / run.vbl_count:.1f} samples a frame ({recorded_hz:.2f} Hz of .wav)")
    print(f"music starts {onset / audio_verify.AUDIO_RATE_HZ:.2f} s into the recording; "
          f"the drum lane fired {len(hits)} times over {span_seconds:.1f} s "
          f"({len(hits) / max(span_seconds, 1e-9):.2f} hits/s)")
    print(f"clock fitted on the kicks: {lag_ms[0]:+.1f} ms at the first, {lag_ms[1]:+.1f} ms at the "
          "last (Hatari's audio and vblank clocks drift apart across the window)")
    for index in sorted({fired for _, fired in hits}):
        mine = [row for row in rows if row["fired"] == index]
        right = sum(1 for row in mine if row["ok"])
        print(f"  {bank_meta['samples'][index]['name']:<6} {right:3d}/{len(mine):<3d} identified "
              f"({100.0 * right / len(mine):5.1f}%)")
    print(f"HIT RATE: {heard}/{len(rows)} = {100.0 * heard / len(rows):.1f}% of the lane's hits are "
          "the sample it asked for, heard in the game's own recording")
    return heard, len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(HERE / "out"), help="where the wav and the trace go")
    parser.add_argument("--reuse", action="store_true",
                        help="analyse the recording already in --out instead of making a new one")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path, trace_path = out_dir / "game_audio.wav", out_dir / "game_trace.log"
    avi_path = out_dir / "game_audio.avi"
    if not args.reuse:
        print(f"hatari exit: {play_the_game(out_dir, avi_path, trace_path)}")
        stereo, chunks = audio_verify.avi_audio(avi_path)
        audio_verify.write_wav(wav_path, stereo)
        avi_path.unlink()                       # tens of megabytes, and the .wav is all of it
        print(f"{wav_path}: {stereo.shape[0] / audio_verify.AUDIO_RATE_HZ:.1f} s of audio from "
              f"{chunks} chunks")

    run = read_drum_plays(trace_path)
    if not run.plays:
        raise SystemExit(f"{trace_path} holds no DMA sample start from our code — either the drum "
                         "lane never fired or the VBL never took it")
    if run.music_frame is None:
        raise SystemExit(f"{trace_path} holds no sound-chip write from our code — the music driver "
                         "never ran, so there is no origin to date the hits from")
    bank_meta = audio_verify.json.loads(BANK_META.read_text())
    heard, total = report(read_wav(wav_path), run, bank_meta, BANK_BLOB.read_bytes())
    return 0 if heard >= audio_verify.DRUM_IDENTIFY_FRACTION * total else 1


if __name__ == "__main__":
    raise SystemExit(main())
