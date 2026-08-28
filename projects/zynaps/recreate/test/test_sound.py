"""Differential tests for the YM2149 driver (src/sound.c).

Three shapes of case, and the third is the one that matters most:

* the two table lookups answer in REGISTERS and touch no memory, so they run through the `jsr`+store
  stub in test/abi.py;
* the rest write the register shadow and the voice records, which are in the text segment and so
  fully diffed;
* `sound_tick` and `sound_reset_psg` also write $ff8800/$ff8802, which is OUTSIDE the image — the
  kit's direct-PSG ledger is what compares those (TRAP_MODEL.md, Phase 6), and `differential`
  compares it on every case whether or not the case asked. `test_music_frames` drives the real
  in-game tune for tens of frames as ONE oracle run, so the ledger it compares is the whole
  multi-frame register stream in order.
"""
import ctypes
import random

import pytest

import abi
import harness
from harness import differential, hi_garbage, report

ENTRY_SOUND_START = 0x16ac8
ENTRY_SOUND_RESET_PSG = 0x16b4e
ENTRY_SOUND_TICK = 0x16b94
ENTRY_SOUND_VOICE_TICK = 0x16bd6
ENTRY_SOUND_VOICE_NEXT_ROW = 0x16bf0
ENTRY_SOUND_LOOKUP_TUNE = 0x16b32
ENTRY_SOUND_LOOKUP_MODTABLE = 0x16cec
ENTRY_SOUND_VOICE_MODULATE = 0x16da6
ENTRY_SOUND_SET_NOTE_PERIOD = 0x16e04
ENTRY_SOUND_NOISE_MODULATE = 0x16e28
ENTRY_SOUND_MODTABLE_STEP_A4 = 0x16e48
ENTRY_SOUND_MODTABLE_STEP = 0x16e4a

A_TUNE_INDEX = 0x17058   # mirror of include/sound.h
A_TUNE_DATA = 0x171e8
A_MOD_TABLE_INDEX = 0x17008
A_MOD_TABLE_DATA = 0x170b2
A_NOTE_PERIOD_TBL = 0x16f40
A_PSG_REG_SHADOW = 0x16e82
A_SFX_VOICE_TOGGLE = 0x16e90
A_SOUND_NOISE_BLOCK = 0x16e92
A_SOUND_VOICE1 = 0x16eaa
A_SOUND_VOICE2 = 0x16edc
A_SOUND_VOICE3 = 0x16f0e
VOICE_STRIDE = 0x32
VOICE_MOD_VOLUME_CURSOR = 0x04
VOICE_MOD_PITCH_CURSOR = 0x08
VOICE_MOD_VOLUME_RESTART = 0x10
VOICE_MOD_PITCH_RESTART = 0x14
VOICE_ENABLE = 0x18
VOICE_NOTE_COUNTDOWN = 0x19
VOICE_STREAM = 0x1a
VOICE_STREAM_LOOP = 0x1e
VOICE_STREAM_RESTART = 0x22
VOICE_ARPEGGIO = 0x2e
VOICE_NOTE = 0x2f
VOICE_ARPEGGIO_PHASE = 0x30
PSG_VOICE_PERIOD_BYTES = 2
PSG_SHADOW_REGS = 14
PSG_TICK_FLUSH_REGS = 11
SOUND_ROW_BYTES = 2
SOUND_STREAM_CHANNEL_TAG = 0xfa
SOUND_CHANNEL_ALTERNATE = 4
MOD_STEP_BYTES = 3
MOD_STEP_PERIOD = 0
MOD_STEP_REPEATS = 2
MOD_RECORD_END = 0xff
VOICE_MOD_TEMPLATE = 0x0c
VOICE_MOD_TEMPLATE_BYTES = 12

# The header a stream that wants the alternating voice opens with.
ALTERNATE_CHANNEL_HEADER = bytes([SOUND_STREAM_CHANNEL_TAG, SOUND_CHANNEL_ALTERNATE])

VOICE_PERIOD_SHADOW = {
    A_SOUND_VOICE1: A_PSG_REG_SHADOW + 0 * PSG_VOICE_PERIOD_BYTES,
    A_SOUND_VOICE2: A_PSG_REG_SHADOW + 1 * PSG_VOICE_PERIOD_BYTES,
    A_SOUND_VOICE3: A_PSG_REG_SHADOW + 2 * PSG_VOICE_PERIOD_BYTES,
}

# The first sound number whose table word has bit 15 set (0x80c8), and so the first that resolves
# BELOW A_TUNE_DATA once `adda.w` sign-extends it. Measured off the image, not inferred: the offsets
# are NOT ascending up to here — they climb from 0x019a to 0x04d2 over numbers 0..10, drop back at
# 11/12/13 (0x0006, 0x0081, 0x0107), then climb again. names.txt reads the real table as 45 entries,
# which is why this is also where the data ends; the two facts coincide but are not the same claim.
TUNE_FIRST_NEGATIVE_OFFSET = 45
TUNE_BOOT_NUMBER = 0x0b      # what `_start` fires at 0x1007c (`moveq #$b,d1`)
TUNE_COUNT = 45              # names.txt: the index has 45 real entries

FUZZ_CHUNKS = 4

for _name, _extra in (("g_sound_lookup_tune", 2), ("g_sound_lookup_modtable", 2),
                      ("g_sound_start", 2), ("g_sound_set_note_period", 2),
                      ("g_sound_modtable_step", 4), ("g_sound_modtable_step_a4", 3),
                      ("g_sound_noise_modulate", 0), ("g_sound_voice_modulate", 2),
                      ("g_sound_voice_next_row", 2), ("g_sound_voice_tick", 2),
                      ("g_sound_reset_psg", 0), ("g_sound_tick", 0)):
    getattr(harness._lib, _name).argtypes = ([ctypes.POINTER(ctypes.c_uint8)]
                                             + [ctypes.c_uint32] * _extra)
    getattr(harness._lib, _name).restype = None


def _image_bytes(addr, length):
    return bytes(harness.BASE_IMAGE[addr:addr + length])


def tune_stream(number, skip_header=True):
    """Where sound_lookup_tune resolves `number` to, read the same little-endian way the game does.

    With `skip_header`, past the two-byte `fa <chan>` opener when the stream has one — which is
    where sound_start leaves the cursor, and so where a row-fetch case has to start. Public because
    test_irq.py arms a voice on a real tune too.
    """
    entry = A_TUNE_INDEX + 2 * number
    stream = A_TUNE_DATA + int.from_bytes(_image_bytes(entry, 2), "little")
    if skip_header and harness.BASE_IMAGE[stream] == SOUND_STREAM_CHANNEL_TAG:
        stream += SOUND_ROW_BYTES
    return stream


# =================================================================================================
# The two table lookups — 0x16b32 and 0x16cec
# =================================================================================================

# The routines write no memory at all — their answers are a pointer and the offset it was built
# from — so a stub stores them where the image diff can see them. THE TWO NEED DIFFERENT STUBS, and
# that difference is itself a fact about them: the tune lookup answers in A1, so the store-through-
# A0 stub serves it, while the modulation lookup answers in A0 and would overwrite that stub's own
# cursor — it takes the `movem.l` one, whose order is the instruction's (D0..D7 then A0..A6).
# (glue, stub builder, the registers it stores, and the extra input registers the stub needs). The
# STUB IS NAMED HERE rather than derived from the register list inside the helper — a helper that
# branched on which tuple it was handed would silently pick the wrong ABI for an equal-but-fresh
# tuple, and picking the wrong ABI is a case that passes while testing something else.
LOOKUPS = {
    "tune": ("g_sound_lookup_tune", abi.register_call_pokes, ("a1", "d1"), {"a0": abi.RESULT}),
    "modtable": ("g_sound_lookup_modtable", abi.register_dump_pokes, ("d1", "a0"), {}),
}
LOOKUP_ENTRY = {"tune": ENTRY_SOUND_LOOKUP_TUNE, "modtable": ENTRY_SOUND_LOOKUP_MODTABLE}


def _lookup_case(which, number, poison=False):
    glue_name, build_pokes, stores, extra_regs = LOOKUPS[which]
    pokes = build_pokes(LOOKUP_ENTRY[which], stores)
    pokes[abi.RESULT] = bytes(range(0x61, 0x69))     # neither answer, so silence shows up
    regs = {"d1": number, "_pokes": pokes, **extra_regs}
    diffs, _ = differential(abi.STUB, regs,
                            lambda lib, buf: getattr(lib, glue_name)(buf, number, abi.RESULT),
                            poison=poison)
    assert not diffs, f"{glue_name} number={number:#x}\n{report(diffs)}"


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_every_tune_number(chunk):
    """All 256 values `andi.w #$ff,d1` can leave — the routine's whole input range.

    Exhaustive rather than sampled because the table is not uniform: names.txt reads 45 real
    entries, and past those the bytes are tune data being read as offsets, 52 of them with bit 15
    set. Those are what exercise `adda.w`'s SIGN EXTENSION — number 45 resolves to 0xf2b0, below the
    load base — so dropping `sign_ext16` from the reconstruction turns this test red there.

    Sharded four ways so no single item gates the wall clock; every chunk walks the same range and
    takes its own quarter, so coverage is byte-identical to one 256-case loop.
    """
    assert TUNE_BOOT_NUMBER < 0x100, "the boot tune must be inside the range this test walks"
    for number in range(chunk, 0x100, FUZZ_CHUNKS):
        _lookup_case("tune", number)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_every_modtable_number(chunk):
    """The same sweep over the modulation index, whose 31 real entries are followed by the same
    kind of over-read. A SEPARATE battery rather than a parametrized one because the two routines
    answer in different registers — A0 here against A1 there — and the stub's store order is what
    proves which."""
    for number in range(chunk, 0x100, FUZZ_CHUNKS):
        _lookup_case("modtable", number)


def test_only_the_low_byte_indexes():
    """`andi.w #$ff,d1` masks to a byte, and nothing else ever reads the rest of D1 — so a number
    with junk above its low byte must resolve to the same entry, and D1's HIGH WORD must come back
    untouched (every step of the routine is a word or byte operation)."""
    rng = random.Random(ENTRY_SOUND_LOOKUP_TUNE)
    for low in (0, 1, TUNE_BOOT_NUMBER, 0xff,
                TUNE_FIRST_NEGATIVE_OFFSET - 1, TUNE_FIRST_NEGATIVE_OFFSET):
        _lookup_case("tune", hi_garbage(rng, low))
        _lookup_case("tune", low | 0xff00)
        _lookup_case("modtable", hi_garbage(rng, low))


@pytest.mark.parametrize("number", (0, TUNE_BOOT_NUMBER, TUNE_FIRST_NEGATIVE_OFFSET, 0xff))
def test_lookup_attribution(number):
    """Poison both result longwords: a candidate that stores only one of them stays canary."""
    _lookup_case("tune", number, poison=True)
    _lookup_case("modtable", number, poison=True)


# =================================================================================================
# sound_start @ 0x16ac8
# =================================================================================================

def _start_case(number, channel, pokes=None, poison=False):
    regs = {"d1": number, "d0": channel, "_pokes": dict(pokes or {})}
    diffs, _ = differential(ENTRY_SOUND_START, regs,
                            lambda lib, buf: lib.g_sound_start(buf, number, channel),
                            poison=poison)
    assert not diffs, f"number={number:#x} channel={channel:#x}\n{report(diffs)}"


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_sound_start_every_number(chunk):
    """All 256 sound numbers, with D0 held at a value no channel code names.

    Past the 45 real tunes the stream pointer lands in the tune DATA (and, for the 52 numbers whose
    word has bit 15 set, below the tables entirely) — the routine reads a byte there and arms a
    voice with it either way, which is what this drives. The channel is 3 so that a stream WITHOUT a
    0xfa header falls to voice 3 and one with a header overrides it, making the two visible apart.
    """
    for number in range(chunk, 0x100, FUZZ_CHUNKS):
        _start_case(number, 3)


@pytest.mark.parametrize("channel", (0, 1, 2, 3, 4, 5, 0xff))
def test_sound_start_channel_comes_from_d0_without_a_header(channel):
    """A stream that does NOT open with 0xfa is armed on whatever D0 held.

    Every channel code is swept because the selection is two equality tests and a fall-through: 1
    and 2 name voices 1 and 2 and EVERYTHING else — 0, 3, 5, 0xff — is voice 3.
    """
    headerless = [n for n in range(TUNE_COUNT)
                  if harness.BASE_IMAGE[tune_stream(n, skip_header=False)]
                  != SOUND_STREAM_CHANNEL_TAG]
    assert headerless, "no shipped tune lacks the 0xfa header — the D0 arm would be untested"
    _start_case(headerless[0], channel)


@pytest.mark.parametrize("toggle", (0, 1, 2, 3, 0xff))
def test_sound_start_alternate_channel_toggles(toggle):
    """Channel code 4 flips the round-robin byte and uses its NEW value as the channel.

    Driven from a shipped tune whose own header is `fa 04` (17 of the 45 are), with the toggle byte
    poked to each value it can hold. The shipped byte is 2, not 0 or 1 — so the round robin runs
    3, 2, 3, 2 rather than the 1, 3 names.txt's comment on 0x16e90 describes; both readings are
    driven here and the diff is what says which the machine does.
    """
    alternating = [n for n in range(TUNE_COUNT)
                   if bytes(harness.BASE_IMAGE[tune_stream(n, skip_header=False):]
                            [:SOUND_ROW_BYTES]) == ALTERNATE_CHANNEL_HEADER]
    assert alternating, "no shipped tune uses channel code 4 — the toggle arm would be untested"
    _start_case(alternating[0], 0, pokes={A_SFX_VOICE_TOGGLE: bytes([toggle])})


@pytest.mark.parametrize("number", (TUNE_BOOT_NUMBER, 0x11, 0x2c))
def test_sound_start_attribution(number):
    """Poison every byte the arm writes: a candidate that skips one of the three stream pointers,
    or leaves the enable byte alone, stays canary on it."""
    _start_case(number, 1, poison=True)


def test_sound_start_ignores_the_high_bits_of_its_arguments():
    """D1's number is masked to a byte by the lookup and D0's channel is only ever compared as
    one."""
    rng = random.Random(ENTRY_SOUND_START)
    dirty_number = hi_garbage(rng, TUNE_BOOT_NUMBER | 0xff00)
    dirty_channel = hi_garbage(rng, 1 | 0xff00)
    _start_case(dirty_number, dirty_channel)


# =================================================================================================
# sound_set_note_period @ 0x16e04
# =================================================================================================

NOTE_COUNT = 100    # names.txt on 0x16f40: 100 little-endian words, chromatic


def _period_case(note, period_shadow, poison=False):
    regs = {"d0": note, "a5": period_shadow, "_pokes": {}}
    diffs, _ = differential(
        ENTRY_SOUND_SET_NOTE_PERIOD, regs,
        lambda lib, buf: lib.g_sound_set_note_period(buf, note, period_shadow), poison=poison)
    assert not diffs, f"note={note:#x} shadow={period_shadow:#x}\n{report(diffs)}"


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_every_note_period(chunk):
    """All 256 note numbers the byte mask admits, into voice 1's period pair.

    The table holds 100 real notes, so numbers 100..255 read the data behind it — which is the
    modulation index — as periods. Both are driven: the mask is the routine's only bound.
    """
    for note in range(chunk, 0x100, FUZZ_CHUNKS):
        _period_case(note, VOICE_PERIOD_SHADOW[A_SOUND_VOICE1])


@pytest.mark.parametrize("voice", (A_SOUND_VOICE1, A_SOUND_VOICE2, A_SOUND_VOICE3))
def test_note_period_reaches_every_voice_pair(voice):
    """Each voice's pair is two bytes further into the shadow, and the write is LOW byte first —
    a big-endian store would put the doubled period's halves the wrong way round in the two
    registers the chip reads them from."""
    for note in (0, 1, NOTE_COUNT - 1, NOTE_COUNT, 0xff):
        _period_case(note, VOICE_PERIOD_SHADOW[voice])


def test_note_period_attribution():
    """Poison both bytes: a candidate writing only the fine byte stays canary on the coarse one."""
    _period_case(0x21, VOICE_PERIOD_SHADOW[A_SOUND_VOICE1], poison=True)


# =================================================================================================
# sound_modtable_step @ 0x16e4a / _a4 @ 0x16e48, and sound_noise_modulate @ 0x16e28
# =================================================================================================

_STEP_STORES = ("d1",)
_STEP_D1_GARBAGE = 0xfeed0000     # only D1's low BYTE is written, so the rest must come back


def _modtable_record(image_pokes, record, cursor, restart, counters=(0, 0)):
    """Lay a modulation machine's live state over `record`: two counters, a cursor and a restart."""
    block = bytearray(_image_bytes(record, 0x18))
    block[0:2] = bytes(counters)
    block[VOICE_MOD_VOLUME_CURSOR:VOICE_MOD_VOLUME_CURSOR + 4] = cursor.to_bytes(4, "big")
    block[VOICE_MOD_VOLUME_RESTART:VOICE_MOD_VOLUME_RESTART + 4] = restart.to_bytes(4, "big")
    image_pokes[record] = bytes(block)
    return image_pokes


def _mod_record_address(number):
    entry = A_MOD_TABLE_INDEX + 2 * number
    return A_MOD_TABLE_DATA + int.from_bytes(_image_bytes(entry, 2), "little")


# Modulation tables the shipped tunes actually name (the operands of their 0xe8 / 0xe9 / 0xea rows).
SHIPPED_MOD_TABLES = (0x00, 0x05, 0x08, 0x0b, 0x0d, 0x1d)


# The two entries, each with its own glue signature. Keyed rather than switched on inside the
# helper: a helper that compared the glue's NAME would silently call the A4 entry with the other
# one's argument list the day a function is renamed.
STEP_ENTRIES = {
    "a4": (ENTRY_SOUND_MODTABLE_STEP_A4,
           lambda lib, buf, counters, record: lib.g_sound_modtable_step_a4(
               buf, record, _STEP_D1_GARBAGE, abi.RESULT)),
    "split": (ENTRY_SOUND_MODTABLE_STEP,
              lambda lib, buf, counters, record: lib.g_sound_modtable_step(
                  buf, counters, record, _STEP_D1_GARBAGE, abi.RESULT)),
}


def _step_case(which, counters, record, cursor, restart, counter_bytes, poison=False):
    entry, call_glue = STEP_ENTRIES[which]
    pokes = abi.register_dump_pokes(entry, _STEP_STORES)
    pokes[abi.RESULT] = bytes(range(0x81, 0x85))
    _modtable_record(pokes, record, cursor, restart, counter_bytes)
    regs = {"a0": counters, "a4": record, "d1": _STEP_D1_GARBAGE, "_pokes": pokes}
    diffs, _ = differential(abi.STUB, regs,
                            lambda lib, buf: call_glue(lib, buf, counters, record), poison=poison)
    assert not diffs, (f"{which} record={record:#x} cursor={cursor:#x} "
                       f"counters={counter_bytes}\n{report(diffs)}")


def _step_boundary_counters(start):
    """The first-counter values that pick a different arm of the routine, for the record at `start`.

    THE PERIOD BYTE IS THE ONLY INTERESTING VALUE and everything below it is the same early return,
    which matters because one shipped record's period is 200 — walking 0..period would put 202
    differential runs in ONE unsharded pytest item, 201 of them identical, and this file's other
    exhaustive batteries are all sharded precisely so no single item gates the wall clock.
    """
    period = harness.BASE_IMAGE[start + MOD_STEP_PERIOD]
    return sorted({0, 1, (period - 2) & 0xff, (period - 1) & 0xff, period, (period + 1) & 0xff})


@pytest.mark.parametrize("table", SHIPPED_MOD_TABLES)
def test_modtable_step_over_a_shipped_record(table):
    """Walk a real modulation record at each counter value that changes the routine's answer.

    The counter pair is what decides which of the routine's three exits a call takes — neutral,
    delta-only, or delta-plus-cursor-step — so the boundary either side of the record's own period
    byte is driven, plus 0 and 1. Real data: the record is whichever one a shipped tune names.
    """
    record = A_SOUND_VOICE1
    start = _mod_record_address(table)
    for counter in _step_boundary_counters(start):
        _step_case("a4", record, record, start, start, (counter, 0))


@pytest.mark.parametrize("second", (0, 1, 0x7f, 0xfe, 0xff))
def test_modtable_step_second_counter(second):
    """Once the first period elapses the SECOND counter decides whether the cursor steps on — and a
    step whose fourth byte is 0xff restarts the record from the restart pointer instead."""
    record = A_SOUND_VOICE1
    start = _mod_record_address(SHIPPED_MOD_TABLES[2])
    period = harness.BASE_IMAGE[start + MOD_STEP_PERIOD]
    _step_case("a4", record, record, start, start, ((period - 1) & 0xff, second))


def test_modtable_step_separate_counter_pointer():
    """The 0x16e4a entry takes its counters SEPARATELY from the record, which is how one routine
    serves both the volume machine (counters at the record's base) and the pitch machine (two bytes
    along) — the same call with the two pointers equal and unequal must touch different bytes."""
    record = A_SOUND_VOICE1
    start = _mod_record_address(SHIPPED_MOD_TABLES[2])
    period = harness.BASE_IMAGE[start + MOD_STEP_PERIOD]
    for counters in (record, record + 2):
        for counter in (0, (period - 1) & 0xff):
            _step_case("split", counters, record, start, start, (counter, 0))


# How far the search below will walk before giving up; the shipped records are a few steps long, and
# a record with no terminator would otherwise walk out of the table.
MOD_RECORD_SEARCH_LIMIT = 0x60


def test_modtable_step_restart_pointer_is_followed():
    """A record ending in 0xff jumps to the restart pointer — pointed at a DIFFERENT table here, so
    a candidate that restarted the record in place would write the wrong cursor."""
    record = A_SOUND_VOICE1
    start = _mod_record_address(SHIPPED_MOD_TABLES[0])
    restart = _mod_record_address(SHIPPED_MOD_TABLES[4])
    # Walk to the last step of the record, where the byte after it is the 0xff terminator.
    cursor = start
    while (harness.BASE_IMAGE[cursor + MOD_STEP_BYTES] != MOD_RECORD_END
           and cursor < start + MOD_RECORD_SEARCH_LIMIT):
        cursor += MOD_STEP_BYTES
    assert harness.BASE_IMAGE[cursor + MOD_STEP_BYTES] == MOD_RECORD_END, (
        f"the record at {start:#x} has no 0xff terminator inside "
        f"{MOD_RECORD_SEARCH_LIMIT} bytes — this case would drive the wrong arm")
    _step_case("a4", record, record, cursor, restart,
               ((harness.BASE_IMAGE[cursor + MOD_STEP_PERIOD] - 1) & 0xff,
                (harness.BASE_IMAGE[cursor + MOD_STEP_REPEATS] - 1) & 0xff))


# NO POISON PASS ON THE MODULATION FAMILY, and not as an oversight. Its outputs are the two
# COUNTERS, and the counters are also its control-flow inputs — the routine increments a byte and
# branches on whether it now matches the record's hold. Pre-inverting them, which is what the
# attribution pass does, sends the two cores down different arms of the same routine, so the pass
# reports a divergence that is the poison's rather than the candidate's. It is the case the
# playbook's §8 names ("poison on a control-flow-affecting output"), and it is measured here rather
# than assumed: with `poison=True` the pass fails at sound_voice1+1, the second counter.
#
# What stands in for it: every case above seeds the whole 24-byte block with the image's own bytes
# and then overwrites only the fields it means to drive, so a candidate that failed to write a
# counter or the cursor leaves the seeded value standing and differs on the plain pass.


@pytest.mark.parametrize("noise_period", (0, 1, 8, 0xf, 0x7f, 0xff))
def test_noise_modulate(noise_period):
    """The noise sweep: one record, no voice, and the answer masked to register 6's four bits.

    The starting register value is swept across the mask's edge, because the delta is BIASED by
    0x80 and the sum is masked afterwards — a candidate that masked before adding, or that dropped
    the bias, would agree on some of these and not others.
    """
    pokes = {}
    start = _mod_record_address(SHIPPED_MOD_TABLES[0])
    _modtable_record(pokes, A_SOUND_NOISE_BLOCK, start, start)
    shadow = bytearray(_image_bytes(A_PSG_REG_SHADOW, PSG_SHADOW_REGS))
    shadow[6] = noise_period
    pokes[A_PSG_REG_SHADOW] = bytes(shadow)
    diffs, _ = differential(ENTRY_SOUND_NOISE_MODULATE, {"_pokes": pokes},
                            lambda lib, buf: lib.g_sound_noise_modulate(buf))
    assert not diffs, f"noise_period={noise_period:#x}\n{report(diffs)}"


# =================================================================================================
# sound_voice_modulate @ 0x16da6
# =================================================================================================

# What a note-on copies over the four live counters. Distinct, nonzero values so a candidate copying
# eleven bytes instead of twelve leaves one of them standing.
TEMPLATE_COUNTER_SEEDS = b"\x05\x06\x07\x08"


def voice_pokes(voice=A_SOUND_VOICE1, fields=None, stream=None, loop=None, restart=None,
                mod_table=SHIPPED_MOD_TABLES[2]):
    """One voice record: both modulation machines on a real table, optionally armed on `stream`.

    THE LIVE CURSORS AND THE RESTART POINTERS ARE DELIBERATELY DIFFERENT — one step apart in the
    same record. A note-on copies the restarts down over the cursors, and with the two equal that
    copy writes what was already there and no case could see it.

    `stream` arms the record the way sound_start leaves it: the tune cursor, the loop point and the
    restart point all at `stream` unless `loop`/`restart` name somewhere else, and the enable byte
    set. `fields` is laid over the result last, so a case can still say `{VOICE_ENABLE: 0}`.

    Public because test_irq.py arms a voice too, and one description of "an armed voice record" is
    the point — a second copy there would go on poking the old offsets if any of them moved.
    """
    start = _mod_record_address(mod_table)
    block = bytearray(_image_bytes(voice, VOICE_STRIDE))
    for offset, value in (
            (VOICE_MOD_VOLUME_CURSOR, start + MOD_STEP_BYTES), (VOICE_MOD_VOLUME_RESTART, start),
            (VOICE_MOD_PITCH_CURSOR, start + MOD_STEP_BYTES), (VOICE_MOD_PITCH_RESTART, start)):
        block[offset:offset + 4] = value.to_bytes(4, "big")
    block[VOICE_MOD_TEMPLATE:VOICE_MOD_TEMPLATE + len(TEMPLATE_COUNTER_SEEDS)] = \
        TEMPLATE_COUNTER_SEEDS
    if stream is not None:
        for offset, target in ((VOICE_STREAM, stream), (VOICE_STREAM_LOOP, stream if loop is None
                                                        else loop),
                               (VOICE_STREAM_RESTART, stream if restart is None else restart)):
            block[offset:offset + 4] = target.to_bytes(4, "big")
        block[VOICE_ENABLE] = 1
        block[VOICE_NOTE_COUNTDOWN] = 1
    for offset, value in (fields or {}).items():
        block[offset] = value
    return {voice: bytes(block)}


def _modulate_case(voice, fields, period, poison=False):
    pokes = voice_pokes(voice, fields)
    shadow = bytearray(_image_bytes(A_PSG_REG_SHADOW, PSG_SHADOW_REGS))
    period_shadow = VOICE_PERIOD_SHADOW[voice]
    shadow[period_shadow - A_PSG_REG_SHADOW] = period & 0xff
    shadow[period_shadow - A_PSG_REG_SHADOW + 1] = period >> 8
    pokes[A_PSG_REG_SHADOW] = bytes(shadow)
    diffs, _ = differential(
        ENTRY_SOUND_VOICE_MODULATE, {"a4": voice, "a5": period_shadow, "_pokes": pokes},
        lambda lib, buf: lib.g_sound_voice_modulate(buf, voice, period_shadow), poison=poison)
    assert not diffs, f"voice={voice:#x} fields={fields} period={period:#x}\n{report(diffs)}"


@pytest.mark.parametrize("period", (0, 1, 0x100, 0x8000, 0xffff))
def test_voice_modulate_pitch_sweep(period):
    """Arpeggio off: the volume envelope runs, and then the period sweeps.

    A period of 0 is the early return — with nothing sounding the sweep is skipped — and it is the
    ONLY input that reaches it, which is why it is in the sweep rather than a case of its own.
    """
    _modulate_case(A_SOUND_VOICE1, {VOICE_ARPEGGIO: 0}, period)


@pytest.mark.parametrize("phase", (0, 1, 0xff))
def test_voice_modulate_arpeggio(phase):
    """Arpeggio on: the phase byte flips every frame and only the frame it flips to ZERO adds the
    arpeggio's offset — so one of the two notes is the row's own."""
    for arpeggio in (1, 0x0c, 0xff):
        _modulate_case(A_SOUND_VOICE1,
                       {VOICE_ARPEGGIO: arpeggio, VOICE_ARPEGGIO_PHASE: phase, VOICE_NOTE: 0x21},
                       0x0200)


# No poison pass here either, for the same measured reason as the modulation stepper above: this
# routine's outputs include both machines' counters AND the arpeggio phase byte, all three of which
# it branches on. Inverting them picks a different arm on the poisoned run.


# =================================================================================================
# sound_voice_next_row @ 0x16bf0 and sound_voice_tick @ 0x16bd6
# =================================================================================================

# One synthetic stream per command, parked in free image space. SYNTHETIC IS JUSTIFIED HERE and the
# reason is measurable: the shipped tunes between them use only 0xe1/0xe4/0xe5/0xe6/0xe8/0xe9/0xea/
# 0xec/0xf0/0xfd/0xfe, so the "unknown command" arm (any opcode 0xe1..0xfb this switch does not
# name) and the 0xfc spawn are unreachable from the game's own data. The inputs are still a stream
# of opcode bytes the interpreter is built to read, not an invented record shape — and every OTHER
# arm is driven from the real tunes as well, by test_shipped_tune_rows below.
STREAM = abi.SCRATCH


def _armed_voice_case(entry, glue_name, stream, voice=A_SOUND_VOICE1, fields=None, loop=None,
                      restart=None, extra_pokes=None, poison=False, note=""):
    """Run `entry` over a voice armed on `stream`, with A4 = the record and A5 = its period pair.

    ONE helper for both routines that take that register pair — the row fetch and the per-frame tick
    — because the staging is identical and four copies of it had already drifted apart once (one set
    the enable byte through `fields`, the others through the record directly).
    """
    pokes = voice_pokes(voice, fields, stream=stream, loop=loop, restart=restart)
    pokes.update(extra_pokes or {})
    period_shadow = VOICE_PERIOD_SHADOW[voice]
    diffs, _ = differential(
        entry, {"a4": voice, "a5": period_shadow, "_pokes": pokes},
        lambda lib, buf: getattr(lib, glue_name)(buf, voice, period_shadow), poison=poison)
    assert not diffs, f"{glue_name} {note}\n{report(diffs)}"


def _next_row_case(stream_bytes, voice=A_SOUND_VOICE1, fields=None, poison=False,
                   loop=STREAM, restart=STREAM):
    _armed_voice_case(ENTRY_SOUND_VOICE_NEXT_ROW, "g_sound_voice_next_row", STREAM, voice=voice,
                      fields=fields, loop=loop, restart=restart,
                      extra_pokes={STREAM: stream_bytes}, poison=poison,
                      note=f"stream={stream_bytes.hex()}")


# {name: the row, followed by a note so a command that CONTINUES the loop still terminates}
COMMAND_ROWS = {
    "note": b"\x21\x40",
    "rest": b"\x00\x10",
    "note_at_the_top_of_the_range": b"\x64\x08",
    "first_command_opcode": b"\x65\x08\x21\x40",
    "end": b"\xe1\x00",
    "noise_period": b"\xe4\x0e\x21\x40",
    "transpose": b"\xe6\x07\x21\x40",
    "arpeggio": b"\xf0\x0c\x21\x40",
    "volume_table": b"\xe8\x08\x21\x40",
    "pitch_table": b"\xe9\x1d\x21\x40",
    "noise_table": b"\xea\x00\x21\x40",
    "swap_tunes": b"\xec\x21\x40",
    "unknown_command": b"\xe2\x00\x21\x40",
    "unknown_command_high": b"\xfb\x00\x21\x40",
    "spawn_voice1": b"\xfc\x16\x21\x40",
    "spawn_voice2": b"\xfd\x0c\x21\x40",
    "spawn_voice3": b"\xfe\x0d\x21\x40",
}


@pytest.mark.parametrize("name", sorted(COMMAND_ROWS))
def test_next_row_command(name):
    """Every opcode the interpreter forks on, one stream each."""
    _next_row_case(COMMAND_ROWS[name])


def test_next_row_jump_and_loop():
    """0xe5 jumps into another tune and remembers the row after itself; 0xff comes back to it, or
    — if THAT row is another 0xff — to the restart pointer.

    Driven as three cases over one stream because the three share the loop and restart pointers:
    the jump writes one, the plain loop reads it, and the exhausted loop falls through to the other.
    """
    _next_row_case(b"\xe5\x0c\x21\x40")              # jump into the real tune 0x0c
    # Loop back to a note. The loop pointer may NOT be the stream's own start here: this stream
    # opens with the 0xff row, so looping to it would read 0xff again, and again, for ever — which
    # the game's own streams avoid by pairing every 0xff with a loop pointer set by an earlier 0xe5.
    _next_row_case(b"\xff\x00\x21\x40", loop=STREAM + 2, restart=STREAM + 2)
    # ...and the exhausted loop: the loop pointer's own row is another 0xff, so the restart wins.
    _next_row_case(b"\xff\x00\xff\x00\x21\x40", loop=STREAM + 2, restart=STREAM + 4)


@pytest.mark.parametrize("noise_pending", (0, 1, 2, 0xff))
def test_next_row_note_consumes_a_pending_noise(noise_pending):
    """A note-on consumes the 0xe4 flag, and the value 1 EXACTLY is what makes it a noise note —
    the original decrements the byte and branches on zero, so 2 and 0xff take the tone arm."""
    _next_row_case(b"\x21\x40", fields={0x27: noise_pending})


@pytest.mark.parametrize("transpose", (0, 1, 0x7f, 0x80, 0xff))
def test_next_row_note_is_transposed(transpose):
    """The transpose is added as a BYTE and wraps, and a REST (opcode 0) skips it entirely."""
    _next_row_case(b"\x21\x40", fields={0x26: transpose})
    _next_row_case(b"\x00\x40", fields={0x26: transpose})


@pytest.mark.parametrize("number", (TUNE_BOOT_NUMBER, 0x0c, 0x0d, 0x11, 0x16, 0x1a, 0x1c, 0x2c))
def test_shipped_tune_rows(number):
    """Run the interpreter over a shipped tune's real bytes, from its start, until it stops.

    The voice is armed exactly as sound_start would leave it, so the rows read are the tune's own
    and every command the game itself uses is exercised on its own operands.
    """
    _armed_voice_case(ENTRY_SOUND_VOICE_NEXT_ROW, "g_sound_voice_next_row",
                      tune_stream(number), note=f"tune={number:#x}")


# No poison pass on the interpreter either, and for a sharper version of the same reason: its FIRST
# output is `VOICE_STREAM`, which is also its first INPUT (`movea.l 26(a4),a0`). Pre-inverting it
# hands the poisoned run a cursor pointing outside the image, so the two cores read different rows
# and the pass reports the poison's divergence rather than the candidate's.
#
# What stands in for it: `voice_pokes` seeds the whole 50-byte record from the image and then makes
# the live cursors DIFFER from the restart pointers, so the twelve-byte template copy a note-on
# makes is visible on the plain pass; and `test_sound_start_attribution` does poison the three
# stream pointers, which sound_start writes without reading.


@pytest.mark.parametrize("enable,countdown", ((0, 5), (1, 1), (1, 2), (1, 0)))
def test_voice_tick(enable, countdown):
    """A disabled voice does nothing; an enabled one counts the row down and fetches the next row
    only when the countdown reaches zero. A countdown of 0 WRAPS to 0xff rather than fetching —
    `subq.b` then `bne`, so the fetch needs the byte to land exactly on zero."""
    _armed_voice_case(ENTRY_SOUND_VOICE_TICK, "g_sound_voice_tick", STREAM,
                      fields={VOICE_ENABLE: enable, VOICE_NOTE_COUNTDOWN: countdown},
                      extra_pokes={STREAM: b"\x21\x40\x21\x40"},
                      note=f"enable={enable} countdown={countdown}")


def test_voice_tick_stops_before_modulating_a_voice_the_row_ended():
    """The enable byte is tested TWICE and the second test is not redundant: command 0xe1 stops the
    voice inside the row fetch, and a stopped voice must not then be modulated."""
    _armed_voice_case(ENTRY_SOUND_VOICE_TICK, "g_sound_voice_tick", STREAM,
                      extra_pokes={STREAM: b"\xe1\x00"}, note="the row that ends the voice")


# =================================================================================================
# The two flushes — sound_reset_psg @ 0x16b4e and sound_tick @ 0x16b94
# =================================================================================================

def test_reset_psg():
    """Silence: three voices stopped, three volumes zeroed, the mixer muted, all 14 registers out.

    The image diff covers the shadow and the voice records; the DIRECT-PSG LEDGER covers the flush
    itself, which is outside the image entirely. `differential` compares that ledger on every case,
    so a candidate that pushed ten registers instead of fourteen — or pushed them ASCENDING — fails
    here even though the shadow it leaves behind is identical.
    """
    diffs, info = differential(ENTRY_SOUND_RESET_PSG, {"_pokes": {}},
                               lambda lib, buf: lib.g_sound_reset_psg(buf))
    assert not diffs, report(diffs)
    assert len(info["regs"]["psg"]) == PSG_SHADOW_REGS, (
        f"the oracle logged {len(info['regs']['psg'])} chip accesses, not the {PSG_SHADOW_REGS} "
        f"this routine pushes — the ledger comparison would be measuring the wrong thing")


MUSIC_FRAMES = (1, 2, 3, 8, 32)
# One tick is a few hundred instructions and the run below chains up to 32 of them plus the arm.
MUSIC_INSN_CAP = 400_000


@pytest.mark.parametrize("frames", MUSIC_FRAMES)
def test_music_frames(frames):
    """Arm the in-game tune and run the driver for `frames` VBLs, as ONE oracle run.

    This is the driver's real workload and the case that composes every routine above: tune 0x0b
    spawns 0x0c and 0x0d on voices 2 and 3 (`fd 0c` / `fe 0d`), so all three voices, both
    modulation machines, the noise sweep and the mixer are live at once, over the game's own data.

    Chained through ONE stub rather than run as N separate cases because the driver's state is what
    carries from frame to frame — `differential` rebuilds the image for every call, so N cases would
    each re-run frame 1. It also puts the whole multi-frame register stream into a single PSG
    ledger, where the order ACROSS frames is compared and not only within one.
    """
    pokes = abi.call_sequence_pokes([ENTRY_SOUND_START] + [ENTRY_SOUND_TICK] * frames)

    def glue(lib, buf):
        lib.g_sound_start(buf, TUNE_BOOT_NUMBER, 0)
        for _ in range(frames):
            lib.g_sound_tick(buf)

    diffs, info = differential(abi.STUB, {"d1": TUNE_BOOT_NUMBER, "d0": 0, "_pokes": pokes},
                               glue, max_insns=MUSIC_INSN_CAP)
    assert not diffs, f"frames={frames}\n{report(diffs)}"
    assert len(info["regs"]["psg"]) == frames * PSG_TICK_FLUSH_REGS, (
        f"{frames} ticks logged {len(info['regs']['psg'])} chip accesses, not "
        f"{frames * PSG_TICK_FLUSH_REGS} — the tick pushes registers 10..0 and nothing else")


def test_music_attribution():
    """Poison a whole frame's worth of driver state."""
    pokes = abi.call_sequence_pokes([ENTRY_SOUND_START, ENTRY_SOUND_TICK, ENTRY_SOUND_TICK])

    def glue(lib, buf):
        lib.g_sound_start(buf, TUNE_BOOT_NUMBER, 0)
        lib.g_sound_tick(buf)
        lib.g_sound_tick(buf)

    diffs, _ = differential(abi.STUB, {"d1": TUNE_BOOT_NUMBER, "d0": 0, "_pokes": pokes},
                            glue, max_insns=MUSIC_INSN_CAP, poison=True)
    assert not diffs, report(diffs)


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_TUNE_INDEX", "include/sound.h", "A_tune_index"),
    ("A_TUNE_DATA", "include/sound.h", "A_tune_data"),
    ("A_MOD_TABLE_INDEX", "include/sound.h", "A_mod_table_index"),
    ("A_MOD_TABLE_DATA", "include/sound.h", "A_mod_table_data"),
    ("A_NOTE_PERIOD_TBL", "include/sound.h", "A_note_period_tbl"),
    ("A_PSG_REG_SHADOW", "include/sound.h", "A_psg_reg_shadow"),
    ("A_SFX_VOICE_TOGGLE", "include/sound.h", "A_sfx_voice_toggle"),
    ("A_SOUND_NOISE_BLOCK", "include/sound.h", "A_sound_noise_block"),
    ("A_SOUND_VOICE1", "include/sound.h", "A_sound_voice1"),
    ("A_SOUND_VOICE2", "include/sound.h", "A_sound_voice2"),
    ("A_SOUND_VOICE3", "include/sound.h", "A_sound_voice3"),
    ("VOICE_STRIDE", "include/sound.h", "VOICE_STRIDE"),
    ("VOICE_ENABLE", "include/sound.h", "VOICE_ENABLE"),
    ("VOICE_NOTE_COUNTDOWN", "include/sound.h", "VOICE_NOTE_COUNTDOWN"),
    ("VOICE_STREAM", "include/sound.h", "VOICE_STREAM"),
    ("VOICE_STREAM_LOOP", "include/sound.h", "VOICE_STREAM_LOOP"),
    ("VOICE_STREAM_RESTART", "include/sound.h", "VOICE_STREAM_RESTART"),
    ("VOICE_ARPEGGIO", "include/sound.h", "VOICE_ARPEGGIO"),
    ("VOICE_NOTE", "include/sound.h", "VOICE_NOTE"),
    ("VOICE_ARPEGGIO_PHASE", "include/sound.h", "VOICE_ARPEGGIO_PHASE"),
    ("PSG_SHADOW_REGS", "include/sound.h", "PSG_SHADOW_REGS"),
    ("PSG_TICK_FLUSH_REGS", "include/sound.h", "PSG_TICK_FLUSH_REGS"),
    ("PSG_VOICE_PERIOD_BYTES", "include/sound.h", "PSG_VOICE_PERIOD_BYTES"),
    ("VOICE_MOD_VOLUME_CURSOR", "include/sound.h", "VOICE_MOD_VOLUME_CURSOR"),
    ("VOICE_MOD_PITCH_CURSOR", "include/sound.h", "VOICE_MOD_PITCH_CURSOR"),
    ("VOICE_MOD_VOLUME_RESTART", "include/sound.h", "VOICE_MOD_VOLUME_RESTART"),
    ("VOICE_MOD_PITCH_RESTART", "include/sound.h", "VOICE_MOD_PITCH_RESTART"),
    ("VOICE_MOD_TEMPLATE", "include/sound.h", "VOICE_MOD_TEMPLATE"),
    ("VOICE_MOD_TEMPLATE_BYTES", "include/sound.h", "VOICE_MOD_TEMPLATE_BYTES"),
    ("MOD_STEP_BYTES", "include/sound.h", "MOD_STEP_BYTES"),
    ("MOD_STEP_PERIOD", "include/sound.h", "MOD_STEP_PERIOD"),
    ("MOD_STEP_REPEATS", "include/sound.h", "MOD_STEP_REPEATS"),
    ("MOD_RECORD_END", "include/sound.h", "MOD_RECORD_END"),
    ("SOUND_ROW_BYTES", "include/sound.h", "SOUND_ROW_BYTES"),
    ("SOUND_STREAM_CHANNEL_TAG", "include/sound.h", "SOUND_STREAM_CHANNEL_TAG"),
    ("SOUND_CHANNEL_ALTERNATE", "include/sound.h", "SOUND_CHANNEL_ALTERNATE"),
)
ENTRY_PROLOGUES = {
    "ENTRY_SOUND_START": "48e7fffe61640c1100fa",
    "ENTRY_SOUND_RESET_PSG": "41fa035a4228001841fa",
    "ENTRY_SOUND_TICK": "48e7fffe41fa02f3700a",
    "ENTRY_SOUND_VOICE_TICK": "4a2c00186712532c0019",
    "ENTRY_SOUND_VOICE_NEXT_ROW": "206c001a101812182948",
    "ENTRY_SOUND_LOOKUP_TUNE": "43fa0524024100ffe349",
    "ENTRY_SOUND_LOOKUP_MODTABLE": "024100ffe34941fa0314",
    "ENTRY_SOUND_VOICE_MODULATE": "610000a0206c002a1010",
    "ENTRY_SOUND_SET_NOTE_PERIOD": "024000ffe34841fa0134",
    "ENTRY_SOUND_NOISE_MODULATE": "49fa00686100001a41fa",
    "ENTRY_SOUND_MODTABLE_STEP_A4": "204c226c000452101011",
    "ENTRY_SOUND_MODTABLE_STEP": "226c000452101011123c",
}
