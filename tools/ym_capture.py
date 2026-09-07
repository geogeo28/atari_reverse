"""The output half of a YM2149 capture: register shadow -> .ym / .wav, and "is this audible?".

Every `projects/<game>/tools/extract_audio.py` in this workspace drives its own game's sound driver
under the kit's oracle, and every one of them then does the SAME four things with what it recorded:
fold the (register, value) stream into a 16-byte shadow, ask whether a frame would make a sound on
the chip, write the frames as an uncompressed interleaved YM6 file, and write a rendered float track
as 16-bit mono PCM. None of that is game-specific — it is the chip's own decode and two file
formats — so it lives here once.

WHAT IS NOT HERE. The capture itself (which routine to enter, when a track ends, what the frames
mean) is each game's, and so is the RENDER: `projects/buggyboy/recreate/sound/ym2149.py` is the
workspace's one synth, but it lives inside a reconstruction rather than in `tools/`, so a caller
imports it and hands `write_wav` the float track. That keeps this module to the standard library
plus numpy, which is what its callers already need.

PENDING MIGRATION. `projects/bubbleghost/tools/extract_audio.py` and
`projects/flyingshark/tools/extract_audio.py` are the callers today;
`projects/zynaps/tools/extract_audio.py` and `projects/wonderboy/tools/extract_audio.py` still hold
verbatim copies of these functions and are the two files left to move over.

WHAT IS THE CALLER'S, not the chip's: whether a channel handed to the envelope generator is making a
sound. That is a property of the driver being captured — Flying Shark's effects hold channel C in
envelope mode and Bubble Ghost's engine never starts a generator at all — so it is `channel_sounds`'s
`envelope_is_level` argument rather than a rule this module picks.
"""
import math
import struct
import wave

import numpy

# ---- the chip, as a captured frame shows it ------------------------------------------------------

YM_REGISTERS = 16                    # a YM6 frame carries all of them
CHANNELS = 3                         # three square-wave tone channels sharing one noise source
PSG_MIXER_REG = 7
PSG_VOLUME_A_REG = 8                 # register 8+c holds channel c's level
VOLUME_LEVEL_MASK = 0x0f
VOLUME_ENVELOPE_BIT = 0x10           # set = this channel takes the envelope generator's level
NOISE_MIXER_SHIFT = 3                # mixer bits 0..2 are the tone gates, 3..5 the noise gates

# ---- the two containers --------------------------------------------------------------------------

YM6_MAGIC = b"YM6!"
YM6_CHECK = b"LeOnArD!"
YM6_ATTRIBUTE_INTERLEAVED = 1 << 0
YM6_DIGIDRUMS = 0
YM6_EXTRA_BYTES = 0
YM6_END = b"End!"
# The three strings are 8-BIT text: a YM player renders them in the machine's own character set,
# where no byte means "em dash". They are therefore ASCII, and the encode says so.
YM6_TEXT_ENCODING = "ascii"
YM6_HEADER_FIELDS = ">IIHIHIH"       # frames, attributes, digidrums, clock, rate, loop, extra bytes

WAV_CHANNELS = 1
SAMPLE_BYTES = 2                     # 16-bit PCM
INT16_PEAK = 32767
# One 16-bit quantisation step: below it a render writes an all-zero .wav, so this is what "the
# render came out silent" means rather than an exact 0.0 the DC blocker never produces.
RENDER_SILENCE_PEAK = 1.0 / INT16_PEAK


def fold(shadow, writes):
    """Apply one run's `(register, value)` writes to a running register shadow.

    Returns the set of registers touched. The shadow is the chip's own latch: a driver writes only
    what changed, so a frame's register file is the shadow AFTER that frame's writes, not the writes
    themselves.
    """
    touched = set()
    for reg, value in writes:
        shadow[reg] = value
        touched.add(reg)
    return touched


def gate_open(frame, channel):
    """Is either of `channel`'s two mixer gates open? They are active LOW.

    Exported because it is half of the audibility rule and a caller with its own envelope policy
    needs exactly this bit of the chip's decode — copying the two lines is how a wrong
    `NOISE_MIXER_SHIFT` gets a second home.
    """
    mixer = frame[PSG_MIXER_REG]
    return not (mixer >> channel) & 1 or not (mixer >> (channel + NOISE_MIXER_SHIFT)) & 1


def channel_sounds(frame, channel, envelope_is_level=False):
    """Is `channel` audible in `frame`? A gate open, and a volume that is not silence.

    Bit 4 of a volume register selects the ENVELOPE generator rather than the 4-bit level, and what
    that means for audibility is the CALLER'S DRIVER, not the chip: `envelope_is_level` false — the
    default — reads such a channel as silent however large the byte is, which is right for a driver
    that never triggers the generator and is why the level is not simply masked to four bits and
    compared. A driver that DOES drive a channel through the envelope (Flying Shark's sound effects
    hold channel C at volume 0x10 with a shape latched) passes true, and then an envelope-mode
    channel with a gate open counts as sounding.

    A channel with BOTH gates closed is silent either way, and that is the chip: it holds the DAC at
    a constant level, which is DC and not a sound.
    """
    volume = frame[PSG_VOLUME_A_REG + channel]
    if volume & VOLUME_ENVELOPE_BIT:
        return envelope_is_level and gate_open(frame, channel)
    return bool(volume & VOLUME_LEVEL_MASK) and gate_open(frame, channel)


def audible_frames(frames, envelope_is_level=False):
    """How many of `frames` would make a sound on the chip, under `channel_sounds`'s rule."""
    return sum(1 for frame in frames
               if any(channel_sounds(frame, channel, envelope_is_level)
                      for channel in range(CHANNELS)))


def peak_dbfs(level):
    """A render's peak in dBFS, or "-" where it came out silent."""
    return "%.1f" % (20.0 * math.log10(level)) if level else "-"


def write_ym6(path, frames, title, author, comment, frame_rate, clock, loop_frame=0):
    """Write `frames` (each `YM_REGISTERS` bytes) as an uncompressed interleaved YM6 file.

    `frame_rate` is the rate the driver STEPS at, which YM6 carries as a header field precisely so
    that a driver ticked by something other than the VBL can be written down as itself. `clock` is
    the chip's master clock. `loop_frame` is where a player restarts; YM6 has no "does not loop"
    flag, so a one-shot passes 0 and says so elsewhere.

    INTERLEAVED means all of register 0's bytes, then all of register 1's: the transpose of the
    frame list. It is done through numpy because the list comprehension it replaces built one Python
    object per register-byte, which on a 48,000-frame sweep is 768,000 of them.
    """
    header = (YM6_MAGIC + YM6_CHECK
              + struct.pack(YM6_HEADER_FIELDS, len(frames), YM6_ATTRIBUTE_INTERLEAVED,
                            YM6_DIGIDRUMS, clock, frame_rate, loop_frame, YM6_EXTRA_BYTES)
              + title.encode(YM6_TEXT_ENCODING) + b"\0" + author.encode(YM6_TEXT_ENCODING) + b"\0"
              + comment.encode(YM6_TEXT_ENCODING) + b"\0")
    interleaved = (numpy.frombuffer(b"".join(frames), dtype=numpy.uint8)
                   .reshape(len(frames), YM_REGISTERS).T.tobytes())
    with open(path, "wb") as handle:
        handle.write(header + interleaved + YM6_END)


def write_wav(path, track, rate):
    """Write a rendered float `track` as `rate` Hz 16-bit mono. Returns its peak, 0..1.

    The peak is what a manifest reports in dBFS and what `RENDER_SILENCE_PEAK` is compared against,
    so it is taken from the float track rather than from the quantised samples: a track whose whole
    content is below one 16-bit step still has a peak here, and rounds to an all-zero file.
    """
    # `str` because `wave.open` takes a filename or an open file and nothing in between: handed a
    # `Path` it treats it as the file and fails inside the header write, not at the call.
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(WAV_CHANNELS)
        handle.setsampwidth(SAMPLE_BYTES)
        handle.setframerate(rate)
        handle.writeframes(numpy.clip(track * INT16_PEAK, -INT16_PEAK, INT16_PEAK)
                           .astype("<i2").tobytes())
    return float(max(track.max(), -track.min()))
