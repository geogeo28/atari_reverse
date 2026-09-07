"""Differential tests for the whole audio path (src/sound.c): the `A\\MODULE.BAK` YM2149 driver and
the six game wrappers that call it.

THREE THINGS MAKE THIS BATTERY DIFFERENT FROM THE OTHERS, and each is a structural fact rather than
a preference:

* **the routines are not in the .PRG.** The driver is a second GEMDOS `.PRG` the boot chain reads
  whole into the bss, so `harness.BASE_IMAGE` — the loaded game, which is what `test_constants.py`'s
  `ENTRY_PROLOGUES` pins entry bytes against — holds ZEROES at every one of its addresses. Its
  entries are therefore named `MODULE_*` here, and pinned by `test_the_module_entries_hold_the_bytes_
  they_name` against `post_load_image`, which is the image they exist in. The pin is the same one
  `check_entry_prologues` makes, over the right image; the seven GAME-side wrappers are ordinary
  `ENTRY_*` and go through the collector unchanged;

* **most of what the driver does is invisible to the byte diff.** Its output is 13 or 14 register
  writes a frame at `$ff8800`/`$ff8802`, which are outside the image — the kit's direct-PSG ledger
  is what compares them (TRAP_MODEL.md, Phase 6), and `differential` compares it on every case
  whether or not the case asked. A whole-track case is therefore the strongest shape available:
  `test_a_tune_plays_the_same_register_stream_for_frames` drives one tune for
  `TRACK_FRAMES` frames as ONE oracle run, so the ledger it compares is the multi-frame stream in
  order, across sequencer steps, envelope refills, arpeggios and pattern changes;

* **the tempo READS hardware.** `btst #1,$ffff820a` picks the 50/60 Hz divider, so every case that
  reaches the music half of a tick declares that byte with `hw_seed=` (Phase 7). Serving the
  undeclared `0` would be a 60 Hz machine — a fifth slower — agreed on by both sides. Every such
  case runs at BOTH settings for that reason.

`../tools/extract_audio.py` drives the same original under the same oracle for all 5 tunes and 13
effects and writes `../out/audio/manifest.tsv`; the frame counts that file measured are quoted
below as the case data they select, so the two agree about what a track IS.
"""
import ctypes
import random

import pytest

import abi
import emu
import harness
import loader
from harness import differential, report

# ---- the module's own routines. NOT `ENTRY_*`: see the docstring ---------------------------------
A_SOUND_MODULE = 0x58944          # mirror of include/globals.h
SND_ENTRY_VBL_TICK = 38
SND_ENTRY_STOP = 434
SND_ENTRY_SFX_START = 1196
SND_ENTRY_MUSIC_START = 1256

MODULE_VBL_TICK = A_SOUND_MODULE + SND_ENTRY_VBL_TICK
MODULE_STOP = A_SOUND_MODULE + SND_ENTRY_STOP
MODULE_SFX_START = A_SOUND_MODULE + SND_ENTRY_SFX_START
MODULE_MUSIC_START = A_SOUND_MODULE + SND_ENTRY_MUSIC_START
MODULE_END_OF_SONG = 0x58af0       # the command-0x88 handler that falls into MODULE_STOP
MODULE_SEQUENCER_NEXT = 0x58b76
MODULE_SEQUENCER_STEP = 0x58b7a
MODULE_START_NOTE = 0x58be4
MODULE_END_STEP = 0x58c14
MODULE_FRAME_NEXT = 0x58c42
MODULE_FRAME_UPDATE = 0x58c46

# ---- the game wrappers, which ARE in the .PRG and in ../names.txt --------------------------------
ENTRY_SFX_PLAY_6 = 0x1217a
ENTRY_MUSIC_STOP = 0x12192
ENTRY_SFX_PLAY_10 = 0x121b6
ENTRY_SFX_PLAY_5 = 0x121ce
ENTRY_SFX_PLAY_2 = 0x121e6
ENTRY_MUSIC_PLAY = 0x12588
ENTRY_MUSIC_RESTART_IF_STOPPED = 0x1259c

# ---- mirrors of include/sound.h (MIRROR_HEADER below) -------------------------------------------
A_MUSIC_SUSPEND_FLAG = 0x176a4
A_LEVEL_TUNE_ID = 0x1776e

SND_SHADOW_PERIOD_A = 0x00
SND_SHADOW_PERIOD_B = 0x02
SND_SHADOW_PERIOD_C = 0x04
SND_SHADOW_PERIOD_BYTES = 2
SND_SHADOW_NOISE_PERIOD = 0x06
SND_SHADOW_VOLUME_A = 0x07
SND_SHADOW_ENV_PERIOD = 0x0a
SND_SHADOW_ENV_SHAPE = 0x0c
SND_SHADOW_BYTES = 12

SND_SFX_DURATION = 0x0d
SND_SFX_PERIOD_DELTA = 0x0e
SND_SFX_PERIOD_RESET = 0x10
SND_SFX_ALT_DELTA = 0x12
SND_SFX_PERIOD_CURRENT = 0x16
SND_SFX_RESET_RELOAD = 0x18
SND_SFX_ALT_RELOAD = 0x19
SND_SFX_ALT_PATTERN = 0x1a
SND_SFX_NOISE_PATTERN = 0x1b
SND_SFX_RESET_COUNTER = 0x1c
SND_SFX_ALT_COUNTER = 0x1d

SND_MUSIC_ACTIVE = 0x1e
SND_SFX_ACTIVE = 0x1f
SCC_TRUE = 0xff
SND_VBL_50HZ_DIVIDER = 0x20
SND_MUSIC_TEMPO_RELOAD = 0x21
SND_MUSIC_TEMPO_COUNTER = 0x22
SND_NOISE_PERIOD_DEFAULT = 0x23
SND_NOISE_PERIOD_ALT = 0x24
SND_MASTER_VOLUME = 0x25
SND_VARIABLE_BLOCK_BYTES = 0x26

SND_SEQ_COMMAND_TABLE = 0x2de
SND_ARP_LOOP_POINT_TABLE = 0x2f8
SND_INSTRUMENT_ENV_OFFSETS = 0x384
SND_NOTE_PERIOD_TABLE = 0x392
SND_TUNE_TABLE = 0x540
SND_CHANNEL_A = 0x568
SND_ARP_SEQUENCE_TABLE = 0x7d1
SND_VOLUME_ENVELOPE_TABLE = 0x7db
SND_SFX_TABLE = 0xf5e

SND_TUNES = 5
SND_EFFECTS = 13
SND_CHANNELS = 3
SND_CHANNEL_STRIDE = 24

TUNE_RECORD_BYTES = 8
TUNE_TEMPO = 1
TUNE_SEQ_LIST = 2
SEQ_LIST_ENTRY_BYTES = 2

SFX_RECORD_BYTES = 18
SFX_COPIED_WORDS = 7
SFX_ENV_PERIOD_WORD = 14
SFX_ENV_SHAPE_WORD = 16

CHAN_FLAGS = 0x00
CHAN_SEQ_CURSOR = 0x01
CHAN_PATTERN_OFFSET = 0x02
CHAN_SEQ_LIST_OFFSET = 0x04
CHAN_SLIDE_STEP = 0x06
CHAN_SLIDE_DELAY = 0x07
CHAN_SLIDE_ACCUM = 0x08
CHAN_DURATION = 0x0a
CHAN_NOTE_LENGTH = 0x0b
CHAN_NOTE = 0x0c
CHAN_NOTE_TIED = 0xff
CHAN_NOTE_TIED_BIT = 0x80
CHAN_ENV_STEP = 0x0d
CHAN_ENV_BYTE = 0x0e
CHAN_INSTRUMENT = 0x0f
CHAN_VIBRATO_LIMIT = 0x10
CHAN_VIBRATO_SPEED = 0x11
CHAN_VIBRATO_CURRENT = 0x12
CHAN_TRANSPOSE = 0x13
CHAN_OUT_FLAGS = 0x14
CHAN_ARP_LOOP_POINT = 0x15
CHAN_ARP_CURSOR = 0x16

CHAN_FLAG_FRAME_TOGGLE = 1 << 0
CHAN_FLAG_NOISE_ALTERNATE = 1 << 1
CHAN_FLAG_NOISE_ONESHOT = 1 << 2
CHAN_FLAG_SLIDE = 1 << 3
CHAN_FLAG_VIBRATO = 1 << 4
CHAN_FLAG_VIBRATO_UP = 1 << 5
CHAN_FLAG_PORTAMENTO = 1 << 6
CHAN_FLAG_PORTAMENTO_DOWN = 1 << 7
CHAN_OUT_NOISE = 1 << 0
CHAN_OUT_NOISE_NOTE = 1 << 1

PATTERN_NOISE_NOTE_BASE = 0x54
PATTERN_COMMAND_BASE = 0x80
PATTERN_ARP_LOOP_BASE = 0xb0
PATTERN_INSTRUMENT_BASE = 0xc0
PATTERN_NOTE_LENGTH_BASE = 0xe0

ENVELOPE_FINISHED = 0xf0
ENVELOPE_FRAME_STEP = 0x10
PSG_REG_MIXER = 7
PSG_REG_ENV_SHAPE = 13
PSG_MIXER_TONES_ON = 0xf8
PSG_VOLUME_ENVELOPE_MODE = 0x10
SHIFTER_SYNC_50HZ = 1 << 1
VBL_50HZ_DIVIDER_RELOAD = 6

SFX_PLAY_2_NUMBER = 2
SFX_PLAY_5_NUMBER = 5
SFX_PLAY_6_NUMBER = 6
SFX_PLAY_10_NUMBER = 10

SOUND_MODULE_OVER_ARENA_BYTES = 9  # mirror of include/globals.h
A_ENTITY_ARENA = 0x59984           # ...and the address those nine bytes land on

MIRROR_HEADER = "include/sound.h"

# ---- what the cases need that no header owns ----------------------------------------------------
#
# The shifter's sync byte. It is `os.h`'s OS_HW_SHIFTER_SYNC on the C side — the KIT's header, not
# this project's, so `test_constants.py`'s mirror machinery cannot reach it; it is pinned against
# the oracle's own modeled set instead (`test_the_sync_byte_is_one_the_model_serves`).
HW_SHIFTER_SYNC = 0xff820a
SYNC_50HZ = SHIFTER_SYNC_50HZ
SYNC_60HZ = 0
BOTH_MACHINES = (SYNC_50HZ, SYNC_60HZ)

# Where a case stages a pattern of its own. It has to be within a SIGNED 16-BIT offset of the module
# base, because that is how a channel names its pattern (`adda.w 2(a0),a1`) — so `abi.SCRATCH` at
# 0x91000 is unreachable and the staging goes inside the module itself, over the tail of its own
# pattern data. Every case that uses it pokes the whole window, so what the module shipped there
# does not matter; and the poke lands on both sides, as every poke does.
PATTERN_SCRATCH_BYTES = 32
PATTERN_SCRATCH = SND_SFX_TABLE - PATTERN_SCRATCH_BYTES
SEQ_LIST_SCRATCH = PATTERN_SCRATCH - 8   # ...and a little sequence list beneath it

# `../out/audio/manifest.tsv`: 240 frames is inside the shortest tune's lead-in (tune 0 runs 1177)
# and well past several sequencer steps of every one of them, and it keeps the run's chip-access
# ledger under the kit's OS_PSG_LOG_MAX of 4096 — a tick pushes 13 registers, or 14 when it latches
# an envelope shape, so 292 frames is the hard ceiling and this is the round number below it.
TRACK_FRAMES = 240
# ...and the longest effect (10) runs 80 frames, so every effect can be driven to its own end.
EFFECT_FRAMES = 84
# One oracle instruction budget for the multi-frame runs. A tick costs a few hundred instructions
# and a sequencer frame a few thousand; this is the measured worst case with room over it.
TRACK_MAX_INSNS = 2_000_000

# The whole shadow plus the mixer, which is not in it — the least a tick can push, and one more
# goes out on the ticks that latch an envelope shape.
PSG_REGS_PER_TICK = SND_SHADOW_BYTES + 1

FUZZ_CHUNKS = 4
FUZZ_CASES_PER_CHUNK = 24

for _name, _extra in (("g_sound_vbl_tick", 0), ("g_sound_stop", 0),
                      ("g_sfx_start", 1), ("g_music_start", 1),
                      ("g_channel_sequencer_step", 1), ("g_channel_sequencer_next", 1),
                      ("g_sequencer_start_note", 3), ("g_sequencer_end_step", 2),
                      ("g_sfx_play_2", 0), ("g_sfx_play_5", 0), ("g_sfx_play_6", 0),
                      ("g_sfx_play_10", 0), ("g_music_play", 1), ("g_music_stop", 0),
                      ("g_music_restart_if_stopped", 0)):
    getattr(harness._lib, _name).argtypes = ([ctypes.POINTER(ctypes.c_uint8)]
                                             + [ctypes.c_uint32] * _extra)
    getattr(harness._lib, _name).restype = None

# The two that answer in D1 — the tone period the tick stores in the shadow. Their glue RETURNS it,
# so a case can compare it against the oracle's own D1 (`info["regs"]["d1"]`); nothing else could,
# since a register is not a byte of the image.
for _name in ("g_channel_frame_update", "g_channel_frame_next"):
    getattr(harness._lib, _name).argtypes = [ctypes.POINTER(ctypes.c_uint8),
                                             ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
    getattr(harness._lib, _name).restype = ctypes.c_uint32


# ---- staging helpers ----------------------------------------------------------------------------


def mod(offset):
    """An absolute image address for a module-base offset."""
    return A_SOUND_MODULE + offset


def channel_address(index):
    return mod(SND_CHANNEL_A + index * SND_CHANNEL_STRIDE)


_CHANNEL_WORD_FIELDS = (CHAN_PATTERN_OFFSET, CHAN_SEQ_LIST_OFFSET, CHAN_SLIDE_ACCUM)


def channel_struct(fields):
    """One 24-byte channel struct: every byte zero bar the `{CHAN_*: value}` entries in `fields`.

    Spelt as WHOLE STRUCTS rather than as per-field pokes because a channel the tick reads must be
    entirely defined: leaving a field at whatever the module happened to hold there makes the case
    depend on data it never states, and the state a fuzz case reached is then not reproducible from
    the case's own text.
    """
    raw = bytearray(SND_CHANNEL_STRIDE)
    for offset, value in fields.items():
        if offset in _CHANNEL_WORD_FIELDS:
            raw[offset:offset + 2] = (value & 0xffff).to_bytes(2, "big")
        else:
            raw[offset] = value & 0xff
    return bytes(raw)


def silent_channels():
    """Pokes that put all three channels in the state `music_start` never quite leaves them in:
    every byte zero. Used by the cases that arm ONE channel and want the other two out of the way."""
    return {channel_address(index): bytes(SND_CHANNEL_STRIDE) for index in range(SND_CHANNELS)}


def module_word(image, offset):
    return int.from_bytes(bytes(image[mod(offset):mod(offset) + 2]), "big")


def tune_record(image, number):
    at = mod(SND_TUNE_TABLE + number * TUNE_RECORD_BYTES)
    return bytes(image[at:at + TUNE_RECORD_BYTES])


def tick_sequence_pokes(frames, before=()):
    """Pokes for a stub that runs `before` (`(routine, d0)` steps) and then `frames` ticks."""
    steps = list(before) + [(MODULE_VBL_TICK, 0)] * frames
    return abi.call_sequence_with_d0_pokes(steps)


def tick_sequence_glue(lib, buf, frames, before=()):
    """The candidate side of `tick_sequence_pokes`, in the same order."""
    for routine, argument in before:
        _MODULE_GLUE[routine](lib, buf, argument)
    for _frame in range(frames):
        lib.g_sound_vbl_tick(buf)


_MODULE_GLUE = {
    MODULE_VBL_TICK: lambda lib, buf, argument: lib.g_sound_vbl_tick(buf),
    MODULE_MUSIC_START: lambda lib, buf, argument: lib.g_music_start(buf, argument),
    MODULE_SFX_START: lambda lib, buf, argument: lib.g_sfx_start(buf, argument),
    MODULE_STOP: lambda lib, buf, argument: lib.g_sound_stop(buf),
}


def run_ticks(frames, before=(), sync=SYNC_50HZ, extra_pokes=None):
    """One differential over `before` then `frames` ticks, at the declared machine speed."""
    pokes = tick_sequence_pokes(frames, before)
    pokes.update(extra_pokes or {})

    def glue(lib, buf):
        tick_sequence_glue(lib, buf, frames, before)

    return differential(abi.STUB, {"_pokes": pokes}, glue,
                        max_insns=TRACK_MAX_INSNS, hw_seed={HW_SHIFTER_SYNC: sync})


# ==================================================== the addresses this battery names


MODULE_ENTRY_PROLOGUES = {
    "MODULE_VBL_TICK": "48e7e0f0424047faffd2",
    "MODULE_STOP": "2f0841fafe5151e80017",
    "MODULE_SFX_START": "48e780c045fafb4e4880",
    "MODULE_MUSIC_START": "48e7e0c04880e70043fa",
    "MODULE_END_OF_SONG": "41fafee42e882f0841fa",
    "MODULE_SEQUENCER_NEXT": "d0fc00185328000a6644",
    "MODULE_SEQUENCER_STEP": "5328000a664402100030",
    "MODULE_START_NOTE": "426800084a28000c6b08",
    "MODULE_END_STEP": "1168000b000a93cb3149",
    "MODULE_FRAME_NEXT": "d0fc00180c2800f0000e",
    "MODULE_FRAME_UPDATE": "0c2800f0000e641e0428",
}


def test_the_module_entries_hold_the_bytes_they_name(post_load_image):
    """`check_entry_prologues`' check for the routines it structurally cannot make.

    `test_constants.py` pins an `ENTRY_*` against `harness.BASE_IMAGE`, the .PRG AS LOADED — which
    is right for every routine in the game and WRONG for these: `A\\MODULE.BAK` is a separate file
    the boot chain reads into the bss, so the loaded .PRG holds zeroes at all eleven addresses and
    a pin there would compare zero against zero and pass for ever. So they are pinned here, against
    the image the module exists in, with the same rule: EVERY declared address is pinned, and one
    that is not fails by name.
    """
    declared = {name: value for name, value in globals().items()
                if name.startswith("MODULE_") and isinstance(value, int)
                and loader.LOAD_BASE <= value < loader.PROGRAM_END}
    missing = sorted(set(declared) - set(MODULE_ENTRY_PROLOGUES))
    assert not missing, (
        f"{', '.join(missing)} name module addresses with no MODULE_ENTRY_PROLOGUES row — an "
        f"address that is never pinned could point at a different routine and still come back clean")
    unknown = sorted(set(MODULE_ENTRY_PROLOGUES) - set(declared))
    assert not unknown, f"MODULE_ENTRY_PROLOGUES pins {', '.join(unknown)}, which names nothing"
    for name, prologue in MODULE_ENTRY_PROLOGUES.items():
        expected = bytes.fromhex(prologue)
        actual = bytes(post_load_image[declared[name]:declared[name] + len(expected)])
        assert actual == expected, (
            f"{name} = {declared[name]:#x} holds {actual.hex()}, not the {expected.hex()} this "
            f"address holds in the staged module")


def test_the_wrappers_jsr_the_module_offsets_the_header_names(post_load_image):
    """Each wrapper's `jsr <n>(a0)` reaches the entry `include/sound.h` says it does.

    The wrappers are the ONE place the module's four entries are named as offsets rather than as
    addresses, and the offset is what a reconstruction has to get right: a wrapper calling +1256
    instead of +1196 starts a tune where the game starts an effect, and both are `jsr`s into a blob
    whose entry table nothing else states.
    """
    sites = {ENTRY_SFX_PLAY_6: (0x12188, SND_ENTRY_SFX_START),
             ENTRY_SFX_PLAY_10: (0x121c4, SND_ENTRY_SFX_START),
             ENTRY_SFX_PLAY_5: (0x121dc, SND_ENTRY_SFX_START),
             ENTRY_SFX_PLAY_2: (0x121f4, SND_ENTRY_SFX_START),
             ENTRY_MUSIC_PLAY: (0x12592, SND_ENTRY_MUSIC_START),
             ENTRY_MUSIC_STOP: (0x121a2, SND_ENTRY_STOP),
             ENTRY_MUSIC_RESTART_IF_STOPPED: (0x125b6, SND_ENTRY_MUSIC_START)}
    jsr_displacement_a0 = 0x4ea8   # `jsr <d16>(a0)`
    for wrapper, (site, entry_offset) in sites.items():
        opcode = int.from_bytes(bytes(post_load_image[site:site + 2]), "big")
        displacement = int.from_bytes(bytes(post_load_image[site + 2:site + 4]), "big")
        assert opcode == jsr_displacement_a0, (
            f"the wrapper at {wrapper:#x} has no `jsr <n>(a0)` at {site:#x}: {opcode:#06x}")
        assert displacement == entry_offset, (
            f"the wrapper at {wrapper:#x} calls the module's +{displacement}, not the "
            f"+{entry_offset} include/sound.h names")


def test_each_sfx_wrapper_loads_the_number_the_header_names(post_load_image):
    """`move.w #$n,d0` — the one place a wrapper's effect number is written down in the binary.

    Four wrappers whose bodies are otherwise byte-identical, so this immediate is the whole of what
    distinguishes them, and `include/sound.h`'s four `SFX_PLAY_*_NUMBER` are its only other home.
    """
    move_w_immediate_d0 = 0x303c
    sites = {ENTRY_SFX_PLAY_2: (0x121f0, SFX_PLAY_2_NUMBER),
             ENTRY_SFX_PLAY_5: (0x121d8, SFX_PLAY_5_NUMBER),
             ENTRY_SFX_PLAY_6: (0x12184, SFX_PLAY_6_NUMBER),
             ENTRY_SFX_PLAY_10: (0x121c0, SFX_PLAY_10_NUMBER)}
    for wrapper, (site, number) in sites.items():
        opcode = int.from_bytes(bytes(post_load_image[site:site + 2]), "big")
        immediate = int.from_bytes(bytes(post_load_image[site + 2:site + 4]), "big")
        assert opcode == move_w_immediate_d0, (
            f"the wrapper at {wrapper:#x} has no `move.w #n,d0` at {site:#x}: {opcode:#06x}")
        assert immediate == number, (
            f"the wrapper at {wrapper:#x} plays effect {immediate}, not the {number} "
            f"include/sound.h names")


def test_the_sync_byte_is_one_the_model_serves():
    """`hw_seed` refuses an address outside the modeled set, so a typo would fail every tick case
    at once with a ValueError rather than here — but it would fail as a keyword-argument problem
    and not as "the tempo input is not declared". This is the one line that says which it is."""
    assert HW_SHIFTER_SYNC in emu.HW_ADDRS, (
        f"{HW_SHIFTER_SYNC:#x} is not one of the hardware bytes the model serves "
        f"({', '.join(f'{a:#x}' for a in emu.HW_ADDRS)}) — the tempo read could not be declared")


# ==================================================== music_start @ 0x58e2c


@pytest.mark.parametrize("tune", range(SND_TUNES))
def test_music_start_arms_every_tune(tune):
    """All five shipped tunes, each seeding three channel structs and the tempo out of its record."""
    diffs, _ = differential(MODULE_MUSIC_START, {"d0": tune, "a0": A_SOUND_MODULE},
                            lambda lib, buf: lib.g_music_start(buf, tune), poison=True)
    assert not diffs, report(diffs)


def test_music_start_reads_the_record_the_image_holds(post_load_image):
    """...and what it seeded is that record's own words, not a table this port carries.

    The check is deliberately made against the IMAGE rather than against a transcription of the five
    records: the tables are `A\\MODULE.BAK`'s bytes and a copy of them here would be a second thing
    to keep true (`include/sound.h`, "everything the driver reads is in the image").
    """
    for tune in range(SND_TUNES):
        record = tune_record(post_load_image, tune)
        image = harness.make_image({})
        final, _writes, _regs = emu.run(image, MODULE_MUSIC_START,
                                        {"d0": tune, "a0": A_SOUND_MODULE})
        assert final[mod(SND_MUSIC_TEMPO_RELOAD)] == record[TUNE_TEMPO]
        for index in range(SND_CHANNELS):
            at = channel_address(index)
            listed = int.from_bytes(record[TUNE_SEQ_LIST + index * SEQ_LIST_ENTRY_BYTES:][:2], "big")
            assert int.from_bytes(bytes(final[at + CHAN_SEQ_LIST_OFFSET:][:2]), "big") == listed


# The tune number reaches the record index through `ext.w` and then a BYTE shift, so it is bounded
# by nothing: 5..0x7f run off the end of the five records into the channel structs behind them, and
# 0x80..0xff resolve BELOW the table because `ext.w`'s sign survives the byte shift. Every one of
# them stays inside the image, so every one is a case the differential can settle.
UNBOUNDED_TUNE_NUMBERS = (SND_TUNES, 0x20, 0x7f, 0x80, 0xc0, 0xff)


@pytest.mark.parametrize("tune", UNBOUNDED_TUNE_NUMBERS)
def test_music_start_does_not_bound_the_tune_number(tune):
    diffs, _ = differential(MODULE_MUSIC_START, {"d0": tune, "a0": A_SOUND_MODULE},
                            lambda lib, buf: lib.g_music_start(buf, tune), poison=True)
    assert not diffs, report(diffs)


def test_music_start_takes_only_the_low_byte_of_d0():
    """`ext.w d0` overwrites D0's word from its byte, so the wrapper's `move.w $1776e,d0` can hand
    over any word and the module reads a number 0..255 out of it."""
    diffs, _ = differential(MODULE_MUSIC_START, {"d0": 0xbeef00 | 3, "a0": A_SOUND_MODULE},
                            lambda lib, buf: lib.g_music_start(buf, 3), poison=True)
    assert not diffs, report(diffs)


# ==================================================== sfx_start @ 0x58df0


@pytest.mark.parametrize("effect", range(SND_EFFECTS))
def test_sfx_start_arms_every_effect(effect):
    diffs, _ = differential(MODULE_SFX_START, {"d0": effect, "a0": A_SOUND_MODULE},
                            lambda lib, buf: lib.g_sfx_start(buf, effect), poison=True)
    assert not diffs, report(diffs)


UNBOUNDED_EFFECT_NUMBERS = (SND_EFFECTS, 0x40, 0x7f, 0x80, 0xff)


@pytest.mark.parametrize("effect", UNBOUNDED_EFFECT_NUMBERS)
def test_sfx_start_does_not_bound_the_effect_number(effect):
    """`ext.w` + `mulu.w` + `adda.w`: only the product's low word reaches the address, so a number
    with bit 7 set reads a record from BELOW the table rather than above it."""
    diffs, _ = differential(MODULE_SFX_START, {"d0": effect, "a0": A_SOUND_MODULE},
                            lambda lib, buf: lib.g_sfx_start(buf, effect), poison=True)
    assert not diffs, report(diffs)


def test_effect_12_is_read_out_of_whichever_image_the_game_left():
    """The nine bytes `A\\MODULE.BAK`'s load leaves over the entity arena are effect 12's own tail.

    `include/globals.h`, "THE SOUND MODULE OVERLAPS THE ARENA": the module's staged bytes run nine
    past `A_entity_arena`, and `clear_actor_arrays` zeroes them on the first `init_new_game` — so
    ON THE MACHINE THE DRIVER ACTUALLY RUNS ON, effect 12's last eight bytes are zero. The game
    never asks for it (the six `sfx_start` sites pass 6, 10, 5, 2, 5 and 11), which is why this is a
    case about the port READING THE IMAGE rather than about a sound anyone hears: the two images
    give different answers, and a port carrying a copy of the table would give one answer twice.
    """
    last = SND_EFFECTS - 1
    started_game = {A_ENTITY_ARENA: bytes(SOUND_MODULE_OVER_ARENA_BYTES)}
    for pokes in ({}, started_game):
        diffs, _ = differential(MODULE_SFX_START,
                                {"d0": last, "a0": A_SOUND_MODULE, "_pokes": pokes},
                                lambda lib, buf: lib.g_sfx_start(buf, last), poison=True)
        assert not diffs, report(diffs)
    # The two runs above prove the port agrees with the original on both images. What is left is
    # that they really ARE two images — otherwise this case names an overlap it never exercised.
    at = mod(SND_SFX_TABLE + last * SFX_RECORD_BYTES)
    pristine = bytes(harness.make_image({})[at:at + SFX_RECORD_BYTES])
    zeroed = bytes(harness.make_image(started_game)[at:at + SFX_RECORD_BYTES])
    assert pristine != zeroed, (
        f"effect {last}'s record reads the same on the pristine image and on the one "
        f"init_new_game leaves, so this case is not testing the overlap it names")


def test_sfx_start_clears_the_active_flag_before_it_fills_the_block():
    """...and sets it after, so a tick that fell between the two sees an idle block rather than a
    half-written one. Entered with the flag already up, which is the state the game's own guarded
    sites (`tst.b sfx_active` at 0x12944 and 0x13e3c) are avoiding."""
    pokes = {mod(SND_SFX_ACTIVE): bytes([SCC_TRUE])}
    diffs, _ = differential(MODULE_SFX_START,
                            {"d0": SFX_PLAY_5_NUMBER, "a0": A_SOUND_MODULE, "_pokes": pokes},
                            lambda lib, buf: lib.g_sfx_start(buf, SFX_PLAY_5_NUMBER), poison=True)
    assert not diffs, report(diffs)


# ==================================================== sound_stop @ 0x58af6


def test_sound_stop_clears_the_music_and_the_three_volumes():
    pokes = {mod(SND_MUSIC_ACTIVE): bytes([SCC_TRUE]), mod(SND_SHADOW_VOLUME_A): b"\x0a\x0b\x0c"}
    diffs, _ = differential(MODULE_STOP, {"a0": A_SOUND_MODULE, "_pokes": pokes},
                            lambda lib, buf: lib.g_sound_stop(buf), poison=True)
    assert not diffs, report(diffs)


def test_sound_stop_leaves_a_running_effect_alone():
    """It clears `music_active` and not `sfx_active`, so an effect started before it plays on — and
    the very next tick then overwrites the channel-C volume it just cleared."""
    pokes = {mod(SND_MUSIC_ACTIVE): bytes([SCC_TRUE]), mod(SND_SFX_ACTIVE): bytes([SCC_TRUE]),
             mod(SND_SHADOW_VOLUME_A): b"\x0a\x0b\x0c"}
    diffs, _ = differential(MODULE_STOP, {"a0": A_SOUND_MODULE, "_pokes": pokes},
                            lambda lib, buf: lib.g_sound_stop(buf), poison=True)
    assert not diffs, report(diffs)


# ==================================================== sound_vbl_tick @ 0x5896a


@pytest.mark.parametrize("sync", BOTH_MACHINES)
def test_a_tick_with_nothing_playing_still_pushes_the_shadow(sync):
    """Both halves skipped, and the chip still gets all thirteen registers.

    The flush is unconditional, so "silence" is a register stream and not an absence of one — which
    is the whole reason the PSG ledger is the surface here: a port that skipped the flush when
    nothing was playing would be byte-identical in the image.
    """
    diffs, _ = run_ticks(1, sync=sync)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("sync", BOTH_MACHINES)
def test_the_divider_drops_one_tick_in_six_on_a_60_hz_machine(sync):
    """Seven ticks with a tune running: on a 50 Hz machine all seven step the divider not at all,
    and on a 60 Hz one the sixth reloads it to 6 and skips the music entirely.

    Seven rather than six so that the skipped frame is not the last one — a case that ended ON the
    dropped tick would compare a state the following frame had not yet had to live with.
    """
    diffs, _ = run_ticks(7, before=[(MODULE_MUSIC_START, 1)], sync=sync)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("divider", (1, 2, VBL_50HZ_DIVIDER_RELOAD, 0))
def test_the_60_hz_divider_reloads_from_every_phase(divider):
    """...including the wrap: `subq.b #1` on a zero divider gives 0xff, which is non-zero, so a
    driver entered on a zero byte runs 255 more ticks before it drops one."""
    pokes = {mod(SND_VBL_50HZ_DIVIDER): bytes([divider])}
    diffs, _ = run_ticks(2, before=[(MODULE_MUSIC_START, 2)], sync=SYNC_60HZ, extra_pokes=pokes)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("tune", range(SND_TUNES))
@pytest.mark.parametrize("sync", BOTH_MACHINES)
def test_a_tune_plays_the_same_register_stream_for_frames(tune, sync):
    """THE CASE THIS BATTERY IS BUILT AROUND: one tune, TRACK_FRAMES frames, as ONE oracle run.

    Everything the driver has is exercised together and in order — the tempo counter, the sequencer
    over three channels, note lengths, instruments, envelopes refilling from the envelope table,
    arpeggios, vibrato, pitch slides, pattern changes through the sequence list, and the mixer — and
    the comparison is the whole multi-frame `$ff8800`/`$ff8802` stream plus every byte of the
    driver's state at the end. `../tools/extract_audio.py` drives the same tunes through the same
    oracle to write `../out/audio/manifest.tsv`; this is the reconstruction held against that.
    """
    diffs, info = run_ticks(TRACK_FRAMES, before=[(MODULE_MUSIC_START, tune)], sync=sync)
    assert not diffs, report(diffs)
    # ...and the run really was TRACK_FRAMES frames long. A stub that emitted fewer calls, or a
    # `music_start` that left the driver idle, would make every assertion above vacuous while the
    # case still reported green — a shorter run has a shorter stream on BOTH sides.
    assert len(info["regs"]["hw_events"]) == TRACK_FRAMES, (
        f"{len(info['regs']['hw_events'])} tempo reads, not one per frame")
    assert len(info["regs"]["psg"]) >= TRACK_FRAMES * PSG_REGS_PER_TICK, (
        f"{len(info['regs']['psg'])} register writes over {TRACK_FRAMES} frames, short of the "
        f"{PSG_REGS_PER_TICK} every tick pushes")


@pytest.mark.parametrize("effect", range(SND_EFFECTS))
def test_an_effect_plays_to_its_own_end(effect):
    """Every effect, driven past the longest one's 80 frames, so each ends by its own duration
    counter reaching zero — which is what clears `sfx_active` and zeroes the channel-C volume."""
    diffs, _ = run_ticks(EFFECT_FRAMES, before=[(MODULE_SFX_START, effect)], sync=SYNC_50HZ)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("effect", (SFX_PLAY_2_NUMBER, SFX_PLAY_5_NUMBER, SFX_PLAY_6_NUMBER,
                                    SFX_PLAY_10_NUMBER))
def test_an_effect_pre_empts_the_music_on_channel_c(effect):
    """A tune running, an effect started between two ticks, and the frames after it.

    That is exactly how the game does it: the tick site is the VBL handler and every wrapper is
    called from the game loop between two of them. The effect takes channel C's volume, period and
    mixer bit and leaves A and B to the music, which the register stream is what proves.
    """
    frames_before = 24
    steps = [(MODULE_MUSIC_START, 1)] + [(MODULE_VBL_TICK, 0)] * frames_before \
        + [(MODULE_SFX_START, effect)]
    diffs, _ = run_ticks(EFFECT_FRAMES, before=steps, sync=SYNC_50HZ)
    assert not diffs, report(diffs)


def test_sound_stop_mid_track_silences_the_next_tick():
    """`sound_stop` between two ticks: the volumes it zeroes are shadow bytes, so the chip only
    hears it on the FOLLOWING flush — and the music half is skipped from then on."""
    steps = [(MODULE_MUSIC_START, 3)] + [(MODULE_VBL_TICK, 0)] * 30 + [(MODULE_STOP, 0)]
    diffs, _ = run_ticks(8, before=steps, sync=SYNC_50HZ)
    assert not diffs, report(diffs)


def test_an_effect_survives_sound_stop():
    """...and keeps writing channel C, because `sound_stop` does not touch `sfx_active`."""
    steps = [(MODULE_MUSIC_START, 2)] + [(MODULE_VBL_TICK, 0)] * 10 \
        + [(MODULE_SFX_START, SFX_PLAY_10_NUMBER)] + [(MODULE_VBL_TICK, 0)] * 4 \
        + [(MODULE_STOP, 0)]
    diffs, _ = run_ticks(EFFECT_FRAMES, before=steps, sync=SYNC_50HZ)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("master", (0x0f, 0x0e, 0x08, 0x00, 0xff))
def test_the_master_volume_clips_the_quiet_envelope_steps(master):
    """`(level | 0xf0) + 1 + master_volume`, kept only if it CARRIED.

    The shipped 0x0f passes every level through unchanged; anything smaller turns the quiet end of
    every envelope into silence, and 0 silences the music altogether. The game never writes the
    byte, so this is the module's own knob driven from its whole range rather than a game state.
    """
    pokes = {mod(SND_MASTER_VOLUME): bytes([master])}
    diffs, _ = run_ticks(40, before=[(MODULE_MUSIC_START, 0)], sync=SYNC_50HZ, extra_pokes=pokes)
    assert not diffs, report(diffs)


def test_the_envelope_shape_is_a_one_shot_latch():
    """Register 13 goes out only on the ticks its shadow byte is non-zero, and the push zeroes it.

    So an effect re-triggers the chip's hardware envelope on the frame it starts and on no other,
    and the two ticks below must differ in their register COUNT — which no image byte records.
    """
    diffs, info = run_ticks(2, before=[(MODULE_SFX_START, SFX_PLAY_6_NUMBER)], sync=SYNC_50HZ)
    assert not diffs, report(diffs)
    shapes = [reg for reg, _value in info["regs"]["psg"] if reg == PSG_REG_ENV_SHAPE]
    assert len(shapes) == 1, (
        f"two ticks after an effect started pushed register {PSG_REG_ENV_SHAPE} {len(shapes)} "
        f"times; the latch should fire on the first and never again")


# ==================================================== the sequencer and its thirteen commands
#
# A staged pattern, a channel pointed at it and a duration of 1, so that one entry at
# `channel_sequencer_step` consumes exactly the bytes the case wrote.


NOTE = 0x20                       # an ordinary tone note, comfortably inside the 84-entry table
NOISE_NOTE = PATTERN_NOISE_NOTE_BASE + 3


def sequencer_pokes(pattern, channel_fields=None):
    """Pokes that arm channel A with `pattern` in the module's pattern scratch."""
    fields = {CHAN_DURATION: 1, CHAN_NOTE_LENGTH: 4, CHAN_PATTERN_OFFSET: PATTERN_SCRATCH}
    fields.update(channel_fields or {})
    pokes = silent_channels()
    pokes[mod(PATTERN_SCRATCH)] = bytes(pattern).ljust(PATTERN_SCRATCH_BYTES, b"\x00")
    pokes[channel_address(0)] = channel_struct(fields)
    return pokes


def run_sequencer(pattern, channel_fields=None):
    """One `channel_sequencer_step` over a staged pattern. D0 enters 0 — see src/sound.c's docstring
    on D0's high half, which the original's `(pc,d0.w)` table indices depend on."""
    pokes = sequencer_pokes(pattern, channel_fields)
    channel = channel_address(0)
    return differential(MODULE_SEQUENCER_STEP,
                        {"a0": channel, "a3": A_SOUND_MODULE, "d0": 0, "_pokes": pokes},
                        lambda lib, buf: lib.g_channel_sequencer_step(buf, channel), poison=True)


# Every command byte the sequencer dispatches, each with the operands it consumes and a note to end
# the step on. 0x88 is absent on purpose: it never returns to its caller (below).
SEQUENCER_COMMANDS = {
    0x80: [0x80],                       # rest — ends the step by itself
    0x81: [0x81, NOTE],
    0x82: [0x82, 0xfe, 0x03, NOTE],     # slide: step -2, delay 3
    0x83: [0x83, NOTE],
    0x84: [0x84, NOTE],
    0x86: [0x86, 0x02, 0x0a, NOTE],     # vibrato: speed 2, depth 10
    0x87: [0x87, NOTE],
    0x89: [0x89, 0x0c, NOTE],           # transpose +12
    0x8a: [0x8a, NOTE],
    0x8b: [0x8b, 0x07, NOTE],           # noise period 7, then as 0x8a
    0x8c: [0x8c, NOTE],
}


@pytest.mark.parametrize("command", sorted(SEQUENCER_COMMANDS))
def test_the_sequencer_runs_every_pattern_command(command):
    """Each command reached THROUGH the dispatch, so the 13-word jump table is part of the case.

    The table is read out of the image and its word is what names the handler (src/sound.c), so a
    port that dispatched on the command byte instead would pass these and diverge the day the table
    it never read said something else.
    """
    diffs, _ = run_sequencer(SEQUENCER_COMMANDS[command])
    assert not diffs, report(diffs)


def test_command_0x85_steps_the_sequence_list():
    """...and a 0x0000 word RESTARTS the list rather than ending it, which is how a tune loops."""
    entries = [PATTERN_SCRATCH + 8, 0x0000]
    list_bytes = b"".join(value.to_bytes(2, "big") for value in entries)
    pattern = [0x85] + [0] * 7 + [NOTE]        # the 0x85 at +0, the list's target pattern at +8
    for cursor in (0, SEQ_LIST_ENTRY_BYTES):   # a live entry, then the terminator
        pokes = sequencer_pokes(pattern, {CHAN_SEQ_CURSOR: cursor,
                                          CHAN_SEQ_LIST_OFFSET: SEQ_LIST_SCRATCH})
        pokes[mod(SEQ_LIST_SCRATCH)] = list_bytes
        channel = channel_address(0)
        diffs, _ = differential(MODULE_SEQUENCER_STEP,
                                {"a0": channel, "a3": A_SOUND_MODULE, "d0": 0, "_pokes": pokes},
                                lambda lib, buf: lib.g_channel_sequencer_step(buf, channel),
                                poison=True)
        assert not diffs, report(diffs)


def test_command_0x88_ends_the_song_and_the_rest_of_the_tick():
    """0x88 is the one command that does not come back: it overwrites `channel_sequencer_step`'s
    return address on the stack so the `rts` lands past the whole music update (src/sound.c).

    It therefore has to be entered at the TICK — entering at `channel_sequencer_step` would rewrite
    the HARNESS's return address — and what the case proves is the reach of that rewrite: channels
    B and C do not get their sequencer step, and the noise shadow and all three periods are left
    exactly as the previous frame set them.
    """
    pattern = [0x88]
    pokes = sequencer_pokes(pattern)
    pokes[mod(SND_MUSIC_ACTIVE)] = bytes([SCC_TRUE])
    pokes[mod(SND_MUSIC_TEMPO_COUNTER)] = b"\x01"
    pokes[mod(SND_MUSIC_TEMPO_RELOAD)] = b"\x04"
    # Channels B and C armed with a note each, so "they did not run" is visible in the image.
    for index in (1, 2):
        pokes[channel_address(index)] = channel_struct({
            CHAN_DURATION: 1, CHAN_NOTE_LENGTH: 4, CHAN_PATTERN_OFFSET: PATTERN_SCRATCH + 16})
    pokes[mod(PATTERN_SCRATCH)] = (bytes(pattern).ljust(16, b"\x00")
                                   + bytes([NOTE])).ljust(PATTERN_SCRATCH_BYTES, b"\x00")

    diffs, _ = differential(MODULE_VBL_TICK, {"a0": A_SOUND_MODULE, "_pokes": pokes},
                            lambda lib, buf: lib.g_sound_vbl_tick(buf),
                            hw_seed={HW_SHIFTER_SYNC: SYNC_50HZ})
    assert not diffs, report(diffs)


@pytest.mark.parametrize("byte", (0x00, 0x53, PATTERN_NOISE_NOTE_BASE, 0x7f))
def test_a_note_byte_ends_the_step(byte):
    """Tone notes 0x00..0x53 and noise notes 0x54..0x7f, at both ends of both ranges. A noise note
    also sets the out-flag bit and writes `byte - 0x54` to the default noise period."""
    diffs, _ = run_sequencer([byte])
    assert not diffs, report(diffs)


@pytest.mark.parametrize("previous_note", (0x00, 0x53, CHAN_NOTE_TIED_BIT, CHAN_NOTE_TIED))
def test_a_tie_carries_the_envelope_into_the_next_note(previous_note):
    """`sequencer_start_note` resets the envelope only when the previous note was NON-negative, and
    command 0x8c leaves 0xff there for exactly that reason. Both arms, at the sign boundary."""
    diffs, _ = run_sequencer([NOTE], {CHAN_NOTE: previous_note, CHAN_ENV_BYTE: 0x35,
                                      CHAN_ENV_STEP: 4})
    assert not diffs, report(diffs)


def test_a_tie_followed_by_a_rest_leaves_the_sentinel_in_the_note():
    """The one pattern that makes command 0x8c's WRITTEN VALUE observable, rather than only its
    effect.

    A tie is normally followed by a note, which overwrites the byte before the step ends — so the
    0xff never reaches the image, and any negative sentinel would behave identically (measured: a
    port writing 0x80 instead survives the rest of this battery). A tie followed by a REST ends the
    step with the sentinel still there.
    """
    diffs, _ = run_sequencer([0x8c, 0x80])
    assert not diffs, report(diffs)


@pytest.mark.parametrize("byte", (PATTERN_ARP_LOOP_BASE, PATTERN_ARP_LOOP_BASE + 5,
                                  PATTERN_ARP_LOOP_BASE + 6, 0xbf))
def test_the_arp_loop_point_bytes_index_a_six_entry_table(byte):
    """0xb0..0xb5 are the six the table has, and 0xb6..0xbf read on past its end into the code
    behind it — which the original does with no check at all, and an image read reproduces."""
    diffs, _ = run_sequencer([byte, NOTE])
    assert not diffs, report(diffs)


@pytest.mark.parametrize("byte", (PATTERN_INSTRUMENT_BASE, PATTERN_INSTRUMENT_BASE + 13,
                                  PATTERN_INSTRUMENT_BASE + 14, 0xdf))
def test_an_instrument_byte_selects_one_of_fourteen(byte):
    """0xc0..0xcd are the fourteen that exist; 0xce..0xdf select an offset from beyond the
    fourteen-byte table, which the envelope fetch then indexes with."""
    diffs, _ = run_sequencer([byte, NOTE], {CHAN_ENV_BYTE: 0x05})
    assert not diffs, report(diffs)


@pytest.mark.parametrize("byte", (PATTERN_NOTE_LENGTH_BASE, PATTERN_NOTE_LENGTH_BASE + 1, 0xff))
def test_a_note_length_byte_is_the_byte_plus_one(byte):
    diffs, _ = run_sequencer([byte, NOTE])
    assert not diffs, report(diffs)


@pytest.mark.parametrize("flags", (0, CHAN_FLAG_PORTAMENTO,
                                   CHAN_FLAG_PORTAMENTO | CHAN_FLAG_PORTAMENTO_DOWN,
                                   CHAN_FLAG_PORTAMENTO_DOWN))
@pytest.mark.parametrize("note", (0x00, 0x30, 0xff))
def test_a_sounding_note_only_runs_portamento(flags, note):
    """While the duration has not expired the sequencer does nothing but walk the note number, one
    semitone a step — and only when bit 6 is set, bit 7 alone doing nothing at all."""
    pokes = sequencer_pokes([NOTE], {CHAN_DURATION: 3, CHAN_FLAGS: flags, CHAN_NOTE: note})
    channel = channel_address(0)
    diffs, _ = differential(MODULE_SEQUENCER_STEP,
                            {"a0": channel, "a3": A_SOUND_MODULE, "d0": 0, "_pokes": pokes},
                            lambda lib, buf: lib.g_channel_sequencer_step(buf, channel), poison=True)
    assert not diffs, report(diffs)


def test_the_sequencer_step_keeps_only_the_vibrato_flags():
    """`andi.b #$30,(a0)` — a new step drops the slide, the portamento and the noise modes and keeps
    vibrato and its direction, which is why vibrato survives a note change and a slide does not."""
    diffs, _ = run_sequencer([NOTE], {CHAN_FLAGS: 0xff})
    assert not diffs, report(diffs)


def test_channel_sequencer_next_steps_the_following_channel():
    """`adda.w #24,a0` and fall through — the tick's way of walking B and C, and the reason A0 comes
    back advanced."""
    pokes = sequencer_pokes([NOTE])
    pokes[channel_address(1)] = channel_struct({CHAN_DURATION: 1, CHAN_NOTE_LENGTH: 6,
                                                CHAN_PATTERN_OFFSET: PATTERN_SCRATCH})
    channel = channel_address(0)
    diffs, _ = differential(MODULE_SEQUENCER_NEXT,
                            {"a0": channel, "a3": A_SOUND_MODULE, "d0": 0, "_pokes": pokes},
                            lambda lib, buf: lib.g_channel_sequencer_next(buf, channel), poison=True)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("note", (0x00, 0x53, PATTERN_NOISE_NOTE_BASE, 0x7f))
@pytest.mark.parametrize("previous_note", (0x10, CHAN_NOTE_TIED))
def test_sequencer_start_note_directly(note, previous_note):
    """The shared note tail on its own: A1 in = the pattern cursor, D0.b = the note byte."""
    pokes = sequencer_pokes([note], {CHAN_NOTE: previous_note, CHAN_ARP_LOOP_POINT: 3,
                                     CHAN_ENV_BYTE: 0x21, CHAN_ENV_STEP: 2})
    channel = channel_address(0)
    cursor = mod(PATTERN_SCRATCH) + 1
    diffs, _ = differential(MODULE_START_NOTE,
                            {"a0": channel, "a1": cursor, "a3": A_SOUND_MODULE, "d0": note,
                             "_pokes": pokes},
                            lambda lib, buf: lib.g_sequencer_start_note(buf, channel, note, cursor),
                            poison=True)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("length", (0, 1, 0xff))
def test_sequencer_end_step_directly(length):
    """The other shared tail: reload the duration from the note length and store the cursor back as
    a 16-bit offset from the module base."""
    pokes = sequencer_pokes([NOTE], {CHAN_NOTE_LENGTH: length})
    channel = channel_address(0)
    cursor = mod(PATTERN_SCRATCH) + 4
    diffs, _ = differential(MODULE_END_STEP,
                            {"a0": channel, "a1": cursor, "a3": A_SOUND_MODULE, "_pokes": pokes},
                            lambda lib, buf: lib.g_sequencer_end_step(buf, channel, cursor),
                            poison=True)
    assert not diffs, report(diffs)


# ==================================================== the per-frame update @ 0x58c46


def run_frame_update(entry, channel_index, channel_fields, arp_table=None):
    """One `channel_frame_update` (or `_next`) over a staged channel, comparing the returned D1.

    The period is answered in a REGISTER and written to no byte of the image, so the glue returns it
    and the case holds that against the oracle's own D1 — the one thing the byte diff cannot see.

    `arp_table` is A1, which the routine indexes BOTH its arpeggio and its envelope table off
    (`(d1.w,a1)` @ 0x58c88 and `(d0.w,a1,10)` @ 0x58c66). The tick's own value is the default; a
    case that moves it is what shows the register is an argument and not a constant.
    """
    channel = channel_address(channel_index)
    volume_shadow = mod(SND_SHADOW_VOLUME_A + channel_index)
    table = mod(SND_ARP_SEQUENCE_TABLE) if arp_table is None else arp_table
    pokes = silent_channels()
    pokes[channel] = channel_struct(channel_fields)
    entered = channel if entry == MODULE_FRAME_UPDATE else channel - SND_CHANNEL_STRIDE
    glue_name = ("g_channel_frame_update" if entry == MODULE_FRAME_UPDATE
                 else "g_channel_frame_next")

    diffs, info = differential(entry,
                               {"a0": entered, "a1": table,
                                "a2": volume_shadow, "a3": A_SOUND_MODULE, "d0": 0,
                                "_pokes": pokes},
                               lambda lib, buf: getattr(lib, glue_name)(buf, entered,
                                                                       volume_shadow, table),
                               poison=True)
    assert not diffs, report(diffs)
    assert info["ret"] & 0xffff == info["regs"]["d1"] & 0xffff, (
        f"the port answered period {info['ret'] & 0xffff:#06x} where the original answered "
        f"{info['regs']['d1'] & 0xffff:#06x}")


@pytest.mark.parametrize("envelope", (0x00, 0x0f, 0x10, 0x1f, 0xef, ENVELOPE_FINISHED, 0xff))
@pytest.mark.parametrize("instrument", (0, 13))
def test_the_volume_envelope_steps_and_refills(envelope, instrument):
    """One frame off the high nibble, and the BORROW is what fetches the next envelope byte. 0x0f is
    the last byte before the borrow, 0x10 the first after it, and 0xf0 and above are finished."""
    run_frame_update(MODULE_FRAME_UPDATE, 0,
                     {CHAN_ENV_BYTE: envelope, CHAN_INSTRUMENT: instrument, CHAN_ENV_STEP: 1,
                      CHAN_NOTE: NOTE})


@pytest.mark.parametrize("loop_point", (0, 1, 3, 5, 7, 9))
@pytest.mark.parametrize("cursor", (0, 1, 8, 9, 0xff))
def test_the_arpeggio_walks_and_snaps_back(loop_point, cursor):
    """The cursor is read ONE AHEAD and a byte with bit 7 set ends the run: its low seven bits are
    still the offset, and the cursor goes back to the loop point instead of advancing.

    A cursor of 0xff is included because the increment is a BYTE add: it wraps to 0 rather than
    reading the 256th byte of a ten-byte table."""
    run_frame_update(MODULE_FRAME_UPDATE, 0,
                     {CHAN_ARP_LOOP_POINT: loop_point, CHAN_ARP_CURSOR: cursor,
                      CHAN_NOTE: NOTE, CHAN_ENV_BYTE: 0x35})


# How far to move A1 for the case below. Two bytes is enough to change what BOTH lookups read while
# keeping them inside the module, and it is not a multiple of the ten-byte arpeggio table, so no
# cursor value can land back on the byte it would have read.
ARP_TABLE_SHIFT = 2


@pytest.mark.parametrize("cursor", (0, 3, 8))
def test_the_two_tables_are_read_off_the_CALLERS_a1(cursor):
    """CONTRACT COVERAGE, NOT GAME COVERAGE, and ../STATUS.md says so.

    `channel_frame_update` reads its arpeggio sequence as `(d1.w,a1)` @ 0x58c88 and its volume
    envelope as `(d0.w,a1,10)` @ 0x58c66 — both off the A1 its caller loaded, not off the module
    base in A3. The only caller is `sound_vbl_tick`, which always loads `lea $59115(pc),a1`, so the
    register is a constant IN THE GAME and a reconstruction that compiled the two table addresses in
    would agree with every case that runs the tick.

    Moving A1 by two bytes is what separates them: the original then reads two bytes further into
    the module for both tables, and a hardcoded port reads the same bytes it always did.
    """
    run_frame_update(MODULE_FRAME_UPDATE, 0,
                     {CHAN_ARP_LOOP_POINT: 1, CHAN_ARP_CURSOR: cursor,
                      CHAN_NOTE: NOTE, CHAN_ENV_BYTE: 0x0f, CHAN_ENV_STEP: 1},
                     arp_table=mod(SND_ARP_SEQUENCE_TABLE + ARP_TABLE_SHIFT))


@pytest.mark.parametrize("note", (0x00, 0x53, PATTERN_NOISE_NOTE_BASE, 0x7f, 0xff))
@pytest.mark.parametrize("transpose", (0, 12, 0xf4))
def test_the_note_period_index_is_a_byte_multiply(note, transpose):
    """`(note + arpeggio + transpose) * 2` computed as a BYTE, so it wraps into the 84-entry table
    rather than running off it — and where it does run off, into the instructions behind the table,
    an image read is what gets the same word the original does."""
    run_frame_update(MODULE_FRAME_UPDATE, 0,
                     {CHAN_NOTE: note, CHAN_TRANSPOSE: transpose, CHAN_ENV_BYTE: 0x35})


@pytest.mark.parametrize("current", (0, 1, 5, 9, 10, 0xff))
@pytest.mark.parametrize("up", (0, CHAN_FLAG_VIBRATO_UP))
def test_the_vibrato_sweeps_and_turns_round(current, up):
    """It turns at `limit` going up and at ZERO coming down — the two ends are two different tests
    in the original (`cmp.b d2,d0` one way, the subtraction's own Z flag the other)."""
    run_frame_update(MODULE_FRAME_UPDATE, 0,
                     {CHAN_FLAGS: CHAN_FLAG_VIBRATO | up, CHAN_VIBRATO_LIMIT: 10,
                      CHAN_VIBRATO_SPEED: 1, CHAN_VIBRATO_CURRENT: current,
                        CHAN_NOTE: NOTE, CHAN_ENV_BYTE: 0x35})


@pytest.mark.parametrize("delay", (0, 1, 2))
@pytest.mark.parametrize("step", (1, 0xff, 0x80, 0x7f))
def test_the_pitch_slide_waits_then_accumulates(delay, step):
    """The delay counts down first; the accumulator then gains the SIGN-EXTENDED step every frame,
    and it is the accumulator — not the step — that displaces the period."""
    run_frame_update(MODULE_FRAME_UPDATE, 0,
                     {CHAN_FLAGS: CHAN_FLAG_SLIDE, CHAN_SLIDE_DELAY: delay,
                      CHAN_SLIDE_STEP: step, CHAN_SLIDE_ACCUM: 0x0100,
                        CHAN_NOTE: NOTE, CHAN_ENV_BYTE: 0x35})


@pytest.mark.parametrize("flags", (0, CHAN_FLAG_NOISE_ALTERNATE,
                                   CHAN_FLAG_NOISE_ALTERNATE | CHAN_FLAG_FRAME_TOGGLE,
                                   CHAN_FLAG_NOISE_ALTERNATE | CHAN_FLAG_NOISE_ONESHOT,
                                   CHAN_FLAG_NOISE_ALTERNATE | CHAN_FLAG_NOISE_ONESHOT
                                   | CHAN_FLAG_FRAME_TOGGLE))
@pytest.mark.parametrize("out_flags", (0, CHAN_OUT_NOISE_NOTE))
def test_the_out_flags_are_rebuilt_from_the_previous_frames(flags, out_flags):
    """Bit 1 is read out of the PREVIOUS frame's byte and written back, so a noise note sustains;
    bit 0 — the only bit the mixer looks at — is set by that or by the alternating-noise flag on the
    frames the toggle is up, and the one-shot flag cancels the alternation after one of them."""
    run_frame_update(MODULE_FRAME_UPDATE, 0,
                     {CHAN_FLAGS: flags, CHAN_OUT_FLAGS: out_flags, CHAN_NOTE: NOISE_NOTE,
                      CHAN_ENV_BYTE: 0x35})


def test_channel_frame_next_updates_the_following_channel():
    run_frame_update(MODULE_FRAME_NEXT, 1, {CHAN_NOTE: NOTE, CHAN_ENV_BYTE: 0x35})


# ==================================================== the game wrappers


@pytest.mark.parametrize("entry,glue_name", (
    (ENTRY_SFX_PLAY_2, "g_sfx_play_2"),
    (ENTRY_SFX_PLAY_5, "g_sfx_play_5"),
    (ENTRY_SFX_PLAY_6, "g_sfx_play_6"),
    (ENTRY_SFX_PLAY_10, "g_sfx_play_10"),
))
def test_each_sfx_wrapper_starts_its_own_effect(entry, glue_name):
    """Four wrappers, four constants, one module entry. The differential settles WHICH constant:
    the block each one arms comes from a different 18-byte record."""
    diffs, _ = differential(entry, {}, lambda lib, buf: getattr(lib, glue_name)(buf), poison=True)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("tune", (0, 4, 0xbeef03))
def test_music_play_passes_its_word_through(tune):
    """d0.w in, straight to the module's +1256. The high garbage is there because the caller at
    0x125b0 loads a WORD out of `level_tune_id` and the module reads a byte out of it."""
    diffs, _ = differential(ENTRY_MUSIC_PLAY, {"d0": tune},
                            lambda lib, buf: lib.g_music_play(buf, tune), poison=True)
    assert not diffs, report(diffs)


def test_music_stop_clears_the_flag_twice():
    """The wrapper calls the module's stop entry and then clears `music_active` ITSELF — which
    `sound_stop` has already done. Reproduced rather than tidied: it is the original's redundancy,
    and so is the `move.w $1776e,d0` it loads into a register the module ignores."""
    pokes = {mod(SND_MUSIC_ACTIVE): bytes([SCC_TRUE]), mod(SND_SHADOW_VOLUME_A): b"\x0a\x0b\x0c",
             A_LEVEL_TUNE_ID: b"\x00\x02"}
    diffs, _ = differential(ENTRY_MUSIC_STOP, {"_pokes": pokes},
                            lambda lib, buf: lib.g_music_stop(buf), poison=True)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("suspended", (0, 1, 0xffff))
@pytest.mark.parametrize("still_playing", (0, 0xff))
@pytest.mark.parametrize("tune", (1, 3))
def test_music_restart_if_stopped_across_both_guards(suspended, still_playing, tune):
    """Both guards, both ways: the stage's suspend word and the module's own `music_active`. This
    is the game's whole use of "the tune has finished", and its only reader of that byte."""
    pokes = {A_MUSIC_SUSPEND_FLAG: suspended.to_bytes(2, "big"),
             A_LEVEL_TUNE_ID: tune.to_bytes(2, "big"),
             mod(SND_MUSIC_ACTIVE): bytes([still_playing])}
    diffs, _ = differential(ENTRY_MUSIC_RESTART_IF_STOPPED, {"_pokes": pokes},
                            lambda lib, buf: lib.g_music_restart_if_stopped(buf), poison=True)
    assert not diffs, report(diffs)


# ==================================================== fuzz
#
# Sharded by `chunk` so `-n auto` spreads it (README.md, "Adding a function", step 4). Every case
# starts from a REAL `music_start` or `sfx_start` rather than from random bytes, and perturbs the
# MODULATION state on top of it: a random pattern offset would point the sequencer at arbitrary
# bytes, and the shipped data is what decides which of the module's unbounded indices are reachable
# at all (`include/sound.h`). What is randomised is everything a running track's own data can move.


# Tune 4's channel-A list has NO 0x0000 before channel B's begins — it is a one-shot jingle that
# ends with pattern command 0x88 instead (../notes/sound_engine.md) — so a walk of a sequence list
# needs a cap as well as a terminator, and this is comfortably past the longest real list.
SEQ_LIST_MAX_ENTRIES = 64


def sequence_list_patterns(image, list_offset):
    """The pattern offsets in one sequence list, as far as its terminator or the cap."""
    patterns, cursor = [], list_offset
    while len(patterns) < SEQ_LIST_MAX_ENTRIES:
        pattern = module_word(image, cursor)
        if pattern == 0:
            break
        patterns.append(pattern)
        cursor += SEQ_LIST_ENTRY_BYTES
    return patterns


def _random_running_channel(rng, image, tune, index):
    """One channel struct as a running tune could plausibly have left it.

    The two ADDRESS fields come from the tune's own record — a random pattern offset would point
    the sequencer at arbitrary bytes, and it is the shipped data that decides which of the module's
    unbounded indices are reachable at all (`include/sound.h`). Everything else is random over its
    whole byte range, which is exactly the modulation state a real track walks through.
    """
    record = tune_record(image, tune)
    at = TUNE_SEQ_LIST + index * SEQ_LIST_ENTRY_BYTES
    list_offset = int.from_bytes(record[at:at + SEQ_LIST_ENTRY_BYTES], "big")
    patterns = sequence_list_patterns(image, list_offset)
    which = rng.randrange(len(patterns))
    return channel_struct({
        CHAN_FLAGS: rng.randrange(0x100),
        CHAN_SEQ_CURSOR: (which + 1) * SEQ_LIST_ENTRY_BYTES,
        CHAN_PATTERN_OFFSET: patterns[which],
        CHAN_SEQ_LIST_OFFSET: list_offset,
        CHAN_SLIDE_STEP: rng.randrange(0x100),
        CHAN_SLIDE_DELAY: rng.randrange(4),
        CHAN_SLIDE_ACCUM: rng.randrange(0x10000),
        CHAN_DURATION: rng.randrange(1, 8),
        CHAN_NOTE_LENGTH: rng.randrange(1, 0x20),
        CHAN_NOTE: rng.randrange(0x100),
        CHAN_ENV_STEP: rng.randrange(0x20),
        CHAN_ENV_BYTE: rng.randrange(0x100),
        CHAN_INSTRUMENT: rng.randrange(14),
        CHAN_VIBRATO_LIMIT: rng.randrange(0x100),
        CHAN_VIBRATO_SPEED: rng.randrange(1, 8),
        CHAN_VIBRATO_CURRENT: rng.randrange(0x100),
        CHAN_TRANSPOSE: rng.randrange(0x100),
        CHAN_OUT_FLAGS: rng.randrange(4),
        CHAN_ARP_LOOP_POINT: rng.randrange(10),
        CHAN_ARP_CURSOR: rng.randrange(0x100),
    })


def _modulation_pokes(rng):
    """Random values for the state `music_start` does NOT re-seed, so it survives the arming.

    `music_start` writes the duration, the flag byte, the sequence cursor, the transpose and the two
    offsets of every channel; a poke to one of those in front of it would be overwritten and the
    case would be quietly narrower than it reads. What is left — the envelope, the instrument, the
    vibrato and slide machines, the arpeggio cursor, and the module's own volume and noise bytes —
    is what a track walks through frame by frame, and is randomised here.
    """
    pokes = {}
    for index in range(SND_CHANNELS):
        at = channel_address(index)
        pokes.update({
            at + CHAN_SLIDE_STEP: bytes([rng.randrange(0x100), rng.randrange(4)]),
            at + CHAN_SLIDE_ACCUM: rng.randrange(0x10000).to_bytes(2, "big"),
            at + CHAN_ENV_STEP: bytes([rng.randrange(0x20), rng.randrange(0x100),
                                       rng.randrange(14)]),
            at + CHAN_VIBRATO_LIMIT: bytes([rng.randrange(0x100), rng.randrange(1, 8),
                                            rng.randrange(0x100)]),
            at + CHAN_ARP_LOOP_POINT: bytes([rng.randrange(10), rng.randrange(0x100)]),
        })
    pokes[mod(SND_MASTER_VOLUME)] = bytes([rng.choice((0x0f, 0x0f, 0x0e, 0x0a, 0x00))])
    pokes[mod(SND_NOISE_PERIOD_DEFAULT)] = bytes([rng.randrange(0x20), rng.randrange(0x20)])
    pokes[mod(SND_VBL_50HZ_DIVIDER)] = bytes([rng.randrange(0x100)])
    return pokes


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz_a_perturbed_tune(chunk):
    """A real tune, a random number of frames, a random machine speed, and the modulation state
    knocked about before the arming."""
    rng = random.Random(0x51a12 + chunk)
    for _case in range(FUZZ_CASES_PER_CHUNK):
        tune = rng.randrange(SND_TUNES)
        frames = rng.randrange(1, 24)
        sync = rng.choice(BOTH_MACHINES)
        diffs, _ = run_ticks(frames, before=[(MODULE_MUSIC_START, tune)], sync=sync,
                             extra_pokes=_modulation_pokes(rng))
        assert not diffs, f"tune {tune}, {frames} frames, sync {sync:#04x}: {report(diffs)}"


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz_an_effect_over_a_tune(chunk):
    """An effect started at a random frame of a random tune, at a random machine speed — the shape
    the game itself makes, since every wrapper is called between two of the VBL handler's ticks."""
    rng = random.Random(0x0eff0 + chunk)
    for _case in range(FUZZ_CASES_PER_CHUNK):
        tune = rng.randrange(SND_TUNES)
        effect = rng.randrange(SND_EFFECTS)
        before_frames = rng.randrange(0, 20)
        after_frames = rng.randrange(1, 24)
        sync = rng.choice(BOTH_MACHINES)
        steps = ([(MODULE_MUSIC_START, tune)] + [(MODULE_VBL_TICK, 0)] * before_frames
                 + [(MODULE_SFX_START, effect)])
        diffs, _ = run_ticks(after_frames, before=steps, sync=sync)
        assert not diffs, (f"tune {tune} + effect {effect} at frame {before_frames}, "
                           f"{after_frames} after, sync {sync:#04x}: {report(diffs)}")


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz_one_tick_from_a_random_driver_state(chunk, post_load_image):
    """ONE tick entered on a wholly randomised driver: every byte of the variable block, and three
    channel structs whose two address fields come from a real tune and whose other twenty-two
    bytes do not.

    The narrowest shape there is, and the one that reaches states no sequence of ticks from a clean
    start would: a random `music_active`/`sfx_active` pair, a tempo counter about to fire, an
    envelope mid-refill, an arpeggio cursor past the end of its table, a sound effect with both of
    its counters live. Nothing in the variable block is used as an ADDRESS — every byte of it is a
    period, a level, a countdown or a bit pattern — which is what makes randomising all of it safe.
    """
    rng = random.Random(0x71c4 + chunk)
    for _case in range(FUZZ_CASES_PER_CHUNK):
        tune = rng.randrange(SND_TUNES)
        pokes = {mod(0): bytes(rng.randrange(0x100) for _ in range(SND_VARIABLE_BLOCK_BYTES))}
        # ...bar the tempo counter, which is left small so that the sequencer really does run on
        # some of these frames rather than one time in 256.
        pokes[mod(SND_MUSIC_TEMPO_COUNTER)] = bytes([rng.randrange(1, 4)])
        pokes[mod(SND_MUSIC_ACTIVE)] = bytes([rng.choice((0, SCC_TRUE))])
        pokes[mod(SND_SFX_ACTIVE)] = bytes([rng.choice((0, SCC_TRUE))])
        for index in range(SND_CHANNELS):
            pokes[channel_address(index)] = _random_running_channel(rng, post_load_image,
                                                                   tune, index)
        diffs, _ = run_ticks(1, sync=rng.choice(BOTH_MACHINES), extra_pokes=pokes)
        assert not diffs, report(diffs)


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_SOUND_MODULE", "include/globals.h", "A_sound_module"),
    ("SOUND_MODULE_OVER_ARENA_BYTES", "include/globals.h", "MODULE_OVER_ARENA_BYTES"),
    ("A_ENTITY_ARENA", "include/globals.h", "A_entity_arena"),
    ("A_MUSIC_SUSPEND_FLAG", "include/sound.h", "A_music_suspend_flag"),
    ("A_LEVEL_TUNE_ID", "include/sound.h", "A_level_tune_id"),
    "SND_ENTRY_VBL_TICK",
    "SND_ENTRY_STOP",
    "SND_ENTRY_SFX_START",
    "SND_ENTRY_MUSIC_START",
    "SND_SHADOW_PERIOD_A",
    "SND_SHADOW_PERIOD_B",
    "SND_SHADOW_PERIOD_C",
    "SND_SHADOW_PERIOD_BYTES",
    "SND_SHADOW_NOISE_PERIOD",
    "SND_SHADOW_VOLUME_A",
    "SND_SHADOW_ENV_PERIOD",
    "SND_SHADOW_ENV_SHAPE",
    "SND_SHADOW_BYTES",
    "SND_SFX_DURATION",
    "SND_SFX_PERIOD_DELTA",
    "SND_SFX_PERIOD_RESET",
    "SND_SFX_ALT_DELTA",
    "SND_SFX_PERIOD_CURRENT",
    "SND_SFX_RESET_RELOAD",
    "SND_SFX_ALT_RELOAD",
    "SND_SFX_ALT_PATTERN",
    "SND_SFX_NOISE_PATTERN",
    "SND_SFX_RESET_COUNTER",
    "SND_SFX_ALT_COUNTER",
    "SND_MUSIC_ACTIVE",
    "SND_SFX_ACTIVE",
    ("SCC_TRUE", "include/common.h", "SCC_TRUE"),
    "SND_VBL_50HZ_DIVIDER",
    "SND_MUSIC_TEMPO_RELOAD",
    "SND_MUSIC_TEMPO_COUNTER",
    "SND_NOISE_PERIOD_DEFAULT",
    "SND_NOISE_PERIOD_ALT",
    "SND_MASTER_VOLUME",
    "SND_VARIABLE_BLOCK_BYTES",
    "SND_SEQ_COMMAND_TABLE",
    "SND_ARP_LOOP_POINT_TABLE",
    "SND_INSTRUMENT_ENV_OFFSETS",
    "SND_NOTE_PERIOD_TABLE",
    "SND_TUNE_TABLE",
    "SND_CHANNEL_A",
    "SND_ARP_SEQUENCE_TABLE",
    "SND_VOLUME_ENVELOPE_TABLE",
    "SND_SFX_TABLE",
    "SND_TUNES",
    "SND_EFFECTS",
    "SND_CHANNELS",
    "SND_CHANNEL_STRIDE",
    "TUNE_RECORD_BYTES",
    "TUNE_TEMPO",
    "TUNE_SEQ_LIST",
    "SEQ_LIST_ENTRY_BYTES",
    "SFX_RECORD_BYTES",
    "SFX_COPIED_WORDS",
    "SFX_ENV_PERIOD_WORD",
    "SFX_ENV_SHAPE_WORD",
    "CHAN_FLAGS",
    "CHAN_SEQ_CURSOR",
    "CHAN_PATTERN_OFFSET",
    "CHAN_SEQ_LIST_OFFSET",
    "CHAN_SLIDE_STEP",
    "CHAN_SLIDE_DELAY",
    "CHAN_SLIDE_ACCUM",
    "CHAN_DURATION",
    "CHAN_NOTE_LENGTH",
    "CHAN_NOTE",
    "CHAN_NOTE_TIED",
    "CHAN_NOTE_TIED_BIT",
    "CHAN_ENV_STEP",
    "CHAN_ENV_BYTE",
    "CHAN_INSTRUMENT",
    "CHAN_VIBRATO_LIMIT",
    "CHAN_VIBRATO_SPEED",
    "CHAN_VIBRATO_CURRENT",
    "CHAN_TRANSPOSE",
    "CHAN_OUT_FLAGS",
    "CHAN_ARP_LOOP_POINT",
    "CHAN_ARP_CURSOR",
    "CHAN_FLAG_FRAME_TOGGLE",
    "CHAN_FLAG_NOISE_ALTERNATE",
    "CHAN_FLAG_NOISE_ONESHOT",
    "CHAN_FLAG_SLIDE",
    "CHAN_FLAG_VIBRATO",
    "CHAN_FLAG_VIBRATO_UP",
    "CHAN_FLAG_PORTAMENTO",
    "CHAN_FLAG_PORTAMENTO_DOWN",
    "CHAN_OUT_NOISE",
    "CHAN_OUT_NOISE_NOTE",
    "PATTERN_NOISE_NOTE_BASE",
    "PATTERN_COMMAND_BASE",
    "PATTERN_ARP_LOOP_BASE",
    "PATTERN_INSTRUMENT_BASE",
    "PATTERN_NOTE_LENGTH_BASE",
    "ENVELOPE_FINISHED",
    "ENVELOPE_FRAME_STEP",
    "PSG_REG_MIXER",
    "PSG_REG_ENV_SHAPE",
    "PSG_MIXER_TONES_ON",
    "PSG_VOLUME_ENVELOPE_MODE",
    "SHIFTER_SYNC_50HZ",
    "VBL_50HZ_DIVIDER_RELOAD",
    "SFX_PLAY_2_NUMBER",
    "SFX_PLAY_5_NUMBER",
    "SFX_PLAY_6_NUMBER",
    "SFX_PLAY_10_NUMBER",
)
ENTRY_PROLOGUES = {
    "ENTRY_SFX_PLAY_6": "48e7fffe41f900058944303c00064ea8",
    "ENTRY_SFX_PLAY_10": "48e7fffe41f900058944303c000a4ea8",
    "ENTRY_SFX_PLAY_5": "48e7fffe41f900058944303c00054ea8",
    "ENTRY_SFX_PLAY_2": "48e7fffe41f900058944303c00024ea8",
    "ENTRY_MUSIC_PLAY": "48e7fffe41f9000589444ea8",
    "ENTRY_MUSIC_STOP": "48e7fffe41f90005894430390001776e",
    "ENTRY_MUSIC_RESTART_IF_STOPPED": "4a79000176a4661641f90005",
}
