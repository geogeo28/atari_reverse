#!/usr/bin/env python3
"""Record what the REAL Zynaps sounds like: boot it in Hatari and take two surfaces off the run.

Usage:
  python3 projects/zynaps/tools/ref_capture.py            # both spans, into out/audio/
  python3 projects/zynaps/tools/ref_capture.py --mode st  # off the raw sector image instead

This is the GROUND TRUTH the dumps in `out/audio/` are judged against, and it exists because
`extract_audio.py` cannot judge itself: it drives the original replayer under the kit's Musashi
oracle and renders the register stream with a software synth of our own, so a fault in either half
comes out as a plausible .wav. Hatari is an independent implementation of both halves — it runs the
whole game, not one routine, and it has its own YM2149 model — so agreeing with it is evidence.

TWO SURFACES, DELIBERATELY, because they fail differently:

  ref_<span>.wav      Hatari's own audio. 16-bit STEREO at 44100 Hz (both channels carry the same
                      mono PSG signal). This is the surface that can see a RENDERER fault — a tone
                      the software synth aliases into the audio band, a gain stage, an envelope —
                      and it is the only one that can, because the register stream is identical
                      either way.
  ref_<span>.regs     One line per 50 Hz frame: the eleven registers (10..0) the game's own tick
                      flushed, read out of Hatari's `--trace psg_write`. This is the surface that
                      can see a CAPTURE fault — a dump of the wrong stream, a driver ticked from a
                      state the game never has — and, again, only it can: two register streams that
                      differ can still render to audio that measures the same.

`compare_audio.py` reads both. Neither is a screenshot of the other: the .wav is judged by pitch and
level against `snd_NN.wav`, the .regs by exact frame equality against `snd_NN.ym`.

THE TWO SPANS

  title   the front end, where sound 0x0b (the boot tune, `_start`'s `moveq #$b,d1`) plays from
          power-on. Recorded once the front end is up, and long enough to hold a phrase.
  level1  a one-player game, entered through the same PREPARE-FOR-COMBAT gate `boot_shots.py`
          opens, with the fire button poked repeatedly so the ship actually shoots: the effects are
          what is wanted here, and an unattended ship makes none.

WHAT THIS RUN DOES NOT PROVE. Hatari is not hardware. Its YM2149 is a model like ours — a better
and much more scrutinised one, band-limited and volume-tabled, but still a model — so an agreement
number here is "two independent implementations agree", not "this is what the chip does". The
register surface is stronger: those bytes are the game's, and Hatari only carried them.

THE MACHINE is `boot_shots.py`'s (it owns the media matrix, the TOS ROM and the memory size), asked
for with sound on. Plain ST, RGB monitor, so 50 Hz — the game never writes $ffff820a, so the tick
rate is the machine's own PAL VBL and not something it chose.
"""
import argparse
import shutil
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import boot_shots                                   # noqa: E402  (owns this project's Hatari line)
from hatari_headless import (                       # noqa: E402
    RECORDED_CHANNELS, RECORDED_SAMPLE_BYTES, SOUND_UNDERRUN_MARKER, HeadlessSession, log_faults,
    sound_capture_arguments)

DEFAULT_OUT_DIR = PROJECT / "out" / "audio"
DEFAULT_MODE = "gemdos"                             # the fastest boot; the audio is the same on all

# --- what is recorded ---------------------------------------------------------------------------
SAMPLE_RATE = 44100                                 # matches ym2149.RATE, so no resampling compares
# The title tune's exact loop is 10304 frames = 206 s, so no practical recording holds a period of
# it. 40 s is several phrases — enough for a pitch track to align unambiguously and to cross every
# kind of frame the dump has (envelope-mode volumes, ultrasonic periods, noise).
TITLE_SECONDS = 40.0
LEVEL_SECONDS = 30.0
# The two spans, and the one place their names and lengths are spelled. Every output file is
# REF_PREFIX + span + a suffix, so a span cannot end up with a .wav under one name and a .regs
# under another.
REF_PREFIX = "ref_"
SPAN_TITLE, SPAN_LEVEL = "title", "level1"
SPANS = (SPAN_TITLE, SPAN_LEVEL)
SPAN_SECONDS = {SPAN_TITLE: TITLE_SECONDS, SPAN_LEVEL: LEVEL_SECONDS}
# The front end is up at load + ~27 s off a floppy (boot_shots.TIMELINE, measured); this waits past
# that on every medium rather than racing the loading picture, whose silence would be recorded.
TITLE_START_SECONDS = 30.0
GAMEPLAY_SETTLE_SECONDS = 3.0                       # let the level scroll in before recording
RECORDER_CLOSE_SECONDS = 1.0                        # Hatari closes the WAV after acting on the stop
# How often the trace is drained while waiting. Draining it is what keeps the read that MARKS a
# recording's start small, and that read's cost is skew between the register frame counter and the
# recorder: measured at ~220 frames (4.4 s) when the whole boot's trace was read in one go at the
# mark, and at a handful of frames when only the last couple of seconds are.
TRACE_DRAIN_SECONDS = 2.0

# --- making the ship fire -------------------------------------------------------------------------
# The gate poke `boot_shots.arm_fire_gate` installs answers ONE question (is fire down?) at ONE
# instruction. In the level the game reads the same byte from its own loop, so the only way to make
# it shoot is to keep putting fire back into it: the real IKBD replies clear the byte a few thousand
# cycles later, which is what gives each poke a fresh press-and-release edge.
FIRE_POKE_INTERVAL_SECONDS = 0.7

# --- the register surface ---------------------------------------------------------------------
# Hatari prints two lines per PSG write — the raw $ff8802 store and the decoded register — and only
# the decoded one carries both numbers.
PSG_TRACE_FLAG = "psg_write"
PSG_TRACE_PREFIX = "ym write data reg="
PSG_TRACE_VALUE_FIELD = "val="
# The driver's tick flushes registers 10..0 in that order and nothing else does (include/sound.h,
# PSG_TICK_FLUSH_REGS). Finding that exact descending run is how a frame is cut out of a trace that
# also holds TOS's own register-14 traffic for the floppy and the keyboard, and it needs no load
# address: a `pc=` filter would have to know where GEMDOS put the program.
TICK_FLUSH_ORDER = tuple(range(10, -1, -1))
# `sound_reset_psg` pushes the whole 14-register shadow the same descending way, so its tail looks
# exactly like a tick. It is skipped whole: it is the chip being silenced between sounds, not a
# frame of one, and counting it would put a muted frame in the middle of a stream to be matched.
RESET_FLUSH_ORDER = tuple(range(13, -1, -1))
REGS_SUFFIX = ".regs"
WAV_SUFFIX = ".wav"
REGS_HEADER = ("# one line per 50 Hz frame: the registers Zynaps' own sound_tick flushed, in the\n"
               "# order it flushed them (10..0), read out of Hatari's psg_write trace.\n"
               "# Written by projects/zynaps/tools/ref_capture.py; see compare_audio.py.\n")

# --- the success gate ------------------------------------------------------------------------
# A recording shorter than this fraction of what was asked for lost samples somewhere, whatever the
# log says; a full-length one that is silent is a run that never reached the music.
MIN_RECORDED_FRACTION = 0.98
# ...and a span's register stream must hold at least this much of the ticking a live replayer would
# have done over the seconds asked for. DERIVED from the span's own length rather than typed, so
# shortening a span cannot quietly leave the gate passing on a fraction of the frames.
MIN_FRAME_FRACTION = 0.5
FRAME_RATE = 50                                     # the VBL the driver ticks on
BYTES_PER_SECOND = SAMPLE_RATE * RECORDED_CHANNELS * RECORDED_SAMPLE_BYTES


def _writes_in(lines):
    """The (register, value) pairs in some lines of a psg_write trace."""
    writes = []
    for line in lines:
        at = line.find(PSG_TRACE_PREFIX)
        if at < 0:
            continue
        fields = line[at + len(PSG_TRACE_PREFIX):].split()      # "<reg> val=<value> video_cyc=..."
        if len(fields) < 2 or not fields[1].startswith(PSG_TRACE_VALUE_FIELD):
            continue
        writes.append((int(fields[0], 0), int(fields[1][len(PSG_TRACE_VALUE_FIELD):], 0)))
    return writes


def _frames_in(writes):
    """(the tick frames `writes` opens with, how many writes those consumed).

    A frame is a run of writes to registers 10, 9, ... 0 in that order. Anything else — TOS's
    register-14 drive select, the boot's mixer setup, `sound_reset_psg`'s wider flush — is skipped.
    Writes past the last complete run are left unconsumed, because the next read may finish them.
    """
    frames, at = [], 0
    while at < len(writes):
        for order, is_tick in ((RESET_FLUSH_ORDER, False), (TICK_FLUSH_ORDER, True)):
            run = writes[at:at + len(order)]
            if tuple(reg for reg, _value in run) != order:
                continue
            if is_tick:
                frames.append(dict(run))
            at += len(order)
            break
        else:
            if len(writes) - at < len(RESET_FLUSH_ORDER):
                break                       # too few left to tell a partial flush from a stray write
            at += 1
    return frames, at


class TraceReader:
    """The tick frames of a psg_write trace, read as the file grows.

    INCREMENTAL ON PURPOSE. This is read while Hatari is running, to mark where a recording starts
    in the register stream, and a trace of a boot plus a game reaches tens of megabytes. Re-reading
    and re-parsing the whole of it costs seconds — and those seconds are SKEW between the frame
    counter and the recorder, which is exactly what makes a recording hard to line up against its
    own registers afterwards. Measured before this was incremental: 100-400 frames, 2 to 8 seconds.
    """

    def __init__(self, path):
        self.path = Path(path)
        self._offset = 0
        self._partial = ""
        self._writes = []
        self.frames = []

    def update(self):
        """Take in whatever has been written since the last call. Returns the frame count."""
        with open(self.path, "rb") as handle:
            handle.seek(self._offset)
            blob = handle.read()
        self._offset += len(blob)
        lines = (self._partial + blob.decode("latin-1", "replace")).split("\n")
        self._partial = lines.pop()         # the last piece has no newline yet: it may be half a line
        self._writes.extend(_writes_in(lines))
        frames, consumed = _frames_in(self._writes)
        self._writes = self._writes[consumed:]
        self.frames.extend(frames)
        return len(self.frames)


def write_regs(path, frames):
    """One frame per line, registers in flush order, as two hex digits each."""
    with open(path, "w") as handle:
        handle.write(REGS_HEADER)
        for frame in frames:
            handle.write(" ".join("%02x" % frame[reg] for reg in TICK_FLUSH_ORDER) + "\n")


def read_regs(path):
    """Read back what `write_regs` wrote: a list of 16-byte register files, 11..15 left at 0.

    Registers 11..13 (the envelope) and 14..15 (the I/O ports) are not in the file because no tick
    writes them, and they are zeroed here rather than guessed: the chip's own power-on state is 0,
    which is the envelope shape (one ramp down, then silence) the shipped register shadow also
    carries. A .ym frame is 16 registers wide, so this returns that width.
    """
    frames = []
    for line in Path(path).read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        values = [int(field, 16) for field in line.split()]
        frame = bytearray(16)
        for reg, value in zip(TICK_FLUSH_ORDER, values):
            frame[reg] = value
        frames.append(bytes(frame))
    return frames


def _record_span(session, out_dir, span, wav_path, reader, first_frame, during=None):
    """Record one span, and file BOTH its surfaces under its own name.

    The .regs is written here rather than after the run so the two surfaces of a span are always
    the same boot: a failure between them used to leave this span's .wav beside the last run's
    .regs, and nothing downstream could tell.

    Returns (bytes of audio, frames of PSG traffic).
    """
    session.record_sound(SPAN_SECONDS[span], during)
    session.wait(RECORDER_CLOSE_SECONDS)
    stem = out_dir / (REF_PREFIX + span)
    shutil.copyfile(wav_path, stem.with_name(stem.name + WAV_SUFFIX))
    reader.update()
    frames = reader.frames[first_frame:]
    write_regs(stem.with_name(stem.name + REGS_SUFFIX), frames)
    return stem.with_name(stem.name + WAV_SUFFIX).stat().st_size, len(frames)


def _wait_draining(session, reader, seconds):
    """Wait `seconds`, keeping the trace reader up to date. See TRACE_DRAIN_SECONDS."""
    deadline = time.monotonic() + seconds
    while True:
        reader.update()
        left = deadline - time.monotonic()
        if left <= 0:
            return
        session.wait(min(TRACE_DRAIN_SECONDS, left))


def _fire_repeatedly(session, joystick_byte, seconds):
    """Hold the fire button down, over and over, for `seconds`. See FIRE_POKE_INTERVAL_SECONDS."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        session.poke(joystick_byte, boot_shots.JOY1_FIRE)
        session.wait(FIRE_POKE_INTERVAL_SECONDS)


def run(mode, out_dir, rom, version):
    """Boot once, record both spans, and write the four files. True if the run is evidence."""
    boot_shots.refuse_unsupported(mode, version)
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    # A run that fails part way must not leave one span's .wav beside the LAST run's .regs: they
    # would be two different boots, and nothing downstream could tell.
    for span in SPANS:
        for suffix in (WAV_SUFFIX, REGS_SUFFIX):
            (out_dir / (REF_PREFIX + span + suffix)).unlink(missing_ok=True)
    work = out_dir / "ref_work"
    work.mkdir(exist_ok=True)
    log = work / "ref_capture.log"
    trace = work / "psg_trace.txt"
    scratch_wav = work / "hatari.wav"

    argv = (boot_shots.hatari_arguments(mode, rom, gui=False, sound_hz=SAMPLE_RATE)
            + sound_capture_arguments(work / "sound.cfg", scratch_wav)
            + ["--trace", PSG_TRACE_FLAG, "--trace-file", str(trace)])
    session = HeadlessSession(argv, log_path=log, fifo_path=work / "ref.fifo", work_dir=work)
    reader = TraceReader(trace)
    sizes, counted = {}, {}
    try:
        base = boot_shots.wait_for_load(session)
        marker = boot_shots.arm_fire_gate(session, base)
        reader.update()                     # absorb the boot's trace before it is in anyone's way
        _wait_draining(session, reader, TITLE_START_SECONDS)
        first_frame = reader.update()
        sizes[SPAN_TITLE], counted[SPAN_TITLE] = _record_span(
            session, out_dir, SPAN_TITLE, scratch_wav, reader, first_frame)

        session.key(boot_shots.KEY_ONE_PLAYER)
        boot_shots.await_gate(session, marker)
        _wait_draining(session, reader, GAMEPLAY_SETTLE_SECONDS)
        first_frame = reader.update()
        joystick_byte = base + boot_shots.JOY1_STATE_OFFSET
        sizes[SPAN_LEVEL], counted[SPAN_LEVEL] = _record_span(
            session, out_dir, SPAN_LEVEL, scratch_wav, reader, first_frame,
            during=lambda seconds: _fire_repeatedly(session, joystick_byte, seconds))
    finally:
        status = session.close()

    problems = [f"Hatari logged: {line}" for line in log_faults(log)]
    if status != 0:
        problems.append(f"Hatari exited with status {status}")
    for span, size in sizes.items():
        recorded = size / BYTES_PER_SECOND
        asked = SPAN_SECONDS[span]
        wanted = int(MIN_FRAME_FRACTION * asked * FRAME_RATE)
        if recorded < MIN_RECORDED_FRACTION * asked:
            problems.append(f"{REF_PREFIX}{span}{WAV_SUFFIX} holds {recorded:.1f}s of the "
                            f"{asked:.0f}s asked for")
        if counted[span] < wanted:
            problems.append(f"{REF_PREFIX}{span}{REGS_SUFFIX} holds {counted[span]} frames, under "
                            f"the {wanted} a live replayer would have ticked in {asked:.0f}s")

    for span in sorted(sizes):
        print(f"-- {REF_PREFIX}{span}: {sizes[span] / BYTES_PER_SECOND:.1f}s of audio, "
              f"{counted[span]} frames of PSG traffic")
    # Hatari drops samples rather than stalling when its mixer buffer overruns. That shortens the
    # file, which the length gate above measures directly, so this is reported and not judged:
    # overruns during the boot (where most of them happen) cost the recordings nothing.
    if log_faults(log, markers=(SOUND_UNDERRUN_MARKER,)):
        print("   note: Hatari logged a mixer overrun during the run; the recorded lengths above "
              "are what says whether a span lost samples")
    for problem in problems:
        print(f"   FAIL: {problem}")
    if not problems:
        print("wrote %s .wav and .regs to %s"
              % (" / ".join(REF_PREFIX + span for span in SPANS), out_dir))
    return not problems


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=boot_shots.BOOT_MODES, default=DEFAULT_MODE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--tos", choices=tuple(boot_shots.TOS_SHORTCUTS), default=boot_shots.DEFAULT_TOS)
    parser.add_argument("--tos-rom", help="boot this TOS image instead")
    options = parser.parse_args()
    rom, version = boot_shots.resolve_tos(options.tos_rom, options.tos)
    return 0 if run(options.mode, options.out, rom, version) else 1


if __name__ == "__main__":
    sys.exit(main())
