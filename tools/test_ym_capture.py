#!/usr/bin/env python3
"""The pins for `tools/ym_capture.py` — the YM6 container, the fold, and the audibility rule.

WHY IT LIVES HERE, next to the tool, and not under any `projects/<name>/recreate/test/`: the module
is game-agnostic — two file formats and the YM2149's own decode — and a per-project suite would pin
a shared tool from inside one game. Like `tools/test_hw_portability.py` it is deliberately NOT wired
into any project's `make test`, which builds an oracle `.so` nothing here needs.

Run it standalone:

    pytest tools/test_ym_capture.py

THREE GROUPS, and the failure each exists to catch:

  * the CONTAINER — a YM6 file read back field by field. The header is seven big-endian numbers and
    three NUL-terminated strings, and a caller has no way to notice a wrong one: a player either
    refuses the file or plays it at the wrong speed, and neither reaches the tool that wrote it.
  * the INTERLEAVE — that the transpose really is register-major. It went through numpy for speed,
    and a `.T` on the wrong axis produces a file of exactly the right LENGTH holding the frames in
    frame-major order, which nothing about the format's size would catch.
  * the AUDIBILITY RULE — `channel_sounds`, whose three clauses (the envelope bit, the level, the
    two gates) each make a frame silent for a different reason. The NOISE gate's shift is pinned
    here in particular: a capture whose game never closes both gates on a live channel cannot tell
    a right shift from a wrong one, so the chip's own bit assignment is stated here instead. The
    envelope clause is the one that is the CALLER'S and not the chip's — `envelope_is_level` — so
    both of its answers are pinned, and so is the gate helper the policy makes callers reuse.
"""
import pathlib
import struct
import sys

import numpy
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import ym_capture  # noqa: E402  (needs the path above)

FRAME_RATE = 200                        # a timer-driven driver, not a VBL: the field is not a 50
CLOCK = 2_000_000                       # the ST's YM2149 master clock
LOOP_FRAME = 7
TITLE, AUTHOR, COMMENT = "a title", "an author", "a comment"


def frames(count):
    """`count` frames whose every byte is distinct across (frame, register), so a transpose that
    came out frame-major cannot look like one that came out register-major."""
    return [bytes((frame * ym_capture.YM_REGISTERS + reg) & 0xff
                  for reg in range(ym_capture.YM_REGISTERS))
            for frame in range(count)]


def read_ym6(path):
    """(header fields, the three strings, interleaved body) of a YM6 file this module wrote."""
    blob = path.read_bytes()
    assert blob.startswith(ym_capture.YM6_MAGIC + ym_capture.YM6_CHECK)
    assert blob.endswith(ym_capture.YM6_END)
    at = len(ym_capture.YM6_MAGIC) + len(ym_capture.YM6_CHECK)
    size = struct.calcsize(ym_capture.YM6_HEADER_FIELDS)
    fields = struct.unpack_from(ym_capture.YM6_HEADER_FIELDS, blob, at)
    at += size
    strings = []
    for _ in range(3):
        end = blob.index(b"\0", at)
        strings.append(blob[at:end].decode(ym_capture.YM6_TEXT_ENCODING))
        at = end + 1
    return fields, strings, blob[at:-len(ym_capture.YM6_END)]


# ==================================================== the container


def test_ym6_header_round_trips(tmp_path):
    """Every header field comes back as the argument that was passed for it."""
    path = tmp_path / "track.ym"
    ym_capture.write_ym6(path, frames(3), TITLE, AUTHOR, COMMENT, FRAME_RATE, CLOCK, LOOP_FRAME)
    fields, strings, body = read_ym6(path)
    assert fields == (3, ym_capture.YM6_ATTRIBUTE_INTERLEAVED, ym_capture.YM6_DIGIDRUMS,
                      CLOCK, FRAME_RATE, LOOP_FRAME, ym_capture.YM6_EXTRA_BYTES)
    assert strings == [TITLE, AUTHOR, COMMENT]
    assert len(body) == 3 * ym_capture.YM_REGISTERS


def test_ym6_loop_frame_defaults_to_the_start():
    """A one-shot passes no loop frame, and the format has no flag for "does not loop"."""
    assert ym_capture.write_ym6.__defaults__ == (0,)


def test_ym6_body_is_register_major(tmp_path):
    """The interleave is all of register 0's bytes, then all of register 1's — not frame-major.

    Both orders produce a body of identical length, so this is the only thing that separates them.
    """
    path = tmp_path / "track.ym"
    made = frames(5)
    ym_capture.write_ym6(path, made, TITLE, AUTHOR, COMMENT, FRAME_RATE, CLOCK)
    _fields, _strings, body = read_ym6(path)
    assert body == bytes(frame[reg] for reg in range(ym_capture.YM_REGISTERS) for frame in made)


def test_ym6_accepts_an_empty_track(tmp_path):
    """A capture that ended before its first frame writes a header and no body, not a crash."""
    path = tmp_path / "empty.ym"
    ym_capture.write_ym6(path, [], TITLE, AUTHOR, COMMENT, FRAME_RATE, CLOCK)
    fields, _strings, body = read_ym6(path)
    assert fields[0] == 0 and body == b""


# ==================================================== the fold


def test_fold_keeps_the_last_write_and_reports_every_register():
    """The shadow is the chip's latch: a second write to one register replaces the first, and the
    registers a run touched are what a manifest's `psg_regs` column is."""
    shadow = bytearray(ym_capture.YM_REGISTERS)
    touched = ym_capture.fold(shadow, [(1, 0x11), (7, 0x38), (1, 0x22)])
    assert touched == {1, 7}
    assert shadow[1] == 0x22 and shadow[7] == 0x38


def test_fold_leaves_untouched_registers_alone():
    """A driver writes only what changed, so everything else must survive the fold unaltered."""
    shadow = bytearray(range(ym_capture.YM_REGISTERS))
    ym_capture.fold(shadow, [(8, 0x0f)])
    assert bytes(shadow) == bytes(range(8)) + bytes([0x0f]) + bytes(range(9, 16))


# ==================================================== the audibility rule


def frame_with(mixer, volumes):
    """One register file: `mixer` in register 7 and `volumes` in registers 8..10."""
    frame = bytearray(ym_capture.YM_REGISTERS)
    frame[ym_capture.PSG_MIXER_REG] = mixer
    frame[ym_capture.PSG_VOLUME_A_REG:ym_capture.PSG_VOLUME_A_REG + len(volumes)] = volumes
    return bytes(frame)


ALL_GATES_OPEN = 0x00                   # gates are active LOW, so 0 opens every one of them
ALL_GATES_SHUT = 0x3f


@pytest.mark.parametrize("channel", range(ym_capture.CHANNELS))
def test_a_channel_needs_a_level(channel):
    """Volume 0 is silence whatever the mixer says."""
    volumes = [0, 0, 0]
    assert not ym_capture.channel_sounds(frame_with(ALL_GATES_OPEN, volumes), channel)
    volumes[channel] = 1
    assert ym_capture.channel_sounds(frame_with(ALL_GATES_OPEN, volumes), channel)


@pytest.mark.parametrize("channel", range(ym_capture.CHANNELS))
def test_a_channel_needs_a_gate(channel):
    """Both gates shut holds the DAC at a constant, which is DC and not a sound."""
    volumes = [15, 15, 15]
    assert not ym_capture.channel_sounds(frame_with(ALL_GATES_SHUT, volumes), channel)


@pytest.mark.parametrize("channel", range(ym_capture.CHANNELS))
def test_the_envelope_bit_is_not_a_level(channel):
    """Bit 4 selects the envelope generator, so the low nibble under it is not a volume at all."""
    volumes = [0, 0, 0]
    volumes[channel] = ym_capture.VOLUME_ENVELOPE_BIT | 0x0f
    assert not ym_capture.channel_sounds(frame_with(ALL_GATES_OPEN, volumes), channel)


@pytest.mark.parametrize("channel", range(ym_capture.CHANNELS))
def test_an_envelope_channel_sounds_only_under_the_envelope_policy(channel):
    """`envelope_is_level` is the caller's driver, not the chip: the same frame reads both ways.

    Whether a channel handed to the envelope generator is making a sound depends on whether that
    driver ever starts one, which this module cannot know. The default says no — a driver that never
    latches a shape leaves the generator at whatever it was, and reading that as audible would call
    every silent frame loud. Flying Shark's effects DO drive channel C that way (volume 0x10, shape
    0x09), and pass true. The low nibble is 0 in both frames below precisely because it is not a
    level under bit 4: the policy alone is what separates the two answers.
    """
    volumes = [0, 0, 0]
    volumes[channel] = ym_capture.VOLUME_ENVELOPE_BIT
    frame = frame_with(ALL_GATES_OPEN, volumes)
    assert not ym_capture.channel_sounds(frame, channel)
    assert ym_capture.channel_sounds(frame, channel, envelope_is_level=True)
    # ...and the gate still has the last word, under either policy.
    shut = frame_with(ALL_GATES_SHUT, volumes)
    assert not ym_capture.channel_sounds(shut, channel, envelope_is_level=True)


def test_audible_frames_threads_the_envelope_policy():
    """The count is `channel_sounds` per frame, policy and all — not a second, fixed rule."""
    envelope = frame_with(ALL_GATES_OPEN, [ym_capture.VOLUME_ENVELOPE_BIT, 0, 0])
    silent = frame_with(ALL_GATES_OPEN, [0, 0, 0])
    assert ym_capture.audible_frames([envelope, silent]) == 0
    assert ym_capture.audible_frames([envelope, silent], envelope_is_level=True) == 1


@pytest.mark.parametrize("channel", range(ym_capture.CHANNELS))
def test_gate_open_is_the_exported_half_of_the_rule(channel):
    """The gate test callers reuse is the one `channel_sounds` runs, at the chip's own bit pair."""
    assert ym_capture.gate_open(frame_with(ALL_GATES_OPEN, [0, 0, 0]), channel)
    assert not ym_capture.gate_open(frame_with(ALL_GATES_SHUT, [0, 0, 0]), channel)
    tone_only = ALL_GATES_SHUT & ~(1 << channel)
    noise_only = ALL_GATES_SHUT & ~(1 << (channel + ym_capture.NOISE_MIXER_SHIFT))
    assert ym_capture.gate_open(frame_with(tone_only, [0, 0, 0]), channel)
    assert ym_capture.gate_open(frame_with(noise_only, [0, 0, 0]), channel)


@pytest.mark.parametrize("channel", range(ym_capture.CHANNELS))
def test_each_gate_alone_is_audible_at_its_own_bit(channel):
    """The chip's bit assignment: channel c's tone gate is bit c and its noise gate is bit c+3.

    Both directions are asserted per channel, so a shift that moved the noise gate to another
    channel's bit — which a capture whose driver never closes both gates cannot notice — fails here.
    """
    volumes = [15, 15, 15]
    tone_only = ALL_GATES_SHUT & ~(1 << channel)
    noise_only = ALL_GATES_SHUT & ~(1 << (channel + ym_capture.NOISE_MIXER_SHIFT))
    assert ym_capture.channel_sounds(frame_with(tone_only, volumes), channel)
    assert ym_capture.channel_sounds(frame_with(noise_only, volumes), channel)
    for other in range(ym_capture.CHANNELS):
        if other != channel:
            assert not ym_capture.channel_sounds(frame_with(tone_only, volumes), other)
            assert not ym_capture.channel_sounds(frame_with(noise_only, volumes), other)


def test_audible_frames_counts_frames_not_channels():
    """A frame with two channels sounding is one audible frame, and a silent one is none."""
    loud = frame_with(ALL_GATES_OPEN, [15, 15, 0])
    quiet = frame_with(ALL_GATES_OPEN, [0, 0, 0])
    assert ym_capture.audible_frames([loud, quiet, loud]) == 2


# ==================================================== the render's two reports


def test_peak_dbfs_names_full_scale_and_silence():
    assert ym_capture.peak_dbfs(1.0) == "0.0"
    assert ym_capture.peak_dbfs(0.5) == "-6.0"
    assert ym_capture.peak_dbfs(0.0) == "-"


def test_write_wav_returns_the_float_peak_and_quantises(tmp_path):
    """The peak is the FLOAT track's, so a track under one 16-bit step still reports one — and
    writes the all-zero file that `RENDER_SILENCE_PEAK` describes."""
    path = tmp_path / "quiet.wav"
    track = numpy.full(8, ym_capture.RENDER_SILENCE_PEAK / 4)
    peak = ym_capture.write_wav(path, track, 48000)
    assert peak == pytest.approx(ym_capture.RENDER_SILENCE_PEAK / 4)
    assert set(path.read_bytes()[-16:]) == {0}
