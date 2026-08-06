#!/usr/bin/env python3
"""Dump Wonder Boy in Monsterland's (Atari ST) music and sound effects.

Usage:
  python3 projects/wonderboy/tools/extract_audio.py [OUT_DIR]

OUT_DIR defaults to `projects/wonderboy/out/audio`. Reads only the game's own binary under
`projects/wonderboy/bin/` (AUTO/SWB.PRG, through the kit's PRG loader) and writes:

  songs/song_NN.ym    the 17 songs, one YM2149 register file per 50 Hz frame (YM6 format)
  songs/song_NN.wav   the same frames rendered to 44100 Hz 16-bit mono
  sfx/sfx_NN.ym       the 26 sound effects, in the same two forms
  sfx/sfx_NN.wav
  manifest.txt        per asset: frames, seconds, how the capture ended, PSG registers touched,
                      and for a song its speed byte from the song directory

THIS IS AN ORACLE-DRIVEN CAPTURE, NOT A STATIC PARSE. The game's replay driver is a self-contained
PSG player reached through `snd_stub_00` ($17adc); `../notes/sound_module_recon.md` decodes its
formats completely, but rather than re-implement them this tool RUNS THE ORIGINAL 68000 CODE under
the kit's Musashi oracle (`tools/recreate_kit`) and records what it writes to the chip:

  stub +0  `snd_play_song`      once, with d0 = song id       -> loads the song, enables the engine
  stub +56 `snd_trigger_effect` once, with d0 = SFX id, d1 = 0 (channel A: the only one the game
                                                                ever passes -- recon section 3)
  stub +14 `snd_music_tick`     once per emulated 50 Hz frame -> one frame of PSG traffic

Each tick's `(reg, value)` writes are folded into a running shadow of the chip's 16 registers, and
the shadow is snapshotted after every tick. That snapshot IS a YM frame.

THE TWO HARDWARE READS THAT MAKE IT POSSIBLE are what `emu.audio_capture` exists to serve, and both
are silent failures without it (see tools/recreate_kit/TRAP_MODEL.md):

  * `$ff8800` read-back. `snd_music_tick` merges its mixer bits into register 7 with a
    read-modify-write ($17f08). The oracle models that read from a register file either way, but a
    differential refuses one of a register the CASE has not declared — and a capture cannot declare a
    seed per tick, so the first tick would sink the run. The mode relaxes exactly that: an undeclared
    register reads 0, and the file spans runs so each tick sees the last one's writes.
  * `$fffa01` bit 7 (monitor detect) and `$ff820a` bit 1 (shifter sync), the driver's tempo
    selector ($17c7e..$17c9a). Read as 0 -- which is what unmodeled hardware returns -- they mean
    MONOCHROME, and the driver then drops 72/256 of every tick: every song would come out 28% slow
    with nothing raising. The mode reports the 50 Hz colour ST, so one tick per frame is one 50 Hz
    music tick, and the capture asserts `snd_tick_drop_value` ($17c6e) is 0 after each asset's
    first tick rather than trusting it.

The driver runs privileged (`move.w #$2700,sr` around its PSG windows) and keeps every byte of its
state inside its own code image; the oracle runs in supervisor mode on a writable image, so both
hold. It needs nothing else -- no interrupts, no timers, no TOS.

EVERY ASSET IS CAPTURED FROM A FRESH IMAGE (`harness.make_image()`), because the shipped image
carries live residue from a run at another load base and `snd_play_song` does not reset all of it:
not the SFX channel blocks at `snd_sfx_channel_state`, and not the PRNG at `snd_prng_state`, which
nothing ever resets. SFX 12/20/21 take their pitch jitter from that PRNG (descriptor +7), so they
are deterministic here only BECAUSE each capture starts from the shipped PRNG seed -- in the game
they depend on how long the machine has been running.

WHERE EACH CAPTURE STOPS. Four rules, and the manifest says which one ended each capture:

  self-ended     the song executed the end-of-song opcode $8e (`snd_engine_enabled` goes 0), or the
                 SFX cleared its active flag. Only 11 `$8e` opcodes exist in the whole data set.
  exact loop     the module's whole mutable state repeated, which proves the output repeats forever
                 from that frame.
  musical loop   the same hash with the song-speed accumulator ($17c6a) left out repeated. Nine of
                 the seventeen songs need this: their speed byte is ODD, so that one byte alone has
                 a period of 256 ticks and the exact state cannot repeat before ~lcm(pattern, 256)
                 frames -- none of the nine did inside 15000, and what those 300 s held was one
                 short phrase over and over. The rule is armed only for songs whose accumulator
                 makes the exact loop unaffordable (MAX_AFFORDABLE_ACCUMULATOR_PERIOD), so it never
                 pre-empts one; and a candidate must span at least one ROW (`_row_tick_count`), so a
                 held note cannot pose as a loop. How much of the loop's second period actually
                 replays its first is MEASURED (`_loop_replay_agreement`) and reported per song in
                 the manifest, because a musical loop's join is not sample-exact and saying so is
                 cheaper than pretending otherwise.
  capped         none of the above inside SONG_FRAME_CAP / SFX_FRAME_CAP frames.

WHAT THE RENDERER MODELS. Square tone per channel from the 12-bit period, noise from the chip's
17-bit LFSR, the mixer's active-low tone/noise gates, and the 4-bit logarithmic volume DAC. It does
NOT implement the envelope generator (registers 11-13): this driver never writes them, which
`_vetted_psg_writes` asserts on every single write rather than assuming. The output is 4x
oversampled and box-decimated, which takes the worst of the aliasing off a hard square wave but is
not a band-limited synthesis; and it is scaled by a FIXED factor, never normalised per file, so
that one asset's loudness is comparable to another's and a silent capture stays measurably silent.
Two checks stand behind it: every .wav must clear an RMS floor, and song 0's spectrum must be
EXPLAINED by its own register stream -- `check_render_spectrum` FFTs a window of the render and
requires each of its strongest peaks to be a harmonic of a tone period the capture actually wrote.

Addresses are RUNTIME addresses at this project's load base $3f8, and every one of them is looked
up in `../names.txt` by name (`leaf.entry_of`, the same lookup the differential batteries use)
rather than spelled as a literal, so a rename or a move fails here loudly instead of capturing from
a stale address.
"""

import functools
import math
import os
import struct
import sys
import wave
from collections import Counter, namedtuple

try:
    import numpy as np
except ImportError:
    raise SystemExit("this tool needs numpy: run it with the atari_reverse conda env's python "
                     "(the interpreter this workspace supports), or `pip install numpy`")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(PROJECT_DIR))
RECREATE_DIR = os.path.join(PROJECT_DIR, "recreate")
DEFAULT_OUT_DIR = os.path.join(PROJECT_DIR, "out", "audio")

sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
from recreate_kit import project                    # noqa: E402  (needs the path above)

project.load(RECREATE_DIR)                          # binds the kit to this game's project.toml
sys.path.insert(0, os.path.join(RECREATE_DIR, "test"))   # where leaf.py and its harness shim live
try:
    from recreate_kit import harness                # noqa: E402  (must follow project.load)
    import emu                                      # noqa: E402
    import leaf                                     # noqa: E402  (recreate/test/leaf.py: entry_of)
except (OSError, RuntimeError) as error:
    # OSError is the ctypes.CDLL behind any of the three; RuntimeError is the kit's own stale-.so
    # check, whose message already names the symbol and the rebuild that restores it.
    raise SystemExit("this tool drives the kit's Musashi oracle and the project's own library, and "
                     "one of them is not built or is out of date (%s):\n"
                     "  make -C projects/wonderboy/recreate" % error)

# ---- the sound module, addressed by name ------------------------------------------------------
# Every name below is a `fn`/`var` line in ../names.txt; the roles are from ../notes/
# sound_module_recon.md, whose section numbers the comments cite. `leaf.entry_of` is the batteries'
# own lookup (exactly one address per name, or a loud failure), reused rather than restated.

SND_STUB = leaf.entry_of("snd_stub_00")                       # the module's entry vector, $17adc
# Byte offsets into that vector (recon section 1). The register each thunk expects is in the map.
STUB_PLAY_SONG = 0                                            # d0.b = song id
STUB_TICK = 14                                                # the per-VBL tick vbl_handler calls
STUB_STOP = 28                                                # stop + silence, resumable
STUB_TRIGGER_SFX = 56                                         # d0.b = SFX id, d1.b = channel
SFX_CHANNEL_A = 0                                             # every call site in the game passes 0

SND_ENGINE_ENABLED = leaf.entry_of("snd_engine_enabled")      # $17c56; 0 once opcode $8e ran
SND_TICK_DROP_VALUE = leaf.entry_of("snd_tick_drop_value")    # $17c6e; 0 on the 50 Hz colour path
SND_SONG_DIRECTORY = leaf.entry_of("snd_song_directory")      # $18480; 17 records of 8 bytes
SND_MUSIC_CHANNEL_STATE = leaf.entry_of("snd_music_channel_state")   # $17bc6; 3 x 48 bytes
SND_PSG_SHADOW = leaf.entry_of("snd_psg_shadow")              # $18352; regs 0..10 + the SFX mix
SND_NOTE_PERIOD_TABLE = leaf.entry_of("snd_note_period_table")   # $1836e; where that region ends
SND_SFX_CHANNEL_STATE = leaf.entry_of("snd_sfx_channel_state")   # $1aa7c; 3 x 26 bytes
SND_PRNG_STATE = leaf.entry_of("snd_prng_state")              # $1aae6; 4 bytes, stepped every tick

# Two module globals with no name of their own in ../names.txt, spelled as offsets from the global
# that does name the block they are in — snd_engine_enabled's `cmt` maps $17c56..$17c71 (a3+2250..
# a3+2277) field by field, and recon section 6 tabulates the same bytes.
SFX_ACTIVE_FLAGS_OFFSET = 4                                   # $17c5a, a3+2254: the A/B/C flags,
SND_SFX_ACTIVE_FLAGS = SND_ENGINE_ENABLED + SFX_ACTIVE_FLAGS_OFFSET   # tested as a long at $17ca6
SONG_SPEED_ACCUMULATOR_OFFSET = 0x14                          # $17c6a, a3+2270: the fractional row
SND_SONG_SPEED_ACCUMULATOR = SND_ENGINE_ENABLED + SONG_SPEED_ACCUMULATOR_OFFSET   # rate's carry acc

SONG_COUNT = 17                                               # ids $00..$10 (recon section 6)
SFX_COUNT = 26                                                # ids $00..$19 (recon section 2)
SONG_RECORD_BYTES = 8
SONG_SPEED_OFFSET = 1                                         # byte +1: the fractional row rate
# Two speeds the recon states outright. Spot-pinned so that a wrong SND_SONG_DIRECTORY — which
# would otherwise report plausible garbage for all 17 — fails instead.
SONG_SPEED_ANCHORS = {12: 0x19, 15: 0xd2}
# The one SFX whose pitch comes out of the PRNG (descriptor +7 non-zero; recon section 7 names 12,
# 20 and 21). The determinism check re-captures it, because a leak into the PRNG is invisible in
# every other asset.
PRNG_SFX_ID = 12

MODULE_GLOBALS_BYTES = 28                                     # $17c56..$17c71
SFX_CHANNELS = 3
SFX_CHANNEL_STATE_BYTES = 26
PRNG_STATE_BYTES = 4                                          # $1aae6..$1aae9 (recon section 6)

# The mutable state whose repetition proves the output loops forever: every MUTABLE region of recon
# section 6 except the PRNG at snd_prng_state, which is handled per asset family below.
MODULE_STATE_REGIONS = (
    (SND_MUSIC_CHANNEL_STATE, SND_ENGINE_ENABLED + MODULE_GLOBALS_BYTES),
    (SND_PSG_SHADOW, SND_NOTE_PERIOD_TABLE),
    (SND_SFX_CHANNEL_STATE, SND_SFX_CHANNEL_STATE + SFX_CHANNELS * SFX_CHANNEL_STATE_BYTES),
)
# The PRNG is stepped unconditionally on EVERY tick, so whether it belongs in the hash is decided by
# whether the asset can consume it, and the two families answer differently:
#   * a SONG cannot. Opcode $97, the only music-to-SFX trigger, occurs zero times in the whole data
#     set (recon section 8), so the PRNG is pure noise here and including it would make every frame
#     unique and find no loop at all.
#   * an SFX can (12, 20, 21 read it), so leaving it out could declare a loop between two frames
#     that will diverge on the next draw — a false loop, and a truncated file.
# It goes LAST so that a state index computed over MODULE_STATE_REGIONS is valid for both.
SONG_STATE_REGIONS = MODULE_STATE_REGIONS
SFX_STATE_REGIONS = MODULE_STATE_REGIONS + ((SND_PRNG_STATE, SND_PRNG_STATE + PRNG_STATE_BYTES),)


def _state_index(addr, regions):
    """Where ``addr`` lands in the concatenation ``_module_state`` builds out of ``regions``."""
    index = 0
    for start, end in regions:
        if start <= addr < end:
            return index + addr - start
        index += end - start
    raise SystemExit("%#x is not inside the regions the loop detector hashes, so the musical hash "
                     "cannot exclude it — the module state map is wrong" % addr)


# The one byte the MUSICAL hash drops on top of the exact one. It is a pure counter: the speed byte
# is added to it every tick and the channels step a row on its carry. Dropping it asks "are we
# playing the same thing again?" rather than "is the machine in the same state?" — see the manifest
# header for what that costs.
SPEED_ACCUMULATOR_STATE_INDEX = _state_index(SND_SONG_SPEED_ACCUMULATOR, MODULE_STATE_REGIONS)

ACCUMULATOR_MODULUS = 256                                     # it is one byte, and it wraps
# WHEN THE MUSICAL RULE IS ARMED AT ALL. The exact state cannot repeat until the music and the
# accumulator repeat together, so waiting for it costs up to the accumulator's own period times the
# musical one — 256/gcd(speed, 256) ticks. That is cheap while the period is small: the four songs
# that do reach an exact loop have 4 ($40) and 16 ($30), and reach it in 2049..7201 frames. It is
# hopeless at 256, which is what every ODD speed byte gives ($27/$31/$19, the other nine songs):
# 15000 frames were not enough for a single one of them. So the fallback is armed only past this
# threshold, and an exact loop is never traded away for a weaker musical one.
MAX_AFFORDABLE_ACCUMULATOR_PERIOD = 16

TICK_DROP_50HZ_COLOUR = 0                                     # what the audio-capture mode selects
SONG_FRAME_CAP = 15000                                        # 5 minutes at 50 Hz
SFX_FRAME_CAP = 1500                                          # 30 s; the longest real SFX is 91
# A tick is a whole replay engine, but a small one: the busiest run of any asset here is 679
# instructions. This is the oracle's own default, kept explicit as the headroom it is.
MAX_INSNS_PER_RUN = 200_000

# ---- the YM2149 as the dumps and the renderer see it -------------------------------------------

YM_REGISTERS = 16                                             # a YM6 frame carries all of them
YM_REGISTERS_WRITTEN = 11                                     # ...but this driver writes 0..10 only
TONE_FINE_REGS = (0, 2, 4)                                    # per channel: period low byte...
TONE_COARSE_REGS = (1, 3, 5)                                  # ...and high nibble
NOISE_PERIOD_REG = 6
MIXER_REG = 7
VOLUME_REGS = (8, 9, 10)
ENVELOPE_SHAPE_REG = 13
TONE_PERIOD_COARSE_MASK = 0x0f
NOISE_PERIOD_MASK = 0x1f
MIXER_MASK = 0x3f                                             # 3 tone gates + 3 noise gates
VOLUME_REG_MASK = 0x1f                                        # 4-bit level + the envelope-mode bit
VOLUME_LEVEL_MASK = 0x0f
VOLUME_LEVEL_MAX = 0x0f
VOLUME_LEVEL_SILENT = 0
NOISE_MIXER_SHIFT = 3                                         # mixer bits 0..2 tone, 3..5 noise
CHANNELS = 3

# Which bits of each register the CHIP actually decodes. This matters for the .ym and not for the
# render: YM5/YM6 reuse the dead bits of registers 1, 3, 6, 7, 14 and 15 as SPECIAL-EFFECT CODES
# (SID voice, sinus-SID, digidrum channel and timer), so a player handed a raw shadow byte with
# rubbish above the field — this driver leaves plenty, e.g. $fb in register 1 — starts an effect on
# whatever voice those bits happen to name. Registers 11..15 are never written here (see
# `_vetted_psg_writes`) and pass through whole.
YM_REGISTER_MASKS = bytes((
    0xff, TONE_PERIOD_COARSE_MASK,                            # 0/1: channel A tone period
    0xff, TONE_PERIOD_COARSE_MASK,                            # 2/3: channel B
    0xff, TONE_PERIOD_COARSE_MASK,                            # 4/5: channel C
    NOISE_PERIOD_MASK,                                        # 6:   noise period
    MIXER_MASK,                                               # 7:   mixer
    VOLUME_REG_MASK, VOLUME_REG_MASK, VOLUME_REG_MASK,        # 8-10: channel volumes
    0xff, 0xff, 0xff, 0xff, 0xff,                             # 11-15: untouched by this driver
))

YM_CLOCK = 2_000_000                                          # the ST's YM2149 master clock
YM_PERIOD_DIVISOR = 16                                        # f = clock / (16 * period)
FRAME_RATE = 50                                               # the 50 Hz tick the capture forces
SAMPLE_RATE = 44100
SAMPLES_PER_FRAME = SAMPLE_RATE // FRAME_RATE                 # 882
SAMPLE_BYTES = 2                                              # 16-bit PCM
INT16_PEAK = 32767
OVERSAMPLE = 4                                                # render at 4x, box-decimate back down
SQUARE_DUTY = 0.5
# The chip's 4-bit DAC is logarithmic, ~3 dB of amplitude per step: level 15 is unity and each step
# down halves the power. The envelope generator's finer 5-bit ladder is not modelled — see below.
VOLUME_DB_HALVING = 2.0
# 17-bit LFSR, taps at bits 0 and 3 (x^17 + x^14 + 1) — the AY-3-8910/YM2149 noise polynomial.
NOISE_LFSR_BITS = 17
NOISE_LFSR_TAP = 3
NOISE_SEQUENCE_LENGTH = (1 << NOISE_LFSR_BITS) - 1
WAV_RMS_FLOOR = 0.01                                          # below this a render is silent, i.e. wrong

# The oracle's shim models the chip's register file for the read-modify-write on register 7, and the
# .ym frames are snapshots of the SAME file. Two different numbers here would mean the shim and this
# tool disagree about what a YM2149 is, and the frames would be silently short or padded.
if emu.PSG_NREGS != YM_REGISTERS:
    raise SystemExit("the oracle models %d YM2149 registers, not the %d a YM6 frame carries, so "
                     "every frame written here would be short or padded. emu.PSG_NREGS is read from "
                     "liboracle.so itself, so this is a real disagreement about what a YM2149 is, "
                     "not a stale build." % (emu.PSG_NREGS, YM_REGISTERS))

# ---- YM6 container ------------------------------------------------------------------------------
# "YM6!" + "LeOnArD!", a fixed header, three NUL-terminated strings, the frames INTERLEAVED
# (register-major: all frames of register 0, then all of register 1, ...) and an "End!" marker.
# Written uncompressed; the usual LHA wrapper is a transport, not part of the format.
YM6_MAGIC = b"YM6!"
YM6_CHECK = b"LeOnArD!"
YM6_ATTRIBUTE_INTERLEAVED = 1 << 0
YM6_DIGIDRUMS = 0
YM6_EXTRA_BYTES = 0
YM6_END = b"End!"
YM6_AUTHOR = b"Activision / Images Software (custom in-house driver; no credit in the binary)"
# The three strings are 8-BIT text: a YM player renders them in the machine's own character set
# (Atari ST, DOS CP437, ...), where no byte means "em dash". They are therefore ASCII, and the
# encode says so rather than trusting whoever edits the format strings below.
YM6_TEXT_ENCODING = "ascii"
# Register 13 is WRITE-TRIGGERED on the real chip — writing it restarts the envelope — so the YM
# formats spell "not written this frame" as $ff rather than as a repeat of the last value.
ENVELOPE_SHAPE_UNTOUCHED = 0xff

# ---- how a capture ended ------------------------------------------------------------------------

END_SELF = "self-ended"                                       # opcode $8e, or an SFX's flag cleared
END_LOOP = "exact loop"                                       # the module's whole state repeated
END_MUSICAL_LOOP = "musical loop"                             # ...all of it bar the speed accumulator
END_CAPPED = "capped"                                         # none of those inside the cap
END_REASONS = (END_SELF, END_LOOP, END_MUSICAL_LOOP, END_CAPPED)
LOOPED_ENDS = (END_LOOP, END_MUSICAL_LOOP)                    # the two that give the .ym a loop frame

Capture = namedtuple("Capture", "frames end loop_start loop_period psg_regs")


def _vetted_psg_writes():
    """The last run's ``(reg, value)`` writes, with the two assumptions this tool rests on checked.

    Both are recon claims that the renderer would otherwise silently mis-serve: that the driver
    never touches registers 11-15 (so there is no envelope to generate and no I/O port to model),
    and that a volume byte never carries bit 4 (which would route the channel through that same
    absent envelope). Neither can be discovered by listening to the result.
    """
    writes = emu.psg_writes()
    for reg, value in writes:
        if reg >= YM_REGISTERS_WRITTEN:
            raise SystemExit("the replayer wrote PSG register %d (= %#x), but ../notes/"
                             "sound_module_recon.md section 5 says it writes 0..%d only — the "
                             "envelope generator this tool does not implement is in use"
                             % (reg, value, YM_REGISTERS_WRITTEN - 1))
        if reg in VOLUME_REGS and value > VOLUME_LEVEL_MAX:
            raise SystemExit("volume register %d was written %#x: bit 4 routes the channel through "
                             "the envelope generator, which this tool does not implement" % (reg, value))
    return writes


def _run(image, entry, regs=None):
    """One oracle run. Returns (final image, this run's PSG writes).

    ``emu.run`` raises on anything it cannot model, and that is left to propagate: mid-capture it
    means the replayer reached a hardware access the recon did not find, which is a finding.
    """
    image, _, _ = emu.run(image, entry, regs, max_insns=MAX_INSNS_PER_RUN)
    return image, _vetted_psg_writes()


def _module_state(image, regions):
    """The module's mutable state, as the bytes whose repetition means the output has looped."""
    return b"".join(bytes(image[start:end]) for start, end in regions)


def _musical_state(state):
    """``state`` without the song-speed accumulator: what the music is playing, not where the
    fractional row clock happens to stand. See SPEED_ACCUMULATOR_STATE_INDEX."""
    return state[:SPEED_ACCUMULATOR_STATE_INDEX] + state[SPEED_ACCUMULATOR_STATE_INDEX + 1:]


def _accumulator_period(speed):
    """How many ticks the song-speed accumulator takes to come back to the same byte."""
    return ACCUMULATOR_MODULUS // math.gcd(speed, ACCUMULATOR_MODULUS)


def _row_tick_count(speed):
    """How many ticks a row lasts at ``speed`` — the accumulator's first carry, rounded up.

    This is the SHORTEST candidate a musical loop may have, and the bar exists because the byte the
    musical hash ignores IS the row clock: over a period too short for the accumulator to carry once,
    no row has stepped and the "repeat" is one held note recurring. Song 12 is that case in the
    flesh — 10-frame rows over a 5-frame vibrato figure, so its state repeats inside every long note
    and the first candidate the hash offers is a single chord of a three-chord jingle. With the bar
    in place its loop comes out at 1310 frames / 127 rows, and no other song moves at all.
    """
    return -(-ACCUMULATOR_MODULUS // speed)


def _loop_replay_agreement(frames, start, period):
    """What fraction of the second musical period replays the first, frame for frame.

    A musical loop is a state repeat MODULO the row clock, so its join is not sample-exact and this
    is the number that says how close it is rather than a promise that it is close. One frame of
    slack is allowed per frame: over a period the accumulator drifts by less than a whole speed
    byte, which moves a row boundary — and with it the tick phase of that row's vibrato and volume
    envelope — by at most one tick either way.
    """
    matched = sum(1 for offset in range(period)
                  if any(frames[start + period + offset] == frames[near]
                         for near in range(max(start, start + offset - 1),
                                           min(start + period, start + offset + 2))))
    return matched / period


def _fold(shadow, writes):
    """Apply one run's writes to the running register shadow. Returns the registers it touched."""
    touched = set()
    for reg, value in writes:
        shadow[reg] = value
        touched.add(reg)
    return touched


def _ym_frame(shadow, written_this_frame):
    """One frame's register file: masked to the bits the chip decodes (YM_REGISTER_MASKS), with
    register 13's "not written" convention honoured."""
    frame = bytearray(byte & mask for byte, mask in zip(shadow, YM_REGISTER_MASKS))
    if ENVELOPE_SHAPE_REG not in written_this_frame:
        frame[ENVELOPE_SHAPE_REG] = ENVELOPE_SHAPE_UNTOUCHED
    return bytes(frame)


def capture(setup, finished, frame_cap, state_regions, min_musical_period):
    """Drive the replayer from a fresh image and return its per-frame register files.

    ``setup`` is the (entry, registers) calls that start the asset — their PSG writes precede frame
    1 and so seed the shadow rather than producing a frame of their own. ``finished`` is asked after
    every tick whether the asset ended by itself. ``state_regions`` is what the loop detector hashes.

    Two loop rules. Once the whole hashed state repeats, every later frame is a replay of an earlier
    one and the capture stops on the spot. A non-zero ``min_musical_period`` arms the weaker rule for
    the songs whose accumulator puts the exact one out of reach (MAX_AFFORDABLE_ACCUMULATOR_PERIOD
    is what decides that, so the two rules never compete for the same song): a repeat of the MUSICAL
    state at least that many frames apart is taken as the loop, and the capture then runs on to the
    end of a SECOND musical period, so the file holds the lead-in plus the loop played through twice.
    The minimum is a row's worth of ticks — see `_row_tick_count` for what it keeps out.
    """
    image = harness.make_image()
    emu.audio_reset()                     # a new capture: forget the previous asset's register file
    shadow = bytearray(YM_REGISTERS)
    for entry, regs in setup:
        image, writes = _run(image, entry, regs)
        _fold(shadow, writes)

    frames, state_seen, musical_seen, psg_regs = [], {}, {}, set()
    end, loop_start, loop_period, musical_end_frame = END_CAPPED, None, None, None
    while len(frames) < frame_cap:
        image, writes = _run(image, SND_STUB + STUB_TICK)
        touched = _fold(shadow, writes)
        psg_regs |= touched
        frames.append(_ym_frame(shadow, touched))
        if len(frames) == 1 and image[SND_TICK_DROP_VALUE] != TICK_DROP_50HZ_COLOUR:
            raise SystemExit("after one tick snd_tick_drop_value is %#x, not %#x: the oracle's "
                             "audio-capture mode is not serving the 50 Hz colour profile, so this "
                             "capture would be %d/256 of ticks short"
                             % (image[SND_TICK_DROP_VALUE], TICK_DROP_50HZ_COLOUR,
                                image[SND_TICK_DROP_VALUE]))
        if finished(image):
            end = END_SELF
            break
        state = _module_state(image, state_regions)
        if state in state_seen:
            end, loop_start = END_LOOP, state_seen[state]
            loop_period = len(frames) - loop_start
            break
        state_seen[state] = len(frames)
        if not min_musical_period:
            continue
        first_seen = musical_seen.setdefault(_musical_state(state), len(frames))
        if musical_end_frame is None and len(frames) - first_seen >= min_musical_period:
            loop_start, loop_period = first_seen, len(frames) - first_seen
            musical_end_frame = loop_start + 2 * loop_period
        if musical_end_frame is not None and len(frames) >= musical_end_frame:
            end = END_MUSICAL_LOOP
            break
    return Capture(frames, end, loop_start, loop_period, psg_regs)


def capture_song(song_id, speed):
    """Play song ``song_id`` and tick it until it ends, loops, or hits the cap.

    ``speed`` is the song's own directory byte, and all it decides here is whether the musical loop
    rule is armed — the driver reads the speed out of the image itself.
    """
    setup = [(SND_STUB + STUB_PLAY_SONG, {"d0": song_id})]
    exact_loop_affordable = _accumulator_period(speed) <= MAX_AFFORDABLE_ACCUMULATOR_PERIOD
    return capture(setup, lambda image: image[SND_ENGINE_ENABLED] == 0, SONG_FRAME_CAP,
                   SONG_STATE_REGIONS,
                   min_musical_period=0 if exact_loop_affordable else _row_tick_count(speed))


def capture_sfx(sfx_id):
    """Trigger SFX ``sfx_id`` on channel A and tick it until its active flag clears.

    The stop first is what gives the effect a defined background: the shipped image's PSG shadow is
    residue, and nothing else would clear the volumes and force the mixer off underneath it.
    """
    setup = [(SND_STUB + STUB_STOP, None),
             (SND_STUB + STUB_TRIGGER_SFX, {"d0": sfx_id, "d1": SFX_CHANNEL_A})]
    return capture(setup, lambda image: struct.unpack_from(">I", image, SND_SFX_ACTIVE_FLAGS)[0] == 0,
                   SFX_FRAME_CAP, SFX_STATE_REGIONS, min_musical_period=0)


# ---- YM6 output ---------------------------------------------------------------------------------


def write_ym6(path, frames, loop_frame, title, comment):
    """Write ``frames`` (each ``YM_REGISTERS`` bytes) as an uncompressed interleaved YM6 file."""
    header = (YM6_MAGIC + YM6_CHECK
              + struct.pack(">IIHIHIH", len(frames), YM6_ATTRIBUTE_INTERLEAVED, YM6_DIGIDRUMS,
                            YM_CLOCK, FRAME_RATE, loop_frame, YM6_EXTRA_BYTES)
              + title.encode(YM6_TEXT_ENCODING) + b"\0" + YM6_AUTHOR + b"\0"
              + comment.encode(YM6_TEXT_ENCODING) + b"\0")
    interleaved = bytes(frame[reg] for reg in range(YM_REGISTERS) for frame in frames)
    with open(path, "wb") as handle:
        handle.write(header + interleaved + YM6_END)


# ---- YM2149 renderer ----------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _noise_sequence():
    """The LFSR's output bit for each of its 131071 states, so a frame can index into it.

    The register is autonomous — the noise period sets only how fast it is clocked — so the whole
    sequence can be built once and sampled at whatever rate a frame asks for.
    """
    bits = np.empty(NOISE_SEQUENCE_LENGTH, dtype=np.float64)
    lfsr = 1
    for i in range(NOISE_SEQUENCE_LENGTH):
        bits[i] = lfsr & 1
        feedback = (lfsr ^ (lfsr >> NOISE_LFSR_TAP)) & 1
        lfsr = (lfsr >> 1) | (feedback << (NOISE_LFSR_BITS - 1))
    return bits


def _frequency(period):
    """A period register to its output frequency. Period 0 behaves as 1 — the counter reloads."""
    return YM_CLOCK / (YM_PERIOD_DIVISOR * max(period, 1))


def _amplitude(level):
    """The 4-bit logarithmic DAC: unity at level 15, halving in power every step down.

    Level 0 is the exception, and it is a hardware fact rather than a rounding: the bottom rung of
    the ladder is the DAC switched OFF, not one more 3 dB step. Extrapolating the geometric law
    would put it at 2**-7.5, an audible -45 dB hiss under every rest — and 12.5% of this game's
    channel-frames sit at level 0.
    """
    if level == VOLUME_LEVEL_SILENT:
        return 0.0
    return 2.0 ** ((level - VOLUME_LEVEL_MAX) / VOLUME_DB_HALVING)


def render(frames):
    """``frames`` to one float track in [-1, 1], stepping the register state once per 50 Hz frame."""
    noise_bits = _noise_sequence()
    oversampled = SAMPLES_PER_FRAME * OVERSAMPLE
    elapsed = np.arange(1, oversampled + 1) / (SAMPLE_RATE * OVERSAMPLE)   # seconds within a frame
    track = np.empty(len(frames) * SAMPLES_PER_FRAME, dtype=np.float64)
    tone_phase = [0.0] * CHANNELS
    noise_phase = 0.0

    for index, frame in enumerate(frames):
        mixer = frame[MIXER_REG]
        noise_walk = noise_phase + _frequency(frame[NOISE_PERIOD_REG] & NOISE_PERIOD_MASK) * elapsed
        noise = noise_bits[noise_walk.astype(np.int64) % NOISE_SEQUENCE_LENGTH]
        noise_phase = noise_walk[-1] % NOISE_SEQUENCE_LENGTH

        mix = np.zeros(oversampled)
        for channel in range(CHANNELS):
            period = (frame[TONE_FINE_REGS[channel]]
                      | (frame[TONE_COARSE_REGS[channel]] & TONE_PERIOD_COARSE_MASK) << 8)
            walk = tone_phase[channel] + _frequency(period) * elapsed
            tone_phase[channel] = walk[-1] % 1.0
            # Mixer bits are active LOW, and a channel with BOTH gates off holds the DAC high — the
            # constant level a digidrum would drive, and the reason `gate` starts at 1.
            gate = np.ones(oversampled)
            if not (mixer >> channel) & 1:
                gate = gate * ((walk % 1.0) < SQUARE_DUTY)
            if not (mixer >> (channel + NOISE_MIXER_SHIFT)) & 1:
                gate = gate * noise
            mix += _amplitude(frame[VOLUME_REGS[channel]] & VOLUME_LEVEL_MASK) * gate

        at = index * SAMPLES_PER_FRAME
        track[at:at + SAMPLES_PER_FRAME] = mix.reshape(-1, OVERSAMPLE).mean(axis=1) / CHANNELS

    return track - track.mean()          # the gates are unipolar, so the mix carries a DC offset


def write_wav(path, track):
    """Write a float track as 44100 Hz 16-bit mono. Returns its RMS, in the track's own units."""
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(SAMPLE_BYTES)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(np.clip(track * INT16_PEAK, -INT16_PEAK, INT16_PEAK)
                           .astype("<i2").tobytes())
    return float(np.sqrt(np.mean(track * track)))


# ---- assembling the outputs ---------------------------------------------------------------------

# One description per asset family, so the capture loop below is written once. ``title`` and
# ``detail`` are the two YM6 strings' variable halves; ``speed`` is the manifest column an SFX does
# not have.
AssetKind = namedtuple("AssetKind", "kind directory count capture title detail speed")

TITLE_PREFIX = "Wonder Boy in Monsterland (ST) - "
COMMENT_PREFIX = "captured from AUTO/SWB.PRG by tools/extract_audio.py; "


def asset_kinds(speeds):
    """The two families, bound to the song speeds read out of this run's image."""
    return (
        AssetKind(kind="song", directory="songs", count=SONG_COUNT,
                  capture=lambda song_id: capture_song(song_id, speeds[song_id]),
                  title=lambda song_id: "song %d" % song_id,
                  detail=lambda song_id: "speed $%02x" % speeds[song_id],
                  speed=lambda song_id: speeds[song_id]),
        AssetKind(kind="sfx", directory="sfx", count=SFX_COUNT, capture=capture_sfx,
                  title=lambda sfx_id: "SFX %d" % sfx_id,
                  detail=lambda _sfx_id: "channel A",
                  speed=lambda _sfx_id: None),
    )


def song_speed(image, song_id):
    """Byte +1 of a song's 8-byte directory record: its fractional row rate (recon section 6)."""
    return image[SND_SONG_DIRECTORY + song_id * SONG_RECORD_BYTES + SONG_SPEED_OFFSET]


def check_song_speeds(speeds):
    wrong = ["song %d is %#x, not %#x" % (song_id, speeds[song_id], expected)
             for song_id, expected in SONG_SPEED_ANCHORS.items() if speeds[song_id] != expected]
    if wrong:
        raise SystemExit("the song directory at %#x does not hold the speeds ../notes/"
                         "sound_module_recon.md read out of it (%s) — the address is wrong"
                         % (SND_SONG_DIRECTORY, "; ".join(wrong)))


def end_description(capture_result):
    """How a capture ended, and for a loop what was proved. A musical loop carries the MEASURED
    agreement between its two periods, because unlike an exact one it is not sample-exact."""
    if capture_result.end == END_MUSICAL_LOOP:
        return "%s (period %d frames, from frame %d, %.0f%% of the next period identical)" % (
            capture_result.end, capture_result.loop_period, capture_result.loop_start,
            100 * loop_replay_agreement(capture_result))
    if capture_result.end == END_LOOP:
        return "%s (period %d frames, from frame %d)" % (capture_result.end,
                                                         capture_result.loop_period,
                                                         capture_result.loop_start)
    return capture_result.end


def loop_replay_agreement(capture_result):
    """``_loop_replay_agreement`` for a musical-loop capture, whose frames hold both periods."""
    return _loop_replay_agreement(capture_result.frames, capture_result.loop_start,
                                  capture_result.loop_period)


def loop_frame(capture_result):
    """The YM6 loop point: the start of whichever loop was proved, and 0 for a capture that proved
    none. YM6 has no "does not loop" flag, so 0 — replay from the top — is the honest fallback for a
    self-ended asset, and for a capped one the manifest and the file's own comment say `capped`."""
    return capture_result.loop_start if capture_result.end in LOOPED_ENDS else 0


def register_list(psg_regs):
    """The registers an asset touched, as a range when they are contiguous (they always are here)."""
    ordered = sorted(psg_regs)
    if ordered == list(range(ordered[0], ordered[-1] + 1)):
        return "%d-%d" % (ordered[0], ordered[-1])
    return ",".join(str(reg) for reg in ordered)


def write_asset(out_dir, kind, asset_id, capture_result, title, detail):
    """One asset's .ym and .wav. Returns the .wav's RMS, the render's one measure of "not silent"."""
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, "%s_%02d" % (kind, asset_id))
    comment = COMMENT_PREFIX + detail + "; capture ended: " + end_description(capture_result)
    write_ym6(stem + ".ym", capture_result.frames, loop_frame(capture_result), title, comment)
    rms = write_wav(stem + ".wav", render(capture_result.frames))
    if rms < WAV_RMS_FLOOR:
        raise SystemExit("%s_%02d.wav has an RMS of %.5f, below the %.5f floor: %d frames of "
                         "register traffic rendered to silence"
                         % (kind, asset_id, rms, WAV_RMS_FLOOR, len(capture_result.frames)))
    return rms


def manifest_line(kind, asset_id, capture_result, speed):
    seconds = len(capture_result.frames) / FRAME_RATE
    return "%-4s %2d  %6d frames  %8.2f s  regs %-5s  speed %-4s  %s" % (
        kind, asset_id, len(capture_result.frames), seconds, register_list(capture_result.psg_regs),
        "$%02x" % speed if speed is not None else "-", end_description(capture_result))


MANIFEST_HEADER = """\
# Wonder Boy in Monsterland (ST) — audio assets, captured from AUTO/SWB.PRG by extract_audio.py.
#
# Each line: kind, id, frames captured at 50 Hz, seconds, the PSG registers the capture saw written,
# the song's speed byte from snd_song_directory (byte +1 of its 8-byte record; SFX have none), and
# how the capture ended:
#
#   self-ended     the song ran opcode $8e, or the SFX cleared its active flag.
#   exact loop     the module's whole mutable state repeated, so the output repeats forever from
#                  that frame. The .ym's loop frame is that frame, and it is exact.
#   musical loop   the state repeated in everything BUT the song-speed accumulator ($17c6a), the
#                  fractional row clock. Nine songs have an odd speed byte, which gives that one
#                  counter a period of 256 ticks and puts an exact repeat out of reach; capture runs
#                  on to the end of a second musical period, so the loop below is in the file twice.
#                  The .ym's loop frame is that loop's start, and because the accumulator is exactly
#                  what was ignored to find it, the row phase at the join — and with it the tick
#                  phase of that row's vibrato and volume envelope — can be off by ONE frame
#                  (1/50 s). The percentage on the line is measured, not promised: it is how much of
#                  the second period replays the first frame for frame, allowing that one frame of
#                  slip. It is NOT 100%%: the accumulator is also the phase of every per-tick effect,
#                  so a row boundary that lands a tick early leaves that row's arpeggio and volume
#                  ramp a tick out of step for as long as they run. Songs 11 and 14 replay their
#                  first period exactly for its first few hundred frames and then hold the right
#                  notes with the wrong effect phase, which is why they score lowest.
#   capped         none of the above happened within %d frames for a song, %d for an SFX. The .ym
#                  loops to frame 0, which is a guess: this line is what says so.
#
# A .ym holds these frames verbatim; a self-ended asset's .ym also loops to frame 0, because YM6
# cannot say "no loop". Every .ym repeats its end reason in its comment field.
#
# SFX 12, 20 and 21 take their pitch jitter from the module's PRNG (snd_prng_state), which nothing
# ever resets — in the game they depend on how long the machine has been running. They are
# reproducible here only because every capture starts from a freshly loaded image, i.e. from the
# PRNG seed the binary ships. The SFX loop detector hashes that PRNG for the same reason; the song
# one cannot (no song reads it), which is what the two loop rules above are about.
"""


def check_songs_are_playable(captures):
    """Every song must have written a tone period and a volume — the shape of an actually-audible
    capture, as opposed to one that ticked an engine that never started."""
    audible = {TONE_FINE_REGS[0], TONE_COARSE_REGS[0], VOLUME_REGS[0]}
    silent = [song_id for song_id, result in captures.items() if not audible <= result.psg_regs]
    if silent:
        raise SystemExit("song(s) %s never wrote registers %s: the engine was ticked but never "
                         "played" % (silent, sorted(audible)))


def check_capture_is_reproducible(what, recapture, reference):
    """Re-capture one asset after every other one and require the identical frame stream.

    The point is not that the emulator is deterministic — it is that nothing LEAKED between assets.
    Every capture reloads the image, but the oracle's modeled register file and select latch are
    process-global and span runs by design, so a missing `audio_reset` would show up here and
    nowhere else. Song 0 covers the music path; PRNG_SFX_ID covers the one piece of module state a
    fresh image is the ONLY thing that restores — the PRNG its pitch comes out of.
    """
    again = recapture()
    if again.frames != reference.frames or again.end != reference.end:
        raise SystemExit("%s captured differently the second time (%d frames %s vs %d frames %s): "
                         "state leaked between captures"
                         % (what, len(again.frames), again.end, len(reference.frames), reference.end))


# ---- the render's spectral self-check ------------------------------------------------------------
# The RMS floor only says a .wav is not silent. This says the pitches in it are the pitches the
# CAPTURE asked for: a wrong master clock, a wrong period divisor, a swapped fine/coarse byte or a
# mis-decimated oversample all move the peaks and none of them move the RMS.

SPECTRUM_SONG = 0
SPECTRUM_RENDER_FRAMES = 150                # 3 s, so the window below is not the render's first
SPECTRUM_WINDOW_FRAMES = 16                 # 0.32 s -> 3.125 Hz bins, finer than the tolerance
SPECTRUM_PEAKS = 5                          # how many of the strongest peaks must be explained
SPECTRUM_MIN_HZ = 40.0                      # below the lowest fundamental: window leakage lives here
SPECTRUM_MAX_HARMONIC = 8                   # a square wave puts real energy this far up
# Two FFT bins wide. The tones are not steady — the driver slides the period by a unit or two every
# frame (its vibrato), which spreads each peak over a few bins — so the tolerance has to cover that
# without covering the next semitone, let alone the octave a divisor error would land on.
SPECTRUM_TOLERANCE_HZ = 8.0


def _audible_tone_frequencies(frames):
    """Every tone frequency ``frames`` could actually have sounded: a channel's period, for the
    frames where its tone gate is open and its volume is not zero."""
    frequencies = set()
    for frame in frames:
        for channel in range(CHANNELS):
            if (frame[MIXER_REG] >> channel) & 1:                       # gate is active LOW
                continue
            if (frame[VOLUME_REGS[channel]] & VOLUME_LEVEL_MASK) == VOLUME_LEVEL_SILENT:
                continue
            period = (frame[TONE_FINE_REGS[channel]]
                      | (frame[TONE_COARSE_REGS[channel]] & TONE_PERIOD_COARSE_MASK) << 8)
            frequencies.add(_frequency(period))
    return sorted(frequencies)


def _strongest_peaks(window, count):
    """The ``count`` strongest local maxima of ``window``'s spectrum, as (frequency, magnitude).

    Hann-windowed, because a rectangular window's sidelobes on a square wave are themselves peaks.
    Everything below SPECTRUM_MIN_HZ is dropped: what sits there is the leakage skirt of the DC the
    unipolar gates leave behind, not a tone.
    """
    spectrum = np.abs(np.fft.rfft(window * np.hanning(len(window))))
    frequencies = np.fft.rfftfreq(len(window), 1.0 / SAMPLE_RATE)
    peaks = [i for i in range(1, len(spectrum) - 1)
             if frequencies[i] >= SPECTRUM_MIN_HZ
             and spectrum[i] > spectrum[i - 1] and spectrum[i] >= spectrum[i + 1]]
    peaks.sort(key=lambda i: -spectrum[i])
    return [(float(frequencies[i]), float(spectrum[i])) for i in peaks[:count]]


def _closest_partial(frequency, fundamentals):
    """The (error, harmonic, fundamental) of whichever partial of ``fundamentals`` is nearest."""
    return min(((abs(frequency - harmonic * fundamental), harmonic, fundamental)
                for fundamental in fundamentals
                for harmonic in range(1, SPECTRUM_MAX_HARMONIC + 1)),
               key=lambda candidate: candidate[0])


def check_render_spectrum(capture_result):
    """Require the render's strongest spectral peaks to be partials of the periods it was given.

    The window is taken from the MIDDLE of a longer render rather than from its start, so what is
    measured has had the renderer's cross-frame tone phase carried into it — a renderer that reset
    each frame's phase would still pass an FFT of its own first frames.

    WHAT IT CATCHES, measured by mutating `render` and re-running: dropping the coarse period byte,
    shifting it 4 instead of 8, doubling the square's period, inverting the tone gate, and resetting
    the tone phase each frame — five of six. WHAT IT CANNOT: a wrong YM_CLOCK or YM_PERIOD_DIVISOR,
    because the expected frequencies come through the same `_frequency` and both sides move together.
    Those two are datasheet constants of the machine rather than choices made here, and nothing in an
    audio dump can pin them; the sixth, box-decimation replaced by picking every fourth sample, is
    aliasing that leaves the fundamentals where they were and needs an ear or a noise-floor measure.
    """
    frames = capture_result.frames[:SPECTRUM_RENDER_FRAMES]
    if len(frames) < SPECTRUM_RENDER_FRAMES:
        raise SystemExit("song %d is only %d frames, too short for the %d-frame spectral check"
                         % (SPECTRUM_SONG, len(frames), SPECTRUM_RENDER_FRAMES))
    at = (SPECTRUM_RENDER_FRAMES - SPECTRUM_WINDOW_FRAMES) // 2
    track = render(frames)
    window = track[at * SAMPLES_PER_FRAME:(at + SPECTRUM_WINDOW_FRAMES) * SAMPLES_PER_FRAME]

    fundamentals = _audible_tone_frequencies(frames[at:at + SPECTRUM_WINDOW_FRAMES])
    peaks = _strongest_peaks(window, SPECTRUM_PEAKS)
    if len(peaks) < SPECTRUM_PEAKS or not fundamentals:
        raise SystemExit("song %d's spectral window has %d peak(s) above %.0f Hz and %d audible "
                         "tone period(s): there is nothing here to check the render against"
                         % (SPECTRUM_SONG, len(peaks), SPECTRUM_MIN_HZ, len(fundamentals)))

    unexplained = []
    for frequency, _magnitude in peaks:
        deviation_hz, harmonic, fundamental = _closest_partial(frequency, fundamentals)
        if deviation_hz > SPECTRUM_TOLERANCE_HZ:
            unexplained.append("%.1f Hz (nearest is harmonic %d of %.1f Hz, %.1f Hz away)"
                               % (frequency, harmonic, fundamental, deviation_hz))
    if unexplained:
        raise SystemExit("song %d renders energy its own register stream does not account for: %s. "
                         "The %d tone period(s) the capture wrote over frames %d-%d give %s. A peak "
                         "off by an octave or a factor of 16 is the master clock or the period "
                         "divisor; one off by a few percent is the oversampling."
                         % (SPECTRUM_SONG, "; ".join(unexplained), len(fundamentals), at,
                            at + SPECTRUM_WINDOW_FRAMES - 1,
                            ", ".join("%.1f" % f for f in fundamentals)))
    return peaks


def end_tally(kind, captures, frame_cap):
    """How each family's captures ended, COUNTED. The summary used to assert what the run was
    expected to do; this reports what it did, so a song that stops ending itself is visible."""
    counted = Counter(result.end for result in captures.values())
    unknown = set(counted) - set(END_REASONS)
    if unknown:
        raise SystemExit("capture(s) ended for reason(s) %s, which END_REASONS does not list" % unknown)
    return "%-6s %d captured — %s (cap %d frames)" % (
        kind + ":", len(captures),
        ", ".join("%d %s" % (counted[end], end) for end in END_REASONS if counted[end]), frame_cap)


def main(argv):
    out_dir = argv[1] if len(argv) > 1 else DEFAULT_OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    image = harness.make_image()
    speeds = [song_speed(image, song_id) for song_id in range(SONG_COUNT)]
    check_song_speeds(speeds)

    lines, levels, captures = [], [], {}
    kinds = asset_kinds(speeds)
    with emu.audio_capturing():
        for kind in kinds:
            captures[kind.kind] = {}
            for asset_id in range(kind.count):
                result = kind.capture(asset_id)
                captures[kind.kind][asset_id] = result
                levels.append(write_asset(os.path.join(out_dir, kind.directory), kind.kind,
                                          asset_id, result, TITLE_PREFIX + kind.title(asset_id),
                                          kind.detail(asset_id)))
                lines.append(manifest_line(kind.kind, asset_id, result, kind.speed(asset_id)))
        songs, sfx = captures["song"], captures["sfx"]
        check_songs_are_playable(songs)
        peaks = check_render_spectrum(songs[SPECTRUM_SONG])
        check_capture_is_reproducible("song 0", lambda: capture_song(0, speeds[0]), songs[0])
        check_capture_is_reproducible("sfx %d" % PRNG_SFX_ID,
                                      lambda: capture_sfx(PRNG_SFX_ID), sfx[PRNG_SFX_ID])

    with open(os.path.join(out_dir, "manifest.txt"), "w") as handle:
        handle.write(MANIFEST_HEADER % (SONG_FRAME_CAP, SFX_FRAME_CAP) + "\n".join(lines) + "\n")

    report = [end_tally("songs", songs, SONG_FRAME_CAP),
              end_tally("sfx", sfx, SFX_FRAME_CAP),
              "render: quietest of the %d .wav files is %.4f RMS, floor is %.4f"
              % (len(levels), min(levels), WAV_RMS_FLOOR),
              "spectrum: song %d's %d strongest peaks are %s Hz, all partials of its own periods"
              % (SPECTRUM_SONG, len(peaks), ", ".join("%.1f" % f for f, _ in peaks)),
              "checks: song directory speeds, PSG registers 11-15 never written, volume bit 4 "
              "never set, 50 Hz tick-drop on every asset's first tick, song 0 and sfx %d "
              "reproducible" % PRNG_SFX_ID]
    musical = [loop_replay_agreement(result) for result in songs.values()
               if result.end == END_MUSICAL_LOOP]
    if musical:
        report.insert(2, "musical loops: %d, replaying %.0f%%-%.0f%% of their own second period "
                         "(see manifest.txt on why that is not 100%%)"
                      % (len(musical), 100 * min(musical), 100 * max(musical)))
    print("\n".join(report))
    print("\nwrote to %s" % out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
