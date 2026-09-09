"""Differential tests for the sound engine (src/sound.c).

Four shapes of case, and the last two are the ones that carry the weight:

* the trigger API (`sound_play` and its four siblings) takes stack arguments and writes voice
  records in the BSS, so it is ordinary diffed memory — plus a stream of `trap #9` PSG accesses the
  kit's direct-PSG ledger compares (TRAP_MODEL.md, Phase 6);
* `install_sound_vectors`/`remove_sound_vectors` write the 68000 vector page and `$fffffa17`. The
  vectors are in the image; the MFP byte is not, and the kit's hardware WRITE ledger is the only
  thing that can see it (Phase 10);
* `timer_c_sound_isr` is entered DIRECTLY — no fabricated exception frame is needed, because the
  handler never `rte`s: it saves and restores `sr` itself and leaves by pushing TOS's saved `$114`
  vector and `rts`ing. Staging that vector word with the harness's own sentinel is what makes the
  chain land back in the runner. It is entered at IPL 7 in supervisor, which is what `emu.run`
  forces anyway, and the `ori`/`andi` on `sr` it opens with have no image effect;
* the MULTI-TICK cases drive that handler N times inside ONE oracle run, through an 18-byte stub
  (`abi.call_n_times_stub`) that `jsr`s it in a `dbf` loop. It works for the same reason: point the saved
  `$114` vector at a bare `rts` and the handler's chain becomes an ordinary return. That is what
  reaches the states a single tick cannot — a decay that runs into its sustain, an LFO that folds,
  a duration that counts down to key-off and takes three release phases with it.

WHAT THE `staged` FIXTURE IS AND IS NOT. Every address this engine touches is BSS that only
`init_globals` fills, and `conftest.py`'s autouse session fixture is what installs that post-init
image as the memory every `differential()` starts from — so a case gets it whether or not it asks.
`staged` is simply a NAME for those bytes, for the two cases that also want to READ the game's own
tables out of them; `harness.BASE_IMAGE` is still the loader's zeroed-bss image and is the wrong
place to read a definition from.
"""
import ctypes
import random

import pytest

import abi
import harness
import emu
import test_sound_asm
from harness import report

ENTRY_SOUND_PLAY = 0x142bc
ENTRY_SOUND_STOP_VOICE = 0x144c4
ENTRY_SOUND_RELEASE_VOICE = 0x14510
ENTRY_SOUND_VOICE_PRIORITY = 0x1455e
ENTRY_SOUND_STOP_ALL = 0x14576
ENTRY_TIMER_C_SOUND_ISR = 0x1459a
ENTRY_PSG_GATE = 0x14940
ENTRY_INSTALL_SOUND_VECTORS = 0x148ea
ENTRY_REMOVE_SOUND_VECTORS = 0x1491c
ENTRY_SOUND_START = 0x14982
ENTRY_SOUND_STOP = 0x1499c

# ---- mirrors of include/sound.h (pinned by test_constants.py's MIRRORS below) --------------------
A_snd_voice = 0x22daa
A_snd_note_period = 0x22cd0
A_snd_volume_scale = 0x22cda
A_snd_mixer_and_mask = 0x22cfa
A_snd_def_level = 0x1f20a
A_snd_def_fx = 0x201ca
# ...and the clib subsystem's three trap-save slots, which `sound_start`/`sound_stop` reach through
# `Supexec`. Mirrored against include/clib.h, where they live.
A_trap_saved_ret = 0x1e932
A_trap_saved_a1 = 0x1e93a

SND_ISR_SAVED_TIMER_C = 0x14932
SND_ISR_VOLUME_SCALE = 0x14936
SND_ISR_TOP_VOICE = 0x1493a
SND_ISR_SAVED_CONTERM = 0x1493e
SND_ISR_STATE_BYTES = 13
SND_ISR_ENTRY = 0x1459a
SND_TRAP9_HANDLER_ENTRY = 0x14950

TOS_VEC_TRAP9 = 0x00a4
TOS_VEC_TIMER_C = 0x0114
TOS_CONTERM = 0x0484
MFP_VECTOR_REG = 0xfffa17
MFP_VECTOR_AUTO_EOI = 0x40
MFP_VECTOR_SW_EOI = 0x48

SND_VOICES = 3
SND_VOICE_BYTES = 0x8c
SND_DEF_WORDS = 56
SND_DEF_BYTES = 0x70

SND_VC_DURATION = 0x00
SND_VC_TONE_PERIOD = 0x02
SND_VC_NOISE_PERIOD = 0x04
SND_VC_VOLUME_INDEX = 0x06
SND_VC_VOL_PHASE = 0x08
SND_VC_VOL_ATTACK_STEP = 0x0a
SND_VC_VOL_DECAY_STEP = 0x0e
SND_VC_VOL_SUSTAIN = 0x12
SND_VC_VOL_RELEASE_STEP = 0x16
SND_VC_VOL_LFO_LIMIT = 0x1a
SND_VC_VOL_LFO_STEP = 0x1e
SND_VC_VOL_LFO_DELAY = 0x22
SND_VC_PITCH_PHASE = 0x24
SND_VC_PITCH_STEP1 = 0x26
SND_VC_PITCH_TARGET1 = 0x2a
SND_VC_PITCH_STEP2 = 0x2e
SND_VC_PITCH_TARGET2 = 0x32
SND_VC_PITCH_RELEASE_STEP = 0x36
SND_VC_PITCH_LFO_LIMIT_HI = 0x3a
SND_VC_PITCH_LFO_STEP = 0x3e
SND_VC_PITCH_LFO_STEP_RELOAD_UP = 0x42
SND_VC_PITCH_LFO_LIMIT_LO = 0x46
SND_VC_PITCH_LFO_STEP_RELOAD_DOWN = 0x4a
SND_VC_PITCH_LFO_DELAY = 0x4e
SND_VC_NOISE_PHASE = 0x50
SND_VC_NOISE_STEP1 = 0x52
SND_VC_NOISE_TARGET1 = 0x56
SND_VC_NOISE_STEP2 = 0x5a
SND_VC_NOISE_TARGET2 = 0x5e
SND_VC_NOISE_RELEASE_STEP = 0x62
SND_VC_NOISE_LFO_LIMIT = 0x66
SND_VC_NOISE_LFO_STEP = 0x6a
SND_VC_NOISE_LFO_DELAY = 0x6e
SND_VC_GATE = 0x70
SND_VC_PRIORITY = 0x72
SND_VC_VOL_ENV_ACC = 0x74
SND_VC_VOL_LFO_ACC = 0x78
SND_VC_PITCH_ENV_ACC = 0x7c
SND_VC_PITCH_LFO_ACC = 0x80
SND_VC_NOISE_ENV_ACC = 0x84
SND_VC_NOISE_LFO_ACC = 0x88

SND_VOL_ENV_PEAK = 0x000f0000
SND_NOTE_MAX = 0x6c
SND_NOTE_MIN = 0x18
SND_NOTE_OCTAVE = 0x0c

# The 47 definitions the shipped game can reach: 36 per-room themes then 11 fixed effects, one flat
# 0x70-byte space (../notes/sound_engine.md §8) — `A_snd_def_level + 36 * 0x70` IS `A_snd_def_fx`.
SND_DEF_LEVEL_COUNT = 36
SND_DEF_FX_COUNT = 11
ALL_DEFINITIONS = [A_snd_def_level + SND_DEF_BYTES * i for i in range(SND_DEF_LEVEL_COUNT)] + \
                  [A_snd_def_fx + SND_DEF_BYTES * i for i in range(SND_DEF_FX_COUNT)]

VOICE_RECORDS = [A_snd_voice + SND_VOICE_BYTES * v for v in range(SND_VOICES)]
VOICE_ARENA = (A_snd_voice, A_snd_voice + SND_VOICES * SND_VOICE_BYTES)

# Where a case builds a synthetic definition. The multi-tick stub itself is `abi.call_n_times_stub`
# — its chain `rts` (where the handler's own `rts` lands, since it does not `rte`) is at
# `abi.CALL_N_TIMES_CHAIN`. D7 is the counter because the handler saves and restores D0-D3/A0-A2.
SCRATCH_DEFINITION = abi.SCRATCH
ISR_TICK_COUNTER_REGISTER = 7

FUZZ_CHUNKS = 8

for _name, _extra, _returns in (("g_sound_play", 5, True),
                                ("g_sound_stop_voice", 1, False),
                                ("g_sound_release_voice", 1, False),
                                ("g_sound_voice_priority", 1, True),
                                ("g_sound_stop_all", 0, False),
                                ("g_timer_c_sound_isr", 0, False),
                                ("g_timer_c_sound_isr_ticks", 1, False),
                                ("g_psg_gate", 3, True),
                                ("g_install_sound_vectors", 0, False),
                                ("g_remove_sound_vectors", 0, False),
                                ("g_sound_start", 2, False),
                                ("g_sound_stop", 2, False)):
    getattr(harness._lib, _name).argtypes = ([ctypes.POINTER(ctypes.c_uint8)]
                                             + [ctypes.c_uint32] * _extra)
    getattr(harness._lib, _name).restype = ctypes.c_uint32 if _returns else None


# =================================================================================================
# Staging
# =================================================================================================

@pytest.fixture
def staged(post_init_image):
    """The bytes every case already runs on — see the module docstring.

    `conftest.py`'s autouse fixture has installed them as the differential's base image, so this is
    a reader's handle rather than a switch: a case takes it to say WHICH image it means when it
    reads a shipped table, and every case takes it so that the dependency is visible at the case
    rather than buried in a session fixture.
    """
    return post_init_image


def trap9_vector():
    """`$a4` pointing at the game's own supervisor PSG handler.

    THIS IS DATA THE GAME WRITES, not a fixture invention: `install_sound_vectors` @ 0x148ea stores
    exactly this longword. Every routine that reaches the chip through `psg_gate` executes a
    `trap #9`, and the oracle dispatches through the vector — which is zero on an image that has not
    run the installer, so the run would jump to address 0.
    """
    return {TOS_VEC_TRAP9: abi.long(SND_TRAP9_HANDLER_ENTRY)}


def isr_state(saved_timer_c, conterm=0x00, volume_scale=A_snd_volume_scale,
              top_voice=A_snd_voice + (SND_VOICES - 1) * SND_VOICE_BYTES):
    """The 13-byte block `install_sound_vectors` fills and the handler reads back.

    `saved_timer_c` is where the handler's closing `rts` lands, because it does not `rte`: it pushes
    this longword and returns through it, chaining to TOS's own Timer C work.
    """
    return {SND_ISR_SAVED_TIMER_C: abi.long(saved_timer_c) + abi.long(volume_scale)
                                   + abi.long(top_voice) + bytes([conterm])}


def all_registers(rng):
    """A `psg_seed` declaring all sixteen registers.

    The chip's contents on entry are an INPUT of the run (TRAP_MODEL.md, Phase 6), and `psg_gate`
    reads one back on every call — register 7 twice, once to merge the mixer. Declaring the whole
    file rather than the registers a given path happens to touch keeps the seed a statement about
    the chip instead of about which branch the case takes.
    """
    return {register: rng.randrange(0x100) for register in range(16)}


def voice_records(records):
    """Poke the three voice records from three 0x8c-byte blobs, with noise either side.

    The guard band is what turns "wrote one record too far" into a difference: the arena is BSS, so
    a candidate running off the end would write over bytes that are already what the oracle leaves.
    """
    blob = b"".join(records)
    assert len(blob) == SND_VOICES * SND_VOICE_BYTES
    guards = abi.seed_spans(0x5ec1, [(VOICE_ARENA[0] - abi.GUARD_BYTES, VOICE_ARENA[0]),
                                     (VOICE_ARENA[1], VOICE_ARENA[1] + abi.GUARD_BYTES)])
    return abi.merge_pokes({A_snd_voice: blob}, guards)


# =================================================================================================
# Building voice records
# =================================================================================================

def idle_record():
    return bytes(SND_VOICE_BYTES)


def _envelope_step(rng):
    """A signed 32-bit envelope step, weighted toward the magnitudes the shipped data uses.

    The extremes are in the pool on purpose: `neg.l` of INT32_MIN and an accumulator that wraps are
    exactly the places a C transcription and the 68000 stop agreeing if the arithmetic is spelt with
    plain signed operators.
    """
    return rng.choice([0, 1, -1, 0x100, -0x100, 0x4000, -0x4000, 0x18000, -0x18000,
                       0x7fffffff, -0x80000000, rng.randrange(-0x80000000, 0x80000000)])


def _accumulator(rng):
    return rng.choice([0, SND_VOL_ENV_PEAK, 0x00007fff, -1, 0x7fff0000, -0x80000000,
                       rng.randrange(-0x80000000, 0x80000000)])


def _limit(rng):
    """An LFO limit. Zero — the machine's off switch — is deliberately common.

    0x8000 earns its place separately: its HIGH word is zero, and the "is this machine running"
    gate ORs the phase with that high word alone (`or.w 26(a0),d0`), so a limit below 0x10000 turns
    the LFO on while leaving the gate shut. Nothing else in the pool separates the high-word read
    from a read of the whole long.
    """
    return rng.choice([0, 0, 0, 1, 0x8000, 0x40000, 0x7fffffff, rng.randrange(0, 0x80000000)])


def _phase(rng):
    """An envelope phase word.

    ALL THREE MACHINES SELECT ON IT WITH `cmp.b`, so only its low byte decides the branch and a
    phase of 0x0104 is a release. Half the pool carries such a high byte, because nothing a
    definition-shaped record does would reach that arm otherwise — and `sound_play` copies whatever
    a definition holds straight into the field.
    """
    low = rng.randrange(0, 6)
    return low if rng.randrange(2) else (rng.randrange(1, 0x100) << 8) | low


def random_record(rng):
    """One voice record covering every phase, both step signs, both LFO gates and both key modes."""
    record = bytearray(SND_VOICE_BYTES)

    def put_w(offset, value):
        record[offset:offset + 2] = abi.word(value)

    def put_l(offset, value):
        record[offset:offset + 4] = abi.long(value)

    put_w(SND_VC_DURATION, rng.choice([0, 1, 2, 3, 40, 200, 1400, rng.randrange(1, 0x8000)]))
    put_w(SND_VC_TONE_PERIOD, rng.choice([-1, -0x8000, 0, 1, 30, 284, 1214, 4032, 0x7fff]))
    put_w(SND_VC_NOISE_PERIOD, rng.choice([-1, -0x8000, 0, 8, 16, 28, 31, 0x7fff]))
    put_w(SND_VC_VOLUME_INDEX, rng.randrange(0, 16))

    put_w(SND_VC_VOL_PHASE, _phase(rng))
    put_l(SND_VC_VOL_ATTACK_STEP, _envelope_step(rng))
    put_l(SND_VC_VOL_DECAY_STEP, _envelope_step(rng))
    put_l(SND_VC_VOL_SUSTAIN, _accumulator(rng))
    put_l(SND_VC_VOL_RELEASE_STEP, _envelope_step(rng))
    put_l(SND_VC_VOL_LFO_LIMIT, _limit(rng))
    put_l(SND_VC_VOL_LFO_STEP, _envelope_step(rng))
    put_w(SND_VC_VOL_LFO_DELAY, rng.choice([0, 0, 1, 2, 40]))

    put_w(SND_VC_PITCH_PHASE, _phase(rng))
    put_l(SND_VC_PITCH_STEP1, _envelope_step(rng))
    put_l(SND_VC_PITCH_TARGET1, _accumulator(rng))
    put_l(SND_VC_PITCH_STEP2, _envelope_step(rng))
    put_l(SND_VC_PITCH_TARGET2, _accumulator(rng))
    put_l(SND_VC_PITCH_RELEASE_STEP, _envelope_step(rng))
    put_l(SND_VC_PITCH_LFO_LIMIT_HI, _limit(rng))
    put_l(SND_VC_PITCH_LFO_STEP, _envelope_step(rng))
    put_l(SND_VC_PITCH_LFO_STEP_RELOAD_UP, _envelope_step(rng))
    put_l(SND_VC_PITCH_LFO_LIMIT_LO, -_limit(rng))
    put_l(SND_VC_PITCH_LFO_STEP_RELOAD_DOWN, _envelope_step(rng))
    put_w(SND_VC_PITCH_LFO_DELAY, rng.choice([0, 0, 1, 2, 40]))

    put_w(SND_VC_NOISE_PHASE, _phase(rng))
    put_l(SND_VC_NOISE_STEP1, _envelope_step(rng))
    put_l(SND_VC_NOISE_TARGET1, _accumulator(rng))
    put_l(SND_VC_NOISE_STEP2, _envelope_step(rng))
    put_l(SND_VC_NOISE_TARGET2, _accumulator(rng))
    put_l(SND_VC_NOISE_RELEASE_STEP, _envelope_step(rng))
    put_l(SND_VC_NOISE_LFO_LIMIT, _limit(rng))
    put_l(SND_VC_NOISE_LFO_STEP, _envelope_step(rng))
    put_w(SND_VC_NOISE_LFO_DELAY, rng.choice([0, 0, 1, 2, 40]))

    put_w(SND_VC_GATE, rng.choice([-1, -1, 0, 60, 250]))
    put_w(SND_VC_PRIORITY, rng.choice([0, 5, 10, 13]))
    put_l(SND_VC_VOL_ENV_ACC, _accumulator(rng))
    put_l(SND_VC_VOL_LFO_ACC, _accumulator(rng))
    put_l(SND_VC_PITCH_ENV_ACC, _accumulator(rng))
    put_l(SND_VC_PITCH_LFO_ACC, _accumulator(rng))
    put_l(SND_VC_NOISE_ENV_ACC, _accumulator(rng))
    put_l(SND_VC_NOISE_LFO_ACC, _accumulator(rng))
    return bytes(record)


def armed_record(duration, fields):
    """A record built field by field, for a case that wants one machine and no others.

    It opens armed, silent and auto-releasing — both base periods negative, so neither the tone nor
    the noise machine reaches the chip unless the case turns it on, and the gate negative, so the
    duration counter runs. `fields` is `{offset: (size, value)}` over include/sound.h's own names.
    """
    record = bytearray(SND_VOICE_BYTES)
    record[SND_VC_DURATION:SND_VC_DURATION + 2] = abi.word(duration)
    record[SND_VC_TONE_PERIOD:SND_VC_TONE_PERIOD + 2] = abi.word(-1)
    record[SND_VC_NOISE_PERIOD:SND_VC_NOISE_PERIOD + 2] = abi.word(-1)
    record[SND_VC_GATE:SND_VC_GATE + 2] = abi.word(-1)
    for offset, (size, value) in fields.items():
        assert size in (2, 4), f"a record field is a word or a longword, not {size} bytes"
        record[offset:offset + size] = (abi.word(value) if size == 2 else abi.long(value))
    return bytes(record)


# =================================================================================================
# psg_gate @ 0x14940 / trap9_psg_handler @ 0x14950
# =================================================================================================

# The gate's three arguments are three words at 4(a7), 6(a7) and 8(a7) — it has no `link`, so they
# start at the first argument slot exactly as a `jsr` leaves them.
def psg_gate_case(staged_image, register, value, mask, seed):
    pokes = abi.merge_pokes(abi.stack_args((2, register & 0xffff), (2, value & 0xffff),
                                       (2, mask & 0xffff)),
                        trap9_vector())
    diffs, info = abi.run_with_a4(ENTRY_PSG_GATE,
                                  lambda lib, buf: lib.g_psg_gate(buf, register & 0xffff,
                                                                  value & 0xffff, mask & 0xffff),
                                  pokes=pokes, psg_seed=seed)
    assert not diffs, report(diffs)
    # The gate's answer is a zero-extended byte (`moveq #0,d0` then `move.b (a0),d0`), so the whole
    # longword is comparable — unlike the `short` the C-compiled routines return.
    assert info["ret"] == info["regs"]["d0"], (
        f"psg_gate({register}, {value}, {mask:#x}) returned {info['ret']:#x}, "
        f"oracle d0 = {info['regs']['d0']:#x}")


def test_psg_gate_writes_and_reads_back_every_register(staged):
    """A plain write: select, store, read the register back. Register 7 is the exception below."""
    rng = random.Random(0x9a10)
    for register in range(16):
        psg_gate_case(staged, register, rng.randrange(0x100), 0xffff, all_registers(rng))


def test_psg_gate_register_7_merges_the_mixer_it_read_back(staged):
    """The read-modify-write that keeps the other two channels' bits and TOS's port directions.

    THE READ IS PART OF THE COMPARED STREAM: a reconstruction that read the wrong register would
    still write the right one, and only the ledger's read entry separates the two.
    """
    rng = random.Random(0x9a11)
    for mask in (0xf6, 0xed, 0xdb, 0x00, 0xff):
        for value in (0x00, 0x01, 0x09, 0x1f, 0x3f):
            psg_gate_case(staged, 7, value, mask, all_registers(rng))


def test_psg_gate_a_negative_value_writes_nothing(staged):
    """`tst.w d0` on the value word: below zero the call is a pure read of the selected register."""
    rng = random.Random(0x9a12)
    for register in (0, 6, 7, 8, 11, 15):
        for value in (-1, -0x8000, -0x100):
            psg_gate_case(staged, register, value, 0xf6, all_registers(rng))


def test_psg_gate_masks_the_register_number_to_four_bits(staged):
    """`and.b #$f,d1`: the select is four bits, so 0x17 and 0x07 are the same register."""
    rng = random.Random(0x9a13)
    for register in (0x10, 0x17, 0xff, 0x1ff, 0x8007):
        psg_gate_case(staged, register, 0x2a, 0x3f, all_registers(rng))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_psg_gate_fuzz(staged, chunk):
    """Random (register, value, mask, chip state) over the whole argument space.

    CHUNK-SEEDED, not chunk-partitioned (`abi.shard`): each chunk seeds its own generator, so the
    suite runs FUZZ_CHUNKS x 12 distinct cases rather than splitting one list of 12.
    """
    rng = random.Random(0x9a14 + chunk)
    for _ in range(12):
        psg_gate_case(staged, rng.randrange(-0x8000, 0x10000), rng.randrange(-0x8000, 0x10000),
                      rng.randrange(0x10000), all_registers(rng))


# =================================================================================================
# sound_voice_priority @ 0x1455e, sound_stop_voice @ 0x144c4, sound_release_voice @ 0x14510,
# sound_stop_all @ 0x14576
# =================================================================================================

def one_word_case(entry, glue, voice, records, seed=None, returns=False):
    pokes = abi.merge_pokes(abi.stack_args((2, voice & 0xffff)), trap9_vector(),
                            voice_records(records))
    diffs, info = abi.run_with_a4(entry,
                                  lambda lib, buf: getattr(lib, glue)(buf, voice & 0xffff),
                                  pokes=pokes, psg_seed=seed)
    assert not diffs, report(diffs)
    if returns:
        # An Alcyon C `short` comes back in D0's LOW WORD; its high half is whatever the routine's
        # own arithmetic left there and no caller reads it.
        assert info["ret"] & 0xffff == info["regs"]["d0"] & 0xffff, (
            f"{glue}({voice}) returned {info['ret'] & 0xffff:#x}, "
            f"oracle d0.w = {info['regs']['d0'] & 0xffff:#x}")


def test_sound_voice_priority_reads_the_record(staged):
    rng = random.Random(0x9a20)
    records = [random_record(rng) for _ in range(SND_VOICES)]
    for voice in range(SND_VOICES):
        one_word_case(ENTRY_SOUND_VOICE_PRIORITY, "g_sound_voice_priority", voice, records,
                      returns=True)


def test_sound_voice_priority_has_no_range_check(staged):
    """It indexes the record array with WHATEVER it is given — unlike its three siblings.

    400 AND 743 ARE THE POINT OF THIS CASE, not the small indices. `muls.w #$8c,dn` builds a 32-bit
    product and `adda.w dn,a0` adds only its SIGN-EXTENDED LOW WORD, so an index at or above 372
    (0x8c * 372 = 0x8000) reaches an address BELOW the record array rather than far above it. A
    reconstruction that added the whole product is green over 0..2 and over every small index;
    these two are what separate the two arithmetics, and both land inside the image either way so
    the difference shows up as a returned word rather than as a fault.
    """
    rng = random.Random(0x9a21)
    records = [random_record(rng) for _ in range(SND_VOICES)]
    for voice in (-8, -3, -1, 3, 4, 8, 371, 372, 400, 743):
        one_word_case(ENTRY_SOUND_VOICE_PRIORITY, "g_sound_voice_priority", voice, records,
                      returns=True)


def test_sound_stop_voice_frees_silences_and_mutes(staged):
    rng = random.Random(0x9a22)
    for voice in (-1, 0, 1, 2, 3, -0x8000, 0x7fff):
        records = [random_record(rng) for _ in range(SND_VOICES)]
        one_word_case(ENTRY_SOUND_STOP_VOICE, "g_sound_stop_voice", voice, records,
                      seed=all_registers(rng))


def test_sound_release_voice_arms_the_key_off(staged):
    """A live voice gets duration 1 and a negative gate; an idle one is left completely alone."""
    rng = random.Random(0x9a23)
    for duration in (0, 1, 2, 400):
        records = [bytearray(random_record(rng)) for _ in range(SND_VOICES)]
        for record in records:
            record[SND_VC_DURATION:SND_VC_DURATION + 2] = abi.word(duration)
        for voice in (-1, 0, 1, 2, 3):
            one_word_case(ENTRY_SOUND_RELEASE_VOICE, "g_sound_release_voice", voice,
                          [bytes(r) for r in records])


def test_sound_stop_all(staged):
    rng = random.Random(0x9a24)
    for _ in range(4):
        records = [random_record(rng) for _ in range(SND_VOICES)]
        pokes = abi.merge_pokes(trap9_vector(), voice_records(records))
        diffs, _info = abi.run_with_a4(ENTRY_SOUND_STOP_ALL,
                                       lambda lib, buf: lib.g_sound_stop_all(buf),
                                       pokes=pokes, psg_seed=all_registers(rng))
        assert not diffs, report(diffs)


# =================================================================================================
# sound_play @ 0x142bc
# =================================================================================================

def sound_play_case(definition, voice, volume, note, priority, records, seed,
                    extra_pokes=None, poison=False):
    pokes = abi.merge_pokes(abi.stack_args((4, definition), (2, voice & 0xffff),
                                           (2, volume & 0xffff), (2, note & 0xffff),
                                           (2, priority & 0xffff)),
                            trap9_vector(), voice_records(records), extra_pokes or {})
    args = (definition, voice & 0xffff, volume & 0xffff, note & 0xffff, priority & 0xffff)
    diffs, info = abi.run_with_a4(ENTRY_SOUND_PLAY, lambda lib, buf: lib.g_sound_play(buf, *args),
                                  pokes=pokes, psg_seed=seed, poison=poison)
    assert not diffs, report(diffs)
    assert info["ret"] & 0xffff == info["regs"]["d0"] & 0xffff, (
        f"sound_play({definition:#x}, {voice}, {volume}, {note}, {priority}) returned "
        f"{info['ret'] & 0xffff:#x}, oracle d0.w = {info['regs']['d0'] & 0xffff:#x}")
    return info


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_sound_play_every_definition(staged, chunk):
    """All 47 definitions the game can reach, on every voice.

    Both halves of the flat definition space are here — the 36 per-room themes and the 11 fixed
    effects — because the two are one array and `room_candle_sfx` indexes across the boundary.
    """
    rng = random.Random(0x9a30 + chunk)
    idle = [idle_record() for _ in range(SND_VOICES)]
    for definition in abi.shard(ALL_DEFINITIONS, chunk, FUZZ_CHUNKS):
        for voice in range(SND_VOICES):
            sound_play_case(definition, voice, -1, -1, 5, idle, all_registers(rng))


def test_sound_play_zeroes_the_accumulators(staged):
    """Every trigger clears all six, whatever the record held — pinned against a poisoned record."""
    rng = random.Random(0x9a31)
    records = [random_record(rng) for _ in range(SND_VOICES)]
    for voice in range(SND_VOICES):
        sound_play_case(A_snd_def_fx, voice, 9, -1, 0x7fff, records, all_registers(rng),
                        poison=True)


def test_sound_play_priority_refusal(staged):
    """`priority < record priority` returns -1 and changes nothing at all."""
    rng = random.Random(0x9a32)
    records = [bytearray(random_record(rng)) for _ in range(SND_VOICES)]
    for record in records:
        record[SND_VC_PRIORITY:SND_VC_PRIORITY + 2] = abi.word(10)
    frozen = [bytes(r) for r in records]
    for priority in (-1, 0, 9, 10, 11):
        for voice in range(SND_VOICES):
            info = sound_play_case(A_snd_def_fx, voice, 8, -1, priority, frozen,
                                   all_registers(rng))
            expected = 0xffff if priority < 10 else voice
            assert info["ret"] & 0xffff == expected


def test_sound_play_zero_duration_only_stops_the_voice(staged):
    """`def[0] == 0` returns after the stop, so a zero-duration definition IS "silence that voice"."""
    rng = random.Random(0x9a33)
    records = [random_record(rng) for _ in range(SND_VOICES)]
    definition = bytearray(SND_DEF_BYTES)
    definition[0:2] = abi.word(0)
    for word_index in range(1, SND_DEF_WORDS):
        definition[2 * word_index:2 * word_index + 2] = abi.word(rng.randrange(0x10000))
    for voice in range(SND_VOICES):
        sound_play_case(SCRATCH_DEFINITION, voice, 8, -1, 15, records, all_registers(rng),
                        extra_pokes={SCRATCH_DEFINITION: bytes(definition)})


def test_sound_play_every_note(staged):
    """Notes 0..127 plus the negative one-shot: the fold, and the whole reachable table window.

    Only slots 24..108 are addressable — the fold walks a note into that window by octaves — and the
    24 slots below it are `snd_volume_scale` and `snd_mixer_and_mask` packed into the table's head.
    """
    rng = random.Random(0x9a34)
    idle = [idle_record() for _ in range(SND_VOICES)]
    for note in list(range(0, 128)) + [-1, -0x8000, 0x7fff, SND_NOTE_MIN - 1, SND_NOTE_MAX + 1]:
        # fx8 is the definition the game itself drives with a caller's note (the bonus tally).
        sound_play_case(A_snd_def_fx + 8 * SND_DEF_BYTES, 2, 8, note, 10, idle,
                        all_registers(rng))


def test_sound_play_tone_off_and_noise_off(staged):
    """A negative base period switches its machine off and raises the mixer bit for that channel."""
    rng = random.Random(0x9a35)
    idle = [idle_record() for _ in range(SND_VOICES)]
    for tone, noise in ((-1, -1), (-1, 16), (284, -1), (284, 16)):
        definition = bytearray(SND_DEF_BYTES)
        definition[0:2] = abi.word(200)
        definition[SND_VC_TONE_PERIOD:SND_VC_TONE_PERIOD + 2] = abi.word(tone)
        definition[SND_VC_NOISE_PERIOD:SND_VC_NOISE_PERIOD + 2] = abi.word(noise)
        # Give both LFO limits and both phases something to clear, so the "switch it off" writes
        # are visible rather than zero-over-zero.
        definition[SND_VC_PITCH_PHASE:SND_VC_PITCH_PHASE + 2] = abi.word(1)
        definition[SND_VC_PITCH_LFO_LIMIT_HI:SND_VC_PITCH_LFO_LIMIT_HI + 4] = abi.long(0x40000)
        definition[SND_VC_NOISE_PHASE:SND_VC_NOISE_PHASE + 2] = abi.word(1)
        definition[SND_VC_NOISE_LFO_LIMIT:SND_VC_NOISE_LFO_LIMIT + 4] = abi.long(0x40000)
        for voice in range(SND_VOICES):
            sound_play_case(SCRATCH_DEFINITION, voice, 8, -1, 5, idle, all_registers(rng),
                            extra_pokes={SCRATCH_DEFINITION: bytes(definition)})


def test_sound_play_volume_argument_and_the_no_envelope_path(staged):
    """A negative volume keeps the definition's own index; a zero volume phase means no envelope.

    The no-envelope path is the one slots 0 and 3 of `snd_def_level` take — the only two definitions
    in the game with `vphase == 0` — and it pegs the accumulator at full scale and writes the raw
    index straight at the chip.
    """
    rng = random.Random(0x9a36)
    idle = [idle_record() for _ in range(SND_VOICES)]
    for volume in (-1, 0, 7, 15, 0x7fff):
        for phase in (0, 1):
            definition = bytearray(SND_DEF_BYTES)
            definition[0:2] = abi.word(140)
            definition[SND_VC_TONE_PERIOD:SND_VC_TONE_PERIOD + 2] = abi.word(478)
            definition[SND_VC_NOISE_PERIOD:SND_VC_NOISE_PERIOD + 2] = abi.word(-1)
            definition[SND_VC_VOLUME_INDEX:SND_VC_VOLUME_INDEX + 2] = abi.word(11)
            definition[SND_VC_VOL_PHASE:SND_VC_VOL_PHASE + 2] = abi.word(phase)
            sound_play_case(SCRATCH_DEFINITION, 0, volume, -1, 5, idle, all_registers(rng),
                            extra_pokes={SCRATCH_DEFINITION: bytes(definition)})


def test_sound_play_picks_a_free_voice(staged):
    """THE ALLOCATOR IS DEAD CODE IN THE SHIPPED GAME — all fifteen call sites pass a literal 0/1/2.

    It is reachable code all the same, so the differential drives it with the synthetic voice
    arguments no caller uses: anything outside 0..2 takes the first voice whose duration counter is
    zero.
    """
    rng = random.Random(0x9a37)
    for busy in range(8):        # every subset of {0, 1, 2} that can be busy
        records = []
        for voice in range(SND_VOICES):
            record = bytearray(random_record(rng))
            record[SND_VC_DURATION:SND_VC_DURATION + 2] = abi.word(40 if busy & (1 << voice) else 0)
            record[SND_VC_PRIORITY:SND_VC_PRIORITY + 2] = abi.word(0)
            records.append(bytes(record))
        for voice in (-1, 3, 7, -0x8000, 0x7fff):
            sound_play_case(A_snd_def_fx, voice, 8, -1, 15, records, all_registers(rng))


def test_sound_play_evicts_the_lowest_priority_voice(staged):
    """All three busy: compare 0 against 1, then the winner against 2. A TIE GOES TO THE HIGHER
    INDEX, because both compares are `bge` — so an all-equal field is always evicted at voice 2."""
    rng = random.Random(0x9a38)
    priorities = (0, 1, 2, 5, 10)
    for first in priorities:
        for second in priorities:
            for third in priorities:
                records = []
                for voice, priority in enumerate((first, second, third)):
                    record = bytearray(idle_record())
                    record[SND_VC_DURATION:SND_VC_DURATION + 2] = abi.word(40)
                    record[SND_VC_PRIORITY:SND_VC_PRIORITY + 2] = abi.word(priority)
                    records.append(bytes(record))
                # priority 15 outranks every record, so the trigger is never refused and the
                # return value is the allocator's own answer.
                info = sound_play_case(A_snd_def_fx, -1, 8, -1, 15, records, all_registers(rng))
                lower = 1 if first >= second else 0
                expected = 2 if (first, second, third)[lower] >= third else lower
                assert info["ret"] & 0xffff == expected, (
                    f"priorities {(first, second, third)} evicted voice "
                    f"{info['ret'] & 0xffff}, expected {expected}")


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_sound_play_fuzz(staged, chunk):
    """Random definitions, records, voices, volumes, notes and priorities.

    Chunk-SEEDED (`abi.shard`'s docstring tells the two shapes apart): FUZZ_CHUNKS x 10 cases.

    The definition is synthetic rather than one of the 47: a shipped definition never has, say, a
    negative volume index or a phase of 4, and the copy loop puts whatever is in the table straight
    into the record the handler will then run.
    """
    rng = random.Random(0x9a39 + chunk)
    for _ in range(10):
        definition = bytearray(SND_DEF_BYTES)
        for word_index in range(SND_DEF_WORDS):
            definition[2 * word_index:2 * word_index + 2] = abi.word(rng.randrange(0x10000))
        definition[0:2] = abi.word(rng.choice([0, 1, 40, 400, rng.randrange(0x10000)]))
        records = [random_record(rng) for _ in range(SND_VOICES)]
        sound_play_case(SCRATCH_DEFINITION,
                        rng.choice([0, 1, 2, -1, 3, rng.randrange(-0x8000, 0x8000)]),
                        rng.choice([-1, 0, 8, 15, rng.randrange(-0x8000, 0x8000)]),
                        rng.choice([-1, rng.randrange(0, 128), rng.randrange(-0x8000, 0x8000)]),
                        rng.choice([0, 5, 10, 15, rng.randrange(-0x8000, 0x8000)]),
                        records, all_registers(rng),
                        extra_pokes={SCRATCH_DEFINITION: bytes(definition)})


# =================================================================================================
# timer_c_sound_isr @ 0x1459a
# =================================================================================================

def isr_case(records, conterm=0x8f, ticks=1, volume_scale=A_snd_volume_scale,
             top_voice=A_snd_voice + (SND_VOICES - 1) * SND_VOICE_BYTES):
    """One differential over `ticks` handler ticks. A single tick is entered at 0x1459a directly."""
    if ticks == 1:
        entry, chain, stub = ENTRY_TIMER_C_SOUND_ISR, emu.SENTINEL, {}
        glue = lambda lib, buf: lib.g_timer_c_sound_isr(buf)                        # noqa: E731
    else:
        entry, chain = abi.STUB, abi.STUB + abi.CALL_N_TIMES_CHAIN
        stub = abi.call_n_times_stub(ENTRY_TIMER_C_SOUND_ISR, ticks,
                                     counter_register=ISR_TICK_COUNTER_REGISTER)
        glue = lambda lib, buf: lib.g_timer_c_sound_isr_ticks(buf, ticks)           # noqa: E731
    pokes = abi.merge_pokes(isr_state(chain, conterm, volume_scale, top_voice),
                        {TOS_CONTERM: bytes([conterm ^ 0xff])},
                        voice_records(records), stub)
    diffs, _info = abi.run_with_a4(entry, glue, pokes=pokes)
    assert not diffs, report(diffs)
    # ...AND THE SAME CASE AGAINST THE HAND-WRITTEN TWIN. The target build runs
    # `../src/asm/sound_tick.S` where this C runs here (../atari/README.md, "The one core this
    # build does NOT run, and what replaces it"), so
    # every case that verifies the core verifies the code that ships — over the same image and the
    # same PSG ledger, from this one call rather than from a second case list nobody would keep in
    # step. `test_sound_asm.py::test_the_c_battery_runs_the_twin` is what keeps this line here.
    test_sound_asm.assert_twin_matches_the_c(pokes, ticks)


def test_isr_skips_idle_voices(staged):
    """Duration 0 costs nothing — no chip access, no record write — and restores conterm."""
    isr_case([idle_record() for _ in range(SND_VOICES)])


def test_isr_restores_conterm_only_when_every_voice_is_idle(staged):
    """It clears $484 unconditionally on entry and puts the saved byte back only at the end of a
    tick in which all three duration counters are zero."""
    for busy in range(8):
        fields = {
            SND_VC_VOL_PHASE: (2, 1),
            SND_VC_VOL_ATTACK_STEP: (4, 0x1000),
        }
        records = [armed_record(40 if busy & (1 << v) else 0, fields) for v in range(SND_VOICES)]
        isr_case(records)


def test_isr_volume_machine(staged):
    """The ADSR: attack to full scale, decay to the sustain, the hold that stores nothing, and the
    release that zeroes the phase and re-arms the counter as a silence sentinel."""
    for phase in range(5):
        for step in (0x1000, -0x1000, 0x100000, -0x100000):
            fields = {
                SND_VC_TONE_PERIOD: (2, 478),
                SND_VC_VOLUME_INDEX: (2, 12),
                SND_VC_VOL_PHASE: (2, phase),
                SND_VC_VOL_ATTACK_STEP: (4, step),
                SND_VC_VOL_DECAY_STEP: (4, -step),
                SND_VC_VOL_SUSTAIN: (4, 0x60000),
                SND_VC_VOL_RELEASE_STEP: (4, -step),
                SND_VC_VOL_ENV_ACC: (4, 0x30000),
            }
            records = [armed_record(40, fields) for _ in range(SND_VOICES)]
            isr_case(records, ticks=6)


def test_isr_volume_lfo_folds_at_both_limits(staged):
    """The triangle: fold at +limit and at -limit, negating the step, after the onset delay."""
    for limit, step, delay in ((0x8000, 0x3000, 0), (0x8000, -0x3000, 0), (0x8000, 0x3000, 3),
                               (0, 0x3000, 0), (0x7fffffff, 0x40000000, 0)):
        fields = {
            SND_VC_TONE_PERIOD: (2, 478),
            SND_VC_VOLUME_INDEX: (2, 15),
            SND_VC_VOL_PHASE: (2, 3),
            SND_VC_VOL_LFO_LIMIT: (4, limit),
            SND_VC_VOL_LFO_STEP: (4, step),
            SND_VC_VOL_LFO_DELAY: (2, delay),
            SND_VC_VOL_ENV_ACC: (4, 0x80000),
        }
        records = [armed_record(200, fields) for _ in range(SND_VOICES)]
        isr_case(records, ticks=10)


def test_isr_pitch_machine(staged):
    """The three-segment sweep, both directions per segment, into the period write.

    The period is `base * (1 + delta/4096)` rounded and clamped to 12 bits, and the whole write is
    off-image — the PSG ledger is the only thing that can see it.
    """
    for phase in range(5):
        for step, target in ((0x2000, 0x40000), (-0x2000, -0x40000), (0x2000, -0x40000),
                             (-0x2000, 0x40000)):
            fields = {
                SND_VC_TONE_PERIOD: (2, 1214),
                SND_VC_VOLUME_INDEX: (2, 15),
                SND_VC_VOL_PHASE: (2, 3),
                SND_VC_PITCH_PHASE: (2, phase),
                SND_VC_PITCH_STEP1: (4, step),
                SND_VC_PITCH_TARGET1: (4, target),
                SND_VC_PITCH_STEP2: (4, -step),
                SND_VC_PITCH_TARGET2: (4, -target),
                SND_VC_PITCH_RELEASE_STEP: (4, step),
                SND_VC_PITCH_ENV_ACC: (4, 0x1000),
            }
            records = [armed_record(60, fields) for _ in range(SND_VOICES)]
            isr_case(records, ticks=8)


def test_isr_pitch_lfo_reloads_its_step_on_a_carry(staged):
    """The two-rate sweep: a carry out of the 32-bit add swaps the step for one of two reloads.

    The huge steps are what make the carry reachable at all — a plausible one never wraps.
    """
    for step, reload_up, reload_down in ((0x40000000, 0x1000, -0x1000),
                                         (-0x40000000, 0x1000, -0x1000),
                                         (0x7fffffff, -0x7fffffff, 0x7fffffff)):
        fields = {
            SND_VC_TONE_PERIOD: (2, 477),
            SND_VC_VOLUME_INDEX: (2, 15),
            SND_VC_VOL_PHASE: (2, 3),
            SND_VC_PITCH_LFO_LIMIT_HI: (4, 0x20000000),
            SND_VC_PITCH_LFO_STEP: (4, step),
            SND_VC_PITCH_LFO_STEP_RELOAD_UP: (4, reload_up),
            SND_VC_PITCH_LFO_LIMIT_LO: (4, -0x20000000),
            SND_VC_PITCH_LFO_STEP_RELOAD_DOWN: (4, reload_down),
            SND_VC_PITCH_LFO_DELAY: (2, 0),
            SND_VC_PITCH_LFO_ACC: (4, 0x10000000),
        }
        records = [armed_record(200, fields) for _ in range(SND_VOICES)]
        isr_case(records, ticks=10)


def test_isr_noise_machine_and_its_byte_wide_clamp(staged):
    """The noise period write, including the `cmp.b #$1f` on a WORD value.

    A result of 0x90 is a NEGATIVE byte, slips past the clamp and reaches the chip whole — the chip
    then takes its low five bits. The values below straddle that: 0x1f, 0x20 (clamped), 0x80 and
    0x90 (not).
    """
    for delta in (0, 0x1f0000, 0x200000, 0x800000, 0x900000, -0x10000):
        fields = {
            SND_VC_NOISE_PERIOD: (2, 16),
            SND_VC_VOLUME_INDEX: (2, 15),
            SND_VC_VOL_PHASE: (2, 3),
            SND_VC_NOISE_PHASE: (2, 3),
            SND_VC_NOISE_LFO_LIMIT: (4, 0x1000),
            SND_VC_NOISE_ENV_ACC: (4, delta),
        }
        records = [armed_record(60, fields) for _ in range(SND_VOICES)]
        isr_case(records, ticks=3)


def test_isr_selects_the_phase_with_a_byte_compare(staged):
    """A phase word whose HIGH byte is set still selects on its low one.

    `sound_play` copies a definition's word straight into the field, so this is reachable data
    rather than a hypothetical; without it a reconstruction comparing the whole word is green.
    """
    for high in (0x00, 0x01, 0x7f, 0xff):
        for low in range(5):
            phase = (high << 8) | low
            fields = {
                SND_VC_TONE_PERIOD: (2, 478),
                SND_VC_NOISE_PERIOD: (2, 16),
                SND_VC_VOLUME_INDEX: (2, 12),
                SND_VC_VOL_PHASE: (2, phase),
                SND_VC_VOL_ATTACK_STEP: (4, 0x8000),
                SND_VC_VOL_DECAY_STEP: (4, -0x8000),
                SND_VC_VOL_SUSTAIN: (4, 0x40000),
                SND_VC_VOL_RELEASE_STEP: (4, -0x8000),
                SND_VC_PITCH_PHASE: (2, phase),
                SND_VC_PITCH_STEP1: (4, 0x2000),
                SND_VC_PITCH_TARGET1: (4, 0x40000),
                SND_VC_PITCH_STEP2: (4, -0x2000),
                SND_VC_PITCH_TARGET2: (4, -0x40000),
                SND_VC_PITCH_RELEASE_STEP: (4, -0x2000),
                SND_VC_NOISE_PHASE: (2, phase),
                SND_VC_NOISE_STEP1: (4, 0x2000),
                SND_VC_NOISE_TARGET1: (4, 0x40000),
                SND_VC_NOISE_STEP2: (4, -0x2000),
                SND_VC_NOISE_TARGET2: (4, -0x40000),
                SND_VC_NOISE_RELEASE_STEP: (4, -0x2000),
                SND_VC_VOL_ENV_ACC: (4, 0x30000),
                SND_VC_PITCH_ENV_ACC: (4, 0x10000),
                SND_VC_NOISE_ENV_ACC: (4, 0x10000),
            }
            records = [armed_record(40, fields) for _ in range(SND_VOICES)]
            isr_case(records, ticks=4)


def test_isr_volume_multiply_aliases_above_a_full_scale_accumulator(staged):
    """`muls.w` takes the LOW WORDS, so a summed accumulator at or above 0x01000000 folds.

    The shipped definitions stay far below it; this pins the arithmetic as written rather than as a
    widened "obviously intended" version.
    """
    for accumulator in (0x00ff8000, 0x01000000, 0x02008000, 0x7fffffff):
        fields = {
            SND_VC_VOLUME_INDEX: (2, 15),
            SND_VC_VOL_PHASE: (2, 3),
            SND_VC_VOL_ENV_ACC: (4, accumulator),
        }
        records = [armed_record(40, fields) for _ in range(SND_VOICES)]
        isr_case(records)


def test_isr_does_not_bound_the_volume_index(staged):
    """`move.w 6(a0),d0 / add.w d0,d0 / move.w (a2,d0.w),d0` — the index is doubled as a WORD and
    then SIGN-EXTENDED, and nothing checks it against the table's 16 entries.

    `sound_play` will happily put any word there (its `volume` argument, or a definition's own
    field), so an index outside 0..15 reads past the table — and 0x4000 reads BELOW it, because
    doubling it makes the word offset negative. Every value here lands inside the image, so the
    difference is a byte written to the chip rather than a fault.
    """
    for index in (16, 0x100, 0x4000, 0x7fff, -1, -0x8000):
        fields = {
            SND_VC_VOLUME_INDEX: (2, index),
            SND_VC_VOL_PHASE: (2, 3),
            SND_VC_VOL_ENV_ACC: (4, 0x40000),
        }
        records = [armed_record(40, fields) for _ in range(SND_VOICES)]
        isr_case(records)


def test_isr_key_off_forces_every_running_machine_into_its_release(staged):
    """The countdown, and what reaching zero does: free the voice, then either write volume 0 (an
    already-idle volume envelope) or take the counter to -1 and release all three machines, turning
    a release step round if it does not already point back toward zero."""
    for volume_phase in (0, 1, 3):
        for pitch_phase in (0, 1, 4):
            for pitch_step in (0x1000, -0x1000):
                fields = {
                    SND_VC_TONE_PERIOD: (2, 478),
                    SND_VC_NOISE_PERIOD: (2, 16),
                    SND_VC_VOLUME_INDEX: (2, 12),
                    SND_VC_VOL_PHASE: (2, volume_phase),
                    SND_VC_VOL_RELEASE_STEP: (4, -0x4000),
                    SND_VC_PITCH_PHASE: (2, pitch_phase),
                    SND_VC_PITCH_RELEASE_STEP: (4, pitch_step),
                    SND_VC_NOISE_PHASE: (2, pitch_phase),
                    SND_VC_NOISE_RELEASE_STEP: (4, -pitch_step),
                    SND_VC_VOL_ENV_ACC: (4, 0x40000),
                    SND_VC_PITCH_ENV_ACC: (4, 0x20000),
                    SND_VC_NOISE_ENV_ACC: (4, 0x20000),
                }
                records = [armed_record(2, fields) for _ in range(SND_VOICES)]
                isr_case(records, ticks=5)


def test_isr_a_non_negative_gate_never_counts_down(staged):
    """A sustained sound (triggered with `note >= 0`) runs for ever until a caller stops it."""
    for gate in (0, 60, 250, 0x7fff):
        fields = {
            SND_VC_TONE_PERIOD: (2, 478),
            SND_VC_VOLUME_INDEX: (2, 12),
            SND_VC_VOL_PHASE: (2, 1),
            SND_VC_VOL_ATTACK_STEP: (4, 0x8000),
            SND_VC_GATE: (2, gate),
        }
        records = [armed_record(1, fields) for _ in range(SND_VOICES)]
        isr_case(records, ticks=6)


def test_isr_reads_its_pointers_out_of_the_state_block(staged):
    """The handler takes `&snd_volume_scale` and `&snd_voice[2]` from 0x14936/0x1493a, not from a
    constant — which is what makes `install_sound_vectors` load-bearing rather than decorative.

    Moving the record base is the strong half: the whole tick then runs somewhere else in the image
    and the untouched real arena is what says so.
    """
    rng = random.Random(0x9a40)
    records = [random_record(rng) for _ in range(SND_VOICES)]
    relocated = abi.SCRATCH + 0x400
    pokes = abi.merge_pokes(isr_state(emu.SENTINEL, 0x8f, A_snd_volume_scale,
                                  relocated + (SND_VOICES - 1) * SND_VOICE_BYTES),
                        {TOS_CONTERM: bytes([0x70])},
                        {relocated: b"".join(records)},
                        abi.seed_spans(0x5ec2, [(relocated - abi.GUARD_BYTES, relocated),
                                                (relocated + SND_VOICES * SND_VOICE_BYTES,
                                                 relocated + SND_VOICES * SND_VOICE_BYTES
                                                 + abi.GUARD_BYTES)]))
    diffs, _info = abi.run_with_a4(ENTRY_TIMER_C_SOUND_ISR,
                                   lambda lib, buf: lib.g_timer_c_sound_isr(buf), pokes=pokes)
    assert not diffs, report(diffs)
    # ...AND THIS IS THE ONE BATTERY THE TWIN MOST NEEDS. Its two pointer loads are the only
    # arithmetic in `../src/asm/sound_tick.S` that is NOT a transcription of the original — the
    # original reads two absolute addresses out of its own TEXT, the twin reads them out of the
    # image and adds the base — so they lie outside the bracket the transcription pin covers, and a
    # relocated record base is what tells a right one from a wrong one. This case does not go
    # through `isr_case` (it stages its own pokes), so the call it makes is spelt here too.
    test_sound_asm.assert_twin_matches_the_c(pokes, 1)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_isr_fuzz_random_records(staged, chunk):
    """Random voice records, several ticks each: every phase, both step signs, LFOs on and off.

    Chunk-SEEDED, so the suite runs FUZZ_CHUNKS x 10 records rather than splitting one list."""
    rng = random.Random(0x9a41 + chunk)
    for _ in range(10):
        records = [random_record(rng) for _ in range(SND_VOICES)]
        isr_case(records, conterm=rng.randrange(0x100), ticks=rng.choice([1, 2, 4, 8]))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_isr_runs_every_real_definition(staged, chunk):
    """Each of the 47 shipped definitions, loaded into all three records and ticked.

    A definition IS the record's first 0x70 bytes, so it can be staged directly rather than through
    `sound_play` — which keeps this a test of the HANDLER over real data. The gate is forced
    negative and the accumulators zeroed, which is the state `sound_play` leaves.
    """
    for at in abi.shard(ALL_DEFINITIONS, chunk, FUZZ_CHUNKS):
        # Out of the POST-INIT image: the definitions are BSS, so the loader's own bytes are zeros.
        definition = staged[at:at + SND_DEF_BYTES]
        record = bytearray(SND_VOICE_BYTES)
        record[:SND_DEF_BYTES] = definition
        record[SND_VC_GATE:SND_VC_GATE + 2] = abi.word(-1)
        record[SND_VC_PRIORITY:SND_VC_PRIORITY + 2] = abi.word(5)
        isr_case([bytes(record)] * SND_VOICES, ticks=12)


# =================================================================================================
# install_sound_vectors @ 0x148ea, remove_sound_vectors @ 0x1491c,
# sound_start @ 0x14982, sound_stop @ 0x1499c
# =================================================================================================

def test_install_sound_vectors(staged):
    """Saves $114 and $484, hands the handler its two pointers, takes both vectors, and puts the
    MFP into AUTOMATIC end-of-interrupt mode.

    The MFP write is off-image: the kit's hardware WRITE ledger is the only surface that can see it,
    and a candidate that skipped it would be byte-for-byte identical without it.
    """
    for saved_vector, conterm in ((0x00fc1234, 0x00), (0x0, 0xff), (0xdeadbee0, 0x0f)):
        pokes = abi.merge_pokes({TOS_VEC_TIMER_C: abi.long(saved_vector)},
                            {TOS_CONTERM: bytes([conterm])},
                            {TOS_VEC_TRAP9: abi.long(0)},
                            abi.seed_spans(0x5ec3, [(SND_ISR_SAVED_TIMER_C,
                                                      SND_ISR_SAVED_TIMER_C
                                                      + SND_ISR_STATE_BYTES)]))
        diffs, _info = abi.run_with_a4(ENTRY_INSTALL_SOUND_VECTORS,
                                       lambda lib, buf: lib.g_install_sound_vectors(buf),
                                       pokes=pokes)
        assert not diffs, report(diffs)


def test_remove_sound_vectors(staged):
    """Puts $114 and $484 back and returns the MFP to TOS's software EOI. THE TRAP #9 VECTOR IS
    DELIBERATELY NOT RESTORED — the handler stays resident for the life of the program."""
    for saved_vector, conterm in ((0x00fc1234, 0x8f), (0x0, 0x00)):
        pokes = abi.merge_pokes(isr_state(saved_vector, conterm),
                            {TOS_CONTERM: bytes([conterm ^ 0xff])},
                            {TOS_VEC_TIMER_C: abi.long(SND_ISR_ENTRY)},
                            {TOS_VEC_TRAP9: abi.long(SND_TRAP9_HANDLER_ENTRY)})
        diffs, _info = abi.run_with_a4(ENTRY_REMOVE_SOUND_VECTORS,
                                       lambda lib, buf: lib.g_remove_sound_vectors(buf),
                                       pokes=pokes)
        assert not diffs, report(diffs)


def supexec_case(entry, glue, caller_a1, caller_a2, records, seed, pokes):
    diffs, _info = abi.run_with_a4(entry,
                                   lambda lib, buf: getattr(lib, glue)(buf, caller_a1, caller_a2),
                                   pokes=abi.merge_pokes(voice_records(records), pokes),
                                   regs={"a1": caller_a1, "a2": caller_a2}, psg_seed=seed)
    assert not diffs, report(diffs)


def test_sound_start(staged):
    """`Supexec(install_sound_vectors)` then `sound_stop_all`.

    THE TRAMPOLINE IS PART OF THE DIFF. `xbios_trap` @ 0x15e3c parks the caller's a1/a2 and its own
    return address in three BSS longs before the trap, and those stores are ordinary image state —
    which is why the reconstruction takes a1/a2 as arguments and the case sets them.
    """
    rng = random.Random(0x9a50)
    for caller_a1, caller_a2 in ((0, 0), (0x12345678, 0x9abcdef0), (0xffffffff, 0x00010002)):
        records = [random_record(rng) for _ in range(SND_VOICES)]
        supexec_case(ENTRY_SOUND_START, "g_sound_start", caller_a1, caller_a2, records,
                     all_registers(rng),
                     abi.merge_pokes({TOS_VEC_TIMER_C: abi.long(0x00fc1234)},
                                 {TOS_CONTERM: bytes([0x8f])},
                                 abi.seed_spans(0x5ec4,
                                                [(SND_ISR_SAVED_TIMER_C,
                                                  SND_ISR_SAVED_TIMER_C + SND_ISR_STATE_BYTES),
                                                 (A_trap_saved_ret, A_trap_saved_a1 + 4)])))


def test_sound_stop(staged):
    """`sound_stop_all` then `Supexec(remove_sound_vectors)` — the trap #9 vector has to be staged
    for the stop, because the gate runs BEFORE the installer would have written it."""
    rng = random.Random(0x9a51)
    for caller_a1, caller_a2 in ((0, 0), (0x0badf00d, 0x00c0ffee)):
        records = [random_record(rng) for _ in range(SND_VOICES)]
        supexec_case(ENTRY_SOUND_STOP, "g_sound_stop", caller_a1, caller_a2, records,
                     all_registers(rng),
                     abi.merge_pokes(trap9_vector(),
                                 isr_state(0x00fc1234, 0x8f),
                                 {TOS_CONTERM: bytes([0x00])},
                                 {TOS_VEC_TIMER_C: abi.long(SND_ISR_ENTRY)},
                                 abi.seed_spans(0x5ec5,
                                                [(A_trap_saved_ret, A_trap_saved_a1 + 4)])))


# =================================================================================================
# The cross-file pins (test_constants.py discovers these)
# =================================================================================================

MIRRORS = (
    ("A_snd_voice", "include/sound.h", "A_snd_voice"),
    ("A_snd_note_period", "include/sound.h", "A_snd_note_period"),
    ("A_snd_volume_scale", "include/sound.h", "A_snd_volume_scale"),
    ("A_snd_mixer_and_mask", "include/sound.h", "A_snd_mixer_and_mask"),
    ("A_snd_def_level", "include/sound.h", "A_snd_def_level"),
    ("A_snd_def_fx", "include/sound.h", "A_snd_def_fx"),
    ("A_trap_saved_ret", "include/clib.h", "A_trap_saved_ret"),
    ("A_trap_saved_a1", "include/clib.h", "A_trap_saved_a1"),
    ("SND_ISR_SAVED_TIMER_C", "include/sound.h", "SND_ISR_SAVED_TIMER_C"),
    ("SND_ISR_VOLUME_SCALE", "include/sound.h", "SND_ISR_VOLUME_SCALE"),
    ("SND_ISR_TOP_VOICE", "include/sound.h", "SND_ISR_TOP_VOICE"),
    ("SND_ISR_SAVED_CONTERM", "include/sound.h", "SND_ISR_SAVED_CONTERM"),
    ("SND_ISR_STATE_BYTES", "include/sound.h", "SND_ISR_STATE_BYTES"),
    ("SND_ISR_ENTRY", "include/sound.h", "SND_ISR_ENTRY"),
    ("SND_TRAP9_HANDLER_ENTRY", "include/sound.h", "SND_TRAP9_HANDLER_ENTRY"),
    ("TOS_VEC_TRAP9", "include/sound.h", "TOS_VEC_TRAP9"),
    ("TOS_VEC_TIMER_C", "include/sound.h", "TOS_VEC_TIMER_C"),
    ("TOS_CONTERM", "include/sound.h", "TOS_CONTERM"),
    ("MFP_VECTOR_REG", "include/sound.h", "MFP_VECTOR_REG"),
    ("MFP_VECTOR_AUTO_EOI", "include/sound.h", "MFP_VECTOR_AUTO_EOI"),
    ("MFP_VECTOR_SW_EOI", "include/sound.h", "MFP_VECTOR_SW_EOI"),
    ("SND_VOICES", "include/sound.h", "SND_VOICES"),
    ("SND_VOICE_BYTES", "include/sound.h", "SND_VOICE_BYTES"),
    ("SND_DEF_WORDS", "include/sound.h", "SND_DEF_WORDS"),
    ("SND_DEF_BYTES", "include/sound.h", "SND_DEF_BYTES"),
    ("SND_VC_DURATION", "include/sound.h", "SND_VC_DURATION"),
    ("SND_VC_TONE_PERIOD", "include/sound.h", "SND_VC_TONE_PERIOD"),
    ("SND_VC_NOISE_PERIOD", "include/sound.h", "SND_VC_NOISE_PERIOD"),
    ("SND_VC_VOLUME_INDEX", "include/sound.h", "SND_VC_VOLUME_INDEX"),
    ("SND_VC_VOL_PHASE", "include/sound.h", "SND_VC_VOL_PHASE"),
    ("SND_VC_VOL_ATTACK_STEP", "include/sound.h", "SND_VC_VOL_ATTACK_STEP"),
    ("SND_VC_VOL_DECAY_STEP", "include/sound.h", "SND_VC_VOL_DECAY_STEP"),
    ("SND_VC_VOL_SUSTAIN", "include/sound.h", "SND_VC_VOL_SUSTAIN"),
    ("SND_VC_VOL_RELEASE_STEP", "include/sound.h", "SND_VC_VOL_RELEASE_STEP"),
    ("SND_VC_VOL_LFO_LIMIT", "include/sound.h", "SND_VC_VOL_LFO_LIMIT"),
    ("SND_VC_VOL_LFO_STEP", "include/sound.h", "SND_VC_VOL_LFO_STEP"),
    ("SND_VC_VOL_LFO_DELAY", "include/sound.h", "SND_VC_VOL_LFO_DELAY"),
    ("SND_VC_PITCH_PHASE", "include/sound.h", "SND_VC_PITCH_PHASE"),
    ("SND_VC_PITCH_STEP1", "include/sound.h", "SND_VC_PITCH_STEP1"),
    ("SND_VC_PITCH_TARGET1", "include/sound.h", "SND_VC_PITCH_TARGET1"),
    ("SND_VC_PITCH_STEP2", "include/sound.h", "SND_VC_PITCH_STEP2"),
    ("SND_VC_PITCH_TARGET2", "include/sound.h", "SND_VC_PITCH_TARGET2"),
    ("SND_VC_PITCH_RELEASE_STEP", "include/sound.h", "SND_VC_PITCH_RELEASE_STEP"),
    ("SND_VC_PITCH_LFO_LIMIT_HI", "include/sound.h", "SND_VC_PITCH_LFO_LIMIT_HI"),
    ("SND_VC_PITCH_LFO_STEP", "include/sound.h", "SND_VC_PITCH_LFO_STEP"),
    ("SND_VC_PITCH_LFO_STEP_RELOAD_UP", "include/sound.h", "SND_VC_PITCH_LFO_STEP_RELOAD_UP"),
    ("SND_VC_PITCH_LFO_LIMIT_LO", "include/sound.h", "SND_VC_PITCH_LFO_LIMIT_LO"),
    ("SND_VC_PITCH_LFO_STEP_RELOAD_DOWN", "include/sound.h", "SND_VC_PITCH_LFO_STEP_RELOAD_DOWN"),
    ("SND_VC_PITCH_LFO_DELAY", "include/sound.h", "SND_VC_PITCH_LFO_DELAY"),
    ("SND_VC_NOISE_PHASE", "include/sound.h", "SND_VC_NOISE_PHASE"),
    ("SND_VC_NOISE_STEP1", "include/sound.h", "SND_VC_NOISE_STEP1"),
    ("SND_VC_NOISE_TARGET1", "include/sound.h", "SND_VC_NOISE_TARGET1"),
    ("SND_VC_NOISE_STEP2", "include/sound.h", "SND_VC_NOISE_STEP2"),
    ("SND_VC_NOISE_TARGET2", "include/sound.h", "SND_VC_NOISE_TARGET2"),
    ("SND_VC_NOISE_RELEASE_STEP", "include/sound.h", "SND_VC_NOISE_RELEASE_STEP"),
    ("SND_VC_NOISE_LFO_LIMIT", "include/sound.h", "SND_VC_NOISE_LFO_LIMIT"),
    ("SND_VC_NOISE_LFO_STEP", "include/sound.h", "SND_VC_NOISE_LFO_STEP"),
    ("SND_VC_NOISE_LFO_DELAY", "include/sound.h", "SND_VC_NOISE_LFO_DELAY"),
    ("SND_VC_GATE", "include/sound.h", "SND_VC_GATE"),
    ("SND_VC_PRIORITY", "include/sound.h", "SND_VC_PRIORITY"),
    ("SND_VC_VOL_ENV_ACC", "include/sound.h", "SND_VC_VOL_ENV_ACC"),
    ("SND_VC_VOL_LFO_ACC", "include/sound.h", "SND_VC_VOL_LFO_ACC"),
    ("SND_VC_PITCH_ENV_ACC", "include/sound.h", "SND_VC_PITCH_ENV_ACC"),
    ("SND_VC_PITCH_LFO_ACC", "include/sound.h", "SND_VC_PITCH_LFO_ACC"),
    ("SND_VC_NOISE_ENV_ACC", "include/sound.h", "SND_VC_NOISE_ENV_ACC"),
    ("SND_VC_NOISE_LFO_ACC", "include/sound.h", "SND_VC_NOISE_LFO_ACC"),
    ("SND_VOL_ENV_PEAK", "include/sound.h", "SND_VOL_ENV_PEAK"),
    ("SND_NOTE_MAX", "include/sound.h", "SND_NOTE_MAX"),
    ("SND_NOTE_MIN", "include/sound.h", "SND_NOTE_MIN"),
    ("SND_NOTE_OCTAVE", "include/sound.h", "SND_NOTE_OCTAVE"),
)

# The first bytes of each routine, read off the loaded image. `sound_stop_voice` and
# `sound_release_voice` open with the SAME ten bytes (`link a6,#0` then `cmpi.w #$0,8(a6)`), so
# every prologue here is twelve — a length that tells all eleven apart.
ENTRY_PROLOGUES = {
    "ENTRY_SOUND_PLAY": "4e56fffa48e70f30266e0008",
    "ENTRY_SOUND_STOP_VOICE": "4e5600000c6e000000086d3c",
    "ENTRY_SOUND_RELEASE_VOICE": "4e5600000c6e000000086d3e",
    "ENTRY_SOUND_VOICE_PRIORITY": "4e560000302e0008c1fc008c",
    "ENTRY_SOUND_STOP_ALL": "4e56fffe426efffe600e3f2e",
    "ENTRY_TIMER_C_SOUND_ISR": "48e7f0e0247a0396207a0396",
    "ENTRY_PSG_GATE": "322f0004302f0006342f0008",
    "ENTRY_INSTALL_SOUND_VECTORS": "41fa004620f8011443ecddc0",
    "ENTRY_REMOVE_SOUND_VECTORS": "21fa0014011411fa001a0484",
    "ENTRY_SOUND_START": "4e560000487aff623f3c0026",
    "ENTRY_SOUND_STOP": "4e5600004ebafbd4487aff76",
}
